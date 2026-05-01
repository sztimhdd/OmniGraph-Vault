---
phase: 10-classification-and-ingest-decoupling
plan: 02
type: execute
wave: 3
depends_on: ["10-01"]
files_modified:
  - ingest_wechat.py
  - batch_ingest_from_spider.py
  - tests/unit/test_vision_worker.py
autonomous: true
requirements: [ARCH-02, ARCH-03, ARCH-04]

must_haves:
  truths:
    - "_vision_worker_impl runs describe_images on url_to_path, builds a markdown sub-doc with successful descriptions only, and calls rag.ainsert with doc_id=f'wechat_{article_hash}_images'"
    - "Sub-doc content header is exactly '# Images for <title>' followed by a blank line then markdown list items '- [image N]: <description>'"
    - "Successful descriptions only: images where describe_images returned '' (empty) are OMITTED from the sub-doc"
    - "Empty sub-doc short-circuit: if zero successful descriptions, rag.ainsert for the sub-doc is NOT called; an info log line is emitted instead"
    - "All exceptions inside _vision_worker_impl are caught and logged; they do NOT propagate to the parent (parent doc already ainserted successfully per plan 10-01)"
    - "emit_batch_complete is called from the worker with provider_mix + vision_error counts — preserves Phase 8 IMG-04 aggregate log"
    - "Batch orchestrator drains pending Vision tasks with a 120s aggregate deadline before finalize_storages (no leaked tasks at process exit, D-10.09)"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Full _vision_worker_impl implementation — replaces plan 10-01 stub"
      contains: "# Images for"
    - path: "batch_ingest_from_spider.py"
      provides: "Vision task drain in run() + ingest_from_db() finally blocks before finalize_storages"
      contains: "asyncio.all_tasks"
    - path: "tests/unit/test_vision_worker.py"
      provides: "7+ unit tests gating D-10.06 / D-10.07 / D-10.08 / D-10.09"
      min_lines: 200
  key_links:
    - from: "_vision_worker_impl"
      to: "image_pipeline.describe_images"
      via: "synchronous call inside worker (wrapped in try/except per D-10.08)"
      pattern: "describe_images\\(.*\\)"
    - from: "_vision_worker_impl"
      to: "rag.ainsert (sub-doc)"
      via: "await rag.ainsert(subdoc_content, ids=[f'wechat_{hash}_images'])"
      pattern: "ids=\\[f['\\\"]wechat_.*_images"
    - from: "batch_ingest_from_spider.run + ingest_from_db"
      to: "pending Vision tasks on the loop"
      via: "asyncio.all_tasks() filter + asyncio.wait_for(asyncio.gather(...), timeout=120)"
      pattern: "asyncio\\.all_tasks"
---

<objective>
Fill in the `_vision_worker_impl` stub from plan 10-01 with the actual Vision cascade + sub-doc
ainsert + failure-tolerant exception handling. Wire the batch orchestrator to drain pending
Vision tasks before `finalize_storages` so no Vision work is lost at batch end.

Purpose: unblock Phase 10 REQs ARCH-02 (async Vision worker), ARCH-03 (append sub-doc), ARCH-04
(Vision failure does not invalidate text ingest). Completes the Phase 10 decoupling — text
ingest already returns fast (plan 10-01); this plan makes the sub-doc actually queryable.

Output: modified `_vision_worker_impl` with full sub-doc construction + failure handling;
modified `batch_ingest_from_spider.{run, ingest_from_db}` with a pending-task drain in the
finally block; 7+ unit tests gating the four behaviors.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/10-classification-and-ingest-decoupling/10-CONTEXT.md
@.planning/phases/10-classification-and-ingest-decoupling/10-PRD.md
@.planning/phases/10-classification-and-ingest-decoupling/10-01-text-first-ingest-split-PLAN.md
@ingest_wechat.py
@batch_ingest_from_spider.py
@image_pipeline.py

<interfaces>
<!-- Contracts the executor needs. -->

From `ingest_wechat.py` AFTER plan 10-01 lands:
```python
# Stub created in plan 10-01, replaced by this plan:
async def _vision_worker_impl(
    *,
    rag,                            # LightRAG instance with AsyncMock-compatible ainsert
    article_hash: str,              # used for sub-doc doc_id
    url_to_path: dict[str, Path],   # image path list source
    title: str,                     # for sub-doc header line
) -> None: ...
```

From `image_pipeline.py` (UNCHANGED by this plan — just called from the worker):
```python
def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Returns {path: description}. Failed images have empty string."""

def get_last_describe_stats() -> dict | None:
    """Returns stats from the most recent describe_images call, or None.
    Shape: {"provider_mix": {"gemini": N, "siliconflow": N, "openrouter": N},
            "vision_success": int, "vision_error": int, "vision_timeout": int}
    """

def emit_batch_complete(*, filter_stats, download_input_count, download_failed,
                        describe_stats, total_ms) -> None: ...
```

Sub-doc content spec (D-10.07 LOCKED — copy verbatim):
```
# Images for <title>

- [image 0]: <description>
- [image 1]: <description>
- [image 3]: <description>
(note the gap — image 2 had empty description, OMITTED per D-10.07)
```

Sub-doc `doc_id` (D-10.07 LOCKED):
```python
sub_doc_id = f"wechat_{article_hash}_images"
```

Batch orchestrator drain sketch (D-10.09) — added to BOTH `run` and `ingest_from_db` in
`batch_ingest_from_spider.py`, in the existing `finally:` block, BEFORE `rag.finalize_storages()`:
```python
finally:
    if rag is not None:
        # D-10.09: drain pending Vision worker tasks before flushing storages.
        # Without this, sub-doc ainsert may be lost if finalize_storages runs mid-ainsert.
        pending = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if pending:
            logger.info("Draining %d pending Vision tasks (120s deadline)...", len(pending))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=120,
                )
                logger.info("Vision tasks drained cleanly")
            except asyncio.TimeoutError:
                # Count again after timeout — some may have completed
                still_pending = [t for t in pending if not t.done()]
                logger.warning(
                    "Vision drain timeout — %d/%d tasks still pending (will be cancelled)",
                    len(still_pending), len(pending),
                )
                for t in still_pending:
                    t.cancel()
        logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
        await rag.finalize_storages()
```

Test pattern — awaiting the Vision task explicitly:
```python
# Given a mocked rag with ainsert = AsyncMock()
task = await ingest_wechat.ingest_article(url, rag=mock_rag)
if task is not None:
    await task  # deterministically wait for Vision worker to finish
# Now assert on mock_rag.ainsert.call_args_list (2 calls: parent + sub-doc)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fill in _vision_worker_impl with describe_images + sub-doc ainsert + failure tolerance</name>
  <files>ingest_wechat.py, tests/unit/test_vision_worker.py</files>
  <behavior>
    Unit tests (RED first) in tests/unit/test_vision_worker.py:
    - test_worker_calls_describe_then_subdoc_ainsert: mock describe_images to return {Path("a.jpg"): "desc A", Path("b.jpg"): "desc B"}; mock rag.ainsert = AsyncMock() → await _vision_worker_impl(rag, "hash1", {"url_a": Path("a.jpg"), "url_b": Path("b.jpg")}, "My Title") → assert rag.ainsert was awaited exactly once, with ids=["wechat_hash1_images"]
    - test_subdoc_content_header_and_format: same setup → capture the first positional arg of ainsert; assert it starts with "# Images for My Title\n\n" and contains "- [image 0]: desc A" AND "- [image 1]: desc B"
    - test_subdoc_omits_empty_descriptions: describe_images returns {Path("a.jpg"): "desc A", Path("b.jpg"): "", Path("c.jpg"): "desc C"} → captured sub-doc content contains "[image 0]: desc A" and "[image 2]: desc C" and does NOT contain "[image 1]:" (empty desc omitted per D-10.07; index preserved — NOT renumbered)
    - test_subdoc_skipped_when_all_descriptions_empty: describe_images returns {path: "" for all} → rag.ainsert is NOT called; a log line "vision_subdoc_skipped" or similar is emitted (captured via caplog fixture)
    - test_worker_swallows_describe_exception: mock describe_images to raise RuntimeError("all providers down") → worker returns None (no exception propagates); caplog has a warning-level entry referencing the error; rag.ainsert was NOT called
    - test_worker_swallows_ainsert_exception: describe_images succeeds → but rag.ainsert raises on the sub-doc call → worker returns None (no exception propagates); caplog has a warning-level entry
    - test_worker_emits_batch_complete: describe_images returns mixed success/empty → verify emit_batch_complete was called with a non-None describe_stats argument (use a patch + spy; Phase 8 IMG-04 aggregate log must still fire from the worker)
  </behavior>
  <action>
    1. Replace the stub body of `_vision_worker_impl` in `ingest_wechat.py` with:
    ```python
    async def _vision_worker_impl(
        *,
        rag,
        article_hash: str,
        url_to_path: dict,
        title: str,
    ) -> None:
        """Background Vision worker — D-10.06 (ARCH-02).

        Describes all images in url_to_path, builds a single image sub-doc via
        ainsert (D-10.07 ARCH-03), and tolerates all failures without propagating
        (D-10.08 ARCH-04).

        Called via asyncio.create_task from ingest_article AFTER parent doc ainsert
        returns. The parent doc is already queryable by the time this runs; sub-doc
        failure never invalidates parent.
        """
        import time as _time
        from pathlib import Path as _Path

        t0 = _time.perf_counter()
        try:
            # D-10.06 Step 1: describe images (can raise — caught by outer try/except)
            paths_list = list(url_to_path.values())
            descriptions = describe_images(paths_list)
            describe_stats = get_last_describe_stats()

            # D-10.07 Step 2: build sub-doc content from successful descriptions only
            lines = [f"# Images for {title}", ""]
            successful = 0
            for i, (url_img, path) in enumerate(url_to_path.items()):
                desc = descriptions.get(path, "")
                if desc and desc.strip():
                    lines.append(f"- [image {i}]: {desc}")
                    successful += 1
                # else: D-10.07 — omit empty/failed descriptions (index NOT renumbered)

            if successful == 0:
                logger.info(
                    "vision_subdoc_skipped article_hash=%s reason=%s",
                    article_hash,
                    "no_images" if not url_to_path else "all_failed",
                )
                # Still emit batch_complete for observability
                # Note: emit_batch_complete requires a FilterStats; if we don't have one
                # here (it was owned by ingest_article pre-split), skip it — the
                # aggregate log is about the IMAGE FILTER phase, which happened pre-split.
                # Alternative: emit a distinct "vision_batch_complete" log for the worker.
                _emit_vision_log(
                    article_hash=article_hash,
                    describe_stats=describe_stats,
                    total_ms=int((_time.perf_counter() - t0) * 1000),
                    subdoc_inserted=False,
                )
                return None

            sub_doc_content = "\n".join(lines) + "\n"
            sub_doc_id = f"wechat_{article_hash}_images"

            # D-10.06 Step 3: append sub-doc via ainsert (D-10.07 — NOT re-embed)
            await rag.ainsert(sub_doc_content, ids=[sub_doc_id])

            _emit_vision_log(
                article_hash=article_hash,
                describe_stats=describe_stats,
                total_ms=int((_time.perf_counter() - t0) * 1000),
                subdoc_inserted=True,
                subdoc_image_count=successful,
            )

        except Exception as exc:  # D-10.08: swallow ALL exceptions; parent doc is safe
            logger.warning(
                "Vision worker failed for article_hash=%s: %s — text ingest unaffected",
                article_hash,
                exc,
                exc_info=True,
            )
            return None
    ```

    2. Add a small helper `_emit_vision_log` in `ingest_wechat.py` to keep logging consistent:
    ```python
    def _emit_vision_log(
        *,
        article_hash: str,
        describe_stats: dict | None,
        total_ms: int,
        subdoc_inserted: bool,
        subdoc_image_count: int = 0,
    ) -> None:
        """Structured log for Phase 10 Vision worker completion (separate from Phase 8 image_batch_complete).

        Keeps IMG-04 (image filter/download aggregate) separate from ARCH-02 (Vision worker aggregate).
        """
        import json as _json
        payload = {
            "event": "vision_worker_complete",
            "article_hash": article_hash,
            "subdoc_inserted": subdoc_inserted,
            "subdoc_image_count": subdoc_image_count,
            "total_ms": total_ms,
            "describe_stats": describe_stats or {},
        }
        logger.info("vision_worker_complete %s", _json.dumps(payload, ensure_ascii=False))
    ```
    Rationale: Phase 8 `emit_batch_complete` owns the `image_batch_complete` event (filter + download
    counts). The Vision worker introduces a DISTINCT event `vision_worker_complete` — separating them
    avoids muddling two pipeline stages that now run on different timelines. If the Phase 11 benchmark
    expects a single unified log, planner can adjust; for v3.1 Phase 10 gate, two events is cleaner.

    3. Do NOT re-add `emit_batch_complete` from `image_pipeline` to the worker — `ingest_article`
    already emits that (for filter/download stats) right after `filter_small_images`. That emission
    point stays in `ingest_article` pre-ainsert.

    Wait — re-check plan 10-01: plan 10-01 says to REMOVE `emit_batch_complete` from the inline
    location and move it to the worker. Reconcile: D-10.07 sub-doc emission + D-08.02 batch complete
    semantics. Resolution: Phase 8 IMG-04's `image_batch_complete` covers filter + download + describe
    in its CURRENT form. Under Phase 10-01 the describe_stats are not available at the old emission
    point (describe hasn't run yet by the time parent ainsert completes). Decision:
      - Move `emit_batch_complete` call INTO the Vision worker (this plan). Keep `filter_stats` +
        `download_input_count` + `download_failed` as kwargs on the worker (plan 10-01 should have
        passed them — update plan 10-01 if needed via Rule 1 auto-fix at implementation time, OR
        pass them as additional _vision_worker_impl kwargs in this plan and also update plan 10-01's
        ingest_article to forward them).
      - The worker calls `emit_batch_complete(filter_stats=<forwarded>, download_input_count=<forwarded>,
        download_failed=<forwarded>, describe_stats=get_last_describe_stats(), total_ms=...)`.
      - Remove `_emit_vision_log` helper above OR keep it for the zero-images short-circuit (where
        `emit_batch_complete` still needs filter_stats, which exists). Simpler: keep
        `emit_batch_complete` as the sole aggregate log emission in the worker, covering both
        success and failure paths. Drop `_emit_vision_log`.

    **Final shape: emit_batch_complete inside the worker** (unified with Phase 8 IMG-04):
    ```python
    async def _vision_worker_impl(
        *,
        rag,
        article_hash: str,
        url_to_path: dict,
        title: str,
        filter_stats,                # Phase 8 FilterStats — forwarded from ingest_article
        download_input_count: int,
        download_failed: int,
    ) -> None:
        import time as _time
        t0 = _time.perf_counter()
        describe_stats = None
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

            if successful > 0:
                sub_doc_content = "\n".join(lines) + "\n"
                sub_doc_id = f"wechat_{article_hash}_images"
                await rag.ainsert(sub_doc_content, ids=[sub_doc_id])
            else:
                logger.info(
                    "vision_subdoc_skipped article_hash=%s reason=%s",
                    article_hash,
                    "no_images" if not url_to_path else "all_failed",
                )

        except Exception as exc:  # D-10.08
            logger.warning(
                "Vision worker failed for article_hash=%s: %s — text ingest unaffected",
                article_hash, exc, exc_info=True,
            )
        finally:
            # Phase 8 IMG-04 aggregate log — always fires, covering success + failure.
            try:
                emit_batch_complete(
                    filter_stats=filter_stats,
                    download_input_count=download_input_count,
                    download_failed=download_failed,
                    describe_stats=describe_stats,
                    total_ms=int((_time.perf_counter() - t0) * 1000),
                )
            except Exception:
                pass  # log emission failure is not fatal
    ```

    4. Update `ingest_article` (plan 10-01 output) to PASS the additional kwargs when spawning
    the task. This is a Rule 1 auto-fix against plan 10-01's `_vision_worker_impl` call site:
    ```python
    vision_task = None
    if url_to_path:
        vision_task = asyncio.create_task(_vision_worker_impl(
            rag=rag,
            article_hash=article_hash,
            url_to_path=url_to_path,
            title=title,
            filter_stats=filter_stats,           # from filter_small_images call earlier
            download_input_count=len(unique_img_urls),
            download_failed=download_failed,
        ))
    ```
    These variables already exist in `ingest_article` scope from the Phase 8 `filter_small_images`
    + `download_images` calls — just forward them.

    5. Write 7 behavior tests above. Use pytest's `caplog` fixture for log assertions. Use `patch("ingest_wechat.describe_images", ...)` and `patch("ingest_wechat.get_last_describe_stats", ...)` to mock the image_pipeline side. For `filter_stats` kwarg in the worker tests, pass a dummy FilterStats dataclass instance (import from image_pipeline).

    Per D-10.06, D-10.07, D-10.08.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_vision_worker.py -v -k "worker"</automated>
  </verify>
  <done>7 behavior tests pass. `_vision_worker_impl` is fully implemented (no stub). Sub-doc content shape matches D-10.07 verbatim. Exceptions never propagate. emit_batch_complete fires in the worker's finally block.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Batch orchestrator drain — gather pending Vision tasks before finalize_storages (D-10.09)</name>
  <files>batch_ingest_from_spider.py, tests/unit/test_vision_worker.py</files>
  <behavior>
    Unit tests (RED first) appended to tests/unit/test_vision_worker.py:
    - test_run_drains_pending_vision_tasks: stub the `run` flow with a single article + mocked rag; ingest_article returns an asyncio.Task that takes 0.5s to complete; run to completion → assert asyncio.wait_for with timeout=120 was called on gather(*pending) before finalize_storages; the Vision task completed (task.done() is True after drain)
    - test_ingest_from_db_drains_pending_vision_tasks: same pattern for ingest_from_db
    - test_drain_timeout_cancels_stragglers: mock a Vision task that sleeps 200s (>120s) → drain wait_for raises TimeoutError → the code path cancels the still-pending tasks and proceeds to finalize_storages; assert task.cancelled() is True; assert rag.finalize_storages was still called
  </behavior>
  <action>
    1. In `batch_ingest_from_spider.py`, modify the `finally:` block of `run()` (around line 589-593):
    ```python
    finally:
        if rag is not None:
            # D-10.09: drain pending Vision worker tasks before flushing storages.
            # Without this, sub-doc ainsert may be lost if finalize_storages runs
            # mid-ainsert. 120s aggregate deadline per CONTEXT D-10.09.
            pending = [
                t for t in asyncio.all_tasks()
                if t is not asyncio.current_task() and not t.done()
            ]
            if pending:
                logger.info("Draining %d pending Vision tasks (120s deadline; D-10.09)...", len(pending))
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=120,
                    )
                    logger.info("Vision tasks drained cleanly")
                except asyncio.TimeoutError:
                    still_pending = [t for t in pending if not t.done()]
                    logger.warning(
                        "Vision drain timeout — %d/%d tasks still pending (cancelling)",
                        len(still_pending), len(pending),
                    )
                    for t in still_pending:
                        t.cancel()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()
    ```

    2. Apply the identical pattern to `ingest_from_db()`'s `finally:` block (around line 691-695),
    replacing its existing `finalize_storages` call.

    3. Write the 3 orchestrator drain tests. Use `asyncio.Event` + `asyncio.sleep` inside fake
    Vision worker tasks to control timing deterministically. Mock ingest_article to return a task
    pre-spawned by the test with a controlled duration.

    4. CAVEAT to document in test + commented in source: `asyncio.all_tasks()` returns ALL tasks
    on the loop — including any tests' own tasks, the main coroutine, etc. The filter
    `t is not asyncio.current_task() and not t.done()` narrows to external tasks. In test context,
    if the test uses `asyncio.run(...)`, `current_task` is the test's entry coroutine, so only
    the Vision-worker task (the one we want) survives the filter — this is why the tests are
    deterministic. In production context this is also safe because only Vision workers and the
    orchestrator coroutine are live on the loop.

    Per D-10.09 (architectural discretion pre-resolved in CONTEXT).
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_vision_worker.py -v</automated>
  </verify>
  <done>All 10 tests in test_vision_worker.py (7 worker behavior + 3 orchestrator drain) pass. `batch_ingest_from_spider.run` and `.ingest_from_db` both drain pending tasks with a 120s aggregate deadline before `finalize_storages`. Straggler tasks are cancelled on deadline miss; `finalize_storages` still runs.</done>
</task>

<task type="auto">
  <name>Task 3: Full Phase 10 regression — Phase 8 + 9 + 10-00 + 10-01 + 10-02 all green</name>
  <files>(no source changes — verification only)</files>
  <action>
    1. Phase 8 regression (MUST stay 22/22 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v
    ```

    2. Phase 9 regression (MUST stay 12/12 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py -v
    ```

    3. Phase 10-00 regression (MUST stay 8/8 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_scrape_first_classify.py -v
    ```

    4. Phase 10-01 regression (MUST stay 6/6 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_text_first_ingest.py -v
    ```

    5. Phase 10-02 new tests (MUST all pass):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_vision_worker.py -v
    ```

    6. Smoke imports:
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import image_pipeline; print('OK')"
    ```

    7. Source-grep D-10.07 sub-doc id pattern (regression guard):
    ```
    grep -n "wechat_.*_images" ingest_wechat.py
    ```
    Must find the `f"wechat_{article_hash}_images"` line in `_vision_worker_impl`.

    8. If any regression fails → STOP + fix in place (Rule 1 auto-fix). Do not mark plan complete
    until all 58 tests (22 + 12 + 8 + 6 + 10) are green.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py tests/unit/test_scrape_first_classify.py tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py -v</automated>
  </verify>
  <done>Cumulative: 22 + 12 + 8 + 6 + 10 = 58 tests pass. All 3 smoke imports succeed. Phase 10 is code-complete — ready for Phase 11 E2E verification gate.</done>
</task>

</tasks>

<verification>
Phase 10 plan 10-02 acceptance (D-10.06 / D-10.07 / D-10.08 / D-10.09):

1. **D-10.06 (async Vision worker):** test_worker_calls_describe_then_subdoc_ainsert + test_subdoc_content_header_and_format verify the worker calls describe_images and inserts a sub-doc with doc_id=wechat_{hash}_images.
2. **D-10.07 (sub-doc shape, omit empty):** test_subdoc_content_header_and_format + test_subdoc_omits_empty_descriptions + test_subdoc_skipped_when_all_descriptions_empty verify the exact content shape and the "omit empty descriptions; skip entirely if all empty" rule.
3. **D-10.08 (failure tolerance):** test_worker_swallows_describe_exception + test_worker_swallows_ainsert_exception verify no exception propagates; parent doc unaffected.
4. **D-10.09 (task drain):** test_run_drains_pending_vision_tasks + test_ingest_from_db_drains_pending_vision_tasks + test_drain_timeout_cancels_stragglers verify the orchestrator drains pending Vision tasks before finalize_storages with a 120s aggregate deadline.
5. **Phase 8 IMG-04 preserved:** test_worker_emits_batch_complete verifies emit_batch_complete still fires (now from the worker's finally block).
6. **Regression:** Phase 8 + 9 + 10-00 + 10-01 cumulative 48 tests stay green.
</verification>

<success_criteria>
- `_vision_worker_impl` is fully implemented — no stub, no TODO (D-10.06)
- Sub-doc content matches D-10.07 spec verbatim (header, list format, empty-desc omission, skip-if-all-empty)
- All exceptions inside the worker are caught and logged; text ingest is never invalidated (D-10.08)
- `batch_ingest_from_spider.{run, ingest_from_db}` drains pending Vision tasks (120s deadline) before `finalize_storages` (D-10.09)
- 10 new unit tests pass (7 worker + 3 orchestrator); Phase 8/9/10-00/10-01 cumulative 48 tests stay green (total 58)
- `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v` reports no regressions
- Ready for Phase 11 E2E verification gate (semantic aquery on sub-doc + benchmark_result.json)
</success_criteria>

<output>
After completion, create `.planning/phases/10-classification-and-ingest-decoupling/10-02-SUMMARY.md` per the standard SUMMARY template. Document:
- Final `_vision_worker_impl` shape (kwargs-forwarded from ingest_article for filter_stats/download_input_count/download_failed)
- Sub-doc content verbatim example (1-2 images)
- Orchestrator drain pattern + 120s deadline rationale
- Any Rule 1 auto-fixes to plan 10-01's `_vision_worker_impl` call site (to pass additional kwargs)
- Clean handoff to Phase 11 (what Phase 11 needs to verify via aquery against a real LightRAG instance)
Commit SUMMARY separately from source changes. Close Phase 10 by updating ROADMAP.md's Phase 10 plan checkboxes from `[ ]` to `[x]`.
</output>
