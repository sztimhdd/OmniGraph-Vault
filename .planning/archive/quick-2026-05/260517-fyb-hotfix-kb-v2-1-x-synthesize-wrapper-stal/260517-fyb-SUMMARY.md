---
phase: 260517-fyb
plan: 01
subsystem: kb-api
tags: [hotfix, synthesize, stale-file-bug, p0]
dependency_graph:
  requires: []
  provides: [HOTFIX-260517-fyb-01, HOTFIX-260517-fyb-02]
  affects: [kb/services/synthesize.py, /api/synthesize]
tech_stack:
  added: []
  patterns: [capture-await-return-value, tdd-red-green]
key_files:
  modified:
    - kb/services/synthesize.py
    - tests/integration/kb/test_synthesize_wrapper.py
    - tests/integration/kb/test_synthesize_structured.py
    - tests/integration/kb/test_api_synthesize.py
    - tests/integration/kb/test_kb3_e2e.py
    - tests/integration/kb/test_long_form_synthesis.py
decisions:
  - "Additive return output in all 5 test stubs — back-compat file-write preserved but return enables new contract"
  - "Defensive isinstance(response, str) guard kept for synthesize_response returning None (3-attempt retry exhausted)"
metrics:
  duration: ~15min
  completed: 2026-05-17
  tasks: 2
  files: 6
---

# Phase 260517-fyb Plan 01: Synthesize Wrapper Stale-File Bug Fix Summary

P0 hotfix: kb_synthesize KG happy path was discarding `synthesize_response`'s return value and reading a stale `synthesis_output.md` file. Aliyun production (2026-05-17 22:13-22:22) confirmed 3 different POST /api/synthesize requests returned byte-identical 2399-char markdown from a 2026-05-08 CLI run rsync'd to the server.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add RED regression test | d944f47 | tests/integration/kb/test_synthesize_wrapper.py |
| 2 | Capture return value; delete stale-file reader | e319e9a | kb/services/synthesize.py + 4 test stub files |

## Commits

- `d944f47` — `test(260517-fyb): add RED regression test for synthesize_response return value contract`
- `e319e9a` — `fix(260517-fyb): capture synthesize_response return value; delete stale-file reader`

## Bug Evidence

Aliyun production 2026-05-17:

- Request A (Q: "AI Agent trends"): markdown = 2399 chars, starts with `# OmniGraph Synthesis...`
- Request B (Q: different question): markdown = same 2399 chars byte-identical
- Request C (Q: yet another question): markdown = same 2399 chars byte-identical
- Root cause: `synthesis_output.md` last written by a Hermes CLI run on 2026-05-08; all three API requests read that file instead of using the LLM response.

## The 4 Minimum Changes Applied

```
grep -n "_read_synthesis_output\|og_config" kb/services/synthesize.py   → 0 hits
grep -n "response = await asyncio.wait_for" kb/services/synthesize.py   → 1 hit (line 426)
grep -n "markdown = response if isinstance" kb/services/synthesize.py   → 1 hit (line 441)
grep -n "from pathlib import Path" kb/services/synthesize.py            → 0 hits (orphan removed)
```

All 4 changes verified:

1. `response = await asyncio.wait_for(synthesize_response(...), timeout=KB_SYNTHESIZE_TIMEOUT)` — captures return value
2. `markdown = response if isinstance(response, str) else ""` — uses return value directly
3. `_read_synthesis_output()` function deleted (12 lines)
4. `import config as og_config` deleted; `from pathlib import Path` deleted (orphan cleanup)

## TDD Verification

**RED (Task 1 — pre-fix):**

```
FAILED tests/integration/kb/test_synthesize_wrapper.py::test_kg_happy_path_uses_synthesize_response_return_value
AssertionError: markdown should be the synthesize_response return value, got: ''
assert '' == '# Sentinel Answer\n\nThe truth is at [a](/article/abc1234567).'
```

**GREEN (Task 2 — post-fix):**

```
tests/integration/kb/test_synthesize_wrapper.py::test_kg_happy_path_uses_synthesize_response_return_value PASSED
1 passed in 1.89s
```

## Full KB Test Suite Result

```
489 passed in 22.14s
```

All 489 tests pass (baseline 472 + 1 new regression test + 16 tests from other recently-added test files). Zero failures, zero errors.

## Test Stub Additive Fix

5 test helper stubs were updated to also `return output` (additive — file-write side effect preserved for back-compat, but now the wrapper consumes the return value):

| File | Helper | Change |
|------|--------|--------|
| test_synthesize_wrapper.py | `_patch_c1` | Added `return output` |
| test_long_form_synthesis.py | `_patch_c1_capture` | Added `return _output` |
| test_long_form_synthesis.py | inline `fake` in `test_kb_synthesize_accepts_mode_kwarg` | Added `return "# x"` |
| test_synthesize_structured.py | `_patch_c1_writes` | Added `return output_md` |
| test_api_synthesize.py | `_patch_c1_success` | Added `return output` |
| test_kb3_e2e.py | inline `fake_c1` in `test_e2e_synthesize_happy_path` | Added `return _output` |

## Local UAT (deferred to Aliyun)

Local KG path cannot run on the dev box: no GCP service-account credential locally → `KG_MODE_AVAILABLE=False` → `kb_synthesize` short-circuits to `fts5_fallback` before reaching the patched lines. The equivalent verification is the new regression test `test_kg_happy_path_uses_synthesize_response_return_value` which:

- Uses real FastAPI + real SQLite fixture_db
- Monkeypatches only the LLM boundary (C1)
- Explicitly asserts `synthesis_output.md` does NOT exist before or after the call
- Asserts `result["markdown"] == sentinel` (the function return value, not a file)

**Aliyun deploy + retest required post-merge:**

1. Deploy this commit to Aliyun: `databricks apps deploy kb-api --source-code-path /Workspace/Users/...`
2. `POST /api/synthesize` with question A → capture `markdown_len` + first 80 chars
3. `POST /api/synthesize` with question B (different) → capture `markdown_len` + first 80 chars
4. Assert: the two markdowns differ (no file-bleed)
5. `rm ~/.hermes/omonigraph-vault/synthesis_output.md` on Aliyun server
6. `POST /api/synthesize` again → assert response is non-empty and references new LLM output (proves no file dependency)
7. Cite curl output + LightRAG journal logs.

## Deviations from Plan

None — plan executed exactly as written. The additive `return output` stub fixes were anticipated in the Task 2 spec ("Audit existing tests that assert on result['markdown'] content via the file-write stub").

## Self-Check: PASSED

- FOUND: kb/services/synthesize.py
- FOUND: tests/integration/kb/test_synthesize_wrapper.py
- FOUND: commit d944f47 (RED test)
- FOUND: commit e319e9a (fix)
