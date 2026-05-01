# Phase 9 PRD — Timeout Control + LightRAG State Management

**Milestone:** v3.1 Single-Article Ingest Stability
**Requirements covered:** TIMEOUT-01, TIMEOUT-02, TIMEOUT-03, STATE-01, STATE-02, STATE-03, STATE-04 (7 REQs)
**Dependencies:** Phase 8 complete (IMG-01..04)
**Downstream blockers:** Phase 10 (ARCH) depends on STATE-04 contract change; Phase 11 (E2E gate) depends on TIMEOUT-01..03

---

## Goal

Deliver two coupled capabilities that give the ingestion pipeline deterministic, interruptible behavior:

1. **Timeout control:** LightRAG respects `LLM_TIMEOUT=600` env; DeepSeek client-side timeout=120s; outer per-article `asyncio.wait_for` budget scales with text chunk count (not image count).
2. **LightRAG state management:** `get_rag()` returns flushable instance; `asyncio.wait_for` timeout on an article rolls back partial inserts; rollback is idempotent; pre-batch cleanup of "history debt" from prior runs.

---

## Locked Decisions (from REQUIREMENTS.md — these ARE the acceptance criteria)

### TIMEOUT-01 — `LLM_TIMEOUT` env controls LightRAG health_check
- LightRAG instance initialization reads `os.environ.get("LLM_TIMEOUT", "600")` and uses it as the health_check timeout ceiling
- Default 600s (up from implicit 180s)

### TIMEOUT-02 — DeepSeek async client explicit timeout
- `lib/llm_deepseek.py` `AsyncOpenAI` client configured with `timeout=120.0` (or pass `timeout=httpx.Timeout(120.0)` — inspect SDK version and pick the correct idiom)
- Default 120s prevents single-chunk runaway

### TIMEOUT-03 — Outer `asyncio.wait_for` budget scales with chunk count
- Formula: `budget_s = max(120 + 30 * chunk_count, 900)`
- Applied in `batch_ingest_from_spider.py` (and/or wherever the per-article orchestrator lives)
- `chunk_count` resolved from the article's text length divided by LightRAG's chunk size (best estimate pre-ingest) OR as a post-ingest observation fed back if unavailable
- **Two-layer timeout semantics** must be explicit in code comments:
  - Outer `wait_for` governs the whole-article budget
  - Inner `LLM_TIMEOUT=600` (TIMEOUT-01) governs each LightRAG per-chunk call
- Floor of 900s guarantees one slow 800s DeepSeek chunk still completes

### STATE-01 — Pre-batch buffer flush
- At start of a `batch_ingest` run (or start of a single-article CLI run), any residual buffered-but-unprocessed entities from a prior crashed run are flushed before new work begins
- Implementation: call an explicit `rag.flush_pending_buffer()` helper OR re-init the rag with a clean slate — whichever is idiomatic to LightRAG's internals (planner to investigate)
- Quota NOT consumed on replay of old buffer

### STATE-02 — Rollback on `asyncio.wait_for` timeout
- When `asyncio.wait_for` kills an in-progress article task, any partially inserted chunks + entities + edges + vectors for that article are removed
- Graph stays consistent: no orphan entity nodes, no chunks without a parent doc, no dangling vectors
- Embed quota NOT wasted on partial doc (this is the single biggest user-visible benefit)

### STATE-03 — Idempotent re-ingest after rollback
- Re-running the same article after a rollback-on-timeout succeeds without orphans or duplicate primary keys
- Covered by a unit test: ingest → force timeout → rollback → re-ingest same article → assert graph state matches a clean single-ingest baseline

### STATE-04 — `get_rag()` contract change
- `get_rag()` either returns a fresh LightRAG instance on each call OR accepts `flush: bool = False` parameter
- Current global-singleton-with-state is the root cause of STATE-01's "history debt" replay
- Callers that want the historical behavior (test reuse) pass `flush=False`; production default is `flush=True` (or simply "always fresh")
- **Breaking change if any external code imports get_rag** — planner MUST grep for all callers and update them

---

## Out of Scope (move to follow-up milestones if they come up)

- Migrating embedding to Vertex AI (v3.3)
- Async Vision worker (Phase 10 ARCH-02)
- Checkpoint/resume across crashes (v3.2)
- Vision provider circuit breaker (v3.2)
- Any batch-level concurrency (v3.2)

---

## Success Criteria for Phase 9

1. Running GPT-5.5 fixture ingest with `LLM_TIMEOUT=300` proves the env var is respected (LightRAG kills at 300s instead of default)
2. DeepSeek client timeout test: patch a 200s sleep into the DeepSeek transport → client raises `httpx.TimeoutException` after ~120s (not 200s)
3. `asyncio.wait_for` timeout test: force a 5s outer budget on an article that takes 60s → article fails, graph contains zero new entities/chunks for that article (rollback proven)
4. After a forced-timeout + rollback, re-ingest same article → graph state equals a pristine single-ingest state (idempotency proven)
5. `get_rag(flush=True)` after a prior crashed run does NOT replay old buffered entities (STATE-01)
6. `get_rag()` called twice returns either two distinct instances OR the same instance with cleared buffer (contract documented in docstring)
7. All Phase 9 pytest cases pass; Phase 8 regression suite still green (22 tests)

---

## Key existing files the planner should read before planning

- `lib/llm_deepseek.py` — current DeepSeek client setup
- `ingest_wechat.py` (search for `get_rag` — likely the `get_rag()` definition sits here or in a helper module)
- `batch_ingest_from_spider.py` — orchestrator, where `asyncio.wait_for` likely lives
- `lib/lightrag_embedding.py` + LightRAG itself (venv/Lib/site-packages/lightrag/) — understand how LightRAG internals buffer entities, what "flush" would mean, and whether rollback can hook a LightRAG API or must be done at our persistence layer
- `tests/unit/test_lightrag_llm.py` — existing DeepSeek test scaffolding to extend
- `tests/unit/test_api_keys.py` — similar scaffolding pattern

---

## Implementation notes (planner's discretion on details)

- Chunk count estimation for TIMEOUT-03: can use `len(full_text) // LIGHTRAG_CHUNK_SIZE` pre-ingest; exact math doesn't matter as long as it scales roughly linearly with content volume
- Rollback mechanism (STATE-02): LightRAG's internal chunk/entity storage is NanoVectorDB + graphml + kv_store JSON files. A practical rollback can be "record the set of chunk_ids inserted during this article's ingest call, on timeout explicitly `adelete_by_chunk_ids()` (or walk the doc_id) to remove them". LightRAG has `adelete_by_doc_id()` — use that as the primary rollback hook. Details for the planner.
- STATE-04 breaking change scope: only production ingest code calls `get_rag()`; tests have their own setups. Rename + deprecate is probably unnecessary — just change the function and update all callers in one commit.
