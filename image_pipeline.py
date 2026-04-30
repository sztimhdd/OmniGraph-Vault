"""Shared image-handling pipeline for WeChat + Zhihu ingestion paths.

Extracted from ingest_wechat.py as part of Phase 4 refactor (D-15, D-16).
All functions are sync; callers wrap in asyncio.to_thread if needed.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Rate-limit between Gemini Vision describe_images calls (D-15).
_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 4

# Local image server base — matches ingest_wechat.py historical value.
_DEFAULT_IMAGE_BASE_URL = "http://localhost:8765"


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


def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe via GLM-4.5V (OpenRouter). Rate-limits 4s between calls (D-15).

    Phase 5-00b: switched from Gemini Vision to GLM-4.5V.
    Gemini 3.1 Flash Lite free tier = 500 RPD (exhausted on both projects).
    GLM-4.5V = $0.0001/call via OpenRouter, no daily quota cap."""
    import base64, requests
    from io import BytesIO

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        return {p: "Error describing image: OPENROUTER_API_KEY not set" for p in paths}

    result: dict[Path, str] = {}
    for i, path in enumerate(paths):
        try:
            img = Image.open(path)
            buf = BytesIO()
            fmt = "PNG" if path.suffix.lower() == ".png" else "JPEG"
            img.save(buf, format=fmt)
            b64 = base64.b64encode(buf.getvalue()).decode()
            mime = f"image/{fmt.lower()}"

            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
                json={
                    "model": "z-ai/glm-4.5v",
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "Describe this image in detail for a knowledge graph. Return only the description."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    ]}],
                    "max_tokens": 300,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"] or ""
                result[path] = content.strip()
            else:
                result[path] = f"Error describing image: HTTP {resp.status_code}"
        except Exception as e:
            result[path] = f"Error describing image: {e}"
        if i + 1 < len(paths):
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
