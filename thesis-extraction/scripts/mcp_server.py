#!/usr/bin/env python3
"""
mcp_server.py
=============
MCP server — exposes the SR8 neo4j knowledge graph as tools that Claude
can call autonomously via the Model Context Protocol.

Transport: stdio (works with Claude Desktop and claude CLI)

Usage:
  python3 scripts/mcp_server.py
  python3 scripts/mcp_server.py --uri bolt://localhost:7687 --user neo4j --password password
"""

import argparse
import json
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from neo4j.graph import Node, Relationship, Path

# ── Module-level driver (set in main() before server starts) ──────────
_driver = None

# ── MCP server instance ───────────────────────────────────────────────
mcp = FastMCP("sr8-knowledge-graph")


# ── neo4j type serialiser ─────────────────────────────────────────────

def _serialise(obj: Any) -> Any:
    """Recursively convert neo4j types to JSON-serialisable Python types."""
    if isinstance(obj, Node):
        return {"_labels": list(obj.labels), **dict(obj)}
    if isinstance(obj, Relationship):
        return {"_type": obj.type, **dict(obj)}
    if isinstance(obj, Path):
        return {
            "nodes":         [_serialise(n) for n in obj.nodes],
            "relationships": [_serialise(r) for r in obj.relationships],
        }
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(i) for i in obj]
    return obj


# ── Tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_graph_schema() -> str:
    """
    Query neo4j and return the live schema of the SR8 knowledge graph:
    all node labels with counts, all relationship types with counts,
    and all property keys per label.

    Always reflects the current state of the graph — never hardcoded.
    Call this first to orient yourself before writing Cypher queries.
    """
    with _driver.session() as s:
        label_rows = s.run("""
            MATCH (n)
            UNWIND labels(n) AS label
            RETURN label, count(n) AS count
            ORDER BY count DESC
        """).data()

        rel_rows = s.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            ORDER BY count DESC
        """).data()

        prop_rows = s.run("""
            CALL db.schema.nodeTypeProperties()
            YIELD nodeLabels, propertyName
            RETURN nodeLabels, collect(propertyName) AS properties
            ORDER BY nodeLabels
        """).data()

    schema = {
        "node_labels": label_rows,
        "relationship_types": rel_rows,
        "properties_by_label": [
            {
                "labels":     r["nodeLabels"],
                "properties": sorted(r["properties"]),
            }
            for r in prop_rows
        ],
    }
    return json.dumps(schema, indent=2)


@mcp.tool()
def query_graph(cypher: str) -> str:
    """
    Execute any Cypher query against the SR8 neo4j knowledge graph
    and return the results as a JSON string.

    Malformed or invalid queries return a descriptive error message
    rather than crashing the server.

    Args:
        cypher: A valid Cypher query string, e.g.
                'MATCH (a:AustralianDesignRule) RETURN a.hasID, a.hasName'
    """
    try:
        with _driver.session() as s:
            records = s.run(cypher).data()
        serialised = [_serialise(r) for r in records]
        return json.dumps(serialised, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "query": cypher}, indent=2)


# ── Entry point ───────────────────────────────────────────────────────

def main():
    global _driver

    parser = argparse.ArgumentParser(description="SR8 MCP Server")
    parser.add_argument("--uri",      default="bolt://localhost:7687",
                        help="neo4j bolt URI (default: bolt://localhost:7687)")
    parser.add_argument("--user",     default="neo4j",
                        help="neo4j username (default: neo4j)")
    parser.add_argument("--password", default="password",
                        help="neo4j password (default: password)")
    args = parser.parse_args()

    _driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    # Verify connection before starting the server
    try:
        with _driver.session() as s:
            s.run("RETURN 1").single()
    except Exception as exc:
        print(f"ERROR: Cannot connect to neo4j at {args.uri}: {exc}",
              file=sys.stderr)
        sys.exit(1)

    # Startup message — printed to stderr so it doesn't interfere with
    # the MCP stdio protocol on stdout
    print("─" * 50,                                  file=sys.stderr)
    print("SR8 Knowledge Graph — MCP Server",        file=sys.stderr)
    print(f"  neo4j     : {args.uri}",               file=sys.stderr)
    print(f"  transport : stdio",                    file=sys.stderr)
    print(f"  tools     : get_graph_schema",         file=sys.stderr)
    print(f"              query_graph",              file=sys.stderr)
    print("─" * 50,                                  file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
