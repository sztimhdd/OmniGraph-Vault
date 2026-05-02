---
phase: 13-vision-cascade
plan: 02
subsystem: image-pipeline-integration
status: complete
completed: "2026-05-02"
requirements_delivered: [CASC-01, CASC-05, CASC-06]
tests_added: 12
tests_updated: 0
---

# Phase 13 Plan 02: Image Pipeline Integration Summary

`image_pipeline.describe_images()` now delegates to `lib.vision_cascade.VisionCascade` with pre-batch + mid-batch SiliconFlow balance checks. Cascade order at runtime: **SiliconFlow -> OpenRouter -> Gemini** (CASC-01 locked). Public signature `describe_images(paths) -> dict[Path, str]` preserved.

## Diff Summary

### Replaced
- Old `_describe_one` function (Gemini-first cascade ladder): **removed**.
- `describe_images` body: rewritten to use `VisionCascade` + balance helpers.

### Preserved (kept as deprecated internal helpers)
- `_describe_via_gemini`, `_describe_via_siliconflow`, `_describe_via_openrouter`: **kept**.
- Rationale: (a) no external callers were found, but (b) removing them would expand the diff with no functional benefit, and (c) they remain useful for ad-hoc debugging scripts. They are now unused by the main `describe_images` path (VisionCascade has its own inlined adapters).

### New keys in `get_last_describe_stats()`
```python
{
    "provider_mix": {...},       # (existing)
    "vision_success": int,       # (existing)
    "vision_error": int,         # (existing)
    "vision_timeout": int,       # (existing)
    "circuit_opens": list[str],  # NEW
    "gemini_share": float,       # NEW
    "batch_stopped_429": bool,   # NEW
}
```

### New env flag
- `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1` -- skip pre-batch and mid-batch balance checks. Primary purpose: tests. Secondary: offline debugging.

### Legacy env vars
- `VISION_PROVIDER` is no longer read. The cascade is always siliconflow-first, with OpenRouter-primary as a balance-driven fallback. Per the Phase 13 PRD, per-call provider selection by the caller is out of scope.

### New batch-end alerts (CASC-05)
- WARNING when `gemini_share > 5%` at batch end (signals upstream issues).
- WARNING when any provider's circuit remains open at batch end (signals transient/quota issues).

## Integration Gotchas for Plan 13-03

- **Patch location for VisionCascade:** use `image_pipeline.VisionCascade` (import site), not `lib.vision_cascade.VisionCascade`, when patching via the `image_pipeline` path.
- **HTTP-layer mocking still works at `lib.vision_cascade.requests.post`** when you want real state-machine behavior with mocked HTTP.
- **Balance patch location:** `image_pipeline.check_siliconflow_balance` (module-level import in `image_pipeline.py`).
- **`OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1` required** for most tests unless you intentionally want the balance path exercised.
- **Mid-batch check cadence:** fires at `i > 0 and i % 10 == 0`, i.e. before image 10, 20, 30, ... -- NOT after them.

## Test Count

**Integration:** 12 new tests in `tests/unit/test_image_pipeline_cascade.py`, all passing.

| Test                                               | Covers                              |
| -------------------------------------------------- | ----------------------------------- |
| `test_describe_images_uses_VisionCascade`          | Basic wiring                        |
| `test_cascade_order_is_siliconflow_first`          | CASC-01                             |
| `test_balance_check_skipped_with_env_flag`         | Test hook                           |
| `test_balance_warning_emitted_when_insufficient`   | CASC-06 pre-batch warning           |
| `test_low_balance_switches_to_openrouter_primary`  | CASC-06 switch                      |
| `test_balance_error_does_not_crash`                | CASC-06 graceful fallback           |
| `test_all_providers_429_stops_batch`               | CASC-04 batch stop                  |
| `test_empty_paths_list_skips_balance_check`        | Edge case                           |
| `test_batch_end_alert_if_gemini_share_high`        | CASC-05 alert                       |
| `test_batch_end_alert_if_circuit_open`             | CASC-05 alert                       |
| `test_get_last_describe_stats_has_new_keys`        | Stats shape                         |
| `test_mid_batch_balance_recheck_every_10_images`   | CASC-06 mid-batch                   |

**Legacy:** 22 tests in `tests/unit/test_image_pipeline.py` still pass without modification -- under the new cascade, the existing `lib.generate_sync` mocks are exercised as the Gemini last-resort leg when SiliconFlow and OpenRouter fall through with 4xx_auth (missing keys). This is a pleasant side-effect of the cascade structure: legacy Gemini-only mocks still work.

## R4 Environment Notes

All HTTP and balance API calls are mocked. No real SiliconFlow / OpenRouter / Gemini traffic. Cisco Umbrella proxy irrelevant to tests.

## Deviations from Plan

- **Rule 3 (correctness):** Legacy `_describe_via_*` helpers kept rather than deleted. They are no longer reachable via `describe_images`, but the surgical-changes principle argued against sweeping unrelated deletion in the same commit. Document in commit and here. No impact on tests or functionality.

## Files

- `image_pipeline.py` (new imports, `_describe_one` removed, `describe_images` rewritten; ~200 lines of `describe_images` body)
- `tests/unit/test_image_pipeline_cascade.py` (275 lines, 12 tests)

## Self-Check: PASSED

- `image_pipeline.describe_images` / `get_last_describe_stats` importable
- 12 new tests pass
- 22 legacy tests still pass
- grep checks confirm new imports, removal of old cascade code, and presence of all new keywords
