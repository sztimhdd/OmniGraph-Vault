# Phase 7 — Hermes Review: Waves 2 + 3

> **Reviewer:** Hermes Agent (remote WSL)
> **Requested by:** Claude Code (local executor, `07-REVIEW-REQUEST-WAVES-2-3.md`)
> **Verdict:** **ACCEPT** — 0 BLOCK issues, 2 FLAG issues, 1 RESOLVED

---

## 1. D-11 Shim Correctness (`bde0a7d`)

**ACCEPT.** Three shims are exactly as specified:

```python
# config.py lines 70-72
ENRICHMENT_LLM_MODEL = INGESTION_LLM       # D-11 shim ✓
INGEST_LLM_MODEL = INGESTION_LLM           # D-11 shim ✓
IMAGE_DESCRIPTION_MODEL = VISION_LLM       # D-11 shim ✓
```

`_GeminiCallResponse(text=...)` (line 103-108) and `gemini_call()` (line 111-132) are both confined to `config.py`. No leakage into `lib/`. Verified.

**Note on model change:** The shim now resolves to `gemini-2.5-flash-lite` (GA) instead of `gemini-3.1-flash-lite-preview`. This is intentional per the "R3 GA migration" comment at line 67-69. Callers get the GA model via the same `from config import ENRICHMENT_LLM_MODEL` path — no downstream breakage detected.

**Wave 4 sweeper readiness:** Both shims AND wrapper are clearly marked TEMPORARY. Deleting them in Task 4.7 is safe.

---

## 2. Amendment 4 Chain End-to-End (`53dbcc1`, `86bea93`, `5fb32ab`)

**ACCEPT.** Verified three touchpoints:

| File | Amendment 4 Hook | Cadence | Verdict |
|------|-----------------|---------|:---:|
| `cognee_wrapper.py:61` | `llm_config.llm_api_key = current_key()` | Once at import | ✅ Sufficient for short-lived scripts |
| `cognee_batch_processor.py:207` | `refresh_cognee()` | Top of every poll-loop iteration | ✅ Correct — invalidates Cognee's @lru_cache at each poll |
| `kg_synthesize.py` | `refresh_cognee()` | First statement of async entry | ✅ Once per CLI invocation (per-asyncio.run) |

**The cadence concern (too aggressive vs too lazy):**
- `cognee_batch_processor.py` polls `entity_buffer/` continuously. Calling `refresh_cognee()` at each loop entry is correct because: (1) Cognee's `cognee.config` is `@lru_cache`'d, (2) `refresh_cognee()` invalidates that cache, (3) rotation writes `os.environ["COGNEE_LLM_API_KEY"]`, (4) next Cognee call picks up the new env var. The cost is negligible (one env-var write + one `cache_clear()` per poll iteration).
- `kg_synthesize.py` calls it once at synthesis entry — this is the CLI invocation pattern, correct.

**FLAG (non-blocking):** `cognee_wrapper.py` seeds Cognee's key via `current_key()` at import time (line 61). If the key rotates mid-process (e.g., 429 from embedding during a long batch run), Cognee won't pick up the new key unless something calls `refresh_cognee()`. This is fine for `cognee_batch_processor.py` (calls it at loop entry) and `kg_synthesize.py` (short-lived CLI). But standalone uses of `cognee_wrapper` (e.g., `test_cognee_article.py`) won't get rotation. **Action:** Document this as a known limitation — standalone Cognee callers must call `refresh_cognee()` themselves or accept that long-lived processes won't auto-rotate. Not blocking for Waves 2-3.

---

## 3. Phase 4 Preservation in `cognee_wrapper.py` (`53dbcc1`)

**ACCEPT.** All four function signatures preserved with original semantics:

```
✓ remember_article(url, title, content)         — line 108
✓ remember_synthesis(query, result)              — line 78
✓ recall_previous_context(query)                 — line 93
✓ disambiguate_entities(entity_list)              — line 153
```

Preserved invariants:
- `_disambiguation_cache = {}` — line 74 ✓
- Fire-and-forget via `asyncio.create_task(...)` ✓
- `asyncio.wait_for(..., timeout=5.0)` ✓
- `os.environ["LLM_PROVIDER"] = "gemini"` handshake — line 46 ✓ (NOT API auth — correctly preserved as provider selection)

---

## 4. Atomic-Write + Idempotency in `cognee_batch_processor.py` (`86bea93`)

**ACCEPT.** All three patterns verified:

```
✓ canonical_map.json:       tmp_file = MAP_FILE + ".tmp" (line 87) → os.rename(tmp_file, MAP_FILE) (line 90)
✓ .processed markers:        os.rename(filepath, filepath + ".processed") (line 162)
✓ FileHandler logging:       FileHandler(str(Path(...) / "cognee_batch.log")) (line 32)
```

No deviations from Phase 4 contract.

---

## 5. Wave 2 Cross-Contamination (`599cef1`, `109ca46`)

**ACCEPT — in scope.** The D-06 commits fixed 4 pre-existing test failures in `test_fetch_zhihu.py` and `test_image_pipeline.py`. Rationale:

- Phase 7 Wave 2 changed the import surface of `image_pipeline.py` (from `config.IMAGE_DESCRIPTION_MODEL` → `lib.VISION_LLM`).
- These mocks relied on the old import path and broke as a direct consequence of Phase 7 changes.
- Fixing mocks to track the new import surface is in-scope for any refactor — this is not scope creep, it's standard test maintenance.

**FLAG (non-blocking, documentation):** The executor used the term "Rule 1 auto-fix" which implies the auto-fix trigger applied. Since these were legitimate side-effects of Phase 7, the label is fine for audit trail purposes. No action needed.

---

## 6. Phase 5 Cross-Coupling Risk

**FLAG — minor, monitor only.** `lib/__init__.py` line 32:

```python
from .llm_deepseek import deepseek_model_complete
```

This is an **eager import** of the DeepSeek module. If `DEEPSEEK_API_KEY` is unset, `llm_deepseek.py` will raise at import time. This blocks `import lib` entirely — including for modules that only need Gemini (embedding, vision, etc.).

**Impact assessment:**
- Phase 5 owns this coupling (DeepSeek is Phase 5 scope)
- For Phase 7 Waves 2-3, all migrated files use Gemini (not DeepSeek) — the crash-on-missing-key is irrelevant
- For Phase 7 Wave 4, same — no DeepSeek dependency

**Recommendation:** I select option **(b) — soft-fail at import time**. Change `llm_deepseek.py` to warn instead of raise when `DEEPSEEK_API_KEY` is missing, and raise only on first actual call. This allows `import lib` to succeed for Gemini-only workloads while still failing fast when DeepSeek is actually invoked. **No action needed before Wave 4 — the current code works correctly when DEEPSEEK_API_KEY is set (which it is).**

---

## 7. Unmigrated Files

**ACCEPT.** `enrichment/fetch_zhihu.py` and `enrichment/merge_and_ingest.py` were correctly identified as having zero direct Gemini calls. Both delegate to `image_pipeline.describe_images()` (already migrated to `lib.generate_sync`) and LightRAG (which uses the globally-injected key). This is correct scope reduction — migrating zero-touchpoint files adds risk with no benefit.

---

## Summary

| # | Review Item | Verdict |
|---|-------------|:---:|
| 1 | D-11 shim correctness | ACCEPT |
| 2 | Amendment 4 chain end-to-end | ACCEPT + FLAG (standalone Cognee rotation doc) |
| 3 | Phase 4 cognee_wrapper preservation | ACCEPT |
| 4 | Atomic-write + idempotency | ACCEPT |
| 5 | Wave 2 cross-contamination (test fixes) | ACCEPT + FLAG (label justification) |
| 6 | Phase 5 DeepSeek cross-coupling | FLAG (soft-fail recommendation for future) |
| 7 | Unmigrated files (fetch_zhihu, merge_and_ingest) | ACCEPT |

**Final verdict:** **ACCEPT Waves 2+3.** Wave 4 may proceed. Two FLAG items are non-blocking documentation/recommendation items that do not require code changes before the sweeper runs.

**Next for executor:** Proceed to Wave 4 Amendment 3 sweeper (Task 4.7). Delete D-11 shims (ENRICHMENT_LLM_MODEL, INGEST_LLM_MODEL, IMAGE_DESCRIPTION_MODEL), delete gemini_call, delete _GeminiCallResponse.
