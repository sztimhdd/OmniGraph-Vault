---
phase: ar-3-verifier-web-tools
plan: 03
type: execute
wave: 3
depends_on:
  - ar-3-02
files_modified:
  - lib/research/tools/web_search.py
  - lib/research/config.py
  - tests/unit/research/test_grounding_autodetect.py
  - tests/unit/research/test_caps_consolidated.py
autonomous: true
status: complete
last_updated: "2026-05-23"
requirements:
  - TOOL-03
  - CONFIG-03
  - TEST-04

must_haves:
  truths:
    - "vertex_gemini_grounding(query: str) -> str is an async callable in lib/research/tools/web_search.py — thin pass-through to a Vertex Gemini search-tool invocation; full prompt-engineering deferred to ar-4 (TOOL-03)"
    - "from_env() auto-detects Vertex Gemini provider via TWO equivalent signals (either suffices): OS env OMNIGRAPH_LLM_PROVIDER == 'vertex_gemini' OR getattr(llm_complete, '__module__', '') == 'lib.vertex_gemini_complete'"
    - "When auto-detected, cfg.google_search_grounding = vertex_gemini_grounding (non-None); when not, cfg.google_search_grounding = None unconditionally (CONFIG-03 Wave-3 half)"
    - "--no-grounding CLI flag is final-word: it sets overrides['google_search_grounding'] = None and dataclasses.replace overrides any auto-detected value (precedence: CLI > auto-detect > None default)"
    - "vertex_gemini_grounding(query) is a single-positional-arg async callable matching the type of cfg.google_search_grounding's slot (Callable | None) and the Verifier's grounding_tool wrapper signature"
    - "TEST-04 Reasoner-half asserts: mock cfg.llm_complete that always emits a tool_call (kg_search) and never finalizes → result.iter_count == cfg.max_iter_reasoner (default 5) AND result.status == 'ok'"
    - "TEST-04 Verifier-half cap test is consolidated into test_caps_consolidated.py — Wave 2's test_verifier_cap.py is removed (file is deleted, not left orphan) so the consolidated file is the single source of cap tests"
    - "Layer 2a cap=0 LLM-free CLI smoke (`python -m omnigraph.research --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding ...`) exits 0 with non-empty markdown ≥200 chars — proves CLI plumbing end-to-end without external services"
  artifacts:
    - path: "lib/research/tools/web_search.py"
      provides: "Adds vertex_gemini_grounding(query) async pass-through callable alongside Wave 1's Tavily/Brave callables"
      contains: "async def vertex_gemini_grounding(query: str) -> str (single positional arg, no api_key kwarg — reads its own env at call time)"
    - path: "lib/research/config.py"
      provides: "from_env() Vertex Gemini auto-detect logic — sets cfg.google_search_grounding non-None when Vertex provider detected"
      contains: "Two-signal auto-detect (env + bound module path), import of vertex_gemini_grounding, conditional binding"
    - path: "tests/unit/research/test_grounding_autodetect.py"
      provides: "TOOL-03 + CONFIG-03 Wave-3-half tests — auto-detect via env, auto-detect via module path, no-detect for non-Vertex, --no-grounding CLI override"
      contains: "test_autodetect_via_env_provider_vertex, test_autodetect_via_module_path_vertex, test_autodetect_deepseek_yields_no_grounding, test_no_grounding_cli_override_nullifies_autodetect, test_grounding_callable_is_zero_arg_factory_compatible"
    - path: "tests/unit/research/test_caps_consolidated.py"
      provides: "TEST-04 consolidated — Reasoner-half cap test + Verifier-half cap test (absorbs and replaces Wave 2's test_verifier_cap.py)"
      contains: "test_reasoner_cap_enforcement, test_verifier_cap_enforcement_consolidated"
  key_links:
    - from: "lib/research/config.py"
      to: "os.environ['OMNIGRAPH_LLM_PROVIDER']"
      via: "_provider_env = os.environ.get('OMNIGRAPH_LLM_PROVIDER', '').strip().lower()"
      pattern: "OMNIGRAPH_LLM_PROVIDER"
    - from: "lib/research/config.py"
      to: "llm_complete.__module__"
      via: "_llm_module = getattr(llm_complete, '__module__', '')"
      pattern: "__module__"
    - from: "lib/research/config.py"
      to: "lib/research/tools/web_search.py:vertex_gemini_grounding"
      via: "from .tools.web_search import vertex_gemini_grounding"
      pattern: "vertex_gemini_grounding"
    - from: "lib/research/__main__.py"
      to: "cfg.google_search_grounding (via dataclasses.replace overrides)"
      via: "overrides['google_search_grounding'] = None when ns.no_grounding (already plumbed in ar-2-03)"
      pattern: "google_search_grounding"
---

<objective>
Wave 3 of ar-3 closes the phase with three deliverables:

1. **TOOL-03** — Add `vertex_gemini_grounding(query: str) -> str` async callable in `lib/research/tools/web_search.py`. Thin pass-through to a Vertex Gemini search-tool invocation. Full prompt-engineering is deferred to ar-4 final-tuning — Wave 3 only ships the bind point.

2. **CONFIG-03 (Wave-3 half)** — Auto-detect Vertex Gemini provider in `from_env()` via two equivalent signals (`OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"` OR `llm_complete.__module__ == "lib.vertex_gemini_complete"`). When auto-detected: `cfg.google_search_grounding = vertex_gemini_grounding`. When not: `None`. The `--no-grounding` CLI flag (already plumbed in ar-2-03) overrides any auto-detected value via `dataclasses.replace`.

3. **TEST-04 consolidation** — Single `test_caps_consolidated.py` file containing both the Reasoner-half cap test (NEW in Wave 3) and the Verifier-half cap test (absorbed from Wave 2's `test_verifier_cap.py`). Wave 2's standalone file is REMOVED so the consolidated file is the single source of cap tests.

Output:
- One file modified: `lib/research/tools/web_search.py` (~30 LOC added: `vertex_gemini_grounding` callable + helper imports). Wave 1's existing Tavily/Brave/cascade code is UNCHANGED.
- One file modified: `lib/research/config.py` (~15 LOC added: two-signal auto-detect block; replaces the `google_search_grounding = None` placeholder).
- One new test file: `tests/unit/research/test_grounding_autodetect.py` (≥5 tests).
- One new test file: `tests/unit/research/test_caps_consolidated.py` (≥2 tests — Reasoner cap + Verifier cap).
- One file removed: `tests/unit/research/test_verifier_cap.py` (Wave 2's standalone — absorbed into consolidated).
- ar-1 + ar-2 + Wave 1 + Wave 2 regression suite still green; full count after Wave 3 ≥106 (Wave 2 baseline) − 1 (removed test_verifier_cap.py) + ≥5 (autodetect) + ≥2 (consolidated) = ≥112.

This plan does NOT touch the Verifier loop (Wave 2), the Reasoner loop (ar-2-01), the Synthesizer, the orchestrator, the dataclasses, or `lib/research/__main__.py` (CLI plumbing was finalized in ar-2-03 — `--no-grounding` already nullifies via `dataclasses.replace(cfg, google_search_grounding=None)` and works as-is once `from_env()` returns non-None values). It does NOT add new env vars.

After Wave 3 lands, the **Layer 2a cap=0 LLM-free CLI smoke** (mandatory at phase close) is runnable:

```bash
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding \
  "什么是 Hermes Harness 深度解析"
# expected: exit 0, ≥200 chars markdown, no exceptions
```

The **Layer 2b live-key smoke** (full pipeline with TAVILY+BRAVE keys) remains the phase-close gate, NOT a Wave 3 deliverable.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md
@.planning/phases/ar-3-verifier-web-tools/ar-3-01-web-tools-PLAN.md
@.planning/phases/ar-3-verifier-web-tools/ar-3-02-verifier-loop-PLAN.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/ROADMAP-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/config.py
@lib/research/tools/web_search.py
@lib/research/stages/reasoner.py
@lib/research/stages/verifier.py
@lib/research/__main__.py
@lib/vertex_gemini_complete.py
@lib/llm_complete.py

<interfaces>
**`vertex_gemini_grounding` callable (NEW in `lib/research/tools/web_search.py`):**

```python
async def vertex_gemini_grounding(query: str) -> str:
    """Vertex Gemini Google Search Grounding pass-through.

    Wraps a Vertex Gemini search-tool invocation. ar-3 ships a thin
    pass-through — full prompt-engineering is deferred to ar-4 final-tuning.

    Reads its own env (GOOGLE_APPLICATION_CREDENTIALS, OMNIGRAPH_GEMINI_KEY,
    GEMINI_API_KEY) at CALL time, NOT at module-import time. Rationale:
    auto-detect at from_env() time only checks "is Vertex selected?", not
    "is Vertex actually configured?" — call-time read defers credential
    failures to first invocation, where the Verifier's outer try/except
    surfaces them as status='failed' (Axis 3).

    Returns the grounded answer text as a single str. Raises on any failure.
    """
    # Implementation in Task 1 — pass-through to Vertex Gemini's search tool
```

The Vertex implementation reuses the existing `lib.vertex_gemini_complete` infrastructure. Signature is single-positional-arg async (no `api_key` kwarg) — matches the dataclass slot's `Callable | None` typing AND the Verifier's `_grounding_tool` wrapper signature `async def _grounding_tool(query: str) -> str`.

**`from_env()` auto-detect logic (modifications to `lib/research/config.py`):**

The current Wave 1 form ends with `google_search_grounding = None  # Wave 3 wires Vertex auto-detect`. Wave 3 replaces that single line with the two-signal block:

```python
# Vertex Gemini Grounding auto-detect (CONFIG-03 Wave-3 half):
# Promoted to "available" if EITHER signal indicates Vertex is the LLM provider.
# Both signals are checked (defense in depth): the env-var path wins when set,
# the bound-module path is the safety net for callers that constructed
# llm_complete directly without setting OMNIGRAPH_LLM_PROVIDER.
_provider_env = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "").strip().lower()
_llm_module = getattr(llm_complete, "__module__", "")

is_vertex = (
    _provider_env == "vertex_gemini"
    or _llm_module == "lib.vertex_gemini_complete"
)

if is_vertex:
    google_search_grounding = vertex_gemini_grounding  # zero-arg bind; reads env at call time
else:
    google_search_grounding = None
```

The import at the top of `config.py` is extended:

```python
from .tools.web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
    vertex_gemini_grounding,  # NEW in Wave 3
)
```

**`--no-grounding` CLI override interaction (UNCHANGED — ar-2-03 already plumbed it):**

`lib/research/__main__.py:_amain` already does:

```python
if ns.no_grounding:
    overrides["google_search_grounding"] = None
if overrides:
    cfg = dataclasses.replace(cfg, **overrides)
```

In Wave 3, this CLI override now has REAL work to do: when `from_env()` returns a `cfg` with `google_search_grounding=vertex_gemini_grounding`, the CLI flag nullifies it. Precedence: **CLI override > auto-detect > None default**.

**Vertex Gemini Grounding implementation (Task 1 specifics):**

The Wave 3 implementation is a thin pass-through. The simplest correct implementation imports the existing Vertex Gemini complete callable and asks for a search-grounded response:

```python
async def vertex_gemini_grounding(query: str) -> str:
    """Vertex Gemini Google Search Grounding pass-through (TOOL-03)."""
    # Lazy import to keep web_search.py importable without Vertex creds at import time.
    # The Verifier's outer try/except surfaces credential / quota errors as status='failed' (Axis 3).
    from lib.vertex_gemini_complete import complete_with_grounding
    return await complete_with_grounding(query)
```

If `lib.vertex_gemini_complete` does not yet expose a `complete_with_grounding` helper, Task 1 introduces ONE helper there using the Vertex SDK's grounding-tool API. The helper is the SOLE addition to `lib.vertex_gemini_complete` — no broader refactor. Read `lib/vertex_gemini_complete.py` during read_first to determine whether the helper exists or needs to be added.

If the existing module doesn't have a clean "ground-this-query" entry point, the alternative is to inline the Vertex grounding call in `vertex_gemini_grounding`:

```python
async def vertex_gemini_grounding(query: str) -> str:
    from google import genai
    from google.genai import types as genai_types

    # Reads creds from GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_CLOUD_PROJECT etc.
    client = genai.Client(vertexai=True, location="global")
    grounding_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
    config = genai_types.GenerateContentConfig(tools=[grounding_tool])
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=query,
        config=config,
    )
    return response.text
```

The executor chooses the cleaner path during Task 1 read_first. **Either path is acceptable** — the contract is: the callable exists, is async, takes a single `query: str`, returns a `str`, and reads its own env at call time. The CONTEXT explicitly calls out "thin pass-through wrapper" as the Wave 3 deliverable; full prompt-tuning lands in ar-4.

**Hard requirements (verbatim from CONTEXT.md § TOOL-03 + § CONFIG-03):**

1. `vertex_gemini_grounding` callable signature: `async def (query: str) -> str`. Single positional arg. No api_key kwarg.
2. Module body for `vertex_gemini_grounding` MUST NOT read env at import time. Lazy imports inside the function body are acceptable; module-level imports of `lib.vertex_gemini_complete` are NOT (would couple all of `lib/research/tools/` to Vertex creds at import time).
3. Auto-detect MUST check BOTH signals (`OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"` OR `llm_complete.__module__ == "lib.vertex_gemini_complete"`).
4. When non-Vertex: `cfg.google_search_grounding is None` UNCONDITIONALLY. Verifier's tool registry omits the grounding tool in that case (Wave 2 already enforces this).
5. `--no-grounding` CLI is final-word — overrides auto-detect. The CLI plumbing in `__main__.py` (ar-2-03) is unchanged; Wave 3 just makes the override actually have work to do.
6. NO new env vars (auto-detect reuses `OMNIGRAPH_LLM_PROVIDER`, already documented in ar-2 LLM provider selection).

**Imports allowed in `lib/research/tools/web_search.py` (Wave 3 additions):**

- (existing Wave 1 imports unchanged: `from __future__ import annotations`, `Awaitable, Callable`, `urlencode`, `httpx`)
- Wave 3 adds NO module-level imports for Vertex (lazy imports inside `vertex_gemini_grounding` only).

**Imports allowed in `lib/research/config.py` (Wave 3 additions):**

- Existing Wave 1 imports unchanged.
- Add `vertex_gemini_grounding` to the existing `from .tools.web_search import (...)` block.

**TEST-04 Reasoner-half cap mock harness (NEW in Wave 3):**

```python
# tests/unit/research/test_caps_consolidated.py — Reasoner-half
@pytest.mark.asyncio
async def test_reasoner_cap_enforcement():
    """LLM never emits final → loop terminates at iter_count == max_iter_reasoner."""
    from lib.research.stages.reasoner import run as run_reasoner, _LLMDecision, _ToolCall

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="kg_search", args={"query": "subq"}),),
        )

    # Stub kg_search at the module level so it doesn't touch LightRAG.
    import lib.research.stages.reasoner as reasoner_mod
    orig_kg_search = reasoner_mod.kg_search

    async def stub_kg_search(q, mode="hybrid"):
        return "stub kg result"

    reasoner_mod.kg_search = stub_kg_search
    try:
        cfg = _make_reasoner_cfg(mock_llm_never_final)  # default max_iter_reasoner=5
        retrieved = _make_retrieved()
        result = await run_reasoner("test query", cfg, retrieved)
    finally:
        reasoner_mod.kg_search = orig_kg_search

    assert result.iter_count == cfg.max_iter_reasoner  # exactly the cap (=5)
    assert result.status == "ok"  # cap is a budget, not an error
```

**Auto-detect mock harness:**

```python
# tests/unit/research/test_grounding_autodetect.py
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_autodetect_via_env_provider_vertex(monkeypatch, tmp_path):
    """OMNIGRAPH_LLM_PROVIDER=vertex_gemini → cfg.google_search_grounding is non-None."""
    from lib.research.config import from_env
    from lib.research.tools.web_search import vertex_gemini_grounding

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    # llm_complete is a stub; its __module__ doesn't matter — env signal is sufficient.
    stub_llm = AsyncMock()
    with patch("lib.llm_complete.get_llm_func", return_value=stub_llm), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is vertex_gemini_grounding


def test_autodetect_via_module_path_vertex(monkeypatch, tmp_path):
    """Bound llm_complete.__module__ == 'lib.vertex_gemini_complete' → grounding non-None."""
    from lib.research.config import from_env
    from lib.research.tools.web_search import vertex_gemini_grounding

    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    # Construct a stub callable whose __module__ matches the Vertex impl module path.
    async def _stub_vertex_complete(*args, **kwargs):
        return None
    _stub_vertex_complete.__module__ = "lib.vertex_gemini_complete"

    with patch("lib.llm_complete.get_llm_func", return_value=_stub_vertex_complete), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is vertex_gemini_grounding


def test_autodetect_deepseek_yields_no_grounding(monkeypatch, tmp_path):
    """OMNIGRAPH_LLM_PROVIDER=deepseek (or unset) AND llm_complete.__module__ != vertex → grounding None."""
    from lib.research.config import from_env

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    async def _stub_deepseek_complete(*args, **kwargs):
        return None
    _stub_deepseek_complete.__module__ = "lib.deepseek_complete"

    with patch("lib.llm_complete.get_llm_func", return_value=_stub_deepseek_complete), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is None


def test_no_grounding_cli_override_nullifies_autodetect(monkeypatch, tmp_path):
    """from_env() returns non-None grounding; --no-grounding CLI override → None."""
    from lib.research.config import from_env

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is not None  # auto-detected

    # Simulate the CLI override path from __main__.py:_amain
    overrides = {"google_search_grounding": None}
    cfg2 = dataclasses.replace(cfg, **overrides)
    assert cfg2.google_search_grounding is None  # CLI override wins


@pytest.mark.asyncio
async def test_grounding_callable_is_zero_arg_factory_compatible():
    """vertex_gemini_grounding(query) returns an awaitable — matches Verifier's
    _grounding_tool signature (single positional str arg returning str)."""
    import inspect
    from lib.research.tools.web_search import vertex_gemini_grounding
    assert inspect.iscoroutinefunction(vertex_gemini_grounding)
    sig = inspect.signature(vertex_gemini_grounding)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "query"
    assert params[0].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                              inspect.Parameter.POSITIONAL_ONLY)
```

The 5th test (`test_grounding_callable_is_zero_arg_factory_compatible`) does NOT call `vertex_gemini_grounding` (it would attempt a real Vertex API call). It only inspects the signature. The actual end-to-end behavior is exercised by Layer 2b live-key smoke at phase close.

**Cap consolidation harness:**

```python
# tests/unit/research/test_caps_consolidated.py
"""TEST-04 consolidated cap tests — Reasoner cap (default 5) + Verifier cap
(default 3). Absorbs and replaces tests/unit/research/test_verifier_cap.py
(which is removed in Wave 3).
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lib.research.types import (
    ReasonerOutput, ResearchConfig, RetrievedImage, RetrieverOutput, Source,
)


def _make_reasoner_cfg(llm_complete, **overrides) -> ResearchConfig:
    base = dict(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=llm_complete,
        embedding_func=AsyncMock(),
        vision_cascade=MagicMock(),
        web_search=AsyncMock(return_value=[]),
        web_extract=AsyncMock(return_value=""),
        web_search_fallback=None,
        google_search_grounding=None,
    )
    base.update(overrides)
    return ResearchConfig(**base)


def _make_verifier_cfg(llm_complete, **overrides) -> ResearchConfig:
    return _make_reasoner_cfg(llm_complete, **overrides)


def _make_retrieved() -> RetrieverOutput:
    return RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="seed", snippet="seed text")],
        image_candidates=[],
    )


def _make_reasoned() -> ReasonerOutput:
    return ReasonerOutput(
        inferences_md="Mock inferences.",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=1,
        status="ok",
    )


@pytest.mark.asyncio
async def test_reasoner_cap_enforcement():
    from lib.research.stages.reasoner import run as run_reasoner, _LLMDecision, _ToolCall

    async def mock_llm(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="kg_search", args={"query": "subq"}),),
        )

    # Stub kg_search to avoid LightRAG.
    import lib.research.stages.reasoner as reasoner_mod
    orig_kg_search = reasoner_mod.kg_search

    async def stub_kg_search(q, mode="hybrid"):
        return "stub"

    reasoner_mod.kg_search = stub_kg_search
    try:
        cfg = _make_reasoner_cfg(mock_llm)  # default max_iter_reasoner=5
        result = await run_reasoner("q", cfg, _make_retrieved())
    finally:
        reasoner_mod.kg_search = orig_kg_search

    assert result.iter_count == cfg.max_iter_reasoner
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_verifier_cap_enforcement_consolidated():
    from lib.research.stages.verifier import run as run_verifier, _LLMDecision, _ToolCall

    async def mock_llm(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="web_search", args={"query": "subq"}),),
        )

    cfg = _make_verifier_cfg(mock_llm)  # default max_iter_verifier=3
    result = await run_verifier("q", cfg, _make_reasoned())

    assert result.iter_count == cfg.max_iter_verifier
    assert result.status == "ok"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add vertex_gemini_grounding async pass-through callable to lib/research/tools/web_search.py</name>
  <read_first>
    - lib/research/tools/web_search.py (Wave 1 form — add the new callable WITHOUT modifying any of the existing Tavily/Brave/cascade code)
    - lib/vertex_gemini_complete.py (existing Vertex Gemini infrastructure — determine whether a clean "ground-this-query" helper exists; if not, decide whether to add one OR inline the grounding call in vertex_gemini_grounding)
    - lib/llm_complete.py (provider dispatch — confirms how OMNIGRAPH_LLM_PROVIDER routes to lib.vertex_gemini_complete)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TOOL-03: Vertex Gemini Google Search Grounding"
    - docs/VERTEX_AI_MIGRATION_SPEC.md (Vertex SDK auth + grounding-tool reference)
  </read_first>
  <files>lib/research/tools/web_search.py</files>
  <behavior>
    `lib/research/tools/web_search.py` MUST satisfy after this task:
    - Adds ONE new async callable: `async def vertex_gemini_grounding(query: str) -> str`.
    - Signature: single positional `query: str` arg; no `api_key` kwarg; returns `str`.
    - Reads its own env at CALL time (lazy imports inside the function body); does NOT read env at module-import time.
    - Module-level imports are unchanged from Wave 1 (no top-level Vertex / google.genai imports — would couple `lib/research/tools/` to Vertex creds at import time).
    - Wave 1's existing Tavily/Brave/cascade code is BYTE-FOR-BYTE UNCHANGED.
    - `__all__` is extended to include `"vertex_gemini_grounding"`.
    - Module body still contains zero `os.environ` reads (env reads inside the function are via the lazily-imported Vertex SDK; no direct `os.environ.get(...)` in this module).
    - Module body still contains zero `omnigraph_search.*` imports (CONTRACT-01).
    - Module body still contains zero `~/.hermes` / `omonigraph-vault` literals (CONTRACT-02).
  </behavior>
  <action>
    1. Open `lib/research/tools/web_search.py`. Locate the end of the file (after `make_web_search_with_fallback` and before `__all__`).

    2. Determine the Vertex impl path during read_first. TWO branches:

       **Branch A** — `lib/vertex_gemini_complete.py` already exposes a "ground-this-query" helper (e.g., `complete_with_grounding(query: str) -> str`). Use it:
       ```python
       async def vertex_gemini_grounding(query: str) -> str:
           """Vertex Gemini Google Search Grounding pass-through (TOOL-03).

           Thin pass-through. Full prompt-engineering deferred to ar-4 final-tuning.
           Reads creds at call time via lib.vertex_gemini_complete (lazy import keeps
           web_search.py importable without Vertex creds at module-import time).

           Returns the grounded answer text. Raises on any failure — the Verifier's
           outer try/except surfaces failures as status='failed' (Axis 3).
           """
           from lib.vertex_gemini_complete import complete_with_grounding
           return await complete_with_grounding(query)
       ```

       **Branch B** — no clean helper exists. Inline the Vertex grounding call:
       ```python
       async def vertex_gemini_grounding(query: str) -> str:
           """Vertex Gemini Google Search Grounding pass-through (TOOL-03).

           Reads creds at call time via google.genai client construction.
           Returns the grounded answer text. Raises on any failure.
           """
           from google import genai
           from google.genai import types as genai_types

           client = genai.Client(vertexai=True, location="global")
           grounding_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
           config = genai_types.GenerateContentConfig(tools=[grounding_tool])
           response = await client.aio.models.generate_content(
               model="gemini-2.5-flash",
               contents=query,
               config=config,
           )
           return response.text or ""
       ```

       Branch A is preferred when feasible (cleaner; reuses existing Vertex infrastructure). Branch B is the fallback.

       Document the chosen branch in SUMMARY.md.

    3. Extend the module's `__all__`:
       ```python
       __all__ = [
           "brave_search",
           "make_web_search_with_fallback",
           "tavily_extract",
           "tavily_search",
           "vertex_gemini_grounding",  # NEW in Wave 3
       ]
       ```

    4. Update `lib/research/tools/__init__.py` to also re-export `vertex_gemini_grounding`:
       ```python
       from .web_search import (
           brave_search,
           make_web_search_with_fallback,
           tavily_extract,
           tavily_search,
           vertex_gemini_grounding,
       )

       __all__ = [
           "brave_search",
           "make_web_search_with_fallback",
           "tavily_extract",
           "tavily_search",
           "vertex_gemini_grounding",
       ]
       ```

    5. CONTRACT-01 grep: `grep -n "omnigraph_search" lib/research/tools/` — expected 0 hits.
       CONTRACT-02 grep: `grep -nE "/.hermes|omonigraph-vault" lib/research/tools/` — expected 0 hits.
       Module-level `os.environ` audit: `grep -n "os.environ" lib/research/tools/web_search.py` — expected 0 hits.

    6. Smoke import (do NOT call the function — would attempt real Vertex API):
       ```bash
       venv/Scripts/python.exe -c "
       from lib.research.tools.web_search import vertex_gemini_grounding
       from lib.research.tools import vertex_gemini_grounding as vg2
       import inspect
       assert inspect.iscoroutinefunction(vertex_gemini_grounding)
       sig = inspect.signature(vertex_gemini_grounding)
       params = list(sig.parameters.values())
       assert len(params) == 1 and params[0].name == 'query'
       print('vertex_gemini_grounding signature OK')
       "
       ```

    7. Run `bash scripts/check_contract.sh` — must exit 0.

    8. Run the full regression suite to confirm Wave 1 tests still pass: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.tools.web_search import vertex_gemini_grounding, tavily_search, brave_search, make_web_search_with_fallback; from lib.research.tools import vertex_gemini_grounding as vg2; import inspect; assert inspect.iscoroutinefunction(vertex_gemini_grounding); print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/tools/web_search.py` defines `async def vertex_gemini_grounding(query: str) -> str` with single positional arg.
    - Module-level imports unchanged from Wave 1 (NO top-level `from google import genai` or `from lib.vertex_gemini_complete import ...`).
    - `__all__` includes `"vertex_gemini_grounding"`.
    - `lib/research/tools/__init__.py` re-exports `vertex_gemini_grounding`.
    - Module body contains zero `os.environ` reads, zero `omnigraph_search.*` imports, zero `~/.hermes` / `omonigraph-vault` literals.
    - Smoke import succeeds; `inspect.iscoroutinefunction(vertex_gemini_grounding) is True`; signature has exactly one parameter named `query`.
    - `bash scripts/check_contract.sh` exits 0.
    - Wave 1 + Wave 2 regression suite still green (no test count regression).
  </acceptance_criteria>
  <done>vertex_gemini_grounding callable shipped; lazy-import discipline preserved; CONTRACT-01 + CONTRACT-02 still clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire Vertex auto-detect into ResearchConfig.from_env() — replace Wave 1's `google_search_grounding = None` placeholder with two-signal detection</name>
  <read_first>
    - lib/research/config.py (Wave 1 form — locate the line `google_search_grounding = None  # Wave 3 wires Vertex auto-detect`; this is the single line Wave 3 replaces)
    - lib/research/tools/web_search.py (just-modified — exposes vertex_gemini_grounding)
    - lib/llm_complete.py (read get_llm_func() to understand what __module__ the bound callable has when OMNIGRAPH_LLM_PROVIDER=vertex_gemini — typically lib.vertex_gemini_complete)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "CONFIG-03: from_env() updates" (Wave-3 half)
  </read_first>
  <files>lib/research/config.py</files>
  <behavior>
    `from_env()` MUST satisfy after this task:
    - When `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` (regardless of bound `llm_complete.__module__`): `cfg.google_search_grounding is vertex_gemini_grounding` (identity-comparable).
    - When `getattr(llm_complete, "__module__", "") == "lib.vertex_gemini_complete"` (regardless of `OMNIGRAPH_LLM_PROVIDER`): `cfg.google_search_grounding is vertex_gemini_grounding`.
    - When NEITHER signal is set (e.g., `OMNIGRAPH_LLM_PROVIDER=deepseek` AND `llm_complete.__module__ == "lib.deepseek_complete"`): `cfg.google_search_grounding is None`.
    - When `OMNIGRAPH_LLM_PROVIDER` is unset (no env value): the env signal is FALSE; only the module-path signal is checked.
    - The two-signal check is OR (either suffices). Both checks happen unconditionally — order doesn't matter.
    - The rest of `from_env()` (rag_working_dir, llm_complete, embedding_func, vision_cascade, web_search/extract/fallback wiring from Wave 1, output_dir, telemetry_jsonl, max_iter_*) is BYTE-FOR-BYTE UNCHANGED.
  </behavior>
  <action>
    1. Open `lib/research/config.py`. Locate the existing `from .tools.web_search import (...)` block (added in Wave 1 Task 2). Add `vertex_gemini_grounding` to the import list, alphabetized after `tavily_search`:
       ```python
       from .tools.web_search import (
           brave_search,
           make_web_search_with_fallback,
           tavily_extract,
           tavily_search,
           vertex_gemini_grounding,  # NEW in Wave 3
       )
       ```

    2. Locate the line `google_search_grounding = None  # Wave 3 wires Vertex auto-detect` (added in Wave 1 Task 2). Replace it with the two-signal block:
       ```python
       # Vertex Gemini Grounding auto-detect (CONFIG-03 Wave-3 half):
       # Promoted to "available" if EITHER signal indicates Vertex is the LLM provider.
       _provider_env = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "").strip().lower()
       _llm_module = getattr(llm_complete, "__module__", "")
       is_vertex = (
           _provider_env == "vertex_gemini"
           or _llm_module == "lib.vertex_gemini_complete"
       )
       if is_vertex:
           google_search_grounding = vertex_gemini_grounding
       else:
           google_search_grounding = None
       ```

    3. The `ResearchConfig(...)` constructor call at the bottom of `from_env()` is UNCHANGED.

    4. CONTRACT-01 grep: 0 hits. CONTRACT-02 grep: only the canonical `omonigraph` typo line stays (allow-listed).

    5. Smoke import:
       ```bash
       venv/Scripts/python.exe -c "
       from lib.research.config import from_env, _skipped_web_search
       from lib.research.tools.web_search import vertex_gemini_grounding
       print('config + grounding imports OK')
       "
       ```

    6. Run `bash scripts/check_contract.sh` — must exit 0.

    7. Run full regression suite to confirm no regressions: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.config import from_env; from lib.research.tools.web_search import vertex_gemini_grounding; print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/config.py` imports `vertex_gemini_grounding` from `.tools.web_search`.
    - The Wave-1 placeholder `google_search_grounding = None  # Wave 3 wires Vertex auto-detect` is gone.
    - The new two-signal auto-detect block is present (verified by literal `_provider_env == "vertex_gemini"` substring AND `_llm_module == "lib.vertex_gemini_complete"` substring AND the `is_vertex` boolean).
    - The `is_vertex` truthy branch binds `google_search_grounding = vertex_gemini_grounding` (identity-bound, NOT a wrapped partial).
    - `bash scripts/check_contract.sh` exits 0.
    - Wave 1 + Wave 2 + Task 1 (Wave 3) tests still pass — no regressions.
    - Smoke import succeeds.
  </acceptance_criteria>
  <done>from_env() auto-detects Vertex via two signals and wires cfg.google_search_grounding accordingly; CLI --no-grounding override still works (unchanged in __main__.py).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Write TOOL-03 + CONFIG-03 Wave-3-half mock test suite (≥5 tests for auto-detect + CLI override + signature)</name>
  <read_first>
    - tests/unit/research/test_web_tools.py (Wave 1 reference — same monkeypatch + lazy-import patch pattern)
    - lib/research/config.py (just-modified — gives the exact env var names + identity binding to assert)
    - lib/research/tools/web_search.py (Task 1 — provides vertex_gemini_grounding for identity-comparison)
    - lib/research/__main__.py (ar-2-03 — confirms the --no-grounding plumbing that Task 4 of this plan tests indirectly via dataclasses.replace)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TOOL-03" + § "CONFIG-03"
  </read_first>
  <files>tests/unit/research/test_grounding_autodetect.py</files>
  <behavior>
    Test file `test_grounding_autodetect.py` covers ≥5 tests, all using mocks:

    1. `test_autodetect_via_env_provider_vertex` — `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`; assert `cfg.google_search_grounding is vertex_gemini_grounding` (identity).
    2. `test_autodetect_via_module_path_vertex` — `OMNIGRAPH_LLM_PROVIDER` unset; bound `llm_complete.__module__ == "lib.vertex_gemini_complete"`; assert `cfg.google_search_grounding is vertex_gemini_grounding`.
    3. `test_autodetect_deepseek_yields_no_grounding` — `OMNIGRAPH_LLM_PROVIDER=deepseek` AND `llm_complete.__module__ == "lib.deepseek_complete"`; assert `cfg.google_search_grounding is None`.
    4. `test_no_grounding_cli_override_nullifies_autodetect` — env auto-detects Vertex (cfg has non-None grounding); apply `dataclasses.replace(cfg, google_search_grounding=None)` (simulates `--no-grounding` CLI path); assert `cfg2.google_search_grounding is None`.
    5. `test_grounding_callable_is_zero_arg_factory_compatible` — signature inspection only (NO call to Vertex). Assert `inspect.iscoroutinefunction(vertex_gemini_grounding) is True`; signature has exactly 1 positional parameter named `query`.

    All tests use mocks for `lib.llm_complete.get_llm_func`, `lib.lightrag_embedding.embedding_func`, and `lib.vision_cascade.VisionCascade` (so `from_env()` doesn't touch real provider/embedding/vision modules). Test 5 does NOT require any patching — it's signature-inspection only.
  </behavior>
  <action>
    1. Create `tests/unit/research/test_grounding_autodetect.py`. Imports:
       ```python
       import asyncio
       import dataclasses
       import inspect
       from unittest.mock import AsyncMock, MagicMock, patch

       import pytest
       ```

    2. Implement Tests 1-5 per `<interfaces>` § "Auto-detect mock harness" verbatim.

    3. The trick for Test 2 (module-path detection) is constructing a stub callable with the right `__module__` attribute:
       ```python
       async def _stub_vertex_complete(*args, **kwargs):
           return None
       _stub_vertex_complete.__module__ = "lib.vertex_gemini_complete"
       ```
       Then patch `lib.llm_complete.get_llm_func` to return that stub. The auto-detect block reads `getattr(llm_complete, "__module__", "")` and matches.

    4. The trick for Test 3 (no-detect) is the inverse — `__module__` is `"lib.deepseek_complete"` (or anything that doesn't match vertex):
       ```python
       async def _stub_deepseek_complete(*args, **kwargs):
           return None
       _stub_deepseek_complete.__module__ = "lib.deepseek_complete"
       ```

    5. Test 4 simulates the CLI override path WITHOUT actually invoking the CLI argparse — just calls `dataclasses.replace(cfg, google_search_grounding=None)` directly. This is the same call `__main__.py:_amain` makes when `ns.no_grounding` is true.

    6. Test 5 is signature-only — does NOT call `vertex_gemini_grounding(...)` (would attempt real Vertex API). Use `inspect.iscoroutinefunction` and `inspect.signature`.

    7. Run new file in isolation: `venv/Scripts/python.exe -m pytest tests/unit/research/test_grounding_autodetect.py -v`. All ≥5 must pass.

    8. Run full suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total ≥106 (Wave 2 baseline) + ≥5 (this task) = ≥111 (before Task 4's consolidated test file lands).

    9. Audit existing `test_web_tools.py` (Wave 1 from_env tests): they patched `os.environ` but did NOT explicitly handle `OMNIGRAPH_LLM_PROVIDER`. With Wave 3's auto-detect block reading that env var, Wave 1's tests may now produce non-None `cfg.google_search_grounding` IF the test environment has `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` leaking in. Surgical fix: add `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)` to Wave 1's `from_env` integration tests if any of them now fails. Document in SUMMARY.md.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_grounding_autodetect.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_grounding_autodetect.py` exists with ≥5 tests; all pass.
    - Test 1 specifically asserts `cfg.google_search_grounding is vertex_gemini_grounding` (identity, NOT equality).
    - Test 2 specifically constructs a stub with `__module__ = "lib.vertex_gemini_complete"` and asserts identity bind.
    - Test 3 specifically asserts `cfg.google_search_grounding is None` for non-Vertex provider.
    - Test 4 specifically asserts that `dataclasses.replace(cfg, google_search_grounding=None)` overrides an auto-detected non-None value.
    - Test 5 specifically asserts `iscoroutinefunction is True` AND signature has exactly 1 parameter named `query`.
    - Any `test_web_tools.py` surgical update (e.g., adding `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER")`) is ≤5 line diff total and documented in SUMMARY.md.
    - Full `tests/unit/research/` suite ≥111 tests passing after this task.
  </acceptance_criteria>
  <done>≥5 grounding-autodetect tests pass; full ar-1+ar-2+Wave-1+Wave-2 + Task 3 regression suite green (≥111 tests); test_web_tools.py surgical update if needed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Write TEST-04 consolidated cap test file (Reasoner-half + Verifier-half) and remove Wave 2's standalone test_verifier_cap.py</name>
  <read_first>
    - tests/unit/research/test_verifier_cap.py (Wave 2's standalone — its single test will be absorbed; the file will be DELETED)
    - tests/unit/research/test_reasoner_agent_loop.py (ar-2-01 — reference for Reasoner cap test mock pattern, including the kg_search monkeypatch trick)
    - lib/research/stages/reasoner.py (Reasoner cap behavior — assert iter_count == max_iter_reasoner = 5 by default)
    - lib/research/stages/verifier.py (Verifier cap behavior — assert iter_count == max_iter_verifier = 3 by default)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TEST-04: Cap enforcement"
  </read_first>
  <files>tests/unit/research/test_caps_consolidated.py</files>
  <behavior>
    Test file `test_caps_consolidated.py` covers ≥2 tests:

    1. `test_reasoner_cap_enforcement` — mock `cfg.llm_complete` always emits `kg_search` tool call (never finalizes); stub `kg_search` at the module level so it doesn't touch LightRAG; assert `result.iter_count == cfg.max_iter_reasoner` (default 5) AND `result.status == "ok"`. Mirrors Wave 2's Verifier-half cap test for the Reasoner.
    2. `test_verifier_cap_enforcement_consolidated` — same content as Wave 2's `test_verifier_cap.py:test_verifier_cap_enforcement` (rename the function for clarity in the consolidated context).

    After this file lands, Wave 2's `tests/unit/research/test_verifier_cap.py` is DELETED — the consolidated file is the single source of cap tests.
  </behavior>
  <action>
    1. Create `tests/unit/research/test_caps_consolidated.py` with the verbatim structure from `<interfaces>` § "Cap consolidation harness":
       - Module docstring noting absorption of `test_verifier_cap.py`.
       - Self-contained imports + helpers (`_make_reasoner_cfg`, `_make_verifier_cfg`, `_make_retrieved`, `_make_reasoned`).
       - `test_reasoner_cap_enforcement` (NEW — mirrors `test_verifier_cap_enforcement` but for Reasoner; uses kg_search monkeypatch trick from ar-2-01's `test_reasoner_caps_at_max_iter` test).
       - `test_verifier_cap_enforcement_consolidated` (renamed copy of Wave 2's test — body unchanged).

    2. Run the new file in isolation: `venv/Scripts/python.exe -m pytest tests/unit/research/test_caps_consolidated.py -v`. Both ≥2 tests must pass.

    3. **Delete** `tests/unit/research/test_verifier_cap.py`:
       ```bash
       rm tests/unit/research/test_verifier_cap.py
       ```
       Verify deletion: `ls tests/unit/research/test_verifier_cap.py` should report "No such file".

    4. Run full suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Expected total: previous Task 3 baseline ≥111 − 1 (deleted test_verifier_cap) + ≥2 (consolidated) = ≥112.

    5. CONTRACT-01 + CONTRACT-02 grep one final time across `lib/research/`:
       ```bash
       cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
       hits=$(grep -rE "from omnigraph_search" lib/research/ --include='*.py' \
         | grep -vE "from omnigraph_search\.query " \
         | grep -vE "from omnigraph_search\.query$" \
         | grep -vE "import omnigraph_search\.query" \
         || true) && \
       if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
       grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
         | grep -vE "config\.py|README\.md|^Binary"
       ```
       Expected: 0 violations.

    6. Run `bash scripts/check_contract.sh` — must exit 0.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_caps_consolidated.py -v &amp;&amp; test ! -f tests/unit/research/test_verifier_cap.py &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_caps_consolidated.py` exists with ≥2 tests; both pass.
    - `test_reasoner_cap_enforcement` specifically asserts `result.iter_count == cfg.max_iter_reasoner` (NOT `<=` — exactly cap; default 5).
    - `test_verifier_cap_enforcement_consolidated` specifically asserts `result.iter_count == cfg.max_iter_verifier` (default 3).
    - Both tests assert `result.status == "ok"` (cap = budget).
    - `tests/unit/research/test_verifier_cap.py` does NOT exist (deleted).
    - Full `tests/unit/research/` suite ≥112 tests passing.
    - CONTRACT-01 + CONTRACT-02 still clean.
    - `bash scripts/check_contract.sh` exits 0.
  </acceptance_criteria>
  <done>Cap tests consolidated; Wave 2's standalone removed; full ar-3 regression suite green (≥112 tests).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Run mandatory Layer 2a cap=0 LLM-free CLI smoke (phase-close gate for Wave 3)</name>
  <read_first>
    - lib/research/__main__.py (ar-2-03 form — confirms --max-iter-reasoner / --max-iter-verifier / --no-grounding flags exist and are wired via dataclasses.replace)
    - lib/research/orchestrator.py (orchestrator still runs all 5 stages even when iter_count caps are 0 — confirm Reasoner / Verifier short-circuit gracefully when the loop body never executes)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "Layer 2a — cap=0 LLM-free CLI smoke (mandatory, no keys required)"
  </read_first>
  <files>(no files modified — this is a smoke-test task)</files>
  <behavior>
    The Layer 2a smoke MUST exit 0 with non-empty markdown ≥200 chars. The smoke proves CLI plumbing end-to-end without touching live external services (Tavily/Brave/Vertex Grounding all bypassed because cap=0 prevents any tool call from being dispatched).
  </behavior>
  <action>
    1. Confirm prerequisites: `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` are NOT required for this smoke (cap=0 means the Verifier loop body never executes). However, the LLM provider AND embedding func MUST be configured — `from_env()` will fail at `get_llm_func()` if `OMNIGRAPH_LLM_PROVIDER`'s creds are not present.

       For the corp-network dev box, this typically means:
       - `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` (Vertex creds via `GOOGLE_APPLICATION_CREDENTIALS` to the SA JSON), OR
       - `OMNIGRAPH_LLM_PROVIDER=deepseek` with `DEEPSEEK_API_KEY=dummy` (DeepSeek is corp-blocked but the import-time defense allows `from_env()` to succeed; no LLM call is made because cap=0).

       The deepseek path with `DEEPSEEK_API_KEY=dummy` is the simpler smoke environment for local Wave 3 close (no Vertex creds required).

    2. Run the cap=0 smoke:
       ```bash
       cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
       OMNIGRAPH_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=dummy \
       venv/Scripts/python.exe -m omnigraph.research \
         --max-iter-reasoner 0 \
         --max-iter-verifier 0 \
         --no-grounding \
         "什么是 Hermes Harness 深度解析"
       ```
       (Adjust env vars to match the local dev box per CLAUDE.md § "Calling Foundation Model serving endpoints from local Python" — Vertex via VS Code metadata is the alternative.)

    3. Capture exit code and stdout. The smoke MUST satisfy:
       - Exit code = 0
       - Stdout ≥ 200 chars of markdown
       - Markdown contains the query echo (`什么是 Hermes Harness 深度解析`) somewhere
       - `result.state.verified.iter_count == 0` (cap=0 → loop body never executed)
       - `result.state.verified.status == "ok"` (cap=0 reached without the loop body executing is still "ok")
       - `result.state.reasoned.iter_count == 0` (same)
       - `result.state.reasoned.status == "ok"`
       - No stage raises (no traceback in stderr)
       - `ResearchState` dataclass populates all 5 stage fields (web_baseline, retrieved, reasoned, verified, synthesized)

       Note: the CLI prints only `result.markdown` to stdout — the deeper state assertions need a Python smoke script if exact-state inspection is required:
       ```bash
       venv/Scripts/python.exe -c "
       import asyncio
       import dataclasses
       from lib.research.config import from_env
       from lib.research.orchestrator import research

       cfg = from_env()
       cfg = dataclasses.replace(cfg, max_iter_reasoner=0, max_iter_verifier=0, google_search_grounding=None)
       result = asyncio.run(research('什么是 Hermes Harness 深度解析', cfg))

       assert len(result.markdown) >= 200, f'markdown too short: {len(result.markdown)}'
       assert result.state.reasoned.iter_count == 0
       assert result.state.reasoned.status == 'ok'
       assert result.state.verified.iter_count == 0
       assert result.state.verified.status == 'ok'
       assert result.state.synthesized is not None
       print('Layer 2a cap=0 smoke OK; markdown length:', len(result.markdown))
       "
       ```
       This Python harness avoids stdout-encoding issues on Windows and exposes the deeper state assertions.

    4. If the smoke fails, the most likely failure modes are:
       - **Reasoner with `max_iter_reasoner=0`**: the `while iter_count < 0` loop body never executes — `iter_count` stays 0, `status="ok"` (cap=0 is a degenerate cap). Confirm the existing Reasoner code handles this correctly. If it asserts `iter_count >= 1` somewhere, that's a bug; fix in `reasoner.py`.
       - **Verifier with `max_iter_verifier=0`**: same shape. The current Wave 2 code uses `while iter_count < cfg.max_iter_verifier:` — with cap=0, the body never executes, returns `status="ok"` with empty values.
       - **`from_env()` LLM provider import fails**: switch to `OMNIGRAPH_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=dummy` (the simplest local smoke environment).
       - **WebBaseline / Retriever stage fails because TAVILY_API_KEY unset**: WebBaseline emits `status="skipped"` with the canonical reason; Retriever runs against the local KG. Both should be `ok` or `skipped` (not `failed`). If they fail with cap=0, that's a regression in ar-1's stage stubs — out of Wave 3 scope; flag in SUMMARY.md.

    5. Document the exact command run + stdout snippet (first 500 chars) + exit code in SUMMARY.md.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; OMNIGRAPH_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import asyncio; import dataclasses; from lib.research.config import from_env; from lib.research.orchestrator import research; cfg = dataclasses.replace(from_env(), max_iter_reasoner=0, max_iter_verifier=0, google_search_grounding=None); result = asyncio.run(research('什么是 Hermes Harness 深度解析', cfg)); assert len(result.markdown) >= 200; assert result.state.reasoned.iter_count == 0; assert result.state.verified.iter_count == 0; print('OK', len(result.markdown))"</automated>
  </verify>
  <acceptance_criteria>
    - Layer 2a cap=0 smoke exits 0.
    - Stdout ≥ 200 chars of markdown.
    - `result.state.reasoned.iter_count == 0` AND `result.state.reasoned.status == "ok"`.
    - `result.state.verified.iter_count == 0` AND `result.state.verified.status == "ok"`.
    - `result.state.synthesized is not None` (terminal stage populated).
    - No tracebacks in stderr.
    - SUMMARY.md documents the exact command run + stdout first-500-chars + exit code.
  </acceptance_criteria>
  <done>Layer 2a cap=0 LLM-free smoke passes; CLI plumbing verified end-to-end without external services; phase-close gate for Wave 3 met.</done>
</task>

</tasks>

<verification>
- All five tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥112 tests passing.
- CONTRACT-01 grep re-check (0 forbidden hits — Wave 3 added zero `omnigraph_search.*` imports across all of `lib/research/`):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ --include='*.py' \
    | grep -vE "from omnigraph_search\.query " \
    | grep -vE "from omnigraph_search\.query$" \
    | grep -vE "import omnigraph_search\.query" \
    || true) && \
  if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
  ```
- CONTRACT-02 grep re-check:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits.
- `bash scripts/check_contract.sh` exits 0.
- File deletion check: `tests/unit/research/test_verifier_cap.py` MUST NOT exist (Task 4 step 3 deleted it).
- Smoke imports:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -c "
  from lib.research.tools.web_search import vertex_gemini_grounding, tavily_search, brave_search, make_web_search_with_fallback
  from lib.research.config import from_env
  from lib.research.stages.verifier import run as run_v, _LLMDecision as VLD, _ToolCall as VTC
  from lib.research.stages.reasoner import run as run_r, _LLMDecision as RLD, _ToolCall as RTC
  import inspect
  assert inspect.iscoroutinefunction(vertex_gemini_grounding)
  assert inspect.iscoroutinefunction(run_v)
  assert inspect.iscoroutinefunction(run_r)
  print('all ar-3 wave-3 imports OK')
  "
  ```
- Layer 2a cap=0 LLM-free CLI smoke passes (Task 5 automated check).
- Layer 2b live-key smoke remains the **phase-close gate** owned by the orchestrator (out of Wave 3 scope; requires TAVILY+BRAVE keys injected to `~/.hermes/.env` per Operator note).
</verification>

<success_criteria>
- ROADMAP § "Phase ar-3" Success Criterion #1 (Verifier real bounded loop): ✓ delivered (Wave 2 + Wave 3 honors conditional grounding via auto-detect).
- ROADMAP Success Criterion #2 (cfg.web_search live Tavily): ✓ delivered (Wave 1).
- ROADMAP Success Criterion #3 (Brave fallback exactly once): ✓ delivered (Wave 1).
- ROADMAP Success Criterion #4 (cfg.google_search_grounding auto-detect for Vertex; --no-grounding override): ✓ delivered by Tasks 1+2+3.
- ROADMAP Success Criterion #5 (cap tests for both loops): ✓ delivered by Task 4 (`test_caps_consolidated.py`).
- REQ TOOL-03 (Vertex Gemini Grounding pass-through callable) ✓ delivered by Task 1.
- REQ CONFIG-03 (Wave-3 half — auto-detect + --no-grounding override): ✓ delivered by Tasks 2+3.
- REQ TEST-04 (Reasoner-half + consolidation): ✓ delivered by Task 4.
- Layer 2a cap=0 LLM-free CLI smoke ✓ delivered by Task 5 (mandatory phase-close gate for Wave 3).
- Layer 2b live-key smoke is the phase-close gate (NOT a Wave 3 deliverable; orchestrator runs it after all 3 waves land).
- CONTRACT-01 + CONTRACT-02 still clean.

After Wave 3 lands, the orchestrator can:
1. Run the Layer 2b live-key smoke against Hermes (with `TAVILY_API_KEY` + `BRAVE_SEARCH_API_KEY` + Vertex creds in `~/.hermes/.env`):
   ```bash
   venv/Scripts/python.exe -m omnigraph.research "什么是 Hermes Harness 深度解析"
   ```
2. Mark ar-3 complete in `STATE-Agentic-RAG-v1.md` and `ROADMAP-Agentic-RAG-v1.md` with the verbatim per-criterion checklist.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-3-verifier-web-tools/ar-3-03-SUMMARY.md` documenting:
- Files modified + LOC count for each (web_search.py +30 LOC; config.py +15 LOC; tools/__init__.py +1 LOC).
- Files created + LOC count for each (test_grounding_autodetect.py ~150 LOC; test_caps_consolidated.py ~120 LOC).
- Files deleted: `tests/unit/research/test_verifier_cap.py` (Wave 2's standalone, absorbed into consolidated).
- Test count: total in each new file, total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (0 forbidden hits).
- Vertex grounding implementation choice: Branch A (`lib.vertex_gemini_complete.complete_with_grounding`) or Branch B (inline `google.genai` call) — with one-line rationale.
- Layer 2a cap=0 LLM-free smoke output: exact command run, exit code, stdout first-500-chars, deeper-state assertions output.
- Any `test_web_tools.py` Wave-1 surgical update (e.g., `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER")` additions): list each test edited with line-count delta.
- Any deviations from plan with one-line rationale.
- Live-key Layer 2b smoke status: NOT executed in Wave 3 — defer to phase-close. Note in SUMMARY: "phase-close orchestrator runs Layer 2b after Wave 3 lands."
</output>

## Planner-flagged ambiguities

1. **`vertex_gemini_grounding` sync vs async.** The planner spec defines it as `async def` to match the dataclass `Callable | None` slot's typing convention used by other tools (Tavily/Brave are async; Verifier's `_grounding_tool` wrapper is async). A sync alternative would force the Verifier wrapper to use `await asyncio.to_thread(...)` — workable but breaks symmetry with the other tools. Default: async.

2. **Branch A vs Branch B for grounding implementation.** Branch A reuses `lib.vertex_gemini_complete.complete_with_grounding` if it exists; Branch B inlines the `google.genai` grounding call. Branch A preferred for cleanliness but requires the helper to exist. Executor decides at Task 1 read_first time.

3. **`test_caps_consolidated.py` absorbing Wave 2's `test_verifier_cap.py`.** The planner default is to DELETE the Wave 2 file after consolidation (single source of truth for cap tests). An alternative is to keep both files (Wave 2's is a duplicate of one consolidated test). Default: delete — avoids duplicate-test confusion. Task 4 step 3 enforces this.

4. **Two-signal vs one-signal auto-detect.** The CONTEXT spec mandates both signals are checked (OR). A simpler one-signal alternative (e.g., only the env signal) would miss callers who construct `llm_complete` without setting `OMNIGRAPH_LLM_PROVIDER` (e.g., test fixtures, programmatic config). The two-signal approach is defense in depth. Default: two-signal as specified.

5. **Layer 2a smoke's LLM provider choice.** The planner spec recommends `OMNIGRAPH_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=dummy` for the local cap=0 smoke (simplest env; no LLM call made because cap=0). An alternative is Vertex via VS Code metadata — also works but requires the user to run from the VS Code integrated terminal. Default: deepseek-dummy for portability. Document the chosen env in SUMMARY.md.

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env (Wave 1+2 unit tests use mocks; Wave 3 Grounding test uses mocks; live-key Layer 2b smoke is the phase-close gate).
