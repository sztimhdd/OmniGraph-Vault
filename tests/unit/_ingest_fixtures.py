"""Behavior-anchor harness fixtures for ingest_from_db orchestration tests.

See CLAUDE.md HIGHEST PRIORITY PRINCIPLE #7. Any contract-shape change to
batch_ingest_from_spider.ingest_from_db requires updating both this module
(if a new column or SQL touched) AND test_ingest_from_db_orchestration.py.

Fixture drift = silent contract-change failure (2026-05-15 lesson #2).

Public API (all snake_case, type-annotated):
    in_memory_db()         -> sqlite3.Connection seeded w/ production schema
    mock_rag()             -> MagicMock with async ainsert/finalize/adelete
    patch_layer_funcs(...) -> applies the full mock stack; returns handles dict
    sample_kol_row(...)    -> 8-tuple matching candidate-row outer-loop unpack
    sample_rss_row(...)    -> 8-tuple matching candidate-row outer-loop unpack
    seed_kol_article(...)  -> INSERT helper for articles row
    seed_rss_article(...)  -> INSERT helper for rss_articles row

Note: leading underscore on the module basename prevents pytest from
auto-collecting this file as tests; the file is NOT a conftest.py so its
exports are NOT auto-injected into other test modules.
"""
from __future__ import annotations

import logging
import os

# Phase 5 cross-coupling defence — must run BEFORE any lib.* import chain
# pulls in lib.llm_deepseek (which raises at import if DEEPSEEK_API_KEY unset).
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import sqlite3
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock


__all__ = [
    "in_memory_db",
    "mock_rag",
    "patch_layer_funcs",
    "sample_kol_row",
    "sample_rss_row",
    "seed_kol_article",
    "seed_rss_article",
]


_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema fixture
# ---------------------------------------------------------------------------


# The ingestions CREATE TABLE clause is BYTE-IDENTICAL to
# batch_ingest_from_spider.py L1585-L1600 — see CLAUDE.md PRINCIPLE #7
# (fixture drift = silent contract-change failure).
_INGESTIONS_DDL = """
CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'wechat'
        CHECK (source IN ('wechat', 'rss')),
    status TEXT NOT NULL CHECK (status IN (
        'ok', 'failed', 'skipped', 'skipped_ingested',
        'dry_run', 'skipped_graded'
    )),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    skip_reason_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (article_id, source)
)
"""


_OTHER_TABLES_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    title TEXT,
    url TEXT,
    digest TEXT,
    body TEXT,
    image_count INTEGER DEFAULT 0,
    layer1_verdict TEXT,
    layer1_reason TEXT,
    layer1_at TEXT,
    layer1_prompt_version TEXT,
    layer2_verdict TEXT,
    layer2_reason TEXT,
    layer2_at TEXT,
    layer2_prompt_version TEXT
);
CREATE TABLE IF NOT EXISTS rss_feeds (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rss_articles (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER NOT NULL,
    title TEXT,
    url TEXT,
    summary TEXT,
    body TEXT,
    image_count INTEGER DEFAULT 0,
    layer1_verdict TEXT,
    layer1_reason TEXT,
    layer1_at TEXT,
    layer1_prompt_version TEXT,
    layer2_verdict TEXT,
    layer2_reason TEXT,
    layer2_at TEXT,
    layer2_prompt_version TEXT
);
CREATE TABLE IF NOT EXISTS classifications (
    article_id INTEGER,
    topic TEXT,
    depth_score INTEGER,
    depth INTEGER,
    topics TEXT,
    rationale TEXT,
    relevant INTEGER,
    UNIQUE (article_id, topic)
);
INSERT INTO accounts(id, name) VALUES (1, 'kol-acc-A');
INSERT INTO rss_feeds(id, name) VALUES (1, 'rss-feed-A');
"""


def in_memory_db() -> sqlite3.Connection:
    """Open an in-memory SQLite connection seeded with the production schema.

    Includes the ingestions table verbatim from batch_ingest_from_spider.py
    L1585-L1600 (CHECK source IN ('wechat','rss'), UNIQUE(article_id,source),
    skip_reason_version INTEGER NOT NULL DEFAULT 0). Also seeds one KOL
    account + one RSS feed so the candidate SELECT's INNER JOINs resolve.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(_INGESTIONS_DDL + ";\n" + _OTHER_TABLES_DDL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Rag mock
# ---------------------------------------------------------------------------


def mock_rag() -> MagicMock:
    """Return a MagicMock LightRAG instance with async ainsert / finalize /
    adelete_by_doc_id. Use this as the ``rag`` argument to patch_layer_funcs
    when you need to assert on rag.finalize_storages.call_count."""
    rag = MagicMock()
    rag.ainsert = AsyncMock(return_value=None)
    rag.finalize_storages = AsyncMock(return_value=None)
    rag.adelete_by_doc_id = AsyncMock(return_value=None)
    return rag


# ---------------------------------------------------------------------------
# Mock-stack helper
# ---------------------------------------------------------------------------


def patch_layer_funcs(
    monkeypatch,
    *,
    layer1_results: list | None = None,
    layer2_results: list | None = None,
    scrape_result: Any = None,
    ingest_outcome: tuple[bool, float, bool] = (True, 100.0, True),
    rag: MagicMock | None = None,
) -> dict[str, Any]:
    """Apply the full downstream mock stack and return installed handles.

    Patches (all via monkeypatch so pytest auto-undoes after test):
        * batch_ingest_from_spider.layer1_pre_filter      → AsyncMock(layer1_results)
        * batch_ingest_from_spider.layer2_full_body_score → AsyncMock(layer2_results)
        * batch_ingest_from_spider.persist_layer1_verdicts → no-op MagicMock
        * batch_ingest_from_spider.persist_layer2_verdicts → no-op MagicMock
        * lib.scraper.scrape_url                          → AsyncMock(scrape_result)
        * batch_ingest_from_spider._drain_pending_vision_tasks → AsyncMock
        * batch_ingest_from_spider._load_hermes_env       → no-op
        * batch_ingest_from_spider.get_deepseek_api_key   → returns "dummy"
        * batch_ingest_from_spider.has_stage              → returns False
        * batch_ingest_from_spider._persist_scraped_body  → echoes scraped.markdown
        * batch_ingest_from_spider.ingest_article         → AsyncMock(ingest_outcome)
        * sys.modules["ingest_wechat"].get_rag            → AsyncMock(rag)
        * logging.basicConfig                             → no-op (caplog defence)
        * batch_ingest_from_spider.SLEEP_BETWEEN_ARTICLES → 0

    Returns a dict whose keys are: layer1, layer2, persist_layer1,
    persist_layer2, scrape, drain_vision, ingest_article, rag — for
    .assert_called* introspection in tests.
    """
    import batch_ingest_from_spider as bi
    import lib.scraper

    layer1_mock = AsyncMock(return_value=list(layer1_results or []))
    monkeypatch.setattr(bi, "layer1_pre_filter", layer1_mock)

    layer2_mock = AsyncMock(return_value=list(layer2_results or []))
    monkeypatch.setattr(bi, "layer2_full_body_score", layer2_mock)

    p1 = MagicMock(return_value=None)
    p2 = MagicMock(return_value=None)
    monkeypatch.setattr(bi, "persist_layer1_verdicts", p1)
    monkeypatch.setattr(bi, "persist_layer2_verdicts", p2)

    scrape_mock = AsyncMock(return_value=scrape_result)
    monkeypatch.setattr(lib.scraper, "scrape_url", scrape_mock)

    drain_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(bi, "_drain_pending_vision_tasks", drain_mock)

    monkeypatch.setattr(bi, "_load_hermes_env", lambda: None)
    monkeypatch.setattr(bi, "get_deepseek_api_key", lambda: "dummy")

    monkeypatch.setattr(bi, "has_stage", lambda h, s: False)

    # _persist_scraped_body returns the scraped markdown verbatim so the
    # in-loop ``body = persisted`` assignment continues with a non-empty body
    # (matches production line 2014-2018 happy path).
    def _fake_persist(conn, art_id, source, scraped):
        if scraped is None:
            return None
        return scraped.markdown or scraped.content_html or None

    monkeypatch.setattr(bi, "_persist_scraped_body", _fake_persist)

    ingest_mock = AsyncMock(return_value=tuple(ingest_outcome))
    monkeypatch.setattr(bi, "ingest_article", ingest_mock)

    fake_rag = rag if rag is not None else mock_rag()
    fake_iw = MagicMock()
    fake_iw.get_rag = AsyncMock(return_value=fake_rag)
    monkeypatch.setitem(sys.modules, "ingest_wechat", fake_iw)

    # caplog defence: production calls logging.basicConfig(force=True) right
    # after LightRAG init, which removes pytest's caplog handler. Patch to
    # no-op so caplog.records stays intact.
    monkeypatch.setattr(logging, "basicConfig", lambda *a, **kw: None)

    monkeypatch.setattr(bi, "SLEEP_BETWEEN_ARTICLES", 0)

    return {
        "layer1": layer1_mock,
        "layer2": layer2_mock,
        "persist_layer1": p1,
        "persist_layer2": p2,
        "scrape": scrape_mock,
        "drain_vision": drain_mock,
        "ingest_article": ingest_mock,
        "rag": fake_rag,
    }


# ---------------------------------------------------------------------------
# Row factories — must match the 8-col outer-loop unpack at L1899:
# (id, source, title, url, account_or_feed_name, body, summary, image_count)
# ---------------------------------------------------------------------------


def sample_kol_row(
    id: int = 1,
    image_count_row: int = 0,
    body: str | None = None,
    title: str = "KOL Article",
    url: str | None = None,
) -> tuple:
    """8-tuple matching the v3.5 ir-4 candidate-row contract for KOL."""
    return (
        id,
        "wechat",
        title,
        url or f"https://mp.weixin.qq.com/s/test-{id}",
        "kol-acc-A",
        body,
        f"digest-{id}",
        image_count_row,
    )


def sample_rss_row(
    id: int = 1,
    image_count_row: int = 0,
    body: str | None = None,
    title: str = "RSS Article",
    url: str | None = None,
) -> tuple:
    """8-tuple matching the v3.5 ir-4 candidate-row contract for RSS."""
    return (
        id,
        "rss",
        title,
        url or f"https://example.com/rss/test-{id}",
        "rss-feed-A",
        body,
        f"summary-{id}",
        image_count_row,
    )


# ---------------------------------------------------------------------------
# DB-row seeders (used when tests want production SELECT to pick rows up)
# ---------------------------------------------------------------------------


def seed_kol_article(
    conn: sqlite3.Connection,
    *,
    art_id: int,
    body: str | None = None,
    image_count: int = 0,
    layer1_verdict: str | None = None,
    layer1_prompt_version: str | None = None,
    title: str | None = None,
    url: str | None = None,
) -> None:
    """Insert one KOL article row keyed for accounts(id=1)."""
    conn.execute(
        "INSERT INTO articles("
        "id, account_id, title, url, digest, body, image_count, "
        "layer1_verdict, layer1_prompt_version) "
        "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
        (
            art_id,
            title or f"KOL article {art_id}",
            url or f"https://mp.weixin.qq.com/s/test-{art_id}",
            f"digest-{art_id}",
            body,
            image_count,
            layer1_verdict,
            layer1_prompt_version,
        ),
    )
    conn.commit()


def seed_rss_article(
    conn: sqlite3.Connection,
    *,
    art_id: int,
    body: str | None = None,
    image_count: int = 0,
    layer1_verdict: str | None = None,
    layer1_prompt_version: str | None = None,
    title: str | None = None,
    url: str | None = None,
) -> None:
    """Insert one RSS article row keyed for rss_feeds(id=1)."""
    conn.execute(
        "INSERT INTO rss_articles("
        "id, feed_id, title, url, summary, body, image_count, "
        "layer1_verdict, layer1_prompt_version) "
        "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
        (
            art_id,
            title or f"RSS article {art_id}",
            url or f"https://example.com/rss/test-{art_id}",
            f"summary-{art_id}",
            body,
            image_count,
            layer1_verdict,
            layer1_prompt_version,
        ),
    )
    conn.commit()
