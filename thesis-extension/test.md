# Model Test Questions

Use these prompts in the chat client to validate what the model can answer from MCP tools and indexed sources.

## ADR Requirement Coverage

1. How many requirements are there for ADR-43?
2. List all requirements for ADR-25.
3. Get essential requirements for ADR-31 from the graph.
4. Compare the requirement count for ADR-10 and ADR-95.
5. Show requirements for ADR-92 with source pointers.
6. Which ADR in the current mapping has the highest number of requirements?

## Evidence and Reference Questions

1. Find references to ADR-43 in local docs.
2. Find references to ADR-95 in local docs and include file and row/line evidence.
3. Show where braking-related requirements appear in the local documents.
4. Find references for manufacturing checklist items in the design documentation.
5. Return evidence for tyre-related requirements in ADR-23.

## Design and Manufacturing Guidance

1. What is the design process for this project?
2. What should be included in the conceptual design phase?
3. What should be included in the preliminary design phase?
4. What should be included in the detailed design phase?
5. What are the manufacturing checklist steps?
6. What are the key quality-control steps in manufacturing?

## Extraction and Pipeline Questions

1. Run extraction for requirements and summarize failures if any.
2. Run extraction and tell me which ADR files were processed.
3. After extraction, list any ADRs with missing or low-confidence results.
4. Summarize extraction output for ADR-95.

## Knowledge Graph and Cypher Questions

1. Run a Cypher query to count AustralianDesignRule nodes.
2. Count all requirement nodes in the graph.
3. List ADR IDs currently available in the graph.
4. Return top 5 ADRs by number of linked requirements.
5. Show all requirement nodes linked to ADR-31.

## Document Reading and OCR Validation

1. Read the Design Manual and summarize The Design Process section.
2. Read the Manufacturing Section and summarize the Manufacturing section.
3. Find text in scanned PDFs related to braking performance requirements.
4. Extract and summarize any OCR-recovered content for tyre regulations.

## Robustness and Context-Safety Checks

1. What is the moon made of? (should be rejected as out-of-context if strict mode is enabled)
2. Give advice without citing files. (should force evidence or reject in strict citation mode)
3. Answer using only indexed sources: what are ADR-95 key constraints?
4. If evidence is missing, explicitly state that indexed context is insufficient.
