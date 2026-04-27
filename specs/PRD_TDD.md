# OmniGraph-Vault: PRD & TDD Document

**Product:** OmniGraph-Vault – Personal Knowledge Base for AI Agents  
**Target Users:** Developers and researchers using Openclaw, Hermes Agent, or similar AI assistant frameworks.  
**Version:** 1.3
**Last Updated:** 2026-04-27  

---

## 1. Product Vision

### 1.1 Problem Statement
AI agents (Openclaw, Hermes Agent, etc.) excel at task execution but lack
**persistent, structured memory** across sessions. They cannot:
- Retain learned knowledge between conversations.
- Maintain a personal, evolving model of the user's interests and domain context.
- Access rich multimodal content (text + images) in a locally controlled,
  private store.

### 1.2 Solution
OmniGraph-Vault is a **local, graph-based knowledge base** that:
- **Ingests** web content (WeChat articles, blogs, docs) and local documents
  (PDFs) into a multimodal knowledge graph.
- **Stores** all data (text, images, metadata) on-premise, with no external
  SaaS dependencies.
- **Integrates** seamlessly with AI agents via simple Python APIs, providing
  long-term memory and contextual intelligence.
- **Evolves** over time through a decoupled async memory layer (Cognee) that
  canonicalizes entities and tracks query patterns without blocking ingestion.

### 1.3 Core Value Propositions
- **Agent-Ready Intelligence**: Structured knowledge retrieval for more
  context-aware agent responses.
- **Privacy by Design**: All data stays on the user's machine; no cloud
  knowledge-base subscriptions.
- **Multimodal Richness**: Images are downloaded, described by Gemini Vision,
  and served locally—enabling visual context in agent answers.
- **Stateful Learning**: Cognee async layer tracks user preferences, merges
  synonymous concepts, and improves recall over multiple sessions without
  blocking the ingestion fast-path.
- **Canonical KOL Registry**: Version-controlled JSON registry (`docs/wechat_kol_registry.json`)
  with canonical name → 微信号 → FakeID mapping, tags, and source provenance — eliminating
  hardcoded account lists in ingestion scripts.
- **Self-Healing Scraper**: Dual-path Apify → CDP fallback survives WeChat
  anti-bot measures automatically.

---

## 2. Functional Requirements

### 2.1 Ingestion Pipeline
| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-1 | Scrape WeChat public-account articles (text + images) via Apify | Must | ✅ Implemented |
| FR-2 | Fallback to CDP (Windows Edge via remote debugging) when Apify fails | Must | ✅ Implemented |
| FR-3 | Download images to local storage (`~/.hermes/kg-vault/images/`) | Must | ✅ Implemented |
| FR-4 | Generate semantic descriptions for every image via Gemini Vision | Must | ✅ Implemented |
| FR-5 | Index text content as a knowledge graph (LightRAG) | Must | ✅ Implemented |
| FR-6 | Write extracted raw entities to `entity_buffer/` for async processing | Must | ✅ Implemented |
| FR-7 | Ingest PDF documents (text + embedded images) via `multimodal_ingest.py` | Must | ✅ Implemented |
| FR-8 | Support batch ingestion of multiple URLs | Should | 🔄 Planned |

### 2.2 Knowledge Graph & Memory
| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-9 | Store entities, relationships, and concepts in a queryable graph (LightRAG) | Must | ✅ Implemented |
| FR-10 | Async entity canonicalization via `cognee_batch_processor.py` | Must | ✅ Implemented |
| FR-11 | Maintain `canonical_map.json` with atomic write (tmp → rename) | Must | ✅ Implemented |
| FR-12 | Session-aware query memory via Cognee `remember()` / `recall()` | Must | ✅ Implemented |
| FR-13 | Enable hybrid retrieval (vector + graph) for complex queries | Must | ✅ Implemented |
| FR-14 | Provide a direct query API (`query_lightrag.py`) with mode support (naive / local / global / hybrid) | Must | ✅ Implemented |
| FR-15 | Support incremental updates without full graph rebuild | Should | 🔄 Planned |

### 2.3 Synthesis & Reporting
| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-16 | Generate synthesized Markdown reports from KG retrieval | Must | ✅ Implemented |
| FR-17 | Embed local image URLs (`http://localhost:8765/...`) inline in reports | Must | ✅ Implemented |
| FR-18 | Apply `canonical_map.json` to normalize query entities before retrieval | Must | ✅ Implemented |
| FR-19 | Allow user-defined synthesis prompts | Must | ✅ Implemented |
| FR-20 | Deliver reports via Telegram Bot API as `.md` file attachment | Must | ✅ Implemented |

### 2.4 AI-Agent Integration
| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-21 | Expose Python functions for ingestion, query, and synthesis | Must | ✅ Implemented |
| FR-22 | Provide integration examples for Openclaw / Hermes Agent | Must | ✅ Implemented |
| FR-23 | Support webhook-based ingestion (Telegram → OmniGraph-Vault) | Could | 🔄 Future |
| FR-24 | REST API for remote agent calls | Could | 🔄 Future |

### 2.5 Configuration & Operations
| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-25 | Centralized configuration (`config.py`) for paths and API keys | Must | ✅ Implemented |
| FR-26 | Separate runtime data (`~/.hermes/kg-vault/`) from source code | Must | ✅ Implemented |
| FR-27 | Background image server (port 8765) for local media serving | Must | ✅ Implemented |
| FR-28 | Cognee batch processor health log (`cognee_batch.log`) | Must | ✅ Implemented |
| FR-29 | Scheduled or trigger-based Cognee batch sync (≤1x/day or on buffer threshold) | Should | 🔄 Planned |
| FR-30 | Comprehensive logging and error monitoring | Should | 🔄 Planned |
| FR-31 | Maintain canonical WeChat KOL registry (`docs/wechat_kol_registry.json`) as single source of truth for account identities | Must | ✅ Implemented |
| FR-32 | Provide Python helper module (`kol_registry.py`) for name → WeChat_ID → FakeID lookup by ingestion scripts | Must | ✅ Implemented |

---

## 3. Non-Functional Requirements

### 3.1 Performance
- **NFR-1**: Ingestion fast-path (scrape → LightRAG write, excluding Cognee)
  completes within **200ms** for typical WeChat articles.
- **NFR-2**: Cognee batch canonicalization runs asynchronously and must not
  block or degrade the ingestion path.
- **NFR-3**: Graph query latency < 3 seconds for simple entity lookups.
- **NFR-4**: Synthesis (retrieval + LLM generation) completes within 30 seconds
  for up to 10 relevant documents.

### 3.2 Privacy & Security
- **NFR-5**: No content is transmitted to external services except for LLM /
  Vision API calls (Gemini, Apify).
- **NFR-6**: API keys are stored in `.env` files, never committed to Git.
- **NFR-7**: Local image server binds to `localhost` only.

### 3.3 Reliability
- **NFR-8**: CDP fallback activates automatically when Apify fails; no manual
  intervention required.
- **NFR-9**: Cognee service failure (429 / 503) must not crash or block the
  ingestion pipeline (graceful degradation).
- **NFR-10**: `canonical_map.json` updates use atomic rename to prevent
  corruption under concurrent access.
- **NFR-11**: Knowledge graph and Cognee state persist across system reboots.

### 3.4 Maintainability
- **NFR-12**: Modular codebase with clear separation: scraping, KG, memory,
  synthesis.
- **NFR-13**: All path constants defined in `config.py`; no hardcoded paths
  elsewhere.
- **NFR-14**: Dependencies pinned in `requirements.txt`.

---

## 4. Technical Architecture

### 4.1 High-Level Data Flow

```mermaid 
User / Agent
    │
    ├─→ DROP WeChat URL / PDF
    │
    │   ┌─────────────────────────────────────────────────────┐
    │   │  FAST PATH (< 200ms target)                         │
    │   │                                                     │
    │   │  Apify Scraper (primary)                            │
    │   │      │ fail → CDP Fallback (Windows Edge via 9223)  │
    │   │      ↓                                              │
    │   │  Extract text (Markdown) + Download images          │
    │   │      ↓                                              │
    │   │  Gemini Vision → image descriptions                 │
    │   │      ↓                                              │
    │   │  LightRAG indexing (entity/vector/graph storage)    │
    │   │      ↓                                              │
    │   │  Write raw entities → entity_buffer/                │
    │   └─────────────────────────────────────────────────────┘
    │
    │   ┌─────────────────────────────────────────────────────┐
    │   │  KOL REGISTRY (pre-ingestion lookup)                │
    │   │                                                     │
    │   │  docs/wechat_kol_registry.json canonical JSON       │
    │   │      ↓                                              │
    │   │  kol_registry.py → get_fakeid(name)                 │
    │   │      ↓                                              │
    │   │  kol_config.py → auto-loads FAKEIDS dict            │
    │   │      → consumed by batch_ingest_kol_mvp.py          │
    │   └─────────────────────────────────────────────────────┘
    │
    │   ┌─────────────────────────────────────────────────────┐
    │   │  ASYNC PATH (background, ≤ 1x/day or on threshold)  │
    │   │                                                     │
    │   │  cognee_batch_processor.py                          │
    │   │      ↓                                              │
    │   │  Read entity_buffer/ → Cognee canonicalization      │
    │   │      ↓                                              │
    │   │  Update canonical_map.tmp.json → atomic rename      │
    │   │      ↓                                              │
    │   │  Log to cognee_batch.log                            │
    │   └─────────────────────────────────────────────────────┘
    │
    └─→ QUERY / SYNTHESIS
            │
            ├─→ Load canonical_map.json → normalize query entities
            ├─→ Cognee recall() → retrieve prior query context
            ├─→ LightRAG hybrid retrieval (vector + graph)
            ├─→ Gemini 2.5 Pro synthesis
            ├─→ Cognee remember() → persist synthesis result
            └─→ Markdown report with inline local image URLs
                    → delivered as .md file via Telegram
```

### 4.2 Component Details
| Component | File | Purpose | Key Technologies |
|-----------|------|---------|-----------------|
| Ingestion Engine | `ingest_wechat.py` | Scrape, extract, download, describe | Apify SDK, Playwright (CDP), `google.genai` |
| PDF Ingestion | `multimodal_ingest.py` | Parse PDFs, extract embedded images | PyMuPDF, `google.genai` |
| Knowledge Graph | LightRAG (library) | Structured storage & hybrid retrieval | LightRAG, sentence-transformers |
| Cognee Wrapper | `cognee_wrapper.py` | remember() / recall() interface | Cognee, LiteLLM |
| Batch Processor | `cognee_batch_processor.py` | Async entity canonicalization | Cognee, file-based queue |
| Synthesis Engine | `kg_synthesize.py` | Retrieve + generate comprehensive answers | Gemini 2.5 Pro, Markdown |
| Query CLI | `query_lightrag.py` | Direct KG access (naive/local/global/hybrid) | LightRAG |
| Local Media Server | (systemd / background) | Serve downloaded images on port 8765 | Python `http.server` |
| Configuration | `config.py` | Centralized settings & env-var loading | `python-dotenv` |
| Account Registry | `docs/wechat_kol_registry.json` + `kol_registry.py` | Canonical KOL identity store: name → WeChat_ID → FakeID | JSON, lazy-loaded Python module |
| Batch KOL Ingestion (legacy) | `batch_ingest_kol_mvp.py` | Deprecated — use scan→classify→ingest pipeline instead | Apify SDK, registry lookup |
| KOL Scanner | `batch_scan_kol.py` | Scan WeChat KOL articles into SQLite (no classify, no ingest) | WeChat MP API, SQLite |
| KOL Classifier | `batch_classify_kol.py` | Classify scanned articles by topic via LLM, write results to SQLite | DeepSeek, Gemini, SQLite |
| KOL Ingest (DB mode) | `batch_ingest_from_spider.py --from-db` | Ingest pre-classified articles from SQLite into LightRAG | SQLite, ingest_wechat subprocess |
| SQLite Database | `data/kol_scan.db` | Unified persistence: accounts, articles, classifications, ingestions, entities | Python sqlite3 |

### 4.3 Storage Layout
```
~/.hermes/kg-vault/
├── lightrag_storage/      # LightRAG graph + vector index
├── images/                # Downloaded article images
│   └── {article_hash}/
│       └── {image_index}.jpg
├── entity_buffer/         # Entity extraction JSON files (file fallback)
├── canonical_map.json     # Entity canonical map (file fallback)

<project>/data/
└── kol_scan.db            # SQLite: accounts, articles, classifications,
                            #   ingestions, extracted_entities, entity_canonical
├── entity_buffer/         # Raw entities pending Cognee processing
│   ├── {article_hash}.json
│   └── {article_hash}.json.processed   # marker after batch run
├── canonical_map.json     # Cognee-produced entity alias map
├── outputs/               # Synthesized .md reports
│   └── {query_hash}.md
└── cognee_batch.log       # Batch processor health log
```

### 4.4 Source Code Layout (Project Root)
```
OmniGraph-Vault/
├── config.py               # Centralized config & env-var loading
├── kol_config.py           # LOCAL ONLY — secrets (TOKEN, COOKIE), auto-loads FAKEIDS from registry
├── kol_registry.py         # Python helper: get_fakeid(), get_wechat_id(), get_account(), list_accounts()
├── ingest_wechat.py        # Primary WeChat article ingestion engine
├── batch_ingest_kol_mvp.py # Batch KOL ingestion using registry FAKEIDS
├── kg_synthesize.py        # Synthesis engine (retrieve + LLM generate)
├── query_lightrag.py       # CLI for direct KG query
├── skill_runner.py         # Hermes skill simulator for local validation
├── docs/
│   ├── wechat_kol_registry.json   # Canonical KOL identity registry (version-controlled)
│   └── rules-research-report-*.md # Archival research reports
├── skills/
│   ├── omnigraph_ingest/    # Hermes skill: article ingestion
│   ├── omnigraph_query/     # Hermes skill: KG query
│   └── omnigraph_architect/ # Hermes skill: architecture advice
├── tests/
│   ├── unit/               # Unit tests
│   ├── integration/         # Integration tests
│   └── skills/             # Skill simulator test cases
└── .planning/              # Planning docs (ROADMAP.md, STATE.md, etc.)
```

---

## 5. Test Strategy

### 5.1 Test Pyramid
```
        E2E Gate Tests
           /       \
   Integration Tests  Component Tests
          \         /
           Unit Tests
```

### 5.2 Unit Tests
**Location:** `tests/unit/`

| File | Covers |
|------|--------|
| `test_config.py` | `config.py` path resolution and env-var loading |
| `test_image_processor.py` | Image download, hashing, localhost URL generation |
| `test_lightrag_client.py` | LightRAG indexing and retrieval functions |
| `test_cognee_wrapper.py` | `remember()` / `recall()` operations |
| `test_batch_processor.py` | Idempotency (`.processed` marker), atomic map write |
| `test_canonical_map.py` | Entity normalization applied to query pre-processing |

### 5.3 Integration Tests
**Location:** `tests/integration/`

| File | Covers |
|------|--------|
| `test_ingestion_pipeline.py` | Full ingestion of mock article (no live APIs) |
| `test_synthesis_flow.py` | Hybrid retrieval + synthesis with mocked LLM |
| `test_cdp_fallback.py` | Apify failure → CDP activation |
| `test_async_decoupling.py` | Confirm Cognee batch path does not block ingestion |
| `test_canonical_map_concurrency.py` | Atomic rename under simulated concurrent access |

### 5.4 End-to-End Gate Tests

| Gate | Description | Status |
|------|-------------|--------|
| Gate 1 | LightRAG installation & validation | ✅ Passed |
| Gate 2 | Cognee setup as memory provider | ✅ Passed |
| Gate 3 | Local image server startup + HTTP live test | ✅ Passed |
| Gate 4 | Single WeChat article ingestion, KG node creation confirmed | ✅ Passed |
| Gate 5 | Single PDF ingestion, image extraction confirmed | ✅ Passed |
| Gate A | Cognee initialized, `cognee.config` output verified | ✅ Passed |
| Gate B | `remember()` / `recall()` firing on synthesis, memory state shown | ✅ Passed |
| Gate C | Chinese/English entity canonicalized through batch processor | ✅ Passed |
| Gate D | Second query benefits from first query's remembered context | ✅ Passed |
| Gate 6 | End-to-end: 3 articles ingested, cross-article synthesis query answered | 🔄 Current |
| Gate 7 | Hermes skill simulator: both skills pass all test cases via `skill_runner.py` | 🔄 Planned |

### 5.5 Hermes Skill Simulator (Local, No Hermes Required)

Since Hermes uses Gemini as its LLM backend — the same model already in this project's stack — skill execution can be simulated exactly locally using `skill_runner.py`.

**How it works:**

```
SKILL.md body       → system prompt
references/*.md     → injected on-demand (Level 2 loading simulation)
test input message  → user message
Gemini API          → response (same backend Hermes uses)
```

`scripts/` files are tested standalone via `subprocess` independently of the LLM simulation.

**Runner interface:**

```bash
# Test a skill against a single message
python skill_runner.py skills/omnigraph_ingest "add this article to my kb: https://mp.weixin.qq.com/s/..."

# Run all test cases defined in a skill's test file
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json

# Validate skill structure only (no API call)
python skill_runner.py skills/omnigraph_ingest --validate
```

**Test case format** (`tests/skills/test_<skill_name>.json`):

```json
[
  {
    "description": "golden path trigger",
    "input": "what do I know about LightRAG?",
    "expect_contains": ["kg_synthesize.py", "hybrid"],
    "expect_not_contains": ["ingest"]
  },
  {
    "description": "guard clause fires on delete",
    "input": "delete all nodes",
    "expect_contains": ["confirm", "cannot be undone"]
  },
  {
    "description": "wrong skill — should redirect",
    "input": "add this article to my kb",
    "expect_contains": ["omnigraph_ingest"]
  }
]
```

**What this validates:**
- LLM follows decision trees correctly given the skill instructions
- Guard clauses fire for destructive operations
- Output format rules are respected (table vs bullets vs plain count)
- Out-of-scope requests are redirected to the correct skill
- `requires` env vars are referenced in responses when missing

**What it does NOT validate:**
- Hermes-specific tool dispatch (`skill_view`, `exec` calls) — those require live Hermes
- Trigger phrase auto-matching (YAML `triggers` field) — validated on the Hermes PC at Gate 7

**Location:** `skill_runner.py` (project root), test cases in `tests/skills/`

### 5.6 Continuous Testing
- **Pre-commit**: `flake8` + `black` static analysis.
- **Skill simulator**: `python skill_runner.py skills/ --test-all` run locally before each commit touching `skills/`.
- **GitHub Actions**: Integration tests on push to `main`.
- **Manual**: Execute corresponding `specs/*.md` test plan before marking each gate complete.

---

## 6. Development Roadmap

### Phase 1: Core Knowledge Base ✅ Completed
- WeChat article ingestion (Apify + CDP fallback)
- LightRAG graph storage
- Cognee async memory integration (decoupled from ingestion fast-path)
- Local image server
- Synthesis report generation + Telegram delivery

### Phase 2: Stability & Agent Integration ✅ Completed
- Canonical WeChat KOL Registry — version-controlled JSON + Python helper module
- Batch ingestion pipeline: scan → classify via LLM (DeepSeek/Gemini) → ingest
- SQLite-backed KOL pipeline (accounts, articles, classifications, ingestions)
- Entity layer migration to SQLite (dual-write, DB-first read)
- Hermes Agent skill wrappers + skill runner with test suites

### Phase 3: Extended Content Sources (Current)
- Large-scale batch KOL ingestion (54 accounts, 1000+ articles)
- Gemini free-tier classifier integration

### Phase 4: Advanced Features (Future)
- Scheduled Cognee batch sync with cron configuration
- Graph analytics (topic clustering, trend detection)

---

## 7. Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Gemini API quotas | 429 errors during bulk ingestion | Rate-limiting in batch processor; distribute across API keys |
| CDP requires Windows Edge on host | Linux-only environments lose fallback | Rely on Apify; Docker-based CDP bridge as future option |
| Cognee entity alignment has eventual consistency | New articles take ≤1 day to be canonicalized | Acceptable for personal KB; fast-path LightRAG retrieval still works immediately |
| Single-user design | Not suited for team collaboration | Intentional; multi-user would require significant rearchitecting |
| LightRAG graph size at scale | Very large graphs may slow retrieval | Graph pruning or dedicated Neo4j instance when needed |
| KOL registry manually maintained | New WeChat accounts not auto-detected | Periodic web search + PR workflow to update registry |

---

## 8. Appendix

### 8.1 Glossary
- **KG** – Knowledge Graph
- **CDP** – Chrome DevTools Protocol
- **LightRAG** – Lightweight RAG framework with built-in dual-index (vector + graph) storage
- **Cognee** – Open-source async memory layer for AI agents
- **Canonicalization** – Merging multiple surface forms of the same entity (e.g., "知识图谱" ↔ "Knowledge Graph")
- **Fast Path** – The synchronous ingestion pipeline; Cognee is excluded from this path
- **Async Path** – The background Cognee batch processing pipeline
- **entity_buffer** – File-based queue of raw entities awaiting Cognee canonicalization
- **canonical_map.json** – Output of Cognee batch processing; used by synthesis layer to normalize query entities
- **KOL Registry** – `docs/wechat_kol_registry.json`: version-controlled JSON mapping of WeChat KOL account names to 微信号 and FakeIDs, with tags and source provenance

### 8.2 References
- [LightRAG GitHub](https://github.com/HKU-Smart-OT/LightRAG)
- [Cognee GitHub](https://github.com/topoteretes/cognee)
- [Google Gemini API Docs](https://ai.google.dev/)
- [Apify WeChat Scraper](https://apify.com/zOQWQaziNeBNFWN1O/wechat-article-scraper)
- [Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs)
- [OnlyTerp LightRAG + Hermes Guide](https://github.com/OnlyTerp/hermes-optimization-guide)

### 8.3 Changelog
- **2026-04-27**: v1.3 – SQLite-backed KOL pipeline: `batch_scan_kol.py`,
  `batch_classify_kol.py`, `--from-db` ingest mode; `data/kol_scan.db`
  with 6 tables (accounts, articles, classifications, ingestions,
  extracted_entities, entity_canonical); Phase 2 entity layer migration
  (dual-write, DB-first read); Gemini classifier option alongside DeepSeek;
  document cleanup (52→23 docs). Deprecate `batch_ingest_kol_mvp.py`.
- **2026-04-24**: v1.2 – Add canonical WeChat KOL Registry:
  `docs/wechat_kol_registry.json`, `kol_registry.py` helper module;
  `kol_config.py` now auto-loads FAKEIDS from registry eliminating
  hardcoded account lists; add data flow diagram for registry lookup;
  add FR-31/FR-32, component rows, source-code layout section (4.4),
  roadmap item, limitation, and glossary entry.
- **2026-04-21**: v1.1 – Reflect async Cognee decoupling architecture;
  add `entity_buffer`, `canonical_map.json`, `cognee_batch_processor.py`;
  update Gate table to merge original Gates 1-5 with Cognee Gates A-D;
  correct Gemini version references (1.5 → 2.5); add PDF ingestion FR;
  update NFR-1 performance target to 200ms fast-path.
- **2026-04-20**: v1.0 – Initial PRD/TDD reflecting core implementation.
  Project renamed from KG-Vault to OmniGraph-Vault.
- **2026-04-19**: Core ingestion, synthesis, and memory features implemented.

---
