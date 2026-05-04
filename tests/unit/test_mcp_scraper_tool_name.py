"""
Regression test for Playwright MCP 1.60 tool rename.

Playwright MCP server renamed `browser_run_code` -> `browser_run_code_unsafe` in
version 1.60. The MCP scraper fallback in ingest_wechat.py must use the new
name; otherwise MCP fallback hard-fails with `Tool "browser_run_code" not found`.

Discovered + validated 2026-05-04 via end-to-end MCP handshake against
http://ohca.ddns.net:58931/mcp (tools list confirmed rename).

This is a source-level regression assertion (no network / no async mocking).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.unit
def test_mcp_scraper_uses_unsafe_tool_name() -> None:
    """scrape_wechat_mcp must call the Playwright MCP 1.60 tool name."""
    src = (REPO_ROOT / "ingest_wechat.py").read_text(encoding="utf-8")
    assert '"name": "browser_run_code_unsafe"' in src, (
        "scrape_wechat_mcp must send tools/call with "
        '"name": "browser_run_code_unsafe" (Playwright MCP 1.60 rename)'
    )


@pytest.mark.unit
def test_mcp_scraper_does_not_use_deprecated_tool_name() -> None:
    """The deprecated tool name must not appear in any tools/call payload."""
    src = (REPO_ROOT / "ingest_wechat.py").read_text(encoding="utf-8")
    # Match `"name": "browser_run_code"` (exact — the suffix-free form) in a
    # JSON-payload position (followed by `,` or `}`). Comments/docstrings /
    # print statements are allowed to keep the historical term.
    bad = re.compile(r'"name"\s*:\s*"browser_run_code"\s*[,}]')
    match = bad.search(src)
    assert match is None, (
        "Deprecated Playwright MCP tool name 'browser_run_code' appears in a "
        f"tools/call payload at char offset {match.start() if match else -1}; "
        "Playwright MCP 1.60 renamed it to 'browser_run_code_unsafe'."
    )
