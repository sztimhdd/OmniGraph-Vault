"""Unit tests for enrichment.daily_digest — asymmetric UNION + Markdown shape + atomic archive."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from enrichment import daily_digest as dd


def _seed(db: Path, today: str, *, kol_rows: int = 0, rss_rows: int = 0,
          kol_enriched: int = 2, rss_enriched: int = 0) -> None:
    """Seed articles + classifications + rss_* schemas and rows for a given date.

    Uses ALTER TABLE to backfill scanned_at on KOL rows so tests can pin the
    date deterministically.
    """
    import batch_scan_kol  # noqa: F401 — triggers full schema create
    conn = batch_scan_kol.init_db(db)
    conn.execute(
        "INSERT INTO accounts (name, fakeid) VALUES (?, ?)",
        ("TestKOL", "kol-fake-1"),
    )
    acct_id = conn.execute("SELECT id FROM accounts WHERE name = 'TestKOL'").fetchone()[0]
    # Seed RSS feed
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
        ("Feed A", "https://a.example/rss"),
    )
    feed_id = conn.execute("SELECT id FROM rss_feeds WHERE name='Feed A'").fetchone()[0]

    for i in range(kol_rows):
        conn.execute(
            "INSERT INTO articles (account_id, title, url, digest, scanned_at, enriched) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (acct_id, f"KOL Title {i}", f"https://mp.weixin.qq.com/s/kol{i}",
             f"KOL digest body {i} " * (30 + i), f"{today} 10:00:00", kol_enriched),
        )
        conn.execute(
            "INSERT INTO classifications (article_id, topic, depth_score, relevant, excluded, reason) "
            "VALUES (?, ?, ?, 1, 0, ?)",
            (conn.execute("SELECT id FROM articles WHERE url = ?",
                          (f"https://mp.weixin.qq.com/s/kol{i}",)).fetchone()[0],
             "Agent", 3 if i % 2 == 0 else 2, "kol reason"),
        )
    for i in range(rss_rows):
        conn.execute(
            "INSERT INTO rss_articles (feed_id, title, url, summary, fetched_at, enriched, content_length) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (feed_id, f"RSS Title {i}", f"https://a.example/p/rss{i}",
             f"RSS summary body {i} " * (25 + i), f"{today} 11:00:00",
             rss_enriched, 500 + i * 10),
        )
        conn.execute(
            "INSERT INTO rss_classifications (article_id, topic, depth_score, relevant, excluded, reason) "
            "VALUES (?, ?, ?, 1, 0, ?)",
            (conn.execute("SELECT id FROM rss_articles WHERE url = ?",
                          (f"https://a.example/p/rss{i}",)).fetchone()[0],
             "LLM", 3 if i == 0 else 2, "rss reason"),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def today() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------
# Test 1 — 7 candidates → gather top_n=5, sorted correctly
# ---------------------------------------------------------------------
def test_top_n_sorting(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=4, rss_rows=3)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    assert len(candidates) == 5
    # Sort invariant: depth DESC first
    depths = [c["depth_score"] for c in candidates]
    assert depths == sorted(depths, reverse=True)
    # Stats reflect all 7 + deep total
    assert stats["kol_total"] == 4
    assert stats["rss_total"] == 3


# ---------------------------------------------------------------------
# Test 2 — render Markdown contains topic, source label, link, excerpt
# ---------------------------------------------------------------------
def test_render_markdown_shape(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=1, rss_rows=1)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    md = dd.render(today, candidates, stats)
    assert "[Agent]" in md or "[LLM]" in md
    assert "· WeChat" in md or "· RSS" in md
    assert "阅读原文" in md
    assert "http" in md
    # Asymmetric source tags
    assert "[KOL]" in md or "[RSS]" in md


# ---------------------------------------------------------------------
# Test 3 — empty candidate pool: no Telegram + no archive
# ---------------------------------------------------------------------
def test_empty_state_skips_telegram_and_archive(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=0, rss_rows=0)
    with patch.object(dd, "deliver_telegram") as mock_tg, \
         patch.object(dd, "archive") as mock_arch:
        rc = dd.run(
            today, dry_run=False, db_path=db, digest_dir=tmp_path / "digests"
        )
    assert rc == 0
    mock_tg.assert_not_called()
    mock_arch.assert_not_called()
    assert not (tmp_path / "digests").exists() or \
        not list((tmp_path / "digests").rglob("*.md"))


# ---------------------------------------------------------------------
# Test 4 — dry-run: print Markdown, no Telegram, no archive
# ---------------------------------------------------------------------
def test_dry_run_no_network_no_write(tmp_path: Path, today: str, capsys) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=1, rss_rows=1)
    with patch.object(dd, "deliver_telegram") as mock_tg, \
         patch.object(dd, "archive") as mock_arch:
        dd.run(today, dry_run=True, db_path=db, digest_dir=tmp_path / "d")
    mock_tg.assert_not_called()
    mock_arch.assert_not_called()
    out = capsys.readouterr().out
    assert today in out
    assert "OmniGraph-Vault" in out


# ---------------------------------------------------------------------
# Test 5 — archive uses atomic tmp-then-rename via os.replace
# ---------------------------------------------------------------------
def test_archive_uses_os_replace(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=1, rss_rows=0)
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
# Test 6 — archive path under omonigraph-vault (typo preserved)
# ---------------------------------------------------------------------
def test_archive_path_preserves_typo(tmp_path: Path, today: str, monkeypatch) -> None:
    """The digest goes under BASE_DIR / 'digests' and BASE_DIR is
    ~/.hermes/omonigraph-vault (typo preserved per CLAUDE.md)."""
    fake_base = tmp_path / "omonigraph-vault"
    monkeypatch.setattr(dd, "BASE_DIR", fake_base)
    monkeypatch.setattr(dd, "DIGEST_DIR", fake_base / "digests")
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=1, rss_rows=0)
    candidates, stats = dd.gather(today, top_n=5, db_path=db)
    md = dd.render(today, candidates, stats)
    path = dd.archive(today, md)  # uses module-level DIGEST_DIR via default
    assert "omonigraph-vault" in str(path)
    assert path.name == f"{today}.md"


# ---------------------------------------------------------------------
# Test 7 — D-19 asymmetric UNION: KOL requires enriched=2, RSS does NOT
# ---------------------------------------------------------------------
def test_asymmetric_enriched_filter(tmp_path: Path, today: str) -> None:
    """KOL rows with enriched=0 MUST NOT appear; RSS rows with enriched=0 MUST appear."""
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=2, rss_rows=2, kol_enriched=0, rss_enriched=0)
    candidates, _ = dd.gather(today, top_n=10, db_path=db)
    srcs = [c["src"] for c in candidates]
    assert "kol" not in srcs, "KOL with enriched=0 must be excluded"
    assert "rss" in srcs, "RSS with enriched=0 must still appear (D-19)"


# ---------------------------------------------------------------------
# Test 8 — KOL enriched=2 + RSS enriched=0 both appear
# ---------------------------------------------------------------------
def test_mixed_enriched_both_appear(tmp_path: Path, today: str) -> None:
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=2, rss_rows=2, kol_enriched=2, rss_enriched=0)
    candidates, _ = dd.gather(today, top_n=10, db_path=db)
    srcs = {c["src"] for c in candidates}
    assert "kol" in srcs and "rss" in srcs


# ---------------------------------------------------------------------
# Test 9 — delivery returns False on missing Telegram creds, run() rc=1
# ---------------------------------------------------------------------
def test_missing_telegram_creds_returns_rc1(
    tmp_path: Path, today: str, monkeypatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    db = tmp_path / "t.db"
    _seed(db, today, kol_rows=1, rss_rows=0)
    rc = dd.run(
        today,
        dry_run=False,
        db_path=db,
        digest_dir=tmp_path / "digests",
    )
    # Archive succeeded but Telegram failed → rc=1 (so cron can alert)
    assert rc == 1
    assert (tmp_path / "digests" / f"{today}.md").exists()
