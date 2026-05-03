"""Verify bundled OPML parses to at least 90 RSS feeds.

Usage:
    venv/bin/python tests/verify_rss_opml.py
    venv/bin/python tests/verify_rss_opml.py --opml data/other.opml
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_SAMPLES: tuple[str, ...] = ("simonwillison", "gwern", "antirez")


def _main(opml_path: Path) -> int:
    if not opml_path.exists():
        print(f"OPML not found at {opml_path}", file=sys.stderr)
        return 2
    tree = ET.parse(opml_path)
    feeds = tree.getroot().findall(".//outline[@type='rss']")
    print(f"feed_count: {len(feeds)}")
    if len(feeds) < 90:
        print(f"FAIL: expected >= 90 feeds, got {len(feeds)}", file=sys.stderr)
        return 1
    urls = [(f.get("xmlUrl") or "") for f in feeds]
    missing = [s for s in EXPECTED_SAMPLES if not any(s in u for u in urls)]
    if missing:
        print(f"FAIL: missing expected samples: {missing}", file=sys.stderr)
        return 1
    print("OK: OPML parse + sample check passed")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--opml", type=Path, default=Path("data/karpathy_hn_2025.opml"))
    args = p.parse_args()
    sys.exit(_main(args.opml))
