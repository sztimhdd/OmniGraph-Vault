"""Integration tests: checkpoint skip-on-resume across ingest_article stages.

Every stage transition must be guarded by a has_stage check; this test suite
proves each guard skips correctly when the prior checkpoint is pre-seeded.

All network + LightRAG + Vision calls are mocked — these tests are fast and
deterministic. No live Gemini, no live DeepSeek, no real CDP browser.

Covers Phase 12 CKPT-01 (stage boundaries) + CKPT-03 (resume logic) +
D-SUBDOC (sub_doc_ingest terminal marker).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
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
def _checkpoint_base(monkeypatch, tmp_path):
    """Redirect checkpoint BASE_DIR to tmp via the Plan 12-01 env seam."""
    base = tmp_path / "omonigraph-vault"
    base.mkdir(parents=True)
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(base))
    import lib.checkpoint as ckpt
    importlib.reload(ckpt)
    # ingest_wechat imported the symbols from lib.checkpoint at module load time;
    # rebind them to the reloaded module's functions so the env override takes effect.
    import ingest_wechat
    for _name in (
        "has_stage", "read_stage", "write_stage",
        "write_vision_description", "write_metadata", "list_vision_markers",
    ):
        monkeypatch.setattr(ingest_wechat, _name, getattr(ckpt, _name))
    monkeypatch.setattr(ingest_wechat, "_ckpt_hash_fn", ckpt.get_article_hash)
    yield ckpt


@pytest.fixture
def sample_url():
    return "https://mp.weixin.qq.com/s/test-article-phase-12"


@pytest.fixture
def fake_article_data():
    # Quick 260510-uai: body padded to >MIN_INGEST_BODY_LEN=500 chars so the
    # production body-length fail-fast guard does not reject these fixtures.
    # The previous ~70-char body (sufficient pre-uai) was bypassing the guard
    # introduced for short-body RSS rows that bypassed RSS_SCRAPE_THRESHOLD=100.
    long_body = " ".join(["Body text with enough content to be non-trivial for LightRAG."] * 12)
    return {
        "method": "ua",
        "title": "Test Article",
        "publish_time": "2026-04-30",
        "content_html": (
            f"<html><body><h1>Test</h1><p>{long_body}</p>"
            "<img src='https://cdn.test/img0.jpg'/></body></html>"
        ),
        "img_urls": ["https://cdn.test/img0.jpg"],
        "url": "https://mp.weixin.qq.com/s/test-article-phase-12",
    }


@pytest.fixture
def mock_ingest_deps(monkeypatch, tmp_path, fake_article_data):
    """Mock everything ingest_article touches except the checkpoint lib."""
    import ingest_wechat as iw

    async def fake_ua(url):
        return fake_article_data

    async def fake_apify(url):
        return None

    async def fake_cdp(url):
        return None

    async def fake_mcp(url):
        return None

    monkeypatch.setattr(iw, "scrape_wechat_ua", fake_ua)
    monkeypatch.setattr(iw, "scrape_wechat_apify", fake_apify)
    monkeypatch.setattr(iw, "scrape_wechat_cdp", fake_cdp)
    monkeypatch.setattr(iw, "scrape_wechat_mcp", fake_mcp)

    def fake_download(urls, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for i, u in enumerate(urls):
            p = out_dir / f"img_{i}.jpg"
            # Minimal valid PNG bytes PIL can open (1x1).
            p.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            result[u] = p
        return result

    monkeypatch.setattr(iw, "download_images", fake_download)

    # filter_small_images as identity — all images pass (for testing the checkpoint
    # path, not the filter logic).
    def fake_filter(url_to_path, min_dim):
        from image_pipeline import FilterStats
        stats = FilterStats(
            input=len(url_to_path), kept=len(url_to_path),
            filtered_too_small=0, size_read_failed=0,
            timings_ms={"total_read": 0},
        )
        return url_to_path, stats

    monkeypatch.setattr(iw, "filter_small_images", fake_filter)
    monkeypatch.setattr(iw, "localize_markdown",
                        lambda md, mapping, article_hash="": md)

    async def fake_extract_entities(content):
        return []

    monkeypatch.setattr(iw, "extract_entities", fake_extract_entities)

    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.adelete_by_doc_id = AsyncMock()
    # 2026-05-10 hot-fix (quick 260510-h09): post-ainsert PROCESSED verification
    # helper now retries + raises on failure. Make the mock return PROCESSED for
    # any doc_id so the helper passes on first attempt without sleep.
    rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "PROCESSED"} for i in ids}
    )

    async def fake_get_rag(flush=True):
        return rag

    monkeypatch.setattr(iw, "get_rag", fake_get_rag)

    # Stub the Vision worker so tests don't need Gemini.
    async def fake_vision_worker(**kwargs):
        return None

    monkeypatch.setattr(iw, "_vision_worker_impl", fake_vision_worker)

    monkeypatch.setattr(iw, "save_markdown_with_images", MagicMock())

    # Redirect BASE_IMAGE_DIR so article_dir lands under tmp.
    monkeypatch.setattr(iw, "BASE_IMAGE_DIR", str(tmp_path / "images"))
    os.makedirs(str(tmp_path / "images"), exist_ok=True)

    # Redirect ENTITY_BUFFER_DIR so entity files don't pollute real paths.
    monkeypatch.setattr(iw, "ENTITY_BUFFER_DIR", str(tmp_path / "entity_buffer"))

    return iw, rag, fake_article_data


# ---------------------------------------------------------------------------
# Task 2 tests — skip-on-resume per stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_run_writes_all_five_stages(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    """Fresh run: all 4 early stages + sub_doc_ingest (no images → immediate
    marker) must be written after one ingest_article call."""
    iw, rag, _ = mock_ingest_deps
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")
    # Vision worker is stubbed (no per-image markers written); images were
    # present so the ingest_article code path spawns the (stubbed) worker —
    # no sub_doc_ingest marker is expected because the stub doesn't write one.
    # That's a separate test (test_vision_worker_writes_sub_doc_ingest_marker).


@pytest.mark.asyncio
async def test_skip_scrape_when_cached(
    _checkpoint_base, mock_ingest_deps, sample_url, caplog
):
    """scrape checkpoint present → scrape_wechat_* not called; resume parses cached HTML."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])

    called = {"ua": 0, "apify": 0, "cdp": 0, "mcp": 0}

    async def boom_ua(url):
        called["ua"] += 1
        return None

    async def boom_apify(url):
        called["apify"] += 1
        return None

    async def boom_cdp(url):
        called["cdp"] += 1
        return None

    async def boom_mcp(url):
        called["mcp"] += 1
        return None

    with patch.object(iw, "scrape_wechat_ua", boom_ua), \
         patch.object(iw, "scrape_wechat_apify", boom_apify), \
         patch.object(iw, "scrape_wechat_cdp", boom_cdp), \
         patch.object(iw, "scrape_wechat_mcp", boom_mcp):
        with caplog.at_level(logging.INFO, logger="ingest_wechat"):
            await iw.ingest_article(sample_url)

    assert called == {"ua": 0, "apify": 0, "cdp": 0, "mcp": 0}
    assert "checkpoint hit: scrape" in caplog.text


@pytest.mark.asyncio
async def test_skip_classify_when_checkpoint_present(
    _checkpoint_base, mock_ingest_deps, sample_url, caplog
):
    """classify checkpoint present → placeholder read, not re-generated."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    seeded_classify = {
        "depth": 2, "topics": ["test-topic"], "rationale": "seeded",
        "model": "test-model", "timestamp": 123.0,
    }
    _checkpoint_base.write_stage(h, "classify", seeded_classify)

    with caplog.at_level(logging.INFO, logger="ingest_wechat"):
        await iw.ingest_article(sample_url)

    assert "checkpoint hit: classify" in caplog.text
    # Confirm the seeded data is still on disk (not overwritten).
    assert _checkpoint_base.read_stage(h, "classify") == seeded_classify


@pytest.mark.asyncio
async def test_skip_image_download_when_manifest_exists(
    _checkpoint_base, mock_ingest_deps, sample_url, tmp_path, caplog
):
    """image_download manifest present → download_images not called."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {
        "depth": None, "topics": [], "rationale": "seeded",
        "model": None, "timestamp": 0,
    })
    # Seed a manifest pointing to a real file so url_to_path reconstruction works.
    p = tmp_path / "cached-img.jpg"
    p.write_bytes(b"fakejpegbytes")
    _checkpoint_base.write_stage(h, "image_download", [
        {
            "url": "https://cdn.test/img0.jpg",
            "local_path": str(p),
            "dimensions": [400, 400],
            "filter_reason": None,
        },
    ])

    called = {"download": 0}

    def boom_download(urls, out_dir):
        called["download"] += 1
        return {}

    with patch.object(iw, "download_images", boom_download):
        with caplog.at_level(logging.INFO, logger="ingest_wechat"):
            await iw.ingest_article(sample_url)

    assert called["download"] == 0
    assert "checkpoint hit: image_download" in caplog.text


@pytest.mark.asyncio
async def test_skip_text_ingest_when_done_marker(
    _checkpoint_base, mock_ingest_deps, sample_url, caplog
):
    """text_ingest marker present → rag.ainsert(parent) not called."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {
        "depth": None, "topics": [], "rationale": "seeded",
        "model": None, "timestamp": 0,
    })
    _checkpoint_base.write_stage(h, "image_download", [])
    _checkpoint_base.write_stage(h, "text_ingest")

    rag.ainsert.reset_mock()
    with caplog.at_level(logging.INFO, logger="ingest_wechat"):
        await iw.ingest_article(sample_url)

    rag.ainsert.assert_not_called()
    assert "checkpoint hit: text_ingest" in caplog.text


@pytest.mark.asyncio
async def test_failure_at_image_download_preserves_prior_checkpoints(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    """RuntimeError in download_images propagates but leaves scrape + classify markers."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    def bad_download(urls, out_dir):
        raise RuntimeError("simulated download failure")

    with patch.object(iw, "download_images", bad_download):
        with pytest.raises(RuntimeError, match="simulated"):
            await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert not _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")


@pytest.mark.asyncio
async def test_resume_after_image_download_failure(
    _checkpoint_base, mock_ingest_deps, sample_url, caplog
):
    """After a failed image_download run, re-running must skip scrape + classify."""
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    # Seed the post-first-failure state.
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {
        "depth": None, "topics": [], "rationale": "seeded",
        "model": None, "timestamp": 0,
    })

    called = {"ua": 0}

    async def count_ua(url):
        called["ua"] += 1
        return art

    with patch.object(iw, "scrape_wechat_ua", count_ua):
        with caplog.at_level(logging.INFO, logger="ingest_wechat"):
            await iw.ingest_article(sample_url)

    assert called["ua"] == 0
    assert "checkpoint hit: scrape" in caplog.text
    assert "checkpoint hit: classify" in caplog.text
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")


@pytest.mark.asyncio
async def test_vision_worker_writes_per_image_checkpoints(
    _checkpoint_base, sample_url, tmp_path
):
    """_vision_worker_impl(ckpt_hash=...) writes 05_vision/{image_id}.json per success."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    p1 = tmp_path / "img_1.jpg"; p1.write_bytes(b"\xff")
    url_to_path = {"https://a/0": p0, "https://a/1": p1}

    rag = MagicMock(); rag.ainsert = AsyncMock()

    def fake_describe(paths):
        return {p0: "description A", p1: "description B"}

    from image_pipeline import FilterStats
    fs = FilterStats(
        input=2, kept=2, filtered_too_small=0,
        size_read_failed=0, timings_ms={"total_read": 0},
    )

    with patch("ingest_wechat.describe_images", fake_describe), \
         patch("ingest_wechat.get_last_describe_stats", MagicMock(return_value=None)), \
         patch("ingest_wechat.emit_batch_complete", MagicMock()):
        await iw._vision_worker_impl(
            rag=rag,
            article_hash="legacy_hash",
            url_to_path=url_to_path,
            title="T",
            filter_stats=fs,
            download_input_count=2,
            download_failed=0,
            ckpt_hash=h,
        )

    vision_dir = _checkpoint_base.get_checkpoint_dir(h) / "05_vision"
    assert (vision_dir / "img_0.json").exists()
    assert (vision_dir / "img_1.json").exists()
    content_0 = json.loads((vision_dir / "img_0.json").read_text(encoding="utf-8"))
    assert content_0["description"] == "description A"


@pytest.mark.asyncio
async def test_vision_worker_writes_sub_doc_ingest_marker_on_success(
    _checkpoint_base, sample_url, tmp_path
):
    """D-SUBDOC: after sub-doc ainsert completes, 06_sub_doc_ingest.done is written."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    url_to_path = {"https://a/0": p0}

    rag = MagicMock(); rag.ainsert = AsyncMock()

    from image_pipeline import FilterStats
    fs = FilterStats(
        input=1, kept=1, filtered_too_small=0,
        size_read_failed=0, timings_ms={"total_read": 0},
    )

    with patch("ingest_wechat.describe_images",
               MagicMock(return_value={p0: "desc X"})), \
         patch("ingest_wechat.get_last_describe_stats", MagicMock(return_value=None)), \
         patch("ingest_wechat.emit_batch_complete", MagicMock()):
        await iw._vision_worker_impl(
            rag=rag,
            article_hash="legacy_hash",
            url_to_path=url_to_path,
            title="T",
            filter_stats=fs,
            download_input_count=1,
            download_failed=0,
            ckpt_hash=h,
        )

    assert _checkpoint_base.has_stage(h, "sub_doc_ingest")


@pytest.mark.asyncio
async def test_vision_worker_writes_sub_doc_ingest_marker_when_all_empty(
    _checkpoint_base, sample_url, tmp_path
):
    """D-SUBDOC: zero Vision successes → marker written immediately (no-op satisfied)."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    url_to_path = {"https://a/0": p0}

    rag = MagicMock(); rag.ainsert = AsyncMock()

    from image_pipeline import FilterStats
    fs = FilterStats(
        input=1, kept=1, filtered_too_small=0,
        size_read_failed=0, timings_ms={"total_read": 0},
    )

    with patch("ingest_wechat.describe_images",
               MagicMock(return_value={p0: ""})), \
         patch("ingest_wechat.get_last_describe_stats", MagicMock(return_value=None)), \
         patch("ingest_wechat.emit_batch_complete", MagicMock()):
        await iw._vision_worker_impl(
            rag=rag,
            article_hash="legacy_hash",
            url_to_path=url_to_path,
            title="T",
            filter_stats=fs,
            download_input_count=1,
            download_failed=0,
            ckpt_hash=h,
        )

    # rag.ainsert must NOT have been called (D-10.07 skip-if-all-empty).
    assert rag.ainsert.await_count == 0
    # Marker written anyway to prevent resume loop.
    assert _checkpoint_base.has_stage(h, "sub_doc_ingest")


@pytest.mark.asyncio
async def test_vision_checkpoint_write_failure_is_swallowed(
    _checkpoint_base, sample_url, tmp_path, caplog
):
    """If write_vision_description raises, the Vision worker must still complete."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    rag = MagicMock(); rag.ainsert = AsyncMock()

    from image_pipeline import FilterStats
    fs = FilterStats(
        input=1, kept=1, filtered_too_small=0,
        size_read_failed=0, timings_ms={"total_read": 0},
    )

    def bad_write(*a, **kw):
        raise IOError("disk full")

    with patch("ingest_wechat.describe_images",
               MagicMock(return_value={p0: "desc"})), \
         patch("ingest_wechat.get_last_describe_stats", MagicMock(return_value=None)), \
         patch("ingest_wechat.emit_batch_complete", MagicMock()), \
         patch("ingest_wechat.write_vision_description", bad_write):
        with caplog.at_level(logging.WARNING, logger="ingest_wechat"):
            # Must NOT raise.
            await iw._vision_worker_impl(
                rag=rag,
                article_hash="legacy_hash",
                url_to_path={"https://a/0": p0},
                title="T",
                filter_stats=fs,
                download_input_count=1,
                download_failed=0,
                ckpt_hash=h,
            )
    assert "vision checkpoint write failed" in caplog.text
