---
phase: quick-260517-lok
plan: 01
subsystem: kg_synthesize / lightrag
tags: [timeout, lightrag, embedding, cross-border, aliyun, tdd]
dependency_graph:
  requires: []
  provides: [default_embedding_timeout kwarg in kg_synthesize.LightRAG()]
  affects: [kg_synthesize.synthesize_response, kb/services/synthesize.py (calls kg_synthesize)]
tech_stack:
  added: []
  patterns: [env-overridable timeout helper, try/except defensive int parse, monkeypatch stub TDD]
key_files:
  created:
    - tests/unit/test_lightrag_embedding_timeout.py
  modified:
    - kg_synthesize.py
decisions:
  - Constructor kwarg over process-global EMBEDDING_TIMEOUT env var (more surgical; only affects synthesize-side rag instance)
  - _embedding_timeout_default() helper over inline int() to enable defensive fallback on non-numeric env value
  - 90s default (Func=90/Worker=180/Health=195) over 120s to preserve margin within KB_SYNTHESIZE_TIMEOUT=240s outer budget
metrics:
  duration: 4 minutes
  tasks_completed: 2
  tasks_pending: 1
  completed_date: "2026-05-17"
---

# Quick 260517-lok: LightRAG Embedding Worker Timeout Fix — Summary

## One-Liner

Added `default_embedding_timeout=90` kwarg to `LightRAG()` constructor in `kg_synthesize.py` to fix cross-border Aliyun→GCP-Singapore embedding worker timeout (Func: 30→90, Worker: 60→180, Health: 75→195).

## Problem

LightRAG default `default_embedding_timeout=30` yields Worker=60s / Health Check=75s (auto-derived as Func×2 / Func×2+15 in `utils.py:680-689`). Cross-border embedding via WireGuard (Aliyun ECS → GCP Singapore) takes 15-25s per Vertex call. A hybrid query batches 3 sequential Vertex calls inside one worker invocation (`lib/lightrag_embedding.py:207` `for text in texts`), meaning 3×25s=75s routinely exceeds the 60s Worker budget. LightRAG silently swallows the `WorkerTimeoutError` (`operate.py:3637-3655`) and proceeds with all embeddings=None → vdb retrieval skipped → empty markdown output.

## Fix

Single kwarg added to `LightRAG()` constructor in `kg_synthesize.synthesize_response`:

```python
default_embedding_timeout=_embedding_timeout_default(),
```

With helper:

```python
def _embedding_timeout_default() -> int:
    raw = os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 90
```

Yields: **Func=90s / Worker=180s / Health Check=195s** on Aliyun restart.

No vendor code modified. No monkey-patch. No env var required (constructor kwarg is surgical — only affects the synthesize-side rag instance, not any ingest-side LightRAG instances).

## Tasks Executed

| Task | Type | Commit | Status |
|------|------|--------|--------|
| T1: RED test — 4 unit tests failing (kwarg absent) | TDD RED | `647628b` | DONE |
| T2: GREEN edit — add helper + kwarg to constructor | TDD GREEN | `bb5605d` | DONE |
| T3: Aliyun retest (operator-side, post-merge) | checkpoint:human-action | — | PENDING |

## Local Test Evidence

### New unit tests — 4/4 PASS (post-T2 GREEN)

```
Command: venv/Scripts/python.exe -m pytest tests/unit/test_lightrag_embedding_timeout.py -v
Exit code: 0

tests/unit/test_lightrag_embedding_timeout.py::test_default_embedding_timeout_passed_to_lightrag PASSED
tests/unit/test_lightrag_embedding_timeout.py::test_lightrag_embedding_timeout_env_override PASSED
tests/unit/test_lightrag_embedding_timeout.py::test_lightrag_embedding_timeout_invalid_env_falls_back_to_default PASSED
tests/unit/test_lightrag_embedding_timeout.py::test_lightrag_other_kwargs_unchanged PASSED

4 passed in 11.04s
```

### Import smoke — env-override validation

```
# Unset (default):
venv/Scripts/python.exe -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"
→ 90

# LIGHTRAG_EMBEDDING_TIMEOUT=120 (env override):
venv/Scripts/python.exe -c "import os; os.environ['LIGHTRAG_EMBEDDING_TIMEOUT']='120'; import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"
→ 120

# LIGHTRAG_EMBEDDING_TIMEOUT=abc (invalid — defensive fallback):
venv/Scripts/python.exe -c "import os; os.environ['LIGHTRAG_EMBEDDING_TIMEOUT']='abc'; import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"
→ 90
```

### Full KB test suite

```
Command: venv/Scripts/python.exe -m pytest tests/integration/kb tests/unit/kb -q
Exit code: 1 (pre-existing failures, not caused by this change)

2 failed, 487 passed in 25.59s

Pre-existing failures (confirmed by stash test against baseline):
  - tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_reads_output_file
  - tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_success_sets_kg_confidence

These 2 failures exist on the baseline (pre-260517-lok HEAD) and are NOT
caused by this change. The plan's "489/489" assumption included these 2
as pre-existing; my change introduced 0 new failures.
```

## Diff Stat

```
kg_synthesize.py: +23 lines, -1 line
  - 1 new helper function _embedding_timeout_default() (16 lines with docstring)
  - 1 constructor call expanded from 1 line to 5 lines + kwarg (+5 net)
  - No other lines touched

tests/unit/test_lightrag_embedding_timeout.py: +140 lines (new file)
  - 4 unit tests covering: default, env override, invalid env fallback, regression guard
  - Stub-based (monkeypatch.setattr), no real LightRAG instantiation, no network calls
```

## Verification Checks

- `grep -c "default_embedding_timeout" kg_synthesize.py` → `1` (single call site)
- No `venv/Lib/site-packages/lightrag/` files modified
- No `kb/services/synthesize.py`, `lib/lightrag_embedding.py`, `kb/api_routers/`, `kb/templates/`, `kb/static/` files modified
- No new dependency added to `requirements.txt`

## Aliyun Retest (Task 3 — PENDING)

Task 3 is a `checkpoint:human-action` — awaiting operator execution. Operator must:

1. SCP `kg_synthesize.py` to `aliyun-vitaclaw:/root/OmniGraph-Vault/kg_synthesize.py`
2. `systemctl restart kb-api.service`
3. Verify journal shows: `Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)`
4. Smoke `POST /api/synthesize` with `mode=qa` → non-empty markdown, error=null
5. Smoke `POST /api/synthesize` with `mode=long_form` → markdown_len > 2000, sources >= 1
6. Confirm no `Worker timeout for task` warnings during smoke

Evidence to be added here after operator completes T3.

## Operational Notes

- **`LIGHTRAG_EMBEDDING_TIMEOUT` env var** is the tuning knob — set in systemd drop-in or `.env` file without redeploy.
  - `90` (default): Func=90 / Worker=180 / Health=195 — accommodates 3×25s cross-border calls
  - `120` (conservative): Func=120 / Worker=240 / Health=255 — NOTE: Worker=240 exactly equals `KB_SYNTHESIZE_TIMEOUT=240` outer budget, leaving zero margin. Do not use unless 90s proves insufficient.
- **No monkey-patch / no vendor edit**: consistent with `feedback_lightrag_is_core_asset_no_bypass.md` principle.
- **Forward note**: if Aliyun smoke shows Worker timeout still firing at 180s, the root cause is Vertex call latency exceeding design expectation (>60s/call). Two options:
  1. Bump `LIGHTRAG_EMBEDDING_TIMEOUT=120` (no redeploy, but squeezes outer budget margin)
  2. Parallelize Vertex calls inside `lib/lightrag_embedding.py:207` using `asyncio.gather` over texts (v1.0.y candidate per RESEARCH.md Q5)

## Known Stubs

None. This is a runtime kwarg fix, no stub data patterns.

## Self-Check: PASSED

- tests/unit/test_lightrag_embedding_timeout.py: FOUND
- Commit 647628b (RED test): FOUND
- Commit bb5605d (GREEN edit): FOUND
