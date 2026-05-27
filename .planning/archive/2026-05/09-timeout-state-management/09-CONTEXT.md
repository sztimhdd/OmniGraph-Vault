# Phase 9 — Context (locked decisions derived from 09-PRD.md)

**Mode:** PRD express path — discuss-phase skipped per user request ("autonomous overnight execution, user asleep").
**Derived from:** `09-PRD.md` (single source of truth for acceptance criteria).
**Date:** 2026-04-29.

This document codifies the 7 PRD requirements as **locked decisions** (D-09.XX) that plans MUST
reference. Each requirement in the PRD maps 1:1 to a decision below — no interpretation, no
judgment, just a direct restatement for traceability.

---

## Canonical Refs (MANDATORY)

All plans MUST cross-reference these files when implementing decisions:

| Ref                                                                             | Purpose                                                                       |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `.planning/phases/09-timeout-state-management/09-PRD.md`                        | Primary source — acceptance criteria                                          |
| `.planning/REQUIREMENTS.md` (TIMEOUT-01..03, STATE-01..04)                      | Milestone v3.1 traceability matrix                                            |
| `.planning/ROADMAP.md` (Phase 9 success criteria)                               | Phase-level observable truths                                                 |
| `lib/llm_deepseek.py`                                                           | DeepSeek async client target for TIMEOUT-02                                   |
| `ingest_wechat.py` (lines 114–129: `get_rag()`; 564/667/800: callers)           | STATE-04 contract change target + 3 in-file callers                           |
| `batch_ingest_from_spider.py` (lines 73–99: `ingest_article`; 482/591: get_rag) | TIMEOUT-03 budget + STATE-02 rollback owner + 2 `get_rag` callers             |
| `enrichment/merge_and_ingest.py:133`                                            | External `get_rag` caller — MUST update in same commit                        |
| `ingest_github.py:258`                                                          | Production GitHub URL ingest `get_rag` caller — MUST update in same commit    |
| `multimodal_ingest.py:147`                                                      | Production PDF ingest `get_rag` caller — MUST update in same commit           |
| `scripts/wave0_reembed.py:200,253` + `scripts/phase0_delete_spike.py:98`        | Non-production `get_rag` callers — update for API consistency                 |
| `venv/Lib/site-packages/lightrag/lightrag.py:432`                               | `default_llm_timeout` reads `LLM_TIMEOUT` env at dataclass-definition time    |
| `venv/Lib/site-packages/lightrag/lightrag.py:3223`                              | `adelete_by_doc_id(doc_id, delete_llm_cache=False) -> DeletionResult` — STATE-02 rollback hook |
| `venv/Lib/site-packages/lightrag/constants.py:100`                              | `DEFAULT_LLM_TIMEOUT = 180` — baseline we are raising to 600                  |
| `tests/unit/test_lightrag_llm.py`                                               | DeepSeek mock patterns — extend for TIMEOUT-02                                |
| `tests/unit/test_api_keys.py`                                                   | `monkeypatch` fixture pattern for env-var-driven tests                        |

---

## Locked Decisions

### D-09.01 — `LLM_TIMEOUT` env controls LightRAG per-chunk LLM timeout (TIMEOUT-01)

- **Decision:** `LLM_TIMEOUT=600` (seconds) is the production default and MUST be exported to the
  process environment **before** `from lightrag.lightrag import LightRAG` is imported.
- **Rationale:** LightRAG reads `os.getenv("LLM_TIMEOUT", 180)` as a dataclass field default on
  `LightRAG.default_llm_timeout` (see `venv/Lib/site-packages/lightrag/lightrag.py:432`). The value
  is captured at import/class-definition time. A runtime `os.environ[...] = ...` after import has
  no effect unless the class is re-imported.
- **Implementation constraint:** Set `LLM_TIMEOUT` either (a) in `~/.hermes/.env` (loaded by
  `config.load_env()` which is called at `config.py` import — but `config.py` itself imports
  LightRAG in some paths), or (b) via `os.environ.setdefault("LLM_TIMEOUT", "600")` at the TOP of
  every entry-point script, before any LightRAG import chain executes. Planner picks idiom; (b) is
  safer (no file dependency) and was the pattern for `GOOGLE_GENAI_USE_VERTEXAI` (see
  `ingest_wechat.py:100`).
- **Default:** `600` seconds (up from implicit `180` in `lightrag/constants.py:100`).
- **Verification:** unit test monkeypatches `LLM_TIMEOUT=300`, re-imports LightRAG + instantiates
  via `get_rag()`, asserts `rag.default_llm_timeout == 300`.

### D-09.02 — DeepSeek `AsyncOpenAI` client timeout=120s (TIMEOUT-02)

- **Decision:** `lib/llm_deepseek.py` `_client = AsyncOpenAI(...)` MUST pass an explicit `timeout`
  argument of `120.0` seconds.
- **Idiom:** `openai>=1.0` accepts either `timeout=120.0` (float → interpreted as total request
  timeout) or `timeout=httpx.Timeout(120.0)`. Planner picks; prefer `httpx.Timeout(120.0)` for
  explicit connect/read/write control if the SDK version supports it. Fallback to `float`.
- **Default:** `120.0` seconds.
- **Verification:** unit test patches `AsyncOpenAI.__init__` (or inspects `_client.timeout` after
  module import with `DEEPSEEK_API_KEY=dummy`) and asserts the `timeout` kwarg was passed.

### D-09.03 — Outer `asyncio.wait_for` budget formula (TIMEOUT-03)

- **Decision:** per-article budget = `max(120 + 30 * chunk_count, 900)` seconds.
- **Owner:** `batch_ingest_from_spider.ingest_article` (lines 73–99) — the function that currently
  calls `asyncio.wait_for(ingest_wechat.ingest_article(url, rag=rag), timeout=1200)`. The hardcoded
  `1200` MUST be replaced by a computed `budget_s`.
- **Secondary owner:** `run_uat_ingest.py:33-47` — same pattern if it wraps `ingest_article` with
  `wait_for`; inspect and apply formula. If it calls `ingest_article` bare (no timeout), out of
  scope for this plan (not a TIMEOUT-03 site).
- **`chunk_count` estimation:** pre-ingest, compute
  `chunk_count = max(1, len(full_content) // LIGHTRAG_CHUNK_SIZE)` where `LIGHTRAG_CHUNK_SIZE`
  is LightRAG's configured chunk token size (default 1200 tokens ≈ 4800 chars; use 4800 as the
  char-based estimate — exact math is NOT load-bearing, linear scaling is).
- **Floor:** 900 seconds — guarantees a single slow DeepSeek chunk (worst-case 800s) completes.
- **Two-layer timeout semantics (MUST be in code comment):**
  - Outer `asyncio.wait_for(budget_s)` governs whole-article budget.
  - Inner `LLM_TIMEOUT=600` (D-09.01) governs each LightRAG per-chunk call.
- **Complication:** `ingest_article` is called with a `url`, not the pre-scraped content. The
  outer orchestrator does NOT have `full_content` until AFTER scrape completes. Planner picks
  one of: (a) move `wait_for` to wrap ONLY the `rag.ainsert(full_content)` step inside
  `ingest_article` (scrape happens outside the budget); (b) use a 2-stage budget — scrape has
  its own short budget (120s), then recompute per-chunk budget after scrape and wrap only
  `ainsert`; (c) fall back to `SINGLE_CHUNK_FLOOR=900` for bulk scrape-+-ingest cases where
  content size isn't known until mid-flight. **Plan MUST pick one and document in action.**
- **Verification:** unit test calls the budget helper with `chunk_count=0` (expects 900),
  `chunk_count=20` (expects max(720, 900)=900), `chunk_count=50` (expects max(1620, 900)=1620).

### D-09.04 — Pre-batch buffer flush (STATE-01)

- **Decision:** Every batch entry point (`batch_ingest_from_spider.run`, `.ingest_from_db`) and
  every single-article CLI entry (`ingest_wechat.__main__`, `run_uat_ingest.main`) MUST begin by
  constructing a **clean** LightRAG instance with no buffered-but-unprocessed entities from a
  prior crashed run.
- **Implementation:** leverage D-09.07's `get_rag(flush=True)` contract. "Flush" MUST clear any
  stateful buffers LightRAG maintains between `ainsert` calls (planner to investigate
  `rag.apipeline_enqueue_documents` internal queue, `apipeline_process_enqueue_documents` state,
  and NanoVectorDB pending-write buffers — whatever the `get_rag` caller can re-init to a known-
  empty state).
- **Simplest viable flush:** construct a **fresh** `LightRAG(...)` instance (new object) and call
  `await rag.initialize_storages()` — this re-reads on-disk state but drops any in-memory pending
  buffers from a prior process / prior singleton. If LightRAG has an explicit "drop pending
  queue" API, prefer that; otherwise, fresh-instance construction IS the flush.
- **Quota:** MUST NOT consume embed/LLM quota on replay of old buffer contents.
- **Verification:** unit test simulates a "prior crashed run" by pre-writing a fake pending-
  entity JSON (or using LightRAG's actual queue storage if accessible), calls `get_rag(flush=True)`,
  asserts that `rag.apipeline_process_enqueue_documents` either finds zero pending docs OR the
  test mock for `embedding_func` is called zero times during the "flush" path.

### D-09.05 — Rollback on `asyncio.wait_for` timeout (STATE-02)

- **Decision:** When `asyncio.wait_for` cancels an in-progress `ingest_article` task, the rollback
  handler MUST call `await rag.adelete_by_doc_id(doc_id)` for the article's `doc_id` to remove
  partially inserted chunks, entities, edges, and vectors.
- **LightRAG API used:** `adelete_by_doc_id(doc_id: str, delete_llm_cache: bool = False) -> DeletionResult`
  (confirmed present at `venv/Lib/site-packages/lightrag/lightrag.py:3223`).
- **`doc_id` source:** LightRAG auto-generates doc IDs as MD5-based hashes of content during
  `ainsert` UNLESS `ids=[...]` is passed. The rollback handler MUST know the `doc_id` BEFORE
  `ainsert` completes. Planner picks one of:
  - **(a) Explicit `ids=[doc_id]` at ainsert call site:** compute `doc_id = f"wechat_{article_hash}"`
    in `ingest_wechat.ingest_article` before `await rag.ainsert(full_content)`, pass
    `ids=[doc_id]`, record in an outer-scope registry (e.g., a closure or `rag._pending_doc_ids`
    dict keyed on task). On `TimeoutError`, orchestrator reads the registry and calls
    `adelete_by_doc_id`.
  - **(b) Compute-then-pass:** same as (a) but pass `doc_id` through `ingest_article` signature
    as a kwarg → orchestrator generates + tracks it, passes it down; cleaner but STATE-04
    change already touches the signature.
- **Plan picks (a)** as the default — less signature churn, matches existing `article_hash`
  convention. STATE-04 keeps `ingest_article` signature stable; STATE-02 only adds a
  `track_doc_id(hash, doc_id)` side channel (planner decides in-module registry OR
  orchestrator-owned dict).
- **Graph consistency requirement:** after rollback, zero orphan entity nodes, zero chunks
  without a parent doc, zero dangling vectors. `adelete_by_doc_id` is documented to handle this.
- **Quota:** embed quota MUST NOT be wasted on partial doc — the `adelete_by_doc_id` call itself
  doesn't re-embed (it deletes).
- **Verification:** unit test mocks `rag.ainsert` to `await asyncio.sleep(10)`, wraps with
  `asyncio.wait_for(..., timeout=0.5)`, catches `TimeoutError`, asserts
  `adelete_by_doc_id(doc_id)` was called exactly once with the tracked id.

### D-09.06 — Idempotent re-ingest after rollback (STATE-03)

- **Decision:** Re-running the same article after rollback MUST succeed without orphans or
  duplicate primary-key errors.
- **Implementation:** follows naturally from D-09.05 (rollback clears state) + LightRAG's own
  doc-id deduplication (if `ids=[doc_id]` is passed on re-ingest, LightRAG either overwrites or
  skips duplicates — planner verifies behavior against actual LightRAG source).
- **Verification:** unit test covered by STATE-03-specific test case:
  1. `ingest → force timeout → rollback` (from D-09.05)
  2. `ingest same article again (no timeout)`
  3. Assert: graph entity count + chunk count + vector count == clean-single-ingest baseline
  (captured in a prior fixture run). Counts compared via LightRAG's own introspection APIs or
  direct NanoVectorDB file inspection (planner picks).

### D-09.07 — `get_rag()` contract change (STATE-04) — BREAKING

- **Decision:** `get_rag()` signature changes from `async def get_rag()` to
  `async def get_rag(flush: bool = True) -> LightRAG`.
- **Behavior:**
  - `flush=True` (production default): returns a **fresh** `LightRAG` instance with cleared
    in-memory buffers (per D-09.04). Each call constructs a new instance.
  - `flush=False`: returns a fresh instance with on-disk state intact and no explicit buffer
    clear — same behavior as the OLD `get_rag()` that tests/spikes may rely on.
- **Docstring MUST state:** "Production code uses `flush=True`. Tests and spikes that need
  reuse of a prior `rag` instance pass `flush=False`." — this is the contract.
- **Breaking-change scope:** ALL of the following call sites MUST update in the SAME commit:
  1. `ingest_wechat.py:564` — `rag = await get_rag()` (cache-hit branch in `ingest_article`)
  2. `ingest_wechat.py:667` — `rag = await get_rag()` (main branch in `ingest_article`)
  3. `ingest_wechat.py:800` — `rag = await get_rag()` (in `ingest_pdf`)
  4. `batch_ingest_from_spider.py:482` — `rag = await get_rag()` (in `run`)
  5. `batch_ingest_from_spider.py:591` — `rag = await get_rag()` (in `ingest_from_db`)
  6. `enrichment/merge_and_ingest.py:133` — `rag = await get_rag()` (in `_ingest_to_lightrag`)
  7. `ingest_github.py:258` — `rag = await get_rag()` (production GitHub URL ingest)
  8. `multimodal_ingest.py:147` — `rag = await get_rag()` (production PDF ingest)
  9. `scripts/wave0_reembed.py:200,253` — re-embed script (non-production but called by ops)
  10. `scripts/phase0_delete_spike.py:98` — spike script (non-production)
- **Update strategy:** Production call sites 1–8 keep old behavior via `get_rag(flush=True)`
  which is the new default → **no source change needed at those call sites** (they can remain
  `await get_rag()` and get the new flush semantic automatically). However, plan MUST explicitly
  audit each site and add a code comment clarifying intent, because the behavior changed even
  if the syntax didn't. Scripts 9–10 (spikes) SHOULD be updated to `get_rag(flush=False)` to
  preserve their historical "reuse prior state" behavior.
- **Verification:** unit test calls `get_rag()` (default) twice, asserts either
  (a) returned objects are distinct instances (`a is not b`), OR
  (b) same instance but second call cleared pending-buffer state. Contract docstring captures
  which variant was chosen.

---

## Out of Scope (defer to later phases)

Per PRD § "Out of Scope":

- Vertex AI embedding migration (v3.3)
- Async Vision worker (Phase 10 — ARCH-02)
- Checkpoint/resume across crashes (v3.2)
- Vision provider circuit breaker (v3.2)
- Any batch-level concurrency (v3.2)

---

## Deferred Ideas (for future phases — DO NOT implement in Phase 9 plans)

- Smarter chunk-count estimation (exact token count instead of char/4800 approximation) — defer
  to Phase 11 if benchmark shows formula is systematically wrong.
- Explicit "pending buffer" introspection API on LightRAG — if fresh-instance flush turns out
  insufficient, escalate; not needed for v3.1 gate.
- Rollback telemetry / Cognee "partial ingest" memory — not needed; embed-quota savings alone
  justify the rollback.

---

## Claude's Discretion

Decisions intentionally left to the planner/implementer:

1. **TIMEOUT-02 idiom:** `timeout=120.0` vs `timeout=httpx.Timeout(120.0)` — planner picks per
   `openai` SDK version in `requirements.txt`.
2. **TIMEOUT-03 budget wrap site:** wrap outer `ingest_article` (full orchestration) vs inner
   `rag.ainsert` only — planner picks and documents in plan action. D-09.03 lists 3 options.
3. **STATE-02 doc-id registry location:** in-module dict on `ingest_wechat` vs orchestrator-
   owned dict — planner picks.
4. **STATE-01 flush mechanism:** fresh-instance construction vs LightRAG-internal-API call if
   one exists — planner investigates and picks.
5. **Test file naming/organization:** extend existing `test_lightrag_llm.py` or create new
   `test_timeout_state.py` — planner picks per single-responsibility.

---

## Success Criteria Reference

All 7 success criteria from `09-PRD.md` § "Success Criteria for Phase 9" are inherited verbatim.
Plans validate against them:

1. `LLM_TIMEOUT=300` respected (D-09.01 → Plan 09-00)
2. DeepSeek client 120s timeout (D-09.02 → Plan 09-00)
3. `wait_for` rollback proven (D-09.05 → Plan 09-01)
4. Rollback idempotency proven (D-09.06 → Plan 09-01)
5. Prior-run buffer NOT replayed (D-09.04 → Plan 09-01)
6. `get_rag()` contract documented (D-09.07 → Plan 09-01)
7. Phase 8 regression green + Phase 9 tests green (both plans — verification gate)

---

*Generated: 2026-04-29 — PRD express path, autonomous overnight execution.*
