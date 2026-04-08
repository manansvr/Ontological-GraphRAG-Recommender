#!/usr/bin/env python3
"""
run_inference.py
================
Inference loop for requirement propagation — finds all unassigned
ExtractedEssentialRequirement nodes, computes the most likely project
for each using similarity to already-assigned requirements, and either
prints a dry-run report or writes suggestedProject relationships to neo4j.

This script calls mcp_server tool functions directly (no MCP protocol).

Usage:
  # Dry run — print inferences, write nothing (default)
  python3 scripts/run_inference.py

  # Write inferences to neo4j as suggestedProject relationships
  python3 scripts/run_inference.py --write

  # Only write inferences above a confidence threshold
  python3 scripts/run_inference.py --write --min-confidence 0.5

  # Custom neo4j connection
  python3 scripts/run_inference.py --uri bolt://localhost:7687 --user neo4j --password password
"""

import argparse
import json
import sys
from collections import Counter

from neo4j import GraphDatabase

import mcp_server


# ── Inference logic ───────────────────────────────────────────────────

def _infer_project(similar_requirements: list) -> tuple[str | None, float, str]:
    """
    Given a list of similar requirements (from get_similar_assigned_requirements),
    vote across their assigned projects weighted by similarity score.

    Returns (project_id, confidence, reasoning) or (None, 0.0, reason).
    """
    if not similar_requirements:
        return None, 0.0, "No similar assigned requirements found."

    # Weighted vote: each similar requirement contributes its similarity
    # score as a vote weight for each of its assigned projects
    project_scores: Counter = Counter()
    project_names:  dict    = {}
    evidence:       list    = []

    for sim_req in similar_requirements:
        score    = sim_req.get("similarityScore", 0.0)
        projects = sim_req.get("assignedProjects", [])
        for proj in projects:
            pid   = proj.get("projectID")
            pname = proj.get("projectName") or pid
            if pid:
                project_scores[pid] += score
                project_names[pid]   = pname
                evidence.append(
                    f"{sim_req.get('requirementID','?')} (score {score:.2f}) → {pid}"
                )

    if not project_scores:
        return None, 0.0, "Similar requirements found but none have project assignments."

    # Best project by weighted vote
    best_pid, best_score = project_scores.most_common(1)[0]
    total_score = sum(project_scores.values())

    # Confidence = winning project's share of the total vote weight,
    # scaled by the top similarity score (so a 0.9 overlap with full
    # consensus is more confident than 0.3 overlap with full consensus)
    top_similarity = max(r.get("similarityScore", 0.0) for r in similar_requirements)
    confidence = round(min((best_score / max(total_score, 1e-9)) * top_similarity, 1.0), 2)

    # Build reasoning string
    n_similar     = len(similar_requirements)
    n_for_project = sum(1 for r in similar_requirements
                        if any(p.get("projectID") == best_pid
                               for p in r.get("assignedProjects", [])))
    reasoning = (
        f"Inferred from {n_similar} similar requirement(s); "
        f"{n_for_project} of them are assigned to {best_pid} "
        f"({project_names.get(best_pid, best_pid)}). "
        f"Top similarity score: {top_similarity:.2f}."
    )

    return best_pid, confidence, reasoning


# ── Report formatting ─────────────────────────────────────────────────

def _banner(text: str):
    print(f"\n{'═' * 65}")
    print(f"  {text}")
    print('═' * 65)


def _section(text: str):
    print(f"\n  {'─' * 60}")
    print(f"  {text}")
    print(f"  {'─' * 60}")


# ── Main loop ─────────────────────────────────────────────────────────

def run(driver, write: bool, min_confidence: float):
    mcp_server._driver = driver

    _banner("SR8 Requirement Propagation Inference")
    if write:
        print(f"  MODE : WRITE — inferences above {min_confidence:.0%} "
              f"will be written to neo4j as suggestedProject")
    else:
        print(f"  MODE : DRY RUN — nothing will be written to neo4j")
    print(f"  MIN CONFIDENCE : {min_confidence:.0%}")

    # ── Step 1: get all unassigned requirements ───────────────────────
    print(f"\n  Fetching unassigned requirements...")
    unassigned_raw  = mcp_server.get_unassigned_requirements()
    unassigned_data = json.loads(unassigned_raw)
    unassigned      = unassigned_data.get("requirements", [])

    print(f"  Found {len(unassigned)} unassigned requirement(s)")

    if not unassigned:
        print("\n  No unassigned requirements — graph is fully mapped.")
        return

    # ── Step 2: for each unassigned requirement, infer a project ─────
    inferences:  list = []   # (req, best_pid, confidence, reasoning)
    skipped:     list = []   # (req, reason)

    for req in unassigned:
        rid  = req["requirementID"]
        name = (req.get("requirementName") or "")[:60]

        similar_raw  = mcp_server.get_similar_assigned_requirements(rid)
        similar_data = json.loads(similar_raw)

        if "error" in similar_data:
            skipped.append((req, similar_data["error"]))
            continue

        similar_reqs = similar_data.get("similar_requirements", [])
        best_pid, confidence, reasoning = _infer_project(similar_reqs)

        if best_pid is None:
            skipped.append((req, reasoning))
            continue

        inferences.append((req, best_pid, confidence, reasoning))

    # ── Step 3: print report ──────────────────────────────────────────
    _banner(f"Inference Report — {len(inferences)} inferences, "
            f"{len(skipped)} skipped")

    if inferences:
        print(f"\n  {'Requirement':<14} {'ADR':<8} {'→ Project':<14} "
              f"{'Conf':>5}  {'Requirement Name'}")
        print(f"  {'───────────':<14} {'───':<8} {'─────────':<14} "
              f"{'────':>5}  {'────────────────'}")
        for req, pid, conf, _ in sorted(inferences,
                                        key=lambda x: x[2], reverse=True):
            flag = "✓" if conf >= min_confidence else "·"
            name = (req.get("requirementName") or "")[:40]
            print(f"  {flag} {req['requirementID']:<13} {req['adrID']:<8} "
                  f"→ {pid:<13} {conf:>4.0%}  {name}")

    if skipped:
        print(f"\n  Skipped ({len(skipped)}):")
        for req, reason in skipped:
            print(f"    {req['requirementID']:<14} {reason}")

    # ── Step 4: write if requested ────────────────────────────────────
    above_threshold = [(req, pid, conf, rsn)
                       for req, pid, conf, rsn in inferences
                       if conf >= min_confidence]

    if not write:
        print(f"\n  DRY RUN complete.")
        print(f"  {len(above_threshold)} inference(s) would be written "
              f"at confidence ≥ {min_confidence:.0%}.")
        print(f"  Run with --write to commit them as suggestedProject "
              f"relationships.")
        return

    if not above_threshold:
        print(f"\n  No inferences meet the confidence threshold "
              f"({min_confidence:.0%}). Nothing written.")
        return

    _section(f"Writing {len(above_threshold)} inferred link(s) to neo4j...")
    written = 0
    for req, pid, conf, rsn in above_threshold:
        result_raw = mcp_server.write_inferred_project_link(
            requirement_id=req["requirementID"],
            project_id=pid,
            confidence=conf,
            reasoning=rsn,
        )
        result = json.loads(result_raw)
        if result.get("written"):
            written += 1
            print(f"  ✓ {req['requirementID']} → {pid} (confidence {conf:.0%})")
        else:
            print(f"  ✗ {req['requirementID']} → {pid}  "
                  f"ERROR: {result.get('error', 'unknown')}")

    print(f"\n  Written: {written} / {len(above_threshold)}")
    print(f"\n  Review inferred links in neo4j Browser:")
    print(f"    MATCH (r)-[rel:suggestedProject]->(p) "
          f"RETURN r.hasID, p.projectID, rel.confidence ORDER BY rel.confidence DESC")
    print(f"\n  Or call get_inferred_links() via the MCP recommender system.")


def main():
    parser = argparse.ArgumentParser(
        description="SR8 requirement propagation inference loop"
    )
    parser.add_argument("--uri",            default="bolt://localhost:7687")
    parser.add_argument("--user",           default="neo4j")
    parser.add_argument("--password",       default="password")
    parser.add_argument("--write",          action="store_true",
                        help="Write inferences to neo4j (default: dry run)")
    parser.add_argument("--min-confidence", type=float, default=0.3,
                        help="Only write inferences at or above this threshold "
                             "(default: 0.3)")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session() as s:
            s.run("RETURN 1").single()
    except Exception as exc:
        print(f"ERROR: Cannot connect to neo4j at {args.uri}: {exc}",
              file=sys.stderr)
        sys.exit(1)

    try:
        run(driver, write=args.write, min_confidence=args.min_confidence)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
