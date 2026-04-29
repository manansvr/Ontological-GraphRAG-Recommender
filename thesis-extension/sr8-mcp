#!/usr/bin/env python3
import os
import re
import json
import csv
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase

load_dotenv()

mcp = FastMCP("sr8-knowledge-mcp")

DEFAULT_DOC_EXTENSIONS = {".md", ".txt", ".csv", ".owl", ".cypher", ".pdf", ".docx"}
WRITE_KEYWORDS = {
    " create ",
    " merge ",
    " delete ",
    " detach ",
    " remove ",
    " set ",
    " drop ",
    " call dbms",
    " call apoc",
    " load csv",
}


def _doc_roots() -> list[Path]:
    configured = os.getenv("DOC_ROOTS", "")
    roots: list[Path] = []
    if configured:
        for chunk in configured.split(","):
            p = Path(chunk.strip()).expanduser()
            if p.exists() and p.is_dir():
                roots.append(p)

    if roots:
        return roots

    fallback = [
        Path("/Users/manan/Desktop/Honours/thesis-extraction/CSV"),
        Path("/Users/manan/Desktop/Honours/thesis-extraction/Design-Documentation"),
        Path("/Users/manan/Desktop/Honours/thesis-extraction/PDF"),
        Path("/Users/manan/Desktop/Honours/thesis-extraction/Documentation"),
        Path("/Users/manan/Desktop/Honours/thesis-ontology/Documentation"),
    ]
    return [p for p in fallback if p.exists() and p.is_dir()]


def _iter_docs() -> list[Path]:
    found: list[Path] = []
    for root in _doc_roots():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in DEFAULT_DOC_EXTENSIONS:
                found.append(path)
    return found


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _normalize_rule_id(rule_id: str) -> tuple[str, list[str]]:
    raw = rule_id.strip().upper().replace(" ", "")
    # Accept SRP-* aliases and normalize to ADR-* because extracted data uses ADR IDs.
    if raw.startswith("SRP"):
        raw = "ADR" + raw[3:]
    if raw.startswith("ADR") and not raw.startswith("ADR-"):
        raw = raw.replace("ADR", "ADR-", 1)

    m = re.match(r"^ADR-(\d+)$", raw)
    if not m:
        return raw, [raw]

    num = int(m.group(1))
    canonical = f"ADR-{num}"
    variants = [canonical, f"ADR-{num:03d}", f"ADR{num}", f"ADR{num:03d}"]
    dedup: list[str] = []
    for v in variants:
        if v not in dedup:
            dedup.append(v)
    return canonical, dedup


def _extract_text_from_pdf(path: Path) -> str:
    # Try normal text extraction first.
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass

    # OCR fallback can be disabled in env if dependencies are unavailable.
    ocr_enabled = os.getenv("OCR_ENABLED", "true").lower() == "true"
    if not ocr_enabled:
        return ""

    try:
        from pdf2image import convert_from_path
        import pytesseract

        dpi = int(os.getenv("OCR_DPI", "200"))
        pages = convert_from_path(str(path), dpi=dpi)
        ocr_parts: list[str] = []
        for image in pages:
            ocr_parts.append(pytesseract.image_to_string(image))
        return "\n".join(ocr_parts).strip()
    except Exception:
        return ""


def _extract_text_from_docx(path: Path) -> str:
    try:
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text).strip()
    except Exception:
        return ""


def _read_text_content(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_from_pdf(path)
    if suffix == ".docx":
        return _extract_text_from_docx(path)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _line_hits(path: Path, query: str, max_hits: int) -> list[dict[str, Any]]:
    q = _normalize(query)
    results: list[dict[str, Any]] = []

    text = _read_text_content(path)
    if not text:
        return results

    for i, line in enumerate(text.splitlines(), start=1):
        norm_line = _normalize(line)
        if q and q in norm_line:
            results.append(
                {
                    "line": i,
                    "snippet": line.strip()[:500],
                }
            )
            if len(results) >= max_hits:
                break

    return results


def _csv_row_hits(path: Path, query: str, max_hits: int) -> list[dict[str, Any]]:
    q = _normalize(query)
    results: list[dict[str, Any]] = []

    if not q:
        return results

    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                matched_columns: list[str] = []
                snippets: list[str] = []
                for key, value in row.items():
                    cell = (value or "").strip()
                    if cell and q in _normalize(cell):
                        matched_columns.append(key)
                        snippets.append(cell[:220])

                if matched_columns:
                    results.append(
                        {
                            "row": row_idx,
                            "matched_columns": matched_columns,
                            "snippet": " | ".join(snippets)[:500],
                        }
                    )
                    if len(results) >= max_hits:
                        break
    except Exception:
        return []

    return results


def _find_adr_csv_file(adr_number: int) -> Path | None:
    pattern = re.compile(rf"^ADR0*{adr_number}-Requirements\.csv$", re.IGNORECASE)
    for p in _iter_docs():
        if p.suffix.lower() == ".csv" and pattern.match(p.name):
            return p
    return None


def _neo4j_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def _cypher_is_read_only(cypher: str) -> bool:
    normalized = f" {_normalize(cypher)} "
    if not normalized.strip().startswith("match") and not normalized.strip().startswith("with"):
        return False
    return not any(keyword in normalized for keyword in WRITE_KEYWORDS)


def _extraction_root() -> Path:
    configured = os.getenv("EXTRACTION_ROOT", "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.exists() and p.is_dir():
            return p
    return Path("/Users/manan/Desktop/Honours/thesis-extraction")


@mcp.tool()
def list_documents(limit: int = 200) -> str:
    """List indexed local documents available to the model."""
    docs = _iter_docs()[: max(1, min(limit, 500))]
    payload = {
        "count": len(docs),
        "roots": [str(r) for r in _doc_roots()],
        "documents": [str(p) for p in docs],
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def run_extraction_for_requirements(dry_run: bool = False) -> str:
    """Run ADR extraction pipeline before requirements analysis."""
    root = _extraction_root()
    script = root / "Scripts" / "run-extraction.py"
    if not script.exists():
        return json.dumps({"error": f"extraction script not found: {script}"}, indent=2)

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    cmd = [
        "python3",
        str(script),
        "--only",
        "adrs",
        "--uri",
        uri,
        "--user",
        user,
        "--password",
        password,
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=600)
    except Exception as exc:
        return json.dumps({"error": f"failed to run extraction: {exc}"}, indent=2)

    return json.dumps(
        {
            "command": cmd,
            "cwd": str(root),
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "ok": proc.returncode == 0,
        },
        indent=2,
    )


@mcp.tool()
def search_local_documents(query: str, max_files: int = 8, max_hits_per_file: int = 5) -> str:
    """Keyword search over local docs and CSV/Ontology files."""
    query = query.strip()
    if not query:
        return json.dumps({"error": "query must not be empty"}, indent=2)

    files = _iter_docs()
    ranked: list[dict[str, Any]] = []

    for path in files:
        if path.suffix.lower() == ".csv":
            hits = _csv_row_hits(path, query, max_hits_per_file)
            pointer_type = "row"
        else:
            hits = _line_hits(path, query, max_hits_per_file)
            pointer_type = "line"

        if hits:
            ranked.append(
                {
                    "path": str(path),
                    "file": path.name,
                    "pointer_type": pointer_type,
                    "hits": hits,
                    "hit_count": len(hits),
                }
            )

    ranked.sort(key=lambda x: x["hit_count"], reverse=True)
    payload = {
        "query": query,
        "roots": [str(r) for r in _doc_roots()],
        "matches": ranked[: max(1, min(max_files, 30))],
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def suggest_requirement_sources(requirement_text: str, max_files: int = 10, max_hits_per_file: int = 3) -> str:
    """Suggest exact source files (with row/line evidence) for a requirement text."""
    requirement_text = requirement_text.strip()
    if not requirement_text:
        return json.dumps({"error": "requirement_text must not be empty"}, indent=2)

    files = _iter_docs()
    ranked: list[dict[str, Any]] = []

    for path in files:
        if path.suffix.lower() == ".csv":
            hits = _csv_row_hits(path, requirement_text, max_hits_per_file)
            pointer_type = "row"
        else:
            hits = _line_hits(path, requirement_text, max_hits_per_file)
            pointer_type = "line"

        if hits:
            ranked.append(
                {
                    "path": str(path),
                    "file": path.name,
                    "pointer_type": pointer_type,
                    "hits": hits,
                    "hit_count": len(hits),
                    "source_priority": (
                        1
                        if "/CSV/" in str(path)
                        else 2
                        if "/Design-Documentation/" in str(path)
                        else 3
                        if "/PDF/" in str(path)
                        else 4
                    ),
                }
            )

    ranked.sort(key=lambda x: (x["source_priority"], -x["hit_count"], x["path"]))

    payload = {
        "requirement_text": requirement_text,
        "source_order": ["CSV", "Design-Documentation", "PDF", "Other"],
        "matches": ranked[: max(1, min(max_files, 50))],
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def read_document(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """Read a local document by absolute path with line range."""
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return json.dumps({"error": f"file not found: {target}"}, indent=2)

    root_ok = any(str(target).startswith(str(root)) for root in _doc_roots())
    if not root_ok:
        return json.dumps({"error": "path is outside DOC_ROOTS"}, indent=2)

    start_line = max(1, start_line)
    end_line = max(start_line, end_line)

    text = _read_text_content(target)
    if not text:
        return json.dumps({"error": f"failed to read file: {target}"}, indent=2)

    lines = text.splitlines()

    chunk = lines[start_line - 1 : end_line]
    payload = {
        "path": str(target),
        "start_line": start_line,
        "end_line": end_line,
        "content": "\n".join(chunk),
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def query_knowledge_graph(cypher: str, limit: int = 50) -> str:
    """Run a read-only Cypher query against the local Neo4j knowledge graph."""
    if not _cypher_is_read_only(cypher):
        return json.dumps(
            {
                "error": "only read-only Cypher is allowed",
                "hint": "Use MATCH/RETURN queries without write clauses",
            },
            indent=2,
        )

    safe_limit = max(1, min(limit, 500))
    if " limit " not in f" {_normalize(cypher)} ":
        cypher = f"{cypher.rstrip()} LIMIT {safe_limit}"

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                result = session.run(cypher)
                rows = [record.data() for record in result]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"row_count": len(rows), "rows": rows}, indent=2)


@mcp.tool()
def get_adr_requirements(adr_id: str, limit: int = 30) -> str:
    """Fetch extracted essential requirements linked to an ADR ID (e.g., ADR-43)."""
    if not adr_id.strip():
        return json.dumps({"error": "adr_id must not be empty"}, indent=2)

    normalized_id, adr_id_variants = _normalize_rule_id(adr_id)

    query = """
    MATCH (a:AustralianDesignRule)
    WHERE a.hasID IN $adr_id_variants
    MATCH (a)-[rel]->(r)
    WHERE type(rel) IN ['hasExternalEssentialRequirement', 'hasExternalRecommendedRequirement']
    OPTIONAL MATCH (r)-[:hasClause]->(c:Clause)
    RETURN a.hasID AS adr,
                type(rel) AS relationship,
                labels(r) AS requirement_labels,
           r.requirementDescription AS requirement,
           collect(distinct c.hasID) AS clauses
    ORDER BY requirement
    LIMIT $limit
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                result = session.run(
                    query,
                    adr_id_variants=adr_id_variants,
                    limit=max(1, min(limit, 200)),
                )
                rows = [record.data() for record in result]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    # Provide explicit evidence refs so strict citation mode can always cite source paths.
    evidence_refs: list[str] = []
    for row in rows[:5]:
        req = (row.get("requirement") or "").strip()
        if not req:
            continue
        try:
            suggestion = json.loads(suggest_requirement_sources(req, max_files=1, max_hits_per_file=1))
            matches = suggestion.get("matches", [])
            if not matches:
                continue
            top = matches[0]
            hits = top.get("hits", [])
            if not hits:
                continue
            first_hit = hits[0]
            if top.get("pointer_type") == "row" and "row" in first_hit:
                evidence_refs.append(f"{top.get('path', '')} | row {first_hit['row']}")
            elif top.get("pointer_type") == "line" and "line" in first_hit:
                evidence_refs.append(f"{top.get('path', '')} | line {first_hit['line']}")
        except Exception:
            continue

    evidence_refs = list(dict.fromkeys(evidence_refs))

    csv_count = None
    csv_file = None
    m = re.match(r"^ADR-(\d+)$", normalized_id)
    if m:
        csv_path = _find_adr_csv_file(int(m.group(1)))
        if csv_path and csv_path.exists():
            csv_file = str(csv_path)
            try:
                with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
                    csv_count = sum(1 for _ in csv.DictReader(f))
                if csv_count and csv_count > 0:
                    evidence_refs.append(f"{csv_file} | row 2")
            except Exception:
                csv_count = None

    evidence_refs = list(dict.fromkeys(evidence_refs))
    graph_count = len(rows)
    preferred_count = csv_count if csv_count is not None else graph_count

    return json.dumps(
        {
            "adr_id": normalized_id,
            "adr_id_variants": adr_id_variants,
            "count": preferred_count,
            "graph_count": graph_count,
            "csv_count": csv_count,
            "csv_file": csv_file,
            "requirements": rows,
            "evidence_refs": evidence_refs,
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
