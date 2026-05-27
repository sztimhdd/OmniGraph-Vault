---
phase: kb-1-ssg-export-i18n-foundation
plan: 05
type: execute
wave: 2
depends_on: ["kb-1-01-config-skeleton", "kb-1-02-migration-lang-detect"]
files_modified:
  - kb/scripts/detect_article_lang.py
  - tests/unit/kb/test_detect_article_lang.py
autonomous: true
requirements:
  - DATA-02
  - DATA-03

must_haves:
  truths:
    - "Running `python -m kb.scripts.detect_article_lang` populates `lang` column for all rows where lang IS NULL in both articles and rss_articles"
    - "Stdout shows coverage report `{zh-CN: N, en: M, unknown: K}` for each table"
    - "Re-running the script issues 0 UPDATEs (incremental, idempotent)"
    - "Rows with `LENGTH(body) < 200` get lang='unknown'"
    - "Script depends on kb-1-01 (config) and kb-1-02 (migration + lang_detect helper) — runs migration first if columns missing"
  artifacts:
    - path: "kb/scripts/detect_article_lang.py"
      provides: "CLI driver for DATA-02 + DATA-03 — populates lang column"
      contains: "WHERE lang IS NULL"
  key_links:
    - from: "kb/scripts/detect_article_lang.py"
      to: "kb.data.lang_detect.detect_lang"
      via: "from kb.data.lang_detect import detect_lang"
      pattern: "from kb\\.data\\.lang_detect import"
    - from: "kb/scripts/detect_article_lang.py"
      to: "kb.scripts.migrate_lang_column.migrate_lang_column"
      via: "ensures column exists before UPDATE"
      pattern: "migrate_lang_column"
---

<objective>
Build the CLI driver that walks `articles` + `rss_articles`, applies `detect_lang()` to body text, and UPDATEs `lang` column where currently NULL. This is the consumer of plan kb-1-02's two outputs (migration + detector library).

Purpose: DATA-02 requires the populated lang column for downstream filtering (DATA-04 list_articles lang filter, I18N-04 list page filter, I18N-05 article-detail content lang badge). DATA-03 requires it be incremental + idempotent so daily cron in kb-4 can re-invoke safely.

Output: `kb/scripts/detect_article_lang.py` CLI driver + unit tests against an in-memory SQLite fixture.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-01-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-02-SUMMARY.md
@kb/data/lang_detect.py
@kb/scripts/migrate_lang_column.py
@kb/config.py
@CLAUDE.md

<interfaces>
Already-built imports this script consumes:

From `kb.data.lang_detect` (created in kb-1-02):

```python
from typing import Literal
LangCode = Literal["zh-CN", "en", "unknown"]
def detect_lang(text: str) -> LangCode: ...
def chinese_char_ratio(text: str) -> float: ...
```

From `kb.scripts.migrate_lang_column` (created in kb-1-02):

```python
def migrate_lang_column(conn: sqlite3.Connection) -> dict[str, str]: ...
```

From `kb.config` (created in kb-1-01):

```python
KB_DB_PATH: Path  # default: ~/.hermes/data/kol_scan.db
```

Schema (verified live in data/kol_scan.db):
- `articles` table: columns include `id INTEGER PRIMARY KEY`, `body TEXT`, `lang TEXT` (added by migration)
- `rss_articles` table: columns include `id INTEGER PRIMARY KEY`, `body TEXT`, `lang TEXT` (added by migration)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write kb/scripts/detect_article_lang.py with table-walking driver + idempotency + tests</name>
  <read_first>
    - kb/data/lang_detect.py (consumes detect_lang())
    - kb/scripts/migrate_lang_column.py (calls migrate_lang_column() to ensure schema before UPDATE)
    - kb/config.py (reads KB_DB_PATH)
    - .planning/REQUIREMENTS-KB-v2.md DATA-02 + DATA-03 (idempotency requirement)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Lang detection algorithm (DATA-02)"
  </read_first>
  <files>kb/scripts/detect_article_lang.py, tests/unit/kb/test_detect_article_lang.py</files>
  <behavior>
    - Test 1: Given a fresh in-memory SQLite with `articles` table containing 3 rows (1 Chinese body 300 chars, 1 English body 300 chars, 1 short body 50 chars) and migration applied, running `detect_for_table(conn, 'articles')` updates rows to `zh-CN`, `en`, `unknown` respectively.
    - Test 2: Re-running `detect_for_table` after Test 1 issues 0 UPDATEs (verified by `conn.total_changes` delta == 0). This is the idempotency proof.
    - Test 3: With BOTH `articles` and `rss_articles` tables populated, `main()` invocation prints a coverage report containing the strings `articles:` and `rss_articles:`, plus per-lang counts. Capture stdout via `capsys`.
    - Test 4: When the migration has NOT been run yet (no `lang` column), the driver detects this and runs `migrate_lang_column` first, THEN proceeds to populate. Verified by checking that after invocation, `PRAGMA table_info(articles)` shows `lang` AND rows have non-NULL lang.
    - Test 5: NULL or empty body in a row results in `lang='unknown'` (defensive — `detect_lang('')` returns 'unknown', not error).
  </behavior>
  <action>
    Create `kb/scripts/detect_article_lang.py` with this exact structure:

    ```python
    """DATA-02 + DATA-03: Walk articles + rss_articles, populate `lang` column.

    Idempotent: only updates rows where `lang IS NULL`. Safe to re-invoke daily
    via cron (DATA-03).

    Auto-runs migration if `lang` column is missing (allows fresh DB usage).

    Algorithm: kb.data.lang_detect.detect_lang(body) -> 'zh-CN' | 'en' | 'unknown'
        - Chinese char ratio > 30% AND len(body) >= 200 -> 'zh-CN'
        - Chinese char ratio <= 30% AND len(body) >= 200 -> 'en'
        - len(body) < 200 -> 'unknown' (insufficient sample)
    """
    from __future__ import annotations

    import sqlite3
    import sys
    from collections import Counter
    from pathlib import Path

    from kb import config
    from kb.data.lang_detect import detect_lang
    from kb.scripts.migrate_lang_column import migrate_lang_column

    _TABLES: tuple[str, ...] = ("articles", "rss_articles")


    def _ensure_lang_column(conn: sqlite3.Connection) -> None:
        """Run migration if either table is missing the lang column."""
        for table in _TABLES:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if cols and "lang" not in cols:
                migrate_lang_column(conn)
                return
            if not cols:
                # Table doesn't exist; migrate_lang_column handles missing tables
                migrate_lang_column(conn)
                return


    def detect_for_table(conn: sqlite3.Connection, table: str) -> Counter[str]:
        """Update lang for rows where lang IS NULL. Returns Counter of new assignments.

        Skips tables that don't exist (returns empty Counter).
        """
        result: Counter[str] = Counter()
        # Check table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return result

        rows = conn.execute(
            f"SELECT id, body FROM {table} WHERE lang IS NULL"
        ).fetchall()
        for row_id, body in rows:
            lang = detect_lang(body or "")
            conn.execute(f"UPDATE {table} SET lang = ? WHERE id = ?", (lang, row_id))
            result[lang] += 1
        conn.commit()
        return result


    def coverage_for_table(conn: sqlite3.Connection, table: str) -> Counter[str]:
        """Return lang distribution across all rows (NULL counted as 'NULL')."""
        result: Counter[str] = Counter()
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return result
        for (lang,) in conn.execute(f"SELECT lang FROM {table}"):
            result[lang or "NULL"] += 1
        return result


    def main() -> int:
        db_path: Path = config.KB_DB_PATH
        if not db_path.exists():
            print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
            return 1
        with sqlite3.connect(db_path) as conn:
            _ensure_lang_column(conn)
            for table in _TABLES:
                updated = detect_for_table(conn, table)
                coverage = coverage_for_table(conn, table)
                print(f"{table}: updated={dict(updated)}, total_coverage={dict(coverage)}")
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Then write `tests/unit/kb/test_detect_article_lang.py` exercising the 5 behaviors. For all tests, use `sqlite3.connect(":memory:")` and CREATE TABLE statements that match the production schema (id INTEGER PRIMARY KEY, body TEXT, plus any other columns needed). Use `monkeypatch.setattr` on `kb.config.KB_DB_PATH` for test 3 + 4 if invoking `main()`.

    Per CLAUDE.md: print() OK in CLI scripts. detect_for_table is a library function — no print, returns Counter.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_detect_article_lang.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `kb/scripts/detect_article_lang.py` exists; `python -c "from kb.scripts.detect_article_lang import detect_for_table, main; print('OK')"` exits 0
    - `pytest tests/unit/kb/test_detect_article_lang.py -v` exits 0 with 5 tests passing
    - File contains exact strings: `WHERE lang IS NULL`, `UPDATE`, `from kb.data.lang_detect import detect_lang`, `from kb.scripts.migrate_lang_column import migrate_lang_column`
    - File contains the table tuple `("articles", "rss_articles")`
    - Idempotency proof in test output: test 2 must assert `conn.total_changes` delta is 0 on second run
    - Coverage report format matches: stdout contains `articles:` and `rss_articles:` substrings
  </acceptance_criteria>
  <done>Detect script complete with idempotency + auto-migration; 5 tests pass.</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/kb/test_detect_article_lang.py -v` exits 0 (5 tests)
- Script can be invoked as `python -m kb.scripts.detect_article_lang`
- Idempotency confirmed: second invocation produces zero UPDATEs
</verification>

<success_criteria>
- DATA-02 driver complete: walks both tables, populates lang column based on Chinese char ratio
- DATA-03 satisfied: incremental + idempotent (WHERE lang IS NULL filter)
- Auto-migration: script self-heals if column was never added
- 5 unit tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-05-SUMMARY.md` documenting:
- Test pass count
- Idempotency proof from test output
- Coverage report sample (from a real test fixture)
</output>
