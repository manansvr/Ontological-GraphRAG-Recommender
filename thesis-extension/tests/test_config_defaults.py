#!/usr/bin/env python3
"""Offline tests for the paper configuration: code defaults, .env.example, the design and
manufacturing redirect links, and graph-only answers under REQUIRE_EXPLICIT_CITATIONS.

The chat test drives ollama-mcp's run_chat with a fake MCP session and a fake model: the
model calls a graph-only tool (list_all_projects or get_rl_policy), then answers without
a file citation. No Neo4j, Ollama or MCP server is used.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import asyncio
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from dotenv import dotenv_values

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)

EXT_DIR = TESTS_DIR.parent
REPO = EXT_DIR.parent
POLICY_VARS = ("OLLAMA_MODEL", "STRICT_CONTEXT_ONLY", "REQUIRE_EXPLICIT_CITATIONS", "RL_ENABLED",
               "RL_LEARNING", "RETRIEVAL_STRATEGY", "RL_MODEL_PATH", "DOC_ROOTS")


def _clean_env(**values):
    """Environment without the policy variables (so code defaults apply), plus values."""
    env = {k: v for k, v in os.environ.items() if k not in POLICY_VARS}
    env.update(values)
    return mock.patch.dict(os.environ, env, clear=True)


class DefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()

    def test_code_defaults(self):
        with _clean_env():
            self.assertEqual(self.ollama._ollama_model(), "qwen2.5:14b-instruct")
            self.assertTrue(self.ollama._strict_context_only())
            self.assertFalse(self.ollama._require_explicit_citations())
            self.assertTrue(self.ollama._rl_enabled())
            self.assertTrue(self.ollama._rl_learning())
            self.assertIsNone(self.ollama._forced_strategy())   # rl
            self.assertEqual(self.ollama._rl_model_path(), str(EXT_DIR / ".rl-model.json"))
        self.assertIn('os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")',
                      (EXT_DIR / "test_recommender.py").read_text(encoding="utf-8"))

    def test_env_example_matches_the_defaults_and_has_no_real_password(self):
        values = dotenv_values(EXT_DIR / ".env.example")
        self.assertEqual({k: values[k] for k in POLICY_VARS[:-1]}, {
            "OLLAMA_MODEL": "qwen2.5:14b-instruct", "STRICT_CONTEXT_ONLY": "true",
            "REQUIRE_EXPLICIT_CITATIONS": "false", "RL_ENABLED": "true", "RL_LEARNING": "true",
            "RETRIEVAL_STRATEGY": "rl", "RL_MODEL_PATH": ".rl-model.json"})
        self.assertEqual(values["NEO4J_PASSWORD"], "replace-with-your-neo4j-password")
        text = (EXT_DIR / ".env.example").read_text(encoding="utf-8")
        for name in POLICY_VARS[3:7]:   # each RL variable carries a one-line comment
            line = next(l for l in text.splitlines() if l.startswith(name + "="))
            self.assertIn("#", line, name)

    def test_env_is_not_tracked_and_ignored(self):
        gitignore = (REPO / ".gitignore").read_text(encoding="utf-8").split()
        for pattern in (".env", "logs/", ".rl-model.json.lock", "thesis-extension/experiments/results/",
                        ".rl-model.backup-*.json"):
            self.assertIn(pattern, gitignore)


class RedirectLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()

    def test_no_hard_coded_user_paths(self):
        self.assertNotIn("/Users/", (EXT_DIR / "ollama-mcp").read_text(encoding="utf-8"))

    def test_default_is_the_repository_design_documentation(self):
        with _clean_env():
            manufacturing = self.ollama._design_guidance_redirect("manufacturing checklist")["redirect"]
            design = self.ollama._design_guidance_redirect("conceptual design review")["redirect"]
        folder = (REPO / "thesis-extraction" / "Design-Documentation").as_posix().replace(" ", "%20")
        self.assertIn(f"({folder}/Manufacturing%20Section.pdf#L1)", manufacturing)
        self.assertIn(f"({folder}/Design%20Manual.pdf#L111)", design)
        self.assertTrue((REPO / "thesis-extraction/Design-Documentation/Design Manual.pdf").is_file())

    def test_doc_roots_entry_holding_the_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp, "docs", "Design-Documentation")
            nested.mkdir(parents=True)
            (nested / "Design Manual.pdf").write_bytes(b"%PDF")
            with _clean_env(DOC_ROOTS=f"/nonexistent, {Path(tmp, 'docs')}"):
                design = self.ollama._design_guidance_redirect("prototype")["redirect"]
                manufacturing = self.ollama._design_guidance_redirect("fabrication")["redirect"]
        self.assertIn(f"({(nested / 'Design Manual.pdf').resolve().as_posix().replace(' ', '%20')}#L111)", design)
        self.assertIn("thesis-extraction/Design-Documentation/Manufacturing%20Section.pdf#L1", manufacturing)


class FakeResult:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(text=text)]
        self.isError = False


class FakeSession:
    TOOLS = [types.SimpleNamespace(name=n, description=n, inputSchema={})
             for n in ("list_all_projects", "get_rl_policy", "search_local_documents")]
    OUTPUT = {
        "list_all_projects": '{"projects": [{"projectID": "SRP8-045", "hasName": "Front Axle"}]}',
        "get_rl_policy": '{"problem_a": {"adr_lookup": {"graph_first": 0.4}}}',
    }

    def __init__(self, reader, writer):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        pass

    async def list_tools(self):
        return types.SimpleNamespace(tools=self.TOOLS)

    async def call_tool(self, name, args):
        self.calls.append(name)
        return FakeResult(self.OUTPUT[name])


@contextlib.asynccontextmanager
async def fake_stdio_client(params):
    yield (None, None)


class GraphOnlyAnswerTests(unittest.TestCase):
    """A question that matches no route, whose answer comes from a graph-only tool."""

    QUESTIONS = {   # no fixed-route trigger, no ADR ID -> rl_prefetch route, model calls the tool
        "list_all_projects": ("Which projects exist in the knowledge graph?",
                              "There is one project: SRP8-045 (Front Axle)."),
        "get_rl_policy": ("What has the retrieval agent learned so far?",
                          "For adr_lookup the agent currently prefers graph_first (Q = 0.4)."),
    }

    def chat(self, tool, require_citations):
        ollama = test_review_access._load_ollama()
        question, answer = self.QUESTIONS[tool]
        route, _ = ollama._match_route(question)
        self.assertIsNone(route, question)
        replies = iter([
            {"message": {"content": "", "tool_calls": [{"function": {"name": tool, "arguments": {}}}]}},
            {"message": {"content": answer}},
        ])
        inputs = iter([question, "exit"])
        ollama.stdio_client = fake_stdio_client
        ollama.ClientSession = FakeSession
        ollama.StdioServerParameters = lambda **kw: kw
        ollama._post_chat = lambda **kw: next(replies)
        ollama.input = lambda prompt="": next(inputs)
        with tempfile.TemporaryDirectory() as tmp:
            ollama.TURN_LOG_PATH = Path(tmp) / "turns.jsonl"
            env = {"RL_ENABLED": "false"}
            if require_citations is not None:
                env["REQUIRE_EXPLICIT_CITATIONS"] = require_citations
            with _clean_env(**env), contextlib.redirect_stdout(io.StringIO()) as out:
                asyncio.run(ollama.run_chat("fake-model", "python3", ["sr8-mcp"]))
            log = ollama.TURN_LOG_PATH.read_text(encoding="utf-8")
        printed = out.getvalue()
        self.assertIn(f"[tool] {tool}({{}})", printed)
        return printed.split("Assistant: ")[-1].strip(), answer, log

    def test_answer_is_kept_by_default_and_with_false(self):
        for tool in self.QUESTIONS:
            for setting in (None, "false"):
                delivered, answer, log = self.chat(tool, setting)
                self.assertEqual(delivered, answer, (tool, setting))
                self.assertNotIn(self.fallback(), delivered)
                self.assertIn('"fallback_used": false', log)

    def test_true_replaces_the_answer_with_the_fallback(self):
        for tool in self.QUESTIONS:
            delivered, _, log = self.chat(tool, "true")
            self.assertEqual(delivered, self.fallback(), tool)
            self.assertIn('"fallback_used": true', log)

    @staticmethod
    def fallback():
        return "I do not have enough context in the indexed sources to answer that."


if __name__ == "__main__":
    unittest.main()
