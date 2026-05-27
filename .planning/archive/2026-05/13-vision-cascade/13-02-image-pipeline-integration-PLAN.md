---
phase: 13-vision-cascade
plan: 02
type: execute
wave: 2
depends_on:
  - 13-00
  - 13-01
files_modified:
  - image_pipeline.py
  - tests/unit/test_image_pipeline_cascade.py
autonomous: true
requirements:
  - CASC-01
  - CASC-05
  - CASC-06

must_haves:
  truths:
    - "image_pipeline.describe_images() delegates to VisionCascade instead of the old 3-provider _describe_one cascade"
    - "Cascade order invoked at runtime is SiliconFlow → OpenRouter → Gemini (replacing the buggy Gemini-first order)"
    - "Pre-batch SiliconFlow balance check is called once at batch start; emits structured warning if balance < estimated cost"
    - "Mid-batch balance re-check every 10 images; if balance < ¥0.05 then subsequent images force-cascade through OpenRouter (skip SiliconFlow)"
    - "AllProvidersExhausted429Error caught at batch boundary → batch stops cleanly with operator warning log (not silent crash)"
    - "Batch-end aggregate log emits per-provider success/attempt/failure counts + alert if gemini_share > 5% or any circuit still open"
    - "Backward-compat: the old sync describe_images(paths) signature still works; cascade is instantiated internally with a default checkpoint dir"
  artifacts:
    - path: "image_pipeline.py"
      provides: "describe_images() rewired to VisionCascade + balance helpers; legacy _describe_one/_describe_via_* kept as deprecated internal helpers OR removed (planner's choice, document in commit)"
      contains: "VisionCascade"
    - path: "tests/unit/test_image_pipeline_cascade.py"
      provides: "Unit tests verifying image_pipeline integration: describe_images uses VisionCascade; balance warning emitted; mid-batch switch triggered"
      contains: "def test_"
      min_lines: 120
  key_links:
    - from: "image_pipeline.py"
      to: "lib.vision_cascade.VisionCascade"
      via: "import and instantiate per describe_images() call"
      pattern: "from lib.vision_cascade import"
    - from: "image_pipeline.py"
      to: "lib.siliconflow_balance.check_siliconflow_balance"
      via: "pre-batch + every-10-images balance fetch"
      pattern: "from lib.siliconflow_balance import"
    - from: "image_pipeline.py"
      to: "lib.vision_cascade.AllProvidersExhausted429Error"
      via: "caught at top of describe_images loop for graceful batch stop"
      pattern: "except AllProvidersExhausted429Error"
---

<objective>
Replace `image_pipeline._describe_one`'s cascade (wrong order: Gemini → SiliconFlow → OpenRouter) with calls to `VisionCascade.describe()` from Plan 13-00. Wire in pre-batch + mid-batch balance checks from Plan 13-01. Preserve the public `describe_images(paths) -> dict[Path, str]` signature so existing callers (`multimodal_ingest.py`, `ingest_wechat.py`, Phase 10's async Vision worker) do not change.

Purpose: CONTEXT.md flagged the current cascade as buggy (Gemini-first wastes free quota + causes 429 spillover). After this plan merges, the batch runs on SiliconFlow primary → OpenRouter fallback → Gemini last-resort as CASC-01 locked.

Output:
- `image_pipeline.py` — describe_images() refactored; old `_describe_one` and `_describe_via_*` helpers either removed (clean) or retained as deprecated (backward-compat). `get_last_describe_stats()` enriched with cascade metadata (circuit_opens, gemini_share).
- `tests/unit/test_image_pipeline_cascade.py` — new test file specifically for the integration; does NOT replace `test_image_pipeline.py` (which tests download/filter/localize).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/13-vision-cascade/13-CONTEXT.md
@.planning/phases/13-vision-cascade/13-00-SUMMARY.md
@.planning/phases/13-vision-cascade/13-01-SUMMARY.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
@image_pipeline.py
@lib/__init__.py
@tests/conftest.py
@tests/unit/test_image_pipeline.py

<interfaces>
<!-- Contracts from Plans 13-00 and 13-01 (already merged before this plan runs) -->

From `lib/vision_cascade.py`:
```python
from lib.vision_cascade import (
    VisionCascade,
    CascadeResult,
    AttemptRecord,
    AllProvidersExhausted429Error,
    DEFAULT_PROVIDERS,  # ("siliconflow", "openrouter", "gemini")
)

cascade = VisionCascade(checkpoint_dir=None)  # defaults to BASE_DIR/checkpoints
result: CascadeResult = cascade.describe(image_id="img_007", image_bytes=b"...", mime="image/jpeg")
# result.description -> str | None
# result.provider_used -> "siliconflow" | "openrouter" | "gemini" | None
# result.attempts -> list[AttemptRecord]
# result.failed -> bool

# For batch-end aggregate:
cascade.status  # dict[provider][failures/circuit_open/total_*]
cascade.total_usage()  # dict[provider, int]  — success counts
```

From `lib/siliconflow_balance.py`:
```python
from lib.siliconflow_balance import (
    check_siliconflow_balance,       # () -> Decimal (raises BalanceCheckError)
    estimate_cost,                   # (remaining_articles, avg_images) -> Decimal
    should_warn,                     # (balance, estimated_cost) -> bool
    should_switch_to_openrouter,     # (balance) -> bool
    BalanceCheckError,
)
```

Existing `image_pipeline.py` public signature (MUST PRESERVE):
```python
def describe_images(paths: list[Path]) -> dict[Path, str]: ...
def get_last_describe_stats() -> dict | None: ...
def emit_batch_complete(*, filter_stats, download_input_count, download_failed, describe_stats, total_ms) -> None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Refactor image_pipeline.describe_images() to use VisionCascade + balance helpers</name>
  <files>image_pipeline.py</files>
  <read_first>
    - image_pipeline.py (full file — understand current describe_images, _describe_one, _describe_via_* helpers + _last_describe_stats global)
    - lib/vision_cascade.py (from 13-00 — VisionCascade, CascadeResult, AllProvidersExhausted429Error)
    - lib/siliconflow_balance.py (from 13-01 — check_siliconflow_balance, should_switch_to_openrouter)
    - tests/unit/test_image_pipeline.py (existing describe_images tests — they must continue to pass)
    - .planning/phases/13-vision-cascade/13-CONTEXT.md (§decisions §Integration into image_pipeline.py)
  </read_first>
  <behavior>
    - `describe_images([p1, p2])` with mocked `VisionCascade.describe` returning successful CascadeResults → returns `{p1: "desc1", p2: "desc2"}` (preserves legacy dict return)
    - `describe_images([])` → returns `{}` + does NOT call balance check (no images = no cost)
    - With env var `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1` → balance check is skipped (test hook so tests don't need network)
    - When `check_siliconflow_balance()` returns `Decimal("0.03")` (< ¥0.05) → subsequent `describe_images` calls use a cascade with providers=["openrouter", "gemini"] (SiliconFlow removed); logger.warning includes "switching to OpenRouter"
    - When `BalanceCheckError` raised by pre-batch check → describe_images still proceeds (logs warning, continues with default cascade; does NOT crash)
    - When `AllProvidersExhausted429Error` raised on any image → describe_images catches, logs clear operator message, and returns partial dict (images processed so far) + a stop-batch signal (e.g., sets `_last_describe_stats["batch_stopped_429"] = True`)
    - `get_last_describe_stats()` post-call includes new keys: `circuit_opens` (list of providers with circuit_open=True at end), `gemini_share` (gemini_success / total_success, or 0.0 if no successes)
    - Batch-end logger.warning emitted if `gemini_share > 0.05` OR any provider circuit still open (CASC-05 alerts)
  </behavior>
  <action>
Refactor `image_pipeline.py`. Specifically:

1. **Add imports** at top of file:
```python
from decimal import Decimal
from lib.vision_cascade import (
    VisionCascade,
    CascadeResult,
    AllProvidersExhausted429Error,
    DEFAULT_PROVIDERS,
)
from lib.siliconflow_balance import (
    check_siliconflow_balance,
    should_switch_to_openrouter,
    BalanceCheckError,
)
```

2. **Replace `_describe_one` cascade logic** — delete the Gemini-first try/except ladder. Keep the three `_describe_via_*` helpers ONLY IF needed by legacy callers; otherwise delete (planner's discretion — document choice in commit message). The new cascade lives entirely in `lib.vision_cascade`.

3. **Rewrite `describe_images`** (new body, preserves signature):

```python
def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe images via VisionCascade (SiliconFlow → OpenRouter → Gemini).

    Phase 13 CASC-01/05/06 rewire. Signature preserved for backward-compat with
    multimodal_ingest.py and ingest_wechat.py. New behavior surfaced via
    get_last_describe_stats().
    """
    global _last_describe_stats

    result: dict[Path, str] = {}
    paths_list = list(paths)
    sleep_secs = float(os.environ.get("VISION_INTER_IMAGE_SLEEP", _DESCRIBE_INTER_IMAGE_SLEEP_SECS))

    if not paths_list:
        _last_describe_stats = {"provider_mix": {}, "vision_success": 0, "vision_error": 0, "vision_timeout": 0, "circuit_opens": [], "gemini_share": 0.0}
        return result

    # CASC-06: pre-batch balance check (skippable for tests)
    skip_balance = os.environ.get("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "").strip() == "1"
    force_openrouter_primary = False
    if not skip_balance:
        try:
            balance = check_siliconflow_balance()
            estimated = Decimal(len(paths_list)) * Decimal("0.0013")
            if balance < estimated:
                logger.warning(
                    "SiliconFlow balance ¥%.4f insufficient for ¥%.4f estimated spend — top up or expect fallback to OpenRouter",
                    balance, estimated,
                )
            if should_switch_to_openrouter(balance):
                logger.warning("SiliconFlow balance ¥%.4f below ¥0.05 floor — switching to OpenRouter-primary for this batch", balance)
                force_openrouter_primary = True
        except BalanceCheckError as e:
            logger.warning("pre-batch balance check failed (%s); proceeding with default cascade", e)

    providers = ["openrouter", "gemini"] if force_openrouter_primary else list(DEFAULT_PROVIDERS)
    cascade = VisionCascade(providers=providers, checkpoint_dir=None)

    provider_mix: dict[str, int] = {}
    vision_success = 0
    vision_error = 0
    vision_timeout = 0
    batch_stopped_429 = False

    for i, path in enumerate(paths_list):
        t0 = time.perf_counter()
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        image_id = f"img_{i:03d}"
        try:
            image_bytes = path.read_bytes()
        except OSError as e:
            logger.warning("failed to read %s: %s", path, e)
            result[path] = f"Error describing image: {e}"
            vision_error += 1
            continue

        # Mid-batch balance monitoring every 10 images (CASC-06)
        if not skip_balance and i > 0 and i % 10 == 0:
            try:
                balance = check_siliconflow_balance()
                if should_switch_to_openrouter(balance) and "siliconflow" in cascade.providers:
                    logger.warning("mid-batch balance ¥%.4f < ¥0.05 — removing SiliconFlow from cascade", balance)
                    cascade.providers = [p for p in cascade.providers if p != "siliconflow"]
            except BalanceCheckError:
                pass  # non-fatal; keep going with current cascade

        try:
            cres: CascadeResult = cascade.describe(image_id=image_id, image_bytes=image_bytes, mime=mime)
        except AllProvidersExhausted429Error as e:
            logger.error("BATCH STOP: %s — all providers 429 on single image; check quotas + balance", e)
            batch_stopped_429 = True
            result[path] = f"Error describing image: all providers 429"
            vision_error += 1
            break   # stop processing further images

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if cres.failed or cres.description is None:
            result[path] = f"Error describing image: cascade failed (attempts={len(cres.attempts)})"
            # Classify via last attempt's result_code
            last = cres.attempts[-1] if cres.attempts else None
            if last and last.result_code == "timeout":
                vision_timeout += 1
                outcome = OUTCOME_TIMEOUT
            else:
                vision_error += 1
                outcome = OUTCOME_VISION_ERROR
            _emit_log({
                "event": "image_processed", "ts": _now_iso(), "url": None,
                "local_path": str(path), "dims": None,
                "bytes": path.stat().st_size if path.exists() else None,
                "provider": None, "ms": latency_ms, "outcome": outcome,
                "error": last.error if last else "no attempts",
            })
        else:
            result[path] = cres.description
            vision_success += 1
            provider_mix[cres.provider_used] = provider_mix.get(cres.provider_used, 0) + 1
            _emit_log({
                "event": "image_processed", "ts": _now_iso(), "url": None,
                "local_path": str(path), "dims": None,
                "bytes": path.stat().st_size if path.exists() else None,
                "provider": cres.provider_used, "ms": latency_ms,
                "outcome": OUTCOME_SUCCESS, "error": None,
            })

        if i + 1 < len(paths_list) and sleep_secs > 0:
            time.sleep(sleep_secs)

    # CASC-05 batch-end aggregate + alerts
    total_success = vision_success
    gemini_share = (provider_mix.get("gemini", 0) / total_success) if total_success > 0 else 0.0
    circuit_opens = [p for p, s in cascade.status.items() if s["circuit_open"]]
    if gemini_share > 0.05:
        logger.warning("CASCADE ALERT: gemini used for %.1f%% of images (>5%% threshold) — upstream provider issues detected", gemini_share * 100)
    if circuit_opens:
        logger.warning("CASCADE ALERT: circuits still open at batch end: %s — review provider_status.json", circuit_opens)

    _last_describe_stats = {
        "provider_mix": provider_mix,
        "vision_success": vision_success,
        "vision_error": vision_error,
        "vision_timeout": vision_timeout,
        "circuit_opens": circuit_opens,
        "gemini_share": round(gemini_share, 4),
        "batch_stopped_429": batch_stopped_429,
    }
    return result
```

4. **Preserve surrounding code** (do NOT touch `download_images`, `filter_small_images`, `localize_markdown`, `save_markdown_with_images`, `emit_batch_complete`, `get_last_describe_stats`, `_emit_log`, FilterStats, OUTCOME_* constants, `_DESCRIBE_INTER_IMAGE_SLEEP_SECS`).

5. **Decide on `_describe_via_*`**:
   - RECOMMENDED: remove `_describe_one` entirely and remove `_describe_via_gemini/siliconflow/openrouter` from image_pipeline.py (they now live inside VisionCascade).
   - ALTERNATIVE: keep them as deprecated module-private helpers for any Phase 10 direct callers. Check if anything imports them:
     ```bash
     grep -rn "from image_pipeline import.*_describe" --include="*.py"
     ```
     If no external callers, remove.
   - Document choice in commit message.

6. **Backward-compat audit**: run `grep -rn "describe_images\|_describe_one" --include="*.py"` and verify no caller relied on the old cascade order (none should — they treat it as opaque).

Surgical-changes principle (CLAUDE.md): do NOT touch unrelated code. Scope is limited to `describe_images()` body + imports at top + (optional) helper cleanup.
  </action>
  <verify>
    <automated>pytest tests/unit/test_image_pipeline.py -v -x && python -c "import ast; tree = ast.parse(open('image_pipeline.py').read()); names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]; assert 'describe_images' in names; print('describe_images preserved')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from lib.vision_cascade import' image_pipeline.py` exits 0
    - `grep -q 'from lib.siliconflow_balance import' image_pipeline.py` exits 0
    - `grep -q 'VisionCascade(' image_pipeline.py` exits 0
    - `grep -q 'AllProvidersExhausted429Error' image_pipeline.py` exits 0
    - `grep -q 'gemini_share' image_pipeline.py` exits 0
    - `grep -q 'check_siliconflow_balance' image_pipeline.py` exits 0
    - `grep -q 'OMNIGRAPH_VISION_SKIP_BALANCE_CHECK' image_pipeline.py` exits 0
    - OLD buggy cascade removed: `grep -q 'except Exception as gemini_err' image_pipeline.py` exits NON-zero (old Gemini-first code gone)
    - Legacy behavior preserved: `pytest tests/unit/test_image_pipeline.py -v` exits 0 (tests for download/filter/localize still pass; describe test may need minor update to mock VisionCascade instead of _describe_one)
    - `python -c "from image_pipeline import describe_images, get_last_describe_stats; print('ok')"` exits 0
  </acceptance_criteria>
  <done>describe_images() uses VisionCascade internally; pre-batch + mid-batch balance checks wired; AllProvidersExhausted429Error handled at batch level; get_last_describe_stats returns cascade metadata. Public signature unchanged. Old cascade deleted. Existing unrelated tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Unit tests for image_pipeline cascade integration (separate from legacy tests)</name>
  <files>tests/unit/test_image_pipeline_cascade.py</files>
  <read_first>
    - image_pipeline.py (Task 1 output — new describe_images body)
    - lib/vision_cascade.py (CascadeResult + VisionCascade public API to mock)
    - lib/siliconflow_balance.py (check_siliconflow_balance + BalanceCheckError to mock)
    - tests/unit/test_image_pipeline.py (existing patterns)
    - tests/unit/test_vision_cascade.py (mocking patterns for VisionCascade)
  </read_first>
  <behavior>
    - Test 1 `describe_images_uses_VisionCascade`: mock `lib.vision_cascade.VisionCascade.describe` to return a CascadeResult with description="stub desc" + provider_used="siliconflow". Call `describe_images([p1])`. Assert result == {p1: "stub desc"}. Assert `VisionCascade` was instantiated with `providers=DEFAULT_PROVIDERS`.
    - Test 2 `cascade_order_is_siliconflow_first`: inspect the providers arg at VisionCascade instantiation → assert first element is "siliconflow" (verifies Phase 13 reordering took effect).
    - Test 3 `balance_check_skipped_with_env_flag`: set `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1` + mock `check_siliconflow_balance` to raise (should NOT be called). Verify `describe_images([p1])` succeeds without balance check.
    - Test 4 `balance_warning_emitted_when_insufficient`: skip env flag; mock `check_siliconflow_balance` → `Decimal("0.01")`; 100 paths → `estimate_cost(100 images × 0.0013) = 0.13`. Verify caplog captures a WARNING mentioning "insufficient".
    - Test 5 `low_balance_switches_to_openrouter_primary`: mock balance → `Decimal("0.03")` (< ¥0.05). Verify `VisionCascade` is instantiated with providers=["openrouter", "gemini"] (NO siliconflow).
    - Test 6 `balance_error_does_not_crash`: mock `check_siliconflow_balance` to raise `BalanceCheckError("timeout")`. Verify `describe_images([p1])` still proceeds with default cascade + logs warning.
    - Test 7 `all_providers_429_stops_batch`: mock cascade.describe to raise `AllProvidersExhausted429Error` on 2nd image. `paths=[p1, p2, p3]` → result contains p1 (success) and p2 (error), does NOT contain p3. `get_last_describe_stats()["batch_stopped_429"] is True`.
    - Test 8 `empty_paths_list_skips_balance_check`: `describe_images([])` → `{}`. `check_siliconflow_balance` NOT called.
    - Test 9 `batch_end_alert_if_gemini_share_high`: mock cascade to return provider_used="gemini" for 3 of 10 images (30%). Verify WARNING with "gemini used for 30.0%" (>5% threshold).
    - Test 10 `batch_end_alert_if_circuit_open`: mock cascade.status to have siliconflow.circuit_open=True at end. Verify WARNING with "circuits still open".
    - Test 11 `get_last_describe_stats_has_new_keys`: after a successful batch, `stats["circuit_opens"]` is a list, `stats["gemini_share"]` is a float, `stats["batch_stopped_429"]` is a bool.
    - Test 12 `mid_batch_balance_recheck_every_10_images`: supply 25 paths. Mock `check_siliconflow_balance` to return ¥1.00 first call, ¥0.04 second call. Verify at i=10 the cascade.providers gets siliconflow removed.
  </behavior>
  <action>
Create `tests/unit/test_image_pipeline_cascade.py`. Use these mocking strategies:

```python
from unittest.mock import MagicMock, patch
from decimal import Decimal
import pytest
from pathlib import Path

from lib.vision_cascade import CascadeResult, AttemptRecord, AllProvidersExhausted429Error
from lib.siliconflow_balance import BalanceCheckError

def _ok_result(desc="stub desc", provider="siliconflow"):
    return CascadeResult(
        description=desc,
        provider_used=provider,
        attempts=[AttemptRecord(provider=provider, result_code="success", latency_ms=100, desc_chars=len(desc))],
        failed=False,
    )
```

Patch strategy (IMPORTANT — patch at the import site in `image_pipeline`, not at the definition site in `lib.*`):
```python
mocker.patch("image_pipeline.VisionCascade")
mocker.patch("image_pipeline.check_siliconflow_balance", return_value=Decimal("5.43"))
```

For Test 1, use `mocker.patch` to capture VisionCascade constructor calls:
```python
mock_cls = mocker.patch("image_pipeline.VisionCascade")
mock_instance = MagicMock()
mock_instance.describe.return_value = _ok_result()
mock_instance.status = {"siliconflow": {"circuit_open": False, "total_successes": 1}, ...}
mock_instance.providers = ["siliconflow", "openrouter", "gemini"]
mock_cls.return_value = mock_instance
```

For Test 2, inspect `mock_cls.call_args.kwargs["providers"]` (or `call_args.args[0]` depending on how image_pipeline calls it).

For Test 12 (mid-batch recheck), use `side_effect` to return different values on each call:
```python
mock_check = mocker.patch("image_pipeline.check_siliconflow_balance")
mock_check.side_effect = [Decimal("1.00"), Decimal("0.04"), Decimal("0.04"), Decimal("0.04")]  # one pre-batch, then every 10th image
```

For caplog-based assertions (Tests 4, 9, 10), use pytest's `caplog` fixture:
```python
def test_balance_warning(caplog, tmp_path, mocker, monkeypatch):
    caplog.set_level(logging.WARNING)
    # ... setup ...
    describe_images([p1] * 100)
    assert any("insufficient" in r.message for r in caplog.records)
```

Also monkeypatch `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK` per test — default is to delete it except where you explicitly want balance skipping.

Create at least 12 tests covering the 12 behaviors. Each test should fit in ≤25 lines.
  </action>
  <verify>
    <automated>pytest tests/unit/test_image_pipeline_cascade.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - Test count: `grep -cE '^def test_' tests/unit/test_image_pipeline_cascade.py` ≥ 10
    - `pytest tests/unit/test_image_pipeline_cascade.py -v` exits 0
    - `grep -q 'AllProvidersExhausted429Error' tests/unit/test_image_pipeline_cascade.py` exits 0
    - `grep -q 'BalanceCheckError' tests/unit/test_image_pipeline_cascade.py` exits 0
    - `grep -q 'gemini_share' tests/unit/test_image_pipeline_cascade.py` exits 0
    - `grep -q 'OMNIGRAPH_VISION_SKIP_BALANCE_CHECK' tests/unit/test_image_pipeline_cascade.py` exits 0
    - `grep -q 'image_pipeline.VisionCascade' tests/unit/test_image_pipeline_cascade.py` exits 0 (verifies patches at the correct import site)
    - Regression: `pytest tests/unit/test_image_pipeline.py -v` still passes (legacy describe/download/filter tests)
  </acceptance_criteria>
  <done>≥10 integration unit tests pass. Cascade order verified, balance warning verified, mid-batch switch verified, all-429 stop verified, alert emissions verified. Legacy test_image_pipeline.py still green.</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/test_image_pipeline_cascade.py tests/unit/test_image_pipeline.py tests/unit/test_vision_cascade.py tests/unit/test_siliconflow_balance.py -v` — all tests pass together
- `grep` verifies imports, VisionCascade instantiation, balance-check wiring, alert keywords
- `python -c "from image_pipeline import describe_images, get_last_describe_stats; stats = get_last_describe_stats(); print('ok')"` — module loads clean
</verification>

<success_criteria>
- [ ] `image_pipeline.describe_images` delegates to VisionCascade with providers=["siliconflow", "openrouter", "gemini"] by default
- [ ] Pre-batch balance check runs once + emits warning if insufficient
- [ ] Mid-batch balance check every 10 images + removes SiliconFlow from cascade if < ¥0.05
- [ ] `AllProvidersExhausted429Error` caught at batch level → stops cleanly with operator log
- [ ] `get_last_describe_stats()` includes new keys: circuit_opens, gemini_share, batch_stopped_429
- [ ] Batch-end alerts for gemini_share > 5% OR circuit still open
- [ ] Public signature of `describe_images(paths) -> dict[Path, str]` unchanged
- [ ] Legacy tests in `test_image_pipeline.py` still pass (backward compat)
- [ ] ≥10 new integration tests all passing
</success_criteria>

<output>
After completion, create `.planning/phases/13-vision-cascade/13-02-SUMMARY.md` with:
- Diff summary: what was replaced vs. preserved in image_pipeline.py
- Decision: removed `_describe_one`/`_describe_via_*` or kept as deprecated? Document rationale.
- Integration gotchas for Plan 13-03 (integration tests) — e.g., which env vars to set, which fixtures to use
</output>
