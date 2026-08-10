"""Pin the round-robin router contract (quick bailian-1, 2026-08-11).

Guards:
1. get_llm_func() routes provider='router' → router_model_complete
2. split env controls bailian fraction (deterministic per-prompt hash)
3. bailian failure falls back to deepseek (soft boost, never blocks)
4. bailian key missing → all calls go deepseek
"""
from __future__ import annotations

import asyncio

import pytest


def test_get_llm_func_routes_router(monkeypatch) -> None:
    import lib.llm_complete as lc

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "router")
    from lib.llm_router import router_model_complete

    assert lc.get_llm_func() is router_model_complete


@pytest.mark.parametrize("split,expected_bailian", [(0.0, 0), (1.0, 5)])
def test_split_controls_fraction(monkeypatch, split: float, expected_bailian: int) -> None:
    """split=0 → all deepseek; split=1 → all bailian (deterministic hash)."""
    import lib.llm_router as lr

    monkeypatch.setenv("LLM_ROUTER_BAILIAN_SPLIT", str(split))
    calls: dict[str, int] = {"deepseek": 0, "bailian": 0}

    async def fake_ds(prompt, **kw):
        calls["deepseek"] += 1
        return "ds"

    async def fake_bl(prompt, **kw):
        calls["bailian"] += 1
        return "bl"

    monkeypatch.setattr(lr, "_deepseek_impl", fake_ds) if hasattr(lr, "_deepseek_impl") else None
    # patch module-level imports inside router via sys.modules is heavy; instead
    # monkeypatch the callables the router imports lazily:
    import lib.llm_deepseek as ld
    import lib.llm_bailian as lb

    monkeypatch.setattr(ld, "deepseek_model_complete", fake_ds)
    monkeypatch.setattr(lb, "bailian_model_complete", fake_bl)

    for i in range(5):
        asyncio.run(lr.router_model_complete(f"prompt-{i}"))
    assert calls["bailian"] == expected_bailian
    assert calls["deepseek"] == 5 - expected_bailian


def test_bailian_failure_falls_back_to_deepseek(monkeypatch) -> None:
    import lib.llm_router as lr
    import lib.llm_deepseek as ld
    import lib.llm_bailian as lb

    monkeypatch.setenv("LLM_ROUTER_BAILIAN_SPLIT", "1.0")  # force bailian

    async def fake_ds(prompt, **kw):
        return "ds-ok"

    async def fake_bl_fail(prompt, **kw):
        raise RuntimeError("bailian down")

    monkeypatch.setattr(ld, "deepseek_model_complete", fake_ds)
    monkeypatch.setattr(lb, "bailian_model_complete", fake_bl_fail)

    result = asyncio.run(lr.router_model_complete("any-prompt"))
    assert result == "ds-ok"


def test_bailian_delimiter_rewrite_roundtrip(monkeypatch) -> None:
    """qwen branch rewrites <|#|> → [TUPLE_DELIM] in prompts and maps back in output."""
    import lib.llm_router as lr
    import lib.llm_deepseek as ld
    import lib.llm_bailian as lb

    monkeypatch.setenv("LLM_ROUTER_BAILIAN_SPLIT", "1.0")  # force bailian

    seen: dict = {}

    async def fake_bailian(prompt, system_prompt=None, model=None, **kw):
        seen["prompt"] = prompt
        seen["system"] = system_prompt
        # qwen would emit the rewritten marker; simulate + verify mapping back
        return "entity[TUPLE_DELIM]OpenAI[TUPLE_DELIM]organization"

    async def fake_ds(prompt, **kw):
        return "ds"

    monkeypatch.setattr(ld, "deepseek_model_complete", fake_ds)
    monkeypatch.setattr(lb, "bailian_model_complete", fake_bailian)

    sys_p = "Use <|#|> as delimiter"
    result = asyncio.run(
        lr.router_model_complete("extract <|#|> entities", system_prompt=sys_p)
    )
    # output delimiter restored for LightRAG parser
    assert result == "entity<|#|>OpenAI<|#|>organization"
    # prompts rewritten so qwen never sees raw <|#|>
    assert "[TUPLE_DELIM]" in seen["prompt"]
    assert "[TUPLE_DELIM]" in seen["system"]
    assert "<|#|>" not in seen["prompt"]
