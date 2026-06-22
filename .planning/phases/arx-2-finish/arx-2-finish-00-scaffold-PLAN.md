---
phase: arx-2-finish
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/research/test_synthesizer_llm.py
  - tests/unit/research/conftest.py
autonomous: false   # GAP-D confirm task is a read-only Aliyun SSH the orchestrator runs
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3]
must_haves:
  truths:
    - "3 RED synthesizer-LLM tests exist and fail (synthesizer not yet changed)"
    - "Existing synthesizer caption tests are guarded against get_llm_func() I/O via autouse conftest mock"
    - "Aliyun /api/research liveness is CONFIRMED (router live, no pull/restart needed)"
  artifacts:
    - path: "tests/unit/research/test_synthesizer_llm.py"
      provides: "3 behavioral tests pinning GAP-A real synthesis (all-chunk, degrade, not-stub-verbatim)"
      contains: "def test_synthesizer_uses_all_chunks_in_prompt"
      min_lines: 60
    - path: "tests/unit/research/conftest.py"
      provides: "autouse fixture patching synthesizer.get_llm_func so existing caption tests survive"
      contains: "autouse"
  key_links:
    - from: "tests/unit/research/conftest.py"
      to: "lib.research.stages.synthesizer.get_llm_func"
      via: "mock.patch autouse fixture"
      pattern: "lib\\.research\\.stages\\.synthesizer\\.get_llm_func"
---

<objective>
Wave 0 — test scaffolding + GAP-D liveness confirm. Lay the RED test floor for GAP-A
(real LLM synthesis) BEFORE Wave 1 touches synthesizer.py, and confirm the Aliyun
research router is live so Wave 3 doesn't waste an E2E cycle on a 404.

Purpose: The 3 new synthesizer tests are RED now (synthesizer still returns the
stub `chunks[0].snippet` verbatim) and become the GREEN gate for Wave 1. The
conftest autouse mock prevents the 10 existing `test_synthesizer_caption_embeds.py`
tests from breaking the moment Wave 1 makes synthesizer.py call `get_llm_func()`
directly (RESEARCH Pitfall 6). GAP-D is a 1-command CONFIRM, not a pull/restart —
the orchestrator's 2026-06-12 read-only probe already proved Aliyun HEAD `ba1121c`
has `38a7286` as ancestor and `POST /api/research` returns 200 + streams SSE.

Output: 2 new test files (RED) + a recorded GAP-D confirmation.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md
@.planning/phases/arx-2-finish/arx-2-finish-VALIDATION.md
@lib/research/stages/synthesizer.py
@tests/unit/research/test_synthesizer_caption_embeds.py

<interfaces>
<!-- Frozen types the tests construct. From lib/research/types.py (read before writing tests). -->
<!-- Source = Source(kind=str, uri=str, title=str|None, snippet=str|None) -->
<!-- ResearchState(query=str, timestamp_start=float); .retrieved set to RetrieverOutput -->
<!-- RetrieverOutput(chunks=list[Source], image_candidates=list[...], status="ok"|"failed", ...) -->
<!-- synthesizer.run(query: str, cfg: ResearchConfig, state: ResearchState) -> SynthesizerOutput -->
<!-- SynthesizerOutput(markdown: str, confidence: float, sources, embedded_images, note_lines: list[str]) -->
<!-- The exact constructor signatures MUST be read from lib/research/types.py and -->
<!-- the existing _make_minimal_cfg helper in test_synthesizer_caption_embeds.py:51-59 -->
<!-- reused verbatim (do NOT invent a new cfg factory). -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create conftest.py autouse get_llm_func mock + 3 RED synthesizer-LLM tests</name>
  <read_first>
    - tests/unit/research/test_synthesizer_caption_embeds.py (COPY its imports + `_make_minimal_cfg` helper at lines 51-59 verbatim — do NOT invent a new cfg factory; reuse the exact fixture pattern)
    - lib/research/types.py (confirm exact constructor signatures for Source / ResearchState / RetrieverOutput / SynthesizerOutput before constructing them)
    - lib/research/stages/synthesizer.py (the run() under test — currently returns chunks[0].snippet verbatim at line 108)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §Risk C (the 3 test bodies are written out verbatim there — lines 436-493)
  </read_first>
  <behavior>
    - Test 1 `test_synthesizer_uses_all_chunks_in_prompt`: given 3 chunks, the prompt passed to the mocked get_llm_func() result contains ALL 3 snippets (chunk-0, chunk-1, chunk-2), not just chunk-0.
    - Test 2 `test_synthesizer_degrades_gracefully_on_llm_failure`: when the mock LLM raises RuntimeError, run() does NOT raise; result.markdown is non-empty AND result.note_lines has an entry containing "failed" or "error".
    - Test 3 `test_synthesizer_real_prose_not_chunks0_verbatim`: mock LLM returns "# Real LLM Answer..."; result.markdown does NOT contain the chunk snippet "THE_STUB_SNIPPET" verbatim AND DOES contain "Real LLM Answer".
    - conftest autouse: an autouse function-scoped fixture patches `lib.research.stages.synthesizer.get_llm_func` to return `async def noop_llm(prompt, **kw): return "# Stub\n\nStub body."` so existing caption tests don't hit real provider I/O. Tests in test_synthesizer_llm.py override it with their own `mock.patch` inside the test body (the autouse mock is a baseline; per-test patches take precedence).
  </behavior>
  <action>
    Create `tests/unit/research/conftest.py`:
    ```python
    import pytest
    from unittest import mock

    @pytest.fixture(autouse=True)
    def _mock_get_llm_func():
        async def noop_llm(prompt, **kw):
            return "# Stub\n\nStub body."
        with mock.patch(
            "lib.research.stages.synthesizer.get_llm_func",
            return_value=noop_llm,
        ):
            yield
    ```
    NOTE: this patches the name AS IMPORTED INTO the synthesizer module. RESEARCH recommends
    Option (b): synthesizer does `from lib.llm_complete import get_llm_func` at function-body
    level (lazy). Patch target MUST be `lib.research.stages.synthesizer.get_llm_func` (the
    rebound name in the synthesizer module namespace), NOT `lib.llm_complete.get_llm_func`.
    If Wave 1 ends up doing a module-level lazy import inside run() such that the name is not
    bound at module scope, the per-test `mock.patch` in the 3 tests below (which target the
    same dotted path) still work because patch resolves the attribute at call time on the module
    object — verify this when Wave 1 lands and adjust the patch target string in ONE place if needed.

    Create `tests/unit/research/test_synthesizer_llm.py` with the 3 async tests EXACTLY as
    sketched in RESEARCH §Risk C lines 436-493. Reuse the import block and `_make_minimal_cfg`
    helper from test_synthesizer_caption_embeds.py:51-59 (copy it, or import it if it's a
    module-level helper). Mark each test `@pytest.mark.unit`. Each test uses
    `with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=<mock_llm>):`
    to install its own LLM, then `result = await run_synthesizer(...)` where `run_synthesizer`
    is the imported `run` (alias it `from lib.research.stages.synthesizer import run as run_synthesizer`
    if RESEARCH used that name, else call `run` directly — match RESEARCH).

    These tests are EXPECTED TO FAIL now (RED) because synthesizer.run() currently ignores
    get_llm_func and returns chunks[0].snippet verbatim. That is the point — they pin GAP-A
    and turn GREEN in Wave 1.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_llm.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/unit/research/conftest.py` exists and `grep -q "autouse" tests/unit/research/conftest.py` succeeds.
    - File `tests/unit/research/test_synthesizer_llm.py` exists; `grep -c "def test_synthesizer" tests/unit/research/test_synthesizer_llm.py` returns ≥ 3.
    - Running `venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_llm.py -v` shows the 3 tests COLLECTED and FAILING (RED — synthesizer not yet changed). A collection ERROR (import failure, wrong signature) is NOT acceptable — failures must be assertion failures, proving the tests run against real run().
    - `venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_caption_embeds.py -v` still passes 10/10 (the autouse conftest mock does NOT break them; if synthesizer.py is unchanged at this point they pass trivially because synthesizer doesn't yet call get_llm_func — confirm green either way).
  </acceptance_criteria>
  <done>3 RED GAP-A tests collected + failing on assertions; conftest autouse mock present; 10 caption tests green.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: GAP-D — confirm Aliyun research router is LIVE (orchestrator-run read-only SSH)</name>
  <read_first>
    - .planning/phases/arx-2-finish/arx-2-finish-CONTEXT.md §GAP D (the orchestrator already probed this 2026-06-12)
    - Memory aliyun_vitaclaw_ssh (SSH alias `aliyun-vitaclaw`)
  </read_first>
  <what-built>
    No code. This is a recorded confirmation of an ALREADY-SETTLED fact. The orchestrator's
    2026-06-12 read-only probe established: Aliyun git HEAD `ba1121c` includes `38a7286` as
    ancestor, and `POST /api/research` returns HTTP 200 + streams SSE (165 bytes in first 8s).
    GAP D is RESOLVED — Aliyun router is LIVE. NO pull. NO restart.
  </what-built>
  <how-to-verify>
    Orchestrator (NOT the executor agent — this is a read-only SSH the orchestrator owns per
    Principle #5) runs ONE confirmation command and records the result:
    ```bash
    ssh aliyun-vitaclaw "cd /var/www/omnigraph-source 2>/dev/null || cd ~/OmniGraph-Vault; \
      git merge-base --is-ancestor 38a7286 HEAD && echo ANCESTOR_OK || echo ANCESTOR_MISSING; \
      git rev-parse --short HEAD"
    ```
    (Adjust repo path to the actual Aliyun checkout; the orchestrator knows it from the 2026-06-12 probe.)
    Then confirm endpoint answers (the orchestrator already saw 200 + SSE):
    ```bash
    ssh aliyun-vitaclaw "curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:<kb-api-port>/api/research \
      -H 'Content-Type: application/json' -d '{\"query\":\"ping\",\"max_iterations\":1}' --max-time 8"
    ```
    Expected: `ANCESTOR_OK` + a 200 (or a clean SSE start). If — and only if — ANCESTOR_MISSING
    appears (contradicting the 2026-06-12 finding), THEN this task escalates to a pull + kb-api
    restart; otherwise record "GAP D CONFIRMED LIVE" and proceed.
  </how-to-verify>
  <acceptance_criteria>
    - Recorded evidence (in the wave SUMMARY) of `ANCESTOR_OK` (38a7286 ⊆ HEAD) on Aliyun.
    - Recorded evidence that `POST /api/research` does NOT 404 (200 or SSE-start observed).
    - If both hold: GAP D marked CONFIRMED-LIVE, no deploy action taken.
  </acceptance_criteria>
  <resume-signal>Type "GAP D confirmed live" (or report ANCESTOR_MISSING to trigger the pull+restart branch).</resume-signal>
</task>

</tasks>

<verification>
- `venv/Scripts/python.exe -m pytest tests/unit/research/ -v` collects test_synthesizer_llm.py (3 RED) + test_synthesizer_caption_embeds.py (10 GREEN) with no collection errors.
- GAP D recorded as CONFIRMED-LIVE in the wave SUMMARY.
</verification>

<success_criteria>
- 3 RED GAP-A behavioral tests exist and fail on assertions (not collection errors).
- conftest autouse mock in place; 10 caption tests still green.
- Aliyun research router confirmed live (no pull/restart performed).
</success_criteria>

<output>
After completion, create `.planning/phases/arx-2-finish/arx-2-finish-00-SUMMARY.md`
</output>
