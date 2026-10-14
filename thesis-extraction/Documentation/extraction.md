# SR8 Extraction Pipeline — Command Reference

## Overview

Two scripts, two sources, one neo4j graph.

| Script | Source | What it writes |
|---|---|---|
| `extract-ADR.py` | `CSV/*.csv` (8 ADR files) | AustralianDesignRule, Clause, ExtractedEssentialRequirement, Project (stub), Department |
| `run-extraction.py` | orchestrates both | runs extract-ADR.py first, then extract_projects.py |
| `extract_assemblies.py` | `data/assemblies.csv` | Assembly, Project -[:belongsToAssembly]-> Assembly (`--only assemblies`) |

`extract-ADR.py` sets `source = 'extracted'` on each `assignedToProject` edge it creates (`ON CREATE SET`, so edges that already exist are not changed). Edges promoted from inferred suggestions by the sr8-mcp `promote_inferred_link` tool carry `source = 'inferred'` instead.

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
thesis-extraction/
├── CSV/                          ← ADR CSV files go here
│   ├── ADR10-Requirements.csv
│   ├── ADR23-Requirements.csv
│   ├── ADR25-Requirements.csv
│   ├── ADR31-Requirements.csv
│   ├── ADR42-Requirements.csv
│   ├── ADR43-Requirements.csv
│   ├── ADR92-Requirements.csv
│   └── ADR95-Requirements.csv
├── Scripts/
│   ├── extract-ADR.py            ← renamed from extract_adrs.py
│   └── run-extraction.py         ← master orchestrator
```

The ontology schema CSV files live in `../thesis-ontology/CSV/`.

---

## Step 0 — Load the ontology schema (run once on a fresh database)

Copy CSV files to neo4j import folder:
```bash
cp CSV/node-labels.csv /opt/homebrew/var/neo4j/import/
cp CSV/relationships.csv /opt/homebrew/var/neo4j/import/
cp CSV/node-properties.csv /opt/homebrew/var/neo4j/import/
```

Then in neo4j Browser run each block from `thesis-ontology/Documentation/one-shot-cypher.md` in order (blocks 1–5).

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
python3 Scripts/extract-ADR.py --file CSV/ADR10-Requirements.csv --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/extract-ADR.py --file CSV/ADR10-Requirements.csv --uri bolt://localhost:7687 --user neo4j --password password123
```

---

## Step 1b — Extract Failure Modes (FMEA)

Source: `Brake_System_Failure_Mode_Data.xlsx` (sheets `Failure Mode Data` and `Requirement Mapping`).

Writes:
- `Component -[:hasFailureMode]-> FailureMode`
- `FailureMode -[:causedBy]-> Cause`
- `FailureMode -[:causes]-> Effect`
- `FailureMode -[:mitigatedBy]-> ControlAction`
- `Component -[:satisfiesRequirement]-> Requirement` (lightweight `Requirement` nodes keyed on `hasName`, not linked to `ExtractedEssentialRequirement` — link those manually in the Browser once matches are verified)

`Component` nodes are MERGEd on `hasID` = the raw component name (e.g. `BrakeDiscs`), so this attaches to whatever `Component` nodes the parts/project extractors already created.

```bash
python3 Scripts/run-extraction.py --only failure-modes --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only failure-modes --uri bolt://localhost:7687 --user neo4j --password password123
```

Or run it standalone:
```bash
python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx --dry-run
python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx
```

Requires `openpyxl` (`pip3 install openpyxl`) in addition to the `neo4j` driver.

---

## Step 2 — Extract Projects (when xlsx is exported)

Export `project-tracking-system.xlsx` as CSV:
- Google Sheets: `File → Download → Comma Separated Values`
- Place the file at `data/project-tracking-system.csv`

Then run:
```bash
python3 Scripts/run-extraction.py --only projects --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only projects --uri bolt://localhost:7687 --user neo4j --password password123
```

---

## Step 3 — Add Assembly groupings

Assemblies group projects. They are listed in `data/assemblies.csv` (one row per project: `assembly_id`, `assembly_name`, `project_id`) and created by the extraction pipeline, after the ADRs (the projects must already exist):

```bash
python3 Scripts/run-extraction.py --only assemblies --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
python3 Scripts/run-extraction.py --only assemblies --uri bolt://localhost:7687 --user neo4j --password password123
```

This writes `(:Assembly {hasID, hasName})` and `(:Project)-[:belongsToAssembly]->(:Assembly)`, the names declared in `thesis-ontology/csv/relationships.csv`. A `project_id` that does not exist (in the graph for a live run; among the projects `extract-ADR.py` creates for a dry run) is printed as a warning and skipped; no stub project is created. For each assembly the run reports the projects linked and how many requirements reach it through `assignedToProject`.

Expected dry-run output with the current data:

```
⚠️  ASM-FRONT-AXLE: project SRP8-088 does not exist (...); skipped, no stub created
[DRY] ASM-FRONT-AXLE (Front Axle Assembly): 3 project(s) linked: SRP8-043 (1), SRP8-045 (36), SRP8-050 (8); 45 requirement(s) reach it via assignedToProject
[DRY] ASM-STEERING (Steering System): 3 project(s) linked: SRP8-047 (12), SRP8-048 (24), SRP8-049 (2); 38 requirement(s) reach it via assignedToProject
⚠️  ASM-REAR-AXLE: project SRP8-089 does not exist (...); skipped, no stub created
[DRY] ASM-REAR-AXLE (Rear Axle Assembly): 3 project(s) linked: SRP8-044 (1), SRP8-046 (25), SRP8-051 (9); 35 requirement(s) reach it via assignedToProject
```

Re-running is safe (`MERGE`). Removing a row from the CSV does not delete an edge created earlier; delete it in the Browser if needed.

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

### 2. Reload schema (in neo4j Browser — blocks from thesis-ontology/Documentation/one-shot-cypher.md)

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
The script looks for `CSV/` by default. Confirm your CSVs are there:
```bash
ls CSV/
```

### Re-running is always safe
All writes use `MERGE` — running the extraction twice never creates duplicates.

---

## Failure Mode (FMEA) Extraction — Full Walkthrough

End-to-end steps to extract `Brake_System_Failure_Mode_Data.xlsx` into neo4j and verify it, from a cold terminal.

### 1. Start neo4j
```bash
brew services start neo4j
neo4j status
```
Wait ~10 seconds after starting, then confirm the Browser loads at http://localhost:7474.

### 2. Install python dependencies
```bash
cd thesis-extraction
python3 -m pip install neo4j openpyxl
```
Use `python3 -m pip install`, not a bare `pip3 install` — it guarantees the packages land in the same interpreter that runs the script (matters if you have multiple Pythons, e.g. conda `base` alongside system Python).

### 3. Dry run (preview only, nothing written)
```bash
python3 Scripts/run-extraction.py --only failure-modes --dry-run --uri bolt://localhost:7687 --user neo4j --password password123
```
Expected tail of output:
```
   ✓ Components: 15 | Failure modes: 22 | Requirement links: 23 | Skipped: 0
```
If `Skipped` is nonzero, or the counts don't match, something in the xlsx sheet layout changed — check the sheet names are still exactly `Failure Mode Data` and `Requirement Mapping`.

### 4. Live run
```bash
python3 Scripts/run-extraction.py --only failure-modes --uri bolt://localhost:7687 --user neo4j --password password123
```
Same counts as the dry run, minus the `[DRY]` prefixes — this time it's actually written.

### 5. Verify in neo4j Browser (http://localhost:7474)

**Node counts by label:**
```cypher
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN ["Component","FailureMode","Cause","Effect","ControlAction","Requirement"])
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
```
Expect: `Component` 15, `FailureMode` 22, `Requirement` ≤ 23 (some requirement text repeats across components and correctly merges into one node), `Cause`/`Effect`/`ControlAction` deduplicated wherever the same cause/effect/action recurs (e.g. `adjuster_mechanism_inadequate` is shared by `BrakeDiscs`, `BrakeDrums`, `BrakeLinings` and should be **one** `Cause` node, not three).

**Full FMEA chain for one component** (same shape as the Aura screenshot query):
```cypher
MATCH (c:Component {hasID: "BrakeDiscs"})-[:hasFailureMode]->(fm)
OPTIONAL MATCH (fm)-[:causedBy]->(cause)
OPTIONAL MATCH (fm)-[:causes]->(effect)
OPTIONAL MATCH (fm)-[:mitigatedBy]->(ca)
RETURN c, fm, cause, effect, ca
```

**Requirement links:**
```cypher
MATCH (c:Component)-[:satisfiesRequirement]->(r:Requirement)
RETURN c.hasID, r.hasName
ORDER BY c.hasID
```

**Everything reachable from one component in one shot:**
```cypher
MATCH (c:Component {hasID: "ServiceBrakingSystem"})-[r]-(n)
RETURN c, r, n
```

**Components with an unmitigated failure mode** (thesis-relevant query — the kind of cross-domain check this integration enables):
```cypher
MATCH (c:Component)-[:hasFailureMode]->(fm)
WHERE NOT (fm)-[:mitigatedBy]->()
RETURN c.hasID, fm.hasName
```
(Should return nothing against this dataset — every row has a `ControlAction` — which is itself a useful sanity check that nothing silently failed to link.)

### 6. Idempotency check
Re-run the live command from step 4 a **second time**, then re-run the count query from step 5. The counts must stay exactly the same — if any count increased, a `MERGE` key collided incorrectly and something is duplicating instead of matching.

### 7. Cross-link check against other extractors
If `Component` nodes already exist from the parts/project extractors, confirm the FMEA data attached to the *same* node rather than creating a duplicate:
```cypher
MATCH (c:Component {hasID: "BrakeDiscs"}) RETURN c, labels(c)
```
One node, one set of labels/properties — if you see two separate `BrakeDiscs` components, there's a naming/case mismatch between the xlsx and whatever created the other node.

### Standalone (no orchestrator)
```bash
python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx --dry-run
python3 Scripts/extract_failure_modes.py --file Brake_System_Failure_Mode_Data.xlsx --uri bolt://localhost:7687 --user neo4j --password password123
```