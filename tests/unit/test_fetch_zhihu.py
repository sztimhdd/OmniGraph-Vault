"""Unit tests for enrichment.fetch_zhihu.

All tests are mocked — no live CDP, no live Gemini, no network I/O.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from enrichment.fetch_zhihu import (
    _filter_small_images,
    fetch_zhihu,
    html_to_markdown,
    main,
)


@pytest.fixture(autouse=True)
def _set_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


# ─────────────────────────────────────────────────────────────────────
# Test 1: Small-image filter drops sub-100px, keeps unknowns and large
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_small_image_filter_drops_sub_100px():
    html = """
        <div>
          <img src="http://a/big.jpg" width="400"/>
          <img src="http://b/small.jpg" width="50"/>
          <img src="http://c/unknown.jpg"/>
        </div>
    """
    cleaned, kept = _filter_small_images(html, min_width=100)

    assert "http://a/big.jpg" in kept, "400px image should be kept"
    assert "http://c/unknown.jpg" in kept, "image with no explicit width should be kept"
    assert "http://b/small.jpg" not in kept, "50px image should be filtered"
    assert "small.jpg" not in cleaned, "filtered img tag must be removed from HTML"
    assert "big.jpg" in cleaned, "big image tag must remain in HTML"


@pytest.mark.unit
def test_small_image_filter_respects_data_width():
    """Zhihu uses data-width on some CDN images."""
    html = '<img data-original="http://x/icon.jpg" data-width="32" />'
    _, kept = _filter_small_images(html, min_width=100)
    assert "http://x/icon.jpg" not in kept, "data-width=32 should be filtered"


@pytest.mark.unit
def test_small_image_filter_boundary_exactly_100px_is_kept():
    """PRD §6.2 says 'width < 100px'; exactly 100px must NOT be filtered."""
    html = '<img src="http://x/edge.jpg" width="100"/>'
    _, kept = _filter_small_images(html, min_width=100)
    # width=100 is NOT less than 100, so it should be kept
    assert "http://x/edge.jpg" in kept, "exactly 100px must NOT be filtered (< 100 rule)"


# ─────────────────────────────────────────────────────────────────────
# Test 2: html_to_markdown extracts RichContent-inner, drops outer noise
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_html_to_markdown_extracts_rich_content():
    html = (
        '<html><body>'
        '<div class="RichContent-inner"><p>Main answer text</p></div>'
        '<footer>ads and tracking</footer>'
        '</body></html>'
    )
    md, urls = html_to_markdown(html)

    assert "Main answer text" in md
    assert "ads and tracking" not in md
    assert urls == []


@pytest.mark.unit
def test_html_to_markdown_returns_image_urls():
    html = '<div class="RichContent-inner"><img src="http://x/img.jpg" width="300"/></div>'
    _, urls = html_to_markdown(html)
    assert "http://x/img.jpg" in urls


# ─────────────────────────────────────────────────────────────────────
# Test 3: fetch_zhihu end-to-end with sample fixture
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_fetch_zhihu_writes_expected_artifacts(tmp_path: Path, mocker):
    """End-to-end with mocked HTML fetcher + mocked image pipeline deps."""
    html_fixture = (
        Path(__file__).parent.parent / "fixtures" / "sample_zhihu_page.html"
    ).read_text(encoding="utf-8")

    async def fake_fetch(url):
        return html_fixture

    # Mock image_pipeline network + Gemini calls.
    # Phase 7 D-06: image_pipeline calls lib.generate_sync (Amendment 5
    # unified multimodal) — patch the lib symbol that image_pipeline imports lazily.
    mocker.patch(
        "image_pipeline.requests.get",
        return_value=MagicMock(status_code=200, content=b"FAKE_JPEG"),
    )
    mocker.patch("image_pipeline.time.sleep")
    mocker.patch("lib.generate_sync", return_value="stub description")

    summary = asyncio.run(
        fetch_zhihu(
            "https://zhihu.com/question/1/answer/2",
            wechat_hash="abc123",
            q_idx=0,
            base_dir=tmp_path,
            html_fetcher=fake_fetch,
        )
    )

    assert summary["status"] == "ok"
    assert summary["hash"] == "abc123"
    assert summary["q_idx"] == 0

    out_dir = tmp_path / "abc123" / "0"
    assert (out_dir / "final_content.md").exists(), "zhihu.md / final_content.md must be written"
    assert (out_dir / "metadata.json").exists(), "metadata.json must be written"

    meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["wechat_hash"] == "abc123"
    assert meta["q_idx"] == 0
    assert meta["url"] == "https://zhihu.com/question/1/answer/2"


# ─────────────────────────────────────────────────────────────────────
# Test 4: Image namespacing — URLs must use <hash>/zhihu_<q_idx>/ prefix
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_fetch_zhihu_image_namespacing(tmp_path: Path, mocker):
    """Images in enriched MD must use <hash>/zhihu_<q_idx>/ to avoid
    collision with WeChat images under the same <hash> directory."""
    html = '<div class="RichContent-inner"><img src="http://x/a.jpg" width="300"/></div>'

    async def fake_fetch(url):
        return html

    # Phase 7 D-06: patch lib.generate_sync (the new Amendment 5 multimodal path).
    mocker.patch(
        "image_pipeline.requests.get",
        return_value=MagicMock(status_code=200, content=b"FAKE_JPEG"),
    )
    mocker.patch("image_pipeline.time.sleep")
    mocker.patch("lib.generate_sync", return_value="desc")

    asyncio.run(
        fetch_zhihu(
            "https://zhihu.com/q/1/a/2",
            wechat_hash="hh",
            q_idx=1,
            base_dir=tmp_path,
            html_fetcher=fake_fetch,
        )
    )

    md = (tmp_path / "hh" / "1" / "final_content.md").read_text(encoding="utf-8")
    # Must namespace under hh/zhihu_1/, NOT bare hh/
    assert "http://localhost:8765/hh/zhihu_1/" in md, "image URL must use hh/zhihu_1/ namespace"
    assert "http://localhost:8765/hh/0.jpg" not in md, "bare hh/ namespace must not appear"


# ─────────────────────────────────────────────────────────────────────
# Test 5: CLI error path returns exit code 1 + JSON on stdout
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_error_path_returns_1(tmp_path: Path, mocker, capsys):
    mocker.patch(
        "enrichment.fetch_zhihu._default_cdp_fetch",
        side_effect=RuntimeError("cdp down"),
    )
    rc = main(
        ["https://zhihu.com/q/1/a/2", "--hash", "h", "--q-idx", "0", "--base-dir", str(tmp_path)]
    )
    assert rc == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "error"
    assert "cdp down" in out["error"]


# ─────────────────────────────────────────────────────────────────────
# Test 6: D-03 stdout cap — single-line JSON < 50 KB
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_stdout_under_50kb(tmp_path: Path, mocker, capsys):
    """D-03: stdout must be a single line and under the 50KB Hermes cap."""
    mocker.patch(
        "enrichment.fetch_zhihu._default_cdp_fetch",
        side_effect=RuntimeError("x"),
    )
    main(
        ["https://zhihu.com/q/1/a/2", "--hash", "h", "--q-idx", "0", "--base-dir", str(tmp_path)]
    )
    line = capsys.readouterr().out.strip()
    assert len(line.encode("utf-8")) < 50_000, "stdout must be < 50KB (D-03)"
    assert "\n" not in line, "stdout must be a single line (D-03)"
