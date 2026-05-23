---
phase: ar-3-verifier-web-tools
plan: 02
type: execute
wave: 2
depends_on:
  - ar-3-01
files_modified:
  - lib/research/stages/verifier.py
  - tests/unit/research/test_verifier_agent_loop.py
  - tests/unit/research/test_verifier_cap.py
autonomous: true
status: planned
last_updated: "2026-05-23"
requirements:
  - ORCH-04
  - TEST-04

must_haves:
  truths:
    - "Verifier.run() executes a bounded LLM agent loop with web_search + web_extract tools (and conditionally google_search_grounding) and never raises out (ORCH-04 + Axis 3)"
    - "Loop cap iter_count <= cfg.max_iter_verifier (default 3) is enforced as part of the loop condition, not post-loop"
    - "Reaching the cap returns status='ok' with whatever was collected — the cap is a budget, not an error"
    - "Any exception inside the loop returns VerifierOutput(status='failed', reason=str(e), iter_count=<current>, confidence=0.0, empty lists) — no raise propagates"
    - "web_search_tool wraps cfg.web_search (already cascade-wrapped from Wave 1 when both keys present) — Verifier does NOT call cascade orchestration directly"
    - "web_extract_tool wraps cfg.web_extract; if cfg.web_extract is None, the tool raises RuntimeError('web_extract not configured') and the outer try/except surfaces it as status='failed'"
    - "google_search_grounding tool is conditionally registered IFF cfg.google_search_grounding is not None — when None, the Verifier prompt does NOT mention grounding and dispatch never sees the tool"
    - "Verifier prompt includes state.reasoned.inferences_md as the verification subject (the LLM has something to fact-check)"
    - "Verifier reads ONLY reasoned (the function's third positional argument) — does NOT touch other ResearchState fields"
    - "confidence is parsed from the LLM's final-answer payload and clamped to [0.0, 100.0]; parse failure → confidence=0.0 + a discrepancy line noting the parse failure (status stays 'ok')"
    - "iter_count is the post-loop turn count; iter_count <= cfg.max_iter_verifier ALWAYS holds"
    - "Single iteration MAY run multiple web_search / web_extract calls in parallel via asyncio.gather() (Axis 1 carve-out)"
    - "TEST-04 Verifier-half asserts: mock cfg.llm_complete that always emits tool_calls and never finalizes → result.iter_count == cfg.max_iter_verifier (default 3) AND result.status == 'ok'"
  artifacts:
    - path: "lib/research/stages/verifier.py"
      provides: "Real bounded LLM agent loop with web_search + web_extract (+ conditional google_search_grounding) tools — replaces ar-1 stub body"
      contains: "async def run(query, cfg, reasoned) -> VerifierOutput, internal _LLMDecision / _ToolCall protocol dataclasses"
    - path: "tests/unit/research/test_verifier_agent_loop.py"
      provides: "ORCH-04 tests — Verifier real loop with mock llm + mock tools"
      contains: "test_verifier_finalizes_after_one_turn, test_verifier_calls_web_search_tool, test_verifier_calls_web_extract_tool, test_verifier_omits_grounding_tool_when_grounding_none, test_verifier_includes_grounding_tool_when_set, test_verifier_includes_reasoned_inferences_md_in_prompt, test_verifier_returns_failed_on_llm_exception, test_verifier_clamps_confidence_to_0_100"
    - path: "tests/unit/research/test_verifier_cap.py"
      provides: "TEST-04 Verifier-half — cap enforcement test (Wave 3 may absorb into test_caps_consolidated.py)"
      contains: "test_verifier_cap_enforcement"
  key_links:
    - from: "lib/research/stages/verifier.py"
      to: "cfg.web_search"
      via: "results = await cfg.web_search(query) inside web_search_tool"
      pattern: "cfg\\.web_search"
    - from: "lib/research/stages/verifier.py"
      to: "cfg.web_extract"
      via: "content = await cfg.web_extract(url) inside web_extract_tool"
      pattern: "cfg\\.web_extract"
    - from: "lib/research/stages/verifier.py"
      to: "cfg.google_search_grounding (conditional)"
      via: "registered in tool registry IFF cfg.google_search_grounding is not None"
      pattern: "cfg\\.google_search_grounding"
    - from: "lib/research/stages/verifier.py"
      to: "reasoned.inferences_md"
      via: "_build_prompt(...) embeds reasoned.inferences_md as the fact-check subject"
      pattern: "reasoned\\.inferences_md"
    - from: "lib/research/stages/verifier.py"
      to: "cfg.llm_complete"
      via: "await cfg.llm_complete(prompt=..., tools=...)"
      pattern: "cfg\\.llm_complete"
---

<objective>
Wave 2 of ar-3 replaces the ar-1 stub body in `lib/research/stages/verifier.py` with a **real bounded LLM agent loop**. Two tools are exposed unconditionally: `web_search(query)` (wraps `cfg.web_search` — already cascade-wrapped from Wave 1) and `web_extract(url)` (wraps `cfg.web_extract`). A third tool `google_search_grounding(query)` is conditionally registered IFF `cfg.google_search_grounding is not None` (Wave 3 wires it; Wave 2 honors the conditional).

Loop terminates when the LLM emits a final answer OR when `iter_count` reaches `cfg.max_iter_verifier` (default 3). Any exception inside the loop is caught and surfaces as `status="failed"` per Axis 3.

Purpose:
- **ORCH-04** — Verifier agent loop deferred from ar-1/ar-2. Structure mirrors the Reasoner loop from ar-2-01 (same `_LLMDecision` / `_ToolCall` protocol, same parallel `asyncio.gather` dispatch, same outer try/except, same cap semantics).
- **TEST-04 Verifier-half** — mock-based test asserting the loop terminates at `iter_count == cfg.max_iter_verifier` when the LLM never finalizes, with `status="ok"`. Wave 3 mirrors this for the Reasoner and consolidates both into `test_caps_consolidated.py`.

Output:
- One file rewritten: `lib/research/stages/verifier.py` (signature unchanged: `async def run(query, cfg, reasoned) -> VerifierOutput`).
- One new test file: `tests/unit/research/test_verifier_agent_loop.py` (≥8 tests).
- One new test file: `tests/unit/research/test_verifier_cap.py` (1 test — Wave 3 may absorb).
- ar-1 + ar-2 + Wave 1 regression suite still green; full count after Wave 2 ≥106.

This plan does NOT touch the Reasoner, Synthesizer, orchestrator, CLI, dataclasses, the `tools/` submodule, or `from_env()`. The Verifier consumes Wave 1's cascade-wrapped `cfg.web_search` transparently.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md
@.planning/phases/ar-3-verifier-web-tools/ar-3-01-web-tools-PLAN.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/ROADMAP-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/config.py
@lib/research/stages/verifier.py
@lib/research/stages/reasoner.py
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-01-reasoner-agent-loop-PLAN.md

<interfaces>
**Verifier.run() signature is UNCHANGED from ar-1 stub:**

```python
async def run(
    query: str,
    cfg: ResearchConfig,
    reasoned: ReasonerOutput,
) -> VerifierOutput:
    ...
```

The contract shape (`VerifierOutput` with `fact_check_summary_md`, `confidence: float`, `external_citations: list[Source]`, `discrepancies: list[str]`, `iter_count: int`, `status`, `reason`) is locked from ar-1. Only the body is replaced.

**Internal protocol dataclasses (mirror Reasoner from ar-2-01):**

```python
@dataclass(frozen=True)
class _ToolCall:
    """One tool call. name is one of:
      - "web_search"               (always available)
      - "web_extract"              (always registered; raises if cfg.web_extract is None)
      - "google_search_grounding"  (conditionally available — only if cfg.google_search_grounding is not None)
    args carry tool-specific kwargs:
      - web_search:               {"query": str}
      - web_extract:              {"url": str}
      - google_search_grounding:  {"query": str}
    """
    name: str
    args: dict[str, object]


@dataclass(frozen=True)
class _LLMDecision:
    is_final: bool
    content: str = ""
    confidence: float = 0.0
    discrepancies: tuple[str, ...] = field(default_factory=tuple)
    tool_calls: tuple[_ToolCall, ...] = field(default_factory=tuple)
```

These are MODULE-private. Test mocks construct them directly. Reasoner's helpers in `reasoner.py` are NOT reused — Verifier defines its own copies (different fields on the final-answer branch).

**Tool wrappers (nested closures inside `run()`):**

```python
async def _web_search_tool(query: str) -> list[dict]:
    return await cfg.web_search(query)

async def _web_extract_tool(url: str) -> str:
    if cfg.web_extract is None:
        raise RuntimeError("web_extract not configured")
    return await cfg.web_extract(url)

# Conditional:
if cfg.google_search_grounding is not None:
    async def _grounding_tool(query: str) -> str:
        return await cfg.google_search_grounding(query)
```

**Loop shape (mirrors Reasoner pattern from ar-2-01):**

```python
iter_count = 0
collected_citations: list[Source] = []
discrepancies: list[str] = []
final_summary = ""
final_confidence = 0.0

try:
    while iter_count < cfg.max_iter_verifier:
        iter_count += 1
        decision = await cfg.llm_complete(prompt=..., tools=...)
        if decision.is_final:
            final_summary = decision.content
            try:
                final_confidence = max(0.0, min(100.0, float(decision.confidence)))
            except (TypeError, ValueError):
                final_confidence = 0.0
                discrepancies.append("Verifier: failed to parse confidence from LLM final answer")
            discrepancies.extend(decision.discrepancies)
            break
        results = await asyncio.gather(
            *[_dispatch(tc) for tc in decision.tool_calls],
            return_exceptions=True,
        )
        for tc, result in zip(decision.tool_calls, results):
            if isinstance(result, BaseException):
                raise result
            if tc.name == "web_search":
                for r in result:  # list[dict]
                    collected_citations.append(Source(
                        kind="web",
                        uri=str(r.get("url", "")),
                        title=(str(r.get("title", "")) or None),
                        snippet=(str(r.get("content", "")) or None),
                    ))
            elif tc.name == "web_extract":
                collected_citations.append(Source(
                    kind="web",
                    uri=str(tc.args["url"]),
                    snippet=str(result),
                ))
            elif tc.name == "google_search_grounding":
                collected_citations.append(Source(
                    kind="grounding",
                    uri=str(tc.args.get("query", query)),
                    snippet=str(result),
                ))
except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
    return VerifierOutput(
        fact_check_summary_md="",
        confidence=0.0,
        external_citations=[],
        discrepancies=[],
        iter_count=iter_count,
        status="failed",
        reason=str(e),
    )

return VerifierOutput(
    fact_check_summary_md=final_summary,
    confidence=final_confidence,
    external_citations=collected_citations,
    discrepancies=discrepancies,
    iter_count=iter_count,
    status="ok",
)
```

**`_build_prompt` helper (module-private):**

```python
def _build_prompt(
    query: str,
    reasoned: ReasonerOutput,
    collected_citations: list[Source],
    has_grounding: bool,
) -> str:
    parts = [
        f"Query: {query}",
        "",
        "You are the Verifier stage of an agentic-RAG pipeline. Fact-check the",
        "Reasoner's inferences against external web sources.",
        "",
        "Reasoner inferences (verification subject):",
        reasoned.inferences_md or "(empty)",
        "",
        "Available tools:",
        "  - web_search(query)",
        "  - web_extract(url)",
    ]
    if has_grounding:
        parts.append("  - google_search_grounding(query)")
    parts.append("")
    parts.append("Emit a final fact-check summary (with confidence 0-100 and a list"
                 " of discrepancies) when ready; otherwise emit one or more tool calls.")
    if collected_citations:
        parts.append("")
        parts.append(f"Citations gathered so far: {len(collected_citations)}")
    return "\n".join(parts)
```

**Hard requirements (verbatim from CONTEXT.md § ORCH-04):**

1. `iter_count` is the post-loop value; `iter_count <= cfg.max_iter_verifier` ALWAYS holds.
2. Any exception inside the loop → return `VerifierOutput(status="failed", reason=str(e), iter_count=<current>, confidence=0.0, fact_check_summary_md="", external_citations=[], discrepancies=[])` — empty lists, NOT partial. Rationale: the Synthesizer's degradation note shouldn't paste partial mid-loop citations as if they were final.
3. Cap reached is NOT a failure — return `status="ok"`.
4. `confidence` clamped to `[0.0, 100.0]`. Parse failure → `confidence=0.0` + discrepancy noting the parse issue. Status stays `"ok"` (parse issue is observation, not stage failure).
5. Verifier prompt MUST include `reasoned.inferences_md`. Verifier touches no other `ResearchState` field.
6. Tool-call parallelism within one iteration via `asyncio.gather()` (Axis 1 carve-out).
7. `cfg.web_search` is called as the WRAPPED form (cascade-aware when both keys set). Verifier does NOT implement primary/fallback.

**Imports allowed in `verifier.py`:**

- `from __future__ import annotations`
- `import asyncio`
- `from dataclasses import dataclass, field`
- `from ..types import ReasonerOutput, ResearchConfig, Source, VerifierOutput`

NO `omnigraph_search.*` imports. NO `~/.hermes` / `omonigraph-vault` literals. NO direct imports from `lib.research.tools.web_search` (callables flow via `cfg.web_*` fields).

**TEST-04 Verifier-half cap mock harness:**

```python
# tests/unit/research/test_verifier_cap.py
@pytest.mark.asyncio
async def test_verifier_cap_enforcement():
    """LLM never emits final → loop terminates at iter_count == max_iter_verifier."""
    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="web_search", args={"query": "subq"}),),
        )
    cfg = _make_cfg(mock_llm_never_final)  # default max_iter_verifier=3
    result = await run_verifier("test query", cfg, _make_reasoned())
    assert result.iter_count == cfg.max_iter_verifier  # exactly the cap (=3)
    assert result.status == "ok"  # cap is a budget, not an error
```

**TEST-04 ORCH-04 mock harness (selected, see Task 2 for full set):**

```python
# tests/unit/research/test_verifier_agent_loop.py — selected tests
@pytest.mark.asyncio
async def test_verifier_finalizes_after_one_turn():
    web_search_mock = AsyncMock(return_value=[])
    async def mock_llm(prompt, tools):
        return _LLMDecision(is_final=True, content="Verified.", confidence=85.0)
    cfg = _make_cfg(mock_llm, web_search=web_search_mock)
    result = await run_verifier("q", cfg, _make_reasoned())
    assert result.iter_count == 1
    assert result.status == "ok"
    assert result.confidence == 85.0
    assert web_search_mock.await_count == 0


@pytest.mark.asyncio
async def test_verifier_omits_grounding_tool_when_grounding_none():
    captured_tools = []
    async def mock_llm(prompt, tools):
        captured_tools.append([t["name"] for t in tools])
        return _LLMDecision(is_final=True, content="Done.", confidence=50.0)
    cfg = _make_cfg(mock_llm, google_search_grounding=None)
    await run_verifier("q", cfg, _make_reasoned())
    assert captured_tools[0] == ["web_search", "web_extract"]


@pytest.mark.asyncio
async def test_verifier_clamps_confidence_to_0_100():
    async def mock_llm(prompt, tools):
        return _LLMDecision(is_final=True, content="Done.", confidence=150.0)
    cfg = _make_cfg(mock_llm)
    result = await run_verifier("q", cfg, _make_reasoned())
    assert result.confidence == 100.0
```

Test-file-local helpers (`_make_cfg`, `_make_reasoned`) are duplicated in both test files for self-containment so Wave 3 can absorb `test_verifier_cap.py` without cross-file fixtures.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace verifier.py body with bounded LLM agent loop + 2-or-3-tool dispatch (web_search + web_extract + conditional grounding)</name>
  <read_first>
    - lib/research/stages/verifier.py (current ar-1 stub — body to replace; signature preserved)
    - lib/research/stages/reasoner.py (ar-2 reference — _LLMDecision/_ToolCall pattern, parallel gather dispatch, outer try/except, cap-reached-is-ok)
    - lib/research/types.py (VerifierOutput shape — DO NOT modify; ReasonerOutput shape — read for the third arg)
    - lib/research/config.py (Wave 1 form — gives Verifier the cascade-wrapped cfg.web_search; cfg.web_extract may be None)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "ORCH-04: Verifier real LLM agent loop"
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-01-reasoner-agent-loop-PLAN.md § <interfaces>
  </read_first>
  <files>lib/research/stages/verifier.py</files>
  <behavior>
    Verifier body MUST satisfy these observable behaviors:
    - Returns a `VerifierOutput` instance with all 7 fields populated.
    - Calls `cfg.llm_complete` exactly once per iteration; loop terminates on final-answer decision OR `iter_count == cfg.max_iter_verifier`.
    - Tool list passed to `cfg.llm_complete` always contains `[web_search, web_extract]` (in that order); includes `google_search_grounding` as a third entry IFF `cfg.google_search_grounding is not None`.
    - On `web_search` tool call: invokes `cfg.web_search(query)`, expects `list[dict]`; for each dict appends `Source(kind="web", uri=<url>, title=<title>, snippet=<content>)` to `external_citations`.
    - On `web_extract` tool call: invokes `cfg.web_extract(url)`, expects `str`; appends `Source(kind="web", uri=<url-from-args>, snippet=<extract>)`.
    - On `google_search_grounding` tool call: invokes `cfg.google_search_grounding(query)`; appends `Source(kind="grounding", uri=<query>, snippet=<result>)`.
    - Multiple tool calls per iteration → parallel via `asyncio.gather()`.
    - Final-answer decision: `confidence = max(0.0, min(100.0, float(decision.confidence)))`. Parse fail → `confidence=0.0` + discrepancy line. Decision's `discrepancies` appended.
    - Cap reached → `status="ok"`, `iter_count == cap`, accumulated values preserved.
    - Any exception → `VerifierOutput(fact_check_summary_md="", confidence=0.0, external_citations=[], discrepancies=[], iter_count=<current>, status="failed", reason=str(e))` — empty lists, not partial. NEVER raises.
    - Prompt includes `reasoned.inferences_md` verbatim (or `"(empty)"`).
    - Prompt mentions grounding tool ONLY when `cfg.google_search_grounding is not None`.
  </behavior>
  <action>
    1. Open `lib/research/stages/verifier.py`. Replace docstring header to reflect ar-3 reality (real bounded LLM agent loop with web_search + web_extract + conditional grounding; outer try/except per Axis 3; cap-reached-is-ok semantics; cfg.web_search is cascade-wrapped from Wave 1).

    2. Replace imports:
       ```python
       from __future__ import annotations
       import asyncio
       from dataclasses import dataclass, field
       from ..types import ReasonerOutput, ResearchConfig, Source, VerifierOutput
       ```

    3. Define `_ToolCall` and `_LLMDecision` frozen dataclasses (module-private) per `<interfaces>` § "Internal protocol dataclasses".

    4. Define module-private `_build_prompt(query, reasoned, collected_citations, has_grounding) -> str` per `<interfaces>` § "_build_prompt helper".

    5. Define `async def run(query: str, cfg: ResearchConfig, reasoned: ReasonerOutput) -> VerifierOutput`. Inside, define tool wrappers as nested async closures capturing `cfg`. Conditionally define `_grounding_tool` only when `cfg.google_search_grounding is not None`.

    6. Build the `tool_list` (passed to `cfg.llm_complete` each turn): always `[web_search, web_extract]`; append `google_search_grounding` IFF the closure was defined.

    7. Define `_dispatch(tc)`: route to `_web_search_tool`/`_web_extract_tool`/`_grounding_tool` based on `tc.name`; raise `ValueError` on unknown name; raise `RuntimeError` if grounding tool called but not registered.

    8. Initialize loop state and implement loop body per `<interfaces>` § "Loop shape". Outer `try/except Exception as e:` wraps the entire `while`. Exception path returns empty-lists `VerifierOutput(status="failed", ...)` per Hard requirement #2.

    9. Final-answer parsing — clamp confidence with `try/except (TypeError, ValueError)`; parse failure → `confidence=0.0` + append parse-failure discrepancy. Then `discrepancies.extend(decision.discrepancies)`.

    10. Tool-call dispatch — parallel via `asyncio.gather(*..., return_exceptions=True)`; iterate results with `zip(decision.tool_calls, results)`; on `BaseException` raise to outer try; otherwise route by `tc.name` and append to `collected_citations`.

    11. Clean exit returns `VerifierOutput(status="ok", ..., iter_count=iter_count)`.

    12. CONTRACT-01 grep audit (verifier.py): 0 hits expected. CONTRACT-02 grep audit: 0 hits expected.

    13. Run `bash scripts/check_contract.sh` — must exit 0.

    14. Smoke import: `venv/Scripts/python.exe -c "from lib.research.stages.verifier import run, _LLMDecision, _ToolCall; import inspect; assert inspect.iscoroutinefunction(run); print('OK')"` — must succeed.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.stages.verifier import run, _LLMDecision, _ToolCall; import inspect; assert inspect.iscoroutinefunction(run); print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/stages/verifier.py` imports without error.
    - `run()` signature unchanged: `async def run(query: str, cfg: ResearchConfig, reasoned: ReasonerOutput) -> VerifierOutput`.
    - Module body contains `_LLMDecision` and `_ToolCall` private dataclasses.
    - Module body contains literal `cfg.web_search` (web_search wiring proof).
    - Module body contains literal `cfg.web_extract` (web_extract wiring proof).
    - Module body contains literal `cfg.google_search_grounding` (conditional grounding wiring proof).
    - Module body contains literal `reasoned.inferences_md` (verification subject proof).
    - Module body contains `asyncio.gather` (parallel dispatch — Axis 1 proof).
    - Module body contains `max(0.0, min(100.0, float(` (confidence clamp proof).
    - Module body contains zero `omnigraph_search.*` imports (CONTRACT-01).
    - Module body contains zero `~/.hermes` or `omonigraph-vault` literals (CONTRACT-02).
    - `bash scripts/check_contract.sh` exits 0.
  </acceptance_criteria>
  <done>verifier.py has the real agent-loop body; CONTRACT-01 + CONTRACT-02 clean; smoke import works.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write ORCH-04 mock test suite (≥8 tests covering finalize / tool dispatch / conditional grounding / prompt content / exception / clamp)</name>
  <read_first>
    - tests/unit/research/test_reasoner_agent_loop.py (ar-2-01 reference for _LLMDecision/_ToolCall mock pattern)
    - tests/unit/research/test_stages_stubs.py (mock cfg construction patterns; potential surgical updates required)
    - lib/research/stages/verifier.py (just-written — gives exact mock shapes)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "ORCH-04: Verifier real LLM agent loop"
    - pyproject.toml § `[tool.pytest.ini_options]` (confirm asyncio_mode = "auto")
  </read_first>
  <files>tests/unit/research/test_verifier_agent_loop.py</files>
  <behavior>
    Test file covers ≥8 tests, all using mocks (no live HTTP, no live LLM):

    1. `test_verifier_finalizes_after_one_turn` — final on turn 1; assert `iter_count == 1`, `status == "ok"`, `fact_check_summary_md`, `confidence`, no tool calls dispatched.
    2. `test_verifier_calls_web_search_tool` — turn 1 = web_search, turn 2 = final; assert `cfg.web_search.await_count >= 1`, ≥1 `Source(kind="web", uri=<mocked url>)` in citations.
    3. `test_verifier_calls_web_extract_tool` — turn 1 = web_extract, turn 2 = final; assert `cfg.web_extract.await_count >= 1`, extract URL recorded.
    4. `test_verifier_omits_grounding_tool_when_grounding_none` — `cfg.google_search_grounding=None` → tool list `== ["web_search", "web_extract"]` exactly; prompt does NOT mention `google_search_grounding`.
    5. `test_verifier_includes_grounding_tool_when_set` — `cfg.google_search_grounding=AsyncMock(...)` → tool list contains `"google_search_grounding"`.
    6. `test_verifier_includes_reasoned_inferences_md_in_prompt` — unique marker in `reasoned.inferences_md` appears in captured prompt.
    7. `test_verifier_returns_failed_on_llm_exception` — `cfg.llm_complete` raises → `status == "failed"`, `reason` contains exception text, `confidence == 0.0`, `external_citations == []`, `discrepancies == []`, no raise out.
    8. `test_verifier_clamps_confidence_to_0_100` — `confidence=150.0` → `result.confidence == 100.0`; (recommended negative case: `confidence=-5.0` → `result.confidence == 0.0`).

    Recommended 9th test:
    9. `test_verifier_records_parse_failure_as_discrepancy` — unparseable confidence → `result.confidence == 0.0` AND `any("failed to parse confidence" in d for d in result.discrepancies)` AND `result.status == "ok"` (parse fail doesn't flip status — Hard requirement #4).
  </behavior>
  <action>
    1. Create `tests/unit/research/test_verifier_agent_loop.py`. Imports:
       ```python
       import asyncio
       import dataclasses
       from pathlib import Path
       from unittest.mock import AsyncMock, MagicMock

       import pytest

       from lib.research.stages.verifier import run as run_verifier, _LLMDecision, _ToolCall
       from lib.research.types import (
           ReasonerOutput, ResearchConfig, Source, VerifierOutput,
       )
       ```

    2. Define test-local helpers:
       ```python
       def _make_cfg(llm_complete, **overrides) -> ResearchConfig:
           base = dict(
               rag_working_dir=Path("/tmp/_test_rag"),
               llm_complete=llm_complete,
               embedding_func=AsyncMock(),
               vision_cascade=MagicMock(),
               web_search=AsyncMock(return_value=[
                   {"title": "T", "url": "https://e.com/x", "content": "c"},
               ]),
               web_extract=AsyncMock(return_value="extracted body"),
               web_search_fallback=None,
               google_search_grounding=None,
           )
           base.update(overrides)
           return ResearchConfig(**base)

       def _make_reasoned(inferences: str = "Mock Reasoner inferences.") -> ReasonerOutput:
           return ReasonerOutput(
               inferences_md=inferences,
               additional_chunks=[],
               analyzed_images=[],
               iter_count=1,
               status="ok",
           )
       ```

    3. Implement Tests 1-8 (and optional 9). Each test independent; fresh mocks per test.

    4. For tool-list capture (Tests 4 + 5):
       ```python
       captured_tools = []
       async def mock_llm(prompt, tools):
           captured_tools.append([t["name"] for t in tools])
           return _LLMDecision(is_final=True, content="Done.", confidence=50.0)
       ```

    5. For prompt-content capture (Test 6):
       ```python
       captured_prompts = []
       async def mock_llm(prompt, tools):
           captured_prompts.append(prompt)
           return _LLMDecision(is_final=True, content="Done.", confidence=50.0)
       cfg = _make_cfg(mock_llm)
       reasoned = _make_reasoned(inferences="UNIQUE-INFERENCE-MARKER-12345")
       await run_verifier("q", cfg, reasoned)
       assert "UNIQUE-INFERENCE-MARKER-12345" in captured_prompts[0]
       ```

    6. For exception test (Test 7):
       ```python
       async def mock_llm_raises(prompt, tools):
           raise RuntimeError("LLM provider down")
       cfg = _make_cfg(mock_llm_raises)
       result = await run_verifier("q", cfg, _make_reasoned())
       assert result.status == "failed"
       assert "LLM provider down" in result.reason
       assert result.confidence == 0.0
       assert result.external_citations == []
       assert result.discrepancies == []
       ```
       (Hard requirement #2 — empty lists, not partial.)

    7. Run new file in isolation: `venv/Scripts/python.exe -m pytest tests/unit/research/test_verifier_agent_loop.py -v`. All ≥8 must pass.

    8. Run full suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total ≥97 (Wave 1 baseline) + ≥8 = ≥105.

    9. If ar-1 Verifier-stub tests in `test_stages_stubs.py` / `test_orchestrator.py` fail (they asserted `status='skipped'`, `reason mentions ar-3`, `iter_count==0`), apply SURGICAL updates:
       - `result.status == "skipped"` → `result.status in {"ok", "failed"}` (or, if the test should remain deterministic, inject a stub `cfg.llm_complete` returning `_LLMDecision(is_final=True, content="", confidence=0.0)` and assert `status="ok"`).
       - `result.reason mentions ar-3` → REMOVED.
       - `result.iter_count == 0` → `result.iter_count >= 0`.
       Document each edit in SUMMARY.md (≤10 line diffs total).
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_verifier_agent_loop.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_verifier_agent_loop.py` exists with ≥8 tests; all pass.
    - Test 1 specifically asserts `result.iter_count == 1` AND `result.status == "ok"`.
    - Test 4 specifically asserts `captured_tools[0] == ["web_search", "web_extract"]` (exact list & order).
    - Test 5 specifically asserts `"google_search_grounding" in captured_tools[0]`.
    - Test 6 specifically asserts `<unique marker> in captured_prompts[0]`.
    - Test 7 specifically asserts `status == "failed"` AND `confidence == 0.0` AND `external_citations == []` AND `discrepancies == []` (Hard requirement #2 — empty lists).
    - Test 8 specifically asserts `result.confidence == 100.0` for `confidence=150.0` LLM output.
    - Full `tests/unit/research/` suite has ≥105 tests passing.
    - Any `test_stages_stubs.py` / `test_orchestrator.py` Verifier-stub-assertion edits SURGICAL (≤10 line diffs total) and documented in SUMMARY.md.
  </acceptance_criteria>
  <done>≥8 ORCH-04 tests pass; full ar-1+ar-2+Wave-1 regression suite still green (≥105 total tests); ar-1 Verifier-stub assertions surgically updated.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Write TEST-04 Verifier-half cap test (1 test in standalone file — Wave 3 may absorb)</name>
  <read_first>
    - tests/unit/research/test_verifier_agent_loop.py (just-written — _LLMDecision/_ToolCall pattern; helpers can be duplicated for self-containment)
    - lib/research/stages/verifier.py (just-written — confirms cap behavior)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TEST-04: Cap enforcement (Wave 2 Verifier-half + Wave 3 Reasoner-half)"
  </read_first>
  <files>tests/unit/research/test_verifier_cap.py</files>
  <behavior>
    Test file covers exactly 1 test:

    - `test_verifier_cap_enforcement` — mock `cfg.llm_complete` always emits `web_search` tool call (never finalizes); assert `result.iter_count == cfg.max_iter_verifier` (default 3) AND `result.status == "ok"` (cap = budget, not error).

    File self-contained — no cross-file fixture imports — to make Wave 3 absorption trivial.
  </behavior>
  <action>
    1. Create `tests/unit/research/test_verifier_cap.py` with self-contained imports + duplicated `_make_cfg` / `_make_reasoned` helpers + the single test:
       ```python
       """TEST-04 Verifier-half cap enforcement test.

       Wave 3 may absorb this into test_caps_consolidated.py and remove this
       standalone file. Self-contained (no cross-file fixture imports) for
       trivial migration.
       """
       from pathlib import Path
       from unittest.mock import AsyncMock, MagicMock

       import pytest

       from lib.research.stages.verifier import run as run_verifier, _LLMDecision, _ToolCall
       from lib.research.types import (
           ReasonerOutput, ResearchConfig, VerifierOutput,
       )


       def _make_cfg(llm_complete, **overrides) -> ResearchConfig:
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


       def _make_reasoned() -> ReasonerOutput:
           return ReasonerOutput(
               inferences_md="Mock inferences.",
               additional_chunks=[],
               analyzed_images=[],
               iter_count=1,
               status="ok",
           )


       @pytest.mark.asyncio
       async def test_verifier_cap_enforcement():
           """LLM never emits final → loop terminates at iter_count == max_iter_verifier."""
           async def mock_llm_never_final(prompt, tools):
               return _LLMDecision(
                   is_final=False,
                   tool_calls=(_ToolCall(name="web_search", args={"query": "subq"}),),
               )

           cfg = _make_cfg(mock_llm_never_final)  # default max_iter_verifier=3
           reasoned = _make_reasoned()
           result = await run_verifier("test query", cfg, reasoned)

           assert result.iter_count == cfg.max_iter_verifier  # exactly the cap (=3)
           assert result.status == "ok"  # cap is a budget, not an error
           assert isinstance(result, VerifierOutput)
       ```

    2. Run new file in isolation: `venv/Scripts/python.exe -m pytest tests/unit/research/test_verifier_cap.py -v`. The 1 test must pass.

    3. Run full suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total ≥105 (Task 2 baseline) + 1 = ≥106.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_verifier_cap.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_verifier_cap.py` exists with exactly 1 test; test passes.
    - Test asserts `result.iter_count == cfg.max_iter_verifier` (NOT `<=` — exactly cap; loop never finalized).
    - Test asserts `result.status == "ok"` (cap = budget — Hard requirement #3).
    - File is self-contained (no fixture imports from `test_verifier_agent_loop.py`).
    - Full `tests/unit/research/` suite has ≥106 tests passing.
  </acceptance_criteria>
  <done>1 cap-enforcement test passes (TEST-04 Verifier-half); file self-contained for Wave 3 absorption.</done>
</task>

</tasks>

<verification>
- All three tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥106 tests passing.
- CONTRACT-01 grep re-check (Wave 2 adds zero `omnigraph_search.*` imports — Verifier has no KG access by design):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ --include='*.py' \
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
- Smoke import:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -c "
  from lib.research.stages.verifier import run, _LLMDecision, _ToolCall
  import inspect
  assert inspect.iscoroutinefunction(run)
  print('verifier.run async ok')
  "
  ```

Wave 2 does NOT exercise the upgraded Layer 2 smoke (cap=0 LLM-free CLI smoke is owned by Wave 3). Wave 2 verification is purely the Layer 1 pytest above.
</verification>

<success_criteria>
- ROADMAP § "Phase ar-3" Success Criterion #1 (Verifier real bounded loop with web_search + web_extract + conditional grounding, terminating at iter_count <= max_iter_verifier, returning iter_count + confidence): ✓ delivered by Tasks 1+2.
- ROADMAP Success Criterion #2 (cfg.web_search live Tavily): NOT this wave (Wave 1).
- ROADMAP Success Criterion #3 (Brave fallback exactly once): NOT this wave (Wave 1).
- ROADMAP Success Criterion #4 (Vertex Grounding auto-detect): NOT this wave (Wave 3). Wave 2 honors conditional registration but does not wire `from_env()`.
- ROADMAP Success Criterion #5 (cap tests for both loops): Verifier-half ✓ delivered by Task 3; Reasoner-half lands Wave 3.
- REQ ORCH-04 ✓ delivered by Task 1.
- REQ TEST-04 Verifier-half ✓ delivered by Task 3; Reasoner-half + consolidation lands Wave 3.
- CONTRACT-01 + CONTRACT-02 still clean.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-3-verifier-web-tools/ar-3-02-SUMMARY.md` documenting:
- Files modified + LOC count for each (verifier.py rewrite ~150 LOC; test_verifier_agent_loop.py ~250 LOC; test_verifier_cap.py ~50 LOC).
- Test count: total in each new file, total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (0 forbidden hits).
- Any `test_stages_stubs.py` / `test_orchestrator.py` Verifier-stub-assertion edits: list each test edited with line-count delta and one-line rationale.
- Any deviations from plan with one-line rationale — particularly: (a) whether the executor reused Reasoner's internal `_LLMDecision` / `_ToolCall` types or defined Verifier-local copies (planner default: Verifier-local); (b) whether the empty-lists-on-failure rule (Hard requirement #2) is preserved exactly — failed Verifier returns `external_citations=[]` and `discrepancies=[]`, NOT partial collected lists; (c) whether the executor inlined the tool list / wrappers vs introducing helpers.
- Smoke import check output.
- Live-key Layer 2b smoke is NOT executed in Wave 2 — defer to phase-close.
</output>

## Planner-flagged ambiguities

1. **`_LLMDecision` / `_ToolCall` shared vs duplicated.** Reasoner (ar-2-01) defined module-private copies; Verifier mirrors with subtly different fields (Verifier's `_LLMDecision` adds `confidence` + `discrepancies` on the final-answer branch). Planner default: duplicate (encapsulation per stage). An ar-4 refactor could lift to shared `lib/research/agent_loop.py`.

2. **Empty lists vs partial lists on Verifier failure.** Per CONTEXT Hard requirement #2, failed Verifier returns `external_citations=[]` and `discrepancies=[]` (NOT partial). Rationale: Synthesizer's Axis-8 degradation note shouldn't paste partial mid-loop citations as final. Task 1 step 8 honors this. If orchestrator disagrees, swap exception-path return; tests need corresponding update.

3. **`web_extract` when `cfg.web_extract is None`.** The planner spec has `_web_extract_tool` raise `RuntimeError("web_extract not configured")` when called against None; outer try/except surfaces as `status="failed"`. Alternative: omit `web_extract` from tool list when `cfg.web_extract is None` (mirror grounding pattern). Default keeps web_extract always-registered for prompt simplicity; revisit ar-4 if it bites.

4. **Confidence parse failure as discrepancy, not status flip.** Per CONTEXT Hard requirement #4, parse failure produces `confidence=0.0` + discrepancy line; status stays `"ok"` (loop completed; parse issue is observation, not stage failure). Honored.

5. **test_verifier_cap.py self-containment vs cross-file imports.** Default: self-contained (duplicates helpers ~30 LOC). Wave 3 absorbs into `test_caps_consolidated.py` without touching Task 2 file. Cross-file imports would shave LOC but couple test-file lifecycles. Default: self-contained.

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env (Wave 1+2 unit tests use mocks; Wave 3 Grounding test uses mocks; live-key Layer 2b smoke is the phase-close gate).
