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
# 2026-08-05: MCP clients default to a ~60s total HTTP deadline (timeout_ms
# 30s + 30s grace) and hard-cut the SSE stream even though the server keeps
# sending pings. LightRAG kg_search takes ~4 min, so a synchronous wait of
# KG_DEADLINE always dies client-side as MCP_TOOL_CALL_FAILED. Fix: kg_search
# waits at most KG_INITIAL_WAIT (inside the client budget), then returns a
# job_id; kg_poll(job_id) fetches the result later in <1s calls.
# 45s: measured total = 45 + job-create(~3-5s) + SSE transfer(~3-5s via
# tunnel/public) ≈ 53-55s, safely inside the 60s client budget.
KG_INITIAL_WAIT = 45

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
    """Check KB-API is reachable (Qdrant is accessed via KB-API)."""
    kb_ok = False
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{KB_API}/health")
            r.raise_for_status()
            kb_ok = True
        except Exception:
            pass
    all_ready = kb_ok
    return JSONResponse({
        "status": "ready" if all_ready else "degraded",
        "checks": {"kb_api": kb_ok},
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
    """Knowledge-graph query via LightRAG (slow: ~1-4 min for full synthesis).

    Waits up to ~55s for the result inside this call; if LightRAG is still
    working it returns a job_id — call kg_poll(job_id) to fetch the report
    once it finishes. Never exceeds the ~60s client HTTP deadline."""
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

        deadline = time.monotonic() + KG_INITIAL_WAIT
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            poll = await client.get(f"{KB_API}/api/search/{jid}")
            poll.raise_for_status()
            pdata = poll.json()
            if pdata.get("status") == "done":
                result = pdata.get("result")
                return result if isinstance(result, str) else str(result or "[no-result]")
        return (
            f"[kg-running] job_id={jid} — LightRAG retrieval still in progress "
            f"(full synthesis takes ~1-4 min). Call kg_poll(job_id=\"{jid}\") "
            f"to fetch the result."
        )


@mcp.tool()
async def kg_poll(job_id: str) -> str:
    """Fetch the result of a kg_search job started earlier.

    Fast (<1s) — safe under any client timeout. Returns the synthesized
    report when done, or a 'still running' note; poll again in ~30s."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        poll = await client.get(f"{KB_API}/api/search/{job_id}")
        poll.raise_for_status()
        pdata = poll.json()
        if pdata.get("status") == "done":
            result = pdata.get("result")
            return result if isinstance(result, str) else str(result or "[no-result]")
        return (
            f"[kg-running] job_id={job_id} — still in progress, "
            f"poll again in ~30s."
        )


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
