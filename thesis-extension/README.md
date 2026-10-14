# SR8 Compliance Knowledge Graph — Thesis Extension

A Formula SAE SR8 compliance assistant built on Neo4j, Ollama, and the Model Context Protocol (MCP). The system extracts requirements from Australian Design Rules (ADRs), maps them to projects and assemblies in a knowledge graph, and exposes 39 MCP tools for document search, compliance analysis, interface risk detection, inference, and change impact tracking.

## Architecture

```
ollama-mcp  ←→  sr8-mcp (MCP server, 39 tools)  ←→  Neo4j
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
| Python | 3.10+ | `mcp` requires 3.10 |
| Neo4j | 5.x | Running locally on bolt://localhost:7687 |
| Ollama | latest | Running locally with `qwen2.5:14b-instruct` pulled |
| tesseract | any | System dependency for OCR (`brew install tesseract`) |
| poppler | any | System dependency for pdf2image (`brew install poppler`) |

## Setup

### 1. Python dependencies

```bash
python3 -m pip install -r requirements.txt   # from the repository root
```

`requirements.txt` at the repository root lists every third-party package; `thesis-extension/requirements.txt` only includes it.

### 2. Environment configuration

```bash
cp .env.example .env
# Edit .env — set NEO4J_PASSWORD (the example holds a placeholder). .env is git-ignored; never commit it.
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password (set your own) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama base URL (`test_recommender.py` also accepts `OLLAMA_URL`) |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Model name |
| `STRICT_CONTEXT_ONLY` | `true` | If no tool ran this turn, the answer is replaced by the "not enough context" fallback |
| `REQUIRE_EXPLICIT_CITATIONS` | `false` | If `true`, an answer without a file citation (`path \| row/line N`) gets the tools' evidence appended, or the fallback if there is none; this also replaces answers from graph-only tools such as `list_all_projects` or `get_rl_policy`, which have no file to cite |
| `RL_ENABLED` | `true` | `false`: `ollama-mcp` chooses no retrieval strategy and learns nothing |
| `RL_LEARNING` | `true` | `false`: learned policies are used greedily and never updated or saved |
| `RETRIEVAL_STRATEGY` | `rl` | `rl`, `graph_first`, `documents_first` or `hybrid` (fixes the `adr_lookup` strategy) |
| `RL_MODEL_PATH` | `.rl-model.json` | Relative paths resolve against `thesis-extension/`. Set it in `.env`: `sr8-mcp` reads `.env` but does not inherit `ollama-mcp`'s shell variables |
| `DOC_ROOTS` | *(empty — uses relative fallbacks)* | Comma-separated paths to local document directories |
| `EXTRACTION_ROOT` | *(empty — uses relative fallback)* | Path to thesis-extraction directory |

Leave `DOC_ROOTS` and `EXTRACTION_ROOT` empty to use the default paths relative to this repository.

### 3. Pull the Ollama model

```bash
ollama pull qwen2.5:14b-instruct
```

## Running the MCP server

```bash
python3 thesis-extension/sr8-mcp
```

The server runs on `stdio` transport and is driven by `ollama-mcp`. Running it directly will appear idle, which is expected.

## Running the Ollama client

```bash
python3 thesis-extension/ollama-mcp
```

This starts an interactive chat session. The client drives the MCP server as a child process, calls tools automatically, and maintains conversation context.

## Running the test script

```bash
python3 thesis-extension/test_recommender.py
```

Intended to run 5 pre-defined questions against the knowledge graph and Ollama, printing tool calls, answers, and a summary. Neo4j and Ollama must both be running. **It currently exits at start-up**: it loads `sr8-mcp.py`, but the server file is `sr8-mcp` (no extension).

## Regenerating ADR mapping files

```bash
python3 thesis-extension/sync-ADR-mapping.py
```

Reads `thesis-extraction/csv/ADR*-Requirements.csv` and writes `thesis-extension/ADR-mapping.csv` and `thesis-extension/ADR-mapping.json` (sr8-mcp falls back to them when the graph has no rows for an ADR). The committed copies hold `source_file` paths from the original author's machine; rerun this to refresh them.

## Tool categories

| Category | Tools |
|----------|-------|
| Document search | `list_documents`, `search_local_documents`, `suggest_requirement_sources`, `read_document`, `summarize_document`, `search_keywords`, `search_braking`, `search_tyre`, `search_manufacturing` |
| Extraction | `run_extraction_for_requirements`, `extraction_report`, `adr_mapping_stats` |
| GraphRAG lookup | `get_project`, `get_adr`, `get_assembly`, `search_requirements`, `list_all_projects`, `list_all_adrs`, `get_adr_requirements` |
| Cypher passthrough | `query_knowledge_graph` (read-only MATCH queries only) |
| Compliance gaps | `get_compliance_gaps`, `get_verification_progress`, `get_highest_risk_gaps` |
| Interface risk | `get_cross_assembly_requirements`, `get_assembly_dependencies`, `get_shared_requirements`, `get_interface_risk_report` |
| FMEA coverage | `get_unmitigated_failure_modes` (components satisfying an FMEA requirement whose failure modes have no `mitigatedBy` control action, with a pointer to the workbook sheet and row) |
| Inference | `get_unassigned_requirements`, `get_similar_assigned_requirements`, `write_inferred_project_link`, `get_inferred_links` |
| Change impact | `get_requirements_by_keyword`, `get_requirement_chain`, `get_reverification_scope`, `write_change_impact_report`, `get_change_impact_reports` |
| RL / feedback (read-only) | `get_feedback_stats`, `get_rl_policy` |

These 39 tools are all the LLM can call. Reviewing suggestions and recording feedback are deliberately **not** MCP tools, so the model cannot confirm, modify or reject its own suggestions; see [Reviewing inferred links](#reviewing-inferred-links).

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
- `FeedbackEvent` — written when a person reviews a suggestion (`promote_inferred_link`, `modify_inferred_link`, `reject_inferred_link`; also the uncalled `record_feedback` function); `hasID`, `requirementID`, `projectID`, `action`, `reward`, `inferenceState`, `overconfidencePenaltyApplied`, `rlAction` (the action credited), `reviewer` (null when written by `record_feedback`), `hasTimestamp` (older events have `timestamp`)

Relationship types:

- `hasExternalEssentialRequirement` — ADR → Requirement
- `assignedToProject` — Requirement → Project (confirmed). `source = 'extracted'` when created by `extract-ADR.py`; `source = 'inferred'` when created by `promote_inferred_link`, or `'inferred-modified'` (plus `modifiedFromProject`, `modificationReason`) when a reviewer assigned a different project through `modify_inferred_link`; both also store `promotedAt`, `promotedBy` (the reviewer), `promotedFromConfidence`, `inferenceReasoning`, `inferredBy`, `inferredAt` and `inferenceState`
- `suggestedProject` — Requirement → Project (machine inference, written by `write_inferred_project_link`). Never deleted: a pending suggestion has no `status`; after review it has `status = 'promoted'`, `'modified'` or `'rejected'`, `reviewedBy`, `reviewedAt`, for modifications `modifiedTo` and `modificationReason`, and for rejections `rejectionReason`. A revised pending suggestion also has `previousConfidence`, `previousReasoning` and `revisionCount`; a resubmitted one has `resubmissionOf` (the reviewed suggestion's `inferredAt`). Every written suggestion has `schemaValidated = true` and `schemaCheckedAt`. `get_inferred_links` and `get_unassigned_requirements` hide reviewed suggestions unless `include_reviewed=True`
- `belongsToAssembly` — Project → Assembly (declared in `thesis-ontology/csv/relationships.csv`)
- `hasClause` — ADR → Clause
- `affectsRequirement` / `affectsProject` — ChangeImpactReport → Requirement / Project
- `recordedFor` — FeedbackEvent → Requirement / Project

### Schema validation

`write_inferred_project_link` and `write_change_impact_report` check each relationship they create against the schema layer before writing (`_validate_against_schema`). The relationship type must exist as a `SchemaRelationship` node (imported from `thesis-ontology/csv/relationships.csv`), and its `sourceLabel` and `targetLabel` must be among the node's labels or their `SUBCLASS_OF` ancestors (`A|B` means either; `All` matches any node). The check fails closed: if the schema layer has not been loaded, or the relationship type is not declared, nothing is written and the response's `schema_validation` gives the reason. Load the schema once before using these tools:

```bash
cd thesis-ontology && python3 scripts/import.py --password <neo4j password>
```

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
  - `strong`: the best same-ADR assigned neighbour from `get_similar_assigned_requirements` scores at least `EVIDENCE_SCORE_THRESHOLD` = 0.5 (score = clause adjacency 0/1 + name-word overlap 0–1), i.e. a close neighbour exists. On the 45 currently unassigned requirements this makes 31 (69%) strong; the earlier rule (≥ 3 assigned same-ADR requirements) made all 45 strong;
  - `yes`: the candidate project already holds at least one assigned requirement from the same ADR;
  - the band of the caller's confidence (`CONFIDENCE_BANDS`): high > 0.7, mid > 0.4, low ≤ 0.4.

  The suggestion stores `baseConfidence`, the adjusted `confidence`, `rlAction` and `inferenceState`. When a person confirms (+1.0), modifies (+0.5) or rejects (−1.0, or −2.0 if the stored confidence was above 0.8) it, Q(`inferenceState`, `rlAction`) is updated. Each suggestion is a one-step decision, so Problem B uses discount factor 0.0: Q ← Q + α(r − Q). Suggestions written before `rlAction` existed do not update the Q-table (`rl_updated: false`).
- **Cold-start prior.** If `problem_b` has no inference states, `sr8-mcp` seeds them from `train_inference_agent()` using `INFERENCE_PRIOR_REWARD_MODEL`, a hand-designed reward model, not data. With seed 99 it first visits every state-action pair 5 times (180 single-step updates, so no pair keeps its untried initial value of 0.0), then runs 1000 epsilon-greedy single-step episodes. The reward model's categories are evidence × project: `strong_yes` favours `increase_confidence` (the proposal agrees with a close neighbour's project), `strong_no` favours `decrease_confidence` (a close neighbour exists but the proposed project holds none of the ADR's requirements, so the proposal contradicts the evidence), and `weak_yes` / `weak_no` favour `keep_confidence`. In the resulting prior every state's greedy action is its category's best action under the reward model. Print its Q-table with `python3 thesis-extension/reinforcemnt-learning.py --inference-table`.
- **Version 2 files** (one shared agent) are migrated automatically on the first save: `inference_*` states go to `problem_b` (with the new single-step config), everything else plus the old config and `episode_rewards` to `problem_a`. To migrate explicitly: `python3 thesis-extension/reinforcemnt-learning.py --migrate thesis-extension/.rl-model.json`.

The model file is loaded automatically when `sr8-mcp` starts. Both processes find the model file with the same rule, in `rl_model_path.py`: `RL_MODEL_PATH` unset or empty means `thesis-extension/.rl-model.json`, a relative value is resolved against the `thesis-extension` folder (not the current working directory), and an absolute value is used as given. `ollama-mcp` only ever writes `problem_a` and `sr8-mcp` only `problem_b`, both through `locked_update`. `sr8-mcp`, `ollama-mcp` and `scripts/review-links.py` each hold their own in-memory copy, so every save goes through `locked_update`: it locks `.rl-model.json.lock`, reloads the latest file, applies only that process's change and writes atomically, so no process overwrites another's learning.

Run the built-in self-test:

```bash
python3 thesis-extension/reinforcemnt-learning.py --self-test
```

## Notes

- `query_knowledge_graph` accepts only MATCH-starting Cypher; write clauses are blocked.
- Document reads are restricted to paths under `DOC_ROOTS`.
- Neo4j writes in the MCP tools use MERGE, except a resubmitted suggestion (`write_inferred_project_link(..., resubmit=True)`), which CREATEs a second `suggestedProject` edge.
- Set `STRICT_CONTEXT_ONLY=false` in `.env` to allow non-contextual model responses.
- Set `OCR_ENABLED=false` to disable the tesseract OCR fallback for scanned PDFs.

## Logs

Both programs append one JSON object per line to `thesis-extension/logs/` (created on first write, ignored by git). Logging never interrupts the chat or a tool call.

**`logs/turns.jsonl`** (`ollama-mcp`, one line per user turn, however the turn ends):

| Field | Meaning |
|---|---|
| `timestamp`, `session_id`, `model` | UTC start time; one id per `ollama-mcp` run; Ollama model |
| `question` | what the user typed |
| `route` | the matching `ROUTES` name (`review_confirm`, `review_reject`, `review_usage`, `cypher_query`, `suggest_link`, `rl_policy`, `unassigned_requirements`, `list_all_projects`, `inferred_links`, `count_requirements`, `reference`, `manufacturing_redirect`, `design_guidance`) or `rl_prefetch` |
| `rl_state`, `rl_action` | Problem A state and chosen strategy (`rl_prefetch` only) |
| `forced_strategy` | the `RETRIEVAL_STRATEGY` used for an `adr_lookup` turn, or `null` when the agent chose (`rl_prefetch` only) |
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
- Both have `expected_requirement_ids`. These are IDs from `thesis-extension/ADR-mapping.json`, restricted to requirements whose mapping ID equals the graph ID that `extract-ADR.py` assigns; for ADR-23, ADR-25 and ADR-31 the two numberings differ for many rows. Every question is worded so it takes the RL route (no "how many … requirement", "reference" or design/manufacturing keywords), which `tests/test_experiments.py` checks.
- `run-baseline.py` runs each question through `ollama-mcp`'s own chat loop in a fresh session:
  - `--train --passes N`: `train_questions.csv`, N times, strategy `rl`, learning on.
  - `--evaluate`: `questions.csv` for `graph_first`, `documents_first`, `hybrid` and `rl`, learning off.
  - `--limit K` runs only the first K questions (a quick check).

  Results go to `experiments/results/`: `<mode>-<timestamp>.csv` (one row per question and strategy: route, chosen and forced strategy, `model_cited`, `fallback_used`, `evidence_appended`, expected IDs found as count and fraction, tool calls, LLM calls, latency, `rl_updated`), `-summary.csv` (per-strategy means and Problem A's update counts), `-turns.jsonl` and `-transcript.txt`.

Problem A has a single learnable state (`adr_lookup`), so training learns one overall best strategy rather than a per-question choice.

## FMEA requirements and ADR requirements

The FMEA workbook (`thesis-extraction/Brake_System_Failure_Mode_Data.xlsx`) creates its own `Requirement` nodes (named by `hasName`, from the "Requirement Mapping" sheet), linked to components by `satisfiesRequirement`. They are deliberately **not** linked to the ADR `ExtractedEssentialRequirement` nodes, and nothing links them automatically.

`scripts/propose-fmea-links.py` (offline; no Neo4j) proposes candidates for a person to review: for each FMEA requirement it ranks the ADR requirements by name overlap (`similarity.name_overlap`, the same function as the `name_overlap` component of `get_similar_assigned_requirements`) and writes the top 3 to a CSV with empty `decision`, `reviewer` and `notes` columns (default `thesis-extension/logs/fmea-link-candidates-<date>.csv`). Nothing enters the graph from this file. On the current data it proposes 48 candidates for 17 FMEA requirements; name overlap alone gives weak matches (no stemming: "braking" does not match "brake"), so every candidate needs review.

