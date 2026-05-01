"""TIMEOUT-01: LightRAG respects LLM_TIMEOUT env var (D-09.01).

Verifies that LightRAG's `default_llm_timeout` dataclass field default is
initialized from ``os.getenv("LLM_TIMEOUT", 180)`` at class-definition time.
Therefore these tests MUST set the env var BEFORE importing/re-importing
``lightrag.lightrag``.

Also includes a source-level smoke test that the production entry-point
scripts set ``LLM_TIMEOUT=600`` via ``os.environ.setdefault`` at module top.
"""
from __future__ import annotations

import dataclasses
import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_lightrag_env(monkeypatch):
    """Drop LLM_TIMEOUT and any cached lightrag modules before each test.

    Without this, a prior test's reload pins the dataclass field default and
    the next test sees stale state.
    """
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    for mod_name in list(sys.modules):
        if mod_name == "lightrag" or mod_name.startswith("lightrag."):
            sys.modules.pop(mod_name, None)


def test_default_llm_timeout_reads_env_300(monkeypatch) -> None:
    """LLM_TIMEOUT=300 env var propagates to LightRAG.default_llm_timeout."""
    monkeypatch.setenv("LLM_TIMEOUT", "300")
    import lightrag.lightrag as lr

    # Reload so the @dataclass field default re-evaluates os.getenv.
    importlib.reload(lr)
    fields = {f.name: f for f in dataclasses.fields(lr.LightRAG)}
    assert fields["default_llm_timeout"].default == 300


def test_default_llm_timeout_unset_falls_back_to_180(monkeypatch) -> None:
    """Without LLM_TIMEOUT, LightRAG uses its internal DEFAULT_LLM_TIMEOUT (180)."""
    # Fixture already deletes LLM_TIMEOUT.
    import lightrag.lightrag as lr

    importlib.reload(lr)
    fields = {f.name: f for f in dataclasses.fields(lr.LightRAG)}
    assert fields["default_llm_timeout"].default == 180


def test_production_entry_points_set_default_600() -> None:
    """Smoke: production entry points set LLM_TIMEOUT=600 at module top.

    Scans source for the setdefault line — avoids importing heavy modules.
    Guards D-09.01: the env must be set BEFORE LightRAG is imported anywhere
    in the process. A regression where an editor moves the `setdefault` below
    a `from lightrag...` import would silently break the 600s timeout.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]  # repo root
    for target in ("ingest_wechat.py", "batch_ingest_from_spider.py", "run_uat_ingest.py"):
        src = (root / target).read_text(encoding="utf-8")
        assert 'setdefault("LLM_TIMEOUT", "600")' in src, (
            f"{target} missing LLM_TIMEOUT=600 setdefault (D-09.01)"
        )
