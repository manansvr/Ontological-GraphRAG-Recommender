#!/usr/bin/env python3
"""propose-fmea-links.py: suggest ADR requirements that an FMEA requirement may correspond to.

FMEA Requirement nodes (from the "Requirement Mapping" sheet of the FMEA workbook) are not
linked to the ADR ExtractedEssentialRequirement nodes, and nothing links them
automatically. This script only proposes candidates for a person to review: it never
connects to Neo4j and never writes to the graph.

For each FMEA requirement name it ranks the ADR requirements (as extract-ADR.py would
create them from thesis-extraction/csv/) by name overlap: the Jaccard overlap of
lower-cased content words, stop-words removed, from similarity.py, the same function
sr8-mcp's get_similar_assigned_requirements uses for its name_overlap component (clause
adjacency does not apply: FMEA requirements have no ADR clause). The top --top candidates
with overlap above --min-overlap are written to a CSV with empty decision, reviewer and
notes columns for the reviewer to fill in.

Usage (offline):
    python3 thesis-extension/scripts/propose-fmea-links.py
    python3 thesis-extension/scripts/propose-fmea-links.py --top 5 --output review.csv
"""

import argparse
import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import openpyxl

EXT_DIR = Path(__file__).resolve().parent.parent
EXTRACTION = EXT_DIR.parent / "thesis-extraction"
DEFAULT_WORKBOOK = EXTRACTION / "Brake_System_Failure_Mode_Data.xlsx"
REQUIREMENT_SHEET = "Requirement Mapping"
FIELDS = ["fmea_requirement", "fmea_components", "fmea_sheet_rows", "rank", "candidate_req_id",
          "candidate_adr", "candidate_name", "candidate_clause", "name_overlap", "shared_words",
          "decision", "reviewer", "notes"]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fmea_requirements(workbook: Path) -> dict:
    """{requirement name: {"components": [...], "rows": [...]}} from the Requirement Mapping sheet."""
    ws = openpyxl.load_workbook(workbook, data_only=True, read_only=True)[REQUIREMENT_SHEET]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h else "" for h in rows[0]]
    out: dict = {}
    for row_number, row in enumerate(rows[1:], start=2):
        record = dict(zip(headers, row))
        name = str(record.get("Requirement") or "").strip()
        component = str(record.get("Component") or "").strip()
        if not name:
            continue
        entry = out.setdefault(name, {"components": [], "rows": []})
        if component and component not in entry["components"]:
            entry["components"].append(component)
        entry["rows"].append(row_number)
    return out


def adr_requirements(csv_folder: Path) -> list:
    """Requirements extract-ADR.py creates, as dicts with req_id, adr_id, name, clause."""
    adr = _load("extract_adr_for_proposals", EXTRACTION / "Scripts" / "extract-ADR.py")
    out = []
    for path in sorted(csv_folder.glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = adr.forward_fill_adr_id([{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)])
        for plan in adr.plan_rows(rows):
            if plan["req_id"]:
                out.append({"req_id": plan["req_id"], "adr_id": plan["adr_id"],
                            "name": plan["req_name"], "clause": plan["clause_num"]})
    return out


def propose(fmea: dict, adr_reqs: list, top: int, min_overlap: float, similarity: Any) -> list:
    rows = []
    for name, entry in fmea.items():
        words = similarity.name_words(name)
        scored = []
        for req in adr_reqs:
            overlap = similarity.name_overlap(name, req["name"])
            if overlap > min_overlap:
                scored.append((overlap, req))
        scored.sort(key=lambda item: (-item[0], item[1]["req_id"]))
        for rank, (overlap, req) in enumerate(scored[:top], start=1):
            rows.append({
                "fmea_requirement": name,
                "fmea_components": ";".join(entry["components"]),
                "fmea_sheet_rows": ";".join(str(r) for r in entry["rows"]),
                "rank": rank,
                "candidate_req_id": req["req_id"],
                "candidate_adr": req["adr_id"],
                "candidate_name": req["name"],
                "candidate_clause": req["clause"],
                "name_overlap": round(overlap, 4),
                "shared_words": " ".join(sorted(words & similarity.name_words(req["name"]))),
                "decision": "", "reviewer": "", "notes": "",
            })
    return rows


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Propose FMEA-to-ADR requirement links for human review (offline).")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--adr-csvs", type=Path, default=EXTRACTION / "csv")
    parser.add_argument("--top", type=int, default=3, help="candidates per FMEA requirement (default 3)")
    parser.add_argument("--min-overlap", type=float, default=0.0,
                        help="only candidates with name overlap above this (default 0.0)")
    parser.add_argument("--output", type=Path,
                        default=EXT_DIR / "logs" / f"fmea-link-candidates-{date.today().isoformat()}.csv")
    args = parser.parse_args(argv)

    similarity = _load("requirement_similarity", EXT_DIR / "similarity.py")
    fmea = fmea_requirements(args.workbook)
    rows = propose(fmea, adr_requirements(args.adr_csvs), args.top, args.min_overlap, similarity)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    without = sorted(set(fmea) - {r["fmea_requirement"] for r in rows})
    print(f"{len(fmea)} FMEA requirements; {len(rows)} candidate link(s) written to {args.output}")
    if without:
        print(f"{len(without)} FMEA requirement(s) with no candidate: {', '.join(without)}")
    print("Nothing was written to the graph. Fill in decision (accept / reject), reviewer and notes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
