"""Phase 19 SCR-01..05 unit tests. Mock-only (Cisco Umbrella blocks live HTTPS)."""
from dataclasses import FrozenInstanceError, fields

import pytest

from lib.scraper import (
    ScrapeResult,
    _BACKOFF_SCHEDULE_S,
    _LOGIN_WALL_PATTERNS,
    _fetch_with_backoff_on_429,
    _passes_quality_gate,
    _route,
    _scrape_generic,
    scrape_url,
)


# SCR-01 -----------------------------------------------------------------

def test_import_and_dataclass_shape():
    expected = {"markdown", "images", "metadata", "method",
                "summary_only", "content_html"}
    got = {f.name for f in fields(ScrapeResult)}
    assert got == expected, f"ScrapeResult fields mismatch: {got}"
    # frozen=True enforcement
    r = ScrapeResult(markdown="x")
    with pytest.raises(FrozenInstanceError):
        r.markdown = "y"  # type: ignore[misc]
    # content_html defaults to None
    assert r.content_html is None


# SCR-03 -----------------------------------------------------------------

def test_route_dispatch():
    assert _route("https://mp.weixin.qq.com/s/abc", None) == "wechat"
    assert _route("https://arxiv.org/abs/2401.00001", None) == "arxiv_abs"
    assert _route("https://arxiv.org/pdf/2401.00001.pdf", None) == "arxiv_pdf"
    assert _route("https://medium.com/foo/bar", None) == "generic"
    # site_hint override — host is medium.com, but wechat hint wins
    assert _route("https://medium.com/foo/bar", site_hint="wechat") == "wechat"


# SCR-04 -----------------------------------------------------------------

def test_quality_gate():
    # None / empty fails
    assert _passes_quality_gate(None) is False
    assert _passes_quality_gate("") is False
    # 499 chars fails (below 500 threshold)
    assert _passes_quality_gate("a" * 499) is False
    # 500 chars + no login-wall keyword passes
    assert _passes_quality_gate("a" * 500) is True
    # Login-wall keyword (English, mid-text, case-insensitive) fails
    content = "a" * 250 + " please Sign in to continue " + "a" * 250
    assert _passes_quality_gate(content) is False
    # Login-wall keyword (Chinese) fails
    content_cn = "a" * 250 + " 请先登录 再查看 " + "a" * 250
    assert _passes_quality_gate(content_cn) is False
    # Sanity: 16 patterns defined
    assert len(_LOGIN_WALL_PATTERNS) == 16


# SCR-05 -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_backoff_429(mocker):
    """Mock requests.get to sequence 429 × 3 then 200, assert correct backoff."""
    mock_sleep = mocker.patch("lib.scraper.asyncio.sleep",
                              new=mocker.AsyncMock())

    class FakeResp:
        def __init__(self, code, text=""):
            self.status_code = code
            self.text = text
    responses = [FakeResp(429), FakeResp(429), FakeResp(429), FakeResp(200, "body")]

    call_idx = {"i": 0}
    def fake_get(*args, **kwargs):
        r = responses[call_idx["i"]]
        call_idx["i"] += 1
        return r
    mocker.patch("requests.get", side_effect=fake_get)

    result = await _fetch_with_backoff_on_429("https://example.com")
    assert result == "body"
    # Sleep called with 30, 60, 120 in order (first attempt is 0.0 which skips sleep)
    assert [c.args[0] for c in mock_sleep.await_args_list] == list(_BACKOFF_SCHEDULE_S)

    # Exhaust case: 4 consecutive 429 → returns None
    call_idx["i"] = 0
    mock_sleep.reset_mock()
    mocker.patch("requests.get",
                 side_effect=lambda *a, **k: FakeResp(429))
    result2 = await _fetch_with_backoff_on_429("https://example.com")
    assert result2 is None
    assert mock_sleep.await_count == 3

    # Non-429 error → returns None immediately, no sleep
    mock_sleep.reset_mock()
    mocker.patch("requests.get",
                 side_effect=lambda *a, **k: FakeResp(500))
    result3 = await _fetch_with_backoff_on_429("https://example.com")
    assert result3 is None
    assert mock_sleep.await_count == 0


# SCR-02 -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cascade_layer_order(mocker):
    """Generic path: layer1 fails gate → layer2 fails gate → summary fallback.

    Tightened: explicit call-count assertions prove BOTH layer 1 and layer 2
    were exercised. A regression that skips layer 1 entirely would have
    passed the old version of this test.
    """
    # Layer 1: trafilatura.fetch_url returns "html1"; extract returns 100 chars (gate fails)
    # The run_in_executor mock evaluates its lambda argument; this way
    # fake_trafilatura.fetch_url is actually called from within _scrape_generic.
    async def fake_run_in_executor(executor, func):
        return func()
    fake_loop = mocker.MagicMock()
    fake_loop.run_in_executor = fake_run_in_executor
    mocker.patch("lib.scraper.asyncio.get_event_loop", return_value=fake_loop)

    fake_trafilatura = mocker.MagicMock()
    fake_trafilatura.fetch_url = mocker.MagicMock(return_value="html1")
    fake_trafilatura.extract = mocker.MagicMock(return_value="short")  # <500, fails gate
    mocker.patch.dict("sys.modules", {"trafilatura": fake_trafilatura})
    # Layer 2: _fetch_with_backoff_on_429 returns None (also fails gate, cascades to layer 4)
    mock_fetch_429 = mocker.patch(
        "lib.scraper._fetch_with_backoff_on_429",
        new=mocker.AsyncMock(return_value=None),
    )

    result = await _scrape_generic("https://medium.com/foo")

    # Final outcome: layer 4 fallback
    assert result.summary_only is True
    assert result.markdown == ""
    assert result.method == "none"
    assert result.content_html is None

    # Tight assertions: prove layer 1 AND layer 2 were actually exercised
    assert fake_trafilatura.fetch_url.call_count == 1, (
        "layer 1 trafilatura.fetch_url must be called exactly once"
    )
    assert fake_trafilatura.extract.call_count >= 1, (
        "layer 1 trafilatura.extract must be called at least once"
    )
    assert mock_fetch_429.await_count == 1, (
        "layer 2 _fetch_with_backoff_on_429 must be awaited exactly once "
        "(proves cascade from layer 1 to layer 2 fired)"
    )
