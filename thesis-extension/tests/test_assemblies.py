#!/usr/bin/env python3
"""Offline tests for assemblies: ontology names, sr8-mcp queries and the assembly extractor.

The ontology names are (Project)-[:belongsToAssembly]->(Assembly), with assemblies
identified by hasID / hasName. No Neo4j is used; the live extractor path runs against a
fake driver.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import csv
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import test_inference_review  # noqa: E402  (provides the sr8-mcp loader and FakeGraph)

EXT_DIR = TESTS_DIR.parent
REPO = EXT_DIR.parent
EXTRACTION = REPO / "thesis-extraction"
SR8_SOURCE = (EXT_DIR / "sr8-mcp").read_text(encoding="utf-8")


def _load_extractor():
    spec = importlib.util.spec_from_file_location("extract_assemblies_under_test",
                                                  EXTRACTION / "Scripts" / "extract_assemblies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OntologyNameTests(unittest.TestCase):
    def test_relationship_is_declared_project_to_assembly(self):
        with (REPO / "thesis-ontology/csv/relationships.csv").open(newline="") as f:
            rows = {r["RelationshipType"]: r for r in csv.DictReader(f)}
        self.assertEqual((rows["belongsToAssembly"]["SourceLabel"], rows["belongsToAssembly"]["TargetLabel"]),
                         ("Project", "Assembly"))
        self.assertNotIn("partOfAssembly", rows)

    def test_sr8_uses_only_the_ontology_names(self):
        for old in ("partOfAssembly", "assemblyID", "assemblyName"):
            self.assertNotIn(old, SR8_SOURCE)
        self.assertEqual(SR8_SOURCE.count("belongsToAssembly"), 13)

    def test_every_assembly_node_pattern_is_labelled(self):
        # hasID is on every node, so an unlabelled (asm {hasID: ...}) could match a requirement or ADR.
        patterns = re.findall(r"\((asm[12]?)(?=[\s:{)])([^)]*)\)", SR8_SOURCE)
        self.assertTrue(patterns)
        for var, rest in patterns:
            if rest.strip().startswith(("IS ", "AND", "OR")):
                continue  # a WHERE expression such as (asm IS NOT NULL ...), not a node pattern
            self.assertTrue(rest.startswith(":Assembly"), f"({var}{rest})")

    def test_get_assembly_matches_by_label_and_hasID(self):
        self.assertIn("MATCH (asm:Assembly {hasID: $assembly_id})", SR8_SOURCE)
        self.assertIn("(asm1:Assembly {hasID: $assembly_id})<-[:belongsToAssembly]-(p1:Project)", SR8_SOURCE)

    def test_schema_validation_accepts_the_relationship(self):
        with (REPO / "thesis-ontology/csv/relationships.csv").open(newline="") as f:
            rels = {r["RelationshipType"]: (r["SourceLabel"], r["TargetLabel"]) for r in csv.DictReader(f)}
        graph = test_inference_review.FakeGraph(schema=rels, subclass_of={})
        ok, reason = test_inference_review.sr8._validate_against_schema(
            "belongsToAssembly", ["Project"], ["Assembly"], tx=test_inference_review.FakeTx(graph))
        self.assertTrue(ok, reason)

    def test_hand_run_cypher_no_longer_creates_assemblies(self):
        text = (EXTRACTION / "Documentation/one-command.cypher").read_text(encoding="utf-8")
        self.assertNotIn("MERGE (a:Assembly", text)
        self.assertIn("run-extraction.py --only assemblies", text)


class ExtractorDryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x = _load_extractor()

    def run_dry(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report = self.x.extract_assemblies(str(EXTRACTION / "data/assemblies.csv"), dry_run=True,
                                               adr_folder=str(EXTRACTION / "csv"))
        return report, out.getvalue()

    def test_projects_linked_and_requirements_per_assembly(self):
        report, _ = self.run_dry()
        self.assertEqual({a: r["projects_linked"] for a, r in report.items()}, {
            "ASM-FRONT-AXLE": ["SRP8-043", "SRP8-045", "SRP8-050"],
            "ASM-STEERING": ["SRP8-047", "SRP8-048", "SRP8-049"],
            "ASM-REAR-AXLE": ["SRP8-044", "SRP8-046", "SRP8-051"],
        })
        self.assertEqual({a: r["requirements_reaching_assembly"] for a, r in report.items()},
                         {"ASM-FRONT-AXLE": 45, "ASM-STEERING": 38, "ASM-REAR-AXLE": 35})

    def test_missing_projects_are_warned_and_skipped(self):
        report, output = self.run_dry()
        self.assertEqual(report["ASM-FRONT-AXLE"]["projects_skipped"], ["SRP8-088"])
        self.assertEqual(report["ASM-REAR-AXLE"]["projects_skipped"], ["SRP8-089"])
        self.assertIn("project SRP8-088 does not exist", output)
        self.assertIn("project SRP8-089 does not exist", output)
        self.assertIn("no stub created", output)

    def test_project_set_matches_extract_adr(self):
        projects, requirements = self.x.projects_from_adr_csvs(str(EXTRACTION / "csv"))
        self.assertEqual(len(projects), 24)                                  # "N/A" is not a project
        self.assertNotIn("N/A", projects)
        self.assertEqual(sum(len(r) for r in requirements.values()), 172)   # assignedToProject edges

    def test_csv_validation_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("assembly,project\nA,P\n")
            with self.assertRaises(ValueError):
                self.x.read_assemblies(str(bad))
            dup = Path(tmp) / "dup.csv"
            dup.write_text("assembly_id,assembly_name,project_id\nA,Alpha,P1\nA,Alpha,P1\nA,Alpha,P2\n,,\n")
            self.assertEqual(self.x.read_assemblies(str(dup)), {"A": {"name": "Alpha", "projects": ["P1", "P2"]}})


class FakeResult(list):
    def single(self):
        return self[0] if self else None


class FakeSession:
    def __init__(self, log, projects):
        self.log, self.projects = log, projects

    def run(self, query, **params):
        self.log.append((query, params))
        if "RETURN p.projectID AS pid" in query and "collect" not in query:
            return FakeResult([{"pid": p} for p in self.projects])
        if "collect(DISTINCT r.hasID) AS reqs" in query:
            return FakeResult([{"pid": "SRP8-045", "reqs": ["REQ-31-001", "REQ-31-003"]}])
        if "RETURN count(DISTINCT p) AS linked" in query:
            return FakeResult([{"linked": len([p for p in params["pids"] if p in self.projects])}])
        return FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDriver:
    def __init__(self, projects):
        self.log, self.projects = [], projects

    def session(self):
        return FakeSession(self.log, self.projects)


class ExtractorLiveRunTests(unittest.TestCase):
    def test_live_run_links_existing_projects_only_and_never_creates_projects(self):
        x = _load_extractor()
        driver = FakeDriver(projects={"SRP8-043", "SRP8-045"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assemblies.csv"
            path.write_text("assembly_id,assembly_name,project_id\n"
                            "ASM-FRONT-AXLE,Front Axle Assembly,SRP8-043\n"
                            "ASM-FRONT-AXLE,Front Axle Assembly,SRP8-045\n"
                            "ASM-FRONT-AXLE,Front Axle Assembly,SRP8-088\n")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                report = x.extract_assemblies(str(path), driver=driver, dry_run=False)
        queries = [q for q, _ in driver.log]
        self.assertFalse(any(re.search(r"(MERGE|CREATE)\s*\(p:Project", q) for q in queries))
        merge_assembly = [p for q, p in driver.log if "MERGE (a:Assembly {hasID: $aid})" in q]
        self.assertEqual(merge_assembly, [{"aid": "ASM-FRONT-AXLE", "name": "Front Axle Assembly"}])
        link = [p for q, p in driver.log if "MERGE (p)-[:belongsToAssembly]->(a)" in q]
        self.assertEqual(link, [{"aid": "ASM-FRONT-AXLE", "pids": ["SRP8-043", "SRP8-045"]}])
        self.assertEqual(report["ASM-FRONT-AXLE"]["projects_skipped"], ["SRP8-088"])
        self.assertEqual(report["ASM-FRONT-AXLE"]["requirements_reaching_assembly"], 2)
        self.assertIn("SRP8-088 does not exist (Project nodes in the graph)", out.getvalue())

    def test_run_extraction_offers_the_assemblies_step(self):
        text = (EXTRACTION / "Scripts/run-extraction.py").read_text(encoding="utf-8")
        self.assertIn('"assemblies"]', text)
        self.assertIn('"assemblies_file": "data/assemblies.csv"', text)


if __name__ == "__main__":
    unittest.main()
