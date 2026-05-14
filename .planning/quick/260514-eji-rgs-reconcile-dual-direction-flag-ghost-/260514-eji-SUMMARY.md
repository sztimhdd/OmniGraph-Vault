---
phase: 260514-eji
plan: 01
subsystem: reconcile
tags: [reconcile, ghost-success, h09, tdd]
key-files:
  modified:
    - scripts/reconcile_ingestions.py
    - tests/unit/test_reconcile_rss.py
decisions:
  - "Ghost JSON lines use kind='ghost' discriminator; mystery lines unchanged (no kind field) — backward compat preserved"
  - "Exit code 1 when ghost > 0 OR mystery > 0; was mystery-only before"
  - "Summary line appends '| N ghost (wechat: X, rss: Y)' after old format left of pipe — old grep parsers unaffected"
metrics:
  duration: "~8 min"
  completed: "2026-05-14"
  tasks: 1
  files: 2
---

# Quick 260514-eji: Dual-Direction Reconcile — Ghost Success Detection

**One-liner:** Added reverse-scan to `reconcile_ingestions.py` that detects `status='failed'` rows whose `kv_store` doc is actually `processed` (ghost success race), emitting `kind="ghost"` JSON lines and exit 1 for cron alerting.

## What Was Done

Extended `scripts/reconcile_ingestions.py` with dual-direction reconciliation:

- **Forward scan** (existing): `status='ok'` rows checked against kv_store → mystery detection
- **Reverse scan** (new): `status='failed'` rows checked against kv_store → ghost detection

The 2026-05-14 09:22 ADT cron produced the first observed ghost: id=166 (EdgeClaw/GitHubDaily) failed h09 retry after 150 attempts, but LightRAG async pipeline independently completed ~9 min later. Without this change, the candidate-pool query (`article_id NOT IN (SELECT ... WHERE status='ok')`) would re-pick id=166 on the next cron and burn paid Vision API budget on an already-processed article.

## TDD Flow

**RED:** 4 new test cases appended to `tests/unit/test_reconcile_rss.py`. All 4 failed with expected "1 ghost" / "0 ghost" / "| 0 ghost" substring AssertionErrors (not import errors).

**GREEN:** Added `_query_failed_rows()` helper + reverse-scan loop in `main()` + extended summary line + updated exit code. All 26 tests passed.

## Changes

### `scripts/reconcile_ingestions.py`

1. **Module docstring**: Added Quick 260514-eji paragraph + updated Exit codes block
2. **`_query_failed_rows(db_path, date_start, date_end)`**: New helper — reverse SQL companion to `_query_ok_rows`, identical structure except `WHERE i.status='failed'`
3. **`main()` reverse-scan loop**: After forward-scan, iterates `_query_failed_rows` results; for each `url` present and kv_store `status='processed'`, increments ghost counters and emits JSON line with `"kind": "ghost"` discriminator + `ingestion_id`, `art_id`, `source`, `doc_id`, `ingested_at`
4. **Summary line**: `f"... | {ghost_count} ghost (wechat: {ghost_count_wechat}, rss: {ghost_count_rss})\n"` — old `"X ok rows / Y matched / Z mystery (wechat: ..., rss: ...)"` substring preserved verbatim left of `|`
5. **Exit code**: `return 1 if (mystery_count > 0 or ghost_count > 0) else 0`

### `tests/unit/test_reconcile_rss.py`

4 new tests added (total 18 in file; 18 + 8 = 26 combined):

- `test_ghost_success_failed_in_db_processed_in_kv` — ghost detected, exit 1
- `test_ghost_zero_normal_failed_no_match` — real failure (kv missing), no ghost, exit 0
- `test_ghost_mixed_with_mystery` — 1 mystery + 1 ghost: exactly 2 JSON lines, mystery has no `kind`, ghost has `kind="ghost"`, exit 1
- `test_ghost_backward_compat_output_format` — old substring preserved, new `| 0 ghost` section present

## Verification

```
python -m py_compile scripts/reconcile_ingestions.py → exit 0
pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v → 26 passed, 0 failed
```

## Deviations from Plan

None — plan executed exactly as written.

## Commit

`cdd37da` — `feat(reconcile): scope extend to ghost successes (status=failed but kv_store=processed)`
Files: `scripts/reconcile_ingestions.py`, `tests/unit/test_reconcile_rss.py` only (verified via `git show --stat HEAD`).

## Self-Check: PASSED

- `scripts/reconcile_ingestions.py` modified: FOUND
- `tests/unit/test_reconcile_rss.py` modified: FOUND
- Commit `cdd37da` exists: FOUND
- 26 tests passed: VERIFIED
- Only 2 files in commit: VERIFIED
