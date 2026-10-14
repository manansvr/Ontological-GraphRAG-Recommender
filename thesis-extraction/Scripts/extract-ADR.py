#!/usr/bin/env python3
"""
extract-ADR.py
==============
Extracts from per-ADR CSV files stored in csv/.

3-level hierarchy:
  AustralianDesignRule
    -[:hasExternalEssentialRequirement]-> ExtractedEssentialRequirement
      -[:assignedToProject]-> Project

Also written:
  AustralianDesignRule -[:hasClause]-> Clause
  ExtractedEssentialRequirement -[:derivedFrom]-> AustralianDesignRule
  AustralianDesignRule -[:assignedToDepartment]-> Department

Applicability (read_applicability): the Applicability column decides when it holds a
recognised value; otherwise the requirement name's keywords; otherwise applicable.
Nodes store applicabilityBasis and needsReview; flagged rows go to
logs/applicability-review.csv. Project ID placeholders (N/A, NA, -, TBC, empty) create
no Project and no edge. The summary reports distinct nodes and edges; the old per-row
counters are kept and labelled as rows.

Usage:
    python3 Scripts/extract-ADR.py --folder csv --dry-run
    python3 Scripts/extract-ADR.py --folder csv
    python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv --dry-run
    python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv
"""

import csv
import re
import argparse
from collections import Counter
from pathlib import Path
from neo4j import GraphDatabase

VERIFICATION_METHOD_MAP = {
    "inspection":               "Inspection",
    "visual inspection":        "Inspection",
    "manual inspection":        "Inspection",
    "demonstration":            "Demonstration",
    "demo":                     "Demonstration",
    "test":                     "Test",
    "physical test":            "Test",
    "functional test":          "Test",
    "analysis":                 "Analysis",
    "simulation":               "Analysis",
    "simulations/calculations": "Analysis",
    "calculations":             "Analysis",
    "fea":                      "Analysis",
    "cfd":                      "Analysis",
    "adr annex":                "ADRAnnex",
    "annex":                    "ADRAnnex",
    "adr testing procedure":    "ADRTestingProcedure",
    "adr test procedure":       "ADRTestingProcedure",
}

EVIDENCE_LABEL_MAP = {
    "Inspection":          "InspectionEvidence",
    "Demonstration":       "DemonstrationEvidence",
    "Test":                "TestEvidence",
    "Analysis":            "AnalysisEvidence",
    "ADRAnnex":            "ADRAnnexEvidence",
    "ADRTestingProcedure": "ADRTestingProcedureEvidence",
}

COLUMN_ALIASES = {
    "adr_id": [
        "ADR Number", "ADR ID", "ADRID", "ADR Id", "adr_id", "ADR",
    ],
    "applicability": [
        "Applicability", "applicability", "Is Applicable", "Applicable?",
    ],
    "adr_name":  ["ADR Name", "ADRName", "adr_name"],
    "checklist": ["Checklist", "Check", "check", "#"],
    "clause":    ["Clause", "Cla", "clause", "Clause No"],
    "req_name":  ["Req Name", "ReqName", "Requirement Name"],
    "text":      ["Text", "Requirement Text", "text"],
    "project_id":   ["Project ID", "ProjectID", "project_id"],
    "rel_project":  ["Relevant Project", "RelevantProject", "Project Name"],
    "rel_dept":     ["Relevant Department", "RelevantDepartment", "Department"],
    "right_project": [
        "Right Project Assigned? (If not, list the appropriate one)",
        "Right Project Assigned?", "Right Project Assigned", "rightProjectAssigned",
    ],
    "alt_testing": [
        "Would like to use Alternative Means of Testing compared to ADR (Yes/No)?",
        "Would like to use Alternative Means Testing compared to ADR (Yes/No)",
        "Alternative Means Testing", "Uses Alternative Testing",
    ],
    "verif_method": [
        "Verification Method : Inspection, Demonstration, Test, Analysis (Simulations/Calculations), ADR Annex, ADR Testing Procedure",
        "Verification Method: Inspection, Demonstration, Test, Analysis (Simulations/Calculations), ADR Annex, ADR Testing Procedure",
        "Verification Method", "VerificationMethod",
    ],
    "verif_desc": [
        "Verification Method Description (As detailed as you can be)",
        "Verification Method Description (be as detailed as you can be)",
        "Verification Method Description", "VerificationMethodDescription",
    ],
    "test_procedure": [
        "Testing Procedure Per Req (To Be Done Later)",
        "Testing Procedure Per Requirement", "Testing Procedure Per...",
        "Testing Procedure", "TestingProcedure",
    ],
    "verified": ["Verified?", "Verified", "Is Verified", "isVerified"],
}


def get_col(row: dict, key: str) -> str:
    for alias in COLUMN_ALIASES.get(key, [key]):
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    return ""


def normalise_adr_id(raw: str) -> str:
    m = re.search(r'\d+', str(raw))
    return f"ADR-{int(m.group())}" if m else ""


def normalise_bool(val: str) -> bool:
    return str(val).strip().upper() in {"YES", "TRUE", "1", "Y"}


def normalise_verification_method(raw: str) -> str:
    if not raw:
        return ""
    key = raw.strip().lower()
    if key in VERIFICATION_METHOD_MAP:
        return VERIFICATION_METHOD_MAP[key]
    for k, label in VERIFICATION_METHOD_MAP.items():
        if k in key:
            return label
    return ""


APPLICABLE_VALUES = {"applicable", "yes", "true", "1", "y"}
NOT_APPLICABLE_VALUES = {"not applicable", "no", "false", "0", "n", "n/a"}
NOT_APPLICABLE_NAME_KEYWORDS = ("not applicable", "post collision")

# Project ID cells that mean "no project" (compared case-insensitively after stripping).
# Such rows get no Project node and no assignedToProject edge; the requirement is unassigned.
MISSING_PROJECT_IDS = {"n/a", "na", "-", "", "tbc"}


def normalise_project_id(raw: str) -> str:
    """Return the project ID, or "" for a placeholder that means no project (see MISSING_PROJECT_IDS)."""
    value = str(raw or "").strip()
    return "" if value.lower() in MISSING_PROJECT_IDS else value


def _name_says_not_applicable(req_name: str) -> bool:
    name = (req_name or "").strip().lower()
    return any(keyword in name for keyword in NOT_APPLICABLE_NAME_KEYWORDS)


def read_applicability(row: dict, req_name: str) -> tuple:
    """Decide applicability from the Applicability column and the requirement name only.

    The requirement text (body) is never read. Rule, in order:
    1. Applicability column holds a recognised value -> use it (basis 'column'):
       applicable/yes/true/1/y -> applicable; not applicable/no/false/0/n/n/a -> not applicable.
    2. Otherwise (column missing, empty or unrecognised): the requirement name contains
       "not applicable" or "post collision" -> not applicable (basis 'name_keyword').
    3. Otherwise -> applicable (basis 'default').
    Returns (is_applicable, note, basis); note is the requirement name when not applicable.
    Whether the row needs human review is decided by applicability_review_reason.
    """
    raw = get_col(row, "applicability").strip().lower()
    if raw in APPLICABLE_VALUES:
        return True, "", "column"
    if raw in NOT_APPLICABLE_VALUES:
        return False, (req_name or "").strip(), "column"
    if _name_says_not_applicable(req_name):
        return False, (req_name or "").strip(), "name_keyword"
    return True, "", "default"


def applicability_review_reason(row: dict, req_name: str) -> str:
    """Return why a row's applicability needs human review, or "" if it does not.

    Flagged only when (a) the Applicability column has a non-empty value that is not
    recognised, or (b) a recognised column value says applicable while the requirement
    name contains a not-applicable keyword. A missing or empty column is not flagged.
    """
    raw = get_col(row, "applicability").strip()
    if not raw:
        return ""
    value = raw.lower()
    if value not in APPLICABLE_VALUES | NOT_APPLICABLE_VALUES:
        return f"unrecognised Applicability value {raw!r}"
    if value in APPLICABLE_VALUES and _name_says_not_applicable(req_name):
        return f"Applicability column says {raw!r} but the requirement name {req_name.strip()!r} says not applicable"
    return ""


def forward_fill_adr_id(rows: list) -> list:
    current_id   = ""
    current_name = ""
    id_header    = COLUMN_ALIASES["adr_id"][0]
    name_header  = COLUMN_ALIASES["adr_name"][0]
    for row in rows:
        raw = get_col(row, "adr_id")
        if raw:
            current_id   = raw
            current_name = get_col(row, "adr_name")
        if not row.get(id_header):
            row[id_header] = current_id
        if not row.get(name_header):
            row[name_header] = current_name
    return rows


# ── Writers ───────────────────────────────────────────────────────────

def write_adr_node(session, adr_id: str, adr_name: str):
    session.run("""
        MERGE (a:AustralianDesignRule:RegulatoryDocument:Document {hasID: $id})
        ON CREATE SET a.hasName       = $name,
                      a.isVerified    = false,
                      a.hasProvenance = 'CSV-Extracted'
        ON MATCH  SET a.hasName = CASE WHEN $name <> '' THEN $name
                                       ELSE a.hasName END
    """, id=adr_id, name=adr_name)


def write_clause(session, adr_id: str, clause_num: str,
                 req_name: str, text: str,
                 is_applicable: bool, applicability_note: str,
                 applicability_basis: str = "default", needs_review: bool = False):
    """Clause node — pure Clause label only, connected via hasClause."""
    cid     = f"CLAUSE-{adr_id.replace('ADR-','')}-{clause_num.replace('.','_')}"
    display = req_name if req_name else clause_num
    session.run("""
        MERGE (c:Clause {hasID: $cid})
        ON CREATE SET c.hasName           = $display,
                      c.clauseText        = $text
        ON MATCH  SET c.clauseText        = CASE WHEN $text <> '' THEN $text
                                                  ELSE c.clauseText END
        SET c.isApplicable       = $applicable,
            c.applicabilityNote  = $note,
            c.applicabilityBasis = $basis,
            c.needsReview        = $needs_review
        WITH c
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasClause]->(c)
    """, cid=cid, display=display, text=text, aid=adr_id,
         applicable=is_applicable, note=applicability_note,
         basis=applicability_basis, needs_review=needs_review)


def write_requirement(session, adr_id: str, req_id: str,
                       req_name: str, text: str,
                       is_applicable: bool, applicability_note: str,
                       is_verified: bool = False,
                       applicability_basis: str = "default", needs_review: bool = False):
    """
    ExtractedEssentialRequirement — sits between ADR and Project.
    ADR -[:hasExternalEssentialRequirement]-> Requirement -[:assignedToProject]-> Project
    """
    session.run("""
        MERGE (r:ExtractedEssentialRequirement:ExtractedRequirement:Requirement
               {hasID: $rid})
        ON CREATE SET r.requirementName        = $name,
                      r.requirementDescription = $text,
                      r.hasRiskLevel           = 'High',
                      r.isEssential            = true,
                      r.isConditional          = false,
                      r.hasConfidenceScore     = 1.0,
                      r.hasProvenance          = 'CSV-Extracted',
                      r.isVerified             = $verified
        ON MATCH  SET r.isVerified        = $verified
        SET r.isApplicable       = $applicable,
            r.applicabilityNote  = $note,
            r.applicabilityBasis = $basis,
            r.needsReview        = $needs_review
        WITH r
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasExternalEssentialRequirement]->(r)
        MERGE (r)-[:derivedFrom]->(a)
    """, rid=req_id, name=req_name, text=text, aid=adr_id,
         applicable=is_applicable, note=applicability_note, verified=is_verified,
         basis=applicability_basis, needs_review=needs_review)


def write_verification(session, adr_id: str, clause_num: str,
                        vmethod: str, vdesc: str, test_proc: str,
                        is_verified: bool):
    evidence_label = EVIDENCE_LABEL_MAP.get(vmethod, "TestEvidence")
    suffix = clause_num.replace(".", "_")
    vp_id  = f"VP-{adr_id.replace('ADR-','')}-{suffix}"
    vm_id  = f"VM-{vmethod}-{adr_id.replace('ADR-','')}-{suffix}"
    ev_id  = f"EV-{adr_id.replace('ADR-','')}-{suffix}"
    session.run(f"""
        MERGE (vp:VerificationProcedure {{hasID: $vpid}})
        ON CREATE SET
            vp.hasName                        = $vpname,
            vp.verificationMethodDescription  = $vdesc,
            vp.testingProcedurePerRequirement = $testproc
        WITH vp
        MATCH (a:AustralianDesignRule {{hasID: $aid}})
        MERGE (a)-[:hasVerificationProcedure]->(vp)
        MERGE (m:{vmethod}:VerificationMethod:VerificationProcedure:Requirement
               {{hasID: $vmid}})
        ON CREATE SET m.hasName = $method
        MERGE (vp)-[:hasVerificationMethod]->(m)
        MERGE (ev:{evidence_label}:TestingEvidence:Document {{hasID: $evid}})
        ON CREATE SET ev.hasName    = $evname,
                      ev.isVerified = $verified
        MERGE (vp)-[:supportedByEvidence]->(ev)
        MERGE (a)-[:verifiedBy]->(ev)
    """,
        vpid=vp_id, vpname=f"VP — {adr_id} clause {clause_num}",
        vdesc=vdesc, testproc=test_proc, aid=adr_id,
        vmid=vm_id, method=vmethod,
        evid=ev_id, evname=f"{vmethod} Evidence — {adr_id} {clause_num}",
        verified=is_verified,
    )


def write_project_links(session, adr_id: str, req_id: str,
                         project_id: str, rel_project: str, rel_dept: str):
    """
    Links Requirement → Project (not ADR → Project).
    New assignedToProject edges get source = 'extracted' (links promoted from
    sr8-mcp suggestions carry source = 'inferred').
    This creates the 3-level hierarchy:
      AustralianDesignRule
        → ExtractedEssentialRequirement
          → Project
    Department is still linked from the ADR directly.
    """
    if project_id:
        # Create Project node
        session.run("""
            MERGE (p:Project {projectID: $pid})
            ON CREATE SET p.projectName = $pname
        """, pid=project_id, pname=rel_project)

        # Link Requirement → Project (creates the 3rd tier)
        if req_id:
            session.run("""
                MATCH (r:ExtractedEssentialRequirement {hasID: $rid})
                MATCH (p:Project {projectID: $pid})
                MERGE (r)-[rel:assignedToProject]->(p)
                ON CREATE SET rel.source = 'extracted'
            """, rid=req_id, pid=project_id)

        # Also keep ADR → Project for completeness (used in analytics queries)
        session.run("""
            MATCH (a:AustralianDesignRule {hasID: $aid})
            MATCH (p:Project {projectID: $pid})
            MERGE (a)-[:hasRelevantProject]->(p)
        """, aid=adr_id, pid=project_id)

    if rel_dept:
        session.run("""
            MERGE (d:Department {hasName: $dept})
            WITH d
            MATCH (a:AustralianDesignRule {hasID: $aid})
            MERGE (a)-[:assignedToDepartment]->(d)
            MERGE (a)-[:hasRelevantDepartment]->(d)
        """, dept=rel_dept, aid=adr_id)


def write_adr_properties(session, adr_id: str, row: dict):
    session.run("""
        MATCH (a:AustralianDesignRule {hasID: $aid})
        SET a.rightProjectAssigned           = $rightProj,
            a.usesAlternativeTesting         = $altTest,
            a.testingProcedurePerRequirement = $testProc,
            a.isVerified                     = $verified
    """,
        aid=adr_id,
        rightProj=normalise_bool(get_col(row, "right_project")),
        altTest=normalise_bool(get_col(row, "alt_testing")),
        testProc=get_col(row, "test_procedure"),
        verified=normalise_bool(get_col(row, "verified")),
    )


# ── Per-row plan ──────────────────────────────────────────────────────

def plan_rows(rows: list) -> list:
    """Decide, for each CSV row (after forward_fill_adr_id), what the extractor does with it.

    Single source of truth for both the graph writes and the summary counts (also used by
    extract_assemblies.py). Each item is a dict with csv_row, adr_id, skip_reason (rows that
    are skipped entirely), the column values, project_id (placeholders such as "N/A" mapped
    to ""), raw_project_id, is_applicable / applicability_note / applicability_basis,
    review_reason, req_id (None when the row creates no requirement) and
    no_requirement_reason.
    """
    plans = []
    req_counter = 0
    for i, row in enumerate(rows, start=2):
        plan = {"csv_row": i, "row": row, "adr_id": normalise_adr_id(get_col(row, "adr_id")),
                "skip_reason": "", "req_id": None, "no_requirement_reason": ""}
        plans.append(plan)
        if not plan["adr_id"]:
            plan["skip_reason"] = "no ADR number"
            continue
        plan.update(
            adr_name=get_col(row, "adr_name"),
            clause_num=get_col(row, "clause"),
            req_name=get_col(row, "req_name"),
            text=get_col(row, "text"),
            raw_project_id=get_col(row, "project_id"),
            project_id=normalise_project_id(get_col(row, "project_id")),
            rel_project=get_col(row, "rel_project"),
            rel_dept=get_col(row, "rel_dept"),
            vmethod=normalise_verification_method(get_col(row, "verif_method")),
            vdesc=get_col(row, "verif_desc"),
            test_proc=get_col(row, "test_procedure"),
            is_verified=normalise_bool(get_col(row, "verified")),
        )
        if not plan["clause_num"] and not plan["req_name"] and not plan["text"]:
            plan["skip_reason"] = "no clause, requirement name or text"
            continue
        is_applicable, note, basis = read_applicability(row, plan["req_name"])
        plan.update(is_applicable=is_applicable, applicability_note=note, applicability_basis=basis,
                    review_reason=applicability_review_reason(row, plan["req_name"]))
        if plan["req_name"] and (plan["text"] or not is_applicable):
            req_counter += 1
            plan["req_id"] = f"REQ-{plan['adr_id'].replace('ADR-', '')}-{req_counter:03d}"
        else:
            plan["no_requirement_reason"] = ("no requirement name" if not plan["req_name"]
                                             else "requirement name but no text (applicable)")
    return plans


def _new_stats() -> dict:
    return {
        "files": 0, "ledger_rows": 0,
        "requirements": {},            # req_id -> is_applicable
        "clauses": set(), "edges": set(), "projects": set(), "unassigned": set(),
        "skipped": Counter(), "no_requirement": Counter(),
        "placeholder_project_rows": 0, "review_rows": [],
        "clause_rows": 0, "requirement_rows": 0, "link_rows": 0, "verification_rows": 0,
    }


def _merge_stats(total: dict, part: dict) -> None:
    for key in ("files", "ledger_rows", "placeholder_project_rows", "clause_rows",
                "requirement_rows", "link_rows", "verification_rows"):
        total[key] += part[key]
    total["requirements"].update(part["requirements"])
    for key in ("clauses", "edges", "projects", "unassigned"):
        total[key] |= part[key]
    total["skipped"].update(part["skipped"])
    total["no_requirement"].update(part["no_requirement"])
    total["review_rows"].extend(part["review_rows"])


def summarise_stats(stats: dict) -> dict:
    """Plain numbers for printing and returning."""
    applicable = sum(1 for a in stats["requirements"].values() if a)
    return {
        "ledger_rows": stats["ledger_rows"],
        "requirement_nodes": len(stats["requirements"]),
        "requirements_applicable": applicable,
        "requirements_not_applicable": len(stats["requirements"]) - applicable,
        "clause_nodes": len(stats["clauses"]),
        "assigned_to_project_edges": len(stats["edges"]),
        "distinct_projects": len(stats["projects"]),
        "unassigned_requirements": len(stats["unassigned"]),
        "flagged_for_review": len(stats["review_rows"]),
        "placeholder_project_rows": stats["placeholder_project_rows"],
        "skipped_rows": dict(stats["skipped"]),
        "rows_without_requirement": dict(stats["no_requirement"]),
        "row_counters": {
            "rows with a clause number": stats["clause_rows"],
            "rows creating a requirement": stats["requirement_rows"],
            "rows with a project or department": stats["link_rows"],
            "rows with a verification method": stats["verification_rows"],
        },
    }


def _reasons(counter: dict) -> str:
    return ", ".join(f"{reason}: {n}" for reason, n in sorted(counter.items())) or "none"


def print_summary(summary: dict, indent: str = "     ") -> None:
    s = summary
    print(f"{indent}ledger rows:                        {s['ledger_rows']}")
    print(f"{indent}requirement nodes:                  {s['requirement_nodes']} "
          f"({s['requirements_applicable']} applicable, {s['requirements_not_applicable']} not applicable)")
    print(f"{indent}distinct Clause nodes:              {s['clause_nodes']}")
    print(f"{indent}assignedToProject edges:            {s['assigned_to_project_edges']}")
    print(f"{indent}distinct projects:                  {s['distinct_projects']}")
    print(f"{indent}unassigned requirements:            {s['unassigned_requirements']}")
    print(f"{indent}rows flagged for review:            {s['flagged_for_review']}")
    print(f"{indent}rows with a placeholder project ID: {s['placeholder_project_rows']} "
          f"(N/A, NA, -, TBC: no Project node, no edge)")
    print(f"{indent}rows skipped:                       {sum(s['skipped_rows'].values())} ({_reasons(s['skipped_rows'])})")
    print(f"{indent}rows without a requirement node:    {sum(s['rows_without_requirement'].values())} "
          f"({_reasons(s['rows_without_requirement'])})")
    print(f"{indent}row counters (rows, not nodes):     "
          + " | ".join(f"{k} {v}" for k, v in s["row_counters"].items()))


# ── Per-file extractor ────────────────────────────────────────────────

def extract_one_file(path: str, driver, dry_run: bool = False) -> dict:
    """Extract one ADR CSV; returns the raw stats (see _new_stats) for this file."""
    print(f"\n📄 {Path(path).name}")
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = [{k.strip(): v for k, v in row.items()} for row in reader]

    stats = _new_stats()
    if not rows:
        print("   Empty file — skipping")
        return stats

    rows = forward_fill_adr_id(rows)
    print(f"   {len(rows)} rows | Headers: {list(rows[0].keys())}")
    stats["files"] = 1
    stats["ledger_rows"] = len(rows)
    seen_adr_id = None
    seen_last_row = None

    for plan in plan_rows(rows):
        if plan["skip_reason"]:
            stats["skipped"][plan["skip_reason"]] += 1
            continue
        adr_id, row = plan["adr_id"], plan["row"]
        clause_num, req_name, text = plan["clause_num"], plan["req_name"], plan["text"]
        project_id, req_id = plan["project_id"], plan["req_id"]
        is_applicable, needs_review = plan["is_applicable"], bool(plan["review_reason"])
        seen_adr_id, seen_last_row = adr_id, row

        # ── counts (distinct nodes/edges, plus the old row counters) ──
        if plan["raw_project_id"] and not project_id:
            stats["placeholder_project_rows"] += 1
        if clause_num:
            stats["clause_rows"] += 1
            stats["clauses"].add(f"CLAUSE-{adr_id.replace('ADR-','')}-{clause_num.replace('.','_')}")
        if req_id:
            stats["requirement_rows"] += 1
            stats["requirements"][req_id] = is_applicable
            if project_id:
                stats["edges"].add((req_id, project_id))
            else:
                stats["unassigned"].add(req_id)
        else:
            stats["no_requirement"][plan["no_requirement_reason"]] += 1
        if plan["vmethod"] and clause_num and is_applicable:
            stats["verification_rows"] += 1
        if project_id or plan["rel_dept"]:
            stats["link_rows"] += 1
        if project_id:
            stats["projects"].add(project_id)
        if needs_review:
            stats["review_rows"].append({
                "source_file": Path(path).name, "csv_row": plan["csv_row"], "adr_id": adr_id,
                "clause": clause_num, "requirement_id": req_id or "", "requirement_name": req_name,
                "applicability_column": get_col(row, "applicability"),
                "decided_applicable": is_applicable, "basis": plan["applicability_basis"],
                "reason": plan["review_reason"],
            })

        if dry_run:
            status    = "NOT APPLICABLE" if not is_applicable else "applicable"
            proj_info = f"→ {project_id}" if project_id else "no project"
            preview   = f" | \"{text[:50]}...\"" if text else " | (no text)"
            review    = " | NEEDS REVIEW" if needs_review else ""
            print(f"  [{'N/A ' if not is_applicable else 'DRY '}]  "
                  f"{adr_id} | {clause_num} | {req_name[:40]} | {proj_info} | {status}{review}{preview}")
            continue

        with driver.session() as s:
            write_adr_node(s, adr_id, plan["adr_name"])

            # Clause — always written via hasClause
            if clause_num:
                write_clause(s, adr_id, clause_num, req_name, text,
                             is_applicable, plan["applicability_note"] or "",
                             plan["applicability_basis"], needs_review)

            # Requirement — written first so we have req_id for project link
            if req_id:
                write_requirement(s, adr_id, req_id, req_name, text,
                                  is_applicable, plan["applicability_note"] or "", plan["is_verified"],
                                  plan["applicability_basis"], needs_review)

            if plan["vmethod"] and clause_num and is_applicable:
                write_verification(s, adr_id, clause_num, plan["vmethod"], plan["vdesc"],
                                   plan["test_proc"], plan["is_verified"])

            # Project link — goes from Requirement → Project (3-level hierarchy)
            if project_id or plan["rel_dept"]:
                write_project_links(s, adr_id, req_id, project_id, plan["rel_project"], plan["rel_dept"])

    if not dry_run and seen_adr_id and seen_last_row:
        with driver.session() as s:
            write_adr_properties(s, seen_adr_id, seen_last_row)

    file_summary = summarise_stats(stats)
    print(f"   ✓ Requirement nodes: {file_summary['requirement_nodes']} "
          f"({file_summary['requirements_not_applicable']} not applicable) | "
          f"Clause nodes: {file_summary['clause_nodes']} | "
          f"assignedToProject edges: {file_summary['assigned_to_project_edges']} | "
          f"Unassigned: {file_summary['unassigned_requirements']} | "
          f"Flagged for review: {file_summary['flagged_for_review']} | "
          f"Ledger rows: {file_summary['ledger_rows']}")
    return stats


# ── Entry point ───────────────────────────────────────────────────────

REVIEW_FILE = Path(__file__).resolve().parent.parent / "logs" / "applicability-review.csv"
REVIEW_FIELDS = ["source_file", "csv_row", "adr_id", "clause", "requirement_id", "requirement_name",
                 "applicability_column", "decided_applicable", "basis", "reason"]


def write_review_file(review_rows: list, path: Path = REVIEW_FILE) -> Path:
    """Write the rows flagged for applicability review (header only if none)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(review_rows)
    return path


def extract_adrs(path=None, folder=None, driver=None, dry_run=False, review_file: Path = REVIEW_FILE):
    """Extract ADR CSVs and print distinct node/edge counts; returns the summary (see summarise_stats)."""
    files = []
    if folder:
        p = Path(folder)
        files = sorted(p.glob("*.csv"))
        print(f"\n📁 Found {len(files)} CSV file(s) in {folder}")
    elif path:
        files = [Path(path)]
    else:
        raise ValueError("Provide either --file or --folder")

    total = _new_stats()
    for f in files:
        _merge_stats(total, extract_one_file(str(f), driver, dry_run=dry_run))

    summary = summarise_stats(total)
    print(f"\n   ── TOTAL across {len(files)} file(s) ──")
    print_summary(summary)
    written = write_review_file(total["review_rows"], review_file)
    print(f"     review list:                       {written} ({summary['flagged_for_review']} row(s))")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",   help="Single ADR CSV file")
    group.add_argument("--folder", help="Folder of ADR CSV files")
    parser.add_argument("--uri",      default="bolt://localhost:7687")
    parser.add_argument("--user",     default="neo4j")
    parser.add_argument("--password", default="password")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    driver = None
    if not args.dry_run:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        extract_adrs(path=args.file, folder=args.folder,
                     driver=driver, dry_run=args.dry_run)
    finally:
        if driver:
            driver.close()