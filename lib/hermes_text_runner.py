"""One bounded, tool-free Hermes native text turn for VitaX production."""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

try:
    from .llm_hermes import HermesCompletionError, _observable_usage
except ImportError:  # Native subprocess executes this file outside the package.
    from llm_hermes import HermesCompletionError, _observable_usage

_USAGE_FIELDS = {
    "estimated_cost_usd", "cost_status", "cost_source", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "total_tokens",
    "api_calls", "model", "provider", "session_id", "completed", "failed", "service_tier",
}


def _failure(code: str, **metadata: Any) -> dict[str, Any]:
    return {"ok": False, "failure": {"code": code, **metadata}, "usage": None, "text": ""}


def _exception_receipt(stage: str, exc: Exception) -> dict[str, Any]:
    frame = traceback.extract_tb(exc.__traceback__)[-1]
    return _failure("native_initialization_failed", stage=stage, exception_type=type(exc).__name__, traceback={"basename": Path(frame.filename).name, "function": frame.name, "line": frame.lineno})


def create_agent(*, provider: str, model: str, timeout_seconds: float):
    """Resolve and construct the packet's fail-closed native agent without a turn."""
    from hermes_cli import oneshot
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from run_agent import AIAgent
    cfg = load_config()
    choice = oneshot._resolve_model_and_provider(cfg, model, provider)
    runtime = resolve_runtime_provider(requested=choice.provider, target_model=choice.model or None, explicit_base_url=choice.base_url, explicit_api_key=choice.api_key)
    if choice.provider != provider or choice.model != model:
        raise RuntimeError("resolved_route_mismatch")
    return AIAgent(
        api_key=runtime.get("api_key"), base_url=runtime.get("base_url"), provider=runtime.get("provider"), requested_provider=runtime.get("requested_provider"), api_mode=runtime.get("api_mode"), model=choice.model, credential_pool=runtime.get("credential_pool"), fallback_model=None, enabled_toolsets=[], disabled_toolsets=[], quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True, session_db=None, session_id=None, platform="subagent", max_iterations=1, run_budget_seconds=timeout_seconds)


def run_native(prompt: str, *, provider: str, model: str, timeout_seconds: float, check_only: bool = False) -> dict[str, Any]:
    """Run exactly one native turn; credentials remain in the native runtime."""
    stage = "create_agent"
    try:
        agent = create_agent(provider=provider, model=model, timeout_seconds=timeout_seconds)
    except Exception as exc:
        return _exception_receipt(stage, exc)
    tool_names = sorted(str(name) for name in agent.valid_tool_names)
    if agent.tools or tool_names:
        return _failure("tool_gate", tools_count=len(agent.tools), tool_names=tool_names)
    fallback_chain = getattr(agent, "_fallback_chain", object())
    if fallback_chain != []:
        return _failure("fallback_gate", fallback_chain_type=type(fallback_chain).__name__)
    if (
        getattr(agent, "model", object()) != model
        or getattr(agent, "provider", object()) != provider
        or getattr(agent, "platform", object()) != "subagent"
        or getattr(agent, "_session_db", object()) is not None
    ):
        return _failure("session_gate")
    initialization = {
        "fallback_chain_count": 0, "tools_count": 0, "tool_names": [],
        "model": getattr(agent, "model"), "provider": getattr(agent, "provider"),
        "platform": getattr(agent, "platform"), "session_db_none": getattr(agent, "_session_db") is None,
        "session_id": getattr(agent, "session_id"),
    }
    if check_only:
        return {"ok": True, "failure": None, "usage": None, "text": "", "initialization": initialization}
    try:
        result = agent.run_conversation(prompt, conversation_history=None)
    except Exception:
        return {**_failure("native_turn_failed"), "initialization": initialization}
    if not isinstance(result, dict):
        return {**_failure("native_result_invalid"), "initialization": initialization}
    text = result.get("final_response")
    try:
        usage = _observable_usage(result)
    except HermesCompletionError as exc:
        return {**_failure("usage_schema_invalid", **(exc.native_failure_details or {})),
                "text": text if isinstance(text, str) else "", "initialization": initialization}
    if result.get("failed") is not False or result.get("completed") is False:
        return {"ok": False, "failure": {"code": "native_turn_failed"}, "usage": usage, "text": text if isinstance(text, str) else "", "initialization": initialization}
    if result.get("provider") is None or result.get("model") is None:
        return {"ok": False, "failure": {"code": "route_unknown"}, "usage": usage, "text": text if isinstance(text, str) else "", "initialization": initialization}
    if result.get("provider") != provider or result.get("model") != model:
        return {"ok": False, "failure": {"code": "route_mismatch"}, "usage": usage, "text": text if isinstance(text, str) else "", "initialization": initialization}
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "failure": {"code": "blank_output"}, "usage": usage, "text": text if isinstance(text, str) else "", "initialization": initialization}
    return {"ok": True, "failure": None, "usage": usage, "text": text, "initialization": initialization}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        result = _failure("prompt_unavailable")
    else:
        result = run_native(prompt, provider=args.provider, model=args.model, timeout_seconds=args.timeout_seconds, check_only=args.check_only)
    args.result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
