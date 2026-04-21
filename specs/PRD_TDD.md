# OmniGraph-Vault: PRD & TDD Document

**Product:** OmniGraph-Vault – Personal Knowledge Base for AI Agents  
**Target Users:** Developers and researchers using Openclaw, Hermes Agent, or similar AI assistant frameworks.  
**Version:** 1.0  
**Last Updated:** 2025-04-21  

---

## 1. Product Vision

### 1.1 Problem Statement
AI agents (Openclaw, Hermes Agent, etc.) excel at task execution but lack **persistent, structured memory** across sessions. They cannot:
- Retain learned knowledge between conversations.
- Maintain a personal, evolving model of the user’s interests and domain context.
- Access rich multimodal content (text + images) in a locally controlled, private store.

### 1.2 Solution
OmniGraph‑Vault is a **local, graph‑based knowledge base** that:
- **Ingests** web content (WeChat articles, blogs, docs) into a multimodal knowledge graph.
- **Stores** all data (text, images, metadata) on‑premise, with no external SaaS dependencies.
- **Integrates** seamlessly with AI agents via simple Python APIs, providing long‑term memory and contextual intelligence.
- **Evolves** over time through user interaction and automated synthesis.

### 1.3 Core Value Propositions
- **Agent‑Ready Intelligence**: Structured knowledge retrieval for more context‑aware agent responses.
- **Privacy by Design**: All data stays on the user’s machine; no cloud knowledge‑base subscriptions.
- **Multimodal Richness**: Images are downloaded, described by vision AI, and served locally—enabling visual context in agent answers.
- **Stateful Learning**: Tracks user preferences, merges synonymous concepts, and improves recall over multiple sessions.

---

## 2. Functional Requirements

### 2.1 Ingestion Pipeline
| Requirement | Priority | Status |
|-------------|----------|--------|
| **FR‑1** – Scrape WeChat public‑account articles (text + images) | Must | ✅ Implemented |
| **FR‑2** – Fallback to CDP when primary Apify scraper fails | Must | ✅ Implemented |
| **FR‑3** – Download images to local storage (`~/.hermes/kg‑vault/images/`) | Must | ✅ Implemented |
| **FR‑4** – Generate semantic descriptions for every image (Gemini Vision) | Must | ✅ Implemented |
| **FR‑5** – Index content as a knowledge graph (LightRAG) | Must | ✅ Implemented |
| **FR‑6** – Support batch ingestion of multiple URLs | Should | 🔄 Planned |

### 2.2 Knowledge Graph & Memory
| Requirement | Priority | Status |
|-------------|----------|--------|
| **FR‑7** – Store entities, relationships, and concepts in a queryable graph | Must | ✅ Implemented |
| **FR‑8** – Integrate Cognee for session‑aware memory and entity canonicalization | Must | ✅ Implemented |
| **FR‑9** – Enable hybrid retrieval (vector + graph) for complex queries | Must | ✅ Implemented |
| **FR‑10** – Provide a direct query API (`query_lightrag.py`) | Must | ✅ Implemented |
| **FR‑11** – Support incremental updates (add new content without full rebuild) | Should | 🔄 Planned |

### 2.3 Synthesis & Reporting
| Requirement | Priority | Status |
|-------------|----------|--------|
| **FR‑12** – Generate synthesized Markdown reports from KG retrieval | Must | ✅ Implemented |
| **FR‑13** – Embed local image URLs (`http://localhost:8765/...`) in reports | Must | ✅ Implemented |
| **FR‑14** – Allow user‑defined synthesis prompts | Must | ✅ Implemented |
| **FR‑15** – Output reports to file and/or Telegram | Must | ✅ Implemented |

### 2.4 AI‑Agent Integration
| Requirement | Priority | Status |
|-------------|----------|--------|
| **FR‑16** – Expose Python functions for ingestion, query, and synthesis | Must | ✅ Implemented |
| **FR‑17** – Provide example integration snippets for Openclaw / Hermes Agent | Must | ✅ Implemented |
| **FR‑18** – Support webhook‑based ingestion (Telegram → OmniGraph‑Vault) | Could | 🔄 Future |
| **FR‑19** – REST API for remote agent calls | Could | 🔄 Future |

### 2.5 Configuration & Operations
| Requirement | Priority | Status |
|-------------|----------|--------|
| **FR‑20** – Centralized configuration (`config.py`) for paths and API keys | Must | ✅ Implemented |
| **FR‑21** – Separate runtime data (`~/.hermes/kg‑vault/`) from source code | Must | ✅ Implemented |
| **FR‑22** – Background image server (port 8765) for local media serving | Must | ✅ Implemented |
| **FR‑23** – Logging and error monitoring | Should | 🔄 Planned |
| **FR‑24** – Health checks and self‑diagnosis scripts | Could | 🔄 Future |

---

## 3. Non‑Functional Requirements

### 3.1 Performance
- **NFR‑1**: Ingestion of a typical WeChat article (≈2000 words + 5 images) completes within 2 minutes.
- **NFR‑2**: Graph query latency < 3 seconds for simple entity lookups.
- **NFR‑3**: Synthesis (retrieval + LLM generation) completes within 30 seconds for up to 10 relevant documents.

### 3.2 Privacy & Security
- **NFR‑4**: No content is transmitted to external services except for LLM/Vision API calls (Gemini, Apify).
- **NFR‑5**: API keys are stored in environment variables or `.env` files, never committed to Git.
- **NFR‑6**: Local image server binds to `localhost` only (no external exposure).

### 3.3 Reliability
- **NFR‑7**: Scraper fallback (CDP) activates automatically when primary method fails.
- **NFR‑8**: Failed ingestions are logged and do not crash the pipeline.
- **NFR‑9**: Knowledge graph persists across system reboots.

### 3.4 Maintainability
- **NFR‑10**: Code is modular with clear separation of concerns (scraping, KG, memory, synthesis).
- **NFR‑11**: Configuration is centralized; path constants are defined in `config.py`.
- **NFR‑12**: Dependencies are pinned in `requirements.txt`.

---

## 4. Technical Architecture

### 4.1 High‑Level Data Flow
```
User / Agent
    │
    ├─→ Ingest WeChat URL → Apify Scraper (primary) → CDP Fallback (if needed)
    │                         │
    │                         ├─→ Extract text (Markdown)
    │                         ├─→ Download images → local storage
    │                         └─→ Gemini Vision descriptions
    │
    ├─→ LightRAG Indexing
    │        │
    │        ├─→ Entity/relationship extraction
    │        ├─→ Vector embeddings
    │        └─→ Graph storage (~/.hermes/kg‑vault/lightrag_storage/)
    │
    ├─→ Cognee Memory
    │        │
    │        ├─→ Session history tracking
    │        └─→ Entity canonicalization
    │
    └─→ Query / Synthesis
           │
           ├─→ Hybrid retrieval (vector + graph)
           ├─→ LLM synthesis (Gemini 2.5 Pro)
           └─→ Markdown report with local image URLs
```

### 4.2 Component Details
| Component | Purpose | Key Technologies |
|-----------|---------|------------------|
| **Ingestion Engine** (`ingest_wechat.py`) | Scrape, extract, download, describe | Apify SDK, Playwright (CDP), `google.genai` |
| **Knowledge Graph** (LightRAG) | Structured storage & retrieval | LightRAG, sentence‑transformers, Neo4j (embedded) |
| **Memory Layer** (Cognee) | Session‑aware memory & learning | Cognee 1.0.1, LiteLLM, Gemini embeddings |
| **Synthesis Engine** (`kg_synthesize.py`) | Retrieve + generate comprehensive answers | Gemini 2.5 Pro, Markdown templating |
| **Local Media Server** | Serve downloaded images | Python `http.server` (port 8765) |
| **Configuration** (`config.py`) | Centralized settings & env‑var loading | Python `dotenv`, path constants |

### 4.3 Integration Points for AI Agents
- **Python API**: Call `ingest_wechat.py`, `kg_synthesize.py`, `query_lightrag.py` via `subprocess`.
- **Direct Import**: Import and call functions from the modules (requires shared environment).
- **Future REST API**: HTTP endpoints for remote agent calls (planned).

---

## 5. Test‑Driven Development (TDD) Strategy

### 5.1 Test Pyramid
```
        E2E Tests (Gate 5)
           /       \
Integration Tests   Component Tests
          \         /
           Unit Tests
```

### 5.2 Unit Tests (Component Level)
**Location:** `tests/unit/`
- **`test_config.py`** – Verify `config.py` loads environment variables and returns correct paths.
- **`test_image_processor.py`** – Validate image download, hashing, and local URL generation.
- **`test_lightrag_client.py`** – Test LightRAG indexing and retrieval functions.
- **`test_cognee_wrapper.py`** – Ensure Cognee memory operations work as expected.

### 5.3 Integration Tests (Cross‑Component)
**Location:** `tests/integration/`
- **`test_ingestion_pipeline.py`** – End‑to‑end ingestion of a mock WeChat article (no external APIs).
- **`test_synthesis_flow.py`** – Hybrid retrieval + synthesis with a mocked LLM.
- **`test_cdp_fallback.py`** – Simulate Apify failure and verify CDP fallback activation.

### 5.4 End‑to‑End Tests (User‑Facing Gates)
**Location:** `specs/` (executable test plans)
- **Gate 1** – LightRAG installation & validation. ✅
- **Gate 2** – Cognee setup as memory provider. ✅
- **Gate 3** – Local image server startup. ✅
- **Gate 4** – Single‑article ingestion & KG node creation. ✅
- **Gate 5** – Cross‑article synthesis & report generation. **Current Gate**
- **Gate 6** – Multi‑source ingestion (WeChat + RSS + local PDF). Planned
- **Gate 7** – Openclaw/Hermes Agent integration demo. Planned

### 5.5 Continuous Testing Practices
- **Pre‑commit Hooks**: Run unit tests and static analysis (flake8, black) before commits.
- **CI Pipeline** (GitHub Actions): Execute integration tests on push to `main`.
- **Manual Validation**: Execute the corresponding `specs/*.md` test plan before marking a gate as complete.

---

## 6. Development Roadmap

### Phase 1: Core Knowledge Base (✅ Completed)
- WeChat article ingestion (Apify + CDP fallback).
- LightRAG graph storage.
- Cognee memory integration.
- Local image server.
- Synthesis report generation.

### Phase 2: Agent Integration & Scalability (Current)
- **Gate 5**: End‑to‑end test with 3+ articles and cross‑article synthesis.
- Improve error handling and logging.
- Add batch ingestion support.
- Provide comprehensive integration examples for Openclaw / Hermes Agent.

### Phase 3: Extended Content Sources (Planned)
- RSS/Atom feed ingestion.
- Local PDF/document parsing.
- Web‑page scraping (generic, not just WeChat).

### Phase 4: Advanced Features (Future)
- REST API for remote agent calls.
- Webhook‑based ingestion (Telegram bot integration).
- Advanced graph analytics (topic clustering, trend detection).
- Multi‑user support with access controls.

---

## 7. Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Google Gemini API quotas** | Embedding requests may hit 429 errors during bulk ingestion. | Use rate‑limiting, switch embedding models, or distribute requests across multiple API keys. |
| **CDP fallback requires Windows Edge** | Linux‑only environments cannot use the CDP fallback. | Provide a Docker‑based CDP bridge or rely solely on Apify (with subscription). |
| **LightRAG graph size** | Very large graphs may slow retrieval. | Implement graph pruning, sharding, or move to a dedicated Neo4j instance. |
| **Single‑user design** | Not suited for team collaboration. | Keep as personal knowledge base; multi‑user version would require significant architectural changes. |

---

## 8. Appendix

### 8.1 Glossary
- **KG** – Knowledge Graph.
- **CDP** – Chrome DevTools Protocol.
- **LightRAG** – Lightweight Retrieval‑Augmented Generation with built‑in graph storage.
- **Cognee** – Open‑source memory layer for AI agents.
- **Canonicalization** – Merging multiple surface forms of the same entity (e.g., “AI Agent” ↔ “Artificial Intelligence Agent”).

### 8.2 References
- [LightRAG GitHub](https://github.com/HKU-Smart-OT/LightRAG)
- [Cognee GitHub](https://github.com/topoteretes/cognee)
- [Google Gemini API Docs](https://ai.google.dev/)
- [Apify Web Scraper Actor](https://apify.com/zOQWQaziNeBNFWN1O/wechat-article-scraper)

### 8.3 Changelog
- **2025‑04‑21**: PRD/TDD v1.0 – Initial document reflecting current implementation and new positioning as AI‑agent personal knowledge base.
- **2025‑04‑20**: Project renamed from “KG‑Vault” to “OmniGraph‑Vault”; centralized configuration (`config.py`) introduced.
- **2025‑04‑19**: Core ingestion, synthesis, and memory features implemented.
