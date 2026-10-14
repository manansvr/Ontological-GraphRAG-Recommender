#!/usr/bin/env python3
"""Offline tests for ollama-mcp's deterministic routing table (no Neo4j, Ollama or MCP server).

Feeds one example phrase per route into the matcher, checks first-match order and the data
each matcher extracts, runs the tool-route handlers against a fake MCP session to confirm
they print the raw tool output without calling the model, and checks that every example
prompt in testing_rl_steps.md takes the intended route.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import asyncio
import contextlib
import io
import re
import sys
import types
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import test_review_access  # noqa: E402  (provides the ollama-mcp loader)

EXT_DIR = TESTS_DIR.parent

EXAMPLES = {
    "exit": "exit",
    "review_confirm": "confirm link REQ-45-003 -> SRP8-045",
    "review_reject": "reject link REQ-31-010 -> SRP8-046 because it is a front-axle rule",
    "review_usage": "reject link REQ-31-010 -> SRP8-046",
    "cypher_query": "Run this Cypher query: MATCH (r:Requirement) RETURN r.hasID LIMIT 5",
    "suggest_link": "Suggest that requirement REQ-43-001 belongs to project SRP8-049 with confidence 0.65, "
                    "because it shares the same ADR source",
    "rl_policy": "Show me the current RL policy.",
    "unassigned_requirements": "Show me the unassigned requirements.",
    "list_all_projects": "List all projects.",
    "inferred_links": "Show me all inferred links.",
    "count_requirements": "How many requirements does ADR 31 have?",
    "reference": "Show the reference documents for ADR 25",
    "manufacturing_redirect": "What should the manufacturing checklist include?",
    "design_guidance": "What are the stages of the conceptual design review?",
}
TOOL_ROUTES = {  # route -> (tool called, expected arguments)
    "rl_policy": ("get_rl_policy", {}),
    "unassigned_requirements": ("get_unassigned_requirements", {}),
    "list_all_projects": ("list_all_projects", {}),
    "inferred_links": ("get_inferred_links", {}),
    "cypher_query": ("query_knowledge_graph", {"cypher": "MATCH (r:Requirement) RETURN r.hasID LIMIT 5"}),
    "suggest_link": ("write_inferred_project_link", {"requirement_id": "REQ-43-001", "project_id": "SRP8-049",
                                                     "confidence": 0.65, "reasoning": "it shares the same ADR source"}),
}


class RouteTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()
        cls.routes = {r.name: r for r in cls.ollama.ROUTES}

    def test_one_example_per_route_selects_that_route(self):
        self.assertEqual(set(EXAMPLES), set(self.routes))
        for expected, phrase in EXAMPLES.items():
            route, _ = self.ollama._match_route(phrase)
            self.assertIsNotNone(route, phrase)
            self.assertEqual(route.name, expected, phrase)

    def test_alternative_trigger_phrasings(self):
        for phrase, expected in [
            ("What are the Q-values for each inference state?", "rl_policy"),
            ("cypher query: MATCH (p:Project) RETURN p.projectID", "cypher_query"),
            ("Are there unassigned requirement nodes left?", "unassigned_requirements"),
            ("Which inferred project links are recommended?", "inferred_links"),
            ("suggest that requirement REQ-1 belongs to project SRP8-045 with confidence .9 because x", "suggest_link"),
            ("quit", "exit"),
            ("/exit", "exit"),
        ]:
            route, _ = self.ollama._match_route(phrase)
            self.assertEqual(route.name if route else None, expected, phrase)

    def test_unmatched_questions_fall_through_to_rl(self):
        for phrase in ["What does ADR 31 require about brake linings?",
                       "Which projects carry the ADR 43 height requirement?",
                       "Please reject the suggestion that REQ-1 belongs to SRP8-045."]:
            self.assertEqual(self.ollama._match_route(phrase), (None, None), phrase)

    def test_assembly_questions_take_the_default_rl_route(self):
        # The model can then call get_assembly; "assembly"/"build" are not redirect keywords.
        for phrase in ["What requirements does the Front Axle assembly have?",
                       "What are the compliance gaps in the Front Axle Assembly?",
                       "Which projects build up the Rear Axle assembly?"]:
            self.assertEqual(self.ollama._match_route(phrase), (None, None), phrase)
        for keywords in (self.ollama._MANUFACTURING_KEYWORDS, self.ollama._DESIGN_KEYWORDS):
            self.assertNotIn("assembly", keywords)
            self.assertNotIn("build", keywords)

    def test_manufacturing_questions_keep_the_redirect(self):
        for phrase in ["What does the manufacturing section say about weld quality control?",
                       "Which suppliers do we procure brake discs from?",
                       "How should the bracket be fabricated?"]:
            route, match = self.ollama._match_route(phrase)
            self.assertEqual(route.name if route else None, "manufacturing_redirect", phrase)
            self.assertEqual(match["query"], "Manufacturing Section", phrase)

    def test_first_match_wins(self):
        # A Cypher query mentioning inferred links stays a Cypher query.
        route, match = self.ollama._match_route("Run this Cypher query: MATCH (r)-[s:suggestedProject]->(p) "
                                                "RETURN 'inferred link' AS x")
        self.assertEqual(route.name, "cypher_query")
        self.assertTrue(match["cypher"].startswith("MATCH"))
        # Review commands win over the inferred-links keywords.
        self.assertEqual(self.ollama._match_route("confirm link REQ-1 -> SRP8-045")[0].name, "review_confirm")

    def test_matchers_extract_arguments(self):
        _, match = self.ollama._match_route(EXAMPLES["suggest_link"])
        self.assertEqual(match, TOOL_ROUTES["suggest_link"][1])
        _, match = self.ollama._match_route(EXAMPLES["count_requirements"])
        self.assertEqual(match, {"rule_id": "ADR31"})
        _, match = self.ollama._match_route(EXAMPLES["review_reject"])
        self.assertEqual(match["reason"], "it is a front-axle rule")
        _, match = self.ollama._match_route(EXAMPLES["manufacturing_redirect"])
        self.assertEqual(match["query"], "Manufacturing Section")
        _, match = self.ollama._match_route(EXAMPLES["design_guidance"])
        self.assertEqual(match["query"], "The Design Process")

    def test_uses_llm_flags(self):
        uses_llm = {name for name, r in self.routes.items() if r.uses_llm}
        self.assertEqual(uses_llm, {"manufacturing_redirect", "design_guidance"})
        self.assertIsNone(self.routes["exit"].handler)
        self.assertTrue(all(r.handler for n, r in self.routes.items() if n != "exit"))

    def test_routes_list_is_explicit_and_ordered(self):
        self.assertEqual([r.name for r in self.ollama.ROUTES], [
            "exit", "review_confirm", "review_reject", "review_usage", "cypher_query", "suggest_link",
            "rl_policy", "unassigned_requirements", "list_all_projects", "inferred_links",
            "count_requirements", "reference", "manufacturing_redirect", "design_guidance",
        ])

    def test_printed_table_has_every_route(self):
        table = self.ollama.format_routes_table()
        for name in self.routes:
            self.assertIn(name, table)
        self.assertIn("rl_prefetch (default)", table)


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=f'{{"tool": "{name}"}}')], isError=False)


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = test_review_access._load_ollama()

    def test_tool_routes_call_one_tool_and_never_the_model(self):
        def no_model(**kwargs):
            raise AssertionError("the model must not be called by a tool route")

        saved = self.ollama._post_chat
        self.ollama._post_chat = no_model
        try:
            for name, (tool, args) in TOOL_ROUTES.items():
                session = FakeSession()
                ctx = self.ollama._ChatContext(session=session, model="m", tools=[], messages=[])
                route, match = self.ollama._match_route(EXAMPLES[name])
                ctx.turn = self.ollama._new_turn("s", "m", EXAMPLES[name])
                ctx.turn["route"] = route.name
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    asyncio.run(route.handler(ctx, match))
                self.assertEqual(session.calls, [(tool, args)], name)
                self.assertEqual(ctx.turn["answer"], f'{{"tool": "{tool}"}}', name)   # raw tool output
                self.assertIn(f'{{"tool": "{tool}"}}', out.getvalue(), name)
                self.assertEqual(ctx.turn["llm_calls"], 0, name)
                self.assertEqual([m["role"] for m in ctx.messages], ["user", "assistant"], name)
        finally:
            self.ollama._post_chat = saved

    def test_chat_loop_dispatches_before_rl_and_zeroes_llm_calls(self):
        source = (EXT_DIR / "ollama-mcp").read_text(encoding="utf-8")
        chat = source[source.index("async def run_chat"):]
        dispatch = chat.index("route, match = _match_route(user_input)")
        self.assertLess(dispatch, chat.index("rl_bridge.choose_action("))
        self.assertIn('turn["route"] = route.name', chat)
        self.assertIn('if not route.uses_llm:\n                            turn["llm_calls"] = 0', chat)


class TestingGuideTests(unittest.TestCase):
    EXPECTED = {
        "Show me the current RL policy.": "rl_policy",
        "Show me the unassigned requirements.": "unassigned_requirements",
        "List all projects.": "list_all_projects",
        "Show me all inferred links.": "inferred_links",
        "Please reject the suggestion that [req_id] belongs to [project_id].": None,
    }

    def test_guide_prompts_take_the_intended_routes(self):
        ollama = test_review_access._load_ollama()
        text = (EXT_DIR / "testing_rl_steps.md").read_text(encoding="utf-8")
        prompts = [line[2:] for line in text.splitlines() if line.startswith("> ")]
        prompts += [line for line in text.splitlines() if re.match(r"^(confirm|reject) link ", line)]
        self.assertTrue(prompts)
        for prompt, expected in self.EXPECTED.items():
            self.assertIn(prompt, prompts)
            route, _ = ollama._match_route(prompt)
            self.assertEqual(route.name if route else None, expected, prompt)
        for prompt in prompts:
            route, _ = ollama._match_route(prompt)
            name = route.name if route else None
            if prompt.startswith("Run this Cypher query:"):
                self.assertEqual(name, "cypher_query", prompt)
            elif prompt.startswith("Suggest that requirement"):
                self.assertEqual(name, "suggest_link", prompt)
            elif prompt.startswith("reject link"):
                self.assertEqual(name, "review_reject", prompt)


if __name__ == "__main__":
    unittest.main()
