---
phase: 17-batch-timeout-management
plan: 02
subsystem: batch-timeout
tags: [batch-ingest, instrumentation, metrics, batch-timeout]
requires: [17-00, 17-01]
provides:
  - batch_ingest_from_spider.py (instrumented)
  - tests/unit/test_batch_timeout_instrumentation.py
  - data/batch_timeout_metrics_<ts>.json (runtime output)
affects:
  - tests/unit/test_rollback_on_timeout.py (signature follow-up)
  - tests/unit/test_vision_worker.py (signature follow-up)
tech-stack:
  added: []
  patterns: [OMNIGRAPH_* env-var idiom, pure helpers + tuple return for observability]
key-files:
  created:
    - tests/unit/test_batch_timeout_instrumentation.py
  modified:
    - batch_ingest_from_spider.py
    - tests/unit/test_rollback_on_timeout.py
    - tests/unit/test_vision_worker.py
decisions:
  - "ingest_article signature extended to (url, dry_run, rag, effective_timeout=None) returning tuple[bool, float] — return-type change required to surface wall-clock to the histogram"
  - "Checkpoint flush guarded with try/ImportError — plan 17-02 merges standalone even without Phase 12 flush_partial_checkpoint API"
  - "Batch metrics written to data/batch_timeout_metrics_<ts>.json; Phase 14 regression integration deferred"
  - "run() and ingest_from_db() get identical metric block in finally: — operator sees same shape regardless of entry point"
metrics:
  duration_min: 15
  tasks: 2
  files: 4
  tests_added: 20
  tests_passing: 20
  completed: 2026-05-02
commit: d5c1686
---

# Phase 17 Plan 02: Batch Instrumentation Summary

One-liner: Wired `clamp_article_timeout` + batch-budget tracking + `batch_timeout_metrics` emission into `batch_ingest_from_spider.py` (`run()` and `ingest_from_db()`), added `--batch-timeout` CLI flag + `OMNIGRAPH_BATCH_TIMEOUT_SEC` env override, and covered the three new pure helpers with 20 unit tests.

## What Was Built

**`batch_ingest_from_spider.py` — surgical edits:**

1. Import `BATCH_SAFETY_MARGIN_S`, `clamp_article_timeout`, `get_remaining_budget` from `lib.batch_timeout` (next to the existing `lib.checkpoint` import).
2. Three new pure helpers after `_compute_article_budget_s`:
   - `_bucket_article_time(seconds) -> str` — histogram buckets `0-60s` / `60-300s` / `300-900s` / `900s+`.
   - `_resolve_batch_timeout(cli_value) -> int` — env `OMNIGRAPH_BATCH_TIMEOUT_SEC` wins, else CLI, else default `28800`.
   - `_build_batch_timeout_metrics(...)` — assembles the 11-key dict per design doc § Monitoring Metrics.
3. `ingest_article` signature: `(url, dry_run, rag, effective_timeout: int | None = None)` returning `tuple[bool, float]` (wall-clock). Checkpoint-flush call guarded with `try/ImportError` so merges standalone without Phase 12 flush API.
4. `run()` Phase 3 loop: batch_start + completed_times + histogram + clamped_count + safety_margin_triggered state, clamp call per article BEFORE checkpoint-skip doesn't apply, early-exit when budget exhausts, `finally:` block writes log line + `data/batch_timeout_metrics_<ts>.json`.
5. `ingest_from_db()` loop: identical pattern mirrored; accepts new `batch_timeout=None` kwarg.
6. New `--batch-timeout` argparse flag; threaded into both `run(...)` and `ingest_from_db(...)` in `main()`.

**`tests/unit/test_batch_timeout_instrumentation.py` — 20 tests:**

| Group | Count | Covers |
|-------|-------|--------|
| `_bucket_article_time` (parametrized) | 11 | all 4 bucket boundaries incl. just-above / just-below / at-the-edge |
| `_resolve_batch_timeout` | 4 | default, CLI, env-wins, invalid-env-falls-back |
| `_build_batch_timeout_metrics` | 5 | 11-key schema, null-avg-when-zero-completed, mean-when-completed, not_started math, safety_margin flag preserved |

## Verification Evidence

- `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout_instrumentation.py -v` → **20 passed in 5.57s**
- Smoke: `python -c "import batch_ingest_from_spider as b; assert b._bucket_article_time(30) == '0-60s' ... b._resolve_batch_timeout(None) == 28800 ... == 7200"` → OK
- `--help` shows `--batch-timeout BATCH_TIMEOUT` with mention of `OMNIGRAPH_BATCH_TIMEOUT_SEC` env var
- Regression sweep (rollback + vision_worker + batch_timeout + instrumentation + timeout_budget): **51 passed in 15.94s**
- Full `tests/unit/` sweep: **298 passed, 13 failed** — all 13 pre-existing regressions (Phase 7 model-constants `test_models.py`, Phase 13 Vertex AI embedding rotation, Phase 13 bench harness); confirmed pre-existing by stash-to-HEAD rerun below.

## Deviations from Plan

**[Rule 1 - Bug] Signature follow-up in 2 regression tests**
- **Found during:** Task 1 (after `ingest_article` signature changed to return `tuple[bool, float]`)
- **Issue:** `tests/unit/test_rollback_on_timeout.py` (4 call sites) and `tests/unit/test_vision_worker.py` (3 fake-ingest definitions) both used the old single-`bool` contract — causing `TypeError: cannot unpack non-iterable bool` on tuple-unpack in the batch loops or `assert ok is True` failing with a tuple.
- **Fix:** Updated the 4 direct calls in `test_rollback_on_timeout.py` to `ok, _wall = await bi.ingest_article(...)`. Updated the 3 fake `_fake_ingest_article` coroutines in `test_vision_worker.py` to accept `effective_timeout=None` kwarg and return `(True, 0.0)`.
- **Files modified:** `tests/unit/test_rollback_on_timeout.py`, `tests/unit/test_vision_worker.py`
- **Commit:** d5c1686

## Deferred Issues

Not caused by Phase 17. Confirmed via `git stash` pre-commit rerun on HEAD:

- `tests/unit/test_models.py::test_ingestion_llm_is_pure_constant` + `test_vision_llm_is_pure_constant` + `test_no_model_env_override` — 3 failures: production model constants no longer match hard-coded `gemini-2.5-flash-lite` expectation.
- `tests/unit/test_lightrag_embedding.py::test_embedding_func_reads_current_key` + `test_lightrag_embedding_rotation.py` (6 tests) — 7 failures: mock signature doesn't accept `vertexai` kwarg (Phase 16 Vertex AI migration).
- `tests/unit/test_bench_harness.py` (3 failures) — siliconflow balance precheck delegation.

All 13 are pre-existing on commit `f62d94a` (before any Phase 17 file change). Out of scope for Phase 17; logged here for the owning phase's verifier.

## Self-Check: PASSED

- `batch_ingest_from_spider.py` has `from lib.batch_timeout import` → verified via grep
- `_bucket_article_time`, `_resolve_batch_timeout`, `_build_batch_timeout_metrics` defined → verified via grep + import smoke
- `OMNIGRAPH_BATCH_TIMEOUT_SEC` literal present → verified via grep
- `--batch-timeout` CLI arg present → verified via `--help | grep`
- 20 instrumentation tests pass → verified
- Phase 9 regression green + Phase 10/12 integration tests green → verified
- Commit `d5c1686` present → verified
