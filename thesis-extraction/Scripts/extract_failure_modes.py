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

Provenance: FailureMode nodes store sourceFile, sourceSheet ("Failure Mode Data") and
sourceRows (workbook row numbers, header = row 1); satisfiesRequirement edges store
sourceFile, sourceSheet ("Requirement Mapping") and sourceRow.

A Cause, Effect or ControlAction cell that is empty or a placeholder (none, n/a, na, -, tbc)
creates no node and no edge, so a failure mode without a control action has no
mitigatedBy relationship (sr8-mcp's get_unmitigated_failure_modes relies on this).

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
MISSING_VALUES = {"", "none", "n/a", "na", "-", "tbc"}


def present(value: str) -> bool:
    """False for an empty cell or a placeholder meaning "no value" (MISSING_VALUES)."""
    return str(value or "").strip().lower() not in MISSING_VALUES


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
    for row_number, row in enumerate(rows[1:], start=2):   # workbook row numbers; header is row 1
        record = {headers[i]: row[i] for i in range(len(headers)) if i < len(row)}
        if any(v not in (None, "") for v in record.values()):
            record["_row"] = row_number
            out.append(record)
    return out


# ── Writers ───────────────────────────────────────────────────────────

def write_failure_mode_row(session, component: str, failure_mode: str,
                            cause: str, effect: str, control_action: str,
                            source_file: str = "", source_row: int = 0):
    """Write one Failure Mode Data row. Cause / Effect / ControlAction are only linked when present()."""
    fm_id = f"FM-{component}-{slug(failure_mode)}"
    session.run("""
        MERGE (c:Component {hasID: $component})
        ON CREATE SET c.hasName = $component

        MERGE (fm:FailureMode {hasID: $fm_id})
        ON CREATE SET fm.hasName = $fm_name
        SET fm.sourceFile  = $source_file,
            fm.sourceSheet = $sheet,
            fm.sourceRows  = CASE WHEN $row IN coalesce(fm.sourceRows, []) THEN fm.sourceRows
                                  ELSE coalesce(fm.sourceRows, []) + $row END
        MERGE (c)-[:hasFailureMode]->(fm)
    """,
        component=component, fm_id=fm_id, fm_name=humanize(failure_mode),
        source_file=source_file, sheet=FAILURE_SHEET, row=source_row,
    )
    linked = [("Cause", "CAUSE", "causedBy", cause),
              ("Effect", "EFFECT", "causes", effect),
              ("ControlAction", "CA", "mitigatedBy", control_action)]
    for label, prefix, rel, value in linked:
        if not present(value):
            continue
        session.run(f"""
            MATCH (fm:FailureMode {{hasID: $fm_id}})
            MERGE (n:{label} {{hasID: $node_id}})
            ON CREATE SET n.hasName = $node_name
            MERGE (fm)-[:{rel}]->(n)
        """, fm_id=fm_id, node_id=f"{prefix}-{slug(value)}", node_name=humanize(value))


def write_requirement_row(session, component: str, requirement: str,
                          source_file: str = "", source_row: int = 0):
    session.run("""
        MERGE (c:Component {hasID: $component})
        ON CREATE SET c.hasName = $component
        MERGE (r:Requirement {hasName: $requirement})
        MERGE (c)-[rel:satisfiesRequirement]->(r)
        SET rel.sourceFile = $source_file, rel.sourceSheet = $sheet, rel.sourceRow = $row
    """, component=component, requirement=requirement,
         source_file=source_file, sheet=REQUIREMENT_SHEET, row=source_row)


# ── Entry point ───────────────────────────────────────────────────────

def extract_failure_modes(path: str, driver, dry_run: bool = False) -> dict:
    print(f"\n📄 {Path(path).name}")

    fm_rows = read_sheet_rows(path, FAILURE_SHEET)
    req_rows = read_sheet_rows(path, REQUIREMENT_SHEET)

    counts = {"components": 0, "failure_modes": 0, "requirement_links": 0, "skipped": 0,
              "without_control_action": 0}
    seen_components = set()
    source_file = Path(path).name
    failure_modes: dict = {}   # (component, failure mode) -> has a control action on any row

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
        key = (component, failure_mode)
        failure_modes[key] = failure_modes.get(key, False) or present(control_action)

        if dry_run:
            mitigation = control_action if present(control_action) else "(none: no mitigatedBy)"
            print(f"  [DRY] {component} -[hasFailureMode]-> {failure_mode} "
                  f"| causedBy={cause} | causes={effect} | mitigatedBy={mitigation} | row {row['_row']}")
            continue

        with driver.session() as s:
            write_failure_mode_row(s, component, failure_mode, cause, effect, control_action,
                                   source_file, row["_row"])

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
            write_requirement_row(s, component, requirement, source_file, row["_row"])

    counts["components"] = len(seen_components)
    counts["distinct_failure_modes"] = len(failure_modes)
    counts["without_control_action"] = sum(1 for mitigated in failure_modes.values() if not mitigated)
    print(f"   ✓ Components: {counts['components']} | "
          f"Failure mode rows: {counts['failure_modes']} "
          f"({counts['distinct_failure_modes']} distinct, "
          f"{counts['without_control_action']} without a control action) | "
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
