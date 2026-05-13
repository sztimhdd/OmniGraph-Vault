"""Backfill image_count for historical rows -- D2 (issue #2 follow-up).

One-shot idempotent script. Walks articles + rss_articles tables; for each
row with a non-empty url, computes the on-disk image count under
``$OMNIGRAPH_BASE_DIR/images/{md5(url)[:10]}/`` and UPDATEs the row.

Idempotent: re-running yields the same count for rows whose disk dir is
unchanged. Only writes when n > 0 to avoid no-op writes (rows pre-mig-011
read as 0 via column DEFAULT, so leaving them as 0 is equivalent).

Hash convention reuses T1-b1 (_count_images_on_disk) -- md5(url.encode())[:10].

Run AFTER applying mig 011. Smoke locally:
    python -c "from scripts.backfill_image_count import count_images, backfill, main"

NOT run in this quick -- prod application deferred to user-initiated push +
Hermes execution.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

# Mirror lib/article_filter._count_images_on_disk extension list.
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH", str(REPO_ROOT / "data" / "kol_scan.db")))


def _base_dir() -> Path:
    """Resolve OMNIGRAPH_BASE_DIR at call time (env may be set after import)."""
    base = os.environ.get("OMNIGRAPH_BASE_DIR") or str(Path("~/.hermes/omonigraph-vault").expanduser())
    return Path(base).expanduser()


def count_images(url: str) -> int:
    """Count downloaded image files under ``$BASE/images/{md5(url)[:10]}/``.

    Returns 0 on missing url, missing dir, or I/O error. Lower-cased suffix
    matching so ``.JPG`` etc. are caught (matches T1-b1 mixed-extension test).
    """
    if not url:
        return 0
    article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    img_dir = _base_dir() / "images" / article_hash
    if not img_dir.is_dir():
        return 0
    try:
        return sum(
            1 for p in img_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _IMG_EXT
        )
    except OSError:
        return 0


def backfill(table: str) -> tuple[int, int]:
    """Walk ``table`` (articles or rss_articles); UPDATE image_count from disk.

    Only writes rows where count > 0 (rows w/ no disk dir read as 0 via DEFAULT
    after mig 011, so the no-op write is skipped).

    Returns (rows_updated, total_image_count).
    """
    rows_updated = 0
    total_image_count = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(f"SELECT id, url FROM {table}").fetchall()
        for row_id, url in rows:
            n = count_images(url or "")
            if n > 0:
                conn.execute(
                    f"UPDATE {table} SET image_count = ? WHERE id = ?",
                    (n, row_id),
                )
                rows_updated += 1
                total_image_count += n
        conn.commit()
    return rows_updated, total_image_count


def main() -> int:
    t0 = time.monotonic()
    a_updated, a_total = backfill("articles")
    r_updated, r_total = backfill("rss_articles")
    elapsed = time.monotonic() - t0
    print(
        f"backfill done: articles updated={a_updated} (total imgs={a_total}); "
        f"rss_articles updated={r_updated} (total imgs={r_total}); "
        f"elapsed={elapsed:.2f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
