# Requirements: Agentic-RAG-v1.1

**Milestone:** Agentic-RAG-v1.1
**Parent:** Agentic-RAG-v1 (CLOSED-WITH-DOCUMENTED-V1.1-GAPS 2026-05-24)
**Created:** 2026-05-24
**Total REQs:** 12 (7 Track 1, 5 Track 2)

> Tracks two functional gaps from v1 audit dim 5 + first HTTP integration. Inline citations (originally v1.1-B in audit) explicitly dropped per user direction.

---

## Track 1 — Functional #1: Images via Retriever chunk extraction

### REQ-1.1-A-1: Retriever returns chunk-list, not single wrap

- **Where:** `lib/research/stages/retriever.py`
- **Acceptance:** `RetrieverResult.sources` contains ≥1 `Source(kind="kg_chunk")` per LightRAG raw chunk (or per paragraph if raw chunks not exposed); NOT a single Source wrapping all kg_text
- **Test:** Unit test pinning `len(sources) >= 2` for any TEST-05-shaped query that returns multi-paragraph kg_text

### REQ-1.1-A-2: Hash extraction per chunk

- **Where:** `lib/research/stages/retriever.py`
- **Acceptance:** `ARTICLE_HASH_RE` is grepped against EACH chunk's content (and metadata if available); all matched hashes deduped across chunks form `image_candidates` source-pool
- **Test:** Fixture with 3 chunks containing 5 hash refs (some duplicated) → exactly N unique hashes extracted

### REQ-1.1-A-3: Image globbing wired from extracted hashes

- **Where:** `lib/research/stages/retriever.py`
- **Acceptance:** For each unique hash, glob `BASE_IMAGE_DIR/{hash}/*.{jpg,png,webp}` (case-insensitive), top-N=10 by deterministic sort (lexicographic filename) populate `RetrieverResult.image_candidates`
- **Test:** Fixture dir with 3 hash dirs × 4 images each → 10 candidates returned (capped), order deterministic

### REQ-1.1-A-4: Synthesizer URL flip

- **Where:** `lib/research/stages/synthesizer.py`
- **Acceptance:** Inline image markdown uses `/static/img/{parent}/{name}` pattern, NOT `http://localhost:8765/{parent}/{name}`
- **Test:** Synthesizer output regex pinning `!\[.*\]\(/static/img/[0-9a-f]{10}/[^)]+\)` for any test that produces images

### REQ-1.1-A-5: Caption-anchored alt text preserved

- **Where:** `lib/research/stages/synthesizer.py`
- **Acceptance:** v1 ar-2-02 caption-anchoring behavior unchanged — alt text comes from caption preceding the hash ref, NOT from filename
- **Test:** Existing ar-2-02 caption-anchor test still passes after URL flip

### REQ-1.1-A-6: Best-effort failure preserved

- **Where:** `lib/research/stages/retriever.py`
- **Acceptance:** Any exception in chunk-split / hash-extract / glob path returns `RetrieverResult(status="failed", ...)` with empty image_candidates, never raises
- **Test:** Mock raising LightRAG client → status="failed", `image_candidates == ()`

### REQ-1.1-A-7: TEST-05 condition (a) flips

- **Where:** smoke harness
- **Acceptance:** TEST-05 query "What is LightRAG?" returns markdown with ≥3 distinct image refs to `/static/img/...` URLs
- **Test:** Existing TEST-05 condition (a) measurement; current value 0 → target ≥3

---

## Track 2 — Functional #2: HTTP API + Databricks-first deploy

### REQ-1.1-B-1: SSE endpoint exists

- **Where:** `kb/api_routers/research.py` (NEW)
- **Acceptance:** `POST /api/research` accepts `{"query": str, "max_iterations": int = 3}`; returns `Content-Type: text/event-stream`
- **Test:** `pytest tests/integration/test_research_router.py` — TestClient SSE response, status 200, content-type correct

### REQ-1.1-B-2: One event per stage + terminal done event

- **Where:** `kb/api_routers/research.py`
- **Acceptance:** Stream emits `event: web_baseline\ndata: {...}\n\n`, then `event: retriever\ndata: {...}\n\n`, etc., for all 5 stages; final `event: done\ndata: <ResearchResult json>\n\n`
- **Test:** Parse SSE stream from TestClient, assert event names sequence

### REQ-1.1-B-3: Wired into kb/api.py

- **Where:** `kb/api.py`
- **Acceptance:** `app.include_router(research_router)` present; existing 3 routers unchanged; `/static/img` mount unchanged
- **Test:** `client.get("/health")` still 200 + new `client.post("/api/research", ...)` returns SSE stream

### REQ-1.1-B-4: Local Databricks UAT 5-step gate passes

- **Where:** Run order: smoke → uvicorn → curl → Playwright MCP → triple verification
- **Acceptance:** All 5 steps green; evidence in `.planning/phases/arx-2/VERIFICATION-1.1-B.md`
  - smoke gate: `scripts/smoke_databricks_serving_local.py` exit 0 with valid completion
  - uvicorn: stdout "Application startup complete" within 10s
  - curl: 5 stage events + done event observed within `OMNIGRAPH_LLM_TIMEOUT_SEC` budget
  - Playwright UAT: ≥5 screenshots in `.playwright-mcp/arx-uat-*.png`
  - triple verification: Network 200 + log SDK call + content marker — all 3 present
- **Test:** Manual UAT execution; this REQ is verification-only

### REQ-1.1-B-5: Databricks Apps deploy + post-deploy UAT pass

- **Where:** Databricks Apps deployment
- **Acceptance:** App name `omnigraph-research-v1-1` (or operator-chosen) deploys successfully; `make logs-tail` shows startup; deployed URL passes the same Playwright UAT
- **Gate:** Triggered ONLY after user replies "go" to deploy preflight (workspace path, app name, env diff, file count). Post-deploy UAT failure → agent fix-redeploys autonomously without second checkpoint.

---

## REQ → Phase Mapping (anticipated; ROADMAP locks final)

| REQ | Phase |
|---|---|
| REQ-1.1-A-1 .. A-7 | arx-1-images |
| REQ-1.1-B-1 .. B-3 | arx-2-http (commit 1: API endpoint) |
| REQ-1.1-B-4, B-5 | arx-2-http (commit 2: Databricks deploy + UAT) |
