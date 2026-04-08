#!/usr/bin/env python3
"""
test_tools.py
=============
Smoke-tests all MCP tool functions directly against neo4j — no MCP
protocol involved. Each tool is called with representative arguments,
and the result is printed so you can verify it looks correct.

Usage:
  python3 scripts/test_tools.py
  python3 scripts/test_tools.py --uri bolt://localhost:7687 --user neo4j --password password
"""

import argparse
import json
import sys
import textwrap

from neo4j import GraphDatabase

# Inject driver before importing tool functions
import mcp_server


def _banner(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def _print_result(raw: str, max_lines: int = 40):
    lines = raw.splitlines()
    for line in lines[:max_lines]:
        print(f"    {line}")
    if len(lines) > max_lines:
        print(f"    ... ({len(lines) - max_lines} more lines)")


def run_tests(driver):
    mcp_server._driver = driver

    # ── get_graph_schema ─────────────────────────────────────────────
    _banner("get_graph_schema()")
    result = mcp_server.get_graph_schema()
    schema = json.loads(result)
    print(f"  node labels      : {len(schema['node_labels'])}")
    print(f"  relationship types: {len(schema['relationship_types'])}")
    print(f"  label→property groups: {len(schema['properties_by_label'])}")
    print("\n  Top node labels by count:")
    for row in schema["node_labels"][:6]:
        print(f"    {row['label']:45s} {row['count']}")
    print("\n  Relationship types:")
    for row in schema["relationship_types"]:
        print(f"    {row['type']:45s} {row['count']}")

    # ── query_graph — valid query ─────────────────────────────────────
    _banner("query_graph() — ADR requirement counts")
    result = mcp_server.query_graph("""
        MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
        RETURN a.hasID AS adr, count(r) AS requirements
        ORDER BY a.hasID
    """)
    rows = json.loads(result)
    for row in rows:
        print(f"  {row['adr']:12s}  {row['requirements']} requirements")

    # ── query_graph — malformed query ─────────────────────────────────
    _banner("query_graph() — malformed query (error handling)")
    result = mcp_server.query_graph("THIS IS NOT CYPHER !!!!")
    parsed = json.loads(result)
    print(f"  error key present : {'error' in parsed}")
    print(f"  error message     : {parsed.get('error', '')[:80]}")

    # ── get_compliance_gaps — no filter ──────────────────────────────
    _banner("get_compliance_gaps() — all gaps, no filter")
    result = mcp_server.get_compliance_gaps()
    data = json.loads(result)
    print(f"  total gaps                  : {data['total_gaps']}")
    print(f"  projects with gaps          : {data['total_projects_with_gaps']}")
    if data["by_project"]:
        top = data["by_project"][0]
        print(f"  highest-gap project         : {top['projectID']} ({top['gapCount']} gaps)")

    # ── get_compliance_gaps — filtered by ADR ────────────────────────
    _banner("get_compliance_gaps(adr_id='ADR-43')")
    result = mcp_server.get_compliance_gaps(adr_id="ADR-43")
    data = json.loads(result)
    print(f"  ADR-43 gaps                 : {data['total_gaps']}")
    print(f"  ADR-43 projects with gaps   : {data['total_projects_with_gaps']}")

    # ── get_compliance_gaps — filtered by assembly ────────────────────
    _banner("get_compliance_gaps(assembly_id='ASM-STEERING')")
    result = mcp_server.get_compliance_gaps(assembly_id="ASM-STEERING")
    data = json.loads(result)
    print(f"  steering gaps               : {data['total_gaps']}")
    print(f"  steering projects with gaps : {data['total_projects_with_gaps']}")

    # ── get_verification_progress — graph-wide ────────────────────────
    _banner("get_verification_progress() — graph-wide")
    result = mcp_server.get_verification_progress()
    data = json.loads(result)
    print(f"  total applicable  : {data['total_applicable']}")
    print(f"  verified          : {data['total_verified']}")
    print(f"  unverified        : {data['total_unverified']}")
    print(f"  completion        : {data['completion_pct']}%")

    # ── get_verification_progress — by assembly ───────────────────────
    _banner("get_verification_progress(assembly_id='ASM-FRONT-AXLE')")
    result = mcp_server.get_verification_progress(assembly_id="ASM-FRONT-AXLE")
    data = json.loads(result)
    print(f"  front axle applicable : {data['total_applicable']}")
    print(f"  front axle verified   : {data['total_verified']}")
    print(f"  front axle completion : {data['completion_pct']}%")

    # ── get_highest_risk_gaps ─────────────────────────────────────────
    _banner("get_highest_risk_gaps() — top 10 by project count")
    result = mcp_server.get_highest_risk_gaps()
    rows = json.loads(result)
    print(f"  results returned : {len(rows)}")
    print()
    print(f"  {'Rank':<5} {'ADR':<8} {'Projects':<9} {'Requirement'}")
    print(f"  {'────':<5} {'───':<8} {'────────':<9} {'───────────'}")
    for i, row in enumerate(rows, 1):
        name = (row.get("requirementName") or "")[:50]
        print(f"  {i:<5} {row['adrID']:<8} {row['projectCount']:<9} {name}")

    # ── get_cross_assembly_requirements ──────────────────────────────
    _banner("get_cross_assembly_requirements()")
    result = mcp_server.get_cross_assembly_requirements()
    data = json.loads(result)
    print(f"  cross-assembly requirements : {data['total_cross_assembly_requirements']}")
    for req in data["requirements"][:5]:
        assemblies = [c["assemblyID"] for c in req["assemblyCoverage"]]
        name = (req.get("requirementName") or "")[:45]
        print(f"    {req['adrID']:<8} spans {req['assemblyCount']} assemblies"
              f"  {assemblies}  {name}")

    # ── get_assembly_dependencies ─────────────────────────────────────
    for asm in ["ASM-STEERING", "ASM-FRONT-AXLE", "ASM-REAR-AXLE"]:
        _banner(f"get_assembly_dependencies('{asm}')")
        result = mcp_server.get_assembly_dependencies(asm)
        data = json.loads(result)
        print(f"  dependencies found : {data['dependency_count']}")
        for dep in data["dependencies"]:
            print(f"    → {dep['dependencyID']:<20s} {dep['sharedCount']} shared requirements")
            for c in dep["couplings"][:3]:
                name = (c.get("requirementName") or "")[:50]
                print(f"        {c['adrID']:<8} {name}")

    # ── get_shared_requirements ───────────────────────────────────────
    # Use two projects that are likely to share ADR-43 requirements
    _banner("get_shared_requirements('SRP8-047', 'SRP8-043')")
    result = mcp_server.get_shared_requirements("SRP8-047", "SRP8-043")
    data = json.loads(result)
    print(f"  shared requirements : {data['shared_requirement_count']}")
    for req in data["shared_requirements"][:5]:
        name = (req.get("requirementName") or "")[:50]
        print(f"    {req['adrID']:<8} verified={req['isVerified']}  {name}")

    _banner("get_shared_requirements('SRP8-048', 'SRP8-050') — same assembly")
    result = mcp_server.get_shared_requirements("SRP8-048", "SRP8-050")
    data = json.loads(result)
    print(f"  shared requirements : {data['shared_requirement_count']}")
    for req in data["shared_requirements"][:3]:
        name = (req.get("requirementName") or "")[:50]
        print(f"    {req['adrID']:<8} {name}")

    # ── get_interface_risk_report ─────────────────────────────────────
    _banner("get_interface_risk_report()")
    result = mcp_server.get_interface_risk_report()
    data = json.loads(result)
    print(f"  assembly pairs with shared requirements : {data['total_assembly_pairs_with_shared_requirements']}")
    print(f"  total risk items                        : {data['total_risk_items']}")
    for pair in data["pairs"]:
        print(f"\n    {pair['assembly_1']} ↔ {pair['assembly_2']}")
        print(f"      shared: {pair['shared_count']}  risks: {pair['risk_count']}")
        for item in pair["risk_items"][:3]:
            name = (item.get("requirementName") or "")[:45]
            print(f"      ⚠  {item['adrID']:<8} {name}")

    _banner("All tests complete")


def main():
    parser = argparse.ArgumentParser(description="SR8 MCP tool smoke-tester")
    parser.add_argument("--uri",      default="bolt://localhost:7687")
    parser.add_argument("--user",     default="neo4j")
    parser.add_argument("--password", default="password")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session() as s:
            s.run("RETURN 1").single()
    except Exception as exc:
        print(f"ERROR: Cannot connect to neo4j at {args.uri}: {exc}",
              file=sys.stderr)
        sys.exit(1)

    print(f"Connected to neo4j at {args.uri}")

    try:
        run_tests(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
