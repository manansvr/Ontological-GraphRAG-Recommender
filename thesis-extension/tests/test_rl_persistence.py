#!/usr/bin/env python3
"""Offline tests that RL updates from different processes do not overwrite each other.

sr8-mcp, ollama-mcp and scripts/review-links.py each hold an in-memory copy of the
Q-learning agent loaded from the same JSON file. These tests reproduce the case where
one copy is stale and check that saving it no longer discards the other's update.
Everything runs against a temporary model file; .rl-model.json is never touched.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_inference_review  # noqa: E402  (provides the sr8-mcp loader)
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)

EXT_DIR = Path(__file__).resolve().parent.parent
RL_PATH = EXT_DIR / "reinforcemnt-learning.py"
ADR_ACTIONS = ["graph_first", "documents_first", "hybrid"]
INFERENCE_STATE = "inference_weak_no_high"


def _load_rl():
    spec = importlib.util.spec_from_file_location("rl_under_test", RL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # needed by its dataclasses
    spec.loader.exec_module(module)
    return module


rl = _load_rl()


def _saved_q(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))["q_table"]


class CrossProcessOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = Path(self.tmp.name) / "model.json"
        seed = rl.QLearningAgent()
        seed.q_table = {"adr_lookup": {a: 0.0 for a in ADR_ACTIONS}}
        seed.save(self.model)

        # sr8-mcp copy (fresh module instance, pointed at the temporary file)
        self.sr8 = test_inference_review._load_sr8()
        self.sr8._RL_MODEL_PATH = self.model

        # ollama-mcp copy
        self._old_env = os.environ.get("RL_MODEL_PATH")
        os.environ["RL_MODEL_PATH"] = str(self.model)
        self.ollama = test_review_access._load_ollama()

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("RL_MODEL_PATH", None)
        else:
            os.environ["RL_MODEL_PATH"] = self._old_env
        self.tmp.cleanup()

    def test_stale_ollama_copy_does_not_overwrite_review_feedback(self):
        with contextlib.redirect_stdout(io.StringIO()):
            bridge = self.ollama._RLBridge()          # loads the file now: no inference states yet
        self.assertTrue(bridge.enabled)

        self.sr8._rl_update("rejected", -1.0, state=INFERENCE_STATE)   # review feedback, saved by sr8 code
        after_review = _saved_q(self.model)[INFERENCE_STATE]["decrease_confidence"]

        with contextlib.redirect_stdout(io.StringIO()):
            bridge.update_and_save("adr_lookup", "hybrid", 1.0, "adr_lookup", ADR_ACTIONS)  # stale copy saves

        saved = _saved_q(self.model)
        self.assertIn(INFERENCE_STATE, saved, "review feedback was overwritten by the stale ollama-mcp copy")
        self.assertEqual(saved[INFERENCE_STATE]["decrease_confidence"], after_review)
        self.assertGreater(saved["adr_lookup"]["hybrid"], 0.0)

    def test_stale_sr8_copy_does_not_overwrite_retrieval_update(self):
        self.sr8._rl_update("confirmed", 1.0, state=INFERENCE_STATE)   # sr8 copy loaded and saved
        with contextlib.redirect_stdout(io.StringIO()):
            bridge = self.ollama._RLBridge()
            bridge.update_and_save("adr_lookup", "documents_first", 1.0, "adr_lookup", ADR_ACTIONS)
        retrieval = _saved_q(self.model)["adr_lookup"]["documents_first"]

        self.sr8._rl_update("rejected", -1.0, state=INFERENCE_STATE)   # sr8's copy predates that update

        saved = _saved_q(self.model)
        self.assertEqual(saved["adr_lookup"]["documents_first"], retrieval,
                         "retrieval update was overwritten by the stale sr8-mcp copy")

    def test_in_memory_copy_is_refreshed_after_each_save(self):
        with contextlib.redirect_stdout(io.StringIO()):
            bridge = self.ollama._RLBridge()
        self.sr8._rl_update("rejected", -1.0, state=INFERENCE_STATE)
        with contextlib.redirect_stdout(io.StringIO()):
            bridge.update_and_save("adr_lookup", "hybrid", 1.0, "adr_lookup", ADR_ACTIONS)
        self.assertIn(INFERENCE_STATE, bridge._agent.q_table)


class Sr8LoaderTests(unittest.TestCase):
    def test_sr8_loads_the_rl_agent(self):
        """Regression: sr8-mcp's loader used to fail silently and return None (RL disabled)."""
        with tempfile.TemporaryDirectory() as tmp:
            sr8 = test_inference_review._load_sr8()
            sr8._RL_MODEL_PATH = Path(tmp) / "model.json"
            agent = sr8._load_rl_agent()
            self.assertIsNotNone(agent)
            self.assertTrue(any(s.startswith("inference_") for s in agent.q_table))
            self.assertIn(INFERENCE_STATE, _saved_q(sr8._RL_MODEL_PATH))


class LockedUpdateTests(unittest.TestCase):
    def test_concurrent_processes_lose_no_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.json"
            worker = textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("rl", {str(RL_PATH)!r})
                rl = importlib.util.module_from_spec(spec)
                sys.modules["rl"] = rl
                spec.loader.exec_module(rl)
                def bump(agent):
                    counter = agent.q_table.setdefault("counter", {{"n": 0}})
                    counter["n"] += 1
                for _ in range(25):
                    rl.locked_update({str(model)!r}, bump)
            """)
            procs = [subprocess.Popen([sys.executable, "-c", worker]) for _ in range(4)]
            self.assertEqual([p.wait(timeout=60) for p in procs], [0, 0, 0, 0])
            self.assertEqual(_saved_q(model)["counter"]["n"], 100)

    def test_save_is_atomic_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.json"
            rl.locked_update(model, lambda agent: agent.q_table.setdefault("s", {"a": 1.0}))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["model.json", "model.json.lock"])
            self.assertEqual(_saved_q(model), {"s": {"a": 1.0}})


if __name__ == "__main__":
    unittest.main()
