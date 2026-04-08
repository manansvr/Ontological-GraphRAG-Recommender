# SR8 Extraction Pipeline — Command Reference

## Overview

Two scripts, two sources, one neo4j graph.

| Script | Source | What it writes |
|---|---|---|
| `extract.py` | `csv/*.csv` (7 ADR files) | AustralianDesignRule, Clause, ExtractedEssentialRequirement, Project (stub), Department |
| `run_extraction.py` | orchestrates both | runs extract.py first, then extract_projects.py |

---

## Prerequisites

### Start neo4j
```bash
brew services start neo4j
```

Confirm it is running:
```bash
neo4j status
```

Open the browser at: http://localhost:7474

### Check your folder structure
```
thesis-ontology/
├── csv/                          ← ADR CSV files go here
│   ├── ADR10-Requirements.csv
│   ├── ADR23-Requirements.csv
│   ├── ADR25-Requirements.csv
│   ├── ADR31-Requirements.csv
│   ├── ADR42-Requirements.csv
│   ├── ADR43-Requirements.csv
│   └── ADR92-Requirements.csv
├── data/
│   └── project-tracking-system.csv   ← export from xlsx when ready
├── scripts/
│   ├── extract.py                ← renamed from extract_adrs.py
│   └── run_extraction.py         ← master orchestrator
```

---

## Step 0 — Load the ontology schema (run once on a fresh database)

Copy CSV files to neo4j import folder:
```bash
cp csv/node-labels.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
cp csv/relationships.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
cp csv/node-properties.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
```

Then in neo4j Browser run each block from `docs/one-shot-cypher.md` in order (blocks 1–5).

---

## Step 1 — Extract ADRs

### Dry run first (preview — nothing written to neo4j)
```bash
python3 scripts/run_extraction.py --only adrs --dry-run
```

Check the output:
- ADR IDs show as `ADR-10`, `ADR-23` etc
- Project IDs show as `SRP8-048` etc
- Applicable rows show `[DRY]`, not-applicable rows show `[N/A]`

### Live run
```bash
python3 scripts/run_extraction.py --only adrs
```

### Expected output
```
📁 Found 7 CSV file(s) in csv

📄 ADR10-Requirements.csv
   11 rows | Headers: [...]
   ✓ Clauses: 11 | Requirements: 11 (6 not applicable) | VPs: 0 | Links: 5

📄 ADR23-Requirements.csv  ...
📄 ADR25-Requirements.csv  ...
📄 ADR31-Requirements.csv  ...
📄 ADR42-Requirements.csv  ...
📄 ADR43-Requirements.csv  ...
📄 ADR92-Requirements.csv  ...

   ── TOTAL across 7 files ──
     clauses: 243
     requirements: 205
     not_applicable: 6
     proj_links: 178
```

### Run a single ADR file only
```bash
python3 scripts/extract.py --file csv/ADR10-Requirements.csv --dry-run
python3 scripts/extract.py --file csv/ADR10-Requirements.csv
```

---

## Step 2 — Extract Projects (when xlsx is exported)

Export `project-tracing-system.xlsx` as CSV:
- Google Sheets: `File → Download → Comma Separated Values`
- Place the file at `data/project-tracking-system.csv`

Then run:
```bash
python3 scripts/run_extraction.py --only projects --dry-run
python3 scripts/run_extraction.py --only projects
```

---

## Step 3 — Add Assembly groupings (run once in neo4j Browser)

After extraction, add assembly nodes manually in the Browser.

Delete old assembly links if re-running:
```cypher
MATCH ()-[r:includesProject|belongsToAssembly]->() DELETE r
MATCH (a:Assembly) DETACH DELETE a
```

Create Front Axle Assembly:
```cypher
MERGE (a:Assembly {hasID: "ASM-FRONT-AXLE", hasName: "Front Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-043", "SRP8-045", "SRP8-050", "SRP8-088"]
MERGE (p)-[:belongsToAssembly]->(a)
```

Create Steering System:
```cypher
MERGE (a:Assembly {hasID: "ASM-STEERING", hasName: "Steering System"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-047", "SRP8-048", "SRP8-049"]
MERGE (p)-[:belongsToAssembly]->(a)
```

Create Rear Axle Assembly:
```cypher
MERGE (a:Assembly {hasID: "ASM-REAR-AXLE", hasName: "Rear Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-044", "SRP8-046", "SRP8-051", "SRP8-089"]
MERGE (p)-[:belongsToAssembly]->(a)
```

---

## Verification queries (run in neo4j Browser)

### Count all node types
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
```

### Check ADR → Clause counts
```cypher
MATCH (a:AustralianDesignRule)-[:hasClause]->(c:Clause)
RETURN a.hasID, count(c) AS clauses
ORDER BY a.hasID
```

### Full 4-level hierarchy — one ADR
```cypher
MATCH path1 = (a:AustralianDesignRule {hasID: "ADR-31"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
LIMIT 30
```

### Full 4-level hierarchy — all ADRs
```cypher
MATCH path1 = (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
```

### ADR-43 spans all 3 assemblies (best thesis demo)
```cypher
MATCH path1 = (a:AustralianDesignRule {hasID: "ADR-43"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
```

### Only applicable requirements
```cypher
MATCH path1 = (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
WHERE r.isApplicable = true
RETURN path1, path2
```

---

## Full reset — wipe and reload everything

### 1. In neo4j Browser — wipe all data
```cypher
MATCH (n) DETACH DELETE n
```

### 2. Reload schema (in neo4j Browser — blocks from one-shot-cypher.md)

### 3. In terminal — re-run extraction
```bash
python3 scripts/run_extraction.py --only adrs
python3 scripts/run_extraction.py --only projects
```

### 4. In neo4j Browser — re-add assemblies
Run the three assembly MERGE blocks from Step 3 above.

---

## Troubleshooting

### neo4j not running
```bash
brew services start neo4j
sleep 10 && neo4j status
```

### Connection refused error
neo4j stopped. Start it and wait 10 seconds before running the script again.

### Wrong password
Open http://localhost:7474, log in to confirm your password, then pass it:
```bash
python3 scripts/run_extraction.py --only adrs --password yourpassword
```

### ADR folder not found
The script looks for `csv/` by default. Confirm your CSVs are there:
```bash
ls csv/
```

### Re-running is always safe
All writes use `MERGE` — running the extraction twice never creates duplicates.

---

## Knowledge Extension

After extraction, the graph can be queried and extended through an MCP (Model Context Protocol) server that exposes the knowledge graph as tools Claude can call autonomously. Claude acts as a recommender system over the graph.

### Starting the MCP server

```bash
pip install -r requirements.txt   # first time only
python3 scripts/mcp_server.py
```

The server connects to neo4j at `bolt://localhost:7687` by default and runs over stdio. Keep neo4j running before starting it.

To connect to Claude Desktop, merge `docs/claude_desktop_config.json` into `~/Library/Application Support/Claude/claude_desktop_config.json` and restart Claude Desktop. See `docs/mcp_guide.md` for full connection instructions.

---

### Tool reference

The MCP server exposes nineteen tools grouped into five areas:

#### Graph exploration

| Tool | What it does |
|---|---|
| `get_graph_schema` | Returns live node labels, relationship types, and property keys |
| `query_graph(cypher)` | Executes any Cypher query and returns JSON results |

**Example questions:**
- *"What does the SR8 knowledge graph contain?"*
- *"Run this Cypher query: MATCH (n) RETURN labels(n), count(n)"*

---

#### Compliance gap detection

| Tool | What it does |
|---|---|
| `get_compliance_gaps(project_id, adr_id, assembly_id)` | Unverified applicable requirements, optionally filtered |
| `get_verification_progress(project_id, assembly_id)` | Verified / unverified counts and completion percentage |
| `get_highest_risk_gaps()` | Top 10 unverified requirements by number of projects affected |

**Example questions:**
- *"What are the compliance gaps for the steering assembly?"*
- *"What is our overall verification progress?"*
- *"Which unverified requirements are the highest risk?"*
- *"How many requirements for ADR-43 are still open?"*

---

#### Interface risk analysis

| Tool | What it does |
|---|---|
| `get_cross_assembly_requirements()` | Requirements that span more than one assembly |
| `get_assembly_dependencies(assembly_id)` | All assemblies a given assembly shares requirements with |
| `get_shared_requirements(project_id_1, project_id_2)` | Requirements two specific projects have in common |
| `get_interface_risk_report()` | Full cross-assembly risk report with flagged items |

**Example questions:**
- *"Which requirements span more than one assembly?"*
- *"What are the dependencies of the steering assembly?"*
- *"What do projects SRP8-047 and SRP8-043 have in common regulatorily?"*
- *"Give me a full interface risk report across all assemblies."*

---

#### Requirement propagation inference

| Tool | What it does |
|---|---|
| `get_unassigned_requirements()` | Requirements with no project assignment |
| `get_similar_assigned_requirements(requirement_id)` | 5 most similar requirements that do have assignments |
| `write_inferred_project_link(requirement_id, project_id, confidence, reasoning)` | Writes a `suggestedProject` relationship (never `assignedToProject`) |
| `get_inferred_links()` | All inferred links waiting for human review |
| `promote_inferred_link(requirement_id, project_id)` | Converts an inferred link to a confirmed assignment |

To run inference in bulk without Claude Desktop, use the standalone loop:

```bash
python3 scripts/run_inference.py              # dry run
python3 scripts/run_inference.py --write      # write to neo4j
python3 scripts/run_inference.py --write --min-confidence 0.6
```

**Example questions:**
- *"Are there any requirements with no project assigned?"*
- *"Which requirements are missing from the graph?"*
- *"Infer a project for REQ-10-003 and write it to the graph."*
- *"Show me all inferred links waiting for review."*

---

#### Change impact analysis

| Tool | What it does |
|---|---|
| `get_requirements_by_keyword(keyword)` | Searches requirement names, descriptions, and clause text |
| `get_requirement_chain(requirement_id)` | Full chain: ADR → requirement → projects → assemblies |
| `get_reverification_scope(project_ids)` | Groups requirements into must-reverify / must-verify / not-affected |
| `write_change_impact_report(...)` | Stores a `ChangeImpactReport` node linked to affected nodes |
| `get_change_impact_reports()` | All past impact reports, newest first |

**Example questions:**
- *"Which requirements are related to steering geometry?"*
- *"Show me the full regulatory chain for REQ-43-007."*
- *"If projects SRP8-047 and SRP8-048 change, what needs re-verification?"*
- *"Write a change impact report for the steering rack geometry change."*
- *"What change impact reports have been recorded?"*

---

### Smoke-testing all tools

Run the test script directly against neo4j (no MCP protocol):

```bash
python3 scripts/test_tools.py
```

This calls every tool with representative arguments and prints results. Use it to verify the graph is populated and queries return sensible data before opening Claude Desktop.