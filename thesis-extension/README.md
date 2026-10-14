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
                                                                         └─[:belongsToAssembly]→ Assembly
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
| Inference | `get_unassigned_requirements`, `get_similar_assigned_requirements`, `write_inferred_project_link`, `get_inferred_links` |
| Change impact | `get_requirements_by_keyword`, `get_requirement_chain`, `get_reverification_scope`, `write_change_impact_report`, `get_change_impact_reports` |
| RL / feedback (read-only) | `get_feedback_stats`, `get_rl_policy` |

These 38 tools are all the LLM can call. Reviewing suggestions and recording feedback are deliberately **not** MCP tools, so the model cannot confirm, modify or reject its own suggestions; see [Reviewing inferred links](#reviewing-inferred-links).

## Fixed routes in ollama-mcp

Before the RL step, `ollama-mcp` checks one explicit `ROUTES` list (name, matcher, handler, `uses_llm`) from top to bottom; the first match handles the turn. Routes with `uses_llm = false` call one tool (or a human review function) directly and print its raw output without calling the model; their turn records have `route = <name>` and `llm_calls = 0`. Anything that matches no route goes to the RL-guided path (`rl_prefetch`). Print the table with:

```bash
python3 thesis-extension/ollama-mcp --print-routes
```

## Neo4j graph structure

Node labels used by the MCP tools:

- `AustralianDesignRule` — an ADR; `hasID`, `hasName`, `isVerified`
- `ExtractedEssentialRequirement` — a requirement extracted from an ADR; `hasID`, `requirementName`, `requirementDescription`, `isApplicable`, `hasRiskLevel`
- `Clause` — a clause within an ADR; `hasID`, `hasName`, `clauseText`
- `Project` — an SR8 project area; `projectID`, `projectName`
- `Assembly` — a group of projects; `hasID` (e.g. `ASM-FRONT-AXLE`, `ASM-STEERING`, `ASM-REAR-AXLE`), `hasName`. Created by `thesis-extraction/Scripts/run-extraction.py --only assemblies` from `thesis-extraction/data/assemblies.csv`
- `ChangeImpactReport` — written by `write_change_impact_report`; `hasID`, `changeDescription`, `riskSummary`, `createdAt`
- `FeedbackEvent` — written when a person reviews a suggestion (`promote_inferred_link`, `modify_inferred_link`, `reject_inferred_link`; also the uncalled `record_feedback` function); `hasID`, `requirementID`, `projectID`, `action`, `reward`, `inferenceState`, `overconfidencePenaltyApplied`, `rlAction` (the action credited), `reviewer` (null when written by `record_feedback`), `timestamp`

Relationship types:

- `hasExternalEssentialRequirement` — ADR → Requirement
- `assignedToProject` — Requirement → Project (confirmed). `source = 'extracted'` when created by `extract-ADR.py`; `source = 'inferred'` when created by `promote_inferred_link`, or `'inferred-modified'` (plus `modifiedFromProject`, `modificationReason`) when a reviewer assigned a different project through `modify_inferred_link`; both also store `promotedAt`, `promotedBy` (the reviewer), `promotedFromConfidence`, `inferenceReasoning`, `inferredBy`, `inferredAt` and `inferenceState`
- `suggestedProject` — Requirement → Project (machine inference, written by `write_inferred_project_link`). Never deleted: a pending suggestion has no `status`; after review it has `status = 'promoted'`, `'modified'` or `'rejected'`, `reviewedBy`, `reviewedAt`, for modifications `modifiedTo` and `modificationReason`, and for rejections `rejectionReason`. A revised pending suggestion also has `previousConfidence`, `previousReasoning` and `revisionCount`; a resubmitted one has `resubmissionOf` (the reviewed suggestion's `inferredAt`). Every written suggestion has `schemaValidated = true` and `schemaCheckedAt`. `get_inferred_links` and `get_unassigned_requirements` hide reviewed suggestions unless `include_reviewed=True`
- `belongsToAssembly` — Project → Assembly (declared in `thesis-ontology/csv/relationships.csv`)
- `hasClause` — ADR → Clause
- `affectsRequirement` / `affectsProject` — ChangeImpactReport → Requirement / Project

### Schema validation

`write_inferred_project_link` and `write_change_impact_report` check each relationship they create against the schema layer before writing (`_validate_against_schema`). The relationship type must exist as a `SchemaRelationship` node (imported from `thesis-ontology/csv/relationships.csv`), and its `sourceLabel` and `targetLabel` must be among the node's labels or their `SUBCLASS_OF` ancestors (`A|B` means either; `All` matches any node). The check fails closed: if the schema layer has not been loaded, or the relationship type is not declared, nothing is written and the response's `schema_validation` gives the reason. Load the schema once before using these tools:

```bash
cd thesis-ontology && python3 scripts/import.py --password <neo4j password>
```
- `recordedFor` — FeedbackEvent → Requirement / Project

## Reviewing inferred links

Only people review suggestions. The review functions in `sr8-mcp` are plain Python functions, not MCP tools, and are reached in two ways:

- **`scripts/review-links.py --reviewer "<name>"`** lists every pending suggestion (requirement, project, confidence, reasoning, inference state, inferred at) and asks the reviewer to **c**onfirm, **m**odify (assign a different project), **r**eject (reason required) or **s**kip each one. Run it with the same Python environment as `sr8-mcp`.
- **Typed commands in `ollama-mcp`**, handled before anything is sent to the model:
  - `confirm link <REQ> -> <PROJECT>`
  - `reject link <REQ> -> <PROJECT> because <reason>`

  The first such command in a session asks for the reviewer's name, which is then used for the rest of the session. They only run from what the user types, never from a model tool call.

| Decision | Function | Reward | Suggestion | `assignedToProject` |
|---|---|---|---|---|
| confirm | `promote_inferred_link(req, project, reviewer)` | 1.0 | `status='promoted'` | created, `source='inferred'` |
| modify | `modify_inferred_link(req, suggested_project, new_project, reviewer, reason)` | 0.5 | `status='modified'`, `modifiedTo` | created to the new project, `source='inferred-modified'` |
| reject | `reject_inferred_link(req, project, reviewer, reason)` | -1.0, or -2.0 if confidence > 0.8 | `status='rejected'`, `rejectionReason` | none |

Each requires a non-empty `reviewer` and, in one transaction, records a `FeedbackEvent` with the reviewer (reading the confidence and inference state from the suggestion before it changes) and marks the suggestion as reviewed; the RL agent is then updated. An existing `assignedToProject` link is never overwritten. `record_feedback` is no longer called by anything in the repository.

A reviewed suggestion is never modified. `write_inferred_project_link`:

- does not write if the requirement is already `assignedToProject` to that project (returns `already_assigned` and the edge's `source`);
- does not write if the pair only has reviewed suggestions, and returns the latest decision (`previously_reviewed`); with `resubmit=True` it creates a second `suggestedProject` edge with `resubmissionOf` instead;
- updates a pending suggestion in place, keeping `previousConfidence`, `previousReasoning` and `revisionCount`;
- still writes, with a `warning`, if the requirement is assigned to a different project.

`promote_inferred_link`, `modify_inferred_link`, `reject_inferred_link` and `record_feedback` act only on the pending suggestion. If the pair has none, no `FeedbackEvent` is written and the earlier decision is returned with the error, so a decision is never counted twice.

Auditing the three kinds of project link:

```cypher
// Grounded links from the ADR checklists
MATCH (r:ExtractedEssentialRequirement)-[a:assignedToProject {source: 'extracted'}]->(p:Project)
RETURN r.hasID, p.projectID;

// Pending machine inferences
MATCH (r:ExtractedEssentialRequirement)-[s:suggestedProject]->(p:Project)
WHERE s.status IS NULL
RETURN r.hasID, p.projectID, s.confidence, s.inferenceState, s.reasoning;

// Human-confirmed inferences
MATCH (r:ExtractedEssentialRequirement)-[a:assignedToProject {source: 'inferred'}]->(p:Project)
MATCH (r)-[s:suggestedProject {status: 'promoted'}]->(p)
RETURN r.hasID, p.projectID, a.promotedBy, a.promotedAt, a.promotedFromConfidence, s.reviewedBy, s.reviewedAt;

// Human corrections of inferences (reviewer assigned a different project)
MATCH (r:ExtractedEssentialRequirement)-[a:assignedToProject {source: 'inferred-modified'}]->(p:Project)
MATCH (r)-[s:suggestedProject {status: 'modified', modifiedTo: p.projectID}]->(sp:Project)
RETURN r.hasID, sp.projectID AS suggested, p.projectID AS assigned, a.promotedBy, a.modificationReason;
```

Links promoted by the earlier version of `promote_inferred_link` have `promotedBy = 'human-review'`, no `source` and no surviving suggestion. Two scripts handle existing graphs (neither runs automatically):

- `scripts/export-confirmed-links.py` — read-only; writes every `assignedToProject` edge with `promotedBy` set to a CSV (requirement, project, promotedBy, promotedAt, promotedFromConfidence, source). Run it before a clean rebuild so human decisions are not lost.
- `scripts/backfill-link-source.cypher` — for graphs that are not rebuilt; sets `source = 'extracted'` on edges with no `promotedBy`, and `source = 'inferred-legacy'` on edges with `promotedBy = 'human-review'`. Only edges without a `source` are changed.

Offline unit tests for these rules (mocked Neo4j session, no server needed):

```bash
python3 -m unittest discover -s thesis-extension/tests -v
```

## Reinforcement learning

`reinforcemnt-learning.py` provides tabular Q-learning for two separate problems, stored in one `.rl-model.json` (`schema_version` 3) with a section each: `problem_a` and `problem_b`, each holding its own `config` (epsilon, alpha, gamma), `q_table` and `episode_rewards`. Exploration decay in one problem never affects the other.

- **Problem A: retrieval strategy (`ollama-mcp`).** For questions naming an ADR/SRP (`adr_lookup`) the agent chooses `graph_first`, `documents_first` or `hybrid` prefetching; discount factor 0.9. Other questions (`general_lookup`) have only `documents_first`, so they are not learned. There is no synthetic prior: the earlier toy environment trained an `adr_question` state the client never uses, so Problem A learns only from live turns. Its `adr_lookup` Q-values were reset to 0.0 (they had been learned under the earlier reward, which counted client-appended evidence as a citation), its epsilon to 0.15 and its `episode_rewards` cleared; the old values remain in `.rl-model.backup-2026-10-12.json`. The reward is computed from the model's own answer, before the client appends evidence or substitutes the "not enough context" fallback: −0.8 if the fallback is used (this replaces everything else); otherwise +0.2 if a tool ran, plus +0.8 if the model itself cited a file (`path | row/line N`) or −0.2 if it did not. Evidence the client appends on the model's behalf is recorded (`evidence_available`) but not rewarded.
- **Problem B: inference confidence (`sr8-mcp`).** When `write_inferred_project_link` writes a suggestion, the agent picks `increase_confidence` (+0.1), `keep_confidence` or `decrease_confidence` (−0.1) for the state `inference_<strong|weak>_<yes|no>_<high|mid|low>`:
  - `strong`: at least 3 requirements from the same ADR are already assigned to a project;
  - `yes`: the candidate project already holds at least one assigned requirement from the same ADR;
  - the band of the caller's confidence (`CONFIDENCE_BANDS`): high > 0.7, mid > 0.4, low ≤ 0.4.

  The suggestion stores `baseConfidence`, the adjusted `confidence`, `rlAction` and `inferenceState`. When a person confirms (+1.0), modifies (+0.5) or rejects (−1.0, or −2.0 if the stored confidence was above 0.8) it, Q(`inferenceState`, `rlAction`) is updated. Each suggestion is a one-step decision, so Problem B uses discount factor 0.0: Q ← Q + α(r − Q). Suggestions written before `rlAction` existed do not update the Q-table (`rl_updated: false`).
- **Cold-start prior.** If `problem_b` has no inference states, `sr8-mcp` seeds them from `train_inference_agent()` using `INFERENCE_PRIOR_REWARD_MODEL`, a hand-designed reward model, not data. With seed 99 it first visits every state-action pair 5 times (180 single-step updates, so no pair keeps its untried initial value of 0.0), then runs 1000 epsilon-greedy single-step episodes. In the resulting prior every state's greedy action is its category's best action under the reward model. Print its Q-table with `python3 thesis-extension/reinforcemnt-learning.py --inference-table`.
- **Version 2 files** (one shared agent) are migrated automatically on the first save: `inference_*` states go to `problem_b` (with the new single-step config), everything else plus the old config and `episode_rewards` to `problem_a`. To migrate explicitly: `python3 thesis-extension/reinforcemnt-learning.py --migrate thesis-extension/.rl-model.json`.

The model file is loaded automatically when `sr8-mcp.py` starts. Both processes find the model file with the same rule, in `rl_model_path.py`: `RL_MODEL_PATH` unset or empty means `thesis-extension/.rl-model.json`, a relative value is resolved against the `thesis-extension` folder (not the current working directory), and an absolute value is used as given. `ollama-mcp` only ever writes `problem_a` and `sr8-mcp` only `problem_b`, both through `locked_update`. `sr8-mcp`, `ollama-mcp` and `scripts/review-links.py` each hold their own in-memory copy, so every save goes through `locked_update`: it locks `.rl-model.json.lock`, reloads the latest file, applies only that process's change and writes atomically, so no process overwrites another's learning.

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

## Logs

Both programs append one JSON object per line to `thesis-extension/logs/` (created on first write, ignored by git). Logging never interrupts the chat or a tool call.

**`logs/turns.jsonl`** (`ollama-mcp`, one line per user turn, however the turn ends):

| Field | Meaning |
|---|---|
| `timestamp`, `session_id`, `model` | UTC start time; one id per `ollama-mcp` run; Ollama model |
| `question` | what the user typed |
| `route` | `review_confirm` / `review_reject` / `review_usage`, `count_requirements`, `reference`, `design_guidance` or `rl_prefetch` |
| `rl_state`, `rl_action` | Problem A state and chosen strategy (`rl_prefetch` only) |
| `forced_strategy` | always `null` (no option to force a strategy exists yet) |
| `tool_calls` | each call's `name`, `args`, `status` (`ok`, `empty` or `error`) and `duration_ms` |
| `reward_components` | `tool_used`, `model_cited`, `evidence_available`, `fallback_used`, `total` (`rl_prefetch` only) |
| `evidence_appended` | the client appended `Evidence:` because the model did not cite |
| `answer`, `latency_ms`, `llm_calls` | text shown to the user, turn duration, number of Ollama chat calls |

**`logs/inference.jsonl`** (`sr8-mcp`, one line per `write_inferred_project_link` call and per review event: `promote`, `modify`, `reject`, `record_feedback`, including refused ones): `event`, `outcome`, `error`, `requirement_id`, `project_id` (and `new_project_id` for modify), `base_confidence`, `adjusted_confidence`, `inference_state`, `rl_action`, `reward`, `overconfidence_penalty_applied`, `rl_updated`, `reviewer`, `reason`, `schema_validation` (the write-time check, or the `schemaValidated` flag stored on the suggestion for review events), `write_mode` and `previous_decision`.

## Retrieval-strategy experiment

Two environment variables control Problem A for experiments (both read by `ollama-mcp`):

- `RETRIEVAL_STRATEGY=rl|graph_first|documents_first|hybrid` (default `rl`). When not `rl`, every `adr_lookup` turn uses that strategy instead of the agent's choice; the turn log records it as `forced_strategy`, and a forced turn never updates the Q-table.
- `RL_LEARNING=true|false` (default `true`). When `false`, the learned policy is used greedily (no exploration) and the model file is neither updated nor saved.

Each live Problem A update appends its reward to `problem_a.episode_rewards` in `.rl-model.json`, so its length is the number of updates Problem A has received; each turn record also has `rl_updated`.

`experiments/` holds the question sets and the runner:

- `questions.csv`: 25 evaluation questions over all 8 ADRs (requirement counts, specific lookups, verification methods, evidence/source questions, cross-ADR questions).
- `train_questions.csv`: 30 different training questions.
- Both have `expected_requirement_ids`. These are IDs from `ADR-mapping.json`, restricted to requirements whose mapping ID equals the graph ID that `extract-ADR.py` assigns; for ADR-23, ADR-25 and ADR-31 the two numberings differ for many rows. Every question is worded so it takes the RL route (no "how many … requirement", "reference" or design/manufacturing keywords), which `tests/test_experiments.py` checks.
- `run-baseline.py` runs each question through `ollama-mcp`'s own chat loop in a fresh session:
  - `--train --passes N`: `train_questions.csv`, N times, strategy `rl`, learning on.
  - `--evaluate`: `questions.csv` for `graph_first`, `documents_first`, `hybrid` and `rl`, learning off.
  - `--limit K` runs only the first K questions (a quick check).

  Results go to `experiments/results/`: `<mode>-<timestamp>.csv` (one row per question and strategy: route, chosen and forced strategy, `model_cited`, `fallback_used`, `evidence_appended`, expected IDs found as count and fraction, tool calls, LLM calls, latency, `rl_updated`), `-summary.csv` (per-strategy means and Problem A's update counts), `-turns.jsonl` and `-transcript.txt`.

Problem A has a single learnable state (`adr_lookup`), so training learns one overall best strategy rather than a per-question choice.
