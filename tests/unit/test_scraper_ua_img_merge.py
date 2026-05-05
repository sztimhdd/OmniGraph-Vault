"""SCR-06-followup unit tests — UA img_urls merge fix in lib/scraper._scrape_wechat.

Audit ece03ae Mismatch #1: UA layer returns key `img_urls`, but the new
consumer at lib/scraper.py:_scrape_wechat only reads `images` (and only on
the SCR-06 short-circuit branch). UA always takes the process_content branch,
so its `img_urls` are silently discarded — every UA-fallback article loses
images that exist outside the #js_content div.

Legacy contract from ingest_wechat.ingest_article:978 to mirror:
    img_urls = article_data.get("img_urls", []) + _img_urls

Tests are mock-only (no real HTTP, no real Apify/CDP/MCP/UA, no LightRAG).
"""
from __future__ import annotations

import pytest

import ingest_wechat
import lib.scraper


_TEST_URL = "https://mp.weixin.qq.com/s/test"


def _patch_layers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    apify=None,
    cdp=None,
    mcp=None,
    ua=None,
    process_content=None,
) -> None:
    """Patch the 4 cascade layer functions + process_content on ingest_wechat.

    Each layer arg should be either None (returns None async) or a dict.
    """

    async def _make_async(value):
        return value

    def _async_factory(value):
        async def _fn(url):  # noqa: ARG001
            return value
        return _fn

    monkeypatch.setattr(
        ingest_wechat, "scrape_wechat_apify", _async_factory(apify)
    )
    monkeypatch.setattr(
        ingest_wechat, "scrape_wechat_cdp", _async_factory(cdp)
    )
    monkeypatch.setattr(
        ingest_wechat, "scrape_wechat_mcp", _async_factory(mcp)
    )
    monkeypatch.setattr(
        ingest_wechat, "scrape_wechat_ua", _async_factory(ua)
    )

    if process_content is not None:
        monkeypatch.setattr(ingest_wechat, "process_content", process_content)


@pytest.mark.asyncio
async def test_ua_merges_img_urls_with_content_html_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug under fix: UA `img_urls` must be merged with process_content output.

    Legacy ingest_article:978 contract: `result["img_urls"] + _process_imgs`.
    Order: UA-extracted full-page data-src URLs FIRST, then content_html images.
    """
    ua_result = {
        "title": "t",
        "content_html": "<div><img src='c'></div>",
        "img_urls": ["a", "b"],
        "url": _TEST_URL,
        "publish_time": "",
        "method": "ua",
    }
    _patch_layers(
        monkeypatch,
        apify=None,
        cdp=None,
        mcp=None,
        ua=ua_result,
        process_content=lambda html: ("md-body", ["c"]),  # noqa: ARG005
    )

    result = await lib.scraper._scrape_wechat(_TEST_URL)

    assert result.images == ["a", "b", "c"]
    assert result.method == "ua"
    assert result.markdown == "md-body"
    assert result.metadata["title"] == "t"


@pytest.mark.asyncio
async def test_ua_empty_img_urls_yields_only_process_content_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UA returns img_urls=[] → result.images is purely process_content output."""
    ua_result = {
        "title": "t",
        "content_html": "<div><img src='x'><img src='y'></div>",
        "img_urls": [],
        "url": _TEST_URL,
        "publish_time": "",
        "method": "ua",
    }
    _patch_layers(
        monkeypatch,
        apify=None,
        cdp=None,
        mcp=None,
        ua=ua_result,
        process_content=lambda html: ("md", ["x", "y"]),  # noqa: ARG005
    )

    result = await lib.scraper._scrape_wechat(_TEST_URL)

    assert result.images == ["x", "y"]
    assert result.method == "ua"


@pytest.mark.asyncio
async def test_ua_img_urls_only_no_html_imgs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UA returns img_urls=['x'] + content_html with no <img> → images == ['x']."""
    ua_result = {
        "title": "t",
        "content_html": "<div>plain text</div>",
        "img_urls": ["x"],
        "url": _TEST_URL,
        "publish_time": "",
        "method": "ua",
    }
    _patch_layers(
        monkeypatch,
        apify=None,
        cdp=None,
        mcp=None,
        ua=ua_result,
        process_content=lambda html: ("md", []),  # noqa: ARG005
    )

    result = await lib.scraper._scrape_wechat(_TEST_URL)

    assert result.images == ["x"]
    assert result.method == "ua"


@pytest.mark.asyncio
async def test_apify_short_circuit_unchanged_no_img_urls_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression sanity: SCR-06 short-circuit (Apify path) is byte-identical.

    Apify returns markdown only — no content_html, no images, no img_urls.
    Cascade short-circuits on first non-None; cdp/mcp/ua never invoked.
    process_content is NOT called on this branch. result.images defaults to [].
    """
    apify_result = {
        "title": "t",
        "markdown": "# h\n![alt](url1)",
        "publish_time": "",
        "url": _TEST_URL,
        "method": "apify",
    }

    # process_content is patched to raise — confirms it's not called on
    # the Apify SCR-06 short-circuit path.
    def _process_content_must_not_be_called(html):  # noqa: ARG001
        raise AssertionError(
            "process_content called on Apify SCR-06 short-circuit"
        )

    _patch_layers(
        monkeypatch,
        apify=apify_result,
        cdp=None,
        mcp=None,
        ua=None,
        process_content=_process_content_must_not_be_called,
    )

    result = await lib.scraper._scrape_wechat(_TEST_URL)

    assert result.markdown == "# h\n![alt](url1)"
    assert result.images == []
    assert result.method == "apify"
