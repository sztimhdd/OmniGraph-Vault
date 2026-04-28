"""
KOL article scanner — stores titles, URLs, and digests in SQLite.

Usage:
    python batch_scan_kol.py --days-back 120 --max-articles 20
    python batch_scan_kol.py --days-back 120 --max-articles 20 --account "叶小钗"
    python batch_scan_kol.py --resume  # skip accounts already in DB
    python batch_scan_kol.py --daily --summary-json  # daily incremental scan, JSON output

Creates data/kol_scan.db on first run. Scan only — no classification, no ingest.
"""
import argparse
import logging
import os
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import kol_config

from kol_registry import list_accounts
from spiders.wechat_spider import (
    list_articles_with_digest as list_articles,
    RATE_LIMIT_SLEEP_ACCOUNTS,
    RATE_LIMIT_SLEEP_PAGES,
    MAX_RETRIES,
)

DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"
SESSION_LIMIT = 54  # 1 req/acct for 54 KOLs; WeChat real limit ~60 (2026-04-27 calibrated)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_scan_kol")


def _load_hermes_env() -> None:
    """Load env vars from ~/.hermes/.env if not already set."""
    dotenv_paths = [
        Path.home() / ".hermes" / ".env",
        Path("//wsl.localhost/Ubuntu-24.04/home/sztimhdd/.hermes/.env"),
    ]
    for p in dotenv_paths:
        if p.exists():
            dotenv_path = p
            break
    else:
        return
    try:
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and val and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            wechat_id TEXT,
            fakeid TEXT NOT NULL UNIQUE,
            tags TEXT,
            source TEXT,
            category TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            digest TEXT,
            update_time INTEGER,
            scanned_at TEXT DEFAULT (datetime('now', 'localtime')),
            content_hash TEXT,
            enriched INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            topic TEXT NOT NULL,
            depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT,
            classified_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id, topic)
        );

        CREATE TABLE IF NOT EXISTS ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            enrichment_id TEXT,
            UNIQUE(article_id)
        );

        CREATE TABLE IF NOT EXISTS extracted_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            entity_name TEXT NOT NULL,
            entity_type TEXT,
            extracted_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS entity_canonical (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_name TEXT NOT NULL UNIQUE,
            canonical_name TEXT NOT NULL,
            entity_type TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_articles_account ON articles(account_id);
        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_classifications_topic ON classifications(topic);
        CREATE INDEX IF NOT EXISTS idx_classifications_article ON classifications(article_id);
        CREATE INDEX IF NOT EXISTS idx_extracted_entities_article ON extracted_entities(article_id);
    """)
    conn.commit()

    # Idempotent runtime migrations. SQLite ALTER TABLE ADD COLUMN is only safe
    # with an explicit PRAGMA table_info guard.
    def _ensure_column(c, table: str, column: str, type_def: str) -> None:
        cols = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")

    _ensure_column(conn, "articles", "content_hash", "TEXT")
    _ensure_column(conn, "articles", "enriched", "INTEGER DEFAULT 0")
    _ensure_column(conn, "ingestions", "enrichment_id", "TEXT")
    conn.commit()

    return conn


def init_accounts(conn: sqlite3.Connection) -> int:
    """Merge kol_registry + kol_config.FAKEIDS into accounts table. Returns count inserted."""
    registry_accounts = {a["name"]: a for a in list_accounts()}
    inserted = 0
    for name, fakeid in kol_config.FAKEIDS.items():
        reg = registry_accounts.get(name, {})
        tags = reg.get("tags", [])
        tags_json = json.dumps(tags) if tags else None
        try:
            conn.execute(
                """INSERT OR IGNORE INTO accounts (name, wechat_id, fakeid, tags, source, category, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    reg.get("wechat_id"),
                    fakeid,
                    tags_json,
                    reg.get("source"),
                    reg.get("category"),
                    reg.get("notes"),
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                inserted += 1
        except Exception as exc:
            logger.warning("Failed to insert account %s: %s", name, exc)
    conn.commit()
    return inserted


import json


def _account_has_articles(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM articles a JOIN accounts acc ON a.account_id = acc.id WHERE acc.name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _import_articles(conn: sqlite3.Connection, articles: list[dict], account_name: str, fakeid: str) -> tuple[int, int]:
    """Insert articles into DB. Returns (new, skipped) counts."""
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if row is None:
        return 0, 0
    account_id = row[0]
    new = 0
    skipped = 0
    for art in articles:
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO articles (account_id, title, url, digest, update_time) VALUES (?, ?, ?, ?, ?)",
                (account_id, art.get("title", ""), art.get("url", ""), art.get("digest", ""), art.get("update_time", 0)),
            )
            if cur.rowcount > 0:
                new += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("  DB insert failed for %s: %s", art.get("title", "")[:40], exc)
    conn.commit()
    return new, skipped


def scan_account(conn: sqlite3.Connection, name: str, fakeid: str, days_back: int, max_articles: int) -> tuple[bool, int, int]:
    """Scan single account. Returns (ok, new, skipped)."""
    logger.info("  Scanning %s (fakeid=%s)...", name, fakeid[:20] + "..." if len(fakeid) > 20 else fakeid)
    try:
        articles = list_articles(
            token=kol_config.TOKEN,
            cookie=kol_config.COOKIE,
            fakeid=fakeid,
            days_back=days_back,
            max_articles=max_articles,
        )
    except Exception as exc:
        logger.error("  Failed to scan %s: %s", name, exc)
        return False, 0, 0

    new, skipped = _import_articles(conn, articles, name, fakeid)
    logger.info("  %s: %d new, %d skipped (total %d scanned)", name, new, skipped, len(articles))
    return True, new, skipped


def run(days_back: int, max_articles: int, account_filter: str | None, resume: bool,
        daily: bool = False, summary_json: bool = False) -> None:
    _load_hermes_env()

    conn = init_db(DB_PATH)
    try:
        inserted = init_accounts(conn)
        logger.info("Accounts: %d new inserted into DB", inserted)

        rows = conn.execute("SELECT name, fakeid FROM accounts ORDER BY name").fetchall()
        if not rows:
            logger.error("No accounts in DB")
            sys.exit(1)

        # Shuffle account order so SESSION_LIMIT truncation affects different
        # accounts each day instead of always skipping the same Z-prefix ones.
        random.shuffle(rows)

        total_accounts = len(rows)
        if resume:
            rows = [(n, f) for n, f in rows if not _account_has_articles(conn, n)]
            if not rows:
                logger.info("All %d accounts already scanned (--resume). Nothing to do.", total_accounts)
                return
            logger.info("Resume mode: %d / %d accounts remaining to scan", len(rows), total_accounts)

        if account_filter:
            rows = [(n, f) for n, f in rows if n == account_filter]
            if not rows:
                logger.error("Account '%s' not found in DB", account_filter)
                sys.exit(1)

        req_count = 0
        scanned_count = 0
        failed_count = 0
        total_new = 0
        total_skipped = 0
        by_account: list[dict] = []

        for i, (name, fakeid) in enumerate(rows, 1):
            if req_count >= SESSION_LIMIT:
                logger.info(
                    "Session limit reached (%d requests). "
                    "Refresh mp.weixin.qq.com in browser then re-run.",
                    SESSION_LIMIT,
                )
                break

            logger.info("[%d/%d] %s", i, len(rows), name)
            ok, new, skipped = scan_account(conn, name, fakeid, days_back, max_articles)
            req_count += 1
            if ok:
                scanned_count += 1
                total_new += new
                total_skipped += skipped
                if summary_json:
                    by_account.append({"name": name, "new": new, "skipped": skipped})
            else:
                failed_count += 1
                if summary_json:
                    by_account.append({"name": name, "new": 0, "skipped": 0, "error": True})

            if i < len(rows) and req_count < SESSION_LIMIT:
                time.sleep(RATE_LIMIT_SLEEP_ACCOUNTS)

        logger.info(
            "Scan complete: %d ok, %d failed, %d requests.",
            scanned_count, failed_count, req_count,
        )

        if summary_json:
            summary = {
                "total_accounts": total_accounts,
                "scanned": scanned_count,
                "failed": failed_count,
                "new_articles": total_new,
                "skipped_articles": total_skipped,
                "by_account": by_account,
            }
            print(json.dumps(summary, ensure_ascii=False))

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan WeChat KOL articles into SQLite")
    parser.add_argument("--days-back", type=int, default=120, help="Days back to scan (default: 120)")
    parser.add_argument("--max-articles", type=int, default=20, help="Max articles per account (default: 20)")
    parser.add_argument("--account", type=str, default=None, help="Scan only this account name")
    parser.add_argument("--resume", action="store_true", help="Skip accounts already present in DB")
    parser.add_argument("--daily", action="store_true",
                        help="Daily incremental scan of all accounts (INSERT OR IGNORE by URL)")
    parser.add_argument("--summary-json", action="store_true",
                        help="Output JSON summary to stdout after scan")
    args = parser.parse_args()

    if args.daily and args.resume:
        parser.error("--daily and --resume are mutually exclusive")

    run(
        days_back=args.days_back,
        max_articles=args.max_articles,
        account_filter=args.account,
        resume=args.resume,
        daily=args.daily,
        summary_json=args.summary_json,
    )


if __name__ == "__main__":
    main()
