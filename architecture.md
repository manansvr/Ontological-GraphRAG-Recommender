# Architecture

## Runtime: answering a question

```mermaid
flowchart LR
    U([User]) -->|question or typed command| C

    subgraph CLIENT["ollama-mcp (chat client)"]
        C[ROUTES table<br/>checked first, first match wins]
        RLA[Problem A agent<br/>retrieval strategy]
        REV[typed review commands<br/>confirm link / reject link]
    end

    C -->|fixed route, no model| TOOLS
    C -->|confirm / reject link| REV
    C -->|no route matched: rl_prefetch| RLA
    RLA -->|graph_first / documents_first / hybrid prefetch| TOOLS
    C <-->|chat with tool calling| O[Ollama<br/>qwen2.5:14b-instruct]
    O -.->|tool calls| TOOLS

    subgraph SERVER["sr8-mcp (MCP server, stdio)"]
        TOOLS[39 MCP tools]
        VAL[schema validation<br/>of every write]
        RLB[Problem B agent<br/>inference confidence]
        RF[review functions<br/>promote / modify / reject<br/>not MCP tools]
    end

    TOOLS --> VAL --> N[(Neo4j<br/>instance graph + schema layer)]
    TOOLS --> N
    TOOLS -->|write_inferred_project_link| RLB
    TOOLS --> DOCS[local documents<br/>DOC_ROOTS]
    TOOLS --> MAP[ADR-mapping.csv / .json<br/>fallback]
    TOOLS -->|run_extraction_for_requirements| EXS[thesis-extraction<br/>run-extraction.py]
    REV -->|imports sr8-mcp in-process| RF
    RCLI[scripts/review-links.py<br/>people only] --> RF
    RF --> N
    RF --> RLB

    RLA <-->|locked_update| M[(.rl-model.json<br/>problem_a / problem_b)]
    RLB <-->|locked_read / locked_update| M
    C --> TL[logs/turns.jsonl]
    TOOLS --> IL[logs/inference.jsonl]
    RF --> IL
```

- **Routing.** `ollama-mcp` checks its `ROUTES` table before anything else (`python3 thesis-extension/ollama-mcp --print-routes` prints it).
  - Most routes call one tool and print its raw output, without the model.
  - `manufacturing_redirect` and `design_guidance` also call the model.
  - Typed `confirm link` / `reject link` commands call the review functions directly.
  - Anything else goes to `rl_prefetch`: the Problem A agent picks a prefetch strategy for questions that name an ADR or SRP (`adr_lookup`), then the model answers with tool calls.
- **People review; the model cannot.** `promote_inferred_link`, `modify_inferred_link` and `reject_inferred_link` are plain functions in `sr8-mcp`, not MCP tools. They are reached only through `scripts/review-links.py` or the typed commands.
- **Writes are validated.** Every relationship that `write_inferred_project_link` and `write_change_impact_report` create is checked against the schema layer (`SchemaRelationship` nodes) first. If the schema is missing or the relationship type is undeclared, nothing is written.
- **Two RL problems, one file.** Both are stored in `.rl-model.json`:
  - Problem A (retrieval strategy) is written only by `ollama-mcp`.
  - Problem B (inference confidence) is written only by `sr8-mcp` and the review functions.

  Every save goes through `locked_update`, which locks the file, reloads it, applies the change and writes atomically. `sr8-mcp` reloads Problem B with `locked_read` before choosing an action and before `get_rl_policy` reports. Both processes find the file through `rl_model_path.py`.

## Build: from sources to the graph

```mermaid
flowchart LR
    subgraph ONT[thesis-ontology]
        OWL[ontology.owl<br/>single source of truth] -->|scripts/owl-to-csv.py| OCSV[csv/<br/>node-labels, relationships,<br/>node-properties, relationship-properties]
        OCSV --> IMP[scripts/import.py]
        OWL --> VALP[scripts/validate.py]
        OCSV --> VALP
        OCSV --> VER[scripts/verify.py]
    end

    subgraph EXTR[thesis-extraction]
        ADR[csv/ ADR checklists] --> EA[Scripts/extract-ADR.py]
        FMEA[Brake_System_Failure_Mode_Data.xlsx] --> EF[Scripts/extract_failure_modes.py]
        ASM[data/assemblies.csv] --> EAS[Scripts/extract_assemblies.py]
        RUN[Scripts/run-extraction.py] --> EA
        RUN --> EF
        RUN --> EAS
    end

    IMP -->|schema layer + uniqueness constraints| N[(Neo4j)]
    VER -->|checks| N
    EA -->|ADRs, clauses, requirements,<br/>projects, assignedToProject| N
    EF -->|components, failure modes,<br/>causes, effects, control actions| N
    EAS -->|assemblies, belongsToAssembly| N

    ADR --> SYNC[thesis-extension/<br/>sync-ADR-mapping.py] --> MAP[ADR-mapping.csv / .json]
    FMEA --> PROP[thesis-extension/scripts/<br/>propose-fmea-links.py]
    ADR --> PROP
    PROP -->|candidates for human review,<br/>never written to the graph| PCSV[logs/fmea-link-candidates-*.csv]
```

- **Ontology.** `ontology.owl` defines 72 classes, 59 object properties and 70 data properties, plus 32 relationship properties as annotations.
  - `owl-to-csv.py` generates the four schema CSVs from it.
  - `validate.py` fails if the CSVs drift from the OWL file.
  - `import.py` loads them into Neo4j as the schema layer.
  - `verify.py` checks the import against the counts and top-level classes in the CSVs.
- **Extraction.** `run-extraction.py` runs the extractors in order: adrs, projects, parts, failure-modes, assemblies. The projects and parts steps are not implemented and are skipped. Every extractor supports `--dry-run`.
  - From the 8 ADR checklists, `extract-ADR.py` creates 217 requirements, 177 clauses and 172 `assignedToProject` links across 24 projects; 45 requirements are unassigned.
- **Supporting files.**
  - `sync-ADR-mapping.py` regenerates the ADR mapping files that `sr8-mcp` falls back to.
  - `propose-fmea-links.py` suggests FMEA-to-ADR requirement links for a person to review offline.

## Experiments and tests

```mermaid
flowchart LR
    Q[experiments/train_questions.csv<br/>experiments/questions.csv] --> RB[experiments/run-baseline.py]
    RB -->|runs each question through<br/>ollama-mcp's own chat loop| C[ollama-mcp + sr8-mcp]
    RB --> RES[experiments/results/<br/>train-* / baseline-* CSV, summary, turns, transcript]
    T[thesis-extension/tests/<br/>offline: no Neo4j, Ollama or MCP server] -.-> C
```

- **Experiment runner.**
  - `--train --passes N` trains Problem A on the 30 training questions.
  - `--evaluate` runs the 25 evaluation questions under graph_first, documents_first, hybrid and rl, with learning off.
- **Offline tests.** Run them with `python3 -m unittest discover -s thesis-extension/tests`. They use fakes for Neo4j and the MCP client.
