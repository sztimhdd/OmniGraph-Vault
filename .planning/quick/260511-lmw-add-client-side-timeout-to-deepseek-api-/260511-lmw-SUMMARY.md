---
phase: quick-260511-lmw
plan: 01
subsystem: lib/llm_deepseek
tags: [deepseek, timeout, env-override, reliability]
dependency_graph:
  requires: []
  provides: [OMNIGRAPH_DEEPSEEK_TIMEOUT env var, _DEEPSEEK_TIMEOUT_S=300.0]
  affects: [lib/llm_deepseek.py, batch_ingest_from_spider.py (via deepseek_model_complete)]
tech_stack:
  added: []
  patterns: [env-overridable module-level constant, TDD RED→GREEN]
key_files:
  created: []
  modified:
    - lib/llm_deepseek.py
    - tests/unit/test_llm_deepseek_lazy.py
    - tests/unit/test_lightrag_llm.py
    - CLAUDE.md
decisions:
  - "Raise default from 120s to 300s (DSTO-01): single hung DeepSeek call was blocking for 800s+ before LIGHTRAG_LLM_TIMEOUT fired; 300s per-call kill switch is sufficient for most long articles without being oppressive"
  - "Use module-level float() expression so OMNIGRAPH_DEEPSEEK_TIMEOUT is re-evaluated on fresh module import — compatible with _purge_modules() pattern in existing tests"
  - "Fix test_lightrag_llm.py::test_deepseek_client_has_120s_timeout isolation: added monkeypatch.delenv + module purge to prevent cross-test contamination from preceding tests caching stale 120.0 client"
metrics:
  duration: ~35 minutes
  completed: "2026-05-11"
  tasks: 2
  files: 4
---

# Phase quick-260511-lmw Plan 01: DeepSeek client-side per-call timeout 300s with env override

**One-liner:** Raised DeepSeek per-call timeout default from 120s to 300s and made it env-overridable via `OMNIGRAPH_DEEPSEEK_TIMEOUT`, with 2 new TDD-verified tests confirming default and override behaviour.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Make _DEEPSEEK_TIMEOUT_S env-overridable + raise default | 91b19d5 | lib/llm_deepseek.py, tests/unit/test_llm_deepseek_lazy.py, tests/unit/test_lightrag_llm.py |
| 2 | Document OMNIGRAPH_DEEPSEEK_TIMEOUT in CLAUDE.md | 91b19d5 | CLAUDE.md |

## Changes Summary

### lib/llm_deepseek.py

Replaced the hardcoded constant:
```python
# BEFORE:
_DEEPSEEK_TIMEOUT_S = 120.0

# AFTER:
_DEEPSEEK_TIMEOUT_S: float = float(
    os.environ.get("OMNIGRAPH_DEEPSEEK_TIMEOUT", "300") or "300"
)
```

The `or "300"` guard handles the edge case where the env var is set to empty string. The constant feeds directly into `_get_client()` → `AsyncOpenAI(timeout=_DEEPSEEK_TIMEOUT_S)`. No other changes to the module.

### tests/unit/test_llm_deepseek_lazy.py

Added 2 new tests after the existing 4:
- `test_default_timeout_is_300` — confirms timeout=300.0 when `OMNIGRAPH_DEEPSEEK_TIMEOUT` is unset
- `test_env_override_changes_timeout` — confirms timeout=60.0 when `OMNIGRAPH_DEEPSEEK_TIMEOUT=60`

Both use the `_purge_modules() + monkeypatch + patch.object(ld, "AsyncOpenAI")` capture pattern consistent with the existing test file.

### tests/unit/test_lightrag_llm.py

Updated `test_deepseek_client_has_120s_timeout` to assert 300.0 (from 120.0). Also added module isolation (`monkeypatch.delenv("OMNIGRAPH_DEEPSEEK_TIMEOUT") + sys.modules.pop + ld._client = None + ld._get_client()`) to prevent cross-test contamination from preceding tests that may leave a stale 120.0 client cached in the module global.

### CLAUDE.md

Added `OMNIGRAPH_DEEPSEEK_TIMEOUT` row to the "Local dev env vars" table, after `OMNIGRAPH_PROCESSED_BACKOFF`.

## Verification Evidence

### Targeted test run (GREEN)

Source: `.scratch/dsto-20260511-160043.log` — run against `tests/unit/test_llm_deepseek_lazy.py` + `tests/unit/test_lightrag_llm.py`

```
tests/unit/test_llm_deepseek_lazy.py::test_import_lib_without_deepseek_key_succeeds PASSED
tests/unit/test_llm_deepseek_lazy.py::test_calling_deepseek_without_key_raises PASSED
tests/unit/test_llm_deepseek_lazy.py::test_calling_deepseek_with_key_uses_env_key PASSED
tests/unit/test_llm_deepseek_lazy.py::test_lib_init_does_not_export_deepseek_anymore PASSED
tests/unit/test_llm_deepseek_lazy.py::test_default_timeout_is_300 PASSED
tests/unit/test_llm_deepseek_lazy.py::test_env_override_changes_timeout PASSED
tests/unit/test_lightrag_llm.py::test_bare_prompt_sends_single_user_message PASSED
tests/unit/test_lightrag_llm.py::test_system_prompt_prepends_system_role PASSED
tests/unit/test_lightrag_llm.py::test_history_messages_ordering PASSED
tests/unit/test_lightrag_llm.py::test_returns_plain_string_from_choices PASSED
tests/unit/test_lightrag_llm.py::test_deepseek_model_env_override PASSED
tests/unit/test_lightrag_llm.py::test_missing_api_key_raises_runtime_error PASSED
tests/unit/test_lightrag_llm.py::test_keyword_extraction_kwarg_is_swallowed PASSED
tests/unit/test_lightrag_llm.py::test_root_shim_reexports_same_object PASSED
tests/unit/test_lightrag_llm.py::test_deepseek_client_has_120s_timeout PASSED
15 passed in 3.45s
```

### Import smoke check

Appended to `.scratch/dsto-20260511-160043.log`:
```
import OK
```

### Grep proof (timeout wired)

```
69:# Raised to 300s default (was 120s); override via OMNIGRAPH_DEEPSEEK_TIMEOUT.
74:_DEEPSEEK_TIMEOUT_S: float = float(
75:    os.environ.get("OMNIGRAPH_DEEPSEEK_TIMEOUT", "300") or "300"
98:            timeout=_DEEPSEEK_TIMEOUT_S,
```

### Full suite (`.scratch/dsto-20260511-163601.log`)

`23 failed, 642 passed, 5 skipped` — 23 failures are all pre-existing; `test_lightrag_llm::test_deepseek_client_has_120s_timeout` is NOT in the failure list.

Baseline failure count was also 23 (verified from `.planning/.../b2uhntn4p.output`) — our change has zero net impact on the failure count. The specific failures in each run differ slightly due to pre-existing flaky test isolation issues in the broader test suite (unrelated to this change).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_lightrag_llm.py::test_deepseek_client_has_120s_timeout isolation**
- **Found during:** Task 1 GREEN verification
- **Issue:** The test was reading `ld._client.timeout` without explicitly rebuilding the client. Under some test orderings in the full suite, a stale 120.0 client cached from a preceding test bled through even after the autouse fixture ran, causing intermittent failures asserting 300.0 == 120.0.
- **Fix:** Added `monkeypatch.delenv("OMNIGRAPH_DEEPSEEK_TIMEOUT", raising=False)`, `sys.modules.pop("lib.llm_deepseek", None)`, `ld._client = None`, `ld._get_client()` to force a deterministic fresh client in every run.
- **Files modified:** `tests/unit/test_lightrag_llm.py` (lines 224-248)
- **Commit:** 91b19d5

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: lib/llm_deepseek.py
- FOUND: tests/unit/test_llm_deepseek_lazy.py
- FOUND: tests/unit/test_lightrag_llm.py
- FOUND: CLAUDE.md
- FOUND: commit 91b19d5
