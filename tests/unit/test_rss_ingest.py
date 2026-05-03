"""Unit tests for enrichment.rss_ingest — D-07 REVISED + D-19 compliance."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


CHINESE_ZH_BODY = (
    "这是一篇关于人工智能与大语言模型架构的中文技术博客。我们讨论检索增强生成、"
    "向量数据库、以及如何设计一个高效的多智能体系统。本文包含丰富的技术细节,"
    "涵盖 Transformer 架构、注意力机制、以及具体的工程权衡。" * 3
)
ENGLISH_BODY = (
    "This is a long English article about agent architectures, multi-step "
    "reasoning loops, and retrieval augmented generation. It contains enough "
    "text so that langdetect will return 'en' confidently. " * 10
)


def _seed(db: Path, *, include_classification_depth: int = 2) -> None:
    import batch_scan_kol  # noqa: F401 — init_db creates the schema
    conn = batch_scan_kol.init_db(db)
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url, active) VALUES (?, ?, 1)",
        ("Feed A", "https://a.example/rss"),
    )
    feed_id = conn.execute(
        "SELECT id FROM rss_feeds WHERE xml_url=?",
        ("https://a.example/rss",),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (?, ?, ?, ?)",
        (feed_id, "EN Article", "https://a.example/p/en", ENGLISH_BODY),
    )
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url, summary) VALUES (?, ?, ?, ?)",
        (feed_id, "ZH Article", "https://a.example/p/zh", CHINESE_ZH_BODY),
    )
    if include_classification_depth is not None:
        for aid in (1, 2):
            conn.execute(
                "INSERT INTO rss_classifications (article_id, topic, depth_score, relevant, excluded) "
                "VALUES (?, 'Agent', ?, 1, 0)",
                (aid, include_classification_depth),
            )
    conn.commit()
    conn.close()


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch):
    db = tmp_path / "kol_scan.db"
    rss_content = tmp_path / "omonigraph-vault" / "rss_content"
    _seed(db)
    import enrichment.rss_ingest as mod
    monkeypatch.setattr(mod, "DB", db)
    monkeypatch.setattr(mod, "RSS_CONTENT_DIR", rss_content)
    yield db, mod, rss_content


def _make_ingest_mock(return_value: bool = True) -> MagicMock:
    async def fake(*a, **kw):
        return return_value
    return MagicMock(side_effect=fake)


# -----------------------------------------------------------------------
# Test 1: English article triggers one translate call
# -----------------------------------------------------------------------
def test_english_article_triggers_translate(seeded) -> None:
    _, mod, rss_content = seeded

    async def fake_ingest(final_md, aid):
        return True

    with patch.object(mod, "_translate_to_chinese",
                      return_value="这是翻译后的中文正文 " * 20) as mock_tr, \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest), \
         patch("enrichment.rss_ingest.subprocess.run") if False else patch.dict({}):
        stats = mod.run(article_id=1, max_articles=None, dry_run=False)
    assert stats["translated"] == 1
    assert stats["ingested"] == 1
    mock_tr.assert_called_once()
    # final_content.md in Chinese is written
    found = list(rss_content.rglob("final_content.md"))
    assert found, "final_content.md must exist"
    text = found[0].read_text(encoding="utf-8")
    assert any("一" <= ch <= "鿿" for ch in text)


# -----------------------------------------------------------------------
# Test 2: Chinese article skips translation
# -----------------------------------------------------------------------
def test_chinese_article_skips_translation(seeded) -> None:
    _, mod, _ = seeded

    async def fake_ingest(final_md, aid):
        return True

    with patch.object(mod, "_translate_to_chinese") as mock_tr, \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest):
        stats = mod.run(article_id=2, max_articles=None, dry_run=False)
    assert stats["translated"] == 0
    assert stats["ingested"] == 1
    mock_tr.assert_not_called()


# -----------------------------------------------------------------------
# Test 3: original.md + final_content.md both written
# -----------------------------------------------------------------------
def test_original_md_written_before_final(seeded) -> None:
    _, mod, rss_content = seeded

    async def fake_ingest(final_md, aid):
        return True

    with patch.object(mod, "_translate_to_chinese",
                      return_value="中文正文"), \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest):
        mod.run(article_id=1, max_articles=None, dry_run=False)
    originals = list(rss_content.rglob("original.md"))
    finals = list(rss_content.rglob("final_content.md"))
    assert originals and finals


# -----------------------------------------------------------------------
# Test 4: atomic write uses os.replace with .tmp
# -----------------------------------------------------------------------
def test_atomic_write_uses_os_replace(seeded) -> None:
    _, mod, _ = seeded

    async def fake_ingest(final_md, aid):
        return True

    calls: list[tuple[str, str]] = []

    def fake_replace(src, dst):
        import os as _os
        calls.append((str(src), str(dst)))
        return _os.rename(src, dst)

    with patch.object(mod, "_translate_to_chinese", return_value="中文"), \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest), \
         patch.object(mod.os, "replace", side_effect=fake_replace):
        mod.run(article_id=1, max_articles=None, dry_run=False)
    assert calls, "os.replace must have been called at least once"
    for src, dst in calls:
        assert src.endswith(".tmp"), f"source must be .tmp, got {src}"
        assert not dst.endswith(".tmp"), f"dest must be final name, got {dst}"


# -----------------------------------------------------------------------
# Test 5: happy path updates enriched=2
# -----------------------------------------------------------------------
def test_enriched_set_to_2_on_processed(seeded) -> None:
    db, mod, _ = seeded

    async def fake_ingest(final_md, aid):
        return True

    with patch.object(mod, "_translate_to_chinese", return_value="中文"), \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest):
        mod.run(article_id=1, max_articles=None, dry_run=False)
    conn = sqlite3.connect(db)
    enriched = conn.execute(
        "SELECT enriched FROM rss_articles WHERE id=1"
    ).fetchone()[0]
    conn.close()
    assert enriched == 2


# -----------------------------------------------------------------------
# Test 6: D-19 PROCESSED gate failure leaves enriched unchanged
# -----------------------------------------------------------------------
def test_non_processed_leaves_enriched_unchanged(seeded) -> None:
    db, mod, _ = seeded

    async def fake_ingest_fail(final_md, aid):
        return False

    with patch.object(mod, "_translate_to_chinese", return_value="中文"), \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest_fail):
        stats = mod.run(article_id=1, max_articles=None, dry_run=False)
    assert stats["errors"] >= 1
    assert stats["ingested"] == 0
    conn = sqlite3.connect(db)
    enriched = conn.execute(
        "SELECT enriched FROM rss_articles WHERE id=1"
    ).fetchone()[0]
    conn.close()
    # Default was 0; must still be 0 (NOT 2, NOT -2)
    assert enriched == 0


# -----------------------------------------------------------------------
# Test 7: subprocess.run NEVER called (D-07 REVISED hard guard)
# -----------------------------------------------------------------------
def test_subprocess_never_invoked(seeded) -> None:
    _, mod, _ = seeded

    async def fake_ingest(final_md, aid):
        return True

    # Patch the stdlib module so any accidental import + call is caught
    with patch.object(mod, "_translate_to_chinese", return_value="中文"), \
         patch.object(mod, "get_deepseek_api_key", return_value="k"), \
         patch.object(mod, "_ingest_lightrag", side_effect=fake_ingest), \
         patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen") as mock_popen:
        mod.run(article_id=None, max_articles=None, dry_run=False)
    assert mock_run.call_count == 0
    assert mock_popen.call_count == 0


# -----------------------------------------------------------------------
# Test 8: dry run writes nothing + doesn't translate
# -----------------------------------------------------------------------
def test_dry_run_no_writes_no_translate(seeded, capsys) -> None:
    _, mod, rss_content = seeded

    with patch.object(mod, "_translate_to_chinese") as mock_tr, \
         patch.object(mod, "get_deepseek_api_key") as mock_key, \
         patch.object(mod, "_ingest_lightrag") as mock_ingest:
        stats = mod.run(article_id=None, max_articles=None, dry_run=True)
    assert stats["dry_run_planned"] >= 1
    mock_tr.assert_not_called()
    mock_key.assert_not_called()
    mock_ingest.assert_not_called()
    assert not list(rss_content.rglob("final_content.md"))
    out = capsys.readouterr().out
    assert "DRY: rss id=" in out
