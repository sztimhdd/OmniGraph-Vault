"""RSS fetcher — iterates over active rss_feeds, writes new rows to rss_articles.

Pre-filter (PRD §3.1.3):
  - skip entries < MIN_CONTENT_CHARS (500)
  - skip entries whose detected language is not in SUPPORTED_LANGS

Fault tolerance (PRD §3.1.3):
  - per-feed try/except
  - socket-level timeout FEED_TIMEOUT_SECONDS (15s)
  - FEED_DELAY_SECONDS (2s) between feeds
  - increment rss_feeds.error_count on failure; reset to 0 on success
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any

import feedparser
from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0  # deterministic language detection

DB = Path("data/kol_scan.db")
FEED_DELAY_SECONDS = 2.0
FEED_TIMEOUT_SECONDS = 15
MIN_CONTENT_CHARS = 500
SUPPORTED_LANGS = {"en", "zh-cn", "zh-tw", "zh"}
USER_AGENT = "OmniGraph-Vault/1.0 (+https://github.com/sztimhdd/OmniGraph-Vault)"

logger = logging.getLogger("rss_fetch")


def _content_text(entry: Any) -> str:
    """Extract the largest text body from a feedparser entry."""
    content_list = getattr(entry, "content", None)
    if content_list:
        bodies = [c.get("value", "") for c in content_list]
        if bodies:
            return max(bodies, key=len)
    return (
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
        or ""
    )


def _should_keep(text: str) -> tuple[bool, str]:
    if len(text) < MIN_CONTENT_CHARS:
        return False, "too_short"
    try:
        lang = detect(text[:2000])
    except LangDetectException:
        return False, "langdetect_failed"
    if lang not in SUPPORTED_LANGS:
        return False, f"unsupported_lang:{lang}"
    return True, ""


def _fetch_feed(xml_url: str) -> list[dict]:
    """Fetch one feed; return list of article dicts ready for INSERT.

    Raises RuntimeError when the feed is unreachable or malformed (bozo=1 AND
    no usable entries) so the caller can count it as a feed-level failure.
    """
    socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)
    parsed = feedparser.parse(xml_url, agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(
            f"feed unreachable or malformed: {parsed.bozo_exception!r}"
        )
    articles: list[dict] = []
    for entry in parsed.entries:
        text = _content_text(entry)
        keep, reason = _should_keep(text)
        if not keep:
            logger.debug(
                "skip %s: %s", getattr(entry, "link", "?"), reason
            )
            continue
        articles.append(
            {
                "title": getattr(entry, "title", "") or "",
                "url": getattr(entry, "link", "") or "",
                "author": getattr(entry, "author", None),
                "summary": getattr(entry, "summary", "") or "",
                "content_hash": hashlib.md5(
                    text.encode("utf-8")
                ).hexdigest(),
                "published_at": getattr(entry, "published", None),
                "content_length": len(text),
            }
        )
    return [a for a in articles if a["url"]]


def _insert_articles(
    conn: sqlite3.Connection, feed_id: int, articles: list[dict]
) -> int:
    inserted = 0
    for a in articles:
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO rss_articles
                   (feed_id, title, url, author, summary, content_hash,
                    published_at, content_length)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feed_id,
                    a["title"],
                    a["url"],
                    a["author"],
                    a["summary"],
                    a["content_hash"],
                    a["published_at"],
                    a["content_length"],
                ),
            )
            # cur.rowcount == 1 is the correct per-row indicator.
            # conn.total_changes is cumulative across the connection.
            if cur.rowcount == 1:
                inserted += 1
        except Exception as ex:
            logger.warning("insert failed for %s: %s", a["url"], ex)
    return inserted


def run(max_feeds: int | None, dry_run: bool, db_path: Path = DB) -> dict:
    conn = sqlite3.connect(db_path)
    feeds = conn.execute(
        "SELECT id, xml_url, name FROM rss_feeds WHERE active=1 ORDER BY id"
    ).fetchall()
    if max_feeds is not None:
        feeds = feeds[:max_feeds]
    stats = {"feeds_ok": 0, "feeds_fail": 0, "articles_inserted": 0}
    for feed_id, xml_url, name in feeds:
        try:
            articles = _fetch_feed(xml_url)
            if not dry_run:
                stats["articles_inserted"] += _insert_articles(
                    conn, feed_id, articles
                )
                conn.execute(
                    "UPDATE rss_feeds SET last_fetched_at=datetime('now','localtime'), "
                    "error_count=0 WHERE id=?",
                    (feed_id,),
                )
                conn.commit()
            stats["feeds_ok"] += 1
            logger.info("OK %s: %d candidates", name, len(articles))
        except Exception as ex:
            stats["feeds_fail"] += 1
            logger.warning("FAIL %s (%s): %s", name, xml_url, ex)
            if not dry_run:
                conn.execute(
                    "UPDATE rss_feeds SET error_count=error_count+1 WHERE id=?",
                    (feed_id,),
                )
                conn.commit()
        time.sleep(FEED_DELAY_SECONDS)
    conn.close()
    return stats


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser()
    p.add_argument("--max-feeds", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    stats = run(args.max_feeds, args.dry_run)
    logger.info("stats: %s", stats)
    print(
        json.dumps(
            {
                "status": "ok",
                "feeds_ok": stats["feeds_ok"],
                "feeds_fail": stats["feeds_fail"],
                "articles_inserted": stats["articles_inserted"],
            }
        )
    )


if __name__ == "__main__":
    main()
