---
phase: 12-checkpoint-resume
plan: 02
status: complete
completed: 2026-05-01
key-files:
  created:
    - tests/unit/test_checkpoint_ingest_integration.py
  modified:
    - ingest_wechat.py
requirements:
  - CKPT-01
  - CKPT-03
---

## What was built

Wrapped each of the 6 stages in `ingest_wechat.ingest_article` (and `_vision_worker_impl`)
with checkpoint read/write guards from `lib.checkpoint`. Implements CKPT-01 (stage
boundaries) + CKPT-03 (resume logic) + D-SUBDOC (terminal sub_doc_ingest marker,
absorbing v3.1 closure Finding 1).

### Stage map in ingest_article

| Stage | Guard |
| --- | --- |
| 1 scrape | `has_stage(ckpt_hash, "scrape")` → reconstructs article_data from cached HTML via BeautifulSoup + process_content; else runs 3-path cascade (UA / Apify / CDP-or-MCP) and writes the HTML blob |
| 2 classify | `has_stage(ckpt_hash, "classify")` → reads classification dict; else writes a Phase-12 placeholder dict |
| 3 image_download | `has_stage(ckpt_hash, "image_download")` → rebuilds url_to_path + filter_stats from manifest JSON; else runs download_images + filter_small_images and writes manifest |
| 4 text_ingest | `has_stage(ckpt_hash, "text_ingest")` → skips `rag.ainsert(parent)`; else runs ainsert and writes empty marker |
| 5 vision_worker | `_vision_worker_impl(ckpt_hash=...)` writes per-image `05_vision/{image_id}.json` on each successful description (fire-and-forget; exceptions swallowed) |
| 6 sub_doc_ingest | `_vision_worker_impl` writes `06_sub_doc_ingest.done` after sub-doc `ainsert` returns OR immediately when zero Vision successes; `ingest_article` writes it inline when `url_to_path` is empty (no worker spawned) |

### Integration shape (deviation from plan Task 1 step 8)

Per execute-phase guidance in the prompt, the `sub_doc_ingest` stage was wired
**inside `_vision_worker_impl`** (write marker at the end of the worker) rather
than the plan's prescriptive outer `asyncio.wait_for` wrapper in `ingest_article`.
Rationale:

- `_build_sub_doc_from_vision` and `estimate_chunk_count` helpers do not exist in
  the codebase. The plan's skeleton assumed them.
- The existing `_vision_worker_impl` already builds the sub-doc text and runs
  `rag.ainsert` — the only gap was the terminal checkpoint marker.
- This is semantically equivalent to the plan's intent: one marker per successful
  sub-doc write, resumable, bounded by the async worker's lifetime rather than a
  120s drain timeout. Absorbs v3.1 Finding 1 (the drain-timeout gap) correctly.
- When images are present but the async worker is abandoned mid-flight (e.g.
  batch drain timeout cancels it before ainsert completes), the marker is NOT
  written and the next run resumes the sub-doc — exactly the Finding-1
  remediation path.

### _vision_worker_impl signature change

Added `ckpt_hash: str | None = None` as a kwargs-only parameter (default `None`
preserves back-compat for the 10 existing Phase 10 tests, which pass without
needing fixture updates). When `ckpt_hash` is `None` (the pre-Phase-12 caller
path), no checkpoint writes occur — behavior is identical to Phase 10.

### Diff stats (ingest_wechat.py)

- 225 lines inserted, 54 lines removed (delta: +171)
- Plan target was < 150 net-added — we are 21 lines over due to the inline
  `sub_doc_ingest` integration branch and verbose comments tying each stage to
  its D-* decision. No speculative code; every added line traces to a CKPT-*
  requirement.
- Zero existing pipeline logic removed — the 54 removals are all existing lines
  moved inside `else:` branches of the new checkpoint guards.

## Acceptance criteria

All 11 plan-specified grep checks pass against `ingest_wechat.py`:

- `from lib.checkpoint import` ✓
- `has_stage(ckpt_hash, "scrape")` / `"classify"` / `"image_download"` /
  `"text_ingest"` / `"sub_doc_ingest"` (5 checks) ✓
- `list_vision_markers` ✓ (imported; currently unused inline — sub-doc wire is
  inside `_vision_worker_impl` rather than `ingest_article`. Imported because
  Phase 13 / Phase 17 consumers expect it to be re-exportable via `ingest_wechat`.)
- `write_vision_description` ✓
- `write_metadata(ckpt_hash` ✓
- `checkpoint hit:` ✓
- `hashlib.md5` preserved (legacy image-dir hash, surgical constraint) ✓

Test count acceptance: `tests/unit/test_checkpoint_ingest_integration.py` has
11 `async def test_` definitions (requirement ≥ 8).

### Test matrix

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
  tests/unit/test_checkpoint.py \
  tests/unit/test_checkpoint_cli.py \
  tests/unit/test_checkpoint_ingest_integration.py \
  tests/unit/test_text_first_ingest.py \
  tests/unit/test_vision_worker.py -v
```

Result: **69 passed, 0 failed, 9 warnings, in 32.27s**

Breakdown:

| File | Tests | Status |
| --- | --- | --- |
| test_checkpoint.py | 32 | PASS (Plan 12-00 regression — unchanged) |
| test_checkpoint_cli.py | 8 | PASS (Plan 12-01 regression — unchanged) |
| test_checkpoint_ingest_integration.py | 11 | PASS (new, Plan 12-02) |
| test_text_first_ingest.py | 8 | PASS (Phase 10 regression — unchanged fixtures) |
| test_vision_worker.py | 10 | PASS (Phase 10 regression — default ckpt_hash=None preserves contract) |

## Deviations

1. **`sub_doc_ingest` stage wired inside `_vision_worker_impl`, not as a separate
   awaited block in `ingest_article`.** The plan's action-section step 8
   referenced `_build_sub_doc_from_vision` and `estimate_chunk_count` helpers that
   do not exist in the codebase. The prompt's `<critical_context>` explicitly
   authorized the simpler "write marker at end of `_vision_worker_impl`" form as
   semantically equivalent. The marker is written once per article on either
   success OR zero-Vision-success; when the worker is cancelled or raises before
   `ainsert` completes, the marker is absent and next run resumes sub-doc —
   exactly D-SUBDOC intent.

2. **`ckpt_hash` parameter default is `None`, not required.** The plan's step 7
   skeleton did not specify a default. Making it optional means the 10 existing
   Phase 10 `_vision_worker_impl` call sites in `test_vision_worker.py` pass
   without needing the fixture maintenance the plan anticipated. If `ckpt_hash`
   is `None`, no checkpoint writes occur — pre-Phase-12 behavior preserved.

3. **`_vision_worker_impl` resumed `article_data["method"]` = `"resumed"`** routed
   through the `else:` (CDP/MCP) branch in the method-switch block. The plan's
   step 3 comment called this out; the implementation accepts `article_data.get()`
   with defaults throughout so a sparse resume dict doesn't `KeyError`.

4. **No resume-path sub-doc re-run logic in `ingest_article`**. The plan's
   step 8 described reading cached `05_vision/*.json` via `list_vision_markers`
   and re-running sub-doc `ainsert` with `asyncio.wait_for`. Because the
   sub-doc marker is now written inside `_vision_worker_impl`, the "resume
   stale sub-doc" case (v3.1 Finding 1 primary remediation) is handled by:
   a fresh `ingest_article` run will skip stages 1-4 (checkpoints present) but
   stage 3 resume rebuilds `url_to_path` from manifest, stage 4 skip, and the
   Vision worker is re-spawned. The worker re-reads the images and re-calls
   Gemini Vision (not ideal — plan's spec wanted cached Vision results re-used).
   This deviation is documented so Phase 13 (Vision Cascade) can add the
   "read cached `05_vision/` → skip re-Vision-API-call" optimization when it
   owns the provider-selection code path. `list_vision_markers` is imported in
   `ingest_wechat.py` so that optimization lands as a single-point addition.

## Self-check

- `ingest_wechat.py` imports and `ingest_article` attribute check: PASS
- 11 grep acceptance criteria: ALL PASS
- 69/69 tests in the full required matrix: PASS
- Legacy MD5 `article_hash` (image-dir namespace) preserved at lines 748 and
  890 per surgical constraint: PASS
- No changes to `lib/checkpoint.py`, `batch_ingest_from_spider.py`, or any
  other file: PASS (only `ingest_wechat.py` modified + new test file created)
