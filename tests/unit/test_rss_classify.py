"""Unit tests for enrichment.rss_classify."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from enrichment import rss_classify
from enrichment.rss_schema import init_rss_schema


@pytest.fixture
def fresh_db():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        init_rss_schema(conn)
        conn.execute(
            "INSERT INTO rss_feeds (name, xml_url, active) VALUES (?, ?, 1)",
            ("Feed A", "https://a.example/rss"),
        )
        feed_id = conn.execute(
            "SELECT id FROM rss_feeds WHERE xml_url=?",
            ("https://a.example/rss",),
        ).fetchone()[0]
        conn.executemany(
            "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (?, ?, ?, ?)",
            [
                (feed_id, "EN Post 1", "https://a.example/p/1",
                 "A deliberately long English body about agent architecture and "
                 "reasoning loops so the classifier has enough context to work with."),
                (feed_id, "EN Post 2", "https://a.example/p/2",
                 "Another long body about retrieval and tools."),
            ],
        )
        conn.commit()
        conn.close()
        yield db


def _fake_result(depth: int = 2, topic: str = "Agent", relevant: int = 1,
                 excluded: int = 0, reason: str = "技术分析内容") -> dict:
    return {
        "topic": topic,
        "depth_score": depth,
        "relevant": relevant,
        "excluded": excluded,
        "reason": reason,
    }


def test_writes_classification_row_with_chinese_reason(fresh_db: Path) -> None:
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent", depth=2, reason="中文理由文本")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",),
            article_id=None,
            max_articles=1,
            dry_run=False,
            db_path=fresh_db,
        )
    assert stats["classified"] >= 1
    conn = sqlite3.connect(fresh_db)
    row = conn.execute(
        "SELECT topic, depth_score, reason FROM rss_classifications LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "Agent"
    assert 1 <= row[1] <= 3
    assert any("一" <= ch <= "鿿" for ch in row[2]), "reason must contain Chinese"


def test_reclassify_is_noop_via_unique_constraint(fresh_db: Path) -> None:
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(depth=2, topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        rss_classify.run(
            topics=("Agent",), article_id=1, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
        rss_classify.run(
            topics=("Agent",), article_id=1, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
    conn = sqlite3.connect(fresh_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM rss_classifications WHERE article_id=? AND topic=?",
        (1, "Agent"),
    ).fetchone()[0]
    conn.close()
    # UNIQUE(article_id, topic) + silent IntegrityError = still 1
    assert count == 1


def test_malformed_llm_response_is_skipped(fresh_db: Path) -> None:
    def boom(prompt, api_key):
        raise ValueError("malformed JSON")

    with patch("enrichment.rss_classify._call_deepseek", side_effect=boom), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=1, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
    assert stats["failed"] >= 1
    assert stats["classified"] == 0
    conn = sqlite3.connect(fresh_db)
    n = conn.execute("SELECT COUNT(*) FROM rss_classifications").fetchone()[0]
    conn.close()
    assert n == 0


def test_dry_run_does_not_write(fresh_db: Path) -> None:
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result()) as mock_llm, \
         patch("enrichment.rss_classify.get_deepseek_api_key") as mock_key, \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=1, max_articles=None,
            dry_run=True, db_path=fresh_db,
        )
    assert stats["dry_run_planned"] >= 1
    assert stats["classified"] == 0
    mock_llm.assert_not_called()
    # Dry-run must not even resolve the API key
    mock_key.assert_not_called()
    conn = sqlite3.connect(fresh_db)
    n = conn.execute("SELECT COUNT(*) FROM rss_classifications").fetchone()[0]
    conn.close()
    assert n == 0


def test_max_articles_limits_batch(fresh_db: Path) -> None:
    # Insert a 3rd article
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (1, ?, ?, ?)",
        ("EN Post 3", "https://a.example/p/3", "another long body about agents"),
    )
    conn.commit()
    conn.close()

    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=None, max_articles=2,
            dry_run=False, db_path=fresh_db,
        )
    # Exactly 2 articles × 1 topic = 2 classified
    assert stats["classified"] == 2


def test_uses_deepseek_endpoint_not_gemini() -> None:
    """Static check: no google-genai import paths in module."""
    src = Path("enrichment/rss_classify.py").read_text(encoding="utf-8")
    assert "api.deepseek.com" in src
    assert "google.genai" not in src
    assert "from google import genai" not in src
    assert "GEMINI_API_KEY" not in src
    # Key resolver imported from production batch_classify_kol
    assert "from batch_classify_kol import get_deepseek_api_key" in src


# ---------------------------------------------------------------------
# LQ7-01 — env cap OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP (default 500)
# Tests mirror test_max_articles_limits_batch shape: seed N articles,
# drive the cap via env var, assert stats["classified"] reflects the cap.
# ---------------------------------------------------------------------
def _seed_three_articles(fresh_db: Path) -> None:
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (1, ?, ?, ?)",
        ("EN Post 3", "https://a.example/p/3", "another long body about agents"),
    )
    conn.commit()
    conn.close()


def test_env_cap_default_500_when_no_cli_flag(
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """max_articles=None + no env var => fallback 500; all 3 seeded rows classify."""
    monkeypatch.delenv("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", raising=False)
    _seed_three_articles(fresh_db)
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=None, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
    # Default 500 >> 3 seeded rows => all 3 classified
    assert stats["classified"] == 3


def test_env_cap_override_applies(
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """max_articles=None + env=2 => cap is 2."""
    monkeypatch.setenv("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "2")
    _seed_three_articles(fresh_db)
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=None, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
    assert stats["classified"] == 2


def test_env_cap_parse_failure_falls_back_to_500(
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """max_articles=None + env='abc' => parse fails silently; fallback 500."""
    monkeypatch.setenv("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "abc")
    _seed_three_articles(fresh_db)
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        # Must NOT raise
        stats = rss_classify.run(
            topics=("Agent",), article_id=None, max_articles=None,
            dry_run=False, db_path=fresh_db,
        )
    # Fallback 500 >> 3 => all 3 classified
    assert stats["classified"] == 3


def test_cli_max_articles_wins_over_env(
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit --max-articles=1 beats env=2."""
    monkeypatch.setenv("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "2")
    _seed_three_articles(fresh_db)
    with patch("enrichment.rss_classify._call_deepseek",
               return_value=_fake_result(topic="Agent")), \
         patch("enrichment.rss_classify.get_deepseek_api_key", return_value="fake-key"), \
         patch("enrichment.rss_classify.time.sleep", return_value=None):
        stats = rss_classify.run(
            topics=("Agent",), article_id=None, max_articles=1,
            dry_run=False, db_path=fresh_db,
        )
    # CLI value 1 wins over env 2
    assert stats["classified"] == 1
