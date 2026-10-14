# Test run-book: SR8 framework after the `paper-fixes` changes

Run this on the test computer **after all fix prompts (0–14, plus 1b) are committed**. Each step gives the command to run, the result to expect, and what to save for the paper.

Every command, path, flag, tool name, route name and chat phrasing below was checked against the code on `paper-fixes`.

- Expected values marked **(code)** are fixed by the code and the committed data: offline dry runs, the generated ontology CSVs, and the seeded RL prior.
- Values marked **(live)** depend on the live database or on the LLM. If a real value differs from any expected value, write it down and send it to me; don't "fix" it.

Save every output into a folder called `evidence/` at the repository root, using the file names given in each step. Take screenshots where it says **📸**. Unless a step says otherwise, run commands from the **repository root**.

---

## 0. Set up the test computer

```bash
git clone <repo-url> && cd <repo-folder>
git checkout paper-fixes
git log -1 --format="%H %s"          # write down the commit hash
python3 --version                    # must be 3.10 or newer (the mcp package requires it)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # requirements.txt is at the repository root
mkdir -p evidence
git log -1 --format="%H %s" > evidence/00-commit.txt
```

> **Expected:** the last commit is `docs: add verified test run-book` (or a later commit on `paper-fixes`), and the install finishes without errors.
> **Save:** `evidence/00-commit.txt`.

Create `thesis-extension/.env` from `.env.example` and fill in the local Neo4j password. **Never commit it.**

```bash
cp thesis-extension/.env.example thesis-extension/.env
# edit NEO4J_PASSWORD (and NEO4J_USER if not 'neo4j'); keep the other values as they are
git status --short thesis-extension/.env     # should print nothing (file is ignored)
export NEO4J_PASSWORD='<your neo4j password>'   # used by the commands below
```

`.env.example` already holds the paper settings: `OLLAMA_MODEL=qwen2.5:14b-instruct`, `STRICT_CONTEXT_ONLY=true`, `REQUIRE_EXPLICIT_CITATIONS=false`, `RL_ENABLED=true`, `RL_LEARNING=true`, `RETRIEVAL_STRATEGY=rl` and `RL_MODEL_PATH=.rl-model.json`.

Start the services:

```bash
# Neo4j 5.x: Homebrew install -> brew services start neo4j
#            Neo4j Desktop    -> start the DBMS in the app
ollama serve &                        # skip if Ollama is already running
ollama pull qwen2.5:14b-instruct
ollama list                           # should list qwen2.5:14b-instruct
python -c "import os; from neo4j import GraphDatabase as G; d=G.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD'])); d.verify_connectivity(); print('neo4j ok')"
```

> **Expected:** `qwen2.5:14b-instruct` appears in `ollama list`, and the Neo4j check prints `neo4j ok`.

---

## 1. Offline checks (no database needed)

```bash
python -m py_compile thesis-extension/sr8-mcp thesis-extension/ollama-mcp thesis-extension/reinforcemnt-learning.py
python thesis-ontology/scripts/validate.py > evidence/01-validate.txt
python thesis-ontology/scripts/owl-to-csv.py --check
(cd thesis-extraction && python Scripts/extract-ADR.py --folder csv --dry-run) > evidence/01-dryrun.txt
python -m unittest discover -s thesis-extension/tests -v > evidence/01-tests.txt 2>&1; tail -n 3 evidence/01-tests.txt
```

> **Expected:**
> - **Compilation:** no output, meaning no errors.
> - **`validate.py` (code):** `Classes: 72`, `Object Properties: 59`, `Data Properties: 70`. All 5 checks show ✓ (XML syntax, Namespaces, Class labels, Ontology metadata, Schema CSVs), followed by `ONTOLOGY READY FOR USE`.
> - **`owl-to-csv.py --check` (code):** `CSVs match ontology.owl`.
> - **Dry-run summary (code)**, the `TOTAL across 8 file(s)` block at the end of `01-dryrun.txt`:
>
> | Count | Expected |
> |---|---|
> | Ledger rows | 255 |
> | Requirement nodes | 217 (211 applicable, 6 not applicable) |
> | Distinct Clause nodes | 177 |
> | assignedToProject edges | 172 |
> | Distinct projects | 24 |
> | Unassigned requirements | 45 |
> | Rows flagged for review (needsReview) | 0 |
> | Rows with a placeholder project ID | 2 |
>
> - **Unit tests (code):** `Ran 214 tests` … `OK`. The suite includes:
>   - schema checks: `SchemaValidationTests`, 15;
>   - suggestion protection and double feedback: `WriteInferredLinkTests` 9 and `FeedbackTests` 6;
>   - credit to the action actually taken, and the overconfidence penalty: `RlCreditTests`, 12;
>   - the two-writer lock test: `TwoRealWritersTests`, 1;
>   - the routing table: `RouteTableTests`, 10, one of which feeds one example phrase to each of the 14 routes.
>
> **Save:** `evidence/01-validate.txt`, `evidence/01-dryrun.txt`, `evidence/01-tests.txt`.

Print the Problem B cold-start prior table:

```bash
python thesis-extension/reinforcemnt-learning.py --inference-table > evidence/01-problemB-prior.txt
```

> **Expected (code):** this is deterministic (coverage phase of 5 × 36 pairs, then 1000 episodes, seed 99, discount 0.0, final epsilon 0.0200). It gives 12 states, all Q-values between −1 and 1:
>
> | State | increase_confidence | keep_confidence | decrease_confidence | Greedy action |
> |---|---|---|---|---|
> | inference_strong_yes_high | 0.7540 | 0.4858 | −0.2259 | increase_confidence |
> | inference_strong_yes_mid | 0.8215 | 0.7204 | −0.1485 | increase_confidence |
> | inference_strong_yes_low | 0.7874 | 0.7285 | −0.1264 | increase_confidence |
> | inference_strong_no_high | −0.4750 | 0.1876 | 0.5981 | decrease_confidence |
> | inference_strong_no_mid | −0.5080 | 0.1627 | 0.7202 | decrease_confidence |
> | inference_strong_no_low | −0.3632 | 0.2084 | 0.6490 | decrease_confidence |
> | inference_weak_yes_high | 0.0483 | 0.4931 | −0.1020 | keep_confidence |
> | inference_weak_yes_mid | 0.0927 | 0.4748 | −0.1534 | keep_confidence |
> | inference_weak_yes_low | 0.0490 | 0.4817 | −0.1391 | keep_confidence |
> | inference_weak_no_high | −0.2527 | 0.3755 | 0.2808 | keep_confidence |
> | inference_weak_no_mid | −0.3854 | 0.3363 | 0.1704 | keep_confidence |
> | inference_weak_no_low | −0.2795 | 0.3734 | 0.2670 | keep_confidence |
>
> **Save:** `evidence/01-problemB-prior.txt`. This becomes the paper's Problem B table.

---

## 2. Load the schema and verify it

In the Neo4j Browser, clear the database first. This deletes everything, so run it only on the test database:

```cypher
MATCH (n) DETACH DELETE n;
```

(`import.py --clear` does the same after asking for confirmation.)

```bash
cd thesis-ontology                    # import.py reads csv/ relative to this folder
python scripts/import.py --password "$NEO4J_PASSWORD" > ../evidence/02-import.txt 2>&1
python scripts/verify.py --password "$NEO4J_PASSWORD" > ../evidence/02-verify.txt 2>&1; echo "verify exit code: $?"
cd ..
```

> **Expected (code):**
> - `import.py` creates the schema-layer constraints and indexes and the 12 instance uniqueness constraints with no errors.
> - `verify.py` passes all five checks (Node Labels, Relationships, Properties, Hierarchy, Validation/Verification Rules) and exits with code 0:
>   - `All 72 Node Labels`, `All 59 Relationship Types` and `All 70 Properties`;
>   - the 11 top-level classes, which it reads from `csv/node-labels.csv`: Cause, ControlAction, Document, Effect, FailureMode, FeedbackEvent, Organization, PartsManagement, Project, ProjectTrackingSystem and Requirement.
>
> **Save:** `evidence/02-import.txt`, `evidence/02-verify.txt`.

Check in the Neo4j Browser:

```cypher
SHOW CONSTRAINTS;
MATCH (n:SchemaLabel) RETURN count(n) AS labels;
MATCH (n:SchemaRelationship) RETURN count(n) AS relationships;
MATCH (n:SchemaProperty) RETURN count(n) AS properties;
MATCH (n:SchemaRelationship {name:'suggestedProject'}) RETURN n;
```

> **Expected (code):**
> - Uniqueness constraints `unique_*` exist for Project (`projectID`) and for these labels on `hasID`: Clause, ExtractedEssentialRequirement, AustralianDesignRule, Component, Assembly, FeedbackEvent, ChangeImpactReport, FailureMode, Cause, Effect and ControlAction. There is also a constraint on `SchemaLabel.name`.
> - labels = 72, relationships = 59, properties = 70.
> - `suggestedProject` exists, with source ExtractedEssentialRequirement and target Project.

---

## 3. Run the full extraction

```bash
cd thesis-extraction                  # run-extraction.py reads csv/, data/ and the workbook relative to this folder
python Scripts/run-extraction.py --password "$NEO4J_PASSWORD" > ../evidence/03-extraction.txt 2>&1
cd ..
```

With no `--only`, this runs every step in order: adrs, projects, parts, failure-modes, assemblies. The **projects** and **parts** steps are **not implemented**: their input files are missing, so they print `Projects file not found` and `Parts file not found` and are skipped. To run one step, add `--only adrs|failure-modes|assemblies`. Run assemblies after adrs.

> **Expected (code):**
> - The ADR summary matches the step 1 table.
> - FMEA: `Components: 15 | Failure mode rows: 22 (20 distinct, 0 without a control action) | Requirement links: 23 | Skipped: 0`.
> - The assembly step warns that **SRP8-088** and **SRP8-089** do not exist and skips them.
>
> **Save:** `evidence/03-extraction.txt`.

Live counts in the Neo4j Browser (run each line separately; the expected values are fixed by the code and the committed data):

```cypher
MATCH (a:AustralianDesignRule) RETURN count(a);                                  // 8
MATCH (r:ExtractedEssentialRequirement) RETURN count(r);                         // 217
MATCH (r:ExtractedEssentialRequirement {isApplicable:false}) RETURN count(r);    // 6
MATCH (c:Clause) RETURN count(c);                                                // 177
MATCH ()-[e:assignedToProject]->() RETURN e.source, count(e);                    // extracted: 172
MATCH (p:Project)<-[:assignedToProject]-() RETURN count(DISTINCT p);             // 24
MATCH (p:Project {projectID:'N/A'}) RETURN count(p);                             // 0
MATCH (r:ExtractedEssentialRequirement) WHERE NOT (r)-[:assignedToProject]->() RETURN count(r);  // 45 unassigned
```

Assembly links:

```cypher
MATCH (a:Assembly)<-[:belongsToAssembly]-(p:Project)<-[:assignedToProject]-(r)
RETURN a.hasName, count(DISTINCT p) AS projects, count(r) AS requirement_links;
```

> **Expected (code):**
>
> | Assembly | Projects | Requirement links |
> |---|---|---|
> | Front Axle Assembly | 3 | 45 |
> | Steering System | 3 | 38 |
> | Rear Axle Assembly | 3 | 35 |

FMEA:

```cypher
MATCH (f:FailureMode) RETURN count(f);                       // 20 (22 rows; repeated failure modes share a node)
MATCH (c:Component) RETURN count(c);                         // 15 (no other implemented extractor creates components)
MATCH ()-[s:satisfiesRequirement]->() RETURN count(s);       // 23
MATCH (r:Requirement) WHERE r.hasName IS NOT NULL AND NOT r:ExtractedEssentialRequirement RETURN count(r);  // 17 FMEA requirements
```

> **Save:** a screenshot or text of every count, as `evidence/03-counts.txt`.

---

## 4. Assembly tools now return results

In the chat client (step 6 explains how to start it), ask:

```
Which requirements are shared across the ASM-FRONT-AXLE, ASM-STEERING and ASM-REAR-AXLE groups?
```

This question matches no fixed route, so it goes to the model through `rl_prefetch`. "Assembly" is no longer a manufacturing-redirect keyword. For a deterministic check, also run the cypher route:

```
cypher query: MATCH (a:Assembly {hasID:'ASM-FRONT-AXLE'})<-[:belongsToAssembly]-(p:Project) RETURN p.projectID
```

> **Expected:**
> - **Cypher form (code):** 3 rows, SRP8-043, SRP8-045 and SRP8-050.
> - **Plain-language form (live):** the model should call the assembly tools (for example `get_cross_assembly_requirements` or `get_assembly`) and get non-empty results. Before the fix these tools returned nothing.
>
> **Save:** `evidence/04-assembly.txt`.

---

## 5. Scenario 6: cross-domain reliability query

In the chat client:

```
cypher query: MATCH (r:Requirement)<-[:satisfiesRequirement]-(c:Component)-[:hasFailureMode]->(f:FailureMode) WHERE NOT (f)-[:mitigatedBy]->(:ControlAction) RETURN r.hasName, c.hasID, f.hasName
```

Or ask in plain language: `Which components have failure modes with no mitigation?` This goes to the model, which should call `get_unmitigated_failure_modes`.

> **Expected:**
> - **Cypher form (code):** `"row_count": 0`. The extraction reports 0 failure modes without a control action, so with the current workbook every failure mode is mitigated.
> - In `logs/turns.jsonl` the cypher turn has `route` `cypher_query` and `llm_calls` 0.
> - **Plain-language form (live):** if the model calls `get_unmitigated_failure_modes`, the tool returns `"unmitigated_count": 0`.
> - **Send me the row count and the first 5 rows, if any.**
>
> **Save:** 📸 `evidence/05-scenario6.png`.

---

## 6. Start the chat client and check the deterministic routes

```bash
cd thesis-extension                   # ollama-mcp starts the server as "python3 sr8-mcp", relative to this folder
python ollama-mcp                     # optional: --model <tag>; python ollama-mcp --print-routes prints the routing table
```

Type each line below in turn. After each one, check the newest line in `thesis-extension/logs/turns.jsonl`:

| Type this | Expected `route` | Expected `llm_calls` |
|---|---|---|
| `show me the rl policy` | rl_policy | 0 |
| `list all projects` | list_all_projects | 0 |
| `show unassigned requirements` | unassigned_requirements | 0 (lists **45** requirements) |
| `show inferred links` | inferred_links | 0 |
| `cypher query: MATCH (a:AustralianDesignRule) RETURN a.hasID` | cypher_query | 0 (returns 8 rows) |
| `cypher query: MATCH (n) DETACH DELETE n` | cypher_query | 0, and the query is **refused**: `"error": "only read-only Cypher is allowed"` |
| `How many requirements does ADR-31 have?` | count_requirements | 0 |
| `Show me the reference for ADR-43` | reference | 0 |
| `confirm link` (with nothing after it) | review_usage | 0 (prints the usage) |
| `Show me the design guidance for brakes` | design_guidance | ≥ 1 |
| `What are the verification methods for ADR-31?` | rl_prefetch (the default route), `rl_state` `adr_lookup` | ≥ 1 |

The routes are fixed by the code and the row values by the data; only the `llm_calls` count of the last two rows depends on the model.

```bash
tail -n 11 logs/turns.jsonl > ../evidence/06-routes.jsonl
```

> **Expected:** each line has the expected `route` and `llm_calls` value, and the DELETE query is refused.
> **Save:** `evidence/06-routes.jsonl` and 📸 one screenshot of the terminal.

---

## 7. Machine-inferred versus human-confirmed links (this is also the worked example)

Use one requirement from `show unassigned requirements` (call it **REQ-A**) and three real projects (**PROJ-1**, **PROJ-2**, **PROJ-3**) from `list all projects`. Type real IDs, without brackets. All the chat lines below are typed into `ollama-mcp`.

> **📸 Take a screenshot at every step marked with 📸.** These screenshots fill the worked-example placeholder in the Results chapter.

Problem B values are read from the model file, not from `show me the rl policy`. Here is why:
- Typed review commands run inside the `ollama-mcp` process.
- `review-links.py` is its own process.
- Both save to `.rl-model.json`, but `get_rl_policy` answers from the `sr8-mcp` server's in-memory copy, which is loaded once per session.

Use this command (from the repository root, in a second terminal) whenever a step says "check Problem B":

```bash
python -c "import json; q=json.load(open('thesis-extension/.rl-model.json'))['problem_b']['q_table']; [print(s, {a: round(v,4) for a,v in q[s].items()}) for s in sorted(q)]"
```

Before 7.1, run it once and save the output as `evidence/07-problemB-before.txt`.

**7.1 The model proposes a link.** 📸

```
Suggest that requirement REQ-A belongs to project PROJ-1 with confidence 0.65 because it shares ADR and wording with requirements already assigned to PROJ-1
```

This takes the `suggest_link` route and calls `write_inferred_project_link` directly.

> **Expected response (code):**
> - `status` `written`, `write_mode` `created`;
> - `inference_state` is one of the 12 `inference_*` states;
> - `original_confidence` is 0.65 and `adjusted_confidence` is 0.55, 0.65 or 0.75;
> - `rl_action` is given;
> - `schema_validation` is `{"ok": true, ...}`.

```cypher
MATCH (r {hasID:'REQ-A'})-[s:suggestedProject]->(p) RETURN s;
```

> **Expected (code):** the edge has `confidence`, `baseConfidence`, `reasoning`, `inferredBy` (`Ollama-MCP`), `inferredAt`, `inferenceState`, `rlAction`, `schemaValidated` and `schemaCheckedAt`, and **no `status`**. 📸

**7.2 A person rejects it.** 📸

```
reject link REQ-A -> PROJ-1 because the requirement belongs to the rear assembly
```

Enter a reviewer name when asked. The client prints `[review] Rejected REQ-A -> PROJ-1 as <name>; reward -1.0.`

```cypher
MATCH (r {hasID:'REQ-A'})-[s:suggestedProject]->(p {projectID:'PROJ-1'}) RETURN s.status, s.reviewedBy, s.rejectionReason;
MATCH (fe:FeedbackEvent) RETURN fe ORDER BY fe.hasTimestamp DESC LIMIT 1;
```

> **Expected (code):**
> - `status` = `rejected`, and the edge is **kept**, not deleted.
> - The FeedbackEvent has `action` `rejected`, `reward` −1.0, your reviewer name, and the `inferenceState` and `rlAction` from 7.1.

**7.3 Protection checks.**

Type the same rejection again:

> **Expected (code):** `[review] Not recorded: ... already reviewed ...`, followed by `Earlier decision: ...`.

Suggest the same pair again (repeat the 7.1 command):

> **Expected (code):** `"status": "previously_reviewed"` with `previous_decision`. The stored suggestion is not overwritten.

**7.4 Overconfidence penalty.** Suggest REQ-A → PROJ-2 with confidence **0.9**, then reject it:

```
Suggest that requirement REQ-A belongs to project PROJ-2 with confidence 0.9 because of very strong evidence from similar requirements in the same ADR
reject link REQ-A -> PROJ-2 because overconfidence test
```

> **Expected (code):**
> - `adjusted_confidence` is 0.8, 0.9 or 1.0.
> - If it is above 0.8, the FeedbackEvent shows `reward` **−2.0** and `overconfidencePenaltyApplied` true, and the client prints `(overconfidence penalty)`.
> - If the agent chose `decrease_confidence` (0.8), the reward is −1.0.

**7.5 A person confirms a link.** 📸

Suggest REQ-A → PROJ-3 (as in 7.1), then confirm it in a separate terminal from the repository root:

```bash
source .venv/bin/activate
python thesis-extension/scripts/review-links.py --reviewer "Ilina Sharma"      # answer c (confirm) for REQ-A -> PROJ-3
```

`review-links.py` lists each pending suggestion and asks for **c**onfirm, **m**odify, **r**eject or **s**kip.

```cypher
MATCH (r {hasID:'REQ-A'})-[a:assignedToProject]->(p {projectID:'PROJ-3'}) RETURN a;
MATCH (r {hasID:'REQ-A'})-[s:suggestedProject]->(p {projectID:'PROJ-3'}) RETURN s.status, s.reviewedBy;
```

> **Expected (code):**
> - The confirmed link has `source` `inferred`, `promotedBy` "Ilina Sharma", `promotedAt`, `promotedFromConfidence`, `inferenceReasoning`, `inferredBy`, `inferredAt` and `inferenceState`.
> - The suggestion still exists, with `status` `promoted` and `reviewedBy` "Ilina Sharma". 📸

**7.6 Audit view of the three kinds of knowledge.** 📸 Run the auditor queries from `thesis-extension/README.md`, section "Reviewing inferred links", under "Auditing the three kinds of project link":

```cypher
MATCH (r:ExtractedEssentialRequirement)-[a:assignedToProject {source: 'extracted'}]->(p:Project)
RETURN count(*) AS extracted;
MATCH (r:ExtractedEssentialRequirement)-[s:suggestedProject]->(p:Project)
WHERE s.status IS NULL
RETURN count(*) AS pending;
MATCH (r:ExtractedEssentialRequirement)-[a:assignedToProject {source: 'inferred'}]->(p:Project)
MATCH (r)-[s:suggestedProject {status: 'promoted'}]->(p)
RETURN count(*) AS human_confirmed;
```

> **Expected (code, given exactly the steps above):** extracted = **172**, pending = **0**, human-confirmed = **1**.

**7.7 Problem B learned from the right action.** Check Problem B (the command above) and compare it with `evidence/07-problemB-before.txt`.

> **Expected (code):**
> - For each state used in 7.2, 7.4 and 7.5, only the Q-value of the **action stored as `rlAction`** has moved: down after each rejection, up after the confirmation. Each update is Q ← Q + 0.2 (r − Q).
> - The other actions are unchanged. A replay batch runs only after 32 updates in one process.
> - The refused decision in 7.3 changes nothing.

**7.8 The LLM cannot confirm its own suggestion.** Ask in plain language:

```
Please confirm the link between REQ-A and PROJ-1
```

This matches no fixed route (only a line starting `confirm link` is a review command), so it goes to the model.

> **Expected:** the model has no review tool, so no `[tool] promote_inferred_link` line appears and no `assignedToProject` edge is created (code). The model should say it cannot do this (live). 📸

> **Save:** all screenshots as `evidence/07-*.png`, `evidence/07-problemB-before.txt`, and the Problem B output after 7.7 as `evidence/07-problemB-after.txt`. Also copy `thesis-extension/logs/inference.jsonl` to `evidence/07-inference.jsonl`.

---

## 8. RL smoke test

A standalone `run-rl-smoke-test.py` (and its `--mutate` mode) is **NOT IMPLEMENTED**. The same behaviour is covered offline by the RL self-test and the unit tests below. Neither changes `.rl-model.json`.

```bash
cp thesis-extension/.rl-model.json evidence/08-rl-model-before.json
python thesis-extension/reinforcemnt-learning.py --self-test > evidence/08-smoke.txt 2>&1
python -m unittest discover -s thesis-extension/tests -p "test_inference_review.py" -k RlCreditTests -v >> evidence/08-smoke.txt 2>&1
python -m unittest discover -s thesis-extension/tests -p "test_rl_persistence.py" -v >> evidence/08-smoke.txt 2>&1
cmp thesis-extension/.rl-model.json evidence/08-rl-model-before.json && echo "model file unchanged"
```

> **Expected (code):**
> - `SELF-TEST PASSED`.
> - `RlCreditTests`: 12 tests OK. They include `test_overconfidence_penalty_kept` (reward −2.0) and `test_rejection_credits_the_stored_action_not_a_mapped_one`, which checks that the Q-value changes for the action actually taken.
> - `test_rl_persistence.py`: all OK.
> - `model file unchanged`.
>
> **Save:** `evidence/08-smoke.txt`.

---

## 9. Problem A: one live question

In the chat client:

```
What are the verification methods for ADR-31 braking requirements?
```

```bash
tail -n 1 thesis-extension/logs/turns.jsonl > evidence/09-problemA-turn.jsonl
python -c "import json; print(json.dumps(json.load(open('thesis-extension/.rl-model.json'))['problem_a'], indent=1)[:1500])" > evidence/09-problemA.txt
```

> **Expected:**
> - **(code)** `route` `rl_prefetch`; `rl_state` `adr_lookup`; `rl_action` one of graph_first / documents_first / hybrid; `forced_strategy` null.
> - **(code)** `reward_components` has `tool_used`, `model_cited`, `evidence_available`, `fallback_used` and `total`. `model_cited` reflects the model's own answer, not appended evidence.
> - **(code)** In `.rl-model.json`, `problem_a` has `adr_lookup` and `general_lookup` only, with no `adr_question`. Only `adr_lookup` changes, and `episode_rewards` grows by 1.
> - **(live)** The answer shows a citation in the form `path/file.csv | row N`.
> - `show me the rl policy` reports Problem B only; read Problem A from `evidence/09-problemA.txt`.
>
> **Save:** 📸 `evidence/09-answer.png`, `evidence/09-problemA-turn.jsonl`, `evidence/09-problemA.txt`.

---

## 10. Baseline experiment (25 questions × 4 strategies)

Problem A starts with no learned values: they were reset in prompt 5. So first train it on the separate training questions, then freeze it and evaluate:

```bash
cd thesis-extension
cp .rl-model.json ../evidence/10-rl-model-before-training.json
python experiments/run-baseline.py --train --passes 3      # 30 training questions x 3, rl strategy, learning on
cp .rl-model.json ../evidence/10-rl-model-after-training.json
python experiments/run-baseline.py --evaluate              # 25 evaluation questions x 4 strategies, learning off
cmp .rl-model.json ../evidence/10-rl-model-after-training.json && echo "model file unchanged by evaluation"
```

Add `--limit 2` to either command for a quick trial run first.

> **Expected after training:**
> - **(code)** The runner prints `Problem A updates: ...` and `Problem A epsilon 0.1500 -> ...`.
> - **(code)** Training uses only `train_questions.csv` (30 questions); the 25 evaluation questions in `questions.csv` are never used for training. No question appears in both files, which `tests/test_experiments.py` checks.
> - **(live)** `problem_a.q_table.adr_lookup` in `evidence/10-rl-model-after-training.json` has non-zero values, and one action has the highest.

> **Expected after evaluation:**
> - **(code)** `experiments/results/baseline-<timestamp>.csv` has **100 rows** (25 questions × 4 strategies: graph_first, documents_first, hybrid, rl).
> - **(code)** `experiments/results/baseline-<timestamp>-summary.csv` has one row per strategy. Its columns are `model_cited_rate`, `fallback_rate`, `evidence_appended_rate`, `expected_ids_found_mean`, `expected_ids_fraction_mean`, `tool_calls_mean`, `llm_calls_mean` and `latency_ms_mean`.
> - **(code)** `model file unchanged by evaluation`, because learning was off.
> - **(live)** I can't predict the values. Whatever they are, they are the paper's baseline result.
>
> **Save:** the two files as `evidence/10-baseline.csv` and `evidence/10-summary.csv`, plus the printed summary as `evidence/10-summary.txt`.

---

## 11. Extra evidence for the paper

**11.1 Change impact (Scenario 3).** In the chat client:

```
What requirements would be affected by a change to SRP8-045, and what needs re-verification?
```

> **Expected:**
> - **(live)** calls to `get_requirement_chain` and `get_reverification_scope`.
> - **(code)** SRP8-045 has 36 assigned requirements in the ADR data.
>
> **Save:** 📸 `evidence/11-change-impact.png`.

**11.2 Ontology competency questions.** Run the 8–10 competency questions the repository chat proposed earlier (prompt 7) as `cypher query: ...` lines, each starting with `MATCH`. Only read-only `MATCH` queries are accepted. These questions are not stored in the repository; copy them from that chat.
> **Save:** each query with its row count, in `evidence/11-competency.txt`.

**11.3 Final policy.**

```
show me the rl policy
```

This shows Problem B as the `sr8-mcp` server loaded it at the start of the session. Restart `ollama-mcp` first so it includes the review updates from step 7.

> **Save:** `evidence/11-policy.txt`, plus a copy of `thesis-extension/.rl-model.json` as `evidence/11-rl-model-final.json`.

---

## 12. What to send back to me

1. `CHANGES-FOR-PAPER.md` and the commit hash.
2. The whole `evidence/` folder (zip it), or at least:
   - the step 1 and 3 counts;
   - the Problem B prior table;
   - the route log;
   - all step 7 screenshots and Problem B files;
   - the baseline summary;
   - the Scenario 6 and change impact outputs.
3. Anything that did not match an **Expected** box.
