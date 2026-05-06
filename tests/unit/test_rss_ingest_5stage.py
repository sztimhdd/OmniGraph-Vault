"""Tests RIN-01, RIN-02, RIN-03, RIN-04, RIN-05, RIN-06 from Phase 20 REQUIREMENTS.md.

Verifies the contract that Plan 20-02 must deliver:
  RIN-01: _ingest_one_article writes 5 stage checkpoint markers
  RIN-02: download_images accepts referer kwarg; passes Referer header
  RIN-03: rss_ingest._pending_doc_ids tracker is isolated from ingest_wechat._PENDING_DOC_IDS
  RIN-04: asyncio.TimeoutError triggers rollback (adelete_by_doc_id x2) + enriched unchanged
  RIN-05: vision sub-doc ainsert uses ids=["rss-{id}_images"] and # Images for {title} header
  RIN-06: _IMAGE_URL_PATTERN matches localize_markdown output (contract lock, PASSES today)

Currently mostly RED because enrichment/rss_ingest.py lacks _ingest_one_article,
_pending_doc_ids, and image_pipeline.download_images lacks referer parameter.
Plan 20-02 turns all RED tests GREEN.
test_image_url_pattern_match (RIN-06) should PASS today — it locks an existing contract.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from lib.checkpoint import get_article_hash, has_stage, STAGE_FILES


# ---------------------------------------------------------------------------
# Test 1: RIN-01 — _ingest_one_article writes all 5 stage checkpoint markers
# ---------------------------------------------------------------------------

async def test_5_stage_checkpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RIN-01: _ingest_one_article must write 5 stage checkpoint markers.

    Currently RED: _ingest_one_article does not exist in enrichment/rss_ingest.
    Plan 20-02 creates the 5-stage function.
    """
    import lib.checkpoint as ckpt_mod
    monkeypatch.setattr(ckpt_mod, "BASE_DIR", tmp_path)

    # Minimal in-memory rss_articles row
    article_url = "https://example.com/rss-article-1"
    article_hash = get_article_hash(article_url)
    row = {
        "id": 1,
        "title": "Test RSS Article",
        "url": article_url,
        "body": "Full body content for test article " * 20,
        "depth": 2,
        "topics": '["Agent"]',
        "classify_rationale": "test",
        "enriched": 0,
    }

    # Mock rag with async methods
    rag = MagicMock()
    rag.ainsert = AsyncMock(return_value="stub-track-id")
    rag.aget_docs_by_ids = AsyncMock(return_value={
        f"rss-{row['id']}": MagicMock(status="PROCESSED")
    })
    rag.adelete_by_doc_id = AsyncMock(return_value=MagicMock(status="success"))

    # Mock image pipeline
    fake_image_path = tmp_path / "0.jpg"
    fake_image_path.touch()
    monkeypatch.setattr(
        "image_pipeline.download_images",
        lambda urls, dest_dir, **kwargs: {"http://example.com/1.jpg": fake_image_path},
    )
    monkeypatch.setattr(
        "image_pipeline.describe_images",
        lambda url_to_path, **kwargs: {fake_image_path: "mock image description"},
    )
    monkeypatch.setattr(
        "image_pipeline.localize_markdown",
        lambda md, url_to_local, **kwargs: md,
    )

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER DEFAULT 1,
            title TEXT,
            url TEXT,
            body TEXT,
            depth INTEGER,
            topics TEXT,
            classify_rationale TEXT,
            enriched INTEGER DEFAULT 0,
            body_scraped_at TEXT
        );
        INSERT INTO rss_articles (id, title, url, body, depth, topics, enriched)
        VALUES (1, 'Test RSS Article', 'https://example.com/rss-article-1',
                'Full body content for test article', 2, '["Agent"]', 0);
        """
    )

    from enrichment.rss_ingest import _ingest_one_article  # noqa: F401 — RED if missing

    await _ingest_one_article(rag, conn, row)

    # RIN-01: 5 stages must have checkpoint markers
    assert has_stage(article_hash, "scrape"), "01_scrape.html must exist after _ingest_one_article"
    assert has_stage(article_hash, "classify"), "02_classify.json must exist"
    assert has_stage(article_hash, "image_download"), "03_images/manifest.json must exist"
    assert has_stage(article_hash, "text_ingest"), "04_text_ingest.done must exist"

    # vision_worker stage: directory must exist (may or may not have .json files
    # depending on whether async worker completed — but dir should be created)
    vision_dir = tmp_path / "checkpoints" / article_hash / "05_vision"
    assert vision_dir.is_dir(), (
        "05_vision/ directory must exist after _ingest_one_article "
        "(RIN-01 checkpoint stage 5)"
    )


# ---------------------------------------------------------------------------
# Test 2: RIN-02 — download_images accepts referer kwarg, passes Referer header
# ---------------------------------------------------------------------------

def test_download_images_referer_svg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """RIN-02/RIN-03: download_images must accept referer kwarg and skip SVG.

    Currently RED: image_pipeline.download_images signature is:
      download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]
    It does NOT accept a `referer` keyword argument.
    Plan 20-02 D-20.08/09 adds: referer: str | None = None + SVG content-type skip.
    """
    import requests as req

    captured_requests: list[dict] = []

    def mock_get(url: str, **kwargs) -> MagicMock:
        captured_requests.append({"url": url, "kwargs": kwargs})
        mock_resp = MagicMock()
        if "svg" in url:
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Type": "image/svg+xml"}
            mock_resp.content = b"<svg/>"
        else:
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Type": "image/jpeg"}
            mock_resp.content = b"\xff\xd8\xff\xe0FAKE"
        return mock_resp

    monkeypatch.setattr(req, "get", mock_get)

    import image_pipeline

    result = image_pipeline.download_images(
        ["http://x.com/diagram.svg", "http://x.com/photo.jpg"],
        tmp_path,
        referer="https://substack.com/article/foo",
    )

    # RIN-02: Referer header must be passed in the request
    assert len(captured_requests) >= 1, "Expected at least one HTTP request"
    for req_info in captured_requests:
        headers = req_info["kwargs"].get("headers", {})
        assert "Referer" in headers, (
            f"Expected 'Referer' header in request to {req_info['url']}, "
            "got headers: {headers}. Plan 20-02 D-20.08: add referer param."
        )
        assert headers["Referer"] == "https://substack.com/article/foo"

    # RIN-02: SVG must be excluded from the result
    result_filenames = [p.name for p in result.values()]
    assert not any("svg" in url for url in result), (
        "SVG URLs must be filtered out. Plan 20-02 D-20.09: skip image/svg content-type."
    )
    # Only the JPEG should be in the result
    assert len(result) == 1, (
        f"Expected 1 entry (jpg only, svg skipped), got {len(result)}. "
        "Plan 20-02 D-20.09: SVG filter not yet implemented."
    )


# ---------------------------------------------------------------------------
# Test 3: RIN-03 — _pending_doc_ids tracker is isolated per-module
# ---------------------------------------------------------------------------

def test_pending_doc_ids_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """RIN-03: rss_ingest._pending_doc_ids must be a separate dict from ingest_wechat._PENDING_DOC_IDS.

    Per D-20.11: each arm has its own tracker keyed by doc_id namespace.
    Currently RED: enrichment/rss_ingest does not have _pending_doc_ids yet.
    Plan 20-02 adds it.
    """
    from enrichment.rss_ingest import _pending_doc_ids as rss_tracker  # RED if missing
    from ingest_wechat import _PENDING_DOC_IDS as kol_tracker

    # Must be different dict objects (D-20.11: per-module, not shared)
    assert rss_tracker is not kol_tracker, (
        "rss_ingest._pending_doc_ids must be a separate dict from "
        "ingest_wechat._PENDING_DOC_IDS. D-20.11: per-module trackers."
    )

    # Mutating one must not affect the other
    original_kol_len = len(kol_tracker)
    rss_tracker["rss-test-123"] = "rss-123"
    assert "rss-test-123" not in kol_tracker, (
        "Mutation of rss_tracker must not appear in kol_tracker."
    )
    assert len(kol_tracker) == original_kol_len

    # Cleanup
    rss_tracker.pop("rss-test-123", None)


# ---------------------------------------------------------------------------
# Test 4: RIN-04/RIN-05 — timeout triggers rollback; enriched stays 0
# ---------------------------------------------------------------------------

async def test_timeout_rollback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """RIN-04/D-20.06/D-20.12: asyncio.TimeoutError triggers rollback.

    On TimeoutError from ainsert:
      1) adelete_by_doc_id("rss-42") called
      2) adelete_by_doc_id("rss-42_images") called
      3) rss_articles.enriched stays 0 (NOT set to 2 or -1)

    Currently RED: _ingest_one_article does not exist.
    Plan 20-02 implements the rollback path.
    """
    import lib.checkpoint as ckpt_mod
    monkeypatch.setattr(ckpt_mod, "BASE_DIR", tmp_path)

    article_url = "https://example.com/rss-timeout-42"
    row = {
        "id": 42,
        "title": "Timeout Test Article",
        "url": article_url,
        "body": "body content " * 50,
        "depth": 2,
        "topics": '["Agent"]',
        "classify_rationale": "test",
        "enriched": 0,
    }

    rag = MagicMock()
    rag.ainsert = AsyncMock(side_effect=asyncio.TimeoutError("simulated timeout"))
    rag.adelete_by_doc_id = AsyncMock(return_value=MagicMock(status="success"))
    rag.aget_docs_by_ids = AsyncMock(return_value={})

    # Image pipeline mocks — return empty to avoid vision path
    monkeypatch.setattr("image_pipeline.download_images", lambda *a, **kw: {})
    monkeypatch.setattr("image_pipeline.describe_images", lambda *a, **kw: {})
    monkeypatch.setattr("image_pipeline.localize_markdown", lambda md, *a, **kw: md)

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER DEFAULT 1,
            title TEXT,
            url TEXT,
            body TEXT,
            depth INTEGER,
            topics TEXT,
            classify_rationale TEXT,
            enriched INTEGER DEFAULT 0
        );
        INSERT INTO rss_articles (id, title, url, body, depth, topics, enriched)
        VALUES (42, 'Timeout Test Article', 'https://example.com/rss-timeout-42',
                'body content', 2, '["Agent"]', 0);
        """
    )

    from enrichment.rss_ingest import _ingest_one_article  # noqa: F401 — RED if missing

    # Must NOT raise on TimeoutError — it should be handled
    await _ingest_one_article(rag, conn, row)

    # D-20.06 + D-20.12: rollback calls adelete_by_doc_id for both doc IDs
    delete_calls = [str(c) for c in rag.adelete_by_doc_id.call_args_list]
    called_ids = [c.args[0] if c.args else c.kwargs.get("doc_id") for c in rag.adelete_by_doc_id.call_args_list]

    assert "rss-42" in called_ids, (
        f"Expected adelete_by_doc_id('rss-42') on timeout rollback, "
        f"got calls: {called_ids}. D-20.06."
    )
    assert "rss-42_images" in called_ids, (
        f"Expected adelete_by_doc_id('rss-42_images') on timeout rollback, "
        f"got calls: {called_ids}. D-20.06."
    )

    # D-20.12: enriched must still be 0 after rollback (not -1, not 2)
    row_after = conn.execute(
        "SELECT enriched FROM rss_articles WHERE id=42"
    ).fetchone()
    assert row_after[0] == 0, (
        f"Expected enriched=0 after timeout rollback, got {row_after[0]}. "
        "D-20.12: leave enriched at prior value so next batch retries."
    )

    # D-20.12: drain helper must be called with cap_seconds=120.0
    # (verified indirectly via the timeout path — exact drain call verified in integration)


# ---------------------------------------------------------------------------
# Test 5: RIN-05 — vision sub-doc has correct ids and header format
# ---------------------------------------------------------------------------

async def test_vision_subdoc_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """RIN-05: vision sub-doc ainsert uses ids=['rss-99_images'] with correct content format.

    Sub-doc format mirrors ingest_wechat._vision_worker_impl:
      # Images for {title}
      - [image N]: {desc}  (http://localhost:8765/{hash}/{filename})

    Currently RED: _ingest_one_article does not exist.
    Plan 20-02 implements the vision worker with rss-{id}_images doc_id.
    """
    import lib.checkpoint as ckpt_mod
    monkeypatch.setattr(ckpt_mod, "BASE_DIR", tmp_path)

    article_url = "https://example.com/rss-vision-99"
    article_hash = get_article_hash(article_url)
    row = {
        "id": 99,
        "title": "Vision Test Article",
        "url": article_url,
        "body": "body content with image reference " * 20,
        "depth": 2,
        "topics": '["Agent"]',
        "classify_rationale": "test",
        "enriched": 0,
    }

    ainsert_calls: list[dict] = []

    async def capture_ainsert(content: str, ids: list[str] | None = None, **kwargs) -> str:
        ainsert_calls.append({"content": content, "ids": ids})
        return "stub"

    rag = MagicMock()
    rag.ainsert = capture_ainsert
    rag.aget_docs_by_ids = AsyncMock(return_value={
        "rss-99": MagicMock(status="PROCESSED")
    })
    rag.adelete_by_doc_id = AsyncMock(return_value=MagicMock(status="success"))

    # Provide one fake image so vision sub-doc path fires
    fake_img_path = tmp_path / "0.jpg"
    fake_img_path.touch()
    fake_url = "http://cdn.example.com/img1.jpg"
    local_url = f"http://localhost:8765/{article_hash}/0.jpg"

    monkeypatch.setattr(
        "image_pipeline.download_images",
        lambda urls, dest_dir, **kwargs: {fake_url: fake_img_path},
    )
    monkeypatch.setattr(
        "image_pipeline.describe_images",
        lambda url_to_path, **kwargs: {fake_img_path: "A diagram showing agent flow"},
    )
    monkeypatch.setattr(
        "image_pipeline.localize_markdown",
        lambda md, url_to_local, base_url="", article_hash="", **kw: md.replace(fake_url, local_url),
    )

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        f"""
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER DEFAULT 1,
            title TEXT,
            url TEXT,
            body TEXT,
            depth INTEGER,
            topics TEXT,
            classify_rationale TEXT,
            enriched INTEGER DEFAULT 0
        );
        INSERT INTO rss_articles (id, title, url, body, depth, topics, enriched)
        VALUES (99, 'Vision Test Article', 'https://example.com/rss-vision-99',
                'body content with image reference ![](http://cdn.example.com/img1.jpg)', 2, '["Agent"]', 0);
        """
    )

    from enrichment.rss_ingest import _ingest_one_article  # noqa: F401 — RED if missing

    await _ingest_one_article(rag, conn, row)

    # RIN-05: find the vision sub-doc ainsert call
    vision_calls = [c for c in ainsert_calls if c["ids"] and any("_images" in i for i in c["ids"])]
    assert vision_calls, (
        f"Expected ainsert called with ids containing '_images'. "
        f"All ainsert calls: {[(c['ids'], c['content'][:50]) for c in ainsert_calls]}. "
        "RIN-05: vision sub-doc must be inserted as 'rss-99_images'."
    )

    sub_doc = vision_calls[0]
    assert sub_doc["ids"] == ["rss-99_images"], (
        f"Expected ids=['rss-99_images'], got {sub_doc['ids']}. "
        "D-20.05: RSS sub-doc id format is rss-{article_id}_images."
    )

    content = sub_doc["content"]
    assert content.startswith("# Images for "), (
        f"Vision sub-doc must start with '# Images for ', got: {content[:60]!r}. "
        "RIN-05: mirrors ingest_wechat._vision_worker_impl format."
    )
    assert "Vision Test Article" in content, (
        f"Vision sub-doc must contain the article title. content[:80]={content[:80]!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: RIN-06 — _IMAGE_URL_PATTERN matches localize_markdown output (contract lock)
# ---------------------------------------------------------------------------

def test_image_url_pattern_match() -> None:
    """RIN-06: _IMAGE_URL_PATTERN matches the URL format produced by localize_markdown.

    This test should PASS today — it locks the existing contract so Plan 20-02
    cannot accidentally break it. Both functions already exist.
    """
    from lib.lightrag_embedding import _IMAGE_URL_PATTERN
    from image_pipeline import localize_markdown

    # Verify pattern is exactly what is expected
    assert _IMAGE_URL_PATTERN.pattern == r"http://localhost:8765/\S+?\.(?:jpg|jpeg|png)", (
        f"_IMAGE_URL_PATTERN pattern changed: {_IMAGE_URL_PATTERN.pattern!r}. "
        "Plan 20-02 must NOT change lib/lightrag_embedding._IMAGE_URL_PATTERN."
    )

    # localize_markdown replaces remote URL with localhost URL
    test_hash = "abc1234567890def"
    url_to_local = {"http://cdn.x.com/foo.jpg": Path("/tmp/0.jpg")}
    md_input = "![Alt text](http://cdn.x.com/foo.jpg)"

    result = localize_markdown(
        md_input,
        url_to_local,
        base_url="http://localhost:8765",
        article_hash=test_hash,
    )

    matches = _IMAGE_URL_PATTERN.findall(result)
    assert len(matches) == 1, (
        f"Expected exactly 1 match for _IMAGE_URL_PATTERN in localized markdown, "
        f"got {len(matches)}. result={result!r}"
    )
    assert matches[0] == f"http://localhost:8765/{test_hash}/0.jpg", (
        f"Pattern matched wrong URL: {matches[0]!r}. "
        f"Expected 'http://localhost:8765/{test_hash}/0.jpg'."
    )
