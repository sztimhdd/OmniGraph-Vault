"""ar-4-02 JSON-mode LLM-decision adapter (Option A — milestone-blocking remediation).

Background — context:

  The Reasoner (ar-2-01) and Verifier (ar-3-02) agent loops dispatch
  ``decision = await cfg.llm_complete(prompt=..., tools=[...])`` and access
  ``decision.is_final``, ``decision.content``, ``decision.tool_calls``. The
  ar-2 unit tests installed mock callables that returned the module-private
  ``_LLMDecision`` dataclass directly; the docstring of
  ``tests/unit/research/test_reasoner_agent_loop.py`` calls this out as the
  "ar-2 contract" with "real provider integration is an ar-3+ refinement."
  ar-3 inherited the mock-only contract for the Verifier. ar-4-02 milestone
  smoke (TEST-05) was the first time the loops invoked a real LLM through
  ``cfg.llm_complete`` (which on Hermes is bound to the LightRAG-compatible
  ``deepseek_model_complete(prompt) -> str``), and crashed at iteration 1
  with ``'str' object has no attribute 'is_final'``.

This module ships the missing piece. It wraps any LightRAG-compatible
``(prompt: str) -> str`` async provider into a tool-calling adapter that
returns objects matching the ``_LLMDecision`` duck-type contract the loops
already consume:

  - ``.is_final: bool``
  - ``.content: str | None``
  - ``.tool_calls: tuple[_ToolCall-like, ...]`` where each tool call has
    ``.name: str`` and ``.args: dict``

The wrapper builds a structured prompt that requests one strict JSON object,
calls the underlying provider, parses the JSON, and constructs a
``_DecisionPayload``. Parse failures degrade gracefully: the adapter returns
``is_final=True`` with ``content=<raw text>`` so the loop terminates with
whatever the model said (the Synthesizer can still consume it).

Design choices (locked):

  - Stdlib only — no new top-level deps.
  - Shared ``_DecisionPayload`` / ``_ToolCallPayload`` dataclasses defined
    here; the loops duck-type accept them without isinstance() checks. The
    module-private ``_LLMDecision`` types in ``stages/reasoner.py`` and
    ``stages/verifier.py`` are NOT modified.
  - JSON-mode via prompt-only instructions (no provider-side
    ``response_format`` parameter required). DeepSeek chat models follow
    JSON-output instructions reliably enough for the smoke and audit gates.
    Native function-calling (Option B in the user's analysis) is a future
    upgrade path — this adapter does NOT preclude it.
  - Markdown code-fence stripping: many LLMs wrap JSON in ```` ```json ... ```` ````
    blocks; the parser strips the most common forms before json.loads.
  - kwargs passthrough: any ``system_prompt`` / ``history_messages`` etc.
    callers pass through to the adapter are forwarded to the underlying
    provider.

Wired into ``ResearchConfig.from_env()`` so ``cfg.llm_complete`` becomes the
adapter automatically. Direct callers constructing a ``ResearchConfig`` by
hand are responsible for wrapping their own provider if they want the
agent-loop interface (mock callers in tests still install ``_LLMDecision``-
returning mocks directly — those tests are unchanged).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


# Strip ```json ... ``` and ``` ... ``` fences; keep the inner payload.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


@dataclass(frozen=True)
class _ToolCallPayload:
    """Duck-type-compatible with stages/{reasoner,verifier}.py's _ToolCall.

    Loops access ``.name`` and ``.args`` only.
    """
    name: str
    args: dict


@dataclass(frozen=True)
class _DecisionPayload:
    """Duck-type-compatible with stages/{reasoner,verifier}.py's _LLMDecision.

    Reasoner accesses: ``.is_final``, ``.content``, ``.tool_calls``.
    Verifier accesses: those plus ``.confidence`` (float 0-100) and
    ``.discrepancies`` (tuple of str). Both extras default to safe values
    so the Reasoner path is unaffected — its prompt never mentions them
    and they stay at their defaults; the Reasoner loop never reads them.
    """
    is_final: bool
    content: str | None = None
    tool_calls: tuple[_ToolCallPayload, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    discrepancies: tuple[str, ...] = field(default_factory=tuple)


# Type alias for clarity at call sites.
LLMProvider = Callable[..., Awaitable[str]]
LLMDecisionAdapter = Callable[..., Awaitable[_DecisionPayload]]


def _build_structured_prompt(prompt: str, tools: list[dict] | None) -> str:
    """Append JSON-output instructions to the loop's per-turn prompt.

    The loops (reasoner.py / verifier.py) already include task-specific
    instructions in ``prompt``. We append the JSON schema + tool list so the
    model knows the strict output format expected.
    """
    tool_names: list[str] = []
    if tools:
        for t in tools:
            name = t.get("name") if isinstance(t, dict) else None
            if isinstance(name, str) and name:
                tool_names.append(name)

    if tool_names:
        tool_list = ", ".join(tool_names)
        tool_clause = (
            f"You have access to these tools: {tool_list}.\n"
            "If you need information from a tool, set is_final=false and emit one or more tool_calls.\n"
            "If you have enough information, set is_final=true and provide content."
        )
    else:
        tool_clause = (
            "No tools are available this turn. Set is_final=true and provide content."
        )

    return (
        f"{prompt}\n\n"
        f"---\nINSTRUCTIONS:\n{tool_clause}\n"
        "Respond with ONE valid JSON object ONLY — no prose before or after, "
        "no markdown code fences. Schema:\n"
        '{"is_final": <bool>, "content": <string|null>, '
        '"tool_calls": [{"name": <string>, "args": <object>}, ...], '
        '"confidence": <number 0-100, optional>, '
        '"discrepancies": [<string>, ...] (optional)}\n'
        "When is_final=true, content is REQUIRED (the final answer). "
        "When is_final=false, tool_calls is REQUIRED (one or more calls). "
        "If the task requests a fact-check / confidence score, include "
        "confidence (0-100) and discrepancies on the final-answer object."
    )


def _strip_fences(text: str) -> str:
    """Strip the most common markdown code-fence wrappers around a JSON body."""
    m = _FENCE_RE.match(text)
    if m is not None:
        return m.group(1).strip()
    return text.strip()


def _parse_decision(raw: str) -> _DecisionPayload:
    """Parse provider output into a _DecisionPayload. Degrade gracefully on
    any failure: return is_final=True with content=raw so the loop finalizes
    instead of raising (Axis 3 best-effort).
    """
    if not isinstance(raw, str) or not raw.strip():
        return _DecisionPayload(is_final=True, content=raw if isinstance(raw, str) else "")

    body = _strip_fences(raw)

    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return _DecisionPayload(is_final=True, content=raw)

    if not isinstance(obj, dict):
        return _DecisionPayload(is_final=True, content=raw)

    is_final_raw = obj.get("is_final")
    is_final = bool(is_final_raw) if is_final_raw is not None else True

    content_raw = obj.get("content")
    content: str | None = content_raw if isinstance(content_raw, str) else None

    tool_calls_raw = obj.get("tool_calls") or []
    if not isinstance(tool_calls_raw, list):
        tool_calls_raw = []

    tool_calls: list[_ToolCallPayload] = []
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name")
        if not isinstance(name, str) or not name:
            continue
        args = tc.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        tool_calls.append(_ToolCallPayload(name=name, args=args))

    # Verifier-only fields: confidence (float 0-100) and discrepancies (list[str]).
    # Default 0.0 / () when absent so the Reasoner path (which never reads them)
    # is unaffected.
    confidence_raw = obj.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(100.0, confidence))

    discrepancies_raw = obj.get("discrepancies") or []
    if not isinstance(discrepancies_raw, list):
        discrepancies_raw = []
    discrepancies = tuple(d for d in discrepancies_raw if isinstance(d, str))

    # If model claimed not-final but emitted no tool calls, treat raw text as
    # a final answer to avoid an infinite loop where the model has nothing to
    # dispatch but nothing to finalize either.
    if not is_final and not tool_calls:
        return _DecisionPayload(
            is_final=True,
            content=content if content else raw,
            confidence=confidence,
            discrepancies=discrepancies,
        )

    return _DecisionPayload(
        is_final=is_final,
        content=content,
        tool_calls=tuple(tool_calls),
        confidence=confidence,
        discrepancies=discrepancies,
    )


def make_json_decision_adapter(underlying: LLMProvider) -> LLMDecisionAdapter:
    """Wrap a string-returning LLM provider into the agent-loop adapter contract.

    The returned async callable matches the signature the Reasoner / Verifier
    loops expect:

        async def adapter(prompt: str, tools: list[dict] | None = None,
                          **kwargs) -> _DecisionPayload

    ``kwargs`` is forwarded to ``underlying`` so callers can still pass
    ``system_prompt``, ``history_messages``, ``model``, etc., as supported by
    the LightRAG-compatible signature.
    """
    async def adapter(prompt: str, tools: list[dict] | None = None,
                      **kwargs: Any) -> _DecisionPayload:
        structured = _build_structured_prompt(prompt, tools)
        raw = await underlying(structured, **kwargs)
        return _parse_decision(raw)

    # Carry over the underlying provider's __module__ so the Vertex Grounding
    # auto-detect logic in from_env() (which inspects llm_complete.__module__)
    # still sees the underlying provider's module rather than this adapter's.
    try:
        adapter.__module__ = getattr(underlying, "__module__", adapter.__module__)
    except (AttributeError, TypeError):
        pass

    return adapter


__all__ = [
    "_DecisionPayload",
    "_ToolCallPayload",
    "make_json_decision_adapter",
]
