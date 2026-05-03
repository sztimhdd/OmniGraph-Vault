"""Shared pytest fixtures for OmniGraph-Vault tests."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest


# Phase 5 cross-coupling guard: lib/__init__.py eagerly imports
# lib.llm_deepseek which raises at import time if DEEPSEEK_API_KEY is unset.
# Under CI/Windows dev, tests mock all network calls, so the value is never
# actually used — but the import has to succeed. Inject a harmless dummy
# BEFORE any lib import reaches the module-level _require_api_key() call.
# Documented caveat in CLAUDE.md: "use DEEPSEEK_API_KEY=dummy if you don't
# have a real one".
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy-for-tests")


# Phase 13: guard against tests polluting ~/.hermes/omonigraph-vault/checkpoints/_batch/
# by defaulting OMNIGRAPH_VISION_CHECKPOINT_DIR to a per-session tmp dir unless
# a test explicitly overrides it via monkeypatch.
@pytest.fixture(autouse=True, scope="session")
def _isolate_vision_checkpoint_dir():
    prior = os.environ.get("OMNIGRAPH_VISION_CHECKPOINT_DIR")
    if prior is None:
        td = tempfile.mkdtemp(prefix="ogv-vision-ckpt-")
        os.environ["OMNIGRAPH_VISION_CHECKPOINT_DIR"] = td
        yield
        os.environ.pop("OMNIGRAPH_VISION_CHECKPOINT_DIR", None)
    else:
        yield


@pytest.fixture
def tmp_base_dir(tmp_path: Path) -> Path:
    """A temporary directory that mirrors ~/.hermes/omonigraph-vault/."""
    base = tmp_path / "omonigraph-vault"
    (base / "lightrag_storage").mkdir(parents=True)
    (base / "images").mkdir()
    (base / "enrichment").mkdir()
    (base / "entity_buffer").mkdir()
    return base


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_gemini_client(mocker):
    """Mock google.genai.Client — returns a client whose generate_content returns stub text."""
    client = MagicMock()
    response = MagicMock()
    response.text = "stub gemini response"
    response.candidates = [MagicMock(grounding_metadata=MagicMock(grounding_chunks=[]))]
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def mock_lightrag(mocker):
    """Mock LightRAG instance with async ainsert / adelete_by_doc_id."""
    rag = MagicMock()

    async def _ainsert(*a, **kw):
        return "stub-track-id"

    async def _adelete(*a, **kw):
        r = MagicMock()
        r.status = "success"
        r.status_code = 200
        return r

    rag.ainsert = _ainsert
    rag.adelete_by_doc_id = _adelete
    return rag


@pytest.fixture
def mock_requests_get(mocker):
    """Mock requests.get for image download tests — returns 200 with bytes body."""
    m = mocker.patch("requests.get")
    m.return_value.status_code = 200
    m.return_value.content = b"\xff\xd8\xff\xe0FAKE_JPEG_BYTES"
    return m


# ---------------------------------------------------------------------------
# Phase 7 lib/ fixtures (D-06: mock at lib.llm_client level)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_lib_llm(mocker):
    """Mock at lib.llm_client.generate / lib.llm_client.aembed / lib.llm_client.generate_sync (D-06).

    Replaces per-call-site google.genai.Client patches. Any test importing a
    production module can patch here once and cover every LLM touchpoint.
    Note: _fake_generate uses `contents` param (Amendment 5).
    """
    from lib.models import EMBEDDING_DIM

    async def _fake_generate(model, contents, **kwargs):
        return "stub lib generate response"

    async def _fake_aembed(model, texts, **kwargs):
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    gen = mocker.patch("lib.llm_client.generate", side_effect=_fake_generate)
    aem = mocker.patch("lib.llm_client.aembed", side_effect=_fake_aembed)
    sync_gen = mocker.patch("lib.llm_client.generate_sync", return_value="stub sync generate response")
    return {"generate": gen, "aembed": aem, "generate_sync": sync_gen}


@pytest.fixture
def reset_lib_state(monkeypatch):
    """Reset lib/ module-level state between tests (rotation cycle, limiter registry)."""
    import lib.api_keys as k
    import lib.rate_limit as r
    k._cycle = None
    k._current = None
    k._rotation_listeners.clear()
    r._limiters.clear()
    # Also reset llm_client cached client
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None
    yield
