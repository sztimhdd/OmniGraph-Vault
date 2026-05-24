"""API-04 + API-05: GET /api/search + GET /api/search/{job_id}.

Mode-discriminated endpoint per kb-3-API-CONTRACT.md §5:
    - mode='kg' (default) → async via BackgroundTasks; wraps `omnigraph_search.query.search`
      (C2 contract — signature unchanged); returns 202 + job_id; client polls
      ``GET /api/search/{job_id}``.  When KG is unavailable returns 503 + Retry-After.
    - mode='fts' → synchronous SQLite FTS5 trigram query (P50 < 100ms,
      DATA-07 active unless KB_SEARCH_BYPASS_QUALITY=on) — explicit mode only,
      not exposed as a user-facing toggle (kb-v2.2-3 F8').

Job state is held in ``kb.services.job_store`` (in-memory dict, single-worker
uvicorn — QA-03). The same store is reused by /api/synthesize in kb-3-08.

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Async route /api/search dispatches by mode: fts is sync (call fts_query directly), kg uses FastAPI BackgroundTasks invoking an async _kg_worker that awaits omnigraph_search.query.search (C2 — signature UNCHANGED, just awaited). Polling endpoint /api/search/{job_id} is a simple dict lookup against job_store. Annotated[type, Query(...)] for declarative param validation. NEVER modify the C2 signature — wrap, don't mutate.")

    Skill(skill="writing-tests", args="TestClient integration tests with monkeypatched fixture_db + populated articles_fts. For the kg path, mock omnigraph_search.query.search via monkeypatch — do NOT actually call LightRAG (slow + needs storage). Test that the BackgroundTask completes (poll the job_id until done with mocked-instantaneous-search the test sleep is brief).")
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from kb.services import job_store, search_index, synthesize as synthesize_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])

# Locally re-bound to keep this router self-contained — same value as
# ``kb.services.synthesize._SOURCE_HASH_PATTERN`` (intentional duplication
# so a downstream synthesize refactor cannot accidentally break search).
_HASH_PAT = re.compile(r"/article/([a-f0-9]{10})")


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


def _make_snippet(body: Optional[str], max_len: int = 200) -> str:
    """Plain-text excerpt for KG-enhanced result cards.

    Strips markdown image syntax + code fences, collapses whitespace, then
    truncates to ``max_len`` chars with an ellipsis. Pure function — safe to
    call from the background worker without locking.
    """
    if not body:
        return ""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


async def _kg_local_worker(job_id: str, query: str) -> None:
    """KG-enhanced search worker for the progressive-enhancement endpoint.

    Calls C2 ``omnigraph_search.query.search`` with ``mode='local'`` (cheaper
    than hybrid for the article-card augmentation use case), parses the
    returned markdown for ``/article/{10-hex}`` links, deduplicates while
    preserving order, then resolves each hash to a ``{hash, title, snippet,
    lang, source}`` row using the same DATA-05 lookup the article-by-hash API
    uses (DATA-07 carve-out: unfiltered).

    Graceful degradation: any exception (LightRAG storage missing, embedding
    timeout, hash lookup failure) is logged at WARNING and the job completes
    with ``results=[]`` so the front end silently keeps the FTS-only view.
    """
    results: list[dict[str, Any]] = []
    try:
        from omnigraph_search.query import search as kg_search

        from kb.data.article_query import get_article_by_hash

        markdown = await kg_search(query_text=query, mode="local")
        hashes = list(dict.fromkeys(_HASH_PAT.findall(markdown or "")))
        for h in hashes:
            try:
                rec = get_article_by_hash(h)
            except Exception as inner:  # noqa: BLE001 — one bad row != bad batch
                logger.warning("kg-search hash lookup failed for %s: %s", h, inner)
                continue
            if rec is None:
                continue
            results.append({
                "hash": h,
                "title": rec.title or "",
                "snippet": _make_snippet(rec.body),
                "lang": rec.lang or "unknown",
                "source": rec.source,
            })
    except Exception as e:  # noqa: BLE001 — graceful degrade, never raise
        logger.warning("kg-search worker failed for query=%r: %s", query, e)
        results = []
    job_store.update_job(job_id, status="done", result=results)


class _KgSearchRequest(BaseModel):
    """POST /api/search/kg body."""

    query: str = Field(min_length=1, max_length=500)


# ---- Endpoints -------------------------------------------------------------


@router.get("/search")
async def search_endpoint(
    background: BackgroundTasks,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    mode: Annotated[Literal["fts", "kg"], Query()] = "kg",
    lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """API-04 (mode=fts) + API-05 (mode=kg async, default).

    Query params:
        q: required, 1..500 chars
        mode: 'kg' (default) | 'fts'
        lang: 'zh-CN' | 'en' | 'unknown' | omitted (FTS path only — KG path
            ignores lang since LightRAG handles its own selection)
        limit: 1..100 (FTS path only)

    Returns:
        KG path (default): ``{job_id, status='running', mode}`` per §5.4;
            503 + Retry-After: 60 when KG is unavailable (kb-v2.2-3 F8')
        FTS path: ``{items, total, mode}`` per kb-3-API-CONTRACT §5.3
    """
    if mode == "fts":
        rows = search_index.fts_query(q, lang=lang, limit=limit)
        items = [
            {"hash": h, "title": t, "snippet": s, "lang": lg, "source": src}
            for (h, t, s, lg, src) in rows
        ]
        return {"items": items, "total": len(items), "mode": "fts"}
    # kb-v2.2-3 F8': when KG is unavailable, return 503 + Retry-After instead of
    # a degraded 200.  No FTS5 fallback — per INPUT.md architectural choice:
    # "KG_MODE_AVAILABLE=False → 503 + retry_after, NOT FTS5 fallback."
    if not synthesize_svc.KG_MODE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            headers={"Retry-After": "60"},
            detail={
                "mode": "kg",
                "kg_unavailable": True,
                "reason": synthesize_svc.KG_MODE_UNAVAILABLE_REASON,
            },
        )
    # KG async path — register BackgroundTask, return 202 + job_id immediately.
    jid = job_store.new_job(kind="search")
    background.add_task(_kg_worker, jid, q)
    return {"job_id": jid, "status": "running", "mode": "kg"}


@router.post("/search/kg")
async def kg_enhance_start(
    payload: _KgSearchRequest,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Spawn a KG-enhancement job for the progressive-enhancement client.

    Returns ``{job_id}`` immediately; the client polls
    ``GET /api/search/kg/{job_id}`` until results arrive. Returns 503 +
    ``Retry-After`` when KG is unavailable so the client can silently keep
    its FTS-only view (matches the existing ``/api/search?mode=kg`` gate).
    """
    if not synthesize_svc.KG_MODE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            headers={"Retry-After": "60"},
            detail={
                "kg_unavailable": True,
                "reason": synthesize_svc.KG_MODE_UNAVAILABLE_REASON,
            },
        )
    jid = job_store.new_job(kind="search")
    background.add_task(_kg_local_worker, jid, payload.query)
    return {"job_id": jid}


@router.get("/search/kg/{job_id}")
async def kg_enhance_poll(job_id: str) -> dict[str, Any]:
    """Poll a KG-enhancement job. 404 if `job_id` unknown.

    Returns ``{results: [...]}`` once the worker is done (always ``done`` —
    failures degrade to empty list inside ``_kg_local_worker``), or
    ``{status: "pending"}`` while still running.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    if job["status"] != "done":
        return {"status": "pending"}
    return {"results": job["result"] or []}


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
