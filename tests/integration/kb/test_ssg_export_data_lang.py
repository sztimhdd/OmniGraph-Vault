"""kb-v2.2-6 (F6): SSG data-lang regularization regression tests.

Pre-fix: prod DB had mixed `articles.lang = 'zh'` (legacy short) and `'zh-CN'`
(canonical long) values. SSG rendered both verbatim, so the JS lang filter
using `[data-lang='zh-CN']` selector silently missed all 'zh'-tagged Chinese
cards.

Fix: `kb.export_knowledge_base._canonical_lang()` normalizes at the
data-layer-to-template boundary; SSG always emits `data-lang='zh-CN'` for
Chinese articles.

These tests:
1. Unit-test the helper (pure function — fast, no SSG needed)
2. Integration-test the full SSG flow with a synthetic 'zh'-tagged fixture
   DB and verify post-render counts (no `data-lang='zh'` on cards, all
   Chinese cards on `data-lang='zh-CN'`).
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Unit tests — pure helper function
# ---------------------------------------------------------------------------


def test_canonical_lang_maps_legacy_zh_to_canonical_zh_cn():
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang("zh") == "zh-CN"


def test_canonical_lang_idempotent_on_zh_cn():
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang("zh-CN") == "zh-CN"


def test_canonical_lang_passes_through_en():
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang("en") == "en"


def test_canonical_lang_none_or_empty_returns_unknown():
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang(None) == "unknown"
    assert _canonical_lang("") == "unknown"


def test_canonical_lang_unknown_passes_through():
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang("unknown") == "unknown"


def test_canonical_lang_passes_through_unrecognized_codes():
    """Defensive: don't silently rewrite future codes (ja-JP, fr-FR, etc.)."""
    from kb.export_knowledge_base import _canonical_lang
    assert _canonical_lang("ja-JP") == "ja-JP"
    assert _canonical_lang("fr") == "fr"


# ---------------------------------------------------------------------------
# Integration test — full SSG export with synthetic legacy-zh fixture
# ---------------------------------------------------------------------------


def _build_minimal_fixture_db(db_path: Path) -> None:
    """Build a tiny DB with mix of legacy 'zh' + canonical 'zh-CN' + 'en' rows.

    Schema mirrors Hermes prod (articles + rss_articles + lang + classifications +
    extracted_entities + layer1/layer2 verdicts) to satisfy export_knowledge_base
    DATA-07 filter and kb-2 entity discovery.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                body TEXT,
                content_hash TEXT,
                lang TEXT,
                update_time INTEGER,
                layer1_verdict TEXT,
                layer2_verdict TEXT,
                body_translated TEXT,
                title_translated TEXT,
                translated_lang VARCHAR(5),
                translated_at DATETIME
            );
            CREATE TABLE rss_articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                body TEXT,
                content_hash TEXT,
                lang TEXT,
                published_at TEXT,
                fetched_at TEXT,
                topics TEXT,
                depth INTEGER,
                layer1_verdict TEXT,
                layer2_verdict TEXT,
                body_translated TEXT,
                title_translated TEXT,
                translated_lang VARCHAR(5),
                translated_at DATETIME
            );
            CREATE TABLE classifications (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
                depth_score INTEGER,
                relevant INTEGER DEFAULT 0,
                excluded INTEGER DEFAULT 0,
                reason TEXT,
                classified_at TEXT,
                depth INTEGER,
                topics TEXT,
                rationale TEXT,
                UNIQUE(article_id, topic)
            );
            CREATE TABLE extracted_entities (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT,
                extracted_at TEXT
            );
            """
        )
        body = (
            "# Test\n\nMinimum body for DATA-07 + OG fallback. "
            "Has enough text to satisfy snippet generation. "
            "Plus more text to be safely above thresholds."
        )
        # Mix: 1 legacy 'zh', 1 canonical 'zh-CN', 1 'en'
        conn.executemany(
            "INSERT INTO articles "
            "(id,title,url,body,content_hash,lang,update_time,layer1_verdict,layer2_verdict) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (1, "Legacy ZH Article", "https://mp.weixin.qq.com/s/legacy",
                 body, "legacyzhzh", "zh", 1778270400, "candidate", "ok"),
                (2, "Canonical ZH-CN Article", "https://mp.weixin.qq.com/s/canon",
                 body, "canonzhcncn", "zh-CN", 1778180400, "candidate", "ok"),
                (3, "English Article", "https://mp.weixin.qq.com/s/eng",
                 body, "englishabc", "en", 1778090400, "candidate", "ok"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def legacy_zh_fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "fixture.db"
    _build_minimal_fixture_db(db)
    return db


def test_ssg_export_normalizes_legacy_zh_to_zh_cn_in_articles_index(
    legacy_zh_fixture_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Full export pipeline must emit data-lang='zh-CN' on the legacy-'zh' card.

    Pre-fix: the legacy-'zh' article would render as data-lang='zh', invisible
    to the [data-lang='zh-CN'] JS filter. Post-fix: rendered as 'zh-CN'.
    """
    output_dir = tmp_path / "kb_output"

    # Run export as subprocess to avoid module-level config side effects in
    # the parent pytest process. KB_DB_PATH + KB_OUTPUT_DIR override config
    # at import time.
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "KB_DB_PATH": str(legacy_zh_fixture_db),
        "KB_OUTPUT_DIR": str(output_dir),
        "KB_BASE_PATH": "",
    }
    result = subprocess.run(
        [sys.executable, "-m", "kb.export_knowledge_base"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, (
        f"export failed: stderr={result.stderr[-800:]} stdout={result.stdout[-400:]}"
    )

    index_html = (output_dir / "articles" / "index.html").read_text(encoding="utf-8")

    # Pull only article-card root data-lang attrs (filter out bilingual UI
    # chrome spans which legitimately use data-lang='zh' / data-lang='en'
    # as binary visibility toggles).
    import re
    card_lang_attrs = re.findall(r'<a class="article-card"[^>]*data-lang="([^"]+)"', index_html)

    # The legacy-'zh' article must NOT keep its 'zh' short code on the card
    assert "zh" not in card_lang_attrs, (
        f"Article-card data-lang attrs should canonicalize to 'zh-CN', got: {card_lang_attrs}"
    )
    # Both Chinese articles render as zh-CN
    assert card_lang_attrs.count("zh-CN") == 2, (
        f"Expected 2 zh-CN cards (1 legacy + 1 canonical), got: {card_lang_attrs}"
    )
    assert card_lang_attrs.count("en") == 1, (
        f"Expected 1 en card, got: {card_lang_attrs}"
    )


def test_ssg_export_emits_no_legacy_zh_data_lang_on_article_cards(
    legacy_zh_fixture_db: Path, tmp_path: Path
):
    """Final acceptance: no card-level data-lang='zh' anywhere in the output."""
    output_dir = tmp_path / "kb_output"

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "KB_DB_PATH": str(legacy_zh_fixture_db),
        "KB_OUTPUT_DIR": str(output_dir),
        "KB_BASE_PATH": "",
    }
    result = subprocess.run(
        [sys.executable, "-m", "kb.export_knowledge_base"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, f"export failed: {result.stderr[-800:]}"

    index_html = (output_dir / "articles" / "index.html").read_text(encoding="utf-8")

    # Look for data-lang on article-cards AND lang-badges (the two places
    # where article.lang flows from DB through SSG render). Must be 'zh-CN'
    # not legacy 'zh'.
    import re
    card_root = re.findall(r'<a class="article-card"[^>]*data-lang="([^"]+)"', index_html)
    lang_badges = re.findall(r'<span class="lang-badge"[^>]*data-lang="([^"]+)"', index_html)

    for v in card_root + lang_badges:
        assert v != "zh", (
            f"Found legacy short 'zh' on article-card or lang-badge — F6 fix regression. "
            f"card_root={card_root} lang_badges={lang_badges}"
        )
