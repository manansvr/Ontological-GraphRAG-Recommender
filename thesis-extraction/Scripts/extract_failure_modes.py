#!/usr/bin/env python3
"""
extract_failure_modes.py
=========================
Extracts FMEA (Failure Mode and Effects Analysis) data from
Brake_System_Failure_Mode_Data.xlsx into the shared knowledge graph.

Sheet 1 "Failure Mode Data" (Component, FailureMode, Cause, Effect, ControlAction):
  Component -[:hasFailureMode]-> FailureMode
  FailureMode -[:causedBy]-> Cause
  FailureMode -[:causes]-> Effect
  FailureMode -[:mitigatedBy]-> ControlAction

Sheet 2 "Requirement Mapping" (Component, Requirement):
  Component -[:satisfiesRequirement]-> Requirement

Component nodes are MERGEd on hasID = raw component name (e.g. "BrakeDiscs"),
the same identifier other extractors would use, so failure-mode data attaches
to whatever Component nodes already exist in the graph rather than creating a
disconnected copy.

Usage:
    python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx --dry-run
    python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx
"""

import argparse
import re
from pathlib import Path

import openpyxl
from neo4j import GraphDatabase

FAILURE_SHEET = "Failure Mode Data"
REQUIREMENT_SHEET = "Requirement Mapping"


def humanize(raw: str) -> str:
    """'wear_adjustment_failure' -> 'Wear adjustment failure'"""
    text = raw.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def slug(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", raw.strip()).strip("_").upper()


def read_sheet_rows(path: str, sheet_name: str) -> list:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h else "" for h in rows[0]]
    out = []
    for row in rows[1:]:
        record = {headers[i]: row[i] for i in range(len(headers)) if i < len(row)}
        if any(v not in (None, "") for v in record.values()):
            out.append(record)
    return out


# ── Writers ───────────────────────────────────────────────────────────

def write_failure_mode_row(session, component: str, failure_mode: str,
                            cause: str, effect: str, control_action: str):
    fm_id = f"FM-{component}-{slug(failure_mode)}"
    cause_id = f"CAUSE-{slug(cause)}"
    effect_id = f"EFFECT-{slug(effect)}"
    ca_id = f"CA-{slug(control_action)}"

    session.run("""
        MERGE (c:Component {hasID: $component})
        ON CREATE SET c.hasName = $component

        MERGE (fm:FailureMode {hasID: $fm_id})
        ON CREATE SET fm.hasName = $fm_name
        MERGE (c)-[:hasFailureMode]->(fm)

        MERGE (cause:Cause {hasID: $cause_id})
        ON CREATE SET cause.hasName = $cause_name
        MERGE (fm)-[:causedBy]->(cause)

        MERGE (effect:Effect {hasID: $effect_id})
        ON CREATE SET effect.hasName = $effect_name
        MERGE (fm)-[:causes]->(effect)

        MERGE (ca:ControlAction {hasID: $ca_id})
        ON CREATE SET ca.hasName = $ca_name
        MERGE (fm)-[:mitigatedBy]->(ca)
    """,
        component=component,
        fm_id=fm_id, fm_name=humanize(failure_mode),
        cause_id=cause_id, cause_name=humanize(cause),
        effect_id=effect_id, effect_name=humanize(effect),
        ca_id=ca_id, ca_name=humanize(control_action),
    )


def write_requirement_row(session, component: str, requirement: str):
    session.run("""
        MERGE (c:Component {hasID: $component})
        ON CREATE SET c.hasName = $component
        MERGE (r:Requirement {hasName: $requirement})
        MERGE (c)-[:satisfiesRequirement]->(r)
    """, component=component, requirement=requirement)


# ── Entry point ───────────────────────────────────────────────────────

def extract_failure_modes(path: str, driver, dry_run: bool = False) -> dict:
    print(f"\n📄 {Path(path).name}")

    fm_rows = read_sheet_rows(path, FAILURE_SHEET)
    req_rows = read_sheet_rows(path, REQUIREMENT_SHEET)

    counts = {"components": 0, "failure_modes": 0, "requirement_links": 0, "skipped": 0}
    seen_components = set()

    for row in fm_rows:
        component = str(row.get("Component") or "").strip()
        failure_mode = str(row.get("FailureMode") or "").strip()
        cause = str(row.get("Cause") or "").strip()
        effect = str(row.get("Effect") or "").strip()
        control_action = str(row.get("ControlAction") or "").strip()

        if not (component and failure_mode):
            counts["skipped"] += 1
            continue

        seen_components.add(component)
        counts["failure_modes"] += 1

        if dry_run:
            print(f"  [DRY] {component} -[hasFailureMode]-> {failure_mode} "
                  f"| causedBy={cause} | causes={effect} | mitigatedBy={control_action}")
            continue

        with driver.session() as s:
            write_failure_mode_row(s, component, failure_mode, cause, effect, control_action)

    for row in req_rows:
        component = str(row.get("Component") or "").strip()
        requirement = str(row.get("Requirement") or "").strip()

        if not (component and requirement):
            counts["skipped"] += 1
            continue

        seen_components.add(component)
        counts["requirement_links"] += 1

        if dry_run:
            print(f"  [DRY] {component} -[satisfiesRequirement]-> \"{requirement}\"")
            continue

        with driver.session() as s:
            write_requirement_row(s, component, requirement)

    counts["components"] = len(seen_components)
    print(f"   ✓ Components: {counts['components']} | "
          f"Failure modes: {counts['failure_modes']} | "
          f"Requirement links: {counts['requirement_links']} | "
          f"Skipped: {counts['skipped']}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract brake FMEA data into neo4j")
    parser.add_argument("--file", required=True, help="Path to Brake_System_Failure_Mode_Data.xlsx")
    parser.add_argument("--uri", default="bolt://localhost:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="password")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    driver = None
    if not args.dry_run:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        extract_failure_modes(args.file, driver, dry_run=args.dry_run)
    finally:
        if driver:
            driver.close()
