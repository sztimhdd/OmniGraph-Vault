from __future__ import annotations

import sys
import types

from lib import hermes_text_runner as runner


def _native(agent):
    choice = types.SimpleNamespace(provider="openai-codex", model="gpt-6-astra", base_url=None, api_key=None)
    oneshot = types.SimpleNamespace(_resolve_model_and_provider=lambda *_: choice)
    package = types.ModuleType("hermes_cli")
    package.oneshot = oneshot
    sys.modules["hermes_cli"] = package
    sys.modules["hermes_cli.oneshot"] = oneshot
    sys.modules["hermes_cli.config"] = types.SimpleNamespace(load_config=lambda: object())
    sys.modules["hermes_cli.runtime_provider"] = types.SimpleNamespace(resolve_runtime_provider=lambda **_: {"provider": "openai-codex", "requested_provider": "openai-codex"})
    sys.modules["run_agent"] = types.SimpleNamespace(AIAgent=lambda **kwargs: agent(kwargs))


def test_native_runner_is_tool_free_and_fallback_free_before_one_turn(monkeypatch):
    calls = []
    constructed = []
    class Agent:
        tools = []
        valid_tool_names = set()
        _fallback_chain = []
        model = "gpt-6-astra"
        provider = "openai-codex"
        platform = "subagent"
        _session_db = None
        session_id = "generated-session"
        def run_conversation(self, prompt, conversation_history=None):
            calls.append((prompt, conversation_history))
            return {"final_response": "中文输出", "provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "cache_read_tokens": 3}
    _native(lambda kwargs: (constructed.append(kwargs), Agent())[1])
    result = runner.run_native("bounded prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)
    assert result["ok"] is True
    assert result["usage"] == {"provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "cache_read_tokens": 3}
    assert result["initialization"] == {"fallback_chain_count": 0, "tools_count": 0, "tool_names": [], "model": "gpt-6-astra", "provider": "openai-codex", "platform": "subagent", "session_db_none": True, "session_id": "generated-session"}
    assert calls == [("bounded prompt", None)]
    assert constructed[0]["fallback_model"] is None
    assert constructed[0]["enabled_toolsets"] == []
    assert constructed[0]["max_iterations"] == 1
    assert constructed[0]["session_db"] is None


def test_native_runner_refuses_tools_without_running(monkeypatch):
    called = False
    class Agent:
        tools = [object()]
        valid_tool_names = {"kanban"}
        _fallback_chain = []
        model = "gpt-6-astra"
        provider = "openai-codex"
        platform = "subagent"
        _session_db = None
        session_id = "generated-session"
        def run_conversation(self, *_args, **_kwargs):
            nonlocal called
            called = True
    _native(lambda kwargs: Agent())
    result = runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)
    assert result["failure"] == {"code": "tool_gate", "tools_count": 1, "tool_names": ["kanban"]}
    assert called is False


def test_check_only_never_runs_and_missing_fallback_attribute_rejects():
    called = False
    class SafeAgent:
        tools = []
        valid_tool_names = set()
        _fallback_chain = []
        model = "gpt-6-astra"
        provider = "openai-codex"
        platform = "subagent"
        _session_db = None
        session_id = "generated-session"
        def run_conversation(self, *_args, **_kwargs):
            nonlocal called
            called = True
    _native(lambda kwargs: SafeAgent())
    assert runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180, check_only=True)["ok"] is True
    assert called is False

    class MissingFallback:
        tools = []
        valid_tool_names = set()
        model = "gpt-6-astra"
        provider = "openai-codex"
        platform = "subagent"
        _session_db = None
        session_id = "generated-session"
    _native(lambda kwargs: MissingFallback())
    assert runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)["failure"]["code"] == "fallback_gate"


def test_failed_native_result_precedes_route_classification():
    agent = types.SimpleNamespace(
        tools=[], valid_tool_names=set(), _fallback_chain=[], model="gpt-6-astra",
        provider="openai-codex", platform="subagent", _session_db=None, session_id="session",
    )
    _native(lambda kwargs: agent)
    for route in ({}, {"provider": "openai-codex", "model": "gpt-6-astra"}):
        native = {"failed": True, "completed": False, "api_calls": 1,
                  "final_response": "Non-streaming call timed out after 90 seconds.", **route}
        agent.run_conversation = lambda *args, **kwargs: native
        result = runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)
        assert result["ok"] is False
        assert result["failure"] == {"code": "native_turn_failed"}
        assert result["text"] == native["final_response"]
        assert result["usage"] == {k: v for k, v in native.items() if k != "final_response"}

    for route, expected in (({}, "route_unknown"), ({"provider": "other", "model": "gpt-6-astra"}, "route_mismatch")):
        agent.run_conversation = lambda *args, **kwargs: {"failed": False, "completed": True, "final_response": "text", **route}
        result = runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)
        assert result["ok"] is False
        assert result["failure"]["code"] == expected


def test_usage_rejection_keeps_final_text_and_safe_field_type():
    native = {"failed": False, "completed": True, "provider": "openai-codex",
              "model": "gpt-6-astra", "cache_read_tokens": "sensitive-value",
              "final_response": "原文输出", "credential": "secret"}
    agent = types.SimpleNamespace(
        tools=[], valid_tool_names=set(), _fallback_chain=[], model="gpt-6-astra",
        provider="openai-codex", platform="subagent", _session_db=None, session_id="session",
        run_conversation=lambda *args, **kwargs: native,
    )
    _native(lambda kwargs: agent)
    result = runner.run_native("prompt", provider="openai-codex", model="gpt-6-astra", timeout_seconds=180)
    assert result["ok"] is False
    assert result["text"] == "原文输出"
    assert result["failure"] == {"code": "usage_schema_invalid", "usage_field": "cache_read_tokens", "usage_type": "str"}
    assert result["usage"] is None
    assert "sensitive-value" not in str(result)
    assert "secret" not in str(result)
