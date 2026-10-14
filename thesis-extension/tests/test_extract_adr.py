#!/usr/bin/env python3
"""Offline tests for extract-ADR.py: applicability rule, review flags, placeholder project
IDs and the distinct-count summary. No Neo4j is used (live writes go to a fake driver).

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
EXTRACTION = REPO / "thesis-extraction"
SCRIPT = EXTRACTION / "Scripts" / "extract-ADR.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_adr_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


x = _load()


def row(applicability=None, name=""):
    r = {"Req Name": name}
    if applicability is not None:
        r["Applicability"] = applicability
    return r


class ApplicabilityRuleTests(unittest.TestCase):
    def test_basis(self):
        cases = [
            (row("Applicable", "Brake Linings"), (True, "", "column")),
            (row("YES", "Brake Linings"), (True, "", "column")),
            (row("Not Applicable", "Collision Testing"), (False, "Collision Testing", "column")),
            (row("n/a", "Collision Testing"), (False, "Collision Testing", "column")),
            (row(None, "Post Collision Testing"), (False, "Post Collision Testing", "name_keyword")),
            (row("", "Not applicable for EVs"), (False, "Not applicable for EVs", "name_keyword")),
            (row("Partial", "Post Collision Testing"), (False, "Post Collision Testing", "name_keyword")),
            (row("Partial", "Brake Linings"), (True, "", "default")),
            (row(None, "Brake Linings"), (True, "", "default")),
            (row(None, ""), (True, "", "default")),
        ]
        for r, expected in cases:
            self.assertEqual(x.read_applicability(r, r["Req Name"]), expected, r)

    def test_column_wins_over_name(self):
        self.assertEqual(x.read_applicability(row("Applicable", "Post Collision Testing"), "Post Collision Testing"),
                         (True, "", "column"))

    def test_review_flag_rule(self):
        flagged = [
            row("Partial", "Brake Linings"),                       # non-empty, unrecognised
            row("TBC", "Post Collision Testing"),                  # non-empty, unrecognised
            row("Applicable", "Post Collision Testing"),           # recognised value disagrees with name
            row("yes", "Not applicable after 2025"),
        ]
        not_flagged = [
            row(None, "Post Collision Testing"),                   # missing column is not a reason
            row("", "Post Collision Testing"),                     # empty column is not a reason
            row("  ", "Brake Linings"),
            row("Not Applicable", "Post Collision Testing"),       # agree
            row("Not Applicable", "Collision Testing"),            # name silent: no disagreement
            row("Applicable", "Brake Linings"),
        ]
        for r in flagged:
            self.assertTrue(x.applicability_review_reason(r, r["Req Name"]), r)
        for r in not_flagged:
            self.assertEqual(x.applicability_review_reason(r, r["Req Name"]), "", r)

    def test_unreachable_branch_removed_and_docstring_states_the_rule(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("is_applicable is None", source)
        doc = x.read_applicability.__doc__
        self.assertIn("requirement text (body) is never read", doc)
        self.assertIn("'column'", doc)
        self.assertIn("'name_keyword'", doc)
        self.assertIn("'default'", doc)
        self.assertIn("A missing or empty column is not flagged", x.applicability_review_reason.__doc__)


class ProjectPlaceholderTests(unittest.TestCase):
    def test_placeholders_mean_no_project(self):
        for value in ("N/A", "n/a", "NA", "na", "-", "", "  ", "TBC", "tbc", None):
            self.assertEqual(x.normalise_project_id(value), "", repr(value))
        self.assertEqual(x.normalise_project_id(" SRP8-045 "), "SRP8-045")


class DryRunSummaryTests(unittest.TestCase):
    def test_summary_on_the_eight_current_csvs(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            summary = x.extract_adrs(folder=str(EXTRACTION / "csv"), dry_run=True,
                                     review_file=Path(tmp) / "review.csv")
            review = list(csv.DictReader(open(Path(tmp) / "review.csv")))
        self.assertEqual({k: summary[k] for k in (
            "ledger_rows", "requirement_nodes", "requirements_applicable", "requirements_not_applicable",
            "clause_nodes", "assigned_to_project_edges", "distinct_projects", "unassigned_requirements",
            "flagged_for_review", "placeholder_project_rows")}, {
            "ledger_rows": 255, "requirement_nodes": 217, "requirements_applicable": 211,
            "requirements_not_applicable": 6, "clause_nodes": 177, "assigned_to_project_edges": 172,
            "distinct_projects": 24, "unassigned_requirements": 45, "flagged_for_review": 0,
            "placeholder_project_rows": 2})
        self.assertEqual(summary["skipped_rows"], {})
        self.assertEqual(summary["rows_without_requirement"],
                         {"no requirement name": 31, "requirement name but no text (applicable)": 7})
        self.assertEqual(summary["row_counters"], {
            "rows with a clause number": 255, "rows creating a requirement": 217,
            "rows with a project or department": 190, "rows with a verification method": 0})
        self.assertEqual(review, [])
        self.assertIn("📄 ADR10-Requirements.csv", out.getvalue())   # sr8-mcp extraction_report parses this line

    def test_extraction_md_shows_the_new_totals(self):
        text = (EXTRACTION / "Documentation" / "extraction.md").read_text(encoding="utf-8")
        for expected in ("ledger rows:                        255",
                         "requirement nodes:                  217 (211 applicable, 6 not applicable)",
                         "distinct Clause nodes:              177",
                         "assignedToProject edges:            172",
                         "distinct projects:                  24",
                         "unassigned requirements:            45"):
            self.assertIn(expected, text)
        for stale in ("clauses: 243", "requirements: 205", "proj_links: 178"):
            self.assertNotIn(stale, text)


HEADER = ["ADR Number", "Clause", "Req Name", "Applicability", "Text", "Project ID", "Relevant Project",
          "Relevant Department", "ADR Name"]


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


class SyntheticFileTests(unittest.TestCase):
    ROWS = [
        ["ADR 99", "1.1", "Brake Linings", "Applicable", "No asbestos.", "SRP8-045", "Front Brakes", "Chassis", "Test ADR"],
        ["", "1.2", "Post Collision Testing", "Applicable", "Doors open.", "N/A", "", "", ""],      # disagreement
        ["", "1.3", "Wheel Space", "Partial", "Room to turn.", "TBC", "", "", ""],                 # unrecognised
        ["", "1.4", "Spare Tyre", "", "Spare fitted.", "SRP8-050", "Front Wheels", "", ""],         # empty column
        ["", "", "", "", "", "", "", "", ""],                                                       # skipped
    ]

    def test_flags_review_rows_and_treats_placeholders_as_unassigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_csv(Path(tmp) / "ADR99-Requirements.csv", self.ROWS)
            with contextlib.redirect_stdout(io.StringIO()):
                summary = x.extract_adrs(folder=tmp, dry_run=True, review_file=Path(tmp) / "review.csv")
            review = list(csv.DictReader(open(Path(tmp) / "review.csv")))
        self.assertEqual(summary["requirement_nodes"], 4)
        self.assertEqual(summary["assigned_to_project_edges"], 2)
        self.assertEqual(summary["unassigned_requirements"], 2)
        self.assertEqual(summary["placeholder_project_rows"], 2)
        self.assertEqual(summary["distinct_projects"], 2)
        self.assertEqual(summary["skipped_rows"], {"no clause, requirement name or text": 1})
        self.assertEqual([(r["csv_row"], r["basis"]) for r in review], [("3", "column"), ("4", "default")])
        self.assertIn("says not applicable", review[0]["reason"])
        self.assertIn("unrecognised Applicability value 'Partial'", review[1]["reason"])

    def test_live_writes_store_basis_and_review_and_never_write_placeholder_projects(self):
        calls = []

        class Session:
            def run(self, query, **params):
                calls.append((query, params))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Driver:
            def session(self):
                return Session()

        with tempfile.TemporaryDirectory() as tmp:
            _write_csv(Path(tmp) / "ADR99-Requirements.csv", self.ROWS)
            with contextlib.redirect_stdout(io.StringIO()):
                x.extract_adrs(folder=tmp, driver=Driver(), dry_run=False, review_file=Path(tmp) / "review.csv")
        requirements = [p for q, p in calls if "MERGE (r:ExtractedEssentialRequirement" in q]
        self.assertEqual([p["clause"] for p in requirements], ["1.1", "1.2", "1.3", "1.4"])   # clauseNumber
        self.assertEqual([(p["rid"], p["basis"], p["needs_review"]) for p in requirements], [
            ("REQ-99-001", "column", False), ("REQ-99-002", "column", True),
            ("REQ-99-003", "default", True), ("REQ-99-004", "default", False)])
        self.assertTrue(any("c.applicabilityBasis = $basis" in q and "c.needsReview        = $needs_review" in q
                            for q, _ in calls))
        project_ids = [p["pid"] for q, p in calls if "MERGE (p:Project {projectID: $pid})" in q]
        self.assertEqual(project_ids, ["SRP8-045", "SRP8-050"])
        edges = [(p["rid"], p["pid"]) for q, p in calls if "MERGE (r)-[rel:assignedToProject]->(p)" in q]
        self.assertEqual(edges, [("REQ-99-001", "SRP8-045"), ("REQ-99-004", "SRP8-050")])


if __name__ == "__main__":
    unittest.main()
