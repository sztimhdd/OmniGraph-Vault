# External Integrations

**Analysis Date:** 2026-04-21

## APIs & External Services

**LLM & Vision Services:**
- Google Gemini API - Large language model and vision AI
  - SDK: `google-genai` Python client
  - Auth: `GEMINI_API_KEY` environment variable
  - Models used:
    - `gemini-2.5-flash` - Fast LLM for synthesis and entity extraction
    - `gemini-2.0-flash` - Fallback/legacy LLM
    - `gemini-3.1-flash-lite-preview` - Cost-optimized LLM variant
    - `gemini-embedding-001` - Semantic embeddings (768/3072 dimensions)
  - Endpoints: Vision API for image description, text generation for synthesis
  - Rate limiting: Implicit (Google Cloud quotas)
  - Used in: `ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`, `cognee_wrapper.py`

**Web Scraping:**
- Apify AI Platform - Bot-detection-resistant scraping
  - SDK: `apify-client` Python SDK
  - Auth: `APIFY_TOKEN` environment variable
  - Actor used: `zOQWQaziNeBNFWN1O` (WeChat scraping actor)
  - Configuration: Magic mode, DOM content loading, user simulation
  - Fallback: Automatic fallback to CDP when Apify fails or detects anti-bot
  - Timeout: 300 seconds per ingestion request
  - Used in: `ingest_wechat.py` in `scrape_wechat_apify()` function

**Browser Automation (Fallback):**
- Chrome DevTools Protocol (CDP) via Playwright
  - Connection: Async Playwright over CDP at `BROWSER_CDP_URL`
  - Default endpoint: `http://127.0.0.1:9223`
  - Browser: Microsoft Edge (Windows) or Chrome/Chromium (Linux)
  - Trigger: When Apify fails or bot detection is suspected
  - Used in: `ingest_wechat.py` in `scrape_wechat_cdp()` function

## Data Storage

**Databases:**
- LightRAG Graph Database
  - Storage: Local file-based (KuzuDB backend)
  - Location: `~/.hermes/omonigraph-vault/lightrag_storage/`
  - Client: `lightrag.lightrag.LightRAG`
  - Operations: Insert documents, query with semantic search
  - Modes: local, global, hybrid, naive, mix
  - Connection: No external connection required (embedded)

- Cognee Memory Layer
  - Purpose: Session state, entity disambiguation, query pattern tracking
  - Client: Python package `cognee`
  - Configuration: Gemini provider via `cognee.config`
  - Backend: Local embeddings + Gemini API
  - No external database server required

**File Storage:**
- Local filesystem only
  - Article images: `~/.hermes/omonigraph-vault/images/{article_hash}/`
  - PDF images: Extracted to same directory structure
  - Metadata: `metadata.json` per article/PDF
  - Content: `final_content.md` with processed markdown
  - Entity buffer: `entity_buffer/` for batch processing
  - Canonical mapping: `canonical_map.json` for entity normalization

**Caching:**
- Disambiguation cache: In-memory Python dict in `cognee_wrapper.py`
  - Scope: Runtime only (lost on process restart)
  - Purpose: Cache canonical entity names to avoid redundant Cognee queries

## Authentication & Identity

**Auth Provider:**
- Custom: API key-based authentication
  - `GEMINI_API_KEY` - Bearer token for Google Gemini API
  - `APIFY_TOKEN` - Platform token for Apify
  - Loaded from: `~/.hermes/.env` file (not in `.env.example`, kept private)

**Implementation:**
- Environment variable loading via custom `load_env()` function in `config.py`
- Manual parsing of `.env` file format
- No OAuth, no session tokens, no user authentication

## Monitoring & Observability

**Error Tracking:**
- None detected
- Manual error handling via try-except blocks throughout codebase
- No integration with Sentry, DataDog, or similar services

**Logs:**
- Console logging: `logging` module used in `cognee_wrapper.py`
  - Logger: `cognee_wrapper` at INFO level
  - File logging: `cognee_batch_processor.py` writes to `/home/sztimhdd/OmniGraph-Vault/cognee_batch.log`

**Metrics:**
- No explicit metrics collection
- Implicit: Command-line output to stdout for ingestion progress

## CI/CD & Deployment

**Hosting:**
- Local machine deployment
- No cloud platform integration detected
- Designed for personal knowledge base on-machine

**CI Pipeline:**
- None detected
- Manual execution via command-line scripts

**Execution Model:**
- Subprocess invocation from AI agents (Openclaw, Hermes)
  - Example: `subprocess.run(["python", "kg_synthesize.py", question])`
  - Synchronous blocking calls expected

## Environment Configuration

**Required env vars:**
- `GEMINI_API_KEY` - Must be present (checked in multiple files)
- `APIFY_TOKEN` - Optional (graceful fallback to CDP if missing)
- `BROWSER_CDP_URL` - Optional (defaults to `http://127.0.0.1:9223`)

**Secrets location:**
- Primary: `~/.hermes/.env` (user home directory under Hermes project)
- Alternative: `.env` file in project root (used in multimodal_ingest.py)
- Not committed: `.gitignore` includes environment files

**API Quotas/Limits:**
- Google Gemini: Subject to Cloud Platform quotas
- Apify: Subject to subscription limits
- No client-side rate limiting implemented

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected
- Unidirectional: All calls are initiated by local scripts

## Content Sources

**Web Sources:**
- WeChat public accounts (via Apify + CDP)
  - Primary scraping target: `mp.weixin.qq.com`
  - Content: Articles, images, publish timestamps
  - Detection: Anti-bot verification pages trigger CDP fallback

- Local PDF files
  - Input: Via command-line arguments to `multimodal_ingest.py`
  - Processing: Page-by-page extraction with embedded image handling

- GitHub repositories (planned Phase 2)
  - API: GitHub REST API (no SDK currently integrated)
  - Content: README.md, docs/*.md, Issues, Discussions

- RSS feeds (planned Phase 2)
  - Library: `feedparser` (listed in requirements.txt, not yet used)
  - Pre-filtering: Gemini Flash for content classification

- Zhihu (planned Phase 2)
  - Method: CDP-based scraping (similar to WeChat)
  - Content: High-quality practitioner answers, comparisons, pitfall discussions

## Data Flow

**Ingestion Pipeline:**
```
Web Content (WeChat/PDF/RSS)
  ↓
Apify/CDP/Parser (extracts HTML/text)
  ↓
Image Download & Vision Description (Gemini Vision)
  ↓
HTML → Markdown Conversion
  ↓
Entity Extraction (Gemini)
  ↓
LightRAG Insertion (graph construction)
  ↓
Entity Buffer (async canonicalization)
  ↓
Cognee Disambiguation (batch processing)
  ↓
Canonical Map Update
```

**Query Pipeline:**
```
User Query
  ↓
Canonical Mapping (replace synonyms)
  ↓
Cognee Context Recall (historical memory)
  ↓
LightRAG Query (graph search: local/global/hybrid)
  ↓
Synthesis (Gemini LLM with context)
  ↓
Cognee Memory Update (remember synthesis)
  ↓
Output (Markdown + Image References)
```

## Integration Points with AI Agents

**Openclaw Integration:**
- Function: `query_kg(question: str) -> str`
- Mechanism: Subprocess call to `kg_synthesize.py`
- Returns: Synthesized markdown response

**Hermes Agent Integration:**
- Design: Agent-ready Python interfaces
- Functions:
  - `ingest_wechat.py` - Background content ingestion
  - `kg_synthesize.py` - Query synthesis for agent context
  - `query_lightrag.py` - Direct graph queries for debugging

---

*Integration audit: 2026-04-21*
