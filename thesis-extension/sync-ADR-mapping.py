#!/usr/bin/env python3
"""sync-ADR-mapping.py: build extension mapping reports directly from extracted ADR CSV files.

This script imports rows from thesis-extraction/CSV/ADR*-Requirements.csv and
regenerates:
    - ADR-mapping.csv
    - ADR-mapping.json
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

EXTRACTION_CSV_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "thesis-extraction" / "csv"
OUTPUT_DIR_DEFAULT = Path(__file__).resolve().parent

COLUMN_ALIASES = {
    "adr_id": ["ADR Number", "ADR ID", "ADRID", "ADR Id", "adr_id", "ADR"],
    "adr_name": ["ADR Name", "ADRName", "adr_name"],
    "clause": ["Clause", "Cla", "clause", "Clause No"],
    "req_name": ["Req Name", "ReqName", "Requirement Name"],
    "text": ["Text", "Requirement Text", "text"],
}

OUTPUT_FIELDS = [
    "adr_id",
    "adr_name",
    "requirement_id",
    "requirement_name",
    "risk_level",
    "clause_ids",
    "requirement_text",
    "source_file",
    "source_pointer_type",
    "source_pointer",
    "matched_columns",
    "evidence_snippet",
    "candidate_match_count",
]


def get_col(row: dict, key: str) -> str:
    for alias in COLUMN_ALIASES.get(key, [key]):
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    return ""


def normalize_adr_id(value: str) -> str:
    match = re.search(r"\d+", str(value))
    if not match:
        return ""
    return f"ADR-{int(match.group())}"


def adr_id_from_filename(path: Path) -> str:
    match = re.search(r"ADR\s*0*(\d+)", path.stem, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"ADR-{int(match.group(1))}"


def forward_fill_adr_fields(rows: list[dict]) -> list[dict]:
    current_id = ""
    current_name = ""

    id_header = COLUMN_ALIASES["adr_id"][0]
    name_header = COLUMN_ALIASES["adr_name"][0]

    for row in rows:
        raw_id = get_col(row, "adr_id")
        if raw_id:
            current_id = raw_id
            current_name = get_col(row, "adr_name")

        if not row.get(id_header):
            row[id_header] = current_id
        if not row.get(name_header):
            row[name_header] = current_name

    return rows


def build_rows(extraction_csv_dir: Path) -> list[dict]:
    output_rows: list[dict] = []

    csv_files = sorted(extraction_csv_dir.glob("ADR*-Requirements.csv"))
    for csv_path in csv_files:
        with csv_path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            raw_rows = [{(k or "").strip(): (v or "") for k, v in row.items()} for row in reader]

        if not raw_rows:
            continue

        rows = forward_fill_adr_fields(raw_rows)
        adr_from_file = adr_id_from_filename(csv_path)
        req_counter = 0

        for row_idx, row in enumerate(rows, start=2):
            adr_id = normalize_adr_id(get_col(row, "adr_id")) or adr_from_file
            adr_name = get_col(row, "adr_name")
            clause = get_col(row, "clause")
            req_name = get_col(row, "req_name")
            text = get_col(row, "text")

            # Skip empty rows.
            if not (clause or req_name or text):
                continue

            req_counter += 1
            requirement_id = f"REQ-{adr_id.replace('ADR-', '')}-{req_counter:03d}" if adr_id else f"REQ-UNK-{req_counter:03d}"

            output_rows.append(
                {
                    "adr_id": adr_id,
                    "adr_name": adr_name,
                    "requirement_id": requirement_id,
                    "requirement_name": req_name,
                    "risk_level": "High",
                    "clause_ids": clause,
                    "requirement_text": text,
                    "source_file": str(csv_path),
                    "source_pointer_type": "row",
                    "source_pointer": str(row_idx),
                    "matched_columns": "Text" if text else "",
                    "evidence_snippet": text[:260],
                    "candidate_match_count": 1,
                }
            )

    return output_rows


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    counts_by_adr: dict[str, int] = defaultdict(int)
    for row in rows:
        adr_id = row.get("adr_id", "")
        if adr_id:
            counts_by_adr[adr_id] += 1

    payload = {
        "total_requirements": len(rows),
        "total_adrs": len(counts_by_adr),
        "no_match_requirements": 0,
        "counts_by_adr": dict(sorted(counts_by_adr.items(), key=lambda kv: int(kv[0].split("-")[1]))),
        "rows": rows,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate ADR mapping reports from extraction CSVs")
    parser.add_argument(
        "--extraction-csv-dir",
        default=str(EXTRACTION_CSV_DIR_DEFAULT),
        help="Directory containing ADR*-Requirements.csv files",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR_DEFAULT),
        help="Output directory for ADR-mapping.csv/json (defaults to thesis-extension root)",
    )
    args = parser.parse_args()

    extraction_csv_dir = Path(args.extraction_csv_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()

    if not extraction_csv_dir.exists() or not extraction_csv_dir.is_dir():
        raise SystemExit(f"Extraction CSV directory not found: {extraction_csv_dir}")

    rows = build_rows(extraction_csv_dir)

    csv_out = output_dir / "ADR-mapping.csv"
    json_out = output_dir / "ADR-mapping.json"

    write_csv(rows, csv_out)
    write_json(rows, json_out)

    print(f"Wrote {len(rows)} rows")
    print(f"CSV:  {csv_out}")
    print(f"JSON: {json_out}")


if __name__ == "__main__":
    main()
