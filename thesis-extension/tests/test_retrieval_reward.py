#!/usr/bin/env python3
"""Offline tests for retrieval-strategy learning (Problem A) in ollama-mcp.

Checks that the reward is computed from the model's own answer (before the client
appends evidence or substitutes the fallback), that single-action states are not
updated, and that the synthetic Problem A prior is gone. No Ollama, MCP or Neo4j is used.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import ast
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)
import test_rl_persistence  # noqa: E402  (provides the RL module)

EXT_DIR = Path(__file__).resolve().parent.parent
OLLAMA_PATH = EXT_DIR / "ollama-mcp"
CITED = "Brake pedal force is limited. /docs/ADR31-Requirements.csv | row 12"
UNCITED = "Brake pedal force is limited."
EVIDENCE = ["/docs/ADR31-Requirements.csv | row 12"]


class RewardComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()

    def reward(self, raw, tool_used=True, evidence=EVIDENCE, substituted=False):
        return self.ollama._rl_reward(raw, tool_used, evidence, substituted)

    def test_model_cited_scores_full_reward(self):
        self.assertEqual(self.reward(CITED), {"tool_used": True, "model_cited": True, "evidence_available": True,
                                              "fallback_used": False, "total": 1.0})

    def test_client_appended_evidence_is_not_rewarded_as_a_citation(self):
        # Previously +1.0 because evidence_refs counted; now the model did not cite, so 0.2 - 0.2.
        out = self.reward(UNCITED)
        self.assertFalse(out["model_cited"])
        self.assertTrue(out["evidence_available"])
        self.assertEqual(out["total"], 0.0)

    def test_substituted_fallback_replaces_everything(self):
        out = self.reward(CITED, substituted=True)
        self.assertTrue(out["fallback_used"])
        self.assertEqual(out["total"], -0.8)

    def test_model_written_fallback_counts_as_fallback(self):
        out = self.reward(self.ollama.FALLBACK_ANSWER, evidence=[])
        self.assertTrue(out["fallback_used"])
        self.assertEqual(out["total"], -0.8)

    def test_no_tool_used_but_cited(self):
        self.assertEqual(self.reward(CITED, tool_used=False, evidence=[])["total"], 0.8)

    def test_no_tool_no_citation(self):
        self.assertEqual(self.reward(UNCITED, tool_used=False, evidence=[])["total"], -0.2)

    def test_components_are_json_serialisable(self):
        json.dumps(self.reward(CITED))


class TurnHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()
        cls.tree = ast.parse(OLLAMA_PATH.read_text(encoding="utf-8"))
        cls.run_chat = next(n for n in ast.walk(cls.tree)
                            if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_chat")

    def test_single_action_states_are_not_learnable(self):
        self.assertFalse(self.ollama._rl_learnable(["documents_first"]))
        self.assertTrue(self.ollama._rl_learnable(["graph_first", "documents_first", "hybrid"]))
        state, actions = self.ollama._rl_state_and_actions("What does the manual say about welding?")
        self.assertEqual(state, "general_lookup")
        self.assertFalse(self.ollama._rl_learnable(actions))

    def test_update_is_guarded_by_rl_learnable(self):
        guarded = []
        for node in ast.walk(self.run_chat):
            if isinstance(node, ast.If) and any(
                    isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_rl_learnable"
                    for c in ast.walk(node.test)):
                guarded += [n for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr == "update_and_save"]
        all_updates = [n for n in ast.walk(self.run_chat) if isinstance(n, ast.Attribute) and n.attr == "update_and_save"]
        self.assertEqual(len(all_updates), 1)
        self.assertEqual(len(guarded), 1)

    def test_reward_is_computed_from_the_raw_answer(self):
        calls = [n for n in ast.walk(self.run_chat)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_rl_reward"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0].id, "raw_content")


class NoSyntheticPriorTests(unittest.TestCase):
    def test_synthetic_retrieval_environment_is_gone(self):
        rl = test_rl_persistence.rl
        for name in ("RetrievalBanditEnvironment", "train_agent", "evaluate_policy", "run_demo"):
            self.assertFalse(hasattr(rl, name), name)

    def test_saved_model_has_no_adr_question_in_problem_a(self):
        doc = json.loads((EXT_DIR / ".rl-model.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 3)
        self.assertNotIn("adr_question", doc["problem_a"]["q_table"])
        self.assertIn("adr_lookup", doc["problem_a"]["q_table"])


if __name__ == "__main__":
    unittest.main()
