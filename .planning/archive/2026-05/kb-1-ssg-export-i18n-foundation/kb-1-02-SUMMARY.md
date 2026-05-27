---
phase: kb-1-ssg-export-i18n-foundation
plan: 02
subsystem: kb
tags: [kb, i18n, data-layer, migration, sqlite, lang-detect]
dependency-graph:
  requires:
    - kb-1-01 (kb/__init__.py + kb/config.py + kb/data/__init__.py + kb/scripts/__init__.py)
  provides:
    - kb.data.lang_detect.detect_lang
    - kb.data.lang_detect.chinese_char_ratio
    - kb.scripts.migrate_lang_column.migrate_lang_column
    - kb.scripts.migrate_lang_column.main (CLI)
  affects:
    - kb-1-05 (detect-script-driver — consumes detect_lang)
    - kb-1-06 (article-query — reads articles.lang / rss_articles.lang)
tech-stack:
  added: []
  patterns:
    - PRAGMA table_info idempotent ALTER (mirrors enrichment/rss_schema.py:_ensure_rss_columns)
    - Pure function module (stdlib only, no DB / no network)
key-files:
  created:
    - kb/data/lang_detect.py
    - kb/scripts/migrate_lang_column.py
    - tests/unit/kb/test_lang_detect.py
    - tests/unit/kb/test_migrate_lang_column.py
  modified: []
decisions:
  - Tests use hand-computed exact ratios, not range bands (per 2026-05-06 lesson on test mirroring)
  - CJK detection uses CJK Unified Ideographs basic block only (`一` to `鿿`); ~1% false-negative on extension blocks accepted
  - Spy via SpyConn proxy class (sqlite3.Connection.execute is read-only in CPython 3.13)
metrics:
  duration: ~10 minutes
  tasks-completed: 2
  tests-added: 18
  tests-passing: 18
  commits: 2
  completed-date: 2026-05-12
requirements: [DATA-01, DATA-02]
---

# Phase kb-1 Plan 02: Migration + Lang-Detect Summary

**One-liner:** Idempotent `lang TEXT` SQLite migration for both articles + rss_articles tables, plus pure-function CJK ratio language detector — schema-extending non-breaking per C3 contract.

## What Was Built

### `kb/data/lang_detect.py` (47 LOC)

Pure-function CJK ratio detector. No DB, no network, stdlib only.

- `chinese_char_ratio(text: str) -> float` — fraction of chars in CJK Unified Ideographs basic block (`一` to `鿿`)
- `detect_lang(text: str) -> Literal["zh-CN", "en", "unknown"]`
  - `len(text) < 200` → `"unknown"` (insufficient sample)
  - ratio > 0.30 → `"zh-CN"`
  - else → `"en"`
- Constants: `MIN_TEXT_LEN = 200`, `ZH_THRESHOLD = 0.30` (locked thresholds, asserted in tests)

### `kb/scripts/migrate_lang_column.py` (60 LOC)

Idempotent SQLite migration. Mirrors `enrichment/rss_schema.py:_ensure_rss_columns`.

- `migrate_lang_column(conn) -> dict[str, str]` — library function returning per-table action (`"added"` | `"already_present"` | `"table_missing"`)
- `main() -> int` — CLI entry; reads `config.KB_DB_PATH`, prints per-table action, returns 1 + stderr if DB missing
- Pre-check via `PRAGMA table_info({table})`; only emits ALTER for missing columns
- Targets: both `articles` and `rss_articles` get nullable `lang TEXT`

## Tests

| File | Count | Status |
|------|-------|--------|
| `tests/unit/kb/test_lang_detect.py` | 12 | All pass |
| `tests/unit/kb/test_migrate_lang_column.py` | 6 | All pass |
| **Total** | **18** | **18/18 pass** |

```
tests/unit/kb/test_lang_detect.py ............                           [ 66%]
tests/unit/kb/test_migrate_lang_column.py ......                         [100%]
============================= 18 passed in 0.11s ==============================
```

## Idempotency Proof

Migration script run twice against a fresh temp DB with both base tables present:

```
=== First run ===
  articles: added
  rss_articles: added
Migration complete (DB: C:\Users\huxxha\AppData\Local\Temp\tmpst6l04y6\demo.db)

=== Second run (should be no-op) ===
  articles: already_present
  rss_articles: already_present
Migration complete (DB: C:\Users\huxxha\AppData\Local\Temp\tmpst6l04y6\demo.db)
```

Test `test_migrate_idempotent_zero_alters_on_second_run` proves this with a `SpyConn` proxy that counts ALTER TABLE calls — second run records zero ALTER calls.

## Pattern Reference — Mirrors `enrichment/rss_schema.py`

The plan required mirroring the canonical idempotent ALTER pattern. Confirmed:

| Aspect | `_ensure_rss_columns` (canonical) | `migrate_lang_column` (this plan) |
|--------|-----------------------------------|------------------------------------|
| Pre-check | `PRAGMA table_info(rss_articles)` | `PRAGMA table_info({table})` |
| Existing-cols set | `{row[1] for row in cursor}` | `{row[1] for row in cursor}` |
| Conditional ALTER | `if col_name not in existing` | `if not _column_exists(...)` |
| Commit at end | `conn.commit()` | `conn.commit()` |

Difference: this plan also handles the "table doesn't exist" case (returns `table_missing`) since the migration runs against possibly-fresh DBs in tests. `_ensure_rss_columns` assumes the table is always present (called from `init_rss_schema` after `CREATE TABLE IF NOT EXISTS`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan Test 1 spec inconsistent with algorithm output**
- **Found during:** Task 1 (RED → GREEN cycle)
- **Issue:** Plan asserted `chinese_char_ratio("人工智能 Agent 框架对比 LangChain CrewAI")` returns `(0.3, 0.6)`. Hand-computed: 8 CJK chars / 32 total chars = 0.25 — below the lower bound.
- **Fix:** Renamed test to `test_ratio_mixed_text_hand_computed`; pinned to exact value `pytest.approx(8/32)`. Honors lesson 2026-05-06: tests should pin to independently-verifiable values, not mirror impl.
- **Files modified:** `tests/unit/kb/test_lang_detect.py`
- **Commit:** 946492c

**2. [Rule 3 - Blocking] sqlite3.Connection.execute is read-only in CPython 3.13**
- **Found during:** Task 2 (running idempotency test)
- **Issue:** Plan suggested spying via `conn.execute = spy_execute` direct attribute assignment, which raises `AttributeError: 'sqlite3.Connection' object attribute 'execute' is read-only` on CPython 3.13.
- **Fix:** Wrapped with a `SpyConn` proxy class that owns its own `execute` method delegating to the real `conn._c.execute`. Functions accept duck-typed connections, so this works cleanly.
- **Files modified:** `tests/unit/kb/test_migrate_lang_column.py`
- **Commit:** 28a96c7

### Additions Beyond Plan

- 2 constants-sanity tests in `test_lang_detect.py` (`test_min_text_len_constant`, `test_zh_threshold_constant`) — guard against future drift of locked thresholds (cheap, ~3 LOC each)
- 1 negative-path test in `test_migrate_lang_column.py` (`test_cli_missing_db_exits_1`) — covers the acceptance criterion that requires `python -m kb.scripts.migrate_lang_column` exits 1 with `ERROR: DB not found` on stderr when DB is absent

Total tests delivered: 18 (plan target was 15). All within scope.

## Acceptance Criteria — Self-Check

### Task 1 (lang_detect)

- [x] `kb/data/lang_detect.py` exists; `python -c "from kb.data.lang_detect import detect_lang; print(detect_lang('a'*300))"` outputs `en`
- [x] `python -c "... print(detect_lang('中'*300))"` outputs `zh-CN`
- [x] `python -c "... print(detect_lang('short'))"` outputs `unknown`
- [x] `pytest tests/unit/kb/test_lang_detect.py -v` exits 0 with all tests passing (12 tests)
- [x] File contains exact strings: `"一"`, `"鿿"`, `MIN_TEXT_LEN: int = 200`, `ZH_THRESHOLD: float = 0.30`
- [x] No `import sqlite3`, no `import requests`, no `os.environ` calls (pure function module)

### Task 2 (migration)

- [x] `kb/scripts/migrate_lang_column.py` exists; imports without error
- [x] `pytest tests/unit/kb/test_migrate_lang_column.py -v` exits 0 with all tests passing (6 tests)
- [x] File contains string `PRAGMA table_info` (verifies pattern adopted from rss_schema.py)
- [x] File contains string `ALTER TABLE` (idempotency proven via spy + tests)
- [x] `python -m kb.scripts.migrate_lang_column` runs against missing DB and exits 1 with `ERROR: DB not found` on stderr
- [x] Second invocation against populated DB outputs `articles: already_present` / `rss_articles: already_present`

## Requirements Satisfied

- **DATA-01**: Idempotent migration script for `articles.lang` + `rss_articles.lang` ✓
- **DATA-02**: Detector algorithm + thresholds (driver script in plan kb-1-04) ✓

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | `946492c` | feat(kb-1-02): add kb.data.lang_detect — pure-function CJK ratio detector |
| 2 | `28a96c7` | feat(kb-1-02): add kb.scripts.migrate_lang_column — idempotent ALTER for lang TEXT |

## Self-Check: PASSED

All files created exist on disk, both commits present in git log, all 18 unit tests pass.
