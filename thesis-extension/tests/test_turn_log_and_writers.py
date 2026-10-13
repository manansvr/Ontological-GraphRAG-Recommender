#!/usr/bin/env python3
"""Offline tests for ollama-mcp's per-turn log, RL_MODEL_PATH resolution, and two real
writers saving different problems of one model file at the same time.

No Ollama, MCP server or Neo4j is used; .rl-model.json and logs/ are never touched.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import ast
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)

EXT_DIR = TESTS_DIR.parent
OLLAMA_PATH = EXT_DIR / "ollama-mcp"


def text_result(text, is_error=False):
    return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)] if text else [], isError=is_error)


class ToolClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()

    def classify(self, text, is_error=False):
        return self.ollama._classify_tool_result(text_result(text, is_error), text)

    def test_classification(self):
        self.assertEqual(self.classify('{"count": 3, "requirements": [1, 2, 3]}'), "ok")
        self.assertEqual(self.classify('{"matches": []}'), "empty")
        self.assertEqual(self.classify('{"adr_id": "ADR-31", "count": 0}'), "empty")
        self.assertEqual(self.classify(""), "empty")
        self.assertEqual(self.classify('{"error": "Neo4j unavailable"}'), "error")
        self.assertEqual(self.classify("plain text answer"), "ok")
        self.assertEqual(self.classify('{"count": 2}', is_error=True), "error")

    def test_call_tool_logged_records_each_call_and_reraises(self):
        class FakeSession:
            async def call_tool(self, name, args):
                if name == "boom":
                    raise RuntimeError("server gone")
                return text_result('{"matches": []}' if name == "search_local_documents" else '{"count": 1, "rows": [1]}')

        turn = self.ollama._new_turn("s1", "llama3.1:8b", "q")
        asyncio.run(self.ollama._call_tool_logged(FakeSession(), turn, "get_adr_requirements", {"adr_id": "ADR-31"}))
        asyncio.run(self.ollama._call_tool_logged(FakeSession(), turn, "search_local_documents", {"query": "x"}))
        with self.assertRaises(RuntimeError):
            asyncio.run(self.ollama._call_tool_logged(FakeSession(), turn, "boom", {}))
        self.assertEqual([(c["name"], c["status"]) for c in turn["tool_calls"]],
                         [("get_adr_requirements", "ok"), ("search_local_documents", "empty"), ("boom", "error")])
        self.assertEqual(turn["tool_calls"][0]["args"], {"adr_id": "ADR-31"})
        self.assertIn("server gone", turn["tool_calls"][2]["error"])
        self.assertTrue(all(isinstance(c["duration_ms"], float) for c in turn["tool_calls"]))


class TurnLogTests(unittest.TestCase):
    FIELDS = {"timestamp", "session_id", "question", "route", "rl_state", "rl_action", "forced_strategy",
              "model", "tool_calls", "reward_components", "evidence_appended", "answer", "latency_ms", "llm_calls"}

    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()
        cls.tree = ast.parse(OLLAMA_PATH.read_text(encoding="utf-8"))
        cls.run_chat = next(n for n in ast.walk(cls.tree)
                            if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_chat")

    def test_finished_turn_is_one_json_line_with_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "turns.jsonl"
            for question in ("first", "second"):
                turn = self.ollama._new_turn("abc", "llama3.1:8b", question)
                turn.update(route="rl_prefetch", rl_state="adr_lookup", rl_action="hybrid", answer="A", llm_calls=1,
                            reward_components={"total": 1.0})
                self.ollama._finish_turn(turn, path)
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(set(lines[0]), self.FIELDS)
        self.assertEqual([l["question"] for l in lines], ["first", "second"])
        self.assertIsNone(lines[0]["forced_strategy"])
        self.assertGreaterEqual(lines[0]["latency_ms"], 0.0)

    def test_default_log_path_is_in_the_extension_folder(self):
        self.assertEqual(self.ollama.TURN_LOG_PATH, EXT_DIR / "logs" / "turns.jsonl")

    def test_every_tool_call_in_the_chat_loop_is_logged(self):
        direct = [n for n in ast.walk(self.run_chat) if isinstance(n, ast.Attribute) and n.attr == "call_tool"]
        logged = [n for n in ast.walk(self.run_chat)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_call_tool_logged"]
        self.assertEqual(direct, [])
        self.assertEqual(len(logged), 8)

    def test_turn_is_written_in_a_finally_block(self):
        finals = [n for n in ast.walk(self.run_chat) if isinstance(n, ast.Try) and n.finalbody]
        writes = [f for f in finals if any(isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_finish_turn"
                                           for c in ast.walk(ast.Module(body=f.finalbody, type_ignores=[])))]
        self.assertEqual(len(writes), 1)

    def test_every_model_call_is_counted(self):
        source = OLLAMA_PATH.read_text(encoding="utf-8")
        chat = source[source.index("async def run_chat"):]
        self.assertEqual(chat.count("_post_chat(model=model"), chat.count('turn["llm_calls"] += 1'))


class ModelPathTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("RL_MODEL_PATH")
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("RL_MODEL_PATH", None)
        else:
            os.environ["RL_MODEL_PATH"] = self._env

    def test_relative_path_resolves_to_extension_folder_not_cwd(self):
        ollama = test_review_access._load_ollama()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            os.environ.pop("RL_MODEL_PATH", None)
            self.assertEqual(Path(ollama._rl_model_path()), EXT_DIR / ".rl-model.json")
            os.environ["RL_MODEL_PATH"] = "models/other.json"
            self.assertEqual(Path(ollama._rl_model_path()), EXT_DIR / "models" / "other.json")
            os.environ["RL_MODEL_PATH"] = str(Path(tmp) / "abs.json")
            self.assertEqual(Path(ollama._rl_model_path()), Path(tmp) / "abs.json")

    def test_default_matches_the_file_sr8_mcp_uses(self):
        ollama = test_review_access._load_ollama()
        os.environ.pop("RL_MODEL_PATH", None)
        sr8_default = (EXT_DIR / ".rl-model.json")  # sr8-mcp: Path(__file__).parent / ".rl-model.json"
        self.assertEqual(Path(ollama._rl_model_path()), sr8_default)
        self.assertIn('_RL_MODEL_PATH = Path(__file__).resolve().parent / ".rl-model.json"',
                      (EXT_DIR / "sr8-mcp").read_text(encoding="utf-8"))


class TwoRealWritersTests(unittest.TestCase):
    """ollama-mcp's RL bridge (problem_a) and sr8-mcp's _rl_update (problem_b) save the
    same file concurrently from separate processes; every update of both must survive."""

    UPDATES = 60

    def test_concurrent_writers_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.json"
            start = Path(tmp) / "go"
            # Each writer loads first (sr8-mcp also merges its prior), then waits for the
            # start file so the timed updates of both processes really overlap.
            common = textwrap.dedent(f"""
                import contextlib, io, os, sys, time
                from pathlib import Path
                sys.path.insert(0, {str(TESTS_DIR)!r})
                os.environ["RL_MODEL_PATH"] = {str(model)!r}
                def wait_for_start():
                    while not Path({str(start)!r}).exists():
                        time.sleep(0.002)
            """)
            ollama_writer = common + textwrap.dedent(f"""
                import test_review_access
                ollama = test_review_access._load_ollama()
                with contextlib.redirect_stdout(io.StringIO()):
                    bridge = ollama._RLBridge()
                    wait_for_start()
                    for _ in range({self.UPDATES}):
                        bridge.update_and_save("adr_lookup", "hybrid", 1.0, "adr_lookup",
                                               ["graph_first", "documents_first", "hybrid"])
            """)
            sr8_writer = common + textwrap.dedent(f"""
                import test_inference_review
                sr8 = test_inference_review._load_sr8()
                sr8._RL_MODEL_PATH = Path({str(model)!r})
                assert sr8._load_rl_agent() is not None
                wait_for_start()
                for _ in range({self.UPDATES}):
                    assert sr8._rl_update(1.0, "inference_weak_no_mid", "keep_confidence")
            """)
            procs = [subprocess.Popen([sys.executable, "-c", code], stderr=subprocess.PIPE)
                     for code in (ollama_writer, sr8_writer)]
            import time
            time.sleep(3)  # let both finish loading before releasing them together
            start.touch()
            results = [(p.wait(timeout=120), p.stderr.read().decode()) for p in procs]
            for code, err in results:
                self.assertEqual(code, 0, err[-2000:])
            doc = json.loads(model.read_text(encoding="utf-8"))

        def decayed(n):
            eps = 0.15
            for _ in range(n):
                eps = max(0.02, eps * 0.995)
            return eps

        # Each update decays its own problem's epsilon once, so an overwritten update would show up here.
        self.assertEqual(doc["problem_a"]["config"]["exploration_rate"], decayed(self.UPDATES))
        self.assertEqual(doc["problem_b"]["config"]["exploration_rate"], decayed(self.UPDATES))
        self.assertGreater(doc["problem_a"]["q_table"]["adr_lookup"]["hybrid"], 0.0)
        self.assertIn("inference_weak_no_mid", doc["problem_b"]["q_table"])
        self.assertEqual(doc["problem_b"]["config"]["discount_factor"], 0.0)
        self.assertEqual(doc["problem_a"]["config"]["discount_factor"], 0.9)


if __name__ == "__main__":
    unittest.main()
