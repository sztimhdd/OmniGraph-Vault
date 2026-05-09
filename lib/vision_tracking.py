"""Dedicated tracking + drain helpers for Vision worker tasks (D-10.09 / 260509-p1n).

The batch orchestrator must drain pending Vision worker tasks before
``rag.finalize_storages()`` so sub-doc ainsert calls don't race with the
storage flush.  The original implementation in
``batch_ingest_from_spider._drain_pending_vision_tasks`` used
``asyncio.all_tasks()`` — a broad scan that captured LightRAG / Cognee /
kuzu library tasks alongside the Vision workers.  ``gather()`` on those
library tasks never resolves and the cron process hung after
``max-articles cap reached`` (Hermes 2026-05-09 15:27 + 16:26 ADT).

This module replaces the broad-scan with a narrow set populated only at
the Vision worker spawn site (``ingest_wechat.py:1186``).  Library tasks
are never touched; the 120 s deadline + cancel-on-timeout semantics are
preserved verbatim.

Public surface
--------------
- ``track_vision_task(task)`` — register a task into ``_VISION_TASKS`` and
  hook ``add_done_callback(_VISION_TASKS.discard)`` so completed tasks
  drop out of the set automatically.  Returns the same task so call sites
  can keep the existing ``vision_task = track_vision_task(asyncio.create_task(...))``
  shape.
- ``drain_vision_tasks(timeout_s)`` — async; gather pending Vision tasks
  with ``asyncio.wait_for``.  On TimeoutError cancel still-pending tasks
  and gather them once more with ``return_exceptions=True`` so cancelled
  side-effects (log lines, finally blocks) complete before the caller
  proceeds to ``finalize_storages()``.
- ``_VISION_TASKS`` — module-level set.  Exported for test introspection
  (``tests/unit/test_drain_cap.py``); production code should not touch it
  directly.

This module deliberately imports nothing from
``batch_ingest_from_spider`` or ``ingest_wechat`` to remain import-cycle
safe.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Module-level dedicated set; populated only by track_vision_task().
_VISION_TASKS: set[asyncio.Task] = set()


def track_vision_task(task: asyncio.Task) -> asyncio.Task:
    """Register ``task`` into the Vision-worker drain set.

    Adds ``task`` to ``_VISION_TASKS`` and hooks
    ``add_done_callback(_VISION_TASKS.discard)`` so the task drops out of
    the set when it completes (success, failure, or cancellation).  The
    same task object is returned so call sites can keep the existing
    ``vision_task = track_vision_task(asyncio.create_task(...))`` shape.
    """
    _VISION_TASKS.add(task)
    task.add_done_callback(_VISION_TASKS.discard)
    return task


async def drain_vision_tasks(timeout_s: float = 120.0) -> None:
    """Drain pending Vision worker tasks before storage finalisation.

    Operates on the narrow ``_VISION_TASKS`` set populated by
    ``track_vision_task()``.  Tasks still pending after ``timeout_s`` are
    cancelled; the caller proceeds to ``finalize_storages()`` regardless.

    Losing some image-side entities is acceptable — next ingest of the
    same article re-adds them, and the text-side ``ainsert`` is already
    committed at this point in the call chain.

    A no-op when ``_VISION_TASKS`` is empty (no log line emitted).
    """
    pending = [t for t in _VISION_TASKS if not t.done()]
    if not pending:
        return
    logger.info(
        "Draining %d pending Vision task(s) (%.0fs deadline; D-10.09 / 260509-p1n)...",
        len(pending),
        timeout_s,
    )
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout_s,
        )
        logger.info("Vision tasks drained cleanly")
    except asyncio.TimeoutError:
        still_pending = [t for t in pending if not t.done()]
        logger.warning(
            "Vision drain timeout — %d/%d task(s) still pending (cancelling)",
            len(still_pending),
            len(pending),
        )
        for t in still_pending:
            t.cancel()
        # Give cancelled tasks a brief moment to process CancelledError so
        # their observable side effects (log lines, test assertions) complete.
        if still_pending:
            await asyncio.gather(*still_pending, return_exceptions=True)
