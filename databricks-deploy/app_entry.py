"""Databricks Apps entrypoint — kb.api:app + SSG static frontend mount.

Single-tier serving: Aliyun deploy uses Caddy in front of FastAPI to serve
the kb/output/ SSG at `/` while FastAPI handles `/api/*` and `/static/img/*`.
Databricks Apps has no Caddy layer, so FastAPI must serve the static frontend
itself. This shim:

  1. Imports the canonical kb.api:app (routers, /static/img mount, /health).
  2. Mounts kb/output/ at `/` LAST so the catch-all StaticFiles only handles
     paths that haven't matched a router or earlier mount (FastAPI mount
     resolution is registration-order, last mount with matching prefix wins
     for paths none of the earlier handlers claim).

Boot command points uvicorn at `app_entry:app` instead of `kb.api:app`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from kb import config
from kb.api import app

logger = logging.getLogger("kb.app_entry")

_debug_router = APIRouter(prefix="/__debug")


@_debug_router.get("/sdk-probe")
async def sdk_probe() -> dict:
    """Raw SDK list_directory_contents probe for hydration debugging.

    Calls list_directory_contents on KB_VOLUME_IMAGES_DIR and reports the
    first 30 entries with their (path, is_directory) tuple — to verify
    whether the SDK is reporting all entries as directories or whether
    some hash entries come back is_directory=False (which would be
    silently skipped by hydrate_images_dir).
    """
    try:
        from _db_client import get_databricks_client
        w = get_databricks_client()
    except Exception as e:
        return {"error": f"WorkspaceClient init failed: {e}"}

    src = os.environ.get("KB_VOLUME_IMAGES_DIR", "<unset>")
    out: dict = {"src": src, "entries": []}

    try:
        entries = list(w.files.list_directory_contents(src))
    except Exception as e:
        out["error"] = f"list_directory_contents failed: {e}"
        return out

    out["entry_count"] = len(entries)
    is_dir_true = 0
    is_dir_false = 0
    for e in entries:
        path = getattr(e, "path", "<no-path>")
        is_dir = getattr(e, "is_directory", None)
        if is_dir is True:
            is_dir_true += 1
        elif is_dir is False:
            is_dir_false += 1
        if len(out["entries"]) < 30:
            out["entries"].append({"path": path, "is_directory": is_dir})
    out["is_directory_true_count"] = is_dir_true
    out["is_directory_false_count"] = is_dir_false

    test_hash = "009b932a7d"
    inner_path = f"{src.rstrip('/')}/{test_hash}"
    try:
        inner = list(w.files.list_directory_contents(inner_path))
        out["inner_test"] = {
            "path": inner_path,
            "count": len(inner),
            "first_3": [
                {
                    "path": getattr(x, "path", None),
                    "is_directory": getattr(x, "is_directory", None),
                }
                for x in inner[:3]
            ],
        }
    except Exception as e:
        out["inner_test_error"] = f"{type(e).__name__}: {e}"

    return out


@_debug_router.get("/img-fs")
async def img_fs() -> dict:
    """Ground-truth probe of KB_IMAGES_DIR on running container.

    Databricks-Apps-only diagnostic — exposes runtime fs state of the
    hydrated images dir so we can tell whether _db_bootstrap actually
    wrote files to disk regardless of what its log claims.
    """
    imgs = config.KB_IMAGES_DIR
    sample_hash = "9cbd555c68"
    sample_file = imgs / sample_hash / "14.jpg"
    sample_dir = imgs / sample_hash

    result: dict = {
        "kb_images_dir": str(imgs),
        "kb_images_dir_resolved": str(imgs.resolve()) if imgs.exists() else None,
        "exists": imgs.exists(),
        "is_dir": imgs.is_dir() if imgs.exists() else False,
    }

    if imgs.exists() and imgs.is_dir():
        try:
            top = sorted(os.listdir(imgs))
            result["top_entry_count"] = len(top)
            result["top_entries_sample"] = top[:20]
        except Exception as e:
            result["top_listing_error"] = str(e)

        if sample_dir.exists() and sample_dir.is_dir():
            try:
                files = sorted(os.listdir(sample_dir))
                result["sample_hash_dir"] = sample_hash
                result["sample_hash_dir_file_count"] = len(files)
                result["sample_hash_dir_files"] = files[:10]
            except Exception as e:
                result["sample_hash_listing_error"] = str(e)
        else:
            result["sample_hash_dir_status"] = (
                f"MISSING — {sample_dir} does not exist as directory"
            )

        if sample_file.exists():
            try:
                result["sample_file_size_bytes"] = sample_file.stat().st_size
            except Exception as e:
                result["sample_file_stat_error"] = str(e)
        else:
            result["sample_file_status"] = f"MISSING — {sample_file}"

        result["env_kb_volume_images_dir"] = os.environ.get(
            "KB_VOLUME_IMAGES_DIR", "<unset>"
        )
        result["env_kb_images_dir"] = os.environ.get("KB_IMAGES_DIR", "<unset>")

    return result


app.include_router(_debug_router)
logger.info("Mounted /__debug/img-fs probe endpoint")

# SSG output is copied into databricks-deploy/_ssg/ at deploy time
# (Makefile target rsyncs kb/output/ → databricks-deploy/_ssg/ before pass-1
# sync). kb/output/ itself is .gitignored AND has an inner */-include guard
# that .databricksignore negation cannot override, so deploy-time copy is the
# only reliable channel to land the SSG inside source_code_path/.
_SSG_DIR = Path(__file__).resolve().parent / "_ssg"

if _SSG_DIR.exists() and (_SSG_DIR / "index.html").exists():
    app.mount(
        "/",
        StaticFiles(directory=str(_SSG_DIR), html=True),
        name="ssg",
    )
    logger.info("Mounted SSG frontend at / from %s", _SSG_DIR)
else:
    logger.warning(
        "SSG dir missing or empty (%s); / will return 404 until kb/output is synced",
        _SSG_DIR,
    )
