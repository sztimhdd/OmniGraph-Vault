---
phase: v1.1-roadmap-P5
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/api.py
  - kg_synthesize.py
  - kb/services/synthesize.py
  - kb/api_routers/synthesize.py
  - kb/api_routers/search.py
  - omnigraph_search/query.py
  - tests/integration/kb/test_lifespan_singleton.py
  - tests/integration/kb/test_async_safety.py
autonomous: false  # final task = checkpoint:human-verify (Local UAT per Principle #6)
requirements:
  - SC#1  # cold-start <30s
  - SC#2  # steady-state latency unchanged or better
  - SC#3  # async-safety N=4 concurrent
  - SC#4  # lifespan shutdown finalize_storages
  - SC#5  # Local UAT cited in P5-VERIFICATION.md
must_haves:
  truths:
    - "kb-api process constructs LightRAG exactly ONCE at startup (one log line `lightrag_singleton_init_start` per process boot)"
    - "Two consecutive POST /api/synthesize requests share the same `app.state.lightrag` object (id() equal)"
    - "First /api/synthesize 200/202 happy-path response after cold-start lands sub-30s on local NTFS"
    - "Four concurrent POST /api/synthesize calls each return distinct correct markdown carrying their own MARKER token (no crosstalk, no deadlock, no shared-state corruption)"
    - "uvicorn SIGTERM fires `await app.state.lightrag.finalize_storages()` (visible in shutdown log)"
    - "`/gsd:execute-phase` evidence cites local_serve.py cold-start wall-clock + Databricks N=4 deploy log inspection in P5-VERIFICATION.md"
  artifacts:
    - path: "kb/api.py"
      provides: "lifespan context manager + app.state.lightrag + app.state.lightrag_lock"
      contains: "@asynccontextmanager"
    - path: "kg_synthesize.py"
      provides: "synthesize_response(query_text, mode, rag, lightrag_lock) — rag + lock params injected; lock wraps inner aquery; module-global singleton REMOVED"
      contains: "async def synthesize_response(query_text"
    - path: "tests/integration/kb/test_lifespan_singleton.py"
      provides: "two-request id() assertion against running app.state.lightrag"
    - path: "tests/integration/kb/test_async_safety.py"
      provides: "N=4 concurrent /api/synthesize with MARKER crosstalk check"
  key_links:
    - from: "kb/api.py"
      to: "kg_synthesize.py:synthesize_response"
      via: "request.app.state.lightrag + lightrag_lock passed through kb_synthesize → synthesize_response(rag=..., lightrag_lock=...)"
      pattern: "request\\.app\\.state\\.lightrag"
    - from: "kb/api_routers/synthesize.py"
      to: "kb/services/synthesize.py:kb_synthesize"
      via: "request: Request param + background.add_task(kb_synthesize, ..., request.app.state.lightrag, request.app.state.lightrag_lock)"
      pattern: "request\\.app\\.state\\.lightrag_lock"
    - from: "kg_synthesize.py:synthesize_response"
      to: "rag.aquery"
      via: "inner `async with lightrag_lock:` wrapping `await asyncio.wait_for(rag.aquery(...))` at kg_synthesize.py:243-246"
      pattern: "async with lightrag_lock"
---

# v1.1.P5 — LR-singleton + async-safety

## SC Validity Check

| SC | Status | Reason |
| --- | --- | --- |
| SC#1 — Cold-start first /api/synthesize sub-30s on local NTFS | **VALID** | RESEARCH §3 confirms current code rebuilds LightRAG per request; lifespan eager init removes that path entirely. Sub-30s wall-clock on the *first* request post-startup is the right gate (cold-start cost paid once at uvicorn boot, not at request time). |
| SC#2 — Steady-state per-query latency unchanged-or-better | **VALID** | Pre-P5 second-request already hit the lazy singleton on hot path; post-P5 second-request hits the same in-memory LightRAG. Net change: zero on hot-path retrieval. asyncio.Lock around inner aquery() **serializes** queries — but with --workers 1 and current 60-180s per-query latency there is no parallel hot-path today, so p50/p95 should be flat. |
| SC#3 — N=4 concurrent /api/synthesize correct + no corruption | **VALID** | RESEARCH §2 confirmed `aquery()` mutates `self.llm_response_cache` (lightrag.py:3045-3046). Without coordination, concurrent calls race. Test exists (`tests/integration/kb/test_async_safety.py`, 39 LoC, branch A discovered race in quick 260527-swt). asyncio.Lock (Option A) is the locked decision per RESEARCH §4. |
| SC#4 — Lifespan SIGTERM finalize_storages | **VALID** | Direct contract of lifespan pattern (RESEARCH §1). `finally:` block in `@asynccontextmanager` is the canonical place; LightRAG provides `finalize_storages()` (RESEARCH §1 confirmed via in-repo lightrag library). |
| SC#5 — Local UAT cited in P5-VERIFICATION.md | **VALID** | Mandated by Principle #6 (CLAUDE.md). Cold-start wall-clock + concurrent-query screenshot are both load-bearing evidence the GSD-verifier can grep. |

All five SCs **VALID** — no revisions, no drops.

## LoC Estimate

Single number with breakdown by file (production source + tests; comments/docstrings counted with their statement). Gross changed lines = added + removed.

| File | LoC delta | Nature |
| --- | --- | --- |
| `kb/api.py` | **+18** | Add `from contextlib import asynccontextmanager`; add `from kb.services.lightrag_factory import build_lightrag` (or inline build — see T1); add `@asynccontextmanager async def lifespan(app)` block (~14 lines) wiring `app.state.lightrag` + `app.state.lightrag_lock = asyncio.Lock()`; add `lifespan=lifespan` kwarg on existing `FastAPI(...)` constructor (line 39) |
| `kg_synthesize.py` | **-30 +9 = net -21** | DELETE lines 71-107 (`_rag_singleton` + `_rag_init_lock` + `_get_or_init_rag()`) — 36 lines removed; KEEP `_embedding_timeout_default()` (still useful for the lifespan factory); MODIFY `synthesize_response()` signature line 185: add `rag: LightRAG \| None = None, lightrag_lock: asyncio.Lock \| None = None` parameters; ADD CLI-fallback build branch when `rag is None` (~5 lines); WRAP the inner `await asyncio.wait_for(rag.aquery(...))` block at lines 243-246 in conditional `async with lightrag_lock:` (~4 lines added incl. else-branch) |
| `kb/services/synthesize.py` | **+4** | `kb_synthesize()` signature: add `rag: LightRAG, lightrag_lock: asyncio.Lock` params (2 lines, with type imports); modify line 521-524 `await asyncio.wait_for(synthesize_response(...))` to pass `rag=rag, lightrag_lock=lightrag_lock` (1 line); add `from lightrag.lightrag import LightRAG` + `import asyncio` if not present (1 line). NOTE: NO `async with` wrapper at this layer — lock acquisition lives inside `synthesize_response()` per Option A |
| `kb/api_routers/synthesize.py` | **+3** | Add `request: Request` param to `synthesize_endpoint` line 51 (1 line); modify `background.add_task(...)` line 62 to pass `request.app.state.lightrag, request.app.state.lightrag_lock` (1 line + extension); add `from fastapi import Request` (1 line) |
| `kb/api_routers/search.py` | **+6** | `_kg_worker` (line 56) signature: add `rag, lightrag_lock` params (1 line); call `synthesize_response(q, mode='hybrid', rag=rag, lightrag_lock=lightrag_lock)` — NO router-layer `async with` (1 line); same treatment for `_kg_local_worker` (line 91) — `rag, lightrag_lock` params (1 line) + pass through to `synthesize_response(...)` inside the existing `asyncio.wait_for(...)` (1 line); both routes pass `request.app.state.lightrag, request.app.state.lightrag_lock` to `background.add_task(...)` (lines 220, 246; 2 lines) |
| `omnigraph_search/query.py` | **-29 +4 = net -25** | DELETE lines 39-67 (29 lines: duplicate `_rag_singleton` + `_rag_init_lock` + `_get_or_init_rag()`); MODIFY `search()` signature line 70: add `rag: LightRAG \| None = None` param; if `rag is None` (CLI path: `python -m omnigraph_search.query ...`) build a one-shot LightRAG inline via the same factory used by lifespan (4 lines). NOTE: `search()` does NOT acquire the lock — its only kb-api caller path is via `synthesize_response`, which holds the lock internally |
| `tests/integration/kb/test_lifespan_singleton.py` (NEW) | **+25** | pytest.mark.integration; httpx.AsyncClient against http://localhost:8766; two GET /health calls + one POST /api/synthesize sequence; assert log line count == 1 via reading server stderr (or skip log check and rely on app.state direct access via TestClient lifespan); assert id(app.state.lightrag) stable across requests |
| `tests/integration/kb/test_async_safety.py` | **+0** | Already exists at 39 LoC (branch A — created during quick 260527-swt). No edits required — it polls `/api/synthesize` directly; works against the lifespan singleton transparently. Re-run as verification, not as a new write. |
| **TOTAL** | **+89 added / −66 removed = +23 net; gross changed = 89** | **Within [20, 100] gate** |

Gross-changed-lines = 89. Within ceiling 100. Net delta = +23. No HALT trigger.

## Async-Safety Strategy

**Locked decision: `asyncio.Lock` on `app.state.lightrag_lock` (Option A from RESEARCH §4).**

### Where the lock is acquired (Option A — single inner site)

The lock is acquired INSIDE `synthesize_response()` itself in `kg_synthesize.py`, wrapping ONLY the inner `await asyncio.wait_for(rag.aquery(...))` block at lines 243-246. Routers and the `kb_synthesize` service wrapper DO NOT acquire the lock — they thread `lightrag_lock` through as a parameter and let `synthesize_response()` own the critical section.

Rationale:
- The actual mutating op is `rag.aquery()` (RESEARCH §2 confirmed `self.llm_response_cache` write at lightrag.py:3045-3046). Wrapping the single call site that reaches `aquery()` is sufficient and minimal.
- The outer `asyncio.wait_for(...)` at `kb/services/synthesize.py:521-524` and `kb/api_routers/search.py:122-125` is UNCHANGED — its timeout still bounds the full call jointly. The lock now lives strictly INSIDE that outer wait_for, so `wait_for` can still cancel a stuck lock-acquire if the holder hangs.
- All three consumer paths (`/api/synthesize`, `/api/search?mode=kg`, `/api/search/kg`) reach `aquery()` only through `synthesize_response()`, so a single inner lock site covers the entire concurrency surface.
- CLI path (`python kg_synthesize.py "<query>"`) passes `lightrag_lock=None`; the wrapper degrades to plain `await asyncio.wait_for(rag.aquery(...))` — no lock needed (single-process single-call).

The lock is **NOT** acquired in `omnigraph_search/query.py:search()` because that function is only called from the CLI (`python -m omnigraph_search.query`) which is single-process single-call — no concurrency surface to protect. When called from inside kb-api router code, the router code reaches LightRAG via `synthesize_response` and the lock is already enforced inside.

### Why this is sufficient

RESEARCH §2 confirmed `aquery()` mutates `self.llm_response_cache` (post-query callback writes index_done at lines 3045-3046 of `lightrag/lightrag.py`). Serializing all `aquery()` invocations on a per-process lock makes concurrent cache writes impossible by construction. With `--workers 1` (hard assumption), there is exactly one lock per host, covering the entire concurrency surface.

RESEARCH §4 LoC analysis showed Option B (per-call clone-on-write) requires LightRAG-internal clone API that does not exist in v1.4.16; out-of-scope for this phase.

Throughput impact: zero on hot path. Current per-query latency is 60-180s and there is no parallel hot path today (Databricks Apps single-worker; Aliyun single-worker). Future parallelization (multi-worker, or per-call clone) is **v1.2+ scope** — explicitly excluded by P5-stub Hard Assumption.

### Scope of the lock — INSIDE wait_for, around aquery() only

**The lock wraps ONLY the inner `await asyncio.wait_for(rag.aquery(...))` block at kg_synthesize.py:243-246.** It does NOT wrap:
- The outer `wait_for(synthesize_response(...))` at `kb/services/synthesize.py:521-524`
- The outer `wait_for(synthesize_response(...))` at `kb/api_routers/search.py:122-125`
- The router-layer `_kg_worker` / `_kg_local_worker` body
- `_resolve_sources_from_markdown`, canonical-map loading, history append, or job_store updates

Reasoning:
- `aquery()` is the only call that mutates LightRAG shared state. Surrounding logic is read-only against article DB / job_store, which has its own lock semantics.
- Wrapping the lock OUTSIDE `wait_for` (at the router layer) would let a hung `aquery()` block all other requests for the full timeout (60-240s). Under N=4 concurrent load that pushes the 4th request to ~4×timeout ≈ 720s and contradicts SC#2.
- Wrapping the lock INSIDE `wait_for` (and inside `synthesize_response()`) keeps the timeout enforceable: if a holder hangs past its inner timeout (`KB_LIGHTRAG_INNER_TIMEOUT`), `asyncio.wait_for` cancels the coroutine, the `async with` exits, and the next waiter proceeds.

Concrete pattern (Option A — single site, inside `synthesize_response()`):

```python
# kg_synthesize.py (replacement around current lines 243-246, inside synthesize_response)
# `lightrag_lock` is a parameter on synthesize_response; None on the CLI path.
if lightrag_lock is not None:
    async with lightrag_lock:
        response = await asyncio.wait_for(
            rag.aquery(custom_prompt, param=param),
            timeout=KB_LIGHTRAG_INNER_TIMEOUT,
        )
else:
    response = await asyncio.wait_for(
        rag.aquery(custom_prompt, param=param),
        timeout=KB_LIGHTRAG_INNER_TIMEOUT,
    )
```

Routers and the service wrapper retain their existing outer `asyncio.wait_for(synthesize_response(...))` UNCHANGED — they merely thread `rag` and `lightrag_lock` through as parameters.

## Validation Plan

### Track 1 — Local cold-start <30s test (SC#1)

```powershell
# clean process — kill any existing kb-api on 8766 first
Get-Process | Where-Object {$_.MainWindowTitle -match "uvicorn"} | Stop-Process -Force

# fresh cold start
$env:DATABRICKS_CONFIG_PROFILE = "dev"
$start = Get-Date
.\venv\Scripts\python.exe .scratch\local_serve.py *> .uvicorn-p5.log &
# wait until /health responds
do { Start-Sleep -Milliseconds 200; $h = try { Invoke-RestMethod http://localhost:8766/health -ErrorAction Stop } catch { $null } } while ($h -eq $null)
$boot_ms = ((Get-Date) - $start).TotalMilliseconds
"BOOT_TO_HEALTH_MS=$boot_ms"

# first /api/synthesize call — measures the request path itself
$req_start = Get-Date
$r = Invoke-RestMethod -Method Post -Uri http://localhost:8766/api/synthesize `
  -ContentType "application/json" `
  -Body '{"question":"What is OmniGraph-Vault?","lang":"en"}'
$jid = $r.job_id
do { Start-Sleep -Milliseconds 500; $s = Invoke-RestMethod "http://localhost:8766/api/synthesize/$jid" } while ($s.status -eq "running")
$req_ms = ((Get-Date) - $req_start).TotalMilliseconds
"FIRST_REQ_WALL_MS=$req_ms"   # PASS criterion: < 30000
```

**PASS:** `FIRST_REQ_WALL_MS < 30000`. **Server-log check:** `Select-String "lightrag_singleton_init_start" .uvicorn-p5.log` returns exactly 1 hit (NOT 0, NOT 2). The 1-hit assertion proves lifespan init ran exactly once at boot, not at first request.

### Track 2 — Databricks N=4 concurrent test (SC#3)

**Pre-deploy file-touch check** (Principle #9 gate):

```powershell
git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'
# expected: empty — P5 touches NO kb/static/ or kb/templates/ files.
```

If empty → **sync-only deploy is permissible**:

```powershell
databricks sync --watch . /Workspace/Users/hhu@edc.ca/kb-api-app
# pass: confirm "Initial Sync Complete" in stdout
databricks apps deploy kb-api-app --source-code-path /Workspace/Users/hhu@edc.ca/kb-api-app
# wait for SUCCEEDED status
```

If non-empty → **HALT and re-plan** (Principle #9 violated; P5 should not have touched these dirs).

**N=4 concurrent test against deployed URL** (uses the existing `tests/integration/kb/test_async_safety.py`):

```powershell
$env:KB_BASE_URL = "https://kb-api-app-xxxx.cloud.databricks.com"
.\venv\Scripts\python.exe -m pytest tests/integration/kb/test_async_safety.py::test_singleton_async_safety_n4 -v
```

**PASS criteria** (already encoded in the test file):
- All 4 jobs reach `done` (line 34)
- 4 distinct markdown payloads — no 2 results identical (line 35)
- Each result's markdown contains its own `MARKER` token — no cross-talk (line 36-37)

**Server-side log inspection** (proves singleton, not just SC#3):

```powershell
databricks apps logs kb-api-app | Select-String "lightrag_singleton_init_start" | Measure-Object
# expected Count: 1  (one init across the entire process lifetime)
```

### Track 3 — Lifespan shutdown (SC#4)

```powershell
# launch local_serve.py in foreground (not backgrounded)
.\venv\Scripts\python.exe .scratch\local_serve.py
# wait for "Application startup complete"
# Ctrl+C to send SIGTERM
# verify shutdown log line:
#   INFO:kg_synthesize:lightrag_singleton_finalize_done
```

**PASS:** `lightrag_singleton_finalize_done` (or equivalent log emitted from the lifespan `finally:` block) appears in stderr after Ctrl+C.

### Track 4 — Steady-state latency baseline (SC#2)

Pre-P5 baseline (run on `main` BEFORE merging P5):

```powershell
$ts = @()
foreach ($i in 1..10) {
  $r = Invoke-RestMethod -Method Post http://localhost:8766/api/synthesize `
    -ContentType "application/json" -Body '{"question":"What is FastAPI?","lang":"en"}'
  $jid = $r.job_id
  $t0 = Get-Date
  do { Start-Sleep -Milliseconds 500; $s = Invoke-RestMethod "http://localhost:8766/api/synthesize/$jid" } while ($s.status -eq "running")
  $ts += ((Get-Date) - $t0).TotalSeconds
}
$ts | Measure-Object -Average -Maximum -Minimum
# record p50 = sorted[5], p95 = sorted[9]
```

Post-P5 same command → record p50 + p95.

**PASS:** `p50_post <= p50_pre * 1.10` AND `p95_post <= p95_pre * 1.20` (10% / 20% regression tolerance for measurement noise on a 60-180s base).

## Rollback Plan

P5 is a **single-feature change** spanning 6 production files. Rollback is `git revert` of the per-task commits with **NO env-var feature flag** — feature-flagging would require keeping the deleted `_rag_singleton` block, doubling code paths in production. Per Principle #2 (Simplicity First), we accept commit-revert as the rollback channel.

### Revert procedure

If post-deploy regression is observed on Databricks:

1. **Identify offending commits** — P5 ships as a 6-task atomic-commit sequence (T1..T6). Each task is its own commit with a `feat(v1.1.P5)` / `refactor(v1.1.P5)` / `test(v1.1.P5)` / `docs(v1.1.P5)` prefix, so the commits are easy to locate by `git log --grep`. No git tags are required (Principle #2 — tags add ceremony without execution value).
2. **Locate the P5 commit SHAs:**
   ```powershell
   # list every P5 commit on main with full SHA + subject
   git log --grep="v1.1.P5" --format='%H %s'
   ```
3. **Full revert** (default; if any uncertainty):
   ```powershell
   # Revert commits in REVERSE order (newest first — T6, T5, ..., T1) so the
   # working tree stays consistent at each step. Revert each commit individually:
   git revert <T6-sha>
   git revert <T5-sha>
   git revert <T4-sha>
   git revert <T3-sha>
   git revert <T2-sha>
   git revert <T1-sha>
   git push origin main
   databricks sync --watch . /Workspace/Users/hhu@edc.ca/kb-api-app
   databricks apps deploy kb-api-app --source-code-path /Workspace/Users/hhu@edc.ca/kb-api-app
   ```
   Or as a range (oldest..newest, with revert applied newest-to-oldest under the hood):
   ```powershell
   git revert --no-edit <T1-parent-sha>..HEAD
   ```
4. **Partial revert (lock-only, keep singleton)** — if regression is async-safety related (deadlock/throughput) but cold-start improvement should be retained, revert only the lock-introducing commits (T2 lock-wrap inside `synthesize_response`, T3/T4 lock parameter threading). Identify by:
   ```powershell
   git log --grep="v1.1.P5" --grep="lock\|async with" --all-match --format='%H %s'
   ```
   Revert those SHAs individually. This leaves lifespan + singleton in place; restores per-call serialization-free behavior. Acceptable interim state if SC#3 surfaces a Databricks-specific issue not seen locally.
5. **Hot-fix gate**: per Principle #9, sync-only is permissible since P5 touches **no** `kb/static/` or `kb/templates/` files. Re-confirm with `git diff --name-only HEAD~6..HEAD | Select-String 'kb/(static|templates)/'` returning empty.

### What the rollback does NOT cover

- The `tests/integration/kb/test_async_safety.py` file (already exists from quick 260527-swt) is preserved; reverting P5 leaves the test file in place. It will fail against pre-P5 code (the race it was written to detect was the reason for P5). Mark `@pytest.mark.skip` if pre-P5 main is the long-term home.

## Phase 2 EXECUTE Task Sequence (atomic commits)

Six atomic commits, dependency-ordered. Operator pre-approves these commit boundaries.

```xml
<task id="P5-T1" wave="1" depends_on="" autonomous="true" requirements="SC#1,SC#4">
  <name>T1: Add lifespan + app.state.lightrag singleton in kb/api.py</name>
  <files_modified>kb/api.py</files_modified>
  <read_first>
    - kb/api.py (current 91 LoC — confirm NO lifespan; line 39 is bare FastAPI() call)
    - .planning/phases/v1.1-roadmap/P5/RESEARCH.md §1 (canonical lifespan pattern)
    - kg_synthesize.py:71-107 (current lazy singleton — REPLICATE the LightRAG(...) construction args verbatim into lifespan)
    - kg_synthesize.py:25-34 (_get_embedding_func — lifespan must call this exactly to keep behavior identical)
    - kg_synthesize.py:110-124 (_embedding_timeout_default — lifespan passes this into LightRAG default_embedding_timeout)
    - lib/llm_complete.py (get_llm_func — lifespan passes this into llm_model_func)
  </read_first>
  <action>
    1. Add imports at top of `kb/api.py` after existing `from typing import Any` (line 23):
       ```python
       import asyncio
       import logging
       import time
       from contextlib import asynccontextmanager

       from fastapi import Request
       from lightrag.lightrag import LightRAG

       from config import RAG_WORKING_DIR
       from lib.llm_complete import get_llm_func
       from kg_synthesize import _get_embedding_func, _embedding_timeout_default
       ```
       (note: `_get_embedding_func` and `_embedding_timeout_default` will REMAIN in kg_synthesize.py after T2 — they are not part of the deleted singleton block)
    2. Insert `lifespan` block IMMEDIATELY BEFORE the `app = FastAPI(...)` call at line 39:
       ```python
       _log = logging.getLogger(__name__)


       @asynccontextmanager
       async def lifespan(app: FastAPI):
           t0 = time.monotonic()
           _log.warning("lightrag_singleton_init_start working_dir=%s", RAG_WORKING_DIR)
           rag = LightRAG(
               working_dir=RAG_WORKING_DIR,
               llm_model_func=get_llm_func(),
               embedding_func=_get_embedding_func(),
               default_embedding_timeout=_embedding_timeout_default(),
           )
           if hasattr(rag, "initialize_storages"):
               await rag.initialize_storages()
           app.state.lightrag = rag
           app.state.lightrag_lock = asyncio.Lock()
           _log.warning(
               "lightrag_singleton_ready wall_s=%.2f", time.monotonic() - t0,
           )
           try:
               yield
           finally:
               if hasattr(rag, "finalize_storages"):
                   await rag.finalize_storages()
               _log.warning("lightrag_singleton_finalize_done")
       ```
       (log level WARNING per the precedent at kb/api_routers/search.py:108-109 — root-logger=WARNING on Databricks Apps swallows INFO; this is a single one-shot log per process boot, not a hot-path emission)
    3. Modify line 39 (the `app = FastAPI(...)` call) to add `lifespan=lifespan` as the first kwarg:
       ```python
       app = FastAPI(
           lifespan=lifespan,
           title="OmniGraph KB v2",
           version=_APP_VERSION,
           description="Bilingual Agent-tech content site backend (FTS5 + KG Q&A wrap)",
       )
       ```
  </action>
  <acceptance_criteria>
    - `grep -q "@asynccontextmanager" kb/api.py` returns true
    - `grep -q "app.state.lightrag" kb/api.py` returns true
    - `grep -q "app.state.lightrag_lock" kb/api.py` returns true
    - `grep -q "finalize_storages" kb/api.py` returns true
    - `grep -q "lifespan=lifespan" kb/api.py` returns true
    - `python -c "from kb.api import app; assert app.router.lifespan_context is not None"` exits 0
    - `python -m py_compile kb/api.py` exits 0
    - `pytest tests/unit/kb/ -x -q` (existing kb unit tests pass)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P5): add lifespan + app.state.lightrag singleton in kb/api.py</commit_message>
</task>

<task id="P5-T2" wave="1" depends_on="P5-T1" autonomous="true" requirements="SC#1,SC#3">
  <name>T2: Refactor synthesize_response to accept rag + lightrag_lock; remove module-global singleton; lock the inner aquery() (Option A)</name>
  <files_modified>kg_synthesize.py</files_modified>
  <read_first>
    - kg_synthesize.py (full file — current 293 LoC; lines 71-107 are the deletion target; line 185 is the signature change; lines 243-246 are the lock-wrap target)
    - .planning/phases/v1.1-roadmap/P5/RESEARCH.md §2 (aquery() mutation confirmation)
    - kb/api.py (post-T1 — confirm `_get_embedding_func` and `_embedding_timeout_default` are imported by lifespan; these helpers MUST stay in kg_synthesize.py)
  </read_first>
  <action>
    1. **DELETE lines 71-107 inclusive** (the module-global singleton block):
       - Remove the comment block at lines 71-77
       - Remove `_rag_singleton: "LightRAG | None" = None` (line 78)
       - Remove `_rag_init_lock: "asyncio.Lock | None" = None` (line 79)
       - Remove the entire `async def _get_or_init_rag() -> LightRAG:` function (lines 82-107)
    2. **KEEP lines 110-124** (`_embedding_timeout_default`) — the lifespan in `kb/api.py` imports it.
    3. **KEEP lines 25-34** (`_get_embedding_func`) — same reason.
    4. **MODIFY line 185** — change signature from:
       ```python
       async def synthesize_response(query_text: str, mode: str = "hybrid"):
       ```
       to:
       ```python
       async def synthesize_response(
           query_text: str,
           mode: str = "hybrid",
           rag: LightRAG | None = None,
           lightrag_lock: asyncio.Lock | None = None,
       ) -> str:
       ```
       (both new params are OPTIONAL with default None — keeps CLI entrypoint `if __name__ == "__main__":` working without API server context. Type hint `str` per existing return-string contract.)
    5. **REPLACE line 186** (`rag = await _get_or_init_rag()`) with the CLI-fallback build:
       ```python
       if rag is None:
           # CLI fallback path: build a one-shot LightRAG. Production callers
           # (kb-api routers) pass the lifespan-pinned app.state.lightrag.
           rag = LightRAG(
               working_dir=RAG_WORKING_DIR,
               llm_model_func=get_llm_func(),
               embedding_func=_get_embedding_func(),
               default_embedding_timeout=_embedding_timeout_default(),
           )
           if hasattr(rag, "initialize_storages"):
               await rag.initialize_storages()
       ```
       (the async-safety lock is enforced INSIDE this same function around `aquery()` — see step 6. CLI path passes `lightrag_lock=None` and the lock branch degrades to a plain await — single-process single-call, no concurrency surface to protect.)
    6. **WRAP the inner `await asyncio.wait_for(rag.aquery(...))` block at lines 243-246** with a conditional `async with lightrag_lock:`. Replace the existing block:
       ```python
       response = await asyncio.wait_for(
           rag.aquery(custom_prompt, param=param),
           timeout=KB_LIGHTRAG_INNER_TIMEOUT,
       )
       ```
       with:
       ```python
       if lightrag_lock is not None:
           async with lightrag_lock:
               response = await asyncio.wait_for(
                   rag.aquery(custom_prompt, param=param),
                   timeout=KB_LIGHTRAG_INNER_TIMEOUT,
               )
       else:
           # CLI path: no concurrency surface, skip lock acquisition
           response = await asyncio.wait_for(
               rag.aquery(custom_prompt, param=param),
               timeout=KB_LIGHTRAG_INNER_TIMEOUT,
           )
       ```
       Note: this is INSIDE the existing `for i in range(3):` retry loop (line 233) — the lock is re-acquired per attempt, which is correct (each attempt is a fresh `aquery()` invocation that mutates cache).
  </action>
  <acceptance_criteria>
    - `grep -q "_rag_singleton" kg_synthesize.py` returns FALSE (block deleted)
    - `grep -q "_rag_init_lock" kg_synthesize.py` returns FALSE (block deleted)
    - `grep -q "_get_or_init_rag" kg_synthesize.py` returns FALSE (function deleted)
    - `grep -qE "rag: LightRAG \| None = None" kg_synthesize.py` returns true (signature updated)
    - `grep -qE "lightrag_lock: asyncio.Lock \| None = None" kg_synthesize.py` returns true (lock param on signature)
    - `grep -q "async with lightrag_lock:" kg_synthesize.py` returns true (inner lock site present)
    - `grep -q "_embedding_timeout_default" kg_synthesize.py` returns true (still defined)
    - `grep -q "_get_embedding_func" kg_synthesize.py` returns true (still defined)
    - `python -m py_compile kg_synthesize.py` exits 0
    - `python -c "from kb.api import app; print('ok')"` exits 0 (import chain unbroken)
  </acceptance_criteria>
  <commit_message>refactor(v1.1.P5): remove kg_synthesize module-global singleton; thread rag+lock through synthesize_response; lock inner aquery</commit_message>
</task>

<task id="P5-T3" wave="1" depends_on="P5-T2" autonomous="true" requirements="SC#1,SC#3">
  <name>T3: Thread request.app.state.lightrag + lock through synthesize router + service wrapper (NO router-layer lock acquisition — Option A)</name>
  <files_modified>kb/services/synthesize.py, kb/api_routers/synthesize.py</files_modified>
  <read_first>
    - kb/api_routers/synthesize.py (current 87 LoC; line 51 is endpoint signature; line 62 is BackgroundTasks dispatch)
    - kb/services/synthesize.py:490-567 (kb_synthesize body — line 521-524 is the synthesize_response call site; UNCHANGED outer wait_for, parameters added only)
    - kg_synthesize.py:185 (post-T2 signature — confirm `rag` and `lightrag_lock` are kwargs; lock is acquired INSIDE synthesize_response, not at this layer)
    - kb/api.py (post-T1 — confirm `app.state.lightrag` and `app.state.lightrag_lock` are populated)
  </read_first>
  <action>
    Edit `kb/api_routers/synthesize.py`:
    1. Add `Request` to the FastAPI import at line 24:
       ```python
       from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
       ```
    2. Modify the `synthesize_endpoint` signature at line 51 to add `request: Request`:
       ```python
       @router.post("/synthesize", status_code=status.HTTP_202_ACCEPTED)
       async def synthesize_endpoint(
           request: Request,
           body: SynthesizeRequest,
           background: BackgroundTasks,
       ) -> dict[str, Any]:
       ```
    3. Modify line 62 — pass `request.app.state.lightrag` and `request.app.state.lightrag_lock` to the BG task:
       ```python
       background.add_task(
           kb_synthesize,
           body.question, body.lang, jid, body.mode,
           request.app.state.lightrag,
           request.app.state.lightrag_lock,
       )
       ```

    Edit `kb/services/synthesize.py`:
    4. Add at top of file (after existing imports, near line ~1-30 — find existing `import asyncio` and confirm; if absent, add):
       ```python
       import asyncio
       from lightrag.lightrag import LightRAG
       ```
    5. Locate `kb_synthesize` function definition (the entry point invoked by BackgroundTasks; near line 480 — exact line to be confirmed by reading the file). Modify signature to add `rag` and `lightrag_lock` params:
       ```python
       async def kb_synthesize(
           question: str,
           lang: str,
           job_id: str,
           mode: str,
           rag: LightRAG,
           lightrag_lock: asyncio.Lock,
       ) -> None:
       ```
    6. At lines 521-524 (the `synthesize_response` call site), DO NOT add a router-layer `async with lightrag_lock:` wrapper. Just thread `rag` and `lightrag_lock` through as kwargs — the lock is acquired INSIDE `synthesize_response` (Option A):
       ```python
       try:
           response = await asyncio.wait_for(
               synthesize_response(
                   query_text,
                   mode="hybrid",
                   rag=rag,
                   lightrag_lock=lightrag_lock,
               ),
               timeout=KB_SYNTHESIZE_TIMEOUT,
           )
           _log.info(
               "c1_after_aquery: job_id=%s wall_s=%.2f response_chars=%d",
               job_id, time.monotonic() - t0,
               len(response) if isinstance(response, str) else 0,
           )
       ```
       (the outer `asyncio.wait_for` is UNCHANGED — it still bounds the full synthesize call; the lock now lives inside `synthesize_response()` so `wait_for` can cancel a stuck holder. NO `async with` at this layer.)
  </action>
  <acceptance_criteria>
    - `grep -q "request: Request" kb/api_routers/synthesize.py` returns true
    - `grep -q "request.app.state.lightrag" kb/api_routers/synthesize.py` returns true
    - `grep -q "request.app.state.lightrag_lock" kb/api_routers/synthesize.py` returns true
    - `grep -qE "async def kb_synthesize\(.*rag: LightRAG.*lightrag_lock: asyncio.Lock" kb/services/synthesize.py` returns true (allow multiline regex via -P or rg multiline)
    - `grep -q "async with lightrag_lock:" kb/services/synthesize.py` returns FALSE (lock NOT acquired at this layer per Option A)
    - `grep -qE "lightrag_lock=lightrag_lock" kb/services/synthesize.py` returns true (lock threaded through as kwarg)
    - `grep -qE "rag=rag" kb/services/synthesize.py` returns true (rag threaded through as kwarg)
    - `python -m py_compile kb/api_routers/synthesize.py kb/services/synthesize.py` exits 0
    - `pytest tests/unit/kb/api_routers/test_synthesize.py -x -q` (existing — must adapt fixtures to inject `request.app.state.lightrag`; if fixtures break, FIX the fixtures by patching app.state in TestClient setup, do NOT skip the test)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P5): thread request.app.state.lightrag + lock through /api/synthesize router and service (no router-layer lock)</commit_message>
</task>

<task id="P5-T4" wave="1" depends_on="P5-T3" autonomous="true" requirements="SC#3">
  <name>T4: Thread app.state.lightrag + lock through search router KG workers (NO router-layer lock — Option A); remove omnigraph_search duplicate singleton</name>
  <files_modified>kb/api_routers/search.py, omnigraph_search/query.py</files_modified>
  <read_first>
    - kb/api_routers/search.py (lines 56-71 = _kg_worker; lines 91-164 = _kg_local_worker; lines 218-220 + 245-247 = both BackgroundTasks dispatches)
    - omnigraph_search/query.py (lines 39-67 = duplicate singleton block; lines 70-101 = search() — signature target)
    - kg_synthesize.py (post-T2 — confirm `rag` and `lightrag_lock` are optional kwargs; lock acquired INSIDE synthesize_response)
    - lib/research/stages/reasoner.py (consumer of omnigraph_search.query.search — verify how it constructs/passes rag; if it does NOT pass rag, the CLI-fallback default-None branch protects it transparently — confirm before edit)
  </read_first>
  <action>
    Edit `kb/api_routers/search.py`:
    1. Add `Request` to the FastAPI import at line 28:
       ```python
       from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
       ```
    2. Add `from lightrag.lightrag import LightRAG` near line 28 (with other imports).
    3. Modify `_kg_worker` (line 56) signature to accept `rag, lightrag_lock` and thread them into `synthesize_response()` — NO router-layer `async with`:
       ```python
       async def _kg_worker(job_id: str, q: str, rag: LightRAG, lightrag_lock: asyncio.Lock) -> None:
           ...
           result = await synthesize_response(
               q,
               mode="hybrid",
               rag=rag,
               lightrag_lock=lightrag_lock,
           )
           job_store.update_job(job_id, status="done", result=result)
       ```
       (the lock is acquired INSIDE `synthesize_response()` — Option A. Do NOT add `async with lightrag_lock:` at this layer.)
    4. Modify `_kg_local_worker` (line 91) signature the same way; thread `rag` and `lightrag_lock` into `synthesize_response()` INSIDE the existing `asyncio.wait_for(...)` — NO router-layer `async with`:
       ```python
       async def _kg_local_worker(job_id: str, query: str, rag: LightRAG, lightrag_lock: asyncio.Lock) -> None:
           ...
           markdown = await asyncio.wait_for(
               synthesize_response(
                   wrapped,
                   mode="local",
                   rag=rag,
                   lightrag_lock=lightrag_lock,
               ),
               timeout=KB_KG_SEARCH_TIMEOUT,
           )
       ```
       (outer `asyncio.wait_for` unchanged — it still bounds the call and can cancel a stuck lock-holder because the lock now lives strictly inside `synthesize_response`.)
    5. Modify `search_endpoint` (line 177) — add `request: Request` first param:
       ```python
       async def search_endpoint(
           request: Request,
           background: BackgroundTasks,
           q: Annotated[str, Query(min_length=1, max_length=500)],
           ...
       ```
       and modify line 220's BG dispatch:
       ```python
       background.add_task(
           _kg_worker, jid, q,
           request.app.state.lightrag,
           request.app.state.lightrag_lock,
       )
       ```
    6. Modify `kg_enhance_start` (line 225) — add `request: Request` param:
       ```python
       async def kg_enhance_start(
           request: Request,
           payload: _KgSearchRequest,
           background: BackgroundTasks,
       ) -> dict[str, Any]:
       ```
       and modify line 246's BG dispatch:
       ```python
       background.add_task(
           _kg_local_worker, jid, payload.query,
           request.app.state.lightrag,
           request.app.state.lightrag_lock,
       )
       ```

    Edit `omnigraph_search/query.py`:
    7. **DELETE lines 39-67 inclusive** (the duplicate singleton block: `_rag_singleton`, `_rag_init_lock`, `_get_or_init_rag`).
    8. Modify `search()` signature at line 70:
       ```python
       async def search(
           query_text: str,
           mode: str = "hybrid",
           only_context: bool = False,
           rag: LightRAG | None = None,
       ) -> str:
       ```
    9. Replace line 97 (`rag = await _get_or_init_rag()`) with:
       ```python
       if rag is None:
           # CLI fallback (skill_runner / `python -m omnigraph_search.query`):
           # build a one-shot LightRAG. Production callers (kb-api routers) pass
           # the lifespan-pinned app.state.lightrag.
           rag = LightRAG(
               working_dir=RAG_WORKING_DIR,
               llm_model_func=get_llm_func(),
               embedding_func=_embedding_func,
           )
           if hasattr(rag, "initialize_storages"):
               await rag.initialize_storages()
       ```
       (no lock parameter on `search()` — its only kb-api consumers reach LightRAG via `synthesize_response` which holds the lock internally. CLI invocation is single-process single-call.)
  </action>
  <acceptance_criteria>
    - `grep -q "_rag_singleton" omnigraph_search/query.py` returns FALSE
    - `grep -q "_rag_init_lock" omnigraph_search/query.py` returns FALSE
    - `grep -q "_get_or_init_rag" omnigraph_search/query.py` returns FALSE
    - `grep -qE "async def search\(.*rag: LightRAG \| None = None" omnigraph_search/query.py` returns true (multiline)
    - `grep -qE "async def _kg_worker\(.*rag: LightRAG.*lightrag_lock: asyncio.Lock" kb/api_routers/search.py` returns true (multiline)
    - `grep -qE "async def _kg_local_worker\(.*rag: LightRAG.*lightrag_lock: asyncio.Lock" kb/api_routers/search.py` returns true (multiline)
    - `grep -q "async with lightrag_lock:" kb/api_routers/search.py` returns FALSE (router does NOT acquire lock per Option A)
    - `grep -c "lightrag_lock=lightrag_lock" kb/api_routers/search.py` returns 2 (one per worker, threaded into synthesize_response kwargs)
    - `grep -q "request.app.state.lightrag" kb/api_routers/search.py` returns true (matched twice — search_endpoint + kg_enhance_start)
    - `python -m py_compile kb/api_routers/search.py omnigraph_search/query.py` exits 0
    - `python -c "from omnigraph_search.query import search; import inspect; assert 'rag' in inspect.signature(search).parameters"` exits 0
    - `pytest tests/unit/kb/api_routers/test_search.py -x -q` (existing — fix any TestClient fixtures that don't populate app.state)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P5): thread app.state.lightrag + lock through search router workers (no router-layer lock); remove omnigraph_search duplicate singleton</commit_message>
</task>

<task id="P5-T5" wave="1" depends_on="P5-T4" autonomous="true" requirements="SC#3">
  <name>T5: Add tests/integration/kb/test_lifespan_singleton.py</name>
  <files_modified>tests/integration/kb/test_lifespan_singleton.py</files_modified>
  <read_first>
    - tests/integration/kb/test_async_safety.py (existing 39 LoC — pattern reference for httpx.AsyncClient + KB_BASE_URL)
    - kb/api.py (post-T1 — confirm `app.state.lightrag` is set in lifespan)
  </read_first>
  <action>
    Create `tests/integration/kb/test_lifespan_singleton.py`:
    ```python
    """P5 SC#1+SC#3: lifespan-pinned LightRAG singleton — same instance across requests.

    Uses FastAPI's TestClient context-manager protocol which fires lifespan startup
    + shutdown; we then directly inspect `app.state.lightrag` to assert id() stability.
    Does NOT require a real running uvicorn — TestClient runs the app in-process.
    """
    from __future__ import annotations

    import pytest
    from fastapi.testclient import TestClient

    from kb.api import app


    @pytest.mark.integration
    def test_lifespan_singleton_id_stable_across_requests() -> None:
        with TestClient(app) as client:
            # /health is the cheapest way to confirm the app is fully booted post-lifespan
            r1 = client.get("/health")
            assert r1.status_code == 200, r1.text
            id_1 = id(app.state.lightrag)
            assert app.state.lightrag is not None
            assert app.state.lightrag_lock is not None

            r2 = client.get("/health")
            assert r2.status_code == 200, r2.text
            id_2 = id(app.state.lightrag)

            assert id_1 == id_2, (
                f"app.state.lightrag was reconstructed between requests "
                f"(id changed: {id_1} -> {id_2}); lifespan singleton broken"
            )


    @pytest.mark.integration
    def test_lifespan_finalize_called_on_shutdown(caplog) -> None:
        """SC#4: finalize_storages is called when lifespan exits."""
        import logging
        caplog.set_level(logging.WARNING, logger="kb.api")
        with TestClient(app) as client:
            client.get("/health")  # ensures full lifespan startup
        # After the with-block exits, lifespan finally: ran
        assert any(
            "lightrag_singleton_finalize_done" in rec.message
            for rec in caplog.records
        ), [r.message for r in caplog.records]
    ```
  </action>
  <acceptance_criteria>
    - File exists at `tests/integration/kb/test_lifespan_singleton.py`
    - `pytest tests/integration/kb/test_lifespan_singleton.py -v -m integration` runs and BOTH tests pass
    - First test asserts `id(app.state.lightrag)` stable across two requests (the SC#1 invariant)
    - Second test asserts `lightrag_singleton_finalize_done` log line emitted on shutdown (SC#4)
  </acceptance_criteria>
  <commit_message>test(v1.1.P5): add lifespan-singleton id-stability + finalize-on-shutdown integration tests</commit_message>
</task>

<task id="P5-T6" wave="2" depends_on="P5-T5" autonomous="false" requirements="SC#1,SC#2,SC#3,SC#4,SC#5">
  <name>T6: Local UAT + Databricks N=4 verification + write P5-VERIFICATION.md (CHECKPOINT)</name>
  <files_modified>.planning/phases/v1.1-roadmap/P5/P5-VERIFICATION.md</files_modified>
  <read_first>
    - This PLAN.md "Validation Plan" section (Track 1 + Track 2 + Track 3 + Track 4)
    - CLAUDE.md Principle #6 (Local UAT mandatory) — VERIFICATION.md must cite launcher + curl smoke + screenshot paths
    - CLAUDE.md Principle #9 (Makefile-deploy gate) — confirm `git diff --name-only` returns empty for kb/static/ and kb/templates/ before sync-only deploy
  </read_first>
  <action>
    Sequential execution:

    1. **Local cold-start measurement (Track 1):**
       - `Stop-Process` any existing uvicorn on :8766
       - Start `.\venv\Scripts\python.exe .scratch\local_serve.py *> .uvicorn-p5.log` in background
       - Measure boot-to-/health time; record `BOOT_TO_HEALTH_MS`
       - First POST /api/synthesize; record `FIRST_REQ_WALL_MS`
       - **Assertion:** `FIRST_REQ_WALL_MS < 30000`
       - **Assertion:** `Select-String "lightrag_singleton_init_start" .uvicorn-p5.log | Measure-Object | %{$_.Count}` returns 1

    2. **Local browser UAT (Principle #6):**
       - Open http://localhost:8766 in browser; submit a query via the existing UI
       - Capture screenshot to `.playwright-mcp/v1.1.P5-uat-local.png`
       - Verify response markdown renders + `confidence: kg` reported

    3. **Steady-state baseline (Track 4):** run the 10-iteration p50/p95 measurement on local AGAINST POST-P5 code (compare to pre-P5 baseline if available — pre-P5 baseline can be captured by `git stash` + measure if not already on file). Record `p50` and `p95`.

    4. **Lifespan shutdown (Track 3):**
       - Foreground-launch `local_serve.py`; Ctrl+C
       - `Select-String "lightrag_singleton_finalize_done" .uvicorn-p5.log` returns ≥1 hit

    5. **Principle #9 file-touch check:**
       - `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` MUST return empty
       - If not empty → HALT and re-plan

    6. **Databricks deploy (sync-only, P9 cleared):**
       - `databricks sync --watch . /Workspace/Users/hhu@edc.ca/kb-api-app` until "Initial Sync Complete"
       - `databricks apps deploy kb-api-app --source-code-path /Workspace/Users/hhu@edc.ca/kb-api-app` until SUCCEEDED

    7. **Databricks N=4 concurrent test (Track 2):**
       - `$env:KB_BASE_URL = "<deployed-url>"`
       - `pytest tests/integration/kb/test_async_safety.py::test_singleton_async_safety_n4 -v`
       - Test must PASS (4/4 done, distinct markdown, MARKER tokens preserved)

    8. **Databricks log singleton check:**
       - `make logs` (or `databricks apps logs ...` per project convention) → `Select-String "lightrag_singleton_init_start"` returns Count: 1

    9. **Write `P5-VERIFICATION.md`** in `.planning/phases/v1.1-roadmap/P5/` with sections:
       - **SC#1 evidence**: `BOOT_TO_HEALTH_MS=<value>`, `FIRST_REQ_WALL_MS=<value>`, init-log-count assertion
       - **SC#2 evidence**: `pre-P5 p50=<>, p95=<>` vs `post-P5 p50=<>, p95=<>`
       - **SC#3 evidence**: pytest output of test_async_safety.py::test_singleton_async_safety_n4 (full stdout)
       - **SC#4 evidence**: `lightrag_singleton_finalize_done` log line excerpt
       - **SC#5 Local UAT section**: launcher command, env values, curl smoke results (status + key fields), screenshot path `.playwright-mcp/v1.1.P5-uat-local.png`
       - **Databricks deploy section**: sync output excerpt, deploy SUCCEEDED line, init-log Count=1 from server log
       - **Principle #9 gate**: paste the empty `git diff --name-only` filter result

    10. **Pause for operator approval** (`<resume-signal>type "approved" to mark P5 complete</resume-signal>`).
  </action>
  <acceptance_criteria>
    - `.planning/phases/v1.1-roadmap/P5/P5-VERIFICATION.md` exists
    - File contains "SC#1", "SC#2", "SC#3", "SC#4", "SC#5" headers (all 5)
    - `grep -q "FIRST_REQ_WALL_MS=" P5-VERIFICATION.md` returns true (numeric value present)
    - `grep -q "lightrag_singleton_finalize_done" P5-VERIFICATION.md` returns true
    - `grep -q ".playwright-mcp/v1.1.P5-uat-local.png" P5-VERIFICATION.md` returns true (screenshot path cited)
    - `grep -qE "test_singleton_async_safety_n4 PASSED" P5-VERIFICATION.md` returns true (pytest evidence)
    - `grep -q "Principle #9" P5-VERIFICATION.md` returns true (P9 gate explicitly recorded)
    - Operator types "approved" in the resume signal
  </acceptance_criteria>
  <commit_message>docs(v1.1.P5): P5-VERIFICATION.md — cold-start &lt;30s, N=4 async-safety green, lifespan shutdown ok</commit_message>
</task>
```

## verification

Phase-level verification (rolled up from per-task acceptance criteria):

- All 5 atomic commits land on main, in T1..T5 order
- T6 produces P5-VERIFICATION.md citing all 5 SCs with concrete numeric / log evidence
- `pytest tests/integration/kb/test_lifespan_singleton.py tests/integration/kb/test_async_safety.py -v -m integration` is GREEN against the deployed Databricks app
- `git grep -n "_rag_singleton\\|_get_or_init_rag" kg_synthesize.py omnigraph_search/query.py` returns no hits (both duplicate singletons removed)
- `git grep -n "async with lightrag_lock" kg_synthesize.py kb/services/synthesize.py kb/api_routers/search.py` returns exactly 1 hit, all in `kg_synthesize.py` (Option A — single inner lock site)
- Databricks Apps server log shows exactly one `lightrag_singleton_init_start` per process boot

## success_criteria

P5 is complete when:
- [ ] SC#1: First /api/synthesize 200/202 sub-30s on local NTFS (numeric in VERIFICATION.md)
- [ ] SC#2: post-P5 p50 ≤ pre-P5 p50 × 1.10 AND post-P5 p95 ≤ pre-P5 p95 × 1.20
- [ ] SC#3: 4-concurrent test PASSED (distinct markdown, MARKER preservation, no deadlock)
- [ ] SC#4: `lightrag_singleton_finalize_done` log line confirmed on shutdown
- [ ] SC#5: Local UAT screenshot + curl smoke cited in P5-VERIFICATION.md per Principle #6

## output

After T6 operator-approved, the phase is closed with:
- 6 commits on main (T1..T6)
- Updated STATE.md (orchestrator handles)
- P5-VERIFICATION.md cited from phase entry
