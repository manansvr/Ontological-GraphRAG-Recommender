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

    # ── get_unassigned_requirements ───────────────────────────────────
    _banner("get_unassigned_requirements()")
    result = mcp_server.get_unassigned_requirements()
    data = json.loads(result)
    print(f"  total unassigned : {data['total_unassigned']}")
    for req in data["requirements"][:5]:
        name = (req.get("requirementName") or "")[:50]
        print(f"    {req['requirementID']:<14} {req['adrID']:<8} {name}")
    if data["total_unassigned"] > 5:
        print(f"    ... ({data['total_unassigned'] - 5} more)")

    # ── get_similar_assigned_requirements ─────────────────────────────
    unassigned_reqs = data["requirements"]
    if unassigned_reqs:
        test_req_id = unassigned_reqs[0]["requirementID"]
        _banner(f"get_similar_assigned_requirements('{test_req_id}')")
        result = mcp_server.get_similar_assigned_requirements(test_req_id)
        sim_data = json.loads(result)
        target = sim_data.get("target_requirement", {})
        print(f"  target : {target.get('requirementID')} — {target.get('requirementName', '')[:50]}")
        print(f"  similar requirements found: {len(sim_data.get('similar_requirements', []))}")
        for s in sim_data.get("similar_requirements", []):
            projects = [p["projectID"] for p in s.get("assignedProjects", []) if p.get("projectID")]
            name = (s.get("requirementName") or "")[:45]
            print(f"    score={s['similarityScore']:.3f}  {s['requirementID']:<14}  "
                  f"projects={projects}  {name}")
    else:
        _banner("get_similar_assigned_requirements() — SKIPPED (no unassigned reqs)")
        print("  All requirements are assigned — nothing to find similarities for.")
        test_req_id = None

    # ── write_inferred_project_link ───────────────────────────────────
    # Write a test inference if we have an unassigned req and similar reqs with projects
    wrote_test_link = False
    test_write_rid  = None
    test_write_pid  = None

    if test_req_id and sim_data.get("similar_requirements"):
        # Pick the first project from the most similar requirement
        top_sim   = sim_data["similar_requirements"][0]
        projects  = [p for p in top_sim.get("assignedProjects", []) if p.get("projectID")]
        if projects:
            test_write_rid = test_req_id
            test_write_pid = projects[0]["projectID"]
            _banner(f"write_inferred_project_link('{test_write_rid}', '{test_write_pid}', ...)")
            result = mcp_server.write_inferred_project_link(
                requirement_id=test_write_rid,
                project_id=test_write_pid,
                confidence=top_sim["similarityScore"],
                reasoning=f"Test inference: similar to {top_sim['requirementID']}",
            )
            write_data = json.loads(result)
            wrote_test_link = write_data.get("written", False)
            print(f"  written      : {write_data.get('written')}")
            print(f"  requirementID: {write_data.get('requirementID')}")
            print(f"  projectID    : {write_data.get('projectID')}")
            print(f"  confidence   : {write_data.get('confidence')}")
            print(f"  inferredAt   : {write_data.get('inferredAt')}")

            # Test bad confidence value
            _banner("write_inferred_project_link() — invalid confidence (error handling)")
            bad_result = json.loads(mcp_server.write_inferred_project_link(
                test_write_rid, test_write_pid, 1.5, "should fail"
            ))
            print(f"  error returned : {'error' in bad_result}")
            print(f"  message        : {bad_result.get('error', '')}")
        else:
            _banner("write_inferred_project_link() — SKIPPED (no projects on similar reqs)")
    else:
        _banner("write_inferred_project_link() — SKIPPED (no unassigned reqs)")

    # ── get_inferred_links ────────────────────────────────────────────
    _banner("get_inferred_links()")
    result = mcp_server.get_inferred_links()
    inf_data = json.loads(result)
    print(f"  total inferred links : {inf_data['total_inferred_links']}")
    for link in inf_data["links"][:5]:
        print(f"    {link['requirementID']:<14} → {link['projectID']:<12} "
              f"conf={link['confidence']:.2f}  by={link['inferredBy']}")

    # ── promote_inferred_link ─────────────────────────────────────────
    # Only promote if we just wrote a test link
    if wrote_test_link and test_write_rid and test_write_pid:
        _banner(f"promote_inferred_link('{test_write_rid}', '{test_write_pid}')")
        result = mcp_server.promote_inferred_link(test_write_rid, test_write_pid)
        prom_data = json.loads(result)
        print(f"  promoted           : {prom_data.get('promoted')}")
        print(f"  requirementID      : {prom_data.get('requirementID')}")
        print(f"  projectID          : {prom_data.get('projectID')}")
        print(f"  promotedAt         : {prom_data.get('promotedAt')}")
        print(f"  originalConfidence : {prom_data.get('originalConfidence')}")

        # Verify it's gone from inferred links
        after_raw  = mcp_server.get_inferred_links()
        after_data = json.loads(after_raw)
        still_inferred = any(
            l["requirementID"] == test_write_rid and l["projectID"] == test_write_pid
            for l in after_data["links"]
        )
        print(f"  still in suggestedProject after promote : {still_inferred} (expect False)")

        # Test promoting something that doesn't exist
        _banner("promote_inferred_link() — missing link (error handling)")
        bad_result = json.loads(mcp_server.promote_inferred_link("REQ-99-999", "SRP8-999"))
        print(f"  error returned : {'error' in bad_result}")
        print(f"  message        : {bad_result.get('error', '')[:80]}")
    else:
        _banner("promote_inferred_link() — SKIPPED (no test link was written)")

    # ── get_requirements_by_keyword ───────────────────────────────────
    for kw in ["steering", "brake", "wheel"]:
        _banner(f"get_requirements_by_keyword('{kw}')")
        result = mcp_server.get_requirements_by_keyword(kw)
        data = json.loads(result)
        req_count    = data["requirement_matches"]["count"]
        clause_count = data["clause_matches"]["count"]
        print(f"  requirement matches : {req_count}")
        print(f"  clause matches      : {clause_count}")
        for req in data["requirement_matches"]["results"][:3]:
            name = (req.get("requirementName") or "")[:50]
            print(f"    {req['requirementID']:<14} {req['adrID']:<8} {name}")
        if req_count == 0 and clause_count == 0:
            print(f"  (no matches — keyword '{kw}' not found in graph)")

    # ── get_requirement_chain ─────────────────────────────────────────
    # Fetch a real requirement ID to test with
    chain_test_id = None
    with driver.session() as s:
        row = s.run("""
            MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->()
            RETURN r.hasID AS rid LIMIT 1
        """).single()
        if row:
            chain_test_id = row["rid"]

    if chain_test_id:
        _banner(f"get_requirement_chain('{chain_test_id}')")
        result = mcp_server.get_requirement_chain(chain_test_id)
        data = json.loads(result)
        chain = data["chain"]
        print(f"  ADR        : {chain['adr']['adrID']} — {chain['adr']['adrName']}")
        print(f"  Requirement: {chain['requirement']['requirementID']}")
        print(f"               {(chain['requirement']['requirementName'] or '')[:60]}")
        print(f"  Projects   : {[p['projectID'] for p in chain['projects_and_assemblies'] if p.get('projectID')]}")
        print(f"  Assemblies : {list({p['assemblyID'] for p in chain['projects_and_assemblies'] if p.get('assemblyID')})}")
        print(f"  ADR clauses for context: {data['adr_clauses_for_context']['count']}")
    else:
        _banner("get_requirement_chain() — SKIPPED (no assigned requirements found)")

    _banner("get_requirement_chain() — missing requirement (error handling)")
    result = mcp_server.get_requirement_chain("REQ-99-999")
    data = json.loads(result)
    print(f"  error returned : {'error' in data}")
    print(f"  message        : {data.get('error', '')[:80]}")

    # ── get_reverification_scope ──────────────────────────────────────
    # Test with projects from the front axle assembly
    test_project_ids = ["SRP8-043", "SRP8-045", "SRP8-050", "SRP8-088"]
    _banner(f"get_reverification_scope({test_project_ids})")
    result = mcp_server.get_reverification_scope(test_project_ids)
    data = json.loads(result)
    summary = data["summary"]
    print(f"  total requirements in scope : {summary['total']}")
    print(f"  must re-verify              : {summary['must_reverify_count']}")
    print(f"  must verify                 : {summary['must_verify_count']}")
    print(f"  not affected                : {summary['not_affected_count']}")
    for req in data["must_reverify"][:3]:
        print(f"    RE-VERIFY  {req['requirementID']:<14} {req['adrID']:<8} {(req.get('requirementName') or '')[:40]}")
    for req in data["must_verify"][:3]:
        print(f"    VERIFY     {req['requirementID']:<14} {req['adrID']:<8} {(req.get('requirementName') or '')[:40]}")

    _banner("get_reverification_scope([]) — empty list")
    result = mcp_server.get_reverification_scope([])
    data = json.loads(result)
    print(f"  total : {data['summary']['total']} (expect 0)")

    # ── write_change_impact_report ────────────────────────────────────
    _banner("write_change_impact_report()")
    # Use real requirement and project IDs from the graph
    test_req_ids  = [r["requirementID"] for r in
                     json.loads(mcp_server.get_compliance_gaps(
                         assembly_id="ASM-STEERING"))["by_project"][:1]
                     ] if True else []
    # Simpler: just use a couple of known project IDs for the test
    test_cir_proj = ["SRP8-047", "SRP8-048"]
    test_cir_reqs = []
    with driver.session() as s:
        rows = s.run("""
            MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->(p:Project)
            WHERE p.projectID IN $pids
            RETURN r.hasID AS rid LIMIT 3
        """, pids=test_cir_proj).data()
        test_cir_reqs = [r["rid"] for r in rows]

    result = mcp_server.write_change_impact_report(
        change_description="Test: steering rack geometry change — increased toe angle by 2°",
        affected_requirement_ids=test_cir_reqs,
        affected_project_ids=test_cir_proj,
        risk_summary="Test report: ADR-43 braking requirements may need re-verification.",
    )
    cir_data = json.loads(result)
    print(f"  written        : {cir_data.get('written')}")
    print(f"  reportID       : {cir_data.get('reportID')}")
    print(f"  affected reqs  : {cir_data.get('affected_requirements')}")
    print(f"  affected proj  : {cir_data.get('affected_projects')}")
    test_report_id = cir_data.get("reportID")

    # ── get_change_impact_reports ─────────────────────────────────────
    _banner("get_change_impact_reports()")
    result = mcp_server.get_change_impact_reports()
    data = json.loads(result)
    print(f"  total reports : {data['total_reports']}")
    for rpt in data["reports"][:3]:
        desc = (rpt.get("changeDescription") or "")[:55]
        print(f"    {rpt['reportID']}  reqs={len(rpt['affectedRequirements'])}"
              f"  proj={len(rpt['affectedProjects'])}  {desc}")
    # Verify our test report appears
    ids = [r["reportID"] for r in data["reports"]]
    print(f"  test report present : {test_report_id in ids} (expect True)")

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
