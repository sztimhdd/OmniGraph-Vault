"""Inspect what cognee + litellm actually resolve to after cognee_wrapper imports.

Quick task 260509-syd — investigation-only. No production-code edits.

What this proves:
- The values cognee_wrapper sets via os.environ at import time
- The EmbeddingConfig + LLMConfig snapshots Cognee 1.0 ends up using
- Whether LiteLLM's model registry recognises the model strings cognee_wrapper
  configures (gemini/gemini-embedding-2 vs vertex_ai/gemini-embedding-2-preview)

What this does NOT prove:
- What the live AI Studio / Vertex endpoint returns for those model strings
  (see probe_litellm_direct.py for that)

Run:
    .venv/Scripts/python scripts/cognee_diag/inspect_cognee_routing.py

Output:
    .scratch/cognee-diag-inspect-<YYYYMMDD-HHMMSS>.log (full stdout + stderr)
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
import traceback
from importlib import metadata
from pathlib import Path

# Phase 5 cross-coupling defense — lib/__init__.py:35 eagerly imports
# deepseek_model_complete which raises at import time without DEEPSEEK_API_KEY.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH = REPO_ROOT / ".scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)
TS = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = SCRATCH / f"cognee-diag-inspect-{TS}.log"


_FILE_HANDLER: logging.FileHandler | None = None
_STREAM_HANDLER: logging.StreamHandler | None = None


def _setup_logging() -> logging.Logger:
    """Force-attach our handlers to root, then re-attach them after cognee imports.

    Cognee 1.0 installs its own logging_utils on first import which calls
    logging.basicConfig — replacing handlers. We attach handlers and then call
    _reattach_handlers() AFTER cognee_wrapper imports to re-install them.
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
    return logging.getLogger("cognee_diag.inspect")


def _reattach_handlers() -> None:
    """Re-install our handlers on root after cognee's basicConfig hijacks them."""
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


def _safe_version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except Exception as exc:  # noqa: BLE001
        return f"<error: {exc!r}>"


def _dump_env_baseline(log: logging.Logger) -> None:
    log.info("--- ENV BASELINE (pre-import) ---")
    for var in (
        "OMNIGRAPH_COGNEE_INLINE",
        "OMNIGRAPH_LLM_PROVIDER",
        "OMNIGRAPH_LLM_MODEL",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ):
        log.info("  %s = %r", var, os.environ.get(var, "<unset>"))
    for keyvar in (
        "GEMINI_API_KEY",
        "OMNIGRAPH_GEMINI_KEY",
        "GEMINI_API_KEY_BACKUP",
        "OMNIGRAPH_GEMINI_KEYS",
    ):
        log.info("  %s = %s", keyvar, _redact(os.environ.get(keyvar)))


def _import_cognee_wrapper(log: logging.Logger) -> object | None:
    log.info("--- IMPORTING cognee_wrapper (this triggers env mutations) ---")
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import cognee_wrapper  # type: ignore  # noqa: F401

        log.info("cognee_wrapper imported OK")
        return cognee_wrapper
    except Exception:
        log.error("cognee_wrapper import failed:\n%s", traceback.format_exc())
        return None


def _dump_env_post_import(log: logging.Logger) -> None:
    log.info("--- ENV AFTER cognee_wrapper IMPORT (the values Cognee actually sees) ---")
    for var in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "COGNEE_SKIP_CONNECTION_TEST",
        "ENABLE_BACKEND_ACCESS_CONTROL",
    ):
        log.info("  %s = %r", var, os.environ.get(var, "<unset>"))
    for keyvar in (
        "COGNEE_LLM_API_KEY",
        "LITELLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_API_KEY",
    ):
        log.info("  %s = %s", keyvar, _redact(os.environ.get(keyvar)))


def _dump_cognee_configs(log: logging.Logger) -> None:
    log.info("--- COGNEE LLMConfig + EmbeddingConfig SNAPSHOT ---")
    try:
        from cognee.infrastructure.llm.config import get_llm_config

        llm_cfg = get_llm_config()
        log.info("LLMConfig.llm_provider = %r", llm_cfg.llm_provider)
        log.info("LLMConfig.llm_model    = %r", llm_cfg.llm_model)
        log.info("LLMConfig.llm_endpoint = %r", llm_cfg.llm_endpoint)
        log.info("LLMConfig.llm_api_key  = %s", _redact(llm_cfg.llm_api_key))
    except Exception:
        log.error("LLMConfig fetch failed:\n%s", traceback.format_exc())

    try:
        from cognee.infrastructure.databases.vector.embeddings.config import (
            get_embedding_config,
        )

        emb_cfg = get_embedding_config()
        log.info("EmbeddingConfig.embedding_provider   = %r", emb_cfg.embedding_provider)
        log.info("EmbeddingConfig.embedding_model      = %r", emb_cfg.embedding_model)
        log.info("EmbeddingConfig.embedding_dimensions = %r", emb_cfg.embedding_dimensions)
        log.info("EmbeddingConfig.embedding_endpoint   = %r", emb_cfg.embedding_endpoint)
        log.info("EmbeddingConfig.embedding_api_key    = %s", _redact(emb_cfg.embedding_api_key))
    except Exception:
        log.error("EmbeddingConfig fetch failed:\n%s", traceback.format_exc())


def _dump_litellm_registry(log: logging.Logger) -> None:
    log.info("--- LITELLM MODEL REGISTRY LOOKUP ---")
    try:
        import litellm  # type: ignore
    except Exception:
        log.error("litellm import failed:\n%s", traceback.format_exc())
        return

    try:
        registry = getattr(litellm, "model_cost", {}) or {}
    except Exception:
        log.error("litellm.model_cost access failed:\n%s", traceback.format_exc())
        registry = {}
    log.info("litellm.model_cost size = %d entries", len(registry))

    candidates = [
        # cognee_wrapper currently configures this (suspect broken):
        "gemini-embedding-2",
        "gemini/gemini-embedding-2",
        # Registry-known AI Studio names:
        "gemini-embedding-2-preview",
        "gemini/gemini-embedding-2-preview",
        "gemini-embedding-001",
        "gemini/gemini-embedding-001",
        # Registry-known Vertex names:
        "vertex_ai/gemini-embedding-2-preview",
    ]
    for name in candidates:
        entry = registry.get(name)
        if entry:
            slim = {
                k: entry.get(k)
                for k in ("litellm_provider", "mode", "uses_embed_content", "max_input_tokens")
            }
            log.info("  REGISTERED: %-45s -> %s", name, json.dumps(slim, default=str))
        else:
            log.info("  MISSING:    %-45s (not in registry)", name)


def _dump_versions(log: logging.Logger) -> None:
    log.info("--- VERSIONS ---")
    log.info("python      = %s", sys.version.split()[0])
    log.info("cognee      = %s", _safe_version("cognee"))
    log.info("litellm     = %s", _safe_version("litellm"))
    log.info("google-genai= %s", _safe_version("google-genai"))


def main() -> int:
    log = _setup_logging()
    print(f"[cognee_diag] log file: {LOG_PATH}")
    log.info("=" * 72)
    log.info("cognee_diag.inspect_cognee_routing — start %s", TS)
    log.info("=" * 72)
    _dump_versions(log)
    _dump_env_baseline(log)
    if _import_cognee_wrapper(log) is None:
        log.error("Aborting: cognee_wrapper failed to import; remaining probes skipped.")
        return 2
    # Cognee's logging_utils calls basicConfig at import time, overriding our
    # handlers. Re-attach them so the rest of the probe logs to file.
    _reattach_handlers()
    log.info("Re-attached file handler post-import (cognee may hijack basicConfig)")
    _dump_env_post_import(log)
    _dump_cognee_configs(log)
    _dump_litellm_registry(log)
    log.info("=" * 72)
    log.info("cognee_diag.inspect_cognee_routing — end")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
