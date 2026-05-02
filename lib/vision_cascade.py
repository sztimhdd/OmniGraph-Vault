"""Vision provider cascade with circuit breaker and persistent state.

Phase 13 CASC-01 locked cascade order: SiliconFlow -> OpenRouter -> Gemini.
This replaces the wrong-order cascade in image_pipeline._describe_one.

Public API:
    - VisionCascade         stateful cascade orchestrator
    - CascadeResult         immutable outcome dataclass
    - AttemptRecord         per-provider attempt record
    - AllProvidersExhausted429Error  raised when all providers 429 on the same image
    - DEFAULT_PROVIDERS     ("siliconflow", "openrouter", "gemini")
    - CIRCUIT_FAILURE_THRESHOLD  3
    - RECOVERY_PROBE_INTERVAL    10
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# CASC-01 LOCKED -- do not reorder. SiliconFlow primary (paid, reliable),
# OpenRouter fallback (paid, cheap), Gemini last-resort (free, rate-limited).
DEFAULT_PROVIDERS: tuple[str, ...] = ("siliconflow", "openrouter", "gemini")

# CASC-03 LOCKED thresholds.
CIRCUIT_FAILURE_THRESHOLD = 3   # 3 consecutive failures -> open
RECOVERY_PROBE_INTERVAL = 10    # after 10 images skipped -> 1 retry

# CASC-04 result codes (internal taxonomy).
RESULT_SUCCESS = "success"
RESULT_HTTP_503 = "http_503"
RESULT_HTTP_429 = "http_429"
RESULT_HTTP_4XX_AUTH = "http_4xx_auth"  # 401/403/422 -- permanent, does NOT count
RESULT_TIMEOUT = "timeout"
RESULT_OTHER = "other"

# Which result codes count toward circuit-breaker failures.
_CIRCUIT_FAILURE_CODES = {RESULT_HTTP_503, RESULT_HTTP_429, RESULT_TIMEOUT}

_VISION_PROMPT = (
    "Describe this image in detail for a knowledge graph. "
    "Return only the description."
)


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt against one provider for one image."""

    provider: str
    result_code: str
    latency_ms: int
    error: str | None = None
    desc_chars: int | None = None


@dataclass(frozen=True)
class CascadeResult:
    """Outcome of VisionCascade.describe() for a single image."""

    description: str | None
    provider_used: str | None
    attempts: list[AttemptRecord] = field(default_factory=list)
    failed: bool = False


class _ProviderError(Exception):
    """Internal classified provider failure."""

    def __init__(self, result_code: str, message: str = "") -> None:
        super().__init__(message)
        self.result_code = result_code


class AllProvidersExhausted429Error(Exception):
    """Raised when all providers return 429 on the same image.

    Caller (image_pipeline integration, Plan 13-02) MUST catch and stop the
    batch gracefully (CASC-04 special rule).
    """


def _classify_http(status_code: int) -> str:
    if status_code == 503:
        return RESULT_HTTP_503
    if status_code == 429:
        return RESULT_HTTP_429
    if status_code in (401, 403, 422):
        return RESULT_HTTP_4XX_AUTH
    return RESULT_OTHER


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
    module-global. Tracks per-provider circuit state + persists to checkpoint
    dir.
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
        self.skipped_since_last_probe: dict[str, int] = {
            p: 0 for p in self.providers
        }

    # ------------------------------------------------------------------ persistence

    def _load_or_init_status(self) -> dict[str, dict]:
        if self._status_path.exists():
            try:
                with open(self._status_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                for p in self.providers:
                    if p not in loaded:
                        loaded[p] = _default_provider_state()
                return loaded
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(
                    "provider_status.json unreadable (%s); resetting", e
                )
        # Ensure ALL known providers have a slot, even if only a subset
        # were requested for this batch (cross-batch persistence).
        all_known = set(DEFAULT_PROVIDERS) | set(self.providers)
        return {p: _default_provider_state() for p in all_known}

    def _persist(self) -> None:
        """Atomic write of provider_status to checkpoint dir.

        Retries briefly on Windows PermissionError (AV/indexer lock races).
        """
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            self.status, indent=2, ensure_ascii=False, default=str
        )
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                try:
                    from lib.checkpoint import _atomic_write_text

                    _atomic_write_text(self._status_path, content)
                except ImportError:
                    tmp = self._status_path.with_suffix(
                        self._status_path.suffix + ".tmp"
                    )
                    tmp.write_text(content, encoding="utf-8")
                    os.replace(tmp, self._status_path)
                return
            except PermissionError as e:
                last_exc = e
                time.sleep(0.05 * (attempt + 1))
        if last_exc is not None:
            logger.warning(
                "provider_status persist failed after retries: %s", last_exc
            )

    def total_usage(self) -> dict[str, int]:
        """Return per-provider success count -- for batch-end aggregate log."""
        return {
            p: self.status.get(p, _default_provider_state())["total_successes"]
            for p in self.providers
        }

    # ------------------------------------------------------------------ main API

    def describe(
        self,
        image_id: str,
        image_bytes: bytes,
        mime: str = "image/jpeg",
    ) -> CascadeResult:
        """Try providers in cascade order with circuit breaker.

        Returns CascadeResult; never raises (except AllProvidersExhausted429Error).
        """
        attempts: list[AttemptRecord] = []
        codes_this_image: list[str] = []

        for provider in self.providers:
            pstate = self.status.setdefault(provider, _default_provider_state())

            # Circuit-open handling (CASC-03)
            if pstate["circuit_open"]:
                self.skipped_since_last_probe[provider] = (
                    self.skipped_since_last_probe.get(provider, 0) + 1
                )
                if (
                    self.skipped_since_last_probe[provider]
                    >= RECOVERY_PROBE_INTERVAL
                ):
                    self.skipped_since_last_probe[provider] = 0
                    logger.info(
                        "image_id=%s provider=%s recovery_probe=1",
                        image_id,
                        provider,
                    )
                    # Fall through to the actual call below.
                else:
                    logger.debug(
                        "image_id=%s provider=%s skipped=circuit_open",
                        image_id,
                        provider,
                    )
                    continue

            # Actual call
            t0 = time.perf_counter()
            pstate["total_attempts"] += 1
            try:
                description = self._call_provider(provider, image_bytes, mime)
                latency_ms = int((time.perf_counter() - t0) * 1000)
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
                    "image_id=%s provider=%s attempt=%d/3 result=200 "
                    "latency_ms=%d desc_chars=%d",
                    image_id,
                    provider,
                    len(attempts),
                    latency_ms,
                    len(description),
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
                    "image_id=%s provider=%s attempt=%d/3 result=%s "
                    "latency_ms=%d msg=%s",
                    image_id,
                    provider,
                    len(attempts),
                    e.result_code,
                    latency_ms,
                    str(e)[:200],
                )
                if e.result_code in _CIRCUIT_FAILURE_CODES:
                    pstate["failures"] += 1
                    if pstate["failures"] >= CIRCUIT_FAILURE_THRESHOLD:
                        pstate["circuit_open"] = True
                        logger.warning(
                            "circuit_open=true provider=%s failures=%d",
                            provider,
                            pstate["failures"],
                        )
                # 4xx_auth / other: don't increment failures, just cascade.
                self._persist()
                continue

        # All providers failed for this image.
        # CASC-04 special: if all non-skipped attempts on this image were 429,
        # signal batch-stop.
        if codes_this_image and all(
            c == RESULT_HTTP_429 for c in codes_this_image
        ):
            raise AllProvidersExhausted429Error(
                f"image_id={image_id}: all providers returned 429 -- "
                f"stopping batch"
            )
        return CascadeResult(
            description=None,
            provider_used=None,
            attempts=attempts,
            failed=True,
        )

    # ------------------------------------------------------------------ adapters

    def _call_provider(
        self, provider: str, image_bytes: bytes, mime: str
    ) -> str:
        """Dispatch. Raises _ProviderError (classified) on any failure."""
        if provider == "siliconflow":
            return self._call_siliconflow(image_bytes, mime)
        if provider == "openrouter":
            return self._call_openrouter(image_bytes, mime)
        if provider == "gemini":
            return self._call_gemini(image_bytes, mime)
        raise _ProviderError(RESULT_OTHER, f"unknown provider {provider}")

    def _call_siliconflow(self, image_bytes: bytes, mime: str) -> str:
        """POST to SiliconFlow Qwen3-VL-32B. Raises _ProviderError on failure."""
        key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
        if not key:
            raise _ProviderError(
                RESULT_HTTP_4XX_AUTH, "SILICONFLOW_API_KEY not set"
            )
        b64 = base64.b64encode(image_bytes).decode()
        fmt = "png" if "png" in mime else "jpeg"
        try:
            resp = requests.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "Qwen/Qwen3-VL-32B-Instruct",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": _VISION_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{fmt};base64,{b64}"
                                    },
                                },
                            ],
                        }
                    ],
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
        raise _ProviderError(
            _classify_http(resp.status_code),
            f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    def _call_openrouter(self, image_bytes: bytes, mime: str) -> str:
        """POST to OpenRouter GLM-4.5V. Raises _ProviderError on failure."""
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise _ProviderError(
                RESULT_HTTP_4XX_AUTH, "OPENROUTER_API_KEY not set"
            )
        b64 = base64.b64encode(image_bytes).decode()
        fmt = "png" if "png" in mime else "jpeg"
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "z-ai/glm-4.5v",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": _VISION_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{fmt};base64,{b64}"
                                    },
                                },
                            ],
                        }
                    ],
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
        raise _ProviderError(
            _classify_http(resp.status_code),
            f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    def _call_gemini(self, image_bytes: bytes, mime: str) -> str:
        """Gemini Vision last-resort. Uses lib.generate_sync (handles rate
        limit + key rotation). Raises _ProviderError on failure."""
        try:
            from google.genai import types

            from lib import VISION_LLM, generate_sync

            description = generate_sync(
                VISION_LLM,
                contents=[
                    _VISION_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                ],
            )
            return description.strip()
        except _ProviderError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "timeout" in msg:
                raise _ProviderError(RESULT_TIMEOUT, str(e)) from e
            if "429" in msg or "quota" in msg or "exhausted" in msg:
                raise _ProviderError(RESULT_HTTP_429, str(e)) from e
            if "401" in msg or "403" in msg or "permission" in msg:
                raise _ProviderError(RESULT_HTTP_4XX_AUTH, str(e)) from e
            raise _ProviderError(RESULT_OTHER, str(e)) from e
