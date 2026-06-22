# Technology Stack

## Languages
- Python 3.11+ - Entire application, core pipeline logic, ingestion, synthesis
- Markdown - Documentation and content rendering (`.md` files, synthesis outputs)

## Runtime
- Python 3.11+ interpreter
- Virtual environment: `venv/` (standard Python venv)
- OS-agnostic with Windows Edge CDP integration fallback
- pip (Python package manager)
- Lockfile: `requirements.txt` (present, pinned dependencies)

## Frameworks
- LightRAG - Knowledge graph construction and querying engine
- pytest (implied from `tests/` directory structure)
- No explicit build system (pure Python scripts)
- Environment: Python standard library + third-party packages

## Key Dependencies
- google-genai - Google Gemini API client (used in vision cascade fallback only — primary LLM is DeepSeek via openai client; primary vision is SiliconFlow via openai client)
- google-cloud-aiplatform - Vertex AI SDK + SA JSON authentication (production embedding via `gemini-embedding-2` on `GOOGLE_CLOUD_LOCATION=global` since 2026-05-17 aim-1 cutover)
- openai - openai-compatible client used for DeepSeek (primary LLM) + SiliconFlow (primary vision)
- apify-client (3.0+) - Apify platform SDK for web scraping (dual-compat with 2.x typed `Run` per a5ccc0c)
- playwright - Browser automation with CDP (Chrome DevTools Protocol) fallback
- beautifulsoup4 - HTML/XML parsing and DOM navigation
- pymupdf (fitz) - PDF extraction
- html2text - HTML to Markdown conversion
- lancedb - Vector database for embeddings (installed, usage in LightRAG)
- kuzu - Graph database backend (installed, used by LightRAG for graph storage)
- numpy - Numerical computing for embedding operations
- Pillow (PIL) - Image file handling and processing
- python-dotenv - Environment variable loading from `.env` files
- nest-asyncio - Async event loop nesting for Jupyter-like environments
- requests - HTTP client for image/file downloads
- watchdog - File system event monitoring (installed, likely for future batch processing)
- litellm - LLM provider abstraction layer
- instructor - Structured output extraction for LLMs

## Configuration
- `.env.example` provided for reference
- Actual secrets loaded from: `~/.hermes/.env` (user home directory)
- Key required variables:
- Base data directory: `~/.hermes/omonigraph-vault/` (user home)
- RAG working directory: `~/.hermes/omonigraph-vault/lightrag_storage/`
- Image storage: `~/.hermes/omonigraph-vault/images/`
- Synthesis output: `~/.hermes/omonigraph-vault/synthesis_output.md`
- Entity buffer: `entity_buffer/` directory for async processing
- Canonical mapping: `canonical_map.json` for entity normalization
- No build configuration files (pure Python, no compilation)
- Entry points are command-line scripts:

## Platform Requirements
- Python 3.11+ interpreter
- Virtual environment support (`venv`)
- Windows Edge browser (for CDP fallback at `http://localhost:9223`)
- Linux/Mac: Chromium or Chrome with CDP support
- Python 3.11+ runtime
- Local HTTP server capability (port 8765 for image serving)
- CDP-enabled browser (Edge on Windows, Chrome/Chromium on Linux)
- Network access to:
