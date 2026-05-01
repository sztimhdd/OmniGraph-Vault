"""D-09.04 (STATE-01): pre-batch flush — get_rag(flush=True) produces fresh instance.

The observable truth: every entry point calls get_rag with flush=True and each
call returns a fresh LightRAG (covered structurally by test_get_rag_contract).
This test verifies the ENTRY POINTS use the flush=True path — catches a regression
where a future refactor reverts to bare get_rag().
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def _src(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / rel_path).read_text(encoding="utf-8")


def test_batch_run_uses_flush_true():
    """batch_ingest_from_spider.run calls get_rag(flush=True) at pre-batch init."""
    src = _src("batch_ingest_from_spider.py")
    # Require at least two flush=True call sites (run + ingest_from_db).
    assert src.count("get_rag(flush=True)") >= 2, \
        "batch_ingest_from_spider must call get_rag(flush=True) at both batch entry points"


def test_state01_comment_present():
    """Pre-batch flush log references STATE-01 / D-09.04 for traceability."""
    src = _src("batch_ingest_from_spider.py")
    assert "STATE-01" in src or "D-09.04" in src, \
        "batch_ingest_from_spider.py pre-batch flush comment must reference STATE-01"
