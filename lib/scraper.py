"""Phase 19 scraper module — unified URL → ScrapeResult with 4-layer cascade.

Public API:
  - ScrapeResult (frozen dataclass)
  - scrape_url(url, site_hint=None) -> ScrapeResult

Internals (private, not exported):
  - _route()              URL / site_hint → cascade identifier
  - _passes_quality_gate() SCR-04 quality check
  - _fetch_with_backoff_on_429() SCR-05 HTTP 429 retry schedule
  - _scrape_wechat()       delegates to ingest_wechat existing cascade
  - _scrape_generic()      trafilatura 4-layer cascade

See .planning/phases/19-generic-scraper-schema-kol-hotfix/19-RESEARCH.md
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# --- SCR-04 constants ---------------------------------------------------

_MIN_CONTENT_LENGTH: int = 500

_LOGIN_WALL_PATTERNS: tuple[str, ...] = (
    "Sign in",
    "Log in to continue",
    "Subscribe to read",
    "Subscribe to continue reading",
    "article limit",
    "This content is for members only",
    "Unlock this article",
    "Become a member",
    "登录查看",
    "关注公众号",
    "请先登录",
    "扫码关注",
    "免费注册",
    "订阅后阅读",
    "会员专享",
    "付费内容",
)

# --- SCR-05 constants ---------------------------------------------------

_BACKOFF_SCHEDULE_S: tuple[float, ...] = (30.0, 60.0, 120.0)
_DEFAULT_UA: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# --- SCR-01 dataclass ---------------------------------------------------

@dataclass(frozen=True)
class ScrapeResult:
    """Frozen result of any scrape path (SCR-01).

    content_html is populated ONLY for WeChat path (Phase 19 line-940 consumer
    calls ingest_wechat.process_content on it); generic path leaves it None.
    """
    markdown: str
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    method: str = ""
    summary_only: bool = False
    content_html: Optional[str] = None


# --- SCR-03 router ------------------------------------------------------

def _route(url: str, site_hint: Optional[str]) -> str:
    """Dispatch identifier for the cascade (SCR-03).

    Returns one of: "wechat", "arxiv_abs", "arxiv_pdf", "generic".
    site_hint='wechat' forces wechat path regardless of host (KOL always
    passes this).
    """
    if site_hint == "wechat":
        return "wechat"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "mp.weixin.qq.com":
        return "wechat"
    if host in ("arxiv.org", "www.arxiv.org"):
        if path.startswith("/abs/"):
            return "arxiv_abs"
        if path.startswith("/pdf/"):
            return "arxiv_pdf"
    return "generic"


# --- SCR-04 quality gate ------------------------------------------------

def _passes_quality_gate(markdown: Optional[str]) -> bool:
    """Return True iff markdown is long enough and has no login-wall marker.

    Case-insensitive match on _LOGIN_WALL_PATTERNS (SCR-04).
    """
    if not markdown or len(markdown) < _MIN_CONTENT_LENGTH:
        return False
    lowered = markdown.lower()
    for pat in _LOGIN_WALL_PATTERNS:
        if pat.lower() in lowered:
            return False
    return True


# --- SCR-05 429 backoff --------------------------------------------------

async def _fetch_with_backoff_on_429(
    url: str, ua: Optional[str] = None
) -> Optional[str]:
    """GET with per-layer exponential backoff on 429 (SCR-05).

    Schedule: 30s / 60s / 120s. After 3 attempts with 429, return None so
    the caller can cascade. HTTP 4xx/5xx (non-429) returns None immediately.
    """
    import requests  # local import so test mocks can patch at module scope
    headers = {"User-Agent": ua or _DEFAULT_UA}
    for attempt, delay_s in enumerate([0.0, *_BACKOFF_SCHEDULE_S]):
        if delay_s > 0:
            logger.info(
                "scraper: 429 backoff %ss (attempt %d/3)", delay_s, attempt
            )
            await asyncio.sleep(delay_s)
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.get(url, headers=headers, timeout=15),
            )
        except requests.RequestException as e:
            logger.warning("scraper: request error: %s", e)
            return None
        if resp.status_code == 200:
            return resp.text
        if resp.status_code != 429:
            logger.warning(
                "scraper: HTTP %d — cascade immediately (not retrying)",
                resp.status_code,
            )
            return None
        # else 429 → loop to next backoff iteration
    logger.warning("scraper: 429 persisted after 3 backoffs — cascading")
    return None


# --- SCR-02 WeChat delegate ---------------------------------------------

# Quick 260508-ev2 F1b: token → ingest_wechat function name mapping for
# SCRAPE_CASCADE env-var override. Tokens are short / lowercase / readable in
# crontab files (no need to type the scrape_wechat_ prefix).
_CASCADE_TOKEN_MAP: dict[str, str] = {
    "ua": "scrape_wechat_ua",
    "apify": "scrape_wechat_apify",
    "cdp": "scrape_wechat_cdp",
    "mcp": "scrape_wechat_mcp",
}

# Default cascade order — UA first because the 2026-05-08 cron failure
# (docs/bugreports/2026-05-08-cron-ingest-failure.md R1) showed UA was the
# only path actually succeeding (5/5 articles), while Apify/CDP/MCP combined
# wasted ~600s of the 900s budget on hard-fail loops. UA-first preserves all
# four layers as fallbacks for sites where UA fails (e.g. login walls).
_DEFAULT_CASCADE_ORDER: tuple[str, ...] = (
    "scrape_wechat_ua",
    "scrape_wechat_apify",
    "scrape_wechat_cdp",
    "scrape_wechat_mcp",
)


def _resolve_cascade_order() -> tuple[str, ...]:
    """Resolve cascade order from SCRAPE_CASCADE env var.

    Reads `SCRAPE_CASCADE` as a comma-separated list of tokens drawn from
    {ua, apify, cdp, mcp}. Whitespace around tokens is stripped. Unknown
    tokens (or an empty list after parsing) trigger a logger.warning and
    fall back to the default order. Unset/empty env → default order.
    """
    raw = os.environ.get("SCRAPE_CASCADE")
    if raw is None or raw.strip() == "":
        return _DEFAULT_CASCADE_ORDER
    tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    resolved: list[str] = []
    for tok in tokens:
        fn_name = _CASCADE_TOKEN_MAP.get(tok)
        if fn_name is None:
            logger.warning(
                "scraper: invalid SCRAPE_CASCADE=%r — falling back to default",
                raw,
            )
            return _DEFAULT_CASCADE_ORDER
        resolved.append(fn_name)
    if not resolved:
        logger.warning(
            "scraper: invalid SCRAPE_CASCADE=%r — falling back to default",
            raw,
        )
        return _DEFAULT_CASCADE_ORDER
    return tuple(resolved)


async def _scrape_wechat(url: str) -> ScrapeResult:
    """Delegate to the existing ingest_wechat cascade.

    Default order: ua → apify → cdp → mcp. First non-None result wins.
    Override via SCRAPE_CASCADE env var (comma-separated subset of
    {ua, apify, cdp, mcp}). Invalid/empty env → default order with a warning.

    content_html is preserved so batch_ingest_from_spider.py:940 consumer
    can call ingest_wechat.process_content on it downstream.

    If all configured layers return None, returns summary_only=True fallback.
    """
    import ingest_wechat

    cascade_order = _resolve_cascade_order()
    for fn_name in cascade_order:
        fn = getattr(ingest_wechat, fn_name, None)
        if fn is None:
            continue
        try:
            result = await fn(url)
        except Exception as e:  # noqa: BLE001 — cascade on any layer error
            logger.warning(
                "scraper: wechat layer %s raised %s — cascading",
                fn_name, e,
            )
            continue
        if not result:
            continue
        content_html = result.get("content_html") or ""
        # SCR-06 hotfix (2026-05-04): Apify returns "markdown" key, not
        # "content_html". If markdown is present but content_html absent,
        # short-circuit with markdown directly — no need to cascade to
        # CDP/MCP/UA (~360s waste per article when CDP is not running).
        scraped_markdown = result.get("markdown") or ""
        if not content_html and not scraped_markdown:
            continue
        if scraped_markdown and not content_html:
            markdown = scraped_markdown
            imgs = result.get("images") or []
        else:
            markdown, _process_imgs = ingest_wechat.process_content(content_html)
            # Mirror ingest_article:978 — merge UA's full-page data-src img_urls
            # (images outside #js_content) with process_content output (images
            # inside content_html). Plain concat, no dedup, preserves order.
            # Audit ece03ae Mismatch #1 — fixes silent data loss for UA fallback.
            imgs = list(result.get("img_urls") or []) + _process_imgs
        method = result.get("method", fn_name.replace("scrape_wechat_", ""))
        return ScrapeResult(
            markdown=markdown,
            images=imgs,
            metadata={
                "title": result.get("title", ""),
                "publish_time": result.get("publish_time", ""),
                "url": url,
            },
            method=method,
            summary_only=False,
            content_html=content_html,
        )
    logger.warning(
        "scraper: all wechat layers (%s) returned None for %s",
        ",".join(cascade_order), url[:80],
    )
    return ScrapeResult(
        markdown="", method="none", summary_only=True, content_html=None,
    )


# --- SCR-02 generic cascade --------------------------------------------

async def _scrape_generic(url: str) -> ScrapeResult:
    """4-layer cascade for non-WeChat URLs (SCR-02).

    Layer 1: trafilatura.fetch_url + trafilatura.extract
    Layer 2: _fetch_with_backoff_on_429 + trafilatura.extract (SCR-05)
    Layer 3: CDP/MCP — INTENTIONALLY SKIPPED in Phase 19 (deferred to Phase 20)
    Layer 4: summary_only=True fallback
    """
    import trafilatura

    # Layer 1: direct trafilatura fetch
    html = await asyncio.get_event_loop().run_in_executor(
        None, lambda: trafilatura.fetch_url(url),
    )
    if html:
        md = trafilatura.extract(
            html,
            output_format="markdown",
            include_images=True,
            include_links=True,
            favor_precision=True,
        )
        if _passes_quality_gate(md):
            return ScrapeResult(
                markdown=md or "",
                method="trafilatura",
                content_html=None,
            )

    # Layer 2: requests (with 429 backoff) + trafilatura extract
    html2 = await _fetch_with_backoff_on_429(url)
    if html2:
        md2 = trafilatura.extract(
            html2,
            output_format="markdown",
            include_images=True,
            include_links=True,
            favor_precision=True,
        )
        if _passes_quality_gate(md2):
            return ScrapeResult(
                markdown=md2 or "",
                method="requests+trafilatura",
                content_html=None,
            )

    # Layer 3: SKIPPED in Phase 19 per D-RSS-SCRAPER-SCOPE Option A scope
    # Generic CDP/MCP is deferred to Phase 20.

    # Layer 4: summary-only fallback (no raise — caller handles)
    logger.warning(
        "scraper: generic cascade exhausted for %s — summary_only",
        url[:80],
    )
    return ScrapeResult(
        markdown="", method="none", summary_only=True, content_html=None,
    )


# --- SCR-01 public API --------------------------------------------------

async def scrape_url(
    url: str, site_hint: Optional[str] = None
) -> ScrapeResult:
    """Public cascade API (SCR-01).

    Dispatches by URL router, runs the appropriate cascade. Never raises
    on scrape failure — returns summary_only=True result instead so
    callers can decide to skip.
    """
    route = _route(url, site_hint)
    if route == "wechat":
        return await _scrape_wechat(url)
    # arxiv_pdf, arxiv_abs, generic all route through the generic cascade
    # (arxiv_pdf existing PyMuPDF path stays in multimodal_ingest.py; Phase 19
    # does not touch it — a generic-cascade pass on arxiv_abs returns the
    # abstract which is sufficient for classify).
    return await _scrape_generic(url)
