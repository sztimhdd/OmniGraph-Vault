"""Tests for kb/scripts/rebuild_fts.py (SEARCH-02).

Coverage matrix (kb-3-07 PLAN Task 1 behaviors):
    1. main(['--db', fixture, '--quiet']) returns 0 (zero exit code)
    2. populates articles_fts with N rows where N == len(list_articles)
    3. idempotent — second invocation produces same row count
    4. DATA-07 inheritance — list_articles negative-case rows absent from index
    5. stdout summary contains '[rebuild_fts] indexed' + 'rows in'
    6. --quiet suppresses stdout
    7. timing budget < 5s on fixture

Skill(skill="writing-tests", args="Unit tests against shared fixture_db (tests/integration/kb/conftest.py via pytest_plugins). Each test invokes main(['--db', str(fixture_db), '--quiet']) and asserts on the populated articles_fts table via direct sqlite3 query. Tests cover: success path + row count match, idempotency (call twice, second is fresh DROP+CREATE not append), DATA-07 inheritance (negative rows absent), stdout (capsys) for summary line, timing budget. Real SQLite throughout — no mocks for the data layer.")
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

pytest_plugins = ["tests.integration.kb.conftest"]


def test_rebuild_returns_zero_exit_code(fixture_db: Path) -> None:
    from kb.scripts.rebuild_fts import main

    rc = main(["--db", str(fixture_db), "--quiet"])
    assert rc == 0


def test_rebuild_populates_fts(fixture_db: Path) -> None:
    """SEARCH-02: rebuild populates articles_fts with rows from list_articles."""
    from kb.scripts.rebuild_fts import main
    from kb.services.search_index import FTS_TABLE_NAME

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
    finally:
        conn.close()
    # fixture_db has 5 KOL positive + 3 RSS positive = 8 DATA-07-passing rows.
    assert count == 8, f"expected 8 indexed rows, got {count}"


def test_rebuild_row_count_matches_list_articles(fixture_db: Path) -> None:
    """Row count in articles_fts must equal list_articles output length."""
    from kb.data.article_query import list_articles
    from kb.scripts.rebuild_fts import main
    from kb.services.search_index import FTS_TABLE_NAME

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
        records = list_articles(limit=100000, conn=conn)
    finally:
        conn.close()
    assert count == len(records)


def test_rebuild_idempotent(fixture_db: Path) -> None:
    """Running rebuild twice must produce identical row count (DROP+CREATE, not append)."""
    from kb.scripts.rebuild_fts import main
    from kb.services.search_index import FTS_TABLE_NAME

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        count_a = conn.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
    finally:
        conn.close()

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        count_b = conn.execute(f"SELECT COUNT(*) FROM {FTS_TABLE_NAME}").fetchone()[0]
    finally:
        conn.close()
    assert count_a == count_b, "rebuild should be idempotent"


def test_rebuild_inherits_data07_filter(fixture_db: Path) -> None:
    """DATA-07-failing fixture rows (REJECTED, LAYER2 REJECTED, NULL BODY RSS,
    LAYER1 REJECT RSS) must NOT appear in articles_fts."""
    from kb.scripts.rebuild_fts import main
    from kb.services.search_index import FTS_TABLE_NAME

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        # Direct title equality (not MATCH) — bypass tokenizer ambiguity.
        rejected_titles = (
            "REJECTED EMPTY BODY",
            "LAYER2 REJECTED",
            "NULL BODY RSS",
            "LAYER1 REJECT RSS",
        )
        for title in rejected_titles:
            row = conn.execute(
                f"SELECT title FROM {FTS_TABLE_NAME} WHERE title = ?", (title,)
            ).fetchone()
            assert row is None, f"DATA-07 violation: {title!r} indexed"
    finally:
        conn.close()


def test_rebuild_stdout_contains_summary(fixture_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from kb.scripts.rebuild_fts import main

    main(["--db", str(fixture_db)])
    captured = capsys.readouterr()
    assert "[rebuild_fts] indexed" in captured.out
    assert "rows in" in captured.out


def test_rebuild_quiet_suppresses_stdout(fixture_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from kb.scripts.rebuild_fts import main

    main(["--db", str(fixture_db), "--quiet"])
    captured = capsys.readouterr()
    assert "[rebuild_fts]" not in captured.out


def test_rebuild_under_5s(fixture_db: Path) -> None:
    """SEARCH-02 timing budget — fixture is tiny so this must be milliseconds."""
    from kb.scripts.rebuild_fts import main

    t0 = time.perf_counter()
    main(["--db", str(fixture_db), "--quiet"])
    dur = time.perf_counter() - t0
    assert dur < 5.0, f"rebuild took {dur:.2f}s — exceeds SEARCH-02 budget"


def test_rebuild_indexes_both_kol_and_rss(fixture_db: Path) -> None:
    """UNION of KOL + RSS sources — both must appear in articles_fts."""
    from kb.scripts.rebuild_fts import main
    from kb.services.search_index import FTS_TABLE_NAME

    main(["--db", str(fixture_db), "--quiet"])
    conn = sqlite3.connect(str(fixture_db))
    try:
        sources = {
            r[0]
            for r in conn.execute(f"SELECT DISTINCT source FROM {FTS_TABLE_NAME}")
        }
    finally:
        conn.close()
    assert sources == {"wechat", "rss"}, f"expected both sources, got {sources}"
