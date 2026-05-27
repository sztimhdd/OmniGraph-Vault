---
phase: quick-260511-lmw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/llm_deepseek.py
  - tests/unit/test_llm_deepseek_lazy.py
  - CLAUDE.md
autonomous: true
requirements: [DSTO-01]
must_haves:
  truths:
    - "DeepSeek client is constructed with timeout=300 by default"
    - "OMNIGRAPH_DEEPSEEK_TIMEOUT env var overrides the default at construction time"
    - "Module imports cleanly with no DEEPSEEK_API_KEY set"
    - "All existing unit tests still pass"
  artifacts:
    - path: "lib/llm_deepseek.py"
      provides: "env-overridable _DEEPSEEK_TIMEOUT_S constant replacing hardcoded 120.0"
      contains: "OMNIGRAPH_DEEPSEEK_TIMEOUT"
    - path: "tests/unit/test_llm_deepseek_lazy.py"
      provides: "two new timeout-specific tests (default 300, env override to 60)"
    - path: "CLAUDE.md"
      provides: "OMNIGRAPH_DEEPSEEK_TIMEOUT row in Local dev env vars table"
  key_links:
    - from: "_DEEPSEEK_TIMEOUT_S"
      to: "AsyncOpenAI(timeout=_DEEPSEEK_TIMEOUT_S)"
      via: "_get_client()"
      pattern: "timeout=_DEEPSEEK_TIMEOUT_S"
---

<objective>
Make the DeepSeek client-side per-call timeout env-overridable and raise the
default from 120s to 300s.

Purpose: A single hung DeepSeek call can block for 800s+ before LightRAG's
outer per-task timeout fires. Giving operators a per-call kill switch
(`OMNIGRAPH_DEEPSEEK_TIMEOUT`) stops runaway calls fast without touching the
unrelated `LIGHTRAG_LLM_TIMEOUT` budget.

Output: 3 files changed (~20 LOC diff total); pytest tests/unit/ GREEN.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260511-lmw-add-client-side-timeout-to-deepseek-api-/260511-lmw-PLAN.md

<!-- Key interfaces the executor needs — no codebase exploration required. -->

From lib/llm_deepseek.py (current state, lines 68-97):
```python
# D-09.02 (TIMEOUT-02): 120s request timeout prevents single-chunk runaway.
_DEEPSEEK_TIMEOUT_S = 120.0

_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = _require_api_key()
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=_DEEPSEEK_BASE_URL,
            timeout=_DEEPSEEK_TIMEOUT_S,
        )
    return _client
```

From tests/unit/test_llm_deepseek_lazy.py (current — 4 tests, all pass):
- test_import_lib_without_deepseek_key_succeeds
- test_calling_deepseek_without_key_raises
- test_calling_deepseek_with_key_uses_env_key  ← patches AsyncOpenAI via patch.object(ld, "AsyncOpenAI")
- test_lib_init_does_not_export_deepseek_anymore

The `_purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])` + `ld._client = None`
pattern must be preserved in every test that exercises client construction so
the module-level constant is re-read from env.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Make _DEEPSEEK_TIMEOUT_S env-overridable + raise default to 300s</name>
  <files>lib/llm_deepseek.py, tests/unit/test_llm_deepseek_lazy.py</files>
  <behavior>
    - Test A: Client constructed with default timeout=300.0 when OMNIGRAPH_DEEPSEEK_TIMEOUT is unset
    - Test B: Client constructed with timeout=60.0 when OMNIGRAPH_DEEPSEEK_TIMEOUT=60 is set
    - Test C: Existing test_calling_deepseek_with_key_uses_env_key still passes (no signature breakage)
  </behavior>
  <action>
    RED phase — add two tests to tests/unit/test_llm_deepseek_lazy.py:

    test_default_timeout_is_300():
      - monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
      - monkeypatch.delenv("OMNIGRAPH_DEEPSEEK_TIMEOUT", raising=False)
      - _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])
      - import lib.llm_deepseek as ld; ld._client = None
      - captured_timeout = None; real_AsyncOpenAI = ld.AsyncOpenAI
      - def mock_ctor(**kwargs): nonlocal captured_timeout; captured_timeout = kwargs.get("timeout"); return MagicMock()
      - with patch.object(ld, "AsyncOpenAI", side_effect=mock_ctor): ld._get_client()
      - assert captured_timeout == 300.0

    test_env_override_changes_timeout():
      - monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
      - monkeypatch.setenv("OMNIGRAPH_DEEPSEEK_TIMEOUT", "60")
      - _purge_modules(...); import lib.llm_deepseek as ld; ld._client = None
      - same capture pattern; assert captured_timeout == 60.0

    Run pytest tests/unit/test_llm_deepseek_lazy.py — expect 2 new FAILURES (RED).

    GREEN phase — edit lib/llm_deepseek.py:
    Replace the hardcoded constant block (currently lines 68-73):

    BEFORE:
      # D-09.02 (TIMEOUT-02): 120s request timeout prevents single-chunk runaway.
      # Outer per-article budget (D-09.03) scales with chunk_count; this inner
      # timeout kills any ONE chat.completions.create call that exceeds 120s so the
      # outer budget has room to retry or fail cleanly. Bare float form — the
      # openai>=1.0 SDK accepts float as total request timeout.
      _DEEPSEEK_TIMEOUT_S = 120.0

    AFTER:
      # D-09.02 (TIMEOUT-02): per-call timeout prevents single-chunk runaway.
      # Raised to 300s default (was 120s); override via OMNIGRAPH_DEEPSEEK_TIMEOUT.
      # Outer per-article budget (D-09.03) scales with chunk_count; this inner
      # timeout kills any ONE chat.completions.create call that exceeds the limit
      # so the outer budget has room to retry or fail cleanly. Float form —
      # openai>=1.0 SDK accepts float as total request timeout.
      _DEEPSEEK_TIMEOUT_S: float = float(
          os.environ.get("OMNIGRAPH_DEEPSEEK_TIMEOUT", "300") or "300"
      )

    No other changes to llm_deepseek.py. The `timeout=_DEEPSEEK_TIMEOUT_S` in
    _get_client() already wires the constant correctly.

    Run pytest tests/unit/test_llm_deepseek_lazy.py — all 6 tests must pass (GREEN).

    NOTE: _DEEPSEEK_TIMEOUT_S is read at module import time (module-level expression),
    so the _purge_modules() + monkeypatch pattern in tests will correctly re-evaluate
    the env var. The lazy _get_client() pattern already in place handles the client
    construction side.
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault && .venv/Scripts/python -m pytest tests/unit/test_llm_deepseek_lazy.py -v 2>&1 | tee .scratch/dsto-$(date +%Y%m%dT%H%M%S).log && grep -E "PASSED|FAILED|ERROR" .scratch/dsto-*.log | tail -10</automated>
  </verify>
  <done>6 tests pass (4 existing + 2 new); grep shows timeout=300.0 line in lib/llm_deepseek.py; no other files modified</done>
</task>

<task type="auto">
  <name>Task 2: Document OMNIGRAPH_DEEPSEEK_TIMEOUT in CLAUDE.md and verify import</name>
  <files>CLAUDE.md</files>
  <action>
    In CLAUDE.md, find the "Local dev env vars" table (currently has 6 rows ending with
    OMNIGRAPH_PROCESSED_BACKOFF). Insert one new row AFTER the OMNIGRAPH_PROCESSED_BACKOFF row:

    | `OMNIGRAPH_DEEPSEEK_TIMEOUT` | No | `300` | Float seconds. DeepSeek client-side per-call timeout. Kills any single hung `chat.completions.create` call; distinct from `LIGHTRAG_LLM_TIMEOUT` (per-task outer budget). See `lib/llm_deepseek.py`. |

    Then run the import smoke check and capture output:

      .venv/Scripts/python -c "from lib.llm_deepseek import deepseek_model_complete; print('import OK')"

    Append the output line to the .scratch/dsto-*.log file created in Task 1.

    Finally commit both changed files:
      git add lib/llm_deepseek.py tests/unit/test_llm_deepseek_lazy.py CLAUDE.md
      git commit -m "fix(deepseek-260511-dsto): client-side per-call timeout 300s with env override -- fail-fast on hung DeepSeek calls instead of waiting for downstream LIGHTRAG_LLM_TIMEOUT"
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault && grep "OMNIGRAPH_DEEPSEEK_TIMEOUT" CLAUDE.md && .venv/Scripts/python -c "from lib.llm_deepseek import deepseek_model_complete; print('import OK')" && git log --oneline -1</automated>
  </verify>
  <done>CLAUDE.md table has OMNIGRAPH_DEEPSEEK_TIMEOUT row; import smoke prints "import OK"; git log shows the fix commit</done>
</task>

</tasks>

<verification>
Full suite smoke:
  cd /c/Users/huxxha/Desktop/OmniGraph-Vault && .venv/Scripts/python -m pytest tests/unit/ -q 2>&1 | tail -5

Expected: no new failures vs baseline (18 known Windows CI failures are pre-existing — ignore those; deepseek_lazy tests = 6 PASSED).

Grep proof (timeout wired):
  grep "OMNIGRAPH_DEEPSEEK_TIMEOUT\|_DEEPSEEK_TIMEOUT_S" lib/llm_deepseek.py
</verification>

<success_criteria>
- lib/llm_deepseek.py: `_DEEPSEEK_TIMEOUT_S` reads from `OMNIGRAPH_DEEPSEEK_TIMEOUT` env var, defaults to 300.0
- tests/unit/test_llm_deepseek_lazy.py: 6 tests pass (4 existing + 2 new timeout tests)
- CLAUDE.md: OMNIGRAPH_DEEPSEEK_TIMEOUT documented in Local dev env vars table
- .scratch/dsto-*.log: pytest GREEN lines + "import OK" line as proof artifacts
- git: single commit with the prescribed message
</success_criteria>

<output>
After completion, create `.planning/quick/260511-lmw-add-client-side-timeout-to-deepseek-api-/260511-lmw-SUMMARY.md`
</output>
