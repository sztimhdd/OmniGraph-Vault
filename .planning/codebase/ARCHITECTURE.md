# Architecture

**Analysis Date:** 2026-04-21

## Pattern Overview

**Overall:** Multi-layer asyncio-based knowledge graph ingestion and synthesis system

**Key Characteristics:**
- Asynchronous pipeline-based processing (all I/O operations use `async`/`await`)
- Dual-fallback scraping strategy (primary + redundant methods)
- Pluggable LLM backends (Gemini for both generation and embeddings)
- Decoupled memory layer (Cognee) for entity canonicalization and context recall
- Local-first data persistence (all artifacts stored in `~/.hermes/kg-vault/`)

## Layers

**Ingestion Layer:**
- Purpose: Extract content from external sources (web, PDF) and normalize to markdown
- Location: `ingest_wechat.py`, `ingest_pdf()` in `ingest_wechat.py`, `multimodal_ingest.py`
- Contains: Web scraping (Apify + CDP fallback), PDF extraction (PyMuPDF), image download/description
- Depends on: Playwright (CDP), Apify SDK, BeautifulSoup, html2text, Gemini Vision API
- Used by: Orchestration scripts (command-line interfaces)

**Knowledge Graph Layer:**
- Purpose: Build and maintain the graph structure (entities, relationships, concepts)
- Location: LightRAG (external library in `requirements.txt`)
- Contains: Graph construction via `ainsert()`, querying via `aquery()`
- Depends on: Gemini LLM (generation) + Gemini Embeddings (vector representation)
- Used by: Synthesis layer for retrieval and inference

**Memory/Canonicalization Layer:**
- Purpose: Track conversation history, learn entity aliases, deduplicate synonyms
- Location: `cognee_wrapper.py`, `cognee_batch_processor.py`
- Contains: Entity disambiguation, past query recall, synthesis memory storage
- Depends on: Cognee library with Gemini backend
- Used by: Synthesis layer to add historical context and entity normalization

**Synthesis Layer:**
- Purpose: Answer queries by combining LightRAG retrieval with memory context
- Location: `kg_synthesize.py`, `query_lightrag.py`
- Contains: Custom prompt engineering, response generation, Cognee integration
- Depends on: LightRAG queries + Cognee context recall
- Used by: External agents (Openclaw, Hermes Agent) via subprocess calls

**Configuration & Environment Layer:**
- Purpose: Centralized path and secret management
- Location: `config.py`
- Contains: Environment loading from `~/.hermes/.env`, base paths for storage
- Depends on: OS environment variables, pathlib
- Used by: All other layers during initialization

## Data Flow

**Ingestion Flow:**

1. User provides URL or file path → `ingest_wechat.py` or `multimodal_ingest.py`
2. Try Apify scraper → returns markdown + image URLs (fast path)
3. On Apify failure (bot detection, timeout) → fallback to CDP (Playwright)
4. Extract all image URLs from content
5. Download each image to `~/.hermes/kg-vault/images/{article_hash}/`
6. Describe each image via Gemini Vision API, embed description in markdown
7. Extract raw entities via Gemini entity extraction → buffer to disk
8. Insert full content (text + image descriptions) into LightRAG graph via `ainsert()`
9. Async batch: cognee_batch_processor polls entity buffer, canonicalizes via Cognee, updates `canonical_map.json`

**Query Flow:**

1. User submits question → `kg_synthesize.py` or `query_lightrag.py`
2. Load `canonical_map.json` (if exists) → normalize query terms
3. Parallel: LightRAG query (via `aquery()` with mode: naive/hybrid/global)
4. Parallel: Cognee recall → retrieve past context from memory
5. Combine both: Cognee context (historical) + LightRAG context (graph) + custom prompt
6. Generate response via Gemini LLM
7. Store query + response in Cognee memory for future context
8. Return synthesized markdown response to caller

**State Management:**
- **LightRAG index**: Persistent in `~/.hermes/kg-vault/lightrag_storage/` (graph edges, entities, embeddings)
- **Cognee memory**: Persistent in Cognee's internal DB (conversation state, entity aliases)
- **Canonical map**: JSON file at `~/.hermes/kg-vault/canonical_map.json` (entity normalization rules)
- **Entity buffer**: Temporary JSON files in `entity_buffer/` directory, processed async by batch processor
- **Images**: Local copies at `~/.hermes/kg-vault/images/{article_hash}/` with metadata.json + final_content.md

## Key Abstractions

**ToolNode (planned, Phase 2-4):**
- Purpose: Represents a software tool or framework in the knowledge graph
- Examples: LightRAG, Cognee, n8n, Cursor (as described in `specs/OMNIGRAPH_VISION_Statement.md`)
- Pattern: Tree-like schema with identity fields (name, aliases, category), knowledge layers (official_docs, community_zh, tutorials), and relationship edges (BASED_ON, INTEGRATES, COMPETES, USED_WITH)

**QueryParam:**
- Purpose: Encapsulates query mode and response type for LightRAG
- Examples: `QueryParam(mode="hybrid", response_type="Detailed Markdown Article")`
- Pattern: Simple dataclass passed to `rag.aquery()` to control retrieval strategy

**ArticleData:**
- Purpose: Intermediate data structure from scraping (Apify or CDP)
- Pattern: Dictionary with keys: title, markdown/content_html, publish_time, url, method
- Example: `{"title": "...", "markdown": "...", "publish_time": "2024-04-01", "method": "apify"}`

## Entry Points

**`ingest_wechat.py`:**
- Location: Project root
- Triggers: `python ingest_wechat.py <url>` (or default hardcoded URL)
- Responsibilities: Primary ingestion script for WeChat articles and web content
- Invokes: Apify client, CDP browser, Gemini Vision for images, LightRAG insertion, Cognee entity buffering

**`kg_synthesize.py`:**
- Location: Project root
- Triggers: `python kg_synthesize.py "<query>" [mode]` (subprocess call from agent)
- Responsibilities: Answer user queries with synthesis
- Returns: Markdown response to stdout and file at `~/.hermes/kg-vault/synthesis_output.md`

**`query_lightrag.py`:**
- Location: Project root
- Triggers: `python query_lightrag.py "<query>"` (direct LightRAG query without Cognee)
- Responsibilities: Raw knowledge graph queries for debugging/validation
- Returns: Direct LightRAG response to stdout

**`multimodal_ingest.py`:**
- Location: Project root
- Triggers: `python multimodal_ingest.py <pdf_path>` (local file ingestion)
- Responsibilities: PDF extraction with image description and indexing
- Returns: Ingested content in LightRAG, local copies in images directory

**`cognee_batch_processor.py`:**
- Location: Project root (meant to run as daemon/background task)
- Triggers: Scheduled or continuous polling of `entity_buffer/` directory
- Responsibilities: Async entity canonicalization and map building
- Operates: Watches for new `*_entities.json` files, processes them, marks `.processed`

## Error Handling

**Strategy:** Graceful degradation with fallback chains

**Patterns:**
- Scraping: Apify (primary) → CDP (secondary) → fail with clear message
- Image download: HTTP error → log warning, continue (don't block article ingestion)
- Image description: Gemini API error → fallback string "Error describing image: {e}"
- Cognee operations: Always wrapped in try/except, warnings logged, main flow unaffected (async + non-blocking)
- LightRAG queries: Retry loop (3 attempts with 5s backoff) before raising exception

Example from `kg_synthesize.py` (lines 74-81):
```python
for i in range(3):
    try:
        response = await rag.aquery(custom_prompt, param=param)
        break
    except Exception as e:
        print(f"Query attempt {i+1} failed: {e}")
        if i < 2: await asyncio.sleep(5)
        else: raise e
```

## Cross-Cutting Concerns

**Logging:** 
- Print-based for CLI scripts (no structured logging framework)
- File-based for batch processor: `cognee_batch.log` at `/home/sztimhdd/OmniGraph-Vault/cognee_batch.log`

**Validation:** 
- Input URL validation: Basic `startswith('http')` checks for images
- File existence checks before processing (PDFs, env files)
- API response status code checks (HTTP 200 for image downloads)

**Authentication:** 
- Gemini API: Via environment variable `GEMINI_API_KEY`
- Apify: Via `APIFY_TOKEN` (optional, non-critical fallback)
- CDP: Via `CDP_URL` environment variable (default `http://localhost:9223`)
- Cognee/LiteLLM: Credentials sourced from Gemini API key

**Asset Management:**
- Image downloads: Atomic write to temp, no partial files left behind
- Canonical map: Atomic JSON write (write to `.tmp`, then `os.rename()`)
- Entity buffer: Explicit `.processed` marker after each file processed (idempotent)

---

*Architecture analysis: 2026-04-21*
