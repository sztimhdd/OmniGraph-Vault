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
