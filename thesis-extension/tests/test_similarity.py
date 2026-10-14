#!/usr/bin/env python3
"""Offline tests for the shared similar-requirements helper in sr8-mcp.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import csv
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_inference_review as tir  # noqa: E402  (sr8-mcp loader, FakeGraph, Base)

sr8 = tir.sr8
REPO = Path(__file__).resolve().parent.parent.parent

CANDIDATES = [  # target is ("Brake Linings", "5.1.1.3")
    {"req_id": "REQ-31-006", "req_name": "Brake Linings", "clause": "5.1.1.3", "assigned_projects": ["SRP8-046"]},
    {"req_id": "REQ-31-041", "req_name": "Brake Linings Inspection", "clause": "5.2.11.2.1", "assigned_projects": ["SRP8-045"]},
    {"req_id": "REQ-31-007", "req_name": "Braking Equipment", "clause": "5.1.1.4", "assigned_projects": ["SRP8-045"]},
    {"req_id": "REQ-31-099", "req_name": "Linings of the brake", "clause": None, "assigned_projects": ["SRP8-045"]},
    {"req_id": "REQ-31-010", "req_name": "Service braking system", "clause": "5.1.2.1", "assigned_projects": ["SRP8-046"]},
    {"req_id": "REQ-31-022", "req_name": "Service Braking System", "clause": "5.2.6", "assigned_projects": ["SRP8-045"]},
    {"req_id": "REQ-31-044", "req_name": "Hydraulic Braking Systems", "clause": "5.2.12", "assigned_projects": ["SRP8-045"]},
]


class WordAndClauseTests(unittest.TestCase):
    def test_content_words(self):
        self.assertEqual(sr8._name_words("Linings of the Brake"), {"linings", "brake"})
        self.assertEqual(sr8._name_words("Relates to 5.2.2, 5.2.3"), {"relates", "5", "2", "3"})
        self.assertEqual(sr8._name_words(None), set())

    def test_clause_parts(self):
        self.assertEqual(sr8._clause_parts("6.6.1 Pt 2"), (6, 6, 1))
        self.assertEqual(sr8._clause_parts("5.2.8.1.2"), (5, 2, 8, 1, 2))
        self.assertIsNone(sr8._clause_parts(""))
        self.assertIsNone(sr8._clause_parts(None))

    def test_adjacency(self):
        cases = [("5.2.7", "5.2.8", True), ("5.2.8", "5.2.8", True), ("5.1", "5.2", True), ("6", "7", True),
                 ("5.2.8", "5.2.10", False), ("5.2.8", "5.2.8.1", False), ("5.1", "6.1", False),
                 ("5.1.1.3", "5.1.2.1", False), ("6.6.1 Pt 2", "6.6.1 Pt 3", True)]
        for a, b, expected in cases:
            self.assertEqual(sr8._clauses_adjacent(a, b), expected, (a, b))
        self.assertIsNone(sr8._clauses_adjacent("5.1", None))


class HelperTests(tir.Base):
    def run_helper(self, candidates, target=("Brake Linings", "5.1.1.3")):
        graph = tir.FakeGraph(candidates=candidates, target=target)
        return sr8._similar_assigned_requirements(tir.FakeTx(graph), "REQ-31-005")

    def test_scores_components_and_order(self):
        result = self.run_helper(CANDIDATES)
        self.assertEqual(result["candidate_count"], 7)
        by_id = {c["req_id"]: c for c in result["candidates"]}
        self.assertEqual((by_id["REQ-31-006"]["clause_adjacent"], by_id["REQ-31-006"]["name_overlap"],
                          by_id["REQ-31-006"]["score"]), (True, 1.0, 2.0))
        self.assertEqual((by_id["REQ-31-007"]["clause_adjacent"], by_id["REQ-31-007"]["score"]), (True, 1.0))
        self.assertEqual((by_id["REQ-31-041"]["clause_adjacent"], by_id["REQ-31-041"]["name_overlap"]),
                         (False, round(2 / 3, 4)))
        self.assertEqual(by_id["REQ-31-041"]["shared_words"], ["brake", "linings"])
        self.assertIsNone(by_id["REQ-31-099"]["clause_adjacent"])      # clause unknown: no adjacency point
        self.assertEqual(by_id["REQ-31-099"]["score"], 1.0)           # "linings", "brake" = target words
        self.assertEqual([c["req_id"] for c in result["candidates"]][:4],
                         ["REQ-31-006", "REQ-31-007", "REQ-31-099", "REQ-31-041"])
        scores = [c["score"] for c in result["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_candidates_and_missing_requirement(self):
        self.assertEqual(self.run_helper([])["candidate_count"], 0)

        class Empty:
            def run(self, query, **params):
                return tir.FakeResult([])
        self.assertIsNone(sr8._similar_assigned_requirements(Empty(), "REQ-NOPE"))

    def test_tool_shows_top_five_but_counts_all(self):
        self.use(tir.FakeGraph(candidates=CANDIDATES))
        out = json.loads(sr8.get_similar_assigned_requirements("REQ-31-005"))
        self.assertEqual((out["candidate_count"], out["similar_count"], out["shown"]), (7, 7, 5))
        self.assertEqual(len(out["similar_requirements"]), 5)
        self.assertEqual(out["similar_requirements"][0]["req_id"], "REQ-31-006")
        for key in ("score", "clause_adjacent", "name_overlap", "shared_words", "assigned_projects"):
            self.assertIn(key, out["similar_requirements"][0])

    def test_inference_and_tool_use_the_same_helper(self):
        source = tir.SR8_PATH.read_text(encoding="utf-8")
        self.assertEqual(source.count("_similar_assigned_requirements(session, requirement_id)"), 2)
        self.assertNotIn("AS project_has_same_adr", source)

    def test_docstring_describes_the_rule(self):
        doc = sr8.get_similar_assigned_requirements.__doc__
        for phrase in ("assignedToProject", "clause_adjacent", "name_overlap", "Jaccard", "stop-words",
                       "top 5", "candidate_count"):
            self.assertIn(phrase, doc)
        self.assertNotIn("adjacent clause ordering", doc)


class ClauseNumberStoredTests(unittest.TestCase):
    def test_extractor_writes_clause_number_and_schema_declares_it(self):
        source = (REPO / "thesis-extraction/Scripts/extract-ADR.py").read_text(encoding="utf-8")
        self.assertIn("r.clauseNumber       = $clause", source)
        with (REPO / "thesis-ontology/csv/node-properties.csv").open(newline="") as f:
            props = {r["PropertyName"]: r for r in csv.DictReader(f)}
        self.assertEqual(props["clauseNumber"]["ApplicableLabels"], "ExtractedEssentialRequirement")


if __name__ == "__main__":
    unittest.main()
