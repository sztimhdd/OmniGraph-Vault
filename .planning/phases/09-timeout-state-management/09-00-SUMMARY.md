---
phase: 09-timeout-state-management
plan: 00
subsystem: infra
tags: [timeout, asyncio, lightrag, deepseek, openai-sdk, pytest]

# Dependency graph
requires:
  - phase: 08-image-pipeline-correctness
    provides: [Phase 8 regression gate: 22 tests guarding image_pipeline.py behavior]
provides:
  - LLM_TIMEOUT=600 env export at top of ingest_wechat.py, run_uat_ingest.py, batch_ingest_from_spider.py (D-09.01)
  - DeepSeek AsyncOpenAI client-side 120s request timeout in lib/llm_deepseek.py (D-09.02)
  - Module-level _compute_article_budget_s(full_content) helper in batch_ingest_from_spider.py — formula max(120 + 30*chunk_count, 900) (D-09.03)
  - ingest_article wait_for budget raised from hardcoded 1200s to _SINGLE_CHUNK_FLOOR_S (900s) — 300s safety margin buy-down at the url-only call site (D-09.03 option c)
  - 10 new unit tests gating the 3 timeout contracts
affects: [09-01-state-management, 10-scrape-first-classification, 11-e2e-verification-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LLM_TIMEOUT env-var export at module top (BEFORE any lightrag import) — guards against late-import drift"
    - "openai SDK timeout= bare float form (no httpx dependency bleed-through)"
    - "Two-layer timeout semantics: outer asyncio.wait_for budget governs whole-article; inner LLM_TIMEOUT governs per-chunk call"
    - "Module-level budget helper exposed for downstream consumers (09-01 / Phase 10) without changing current call-site signature"

key-files:
  created:
    - tests/unit/test_lightrag_timeout.py
    - tests/unit/test_timeout_budget.py
  modified:
    - ingest_wechat.py
    - run_uat_ingest.py
    - batch_ingest_from_spider.py
    - lib/llm_deepseek.py
    - tests/unit/test_lightrag_llm.py

key-decisions:
  - "TIMEOUT-02 idiom: bare float `timeout=120.0` (no httpx.Timeout) — keeps import surface minimal; openai>=1.0 accepts it as total request timeout"
  - "TIMEOUT-03 wrap site: chose CONTEXT option (c) — ingest_article is called with `url`, full_content is unknown pre-scrape, so use _SINGLE_CHUNK_FLOOR_S (900s) at the url-only call site. Chunk-count-aware scaling deferred to Phase 10 when scrape/ingest decouple"
  - "Helper _compute_article_budget_s exposed at module scope (not in a function closure) so Plan 09-01 / Phase 10 can import and consume it once full_content is known"

patterns-established:
  - "D-09.01 idiom: `os.environ.setdefault('LLM_TIMEOUT', '600')` at module TOP, before any `from lightrag...` import. Source-scan smoke test guards against regressions that move the setdefault line."
  - "D-09.02 idiom: bare-float timeout in AsyncOpenAI(...) constructor; test asserts `_client.timeout == 120.0` with httpx.Timeout fallback for SDK version robustness."
  - "D-09.03 idiom: budget helper is module-level + pure, so unit tests import and call directly without spinning up LightRAG."

requirements-completed: [TIMEOUT-01, TIMEOUT-02, TIMEOUT-03]

# Metrics
duration: 6min
completed: 2026-04-30
---

# Phase 9 Plan 09-00: Timeout Layer Summary

**LightRAG per-chunk LLM_TIMEOUT=600, DeepSeek AsyncOpenAI request timeout=120s, chunk-scaled outer wait_for budget (900s floor) — three deterministic timeout controls so single-chunk and single-article runaways cannot stall the ingestion pipeline.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-01T00:33:05Z
- **Completed:** 2026-05-01T00:39:01Z
- **Tasks:** 3 (T1 TIMEOUT-01, T2 TIMEOUT-02, T3 TIMEOUT-03) — all `type="auto"`, no checkpoints
- **Files modified:** 5 (2 new tests + 3 modified source + 1 extended test)

## Accomplishments

- **TIMEOUT-01 (D-09.01):** `os.environ.setdefault("LLM_TIMEOUT", "600")` exported at the TOP of `ingest_wechat.py`, `run_uat_ingest.py`, and `batch_ingest_from_spider.py` — BEFORE any transitive LightRAG import. LightRAG's `default_llm_timeout` dataclass field default is now 600s in production (up from the 180s baked into `lightrag/constants.py:100`).
- **TIMEOUT-02 (D-09.02):** `lib/llm_deepseek.py` `_client = AsyncOpenAI(..., timeout=120.0)` — any DeepSeek chat.completions.create that exceeds 120s is killed client-side, so the outer article budget isn't drained by one runaway chunk.
- **TIMEOUT-03 (D-09.03):** Added module-level `_compute_article_budget_s(full_content)` helper implementing `max(120 + 30 * chunk_count, 900)` with `chunk_count = max(1, len(full_content) // 4800)`. `ingest_article` `asyncio.wait_for(..., timeout=1200)` replaced with `timeout=_SINGLE_CHUNK_FLOOR_S` (900s) because the url-only call site doesn't know full_content yet. TimeoutError log message now uses the named constant (was stale hardcoded "600s").
- **10 new unit tests** gate the three contracts (verification gate below).

## Task Commits

1. **T1 — TIMEOUT-01 entry-point LLM_TIMEOUT exports:** `b987d12` (feat)
2. **T2 — DeepSeek AsyncOpenAI timeout=120s:** `2890440` (feat)
3. **T3 + T1 (batch_ingest_from_spider.py shared file) — budget helper, wait_for rewrite, LLM_TIMEOUT at batch top:** `fd9e287` (feat)

**Final metadata commit (SUMMARY + STATE + ROADMAP):** pending — see `final_commit` step below.

## Files Created/Modified

- `ingest_wechat.py` — added 7 lines at top (comment + `os.environ.setdefault("LLM_TIMEOUT", "600")`) before `from lightrag.lightrag import ...`
- `run_uat_ingest.py` — added 7 lines after `sys.stdout.reconfigure`, before `GOOGLE_GENAI_USE_VERTEXAI` env set. (Git diff shows CRLF/LF line-ending reformatting — cosmetic only; file content is correct.)
- `batch_ingest_from_spider.py` — two insertions: (a) `LLM_TIMEOUT=600` setdefault at module top (T1); (b) module-level budget constants + `_compute_article_budget_s` helper + `ingest_article` `timeout=_SINGLE_CHUNK_FLOOR_S` rewrite + updated log message (T3)
- `lib/llm_deepseek.py` — `_DEEPSEEK_TIMEOUT_S = 120.0` constant + `timeout=_DEEPSEEK_TIMEOUT_S` kwarg on `AsyncOpenAI(...)`
- `tests/unit/test_lightrag_llm.py` — appended `test_deepseek_client_has_120s_timeout` (asserts `_client.timeout` is 120.0 with httpx.Timeout fallback)
- `tests/unit/test_lightrag_timeout.py` (NEW) — 3 tests: LLM_TIMEOUT=300 reload → field default 300; unset → fallback 180; source-scan smoke for setdefault presence in all 3 entry points
- `tests/unit/test_timeout_budget.py` (NEW) — 6 pure-unit tests covering floor (empty / small / 20-chunk), scaling (50 / 100 chunks), chunk_count floor of 1

## Decisions Made

- **Idiom for TIMEOUT-02:** bare `timeout=120.0` float over `httpx.Timeout(120.0)` — the openai>=1.0 SDK accepts float as total-request timeout and keeps import surface minimal. Test accepts either form for cross-version robustness.
- **TIMEOUT-03 wrap site:** chose CONTEXT option (c) — 900s floor at the url-only call site. Rationale: `ingest_article(url, dry_run, rag)` calls `ingest_wechat.ingest_article(url, rag=rag)` which does scrape + image-download + ainsert; full_content isn't known pre-scrape. Moving the `wait_for` inside `rag.ainsert` to use `_compute_article_budget_s(full_content)` is Phase 10 refactor work (scrape/ingest decoupling). For v3.1 gate, 900s floor + 600s per-chunk inner + 120s DeepSeek client is sufficient — PRD success criterion 3 uses a 5s budget to prove rollback (Plan 09-01 owns that), which the floor doesn't affect.
- **Helper exposure:** `_compute_article_budget_s` is module-level (not nested), so Plan 09-01 / Phase 10 can import and consume it from any future call site where full_content is known.

## Deviations from Plan

None — plan executed exactly as written. All three tasks used the code shapes specified in the plan's `## Tasks` section.

## Issues Encountered

- `run_uat_ingest.py` diff was visually large (246 insertions / 120 deletions) due to CRLF↔LF line-ending renormalization triggered by the first edit on a Windows checkout. Content change was limited to the 7-line block specified in the plan. Verified by git show of the hunk — substantive diff is the setdefault addition; the rest is whitespace-only reflow. No behavioral impact.

## Verification

**Phase 9 Plan 09-00 tests (expected: all pass, 10 new):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_lightrag_llm.py \
    tests/unit/test_timeout_budget.py \
    tests/unit/test_lightrag_timeout.py -v
```

Result: **18 passed** (8 existing `test_lightrag_llm.py` + 1 new `test_deepseek_client_has_120s_timeout` + 6 new `test_timeout_budget.py` + 3 new `test_lightrag_timeout.py`) = **10 new tests**, matches plan expectation.

**Phase 8 regression gate (MANDATORY — must remain 22 green):**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v
```

Result: **22 passed in 3.41s** — zero regressions.

**Full unit suite:**

- Baseline (before plan): 113 passed, 10 failed
- Post-plan: **123 passed (+10 new), 10 failed (identical pre-existing set — all Phase 7 test_models / Phase 5 embedding rotation issues unrelated to Phase 9)**

**Smoke imports:**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"        # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"  # OK
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import lib.llm_deepseek as ld; print(ld._client.timeout)"  # 120.0
```

All three green.

## Next Phase Readiness

- Plan 09-00 complete. Interface contract holds:
  - `batch_ingest_from_spider._compute_article_budget_s(full_content) -> int` is exported at module scope for Plan 09-01 / Phase 10 consumption.
  - `LLM_TIMEOUT=600` is now the production env default via setdefault at all three entry-point tops.
  - `lib.llm_deepseek._client` carries a 120.0s request timeout.
- **Plan 09-01 can start** (STATE-01 pre-batch buffer flush, STATE-02 rollback on wait_for timeout, STATE-03 idempotent re-ingest, STATE-04 `get_rag()` contract change).
- **Rollback-ordering note:** if Plan 09-01 starts consuming `_compute_article_budget_s`, revert 09-01 first, then 09-00. `git revert --no-commit <09-01> <09-00>` handles both.

## Self-Check: PASSED

All claimed files exist: `tests/unit/test_lightrag_timeout.py`, `tests/unit/test_timeout_budget.py`, `.planning/phases/09-timeout-state-management/09-00-SUMMARY.md`.
All claimed commits exist on main: `b987d12`, `2890440`, `fd9e287`.

---
*Phase: 09-timeout-state-management*
*Completed: 2026-04-30*
