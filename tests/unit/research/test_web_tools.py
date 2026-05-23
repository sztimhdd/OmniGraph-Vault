"""Unit tests for ar-3 Wave 1 web tools — TOOL-01, TOOL-02, TEST-02, CONFIG-03 env-half.

Three groups:
  1. Callable-shape (3 tests, mock httpx.AsyncClient): tavily_search, tavily_extract, brave_search.
  2. Cascade behavior (3 tests, mock primary/fallback as AsyncMock): success path, fallback path, per-call independence.
  3. from_env() integration (3 tests, monkeypatch env + lazy-import patches): no keys, Tavily only, both keys.

NO live HTTP — every external call is patched.
"""
from __future__ import annotations

import functools
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lib.research.tools.web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
)


# ---------------------------------------------------------------------------
# Group 1 — Callable-shape tests (mock httpx.AsyncClient)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_tavily_search_returns_list_of_dicts():
    """Mock httpx response; assert tavily_search returns list[dict] with expected keys."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "results": [
            {"title": "T1", "url": "https://e.com/1", "content": "c1", "score": 0.9},
            {"title": "T2", "url": "https://e.com/2", "content": "c2", "score": 0.7},
        ],
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await tavily_search("test query", api_key="fake_key", top_k=10)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(r, dict) for r in result)
    assert result[0]["title"] == "T1"
    assert "url" in result[0]
    assert "content" in result[0]
    assert "score" in result[0]


@pytest.mark.unit
async def test_tavily_extract_returns_str():
    """Mock httpx response; assert tavily_extract returns str containing raw_content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "results": [{"url": "https://e.com/x", "raw_content": "extracted markdown body"}],
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await tavily_extract("https://e.com/x", api_key="fake_key")

    assert isinstance(result, str)
    assert "extracted markdown body" in result


@pytest.mark.unit
async def test_brave_search_returns_list_of_dicts():
    """Mock httpx response; assert brave_search returns list[dict] with description→content normalization."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "web": {"results": [
            {"title": "B1", "url": "https://e.com/b1", "description": "bc1"},
            {"title": "B2", "url": "https://e.com/b2", "description": "bc2"},
        ]},
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await brave_search("brave query", api_key="fake_key", top_k=10)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["title"] == "B1"
    assert "url" in result[0]
    assert "content" in result[0]  # brave_search normalizes 'description' → 'content'
    assert result[0]["content"] == "bc1"


# ---------------------------------------------------------------------------
# Group 2 — Cascade behavior tests (mock primary/fallback directly — no httpx)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cascade_calls_primary_only_on_success():
    """When primary succeeds, fallback is never called (TEST-02 negative case)."""
    primary = AsyncMock(return_value=[{"title": "P", "url": "u", "content": "c"}])
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    result = await cascade("q")

    assert result == [{"title": "P", "url": "u", "content": "c"}]
    assert primary.await_count == 1
    assert fallback.await_count == 0


@pytest.mark.unit
async def test_cascade_falls_back_exactly_once_on_primary_exception():
    """When primary raises, fallback called exactly once and its result returned (TEST-02 positive case)."""
    primary = AsyncMock(side_effect=httpx.TimeoutException("primary timed out"))
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    result = await cascade("q")

    assert result == [{"title": "F", "url": "u", "content": "c"}]
    assert primary.await_count == 1
    assert fallback.await_count == 1


@pytest.mark.unit
async def test_cascade_per_call_independence():
    """Failure on call N does NOT disable primary for call N+1 (TEST-02 independence)."""
    # Primary: raises on call 1, succeeds on call 2.
    primary = AsyncMock(side_effect=[
        httpx.TimeoutException("call-1 boom"),
        [{"title": "P2", "url": "u", "content": "c"}],
    ])
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    r1 = await cascade("q1")
    r2 = await cascade("q2")

    assert r1 == [{"title": "F", "url": "u", "content": "c"}]
    assert r2 == [{"title": "P2", "url": "u", "content": "c"}]
    assert primary.await_count == 2  # called fresh each time
    assert fallback.await_count == 1  # only call 1 needed fallback


# ---------------------------------------------------------------------------
# Group 3 — from_env() integration tests (monkeypatch env + lazy-import patches)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_env_no_keys_uses_skipped_stub(monkeypatch, tmp_path):
    """Neither TAVILY_API_KEY nor BRAVE_SEARCH_API_KEY set → web_search is _skipped_web_search."""
    from lib.research.config import _skipped_web_search, from_env

    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.web_search is _skipped_web_search
    assert cfg.web_search_fallback is None
    assert cfg.web_extract is None


@pytest.mark.unit
def test_from_env_tavily_only_uses_tavily_no_fallback(monkeypatch, tmp_path):
    """TAVILY_API_KEY set, BRAVE_SEARCH_API_KEY unset → cfg.web_search is bare Tavily partial."""
    from lib.research.config import from_env

    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly_test_key")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    # web_search is a functools.partial of tavily_search bound to api_key
    assert isinstance(cfg.web_search, functools.partial)
    assert cfg.web_search.func is tavily_search
    assert cfg.web_search.keywords == {"api_key": "tvly_test_key"}
    assert cfg.web_search_fallback is None  # Brave key unset
    assert cfg.web_extract is not None      # Tavily extract bound
    assert isinstance(cfg.web_extract, functools.partial)
    assert cfg.web_extract.func is tavily_extract


@pytest.mark.unit
def test_from_env_both_keys_wraps_with_cascade(monkeypatch, tmp_path):
    """Both keys set → cfg.web_search is the cascade wrapper (NOT a bare partial)."""
    from lib.research.config import from_env

    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly_test_key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave_test_key")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    # web_search is the cascade wrapper, NOT a bare functools.partial of tavily_search
    is_bare_tavily_partial = (
        isinstance(cfg.web_search, functools.partial)
        and cfg.web_search.func is tavily_search
    )
    assert not is_bare_tavily_partial, (
        "When both keys are set, cfg.web_search should be the cascade wrapper, "
        "not a bare Tavily partial"
    )
    # web_search_fallback is the bare Brave partial (observability slot)
    assert cfg.web_search_fallback is not None
    assert isinstance(cfg.web_search_fallback, functools.partial)
    assert cfg.web_search_fallback.func is brave_search
    # web_extract is the bare Tavily extract partial
    assert cfg.web_extract is not None
    assert isinstance(cfg.web_extract, functools.partial)
    assert cfg.web_extract.func is tavily_extract
