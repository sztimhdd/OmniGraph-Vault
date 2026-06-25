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

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import RAG_WORKING_DIR
from kb import config
from kb.api_routers.articles import router as articles_router
from kb.api_routers.research import router as research_router
from kb.api_routers.search import router as search_router
from kb.api_routers.synthesize import router as synthesize_router
from kg_synthesize import _embedding_timeout_default, _get_embedding_func
from lib.llm_complete import get_llm_func
from lightrag.lightrag import LightRAG

# Application version surfaced via /health and FastAPI metadata.
# Kept in lock-step with kb-3 milestone v2.0 (PROJECT-KB-v2.md).
_APP_VERSION = "2.0.0"

_log = logging.getLogger(__name__)


def _build_llm_rerank() -> tuple[Callable[..., object] | None, bool]:
    """Build LightRAG-compatible async rerank function via lib/llm_rerank dispatcher.

    Returns (rerank_func, ok_flag). ok=False signals graceful degrade
    (KG paths fall back to mode='hybrid' via app.state.rerank_disabled).

    Honors OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 env override for SC#4 testing.
    Also honors legacy BGE_FORCE_LOAD_FAIL=1 (P2-3 escape compat).
    """
    if (os.environ.get("OMNIGRAPH_LLM_RERANK_FORCE_FAIL") == "1"
            or os.environ.get("BGE_FORCE_LOAD_FAIL") == "1"):
        _log.warning("llm_rerank_force_fail (test/escape override)")
        return None, False
    t0 = time.monotonic()
    _log.warning("llm_rerank_init_start")
    try:
        from lib.llm_rerank import get_rerank_func
        func, ok = get_rerank_func()
        if not ok:
            _log.warning("llm_rerank_init_disabled (provider returned no-op)")
            return None, False
        _log.warning(
            "llm_rerank_init_ok provider=%s wall_s=%.2f",
            os.environ.get("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving"),
            time.monotonic() - t0,
        )
        return func, True
    except Exception as exc:  # noqa: BLE001 — graceful degrade
        _log.warning("llm_rerank_init_failed err=%s", exc)
        return None, False


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.monotonic()
    _log.warning("lightrag_singleton_init_start working_dir=%s", RAG_WORKING_DIR)
    rerank_func, rerank_ok = _build_llm_rerank()
    app.state.reranker = rerank_func
    app.state.rerank_disabled = not rerank_ok
    # NOTE: vector_storage env read — also at ingest_wechat.py:392 + kg_synthesize.py:155; sync if changed.
    _vector_storage_kwargs = (
        {"vector_storage": "QdrantVectorDBStorage"}
        if os.environ.get("OMNIGRAPH_VECTOR_STORAGE", "nanovectordb") == "qdrant"
        else {}
    )
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=_get_embedding_func(),
        default_embedding_timeout=_embedding_timeout_default(),
        rerank_model_func=rerank_func,
        **_vector_storage_kwargs,
    )
    # ISSUES #65 diagnostic: settle the init-vs-query rerank disagreement on the
    # LIVE deployed instance. Records whether the reranker survived init AND
    # whether asdict(rag) carries rerank_model_func into the query-path
    # global_config (lightrag.py builds global_config = asdict(self) at query
    # time). This is the A/B/C discriminator — read it off the deployed log.
    from dataclasses import asdict as _asdict
    _gc_rerank = _asdict(rag).get("rerank_model_func")
    _log.warning(
        "rerank_diag init_reranker_set=%s rerank_disabled=%s "
        "global_config_has_func=%s enable_rerank_default=%s",
        app.state.reranker is not None,
        app.state.rerank_disabled,
        _gc_rerank is not None,
        os.getenv("RERANK_BY_DEFAULT", "true"),
    )
    _log.warning(
        "lightrag_vector_storage backend=%s",
        os.environ.get("OMNIGRAPH_VECTOR_STORAGE", "nanovectordb"),
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    app.state.lightrag = rag
    app.state.lightrag_lock = asyncio.Lock()
    _log.warning(
        "lightrag_singleton_ready wall_s=%.2f", time.monotonic() - t0,
    )
    try:
        yield
    finally:
        if hasattr(rag, "finalize_storages"):
            await rag.finalize_storages()
        _log.warning("lightrag_singleton_finalize_done")


app = FastAPI(
    lifespan=lifespan,
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

# API-06 + API-07 (kb-3-08): POST /api/synthesize (202 + job_id) + GET
# /api/synthesize/{job_id} polling. Wrapper around C1 (kg_synthesize.synthesize_response)
# with I18N-07 language directive injection. Reuses kb.services.job_store from kb-3-06.
# Failure path is BASIC ('failed' status); kb-3-09 will replace with FTS5 fallback per QA-05.
app.include_router(synthesize_router)

# Agentic-RAG-v1.1 arx-2-http: POST /api/research SSE stream wrapping the
# 5-stage pipeline in lib/research/orchestrator.py. Single-shot streaming
# endpoint (no job polling) — clients consume text/event-stream until the
# terminal `done` event lands with the ResearchResult JSON.
app.include_router(research_router)


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
