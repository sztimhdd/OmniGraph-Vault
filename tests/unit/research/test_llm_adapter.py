"""ar-4-02 Option A — JSON-mode LLM-decision adapter tests.

Mock-based tests for ``lib.research.llm_adapter.make_json_decision_adapter``.
The adapter wraps a string-returning async LLM provider into a
(prompt, tools) -> _DecisionPayload contract that the Reasoner / Verifier
loops consume. Failure modes (malformed JSON, missing fields, no tool_calls
when not-final, etc.) MUST degrade gracefully with is_final=True so loops
terminate instead of raising (Axis 3 best-effort).
"""
from __future__ import annotations

import pytest

from lib.research.llm_adapter import (
    _DecisionPayload,
    _ToolCallPayload,
    make_json_decision_adapter,
    _build_structured_prompt,
    _strip_fences,
    _parse_decision,
)


# --- _parse_decision (pure unit tests, no async) ---


def test_parse_decision_final_with_content():
    raw = '{"is_final": true, "content": "the answer"}'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == "the answer"
    assert d.tool_calls == ()


def test_parse_decision_tool_call_with_args():
    raw = '{"is_final": false, "tool_calls": [{"name": "kg_search", "args": {"query": "x"}}]}'
    d = _parse_decision(raw)
    assert d.is_final is False
    assert d.content is None
    assert len(d.tool_calls) == 1
    tc = d.tool_calls[0]
    assert isinstance(tc, _ToolCallPayload)
    assert tc.name == "kg_search"
    assert tc.args == {"query": "x"}


def test_parse_decision_multiple_tool_calls():
    raw = (
        '{"is_final": false, "tool_calls": ['
        '{"name": "kg_search", "args": {"q": "a"}}, '
        '{"name": "vision_analyze", "args": {"image_path": "/p", "question": "what"}}'
        ']}'
    )
    d = _parse_decision(raw)
    assert d.is_final is False
    assert len(d.tool_calls) == 2
    assert d.tool_calls[0].name == "kg_search"
    assert d.tool_calls[1].name == "vision_analyze"
    assert d.tool_calls[1].args["question"] == "what"


def test_parse_decision_malformed_json_degrades_gracefully():
    raw = "this is not json at all"
    d = _parse_decision(raw)
    # graceful degrade: mark final + use raw text as content so loop terminates
    assert d.is_final is True
    assert d.content == raw
    assert d.tool_calls == ()


def test_parse_decision_strips_markdown_fences():
    raw = '```json\n{"is_final": true, "content": "fenced"}\n```'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == "fenced"


def test_parse_decision_strips_bare_fences():
    raw = '```\n{"is_final": true, "content": "bare-fence"}\n```'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == "bare-fence"


def test_parse_decision_missing_is_final_defaults_true():
    raw = '{"content": "no flag"}'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == "no flag"


def test_parse_decision_not_final_with_no_tool_calls_treated_as_final():
    """If model claims not-final but emits no tool calls, treat raw text as
    a final answer (avoids infinite loop with nothing to dispatch)."""
    raw = '{"is_final": false, "content": "i meant to be final"}'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == "i meant to be final"


def test_parse_decision_tool_call_missing_args_defaults_empty():
    raw = '{"is_final": false, "tool_calls": [{"name": "kg_search"}]}'
    d = _parse_decision(raw)
    assert d.is_final is False
    assert len(d.tool_calls) == 1
    assert d.tool_calls[0].args == {}


def test_parse_decision_tool_call_missing_name_filtered():
    raw = (
        '{"is_final": false, "tool_calls": ['
        '{"args": {"x": 1}}, '  # no name → filtered
        '{"name": "kg_search", "args": {"q": "y"}}'
        ']}'
    )
    d = _parse_decision(raw)
    # 1 valid tool call (name-less filtered)
    assert len(d.tool_calls) == 1
    assert d.tool_calls[0].name == "kg_search"


def test_parse_decision_empty_string_returns_empty_final():
    d = _parse_decision("")
    assert d.is_final is True
    assert d.content == ""
    assert d.tool_calls == ()


def test_parse_decision_non_dict_json_degrades():
    """A JSON list or scalar is not a valid decision shape."""
    raw = '["not", "a", "decision"]'
    d = _parse_decision(raw)
    assert d.is_final is True
    assert d.content == raw


def test_parse_decision_non_list_tool_calls_ignored():
    raw = '{"is_final": false, "tool_calls": "not-a-list", "content": "fallback"}'
    d = _parse_decision(raw)
    # tool_calls is invalid → empty list → "not_final + no tool_calls" rule fires
    assert d.is_final is True
    assert d.content == "fallback"


# --- _build_structured_prompt ---


def test_build_structured_prompt_includes_tool_names():
    prompt = "do a thing"
    tools = [{"name": "kg_search", "fn": object()}, {"name": "vision_analyze", "fn": object()}]
    structured = _build_structured_prompt(prompt, tools)
    assert "do a thing" in structured
    assert "kg_search" in structured
    assert "vision_analyze" in structured
    assert "is_final" in structured  # JSON schema mentioned
    assert "tool_calls" in structured


def test_build_structured_prompt_no_tools():
    structured = _build_structured_prompt("question", None)
    assert "question" in structured
    assert "No tools are available" in structured


def test_build_structured_prompt_filters_invalid_tool_entries():
    tools = [{"name": "kg_search"}, {"fn": object()}, {"name": ""}, {"name": "valid"}]
    structured = _build_structured_prompt("p", tools)
    assert "kg_search" in structured
    assert "valid" in structured


# --- make_json_decision_adapter (async, with mock provider) ---


@pytest.mark.asyncio
async def test_adapter_calls_underlying_with_structured_prompt():
    captured: dict = {}

    async def mock_underlying(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return '{"is_final": true, "content": "ok"}'

    adapter = make_json_decision_adapter(mock_underlying)
    decision = await adapter("user-prompt", tools=[{"name": "t1"}])

    assert decision.is_final is True
    assert decision.content == "ok"
    assert "user-prompt" in captured["prompt"]
    assert "t1" in captured["prompt"]
    assert "is_final" in captured["prompt"]


@pytest.mark.asyncio
async def test_adapter_forwards_kwargs():
    seen_kwargs: dict = {}

    async def mock_underlying(prompt, **kwargs):
        seen_kwargs.update(kwargs)
        return '{"is_final": true, "content": "ok"}'

    adapter = make_json_decision_adapter(mock_underlying)
    await adapter("p", tools=None, system_prompt="sys", history_messages=[], model="x")

    assert seen_kwargs.get("system_prompt") == "sys"
    assert seen_kwargs.get("history_messages") == []
    assert seen_kwargs.get("model") == "x"


@pytest.mark.asyncio
async def test_adapter_returns_decision_with_tool_calls():
    async def mock_underlying(prompt, **kwargs):
        return '{"is_final": false, "tool_calls": [{"name": "kg_search", "args": {"q": "z"}}]}'

    adapter = make_json_decision_adapter(mock_underlying)
    decision = await adapter("p", tools=[{"name": "kg_search"}])

    assert decision.is_final is False
    assert len(decision.tool_calls) == 1
    assert decision.tool_calls[0].name == "kg_search"
    assert decision.tool_calls[0].args == {"q": "z"}


@pytest.mark.asyncio
async def test_adapter_preserves_underlying_module_for_autodetect():
    """Vertex Grounding auto-detect inspects llm_complete.__module__. The
    adapter must forward it from the wrapped provider so wrapping doesn't
    break detection."""
    async def fake_vertex_provider(prompt, **kwargs):
        return '{"is_final": true, "content": "ok"}'

    fake_vertex_provider.__module__ = "lib.vertex_gemini_complete"

    adapter = make_json_decision_adapter(fake_vertex_provider)
    assert getattr(adapter, "__module__", "") == "lib.vertex_gemini_complete"


@pytest.mark.asyncio
async def test_adapter_degrades_on_provider_returning_garbage():
    async def mock_underlying(prompt, **kwargs):
        return "i forgot to output JSON"

    adapter = make_json_decision_adapter(mock_underlying)
    decision = await adapter("p", tools=[])

    assert decision.is_final is True
    assert decision.content == "i forgot to output JSON"


# --- _strip_fences ---


def test_strip_fences_no_fence_returns_stripped():
    assert _strip_fences("  hello  ") == "hello"


def test_strip_fences_json_fence():
    assert _strip_fences("```json\n{}\n```") == "{}"


def test_strip_fences_bare_fence():
    assert _strip_fences("```\nbody\n```") == "body"
