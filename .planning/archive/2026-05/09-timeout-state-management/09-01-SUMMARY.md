---
phase: 09-timeout-state-management
plan: 01
subsystem: state-management
tags: [lightrag, get_rag, doc_id, rollback, asyncio, pytest, breaking-change]

# Dependency graph
requires:
  - phase: 08-image-pipeline-correctness
    provides: [Phase 8 regression gate: 22 tests guarding image_pipeline.py behavior]
  - phase: 09-timeout-state-management
    plan: 00
    provides: [asyncio.wait_for wraps ingest_article in batch_ingest_from_spider; _SINGLE_CHUNK_FLOOR_S = 900s budget]
provides:
  - ingest_wechat.get_rag(flush: bool = True) -> LightRAG — breaking signature change (D-09.07)
  - ingest_wechat._PENDING_DOC_IDS module-level registry + get_pending_doc_id() public accessor
  - Deterministic doc_id = f"wechat_{article_hash}" passed as ids=[doc_id] to rag.ainsert at both ingest_article branches
  - batch_ingest_from_spider.ingest_article TimeoutError branch now calls rag.adelete_by_doc_id(doc_id) for rollback (D-09.05)
  - 12 new unit tests gating STATE-01/02/03/04 decisions
affects: [10-scrape-first-classification (consumer of get_rag(flush=True)), 11-e2e-verification-gate (rollback validation)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Breaking API change landed in a single atomic commit — all 10 call sites updated together; revert restores pre-Phase-9 signature + all sites atomically"
    - "Module-level side-channel registry pattern for doc_id tracking — orchestrator reads tracker after asyncio.TimeoutError (cooperative-cancellation-friendly)"
    - "Clear-on-success-only: ingest_wechat.ingest_article clears the tracker only after successful ainsert; orchestrator clears after rollback. Matches real asyncio cancellation semantics (unlike try/finally which would race the orchestrator read)"
    - "Deterministic ids=[f'wechat_{article_hash}'] at ainsert call sites — LightRAG's own doc-id dedup handles re-ingest idempotency (STATE-03)"

key-files:
  created:
    - tests/unit/test_get_rag_contract.py
    - tests/unit/test_rollback_on_timeout.py
    - tests/unit/test_prebatch_flush.py
  modified:
    - ingest_wechat.py
    - batch_ingest_from_spider.py
    - enrichment/merge_and_ingest.py
    - ingest_github.py
    - multimodal_ingest.py
    - scripts/wave0_reembed.py
    - scripts/phase0_delete_spike.py
    - tests/unit/test_merge_and_ingest.py

key-decisions:
  - "Clear-on-success-only (NOT try/finally): ingest_wechat clears the doc_id tracker only after successful ainsert. On CancelledError / TimeoutError the tracker remains populated so the orchestrator can read it via get_pending_doc_id() and roll back. Using try/finally would race the orchestrator's read — finally would typically run first and clear the tracker before the orchestrator sees it."
  - "Consolidated Task 1 (signature + 10 call sites) with Task 2 (registry + ainsert wiring) into a SINGLE commit as the D-09.07 plan explicitly mandates all 10 call sites ship atomically with the signature change. Tests shipped as a separate commit for cleaner git history."
  - "Fixed test_merge_and_ingest.py::test_zhihu_docs_use_deterministic_ids_and_enriches_backlink regression caused by our own breaking API change — Rule 1 auto-fix (bug in our changes): updated the test's fake_get_rag stub to accept the new flush kwarg."

patterns-established:
  - "D-09.07 idiom: async def get_rag(flush: bool = True) -> LightRAG. flush=True is the production default; flush=False is reserved for spikes that want to observe pre-Phase-9 reuse-prior-state semantics."
  - "D-09.05 idiom: (1) compute doc_id before ainsert, (2) register via _register_pending_doc_id(article_hash, doc_id), (3) await rag.ainsert(..., ids=[doc_id]), (4) _clear_pending_doc_id only on success. Orchestrator's TimeoutError branch reads via get_pending_doc_id(), calls rag.adelete_by_doc_id(doc_id), then clears."
  - "Test patterns: mock LightRAG as MagicMock with AsyncMock methods (ainsert, adelete_by_doc_id); monkeypatch _SINGLE_CHUNK_FLOOR_S to 0.1 to force TimeoutError deterministically; source-grep assertions to guard against future regression to bare get_rag() calls."

requirements-completed: [STATE-01, STATE-02, STATE-03, STATE-04]

# Metrics
duration: 9min
completed: 2026-04-30
---

# Phase 9 Plan 09-01: LightRAG State Management + Rollback Summary

**Breaking API: get_rag(flush: bool = True) returns a fresh LightRAG per call; deterministic doc_ids passed as ids=[doc_id] at both ainsert sites enable rollback via rag.adelete_by_doc_id on asyncio.wait_for timeout — proving idempotent re-ingest after rollback (STATE-01/02/03/04).**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-05-01T00:46:14Z
- **Completed:** 2026-05-01T00:55:XX Z
- **Tasks:** 2 planned, executed as 3 commits (source breaking change + tests + metadata)
- **Files modified:** 8 (7 source + 1 regression-fix test)
- **Files created:** 3 (new test suites)

## Accomplishments

- **STATE-04 (D-09.07) — get_rag() signature change:** `async def get_rag()` → `async def get_rag(flush: bool = True) -> LightRAG`. Docstring documents flush=True (production default / fresh instance / no replay of prior pending buffer) vs flush=False (reserved for tests and one-off spikes). ALL 10 call sites updated in the SAME commit:
  - Production (7): ingest_wechat.py (3 sites), batch_ingest_from_spider.py (2 sites), enrichment/merge_and_ingest.py, ingest_github.py, multimodal_ingest.py → all pass `flush=True` explicitly with D-09.07/D-09.04 code comments.
  - Spike (3): scripts/wave0_reembed.py (2 sites), scripts/phase0_delete_spike.py → all pass `flush=False` to preserve historical reuse-prior-state semantics.
- **STATE-01 (D-09.04) — pre-batch flush:** Both `batch_ingest_from_spider.run` and `.ingest_from_db` entry points now call `get_rag(flush=True)` with a log line and comment referencing STATE-01 / D-09.04. A future refactor that reverts to bare `get_rag()` will fail the source-grep test.
- **STATE-02 (D-09.05) — rollback on timeout:** Added `_PENDING_DOC_IDS: dict[str, str]` module-level tracker + `_register_pending_doc_id`, `_clear_pending_doc_id`, and `get_pending_doc_id` (public) helpers in `ingest_wechat.py`. Both `ingest_article` branches (cache hit + fresh scrape) compute `doc_id = f"wechat_{article_hash}"`, register it, pass `ids=[doc_id]` to `rag.ainsert`, and clear only on success. `batch_ingest_from_spider.ingest_article` catches `asyncio.TimeoutError`, reads `get_pending_doc_id(article_hash)`, and if a doc_id is tracked + rag is not None, awaits `rag.adelete_by_doc_id(doc_id)`. Rollback failure is logged (not raised); orchestrator clears the tracker in `finally`.
- **STATE-03 (D-09.06) — idempotent re-ingest:** Proven by `test_idempotent_reingest_after_rollback`: ingest → timeout → rollback → re-ingest succeeds with ONE `adelete_by_doc_id` + ONE `ainsert(ids=[doc_id])`. Follows naturally from STATE-02 + LightRAG's own doc-id dedup.
- **12 new unit tests** gate the four state decisions (6 for get_rag contract, 4 for rollback/idempotency, 2 for pre-batch flush).
- **Regression fix (Rule 1 auto-fix):** `tests/unit/test_merge_and_ingest.py::test_zhihu_docs_use_deterministic_ids_and_enriches_backlink` was broken by our own breaking API change (its `fake_get_rag()` stub didn't accept the new `flush` kwarg). Added `flush: bool = True` parameter to the stub with a D-09.07 comment — now passes.

## Task Commits

1. **T1+T2 — source changes (signature + 10 call sites + registry + ainsert wiring + batch rollback handler + merge test fix):** `4e87ae4` (feat)
2. **T3 — three new test suites:** `63775f4` (test)
3. **Final metadata commit (SUMMARY + STATE + ROADMAP):** pending — see `final_commit` step below.

## Files Created/Modified

- **ingest_wechat.py** (modified): get_rag signature + docstring (D-09.07); `_PENDING_DOC_IDS` registry + 3 helper functions (D-09.05); both ingest_article branches compute doc_id + register + pass ids=[doc_id] + clear-on-success; PDF ingest branch updates get_rag call site to flush=True.
- **batch_ingest_from_spider.py** (modified): both `get_rag()` sites → `get_rag(flush=True)` with STATE-01 comments; `ingest_article` adds `article_hash` pre-computation + TimeoutError rollback branch + log-not-raise on rollback failure.
- **enrichment/merge_and_ingest.py, ingest_github.py, multimodal_ingest.py** (modified): one-line `get_rag(flush=True)` updates with D-09.07/D-09.04 comments.
- **scripts/wave0_reembed.py** (modified): both spike call sites → `get_rag(flush=False)` with D-09.07 comment.
- **scripts/phase0_delete_spike.py** (modified): single spike call site → `get_rag(flush=False)` with D-09.07 comment.
- **tests/unit/test_merge_and_ingest.py** (modified, Rule 1 regression fix): `fake_get_rag()` stub now accepts `flush: bool = True`.
- **tests/unit/test_get_rag_contract.py** (NEW, 6 tests): signature + docstring + distinct-instance contract + flush=False fresh-per-call + production/spike source-grep.
- **tests/unit/test_rollback_on_timeout.py** (NEW, 4 tests): timeout triggers adelete; happy path no adelete; rollback failure logged not raised; idempotent re-ingest after rollback.
- **tests/unit/test_prebatch_flush.py** (NEW, 2 tests): batch entry points call get_rag(flush=True); STATE-01 / D-09.04 comment present.

## Decisions Made

- **Clear-on-success-only tracker semantics** (not in plan verbatim — refined from plan's try/finally pattern): the plan shows a `try/finally` around `rag.ainsert` in which finally clears the tracker. In real asyncio cancellation, the inner coroutine's `finally` runs BEFORE `wait_for` raises `TimeoutError` to the caller — so a try/finally clear would remove the tracker before the orchestrator could read it. Implementation uses clear-on-success-only: the tracker is cleared AFTER `ainsert` returns normally; on exception (including CancelledError) it remains populated for the orchestrator. The orchestrator clears it in its own `finally` after rollback completes. Test `test_timeout_triggers_adelete_by_doc_id` was adjusted to match (mock `_slow_ingest` registers but does not clear). Logged as a sharpening of the plan's pattern, not a deviation.
- **Commit shape:** Task 1 (signature + 10 call sites) and Task 2 (registry helpers + doc_id wiring at ainsert sites + batch rollback handler) landed in ONE commit because D-09.07 mandates the breaking change ship atomically across all call sites. The plan's "three decisions land as one atomic code change" phrasing for Task 2 was applied to the whole source change. Tests landed as a separate commit for git-log clarity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_merge_and_ingest fake_get_rag() stub for new flush kwarg**

- **Found during:** full-suite regression run after Task 2
- **Issue:** `test_zhihu_docs_use_deterministic_ids_and_enriches_backlink` failed with `TypeError: fake_get_rag() got an unexpected keyword argument 'flush'` because our breaking API change to `get_rag(flush: bool = True)` meant any caller passing `flush=True` (including the updated `enrichment/merge_and_ingest.py`) now fails against a 0-arg stub.
- **Fix:** Added `flush: bool = True` parameter to the `fake_get_rag()` stub with a `# D-09.07` comment explaining why.
- **Files modified:** tests/unit/test_merge_and_ingest.py (1 line)
- **Commit:** `4e87ae4` (bundled with the breaking API change)

### Plan-sharpening notes (not deviations)

- **Clear-on-success-only vs try/finally:** Plan Task 2 Change 2 shows a try/finally block around ainsert. In practice this would race the orchestrator's read of `get_pending_doc_id()` during cancellation. Implementation clears only on success; orchestrator clears in its own finally after rollback. Test mocks adjusted to match. This is a semantic sharpening of the plan's intent (plan's prose elsewhere clarifies "cancellation is cooperative; this finally runs" — which is true but means the finally clears BEFORE wait_for re-raises TimeoutError to caller, so the orchestrator would see a cleared tracker).

## Issues Encountered

- **CRLF/LF line-ending renormalization** on `enrichment/merge_and_ingest.py`, `scripts/phase0_delete_spike.py`, and `tests/unit/test_merge_and_ingest.py` — same cosmetic Windows-checkout issue documented in 09-00 SUMMARY for `run_uat_ingest.py`. Diff stats show ~475/~423/~355 inserted/deleted lines for these files; substantive changes are only a handful of lines each. Verified via `git show` that file contents are correct.
- **No architectural changes / auth gates / blockers encountered.**

## Verification

**Plan 09-01 tests (expected: 12 new, all pass):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_get_rag_contract.py \
    tests/unit/test_rollback_on_timeout.py \
    tests/unit/test_prebatch_flush.py -v
```

Result: **12 passed in 10.11s** (6 contract + 4 rollback + 2 flush).

**Plan 09-00 regression (expected: all 18 still pass):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_lightrag_llm.py \
    tests/unit/test_timeout_budget.py \
    tests/unit/test_lightrag_timeout.py -v
```

Result: **18 passed** — zero regressions.

**Phase 8 regression gate (MANDATORY — must remain 22 green):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v
```

Result: **22 passed in 3.13s** — zero regressions.

**Full unit suite:**

- Baseline (per 09-00 SUMMARY): 123 passed, 10 failed
- Post-plan: **135 passed (+12 new from 09-01), 10 failed (identical pre-existing set — 7 embedding rotation + 3 models)**

**Smoke imports (5 production modules):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"               # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"   # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import enrichment.merge_and_ingest; print('OK')" # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_github; print('OK')"              # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import multimodal_ingest; print('OK')"          # OK
```

All 5 green.

**Grep audit — zero bare get_rag() calls in production:**

```bash
git ls-files '*.py' | xargs grep -nE 'await\s+get_rag\s*\(\s*\)' 2>/dev/null
# → no matches
```

Clean.

## Next Phase Readiness

- Plan 09-01 complete. All four STATE-* acceptance criteria proven:
  - **STATE-01:** get_rag(flush=True) is now the default at every batch/CLI entry. Source-grep test prevents regression.
  - **STATE-02:** rag.adelete_by_doc_id called exactly once on asyncio.TimeoutError — unit-proven with mocked LightRAG.
  - **STATE-03:** rollback → re-ingest succeeds with one adelete_by_doc_id + one ainsert(ids=[doc_id]) — unit-proven.
  - **STATE-04:** signature is `async def get_rag(flush: bool = True) -> LightRAG`; docstring documents the contract; all 10 call sites audited.
- Phase 9 success criteria 3-6 green. Success criterion 7 (Phase 8 regression + Phase 9 tests green) verified.
- **Phase 10 (PRD generation) ready to proceed.** No blockers. E2E rollback benchmark (real LightRAG + real NanoVectorDB) deferred to Phase 11 per plan Out-of-Scope.
- **Rollback-ordering note:** if reverting both plans, revert 09-01 FIRST then 09-00 because 09-01's rollback handler in batch_ingest_from_spider references `_SINGLE_CHUNK_FLOOR_S` from 09-00. `git revert --no-commit <09-01> <09-00> && git commit` handles the sequenced revert.
- **Breaking-change caveat for revert:** if downstream code adopts `get_rag(flush=...)` after this plan landed, revert must be paired with `grep -rn "get_rag(flush=" .` → restore bare calls.

## Self-Check: PASSED

All claimed files exist:

- tests/unit/test_get_rag_contract.py — FOUND
- tests/unit/test_rollback_on_timeout.py — FOUND
- tests/unit/test_prebatch_flush.py — FOUND
- .planning/phases/09-timeout-state-management/09-01-SUMMARY.md — FOUND (this file)

All claimed commits exist on main:

- `4e87ae4` (source breaking change) — FOUND
- `63775f4` (tests) — FOUND

---
*Phase: 09-timeout-state-management*
*Completed: 2026-04-30*
