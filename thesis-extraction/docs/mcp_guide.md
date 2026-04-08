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

The recommender system currently has access to two tools:

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
