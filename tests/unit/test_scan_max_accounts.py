"""Behavior-anchor tests for the --max-accounts staleness-partition path (quick 260626-jgp).

Three observable contracts:
  (a) staleness selection: given N accounts with varying scanned_at history,
      run(max_accounts=M) hands exactly M accounts to scan_account in staleness order
      (never-scanned NULL-first, then oldest-scanned, then name tiebreak).
  (b) default-path invariance: run(max_accounts=None) does NOT truncate; all seeded
      accounts are offered to scan_account (shuffle path, not staleness path).
  (c) argparse: --max-accounts 15 parses to int 15; absent parses to None; existing
      flags (--daily) still thread correctly.

These tests pin observable post-conditions (call-count + call-arg order against a real
in-process SQLite), NOT SQL string content. Avoids brittle impl-mirroring.
"""
from __future__ import annotations

import os
import sys

# Defuse import-time DEEPSEEK_API_KEY / GEMINI_API_KEY coupling BEFORE importing the module.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

import batch_scan_kol  # noqa: E402  (import after env seed is intentional)


# ---------------------------------------------------------------------------
# Shared harness helpers
# ---------------------------------------------------------------------------

def _seed_db(tmp_db, accounts_with_articles):
    """
    Seed a real SQLite at tmp_db with accounts + articles.

    accounts_with_articles: list of dicts:
      {
        "name": str,
        "fakeid": str,
        "articles": [{"scanned_at": "2026-06-01 00:00:00"}, ...]  # empty list = never-scanned
      }
    """
    conn = batch_scan_kol.init_db(tmp_db)
    for acc in accounts_with_articles:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (name, wechat_id, fakeid) VALUES (?, ?, ?)",
            (acc["name"], None, acc["fakeid"]),
        )
        account_row = conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (acc["name"],)
        ).fetchone()
        account_id = account_row[0]
        for art in acc.get("articles", []):
            conn.execute(
                "INSERT OR IGNORE INTO articles (account_id, title, url, scanned_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    account_id,
                    f"article-{acc['name']}-{art['scanned_at']}",
                    f"http://example.com/{acc['name']}/{art['scanned_at']}",
                    art["scanned_at"],
                ),
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Test (a): staleness selection — NULL-first, oldest-scanned, name tiebreak
# ---------------------------------------------------------------------------

def test_staleness_selection_null_first_then_oldest(monkeypatch, tmp_path) -> None:
    """run(max_accounts=3) must hand exactly the 3 staleest accounts to scan_account
    in staleness order: never-scanned accounts first (name-sorted among themselves),
    then oldest-scanned, not the recently-scanned ones."""
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    # 5 accounts, 2 never-scanned, 3 with articles of varying recency
    accounts_with_articles = [
        # Never scanned (no articles rows) — should be first two
        {"name": "Alpha",   "fakeid": "fid_alpha",   "articles": []},
        {"name": "Beta",    "fakeid": "fid_beta",    "articles": []},
        # Scanned: oldest first
        {"name": "Charlie", "fakeid": "fid_charlie", "articles": [{"scanned_at": "2026-06-01 00:00:00"}]},
        {"name": "Delta",   "fakeid": "fid_delta",   "articles": [{"scanned_at": "2026-06-15 00:00:00"}]},
        {"name": "Echo",    "fakeid": "fid_echo",    "articles": [{"scanned_at": "2026-06-25 00:00:00"}]},
    ]
    _seed_db(tmp_db, accounts_with_articles)

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    # scan_account returns (ok, new, skipped, session_invalid)
    m = mock.MagicMock(return_value=(True, 0, 0, False))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)

    # Patch sleep to avoid 5s delays
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    batch_scan_kol.run(
        days_back=120,
        max_articles=20,
        account_filter=None,
        resume=False,
        max_accounts=3,
    )

    # Exactly 3 accounts scanned
    assert m.call_count == 3, (
        f"Expected 3 accounts scanned, got {m.call_count}"
    )

    # Extract scanned names from call args: scan_account(conn, name, fakeid, days_back, max_articles)
    scanned_names = [c.args[1] for c in m.call_args_list]

    # The 2 never-scanned accounts (Alpha, Beta — name-sorted) + oldest-scanned Charlie
    assert scanned_names == ["Alpha", "Beta", "Charlie"], (
        f"Expected staleness-ordered ['Alpha', 'Beta', 'Charlie'], got {scanned_names}"
    )


# ---------------------------------------------------------------------------
# Test (b): default path — no truncation, all accounts offered
# ---------------------------------------------------------------------------

def test_default_path_no_truncation(monkeypatch, tmp_path) -> None:
    """run(max_accounts=None) must call scan_account for ALL seeded accounts.
    No staleness truncation. Shuffle is still invoked (we just freeze it to
    make call-count assertion stable)."""
    import unittest.mock as mock

    tmp_db = tmp_path / "kol_scan.db"

    accounts_with_articles = [
        {"name": "Alpha",   "fakeid": "fid_alpha",   "articles": []},
        {"name": "Beta",    "fakeid": "fid_beta",    "articles": [{"scanned_at": "2026-06-01 00:00:00"}]},
        {"name": "Charlie", "fakeid": "fid_charlie", "articles": [{"scanned_at": "2026-06-15 00:00:00"}]},
        {"name": "Delta",   "fakeid": "fid_delta",   "articles": [{"scanned_at": "2026-06-25 00:00:00"}]},
        {"name": "Echo",    "fakeid": "fid_echo",    "articles": [{"scanned_at": "2026-06-20 00:00:00"}]},
        {"name": "Foxtrot", "fakeid": "fid_foxtrot", "articles": []},
    ]
    _seed_db(tmp_db, accounts_with_articles)

    monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)

    # Freeze shuffle so order is deterministic (but the shuffle CODE PATH still executes)
    monkeypatch.setattr(batch_scan_kol.random, "shuffle", lambda x: None)

    m = mock.MagicMock(return_value=(True, 0, 0, False))
    monkeypatch.setattr(batch_scan_kol, "scan_account", m)

    # Patch sleep to avoid 5s delays
    monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)

    batch_scan_kol.run(
        days_back=120,
        max_articles=20,
        account_filter=None,
        resume=False,
        max_accounts=None,  # DEFAULT — no truncation
    )

    assert m.call_count == len(accounts_with_articles), (
        f"Default path must scan ALL {len(accounts_with_articles)} accounts; "
        f"got {m.call_count}"
    )


# ---------------------------------------------------------------------------
# Test (c): argparse — --max-accounts parses correctly
# ---------------------------------------------------------------------------

def _run_main_with(monkeypatch, argv: list[str]):
    """Drive main() with a fake CLI, run() mocked.
    Returns the mock for assertion on call-count / call-args.

    Note: batch_scan_kol.main() does NOT guard on DB_PATH.exists() (no sys.exit guard
    like batch_classify_kol has), so no DB_PATH patching needed — run() is mocked out
    before any DB access happens.
    """
    import unittest.mock as mock

    mock_run = mock.MagicMock()
    monkeypatch.setattr(batch_scan_kol, "run", mock_run)
    monkeypatch.setattr(sys, "argv", ["batch_scan_kol.py", *argv])
    batch_scan_kol.main()
    return mock_run


def test_argparse_max_accounts_int(monkeypatch) -> None:
    """--max-accounts 15 must thread to run(max_accounts=15)."""
    mock_run = _run_main_with(monkeypatch, ["--daily", "--max-accounts", "15"])
    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["max_accounts"] == 15, (
        f"Expected max_accounts=15, got {mock_run.call_args.kwargs.get('max_accounts')!r}"
    )
    # Backward compat: --daily also threads
    assert mock_run.call_args.kwargs["daily"] is True


def test_argparse_max_accounts_absent_is_none(monkeypatch) -> None:
    """Absent --max-accounts must default to None (preserves current behavior)."""
    mock_run = _run_main_with(monkeypatch, ["--daily"])
    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["max_accounts"] is None, (
        f"Expected max_accounts=None when flag absent, "
        f"got {mock_run.call_args.kwargs.get('max_accounts')!r}"
    )
