---
phase: 13-vision-cascade
plan: 03
type: execute
wave: 3
depends_on:
  - 13-00
  - 13-01
  - 13-02
files_modified:
  - tests/integration/test_vision_cascade_e2e.py
  - tests/integration/__init__.py
autonomous: true
requirements:
  - CASC-01
  - CASC-02
  - CASC-03
  - CASC-04
  - CASC-05
  - CASC-06

must_haves:
  truths:
    - "An integration test simulates a sequence of 3 consecutive SiliconFlow 503s and asserts the circuit opens (state changes observable on disk)"
    - "An integration test simulates SiliconFlow 429 → OpenRouter 429 → Gemini 429 on the same image and asserts AllProvidersExhausted429Error is raised"
    - "An integration test simulates SiliconFlow timeout → OpenRouter 200 and asserts cascade falls through cleanly with provider_used='openrouter'"
    - "An integration test simulates recovery: 3 SiliconFlow failures → 10 skipped images (provider_used='openrouter') → probe succeeds → 11th image uses SiliconFlow again"
    - "An integration test verifies provider_status.json on disk matches in-memory state after each mutation"
    - "An integration test verifies SiliconFlow balance < ¥0.05 triggers mid-batch switch to OpenRouter-only"
    - "An integration test runs the full image_pipeline.describe_images() against a mock HTTP fixture (no real API keys required)"
  artifacts:
    - path: "tests/integration/test_vision_cascade_e2e.py"
      provides: "End-to-end integration tests for Phase 13 cascade + balance — all mocked at the HTTP layer (no real providers)"
      contains: "def test_"
      min_lines: 200
  key_links:
    - from: "tests/integration/test_vision_cascade_e2e.py"
      to: "image_pipeline.describe_images"
      via: "full batch exercise with mocked providers at requests.post level"
      pattern: "describe_images\\("
    - from: "tests/integration/test_vision_cascade_e2e.py"
      to: "lib.vision_cascade.VisionCascade"
      via: "direct VisionCascade instance for low-level state-machine tests"
      pattern: "VisionCascade\\("
---

<objective>
Ship integration tests that exercise the full Phase 13 stack (VisionCascade + siliconflow_balance + image_pipeline integration) end-to-end against mocked HTTP responses. Unit tests from 13-00/01/02 cover individual components; this plan validates they compose correctly.

Purpose: CASC-04 has a subtle "all-429 → stop batch" rule, CASC-03 has recovery-probe semantics over 10 skipped images, and CASC-06 has mid-batch SiliconFlow-removal logic. These multi-step sequences are best tested via integration: instantiate the real `VisionCascade`, mock only the HTTP layer, and run sequences of calls that exercise the state machine across many iterations.

Output:
- `tests/integration/test_vision_cascade_e2e.py` — ≥7 integration tests simulating 503/429/timeout/recovery/balance sequences
- `tests/integration/__init__.py` — ensure test dir is importable (may already exist)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/13-vision-cascade/13-CONTEXT.md
@.planning/phases/13-vision-cascade/13-00-SUMMARY.md
@.planning/phases/13-vision-cascade/13-01-SUMMARY.md
@.planning/phases/13-vision-cascade/13-02-SUMMARY.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
@image_pipeline.py
@lib/vision_cascade.py
@lib/siliconflow_balance.py
@tests/integration/test_image_pipeline_golden.py
@tests/integration/test_cognee_rotation.py
@tests/conftest.py

<interfaces>
<!-- All patched at the requests/HTTP boundary — never import real API keys -->

From `lib.vision_cascade`:
```python
from lib.vision_cascade import (
    VisionCascade,
    CascadeResult,
    AttemptRecord,
    AllProvidersExhausted429Error,
    DEFAULT_PROVIDERS,
    CIRCUIT_FAILURE_THRESHOLD,   # 3
    RECOVERY_PROBE_INTERVAL,      # 10
)
```

Mocking strategy (patches at the HTTP boundary inside vision_cascade):
```python
mocker.patch("lib.vision_cascade.requests.post")   # for SiliconFlow + OpenRouter
mocker.patch("lib.vision_cascade.generate_sync")   # for Gemini (via lib.generate_sync)
```

Helper for stubbed HTTP response:
```python
def make_post_response(status_code=200, description="stub"):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"choices": [{"message": {"content": description}}]}
    r.text = description
    return r
```

Integration test file pattern (from `tests/integration/test_image_pipeline_golden.py`, `test_cognee_rotation.py`) — uses `pytest.mark.integration`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write integration tests simulating provider failure/recovery sequences</name>
  <files>tests/integration/test_vision_cascade_e2e.py, tests/integration/__init__.py</files>
  <read_first>
    - lib/vision_cascade.py (state machine internals, _call_provider dispatch)
    - lib/siliconflow_balance.py (check_siliconflow_balance signature)
    - image_pipeline.py (describe_images for Test 7 end-to-end)
    - tests/integration/test_image_pipeline_golden.py (pattern: pytest.mark.integration, tmp_path usage)
    - tests/integration/test_cognee_rotation.py (pattern: monkeypatch env, mocker.patch at module boundary)
    - .planning/phases/13-vision-cascade/13-CONTEXT.md (§specifics — acceptance check commands)
  </read_first>
  <behavior>
    - Test 1 `circuit_opens_after_3_siliconflow_503s`: Instantiate `VisionCascade(checkpoint_dir=tmp)`. Mock `requests.post` to return 503 for SiliconFlow + 200 for OpenRouter (route by URL). Call `cascade.describe(image_id, image_bytes)` 3 times. After 3rd call: `cascade.status["siliconflow"]["circuit_open"] is True`, `cascade.status["siliconflow"]["failures"] == 3`. Verify `provider_status.json` on disk reflects this.
    - Test 2 `all_providers_429_raises_stop_batch`: Mock `requests.post` to return 429 for both SiliconFlow AND OpenRouter, and mock `generate_sync` to raise a 429-like exception. Call `cascade.describe("img_001", b"x")`. Assert `AllProvidersExhausted429Error` is raised. Verify logged message contains "img_001".
    - Test 3 `siliconflow_timeout_falls_through_to_openrouter`: Mock SiliconFlow post to raise `requests.Timeout`, OpenRouter to return 200. Call `cascade.describe(...)`. Assert result.provider_used == "openrouter", result.attempts has 2 entries with codes [timeout, success]. Assert `cascade.status["siliconflow"]["failures"] == 1` (timeout counts).
    - Test 4 `recovery_after_10_skipped_images`: Trip the circuit (3×503) on SiliconFlow first. Then 10 images with OpenRouter=200 (should use OpenRouter, SiliconFlow skipped). On image 11, mock SiliconFlow to return 200. Assert image 11's result.provider_used == "siliconflow" (probe succeeded), `cascade.status["siliconflow"]["circuit_open"] is False`, `cascade.status["siliconflow"]["failures"] == 0`.
    - Test 5 `auth_error_does_not_open_circuit`: Mock SiliconFlow to return 401, OpenRouter 200. Call 3 times. Assert `cascade.status["siliconflow"]["circuit_open"] is False` AND `cascade.status["siliconflow"]["failures"] == 0` (auth is permanent, not circuit-counted). Result.provider_used == "openrouter" on all 3.
    - Test 6 `provider_status_persists_across_instances`: First VisionCascade trips siliconflow circuit (3×503). Create SECOND VisionCascade pointing at same `checkpoint_dir`. Assert `cascade2.status["siliconflow"]["circuit_open"] is True` (loaded from disk, simulating batch restart).
    - Test 7 `image_pipeline_e2e_happy_path`: Call `image_pipeline.describe_images([p1, p2])` with `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1`. Mock `lib.vision_cascade.requests.post` to return SiliconFlow 200. Assert result has both paths with descriptions. Assert `get_last_describe_stats()["provider_mix"] == {"siliconflow": 2}`. Verify the cascade order was siliconflow-first (no Gemini calls made).
    - Test 8 `mid_batch_switch_to_openrouter_below_floor`: Call `describe_images([p1...p25])` (25 paths). Mock `check_siliconflow_balance` to return ¥1.00 first, ¥0.03 on 2nd call (at i=10). Mock SiliconFlow 200, OpenRouter 200. Assert: images 0-9 served by siliconflow, images 10+ served by openrouter (via `_last_describe_stats.provider_mix`).
    - Test 9 `gemini_alert_at_batch_end`: 10 images where SiliconFlow 503, OpenRouter 503, Gemini 200 each time. Assert caplog WARNING contains "gemini used for 100.0%" (or similar >5%) at batch end.
  </behavior>
  <action>
Create `tests/integration/test_vision_cascade_e2e.py`. Structure:

```python
"""Integration tests for Phase 13 Vision Cascade + Circuit Breaker + Balance.

All HTTP is mocked at the requests boundary — no real API keys needed.
Exercises multi-step state-machine sequences that unit tests can't cover well.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from lib.vision_cascade import (
    VisionCascade,
    CascadeResult,
    AttemptRecord,
    AllProvidersExhausted429Error,
    DEFAULT_PROVIDERS,
    CIRCUIT_FAILURE_THRESHOLD,
    RECOVERY_PROBE_INTERVAL,
)
from lib.siliconflow_balance import BalanceCheckError


pytestmark = pytest.mark.integration


# ── helpers ────────────────────────────────────────────────────────────

def make_post_response(status_code=200, content="stub description"):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    r.text = content if status_code == 200 else f"HTTP {status_code}"
    return r


def route_by_url(siliconflow_resp, openrouter_resp):
    """Return a side_effect for requests.post that routes by URL."""
    def _side_effect(url, *args, **kwargs):
        if "siliconflow" in url:
            if isinstance(siliconflow_resp, Exception):
                raise siliconflow_resp
            return siliconflow_resp() if callable(siliconflow_resp) else siliconflow_resp
        elif "openrouter" in url:
            if isinstance(openrouter_resp, Exception):
                raise openrouter_resp
            return openrouter_resp() if callable(openrouter_resp) else openrouter_resp
        raise ValueError(f"unexpected url: {url}")
    return _side_effect


@pytest.fixture
def cascade_env(monkeypatch, tmp_path):
    """Set fake API keys + checkpoint dir for VisionCascade."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test-sf")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-or")
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEY", "sk-test-gm")
    return tmp_path


# ── Tests ───────────────────────────────────────────────────────────────

def test_circuit_opens_after_3_siliconflow_503s(cascade_env, mocker):
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503, "upstream unavailable"),
            openrouter_resp=make_post_response(200, "openrouter desc"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"imgbytes")
        assert res.provider_used == "openrouter", f"image {i}"
    assert cascade.status["siliconflow"]["circuit_open"] is True
    assert cascade.status["siliconflow"]["failures"] == 3
    # Verify on-disk persistence
    status_path = cascade_env / "_batch" / "provider_status.json"
    assert status_path.exists()
    persisted = json.loads(status_path.read_text())
    assert persisted["siliconflow"]["circuit_open"] is True


def test_all_providers_429_raises_stop_batch(cascade_env, mocker):
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(429, "quota"),
            openrouter_resp=make_post_response(429, "quota"),
        ),
    )
    mocker.patch("lib.vision_cascade.generate_sync", side_effect=RuntimeError("429 quota exhausted"))
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    with pytest.raises(AllProvidersExhausted429Error, match="img_stop"):
        cascade.describe("img_stop", b"x")


def test_siliconflow_timeout_falls_through_to_openrouter(cascade_env, mocker):
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=requests.Timeout("deadline exceeded"),
            openrouter_resp=make_post_response(200, "openrouter served"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    res = cascade.describe("img_t", b"x")
    assert res.provider_used == "openrouter"
    assert res.description == "openrouter served"
    assert len(res.attempts) == 2
    assert res.attempts[0].result_code == "timeout"
    assert res.attempts[1].result_code == "success"
    assert cascade.status["siliconflow"]["failures"] == 1


def test_recovery_after_10_skipped_images(cascade_env, mocker):
    # Phase 1: trip the circuit on SiliconFlow
    call_count = {"siliconflow": 0}
    def sf_side(url, *a, **kw):
        if "siliconflow" in url:
            call_count["siliconflow"] += 1
            # 3 × 503, then (after 10 skips) 1 × 200 for the probe
            if call_count["siliconflow"] <= 3:
                return make_post_response(503)
            return make_post_response(200, "recovered sf")
        return make_post_response(200, "openrouter")
    mocker.patch("lib.vision_cascade.requests.post", side_effect=sf_side)
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    # Trip circuit (3 × 503)
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["siliconflow"]["circuit_open"] is True
    # 10 skipped images — each served by OpenRouter
    for i in range(3, 13):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.provider_used == "openrouter"
    # Image 14 triggers the probe; probe succeeds → circuit closes
    res = cascade.describe("img_probe", b"x")
    assert res.provider_used == "siliconflow"
    assert cascade.status["siliconflow"]["circuit_open"] is False
    assert cascade.status["siliconflow"]["failures"] == 0


def test_auth_error_does_not_open_circuit(cascade_env, mocker):
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(401, "bad api key"),
            openrouter_resp=make_post_response(200, "ok"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.provider_used == "openrouter"
    assert cascade.status["siliconflow"]["failures"] == 0
    assert cascade.status["siliconflow"]["circuit_open"] is False


def test_provider_status_persists_across_instances(cascade_env, mocker):
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503),
            openrouter_resp=make_post_response(200),
        ),
    )
    c1 = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        c1.describe(f"img_{i:03d}", b"x")
    assert c1.status["siliconflow"]["circuit_open"] is True
    # New instance pointing at same checkpoint dir
    c2 = VisionCascade(checkpoint_dir=cascade_env)
    assert c2.status["siliconflow"]["circuit_open"] is True
    assert c2.status["siliconflow"]["failures"] == 3


def test_image_pipeline_e2e_happy_path(cascade_env, mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(200, "siliconflow describes"),
    )
    from image_pipeline import describe_images, get_last_describe_stats
    p1 = tmp_path / "a.jpg"; p1.write_bytes(b"imgdata")
    p2 = tmp_path / "b.jpg"; p2.write_bytes(b"imgdata")
    result = describe_images([p1, p2])
    assert result[p1] == "siliconflow describes"
    assert result[p2] == "siliconflow describes"
    stats = get_last_describe_stats()
    assert stats["provider_mix"].get("siliconflow", 0) == 2
    # No Gemini calls should have happened
    assert stats["provider_mix"].get("gemini", 0) == 0


def test_mid_batch_switch_to_openrouter_below_floor(cascade_env, mocker, tmp_path, monkeypatch):
    # IMPORTANT: do NOT set SKIP_BALANCE_CHECK — we want the pre-batch + mid-batch checks to run
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    balance_seq = iter([Decimal("1.00"), Decimal("0.03"), Decimal("0.03"), Decimal("0.03")])
    mocker.patch("image_pipeline.check_siliconflow_balance", side_effect=lambda: next(balance_seq))
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(200, "sf"),
            openrouter_resp=make_post_response(200, "or"),
        ),
    )
    from image_pipeline import describe_images, get_last_describe_stats
    paths = [tmp_path / f"{i}.jpg" for i in range(25)]
    for p in paths:
        p.write_bytes(b"imgdata")
    describe_images(paths)
    mix = get_last_describe_stats()["provider_mix"]
    # First 10 images: siliconflow; images 10+ after mid-batch switch: openrouter
    assert mix.get("siliconflow", 0) == 10
    assert mix.get("openrouter", 0) == 15


def test_gemini_alert_at_batch_end(cascade_env, mocker, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503),
            openrouter_resp=make_post_response(503),
        ),
    )
    mocker.patch("lib.vision_cascade.generate_sync", return_value="gemini describes")
    from image_pipeline import describe_images
    paths = [tmp_path / f"{i}.jpg" for i in range(10)]
    for p in paths:
        p.write_bytes(b"imgdata")
    caplog.set_level(logging.WARNING)
    describe_images(paths)
    assert any("gemini used for" in r.message for r in caplog.records), (
        f"expected gemini alert, got: {[r.message for r in caplog.records]}"
    )
```

Ensure `tests/integration/__init__.py` exists (if missing, create empty). Add `pytest.mark.integration` marker to all tests. Tests should be runnable via `pytest tests/integration/test_vision_cascade_e2e.py -v` AND skippable in unit-only CI runs via `-m "not integration"`.

Edge cases to handle:
- If `image_pipeline.describe_images` imports `VisionCascade` via `from lib.vision_cascade import VisionCascade`, then patches at `image_pipeline.VisionCascade` (not `lib.vision_cascade.VisionCascade`) — but for HTTP-layer mocks we patch `lib.vision_cascade.requests.post` because that's where the real `_call_provider` methods live.
- Balance check in image_pipeline is imported as `from lib.siliconflow_balance import check_siliconflow_balance` so patch at `image_pipeline.check_siliconflow_balance`.
  </action>
  <verify>
    <automated>pytest tests/integration/test_vision_cascade_e2e.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `grep -cE '^def test_' tests/integration/test_vision_cascade_e2e.py` ≥ 7
    - `pytest tests/integration/test_vision_cascade_e2e.py -v` exits 0, all passing
    - `grep -q 'pytest.mark.integration' tests/integration/test_vision_cascade_e2e.py` exits 0 (marker set)
    - `grep -q 'AllProvidersExhausted429Error' tests/integration/test_vision_cascade_e2e.py` exits 0
    - `grep -q 'circuit_open' tests/integration/test_vision_cascade_e2e.py` exits 0
    - `grep -q 'recovery' tests/integration/test_vision_cascade_e2e.py` exits 0
    - `grep -q 'mid_batch' tests/integration/test_vision_cascade_e2e.py` exits 0
    - `grep -q 'gemini_alert' tests/integration/test_vision_cascade_e2e.py` exits 0
    - `grep -q 'provider_status.json' tests/integration/test_vision_cascade_e2e.py` exits 0 (persistence verified)
    - `ls tests/integration/__init__.py` exits 0 (file exists)
    - Combined run: `pytest tests/unit/test_vision_cascade.py tests/unit/test_siliconflow_balance.py tests/unit/test_image_pipeline_cascade.py tests/unit/test_image_pipeline.py tests/integration/test_vision_cascade_e2e.py -v` exits 0
  </acceptance_criteria>
  <done>≥7 integration tests pass, simulating the full cascade/circuit/recovery/balance state machine sequences. HTTP-layer mocking throughout (no real API calls). Combined unit + integration test suite green.</done>
</task>

</tasks>

<verification>
- `pytest tests/integration/test_vision_cascade_e2e.py -v` — all integration tests pass
- `pytest tests/ -v -m "not integration"` — unit suite unaffected (regression check)
- `pytest tests/ -v -m integration` — integration suite includes new tests
- Combined assertions from CASC-01..CASC-06 covered across unit + integration suites
</verification>

<success_criteria>
- [ ] Circuit-open sequence (3×503) verified at integration level with on-disk provider_status.json check
- [ ] All-providers-429 raises `AllProvidersExhausted429Error` verified
- [ ] Recovery probe after 10 skipped images verified (circuit re-closes on success)
- [ ] 4xx auth errors do NOT count toward circuit verified
- [ ] Cross-instance persistence (batch restart) verified
- [ ] End-to-end `image_pipeline.describe_images()` uses SiliconFlow-first verified
- [ ] Mid-batch balance switch to OpenRouter verified
- [ ] Gemini >5% alert emission verified
- [ ] Every requirement ID (CASC-01..CASC-06) has integration coverage
</success_criteria>

<output>
After completion, create `.planning/phases/13-vision-cascade/13-03-SUMMARY.md` with:
- Test count + coverage mapping (which CASC-0X each test covers)
- How to run: `pytest tests/integration/test_vision_cascade_e2e.py -v`
- Any flaky-test risk flags (e.g., tests depending on iteration order)
- Handoff note to Phase 14 (regression fixtures): these integration tests are mock-based; Phase 14 will add real-fixture-based regression tests.
</output>
