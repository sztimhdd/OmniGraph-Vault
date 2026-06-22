---
phase: quick-260527-swt
plan: 01
subsystem: kb-api / kg_synthesize singleton
tags: [v1.1, P5-stub, async-safety, singleton, race, lightrag]
acceptance_branch: A
requirements:
  - P5-SC3   # NOT closed; singleton race detected — escalated to /gsd:plan-phase v1.1.P5
key_files:
  created:
    - tests/integration/kb/test_async_safety.py   # 28 LoC (≤30); UNCOMMITTED on branch A
    - .scratch/v1.1-yolo-p5verify-20260528T001527Z.log   # full report; gitignored
    - .scratch/p5verify_serve.py                  # ephemeral .env.local-aware launcher; gitignored
    - .scratch/p5verify-uvicorn.log               # raw server log; gitignored
    - .scratch/p5verify-pytest-1.log              # raw pytest output; gitignored
  modified: []
decisions:
  - "Branch A — singleton state corruption observed; do NOT commit failing test on main; do NOT add asyncio.Lock fix in this quick (per halt-rule #4)"
  - "Singleton implementation files (kg_synthesize.py, kb/api.py, kb/services/synthesize.py, kb/api_routers/synthesize.py) UNTOUCHED — zero diff"
metrics:
  duration: ~25 min
  completed: 2026-05-28T00:15:27Z
---

# Quick 260527-swt: P5-stub SC#3 — singleton async-safety verification

## Branch: A (race / shared-state corruption observed)

The N=4 concurrent `/api/synthesize` test correctly caught problematic
behavior. Server-side log shows multiple concurrent POSTs each triggering
a fresh `LightRAG(...)` constructor (independent graph hydration of 2625
nodes / 3412 edges per request), proving the module-global `_rag_singleton`
in `kg_synthesize._get_or_init_rag()` is NOT being preserved across
concurrent BG-task invocations under N=4 traffic.

This is consistent with bug 2c (job 564f270d59e6, where frontend poll
reports `done@T=59s` but backend log fires `c1_after_aquery` at `T=92s`):
two concurrent aquery() calls running against independent LightRAG
instances, with one BG task overwriting the other's job-store slot.

## Acceptance branch decision flow

| Halt-rule from PLAN | Triggered? | Outcome |
| --- | --- | --- |
| #1 Test > 30 LoC | No (28 LoC) | Pass |
| #2 Singleton edits required | No (zero diff) | Pass |
| #3 Git op fails | No git ops attempted (branch A) | N/A |
| #4 Race / deadlock / corruption observed | **YES** | **HALT branch A** |
| #5 Both env channels unreachable | No (Channel 1 worked, server booted, /health 200) | Pass |
| #6 Pre-commit hook fails | No commit attempted | N/A |
| #7 Push rejected | No push attempted | N/A |

## What ran

1. **Task 1**: Authored `tests/integration/kb/test_async_safety.py` (28 LoC,
   ≤30 ceiling verified by the plan's automated LoC check). Single async
   test, real `httpx.AsyncClient` + `asyncio.gather`, no mocks, no
   TestClient. Markers AAAA/BBBB/CCCC/DDDD-MARKER-{1..4} on questions.

2. **Task 2 (Channel 1, local one-port deploy)**:
   - Storage hydrated: `.dev-runtime/databricks-app-local/lightrag_storage/graph_chunk_entity_relation.graphml` present.
   - Wrapped `.scratch/local_serve.py` with a tiny `.scratch/p5verify_serve.py`
     that loads `databricks-deploy/.env.local` BEFORE local_serve.py's
     `setdefault()` calls (so `.dev-runtime/databricks-app-local/...` paths
     win over `.dev-runtime/data/...` defaults).
   - Server booted; `/health` → 200 OK pre-test.
   - Ran `venv/Scripts/python.exe -m pytest tests/integration/kb/test_async_safety.py -v --tb=short -p no:cacheprovider`.
   - Test FAILED with `httpx.ReadTimeout` after 180.93s. Server log
     shows two distinct `LightRAG(...)` constructions and two 5-min
     Databricks SDK metadata probes for two consecutive POSTs — singleton
     cache is not surviving across concurrent requests.

3. **Task 3 (Branch A dispatch)**: STOP, no commit. Singleton files
   verified untouched via `git diff -- kg_synthesize.py kb/api.py
   kb/services/synthesize.py kb/api_routers/synthesize.py` → empty.

## Evidence — server-side log proves singleton race

Two consecutive `LightRAG(...)` constructions for two consecutive POSTs
(uvicorn log excerpt, condensed):

```
POST 1 (61309) → 202 Accepted
  -> WARNING: Failed to fetch host metadata ... Timed out after 0:05:00
  -> INFO: [] Loaded graph from ... 2625 nodes, 3412 edges    # <-- LightRAG #1
POST 2 (61310) → 202 Accepted
  -> WARNING: Failed to fetch host metadata ... Timed out after 0:05:00
  -> INFO: [] Loaded graph from ... 2625 nodes, 3412 edges    # <-- LightRAG #2
POST 3 (61307) → 202 Accepted (server still hung when test killed at T=180s)
```

`Loaded graph from ...` is emitted by
`venv/Lib/site-packages/lightrag/kg/networkx_impl.py:62` inside
`NetworkXStorage.__post_init__` — fires once per `LightRAG(...)`
constructor call. Two log lines = two graph instances loaded =
`_rag_singleton = rag` did not survive between the two BG tasks.

## Hypotheses for the next session (P5 plan-phase scope)

Either or both of:

1. **`asyncio.Lock` lazy-init race** in `kg_synthesize.py:87-89`:
   `if _rag_init_lock is None: _rag_init_lock = asyncio.Lock()` is
   theoretically atomic in a single asyncio loop (no `await` between
   check and assign), but the observed double-init suggests something
   in this path is interacting unexpectedly with FastAPI BG-task
   scheduling.

2. **Silent constructor failure inside `LightRAG(...)`**: the 5-min
   Databricks SDK metadata probe in `lib/llm_complete.get_llm_func()`
   (`auth_type='pat'` not being passed — see CLAUDE.md "30-second
   self-check") may cause a transient exception that escapes
   `async with _rag_init_lock:` BEFORE `_rag_singleton = rag` runs,
   leaving the cache as None and forcing each request to re-init.

P5 plan-phase should resolve both via the `app.state.lightrag` lifespan
pattern from P5-stub.md, which eliminates per-request init entirely AND
removes the lazy-lock pattern as a class of bug.

## Escalation prompt — operator MUST run this

```
/gsd:plan-phase v1.1.P5 --reason async-safety-race-detected \
  --evidence .scratch/v1.1-yolo-p5verify-20260528T001527Z.log \
  --bug-link 564f270d59e6
```

## Constraint-compliance checklist

- [x] Test file 28 LoC (≤30 hard ceiling)
- [x] No edits to `kb/api.py` / `kg_synthesize.py` / `kb/services/synthesize.py` / `kb/api_routers/synthesize.py` (verified zero `git diff`)
- [x] No `git add -A` (no commits at all on branch A)
- [x] No `--amend`, `reset --hard`, `push --force`
- [x] No literal secrets in test file or report log
- [x] "omonigraph-vault" misspelling preserved
- [x] All Python invocations via `venv/Scripts/python.exe`
- [x] Real running singleton (Channel 1 local at `localhost:8766`), NOT TestClient, NOT mocked
- [x] Report log contains all 7 required fields (env / storage / pytest exit / N=4 summary / branch / branch-A details / artifacts)
- [x] Singleton implementation files unchanged (verifiable: `git diff -- kg_synthesize.py kb/api.py kb/services/synthesize.py kb/api_routers/synthesize.py` empty)

## Self-Check: PASSED

- File `tests/integration/kb/test_async_safety.py` exists, 28 LoC.
- File `.scratch/v1.1-yolo-p5verify-20260528T001527Z.log` exists with branch field A.
- No commits made on branch A (per discipline).
- Singleton implementation files unchanged.
