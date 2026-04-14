# Ollama + MCP for SR8 Knowledge Graph and Local Docs

**For Ollama installation and setup instructions, see [OLLAMA_SETUP.md](OLLAMA_SETUP.md).**

This folder provides a terminal workflow where an Ollama model can call MCP tools to query:

- your local Neo4j SR8 knowledge graph
- your local requirements CSV files first
- your design documentation and PDF evidence for cross-checking

## 1. Prerequisites

- Python 3.10+
- Ollama running locally
- Neo4j running locally with your extracted graph data
- Optional OCR dependencies for scanned PDFs:
	- `tesseract` (OCR engine)
	- `poppler` (PDF rendering used by `pdf2image`)

Install optional OCR system dependencies on macOS:

```bash
brew install tesseract poppler
```

## 2. Install dependencies

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure environment

```bash
cp .env.example .env
# edit .env with your actual Neo4j password/model if needed
```

Context-only safety mode:

- `STRICT_CONTEXT_ONLY=true` makes the chat client answer only when MCP tool context was used in that turn.
- If no indexed context is available, it returns: `I do not have enough context in the indexed sources to answer that.`
- `REQUIRE_EXPLICIT_CITATIONS=true` requires every answer to include at least one explicit evidence reference (`path | row N` or `path | line N`).

## 4. Start services

In separate terminals:

```bash
ollama serve
```

```bash
# optional if not already running as service
brew services start neo4j
```

Pull your preferred model once:

```bash
ollama pull llama3.1:8b
```

## 5. Run terminal chat (Ollama + MCP)

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
source .venv/bin/activate
python3 ollama-mcp --model llama3.1:8b
```

## 6. Run MCP server directly

If you want to run only the MCP server process from terminal:

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
source .venv/bin/activate
python3 sr8-mcp
```

The server uses stdio transport, so it is intended to be launched by an MCP client.
If you just run it directly, it may appear idle (no interactive prompt), which is expected.

To run chat + server together (recommended):

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
source .venv/bin/activate
python3 ollama-mcp --model llama3.1:8b
```

Then ask things like:

- "List all available ADR document files."
- "Run extraction for requirements and summarize failures if any."
- "Find references to ADR-43 in local docs."
- "Get essential requirements for ADR-31 from the graph."
- "Run a Cypher query to count AustralianDesignRule nodes."

Special behavior:

- If you ask a question like `how many requirements are there for SRP-043` (or ADR equivalent),
  the client calls `get_adr_requirements` directly and returns:
  - total count, and
  - a full requirement list for that ADR/SRP ID.
- If you ask a question like `find references to ADR-43` (or SRP equivalent),
  the client calls `get_adr_requirements` + `search_local_documents` directly and returns
  file-level references with row/line pointers.

Type /exit to quit.

## Exposed MCP tools

- list_documents
- run_extraction_for_requirements
- search_local_documents
- suggest_requirement_sources
- read_document
- query_knowledge_graph
- get_adr_requirements

## Notes

- query_knowledge_graph only allows read-only Cypher (MATCH/RETURN style).
- Document reads are restricted to paths under DOC_ROOTS in .env.
- Search/suggestion results include exact file paths with line numbers (text/PDF/DOCX) or row numbers (CSV).
- PDF files are parsed via `pypdf`; OCR fallback is used when no text is found.
- OCR fallback can be toggled using `OCR_ENABLED` in `.env`.
- Extraction can be run from chat via `run_extraction_for_requirements`.
- Set `STRICT_CONTEXT_ONLY=false` if you want to allow non-contextual model responses.
- Set `REQUIRE_EXPLICIT_CITATIONS=false` if you do not want mandatory file citations in each answer.
