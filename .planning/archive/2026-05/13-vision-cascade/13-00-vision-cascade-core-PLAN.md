---
phase: 13-vision-cascade
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/vision_cascade.py
  - tests/unit/test_vision_cascade.py
autonomous: true
requirements:
  - CASC-01
  - CASC-02
  - CASC-03
  - CASC-04
  - CASC-05

must_haves:
  truths:
    - "VisionCascade.describe() tries SiliconFlow first, then OpenRouter, then Gemini — in that exact order"
    - "3 consecutive 503 (or timeout, or 429) errors from one provider sets circuit_open=True for that provider"
    - "While circuit_open=True, the provider is skipped until 10 images have been skipped, at which point one recovery probe is attempted"
    - "A successful probe resets failures=0 and circuit_open=False"
    - "4xx auth errors (401/403/422) do NOT increment the circuit failure counter; they log as permanent and fall through"
    - "provider_status is persisted to the checkpoint dir via atomic write after every state change"
    - "Per-image structured JSON log lines are emitted for every attempt (provider, attempt, result, latency_ms)"
  artifacts:
    - path: "lib/vision_cascade.py"
      provides: "VisionCascade class + CascadeResult dataclass + provider adapter helpers"
      contains: "class VisionCascade"
      min_lines: 200
    - path: "tests/unit/test_vision_cascade.py"
      provides: "Unit tests with mocked providers covering 503/429/timeout/4xx/circuit-breaker/recovery"
      contains: "def test_"
      min_lines: 150
  key_links:
    - from: "lib/vision_cascade.py"
      to: "lib.checkpoint._atomic_write"
      via: "import for atomic persist of provider_status.json"
      pattern: "from lib.checkpoint import"
    - from: "lib/vision_cascade.py"
      to: "lib.current_key / lib.rotate_key"
      via: "Gemini Vision last-resort provider uses existing key rotation"
      pattern: "from lib import.*current_key|rotate_key"
    - from: "tests/unit/test_vision_cascade.py"
      to: "lib.vision_cascade.VisionCascade"
      via: "unit tests instantiate VisionCascade with mocked providers"
      pattern: "VisionCascade\\("
---

<objective>
Build the core Vision cascade state machine in `lib/vision_cascade.py`: a `VisionCascade` class that orchestrates calls through SiliconFlow → OpenRouter → Gemini with per-provider circuit breaker, error classification, persistent state, and structured logging. Ships with unit tests covering all circuit-breaker and error-classification paths using mocked providers.

Purpose: Today `image_pipeline._describe_one` cascades Gemini → SiliconFlow → OpenRouter (wrong order per PRD) and has no failure tracking — a single 503 kills the article. This plan produces the replacement module. Integration into `image_pipeline.py` is deferred to 13-02.

Output:
- `lib/vision_cascade.py` — public `VisionCascade` class + `CascadeResult` dataclass + `AttemptRecord` dataclass
- `tests/unit/test_vision_cascade.py` — ≥10 unit tests with mocked providers
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/13-vision-cascade/13-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@CLAUDE.md
@image_pipeline.py
@lib/__init__.py
@lib/api_keys.py
@lib/rate_limit.py
@config.py
@tests/conftest.py
@tests/unit/test_image_pipeline.py

<interfaces>
<!-- Key types and contracts the executor needs. Use directly — no codebase exploration required. -->

From `lib/__init__.py` (public exports already available):
```python
from lib import current_key, rotate_key, VISION_LLM, generate_sync
# current_key() -> str  (Gemini API key, auto-rotated by tenacity retry)
# rotate_key() -> str   (advances to next key in pool)
# generate_sync(model, contents) -> str  (wraps Gemini with rate limit + retry + key rotation)
```

From `image_pipeline.py` (patterns to reuse — do NOT re-import from image_pipeline; copy/adapt):
```python
def _describe_via_siliconflow(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """POST https://api.siliconflow.cn/v1/chat/completions, model=Qwen/Qwen3-VL-32B-Instruct,
    Authorization: Bearer $SILICONFLOW_API_KEY, timeout=60. Raises on non-200."""

def _describe_via_openrouter(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """POST https://openrouter.ai/api/v1/chat/completions, model=z-ai/glm-4.5v,
    Authorization: Bearer $OPENROUTER_API_KEY, timeout=30. Raises on non-200."""

def _describe_via_gemini(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Uses lib.generate_sync(VISION_LLM, contents=[prompt_text, types.Part.from_bytes(...)]).
    Raises on failure."""
```

From Phase 12 `lib/checkpoint.py` (dependency — will exist at integration time):
```python
from pathlib import Path
def _atomic_write(path: Path, content: str | bytes, mode: str = "w") -> None:
    """write to {path}.tmp then os.rename() — atomic."""
```

Phase 13 MUST use `lib.checkpoint._atomic_write` for `provider_status.json` persistence.
If Phase 12 is not yet merged, executor may inline a copy of the helper with a TODO + import guard.

From `config.py`:
```python
BASE_DIR = Path.home() / ".hermes" / "omonigraph-vault"
# Checkpoint root (Phase 12 convention): BASE_DIR / "checkpoints"
# provider_status.json path: BASE_DIR / "checkpoints" / "_batch" / "provider_status.json"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write VisionCascade + CascadeResult contracts + provider_status schema</name>
  <files>lib/vision_cascade.py</files>
  <read_first>
    - .planning/phases/13-vision-cascade/13-CONTEXT.md (§decisions, §specifics — schema + state machine sketch)
    - image_pipeline.py (current _describe_via_* helpers — to adapt, not re-import)
    - lib/__init__.py (available public API)
    - lib/api_keys.py (current_key / rotate_key contract)
    - config.py (BASE_DIR path constant)
  </read_first>
  <behavior>
    - Test 1: `VisionCascade(providers=["siliconflow","openrouter","gemini"], checkpoint_dir=tmp)` constructs cleanly; `cascade.status` has 3 keys with default schema (failures=0, circuit_open=False, total_attempts=0, total_successes=0, total_failures=0, last_error=None, next_retry_at=None)
    - Test 2: `CascadeResult` is a frozen dataclass with fields (description: str | None, provider_used: str | None, attempts: list[AttemptRecord], failed: bool); `AttemptRecord` has (provider, result_code, latency_ms, error)
    - Test 3: `cascade.providers == ["siliconflow", "openrouter", "gemini"]` — exact order per CASC-01 (NOT Gemini-first like image_pipeline.py today)
    - Test 4: `cascade._status_path` resolves to `checkpoint_dir / "_batch" / "provider_status.json"`
    - Test 5: Fresh construction with no existing `provider_status.json` initialises defaults and does NOT raise
    - Test 6: Existing `provider_status.json` with valid JSON is loaded on construction (simulating resume)
  </behavior>
  <action>
Create `lib/vision_cascade.py` with ONLY the public contracts + state scaffolding (no provider adapter logic yet — that's Task 2). Copy this skeleton verbatim then fill in per CASC-01/02 locked spec:

```python
"""Vision provider cascade with circuit breaker and persistent state.

Phase 13 CASC-01 locked cascade order: SiliconFlow → OpenRouter → Gemini.
This replaces the wrong-order cascade in image_pipeline._describe_one.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# CASC-01 LOCKED — do not reorder. SiliconFlow primary (paid, reliable),
# OpenRouter fallback (paid, cheap), Gemini last-resort (free, rate-limited).
DEFAULT_PROVIDERS: tuple[str, ...] = ("siliconflow", "openrouter", "gemini")

# CASC-03 LOCKED thresholds.
CIRCUIT_FAILURE_THRESHOLD = 3   # 3 consecutive failures → open
RECOVERY_PROBE_INTERVAL = 10    # after 10 images skipped → 1 retry

# CASC-04 result codes (internal taxonomy).
RESULT_SUCCESS = "success"
RESULT_HTTP_503 = "http_503"
RESULT_HTTP_429 = "http_429"
RESULT_HTTP_4XX_AUTH = "http_4xx_auth"  # 401/403/422 — permanent, does NOT count
RESULT_TIMEOUT = "timeout"
RESULT_OTHER = "other"

# Which result codes count toward circuit-breaker failures.
_CIRCUIT_FAILURE_CODES = {RESULT_HTTP_503, RESULT_HTTP_429, RESULT_TIMEOUT}


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt against one provider for one image."""
    provider: str
    result_code: str       # RESULT_* constant
    latency_ms: int
    error: str | None = None
    desc_chars: int | None = None   # len of description on success


@dataclass(frozen=True)
class CascadeResult:
    """Outcome of VisionCascade.describe() for a single image."""
    description: str | None
    provider_used: str | None
    attempts: list[AttemptRecord]
    failed: bool = False


def _default_provider_state() -> dict:
    """Per-CASC-02 schema."""
    return {
        "failures": 0,
        "last_error": None,
        "circuit_open": False,
        "next_retry_at": None,
        "total_attempts": 0,
        "total_successes": 0,
        "total_failures": 0,
    }


class VisionCascade:
    """Stateful Vision cascade orchestrator.

    One instance per batch. Passed INTO describe_image_cascade(); not a
    module-global. Tracks per-provider circuit state + persists to checkpoint dir.
    """

    def __init__(
        self,
        providers: tuple[str, ...] | list[str] = DEFAULT_PROVIDERS,
        checkpoint_dir: Path | None = None,
    ) -> None:
        self.providers: list[str] = list(providers)
        if checkpoint_dir is None:
            from config import BASE_DIR
            checkpoint_dir = BASE_DIR / "checkpoints"
        self.checkpoint_dir = Path(checkpoint_dir)
        self._status_path = self.checkpoint_dir / "_batch" / "provider_status.json"
        self.status: dict[str, dict] = self._load_or_init_status()
        self.skipped_since_last_probe: dict[str, int] = {p: 0 for p in self.providers}
        # Per-batch raised-429 counter for "all-429 → stop batch" rule (CASC-04).
        self._last_attempt_codes: list[str] = []

    def _load_or_init_status(self) -> dict[str, dict]:
        if self._status_path.exists():
            try:
                with open(self._status_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Ensure all providers have a slot (robust against schema drift)
                for p in self.providers:
                    if p not in loaded:
                        loaded[p] = _default_provider_state()
                return loaded
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("provider_status.json unreadable (%s); resetting", e)
        return {p: _default_provider_state() for p in self.providers}

    def total_usage(self) -> dict[str, int]:
        """Return per-provider success count — for batch-end aggregate log."""
        return {p: self.status[p]["total_successes"] for p in self.providers}
```

Defer the `describe()` method + provider adapters + `_persist()` to Task 2. This task establishes the contracts only. Reference decision CASC-01 (locked) in docstring.
  </action>
  <verify>
    <automated>pytest tests/unit/test_vision_cascade.py::test_contracts -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class VisionCascade' lib/vision_cascade.py` exits 0
    - `grep -q 'DEFAULT_PROVIDERS.*siliconflow.*openrouter.*gemini' lib/vision_cascade.py` exits 0 (verifies locked cascade order)
    - `grep -q '@dataclass(frozen=True)' lib/vision_cascade.py` exits 0
    - `grep -q 'CIRCUIT_FAILURE_THRESHOLD = 3' lib/vision_cascade.py` exits 0
    - `grep -q 'RECOVERY_PROBE_INTERVAL = 10' lib/vision_cascade.py` exits 0
    - `python -c "from lib.vision_cascade import VisionCascade, CascadeResult, AttemptRecord; print('ok')"` exits 0
    - At least 6 test functions matching `test_*` exist in `tests/unit/test_vision_cascade.py` (contracts coverage)
  </acceptance_criteria>
  <done>Contracts + frozen dataclasses + state init/load in place. Tests verify provider order + schema + persistence-path resolution. `describe()` method is NOT implemented yet.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement describe() + provider adapters + circuit breaker + atomic persist</name>
  <files>lib/vision_cascade.py, tests/unit/test_vision_cascade.py</files>
  <read_first>
    - lib/vision_cascade.py (Task 1 output — scaffolding to extend)
    - image_pipeline.py (_describe_via_siliconflow, _describe_via_openrouter, _describe_via_gemini — reuse logic verbatim; adapt to return AttemptRecord instead of raise)
    - .planning/phases/13-vision-cascade/13-CONTEXT.md (§specifics — state machine pseudocode)
    - lib/__init__.py (current_key, generate_sync, VISION_LLM)
    - tests/unit/test_image_pipeline.py (mocking patterns for requests.post + lib.generate_sync)
    - tests/conftest.py (tmp_base_dir fixture pattern)
  </read_first>
  <behavior>
    - Test 7: Mock SiliconFlow returning 200 with description → `CascadeResult.provider_used == "siliconflow"`, attempts has exactly 1 entry, status["siliconflow"]["total_successes"] == 1
    - Test 8: Mock SiliconFlow 503 + OpenRouter 200 → `provider_used == "openrouter"`, attempts has 2 entries with codes [http_503, success], status["siliconflow"]["failures"] == 1
    - Test 9: Three consecutive 503 calls to same VisionCascade instance → after 3rd call status["siliconflow"]["circuit_open"] == True AND status["siliconflow"]["failures"] == 3
    - Test 10: With circuit_open=True for siliconflow, next 9 images skip it silently (OpenRouter used); 10th image triggers a probe on SiliconFlow
    - Test 11: Successful probe resets circuit_open=False AND failures=0; skipped_since_last_probe back to 0
    - Test 12: SiliconFlow returns 401 → classified as RESULT_HTTP_4XX_AUTH, status["siliconflow"]["failures"] stays 0 (not a circuit failure), cascade falls through to OpenRouter
    - Test 13: All three providers return 429 in sequence on same image → CascadeResult.failed == True AND a module-level flag or raised `AllProvidersExhausted429Error` signals "stop batch" (CASC-04 special rule)
    - Test 14: Timeout exception from requests → classified as RESULT_TIMEOUT, counts as circuit failure
    - Test 15: After successful provider call, `_persist()` is invoked and `provider_status.json` on disk matches `cascade.status` dict (atomic write via lib.checkpoint._atomic_write — or inline equivalent if Phase 12 not merged)
    - Test 16: Per-image log lines emit via `logger.info()` in the documented format: `image_id=X provider=siliconflow attempt=1/3 result=503 latency_ms=N msg="..."` (use logger.info with structured kwargs or a single formatted message — planner choice)
  </behavior>
  <action>
Extend `lib/vision_cascade.py` with the full `describe()` method + provider adapter helpers + atomic persist. Use this exact method signature and state machine:

```python
class VisionCascade:
    # ... (existing from Task 1) ...

    def describe(
        self,
        image_id: str,
        image_bytes: bytes,
        mime: str = "image/jpeg",
    ) -> CascadeResult:
        """Try providers in cascade order with circuit breaker.
        Returns CascadeResult; never raises (except AllProvidersExhausted429Error)."""
        attempts: list[AttemptRecord] = []
        codes_this_image: list[str] = []

        for provider in self.providers:
            pstate = self.status[provider]

            # Circuit-open handling (CASC-03)
            if pstate["circuit_open"]:
                self.skipped_since_last_probe[provider] += 1
                if self.skipped_since_last_probe[provider] >= RECOVERY_PROBE_INTERVAL:
                    # Recovery probe — reset counter regardless of outcome
                    self.skipped_since_last_probe[provider] = 0
                    logger.info(
                        "image_id=%s provider=%s recovery_probe=1",
                        image_id, provider,
                    )
                    # Fall through to actual call below
                else:
                    logger.debug(
                        "image_id=%s provider=%s skipped=circuit_open",
                        image_id, provider,
                    )
                    continue

            # Actual call
            t0 = time.perf_counter()
            pstate["total_attempts"] += 1
            try:
                description = self._call_provider(provider, image_bytes, mime)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                # SUCCESS
                rec = AttemptRecord(
                    provider=provider,
                    result_code=RESULT_SUCCESS,
                    latency_ms=latency_ms,
                    desc_chars=len(description),
                )
                attempts.append(rec)
                codes_this_image.append(RESULT_SUCCESS)
                pstate["failures"] = 0
                pstate["circuit_open"] = False  # reset on probe success
                pstate["total_successes"] += 1
                pstate["last_error"] = None
                self.skipped_since_last_probe[provider] = 0
                logger.info(
                    "image_id=%s provider=%s attempt=%d/3 result=200 latency_ms=%d desc_chars=%d",
                    image_id, provider, len(attempts), latency_ms, len(description),
                )
                self._persist()
                return CascadeResult(
                    description=description,
                    provider_used=provider,
                    attempts=attempts,
                    failed=False,
                )
            except _ProviderError as e:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                rec = AttemptRecord(
                    provider=provider,
                    result_code=e.result_code,
                    latency_ms=latency_ms,
                    error=str(e),
                )
                attempts.append(rec)
                codes_this_image.append(e.result_code)
                pstate["last_error"] = str(e)[:500]
                pstate["total_failures"] += 1
                logger.warning(
                    "image_id=%s provider=%s attempt=%d/3 result=%s latency_ms=%d msg=%s",
                    image_id, provider, len(attempts),
                    e.result_code, latency_ms, str(e)[:200],
                )
                if e.result_code in _CIRCUIT_FAILURE_CODES:
                    pstate["failures"] += 1
                    if pstate["failures"] >= CIRCUIT_FAILURE_THRESHOLD:
                        pstate["circuit_open"] = True
                        logger.warning(
                            "circuit_open=true provider=%s failures=%d",
                            provider, pstate["failures"],
                        )
                # 4xx_auth / other: don't increment failures, just cascade
                self._persist()
                continue

        # All providers failed
        # CASC-04 special: if all attempts on this image were 429, signal batch-stop
        non_skip_codes = [c for c in codes_this_image if c != ""]
        if non_skip_codes and all(c == RESULT_HTTP_429 for c in non_skip_codes):
            raise AllProvidersExhausted429Error(
                f"image_id={image_id}: all providers returned 429 — stopping batch"
            )
        return CascadeResult(
            description=None,
            provider_used=None,
            attempts=attempts,
            failed=True,
        )

    def _call_provider(self, provider: str, image_bytes: bytes, mime: str) -> str:
        """Dispatch. Raises _ProviderError (classified) on any failure."""
        if provider == "siliconflow":
            return self._call_siliconflow(image_bytes, mime)
        if provider == "openrouter":
            return self._call_openrouter(image_bytes, mime)
        if provider == "gemini":
            return self._call_gemini(image_bytes, mime)
        raise _ProviderError(RESULT_OTHER, f"unknown provider {provider}")

    def _call_siliconflow(self, image_bytes: bytes, mime: str) -> str:
        """POST to SiliconFlow Qwen3-VL-32B. Raises _ProviderError on any failure."""
        import base64
        import requests
        key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
        if not key:
            raise _ProviderError(RESULT_HTTP_4XX_AUTH, "SILICONFLOW_API_KEY not set")
        b64 = base64.b64encode(image_bytes).decode()
        fmt = "png" if "png" in mime else "jpeg"
        try:
            resp = requests.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "Qwen/Qwen3-VL-32B-Instruct",
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "Describe this image in detail for a knowledge graph. Return only the description."},
                        {"type": "image_url", "image_url": {"url": f"data:image/{fmt};base64,{b64}"}}
                    ]}],
                    "max_tokens": 300,
                },
                timeout=60,
            )
        except requests.Timeout as e:
            raise _ProviderError(RESULT_TIMEOUT, f"timeout: {e}") from e
        except requests.RequestException as e:
            raise _ProviderError(RESULT_OTHER, f"network: {e}") from e
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"] or ""
            return content.strip()
        raise _ProviderError(_classify_http(resp.status_code), f"HTTP {resp.status_code}: {resp.text[:200]}")

    def _call_openrouter(self, image_bytes: bytes, mime: str) -> str:
        """POST to OpenRouter GLM-4.5V. Raises _ProviderError on any failure."""
        import base64
        import requests
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise _ProviderError(RESULT_HTTP_4XX_AUTH, "OPENROUTER_API_KEY not set")
        b64 = base64.b64encode(image_bytes).decode()
        fmt = "png" if "png" in mime else "jpeg"
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "z-ai/glm-4.5v",
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "Describe this image in detail for a knowledge graph. Return only the description."},
                        {"type": "image_url", "image_url": {"url": f"data:image/{fmt};base64,{b64}"}}
                    ]}],
                    "max_tokens": 300,
                },
                timeout=30,
            )
        except requests.Timeout as e:
            raise _ProviderError(RESULT_TIMEOUT, f"timeout: {e}") from e
        except requests.RequestException as e:
            raise _ProviderError(RESULT_OTHER, f"network: {e}") from e
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"] or ""
            return content.strip()
        raise _ProviderError(_classify_http(resp.status_code), f"HTTP {resp.status_code}: {resp.text[:200]}")

    def _call_gemini(self, image_bytes: bytes, mime: str) -> str:
        """Gemini Vision last-resort. Uses existing lib.generate_sync (handles rate
        limit + key rotation). Raises _ProviderError on any failure."""
        try:
            from lib import VISION_LLM, generate_sync
            from google.genai import types
            description = generate_sync(
                VISION_LLM,
                contents=[
                    "Describe this image in detail for a knowledge graph. Return only the description.",
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                ],
            )
            return description.strip()
        except Exception as e:
            msg = str(e).lower()
            if "timeout" in msg:
                raise _ProviderError(RESULT_TIMEOUT, str(e)) from e
            if "429" in msg or "quota" in msg or "exhausted" in msg:
                raise _ProviderError(RESULT_HTTP_429, str(e)) from e
            if "401" in msg or "403" in msg or "permission" in msg:
                raise _ProviderError(RESULT_HTTP_4XX_AUTH, str(e)) from e
            raise _ProviderError(RESULT_OTHER, str(e)) from e

    def _persist(self) -> None:
        """Atomic write of provider_status to checkpoint dir."""
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.status, indent=2, ensure_ascii=False, default=str)
        # Prefer lib.checkpoint._atomic_write if Phase 12 is merged; inline fallback otherwise.
        try:
            from lib.checkpoint import _atomic_write
            _atomic_write(self._status_path, content, mode="w")
        except ImportError:
            tmp = self._status_path.with_suffix(self._status_path.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, self._status_path)


# ── module-level helpers ────────────────────────────────────────────────

class _ProviderError(Exception):
    def __init__(self, result_code: str, message: str = "") -> None:
        super().__init__(message)
        self.result_code = result_code


class AllProvidersExhausted429Error(Exception):
    """Raised by VisionCascade.describe() when all providers return 429 on the
    same image. Caller (image_pipeline integration, Plan 13-02) MUST catch and
    stop the batch gracefully (CASC-04 special rule)."""


def _classify_http(status_code: int) -> str:
    if status_code == 503:
        return RESULT_HTTP_503
    if status_code == 429:
        return RESULT_HTTP_429
    if status_code in (401, 403, 422):
        return RESULT_HTTP_4XX_AUTH
    return RESULT_OTHER
```

Then add the Test 7–16 unit tests to `tests/unit/test_vision_cascade.py` using `mocker.patch("lib.vision_cascade.requests.post", ...)` to simulate each HTTP response. Use `tmp_path` fixture for `checkpoint_dir`. For Gemini tests, patch `lib.generate_sync`. Each test must assert both the `CascadeResult` return value AND the `cascade.status` mutation (failures count, circuit_open flag).

Use `pytest.raises(AllProvidersExhausted429Error)` for Test 13.
  </action>
  <verify>
    <automated>pytest tests/unit/test_vision_cascade.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'def describe(self' lib/vision_cascade.py` exits 0
    - `grep -qE '_call_siliconflow|_call_openrouter|_call_gemini' lib/vision_cascade.py` returns 3 lines (one per provider)
    - `grep -q 'class AllProvidersExhausted429Error' lib/vision_cascade.py` exits 0
    - `grep -q '_classify_http' lib/vision_cascade.py` exits 0
    - Test count: `grep -cE '^def test_' tests/unit/test_vision_cascade.py` ≥ 10
    - `pytest tests/unit/test_vision_cascade.py -v` exits 0 with all tests passing
    - Specific assertions verified: test that mocks 3 consecutive 503 calls and asserts `cascade.status["siliconflow"]["circuit_open"] is True`; test that mocks 401 and asserts `cascade.status["siliconflow"]["failures"] == 0` (auth is NOT a circuit failure)
    - `python -c "import json; from pathlib import Path; from lib.vision_cascade import VisionCascade; import tempfile; d=Path(tempfile.mkdtemp()); c=VisionCascade(checkpoint_dir=d); c._persist(); assert (d/'_batch'/'provider_status.json').exists(); print('persist ok')"` exits 0
  </acceptance_criteria>
  <done>describe() method complete with full circuit-breaker logic; all 4 error classifications handled; atomic persist working; ≥10 unit tests passing. No integration into image_pipeline.py yet (that's Plan 13-02).</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/test_vision_cascade.py -v` — all tests pass
- `python -c "from lib.vision_cascade import VisionCascade, CascadeResult, AttemptRecord, AllProvidersExhausted429Error; print('imports ok')"` — public API imports clean
- Grep verifies cascade order and locked thresholds in code
- Persistence verified: creating a VisionCascade + describing one image produces `provider_status.json` on disk
</verification>

<success_criteria>
- [ ] `lib/vision_cascade.py` exports `VisionCascade`, `CascadeResult`, `AttemptRecord`, `AllProvidersExhausted429Error`
- [ ] Cascade order in code is SiliconFlow → OpenRouter → Gemini (CASC-01)
- [ ] `provider_status` dict schema matches CASC-02 exactly (failures, last_error, circuit_open, next_retry_at, total_attempts, total_successes, total_failures)
- [ ] 3 consecutive circuit-failure codes → circuit_open=True (CASC-03)
- [ ] 10 skipped images → 1 recovery probe; success resets circuit (CASC-03)
- [ ] 4xx auth codes do NOT increment failures (CASC-04)
- [ ] All-429 on single image → `AllProvidersExhausted429Error` raised (CASC-04)
- [ ] Per-attempt structured log lines (CASC-05)
- [ ] provider_status.json persisted via atomic write (works with or without Phase 12 merged)
- [ ] ≥10 unit tests with mocked providers, all passing
</success_criteria>

<output>
After completion, create `.planning/phases/13-vision-cascade/13-00-SUMMARY.md` with:
- Public API exported from `lib/vision_cascade.py`
- Example usage snippet (for Plan 13-02 to copy)
- Test count + coverage claim
- Any deviation from PRD (expected: none)
</output>
