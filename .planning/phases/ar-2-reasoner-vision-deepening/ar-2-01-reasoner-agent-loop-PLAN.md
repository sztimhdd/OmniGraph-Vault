---
phase: ar-2-reasoner-vision-deepening
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/research/stages/reasoner.py
  - tests/unit/research/test_reasoner_agent_loop.py
autonomous: true
requirements:
  - ORCH-03
  - TOOL-04
  - TEST-03

must_haves:
  truths:
    - "Reasoner.run() executes a bounded LLM agent loop with kg_search + vision_analyze tools and never raises out (ORCH-03 + Axis 3)"
    - "Loop cap iter_count <= cfg.max_iter_reasoner (default 5) is enforced as part of the loop condition, not post-loop"
    - "Reaching the cap returns status='ok' with whatever was collected — the cap is a budget, not an error"
    - "Any exception inside the loop returns ReasonerOutput(status='failed', reason=str(e), iter_count=<current>) — no raise propagates"
    - "kg_search tool wraps omnigraph_search.query.search via the SAME import the Retriever uses (CONTRACT-01 — only one omnigraph_search.query import line allowed in lib/research/)"
    - "vision_analyze tool wraps cfg.vision_cascade.describe — no new vision infrastructure introduced (TOOL-04)"
    - "ReasonerOutput.analyzed_images is a list[RetrievedImage] where each entry has caption populated (NOT None) — captions sourced from cfg.vision_cascade.describe()"
    - "iter_count returned in ReasonerOutput is the post-loop turn count (number of agent turns actually taken)"
    - "Single iteration MAY run multiple vision_analyze calls in parallel via asyncio.gather() (Axis 1 carve-out — only blessed in-stage parallelism)"
    - "TEST-03 Reasoner-half asserts: iter_count >= 1, analyzed_images non-empty, ≥1 entry has caption == '<MOCK_CAPTION>', cfg.vision_cascade.describe called ≥ 1 time"
  artifacts:
    - path: "lib/research/stages/reasoner.py"
      provides: "Real bounded LLM agent loop with kg_search + vision_analyze tools (replaces ar-1 stub body)"
      contains: "async def run(query, cfg, retrieved) -> ReasonerOutput, async def _kg_search_tool, async def _vision_analyze_tool"
    - path: "tests/unit/research/test_reasoner_agent_loop.py"
      provides: "TEST-03 Reasoner-half — mock-based test of the agent loop with mock llm_complete + mock vision_cascade"
      contains: "test_reasoner_runs_two_turn_loop, test_reasoner_caps_at_max_iter, test_reasoner_caps_returns_ok_not_failed, test_reasoner_catches_llm_exception, test_reasoner_catches_vision_exception"
  key_links:
    - from: "lib/research/stages/reasoner.py"
      to: "omnigraph_search.query.search"
      via: "from omnigraph_search.query import search as kg_search"
      pattern: "from omnigraph_search\\.query import search"
    - from: "lib/research/stages/reasoner.py"
      to: "cfg.vision_cascade.describe"
      via: "await cfg.vision_cascade.describe(image_path, question)"
      pattern: "cfg\\.vision_cascade\\.describe"
    - from: "lib/research/stages/reasoner.py"
      to: "cfg.llm_complete"
      via: "await cfg.llm_complete(prompt=..., tools=...)"
      pattern: "cfg\\.llm_complete"
---

<objective>
Replace the ar-1 deterministic-stub body in `lib/research/stages/reasoner.py` with a real bounded LLM agent loop. Two tools are exposed to the loop: `kg_search(query, top_k)` (wraps `omnigraph_search.query.search`) and `vision_analyze(image_path, question)` (wraps `cfg.vision_cascade.describe`). The loop terminates either when the LLM emits a final answer OR when `iter_count` reaches `cfg.max_iter_reasoner` (default 5). Any exception inside the loop is caught and surfaces as `status="failed"` per Axis 3.

Purpose:
- ORCH-03: deliver the Reasoner agent loop that the ar-1 plan deferred ("real loops land in ar-2").
- TOOL-04: reuse `lib/vision_cascade.py` directly via `cfg.vision_cascade` — introduce no new vision infrastructure.
- TEST-03 (Reasoner half): mock-based test asserting that the loop runs ≥1 turn, calls `vision_analyze` ≥1 time, and produces `analyzed_images` entries whose `caption` field carries the mocked vision-cascade output. The Synthesizer half of TEST-03 is delivered in ar-2-02.

Output:
- One file rewritten: `lib/research/stages/reasoner.py` (signature unchanged: `async def run(query, cfg, retrieved) -> ReasonerOutput`).
- One new test file: `tests/unit/research/test_reasoner_agent_loop.py` (≥5 tests, all using mocks — no live LLM or vision call).
- ar-1 regression suite still green (every existing test under `tests/unit/research/` continues to pass).

This plan does NOT touch the Synthesizer, the orchestrator, the CLI, or any other stage. It does NOT add a new helper module — the agent loop body lives inline in `reasoner.py`. (Rationale: the loop body is ~60-80 LOC. Splitting it into `lib/research/agent_loop.py` would be premature factoring — ar-3 will land a parallel Verifier loop, and only then is the abstraction's shape evident.)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/config.py
@lib/research/stages/reasoner.py
@lib/research/stages/retriever.py
@lib/vision_cascade.py
@omnigraph_search/query.py
@scripts/check_contract.sh

<interfaces>
**Reasoner.run() signature is UNCHANGED from ar-1:**

```python
async def run(
    query: str,
    cfg: ResearchConfig,
    retrieved: RetrieverOutput,
) -> ReasonerOutput:
    ...
```

The contract shape (`ReasonerOutput` dataclass with `inferences_md`, `additional_chunks`, `analyzed_images`, `iter_count`, `status`, `reason`) does NOT change in this plan. Only the body is replaced.

**Tool registry — built inside `run()`, NOT in `ResearchConfig`** (per-invocation, not session-level):

```python
async def _kg_search_tool(query: str, top_k: int = 10) -> str:
    """Wraps omnigraph_search.query.search. CONTRACT-01: reuses the SAME import
    path the Retriever uses — there is exactly ONE `from omnigraph_search.query
    import search` line in lib/research/ today (in retriever.py). This module
    adds the SECOND such line. No other omnigraph_search import is allowed."""
    return await kg_search(query, mode="hybrid")  # already async per omnigraph_search/query.py

async def _vision_analyze_tool(image_path: str, question: str) -> str:
    """Wraps cfg.vision_cascade.describe. TOOL-04: no new vision infrastructure.
    Returns a caption string suitable for inline image alt text."""
    return await cfg.vision_cascade.describe(image_path, question)
```

**Loop shape (deterministic, bounded):**

```python
iter_count = 0
collected_chunks: list[Source] = []
collected_images: list[RetrievedImage] = []  # captions filled in
final_answer = ""

try:
    while iter_count < cfg.max_iter_reasoner:
        iter_count += 1
        # cfg.llm_complete returns either a tool-call decision or a final answer.
        # The exact protocol shape (e.g., function-calling JSON, structured tool
        # response, or string-based marker) is determined by cfg.llm_complete's
        # contract — see lib/llm_complete.get_llm_func.
        decision = await cfg.llm_complete(
            prompt=_build_prompt(query, retrieved, collected_chunks, collected_images),
            tools=[
                {"name": "kg_search", "fn": _kg_search_tool},
                {"name": "vision_analyze", "fn": _vision_analyze_tool},
            ],
        )

        if decision.is_final:
            final_answer = decision.content
            break

        # Dispatch tool calls — possibly multiple in one turn, run in parallel
        # (Axis 1 carve-out for vision_analyze parallelism within a single iteration).
        tool_call_results = await asyncio.gather(
            *[_dispatch_tool_call(tc, _kg_search_tool, _vision_analyze_tool)
              for tc in decision.tool_calls],
            return_exceptions=True,
        )

        # Accumulate results into collected_chunks / collected_images. Any exception
        # in tool_call_results propagates to the outer except (Axis 3).
        for tc, result in zip(decision.tool_calls, tool_call_results):
            if isinstance(result, Exception):
                raise result
            if tc.name == "kg_search":
                collected_chunks.append(Source(
                    kind="kg_chunk",
                    uri="omnigraph_search.query.search",
                    snippet=result,
                ))
            elif tc.name == "vision_analyze":
                # tc.args contains image_path; build a RetrievedImage with caption
                collected_images.append(RetrievedImage(
                    article_hash=Path(tc.args["image_path"]).parent.name,
                    image_path=Path(tc.args["image_path"]),
                    caption=result,
                ))
except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
    return ReasonerOutput(
        inferences_md=final_answer,
        additional_chunks=collected_chunks,
        analyzed_images=collected_images,
        iter_count=iter_count,
        status="failed",
        reason=str(e),
    )

return ReasonerOutput(
    inferences_md=final_answer,
    additional_chunks=collected_chunks,
    analyzed_images=collected_images,
    iter_count=iter_count,
    status="ok",  # cap reached without final answer is still "ok" — cap is a budget, not an error
)
```

**Implementation note on `cfg.llm_complete` protocol:** the exact decision/tool-call object shape is the Reasoner's internal protocol — `cfg.llm_complete` is a `Callable` per ResearchConfig. The executor MAY introduce a small lightweight protocol type (e.g., a `_LLMDecision` dataclass with `is_final: bool`, `content: str`, `tool_calls: list[_ToolCall]`) inside `reasoner.py` to give the loop body shape. The protocol does NOT need to be exported. The mock test in `test_reasoner_agent_loop.py` constructs whatever shape the implementation expects — the mock IS the contract for ar-2 (real LLM provider integration / function-calling JSON parsing is an ar-3+ refinement, NOT an ar-2 concern).

**Hard requirements (verbatim from CONTEXT.md § ORCH-03 + TOOL-04):**

1. `iter_count` is the post-loop value (number of agent turns actually taken), NOT a counter pre-incremented past the cap.
2. `iter_count <= cfg.max_iter_reasoner` ALWAYS holds — cap enforcement is part of the loop condition, not a post-loop assertion.
3. Any exception inside the loop → return `ReasonerOutput(status="failed", reason=str(e), iter_count=<current>, ...)` per Axis 3.
4. Reaching the cap is NOT a failure — return `status="ok"` with whatever was collected; a separate "cap exhausted" log line is fine but does not change `status`.
5. Vision parallelism: a single iteration MAY run multiple `vision_analyze` calls in parallel via `asyncio.gather()`. This is the only blessed in-stage parallelism in ar-2.

**Imports allowed in `reasoner.py` (CONTRACT-01 + CONTRACT-02 audit):**

- `from __future__ import annotations`
- `import asyncio`
- `from dataclasses import dataclass` (only if a `_LLMDecision` / `_ToolCall` helper type is added — internal, not exported)
- `from pathlib import Path`
- `from omnigraph_search.query import search as kg_search` (CONTRACT-01 — the only allowed `omnigraph_search.*` import in this file)
- `from ..types import ReasonerOutput, ResearchConfig, RetrievedImage, RetrieverOutput, Source`

NO additional `omnigraph_search.*` imports. NO `~/.hermes` / `omonigraph-vault` literals (CONTRACT-02 — paths flow exclusively via `cfg.rag_working_dir` and `RetrievedImage.image_path`).

**TEST-03 mock harness (Reasoner-half, this plan):**

```python
# tests/unit/research/test_reasoner_agent_loop.py
import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lib.research.stages.reasoner import run as run_reasoner
from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    RetrievedImage,
    RetrieverOutput,
    Source,
)


def _make_cfg(llm_complete, vision_cascade, **overrides) -> ResearchConfig:
    """Build a minimal ResearchConfig for tests — bypasses from_env()."""
    return ResearchConfig(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=llm_complete,
        embedding_func=AsyncMock(),
        vision_cascade=vision_cascade,
        web_search=lambda q: [],
        **overrides,
    )


def _make_retrieved(image_path: Path) -> RetrieverOutput:
    return RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="test", snippet="seed kg text")],
        image_candidates=[RetrievedImage(
            article_hash=image_path.parent.name,
            image_path=image_path,
        )],
    )


@pytest.mark.asyncio
async def test_reasoner_runs_two_turn_loop(tmp_path):
    """Turn 1: vision_analyze tool call. Turn 2: final answer."""
    image_path = tmp_path / "abc1234567" / "5.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    # Mock vision_cascade.describe to always return the canonical caption.
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    # Mock cfg.llm_complete: turn 1 emits vision_analyze tool call, turn 2 emits final.
    # The exact decision/tool_call shape mirrors whatever reasoner.py defines.
    # Implementer: import the internal _LLMDecision / _ToolCall type from reasoner
    # for the test, OR design llm_complete's mock to match the implementation's
    # interpretation (whichever is cleaner — the test should look ~30 lines).
    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Return a decision-like object that the impl interprets as a vision_analyze tool call
            return _build_tool_call_decision(
                tool_name="vision_analyze",
                args={"image_path": str(image_path), "question": "what is in this image"},
            )
        else:
            return _build_final_decision(content="Final inferred answer.")

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(image_path)

    result = await run_reasoner("test query", cfg, retrieved)

    assert isinstance(result, ReasonerOutput)
    assert result.iter_count >= 1
    assert result.status == "ok"
    assert len(result.analyzed_images) >= 1
    assert any(img.caption == "<MOCK_CAPTION>" for img in result.analyzed_images)
    assert vision_cascade.describe.await_count >= 1


@pytest.mark.asyncio
async def test_reasoner_caps_at_max_iter(tmp_path):
    """LLM never emits final → loop terminates at iter_count == cap, status=ok."""
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm_never_final(prompt, tools):
        # Always emits a kg_search tool call, never a final answer.
        return _build_tool_call_decision(
            tool_name="kg_search",
            args={"query": "subquery", "top_k": 5},
        )

    # Patch kg_search at import site so it returns a string without hitting LightRAG.
    import lib.research.stages.reasoner as reasoner_mod
    orig_kg_search = reasoner_mod.kg_search

    async def stub_kg_search(q, mode="hybrid"):
        return "stub kg result"

    reasoner_mod.kg_search = stub_kg_search
    try:
        cfg = _make_cfg(mock_llm_never_final, vision_cascade)
        cfg = dataclasses.replace(cfg, max_iter_reasoner=3)  # tight cap for test speed
        retrieved = _make_retrieved(tmp_path / "deadbeef00" / "1.jpg")
        result = await run_reasoner("test", cfg, retrieved)
    finally:
        reasoner_mod.kg_search = orig_kg_search

    assert result.iter_count == 3  # exactly the cap
    assert result.status == "ok"  # cap is a budget, not an error


@pytest.mark.asyncio
async def test_reasoner_caps_returns_ok_not_failed():
    """Explicit assertion: cap reached → status='ok', NOT 'failed'."""
    # ... same shape as above, asserting result.status == "ok" specifically


@pytest.mark.asyncio
async def test_reasoner_catches_llm_exception(tmp_path):
    """cfg.llm_complete raises → ReasonerOutput(status='failed', reason=str(e))."""
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm_raises(prompt, tools):
        raise RuntimeError("LLM provider down")

    cfg = _make_cfg(mock_llm_raises, vision_cascade)
    retrieved = _make_retrieved(tmp_path / "abc1234567" / "5.jpg")
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "failed"
    assert "LLM provider down" in result.reason


@pytest.mark.asyncio
async def test_reasoner_catches_vision_exception(tmp_path):
    """vision_cascade.describe raises → ReasonerOutput(status='failed', reason=str(e))."""
    image_path = tmp_path / "abc1234567" / "5.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(side_effect=RuntimeError("vision provider 503"))

    async def mock_llm(prompt, tools):
        return _build_tool_call_decision(
            tool_name="vision_analyze",
            args={"image_path": str(image_path), "question": "test"},
        )

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(image_path)
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "failed"
    assert "vision provider 503" in result.reason
```

The `_build_tool_call_decision` and `_build_final_decision` test helpers construct whatever decision-object shape the implementation chose. The executor implements those helpers in the test file or imports the internal protocol type from `reasoner.py` — either is acceptable.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace reasoner.py body with bounded LLM agent loop + tool dispatch</name>
  <read_first>
    - lib/research/stages/reasoner.py (current ar-1 stub — body to replace; signature preserved)
    - lib/research/stages/retriever.py (CONTRACT-01 reference — same `from omnigraph_search.query import search as kg_search` line; reasoner adds the second such line)
    - lib/research/types.py (ReasonerOutput shape — DO NOT modify)
    - lib/vision_cascade.py (cfg.vision_cascade duck-type; uses `describe(image_path, question) -> str` async method)
    - omnigraph_search/query.py (search signature; confirm whether it is async — affects whether `await` is needed in `_kg_search_tool`)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "ORCH-03 + TOOL-04: Reasoner agent loop" (loop shape)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "Best-effort failure handling (Axis 3)" (try/except wrap of full loop)
  </read_first>
  <files>lib/research/stages/reasoner.py</files>
  <behavior>
    Reasoner body MUST satisfy these observable behaviors (verified by Task 2 tests):
    - Returns a `ReasonerOutput` instance (frozen dataclass) with all 6 fields populated.
    - Calls `cfg.llm_complete` exactly once per iteration; loop terminates when LLM emits a "final answer" decision OR when `iter_count == cfg.max_iter_reasoner`.
    - When LLM emits a `vision_analyze` tool call: invokes `cfg.vision_cascade.describe(image_path, question)`, appends a `RetrievedImage(article_hash=Path(path).parent.name, image_path=Path(path), caption=<describe result>)` to `analyzed_images`.
    - When LLM emits a `kg_search` tool call: invokes the module-level `kg_search` (alias for `omnigraph_search.query.search`), appends a `Source(kind="kg_chunk", uri="omnigraph_search.query.search", snippet=<result>)` to `additional_chunks`.
    - Multiple tool calls in a single LLM decision are dispatched in parallel via `asyncio.gather()`.
    - Cap reached (iter_count == max_iter) → `status="ok"`, `iter_count == cap`.
    - Any exception in the loop body → `status="failed"`, `reason=str(e)`, `iter_count=<current>` — NEVER raises.
  </behavior>
  <action>
    1. Open `lib/research/stages/reasoner.py`. Preserve the module docstring header but UPDATE the "ar-1 stub" wording to reflect ar-2 reality ("Real bounded LLM agent loop with kg_search + vision_analyze tools (ORCH-03 + TOOL-04)").

    2. Replace the imports per `<interfaces>` § "Imports allowed in reasoner.py". Required:
       - `from __future__ import annotations`
       - `import asyncio`
       - `from dataclasses import dataclass` (for internal `_LLMDecision` / `_ToolCall` helpers if you choose)
       - `from pathlib import Path`
       - `from omnigraph_search.query import search as kg_search`  ← second CONTRACT-01-allowed line
       - `from ..types import ReasonerOutput, ResearchConfig, RetrievedImage, RetrieverOutput, Source`

    3. Define internal helper dataclasses (frozen) for the LLM-decision protocol — keep them MODULE-private (single leading underscore). Suggested:
       ```python
       @dataclass(frozen=True)
       class _ToolCall:
           name: str  # "kg_search" or "vision_analyze"
           args: dict[str, object]

       @dataclass(frozen=True)
       class _LLMDecision:
           is_final: bool
           content: str = ""  # populated when is_final=True
           tool_calls: tuple[_ToolCall, ...] = ()  # populated when is_final=False
       ```
       These are NOT exported. They define the contract between `cfg.llm_complete` and the loop. Test mocks construct them directly.

    4. Define the two tool wrappers as nested async functions inside `run()` (so they close over `cfg`):
       ```python
       async def _kg_search_tool(query: str, top_k: int = 10) -> str:
           # NOTE: confirm whether omnigraph_search.query.search is async during read_first.
           # If async, use `await kg_search(query, mode="hybrid")`.
           # If sync, drop the await. Match retriever.py's existing pattern.
           ...

       async def _vision_analyze_tool(image_path: str, question: str) -> str:
           return await cfg.vision_cascade.describe(image_path, question)
       ```

    5. Implement the loop body per `<interfaces>` § "Loop shape". Wrap the entire `while` in a single `try/except Exception as e:` (Axis 3 best-effort). Reaching the cap WITHOUT a final answer returns `status="ok"`. The exception path returns `status="failed", reason=str(e), iter_count=<current>`.

    6. Build the LLM prompt via a small helper `def _build_prompt(query, retrieved, collected_chunks, collected_images) -> str` — the prompt body itself can be minimal in ar-2 (final tuning is ar-4). At minimum it should include the query, the retrieved KG seed text, and a brief tool-availability statement. Inline the helper as a module-level private function.

    7. Tool-call dispatch (multiple per turn → parallel via `asyncio.gather`):
       ```python
       tool_call_results = await asyncio.gather(
           *[_dispatch(tc) for tc in decision.tool_calls],
           return_exceptions=True,
       )
       for tc, result in zip(decision.tool_calls, tool_call_results):
           if isinstance(result, BaseException):
               raise result  # propagates to outer except → status="failed"
           # accumulate into collected_chunks or collected_images
       ```
       where `_dispatch(tc)` is a small inline async function that selects between `_kg_search_tool` and `_vision_analyze_tool` based on `tc.name`.

    8. Return `ReasonerOutput(inferences_md=final_answer, additional_chunks=collected_chunks, analyzed_images=collected_images, iter_count=iter_count, status="ok")` after a clean exit (final answer OR cap reached).

    9. CONTRACT-02 audit: confirm zero `~/.hermes` / `omonigraph-vault` literals in the file. Image paths flow ONLY via `Path(tc.args["image_path"])` — string came from the LLM tool call args, which were built upstream from `state.retrieved.image_candidates[*].image_path` (already `cfg.rag_working_dir`-derived).

    10. Run `bash scripts/check_contract.sh` to confirm CONTRACT-01 + CONTRACT-02 still clean. The grep should now show TWO allowed `from omnigraph_search.query import search` lines (retriever.py + reasoner.py) but ZERO forbidden patterns.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.stages.reasoner import run; print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/stages/reasoner.py` imports without error.
    - Module body contains exactly one `from omnigraph_search.query import search as kg_search` line (no other `omnigraph_search.*` import).
    - `bash scripts/check_contract.sh` exits 0 (CONTRACT-01 + CONTRACT-02 clean).
    - Module body contains zero literal `~/.hermes` or `omonigraph-vault` substrings.
    - `run()` signature is unchanged: `async def run(query: str, cfg: ResearchConfig, retrieved: RetrieverOutput) -> ReasonerOutput`.
    - Module body contains the literal string `cfg.vision_cascade.describe` (TOOL-04 wiring proof).
    - Module body contains `asyncio.gather` (parallel tool dispatch — Axis 1 carve-out proof).
  </acceptance_criteria>
  <done>reasoner.py has the real agent-loop body; CONTRACT-01 + CONTRACT-02 clean; `from lib.research.stages.reasoner import run` works.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write TEST-03 Reasoner-half mock test suite + verify ar-1 regression suite still green</name>
  <read_first>
    - tests/unit/research/test_stages_stubs.py (ar-1 test patterns — pytest-asyncio, mock fixtures, ResearchConfig construction)
    - tests/unit/research/test_orchestrator.py (mock cfg patterns)
    - lib/research/stages/reasoner.py (just-written body — gives the executor the exact `_LLMDecision` / `_ToolCall` shape to construct in mocks)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "TEST-03: Reasoner loop mock test"
    - pyproject.toml § `[tool.pytest.ini_options]` (confirm `asyncio_mode = "auto"`)
  </read_first>
  <files>tests/unit/research/test_reasoner_agent_loop.py</files>
  <behavior>
    Test file `test_reasoner_agent_loop.py` covers:
    - Test 1 `test_reasoner_runs_two_turn_loop`: 2-turn sequence (turn 1 = vision_analyze tool call, turn 2 = final answer). Mock `cfg.vision_cascade.describe` returns `"<MOCK_CAPTION>"`. Asserts: `iter_count >= 1`, `status == "ok"`, `analyzed_images` non-empty, ≥1 entry has `caption == "<MOCK_CAPTION>"`, `cfg.vision_cascade.describe.await_count >= 1`.
    - Test 2 `test_reasoner_caps_at_max_iter`: LLM never emits final → loop terminates at `iter_count == cap` (use `cfg.max_iter_reasoner=3` for test speed). Asserts `result.iter_count == 3`, `result.status == "ok"`.
    - Test 3 `test_reasoner_caps_returns_ok_not_failed`: same shape as test 2 but explicit assertion `result.status == "ok"` — guards against a regression where someone "fixes" cap-reached to be a failure.
    - Test 4 `test_reasoner_catches_llm_exception`: `cfg.llm_complete` raises `RuntimeError("LLM provider down")` → `result.status == "failed"`, `"LLM provider down" in result.reason`, no raise out.
    - Test 5 `test_reasoner_catches_vision_exception`: `cfg.vision_cascade.describe` raises `RuntimeError("vision provider 503")` → `result.status == "failed"`, `"vision provider 503" in result.reason`, no raise out.
    - Test 6 `test_reasoner_kg_search_tool_appends_chunk`: turn 1 = kg_search tool call (mocked `omnigraph_search.query.search` returns `"stub kg result"` via monkeypatch), turn 2 = final. Asserts `len(result.additional_chunks) == 1`, `result.additional_chunks[0].kind == "kg_chunk"`, `result.additional_chunks[0].snippet == "stub kg result"`.
    - Test 7 `test_reasoner_parallel_vision_calls`: turn 1 emits TWO `vision_analyze` tool calls in one decision; verify `cfg.vision_cascade.describe` is awaited 2 times AND that the implementation used `asyncio.gather` (assert via timing — both mocked describe calls take 100ms via `asyncio.sleep`; total wall time < 180ms proves parallelism, vs ~200ms+ if sequential). Use `time.perf_counter` with a generous threshold.
  </behavior>
  <action>
    1. Create `tests/unit/research/test_reasoner_agent_loop.py`. Imports:
       ```python
       import asyncio
       import dataclasses
       import time
       from pathlib import Path
       from unittest.mock import AsyncMock, MagicMock

       import pytest

       from lib.research.stages.reasoner import run as run_reasoner, _LLMDecision, _ToolCall
       from lib.research.types import (
           ReasonerOutput, ResearchConfig, RetrievedImage, RetrieverOutput, Source,
       )
       ```
       (If executor named the helpers differently, adjust the import accordingly.)

    2. Build `_make_cfg(llm_complete, vision_cascade, max_iter_reasoner=5)` and `_make_retrieved(image_path)` helpers per `<interfaces>` § "TEST-03 mock harness". These are test-file-local — not shared.

    3. Implement Tests 1-7 above. Each test is independent (fresh mocks, fresh tmp_path). Use `pytest_asyncio` async-mode-auto (already configured).

    4. Test 7 (parallel-dispatch timing) is the only "soft" assertion — use `assert elapsed < 0.18` with a 100ms-per-describe sleep. If timing flakes in CI, the executor MAY relax to `assert vision_cascade.describe.await_count == 2` and document the relaxation in SUMMARY.md.

    5. Run the new test file in isolation FIRST: `venv/Scripts/python.exe -m pytest tests/unit/research/test_reasoner_agent_loop.py -v`. All 7 must pass.

    6. Then run the full ar-1 regression suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total test count must be `≥ 35 (ar-1 baseline) + 7 (this plan) = ≥ 42`.

    7. If ANY ar-1 test fails (regression), STOP and fix in `reasoner.py` — the ar-1 reasoner stub had `iter_count=0, status="skipped"`; ar-2 changes that to `iter_count >= 0, status="ok"|"failed"`. The ar-1 `test_stages_stubs.py` tests for the reasoner specifically asserted `status == "skipped"` and `iter_count == 0` and `reason mentions ar-2` — those tests are EXPECTED to need updates in this plan (they were placeholders explicitly tied to ar-1 behavior). Update the ar-1 reasoner-stub tests in `test_stages_stubs.py` to reflect the new ar-2 behavior:
       - `iter_count` may be `0` only if `cfg.llm_complete` returns `is_final=True` on turn 1; otherwise it should be `>= 1`.
       - `status` is `"ok"` (or `"failed"` if mocks raise), NOT `"skipped"`.
       - The `reason mentions ar-2` assertion should be REMOVED (no longer applicable — Reasoner is no longer a stub).
       - Test 8 in `test_stages_stubs.py` (the explicit reasoner stub test) should be reworked: with a mock `cfg.llm_complete` that immediately returns `_LLMDecision(is_final=True, content="")`, assert `result.status == "ok"`, `result.iter_count == 1`, `result.analyzed_images == []`, `result.additional_chunks == []`. This preserves the test's intent (smoke-check the Reasoner stub shape) while accommodating the ar-2 change.
       - Similarly the Test 1 in `test_orchestrator.py` should be updated: `result.state.reasoned.status == "skipped"` → `result.state.reasoned.status in {"ok", "failed"}` (the orchestrator default-cfg path uses real `cfg.llm_complete` from `from_env()`, which may succeed or fail depending on env). If executor wishes to keep the orchestrator test deterministic, inject a stub `cfg.llm_complete` that returns `_LLMDecision(is_final=True)` immediately and assert `status == "ok"`.

    8. Confirm any ar-1 test edits are SURGICAL (touch only the reasoner-stub assertions). Do NOT broadly rewrite ar-1 tests.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_reasoner_agent_loop.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_reasoner_agent_loop.py` exists with ≥7 tests; all pass.
    - Full `tests/unit/research/` suite has ≥42 tests passing (ar-1 baseline ≥35 + ar-2 ≥7).
    - Test 1 specifically asserts `caption == "<MOCK_CAPTION>"` on at least one analyzed_images entry (TEST-03 hard requirement).
    - Test 1 specifically asserts `cfg.vision_cascade.describe.await_count >= 1` (TEST-03 + TOOL-04 hard requirement — proves vision_cascade was actually invoked, not bypassed).
    - Test 4 + Test 5 specifically assert `result.status == "failed"` AND a substring of the original exception message in `result.reason` (Axis 3 proof).
    - ar-1 reasoner-stub assertions in `test_stages_stubs.py` and `test_orchestrator.py` updated surgically (≤10 line diffs total) to reflect the ar-2 reasoner behavior.
  </acceptance_criteria>
  <done>≥7 new Reasoner-loop tests pass; full ar-1 regression suite still green (≥42 total tests); ar-1 stub assertions surgically updated.</done>
</task>

</tasks>

<verification>
- Both tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥42 tests passing.
- CONTRACT-01 grep re-check (must return zero forbidden hits — exactly 2 allowed `from omnigraph_search.query import search` lines: retriever.py + reasoner.py):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ \
    --include='*.py' \
    | grep -vE "from omnigraph_search\.query " \
    | grep -vE "from omnigraph_search\.query$" \
    | grep -vE "import omnigraph_search\.query" \
    || true) && \
  if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
  ```
  Expected: 0 hits.
- CONTRACT-02 grep re-check:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits.
- `bash scripts/check_contract.sh` exits 0.
- Smoke-check the import path:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -c "from lib.research.stages.reasoner import run; import inspect; assert inspect.iscoroutinefunction(run); print('reasoner.run async ok')"
  ```

ar-2 Layer 2 smoke test (manual, documented step — full smoke is wired up in ar-2-03):
After ar-2-03 lands, the upgraded smoke command is:
```bash
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 2 \
  --max-iter-verifier 1 \
  --no-grounding \
  "什么是 Hermes Harness 深度解析"
```
This plan does NOT exercise the upgraded smoke (CLI flags don't exist yet) — Layer 2 smoke is the responsibility of ar-2-03.
</verification>

<success_criteria>
- ROADMAP § "Phase ar-2: Reasoner + vision deepening" Success Criterion #1: Reasoner executes a bounded LLM agent loop with `kg_search` and `vision_analyze` as tools, terminating at `iter_count <= max_iter_reasoner` (default 5), returning `iter_count` in `ReasonerOutput`. ✓ delivered by Task 1.
- ROADMAP Success Criterion #3: Reasoner uses `lib/vision_cascade.py` directly via `cfg.vision_cascade` — no new vision infra. ✓ enforced by acceptance criterion "module body contains literal `cfg.vision_cascade.describe`".
- ROADMAP Success Criterion #5 (Reasoner half): Mock-based test exercises Reasoner agent loop calling `vision_analyze` ≥1 time and confirms the resulting caption appears in `analyzed_images`. ✓ delivered by Task 2 Test 1 (`<MOCK_CAPTION>` round-trip). The Synthesizer half of #5 lands in ar-2-02.
- REQ ORCH-03 (Reasoner agent loop with cap + iter_count) ✓ delivered.
- REQ TOOL-04 (Reasoner uses existing `lib/vision_cascade.py`) ✓ delivered.
- REQ TEST-03 (Reasoner-half) ✓ delivered; Synthesizer-half lands in ar-2-02.
- CONTRACT-01 + CONTRACT-02 still clean.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-2-reasoner-vision-deepening/ar-2-01-SUMMARY.md` documenting:
- Files modified + LOC count for each (rough proxy for plan-size sanity).
- Test count: total in `tests/unit/research/test_reasoner_agent_loop.py`, total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (paste raw output — should be 0 forbidden hits, 2 allowed lines).
- ar-1 stub-test surgical updates: list each test edited in `test_stages_stubs.py` / `test_orchestrator.py` with line-count delta and one-line rationale.
- Any deviations from plan (with one-line rationale) — particularly: (a) whether the executor introduced a `_LLMDecision` / `_ToolCall` internal protocol type or a different shape; (b) whether `omnigraph_search.query.search` turned out to be sync vs async (affects `_kg_search_tool`'s `await`); (c) whether Test 7's timing assertion was relaxed to await-count-only.
- Smoke import check output (`from lib.research.stages.reasoner import run` works).
</output>

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env
