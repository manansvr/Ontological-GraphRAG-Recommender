#!/usr/bin/env python3
"""export-confirmed-links.py: export human-confirmed project links before a graph rebuild.

Writes every assignedToProject relationship that has promotedBy set to a CSV. That covers
links promoted by the old promote_inferred_link (promotedBy = 'human-review') and by the
current one (promotedBy = the reviewer's name). Extracted links have no promotedBy and are
recreated by extract-ADR.py, so they are not exported.

The script only reads from Neo4j (read-access session).

Usage:
    python3 scripts/export-confirmed-links.py
    python3 scripts/export-confirmed-links.py --output confirmed-links.csv
    python3 scripts/export-confirmed-links.py --uri bolt://localhost:7687 --user neo4j --password ...

Connection settings default to NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD from
thesis-extension/.env, matching sr8-mcp.
"""

import argparse
import csv
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase, READ_ACCESS

EXTENSION_DIR = Path(__file__).resolve().parent.parent

FIELDS = [
    "requirement_id",
    "project_id",
    "promoted_by",
    "promoted_at",
    "promoted_from_confidence",
    "source",
]

QUERY = """
MATCH (r)-[a:assignedToProject]->(p:Project)
WHERE a.promotedBy IS NOT NULL
RETURN r.hasID AS requirement_id,
       p.projectID AS project_id,
       a.promotedBy AS promoted_by,
       toString(a.promotedAt) AS promoted_at,
       a.promotedFromConfidence AS promoted_from_confidence,
       a.source AS source
ORDER BY requirement_id, project_id
"""


def main() -> None:
    load_dotenv(EXTENSION_DIR / ".env")
    parser = argparse.ArgumentParser(description="Export human-confirmed assignedToProject links to CSV")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "password"))
    parser.add_argument(
        "--output",
        default=f"confirmed-links-{date.today().isoformat()}.csv",
        help="CSV file to write (default: confirmed-links-<today>.csv in the current directory)",
    )
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session(default_access_mode=READ_ACCESS) as session:
            rows = [record.data() for record in session.run(QUERY)]
    finally:
        driver.close()

    output = Path(args.output)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    legacy = sum(1 for r in rows if r["promoted_by"] == "human-review")
    print(f"Wrote {len(rows)} confirmed link(s) to {output} ({legacy} from the old promote_inferred_link).")


if __name__ == "__main__":
    main()
