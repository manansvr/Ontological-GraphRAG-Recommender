#!/usr/bin/env python3
"""Offline tests for the retrieval-strategy experiment (no Ollama, MCP server or Neo4j).

Checks the question files (coverage, no repeats, valid IDs, every question takes the RL
route), the RETRIEVAL_STRATEGY and RL_LEARNING switches in ollama-mcp, and the runner's
plumbing with a fake chat client.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import csv
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)
import test_rl_persistence  # noqa: E402  (provides the RL module)

EXT_DIR = TESTS_DIR.parent
REPO = EXT_DIR.parent
EXPERIMENTS = EXT_DIR / "experiments"
ALL_ADRS = {"ADR-10", "ADR-23", "ADR-25", "ADR-31", "ADR-42", "ADR-43", "ADR-92", "ADR-95"}


def _read(name):
    with (EXPERIMENTS / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _consistent_ids():
    """Requirement IDs whose ADR-mapping.json ID equals the ID extract-ADR.py gives the node."""
    spec = importlib.util.spec_from_file_location("extract_adr_for_tests", REPO / "thesis-extraction/Scripts/extract-ADR.py")
    x = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(x)
    graph = {}
    for path in sorted((REPO / "thesis-extraction/csv").glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = x.forward_fill_adr_id([{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)])
        counter = 0
        for i, row in enumerate(rows, start=2):
            adr = x.normalise_adr_id(x.get_col(row, "adr_id"))
            clause, name, text = x.get_col(row, "clause"), x.get_col(row, "req_name"), x.get_col(row, "text")
            if not adr or (not clause and not name and not text):
                continue
            applicable, _ = x.read_applicability(row, name) if name else (True, "")
            if name and (text or not applicable):
                counter += 1
                graph[(adr, str(i))] = f"REQ-{adr.replace('ADR-', '')}-{counter:03d}"
    mapping = json.loads((EXT_DIR / "ADR-mapping.json").read_text(encoding="utf-8"))["rows"]
    return {r["requirement_id"] for r in mapping if graph.get((r["adr_id"], r["source_pointer"])) == r["requirement_id"]}


class QuestionFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation = _read("questions.csv")
        cls.training = _read("train_questions.csv")
        cls.ollama = test_review_access._load_ollama()

    def test_sizes_and_columns(self):
        self.assertEqual(len(self.evaluation), 25)
        self.assertEqual(len(self.training), 30)
        for rows in (self.evaluation, self.training):
            self.assertEqual(list(rows[0]), ["question_id", "category", "adr_ids", "question", "expected_requirement_ids"])

    def test_evaluation_covers_all_adrs_and_question_types(self):
        covered = {adr for r in self.evaluation for adr in r["adr_ids"].split(";")}
        self.assertEqual(covered, ALL_ADRS)
        self.assertEqual({r["category"] for r in self.evaluation},
                         {"requirement_count", "requirement_lookup", "verification_method", "evidence_source", "cross_adr"})

    def test_no_question_is_repeated(self):
        texts = [r["question"].strip().lower() for r in self.evaluation + self.training]
        self.assertEqual(len(texts), len(set(texts)))
        ids = [r["question_id"] for r in self.evaluation + self.training]
        self.assertEqual(len(ids), len(set(ids)))

    def test_expected_ids_are_real_and_match_the_graph(self):
        consistent = _consistent_ids()
        for row in self.evaluation + self.training:
            expected = [i for i in row["expected_requirement_ids"].split(";") if i]
            self.assertTrue(expected, row["question_id"])
            for req_id in expected:
                self.assertIn(req_id, consistent, f"{row['question_id']}: {req_id}")
                self.assertIn(req_id.split("-")[1], {a.split("-")[1] for a in row["adr_ids"].split(";")},
                              f"{row['question_id']}: {req_id} not from a listed ADR")

    def test_every_question_takes_the_rl_route(self):
        o = self.ollama
        for row in self.evaluation + self.training:
            q = row["question"]
            self.assertIsNone(o._parse_review_command(q), row["question_id"])
            self.assertFalse(o._is_count_requirements_question(q) and o._extract_rule_id_from_question(q),
                             f"{row['question_id']} would take the count route")
            self.assertFalse(o._is_reference_question(q), f"{row['question_id']} would take the reference route")
            self.assertIsNone(o._design_guidance_redirect(q), f"{row['question_id']} would take the design route")
            self.assertEqual(o._rl_state_and_actions(q)[0], "adr_lookup", row["question_id"])


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("RETRIEVAL_STRATEGY", "RL_LEARNING", "RL_MODEL_PATH")}
        self.tmp = tempfile.TemporaryDirectory()
        self.model = Path(self.tmp.name) / "model.json"
        os.environ["RL_MODEL_PATH"] = str(self.model)
        self.ollama = test_review_access._load_ollama()

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def bridge(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.ollama._RLBridge()

    def test_retrieval_strategy_values(self):
        for value, expected in [(None, None), ("rl", None), ("", None), ("hybrid", "hybrid"),
                                ("graph_first", "graph_first"), ("Documents_First", "documents_first")]:
            if value is None:
                os.environ.pop("RETRIEVAL_STRATEGY", None)
            else:
                os.environ["RETRIEVAL_STRATEGY"] = value
            self.assertEqual(self.ollama._forced_strategy(), expected, value)
        os.environ["RETRIEVAL_STRATEGY"] = "random"
        with self.assertRaises(ValueError):
            self.ollama._forced_strategy()

    def test_learning_off_uses_greedy_policy_and_saves_nothing(self):
        rl = test_rl_persistence.rl
        rl.locked_update(self.model, lambda a: a.q_table.update(
            {"adr_lookup": {"graph_first": 0.1, "documents_first": 0.9, "hybrid": 0.2}}), rl.PROBLEM_A)
        before = self.model.read_bytes()
        os.environ["RL_LEARNING"] = "false"
        bridge = self.bridge()
        actions = ["graph_first", "documents_first", "hybrid"]
        self.assertEqual({bridge.choose_action("adr_lookup", actions) for _ in range(50)}, {"documents_first"})
        self.assertFalse(bridge.update_and_save("adr_lookup", "hybrid", 1.0, "adr_lookup", actions))
        self.assertEqual(self.model.read_bytes(), before)

    def test_learning_on_updates_and_counts_updates(self):
        os.environ["RL_LEARNING"] = "true"
        bridge = self.bridge()
        actions = ["graph_first", "documents_first", "hybrid"]
        for reward in (1.0, 0.0, -0.8):
            self.assertTrue(bridge.update_and_save("adr_lookup", "hybrid", reward, "adr_lookup", actions))
        saved = json.loads(self.model.read_text())["problem_a"]
        self.assertEqual(saved["episode_rewards"], [1.0, 0.0, -0.8])

    def test_forced_strategy_only_for_adr_lookup_and_never_trains(self):
        source = (EXT_DIR / "ollama-mcp").read_text(encoding="utf-8")
        self.assertIn('forced_strategy = _forced_strategy() if rl_state == "adr_lookup" else None', source)
        self.assertIn("if _rl_learnable(rl_actions) and forced_strategy is None:", source)


class FakeClient:
    """Stands in for ollama-mcp: run_chat reads input() twice and records one turn."""

    def __init__(self, answers=None, fail=False):
        self.answers = answers or {}
        self.fail = fail
        self.seen_env = []
        self.TURN_LOG_PATH = None

    def _ollama_model(self, default=None):
        return "fake-model"

    def _finish_turn(self, turn, path=None):
        turn.pop("_started", None)

    async def run_chat(self, model, server_command, server_args):
        question = self.input("You: ")
        assert self.input("You: ") == "exit"
        if self.fail:
            raise ConnectionError("Ollama not reachable")
        strategy = os.environ["RETRIEVAL_STRATEGY"]
        learning = os.environ["RL_LEARNING"] == "true"
        self.seen_env.append((strategy, learning))
        self._finish_turn({
            "route": "rl_prefetch", "rl_state": "adr_lookup",
            "rl_action": "hybrid" if strategy == "rl" else strategy,
            "forced_strategy": None if strategy == "rl" else strategy,
            "reward_components": {"model_cited": True, "fallback_used": False, "total": 1.0},
            "evidence_appended": False, "answer": self.answers.get(question, ""),
            "tool_calls": [{"name": "get_adr_requirements", "status": "ok"}],
            "llm_calls": 1, "latency_ms": 12.5, "rl_updated": learning and strategy == "rl", "_started": 0,
        })


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("run_baseline_under_test", str(EXPERIMENTS / "run-baseline.py"))
        spec = importlib.util.spec_from_loader("run_baseline_under_test", loader)
        cls.runner = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.runner)

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("RETRIEVAL_STRATEGY", "RL_LEARNING")}

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def run_mode(self, mode, plan, learning, client):
        counter = {"n": 0}

        def status():
            counter["n"] += 1
            return {"model_file": "m.json", "updates": 10 if counter["n"] == 1 else 13,
                    "epsilon": 0.15, "adr_lookup_q": {}}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            out = self.runner.run(mode, plan, learning, None, client_factory=lambda: client,
                                  status=status, results_dir=Path(tmp))
            base = Path(out["base"])
            rows = list(csv.DictReader(open(f"{base}.csv", newline="")))
            summary = list(csv.DictReader(open(f"{base}-summary.csv", newline="")))
            files = sorted(p.name.split("-", 3)[-1] if p.name.count("-") > 2 else p.name for p in Path(tmp).iterdir())
        return out, rows, summary, base.name, files

    def test_evaluate_plan_runs_every_strategy_on_every_question(self):
        plan = self.runner.build_plan("baseline", 1, self.runner.STRATEGIES, None)
        self.assertEqual(len(plan), 4 * 25)
        self.assertEqual({s for _, s, _ in plan}, {"graph_first", "documents_first", "hybrid", "rl"})

    def test_train_plan_repeats_training_questions_with_rl(self):
        plan = self.runner.build_plan("train", 3, ["rl"], None)
        self.assertEqual(len(plan), 3 * 30)
        self.assertEqual({s for _, s, _ in plan}, {"rl"})
        self.assertEqual({p for p, _, _ in plan}, {1, 2, 3})

    def test_evaluation_rows_summary_and_switches(self):
        q = [{"question_id": "E01", "category": "requirement_count", "question": "Q1?", "expected_requirement_ids": "REQ-42-001;REQ-42-002"},
             {"question_id": "E02", "category": "requirement_lookup", "question": "Q2?", "expected_requirement_ids": "REQ-92-001"}]
        client = FakeClient(answers={"Q1?": "REQ-42-001 and req-42-002.", "Q2?": "nothing"})
        plan = [(1, s, x) for s in self.runner.STRATEGIES for x in q]
        out, rows, summary, base, _ = self.run_mode("baseline", plan, False, client)
        self.assertTrue(base.startswith("baseline-"))
        self.assertEqual(client.seen_env, [(s, False) for s in self.runner.STRATEGIES for _ in q])
        self.assertEqual(len(rows), 8)
        e01 = next(r for r in rows if r["question_id"] == "E01")
        self.assertEqual((e01["expected_ids_found"], e01["expected_ids_total"], e01["expected_ids_fraction"]), ("2", "2", "1.0"))
        per_strategy = {r["strategy"]: r for r in summary}
        self.assertEqual(set(per_strategy) - {"problem_a_updates_this_run", "problem_a_updates_total_before",
                                              "problem_a_updates_total_after"}, set(self.runner.STRATEGIES))
        self.assertEqual(per_strategy["hybrid"]["expected_ids_fraction_mean"], "0.5")
        self.assertEqual(per_strategy["problem_a_updates_this_run"]["rl_updates"], "0")
        self.assertEqual(per_strategy["problem_a_updates_total_after"]["rl_updates"], "13")

    def test_training_counts_problem_a_updates(self):
        q = {"question_id": "T01", "category": "requirement_lookup", "question": "T?", "expected_requirement_ids": "REQ-43-024"}
        client = FakeClient()
        out, rows, summary, base, _ = self.run_mode("train", [(p, "rl", q) for p in (1, 2, 3)], True, client)
        self.assertTrue(base.startswith("train-"))
        self.assertEqual(client.seen_env, [("rl", True)] * 3)
        self.assertEqual(next(r for r in summary if r["strategy"] == "problem_a_updates_this_run")["rl_updates"], "3")

    def test_stops_after_consecutive_errors(self):
        q = {"question_id": "E01", "category": "c", "question": "Q?", "expected_requirement_ids": "REQ-42-001"}
        out, rows, *_ = self.run_mode("baseline", [(1, "rl", q)] * 10, False, FakeClient(fail=True))
        self.assertEqual(len(rows), self.runner.MAX_CONSECUTIVE_ERRORS)
        self.assertTrue(all("ConnectionError" in r["error"] for r in rows))

    def test_runner_uses_the_chat_clients_own_loop(self):
        source = (EXPERIMENTS / "run-baseline.py").read_text(encoding="utf-8")
        self.assertIn("client.run_chat(", source)
        self.assertIn('EXT_DIR / "ollama-mcp"', source)


if __name__ == "__main__":
    unittest.main()
