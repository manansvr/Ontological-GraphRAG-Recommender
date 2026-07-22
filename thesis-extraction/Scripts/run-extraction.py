#!/usr/bin/env python3
"""
run-extraction.py
=================
Master script — runs extractors in dependency order.

Usage:
    python3 Scripts/run-extraction.py --only adrs --dry-run
    python3 Scripts/run-extraction.py --only adrs
    python3 Scripts/run-extraction.py --dry-run
    python3 Scripts/run-extraction.py
"""

import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j import GraphDatabase


def load_extract_adrs_function():
    # Load the ADR extractor from file because the script name contains a hyphen.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    module_path = os.path.join(script_dir, "extract-ADR.py")
    spec = importlib.util.spec_from_file_location("extract_adr_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract_adrs

DEFAULTS = {
    "adrs_folder":   "csv",
    "projects_file": "data/project-tracking-system.csv",
    "parts_file":    "data/parts-management.csv",
    "failure_modes_file": "Brake_System_Failure_Mode_Data.xlsx",
}


def main():
    extract_adrs = load_extract_adrs_function()

    parser = argparse.ArgumentParser(description="SR8 Extraction Pipeline")
    parser.add_argument("--uri",           default="bolt://localhost:7687")
    parser.add_argument("--user",          default="neo4j")
    parser.add_argument("--password",      default="password")
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("--only",          choices=["adrs", "projects", "parts", "failure-modes"])
    parser.add_argument("--adrs-folder",   default=DEFAULTS["adrs_folder"])
    parser.add_argument("--projects-file", default=DEFAULTS["projects_file"])
    parser.add_argument("--parts-file",    default=DEFAULTS["parts_file"])
    parser.add_argument("--failure-modes-file", default=DEFAULTS["failure_modes_file"])
    args = parser.parse_args()

    print("=" * 60)
    print("SR8 KNOWLEDGE EXTRACTION — CSV PIPELINE")
    print("=" * 60)
    if args.dry_run:
        print("  MODE: DRY RUN — nothing written to neo4j\n")

    driver = None
    if not args.dry_run:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        print(f"  Connected: {args.uri}\n")

    try:
        # ── 1. ADRs ──────────────────────────────────────────────────
        if not args.only or args.only == "adrs":
            if os.path.isdir(args.adrs_folder):
                extract_adrs(
                    folder=args.adrs_folder,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"  ⚠️  ADR folder not found: {args.adrs_folder}")
                print(f"      Expected: {os.path.abspath(args.adrs_folder)}")

        # ── 2. Projects (export xlsx → csv first) ─────────────────────
        if not args.only or args.only == "projects":
            if os.path.exists(args.projects_file):
                from extract_projects import extract_projects   
                extract_projects(
                    args.projects_file,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"\n  ⚠️  Projects file not found: {args.projects_file}")
                print(f"      Export project-tracing-system.xlsx → CSV first")

        # ── 3. Parts (export xlsx → csv first) ────────────────────────
        if not args.only or args.only == "parts":
            if os.path.exists(args.parts_file):
                from extract_parts import extract_parts         
                extract_parts(
                    args.parts_file,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"\n  ⚠️  Parts file not found: {args.parts_file}")
                print(f"      Export parts-management.xlsx → CSV first")

        # ── 4. Failure modes (FMEA data from xlsx) ─────────────────────
        if not args.only or args.only == "failure-modes":
            if os.path.exists(args.failure_modes_file):
                from extract_failure_modes import extract_failure_modes
                extract_failure_modes(
                    args.failure_modes_file,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"\n  ⚠️  Failure mode file not found: {args.failure_modes_file}")

    finally:
        if driver:
            driver.close()

    print("\n" + "=" * 60)
    print("✅ DONE")
    print("=" * 60)

    if not args.dry_run:
        print("""
  Verify in neo4j Browser → http://localhost:7474

  // All node types and counts
  MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
  ORDER BY count DESC

  // ADRs linked to Projects
  MATCH (a:AustralianDesignRule)-[:assignedToProject]->(p:Project)
  RETURN a.hasID, collect(distinct p.projectID) AS projects
  ORDER BY a.hasID

  // ADR → Clause count
  MATCH (a:AustralianDesignRule)-[:hasClause]->(c:Clause)
  RETURN a.hasID, count(c) AS clauses
  ORDER BY a.hasID
        """)


if __name__ == "__main__":
    main()