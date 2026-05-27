# P5 — LR-singleton + async-safety

**Wave:** 1 (parallel with P1)
**LoC estimate:** 50–80
**Risk:** Medium (async-safety verification gate)
**Mainstream alignment:** ⭐⭐ (perf-only on the user-facing axis; ⭐⭐⭐⭐ on the iteration-velocity axis)
**Dependencies:** P6.0 (fixture green floor)
**Recommended GSD ceremony:** `/gsd:plan-phase`

## Goal

Pin a single LightRAG instance to `app.state` via FastAPI's `lifespan` context manager so the cold-start cost (entity store load + embedding cache warm-up) is paid **once per uvicorn process** instead of **once per `/api/synthesize` request**. Today's per-request init is 60–350s on local NTFS (filed from arx-3 STEP 4 diagnostic 2026-05-26), which makes UAT iteration on P1 / P2-3 / P4 painful. This phase also adds the **async-safety verification gate** flagged in [RESEARCH.md §6](RESEARCH.md): `app.state` is not concurrent-safe by default — LightRAG internal state may not be reentrant, so we must explicitly verify behavior under N parallel `aquery()` calls and add an `asyncio.Lock` or per-call clone-on-write strategy if needed.

## File-touch list (best guess; verified at /gsd:plan-phase time)

- `kb/api.py` — add `lifespan` async context manager; load LightRAG into `app.state.lightrag` at startup, finalize storages on shutdown
- `kg_synthesize.py` — refactor `synthesize_response()` to consume `request.app.state.lightrag` instead of constructing a fresh instance per call (`kg_synthesize.py:146-153` is current init site)
- `kb/services/synthesize.py` — same refactor, route through app.state
- `kb/api_routers/*` — wire `request.app.state.lightrag` consumer pattern
- `tests/integration/kb/test_lifespan_singleton.py` — NEW: assert `app.state.lightrag` is the same object across two requests
- `tests/integration/kb/test_async_safety.py` — NEW: fire N=4 concurrent `/api/synthesize` requests; assert no deadlock, no corrupted state, no embedding-cache race

## Success criteria

1. Cold-start of kb-api → first `/api/synthesize` 200 response is **sub-30s on local NTFS** (down from 60–350s)
2. Steady-state per-query latency unchanged or better (pre-P5 vs. post-P5 benchmark on identical query set, p50 + p95)
3. Async-safety verified: 4 concurrent `/api/synthesize` requests against the singleton produce 4 correct, independent responses (no deadlock, no shared-state corruption); if test fails, add `asyncio.Lock` around LightRAG ops and re-verify
4. Lifespan shutdown gracefully calls `await app.state.lightrag.finalize_storages()` on uvicorn SIGTERM (no orphaned file handles)
5. Local UAT per Principle #6: `local_serve.py` cold-start time logged in `P5-VERIFICATION.md`; concurrent-query test screenshot

## Hard assumption (documented for clarity)

**Single-worker uvicorn.** Both Aliyun + Databricks deploy targets currently run kb-api with `--workers 1`. Lifespan-scoped state is **per worker process**; multi-worker safety (multiple LightRAG instances per host, embedding-cache fragmentation) is **v1.2+ scope, NOT v1.1**. P5 stub explicitly excludes multi-worker work.

## Async-safety considerations (cite RESEARCH.md §6)

- [SitePoint FastAPI](https://www.sitepoint.com/problems-and-solutions-with-fast-api-servers/): `app.state` is lifespan-scoped per worker process; persists across requests but is NOT automatically thread-/coroutine-safe.
- [Stack Overflow heavy-service init](https://stackoverflow.com/questions/67663970/optimal-way-to-initialize-heavy-services-only-once-in-fastapi): canonical pattern is `@asynccontextmanager async def lifespan(app)` with `await build_resource()` at startup and `await resource.cleanup()` at shutdown.
- LightRAG's internal `aquery()` mutates state (KV store reads, embedding cache writes); concurrent calls may race. P5 must verify empirically before declaring done.

## Deferred decisions (resolve at /gsd:plan-phase time)

- Whether `asyncio.Lock` (serialize all queries, simpler but lower throughput) or per-call clone-on-write (parallel queries against an immutable snapshot, more LoC) is the right shape — depends on what the async-safety test reveals
- Where to log the cold-start time for monitoring (stderr only, or a `/healthz` field)

---

**Execution detail TBD at `/gsd:plan-phase v1.1.P5` time.**
