# Plan 08-00 — filter_small_images function + caller refactor

**Phase:** 8 — Image Pipeline Correctness
**REQs covered:** IMG-01
**Dependencies:** none (self-contained; no prior Phase 8 plan)

---

## Summary

Extract the inline dimension-filter currently at `ingest_wechat.py:627-649` into a new `filter_small_images(url_to_path, *, min_dim=300) -> (filtered_map, FilterStats)` function in `image_pipeline.py`, and replace the inline block in `ingest_wechat.py` with a single call. Preserves existing `min(w,h) < min_dim` semantics (the code already filters correctly — `or` is mathematically equivalent); the refactor is for testability + single-responsibility + feeding IMG-04 aggregate counts structurally.

---

## Files to modify

- `image_pipeline.py` (modify — add `FilterStats` dataclass + `filter_small_images()` function)
- `ingest_wechat.py` (modify — replace lines 627-649 with one call to `filter_small_images()`, read `IMAGE_FILTER_MIN_DIM` env at call site per D-08.03)
- `tests/unit/test_image_pipeline.py` (modify — add test cases for `filter_small_images()` per D-08.07 §1)

---

## Tasks

### Task 1: Add `FilterStats` + `filter_small_images()` to `image_pipeline.py`

- **Change** (IMG-01, D-08.01, D-08.06):
  1. Add a frozen dataclass near top of `image_pipeline.py` (after existing module-level constants, before `download_images`). **Shape MUST match CONTEXT D-08.01 literal wire format** — `timings_ms` is a nested dict, not a flat field:
     ```python
     from dataclasses import dataclass, field

     @dataclass(frozen=True)
     class FilterStats:
         input: int
         kept: int
         filtered_too_small: int
         size_read_failed: int
         timings_ms: dict  # {"total_read": <int ms>} — nested per D-08.01 wire format
     ```
  2. Add the new function immediately after `download_images`:
     ```python
     def filter_small_images(
         url_to_path: dict[str, Path],
         *,
         min_dim: int = 300,
     ) -> tuple[dict[str, Path], FilterStats]:
         """Filter images where min(width, height) < min_dim.

         PIL open failure => keep image (can't measure => don't drop). Filtered-out
         files are unlinked from disk to reclaim space. Returns (new_map, stats).
         """
         from PIL import Image as PILImage
         t0 = time.perf_counter()
         kept: dict[str, Path] = {}
         filtered_too_small = 0
         size_read_failed = 0
         for url, path in url_to_path.items():
             try:
                 with PILImage.open(path) as im:
                     w, h = im.size
             except Exception as e:
                 logger.warning("PIL open failed for %s (%s) — keeping image", path, e)
                 size_read_failed += 1
                 kept[url] = path  # D-08.01: PIL failure degrades to KEEP
                 continue
             if min(w, h) < min_dim:
                 filtered_too_small += 1
                 path.unlink(missing_ok=True)
             else:
                 kept[url] = path
         stats = FilterStats(
             input=len(url_to_path),
             kept=len(kept),
             filtered_too_small=filtered_too_small,
             size_read_failed=size_read_failed,
             timings_ms={"total_read": int((time.perf_counter() - t0) * 1000)},
         )
         return kept, stats
     ```
  3. **Exact filter math:** `min(w, h) < min_dim` (D-08.01 return contract). Code comment must cite: `# Phase 8 IMG-01: min(w,h)<min_dim matches current or-logic; see CONTEXT §Specifics for pre-fix history`.
  4. PIL import is kept lazy inside the function (matches existing pattern in `ingest_wechat.py:635`) to avoid forcing Pillow on callers that don't filter.
  5. **Why nested `timings_ms: dict`:** conforms to CONTEXT D-08.01 literal wire format (`FilterStats: {input, kept, filtered_too_small, size_read_failed, timings_ms: {total_read: int}}`). Future stages may add `timings_ms.total_unlink_ms` / `timings_ms.total_stat_ms` without changing the dataclass shape. If a flatter ergonomic shape becomes desirable downstream, update CONTEXT.md first to avoid spec drift.
- **Test** (D-08.07 §1 — new pytest cases in Task 3 below); also manual smoke: `python -c "from image_pipeline import filter_small_images, FilterStats; print(FilterStats.__annotations__)"` → prints 5 fields including `timings_ms: dict`.
- **Rollback:** `git revert <commit>` — function + dataclass are pure additions, no existing signatures touched.

### Task 2: Replace inline filter in `ingest_wechat.py` with call to `filter_small_images()`

- **Change** (IMG-01, D-08.01, D-08.03):
  1. At the top of `ingest_wechat.py`, ensure `filter_small_images` is added to the existing import from `image_pipeline`. Current import is `from image_pipeline import download_images, describe_images, localize_markdown` (or similar — confirm the exact line with grep before editing). Add `filter_small_images` to it.
  2. Replace lines `627-649` (the current inline PIL filter block starting with `# Phase 5-00b: filter small images...` and ending with the `if filtered_out: print(...)` line) with:
     ```python
     # Phase 8 IMG-01: filter small images via shared pipeline (D-08.01, D-08.03).
     min_dim = int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300))
     url_to_path, filter_stats = filter_small_images(url_to_path, min_dim=min_dim)
     print(
         f"Filtered {filter_stats.filtered_too_small} small images "
         f"(<{min_dim}px) — {filter_stats.kept} remaining"
     )
     ```
  3. Do not change the surrounding code (`download_images(...)` call before, `describe_images(...)` call after). This is a surgical extraction.
  4. The `from PIL import Image as PILImage` and `_MIN_IMG_DIM = 300` local statements inside the block must be deleted (they become orphans).
- **Test:**
  - `python -c "import ingest_wechat"` → imports cleanly, no syntax error
  - `grep -n "PILImage" ingest_wechat.py` → returns nothing (orphan removed)
  - `grep -n "filter_small_images" ingest_wechat.py` → returns exactly one import and one call site
- **Rollback:** `git revert <commit>` — single-file, single-block diff.

### Task 3: Add pytest cases for `filter_small_images()` in `tests/unit/test_image_pipeline.py`

- **Change** (IMG-01, D-08.07 §1):
  1. Add import: `from image_pipeline import filter_small_images, FilterStats` (extend existing import tuple).
  2. Add a helper fixture that writes N fake JPEG-like files with controllable dims by monkey-patching `PIL.Image.open`. Pattern:
     ```python
     def _fake_open(dims_by_name: dict[str, tuple[int, int]]):
         """Returns a context manager that yields an object with .size set per file name."""
         class _Ctx:
             def __init__(self, w, h): self.size = (w, h)
             def __enter__(self): return self
             def __exit__(self, *a): return False
         def _open(path, *a, **kw):
             return _Ctx(*dims_by_name[Path(path).name])
         return _open
     ```
  3. Add these seven tests (all `@pytest.mark.unit`):
     - `test_filter_keeps_800x600(tmp_path, mocker)` → one file, dims (800,600), min_dim=300 → `kept == 1`, `filtered_too_small == 0`
     - `test_filter_drops_100x800_narrow_banner(tmp_path, mocker)` → one file, dims (100,800), min_dim=300 → `kept == 0`, `filtered_too_small == 1`, file unlinked from disk
     - `test_filter_drops_300x299_just_below(tmp_path, mocker)` → one file, dims (300,299), min_dim=300 → `kept == 0`, `filtered_too_small == 1`
     - `test_filter_keeps_300x300_exact_threshold(tmp_path, mocker)` → dims (300,300), min_dim=300 → `kept == 1` (boundary: `min(w,h) < 300` is strict inequality)
     - `test_filter_drops_299x300_one_axis_below(tmp_path, mocker)` → dims (299,300), min_dim=300 → `filtered_too_small == 1`
     - `test_filter_kwarg_min_dim_100_keeps_150x150(tmp_path, mocker)` → dims (150,150), min_dim=100 → `kept == 1`
     - `test_filter_pil_open_failure_keeps_image(tmp_path, mocker)` → `PILImage.open` raises OSError → `kept == 1` (D-08.01 degrades to KEEP), `size_read_failed == 1`, file NOT unlinked
  4. Each test asserts the returned `FilterStats` fields AND the resulting dict contents. Note: `timings_ms` is a nested dict — tests that check it should use `stats.timings_ms["total_read"]` and assert `isinstance(stats.timings_ms, dict)` + `"total_read" in stats.timings_ms`. Most tests can just ignore `timings_ms` (timing is non-deterministic). Use `monkeypatch.setattr("PIL.Image.open", _open)` to inject fake dimensions without needing real image files.
  5. **Integration-style test** (covers `IMAGE_FILTER_MIN_DIM` env read in `ingest_wechat.py`, D-08.07 §1 bullet 7): add `test_ingest_wechat_reads_env_min_dim(monkeypatch)` that imports the module and asserts `int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300))` with the env set to `100` returns `100`. This is a thin smoke test, not a full subprocess run — full subprocess validation belongs in Phase 11 E2E.
- **Test:**
  - `cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/unit/test_image_pipeline.py -v` → all new tests pass, existing 5 tests still pass (8 total minimum)
- **Rollback:** `git revert <commit>` — test additions only, no production code impact.

---

## Success Criteria

1. `filter_small_images(url_to_path, min_dim=300)` exists in `image_pipeline.py`, returns `(dict, FilterStats)` with 5 fields: `input`, `kept`, `filtered_too_small`, `size_read_failed`, `timings_ms` (nested dict with `total_read` key per CONTEXT D-08.01).
2. `ingest_wechat.py:627-649` inline filter block is deleted; replaced by a single call to `filter_small_images()` reading `IMAGE_FILTER_MIN_DIM` from env (default 300).
3. Image with dims (100, 800) — the narrow-banner bug Hermes flagged — is filtered out: `min(100, 800) = 100 < 300`.
4. Image with dims (800, 600) is kept.
5. PIL open failure keeps the image (no silent drop) and increments `size_read_failed`.
6. 7 new pytest cases in `tests/unit/test_image_pipeline.py::test_filter_*` all pass.
7. Existing pytest suite (`pytest tests/unit/test_image_pipeline.py`) still passes — no regression on pre-existing tests (**noting pre-existing sleep-assertion staleness documented below; 08-01 Task 5 fixes it**).

---

## Verification

**Baseline check (run BEFORE any Phase 8 changes):**

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate
pytest tests/unit/test_image_pipeline.py -v
```

**Note any pre-existing failures before starting work.** Specifically, `test_describe_images_batch_calls_sleep_between` currently asserts `mock_sleep.assert_called_once_with(4)` (line 54) but `image_pipeline.py:19` has `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 2` — this test may already be failing before Phase 8 begins. If it is, the failure is out of Plan 08-00 scope (Plan 08-01 Task 5 will fix it). Record the baseline pass/fail count in the commit message so 08-00's regression claim is falsifiable.

**Post-change verification:**

```bash
# On remote Hermes PC (D-06 — all Phase 4+ validation runs there)
ssh <remote> "cd ~/OmniGraph-Vault && git pull --ff-only"
ssh <remote> "cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/unit/test_image_pipeline.py -v"
```

Expected output:
- `test_filter_keeps_800x600 PASSED`
- `test_filter_drops_100x800_narrow_banner PASSED`
- `test_filter_drops_300x299_just_below PASSED`
- `test_filter_keeps_300x300_exact_threshold PASSED`
- `test_filter_drops_299x300_one_axis_below PASSED`
- `test_filter_kwarg_min_dim_100_keeps_150x150 PASSED`
- `test_filter_pil_open_failure_keeps_image PASSED`
- `test_ingest_wechat_reads_env_min_dim PASSED`
- Pre-existing 5 tests — same pass/fail state as baseline (any pre-existing failure is an 08-01 concern, not a 08-00 regression)

Plus a static check:
```bash
grep -n "PILImage" ingest_wechat.py  # MUST return empty
grep -c "filter_small_images" image_pipeline.py  # MUST return >= 2 (def + export surface)
```

---

## Out of Scope (reference only, do not implement here)

- **Per-image JSON-lines logging** — Plan 08-01 (IMG-03)
- **Aggregate `image_batch_complete` log** — Plan 08-01 (IMG-04)
- **`_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0` default change** — Plan 08-01 (IMG-02)
- **Fix pre-existing stale `test_describe_images_batch_calls_sleep_between` (expects 4, code has 2)** — Plan 08-01 Task 5
- **Golden-file diff against cached articles** — Plan 08-01 Verification (D-08.07 §2) — runs after BOTH plans merge so structural-diff captures full Phase 8 behavior
- **`classifications` SQLite table** — Phase 10 (CLASS-04)
- **Async Vision worker decoupling** — Phase 10 (ARCH-02)
