"""RED stubs for Phase 19 Wave 1. Go GREEN when lib/scraper.py lands in plan 19-01."""
import pytest


def test_import_and_dataclass_shape():
    """SCR-01: lib.scraper exposes scrape_url + frozen ScrapeResult dataclass with
    fields {markdown, images, metadata, method, summary_only, content_html}."""
    pytest.fail("RED — awaiting plan 19-01 (lib/scraper.py creation)")


def test_route_dispatch():
    """SCR-03: _route() returns 'wechat' for mp.weixin.qq.com, 'arxiv_abs' for
    arxiv.org/abs/, 'arxiv_pdf' for arxiv.org/pdf/, 'generic' otherwise.
    site_hint='wechat' forces wechat regardless of host."""
    pytest.fail("RED — awaiting plan 19-01 (_route implementation)")


def test_quality_gate():
    """SCR-04: _passes_quality_gate returns False if markdown is None, shorter
    than 500 chars, or contains any _LOGIN_WALL_PATTERNS phrase (case-insensitive).
    Returns True otherwise."""
    pytest.fail("RED — awaiting plan 19-01 (_passes_quality_gate)")


def test_backoff_429():
    """SCR-05: _fetch_with_backoff_on_429 retries on HTTP 429 with schedule
    (30, 60, 120) seconds — 3 attempts max — then returns None. HTTP 200 returns
    text. HTTP 4xx/5xx (non-429) returns None immediately without sleeping."""
    pytest.fail("RED — awaiting plan 19-01 (_fetch_with_backoff_on_429)")


def test_cascade_layer_order():
    """SCR-02: _scrape_generic calls layer-1 (trafilatura.fetch_url) first;
    if quality gate fails, cascades to layer-2 (requests+trafilatura); then
    falls through to layer-4 summary fallback (summary_only=True)."""
    pytest.fail("RED — awaiting plan 19-01 (_scrape_generic cascade)")
