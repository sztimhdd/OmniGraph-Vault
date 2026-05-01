---
phase: 10-classification-and-ingest-decoupling
plan: 01
type: execute
wave: 2
depends_on: ["10-00"]
files_modified:
  - ingest_wechat.py
  - tests/unit/test_text_first_ingest.py
autonomous: true
requirements: [ARCH-01]

must_haves:
  truths:
    - "ingest_article returns after rag.ainsert(full_content, ids=[parent_doc_id]) completes — NOT after describe_images"
    - "The body ainserted for the parent doc contains [Image N Reference]: <local_url> lines but NOT [Image N Description]: lines (descriptions arrive via sub-doc in plan 10-02)"
    - "ingest_article now returns asyncio.Task | None (Task handle if images present and Vision worker spawned; None if zero images)"
    - "Timing test: with describe_images mocked to sleep 60s, ingest_article returns in <5s"
    - "Phase 9 D-09.05 rollback registry (parent doc_id tracking + _register/_clear/get_pending_doc_id) remains intact and functional"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Split ingest_article: synchronous text ainsert (fast return) + asyncio.create_task for Vision worker (background, plan 10-02 fills in)"
      contains: "asyncio.create_task"
    - path: "tests/unit/test_text_first_ingest.py"
      provides: "5+ unit tests gating D-10.05 behavior (return type, timing, ainsert ordering, content shape)"
      min_lines: 150
  key_links:
    - from: "ingest_article (post-split)"
      to: "rag.ainsert (parent doc only — sub-doc comes from worker)"
      via: "single synchronous await before return"
      pattern: "await rag\\.ainsert\\(full_content, ids=\\[doc_id\\]\\)"
    - from: "ingest_article"
      to: "_vision_worker_impl (stub — body added in plan 10-02)"
      via: "asyncio.create_task(_vision_worker_impl(...))"
      pattern: "asyncio\\.create_task\\("
---

<objective>
Split `ingest_wechat.ingest_article` so that the text-ingest hot path (`rag.ainsert` of the
article body + image reference lines but WITHOUT image descriptions) returns fast. Vision
description work is moved behind an `asyncio.create_task(_vision_worker_impl(...))` call that
returns the task handle but does NOT block the return.

Purpose: unblock Phase 10 REQ ARCH-01 — "Text ingest synchronous-fast" — the root cause of
the current 2-min+ ingest latency on the gpt55 fixture. describe_images on 28 images serializes
Vision API calls; moving that off the hot path cuts text-ingest wall-clock to <20s.

Output: modified ingest_wechat.py where ingest_article returns an asyncio.Task handle (or None
if no images), a STUB `_vision_worker_impl` function (minimal body — plan 10-02 fills in sub-doc
ainsert + failure handling), and 5+ unit tests gating D-10.05 behavior.

This plan creates the SHAPE of the split. Plan 10-02 fills in the worker's actual Vision +
sub-doc logic. The stub in this plan returns immediately without doing any Vision work — tests
in this plan mock describe_images to observe timing and call ordering.
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
@.planning/phases/09-timeout-state-management/09-01-SUMMARY.md
@.planning/phases/10-classification-and-ingest-decoupling/10-00-scrape-first-classification-PLAN.md
@ingest_wechat.py
@image_pipeline.py

<interfaces>
<!-- Contracts the executor needs. -->

From `ingest_wechat.py` (Phase 9 state — what EXISTS now):
```python
_PENDING_DOC_IDS: dict[str, str] = {}
def _register_pending_doc_id(article_hash: str, doc_id: str) -> None: ...
def _clear_pending_doc_id(article_hash: str) -> None: ...
def get_pending_doc_id(article_hash: str) -> str | None: ...

async def get_rag(flush: bool = True) -> "LightRAG": ...

async def ingest_article(url, rag=None):
    # Current shape (Phase 9):
    #   1. scrape (UA → Apify → MCP/CDP cascade)
    #   2. download_images + filter_small_images
    #   3. describe_images  ← SERIALIZED Vision API calls (2 min on 28 images)
    #   4. Append "[Image N Description]: <desc>" lines to full_content
    #   5. extract_entities (DeepSeek)
    #   6. _register_pending_doc_id + rag.ainsert(full_content, ids=[doc_id])
    #   7. _clear_pending_doc_id
    #   8. cognee_wrapper.remember_article (swallow-all)
    #   9. save_markdown_with_images
    #   Returns: None
```

Current `full_content` shape (Phase 9, BEFORE Phase 10-01 split):
```
# <title>

URL: <url>
Time: <publish_time>

<body markdown with LOCALIZED image urls>

[Image 0 Reference]: http://localhost:8765/<hash>/img0.jpg
[Image 0 Description]: <vision description>

[Image 1 Reference]: http://localhost:8765/<hash>/img1.jpg
[Image 1 Description]: <vision description>
...
```

Target `full_content` shape AFTER Phase 10-01 (parent doc only — descriptions move to sub-doc):
```
# <title>

URL: <url>
Time: <publish_time>

<body markdown with LOCALIZED image urls>

[Image 0 Reference]: http://localhost:8765/<hash>/img0.jpg
[Image 1 Reference]: http://localhost:8765/<hash>/img1.jpg
...
```

Stub `_vision_worker_impl` signature (this plan creates, plan 10-02 implements):
```python
async def _vision_worker_impl(
    *,
    rag,                            # LightRAG instance
    article_hash: str,              # for sub-doc doc_id composition + registry key
    url_to_path: dict[str, Path],   # for describe_images call
    title: str,                     # for sub-doc markdown header
) -> None:
    """Plan 10-02 fills in: describe_images cascade + sub-doc ainsert + failure handling.
    This stub in plan 10-01 simply returns immediately — tests use mock rag anyway.
    """
    return None
```

describe_images (from image_pipeline.py — UNCHANGED by this plan):
```python
def describe_images(paths: list[Path]) -> dict[Path, str]: ...
def get_last_describe_stats() -> dict | None: ...
def emit_batch_complete(*, filter_stats, download_input_count, download_failed, describe_stats, total_ms) -> None: ...
```

D-10.05 return type contract:
```python
async def ingest_article(url: str, rag=None) -> "asyncio.Task | None":
    # Returns:
    #   - asyncio.Task if images present and Vision worker was spawned
    #   - None if zero images OR error occurred before spawn
```

Cache-hit branch (lines 596-637 in current ingest_wechat.py) — this branch currently ALSO runs
a truncated flow without Vision. Per D-10.05 it now MUST also return asyncio.Task | None. For
cache-hit, descriptions from the cached final_content.md are already embedded in the body —
NO Vision worker is spawned. Return None.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Split ingest_article so text ainsert returns fast (Vision worker spawned but not awaited)</name>
  <files>ingest_wechat.py, tests/unit/test_text_first_ingest.py</files>
  <behavior>
    Unit tests (RED first) in tests/unit/test_text_first_ingest.py:
    - test_ingest_article_returns_task_when_images_present: mock scrape_wechat_ua to return 3 img_urls; mock download_images to return 3 paths; mock rag as MagicMock with AsyncMock ainsert; mock describe_images to sleep 60s but we patch _vision_worker_impl to a no-op async → assert returned value is an asyncio.Task (or awaitable), not None, not None-from-coroutine
    - test_ingest_article_returns_none_when_zero_images: mock scrape to return empty img_urls → no Vision worker spawned → returns None
    - test_ingest_article_returns_fast_with_slow_vision: patch describe_images with a real sleep(60) (inside the _vision_worker_impl test stub) → time.monotonic() the ingest_article call → assert elapsed < 5 seconds (the Vision worker runs in background; parent doc ainsert already completed)
    - test_parent_ainsert_content_has_references_not_descriptions: mock rag.ainsert as AsyncMock; run ingest_article with 2 images → assert the ainsert call's content argument contains "[Image 0 Reference]:" AND "[Image 1 Reference]:" AND does NOT contain "[Image 0 Description]:"
    - test_vision_worker_spawn_order_after_parent_ainsert: use a spy list to record call order; assert rag.ainsert (parent) is awaited BEFORE asyncio.create_task is called for the worker (i.e., the task spawn happens after parent ingest returns); the task itself may or may not have started executing by that point (event loop scheduling) — assert the CREATE_TASK line executes after the AWAIT line in the source flow
    - test_cache_hit_returns_none: pre-create the final_content.md cache file for the article's hash → run ingest_article → assert return value is None (cache-hit path does NOT spawn Vision worker)
  </behavior>
  <action>
    1. Create a STUB `_vision_worker_impl` in `ingest_wechat.py` (plan 10-02 will replace the body):
    ```python
    # D-10.06 (ARCH-02): async Vision worker. Plan 10-01 creates this as a stub.
    # Plan 10-02 fills in: describe_images cascade + sub-doc ainsert (D-10.07) +
    # failure-tolerant exception handling (D-10.08).
    async def _vision_worker_impl(
        *,
        rag,
        article_hash: str,
        url_to_path: dict,
        title: str,
    ) -> None:
        """STUB — plan 10-02 implements. Returns immediately."""
        return None
    ```

    2. Modify `ingest_article` in `ingest_wechat.py` — the MAIN (non-cache) branch (lines ~580-810):
       - Keep scraping (UA → Apify → MCP/CDP) unchanged.
       - Keep `download_images` + `filter_small_images` calls unchanged (both are fast, synchronous, and MUST run before the parent ainsert because they determine which local URLs go into the parent body).
       - REMOVE the synchronous `describe_images(list(url_to_path.values()))` call from BEFORE the parent ainsert. Also REMOVE the `describe_stats = get_last_describe_stats()` and the `emit_batch_complete` call from this inline location — both move to the Vision worker in plan 10-02.
       - REMOVE the inline `for i, (url_img, path) in enumerate(url_to_path.items()):` loop that appends `[Image N Reference]: ...\n[Image N Description]: ...` lines. REPLACE with a simpler loop that appends ONLY reference lines:
       ```python
       # Phase 10 D-10.05 (ARCH-01): parent doc body contains image REFERENCE lines only.
       # Image DESCRIPTIONS arrive via sub-doc (D-10.07, inserted by _vision_worker_impl
       # via asyncio.create_task below).
       for i, (url_img, path) in enumerate(url_to_path.items()):
           local_url = f"http://localhost:8765/{article_hash}/{path.name}"
           full_content += f"\n\n[Image {i} Reference]: {local_url}"
       ```
       Also DROP `processed_images` list from the parent ainsert path (it was previously populated inside the removed describe loop; save_markdown_with_images still wants it — see step 4 below).
       - Keep `extract_entities` and the entity_buffer write unchanged.
       - Keep the `_register_pending_doc_id` + `await rag.ainsert(full_content, ids=[doc_id])` + `_clear_pending_doc_id` trio unchanged (Phase 9 D-09.05 intact).
       - AFTER the parent ainsert completes (after `_clear_pending_doc_id`), add:
       ```python
       # D-10.05 / D-10.06: spawn Vision worker AFTER parent ainsert returns.
       # Worker fills in image descriptions via sub-doc (plan 10-02 implementation).
       # Returned task handle is passed up to the caller — tests await it;
       # production orchestrator does NOT await (fire-and-forget per D-10.09).
       vision_task = None
       if url_to_path:
           vision_task = asyncio.create_task(_vision_worker_impl(
               rag=rag,
               article_hash=article_hash,
               url_to_path=url_to_path,
               title=title,
           ))
       ```
       - Keep cognee_wrapper.remember_article (fire-and-forget, already swallow-all) and save_markdown_with_images. For save_markdown_with_images, pass `processed_images=[]` (empty list) — the sub-doc owns descriptions now; local metadata.json can remain minimal. Alternatively, populate `processed_images` with just reference entries (no descriptions):
       ```python
       processed_images = [
           {"index": i, "local_url": f"http://localhost:8765/{article_hash}/{p.name}"}
           for i, (_, p) in enumerate(url_to_path.items())
       ]
       ```
       - Change the function signature to explicitly document the new return:
       ```python
       async def ingest_article(url, rag=None) -> "asyncio.Task | None":
           """...
           Returns:
               asyncio.Task: if images present, the handle for the background Vision worker
                   that fills in image descriptions via a sub-doc (D-10.06).
               None: if zero images OR cache-hit path (descriptions already embedded).
           """
       ```
       - Return `vision_task` at the end of the function (not `None`).

    3. Modify the CACHE-HIT branch (lines ~596-637):
       - Cached final_content.md ALREADY contains descriptions from a previous run's Vision work. NO Vision worker is spawned. Keep the existing flow but ensure the function returns `None` explicitly at the end of the cache branch.
       - Do NOT change the cached content parsing.

    4. Modify `ingest_pdf` (lines ~812-888) similarly IF it has the same per-image describe-inline pattern — inspect and apply the same refactor (describe_images moved to a Vision worker; parent ainsert contains references only). Keep the same `asyncio.Task | None` return contract. Note: `ingest_pdf` is less load-bearing; planner may scope this to a documented TODO if time-constrained, but include a failing test in test_text_first_ingest.py to flag the gap.

    5. Write the 6 behavior tests above. Use `DEEPSEEK_API_KEY=dummy` + monkeypatch env. Mock:
       - `ingest_wechat.scrape_wechat_ua` via `patch("ingest_wechat.scrape_wechat_ua", new=AsyncMock(return_value={...}))` (build a minimal article_data dict)
       - `ingest_wechat.download_images` and `filter_small_images` via patch
       - `ingest_wechat.describe_images` — patch to a real `asyncio.sleep(60)` wrapper (used by the timing test)
       - `ingest_wechat.extract_entities` via AsyncMock returning `[]`
       - `ingest_wechat.cognee_wrapper.remember_article` via AsyncMock
       - `ingest_wechat.save_markdown_with_images` via MagicMock
       - `rag` parameter passed in as `MagicMock(spec=...)` with `ainsert = AsyncMock()`
       For the cache-hit test, create a temporary directory, set `BASE_IMAGE_DIR` via monkeypatch, write a dummy `<hash>/final_content.md` before calling `ingest_article`.

    Per D-10.05 (ARCH-01). Do NOT implement D-10.06 (worker body) or D-10.07 (sub-doc) in this plan — those are plan 10-02 scope. Stub-only.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_text_first_ingest.py -v</automated>
  </verify>
  <done>All 6 behavior tests pass. `ingest_article` returns `asyncio.Task | None`. Parent doc body contains "[Image N Reference]:" lines but NOT "[Image N Description]:" lines. Stub `_vision_worker_impl` exists (body = `return None`). Phase 9 rollback registry (`_register_pending_doc_id`, `get_pending_doc_id`) is UNCHANGED.</done>
</task>

<task type="auto">
  <name>Task 2: Regression verification — Phase 8 + Phase 9 + Phase 10-00 stay green</name>
  <files>(no source changes — verification only)</files>
  <action>
    1. Phase 8 regression (MUST stay 22/22 green — image_pipeline.py unchanged by this plan):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v
    ```
    2. Phase 9 regression (MUST stay 12/12 green — rollback registry untouched):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py -v
    ```
    3. Phase 10-00 regression (MUST stay green — scrape-first path unaffected by ingest_article signature change since the orchestrator uses the `batch_ingest_from_spider.ingest_article` wrapper which does not await the returned task):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_scrape_first_classify.py -v
    ```
    4. Smoke imports:
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import multimodal_ingest; print('OK')"
    ```
    5. Verify the Phase 9 `_register_pending_doc_id` / `get_pending_doc_id` symbols are still present (grep source):
    ```
    grep -n "_register_pending_doc_id\|_clear_pending_doc_id\|get_pending_doc_id" ingest_wechat.py
    ```
    All three must still exist. Rollback contract unchanged.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py tests/unit/test_scrape_first_classify.py tests/unit/test_text_first_ingest.py -v</automated>
  </verify>
  <done>Cumulative: 22 Phase-8 + 12 Phase-9 + 8 Phase-10-00 + 6 Phase-10-01 = 48 tests pass. All three smoke imports succeed. Rollback registry symbols still present.</done>
</task>

</tasks>

<verification>
Phase 10 plan 10-01 acceptance (D-10.05 / ARCH-01):

1. **Return type:** test_ingest_article_returns_task_when_images_present + test_ingest_article_returns_none_when_zero_images assert the Task | None contract.
2. **Timing:** test_ingest_article_returns_fast_with_slow_vision asserts <5s wall-clock even with 60s-sleeping describe_images — proves Vision is off the hot path.
3. **Content shape:** test_parent_ainsert_content_has_references_not_descriptions asserts no "[Image N Description]:" in the parent doc body.
4. **Ordering:** test_vision_worker_spawn_order_after_parent_ainsert asserts the `await rag.ainsert` completes BEFORE `asyncio.create_task` fires for the worker.
5. **Cache-hit:** test_cache_hit_returns_none asserts the cache-hit path (with pre-existing final_content.md) returns None (no new Vision worker).

Phase 8 + 9 + 10-00 regression stays GREEN.
</verification>

<success_criteria>
- `ingest_article` returns `asyncio.Task | None` (timing test + return-type tests pass)
- Parent doc body contains image references only; descriptions deferred to sub-doc (content-shape test passes)
- Stub `_vision_worker_impl` exists — plan 10-02 fills in its body
- 6 new unit tests pass, Phase 8/9/10-00 cumulative 42 tests stay green
- `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v` reports no regressions
</success_criteria>

<output>
After completion, create `.planning/phases/10-classification-and-ingest-decoupling/10-01-SUMMARY.md` per the standard SUMMARY template. Document:
- Content-shape change (references without descriptions in parent doc)
- Return-type change (asyncio.Task | None) and its implications for the batch orchestrator
- Any Rule 1 auto-fixes to downstream callers that relied on `ingest_article` returning None
- The stub `_vision_worker_impl` and its plan-10-02 fill-in plan
Commit SUMMARY separately from source changes.
</output>
