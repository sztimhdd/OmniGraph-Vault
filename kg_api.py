#!/usr/bin/env python3
"""Lightweight HTTP API wrapping OmniGraph LightRAG for the website chatbot.

Usage:
    python kg_api.py --port 8932

Endpoints:
    GET  /health
    POST /query  {"question": "...", "mode": "hybrid"}
    POST /search {"query": "...", "top_k": 20}
    GET  /entity/{name}
    GET  /stats
"""

from __future__ import annotations

import argparse, asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path("/root/OmniGraph-Vault")))
os.environ.setdefault("OMNIGRAPH_BASE_DIR", "/root/.hermes/omonigraph-vault")
os.environ.setdefault("OMNIGRAPH_VECTOR_STORAGE", "qdrant")

from lightrag.lightrag import QueryParam
from lib.ingest_wechat import get_rag

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

_rag = None
_lock = asyncio.Lock()


async def _ensure_rag():
    global _rag
    if _rag is not None:
        return _rag
    async with _lock:
        if _rag is not None:
            return _rag
        _rag = await get_rag(flush=False)
        return _rag


# ── Endpoints ────────────────────────────────────────────────────

async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def query(request: Request) -> JSONResponse:
    body = await request.json()
    question = body.get("question", "").strip()
    mode = body.get("mode", "hybrid")
    if not question:
        return JSONResponse({"error": "question required"}, 400)

    rag = await _ensure_rag()
    try:
        result = await rag.aquery(question, param=QueryParam(mode=mode))
        return JSONResponse({"answer": result, "mode": mode})
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


async def search_chunks(request: Request) -> JSONResponse:
    body = await request.json()
    q = body.get("query", "").strip()
    top_k = body.get("top_k", 20)
    if not q:
        return JSONResponse({"error": "query required"}, 400)

    rag = await _ensure_rag()
    try:
        result = await rag.aquery(q, param=QueryParam(mode="naive", top_k=top_k))
        return JSONResponse({"results": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


async def get_entity(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    rag = await _ensure_rag()
    try:
        result = await rag.aquery(
            f"What is {name}? Describe its key attributes and relationships.",
            param=QueryParam(mode="local"),
        )
        return JSONResponse({"entity": name, "info": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


async def stats(request: Request) -> JSONResponse:
    rag = await _ensure_rag()
    g = rag.chunk_entity_relation_graph
    return JSONResponse({
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    })


# ── App ──────────────────────────────────────────────────────────

app = Starlette(routes=[
    Route("/health", health),
    Route("/query", query, methods=["POST"]),
    Route("/search", search_chunks, methods=["POST"]),
    Route("/entity/{name}", get_entity),
    Route("/stats", stats),
])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8932)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
