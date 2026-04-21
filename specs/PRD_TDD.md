# OmniGraph-Vault: PRD & TDD Document

**Product:** OmniGraph-Vault – Personal Knowledge Base for AI Agents  
**Target Users:** Developers and researchers using Openclaw, Hermes Agent, or similar AI assistant frameworks.  
**Version:** 1.1  
**Last Updated:** 2026-04-21  

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

### 4.3 Storage Layout
```
~/.hermes/kg-vault/
├── lightrag_storage/      # LightRAG graph + vector index
├── images/                # Downloaded article images
│   └── {article_hash}/
│       └── {image_index}.jpg
├── entity_buffer/         # Raw entities pending Cognee processing
│   ├── {article_hash}.json
│   └── {article_hash}.json.processed   # marker after batch run
├── canonical_map.json     # Cognee-produced entity alias map
├── outputs/               # Synthesized .md reports
│   └── {query_hash}.md
└── cognee_batch.log       # Batch processor health log
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
| Gate 7 | Openclaw / Hermes Agent integration demo | 🔄 Planned |

### 5.5 Continuous Testing
- **Pre-commit**: `flake8` + `black` static analysis.
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

### Phase 2: Stability & Agent Integration (Current)
- Gate 6 end-to-end validation
- Batch ingestion support (FR-8)
- Comprehensive error handling and logging (FR-30)
- Hermes Agent skill wrappers for `ingest_wechat` / `kg_synthesize`

### Phase 3: Extended Content Sources (Planned)
- RSS / Atom feed ingestion
- Generic web-page scraping (non-WeChat)
- Scheduled Cognee batch sync with cron configuration

### Phase 4: Advanced Features (Future)
- REST API for remote agent calls
- Webhook-based ingestion (Telegram bot direct integration)
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

### 8.2 References
- [LightRAG GitHub](https://github.com/HKU-Smart-OT/LightRAG)
- [Cognee GitHub](https://github.com/topoteretes/cognee)
- [Google Gemini API Docs](https://ai.google.dev/)
- [Apify WeChat Scraper](https://apify.com/zOQWQaziNeBNFWN1O/wechat-article-scraper)
- [Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs)
- [OnlyTerp LightRAG + Hermes Guide](https://github.com/OnlyTerp/hermes-optimization-guide)

### 8.3 Changelog
- **2026-04-21**: v1.1 – Reflect async Cognee decoupling architecture;
  add `entity_buffer`, `canonical_map.json`, `cognee_batch_processor.py`;
  update Gate table to merge original Gates 1-5 with Cognee Gates A-D;
  correct Gemini version references (1.5 → 2.5); add PDF ingestion FR;
  update NFR-1 performance target to 200ms fast-path.
- **2026-04-20**: v1.0 – Initial PRD/TDD reflecting core implementation.
  Project renamed from KG-Vault to OmniGraph-Vault.
- **2026-04-19**: Core ingestion, synthesis, and memory features implemented.

---
