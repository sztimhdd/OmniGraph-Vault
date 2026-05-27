# Plan 08-01 — JSON-lines observability + inter-image sleep config

**Phase:** 8 — Image Pipeline Correctness
**REQs covered:** IMG-02, IMG-03, IMG-04
**Dependencies:** 08-00 (requires `filter_small_images()` + `FilterStats` to exist; Plan 08-01 instruments the function and adds aggregate logging)

---

## Summary

Add structured JSON-lines observability to the image pipeline per D-08.02/D-08.05 (per-image `image_processed` log on every image, aggregate `image_batch_complete` log at end of batch), and drop the default inter-image Vision sleep from `2s` to `0s` with an env override per D-08.04. All three changes land in one plan because they share the same `_emit_log` helper + outcome-taxonomy contract.

**Design choice — describe_images() signature preservation (Option A):** To avoid touching 3 call sites invasively, `describe_images(paths: list[Path]) -> dict[Path, str]` keeps its original signature. Per-call stats (provider_mix, vision_success/error/timeout counts) are exposed via a new module-level accessor `get_last_describe_stats() -> dict | None`. Callers that need stats call `describe_images(paths); stats = get_last_describe_stats()`. Callers that don't need stats (multimodal_ingest PDF single-image path, enrichment/fetch_zhihu.py) are **completely unchanged**.

---

## Files to modify

- `image_pipeline.py` (modify — add `_emit_log()` helper, module-level `_last_describe_stats` + `get_last_describe_stats()` accessor, instrument `download_images`/`filter_small_images`/`describe_images` with per-image logs, add `emit_batch_complete()` helper, change `_DESCRIBE_INTER_IMAGE_SLEEP_SECS` default to `0` with env override)
- `ingest_wechat.py` (modify — after the existing `describe_images()` call at line 651, call `get_last_describe_stats()` then `emit_batch_complete()`; line 778 PDF path is **unchanged** — Option A preserves return signature)
- `tests/unit/test_image_pipeline.py` (modify — fix pre-existing stale sleep assertion, update tests for new default=0, add tests for `_emit_log`, `emit_batch_complete`, outcome taxonomy, `get_last_describe_stats()`, env-override for `VISION_INTER_IMAGE_SLEEP`)

**Note on `enrichment/fetch_zhihu.py:249`:** unchanged (Option A preserves return signature). The Zhihu caller does not currently emit `image_batch_complete`; adding that to the Zhihu path is **out of scope** for Phase 8 (future Phase concern — see Out of Scope below). The per-image `image_processed` logs still fire from inside the instrumented pipeline functions, so Zhihu ingestions get partial observability for free.

---

## Tasks

### Task 1: Add `_emit_log()` helper + outcome taxonomy constants to `image_pipeline.py`

- **Change** (IMG-03, D-08.02, D-08.05):
  1. Add imports at top of `image_pipeline.py` (after existing imports): `import sys`, `from datetime import datetime, timezone`. `json` is already imported.
  2. Add outcome-taxonomy constants near module-level configs (after `_DEFAULT_IMAGE_BASE_URL`):

     ```python
     # Phase 8 IMG-03 / D-08.05: canonical outcome taxonomy (6 values).
     OUTCOME_SUCCESS = "success"
     OUTCOME_DOWNLOAD_FAILED = "download_failed"
     OUTCOME_FILTERED_TOO_SMALL = "filtered_too_small"
     OUTCOME_SIZE_READ_FAILED = "size_read_failed"
     OUTCOME_VISION_ERROR = "vision_error"
     OUTCOME_TIMEOUT = "timeout"
     ```

  3. Add the helper:

     ```python
     def _emit_log(event: dict) -> None:
         """Emit one JSON-lines event to stderr, or to VISION_LOG_PATH file if set.

         Atomic append: open('a') per call so concurrent-writer races are harmless
         at the line level (OS-level write-atomicity for <PIPE_BUF bytes).
         """
         line = json.dumps(event, ensure_ascii=False)
         log_path = os.environ.get("VISION_LOG_PATH", "").strip()
         if log_path:
             try:
                 with open(log_path, "a", encoding="utf-8") as f:
                     f.write(line + "\n")
                 return
             except OSError as e:
                 # Fallback to stderr on file write failure — do not crash pipeline
                 print(f"[_emit_log] VISION_LOG_PATH write failed: {e}", file=sys.stderr)
         print(line, file=sys.stderr)

     def _now_iso() -> str:
         now = datetime.now(timezone.utc)
         return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
     ```

- **Test** (covered in Task 5): unit test asserts `_emit_log({"a":1})` writes valid JSON to stderr by default, writes to file when `VISION_LOG_PATH` set, falls back to stderr on OSError.
- **Rollback:** `git revert <commit>`.

### Task 2: Instrument `download_images()` + `filter_small_images()` with per-image logs

- **Change** (IMG-03, D-08.02):
  1. In `download_images`, wrap each URL iteration with timing and emit on failure:

     ```python
     for i, url in enumerate(urls):
         t0 = time.perf_counter()
         try:
             resp = requests.get(url, timeout=10)
             if resp.status_code != 200:
                 _emit_log({
                     "event": "image_processed",
                     "ts": _now_iso(),
                     "url": url,
                     "local_path": None,
                     "dims": None,
                     "bytes": None,
                     "provider": None,
                     "ms": int((time.perf_counter() - t0) * 1000),
                     "outcome": OUTCOME_DOWNLOAD_FAILED,
                     "error": f"HTTP {resp.status_code}",
                 })
                 continue
             path = dest_dir / f"{i}.jpg"
             path.write_bytes(resp.content)
             result[url] = path
         except Exception as e:
             _emit_log({
                 "event": "image_processed",
                 "ts": _now_iso(),
                 "url": url,
                 "local_path": None,
                 "dims": None,
                 "bytes": None,
                 "provider": None,
                 "ms": int((time.perf_counter() - t0) * 1000),
                 "outcome": OUTCOME_DOWNLOAD_FAILED,
                 "error": str(e),
             })
     ```

     Note: successful downloads do NOT emit `image_processed` themselves — the downstream stage (filter or describe) owns the per-image event for kept images. This matches D-08.02 "`ms` measures wall-clock of the STAGE that owns this event."
  2. In `filter_small_images`, emit a per-filtered-out image log and a per-size-read-failed log (kept images are emitted later by `describe_images`):

     ```python
     for url, path in url_to_path.items():
         t0 = time.perf_counter()
         try:
             with PILImage.open(path) as im:
                 w, h = im.size
             file_bytes = path.stat().st_size
         except Exception as e:
             size_read_failed += 1
             kept[url] = path  # D-08.01 degrades to KEEP
             _emit_log({
                 "event": "image_processed",
                 "ts": _now_iso(),
                 "url": url,
                 "local_path": str(path),
                 "dims": None,
                 "bytes": None,
                 "provider": None,
                 "ms": int((time.perf_counter() - t0) * 1000),
                 "outcome": OUTCOME_SIZE_READ_FAILED,
                 "error": str(e),
             })
             continue
         if min(w, h) < min_dim:
             filtered_too_small += 1
             path.unlink(missing_ok=True)
             _emit_log({
                 "event": "image_processed",
                 "ts": _now_iso(),
                 "url": url,
                 "local_path": str(path),
                 "dims": f"{w}x{h}",
                 "bytes": file_bytes,
                 "provider": None,
                 "ms": int((time.perf_counter() - t0) * 1000),
                 "outcome": OUTCOME_FILTERED_TOO_SMALL,
                 "error": None,
             })
         else:
             kept[url] = path
     ```

     (Kept images produce NO event here — `describe_images` owns the success/vision_error/timeout outcome per D-08.02.)
- **Test:** Task 5 adds asserts that `_emit_log` is called N times for a batch with N-kept-plus-M-filtered images.
- **Rollback:** `git revert <commit>`.

### Task 3: Instrument `describe_images()` — Option A (signature-preserving)

- **Change** (IMG-03, D-08.02, D-08.05, IMG-02, D-08.04):

  **Key design decision (Option A, per revision feedback):** Keep the public signature `describe_images(paths: list[Path]) -> dict[Path, str]` **unchanged**. Stats are exposed via a new module-level accessor — no call-site changes required.

  1. Add module-level state near other module constants (after outcome constants from Task 1):

     ```python
     # Phase 8 IMG-04: stats from the most recent describe_images() call. Caller
     # retrieves via get_last_describe_stats() after describe_images() returns.
     # None until first call. Not thread-safe — single-ingest-at-a-time assumption
     # matches current batch orchestrator (one article at a time).
     _last_describe_stats: dict | None = None

     def get_last_describe_stats() -> dict | None:
         """Return stats from the most recent describe_images() call, or None if
         describe_images() has never been called in this process.

         Shape:
             {
                 "provider_mix": {"gemini": N, "siliconflow": N, "openrouter": N},
                 "vision_success": int,
                 "vision_error": int,
                 "vision_timeout": int,
             }
         """
         return _last_describe_stats
     ```

  2. Modify `_describe_one()` to return `tuple[str, str]` of `(description, provider_used)`. This is a **private helper** (underscore-prefixed) so changing its signature is not a public API break. The `provider_used` string is `"gemini" | "siliconflow" | "openrouter"`. **Enumerate the exact return points** (current `image_pipeline.py:132-158`):

     | Current line | Current return | New return |
     |---|---|---|
     | `image_pipeline.py:140` | `return _describe_via_gemini(image_bytes, mime)` | `return _describe_via_gemini(image_bytes, mime), "gemini"` |
     | `image_pipeline.py:142` | `return _describe_via_siliconflow(image_bytes, mime)` | `return _describe_via_siliconflow(image_bytes, mime), "siliconflow"` |
     | `image_pipeline.py:144` | `return _describe_via_openrouter(image_bytes, mime)` | `return _describe_via_openrouter(image_bytes, mime), "openrouter"` |
     | `image_pipeline.py:147` (auto — gemini first try) | `return _describe_via_gemini(image_bytes, mime)` | `return _describe_via_gemini(image_bytes, mime), "gemini"` |
     | `image_pipeline.py:155` (auto — siliconflow fallback) | `return _describe_via_siliconflow(image_bytes, mime)` | `return _describe_via_siliconflow(image_bytes, mime), "siliconflow"` |
     | `image_pipeline.py:158` (auto — openrouter last resort) | `return _describe_via_openrouter(image_bytes, mime)` | `return _describe_via_openrouter(image_bytes, mime), "openrouter"` |

     All 6 return points must be updated in the same commit; `_describe_one`'s only caller is `describe_images`, so no external blast radius.

  3. Rewrite `describe_images()` body. Public signature unchanged — `paths: list[Path]` in, `dict[Path, str]` out. Stats accumulated into module-level `_last_describe_stats`:

     ```python
     def describe_images(paths: list[Path]) -> dict[Path, str]:
         """Batch-describe images with automatic 3-provider cascade.
         (existing docstring preserved...)

         Phase 8 IMG-04: per-call stats exposed via get_last_describe_stats().
         """
         global _last_describe_stats
         provider = os.environ.get("VISION_PROVIDER", "auto").strip().lower()
         if provider not in ("gemini", "siliconflow", "openrouter", "auto"):
             logger.warning("Unknown VISION_PROVIDER=%r — falling back to 'auto'", provider)
             provider = "auto"

         sleep_secs = float(os.environ.get("VISION_INTER_IMAGE_SLEEP", _DESCRIBE_INTER_IMAGE_SLEEP_SECS))

         result: dict[Path, str] = {}
         paths_list = list(paths)
         provider_mix: dict[str, int] = {}
         vision_success = 0
         vision_error = 0
         vision_timeout = 0

         # Need url reverse-lookup for per-image logs. describe_images takes only
         # paths (public API), so url is unknown here. Emit local_path instead;
         # url=None for per-image logs from this stage. (Caller can correlate by
         # local_path since download_images already logged the original url.)
         for i, path in enumerate(paths_list):
             t0 = time.perf_counter()
             try:
                 desc, provider_used = _describe_one(path, provider)
                 result[path] = desc
                 vision_success += 1
                 provider_mix[provider_used] = provider_mix.get(provider_used, 0) + 1
                 _emit_log({
                     "event": "image_processed",
                     "ts": _now_iso(),
                     "url": None,  # not available here; correlate via local_path
                     "local_path": str(path),
                     "dims": None,
                     "bytes": path.stat().st_size if path.exists() else None,
                     "provider": provider_used,
                     "ms": int((time.perf_counter() - t0) * 1000),
                     "outcome": OUTCOME_SUCCESS,
                     "error": None,
                 })
             except Exception as e:
                 result[path] = f"Error describing image: {e}"
                 # Outcome taxonomy: timeout vs vision_error
                 err_text = str(e).lower()
                 is_timeout = (
                     "timeout" in err_text
                     or isinstance(e, TimeoutError)
                     or (hasattr(requests, "Timeout") and isinstance(e, requests.Timeout))
                 )
                 if is_timeout:
                     vision_timeout += 1
                     outcome = OUTCOME_TIMEOUT
                 else:
                     vision_error += 1
                     outcome = OUTCOME_VISION_ERROR
                 _emit_log({
                     "event": "image_processed",
                     "ts": _now_iso(),
                     "url": None,
                     "local_path": str(path),
                     "dims": None,
                     "bytes": path.stat().st_size if path.exists() else None,
                     "provider": None,  # provider unknown on failure (could be any in cascade)
                     "ms": int((time.perf_counter() - t0) * 1000),
                     "outcome": outcome,
                     "error": str(e),
                 })
             if i + 1 < len(paths_list) and sleep_secs > 0:
                 time.sleep(sleep_secs)

         _last_describe_stats = {
             "provider_mix": provider_mix,
             "vision_success": vision_success,
             "vision_error": vision_error,
             "vision_timeout": vision_timeout,
         }
         return result
     ```

  4. Change the default constant (IMG-02, D-08.04):

     ```python
     _DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0  # Phase 8 IMG-02: was 2; SiliconFlow has no RPM cap
     ```

  5. **Call-site inventory (for B1 traceability)** — confirm no caller requires modification under Option A:

     | Call site | Shape | Action under Option A |
     |---|---|---|
     | `ingest_wechat.py:651` (WeChat main ingest) | `descriptions = describe_images(list(url_to_path.values()))` | **Unchanged** at the `describe_images()` call itself. Task 4 adds a `get_last_describe_stats()` + `emit_batch_complete()` block immediately after. |
     | `ingest_wechat.py:778` (PDF loop, single image) | `describe_images([Path(img_path)]).get(Path(img_path), "")` | **Unchanged** — Option A preserves return signature. This was a key driver for choosing Option A: chaining `.get()` directly on the return value still works. |
     | `enrichment/fetch_zhihu.py:249` (Zhihu enrichment) | `descriptions = describe_images(list(url_to_path.values()))` | **Unchanged**. Zhihu does not emit `image_batch_complete` in Phase 8 (out of scope). Per-image logs still fire from inside the pipeline. |

  6. **Why not return `tuple[dict, dict]` (Option B / invasive)?** Rejected per revision feedback B2: breaks the `ingest_wechat.py:778` single-image chain (`.get()` on a tuple is awkward) and forces all 3 callers to change in the same commit. Option A isolates the feature to opt-in via a separate accessor.

- **Test:** Task 5 asserts (a) default sleep path calls `time.sleep(0)` and is skipped; (b) `VISION_INTER_IMAGE_SLEEP=1.5` env causes `time.sleep(1.5)`; (c) per-image log emitted per success/error/timeout; (d) timeout exception maps to `OUTCOME_TIMEOUT` not `OUTCOME_VISION_ERROR`; (e) `get_last_describe_stats()` returns populated dict after a call; (f) public `describe_images(paths)` signature unchanged — callers passing a plain `list[Path]` still work.
- **Rollback:** `git revert <commit>`. Note: this task changes `_describe_one` (private) return shape AND `describe_images` body but preserves public `describe_images` signature. Task 4 depends on the new module-level state; Task 3 + 4 can be committed atomically OR reverted together.

### Task 4: Add `emit_batch_complete()` helper + wire into `ingest_wechat.py` (WeChat path only)

- **Change** (IMG-04, D-08.02):
  1. Add helper to `image_pipeline.py` (after `get_last_describe_stats`):

     ```python
     def emit_batch_complete(
         *,
         filter_stats: FilterStats,
         download_input_count: int,
         download_failed: int,
         describe_stats: dict | None,
         total_ms: int,
     ) -> None:
         """Emit the aggregate image_batch_complete JSON-lines event (IMG-04).

         describe_stats can be None (e.g., if the batch had 0 images to describe);
         the helper normalizes missing keys to 0 / {} to keep wire format stable.
         """
         ds = describe_stats or {}
         _emit_log({
             "event": "image_batch_complete",
             "ts": _now_iso(),
             "counts": {
                 "input": download_input_count,
                 "kept": filter_stats.kept,
                 "filtered_too_small": filter_stats.filtered_too_small,
                 "download_failed": download_failed,
                 "size_read_failed": filter_stats.size_read_failed,
                 "vision_success": ds.get("vision_success", 0),
                 "vision_error": ds.get("vision_error", 0),
                 "vision_timeout": ds.get("vision_timeout", 0),
             },
             "total_ms": total_ms,
             "provider_mix": ds.get("provider_mix", {}),
         })
     ```

  2. In `ingest_wechat.py`, capture timing around the image-processing block and emit at the end. The `describe_images()` call at line 651 stays **unchanged**; we only add wrapping instrumentation and a trailing `emit_batch_complete` call:

     ```python
     # Phase 8 IMG-04: aggregate batch-complete log (D-08.02).
     import time as _time
     _img_batch_t0 = _time.perf_counter()
     url_to_path = download_images(unique_img_urls, Path(article_dir))
     download_failed = len(unique_img_urls) - len(url_to_path)
     # ... Plan 08-00 inserted filter_small_images call here ...
     min_dim = int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300))
     url_to_path, filter_stats = filter_small_images(url_to_path, min_dim=min_dim)
     # describe_images signature unchanged (Option A) — stats via accessor
     descriptions = describe_images(list(url_to_path.values()))
     describe_stats = get_last_describe_stats()
     emit_batch_complete(
         filter_stats=filter_stats,
         download_input_count=len(unique_img_urls),
         download_failed=download_failed,
         describe_stats=describe_stats,
         total_ms=int((_time.perf_counter() - _img_batch_t0) * 1000),
     )
     ```

  3. Ensure `emit_batch_complete` and `get_last_describe_stats` are added to the `from image_pipeline import ...` line.

  4. **PDF path at `ingest_wechat.py:778` is NOT modified.** It calls `describe_images([Path(img_path)]).get(Path(img_path), "")` once per image inside a loop — there is no "batch" in the aggregate sense and the per-image logs already cover observability. Adding `emit_batch_complete` to the PDF path is out of scope. Verify: `grep -n "describe_images" ingest_wechat.py` returns exactly 2 lines (one at ~651, one at ~778), and only the ~651 site is surrounded by new `emit_batch_complete` scaffolding.

  5. **Zhihu path at `enrichment/fetch_zhihu.py:249` is NOT modified** for the same reason — Zhihu-specific observability is out of Phase 8 scope.

- **Test:**
  - Manual: run `python ingest_wechat.py <fixture-url>` and redirect stderr through `jq`:
    `python ingest_wechat.py <url> 2> >(jq -c 'select(.event=="image_batch_complete")')`
    → one line of valid JSON with the full `counts` dict.
  - `VISION_LOG_PATH=/tmp/vision.log python ingest_wechat.py <url>` → file has N `image_processed` lines + 1 `image_batch_complete` line, all parseable by `jq`.
  - Unit test in Task 5 stubs `_emit_log` and asserts the shape of the batch-complete event.
- **Rollback:** `git revert <commit>`.

### Task 5: Update + extend pytest suite in `tests/unit/test_image_pipeline.py`

- **Change** (IMG-02, IMG-03, IMG-04, D-08.07):
  1. **Fix pre-existing stale test** `test_describe_images_batch_calls_sleep_between` (currently line 38-54). **Note: pre-Phase-8 mismatch — code currently has `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 2` (`image_pipeline.py:19`) but the test asserts `mock_sleep.assert_called_once_with(4)` (test line 54). This test may already be failing before Phase 8 begins.** Plan 08-00's baseline check documents this. Plan 08-01 Task 5 fixes it:
     - Line 54 currently asserts `mock_sleep.assert_called_once_with(4)`. Update to reflect D-08.04 default=0:

       ```python
       # With default _DESCRIBE_INTER_IMAGE_SLEEP_SECS=0, sleep(0) is skipped by the
       # `if ... and sleep_secs > 0` guard — so sleep is NOT called at all by default.
       mock_sleep.assert_not_called()
       ```

     - **Public signature unchanged (Option A)** — test still passes a `list[Path]`: `describe_images([p1, p2])`. No dict re-wiring.
     - Return type unchanged — `result = describe_images(...)` is still `dict[Path, str]`. No tuple-unpacking.
     - `_describe_one` now returns `(desc, provider)`, but the test patches `lib.generate_sync` at the bottom of the call stack — `_describe_via_gemini` wraps it and returns a str, then `_describe_one` returns `(str, "gemini")`. The test's existing `mocker.patch("lib.generate_sync", return_value="desc")` is sufficient because `_describe_via_gemini` passes the return value through unchanged.
  2. **Fix pre-existing test** `test_describe_images_per_image_error_isolation`: no signature changes needed (Option A). The test stays as-is except for verifying the error-isolation contract still holds with the new outcome-taxonomy code path — content assertions unchanged (`"Error describing image"` check remains valid, because `result[path] = f"Error describing image: {e}"` is preserved in the new body).
  3. **Add new test** `test_describe_images_respects_vision_inter_image_sleep_env(tmp_path, mocker, monkeypatch)`:
     - `monkeypatch.setenv("VISION_INTER_IMAGE_SLEEP", "1.5")`
     - Two fake images, mock `lib.generate_sync` → "desc"
     - `describe_images([p1, p2])` (list, not dict — Option A)
     - Assert `mock_sleep.assert_called_once_with(1.5)`
  4. **Add new test** `test_emit_log_writes_jsonlines_to_stderr(capsys, monkeypatch)`:
     - `monkeypatch.delenv("VISION_LOG_PATH", raising=False)`
     - Call `_emit_log({"event": "x", "ts": "t", "url": "u"})`
     - Assert `capsys.readouterr().err` contains a valid JSON line that round-trips via `json.loads`
  5. **Add new test** `test_emit_log_writes_to_file_when_env_set(tmp_path, monkeypatch)`:
     - `monkeypatch.setenv("VISION_LOG_PATH", str(tmp_path / "vision.log"))`
     - Call `_emit_log({"event": "x"})` twice
     - Assert file has exactly 2 lines, each parses via `json.loads`
  6. **Add new test** `test_filter_small_images_emits_filtered_too_small_log(tmp_path, mocker, monkeypatch, capsys)`:
     - Mock `PIL.Image.open` to return dims (100, 800)
     - Write a fake file so `path.stat().st_size` succeeds
     - Call `filter_small_images({"u": path}, min_dim=300)`
     - Parse stderr → expect one `image_processed` line with `outcome == "filtered_too_small"`, `dims == "100x800"`
  7. **Add new test** `test_filter_small_images_emits_size_read_failed_log(tmp_path, mocker, monkeypatch, capsys)`:
     - Mock `PIL.Image.open` to raise `OSError("corrupt")`
     - Call `filter_small_images({"u": path}, min_dim=300)`
     - Parse stderr → one event with `outcome == "size_read_failed"`, `error == "corrupt"`
  8. **Add new test** `test_describe_images_outcome_timeout_vs_vision_error(tmp_path, mocker, monkeypatch, capsys)`:
     - First image: `lib.generate_sync` raises `TimeoutError("read timeout")` → assert emitted event has `outcome == "timeout"`
     - Second image: `lib.generate_sync` raises `RuntimeError("HTTP 500")` → assert emitted event has `outcome == "vision_error"`
  9. **Add new test** `test_get_last_describe_stats_populated_after_call(tmp_path, mocker, monkeypatch)`:
     - `monkeypatch.setenv("GEMINI_API_KEY", "test")`
     - Mock `lib.generate_sync` → "desc"
     - Call `describe_images([p1, p2])`
     - Call `get_last_describe_stats()` → dict with `vision_success == 2`, `provider_mix["gemini"] == 2` (default VISION_PROVIDER=auto, first try = gemini succeeds)
     - Also assert: before any describe_images call in a fresh process, `get_last_describe_stats()` returns `None` (document in docstring; test via fresh import if needed, or reset the module-level var via `monkeypatch.setattr("image_pipeline._last_describe_stats", None)`)
  10. **Add new test** `test_emit_batch_complete_aggregate_shape(capsys)`:
      - Synthesize `FilterStats(input=30, kept=20, filtered_too_small=9, size_read_failed=1, timings_ms={"total_read": 50})` (nested `timings_ms` per CONTEXT D-08.01)
      - Call `emit_batch_complete(filter_stats=..., download_input_count=30, download_failed=0, describe_stats={"vision_success": 18, "vision_error": 2, "vision_timeout": 0, "provider_mix": {"siliconflow": 18}}, total_ms=12000)`
      - Parse stderr; assert event shape matches D-08.02 aggregate schema exactly (all 3 top-level keys: `counts`, `total_ms`, `provider_mix`; `counts` has all 8 subkeys per D-08.02 aggregate sample).
  11. **Add new test** `test_emit_batch_complete_handles_none_describe_stats(capsys)`:
      - Call `emit_batch_complete(..., describe_stats=None, ...)`
      - Assert event shape intact; `vision_success/error/timeout` default to 0; `provider_mix` defaults to `{}`
  12. All new tests use `@pytest.mark.unit`.
- **Test:** `pytest tests/unit/test_image_pipeline.py -v` → all ~17 tests pass (5 original with 1 pre-existing fix + 7 from 08-00 + 9 new from this plan — one of the 5 originals gets the stale sleep fix, the other stays as-is).
- **Rollback:** `git revert <commit>`.

### Task 6: Golden-file diff — D-08.07 §2 regression gate

- **Change** (D-08.07 §2, D-16 carry-forward):
  1. **Setup** (one-time on remote Hermes PC, run BEFORE merging this plan):

     ```bash
     # Pick 2-3 already-cached articles from ~/.hermes/omonigraph-vault/images/
     # Criteria: one image-heavy (≥15 images after filter), one text-heavy (≤5 images), one mixed
     ls ~/.hermes/omonigraph-vault/images/ | head
     # Copy their final_content.md to a golden baseline:
     mkdir -p tests/golden/phase8_baseline/
     cp ~/.hermes/omonigraph-vault/images/<hash1>/final_content.md tests/golden/phase8_baseline/<hash1>.md
     cp ~/.hermes/omonigraph-vault/images/<hash2>/final_content.md tests/golden/phase8_baseline/<hash2>.md
     cp ~/.hermes/omonigraph-vault/images/<hash3>/final_content.md tests/golden/phase8_baseline/<hash3>.md
     git add tests/golden/phase8_baseline/ && git commit -m "test: capture Phase 8 golden baseline (pre-change)"
     ```

  2. **After implementing Tasks 1-5**, re-run ingest for the same 3 articles with the updated pipeline (must pass `GEMINI_API_KEY` + `SILICONFLOW_API_KEY`; re-uses cached image files). Diff:

     ```bash
     for hash in <hash1> <hash2> <hash3>; do
         diff <(grep -E '^# |^\[Image [0-9]+ Reference\]:' tests/golden/phase8_baseline/$hash.md) \
              <(grep -E '^# |^\[Image [0-9]+ Reference\]:' ~/.hermes/omonigraph-vault/images/$hash/final_content.md)
     done
     ```

     **Expected:** Structural diff (title `# ...`, `[Image N Reference]:` lines, image count) is empty. Content lines (`[Image N Description]:`) may differ by 1-2 lines per image (Vision model non-determinism is acceptable).
  3. **Fail condition:** image count per article changes, OR local URL format diverges from `http://localhost:8765/<hash>/<N>.jpg`, OR title / publish-time lines disappear.
- **Test:** Structural-diff empty per the script above; record results in the plan SUMMARY.md.
- **Rollback:** `git revert <commit>` for baseline files; no production code to revert beyond Tasks 1-5.

---

## Success Criteria

1. `_emit_log()` writes one JSON-lines event to stderr by default; writes to `$VISION_LOG_PATH` when env is set; falls back to stderr on OSError.
2. Every image processed emits exactly one `image_processed` JSON line with all required fields (`event`, `ts`, `url`, `local_path`, `dims`, `bytes`, `provider`, `ms`, `outcome`, `error`) per D-08.02 schema.
3. `outcome` field uses exactly one of the 6 values from D-08.05: `success | download_failed | filtered_too_small | size_read_failed | vision_error | timeout`.
4. `provider` is `null` for non-Vision outcomes (`download_failed`, `filtered_too_small`, `size_read_failed`, `vision_error`, `timeout`); one of `"gemini" | "siliconflow" | "openrouter"` for `success`.
5. One `image_batch_complete` JSON line emitted per `ingest_wechat` **WeChat** run with full counts + total_ms + provider_mix per D-08.02. PDF and Zhihu paths emit per-image logs but **no** aggregate (out of scope).
6. `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0` (down from 2); `VISION_INTER_IMAGE_SLEEP=1.5` env causes `time.sleep(1.5)` between images; default path calls no sleep.
7. **Public `describe_images(paths: list[Path]) -> dict[Path, str]` signature unchanged** (Option A). All 3 call sites (`ingest_wechat.py:651`, `ingest_wechat.py:778`, `enrichment/fetch_zhihu.py:249`) continue to compile and run without signature edits.
8. `get_last_describe_stats()` returns a dict with keys `provider_mix`, `vision_success`, `vision_error`, `vision_timeout` after any `describe_images` call; returns `None` before first call in a process.
9. Pytest suite passes: 5 original tests (1 modified for stale assertion + default=0) + 7 from Plan 08-00 + 9 new from this plan = ~17 tests green.
10. Golden-file structural diff against 3 cached articles shows zero image-count / URL-format divergence.

---

## Verification

```bash
# On remote Hermes PC
ssh <remote> "cd ~/OmniGraph-Vault && git pull --ff-only"
ssh <remote> "cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/unit/test_image_pipeline.py -v"
```

Expected: all tests PASSED, including:
- `test_describe_images_batch_calls_sleep_between` (UPDATED — fixes pre-existing stale assertion; now asserts `mock_sleep.assert_not_called()` per default=0)
- `test_describe_images_respects_vision_inter_image_sleep_env` (NEW)
- `test_emit_log_writes_jsonlines_to_stderr` (NEW)
- `test_emit_log_writes_to_file_when_env_set` (NEW)
- `test_filter_small_images_emits_filtered_too_small_log` (NEW)
- `test_filter_small_images_emits_size_read_failed_log` (NEW)
- `test_describe_images_outcome_timeout_vs_vision_error` (NEW)
- `test_get_last_describe_stats_populated_after_call` (NEW)
- `test_emit_batch_complete_aggregate_shape` (NEW)
- `test_emit_batch_complete_handles_none_describe_stats` (NEW)

Live-run verification on gpt55 fixture (after Phase 11 CLI lands this becomes automated; for Phase 8 do it manually):

```bash
# On remote
cd ~/OmniGraph-Vault && source venv/bin/activate
python ingest_wechat.py "https://mp.weixin.qq.com/s/<gpt55-fixture-url>" 2> /tmp/vision.log
# Check per-image log shape
head -5 /tmp/vision.log | jq 'select(.event=="image_processed")'
# Check aggregate log
grep image_batch_complete /tmp/vision.log | jq '.'
# Must show: counts.input == 39 (or whatever raw WeChat gives), counts.kept == 28 (fixture baseline),
# counts.filtered_too_small == 11, provider_mix non-empty.
```

Golden-file diff (D-08.07 §2):

```bash
# Run the for-loop from Task 6 step 2 — structural diff MUST be empty for all 3 articles.
```

---

## Out of Scope (reference only, do not implement here)

- **`filter_small_images()` function itself** — Plan 08-00 (IMG-01)
- **`IMAGE_FILTER_MIN_DIM` env read at ingest_wechat call site** — Plan 08-00 (D-08.03)
- **Per-image Vision cache (`cache_hit` outcome)** — deferred to v3.2 per D-08.05
- **Image cost tracking (`estimated_cost_yuan` field)** — deferred per CONTEXT §Deferred
- **OTel / structlog / Datadog log shipping** — deferred per CONTEXT §Deferred
- **`image_batch_complete` emission from PDF (`ingest_wechat.py:778`) and Zhihu (`enrichment/fetch_zhihu.py:249`) paths** — per-image logs fire from inside the pipeline for these paths, but the aggregate event is WeChat-only in Phase 8. Extending coverage is a future-phase concern.
- **Benchmark `benchmark_result.json` schema + gate_pass** — Phase 11 (E2E-07) — this plan provides the raw material (stderr JSON-lines) that Phase 11 benchmark will tail + aggregate into `benchmark_result.json`
- **Phase 9 / 10 / 11 concerns** — timeout, classifier scrape-first, E2E CLI all out of scope
