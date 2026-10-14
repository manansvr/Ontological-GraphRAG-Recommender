#!/usr/bin/env python3
"""Fault-injection tests for thesis-ontology/scripts/validate.py: every check must fail, and
the script must exit 1, when its condition is broken. Each test works on a temporary copy.

Run from the repository root:
    python3 -m unittest discover -s thesis-extension/tests -v
"""

import contextlib
import importlib.util
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ONTOLOGY = Path(__file__).resolve().parent.parent.parent / "thesis-ontology"
OWL = (ONTOLOGY / "ontology.owl").read_text(encoding="utf-8")


def _load_validate():
    spec = importlib.util.spec_from_file_location("validate_under_test", ONTOLOGY / "scripts" / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = _load_validate()


class ValidateFaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.owl = self.dir / "ontology.owl"
        self.csv = self.dir / "csv"
        shutil.copytree(ONTOLOGY / "csv", self.csv)
        self.owl.write_text(OWL, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_validate(self):
        results, _ = validate.run_checks(self.owl, self.csv)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = validate.main(["--owl", str(self.owl), "--csv-dir", str(self.csv)])
        return {name: ok for name, ok, _ in results}, code, out.getvalue()

    def edit(self, old, new, count=1):
        text = self.owl.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.owl.write_text(text.replace(old, new, count), encoding="utf-8")

    def test_unmodified_ontology_passes(self):
        checks, code, out = self.run_validate()
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(code, 0)
        self.assertIn("ONTOLOGY READY FOR USE", out)

    def test_broken_xml_fails(self):
        self.owl.write_text(OWL[: len(OWL) // 2], encoding="utf-8")
        checks, code, out = self.run_validate()
        self.assertFalse(checks["XML syntax"])
        self.assertEqual(code, 1)
        self.assertIn("✗ XML syntax: not well-formed XML", out)

    def test_wrong_namespace_fails(self):
        self.edit('xmlns:xsd="http://www.w3.org/2001/XMLSchema#"', 'xmlns:xsd="http://example.org/not-xsd#"')
        checks, code, out = self.run_validate()
        self.assertFalse(checks["Namespaces"])
        self.assertTrue(checks["XML syntax"])
        self.assertEqual(code, 1)
        self.assertIn("xsd (expected http://www.w3.org/2001/XMLSchema#", out)

    def test_class_without_label_fails(self):
        self.edit("        <rdfs:label>Component</rdfs:label>\n", "")
        checks, code, out = self.run_validate()
        self.assertFalse(checks["Class labels"])
        self.assertEqual(code, 1)
        self.assertIn("#Component", out)

    def test_empty_label_fails(self):
        self.edit("<rdfs:label>Component</rdfs:label>", "<rdfs:label>  </rdfs:label>")
        self.assertFalse(self.run_validate()[0]["Class labels"])

    def test_missing_ontology_metadata_fails(self):
        title = re.search(r"\s*<dcterms:title>.*?</dcterms:title>", OWL).group(0)
        self.edit(title, "")
        checks, code, out = self.run_validate()
        self.assertFalse(checks["Ontology metadata"])
        self.assertEqual(code, 1)
        self.assertIn("missing: dcterms:title", out)

    def test_missing_version_info_fails(self):
        version = re.search(r"\s*<owl:versionInfo>.*?</owl:versionInfo>", OWL).group(0)
        self.edit(version, "")
        self.assertFalse(self.run_validate()[0]["Ontology metadata"])

    def test_csv_drift_fails(self):
        path = self.csv / "node-properties.csv"
        path.write_text(path.read_text(encoding="utf-8") + "extra,All,string,,\n", encoding="utf-8")
        checks, code, out = self.run_validate()
        self.assertFalse(checks["Schema CSVs"])
        self.assertEqual(code, 1)
        self.assertIn("node-properties.csv", out)

    def test_no_check_is_printed_without_being_tested(self):
        source = (ONTOLOGY / "scripts" / "validate.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'print\(f?"\s*✓')   # every ✓ comes from a result


if __name__ == "__main__":
    unittest.main()
