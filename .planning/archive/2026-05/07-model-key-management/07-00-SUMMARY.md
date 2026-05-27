---
phase: 07-model-key-management
plan: 00
subsystem: infra
tags: [gemini, api-keys, rate-limiting, retry, embeddings, lightrag, cognee]

requires:
  - phase: 05-pipeline-automation
    provides: lightrag_embedding.py root module using gemini-embedding-2 (absorbed via D-09)
provides:
  - lib/ package (6 modules) with models, api_keys, rate_limit, llm_client, lightrag_embedding, __init__
  - Centralized API key rotation with OMNIGRAPH_GEMINI_KEY precedence + OMNIGRAPH_GEMINI_KEYS pool
  - Per-model AsyncLimiter singletons with OMNIGRAPH_RPM_<MODEL> env overrides (D-08)
  - Tenacity-based retry on 429/503 with limiter re-acquisition + key rotation
  - Inline COGNEE_LLM_API_KEY side-effect + refresh_cognee() helper (Amendment 4 — no bridge module)
  - embedding_func absorbed into lib/ (D-09) with root-shim back-compat
affects: [ingest_wechat, ingest_github, multimodal_ingest, kg_synthesize, query_lightrag, image_pipeline, cognee_wrapper]

tech-stack:
  added: [aiolimiter>=1.2.1, tenacity>=9.0.0]
  patterns: [per-model rate limiter singleton, retry-outside-limiter, env-var rotation side-effect]

key-files:
  created:
    - lib/__init__.py
    - lib/models.py
    - lib/api_keys.py
    - lib/rate_limit.py
    - lib/llm_client.py
    - lib/lightrag_embedding.py
    - tests/unit/test_models.py
    - tests/unit/test_api_keys.py
    - tests/unit/test_rate_limit.py
    - tests/unit/test_llm_client.py
    - tests/unit/test_lightrag_embedding.py
    - tests/integration/test_cognee_rotation.py
  modified:
    - lightrag_embedding.py (now a 12-line shim re-exporting from lib)
    - tests/conftest.py (extended with mock_lib_llm + reset_lib_state fixtures)
    - requirements.txt (pinned aiolimiter + tenacity)

key-decisions:
  - "D-02 SUPERSEDED (Hermes amendment 1): pure string model constants, no os.environ.get wrappers — single-user + git-as-deploy means git revert IS the rollback"
  - "Amendment 4: rotate_key() writes os.environ['COGNEE_LLM_API_KEY'] inline as a side-effect; refresh_cognee() is a 5-line @lru_cache.cache_clear() helper — no bridge module, no observer chain"
  - "Amendment 5: generate() and generate_sync() accept contents as str OR list of parts natively (multimodal); no direct genai.Client fallback needed in callers"
  - "D-09: lightrag_embedding.py absorbed into lib/ — root shim kept until Wave 1/2 importers migrate"
  - "D-10: EMBEDDING_MODEL default = 'gemini-embedding-2' (matches production state); RATE_LIMITS_RPM covers both gemini-embedding-001 and gemini-embedding-2"

patterns-established:
  - "Rate limiter: one AsyncLimiter per model, cached in module-level dict, OMNIGRAPH_RPM_<MODEL> env override"
  - "Retry: @retry wraps outside `async with limiter` — re-acquires slot on retry, avoids fairness bugs"
  - "Key rotation: current_key() reads pool head; rotate_key() advances head + writes COGNEE_LLM_API_KEY; refresh_cognee() clears @lru_cache"
  - "Test mocking: fixtures patch lib.llm_client.generate / aembed / generate_sync (D-06 — lib-level, not vendor-SDK-level)"

requirements-completed: [D-02, D-04, D-06, D-08, D-09, D-10]

duration: ~4h (Hermes autonomous + orchestrator)
completed: 2026-04-28
---

# Phase 7 Wave 0 Summary

**lib/ package with centralized Gemini key rotation, per-model rate limiting, tenacity retry with 429/503 rotation, and D-09 lightrag_embedding absorption — all behind a clean facade ready for 18 call-site migrations.**

## Performance

- **Duration:** ~4h (split across Hermes autonomous sessions + local orchestration)
- **Completed:** 2026-04-28
- **Tasks:** 7 (per Hermes Amendment 0 — aligned Wave 0 with D-03 per-task commit policy)
- **Files modified:** 15 (12 new + 3 modified)

## Accomplishments

- Centralized model constants (`INGESTION_LLM`, `VISION_LLM`, `SYNTHESIS_LLM`, `EMBEDDING_MODEL`, `GITHUB_INGEST_LLM`) as pure strings
- Key rotation API (`current_key`, `rotate_key`, `on_rotate`) with multi-account pool support and inline Cognee env sync
- Per-model `AsyncLimiter` singletons with D-08 `OMNIGRAPH_RPM_<MODEL>` env overrides
- Tenacity retry (`@retry` + `retry_if_exception` predicate, `wait_exponential`) for 429/503 only; never 400/401/403
- Multimodal `generate_sync(contents=str | list[types.Part])` — no caller needs to drop to `genai.Client` directly
- D-09 absorption: `lightrag_embedding.py` internals now use `current_key()` + `EMBEDDING_MODEL` from lib; root becomes 12-line shim
- Wave 0 test suite: 42 unit tests + 3 integration tests — all green; Parity assertion (Amendment 2) confirms root shim is `is` the same object as `lib.embedding_func`

## Task Commits

1. **Task 1: lib/models.py with pure-string constants (Amendment 1; D-10 embedding-2)** — `487784c` (feat)
2. **Task 2: lib/api_keys.py with rotation + COGNEE_LLM_API_KEY side-effect + refresh_cognee (Amendment 4)** — `7710abf` (feat)
3. **Task 3: lib/rate_limit.py with D-08 OMNIGRAPH_RPM_* env override** — `5f0893b` (feat)
4. **Task 4: lib/llm_client.py with @retry + rotation + native multimodal contents (Amendment 5)** — `515ade8` (feat)
5. **Task 5: D-09 absorb lightrag_embedding into lib/ + root shim + parity assertion (Amendment 2)** — `9d7ca5c` (feat)
6. **Task 6: conftest lib-level mocks (D-06) + cognee-rotation integration test (Amendment 4)** — `da1a0fc` (feat)
7. **Task 7: pin aiolimiter>=1.2.1,<2.0 and tenacity>=9.0.0,<9.2.0** — `d08677b` (feat)

**Plan metadata:** `40c0c11` (chore: flip wave_0_complete to true — 7/7 commits landed + all tests green)

## Decisions Made

See key-decisions in frontmatter. Post-Hermes-review amendments (recorded in `07-CONTEXT.md`) superseded original D-02 (env overrides) and replaced the formal `cognee_bridge.py` module with inline rotation side-effects. Plan executed faithfully to the amended contract.

## Deviations from Plan

None — plan was amended before execution (Hermes review Option B) rather than during, so execution matched the revised plan exactly.

## Issues Encountered

- Stale `__pycache__` caused `EMBEDDING_DIM` mismatch (768 vs 3072) in `test_lightrag_embedding.py`; resolved by wiping caches. Not a code defect.
- 4 pre-existing test failures in `test_fetch_zhihu.py` + `test_image_pipeline.py` confirmed as Phase 4 regressions (present on unmodified `main`), not Phase 7 responsibility.

## Next Phase Readiness

- `lib/` is importable from repo root; 13 public symbols exposed via `lib/__init__.py`
- Wave 1 (07-01) consumed the D-09 shim and dropped its `from lightrag_embedding import` to `from lib import embedding_func`
- Ready for Wave 2 mass migration of the 7 remaining P0 files

---
*Phase: 07-model-key-management*
*Completed: 2026-04-28*
