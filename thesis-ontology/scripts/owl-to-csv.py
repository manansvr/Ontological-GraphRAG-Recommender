#!/usr/bin/env python3
"""owl-to-csv.py: generate the schema CSVs from ontology.owl, the single source of truth.

Writes, in OWL document order:
  csv/node-labels.csv              Label, ParentLabel, Description, Type, Category
  csv/relationships.csv            RelationshipType, SourceLabel, TargetLabel, Description, Properties
  csv/node-properties.csv          PropertyName, ApplicableLabels, DataType, Description, Constraints
  csv/relationship-properties.csv  RelationshipType, PropertyName, DataType, Description

How each column is derived from the OWL file:
  Label / RelationshipType / PropertyName   owl:Class / owl:ObjectProperty / owl:DatatypeProperty
  ParentLabel                               rdfs:subClassOf
  Description                               rdfs:comment ("" if none)
  Type                                      TopLevel if the class has no parent, else Derived
  Category                                  Organization if the root ancestor is Organization, else Artifact
  SourceLabel / TargetLabel / ApplicableLabels   rdfs:domain / rdfs:range; owl:unionOf -> "A|B";
                                            owl:Thing or no domain -> "All"
  Properties                                owl:SymmetricProperty / owl:TransitiveProperty -> symmetric / transitive
  DataType                                  XSD range local name (dateTime -> datetime)
  Constraints                               the valueConstraint annotation
  relationship-properties rows              edgeProperty annotations, "name | datatype | description";
                                            OWL data properties describe nodes, so properties stored on
                                            Neo4j relationships are documented this way

Usage:
    python3 scripts/owl-to-csv.py           # regenerate the four CSVs
    python3 scripts/owl-to-csv.py --check   # exit 1 if any CSV differs from ontology.owl
"""

import argparse
import csv
import io
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).resolve().parent.parent
OWL_FILE = ONTOLOGY_DIR / "ontology.owl"
CSV_DIR = ONTOLOGY_DIR / "csv"

NS = {
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "sr8": "http://www.sunswift.com/ontology/sr8-thesis#",
}
ABOUT = f"{{{NS['rdf']}}}about"
RESOURCE = f"{{{NS['rdf']}}}resource"
CHARACTERISTICS = {"SymmetricProperty": "symmetric", "TransitiveProperty": "transitive"}
DATATYPES = {"dateTime": "datetime"}

FILES = {
    "node-labels.csv": ["Label", "ParentLabel", "Description", "Type", "Category"],
    "relationships.csv": ["RelationshipType", "SourceLabel", "TargetLabel", "Description", "Properties"],
    "node-properties.csv": ["PropertyName", "ApplicableLabels", "DataType", "Description", "Constraints"],
    "relationship-properties.csv": ["RelationshipType", "PropertyName", "DataType", "Description"],
}


def _local(uri):
    return (uri or "").rsplit("#", 1)[-1]


def _classes(element):
    """Class names in a domain/range element: a single resource or an owl:unionOf collection."""
    if element is None:
        return []
    if element.get(RESOURCE):
        return [_local(element.get(RESOURCE))]
    return [_local(d.get(ABOUT) or d.get(RESOURCE)) for d in element.findall(".//owl:unionOf/*", NS)]


def _labels(names):
    names = [n for n in names if n != "Thing"]
    return "|".join(names) if names else "All"


def _text(element, path):
    found = element.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def read_ontology(path=OWL_FILE):
    root = ET.parse(path).getroot()
    classes, relationships, properties, characteristics = {}, {}, {}, {}
    for el in root:
        name = _local(el.get(ABOUT))
        if not name:
            continue
        tag = el.tag.rsplit("}", 1)[-1]
        types = [_local(t.get(RESOURCE)) for t in el.findall("rdf:type", NS)]
        for t in types:
            if t in CHARACTERISTICS:
                characteristics.setdefault(name, []).append(CHARACTERISTICS[t])
        if tag == "Class":
            parents = [_local(s.get(RESOURCE)) for s in el.findall("rdfs:subClassOf", NS) if s.get(RESOURCE)]
            classes[name] = {"parents": parents, "comment": _text(el, "rdfs:comment")}
        elif tag == "ObjectProperty":
            edges = []
            for e in el.findall("sr8:edgeProperty", NS):
                parts = [p.strip() for p in (e.text or "").split("|", 2)]
                if len(parts) != 3:
                    raise ValueError(f"{name}: edgeProperty must be 'name | datatype | description': {e.text!r}")
                edges.append(parts)
            relationships[name] = {
                "domain": _classes(el.find("rdfs:domain", NS)),
                "range": _classes(el.find("rdfs:range", NS)),
                "comment": _text(el, "rdfs:comment"),
                "edges": edges,
            }
        elif tag == "DatatypeProperty":
            rng = el.find("rdfs:range", NS)
            properties[name] = {
                "domain": _classes(el.find("rdfs:domain", NS)),
                "range": _local(rng.get(RESOURCE)) if rng is not None else "",
                "comment": _text(el, "rdfs:comment"),
                "constraint": _text(el, "sr8:valueConstraint"),
            }
    return classes, relationships, properties, characteristics


def build_rows(path=OWL_FILE):
    classes, relationships, properties, characteristics = read_ontology(path)

    def root_of(name):
        seen = set()
        while classes.get(name, {}).get("parents") and name not in seen:
            seen.add(name)
            name = classes[name]["parents"][0]
        return name

    labels = [{
        "Label": name,
        "ParentLabel": "|".join(info["parents"]),
        "Description": info["comment"],
        "Type": "TopLevel" if not info["parents"] else "Derived",
        "Category": "Organization" if root_of(name) == "Organization" else "Artifact",
    } for name, info in classes.items()]
    rels = [{
        "RelationshipType": name,
        "SourceLabel": _labels(info["domain"]),
        "TargetLabel": _labels(info["range"]),
        "Description": info["comment"],
        "Properties": "|".join(characteristics.get(name, [])),
    } for name, info in relationships.items()]
    props = [{
        "PropertyName": name,
        "ApplicableLabels": _labels(info["domain"]),
        "DataType": DATATYPES.get(info["range"], info["range"]),
        "Description": info["comment"],
        "Constraints": info["constraint"],
    } for name, info in properties.items()]
    edge_props = [{
        "RelationshipType": name, "PropertyName": prop, "DataType": dtype, "Description": desc,
    } for name, info in relationships.items() for prop, dtype, desc in info["edges"]]
    return {"node-labels.csv": labels, "relationships.csv": rels,
            "node-properties.csv": props, "relationship-properties.csv": edge_props}


def render(rows_by_file):
    out = {}
    for filename, fields in FILES.items():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows_by_file[filename])
        out[filename] = buffer.getvalue()
    return out


def differences(csv_dir=CSV_DIR, owl_file=OWL_FILE):
    """Files whose content differs from what ontology.owl generates (missing files included)."""
    expected = render(build_rows(owl_file))
    diffs = []
    for filename, content in expected.items():
        path = Path(csv_dir) / filename
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            diffs.append(filename)
    return diffs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the schema CSVs from ontology.owl.")
    parser.add_argument("--check", action="store_true", help="exit 1 if the CSVs differ from ontology.owl")
    args = parser.parse_args(argv)
    if args.check:
        diffs = differences()
        if diffs:
            print("Out of date with ontology.owl: " + ", ".join(diffs) + " (run scripts/owl-to-csv.py)")
            return 1
        print("CSVs match ontology.owl")
        return 0
    rendered = render(build_rows())
    for filename, content in rendered.items():
        (CSV_DIR / filename).write_text(content, encoding="utf-8")
        print(f"wrote csv/{filename} ({content.count(chr(10)) - 1} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
