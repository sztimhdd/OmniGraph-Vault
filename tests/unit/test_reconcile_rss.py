"""Unit tests for reconcile_ingestions RSS scope extension (quick 260512-rrx).

Tests cover both WeChat and RSS sources to ensure:
1. WeChat rows are properly reconciled (existing functionality)
2. RSS rows are now included in reconciliation (new)
3. Per-source mystery counts are tracked
4. Output format supports both sources
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.reconcile_ingestions import (
    _compute_doc_id,
    _load_doc_status,
    _query_ok_rows,
    main,
)


@pytest.fixture
def tmp_db() -> Path:
    """Create a temporary SQLite database with required schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    try:
        # Create articles table (WeChat)
        conn.execute(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                digest TEXT
            )
            """
        )

        # Create rss_articles table (RSS)
        conn.execute(
            """
            CREATE TABLE rss_articles (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                summary TEXT,
                feed_id INTEGER
            )
            """
        )

        # Create ingestions table
        conn.execute(
            """
            CREATE TABLE ingestions (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """
        )

        conn.commit()
    finally:
        conn.close()

    yield db_path

    # Cleanup (ignore errors on Windows file locking)
    try:
        db_path.unlink()
    except PermissionError:
        pass


@pytest.fixture
def tmp_storage(tmp_path) -> Path:
    """Create a temporary storage directory with kv_store_doc_status.json fixture."""
    storage_dir = tmp_path / "lightrag_storage"
    storage_dir.mkdir()
    yield storage_dir


def _add_article(db_path: Path, art_id: int, url: str) -> None:
    """Helper: add WeChat article to DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("INSERT INTO articles (id, url) VALUES (?, ?)", (art_id, url))
        conn.commit()
    finally:
        conn.close()


def _add_rss_article(db_path: Path, art_id: int, url: str) -> None:
    """Helper: add RSS article to DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("INSERT INTO rss_articles (id, url) VALUES (?, ?)", (art_id, url))
        conn.commit()
    finally:
        conn.close()


def _add_ingestion(
    db_path: Path, art_id: int, source: str, status: str, date_str: str = "2026-05-12"
) -> None:
    """Helper: add ingestion record to DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ingestions (article_id, source, status, ingested_at) "
            "VALUES (?, ?, ?, ?)",
            (art_id, source, status, f"{date_str} 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def _set_doc_status(storage_dir: Path, doc_id: str, status: str) -> None:
    """Helper: set doc status in kv_store_doc_status.json fixture."""
    status_path = storage_dir / "kv_store_doc_status.json"
    status_map: dict[str, dict[str, Any]] = {}
    if status_path.exists():
        status_map = json.loads(status_path.read_text())
    status_map[doc_id] = {"status": status}
    status_path.write_text(json.dumps(status_map))


def test_compute_doc_id_wechat() -> None:
    """Test: WeChat doc_id uses MD5[:10] with wechat_ prefix."""
    url = "https://example.com/article/123"
    expected_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"wechat_{expected_hash}"

    doc_id = _compute_doc_id(url, source="wechat")
    assert doc_id == expected_doc_id


def test_compute_doc_id_rss() -> None:
    """Test: RSS doc_id uses MD5[:10] with rss_ prefix.

    Verified 2026-05-12 against prod kv_store_doc_status.json:
    seangoedecke article (id=60, url=https://seangoedecke.com/fast-llm-inference/)
    has doc_id ``rss_9f52f6cbef`` which equals ``f"rss_{md5(url)[:10]}"``.
    """
    url = "https://example.com/feed/item/456"
    expected_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"rss_{expected_hash}"

    doc_id = _compute_doc_id(url, source="rss")
    assert doc_id == expected_doc_id


def test_compute_doc_id_default() -> None:
    """Test: Default source is wechat."""
    url = "https://example.com/article/789"
    doc_id_default = _compute_doc_id(url)
    doc_id_explicit = _compute_doc_id(url, source="wechat")

    assert doc_id_default == doc_id_explicit


def test_compute_doc_id_rss_prod_regression() -> None:
    """Regression: pin formula to actual prod RSS doc_id from 2026-05-12.

    The seangoedecke "Fast LLM Inference" article is the historical first
    RSS source='ok' row. Its prod doc_id (verified via SSH on the live
    LightRAG kv_store_doc_status.json) is ``rss_9f52f6cbef``. If this
    test fails, the formula drifted and reconcile will silently report
    every RSS row as mystery.
    """
    url = "https://seangoedecke.com/fast-llm-inference/"
    assert _compute_doc_id(url, source="rss") == "rss_9f52f6cbef"


def test_query_ok_rows_wechat_only(tmp_db: Path) -> None:
    """Test 1: Query returns WeChat articles with source='wechat'."""
    _add_article(tmp_db, 1, "https://example.com/article/1")
    _add_ingestion(tmp_db, 1, "wechat", "ok")

    rows = _query_ok_rows(tmp_db, date(2026, 5, 12), date(2026, 5, 12))

    assert len(rows) == 1
    assert rows[0]["source"] == "wechat"
    assert rows[0]["url"] == "https://example.com/article/1"


def test_query_ok_rows_rss_only(tmp_db: Path) -> None:
    """Test 2: Query returns RSS articles with source='rss' (new coverage)."""
    _add_rss_article(tmp_db, 100, "https://feeds.example.com/item/100")
    _add_ingestion(tmp_db, 100, "rss", "ok")

    rows = _query_ok_rows(tmp_db, date(2026, 5, 12), date(2026, 5, 12))

    assert len(rows) == 1
    assert rows[0]["source"] == "rss"
    assert rows[0]["url"] == "https://feeds.example.com/item/100"


def test_query_ok_rows_mixed(tmp_db: Path) -> None:
    """Test 3: Query returns both WeChat and RSS rows."""
    _add_article(tmp_db, 1, "https://example.com/article/1")
    _add_rss_article(tmp_db, 100, "https://feeds.example.com/item/100")
    _add_ingestion(tmp_db, 1, "wechat", "ok")
    _add_ingestion(tmp_db, 100, "rss", "ok")

    rows = _query_ok_rows(tmp_db, date(2026, 5, 12), date(2026, 5, 12))

    assert len(rows) == 2
    sources = {row["source"] for row in rows}
    assert sources == {"wechat", "rss"}


def test_reconcile_wechat_mystery_zero(
    tmp_db: Path, tmp_storage: Path, capsys
) -> None:
    """Test 4: WeChat row with matched LightRAG status → mystery_count_wechat=0."""
    url = "https://example.com/article/1"
    _add_article(tmp_db, 1, url)
    _add_ingestion(tmp_db, 1, "wechat", "ok")

    doc_id = _compute_doc_id(url, source="wechat")
    _set_doc_status(tmp_storage, doc_id, "processed")

    exit_code = main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    assert "0 mystery" in captured.out
    assert "wechat: 0, rss: 0" in captured.out
    assert exit_code == 0


def test_reconcile_rss_mystery_zero(tmp_db: Path, tmp_storage: Path, capsys) -> None:
    """Test 5: RSS row with matched LightRAG status → mystery_count_rss=0 (new)."""
    url = "https://feeds.example.com/item/100"
    _add_rss_article(tmp_db, 100, url)
    _add_ingestion(tmp_db, 100, "rss", "ok")

    doc_id = _compute_doc_id(url, source="rss")
    _set_doc_status(tmp_storage, doc_id, "processed")

    exit_code = main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    assert "0 mystery" in captured.out
    assert "wechat: 0, rss: 0" in captured.out
    assert exit_code == 0


def test_reconcile_wechat_mystery_found(
    tmp_db: Path, tmp_storage: Path, capsys
) -> None:
    """Test 6: WeChat row with failed LightRAG status → mystery_count_wechat=1."""
    url = "https://example.com/article/1"
    _add_article(tmp_db, 1, url)
    _add_ingestion(tmp_db, 1, "wechat", "ok")

    doc_id = _compute_doc_id(url, source="wechat")
    _set_doc_status(tmp_storage, doc_id, "failed")

    exit_code = main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    assert "1 mystery" in captured.out
    assert "wechat: 1, rss: 0" in captured.out
    assert exit_code == 1


def test_reconcile_rss_mystery_found(tmp_db: Path, tmp_storage: Path, capsys) -> None:
    """Test 7: RSS row with failed LightRAG status → mystery_count_rss=1 (new)."""
    url = "https://feeds.example.com/item/100"
    _add_rss_article(tmp_db, 100, url)
    _add_ingestion(tmp_db, 100, "rss", "ok")

    doc_id = _compute_doc_id(url, source="rss")
    _set_doc_status(tmp_storage, doc_id, "failed")

    exit_code = main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    assert "1 mystery" in captured.out
    assert "wechat: 0, rss: 1" in captured.out
    assert exit_code == 1


def test_reconcile_mixed_mystery(tmp_db: Path, tmp_storage: Path, capsys) -> None:
    """Test 8: Mixed mystery (1 wechat + 1 rss) → both counts tracked."""
    wechat_url = "https://example.com/article/1"
    rss_url = "https://feeds.example.com/item/100"

    _add_article(tmp_db, 1, wechat_url)
    _add_rss_article(tmp_db, 100, rss_url)
    _add_ingestion(tmp_db, 1, "wechat", "ok")
    _add_ingestion(tmp_db, 100, "rss", "ok")

    wechat_doc_id = _compute_doc_id(wechat_url, source="wechat")
    rss_doc_id = _compute_doc_id(rss_url, source="rss")
    _set_doc_status(tmp_storage, wechat_doc_id, "failed")
    _set_doc_status(tmp_storage, rss_doc_id, "failed")

    exit_code = main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    assert "2 mystery" in captured.out
    assert "wechat: 1, rss: 1" in captured.out
    assert exit_code == 1


def test_reconcile_output_format(tmp_db: Path, tmp_storage: Path, capsys) -> None:
    """Test 9: Output format includes per-source breakdown."""
    url = "https://example.com/article/1"
    _add_article(tmp_db, 1, url)
    _add_ingestion(tmp_db, 1, "wechat", "ok")

    doc_id = _compute_doc_id(url, source="wechat")
    _set_doc_status(tmp_storage, doc_id, "processed")

    main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    # Verify format: date: N ok rows / N matched / N mystery (wechat: X, rss: Y)
    assert "2026-05-12:" in captured.out
    assert "1 ok rows" in captured.out
    assert "1 matched" in captured.out
    assert "0 mystery" in captured.out
    assert "(wechat: 0, rss: 0)" in captured.out


def test_reconcile_backward_compat(tmp_db: Path, tmp_storage: Path, capsys) -> None:
    """Test 10: Output is backward compatible (existing parsers still work)."""
    url = "https://example.com/article/1"
    _add_article(tmp_db, 1, url)
    _add_ingestion(tmp_db, 1, "wechat", "ok")

    doc_id = _compute_doc_id(url, source="wechat")
    _set_doc_status(tmp_storage, doc_id, "processed")

    main(
        [
            "--db-path",
            str(tmp_db),
            "--storage-dir",
            str(tmp_storage),
            "--date",
            "2026-05-12",
        ]
    )

    captured = capsys.readouterr()
    # Old parsers extract "X ok rows / Y matched / Z mystery" — should still work
    assert "1 ok rows / 1 matched / 0 mystery" in captured.out
    # New consumers can optionally parse the (wechat: ..., rss: ...) suffix
    assert "(wechat: 0, rss: 0)" in captured.out
