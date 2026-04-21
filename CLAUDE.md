# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

OmniGraph-Vault is a personal knowledge base for **OpenClaw** and **Hermes Agent** AI assistants. It ingests web content (WeChat articles, PDFs) into a **LightRAG** knowledge graph enriched with **Cognee** async memory, then exposes that graph as agent skills.

**Tech stack:** Python 3.11+, LightRAG (KG engine), Cognee (memory layer), Google Gemini 2.5 Pro/Flash (LLM + vision), Apify + Playwright CDP (scraping), local HTTP image server (port 8765)

**Runtime data:** `~/.hermes/omonigraph-vault/` (note: the directory name has a typo — `omonigraph` not `omnigraph` — this is the actual path used in `config.py` and must be preserved)

---

## Common Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate   # Linux/macOS
python -m venv venv && venv\Scripts\activate       # Windows
pip install -r requirements.txt

# Verify imports
python -c "import lightrag; print('LightRAG OK')"
python -c "import cognee; print('Cognee OK')"

# Ingest a WeChat article (dual-path: Apify primary, CDP fallback)
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# Ingest a local PDF with image extraction
python multimodal_ingest.py "/path/to/document.pdf"

# Query with Cognee memory context (modes: naive, local, global, hybrid, mix)
python kg_synthesize.py "What are the latest trends in AI Agents?" hybrid

# Direct LightRAG query (no Cognee, for debugging)
python query_lightrag.py "Explain the architecture of OmniGraph-Vault"

# List graph entities
python list_entities.py

# Start image server (background)
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &

# Run entity canonicalization batch (polls entity_buffer/)
python cognee_batch_processor.py

# Verification gates (manual test scripts, not pytest)
python tests/verify_gate_a.py   # Cognee remember()
python tests/verify_gate_b.py   # Cognee recall() + search()
python tests/verify_gate_c.py   # Entity disambiguation
```

No pytest framework, no linting, no CI configured yet. Tests are manual verification scripts that hit live APIs.

---

## Architecture

### Ingestion Flow

```
URL → ingest_wechat.py
  ├─ Apify (primary) or CDP/Playwright (fallback) → HTML
  ├─ BeautifulSoup + html2text → Markdown
  ├─ Image download → ~/.hermes/omonigraph-vault/images/{hash}/
  ├─ Gemini Vision → image descriptions appended to content
  ├─ Gemini Flash → entity extraction → entity_buffer/{hash}_entities.json
  └─ LightRAG ainsert() → knowledge graph stored in lightrag_storage/
```

Entity canonicalization runs **async and decoupled** via `cognee_batch_processor.py`, which polls `entity_buffer/` and writes to `canonical_map.json` atomically (tmp → rename).

### Query/Synthesis Flow

```
Query → kg_synthesize.py
  ├─ Load canonical_map.json → normalize entity names in query
  ├─ LightRAG aquery(mode=hybrid) → graph retrieval
  ├─ cognee_wrapper.recall_previous_context() → past query memory
  ├─ Combined prompt → Gemini generates Markdown report
  ├─ cognee_wrapper.remember_synthesis() → store for future recall
  └─ Output → stdout + ~/.hermes/omonigraph-vault/synthesis_output.md
```

### Key Integration Points

**LightRAG** — used in `ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`, `query_lightrag.py`. Configured with Gemini model wrappers (`gemini_model_complete`, `gemini_embed`). Storage: `~/.hermes/omonigraph-vault/lightrag_storage/`.

**Cognee** — wrapped by `cognee_wrapper.py` (provides `remember_synthesis()`, `recall_previous_context()`, `disambiguate_entities()`). Batch processing in `cognee_batch_processor.py`. Must be configured via env vars *before* import: `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-flash`, `EMBEDDING_PROVIDER=gemini`.

**config.py** — loads `~/.hermes/.env` at import time. All modules import it for `BASE_DIR`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `CDP_URL`. The env loader does *not* overwrite existing env vars.

### Environment Variables

| Variable | Required | Used For |
|---|---|---|
| `GEMINI_API_KEY` | Yes | All LLM, vision, and embedding calls |
| `APIFY_TOKEN` | No | Primary scraping (falls back to CDP) |
| `CDP_URL` | No | Playwright CDP fallback (default: `http://localhost:9223`) |

Set in `~/.hermes/.env`. Cognee-specific vars (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, etc.) are hardcoded in each script that uses Cognee.

---

## Development Conventions

- **Atomic writes** for `canonical_map.json`: always write `.tmp` then rename
- **Cognee is async** — never block the ingestion fast-path on any Cognee operation
- **LLM output never goes directly into the graph** — always validate against real sources first
- **Entity buffer idempotency** — write `.processed` marker after each batch run, never delete originals
- **Image server must be running** for synthesized reports to render correctly (port 8765)

---

## OpenClaw / Hermes Skill Writing Standards

> Synthesized from: docs.openclaw.ai/tools/creating-skills, dench.com/blog/openclaw-skill-writing-advanced,
> hermes-agent.ai/blog/hermes-agent-skills-guide, lushbinary.com/blog/hermes-agent-custom-skills-development-guide,
> hermes-agent.nousresearch.com/docs/user-guide/features/skills

### Skill Directory Structure

Every skill is a **directory**, not a single file:

```
my-skill/
├── SKILL.md           # Agent-facing instructions + metadata (required)
├── references/        # Docs the agent reads on-demand (Level 2 loading)
│   └── api-docs.md
├── scripts/           # Shell scripts the agent executes via exec
│   └── run-query.sh
└── README.md          # Human-facing: install guide, examples
```

`references/` = documents the agent reads. `scripts/` = scripts the agent runs. Never mix.

### SKILL.md Frontmatter

```yaml
---
name: omnigraph_query          # snake_case, unique, required
description: >-                # one-line, shown to agent at Level 0 — accuracy is critical
  Query the OmniGraph-Vault knowledge graph by natural language.
triggers:                      # Hermes auto-match phrases
  - "search the knowledge base"
  - "what do I know about"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---
```

Required: `name`, `description`. Optional but impactful: `triggers`, `metadata.openclaw.requires.*`.

### Progressive Disclosure (Hermes Token Efficiency)

```
Level 0: skills_list()           → name + description only (~3k tokens for full catalog)
Level 1: skill_view(name)        → full SKILL.md content
Level 2: skill_view(name, path)  → specific file in references/
```

Keep SKILL.md lean. Put heavy reference material in `references/` — it stays at Level 2 until explicitly requested.

### OpenClaw Loading Precedence

| Location | Precedence | Scope |
|---|---|---|
| `<workspace>/skills/` | Highest | Per-agent |
| `<workspace>/.agents/skills/` | High | Per-workspace agent |
| `~/.agents/skills/` | Medium | Shared agent profile |
| `~/.openclaw/skills/` | Medium | Shared (all agents) |
| Bundled | Low | Global |
| `skills.load.extraDirs` | Lowest | Custom shared |

Reload: `/new` in chat or `openclaw gateway restart`.

### Instruction Writing Patterns

**1. Explicit decision trees, not vague instructions.** Write if/then branches for every trigger scenario and every "when NOT to trigger" case. The agent should never guess.

**2. Focused scope.** One skill per pipeline stage (`omnigraph_ingest`, `omnigraph_query`, `omnigraph_synthesize`, `omnigraph_status`, `omnigraph_manage`), not a monolithic skill.

**3. Guard clauses before destructive actions.** Any skill that deletes/overwrites KG data must: show what will change, ask for explicit confirmation, wait for "yes"/"y"/"confirm", and never batch-delete >10 nodes without listing them.

**4. Consistent output formatting.** Define in the skill body: >5 items = markdown table, ≤5 = bullet list, COUNT = plain number, errors = `⚠️ [Type]: [What happened]. [What to do next].`

**5. Environment variables, not hardcoded paths.** Reference env vars by name in the skill body (`GEMINI_API_KEY`, `OMNIGRAPH_DATA_DIR`, `OMNIGRAPH_IMAGE_PORT`).

**6. Skill composition via references.** Skills can't call each other directly. Document dependencies explicitly: "For ingestion, see the `omnigraph_ingest` skill."

### Planned Skills for This Project

| Skill | Description | Triggers |
|---|---|---|
| `omnigraph_ingest` | Ingest a URL into the knowledge graph | "add this to my kb", "ingest", "save this article" |
| `omnigraph_query` | Query the KG by natural language | "what do I know about", "search my kb" |
| `omnigraph_synthesize` | Generate a synthesized report from the KG | "write a report on", "summarize what I know about" |
| `omnigraph_status` | Check pipeline health and graph stats | "kg status", "how many nodes" |
| `omnigraph_manage` | List, delete, or re-index KG entities | "remove entity", "list all tools", "reindex" |

### Testing Skills

- `openclaw agent --message "<trigger phrase>"` exercises the golden path
- Test with missing env vars — guard clause should fire cleanly
- Test destructive actions — confirmation prompt must appear
- Test edge cases (empty result, ambiguous entity) — output format must hold
- `openclaw skills list` to verify skill appears with correct description

### Publishing

```bash
# OpenClaw → ClawHub
openclaw skills publish my-skill --to clawhub

# Hermes → GitHub
hermes skills publish skills/omnigraph-query --to github --repo sztimhdd/OmniGraph-Vault
```

SkillHub reviewers check: metadata correctness, focused scope, guard clauses on destructive ops, references/scripts separation, README.md present.

### Agent-Created Skills (Hermes Self-Improvement)

After 5+ tool calls on a complex task, Hermes evaluates whether to auto-create a skill at `~/.hermes/skills/[category]/`. Let these accumulate during development — they capture real usage patterns. Review periodically and promote good ones to the project skills directory.

---

## Lessons Learned

- Cognee batch operations silently drop entities if the buffer path isn't checked for `.processed` markers — always verify idempotency
- The runtime data directory is `omonigraph-vault` (typo is baked into config.py and deployed environments — do not "fix" it without a coordinated migration)

<!-- GSD:project-start source:PROJECT.md -->
## Project

**OmniGraph-Vault**

A local, graph-based personal knowledge base that gives Hermes Agent (and Openclaw) persistent memory over articles and documents. You drop in a WeChat article URL or PDF; the vault scrapes it, extracts entities and images, indexes everything into LightRAG, and surfaces it back on demand via two skills: one to ingest content, one to answer questions.

**Core Value:** When Hermes sees "add this to my KB" or "what do I know about X?" it calls the right script and gets a useful answer back.

### Constraints

- **Privacy**: All data stays local; no SaaS KB subscriptions; only Gemini API + Apify make external calls
- **Platform**: Windows-primary (Edge for CDP); Cognee requires Python 3.12 venv per wrapper
- **Single user**: No auth, no isolation required — personal tool only
- **Stack**: Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ - Entire application, core pipeline logic, ingestion, synthesis
- Python 3.12 - Virtual environment target (referenced in `cognee_wrapper.py`)
- Markdown - Documentation and content rendering (`.md` files, synthesis outputs)
## Runtime
- Python 3.11+ interpreter
- Virtual environment: `venv/` (standard Python venv)
- OS-agnostic with Windows Edge CDP integration fallback
- pip (Python package manager)
- Lockfile: `requirements.txt` (present, pinned dependencies)
## Frameworks
- LightRAG - Knowledge graph construction and querying engine
- Cognee - Stateful memory layer for context tracking
- pytest (implied from `tests/` directory structure with `verify_gate_*.py` files)
- No explicit build system (pure Python scripts)
- Environment: Python standard library + third-party packages
## Key Dependencies
- google-genai - Google Gemini API client for LLM and vision
- apify-client - Apify platform SDK for web scraping
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module scripts: lowercase with underscores (`cognee_wrapper.py`, `multimodal_ingest.py`, `kg_synthesize.py`)
- Configuration: `config.py`
- Test verification scripts: `verify_gate_*.py` (e.g., `verify_gate_a.py`)
- Async functions: lowercase with underscores, descriptive names (`disambiguate_entities`, `ingest_pdf`, `synthesize_response`, `query_and_synthesize`)
- Helper functions: lowercase with underscores (`load_env`, `describe_image`, `llm_model_func`, `embedding_func`)
- Main entry points: `main()` in `if __name__ == "__main__"` blocks
- Constants: UPPERCASE with underscores (`GEMINI_API_KEY`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `VENV_SITE_PACKAGES`)
- Local variables: lowercase with underscores (`query_text`, `response`, `canonical_map`, `pdf_path`)
- Cache/state: prefixed with underscore for internal use (`_disambiguation_cache`)
- Type hints used in function signatures: `list[str]`, `np.ndarray`, `dict`
- Return types documented in async functions: `async def function_name(...) -> ReturnType:`
## Code Style
- No explicit formatter configured (black/ruff not detected)
- Manual formatting conventions observed:
- No `.eslintrc`, `.pylintrc`, or similar configuration found
- No linting tool requirements detected in `requirements.txt`
- Manual code review likely the primary quality control
## Import Organization
- None detected. Full module paths used throughout (`from lightrag.lightrag import LightRAG`).
- Local modules imported directly by name (`import cognee_wrapper`).
## Error Handling
- Return `None` on non-critical failures: `cognee_wrapper.py` functions
- `sys.exit(1)` on critical startup failures (missing API keys, imports)
- Print warnings and continue on recoverable errors
## Logging
- Module-level logger: `logger = logging.getLogger("module_name")`
- Levels used: `INFO`, `ERROR`, `WARNING`
- Basic configuration: `logging.basicConfig(level=logging.INFO)`
- File handlers for batch processes: `logging.FileHandler("/path/to/logfile.log")`
- Heavy use of `print()` for console output (not using logging in all cases)
- Examples: `query_lightrag.py`, `multimodal_ingest.py` use both print and logging
- Convention: Use `print()` for user-facing output, `logger` for operational logs
## Comments
- Inline comments for non-obvious logic (rare in this codebase)
- TODO/FIXME comments: None detected
- Configuration comments: Yes (e.g., "Force standard Gemini API mode")
- Minimal docstrings present
- Examples:
- Not consistently applied across all functions
## Function Design
- Functions range from 5 lines to 50+ lines
- Typical: 15-35 lines for business logic
- Larger functions: `ingest_pdf()` (~55 lines), `ingest_wechat()` (~150 lines)
- Use keyword arguments with defaults: `mode: str = "naive"`
- Environment-based configuration common (from `os.environ`)
- Async functions accept `**kwargs` for flexibility
- Early returns on error conditions
- Multiple return paths (success/failure):
## Module Design
- No explicit `__all__` definitions detected
- Functions defined at module level are importable
- Internal module state: `_disambiguation_cache = {}`
- Not used. Each module is self-contained.
- `config.py` serves as shared configuration module.
- Configuration loaded at module import time (top-level code execution)
- Example from `cognee_wrapper.py` (lines 7-45): Environment variables, logging setup, and module imports all happen at import time
- This means configuration is not testable without modifying environment
## Async Patterns
- `nest_asyncio.apply()` used to allow nested event loops (development/Jupyter compatibility)
## Antipatterns Observed
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Asynchronous pipeline-based processing (all I/O operations use `async`/`await`)
- Dual-fallback scraping strategy (primary + redundant methods)
- Pluggable LLM backends (Gemini for both generation and embeddings)
- Decoupled memory layer (Cognee) for entity canonicalization and context recall
- Local-first data persistence (all artifacts stored in `~/.hermes/kg-vault/`)
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
- Purpose: Track conversation history, learn entity aliases, deduplicate synonyms
- Location: `cognee_wrapper.py`, `cognee_batch_processor.py`
- Contains: Entity disambiguation, past query recall, synthesis memory storage
- Depends on: Cognee library with Gemini backend
- Used by: Synthesis layer to add historical context and entity normalization
- Purpose: Answer queries by combining LightRAG retrieval with memory context
- Location: `kg_synthesize.py`, `query_lightrag.py`
- Contains: Custom prompt engineering, response generation, Cognee integration
- Depends on: LightRAG queries + Cognee context recall
- Used by: External agents (Openclaw, Hermes Agent) via subprocess calls
- Purpose: Centralized path and secret management
- Location: `config.py`
- Contains: Environment loading from `~/.hermes/.env`, base paths for storage
- Depends on: OS environment variables, pathlib
- Used by: All other layers during initialization
## Data Flow
- **LightRAG index**: Persistent in `~/.hermes/kg-vault/lightrag_storage/` (graph edges, entities, embeddings)
- **Cognee memory**: Persistent in Cognee's internal DB (conversation state, entity aliases)
- **Canonical map**: JSON file at `~/.hermes/kg-vault/canonical_map.json` (entity normalization rules)
- **Entity buffer**: Temporary JSON files in `entity_buffer/` directory, processed async by batch processor
- **Images**: Local copies at `~/.hermes/kg-vault/images/{article_hash}/` with metadata.json + final_content.md
## Key Abstractions
- Purpose: Represents a software tool or framework in the knowledge graph
- Examples: LightRAG, Cognee, n8n, Cursor (as described in `specs/OMNIGRAPH_VISION_Statement.md`)
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
- Invokes: Apify client, CDP browser, Gemini Vision for images, LightRAG insertion, Cognee entity buffering
- Location: Project root
- Triggers: `python kg_synthesize.py "<query>" [mode]` (subprocess call from agent)
- Responsibilities: Answer user queries with synthesis
- Returns: Markdown response to stdout and file at `~/.hermes/kg-vault/synthesis_output.md`
- Location: Project root
- Triggers: `python query_lightrag.py "<query>"` (direct LightRAG query without Cognee)
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
- Cognee operations: Always wrapped in try/except, warnings logged, main flow unaffected (async + non-blocking)
- LightRAG queries: Retry loop (3 attempts with 5s backoff) before raising exception
```python
```
## Cross-Cutting Concerns
- Print-based for CLI scripts (no structured logging framework)
- File-based for batch processor: `cognee_batch.log` at `/home/sztimhdd/OmniGraph-Vault/cognee_batch.log`
- Input URL validation: Basic `startswith('http')` checks for images
- File existence checks before processing (PDFs, env files)
- API response status code checks (HTTP 200 for image downloads)
- Gemini API: Via environment variable `GEMINI_API_KEY`
- Apify: Via `APIFY_TOKEN` (optional, non-critical fallback)
- CDP: Via `CDP_URL` environment variable (default `http://localhost:9223`)
- Cognee/LiteLLM: Credentials sourced from Gemini API key
- Image downloads: Atomic write to temp, no partial files left behind
- Canonical map: Atomic JSON write (write to `.tmp`, then `os.rename()`)
- Entity buffer: Explicit `.processed` marker after each file processed (idempotent)
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
