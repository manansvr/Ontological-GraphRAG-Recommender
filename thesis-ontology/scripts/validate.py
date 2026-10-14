#!/usr/bin/env python3
"""Validate ontology.owl and the schema CSVs generated from it. Exits 1 if any check fails.

Checks (each one tests its condition; nothing is reported as passed without being tested):
  XML syntax         ontology.owl is well-formed XML
  Namespaces         rdf, rdfs, owl, xsd and dcterms are declared with their standard URIs
  Class labels       every owl:Class with rdf:about has a non-empty rdfs:label
  Ontology metadata  the owl:Ontology element has rdf:about and non-empty dcterms:title,
                     dcterms:description, dcterms:creator, dcterms:created and owl:versionInfo
  Schema CSVs        the four CSVs in csv/ are exactly what scripts/owl-to-csv.py generates

Usage:
    python3 scripts/validate.py [--owl PATH] [--csv-dir PATH]
"""

import argparse
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).resolve().parent.parent
NS = {
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dcterms": "http://purl.org/dc/terms/",
}
ABOUT = f"{{{NS['rdf']}}}about"
RESOURCE = f"{{{NS['rdf']}}}resource"
REQUIRED_METADATA = ["dcterms:title", "dcterms:description", "dcterms:creator", "dcterms:created", "owl:versionInfo"]


def _owl_to_csv():
    spec = importlib.util.spec_from_file_location(
        "owl_to_csv", Path(__file__).resolve().with_name("owl-to-csv.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_xml(owl_file):
    """(ok, detail, root) for the XML syntax check."""
    try:
        root = ET.parse(owl_file).getroot()
    except ET.ParseError as exc:
        return False, f"not well-formed XML: {exc}", None
    except OSError as exc:
        return False, f"cannot read {owl_file}: {exc}", None
    return True, "well-formed XML", root


def check_namespaces(owl_file):
    """Every prefix in NS must be declared on the document with its standard URI."""
    text = Path(owl_file).read_text(encoding="utf-8")
    declared = dict(re.findall(r'xmlns:(\w+)="([^"]*)"', text))
    problems = [f"{prefix} (expected {uri}, found {declared.get(prefix, 'nothing')})"
                for prefix, uri in NS.items() if declared.get(prefix) != uri]
    if problems:
        return False, "missing or wrong namespace declarations: " + "; ".join(problems)
    return True, "rdf, rdfs, owl, xsd and dcterms declared"


def check_class_labels(root):
    unlabelled = [c.get(ABOUT) for c in root.findall(".//owl:Class[@rdf:about]", NS)
                  if not (c.findtext("rdfs:label", default="", namespaces=NS) or "").strip()]
    if unlabelled:
        return False, f"{len(unlabelled)} class(es) without rdfs:label: {', '.join(unlabelled)}"
    return True, f"all {len(root.findall('.//owl:Class[@rdf:about]', NS))} classes have rdfs:label"


def check_metadata(root):
    ontologies = root.findall("owl:Ontology", NS)
    if len(ontologies) != 1:
        return False, f"expected one owl:Ontology element, found {len(ontologies)}"
    onto = ontologies[0]
    missing = [] if onto.get(ABOUT) else ["rdf:about"]
    missing += [tag for tag in REQUIRED_METADATA if not (onto.findtext(tag, default="", namespaces=NS) or "").strip()]
    if missing:
        return False, "owl:Ontology is missing: " + ", ".join(missing)
    return True, "owl:Ontology has rdf:about, " + ", ".join(REQUIRED_METADATA)


def check_csvs(owl_file, csv_dir):
    try:
        diffs = _owl_to_csv().differences(csv_dir=csv_dir, owl_file=owl_file)
    except Exception as exc:   # e.g. the OWL file cannot be parsed
        return False, f"could not generate CSVs from {owl_file}: {exc}"
    if diffs:
        return False, f"out of date with ontology.owl: {', '.join(diffs)} (run scripts/owl-to-csv.py)"
    return True, "node-labels.csv, relationships.csv, node-properties.csv and relationship-properties.csv match ontology.owl"


def run_checks(owl_file=ONTOLOGY_DIR / "ontology.owl", csv_dir=ONTOLOGY_DIR / "csv"):
    """Return [(check name, ok, detail)]; later checks that need the parsed XML fail if it is broken."""
    results = []
    ok, detail, root = check_xml(owl_file)
    results.append(("XML syntax", ok, detail))
    results.append(("Namespaces", *check_namespaces(owl_file)))
    if root is None:
        results.append(("Class labels", False, "skipped: XML could not be parsed"))
        results.append(("Ontology metadata", False, "skipped: XML could not be parsed"))
    else:
        results.append(("Class labels", *check_class_labels(root)))
        results.append(("Ontology metadata", *check_metadata(root)))
    results.append(("Schema CSVs", *check_csvs(owl_file, csv_dir)))
    return results, root


def analyze_ontology(owl_file=ONTOLOGY_DIR / "ontology.owl", csv_dir=ONTOLOGY_DIR / "csv"):
    """Print the report; return True if every check passed."""
    results, root = run_checks(owl_file, csv_dir)

    print("\n" + "=" * 60)
    print("SR8 ONTOLOGY VALIDATION REPORT")
    print("=" * 60)

    if root is not None:
        classes = root.findall(".//owl:Class[@rdf:about]", NS)
        obj_props = root.findall(".//owl:ObjectProperty[@rdf:about]", NS)
        data_props = root.findall(".//owl:DatatypeProperty[@rdf:about]", NS)
        print("\n📊 STATISTICS:")
        print(f"   Classes:           {len(classes)}")
        print(f"   Object Properties: {len(obj_props)}")
        print(f"   Data Properties:   {len(data_props)}")
        print(f"   Individuals:       {len(root.findall('.//owl:NamedIndividual', NS))}")

        print("\n🌳 TOP-LEVEL CLASSES:")
        for cls in classes:
            if cls.find("rdfs:subClassOf", NS) is None:
                print(f"   • {cls.findtext('rdfs:label', default=cls.get(ABOUT), namespaces=NS)}")

    print("\n✅ VALIDATION:")
    for name, ok, detail in results:
        print(f"   {'✓' if ok else '✗'} {name}: {detail}")

    passed = all(ok for _, ok, _ in results)
    print("\n" + "=" * 60)
    print("ONTOLOGY READY FOR USE" if passed else "VALIDATION FAILED")
    print("=" * 60)
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate ontology.owl and the generated schema CSVs.")
    parser.add_argument("--owl", type=Path, default=ONTOLOGY_DIR / "ontology.owl")
    parser.add_argument("--csv-dir", type=Path, default=ONTOLOGY_DIR / "csv")
    args = parser.parse_args(argv)
    return 0 if analyze_ontology(args.owl, args.csv_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
