# SR8 GraphRAG Recommender — Demo

---

## Setup

```bash
cd thesis-extension
rm -f .rl-model.json .rl-model.json.lock
```

**2. Starting services:**

```bash
# Terminal 1
neo4j start          

# Terminal 2
ollama serve

# Terminal 3
cd thesis-extension
python3 ollama-mcp
```

---

## The demo — 5 questions

### 1. Cited answers (knowledge Extraction)
> `What does ADR-43 require?`

**Expected:** 27 requirements, each ending in `(evidence: .../ADR43-Requirements.csv | row N)`.

### 2. Compliance Gap Reports (cross-referenced deliverable)
> `What are the compliance gaps in the Front Axle Assembly (ASM-FRONT-AXLE)?`

**Expected:** 45 gaps, grouped by project (SRP8-050 Front Wheels, SRP8-045 Front Brakes,
SRP8-043 Front Suspension), each with ADR/requirement ID and risk level.

### 3. Change Impact Analyses (change imact analysis deliverable)
> `What requirements need re-verification if we change project SRP8-045?`

**Expected:** a breakdown of `must_reverify` / `must_verify` / `not_affected` counts, then a
list (36 requirements currently need verification).

### 4. The recommender — confidence score (knowledge extension)
> `For REQ-31-031, suggest the most appropriate project using the graph to find similar assigned requirements, and give me a confidence score.`

**Expected:** a vote breakdown (e.g. `SRP8-045 (3/5), SRP8-046 (2/5)`), a base confidence,
an "RL-adjusted confidence" with an inference state (e.g. `inference_strong_yes_mid`), and
confirmation it was written to the graph as a `suggestedProject` relationship.

the confidence isn't the LLM guessing, it's a similarity vote over real graph
data, nudged by a trained Q-learning agent.

### 5. Prove it learns — the payoff
> `Reject that suggestion.`

then:

> `Show me the current RL policy.`

**Expected:** the `inference_strong_yes_mid` row's `↓` (decrease_confidence) Q-value is
higher than before the rejection; `Total feedback events: 1`; `Average reward: -1.0`.

**policy table:**
- suggestion fell into (`inference_strong_yes_mid`) and its `↓` value, *"that number just moved because of the rejection made thirty seconds ago, via a real Bellman update, not a hardcoded 
    counter "*
- `keep_confidence` is still the greedy action (its Q-value is much higher than
  `decrease_confidence`) so *"one rejection nudges the policy, it doesn't override it;
  the agent needs sustained, consistent feedback before it actually changes its
  recommendation."*
- `Total feedback events` / `Average reward` are backed by real `FeedbackEvent` nodes in
  Neo4j, not in-memory state, provable with `MATCH (fe:FeedbackEvent) RETURN fe.action, fe.reward, fe.timestamp`.

