---
revised: "2026-05-01 — v3.1 closure alignment (commit 2b38e98). Added D-BENCH-PRECHECK: `lib/siliconflow_balance.py` imports `config` at module load to guarantee `~/.hermes/.env` is sourced before any key reads; `scripts/bench_ingest_fixture.py::_balance_precheck()` is refactored to delegate to `check_siliconflow_balance()` (no direct os.environ reads). Absorbs v3.1 closure Finding 2 from docs/MILESTONE_v3.1_CLOSURE.md §6.2."
phase: 13-vision-cascade
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/siliconflow_balance.py
  - tests/unit/test_siliconflow_balance.py
  - scripts/bench_ingest_fixture.py
  - tests/unit/test_bench_precheck_delegation.py
autonomous: true
requirements:
  - CASC-06

must_haves:
  truths:
    - "check_siliconflow_balance() calls GET https://api.siliconflow.cn/v1/user/info with Bearer token and returns Decimal balance from data.balance field"
    - "estimate_cost(remaining_articles, avg_images_per_article) returns Decimal = remaining_articles × avg_images × ¥0.0013"
    - "should_warn(balance, estimated_cost) returns True when balance < estimated_cost OR balance < ¥0.05"
    - "should_switch_to_openrouter(balance) returns True when balance < ¥0.05 (hard cutoff)"
    - "Missing SILICONFLOW_API_KEY raises a clear error with remediation message"
    - "HTTP failures (timeout, 5xx) raise BalanceCheckError so caller can degrade gracefully without crashing the batch"
    - "lib/siliconflow_balance.py imports config at module load so ~/.hermes/.env is sourced into os.environ before any key reads (D-BENCH-PRECHECK, absorbs v3.1 Finding 2)"
    - "scripts/bench_ingest_fixture.py::_balance_precheck() delegates to lib.siliconflow_balance.check_siliconflow_balance() with NO direct os.environ.get('SILICONFLOW_API_KEY') call; the four output branches (skipped / warning-ok / warning-insufficient / failed) are preserved as a thin mapper"
  artifacts:
    - path: "lib/siliconflow_balance.py"
      provides: "Balance API wrapper + cost estimation + warning thresholds"
      contains: "def check_siliconflow_balance"
      min_lines: 80
    - path: "tests/unit/test_siliconflow_balance.py"
      provides: "Unit tests with mocked requests.get covering success/timeout/HTTP errors/missing key/threshold math"
      contains: "def test_"
      min_lines: 100
    - path: "scripts/bench_ingest_fixture.py"
      provides: "_balance_precheck() refactored to delegate to lib.siliconflow_balance (D-BENCH-PRECHECK)"
      contains: "from lib.siliconflow_balance import"
    - path: "tests/unit/test_bench_precheck_delegation.py"
      provides: "Regression test: bench precheck no longer emits balance_precheck_skipped when SILICONFLOW_API_KEY is only in ~/.hermes/.env (not process env)"
      contains: "def test_"
      min_lines: 40
  key_links:
    - from: "lib/siliconflow_balance.py"
      to: "requests.get"
      via: "HTTP call to api.siliconflow.cn/v1/user/info"
      pattern: "requests\\.get.*api\\.siliconflow\\.cn/v1/user/info"
    - from: "tests/unit/test_siliconflow_balance.py"
      to: "lib.siliconflow_balance.check_siliconflow_balance"
      via: "mocked via mocker.patch('lib.siliconflow_balance.requests.get')"
      pattern: "mocker\\.patch.*siliconflow_balance"
    - from: "scripts/bench_ingest_fixture.py::_balance_precheck"
      to: "lib.siliconflow_balance.check_siliconflow_balance"
      via: "direct delegation — no re-implementation of HTTP call or env-read"
      pattern: "from lib.siliconflow_balance import check_siliconflow_balance"
---

<objective>
Build `lib/siliconflow_balance.py` — balance API wrapper, cost estimation, and warning-threshold helpers for CASC-06. Lightweight sync HTTP module; no persistent state (caller/integrator Plan 13-02 decides when to call and how often).

Purpose: Before each batch + every 10 images during a batch, we need to know whether SiliconFlow has enough balance to continue or whether we should switch to OpenRouter early. Avoids the failure mode where batch runs halfway on SiliconFlow then silently flips to OpenRouter with no operator warning.

Output:
- `lib/siliconflow_balance.py` — 4 public functions: `check_siliconflow_balance`, `estimate_cost`, `should_warn`, `should_switch_to_openrouter`; 1 exception class
- `tests/unit/test_siliconflow_balance.py` — ≥6 unit tests
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/13-vision-cascade/13-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
@lib/__init__.py
@image_pipeline.py
@tests/conftest.py

<interfaces>
<!-- No prior art to import; this is a new module. Standard patterns from config.py + image_pipeline.py apply. -->

External API contract (SiliconFlow docs):
```
GET https://api.siliconflow.cn/v1/user/info
Headers: Authorization: Bearer <SILICONFLOW_API_KEY>
Response (200): {
  "code": 20000,
  "message": "OK",
  "status": true,
  "data": {
    "id": "...",
    "name": "...",
    "email": "...",
    "balance": "5.43000000"   # CNY, string-serialized decimal
  }
}
```

Price constant (from CONTEXT §decisions): SiliconFlow Qwen3-VL-32B costs **¥0.0013 per image**.

Thresholds (from CONTEXT §decisions §CASC-06):
- Mid-batch hard cutoff: balance < ¥0.05 → switch to OpenRouter
- Pre-batch warning: balance < estimated remaining cost
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement lib/siliconflow_balance.py with 4 pure functions + custom exception</name>
  <files>lib/siliconflow_balance.py</files>
  <read_first>
    - .planning/phases/13-vision-cascade/13-CONTEXT.md (§specifics — balance check reference code)
    - image_pipeline.py (sync HTTP pattern with requests + error handling style)
    - lib/__init__.py (current public API — do NOT export from lib; keep siliconflow_balance as a separate importable module)
    - config.py (env var loading pattern)
  </read_first>
  <behavior>
    - `check_siliconflow_balance()` with mocked `requests.get` returning `{"data":{"balance":"5.43"}}` → returns `Decimal("5.43")`
    - `check_siliconflow_balance()` when `SILICONFLOW_API_KEY` unset → raises `BalanceCheckError` with remediation text (mentions the env var name)
    - `check_siliconflow_balance()` when HTTP returns 500 → raises `BalanceCheckError` (does NOT propagate `requests.HTTPError` verbatim)
    - `check_siliconflow_balance()` when `requests.get` raises `Timeout` → raises `BalanceCheckError` with "timeout" in message
    - `estimate_cost(100, 10)` → `Decimal("1.30")` (100 * 10 * 0.0013)
    - `estimate_cost(0, 10)` → `Decimal("0")` (no articles = no cost)
    - `should_warn(Decimal("1.00"), Decimal("1.30"))` → True (balance < estimated)
    - `should_warn(Decimal("5.00"), Decimal("1.30"))` → False (enough budget)
    - `should_warn(Decimal("0.04"), Decimal("0.01"))` → True (below hard floor regardless of estimate)
    - `should_switch_to_openrouter(Decimal("0.04"))` → True
    - `should_switch_to_openrouter(Decimal("0.05"))` → False (exact threshold — strict less-than)
    - `should_switch_to_openrouter(Decimal("1.00"))` → False
  </behavior>
  <action>
Create `lib/siliconflow_balance.py` with exactly this structure. Copy verbatim from CONTEXT §specifics for the balance-check reference, then add helpers + error class:

```python
"""SiliconFlow balance API + cost estimation for Phase 13 CASC-06.

Pure functions + one exception. Caller (image_pipeline integration Plan 13-02)
decides when to call and how to react to warnings. No module-level cache,
no module state — balance fluctuates; always fresh.
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

# CASC-06 LOCKED constants.
SILICONFLOW_PRICE_PER_IMAGE = Decimal("0.0013")   # ¥ per image for Qwen3-VL-32B
OPENROUTER_SWITCH_THRESHOLD = Decimal("0.05")     # ¥ — switch to OpenRouter below this
BALANCE_API_TIMEOUT_SECS = 5.0

_BALANCE_URL = "https://api.siliconflow.cn/v1/user/info"


class BalanceCheckError(RuntimeError):
    """Raised when balance cannot be fetched (missing key, HTTP error, timeout).
    Caller decides whether to abort batch, warn, or proceed assuming OK."""


def check_siliconflow_balance() -> Decimal:
    """Fetch current SiliconFlow balance in CNY.

    Raises:
        BalanceCheckError: on missing API key, HTTP error, timeout, or parse failure.
    """
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        raise BalanceCheckError(
            "SILICONFLOW_API_KEY not set — required for balance check. "
            "Add to ~/.hermes/.env or export in shell."
        )
    try:
        resp = requests.get(
            _BALANCE_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=BALANCE_API_TIMEOUT_SECS,
        )
    except requests.Timeout as e:
        raise BalanceCheckError(f"timeout fetching SiliconFlow balance: {e}") from e
    except requests.RequestException as e:
        raise BalanceCheckError(f"network error fetching SiliconFlow balance: {e}") from e

    if resp.status_code != 200:
        raise BalanceCheckError(
            f"SiliconFlow balance HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        balance_str = resp.json()["data"]["balance"]
        return Decimal(str(balance_str))
    except (KeyError, ValueError, TypeError) as e:
        raise BalanceCheckError(
            f"malformed balance response: {resp.text[:200]}"
        ) from e


def estimate_cost(remaining_articles: int, avg_images_per_article: int) -> Decimal:
    """Estimate SiliconFlow cost for remaining batch in CNY.

    Cost model: remaining_articles × avg_images_per_article × ¥0.0013/image.
    Returns Decimal("0") if either input is 0 or negative (graceful — caller
    may pass 0 on a small batch).
    """
    articles = max(0, remaining_articles)
    images = max(0, avg_images_per_article)
    return Decimal(articles) * Decimal(images) * SILICONFLOW_PRICE_PER_IMAGE


def should_warn(balance: Decimal, estimated_cost: Decimal) -> bool:
    """Return True if operator should see a pre-batch / mid-batch warning.

    Two trigger conditions (either):
        1. balance < estimated_cost    (not enough for planned work)
        2. balance < OPENROUTER_SWITCH_THRESHOLD  (already at critical floor)
    """
    return balance < estimated_cost or balance < OPENROUTER_SWITCH_THRESHOLD


def should_switch_to_openrouter(balance: Decimal) -> bool:
    """Return True if cascade should switch to OpenRouter-only for remaining images.

    Strict less-than against OPENROUTER_SWITCH_THRESHOLD (¥0.05).
    Rationale (CASC-06): prevents partial batch where half images have SiliconFlow
    descriptions and half have OpenRouter.
    """
    return balance < OPENROUTER_SWITCH_THRESHOLD
```

Do NOT add this module to `lib/__init__.py` exports. Callers import as `from lib.siliconflow_balance import check_siliconflow_balance, estimate_cost, should_warn, should_switch_to_openrouter, BalanceCheckError`.
  </action>
  <verify>
    <automated>python -c "from lib.siliconflow_balance import check_siliconflow_balance, estimate_cost, should_warn, should_switch_to_openrouter, BalanceCheckError, SILICONFLOW_PRICE_PER_IMAGE, OPENROUTER_SWITCH_THRESHOLD; from decimal import Decimal; assert estimate_cost(100, 10) == Decimal('1.30'); assert should_switch_to_openrouter(Decimal('0.04')) is True; assert should_switch_to_openrouter(Decimal('0.05')) is False; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'def check_siliconflow_balance' lib/siliconflow_balance.py` exits 0
    - `grep -q 'def estimate_cost' lib/siliconflow_balance.py` exits 0
    - `grep -q 'def should_warn' lib/siliconflow_balance.py` exits 0
    - `grep -q 'def should_switch_to_openrouter' lib/siliconflow_balance.py` exits 0
    - `grep -q 'class BalanceCheckError' lib/siliconflow_balance.py` exits 0
    - `grep -q 'SILICONFLOW_PRICE_PER_IMAGE = Decimal."0.0013"' lib/siliconflow_balance.py` exits 0
    - `grep -q 'OPENROUTER_SWITCH_THRESHOLD = Decimal."0.05"' lib/siliconflow_balance.py` exits 0
    - `grep -q 'api\.siliconflow\.cn/v1/user/info' lib/siliconflow_balance.py` exits 0
    - `python -c "from lib.siliconflow_balance import *"` exits 0
  </acceptance_criteria>
  <done>Module has all 4 public functions + 1 exception class + 3 constants. All pure logic (no persistent state). Importable cleanly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Unit tests covering balance API + estimate + thresholds</name>
  <files>tests/unit/test_siliconflow_balance.py</files>
  <read_first>
    - lib/siliconflow_balance.py (Task 1 output)
    - tests/conftest.py (fixture patterns)
    - tests/unit/test_image_pipeline.py (mocker.patch requests.get/post pattern)
  </read_first>
  <behavior>
    - Test 1: `check_siliconflow_balance_success` — mock requests.get returns 200 with `{"data":{"balance":"5.43"}}` + env has SILICONFLOW_API_KEY → returns `Decimal("5.43")`
    - Test 2: `check_siliconflow_balance_missing_key` — unset SILICONFLOW_API_KEY → raises BalanceCheckError, message contains "SILICONFLOW_API_KEY"
    - Test 3: `check_siliconflow_balance_http_500` — mock 500 → raises BalanceCheckError, message contains "500"
    - Test 4: `check_siliconflow_balance_timeout` — mock raises requests.Timeout → raises BalanceCheckError, message contains "timeout"
    - Test 5: `check_siliconflow_balance_malformed_json` — mock returns 200 but json has no `data.balance` key → raises BalanceCheckError
    - Test 6: `check_siliconflow_balance_network_error` — mock raises `requests.ConnectionError` → raises BalanceCheckError
    - Test 7: `estimate_cost_basic` — `estimate_cost(100, 10) == Decimal("1.30")`, `estimate_cost(0, 10) == Decimal("0")`, `estimate_cost(-5, 10) == Decimal("0")` (graceful negative)
    - Test 8: `should_warn_insufficient_balance` — `should_warn(Decimal("1.00"), Decimal("1.30")) is True`
    - Test 9: `should_warn_enough_budget` — `should_warn(Decimal("5.00"), Decimal("1.30")) is False`
    - Test 10: `should_warn_below_hard_floor` — `should_warn(Decimal("0.04"), Decimal("0.01")) is True` (even though 0.04 > 0.01 estimate)
    - Test 11: `should_switch_to_openrouter_boundary` — verify exact boundary: 0.04 → True, 0.05 → False (strict less-than), 1.00 → False
    - Test 12: `authorization_header_sent` — verify the Bearer token format in request headers
  </behavior>
  <action>
Create `tests/unit/test_siliconflow_balance.py`. Use `pytest.mark.unit` marker (matches repo convention from test_image_pipeline.py). Use `mocker.patch("lib.siliconflow_balance.requests.get")` to mock. Use `monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key-xxx")` for happy-path tests and `monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)` for missing-key test.

Helper for mock response:
```python
def _mock_resp(status_code=200, json_body=None, raise_exc=None):
    if raise_exc is not None:
        raise raise_exc
    r = MagicMock()
    r.status_code = status_code
    r.text = json.dumps(json_body or {})
    r.json.return_value = json_body or {}
    return r
```

For Test 12 (authorization header verification), capture kwargs of `requests.get` via `mocker.patch.return_value = _mock_resp(...)` + `assert "Bearer test-key-xxx" in mock_get.call_args.kwargs["headers"]["Authorization"]`.

Cover all 12 behaviors. Each test ≤20 lines. Use `pytest.raises(BalanceCheckError, match="...")` where message content is asserted.
  </action>
  <verify>
    <automated>pytest tests/unit/test_siliconflow_balance.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - Test count: `grep -cE '^def test_' tests/unit/test_siliconflow_balance.py` ≥ 10
    - `pytest tests/unit/test_siliconflow_balance.py -v` exits 0, all passing
    - `grep -q 'Bearer' tests/unit/test_siliconflow_balance.py` exits 0 (Test 12 asserts auth header)
    - `grep -q 'BalanceCheckError' tests/unit/test_siliconflow_balance.py` exits 0
    - `grep -q 'Decimal' tests/unit/test_siliconflow_balance.py` exits 0 (uses Decimal for precise math assertions)
  </acceptance_criteria>
  <done>≥10 unit tests pass. Balance API covered for success/timeout/HTTP-error/missing-key/malformed-json. Threshold math verified with Decimal precision including boundary conditions.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Refactor bench precheck to delegate to lib (D-BENCH-PRECHECK — absorbs v3.1 Finding 2)</name>
  <files>
    - scripts/bench_ingest_fixture.py
    - tests/unit/test_bench_precheck_delegation.py
  </files>

  <read_first>
    - scripts/bench_ingest_fixture.py lines 240-290 (current `_balance_precheck()` implementation)
    - lib/siliconflow_balance.py (just created — the `check_siliconflow_balance()` + `BalanceCheckError` public API)
    - config.py (env-loading mechanism — confirm `lib/siliconflow_balance.py` imports this)
    - docs/HERMES_E2E_VERIFICATION_v3.1_20260501.md §5 (symptom description)
    - docs/MILESTONE_v3.1_CLOSURE.md §6.2 (routing rationale)
    - .planning/phases/13-vision-cascade/13-CONTEXT.md § D-BENCH-PRECHECK
  </read_first>

  <action>
**Step 1 — Ensure `lib/siliconflow_balance.py` imports `config` at module load (edit Task 1's module):**

In `lib/siliconflow_balance.py`, add at top of file (after stdlib imports, before `import requests`):

```python
# Trigger ~/.hermes/.env load before any SILICONFLOW_API_KEY reads.
# This is the correct-by-construction guarantee for D-BENCH-PRECHECK
# (absorbs v3.1 closure Finding 2).
import config  # noqa: F401 — import for side effect (dotenv load)
```

Acceptance: `grep -q 'import config' lib/siliconflow_balance.py`.

**Step 2 — Refactor `_balance_precheck()` in `scripts/bench_ingest_fixture.py` (lines 241-290):**

Replace the current body (which reads `os.environ` directly and makes its own HTTP call) with a thin mapper that calls into the lib module. Preserve the four output branches verbatim for backward compatibility of `benchmark_result.json` warnings.

```python
def _balance_precheck() -> dict[str, Any]:
    """Balance precheck — delegates to lib.siliconflow_balance (D-BENCH-PRECHECK 2026-05-01).

    Before 2026-05-01 this function did its own os.environ read and HTTP call,
    which produced balance_precheck_skipped when SILICONFLOW_API_KEY was only
    in ~/.hermes/.env (not in process env). The lib module now imports `config`
    at module load so env is always sourced. See docs/MILESTONE_v3.1_CLOSURE.md §6.2.

    Four branches (per D-11.05) preserved for benchmark_result.json stability:
        1. Key unset (even after .env load) → event=balance_precheck_skipped
        2. balance >= ESTIMATED_COST_CNY → event=balance_warning, status=ok
        3. balance < ESTIMATED_COST_CNY → event=balance_warning, status=insufficient_for_batch
        4. HTTP / JSON / timeout error → event=balance_precheck_failed
    Non-fatal for v3.1 gate — always returns a dict, never raises.
    """
    from lib.siliconflow_balance import (
        check_siliconflow_balance,
        BalanceCheckError,
        MissingKeyError,  # lib raises this when key still missing after .env load
    )
    try:
        balance = check_siliconflow_balance()  # Decimal, e.g. Decimal("5.43")
    except MissingKeyError:
        return {
            "event": "balance_precheck_skipped",
            "provider": "siliconflow",
            "reason": "api_key_unset",
        }
    except BalanceCheckError as e:
        return {
            "event": "balance_precheck_failed",
            "provider": "siliconflow",
            "error": str(e),
        }

    status = "ok" if float(balance) >= ESTIMATED_COST_CNY else "insufficient_for_batch"
    return {
        "event": "balance_warning",
        "provider": "siliconflow",
        "balance_cny": float(balance),
        "estimated_cost_cny": ESTIMATED_COST_CNY,
        "status": status,
    }
```

Remove the direct `os.environ.get("SILICONFLOW_API_KEY", ...)` call. Remove the `urllib.request` HTTP code block. Remove `SILICONFLOW_URL` and `BALANCE_TIMEOUT_S` constants (now owned by lib module). Keep `ESTIMATED_COST_CNY` since that's bench-specific.

**Step 3 — Add regression test:**

Create `tests/unit/test_bench_precheck_delegation.py`:

```python
"""Regression test for D-BENCH-PRECHECK (v3.1 closure Finding 2).

Before 2026-05-01: bench _balance_precheck() read os.environ directly and
emitted balance_precheck_skipped when SILICONFLOW_API_KEY was only in
~/.hermes/.env (not loaded into process env). Production Vision path worked
correctly; only the precheck helper was buggy.

This test verifies the fix: bench precheck delegates to lib.siliconflow_balance,
which imports config to auto-load .env. No direct os.environ reads remain.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


def test_bench_precheck_no_longer_reads_os_environ_directly():
    """Regression: grep the bench source for the old anti-pattern."""
    bench_src = open("scripts/bench_ingest_fixture.py").read()

    # The direct os.environ.get("SILICONFLOW_API_KEY"...) pattern MUST be gone
    # from _balance_precheck(). Any remaining os.environ read would reintroduce
    # the Hermes 2026-05-01 bug.
    precheck_start = bench_src.index("def _balance_precheck")
    precheck_end = bench_src.index("\ndef ", precheck_start + 1)
    precheck_body = bench_src[precheck_start:precheck_end]
    assert 'os.environ.get("SILICONFLOW_API_KEY"' not in precheck_body, \
        "_balance_precheck must delegate to lib.siliconflow_balance (D-BENCH-PRECHECK)"
    assert "from lib.siliconflow_balance import" in precheck_body, \
        "_balance_precheck must import from lib.siliconflow_balance"


def test_bench_precheck_warning_branch():
    """When lib returns Decimal, bench emits balance_warning with status=ok."""
    from scripts.bench_ingest_fixture import _balance_precheck
    with patch("lib.siliconflow_balance.check_siliconflow_balance", return_value=Decimal("10.00")):
        result = _balance_precheck()
    assert result["event"] == "balance_warning"
    assert result["status"] == "ok"
    assert result["balance_cny"] == 10.0


def test_bench_precheck_insufficient_branch():
    """When balance < ESTIMATED_COST_CNY, bench emits insufficient_for_batch."""
    from scripts.bench_ingest_fixture import _balance_precheck
    with patch("lib.siliconflow_balance.check_siliconflow_balance", return_value=Decimal("0.001")):
        result = _balance_precheck()
    assert result["event"] == "balance_warning"
    assert result["status"] == "insufficient_for_batch"


def test_bench_precheck_skipped_branch_when_key_missing():
    """When lib raises MissingKeyError, bench emits balance_precheck_skipped."""
    from scripts.bench_ingest_fixture import _balance_precheck
    from lib.siliconflow_balance import MissingKeyError
    with patch("lib.siliconflow_balance.check_siliconflow_balance",
               side_effect=MissingKeyError("SILICONFLOW_API_KEY not set")):
        result = _balance_precheck()
    assert result["event"] == "balance_precheck_skipped"
    assert result["reason"] == "api_key_unset"


def test_bench_precheck_failed_branch_on_http_error():
    """When lib raises BalanceCheckError, bench emits balance_precheck_failed."""
    from scripts.bench_ingest_fixture import _balance_precheck
    from lib.siliconflow_balance import BalanceCheckError
    with patch("lib.siliconflow_balance.check_siliconflow_balance",
               side_effect=BalanceCheckError("HTTP 500")):
        result = _balance_precheck()
    assert result["event"] == "balance_precheck_failed"
    assert "HTTP 500" in result["error"]
```

**Step 4 — Add `MissingKeyError` to the lib module:**

In `lib/siliconflow_balance.py`, alongside `BalanceCheckError`, add a distinct exception so the bench mapper can route `balance_precheck_skipped` vs `balance_precheck_failed` cleanly:

```python
class MissingKeyError(BalanceCheckError):
    """SILICONFLOW_API_KEY missing even after ~/.hermes/.env load.
    Subclasses BalanceCheckError so existing `except BalanceCheckError` catches still work.
    """
```

`check_siliconflow_balance()` raises `MissingKeyError("SILICONFLOW_API_KEY not set in env or ~/.hermes/.env")` when both lookups fail. Update Task 1's error-handling path accordingly.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_bench_precheck_delegation.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q 'from lib.siliconflow_balance import' scripts/bench_ingest_fixture.py`
    - `grep -c 'os.environ.get("SILICONFLOW_API_KEY"' scripts/bench_ingest_fixture.py` returns 0 (pattern removed from bench)
    - `grep -q 'import config' lib/siliconflow_balance.py`
    - `grep -q 'class MissingKeyError' lib/siliconflow_balance.py`
    - `.venv/Scripts/python -m pytest tests/unit/test_bench_precheck_delegation.py -v` exits 0
    - `.venv/Scripts/python -m pytest tests/unit/test_siliconflow_balance.py -v` still passes (Task 1+2 tests unchanged)
    - `DEEPSEEK_API_KEY=dummy .venv/Scripts/python -c "import scripts.bench_ingest_fixture; print('OK')"` imports clean (no module-level env read errors)
  </acceptance_criteria>

  <done>
    Bench precheck delegates to lib.siliconflow_balance; no direct os.environ.get("SILICONFLOW_API_KEY") reads remain in bench script; lib imports config at module load to guarantee ~/.hermes/.env is sourced; regression test enforces both via grep assertion + mocked branch tests; v3.1 closure Finding 2 absorbed.
  </done>
</task>

</tasks>

<verification>
- `pytest tests/unit/test_siliconflow_balance.py -v` — all tests pass
- `python -c "from lib.siliconflow_balance import *; print('ok')"` — imports clean
- `grep` checks verify public API + locked constants per CASC-06
</verification>

<success_criteria>
- [ ] `lib/siliconflow_balance.py` provides `check_siliconflow_balance`, `estimate_cost`, `should_warn`, `should_switch_to_openrouter`, `BalanceCheckError`
- [ ] Price constant `¥0.0013/image` locked (CASC-06)
- [ ] OpenRouter switch threshold `¥0.05` locked (CASC-06)
- [ ] Balance API calls `GET https://api.siliconflow.cn/v1/user/info` with `Authorization: Bearer` header
- [ ] All HTTP error paths (timeout, 5xx, network, malformed) raise `BalanceCheckError` — never crash caller
- [ ] Missing env var raises with clear remediation
- [ ] ≥10 unit tests all passing
</success_criteria>

<output>
After completion, create `.planning/phases/13-vision-cascade/13-01-SUMMARY.md` with:
- Public API exported
- Threshold constants + rationale
- Example caller snippet (for 13-02 integration)
</output>
