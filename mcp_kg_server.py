#!/usr/bin/env python3
"""MCP server exposing the OmniGraph knowledge graph (LightRAG + Qdrant).

Usage:
    python mcp_kg_server.py                    # stdio mode
    python mcp_kg_server.py --transport sse    # HTTP/SSE on port 8932

Requires: OmniGraph venv (mcp, lightrag, qdrant-client)
"""

from __future__ import annotations

import argparse, asyncio, json, os, sys, textwrap
from pathlib import Path

# ── OmniGraph bootstrap ──────────────────────────────────────────
sys.path.insert(0, str(Path("/root/OmniGraph-Vault")))
os.environ.setdefault("P_DIR", "/root/.hermes/omonigraph-vault")
os.environ.setdefault("OMNIGRAPH_VECTOR_STORAGE", "qdrant")

from lightrag.lightrag import QueryParam
from lib.ingest_wechat import get_rag

# ── FastMCP ──────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omnigraph-kg")

_rag = None
_init_lock = asyncio.Lock()


async def _ensure_rag():
    global _rag
    if _rag is not None:
        return _rag
    async with _init_lock:
        if _rag is not None:
            return _rag
        _rag = await get_rag(flush=False)
        return _rag


# ── Tools ────────────────────────────────────────────────────────

@mcp.tool()
async def search_knowledge(
    query: str,
    mode: str = "hybrid",
    top_k: int = 10,
) -> str:
    """Full knowledge graph query. Returns relevant passages with entity context.

    Args:
        query: Natural language question
        mode: Query mode — 'naive' (keyword), 'local' (entity-focused),
              'global' (summary-focused), 'hybrid' (best of all)
        top_k: Number of results (default 10)
    """
    rag = await _ensure_rag()
    param = QueryParam(mode=mode, top_k=top_k)
    try:
        result = await rag.aquery(query, param=param)
    except Exception as e:
        return f"[ERROR] Query failed: {e}"
    return result


@mcp.tool()
async def search_chunks(query: str, top_k: int = 20) -> str:
    """Vector search over text chunks only. Returns raw passages without
    entity/relation synthesis. Faster than full query, best for
    finding specific facts.

    Args:
        query: Search query
        top_k: Number of results (default 20)
    """
    rag = await _ensure_rag()
    param = QueryParam(mode="naive", top_k=top_k)
    try:
        result = await rag.aquery(query, param=param)
    except Exception as e:
        return f"[ERROR] {e}"
    return result


@mcp.tool()
async def get_entity(name: str) -> str:
    """Look up a specific entity in the knowledge graph. Returns all
    known facts and relationships for this entity.

    Args:
        name: Entity name (e.g., 'Claude Code', 'OpenClaw', 'Manus')
    """
    rag = await _ensure_rag()
    try:
        info = await rag.aquery(
            f"What is {name}? Describe it in detail including its relationships.",
            param=QueryParam(mode="local", top_k=5),
        )
    except Exception as e:
        return f"[ERROR] {e}"
    return info


@mcp.tool()
async def get_graph_stats() -> str:
    """Return knowledge graph statistics: node count, edge count,
    storage size, and entity type distribution.
    """
    rag = await _ensure_rag()
    try:
        nodes = rag.chunk_entity_relation_graph.number_of_nodes()
        edges = rag.chunk_entity_relation_graph.number_of_edges()
    except Exception:
        nodes = edges = "unknown"

    storage = Path(os.environ["OMNIGRAPH_BASE_DIR"]) / "lightrag_storage"
    size_mb = sum(
        f.stat().st_size
        for f in storage.rglob("*")
        if f.is_file() and f.stat().st_size > 0
    ) / (1024 * 1024)

    return json.dumps({
        "nodes": nodes,
        "edges": edges,
        "storage_mb": round(size_mb, 1),
        "working_dir": str(storage),
    }, indent=2)


@mcp.tool()
async def list_entities(prefix: str = "", limit: int = 20) -> str:
    """List entity names in the knowledge graph. Supports prefix search.

    Args:
        prefix: Filter entities starting with this string
        limit: Maximum number of results (default 20)
    """
    rag = await _ensure_rag()
    entities = []
    for node, data in rag.chunk_entity_relation_graph.nodes(data=True):
        if prefix.lower() in node.lower():
            etype = data.get("entity_type", "unknown")
            desc = data.get("description", "")[:80]
            entities.append({"name": node, "type": etype, "description": desc})
            if len(entities) >= limit:
                break
    return json.dumps(entities, ensure_ascii=False, indent=2)


# ── Entry point ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OmniGraph KG MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio for Hermes, sse for HTTP)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8932,
        help="SSE port (default: 8932)",
    )
    args = parser.parse_args()
    if args.transport == "sse":
        print(f"Starting OmniGraph KG MCP on :{args.port} (SSE)")
        # SSE needs port in constructor, not run()
        global mcp
        mcp = FastMCP("omnigraph-kg", port=args.port, host="0.0.0.0")
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
