"""Behavior-anchor tests for the last_scanned_at stamp + staleness ordering (quick 260629-gvl).

Four observable contracts:
  (a) stamp_on_success_even_zero_articles: a successful scan (ok=True, 0 articles) still
      stamps accounts.last_scanned_at.
  (b) no_stamp_on_failure: a cookie-dead failure (ok=False, session_invalid=True) must NOT
      stamp last_scanned_at — failed attempts must not falsely rotate accounts to the back.
  (c) staleness_orders_by_last_scanned_at: the staleness SELECT orders by last_scanned_at
      (NULL-first, then oldest-attempted, then name) — not by article recency.
  (d) just_scanned_rotates_to_back: an account with a very recent last_scanned_at is skipped
      in favor of older-stamped accounts when max_accounts truncates the queue.

Mirrors the test_scan_max_accounts.py harness pattern exactly:
  - env seed before import
  - real schema via batch_scan_kol.init_db()
  - monkeypatch DB_PATH / load_env / init_accounts / scan_account / time.sleep
  - selection order pinned via c.args[1] from call_args_list
"""
from __future__ import annotations

import os
import sqlite3
import sys

# Defuse import-time DEEPSEEK_API_KEY / GEMINI_API_KEY coupling BEFORE importing the module.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

import batch_scan_kol  # noqa: E402  (import after env seed is intentional)


# ---------------------------------------------------------------------------
# Shared harness helpers
# ---------------------------------------------------------------------------

def _seed_db_accounts(tmp_db, accounts):
    """
    Seed a real SQLite at tmp_db with accounts only (no articles).

    accounts: list of dicts:
      {
        "name": str,
        "fakeid": str,
        "last_scanned_at": str | None   # optional; if absent → NULL
      }
    """
    conn = batch_scan_kol.init_db(tmp_db)
    for acc in accounts:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (name, wechat_id, fakeid) VALUES (?, ?, ?)",
            (acc["name"], None, acc["fakeid"]),
        )
        # Set last_scanned_at if provided
        if acc.get("last_scanned_at") is not None:
            conn.execute(
                "UPDATE accounts SET last_scanned_at = ? WHERE name = ?",
                (acc["last_scanned_at"], acc["name"]),
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Test (a): stamp on success — even when 0 articles returned
# ---------------------------------------------------------------------------

def test_stamp_on_success_even_zero_articles(monkeypatch, tmp_path) -> None:
    """run(max_accounts=3) with scan_account→(True,0,0,False) must stamp last_scanned_at
    for ALL 3 accounts. Core fix: a 0-article success still marks the account as attempted."""
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    # Seed 3 accounts, no last_scanned_at set (all NULL)
    _seed_db_accounts(tmp_db, [
        {"name": "Alpha", "fakeid": "fid_alpha"},
        {"name": "Beta",  "fakeid": "fid_beta"},
        {"name": "Gamma", "fakeid": "fid_gamma"},
    ])

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    # Always return success with 0 articles
    m = mock.MagicMock(return_value=(True, 0, 0, False))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    batch_scan_kol.run(
        days_back=120,
        max_articles=20,
        account_filter=None,
        resume=False,
        max_accounts=3,
    )

    # Open a fresh connection (independent of run()'s closed conn) to verify stamps
    conn2 = sqlite3.connect(str(tmp_db))
    rows = conn2.execute(
        "SELECT name, last_scanned_at FROM accounts ORDER BY name"
    ).fetchall()
    conn2.close()

    names_with_null = [name for name, ts in rows if ts is None]
    assert names_with_null == [], (
        f"Expected all accounts stamped but these still have NULL last_scanned_at: "
        f"{names_with_null}"
    )
    assert len(rows) == 3, f"Expected 3 accounts, got {len(rows)}"


# ---------------------------------------------------------------------------
# Test (b): no stamp on failure (cookie-dead)
# ---------------------------------------------------------------------------

def test_no_stamp_on_failure(monkeypatch, tmp_path) -> None:
    """When scan_account returns (False, 0, 0, True) (cookie-dead) for ALL accounts,
    the SESSION_INVALID_THRESHOLD triggers sys.exit(2). After catching that exit,
    last_scanned_at must remain NULL for all accounts — a failed attempt must not
    falsely rotate accounts to the back of the staleness queue."""
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    _seed_db_accounts(tmp_db, [
        {"name": "Alpha", "fakeid": "fid_alpha"},
        {"name": "Beta",  "fakeid": "fid_beta"},
        {"name": "Gamma", "fakeid": "fid_gamma"},
    ])

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    # All failures: cookie-dead (session_invalid=True)
    m = mock.MagicMock(return_value=(False, 0, 0, True))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    import pytest
    # 3/3 cookie-dead = 100% > SESSION_INVALID_THRESHOLD (30%) → sys.exit(2)
    with pytest.raises(SystemExit) as exc_info:
        batch_scan_kol.run(
            days_back=120,
            max_articles=20,
            account_filter=None,
            resume=False,
            max_accounts=3,
        )
    assert exc_info.value.code == 2, f"Expected exit(2), got exit({exc_info.value.code})"

    # Verify no stamps were written
    conn2 = sqlite3.connect(str(tmp_db))
    rows = conn2.execute(
        "SELECT name, last_scanned_at FROM accounts ORDER BY name"
    ).fetchall()
    conn2.close()

    names_with_stamp = [name for name, ts in rows if ts is not None]
    assert names_with_stamp == [], (
        f"Expected all last_scanned_at to be NULL after all-failure run, "
        f"but these have stamps: {names_with_stamp}"
    )


# ---------------------------------------------------------------------------
# Test (c): staleness SELECT orders by last_scanned_at, not article recency
# ---------------------------------------------------------------------------

def test_staleness_orders_by_last_scanned_at(monkeypatch, tmp_path) -> None:
    """The staleness SELECT must order by accounts.last_scanned_at (NULL-first, then
    oldest attempted, then name) — NOT by article scanned_at.

    Seed 4 accounts:
      - NullAccount: last_scanned_at = NULL (never attempted)
      - OldStamped:  last_scanned_at = '2026-06-01 00:00:00' (oldest)
      - MidStamped:  last_scanned_at = '2026-06-15 00:00:00'
      - NewStamped:  last_scanned_at = '2026-06-25 00:00:00' (most recent)

    run(max_accounts=2) must hand [NullAccount, OldStamped] to scan_account in that order.
    """
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    _seed_db_accounts(tmp_db, [
        {"name": "NullAccount", "fakeid": "fid_null",  "last_scanned_at": None},
        {"name": "OldStamped",  "fakeid": "fid_old",   "last_scanned_at": "2026-06-01 00:00:00"},
        {"name": "MidStamped",  "fakeid": "fid_mid",   "last_scanned_at": "2026-06-15 00:00:00"},
        {"name": "NewStamped",  "fakeid": "fid_new",   "last_scanned_at": "2026-06-25 00:00:00"},
    ])

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    m = mock.MagicMock(return_value=(True, 0, 0, False))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    batch_scan_kol.run(
        days_back=120,
        max_articles=20,
        account_filter=None,
        resume=False,
        max_accounts=2,
    )

    assert m.call_count == 2, f"Expected 2 accounts scanned, got {m.call_count}"

    scanned_names = [c.args[1] for c in m.call_args_list]
    assert scanned_names == ["NullAccount", "OldStamped"], (
        f"Expected ['NullAccount', 'OldStamped'] (NULL-first, then oldest-stamped), "
        f"got {scanned_names}"
    )


# ---------------------------------------------------------------------------
# Test (d): just-scanned account rotates to the back
# ---------------------------------------------------------------------------

def test_just_scanned_rotates_to_back(monkeypatch, tmp_path) -> None:
    """An account with a very recent last_scanned_at must NOT be selected when
    max_accounts truncates the queue — it sorts to the back, letting older accounts go first.

    Seed 3 accounts:
      - VeryRecent: last_scanned_at = '2026-06-29 12:00:00' (just scanned)
      - OlderA:     last_scanned_at = '2026-06-01 00:00:00'
      - OlderB:     last_scanned_at = '2026-06-10 00:00:00'

    run(max_accounts=2) must scan OlderA and OlderB; VeryRecent must NOT be scanned.
    """
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    _seed_db_accounts(tmp_db, [
        {"name": "VeryRecent", "fakeid": "fid_vr",     "last_scanned_at": "2026-06-29 12:00:00"},
        {"name": "OlderA",     "fakeid": "fid_oldera", "last_scanned_at": "2026-06-01 00:00:00"},
        {"name": "OlderB",     "fakeid": "fid_olderb", "last_scanned_at": "2026-06-10 00:00:00"},
    ])

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    m = mock.MagicMock(return_value=(True, 0, 0, False))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    batch_scan_kol.run(
        days_back=120,
        max_articles=20,
        account_filter=None,
        resume=False,
        max_accounts=2,
    )

    assert m.call_count == 2, f"Expected 2 accounts scanned, got {m.call_count}"

    scanned_names = [c.args[1] for c in m.call_args_list]
    assert "VeryRecent" not in scanned_names, (
        f"VeryRecent (just-scanned) should have rotated to the back; "
        f"got scanned_names={scanned_names}"
    )
    assert set(scanned_names) == {"OlderA", "OlderB"}, (
        f"Expected {{OlderA, OlderB}} to be scanned, got {scanned_names}"
    )
