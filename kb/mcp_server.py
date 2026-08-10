"""kb/mcp_server.py — MCP server wrapping OmniGraph KB for external AI agents.

Architecture
------------
                  ┌────────────────────────────┐
                  │  External AI (Vitaclaw,     │
                  │  Hermes, Claude, etc.)      │
                  └──────────┬─────────────────┘
                             │ MCP protocol (HTTP/SSE)
                             ▼
                  ┌────────────────────────────┐
                  │  mcp_server.py (:8767)      │
                  │  Tools: fts_search,         │
                  │  kg_query, synthesize,      │
                  │  get_article, health        │
                  └──────────┬─────────────────┘
                             │ HTTP → localhost:8766
                             ▼
                  ┌────────────────────────────┐
                  │  kb-api (FastAPI :8766)     │
                  │  LightRAG + FTS5 + Qdrant   │
                  └────────────────────────────┘

Deployment
----------
    # Install deps (once)
    pip install mcp httpx

    # Run (foreground)
    python kb/mcp_server.py

    # Run as systemd service (see /etc/systemd/system/omni-mcp.service)

    # Connect from Hermes config.yaml:
    mcp_servers:
      omnigraph:
        url: "http://127.0.0.1:8767/mcp"
        timeout: 180

    # Connect from remote (via SSH tunnel or Caddy):
    ssh -L 8767:127.0.0.1:8767 vitaclaw-aliyun
    # Then: url: "http://127.0.0.1:8767/mcp"

Knowledge sources
-----------------
    FTS5  — SQLite full-text index on article title + body (fast, no embedding)
    KG    — LightRAG graph + Qdrant vectors (deep, with citations)
    DB    — SQLite article metadata, entities, canonical map

Tools exposed
-------------
    fts_search(query, lang, limit)    → {items[], total}
    kg_query(query, mode)             → {job_id, status, result?}  [async poll]
    synthesize(question, lang, mode)  → {job_id, status, result?}  [async poll]
    get_article(hash)                 → {title, body, entities, ...}
    health()                          → {status, ...}
"""

from __future__ import annotations

import asyncio
import json
import locale
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Workaround: Python 3.12+ removed locale.normalize, but click/types.py still uses it.
# Inject a no-op stub before mcp/click import.
if not hasattr(locale, "normalize"):
    locale.normalize = lambda x: x

# ---------------------------------------------------------------------------
# Bootstrap: ensure the repo root is on sys.path so we can import kb.config
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration — env-overridable defaults
# ---------------------------------------------------------------------------
KB_API_URL = os.environ.get("OMNIGRAPH_KB_API_URL", "http://127.0.0.1:8766")
MCP_HOST = os.environ.get("OMNIGRAPH_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("OMNIGRAPH_MCP_PORT", "8767"))
KG_POLL_MAX_S = int(os.environ.get("OMNIGRAPH_MCP_KG_POLL_MAX_S", "300"))
KG_POLL_INTERVAL_S = int(os.environ.get("OMNIGRAPH_MCP_KG_POLL_INTERVAL_S", "5"))
SYNTH_POLL_MAX_S = int(os.environ.get("OMNIGRAPH_MCP_SYNTH_POLL_MAX_S", "600"))
SYNTH_POLL_INTERVAL_S = int(os.environ.get("OMNIGRAPH_MCP_SYNTH_POLL_INTERVAL_S", "5"))

mcp = FastMCP(
    "OmniGraph KB",
    instructions="OmniGraph Knowledge Graph — FTS5 + LightRAG + Qdrant over Chinese AI articles",
    host=MCP_HOST,
    port=MCP_PORT,
)


# ============================================================================
# Tool: health
# ============================================================================

@mcp.tool()
def health() -> dict:
    """Check if the OmniGraph KB is alive and accessible.

    Returns kb-api /health response: {status, kb_db_path, version}.
    Does NOT require any LLM or embedding call — cheap, sync.
    """
    try:
        with urllib.request.urlopen(f"{KB_API_URL}/health", timeout=5) as r:
            return json.load(r)
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}


# ============================================================================
# Tool: fts_search — full-text keyword search (fast, no embedding)
# ============================================================================

@mcp.tool()
def fts_search(query: str, lang: str = "zh-CN", limit: int = 10) -> dict:
    """Full-text keyword search across all indexed articles (FTS5).

    Fast, no LLM/embedding cost. Good for:
    - Finding articles by keyword, name, or concept
    - Checking if a topic exists in the KB
    - Quick fact lookup

    Args:
        query: Search query string (1-500 chars)
        lang: Language filter — 'zh-CN', 'en', or 'unknown'. Default 'zh-CN'.
        limit: Max results (1-100). Default 10.

    Returns:
        {items: [{hash, title, snippet, lang, source}], total, mode: 'fts'}
    """
    params = urllib.parse.urlencode({
        "q": query,
        "mode": "fts",
        "lang": lang,
        "limit": limit,
    })
    try:
        with urllib.request.urlopen(
            f"{KB_API_URL}/api/search?{params}", timeout=10
        ) as r:
            return json.load(r)
    except Exception as exc:
        return {"error": str(exc), "mode": "fts"}


# ============================================================================
# Tool: kg_query — Knowledge Graph query (async poll)
# ============================================================================

@mcp.tool()
async def kg_query(query: str, mode: str = "local") -> dict:
    """Query the Knowledge Graph (LightRAG over Qdrant vectors).

    Deep semantic search across entities, relationships, and chunks.
    Returns cited answer with source references. Good for:
    - Conceptual questions like "What is OpenClaw's architecture?"
    - Relationship queries like "How does X relate to Y?"
    - Finding articles by semantic meaning (not just keywords)

    Args:
        query: Natural language question (1-500 chars)
        mode: LightRAG query mode. One of:
            'local'  — entity/chunk-level retrieval (default, fastest)
            'global' — community-level summarization
            'hybrid' — local + global combined
            'naive'  — raw vector search without graph context
            'mix'    — mix of all modes

    Returns:
        {job_id, status: 'done'|'failed'|'timeout', result?, ...}
    """
    import httpx

    async with httpx.AsyncClient() as client:
        # Submit KG search job
        resp = await client.get(
            f"{KB_API_URL}/api/search",
            params={"q": query, "mode": "kg"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"error": f"submit_failed: HTTP {resp.status_code}", "body": resp.text[:500]}
        job = resp.json()
        job_id = job["job_id"]

        # Poll until terminal or timeout
        max_iterations = KG_POLL_MAX_S // KG_POLL_INTERVAL_S
        for _ in range(max_iterations):
            await asyncio.sleep(KG_POLL_INTERVAL_S)
            poll = await client.get(
                f"{KB_API_URL}/api/search/{job_id}", timeout=15
            )
            data = poll.json()
            if data.get("status") in ("done", "failed", "error"):
                return data

        return {"job_id": job_id, "status": "timeout", "error": "kg_query poll exhausted"}


# ============================================================================
# Tool: synthesize — Deep Q&A with citations (async poll)
# ============================================================================

@mcp.tool()
async def synthesize(question: str, lang: str = "zh", mode: str = "qa") -> dict:
    """Deep Q&A synthesis with citations from the knowledge graph.

    Calls the full LightRAG synthesis pipeline — generates a natural-language
    answer with inline citations and source references. Good for:
    - "What is X and why does it matter?"
    - "Explain the trade-offs between A and B"
    - "Summarize the latest thinking on Y"

    Args:
        question: Natural language question (1-2000 chars)
        lang: Response language — 'zh' (Chinese) or 'en' (English). Default 'zh'.
        mode: Answer style — 'qa' (short answer, default) or 'long_form' (article)

    Returns:
        {job_id, status: 'done'|'failed'|'timeout', result?, fallback_used,
         confidence, citations_present?, error?}
    """
    import httpx

    async with httpx.AsyncClient() as client:
        # Submit synthesize job
        resp = await client.post(
            f"{KB_API_URL}/api/synthesize",
            json={"question": question, "lang": lang, "mode": mode},
            timeout=15,
        )
        if resp.status_code != 202:
            return {"error": f"submit_failed: HTTP {resp.status_code}", "body": resp.text[:500]}
        job = resp.json()
        job_id = job["job_id"]

        # Poll until terminal or timeout
        max_iterations = SYNTH_POLL_MAX_S // SYNTH_POLL_INTERVAL_S
        for _ in range(max_iterations):
            await asyncio.sleep(SYNTH_POLL_INTERVAL_S)
            poll = await client.get(
                f"{KB_API_URL}/api/synthesize/{job_id}", timeout=15
            )
            data = poll.json()
            if data.get("status") in ("done", "failed", "error"):
                return data

        return {"job_id": job_id, "status": "timeout", "error": "synthesize poll exhausted"}


# ============================================================================
# Tool: get_article — Fetch full article content
# ============================================================================

@mcp.tool()
def get_article(hash_or_url: str) -> dict:
    """Fetch full article content, entities, and metadata by content hash.

    Returns the complete article body, extracted entities, and metadata.
    Good for deep-reading a specific article found via fts_search or kg_query.

    Args:
        hash_or_url: Article content hash (10-char hex from search results)
                     or full WeChat article URL.

    Returns:
        {title, body, lang, entities, ...} or {error: 'not_found'}
    """
    try:
        with urllib.request.urlopen(
            f"{KB_API_URL}/api/article/{hash_or_url}", timeout=15
        ) as r:
            if r.status == 404:
                return {"error": "not_found", "hash": hash_or_url}
            return json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"error": "not_found", "hash": hash_or_url}
        return {"error": f"HTTP {exc.code}", "hash": hash_or_url}
    except Exception as exc:
        return {"error": str(exc), "hash": hash_or_url}


# ============================================================================
# Main entrypoint
# ============================================================================

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
