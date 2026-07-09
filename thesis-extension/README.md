# SR8 Compliance Knowledge Graph — Thesis Extension

A Formula SAE SR8 compliance assistant built on Neo4j, Ollama, and the Model Context Protocol (MCP). The system extracts requirements from Australian Design Rules (ADRs), maps them to projects and assemblies in a knowledge graph, and exposes 33 tools for compliance analysis, interface risk detection, inference, and change impact tracking.

## Architecture

```
ollama-mcp.py  ←→  sr8-mcp.py (MCP server, 33 tools)  ←→  Neo4j
                         ↕
               reinforcemnt-learning.py (Q-learning agent)
```

**Graph hierarchy**

```
AustralianDesignRule
  └─[:hasExternalEssentialRequirement]→ ExtractedEssentialRequirement
                                              └─[:assignedToProject]→ Project
                                                                         └─[:partOfAssembly]→ Assembly
```

## Prerequisites

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.11+ | |
| Neo4j | 5.x | Running locally on bolt://localhost:7687 |
| Ollama | latest | Running locally with `llama3.1:8b` pulled |
| tesseract | any | System dependency for OCR (`brew install tesseract`) |
| poppler | any | System dependency for pdf2image (`brew install poppler`) |

## Setup

### 1. Python dependencies

```bash
cd thesis-extension
pip install -r requirements.txt
```

### 2. Environment configuration

```bash
cp .env.example .env
# Edit .env — set NEO4J_PASSWORD and confirm OLLAMA_URL/OLLAMA_MODEL
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | — | Neo4j password (required) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `OLLAMA_MODEL` | `llama3.1:8b` | Model name |
| `DOC_ROOTS` | *(empty — uses relative fallbacks)* | Comma-separated paths to local document directories |
| `EXTRACTION_ROOT` | *(empty — uses relative fallback)* | Path to thesis-extraction directory |

Leave `DOC_ROOTS` and `EXTRACTION_ROOT` empty to use the default paths relative to this repository.

### 3. Pull the Ollama model

```bash
ollama pull llama3.1:8b
```

## Running the MCP server

```bash
python3 thesis-extension/sr8-mcp.py
```

The server runs on `stdio` transport and is driven by `ollama-mcp.py`. Running it directly will appear idle, which is expected.

## Running the Ollama client

```bash
python3 thesis-extension/ollama-mcp.py
```

This starts an interactive chat session. The client drives the MCP server as a child process, calls tools automatically, and maintains conversation context.

**Do not modify `ollama-mcp.py`.**

## Running the test script

```bash
python3 thesis-extension/test_recommender.py
```

Runs 5 pre-defined questions against the knowledge graph and Ollama, printing tool calls, answers, and a summary. Neo4j and Ollama must both be running.

## Regenerating ADR mapping files

```bash
python3 thesis-extension/sync-ADR-mapping.py
```

Reads `thesis-extraction/csv/ADR*-Requirements.csv` and writes `ADR-mapping.csv` and `ADR-mapping.json` into this directory.

## Tool categories

| Category | Tools |
|----------|-------|
| Document search | `list_documents`, `search_local_documents`, `suggest_requirement_sources`, `read_document`, `run_extraction_for_requirements` |
| GraphRAG lookup | `get_project`, `get_adr`, `get_assembly`, `search_requirements`, `list_all_projects`, `list_all_adrs`, `get_adr_requirements` |
| Cypher passthrough | `query_knowledge_graph` (read-only MATCH queries only) |
| Compliance gaps | `get_compliance_gaps`, `get_verification_progress`, `get_highest_risk_gaps` |
| Interface risk | `get_cross_assembly_requirements`, `get_assembly_dependencies`, `get_shared_requirements`, `get_interface_risk_report` |
| Inference | `get_unassigned_requirements`, `get_similar_assigned_requirements`, `write_inferred_project_link`, `get_inferred_links`, `promote_inferred_link` |
| Change impact | `get_requirements_by_keyword`, `get_requirement_chain`, `get_reverification_scope`, `write_change_impact_report`, `get_change_impact_reports` |
| RL / feedback | `record_feedback`, `get_feedback_stats`, `get_rl_policy` |

## Neo4j graph structure

Node labels used by the MCP tools:

- `AustralianDesignRule` — an ADR; `hasID`, `hasName`, `isVerified`
- `ExtractedEssentialRequirement` — a requirement extracted from an ADR; `hasID`, `requirementName`, `requirementDescription`, `isApplicable`, `hasRiskLevel`
- `Clause` — a clause within an ADR; `hasID`, `hasName`, `clauseText`
- `Project` — an SR8 project area; `projectID`, `projectName`
- `Assembly` (or any node with `assemblyID`) — e.g. `ASM-FRONT-AXLE`, `ASM-STEERING`, `ASM-REAR-AXLE`
- `ChangeImpactReport` — written by `write_change_impact_report`; `hasID`, `changeDescription`, `riskSummary`, `createdAt`
- `FeedbackEvent` — written by `record_feedback`; `hasID`, `action`, `reward`, `timestamp`

Relationship types:

- `hasExternalEssentialRequirement` — ADR → Requirement
- `assignedToProject` — Requirement → Project (confirmed)
- `suggestedProject` — Requirement → Project (inferred; promoted by `promote_inferred_link`)
- `partOfAssembly` — Project → Assembly
- `hasClause` — ADR → Clause
- `affectsRequirement` / `affectsProject` — ChangeImpactReport → Requirement / Project
- `recordedFor` — FeedbackEvent → Requirement / Project

## Reinforcement learning

The RL agent in `reinforcemnt-learning.py` learns from human feedback via `record_feedback`. The Q-table is saved to `.rl-model.json` and loaded automatically when `sr8-mcp.py` starts. It adjusts confidence scores on inferred project links (`write_inferred_project_link`) based on prior feedback signals.

Run the built-in self-test:

```bash
python3 thesis-extension/reinforcemnt-learning.py --self-test
```

## Notes

- `query_knowledge_graph` accepts only MATCH-starting Cypher; write clauses are blocked.
- Document reads are restricted to paths under `DOC_ROOTS`.
- All Neo4j writes in the MCP tools use MERGE, never CREATE.
- Set `STRICT_CONTEXT_ONLY=false` in `.env` to allow non-contextual model responses.
- Set `OCR_ENABLED=false` to disable the tesseract OCR fallback for scanned PDFs.
