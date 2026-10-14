#!/usr/bin/env python3
"""test_recommender.py — terminal test harness for the SR8 GraphRAG MCP tools.

Runs 5 pre-defined questions against the local Neo4j knowledge graph and Ollama,
printing the tools called, the final answer, and a summary at the end.

Usage:
    python3 thesis-extension/test_recommender.py
"""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# ── Load sr8-mcp module so we can call tools directly (no running MCP server needed) ──

_MCP_PATH = Path(__file__).resolve().parent / "sr8-mcp.py"

def _load_mcp_module():
    spec = importlib.util.spec_from_file_location("sr8_mcp", _MCP_PATH)
    if not spec or not spec.loader:
        sys.exit(f"ERROR: cannot load {_MCP_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

try:
    mcp = _load_mcp_module()
except Exception as exc:
    sys.exit(f"ERROR loading sr8-mcp: {exc}")


# ── Ollama helpers ─────────────────────────────────────────────────────────────

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

TOOL_DESCRIPTIONS = {
    "get_project": "Get project metadata and requirements",
    "get_adr": "Get ADR overview and summary",
    "get_assembly": "Get assembly details",
    "search_requirements": "Search requirements by keyword",
    "list_all_projects": "List all projects",
    "list_all_adrs": "List all ADRs",
    "get_compliance_gaps": "Find unverified compliance gaps",
    "get_verification_progress": "Show verification completion percentage",
    "get_highest_risk_gaps": "Top 10 highest-risk unverified requirements",
    "get_cross_assembly_requirements": "ADRs spanning multiple assemblies",
    "get_assembly_dependencies": "Assemblies coupled by shared ADRs",
    "get_shared_requirements": "Requirements shared between two projects",
    "get_interface_risk_report": "Full interface risk report",
    "get_unmitigated_failure_modes": "Failure modes without a control action, by FMEA requirement",
    "get_unassigned_requirements": "Requirements with no project assigned",
    "get_similar_assigned_requirements": "Similar requirements that have project assignments",
    "write_inferred_project_link": "Write an inferred project link",
    "get_inferred_links": "List all inferred project links",
    "get_requirements_by_keyword": "Search requirements, descriptions, and clauses",
    "get_requirement_chain": "Full chain: ADR → Clause → Requirement → Project → Assembly",
    "get_reverification_scope": "Scope of re-verification after a change",
    "write_change_impact_report": "Record a change impact report",
    "get_change_impact_reports": "List change impact reports",
    "get_adr_requirements": "Fetch requirements for a specific ADR",
    "get_feedback_stats": "Feedback statistics and RL reward summary",
}

# Map from question intent to the tools that should be called.
QUESTION_TOOL_MAP: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "What requirements apply to SRP8-048?": [
        ("get_adr", {"adr_id": "ADR-48"}),
        ("get_adr_requirements", {"adr_id": "ADR-48"}),
    ],
    "What are the compliance gaps in the Front Axle Assembly?": [
        ("get_assembly", {"assembly_id": "ASM-FRONT-AXLE"}),
        ("get_compliance_gaps", {"assembly_id": "ASM-FRONT-AXLE"}),
    ],
    "Which requirements span more than one assembly?": [
        ("get_cross_assembly_requirements", {}),
    ],
    "Are there any requirements with no project assigned?": [
        ("get_unassigned_requirements", {}),
    ],
    "What would be affected if we changed the front wheel diameter?": [
        ("get_requirements_by_keyword", {"keyword": "wheel diameter"}),
        ("get_compliance_gaps", {}),
    ],
}


def _call_tool(tool_name: str, kwargs: dict[str, Any]) -> tuple[Any, str]:
    """Call a tool function from the loaded sr8-mcp module and return (parsed_result, raw_json)."""
    fn = getattr(mcp, tool_name, None)
    if fn is None:
        return None, json.dumps({"error": f"tool '{tool_name}' not found in sr8-mcp"})
    try:
        raw = fn(**kwargs)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed, raw
    except Exception as exc:
        err = json.dumps({"error": str(exc)})
        return None, err


def _build_context(tool_results: list[tuple[str, dict, Any]]) -> str:
    """Summarise tool results into a concise context block for Ollama."""
    parts: list[str] = []
    for tool_name, kwargs, result in tool_results:
        arg_summary = ", ".join(f"{k}={v!r}" for k, v in kwargs.items()) or "(no args)"
        if isinstance(result, dict) and "error" in result:
            snippet = f"[ERROR: {result['error']}]"
        elif isinstance(result, dict):
            # Produce a compact JSON snippet (first 1200 chars).
            snippet = json.dumps(result, indent=None)[:1200]
        else:
            snippet = str(result)[:1200]
        parts.append(f"Tool: {tool_name}({arg_summary})\nResult: {snippet}")
    return "\n\n".join(parts)


def _ask_ollama(question: str, context: str) -> str:
    """Send a question + tool context to Ollama and return the assistant's answer."""
    system_prompt = (
        "You are an SR8 Formula SAE compliance assistant. "
        "Answer the user's question using only the tool results provided in the context. "
        "Be concise and precise. Use British English. "
        "If the tool results indicate an error or no data, say so explicitly."
    )
    user_message = f"Context from knowledge graph tools:\n\n{context}\n\nQuestion: {question}"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()
    except requests.exceptions.ConnectionError:
        return f"[Ollama not reachable at {OLLAMA_URL} — showing raw tool results only]"
    except Exception as exc:
        return f"[Ollama error: {exc}]"


def _separator(char: str = "─", width: int = 72) -> str:
    return char * width


def run_tests() -> None:
    questions = list(QUESTION_TOOL_MAP.keys())

    print(_separator("═"))
    print("  SR8 GraphRAG Recommender — Terminal Test Suite")
    print(f"  Ollama: {OLLAMA_URL}  model: {OLLAMA_MODEL}")
    print(f"  MCP module: {_MCP_PATH}")
    print(_separator("═"))

    all_tool_calls: list[str] = []
    answered: int = 0

    for q_idx, question in enumerate(questions, start=1):
        tool_plan = QUESTION_TOOL_MAP[question]

        print(f"\nQ{q_idx}: {question}")
        print(_separator())

        tool_results: list[tuple[str, dict, Any]] = []
        tools_called: list[str] = []

        for tool_name, kwargs in tool_plan:
            arg_repr = ", ".join(f"{k}={v!r}" for k, v in kwargs.items()) or "(no args)"
            print(f"  → calling {tool_name}({arg_repr})")
            t0 = time.monotonic()
            parsed, raw = _call_tool(tool_name, kwargs)
            elapsed = time.monotonic() - t0

            # Check for data in result.
            has_data = False
            if isinstance(parsed, dict):
                # Consider it populated if any value is non-empty/non-zero.
                for v in parsed.values():
                    if v and v != [] and v != {} and v != 0:
                        has_data = True
                        break
            status = "OK" if has_data else "EMPTY/ERROR"
            print(f"    [{status}  {elapsed:.2f}s]")

            tool_results.append((tool_name, kwargs, parsed))
            tools_called.append(tool_name)
            all_tool_calls.append(tool_name)

        context = _build_context(tool_results)
        print("\n  Asking Ollama...")
        t0 = time.monotonic()
        answer = _ask_ollama(question, context)
        elapsed = time.monotonic() - t0
        print(f"  [{elapsed:.2f}s]\n")
        print("Answer:")
        for line in answer.splitlines():
            print(f"  {line}")

        if answer and not answer.startswith("["):
            answered += 1

        print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print(_separator("═"))
    print("SUMMARY")
    print(_separator("═"))
    print(f"  Questions run       : {len(questions)}")
    print(f"  Non-empty answers   : {answered}/{len(questions)}")
    print(f"  Total tool calls    : {len(all_tool_calls)}")

    from collections import Counter
    freq = Counter(all_tool_calls)
    print("  Most frequent tools :")
    for tool, count in freq.most_common(5):
        print(f"    {count}×  {tool}")

    all_ok = answered == len(questions)
    print()
    print("  Result:", "PASS — all questions answered" if all_ok else "PARTIAL — some questions returned no answer")
    print(_separator("═"))


if __name__ == "__main__":
    run_tests()
