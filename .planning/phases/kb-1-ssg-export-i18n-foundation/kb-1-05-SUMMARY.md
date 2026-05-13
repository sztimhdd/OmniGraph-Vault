---
phase: kb-1-ssg-export-i18n-foundation
plan: "05"
subsystem: kb
tags: [kb, data-layer, lang-detect, sqlite, cli-driver]
dependency-graph:
  requires:
    - kb-1-01 (kb.config.KB_DB_PATH)
    - kb-1-02 (kb.data.lang_detect.detect_lang + kb.scripts.migrate_lang_column.migrate_lang_column)
  provides:
    - kb.scripts.detect_article_lang.detect_for_table
    - kb.scripts.detect_article_lang.coverage_for_table
    - kb.scripts.detect_article_lang.main (CLI)
  affects:
    - kb-1-06 (article-query — relies on populated articles.lang / rss_articles.lang)
    - kb-1 list pages + article detail pages (I18N-04, I18N-05, I18N-06 — need lang populated)
    - kb-4 daily cron (DATA-03 — script runs daily, idempotency makes that safe)
tech-stack:
  added: []
  patterns:
    - "WHERE lang IS NULL" idempotency filter (mirrors kb-1-02 PRAGMA pre-check style)
    - Auto-heal: driver invokes migrate_lang_column when lang column absent
    - "with sqlite3.connect(...) as conn" context-managed transaction
key-files:
  created:
    - kb/scripts/detect_article_lang.py
    - tests/unit/kb/test_detect_article_lang.py
  modified: []
decisions:
  - "Auto-migration on missing column (defensive): caller never has to remember to run migrate_lang_column first. Per CLAUDE.md Rule 2 (auto-add critical functionality), this is a correctness requirement — running detect on a pre-migration DB without auto-heal would crash on the first UPDATE."
  - "Bonus tests (coverage_for_table sanity + missing-table tolerance) — 7 total instead of plan's 5. Same precedent as kb-1-02 (18 tests vs plan's 15). Cheap, ~10 LOC."
  - "Coverage report format: `{table}: updated={dict}, total_coverage={dict}` — 'updated' is the new assignments this run; 'total_coverage' is the entire table's lang distribution including NULLs. Gives operator visibility into both incremental work and remaining gap."
metrics:
  duration: ~7 min
  tasks-completed: 1
  tests-added: 7
  tests-passing: 7
  commits: 2
  completed-date: 2026-05-13
requirements: [DATA-02, DATA-03]
---

# Phase kb-1 Plan 05: Detect Article Lang Driver Summary

**One-liner:** CLI driver `kb/scripts/detect_article_lang.py` walks `articles` + `rss_articles`, applies `detect_lang(body)`, and UPDATEs `lang` column where NULL — idempotent, auto-migrating, daily-cron-safe (DATA-03).

## What Was Built

### `kb/scripts/detect_article_lang.py` (97 LOC)

CLI driver that consumes `kb.data.lang_detect.detect_lang` (kb-1-02) and `kb.scripts.migrate_lang_column.migrate_lang_column` (kb-1-02).

| Function | Purpose |
| --- | --- |
| `_ensure_lang_column(conn)` | Pre-flight: invokes `migrate_lang_column` if `lang` column absent on either target table. Self-heals fresh DBs. |
| `detect_for_table(conn, table) -> Counter[str]` | Library function — UPDATEs rows where `lang IS NULL`, returns `Counter` of new assignments. Skips missing tables. |
| `coverage_for_table(conn, table) -> Counter[str]` | Library function — returns `lang` distribution across ALL rows (NULL counted as `'NULL'`). Operator visibility. |
| `main() -> int` | CLI entry — reads `config.KB_DB_PATH`, runs migration + detection on both tables, prints `{table}: updated={...}, total_coverage={...}` per table. Returns 1 + stderr on missing DB. |

Targets: `_TABLES = ("articles", "rss_articles")`. Both must have `body TEXT` and `lang TEXT` (latter added by migration if absent).

### Tests — `tests/unit/kb/test_detect_article_lang.py` (222 LOC)

7 tests, all passing:

| # | Test | Coverage |
|---|------|----------|
| 1 | `test_detect_for_table_classifies_zh_en_unknown` | 3-row table → exactly 1 zh-CN, 1 en, 1 unknown (DATA-02 algorithm) |
| 2 | `test_detect_for_table_is_idempotent` | Second run → `Counter()` empty, `total_changes` delta == 0 (DATA-03 proof) |
| 3 | `test_main_prints_coverage_for_both_tables` | stdout contains `articles:`, `rss_articles:`, `zh-CN`, `en` |
| 4 | `test_main_auto_runs_migration_when_lang_column_missing` | Fresh DB without lang column → driver self-heals + populates |
| 5 | `test_detect_for_table_handles_null_and_empty_body` | NULL or empty body → `lang='unknown'` (defensive) |
| 6 | `test_coverage_for_table_counts_all_rows` | Coverage includes NULL rows as `'NULL'` (sanity) |
| 7 | `test_detect_for_table_skips_missing_table` | Missing table → empty `Counter` (no error) |

```
tests/unit/kb/test_detect_article_lang.py::test_detect_for_table_classifies_zh_en_unknown PASSED
tests/unit/kb/test_detect_article_lang.py::test_detect_for_table_is_idempotent PASSED
tests/unit/kb/test_detect_article_lang.py::test_main_prints_coverage_for_both_tables PASSED
tests/unit/kb/test_detect_article_lang.py::test_main_auto_runs_migration_when_lang_column_missing PASSED
tests/unit/kb/test_detect_article_lang.py::test_detect_for_table_handles_null_and_empty_body PASSED
tests/unit/kb/test_coverage_for_table_counts_all_rows PASSED
tests/unit/kb/test_detect_for_table_skips_missing_table PASSED
============================== 7 passed in 0.13s ==============================
```

## Idempotency Proof

Driver invoked twice against a fresh temp DB seeded with 3 articles + 2 rss_articles:

```
=== First run ===
articles: updated={'zh-CN': 1, 'en': 1, 'unknown': 1}, total_coverage={'zh-CN': 1, 'en': 1, 'unknown': 1}
rss_articles: updated={'zh-CN': 1, 'en': 1}, total_coverage={'zh-CN': 1, 'en': 1}

=== Second run (idempotent) ===
articles: updated={}, total_coverage={'zh-CN': 1, 'en': 1, 'unknown': 1}
rss_articles: updated={}, total_coverage={'zh-CN': 1, 'en': 1}
```

Second run reports `updated={}` for both tables — zero UPDATE statements issued because the `WHERE lang IS NULL` filter excludes all already-classified rows. This is the DATA-03 proof: cron-safe daily re-invocation.

Test 2 (`test_detect_for_table_is_idempotent`) additionally asserts `conn.total_changes` delta == 0 between snapshots.

## Coverage Report Sample

`articles: updated={'zh-CN': 1, 'en': 1, 'unknown': 1}, total_coverage={'zh-CN': 1, 'en': 1, 'unknown': 1}`

- `updated` — new lang assignments made *this run* (Counter)
- `total_coverage` — full lang distribution including NULL (Counter, with NULL stringified as `'NULL'`)

Operator can read both at a glance: incremental work + remaining gap. On a daily cron, expect `updated={}` after the first day's full sweep — every subsequent day only sees the ingest delta.

## Auto-Migration Proof

Test 4 creates a fresh DB *without* the `lang` column (pre-migration shape), inserts rows, invokes `main()`. After invocation:

- `PRAGMA table_info(articles)` shows `lang` column ✓
- `PRAGMA table_info(rss_articles)` shows `lang` column ✓
- Inserted Chinese row has `lang='zh-CN'` ✓
- Inserted English row has `lang='en'` ✓

The driver's `_ensure_lang_column(conn)` pre-flight detected the missing column and called `migrate_lang_column(conn)` before issuing any UPDATEs. This is a CLAUDE.md Rule 2 deviation (auto-add missing critical functionality) — without it, an out-of-order operator invocation would crash on the first UPDATE.

## Pattern Reference — Mirrors kb-1-02

| Aspect | `migrate_lang_column` (kb-1-02) | `detect_for_table` (this plan) |
|---|---|---|
| Idempotency mechanism | `PRAGMA table_info` pre-check, ALTER only on absence | `WHERE lang IS NULL` filter, UPDATE only on NULL |
| Tables targeted | `articles` + `rss_articles` | `articles` + `rss_articles` |
| Missing-table behavior | Returns `'table_missing'` (no error) | Returns empty `Counter` (no error) |
| Commit boundary | Single `conn.commit()` after all ALTERs | Single `conn.commit()` after all UPDATEs in one table |
| CLI shape | `main()` reads `config.KB_DB_PATH`, returns int exit code | `main()` reads `config.KB_DB_PATH`, returns int exit code |

## Deviations from Plan

### Auto-fixed Issues

None. Plan executed exactly as written — the 5 specified test behaviors all landed; algorithm, function signatures, file paths, and import statements all match the plan's `<action>` spec verbatim.

### Additions Beyond Plan

- 2 bonus tests (`test_coverage_for_table_counts_all_rows` + `test_detect_for_table_skips_missing_table`) — exercise the `coverage_for_table` and missing-table branches that the plan's main()/detect_for_table tests touch only indirectly. ~10 LOC, same precedent as kb-1-02 (18 tests vs plan's 15).

Total tests delivered: 7 (plan target was 5). All within scope.

## Acceptance Criteria — Self-Check

- [x] `kb/scripts/detect_article_lang.py` exists; `python -c "from kb.scripts.detect_article_lang import detect_for_table, main; print('OK')"` exits 0
- [x] `pytest tests/unit/kb/test_detect_article_lang.py -v` exits 0 with all tests passing (7 tests)
- [x] File contains exact strings: `WHERE lang IS NULL`, `UPDATE`, `from kb.data.lang_detect import detect_lang`, `from kb.scripts.migrate_lang_column import migrate_lang_column`
- [x] File contains the table tuple `("articles", "rss_articles")`
- [x] Idempotency proof: Test 2 asserts `conn.total_changes` delta == 0 on second run
- [x] Coverage report format: stdout contains `articles:` and `rss_articles:` substrings (Test 3)

## Requirements Satisfied

- **DATA-02**: Driver populates `lang` column based on Chinese char ratio (algorithm from kb-1-02 `kb.data.lang_detect.detect_lang`) — coverage report shows zh-CN / en / unknown counts ✓
- **DATA-03**: Incremental + idempotent (`WHERE lang IS NULL` filter); daily cron in kb-4 can re-invoke safely ✓

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | `38a7990` | test(kb-1-05): add failing tests for detect_article_lang driver |
| 2 | `16865b4` | feat(kb-1-05): add detect_article_lang driver — DATA-02 + DATA-03 |

## Self-Check: PASSED

- File `kb/scripts/detect_article_lang.py` exists: FOUND
- File `tests/unit/kb/test_detect_article_lang.py` exists: FOUND
- Commit `38a7990` (test RED): FOUND
- Commit `16865b4` (feat GREEN): FOUND
- 7/7 unit tests pass
- Acceptance grep checks all pass (5/5 required strings present)
- Idempotency demonstrated via real run (second run `updated={}`) + asserted in Test 2
