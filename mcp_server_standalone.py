#!/usr/bin/env python3
"""MCP server — thin proxy to kb-api. 2 tools. Health on :8768."""
from __future__ import annotations

import argparse, asyncio, os, threading, time

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp.server.fastmcp import FastMCP

KB_API = os.environ.get("KB_API_URL", "http://127.0.0.1:8766")
TIMEOUT = 120
POLL_INTERVAL = 1.0
KG_DEADLINE = 240

mcp = FastMCP("omnigraph-kg", host="0.0.0.0", port=8767)

# ── Health (separate port, separate uvicorn) ──────────────────────

async def health(request):
    return JSONResponse({"status": "ok"})

health_app = Starlette(routes=[Route("/health", health, methods=["GET"])])


def _run_health():
    uvicorn.run(health_app, host="0.0.0.0", port=8768, log_level="warning")


# ── Tools ─────────────────────────────────────────────────────────

@mcp.tool()
async def fts_search(query: str, limit: int = 10, lang: str = "zh-CN") -> str:
    """Full-text keyword search. Sync, <100ms, no LLM."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{KB_API}/api/search",
            params={
                "q": query[:500], "mode": "fts",
                "limit": min(max(limit, 1), 50),
                "lang": lang if lang in ("zh-CN", "en") else "zh-CN",
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return "[no-results]"
        return "\n".join(
            f"## {i.get('title','?')}\n{i.get('snippet','')}\n"
            for i in items
        )


@mcp.tool()
async def kg_search(query: str) -> str:
    """Knowledge-graph query via LightRAG. Slower, understands concepts."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{KB_API}/api/search",
            params={"q": query[:500], "mode": "kg"},
        )
        if resp.status_code == 503:
            return "[kg-unavailable] Try fts_search."
        resp.raise_for_status()
        jid = resp.json().get("job_id")
        if not jid:
            return "[job-create-failed]"

        deadline = time.monotonic() + KG_DEADLINE
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            poll = await client.get(f"{KB_API}/api/search/{jid}")
            poll.raise_for_status()
            pdata = poll.json()
            if pdata.get("status") == "done":
                result = pdata.get("result")
                return result if isinstance(result, str) else str(result or "[no-result]")
        return "[kg-timeout]"


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="streamable-http")
    args = parser.parse_args()

    if args.transport != "streamable-http":
        mcp.run(transport=args.transport)
        return

    # ponytail: health on separate port avoids touching FastMCP internals
    t = threading.Thread(target=_run_health, daemon=True)
    t.start()

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
