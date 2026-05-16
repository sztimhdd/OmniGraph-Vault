"""Startup storage adapter for Databricks Apps.

Copies ``/Volumes/.../lightrag_storage`` to ``/tmp/`` so LightRAG's mandatory
``os.makedirs(workspace_dir, exist_ok=True)`` at storage init time does not
raise ``OSError [Errno 30]`` on the read-only UC Volume FUSE mount.

See ``.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md``
Decision 1 + Decision 2 for the rationale.

Phase: kdb-1.5 (storage adapter)
Requirement: STORAGE-DBX-05 (alternative satisfaction path)
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
TMP_ROOT = "/tmp/omnigraph_vault"
LIGHTRAG_SUBDIR = "lightrag_storage"


@dataclass(frozen=True)
class CopyResult:
    """Outcome of a single hydration call.

    Attributes:
        status: ``"copied"`` or ``"skipped"``.
        reason: Populated when ``status == "skipped"``; one of
            ``"already_hydrated"`` or ``"source_empty_pre_seed"``.
        method: Populated when ``status == "copied"``; one of ``"fuse"`` or ``"sdk"``.
        elapsed_s: Wall-clock seconds for the copy (``None`` when skipped).
        bytes_copied: Sum of file sizes under ``dst`` after copy (``None`` when skipped).
    """

    status: str
    reason: str | None = None
    method: str | None = None
    elapsed_s: float | None = None
    bytes_copied: int | None = None


def _bytes_in_dir(p: Path) -> int:
    """Sum file sizes under ``p`` recursively."""
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def hydrate_lightrag_storage_from_volume(
    volume_root: str = VOLUME_ROOT,
    tmp_root: str = TMP_ROOT,
) -> CopyResult:
    """Copy ``volume_root/lightrag_storage`` to ``tmp_root/lightrag_storage``.

    Idempotent: returns ``CopyResult(status="skipped", reason="already_hydrated")``
    when the destination already contains files. Raises ``RuntimeError`` if
    ``/tmp`` itself is not writable.

    Args:
        volume_root: UC Volume root (default: production VOLUME_ROOT).
        tmp_root: App-local writable cache root (default: production TMP_ROOT).

    Returns:
        CopyResult describing the outcome.

    Raises:
        RuntimeError: when ``/tmp`` is not writable (defensive per RESEARCH Risk 5).
    """
    if not os.access("/tmp", os.W_OK):
        raise RuntimeError("/tmp is not writable; storage adapter cannot proceed")

    src = Path(volume_root) / LIGHTRAG_SUBDIR
    dst = Path(tmp_root) / LIGHTRAG_SUBDIR

    # Idempotency check: if dst already has content, short-circuit
    if dst.exists() and any(dst.iterdir()):
        logger.info(
            "startup_adapter: skip already_hydrated dst=%s",
            dst,
        )
        return CopyResult(status="skipped", reason="already_hydrated")

    dst.mkdir(parents=True, exist_ok=True)

    # FUSE primary path — taken when the Volume is mounted OR src exists locally
    if os.path.ismount(volume_root) or src.exists():
        if not src.exists() or not any(src.iterdir()):
            logger.info(
                "startup_adapter: skip source_empty_pre_seed src=%s",
                src,
            )
            return CopyResult(status="skipped", reason="source_empty_pre_seed")
        t0 = time.time()
        shutil.copytree(src, dst, dirs_exist_ok=True)
        elapsed = time.time() - t0
        n_bytes = _bytes_in_dir(dst)
        logger.info(
            "startup_adapter: copied via fuse elapsed_s=%.3f bytes=%d",
            elapsed,
            n_bytes,
        )
        return CopyResult(
            status="copied",
            method="fuse",
            elapsed_s=elapsed,
            bytes_copied=n_bytes,
        )

    # SDK fallback path — lazy import keeps tests independent of databricks-sdk
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    t0 = time.time()
    w.files.download_directory(str(src), str(dst), overwrite=True)
    elapsed = time.time() - t0
    n_bytes = _bytes_in_dir(dst)
    logger.info(
        "startup_adapter: copied via sdk elapsed_s=%.3f bytes=%d",
        elapsed,
        n_bytes,
    )
    return CopyResult(
        status="copied",
        method="sdk",
        elapsed_s=elapsed,
        bytes_copied=n_bytes,
    )
