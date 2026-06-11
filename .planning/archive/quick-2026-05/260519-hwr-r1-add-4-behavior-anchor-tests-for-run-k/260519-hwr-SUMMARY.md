---
quick_id: 260519-hwr
description: R1 — add 4 behavior-anchor tests for run() KOL orchestrator
status: complete
date: 2026-05-19
---

# Summary: R1 behavior-anchor harness for `run()`

## What changed

- **New file**: `tests/unit/test_run_kol_scan_orchestration.py` (4 tests)

Companion to T1–T5 in `tests/unit/test_ingest_from_db_orchestration.py`.
Closes the harness gap on the sister orchestrator at
`batch_ingest_from_spider.py:793-1014` per CLAUDE.md PRINCIPLE #7.

### Anchor tests added

| ID | Anchor | Pinned post-condition |
|----|--------|-----------------------|
| R1 | unknown `account_filter` early-return | `list_articles` / `ingest_article` / `get_rag` never called; no summary or metrics file written |
| R2 | checkpoint-skip on `has_stage('text_ingest')` | exactly one summary row with `status='skipped_ingested'`; `ingest_article` not called |
| R3 | `dry_run=True` suppresses LightRAG init | `get_rag` never called; both rows stamped `status='dry_run'` |
| R4 | `finally` writes `batch_timeout_metrics_*.json` even on exception | metrics JSON exists under `tmp_path/data/` after `RuntimeError` propagates; `rag.finalize_storages` called once |

Patches applied via a single `_patch_run_env()` helper that mirrors the
`_ingest_fixtures.py:patch_layer_funcs` pattern but covers the run-specific
boundary (`bi.kol_config`, `bi.list_articles`, `bi.PROJECT_ROOT`,
`bi.RATE_LIMIT_SLEEP_ACCOUNTS`).

## Verification (PRINCIPLE #7)

| Stage | Command | Result |
|-------|---------|--------|
| Pre-change baseline | `pytest tests/unit/test_ingest_from_db_orchestration.py -v` | **5 passed** ([log](../../.scratch/quick-r1-pytest-prechange.log)) |
| Post-change | `pytest tests/unit/test_run_kol_scan_orchestration.py -v` | **4 passed** ([log](../../.scratch/quick-r1-pytest-postchange.log)) |
| Full unit suite | `pytest tests/unit/ -v` | **969 passed**, 5 pre-existing failures unrelated to R1 ([log](../../.scratch/quick-r1-pytest-full.log)) |

### Pre-existing failures (NOT caused by R1)

5 tests in `test_max_articles_hard_cap.py` and `test_vision_worker.py` fail
with `TypeError: ingest_from_db() got an unexpected keyword argument
'min_depth'` — fixture drift from a separate change to `ingest_from_db()`
signature. Verified by running those files in isolation without
`test_run_kol_scan_orchestration.py` present (same 5 failures). Filing as
out-of-scope for R1.

## Files touched

- `tests/unit/test_run_kol_scan_orchestration.py` (new, ~210 LOC)

No production code changes. No fixture changes (reuses
`tests/unit/_ingest_fixtures.py:mock_rag` only).

## Commit

`test(run): add R1-R4 behavior-anchor harness for run() orchestrator`
