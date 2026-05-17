"""E2E failure-injection tests for the Phase 12 checkpoint/resume mechanism.

These tests realize Gate-1 acceptance: inject failure at each of the 4 stage
boundaries, verify resume skips completed work, verify atomic writes leave no
.tmp corpses. All external dependencies (scrape, download, ainsert, vision)
are mocked.
"""
from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _checkpoint_base(monkeypatch, tmp_path):
    base = tmp_path / "omonigraph-vault"
    base.mkdir(parents=True)
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(base))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    import lib.checkpoint as ckpt
    importlib.reload(ckpt)
    yield ckpt


@pytest.fixture
def sample_url():
    return "https://mp.weixin.qq.com/s/gate1-e2e-test"


@pytest.fixture
def fake_article_data():
    # Body must be >=500 chars after process_content() to satisfy
    # MIN_INGEST_BODY_LEN=500 (post-260510-uai short-body fail-fast guard).
    long_paragraph = (
        "This is a Gate1 end-to-end checkpoint resume test fixture body. "
        "It must be long enough to pass the MIN_INGEST_BODY_LEN=500 guard "
        "introduced in quick 260510-uai (source-aware ingest dispatch + "
        "body-length fail-fast for RSS short-body ainsert failures). "
        "Repeated content here pads the body to comfortably exceed the "
        "500-char floor while remaining synthetic test data. "
    ) * 3
    return {
        "method": "ua",
        "title": "Gate1 E2E Article",
        "publish_time": "2026-04-30",
        "content_html": (
            "<html><body><h1>Gate1 E2E</h1>"
            f"<p>{long_paragraph}</p>"
            "<img src='https://cdn.test/a.jpg'/></body></html>"
        ),
        "img_urls": ["https://cdn.test/a.jpg"],
    }


@pytest.fixture
def mock_ingest_deps(monkeypatch, tmp_path, fake_article_data):
    """Mock everything ingest_article touches except lib.checkpoint."""
    import ingest_wechat as iw

    async def fake_ua(url):
        return fake_article_data

    async def fake_none(url):
        return None

    monkeypatch.setattr(iw, "scrape_wechat_ua", fake_ua)
    monkeypatch.setattr(iw, "scrape_wechat_apify", fake_none)
    monkeypatch.setattr(iw, "scrape_wechat_cdp", fake_none)
    monkeypatch.setattr(iw, "scrape_wechat_mcp", fake_none)

    def fake_download(urls, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for i, u in enumerate(urls):
            p = out_dir / f"img_{i}.jpg"
            p.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            result[u] = p
        return result

    monkeypatch.setattr(iw, "download_images", fake_download)

    def fake_filter(url_to_path, min_dim):
        from image_pipeline import FilterStats
        fs = FilterStats(
            input=len(url_to_path),
            kept=len(url_to_path),
            filtered_too_small=0,
            size_read_failed=0,
            timings_ms={},
        )
        return url_to_path, fs

    monkeypatch.setattr(iw, "filter_small_images", fake_filter)

    async def fake_extract(content):
        return []

    monkeypatch.setattr(iw, "extract_entities", fake_extract)

    rag = MagicMock()
    rag.ainsert = AsyncMock()

    # Post-260510-h09 + 260511-lmc: ingest_article calls
    # _verify_doc_processed_or_raise(rag, doc_id) which polls
    # rag.aget_docs_by_ids([doc_id]). Mock returns processed+no-error so the
    # helper returns immediately. Stable-state re-poll (Option A) sleeps for
    # OMNIGRAPH_STABLE_VERIFY_DELAY_S — knock it down to ~0 for fast tests.
    rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "processed", "error_msg": None} for i in ids}
    )
    monkeypatch.setattr(iw, "STABLE_VERIFY_DELAY_S", 0.0)
    monkeypatch.setattr(iw, "PROCESSED_VERIFY_BACKOFF_S", 0.0)

    async def fake_get_rag(flush=True):
        return rag

    monkeypatch.setattr(iw, "get_rag", fake_get_rag)

    async def fake_vision(**kw):
        return None

    monkeypatch.setattr(iw, "_vision_worker_impl", fake_vision)

    imgs_dir = tmp_path / "images"
    imgs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(iw, "BASE_IMAGE_DIR", str(imgs_dir))

    return iw, rag, fake_article_data


@pytest.mark.asyncio
async def test_gate1_fail_at_image_download_then_resume(_checkpoint_base, mock_ingest_deps, sample_url):
    """GATE 1 acceptance: fail at image_download, resume picks up at text_ingest."""
    iw, rag, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    def bad_download(urls, out_dir):
        raise RuntimeError("injected stage 3 failure")

    with patch.object(iw, "download_images", bad_download):
        with pytest.raises(RuntimeError, match="injected stage 3"):
            await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert not _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")

    called = {"ua": 0}

    async def count_ua(url):
        called["ua"] += 1
        return None

    with patch.object(iw, "scrape_wechat_ua", count_ua):
        await iw.ingest_article(sample_url)

    assert called["ua"] == 0, "scrape re-ran despite checkpoint present"
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")
    rag.ainsert.assert_called()


@pytest.mark.asyncio
async def test_fail_at_scrape_leaves_no_stage_checkpoints(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, _, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    async def fail_all(url):
        return None

    with patch.object(iw, "scrape_wechat_ua", fail_all), \
         patch.object(iw, "scrape_wechat_apify", fail_all), \
         patch.object(iw, "scrape_wechat_cdp", fail_all):
        result = await iw.ingest_article(sample_url)

    assert result is None
    assert not _checkpoint_base.has_stage(h, "scrape")


@pytest.mark.asyncio
async def test_fail_at_text_ingest_preserves_stages_1_to_3(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, rag, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    rag.ainsert = AsyncMock(side_effect=RuntimeError("injected text_ingest failure"))
    with pytest.raises(RuntimeError, match="text_ingest"):
        await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")

    rag.ainsert = AsyncMock()
    await iw.ingest_article(sample_url)
    assert _checkpoint_base.has_stage(h, "text_ingest")


def test_batch_skip_guard_predicate(_checkpoint_base, sample_url):
    """Simulate the batch-loop body's guard check."""
    from lib.checkpoint import get_article_hash, has_stage
    h = get_article_hash(sample_url)
    assert not has_stage(h, "text_ingest")
    _checkpoint_base.write_stage(h, "text_ingest")
    assert has_stage(h, "text_ingest"), "guard predicate broken"


def test_batch_ingest_from_spider_contains_skip_guard():
    """Static check: batch_ingest_from_spider.py wires the skip guard."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src = (repo_root / "batch_ingest_from_spider.py").read_text(encoding="utf-8")
    assert "from lib.checkpoint import" in src
    assert "has_stage(ckpt_hash, \"text_ingest\")" in src
    assert "checkpoint-skip: already-ingested" in src


@pytest.mark.asyncio
async def test_metadata_updated_at_advances(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, _, _ = mock_ingest_deps
    t0 = time.time()
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    meta = _checkpoint_base.read_metadata(h)
    assert meta.get("updated_at", 0) >= t0


@pytest.mark.asyncio
async def test_no_tmp_files_after_success(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, _, _ = mock_ingest_deps
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    ckpt_dir = _checkpoint_base.get_checkpoint_dir(h)
    tmp_files = list(ckpt_dir.rglob("*.tmp"))
    assert tmp_files == [], f"leftover .tmp files: {tmp_files}"
