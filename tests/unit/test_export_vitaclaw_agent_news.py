"""Tests for the VitaClaw website Agent news exporter."""
from __future__ import annotations

import sqlite3

import pytest

from scripts.export_vitaclaw_agent_news import ExportError, build_export


def _init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
    )
    conn.execute(
        """CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            digest TEXT,
            update_time INTEGER,
            scanned_at TEXT,
            layer1_verdict TEXT,
            layer2_verdict TEXT,
            layer2_at TEXT,
            layer2_reason TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE classifications (
            article_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            depth_score INTEGER,
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        "CREATE TABLE rss_feeds (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
    )
    conn.execute(
        """CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            summary TEXT,
            published_at TEXT,
            fetched_at TEXT,
            topics TEXT,
            layer1_verdict TEXT,
            layer2_verdict TEXT,
            layer2_at TEXT,
            layer2_reason TEXT
        )"""
    )
    conn.execute("INSERT INTO accounts (id, name) VALUES (1, 'AI前线')")
    conn.execute("INSERT INTO rss_feeds (id, name) VALUES (1, 'OpenAI')")
    return conn


def _insert_kol(
    conn: sqlite3.Connection,
    article_id: int,
    *,
    verdict: str = "ok",
    url: str | None = None,
    digest: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO articles (
            id, account_id, title, url, digest, scanned_at, layer1_verdict,
            layer2_verdict, layer2_at, layer2_reason
        ) VALUES (?, 1, ?, ?, ?, ?, 'candidate', ?, ?, ?)""",
        (
            article_id,
            f"Agent 技术文章 {article_id}",
            url or f"https://example.com/posts/{article_id}",
            digest or "这是一段面向网站展示的中文摘要，说明 Agent 工程化与企业集成的关键价值。",
            "2026-05-09 08:00:00",
            verdict,
            f"2026-05-09T0{article_id}:00:00+00:00",
            "MCP与Agent工程实践",
        ),
    )
    conn.execute(
        """INSERT INTO classifications (
            article_id, topic, depth_score, relevant, excluded
        ) VALUES (?, 'agent', 2, 1, 0)""",
        (article_id,),
    )


def test_build_export_emits_exact_website_contract() -> None:
    conn = _init_db()
    for article_id in range(1, 6):
        _insert_kol(conn, article_id)
    _insert_kol(conn, 6, verdict="reject")
    _insert_kol(conn, 7, url="ftp://example.com/not-public")

    export = build_export(conn, generated_at="2026-05-09T12:00:00Z")

    assert export["contractVersion"] == 1
    assert export["generatedAt"] == "2026-05-09T12:00:00Z"
    assert len(export["items"]) == 5
    for item in export["items"]:
        assert item["originalTitle"]
        assert item["originalUrl"].startswith("https://")
        assert item["summaryZh"]
        assert item["tags"]
        assert item["sourceDomain"] == "example.com"
        assert item["layer"] == "layer2"
        assert item["curationStatus"] == "passed"


def test_build_export_requires_five_eligible_items() -> None:
    conn = _init_db()
    for article_id in range(1, 5):
        _insert_kol(conn, article_id)

    with pytest.raises(ExportError, match="expected 5 eligible items"):
        build_export(conn, generated_at="2026-05-09T12:00:00Z")
