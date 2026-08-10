"""Pin the Bailian provider contract (quick bailian-1, 2026-08-11).

Guards:
1. lib.llm_complete.get_llm_func() routes provider='bailian' → bailian_model_complete
2. unknown provider raises ValueError listing valid names incl. bailian
3. bailian_model_complete builds messages [user] and calls AsyncOpenAI
4. bailian_embedding sorts by index to preserve input order
"""
from __future__ import annotations

import asyncio

import pytest


class _FakeChoices:
    def __init__(self, content: str):
        self.message = type("M", (), {"content": content})


class _FakeEmbedData:
    def __init__(self, index: int, dims: int):
        self.index = index
        self.embedding = [float(index + 1)] * dims


def test_get_llm_func_routes_bailian(monkeypatch) -> None:
    import lib.llm_complete as lc

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "bailian")
    fn = lc.get_llm_func()
    from lib.llm_bailian import bailian_model_complete

    assert fn is bailian_model_complete


def test_get_llm_func_unknown_provider(monkeypatch) -> None:
    import lib.llm_complete as lc

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "not-a-provider")
    with pytest.raises(ValueError, match="bailian"):
        lc.get_llm_func()


def test_bailian_complete_sends_user_message(monkeypatch) -> None:
    import lib.llm_bailian as lb

    captured: dict = {}

    class _FakeResp:
        choices = [_FakeChoices("hello from qwen")]

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setenv("BAILIAN_API_KEY", "test-key")
    monkeypatch.setattr(lb, "_get_client", lambda: _FakeClient())

    result = asyncio.run(lb.bailian_model_complete("hi"))
    assert result == "hello from qwen"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["model"] == "qwen3.7-flash"


def test_bailian_complete_requires_key(monkeypatch) -> None:
    import lib.llm_bailian as lb

    monkeypatch.delenv("BAILIAN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BAILIAN_API_KEY"):
        lb._require_api_key()


def test_bailian_embedding_sorts_by_index(monkeypatch) -> None:
    import lib.llm_bailian as lb

    class _FakeResp:
        # deliberately out of order
        data = [_FakeEmbedData(1, 4), _FakeEmbedData(0, 4), _FakeEmbedData(2, 4)]

    class _FakeEmbeddings:
        async def create(self, **kwargs):
            return _FakeResp()

    class _FakeClient:
        embeddings = _FakeEmbeddings()

    monkeypatch.setenv("BAILIAN_API_KEY", "test-key")
    monkeypatch.setattr(lb, "_get_client", lambda: _FakeClient())

    result = asyncio.run(lb.bailian_embedding(["a", "b", "c"]))
    assert result[0][0] == 1.0  # index 0 first
    assert result[1][0] == 2.0  # index 1 second
    assert result[2][0] == 3.0  # index 2 third
