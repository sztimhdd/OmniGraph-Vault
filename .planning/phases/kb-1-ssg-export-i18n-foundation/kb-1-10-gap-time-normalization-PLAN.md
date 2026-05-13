---
phase: kb-1-ssg-export-i18n-foundation
plan: "10"
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/data/article_query.py
  - kb/export_knowledge_base.py
  - tests/unit/kb/test_article_query.py
  - tests/integration/kb/test_export.py
autonomous: true
gap_closure: true
requirements:
  - DATA-04
  - EXPORT-01
  - EXPORT-03
  - I18N-04

user_setup: []

must_haves:
  truths:
    - "Running `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` exits 0 with no TypeError"
    - "kb/data/article_query.list_articles() works against the production schema where articles.update_time is INTEGER (Unix epoch) and rss_articles.published_at is TEXT (ISO-8601), without raising TypeError on the merge sort at line 165"
    - "The integration fixture at tests/integration/kb/test_export.py mirrors production schema (articles.update_time INTEGER) so future regressions of the same shape are caught by CI"
    - "kb/export_knowledge_base.py fails fast with a clear, actionable error message when articles.lang or rss_articles.lang columns are absent (instead of leaking a deep stack trace)"
  artifacts:
    - path: "kb/data/article_query.py"
      provides: "_row_to_record_kol normalizes integer Unix-epoch update_time to ISO-8601 string at the row mapper boundary"
      contains: "isinstance"
    - path: "kb/export_knowledge_base.py"
      provides: "Defensive _ensure_lang_column startup check that fails fast with operator-actionable error referencing migrate_lang_column + detect_article_lang"
      contains: "_ensure_lang_column"
    - path: "tests/unit/kb/test_article_query.py"
      provides: "Production-shape regression test mirroring articles.update_time INTEGER + rss_articles.published_at TEXT"
      contains: "update_time INTEGER"
    - path: "tests/integration/kb/test_export.py"
      provides: "Fixture schema corrected to mirror production (articles.update_time INTEGER, epoch ints inserted)"
      contains: "update_time INTEGER"
  key_links:
    - from: "kb/data/article_query.py::_row_to_record_kol"
      to: "ArticleRecord.update_time"
      via: "isinstance(raw, int) -> datetime.fromtimestamp(raw, tz=timezone.utc).isoformat() else raw"
      pattern: "isinstance\\(.*int\\)"
    - from: "kb/export_knowledge_base.py::main"
      to: "kb.scripts.migrate_lang_column"
      via: "_ensure_lang_column pre-flight check at startup; clear error pointing to migrate_lang_column + detect_article_lang"
      pattern: "_ensure_lang_column"
    - from: "tests/integration/kb/test_export.py::fixture_db"
      to: "production schema"
      via: "articles.update_time declared INTEGER; epoch ints inserted (e.g. 1777249680)"
      pattern: "update_time INTEGER"
---

<objective>
Close the two gaps surfaced by `kb-1-VERIFICATION.md` so the phase kb-1 SSG export driver actually runs end-to-end against `.dev-runtime/data/kol_scan.db`:

1. **Bug fix (BLOCKING):** `kb/data/article_query.py:_row_to_record_kol` passes raw `articles.update_time` (INTEGER Unix epoch in production) into `ArticleRecord.update_time` without normalizing. `_row_to_record_rss` passes raw TEXT ISO strings. `list_articles:165` then sorts the merged list by `update_time` and crashes with `TypeError: '<' not supported between instances of 'int' and 'str'`. All 71 existing tests pass because the integration fixture at `tests/integration/kb/test_export.py:73` declares `update_time TEXT` (uniform type) — fixture diverges from production schema. Fix the row mapper AND the fixture in the same plan.

2. **Defensive guard (operational):** Add `_ensure_lang_column` startup check to `kb/export_knowledge_base.py` that fails fast with an operator-actionable error if `articles.lang` or `rss_articles.lang` columns are absent (pointing the operator to `python -m kb.scripts.migrate_lang_column` + `python -m kb.scripts.detect_article_lang`).

Purpose: The 4 BLOCKED requirements (I18N-04, DATA-04, EXPORT-01, EXPORT-03) flip to SATISFIED once gap 1 closes and a real-DB export run is captured. Phase score moves from 1/8 fully VERIFIED to 7/8 VERIFIED (only the operational owe — gap 2 partial — remains, which this plan also closes via the defensive guard).

Output:
- 2 source files modified (`kb/data/article_query.py`, `kb/export_knowledge_base.py`)
- 2 test files modified (`tests/unit/kb/test_article_query.py`, `tests/integration/kb/test_export.py`)
- 1 SUMMARY.md created
- Real-DB smoke evidence captured (`.scratch/kb-1-10-real-db-smoke-{ts}.log`)

**Lesson reference (CLAUDE.md 2026-05-07 CV-mass-classify postmortem):**
> 任何涉及 ON CONFLICT 子句或 UNIQUE 约束的 schema 改动,ship 之前必须 grep 整个 codebase 把所有使用该约束的 INSERT 调用点都过一遍,并在 production-shape 数据上模拟完整 cron 调用序列(包括 sequential per-topic invocation),Mock-only 单元测试不抓这种 cross-component bug。

Gap 1 is the same anti-pattern with a different surface: integration fixture declared `update_time TEXT` (uniform-type), production has mixed types (INT KOL, TEXT RSS). All 71 tests pass because the fixture does not mirror production schema. This plan installs a production-shape fixture as the **mandatory** acceptance criterion (not "looks correct" — must declare INTEGER + insert epoch ints).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/STATE.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-VERIFICATION.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-SUMMARY.md
@kb/data/article_query.py
@kb/export_knowledge_base.py
@kb/scripts/migrate_lang_column.py
@tests/unit/kb/test_article_query.py
@tests/integration/kb/test_export.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from existing kb/ codebase + production DB. -->
<!-- Use these directly — no codebase exploration needed. -->

From kb/data/article_query.py — current row mappers (the bug):
```python
def _row_to_record_kol(row) -> ArticleRecord:
    return ArticleRecord(
        ...,
        update_time=row["update_time"] or "",  # BUG: row["update_time"] is int in prod (Unix epoch), not str
        ...,
    )

def _row_to_record_rss(row) -> ArticleRecord:
    update_time = row["published_at"] or row["fetched_at"] or ""  # OK: both are TEXT
    ...
```

From kb/data/article_query.py — ArticleRecord dataclass annotation:
```python
@dataclass(frozen=True)
class ArticleRecord:
    update_time: str  # Annotated str; not runtime-enforced (Python dataclasses do not coerce types)
```

From kb/data/article_query.py:165 — the failing sort:
```python
results.sort(key=lambda r: r.update_time, reverse=True)  # TypeError when mixing int + str
```

Production schema (verified 2026-05-13 against .dev-runtime/data/kol_scan.db):
- articles.update_time: INTEGER (Unix epoch seconds, e.g. 1777249680, 1776990480)
- rss_articles.published_at: TEXT (ISO-8601, e.g. '2026-05-02T17:26:40+00:00')
- rss_articles.fetched_at: TEXT (ISO-8601)

From kb/scripts/migrate_lang_column.py — the column-existence check pattern to mirror:
```python
def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols
```

From kb/export_knowledge_base.py:38-56 — module top, where _ensure_lang_column should be added:
```python
import argparse  # noqa: E402
...
from kb import config  # noqa: E402
from kb.data.article_query import (...)  # noqa: E402
from kb.i18n import register_jinja2_filter, validate_key_parity  # noqa: E402
```
The defensive guard should be a private module-level helper invoked from `main()` BEFORE any `list_articles()` call (which is the first thing that touches the DB).

From CLAUDE.md "Lessons Learned 2026-05-07" — the canonical anti-pattern this plan addresses:
> 任何 schema/SQL 改动必须在 production-shape 数据上跑过完整使用场景才能 push。
> Mock-only 单元测试不抓这种 cross-component bug。
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TDD RED — Add production-shape regression tests + fix integration fixture schema</name>
  <files>tests/unit/kb/test_article_query.py, tests/integration/kb/test_export.py</files>
  <read_first>
    - kb/data/article_query.py (full — understand current row mappers + list_articles sort)
    - tests/unit/kb/test_article_query.py (lines 1-50 for fixture style, lines containing "in_memory" or "_make_conn" for the SQLite-in-memory pattern already used)
    - tests/integration/kb/test_export.py (full — current fixture is at line 60-134; lines 66-86 declare schema, lines 88-130 insert rows)
    - Production schema reference: `.dev-runtime/data/kol_scan.db` — verified 2026-05-13: `articles.update_time INTEGER`, `rss_articles.published_at TEXT`, `rss_articles.fetched_at TEXT`.
  </read_first>
  <behavior>
    Two NEW tests in `tests/unit/kb/test_article_query.py` (regression tests) MUST be added:

    - **Test A: `test_list_articles_handles_mixed_int_text_update_time`**
      Setup: in-memory SQLite with PRODUCTION schema:
      ```
      CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
                             body TEXT, content_hash TEXT, lang TEXT, update_time INTEGER);
      CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
                                 body TEXT, content_hash TEXT, lang TEXT,
                                 published_at TEXT, fetched_at TEXT);
      ```
      Insert 1 KOL row with `update_time = 1777249680` (Unix epoch INT, real prod sample) and
      Insert 1 RSS row with `published_at = '2026-05-02T17:26:40+00:00'` (ISO-8601 TEXT).
      Call `list_articles(conn=conn, limit=10)`.
      Assert: no exception raised (specifically NOT `TypeError`). Returned list has 2 records.
      Assert: every `record.update_time` is `isinstance(_, str)` (the row-mapper normalizer must produce strings on both sides).

    - **Test B: `test_row_to_record_kol_normalizes_epoch_int_to_iso`**
      Direct unit test of the row-mapper normalization. Construct a `sqlite3.Row`-like dict
      (use the existing kb-1-06 SpyConn idiom OR an in-memory cursor on the production-shape
      table from Test A). Insert one row with `update_time = 1777249680`. Fetch the row.
      Pass it through `_row_to_record_kol` (import as `from kb.data.article_query import _row_to_record_kol`).
      Assert: `record.update_time` is a string (`isinstance(record.update_time, str)`).
      Assert: `record.update_time` starts with `'2026'` or contains `'-'` (some recognizable
      ISO date marker — exact format is implementation choice but MUST be sortable lexicographically
      against ISO-8601 strings).

    Both tests MUST FAIL on current main (current code passes the int through unchanged → list_articles raises TypeError, _row_to_record_kol returns int).

    ALSO modify `tests/integration/kb/test_export.py` fixture at lines 66-86 + 88-130:
    - Change `articles.update_time TEXT` → `articles.update_time INTEGER`
    - Change Article 1 row insert: `update_time = '2026-05-12 10:00:00'` → `update_time = 1778270400` (epoch for 2026-05-12 10:00:00 UTC; use any plausible epoch int — value just needs to be a real int and > 0)
    - Change Article 2 row insert: `update_time = '2026-05-11 09:00:00'` → `update_time = 1778180400` (or any plausible epoch int that sorts BEFORE Article 1 — keep relative order for `_url_index` ordering assertions)
    - Leave Article 3 (RSS) untouched — `published_at`/`fetched_at` already TEXT, matches prod
    - DO NOT change any test assertions yet (some assertions may break in Task 2 after the fix; will address there)

    Run all tests to confirm RED state:
    - `venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py::test_list_articles_handles_mixed_int_text_update_time tests/unit/kb/test_article_query.py::test_row_to_record_kol_normalizes_epoch_int_to_iso -v` MUST exit non-zero (both tests fail with TypeError or AssertionError on current code).
    - `venv/Scripts/python.exe -m pytest tests/integration/kb/test_export.py -v` is EXPECTED to fail too (the fixture INT now collides with the str sort — that's the same gap surfacing in integration scope).
  </behavior>
  <action>
    1. Open `tests/unit/kb/test_article_query.py`. Append the two regression tests (Test A + Test B above) at end of file. Use the existing in-memory SQLite + `sqlite3.Row` pattern from existing tests in this file. Mark with `@pytest.mark.unit` if the file uses that marker (check existing tests; copy their style).

    2. Open `tests/integration/kb/test_export.py`. In the `fixture_db` fixture (line 55-134):
       - In the `executescript` block (line 64-86): change `update_time TEXT` to `update_time INTEGER` on the `articles` table.
       - In Article 1 INSERT (line 88-100): change the 7th value `"2026-05-12 10:00:00"` to integer `1778270400`.
       - In Article 2 INSERT (line 102-114): change the 7th value `"2026-05-11 09:00:00"` to integer `1778180400`.
       - Leave Article 3 RSS INSERT untouched.

    3. Commit RED:
       ```bash
       node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit "test(kb-1-10): add regression tests for update_time mixed-type bug + production-shape fixture (RED)" --files tests/unit/kb/test_article_query.py tests/integration/kb/test_export.py
       ```

    4. Verify RED. Run both:
       ```
       venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py::test_list_articles_handles_mixed_int_text_update_time tests/unit/kb/test_article_query.py::test_row_to_record_kol_normalizes_epoch_int_to_iso -v
       venv/Scripts/python.exe -m pytest tests/integration/kb/test_export.py -v
       ```
       Both must exit non-zero. Capture exit codes + relevant TypeError stack snippets to `.scratch/kb-1-10-task1-red-{ts}.log`.

    5. Reference CLAUDE.md 2026-05-07 lesson in the commit message body — production-shape fixture is the lesson, not optional.
  </action>
  <verify>
    <automated>
      # Both regression tests added (must exist by name)
      grep -nE "def test_list_articles_handles_mixed_int_text_update_time|def test_row_to_record_kol_normalizes_epoch_int_to_iso" tests/unit/kb/test_article_query.py | wc -l   # expect 2

      # Integration fixture mirrors production schema
      grep -nE "update_time INTEGER" tests/integration/kb/test_export.py | wc -l   # expect >= 1

      # Integration fixture inserts integer epochs (not string timestamps) for KOL rows
      grep -nE "1778270400|1778180400" tests/integration/kb/test_export.py | wc -l  # expect 2 (one per KOL article)

      # RED verified — new unit tests fail on unmodified production code
      venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py::test_list_articles_handles_mixed_int_text_update_time tests/unit/kb/test_article_query.py::test_row_to_record_kol_normalizes_epoch_int_to_iso -v   # expect non-zero exit

      # Commit landed
      git log --oneline -1 | grep -E "kb-1-10.*RED"   # expect match
    </automated>
  </verify>
  <acceptance_criteria>
    - tests/unit/kb/test_article_query.py contains `def test_list_articles_handles_mixed_int_text_update_time` AND `def test_row_to_record_kol_normalizes_epoch_int_to_iso`
    - tests/unit/kb/test_article_query.py contains `update_time INTEGER` in the fixture for Test A
    - tests/integration/kb/test_export.py contains `update_time INTEGER` (NOT `update_time TEXT`)
    - tests/integration/kb/test_export.py contains BOTH integer-epoch values (e.g. `1778270400` and `1778180400`) replacing the previous string timestamps
    - `venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py::test_list_articles_handles_mixed_int_text_update_time tests/unit/kb/test_article_query.py::test_row_to_record_kol_normalizes_epoch_int_to_iso -v` exits NON-ZERO (RED state proven)
    - Most recent commit subject contains `kb-1-10` and `RED`
  </acceptance_criteria>
  <done>Two regression tests added (red), integration fixture upgraded to production-shape schema, RED state captured in commit + log file. Lesson reference (CLAUDE.md 2026-05-07) cited in commit body.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — Normalize epoch INT → ISO string in _row_to_record_kol; verify all 73 tests pass + real-DB smoke</name>
  <files>kb/data/article_query.py, tests/integration/kb/test_export.py</files>
  <read_first>
    - kb/data/article_query.py (lines 86-97 — the function being modified; lines 1-25 — current imports for adding `from datetime import datetime, timezone`)
    - Task 1 RED log at `.scratch/kb-1-10-task1-red-{ts}.log` for exact failing assertion messages
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-VERIFICATION.md (gap 1 "missing" section recommends the exact fix shape: `datetime.fromtimestamp(row['update_time'], tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')` if non-None, else empty string)
  </read_first>
  <behavior>
    The fix has TWO surfaces, both small:

    **Surface 1: `kb/data/article_query.py:_row_to_record_kol` (~5 LOC change)**
    Add `from datetime import datetime, timezone` import (top of file, after existing imports).
    Modify `_row_to_record_kol` to normalize the raw `update_time` value at the row-mapper boundary. Concrete formula (NOT optional — write exactly this branching):
    ```python
    def _normalize_update_time(raw) -> str:
        """Normalize the raw articles.update_time column (INTEGER Unix epoch in prod,
        but historically TEXT in some test fixtures and migration shapes) to a single
        sortable ISO-8601 string form. Returns '' on None/empty/zero.

        Production: articles.update_time is INTEGER (Unix epoch seconds).
        Legacy/test: may be TEXT ISO-8601. Both must produce ISO-8601 string output
        so list_articles can sort uniformly across articles + rss_articles.
        """
        if raw is None or raw == "" or raw == 0:
            return ""
        if isinstance(raw, int):
            return datetime.fromtimestamp(raw, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        return str(raw)  # TEXT path: pass through unchanged
    ```
    Then in `_row_to_record_kol`, replace `update_time=row["update_time"] or ""` with
    `update_time=_normalize_update_time(row["update_time"])`.

    **Surface 2: `tests/integration/kb/test_export.py` assertions (if any depend on the old TEXT timestamp string format)**
    After Task 1 fixed the fixture schema, the existing 6 integration tests may need adjusting if they assumed the old `'2026-05-12 10:00:00'` string appeared anywhere in output (e.g., sitemap `<lastmod>` or _url_index timestamps). Run the integration tests now with the GREEN code; ANY assertion that fails because the rendered timestamp is now ISO-8601 (`'2026-05-12T...'`) instead of space-separated (`'2026-05-12 10:00:00'`) needs updating to match the new ISO output. If no integration assertions depend on the literal string format, leave them alone.

    DO NOT touch `_row_to_record_rss` — RSS columns are already TEXT in production, the function is correct as-is. Confirm with grep + read-pass: `_row_to_record_rss` should remain unchanged.

    Both new unit tests (Test A + Test B from Task 1) MUST flip GREEN. ALL 73 tests (71 prior + 2 new) MUST pass.

    Real-DB smoke (HARD acceptance):
    ```
    KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3
    ```
    MUST exit 0. MUST NOT raise TypeError. MUST produce `kb/output/articles/*.html` files. Capture stdout + exit code + `ls kb/output/articles/` to `.scratch/kb-1-10-real-db-smoke-{ts}.log`.
  </behavior>
  <action>
    1. Open `kb/data/article_query.py`. Add `from datetime import datetime, timezone` to the imports block (after `import re`, before `import sqlite3`).

    2. Add the `_normalize_update_time` private helper above `_row_to_record_kol` (verbatim from the behavior block).

    3. Modify `_row_to_record_kol` line 95: replace `update_time=row["update_time"] or ""` with `update_time=_normalize_update_time(row["update_time"])`.

    4. Verify `_row_to_record_rss` is UNCHANGED (no edits, function still returns the TEXT-passthrough form).

    5. Run unit tests:
       ```
       venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py -v
       ```
       Expect: all tests including the 2 new Task 1 tests pass.

    6. Run integration tests:
       ```
       venv/Scripts/python.exe -m pytest tests/integration/kb/test_export.py -v
       ```
       Triage failures. If any failure is "expected timestamp '2026-05-12 10:00:00' but got '2026-05-12T10:00:00+00:00'" (the ISO-8601 form), update the assertion to match the new ISO form. Document each touched assertion in commit body. If a failure is anything else (e.g., assertion about file count, og: tags, lang badge), STOP — that's a regression, not a string-format adjustment; investigate.

    7. Run full kb test suite:
       ```
       venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -v
       ```
       MUST be ≥ 73 passed (71 prior + 2 new from Task 1).

    8. Real-DB smoke (the gold acceptance — proves gap 1 is closed):
       ```
       set "KB_DB_PATH=.dev-runtime/data/kol_scan.db"
       venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3 > .scratch/kb-1-10-real-db-smoke-stdout.log 2> .scratch/kb-1-10-real-db-smoke-stderr.log
       echo $?  # MUST be 0
       ls kb/output/articles/*.html | wc -l  # MUST be ≥ 3
       ```
       Tee both stdout + stderr + exit code + file listing into `.scratch/kb-1-10-real-db-smoke-{ts}.log`. THIS LOG IS THE GOLD EVIDENCE for SUMMARY.md (cited verbatim with file path + line numbers — no fabrication; see CLAUDE.md 2026-05-08 ir-1 fabrication lesson).

    9. Commit GREEN:
       ```bash
       node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit "fix(kb-1-10): normalize KOL update_time epoch INT to ISO string in row mapper (GREEN); resolves TypeError in list_articles against production schema" --files kb/data/article_query.py tests/integration/kb/test_export.py
       ```
  </action>
  <verify>
    <automated>
      # Source fix in place
      grep -nE "isinstance.*int.*\)|datetime\.fromtimestamp.*tz=timezone\.utc" kb/data/article_query.py | wc -l   # expect >= 1
      grep -nE "_normalize_update_time" kb/data/article_query.py | wc -l   # expect >= 2 (helper + call site)
      grep -nE "from datetime import datetime, timezone" kb/data/article_query.py | wc -l   # expect 1

      # _row_to_record_rss UNCHANGED — still uses the published_at OR fetched_at OR "" pattern
      grep -nE 'row\["published_at"\] or row\["fetched_at"\]' kb/data/article_query.py | wc -l   # expect 1

      # Full kb test suite green
      venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q   # expect "73 passed" or higher; exit 0

      # Real-DB smoke proven by smoke log
      test -f .scratch/kb-1-10-real-db-smoke-*.log
      grep -E "exit ?code:?\s*0|^0$" .scratch/kb-1-10-real-db-smoke-*.log | head -1   # exit 0 captured
      grep -cE "^.*\.html$" .scratch/kb-1-10-real-db-smoke-*.log | head -1   # >= 3 article HTMLs

      # Commit landed
      git log --oneline -1 | grep -E "kb-1-10.*GREEN"   # expect match
    </automated>
  </verify>
  <acceptance_criteria>
    - kb/data/article_query.py contains `from datetime import datetime, timezone`
    - kb/data/article_query.py contains `def _normalize_update_time` AND `isinstance(raw, int)` AND `datetime.fromtimestamp(raw, tz=timezone.utc)`
    - kb/data/article_query.py `_row_to_record_kol` calls `_normalize_update_time(row["update_time"])` — old `row["update_time"] or ""` form REMOVED
    - kb/data/article_query.py `_row_to_record_rss` UNCHANGED (still uses `row["published_at"] or row["fetched_at"] or ""`)
    - `venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q` exits 0 with at least 73 tests passed
    - Real-DB smoke log file exists at `.scratch/kb-1-10-real-db-smoke-*.log` and contains exit code 0 + ≥ 3 HTML filenames
    - `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` exits 0 (no TypeError)
    - Most recent commit subject contains `kb-1-10` and `GREEN`
  </acceptance_criteria>
  <done>Gap 1 closed. KOL epoch INT normalizes to ISO-8601 string at the row-mapper boundary. All 73+ tests pass. Real-DB smoke proves end-to-end export against production schema. RSS path untouched (was correct). Smoke log committed (or saved to .scratch with exact path cited in commit body — no fabrication).</done>
</task>

<task type="auto">
  <name>Task 3: Defensive guard — _ensure_lang_column startup check in export driver</name>
  <files>kb/export_knowledge_base.py</files>
  <read_first>
    - kb/export_knowledge_base.py (full file — understand current main() flow; the guard goes at the START of main(), before any list_articles call)
    - kb/scripts/migrate_lang_column.py (lines 23-33 — the `_table_exists` + `_column_exists` helpers to mirror the pattern; DO NOT import from kb.scripts.* — duplicate the 6 lines locally to keep the export driver self-contained per CLAUDE.md "Surgical Changes")
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-VERIFICATION.md (gap 2 "missing" section recommends adding `_ensure_lang_column` startup self-check that exits with clear error if columns absent)
  </read_first>
  <action>
    1. Open `kb/export_knowledge_base.py`. Locate `main()` function.

    2. Add private module-level helper `_ensure_lang_column(db_path: Path) -> None` near the top of the file (just after the existing helper functions, before `main()`):
       ```python
       def _ensure_lang_column(db_path: Path) -> None:
           """Pre-flight check: fail fast if articles.lang or rss_articles.lang are absent.

           The export driver hard-depends on the lang column (DATA-04 list_articles filters by it,
           templates emit `<html lang>` from it). If the migration was never run on this DB,
           list_articles raises an opaque sqlite3.OperationalError. Catch it here and surface
           an operator-actionable error pointing at the migration + detection scripts.
           """
           import sqlite3
           with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
               for table in ("articles", "rss_articles"):
                   cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                   if "lang" not in cols:
                       raise SystemExit(
                           f"ERROR: '{table}.lang' column missing in {db_path}.\n"
                           f"Run the lang-column migration + detection first:\n"
                           f"  KB_DB_PATH={db_path} venv/Scripts/python.exe -m kb.scripts.migrate_lang_column\n"
                           f"  KB_DB_PATH={db_path} venv/Scripts/python.exe -m kb.scripts.detect_article_lang\n"
                           f"Both scripts are idempotent — safe to re-run."
                       )
       ```

    3. In `main()`, add a call to `_ensure_lang_column(config.KB_DB_PATH)` BEFORE the first `list_articles()` call (i.e. after `validate_key_parity()` if that's the first thing main does, but BEFORE any DB-touching list call).

    4. Verify the existing 6 integration tests still pass — fixture has lang columns populated already, so `_ensure_lang_column` is a no-op there.

    5. Smoke the negative branch (the new error path):
       ```
       # Create a temp DB with NO lang column to verify the guard fires cleanly
       venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('.scratch/kb-1-10-no-lang.db'); c.executescript('CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT, update_time INTEGER); CREATE TABLE rss_articles(id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT, published_at TEXT, fetched_at TEXT);'); c.commit(); c.close()"
       set "KB_DB_PATH=.scratch/kb-1-10-no-lang.db"
       venv/Scripts/python.exe kb/export_knowledge_base.py --limit 1
       # Expect: non-zero exit + stderr matches "ERROR: 'articles.lang' column missing" + "migrate_lang_column"
       ```
       Capture into `.scratch/kb-1-10-guard-smoke-{ts}.log`.

    6. Re-run the GREEN happy path to confirm no regression:
       ```
       venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q   # 73+ pass
       set "KB_DB_PATH=.dev-runtime/data/kol_scan.db"
       venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3   # exit 0
       ```

    7. Commit:
       ```bash
       node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit "feat(kb-1-10): _ensure_lang_column startup guard in export driver fails fast with operator-actionable error when lang columns absent" --files kb/export_knowledge_base.py
       ```
  </action>
  <verify>
    <automated>
      # Helper added to module
      grep -nE "def _ensure_lang_column" kb/export_knowledge_base.py | wc -l   # expect 1

      # Helper invoked from main()
      grep -nE "_ensure_lang_column\(" kb/export_knowledge_base.py | wc -l   # expect >= 2 (def + call)

      # Error message references both remediation scripts (operator-actionable)
      grep -nE "migrate_lang_column" kb/export_knowledge_base.py | wc -l   # expect >= 1
      grep -nE "detect_article_lang" kb/export_knowledge_base.py | wc -l   # expect >= 1

      # Negative-branch smoke proven (guard fires cleanly on lang-less DB)
      test -f .scratch/kb-1-10-guard-smoke-*.log
      grep -E "ERROR.*articles\.lang.*column missing" .scratch/kb-1-10-guard-smoke-*.log   # match required

      # Happy path still green
      venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q   # 73+ pass

      # Real-DB still works
      KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3   # exit 0

      # Commit landed
      git log --oneline -1 | grep -E "kb-1-10.*_ensure_lang_column"   # expect match
    </automated>
  </verify>
  <acceptance_criteria>
    - kb/export_knowledge_base.py contains `def _ensure_lang_column` with docstring referencing DATA-04 + the migration scripts
    - kb/export_knowledge_base.py `main()` calls `_ensure_lang_column(config.KB_DB_PATH)` BEFORE any `list_articles()` invocation
    - Error message format matches: `ERROR: 'articles.lang' column missing in {db_path}` AND mentions both `migrate_lang_column` AND `detect_article_lang`
    - Negative-branch smoke log exists at `.scratch/kb-1-10-guard-smoke-*.log` showing the guard fired with the expected error
    - All 73+ tests still pass (no regression)
    - Real-DB smoke (KB_DB_PATH=.dev-runtime/data/kol_scan.db) still exits 0
    - Most recent commit subject contains `kb-1-10` and `_ensure_lang_column`
  </acceptance_criteria>
  <done>Gap 2 closed (defensive guard). Operator hitting a fresh lang-less DB now sees a clear actionable error instead of a deep stack trace from list_articles. Existing happy paths preserved.</done>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. **All tests pass:**
   ```
   venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -v
   ```
   MUST show 73+ tests passed (71 prior + 2 new from Task 1; integration count unchanged at 6).

2. **Real-DB end-to-end (the verification gold):**
   ```
   set "KB_DB_PATH=.dev-runtime/data/kol_scan.db"
   venv/Scripts/python.exe kb/export_knowledge_base.py --limit 5
   ls kb/output/articles/*.html | wc -l   # >= 5
   grep -E "<lastmod>2026-05" kb/output/sitemap.xml | head -3   # ISO dates from real prod data
   ```

3. **Defensive guard fires on lang-less DB:** verified by Task 3 negative smoke log.

4. **Read-only invariant preserved:**
   ```
   grep -E "(INSERT INTO|UPDATE.*SET|DELETE FROM|\.unlink\(|rmtree)" kb/data/article_query.py kb/export_knowledge_base.py
   # MUST be 0 hits
   ```
   This protects EXPORT-02 across the gap-closure delta.

5. **No regressions in row mapper symmetry:**
   ```
   grep -nE "_row_to_record_rss" kb/data/article_query.py
   ```
   The function should be UNCHANGED relative to the kb-1-06 SUMMARY (verify by reading the function body — passes `row["published_at"] or row["fetched_at"] or ""` through unchanged; we only normalized the KOL side because only KOL has the INT problem).
</verification>

<success_criteria>
The phase kb-1 verification re-run will show:

- **Truth #2 (FAILED → VERIFIED):** Real-DB export run produces a complete `kb/output/` tree.
- **Truth #7 (PARTIAL → VERIFIED):** `list_articles` against production DB returns sorted records with no TypeError.
- **Truths #3-6 (UNCERTAIN → human-verifiable):** Real-DB export output now exists for human browser verification.
- **Requirements I18N-04, DATA-04, EXPORT-01, EXPORT-03 (BLOCKED → SATISFIED):** Once gap 1 closes and a real-DB export captured.
- **Gap 2 (PARTIAL):** Closed — defensive guard fails fast with operator-actionable error if migrations not yet run.

**Phase score after this plan:** 7/8 truths VERIFIED (only operational owe — the migration-was-never-run-on-prod-DB note — remains as a kb-4 deploy preflight item, but the code-level guard prevents the failure mode).

**Commits expected:** 3 (Task 1 RED, Task 2 GREEN, Task 3 guard).
**LOC delta:** ~25 LOC production source + ~40 LOC tests + 4 fixture-line edits = ~70 LOC total.
**Files created:** 1 (`kb-1-10-SUMMARY.md`); 0 new source files; 0 new test files.
**Time budget:** ~10-15 minutes execution.
</success_criteria>

<output>
After all 3 tasks complete and committed, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-10-SUMMARY.md` following the standard summary template. The summary MUST include:

- Frontmatter: `phase: kb-1-ssg-export-i18n-foundation`, `plan: "10"`, `gap_closure: true`, `requirements_completed: [DATA-04, EXPORT-01, EXPORT-03, I18N-04]`, commit list
- "Gaps closed" section citing kb-1-VERIFICATION.md gap 1 + gap 2 by truth-text
- Real-DB smoke evidence — verbatim citation of `.scratch/kb-1-10-real-db-smoke-*.log` file path + exit code + output file count (NO FABRICATION per CLAUDE.md 2026-05-08 ir-1 lesson)
- Negative-branch evidence — citation of `.scratch/kb-1-10-guard-smoke-*.log`
- Test count delta (71 → 73)
- Commit list (3 commits)
- "Self-Check: PASSED" section confirming all 4 acceptance-criteria blocks met
</output>
