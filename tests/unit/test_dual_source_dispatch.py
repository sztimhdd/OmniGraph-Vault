"""Unit tests for v3.5 ir-4 W2 dispatch logic.

Pins three deliverables introduced by Wave 2 of the RSS integration:

1. ``_needs_scrape(source, body)`` module-level helper that decides whether
   the per-article scrape stage runs. KOL preserves pre-ir-4 semantics
   (skip when body present, regardless of length); RSS uses
   ``RSS_SCRAPE_THRESHOLD`` because rss_fetch sometimes only captured the
   feed's <description> excerpt (typically 50-80 chars — too short for
   Layer 2 + ainsert to extract anything meaningful).

2. ``_persist_scraped_body(conn, article_id, source, scrape)`` source
   dispatch via ``_BODY_TABLE_FOR``. Writes go to ``articles.body`` for
   source='wechat' and ``rss_articles.body`` for source='rss'. Unknown
   source is a soft-skip with a WARNING (refused write rather than
   defaulting to a guess that could corrupt the wrong table).

3. ingest_from_db scrape call drops the W1 ``site_hint='wechat'`` so
   ``lib.scraper.scrape_url`` auto-routes by URL. (Behavioral test for
   this lives in the helper test below — verifying no site_hint leaks to
   the call site is structural and covered by the integration smoke).

These tests are mock-only — no LLM, no scraper, no LightRAG. They focus on
the pure-Python dispatch decisions.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _deepseek_dummy(monkeypatch):
    """Phase 5 cross-coupling — see CLAUDE.md."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


# ---------------------------------------------------------------------------
# _needs_scrape(source, body) helper
# ---------------------------------------------------------------------------


def test_needs_scrape_kol_no_body_triggers_scrape():
    from batch_ingest_from_spider import _needs_scrape

    assert _needs_scrape("wechat", None) is True
    assert _needs_scrape("wechat", "") is True


def test_needs_scrape_kol_any_body_skips():
    """KOL: pre-ir-4 semantic preserved — any non-empty body skips scrape,
    even very short stubs (legacy KOL has whole-body persisted at scrape
    time; short body for KOL means a checkpoint-recovered partial that the
    caller's pre-scrape guard already handles)."""
    from batch_ingest_from_spider import _needs_scrape

    assert _needs_scrape("wechat", "x") is False
    assert _needs_scrape("wechat", "x" * 50) is False
    assert _needs_scrape("wechat", "x" * 5000) is False


def test_needs_scrape_rss_no_body_triggers_scrape():
    from batch_ingest_from_spider import _needs_scrape

    assert _needs_scrape("rss", None) is True
    assert _needs_scrape("rss", "") is True


def test_needs_scrape_rss_short_body_triggers_scrape():
    """RSS rows whose body is the feed's <description> excerpt (≤ threshold)
    must re-scrape via the generic cascade. Boundary is inclusive on the
    threshold value (≤100 = scrape; >100 = skip)."""
    from batch_ingest_from_spider import _needs_scrape, RSS_SCRAPE_THRESHOLD

    assert _needs_scrape("rss", "x" * 1) is True
    assert _needs_scrape("rss", "x" * 50) is True
    assert _needs_scrape("rss", "x" * RSS_SCRAPE_THRESHOLD) is True


def test_needs_scrape_rss_long_body_skips():
    """RSS rows where rss_fetch already captured <content:encoded> (well
    above 100 chars) skip scrape and go straight to Layer 2 / ainsert.
    Saves the generic-cascade network round-trip for ~27% of W0-audited
    local RSS rows."""
    from batch_ingest_from_spider import _needs_scrape, RSS_SCRAPE_THRESHOLD

    assert _needs_scrape("rss", "x" * (RSS_SCRAPE_THRESHOLD + 1)) is False
    assert _needs_scrape("rss", "x" * 500) is False
    assert _needs_scrape("rss", "x" * 10000) is False


def test_rss_scrape_threshold_value():
    """Pin the threshold value so behavioral tests above remain meaningful
    if the constant is bumped accidentally. RSS feed's <description>
    typically 50-80 chars; pre-ir-4 production data shows 100 char floor
    captures the rss_fetch full-content path (W0 audit)."""
    from batch_ingest_from_spider import RSS_SCRAPE_THRESHOLD

    assert RSS_SCRAPE_THRESHOLD == 100


# ---------------------------------------------------------------------------
# _persist_scraped_body source dispatch
# ---------------------------------------------------------------------------


def _make_scrape(markdown: str = "x" * 1500, content_html: str | None = None):
    from lib.scraper import ScrapeResult

    return ScrapeResult(
        markdown=markdown,
        content_html=content_html,
        method="apify",
        summary_only=False,
    )


def _make_dual_source_db() -> sqlite3.Connection:
    """In-memory sqlite with both KOL and RSS body-persistence targets."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, url TEXT, title TEXT, body TEXT
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY, feed_id INTEGER NOT NULL,
            url TEXT, title TEXT, body TEXT
        );
        """
    )
    return conn


def test_persist_kol_writes_to_articles_table():
    """source='wechat' → updates articles.body (preserves rss_articles.body)."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_dual_source_db()
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (42, 'https://mp.weixin.qq.com/s/x', 't', NULL)"
    )
    conn.execute(
        "INSERT INTO rss_articles(id, feed_id, url, title, body) "
        "VALUES (42, 1, 'https://example.com/x', 't', 'pre-existing rss body')"
    )
    conn.commit()

    persisted = _persist_scraped_body(conn, 42, "wechat", _make_scrape("kol body x" * 60))

    assert persisted is not None
    kol_body = conn.execute("SELECT body FROM articles WHERE id=42").fetchone()[0]
    rss_body = conn.execute("SELECT body FROM rss_articles WHERE id=42").fetchone()[0]
    assert kol_body and "kol body" in kol_body, "articles.body must be updated"
    assert rss_body == "pre-existing rss body", (
        "rss_articles.body must NOT be touched when source='wechat'"
    )


def test_persist_rss_writes_to_rss_articles_table():
    """source='rss' → updates rss_articles.body (preserves articles.body)."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_dual_source_db()
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (42, 'https://mp.weixin.qq.com/s/x', 't', 'pre-existing kol body')"
    )
    conn.execute(
        "INSERT INTO rss_articles(id, feed_id, url, title, body) "
        "VALUES (42, 1, 'https://example.com/x', 't', NULL)"
    )
    conn.commit()

    persisted = _persist_scraped_body(conn, 42, "rss", _make_scrape("rss body y" * 60))

    assert persisted is not None
    kol_body = conn.execute("SELECT body FROM articles WHERE id=42").fetchone()[0]
    rss_body = conn.execute("SELECT body FROM rss_articles WHERE id=42").fetchone()[0]
    assert kol_body == "pre-existing kol body", (
        "articles.body must NOT be touched when source='rss'"
    )
    assert rss_body and "rss body" in rss_body, "rss_articles.body must be updated"


def test_persist_rss_id_collision_isolates_correctly():
    """The whole point of dual-source identity: KOL id=42 and RSS id=42 are
    different rows on different tables. Persisting RSS scrape with id=42
    must not touch KOL id=42 even though the numeric id is identical."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_dual_source_db()
    # Both id=42 rows, both NULL body — about to be racing.
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (42, 'https://mp.weixin.qq.com/s/x', 'kol-title', NULL)"
    )
    conn.execute(
        "INSERT INTO rss_articles(id, feed_id, url, title, body) "
        "VALUES (42, 1, 'https://example.com/x', 'rss-title', NULL)"
    )
    conn.commit()

    # Persist ONLY RSS. KOL id=42 must remain NULL.
    _persist_scraped_body(conn, 42, "rss", _make_scrape("rss body" * 80))

    kol_body = conn.execute("SELECT body FROM articles WHERE id=42").fetchone()[0]
    rss_body = conn.execute("SELECT body FROM rss_articles WHERE id=42").fetchone()[0]
    assert kol_body is None, "RSS persist must NOT cross-update KOL id=42"
    assert rss_body is not None and "rss body" in rss_body


def test_persist_unknown_source_is_soft_skip(caplog):
    """Unknown source value (typo / future enum) → return None, log WARNING,
    do NOT default to 'wechat' (defaulting could silently corrupt the wrong
    table). caplog asserts the WARNING fires."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_dual_source_db()
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (1, 'https://x', 't', 'untouched')"
    )
    conn.commit()

    with caplog.at_level("WARNING"):
        result = _persist_scraped_body(conn, 1, "twitter", _make_scrape())

    assert result is None
    body = conn.execute("SELECT body FROM articles WHERE id=1").fetchone()[0]
    assert body == "untouched", "unknown source must NOT default-update articles"
    assert any(
        "unknown source" in rec.message.lower() for rec in caplog.records
    )


def test_persist_rss_idempotent_500_char_guard():
    """The pre-existing 500-char idempotency guard from BODY-01 must apply
    to the rss_articles UPDATE the same way it applies to articles. A row
    with body >= 500 chars must NOT be overwritten."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_dual_source_db()
    conn.execute(
        "INSERT INTO rss_articles(id, feed_id, url, title, body) "
        "VALUES (1, 1, 'http://x', 't', ?)",
        ("y" * 600,),
    )
    conn.commit()

    _persist_scraped_body(conn, 1, "rss", _make_scrape("x" * 1500))

    row = conn.execute("SELECT body FROM rss_articles WHERE id=1").fetchone()
    assert row[0] == "y" * 600, (
        "rss_articles 500-char guard must prevent overwrite, mirror of articles"
    )


def test_persist_rss_swallows_db_exception(caplog):
    """rss_articles UPDATE failure (lock, schema mismatch, etc.) returns
    None, never raises into main loop. Mirror of the KOL exception swallow."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError("locked")
    with caplog.at_level("WARNING"):
        result = _persist_scraped_body(conn, 1, "rss", _make_scrape())

    assert result is None
    assert any(
        "rss" in rec.message.lower() and ("persist" in rec.message.lower() or "body" in rec.message.lower())
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# scrape_url call site no longer hardcodes site_hint='wechat'
# ---------------------------------------------------------------------------


def test_ingest_from_db_scrape_call_drops_site_hint():
    """The W1 ``site_hint='wechat'`` was a deliberate KOL-only gate that
    forced the WeChat cascade on every URL — broken for RSS rows whose
    URLs are blogs/news sites. W2 removes it so scrape_url's _route()
    auto-detects WeChat vs generic by URL pattern.

    Structural test: scan ingest_from_db's source, find every active
    ``scrape_url(`` call line (skipping comment-only lines that may
    explain *why* the hint was dropped), and assert NONE of them carry
    site_hint=. We don't import-and-execute because the path requires DB
    + LLM mocks the rest of the suite already covers."""
    import inspect
    import batch_ingest_from_spider

    src = inspect.getsource(batch_ingest_from_spider.ingest_from_db)
    # Scan lines that contain a *call* to scrape_url (i.e. not a comment).
    call_lines = [
        ln for ln in src.splitlines()
        if "scrape_url(" in ln and not ln.lstrip().startswith("#")
    ]
    assert call_lines, (
        "regression: scrape_url is not called from ingest_from_db at all"
    )
    for ln in call_lines:
        assert "site_hint" not in ln, (
            f"ir-4 W2: scrape_url() call must NOT pass site_hint — that "
            f"forces a single cascade and breaks dual-source auto-routing. "
            f"Offending line: {ln.strip()!r}"
        )


def test_ingest_from_db_uses_needs_scrape_helper():
    """Structural: the W1 KOL-only gate ``if not body and source == "wechat":``
    is replaced by the centralised helper call. This test guards against
    accidental revert (or duplication of the gate condition)."""
    import inspect
    import batch_ingest_from_spider

    src = inspect.getsource(batch_ingest_from_spider.ingest_from_db)
    assert "_needs_scrape(source, body)" in src, (
        "ir-4 W2: ingest_from_db must call _needs_scrape(source, body) "
        "instead of the W1 inline 'source == \"wechat\"' gate."
    )


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_body_table_for_mapping_complete():
    """The dispatch dict must cover both source values. Future sources
    (if any) require explicit decisions — no implicit defaulting."""
    from batch_ingest_from_spider import _BODY_TABLE_FOR

    assert _BODY_TABLE_FOR == {"wechat": "articles", "rss": "rss_articles"}


def test_persist_signature_takes_source_third():
    """Pin the API: ``_persist_scraped_body(conn, article_id, source, scrape)``.
    Reordering would break call sites silently (positional)."""
    import inspect
    from batch_ingest_from_spider import _persist_scraped_body

    sig = inspect.signature(_persist_scraped_body)
    params = list(sig.parameters)
    assert params == ["conn", "article_id", "source", "scrape"], (
        f"signature drift: {params}; ir-4 W2 contract is "
        f"(conn, article_id, source, scrape)"
    )
