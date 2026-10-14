#!/usr/bin/env python3
"""Offline tests that ontology.owl is the single source of truth for the schema.

The four schema CSVs must be exactly what scripts/owl-to-csv.py generates; every node label,
relationship type and edge property the code writes must be declared; and import.py must
load the regenerated CSVs and create the instance-level constraints. No Neo4j is used.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import csv
import importlib.util
import io
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
ONTOLOGY = REPO / "thesis-ontology"
CSV_DIR = ONTOLOGY / "csv"
CODE = {
    "sr8": (REPO / "thesis-extension/sr8-mcp").read_text(encoding="utf-8"),
    "adr": (REPO / "thesis-extraction/Scripts/extract-ADR.py").read_text(encoding="utf-8"),
    "fmea": (REPO / "thesis-extraction/Scripts/extract_failure_modes.py").read_text(encoding="utf-8"),
    "asm": (REPO / "thesis-extraction/Scripts/extract_assemblies.py").read_text(encoding="utf-8"),
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


owl_to_csv = _load("owl_to_csv_under_test", ONTOLOGY / "scripts" / "owl-to-csv.py")


def _rows(name, key):
    with open(CSV_DIR / name, newline="", encoding="utf-8") as f:
        return {r[key]: r for r in csv.DictReader(f)} if key else list(csv.DictReader(f))


def _function(source, name):
    start = source.index(f"def {name}(")
    nxt = re.search(r"\n(?:@|def |# ── )", source[start + 1:])
    return source[start:start + 1 + nxt.start()] if nxt else source[start:]


class GeneratedCsvTests(unittest.TestCase):
    def test_csvs_match_ontology(self):
        self.assertEqual(owl_to_csv.differences(), [])

    def test_regeneration_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in owl_to_csv.render(owl_to_csv.build_rows()).items():
                Path(tmp, name).write_text(content, encoding="utf-8")
            self.assertEqual(owl_to_csv.differences(csv_dir=tmp), [])

    def test_counts(self):
        classes, relationships, properties, _ = owl_to_csv.read_ontology()
        self.assertEqual((len(classes), len(relationships), len(properties)), (72, 59, 70))
        self.assertEqual(len(_rows("relationship-properties.csv", None)), 32)

    def test_broken_symlink_is_gone(self):
        self.assertFalse(os.path.lexists(CSV_DIR / "CSV"))

    def test_validate_fails_when_a_csv_drifts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in owl_to_csv.render(owl_to_csv.build_rows()).items():
                Path(tmp, name).write_text(content, encoding="utf-8")
            Path(tmp, "relationships.csv").write_text("RelationshipType\nx\n", encoding="utf-8")
            self.assertEqual(owl_to_csv.differences(csv_dir=tmp), ["relationships.csv"])
        self.assertIn("check_csvs_match_owl", (ONTOLOGY / "scripts/validate.py").read_text(encoding="utf-8"))


class ModelTests(unittest.TestCase):
    def test_component_is_not_an_assembly(self):
        labels = _rows("node-labels.csv", "Label")
        self.assertEqual(labels["Component"]["ParentLabel"], "PartsManagement")
        self.assertEqual(labels["Assembly"]["ParentLabel"], "PartsManagement")
        rels = _rows("relationships.csv", "RelationshipType")
        self.assertEqual((rels["assembledFrom"]["SourceLabel"], rels["assembledFrom"]["TargetLabel"]), ("Assembly", "Component"))

    def test_new_classes_and_parents(self):
        labels = _rows("node-labels.csv", "Label")
        for name in ("FailureMode", "Cause", "Effect", "ControlAction", "FeedbackEvent"):
            self.assertEqual((labels[name]["ParentLabel"], labels[name]["Type"]), ("", "TopLevel"), name)
        self.assertEqual(labels["ChangeImpactReport"]["ParentLabel"], "Document")

    def test_characteristics(self):
        rels = _rows("relationships.csv", "RelationshipType")
        self.assertEqual({k: r["Properties"] for k, r in rels.items() if r["Properties"]}, {
            "collaboratesWith": "symmetric", "interface": "symmetric",
            "hasComponent": "transitive", "dependsOn": "transitive", "partOfBOM": "transitive"})

    def test_new_relationships(self):
        rels = _rows("relationships.csv", "RelationshipType")
        expected = {
            "hasFailureMode": ("Component", "FailureMode"), "causedBy": ("FailureMode", "Cause"),
            "causes": ("FailureMode", "Effect"), "mitigatedBy": ("FailureMode", "ControlAction"),
            "satisfiesRequirement": ("Component", "Requirement"),
            "suggestedProject": ("ExtractedEssentialRequirement", "Project"),
            "belongsToAssembly": ("Project", "Assembly"),
            "recordedFor": ("FeedbackEvent", "ExtractedEssentialRequirement|Project"),
            "affectsRequirement": ("ChangeImpactReport", "Requirement"),
            "affectsProject": ("ChangeImpactReport", "Project"),
        }
        for name, (src, tgt) in expected.items():
            self.assertEqual((rels[name]["SourceLabel"], rels[name]["TargetLabel"]), (src, tgt), name)

    def test_node_properties(self):
        props = _rows("node-properties.csv", "PropertyName")
        for name in ("applicabilityNote", "clauseText", "isApplicable", "clauseNumber", "applicabilityBasis",
                     "needsReview", "reviewer", "action", "reward", "inferenceState",
                     "overconfidencePenaltyApplied", "hasTimestamp", "rlAction", "requirementID",
                     "hasDescription", "numberOfRequirements"):
            self.assertIn(name, props)
        self.assertNotIn("hasSource", props)
        self.assertEqual(props["hasTimestamp"]["DataType"], "datetime")
        self.assertEqual(props["projectID"]["ApplicableLabels"], "Project|FeedbackEvent")
        self.assertEqual(props["action"]["Constraints"], "values:confirmed|rejected|modified|ignored")


class CodeCoverageTests(unittest.TestCase):
    """Everything the code writes or matches on is declared in the ontology."""

    def test_every_label_and_relationship_type_in_the_code_is_declared(self):
        labels = set(_rows("node-labels.csv", "Label"))
        rels = set(_rows("relationships.csv", "RelationshipType"))
        used_labels, used_rels = set(), set()
        for source in CODE.values():
            for m in re.finditer(r"\(\w*:([A-Z][A-Za-z:]*)", source):
                used_labels |= {l for l in m.group(1).split(":") if l and not l.startswith("Schema")}
            for m in re.finditer(r"\[\w*:([A-Za-z|]+)[\]\s*{]", source):
                used_rels |= set(m.group(1).split("|"))
        self.assertEqual(used_labels - labels, set())
        self.assertEqual(used_rels - rels, set())

    def test_edge_properties_match_what_the_code_writes(self):
        sr8 = CODE["sr8"]
        written = {"suggestedProject": set(), "assignedToProject": set(), "satisfiesRequirement": set()}
        written["suggestedProject"] |= set(re.findall(r"\brel\.(\w+)\s*=", _function(sr8, "_write_inferred_project_link")))
        for fn in ("promote_inferred_link", "modify_inferred_link", "reject_inferred_link"):
            body = _function(sr8, fn)
            written["suggestedProject"] |= set(re.findall(r"\bsuggested\.(\w+)\s*=", body))
            written["assignedToProject"] |= set(re.findall(r"\bconfirmed\.(\w+)\s*=", body))
        written["assignedToProject"] |= set(re.findall(r"\brel\.(\w+)\s*=", CODE["adr"]))
        written["satisfiesRequirement"] |= set(re.findall(r"\brel\.(\w+)\s*=", CODE["fmea"]))
        declared = {}
        for r in _rows("relationship-properties.csv", None):
            declared.setdefault(r["RelationshipType"], set()).add(r["PropertyName"])
        self.assertEqual(declared, written)

    def test_feedback_event_uses_has_timestamp(self):
        helper = _function(CODE["sr8"], "_record_feedback_internal")
        self.assertIn("fe.hasTimestamp = datetime()", helper)
        self.assertNotIn("fe.timestamp =", CODE["sr8"])
        self.assertIn("coalesce(fe.hasTimestamp, fe.timestamp)", CODE["sr8"])   # older events still sort


class ImportScriptTests(unittest.TestCase):
    def run_import(self):
        runs = []

        class Session:
            def run(self, query, **params):
                runs.append((query, params))
                return types.SimpleNamespace(single=lambda: {"count": 0}, __iter__=lambda s: iter([]))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Driver:
            def session(self):
                return Session()

            def close(self):
                pass

        saved = sys.modules.get("neo4j")
        sys.modules["neo4j"] = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda *a, **k: Driver()))
        cwd = os.getcwd()
        try:
            module = _load("import_under_test", ONTOLOGY / "scripts" / "import.py")
            os.chdir(ONTOLOGY)   # import.py reads csv/... relative to thesis-ontology
            with contextlib.redirect_stdout(io.StringIO()):
                importer = module.SR8OntologyImporter()
                counts = (importer.import_node_labels(), importer.import_relationships(), importer.import_properties())
                importer.create_instance_constraints()
        finally:
            os.chdir(cwd)
            if saved is None:
                sys.modules.pop("neo4j", None)
            else:
                sys.modules["neo4j"] = saved
        return counts, runs, module

    def test_loads_the_regenerated_csvs(self):
        counts, runs, _ = self.run_import()
        self.assertEqual(counts, (72, 59, 70))
        names = {p.get("name") for q, p in runs if "MERGE (r:SchemaRelationship" in q}
        self.assertTrue({"suggestedProject", "belongsToAssembly", "affectsRequirement", "affectsProject"} <= names)

    def test_instance_constraints(self):
        _, runs, module = self.run_import()
        statements = [q for q, _ in runs if q.startswith("CREATE CONSTRAINT unique_")]
        for label, prop in [("Project", "projectID"), ("Clause", "hasID"), ("ExtractedEssentialRequirement", "hasID"),
                            ("AustralianDesignRule", "hasID"), ("Component", "hasID"), ("Assembly", "hasID"),
                            ("FeedbackEvent", "hasID"), ("FailureMode", "hasID"), ("Cause", "hasID"),
                            ("Effect", "hasID"), ("ControlAction", "hasID")]:
            self.assertIn(f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE", " ".join(statements), label)
        self.assertNotIn("FOR (n:Requirement) REQUIRE n.hasName", " ".join(statements))
        self.assertTrue(all("IF NOT EXISTS" in q for q in statements))

    def test_verify_counts_come_from_the_csvs(self):
        saved = sys.modules.get("neo4j")
        sys.modules["neo4j"] = types.SimpleNamespace(GraphDatabase=None)
        try:
            verify = _load("verify_under_test", ONTOLOGY / "scripts" / "verify.py")
        finally:
            if saved is None:
                sys.modules.pop("neo4j", None)
            else:
                sys.modules["neo4j"] = saved
        self.assertEqual((verify.EXPECTED_LABELS, verify.EXPECTED_RELATIONSHIPS, verify.EXPECTED_PROPERTIES), (72, 59, 70))


if __name__ == "__main__":
    unittest.main()
