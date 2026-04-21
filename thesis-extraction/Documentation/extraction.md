# SR8 Extraction Pipeline — Command Reference

## Overview

Two scripts, two sources, one neo4j graph.

| Script | Source | What it writes |
|---|---|---|
| `extract-ADR.py` | `csv/*.csv` (8 ADR files) | AustralianDesignRule, Clause, ExtractedEssentialRequirement, Project (stub), Department |
| `run-extraction.py` | orchestrates both | runs extract-ADR.py first, then extract_projects.py |

---

## Prerequisites

### Start neo4j
```bash
brew services start neo4j
```

Confirm it is running:
```bash
neo4j status
```

Open the browser at: http://localhost:7474

### Check your folder structure
```
thesis-ontology/
├── csv/                          ← ADR CSV files go here
│   ├── ADR10-Requirements.csv
│   ├── ADR23-Requirements.csv
│   ├── ADR25-Requirements.csv
│   ├── ADR31-Requirements.csv
│   ├── ADR42-Requirements.csv
│   ├── ADR43-Requirements.csv
│   ├── ADR92-Requirements.csv
│   └── ADR95-Requirements.csv
├── data/
│   └── project-tracking-system.csv   ← export from xlsx when ready
├── Scripts/
│   ├── extract-ADR.py            ← renamed from extract_adrs.py
│   └── run-extraction.py         ← master orchestrator
```

---

## Step 0 — Load the ontology schema (run once on a fresh database)

Copy CSV files to neo4j import folder:
```bash
cp csv/node-labels.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
cp csv/relationships.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
cp csv/node-properties.csv /opt/homebrew/Cellar/neo4j/2026.02.3/libexec/import/
```

Then in neo4j Browser run each block from `docs/one-shot-cypher.md` in order (blocks 1–5).

---

## Step 1 — Extract ADRs

### Dry run first (preview — nothing written to neo4j)
```bash
python3 Scripts/run-extraction.py --only adrs --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
```

Check the output:
- ADR IDs show as `ADR-10`, `ADR-23` etc
- Project IDs show as `SRP8-048` etc
- Applicable rows show `[DRY]`, not-applicable rows show `[N/A]`

### Live run
```bash
python3 Scripts/run-extraction.py --only adrs --uri bolt://localhost:7687 --user neo4j --password password123
```

### Expected output
```
📁 Found 8 CSV file(s) in csv

📄 ADR10-Requirements.csv
   11 rows | Headers: [...]
   ✓ Clauses: 11 | Requirements: 11 (6 not applicable) | VPs: 0 | Links: 5

📄 ADR23-Requirements.csv  ...
📄 ADR25-Requirements.csv  ...
📄 ADR31-Requirements.csv  ...
📄 ADR42-Requirements.csv  ...
📄 ADR43-Requirements.csv  ...
📄 ADR92-Requirements.csv  ...
📄 ADR95-Requirements.csv  ...

   ── TOTAL across 8 files ──
     clauses: 243
     requirements: 205
     not_applicable: 6
     proj_links: 178
```

### Run a single ADR file only
```bash
python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/extract-ADR.py --file csv/ADR10-Requirements.csv --uri bolt://localhost:7687 --user neo4j --password password123
```

---

## Step 2 — Extract Projects (when xlsx is exported)

Export `project-tracing-system.xlsx` as CSV:
- Google Sheets: `File → Download → Comma Separated Values`
- Place the file at `data/project-tracking-system.csv`

Then run:
```bash
python3 Scripts/run-extraction.py --only projects --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only projects --uri bolt://localhost:7687 --user neo4j --password password123
```

---

## Step 3 — Add Assembly groupings (run once in neo4j Browser)

After extraction, add assembly nodes manually in the Browser.

Delete old assembly links if re-running:
```cypher
MATCH ()-[r:includesProject|belongsToAssembly]->() DELETE r
MATCH (a:Assembly) DETACH DELETE a
```

Create Front Axle Assembly:
```cypher
MERGE (a:Assembly {hasID: "ASM-FRONT-AXLE", hasName: "Front Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-043", "SRP8-045", "SRP8-050", "SRP8-088"]
MERGE (p)-[:belongsToAssembly]->(a)
```

Create Steering System:
```cypher
MERGE (a:Assembly {hasID: "ASM-STEERING", hasName: "Steering System"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-047", "SRP8-048", "SRP8-049"]
MERGE (p)-[:belongsToAssembly]->(a)
```

Create Rear Axle Assembly:
```cypher
MERGE (a:Assembly {hasID: "ASM-REAR-AXLE", hasName: "Rear Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-044", "SRP8-046", "SRP8-051", "SRP8-089"]
MERGE (p)-[:belongsToAssembly]->(a)
```

---

## Verification queries (run in neo4j Browser)

### Count all node types
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
```

### Check ADR → Clause counts
```cypher
MATCH (a:AustralianDesignRule)-[:hasClause]->(c:Clause)
RETURN a.hasID, count(c) AS clauses
ORDER BY a.hasID
```

### Full 4-level hierarchy — one ADR
```cypher
MATCH path1 = (a:AustralianDesignRule {hasID: "ADR-31"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
LIMIT 30
```

### Full 4-level hierarchy — all ADRs
```cypher
MATCH path1 = (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
```

### ADR-43 spans all 3 assemblies (best thesis demo)
```cypher
MATCH path1 = (a:AustralianDesignRule {hasID: "ADR-43"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3
```

### Only applicable requirements
```cypher
MATCH path1 = (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
WHERE r.isApplicable = true
RETURN path1, path2
```

---

## Full reset — wipe and reload everything

### 1. In neo4j Browser — wipe all data
```cypher
MATCH (n) DETACH DELETE n
```

### 2. Reload schema (in neo4j Browser — blocks from one-shot-cypher.md)

### 3. In terminal — re-run extraction
```bash
python3 Scripts/run-extraction.py --only adrs --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only projects --uri bolt://localhost:7687 --user neo4j --password password123
```

### 4. In neo4j Browser — re-add assemblies
Run the three assembly MERGE blocks from Step 3 above.

---

## Troubleshooting

### neo4j not running
```bash
brew services start neo4j
sleep 10 && neo4j status
```

### Connection refused error
neo4j stopped. Start it and wait 10 seconds before running the script again.

### Wrong password
Open http://localhost:7474, log in to confirm your password, then pass it:
```bash
python3 Scripts/run-extraction.py --only adrs --uri bolt://localhost:7687 --user neo4j --password yourpassword
```

### ADR folder not found
The script looks for `csv/` by default. Confirm your CSVs are there:
```bash
ls csv/
```

### Re-running is always safe
All writes use `MERGE` — running the extraction twice never creates duplicates.