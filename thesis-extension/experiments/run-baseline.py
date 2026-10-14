#!/usr/bin/env python3
"""run-baseline.py: compare fixed retrieval strategies with the RL-selected one (Problem A).

Every question is run non-interactively through ollama-mcp's own chat loop (run_chat):
the typed input is replaced by the question followed by "exit", a fresh session (and a
fresh sr8-mcp subprocess) is started per question so answers never see earlier questions,
and the turn record that ollama-mcp writes is captured for scoring.

Modes
  --train --passes N   run experiments/train_questions.csv N times with
                       RETRIEVAL_STRATEGY=rl and RL_LEARNING=true, so Problem A
                       (problem_a in .rl-model.json) learns from every adr_lookup turn.
  --evaluate           run experiments/questions.csv once per strategy in
                       graph_first, documents_first, hybrid, rl with RL_LEARNING=false
                       (the learned policy is used greedily and nothing is saved).

Outputs (experiments/results/)
  <mode>-<timestamp>.csv           one row per question and strategy
  <mode>-<timestamp>-summary.csv   per-strategy means, plus Problem A's update count
  <mode>-<timestamp>-turns.jsonl   the full ollama-mcp turn records
  <mode>-<timestamp>-transcript.txt everything the chat client printed

Requirements: Neo4j running with the schema and extracted graph loaded, Ollama running
with the model pulled, and the same Python environment as ollama-mcp / sr8-mcp.
Note that the model is offered all 39 sr8-mcp tools, including the write tools.
"""

import argparse
import asyncio
import contextlib
import csv
import importlib.machinery
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

EXPERIMENTS_DIR = Path(__file__).resolve().parent
EXT_DIR = EXPERIMENTS_DIR.parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
EVAL_QUESTIONS = EXPERIMENTS_DIR / "questions.csv"
TRAIN_QUESTIONS = EXPERIMENTS_DIR / "train_questions.csv"
STRATEGIES = ["graph_first", "documents_first", "hybrid", "rl"]
MAX_CONSECUTIVE_ERRORS = 3

ROW_FIELDS = [
    "mode", "pass", "question_id", "category", "strategy", "route", "rl_state", "rl_action",
    "forced_strategy", "model_cited", "fallback_used", "evidence_appended",
    "expected_ids_total", "expected_ids_found", "expected_ids_fraction",
    "tool_calls", "tool_errors", "llm_calls", "latency_ms", "rl_updated", "error",
]
SUMMARY_FIELDS = [
    "strategy", "questions", "errors", "not_rl_route", "model_cited_rate", "fallback_rate",
    "evidence_appended_rate", "expected_ids_found_mean", "expected_ids_fraction_mean",
    "tool_calls_mean", "llm_calls_mean", "latency_ms_mean", "rl_updates",
]


def _load_by_path(name: str, path: Path, register: bool = False) -> Any:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[name] = module  # reinforcemnt-learning's dataclasses need this
    loader.exec_module(module)
    return module


def load_client() -> Any:
    return _load_by_path("ollama_mcp_client", EXT_DIR / "ollama-mcp")


def problem_a_status() -> dict[str, Any]:
    """Problem A as saved in the model file: live update count, epsilon and adr_lookup Q-values."""
    rl = _load_by_path("rl_module_for_experiments", EXT_DIR / "reinforcemnt-learning.py", register=True)
    path = _load_by_path("rl_model_path_for_experiments", EXT_DIR / "rl_model_path.py").resolve_rl_model_path()
    agent = rl.load_problem(path, rl.PROBLEM_A)
    return {
        "model_file": str(path),
        "updates": len(agent.episode_rewards),
        "epsilon": agent.config.exploration_rate,
        "adr_lookup_q": dict(agent.q_table.get("adr_lookup", {})),
    }


def read_questions(path: Path, limit: Optional[int] = None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit] if limit else rows


def expected_ids_found(answer: Optional[str], expected: str) -> tuple[int, int, float]:
    """(found, total, fraction) of the expected requirement IDs mentioned in the answer (case-insensitive)."""
    ids = [i.strip() for i in expected.split(";") if i.strip()]
    text = (answer or "").upper()
    found = sum(1 for i in ids if i.upper() in text)
    return found, len(ids), (found / len(ids) if ids else 0.0)


def run_question(client: Any, question: str, model: str, strategy: str, learning: bool,
                 transcript: Any) -> dict[str, Any]:
    """Run one question through client.run_chat and return the turn record it logged."""
    os.environ["RETRIEVAL_STRATEGY"] = strategy
    os.environ["RL_LEARNING"] = "true" if learning else "false"
    captured: list[dict[str, Any]] = []
    original_finish = client._finish_turn
    inputs = iter([question, "exit"])

    def capture(turn: dict[str, Any], path: Any = None) -> None:
        original_finish(turn, path)
        captured.append(turn)

    client._finish_turn = capture
    client.input = lambda prompt="": next(inputs)
    try:
        with contextlib.redirect_stdout(transcript):
            asyncio.run(client.run_chat(
                model=model, server_command=sys.executable, server_args=[str(EXT_DIR / "sr8-mcp")],
            ))
    finally:
        client._finish_turn = original_finish
    if not captured:
        raise RuntimeError("the chat loop finished without recording a turn")
    return captured[0]


def score(turn: Optional[dict[str, Any]], question: dict[str, str], strategy: str, mode: str,
          pass_number: int, error: str = "") -> dict[str, Any]:
    turn = turn or {}
    reward = turn.get("reward_components") or {}
    found, total, fraction = expected_ids_found(turn.get("answer"), question["expected_requirement_ids"])
    tool_calls = turn.get("tool_calls") or []
    return {
        "mode": mode, "pass": pass_number, "question_id": question["question_id"],
        "category": question["category"], "strategy": strategy, "route": turn.get("route"),
        "rl_state": turn.get("rl_state"), "rl_action": turn.get("rl_action"),
        "forced_strategy": turn.get("forced_strategy"),
        "model_cited": reward.get("model_cited"), "fallback_used": reward.get("fallback_used"),
        "evidence_appended": turn.get("evidence_appended"),
        "expected_ids_total": total, "expected_ids_found": found, "expected_ids_fraction": round(fraction, 4),
        "tool_calls": len(tool_calls), "tool_errors": sum(1 for c in tool_calls if c.get("status") == "error"),
        "llm_calls": turn.get("llm_calls"), "latency_ms": turn.get("latency_ms"),
        "rl_updated": bool(turn.get("rl_updated")), "error": error,
    }


def _mean(values: list[Any]) -> Optional[float]:
    nums = [float(v) for v in values if v is not None and v != ""]
    return round(sum(nums) / len(nums), 4) if nums else None


def summarise(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-strategy means over the rows that completed without error."""
    summary = []
    for strategy in dict.fromkeys(r["strategy"] for r in rows):
        mine = [r for r in rows if r["strategy"] == strategy]
        ok = [r for r in mine if not r["error"]]
        summary.append({
            "strategy": strategy,
            "questions": len(mine),
            "errors": len(mine) - len(ok),
            "not_rl_route": sum(1 for r in ok if r["route"] != "rl_prefetch"),
            "model_cited_rate": _mean([r["model_cited"] for r in ok]),
            "fallback_rate": _mean([r["fallback_used"] for r in ok]),
            "evidence_appended_rate": _mean([r["evidence_appended"] for r in ok]),
            "expected_ids_found_mean": _mean([r["expected_ids_found"] for r in ok]),
            "expected_ids_fraction_mean": _mean([r["expected_ids_fraction"] for r in ok]),
            "tool_calls_mean": _mean([r["tool_calls"] for r in ok]),
            "llm_calls_mean": _mean([r["llm_calls"] for r in ok]),
            "latency_ms_mean": _mean([r["latency_ms"] for r in ok]),
            "rl_updates": sum(1 for r in mine if r["rl_updated"]),
        })
    return summary


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(mode: str, plan: list[tuple[int, str, dict[str, str]]], learning: bool, model: Optional[str],
        client_factory: Callable[[], Any] = load_client, status: Callable[[], dict] = problem_a_status,
        results_dir: Path = RESULTS_DIR) -> dict[str, Any]:
    """Run (pass, strategy, question) items and write the results; returns paths and summary."""
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = results_dir / f"{mode}-{stamp}"
    client = client_factory()
    client.TURN_LOG_PATH = Path(f"{base}-turns.jsonl")
    model = model or client._ollama_model()
    before = status()

    rows: list[dict[str, Any]] = []
    consecutive_errors = 0
    with open(f"{base}-transcript.txt", "w", encoding="utf-8") as transcript:
        for n, (pass_number, strategy, question) in enumerate(plan, start=1):
            print(f"[{n}/{len(plan)}] {mode} pass {pass_number} {strategy:<15} {question['question_id']}", flush=True)
            print(f"\n===== {question['question_id']} | {strategy} | pass {pass_number} =====", file=transcript)
            try:
                turn = run_question(client, question["question"], model, strategy, learning, transcript)
                rows.append(score(turn, question, strategy, mode, pass_number))
                consecutive_errors = 0
            except Exception as exc:
                rows.append(score(None, question, strategy, mode, pass_number, error=f"{type(exc).__name__}: {exc}"))
                consecutive_errors += 1
                print(f"    error: {exc}", flush=True)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"Stopping after {MAX_CONSECUTIVE_ERRORS} consecutive errors "
                          "(is Ollama running and is Neo4j reachable?).", flush=True)
                    break

    after = status()
    summary = summarise(rows)
    summary_rows = summary + [
        {"strategy": "problem_a_updates_this_run", "rl_updates": sum(1 for r in rows if r["rl_updated"])},
        {"strategy": "problem_a_updates_total_before", "rl_updates": before["updates"]},
        {"strategy": "problem_a_updates_total_after", "rl_updates": after["updates"]},
    ]
    write_csv(Path(f"{base}.csv"), ROW_FIELDS, rows)
    write_csv(Path(f"{base}-summary.csv"), SUMMARY_FIELDS, summary_rows)

    print(f"\n{mode} summary (means over completed questions)")
    print(f"{'strategy':<16}{'n':>4}{'err':>5}{'cited':>8}{'fallback':>10}{'ids_frac':>10}"
          f"{'tools':>7}{'llm':>6}{'latency_ms':>12}")
    for s in summary:
        fmt = lambda v, w, p=3: f"{v:>{w}.{p}f}" if isinstance(v, float) else f"{'-':>{w}}"  # noqa: E731
        print(f"{s['strategy']:<16}{s['questions']:>4}{s['errors']:>5}{fmt(s['model_cited_rate'], 8)}"
              f"{fmt(s['fallback_rate'], 10)}{fmt(s['expected_ids_fraction_mean'], 10)}"
              f"{fmt(s['tool_calls_mean'], 7, 2)}{fmt(s['llm_calls_mean'], 6, 2)}{fmt(s['latency_ms_mean'], 12, 0)}")
    print(f"\nProblem A updates: {sum(1 for r in rows if r['rl_updated'])} in this run; "
          f"{before['updates']} -> {after['updates']} in total ({after['model_file']}).")
    print(f"Problem A epsilon {before['epsilon']:.4f} -> {after['epsilon']:.4f}; "
          f"adr_lookup Q after: {json.dumps({k: round(v, 4) for k, v in after['adr_lookup_q'].items()})}")
    not_rl = sum(s["not_rl_route"] for s in summary)
    if not_rl:
        print(f"Warning: {not_rl} question run(s) did not take the RL route, so the strategy did not apply to them.")
    print(f"Results: {base}.csv\nSummary: {base}-summary.csv")
    return {"rows": rows, "summary": summary, "base": str(base), "before": before, "after": after}


def build_plan(mode: str, passes: int, strategies: list[str], limit: Optional[int],
               eval_path: Path = EVAL_QUESTIONS, train_path: Path = TRAIN_QUESTIONS) -> list:
    if mode == "train":
        questions = read_questions(train_path, limit)
        return [(p, "rl", q) for p in range(1, passes + 1) for q in questions]
    questions = read_questions(eval_path, limit)
    return [(1, s, q) for s in strategies for q in questions]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare fixed retrieval strategies with the RL-selected one.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train", action="store_true", help="train Problem A on train_questions.csv (rl, learning on)")
    mode.add_argument("--evaluate", action="store_true", help="evaluate all strategies on questions.csv (learning off)")
    parser.add_argument("--passes", type=int, default=1, help="training passes over train_questions.csv (--train)")
    parser.add_argument("--strategies", nargs="+", default=STRATEGIES, choices=STRATEGIES,
                        help="strategies to evaluate (--evaluate; default all four)")
    parser.add_argument("--model", default=None, help="Ollama model (default OLLAMA_MODEL from .env)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions (for a quick check)")
    args = parser.parse_args(argv)
    if args.passes < 1:
        parser.error("--passes must be at least 1")

    if args.train:
        plan = build_plan("train", args.passes, ["rl"], args.limit)
        run("train", plan, learning=True, model=args.model)
    else:
        plan = build_plan("baseline", 1, args.strategies, args.limit)
        run("baseline", plan, learning=False, model=args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
