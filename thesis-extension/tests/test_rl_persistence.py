#!/usr/bin/env python3
"""Offline tests for the RL model file: per-problem storage, migration and safe saves.

The model file (schema version 3) holds two independent agents: problem_a (retrieval
strategy, ollama-mcp) and problem_b (inference confidence, sr8-mcp). sr8-mcp, ollama-mcp
and scripts/review-links.py each keep an in-memory copy; these tests reproduce stale
copies and check that saving one never discards another process's update, that the two
problems never affect each other, and that version-2 files migrate correctly.
Everything runs against temporary files; .rl-model.json is never touched.

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


def _doc(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _q(path, problem):
    return _doc(path)[problem]["q_table"]


def _write_v2(path, q_table):
    """Write a version-2 (single shared agent) model file, the format committed before this change."""
    agent = rl.QLearningAgent()
    agent.q_table = q_table
    agent.save(path)  # QLearningAgent.save writes the version-2 single-agent format


class ProcessCopies(unittest.TestCase):
    """Fixture: a version-2 model file plus fresh sr8-mcp and ollama-mcp module copies."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = Path(self.tmp.name) / "model.json"
        _write_v2(self.model, {"adr_lookup": {a: 0.0 for a in ADR_ACTIONS}})

        self.sr8 = test_inference_review._load_sr8()
        self.sr8._RL_MODEL_PATH = self.model

        self._old_env = os.environ.get("RL_MODEL_PATH")
        os.environ["RL_MODEL_PATH"] = str(self.model)
        self.ollama = test_review_access._load_ollama()

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("RL_MODEL_PATH", None)
        else:
            os.environ["RL_MODEL_PATH"] = self._old_env
        self.tmp.cleanup()

    def bridge(self):
        with contextlib.redirect_stdout(io.StringIO()):
            bridge = self.ollama._RLBridge()
        self.assertTrue(bridge.enabled)
        return bridge

    def turn(self, bridge, action="hybrid", reward=1.0):
        with contextlib.redirect_stdout(io.StringIO()):
            bridge.update_and_save("adr_lookup", action, reward, "adr_lookup", ADR_ACTIONS)


class CrossProcessOverwriteTests(ProcessCopies):
    def test_stale_ollama_copy_does_not_overwrite_review_feedback(self):
        bridge = self.bridge()                                     # loaded before any Problem B data
        self.assertTrue(self.sr8._rl_update(-1.0, INFERENCE_STATE, "decrease_confidence"))
        after_review = _q(self.model, "problem_b")[INFERENCE_STATE]["decrease_confidence"]

        self.turn(bridge)                                          # stale copy saves

        self.assertEqual(_q(self.model, "problem_b")[INFERENCE_STATE]["decrease_confidence"], after_review)
        self.assertGreater(_q(self.model, "problem_a")["adr_lookup"]["hybrid"], 0.0)

    def test_stale_sr8_copy_does_not_overwrite_retrieval_update(self):
        self.sr8._rl_update(1.0, INFERENCE_STATE, "increase_confidence")    # sr8 copy loaded and saved
        self.turn(self.bridge(), action="documents_first")
        retrieval = _q(self.model, "problem_a")["adr_lookup"]["documents_first"]

        self.sr8._rl_update(-1.0, INFERENCE_STATE, "decrease_confidence")  # sr8's copy predates that update

        self.assertEqual(_q(self.model, "problem_a")["adr_lookup"]["documents_first"], retrieval)

    def test_in_memory_copy_is_refreshed_after_each_save(self):
        first, second = self.bridge(), self.bridge()
        self.turn(second, action="graph_first")
        self.turn(first, action="hybrid")
        self.assertGreater(first._agent.q_table["adr_lookup"]["graph_first"], 0.0)


class ProblemSeparationTests(ProcessCopies):
    def test_file_is_migrated_to_version_3_with_two_sections(self):
        self.sr8._rl_update(-1.0, INFERENCE_STATE, "decrease_confidence")
        doc = _doc(self.model)
        self.assertEqual(doc["schema_version"], 3)
        self.assertIn("adr_lookup", doc["problem_a"]["q_table"])
        self.assertNotIn("adr_lookup", doc["problem_b"]["q_table"])
        self.assertTrue(all(s.startswith("inference_") for s in doc["problem_b"]["q_table"]))

    def test_epsilon_decay_in_one_problem_does_not_affect_the_other(self):
        bridge = self.bridge()
        self.sr8._rl_update(-1.0, INFERENCE_STATE, "decrease_confidence")
        eps_a = _doc(self.model)["problem_a"]["config"]["exploration_rate"]
        for _ in range(10):
            self.sr8._rl_update(1.0, INFERENCE_STATE, "keep_confidence")
        self.assertEqual(_doc(self.model)["problem_a"]["config"]["exploration_rate"], eps_a)

        eps_b = _doc(self.model)["problem_b"]["config"]["exploration_rate"]
        for _ in range(10):
            self.turn(bridge)
        self.assertEqual(_doc(self.model)["problem_b"]["config"]["exploration_rate"], eps_b)
        self.assertLess(_doc(self.model)["problem_a"]["config"]["exploration_rate"], eps_a)

    def test_problem_b_is_single_step_and_problem_a_keeps_its_discount(self):
        self.sr8._rl_update(0.0, INFERENCE_STATE, "keep_confidence")       # load + merge priors
        q0 = _q(self.model, "problem_b")[INFERENCE_STATE]["increase_confidence"]
        self.sr8._rl_update(1.0, INFERENCE_STATE, "increase_confidence")
        q1 = _q(self.model, "problem_b")[INFERENCE_STATE]["increase_confidence"]
        self.assertAlmostEqual(q1, q0 + 0.2 * (1.0 - q0))                  # Q <- Q + alpha (r - Q)
        self.assertEqual(_doc(self.model)["problem_b"]["config"]["discount_factor"], 0.0)
        self.turn(self.bridge())
        self.assertEqual(_doc(self.model)["problem_a"]["config"]["discount_factor"], 0.9)

    def test_repeated_reward_converges_to_the_reward_not_r_over_one_minus_gamma(self):
        self.sr8._rl_update(0.0, INFERENCE_STATE, "keep_confidence")
        for _ in range(60):
            self.sr8._rl_update(1.0, INFERENCE_STATE, "increase_confidence")
        q = _q(self.model, "problem_b")[INFERENCE_STATE]["increase_confidence"]
        self.assertLessEqual(q, 1.0)
        self.assertGreater(q, 0.99)


class MigrationTests(unittest.TestCase):
    V2 = {
        "schema_version": 2,
        "config": {"learning_rate": 0.2, "discount_factor": 0.9, "exploration_rate": 0.02,
                   "min_exploration_rate": 0.02, "exploration_decay": 0.995, "optimistic_initial_q": 0.0},
        "q_table": {"adr_question": {"hybrid": 7.1}, "adr_lookup": {"hybrid": -0.25},
                    "inference_strong_yes_high": {"increase_confidence": 5.0}},
        "episode_rewards": [0.1, 0.2],
    }

    def v2(self):
        return json.loads(json.dumps(self.V2))

    def test_v2_document_splits_by_state_name(self):
        doc = rl.migrate_model_document(self.v2())
        self.assertEqual(doc["schema_version"], 3)
        self.assertEqual(set(doc["problem_a"]["q_table"]), {"adr_question", "adr_lookup"})
        self.assertEqual(set(doc["problem_b"]["q_table"]), {"inference_strong_yes_high"})
        self.assertEqual(doc["problem_a"]["config"], self.V2["config"])
        self.assertEqual(doc["problem_a"]["episode_rewards"], [0.1, 0.2])
        self.assertEqual(doc["problem_b"]["config"]["discount_factor"], 0.0)
        self.assertEqual(doc["problem_b"]["episode_rewards"], [])

    def test_version_3_is_returned_unchanged(self):
        doc = rl.migrate_model_document(self.v2())
        self.assertIs(rl.migrate_model_document(doc), doc)

    def test_load_problem_migrates_in_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(json.dumps(self.V2))
            agent = rl.load_problem(path, rl.PROBLEM_B)
            self.assertEqual(set(agent.q_table), {"inference_strong_yes_high"})
            self.assertEqual(agent.config.discount_factor, 0.0)
            self.assertEqual(_doc(path)["schema_version"], 2)

    def test_migrate_model_file_rewrites_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(json.dumps(self.V2))
            self.assertTrue(rl.migrate_model_file(path))
            self.assertEqual(_doc(path)["schema_version"], 3)
            self.assertFalse(rl.migrate_model_file(path))

    def test_unknown_problem_name_is_rejected(self):
        with self.assertRaises(ValueError):
            rl.load_problem("unused.json", "problem_c")


class InferencePriorTests(unittest.TestCase):
    def test_prior_is_single_step_deterministic_and_bounded(self):
        prior = rl.train_inference_agent()
        again = rl.train_inference_agent()
        self.assertEqual(prior.q_table, again.q_table)                      # seed 99 is fixed
        self.assertEqual(prior.config.discount_factor, 0.0)
        self.assertEqual(len(prior.episode_rewards), 1000)
        self.assertEqual(set(prior.q_table), set(rl.INFERENCE_STATES))
        for actions in prior.q_table.values():
            for q in actions.values():
                self.assertTrue(-1.0 <= q <= 1.0)                           # rewards are clipped to [-1, 1]

    def test_reward_model_is_a_named_constant(self):
        self.assertEqual(set(rl.INFERENCE_PRIOR_REWARD_MODEL), {"strong", "moderate", "weak"})
        self.assertIn("NOT learned from data", RL_PATH.read_text(encoding="utf-8"))


class Sr8LoaderTests(unittest.TestCase):
    def test_sr8_loads_the_problem_b_agent_with_priors(self):
        """Regression: sr8-mcp's loader used to fail silently and return None (RL disabled)."""
        with tempfile.TemporaryDirectory() as tmp:
            sr8 = test_inference_review._load_sr8()
            sr8._RL_MODEL_PATH = Path(tmp) / "model.json"
            agent = sr8._load_rl_agent()
            self.assertIsNotNone(agent)
            self.assertEqual(agent.config.discount_factor, 0.0)
            self.assertEqual(set(agent.q_table), set(rl.INFERENCE_STATES))
            self.assertIn(INFERENCE_STATE, _q(sr8._RL_MODEL_PATH, "problem_b"))


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
                problem = sys.argv[1]
                for _ in range(25):
                    rl.locked_update({str(model)!r}, bump, problem)
            """)
            procs = [subprocess.Popen([sys.executable, "-c", worker, p])
                     for p in ("problem_a", "problem_a", "problem_b", "problem_b")]
            self.assertEqual([p.wait(timeout=60) for p in procs], [0, 0, 0, 0])
            self.assertEqual(_q(model, "problem_a")["counter"]["n"], 50)
            self.assertEqual(_q(model, "problem_b")["counter"]["n"], 50)

    def test_save_is_atomic_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.json"
            rl.locked_update(model, lambda agent: agent.q_table.setdefault("s", {"a": 1.0}), rl.PROBLEM_A)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["model.json", "model.json.lock"])
            self.assertEqual(_q(model, "problem_a"), {"s": {"a": 1.0}})
            self.assertNotIn("problem_b", _doc(model))


if __name__ == "__main__":
    unittest.main()
