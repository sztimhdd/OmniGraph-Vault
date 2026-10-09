"""Terminology lookup must yield to the ingestion deadline."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

@pytest.mark.asyncio
async def test_lookup_is_cancellable(monkeypatch):
    from lib.translate import _tavily_search
    async def slow(**kwargs):
        await asyncio.sleep(1)
    search = AsyncMock(side_effect=slow)
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic')
    monkeypatch.setitem(sys.modules, 'tavily', SimpleNamespace(AsyncTavilyClient=lambda **kwargs: SimpleNamespace(search=search)))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_tavily_search('synthetic'), timeout=0.01)
    search.assert_awaited_once()
