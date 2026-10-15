# Worked example run-book: REQ-31-008 (save everything under `evidence-4/`)

## Prompt for the Claude on the test laptop

> I need to re-run the worked example for our journal paper on requirement **REQ-31-008**, using the SR8 repository on this laptop. Follow `WORKED-EXAMPLE-REQ-31-008.md` step by step, in order. Run every Cypher query and shell command yourself where you can. For the chat-client steps (`ollama-mcp`) and the review script, tell me exactly what to type and wait while I do it. Save each output as the file named in that step, under `evidence-4/`, including the full JSON responses. Do not skip, merge or reorder steps.
>
> After each step, compare the output with the **Expected** line. If it doesn't match, stop and tell me what differs rather than carrying on. Never print or save the Neo4j password. Do not change any code, and do not commit or push anything.
>
> At the end, write `evidence-4/00-SUMMARY.md` with a table of each step, its file, and whether the result matched the expected value. Include any difference you found.

---

## Step 0: Reset the graph and Problem B (required)

The last two runs left test links on REQ-10-001 and REQ-31-023, and changed several Problem B values. Every one of them has to go.

**0.1 Delete all test review data** (Neo4j browser or `cypher-shell`):

```cypher
MATCH ()-[s:suggestedProject]->() DELETE s;
MATCH ()-[a:assignedToProject]->() WHERE a.source IN ['inferred','inferred-modified'] DELETE a;
MATCH (fe:FeedbackEvent) DETACH DELETE fe;
```

**0.2 Reset Problem B to the cold-start prior.** In `thesis-extension/.rl-model.json`, replace only the `problem_b` section with the seed-99 cold-start prior, using the repository's own prior-generation code (`train_inference_agent`, seed 99). Leave `problem_a` unchanged. Back up the file first, as `.rl-model.backup-before-evidence-4.json`.

**0.3 Check the reset.** Save as `evidence-4/00-reset-check.txt`:

```cypher
MATCH ()-[a:assignedToProject {source:'extracted'}]->() RETURN count(a) AS extracted;
MATCH ()-[a:assignedToProject]->() WHERE a.source <> 'extracted' RETURN count(a) AS non_extracted;
MATCH ()-[s:suggestedProject]->() RETURN count(s) AS suggestions;
MATCH (fe:FeedbackEvent) RETURN count(fe) AS feedback_events;
MATCH (r:ExtractedEssentialRequirement) WHERE NOT (r)-[:assignedToProject]->() RETURN count(r) AS unassigned;
```

Then, in the chat client, run `show me the rl policy` and add its output to the same file.

> **Expected:**
> - extracted = 172; non_extracted = 0; suggestions = 0; feedback_events = 0; unassigned = 45.
> - Policy report: "Total feedback events: 0", plus these values:
>
> | State | Expected value |
> |---|---|
> | `strong_yes_mid` | increase 0.822, keep 0.720 |
> | `strong_no_high` | decrease 0.598 |
> | `strong_no_mid` | decrease 0.720 |
> | `weak_no_mid` | keep 0.336, decrease 0.170 |
> | `weak_no_high` | keep 0.376 |
>
> If any value differs, the reset did not work. **Stop here.**

---

## Step 1: Inspect REQ-31-008 (read-only)

Save as `evidence-4/01-inspect.txt`:

```cypher
MATCH (r:ExtractedEssentialRequirement {hasID:'REQ-31-008'})
RETURN r.hasID, r.requirementName, r.clauseNumber, r.isApplicable,
       EXISTS((r)-[:assignedToProject]->()) AS already_assigned,
       left(r.requirementDescription, 200) AS text;

MATCH (n:ExtractedEssentialRequirement)-[:assignedToProject]->(p:Project)
WHERE n.hasID STARTS WITH 'REQ-31-' AND n.hasID <> 'REQ-31-008'
RETURN n.hasID, n.clauseNumber, n.requirementName, collect(p.projectID) AS projects
ORDER BY n.hasID LIMIT 25;
```

> **Expected:** `isApplicable` = true and `already_assigned` = **false**. If either is wrong, **stop**: REQ-31-008 isn't suitable.

From the second query, note the projects held by the requirements whose clause numbers are closest to REQ-31-008's. They are most likely SRP8-045 (Front Brakes) and/or SRP8-046 (Rear Brakes).

**Fix these names now and use them in every later step:**

| Name | Project | Role |
|---|---|---|
| **PROJ-WRONG-1** | SRP8-043 (Front Suspension) | first wrong project |
| **PROJ-WRONG-2** | SRP8-048 (Steering Column) | second wrong project |
| **PROJ-MODIFY** | SRP8-046 (Rear Brakes) | target of the modify step |
| **PROJ-GOOD** | SRP8-045 (Front Brakes) | the project to confirm |

If the neighbours point the other way (to 046 rather than 045), swap PROJ-GOOD and PROJ-MODIFY. Write down which projects you used in `01-inspect.txt`.

---

## Step 2: Detect the gap (chat client)

Type each line, and save the output as `evidence-4/02-gap.txt`:

```
show unassigned requirements
show inferred links
```

> **Expected:** REQ-31-008 appears in the unassigned list, and inferred links = 0.

---

## Step 3: A proposal to a wrong project

Type, then save as `evidence-4/03-suggest-wrong1.txt`:

```
Suggest that requirement REQ-31-008 belongs to project SRP8-043 with confidence 0.65 because it shares ADR and wording with requirements already assigned to SRP8-043
```

Then run this query, saving the result as `evidence-4/03-edge.txt`, plus a **cropped** screenshot of just the result table as `03-edge.png`:

```cypher
MATCH (r {hasID:'REQ-31-008'})-[s:suggestedProject]->(p {projectID:'SRP8-043'}) RETURN properties(s);
```

> **Expected:**
> - `status` written; `schema_validation.ok` true; `inference_state` given.
> - The response includes `best_neighbour_id`, `best_neighbour_score` and `project_has_same_adr`.
> - The edge has no `status` property.
> - Note the state and `rl_action`.

---

## Step 4: Rejection

Type (and enter your reviewer name if asked), then save as `evidence-4/04-reject-wrong1.txt`:

```
reject link REQ-31-008 -> SRP8-043 because the requirement concerns the braking system, not the suspension
```

```cypher
MATCH (r {hasID:'REQ-31-008'})-[s:suggestedProject]->(p {projectID:'SRP8-043'})
RETURN s.status, s.reviewedBy, s.rejectionReason;
```

> **Expected:** reward −1.0; `status` = rejected; the edge is kept.

---

## Step 5: Protecting the decision

Type the **same rejection again**, then the **same suggestion again** (the step 3 text). Save both outputs as `evidence-4/05-protection.txt`.

> **Expected:**
> - The rejection is "Not recorded … already reviewed".
> - The suggestion returns `previously_reviewed` with the earlier decision.

---

## Step 6: Overconfidence penalty

Type, then save as `evidence-4/06-suggest-wrong2.txt`:

```
Suggest that requirement REQ-31-008 belongs to project SRP8-048 with confidence 0.95 because of very strong evidence from similar requirements in the same ADR
```

Then type, and save as `evidence-4/06-reject-wrong2.txt`:

```
reject link REQ-31-008 -> SRP8-048 because overconfident proposal to the wrong project
```

> **Expected:**
> - The stored `adjusted_confidence` is 0.85, 0.95 or 1.0. With 0.95, it stays above 0.8 even after a decrease.
> - The rejection gives reward **−2.0** (overconfidence penalty).

---

## Step 7: Resubmission, then modification

**7.1** Resubmit the step 3 proposal (REQ-31-008 → SRP8-043, confidence 0.65, reasoning "Re-evaluated wrong project before human correction.") with `resubmit=True`. Use the same method you used for the resubmission in evidence-3. Save the JSON as `evidence-4/07-resubmission.txt`.

> **Expected:** `write_mode` = resubmitted, and `resubmission_of` is set.

**7.2** In a separate terminal:

```bash
.venv/bin/python thesis-extension/scripts/review-links.py --reviewer "Ilina Sharma"
```

Choose `m`, then enter `SRP8-046`. For the reason, enter: `Corrected from the suspension project to the rear brakes project after human review.` Save the terminal output as `evidence-4/07-modify.txt`.

**7.3** Run this query, saving the result as `evidence-4/07-modify-graph.txt` plus a **cropped** screenshot as `07-modify-graph.png`:

```cypher
MATCH (r {hasID:'REQ-31-008'})-[s:suggestedProject]->(p {projectID:'SRP8-043'}) RETURN properties(s) ORDER BY s.inferredAt;
MATCH (r {hasID:'REQ-31-008'})-[a:assignedToProject]->(p {projectID:'SRP8-046'}) RETURN properties(a);
```

> **Expected:**
> - Reward +0.5.
> - Two SRP8-043 suggestions: one `rejected`, one `modified` with `modifiedTo` SRP8-046.
> - A new `assignedToProject` edge to SRP8-046 with `source` = `inferred-modified`, `promotedBy` and `modificationReason`.
> - It must **not** say "link already existed".

---

## Step 8: The language model proposes, then a person confirms

**8.1** Type this exactly. It matches no route, so the model chooses the tools:

```
Find the requirements most similar to REQ-31-008 and suggest the most appropriate project for it, with your confidence and reasoning.
```

Save the full output as `evidence-4/08-model-proposal.txt`, including every `[tool]` line.

> **Record:**
> - Did the model call `get_similar_assigned_requirements`?
> - Did it call `write_inferred_project_link`?
> - If so, which project and confidence did it propose?

**8.2** Decide what happens next:

- **If the model wrote a suggestion to SRP8-045:** go straight to 8.3.
- **Otherwise:** type the following, and save it as `evidence-4/08-suggest-good.txt`:

  ```
  Suggest that requirement REQ-31-008 belongs to project SRP8-045 with confidence 0.65 because its nearest same-ADR neighbours are assigned to SRP8-045
  ```

  If the model wrote a suggestion to some *other* project, reject that one in 8.3 as well, and record that you did.

**8.3** In a separate terminal:

```bash
.venv/bin/python thesis-extension/scripts/review-links.py --reviewer "Ilina Sharma"
```

Choose `c` for REQ-31-008 → SRP8-045. If there is a second pending suggestion from the model, choose `r` for it. Save the output as `evidence-4/08-confirm.txt`.

**8.4** Run these queries, saving the results as `evidence-4/08-confirm-graph.txt` plus a **cropped** screenshot as `08-confirm-graph.png`:

```cypher
MATCH (r {hasID:'REQ-31-008'})-[a:assignedToProject]->(p {projectID:'SRP8-045'}) RETURN properties(a);
MATCH (r {hasID:'REQ-31-008'})-[s:suggestedProject]->(p {projectID:'SRP8-045'}) RETURN s.status, s.reviewedBy, s.inferredBy;
```

> **Expected:**
> - Reward +1.0.
> - `source` = `inferred`, with `promotedBy`, `promotedFromConfidence` and the copied inference fields.
> - The suggestion is `promoted`.

---

## Step 9: Audit by query

Save as `evidence-4/09-audit.txt`:

```cypher
MATCH ()-[a:assignedToProject {source:'extracted'}]->() RETURN count(a) AS extracted;
MATCH ()-[s:suggestedProject]->() WHERE s.status IS NULL RETURN count(s) AS pending;
MATCH (r)-[a:assignedToProject {source:'inferred'}]->(p) MATCH (r)-[s:suggestedProject {status:'promoted'}]->(p)
RETURN count(*) AS human_confirmed;
MATCH (r)-[a:assignedToProject {source:'inferred-modified'}]->(p)
MATCH (r)-[s:suggestedProject {status:'modified', modifiedTo:p.projectID}]->(sp)
RETURN r.hasID, sp.projectID AS suggested, p.projectID AS assigned, a.promotedBy, a.modificationReason;
MATCH (r {hasID:'REQ-31-008'})-[e]->(p:Project)
RETURN type(e) AS edge, p.projectID, e.source, e.status, e.confidence ORDER BY edge, p.projectID;
MATCH (r:ExtractedEssentialRequirement) WHERE NOT (r)-[:assignedToProject]->() RETURN count(r) AS unassigned;
```

> **Expected:**
> - extracted = 172; pending = 0; human_confirmed = 1.
> - Exactly one modified row, for REQ-31-008 (suggested SRP8-043, assigned SRP8-046).
> - unassigned = 44.

---

## Step 10: Problem B after the reviews

Save the chat output of `show me the rl policy` as `evidence-4/10-policy-after.txt`. Also save the raw `problem_b` Q-table from `.rl-model.json`, with four decimal places, as `evidence-4/10-problemB-after.txt`.

> **Expected:**
> - Total feedback events = **5** (or 6 if a model suggestion was also rejected in step 8).
> - Only the states and actions credited in steps 4, 6, 7 and 8 have changed.
> - Each one moved by Q_new = Q_old + 0.2 × (reward − Q_old).

---

## Step 11: The model cannot review (use the REAL IDs)

Type, then save as `evidence-4/11-llm-confirm.txt`:

```
Please confirm the link between REQ-31-008 and SRP8-043
```

Then run this query and add the result to the same file:

```cypher
MATCH (r {hasID:'REQ-31-008'})-[a:assignedToProject]->(p {projectID:'SRP8-043'}) RETURN count(a) AS assigned_edges;
```

> **Expected:** no review tool is called, and assigned_edges = **0**.

---

## Step 12: Logs

Copy these into `evidence-4/`:

- `thesis-extension/logs/inference.jsonl` → `evidence-4/12-inference.jsonl`
- `thesis-extension/logs/turns.jsonl` → `evidence-4/12-turns.jsonl`

Then write `evidence-4/00-SUMMARY.md`, zip the folder, and send it.