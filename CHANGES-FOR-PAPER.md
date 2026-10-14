# Changes on `paper-fixes` and what the paper should say

Every commit made on `paper-fixes` for the journal paper, oldest first. For each commit: what changed, the files, the old and new value of every number it affects, and the wording the paper should now use. Numbers were measured offline (dry runs, the offline test suite, `--inference-table`). Where an "old" value comes from running the earlier code, the commit it was run from is named.

`git log main..paper-fixes` also lists 12 earlier commits (35a043e … 3dbcb50: "file name update", "Hypertuned qlearning agent", "Added brake failure testing with dry run working", and others). They were on the branch's base before this work began and are not described here.

## Summary of numbers

| Quantity | Old | New | Commit |
|---|---|---|---|
| MCP tools the LLM can call | 40 (41 after 083f118) | 39 | 23f4c8c (→ 38), 397e182 (→ 39) |
| Ontology classes / object properties / data properties (OWL) | 66 / 49 / 50 | 72 / 59 / 70 | 3616a58 |
| Schema CSV rows (labels / relationships / node properties) | 66 / 49 / 49 (CSV and OWL disagreed) | 72 / 59 / 70, generated from the OWL | e08afc4 … 3616a58 |
| Edge properties (`relationship-properties.csv`) | none | 32 | 3616a58 |
| ADR extraction: clauses | "243" (doc); 255 printed by the code (rows) | 177 distinct Clause nodes (255 rows) | 3cd92a1 |
| ADR extraction: requirements | "205" (doc); 217 printed by the code | 217 nodes (211 applicable, 6 not applicable) | 3cd92a1 |
| ADR extraction: project links | "178" (doc); 190 printed by the code (rows with a project or department) | 172 `assignedToProject` edges, 24 distinct projects, 45 unassigned requirements | 3cd92a1 |
| Rows with placeholder project ID (N/A etc.) | counted as projects | 2, no Project node or edge | 3cd92a1 |
| Problem B "strong evidence" among the 45 unassigned requirements | 45 / 45 | 31 / 45 (69%) | 461b2b6 |
| Problem B prior: pairs never tried (Q = 0.0) | 4 of 36 | 0 of 36 | 8329217, 90391b5 |
| Problem B discount factor | 0.9 | 0.0 | 8329217 |
| Problem A `adr_lookup` Q (graph_first / documents_first / hybrid) | −0.2753 / −0.4040 / −0.2558 | 0.0 / 0.0 / 0.0 | 49577d0 |
| Problem A epsilon / episode rewards | 0.02 / 800 | 0.15 / 0 | 49577d0 |
| Fixed routes in `ollama-mcp` (besides exit and the RL path) | 4 ad-hoc branches (review, count, reference, design/manufacturing guidance) | 14 `ROUTES` rows (including `exit`), then the RL path | 9806579 |
| Offline tests | 0 | 214 | all |
| Default `OLLAMA_MODEL` / `REQUIRE_EXPLICIT_CITATIONS` | `llama3.1:8b` / `true` | `qwen2.5:14b-instruct` / `false` | final commit |

---

## e08afc4 — Add FMEA classes and relationships to schema CSVs

- **Change:** commits CSV rows that were already in the working tree for the FMEA classes (`FailureMode`, `Cause`, `Effect`, `ControlAction`) and their relationships.
- **Files:** `thesis-ontology/csv/node-labels.csv`, `relationships.csv`.
- **Numbers:** node labels 66 → 70; relationships 49 → 54. The OWL file was unchanged (66 classes, 49 object properties), so CSV and OWL disagreed until 3616a58.
- **Paper:** no claim on its own; see 3616a58 for the final counts.

## 083f118 — fix(inference): keep reviewed suggestions and record reviewer and feedback on promote/reject

- **Change:**
  - `promote_inferred_link` no longer deletes the `suggestedProject` edge. It requires a reviewer, records a FeedbackEvent before the edge changes, and copies the inference provenance onto the new `assignedToProject` edge (`source='inferred'`).
  - Adds `reject_inferred_link`.
  - `get_inferred_links` and `get_unassigned_requirements` hide reviewed suggestions unless `include_reviewed=True`.
  - `extract-ADR.py` marks its edges `source='extracted'`.
- **Files:** `thesis-extension/sr8-mcp`, `README.md`, `test_recommender.py`; `thesis-extraction/Scripts/extract-ADR.py`, `Documentation/extraction.md`.
- **Numbers:** MCP tools 40 → 41.
- **Paper:** a confirmed inference is kept as a reviewed `suggestedProject` edge (`status='promoted'`) next to a new `assignedToProject` edge with `source='inferred'`. Extracted, inferred and confirmed links can therefore be told apart by query.

## 6244783 — fix(inference): protect reviewed suggestions and prevent double feedback

- **Change:** `write_inferred_project_link` handles each existing state of the pair:
  - already assigned to that project: refuses (`already_assigned`);
  - only reviewed suggestions exist: returns the earlier decision (`previously_reviewed`), or CREATEs a second edge with `resubmissionOf` when `resubmit=True`;
  - a pending suggestion exists: revises it in place, keeping `previousConfidence`, `previousReasoning` and `revisionCount`;
  - assigned to a different project: still writes, with a warning.

  Feedback acts only on the pending suggestion. Adds `scripts/export-confirmed-links.py` and `scripts/backfill-link-source.cypher` (not run).
- **Files:** `sr8-mcp`, `README.md`, `testing_rl_steps.md`, `scripts/*`, `tests/test_inference_review.py`.
- **Numbers:** none.
- **Paper:** a human decision is never overwritten or counted twice. Every decision yields exactly one FeedbackEvent.

## 23f4c8c — fix(review): restrict link review and feedback to people

- **Change:** `promote_inferred_link`, `reject_inferred_link` and `record_feedback` are no longer MCP tools. Adds:
  - `modify_inferred_link` (`source='inferred-modified'`);
  - `scripts/review-links.py` (people-only CLI, `--reviewer` required);
  - typed `confirm link` / `reject link` commands in `ollama-mcp`, which run only from user input.
- **Files:** `sr8-mcp`, `ollama-mcp`, `scripts/review-links.py`, `scripts/export-confirmed-links.py`, `README.md`, `testing_rl_steps.md`, `test_recommender.py`, `tests/test_inference_review.py`, `tests/test_review_access.py`.
- **Numbers:** MCP tools 41 → 38.
- **Paper:** "The LLM cannot confirm, modify or reject its own suggestions. Review is performed by a named person, through a CLI or typed commands, and the rewards are confirm +1.0, modify +0.5, reject −1.0 (−2.0 if the stored confidence exceeds 0.8)."

## bd4ac13 — fix(rl): register RL module so sr8-mcp's agent loads

- **Change:** `sr8-mcp` now registers `reinforcemnt-learning.py` in `sys.modules` before executing it. From 17b90b9 until this commit, loading raised an `AttributeError` that was swallowed, so the sr8-mcp RL agent never loaded. During that time, confidence was stored unchanged and feedback updated nothing.
- **Files:** `sr8-mcp`.
- **Numbers:** none; this affects any result attributed to Problem B before this commit.
- **Paper:** do not report Problem B learning from runs made before this fix.

## 0b61181 — fix(rl): apply saves to the latest model under lock to stop cross-process overwrites

- **Change:** adds `locked_update`. It locks `<file>.lock`, reloads the latest model, applies only this process's change and writes atomically. `sr8-mcp` and `ollama-mcp` save only through it.
- **Files:** `reinforcemnt-learning.py`, `sr8-mcp`, `ollama-mcp`, `README.md`, `testing_rl_steps.md`, `tests/test_rl_persistence.py`.
- **Numbers:** none.
- **Paper:** two processes share one model file, and neither overwrites the other's learning.

## 08a171a — fix(schema): validate written relationships against the schema layer

- **Change:** `_validate_against_schema` checks each relationship that `write_inferred_project_link` and `write_change_impact_report` create:
  - the relationship type must exist as a `SchemaRelationship` node;
  - its source and target labels must match, including `SUBCLASS_OF` ancestors, `A|B` and `All`;
  - the check fails closed.

  Declares `suggestedProject`, `affectsRequirement` and `affectsProject`.
- **Files:** `sr8-mcp`, `README.md`, `testing_rl_steps.md`, `tests/test_inference_review.py`, `thesis-ontology/csv/relationships.csv`.
- **Numbers:** relationships 54 → 57 (CSV).
- **Paper:** "LLM-initiated writes are validated against the ontology's schema layer before they are written. If the schema is missing or the relationship is undeclared, nothing is written."

## 8329217 — fix(rl): credit the chosen action, make inference learning single-step and separate the two problems

- **Change:**
  - The suggestion stores `rlAction` and `baseConfidence`, and feedback updates Q(`inferenceState`, `rlAction`). Previously `rl_map` credited a fixed action per decision (confirmed → increase, and so on), whatever the agent had chosen.
  - Problem B has its own config with discount 0.0.
  - The `yes/no` feature means "the candidate project already holds a same-ADR requirement".
  - `.rl-model.json` schema version 3 stores `problem_a` and `problem_b` separately, with a migration from version 2.
  - The prior's reward model is named as a designer-specified prior; `--inference-table` prints it.
- **Files:** `reinforcemnt-learning.py`, `sr8-mcp`, `ollama-mcp`, `README.md`, `testing_rl_steps.md`, `tests/test_inference_review.py`, `tests/test_rl_persistence.py`.
- **Numbers:** Problem B discount 0.9 → 0.0. Prior Q-values, regenerated from the 08a171a code, were about 0 to 8, with 4 of 36 pairs never tried (Q = 0.0). The final table is under 461b2b6.
- **Paper:** "Problem B is a one-step (contextual-bandit) decision, Q ← Q + α(r − Q). The reward credits the action actually taken. The prior is a hand-designed reward model, not data."

## 49577d0 — fix(rl): remove the synthetic retrieval prior and reward the model's own citations

- **Change:**
  - Removes the toy retrieval environment (`adr_question`); Problem A learns only from live turns.
  - `general_lookup` (one action) is no longer updated.
  - The reward is computed from the model's raw answer.
  - Ignores `.rl-model.json.lock`.
- **Files:** `ollama-mcp`, `reinforcemnt-learning.py`, `.rl-model.json`, `.gitignore`, `README.md`, `tests/test_retrieval_reward.py`.
- **Numbers:**

  | `.rl-model.json` | Old (backup `.rl-model.backup-2026-10-12.json`) | New |
  |---|---|---|
  | `adr_question` | graph_first 6.5103, documents_first 6.7397, hybrid 7.1140 | removed |
  | `adr_lookup` | graph_first −0.2753, documents_first −0.4040, hybrid −0.2558 (greedy hybrid) | 0.0 / 0.0 / 0.0 |
  | `general_lookup` | documents_first −0.6211 | unchanged, no longer updated |
  | epsilon | 0.02 | 0.15 |
  | `episode_rewards` | 800 | 0 |

  Reward, old: −0.8 for the fallback; otherwise +0.2 if a tool ran, plus +0.8 if the answer cited a file **or the tools returned any evidence**, else −0.2. Because the client appends evidence itself, the citation term was almost always earned.

  Reward, new: the same values, but the +0.8 requires the model's own answer to cite (`path | row/line N`). It is computed before evidence is appended or the fallback is substituted.
- **Paper:** report Problem A results only from runs after this commit. Earlier Q-values measured client-appended evidence, not the model's citations.

## 165420e — fix(logging): log turns and inference events, and resolve RL_MODEL_PATH from the extension folder

- **Change:** adds `logs/turns.jsonl` (one line per user turn) and `logs/inference.jsonl` (each suggestion and review event, including refusals). A relative `RL_MODEL_PATH` resolves against `thesis-extension/`. Ignores `logs/`.
- **Files:** `ollama-mcp`, `sr8-mcp`, `.gitignore`, `README.md`, `tests/test_inference_review.py`, `tests/test_turn_log_and_writers.py`.
- **Numbers:** none.
- **Paper:** per-turn and per-decision logs are the source for the experiment tables.

## b2c7719 — fix(rl): make sr8-mcp honour RL_MODEL_PATH

- **Change:** `rl_model_path.py` holds the single path rule: unset or empty means `thesis-extension/.rl-model.json`, a relative path resolves against `thesis-extension/`, and an absolute path is used as given. Both processes use it.
- **Files:** `rl_model_path.py`, `sr8-mcp`, `ollama-mcp`, `README.md`, `tests/test_turn_log_and_writers.py`.
- **Numbers:** none.

## 90391b5 — fix(rl): ensure the Problem B prior visits every state-action pair

- **Change:** adds a coverage phase before the 1000 epsilon-greedy episodes (seed 99): 5 samples for each of the 12 × 3 pairs, 180 updates in all.
- **Files:** `reinforcemnt-learning.py`, `README.md`, `testing_rl_steps.md`, `tests/test_rl_persistence.py`.
- **Numbers:** pairs never tried: some (for example, `inference_strong_yes_mid` was greedy on `keep_confidence`) → 0. Every greedy action now matches the reward model's best action.
- **Paper:** "The prior is trained with a coverage phase (5 visits per state-action pair), then 1000 single-step episodes, seed 99."

## 6821e32 — feat(experiments): add strategy switches and a train/evaluate runner for retrieval strategies

- **Change:**
  - Adds `RETRIEVAL_STRATEGY` (`rl|graph_first|documents_first|hybrid`); forced turns never train.
  - Adds `RL_LEARNING` (`false`: greedy policy, no updates or saves).
  - Adds `experiments/questions.csv` and `train_questions.csv`, and `run-baseline.py` (`--train --passes N`, `--evaluate`, `--limit K`).
- **Files:** `ollama-mcp`, `.env.example`, `README.md`, `experiments/*`, `tests/test_experiments.py`, `tests/test_retrieval_reward.py`, `tests/test_turn_log_and_writers.py`.
- **Numbers:** 25 evaluation questions over all 8 ADRs; 30 training questions.
- **Paper:** describe the evaluation as 4 strategies (graph_first, documents_first, hybrid, rl) × 25 questions with learning off. Problem A has one learnable state (`adr_lookup`), so it learns one overall strategy, not a per-question choice.

## 9806579 — feat(routing): add an explicit deterministic routing table checked before the RL step

- **Change:** one `ROUTES` list (name, matcher, handler, `uses_llm`), matched first-wins before the RL step. Routes without the model call one tool and log `llm_calls = 0`. Adds `--print-routes`.
- **Files:** `ollama-mcp`, `README.md`, `testing_rl_steps.md`, `tests/test_routes.py`, `tests/test_experiments.py`, `tests/test_review_access.py`, `tests/test_turn_log_and_writers.py`.
- **Numbers:**
  - Old: exit, plus 4 ad-hoc branches (review commands, count questions, reference questions, design/manufacturing guidance).
  - New: 14 rows: `exit`, `review_confirm`, `review_reject`, `review_usage`, `cypher_query`, `suggest_link`, `rl_policy`, `unassigned_requirements`, `list_all_projects`, `inferred_links`, `count_requirements`, `reference`, `manufacturing_redirect`, `design_guidance`.
  - Then `rl_prefetch` for everything else. 2 of the 14 call the model (`manufacturing_redirect`, `design_guidance`).
- **Paper:** "Deterministic routes are checked before the RL step; only unmatched questions reach the learned retrieval policy." Quote the table from `python3 thesis-extension/ollama-mcp --print-routes`.

## 2d6b1db — fix(assemblies): use the ontology's belongsToAssembly/hasID and create assemblies in the extraction pipeline

- **Change:** the `sr8-mcp` assembly tools queried `partOfAssembly`, `assemblyID` and `assemblyName`, while the Cypher script created `belongsToAssembly` and `hasID`, so the tools found nothing. They now use `belongsToAssembly`, `Assembly.hasID` and `hasName`. Adds `run-extraction.py --only assemblies` from `thesis-extraction/data/assemblies.csv`. Projects that don't exist are skipped, never stubbed.
- **Files:** `sr8-mcp`, `README.md`, `tests/test_assemblies.py`, `thesis-extraction/Scripts/extract_assemblies.py`, `run-extraction.py`, `data/assemblies.csv`, `Documentation/extraction.md`, `Documentation/one-command.cypher`, `thesis-ontology/csv/relationships.csv`.
- **Numbers:**
  - Relationships 57 → 58 (CSV).
  - 3 assemblies:
    - ASM-FRONT-AXLE: 3 projects, 45 requirements;
    - ASM-STEERING: 3 projects, 38 requirements;
    - ASM-REAR-AXLE: 3 projects, 35 requirements.
  - 2 listed projects are missing and skipped (SRP8-088, SRP8-089).
- **Paper:** use these assembly counts. ADR-43 reaches all 3 assemblies.

## 3cd92a1 — fix(extraction): report distinct counts, treat placeholder project IDs as missing, and flag ambiguous applicability

- **Change:**
  - Distinct node and edge counts, with the old row counters kept and labelled.
  - `N/A`, `NA`, `-`, `TBC` and empty project IDs mean no project.
  - Applicability has a basis (`column`, `name_keyword`, `default`) and `needsReview`.
  - One `plan_rows()` feeds the writes, the counts and the assembly extractor.
- **Files:** `extract-ADR.py`, `extract_assemblies.py`, `extraction.md`, `tests/test_extract_adr.py`, `tests/test_assemblies.py`, `tests/test_experiments.py`.
- **Numbers (8 ADR files):**

  | | Old doc | Old code (run from 3cd92a1^) | New |
  |---|---|---|---|
  | Clauses | 243 | 255 (rows) | 177 distinct nodes (255 rows) |
  | Requirements | 205 | 217 | 217 (211 applicable, 6 not applicable) |
  | Project links | 178 | 190 (rows with a project or department) | 172 `assignedToProject` edges |
  | Distinct projects | — | — | 24 |
  | Unassigned requirements | — | — | 45 |
  | Placeholder project IDs | — | counted | 2 (REQ-95-003, REQ-95-010), no edge |
  | Rows flagged for review | — | — | 0 |
  | Rows without a requirement node | — | — | 38 (31 without a name, 7 with a name but no text) |

- **Paper:** "255 checklist rows yield 217 requirements, 177 clauses and 172 requirement-to-project links across 24 projects; 45 requirements are unassigned."

## a4da74d — fix(routing): stop assembly questions triggering the manufacturing redirect

- **Change:** removes `assembly` and `build` from the redirect keywords, and defines the keyword lists once.
- **Files:** `ollama-mcp`, `tests/test_routes.py`.
- **Numbers:** manufacturing keywords went from 6 (`manufactur`, `fabricat`, `assembly`, `procure`, `quality control`, `build`) to 4 (`manufactur`, `fabricat`, `procure`, `quality control`). Design keywords: `design`, `prototype`, `conceptual`, `preliminary`, `detailed`.
- **Paper:** questions naming an assembly reach the model, which can call `get_assembly`.

## 5c22c1e — fix(inference): score similar requirements by clause adjacency and name overlap in one shared helper

- **Change:** `get_similar_assigned_requirements` previously returned the first 5 same-ADR assigned requirements ordered by ID. Its docstring claimed clause and name similarity, but nothing was scored. It now scores every candidate as clause adjacency (0 or 1) plus the Jaccard overlap of requirement-name content words (0 to 1). It shows the top 5 with their components, plus the uncapped `candidate_count`. `extract-ADR.py` stores `clauseNumber`.
- **Files:** `sr8-mcp`, `extract-ADR.py`, `extraction.md`, `thesis-ontology/csv/node-properties.csv`, `tests/test_extract_adr.py`, `tests/test_inference_review.py`, `tests/test_similarity.py`.
- **Numbers:** node properties 49 → 50 (CSV).
- **Paper:** describe the similarity score exactly as above.

## 461b2b6 — fix(rl): base Problem B evidence on neighbour similarity, not ADR size

- **Change:** evidence is `strong` when the best same-ADR assigned neighbour scores at least `EVIDENCE_SCORE_THRESHOLD` = 0.5. The old rule was at least 3 same-ADR assigned requirements, counted from the 5-row capped query. The reward model is keyed by evidence × project (`strong_yes`, `strong_no`, `weak_yes`, `weak_no`). `get_requirement_chain` starts from the requirement's own clause.
- **Files:** `sr8-mcp`, `reinforcemnt-learning.py`, `README.md`, `testing_rl_steps.md`, `thesis-ontology/csv/node-properties.csv`, `tests/*`.
- **Numbers:**
  - Strong evidence among the 45 unassigned requirements: 45 / 45 → 31 / 45 (69%).
  - Node properties 50 → 52 (CSV).
  - Problem B cold-start prior (`python3 thesis-extension/reinforcemnt-learning.py --inference-table`, final epsilon 0.0200), Q(increase / keep / decrease):

  | State | Old (08a171a code, γ = 0.9) | New (γ = 0.0) | Greedy old → new |
  |---|---|---|---|
  | strong_yes_high | 5.4658 / 5.6265 / 3.9290 | 0.7540 / 0.4858 / −0.2259 | keep → increase |
  | strong_yes_mid | 0.0000 / 6.0629 / 1.0561 | 0.8215 / 0.7204 / −0.1485 | keep → increase |
  | strong_yes_low | 7.9998 / 7.1459 / 6.0220 | 0.7874 / 0.7285 / −0.1264 | increase → increase |
  | strong_no_high | 8.0380 / 6.6511 / 5.9872 | −0.4750 / 0.1876 / 0.5981 | increase → decrease |
  | strong_no_mid | 7.8566 / 6.7714 / 0.0000 | −0.5080 / 0.1627 / 0.7202 | increase → decrease |
  | strong_no_low | 7.8128 / 5.7489 / 6.6687 | −0.3632 / 0.2084 / 0.6490 | increase → decrease |
  | weak_yes_high | 3.1556 / 4.9100 / 3.9657 | 0.0483 / 0.4931 / −0.1020 | keep → keep |
  | weak_yes_mid | 1.1884 / 0.0000 / 0.8900 | 0.0927 / 0.4748 / −0.1534 | increase → keep |
  | weak_yes_low | 3.4213 / 4.7179 / 4.0635 | 0.0490 / 0.4817 / −0.1391 | keep → keep |
  | weak_no_high | 1.1869 / 2.8379 / 2.6742 | −0.2527 / 0.3755 / 0.2808 | keep → keep |
  | weak_no_mid | 4.4556 / 5.0683 / 3.0828 | −0.3854 / 0.3363 / 0.1704 | keep → keep |
  | weak_no_low | 3.3221 / 0.0000 / 6.0271 | −0.2795 / 0.3734 / 0.2670 | decrease → keep |

  The old prior was never used live: until bd4ac13 the sr8-mcp agent did not load. The committed `.rl-model.json` has an empty `problem_b`, so `sr8-mcp` seeds the new prior on first load.
- **Paper:** use the new table and state definitions. "Strong evidence means a close neighbour exists (score ≥ 0.5), true for 31 of the 45 unassigned requirements."

## 397e182 — feat(fmea): add get_unmitigated_failure_modes with workbook provenance, and an offline FMEA-to-ADR link proposal script

- **Change:**
  - New MCP tool `get_unmitigated_failure_modes`.
  - The FMEA extractor no longer creates Cause, Effect or ControlAction nodes for empty or placeholder cells. Before, an empty control action created a blank `CA-` node, which hid an unmitigated failure mode.
  - The extractor stores workbook provenance.
  - `scripts/propose-fmea-links.py` writes FMEA-to-ADR candidates to a CSV for human review.
  - Similarity moved to `similarity.py`.
- **Files:** `sr8-mcp`, `similarity.py`, `scripts/propose-fmea-links.py`, `extract_failure_modes.py`, `README.md`, `extraction.md`, `test_recommender.py`, `tests/test_fmea.py`, `tests/test_review_access.py`.
- **Numbers:**
  - MCP tools 38 → 39.
  - FMEA dry run: 15 components, 22 failure-mode rows (20 distinct), 0 without a control action, 23 requirement links. The same counts came from the old extractor, because this workbook has no empty cells.
  - The proposal script gives 48 candidates for 17 FMEA requirements.
- **Paper:** FMEA requirements are not linked to ADR requirements automatically. On the current workbook every failure mode has a control action, so the tool returns none.

## 3616a58 — feat(ontology): make ontology.owl the single source of truth and generate the schema CSVs from it

- **Change:**
  - Adds to the OWL everything the code writes.
  - Component becomes a subclass of PartsManagement (it was Assembly); `hasSource` is removed.
  - Adds symmetric/transitive markings for `collaboratesWith` and `partOfBOM`.
  - Adds `valueConstraint` and `edgeProperty` annotations.
  - `owl-to-csv.py` generates the 4 CSVs; `validate.py` fails on drift; `verify.py` reads its counts from the CSVs; `import.py` creates instance uniqueness constraints.
  - FeedbackEvent uses `hasTimestamp`.
  - Deletes the broken `csv/CSV` symlink.
- **Files:** `thesis-ontology/ontology.owl`, `csv/*` (4 files), `scripts/owl-to-csv.py`, `validate.py`, `verify.py`, `import.py`, `Documentation/ontology.md`; `thesis-extension/sr8-mcp`, `README.md`, `testing_rl_steps.md`, `tests/test_ontology.py`.
- **Numbers:**

  | | OWL before | CSV before (461b2b6) | After (OWL = CSV) |
  |---|---|---|---|
  | Classes / node labels | 66 | 70 | 72 |
  | Object properties / relationships | 49 | 58 | 59 |
  | Data properties / node properties | 50 | 52 | 70 |
  | Edge properties | — | — | 32 |

  Characteristics: 5 (symmetric `collaboratesWith`, `interface`; transitive `hasComponent`, `dependsOn`, `partOfBOM`). There are 5 `valueConstraint` annotations, and rdflib parses the OWL file to 1,004 triples.
- **Paper:** "The ontology defines 72 classes, 59 object properties and 70 data properties, with 32 relationship properties as annotations. The Neo4j schema layer is generated from it." Symmetry, transitivity and disjointness are declared but not enforced in Neo4j.

## d43e475 — fix(validate): make validate.py's existing checks real

- **Change:** XML syntax, namespaces, class labels and ontology metadata are now tested; before, they were printed as passed without being checked. Any failure exits 1. Adds `--owl` and `--csv-dir`.
- **Files:** `thesis-ontology/scripts/validate.py`, `tests/test_validate.py`, `tests/test_ontology.py`.
- **Numbers:** 5 validation checks.
- **Paper:** if the paper mentions validation, list the 5 checks.

## Final commit — fix(config): untrack .env, set paper defaults, resolve redirect paths, add requirements and align docs

- **Change:**
  - `thesis-extension/.env` (which held a real Neo4j password) is untracked and ignored. It remains in the git history, so the password must be changed in Neo4j.
  - `.env.example` holds placeholders and every policy variable with its default.
  - Code defaults now match the paper.
  - The design and manufacturing redirect links are resolved from `DOC_ROOTS`, or else from `thesis-extraction/Design-Documentation/`. They were hard-coded to `/Users/manan/...`.
  - Root `requirements.txt` (Python 3.10+).
  - `.gitignore` covers `.env`, `logs/`, the lock file, `experiments/results/` and `.rl-model.backup-*.json`.
  - Docs aligned with the code; the example password is removed from the docs.
  - `test_recommender.py` also reads `OLLAMA_BASE_URL`.
- **Files:** `.gitignore`, `README.md` (new), `requirements.txt` (new), `CHANGES-FOR-PAPER.md` (new); `thesis-extension/.env` (removed from git), `.env.example`, `ollama-mcp`, `test_recommender.py`, `requirements.txt`, `README.md`, `testing_rl_steps.md`, `tests/test_config_defaults.py` (new); `thesis-extraction/Documentation/extraction.md`; `thesis-ontology/Documentation/ontology.md`, `cypher.md`, `one-command.cypher`.
- **Numbers:**

  | Setting | Old default | New default |
  |---|---|---|
  | `OLLAMA_MODEL` | `llama3.1:8b` | `qwen2.5:14b-instruct` |
  | `STRICT_CONTEXT_ONLY` | `true` | `true` |
  | `REQUIRE_EXPLICIT_CITATIONS` | `true` | `false` |
  | `RL_ENABLED`, `RL_LEARNING`, `RETRIEVAL_STRATEGY`, `RL_MODEL_PATH` | `true`, `true`, `rl`, `.rl-model.json` | unchanged, now listed in `.env.example` |

  Offline tests: 206 → 214.
- **Paper:**
  - "Answers are generated by qwen2.5:14b-instruct via Ollama. The client requires that a tool ran in the turn (`STRICT_CONTEXT_ONLY`) but does not force a file citation, so answers from graph-only tools are kept. The Problem A reward measures the model's own citations."
  - With `REQUIRE_EXPLICIT_CITATIONS=true`, a graph-only answer such as one from `list_all_projects` or `get_rl_policy` was replaced by the fallback. `tests/test_config_defaults.py` checks both settings.
  - Any experiment run with a local `.env` that still sets `llama3.1:8b` or `REQUIRE_EXPLICIT_CITATIONS=true` used those values, because `.env` overrides the code defaults.
