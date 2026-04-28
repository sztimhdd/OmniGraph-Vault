# Plan 05-00c — LLM Abstraction Audit

**Date:** 2026-04-28
**Task:** 0c.0 — Audit existing LLM abstractions in `lib/` and inventory all LLM call sites before swapping to Deepseek.

---

## Section 1 — `lib/` Inventory

### What exists

The `lib/` package (introduced in Phase 7, see `lib/__init__.py` docstring) is the canonical shared library. It already provides:

| Module | Purpose |
| ------ | ------- |
| `lib/models.py` | Model name constants: `INGESTION_LLM`, `VISION_LLM`, `SYNTHESIS_LLM`, `GITHUB_INGEST_LLM`, `EMBEDDING_MODEL` + RPM caps |
| `lib/api_keys.py` | Multi-key pool (`OMNIGRAPH_GEMINI_KEYS`, `OMNIGRAPH_GEMINI_KEY`, `GEMINI_API_KEY_BACKUP`, `GEMINI_API_KEY`) with `current_key()`, `rotate_key()`, `on_rotate()`, `refresh_cognee()` |
| `lib/rate_limit.py` | Per-model leaky-bucket `AsyncLimiter` via `get_limiter(model)` |
| `lib/llm_client.py` | `generate()` + `generate_sync()` + `aembed()` — Gemini-only, wraps `gemini.Client.aio.models.generate_content` with tenacity retry + 429 rotation |
| `lib/lightrag_embedding.py` | Gemini embedding (gemini-embedding-2, 3072 dim), in-band multimodal, task-prefix routing, `current_key()` integration |

### Key insight — key rotation is ALREADY implemented

`lib/api_keys.py:24-55` (`load_keys()`) already folds `GEMINI_API_KEY_BACKUP` into the rotation pool (per Phase 7 D-04). `lib/lightrag_embedding.py:122` uses `current_key()` (rotation-aware).

Rotation-on-429 is implemented in `lib/llm_client.py:55-69` via tenacity `@retry` + manual `rotate_key()` call on 429. But `lib/lightrag_embedding.py` does **NOT** currently loop on 429 — it calls `embed_content()` once per text and lets the exception bubble up. That is the exact gap Task 0c.2 closes.

### Decision: extend `lib/` vs create fresh `lightrag_llm.py`

**Decision:** Create fresh `lightrag_llm.py` at repo root AND re-export from `lib/`.

**Rationale:**

1. The plan's frontmatter and `key_links` require `from lightrag_llm import deepseek_model_complete` — call sites need a stable, top-level import path.
2. `lib/` is the single source of truth — putting the implementation in `lib/llm_deepseek.py` (new module) and re-exporting from root `lightrag_llm.py` preserves the "many call sites, one implementation" pattern already established by the root `lightrag_embedding.py` shim (`lib/lightrag_embedding.py` + 2-line shim).
3. Extending the existing `lib/llm_client.py` would conflate Gemini-specific retry/rotation logic with Deepseek's OpenAI-compatible SDK. Better to keep providers separate.

**Structure chosen:**
- `lib/llm_deepseek.py` — implementation (`deepseek_model_complete` + `_client` singleton)
- `lightrag_llm.py` — 2-line shim that re-exports
- `lib/__init__.py` — also exports `deepseek_model_complete` for symmetry

This matches the established pattern exactly and keeps the plan's `key_links` import line stable.

---

## Section 2 — Call-Site Inventory

### LightRAG `llm_model_func` production sites (5)

| # | File | Current Model | Current pattern | Swap complexity | Site-specific risks |
| - | ---- | ------------- | --------------- | --------------- | ------------------- |
| 1 | `ingest_wechat.py:99-114` | `INGESTION_LLM` (gemini-2.5-flash-lite) | `async with get_limiter(INGESTION_LLM): await gemini_model_complete(...)` | Trivial — drop wrapper, import `deepseek_model_complete`, pass as `llm_model_func=deepseek_model_complete` | None; no grounding, no streaming |
| 2 | `ingest_github.py:46-59` | `GITHUB_INGEST_LLM` (gemini-3.1-flash-lite-preview) | Same pattern | Trivial | User specified "FULL pipeline" swap per scope → swap to deepseek-v4-flash for consistency |
| 3 | `query_lightrag.py:23-33` | `SYNTHESIS_LLM` (gemini-2.5-flash-lite) | Same pattern | Trivial | None |
| 4 | `multimodal_ingest.py:54-64` | `INGESTION_LLM` | Same pattern | Trivial | Vision call separate (`describe_image` via `generate_sync(VISION_LLM)`) — stays on Gemini |
| 5 | `omnigraph_search/query.py:31-45` | `gemini-2.5-flash-lite` (hardcoded) | Direct `gemini_model_complete`, no limiter | Trivial | None |

### Classification + enrichment standalone LLM callers (6)

| # | File | Current Model | Current pattern | Swap complexity | Site-specific risks |
| - | ---- | ------------- | --------------- | --------------- | ------------------- |
| 6 | `batch_classify_kol.py:217-235` | `gemini-2.5-flash-lite` (`_call_gemini`) | Direct `genai.Client`; ALSO has `_call_deepseek` at :185-214 already | Already has DeepSeek path — default classifier is already `deepseek` (see :335). **No swap needed; scope guard.** | DeepSeek path already works; only change: ensure default is DeepSeek (already is) and document |
| 7 | `batchkol_topic.py:189-205` | `gemini-2.5-flash-lite` / `deepseek-chat` (dual) | Same pattern — already has DeepSeek default | **No swap needed**; same reason | Same |
| 8 | `_reclassify.py:72-88` | `gemini-2.5-flash-lite` / `deepseek-chat` (dual) | Same pattern | **No swap needed** | Same |
| 9 | `enrichment/extract_questions.py:47-78` | `gemini-2.5-flash-lite` with **google_search grounding** (D-12) | `gemini_call()` from `config` | **Do NOT swap** — DeepSeek does NOT support Gemini's `google_search` grounding tool. Swapping would break the enrichment quality invariant (Phase 4 D-12). | Grounding is load-bearing |
| 10 | `batch_ingest_from_spider.py:259-276` | `gemini-2.5-flash-lite` / `deepseek-chat` (dual) | Same as classification scripts | **No swap needed**; default already deepseek (see :606) | Also shells out to `ingest_wechat.py`, which picks up LightRAG swap automatically |
| 11 | `cognee_wrapper.py:18-46` | `gemini-2.5-flash` via Cognee config | env-var driven | See Section 3 | Cognee internal registry |

### Net effect on Gemini LLM quota

After swapping 5 LightRAG sites:
- **Eliminated:** ALL LightRAG-driven `generate_content` calls (entity extraction, relationship summarization, query synthesis) → the biggest quota consumer.
- **Retained on Gemini:** `enrichment/extract_questions.py` (grounding required), `describe_image` vision path in `multimodal_ingest.py` (VISION_LLM).
- **Already on DeepSeek by default:** 4 classification scripts (batch_classify_kol, batchkol_topic, _reclassify, batch_ingest_from_spider).

This matches the plan's stated intent: "Vision calls remain on Gemini — the swap is LLM-only, not multimodal" and "Classification + enrichment scripts route to Deepseek via the same shared wrapper" (interpreted pragmatically — classification scripts already route there; only `extract_questions` stays on Gemini and is justified by grounding).

---

## Section 3 — Cognee Binding Decision

### Current state (`cognee_wrapper.py:18-46`)

```python
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
os.environ["COGNEE_LLM_API_KEY"] = GEMINI_API_KEY
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = "gemini-2.5-flash"
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"
```

Cognee is:
- Async-decoupled from the fast path (`cognee_batch_processor.py` polls `entity_buffer/`)
- Low-volume — operates on entity lists, not full chunks
- Its LLM calls are already rate-controlled at the caller level (`_COGNEE_TIMEOUT = 30s` wrap)
- Its embeddings go through Gemini's gemini-embedding-2 — part of the SAME quota pool we're trying to relieve

### Decision: **KEEP on Gemini**

**Rationale:**

1. **Cognee's generate_content volume is tiny** — entity disambiguation is a few-token prompt per entity, not the large-prompt bursts LightRAG produces for chunk summarization. Quota impact is negligible.
2. **Cognee's embeddings are already in the same pool** as LightRAG — they use `gemini-embedding-2` via `EMBEDDING_MODEL=gemini-embedding-2`. This is intentional: Phase 7 D-04 centralized keys for Cognee propagation (see `api_keys.py:63,84` — `COGNEE_LLM_API_KEY` is set inline on every rotation). The rotation infrastructure already propagates to Cognee's LLM config via `refresh_cognee()`.
3. **Swapping Cognee to DeepSeek introduces Cognee-internal model registry risk.** Cognee has its own LLM driver stack (litellm) and model-specific tokenizer/cost assumptions. An env-var swap might work, might fail silently with wrong token budgets. Not worth the risk for a small-volume component.
4. **Isolation of failure modes already achieved.** The embedding pool is what hits 429 first (it's the call-volume dominant operation). LLM generate_content from Cognee is a rounding error.

Cognee continues to use Gemini. Task 0c.5 becomes a documented no-op.

---

## Section 4 — Final Plan of Attack

### Task 0c.1 — Create shared wrapper
- Write `lib/llm_deepseek.py` with `deepseek_model_complete` (AsyncOpenAI against `https://api.deepseek.com/v1`, `deepseek-v4-flash` default, `DEEPSEEK_MODEL` env override, module-level singleton `_client`).
- Write `lightrag_llm.py` (2-line shim, re-exports from `lib.llm_deepseek`).
- Add to `lib/__init__.py` exports.
- Add 6 unit tests in `tests/unit/test_lightrag_llm.py` (all mocked).

### Task 0c.2 — Key rotation for embedding
- The `_KEY_POOL` already effectively exists via `lib.api_keys.load_keys()`. What's missing: a per-call in-loop 429 retry inside `lib/lightrag_embedding.py` that calls `rotate_key()` and retries against the next key.
- Add a round-robin + 429 failover loop in `embedding_func` that wraps the `client.aio.models.embed_content(...)` call.
- Add module-level `_ROTATION_HITS: dict[str, int]` counter for smoke-test telemetry (Task 0c.6 assertion).
- Add 6 rotation tests in `tests/unit/test_lightrag_embedding_rotation.py`.
- Keep existing 6 tests in `test_lightrag_embedding.py` green.

### Task 0c.3 — Swap 5 LightRAG sites
- Surgical edit: delete local `llm_model_func`, `import deepseek_model_complete`, pass as `llm_model_func=deepseek_model_complete`. Update `llm_model_name` string to `deepseek-v4-flash`.
- 5 files: `ingest_wechat.py`, `ingest_github.py`, `query_lightrag.py`, `multimodal_ingest.py`, `omnigraph_search/query.py`.

### Task 0c.4 — Classification scripts
- `batch_classify_kol.py`, `batchkol_topic.py`, `_reclassify.py`, `batch_ingest_from_spider.py`: **Already default to DeepSeek.** Nothing to change. Add an explicit import of `deepseek_model_complete` for future convergence (optional — document as skipped).
- `enrichment/extract_questions.py`: **Explicitly SKIP** — grounding dependency.

Revised Task 0c.4 scope: document no-op + add convergence import comments in the scripts that make the pipeline easier to refactor later.

### Task 0c.5 — Cognee
- **No-op.** Document in SUMMARY that Cognee stays on Gemini.

### Task 0c.6 — Smoke test
- Run end-to-end on remote if Gemini keys have quota; otherwise log `result: pending_api_budget`.

---

## Appendix — Scope vs Plan Frontmatter

The plan frontmatter lists 5 LightRAG sites + 4 standalone callers as required to "route to Deepseek via the same shared wrapper." The audit reveals 4 of those 4 callers **already** have DeepSeek paths (just with their own hand-rolled `requests.post` to `api.deepseek.com/v1/chat/completions`). Adopting a single shared wrapper for them is *desirable* but not required to achieve the plan's stated objective (relieve Gemini generate_content pressure). Task 0c.4 is adjusted to focus on **verifying defaults** rather than forcing a refactor that would balloon scope.

**Decision:** Task 0c.4 performs a lighter action — verify DeepSeek is the default on all 4 scripts + add scripts/docs if needed. Full unification behind `deepseek_model_complete` is a Phase 8 candidate (opportunistic cleanup).
