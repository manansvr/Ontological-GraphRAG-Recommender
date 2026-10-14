#!/usr/bin/env python3
"""Offline tests that only people can review inferred links.

Checks that the review and feedback functions are not registered as MCP tools, that
ollama-mcp's typed review commands parse correctly and are only reachable from typed
input, and that scripts/review-links.py calls the right functions. No Neo4j server,
MCP runtime, Ollama or RL model is used.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import __future__
import ast
import contextlib
import io
import importlib.machinery
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parent.parent
SR8_PATH = EXT_DIR / "sr8-mcp"
OLLAMA_PATH = EXT_DIR / "ollama-mcp"
REVIEW_CLI_PATH = EXT_DIR / "scripts" / "review-links.py"

EXPECTED_TOOLS = {
    # Document tools
    "list_documents", "run_extraction_for_requirements", "search_local_documents",
    "suggest_requirement_sources", "read_document", "query_knowledge_graph",
    "get_adr_requirements", "adr_mapping_stats", "summarize_document", "extraction_report",
    "search_keywords", "search_braking", "search_tyre", "search_manufacturing",
    # Phase 1: GraphRAG
    "get_project", "get_adr", "get_assembly", "search_requirements", "list_all_projects", "list_all_adrs",
    # Phase 2: compliance gaps
    "get_compliance_gaps", "get_verification_progress", "get_highest_risk_gaps",
    # Phase 3: interface risk
    "get_cross_assembly_requirements", "get_assembly_dependencies", "get_shared_requirements",
    "get_interface_risk_report",
    # FMEA coverage
    "get_unmitigated_failure_modes",
    # Phase 4: inference (suggest and inspect only)
    "get_unassigned_requirements", "get_similar_assigned_requirements", "write_inferred_project_link",
    "get_inferred_links",
    # Phase 5: change impact
    "get_requirements_by_keyword", "get_requirement_chain", "get_reverification_scope",
    "write_change_impact_report", "get_change_impact_reports",
    # Phase 6/7: RL read-only
    "get_feedback_stats", "get_rl_policy",
}
HUMAN_ONLY = {"promote_inferred_link", "modify_inferred_link", "reject_inferred_link",
              "record_feedback", "_record_feedback_internal"}


def _exec_with_lazy_annotations(path: Path, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = str(path)
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec",
                   flags=__future__.annotations.compiler_flag, dont_inherit=True)
    exec(code, module.__dict__)
    return module


def _registered_sr8_tools() -> list:
    """Load sr8-mcp with a FastMCP stand-in that records every @mcp.tool() registration."""
    registered = []

    class RecordingFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def register(fn):
                registered.append(fn.__name__)
                return fn
            return register

        def run(self, *args, **kwargs):
            pass

    fastmcp = types.ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = RecordingFastMCP
    stubs = {"mcp": types.ModuleType("mcp"), "mcp.server": types.ModuleType("mcp.server"),
             "mcp.server.fastmcp": fastmcp}
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        _exec_with_lazy_annotations(SR8_PATH, "sr8_registration_check")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return registered


def _load_ollama() -> types.ModuleType:
    """Load ollama-mcp with stand-ins for the MCP client and requests (nothing is contacted)."""
    mcp_mod = types.ModuleType("mcp")
    mcp_mod.ClientSession = object
    mcp_mod.StdioServerParameters = object
    stdio = types.ModuleType("mcp.client.stdio")
    stdio.stdio_client = None
    stubs = {"mcp": mcp_mod, "mcp.client": types.ModuleType("mcp.client"), "mcp.client.stdio": stdio,
             "requests": types.ModuleType("requests")}
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        return _exec_with_lazy_annotations(OLLAMA_PATH, "ollama_mcp_under_test")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _load_review_cli() -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader("review_links_under_test", str(REVIEW_CLI_PATH))
    spec = importlib.util.spec_from_loader("review_links_under_test", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ── MCP tool surface ─────────────────────────────────────────────────────────

class ToolSurfaceTests(unittest.TestCase):
    def test_review_and_feedback_functions_are_not_mcp_tools(self):
        registered = set(_registered_sr8_tools())
        self.assertEqual(registered & HUMAN_ONLY, set())

    def test_exact_tool_list(self):
        registered = _registered_sr8_tools()
        self.assertEqual(len(registered), len(set(registered)), "a tool is registered twice")
        self.assertEqual(set(registered), EXPECTED_TOOLS)
        self.assertEqual(len(registered), 39)


# ── ollama-mcp typed review commands ─────────────────────────────────────────

class OllamaReviewCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = _load_ollama()

    def test_parse_confirm(self):
        self.assertEqual(self.ollama._parse_review_command("confirm link REQ-45-003 -> SRP8-045"),
                         {"kind": "confirm", "requirement_id": "REQ-45-003", "project_id": "SRP8-045"})
        self.assertEqual(self.ollama._parse_review_command("  Confirm Link REQ-1->SRP8-046  ")["kind"], "confirm")

    def test_parse_reject_keeps_full_reason(self):
        cmd = self.ollama._parse_review_command("reject link REQ-31-010 -> SRP8-046 because it is a front-axle brake rule")
        self.assertEqual(cmd, {"kind": "reject", "requirement_id": "REQ-31-010", "project_id": "SRP8-046",
                               "reason": "it is a front-axle brake rule"})

    def test_malformed_review_commands_give_usage_not_model(self):
        for text in ["confirm link REQ-1", "reject link REQ-1 -> SRP8-045", "reject link REQ-1 -> SRP8-045 because   ",
                     "confirm link"]:
            self.assertEqual(self.ollama._parse_review_command(text), {"kind": "usage"}, text)

    def test_ordinary_questions_are_not_review_commands(self):
        for text in ["What does ADR-31 require?", "please confirm the link between ADR-31 and brakes",
                     "how many requirements does ADR 31 have", "rejection criteria for ADR-25"]:
            self.assertIsNone(self.ollama._parse_review_command(text), text)

    def test_run_review_command_calls_internal_functions_with_reviewer(self):
        calls = []

        class FakeSr8:
            def promote_inferred_link(self, req, proj, reviewer):
                calls.append(("promote", req, proj, reviewer))
                return json.dumps({"status": "promoted", "req_id": req, "project_id": proj,
                                   "already_assigned": False, "feedback": {"reward_applied": 1.0}})

            def reject_inferred_link(self, req, proj, reviewer, reason):
                calls.append(("reject", req, proj, reviewer, reason))
                return json.dumps({"error": "already reviewed",
                                   "previous_decision": {"status": "rejected", "reviewed_by": "bob"}})

        self.ollama._review_module = FakeSr8()
        try:
            ok = self.ollama._run_review_command(
                {"kind": "confirm", "requirement_id": "REQ-1", "project_id": "SRP8-045"}, "alice")
            refused = self.ollama._run_review_command(
                {"kind": "reject", "requirement_id": "REQ-1", "project_id": "SRP8-045", "reason": "wrong"}, "alice")
        finally:
            self.ollama._review_module = None
        self.assertEqual(calls, [("promote", "REQ-1", "SRP8-045", "alice"),
                                 ("reject", "REQ-1", "SRP8-045", "alice", "wrong")])
        self.assertIn("Promoted REQ-1 -> SRP8-045 as alice", ok)
        self.assertIn("Earlier decision", refused)

    def test_review_functions_only_reachable_from_typed_input(self):
        """promote/reject are referenced only in _run_review_command, which only the review route's
        handler calls, and run_chat matches routes only against what the user typed."""
        tree = ast.parse(OLLAMA_PATH.read_text(encoding="utf-8"))
        referencing, callers_of_run_review, route_args = set(), set(), []
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Attribute) and node.attr in HUMAN_ONLY:
                        referencing.add(fn.name)
                    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_run_review_command":
                        callers_of_run_review.add(fn.name)
                    if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_match_route"
                            and fn.name == "run_chat"):
                        route_args.append(node.args[0].id)
        self.assertEqual(referencing, {"_run_review_command"})
        self.assertEqual(callers_of_run_review, {"_handle_review"})
        self.assertEqual(route_args, ["user_input"])


# ── scripts/review-links.py ──────────────────────────────────────────────────

class ReviewCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = _load_review_cli()

    def fake_sr8(self, links):
        calls = []

        class FakeSr8:
            def get_inferred_links(self):
                return json.dumps({"inferred_link_count": len(links), "inferred_links": links})

            def promote_inferred_link(self, req, proj, reviewer):
                calls.append(("promote", req, proj, reviewer))
                return json.dumps({"status": "promoted", "feedback": {"reward_applied": 1.0}})

            def modify_inferred_link(self, req, proj, new_proj, reviewer, reason):
                calls.append(("modify", req, proj, new_proj, reviewer, reason))
                return json.dumps({"status": "modified", "feedback": {"reward_applied": 0.5}})

            def reject_inferred_link(self, req, proj, reviewer, reason):
                calls.append(("reject", req, proj, reviewer, reason))
                return json.dumps({"status": "rejected", "feedback": {"reward_applied": -1.0}})

        return FakeSr8(), calls

    def run_cli(self, sr8, answers, argv=("--reviewer", "Jane Smith")):
        answers = list(answers)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.cli.main(list(argv), sr8=sr8, ask=lambda prompt: answers.pop(0))

    def test_each_decision_calls_the_matching_function_with_reviewer(self):
        links = [{"req_id": f"REQ-{i}", "project_id": "SRP8-045", "confidence": 0.7} for i in range(1, 5)]
        sr8, calls = self.fake_sr8(links)
        code = self.run_cli(sr8, [
            "r", "", "r", "wrong subsystem",      # reject: blank reason goes back, then a real reason
            "m", "SRP8-046", "rear axle",         # modify to another project
            "x", "c",                             # invalid answer, then confirm
            "s",                                  # skip
        ])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [
            ("reject", "REQ-1", "SRP8-045", "Jane Smith", "wrong subsystem"),
            ("modify", "REQ-2", "SRP8-045", "SRP8-046", "Jane Smith", "rear axle"),
            ("promote", "REQ-3", "SRP8-045", "Jane Smith"),
        ])

    def test_quit_stops_without_further_calls(self):
        sr8, calls = self.fake_sr8([{"req_id": "REQ-1", "project_id": "SRP8-045"},
                                    {"req_id": "REQ-2", "project_id": "SRP8-045"}])
        self.run_cli(sr8, ["q"])
        self.assertEqual(calls, [])

    def test_reviewer_is_required_and_non_empty(self):
        sr8, _ = self.fake_sr8([])
        with self.assertRaises(SystemExit):
            self.run_cli(sr8, [], argv=())
        with self.assertRaises(SystemExit):
            self.run_cli(sr8, [], argv=("--reviewer", "   "))


if __name__ == "__main__":
    unittest.main()
