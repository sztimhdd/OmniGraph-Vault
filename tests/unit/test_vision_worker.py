"""Phase 10 plan 10-02: async Vision worker + sub-doc ainsert + failure tolerance.

Covers:
- D-10.06 (ARCH-02): async Vision worker calls describe_images + rag.ainsert(sub_doc)
- D-10.07 (ARCH-03): sub-doc content shape (header, list-item format, omit empty, skip-if-all-empty)
- D-10.08 (ARCH-04): worker swallows all exceptions; parent doc unaffected
- D-10.09 (batch drain): orchestrator drains pending Vision tasks before finalize_storages

All tests mock describe_images / get_last_describe_stats / emit_batch_complete / rag so no
live Vision calls, no real LightRAG init, no real I/O.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    """DEEPSEEK_API_KEY=dummy to satisfy lib.__init__ eager import (Phase 5 FLAG 2)."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


@pytest.fixture
def _fake_rag():
    """MagicMock rag with AsyncMock ainsert — records calls for ordering assertions."""
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.adelete_by_doc_id = AsyncMock()
    rag.finalize_storages = AsyncMock()
    return rag


@pytest.fixture
def _dummy_filter_stats():
    """FilterStats instance for the worker's emit_batch_complete call."""
    from image_pipeline import FilterStats

    return FilterStats(
        input=2,
        kept=2,
        filtered_too_small=0,
        size_read_failed=0,
        timings_ms={"total_read": 0},
    )


# ---------------------------------------------------------------------------
# Task 1 — D-10.06 / D-10.07 / D-10.08 worker behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_calls_describe_then_subdoc_ainsert(
    monkeypatch, _fake_rag, _dummy_filter_stats
):
    """D-10.06: worker calls describe_images then rag.ainsert with sub-doc id."""
    import ingest_wechat

    url_to_path = {
        "url_a": Path("a.jpg"),
        "url_b": Path("b.jpg"),
    }
    descriptions = {Path("a.jpg"): "desc A", Path("b.jpg"): "desc B"}
    describe_mock = MagicMock(return_value=descriptions)
    monkeypatch.setattr(ingest_wechat, "describe_images", describe_mock)
    monkeypatch.setattr(
        ingest_wechat,
        "get_last_describe_stats",
        MagicMock(return_value={"provider_mix": {"gemini": 2}, "vision_success": 2}),
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    await ingest_wechat._vision_worker_impl(
        rag=_fake_rag,
        article_hash="hash1",
        url_to_path=url_to_path,
        title="My Title",
        filter_stats=_dummy_filter_stats,
        download_input_count=2,
        download_failed=0,
    )

    describe_mock.assert_called_once()
    assert _fake_rag.ainsert.await_count == 1
    call = _fake_rag.ainsert.await_args_list[0]
    assert call.kwargs.get("ids") == ["wechat_hash1_images"], (
        f"expected ids=['wechat_hash1_images'], got {call.kwargs}"
    )


@pytest.mark.asyncio
async def test_subdoc_content_header_and_format(
    monkeypatch, _fake_rag, _dummy_filter_stats
):
    """D-10.07: sub-doc content starts with '# Images for <title>\\n\\n' and lists items."""
    import ingest_wechat

    url_to_path = {
        "url_a": Path("a.jpg"),
        "url_b": Path("b.jpg"),
    }
    descriptions = {Path("a.jpg"): "desc A", Path("b.jpg"): "desc B"}
    monkeypatch.setattr(
        ingest_wechat, "describe_images", MagicMock(return_value=descriptions)
    )
    monkeypatch.setattr(
        ingest_wechat, "get_last_describe_stats", MagicMock(return_value=None)
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    await ingest_wechat._vision_worker_impl(
        rag=_fake_rag,
        article_hash="hash1",
        url_to_path=url_to_path,
        title="My Title",
        filter_stats=_dummy_filter_stats,
        download_input_count=2,
        download_failed=0,
    )

    call = _fake_rag.ainsert.await_args_list[0]
    content = call.args[0] if call.args else call.kwargs.get("input")
    assert content is not None
    assert content.startswith("# Images for My Title\n\n"), (
        f"header shape wrong; got first 40 chars: {content[:40]!r}"
    )
    assert "- [image 0]: desc A" in content
    assert "- [image 1]: desc B" in content


@pytest.mark.asyncio
async def test_subdoc_omits_empty_descriptions(
    monkeypatch, _fake_rag, _dummy_filter_stats
):
    """D-10.07: empty descriptions OMITTED; index NOT renumbered (preserve positions)."""
    import ingest_wechat

    url_to_path = {
        "url_a": Path("a.jpg"),
        "url_b": Path("b.jpg"),
        "url_c": Path("c.jpg"),
    }
    descriptions = {
        Path("a.jpg"): "desc A",
        Path("b.jpg"): "",  # empty — must be omitted
        Path("c.jpg"): "desc C",
    }
    monkeypatch.setattr(
        ingest_wechat, "describe_images", MagicMock(return_value=descriptions)
    )
    monkeypatch.setattr(
        ingest_wechat, "get_last_describe_stats", MagicMock(return_value=None)
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    await ingest_wechat._vision_worker_impl(
        rag=_fake_rag,
        article_hash="hash1",
        url_to_path=url_to_path,
        title="T",
        filter_stats=_dummy_filter_stats,
        download_input_count=3,
        download_failed=0,
    )

    call = _fake_rag.ainsert.await_args_list[0]
    content = call.args[0] if call.args else call.kwargs.get("input")
    assert "[image 0]: desc A" in content
    assert "[image 2]: desc C" in content
    # image 1 had an empty description — OMITTED entirely (not renumbered)
    assert "[image 1]:" not in content


@pytest.mark.asyncio
async def test_subdoc_skipped_when_all_descriptions_empty(
    monkeypatch, _fake_rag, _dummy_filter_stats, caplog
):
    """D-10.07: zero successful descriptions → sub-doc ainsert NOT called; info log emitted."""
    import ingest_wechat

    url_to_path = {"url_a": Path("a.jpg"), "url_b": Path("b.jpg")}
    descriptions = {Path("a.jpg"): "", Path("b.jpg"): ""}
    monkeypatch.setattr(
        ingest_wechat, "describe_images", MagicMock(return_value=descriptions)
    )
    monkeypatch.setattr(
        ingest_wechat, "get_last_describe_stats", MagicMock(return_value=None)
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    with caplog.at_level(logging.INFO, logger="ingest_wechat"):
        await ingest_wechat._vision_worker_impl(
            rag=_fake_rag,
            article_hash="hash1",
            url_to_path=url_to_path,
            title="T",
            filter_stats=_dummy_filter_stats,
            download_input_count=2,
            download_failed=0,
        )

    assert _fake_rag.ainsert.await_count == 0, "sub-doc ainsert must NOT be called"
    # Check caplog for the skip marker
    combined = " ".join(r.getMessage() for r in caplog.records)
    assert "vision_subdoc_skipped" in combined, (
        f"expected 'vision_subdoc_skipped' in logs; got: {combined!r}"
    )


@pytest.mark.asyncio
async def test_worker_swallows_describe_exception(
    monkeypatch, _fake_rag, _dummy_filter_stats, caplog
):
    """D-10.08: describe_images raises → worker returns None; rag.ainsert NOT called."""
    import ingest_wechat

    url_to_path = {"url_a": Path("a.jpg")}

    def _raise(*args, **kwargs):
        raise RuntimeError("all providers down")

    monkeypatch.setattr(ingest_wechat, "describe_images", _raise)
    monkeypatch.setattr(
        ingest_wechat, "get_last_describe_stats", MagicMock(return_value=None)
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    with caplog.at_level(logging.WARNING, logger="ingest_wechat"):
        result = await ingest_wechat._vision_worker_impl(
            rag=_fake_rag,
            article_hash="hash1",
            url_to_path=url_to_path,
            title="T",
            filter_stats=_dummy_filter_stats,
            download_input_count=1,
            download_failed=0,
        )

    assert result is None
    assert _fake_rag.ainsert.await_count == 0, (
        "rag.ainsert must NOT be called when describe_images raised"
    )
    # Worker must have logged the failure
    combined = " ".join(r.getMessage() for r in caplog.records)
    assert "all providers down" in combined or "Vision worker failed" in combined


@pytest.mark.asyncio
async def test_worker_swallows_ainsert_exception(
    monkeypatch, _fake_rag, _dummy_filter_stats, caplog
):
    """D-10.08: rag.ainsert raises on sub-doc → worker returns None, no propagate."""
    import ingest_wechat

    url_to_path = {"url_a": Path("a.jpg")}
    descriptions = {Path("a.jpg"): "desc A"}
    monkeypatch.setattr(
        ingest_wechat, "describe_images", MagicMock(return_value=descriptions)
    )
    monkeypatch.setattr(
        ingest_wechat, "get_last_describe_stats", MagicMock(return_value=None)
    )
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", MagicMock())

    _fake_rag.ainsert = AsyncMock(side_effect=RuntimeError("storage corrupt"))

    with caplog.at_level(logging.WARNING, logger="ingest_wechat"):
        result = await ingest_wechat._vision_worker_impl(
            rag=_fake_rag,
            article_hash="hash2",
            url_to_path=url_to_path,
            title="T",
            filter_stats=_dummy_filter_stats,
            download_input_count=1,
            download_failed=0,
        )

    assert result is None
    combined = " ".join(r.getMessage() for r in caplog.records)
    assert "storage corrupt" in combined or "Vision worker failed" in combined


@pytest.mark.asyncio
async def test_worker_emits_batch_complete(
    monkeypatch, _fake_rag, _dummy_filter_stats
):
    """Phase 8 IMG-04 preserved: emit_batch_complete fires from worker's finally block."""
    import ingest_wechat

    url_to_path = {"url_a": Path("a.jpg"), "url_b": Path("b.jpg")}
    descriptions = {Path("a.jpg"): "desc A", Path("b.jpg"): ""}
    describe_stats = {
        "provider_mix": {"gemini": 1, "siliconflow": 0, "openrouter": 0},
        "vision_success": 1,
        "vision_error": 1,
        "vision_timeout": 0,
    }
    monkeypatch.setattr(
        ingest_wechat, "describe_images", MagicMock(return_value=descriptions)
    )
    monkeypatch.setattr(
        ingest_wechat,
        "get_last_describe_stats",
        MagicMock(return_value=describe_stats),
    )
    emit_spy = MagicMock()
    monkeypatch.setattr(ingest_wechat, "emit_batch_complete", emit_spy)

    await ingest_wechat._vision_worker_impl(
        rag=_fake_rag,
        article_hash="hash3",
        url_to_path=url_to_path,
        title="T",
        filter_stats=_dummy_filter_stats,
        download_input_count=2,
        download_failed=0,
    )

    emit_spy.assert_called_once()
    kwargs = emit_spy.call_args.kwargs
    assert kwargs.get("describe_stats") == describe_stats, (
        f"emit_batch_complete not given describe_stats; got {kwargs}"
    )
    assert kwargs.get("filter_stats") is _dummy_filter_stats
    assert kwargs.get("download_input_count") == 2
    assert kwargs.get("download_failed") == 0


# ---------------------------------------------------------------------------
# Task 2 — D-10.09 batch orchestrator drain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_drains_pending_vision_tasks(monkeypatch, _fake_rag):
    """D-10.09: run() awaits pending Vision tasks before finalize_storages."""
    import batch_ingest_from_spider

    drained: list[str] = []

    async def _fake_vision_work():
        await asyncio.sleep(0.2)
        drained.append("done")

    # 260509-p1n: tasks are now tracked via lib.vision_tracking.track_vision_task
    # at the real spawn site (ingest_wechat.py:1186); the fake must mirror that
    # registration or the narrow-set drain will be a no-op.
    from lib.vision_tracking import track_vision_task

    # Patch ingest_article so it spawns a Vision task and returns ok.
    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    # 260510-uai: outer ingest_article signature is (source, url, dry_run, rag, ...).
    async def _fake_ingest_article(source, url, dry_run, rag, effective_timeout=None):
        track_vision_task(asyncio.create_task(_fake_vision_work()))
        return True, 0.0, True

    monkeypatch.setattr(batch_ingest_from_spider, "ingest_article", _fake_ingest_article)

    # Patch get_rag — late-imported inside run().
    async def _fake_get_rag(flush=True):
        return _fake_rag

    monkeypatch.setattr("ingest_wechat.get_rag", _fake_get_rag)

    # Stub kol_config + list_articles so run() delivers exactly one article.
    fake_config = MagicMock()
    fake_config.FAKEIDS = {"acct1": "fakeid1"}
    fake_config.TOKEN = "tok"
    fake_config.COOKIE = "cookie"
    monkeypatch.setattr(batch_ingest_from_spider, "kol_config", fake_config)
    monkeypatch.setattr(
        batch_ingest_from_spider,
        "list_articles",
        lambda **kw: [{"title": "t", "url": "https://mp.weixin.qq.com/s/x"}],
    )
    monkeypatch.setattr(batch_ingest_from_spider, "SLEEP_BETWEEN_ARTICLES", 0)
    monkeypatch.setattr(batch_ingest_from_spider, "RATE_LIMIT_SLEEP_ACCOUNTS", 0)
    # Avoid loading ~/.hermes/.env in CI context.
    monkeypatch.setattr(batch_ingest_from_spider, "_load_hermes_env", lambda: None)

    await batch_ingest_from_spider.run(
        days_back=30, max_articles=1, dry_run=False
    )

    # The fake Vision task must have completed (drained) before finalize_storages ran.
    assert drained == ["done"], (
        "pending Vision task was not drained before finalize_storages"
    )
    _fake_rag.finalize_storages.assert_awaited_once()


@pytest.mark.xfail(
    strict=False,
    reason="kb-v2.1-9 audit: passes individually after B2b fix but fails in full pytest suite. "
    "Likely module-state leak from a prior test (similar to lightrag_embedding_rotation "
    "isolation drift). Surface for test-isolation refactor in a follow-up quick.",
)
@pytest.mark.asyncio
async def test_ingest_from_db_drains_pending_vision_tasks(
    monkeypatch, tmp_path, _fake_rag
):
    """D-10.09: ingest_from_db() drains pending Vision tasks before finalize_storages."""
    import sqlite3

    import batch_ingest_from_spider

    # Build a minimal SQLite DB matching the schema ingest_from_db SELECTs.
    db_path = tmp_path / "kol_scan.db"
    conn = sqlite3.connect(db_path)
    # ir-4 dual-source: SQL also queries rss_articles + rss_feeds (UNION ALL),
    # so the fixture must declare them. Empty tables are fine — UNION returns
    # only the KOL row(s) we seeded below.
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            fakeid TEXT
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            title TEXT,
            url TEXT UNIQUE,
            body TEXT,
            enriched INTEGER DEFAULT 0,
            content_hash TEXT,
            digest TEXT,
            layer1_verdict TEXT NULL,
            layer1_reason TEXT NULL,
            layer1_at TEXT NULL,
            layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL,
            layer2_reason TEXT NULL,
            layer2_at TEXT NULL,
            layer2_prompt_version TEXT NULL,
            image_count INTEGER DEFAULT 0
        );
        CREATE TABLE rss_feeds (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY, feed_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, summary TEXT,
            layer1_verdict TEXT NULL, layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL, layer2_prompt_version TEXT NULL,
            image_count INTEGER DEFAULT 0
        );
        CREATE TABLE classifications (
            article_id INTEGER,
            depth_score INTEGER,
            depth INTEGER,
            topic TEXT,
            topics TEXT,
            reason TEXT,
            rationale TEXT,
            classified_at TEXT
        );
        """
    )
    conn.execute("INSERT INTO accounts(name, fakeid) VALUES (?, ?)", ("acct1", "fakeid1"))
    conn.execute(
        "INSERT INTO articles(account_id, title, url, body) VALUES (?, ?, ?, ?)",
        (1, "T", "https://mp.weixin.qq.com/s/x", "body text with enough content"),
    )
    conn.execute(
        "INSERT INTO classifications(article_id, depth_score, depth, topic, topics, rationale) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 2, 2, "AI agents", '["AI agents"]', "has topic"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(batch_ingest_from_spider, "DB_PATH", db_path)

    drained: list[str] = []

    async def _fake_vision_work():
        await asyncio.sleep(0.2)
        drained.append("done")

    # 260509-p1n: register fake task via track_vision_task to match the real spawn site.
    from lib.vision_tracking import track_vision_task

    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    # 260510-uai: outer ingest_article signature is (source, url, dry_run, rag, ...).
    async def _fake_ingest_article(source, url, dry_run, rag, effective_timeout=None):
        track_vision_task(asyncio.create_task(_fake_vision_work()))
        return True, 0.0, True

    monkeypatch.setattr(batch_ingest_from_spider, "ingest_article", _fake_ingest_article)

    async def _fake_get_rag(flush=True):
        return _fake_rag

    monkeypatch.setattr("ingest_wechat.get_rag", _fake_get_rag)
    monkeypatch.setattr(batch_ingest_from_spider, "SLEEP_BETWEEN_ARTICLES", 0)
    monkeypatch.setattr(batch_ingest_from_spider, "_load_hermes_env", lambda: None)
    # Skip classifier pre-flight; classification row already present.
    monkeypatch.setattr(
        batch_ingest_from_spider,
        "_classify_full_body",
        AsyncMock(return_value={"depth": 2, "topics": ["AI agents"], "rationale": "ok"}),
    )
    monkeypatch.setattr(
        batch_ingest_from_spider, "get_deepseek_api_key", lambda: "dummy"
    )
    # 260507-lai v3.5 refactor: ingest_from_db now calls layer1_pre_filter +
    # layer2_full_body_score. Without a mock the real Vertex Gemini call fires
    # and fails with GOOGLE_CLOUD_PROJECT not set in this unit-test environment.
    from lib.article_filter import FilterResult, PROMPT_VERSION_LAYER1, PROMPT_VERSION_LAYER2

    async def _fake_layer1(arts):
        return [FilterResult(verdict="candidate", reason="ok", prompt_version=PROMPT_VERSION_LAYER1) for _ in arts]

    async def _fake_layer2(articles):
        return [FilterResult(verdict="ok", reason="ok", prompt_version=PROMPT_VERSION_LAYER2) for _ in articles]

    monkeypatch.setattr("lib.article_filter.layer1_pre_filter", _fake_layer1)
    monkeypatch.setattr("lib.article_filter.layer2_full_body_score", _fake_layer2)
    monkeypatch.setattr("batch_ingest_from_spider.layer1_pre_filter", _fake_layer1, raising=False)
    monkeypatch.setattr("batch_ingest_from_spider.layer2_full_body_score", _fake_layer2, raising=False)

    await batch_ingest_from_spider.ingest_from_db(
        topic=["AI agents"], min_depth=1, dry_run=False
    )

    assert drained == ["done"]
    _fake_rag.finalize_storages.assert_awaited_once()


@pytest.mark.asyncio
async def test_drain_timeout_cancels_stragglers(monkeypatch, _fake_rag):
    """D-10.09: tasks exceeding drain deadline are cancelled; finalize_storages still runs."""
    import batch_ingest_from_spider

    # Shorten the drain timeout so the test doesn't sleep 120s.
    monkeypatch.setattr(batch_ingest_from_spider, "VISION_DRAIN_TIMEOUT", 0.1)

    straggler_ref: dict = {}

    async def _straggler():
        try:
            await asyncio.sleep(10)  # far longer than drain timeout
        except asyncio.CancelledError:
            straggler_ref["cancelled"] = True
            raise

    # 260509-p1n: register straggler via track_vision_task to match the real spawn site.
    from lib.vision_tracking import track_vision_task

    # 260510-uai/oxq: outer ingest_article signature is
    # (source, url, dry_run, rag, ...) returning 3-tuple (success, wall, doc_confirmed).
    async def _fake_ingest_article(source, url, dry_run, rag, effective_timeout=None):
        straggler_ref["task"] = track_vision_task(asyncio.create_task(_straggler()))
        return True, 0.0, True

    monkeypatch.setattr(batch_ingest_from_spider, "ingest_article", _fake_ingest_article)

    async def _fake_get_rag(flush=True):
        return _fake_rag

    monkeypatch.setattr("ingest_wechat.get_rag", _fake_get_rag)

    fake_config = MagicMock()
    fake_config.FAKEIDS = {"acct1": "fakeid1"}
    fake_config.TOKEN = "tok"
    fake_config.COOKIE = "cookie"
    monkeypatch.setattr(batch_ingest_from_spider, "kol_config", fake_config)
    monkeypatch.setattr(
        batch_ingest_from_spider,
        "list_articles",
        lambda **kw: [{"title": "t", "url": "https://mp.weixin.qq.com/s/x"}],
    )
    monkeypatch.setattr(batch_ingest_from_spider, "SLEEP_BETWEEN_ARTICLES", 0)
    monkeypatch.setattr(batch_ingest_from_spider, "RATE_LIMIT_SLEEP_ACCOUNTS", 0)
    monkeypatch.setattr(batch_ingest_from_spider, "_load_hermes_env", lambda: None)

    await batch_ingest_from_spider.run(
        days_back=30, max_articles=1, dry_run=False
    )

    # Task should have been cancelled (drain timeout fired).
    assert straggler_ref.get("cancelled") is True, (
        "straggler task must be cancelled after drain timeout"
    )
    # finalize_storages still ran despite the timeout.
    _fake_rag.finalize_storages.assert_awaited_once()
