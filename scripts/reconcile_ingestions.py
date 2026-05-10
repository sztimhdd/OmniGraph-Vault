"""Daily reconciliation cron — detect mystery ingestion rows.

Reads ingestions=ok rows for a date window and confirms each has a
corresponding LightRAG ``doc_status='processed'`` entry in
``kv_store_doc_status.json``. Read-only canary for commit ``949e3f4``
(quick 260510-h09 PROCESSED-gate hot-fix).

Quick 260510-k5q. RSS reconciliation deferred to ar-1.

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


def _compute_doc_id(url: str) -> str:
    """Mirror ``ingest_wechat.py:943,983`` byte-for-byte.

    Any deviation here creates a silent reconciliation gap — every wechat
    ingest must hash the URL identically to its production ingest path.
    """
    return f"wechat_{hashlib.md5(url.encode()).hexdigest()[:10]}"


def _load_doc_status(storage_dir: Path) -> dict[str, dict[str, Any]]:
    path = storage_dir / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _query_ok_rows(
    db_path: Path, date_start: date, date_end: date
) -> list[dict[str, Any]]:
    """Join ingestions → articles on article_id to recover URL.

    Production schema (mig 008) does NOT carry ``url`` on ``ingestions`` —
    the column lives on ``articles``. Pattern mirrors ``run_uat_ingest.py:65``.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT i.id AS id, i.article_id AS article_id, "
            "       a.url AS url, i.source AS source, "
            "       i.ingested_at AS ingested_at "
            "FROM ingestions i "
            "LEFT JOIN articles a ON a.id = i.article_id "
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
    processed_count = 0

    for row in rows:
        if row["source"] != "wechat":
            # RSS reconciliation deferred to ar-1
            continue
        doc_id = _compute_doc_id(row["url"])
        entry = status_map.get(doc_id)
        actual = entry.get("status") if isinstance(entry, dict) else None
        if isinstance(actual, str) and actual.lower() == "processed":
            processed_count += 1
            continue
        mystery_count += 1
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
        f"{processed_count} matched / {mystery_count} mystery\n"
    )
    return 1 if mystery_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
