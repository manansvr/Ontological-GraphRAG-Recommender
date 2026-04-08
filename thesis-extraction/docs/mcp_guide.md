# SR8 Knowledge Graph — MCP & Recommender System Guide

This document explains how to run the MCP server, connect it to Claude, and use the recommender system to query the SR8 knowledge graph.

Keep this document open alongside neo4j Browser when working with the recommender system.

---

## What is the MCP server?

The MCP (Model Context Protocol) server sits between Claude and neo4j. It exposes the SR8 knowledge graph as callable tools. Claude acts as a recommender system — it calls these tools autonomously, inspects the results, and reasons across the graph to answer questions about ADR compliance, project assignments, and assembly traceability.

```
You ──► Claude (recommender system)
              │
              ▼
        MCP Server (mcp_server.py)
              │
              ▼
        neo4j (bolt://localhost:7687)
              │
              ▼
        SR8 Knowledge Graph
```

---

## Prerequisites

### 1. Install dependencies

From the `thesis-extraction/` directory:

```bash
pip install -r requirements.txt
```

Packages installed:
- `mcp[cli]` — MCP Python SDK
- `neo4j` — neo4j Python driver

### 2. Start neo4j

```bash
brew services start neo4j
```

Confirm it is running:

```bash
neo4j status
```

The graph must be populated before the recommender system can answer questions. If starting fresh, run the extraction pipeline first — see `docs/extraction.md`.

---

## Running the MCP server

From the `thesis-extraction/` directory:

```bash
python3 scripts/mcp_server.py
```

With custom connection details:

```bash
python3 scripts/mcp_server.py --uri bolt://localhost:7687 --user neo4j --password password
```

### Expected startup output

```
──────────────────────────────────────────────────
SR8 Knowledge Graph — MCP Server
  neo4j     : bolt://localhost:7687
  transport : stdio
  tools     : get_graph_schema
              query_graph
──────────────────────────────────────────────────
```

The server runs over stdio and stays alive until you kill it (`Ctrl+C`). All startup messages go to stderr — stdout is reserved for the MCP protocol.

---

## Connecting to Claude Desktop

### 1. Locate the Claude Desktop config file

On macOS:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

### 2. Add the SR8 server

Merge the contents of `docs/claude_desktop_config.json` into your Claude Desktop config. The final file should look like:

```json
{
  "mcpServers": {
    "sr8-knowledge-graph": {
      "command": "python3",
      "args": [
        "/Users/ilina.sharma/thesis-ontology/thesis-extraction/scripts/mcp_server.py"
      ],
      "env": {}
    }
  }
}
```

Adjust the path if your repo is in a different location.

### 3. Restart Claude Desktop

Quit Claude Desktop completely and reopen it. The `sr8-knowledge-graph` server will appear in the tool list (hammer icon).

---

## Available tools

The recommender system currently has access to fourteen tools:

### `get_graph_schema`

Queries neo4j and returns the live schema of the knowledge graph:
- All node labels with counts
- All relationship types with counts
- All property keys per label

The recommender system should call this first to orient itself before writing Cypher queries. The schema always reflects the current state of the graph — it is never hardcoded.

**No arguments required.**

Example output (abbreviated):

```json
{
  "node_labels": [
    { "label": "ExtractedEssentialRequirement", "count": 205 },
    { "label": "Clause", "count": 243 },
    { "label": "Project", "count": 24 },
    { "label": "AustralianDesignRule", "count": 7 }
  ],
  "relationship_types": [
    { "type": "hasExternalEssentialRequirement", "count": 205 },
    { "type": "assignedToProject", "count": 178 },
    { "type": "hasClause", "count": 243 }
  ],
  "properties_by_label": [...]
}
```

---

### `get_compliance_gaps`

Finds all `ExtractedEssentialRequirement` nodes where `isApplicable` is `true` but `isVerified` is `false` or `null`. Results are grouped by project and include the ADR source and requirement name for each gap.

All filter parameters are optional — omit all three to return gaps across the entire graph.

**Arguments:**
- `project_id` (string, optional) — e.g. `"SRP8-048"`
- `adr_id` (string, optional) — e.g. `"ADR-43"`
- `assembly_id` (string, optional) — e.g. `"ASM-STEERING"`

**Example output:**
```json
{
  "filters": { "project_id": null, "adr_id": "ADR-43", "assembly_id": null },
  "total_projects_with_gaps": 8,
  "total_gaps": 24,
  "by_project": [
    {
      "projectID": "SRP8-048",
      "projectName": "Steering Rack",
      "gapCount": 5,
      "gaps": [
        { "requirementID": "REQ-43-007", "requirementName": "...", "adrID": "ADR-43", "adrName": "..." }
      ]
    }
  ]
}
```

The recommender system calls this tool proactively whenever you mention a project, assembly, or ADR — you do not need to ask about compliance specifically.

---

### `get_verification_progress`

Returns a verification progress summary: total applicable requirements, total verified, total unverified, and a completion percentage.

**Arguments:**
- `project_id` (string, optional) — scope to a single project
- `assembly_id` (string, optional) — scope to all projects in an assembly
- no arguments — returns graph-wide progress

**Example output:**
```json
{
  "filters": { "project_id": null, "assembly_id": "ASM-FRONT-AXLE" },
  "total_applicable": 42,
  "total_verified": 0,
  "total_unverified": 42,
  "completion_pct": 0.0
}
```

The recommender system calls this tool proactively whenever you mention a project, assembly, or ADR — you do not need to ask about compliance specifically.

---

### `get_highest_risk_gaps`

Returns the top 10 unverified applicable requirements ranked by the number of projects they affect. A requirement assigned to 3 projects is higher risk than one assigned to 1.

Each result includes: ADR source, requirement name, affected project IDs, affected assembly names, and the project count used for ranking.

**No arguments.**

The recommender system calls this tool proactively whenever you mention a project, assembly, or ADR — you do not need to ask about compliance specifically.

---

### `query_graph`

Executes any Cypher query against neo4j and returns the results as JSON.

**Arguments:**
- `cypher` (string) — a valid Cypher query

If the query is malformed or fails, the recommender system receives a structured error message (`{"error": "...", "query": "..."}`) rather than a crash.

**Example queries the recommender system might run:**

```cypher
// All ADRs and their requirement counts
MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
RETURN a.hasID, count(r) AS requirements
ORDER BY a.hasID
```

```cypher
// Full 4-level hierarchy for ADR-43
MATCH (a:AustralianDesignRule {hasID: "ADR-43"})
      -[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
      -[:assignedToProject]->(p:Project)
      -[:belongsToAssembly]->(asm:Assembly)
RETURN a.hasID, r.requirementName, p.projectID, asm.hasName
```

```cypher
// Which ADRs touch the steering assembly?
MATCH (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r)
      -[:assignedToProject]->(p)-[:belongsToAssembly]->(asm:Assembly)
WHERE asm.hasID = "ASM-STEERING"
RETURN DISTINCT a.hasID, a.hasName
```

---

---

## Requirement propagation inference tools

This component finds requirements with no project assignment and uses
similarity reasoning to infer which project they likely apply to. All
inferred links use a `suggestedProject` relationship type that is
permanently distinguishable from confirmed `assignedToProject` links.

### `get_unassigned_requirements`

Returns all `ExtractedEssentialRequirement` nodes with no `assignedToProject` relationship — the gaps in the current graph. Includes requirement name, description, and ADR source for each.

**No arguments.** The recommender system calls this proactively when you ask about gaps, missing assignments, or extending the knowledge base.

---

### `get_similar_assigned_requirements`

Given an unassigned requirement ID, finds the 5 most similar requirements that do have project assignments. Similarity is scored by: same ADR (+0.4 bonus) and Jaccard word overlap on `requirementName`. Returns the similar requirements and their assigned projects — these serve as examples for inference.

**Arguments:**
- `requirement_id` (string) — e.g. `"REQ-10-003"`

---

### `write_inferred_project_link`

Writes an inferred project assignment to neo4j as a `suggestedProject` relationship. Never writes `assignedToProject` — inferred links are always distinguishable from confirmed extracted links.

Stores `confidence`, `reasoning`, `inferredBy: "Claude-MCP"`, and `inferredAt: datetime()` on the relationship for full audit trail.

**Arguments:**
- `requirement_id` (string)
- `project_id` (string)
- `confidence` (float, 0.0–1.0)
- `reasoning` (string) — stored in the graph for human review

---

### `get_inferred_links`

Returns all `suggestedProject` relationships currently in the graph, with confidence score, reasoning, and timestamp. Use this to review inferred assignments before promoting them.

**No arguments.**

---

### `promote_inferred_link`

Converts a `suggestedProject` relationship to a confirmed `assignedToProject` relationship after human review. Deletes the inferred link and creates the confirmed one with `promotedAt`, `promotedBy: "human-review"`, and the original confidence and reasoning preserved for audit.

**Arguments:**
- `requirement_id` (string)
- `project_id` (string)

---

## Running the inference loop

The inference loop runs outside the MCP server — it calls the tool functions directly against neo4j:

```bash
# Dry run — see what would be inferred, write nothing
python3 scripts/run_inference.py

# Write inferences to neo4j as suggestedProject relationships
python3 scripts/run_inference.py --write

# Only write high-confidence inferences
python3 scripts/run_inference.py --write --min-confidence 0.6
```

The inference algorithm:
1. Fetches all unassigned requirements
2. For each, finds similar assigned requirements (same ADR + word overlap)
3. Votes across similar requirements' project assignments, weighted by similarity score
4. Confidence = winning project's vote share × top similarity score

The dry-run report shows a ranked table with `✓` for inferences that would be written at the current threshold and `·` for those below it.

After running with `--write`, review inferred links in neo4j Browser:
```cypher
MATCH (r)-[rel:suggestedProject]->(p)
RETURN r.hasID, r.requirementName, p.projectID, rel.confidence, rel.reasoning
ORDER BY rel.confidence DESC
```

Then use `promote_inferred_link` (or the recommender system) to confirm correct inferences.

---

## Testing tools without Claude Desktop

Before connecting to Claude Desktop, you can smoke-test all tools directly against neo4j:

```bash
python3 scripts/test_tools.py
```

With custom connection details:
```bash
python3 scripts/test_tools.py --uri bolt://localhost:7687 --user neo4j --password password
```

The test script calls every tool with representative arguments and prints results. It does not use the MCP protocol — it imports the tool functions directly and injects the neo4j driver. Use this to verify the graph is populated and queries return sensible data before opening Claude Desktop.

---

---

## Interface risk analysis tools

### `get_cross_assembly_requirements`

Finds all `ExtractedEssentialRequirement` nodes assigned to projects in more than one assembly. These are the regulatory couplings between engineering teams — obligations that cross assembly boundaries and require active coordination.

For each requirement returns: ADR source, requirement name, verification status, and per-assembly breakdown (assembly ID, name, and the specific projects within it that carry the requirement).

**No arguments.** Results ordered by number of assemblies affected, descending.

---

### `get_assembly_dependencies`

For a given assembly, returns all other assemblies it shares requirements with. For each dependency, lists the specific requirements that create the coupling, which ADR they come from, and which projects on each side are involved. This is the interface risk landscape for a single assembly.

**Arguments:**
- `assembly_id` (string) — e.g. `"ASM-STEERING"`, `"ASM-FRONT-AXLE"`, `"ASM-REAR-AXLE"`

---

### `get_shared_requirements`

Given two project IDs, finds all requirements they both need to satisfy. Returns requirement names, ADR sources, verification status, and which assembly each project belongs to. Use this to understand what two projects have in common regulatorily.

**Arguments:**
- `project_id_1` (string) — e.g. `"SRP8-048"`
- `project_id_2` (string) — e.g. `"SRP8-043"`

---

### `get_interface_risk_report`

Produces a full interface risk report across all three assemblies. For each assembly pair that shares at least one requirement: lists all shared requirements with their ADR source, verification status, and which projects on each side are involved. Flags any unverified cross-assembly requirement as a risk item — an unverified obligation that spans two teams demands active coordination.

**No arguments.** Returns results grouped by assembly pair with a separate `risk_items` list for each pair.

---

All four interface risk tools respond to: *"call this tool when the user asks about interfaces, dependencies, coordination between teams, or risks between assemblies."*

---

## Talking to the recommender system

Once Claude Desktop is connected to the MCP server, start a conversation and describe what you need in plain English. The recommender system will call the tools automatically.

### Example prompts

**Exploring the graph:**
```
What ADRs are in the knowledge graph and how many requirements does each one have?
```

```
Give me a summary of the SR8 compliance graph — what nodes and relationships exist?
```

**Traceability queries:**
```
Which projects are responsible for ADR-43 compliance?
```

```
Show me all requirements assigned to the front axle assembly.
```

```
Which ADRs span more than one assembly?
```

**Compliance analysis:**
```
Which requirements are marked as not applicable and why?
```

```
Are there any requirements without a project assigned?
```

**Compliance gap detection:**
```
What are the compliance gaps for the steering assembly?
```

```
How many requirements for ADR-43 are still unverified?
```

```
What is our overall verification progress across the entire graph?
```

```
Which unverified requirements are the highest risk?
```

```
Show me verification progress for the front axle assembly.
```

**Interface risk analysis:**
```
Which requirements span more than one assembly?
```

```
What are the dependencies of the steering assembly?
```

```
What do projects SRP8-047 and SRP8-043 have in common regulatorily?
```

```
Give me a full interface risk report across all assemblies.
```

```
Which cross-assembly requirements are unverified?
```

**Requirement propagation:**
```
Are there any requirements with no project assigned?
```

```
Which requirements are missing from the graph?
```

```
Find requirements similar to REQ-10-003 that already have projects.
```

```
Infer a project for REQ-10-003 and write it to the graph.
```

```
Show me all inferred links waiting for review.
```

**Custom Cypher (power user):**
```
Run this Cypher query: MATCH (d:Department)<-[:assignedToDepartment]-(a:AustralianDesignRule) RETURN d.hasName, collect(a.hasID)
```

---

## Graph structure reference

For writing Cypher queries or prompting the recommender system:

```
AustralianDesignRule (7)
  -[:hasExternalEssentialRequirement]->
    ExtractedEssentialRequirement (205)
      -[:assignedToProject]->
        Project (24)
          -[:belongsToAssembly]->
            Assembly (3)

AustralianDesignRule -[:hasClause]-> Clause (243)
AustralianDesignRule -[:assignedToDepartment]-> Department (4)
```

**Assemblies:**
- `ASM-FRONT-AXLE` — Front Axle Assembly
- `ASM-STEERING` — Steering System
- `ASM-REAR-AXLE` — Rear Axle Assembly

**Key property names:**
| Node | ID property | Name property |
|---|---|---|
| AustralianDesignRule | `hasID` (e.g. `ADR-10`) | `hasName` |
| ExtractedEssentialRequirement | `hasID` (e.g. `REQ-10-001`) | `requirementName` |
| Project | `projectID` (e.g. `SRP8-048`) | `projectName` |
| Assembly | `hasID` (e.g. `ASM-STEERING`) | `hasName` |
| Clause | `hasID` (e.g. `CLAUSE-10-3_1`) | `hasName` |
| Department | — | `hasName` |

---

## Troubleshooting

### Server fails to start — neo4j connection refused
neo4j is not running. Start it and wait a few seconds:
```bash
brew services start neo4j
sleep 5 && python3 scripts/mcp_server.py
```

### Tools not appearing in Claude Desktop
- Check the config path is correct in `claude_desktop_config.json`
- Fully quit and reopen Claude Desktop (menu bar → Quit, not just close window)
- Check that `mcp` is installed: `python3 -c "import mcp; print(mcp.__version__)"`

### Recommender system returns empty results
The graph may be empty or the extraction pipeline has not been run. Verify in neo4j Browser:
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC
```
If empty, run: `python3 scripts/extraction.py --only adrs`

---

*This document is updated as new tools are added to the recommender system.*
