---
phase: 07-model-key-management
plan: 03
subsystem: infra
tags: [gemini, cognee, rotation, amendment-4, p1-migration, cache-invalidation]

requires:
  - phase: 07-model-key-management
    provides: Wave 0 lib/ package + Wave 2 P0 migration + kg_synthesize.py Cognee init
provides:
  - Cognee-adjacent P1 files (cognee_wrapper, cognee_batch_processor, extract_questions, init_cognee, setup_cognee) migrated to lib/
  - Amendment 4 Cognee-rotation chain live end-to-end — rotate_key() writes os.environ["COGNEE_LLM_API_KEY"] inline + refresh_cognee() clears @lru_cache at poll-loop / synthesis-entry points
affects: [cognee_wrapper, cognee_batch_processor, kg_synthesize, extract_questions, init_cognee, setup_cognee]

tech-stack:
  added: []
  patterns:
    - "Amendment 4 cache invalidation — refresh_cognee() called at top of run_batch() poll loop (cognee_batch_processor.py) and synthesize_response() entry (kg_synthesize.py)"
    - "Phase 4 fire-and-forget preservation — cognee_wrapper function signatures (remember_article/remember_synthesis/recall_previous_context/disambiguate_entities) and asyncio.wait_for timeouts left intact; only LLM plumbing swapped underneath"

key-files:
  created: []
  modified:
    - cognee_wrapper.py
    - cognee_batch_processor.py
    - kg_synthesize.py
    - enrichment/extract_questions.py
    - init_cognee.py
    - setup_cognee.py

key-decisions:
  - "D-03 honored: 6 atomic commits (one file per commit, Task 3.4 split into 3.4a init_cognee + 3.4b setup_cognee)"
  - "Amendment 4 two-hook pattern landed: refresh_cognee() at cognee_batch_processor.run_batch entry AND at kg_synthesize.synthesize_response entry — covers both long-running consumers of Cognee"
  - "cognee_wrapper.py preserves Cognee handshake env vars verbatim (LLM_PROVIDER='gemini', EMBEDDING_PROVIDER='gemini', EMBEDDING_MODEL='gemini-embedding-2', COGNEE_SKIP_CONNECTION_TEST='true', ENABLE_BACKEND_ACCESS_CONTROL='false') — these configure Cognee's LLM/embedding backend identity, not Gemini API auth. Only LLM_MODEL was pivoted from hardcoded 'gemini-2.5-flash' to lib.INGESTION_LLM."
  - "enrichment/extract_questions.py: DEFAULT_MODEL = os.environ.get('ENRICHMENT_LLM_MODEL', INGESTION_LLM) — the env override pattern in the original file is preserved; the new fallback is lib.INGESTION_LLM instead of the hardcoded string (semantic clarity kept)."
  - "cognee_batch_processor.py: removed the gemini_client parameter from process_buffer_file and process_db_entities (lib.generate_sync handles client caching + key rotation internally). Function signatures were internal-only (not a public API), safe to change."
  - "Tests were already pivoted to lib.llm_client.generate mocks in Wave 2 (D-06 surgical updates); no test patch-target changes required this wave."

requirements-completed: [D-03]

metrics:
  duration: "~25 min (Claude executor, autonomous)"
  completed: "2026-04-28"
  tasks_completed: 7
  files_modified: 6
  commits: 6

---

# Phase 7 Plan 03: Wave 3 P1 Migration + Amendment 4 Cognee-Rotation Chain Summary

**Five Cognee-adjacent P1 files migrated to lib/ plus a one-line Amendment 4 patch on kg_synthesize.py — the refresh_cognee() + env-var-write rotation chain now exercised by real production code paths (cognee_batch_processor poll loop, kg_synthesize synthesis entry, cognee_wrapper init). Pytest suite held green at 109/109 across all 6 commits; integration test tests/integration/test_cognee_rotation.py remained green throughout.**

## Performance

- **Duration:** ~25 min (Claude executor, autonomous — no checkpoints besides the terminal one)
- **Completed:** 2026-04-28
- **Tasks:** 7 (3.1, 3.2, 3.2.5, 3.3, 3.4a, 3.4b, 3.5 checkpoint)
- **Files modified:** 6
- **Commits:** 6 (atomic per D-03)

## Accomplishments

### Task 3.1 — cognee_wrapper.py (commit `53dbcc1`)
- Replaced module-level `GEMINI_API_KEY = os.environ.get(...)` with `current_key()` from lib
- `llm_config.llm_api_key = current_key()` (Amendment 4 init pattern, mirrors kg_synthesize.py Wave 2)
- Replaced hardcoded `"gemini-2.5-flash"` with `lib.INGESTION_LLM`
- **Preserved** all 4 Phase 4 fire-and-forget function signatures (`remember_article`, `remember_synthesis`, `recall_previous_context`, `disambiguate_entities`) — Phase 4 contract
- **Preserved** `_disambiguation_cache = {}` module-level dict + `asyncio.wait_for(..., timeout=...)` patterns
- **Preserved** Cognee handshake env vars (`LLM_PROVIDER='gemini'`, `EMBEDDING_PROVIDER='gemini'`, `EMBEDDING_MODEL='gemini-embedding-2'`, `COGNEE_SKIP_CONNECTION_TEST`, `ENABLE_BACKEND_ACCESS_CONTROL`) — Cognee backend identity, not Gemini SDK calls

### Task 3.2 — cognee_batch_processor.py (commit `86bea93`)
- Replaced `genai.Client(api_key=GEMINI_API_KEY)` instantiation in `run_batch()` with lib-managed client
- Both `process_buffer_file` and `process_db_entities` now call `lib.generate_sync(INGESTION_LLM, prompt, config=...)` — removed the `gemini_client` / `client` parameter (internal signature; lib handles key caching + rate limit + retry + rotation)
- **Amendment 4:** `refresh_cognee()` called as first statement in `run_batch()` — invalidates Cognee's `@lru_cache` so rotated keys land on the next poll cycle
- **Preserved** atomic write for `canonical_map.json` (`.tmp` + `os.rename`) — CLAUDE.md convention
- **Preserved** `.processed` marker writes (Phase idempotency)
- **Preserved** `FileHandler` logging to `cognee_batch.log`
- **Preserved** DB-first + file-buffer poll discovery + `_RATE_LIMIT_SECONDS` sleep

### Task 3.2.5 — kg_synthesize.py Amendment 4 one-line patch (commit `5fb32ab`)
- Added `refresh_cognee` to the existing `from lib import ...` line
- Added `refresh_cognee()` as first statement inside `synthesize_response(query_text, mode)` with Amendment-4 citation comment for greppability
- Wave 2 Task 2.4 migration state otherwise untouched (surgical change — one line + one import token)

### Task 3.3 — enrichment/extract_questions.py (commit `221b898`)
- Replaced `from config import gemini_call` + `gemini_call(...)` call with `from lib import INGESTION_LLM, generate_sync` + `generate_sync(DEFAULT_MODEL, ..., config=config)`
- `DEFAULT_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", INGESTION_LLM)` — env override preserved; hardcoded fallback swapped for lib constant
- `GROUNDING_ENABLED` behavior preserved (google_search Tool kwarg still flows through)
- Response-text access simplified from `response.text or ""` to `generate_sync(...) or ""` (the sync wrapper already returns `.text`)
- Tests in `tests/unit/test_extract_questions.py` already pivoted to `lib.llm_client.generate` mocks in Wave 2 D-06 — no test edits needed. All 7 pass.

### Task 3.4a — init_cognee.py (commit `7073eff`)
- `os.environ['GOOGLE_API_KEY'] = current_key()` (was `os.environ.get('GEMINI_API_KEY', '')`)
- **Preserved** Cognee handshake vars: `LLM_PROVIDER='gemini'`, `LLM_MODEL='gemini/gemini-1.5-pro'`, `EMBEDDING_PROVIDER='gemini'`, `EMBEDDING_MODEL='gemini/text-embedding-004'`, `EMBEDDING_DIMENSIONS='768'`, `COGNEE_SKIP_CONNECTION_TEST='true'` — these are litellm-qualified model names that Cognee expects verbatim; not Gemini SDK model selectors

### Task 3.4b — setup_cognee.py (commit `2892d2f`)
- Deleted the hand-rolled `~/.hermes/.env` parsing loop entirely; `lib.current_key()` (via lib.api_keys.load_keys → config.load_env) handles env loading
- `_key = current_key()` fed into `LLM_API_KEY`, `GOOGLE_API_KEY`
- **Preserved** same Cognee handshake vars as init_cognee.py

## Commit Hashes

1. **Task 3.1:** `53dbcc1` — refactor(07-03): migrate cognee_wrapper.py to lib/ (Phase 4 semantics preserved)
2. **Task 3.2:** `86bea93` — refactor(07-03): migrate cognee_batch_processor.py to lib/ + Amendment 4 refresh_cognee at poll loop
3. **Task 3.2.5:** `5fb32ab` — refactor(07-03): kg_synthesize.py add refresh_cognee() at synthesis entry (Amendment 4)
4. **Task 3.3:** `221b898` — refactor(07-03): migrate enrichment/extract_questions.py to lib/
5. **Task 3.4a:** `7073eff` — refactor(07-03): migrate init_cognee.py to lib/
6. **Task 3.4b:** `2892d2f` — refactor(07-03): migrate setup_cognee.py to lib/

## Wave 3 Verification Gates

### Integration test (Task 3.5 Step A)
```
$ DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/integration/test_cognee_rotation.py -v
tests/integration/test_cognee_rotation.py::test_rotate_sets_env_and_refresh_clears_cache PASSED
tests/integration/test_cognee_rotation.py::test_rotate_propagates_fresh_key_after_cache_clear PASSED
tests/integration/test_cognee_rotation.py::test_refresh_cognee_calls_cache_clear PASSED
======================= 3 passed, 9 warnings in 10.17s ========================
```
**Result: PASS (3/3).** Amendment 4 env-var write + cache-clear chain verified by existing Wave 0 fixtures. No source edits to the integration test required this wave.

### Full test suite (Task 3.5 Step B)
```
$ DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/ --tb=no -q
109 passed, 14 warnings in 15.14s
```
**Result: PASS (109/109).** Matches the Wave 2 exit baseline exactly — zero regressions from the 6 Wave 3 commits.

Baseline without DEEPSEEK_API_KEY: 11 failed / 69 passed / 29 errors — consistent with Wave 2 SUMMARY's documented Phase 5 Plan 05-00c cross-coupling (lib/__init__.py imports `deepseek_model_complete` which raises at module import time if `DEEPSEEK_API_KEY` is unset). Not a Wave 3 regression.

### Live kg_synthesize smoke (Task 3.5 Step C)
**Deferred to remote PC per 07-VALIDATION.md "Manual-Only Verifications" row "End-to-end kg_synthesize + Cognee rotation".** The live smoke requires real Gemini API calls + the deployed Cognee DB + populated LightRAG graph — local Windows dev env has none of these in place. Integration test (Step A) covers the Amendment 4 env-var + cache-clear surface programmatically; a real rotation event against live Cognee can be exercised on the remote Hermes PC when Wave 4 deploy verification runs.

## Amendment 4 Chain — Final State

```
rotate_key()                                  [lib/api_keys.py — Wave 0]
  └─ os.environ["COGNEE_LLM_API_KEY"] = new   [inline write — no bridge module]

cognee_wrapper.py (init)                      [Wave 3 Task 3.1]
  └─ llm_config.llm_api_key = current_key()   [seeds @lru_cache'd config singleton]

cognee_batch_processor.py (poll loop)         [Wave 3 Task 3.2]
  └─ refresh_cognee() at run_batch() entry    [invalidates @lru_cache per cycle]

kg_synthesize.py (synthesis entry)            [Wave 3 Task 3.2.5]
  └─ refresh_cognee() at synthesize_response  [invalidates @lru_cache per query]
```

Real production code now exercises both sides of the Amendment 4 chain (env-var write + cache clear). No bridge module, no observer pattern, no listener registration — exactly what Amendment 4 spec prescribed.

## Deviations from Plan

### Minor scope simplification — cognee_batch_processor internal signature change
**Trigger:** Plan Step D said "swap `genai.Client(api_key=...)` for `api_key=current_key()`". With the migration to `lib.generate_sync`, the `client` parameter is no longer needed on the two processor functions — the lib client is module-global and handles its own key rotation.

**Decision:** Removed the `gemini_client` / `client` parameter from `process_buffer_file` and `process_db_entities` entirely (both are internal helper functions, not part of any public API; grepping the repo confirmed no external callers).

**Rationale:** Per Simplicity First and Surgical Changes rules — leaving an unused parameter just to match the plan's letter would be dead-parameter cruft. The change is surgical (internal-only) and traces directly to the plan's intent (one code path through lib/).

### Baseline pytest state note

Baseline before Wave 3 (without DEEPSEEK_API_KEY set): 11 failed / 69 passed / 29 errors.

With `DEEPSEEK_API_KEY=dummy`: **109 passed / 0 failed**.

The discrepancy is entirely driven by `lib/__init__.py` importing `deepseek_model_complete` from `lib/llm_deepseek.py`, which raises `RuntimeError("DEEPSEEK_API_KEY is not set...")` at import time (Phase 5 Plan 05-00c side-effect). Wave 2 SUMMARY documented the same issue. Wave 3 adds no new regressions, and every post-task run with `DEEPSEEK_API_KEY=dummy` held at 109/109.

## Issues Encountered

### Phase 5 Plan 05-00c cross-coupling (not Wave 3 scope)

During Wave 3 execution, Hermes landed 3 additional Phase 5 Plan 00c commits (`ba6057d`, `f03b582`, `4d7d902`) on main — all in distinct files from Wave 3's scope (llm_deepseek / embedding / sys-path / smoke tests). No merge conflicts. `git pull --ff-only` was clean at Wave 3 start; subsequent commits serialized cleanly on top.

The DEEPSEEK_API_KEY import-time validation remains an open cross-phase issue (tracked in Wave 2 SUMMARY's Issues Encountered section). Wave 3 worked around it for verification via `DEEPSEEK_API_KEY=dummy`, which pytest fixtures in `tests/conftest.py` also set. Not a Wave 3 regression; not in scope to fix this wave.

## Next Phase Readiness

- **Wave 4 (`07-04-PLAN.md`):** Amendment 3 sweeper — delete config.py D-11 shims once `ingest_wechat.extract_entities` and (any remaining) callers migrate to `lib.generate_sync` directly. Plus batch scripts, skill_runner, verify_gate tests, SKILL.md updates, Deploy.md.
- **Amendment 4 status:** COMPLETE end-to-end. Rotation chain wired into all long-running Cognee consumers. No further work required on the Cognee-rotation surface.

## Self-Check: PASSED

**Files verified exist:**
- FOUND: cognee_wrapper.py
- FOUND: cognee_batch_processor.py
- FOUND: kg_synthesize.py
- FOUND: enrichment/extract_questions.py
- FOUND: init_cognee.py
- FOUND: setup_cognee.py

**Commits verified present on main:**
- FOUND: 53dbcc1 (Task 3.1)
- FOUND: 86bea93 (Task 3.2)
- FOUND: 5fb32ab (Task 3.2.5)
- FOUND: 221b898 (Task 3.3)
- FOUND: 7073eff (Task 3.4a)
- FOUND: 2892d2f (Task 3.4b)

**Wave 3 acceptance gate:**
- FOUND: 6 Wave 3 commits (5 P1 file migrations + 1 Amendment 4 patch on kg_synthesize) — matches plan's "6 commits total"
- FOUND: Integration test tests/integration/test_cognee_rotation.py PASS (3/3)
- FOUND: Full pytest suite PASS (109/109, matches Wave 2 baseline)
- FOUND: 07-03-SUMMARY.md written at expected path
- PENDING: User acknowledgement of wave completion before Wave 4 begins

---
*Phase: 07-model-key-management*
*Completed: 2026-04-28*
