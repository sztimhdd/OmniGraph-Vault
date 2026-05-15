"""API-04 + API-05: GET /api/search + GET /api/search/{job_id}.

Mode-discriminated endpoint per kb-3-API-CONTRACT.md §5:
    - mode='fts' (default) → synchronous SQLite FTS5 trigram query (P50 < 100ms,
      DATA-07 active unless KB_SEARCH_BYPASS_QUALITY=on)
    - mode='kg' → async via BackgroundTasks; wraps `omnigraph_search.query.search`
      (C2 contract — signature unchanged); returns 202 + job_id; client polls
      ``GET /api/search/{job_id}``.

Job state is held in ``kb.services.job_store`` (in-memory dict, single-worker
uvicorn — QA-03). The same store is reused by /api/synthesize in kb-3-08.

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Async route /api/search dispatches by mode: fts is sync (call fts_query directly), kg uses FastAPI BackgroundTasks invoking an async _kg_worker that awaits omnigraph_search.query.search (C2 — signature UNCHANGED, just awaited). Polling endpoint /api/search/{job_id} is a simple dict lookup against job_store. Annotated[type, Query(...)] for declarative param validation. NEVER modify the C2 signature — wrap, don't mutate.")

    Skill(skill="writing-tests", args="TestClient integration tests with monkeypatched fixture_db + populated articles_fts. For the kg path, mock omnigraph_search.query.search via monkeypatch — do NOT actually call LightRAG (slow + needs storage). Test that the BackgroundTask completes (poll the job_id until done with mocked-instantaneous-search the test sleep is brief).")
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from kb.services import job_store, search_index, synthesize as synthesize_svc

router = APIRouter(prefix="/api", tags=["search"])


# ---- KG worker -------------------------------------------------------------


async def _kg_worker(job_id: str, q: str) -> None:
    """Run ``omnigraph_search.query.search`` (C2) and update job_store.

    C2 contract preserved: the function is called with its original
    ``(query_text, mode='hybrid')`` signature; we ``await`` it because C2 is
    declared ``async def`` (omnigraph_search/query.py:35). Any exception is
    captured into ``status='failed'`` — KG search has no FTS5 fallback per
    kb-3-API-CONTRACT §6.5 (synthesize is the never-500 surface, not search).
    """
    try:
        from omnigraph_search.query import search as kg_search

        result = await kg_search(q, mode="hybrid")
        job_store.update_job(job_id, status="done", result=result)
    except Exception as e:  # noqa: BLE001 — surface all errors to job record
        job_store.update_job(job_id, status="failed", error=str(e))


# ---- Endpoints -------------------------------------------------------------


@router.get("/search")
async def search_endpoint(
    background: BackgroundTasks,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    mode: Annotated[Literal["fts", "kg"], Query()] = "fts",
    lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """API-04 (mode=fts) + API-05 (mode=kg async).

    Query params:
        q: required, 1..500 chars
        mode: 'fts' (default) | 'kg'
        lang: 'zh-CN' | 'en' | 'unknown' | omitted (FTS path only — KG path
            ignores lang since LightRAG handles its own selection)
        limit: 1..100 (FTS path only)

    Returns:
        FTS path: ``{items, total, mode}`` per kb-3-API-CONTRACT §5.3
        KG path: ``{job_id, status='running', mode}`` per §5.4
    """
    if mode == "fts":
        rows = search_index.fts_query(q, lang=lang, limit=limit)
        items = [
            {"hash": h, "title": t, "snippet": s, "lang": lg, "source": src}
            for (h, t, s, lg, src) in rows
        ]
        return {"items": items, "total": len(items), "mode": "fts"}
    # kb-v2.1-1 KG-mode hardening: when the import-time credential probe failed,
    # avoid dispatching the BackgroundTask (which would try to import LightRAG,
    # init Vertex AI, and risk OOM). Return controlled-degraded shape with
    # HTTP 200 — never 500/502.
    if not synthesize_svc.KG_MODE_AVAILABLE:
        return {
            "items": [],
            "total": 0,
            "mode": "kg",
            "kg_unavailable": True,
            "reason": synthesize_svc.KG_MODE_UNAVAILABLE_REASON,
            "fallback_suggestion": synthesize_svc.KG_FALLBACK_SUGGESTION,
        }
    # KG async path — register BackgroundTask, return 202 + job_id immediately.
    jid = job_store.new_job(kind="search")
    background.add_task(_kg_worker, jid, q)
    return {"job_id": jid, "status": "running", "mode": "kg"}


@router.get("/search/{job_id}")
async def search_job_status(job_id: str) -> dict[str, Any]:
    """Poll an async KG-search job. 404 if `job_id` unknown.

    Response shape per kb-3-API-CONTRACT §6.3-6.5:
        ``{job_id, status, result?, error?}``
    where ``status`` is one of ``'running' | 'done' | 'failed'``.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "result": job["result"],
        "error": job["error"],
    }
