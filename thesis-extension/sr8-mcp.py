#!/usr/bin/env python3
import os
import re
import json
import csv
import subprocess
import importlib.util as _importlib_util
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase

load_dotenv()

# ── RL reward constants ────────────────────────────────────────────────────────
REWARD_CONFIRMED = 1.0
REWARD_REJECTED = -1.0
REWARD_MODIFIED = 0.5
REWARD_IGNORED = -0.3
PENALTY_OVERCONFIDENT = -2.0  # applied when confidence > 0.8 and recommendation was rejected

mcp = FastMCP("sr8-knowledge-mcp")

# Derive the project root from this file's location so fallback paths are portable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RL_MODEL_PATH = Path(__file__).resolve().parent / ".rl-model.json"

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


# ── Path helpers ───────────────────────────────────────────────────────────────

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
    # Relative fallbacks derived from this repository's layout.
    fallback = [
        _PROJECT_ROOT / "thesis-extraction" / "csv",
        _PROJECT_ROOT / "thesis-extraction" / "Design-Documentation",
        _PROJECT_ROOT / "thesis-extraction" / "PDF",
        _PROJECT_ROOT / "thesis-extraction" / "Documentation",
        _PROJECT_ROOT / "thesis-ontology" / "Documentation",
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
    # Accept SRP-* aliases and normalise to ADR-* because extracted data uses ADR IDs.
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
            results.append({"line": i, "snippet": line.strip()[:500]})
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
                    results.append({
                        "row": row_idx,
                        "matched_columns": matched_columns,
                        "snippet": " | ".join(snippets)[:500],
                    })
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
    # Only MATCH-starting queries are permitted; dropping the WITH allowance
    # prevents a WITH … CREATE bypass where the write keyword check would still
    # catch CREATE but an attacker could craft edge cases with sub-clauses.
    if not normalized.strip().startswith("match"):
        return False
    return not any(keyword in normalized for keyword in WRITE_KEYWORDS)


def _extraction_root() -> Path:
    configured = os.getenv("EXTRACTION_ROOT", "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.exists() and p.is_dir():
            return p
    return _PROJECT_ROOT / "thesis-extraction"


# ── RL agent bridge ────────────────────────────────────────────────────────────

_rl_agent: Any = None
_rl_agent_loaded: bool = False
_rl_transition_cls: Any = None


def _load_rl_agent() -> Any:
    global _rl_agent, _rl_agent_loaded, _rl_transition_cls
    if _rl_agent_loaded:
        return _rl_agent
    _rl_agent_loaded = True
    module_path = Path(__file__).resolve().with_name("reinforcemnt-learning.py")
    if not module_path.exists():
        return None
    try:
        spec = _importlib_util.spec_from_file_location("rl_module", module_path)
        if not spec or not spec.loader:
            return None
        module = _importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _rl_transition_cls = getattr(module, "Transition")
        q_cls = getattr(module, "QLearningAgent")
        _rl_agent = q_cls.load(_RL_MODEL_PATH) if _RL_MODEL_PATH.exists() else q_cls()
    except Exception:
        _rl_agent = None
    return _rl_agent


def _rl_adjust_confidence(base: float) -> float:
    """Nudge a confidence score using the Q-learning agent's current policy."""
    agent = _load_rl_agent()
    if not agent:
        return base
    actions = ["increase_confidence", "keep_confidence", "decrease_confidence"]
    try:
        action = agent.choose_action("inference", actions)
        if action == "increase_confidence":
            return min(1.0, base + 0.1)
        if action == "decrease_confidence":
            return max(0.0, base - 0.1)
    except Exception:
        pass
    return base


def _rl_update(feedback_action: str, reward: float) -> None:
    """Update the RL agent from a human-feedback event and persist the model."""
    agent = _load_rl_agent()
    if not agent or _rl_transition_cls is None:
        return
    try:
        actions = ["increase_confidence", "keep_confidence", "decrease_confidence"]
        rl_map = {
            "confirmed": "increase_confidence",
            "rejected": "decrease_confidence",
            "modified": "keep_confidence",
            "ignored": "decrease_confidence",
        }
        rl_action = rl_map.get(feedback_action, "keep_confidence")
        t = _rl_transition_cls("inference", rl_action, reward, "inference", actions)
        agent.update(t)
        agent.decay_exploration()
        agent.save(_RL_MODEL_PATH)
    except Exception:
        pass


# ── Existing tools (unchanged) ─────────────────────────────────────────────────

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

    cmd = ["python3", str(script), "--only", "adrs", "--uri", uri, "--user", user, "--password", password]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=600)
    except Exception as exc:
        return json.dumps({"error": f"failed to run extraction: {exc}"}, indent=2)

    return json.dumps({
        "command": cmd,
        "cwd": str(root),
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
        "ok": proc.returncode == 0,
    }, indent=2)


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
            ranked.append({
                "path": str(path),
                "file": path.name,
                "pointer_type": pointer_type,
                "hits": hits,
                "hit_count": len(hits),
            })

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
            ranked.append({
                "path": str(path),
                "file": path.name,
                "pointer_type": pointer_type,
                "hits": hits,
                "hit_count": len(hits),
                "source_priority": (
                    1 if "/csv/" in str(path).lower()
                    else 2 if "/design-documentation/" in str(path).lower()
                    else 3 if "/pdf/" in str(path).lower()
                    else 4
                ),
            })

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
        return json.dumps({
            "error": "only read-only Cypher is allowed",
            "hint": "Use MATCH/RETURN queries without write clauses",
        }, indent=2)

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

    return json.dumps({
        "adr_id": normalized_id,
        "adr_id_variants": adr_id_variants,
        "count": preferred_count,
        "graph_count": graph_count,
        "csv_count": csv_count,
        "csv_file": csv_file,
        "requirements": rows,
        "evidence_refs": evidence_refs,
    }, indent=2)


# ── Phase 1: GraphRAG tools ────────────────────────────────────────────────────

@mcp.tool()
def get_project(project_id: str) -> str:
    """Return project metadata, assigned requirements, ADR sources, and verification status."""
    if not project_id.strip():
        return json.dumps({"error": "project_id must not be empty"}, indent=2)

    meta_query = """
    MATCH (p:Project {projectID: $pid})
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    OPTIONAL MATCH (a:AustralianDesignRule)-[:assignedToDepartment]->(d)
    WHERE (a)-[:hasExternalEssentialRequirement]->(:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p)
    RETURN p.projectID AS project_id,
           p.projectName AS project_name,
           collect(DISTINCT asm.assemblyID)[0] AS assembly_id,
           collect(DISTINCT asm.assemblyName)[0] AS assembly_name,
           collect(DISTINCT d.hasName)[0] AS department
    """

    req_query = """
    MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->(p:Project {projectID: $pid})
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           a.hasName AS adr_name,
           coalesce(a.isVerified, false) AS adr_verified
    ORDER BY a.hasID, r.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                meta_row = session.run(meta_query, pid=project_id).single()
                if not meta_row:
                    return json.dumps({"error": f"Project '{project_id}' not found."}, indent=2)
                meta = dict(meta_row)
                reqs = [record.data() for record in session.run(req_query, pid=project_id)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({**meta, "requirement_count": len(reqs), "requirements": reqs}, indent=2)


@mcp.tool()
def get_adr(adr_id: str) -> str:
    """Return ADR overview: name, clause count, requirement count, applicable/verified counts, and assigned projects."""
    if not adr_id.strip():
        return json.dumps({"error": "adr_id must not be empty"}, indent=2)

    _, variants = _normalize_rule_id(adr_id)

    query = """
    MATCH (a:AustralianDesignRule)
    WHERE a.hasID IN $variants
    OPTIONAL MATCH (a)-[:hasClause]->(c:Clause)
    OPTIONAL MATCH (a)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    RETURN a.hasID AS adr_id,
           a.hasName AS adr_name,
           coalesce(a.isVerified, false) AS is_verified,
           count(DISTINCT c) AS clause_count,
           count(DISTINCT r) AS requirement_count,
           count(DISTINCT CASE WHEN r.isApplicable = true THEN r END) AS applicable_count,
           count(DISTINCT CASE WHEN r.isApplicable = true AND a.isVerified = true THEN r END) AS verified_count,
           collect(DISTINCT p.projectID) AS assigned_projects
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(query, variants=variants).single()
                if not row:
                    return json.dumps({"error": f"ADR '{adr_id}' not found."}, indent=2)
                return json.dumps(dict(row), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


@mcp.tool()
def get_assembly(assembly_id: str) -> str:
    """Return assembly details: all projects within it and a compliance summary across those projects."""
    if not assembly_id.strip():
        return json.dumps({"error": "assembly_id must not be empty"}, indent=2)

    query = """
    MATCH (asm {assemblyID: $assembly_id})
    OPTIONAL MATCH (p:Project)-[:partOfAssembly]->(asm)
    OPTIONAL MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->(p)
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    WITH asm,
         collect(DISTINCT {id: p.projectID, name: p.projectName}) AS projects,
         count(DISTINCT r) AS total_reqs,
         count(DISTINCT CASE WHEN r.isApplicable = true THEN r END) AS applicable_reqs,
         count(DISTINCT CASE WHEN r.isApplicable = true AND r.isVerified = true THEN r END) AS verified_reqs
    RETURN asm.assemblyID AS assembly_id,
           asm.assemblyName AS assembly_name,
           projects,
           total_reqs,
           applicable_reqs,
           verified_reqs,
           CASE WHEN applicable_reqs > 0
                THEN round(100.0 * verified_reqs / applicable_reqs, 1)
                ELSE 0.0 END AS verification_pct
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(query, assembly_id=assembly_id).single()
                if not row:
                    return json.dumps({
                        "error": f"Assembly '{assembly_id}' not found. "
                                 "Use list_all_projects() to see available assemblies.",
                    }, indent=2)
                return json.dumps(dict(row), indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


@mcp.tool()
def search_requirements(keyword: str) -> str:
    """Search requirementName and requirementDescription across all ExtractedEssentialRequirement nodes."""
    if not keyword.strip():
        return json.dumps({"error": "keyword must not be empty"}, indent=2)

    query = """
    MATCH (r:ExtractedEssentialRequirement)
    WHERE toLower(r.requirementName) CONTAINS toLower($kw)
       OR toLower(r.requirementDescription) CONTAINS toLower($kw)
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.requirementDescription AS req_description,
           r.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           a.hasName AS adr_name,
           collect(DISTINCT p.projectID) AS assigned_projects
    ORDER BY a.hasID, r.hasID
    LIMIT 50
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, kw=keyword)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"keyword": keyword, "match_count": len(rows), "matches": rows}, indent=2)


@mcp.tool()
def list_all_projects() -> str:
    """Return all project IDs and names grouped by assembly."""
    query = """
    MATCH (p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    RETURN p.projectID AS project_id,
           p.projectName AS project_name,
           asm.assemblyID AS assembly_id,
           asm.assemblyName AS assembly_name
    ORDER BY assembly_id, project_id
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    # Group by assembly for convenience.
    grouped: dict[str, Any] = {}
    ungrouped: list[dict] = []
    for row in rows:
        asm = row.get("assembly_id")
        if asm:
            grouped.setdefault(asm, {"assembly_name": row.get("assembly_name"), "projects": []})
            grouped[asm]["projects"].append({"id": row["project_id"], "name": row["project_name"]})
        else:
            ungrouped.append({"id": row["project_id"], "name": row["project_name"]})

    return json.dumps({
        "total_projects": len(rows),
        "by_assembly": grouped,
        "no_assembly": ungrouped,
    }, indent=2)


@mcp.tool()
def list_all_adrs() -> str:
    """Return all ADR IDs and names with clause and requirement counts."""
    query = """
    MATCH (a:AustralianDesignRule)
    OPTIONAL MATCH (a)-[:hasClause]->(c:Clause)
    OPTIONAL MATCH (a)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
    RETURN a.hasID AS adr_id,
           a.hasName AS adr_name,
           coalesce(a.isVerified, false) AS is_verified,
           count(DISTINCT c) AS clause_count,
           count(DISTINCT r) AS requirement_count,
           count(DISTINCT CASE WHEN r.isApplicable = true THEN r END) AS applicable_count
    ORDER BY adr_id
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"total_adrs": len(rows), "adrs": rows}, indent=2)


# ── Phase 2: Compliance gap detection ─────────────────────────────────────────

@mcp.tool()
def get_compliance_gaps(
    project_id: str | None = None,
    adr_id: str | None = None,
    assembly_id: str | None = None,
) -> str:
    """Call this proactively when the user asks about any project, assembly, or ADR — do not wait to be asked about compliance specifically.

    Finds all applicable requirements that are not yet verified, optionally filtered by
    project, ADR, or assembly. Returns results grouped by project.
    """
    adr_variants: list[str] | None = None
    if adr_id:
        _, adr_variants = _normalize_rule_id(adr_id)

    query = """
    MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
    WHERE r.isApplicable = true
      AND (r.isVerified = false OR r.isVerified IS NULL)
      AND ($adr_variants IS NULL OR a.hasID IN $adr_variants)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    WITH a, r, p, asm
    WHERE ($project_id IS NULL OR (p IS NOT NULL AND p.projectID = $project_id))
      AND ($assembly_id IS NULL OR (asm IS NOT NULL AND asm.assemblyID = $assembly_id))
    RETURN a.hasID AS adr_id,
           a.hasName AS adr_name,
           r.hasID AS req_id,
           r.requirementName AS req_name,
           r.requirementDescription AS req_description,
           r.hasRiskLevel AS risk_level,
           p.projectID AS project_id,
           p.projectName AS project_name
    ORDER BY a.hasID, r.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(
                    query,
                    project_id=project_id,
                    adr_variants=adr_variants,
                    assembly_id=assembly_id,
                )]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    # Group by project for readability.
    by_project: dict[str, Any] = {}
    no_project: list[dict] = []
    for row in rows:
        pid = row.get("project_id")
        entry = {
            "adr_id": row["adr_id"],
            "adr_name": row["adr_name"],
            "req_id": row["req_id"],
            "req_name": row["req_name"],
            "risk_level": row["risk_level"],
        }
        if pid:
            by_project.setdefault(pid, {"project_name": row.get("project_name"), "gaps": []})
            by_project[pid]["gaps"].append(entry)
        else:
            no_project.append(entry)

    return json.dumps({
        "filter": {"project_id": project_id, "adr_id": adr_id, "assembly_id": assembly_id},
        "total_gaps": len(rows),
        "by_project": by_project,
        "unassigned_gaps": no_project,
    }, indent=2)


@mcp.tool()
def get_verification_progress(
    project_id: str | None = None,
    assembly_id: str | None = None,
) -> str:
    """Return verification progress: total applicable requirements, verified, unverified, and completion percentage.

    No filters = graph-wide progress. Filter by project_id or assembly_id to scope the report.
    """
    query = """
    MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
    WHERE r.isApplicable = true
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    WITH a, r, p, asm
    WHERE ($project_id IS NULL OR (p IS NOT NULL AND p.projectID = $project_id))
      AND ($assembly_id IS NULL OR (asm IS NOT NULL AND asm.assemblyID = $assembly_id))
    RETURN count(r) AS total_applicable,
           count(CASE WHEN r.isVerified = true THEN 1 END) AS total_verified,
           count(CASE WHEN r.isVerified = false OR r.isVerified IS NULL THEN 1 END) AS total_unverified
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(query, project_id=project_id, assembly_id=assembly_id).single()
                if not row:
                    return json.dumps({"error": "No data found."}, indent=2)
                data = dict(row)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    total = data["total_applicable"]
    verified = data["total_verified"]
    pct = round(100.0 * verified / total, 1) if total > 0 else 0.0

    return json.dumps({
        "filter": {"project_id": project_id, "assembly_id": assembly_id},
        "total_applicable": total,
        "total_verified": verified,
        "total_unverified": data["total_unverified"],
        "completion_pct": pct,
    }, indent=2)


@mcp.tool()
def get_highest_risk_gaps() -> str:
    """Return the top 10 unverified applicable requirements ranked by number of projects affected."""
    query = """
    MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
    WHERE r.isApplicable = true
      AND (r.isVerified = false OR r.isVerified IS NULL)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    WITH r, a,
         [x IN collect(DISTINCT p.projectID) WHERE x IS NOT NULL] AS projects,
         [x IN collect(DISTINCT asm.assemblyID) WHERE x IS NOT NULL] AS assemblies
    ORDER BY size(projects) DESC, a.hasID, r.hasID
    LIMIT 10
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.hasRiskLevel AS risk_level,
           a.hasID AS adr_id,
           a.hasName AS adr_name,
           projects AS affected_projects,
           assemblies AS affected_assemblies,
           size(projects) AS project_count
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"top_risk_gaps": rows, "count": len(rows)}, indent=2)


# ── Phase 3: Interface risk analysis ──────────────────────────────────────────

@mcp.tool()
def get_cross_assembly_requirements() -> str:
    """Find ADRs whose requirements span more than one assembly; returns ADR, affected assemblies, and project counts."""
    query = """
    MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p:Project)-[:partOfAssembly]->(asm)
    WITH a, collect(DISTINCT asm.assemblyID) AS assemblies, collect(DISTINCT p.projectID) AS projects
    WHERE size(assemblies) > 1
    OPTIONAL MATCH (a)-[:hasExternalEssentialRequirement]->(r2:ExtractedEssentialRequirement)
    RETURN a.hasID AS adr_id,
           a.hasName AS adr_name,
           assemblies AS affected_assemblies,
           size(assemblies) AS assembly_count,
           projects AS affected_projects,
           count(DISTINCT r2) AS total_requirements
    ORDER BY assembly_count DESC, a.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "cross_assembly_adrs": rows,
        "count": len(rows),
        "note": "Empty result means no assembly nodes exist yet or no ADRs span multiple assemblies.",
    }, indent=2)


@mcp.tool()
def get_assembly_dependencies(assembly_id: str) -> str:
    """Return all assemblies that the given assembly shares ADR requirements with, and the requirements creating the coupling."""
    if not assembly_id.strip():
        return json.dumps({"error": "assembly_id must not be empty"}, indent=2)

    query = """
    MATCH (asm1 {assemblyID: $assembly_id})<-[:partOfAssembly]-(p1:Project)
          <-[:assignedToProject]-(r:ExtractedEssentialRequirement)
          <-[:hasExternalEssentialRequirement]-(a:AustralianDesignRule)
          -[:hasExternalEssentialRequirement]->(r2:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p2:Project)-[:partOfAssembly]->(asm2)
    WHERE asm2.assemblyID <> $assembly_id
    WITH asm2.assemblyID AS other_assembly,
         asm2.assemblyName AS other_assembly_name,
         a.hasID AS adr_id,
         collect(DISTINCT {req_id: r.hasID, req_name: r.requirementName}) AS coupling_reqs
    RETURN other_assembly,
           other_assembly_name,
           adr_id,
           coupling_reqs,
           size(coupling_reqs) AS shared_req_count
    ORDER BY shared_req_count DESC
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, assembly_id=assembly_id)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "assembly_id": assembly_id,
        "dependencies": rows,
        "dependency_count": len(rows),
    }, indent=2)


@mcp.tool()
def get_shared_requirements(project_id_1: str, project_id_2: str) -> str:
    """Return requirements that both projects must satisfy, with ADR sources and verification status for each."""
    if not project_id_1.strip() or not project_id_2.strip():
        return json.dumps({"error": "Both project IDs must be provided."}, indent=2)

    query = """
    MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r1:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p1:Project {projectID: $pid1})
    MATCH (a)-[:hasExternalEssentialRequirement]->(r2:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p2:Project {projectID: $pid2})
    RETURN a.hasID AS adr_id,
           a.hasName AS adr_name,
           coalesce(a.isVerified, false) AS adr_verified,
           r1.hasID AS req_id_project1,
           r1.requirementName AS req_name_project1,
           r1.isApplicable AS applicable_project1,
           r2.hasID AS req_id_project2,
           r2.requirementName AS req_name_project2,
           r2.isApplicable AS applicable_project2
    ORDER BY a.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, pid1=project_id_1, pid2=project_id_2)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "project_1": project_id_1,
        "project_2": project_id_2,
        "shared_adr_count": len(rows),
        "shared_requirements": rows,
    }, indent=2)


@mcp.tool()
def get_interface_risk_report() -> str:
    """Full interface risk report across all assemblies: shared requirements, ADR sources, and verification mismatches."""
    query = """
    MATCH (asm1)<-[:partOfAssembly]-(p1:Project)
          <-[:assignedToProject]-(r1:ExtractedEssentialRequirement)
          <-[:hasExternalEssentialRequirement]-(a:AustralianDesignRule)
          -[:hasExternalEssentialRequirement]->(r2:ExtractedEssentialRequirement)
          -[:assignedToProject]->(p2:Project)-[:partOfAssembly]->(asm2)
    WHERE asm1.assemblyID < asm2.assemblyID
    WITH asm1.assemblyID AS assembly_a,
         asm2.assemblyID AS assembly_b,
         a.hasID AS adr_id,
         a.hasName AS adr_name,
         collect(DISTINCT r1.hasID) AS reqs_in_a,
         collect(DISTINCT r2.hasID) AS reqs_in_b,
         count(CASE WHEN r1.isVerified = false OR r1.isVerified IS NULL THEN 1 END) +
         count(CASE WHEN r2.isVerified = false OR r2.isVerified IS NULL THEN 1 END) AS unverified_count
    RETURN assembly_a,
           assembly_b,
           adr_id,
           adr_name,
           reqs_in_a,
           reqs_in_b,
           size(reqs_in_a) + size(reqs_in_b) AS total_shared,
           unverified_count,
           CASE WHEN unverified_count > 0 THEN 'RISK: unverified requirements on interface'
                ELSE 'OK'
           END AS risk_flag
    ORDER BY assembly_a, assembly_b, adr_id
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    risk_rows = [r for r in rows if r.get("risk_flag", "").startswith("RISK")]
    return json.dumps({
        "total_interface_pairs": len(rows),
        "risk_count": len(risk_rows),
        "interfaces": rows,
    }, indent=2)


# ── Phase 4: Requirement propagation inference ─────────────────────────────────

@mcp.tool()
def get_unassigned_requirements() -> str:
    """Call when user asks about gaps, missing assignments, or extending the knowledge base.

    Returns all ExtractedEssentialRequirement nodes that have no assignedToProject relationship.
    """
    query = """
    MATCH (r:ExtractedEssentialRequirement)
    WHERE NOT (r)-[:assignedToProject]->()
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    OPTIONAL MATCH (a)-[:hasClause]->(c:Clause)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.requirementDescription AS req_description,
           r.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           a.hasName AS adr_name,
           collect(DISTINCT c.hasID) AS clause_ids
    ORDER BY a.hasID, r.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "unassigned_count": len(rows),
        "unassigned_requirements": rows,
    }, indent=2)


@mcp.tool()
def get_similar_assigned_requirements(requirement_id: str) -> str:
    """Find the 5 most similar requirements that already have project assignments.

    Similarity is based on: same ADR source, adjacent clause ordering, and overlapping
    words in requirementName. Returns matches with their assigned projects.
    """
    if not requirement_id.strip():
        return json.dumps({"error": "requirement_id must not be empty"}, indent=2)

    query = """
    MATCH (target:ExtractedEssentialRequirement {hasID: $req_id})
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(target)
    WITH target, a
    MATCH (a)-[:hasExternalEssentialRequirement]->(similar:ExtractedEssentialRequirement)
    WHERE similar.hasID <> $req_id
      AND (similar)-[:assignedToProject]->()
    OPTIONAL MATCH (similar)-[:assignedToProject]->(p:Project)
    WITH similar, a, collect(DISTINCT p.projectID) AS projects
    RETURN similar.hasID AS req_id,
           similar.requirementName AS req_name,
           similar.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           projects AS assigned_projects
    ORDER BY similar.hasID
    LIMIT 5
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, req_id=requirement_id)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "source_requirement_id": requirement_id,
        "similar_count": len(rows),
        "similar_requirements": rows,
    }, indent=2)


@mcp.tool()
def write_inferred_project_link(
    requirement_id: str,
    project_id: str,
    confidence: float,
    reasoning: str,
) -> str:
    """Write a suggestedProject relationship from an unassigned requirement to a project.

    NEVER creates assignedToProject — only suggestedProject. The confidence score is
    nudged by the RL agent's current policy before being stored.
    """
    if not requirement_id.strip() or not project_id.strip():
        return json.dumps({"error": "requirement_id and project_id must not be empty."}, indent=2)
    if not 0.0 <= confidence <= 1.0:
        return json.dumps({"error": "confidence must be between 0.0 and 1.0."}, indent=2)

    adjusted_confidence = _rl_adjust_confidence(confidence)

    query = """
    MATCH (r:ExtractedEssentialRequirement {hasID: $req_id})
    MATCH (p:Project {projectID: $project_id})
    MERGE (r)-[rel:suggestedProject]->(p)
    SET rel.confidence = $confidence,
        rel.reasoning = $reasoning,
        rel.inferredBy = 'Ollama-MCP',
        rel.inferredAt = datetime()
    RETURN r.hasID AS req_id, p.projectID AS project_id, rel.confidence AS stored_confidence
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(
                    query,
                    req_id=requirement_id,
                    project_id=project_id,
                    confidence=adjusted_confidence,
                    reasoning=reasoning,
                ).single()
                if not row:
                    return json.dumps({"error": "Requirement or Project not found."}, indent=2)
                return json.dumps({
                    "status": "written",
                    "req_id": row["req_id"],
                    "project_id": row["project_id"],
                    "original_confidence": confidence,
                    "adjusted_confidence": adjusted_confidence,
                    "reasoning": reasoning,
                }, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


@mcp.tool()
def get_inferred_links() -> str:
    """Return all suggestedProject relationships with confidence, reasoning, and timestamp."""
    query = """
    MATCH (r:ExtractedEssentialRequirement)-[rel:suggestedProject]->(p:Project)
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           p.projectID AS project_id,
           p.projectName AS project_name,
           rel.confidence AS confidence,
           rel.reasoning AS reasoning,
           rel.inferredBy AS inferred_by,
           toString(rel.inferredAt) AS inferred_at,
           a.hasID AS adr_id
    ORDER BY rel.confidence DESC
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"inferred_link_count": len(rows), "inferred_links": rows}, indent=2)


@mcp.tool()
def promote_inferred_link(requirement_id: str, project_id: str) -> str:
    """Convert a suggestedProject relationship into a confirmed assignedToProject relationship.

    Adds promotedAt timestamp and promotedBy: 'human-review'. The suggestedProject
    relationship is removed once promoted.
    """
    if not requirement_id.strip() or not project_id.strip():
        return json.dumps({"error": "requirement_id and project_id must not be empty."}, indent=2)

    query = """
    MATCH (r:ExtractedEssentialRequirement {hasID: $req_id})
    MATCH (p:Project {projectID: $project_id})
    MATCH (r)-[suggested:suggestedProject]->(p)
    MERGE (r)-[confirmed:assignedToProject]->(p)
    SET confirmed.promotedAt = datetime(),
        confirmed.promotedBy = 'human-review',
        confirmed.promotedFromConfidence = suggested.confidence
    DELETE suggested
    RETURN r.hasID AS req_id, p.projectID AS project_id
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(query, req_id=requirement_id, project_id=project_id).single()
                if not row:
                    return json.dumps({
                        "error": f"No suggestedProject relationship found between '{requirement_id}' and '{project_id}'.",
                    }, indent=2)
                return json.dumps({
                    "status": "promoted",
                    "req_id": row["req_id"],
                    "project_id": row["project_id"],
                    "message": "suggestedProject converted to assignedToProject with promotedBy='human-review'.",
                }, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


# ── Phase 5: Change impact analysis ───────────────────────────────────────────

@mcp.tool()
def get_requirements_by_keyword(keyword: str) -> str:
    """Search requirementName, requirementDescription, and clauseText for a keyword.

    Returns matches with ADR, clause number, assigned projects, and assemblies.
    """
    if not keyword.strip():
        return json.dumps({"error": "keyword must not be empty"}, indent=2)

    query = """
    MATCH (r:ExtractedEssentialRequirement)
    WHERE toLower(r.requirementName) CONTAINS toLower($kw)
       OR toLower(r.requirementDescription) CONTAINS toLower($kw)
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    OPTIONAL MATCH (a)-[:hasClause]->(c:Clause)
    WHERE toLower(c.clauseText) CONTAINS toLower($kw)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           collect(DISTINCT c.hasID) AS matching_clauses,
           collect(DISTINCT p.projectID) AS assigned_projects,
           collect(DISTINCT asm.assemblyID) AS assemblies
    ORDER BY a.hasID, r.hasID
    LIMIT 50
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, kw=keyword)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"keyword": keyword, "match_count": len(rows), "matches": rows}, indent=2)


@mcp.tool()
def get_requirement_chain(requirement_id: str) -> str:
    """Traverse the full chain for a requirement: AustralianDesignRule → Clause → ExtractedEssentialRequirement → Project → Assembly."""
    if not requirement_id.strip():
        return json.dumps({"error": "requirement_id must not be empty"}, indent=2)

    query = """
    MATCH (r:ExtractedEssentialRequirement {hasID: $req_id})
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    OPTIONAL MATCH (a)-[:hasClause]->(c:Clause)
    OPTIONAL MATCH (r)-[:assignedToProject]->(p:Project)
    OPTIONAL MATCH (p)-[:partOfAssembly]->(asm)
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.requirementDescription AS req_description,
           r.isApplicable AS is_applicable,
           a.hasID AS adr_id,
           a.hasName AS adr_name,
           coalesce(a.isVerified, false) AS adr_verified,
           collect(DISTINCT {clause_id: c.hasID, clause_name: c.hasName, clause_text: c.clauseText}) AS clauses,
           collect(DISTINCT {project_id: p.projectID, project_name: p.projectName}) AS projects,
           collect(DISTINCT {assembly_id: asm.assemblyID, assembly_name: asm.assemblyName}) AS assemblies
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                row = session.run(query, req_id=requirement_id).single()
                if not row:
                    return json.dumps({"error": f"Requirement '{requirement_id}' not found."}, indent=2)
                return json.dumps(dict(row), indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


@mcp.tool()
def get_reverification_scope(project_ids: list[str]) -> str:
    """Given a list of affected project IDs, return all requirements grouped by re-verification category.

    Categories:
    - must_reverify: applicable and currently verified (needs re-checking after change)
    - must_verify: applicable but not yet verified
    - not_affected: not applicable
    """
    if not project_ids:
        return json.dumps({"error": "project_ids must not be empty."}, indent=2)

    query = """
    MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->(p:Project)
    WHERE p.projectID IN $project_ids
    OPTIONAL MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
    WITH r, a, collect(DISTINCT p.projectID) AS projects
    RETURN r.hasID AS req_id,
           r.requirementName AS req_name,
           r.isApplicable AS is_applicable,
           coalesce(r.isVerified, false) AS req_verified,
           a.hasID AS adr_id,
           projects,
           CASE
               WHEN r.isApplicable = true AND r.isVerified = true  THEN 'must_reverify'
               WHEN r.isApplicable = true                          THEN 'must_verify'
               ELSE 'not_affected'
           END AS scope_category
    ORDER BY scope_category, a.hasID, r.hasID
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query, project_ids=project_ids)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    grouped: dict[str, list] = {"must_reverify": [], "must_verify": [], "not_affected": []}
    for row in rows:
        cat = row.get("scope_category", "not_affected")
        grouped.setdefault(cat, []).append({
            "req_id": row["req_id"],
            "req_name": row["req_name"],
            "adr_id": row["adr_id"],
            "projects": row["projects"],
        })

    return json.dumps({
        "project_ids_in_scope": project_ids,
        "must_reverify_count": len(grouped["must_reverify"]),
        "must_verify_count": len(grouped["must_verify"]),
        "not_affected_count": len(grouped["not_affected"]),
        "scope": grouped,
    }, indent=2)


@mcp.tool()
def write_change_impact_report(
    change_description: str,
    affected_requirement_ids: list[str],
    affected_project_ids: list[str],
    risk_summary: str,
) -> str:
    """Create a ChangeImpactReport node in Neo4j linked to all affected requirements and projects."""
    if not change_description.strip():
        return json.dumps({"error": "change_description must not be empty."}, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    report_id = f"CIR-{ts}"

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                session.run("""
                    MERGE (cir:ChangeImpactReport {hasID: $cir_id})
                    SET cir.changeDescription = $change_description,
                        cir.riskSummary = $risk_summary,
                        cir.createdAt = datetime(),
                        cir.affectedRequirementCount = $req_count,
                        cir.affectedProjectCount = $proj_count
                """,
                    cir_id=report_id,
                    change_description=change_description,
                    risk_summary=risk_summary,
                    req_count=len(affected_requirement_ids),
                    proj_count=len(affected_project_ids),
                )

                for req_id in affected_requirement_ids:
                    session.run("""
                        MATCH (cir:ChangeImpactReport {hasID: $cir_id})
                        OPTIONAL MATCH (r:ExtractedEssentialRequirement {hasID: $req_id})
                        WITH cir, r WHERE r IS NOT NULL
                        MERGE (cir)-[:affectsRequirement]->(r)
                    """, cir_id=report_id, req_id=req_id)

                for proj_id in affected_project_ids:
                    session.run("""
                        MATCH (cir:ChangeImpactReport {hasID: $cir_id})
                        OPTIONAL MATCH (p:Project {projectID: $proj_id})
                        WITH cir, p WHERE p IS NOT NULL
                        MERGE (cir)-[:affectsProject]->(p)
                    """, cir_id=report_id, proj_id=proj_id)

    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "status": "created",
        "report_id": report_id,
        "change_description": change_description,
        "affected_requirement_count": len(affected_requirement_ids),
        "affected_project_count": len(affected_project_ids),
        "risk_summary": risk_summary,
    }, indent=2)


@mcp.tool()
def get_change_impact_reports() -> str:
    """Return all ChangeImpactReport nodes, newest first."""
    query = """
    MATCH (cir:ChangeImpactReport)
    OPTIONAL MATCH (cir)-[:affectsRequirement]->(r:ExtractedEssentialRequirement)
    OPTIONAL MATCH (cir)-[:affectsProject]->(p:Project)
    RETURN cir.hasID AS report_id,
           cir.changeDescription AS change_description,
           cir.riskSummary AS risk_summary,
           toString(cir.createdAt) AS created_at,
           cir.affectedRequirementCount AS req_count,
           cir.affectedProjectCount AS proj_count,
           collect(DISTINCT r.hasID) AS requirement_ids,
           collect(DISTINCT p.projectID) AS project_ids
    ORDER BY cir.createdAt DESC
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                rows = [record.data() for record in session.run(query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({"report_count": len(rows), "reports": rows}, indent=2)


# ── Phase 6: RL / feedback tools ──────────────────────────────────────────────

@mcp.tool()
def record_feedback(
    requirement_id: str,
    project_id: str,
    action: str,
    reward: float,
) -> str:
    """Record a human-feedback event for an inferred recommendation.

    action must be one of: confirmed, rejected, modified, ignored.
    Writes a FeedbackEvent node to Neo4j and updates the RL agent.
    Use the REWARD_* constants: confirmed=1.0, rejected=-1.0, modified=0.5, ignored=-0.3.
    If confidence was >0.8 and the action is rejected, pass reward=-2.0 (PENALTY_OVERCONFIDENT).
    """
    valid_actions = {"confirmed", "rejected", "modified", "ignored"}
    if action not in valid_actions:
        return json.dumps({"error": f"action must be one of {sorted(valid_actions)}."}, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    fe_id = f"FE-{ts}"

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                session.run("""
                    MERGE (fe:FeedbackEvent {hasID: $feid})
                    SET fe.requirementID = $req_id,
                        fe.projectID = $proj_id,
                        fe.action = $action,
                        fe.reward = $reward,
                        fe.timestamp = datetime()
                """, feid=fe_id, req_id=requirement_id, proj_id=project_id, action=action, reward=reward)

                session.run("""
                    MATCH (fe:FeedbackEvent {hasID: $feid})
                    OPTIONAL MATCH (r:ExtractedEssentialRequirement {hasID: $req_id})
                    WITH fe, r WHERE r IS NOT NULL
                    MERGE (fe)-[:recordedFor]->(r)
                """, feid=fe_id, req_id=requirement_id)

                session.run("""
                    MATCH (fe:FeedbackEvent {hasID: $feid})
                    OPTIONAL MATCH (p:Project {projectID: $proj_id})
                    WITH fe, p WHERE p IS NOT NULL
                    MERGE (fe)-[:recordedFor]->(p)
                """, feid=fe_id, proj_id=project_id)

    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    _rl_update(action, reward)

    return json.dumps({
        "status": "recorded",
        "feedback_id": fe_id,
        "requirement_id": requirement_id,
        "project_id": project_id,
        "action": action,
        "reward": reward,
    }, indent=2)


@mcp.tool()
def get_feedback_stats() -> str:
    """Return feedback statistics: total events, average reward, breakdown by action, and 5 most recent events."""
    query = """
    MATCH (fe:FeedbackEvent)
    WITH count(fe) AS total,
         avg(fe.reward) AS avg_reward,
         collect({
             id: fe.hasID,
             req_id: fe.requirementID,
             proj_id: fe.projectID,
             action: fe.action,
             reward: fe.reward,
             timestamp: toString(fe.timestamp)
         }) AS all_events
    UNWIND all_events AS ev
    WITH total, avg_reward, all_events,
         ev.action AS action, count(ev) AS action_count, avg(ev.reward) AS action_avg_reward
    RETURN total, avg_reward, all_events,
           collect({action: action, count: action_count, avg_reward: action_avg_reward}) AS breakdown
    LIMIT 1
    """

    # Simpler two-query approach to avoid Cypher aggregation complexity.
    summary_query = """
    MATCH (fe:FeedbackEvent)
    RETURN count(fe) AS total,
           avg(fe.reward) AS avg_reward
    """
    breakdown_query = """
    MATCH (fe:FeedbackEvent)
    RETURN fe.action AS action,
           count(fe) AS event_count,
           avg(fe.reward) AS avg_reward
    ORDER BY event_count DESC
    """
    recent_query = """
    MATCH (fe:FeedbackEvent)
    RETURN fe.hasID AS id,
           fe.requirementID AS req_id,
           fe.projectID AS proj_id,
           fe.action AS action,
           fe.reward AS reward,
           toString(fe.timestamp) AS timestamp
    ORDER BY fe.timestamp DESC
    LIMIT 5
    """

    try:
        with _neo4j_driver() as driver:
            with driver.session() as session:
                summary = session.run(summary_query).single()
                breakdown = [r.data() for r in session.run(breakdown_query)]
                recent = [r.data() for r in session.run(recent_query)]
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps({
        "total_events": summary["total"] if summary else 0,
        "average_reward": round(summary["avg_reward"] or 0.0, 4) if summary else 0.0,
        "breakdown_by_action": breakdown,
        "recent_events": recent,
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
