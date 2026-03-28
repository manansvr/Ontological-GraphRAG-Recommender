#!/usr/bin/env python3
"""
run_extraction.py
==================
Master script — runs all extractors in dependency order:
  1. ADRs     — data/adrs/*.csv
  2. Projects — data/project-tracking-system.csv  (export xlsx first)
  3. Parts    — data/parts-management.csv          (export xlsx first)

Usage:
  python scripts/run_extraction.py --only adrs             # just ADRs
  python scripts/run_extraction.py --only adrs --dry-run   # preview ADRs
  python scripts/run_extraction.py                         # everything
  python scripts/run_extraction.py --dry-run               # preview all
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j import GraphDatabase
from extract_adrs     import extract_adrs
from extract_projects import extract_projects
from extract_parts    import extract_parts

# ── File paths — matches your repo structure ─────────────────────────
DEFAULTS = {
    "adrs_folder":   "data/adrs",                        # all ADR CSVs
    "projects_file": "data/project-tracking-system.csv", # export xlsx → csv
    "parts_file":    "data/parts-management.csv",        # export xlsx → csv
}


def main():
    parser = argparse.ArgumentParser(description="SR8 Extraction Pipeline")
    parser.add_argument("--uri",           default="bolt://localhost:7687")
    parser.add_argument("--user",          default="neo4j")
    parser.add_argument("--password",      default="password")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Preview without writing to neo4j")
    parser.add_argument("--only",          choices=["adrs", "projects", "parts"],
                        help="Run only one extractor")
    parser.add_argument("--adrs-folder",   default=DEFAULTS["adrs_folder"])
    parser.add_argument("--projects-file", default=DEFAULTS["projects_file"])
    parser.add_argument("--parts-file",    default=DEFAULTS["parts_file"])
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

        # ── 2. Projects ───────────────────────────────────────────────
        if not args.only or args.only == "projects":
            if os.path.exists(args.projects_file):
                extract_projects(
                    args.projects_file,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"  ⚠️  Projects file not found: {args.projects_file}")
                print(f"      Export project-tracing-system.xlsx → CSV first")

        # ── 3. Parts ─────────────────────────────────────────────────
        if not args.only or args.only == "parts":
            if os.path.exists(args.parts_file):
                extract_parts(
                    args.parts_file,
                    driver=driver,
                    dry_run=args.dry_run,
                )
            else:
                print(f"  ⚠️  Parts file not found: {args.parts_file}")
                print(f"      Export parts-management.xlsx → CSV first")

    finally:
        if driver:
            driver.close()

    print("\n" + "=" * 60)
    print("✅ DONE")
    print("=" * 60)

    if not args.dry_run:
        print("""
  Verify in neo4j Browser → http://localhost:7474

  // All node types
  MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
  ORDER BY count DESC

  // ADRs and their linked projects
  MATCH (a:AustralianDesignRule)-[:assignedToProject]->(p:Project)
  RETURN a.hasID, collect(distinct p.projectID) AS projects
  ORDER BY a.hasID

  // Full chain: ADR → Clause → linked project
  MATCH (a:AustralianDesignRule)-[:hasClause]->(c:Clause)
  OPTIONAL MATCH (a)-[:assignedToProject]->(p:Project)
  RETURN a.hasID, c.hasName AS clause, p.projectID
  ORDER BY a.hasID, clause
  LIMIT 30
        """)


if __name__ == "__main__":
    main()