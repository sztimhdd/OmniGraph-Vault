"""Shared image-handling pipeline for WeChat + Zhihu ingestion paths.

Extracted from ingest_wechat.py as part of Phase 4 refactor (D-15, D-16).
All functions are sync; callers wrap in asyncio.to_thread if needed.

Phase 13 (2026-05-02): describe_images now delegates to lib.vision_cascade
with pre-batch + mid-batch SiliconFlow balance checks (CASC-01..06). The
legacy VISION_PROVIDER env var is obsolete; the cascade is always
siliconflow -> openrouter -> gemini unless balance is below the CNY 0.05
switch threshold.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

from lib.siliconflow_balance import (
    BalanceCheckError,
    check_siliconflow_balance,
    should_switch_to_openrouter,
)
from lib.vision_cascade import (
    DEFAULT_PROVIDERS,
    AllProvidersExhausted429Error,
    CascadeResult,
    VisionCascade,
)

logger = logging.getLogger(__name__)

# Rate-limit between Gemini Vision describe_images calls (D-15).
_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0  # Phase 8 IMG-02: was 2; SiliconFlow has no RPM cap

# Local image server base — matches ingest_wechat.py historical value.
_DEFAULT_IMAGE_BASE_URL = "http://localhost:8765"

# Phase 8 IMG-03 / D-08.05: canonical outcome taxonomy (6 values).
OUTCOME_SUCCESS = "success"
OUTCOME_DOWNLOAD_FAILED = "download_failed"
OUTCOME_FILTERED_TOO_SMALL = "filtered_too_small"
OUTCOME_SIZE_READ_FAILED = "size_read_failed"
OUTCOME_VISION_ERROR = "vision_error"
OUTCOME_TIMEOUT = "timeout"


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


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


def emit_batch_complete(
    *,
    filter_stats: "FilterStats",
    download_input_count: int,
    download_failed: int,
    describe_stats: dict | None,
    total_ms: int,
) -> None:
    """Emit the aggregate image_batch_complete JSON-lines event (IMG-04 / D-08.02).

    describe_stats can be None (e.g., if the batch had 0 images to describe);
    the helper normalizes missing keys to 0 / {} to keep the wire format stable.
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


@dataclass(frozen=True)
class FilterStats:
    """Stats from filter_small_images — wire format per CONTEXT D-08.01.

    timings_ms is nested (not flat) to allow future sub-stage additions
    (e.g. total_unlink_ms, total_stat_ms) without dataclass shape churn.
    """

    input: int
    kept: int
    filtered_too_small: int
    size_read_failed: int
    timings_ms: dict  # {"total_read": <int ms>}


def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]:
    """Download each URL to dest_dir/{i}.jpg. Return {remote_url: local_path}
    for successes only (non-200 responses and exceptions are silently skipped
    with a warning log).

    Phase 8 IMG-03: emits per-image JSON-lines log on failure only. Successful
    downloads are not logged here — the downstream stage (filter or describe)
    owns the per-image event for kept images. This matches D-08.02 "ms measures
    wall-clock of the STAGE that owns this event."
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for i, url in enumerate(urls):
        t0 = time.perf_counter()
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning(
                    "Image %d download failed: HTTP %d for %s", i, resp.status_code, url
                )
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
            logger.warning("Image %d error: %s", i, e)
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
    return result


def filter_small_images(
    url_to_path: dict[str, Path],
    *,
    min_dim: int = 300,
) -> tuple[dict[str, Path], FilterStats]:
    """Filter images where min(width, height) < min_dim.

    PIL open failure => keep image (can't measure => don't drop). Filtered-out
    files are unlinked from disk to reclaim space. Returns (new_map, stats).
    """
    # Phase 8 IMG-01: min(w,h)<min_dim matches current or-logic; see CONTEXT §Specifics for pre-fix history
    from PIL import Image as PILImage
    t0 = time.perf_counter()
    kept: dict[str, Path] = {}
    filtered_too_small = 0
    size_read_failed = 0
    for url, path in url_to_path.items():
        # Phase 8 IMG-03: per-image stage timing for JSON-lines log.
        per_t0 = time.perf_counter()
        try:
            with PILImage.open(path) as im:
                w, h = im.size
            file_bytes = path.stat().st_size
        except Exception as e:
            logger.warning("PIL open failed for %s (%s) — keeping image", path, e)
            size_read_failed += 1
            kept[url] = path  # D-08.01: PIL failure degrades to KEEP
            _emit_log({
                "event": "image_processed",
                "ts": _now_iso(),
                "url": url,
                "local_path": str(path),
                "dims": None,
                "bytes": None,
                "provider": None,
                "ms": int((time.perf_counter() - per_t0) * 1000),
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
                "ms": int((time.perf_counter() - per_t0) * 1000),
                "outcome": OUTCOME_FILTERED_TOO_SMALL,
                "error": None,
            })
        else:
            # Kept images produce NO event here — describe_images owns the
            # success/vision_error/timeout outcome per D-08.02.
            kept[url] = path
    stats = FilterStats(
        input=len(url_to_path),
        kept=len(kept),
        filtered_too_small=filtered_too_small,
        size_read_failed=size_read_failed,
        timings_ms={"total_read": int((time.perf_counter() - t0) * 1000)},
    )
    return kept, stats


def localize_markdown(
    md: str,
    url_to_local: dict[str, Path],
    base_url: str = _DEFAULT_IMAGE_BASE_URL,
    article_hash: str = "",
) -> str:
    """Replace each remote URL in md with {base_url}/{article_hash}/{filename}."""
    for url, path in url_to_local.items():
        local = (
            f"{base_url}/{article_hash}/{path.name}"
            if article_hash
            else f"{base_url}/{path.name}"
        )
        md = md.replace(url, local)
    return md


def _describe_via_gemini(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Describe one image via Gemini Vision (free tier, key rotation).
    Raises on failure — caller handles fallback."""
    from lib import VISION_LLM, generate_sync
    from google.genai import types
    return generate_sync(
        VISION_LLM,
        contents=[
            "Describe this image in detail for a knowledge graph. Return only the description.",
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
        ],
    )


def _describe_via_openrouter(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Describe one image via GLM-4.5V (OpenRouter). $0.0001/call, last resort."""
    import base64
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    b64 = base64.b64encode(image_bytes).decode()
    fmt = "png" if "png" in mime else "jpeg"
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
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
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")
    content = resp.json()["choices"][0]["message"]["content"] or ""
    return content.strip()


def _describe_via_siliconflow(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Describe one image via Qwen3-VL-32B (SiliconFlow). ¥0.0013/image, best open-source vision."""
    import base64
    sf_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not sf_key:
        raise RuntimeError("SILICONFLOW_API_KEY not set")
    b64 = base64.b64encode(image_bytes).decode()
    fmt = "png" if "png" in mime else "jpeg"
    resp = requests.post(
        "https://api.siliconflow.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {sf_key}", "Content-Type": "application/json"},
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
    if resp.status_code != 200:
        raise RuntimeError(f"SiliconFlow HTTP {resp.status_code}: {resp.text[:200]}")
    content = resp.json()["choices"][0]["message"]["content"] or ""
    return content.strip()


def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe images via VisionCascade (SiliconFlow -> OpenRouter -> Gemini).

    Phase 13 CASC-01/05/06 rewire. Signature preserved for backward-compat with
    multimodal_ingest.py and ingest_wechat.py. New behavior surfaced via
    get_last_describe_stats().

    Pre-batch balance check (once, unless OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1):
      - Warns if SiliconFlow balance < estimated spend.
      - If balance < CNY 0.05 -> construct cascade with providers=[openrouter, gemini].

    Mid-batch (every 10th image): re-check balance; if below CNY 0.05 remove
    SiliconFlow from the live cascade's provider list.

    AllProvidersExhausted429Error stops the batch cleanly; callers see a
    partial dict with a `batch_stopped_429=True` marker in describe stats.
    """
    global _last_describe_stats

    result: dict[Path, str] = {}
    paths_list = list(paths)
    sleep_secs = float(
        os.environ.get("VISION_INTER_IMAGE_SLEEP", _DESCRIBE_INTER_IMAGE_SLEEP_SECS)
    )

    if not paths_list:
        _last_describe_stats = {
            "provider_mix": {},
            "vision_success": 0,
            "vision_error": 0,
            "vision_timeout": 0,
            "circuit_opens": [],
            "gemini_share": 0.0,
            "batch_stopped_429": False,
        }
        return result

    # CASC-06 pre-batch balance check
    skip_balance = (
        os.environ.get("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "").strip() == "1"
    )
    force_openrouter_primary = False
    if not skip_balance:
        try:
            balance = check_siliconflow_balance()
            estimated = Decimal(len(paths_list)) * Decimal("0.0013")
            if balance < estimated:
                logger.warning(
                    "SiliconFlow balance CNY %.4f insufficient for CNY %.4f "
                    "estimated spend -- top up or expect fallback to OpenRouter",
                    float(balance),
                    float(estimated),
                )
            if should_switch_to_openrouter(balance):
                logger.warning(
                    "SiliconFlow balance CNY %.4f below CNY 0.05 floor -- "
                    "switching to OpenRouter-primary for this batch",
                    float(balance),
                )
                force_openrouter_primary = True
        except BalanceCheckError as e:
            logger.warning(
                "pre-batch balance check failed (%s); proceeding with default "
                "cascade", e,
            )

    providers = (
        ["openrouter", "gemini"]
        if force_openrouter_primary
        else list(DEFAULT_PROVIDERS)
    )
    # Test seam: allow tests to redirect checkpoint storage off the user's
    # production ~/.hermes dir. Production leaves this unset.
    _ckpt_override = os.environ.get(
        "OMNIGRAPH_VISION_CHECKPOINT_DIR", ""
    ).strip()
    _ckpt_dir = Path(_ckpt_override) if _ckpt_override else None
    cascade = VisionCascade(providers=providers, checkpoint_dir=_ckpt_dir)

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

        # CASC-06 mid-batch balance monitoring every 10 images
        if not skip_balance and i > 0 and i % 10 == 0:
            try:
                balance = check_siliconflow_balance()
                if (
                    should_switch_to_openrouter(balance)
                    and "siliconflow" in cascade.providers
                ):
                    logger.warning(
                        "mid-batch balance CNY %.4f < CNY 0.05 -- removing "
                        "SiliconFlow from cascade",
                        float(balance),
                    )
                    cascade.providers = [
                        p for p in cascade.providers if p != "siliconflow"
                    ]
            except BalanceCheckError:
                pass  # non-fatal; keep going with current cascade

        try:
            cres: CascadeResult = cascade.describe(
                image_id=image_id, image_bytes=image_bytes, mime=mime
            )
        except AllProvidersExhausted429Error as e:
            logger.error(
                "BATCH STOP: %s -- all providers 429 on single image; check "
                "quotas + balance", e,
            )
            batch_stopped_429 = True
            result[path] = "Error describing image: all providers 429"
            vision_error += 1
            break

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if cres.failed or cres.description is None:
            result[path] = (
                f"Error describing image: cascade failed "
                f"(attempts={len(cres.attempts)})"
            )
            last = cres.attempts[-1] if cres.attempts else None
            if last and last.result_code == "timeout":
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
                "provider": None,
                "ms": latency_ms,
                "outcome": outcome,
                "error": last.error if last else "no attempts",
            })
        else:
            result[path] = cres.description
            vision_success += 1
            provider_mix[cres.provider_used] = (
                provider_mix.get(cres.provider_used, 0) + 1
            )
            _emit_log({
                "event": "image_processed",
                "ts": _now_iso(),
                "url": None,
                "local_path": str(path),
                "dims": None,
                "bytes": path.stat().st_size if path.exists() else None,
                "provider": cres.provider_used,
                "ms": latency_ms,
                "outcome": OUTCOME_SUCCESS,
                "error": None,
            })

        if i + 1 < len(paths_list) and sleep_secs > 0:
            time.sleep(sleep_secs)

    # CASC-05 batch-end aggregate + alerts
    total_success = vision_success
    gemini_share = (
        (provider_mix.get("gemini", 0) / total_success)
        if total_success > 0
        else 0.0
    )
    circuit_opens = [
        p for p, s in cascade.status.items() if s.get("circuit_open")
    ]
    if gemini_share > 0.05:
        logger.warning(
            "CASCADE ALERT: gemini used for %.1f%% of images (>5%% threshold) "
            "-- upstream provider issues detected",
            gemini_share * 100,
        )
    if circuit_opens:
        logger.warning(
            "CASCADE ALERT: circuits still open at batch end: %s -- review "
            "provider_status.json",
            circuit_opens,
        )

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


def save_markdown_with_images(
    md: str,
    dest_dir: Path,
    metadata: dict,
) -> tuple[Path, Path]:
    """Atomic write of final_content.md + metadata.json via tmp -> rename."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    md_path = dest_dir / "final_content.md"
    meta_path = dest_dir / "metadata.json"
    md_tmp = md_path.with_suffix(".md.tmp")
    meta_tmp = meta_path.with_suffix(".json.tmp")
    md_tmp.write_text(md, encoding="utf-8")
    meta_tmp.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(md_tmp, md_path)
    os.replace(meta_tmp, meta_path)
    return md_path, meta_path
