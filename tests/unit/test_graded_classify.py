"""Unit tests for graded classification probe (_graded_probe).

Mock-only — no real DeepSeek API calls.
Tests 4 routing cases:
  1. confidence=0.95, unrelated=True  → probe returns dict (caller decides skip)
  2. confidence=0.85, unrelated=True  → probe returns dict (caller decides NOT skip)
  3. confidence=0.95, unrelated=False → probe returns dict (caller decides NOT skip)
  4. LLM raises / HTTP errors           → probe returns None (fail-open)
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


async def _graded_probe(title, account, digest, filter_keywords, api_key, timeout=30.0):
    """Re-import from batch_ingest_from_spider to ensure we test the real function."""
    from batch_ingest_from_spider import _graded_probe
    return await _graded_probe(title, account, digest, filter_keywords, api_key, timeout)


def _make_response(content: dict):
    """Build a mock aiohttp response with JSON content."""
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps(content)}}]
    })
    return resp


class MockClientSession:
    """Mock aiohttp.ClientSession that returns a controlled response."""

    def __init__(self, response=None, status=200, exc=None):
        self._response = response
        self._status = status
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        resp = AsyncMock()
        if self._response is not None:
            resp.status = self._status
            resp.json = AsyncMock(return_value=self._response)
        else:
            resp.status = self._status
            resp.json = AsyncMock(side_effect=ValueError("bad json"))
        self._resp = resp

        class _Ctx:
            async def __aenter__(self2):
                return resp

            async def __aexit__(self2, *args):
                pass

        return _Ctx()


@pytest.mark.asyncio
async def test_graded_probe_confident_unrelated():
    """Case 1: confidence=0.95, unrelated=True → returns valid dict."""
    mock_response = {
        "choices": [{"message": {"content": json.dumps({
            "unrelated": True,
            "confidence": 0.95,
            "reason": "CVPR paper acceptance, not Agent/Harness"
        })}}]
    }

    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value = MockClientSession(
            response=mock_response, status=200)

        result = await _graded_probe(
            title="CVPR 2026 动态视觉智能观察",
            account="AI科技评论",
            digest="CVPR论文接收结果整理",
            filter_keywords=("openclaw", "hermes", "agent", "harness"),
            api_key="test-key",
        )

    assert result is not None
    assert result["unrelated"] is True
    assert result["confidence"] == 0.95
    assert "CVPR" in result["reason"]


@pytest.mark.asyncio
async def test_graded_probe_low_confidence_unrelated():
    """Case 2: confidence=0.85, unrelated=True → probe returns dict (caller
    checks threshold >= 0.9 — this is below, so caller skips the graded skip)."""
    mock_response = {
        "choices": [{"message": {"content": json.dumps({
            "unrelated": True,
            "confidence": 0.85,
            "reason": "might be tangentially related"
        })}}]
    }

    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value = MockClientSession(
            response=mock_response, status=200)

        result = await _graded_probe(
            title="小米白送了我 16 亿 tokens",
            account="程序员鱼皮",
            digest="手把手教你领取 Claude Code 实战测评",
            filter_keywords=("openclaw", "hermes", "agent", "harness"),
            api_key="test-key",
        )

    assert result is not None
    assert result["unrelated"] is True
    assert result["confidence"] == 0.85  # below 0.9 threshold → caller won't skip


@pytest.mark.asyncio
async def test_graded_probe_not_unrelated():
    """Case 3: confidence=0.95, unrelated=False → probe returns dict."""
    mock_response = {
        "choices": [{"message": {"content": json.dumps({
            "unrelated": False,
            "confidence": 0.95,
            "reason": "Agent architecture article"
        })}}]
    }

    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value = MockClientSession(
            response=mock_response, status=200)

        result = await _graded_probe(
            title="OpenClaw vs Hermes：拆解 Hermes Agent 五层架构",
            account="叶小钗",
            digest="一条消息在 Hermes Agent 里经历了什么？万字拆解五层架构",
            filter_keywords=("openclaw", "hermes", "agent", "harness"),
            api_key="test-key",
        )

    assert result is not None
    assert result["unrelated"] is False
    assert "Agent" in result["reason"]


@pytest.mark.asyncio
async def test_graded_probe_http_error_fail_open():
    """Case 4a: HTTP 500 → probe returns None (fail-open)."""
    mock_response = {"error": "internal server error"}

    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value = MockClientSession(
            response=mock_response, status=500)

        result = await _graded_probe(
            title="任何文章",
            account="任何账号",
            digest="任何摘要内容",
            filter_keywords=("agent",),
            api_key="test-key",
        )

    assert result is None  # fail-open


@pytest.mark.asyncio
async def test_graded_probe_network_error_fail_open():
    """Case 4b: network exception → probe returns None (fail-open)."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value = MockClientSession(
            exc=ConnectionError("connection refused"))

        result = await _graded_probe(
            title="任何文章",
            account="任何账号",
            digest="任何摘要内容",
            filter_keywords=("agent",),
            api_key="test-key",
        )

    assert result is None  # fail-open


@pytest.mark.asyncio
async def test_graded_probe_empty_digest_fail_open():
    """Case 4c: empty/short digest → probe returns None without API call."""
    result = await _graded_probe(
        title="某文章",
        account="某账号",
        digest="",  # empty
        filter_keywords=("agent",),
        api_key="test-key",
    )
    assert result is None

    result2 = await _graded_probe(
        title="某文章", account="某账号",
        digest="abc",  # too short (< 10 chars)
        filter_keywords=("agent",),
        api_key="test-key",
    )
    assert result2 is None
