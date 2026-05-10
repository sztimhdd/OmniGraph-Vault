"""Drive litellm.aembedding directly with each candidate model string.

Quick task 260509-syd — investigation-only. No production-code edits.

What this proves:
- Whether the 422 NOT_FOUND comes from AI Studio (model name unknown) or from
  LiteLLM routing (registry miss → unknown provider behaviour). Bypasses
  Cognee + cognee_wrapper entirely so the only confound is LiteLLM.
- Whether vertex_ai/gemini-embedding-2-preview works when GOOGLE_APPLICATION_
  CREDENTIALS + GOOGLE_CLOUD_PROJECT are set (Path B feasibility check).

What this does NOT prove:
- Whether AI Studio's `gemini-embedding-2` (without -preview) silently routes to
  -preview server-side (the documentation suggests it does NOT, but only a real
  HTTP call settles it).

Run:
    .venv/Scripts/python scripts/cognee_diag/probe_litellm_direct.py

Output:
    .scratch/cognee-diag-litellm-<YYYYMMDD-HHMMSS>.log
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
from typing import Any

os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

# Load ~/.hermes/.env early so the resolved GEMINI_API_KEY matches what
# cognee_wrapper / production code sees (overwrites any stale OS env). Without
# this, the OS-level env may carry an expired key and the probe's "key valid?"
# evidence is invalid.
_HERMES_ENV = Path.home() / ".hermes" / ".env"
if _HERMES_ENV.exists():
    with open(_HERMES_ENV, "r") as f:
        for _line in f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip("'").strip('"')

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH = REPO_ROOT / ".scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)
TS = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = SCRATCH / f"cognee-diag-litellm-{TS}.log"

PER_CALL_TIMEOUT_SEC = 30.0


_FILE_HANDLER: logging.FileHandler | None = None
_STREAM_HANDLER: logging.StreamHandler | None = None


def _setup_logging() -> logging.Logger:
    """Attach file + stream handlers and reapply after first litellm import.

    LiteLLM also tends to call basicConfig under the covers; call
    _reattach_handlers() once the imports are settled.
    """
    global _FILE_HANDLER, _STREAM_HANDLER
    fmt = "%(asctime)s %(levelname)s %(name)s -- %(message)s"
    _FILE_HANDLER = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _FILE_HANDLER.setFormatter(logging.Formatter(fmt))
    _STREAM_HANDLER = logging.StreamHandler(sys.stdout)
    _STREAM_HANDLER.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[_FILE_HANDLER, _STREAM_HANDLER],
        force=True,
    )
    for name in ("litellm", "httpx", "LiteLLM"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    return logging.getLogger("cognee_diag.litellm")


def _reattach_handlers() -> None:
    if _FILE_HANDLER is None or _STREAM_HANDLER is None:
        return
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if _FILE_HANDLER not in root.handlers:
        root.addHandler(_FILE_HANDLER)
    if _STREAM_HANDLER not in root.handlers:
        root.addHandler(_STREAM_HANDLER)


def _redact(value: str | None) -> str:
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]} (len={len(value)})"


def _resolve_gemini_key() -> str | None:
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("OMNIGRAPH_GEMINI_KEY")
        or os.environ.get("COGNEE_LLM_API_KEY")
    )


async def _run_one(
    log: logging.Logger,
    label: str,
    model: str,
    api_key: str | None,
    extra: dict[str, Any] | None = None,
) -> None:
    log.info("-" * 60)
    log.info("PROBE: %s", label)
    log.info("  model     = %r", model)
    log.info("  api_key   = %s", _redact(api_key))
    if extra:
        # Don't dump SA contents — just announce presence
        for k, v in extra.items():
            if isinstance(v, str) and len(v) > 60:
                log.info("  %s = <%d chars>", k, len(v))
            else:
                log.info("  %s = %r", k, v)

    import litellm  # type: ignore

    # First litellm import may install handlers; re-attach ours.
    _reattach_handlers()

    try:
        litellm.set_verbose = True  # type: ignore[attr-defined]
    except Exception:
        pass

    kwargs: dict[str, Any] = {"model": model, "input": ["hello world"]}
    if api_key is not None:
        kwargs["api_key"] = api_key
    if extra:
        kwargs.update(extra)

    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            litellm.aembedding(**kwargs),
            timeout=PER_CALL_TIMEOUT_SEC,
        )
        elapsed = time.monotonic() - start
        # Don't log full vector — just shape
        try:
            data = response.data  # type: ignore[attr-defined]
            n = len(data)
            dim = len(data[0]["embedding"]) if n else 0
            log.info("OK: %s — %d vectors, dim=%d, elapsed=%.2fs", label, n, dim, elapsed)
        except Exception:
            log.info("OK (unexpected shape): %r elapsed=%.2fs", response, elapsed)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        log.error("TIMEOUT %s after %.2fs", label, elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - start
        log.error("FAIL %s after %.2fs: %s", label, elapsed, type(exc).__name__)
        log.error("  exc message = %s", str(exc))
        for attr in ("status_code", "response", "body", "llm_provider"):
            val = getattr(exc, attr, None)
            if val is not None:
                # response objects can be httpx.Response — try .text
                if hasattr(val, "text"):
                    text = getattr(val, "text", None)
                    if isinstance(text, str):
                        # Redact any key= in the URL/body
                        redacted = _redact_keys(text)
                        log.error("  exc.%s.text = %s", attr, redacted[:1000])
                        continue
                log.error("  exc.%s = %r", attr, val)
        log.debug("Traceback:\n%s", traceback.format_exc())


def _redact_keys(text: str) -> str:
    # Strip ?key=... and "key": "..." patterns
    import re

    text = re.sub(r"key=[^&\s\"']+", "key=<REDACTED>", text)
    text = re.sub(r"\"api_key\"\s*:\s*\"[^\"]+\"", "\"api_key\":\"<REDACTED>\"", text)
    return text


async def _amain(log: logging.Logger) -> None:
    api_key = _resolve_gemini_key()
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    log.info("API key resolved: %s", _redact(api_key))
    log.info("SA path:           %s", sa_path or "<unset>")
    log.info("GCP project:       %s", gcp_project or "<unset>")

    # AI Studio probes — the cognee_wrapper-configured value first
    await _run_one(log, "AI-Studio: gemini/gemini-embedding-2 (cognee_wrapper config)",
                   "gemini/gemini-embedding-2", api_key)
    await _run_one(log, "AI-Studio: gemini/gemini-embedding-2-preview (registry-known)",
                   "gemini/gemini-embedding-2-preview", api_key)
    await _run_one(log, "AI-Studio: gemini/gemini-embedding-001 (legacy registry-known)",
                   "gemini/gemini-embedding-001", api_key)

    # Vertex probes — only attempt if SA is configured
    if sa_path and Path(sa_path).exists() and gcp_project:
        # gemini-embedding-2 (no -preview) is GA on global endpoint per
        # CLAUDE.md and lib/lightrag_embedding.py — but LiteLLM's registry only
        # has the -preview entry. Probe both anyway.
        vertex_extra = {
            "vertex_project": gcp_project,
            "vertex_location": os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            "vertex_credentials": sa_path,
        }
        await _run_one(log, "Vertex: vertex_ai/gemini-embedding-2-preview (registry-known)",
                       "vertex_ai/gemini-embedding-2-preview", None, vertex_extra)
        await _run_one(log, "Vertex: vertex_ai/gemini-embedding-2 (production-config)",
                       "vertex_ai/gemini-embedding-2", None, vertex_extra)
    else:
        log.warning("Skipping Vertex probes — GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_PROJECT unset")


def main() -> int:
    log = _setup_logging()
    print(f"[cognee_diag] log file: {LOG_PATH}")
    log.info("=" * 72)
    log.info("cognee_diag.probe_litellm_direct — start %s", TS)
    log.info("PER_CALL_TIMEOUT_SEC = %.1fs", PER_CALL_TIMEOUT_SEC)
    log.info("=" * 72)
    try:
        asyncio.run(_amain(log))
    except Exception:
        log.error("Top-level failure:\n%s", traceback.format_exc())
        return 2
    log.info("=" * 72)
    log.info("cognee_diag.probe_litellm_direct — end")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
