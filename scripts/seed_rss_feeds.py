"""Seed rss_feeds table from bundled OPML.

Idempotent via INSERT OR IGNORE (xml_url UNIQUE constraint). Safe to re-run.
Run after batch_scan_kol.init_db has created the rss_feeds table.

Usage:
    venv/bin/python scripts/seed_rss_feeds.py              # run
    venv/bin/python scripts/seed_rss_feeds.py --dry-run    # preview
    venv/bin/python scripts/seed_rss_feeds.py --opml data/alt.opml --db data/other.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_OPML = Path("data/karpathy_hn_2025.opml")
DEFAULT_DB = Path("data/kol_scan.db")


def parse_opml(path: Path) -> list[dict]:
    tree = ET.parse(path)
    feeds: list[dict] = []
    for outline in tree.getroot().findall(".//outline[@type='rss']"):
        feeds.append(
            {
                "name": outline.get("text") or outline.get("title") or "",
                "xml_url": outline.get("xmlUrl") or "",
                "html_url": outline.get("htmlUrl") or None,
                "category": None,
            }
        )
    return [f for f in feeds if f["xml_url"]]


def seed(db_path: Path, feeds: list[dict], dry_run: bool) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
        if not dry_run:
            conn.executemany(
                "INSERT OR IGNORE INTO rss_feeds (name, xml_url, html_url, category) "
                "VALUES (?, ?, ?, ?)",
                [
                    (f["name"], f["xml_url"], f["html_url"], f["category"])
                    for f in feeds
                ],
            )
            conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
        return before, after
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--opml", type=Path, default=DEFAULT_OPML)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.opml.exists():
        print(f"ERROR: OPML not found at {args.opml}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(
            f"ERROR: DB not found at {args.db}; run batch_scan_kol.init_db first",
            file=sys.stderr,
        )
        return 2

    feeds = parse_opml(args.opml)
    print(f"Parsed {len(feeds)} feeds from {args.opml}")
    before, after = seed(args.db, feeds, args.dry_run)
    print(f"rss_feeds count: {before} -> {after}")
    if args.dry_run:
        print("(dry-run: no writes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
