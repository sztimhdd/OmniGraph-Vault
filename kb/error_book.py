"""Persistent deduplicating Error Book for Wiki lint failures (W5-0 Gate E).

Replaces flat JSONL (~/.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl)
with SQLite-backed store at kb/wiki/error_book.db.

Features:
- Fingerprint dedup (CHECK_TYPE:SLUG:EVIDENCE_KEY) — same issue logged once
- Resolvable: open → resolved/ignored lifecycle
- Queryable: SQL for open issues, per-page history, trend analysis
- Automatic migration of legacy JSONL on first access
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = Path("kb/wiki/error_book.db")
_LEGACY_JSONL = Path(".planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lint_errors (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    check_type TEXT NOT NULL,
    page_slug  TEXT NOT NULL,
    evidence   TEXT NOT NULL,
    payload    TEXT NOT NULL,          -- JSON blob of full failure dict
    status     TEXT NOT NULL DEFAULT 'open',  -- open|resolved|ignored
    first_seen TEXT NOT NULL,          -- ISO timestamp
    last_seen  TEXT NOT NULL,          -- ISO timestamp
    seen_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_lint_status ON lint_errors(status);
CREATE INDEX IF NOT EXISTS idx_lint_page   ON lint_errors(page_slug);
CREATE INDEX IF NOT EXISTS idx_lint_check  ON lint_errors(check_type);
"""


def _fingerprint(check_type: str, page_slug: str, evidence: str) -> str:
    """Stable dedup key: SHA256 of `check_type:page_slug:evidence[:80]`."""
    key = f"{check_type}:{page_slug}:{evidence[:80]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _migrate_jsonl(db_path: Path) -> int:
    """Import legacy JSONL entries into Error Book. Returns count migrated."""
    if not _LEGACY_JSONL.exists():
        return 0
    count = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(CREATE_TABLE_SQL)
        for line in _LEGACY_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            check_type = entry.get("lint_name", "unknown")
            page_path = entry.get("page_path", "")
            slug = Path(page_path).stem if page_path else "unknown"
            failures = entry.get("failures", [])
            evidence = failures[0] if failures else "unknown"
            fp = _fingerprint(check_type, slug, evidence)
            ts = entry.get("ts", datetime.now(UTC).isoformat())
            conn.execute(
                """INSERT OR IGNORE INTO lint_errors
                   (fingerprint, check_type, page_slug, evidence, payload, status, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
                (fp, check_type, slug, evidence, json.dumps(entry, ensure_ascii=False), ts, ts),
            )
            if conn.total_changes:
                count += 1
        conn.commit()
    if count > 0:
        _LEGACY_JSONL.rename(_LEGACY_JSONL.with_suffix(".jsonl.migrated"))
    return count


def _ensure_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(CREATE_TABLE_SQL)
    conn.commit()
    # One-shot migration
    migrated = _migrate_jsonl(path)
    return conn


def log_lint_failure(failure_dict: dict, db_path: Path | None = None) -> None:
    """Write a lint failure to the Error Book with dedup fingerprint.

    failure_dict keys: lint_name, page_path, failures, suggestion_excerpt, ts
    Same signature as the old JSONL log_lint_failure for drop-in compat.
    """
    conn = _ensure_db(db_path)
    check_type = failure_dict.get("lint_name", "unknown")
    page_path = failure_dict.get("page_path", "")
    slug = Path(page_path).stem if page_path else "unknown"
    failures = failure_dict.get("failures", [])
    evidence = failures[0] if failures else "unknown"
    fp = _fingerprint(check_type, slug, evidence)
    ts = failure_dict.get("ts", datetime.now(UTC).isoformat())
    existing = conn.execute(
        "SELECT id, seen_count FROM lint_errors WHERE fingerprint = ?", (fp,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE lint_errors SET last_seen = ?, seen_count = seen_count + 1 WHERE id = ?",
            (ts, existing[0]),
        )
    else:
        conn.execute(
            """INSERT INTO lint_errors
               (fingerprint, check_type, page_slug, evidence, payload, status, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
            (fp, check_type, slug, evidence,
             json.dumps(failure_dict, ensure_ascii=False, default=str), ts, ts),
        )
    conn.commit()
    conn.close()


def resolve_error(fingerprint: str, db_path: Path | None = None) -> bool:
    """Mark an error as resolved by fingerprint."""
    conn = _ensure_db(db_path)
    conn.execute("UPDATE lint_errors SET status = 'resolved' WHERE fingerprint = ?", (fingerprint,))
    changed = conn.total_changes > 0
    conn.commit()
    conn.close()
    return changed


def get_open_errors(db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return all open errors as dicts."""
    conn = _ensure_db(db_path)
    rows = conn.execute(
        "SELECT fingerprint, check_type, page_slug, evidence, first_seen, seen_count "
        "FROM lint_errors WHERE status = 'open' ORDER BY first_seen DESC"
    ).fetchall()
    conn.close()
    return [
        {"fingerprint": r[0], "check_type": r[1], "page_slug": r[2],
         "evidence": r[3], "first_seen": r[4], "seen_count": r[5]}
        for r in rows
    ]


def get_page_errors(slug: str, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return all errors for a specific wiki page slug."""
    conn = _ensure_db(db_path)
    rows = conn.execute(
        "SELECT fingerprint, check_type, evidence, status, first_seen, last_seen, seen_count "
        "FROM lint_errors WHERE page_slug = ? ORDER BY last_seen DESC", (slug,)
    ).fetchall()
    conn.close()
    return [
        {"fingerprint": r[0], "check_type": r[1], "evidence": r[2],
         "status": r[3], "first_seen": r[4], "last_seen": r[5], "seen_count": r[6]}
        for r in rows
    ]


def error_summary(db_path: Path | None = None) -> dict[str, Any]:
    """Return summary stats: counts by status and check_type."""
    conn = _ensure_db(db_path)
    by_status = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT status, COUNT(*) FROM lint_errors GROUP BY status"
        ).fetchall()
    }
    by_check = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT check_type, COUNT(*) FROM lint_errors GROUP BY check_type"
        ).fetchall()
    }
    total = conn.execute("SELECT COUNT(*) FROM lint_errors").fetchone()[0]
    conn.close()
    return {"total": total, "by_status": by_status, "by_check": by_check}
