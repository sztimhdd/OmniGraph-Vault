## RESEARCH COMPLETE

# v1.1.P5 RESEARCH — LR-singleton + async-safety

**Date:** 2026-05-28
**Source:** Direct codebase reads (no gsd-phase-researcher round-trip needed — orchestrator did the research inline)
**Halt triggers evaluated:** all PASS (proceed to plan)

---

## 1. FastAPI lifespan best-practice (FastAPI ≥0.100)

Canonical pattern (cited in P5-stub §6, verified against in-repo references):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: build heavy resource ONCE per worker process
    rag = LightRAG(working_dir=..., llm_model_func=..., embedding_func=...)
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    app.state.lightrag = rag
    try:
        yield
    finally:
        # shutdown: graceful close (LightRAG provides finalize_storages())
        if hasattr(rag, "finalize_storages"):
            await rag.finalize_storages()

app = FastAPI(lifespan=lifespan)
```

Replaces deprecated `@app.on_event("startup" | "shutdown")` (FastAPI 0.93+). `app.state.lightrag` is per-worker-process; this phase's hard assumption (`--workers 1`) means singleton-per-host. Multi-worker scope deferred to v1.2+.

## 2. LightRAG `aquery()` state mutation — CONFIRMED

Read `venv/Lib/site-packages/lightrag/lightrag.py`:

- `aquery()` line 2622 → wraps `aquery_llm()` line 2884
- `aquery_llm()` calls `kg_query / naive_query` with `hashing_kv=self.llm_response_cache` (lines 2920, 2930)
- After query: `await self._query_done()` (line 2974) → `self.llm_response_cache.index_done_callback()` (line 3045-3046)

**Conclusion:** `aquery()` MUTATES shared cache state. Concurrent calls without coordination CAN race on cache writes. **SC#3 (async-safety) is valid.**

→ Halt-trigger HT1 (aquery doesn't mutate) **NEGATIVE — proceed**.

## 3. Current `kb/api.py` state

Read `kb/api.py` (91 LoC):

- ✗ NO `lifespan` parameter on `FastAPI()` constructor
- ✗ NO `app.state.lightrag`
- ✓ Singleton currently lives in `kg_synthesize.py:78` as module-global `_rag_singleton`
- ✓ Lazy-init under `_rag_init_lock = asyncio.Lock()` (kg_synthesize.py:87-89)
- ✓ `omnigraph_search/query.py:41-66` has a DUPLICATE singleton block for the KG-search path (used by `/api/search?mode=kg`)

→ Halt-trigger HT2 (singleton already shipped via lifespan) **NEGATIVE — proceed**.

**Branch A observation (P5-verify quick 260527-swt):** server log showed TWO distinct `LightRAG(...)` constructions for two consecutive POST requests, each loading 2625 nodes / 3412 edges. Two hypotheses:

- **H1: Lazy-Lock TOCTOU race** — `kg_synthesize.py:87-89`

  ```python
  if _rag_init_lock is None:
      _rag_init_lock = asyncio.Lock()
  async with _rag_init_lock:
      ...
  ```

  Two concurrent first-callers both pass the `is None` check, each instantiates its own `asyncio.Lock()`, each acquires its own (different) lock instance, both proceed to construct LightRAG. Module-global `_rag_singleton` is overwritten by whichever finishes second; first wasted ~30s of work.

- **H2: Silent constructor failure on Databricks SDK metadata probe** — `LightRAG(...)` line 94 internally instantiates embedding/LLM clients, which may probe `WorkspaceClient()` without `auth_type='pat'`. On EDC corp network the probe hangs ~5 min; the lock-acquire branch never reaches `_rag_singleton = rag` (line 106), so the next request still finds `_rag_singleton is None` and starts over. **This is a local-only confound** (deployed Databricks App injects M2M credentials via platform; no metadata probe).

**Bug 2c on Databricks** (frontend `done@T=59s`, backend `c1_after_aquery@T=92s`): NOT explained by H2 (no metadata probe in deployed App). Likely H1 (lazy-lock race) OR an orthogonal wrapper-timeout-vs-LightRAG-worker-timeout interaction. P5 lifespan-pattern fixes H1 by construction (eager init at startup, no lazy lock). H2 is local-only and doesn't need a Databricks fix. The orthogonal timeout interaction is OUT OF SCOPE for P5 (track separately if it persists post-P5 deploy).

## 4. asyncio.Lock vs per-call clone-on-write — LoC delta

**Option A: asyncio.Lock around aquery()** (serialize all KG queries on this worker)

```python
async def kb_synthesize(question, lang, job_id, mode, lightrag, lightrag_lock):
    async with lightrag_lock:
        result = await synthesize_response(question, mode="hybrid", rag=lightrag)
```

- LoC delta: +1 lock attribute on `app.state` + 1 `async with` per call site (~3-4 sites)
- Throughput: serializes; with `--workers 1` and current 60-180s per-query latency this is acceptable (no parallel hot path today)
- Correctness: provably safe — concurrent cache writes impossible

**Option B: per-call clone-on-write snapshot** (parallel queries against immutable graph snapshot)

- Requires LightRAG-internal API to clone storages — does NOT exist in v1.4.16
- Would need wrapping each storage object with copy-on-write semantics — significant LoC
- Out of scope for ~80 LoC phase; defer to v1.2+ if throughput becomes a constraint

**Recommendation:** Option A (asyncio.Lock). Smaller LoC, provably safe, matches stub §"Deferred decisions" first option. Throughput claim from stub SC#2 ("steady-state latency unchanged or better") holds: cold-start is removed → first request faster; sequential queries unchanged (currently single-flight anyway).

## 5. Databricks `auth_type='pat'` threading

Read `databricks-deploy/_db_client.py`:

```python
def get_databricks_client(**kwargs):
    profile = os.getenv("DATABRICKS_CONFIG_PROFILE")
    if profile:
        return WorkspaceClient(profile=profile, auth_type="pat", **kwargs)
    return WorkspaceClient(**kwargs)  # deployed App: M2M auto-injected
```

Used by `databricks-deploy/lightrag_databricks_provider.py:69, 121` (factory bodies). Local-PAT path is properly guarded; deployed-App path is M2M-auto.

**Conclusion:** local 5-min probe is a local-only confound. Bug 2c on Databricks does NOT reduce to this. P5 must validate against Databricks-side behavior (deploy + N=4 concurrent test) — local cold-start <30s test is a parallel sufficient-condition check, not a Databricks-race reproducer.

---

## Halt-trigger summary

| Trigger | Outcome | Action |
| --- | --- | --- |
| HT1: aquery doesn't mutate state | NEGATIVE — confirmed mutates | proceed |
| HT2: kb/api.py already has lifespan + singleton | NEGATIVE — no lifespan today | proceed |
| HT3: Phase 1 LoC > 100 | (deferred to Phase 1 DECIDE) | TBD |
| HT4: Phase 1 LoC < 20 | (deferred to Phase 1 DECIDE) | TBD |

## Files in scope (verified read; line counts)

| File | LoC | Role |
| --- | --- | --- |
| `kb/api.py` | 91 | NEW lifespan; init `app.state.lightrag` + `app.state.lightrag_lock` |
| `kg_synthesize.py` | 293 | REMOVE module-global singleton (lines 71-107); ADD `rag` parameter to `synthesize_response()` |
| `kb/services/synthesize.py` | 566 | THREAD `rag` through `kb_synthesize()` wrapper |
| `kb/api_routers/synthesize.py` | 87 | ADD `request: Request` param; pass `request.app.state.lightrag` to BG-task |
| `kb/api_routers/search.py` | (unread) | KG-mode async path — same pattern as synthesize router |
| `omnigraph_search/query.py` | 122 | REMOVE duplicate `_rag_singleton` block (lines 41-66); ADD `rag` parameter |
| `tests/integration/kb/test_lifespan_singleton.py` | NEW | assert `app.state.lightrag` is same object across two requests |
| `tests/integration/kb/test_async_safety.py` | 28 (untracked from Branch A) | refactor to use lifespan; assert N=4 concurrent reqs OK |

## Validation Architecture

**Local (cold-start <30s):**

- `venv/Scripts/python.exe .scratch/local_serve.py` → `localhost:8766`
- First `curl POST /api/synthesize` after fresh start → measure wall-clock to first 200/202 response
- Pass: <30s on local NTFS

**Databricks (N=4 concurrent):**

- `make deploy` (Pass 0+1+2+3 — see Principle #9; only `kb/api.py` + `kg_synthesize.py` + `kb/services/` + `kb/api_routers/` touched, so Pass 0 SSG bake NOT required → sync-only Pass 1+2+3 acceptable IF no `kb/static/` or `kb/templates/` in commit)
- `httpx.AsyncClient` + `asyncio.gather()` 4 distinct queries against deployed `/api/synthesize`
- Server-side log inspection: confirm exactly ONE `LightRAG(...)` construction (no double-init)
- All 4 jobs reach `done` status with distinct payloads; no deadlock; no FS handle leak

---

*Phase v1.1.P5 — research complete; halt-triggers PASS; planner can proceed.*
