"""Shared pytest fixtures for jobs/ unit tests.

Reuses asyncio_mode=auto from the parent databricks-deploy/pytest.ini.
pytest-asyncio>=0.23.0 confirmed in databricks-deploy/requirements.txt.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make databricks-deploy/jobs importable for all tests in this package.
_JOBS_DIR = Path(__file__).resolve().parent.parent
_DEPLOY_DIR = _JOBS_DIR.parent
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))
if str(_JOBS_DIR) not in sys.path:
    sys.path.insert(0, str(_JOBS_DIR))

# ---------------------------------------------------------------------------
# Fixture DB helpers
# ---------------------------------------------------------------------------

_CREATE_ARTICLES_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    content_hash TEXT,
    title TEXT,
    body TEXT,
    lang TEXT,
    layer1_verdict TEXT,
    layer2_verdict TEXT
)
"""

_CREATE_RSS_ARTICLES_SQL = """
CREATE TABLE IF NOT EXISTS rss_articles (
    id INTEGER PRIMARY KEY,
    content_hash TEXT,
    title TEXT,
    body TEXT,
    lang TEXT,
    layer1_verdict TEXT,
    layer2_verdict TEXT
)
"""


def _make_fixture_db(db_path: Path) -> None:
    """Create a minimal kol_scan fixture DB matching production schema.

    Rows:
      articles:
        - hash 'aaaa' x 32 chars  candidate / None   -> should be included
        - hash 'bbbb' x 32 chars  candidate / ok     -> should be included
        - hash 'cccc' x 32 chars  reject / None      -> should be excluded
      rss_articles:
        - hash 'dddd' x 32 chars  candidate / None   -> should be included
        - hash 'eeee' x 32 chars  candidate / reject -> should be excluded (layer2=reject)
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_ARTICLES_SQL)
    conn.execute(_CREATE_RSS_ARTICLES_SQL)

    # Articles rows
    conn.execute(
        "INSERT INTO articles VALUES (1, ?, 'Article A', ?, 'zh', 'candidate', NULL)",
        ("a" * 32, "short article body approximately 100 chars long content here" + "x" * 50),
    )
    conn.execute(
        "INSERT INTO articles VALUES (2, ?, 'Article B', ?, 'en', 'candidate', 'ok')",
        ("b" * 32, "medium body " * 50),
    )
    conn.execute(
        "INSERT INTO articles VALUES (3, ?, 'Article C (reject)', ?, 'zh', 'reject', NULL)",
        ("c" * 32, "rejected article body"),
    )
    # rss_articles rows
    conn.execute(
        "INSERT INTO rss_articles VALUES (4, ?, 'RSS D', ?, 'en', 'candidate', NULL)",
        ("d" * 32, "rss article body " * 15),
    )
    conn.execute(
        "INSERT INTO rss_articles VALUES (5, ?, 'RSS E (layer2 reject)', ?, 'zh', 'candidate', 'reject')",
        ("e" * 32, "rss reject layer2 body"),
    )

    conn.commit()
    conn.close()


@pytest.fixture
def fixture_db_path(tmp_path: Path) -> str:
    """Return path to a temporary kol_scan_fixture.db with 5 rows."""
    db_path = tmp_path / "kol_scan_fixture.db"
    _make_fixture_db(db_path)
    return str(db_path)


@pytest.fixture
def tmp_working_dir(tmp_path: Path) -> Path:
    """Temporary directory that mirrors the Volume layout.

    Creates lightrag_storage/ and output/ subdirectories.
    """
    (tmp_path / "lightrag_storage").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Mock LightRAG rag object
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag() -> Any:
    """Mock LightRAG instance with async ainsert + doc_status.

    Default behaviour: ainsert returns 'track-123'; doc_status returns PROCESSED.
    Tests can override individual async return values as needed.
    """
    rag = MagicMock()

    # ainsert returns a track_id string
    rag.ainsert = AsyncMock(return_value="track-123")

    # doc_status.get_docs_by_ids returns a list with one PROCESSED record
    processed_record = MagicMock()
    processed_record.status = MagicMock()
    processed_record.status.value = "PROCESSED"
    rag.doc_status = MagicMock()
    rag.doc_status.get_docs_by_ids = AsyncMock(return_value=[processed_record])

    return rag


# ---------------------------------------------------------------------------
# Stratified sample fixture DB (50 rows across 5 body-length buckets)
# ---------------------------------------------------------------------------

@pytest.fixture
def stratified_db_path(tmp_path: Path) -> str:
    """Return path to a DB with 50 articles (10 per body-length bucket).

    Body lengths: 100 (x10), 500 (x10), 1000 (x10), 5000 (x10), 50000 (x10).
    All rows are candidates with no layer2 filter.
    """
    db_path = tmp_path / "stratified_fixture.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_ARTICLES_SQL)
    conn.execute(_CREATE_RSS_ARTICLES_SQL)

    body_lengths = [100, 500, 1000, 5000, 50000]
    row_id = 1
    for bucket_idx, body_len in enumerate(body_lengths):
        body = "x" * body_len
        for j in range(10):
            h = f"{bucket_idx:02d}{j:02d}" + "0" * 28  # 32-char hash
            conn.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?, 'en', 'candidate', NULL)",
                (row_id, h, f"Article {h[:8]}", body),
            )
            row_id += 1

    conn.commit()
    conn.close()
    return str(db_path)
