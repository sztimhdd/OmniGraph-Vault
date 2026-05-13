"""DATA-02 + DATA-03: Walk articles + rss_articles, populate `lang` column.

Idempotent: only updates rows where `lang IS NULL`. Safe to re-invoke daily
via cron (DATA-03).

Auto-runs migration if `lang` column is missing (allows fresh DB usage).

Algorithm: kb.data.lang_detect.detect_lang(body) -> 'zh-CN' | 'en' | 'unknown'
    - Chinese char ratio > 30% AND len(body) >= 200 -> 'zh-CN'
    - Chinese char ratio <= 30% AND len(body) >= 200 -> 'en'
    - len(body) < 200 -> 'unknown' (insufficient sample)
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

from kb import config
from kb.data.lang_detect import detect_lang
from kb.scripts.migrate_lang_column import migrate_lang_column

_TABLES: tuple[str, ...] = ("articles", "rss_articles")


def _ensure_lang_column(conn: sqlite3.Connection) -> None:
    """Run migration if either table is missing the lang column.

    Safe on fresh DBs: migrate_lang_column handles missing tables by
    returning 'table_missing' for them.
    """
    for table in _TABLES:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if cols and "lang" not in cols:
            migrate_lang_column(conn)
            return
        if not cols:
            # Table doesn't exist; let migrate_lang_column decide what to do.
            migrate_lang_column(conn)
            return


def detect_for_table(conn: sqlite3.Connection, table: str) -> Counter[str]:
    """Update lang for rows where lang IS NULL. Returns Counter of new assignments.

    Skips tables that don't exist (returns empty Counter).
    Idempotent — second invocation produces zero UPDATEs because the WHERE
    filter excludes already-classified rows.
    """
    result: Counter[str] = Counter()
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return result

    rows = conn.execute(
        f"SELECT id, body FROM {table} WHERE lang IS NULL"
    ).fetchall()
    for row_id, body in rows:
        lang = detect_lang(body or "")
        conn.execute(f"UPDATE {table} SET lang = ? WHERE id = ?", (lang, row_id))
        result[lang] += 1
    conn.commit()
    return result


def coverage_for_table(conn: sqlite3.Connection, table: str) -> Counter[str]:
    """Return lang distribution across all rows (NULL counted as 'NULL')."""
    result: Counter[str] = Counter()
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return result
    for (lang,) in conn.execute(f"SELECT lang FROM {table}"):
        result[lang or "NULL"] += 1
    return result


def main() -> int:
    db_path: Path = config.KB_DB_PATH
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        return 1
    with sqlite3.connect(db_path) as conn:
        _ensure_lang_column(conn)
        for table in _TABLES:
            updated = detect_for_table(conn, table)
            coverage = coverage_for_table(conn, table)
            print(f"{table}: updated={dict(updated)}, total_coverage={dict(coverage)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
