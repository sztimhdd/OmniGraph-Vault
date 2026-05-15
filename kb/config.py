"""KB-v2 env-driven configuration — single source of truth for paths and ports.

CONFIG-01: All KB paths and ports configurable via env vars with documented
defaults. NO hardcoded paths anywhere else in kb/. Verified by:
    grep -rE "/.hermes|kol_scan.db" kb/ --include='*.py' --exclude=config.py
must return 0 hits in kb/ (matches in tests/ are OK).
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_path(key: str, default: Path) -> Path:
    """Read env var as Path; empty string treated as unset (mirrors main config.py)."""
    val = os.environ.get(key)
    return Path(val) if val else default


def _env_int(key: str, default: int) -> int:
    """Read env var as int; non-numeric falls back to default."""
    val = os.environ.get(key)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


# Constants are computed at module-import time. To support test override after
# first import, callers can `importlib.reload(kb.config)` after monkeypatching
# the env vars — see tests/unit/kb/test_config.py.
KB_DB_PATH: Path = _env_path("KB_DB_PATH", Path.home() / ".hermes" / "data" / "kol_scan.db")
KB_IMAGES_DIR: Path = _env_path(
    "KB_IMAGES_DIR",
    Path.home() / ".hermes" / "omonigraph-vault" / "images",  # 'omonigraph' typo is canonical
)
KB_OUTPUT_DIR: Path = _env_path("KB_OUTPUT_DIR", Path("kb/output"))
KB_PORT: int = _env_int("KB_PORT", 8766)
KB_DEFAULT_LANG: str = os.environ.get("KB_DEFAULT_LANG") or "zh-CN"
KB_SYNTHESIZE_TIMEOUT: int = _env_int("KB_SYNTHESIZE_TIMEOUT", 60)


# Subdirectory deploy prefix — empty = served at site root (default).
# Aliyun ECS deploys under `/kb/` (Caddy reverse-proxy), so set
# KB_BASE_PATH=/kb at export time + template paths emit `/kb/static/...`,
# `/kb/articles/...` etc. Trailing slashes stripped for clean
# `{{ base_path }}/static/...` concatenation in templates.
_kb_base_raw: str = os.environ.get("KB_BASE_PATH", "")
KB_BASE_PATH: str = _kb_base_raw.rstrip("/") if _kb_base_raw else ""


# kb-v2.1-1 KG-mode hardening: optional KB-namespaced override for the GCP SA
# JSON path used by LightRAG embedding (Vertex mode). Falls back to the
# upstream `GOOGLE_APPLICATION_CREDENTIALS` env var so existing deployments
# keep working without change. Returns None when neither is set — the kb
# services layer reads this and proactively verifies the file exists at
# module-import time, gating /api/search?mode=kg on a controlled flag.
def _resolve_kg_sa_key_path() -> Path | None:
    val = os.environ.get("KB_KG_GCP_SA_KEY_PATH") or \
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return Path(val) if val else None


KB_KG_GCP_SA_KEY_PATH: Path | None = _resolve_kg_sa_key_path()
