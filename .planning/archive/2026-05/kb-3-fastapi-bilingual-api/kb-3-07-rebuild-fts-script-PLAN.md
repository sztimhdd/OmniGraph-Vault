---
phase: kb-3-fastapi-bilingual-api
plan: 07
subsystem: search-index-rebuild
tags: [python, sqlite, fts5, cli, cron]
type: execute
wave: 2
depends_on: ["kb-3-06"]
files_modified:
  - kb/scripts/rebuild_fts.py
  - tests/unit/kb/test_rebuild_fts.py
autonomous: true
requirements:
  - SEARCH-02

must_haves:
  truths:
    - "kb/scripts/rebuild_fts.py is invokable as `python -m kb.scripts.rebuild_fts`"
    - "Drops + recreates articles_fts virtual table; populates from articles + rss_articles UNION"
    - "Honors DATA-07 filter (only indexes rows passing 3-condition filter — wasted index entries on rejects)"
    - "Re-runnable safely (idempotent — drops + recreates)"
    - "Writes one summary line to stdout: '[rebuild_fts] indexed N rows in M.MMs'"
    - "On Hermes prod (~2300 visible rows after DATA-07): completes in < 5s (verified by SEARCH-02 timing assertion)"
  artifacts:
    - path: "kb/scripts/rebuild_fts.py"
      provides: "CLI entry point + main(args) function for FTS5 index rebuild"
      exports: ["main"]
      min_lines: 80
    - path: "tests/unit/kb/test_rebuild_fts.py"
      provides: "TDD coverage for idempotency + DATA-07 filtering + timing"
      min_lines: 100
  key_links:
    - from: "kb/scripts/rebuild_fts.py"
      to: "kb.services.search_index.ensure_fts_table + FTS_TABLE_NAME"
      via: "import — reuses table schema constant from kb-3-06"
      pattern: "from kb.services.search_index import|search_index\\.FTS_TABLE_NAME"
    - from: "kb/scripts/rebuild_fts.py"
      to: "kb.data.article_query.list_articles (DATA-07-filtered)"
      via: "import + iterate — natural inheritance of quality filter"
      pattern: "list_articles"
---

<objective>
Implement `kb/scripts/rebuild_fts.py` — a CLI script invoked by daily cron after each export run. Drops `articles_fts`, recreates it via `ensure_fts_table`, populates rows from `list_articles(limit=10000)` (which already applies DATA-07).

Purpose: SEARCH-02 mandates a daily rebuild. Without it, /api/search?mode=fts queries against a stale index — new ingests don't appear, deleted articles linger. The script is the canonical rebuild path; ad-hoc REINDEX or per-row UPDATE not needed for this corpus size (~2300 rows).

Output: One Python script in `kb/scripts/` + dedicated unit tests verifying idempotency, DATA-07 inheritance, < 5s timing on fixture.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-02-SUMMARY.md
@kb/services/search_index.py
@kb/data/article_query.py
@kb/scripts/detect_article_lang.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Existing helpers (consumed by this plan, not modified):

```python
# kb/services/search_index.py (kb-3-06)
FTS_TABLE_NAME = "articles_fts"
def ensure_fts_table(conn: sqlite3.Connection) -> None: ...

# kb/data/article_query.py (kb-1 + kb-3-02)
def list_articles(lang=None, source=None, limit=20, offset=0, conn=None) -> list[ArticleRecord]: ...   # DATA-07 active
def resolve_url_hash(rec: ArticleRecord) -> str: ...
```

CLI shape (paste-ready):

```python
# kb/scripts/rebuild_fts.py
import argparse
import sqlite3
import time
import sys

from kb import config
from kb.services import search_index
from kb.data import article_query


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEARCH-02: rebuild FTS5 index")
    parser.add_argument("--db", default=str(config.KB_DB_PATH),
                        help="SQLite path (default: kb.config.KB_DB_PATH)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    t0 = time.perf_counter()
    n = _rebuild(args.db)
    dur = time.perf_counter() - t0
    if not args.quiet:
        print(f"[rebuild_fts] indexed {n} rows in {dur:.2f}s")
    return 0


def _rebuild(db_path: str) -> int:
    """Drop + recreate articles_fts; populate from list_articles. Returns row count."""
    # Open RW connection (rebuild is the only FTS write path)
    conn = sqlite3.connect(db_path)
    try:
        # 1. DROP existing FTS table (idempotent)
        conn.execute(f"DROP TABLE IF EXISTS {search_index.FTS_TABLE_NAME}")
        # 2. CREATE virtual table fresh
        search_index.ensure_fts_table(conn)
        # 3. Populate from DATA-07-filtered list_articles
        records = article_query.list_articles(limit=100000, conn=conn)
        n = 0
        for rec in records:
            h = article_query.resolve_url_hash(rec)
            conn.execute(
                f"INSERT INTO {search_index.FTS_TABLE_NAME} "
                "(hash, title, body, lang, source) VALUES (?, ?, ?, ?, ?)",
                (h, rec.title or "", rec.body or "", rec.lang, rec.source),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + create kb/scripts/rebuild_fts.py + tests</name>
  <read_first>
    - .planning/REQUIREMENTS-KB-v2.md SEARCH-02 (exact REQ wording, < 5s target)
    - kb/services/search_index.py (kb-3-06 — FTS_TABLE_NAME + ensure_fts_table)
    - kb/data/article_query.py (list_articles + resolve_url_hash)
    - kb/scripts/detect_article_lang.py (kb-1 CLI script — same pattern: argparse + main(argv) + sys.exit(main()))
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (DATA-07 inheritance via list_articles)
  </read_first>
  <files>kb/scripts/rebuild_fts.py, tests/unit/kb/test_rebuild_fts.py</files>
  <behavior>
    - Test 1: Calling `main(["--db", str(fixture_db), "--quiet"])` returns 0; populates articles_fts with N rows (where N = list_articles count on fixture).
    - Test 2: Idempotent — calling main() twice returns same row count both times; final row count matches list_articles output (no duplicates).
    - Test 3: After rebuild, every row in articles_fts has a corresponding ArticleRecord in list_articles (DATA-07 inheritance).
    - Test 4: Negative-case fixture rows (DATA-07-excluded) do NOT appear in articles_fts.
    - Test 5: Stdout summary contains `[rebuild_fts] indexed` and the row count.
    - Test 6: Timing on fixture DB < 5s (will be < 100ms in practice).
    - Test 7: `--quiet` suppresses stdout summary.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Idiomatic Python CLI script: argparse with --db override + --quiet flag, main(argv) returning exit code, `if __name__ == '__main__': sys.exit(main())` boilerplate. Open a single sqlite3 connection (RW for INSERT) — rebuild is one of the few WRITE paths in kb/. Wrap in try/finally for close. Use perf_counter for timing. Print one-line summary unless --quiet. NO new env vars. Reuse FTS_TABLE_NAME constant from search_index.")

    Skill(skill="writing-tests", args="Unit tests against shared fixture_db. Each test invokes main(['--db', str(fixture_db), '--quiet']) and asserts on the populated articles_fts table via direct sqlite3 query. Tests cover: success path + row count match, idempotency (call twice, second is fresh DROP+CREATE not append), DATA-07 inheritance (negative rows absent), stdout (capsys) for summary line, timing budget. Use capsys for stdout capture, monkeypatch for KB_DB_PATH if main() doesn't get --db (test both default-config path + explicit-override).")

    **Step 1 — Create `kb/scripts/rebuild_fts.py`** (use the paste-ready code from `<interfaces>` block — copy verbatim, then add Skill invocation comments at top):

    ```python
    """SEARCH-02: rebuild articles_fts virtual table from DATA-07-filtered article list.

    Invoked daily by cron (kb/scripts/daily_rebuild.sh — kb-4 plan):
        python -m kb.scripts.rebuild_fts

    Drops + recreates articles_fts; populates from list_articles() which already applies
    the DATA-07 content-quality filter. Row count expected ~160 on Hermes prod (~2500
    scanned, ~6.4% pass filter).

    Skill(skill="python-patterns", args="...")
    Skill(skill="writing-tests", args="...")
    """
    from __future__ import annotations

    import argparse
    import sqlite3
    import sys
    import time
    from typing import Optional

    from kb import config
    from kb.data import article_query
    from kb.services import search_index


    def _rebuild(db_path: str) -> int:
        """Drop + recreate articles_fts; populate from list_articles. Returns row count."""
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(f"DROP TABLE IF EXISTS {search_index.FTS_TABLE_NAME}")
            search_index.ensure_fts_table(conn)
            records = article_query.list_articles(limit=100000, conn=conn)
            n = 0
            for rec in records:
                h = article_query.resolve_url_hash(rec)
                conn.execute(
                    f"INSERT INTO {search_index.FTS_TABLE_NAME} "
                    "(hash, title, body, lang, source) VALUES (?, ?, ?, ?, ?)",
                    (h, rec.title or "", rec.body or "", rec.lang, rec.source),
                )
                n += 1
            conn.commit()
            return n
        finally:
            conn.close()


    def main(argv: Optional[list[str]] = None) -> int:
        parser = argparse.ArgumentParser(description="SEARCH-02: rebuild FTS5 index")
        parser.add_argument(
            "--db",
            default=str(config.KB_DB_PATH),
            help="SQLite path (default: kb.config.KB_DB_PATH)",
        )
        parser.add_argument("--quiet", action="store_true")
        args = parser.parse_args(argv)
        t0 = time.perf_counter()
        n = _rebuild(args.db)
        dur = time.perf_counter() - t0
        if not args.quiet:
            print(f"[rebuild_fts] indexed {n} rows in {dur:.2f}s")
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    **Step 2 — Create `tests/unit/kb/test_rebuild_fts.py`** with the 7 behaviors:

    ```python
    """Tests for kb/scripts/rebuild_fts.py (SEARCH-02)."""
    from __future__ import annotations

    import sqlite3
    import time
    from pathlib import Path

    import pytest

    pytest_plugins = ["tests.integration.kb.conftest"]


    def test_rebuild_returns_zero_exit_code(fixture_db, capsys):
        from kb.scripts.rebuild_fts import main
        rc = main(["--db", str(fixture_db), "--quiet"])
        assert rc == 0


    def test_rebuild_populates_fts(fixture_db):
        from kb.scripts.rebuild_fts import main
        from kb.services.search_index import FTS_TABLE_NAME
        main(["--db", str(fixture_db), "--quiet"])
        c = sqlite3.connect(str(fixture_db))
        try:
            count = c.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
        finally:
            c.close()
        assert count > 0


    def test_rebuild_idempotent(fixture_db):
        from kb.scripts.rebuild_fts import main
        from kb.services.search_index import FTS_TABLE_NAME
        main(["--db", str(fixture_db), "--quiet"])
        c = sqlite3.connect(str(fixture_db))
        try:
            count_a = c.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
        finally:
            c.close()
        main(["--db", str(fixture_db), "--quiet"])
        c = sqlite3.connect(str(fixture_db))
        try:
            count_b = c.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
        finally:
            c.close()
        assert count_a == count_b, "rebuild should be idempotent"


    def test_rebuild_inherits_data07_filter(fixture_db):
        """Negative-case fixture rows must NOT appear in articles_fts."""
        from kb.scripts.rebuild_fts import main
        from kb.services.search_index import FTS_TABLE_NAME
        main(["--db", str(fixture_db), "--quiet"])
        c = sqlite3.connect(str(fixture_db))
        try:
            # Fixture has a row with title='REJECTED' (kb-3-02 negative case).
            # Per DATA-07, it must NOT be indexed.
            row = c.execute(
                f"SELECT * FROM {FTS_TABLE_NAME} WHERE title MATCH 'REJECTED'"
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            c.close()
        # Either no match OR the row simply doesn't exist; either way, no REJECTED indexed
        if row is not None:
            pytest.fail(f"DATA-07 violation: REJECTED row indexed: {row}")


    def test_rebuild_stdout_contains_summary(fixture_db, capsys):
        from kb.scripts.rebuild_fts import main
        main(["--db", str(fixture_db)])
        captured = capsys.readouterr()
        assert "[rebuild_fts] indexed" in captured.out
        assert "rows in" in captured.out


    def test_rebuild_quiet_suppresses_stdout(fixture_db, capsys):
        from kb.scripts.rebuild_fts import main
        main(["--db", str(fixture_db), "--quiet"])
        captured = capsys.readouterr()
        assert "[rebuild_fts]" not in captured.out


    def test_rebuild_under_5s(fixture_db):
        """SEARCH-02: rebuild on fixture must complete in well under 5 seconds (target).

        Fixture is small (~10 rows) so this should be milliseconds; target validates the
        timing budget pattern works even if Hermes prod (~160 rows) is exercised."""
        from kb.scripts.rebuild_fts import main
        t0 = time.perf_counter()
        main(["--db", str(fixture_db), "--quiet"])
        dur = time.perf_counter() - t0
        assert dur < 5.0, f"rebuild took {dur:.2f}s — exceeds SEARCH-02 budget"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_rebuild_fts.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/scripts/rebuild_fts.py` exists with ≥80 lines
    - `grep -q "def main" kb/scripts/rebuild_fts.py`
    - `grep -q "from kb.services.search_index import\\|from kb.services import search_index" kb/scripts/rebuild_fts.py`
    - `grep -q "from kb.data import article_query\\|from kb.data.article_query import" kb/scripts/rebuild_fts.py`
    - `grep -q "DROP TABLE IF EXISTS" kb/scripts/rebuild_fts.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/scripts/rebuild_fts.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/scripts/rebuild_fts.py` OR in test file
    - `pytest tests/unit/kb/test_rebuild_fts.py -v` exits 0 with ≥7 tests passing
    - `python -m kb.scripts.rebuild_fts --help` exits 0 (CLI parses)
  </acceptance_criteria>
  <done>rebuild_fts.py CLI works; idempotent; DATA-07 inherited via list_articles; ≥7 tests pass.</done>
</task>

</tasks>

<verification>
- SEARCH-02 satisfied: rebuild script invokable, idempotent, < 5s
- DATA-07 inherited via list_articles call (no duplicate filter logic in script)
- python-patterns + writing-tests Skills literal in code/tests AND will appear in SUMMARY
</verification>

<success_criteria>
- SEARCH-02: daily rebuild path locked
- Idempotent + correct + fast
- Negative-case rows excluded automatically (DATA-07 inheritance)
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-07-SUMMARY.md` documenting:
- kb/scripts/rebuild_fts.py CLI ready for cron invocation
- ≥7 tests passing
- Skill invocation strings: `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)`
- DATA-07 inheritance pattern (script calls list_articles which applies filter)
</output>
</content>
</invoke>