---
phase: 10-classification-and-ingest-decoupling
plan: 02
subsystem: ingestion
tags: [asyncio, vision, subdoc, tdd, arch-02, arch-03, arch-04]

# Dependency graph
requires:
  - phase: 10-classification-and-ingest-decoupling
    plan: 01
    provides: "ingest_wechat._vision_worker_impl stub (plan 10-01) + ingest_article(url, rag) -> asyncio.Task|None split — plan 10-02 replaces stub body"
  - phase: 09-timeout-state-management
    provides: "D-09.05 rollback registry + rag.ainsert(content, ids=[doc_id]) pattern — sub-doc uses the same ids= keyword shape"
  - phase: 08-image-pipeline
    provides: "image_pipeline.describe_images + get_last_describe_stats + emit_batch_complete + FilterStats — worker imports + re-emits"
provides:
  - "ingest_wechat._vision_worker_impl — full body: describe_images cascade + sub-doc ainsert + try/except Exception wrapper (D-10.06 / D-10.07 / D-10.08)"
  - "batch_ingest_from_spider._drain_pending_vision_tasks + VISION_DRAIN_TIMEOUT — 120s aggregate drain before finalize_storages (D-10.09)"
  - "Sub-doc ainsert with doc_id=f\"wechat_{article_hash}_images\" — independent from parent doc, rollback-isolated"
  - "10 unit tests in tests/unit/test_vision_worker.py — 7 worker behavior + 3 orchestrator drain"
affects:
  - 11-e2e-verification-gate

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Worker-as-closure kwargs — _vision_worker_impl accepts rag/article_hash/url_to_path/title/filter_stats/download_input_count/download_failed as explicit kwargs (no implicit closure capture from ingest_article scope) for testability"
    - "finally-emit telemetry — emit_batch_complete fires from worker's finally block regardless of success/failure, unifying Phase 8 IMG-04 with Phase 10 ARCH-02"
    - "asyncio.all_tasks() + filter(not current_task, not done) — drain pattern safe for both production and test event-loop contexts"

key-files:
  created:
    - "tests/unit/test_vision_worker.py"
  modified:
    - "ingest_wechat.py"
    - "batch_ingest_from_spider.py"

key-decisions:
  - "Sub-doc content shape (D-10.07 LOCKED): `# Images for <title>\\n\\n- [image N]: <description>\\n...`. Index N preserved — empty descriptions are OMITTED, not renumbered. Downstream retrieval can correlate by the N index against [Image N Reference] lines in the parent doc."
  - "Empty-all short-circuit: when zero successful descriptions, rag.ainsert is NOT called. Info log `vision_subdoc_skipped article_hash=... reason=<no_images|all_failed>` emits instead. Parent doc is unaffected (D-10.07, D-10.08)."
  - "Exception scope (D-10.08): broad `try/except Exception` around describe_images AND rag.ainsert. CancelledError is NOT swallowed by default (subclasses BaseException in 3.8+, Exception in earlier Pythons) — this is deliberate. The batch orchestrator drain cancels stragglers; those cancellations propagate cleanly and do not pollute logs."
  - "emit_batch_complete placement: moved INSIDE the worker's finally block, forwarded filter_stats/download_input_count/download_failed from ingest_article scope. Phase 8 IMG-04 wire format is unchanged; describe_stats arrives from the worker (which now owns the describe stage), so the IMG-04 event is now emitted AFTER the Vision cascade completes rather than before (was: inline, pre-describe; now: background, post-describe). Timing downstream: the `total_ms` now measures the full Vision stage including describe_images — richer signal."
  - "Drain timeout (D-10.09): 120s aggregate deadline across ALL pending Vision tasks at batch end. Rationale: ~30 articles * ~4s describe_images per article = 120s worst case. Tests override via monkeypatch.setattr(batch_ingest_from_spider, 'VISION_DRAIN_TIMEOUT', 0.1) for determinism."
  - "asyncio.all_tasks() filter: `t is not asyncio.current_task() and not t.done()`. In both test and production contexts, the orchestrator coroutine itself is the current_task; everything else pending on the loop must be Vision workers (no other long-running background tasks in this codebase)."
  - "Straggler handling: on drain timeout, still-pending tasks are `.cancel()`-ed, then awaited once more via gather(..., return_exceptions=True) so CancelledError propagates to them — enables observable-cancellation semantics (e.g., test_drain_timeout_cancels_stragglers asserts task.cancelled()==True)."
  - "NO Rule 1 auto-fixes to plan 10-01: plan 10-01 already passed filter_stats/download_input_count/download_failed as kwargs when spawning the task (ingest_wechat.py:798-806 pre-existing). The plan 10-02 executor anticipated this correctly; no call-site changes were needed."

patterns-established:
  - "Fire-and-forget Vision worker is the default for batch ingest. `asyncio.Task` return handle is a test affordance only; production callers rely on the batch-end drain to reap."
  - "Sub-doc ainsert as the extension mechanism: LightRAG accepts a new doc with its own doc_id, and the graph engine resolves cross-doc entity links on its own. No manual edge-patching or re-embed is required."
  - "Module-level logger: ingest_wechat.py now has `logger = logging.getLogger(__name__)` at the top. caplog fixture (via `logger='ingest_wechat'`) captures worker diagnostics in tests."

metrics:
  duration: "~40 min"
  completed: "2026-04-29"
  commits:
    - hash: "93d8c58"
      description: "feat(10-02): implement async Vision worker with sub-doc ainsert + failure tolerance"
    - hash: "e6f11dc"
      description: "feat(10-02): drain pending Vision tasks before finalize_storages (D-10.09)"
  files_modified: 2
  files_created: 1
  tests_added: 10
  total_regression_passing: 61
---

# Phase 10 Plan 02: Async Vision Worker + Sub-Doc Summary

## One-liner

Background async Vision worker describes images via the existing cascade, appends descriptions as a sub-doc via `rag.ainsert(ids=["wechat_{hash}_images"])`, and swallows all failures so text-ingest (already returned successfully from plan 10-01's split) is never invalidated. Batch orchestrator drains pending workers with a 120s aggregate deadline before `finalize_storages`.

## What was built

### 1. `_vision_worker_impl` — full body (ingest_wechat.py:190-272)

Replaces the plan 10-01 stub. Signature unchanged; body implements D-10.06 / D-10.07 / D-10.08:

```python
async def _vision_worker_impl(
    *,
    rag,
    article_hash: str,
    url_to_path: dict,
    title: str,
    filter_stats=None,
    download_input_count: int = 0,
    download_failed: int = 0,
) -> None:
    t0 = time.perf_counter()
    describe_stats: dict | None = None
    try:
        paths_list = list(url_to_path.values())
        descriptions = describe_images(paths_list) if paths_list else {}
        describe_stats = get_last_describe_stats()

        lines = [f"# Images for {title}", ""]
        successful = 0
        for i, (url_img, path) in enumerate(url_to_path.items()):
            desc = descriptions.get(path, "")
            if desc and desc.strip():
                lines.append(f"- [image {i}]: {desc}")
                successful += 1

        if successful == 0:
            logger.info("vision_subdoc_skipped article_hash=%s reason=%s", ...)
        else:
            sub_doc_content = "\n".join(lines) + "\n"
            sub_doc_id = f"wechat_{article_hash}_images"
            await rag.ainsert(sub_doc_content, ids=[sub_doc_id])

    except Exception as exc:
        logger.warning("Vision worker failed for article_hash=%s: %s ...", ...)
    finally:
        try:
            emit_batch_complete(
                filter_stats=filter_stats,
                download_input_count=download_input_count,
                download_failed=download_failed,
                describe_stats=describe_stats,
                total_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception:
            pass
```

### 2. Sub-doc content verbatim example

For an article titled "LightRAG vs GraphRAG" with three images (two successful, one failed):

```
# Images for LightRAG vs GraphRAG

- [image 0]: Architecture diagram showing parallel retrieval flow
- [image 2]: Benchmark table — LightRAG at 30.2% accuracy vs GraphRAG 24.7%
```

(Image 1 had an empty description from describe_images and is OMITTED — indices 0 and 2 are preserved, NOT renumbered to 0 and 1.)

Inserted via: `await rag.ainsert(content, ids=["wechat_abc1234567_images"])`.

### 3. Orchestrator drain (batch_ingest_from_spider.py:83-134)

```python
VISION_DRAIN_TIMEOUT = 120.0


async def _drain_pending_vision_tasks() -> None:
    pending = [
        t for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    if not pending:
        return
    logger.info("Draining %d pending Vision task(s) (%.0fs deadline; D-10.09)...",
                len(pending), VISION_DRAIN_TIMEOUT)
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=VISION_DRAIN_TIMEOUT,
        )
        logger.info("Vision tasks drained cleanly")
    except asyncio.TimeoutError:
        still_pending = [t for t in pending if not t.done()]
        logger.warning("Vision drain timeout — %d/%d task(s) still pending (cancelling)",
                       len(still_pending), len(pending))
        for t in still_pending:
            t.cancel()
        if still_pending:
            await asyncio.gather(*still_pending, return_exceptions=True)
```

Called from `finally:` of BOTH `run()` and `ingest_from_db()` BEFORE `rag.finalize_storages()`.

### 4. Test file: `tests/unit/test_vision_worker.py` (10 tests)

Worker behavior (7):
- `test_worker_calls_describe_then_subdoc_ainsert` — D-10.06
- `test_subdoc_content_header_and_format` — D-10.07
- `test_subdoc_omits_empty_descriptions` — D-10.07 omit-empty rule
- `test_subdoc_skipped_when_all_descriptions_empty` — D-10.07 zero-success short-circuit
- `test_worker_swallows_describe_exception` — D-10.08
- `test_worker_swallows_ainsert_exception` — D-10.08
- `test_worker_emits_batch_complete` — Phase 8 IMG-04 preservation

Orchestrator drain (3):
- `test_run_drains_pending_vision_tasks` — D-10.09 (batch run)
- `test_ingest_from_db_drains_pending_vision_tasks` — D-10.09 (db-replay path)
- `test_drain_timeout_cancels_stragglers` — D-10.09 timeout-cancel semantics

## Deviations from Plan

**Rule 1 auto-fix: none needed.** The plan flagged a potential need to update `ingest_article` to pass `filter_stats/download_input_count/download_failed` when spawning `_vision_worker_impl`. Inspection of ingest_wechat.py:798-806 showed plan 10-01 had already wired these kwargs correctly — no source change required. The plan's self-annotation ("plan 10-01 should have passed them — update plan 10-01 if needed via Rule 1 auto-fix at implementation time") was resolved at plan 10-01 time.

**Test-pattern adjustment:** Plan sketched `monkeypatch.setattr(batch_ingest_from_spider, "_get_kol_accounts", ...)` and `"fetch_recent_articles_for_account"` — neither symbol exists in the codebase. Real attachment points are `kol_config.FAKEIDS` + `spiders.wechat_spider.list_articles_with_digest as list_articles`. Tests adjusted accordingly; behavior covered is identical.

**Logger addition (Rule 2 — missing critical functionality):** `ingest_wechat.py` had no module-level logger. Worker uses `logger.warning(...)` and `logger.info(...)` per D-10.08. Added `import logging` and `logger = logging.getLogger(__name__)` at module top. This is a minimal, non-invasive change; all other code continues to use `print()` (no scope-creep).

## Regression Evidence

```
tests/unit/test_image_pipeline.py       22 passed
tests/unit/test_get_rag_contract.py      6 passed
tests/unit/test_rollback_on_timeout.py   4 passed
tests/unit/test_prebatch_flush.py        2 passed
tests/unit/test_scrape_first_classify.py 9 passed
tests/unit/test_text_first_ingest.py     8 passed
tests/unit/test_vision_worker.py        10 passed
────────────────────────────────────────────────
Cumulative:                             61 passed
```

All 3 smoke imports succeed. D-10.07 sub-doc id regression grep confirms presence at `ingest_wechat.py:252`.

## Phase 10 Status — CODE-COMPLETE

With plan 10-02 landed:

| Req      | Plan  | Status      |
|----------|-------|-------------|
| CLASS-01 | 10-00 | delivered   |
| CLASS-02 | 10-00 | delivered   |
| CLASS-03 | 10-00 | delivered   |
| CLASS-04 | 10-00 | delivered   |
| ARCH-01  | 10-01 | delivered   |
| ARCH-02  | 10-02 | delivered   |
| ARCH-03  | 10-02 | delivered   |
| ARCH-04  | 10-02 | delivered   |

## Handoff to Phase 11 (E2E Verification Gate)

Phase 11 needs to verify against a real LightRAG instance (no mocks) — the final milestone v3.1 gate:

1. **Semantic aquery on sub-doc:** ingest the GPT-5.5 fixture article, wait for the background Vision worker to complete (Phase 11 may add explicit `await task` since it controls the flow), then `rag.aquery("What does the architecture diagram show?", ...)` — response MUST cite image descriptions via the sub-doc cross-reference.
2. **benchmark_result.json:** record end-to-end timing breakdown (scrape + classify + parent ainsert + Vision worker + sub-doc ainsert) per CONTEXT § Phase 11 scope.
3. **Graph cross-doc link verification:** the sub-doc and parent doc have distinct doc_ids but share `article_hash` in their identifiers. LightRAG's entity resolver should link them automatically via shared entity names (e.g., "GPT-5.5", "OpenAI") appearing in both texts. Phase 11 should confirm this.
4. **Vision failure path (D-10.08 live):** temporarily break the Vision cascade (e.g., `VISION_PROVIDER=nonsense`) and confirm: parent doc is queryable, no error propagates, warning log is emitted, batch completes.
5. **Drain timeout (D-10.09 live):** ingest a large batch (>30 articles) and confirm the drain log fires with "Vision tasks drained cleanly" before finalize_storages.

## Self-Check: PASSED

- ingest_wechat.py:190-272 — `_vision_worker_impl` full body present (no stub).
- ingest_wechat.py:252 — `sub_doc_id = f"wechat_{article_hash}_images"` present.
- batch_ingest_from_spider.py:83-134 — `VISION_DRAIN_TIMEOUT` + `_drain_pending_vision_tasks` present.
- batch_ingest_from_spider.py:669 + :898 — both `finally:` blocks call `_drain_pending_vision_tasks()` before `rag.finalize_storages()`.
- tests/unit/test_vision_worker.py — 10 tests, all pass.
- Commits: `93d8c58`, `e6f11dc` — both present in `git log --oneline`.
- Cumulative regression: 61 passed (22 + 6 + 4 + 2 + 9 + 8 + 10).
