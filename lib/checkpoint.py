"""Phase 12 checkpoint/resume — per-article stage persistence.

Public API documented in .planning/phases/12-checkpoint-resume/12-CONTEXT.md.
6 stages: scrape, classify, image_download, text_ingest, vision_worker, sub_doc_ingest.

Atomicity: every write follows the .tmp -> os.rename() pattern established by
cognee_batch_processor.py. A crash mid-write leaves only a .tmp file which is
invisible to has_stage() so resume logic is always safe.

Path: ~/.hermes/omonigraph-vault/checkpoints/{article_hash}/
(typo "omonigraph" is canonical per CLAUDE.md Lessons Learned -- do NOT rename.)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path

from config import BASE_DIR as _CONFIG_BASE_DIR

logger = logging.getLogger(__name__)

# Module-level for monkeypatch-friendliness in tests.
BASE_DIR: Path = _CONFIG_BASE_DIR

# Test seam: allow subprocess-invoked CLIs to redirect BASE_DIR via env var without
# needing to monkeypatch the child process. Not used in production deployments.
_env_override = os.environ.get("OMNIGRAPH_CHECKPOINT_BASE_DIR")
if _env_override:
    BASE_DIR = Path(_env_override)

STAGE_FILES: dict[str, str] = {
    "scrape": "01_scrape.html",
    "classify": "02_classify.json",
    "image_download": "03_images/manifest.json",
    "text_ingest": "04_text_ingest.done",
    "vision_worker": "05_vision/",
    "sub_doc_ingest": "06_sub_doc_ingest.done",
}

_VALID_STAGES = set(STAGE_FILES.keys())
_METADATA_FILE = "metadata.json"

# Stage ordering for list_checkpoints "last_stage" and completion logic.
# sub_doc_ingest is the terminal marker (D-SUBDOC, 2026-05-01 v3.1 closure Finding 1).
_STAGE_ORDER = [
    "scrape",
    "classify",
    "image_download",
    "text_ingest",
    "sub_doc_ingest",
]


def _checkpoints_root() -> Path:
    return BASE_DIR / "checkpoints"


def get_article_hash(url: str) -> str:
    """SHA256 first-16-hex-chars of URL bytes. Deterministic + collision-safe for URL scale."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def get_checkpoint_dir(article_hash: str) -> Path:
    """Return {BASE_DIR}/checkpoints/{article_hash}/ -- creates parents idempotently."""
    path = _checkpoints_root() / article_hash
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_path(article_hash: str, stage: str) -> Path:
    if stage not in _VALID_STAGES:
        raise ValueError(f"Unknown stage: {stage!r}. Valid: {sorted(_VALID_STAGES)}")
    return get_checkpoint_dir(article_hash) / STAGE_FILES[stage]


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via .tmp -> os.replace (crash-safe, overwrites on Windows).

    Equivalent to the cognee_batch_processor.py os.rename pattern on POSIX but
    os.replace is used so metadata.json upserts work on Windows (os.rename raises
    FileExistsError on Windows when the destination already exists; os.replace
    is the standard-library-documented atomic-and-portable spelling).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, path)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_json(path: Path, obj) -> None:
    _atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def has_stage(article_hash: str, stage: str) -> bool:
    """Return True iff the stage's marker file/dir is present. Crash-safe: ignores .tmp."""
    path = _stage_path(article_hash, stage)
    if stage == "vision_worker":
        if not path.is_dir():
            return False
        return any(p.suffix == ".json" for p in path.iterdir())
    return path.exists()


def read_stage(article_hash: str, stage: str):
    """Load committed stage data. Returns None if absent."""
    if not has_stage(article_hash, stage):
        return None
    path = _stage_path(article_hash, stage)
    if stage == "scrape":
        return path.read_text(encoding="utf-8")
    if stage == "classify":
        return json.loads(path.read_text(encoding="utf-8"))
    if stage == "image_download":
        return json.loads(path.read_text(encoding="utf-8"))
    if stage in ("text_ingest", "sub_doc_ingest"):
        return True
    if stage == "vision_worker":
        return {
            p.name: json.loads(p.read_text(encoding="utf-8"))
            for p in path.iterdir()
            if p.suffix == ".json"
        }
    raise ValueError(stage)


def write_stage(article_hash: str, stage: str, data=None) -> None:
    """Atomic write for a stage. For marker stages (text_ingest, sub_doc_ingest), data is ignored."""
    path = _stage_path(article_hash, stage)
    if stage == "scrape":
        if not isinstance(data, str):
            raise TypeError("scrape stage expects HTML string")
        _atomic_write_text(path, data)
    elif stage == "classify":
        if not isinstance(data, dict):
            raise TypeError("classify stage expects dict")
        _atomic_write_json(path, data)
    elif stage == "image_download":
        manifest = data["manifest"] if isinstance(data, dict) and "manifest" in data else data
        _atomic_write_json(path, manifest)
    elif stage in ("text_ingest", "sub_doc_ingest"):
        _atomic_write_bytes(path, b"")
    elif stage == "vision_worker":
        raise ValueError(
            "vision_worker is per-image; use write_vision_description(hash, image_id, desc)"
        )
    else:
        raise ValueError(stage)
    logger.debug("checkpoint stage=%s written for %s", stage, article_hash)


def write_vision_description(article_hash: str, image_id: str, description: dict) -> None:
    """Per-image Vision result. Path: 05_vision/{image_id}.json. Atomic."""
    target_dir = get_checkpoint_dir(article_hash) / "05_vision"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{image_id}.json"
    _atomic_write_json(path, description)


def list_vision_markers(article_hash: str) -> list[dict]:
    """Return parsed 05_vision/*.json dicts ordered by filename. [] if dir missing/empty.

    Added 2026-05-01 (D-SUBDOC). Consumed by Phase 12-02 (sub_doc_ingest stage) and
    Phase 13-02 (provider usage aggregation).
    """
    target_dir = get_checkpoint_dir(article_hash) / "05_vision"
    if not target_dir.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(target_dir.iterdir()):
        if p.suffix != ".json":
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("vision marker corrupt at %s: %s; skipping", p, e)
    return out


def read_metadata(article_hash: str) -> dict:
    """Return {} if metadata.json absent or unreadable."""
    path = get_checkpoint_dir(article_hash) / _METADATA_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("metadata.json corrupt for %s: %s; treating as empty", article_hash, e)
        return {}


def write_metadata(article_hash: str, metadata: dict) -> None:
    """Atomic upsert: merge new fields into existing metadata. Always refreshes updated_at."""
    path = get_checkpoint_dir(article_hash) / _METADATA_FILE
    now = time.time()
    existing = read_metadata(article_hash)
    merged = {**existing, **metadata}
    merged.setdefault("created_at", now)
    merged["updated_at"] = now
    _atomic_write_json(path, merged)


def reset_article(article_hash: str) -> None:
    """Idempotent removal of one article's checkpoint dir."""
    shutil.rmtree(get_checkpoint_dir(article_hash), ignore_errors=True)


def reset_all() -> None:
    """Idempotent removal of the entire checkpoints/ root."""
    shutil.rmtree(_checkpoints_root(), ignore_errors=True)


def list_checkpoints() -> list[dict]:
    """Return one record per article_hash under checkpoints/.

    Record: {hash, url, title, last_stage, age_seconds, status}.
    status: "complete" if sub_doc_ingest marker present (D-SUBDOC terminal), else "in_flight".
    """
    root = _checkpoints_root()
    if not root.is_dir():
        return []
    out: list[dict] = []
    now = time.time()
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        h = sub.name
        meta = read_metadata(h)
        last = None
        for stage in _STAGE_ORDER:
            if has_stage(h, stage):
                last = stage
        status = "complete" if has_stage(h, "sub_doc_ingest") else "in_flight"
        updated_at = meta.get("updated_at")
        age = (now - updated_at) if isinstance(updated_at, (int, float)) else None
        out.append({
            "hash": h,
            "url": meta.get("url", ""),
            "title": meta.get("title", ""),
            "last_stage": last,
            "age_seconds": age,
            "status": status,
        })
    return out
