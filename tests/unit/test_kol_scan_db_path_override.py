"""
Mock-only regression tests for KOL_SCAN_DB_PATH env override propagation.

Quick task 260504-lt2 propagated the af6f5bc pattern (originally applied to
`batch_ingest_from_spider.py:86` in Quick 260504-g7a/e2e) across 11 more
modules. Each module must:

1. Read `KOL_SCAN_DB_PATH` at import time via ``os.environ.get``.
2. Fall back to the module's pre-existing default path when the env is unset
   (byte-identical to pre-change behavior — Hermes production zero breaking
   change).
3. NOT hardcode the `data/kol_scan.db` path anywhere that would bypass the
   override.

These tests execute each import in a subprocess so that module-level
assignments (``DB = Path(os.environ.get(...))``) are re-evaluated under the
correct env. No network / no real DB access.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PYEXE = sys.executable


# (module_dotted, attr_name)
MODULES = [
    ("batch_classify_kol", "DB_PATH"),
    ("batch_scan_kol", "DB_PATH"),
    ("ingest_wechat", "DB_PATH"),
    ("kg_synthesize", "DB_PATH"),
    ("cognee_batch_processor", "DB_PATH"),
    ("enrichment.daily_digest", "DB"),
    ("enrichment.orchestrate_daily", "DB"),
    ("enrichment.rss_classify", "DB"),
    ("enrichment.rss_fetch", "DB"),
    ("enrichment.rss_ingest", "DB"),
    ("enrichment.run_enrich_for_id", "DB"),
]


def _probe(module: str, attr: str, env_value: str | None) -> str:
    """Import module in a fresh subprocess and return str(module.<attr>)."""
    snippet = (
        "import os, sys\n"
        # Satisfy the Phase 5 eager DeepSeek import without touching the network.
        "os.environ.setdefault('DEEPSEEK_API_KEY', 'dummy')\n"
        f"env = {env_value!r}\n"
        "if env is None:\n"
        "    os.environ.pop('KOL_SCAN_DB_PATH', None)\n"
        "else:\n"
        "    os.environ['KOL_SCAN_DB_PATH'] = env\n"
        f"import {module} as m\n"
        f"sys.stdout.write(str(m.{attr}))\n"
    )
    result = subprocess.run(
        [PYEXE, "-c", snippet],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"subprocess import of {module} failed (exit={result.returncode}):\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr[-2000:]}"
        )
    return result.stdout.strip()


@pytest.mark.unit
@pytest.mark.parametrize("module,attr", MODULES, ids=[m for m, _ in MODULES])
def test_env_override_routes_to_custom_path(module: str, attr: str) -> None:
    """With KOL_SCAN_DB_PATH set, every module must resolve to that path."""
    custom = "z:/mock/custom_kol.db"
    got = _probe(module, attr, custom)
    assert Path(got) == Path(custom), (
        f"{module}.{attr} did not pick up KOL_SCAN_DB_PATH env: got {got!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("module,attr", MODULES, ids=[m for m, _ in MODULES])
def test_env_unset_preserves_default_fallback(module: str, attr: str) -> None:
    """Without KOL_SCAN_DB_PATH, DB must fall back to the pre-change default.

    The default ends in 'data/kol_scan.db' (or 'data\\kol_scan.db' on Windows).
    Exact prefix differs per module (absolute vs. CWD-relative), so we only
    assert the trailing path component for byte-identical fallback suffix.
    """
    got = _probe(module, attr, None)
    got_norm = got.replace("\\", "/")
    assert got_norm.endswith("data/kol_scan.db"), (
        f"{module}.{attr} fallback drifted from 'data/kol_scan.db': got {got!r}"
    )


@pytest.mark.unit
def test_batch_ingest_from_spider_pattern_is_the_reference() -> None:
    """The original af6f5bc file must still carry the override (sanity).

    If someone reverts batch_ingest_from_spider.py to the hardcoded form, the
    whole KOL_SCAN_DB_PATH abstraction becomes inconsistent. Pin it.
    """
    src = (REPO_ROOT / "batch_ingest_from_spider.py").read_text(encoding="utf-8")
    assert "KOL_SCAN_DB_PATH" in src and "os.environ.get" in src, (
        "batch_ingest_from_spider.py no longer reads KOL_SCAN_DB_PATH env; "
        "the lt2 propagation depends on this pattern."
    )
