"""Round-robin LLM router — DeepSeek (primary, company-paid) + Bailian (boost).

DEPRECATED (2026-08-12): the Bailian entity-extraction split is disabled.
Zero-Ent attribution: of 38 empty-entity chunks, 33 were ALL bailian-extracted
(DeepSeek: 0). Root cause: qwen's [TUPLE_DELIM]→<|#|> output mapping fails on
the production ingest entity-extraction path (the marker rewrite is bypassed
or the output mapping is not applied there), silently dropping all entities.
Decision: entity extraction returns to pure DeepSeek
(OMNIGRAPH_LLM_PROVIDER=deepseek) — this router module is retained for
reference/rollback only and must not be selected. Bailian itself is KEPT for
other paths: vision (qwen3-vl-flash via lib/vision_cascade.py) and the
classify fallback branch are unaffected.

Rationale (2026-08-11, quick bailian-1):
- DeepSeek is company-reimbursed and unlimited; NOT replaced 1:1.
- Bailian qwen3.7-flash is user-funded (¥320) — used ONLY to raise the
  concurrent entity-extraction ceiling. DeepSeek max_async=4 caps per-article
  throughput at ~15min; routing ~40% of LightRAG extraction calls to Bailian
  doubles effective concurrency → single-article time ≈ 9-10min.
- Bailian output verified compatible with LightRAG's ``<|#|>`` delimiter
  extraction format when the entity_extraction prompt is used verbatim.

Routing policy:
- ``LLM_ROUTER_BAILIAN_SPLIT`` env (default 0.4): fraction of calls to Bailian.
- Round-robin counter seeded from hash(prompt) for stability across retries.
- Both providers must be configured; missing Bailian key falls back to 100%
  DeepSeek (router is a soft boost, never a hard dependency).

IMPORTANT: mirrors deepseek_model_complete's signature — async, single prompt,
returns plain string. Both backends satisfy the LightRAG llm_model_func
contract. The ``system_prompt`` kwarg is forwarded to Bailian; DeepSeek's
wrapper accepts it too.
"""
from __future__ import annotations

import asyncio
import hashlib
import os

from config import load_env

load_env()


async def router_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    **kwargs,
) -> str:
    """Route a completion to DeepSeek or Bailian based on prompt hash.

    Deterministic per-prompt (same prompt → same provider) so retries
    land on the same backend and the LLM cache stays coherent.
    """
    # DEPRECATED 2026-08-12 (zero-Ent fix): entity extraction is back on pure
    # DeepSeek (OMNIGRAPH_LLM_PROVIDER=deepseek). 33/38 empty-entity chunks
    # were bailian-extracted — qwen's [TUPLE_DELIM]→<|#|> output mapping fails
    # on the production ingest path and silently drops ALL entities. This
    # split must stay disabled (provider != "router"); code kept for reference.
    split = float(os.environ.get("LLM_ROUTER_BAILIAN_SPLIT", "0.4"))
    h = int(hashlib.md5(prompt.encode("utf-8")).hexdigest(), 16)
    use_bailian = (h % 1000) / 1000.0 < split

    from lib.llm_deepseek import deepseek_model_complete

    if use_bailian:
        try:
            from lib.llm_bailian import bailian_model_complete

            # Bailian (qwen) mangles the literal `<|#|>` tuple delimiter — its
            # tokenizer treats it as a special token and substitutes `|`
            # (verified 2026-08-11: qwen emitted `实体|类型 | MCP协议|technology`
            # with a real prompt). Fix: rewrite BOTH the system prompt and the
            # user prompt so qwen never sees the raw `<|#|>` token — replace it
            # with an explicit ASCII marker ``[TUPLE_DELIM]`` plus a format
            # example. DeepSeek branch is untouched (its tokenizer keeps
            # `<|#|>` intact).
            if "<|#|>" in (system_prompt or "") or "<|#|>" in prompt:
                _marker = "[TUPLE_DELIM]"
                if system_prompt:
                    system_prompt = system_prompt.replace("<|#|>", _marker)
                prompt = prompt.replace("<|#|>", _marker)
                example = (
                    "\n\n---Format Example (must follow EXACTLY; use [TUPLE_DELIM] as the field separator, NOT |)---\n"
                    f"entity{_marker}OpenAI{_marker}organization{_marker}An AI research company{_marker}doc_001\n"
                    f"relationship{_marker}OpenAI{_marker}GPT-4{_marker}developed{_marker}created,built{_marker}0.9{_marker}doc_001\n"
                    "---End of Example---\n"
                )
                prompt = prompt + example

            return await _bailian_complete_with_delimiter_fix(
                bailian_model_complete, prompt, system_prompt, model, **kwargs
            )
        except Exception:
            # Bailian failure → fall back to DeepSeek (never block the batch).
            return await deepseek_model_complete(prompt, system_prompt=system_prompt, model=model, **kwargs)

    return await deepseek_model_complete(prompt, system_prompt=system_prompt, model=model, **kwargs)


async def router_model_complete_sync_guard(prompt: str, **kwargs) -> str:
    """Non-async entrypoint for callers that run completion via asyncio.run."""
    return await router_model_complete(prompt, **kwargs)


async def _bailian_complete_with_delimiter_fix(
    bailian_model_complete,
    prompt: str,
    system_prompt: str | None,
    model: str | None,
    **kwargs,
) -> str:
    """Call Bailian then restore `<|#|>` delimiters in the output.

    qwen emits the rewritten `[TUPLE_DELIM]` marker verbatim; LightRAG's
    parser only accepts the native `<|#|>` token, so map it back. Also
    normalizes any stray pipe-separated lines qwen may still produce when
    the marker rewrite was bypassed (defensive).
    """
    result = await bailian_model_complete(
        prompt, system_prompt=system_prompt, model=model, **kwargs
    )
    result = result.replace("[TUPLE_DELIM]", "<|#|>")
    return result
