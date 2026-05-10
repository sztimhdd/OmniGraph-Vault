"""Unit tests for enrichment.daily_digest — Layer 2 gate + UNION ALL + Markdown shape + atomic archive.

v3.5 schema (2026-05-09): KOL + RSS branches both gate on layer2_verdict = 'ok'.
classifications/rss_classifications tables are stale; rss_classify.py deleted.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from enrichment import daily_digest as dd


def _seed(db: Path, today: str, *, kol_ok: int = 0, rss_ok: int = 0,
          kol_total: int = 0, rss_total: int = 0) -> None:
    """Seed articles + rss_articles with layer2_verdict = 'ok' for qualified rows.

    kol_ok/rss_ok: count of articles with layer2='ok' (deep, appear in digest).
    kol_total/rss_total: total article count including rejected/uncategorized.
    kol_total must be >= kol_ok, rss_total >= rss_ok.
    """
    import batch_scan_kol  # noqa: F401 -- triggers full schema create
    conn = batch_scan_kol.init_db(db)

    # Apply migrations that add Layer 2 columns (not in base schema)
    for col, col_type in [
        ("layer2_verdict", "TEXT"),
        ("layer2_reason", "TEXT"),
        ("layer2_at", "TEXT"),
        ("layer2_prompt_version", "TEXT"),
        ("layer1_verdict", "TEXT"),
        ("layer1_reason", "TEXT"),
        ("layer1_at", "TEXT"),
        ("layer1_prompt_version", "TEXT"),
    ]:
        for table in ("articles", "rss_articles"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already exists

    # KOL account
    conn.execute(
        "INSERT INTO accounts (name, fakeid) VALUES (?, ?)",
        ("TestKOL", "kol-fake-1"),
    )
    acct_id = conn.execute("SELECT id FROM accounts WHERE name = 'TestKOL'").fetchone()[0]

    # RSS feed
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
        ("Feed A", "https://a.example/rss"),
    )
    feed_id = conn.execute("SELECT id FROM rss_feeds WHERE name='Feed A'").fetchone()[0]

    for i in range(kol_total):
        is_ok = i < kol_ok
        conn.execute(
            "INSERT INTO articles (account_id, title, url, digest, scanned_at,"
            " layer2_verdict, layer2_reason, layer2_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (acct_id, f"KOL Title {i}", f"https://mp.weixin.qq.com/s/kol{i}",
             f"KOL digest body {i} " * (30 + i), f"{today} 10:00:00",
             'ok' if is_ok else 'reject',
             f"kol reason {i}", f"{today} 10:{i:02d}:00"),
        )
    for i in range(rss_total):
        is_ok = i < rss_ok
        conn.execute(
            "INSERT INTO rss_articles (feed_id, title, url, summary, fetched_at,"
            " content_length, layer2_verdict, layer2_reason, layer2_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (feed_id, f"RSS Title {i}", f"https://a.example/p/rss{i}",
             f"RSS summary body {i} " * (25 + i), f"{today} 11:00:00",
             500 + i * 10,
             'ok' if is_ok else 'reject',
             f"rss reason {i}", f"{today} 11:{i:02d}:00"),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def today() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------
# Test 1 -- 7 candidates -> gather top_n=5, sorted by content_length DESC
# ---------------------------------------------------------------------
def test_top_n_sorting(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=4, rss_ok=3, kol_total=4, rss_total=3)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    assert len(candidates) == 5
    # Sort invariant: content_length DESC first
    lengths = [c["content_length"] for c in candidates]
    assert lengths == sorted(lengths, reverse=True)
    assert stats["kol_total"] == 4
    assert stats["rss_total"] == 3
    assert stats["deep_total"] == 7


# ---------------------------------------------------------------------
# Test 2 -- render Markdown contains topic, source label, link, excerpt
# ---------------------------------------------------------------------
def test_render_markdown_shape(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=1, kol_total=1, rss_total=1)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    md = dd.render(today, candidates, stats)
    assert "[[KOL]]" in md
    assert "[[RSS]]" in md
    assert "WeChat" in md or "RSS" in md
    assert "阅读原文" in md
    assert "http" in md


# ---------------------------------------------------------------------
# Test 3 -- empty candidate pool: no Telegram + no archive
# ---------------------------------------------------------------------
def test_empty_state_skips_telegram_and_archive(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=0, rss_ok=0, kol_total=0, rss_total=0)
    with patch.object(dd, "deliver_telegram") as mock_tg, \
         patch.object(dd, "archive") as mock_arch:
        rc = dd.run(
            today, dry_run=False, db_path=db, digest_dir=tmp_path / "digests"
        )
    assert rc == 0
    mock_tg.assert_not_called()
    mock_arch.assert_not_called()


# ---------------------------------------------------------------------
# Test 4 -- dry-run: print Markdown, no Telegram, no archive
# ---------------------------------------------------------------------
def test_dry_run_no_network_no_write(tmp_path: Path, today: str, capsys) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=1, kol_total=1, rss_total=1)
    with patch.object(dd, "deliver_telegram") as mock_tg, \
         patch.object(dd, "archive") as mock_arch:
        dd.run(today, dry_run=True, db_path=db, digest_dir=tmp_path / "d")
    mock_tg.assert_not_called()
    mock_arch.assert_not_called()
    out = capsys.readouterr().out
    assert today in out
    assert "OmniGraph-Vault" in out


# ---------------------------------------------------------------------
# Test 5 -- archive uses atomic tmp-then-rename via os.replace
# ---------------------------------------------------------------------
def test_archive_uses_os_replace(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=0, kol_total=1, rss_total=0)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    md = dd.render(today, candidates, stats)
    calls: list[tuple[str, str]] = []

    def fake_replace(src, dst):
        calls.append((str(src), str(dst)))
        os.rename(src, dst)

    with patch.object(dd.os, "replace", side_effect=fake_replace):
        path = dd.archive(today, md, digest_dir=tmp_path / "digests")
    assert path.exists()
    assert calls, "os.replace must be called"
    src, dst = calls[0]
    assert src.endswith(".tmp")
    assert dst.endswith(".md")


# ---------------------------------------------------------------------
# Test 6 -- archive path under omonigraph-vault
# ---------------------------------------------------------------------
def test_archive_path_preserves_typo(tmp_path: Path, today: str, monkeypatch) -> None:
    fake_base = tmp_path / "omonigraph-vault"
    monkeypatch.setattr(dd, "BASE_DIR", fake_base)
    monkeypatch.setattr(dd, "DIGEST_DIR", fake_base / "digests")
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=0, kol_total=1, rss_total=0)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    md = dd.render(today, candidates, stats)
    path = dd.archive(today, md)
    assert "omonigraph-vault" in str(path)
    assert path.name == f"{today}.md"


# ---------------------------------------------------------------------
# Test 7 -- Layer 2 gate: only layer2='ok' appears, rejects excluded
# ---------------------------------------------------------------------
def test_layer2_gate_filters_rejects(tmp_path: Path, today: str) -> None:
    """KOL + RSS rows with layer2='reject' MUST NOT appear in candidates."""
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=1, kol_total=3, rss_total=3)
    candidates, _ = dd.gather(today, top_n=10, db_path=db)
    # Only the 2 'ok' articles should appear
    assert len(candidates) == 2
    srcs = {c["src"] for c in candidates}
    assert srcs == {"kol", "rss"}


# ---------------------------------------------------------------------
# Test 8 -- KOL + RSS both appear when both have layer2='ok'
# ---------------------------------------------------------------------
def test_mixed_layer2_both_appear(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=2, rss_ok=2, kol_total=2, rss_total=2)
    candidates, _ = dd.gather(today, top_n=10, db_path=db)
    srcs = {c["src"] for c in candidates}
    assert "kol" in srcs and "rss" in srcs
    assert len(candidates) == 4


# ---------------------------------------------------------------------
# Test 9 -- delivery returns False on missing Telegram creds, run() rc=1
# ---------------------------------------------------------------------
def test_missing_telegram_creds_returns_rc1(
    tmp_path: Path, today: str, monkeypatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    db = tmp_path / "t.db"
    _seed(db, today, kol_ok=1, rss_ok=0, kol_total=1, rss_total=0)
    rc = dd.run(
        today,
        dry_run=False,
        db_path=db,
        digest_dir=tmp_path / "digests",
    )
    assert rc == 1
    assert (tmp_path / "digests" / f"{today}.md").exists()
