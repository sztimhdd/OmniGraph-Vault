# Technology Stack

**Analysis Date:** 2026-04-21

## Languages

**Primary:**
- Python 3.11+ - Entire application, core pipeline logic, ingestion, synthesis
- Python 3.12 - Virtual environment target (referenced in `cognee_wrapper.py`)

**Secondary:**
- Markdown - Documentation and content rendering (`.md` files, synthesis outputs)

## Runtime

**Environment:**
- Python 3.11+ interpreter
- Virtual environment: `venv/` (standard Python venv)
- OS-agnostic with Windows Edge CDP integration fallback

**Package Manager:**
- pip (Python package manager)
- Lockfile: `requirements.txt` (present, pinned dependencies)

## Frameworks

**Core Knowledge Graph:**
- LightRAG - Knowledge graph construction and querying engine
  - Location: Imported from `lightrag.lightrag` module
  - Used in: `ingest_wechat.py`, `multimodal_ingest.py`, `query_lightrag.py`, `kg_synthesize.py`
  - Provides: Graph storage, entity extraction, semantic search

**Memory & Context:**
- Cognee - Stateful memory layer for context tracking
  - Location: Python package via `import cognee`
  - Used in: `cognee_wrapper.py`, `cognee_batch_processor.py`, `kg_synthesize.py`
  - Provides: Session-aware memory, entity disambiguation, query pattern logging

**Testing:**
- pytest (implied from `tests/` directory structure with `verify_gate_*.py` files)

**Build/Dev:**
- No explicit build system (pure Python scripts)
- Environment: Python standard library + third-party packages

## Key Dependencies

**Critical:**
- google-genai - Google Gemini API client for LLM and vision
  - Version: Latest (google-genai)
  - API Key: `GEMINI_API_KEY` environment variable
  - Used for: LLM completions, embeddings, image descriptions
  - Models: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-embedding-001`, `gemini-3.1-flash-lite-preview`

- apify-client - Apify platform SDK for web scraping
  - Used in: `ingest_wechat.py`
  - Token: `APIFY_TOKEN` environment variable
  - Primary scraper for WeChat articles with bot detection handling

**Infrastructure:**
- playwright - Browser automation with CDP (Chrome DevTools Protocol) fallback
  - Async integration: `async_playwright()` in `ingest_wechat.py`
  - Fallback for Apify failures on bot-protected sites
  - Connection: `CDP_URL` (default: `http://127.0.0.1:9223`)

- beautifulsoup4 - HTML/XML parsing and DOM navigation
  - Used in: `ingest_wechat.py` for HTML-to-Markdown conversion
  - Dependency: Used with `html.parser` engine

- pymupdf (fitz) - PDF extraction
  - Used in: `multimodal_ingest.py`, `ingest_wechat.py`
  - Provides: Page text extraction, embedded image extraction, PDF metadata

- html2text - HTML to Markdown conversion
  - Used in: `ingest_wechat.py` in `process_content()` for content standardization

**Data & Storage:**
- lancedb - Vector database for embeddings (installed, usage in LightRAG)
- kuzu - Graph database backend (installed, used by LightRAG for graph storage)
- numpy - Numerical computing for embedding operations
  - Used in: `embedding_func()` returns `np.ndarray` with shape matching `embedding_dim`

**Image Processing:**
- Pillow (PIL) - Image file handling and processing
  - Used in: `describe_image()` for loading images before vision API calls

**Utilities:**
- python-dotenv - Environment variable loading from `.env` files
  - Manual implementation in `config.py` via `load_env()` function
  - Loads from: `~/.hermes/.env`

- nest-asyncio - Async event loop nesting for Jupyter-like environments
  - Applied in: `ingest_wechat.py`, `multimodal_ingest.py` via `nest_asyncio.apply()`

- requests - HTTP client for image/file downloads
  - Used in: `ingest_wechat.py` for downloading images from URLs

- watchdog - File system event monitoring (installed, likely for future batch processing)
  - Used in: `cognee_batch_processor.py` imports (FileSystemEventHandler, Observer)

- litellm - LLM provider abstraction layer
  - Used as: Intermediary between Cognee and Gemini API
  - Environment var: `LITELLM_API_KEY` set to `GEMINI_API_KEY`

- instructor - Structured output extraction for LLMs
  - Used by: Cognee for structured entity canonicalization

## Configuration

**Environment:**
- `.env.example` provided for reference
- Actual secrets loaded from: `~/.hermes/.env` (user home directory)
- Key required variables:
  - `GEMINI_API_KEY` - Google Gemini API credential
  - `APIFY_TOKEN` - Apify platform token (optional, fallback to CDP)
  - `BROWSER_CDP_URL` - Chrome DevTools Protocol endpoint (default: `http://127.0.0.1:9223`)

**Runtime Paths:**
- Base data directory: `~/.hermes/omonigraph-vault/` (user home)
- RAG working directory: `~/.hermes/omonigraph-vault/lightrag_storage/`
- Image storage: `~/.hermes/omonigraph-vault/images/`
- Synthesis output: `~/.hermes/omonigraph-vault/synthesis_output.md`
- Entity buffer: `entity_buffer/` directory for async processing
- Canonical mapping: `canonical_map.json` for entity normalization

**Build:**
- No build configuration files (pure Python, no compilation)
- Entry points are command-line scripts:
  - `ingest_wechat.py` - Main ingestion command
  - `kg_synthesize.py` - Query synthesis
  - `query_lightrag.py` - Direct graph queries
  - `multimodal_ingest.py` - PDF ingestion

## Platform Requirements

**Development:**
- Python 3.11+ interpreter
- Virtual environment support (`venv`)
- Windows Edge browser (for CDP fallback at `http://localhost:9223`)
- Linux/Mac: Chromium or Chrome with CDP support

**Production:**
- Python 3.11+ runtime
- Local HTTP server capability (port 8765 for image serving)
- CDP-enabled browser (Edge on Windows, Chrome/Chromium on Linux)
- Network access to:
  - Google Gemini API endpoints
  - Apify API (optional)
  - Target websites for scraping

---

*Stack analysis: 2026-04-21*
