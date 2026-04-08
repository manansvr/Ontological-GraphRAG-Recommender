#!/usr/bin/env python3
"""
recommender_app.py
==================
SR8 Compliance Recommender System — Streamlit web interface.

Calls the Anthropic API directly with the neo4j tool functions defined
as tools. Does not use MCP — tool functions are imported from mcp_server
and called in-process.

Usage:
    streamlit run scripts/recommender_app.py

Environment variables (copy .env.example → .env):
    ANTHROPIC_API_KEY   required
    NEO4J_URI           default bolt://localhost:7687
    NEO4J_USER          default neo4j
    NEO4J_PASSWORD      default password
"""

import json
import os
import sys
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Path setup — import mcp_server from the same directory ────────────
sys.path.insert(0, str(Path(__file__).parent))
import mcp_server

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
MODEL          = "claude-opus-4-6"
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
API_KEY        = os.getenv("ANTHROPIC_API_KEY", "")

MAX_TOKENS = 8192


# ── neo4j + mcp_server initialisation ────────────────────────────────

@st.cache_resource
def get_driver():
    """Connect to neo4j and inject the driver into mcp_server."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    mcp_server._driver = driver
    return driver


@st.cache_data(ttl=300)
def load_graph_schema() -> str:
    """Load the live graph schema (cached 5 min)."""
    get_driver()
    return mcp_server.get_graph_schema()


@st.cache_data(ttl=60)
def get_sidebar_stats() -> dict:
    """Fetch summary stats for the sidebar (cached 1 min)."""
    driver = get_driver()
    with driver.session() as s:
        total_nodes = s.run(
            "MATCH (n) RETURN count(n) AS c"
        ).single()["c"]

        req_count = s.run(
            "MATCH (n:ExtractedEssentialRequirement) RETURN count(n) AS c"
        ).single()["c"]

        prog = s.run("""
            MATCH (r:ExtractedEssentialRequirement)
            WHERE r.isApplicable = true
            RETURN count(r) AS total,
                   count(CASE WHEN r.isVerified = true THEN 1 END) AS verified
        """).single()

    total    = prog["total"]    if prog else 0
    verified = prog["verified"] if prog else 0
    pct      = round(verified / total * 100, 1) if total > 0 else 0.0

    return {
        "total_nodes":        total_nodes,
        "total_requirements": req_count,
        "verification_pct":   pct,
        "verified":           verified,
        "total_applicable":   total,
    }


# ── Anthropic client ──────────────────────────────────────────────────

@st.cache_resource
def get_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=API_KEY)


# ── Tool definitions (Anthropic format) ───────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_graph_schema",
        "description": (
            "Query neo4j and return the live schema: all node labels with counts, "
            "all relationship types with counts, and all property keys per label. "
            "Call this first to orient yourself before writing Cypher queries."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_compliance_gaps",
        "description": (
            "Find all applicable requirements that have not yet been verified. "
            "Returns results grouped by project. All filters are optional — "
            "omit all three for graph-wide gaps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id":  {"type": "string", "description": "e.g. \"SRP8-048\""},
                "adr_id":      {"type": "string", "description": "e.g. \"ADR-43\""},
                "assembly_id": {"type": "string",
                                "description": "e.g. \"ASM-STEERING\", \"ASM-FRONT-AXLE\", \"ASM-REAR-AXLE\""},
            },
            "required": [],
        },
    },
    {
        "name": "get_verification_progress",
        "description": (
            "Return verification progress: total applicable, total verified, "
            "total unverified, completion percentage. Optionally filter by project or assembly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id":  {"type": "string", "description": "e.g. \"SRP8-048\""},
                "assembly_id": {"type": "string",
                                "description": "e.g. \"ASM-STEERING\", \"ASM-FRONT-AXLE\", \"ASM-REAR-AXLE\""},
            },
            "required": [],
        },
    },
    {
        "name": "get_highest_risk_gaps",
        "description": (
            "Return the top 10 unverified applicable requirements ranked by the "
            "number of projects they affect. Higher project count = higher risk."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_cross_assembly_requirements",
        "description": (
            "Find all requirements assigned to projects in more than one assembly. "
            "These are regulatory couplings between engineering teams."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_assembly_dependencies",
        "description": (
            "For a given assembly, return all other assemblies it shares requirements "
            "with and which specific requirements create each coupling."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assembly_id": {
                    "type": "string",
                    "description": "\"ASM-STEERING\", \"ASM-FRONT-AXLE\", or \"ASM-REAR-AXLE\"",
                },
            },
            "required": ["assembly_id"],
        },
    },
    {
        "name": "get_shared_requirements",
        "description": (
            "Given two project IDs, find all requirements they both need to satisfy. "
            "Returns names, ADR sources, and verification status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id_1": {"type": "string", "description": "e.g. \"SRP8-048\""},
                "project_id_2": {"type": "string", "description": "e.g. \"SRP8-043\""},
            },
            "required": ["project_id_1", "project_id_2"],
        },
    },
    {
        "name": "get_interface_risk_report",
        "description": (
            "Full interface risk report across all assembly pairs. For each pair "
            "sharing requirements, lists them and flags unverified ones as risks."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_unassigned_requirements",
        "description": (
            "Return all requirements with no assignedToProject relationship — "
            "the gaps in the graph where no project has been made responsible."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_similar_assigned_requirements",
        "description": (
            "Given an unassigned requirement ID, find the 5 most similar requirements "
            "that DO have project assignments (by ADR and word overlap). "
            "Used to infer which project an unassigned requirement should go to."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "requirement_id": {
                    "type": "string",
                    "description": "hasID of an unassigned requirement, e.g. \"REQ-10-003\"",
                },
            },
            "required": ["requirement_id"],
        },
    },
    {
        "name": "write_inferred_project_link",
        "description": (
            "Write an inferred project assignment to neo4j as a suggestedProject "
            "relationship (never assignedToProject). Stores confidence and reasoning "
            "for audit trail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string", "description": "e.g. \"REQ-10-003\""},
                "project_id":     {"type": "string", "description": "e.g. \"SRP8-048\""},
                "confidence":     {"type": "number",
                                   "description": "Float 0.0–1.0 indicating inference confidence"},
                "reasoning":      {"type": "string",
                                   "description": "Human-readable explanation stored in the graph"},
            },
            "required": ["requirement_id", "project_id", "confidence", "reasoning"],
        },
    },
    {
        "name": "get_inferred_links",
        "description": (
            "Return all suggestedProject relationships in the graph, with confidence "
            "score, reasoning, and timestamp. Used for human review before promoting."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "promote_inferred_link",
        "description": (
            "Convert a suggestedProject relationship to a confirmed assignedToProject "
            "relationship after human review. Preserves the original confidence and "
            "reasoning for audit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
                "project_id":     {"type": "string"},
            },
            "required": ["requirement_id", "project_id"],
        },
    },
    {
        "name": "get_requirements_by_keyword",
        "description": (
            "Search requirementName, requirementDescription, and clauseText for a "
            "keyword (case-insensitive). Returns matching requirements with their "
            "ADR source, projects, and assemblies. Also returns matching clauses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Word or phrase to search, e.g. \"steering\", \"braking force\"",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_requirement_chain",
        "description": (
            "For a single requirement, return the full regulatory chain: "
            "AustralianDesignRule → requirement → projects → assemblies. "
            "Also returns all clauses from the parent ADR as context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "requirement_id": {
                    "type": "string",
                    "description": "hasID of the requirement, e.g. \"REQ-43-007\"",
                },
            },
            "required": ["requirement_id"],
        },
    },
    {
        "name": "get_reverification_scope",
        "description": (
            "Given project IDs affected by a design change, group their requirements "
            "into: must_reverify (applicable + verified — change may invalidate), "
            "must_verify (applicable + not verified), and not_affected (not applicable)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs, e.g. [\"SRP8-047\", \"SRP8-048\"]",
                },
            },
            "required": ["project_ids"],
        },
    },
    {
        "name": "write_change_impact_report",
        "description": (
            "Create a ChangeImpactReport node in neo4j linking the analysis findings "
            "to all affected requirements and projects. Call this after completing "
            "a change impact analysis to store findings for future reference."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "change_description":       {"type": "string"},
                "affected_requirement_ids": {
                    "type": "array", "items": {"type": "string"},
                },
                "affected_project_ids": {
                    "type": "array", "items": {"type": "string"},
                },
                "risk_summary": {"type": "string"},
            },
            "required": [
                "change_description",
                "affected_requirement_ids",
                "affected_project_ids",
                "risk_summary",
            ],
        },
    },
    {
        "name": "get_change_impact_reports",
        "description": (
            "Return all ChangeImpactReport nodes stored in the graph, newest first. "
            "Allows engineers to review past impact analyses."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_graph",
        "description": (
            "Execute any Cypher query against the SR8 neo4j knowledge graph and "
            "return results as JSON. Malformed queries return an error message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cypher": {
                    "type": "string",
                    "description": "A valid Cypher query string",
                },
            },
            "required": ["cypher"],
        },
    },
]

# ── Tool dispatch ─────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict = {
    "get_graph_schema":                mcp_server.get_graph_schema,
    "get_compliance_gaps":             mcp_server.get_compliance_gaps,
    "get_verification_progress":       mcp_server.get_verification_progress,
    "get_highest_risk_gaps":           mcp_server.get_highest_risk_gaps,
    "get_cross_assembly_requirements": mcp_server.get_cross_assembly_requirements,
    "get_assembly_dependencies":       mcp_server.get_assembly_dependencies,
    "get_shared_requirements":         mcp_server.get_shared_requirements,
    "get_interface_risk_report":       mcp_server.get_interface_risk_report,
    "get_unassigned_requirements":     mcp_server.get_unassigned_requirements,
    "get_similar_assigned_requirements": mcp_server.get_similar_assigned_requirements,
    "write_inferred_project_link":     mcp_server.write_inferred_project_link,
    "get_inferred_links":              mcp_server.get_inferred_links,
    "promote_inferred_link":           mcp_server.promote_inferred_link,
    "get_requirements_by_keyword":     mcp_server.get_requirements_by_keyword,
    "get_requirement_chain":           mcp_server.get_requirement_chain,
    "get_reverification_scope":        mcp_server.get_reverification_scope,
    "write_change_impact_report":      mcp_server.write_change_impact_report,
    "get_change_impact_reports":       mcp_server.get_change_impact_reports,
    "query_graph":                     mcp_server.query_graph,
}


def execute_tool(name: str, inputs: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name!r}"})
    try:
        return fn(**inputs)
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": name, "inputs": inputs})


# ── System prompt ─────────────────────────────────────────────────────

def build_system_prompt(schema_json: str) -> str:
    return f"""You are the SR8 Compliance Recommender System — an AI assistant \
for Sunswift Racing's SR8 solar car project. You help the engineering team \
reason about regulatory compliance by querying a neo4j knowledge graph that \
contains all Australian Design Rules (ADRs) relevant to SR8, extracted \
requirements, project assignments, and assembly groupings.

Your role is to:
- Answer questions about ADR compliance, verification status, and gaps
- Identify interface risks between engineering teams (cross-assembly requirements)
- Infer project assignments for unassigned requirements
- Analyse the impact of proposed design changes
- Store findings in the graph for future reference

Always be specific — cite requirement IDs, ADR IDs, and project IDs in your \
answers. When you are unsure about the graph structure, call get_graph_schema \
first. When the user describes a change or asks about an area, search by keyword \
before drawing conclusions.

Graph structure:
  AustralianDesignRule (7)
    -[:hasExternalEssentialRequirement]-> ExtractedEssentialRequirement (205)
      -[:assignedToProject]-> Project (24)
        -[:belongsToAssembly]-> Assembly (3)
  AustralianDesignRule -[:hasClause]-> Clause (243)
  AustralianDesignRule -[:assignedToDepartment]-> Department (4)

Assemblies:
  ASM-FRONT-AXLE  projects: SRP8-043, SRP8-045, SRP8-050, SRP8-088
  ASM-STEERING    projects: SRP8-047, SRP8-048, SRP8-049
  ASM-REAR-AXLE   projects: SRP8-044, SRP8-046, SRP8-051, SRP8-089

Key property names:
  AustralianDesignRule   hasID (e.g. ADR-10)        hasName
  ExtractedEssentialRequirement  hasID (e.g. REQ-10-001)  requirementName
  Project                projectID (e.g. SRP8-048)   projectName
  Assembly               hasID (e.g. ASM-STEERING)   hasName

Live graph schema (queried at startup):
{schema_json}"""


# ── Message processing ────────────────────────────────────────────────

def process_user_message(user_text: str, schema_json: str) -> None:
    """
    Add the user message to history, call Claude in a tool-call loop,
    display each tool call as it happens, and render the final answer.
    """
    client = get_anthropic_client()

    # Add to display history and API messages
    st.session_state.display_history.append({"type": "user", "text": user_text})
    st.session_state.api_messages.append({"role": "user", "content": user_text})

    # Render the user message immediately
    with st.chat_message("user"):
        st.markdown(user_text)

    # Tool-call loop
    with st.chat_message("assistant"):
        tool_placeholder = st.empty()

        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=build_system_prompt(schema_json),
                messages=st.session_state.api_messages,
                tools=TOOL_DEFINITIONS,
            )

            # Add assistant turn to API messages
            st.session_state.api_messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # Check for tool calls
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls — extract and display final text
                final_text = " ".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                tool_placeholder.empty()
                st.markdown(final_text)
                st.session_state.display_history.append({
                    "type": "assistant",
                    "text": final_text,
                })
                break

            # Execute all tool calls in this turn
            tool_results = []
            tool_call_records = []

            with tool_placeholder.container():
                for block in tool_use_blocks:
                    result_str = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result_str,
                    })
                    tool_call_records.append({
                        "name":   block.name,
                        "input":  block.input,
                        "output": result_str,
                    })

                    # Show tool call in expandable section
                    label = f"🔧 `{block.name}`"
                    with st.expander(label, expanded=False):
                        if block.input:
                            st.caption("Inputs")
                            st.json(block.input)
                        st.caption("Result")
                        try:
                            parsed = json.loads(result_str)
                            st.json(parsed)
                        except json.JSONDecodeError:
                            st.code(result_str)

            # Store tool calls in display history
            st.session_state.display_history.append({
                "type":  "tool_calls",
                "calls": tool_call_records,
            })

            # Add tool results as user turn and loop
            st.session_state.api_messages.append({
                "role":    "user",
                "content": tool_results,
            })


# ── Chat history rendering ────────────────────────────────────────────

def render_history() -> None:
    """Re-render the full display history (called at the top of each rerun)."""
    for item in st.session_state.display_history:
        if item["type"] == "user":
            with st.chat_message("user"):
                st.markdown(item["text"])

        elif item["type"] == "assistant":
            with st.chat_message("assistant"):
                st.markdown(item["text"])

        elif item["type"] == "tool_calls":
            with st.chat_message("assistant"):
                for call in item["calls"]:
                    label = f"🔧 `{call['name']}`"
                    with st.expander(label, expanded=False):
                        if call["input"]:
                            st.caption("Inputs")
                            st.json(call["input"])
                        st.caption("Result")
                        try:
                            st.json(json.loads(call["output"]))
                        except json.JSONDecodeError:
                            st.code(call["output"])


# ── Sidebar ───────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.header("Graph Statistics")

        try:
            stats = get_sidebar_stats()
            col1, col2 = st.columns(2)
            col1.metric("Total Nodes",        stats["total_nodes"])
            col2.metric("Requirements",        stats["total_requirements"])

            pct = stats["verification_pct"]
            st.metric(
                "Verification Progress",
                f"{pct}%",
                delta=f"{stats['verified']} / {stats['total_applicable']} verified",
                delta_color="normal",
            )
            st.progress(pct / 100)

        except Exception as exc:
            st.error(f"Could not load stats: {exc}")

        st.divider()
        st.header("Quick Actions")
        st.caption("Click to pre-fill the chat.")

        quick_actions = [
            ("📋 Compliance gaps",       "Show all compliance gaps across the entire graph, grouped by project."),
            ("⚠️ Interface risks",       "Show the full interface risk report across all assemblies."),
            ("❓ Unassigned requirements","List all requirements that have no project assigned."),
            ("📊 Verification progress", "What is our overall verification progress?"),
            ("🔗 Cross-assembly reqs",   "Which requirements span more than one assembly?"),
        ]

        for label, prompt in quick_actions:
            if st.button(label, use_container_width=True):
                st.session_state.pending_prompt = prompt

        st.divider()
        st.caption(f"Model: `{MODEL}`")
        st.caption(f"neo4j: `{NEO4J_URI}`")

        if st.button("🗑️ Clear conversation", use_container_width=True):
            st.session_state.display_history = []
            st.session_state.api_messages    = []
            st.rerun()


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="SR8 Compliance Recommender System",
        page_icon="🏎️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Check API key ─────────────────────────────────────────────────
    if not API_KEY:
        st.error(
            "**ANTHROPIC_API_KEY is not set.** "
            "Copy `.env.example` to `.env` and add your key, then restart."
        )
        st.stop()

    # ── Connect to neo4j ──────────────────────────────────────────────
    try:
        get_driver()
    except Exception as exc:
        st.error(
            f"**Cannot connect to neo4j** at `{NEO4J_URI}`: {exc}\n\n"
            "Start neo4j with `brew services start neo4j` then refresh."
        )
        st.stop()

    # ── Load schema ───────────────────────────────────────────────────
    try:
        schema_json = load_graph_schema()
    except Exception as exc:
        st.error(f"**Could not load graph schema**: {exc}")
        st.stop()

    # ── Session state init ────────────────────────────────────────────
    if "display_history" not in st.session_state:
        st.session_state.display_history = []
    if "api_messages" not in st.session_state:
        st.session_state.api_messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None

    # ── Layout ────────────────────────────────────────────────────────
    render_sidebar()

    st.title("SR8 Compliance Recommender System")
    st.caption("Powered by Claude + neo4j Knowledge Graph")
    st.divider()

    # ── Render conversation history ───────────────────────────────────
    render_history()

    # ── Chat input (also picks up quick-action pending prompts) ───────
    user_input = st.chat_input("Ask about SR8 compliance…")

    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if user_input:
        process_user_message(user_input, schema_json)


if __name__ == "__main__":
    main()
