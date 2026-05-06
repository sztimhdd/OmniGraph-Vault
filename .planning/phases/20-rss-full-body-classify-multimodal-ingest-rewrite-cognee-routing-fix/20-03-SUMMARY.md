---
phase: 20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix
plan: "03"
subsystem: cognee_wrapper
status: PARTIAL
tags: [cognee, fire-and-forget, asyncio, cog-02, cog-01]
dependency_graph:
  requires: ["20-00"]
  provides: ["COG-02"]
  affects: ["cognee_wrapper.remember_article", "ingest_wechat (pending COG-03)"]
tech_stack:
  added: []
  patterns: ["asyncio.create_task fire-and-forget", "inner coroutine swallow-exceptions pattern"]
key_files:
  created: []
  modified:
    - cognee_wrapper.py
decisions:
  - "D-20.15: asyncio.create_task wrap mandatory (wait_for(timeout=5.0) was blocking ~5s per Research Q3)"
  - "COG-01 verified-only: EMBEDDING_MODEL=gemini/gemini-embedding-2 at line 50 — no code change"
  - "Task 3.3 PARKED: env gate retirement gated on live Hermes 3-article smoke per D-20.14"
metrics:
  duration: "~3 min"
  completed_date: "2026-05-06"
  tasks_completed: 2
  tasks_parked: 1
  files_modified: 1
---

# Phase 20 Plan 03: COG Routing Fix Summary

**One-liner:** Fire-and-forget `remember_article` via `asyncio.create_task` eliminates 5s blocking of ingest fast-path; COG-01 LiteLLM routing verified in place.

---

## Status: PARTIAL (Tasks 3.1 + 3.2 complete; Task 3.3 PARKED)

Task 3.3 (COG-03 — retire OMNIGRAPH_COGNEE_INLINE env gate from ingest_wechat.py)
is parked pending operator action per D-20.14. Operator must:

1. SSH to Hermes per `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`
2. Run `OMNIGRAPH_COGNEE_INLINE=1 venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter agent --min-depth 2 --max-articles 3`
3. Verify all 3 articles complete <30 min total + Cognee episodic store grows + no 422 errors
4. Only after 3/3 success: re-invoke `/gsd:execute-phase 20 --task 3.3` to retire the env gate

This plan is INCOMPLETE pending Task 3.3.

---

## Tasks Completed

### Task 3.1: COG-01 Verification (no code change)

**COG-01 verification (2026-05-06):**
- `cognee_wrapper.py:50` → `EMBEDDING_MODEL = "gemini/gemini-embedding-2"` (with `gemini/` LiteLLM prefix) ✓
- `cognee_wrapper.py:51` → `EMBEDDING_DIMENSIONS = "3072"` ✓
- `git log --oneline -- cognee_wrapper.py` top entry: `74f7503 fix(cognee): route LiteLLM embedding via Gemini API, not Vertex AI` ✓
- Status: COG-01 verified-only — no code change required or made

### Task 3.2: COG-02 — refactor remember_article to fire-and-forget

**What changed in `cognee_wrapper.py`:**

Replaced the `asyncio.wait_for(timeout=5.0)` blocking wrapper around `cognee.remember(...)` in `remember_article` with a true fire-and-forget `asyncio.create_task(_bg_remember())` pattern.

Before (blocks ~5s):
```python
await asyncio.wait_for(
    cognee.remember(text, dataset_name=_ARTICLE_DATASET, ...),
    timeout=5.0,
)
```

After (returns in <1ms):
```python
async def _bg_remember() -> None:
    try:
        await cognee.remember(text, dataset_name=_ARTICLE_DATASET, ...)
        logger.info("remember_article stored: %s", title[:80])
    except Exception as e:
        logger.debug("remember_article task failed: %s", e)

asyncio.create_task(_bg_remember())
return True
```

**Functions NOT touched (different semantics — callers DO want bounded results):**
- `remember_synthesis` — keeps `asyncio.wait_for(_COGNEE_TIMEOUT=30s)` 
- `recall_previous_context` — keeps `asyncio.wait_for(_COGNEE_TIMEOUT=30s)`
- `disambiguate_entities` — keeps `asyncio.wait_for(timeout=2.0)`
- `log_query_pattern` — direct await (no timeout wrapper)

**Test result:**

```
tests/unit/test_cognee_remember_detaches.py::test_remember_returns_fast PASSED
1 passed in 7.51s
```

Mock `cognee.remember = asyncio.sleep(10)` returns in <100ms — COG-02 contract satisfied.

**Regression result (4-test targeted):**

```
9 passed in 8.34s
```

All 4 test files (test_cognee_remember_detaches, test_scraper, test_batch_ingest_hash, test_rss_schema_migration) pass.

**Commit:** `c6bd91c` — `refactor(cognee_wrapper): D-20.15 fire-and-forget remember_article (COG-02)`

---

## Task 3.3: PARKED — COG-03 Live Hermes Smoke (D-20.14)

**Status:** NOT EXECUTED — operator gate, out of scope for autonomous run.

`ingest_wechat.py` `OMNIGRAPH_COGNEE_INLINE` env gate at lines 796-809 and 1163-1172 is UNCHANGED. The gate remains default-off (`OMNIGRAPH_COGNEE_INLINE=0`).

**Operator steps required before this task can run:**

1. Pull latest `cognee_wrapper.py` to Hermes (`git pull --ff-only`)
2. Confirm `grep -n 'asyncio.create_task' cognee_wrapper.py` shows the new fire-and-forget path
3. Run: `OMNIGRAPH_COGNEE_INLINE=1 venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter agent --min-depth 2 --max-articles 3 2>&1 | tee /tmp/cog03-smoke-$(date +%Y%m%d-%H%M%S).log`
4. Verify all 5 criteria from the plan's Task 3.3 Step 4 (a-e)
5. On 3/3 pass: proceed to Step 6 retirement edits in plan

**Retirement scope (when COG-03 smoke passes):**
- Delete `_cognee_inline_enabled()` helper at `ingest_wechat.py:796-809`
- Replace `if _cognee_inline_enabled():` block at `ingest_wechat.py:1163-1172` with unconditional call
- Remove `OMNIGRAPH_COGNEE_INLINE` row from CLAUDE.md Environment Variables table

---

## Deviations from Plan

None — Tasks 3.1 and 3.2 executed exactly as specified in the plan. Task 3.3 was intentionally skipped per the execution objective (operator-gated, out of scope for autonomous run). This is not a deviation but a planned partial execution boundary.

---

## Known Stubs

None in the code modified. `ingest_wechat.py` env gate (`OMNIGRAPH_COGNEE_INLINE`) is an intentional holdover pending Task 3.3 operator smoke — not a stub, it is the safety gate designed to remain until the live Hermes smoke proves the fire-and-forget path is stable.

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `cognee_wrapper.py` exists | FOUND |
| `20-03-SUMMARY.md` exists | FOUND |
| Commit `c6bd91c` in git log | FOUND |
| `asyncio.create_task` in cognee_wrapper.py | 2 occurrences |
| `gemini/gemini-embedding-2` at line 50 | CONFIRMED |
| `OMNIGRAPH_COGNEE_INLINE` in ingest_wechat.py | 5 occurrences (gate PRESERVED, untouched) |
| `asyncio.wait_for` in remember_article body | 0 occurrences (removed from function, kept in other functions) |
| test_remember_returns_fast | 1 PASSED |
| 4-test regression suite | 9 PASSED |
