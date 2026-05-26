# Architecture

> Note: runtime data path uses `omonigraph` typo canonically (not `omnigraph`) — see CLAUDE.md.

## Pattern Overview
- Asynchronous pipeline-based processing (all I/O operations use `async`/`await`)
- Dual-fallback scraping strategy (primary + redundant methods)
- Pluggable LLM backends (Gemini for both generation and embeddings)
- Local-first data persistence (all artifacts stored in `~/.hermes/omonigraph-vault/`)

## Layers
- Purpose: Extract content from external sources (web, PDF) and normalize to markdown
- Location: `ingest_wechat.py`, `ingest_pdf()` in `ingest_wechat.py`, `multimodal_ingest.py`
- Contains: Web scraping (Apify + CDP fallback), PDF extraction (PyMuPDF), image download/description
- Depends on: Playwright (CDP), Apify SDK, BeautifulSoup, html2text, Gemini Vision API
- Used by: Orchestration scripts (command-line interfaces)
- Purpose: Build and maintain the graph structure (entities, relationships, concepts)
- Location: LightRAG (external library in `requirements.txt`)
- Contains: Graph construction via `ainsert()`, querying via `aquery()`
- Depends on: Gemini LLM (generation) + Gemini Embeddings (vector representation)
- Used by: Synthesis layer for retrieval and inference
- Purpose: Answer queries by combining LightRAG retrieval with synthesis
- Location: `kg_synthesize.py`, `query_lightrag.py`
- Contains: Custom prompt engineering, response generation
- Depends on: LightRAG queries
- Used by: External agents (Openclaw, Hermes Agent) via subprocess calls
- Purpose: Centralized path and secret management
- Location: `config.py`
- Contains: Environment loading from `~/.hermes/.env`, base paths for storage
- Depends on: OS environment variables, pathlib
- Used by: All other layers during initialization

## Data Flow
- **LightRAG index**: Persistent in `~/.hermes/omonigraph-vault/lightrag_storage/` (graph edges, entities, embeddings)
- **Canonical map**: JSON file at `~/.hermes/omonigraph-vault/canonical_map.json` (entity normalization rules)
- **Entity buffer**: Temporary JSON files in `entity_buffer/` directory, processed async by batch processor
- **Images**: Local copies at `~/.hermes/omonigraph-vault/images/{article_hash}/` with metadata.json + final_content.md

## Key Abstractions
- Purpose: Represents a software tool or framework in the knowledge graph
- Examples: LightRAG, n8n, Cursor (as described in `specs/OMNIGRAPH_VISION_Statement.md`)
- Pattern: Tree-like schema with identity fields (name, aliases, category), knowledge layers (official_docs, community_zh, tutorials), and relationship edges (BASED_ON, INTEGRATES, COMPETES, USED_WITH)
- Purpose: Encapsulates query mode and response type for LightRAG
- Examples: `QueryParam(mode="hybrid", response_type="Detailed Markdown Article")`
- Pattern: Simple dataclass passed to `rag.aquery()` to control retrieval strategy
- Purpose: Intermediate data structure from scraping (Apify or CDP)
- Pattern: Dictionary with keys: title, markdown/content_html, publish_time, url, method
- Example: `{"title": "...", "markdown": "...", "publish_time": "2024-04-01", "method": "apify"}`

## Entry Points
- Location: Project root
- Triggers: `python ingest_wechat.py <url>` (or default hardcoded URL)
- Responsibilities: Primary ingestion script for WeChat articles and web content
- Invokes: Apify client, CDP browser, Gemini Vision for images, LightRAG insertion, entity buffering
- Location: Project root
- Triggers: `python kg_synthesize.py "<query>" [mode]` (subprocess call from agent)
- Responsibilities: Answer user queries with synthesis
- Returns: Markdown response to stdout and file at `~/.hermes/omonigraph-vault/synthesis_output.md`
- Location: Project root
- Triggers: `python query_lightrag.py "<query>"` (direct LightRAG query for debugging)
- Responsibilities: Raw knowledge graph queries for debugging/validation
- Returns: Direct LightRAG response to stdout
- Location: Project root
- Triggers: `python multimodal_ingest.py <pdf_path>` (local file ingestion)
- Responsibilities: PDF extraction with image description and indexing
- Returns: Ingested content in LightRAG, local copies in images directory
- Location: Project root (meant to run as daemon/background task)
- Triggers: Scheduled or continuous polling of `entity_buffer/` directory
- Responsibilities: Async entity canonicalization and map building
- Operates: Watches for new `*_entities.json` files, processes them, marks `.processed`

## Error Handling
- Scraping: Apify (primary) → CDP (secondary) → fail with clear message
- Image download: HTTP error → log warning, continue (don't block article ingestion)
- Image description: Gemini API error → fallback string "Error describing image: {e}"
- LightRAG queries: Retry loop (3 attempts with 5s backoff) before raising exception
```python
```

## Cross-Cutting Concerns
- Print-based for CLI scripts (no structured logging framework)
- Input URL validation: Basic `startswith('http')` checks for images
- File existence checks before processing (PDFs, env files)
- API response status code checks (HTTP 200 for image downloads)
- Gemini API: Via environment variable `GEMINI_API_KEY`
- Apify: Via `APIFY_TOKEN` (optional, non-critical fallback)
- CDP: Via `CDP_URL` environment variable (default `http://localhost:9223`)
- Image downloads: Atomic write to temp, no partial files left behind
- Canonical map: Atomic JSON write (write to `.tmp`, then `os.rename()`)
- Entity buffer: Explicit `.processed` marker after each file processed (idempotent)
