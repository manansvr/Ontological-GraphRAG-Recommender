#!/usr/bin/env python3
"""
extract_adrs.py
================
Extracts from per-ADR CSV files stored in data/adrs/.

What this script does, step by step:
  1. Reads every CSV file in data/adrs/ (or a single file if --file is used)
  2. Forward-fills the ADR Number column down all rows
     (because it only appears in the first row of each CSV)
  3. For each row it decides what to create:
       - Always: a Clause node (if there is a clause number)
       - If named: an ExtractedEssentialRequirement node
       - If method filled in: a VerificationProcedure node + evidence stub
       - If project ID present: assignedToProject relationship
       - Skips: section headers, Not Applicable rows
  4. All writes use MERGE so re-running is always safe

Usage:
  python scripts/extract_adrs.py --folder data/adrs/ --dry-run
  python scripts/extract_adrs.py --folder data/adrs/
  python scripts/extract_adrs.py --file data/adrs/ADR10-Requirements.csv --dry-run
  python scripts/extract_adrs.py --file data/adrs/ADR10-Requirements.csv
"""

import csv
import re
import argparse
from pathlib import Path
from neo4j import GraphDatabase

# ── Verification method normaliser ──────────────────────────────────
# Maps whatever someone types in the CSV to the exact ontology label
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

# Maps verification method to the correct evidence node label
EVIDENCE_LABEL_MAP = {
    "Inspection":          "InspectionEvidence",
    "Demonstration":       "DemonstrationEvidence",
    "Test":                "TestEvidence",
    "Analysis":            "AnalysisEvidence",
    "ADRAnnex":            "ADRAnnexEvidence",
    "ADRTestingProcedure": "ADRTestingProcedureEvidence",
}

# ── Column header aliases ────────────────────────────────────────────
# Each key maps to every possible way that column might be named in the CSV.
# get_col() tries each alias in order until it finds a non-empty value.
COLUMN_ALIASES = {
    "adr_id": [
        "ADR Number",   # ← your actual header
        "ADR ID", "ADRID", "ADR Id", "adr_id", "ADR",
    ],
    "adr_name":  ["ADR Name", "ADRName", "adr_name"],
    "checklist": ["Checklist", "Check", "check", "#"],
    "clause":    ["Clause", "Cla", "clause", "Clause No"],
    "req_name":  ["Req Name", "ReqName", "Requirement Name"],
    "text":      ["Text", "Requirement Text", "text"],
    "project_id":    ["Project ID", "ProjectID", "project_id"],
    "rel_project":   ["Relevant Project", "RelevantProject", "Project Name"],
    "rel_dept":      ["Relevant Department", "RelevantDepartment", "Department"],
    "right_project": [
        "Right Project Assigned? (If not, list the appropriate one)",
        "Right Project Assigned?",
        "Right Project Assigned",
        "rightProjectAssigned",
    ],
    "alt_testing": [
        "Would like to use Alternative Means of Testing compared to ADR (Yes/No)?",
        "Would like to use Alternative Means Testing compared to ADR (Yes/No)",
        "Alternative Means Testing",
        "Uses Alternative Testing",
    ],
    "verif_method": [
        "Verification Method : Inspection, Demonstration, Test, Analysis (Simulations/Calculations), ADR Annex, ADR Testing Procedure",
        "Verification Method: Inspection, Demonstration, Test, Analysis (Simulations/Calculations), ADR Annex, ADR Testing Procedure",
        "Verification Method",
        "VerificationMethod",
    ],
    "verif_desc": [
        "Verification Method Description (As detailed as you can be)",
        "Verification Method Description (be as detailed as you can be)",
        "Verification Method Description",
        "VerificationMethodDescription",
    ],
    "test_procedure": [
        "Testing Procedure Per Req (To Be Done Later)",
        "Testing Procedure Per Requirement",
        "Testing Procedure Per...",
        "Testing Procedure",
        "TestingProcedure",
    ],
    "verified": ["Verified?", "Verified", "Is Verified", "isVerified"],
}


def get_col(row: dict, key: str) -> str:
    """Try every alias for this key, return the first non-empty value found."""
    for alias in COLUMN_ALIASES.get(key, [key]):
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    return ""


def normalise_adr_id(raw: str) -> str:
    """'ADR 10', 'ADR-10/00', 'adr10' → 'ADR-10'."""
    m = re.search(r'\d+', str(raw))
    return f"ADR-{int(m.group())}" if m else ""


def normalise_bool(val: str) -> bool:
    """Yes/No/TRUE/FALSE/Pending → bool. Pending and No → False."""
    return str(val).strip().upper() in {"YES", "TRUE", "1", "Y"}


def normalise_verification_method(raw: str) -> str:
    """Map any freeform text to one of the 6 valid ontology labels."""
    if not raw:
        return ""
    key = raw.strip().lower()
    if key in VERIFICATION_METHOD_MAP:
        return VERIFICATION_METHOD_MAP[key]
    for k, label in VERIFICATION_METHOD_MAP.items():
        if k in key:
            return label
    return ""


def is_not_applicable(req_name: str) -> bool:
    """
    Returns True if this row is a section header or not-applicable row
    that should be skipped entirely.
    These rows appear in the ADR spreadsheets as structural dividers —
    they are not real requirements.
    """
    skip_phrases = [
        "not applicable",
        "post collision testing",
        "specifications",
        "requirements",
        "exemptions and alternative procedures",
        "exemptions",
        "scope",
        "definitions",
        "note (from",       # catches "ADR XX Note (From Andy)" rows
    ]
    name_lower = req_name.strip().lower()
    if name_lower in {"n/a", "na"}:
        return True
    return any(phrase in name_lower for phrase in skip_phrases)


def forward_fill_adr_id(rows: list) -> list:
    """
    In your CSVs, the ADR Number only appears in the first data row.
    Every row after that has an empty ADR Number column.
    This function reads down the rows, remembers the last non-empty
    ADR Number, and writes it into every row that is missing it.
    This means every row knows which ADR it belongs to before extraction starts.
    """
    current_id   = ""
    current_name = ""
    id_header    = COLUMN_ALIASES["adr_id"][0]    # "ADR Number"
    name_header  = COLUMN_ALIASES["adr_name"][0]  # "ADR Name"

    for row in rows:
        raw = get_col(row, "adr_id")
        if raw:
            current_id   = raw
            current_name = get_col(row, "adr_name")

        # Inject the filled value if the cell was empty
        if not row.get(id_header):
            row[id_header] = current_id
        if not row.get(name_header):
            row[name_header] = current_name

    return rows


# ── Neo4j writers ────────────────────────────────────────────────────
# Each function is responsible for one type of node or relationship.
# All use MERGE so they are safe to call multiple times — no duplicates.

def write_adr_node(session, adr_id: str, adr_name: str):
    """
    Creates or updates the top-level AustralianDesignRule node.
    Called once per unique ADR ID per file.
    Gets three labels: AustralianDesignRule, RegulatoryDocument, Document —
    matching the ontology hierarchy.
    """
    session.run("""
        MERGE (a:AustralianDesignRule:RegulatoryDocument:Document {hasID: $id})
        ON CREATE SET a.hasName       = $name,
                      a.isVerified    = false,
                      a.hasProvenance = 'CSV-Extracted'
        ON MATCH  SET a.hasName = CASE WHEN $name <> '' THEN $name
                                       ELSE a.hasName END
    """, id=adr_id, name=adr_name)


def write_clause(session, adr_id: str, clause_num: str,
                 req_name: str, text: str):
    """
    Creates a Clause node for every row that has a clause number,
    even if Req Name is blank. The full text of the clause is stored.
    Clause carries four requirement parent labels so it can be found
    via any branch of the requirement hierarchy.
    The hasClause relationship connects it back to its ADR.
    """
    cid     = f"CLAUSE-{adr_id.replace('ADR-','')}-{clause_num.replace('.','_')}"
    display = req_name if req_name else clause_num

    session.run("""
        MERGE (c:Clause
               :InternalEssentialRequirement
               :InternalRecommendedRequirement
               :ExtractedEssentialRequirement
               :ExtractedRecommendedRequirement
               {hasID: $cid})
        ON CREATE SET c.hasName    = $display,
                      c.clauseText = $text
        ON MATCH  SET c.clauseText = CASE WHEN $text <> '' THEN $text
                                          ELSE c.clauseText END
        WITH c
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasClause]->(c)
    """, cid=cid, display=display, text=text, aid=adr_id)


def write_requirement(session, adr_id: str, req_id: str,
                       req_name: str, text: str):
    """
    Creates an ExtractedEssentialRequirement node.
    Only called when both Req Name and Text are present.
    Links back to the ADR via hasExternalEssentialRequirement
    and derivedFrom.
    All CSV-sourced requirements are marked as essential with
    confidence score 1.0 since they come directly from the ADR document.
    """
    session.run("""
        MERGE (r:ExtractedEssentialRequirement
               :ExtractedRequirement
               :Requirement
               {hasID: $rid})
        ON CREATE SET r.requirementName        = $name,
                      r.requirementDescription = $text,
                      r.hasRiskLevel           = 'High',
                      r.isEssential            = true,
                      r.isConditional          = false,
                      r.hasConfidenceScore     = 1.0,
                      r.hasProvenance          = 'CSV-Extracted'
        WITH r
        MATCH (a:AustralianDesignRule {hasID: $aid})
        MERGE (a)-[:hasExternalEssentialRequirement]->(r)
        MERGE (r)-[:derivedFrom]->(a)
    """, rid=req_id, name=req_name, text=text, aid=adr_id)


def write_verification(session, adr_id: str, clause_num: str,
                        vmethod: str, vdesc: str, test_proc: str,
                        is_verified: bool):
    """
    Creates three nodes and links them:
      AustralianDesignRule
        -[:hasVerificationProcedure]-> VerificationProcedure
        -[:hasVerificationMethod]->    <VerificationMethod subtype>
        -[:supportedByEvidence]->      <TestingEvidence subtype>
    The evidence subtype matches the method —
    e.g. Inspection → InspectionEvidence.
    Only called when the Verification Method column is filled in.
    """
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
        vpid=vp_id,
        vpname=f"VP — {adr_id} clause {clause_num}",
        vdesc=vdesc, testproc=test_proc, aid=adr_id,
        vmid=vm_id, method=vmethod,
        evid=ev_id,
        evname=f"{vmethod} Evidence — {adr_id} {clause_num}",
        verified=is_verified,
    )


def write_project_links(session, adr_id: str, project_id: str,
                         rel_project: str, rel_dept: str):
    """
    Links an ADR to a Project and/or Department.
    Creates stub Project/Department nodes if they don't exist yet —
    they will be enriched later when extract_projects.py runs.
    Uses both assignedToProject and hasRelevantProject relationships
    as defined in relationships.csv.
    """
    if project_id:
        session.run("""
            MERGE (p:Project {projectID: $pid})
            ON CREATE SET p.projectName = $pname
            WITH p
            MATCH (a:AustralianDesignRule {hasID: $aid})
            MERGE (a)-[:assignedToProject]->(p)
            MERGE (a)-[:hasRelevantProject]->(p)
        """, pid=project_id, pname=rel_project, aid=adr_id)

    if rel_dept:
        session.run("""
            MERGE (d:Department {hasName: $dept})
            WITH d
            MATCH (a:AustralianDesignRule {hasID: $aid})
            MERGE (a)-[:assignedToDepartment]->(d)
            MERGE (a)-[:hasRelevantDepartment]->(d)
        """, dept=rel_dept, aid=adr_id)


def write_adr_properties(session, adr_id: str, row: dict):
    """
    Updates the ADR node's boolean flags using the last row seen.
    Called once per file after all rows are processed.
    """
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
    """
    Processes a single ADR CSV file.
    Returns a dict of counts for reporting.
    """
    print(f"\n📄 {Path(path).name}")

    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("   Empty file — skipping")
        return {}

    # Step 1: forward-fill ADR Number down all rows
    rows = forward_fill_adr_id(rows)
    print(f"   {len(rows)} rows | Headers: {list(rows[0].keys())}")

    counts = {
        "clauses": 0, "requirements": 0,
        "vps": 0, "proj_links": 0, "skipped": 0,
    }
    seen_adr_id   = None
    seen_last_row = None
    req_counter   = 0

    for i, row in enumerate(rows, start=2):

        # Step 2: get ADR ID for this row
        adr_id   = normalise_adr_id(get_col(row, "adr_id"))
        adr_name = get_col(row, "adr_name")

        if not adr_id:
            counts["skipped"] += 1
            continue

        # Step 3: read all fields for this row
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

        # Step 4: skip section headers and not-applicable rows
        if req_name and is_not_applicable(req_name):
            counts["skipped"] += 1
            if dry_run:
                print(f"  [SKIP] {clause_num}: {req_name[:60]}")
            continue

        # Skip rows with nothing useful at all
        if not clause_num and not req_name and not text:
            counts["skipped"] += 1
            continue

        seen_adr_id   = adr_id
        seen_last_row = row

        # ── DRY RUN: just print, don't write ────────────────────
        if dry_run:
            proj_info = f"→ {project_id}" if project_id else "no project"
            method_info = f"| method: {vmethod}" if vmethod else ""
            print(f"  [DRY]  {adr_id} | clause {clause_num} "
                  f"| {req_name[:40]} | {proj_info} {method_info}")
            if clause_num:
                counts["clauses"] += 1
            if req_name and text and not is_not_applicable(req_name):
                counts["requirements"] += 1
            if vmethod:
                counts["vps"] += 1
            if project_id or rel_dept:
                counts["proj_links"] += 1
            continue

        # ── LIVE RUN: write to neo4j ─────────────────────────────
        with driver.session() as s:

            # Always write the ADR node (MERGE = safe to repeat)
            write_adr_node(s, adr_id, adr_name)

            # Write Clause node for every row with a clause number
            if clause_num:
                write_clause(s, adr_id, clause_num, req_name, text)
                counts["clauses"] += 1

            # Write Requirement node only if there is a named requirement
            if req_name and text and not is_not_applicable(req_name):
                req_counter += 1
                req_id = f"REQ-{adr_id.replace('ADR-','')}-{req_counter:03d}"
                write_requirement(s, adr_id, req_id, req_name, text)
                counts["requirements"] += 1

            # Write VerificationProcedure if method is filled in
            if vmethod and clause_num:
                write_verification(s, adr_id, clause_num,
                                   vmethod, vdesc, test_proc, is_verified)
                counts["vps"] += 1

            # Write Project and Department links
            if project_id or rel_dept:
                write_project_links(s, adr_id, project_id,
                                    rel_project, rel_dept)
                counts["proj_links"] += 1

    # Update ADR-level boolean flags using the last row seen
    if not dry_run and seen_adr_id and seen_last_row:
        with driver.session() as s:
            write_adr_properties(s, seen_adr_id, seen_last_row)

    print(f"   ✓ Clauses: {counts['clauses']} | "
          f"Requirements: {counts['requirements']} | "
          f"VPs: {counts['vps']} | "
          f"Project links: {counts['proj_links']} | "
          f"Skipped: {counts['skipped']}")
    return counts


# ── Entry point ───────────────────────────────────────────────────────

def extract_adrs(path=None, folder=None, driver=None, dry_run=False):
    """Called by run_extraction.py or directly from the CLI."""
    files = []
    if folder:
        p = Path(folder)
        files = sorted(p.glob("*.csv"))
        print(f"\n📁 Found {len(files)} CSV file(s) in {folder}")
    elif path:
        files = [Path(path)]
    else:
        raise ValueError("Provide either --file or --folder")

    total = {"clauses": 0, "requirements": 0,
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
    parser = argparse.ArgumentParser(
        description="Extract ADR requirements from per-ADR CSV files in data/adrs/"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",   help="Single ADR CSV file")
    group.add_argument("--folder", help="Folder containing ADR CSV files")
    parser.add_argument("--uri",      default="bolt://localhost:7687")
    parser.add_argument("--user",     default="neo4j")
    parser.add_argument("--password", default="password")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Preview without writing to neo4j")
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