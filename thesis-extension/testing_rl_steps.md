# RL Implementation Testing Guide

Tests for the 7 RL fixes implemented in `sr8-mcp`. Each test uses the Ollama chat interface (`ollama-mcp`) and verifies a specific behaviour in the response. Run tests in order — some tests build on state created by earlier ones.

---

## Prerequisites

```bash
# Terminal 1 — start Neo4j (if not already running)
# Neo4j must be running at bolt://localhost:7687

# Terminal 2 — start Ollama
ollama serve

# Terminal 3 — start the Ollama client (drives sr8-mcp as a subprocess)
python3 thesis-extension/ollama-mcp
```

Confirm both services are up before proceeding.

---

## Test 1 — FIX 6: Pre-trained inference states exist on first load

**What it tests:** When `sr8-mcp` starts with no `.rl-model.json`, `_load_rl_agent()` calls `train_inference_agent()` and merges 1 000 episodes of inference priors into the Q-table before the first tool call.

**Step 1a — Reset the model file (optional but recommended for a clean test):**

```bash
rm -f thesis-extension/.rl-model.json thesis-extension/.rl-model.json.lock
```

Then restart the Ollama client so the server reloads with no saved model.

**Step 1b — Ask Ollama:**

> Show me the current RL policy.

**Expected response:** `get_rl_policy` is called and returns a report that includes all 12 inference states (`inference_strong_yes_high` through `inference_weak_no_low`) with non-zero Q-values. The greedy action for `inference_strong_*` states should be `increase_confidence`; for `inference_weak_no_*` states it should be `decrease_confidence`.

**Pass criteria:**
- 12 inference states listed in the policy table
- No state shows all Q-values as `+0.000`
- `inference_strong_yes_high` greedy action is `increase_confidence`
- `inference_weak_no_low` greedy action is `decrease_confidence`

---

## Test 2 — FIX 7: `get_rl_policy` tool returns a readable report

**What it tests:** The `get_rl_policy` MCP tool exists and returns a structured human-readable string.

**Ask Ollama:**

> What is the current state of the reinforcement learning agent? Show me the Q-values for each inference state.

**Expected response:** The response should include:
- `Exploration rate (epsilon)` value
- `Converged: Yes/No`
- A table with `State`, `Greedy action`, and `Q-values (↑ keep ↓)` columns
- `Total feedback events` count
- `Average reward` value

**Pass criteria:**
- All three Q-value columns (`↑`, `keep`, `↓`) are shown per state
- Epsilon is between 0.02 and 0.15 (decayed from pre-training)
- The tool output is not an error dict

---

## Test 3 — FIX 1: Richer 12-state inference encoding on `write_inferred_project_link`

**What it tests:** When a suggestedProject relationship is written, the server queries Neo4j for context (similar assigned requirements, ADR population), computes one of the 12 `inference_*` state strings, and stores it on the relationship as `inferenceState`.

**Step 3a — Find an unassigned requirement:**

> Are there any requirements that have not been assigned to a project?

This calls `get_unassigned_requirements`. Note a `req_id` from the result (e.g. `REQ-ADR43-001`) and its `adr_id`.

**Step 3b — Find a target project:**

> List all projects.

Note a `project_id` to assign to (e.g. `PROJ-BRAKES`).

**Step 3c — Write an inferred link:**

> Suggest that requirement [req_id from 3a] belongs to project [project_id from 3b] with confidence 0.65, because it shares the same ADR source as other braking requirements already assigned there.

This calls `write_inferred_project_link`. The response JSON should contain:

```json
{
  "original_confidence": 0.65,
  "adjusted_confidence": ...,
  "inference_state": "inference_strong_yes_mid"
}
```

**Step 3d — Verify the relationship was stored correctly:**

> Run this Cypher query: MATCH (r)-[rel:suggestedProject]->(p) RETURN r.hasID, p.projectID, rel.confidence, rel.inferenceState LIMIT 5

**Pass criteria:**
- `inference_state` in the `write_inferred_project_link` response is one of the 12 valid strings (not `"inference"`)
- `adjusted_confidence` differs from `original_confidence` by ±0.1 (agent nudged it)
- `rel.inferenceState` is populated in the Cypher query result

---

## Test 4 — FIX 2: `recommended` and `warning` fields in `get_inferred_links`

**What it tests:** Every entry returned by `get_inferred_links` includes a `recommended` boolean (true when confidence ≥ 0.6) and a `warning` string (set when confidence < 0.4).

**Ask Ollama (after Test 3 has created at least one inferred link):**

> Show me all inferred project links and tell me which ones are recommended.

This calls `get_inferred_links`.

**Pass criteria:**
- Each entry in `inferred_links` has a `recommended` field (`true` or `false`)
- The link written in Test 3 (confidence ~0.65) shows `"recommended": true`
- Any link with confidence < 0.4 shows `"warning": "low confidence — review carefully"` and `"recommended": false`
- Links with 0.4 ≤ confidence < 0.6 show `"recommended": false` and `"warning": null`

---

## Test 5 — FIX 3: Auto-apply `PENALTY_OVERCONFIDENT` on high-confidence rejection

**What it tests:** When a person rejects a suggestion whose stored `suggestedProject` relationship has `confidence > 0.8`, the reward is automatically replaced with `PENALTY_OVERCONFIDENT = -2.0` and `overconfidencePenaltyApplied = true` is stored.

**Step 5a — Write a high-confidence inferred link:**

> Suggest that requirement [req_id] belongs to project [project_id] with confidence 0.92, because of very strong evidence from similar requirements in the same ADR.

Confirm the `adjusted_confidence` in the response is > 0.8 (if the RL agent pushes it to ≥ 0.82, it still exceeds the threshold).

> Run this Cypher query: MATCH (r {hasID: "[req_id]"})-[rel:suggestedProject]->(p {projectID: "[project_id]"}) RETURN rel.confidence

Confirm the stored confidence is > 0.8 before proceeding.

**Step 5b — Reject it (typed command; this is not sent to the model):**

```
reject link [req_id] -> [project_id] because overconfidence test
```

On the first review command of the session `ollama-mcp` asks for your name. The command calls `reject_inferred_link` directly; the model cannot, because review functions are not MCP tools.

**Expected output:**

```
[review] Rejected [req_id] -> [project_id] as [your name]; reward -2.0 (overconfidence penalty).
```

**Pass criteria:**
- The reward is `-2.0`, not `-1.0` (the penalty replaces the rejection reward)
- The output mentions the overconfidence penalty
- The FeedbackEvent node can be queried from Neo4j with `overconfidencePenaltyApplied = true`

**Verify in Neo4j:**

> Run this Cypher query: MATCH (fe:FeedbackEvent) RETURN fe.action, fe.reward, fe.overconfidencePenaltyApplied ORDER BY fe.timestamp DESC LIMIT 3

---

## Test 5b — Rejection through `reject_inferred_link` keeps the suggestion and blocks double feedback

**What it tests:** `reject_inferred_link` records a `rejected` FeedbackEvent that names the reviewer, marks the suggestion `status = 'rejected'` without deleting it, and any later feedback for the same pair is refused instead of being counted twice.

**Step 5b-1 — Write a fresh suggestion** for a requirement/project pair that has no suggestion yet (use Step 3a–3c to pick one):

> Suggest that requirement [req_id] belongs to project [project_id] with confidence 0.65, because it shares the same ADR source as other requirements already assigned there.

Confirm the response has `"status": "written"` and `"write_mode": "created"`.

**Step 5b-2 — Reject it as a named reviewer (typed command, not sent to the model):**

```
reject link [req_id] -> [project_id] because belongs to a different subsystem
```

Give your name if asked. This calls `reject_inferred_link`.

**Expected output:**

```
[review] Rejected [req_id] -> [project_id] as [your name]; reward -1.0.
```

Alternatively run `python3 thesis-extension/scripts/review-links.py --reviewer "[your name]"`, answer `r` for this suggestion and give the same reason.

**Step 5b-3 — The suggestion is kept, marked rejected:**

> Run this Cypher query: MATCH (r {hasID: "[req_id]"})-[s:suggestedProject]->(p {projectID: "[project_id]"}) RETURN s.status, s.reviewedBy, s.reviewedAt, s.rejectionReason, s.confidence

**Step 5b-4 — The FeedbackEvent names the reviewer:**

> Run this Cypher query: MATCH (fe:FeedbackEvent {requirementID: "[req_id]", projectID: "[project_id]"}) RETURN fe.action, fe.reward, fe.reviewer, fe.timestamp ORDER BY fe.timestamp DESC

**Step 5b-5 — A second decision on the same pair is refused:**

```
reject link [req_id] -> [project_id] because second attempt
```

**Expected output:** `[review] Not recorded: ... already reviewed (status 'rejected'); feedback not recorded again.` followed by `Earlier decision:` with `status: "rejected"`, your name as `reviewed_by`, and the original reason.

**Step 5b-5b — The model cannot review:** ask in plain language

> Reject the inferred link from [req_id] to [project_id].

The model has no review tool, so it should say it cannot; no `[tool] reject_inferred_link` or `[tool] record_feedback` line appears.

**Step 5b-6 — Re-suggesting does not overwrite the decision:**

> Suggest that requirement [req_id] belongs to project [project_id] with confidence 0.7, because of the same ADR source.

**Expected response:** `"status": "previously_reviewed"` with the same `previous_decision`; the stored suggestion is unchanged.

**Pass criteria:**
- Step 5b-3 returns exactly one row with `s.status = "rejected"`, your name in `s.reviewedBy`, a `s.reviewedAt` timestamp and the reason in `s.rejectionReason`
- Step 5b-4 returns exactly one `rejected` FeedbackEvent for the pair, with `fe.reviewer` set to your name
- Step 5b-5 returns an error with `previous_decision`, and re-running the Step 5b-4 query still returns exactly one FeedbackEvent
- Step 5b-6 returns `previously_reviewed` and Step 5b-3 still shows the original confidence

---

## Test 6 — FIX 5: File lock is created during saves

**What it tests:** Every save goes through `locked_update` in `reinforcemnt-learning.py`, which takes `.rl-model.json.lock`, reloads the latest saved model, applies only the current change and writes the file atomically. This stops `ollama-mcp`, `sr8-mcp` and review commands from overwriting each other's updates with stale in-memory copies. The overwrite scenario itself is covered offline by `tests/test_rl_persistence.py`.

This cannot be easily observed through Ollama alone, but the lock file's existence can be confirmed after any feedback event.

**Ask Ollama (immediately after Test 5):**

> Show me the current RL policy.

Then in a separate terminal, quickly run:

```bash
ls -la thesis-extension/.rl-model.json*
```

**Pass criteria:**
- `.rl-model.json` exists and has a recent modification timestamp (updated by the rejection in Test 5)
- `.rl-model.json.lock` exists (created by `locked_update`; may be 0 bytes, which is expected)
- The JSON file is valid: `python3 -m json.tool thesis-extension/.rl-model.json > /dev/null && echo valid`

---

## Test 7 — FIX 4: Replay buffer accumulates live transitions

**What it tests:** `_rl_replay_buffer` (capacity 500) holds transitions from `_rl_update` calls. When ≥ 32 transitions have accumulated, `agent.replay()` is triggered automatically to batch-update Q-values.

The replay batch is invisible from outside, but its effect can be observed by checking that Q-values shift after many feedback events.

**Step 7a — Record the Q-values before:**

> Show me the current RL policy.

Note the Q-values for one state, e.g. `inference_strong_yes_high`.

**Step 7b — Submit 35 feedback events:**

Run the following in a separate terminal (bypasses Ollama; calls the tool function directly):

```bash
/opt/miniconda3/bin/python3 - <<'EOF'
import importlib.util, json
from pathlib import Path

# Load sr8-mcp directly
spec = importlib.util.spec_from_loader(
    "sr8_mcp",
    importlib.util.LazyLoader(
        importlib.machinery.SourceFileLoader("sr8_mcp", "thesis-extension/sr8-mcp")
    ),
)
import importlib.machinery
loader = importlib.machinery.SourceFileLoader("sr8_mcp", "thesis-extension/sr8-mcp")
spec = importlib.util.spec_from_loader("sr8_mcp", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

# Fire 35 feedback events directly via _rl_update (bypasses Neo4j write)
for i in range(35):
    mod._rl_update("confirmed", 1.0, state="inference_strong_yes_high")

print("35 updates sent")

# Read updated Q-table
agent = mod._load_rl_agent()
state = "inference_strong_yes_high"
if state in agent.q_table:
    print(f"Q-values for {state}:", json.dumps(agent.q_table[state], indent=2))
EOF
```

**Step 7c — Check Q-values shifted:**

> Show me the current RL policy.

**Pass criteria:**
- Q-values for `inference_strong_yes_high` are higher for `increase_confidence` than before step 7b
- The script in 7b prints without error and shows non-zero Q-values
- `.rl-model.json` modification time is updated

---

## Test 8 — Full end-to-end RL loop

**What it tests:** The complete inference → feedback → policy update cycle works as a unit.

**Ask Ollama (single conversation):**

> 1. Are there any unassigned requirements?
> 2. For the first one, suggest it belongs to the most appropriate project with a confidence score. Use the graph to reason about similar requirements.
> 3. Show me all inferred links and tell me which are recommended.
Then, as the reviewer, type (not a question to the model):

```
reject link [req_id] -> [project_id] because end-to-end test
```

> 5. Now show me the RL policy — has the agent updated?

**Pass criteria:**
- Step 2 calls `get_unassigned_requirements`, then `get_similar_assigned_requirements`, then `write_inferred_project_link` — all three tools appear in the tool call log
- Step 3 response includes `recommended` and `warning` fields
- The typed `reject link` command prints `[review] Rejected ...` with the reward; if confidence was > 0.8, the penalty is applied automatically
- Step 5 shows an epsilon value lower than the one reported in Test 1 (exploration has decayed)

---

## Quick reference — what each fix produces in responses

| Fix | Tool | Field to check | Expected value |
|-----|------|----------------|----------------|
| FIX 1 | `write_inferred_project_link` | `inference_state` | one of 12 `inference_*` strings |
| FIX 1 | `write_inferred_project_link` | `adjusted_confidence` | differs from `original_confidence` by ±0.1 |
| FIX 2 | `get_inferred_links` | `recommended` | `true` when confidence ≥ 0.6 |
| FIX 2 | `get_inferred_links` | `warning` | `"low confidence — review carefully"` when confidence < 0.4 |
| FIX 3 | typed `reject link` | reward | `-2.0` when confidence > 0.8, with "overconfidence penalty" |
| Review | typed `reject link` / `review-links.py` | outcome | `Rejected ...`, reward `-1.0` (or `-2.0` when confidence > 0.8) |
| Review | second decision on same pair | outcome | `Not recorded: ... already reviewed` plus earlier decision; no second FeedbackEvent |
| Review | model asked to confirm/reject | tool calls | none; review functions are not MCP tools |
| Review | `write_inferred_project_link` after review | `status` | `"previously_reviewed"` (unless `resubmit=True`) |
| FIX 5 | any write | `.rl-model.json.lock` | file exists on disk |
| FIX 6 | `get_rl_policy` | 12 inference states | all present with non-zero Q-values on first start |
| FIX 7 | `get_rl_policy` | full text report | epsilon, Q-table, feedback stats, convergence |

---

## Troubleshooting

**`get_rl_policy` returns "RL agent not available"**
The `reinforcemnt-learning.py` file is missing or unreadable. Check it exists at `thesis-extension/reinforcemnt-learning.py`.

**`inference_state` is missing from `write_inferred_project_link` response**
The Neo4j context query in `_inference_state` may have failed silently, falling back to state `"inference"` (the old default). Check Neo4j is running and the password in `.env` is correct.

**`reward_applied` is `-1.0` instead of `-2.0` in Test 5**
The stored confidence on the `suggestedProject` relationship is ≤ 0.8. Repeat with a higher initial confidence (0.92+) and verify with the Cypher query in step 5a before rejecting.

**Q-values do not change after Test 7**
The replay batch only fires when `len(_rl_replay_buffer) >= 32`. If fewer than 32 calls to `_rl_update` have been made in this server session, the batch has not run yet. The `_rl_replay_buffer` resets when the server restarts (it is in-memory only).
