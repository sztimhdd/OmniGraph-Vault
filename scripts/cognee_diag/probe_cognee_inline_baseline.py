"""Exercise the failing inline path: cognee.remember(...) with cognee_wrapper config.

Quick task 260509-syd — investigation-only. No production-code edits.

What this proves:
- Whether the actual cognee_wrapper-configured embedding flow can complete a
  single round-trip (success path) or what it fails with (likely 422 NOT_FOUND
  loop wrapped in tenacity retries)
- Wall-clock duration of the failure (should be ~128s if tenacity exhausts the
  stop_after_delay budget)

What this does NOT prove:
- Whether the failure happens at the embedding step or earlier (entity
  extraction LLM step). Wrap with timeout so even a hang yields evidence.

Run:
    .venv/Scripts/python scripts/cognee_diag/probe_cognee_inline_baseline.py

Output:
    .scratch/cognee-diag-inline-<YYYYMMDD-HHMMSS>.log
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ["OMNIGRAPH_COGNEE_INLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH = REPO_ROOT / ".scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)
TS = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = SCRATCH / f"cognee-diag-inline-{TS}.log"

# 60s wall-clock cap. cognee.remember() under tenacity has stop_after_delay(128s),
# so 60s won't catch the full retry cycle but will prove the call is blocking.
WALL_TIMEOUT_SEC = 60.0


_FILE_HANDLER: logging.FileHandler | None = None
_STREAM_HANDLER: logging.StreamHandler | None = None


def _setup_logging() -> logging.Logger:
    """Force-attach handlers; cognee's basicConfig at import time will hijack —
    callers must invoke _reattach_handlers() after the cognee_wrapper import.
    """
    global _FILE_HANDLER, _STREAM_HANDLER
    fmt = "%(asctime)s %(levelname)s %(name)s -- %(message)s"
    _FILE_HANDLER = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _FILE_HANDLER.setFormatter(logging.Formatter(fmt))
    _STREAM_HANDLER = logging.StreamHandler(sys.stdout)
    _STREAM_HANDLER.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(
        level=logging.DEBUG,
        format=fmt,
        handlers=[_FILE_HANDLER, _STREAM_HANDLER],
        force=True,
    )
    for name in ("litellm", "httpx", "LiteLLM", "LiteLLMEmbeddingEngine"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    return logging.getLogger("cognee_diag.inline")


def _reattach_handlers() -> None:
    if _FILE_HANDLER is None or _STREAM_HANDLER is None:
        return
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if _FILE_HANDLER not in root.handlers:
        root.addHandler(_FILE_HANDLER)
    if _STREAM_HANDLER not in root.handlers:
        root.addHandler(_STREAM_HANDLER)


async def _run_remember(log: logging.Logger) -> None:
    sys.path.insert(0, str(REPO_ROOT))
    log.info("Importing cognee_wrapper (will mutate env)")
    import cognee_wrapper  # type: ignore

    # Re-attach handlers — cognee_wrapper -> cognee -> logging_utils calls
    # basicConfig at import time, removing our file handler.
    _reattach_handlers()
    log.info("Re-attached file handler post-import")

    if cognee_wrapper.cognee is None:
        log.error("cognee_wrapper.cognee is None — Cognee SDK not available")
        return

    log.info("Calling cognee.remember(...) with WALL_TIMEOUT_SEC=%.1fs", WALL_TIMEOUT_SEC)
    start = time.monotonic()
    try:
        await asyncio.wait_for(
            cognee_wrapper.cognee.remember(
                "diagnostic article: hello world from cognee_diag probe",
                dataset_name="cognee_diag",
                self_improvement=False,
            ),
            timeout=WALL_TIMEOUT_SEC,
        )
        elapsed = time.monotonic() - start
        log.info("remember() returned cleanly in %.2fs (UNEXPECTED if 422 hypothesis holds)", elapsed)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        log.error(
            "remember() exceeded wall-clock %.1fs — TIMEOUT (consistent with retry-loop hypothesis)",
            elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - start
        log.error("remember() raised after %.2fs: %r", elapsed, exc)
        log.error("Traceback:\n%s", traceback.format_exc())
        # Try to extract HTTP body / status code if exception carries one
        for attr in ("response", "status_code", "message", "body", "args"):
            val = getattr(exc, attr, None)
            if val is not None:
                log.error("  exc.%s = %r", attr, val)


def main() -> int:
    log = _setup_logging()
    print(f"[cognee_diag] log file: {LOG_PATH}")
    log.info("=" * 72)
    log.info("cognee_diag.probe_cognee_inline_baseline — start %s", TS)
    log.info("OMNIGRAPH_COGNEE_INLINE = %r", os.environ.get("OMNIGRAPH_COGNEE_INLINE"))
    log.info("WALL_TIMEOUT_SEC = %.1fs", WALL_TIMEOUT_SEC)
    log.info("=" * 72)
    try:
        asyncio.run(_run_remember(log))
    except Exception:
        log.error("Top-level failure:\n%s", traceback.format_exc())
        return 2
    log.info("=" * 72)
    log.info("cognee_diag.probe_cognee_inline_baseline — end")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
