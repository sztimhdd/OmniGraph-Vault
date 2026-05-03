"""Unit tests for enrichment.run_enrich_for_id — env-var contract + RSS guard."""
from __future__ import annotations

import sqlite3
import subprocess as _subprocess_module
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _seed_db(db: Path) -> None:
    """Seed a minimal DB with both the articles table (KOL) and rss_articles."""
    import batch_scan_kol  # triggers init_db path and full schema
    conn = batch_scan_kol.init_db(db)
    # Create a KOL account + article with content_hash populated
    conn.execute(
        "INSERT INTO accounts (name, fakeid) VALUES (?, ?)",
        ("TestKOL", "fake-kol-id-1"),
    )
    conn.execute(
        "INSERT INTO articles (account_id, title, url, content_hash) VALUES (?, ?, ?, ?)",
        (1, "KOL Title", "https://mp.weixin.qq.com/s/abc", "abcdef123456"),
    )
    # Seed one RSS feed + article
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
        ("Feed A", "https://a.example/rss"),
    )
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (?, ?, ?, ?)",
        (1, "RSS Title", "https://a.example/p/1", "Body"),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch):
    db = tmp_path / "kol_scan.db"
    _seed_db(db)
    # Redirect the module-level DB constant to this temp file
    import enrichment.run_enrich_for_id as mod
    monkeypatch.setattr(mod, "DB", db)
    monkeypatch.setattr(mod, "BASE_DIR", tmp_path / "omonigraph-vault")
    yield db, mod


def _run_main(mod, argv: list[str]) -> int:
    with patch.object(sys, "argv", ["run_enrich_for_id.py", *argv]):
        return mod.main()


def test_kol_path_invokes_skill_with_env_vars(seeded) -> None:
    _, mod = seeded
    fake_result = MagicMock(returncode=0, stdout="enriched ok", stderr="")
    with patch.object(mod.subprocess, "run", return_value=fake_result) as mock_run:
        rc = _run_main(mod, ["--source", "kol", "--article-id", "1"])
    assert rc == 0
    mock_run.assert_called_once()
    call = mock_run.call_args
    # First positional arg: the command list
    cmd = call.args[0] if call.args else call.kwargs.get("args")
    assert cmd == ["hermes", "skill", "run", "enrich_article"]
    env = call.kwargs["env"]
    assert env["ARTICLE_PATH"].endswith("final_content.md")
    assert "abcdef123456" in env["ARTICLE_PATH"]
    assert env["ARTICLE_URL"] == "https://mp.weixin.qq.com/s/abc"
    assert env["ARTICLE_HASH"] == "abcdef123456"


def test_rss_guarded_noop_does_not_invoke_skill(seeded, capsys) -> None:
    _, mod = seeded
    with patch.object(mod.subprocess, "run") as mock_run:
        rc = _run_main(mod, ["--source", "rss", "--article-id", "1"])
    assert rc == 0
    mock_run.assert_not_called()
    captured = capsys.readouterr()
    assert "RSS excluded per D-07 REVISED" in captured.out


def test_kol_missing_article_exits_nonzero(seeded) -> None:
    _, mod = seeded
    with patch.object(mod.subprocess, "run") as mock_run:
        rc = _run_main(mod, ["--source", "kol", "--article-id", "9999"])
    assert rc == 2
    mock_run.assert_not_called()


def test_subprocess_args_use_env_not_cli_flags(seeded) -> None:
    """SKILL.md contract requires env vars — regression guard against anyone
    re-introducing ``--article-id`` on the skill invocation line."""
    _, mod = seeded
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch.object(mod.subprocess, "run", return_value=fake_result) as mock_run:
        _run_main(mod, ["--source", "kol", "--article-id", "1"])
    call = mock_run.call_args
    cmd = call.args[0] if call.args else call.kwargs.get("args")
    joined = " ".join(cmd)
    assert "--article-id" not in joined
    assert "--source" not in joined
    assert cmd == ["hermes", "skill", "run", "enrich_article"]


def test_invalid_source_argparse_errors(seeded) -> None:
    _, mod = seeded
    with pytest.raises(SystemExit) as excinfo:
        _run_main(mod, ["--source", "bogus", "--article-id", "1"])
    # argparse exits with code 2 on choices violation
    assert excinfo.value.code == 2
