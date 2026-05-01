"""D-09.07 (STATE-04): get_rag() contract — flush param + fresh per call.

Tests the public contract without constructing a real LightRAG (heavy init).
Uses monkeypatch to stub ``LightRAG`` + ``initialize_storages`` so the test
runs in <1s without network / file / embedding calls.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def test_get_rag_signature_has_flush_default_true():
    """Signature is ``async def get_rag(flush: bool = True) -> LightRAG`` (D-09.07)."""
    from ingest_wechat import get_rag

    sig = inspect.signature(get_rag)
    params = sig.parameters
    assert list(params.keys()) == ["flush"], f"unexpected params: {list(params.keys())}"
    assert params["flush"].default is True
    assert params["flush"].annotation is bool


def test_get_rag_docstring_documents_contract():
    """Docstring references D-09.07 and explains flush=True vs flush=False (D-09.07)."""
    from ingest_wechat import get_rag

    doc = (get_rag.__doc__ or "")
    assert "flush" in doc.lower()
    assert "D-09.07" in doc or "STATE-04" in doc
    assert "production" in doc.lower() or "default" in doc.lower()


@pytest.mark.asyncio
async def test_get_rag_returns_distinct_instances_per_call():
    """Two successive get_rag() calls return distinct LightRAG objects (D-09.07)."""
    with patch("ingest_wechat.LightRAG") as mock_cls:
        # Each construction returns a fresh MagicMock with an awaitable
        # initialize_storages() so ``await rag.initialize_storages()`` resolves.
        def _new_instance(*_a, **_kw):
            inst = MagicMock()
            inst.initialize_storages = AsyncMock()
            return inst

        mock_cls.side_effect = _new_instance

        from ingest_wechat import get_rag

        a = await get_rag(flush=True)
        b = await get_rag(flush=True)
        assert a is not b
        # Both instances had initialize_storages awaited:
        a.initialize_storages.assert_awaited_once()
        b.initialize_storages.assert_awaited_once()


@pytest.mark.asyncio
async def test_flush_false_also_returns_fresh_instance_today():
    """D-09.07: flush=False is reserved-for-future; current behavior = fresh."""
    with patch("ingest_wechat.LightRAG") as mock_cls:
        def _new_instance(*_a, **_kw):
            inst = MagicMock()
            inst.initialize_storages = AsyncMock()
            return inst

        mock_cls.side_effect = _new_instance

        from ingest_wechat import get_rag

        a = await get_rag(flush=False)
        b = await get_rag(flush=False)
        # Current implementation: fresh per call regardless of flush. Docstring
        # notes flush=False is reserved for future "reuse prior instance".
        assert a is not b


def test_all_production_callers_pass_flush_explicitly():
    """Breaking-change scope: production sites pass flush=True explicitly (D-09.07)."""
    root = Path(__file__).resolve().parents[2]
    production_sites = [
        "ingest_wechat.py",
        "batch_ingest_from_spider.py",
        "enrichment/merge_and_ingest.py",
        "ingest_github.py",
        "multimodal_ingest.py",
    ]
    for site in production_sites:
        src = (root / site).read_text(encoding="utf-8")
        # Each production site that mentions get_rag MUST either define it
        # (ingest_wechat.py) OR call it with flush=True.
        if site == "ingest_wechat.py":
            # Defining site — must show signature ``flush: bool = True``.
            assert "flush: bool = True" in src, f"{site} missing flush signature"
        else:
            # Must NOT call bare get_rag() in production code.
            assert "get_rag(flush=True)" in src, f"{site} missing explicit flush=True"
            # And must not have a bare call that slipped through:
            # Match ``await get_rag()`` with no args — flag it.
            bare_calls = re.findall(r"await\s+get_rag\s*\(\s*\)", src)
            assert not bare_calls, f"{site} has bare get_rag() call(s): {bare_calls}"


def test_spike_scripts_pass_flush_false():
    """Non-production spikes pass flush=False explicitly (D-09.07)."""
    root = Path(__file__).resolve().parents[2]
    for site in ("scripts/wave0_reembed.py", "scripts/phase0_delete_spike.py"):
        path = root / site
        if not path.exists():
            pytest.skip(f"{site} absent")
        src = path.read_text(encoding="utf-8")
        if "get_rag" in src:
            assert "get_rag(flush=False)" in src, \
                f"{site} should use flush=False per D-09.07"
