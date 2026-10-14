#!/usr/bin/env python3
"""
extract_assemblies.py
=====================
Groups projects into assemblies from data/assemblies.csv
(columns: assembly_id, assembly_name, project_id; one row per project in an assembly).

Writes (names as declared in thesis-ontology: Assembly identified by hasID / hasName):
  (a:Assembly {hasID: assembly_id}) with hasName = assembly_name
  (p:Project {projectID: project_id})-[:belongsToAssembly]->(a)

Projects are only matched, never created. A project_id that does not exist is reported
with a warning and skipped:
  - live run: the Project must already be in the graph (run --only adrs first);
  - dry run: the Project must be one that extract-ADR.py creates from the ADR CSVs.

For each assembly it reports the projects linked and how many distinct requirements
reach the assembly through (requirement)-[:assignedToProject]->(project).

Usage:
    python3 Scripts/run-extraction.py --only assemblies --dry-run
    python3 Scripts/run-extraction.py --only assemblies --uri bolt://localhost:7687 --user neo4j --password ...
"""

import csv
import importlib.util
from pathlib import Path

REQUIRED_COLUMNS = ("assembly_id", "assembly_name", "project_id")


def read_assemblies(path: str) -> dict:
    """Return {assembly_id: {"name": ..., "projects": [project_id, ...]}} in file order."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}; expected {list(REQUIRED_COLUMNS)}")
        assemblies: dict = {}
        for row in reader:
            assembly_id = (row["assembly_id"] or "").strip()
            project_id = (row["project_id"] or "").strip()
            if not assembly_id or not project_id:
                continue
            entry = assemblies.setdefault(assembly_id, {"name": (row["assembly_name"] or "").strip(), "projects": []})
            if project_id not in entry["projects"]:
                entry["projects"].append(project_id)
    return assemblies


def projects_from_adr_csvs(adr_folder: str) -> tuple:
    """(project_ids, {project_id: {requirement_id, ...}}) that extract-ADR.py would write.

    Uses extract-ADR.py's own row plan (plan_rows): a Project is created for every row with
    a real Project ID (placeholders such as "N/A" are not projects); an assignedToProject
    edge only when the same row also creates a requirement.
    """
    spec = importlib.util.spec_from_file_location("extract_adr_module", Path(__file__).with_name("extract-ADR.py"))
    adr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adr)

    projects: set = set()
    requirements: dict = {}
    for path in sorted(Path(adr_folder).glob("*.csv")):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = adr.forward_fill_adr_id([{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)])
        for plan in adr.plan_rows(rows):
            if plan["skip_reason"] or not plan["project_id"]:
                continue
            projects.add(plan["project_id"])
            if plan["req_id"]:
                requirements.setdefault(plan["project_id"], set()).add(plan["req_id"])
    return projects, requirements


def _graph_projects(driver) -> tuple:
    with driver.session() as s:
        projects = {r["pid"] for r in s.run("MATCH (p:Project) RETURN p.projectID AS pid") if r["pid"]}
        requirements: dict = {}
        for r in s.run("""
            MATCH (r:ExtractedEssentialRequirement)-[:assignedToProject]->(p:Project)
            RETURN p.projectID AS pid, collect(DISTINCT r.hasID) AS reqs
        """):
            requirements[r["pid"]] = set(r["reqs"])
    return projects, requirements


def _write_assembly(driver, assembly_id: str, name: str, project_ids: list) -> int:
    """MERGE the Assembly and belongsToAssembly edges; returns the number of projects linked."""
    with driver.session() as s:
        s.run("""
            MERGE (a:Assembly {hasID: $aid})
            ON CREATE SET a.hasName = $name
            ON MATCH  SET a.hasName = CASE WHEN $name <> '' THEN $name ELSE a.hasName END
        """, aid=assembly_id, name=name)
        row = s.run("""
            MATCH (a:Assembly {hasID: $aid})
            MATCH (p:Project) WHERE p.projectID IN $pids
            MERGE (p)-[:belongsToAssembly]->(a)
            RETURN count(DISTINCT p) AS linked
        """, aid=assembly_id, pids=project_ids).single()
    return row["linked"] if row else 0


def extract_assemblies(path: str, driver=None, dry_run: bool = False, adr_folder: str = "csv") -> dict:
    print(f"\n📄 {Path(path).name}")
    assemblies = read_assemblies(path)
    if dry_run:
        existing, requirements = projects_from_adr_csvs(adr_folder)
        source = f"projects extract-ADR.py creates from {adr_folder}/"
    else:
        existing, requirements = _graph_projects(driver)
        source = "Project nodes in the graph"
    print(f"   {len(assemblies)} assemblies; checking project IDs against {len(existing)} {source}")

    report = {}
    for assembly_id, entry in assemblies.items():
        linked = [p for p in entry["projects"] if p in existing]
        skipped = [p for p in entry["projects"] if p not in existing]
        for project_id in skipped:
            print(f"   ⚠️  {assembly_id}: project {project_id} does not exist ({source}); skipped, no stub created")
        if not dry_run and linked:
            written = _write_assembly(driver, assembly_id, entry["name"], linked)
            if written != len(linked):
                print(f"   ⚠️  {assembly_id}: expected to link {len(linked)} projects, linked {written}")
        reqs = set().union(*(requirements.get(p, set()) for p in linked)) if linked else set()
        report[assembly_id] = {
            "name": entry["name"],
            "projects_linked": linked,
            "projects_skipped": skipped,
            "requirements_per_project": {p: len(requirements.get(p, set())) for p in linked},
            "requirements_reaching_assembly": len(reqs),
        }
        tag = "[DRY]" if dry_run else "[OK] "
        per_project = ", ".join(f"{p} ({len(requirements.get(p, set()))})" for p in linked) or "none"
        print(f"  {tag} {assembly_id} ({entry['name']}): {len(linked)} project(s) linked: {per_project}; "
              f"{len(reqs)} requirement(s) reach it via assignedToProject")

    total_links = sum(len(r["projects_linked"]) for r in report.values())
    total_skipped = sum(len(r["projects_skipped"]) for r in report.values())
    print(f"   ✓ Assemblies: {len(report)} | Project links: {total_links} | Skipped (missing projects): {total_skipped}")
    return report
