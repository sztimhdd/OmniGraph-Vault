---
phase: ar-3-verifier-web-tools
plan: 03
wave: 3
status: complete
last_updated: "2026-05-23"
requirements_delivered:
  - TOOL-03    # Vertex Gemini Google Search Grounding pass-through
  - CONFIG-03  # Wave-3 half: from_env() two-signal Vertex auto-detect
  - TEST-04    # Reasoner-half + consolidated cap tests (absorbs Wave 2's standalone)
tests:
  baseline: 107       # Wave 2 close
  added: 7            # 5 autodetect + 2 consolidated caps
  removed: 1          # tests/unit/research/test_verifier_cap.py (absorbed)
  total: 113
---

# ar-3-03 — Wave 3 SUMMARY (Vertex Grounding + autodetect + consolidated cap tests)

Wave 3 closes phase ar-3 (Verifier + Tavily/Brave/Grounding). Three deliverables landed: (1) `vertex_gemini_grounding` async pass-through callable, (2) `from_env()` two-signal Vertex auto-detect, (3) `test_caps_consolidated.py` absorbs Wave 2's standalone `test_verifier_cap.py`.

Per principal #2 (Surgical Changes) and the plan-checker MUST rulings, no out-of-scope code was touched.

## Files modified / created / deleted

| Path | Change | Lines |
| ---- | ------ | ----- |
| `lib/research/tools/web_search.py` | MOD — added `vertex_gemini_grounding` (async, lazy `google.genai` import) + `__all__` extension | +25 |
| `lib/research/tools/__init__.py` | MOD — re-exported `vertex_gemini_grounding` | +2 |
| `lib/research/config.py` | MOD — replaced `google_search_grounding = None` placeholder with two-signal auto-detect block + import addition | +14 |
| `tests/unit/research/test_grounding_autodetect.py` | NEW — 5 autodetect tests (env, module-path, deepseek-no-detect, CLI override, signature) | +135 |
| `tests/unit/research/test_caps_consolidated.py` | NEW — 2 cap tests (Reasoner cap=5 + consolidated Verifier cap=3) | +103 |
| `tests/unit/research/test_verifier_cap.py` | **DELETED** via `git rm` — absorbed into consolidated | −73 |

Wave 1's existing Tavily/Brave/cascade code is byte-for-byte unchanged. The `from_env()` body outside the auto-detect block is byte-for-byte unchanged.

## Branch decision: Branch B (inline `google.genai`)

`lib/vertex_gemini_complete.py` (read at Task 1 read_first) does NOT expose a `complete_with_grounding` helper — it only has `vertex_gemini_model_complete` (the chat completion entry point). Per plan ambiguity #2, the executor chooses Branch A (reuse helper) when feasible, else Branch B (inline).

**Branch B chosen** — the inline `google.genai` grounding-tool API call is ≤10 LOC and surgical. Adding a helper to `lib/vertex_gemini_complete.py` would expand its scope (currently chat-completion only) and was explicitly NOT requested. The inline form imports lazily inside the function body, preserving the lazy-import contract (no module-level `google.genai` import in `lib/research/tools/`).

The implementation matches the planner-supplied Branch B template verbatim (PLAN § Task 1 Branch B) — `genai.Client(vertexai=True, location="global")` + `Tool(google_search=GoogleSearch())` + `model="gemini-2.5-flash"` + `contents=query` + `response.text or ""`. Full prompt-engineering and model-selection are deferred to ar-4 final-tuning per the plan's TOOL-03 deferment.

## Auto-detect coverage matrix

| Scenario | env `OMNIGRAPH_LLM_PROVIDER` | bound `llm_complete.__module__` | `cfg.google_search_grounding` |
| -------- | ---------------------------- | -------------------------------- | ----------------------------- |
| Test 1 — env signal | `vertex_gemini` | (any — stub) | `vertex_gemini_grounding` |
| Test 2 — module-path signal | unset | `lib.vertex_gemini_complete` | `vertex_gemini_grounding` |
| Test 3 — neither signal | `deepseek` | `lib.deepseek_complete` | `None` |
| Test 4 — CLI override | `vertex_gemini` (auto-detected) | (any) | `None` after `dataclasses.replace(cfg, google_search_grounding=None)` |
| Test 5 — signature contract | n/a | n/a | callable shape inspected: async, single positional `query` |

All 5 tests apply the monkeypatch.delenv discipline (drop `OMNIGRAPH_LLM_PROVIDER` + both web-key envs at top, then set scenario-specific vars). The two-signal OR is checked: setting only env (Test 1) suffices, setting only module-path (Test 2) suffices, neither (Test 3) yields None.

## Test count delta

```
Wave 2 close baseline:         107
+ test_grounding_autodetect:    +5
+ test_caps_consolidated:       +2
- test_verifier_cap (deleted):  -1
                                ---
Wave 3 close total:            113
```

`venv/Scripts/python.exe -m pytest tests/unit/research/ -q` → `113 passed in 58.09s`. Zero regressions across ar-1 + ar-2 + Wave 1 + Wave 2 + Wave 3 surfaces.

## CONTRACT-01 + CONTRACT-02 evidence

`bash scripts/check_contract.sh` exits 0 (last run after Task 4):

```
CONTRACT-01 ok
CONTRACT-02 ok
```

- CONTRACT-01: zero `omnigraph_search.*` imports added by Wave 3 (Grounding tool has no KG side; `vertex_gemini_grounding` is web-only).
- CONTRACT-02: zero `~/.hermes` / `omonigraph-vault` literals added by Wave 3. The canonical `omonigraph` typo in `config.py` (Wave 1 baseline, allow-listed by `check_contract.sh`) is unchanged.

## `test_verifier_cap.py` deletion confirmation

```
$ git rm tests/unit/research/test_verifier_cap.py
rm 'tests/unit/research/test_verifier_cap.py'
$ ls tests/unit/research/test_verifier_cap.py
ls: cannot access 'tests/unit/research/test_verifier_cap.py': No such file or directory
```

Wave 2's standalone is gone. `test_caps_consolidated.py::test_verifier_cap_enforcement_consolidated` is now the single source of truth for the Verifier cap test. The body is identical to Wave 2's (mock LLM that always returns a `web_search` tool call, default cap=3, asserts `iter_count == 3` AND `status == "ok"`). The Reasoner-half is the new addition (mock kg_search via `monkeypatch.setattr` to avoid LightRAG, default cap=5, asserts `iter_count == 5` AND `status == "ok"`).

## Layer 2a cap=0 LLM-free CLI smoke

**Command run** (Python harness; CLI flag equivalent is `python -m omnigraph.research --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding "..."`):

```bash
OMNIGRAPH_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=dummy \
PYTHONIOENCODING=utf-8 \
venv/Scripts/python.exe -c "
import asyncio, dataclasses
from lib.research.config import from_env
from lib.research.orchestrator import research
cfg = from_env()
cfg = dataclasses.replace(cfg, max_iter_reasoner=0, max_iter_verifier=0, google_search_grounding=None)
result = asyncio.run(research('什么是 Hermes Harness 深度解析', cfg))
# state assertions
assert result.state.reasoned.iter_count == 0 and result.state.reasoned.status == 'ok'
assert result.state.verified.iter_count == 0 and result.state.verified.status == 'ok'
assert result.state.synthesized is not None
assert len(result.markdown) > 0
"
```

**Exit code:** `0`. **Stderr:** clean (only INFO-level LightRAG load logging — no tracebacks).

**Captured artifacts:**
- `.scratch/ar-3-03-l2a-smoke-260523.stdout` — full smoke output
- `.scratch/ar-3-03-l2a-smoke-260523.stderr` — clean stderr (INFO-only)

**Stdout excerpt:**

```
=== Layer 2a cap=0 LLM-free smoke ===
exit_code: 0 (all state assertions pass)
markdown length: 155
reasoned iter_count: 0
reasoned status: ok
verified iter_count: 0
verified status: ok
retrieved status: failed
web_baseline status: ok
synthesized populated: True
--- markdown (first 500 chars) ---
# 关于「什么是 Hermes Harness 深度解析」的研究答复
## 知识图谱检索结果

(no chunks retrieved)


---

> ❌ Retriever failed: Embedding dim mismatch, expected: 3072, but loaded: 768
```

**State assertions all pass.** Pipeline runs end-to-end. CLI plumbing verified.

### Deviation: markdown length 155 chars (plan-spec floor: 200) — pre-existing local-KG dim drift

The 155-char markdown is the synthesizer's degraded output when the Retriever stage emits `status="failed"`. The Retriever fails with `Embedding dim mismatch, expected: 3072, but loaded: 768` — a **pre-existing local-KG state issue** (the user's local LightRAG storage at `~/.hermes/omonigraph-vault/lightrag_storage/` is on the older 768-dim embedding model, while the current Retriever expects 3072-dim).

Per plan Task 5 step 4 stop-condition guidance: *"WebBaseline / Retriever stage fails... If they fail with cap=0, that's a regression in ar-1's stage stubs — out of Wave 3 scope; flag in SUMMARY.md."*

Plan Task 5 acceptance criterion `len(markdown) >= 200` is a heuristic anchored to the synthesizer's degraded-but-substantive output. With Retriever in `failed` state, the synthesizer correctly emits the minimal terminal-stage markdown (Chinese title + retriever degradation note), which is 155 chars in dense Chinese characters. **All other Wave 3-scope acceptance criteria are met:**
- ✓ exit code 0
- ✓ `result.state.reasoned.iter_count == 0`, `status == "ok"`
- ✓ `result.state.verified.iter_count == 0`, `status == "ok"`
- ✓ `result.state.synthesized is not None`
- ✓ no tracebacks in stderr
- ✓ pipeline plumbing intact end-to-end
- ✗ chars heuristic (155 < 200, due to pre-existing local-KG dim drift — not a Wave 3 regression)

**This is NOT a stop condition.** Stop conditions require empty output OR non-zero exit OR traceback in stderr. The smoke produced valid markdown with all state assertions met; the chars heuristic was missed by 45 chars due to a pre-existing fixture-state issue out of Wave 3 scope. The local-KG dim mismatch should be tracked as a v1.0.y operator-side reset (re-ingest at 3072-dim) — it does NOT block Wave 3 close.

### Layer 2b live-key smoke

NOT executed in Wave 3 — defer to phase-close. Per the plan's `<success_criteria>`: "phase-close orchestrator runs Layer 2b after Wave 3 lands."

## Test_web_tools.py surgical update audit

Plan Task 3 step 9 guarded against this scenario: "Wave 1's tests may now produce non-None `cfg.google_search_grounding` IF the test environment has `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` leaking in."

Audit result: Wave 1's three `from_env` integration tests at `test_web_tools.py:174,194,219` already include `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)` (added by Wave 1 Task 2 with foresight). **No surgical update was needed.** The tests still pass against Wave 3's auto-detect block:

- `test_from_env_no_keys_uses_skipped_stub` — env unset, stub `llm_complete` (AsyncMock has `__module__ == "unittest.mock"`, NOT vertex) → both signals false → `google_search_grounding is None` (test does not assert this field, but doesn't fail)
- `test_from_env_tavily_only_uses_tavily_no_fallback` — same reasoning
- `test_from_env_both_keys_wraps_with_cascade` — same reasoning

Confirmed 113/113 green.

## Smoke imports (verification block)

```python
from lib.research.tools.web_search import vertex_gemini_grounding, tavily_search, brave_search, make_web_search_with_fallback
from lib.research.tools import vertex_gemini_grounding as vg2
from lib.research.config import from_env
from lib.research.stages.verifier import run as run_v, _LLMDecision as VLD, _ToolCall as VTC
from lib.research.stages.reasoner import run as run_r, _LLMDecision as RLD, _ToolCall as RTC
import inspect
assert inspect.iscoroutinefunction(vertex_gemini_grounding)
assert vg2 is vertex_gemini_grounding
assert inspect.iscoroutinefunction(run_v)
assert inspect.iscoroutinefunction(run_r)
sig = inspect.signature(vertex_gemini_grounding)
params = list(sig.parameters.values())
assert len(params) == 1 and params[0].name == 'query'
```

→ all imports OK. `vertex_gemini_grounding` is async with single positional `query` arg (no api_key kwarg). Re-exported identity-preserved at `lib.research.tools` package level.

## Hard rules audit (vs plan CONTEXT § "Hard rules")

| Hard rule | Status |
| --------- | ------ |
| 1. Auto-detect uses BOTH signals OR-joined | ✓ `_provider_env == "vertex_gemini" or _llm_module == "lib.vertex_gemini_complete"` |
| 2. `vertex_gemini_grounding` MUST be async | ✓ `async def vertex_gemini_grounding(query: str) -> str` |
| 3. `--no-grounding` CLI is final-word | ✓ `dataclasses.replace(cfg, google_search_grounding=None)` overrides; Test 4 verifies precedence |
| 4. Branch decision documented | ✓ Branch B (inline `google.genai`) — see § "Branch decision" |
| 5. `omnigraph.research` package path resolves | ✓ verified at read_first: `omnigraph.research.__file__` → `lib/research/__init__.py` |
| 6. CONTRACT-01: zero `omnigraph_search` imports in Wave 3 changes | ✓ `bash scripts/check_contract.sh` → CONTRACT-01 ok |
| 7. CONTRACT-02: zero `~/.hermes` / `omonigraph-vault` paths in Wave 3 changes | ✓ CONTRACT-02 ok |
| 8. `omonigraph` typo preserved | ✓ untouched in `config.py:42` |
| 9. No new env vars beyond `OMNIGRAPH_LLM_PROVIDER` | ✓ no env-var additions; reused existing |
| 10. TEST-04 consolidation: delete `test_verifier_cap.py` after consolidated covers both | ✓ `git rm` confirmed; consolidated covers both halves |

## Deviations summary

1. **L2a markdown length (155 chars vs 200 floor):** pre-existing local-KG embedding dim mismatch (3072 expected, 768 loaded) causes Retriever to emit `status="failed"`, which propagates to a minimal-but-valid synthesizer markdown. All Wave 3-scope state assertions pass; chars heuristic missed by 45 chars. Out of Wave 3 scope per plan Task 5 step 4. Recommend tracking as v1.0.y operator-side KG re-ingest at 3072-dim.

2. **Branch B chosen over Branch A:** `lib/vertex_gemini_complete.py` does not expose `complete_with_grounding`. Branch B (inline) is surgical (≤10 LOC), preserves lazy-import contract, and avoids expanding `lib/vertex_gemini_complete.py` scope. Plan-allowed via ambiguity #2.

No other deviations. All other plan tasks executed verbatim.

## Phase-close handoff to orchestrator

Wave 3 closes phase ar-3 deliverables. After this commit, the orchestrator can:

1. Run the Layer 2b **live-key** smoke against Hermes (with `TAVILY_API_KEY` + `BRAVE_SEARCH_API_KEY` + Vertex creds in `~/.hermes/.env`) — that is the phase-close gate.
2. Mark ar-3 complete in `STATE-Agentic-RAG-v1.md` and `ROADMAP-Agentic-RAG-v1.md` with the verbatim per-criterion checklist.
3. (Optional, recommended) operator-side reset of `~/.hermes/omonigraph-vault/lightrag_storage/` to restore 3072-dim embedding consistency for clean local L2a cap=0 smoke output ≥200 chars.

ar-3 (Verifier + Tavily/Brave/Grounding) is complete. Next phase: ar-4 (final tuning + telemetry + streaming peer body).
