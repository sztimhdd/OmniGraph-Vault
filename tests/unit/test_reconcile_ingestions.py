"""Quick 260510-k5q (RCN-03): tests for scripts/reconcile_ingestions.py.

Mock-only: no real LightRAG, no real ingest DB. Each test uses tmp_path
for both the sqlite DB AND the kv_store_doc_status.json.

doc_id formula MUST byte-match ``f"wechat_{md5(url).hexdigest()[:10]}"``
mirroring ``ingest_wechat.py:943,983`` — anything else creates a silent
reconciliation gap.

RSS rows are silently skipped (deferred to ar-1).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest


# DEEPSEEK_API_KEY=dummy already set in tests/conftest.py session-wide
# (Phase 5 cross-coupling FLAG 2). Autouse fixture reasserts for safety.
@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


@pytest.fixture
def reconcile_main():
    """Import the script's ``main`` entry point lazily."""
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(repo_root / "scripts") not in sys.path:
        sys.path.insert(0, str(repo_root / "scripts"))
    from reconcile_ingestions import main  # type: ignore
    return main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_doc_id(url: str) -> str:
    """Mirror ingest_wechat.py:943,983 byte-for-byte."""
    return f"wechat_{hashlib.md5(url.encode()).hexdigest()[:10]}"


def _seed_ingestions_db(db_path: Path, rows: list[dict]) -> None:
    """Seed minimal production-shape schema: ingestions JOIN articles by article_id.

    Production (mig 008) carries ``url`` on ``articles``, NOT ``ingestions``;
    the script JOINs to recover URL. Mirror that here so tests exercise the
    same SELECT path.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ingestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                source TEXT,
                status TEXT,
                ingested_at TEXT
            )
            """
        )
        for row in rows:
            # Insert article row keyed by article_id; if multiple ingestions
            # share article_id (legitimate retry), the article row is created
            # once via INSERT OR IGNORE.
            conn.execute(
                "INSERT OR IGNORE INTO articles (id, url) VALUES (?, ?)",
                (row["article_id"], row["url"]),
            )
            conn.execute(
                "INSERT INTO ingestions "
                "(article_id, source, status, ingested_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    row["article_id"],
                    row["source"],
                    row["status"],
                    row["ingested_at"],
                ),
            )
        conn.commit()


def _write_doc_status(storage_dir: Path, mapping: dict) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "kv_store_doc_status.json").write_text(
        json.dumps(mapping), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Test 1 — happy path: zero mystery → exit 0; RSS row silently skipped
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_zero_mystery_returns_exit_zero(tmp_path, capsys, reconcile_main):
    db = tmp_path / "kol_scan.db"
    storage = tmp_path / "lightrag_storage"
    url = "https://mp.weixin.qq.com/s/abc"
    doc_id = _expected_doc_id(url)

    _seed_ingestions_db(
        db,
        [
            {
                "article_id": 1,
                "url": url,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-10T09:00:00",
            },
            # RSS row should be silently skipped (deferred to ar-1)
            {
                "article_id": 2,
                "url": "https://example.com/rss/1",
                "source": "rss",
                "status": "ok",
                "ingested_at": "2026-05-10T09:01:00",
            },
        ],
    )
    _write_doc_status(storage, {doc_id: {"status": "processed"}})

    exit_code = reconcile_main([
        "--date", "2026-05-10",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    assert exit_code == 0

    out = capsys.readouterr().out
    # No JSON line emitted (only summary line)
    json_lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert json_lines == []
    assert "0 mystery" in out


# ---------------------------------------------------------------------------
# Test 2 — doc_status missing entirely → mystery, exit 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_doc_status_missing_is_mystery(tmp_path, capsys, reconcile_main):
    db = tmp_path / "kol_scan.db"
    storage = tmp_path / "lightrag_storage"
    url = "https://mp.weixin.qq.com/s/missing"
    doc_id = _expected_doc_id(url)

    _seed_ingestions_db(
        db,
        [
            {
                "article_id": 42,
                "url": url,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-10T09:00:00",
            }
        ],
    )
    _write_doc_status(storage, {})  # empty — doc_id not present

    exit_code = reconcile_main([
        "--date", "2026-05-10",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    assert exit_code == 1

    out = capsys.readouterr().out
    json_lines = [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]
    assert len(json_lines) == 1
    payload = json_lines[0]
    assert payload["actual_status"] == "missing"
    assert payload["doc_id"] == doc_id
    assert payload["art_id"] == 42


# ---------------------------------------------------------------------------
# Test 3 — doc_status='processing' (h09 race shape) → mystery, exit 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_doc_status_processing_is_mystery(tmp_path, capsys, reconcile_main):
    db = tmp_path / "kol_scan.db"
    storage = tmp_path / "lightrag_storage"
    url = "https://mp.weixin.qq.com/s/processing"
    doc_id = _expected_doc_id(url)

    _seed_ingestions_db(
        db,
        [
            {
                "article_id": 7,
                "url": url,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-10T09:00:00",
            }
        ],
    )
    _write_doc_status(storage, {doc_id: {"status": "processing"}})

    exit_code = reconcile_main([
        "--date", "2026-05-10",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    assert exit_code == 1

    out = capsys.readouterr().out
    json_lines = [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]
    assert len(json_lines) == 1
    assert json_lines[0]["actual_status"] == "processing"


# ---------------------------------------------------------------------------
# Test 4 — exit-codes parametrized: 0 → exit 0, ≥1 → exit 1
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("mystery_count,expected_exit", [(0, 0), (1, 1), (5, 1)])
def test_exit_codes_parametrized(
    tmp_path, capsys, reconcile_main, mystery_count, expected_exit
):
    db = tmp_path / f"kol_scan_{mystery_count}.db"
    storage = tmp_path / f"storage_{mystery_count}"

    rows = []
    status_map = {}
    for i in range(max(mystery_count, 1)):
        url = f"https://mp.weixin.qq.com/s/p4-{mystery_count}-{i}"
        doc_id = _expected_doc_id(url)
        rows.append(
            {
                "article_id": 100 + i,
                "url": url,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-10T09:00:00",
            }
        )
        if mystery_count == 0:
            # Healthy day: every row matched → no mystery
            status_map[doc_id] = {"status": "processed"}
        elif i < mystery_count:
            # Leave OUT of status_map → counts as missing/mystery
            pass
        else:
            status_map[doc_id] = {"status": "processed"}

    _seed_ingestions_db(db, rows)
    _write_doc_status(storage, status_map)

    exit_code = reconcile_main([
        "--date", "2026-05-10",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    assert exit_code == expected_exit

    out = capsys.readouterr().out
    json_lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert len(json_lines) == mystery_count


# ---------------------------------------------------------------------------
# Test 5 — --date filters to arbitrary historical date
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_date_flag_filters_to_arbitrary_historical_date(
    tmp_path, capsys, reconcile_main
):
    db = tmp_path / "kol_scan.db"
    storage = tmp_path / "lightrag_storage"

    url_old = "https://mp.weixin.qq.com/s/old"
    url_new = "https://mp.weixin.qq.com/s/new"
    doc_old = _expected_doc_id(url_old)
    # doc_new not declared in status_map → would be mystery if examined.

    _seed_ingestions_db(
        db,
        [
            {
                "article_id": 1,
                "url": url_old,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-08T09:00:00",
            },
            {
                "article_id": 2,
                "url": url_new,
                "source": "wechat",
                "status": "ok",
                "ingested_at": "2026-05-10T09:00:00",
            },
        ],
    )
    # Old article processed; new article would be mystery if window included it
    _write_doc_status(storage, {doc_old: {"status": "processed"}})

    exit_code = reconcile_main([
        "--date", "2026-05-08",
        "--lookback-days", "1",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    # Window = [2026-05-08, 2026-05-08] (lookback-days=1 means single day)
    # Only the old row is examined → it's processed → exit 0
    assert exit_code == 0

    out = capsys.readouterr().out
    json_lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert json_lines == []


# ---------------------------------------------------------------------------
# Test 6 — --lookback-days extends window
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lookback_days_extends_window(tmp_path, capsys, reconcile_main):
    db = tmp_path / "kol_scan.db"
    storage = tmp_path / "lightrag_storage"

    rows = [
        {
            "article_id": 1,
            "url": "https://mp.weixin.qq.com/s/05-07",
            "source": "wechat",
            "status": "ok",
            "ingested_at": "2026-05-07T09:00:00",
        },
        {
            "article_id": 2,
            "url": "https://mp.weixin.qq.com/s/05-08",
            "source": "wechat",
            "status": "ok",
            "ingested_at": "2026-05-08T09:00:00",
        },
        {
            "article_id": 3,
            "url": "https://mp.weixin.qq.com/s/05-10",
            "source": "wechat",
            "status": "ok",
            "ingested_at": "2026-05-10T09:00:00",
        },
    ]
    _seed_ingestions_db(db, rows)
    # All three rows missing from status_map → all 3 are mystery
    _write_doc_status(storage, {})

    exit_code = reconcile_main([
        "--date", "2026-05-10",
        "--lookback-days", "4",
        "--db-path", str(db),
        "--storage-dir", str(storage),
    ])
    # Window = [2026-05-07, 2026-05-10] inclusive (4 days)
    assert exit_code == 1

    out = capsys.readouterr().out
    json_lines = [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]
    assert len(json_lines) == 3
    art_ids = {ln["art_id"] for ln in json_lines}
    assert art_ids == {1, 2, 3}
