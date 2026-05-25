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

import concurrent.futures
import logging
import os
import shutil
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


def hydrate_images_dir(src_dir: str, dst_dir: str) -> int:
    """Mirror UC volume images dir → local /tmp dir (2-level: <hash>/<N>.jpg).

    kb/api.py mounts /static/img to KB_IMAGES_DIR via StaticFiles(check_dir=False);
    on Databricks Apps the default ~/.hermes/... path does not exist, so every
    image request 404s. Walk the volume two levels deep and download all .jpg
    files in parallel via ThreadPoolExecutor (max_workers=16). Volume layout:
    <root>/<article_hash>/<N>.jpg, ~254 dirs / ~2500 files / ~47MB.

    Degrades gracefully: per-file failures log a warning and continue; the
    function returns non-zero on partial/total failure but caller should NOT
    abort boot — broken images are tolerable, broken /api/articles is not.
    """
    dst = Path(dst_dir)
    # /tmp is preserved across container restarts within a single deployment.
    # Earlier buggy hydrations (pre-rstrip-fix) wrote files flat at the dst
    # root because rsplit on a trailing-slash directory path returned "",
    # collapsing hash_dst back to dst. Those stale flat files survive next
    # to subsequent correct nested layouts. Volume is the canonical source —
    # wipe dst before rebuilding so the layout matches the volume exactly.
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    logger.info("Hydrating images: %s -> %s", src_dir, dst)

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        hash_entries = list(w.files.list_directory_contents(src_dir))
    except Exception as e:
        logger.exception("Image dir listing failed: %s", e)
        return 1

    file_jobs: list[tuple[str, Path]] = []
    for hash_entry in hash_entries:
        if not getattr(hash_entry, "is_directory", False):
            continue
        hash_path = hash_entry.path
        # SDK DirectoryEntry.path appends trailing slash for directories;
        # rstrip first so rsplit doesn't return empty string (which would
        # collapse hash_dst back to dst and write all files flat).
        hash_name = hash_path.rstrip("/").rsplit("/", 1)[-1]
        hash_dst = dst / hash_name
        hash_dst.mkdir(parents=True, exist_ok=True)
        try:
            file_entries = list(w.files.list_directory_contents(hash_path))
        except Exception as e:
            logger.warning("Failed listing %s: %s", hash_path, e)
            continue
        for file_entry in file_entries:
            if getattr(file_entry, "is_directory", False):
                continue
            src_file = file_entry.path
            file_name = src_file.rstrip("/").rsplit("/", 1)[-1]
            file_jobs.append((src_file, hash_dst / file_name))

    if not file_jobs:
        logger.warning("No image files found under %s", src_dir)
        return 2

    def _download_one(job: tuple[str, Path]) -> int:
        src_file, dst_path = job
        try:
            resp = w.files.download(src_file)
            with dst_path.open("wb") as fh:
                for chunk in iter(lambda: resp.contents.read(1024 * 1024), b""):
                    fh.write(chunk)
            return dst_path.stat().st_size
        except Exception as e:
            logger.warning("Failed downloading %s: %s", src_file, e)
            return -1

    total_bytes = 0
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for size in pool.map(_download_one, file_jobs):
            if size < 0:
                failures += 1
            else:
                total_bytes += size

    ok_count = len(file_jobs) - failures
    logger.info("Image hydration complete: %d files, %d bytes", ok_count, total_bytes)
    if failures:
        logger.warning("Image hydration had %d failures (out of %d)", failures, len(file_jobs))
        return 3
    return 0


def hydrate_gcp_sa(src: str, dst: str) -> int:
    """Download GCP service-account JSON from UC volume → local /tmp.

    arx-2: embedding is unconditionally Vertex (3072-dim); SA must be present
    before LightRAG initialises. Boot aborts (rc=8) if this fails.
    """
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Hydrating GCP SA: %s -> %s", src, dst_path)
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        resp = w.files.download(src)
        with dst_path.open("wb") as fh:
            for chunk in iter(lambda: resp.contents.read(1024 * 1024), b""):
                fh.write(chunk)
    except Exception as e:
        logger.exception("GCP SA download failed: %s", e)
        return 1
    size = dst_path.stat().st_size
    if size == 0:
        logger.error("GCP SA file is empty; aborting boot")
        return 2
    try:
        os.chmod(dst_path, 0o600)
    except OSError as e:
        logger.warning("chmod 0600 on GCP SA failed (non-fatal): %s", e)
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

    # arx-2: hydrate GCP SA JSON from UC volume → /tmp so lib/lightrag_embedding.py
    # can authenticate to Vertex AI (3072-dim). Must run before LightRAG hydration.
    gcp_sa_src = os.environ.get("KB_VOLUME_GCP_SA_PATH")
    gcp_sa_dst = os.environ.get("KB_KG_GCP_SA_KEY_PATH")
    if gcp_sa_src and gcp_sa_dst:
        rc = hydrate_gcp_sa(gcp_sa_src, gcp_sa_dst)
        if rc != 0:
            logger.error(
                "GCP SA hydration failed rc=%d; Vertex embedding unavailable, "
                "aborting boot to prevent LightRAG init OOM",
                rc,
            )
            return 8
    else:
        logger.warning(
            "KB_VOLUME_GCP_SA_PATH or KB_KG_GCP_SA_KEY_PATH unset; "
            "skipping GCP SA hydration (KG mode will degrade)"
        )

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

    # kdb-images-fix: hydrate UC volume images → /tmp at boot.
    # Image-only failure must NOT block boot (degrade to broken images, not
    # broken /api/articles or /api/search).
    img_src = os.environ.get("KB_VOLUME_IMAGES_DIR")
    img_dst = os.environ.get("KB_IMAGES_DIR")
    if img_src and img_dst:
        rc = hydrate_images_dir(img_src, img_dst)
        if rc != 0:
            logger.warning(
                "Image hydration failed rc=%d; /static/img/* will return 404", rc
            )
    else:
        logger.info(
            "KB_VOLUME_IMAGES_DIR or KB_IMAGES_DIR unset; skipping image hydration"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
