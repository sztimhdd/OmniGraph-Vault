"""D-10.09 / 260509-p1n: drain_vision_tasks dedicated-set semantics.

Three deterministic cases against ``lib.vision_tracking`` directly:

1. ``test_drain_completes_within_timeout`` — 3 short tasks (sleep 0.05) drain
   cleanly inside the 1.0 s deadline; ``_VISION_TASKS`` empties on its own
   via the ``add_done_callback`` discard hook.
2. ``test_drain_timeout_cancels_pending`` — 2 long tasks (sleep 60) exceed a
   0.1 s deadline; the drain cancels them and emits a WARNING line; total
   wall-clock stays well under 2 s (proves the cap fires, not a fallthrough
   to a 60 s sleep).
3. ``test_drain_no_pending_is_noop`` — empty set, no log line, sub-0.1 s
   wall-clock.

All tests use real ``asyncio.create_task(asyncio.sleep(...))`` — no mocking
of ``drain_vision_tasks`` itself.
"""
from __future__ import annotations

import asyncio
import logging
import time

import pytest


@pytest.fixture(autouse=True)
def _clear_vision_tasks():
    """Clear ``_VISION_TASKS`` before+after every test so prior bleed is impossible."""
    from lib import vision_tracking

    vision_tracking._VISION_TASKS.clear()
    yield
    vision_tracking._VISION_TASKS.clear()


@pytest.mark.asyncio
async def test_drain_completes_within_timeout(caplog):
    """Drain returns clean for short tasks; the set empties via done-callback."""
    from lib import vision_tracking

    tasks = [
        vision_tracking.track_vision_task(asyncio.create_task(asyncio.sleep(0.05)))
        for _ in range(3)
    ]

    with caplog.at_level(logging.INFO, logger="lib.vision_tracking"):
        start = time.perf_counter()
        await vision_tracking.drain_vision_tasks(timeout_s=1.0)
        elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"drain should finish well under 1 s, took {elapsed:.3f}s"
    for t in tasks:
        assert t.done(), "task did not complete"
        assert not t.cancelled(), "task should have completed naturally, not been cancelled"
    assert vision_tracking._VISION_TASKS == set(), (
        "_VISION_TASKS should be empty after natural completion via add_done_callback"
    )
    # No WARNING log; the INFO "drained cleanly" line is allowed.
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == [], f"unexpected warning(s): {warnings}"


@pytest.mark.asyncio
async def test_drain_timeout_cancels_pending(caplog):
    """Tasks exceeding the deadline are cancelled; WARNING line emitted; wall-clock bounded."""
    from lib import vision_tracking

    tasks = [
        vision_tracking.track_vision_task(asyncio.create_task(asyncio.sleep(60)))
        for _ in range(2)
    ]

    with caplog.at_level(logging.WARNING, logger="lib.vision_tracking"):
        start = time.perf_counter()
        await vision_tracking.drain_vision_tasks(timeout_s=0.1)
        elapsed = time.perf_counter() - start

    assert elapsed < 2.0, (
        f"drain must respect the 0.1 s cap (proves no fallthrough to the 60 s sleep), "
        f"took {elapsed:.3f}s"
    )
    for t in tasks:
        assert t.cancelled(), "task should have been cancelled by drain timeout"
    assert vision_tracking._VISION_TASKS == set(), (
        "_VISION_TASKS should drain via the discard callback after cancellation"
    )
    warning_msgs = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("still pending" in m or "cancelling" in m for m in warning_msgs), (
        f"expected WARNING containing 'still pending' or 'cancelling'; got {warning_msgs!r}"
    )


@pytest.mark.asyncio
async def test_drain_no_pending_is_noop(caplog):
    """Empty set → no await, no log line, near-zero wall-clock."""
    from lib import vision_tracking

    assert vision_tracking._VISION_TASKS == set(), "fixture should leave the set empty"

    with caplog.at_level(logging.DEBUG, logger="lib.vision_tracking"):
        start = time.perf_counter()
        await vision_tracking.drain_vision_tasks(timeout_s=0.1)
        elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"no-op drain should be near-instant, took {elapsed:.3f}s"
    lib_records = [r for r in caplog.records if r.name == "lib.vision_tracking"]
    assert lib_records == [], (
        f"no-op drain should not emit any log lines; got {[r.getMessage() for r in lib_records]!r}"
    )
