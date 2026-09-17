"""Experimental, opt-in Hermes text-completion callback.

This is deliberately not a production default.  Hermes ``-z`` accepts one
user string, so system/history data is JSON context rather than native roles.
The argv transport is OS-length-limited; this adapter caps rendered prompts at
32 KiB.  Production enablement additionally requires output-quality and
version-pinned ``bot_room`` toolset validation.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROVIDER = "openai-codex"
_MODEL = "gpt-6-astra"
_PROMPT_LIMIT = 32 * 1024
_DEFAULT_TIMEOUT = 180.0
_LOCK = asyncio.Lock()
_MULTIMODAL_KEYS = {"image", "images", "image_data", "audio", "video", "media", "attachments"}


class HermesCompletionError(RuntimeError):
    """A redacted Hermes completion failure."""

    def __init__(
        self,
        message: str,
        *,
        usage: dict[str, Any] | None = None,
        stdout: str | None = None,
        failure_code: str | None = None,
        native_failure_code: str | None = None,
        native_failure_details: dict[str, Any] | None = None,
        initialization: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.stdout = stdout
        self.failure_code = failure_code
        self.native_failure_code = native_failure_code
        self.native_failure_details = native_failure_details
        self.initialization = initialization


@dataclass(frozen=True)
class HermesCompletion:
    """Text plus the small, non-sensitive observable part of Hermes usage."""

    text: str
    usage: dict[str, Any]
    initialization: dict[str, Any] | None = None


_NATIVE_FAILURE_CODES = {"native_initialization_failed", "tool_gate", "fallback_gate", "session_gate", "native_turn_failed", "native_result_invalid", "usage_schema_invalid", "route_mismatch", "route_unknown", "blank_output", "prompt_unavailable"}


_USAGE_STRINGS = ("provider", "model", "session_id", "cost_status", "cost_source", "service_tier")
_USAGE_NUMBERS = {
        "api_calls", "input_tokens", "output_tokens", "total_tokens", "cached_tokens",
        "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "estimated_cost_usd",
        "duration_ms", "duration_seconds", "cost", "cost_usd",
    }
_USAGE_FIELDS = set(_USAGE_STRINGS) | _USAGE_NUMBERS | {"completed", "failed"}

def _native_receipt(result: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    failure = result.get("failure")
    code = failure.get("code") if isinstance(failure, dict) else None
    if code is not None and code not in _NATIVE_FAILURE_CODES:
        raise HermesCompletionError("Hermes completion failed (native receipt invalid)")
    details = None
    if code == "native_initialization_failed":
        trace = failure.get("traceback") if isinstance(failure, dict) else None
        if not (isinstance(failure.get("stage"), str) and isinstance(failure.get("exception_type"), str) and isinstance(trace, dict) and all(isinstance(trace.get(k), t) for k, t in (("basename", str), ("function", str), ("line", int)))):
            raise HermesCompletionError("Hermes completion failed (native receipt invalid)")
        details = {"stage": failure["stage"], "exception_type": failure["exception_type"], "traceback_basename": trace["basename"], "traceback_function": trace["function"], "traceback_line": trace["line"]}
    if code == "usage_schema_invalid":
        field, kind = failure.get("usage_field"), failure.get("usage_type")
        if isinstance(field, str) and field in _USAGE_FIELDS and kind in ("NoneType", "str", "bool", "int", "float", "list", "dict"):
            details = {"usage_field": field, "usage_type": kind}
    init = result.get("initialization")
    if init is None:
        return code, None, details
    if not isinstance(init, dict):
        raise HermesCompletionError("Hermes completion failed (native receipt invalid)")
    safe: dict[str, Any] = {}
    for name, kind in (("model", str), ("provider", str), ("platform", str), ("session_id", str), ("session_db_none", bool), ("fallback_chain_count", int), ("tools_count", int)):
        if name in init and isinstance(init[name], kind) and not (kind is int and isinstance(init[name], bool)):
            safe[name] = init[name]
        elif name in init:
            raise HermesCompletionError("Hermes completion failed (native receipt invalid)")
    if "tool_names" in init:
        if not isinstance(init["tool_names"], list) or not all(isinstance(x, str) for x in init["tool_names"]):
            raise HermesCompletionError("Hermes completion failed (native receipt invalid)")
        safe["tool_names"] = init["tool_names"]
    return code, safe, details


def _timeout_seconds() -> float:
    raw = os.environ.get("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise HermesCompletionError("Hermes completion failed (invalid timeout)") from None
    if not math.isfinite(value) or value <= 0:
        raise HermesCompletionError("Hermes completion failed (invalid timeout)")
    return value


def _has_multimodal(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in _MULTIMODAL_KEYS for key in value):
            return True
        return any(_has_multimodal(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_multimodal(item) for item in value)
    return False


def _validate_text_inputs(prompt: Any, system_prompt: Any, history_messages: Any) -> None:
    if not isinstance(prompt, str):
        raise HermesCompletionError("Hermes completion failed (text prompt required)")
    if system_prompt is not None and not isinstance(system_prompt, str):
        raise HermesCompletionError("Hermes completion failed (text system prompt required)")
    if history_messages is None:
        return
    if not isinstance(history_messages, list):
        raise HermesCompletionError("Hermes completion failed (text history list required)")
    for message in history_messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise HermesCompletionError("Hermes completion failed (text-only history required)")
        if message["role"] not in {"system", "user", "assistant"}:
            raise HermesCompletionError("Hermes completion failed (text-only history required)")
        if not isinstance(message["content"], str):
            raise HermesCompletionError("Hermes completion failed (text-only history required)")


def _render_prompt(prompt: str, system_prompt: Any, history_messages: Any) -> str:
    try:
        rendered = json.dumps(
            {
                "role_semantics": "system_prompt and history_messages are context, not native roles",
                "system_prompt": system_prompt,
                "history_messages": history_messages,
                "prompt": prompt,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        encoded = rendered.encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeEncodeError):
        raise HermesCompletionError("Hermes completion failed (prompt serialization rejected)") from None
    if len(encoded) > _PROMPT_LIMIT:
        raise HermesCompletionError("Hermes completion failed (prompt exceeds 32 KiB)")
    return rendered


async def _reap_process_group(
    process: asyncio.subprocess.Process, communication: asyncio.Task[tuple[bytes, bytes]]
) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(communication), timeout=5)
            return
        except asyncio.TimeoutError:
            continue
    await asyncio.wait_for(asyncio.shield(communication), timeout=5)


def _load_usage(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid")


def _observable_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Keep only the observed route/session and non-sensitive meter schema."""
    result: dict[str, Any] = {}
    for field in _USAGE_STRINGS:
        if field == "service_tier" and usage.get(field) is None:
            continue
        if field in usage:
            if not isinstance(usage[field], str):
                raise HermesCompletionError("Hermes completion failed (usage schema invalid)", native_failure_details={"usage_field": field, "usage_type": type(usage[field]).__name__})
            result[field] = usage[field]
    for field in ("completed", "failed"):
        if field in usage:
            if not isinstance(usage[field], bool):
                raise HermesCompletionError("Hermes completion failed (usage schema invalid)", native_failure_details={"usage_field": field, "usage_type": type(usage[field]).__name__})
            result[field] = usage[field]
    for field in _USAGE_NUMBERS:
        if field in usage:
            value = usage[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise HermesCompletionError("Hermes completion failed (usage schema invalid)", native_failure_details={"usage_field": field, "usage_type": type(usage[field]).__name__})
            result[field] = value
    return result


def _validated_completion_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Accept only a successful receipt from this adapter's fixed route."""
    observed = _observable_usage(usage)
    if usage.get("failed") is not False:
        raise HermesCompletionError(
            "Hermes completion failed (successful receipt required)", usage=observed
        )
    if usage.get("provider") != _PROVIDER or usage.get("model") != _MODEL:
        raise HermesCompletionError(
            "Hermes completion failed (route=mismatch)", usage=observed
        )
    return observed


async def hermes_model_complete_with_usage(
    prompt: str, system_prompt: Any = None, history_messages: Any = None, **kwargs: Any
) -> HermesCompletion:
    """Invoke Hermes and retain its allowlisted observable usage for production."""
    if kwargs.get("stream") is True:
        raise HermesCompletionError("Hermes completion failed (stream unsupported)")
    _validate_text_inputs(prompt, system_prompt, history_messages)
    if _has_multimodal(kwargs):
        raise HermesCompletionError("Hermes completion failed (multimodal unsupported)")
    rendered = _render_prompt(prompt, system_prompt, history_messages)
    timeout_seconds = _timeout_seconds()
    binary = os.environ.get("OMNIGRAPH_HERMES_PYTHON", "").strip()
    if not binary:
        raise HermesCompletionError("Hermes completion failed (native runtime not configured)")
    if not Path(binary).is_file():
        raise HermesCompletionError("Hermes completion failed (binary unavailable)")
    async with _LOCK:
        with tempfile.TemporaryDirectory(prefix="omnigraph-hermes-") as temp:
            temp_path = Path(temp)
            prompt_path = temp_path / "prompt.txt"
            result_path = temp_path / "result.json"
            prompt_path.write_text(rendered, encoding="utf-8")
            try:
                process = await asyncio.create_subprocess_exec(
                    binary, str(Path(__file__).with_name("hermes_text_runner.py")),
                    "--prompt-file", str(prompt_path), "--result-file", str(result_path),
                    "--provider", _PROVIDER, "--model", _MODEL, "--timeout-seconds", str(timeout_seconds),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError:
                raise HermesCompletionError("Hermes completion failed (binary execution unavailable)") from None
            communication = asyncio.create_task(process.communicate())
            try:
                stdout, _stderr = await asyncio.wait_for(
                    asyncio.shield(communication), timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                await _reap_process_group(process, communication)
                raise HermesCompletionError("Hermes completion failed (parent_timeout=True)") from exc
            except asyncio.CancelledError:
                await _reap_process_group(process, communication)
                raise
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                result = None
    usage = result.get("usage") if isinstance(result, dict) else None
    try:
        native_failure_code, initialization, native_failure_details = _native_receipt(result) if isinstance(result, dict) else (None, None, None)
    except HermesCompletionError:
        native_failure_code, initialization, native_failure_details = None, None, None
    usage_status = "ok" if isinstance(usage, dict) else "missing"
    text = result.get("text", "") if isinstance(result, dict) and isinstance(result.get("text"), str) else ""
    status = [f"exit={process.returncode}", "parent_timeout=False", f"usage={usage_status}"]
    if usage is not None:
        status.extend((f"failed={usage.get('failed') is True}",))
    if (
        process.returncode != 0
        or not isinstance(result, dict)
        or result.get("ok") is not True
        or result.get("failure") is not None
        or usage is None
    ):
        raise HermesCompletionError(
            "Hermes completion failed (" + ", ".join(status) + ")",
            usage=_observable_usage(usage) if usage is not None else None,
            stdout=text,
            failure_code="run_invalid",
            native_failure_code=native_failure_code,
            native_failure_details=native_failure_details,
            initialization=initialization,
        )
    try:
        observed_usage = _validated_completion_usage(usage)
    except HermesCompletionError as exc:
        if str(exc).endswith("route=mismatch)"):
            message = "Hermes completion failed (" + ", ".join(status) + ", route=mismatch)"
            failure_code = "route_mismatch"
        elif str(exc).endswith("successful receipt required)"):
            message = "Hermes completion failed (" + ", ".join(status) + ")"
            failure_code = "run_invalid"
        else:
            message = str(exc)
            failure_code = "usage_schema_invalid"
        raise HermesCompletionError(
            message, usage=exc.usage, stdout=text, failure_code=failure_code
        ) from None
    if not text.strip():
        raise HermesCompletionError(
            "Hermes completion failed (" + ", ".join(status) + ", stdout=blank)",
            usage=observed_usage,
            stdout=text,
            failure_code="stdout_blank",
        )
    return HermesCompletion(text=text, usage=observed_usage, initialization=initialization)


async def hermes_model_complete(
    prompt: str, system_prompt: Any = None, history_messages: Any = None, **kwargs: Any
) -> str:
    """Backward-compatible text-only Hermes callback."""
    return (await hermes_model_complete_with_usage(prompt, system_prompt, history_messages, **kwargs)).text


__all__ = ["HermesCompletion", "HermesCompletionError", "hermes_model_complete", "hermes_model_complete_with_usage"]
