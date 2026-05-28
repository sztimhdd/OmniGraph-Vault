"""P5 SC#1+SC#3: lifespan-pinned LightRAG singleton — same instance across requests.

Uses FastAPI's TestClient context-manager protocol which fires lifespan startup
+ shutdown; we then directly inspect ``app.state.lightrag`` to assert id()
stability. Does NOT require a real running uvicorn — TestClient runs the app
in-process.

LightRAG is mocked at the import site (``kb.api.LightRAG``) so the lifespan
runs without hydrating the real graph + vdb (which on this dev machine is
768-dim while config expects 3072-dim — a runtime concern not gated by P5).
The assertions target the lifespan WIRING (id-stability, finalize log line),
not LightRAG semantics.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_mock_lightrag(monkeypatch):
    """Patch the LightRAG import inside kb.api so lifespan builds a stub."""
    fake_rag = MagicMock(name="fake_LightRAG_instance")
    fake_rag.initialize_storages = AsyncMock()
    fake_rag.finalize_storages = AsyncMock()

    def _factory(*_a, **_kw):
        return fake_rag

    import kb.api as kb_api
    monkeypatch.setattr(kb_api, "LightRAG", _factory)
    return kb_api.app, fake_rag


@pytest.mark.integration
def test_lifespan_singleton_id_stable_across_requests(app_with_mock_lightrag) -> None:
    app, fake_rag = app_with_mock_lightrag
    with TestClient(app) as client:
        # /health is the cheapest way to confirm the app is fully booted post-lifespan.
        r1 = client.get("/health")
        assert r1.status_code == 200, r1.text
        assert app.state.lightrag is fake_rag
        assert app.state.lightrag_lock is not None
        id_1 = id(app.state.lightrag)

        r2 = client.get("/health")
        assert r2.status_code == 200, r2.text
        id_2 = id(app.state.lightrag)

        assert id_1 == id_2, (
            f"app.state.lightrag was reconstructed between requests "
            f"(id changed: {id_1} -> {id_2}); lifespan singleton broken"
        )


@pytest.mark.integration
def test_lifespan_finalize_called_on_shutdown(app_with_mock_lightrag, caplog) -> None:
    """SC#4: finalize_storages is called when lifespan exits."""
    app, fake_rag = app_with_mock_lightrag
    caplog.set_level(logging.WARNING, logger="kb.api")
    with TestClient(app) as client:
        client.get("/health")  # ensures full lifespan startup
    # After the with-block exits, lifespan finally: ran
    fake_rag.finalize_storages.assert_awaited_once()
    assert any(
        "lightrag_singleton_finalize_done" in rec.message
        for rec in caplog.records
    ), [r.message for r in caplog.records]
