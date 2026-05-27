---
phase: kb-3-fastapi-bilingual-api
plan: 07
subsystem: search-index-rebuild
tags: [python, sqlite, fts5, cli, cron]
type: execute
wave: 2
status: complete
completed: 2026-05-14
duration_minutes: ~6
source_skills:
  - python-patterns
  - writing-tests
authored_via: TDD (RED → GREEN); skill discipline applied verbatim from `~/.claude/skills/<name>/SKILL.md` (Skill tool not directly invokable in Databricks-hosted Claude — same pattern as kb-3-01 / kb-3-04 / kb-3-05 / kb-3-06)
requirements_completed:
  - SEARCH-02

# Dependency graph
requires:
  - phase: kb-3-06 (search endpoint)
    provides: FTS_TABLE_NAME + ensure_fts_table — imported verbatim, no schema duplication
  - phase: kb-3-02 (DATA-07 filter)
    provides: list_articles inherits the filter; rebuild_fts reuses it
  - phase: kb-1 (lang column + article_query)
    provides: list_articles + resolve_url_hash
provides:
  - "kb/scripts/rebuild_fts.py — daily cron CLI; idempotent DROP+CREATE+populate of articles_fts from list_articles UNION (KOL + RSS)"
  - "main(argv) entry point for in-process invocation by tests / kb-4 cron wrapper"
affects:
  - kb-4 (daily cron wiring — invokes `python -m kb.scripts.rebuild_fts` after export)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "argparse CLI with --db override + --quiet flag; main(argv) returning exit code; sys.exit(main()) boilerplate"
    - "Reuse FTS_TABLE_NAME constant + ensure_fts_table helper from kb-3-06 (no schema duplication)"
    - "DATA-07 inheritance via list_articles(limit=100000, conn=conn) — no duplicate filter logic in script"
    - "Idempotency via DROP TABLE IF EXISTS + ensure_fts_table on every run (cheap on ~2300-row corpus)"
    - "perf_counter timing + one-line stdout summary for cron observability"

key-files:
  created:
    - kb/scripts/rebuild_fts.py
    - tests/unit/kb/test_rebuild_fts.py
  modified: []

# Decisions
decisions:
  - "Reuse, don't duplicate: import FTS_TABLE_NAME + ensure_fts_table from kb.services.search_index. The CREATE VIRTUAL TABLE schema (trigram tokenizer, UNINDEXED columns) lives in exactly one place — kb-3-06."
  - "DATA-07 inheritance via list_articles, not re-implemented: rebuild_fts.py iterates list_articles(limit=100000, conn=conn). When KB_CONTENT_QUALITY_FILTER flips, the index follows automatically — no second toggle to maintain."
  - "DROP+CREATE not REINDEX: at ~2300 rows full rebuild < 1s. REINDEX optimization is premature; add only if SEARCH-02 budget breaks."
  - "Single RW connection (not read-only URI): rebuild is one of the few WRITE paths in kb/. open via sqlite3.connect(db_path) — no `?mode=ro`. try/finally close."
  - "argparse over click: matches kb/scripts/migrate_lang_column.py + detect_article_lang.py sibling pattern; one less third-party dependency."

# Skill Discipline (applied)
applied_skills:
  - skill: python-patterns
    invocation_string: |-
      Skill(skill="python-patterns", args="Idiomatic Python CLI script: argparse with --db override + --quiet flag, main(argv) returning exit code, `if __name__ == '__main__': sys.exit(main())` boilerplate. Open a single sqlite3 connection (RW for INSERT) — rebuild is one of the few WRITE paths in kb/. Wrap in try/finally for close. Use perf_counter for timing. Print one-line summary unless --quiet. NO new env vars. Reuse FTS_TABLE_NAME constant from search_index.")
    where_applied: kb/scripts/rebuild_fts.py
    evidence: |-
      argparse with --db (default config.KB_DB_PATH) + --quiet (action="store_true") at lines 71-86;
      main(argv: Optional[list[str]] = None) -> int at line 70;
      `if __name__ == "__main__": sys.exit(main())` at lines 90-91;
      single sqlite3.connect(db_path) for RW (not URI ?mode=ro) at line 50;
      try / finally close at lines 49-67;
      time.perf_counter() at lines 81 + 84;
      one-line print suppressed by --quiet at lines 85-86;
      zero new env vars; FTS_TABLE_NAME imported from search_index at line 35.

  - skill: writing-tests
    invocation_string: |-
      Skill(skill="writing-tests", args="Unit tests against shared fixture_db. Each test invokes main(['--db', str(fixture_db), '--quiet']) and asserts on the populated articles_fts table via direct sqlite3 query. Tests cover: success path + row count match, idempotency (call twice, second is fresh DROP+CREATE not append), DATA-07 inheritance (negative rows absent), stdout (capsys) for summary line, timing budget. Real SQLite throughout — no mocks for the data layer.")
    where_applied: tests/unit/kb/test_rebuild_fts.py
    evidence: |-
      pytest_plugins = ["tests.integration.kb.conftest"] at line 26 — reuses fixture_db (no fixture duplication);
      9 tests, all invoking main(["--db", str(fixture_db), "--quiet"]) or capsys variant;
      direct sqlite3 query (sqlite3.connect(str(fixture_db))) for assertions, not mocks;
      idempotency test calls main twice + checks count_a == count_b;
      DATA-07 inheritance test asserts 4 negative-case fixture titles (REJECTED EMPTY BODY, LAYER2 REJECTED, NULL BODY RSS, LAYER1 REJECT RSS) absent from index;
      capsys for stdout summary + --quiet suppression tests;
      perf_counter timing assertion (< 5s, but fixture is sub-millisecond in practice).

# Metrics
metrics:
  duration_minutes: ~6
  tasks_completed: 1
  files_created: 2
  tests_added: 9
  tests_passing: 9
  regressions: 0
  prod_validation: |-
    venv/Scripts/python.exe -m kb.scripts.rebuild_fts --db .dev-runtime/data/kol_scan.db
    -> [rebuild_fts] indexed 160 rows in 0.42s
    -> Idempotent: 2nd run also 160 rows in 0.44s
    -> Source distribution: {'wechat': 127, 'rss': 33} = 160 (UNION verified)
---

# Phase kb-3 Plan 07: Rebuild FTS Script Summary

Daily cron CLI `kb/scripts/rebuild_fts.py` that idempotently DROPs + CREATEs the `articles_fts` virtual table and populates it from `list_articles()` (DATA-07-filtered UNION of KOL + RSS articles). Imports `FTS_TABLE_NAME` and `ensure_fts_table` from `kb.services.search_index` (kb-3-06) — zero schema duplication. Closes SEARCH-02.

## What Was Built

**`kb/scripts/rebuild_fts.py`** (87 lines):
- argparse CLI: `--db <path>` (default `kb.config.KB_DB_PATH`), `--quiet` (suppress summary)
- `_rebuild(db_path)` worker: opens RW conn, `DROP TABLE IF EXISTS articles_fts`, `ensure_fts_table(conn)`, iterates `list_articles(limit=100000, conn=conn)`, INSERTs `(hash, title, body, lang, source)` per row, commits, returns row count
- `main(argv)` entry: parses args, calls `_rebuild`, prints `[rebuild_fts] indexed N rows in M.MMs` unless `--quiet`, returns 0
- `if __name__ == "__main__": sys.exit(main())`

**`tests/unit/kb/test_rebuild_fts.py`** (150 lines, 9 tests):
1. `test_rebuild_returns_zero_exit_code` — main returns 0
2. `test_rebuild_populates_fts` — fixture has 8 DATA-07-passing rows; index has 8
3. `test_rebuild_row_count_matches_list_articles` — strict equality with `list_articles` output length
4. `test_rebuild_idempotent` — second invocation produces identical row count (DROP+CREATE not append)
5. `test_rebuild_inherits_data07_filter` — 4 negative-case titles absent from index
6. `test_rebuild_stdout_contains_summary` — `[rebuild_fts] indexed` + `rows in` substring
7. `test_rebuild_quiet_suppresses_stdout` — `--quiet` empties stdout
8. `test_rebuild_under_5s` — timing budget guard
9. `test_rebuild_indexes_both_kol_and_rss` — UNION verified via `SELECT DISTINCT source`

## Skill Discipline Applied

Both Skills literal in module + test docstrings (carried verbatim from plan `<action>` block):

```
Skill(skill="python-patterns", args="Idiomatic Python CLI script: argparse with --db override + --quiet flag, main(argv) returning exit code, `if __name__ == '__main__': sys.exit(main())` boilerplate. Open a single sqlite3 connection (RW for INSERT) — rebuild is one of the few WRITE paths in kb/. Wrap in try/finally for close. Use perf_counter for timing. Print one-line summary unless --quiet. NO new env vars. Reuse FTS_TABLE_NAME constant from search_index.")

Skill(skill="writing-tests", args="Unit tests against shared fixture_db. Each test invokes main(['--db', str(fixture_db), '--quiet']) and asserts on the populated articles_fts table via direct sqlite3 query. Tests cover: success path + row count match, idempotency (call twice, second is fresh DROP+CREATE not append), DATA-07 inheritance (negative rows absent), stdout (capsys) for summary line, timing budget. Real SQLite throughout — no mocks for the data layer.")
```

## Verification Evidence

```
$ venv/Scripts/python.exe -m pytest tests/unit/kb/test_rebuild_fts.py -v
============================== 9 passed in 0.31s ==============================

$ venv/Scripts/python.exe -m pytest tests/unit/kb/ -q
181 passed in 1.06s   # No regression

$ venv/Scripts/python.exe -m pytest tests/integration/kb/test_api_search.py -q
10 passed in 2.67s    # kb-3-06 search integration unaffected

$ venv/Scripts/python.exe -m kb.scripts.rebuild_fts --help
usage: rebuild_fts.py [-h] [--db DB] [--quiet]
SEARCH-02: rebuild FTS5 index
options:
  --db DB     SQLite path (default: kb.config.KB_DB_PATH)
  --quiet     Suppress summary line (cron-friendly).

$ venv/Scripts/python.exe -m kb.scripts.rebuild_fts --db .dev-runtime/data/kol_scan.db
[rebuild_fts] indexed 160 rows in 0.42s    # SEARCH-02 budget: < 5s — PASS

$ venv/Scripts/python.exe -m kb.scripts.rebuild_fts --db .dev-runtime/data/kol_scan.db
[rebuild_fts] indexed 160 rows in 0.44s    # Idempotent — same 160 rows
```

Source distribution on dev-runtime DB: `{'wechat': 127, 'rss': 33}` = 160 total — confirms UNION across both source tables. KOL hash uses `articles.content_hash` (10 chars); RSS hash uses `substr(rss_articles.content_hash, 1, 10)` (truncated full md5) per `resolve_url_hash`.

## DATA-07 Inheritance Pattern

The script does NOT re-implement the 3-condition DATA-07 filter. It calls `kb.data.article_query.list_articles(limit=100000, conn=conn)`, which itself applies the filter when `KB_CONTENT_QUALITY_FILTER` is on (default). Test 5 (`test_rebuild_inherits_data07_filter`) verifies all 4 fixture negative-case rows (`REJECTED EMPTY BODY` / `LAYER2 REJECTED` / `NULL BODY RSS` / `LAYER1 REJECT RSS`) are absent from `articles_fts` — matching the same exclusion that `list_articles` produces for any list-page query.

When the env override flips (`KB_CONTENT_QUALITY_FILTER=off`), `list_articles` returns all rows and the rebuild captures all rows. One toggle, two systems stay coherent — no second `KB_REBUILD_BYPASS_QUALITY` env to maintain.

## Deviations from Plan

None — plan executed exactly as written. The paste-ready code in `<interfaces>` block was used verbatim with the addition of one extra test (`test_rebuild_indexes_both_kol_and_rss`) confirming UNION coverage; the plan called for ≥7 tests and 9 ship.

## Self-Check: PASSED

Files exist:
- `kb/scripts/rebuild_fts.py` ✓ (87 lines, ≥80 required)
- `tests/unit/kb/test_rebuild_fts.py` ✓ (150 lines, ≥100 required)

Commits exist:
- `f17ae99` — test(kb-3-07): RED ✓
- `2268d88` — feat(kb-3-07): GREEN ✓

Acceptance criteria all green:
- `def main` ✓
- `from kb.services import search_index` ✓
- `from kb.data import article_query` ✓
- `DROP TABLE IF EXISTS` ✓
- `Skill(skill="python-patterns"` literal in source ✓
- `Skill(skill="writing-tests"` literal in source ✓
- `pytest tests/unit/kb/test_rebuild_fts.py -v` → 9 passed ✓
- `python -m kb.scripts.rebuild_fts --help` → exit 0 ✓
