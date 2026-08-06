# Extraction Demo 

## setup

```bash
brew services start neo4j
neo4j status
open http://localhost:7474        # login: neo4j / password123
cd /Users/manan/Desktop/Ontological-GraphRAG-Recommender/thesis-extraction
source .venv/bin/activate
```

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;
```

Expected: `ExtractedEssentialRequirement`/`Requirement` ~217+22, `Clause` ~255, `Component` 15, `FailureMode` 20, `Project`, `Department`, `Assembly` (3), `AustralianDesignRule` 8.

---

## running extraction live 

```bash
# ADR CSVs
python3 Scripts/run-extraction.py --only adrs --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only adrs --uri bolt://localhost:7687 --user neo4j --password password123

# Kun's brake FMEA
python3 Scripts/run-extraction.py --only failure-modes --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only failure-modes --uri bolt://localhost:7687 --user neo4j --password password123
```

All writes use `MERGE` — safe to re-run, never duplicates.

---
"FMEA's `Effect` nodes are real operational failure scenarios, which is exactly what the ontology's `ValidationScenario` class is meant to hold. `ControlAction` nodes are testable success conditions, `AcceptanceCriterion` content."

