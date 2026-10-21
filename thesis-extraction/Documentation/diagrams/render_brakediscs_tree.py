#!/usr/bin/env python3
"""
Pulls the ADR-31 / BrakeDiscs demo subgraph from Neo4j and renders it as a
strict left-to-right hierarchical tree via Graphviz:

  ADR -> Requirement -> Project -> [bridge] Component -> FailureMode -> {Cause, Effect, ControlAction}

Cause/Effect/ControlAction are colour-coded distinctly so the FMEA causal
chain reads at a glance.
"""
import subprocess
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password123")

QUERY = """
MATCH (a:AustralianDesignRule {hasID: "ADR-31"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
WHERE r.requirementName CONTAINS "Wear"
MATCH (r)-[:assignedToProject]->(p:Project)
MATCH (c:Component {hasID: "BrakeDiscs"})-[:componentInProject]->(p)
MATCH (c)-[:hasFailureMode]->(fm:FailureMode)
OPTIONAL MATCH (fm)-[:causedBy]->(cause:Cause)
OPTIONAL MATCH (fm)-[:causes]->(effect:Effect)
OPTIONAL MATCH (fm)-[:mitigatedBy]->(ca:ControlAction)
OPTIONAL MATCH (c)-[:satisfiesRequirement]->(req:Requirement)
RETURN a, r, p, c, fm, cause, effect, ca, req
"""

COLORS = {
    "AustralianDesignRule": "#8e44ad",
    "ExtractedEssentialRequirement": "#c0392b",
    "Project": "#e91e8c",
    "Component": "#16a085",
    "FailureMode": "#2c3e50",   # dark slate — the hub, deliberately neutral
    "Cause": "#f1c40f",         # amber — the trigger
    "Effect": "#e74c3c",        # red — the consequence
    "ControlAction": "#2980b9", # blue — the mitigation/fix
    "Requirement": "#27ae60",
}

# nodes with light fills need dark text for contrast
DARK_TEXT_LABELS = {"Cause"}

LEGEND_ORDER = [
    ("AustralianDesignRule", "ADR (regulation)"),
    ("ExtractedEssentialRequirement", "Extracted Requirement"),
    ("Project", "Project"),
    ("Component", "Component"),
    ("FailureMode", "Failure Mode"),
    ("Cause", "Cause (trigger)"),
    ("Effect", "Effect (consequence)"),
    ("ControlAction", "Control Action (mitigation)"),
]

RANK = {
    "AustralianDesignRule": 0,
    "ExtractedEssentialRequirement": 1,
    "Project": 2,
    "Component": 3,
    "FailureMode": 4,
    "Requirement": 4,
    "Cause": 5,
    "Effect": 5,
    "ControlAction": 5,
}


def node_key(n):
    """Requirement nodes are keyed by name so duplicate clauses (same
    requirement assigned to both Front and Rear Brakes) collapse into one
    node with two outgoing edges, instead of drawing twice."""
    labels = set(n.labels)
    if "ExtractedEssentialRequirement" in labels:
        return "REQ::" + n.get("requirementName", n.element_id)
    return n.element_id


def label_of(n):
    labels = set(n.labels)
    for lbl in ("AustralianDesignRule", "ExtractedEssentialRequirement", "Project",
                "Component", "FailureMode", "Cause", "Effect", "ControlAction", "Requirement"):
        if lbl in labels:
            return lbl
    return next(iter(labels))


def caption_of(n, lbl):
    props = dict(n)
    if lbl == "AustralianDesignRule":
        return props.get("hasID", "")
    if lbl == "ExtractedEssentialRequirement":
        return props.get("requirementName", "")
    if lbl == "Project":
        return props.get("projectName", "")
    if lbl == "Component":
        return props.get("hasID", "")
    return props.get("hasName", props.get("requirementName", ""))


def main():
    nodes = {}
    edges = set()

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            result = session.run(QUERY)
            for record in result:
                for key in ("a", "r", "p", "c", "fm", "cause", "effect", "ca", "req"):
                    n = record.get(key)
                    if n is not None:
                        nodes[node_key(n)] = n

                a, r, p, c, fm = record["a"], record["r"], record["p"], record["c"], record["fm"]
                cause, effect, ca, req = record["cause"], record["effect"], record["ca"], record["req"]

                edges.add((node_key(a), node_key(r), "hasExternalEssentialRequirement", "fwd"))
                edges.add((node_key(r), node_key(p), "assignedToProject", "fwd"))
                edges.add((node_key(p), node_key(c), "componentInProject", "back"))
                edges.add((node_key(c), node_key(fm), "hasFailureMode", "fwd"))
                if cause is not None:
                    edges.add((node_key(fm), node_key(cause), "causedBy", "fwd"))
                if effect is not None:
                    edges.add((node_key(fm), node_key(effect), "causes", "fwd"))
                if ca is not None:
                    edges.add((node_key(fm), node_key(ca), "mitigatedBy", "fwd"))
                if req is not None:
                    edges.add((node_key(c), node_key(req), "satisfiesRequirement", "fwd"))

    dot_lines = [
        "digraph G {",
        '  rankdir=LR;',
        '  splines=true;',
        '  nodesep=0.45;',
        '  ranksep=1.1;',
        '  bgcolor="white";',
        '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 fontcolor="white" penwidth=0];',
        '  edge [fontname="Helvetica" fontsize=9 color="#888888" fontcolor="#555555"];',
    ]

    # rank groups so the LR column order is enforced even where edge direction alone wouldn't do it
    by_rank = {}
    for key, n in nodes.items():
        lbl = label_of(n)
        by_rank.setdefault(RANK.get(lbl, 9), []).append(key)

    for key, n in nodes.items():
        lbl = label_of(n)
        text = caption_of(n, lbl).replace('"', "'")
        color = COLORS.get(lbl, "#999999")
        width = 2.6 if lbl == "ControlAction" else 1.8
        fontcolor = "#1a1a1a" if lbl in DARK_TEXT_LABELS else "white"
        dot_lines.append(
            f'  "{key}" [label="{text}" fillcolor="{color}" fontcolor="{fontcolor}" width={width}];'
        )

    for src, dst, rel, direction in edges:
        if direction == "back":
            # draw Project -> Component for rank order, arrowhead reversed to show true direction
            dot_lines.append(f'  "{src}" -> "{dst}" [label="{rel}" dir=back];')
        else:
            dot_lines.append(f'  "{src}" -> "{dst}" [label="{rel}"];')

    for rank, keys in by_rank.items():
        same = " ".join(f'"{k}"' for k in keys)
        dot_lines.append(f'  {{ rank=same; {same} }}')

    # legend — floating cluster, not connected to the main graph
    dot_lines.append('  subgraph cluster_legend {')
    dot_lines.append('    label="Legend"; fontname="Helvetica" fontsize=12; color="#cccccc"; style=rounded;')
    for i, (lbl, text) in enumerate(LEGEND_ORDER):
        color = COLORS.get(lbl, "#999999")
        fontcolor = "#1a1a1a" if lbl in DARK_TEXT_LABELS else "white"
        dot_lines.append(
            f'    "legend_{i}" [label="{text}" fillcolor="{color}" fontcolor="{fontcolor}" width=2.0 shape=box];'
        )
    for i in range(len(LEGEND_ORDER) - 1):
        dot_lines.append(f'    "legend_{i}" -> "legend_{i+1}" [style=invis];')
    dot_lines.append('  }')

    dot_lines.append("}")
    dot_source = "\n".join(dot_lines)

    out_dot = "/private/tmp/claude-501/-Users-manan-Desktop-Ontological-GraphRAG-Recommender/008ae321-eac6-4d34-8102-651913d70444/scratchpad/brakediscs_tree.dot"
    out_png = out_dot.replace(".dot", ".png")
    out_svg = out_dot.replace(".dot", ".svg")

    with open(out_dot, "w") as f:
        f.write(dot_source)

    subprocess.run(["dot", "-Tpng", out_dot, "-o", out_png], check=True)
    subprocess.run(["dot", "-Tsvg", out_dot, "-o", out_svg], check=True)
    print(f"Nodes: {len(nodes)}  Edges: {len(edges)}")
    print(f"Wrote {out_png}")
    print(f"Wrote {out_svg}")


if __name__ == "__main__":
    main()
