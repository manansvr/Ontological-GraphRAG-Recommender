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

Usage:
    python3 Scripts/extract-ADR.py --folder csv --dry-run
    python3 Scripts/extract-ADR.py --folder csv
    python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv --dry-run
    python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv
"""

import csv
import re
import argparse
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


def read_applicability(row: dict, req_name: str) -> tuple:
    raw = get_col(row, "applicability").strip().lower()
    if raw in {"applicable", "yes", "true", "1", "y"}:
        return True, ""
    if raw in {"not applicable", "no", "false", "0", "n", "n/a"}:
        return False, req_name.strip()
    if not req_name:
        return True, ""
    name_lower = req_name.strip().lower()
    if "not applicable" in name_lower or "post collision" in name_lower:
        return False, req_name.strip()
    return True, ""


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
                 is_applicable: bool, applicability_note: str):
    """Clause node — pure Clause label only, connected via hasClause."""
    cid     = f"CLAUSE-{adr_id.replace('ADR-','')}-{clause_num.replace('.','_')}"
    display = req_name if req_name else clause_num
    session.run("""
        MERGE (c:Clause {hasID: $cid})
        ON CREATE SET c.hasName           = $display,
                      c.clauseText        = $text,
                      c.isApplicable      = $applicable,
                      c.applicabilityNote = $note
        ON MATCH  SET c.clauseText        = CASE WHEN $text <> '' THEN $text
                                                  ELSE c.clauseText END,
                      c.isApplicable      = $applicable,
                      c.applicabilityNote = $note
        WITH c
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasClause]->(c)
    """, cid=cid, display=display, text=text, aid=adr_id,
         applicable=is_applicable, note=applicability_note)


def write_requirement(session, adr_id: str, req_id: str,
                       req_name: str, text: str,
                       is_applicable: bool, applicability_note: str):
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
                      r.isApplicable           = $applicable,
                      r.applicabilityNote      = $note
        ON MATCH  SET r.isApplicable      = $applicable,
                      r.applicabilityNote = $note
        WITH r
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasExternalEssentialRequirement]->(r)
        MERGE (r)-[:derivedFrom]->(a)
    """, rid=req_id, name=req_name, text=text, aid=adr_id,
         applicable=is_applicable, note=applicability_note)


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
                MERGE (r)-[:assignedToProject]->(p)
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


# ── Per-file extractor ────────────────────────────────────────────────

def extract_one_file(path: str, driver, dry_run: bool = False) -> dict:
    print(f"\n📄 {Path(path).name}")
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = [{k.strip(): v for k, v in row.items()} for row in reader]

    if not rows:
        print("   Empty file — skipping")
        return {}

    rows = forward_fill_adr_id(rows)
    print(f"   {len(rows)} rows | Headers: {list(rows[0].keys())}")

    counts = {
        "clauses": 0, "requirements": 0, "not_applicable": 0,
        "vps": 0, "proj_links": 0, "skipped": 0,
    }
    seen_adr_id   = None
    seen_last_row = None
    req_counter   = 0

    for i, row in enumerate(rows, start=2):
        adr_id   = normalise_adr_id(get_col(row, "adr_id"))
        adr_name = get_col(row, "adr_name")
        if not adr_id:
            counts["skipped"] += 1
            continue

        clause_num  = get_col(row, "clause")
        req_name    = get_col(row, "req_name")
        text        = get_col(row, "text")
        project_id  = get_col(row, "project_id")
        rel_project = get_col(row, "rel_project")
        rel_dept    = get_col(row, "rel_dept")
        vmethod_raw = get_col(row, "verif_method")
        vdesc       = get_col(row, "verif_desc")
        test_proc   = get_col(row, "test_procedure")
        is_verified = normalise_bool(get_col(row, "verified"))
        vmethod     = normalise_verification_method(vmethod_raw)

        if not clause_num and not req_name and not text:
            counts["skipped"] += 1
            continue

        if req_name:
            is_applicable, applicability_note = read_applicability(row, req_name)
        else:
            is_applicable, applicability_note = True, ""

        if is_applicable is None:
            counts["skipped"] += 1
            if dry_run:
                print(f"  [HEADER] {clause_num}: {req_name[:60]}")
            continue

        seen_adr_id   = adr_id
        seen_last_row = row

        if dry_run:
            status    = "NOT APPLICABLE" if not is_applicable else "applicable"
            proj_info = f"→ {project_id}" if project_id else "no project"
            preview   = f" | \"{text[:50]}...\"" if text else " | (no text)"
            print(f"  [{'N/A ' if not is_applicable else 'DRY '}]  "
                  f"{adr_id} | {clause_num} | {req_name[:40]} | {proj_info} | {status}{preview}")
            if clause_num:
                counts["clauses"] += 1
            if req_name and (text or not is_applicable):
                counts["requirements"] += 1
                if not is_applicable:
                    counts["not_applicable"] += 1
            if vmethod:
                counts["vps"] += 1
            if project_id or rel_dept:
                counts["proj_links"] += 1
            continue

        with driver.session() as s:
            write_adr_node(s, adr_id, adr_name)

            # Clause — always written via hasClause
            if clause_num:
                write_clause(s, adr_id, clause_num, req_name, text,
                             is_applicable, applicability_note or "")
                counts["clauses"] += 1

            # Requirement — written first so we have req_id for project link
            current_req_id = None
            if req_name and (text or not is_applicable):
                req_counter += 1
                current_req_id = f"REQ-{adr_id.replace('ADR-','')}-{req_counter:03d}"
                write_requirement(s, adr_id, current_req_id, req_name, text,
                                  is_applicable, applicability_note or "")
                counts["requirements"] += 1
                if not is_applicable:
                    counts["not_applicable"] += 1

            if vmethod and clause_num and is_applicable:
                write_verification(s, adr_id, clause_num,
                                   vmethod, vdesc, test_proc, is_verified)
                counts["vps"] += 1

            # Project link — goes from Requirement → Project (3-level hierarchy)
            if project_id or rel_dept:
                write_project_links(s, adr_id, current_req_id,
                                    project_id, rel_project, rel_dept)
                counts["proj_links"] += 1

    if not dry_run and seen_adr_id and seen_last_row:
        with driver.session() as s:
            write_adr_properties(s, seen_adr_id, seen_last_row)

    print(f"   ✓ Clauses: {counts['clauses']} | "
          f"Requirements: {counts['requirements']} "
          f"({counts['not_applicable']} not applicable) | "
          f"VPs: {counts['vps']} | "
          f"Links: {counts['proj_links']} | "
          f"Headers skipped: {counts['skipped']}")
    return counts


# ── Entry point ───────────────────────────────────────────────────────

def extract_adrs(path=None, folder=None, driver=None, dry_run=False):
    files = []
    if folder:
        p = Path(folder)
        files = sorted(p.glob("*.csv"))
        print(f"\n📁 Found {len(files)} CSV file(s) in {folder}")
    elif path:
        files = [Path(path)]
    else:
        raise ValueError("Provide either --file or --folder")

    total = {"clauses": 0, "requirements": 0, "not_applicable": 0,
             "vps": 0, "proj_links": 0, "skipped": 0}

    for f in files:
        counts = extract_one_file(str(f), driver, dry_run=dry_run)
        for k in total:
            total[k] += counts.get(k, 0)

    if len(files) > 1:
        print(f"\n   ── TOTAL across {len(files)} files ──")
        for k, v in total.items():
            print(f"     {k}: {v}")

    return total


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