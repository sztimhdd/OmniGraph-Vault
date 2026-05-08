"""Quick 260508-ev2 F1b: tests for _scrape_wechat cascade order + SCRAPE_CASCADE.

Verifies lib.scraper._scrape_wechat():
  1. default order (no env)         → ua, apify, cdp, mcp
  2. env=ua                         → ua only
  3. env=ua,apify                   → ua, apify only
  4. env=invalid                    → fallback to default + warning
  5. first success short-circuits   → ua wins → apify/cdp/mcp not called

All cases mock the 4 scrape_wechat_* functions on ingest_wechat. ZERO live calls.
"""

import logging

import pytest
from unittest.mock import AsyncMock

import ingest_wechat
import lib.scraper as scraper


def _attach_mocks(monkeypatch, *, ua=None, apify=None, cdp=None, mcp=None,
                  call_order=None):
    """Patch the four scrape_wechat_* funcs so we can observe call order.

    Each None-returning mock represents a "miss" — _scrape_wechat will then
    cascade to the next layer. Use a non-None return on one mock to test
    short-circuiting.
    """
    def _mk(name, retval):
        async def _impl(url):
            if call_order is not None:
                call_order.append(name)
            return retval
        return AsyncMock(side_effect=_impl)

    monkeypatch.setattr(ingest_wechat, "scrape_wechat_ua",
                        _mk("ua", ua))
    monkeypatch.setattr(ingest_wechat, "scrape_wechat_apify",
                        _mk("apify", apify))
    monkeypatch.setattr(ingest_wechat, "scrape_wechat_cdp",
                        _mk("cdp", cdp))
    monkeypatch.setattr(ingest_wechat, "scrape_wechat_mcp",
                        _mk("mcp", mcp))


@pytest.mark.asyncio
async def test_default_order_ua_apify_cdp_mcp(monkeypatch):
    """No SCRAPE_CASCADE env → default order ua, apify, cdp, mcp."""
    monkeypatch.delenv("SCRAPE_CASCADE", raising=False)
    call_order: list[str] = []
    # All return None → cascade exhausts; gives us the full order.
    _attach_mocks(monkeypatch, call_order=call_order)
    await scraper._scrape_wechat("https://mp.weixin.qq.com/s/abc")
    assert call_order == ["ua", "apify", "cdp", "mcp"], (
        f"expected default ua,apify,cdp,mcp — got {call_order}"
    )


@pytest.mark.asyncio
async def test_env_subset_ua_only(monkeypatch):
    """SCRAPE_CASCADE=ua → only ua invoked."""
    monkeypatch.setenv("SCRAPE_CASCADE", "ua")
    call_order: list[str] = []
    _attach_mocks(monkeypatch, call_order=call_order)
    await scraper._scrape_wechat("https://mp.weixin.qq.com/s/abc")
    assert call_order == ["ua"], (
        f"expected only ua to be called — got {call_order}"
    )


@pytest.mark.asyncio
async def test_env_subset_ua_apify(monkeypatch):
    """SCRAPE_CASCADE=ua,apify → exactly those 2 in order; cdp/mcp untouched."""
    monkeypatch.setenv("SCRAPE_CASCADE", "ua,apify")
    call_order: list[str] = []
    _attach_mocks(monkeypatch, call_order=call_order)
    await scraper._scrape_wechat("https://mp.weixin.qq.com/s/abc")
    assert call_order == ["ua", "apify"], (
        f"expected only ua then apify — got {call_order}"
    )


@pytest.mark.asyncio
async def test_env_invalid_falls_back(monkeypatch, caplog):
    """SCRAPE_CASCADE=invalid → warning + default order."""
    monkeypatch.setenv("SCRAPE_CASCADE", "invalid")
    call_order: list[str] = []
    _attach_mocks(monkeypatch, call_order=call_order)
    with caplog.at_level(logging.WARNING, logger="lib.scraper"):
        await scraper._scrape_wechat("https://mp.weixin.qq.com/s/abc")
    assert call_order == ["ua", "apify", "cdp", "mcp"], (
        f"invalid env should fall back to default — got {call_order}"
    )
    warning_text = " ".join(r.getMessage() for r in caplog.records
                            if r.levelno == logging.WARNING)
    assert "SCRAPE_CASCADE" in warning_text and "invalid" in warning_text, (
        "expected fallback warning mentioning SCRAPE_CASCADE and 'invalid'; "
        f"got: {warning_text!r}"
    )


@pytest.mark.asyncio
async def test_first_success_short_circuits(monkeypatch):
    """ua returns valid result → apify/cdp/mcp NOT invoked."""
    monkeypatch.delenv("SCRAPE_CASCADE", raising=False)
    call_order: list[str] = []
    ua_payload = {
        "title": "Test",
        "content_html": "<p>" + "x" * 600 + "</p>",
        "publish_time": "",
        "url": "https://mp.weixin.qq.com/s/abc",
        "method": "ua",
    }
    _attach_mocks(
        monkeypatch,
        ua=ua_payload,
        call_order=call_order,
    )
    result = await scraper._scrape_wechat("https://mp.weixin.qq.com/s/abc")
    assert call_order == ["ua"], (
        f"first-success should short-circuit — got {call_order}"
    )
    assert result.method == "ua"
    assert not result.summary_only
