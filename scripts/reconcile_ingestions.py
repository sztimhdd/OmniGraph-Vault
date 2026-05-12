"""Daily reconciliation cron — detect mystery ingestion rows.

Reads ingestions=ok rows for a date window (WeChat + RSS sources) and confirms
each has a corresponding LightRAG ``doc_status='processed'`` entry in
``kv_store_doc_status.json``. Read-only canary for commit ``949e3f4``
(quick 260510-h09 PROCESSED-gate hot-fix).

Quick 260510-k5q: WeChat support (initial).
Quick 260512-rrx: RSS support (scope extension).

Exit codes:
    0 — zero mystery rows detected (silent healthy day)
    1 — one or more mystery rows found (cron logs surface them)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("reconcile_ingestions")

DEFAULT_DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH") or "data/kol_scan.db")

# Import get_article_hash for RSS doc_id computation (uses SHA256[:16])
try:
    from lib.checkpoint import get_article_hash
except ImportError:
    get_article_hash = None  # type: ignore


def _compute_doc_id(url: str, source: str = "wechat") -> str:
    """Compute doc_id based on source.

    WeChat: mirrors ``ingest_wechat.py:943,983`` — MD5[:10].
    RSS: uses ``lib.checkpoint.get_article_hash`` — SHA256[:16].

    Any deviation creates a silent reconciliation gap — ingested docs must
    have matching doc_id in LightRAG kv_store_doc_status.json.
    """
    if source == "rss":
        # RSS uses SHA256[:16] (matches batch_ingest_from_spider.py + ingest_wechat.py dispatch)
        if get_article_hash:
            h = get_article_hash(url)
        else:
            h = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"rss_{h}"
    else:
        # WeChat pattern (default)
        return f"wechat_{hashlib.md5(url.encode()).hexdigest()[:10]}"


def _load_doc_status(storage_dir: Path) -> dict[str, dict[str, Any]]:
    path = storage_dir / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _query_ok_rows(
    db_path: Path, date_start: date, date_end: date
) -> list[dict[str, Any]]:
    """Join ingestions → articles (WeChat) OR rss_articles (RSS) to recover URL.

    Production schema (mig 008) carries ``url`` on ``articles`` (WeChat) and
    ``rss_articles`` (RSS). Uses LEFT JOIN with source-specific conditions.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT i.id AS id, i.article_id AS article_id, "
            "       COALESCE(a.url, r.url) AS url, i.source AS source, "
            "       i.ingested_at AS ingested_at "
            "FROM ingestions i "
            "LEFT JOIN articles a ON a.id = i.article_id AND i.source = 'wechat' "
            "LEFT JOIN rss_articles r ON r.id = i.article_id AND i.source = 'rss' "
            "WHERE i.status='ok' "
            "AND date(i.ingested_at) BETWEEN date(?) AND date(?) "
            "ORDER BY i.ingested_at",
            (date_start.isoformat(), date_end.isoformat()),
        )
        return [dict(r) for r in cur.fetchall()]


def _resolve_storage_dir(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    from config import RAG_WORKING_DIR  # type: ignore[import-not-found]
    return Path(RAG_WORKING_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect ingestions=ok rows lacking LightRAG status=processed."
        )
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date YYYY-MM-DD (window end); defaults to today.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=1,
        help="Window length in days (default 1 = end-date only).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override KOL_SCAN_DB_PATH for this invocation.",
    )
    parser.add_argument(
        "--storage-dir",
        default=None,
        help="LightRAG storage dir; defaults to config.RAG_WORKING_DIR.",
    )
    args = parser.parse_args(argv)

    end_date = date.fromisoformat(args.date) if args.date else date.today()
    start_date = end_date - timedelta(days=max(args.lookback_days - 1, 0))

    db_path = Path(args.db_path) if args.db_path else DEFAULT_DB_PATH
    storage_dir = _resolve_storage_dir(args.storage_dir)

    rows = _query_ok_rows(db_path, start_date, end_date)
    status_map = _load_doc_status(storage_dir)

    ok_count = len(rows)
    mystery_count = 0
    mystery_count_wechat = 0
    mystery_count_rss = 0
    processed_count = 0

    for row in rows:
        # Extended scope: support both wechat and rss sources
        doc_id = _compute_doc_id(row["url"], row["source"])
        entry = status_map.get(doc_id)
        actual = entry.get("status") if isinstance(entry, dict) else None
        if isinstance(actual, str) and actual.lower() == "processed":
            processed_count += 1
            continue
        mystery_count += 1
        if row["source"] == "rss":
            mystery_count_rss += 1
        else:
            mystery_count_wechat += 1
        sys.stdout.write(
            json.dumps(
                {
                    "art_id": row["article_id"],
                    "url": row["url"],
                    "doc_id": doc_id,
                    "actual_status": actual or "missing",
                    "ingested_at": row["ingested_at"],
                }
            )
            + "\n"
        )

    date_range = (
        f"{start_date.isoformat()}..{end_date.isoformat()}"
        if start_date != end_date
        else end_date.isoformat()
    )
    sys.stdout.write(
        f"{date_range}: {ok_count} ok rows / "
        f"{processed_count} matched / {mystery_count} mystery "
        f"(wechat: {mystery_count_wechat}, rss: {mystery_count_rss})\n"
    )
    return 1 if mystery_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
