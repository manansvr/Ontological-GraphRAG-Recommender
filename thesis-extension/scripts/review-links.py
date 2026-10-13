#!/usr/bin/env python3
"""review-links.py: let a person review pending inferred project links.

The LLM can suggest links (write_inferred_project_link) but cannot confirm or reject
them: promote_inferred_link, modify_inferred_link and reject_inferred_link are not MCP
tools. This command-line tool is how a reviewer decides on each pending suggestion.

For every pending suggestedProject relationship it shows the requirement, project,
confidence, reasoning, inference state and time of inference, then asks:

    [c]onfirm  promote the suggestion to assignedToProject
    [m]odify   assign the requirement to a different project instead
    [r]eject   reject the suggestion (a reason is required)
    [s]kip     leave it pending
    [q]uit     stop reviewing

Every decision records a FeedbackEvent with the reviewer's name and updates the RL agent.

Usage (run with the same Python environment as sr8-mcp, from any directory):
    python3 thesis-extension/scripts/review-links.py --reviewer "Jane Smith"
"""

import argparse
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

SR8_PATH = Path(__file__).resolve().parent.parent / "sr8-mcp"

CHOICES = {"c": "confirm", "m": "modify", "r": "reject", "s": "skip", "q": "quit"}


def load_sr8() -> Any:
    """Import sr8-mcp as a module without starting the MCP server."""
    loader = importlib.machinery.SourceFileLoader("sr8_mcp_review", str(SR8_PATH))
    spec = importlib.util.spec_from_loader("sr8_mcp_review", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def show(link: dict, index: int, total: int) -> None:
    print("")
    print(f"[{index}/{total}] {link.get('req_id')} -> {link.get('project_id')} ({link.get('project_name') or 'no name'})")
    print(f"  Requirement:     {link.get('req_name') or ''}")
    print(f"  ADR:             {link.get('adr_id') or ''}")
    print(f"  Confidence:      {link.get('confidence')}")
    print(f"  Inference state: {link.get('inference_state')}")
    print(f"  Inferred at:     {link.get('inferred_at')} by {link.get('inferred_by')}")
    print(f"  Reasoning:       {link.get('reasoning') or ''}")


def report(raw: str) -> str:
    """Print a one-line outcome for a review call and return its status ('error' on failure)."""
    out = json.loads(raw)
    if "error" in out:
        print(f"  Not recorded: {out['error']}")
        if out.get("previous_decision"):
            print(f"  Earlier decision: {json.dumps(out['previous_decision'])}")
        return "error"
    feedback = out.get("feedback", {})
    note = " (link already existed; left unchanged)" if out.get("already_assigned") else ""
    print(f"  {out['status']}{note}; reward {feedback.get('reward_applied')}"
          f"{' (overconfidence penalty)' if feedback.get('overconfidence_penalty_applied') else ''}")
    return out["status"]


def review(sr8: Any, reviewer: str, ask: Callable[[str], str] = input) -> dict:
    """Run the interactive review loop and return a count of outcomes."""
    listing = json.loads(sr8.get_inferred_links())
    if "error" in listing:
        print(f"Could not load pending suggestions: {listing['error']}")
        return {"error": 1}
    links = listing.get("inferred_links", [])
    counts = {"promoted": 0, "modified": 0, "rejected": 0, "skipped": 0, "error": 0}
    if not links:
        print("No pending suggestions.")
        return counts
    print(f"{len(links)} pending suggestion(s). Reviewer: {reviewer}")

    for i, link in enumerate(links, start=1):
        show(link, i, len(links))
        while True:
            choice = CHOICES.get(ask("  [c]onfirm / [m]odify / [r]eject / [s]kip / [q]uit: ").strip().lower()[:1])
            if choice == "quit":
                return counts
            if choice == "skip":
                counts["skipped"] += 1
                break
            if choice == "confirm":
                counts[report(sr8.promote_inferred_link(link["req_id"], link["project_id"], reviewer))] += 1
                break
            if choice == "modify":
                new_project = ask("  Assign to which project ID instead? (blank to go back): ").strip()
                if not new_project:
                    continue
                reason = ask("  Reason (optional): ").strip()
                counts[report(sr8.modify_inferred_link(
                    link["req_id"], link["project_id"], new_project, reviewer, reason,
                ))] += 1
                break
            if choice == "reject":
                reason = ask("  Reason for rejecting (required, blank to go back): ").strip()
                if not reason:
                    continue
                counts[report(sr8.reject_inferred_link(link["req_id"], link["project_id"], reviewer, reason))] += 1
                break
            print("  Please answer c, m, r, s or q.")
    return counts


def main(argv: Optional[list] = None, sr8: Any = None, ask: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(description="Review pending inferred project links (people only).")
    parser.add_argument("--reviewer", required=True, help="Your name; recorded on every decision")
    args = parser.parse_args(argv)
    reviewer = args.reviewer.strip()
    if not reviewer:
        parser.error("--reviewer must not be empty")

    counts = review(sr8 if sr8 is not None else load_sr8(), reviewer, ask)
    print("")
    print("Summary: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 1 if counts.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
