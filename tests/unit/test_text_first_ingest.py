"""Phase 10 plan 10-01: text-first ingest split tests (D-10.05 / ARCH-01).

Covers the split of `ingest_wechat.ingest_article` so the synchronous
`rag.ainsert` hot-path returns without awaiting Vision description work.
Vision runs in a background `asyncio.create_task(_vision_worker_impl(...))`;
this plan creates the SHAPE (stub worker) — plan 10-02 fills in the body.

All tests mock scraping, image download, describe_images, and rag so no
live network, no LightRAG init, no real Vision API calls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
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
    """MagicMock rag with AsyncMock ainsert — records calls for ordering assertions.

    Default `aget_docs_by_ids` returns a PROCESSED status for whichever doc_id
    is queried, matching the Task 0.8 verification-hook happy path so the
    existing suite does not short-circuit on the new content_hash gate.
    Tests that exercise the unverified path override this with an explicit
    `side_effect` or `return_value`.
    """
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.adelete_by_doc_id = AsyncMock()
    rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "PROCESSED"} for i in ids}
    )
    return rag


@pytest.fixture
def _isolated_image_dir(tmp_path, monkeypatch):
    """Redirect BASE_IMAGE_DIR to a tmp path so cache-hit files don't collide."""
    import ingest_wechat

    monkeypatch.setattr(ingest_wechat, "BASE_IMAGE_DIR", str(tmp_path))
    # Also isolate ENTITY_BUFFER_DIR so entity writes don't pollute the real dir.
    entity_buf = tmp_path / "entity_buffer"
    monkeypatch.setattr(ingest_wechat, "ENTITY_BUFFER_DIR", str(entity_buf))
    return tmp_path


def _make_article_data(
    url: str, img_urls: list[str] | None = None
) -> dict:
    """Build a minimal UA-scraped article_data dict."""
    return {
        "title": "Test Article",
        "content_html": "<p>Body text</p>",
        "img_urls": img_urls or [],
        "url": url,
        "publish_time": "2026-04-29",
        "method": "ua",
    }


def _patch_common(monkeypatch, _fake_rag, article_data, url_to_path):
    """Common patches shared across most tests."""
    import ingest_wechat

    monkeypatch.setattr(
        ingest_wechat,
        "scrape_wechat_ua",
        AsyncMock(return_value=article_data),
    )
    monkeypatch.setattr(
        ingest_wechat, "process_content", lambda html: ("body markdown", [])
    )
    monkeypatch.setattr(
        ingest_wechat, "download_images", MagicMock(return_value=url_to_path)
    )
    # filter_small_images returns (url_to_path, stats) tuple
    from image_pipeline import FilterStats

    stats = FilterStats(
        input=len(url_to_path),
        kept=len(url_to_path),
        filtered_too_small=0,
        size_read_failed=0,
        timings_ms={"total_read": 0},
    )
    monkeypatch.setattr(
        ingest_wechat,
        "filter_small_images",
        MagicMock(return_value=(url_to_path, stats)),
    )
    monkeypatch.setattr(
        ingest_wechat,
        "localize_markdown",
        lambda md, mapping, article_hash="": md,
    )
    monkeypatch.setattr(
        ingest_wechat, "extract_entities", AsyncMock(return_value=[])
    )
    import cognee_wrapper

    monkeypatch.setattr(
        cognee_wrapper, "remember_article", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        ingest_wechat, "save_markdown_with_images", MagicMock()
    )


# ---------------------------------------------------------------------------
# Task 1 — D-10.05 return-type + content-shape + ordering + timing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_article_returns_task_when_images_present(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05: when images are present, ingest_article returns an asyncio.Task."""
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_with_images"
    img_urls = ["https://mmbiz.qpic.cn/a.jpg", "https://mmbiz.qpic.cn/b.jpg"]
    # Build url_to_path with real Path objects pointing into tmp dir.
    url_to_path = {
        u: _isolated_image_dir / f"img_{i}.jpg" for i, u in enumerate(img_urls)
    }
    article_data = _make_article_data(url, img_urls=img_urls)
    _patch_common(monkeypatch, _fake_rag, article_data, url_to_path)

    # Replace the Vision worker with a fast no-op so we can inspect the return.
    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)

    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)

    assert isinstance(result, asyncio.Task), (
        f"expected asyncio.Task when images present, got {type(result)}"
    )
    # Clean up: await the task so no warnings about never-awaited coroutines.
    await result


@pytest.mark.asyncio
async def test_ingest_article_returns_none_when_zero_images(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05: zero images → no Vision worker spawned → returns None."""
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_no_images"
    article_data = _make_article_data(url, img_urls=[])
    _patch_common(monkeypatch, _fake_rag, article_data, {})

    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)

    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)

    assert result is None


@pytest.mark.asyncio
async def test_ingest_article_returns_fast_with_slow_vision(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05 (CRITICAL): parent doc ainsert returns in <5s even if Vision sleeps 60s.

    Proves Vision is off the hot path: ingest_article does NOT await the worker.
    """
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_slow_vision"
    img_urls = ["https://mmbiz.qpic.cn/a.jpg"]
    url_to_path = {img_urls[0]: _isolated_image_dir / "img_0.jpg"}
    article_data = _make_article_data(url, img_urls=img_urls)
    _patch_common(monkeypatch, _fake_rag, article_data, url_to_path)

    # Simulate a slow Vision worker — 60s sleep. ingest_article must NOT await it.
    async def _slow_worker(**kwargs):
        await asyncio.sleep(60)
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _slow_worker)

    t0 = time.monotonic()
    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)
    elapsed = time.monotonic() - t0

    assert elapsed < 5.0, (
        f"ingest_article should return in <5s; took {elapsed:.2f}s "
        f"(Vision worker must be fire-and-forget, not awaited)"
    )
    assert isinstance(result, asyncio.Task)
    # Cancel the slow task so the test doesn't leak a pending coroutine.
    result.cancel()
    try:
        await result
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_parent_ainsert_content_has_references_not_descriptions(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05 content-shape: parent doc has [Image N Reference]: but NOT [Image N Description]:."""
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_content_shape"
    img_urls = [
        "https://mmbiz.qpic.cn/a.jpg",
        "https://mmbiz.qpic.cn/b.jpg",
    ]
    url_to_path = {
        u: _isolated_image_dir / f"img_{i}.jpg" for i, u in enumerate(img_urls)
    }
    article_data = _make_article_data(url, img_urls=img_urls)
    _patch_common(monkeypatch, _fake_rag, article_data, url_to_path)

    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)

    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)
    if isinstance(result, asyncio.Task):
        await result

    # Assert rag.ainsert was called for the parent doc.
    assert _fake_rag.ainsert.await_count >= 1
    first_call = _fake_rag.ainsert.await_args_list[0]
    # Content is passed positionally (args[0]) per current ingest_wechat usage.
    content = first_call.args[0] if first_call.args else first_call.kwargs.get("input")
    assert content is not None

    assert "[Image 0 Reference]:" in content
    assert "[Image 1 Reference]:" in content
    assert "[Image 0 Description]:" not in content
    assert "[Image 1 Description]:" not in content


@pytest.mark.asyncio
async def test_vision_worker_spawn_order_after_parent_ainsert(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05 ordering: rag.ainsert (parent) awaited BEFORE create_task for worker."""
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_order"
    img_urls = ["https://mmbiz.qpic.cn/a.jpg"]
    url_to_path = {img_urls[0]: _isolated_image_dir / "img_0.jpg"}
    article_data = _make_article_data(url, img_urls=img_urls)
    _patch_common(monkeypatch, _fake_rag, article_data, url_to_path)

    call_order: list[str] = []

    async def _recording_ainsert(*args, **kwargs):
        call_order.append("parent_ainsert")

    _fake_rag.ainsert = AsyncMock(side_effect=_recording_ainsert)

    async def _recording_worker(**kwargs):
        call_order.append("vision_worker")
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _recording_worker)

    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)
    if isinstance(result, asyncio.Task):
        await result  # let worker finish so it gets recorded

    # parent_ainsert must appear before vision_worker in the call order.
    assert "parent_ainsert" in call_order
    assert "vision_worker" in call_order
    assert call_order.index("parent_ainsert") < call_order.index("vision_worker"), (
        f"parent ainsert must complete before vision worker runs; got {call_order}"
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_none(
    monkeypatch, _fake_rag, _isolated_image_dir
):
    """D-10.05 cache-hit: pre-existing final_content.md → returns None (no worker spawn)."""
    import ingest_wechat

    url = "https://mp.weixin.qq.com/s/test_cache_hit"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = _isolated_image_dir / article_hash
    article_dir.mkdir(parents=True, exist_ok=True)
    # Pre-seed the cache.
    (article_dir / "final_content.md").write_text(
        "# Cached Title\n\nBody with [Image 0 Description]: cached desc",
        encoding="utf-8",
    )
    (article_dir / "metadata.json").write_text(
        json.dumps({"title": "Cached Title", "images": []}), encoding="utf-8"
    )

    monkeypatch.setattr(
        ingest_wechat, "extract_entities", AsyncMock(return_value=[])
    )

    # No scraping should happen — scrape_wechat_ua must NOT be called.
    scrape_mock = AsyncMock()
    monkeypatch.setattr(ingest_wechat, "scrape_wechat_ua", scrape_mock)

    result = await ingest_wechat.ingest_article(url, rag=_fake_rag)

    assert result is None
    scrape_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Extra gating test — stub existence
# ---------------------------------------------------------------------------


def test_vision_worker_impl_is_defined_as_async_stub():
    """D-10.06 prep: _vision_worker_impl must exist as an async function.

    Plan 10-01 creates the stub (returns None). Plan 10-02 replaces body.
    """
    import inspect
    import ingest_wechat

    assert hasattr(ingest_wechat, "_vision_worker_impl")
    assert inspect.iscoroutinefunction(ingest_wechat._vision_worker_impl)


def test_phase9_rollback_registry_symbols_still_present():
    """Regression guard: Phase 9 D-09.05 rollback API unchanged by this plan."""
    import ingest_wechat

    assert callable(ingest_wechat._register_pending_doc_id)
    assert callable(ingest_wechat._clear_pending_doc_id)
    assert callable(ingest_wechat.get_pending_doc_id)


# ---------------------------------------------------------------------------
# Task 0.8 (Phase 5 Wave 0) — aget_docs_by_ids verification hook
#
# Three cases: (A) doc absent from status, (B) status != PROCESSED,
# (C) status == PROCESSED happy path. Failure path skips content_hash write
# so batch re-scheduler retries — Phase 12 checkpoint/resume semantics.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task08_hook_raises_runtime_error_when_doc_absent_from_status(
    monkeypatch, _fake_rag, _isolated_image_dir, tmp_path
):
    """Task 0.8 case A: aget_docs_by_ids returns {} → helper raises RuntimeError.

    2026-05-10 hot-fix (quick 260510-h09): silent-skip replaced with raise so
    outer batch_ingest_from_spider.ingest_article marks status='failed' and
    mig 009 retry pool re-queues next cron. Renamed from
    ``test_task08_hook_skips_content_hash_when_doc_absent_from_status``.
    Reduce backoff_s effectively by patching the helper's defaults so the
    test runs sub-second.
    """
    import ingest_wechat

    db_path = tmp_path / "kol_scan.db"
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, content_hash TEXT, enriched INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE ingestions (article_id INTEGER, source TEXT NOT NULL DEFAULT 'wechat', status TEXT, PRIMARY KEY(article_id, status))"
    )
    url = "https://mp.weixin.qq.com/s/task08_case_a"
    conn.execute("INSERT INTO articles(url) VALUES (?)", (url,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(ingest_wechat, "DB_PATH", db_path)

    article_data = _make_article_data(url, img_urls=[])
    _patch_common(monkeypatch, _fake_rag, article_data, {})

    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)
    # Speed: zero backoff so retry loop completes sub-second.
    monkeypatch.setattr(ingest_wechat, "PROCESSED_VERIFY_BACKOFF_S", 0.0)
    # Override default fixture: return empty dict (doc absent).
    _fake_rag.aget_docs_by_ids = AsyncMock(return_value={})

    with pytest.raises(RuntimeError, match="PROCESSED verification failed"):
        await ingest_wechat.ingest_article(url, rag=_fake_rag)

    # content_hash NOT written because helper raised before the UPDATE statement.
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT content_hash FROM articles WHERE url = ?", (url,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is None, (
        f"content_hash should remain NULL when helper raises; got {row[0]!r}"
    )


@pytest.mark.asyncio
async def test_task08_hook_raises_runtime_error_when_status_not_processed(
    monkeypatch, _fake_rag, _isolated_image_dir, tmp_path
):
    """Task 0.8 case B: status=='FAILED' (never PROCESSED) → helper raises RuntimeError.

    2026-05-10 hot-fix (quick 260510-h09): renamed from
    ``test_task08_hook_skips_content_hash_when_status_not_processed``.
    Mock returns FAILED for ALL retry attempts so helper exhausts retries
    and raises.
    """
    import ingest_wechat

    db_path = tmp_path / "kol_scan.db"
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, content_hash TEXT, enriched INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE ingestions (article_id INTEGER, source TEXT NOT NULL DEFAULT 'wechat', status TEXT, PRIMARY KEY(article_id, status))"
    )
    url = "https://mp.weixin.qq.com/s/task08_case_b"
    conn.execute("INSERT INTO articles(url) VALUES (?)", (url,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(ingest_wechat, "DB_PATH", db_path)

    article_data = _make_article_data(url, img_urls=[])
    _patch_common(monkeypatch, _fake_rag, article_data, {})

    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)
    # Speed: zero backoff so retry loop completes sub-second.
    monkeypatch.setattr(ingest_wechat, "PROCESSED_VERIFY_BACKOFF_S", 0.0)
    # Override default fixture: status is FAILED for ALL retry attempts.
    _fake_rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "FAILED"} for i in ids}
    )

    with pytest.raises(RuntimeError, match="PROCESSED verification failed"):
        await ingest_wechat.ingest_article(url, rag=_fake_rag)

    # content_hash NOT written because helper raised before the UPDATE statement.
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT content_hash FROM articles WHERE url = ?", (url,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is None, (
        f"content_hash should remain NULL when helper raises; got {row[0]!r}"
    )


@pytest.mark.asyncio
async def test_task08_hook_writes_content_hash_when_status_processed(
    monkeypatch, _fake_rag, _isolated_image_dir, tmp_path
):
    """Task 0.8 case C: status=='PROCESSED' → content_hash IS written (happy path).

    2026-05-10 hot-fix (quick 260510-h09): the test's fixture sqlite DB
    needs the ``source TEXT NOT NULL DEFAULT 'wechat'`` column added (predates
    mig 008) so the new INSERT's ``source='wechat'`` field has a target.
    """
    import ingest_wechat

    db_path = tmp_path / "kol_scan.db"
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, content_hash TEXT, enriched INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE ingestions (article_id INTEGER, source TEXT NOT NULL DEFAULT 'wechat', status TEXT, PRIMARY KEY(article_id, status))"
    )
    url = "https://mp.weixin.qq.com/s/task08_case_c"
    conn.execute("INSERT INTO articles(url) VALUES (?)", (url,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(ingest_wechat, "DB_PATH", db_path)

    article_data = _make_article_data(url, img_urls=[])
    _patch_common(monkeypatch, _fake_rag, article_data, {})

    async def _noop_worker(**kwargs):
        return None

    monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _noop_worker)
    # Default fixture already returns PROCESSED, but reassert explicitly for clarity.
    _fake_rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "PROCESSED"} for i in ids}
    )

    await ingest_wechat.ingest_article(url, rag=_fake_rag)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT content_hash FROM articles WHERE url = ?", (url,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None, (
        "content_hash MUST be written when aget_docs_by_ids reports PROCESSED"
    )
    assert len(row[0]) >= 8, (
        f"content_hash should be a non-trivial hash; got {row[0]!r}"
    )
