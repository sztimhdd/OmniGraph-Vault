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
from PIL import Image

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
    """Batch-describe via Gemini Vision. Rate-limits 4s between calls (D-15).

    Uses gemini_call() from config for key fallback + 503 retry + RPM guard.
    Model defaulted via IMAGE_DESCRIPTION_MODEL config key.
    """
    from config import gemini_call, IMAGE_DESCRIPTION_MODEL

    result: dict[Path, str] = {}
    paths_list = list(paths)
    for i, path in enumerate(paths_list):
        try:
            img = Image.open(path)
            response = gemini_call(
                model=IMAGE_DESCRIPTION_MODEL,
                contents=[
                    "Describe this image in detail for a knowledge graph. Return only the description.",
                    img,
                ],
            )
            result[path] = response.text
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
