# Codebase Structure

**Analysis Date:** 2026-04-21

## Directory Layout

```
OmniGraph-Vault/
├── config.py                    # Centralized environment & path configuration
├── ingest_wechat.py             # Primary ingestion: WeChat articles + fallback CDP
├── kg_synthesize.py             # Query synthesis with Cognee memory integration
├── query_lightrag.py            # Direct LightRAG queries (debugging)
├── cognee_wrapper.py            # Cognee API wrapper (entity canonicalization, recall)
├── cognee_batch_processor.py    # Async batch processor for entity buffers
├── multimodal_ingest.py         # PDF ingestion with image extraction
├── init_cognee.py               # Cognee initialization (minimal setup)
├── setup_cognee.py              # Cognee setup utilities
├── list_entities.py             # CLI tool to inspect ingested entities
├── kg_query.py                  # Alias/helper for query_lightrag.py (if used)
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment variables
├── .gitignore                   # Git exclusions (includes .env, venv, etc.)
├── README.md                    # Project documentation (English & Chinese)
├── Deploy.md                    # Deployment guide
├── .planning/
│   └── codebase/
│       ├── ARCHITECTURE.md      # (This layer's design)
│       └── STRUCTURE.md         # (This directory map)
├── specs/
│   ├── OMNIGRAPH_VISION_Statement.md   # Phase 2-4 roadmap & tool-node schema
│   ├── PRD_TDD.md                      # Product requirements & test-driven specs
│   └── [other design docs]
└── tests/
    ├── verify_gate_a.py         # Gate A: Cognee integration test
    ├── verify_gate_b.py         # Gate B: LightRAG + Gemini integration test
    └── verify_gate_c.py         # Gate C: End-to-end ingestion pipeline test
```

## Directory Purposes

**Project Root:**
- Purpose: Command-line entry points for all major workflows
- Contains: Executable scripts that users call directly
- Key files: `ingest_*.py`, `kg_*.py`, `config.py`

**.planning/codebase/:**
- Purpose: GSD codebase mapping documentation (architecture analysis, structure reference)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md
- Committed: Yes (documentation only, no secrets)

**specs/:**
- Purpose: Design specifications, PRDs, vision statements, roadmaps
- Contains: Long-term architectural decisions, phase breakdowns, schema definitions
- Key files: `OMNIGRAPH_VISION_Statement.md` (Phase 2-4 roadmap), `PRD_TDD.md` (TDD specs)

**tests/:**
- Purpose: Gate validation tests (integration-focused, not unit tests)
- Contains: Verification scripts for major subsystems
- Key files: `verify_gate_a.py` (Cognee), `verify_gate_b.py` (LightRAG), `verify_gate_c.py` (pipeline)
- Note: Tests are integration-level; no unit test framework (pytest) currently used

**Runtime Data (NOT in repo, stored locally):**
- Location: `~/.hermes/kg-vault/` (home directory)
  - `lightrag_storage/`: LightRAG graph database (edges, entities, embeddings)
  - `images/`: Local copies of all ingested images organized by article hash
  - `synthesis_output.md`: Query response output file
  - `canonical_map.json`: Entity normalization rules (raw → canonical)
  - `entity_buffer/`: Temporary JSON files for async batch processing (`.processed` markers)
  - `.env`: Secrets file (loaded by config.py)

## Key File Locations

**Entry Points:**

| Script | Purpose | Command |
|--------|---------|---------|
| `config.py` | Environment & paths | Imported, not executed directly |
| `ingest_wechat.py` | WeChat article ingestion | `python ingest_wechat.py "<url>"` |
| `multimodal_ingest.py` | PDF ingestion | `python multimodal_ingest.py "<pdf_path>"` |
| `kg_synthesize.py` | Query synthesis | `python kg_synthesize.py "<query>" [mode]` |
| `query_lightrag.py` | Direct KG query | `python query_lightrag.py "<query>"` |
| `cognee_batch_processor.py` | Entity batch processor | `python cognee_batch_processor.py` (daemon) |
| `list_entities.py` | Entity inspection | `python list_entities.py` (utility) |

**Configuration:**

| File | Purpose | Contains |
|------|---------|----------|
| `.env.example` | Template | Example API keys and paths |
| `~/.hermes/.env` | Runtime secrets | GEMINI_API_KEY, APIFY_TOKEN, etc. |
| `config.py` | Centralized config | `BASE_DIR`, `RAG_WORKING_DIR`, `load_env()` function |

**Core Logic:**

| File | Responsibility |
|------|-----------------|
| `ingest_wechat.py` | Scraping (Apify + CDP), image processing, LightRAG insertion |
| `multimodal_ingest.py` | PDF extraction, image description, LightRAG insertion |
| `kg_synthesize.py` | Query synthesis with Cognee memory layer |
| `query_lightrag.py` | Direct LightRAG queries (bypasses Cognee) |
| `cognee_wrapper.py` | Cognee API abstractions (entity canonicalization, recall) |
| `cognee_batch_processor.py` | Async polling of entity buffer, canonical map updates |

**Testing:**

| File | Scope |
|------|-------|
| `tests/verify_gate_a.py` | Cognee integration (memory layer functional test) |
| `tests/verify_gate_b.py` | LightRAG + Gemini (graph + LLM functional test) |
| `tests/verify_gate_c.py` | End-to-end pipeline (full ingestion flow) |

## Naming Conventions

**Files:**

- Ingestion scripts: `ingest_*.py` (e.g., `ingest_wechat.py`, `multimodal_ingest.py`)
- Query scripts: `query_*.py` or `*_synthesize.py` (e.g., `query_lightrag.py`, `kg_synthesize.py`)
- Wrapper modules: `*_wrapper.py` (e.g., `cognee_wrapper.py`)
- Processor modules: `*_processor.py` (e.g., `cognee_batch_processor.py`)
- Configuration: `config.py` (no prefix)
- Setup utilities: `setup_*.py` or `init_*.py` (e.g., `setup_cognee.py`, `init_cognee.py`)

**Directories:**

- `spec/`: Design specifications (no suffix)
- `tests/`: Test files (no prefix, just descriptive name)
- `.planning/`: GSD mapping output (dot prefix for hidden directory)
- Runtime data: `~/.hermes/kg-vault/` (flat structure with descriptive names: `lightrag_storage/`, `images/`, `entity_buffer/`)

**Python Functions & Classes:**

- Async functions: Prefix with `async def` (e.g., `async def ingest_article()`, `async def synthesize_response()`)
- Scraping methods: Named by source (e.g., `scrape_wechat_apify()`, `scrape_wechat_cdp()`)
- Processing steps: Verb-noun pattern (e.g., `process_content()`, `describe_image()`, `extract_entities()`)
- Internal helpers: Lowercase, snake_case (e.g., `load_env()`)

## Where to Add New Code

**New Ingestion Source (e.g., RSS, GitHub, Zhihu):**
- Primary code: Create `ingest_<source>.py` in project root (follow `ingest_wechat.py` pattern)
- Tests: Add `tests/verify_gate_<source>.py` for integration test
- Config: Add necessary env vars to `.env.example` and `config.py` if paths differ
- Entry point: Callable as `python ingest_<source>.py "<url_or_path>"`
- Expected output: Content inserted into LightRAG, entities buffered for async processing

**New Query Mode or Synthesis Strategy:**
- Primary code: Extend `kg_synthesize.py` or create new `query_<strategy>.py`
- Logic location: New function in existing module (e.g., `async def synthesize_response_with_<mode>()`)
- Cognee integration: Add new wrapper function in `cognee_wrapper.py` if needed
- Testing: Add scenario to `tests/verify_gate_c.py` or new integration test

**New Processing/Batch Job:**
- Primary code: Create `<task>_processor.py` in project root (follow `cognee_batch_processor.py` pattern)
- Logging: Use file-based logging (see example in `cognee_batch_processor.py`)
- Runtime data: Create subdirectory under `~/.hermes/kg-vault/<task_name>/` as needed
- Entry point: Callable as `python <task>_processor.py` or as scheduled daemon

**Utilities & Helpers:**
- Shared functions: Add to `config.py` if environment/path-related, else create `utils.py`
- Cognee helpers: Add to `cognee_wrapper.py`
- LightRAG helpers: Add new module `lightrag_utils.py` if extending RAG functionality
- CLI tools: Create as `<tool_name>.py` in project root (e.g., `list_entities.py`)

**Test Coverage:**
- Integration tests: Add to `tests/verify_gate_<letter>.py` files
- New subsystem gates: Create `tests/verify_gate_<letter>.py` with descriptive imports and async main()
- No pytest framework currently in use — follow manual async testing pattern

## Special Directories

**~/.hermes/kg-vault/ (Runtime Data):**
- Purpose: Persistent storage separate from source code
- Generated: Yes (created by scripts at first run)
- Committed: No (local machine only, not in git)
- Structure:
  ```
  ~/.hermes/kg-vault/
  ├── lightrag_storage/      # LightRAG graph database (opaque binary/text)
  ├── images/                # Article images organized as {article_hash}/{i}.jpg
  │   └── {article_hash}/
  │       ├── 0.jpg
  │       ├── 1.jpg
  │       ├── metadata.json  # Article metadata (title, URL, images list)
  │       └── final_content.md  # Full markdown with image descriptions
  ├── entity_buffer/         # Temporary JSON files for async processing
  │   ├── {hash}_entities.json
  │   └── {hash}_entities.json.processed
  ├── canonical_map.json     # Entity alias normalization rules
  ├── synthesis_output.md    # Query response output
  └── cognee_batch.log       # Batch processor logs
  ```

**specs/ (Design Documentation):**
- Purpose: Long-term roadmap, architectural decisions, schema definitions
- Generated: No (manually written by team)
- Committed: Yes
- Key docs:
  - `OMNIGRAPH_VISION_Statement.md`: Phase 2-4 roadmap (multi-source ingestion, cross-validation, gap detection)
  - `PRD_TDD.md`: Product requirements with TDD approach

**.planning/codebase/ (GSD Mapping Output):**
- Purpose: Architecture and structure analysis for code generation tools
- Generated: Yes (output by `/gsd:map-codebase` command)
- Committed: Yes (reference documentation)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md

---

*Structure analysis: 2026-04-21*
