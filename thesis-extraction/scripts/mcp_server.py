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
def get_cross_assembly_requirements() -> str:
    """
    Find all ExtractedEssentialRequirement nodes that are assigned to
    projects in more than one assembly. These are the regulatory couplings
    between engineering teams — requirements that cross assembly boundaries
    and therefore demand coordination.

    For each cross-assembly requirement returns: ADR source, requirement
    name, and for each affected assembly the assembly ID, name, and the
    list of projects within it that carry the requirement.

    Results are ordered by number of assemblies affected (descending),
    then by ADR.

    Call this tool when the user asks about interfaces, dependencies,
    coordination between teams, or risks between assemblies.
    """
    cypher = """
        MATCH (a:AustralianDesignRule)
              -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p:Project)
              -[:belongsToAssembly]->(asm:Assembly)
        WITH r, a, asm.hasID AS asmID, asm.hasName AS asmName,
             collect(DISTINCT p.projectID) AS projectsInAssembly
        WITH r, a,
             collect({
                 assemblyID:   asmID,
                 assemblyName: asmName,
                 projects:     projectsInAssembly,
                 projectCount: size(projectsInAssembly)
             }) AS assemblyCoverage,
             count(DISTINCT asmID) AS assemblyCount
        WHERE assemblyCount > 1
        RETURN
            r.hasID           AS requirementID,
            r.requirementName AS requirementName,
            r.isVerified      AS isVerified,
            a.hasID           AS adrID,
            a.hasName         AS adrName,
            assemblyCoverage,
            assemblyCount
        ORDER BY assemblyCount DESC, a.hasID
    """

    with _driver.session() as s:
        rows = s.run(cypher).data()

    return json.dumps({
        "total_cross_assembly_requirements": len(rows),
        "requirements": _serialise(rows),
    }, indent=2)


@mcp.tool()
def get_assembly_dependencies(assembly_id: str) -> str:
    """
    For a given assembly, return all other assemblies it shares
    requirements with. For each dependency, lists the specific
    requirements that create the coupling and which ADR they come from.
    This maps the full interface risk landscape for a single assembly.

    Args:
        assembly_id: The assembly to analyse, e.g. "ASM-STEERING",
                     "ASM-FRONT-AXLE", or "ASM-REAR-AXLE".

    Call this tool when the user asks about interfaces, dependencies,
    coordination between teams, or risks between assemblies.
    """
    cypher = """
        MATCH (target:Assembly {hasID: $aid})
              <-[:belongsToAssembly]-(p1:Project)
              <-[:assignedToProject]-(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p2:Project)
              -[:belongsToAssembly]->(other:Assembly)
        WHERE other.hasID <> $aid
        MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
        WITH other, r, a,
             collect(DISTINCT p1.projectID) AS selfProjects,
             collect(DISTINCT p2.projectID) AS otherProjects
        RETURN
            other.hasID   AS dependencyID,
            other.hasName AS dependencyName,
            count(DISTINCT r) AS sharedCount,
            collect({
                requirementID:   r.hasID,
                requirementName: r.requirementName,
                adrID:           a.hasID,
                adrName:         a.hasName,
                isVerified:      r.isVerified,
                selfProjects:    selfProjects,
                otherProjects:   otherProjects
            }) AS couplings
        ORDER BY sharedCount DESC
    """

    with _driver.session() as s:
        rows = s.run(cypher, aid=assembly_id).data()

    return json.dumps({
        "assembly": assembly_id,
        "dependency_count": len(rows),
        "dependencies": _serialise(rows),
    }, indent=2)


@mcp.tool()
def get_shared_requirements(project_id_1: str, project_id_2: str) -> str:
    """
    Given two project IDs, find all requirements they both need to
    satisfy. Returns requirement names, ADR sources, verification status,
    and which assembly each project belongs to.

    Use this to understand what two projects have in common regulatorily
    and whether their shared obligations are being tracked consistently.

    Args:
        project_id_1: First project ID, e.g. "SRP8-048"
        project_id_2: Second project ID, e.g. "SRP8-043"

    Call this tool when the user asks about interfaces, dependencies,
    coordination between teams, or risks between assemblies.
    """
    cypher = """
        MATCH (p1:Project {projectID: $pid1})
              <-[:assignedToProject]-(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p2:Project {projectID: $pid2})
        MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
        OPTIONAL MATCH (p1)-[:belongsToAssembly]->(asm1:Assembly)
        OPTIONAL MATCH (p2)-[:belongsToAssembly]->(asm2:Assembly)
        RETURN
            r.hasID           AS requirementID,
            r.requirementName AS requirementName,
            r.isApplicable    AS isApplicable,
            r.isVerified      AS isVerified,
            a.hasID           AS adrID,
            a.hasName         AS adrName,
            asm1.hasID        AS project1Assembly,
            asm2.hasID        AS project2Assembly
        ORDER BY a.hasID, r.hasID
    """

    with _driver.session() as s:
        rows = s.run(cypher, pid1=project_id_1, pid2=project_id_2).data()

    return json.dumps({
        "project_1": project_id_1,
        "project_2": project_id_2,
        "shared_requirement_count": len(rows),
        "shared_requirements": _serialise(rows),
    }, indent=2)


@mcp.tool()
def get_interface_risk_report() -> str:
    """
    Produce a full interface risk report across all assembly pairs.

    For each pair of assemblies that share at least one requirement:
    - Lists every shared requirement and the ADR it comes from
    - Reports verification status
    - Flags any unverified cross-assembly requirement as a risk, because
      an unverified obligation that spans two engineering teams requires
      active coordination to close

    Results are grouped by assembly pair. Risk items are surfaced
    separately for easy scanning.

    Call this tool when the user asks about interfaces, dependencies,
    coordination between teams, or risks between assemblies.
    """
    cypher = """
        MATCH (asm1:Assembly)<-[:belongsToAssembly]-(p1:Project)
              <-[:assignedToProject]-(r:ExtractedEssentialRequirement)
              -[:assignedToProject]->(p2:Project)
              -[:belongsToAssembly]->(asm2:Assembly)
        WHERE asm1.hasID < asm2.hasID
        MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
        RETURN
            asm1.hasID        AS asm1ID,
            asm1.hasName      AS asm1Name,
            asm2.hasID        AS asm2ID,
            asm2.hasName      AS asm2Name,
            r.hasID           AS requirementID,
            r.requirementName AS requirementName,
            r.isVerified      AS isVerified,
            a.hasID           AS adrID,
            a.hasName         AS adrName,
            collect(DISTINCT p1.projectID) AS asm1Projects,
            collect(DISTINCT p2.projectID) AS asm2Projects
        ORDER BY asm1.hasID, asm2.hasID, a.hasID
    """

    with _driver.session() as s:
        rows = s.run(cypher).data()

    # Group by assembly pair in Python
    pairs: dict = {}
    for row in rows:
        key = (row["asm1ID"], row["asm2ID"])
        if key not in pairs:
            pairs[key] = {
                "assembly_1":       row["asm1ID"],
                "assembly_1_name":  row["asm1Name"],
                "assembly_2":       row["asm2ID"],
                "assembly_2_name":  row["asm2Name"],
                "shared_requirements": [],
                "risk_items":          [],
            }
        is_verified = row["isVerified"]
        is_risk     = (is_verified is False) or (is_verified is None)
        entry = {
            "requirementID":   row["requirementID"],
            "requirementName": row["requirementName"],
            "adrID":           row["adrID"],
            "adrName":         row["adrName"],
            "isVerified":      is_verified,
            "asm1Projects":    row["asm1Projects"],
            "asm2Projects":    row["asm2Projects"],
            "isRisk":          is_risk,
        }
        pairs[key]["shared_requirements"].append(entry)
        if is_risk:
            pairs[key]["risk_items"].append(entry)

    report = []
    total_risks = 0
    for pair in pairs.values():
        pair["shared_count"] = len(pair["shared_requirements"])
        pair["risk_count"]   = len(pair["risk_items"])
        total_risks += pair["risk_count"]
        report.append(pair)

    return json.dumps({
        "total_assembly_pairs_with_shared_requirements": len(report),
        "total_risk_items": total_risks,
        "pairs": report,
    }, indent=2)


@mcp.tool()
def get_unassigned_requirements() -> str:
    """
    Return all ExtractedEssentialRequirement nodes that have no
    assignedToProject relationship. These are the gaps in the current
    graph — requirements extracted from ADRs that have not yet been
    mapped to a responsible project.

    For each unassigned requirement returns: requirement ID, name,
    description, ADR source, and applicability status.

    Call this tool when the user asks about gaps in the graph, missing
    assignments, or wants to extend the knowledge base.
    """
    cypher = """
        MATCH (a:AustralianDesignRule)
              -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
        WHERE NOT (r)-[:assignedToProject]->()
        RETURN
            r.hasID                  AS requirementID,
            r.requirementName        AS requirementName,
            r.requirementDescription AS requirementDescription,
            r.isApplicable           AS isApplicable,
            a.hasID                  AS adrID,
            a.hasName                AS adrName
        ORDER BY a.hasID, r.hasID
    """

    with _driver.session() as s:
        rows = s.run(cypher).data()

    return json.dumps({
        "total_unassigned": len(rows),
        "requirements": rows,
    }, indent=2)


def _word_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets — used for requirement name comparison."""
    a_words = set((a or "").lower().split()) - {"the", "a", "an", "of", "and", "or", "to", "be", "is", "in", "that", "shall"}
    b_words = set((b or "").lower().split()) - {"the", "a", "an", "of", "and", "or", "to", "be", "is", "in", "that", "shall"}
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


@mcp.tool()
def get_similar_assigned_requirements(requirement_id: str) -> str:
    """
    Given an unassigned requirement ID, find the 5 most similar
    requirements that DO have project assignments. Similarity is based
    on: same ADR (strong signal), and word overlap in requirementName.

    Returns the similar requirements with their assigned projects.
    These serve as examples for inferring which project the unassigned
    requirement should be mapped to.

    Call this tool when the user asks about gaps in the graph, missing
    assignments, or wants to extend the knowledge base.

    Args:
        requirement_id: The hasID of an unassigned requirement,
                        e.g. "REQ-10-003"
    """
    # Fetch the target requirement and its ADR
    with _driver.session() as s:
        target_row = s.run("""
            MATCH (a:AustralianDesignRule)
                  -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement {hasID: $rid})
            RETURN r.requirementName AS name, a.hasID AS adrID
        """, rid=requirement_id).single()

        if not target_row:
            return json.dumps({"error": f"Requirement {requirement_id!r} not found."}, indent=2)

        target_name = target_row["name"] or ""
        target_adr  = target_row["adrID"]

        # Fetch all assigned requirements — same ADR first, then others
        candidates = s.run("""
            MATCH (a:AustralianDesignRule)
                  -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
                  -[:assignedToProject]->(p:Project)
            WHERE r.hasID <> $rid
            OPTIONAL MATCH (p)-[:belongsToAssembly]->(asm:Assembly)
            RETURN
                r.hasID           AS requirementID,
                r.requirementName AS requirementName,
                a.hasID           AS adrID,
                collect(DISTINCT {projectID: p.projectID, projectName: p.projectName,
                                  assemblyID: asm.hasID}) AS assignedProjects,
                (a.hasID = $adrID) AS sameADR
            ORDER BY sameADR DESC, r.hasID
        """, rid=requirement_id, adrID=target_adr).data()

    # Score by: same ADR bonus + word overlap
    scored = []
    for c in candidates:
        overlap    = _word_overlap(target_name, c["requirementName"] or "")
        adr_bonus  = 0.4 if c["sameADR"] else 0.0
        score      = round(min(overlap + adr_bonus, 1.0), 3)
        scored.append({**c, "similarityScore": score})

    scored.sort(key=lambda x: x["similarityScore"], reverse=True)
    top5 = scored[:5]

    return json.dumps({
        "target_requirement": {
            "requirementID":   requirement_id,
            "requirementName": target_name,
            "adrID":           target_adr,
        },
        "similar_requirements": _serialise(top5),
    }, indent=2)


@mcp.tool()
def write_inferred_project_link(
    requirement_id: str,
    project_id: str,
    confidence: float,
    reasoning: str,
) -> str:
    """
    Write an inferred project assignment to neo4j as a suggestedProject
    relationship — never as assignedToProject.

    Creates:
      (ExtractedEssentialRequirement)-[:suggestedProject {
          confidence, reasoning, inferredBy, inferredAt
      }]->(Project)

    The suggestedProject relationship type is permanently distinguishable
    from confirmed assignedToProject relationships. Use promote_inferred_link
    to confirm an inference after human review.

    Args:
        requirement_id: hasID of the requirement, e.g. "REQ-10-003"
        project_id:     projectID of the suggested project, e.g. "SRP8-048"
        confidence:     float between 0.0 and 1.0
        reasoning:      human-readable explanation of why this inference
                        was made — stored in the graph for audit trail

    Call this tool when the user asks about gaps in the graph, missing
    assignments, or wants to extend the knowledge base.
    """
    if not 0.0 <= confidence <= 1.0:
        return json.dumps(
            {"error": f"confidence must be between 0.0 and 1.0, got {confidence}"},
            indent=2,
        )

    with _driver.session() as s:
        result = s.run("""
            MATCH (r:ExtractedEssentialRequirement {hasID: $rid})
            MATCH (p:Project {projectID: $pid})
            MERGE (r)-[rel:suggestedProject]->(p)
            SET rel.confidence  = $confidence,
                rel.reasoning   = $reasoning,
                rel.inferredBy  = "Claude-MCP",
                rel.inferredAt  = datetime()
            RETURN r.hasID AS requirementID, p.projectID AS projectID,
                   rel.confidence AS confidence, rel.inferredAt AS inferredAt
        """, rid=requirement_id, pid=project_id,
             confidence=confidence, reasoning=reasoning).single()

    if not result:
        return json.dumps({
            "error": f"Could not find requirement {requirement_id!r} or project {project_id!r}."
        }, indent=2)

    return json.dumps({
        "written": True,
        "requirementID": result["requirementID"],
        "projectID":     result["projectID"],
        "confidence":    result["confidence"],
        "inferredAt":    str(result["inferredAt"]),
    }, indent=2)


@mcp.tool()
def get_inferred_links() -> str:
    """
    Return all suggestedProject relationships currently in the graph,
    including confidence score, reasoning, who inferred it, and when.

    Use this for human review of inferred project assignments before
    deciding which to promote to confirmed assignedToProject links.

    Call this tool when the user asks about gaps in the graph, missing
    assignments, or wants to extend the knowledge base.
    """
    cypher = """
        MATCH (r:ExtractedEssentialRequirement)-[rel:suggestedProject]->(p:Project)
        MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
        OPTIONAL MATCH (p)-[:belongsToAssembly]->(asm:Assembly)
        RETURN
            r.hasID           AS requirementID,
            r.requirementName AS requirementName,
            a.hasID           AS adrID,
            p.projectID       AS projectID,
            p.projectName     AS projectName,
            asm.hasID         AS assemblyID,
            rel.confidence    AS confidence,
            rel.reasoning     AS reasoning,
            rel.inferredBy    AS inferredBy,
            rel.inferredAt    AS inferredAt
        ORDER BY rel.confidence DESC
    """

    with _driver.session() as s:
        rows = s.run(cypher).data()

    # Convert neo4j datetime to string
    for row in rows:
        if row.get("inferredAt") is not None:
            row["inferredAt"] = str(row["inferredAt"])

    return json.dumps({
        "total_inferred_links": len(rows),
        "links": rows,
    }, indent=2)


@mcp.tool()
def promote_inferred_link(requirement_id: str, project_id: str) -> str:
    """
    Promote a suggestedProject relationship to a confirmed assignedToProject
    relationship. Call this when an engineer has reviewed an inferred link
    and confirmed it is correct.

    The original suggestedProject relationship is deleted. A new
    assignedToProject relationship is created with promotedAt and
    promotedBy properties for audit trail. The original confidence and
    reasoning are preserved on the confirmed relationship.

    Args:
        requirement_id: hasID of the requirement, e.g. "REQ-10-003"
        project_id:     projectID of the project to confirm, e.g. "SRP8-048"

    Call this tool when the user asks about gaps in the graph, missing
    assignments, or wants to extend the knowledge base.
    """
    with _driver.session() as s:
        # Read the inferred link properties before deleting
        inferred = s.run("""
            MATCH (r:ExtractedEssentialRequirement {hasID: $rid})
                  -[rel:suggestedProject]->(p:Project {projectID: $pid})
            RETURN rel.confidence AS confidence, rel.reasoning AS reasoning
        """, rid=requirement_id, pid=project_id).single()

        if not inferred:
            return json.dumps({
                "error": f"No suggestedProject link found between "
                         f"{requirement_id!r} and {project_id!r}."
            }, indent=2)

        saved_confidence = inferred["confidence"]
        saved_reasoning  = inferred["reasoning"]

        # Delete the inferred link and write the confirmed one
        result = s.run("""
            MATCH (r:ExtractedEssentialRequirement {hasID: $rid})
                  -[rel:suggestedProject]->(p:Project {projectID: $pid})
            DELETE rel
            WITH r, p
            MERGE (r)-[confirmed:assignedToProject]->(p)
            SET confirmed.promotedAt          = datetime(),
                confirmed.promotedBy          = "human-review",
                confirmed.originalConfidence  = $confidence,
                confirmed.originalReasoning   = $reasoning
            RETURN r.hasID AS requirementID, p.projectID AS projectID,
                   confirmed.promotedAt AS promotedAt
        """, rid=requirement_id, pid=project_id,
             confidence=saved_confidence, reasoning=saved_reasoning).single()

    return json.dumps({
        "promoted": True,
        "requirementID":      result["requirementID"],
        "projectID":          result["projectID"],
        "promotedAt":         str(result["promotedAt"]),
        "originalConfidence": saved_confidence,
        "originalReasoning":  saved_reasoning,
    }, indent=2)


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
    print(f"              get_highest_risk_gaps",            file=sys.stderr)
    print(f"              get_cross_assembly_requirements", file=sys.stderr)
    print(f"              get_assembly_dependencies",       file=sys.stderr)
    print(f"              get_shared_requirements",         file=sys.stderr)
    print(f"              get_interface_risk_report",       file=sys.stderr)
    print(f"              get_unassigned_requirements",    file=sys.stderr)
    print(f"              get_similar_assigned_requirements", file=sys.stderr)
    print(f"              write_inferred_project_link",    file=sys.stderr)
    print(f"              get_inferred_links",             file=sys.stderr)
    print(f"              promote_inferred_link",          file=sys.stderr)
    print("─" * 50,                                        file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
