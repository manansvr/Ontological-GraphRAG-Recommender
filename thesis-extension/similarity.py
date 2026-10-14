"""Requirement similarity primitives shared by sr8-mcp and scripts/propose-fmea-links.py.

sr8-mcp loads this file by path (like rl_model_path.py), so the MCP tools and the offline
scripts score names and clause numbers identically:

- name_words: lower-cased content words of a requirement name, stop-words removed
- name_overlap: Jaccard overlap of two names' content words (0..1)
- clause_parts / clauses_adjacent: clause numbers are adjacent when they have the same
  depth and parent and their last parts differ by at most 1 (5.2.7 / 5.2.8)
"""

import re
from typing import Optional, Set, Tuple

# Function words removed before comparing requirement names.
NAME_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it",
    "its", "of", "on", "or", "per", "shall", "that", "the", "their", "this", "to", "with",
}
_CLAUSE_NUMBER_RE = re.compile(r"\d+(?:\.\d+)*")


def name_words(name: Optional[str]) -> Set[str]:
    """Lower-cased content words of a requirement name (stop-words removed)."""
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in NAME_STOP_WORDS}


def name_overlap(a: Optional[str], b: Optional[str]) -> float:
    """Jaccard overlap of the content words of two names (0 when both are empty)."""
    wa, wb = name_words(a), name_words(b)
    union = wa | wb
    return len(wa & wb) / len(union) if union else 0.0


def clause_parts(clause: Optional[str]) -> Optional[Tuple[int, ...]]:
    """Numeric parts of a clause number ("6.6.1 Pt 2" -> (6, 6, 1)); None if it has none."""
    m = _CLAUSE_NUMBER_RE.search(clause or "")
    return tuple(int(p) for p in m.group(0).split(".")) if m else None


def clauses_adjacent(a: Optional[str], b: Optional[str]) -> Optional[bool]:
    """True if the clause numbers have the same depth and parent and their last parts differ
    by at most 1 (5.2.7 / 5.2.8, or equal numbers); None if either clause number is unknown."""
    pa, pb = clause_parts(a), clause_parts(b)
    if pa is None or pb is None:
        return None
    return len(pa) == len(pb) and pa[:-1] == pb[:-1] and abs(pa[-1] - pb[-1]) <= 1
