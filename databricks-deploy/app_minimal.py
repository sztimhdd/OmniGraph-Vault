"""FastAPI app with FTS search endpoint."""
import sys
import os
from pathlib import Path

# Ensure source root is in path for kb/ imports
source_root = Path("/app/python/source_code")
if source_root not in [Path(p) for p in sys.path]:
    sys.path.insert(0, str(source_root))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import sqlite3

# Import startup adapter to hydrate the FTS table at app start
try:
    from startup_adapter import hydrate_db_from_volume
    hydrate_db_from_volume()
except Exception as e:
    print(f"[STARTUP WARNING] Failed to hydrate DB: {e}", flush=True)

app = FastAPI(title="OmniGraph KB Search API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/search")
def search(q: str, lang: str | None = None, mode: str = "fts", limit: int = 20):
    """Search the knowledge base using FTS."""
    try:
        from kb.services.search_index import fts_query
        from kb import config

        results = fts_query(q=q, lang=lang, limit=limit)
        items = [
            {
                "hash": r[0],
                "title": r[1],
                "snippet": r[2],
                "lang": r[3],
                "source": r[4],
            }
            for r in results
        ]
        return {"items": items, "total": len(items)}
    except Exception as e:
        print(f"[SEARCH ERROR] {e}", flush=True)
        return JSONResponse(
            {"error": str(e), "items": [], "total": 0},
            status_code=500
        )
