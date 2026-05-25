"""
Unit tests for batch_scan_kol.py ret=200003 session-invalid detection (Track B1).

Pins exit-code behavior at the 30% threshold boundary:
  case 1:  0/54 invalid  → exits 0
  case 2: 16/54 (29.6%) invalid → exits 0 (under threshold)
  case 3: 17/54 (31.5%) invalid → exits 2 + stderr contains WECHAT_SESSION_INVALID: 17/54
  case 4: 54/54 (100%)  invalid → exits 2 + stderr contains WECHAT_SESSION_INVALID: 54/54
"""
import sqlite3
import sys
import types
import pytest

# kol_config is gitignored (runtime credentials) — inject a stub before import
_kol_stub = types.ModuleType("kol_config")
_kol_stub.TOKEN = "stub_token"
_kol_stub.COOKIE = "stub=cookie"
_kol_stub.FAKEIDS = {f"acct_{i:03d}": f"fakeid_{i:03d}" for i in range(54)}
sys.modules.setdefault("kol_config", _kol_stub)

import batch_scan_kol


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_in_memory_db_with_accounts(n: int = 54):
    """Return an in-memory SQLite connection pre-populated with n fake accounts."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            fakeid TEXT NOT NULL UNIQUE
        );
    """)
    for i in range(n):
        conn.execute(
            "INSERT INTO accounts (name, fakeid) VALUES (?, ?)",
            (f"acct_{i:03d}", f"fakeid_{i:03d}"),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helper: build a stub scan_account that returns session_invalid=True for the
# first `invalid_count` calls and ok for the rest.
# ---------------------------------------------------------------------------

def _make_scan_stub(invalid_count: int):
    call_count = {"n": 0}

    def stub(conn, name, fakeid, days_back, max_articles):
        call_count["n"] += 1
        if call_count["n"] <= invalid_count:
            return False, 0, 0, True   # session invalid
        return True, 0, 0, False       # ok

    return stub


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def _run_with_stubs(monkeypatch, invalid_of_54: int):
    """
    Patch batch_scan_kol internals so run() drives a 54-account in-memory DB
    with `invalid_of_54` accounts returning ret=200003.
    Returns (capsys, exception_or_none).
    """
    db_conn = _make_in_memory_db_with_accounts(54)

    monkeypatch.setattr(batch_scan_kol, "init_db", lambda path: db_conn)
    monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)
    monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(batch_scan_kol, "scan_account", _make_scan_stub(invalid_of_54))


@pytest.mark.parametrize("invalid_of_54,expected_exit", [
    (0, 0),    # case 1: 0% → exit 0
    (16, 0),   # case 2: 16/54 = 29.6% → exit 0 (below 30% threshold)
])
def test_no_exit_below_threshold(monkeypatch, invalid_of_54, expected_exit):
    """Cases 1 & 2: below threshold → run() completes without SystemExit(2)."""
    _run_with_stubs(monkeypatch, invalid_of_54)
    # Should not raise SystemExit at all (or raise with code != 2)
    try:
        batch_scan_kol.run(
            days_back=1,
            max_articles=1,
            account_filter=None,
            resume=False,
            daily=False,
            summary_json=False,
        )
    except SystemExit as exc:
        assert exc.code != 2, (
            f"Expected no SystemExit(2) for {invalid_of_54}/54 invalid "
            f"but got SystemExit({exc.code})"
        )


@pytest.mark.parametrize("invalid_of_54,label", [
    (17, "17/54"),   # case 3: 17/54 = 31.5% → exit 2
    (54, "54/54"),   # case 4: 54/54 = 100% → exit 2
])
def test_exit2_above_threshold(monkeypatch, capsys, invalid_of_54, label):
    """Cases 3 & 4: at/above threshold → SystemExit(2) + WECHAT_SESSION_INVALID on stderr."""
    _run_with_stubs(monkeypatch, invalid_of_54)

    with pytest.raises(SystemExit) as exc_info:
        batch_scan_kol.run(
            days_back=1,
            max_articles=1,
            account_filter=None,
            resume=False,
            daily=False,
            summary_json=False,
        )

    assert exc_info.value.code == 2, (
        f"Expected SystemExit(2) for {invalid_of_54}/54 invalid "
        f"but got SystemExit({exc_info.value.code})"
    )

    captured = capsys.readouterr()
    expected_marker = f"WECHAT_SESSION_INVALID: {label}"
    assert expected_marker in captured.err, (
        f"Expected '{expected_marker}' in stderr but got:\n{captured.err!r}"
    )
