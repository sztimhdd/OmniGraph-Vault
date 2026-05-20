"""Boot-time UC Volume → /tmp DB hydrator for Databricks Apps.

Databricks Apps runtime does NOT auto-FUSE-mount Unity Catalog volumes
(verified 2026-05-20 by surveying 16 workspace apps — none declare
volumes as resources, no app.yaml volume resource type exists). A path
like `/Volumes/.../kol_scan.db` therefore does not exist in the
container filesystem; sqlite3.connect against it fails with
"unable to open database file".

Workaround: at boot, use the SDK Files API (`w.files.download`) to copy
the read-only DB from the volume to a local file under /tmp, then point
KB_DB_PATH at the local copy via app.yaml env. The app's service
principal already has READ VOLUME on
mdlg_ai_shared.kb_v2.omnigraph_vault (verified via SHOW GRANTS), so the
SDK call authenticates implicitly through the Apps-injected identity.

Reads:
  KB_VOLUME_DB_PATH  — UC volume source (e.g. /Volumes/cat/sch/vol/.../kol_scan.db)
  KB_DB_PATH         — local target (e.g. /tmp/kol_scan.db)

Exits non-zero on failure so the App container restart loop surfaces the
problem in deployment logs instead of silently starting with a broken DB.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("kb.db_bootstrap")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def hydrate_lightrag_storage(src_dir: str, dst_dir: str) -> int:
    """Mirror UC volume LightRAG storage dir → local /tmp dir.

    Same rationale as the kol_scan.db hydrator: UC volumes are not
    auto-FUSE-mounted in Databricks Apps, so RAG_WORKING_DIR must
    point to a real local path. Lists the volume directory via SDK
    Files API and downloads each file (12 JSON/GraphML files,
    <100MB total).

    Returns 0 on success, non-zero on failure (caller decides whether
    to abort boot or degrade to KG-disabled mode).
    """
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    logger.info("Hydrating LightRAG storage: %s -> %s", src_dir, dst)
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        entries = list(w.files.list_directory_contents(src_dir))
    except Exception as e:
        logger.exception("LightRAG dir listing failed: %s", e)
        return 1

    total_bytes = 0
    for entry in entries:
        if getattr(entry, "is_directory", False):
            continue
        src_path = entry.path
        name = src_path.rsplit("/", 1)[-1]
        dst_path = dst / name
        try:
            resp = w.files.download(src_path)
            with dst_path.open("wb") as fh:
                for chunk in iter(lambda: resp.contents.read(1024 * 1024), b""):
                    fh.write(chunk)
            total_bytes += dst_path.stat().st_size
        except Exception as e:
            logger.exception("Failed downloading %s: %s", src_path, e)
            return 2

    logger.info("LightRAG storage hydration complete: %d files, %d bytes", len(entries), total_bytes)
    return 0


def main() -> int:
    src = os.environ.get("KB_VOLUME_DB_PATH")
    dst = os.environ.get("KB_DB_PATH")

    if not src:
        logger.error("KB_VOLUME_DB_PATH not set; cannot hydrate KB DB from UC volume")
        return 1
    if not dst:
        logger.error("KB_DB_PATH not set; cannot determine local target")
        return 1

    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Hydrating KB DB: %s -> %s", src, dst)

    try:
        from databricks.sdk import WorkspaceClient
    except ImportError as e:
        logger.error("databricks-sdk not installed: %s", e)
        return 2

    try:
        w = WorkspaceClient()
        resp = w.files.download(src)
        with dst_path.open("wb") as fh:
            for chunk in iter(lambda: resp.contents.read(1024 * 1024), b""):
                fh.write(chunk)
    except Exception as e:
        logger.exception("Files API download failed: %s", e)
        return 3

    size = dst_path.stat().st_size
    logger.info("Hydration complete: %s (%d bytes)", dst_path, size)
    if size == 0:
        logger.error("Hydrated DB file is empty; aborting boot")
        return 4

    try:
        import sqlite3

        from kb.data.migrations.run_migrations import run_migrations
        from kb.scripts.migrate_lang_column import migrate_lang_column

        with sqlite3.connect(dst_path) as conn:
            results = migrate_lang_column(conn)
        logger.info("lang-column migration: %s", results)

        rc = run_migrations(dst_path)
        if rc != 0:
            logger.error("SQL migrations failed with rc=%d", rc)
            return 6
        logger.info("SQL migrations complete")
    except Exception as e:
        logger.exception("DB migration failed: %s", e)
        return 5

    try:
        from kb.scripts.rebuild_fts import _rebuild as rebuild_fts

        n = rebuild_fts(str(dst_path))
        logger.info("FTS5 rebuild complete: %d rows indexed", n)
    except Exception as e:
        logger.exception("FTS5 rebuild failed: %s", e)
        return 7

    # kdb-3 LightRAG storage hydration (post-FTS, optional — degrade to
    # KG-disabled if it fails so /api/articles + /api/search?mode=fts stay up).
    lr_src = os.environ.get("KB_VOLUME_LIGHTRAG_DIR")
    lr_dst = os.environ.get("RAG_WORKING_DIR")
    if lr_src and lr_dst:
        rc = hydrate_lightrag_storage(lr_src, lr_dst)
        if rc != 0:
            logger.warning(
                "LightRAG hydration failed rc=%d; /api/synthesize will return [no-context]",
                rc,
            )
    else:
        logger.info(
            "KB_VOLUME_LIGHTRAG_DIR or RAG_WORKING_DIR unset; skipping LightRAG hydration"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
