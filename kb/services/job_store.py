"""In-memory async-job store — QA-03.

Used by ``GET /api/search?mode=kg`` (kb-3-06) AND ``POST /api/synthesize``
(kb-3-08). Single-uvicorn-worker assumed (``--workers 1``); multi-worker
SQLite-backed store deferred to v2.1 per kb-3-API-CONTRACT.md §1.5.

Job records persist for the lifetime of the uvicorn process. No TTL or
cleanup in v2.0 — expected magnitude is small (<1000 jobs/day).

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="kb/services/job_store.py is the shared in-memory async-job dict with a threading.Lock — used by both /api/search?mode=kg AND kb-3-08 /api/synthesize. uuid4().hex[:12] for opaque job ids. Module-level _JOBS dict guarded by Lock for thread-safety under FastAPI BackgroundTasks (BackgroundTasks run in the threadpool, not the event loop).")

    Skill(skill="writing-tests", args="Round-trip + concurrent.futures.ThreadPoolExecutor (multiple workers each calling update_job with different keys; final state must reflect all updates). No mocks.")
"""
from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any, Optional

# Module-level state guarded by `_LOCK`. FastAPI BackgroundTasks run in a
# threadpool, so concurrent reads/writes are real.
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = Lock()


def new_job(kind: str = "search") -> str:
    """Allocate a new job id; initial state ``{status: 'running', ...}``.

    Args:
        kind: job classification — ``'search'`` (kb-3-06) or
            ``'synthesize'`` (kb-3-08). Used by callers to disambiguate
            polling endpoints.

    Returns:
        12-char hex job id (opaque to clients).
    """
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {
            "job_id": jid,
            "kind": kind,
            "status": "running",
            "result": None,
            "error": None,
            "fallback_used": False,
            "confidence": "kg",  # default; QA wrapper updates if FTS5 fallback
            "started_at": time.time(),
        }
    return jid


def update_job(jid: str, **kwargs: Any) -> None:
    """Merge `kwargs` into the job record (no-op if `jid` unknown)."""
    with _LOCK:
        if jid in _JOBS:
            _JOBS[jid].update(kwargs)


def get_job(jid: str) -> Optional[dict[str, Any]]:
    """Return a shallow copy of the job record, or None if unknown."""
    with _LOCK:
        return dict(_JOBS[jid]) if jid in _JOBS else None
