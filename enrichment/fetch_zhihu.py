"""Fetch a Zhihu answer URL, extract markdown + images, write to disk.

Part of Phase 4 enrichment pipeline. Called by the Hermes ``enrich_article``
skill once per question, after ``/zhihu-haowen-enrich`` yields a best-source URL.

CLI:
    python -m enrichment.fetch_zhihu <url> --hash <wechat_hash> --q-idx <N>

Design note: HTML fetch is pluggable (default uses Playwright CDP). For
unit tests, callers pass a ``html_fetcher`` callable that returns the HTML
string directly, bypassing CDP entirely.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Awaitable, Callable

from bs4 import BeautifulSoup
import html2text

from image_pipeline import (
    download_images,
    describe_images,
    localize_markdown,
    save_markdown_with_images,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path(
    os.environ.get(
        "ENRICHMENT_DIR",
        str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
    )
)
DEFAULT_TIMEOUT = int(os.environ.get("ENRICHMENT_ZHIHU_FETCH_TIMEOUT", "60"))
DEFAULT_CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")

# PRD §6.2 — filter images narrower than this threshold (author icons, emoji, etc.)
MIN_IMAGE_WIDTH_PX = 100


# ─────────────────────────────────────────────────────────────────────
# HTML → Markdown helpers
# ─────────────────────────────────────────────────────────────────────


def _extract_main_content_html(raw_html: str) -> str:
    """Return the inner HTML of the main Zhihu answer body.

    Tries several CSS selectors in priority order. Falls back to the whole
    document if none match (so the caller always gets something back).
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    for selector in [".RichContent-inner", ".RichText", "article"]:
        node = soup.select_one(selector)
        if node:
            return str(node)
    return raw_html


def _filter_small_images(
    html: str, min_width: int = MIN_IMAGE_WIDTH_PX
) -> tuple[str, list[str]]:
    """Remove <img> tags with explicit width < min_width.

    Images without an explicit width are kept (we can't know their size).
    Returns (cleaned_html, list_of_kept_image_urls).
    """
    soup = BeautifulSoup(html, "html.parser")
    kept: list[str] = []

    for img in list(soup.find_all("img")):
        # Check width attribute — Zhihu uses both ``width`` and ``data-width``
        raw_width = img.get("width") or img.get("data-width") or ""
        try:
            w = int(str(raw_width).replace("px", "").strip())
        except (ValueError, TypeError):
            w = None

        if w is not None and w < min_width:
            img.decompose()
            continue

        # Prefer ``data-original`` (full-res Zhihu CDN URL) over ``src``
        src = img.get("data-original") or img.get("src") or ""
        if src.startswith("http"):
            kept.append(src)

    return str(soup), kept


def html_to_markdown(raw_html: str) -> tuple[str, list[str]]:
    """Extract main content, filter small images, convert to Markdown.

    Returns (markdown_text, kept_image_urls).
    """
    main_html = _extract_main_content_html(raw_html)
    filtered_html, image_urls = _filter_small_images(main_html)
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    return converter.handle(filtered_html), image_urls


# ─────────────────────────────────────────────────────────────────────
# Default CDP fetcher (real; replaced by stub in unit tests)
# ─────────────────────────────────────────────────────────────────────


async def _default_cdp_fetch(
    url: str,
    cdp_url: str = DEFAULT_CDP_URL,
    timeout_s: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch ``url`` via a Playwright CDP connection.

    Supports two modes auto-detected by URL suffix:
    - ``http://host:port`` (no ``/mcp`` suffix) — ``connect_over_cdp`` (local Edge)
    - ``http://host:port/mcp`` suffix — ``_MCPClient`` (remote Playwright MCP server)
    """
    if cdp_url.endswith("/mcp"):
        return await _mcp_fetch(url, cdp_url, timeout_s)
    return await _cdp_connect_fetch(url, cdp_url, timeout_s)


async def _cdp_connect_fetch(url: str, cdp_url: str, timeout_s: int) -> str:
    """Playwright connect_over_cdp path (local Edge or Chromium)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        try:
            context = (
                browser.contexts[0]
                if browser.contexts
                else await browser.new_context()
            )
            page = await context.new_page()
            await page.goto(url, timeout=timeout_s * 1000)
            await page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
            return await page.content()
        finally:
            await browser.close()


async def _mcp_fetch(url: str, mcp_url: str, timeout_s: int) -> str:
    """Remote Playwright MCP server path (MCP-over-SSE).

    Mirrors the ``_MCPClient`` pattern in ``ingest_wechat.py``.
    """
    import uuid
    import aiohttp

    session_id = str(uuid.uuid4())
    headers = {"Content-Type": "application/json", "mcp-session-id": session_id}

    async with aiohttp.ClientSession() as session:
        # Initialize MCP session
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
        async with session.post(
            mcp_url, json=init_payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            await resp.json()

        # Navigate to URL
        nav_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "browser_navigate",
                "arguments": {"url": url},
            },
        }
        async with session.post(
            mcp_url,
            json=nav_payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as resp:
            await resp.json()

        # Get page content
        content_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "browser_evaluate", "arguments": {"expression": "document.documentElement.outerHTML"}},
        }
        async with session.post(
            mcp_url,
            json=content_payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            result = data.get("result", {})
            content = result.get("content", [{}])
            if isinstance(content, list) and content:
                return content[0].get("text", "")
            return ""


# ─────────────────────────────────────────────────────────────────────
# Main orchestration
# ─────────────────────────────────────────────────────────────────────


async def fetch_zhihu(
    url: str,
    wechat_hash: str,
    q_idx: int,
    base_dir: Path = DEFAULT_BASE_DIR,
    html_fetcher: Callable[[str], Awaitable[str]] | None = None,
) -> dict:
    """Fetch a Zhihu URL, extract + describe images, write artifacts to disk.

    Returns a summary dict matching the D-03 stdout contract:
    ``{"hash": ..., "q_idx": ..., "status": "ok", "md_path": ..., "image_count": N}``
    """
    fetcher = html_fetcher or _default_cdp_fetch
    raw_html = await fetcher(url)

    md, image_urls = html_to_markdown(raw_html)

    out_dir = base_dir / wechat_hash / str(q_idx)
    images_dir = out_dir / "images"

    # Download and describe images via shared image_pipeline
    url_to_path = download_images(image_urls, images_dir)
    descriptions = describe_images(list(url_to_path.values()))

    # Namespace Zhihu images as <hash>/zhihu_<q_idx>/ to avoid collision
    # with WeChat images stored under bare <hash>/ (D-13 image namespacing)
    ns_hash = f"{wechat_hash}/zhihu_{q_idx}"
    md = localize_markdown(md, url_to_path, article_hash=ns_hash)

    # Append image reference blocks (matches WeChat ingestion convention)
    processed: list[dict] = []
    for i, (src, path) in enumerate(url_to_path.items()):
        desc = descriptions.get(path, "")
        local_url = f"http://localhost:8765/{ns_hash}/{path.name}"
        md += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {desc}\n"
        processed.append(
            {"index": i, "description": desc, "local_url": local_url, "src": src}
        )

    save_markdown_with_images(
        md,
        out_dir,
        {
            "url": url,
            "wechat_hash": wechat_hash,
            "q_idx": q_idx,
            "images": processed,
        },
    )

    return {
        "hash": wechat_hash,
        "q_idx": q_idx,
        "status": "ok",
        "md_path": str(out_dir / "final_content.md"),
        "image_count": len(processed),
    }


# ─────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Usage:
        python -m enrichment.fetch_zhihu <url> --hash <wechat_hash> --q-idx <N>

    Exits 0 on success, 1 on error. Emits a single-line JSON summary on stdout
    (D-03 contract — stays under the 50KB Hermes stdout truncation cap).
    """
    parser = argparse.ArgumentParser(
        description="Fetch a Zhihu answer URL and write enriched markdown to disk.",
    )
    parser.add_argument("url", help="Zhihu answer URL to fetch")
    parser.add_argument("--hash", required=True, dest="wechat_hash", help="Parent WeChat article hash")
    parser.add_argument("--q-idx", type=int, required=True, help="Question index (0, 1, 2, …)")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR), help="Base enrichment directory")
    args = parser.parse_args(argv)

    try:
        summary = asyncio.run(
            fetch_zhihu(
                args.url,
                args.wechat_hash,
                args.q_idx,
                base_dir=Path(args.base_dir),
            )
        )
    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stderr)
        print(
            json.dumps(
                {
                    "hash": args.wechat_hash,
                    "q_idx": args.q_idx,
                    "status": "error",
                    "error": str(e),
                }
            )
        )
        return 1

    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
