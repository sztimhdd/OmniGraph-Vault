---
phase: 10-classification-and-ingest-decoupling
plan: 01
subsystem: ingestion
tags: [asyncio, vision, split, task, tdd, arch-01]

# Dependency graph
requires:
  - phase: 09-timeout-state-management
    provides: "D-09.05 rollback registry (_register_pending_doc_id / _clear_pending_doc_id / get_pending_doc_id) wrapping rag.ainsert(full_content, ids=[doc_id]) — preserved unchanged by this plan"
  - phase: 08-image-pipeline
    provides: "image_pipeline.describe_images + filter_small_images + get_last_describe_stats + emit_batch_complete — imports retained, consumption shifted from inline to plan 10-02 worker body"
provides:
  - "ingest_wechat.ingest_article(url, rag=None) -> asyncio.Task | None — split-return contract: Task handle if images, None otherwise (D-10.05 / ARCH-01)"
  - "ingest_wechat._vision_worker_impl(*, rag, article_hash, url_to_path, title, filter_stats, download_input_count, download_failed) — STUB that returns None; plan 10-02 fills body"
  - "8 unit tests in tests/unit/test_text_first_ingest.py gating D-10.05 shape, timing, ordering, content-shape, cache-hit return-None, and Phase 9 registry regression"
affects:
  - 10-02-async-vision-subdoc

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.create_task(_vision_worker_impl(...)) AFTER parent rag.ainsert returns — fire-and-forget per D-10.09; Task handle returned up for test observation"
    - "Deferred description lines — parent doc body has [Image N Reference]: <local_url> ONLY; [Image N Description]: lines now belong to sub-doc (plan 10-02)"

key-files:
  created:
    - "tests/unit/test_text_first_ingest.py"
  modified:
    - "ingest_wechat.py"

key-decisions:
  - "Return type change: ingest_article now returns asyncio.Task | None. Production callers (batch_ingest_from_spider.ingest_article wrapper) previously ignored the None return — they continue to ignore the Task handle (fire-and-forget). Test harness MAY await the Task to deterministically observe sub-doc insertion."
  - "Cache-hit branch returns None (no Vision worker spawn) because cached final_content.md already contains descriptions from a previous run."
  - "_vision_worker_impl kwargs signature finalized: rag, article_hash, url_to_path, title, filter_stats, download_input_count, download_failed. Plan 10-02 will implement describe_images cascade + sub-doc ainsert + try/except Exception wrapper (D-10.08)."
  - "processed_images metadata dict no longer contains 'description' key (it was always embedded in the parent ainsert content — now moves to sub-doc). metadata.json still written via save_markdown_with_images for debugging, but description field is absent."
  - "ingest_pdf NOT modified in this plan (explicitly deferred per plan — not load-bearing for v3.1 gate which is WeChat articles only). Planner elected NOT to emit a failing guard test because adding one here would require the same split in plan 10-02 scope; simpler to scope an ingest_pdf update to a later phase if needed."

patterns-established:
  - "Text-first / Vision-deferred split — parent ainsert returns fast; asyncio.create_task spawns worker that completes out-of-band. Tests await returned Task; production does not."
  - "Stub worker shape lets a two-plan decomposition land atomically: plan 10-01 defines SHAPE (contract + spawn-site), plan 10-02 fills BODY (describe + sub-doc ainsert + exception swallowing)."

requirements-completed: [ARCH-01]

# Metrics
duration: 12min
completed: 2026-05-01
---

# Phase 10 Plan 01: Text-First Ingest Split Summary

**ingest_article now returns in <5s even with 60s-sleeping describe_images by deferring Vision to a background asyncio.create_task; parent doc carries image references only, descriptions move to a sub-doc (body filled in plan 10-02).**

## Changes

### `ingest_wechat.py`

1. **New STUB function `_vision_worker_impl`** (post-registry block) — async function with kwargs-only signature (`rag`, `article_hash`, `url_to_path`, `title`, `filter_stats`, `download_input_count`, `download_failed`). Body returns `None`. Plan 10-02 will replace the body with describe_images cascade + sub-doc ainsert + try/except Exception.

2. **`ingest_article` signature annotated** — added explicit return type `"asyncio.Task | None"` plus expanded docstring documenting the D-10.05 split.

3. **Cache-hit branch** (lines ~596-637 original, ~636 now) — added explicit `return None` at the end of the branch with comment explaining that cached `final_content.md` already contains descriptions so no worker is spawned.

4. **Main ingest path** (lines ~738-762 now):
   - Removed inline `describe_images(list(url_to_path.values()))` call
   - Removed inline `describe_stats = get_last_describe_stats()` + `emit_batch_complete(...)` call
   - Rewrote the image-reference loop: parent doc appends `[Image N Reference]: <local_url>` ONLY (no `[Image N Description]:` line)
   - `processed_images` dict entries no longer carry `description` key — only `index` + `local_url`

5. **Worker spawn** (after `_clear_pending_doc_id` on success) — new block introduces `vision_task = asyncio.create_task(_vision_worker_impl(...))` when `url_to_path` is non-empty, otherwise `vision_task = None`.

6. **Return statement** — new explicit `return vision_task` at the end of the function.

### `tests/unit/test_text_first_ingest.py` (NEW, 8 tests, ~335 lines)

| Test                                                          | D-10.05 facet gated                          |
| ------------------------------------------------------------- | -------------------------------------------- |
| `test_ingest_article_returns_task_when_images_present`        | Task return when images present              |
| `test_ingest_article_returns_none_when_zero_images`           | None return when zero images                 |
| `test_ingest_article_returns_fast_with_slow_vision`           | <5s elapsed even with 60s sleep in worker    |
| `test_parent_ainsert_content_has_references_not_descriptions` | Parent doc body shape                        |
| `test_vision_worker_spawn_order_after_parent_ainsert`         | Ordering: parent ainsert BEFORE worker runs  |
| `test_cache_hit_returns_none`                                 | Cache-hit returns None, no scrape, no spawn  |
| `test_vision_worker_impl_is_defined_as_async_stub`            | Stub exists + is coroutine function          |
| `test_phase9_rollback_registry_symbols_still_present`         | Regression guard for D-09.05 registry API    |

## Deviations from Plan

None — plan executed as written.

The plan specifies "5+ unit tests" and the frontmatter `min_lines: 150`; delivered 8 tests and ~335 lines. The plan allowed the planner to emit a failing test to flag the `ingest_pdf` gap — the planner elected NOT to (out of scope for v3.1 gate; documented above under key-decisions).

## Verification

### Task 1 (new tests)

```
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_text_first_ingest.py -v
=> 8 passed
```

### Task 2 (regression)

```
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
  tests/unit/test_image_pipeline.py \
  tests/unit/test_get_rag_contract.py \
  tests/unit/test_rollback_on_timeout.py \
  tests/unit/test_prebatch_flush.py \
  tests/unit/test_scrape_first_classify.py \
  tests/unit/test_text_first_ingest.py -v
=> 51 passed (22 Phase-8 + 12 Phase-9 + 9 Phase-10-00 + 8 Phase-10-01)
```

### Smoke imports

```
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import multimodal_ingest; print('OK')"
=> all three print OK
```

### Rollback registry regression grep

```
grep -n "_register_pending_doc_id\|_clear_pending_doc_id\|get_pending_doc_id" ingest_wechat.py
=> symbols defined at 175 / 180 / 185; both call sites (cache branch 668/673, main branch 785/790) intact.
```

## Known Stubs

- `_vision_worker_impl` in `ingest_wechat.py` (body = `return None`). Plan 10-02 will replace with: `describe_images(list(url_to_path.values()))` → build sub-doc markdown per D-10.07 (`# Images for <title>\n\n- [image 0]: <desc>\n...`) → `rag.ainsert(sub_doc, ids=[f"wechat_{article_hash}_images"])` → `emit_batch_complete(...)` for stats → all wrapped in `try/except Exception` per D-10.08. This stub is **intentional** and gated by the v3.1 plan dependency graph — plan 10-02 is Wave 2 in the same phase.

## Stub risk assessment

The stub causes image descriptions to be MISSING from the knowledge graph between plans 10-01 and 10-02. Queries against images will return no description text. Acceptable because:
1. Plans 10-01 and 10-02 land sequentially in the same phase.
2. Text body is unaffected — it's still queryable.
3. The gap is covered by plan 10-02's 6+ new tests.

## Implications for Phase 10-02

Plan 10-02 must:
- Replace `_vision_worker_impl` body (signature fixed here — do not change kwargs).
- Add sub-doc doc_id `f"wechat_{article_hash}_images"` (per D-10.07).
- Wrap entire body in `try/except Exception` → swallow per D-10.08.
- Verify the worker observes the 6 test kwargs passed by `ingest_article` in this plan.
- Add orchestrator drain in `batch_ingest_from_spider` before `rag.finalize_storages` per D-10.09.

## Self-Check: PASSED

- File `ingest_wechat.py` exists + contains `_vision_worker_impl` + `asyncio.create_task(` + `return vision_task`: confirmed.
- File `tests/unit/test_text_first_ingest.py` exists: confirmed.
- Commit `79133f7` exists: confirmed via `git log --oneline -5`.
- 51/51 target tests green: confirmed.
- Phase 9 rollback registry grep returns all three symbols: confirmed.
