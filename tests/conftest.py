"""Shared pytest fixtures for Phase 4 enrichment tests."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest


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
