---
phase: 04-knowledge-enrichment-zhihu
plan: 01
subsystem: image-pipeline
tags: [refactor, tdd, image-handling, python]
dependency_graph:
  requires: [04-00]
  provides: [image_pipeline.py, tests/unit/test_image_pipeline.py, tests/integration/test_image_pipeline_golden.py]
  affects: [ingest_wechat.py, future zhihu ingestion path]
tech_stack:
  added: []
  patterns: [atomic-write-tmp-rename, batch-rate-limited-api-calls, tdd-red-green]
key_files:
  created:
    - image_pipeline.py
    - tests/unit/test_image_pipeline.py
    - tests/integration/test_image_pipeline_golden.py
  modified:
    - ingest_wechat.py
decisions:
  - "describe_images batch API rate-limits internally with 4s sleep (D-15) — callers never manage rate-limiting"
  - "ingest_pdf also updated to use describe_images([path]) to remove last reference to deleted describe_image()"
  - "golden regression uses structural invariants only by default (no live Gemini); GOLDEN_REDESCRIBE=1 for live re-describe"
metrics:
  duration: ~25min
  completed: "2026-04-27T15:21:17Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 1
---

# Phase 4 Plan 01: Image Pipeline Refactor Summary

**One-liner:** Extracted WeChat image download/describe/localize/save logic into `image_pipeline.py` with 4 public functions, rate-limited batch describe, and atomic writes — shared by WeChat and future Zhihu ingestion (D-15, D-16).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1.1 | Create image_pipeline.py (TDD) | c4c5a35 | image_pipeline.py, tests/unit/test_image_pipeline.py |
| 1.2 | Refactor ingest_wechat.py | 19cb925 | ingest_wechat.py |
| 1.3 | Golden-file regression test | 2175d4a | tests/integration/test_image_pipeline_golden.py |

## Verification Results

- `pytest tests/unit/test_image_pipeline.py -x`: 5/5 passed
- `pytest tests/integration/test_image_pipeline_golden.py -v`: 3/3 passed (all 3 golden fixtures: 3738bfe579, 8ac04218b4, c5e5a98589)
- `grep "^def describe_image" ingest_wechat.py`: no match (function removed)
- `grep "from image_pipeline import" ingest_wechat.py`: present
- `python -c "import ast; ast.parse(open('ingest_wechat.py', encoding='utf-8').read())"`: exits 0

## Must-Haves Check

- [x] `image_pipeline.py` exports exactly 4 functions: `download_images`, `localize_markdown`, `describe_images`, `save_markdown_with_images`
- [x] `describe_images` is batch: accepts a list, rate-limits internally with `time.sleep(4)` between calls
- [x] `ingest_wechat.py` uses `image_pipeline` for all image work (no duplicate logic)
- [x] Golden regression passes for all 3 fixtures (idempotency + structural invariants)
- [x] Each of the 4 public functions has a dedicated unit test (5 tests total — extra test for `describe_images` error isolation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ingest_pdf's broken reference to deleted describe_image()**
- **Found during:** Task 1.2
- **Issue:** `ingest_pdf()` called `describe_image(img_path)` which we deleted from the file. Leaving it would break PDF ingestion with `NameError: name 'describe_image' is not defined`.
- **Fix:** Updated `ingest_pdf` to call `describe_images([Path(img_path)]).get(Path(img_path), "")` — uses the batch API with a single-item list.
- **Files modified:** ingest_wechat.py (same commit as Task 1.2)
- **Commit:** 19cb925

**2. [Rule 1 - Bug] Removed PIL import made orphan by describe_image deletion**
- **Found during:** Task 1.2
- **Issue:** `from PIL import Image` was only used by the deleted `describe_image` function. Leaving it would create an unused import that could cause ImportError if PIL is not installed.
- **Fix:** Removed the import per Surgical Changes principle (we made it orphaned).
- **Files modified:** ingest_wechat.py
- **Commit:** 19cb925

### Plan Threshold Adjustment

The prior_plan_context noted all 3 golden fixtures have `metadata.images == 2` (not >= 3 as the plan's original threshold implied). The regression test uses `len(baseline_meta.get("images", []))` as the ground truth rather than a hardcoded minimum — each fixture validates exactly the count it has. This matches the executor note to use `>= 1` tolerance.

## Known Stubs

None. All 4 functions are fully implemented with real logic.

## Self-Check: PASSED

- FOUND: image_pipeline.py
- FOUND: tests/unit/test_image_pipeline.py
- FOUND: tests/integration/test_image_pipeline_golden.py
- FOUND: commit c4c5a35 (Task 1.1)
- FOUND: commit 19cb925 (Task 1.2)
- FOUND: commit 2175d4a (Task 1.3)
