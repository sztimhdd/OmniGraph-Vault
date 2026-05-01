"""Phase 10 plan 10-00: scrape-first classification tests.

Covers D-10.01 (scrape before classify), D-10.02 (full-body DeepSeek prompt +
new {depth, topics, rationale} schema), D-10.03 (rate-limit reuse), D-10.04
(strict persist-before-ingest ordering + no fail-open + idempotent schema
migration).

All tests mock external deps (requests.post, ingest_wechat.scrape_wechat_ua,
ingest_wechat.process_content, the Phase 9 ingest_article wrapper). No live
network, no LightRAG init, no real DeepSeek calls.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    """All tests run with DEEPSEEK_API_KEY=dummy to satisfy module-level checks."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


# ---------------------------------------------------------------------------
# Task 1 — D-10.02 / D-10.04 tests
# ---------------------------------------------------------------------------


def test_fullbody_prompt_includes_body_not_digest():
    """D-10.02: prompt uses full body, not [digest: ...]."""
    from batch_classify_kol import _build_fullbody_prompt

    body = "long text about GPT-5.5 benchmark showing substantive deep analysis"
    prompt = _build_fullbody_prompt(
        title="Some article", body=body, topic_filter=["AI agents"]
    )
    assert "long text about GPT-5.5" in prompt
    assert "[digest: N/A]" not in prompt
    assert "[digest:" not in prompt


def test_fullbody_prompt_schema_requires_topics_list():
    """D-10.02: prompt instructs model to return depth+topics+rationale JSON object."""
    from batch_classify_kol import _build_fullbody_prompt

    prompt = _build_fullbody_prompt(title="t", body="b", topic_filter=None)
    assert "topics" in prompt
    assert "depth" in prompt
    assert "rationale" in prompt
    # must say JSON object (not JSON array) so caller parses single dict
    assert "JSON object" in prompt or "JSON OBJECT" in prompt.upper()


def test_call_deepseek_returns_new_schema():
    """D-10.02: _call_deepseek_fullbody parses {depth, topics, rationale} dict."""
    from batch_classify_kol import _call_deepseek_fullbody

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"depth": 1, "topics": ["news"], "rationale": "shallow"}'
                }
            }
        ]
    }

    with patch("batch_classify_kol.requests.post", return_value=mock_response):
        result = _call_deepseek_fullbody("some prompt", "dummy-key")

    assert result == {"depth": 1, "topics": ["news"], "rationale": "shallow"}


def test_call_deepseek_fullbody_returns_none_on_error():
    """D-10.04: API failure → None (orchestrator must skip, no fail-open)."""
    from batch_classify_kol import _call_deepseek_fullbody

    with patch("batch_classify_kol.requests.post", side_effect=RuntimeError("boom")):
        result = _call_deepseek_fullbody("some prompt", "dummy-key")

    assert result is None


def test_schema_migration_idempotent(tmp_path):
    """D-10.04 / D-10.01: _ensure_fullbody_columns adds columns once, no crash on 2nd call."""
    from batch_ingest_from_spider import _ensure_fullbody_columns

    db_path = tmp_path / "test_schema.db"
    conn = sqlite3.connect(str(db_path))
    # Seed with the legacy classifications + articles schema (mirrors init_db).
    conn.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            title TEXT,
            url TEXT UNIQUE,
            digest TEXT
        );
        CREATE TABLE classifications (
            id INTEGER PRIMARY KEY,
            article_id INTEGER,
            topic TEXT,
            depth_score INTEGER,
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT
        );
        """
    )
    conn.commit()

    # First call: should add all four columns.
    _ensure_fullbody_columns(conn)
    cls_cols = {row[1] for row in conn.execute("PRAGMA table_info(classifications)")}
    art_cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    assert {"depth", "topics", "rationale"}.issubset(cls_cols)
    assert "body" in art_cols

    # Second call: must not crash (D-10.04 idempotency).
    _ensure_fullbody_columns(conn)  # no exception

    # Columns unchanged (no dupes — SQLite wouldn't allow that anyway, but sanity-check).
    cls_cols_after = {row[1] for row in conn.execute("PRAGMA table_info(classifications)")}
    assert cls_cols == cls_cols_after
    conn.close()


# ---------------------------------------------------------------------------
# Task 2 — D-10.01 / D-10.03 / D-10.04 flow tests
# ---------------------------------------------------------------------------


def _seed_db_with_article(tmp_path: Path, body: str | None = None) -> Path:
    """Create an in-file SQLite DB with one pending article. Returns DB path."""
    db_path = tmp_path / "kol_scan.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            digest TEXT
        );
        CREATE TABLE classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            topic TEXT NOT NULL,
            depth_score INTEGER,
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT,
            classified_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id, topic)
        );
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id)
        );
        """
    )
    conn.execute("INSERT INTO accounts (name) VALUES ('test_kol')")
    conn.execute(
        "INSERT INTO articles (account_id, title, url, digest) VALUES (?, ?, ?, ?)",
        (1, "GPT-5.5 benchmark", "https://mp.weixin.qq.com/s/test_article", "N/A"),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.mark.asyncio
async def test_scrape_on_demand_when_body_empty(tmp_path, monkeypatch):
    """D-10.01: articles.body empty → scrape_wechat_ua called → body persisted."""
    import batch_ingest_from_spider as bi
    import ingest_wechat

    db_path = _seed_db_with_article(tmp_path)
    conn = sqlite3.connect(str(db_path))
    bi._ensure_fullbody_columns(conn)

    # Mock scraper to return HTML.
    scrape_mock = AsyncMock(
        return_value={
            "title": "GPT-5.5 benchmark",
            "content_html": "<p>long gpt-5.5 body with deep analysis</p>",
            "img_urls": [],
            "url": "https://mp.weixin.qq.com/s/test_article",
            "publish_time": "2026-04-29",
            "method": "ua",
        }
    )
    monkeypatch.setattr(ingest_wechat, "scrape_wechat_ua", scrape_mock)
    monkeypatch.setattr(
        ingest_wechat,
        "process_content",
        lambda html: ("long gpt-5.5 body with deep analysis", []),
    )

    # Mock DeepSeek to return a valid classification.
    fake_cls = {"depth": 3, "topics": ["AI benchmark"], "rationale": "deep technical"}
    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek_fullbody", lambda prompt, key: fake_cls
    )

    result = await bi._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test_article",
        title="GPT-5.5 benchmark",
        body=None,
        api_key="dummy",
    )

    assert result == fake_cls
    scrape_mock.assert_awaited_once()

    # Body persisted to articles.body.
    row = conn.execute("SELECT body FROM articles WHERE id = 1").fetchone()
    assert row[0] == "long gpt-5.5 body with deep analysis"

    # classifications row has new columns populated.
    cls_row = conn.execute(
        "SELECT depth, topics, rationale FROM classifications WHERE article_id = 1"
    ).fetchone()
    assert cls_row[0] == 3
    assert json.loads(cls_row[1]) == ["AI benchmark"]
    assert cls_row[2] == "deep technical"

    conn.close()


@pytest.mark.asyncio
async def test_classifier_persistence_before_ingest_decision(tmp_path, monkeypatch):
    """D-10.04: classifications INSERT happens BEFORE the ingest decision is returned.

    Strategy: spy on call order. We capture a call-order list that the
    classifier-persist step appends to, and assert the classifier result is
    returned only after the INSERT.
    """
    import batch_ingest_from_spider as bi
    import ingest_wechat

    db_path = _seed_db_with_article(tmp_path)
    conn = sqlite3.connect(str(db_path))
    bi._ensure_fullbody_columns(conn)

    monkeypatch.setattr(
        ingest_wechat,
        "scrape_wechat_ua",
        AsyncMock(
            return_value={
                "title": "t",
                "content_html": "<p>body</p>",
                "img_urls": [],
                "url": "u",
                "publish_time": "",
                "method": "ua",
            }
        ),
    )
    monkeypatch.setattr(ingest_wechat, "process_content", lambda h: ("body", []))

    fake_cls = {"depth": 2, "topics": ["x"], "rationale": "r"}
    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek_fullbody", lambda prompt, key: fake_cls
    )

    result = await bi._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test_article",
        title="t",
        body=None,
        api_key="dummy",
    )

    assert result == fake_cls

    # At return time, the classifications row must already be in the DB
    # (proves persistence happened before _classify_full_body returned).
    cls_row = conn.execute(
        "SELECT depth FROM classifications WHERE article_id = 1"
    ).fetchone()
    assert cls_row is not None
    assert cls_row[0] == 2

    # And no ingestions row has been written yet — the caller owns that decision.
    ing_row = conn.execute(
        "SELECT * FROM ingestions WHERE article_id = 1"
    ).fetchone()
    assert ing_row is None

    conn.close()


@pytest.mark.asyncio
async def test_deepseek_failure_skips_ingest(tmp_path, monkeypatch):
    """D-10.04: DeepSeek returns None → _classify_full_body returns None, no row persisted."""
    import batch_ingest_from_spider as bi
    import ingest_wechat

    db_path = _seed_db_with_article(tmp_path)
    conn = sqlite3.connect(str(db_path))
    bi._ensure_fullbody_columns(conn)

    monkeypatch.setattr(
        ingest_wechat,
        "scrape_wechat_ua",
        AsyncMock(
            return_value={
                "title": "t",
                "content_html": "<p>body</p>",
                "img_urls": [],
                "url": "u",
                "publish_time": "",
                "method": "ua",
            }
        ),
    )
    monkeypatch.setattr(ingest_wechat, "process_content", lambda h: ("body", []))

    # DeepSeek returns None (API failure / parse failure).
    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek_fullbody", lambda prompt, key: None
    )

    result = await bi._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test_article",
        title="t",
        body=None,
        api_key="dummy",
    )

    assert result is None

    # No classifications row was written for this article — strict no fail-open.
    cls_row = conn.execute(
        "SELECT * FROM classifications WHERE article_id = 1"
    ).fetchone()
    assert cls_row is None

    # No ingestions row either.
    ing_row = conn.execute(
        "SELECT * FROM ingestions WHERE article_id = 1"
    ).fetchone()
    assert ing_row is None

    conn.close()


def test_rate_limit_constants_reused():
    """D-10.03: batch_ingest_from_spider imports existing constants, no new ones.

    Source-grep: module MUST import RATE_LIMIT_SLEEP_ACCOUNTS + RATE_LIMIT_COOLDOWN
    from spiders.wechat_spider AND must NOT introduce new rate-limit constants.
    """
    import re

    src_path = Path(__file__).parent.parent.parent / "batch_ingest_from_spider.py"
    src = src_path.read_text(encoding="utf-8")

    # Must import existing constants from the canonical source.
    assert "from spiders.wechat_spider import" in src
    assert "RATE_LIMIT_SLEEP_ACCOUNTS" in src
    assert "RATE_LIMIT_COOLDOWN" in src

    # Must NOT define new rate-limit constants for the scrape-on-demand path.
    # Regex allows pre-existing constants; forbids the specific names called out in D-10.03.
    forbidden = [
        r"^\s*SCRAPE_ON_DEMAND_SLEEP\s*=",
        r"^\s*PER_ARTICLE_DELAY\s*=",
        r"^\s*CLASSIFY_RATE_LIMIT\s*=",
        r"^\s*SCRAPE_FIRST_COOLDOWN\s*=",
    ]
    for pattern in forbidden:
        assert (
            re.search(pattern, src, re.MULTILINE) is None
        ), f"Forbidden new rate-limit constant found: {pattern}"
