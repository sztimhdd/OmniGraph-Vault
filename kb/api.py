"""kb/api.py — FastAPI application entry for kb-3 (port 8766).

Per kb-3-API-CONTRACT.md (kb-3-01 output): single `app` instance, /health
endpoint, /static/img mount (D-15 replaces standalone :8765 image server).
Subsequent plans (kb-3-05 articles, kb-3-06 search, kb-3-08 synthesize) extend
this app with route handlers via `from kb.api import app` import.

Booted by uvicorn:
    uvicorn kb.api:app --host 127.0.0.1 --port 8766 --workers 1

KB_PORT env override (CONFIG-01) controls the launch port at the uvicorn CLI;
the app object itself is port-agnostic.

NO new LLM provider env vars introduced (CONFIG-02 — REQ verbatim). All env
configuration delegates to `kb.config` (CONFIG-01 single source of truth).

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Idiomatic minimal FastAPI app skeleton: single app.py with FastAPI() instance, lifecycle handled by uvicorn (no @app.on_event needed for this scope — DB conn is lazy per-request). app.mount('/static/img', StaticFiles(directory=..., check_dir=False)) so import does not fail when KB_IMAGES_DIR doesn't exist (e.g. CI). Single /health endpoint returning {status, kb_db_path, kb_images_dir, version}. Type hints throughout. Module is import-safe — no DB connect, no filesystem writes at import time.")
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from kb import config
from kb.api_routers.articles import router as articles_router
from kb.api_routers.search import router as search_router

# Application version surfaced via /health and FastAPI metadata.
# Kept in lock-step with kb-3 milestone v2.0 (PROJECT-KB-v2.md).
_APP_VERSION = "2.0.0"


app = FastAPI(
    title="OmniGraph KB v2",
    version=_APP_VERSION,
    description="Bilingual Agent-tech content site backend (FTS5 + KG Q&A wrap)",
)

# API-08 / D-15: replace standalone http://localhost:8765 image server.
# `check_dir=False` so module import does not fail in CI / fresh checkouts where
# KB_IMAGES_DIR may not exist yet. Runtime requests for missing files then
# 404 cleanly via StaticFiles' default behavior.
app.mount(
    "/static/img",
    StaticFiles(directory=str(config.KB_IMAGES_DIR), check_dir=False),
    name="static_img",
)

# API-02 + API-03 (kb-3-05): /api/articles + /api/article/{hash}.
# Router is THIN — all DB access lives in kb.data.article_query.
app.include_router(articles_router)

# API-04 + API-05 (kb-3-06): /api/search (mode=fts sync OR mode=kg async via
# BackgroundTasks) + /api/search/{job_id} polling. Router is THIN — FTS5
# helpers live in kb.services.search_index; async-job state in kb.services.job_store.
app.include_router(search_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness + config-summary endpoint. Used by smoke tests + monitoring.

    Returns the resolved kb.config paths so operators can verify the running
    process picked up the expected env overrides without exec-ing into the
    container.
    """
    return {
        "status": "ok",
        "kb_db_path": str(config.KB_DB_PATH),
        "kb_images_dir": str(config.KB_IMAGES_DIR),
        "version": _APP_VERSION,
    }
