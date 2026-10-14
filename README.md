# SR8 Semantic Modelling

An ontology, extraction pipeline and LLM assistant for Sunswift Racing SR8 regulatory compliance (Australian Design Rules), built on Neo4j, Ollama and the Model Context Protocol (MCP).

| Folder | What it holds | Documentation |
|---|---|---|
| `thesis-ontology/` | `ontology.owl` (72 classes, 59 object properties, 70 data properties, 32 edge properties), the schema CSVs generated from it, and the import / validation scripts | `thesis-ontology/Documentation/ontology.md` |
| `thesis-extraction/` | ADR checklists (`csv/`), the FMEA workbook, assemblies (`data/assemblies.csv`) and the extractors that load them into Neo4j | `thesis-extraction/Documentation/extraction.md` |
| `thesis-extension/` | `sr8-mcp` (MCP server, 39 tools), `ollama-mcp` (chat client with a deterministic routing table), `reinforcemnt-learning.py` (tabular Q-learning), review scripts, experiments and offline tests | `thesis-extension/README.md`, `thesis-extension/testing_rl_steps.md` |

`CHANGES-FOR-PAPER.md` lists every change on the `paper-fixes` branch with the old and new values of each reported number.

## Setup

Python 3.10 or later (the `mcp` package requires it), Neo4j 5.x and Ollama.

```bash
python3 -m pip install -r requirements.txt
cp thesis-extension/.env.example thesis-extension/.env   # then set NEO4J_PASSWORD; .env is git-ignored
ollama pull qwen2.5:14b-instruct
```

## Build the graph

```bash
cd thesis-ontology
python3 scripts/validate.py                                   # OWL checks; CSVs match ontology.owl
python3 scripts/import.py --password <neo4j password>         # schema layer + uniqueness constraints
cd ../thesis-extraction
python3 Scripts/run-extraction.py --only adrs --password <neo4j password>
python3 Scripts/run-extraction.py --only failure-modes --password <neo4j password>
python3 Scripts/run-extraction.py --only assemblies --password <neo4j password>
```

Add `--dry-run` to any extraction command to preview it without Neo4j. After editing `ontology.owl`, regenerate the CSVs with `python3 thesis-ontology/scripts/owl-to-csv.py`.

## Run the assistant

```bash
python3 thesis-extension/ollama-mcp                 # starts sr8-mcp as a child process
python3 thesis-extension/ollama-mcp --print-routes  # the fixed routing table
```

## Offline checks (no Neo4j, Ollama or MCP server)

```bash
python3 -m unittest discover -s thesis-extension/tests
python3 thesis-ontology/scripts/validate.py
python3 thesis-ontology/scripts/owl-to-csv.py --check
python3 thesis-extension/reinforcemnt-learning.py --self-test
cd thesis-extraction && python3 Scripts/extract-ADR.py --folder csv --dry-run
```
