"""Test scripts/backfill_image_count.py -- D2 (issue #2 follow-up).

Pure-unit: tmp_path + monkeypatch + sqlite memory-style tmp file.
No production DB or filesystem touched.
"""
from __future__ import annotations

import hashlib
import sqlite3


def test_count_images_existing_dir_returns_count(tmp_path, monkeypatch) -> None:
    """images/{md5(url)[:10]}/ with 5 jpg + 1 .json file -> returns 5."""
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    # Reload module so it picks up the env override.
    import importlib
    import scripts.backfill_image_count as bf
    importlib.reload(bf)

    url = "https://example.com/exist"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    for i in range(1, 6):
        (img_dir / f"{i}.jpg").write_bytes(b"")
    (img_dir / "metadata.json").write_text("{}")
    assert bf.count_images(url) == 5


def test_count_images_missing_dir_returns_zero(tmp_path, monkeypatch) -> None:
    """url with no images dir -> 0, no exception."""
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    import importlib
    import scripts.backfill_image_count as bf
    importlib.reload(bf)
    assert bf.count_images("https://example.com/missing") == 0


def test_backfill_updates_rows_with_disk_files(tmp_path, monkeypatch) -> None:
    """End-to-end: 2 articles, 1 with disk files -> exactly 1 row updated."""
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    # Build a tmp sqlite with mig-011 shape.
    db_path = tmp_path / "kol_scan.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT, image_count INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, url TEXT, image_count INTEGER DEFAULT 0)"
    )
    url_with = "https://mp.weixin.qq.com/s/has_imgs"
    url_without = "https://mp.weixin.qq.com/s/no_imgs"
    conn.execute("INSERT INTO articles(url) VALUES (?)", (url_with,))
    conn.execute("INSERT INTO articles(url) VALUES (?)", (url_without,))
    conn.commit()
    conn.close()

    # Disk files only for url_with.
    h = hashlib.md5(url_with.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    for i in range(1, 8):
        (img_dir / f"{i}.png").write_bytes(b"")

    # Monkeypatch DB_PATH so backfill reads our tmp DB.
    import importlib
    import scripts.backfill_image_count as bf
    importlib.reload(bf)
    monkeypatch.setattr(bf, "DB_PATH", db_path)

    updated, total = bf.backfill("articles")
    assert updated == 1, f"expected 1 row updated, got {updated}"
    assert total == 7, f"expected 7 total images, got {total}"

    # Confirm DB state.
    conn = sqlite3.connect(str(db_path))
    rows = dict(conn.execute("SELECT url, image_count FROM articles").fetchall())
    conn.close()
    assert rows[url_with] == 7
    assert rows[url_without] == 0
