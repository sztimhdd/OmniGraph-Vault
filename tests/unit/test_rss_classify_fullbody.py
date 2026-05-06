"""Tests RCL-01, RCL-02, RCL-03 from Phase 20 REQUIREMENTS.md.

Verifies the contract that Plan 20-01 must deliver:
  RCL-01: rss_classify.run reads article body and passes it to _call_fullbody_llm
  RCL-02: single _call_fullbody_llm call per article (not one per topic);
          FULLBODY_THROTTLE_SECONDS constant exists and equals 4.5
  RCL-03: OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP env gate is respected by the
          full-body path (call count reflects the cap)

Currently RED because enrichment/rss_classify.py uses _call_deepseek per-topic
loop, NOT _call_fullbody_llm. Plans 20-01 will turn these GREEN.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from enrichment.rss_schema import _ensure_rss_columns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_rss_db(path: Path) -> None:
    """Create minimal rss_articles + rss_classifications schema at path."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            xml_url TEXT NOT NULL UNIQUE,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS rss_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            summary TEXT,
            fetched_at TEXT DEFAULT (datetime('now','localtime')),
            enriched INTEGER DEFAULT 0,
            content_length INTEGER
        );
        CREATE TABLE IF NOT EXISTS rss_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            depth_score INTEGER,
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT,
            classified_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(article_id, topic)
        );
        INSERT INTO rss_feeds (name, xml_url) VALUES ('TestFeed', 'https://test.example/rss');
        """
    )
    _ensure_rss_columns(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Test 1: RCL-01 — run() passes full body content to _call_fullbody_llm
# ---------------------------------------------------------------------------

def test_classify_reads_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RCL-01: rss_classify.run must pass body column to _call_fullbody_llm.

    Currently RED: the module uses _call_deepseek (per-topic, no body column).
    Plan 20-01 wires _call_fullbody_llm which receives the full body.
    """
    db_path = tmp_path / "kol_scan.db"
    _create_rss_db(db_path)

    body_content = "Test body content " * 100  # ~1700 chars

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary, body) "
        "VALUES (1, 'Test Article', 'https://example.com/a1', 'short summary', ?)",
        (body_content,),
    )
    conn.commit()
    conn.close()

    call_count = 0
    called_with_body: list[str] = []

    def mock_call_fullbody_llm(prompt: str) -> dict:
        nonlocal call_count
        call_count += 1
        called_with_body.append(prompt)
        return {"depth": 2, "topics": ["Agent"], "rationale": "test rationale"}

    monkeypatch.setattr("batch_classify_kol._build_fullbody_prompt", lambda title, body, topic_filter=None: f"MOCK_PROMPT:{body[:30]}")
    monkeypatch.setattr("batch_classify_kol._call_fullbody_llm", mock_call_fullbody_llm)
    monkeypatch.setattr("enrichment.rss_classify.get_deepseek_api_key", lambda: "dummy-key")
    # Block the legacy _call_deepseek path to prevent network calls.
    # After Plan 20-01, _call_deepseek will no longer be called at all;
    # the call will route to _call_fullbody_llm instead.
    def _assert_no_deepseek(prompt, api_key):
        raise AssertionError(
            "_call_deepseek must not be called after Plan 20-01; "
            "rss_classify must use _call_fullbody_llm instead"
        )
    monkeypatch.setattr("enrichment.rss_classify._call_deepseek", _assert_no_deepseek)
    monkeypatch.setattr("enrichment.rss_classify.time.sleep", lambda _: None)

    from enrichment import rss_classify
    rss_classify.run(
        topics=("Agent",),
        article_id=1,
        max_articles=None,
        dry_run=False,
        db_path=db_path,
    )

    # RCL-01: _call_fullbody_llm called exactly once for the article (NOT once per topic)
    assert call_count == 1, (
        f"Expected _call_fullbody_llm called 1 time, got {call_count}. "
        "Plan 20-01 must replace per-topic _call_deepseek loop with single _call_fullbody_llm."
    )

    # RCL-01: body column written to rss_articles.depth and topics
    conn2 = sqlite3.connect(str(db_path))
    row = conn2.execute(
        "SELECT depth, topics, body_scraped_at FROM rss_articles WHERE id=1"
    ).fetchone()
    conn2.close()

    assert row[0] == 2, f"Expected rss_articles.depth=2, got {row[0]}"
    topics_list = json.loads(row[1])
    assert topics_list == ["Agent"], f"Expected topics=[\"Agent\"], got {topics_list}"
    assert row[2] is not None, "Expected body_scraped_at NOT NULL after classify run"


# ---------------------------------------------------------------------------
# Test 2: RCL-02 — single call for multi-topic; FULLBODY_THROTTLE_SECONDS=4.5
# ---------------------------------------------------------------------------

def test_single_call_multi_topic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RCL-02: one _call_fullbody_llm call per article regardless of topic count.

    Also asserts FULLBODY_THROTTLE_SECONDS constant exists at 4.5.
    Currently RED because:
      - Module still uses _call_deepseek per-topic (3 calls for 3 topics)
      - FULLBODY_THROTTLE_SECONDS constant does not exist yet (AttributeError)
    Plan 20-01 ships both changes.
    """
    db_path = tmp_path / "kol_scan.db"
    _create_rss_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary, body) "
        "VALUES (1, 'Multi-Topic Article', 'https://example.com/multi', 'summary', ?)",
        ("Some body content " * 50,),
    )
    conn.commit()
    conn.close()

    call_count = 0

    def mock_call_fullbody_llm(prompt: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"depth": 3, "topics": ["Agent", "LLM", "RAG"], "rationale": "deep"}

    monkeypatch.setattr("batch_classify_kol._build_fullbody_prompt", lambda title, body, topic_filter=None: "MOCK")
    monkeypatch.setattr("batch_classify_kol._call_fullbody_llm", mock_call_fullbody_llm)
    monkeypatch.setattr("enrichment.rss_classify.get_deepseek_api_key", lambda: "dummy-key")
    # Block legacy path to prevent network calls.
    monkeypatch.setattr(
        "enrichment.rss_classify._call_deepseek",
        lambda prompt, api_key: None,  # no-op; call_count stays 0 -> assert fires
    )
    monkeypatch.setattr("enrichment.rss_classify.time.sleep", lambda _: None)

    from enrichment import rss_classify
    rss_classify.run(
        topics=("Agent", "LLM", "RAG"),
        article_id=1,
        max_articles=None,
        dry_run=False,
        db_path=db_path,
    )

    # RCL-02: single call for 3 topics (not 3 separate calls)
    assert call_count == 1, (
        f"Expected 1 _call_fullbody_llm call for 3 topics, got {call_count}. "
        "Plan 20-01: replace per-topic loop with single full-body call."
    )

    # RCL-02: FULLBODY_THROTTLE_SECONDS constant must exist and be 4.5
    assert hasattr(rss_classify, "FULLBODY_THROTTLE_SECONDS"), (
        "FULLBODY_THROTTLE_SECONDS not found in enrichment.rss_classify. "
        "Plan 20-01 D-20.03: define FULLBODY_THROTTLE_SECONDS = 4.5."
    )
    assert rss_classify.FULLBODY_THROTTLE_SECONDS == 4.5, (
        f"Expected FULLBODY_THROTTLE_SECONDS=4.5, got {rss_classify.FULLBODY_THROTTLE_SECONDS}. "
        "D-20.03: 60s / 15 RPM = 4.0s + 12.5% safety = 4.5s."
    )


# ---------------------------------------------------------------------------
# Test 3: RCL-03 — OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP gates full-body path
# ---------------------------------------------------------------------------

def test_daily_cap_gates_article(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RCL-03: daily cap env var limits how many articles get classified.

    Seeds 10 articles with body populated. Sets cap=3. Expects exactly 3
    articles classified and 7 left with depth IS NULL.

    Currently partially RED: the env cap exists in the module, but the
    call-count assertion to _call_fullbody_llm will fail until Plan 20-01
    replaces _call_deepseek with _call_fullbody_llm.
    """
    db_path = tmp_path / "kol_scan.db"
    _create_rss_db(db_path)

    conn = sqlite3.connect(str(db_path))
    for i in range(10):
        conn.execute(
            "INSERT INTO rss_articles (feed_id, title, url, summary, body) "
            "VALUES (1, ?, ?, 'summary', ?)",
            (f"Article {i}", f"https://example.com/article-{i}", f"Body content for article {i} " * 30),
        )
    conn.commit()
    conn.close()

    monkeypatch.setenv("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "3")

    call_count = 0

    def mock_call_fullbody_llm(prompt: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"depth": 2, "topics": ["Agent"], "rationale": "capped"}

    monkeypatch.setattr("batch_classify_kol._build_fullbody_prompt", lambda title, body, topic_filter=None: "MOCK")
    monkeypatch.setattr("batch_classify_kol._call_fullbody_llm", mock_call_fullbody_llm)
    monkeypatch.setattr("enrichment.rss_classify.get_deepseek_api_key", lambda: "dummy-key")
    # Block legacy path to prevent network calls.
    monkeypatch.setattr(
        "enrichment.rss_classify._call_deepseek",
        lambda prompt, api_key: None,  # no-op so cap test gets clean 0-classify result
    )
    monkeypatch.setattr("enrichment.rss_classify.time.sleep", lambda _: None)

    from enrichment import rss_classify
    rss_classify.run(
        topics=("Agent",),
        article_id=None,
        max_articles=None,
        dry_run=False,
        db_path=db_path,
    )

    conn2 = sqlite3.connect(str(db_path))
    null_depth_count = conn2.execute(
        "SELECT COUNT(*) FROM rss_articles WHERE depth IS NULL"
    ).fetchone()[0]
    classified_count = conn2.execute(
        "SELECT COUNT(*) FROM rss_articles WHERE depth IS NOT NULL"
    ).fetchone()[0]
    conn2.close()

    # Cap=3: only 3 articles classified
    assert classified_count == 3, (
        f"Expected 3 articles classified (cap=3), got {classified_count}. "
        "RCL-03: OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP must gate the full-body path."
    )
    assert null_depth_count == 7, (
        f"Expected 7 articles with depth IS NULL, got {null_depth_count}."
    )

    # RCL-03 + RCL-02: _call_fullbody_llm called exactly 3 times (one per article, cap=3)
    assert call_count == 3, (
        f"Expected _call_fullbody_llm called 3 times (cap=3), got {call_count}. "
        "Plan 20-01 must wire _call_fullbody_llm (single call per article)."
    )
