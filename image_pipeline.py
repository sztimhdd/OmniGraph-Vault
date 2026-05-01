"""Shared image-handling pipeline for WeChat + Zhihu ingestion paths.

Extracted from ingest_wechat.py as part of Phase 4 refactor (D-15, D-16).
All functions are sync; callers wrap in asyncio.to_thread if needed.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Rate-limit between Gemini Vision describe_images calls (D-15).
_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 2  # Phase 7: reduced from 4s — SiliconFlow has no RPM cap

# Local image server base — matches ingest_wechat.py historical value.
_DEFAULT_IMAGE_BASE_URL = "http://localhost:8765"


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
    with a warning log)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for i, url in enumerate(urls):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning(
                    "Image %d download failed: HTTP %d for %s", i, resp.status_code, url
                )
                continue
            path = dest_dir / f"{i}.jpg"
            path.write_bytes(resp.content)
            result[url] = path
        except Exception as e:
            logger.warning("Image %d error: %s", i, e)
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


def _describe_one(path: Path, provider: str) -> str:
    """Describe a single image. provider: 'gemini' | 'siliconflow' | 'openrouter' | 'auto'.
    'auto' tries Gemini → SiliconFlow → OpenRouter in cascade."""
    image_bytes = Path(path).read_bytes()
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"

    if provider == "gemini":
        return _describe_via_gemini(image_bytes, mime)
    elif provider == "siliconflow":
        return _describe_via_siliconflow(image_bytes, mime)
    elif provider == "openrouter":
        return _describe_via_openrouter(image_bytes, mime)
    else:  # auto — cascade: Gemini → Qwen3-VL(SiliconFlow) → GLM-4.5V(OpenRouter)
        try:
            return _describe_via_gemini(image_bytes, mime)
        except Exception as gemini_err:
            msg = str(gemini_err).lower()
            if "429" in msg or "quota" in msg or "exhausted" in msg:
                logger.info("Gemini Vision 429 → falling back to Qwen3-VL-32B (SiliconFlow)")
            else:
                logger.warning("Gemini Vision failed (%s) → falling back to SiliconFlow", gemini_err)
            try:
                return _describe_via_siliconflow(image_bytes, mime)
            except Exception as sf_err:
                logger.warning("SiliconFlow failed (%s) → last resort: OpenRouter/GLM-4.5V", sf_err)
                return _describe_via_openrouter(image_bytes, mime)


def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe images with automatic 3-provider cascade.

    Controlled by env VISION_PROVIDER: 'gemini' | 'siliconflow' | 'openrouter' | 'auto' (default).
    - gemini: free tier with key rotation (lib.generate_sync). 429s propagate as errors.
    - siliconflow: Qwen3-VL-32B at ¥0.0013/image, best open-source vision.
    - openrouter: GLM-4.5V at $0.0001/call, last resort.
    - auto: Gemini → Qwen3-VL(SiliconFlow) → GLM-4.5V(OpenRouter).
      Maximizes free Gemini, falls back to best quality, then cheapest."""
    provider = os.environ.get("VISION_PROVIDER", "auto").strip().lower()
    if provider not in ("gemini", "siliconflow", "openrouter", "auto"):
        logger.warning("Unknown VISION_PROVIDER=%r — falling back to 'auto'", provider)
        provider = "auto"

    result: dict[Path, str] = {}
    paths_list = list(paths)
    for i, path in enumerate(paths_list):
        try:
            result[path] = _describe_one(path, provider)
        except Exception as e:
            result[path] = f"Error describing image: {e}"
        if i + 1 < len(paths_list):
            time.sleep(_DESCRIBE_INTER_IMAGE_SLEEP_SECS)
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
