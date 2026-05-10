"""
Unit tests for batch_classify_rss_layer2.py.

Quick 260510-p1s — 7 mock-only tests.
All tests monkeypatch layer2_full_body_score in the script's namespace
to avoid any real LLM/network calls. DeepSeek is corp-blocked on this
Windows dev box; tests MUST NOT hit the network.
"""
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# DB fixture helper
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER, title TEXT, url TEXT, author TEXT, summary TEXT,
    content_hash TEXT, published_at TEXT, fetched_at TEXT,
    enriched INTEGER, content_length INTEGER, body TEXT,
    body_scraped_at TEXT, depth INTEGER, topics TEXT,
    classify_rationale TEXT,
    layer1_verdict TEXT, layer1_reason TEXT, layer1_at TEXT,
    layer1_prompt_version TEXT,
    layer2_verdict TEXT, layer2_reason TEXT, layer2_at TEXT,
    layer2_prompt_version TEXT
)
"""


def _seed_db(path: Path, rows: list[dict]) -> None:
    """Create rss_articles table in a fresh SQLite DB and insert rows."""
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_TABLE)
    for row in rows:
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        conn.execute(
            f"INSERT INTO rss_articles ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )
    conn.commit()
    conn.close()


def _make_row(
    id: int,
    layer1_verdict: str = "candidate",
    layer2_verdict: str | None = None,
    body: str = "article body text",
    url: str = "",
    title: str = "Test Article",
) -> dict:
    return {
        "id": id,
        "title": title,
        "url": url or f"https://example.com/article/{id}",
        "body": body,
        "layer1_verdict": layer1_verdict,
        "layer2_verdict": layer2_verdict,
    }


# ---------------------------------------------------------------------------
# Import module under test (done lazily inside tests so monkeypatching works)
# ---------------------------------------------------------------------------

def _run(db_path: Path, max_articles: int = 500, dry_run: bool = False) -> int:
    """Import and call the script's run() entrypoint."""
    import batch_classify_rss_layer2 as m
    return m.run(db_path, max_articles, dry_run)


# ---------------------------------------------------------------------------
# Test 1 — selects only candidates with NULL layer2_verdict
# ---------------------------------------------------------------------------

def test_selects_only_candidates_with_null_layer2(tmp_path, monkeypatch):
    """Rows with layer1='reject' or layer2!= NULL must be skipped."""
    db = tmp_path / "test.db"
    _seed_db(db, [
        _make_row(1, layer1_verdict="candidate", layer2_verdict=None),   # SELECTED
        _make_row(2, layer1_verdict="reject",    layer2_verdict=None),   # SKIPPED
        _make_row(3, layer1_verdict="candidate", layer2_verdict="ok"),   # SKIPPED
    ])

    called_ids: list[int] = []

    async def fake_layer2(articles):
        called_ids.extend(a.id for a in articles)
        from lib.article_filter import FilterResult
        return [FilterResult(verdict="ok", reason="test", prompt_version="v0")] * len(articles)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(db)

    assert rc == 0
    assert called_ids == [1], f"Expected only id=1, got {called_ids}"


# ---------------------------------------------------------------------------
# Test 2 — --max-articles limit is respected
# ---------------------------------------------------------------------------

def test_max_articles_limit_respected(tmp_path, monkeypatch):
    """Only max_articles rows should be passed to layer2."""
    db = tmp_path / "test.db"
    _seed_db(db, [_make_row(i) for i in range(1, 7)])  # 6 candidates

    total_articles: list[int] = []

    async def fake_layer2(articles):
        total_articles.extend(a.id for a in articles)
        from lib.article_filter import FilterResult
        return [FilterResult(verdict="ok", reason="test", prompt_version="v0")] * len(articles)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(db, max_articles=3)

    assert rc == 0
    assert len(total_articles) == 3, f"Expected 3 total articles, got {len(total_articles)}"


# ---------------------------------------------------------------------------
# Test 3 — --dry-run skips LLM call AND DB UPDATE
# ---------------------------------------------------------------------------

def test_dry_run_skips_call_and_update(tmp_path, monkeypatch):
    """dry_run=True must skip LLM and leave layer2_verdict = NULL."""
    db = tmp_path / "test.db"
    _seed_db(db, [_make_row(10)])

    async def should_not_be_called(articles):
        raise AssertionError("layer2_full_body_score must NOT be called in dry-run mode")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", should_not_be_called)

    rc = _run(db, dry_run=True)

    assert rc == 0
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM rss_articles WHERE id = 10"
    ).fetchone()
    conn.close()
    assert row[0] is None, f"layer2_verdict should be NULL, got {row[0]!r}"
    assert row[1] is None, f"layer2_at should be NULL, got {row[1]!r}"


# ---------------------------------------------------------------------------
# Test 4 — verdict='ok' is persisted correctly
# ---------------------------------------------------------------------------

def test_verdict_ok_persisted(tmp_path, monkeypatch):
    """ok verdict + reason + prompt_version must be written to DB."""
    db = tmp_path / "test.db"
    _seed_db(db, [_make_row(42)])

    async def fake_layer2(articles):
        from lib.article_filter import FilterResult
        return [FilterResult(verdict="ok", reason="deep-tech", prompt_version="layer2_v0_test")]

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(db)

    assert rc == 0
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT layer2_verdict, layer2_reason, layer2_at, layer2_prompt_version "
        "FROM rss_articles WHERE id = 42"
    ).fetchone()
    conn.close()
    assert row[0] == "ok", f"Expected 'ok', got {row[0]!r}"
    assert row[1] == "deep-tech", f"Expected 'deep-tech', got {row[1]!r}"
    assert row[2] is not None, "layer2_at must be set"
    assert row[3] == "layer2_v0_test", f"Expected 'layer2_v0_test', got {row[3]!r}"


# ---------------------------------------------------------------------------
# Test 5 — verdict='reject' is persisted correctly
# ---------------------------------------------------------------------------

def test_verdict_reject_persisted(tmp_path, monkeypatch):
    """reject verdict must be written to DB with correct reason."""
    db = tmp_path / "test.db"
    _seed_db(db, [_make_row(55)])

    async def fake_layer2(articles):
        from lib.article_filter import FilterResult
        return [FilterResult(verdict="reject", reason="off-topic", prompt_version="layer2_v0_test")]

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(db)

    assert rc == 0
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT layer2_verdict, layer2_reason FROM rss_articles WHERE id = 55"
    ).fetchone()
    conn.close()
    assert row[0] == "reject", f"Expected 'reject', got {row[0]!r}"
    assert row[1] == "off-topic", f"Expected 'off-topic', got {row[1]!r}"


# ---------------------------------------------------------------------------
# Test 6 — all-NULL batch leaves rows untouched; subsequent batches proceed
# ---------------------------------------------------------------------------

def test_exception_yields_null_persistence_and_continues(tmp_path, monkeypatch):
    """First chunk all-NULL: rows stay NULL. Second chunk 'ok': rows updated."""
    db = tmp_path / "test.db"
    # 10 rows forces 2 chunks of 5 (LAYER2_BATCH_SIZE=5)
    _seed_db(db, [_make_row(i) for i in range(1, 11)])

    call_count = [0]

    async def fake_layer2(articles):
        from lib.article_filter import FilterResult
        call_count[0] += 1
        if call_count[0] == 1:
            # First chunk: all-null (simulates LLM timeout/error)
            return [FilterResult(verdict=None, reason="timeout", prompt_version="layer2_v0_test")] * len(articles)
        else:
            # Second chunk: all ok
            return [FilterResult(verdict="ok", reason="relevant", prompt_version="layer2_v0_test")] * len(articles)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(db)

    assert rc == 0
    assert call_count[0] == 2, f"Expected 2 batch calls, got {call_count[0]}"

    conn = sqlite3.connect(str(db))
    # First 5 rows (ids 1-5) should still have NULL layer2_verdict
    first_chunk = conn.execute(
        "SELECT id, layer2_verdict FROM rss_articles WHERE id <= 5 ORDER BY id"
    ).fetchall()
    # Second 5 rows (ids 6-10) should have 'ok'
    second_chunk = conn.execute(
        "SELECT id, layer2_verdict FROM rss_articles WHERE id >= 6 ORDER BY id"
    ).fetchall()
    conn.close()

    for row_id, verdict in first_chunk:
        assert verdict is None, f"id={row_id}: expected NULL (all-null batch), got {verdict!r}"
    for row_id, verdict in second_chunk:
        assert verdict == "ok", f"id={row_id}: expected 'ok', got {verdict!r}"


# ---------------------------------------------------------------------------
# Test 7 — --db-path override is honored
# ---------------------------------------------------------------------------

def test_custom_db_path_honored(tmp_path, monkeypatch):
    """Script must read/write the custom DB, not the default one."""
    custom_db = tmp_path / "custom.db"
    _seed_db(custom_db, [_make_row(99)])

    async def fake_layer2(articles):
        from lib.article_filter import FilterResult
        return [FilterResult(verdict="ok", reason="custom-path-test", prompt_version="v0")]

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr("batch_classify_rss_layer2.layer2_full_body_score", fake_layer2)

    rc = _run(custom_db)

    assert rc == 0
    conn = sqlite3.connect(str(custom_db))
    row = conn.execute(
        "SELECT layer2_verdict FROM rss_articles WHERE id = 99"
    ).fetchone()
    conn.close()
    assert row[0] == "ok", f"Expected 'ok' in custom DB, got {row[0]!r}"
