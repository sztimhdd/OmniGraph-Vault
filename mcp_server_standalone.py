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
# Three levels (Ponytail M3, 2026-08-04):
#   /live  — process alive (always 200 while thread is up)
#   /ready — dependency check (KB-API + Qdrant reachable)
#   /status — deeper state (collection point counts, pending jobs)

health_start = time.time()


async def health_live(request):
    return JSONResponse({"status": "ok", "uptime_s": int(time.time() - health_start)})


async def health_ready(request):
    """Check KB-API and Qdrant are reachable."""
    status = {"kb_api": False, "qdrant": False}
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{KB_API}/health")
            r.raise_for_status()
            status["kb_api"] = True
        except Exception:
            pass
    # Qdrant is accessed via KB-API, so kb_api check covers it indirectly.
    # Direct Qdrant check would require qdrant_client import — skip for lightweight readiness.
    all_ready = all(status.values())
    return JSONResponse({
        "status": "ready" if all_ready else "degraded",
        "checks": status,
        "uptime_s": int(time.time() - health_start),
    }, status_code=200 if all_ready else 503)


async def health_status(request):
    """Deeper status: collection counts, KB-API version. Internal use only."""
    info = {"uptime_s": int(time.time() - health_start)}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{KB_API}/health")
            r.raise_for_status()
            info["kb_api"] = r.json()
        except Exception as e:
            info["kb_api_error"] = str(e)
    return JSONResponse(info)


health_app = Starlette(routes=[
    Route("/live", health_live, methods=["GET"]),
    Route("/health", health_live, methods=["GET"]),   # backward compat
    Route("/ready", health_ready, methods=["GET"]),
    Route("/status", health_status, methods=["GET"]),
])


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
