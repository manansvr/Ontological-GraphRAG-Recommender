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
def get_compliance_gaps(
    project_id: str = None,
    adr_id: str = None,
    assembly_id: str = None,
) -> str:
    """
    Find all applicable requirements that have not yet been verified —
    i.e. ExtractedEssentialRequirement nodes where isApplicable is true
    and isVerified is false or null. Results are grouped by project and
    include the ADR source and requirement name for each gap.

    All filter parameters are optional:
    - project_id:   restrict to a single project (e.g. "SRP8-048")
    - adr_id:       restrict to a single ADR (e.g. "ADR-43")
    - assembly_id:  restrict to all projects in an assembly
                    (e.g. "ASM-STEERING")
    - no filters:   returns all compliance gaps across the entire graph.

    Call this tool proactively when the user asks about any project,
    assembly, or ADR — do not wait to be asked about compliance specifically.
    """
    conditions = [
        "r.isApplicable = true",
        "(r.isVerified = false OR r.isVerified IS NULL)",
    ]
    params: dict = {}

    assembly_clause = ""
    if assembly_id:
        assembly_clause = "-[:belongsToAssembly]->(:Assembly {hasID: $assembly_id})"
        params["assembly_id"] = assembly_id

    if project_id:
        conditions.append("p.projectID = $project_id")
        params["project_id"] = project_id

    if adr_id:
        conditions.append("a.hasID = $adr_id")
        params["adr_id"] = adr_id

    where = " AND ".join(conditions)

    cypher = f"""
        MATCH (a:AustralianDesignRule)
              -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p:Project){assembly_clause}
        WHERE {where}
        RETURN
            p.projectID   AS projectID,
            p.projectName AS projectName,
            count(r)      AS gapCount,
            collect({{
                requirementID:   r.hasID,
                requirementName: r.requirementName,
                adrID:           a.hasID,
                adrName:         a.hasName
            }}) AS gaps
        ORDER BY gapCount DESC
    """

    with _driver.session() as s:
        rows = s.run(cypher, **params).data()

    result = {
        "filters": {
            "project_id":  project_id,
            "adr_id":      adr_id,
            "assembly_id": assembly_id,
        },
        "total_projects_with_gaps": len(rows),
        "total_gaps": sum(r["gapCount"] for r in rows),
        "by_project": _serialise(rows),
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_verification_progress(
    project_id: str = None,
    assembly_id: str = None,
) -> str:
    """
    Return a verification progress summary: total applicable requirements,
    total verified, total unverified, and a completion percentage.

    Filter parameters are optional:
    - project_id:   scope to a single project (e.g. "SRP8-048")
    - assembly_id:  scope to all projects in an assembly
                    (e.g. "ASM-FRONT-AXLE")
    - no filters:   returns graph-wide progress across all projects.

    Call this tool proactively when the user asks about any project,
    assembly, or ADR — do not wait to be asked about compliance specifically.
    """
    conditions = ["r.isApplicable = true"]
    params: dict = {}

    assembly_clause = ""
    if assembly_id:
        assembly_clause = "-[:belongsToAssembly]->(:Assembly {hasID: $assembly_id})"
        params["assembly_id"] = assembly_id

    if project_id:
        conditions.append("p.projectID = $project_id")
        params["project_id"] = project_id

    where = " AND ".join(conditions)

    cypher = f"""
        MATCH (a:AustralianDesignRule)
              -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p:Project){assembly_clause}
        WHERE {where}
        RETURN
            count(r) AS total,
            count(CASE WHEN r.isVerified = true THEN 1 END)                    AS verified,
            count(CASE WHEN r.isVerified = false OR r.isVerified IS NULL
                       THEN 1 END)                                             AS unverified
    """

    with _driver.session() as s:
        row = s.run(cypher, **params).single()

    total      = row["total"]      if row else 0
    verified   = row["verified"]   if row else 0
    unverified = row["unverified"] if row else 0
    pct        = round((verified / total * 100), 1) if total > 0 else 0.0

    result = {
        "filters": {
            "project_id":  project_id,
            "assembly_id": assembly_id,
        },
        "total_applicable":  total,
        "total_verified":    verified,
        "total_unverified":  unverified,
        "completion_pct":    pct,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_highest_risk_gaps() -> str:
    """
    Return the top 10 unverified applicable requirements ranked by the
    number of projects they affect. A requirement assigned to 3 projects
    is higher risk than one assigned to 1.

    Each result includes the ADR source, requirement name, all affected
    project IDs, all affected assembly names, and the project count used
    for ranking.

    Call this tool proactively when the user asks about any project,
    assembly, or ADR — do not wait to be asked about compliance specifically.
    """
    cypher = """
        MATCH (a:AustralianDesignRule)
              -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p:Project)
        WHERE r.isApplicable = true
          AND (r.isVerified = false OR r.isVerified IS NULL)
        OPTIONAL MATCH (p)-[:belongsToAssembly]->(asm:Assembly)
        WITH r, a,
             collect(DISTINCT p.projectID)  AS projects,
             collect(DISTINCT asm.hasName)  AS assemblies
        RETURN
            r.hasID          AS requirementID,
            r.requirementName AS requirementName,
            a.hasID          AS adrID,
            a.hasName        AS adrName,
            projects,
            assemblies,
            size(projects)   AS projectCount
        ORDER BY projectCount DESC
        LIMIT 10
    """

    with _driver.session() as s:
        rows = s.run(cypher).data()

    return json.dumps(_serialise(rows), indent=2)


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
    print(f"  tools     : get_graph_schema",           file=sys.stderr)
    print(f"              query_graph",              file=sys.stderr)
    print(f"              get_compliance_gaps",      file=sys.stderr)
    print(f"              get_verification_progress", file=sys.stderr)
    print(f"              get_highest_risk_gaps",    file=sys.stderr)
    print("─" * 50,                                  file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
