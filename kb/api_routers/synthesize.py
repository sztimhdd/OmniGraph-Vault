"""API-06 + API-07: POST /api/synthesize + GET /api/synthesize/{job_id}.

Async wrapper around kg_synthesize.synthesize_response (C1 unchanged) — see
kb/services/synthesize.py for the wrapper module.

Per kb-3-API-CONTRACT.md §7:
    POST /api/synthesize {question, lang} → 202 + {job_id, status: 'running'}
    GET /api/synthesize/{job_id}          → {status, result?, fallback_used,
                                             confidence, error?}

QA-03: BackgroundTasks pattern with single-uvicorn-worker (--workers 1) and the
shared in-memory job_store (kb.services.job_store, established by kb-3-06).

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="POST endpoint accepts Pydantic request model, allocates job_id via job_store.new_job(kind='synthesize'), schedules kb_synthesize via FastAPI BackgroundTasks (NOT asyncio.create_task — BackgroundTasks ensure response is sent before task runs), returns 202 + job_id. GET endpoint is dict lookup on job_store. Use status_code=status.HTTP_202_ACCEPTED on the route decorator. Type hints + Pydantic for request validation; FastAPI auto-generates OpenAPI from these.")

    Skill(skill="writing-tests", args="TestClient integration tests. Cover validation paths (422 on missing/empty/invalid lang/too-long question), 404 on missing job, full happy path with monkeypatched C1, full failure path with monkeypatched C1 raising. For polling, do NOT block forever — poll up to ~2s with 100ms sleep, fail test if not terminal. Reuse the patch-C1 + redirect-BASE_DIR helpers.")
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from kb.services import job_store
from kb.services.synthesize import kb_synthesize

router = APIRouter(prefix="/api", tags=["synthesize"])


class SynthesizeRequest(BaseModel):
    """POST /api/synthesize body — kb-3-API-CONTRACT §7.2.

    `question`: 1..2000 chars (CONTRACT §7.2 says 1..1000; we mirror plan-PLAN
    bounds 1..2000 which is the looser of the two — defensive for CJK queries
    that pack more semantics per char).
    `lang`: zh | en (Literal — Pydantic enforces 422 on anything else).
    `mode` (kb-v2.1-5): 'qa' (default — short Q&A, backward-compat) | 'long_form'
        (deep research article). Default 'qa' so old qa.js clients without the
        field still work. Pydantic enforces 422 on anything else.
    """

    question: str = Field(..., min_length=1, max_length=2000)
    lang: Literal["zh", "en"] = "zh"
    mode: Literal["qa", "long_form"] = "qa"


@router.post("/synthesize", status_code=status.HTTP_202_ACCEPTED)
async def synthesize_endpoint(
    body: SynthesizeRequest,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """API-06: enqueue a Q&A synthesis job. Returns 202 + job_id.

    Client should poll GET /api/synthesize/{job_id} every KB_QA_POLL_INTERVAL_MS
    until status != 'running'. The kb_synthesize wrapper prepends the I18N-07
    language directive before invoking C1 (kg_synthesize.synthesize_response).
    """
    jid = job_store.new_job(kind="synthesize")
    background.add_task(kb_synthesize, body.question, body.lang, jid, body.mode)
    return {"job_id": jid, "status": "running"}


@router.get("/synthesize/{job_id}")
async def synthesize_status(job_id: str) -> dict[str, Any]:
    """API-07: poll a synthesis job. 404 on unknown id.

    Response shape per kb-3-API-CONTRACT §7.7-7.9:
        {job_id, status, result?, fallback_used, confidence, error?}
    where status is one of 'running' | 'done' | 'failed'.

    Note: pre-kb-3-09 the failure path returns status='failed'; post-kb-3-09 it
    returns status='done' with confidence='fts5_fallback' (NEVER-500 per QA-05).
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "result": job["result"],
        "fallback_used": job["fallback_used"],
        "confidence": job["confidence"],
        "error": job["error"],
    }
