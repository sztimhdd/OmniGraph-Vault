"""Coverage uses account identities and the approved per-run request ceiling."""
import json
import sqlite3
from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest


def seed(tmp_path):
    db = tmp_path / "scan.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,wechat_id TEXT,last_scanned_at TEXT,last_attempted_at TEXT)")
        c.executemany("INSERT INTO accounts VALUES (?,?,?,NULL,NULL)", [(i, f"synthetic-{i}", "") for i in range(1, 5)])
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"schema_version": 1, "account_ids": [1, 2, 3]}))
    return db, targets


def test_zero_history_and_failed_attempts_rotate_without_false_success(tmp_path, monkeypatch):
    from scripts import dajiala_kol_scan as scan
    db, targets = seed(tmp_path)
    calls = []
    def fake(key, conn, name, **kwargs):
        calls.append(name)
        return {"code": 1, "error": "failed"} if name.endswith('-1') else {"code": 0, "new": 0, "found": 0, "history_end": True}
    monkeypatch.setattr(scan, "scan_account_pro", fake)
    first = scan.run_coverage(str(db), str(targets), "synthetic", max_accounts=2, sleep_seconds=0)
    assert first["attempted"] == 2 and first["failed"] == 1
    second = scan.select_coverage_accounts(str(db), str(targets), max_accounts=1)
    assert second[0]["id"] == 3
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT last_scanned_at FROM accounts WHERE id=1").fetchone()[0] is None
        assert c.execute("SELECT last_attempted_at FROM accounts WHERE id=1").fetchone()[0] is not None
        assert c.execute("SELECT last_scanned_at FROM accounts WHERE id=2").fetchone()[0] is not None
    before = db.read_bytes()
    result = scan.run_coverage(str(db), str(targets), "", dry_run=True, max_accounts=2)
    assert result["attempted"] == 0 and len(calls) == 2 and db.read_bytes() == before
    assert "synthetic-" not in json.dumps(result)
    for kwargs in ({"pages": 3}, {"max_accounts": 21}):
        with pytest.raises(ValueError):
            scan.run_coverage(str(db), str(targets), "", **kwargs)


def test_target_schema_is_explicit_and_all_target_ids_have_a_turn(tmp_path, monkeypatch):
    from scripts import dajiala_kol_scan as scan
    db, targets = seed(tmp_path)
    monkeypatch.setattr(scan, "scan_account_pro", lambda *a, **k: {"code": 0, "found": 0, "new": 0, "history_end": True})
    observed = []
    for _ in range(3):
        result = scan.run_coverage(str(db), str(targets), "synthetic", max_accounts=1, sleep_seconds=0)
        observed.extend(x["account_id"] for x in result["results"])
    assert observed == [1, 2, 3]
    targets.write_text(json.dumps({"schema_version": 1, "account_ids": [1, 99]}))
    with pytest.raises(ValueError):
        scan.select_coverage_accounts(str(db), str(targets))


def test_real_scan_path_stops_after_three_rate_limits(tmp_path, monkeypatch):
    from scripts import dajiala_kol_scan as scan
    db, targets = seed(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO accounts VALUES(5,'synthetic-5','',NULL,NULL)")
    targets.write_text(json.dumps({'schema_version': 1, 'account_ids': [1,2,3,4,5]}))
    calls = []
    def limited(*args, **kwargs):
        calls.append(1)
        raise HTTPError('https://synthetic.invalid', 429, 'rate limit', {}, None)
    monkeypatch.setattr(scan, 'fetch_by_ghid', limited)
    result = scan.run_coverage(str(db), str(targets), 'synthetic', sleep_seconds=0)
    assert len(calls) == result['attempted'] == 3
    assert result['stopped'] == 'rate_limited' and result['unattempted'] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM accounts WHERE last_attempted_at IS NULL').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM accounts WHERE last_scanned_at IS NOT NULL').fetchone()[0] == 0


def test_coverage_gap_uses_aware_times_and_unknown_legacy_timezone(tmp_path, monkeypatch):
    from scripts import dajiala_kol_scan as scan
    db, targets = seed(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE accounts SET last_scanned_at='2026-10-02T12:00:00+00:00' WHERE id=1")
        conn.execute("UPDATE accounts SET last_scanned_at='2026-10-02 12:00:00' WHERE id=2")
    oldest = int(datetime(2026,10,2,10,tzinfo=UTC).timestamp())
    monkeypatch.setattr(scan, 'scan_account_pro', lambda *a, **k: {'code':0, 'new':0, 'found':1, 'oldest_send_time': oldest})
    result = scan.run_coverage(str(db), str(targets), 'synthetic', max_accounts=2, sleep_seconds=0)
    assert [x['coverage_gap'] for x in result['results']] == [False, 'unknown']
    with sqlite3.connect(db) as conn:
        assert all(datetime.fromisoformat(x[0]).tzinfo is not None for x in conn.execute('SELECT last_scanned_at FROM accounts WHERE id IN(1,2)'))
