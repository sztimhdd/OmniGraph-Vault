"""kb-v2.2-7 Wave 4: bilingual-by-site-language SSG rendering.

Validates that:
  1. Article detail HTML emits `<span data-lang="zh">` + `<span data-lang="en">`
     for h1 and dual `<article class="article-body lang-block" data-lang>` siblings.
  2. `data-fixed-lang="true"` no longer appears in any rendered article HTML
     (deleted in Wave 4 per locked decision A1).
  3. `<script>window.KB_DEFAULT_LANG = "..."</script>` precedes the lang.js
     script tag in rendered base.html, with the value reflecting the
     KB_DEFAULT_LANG env var (locked decision A9).
  4. Articles index + homepage emit dual-span card titles.
  5. Untranslated rows (`title_translated IS NULL`) gracefully render the
     original title in BOTH zh and en spans via the Jinja `or` fallback —
     no "[Translation pending]" marker per locked decision A4.
  6. The `_resolve_kb_default_lang` helper validates against {zh-CN, en} and
     falls back to 'zh-CN' on unset / bogus values.

Real fixture DB; one row UPDATEd in-place to seed populated translation
columns. No mocks for the DB layer (Testing Trophy: integration > unit).
"""
from __future__ import annotations

import importlib
import os
import re
import sqlite3
from pathlib import Path

import pytest


# ---- helpers ---------------------------------------------------------------


def _seed_one_translated_row(fixture_db: Path) -> int:
    """Populate body_translated + title_translated for KOL id=1 (a positive
    DATA-07 row in the shared fixture). Returns the seeded id.
    """
    with sqlite3.connect(fixture_db) as conn:
        conn.execute(
            "UPDATE articles SET title_translated = ?, body_translated = ?, "
            "translated_lang = ?, translated_at = ? WHERE id = ?",
            (
                "Test Article One (translated)",
                "# English Translation\n\nThis article body has been translated.",
                "en",
                "2026-05-19T00:00:00Z",
                1,
            ),
        )
        conn.commit()
    return 1


@pytest.fixture
def export_module_for_w4(fixture_db: Path, tmp_path: Path, monkeypatch):
    """Reload kb.config + kb.export_knowledge_base with KB_DB_PATH pointing at
    fixture DB, KB_IMAGES_DIR empty (skip D-14 fallback), and the requested
    KB_DEFAULT_LANG env var (caller sets via monkeypatch BEFORE invoking).
    """
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setenv("KB_IMAGES_DIR", str(images_dir))

    import kb.config
    import kb.data.article_query
    import kb.export_knowledge_base
    import kb.i18n

    importlib.reload(kb.config)
    importlib.reload(kb.i18n)
    monkeypatch.setattr(
        kb.data.article_query,
        "QUALITY_FILTER_ENABLED",
        os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off",
    )
    importlib.reload(kb.export_knowledge_base)
    return kb.export_knowledge_base


# ---- _resolve_kb_default_lang (pure Python, no SSG) ------------------------


def test_default_lang_unset_resolves_zh_cn(monkeypatch):
    monkeypatch.delenv("KB_DEFAULT_LANG", raising=False)
    from kb.export_knowledge_base import _resolve_kb_default_lang
    assert _resolve_kb_default_lang() == "zh-CN"


def test_default_lang_en_explicit(monkeypatch):
    monkeypatch.setenv("KB_DEFAULT_LANG", "en")
    from kb.export_knowledge_base import _resolve_kb_default_lang
    assert _resolve_kb_default_lang() == "en"


def test_default_lang_zh_cn_explicit(monkeypatch):
    monkeypatch.setenv("KB_DEFAULT_LANG", "zh-CN")
    from kb.export_knowledge_base import _resolve_kb_default_lang
    assert _resolve_kb_default_lang() == "zh-CN"


def test_default_lang_bogus_falls_back_to_zh_cn(monkeypatch):
    monkeypatch.setenv("KB_DEFAULT_LANG", "fr")
    from kb.export_knowledge_base import _resolve_kb_default_lang
    assert _resolve_kb_default_lang() == "zh-CN"


def test_default_lang_empty_falls_back_to_zh_cn(monkeypatch):
    monkeypatch.setenv("KB_DEFAULT_LANG", "")
    from kb.export_knowledge_base import _resolve_kb_default_lang
    assert _resolve_kb_default_lang() == "zh-CN"


# ---- SSG output: dual-`<span data-lang>` + `<article lang-block>` ----------


@pytest.mark.integration
def test_article_detail_emits_dual_span_h1(export_module_for_w4, tmp_path: Path, fixture_db: Path):
    """h1 has `<span data-lang="zh">` + `<span data-lang="en">` children."""
    seeded = _seed_one_translated_row(fixture_db)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0

    # Find the seeded article's HTML by scanning for the seeded title.
    html_files = list((out / "articles").glob("*.html"))
    target = None
    for f in html_files:
        text = f.read_text(encoding="utf-8")
        if "测试文章一" in text and "Test Article One (translated)" in text:
            target = text
            break
    assert target is not None, f"seeded translated article (id={seeded}) not found in output"

    h1_match = re.search(r"<h1>(.*?)</h1>", target, re.DOTALL)
    assert h1_match, "no <h1> in article detail page"
    h1 = h1_match.group(1)
    assert 'data-lang="zh"' in h1
    assert 'data-lang="en"' in h1
    assert "测试文章一" in h1                          # zh source title
    assert "Test Article One (translated)" in h1     # en translated title


@pytest.mark.integration
def test_article_detail_emits_dual_lang_block_body(export_module_for_w4, tmp_path: Path, fixture_db: Path):
    """Body is two `<article class="article-body lang-block" data-lang>` siblings."""
    _seed_one_translated_row(fixture_db)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0

    target = None
    for f in (out / "articles").glob("*.html"):
        text = f.read_text(encoding="utf-8")
        if "English Translation" in text and "测试文章一" in text:
            target = text
            break
    assert target is not None

    # Both siblings present; both have `lang-block` class so the existing CSS
    # block-display rule (style.css:343-346) activates per-language.
    assert re.search(
        r'<article class="article-body lang-block" data-lang="zh">',
        target,
    ), "zh body sibling missing"
    assert re.search(
        r'<article class="article-body lang-block" data-lang="en">',
        target,
    ), "en body sibling missing"
    # zh sibling has source body; en sibling has translated body
    assert "English Translation" in target


@pytest.mark.integration
def test_article_detail_strips_data_fixed_lang(export_module_for_w4, tmp_path: Path):
    """`data-fixed-lang="true"` does not appear in any rendered article HTML."""
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    for f in (out / "articles").glob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert "data-fixed-lang" not in text, (
            f"data-fixed-lang attribute should be removed (Wave 4 / locked A1) — found in {f.name}"
        )


# ---- SSG output: card titles dual-span -------------------------------------


@pytest.mark.integration
def test_articles_index_card_titles_dual_span(export_module_for_w4, tmp_path: Path, fixture_db: Path):
    """`/articles/` list page card titles emit dual `<span data-lang>`."""
    _seed_one_translated_row(fixture_db)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    list_html = (out / "articles" / "index.html").read_text(encoding="utf-8")
    # The seeded translated row's en label must appear in the en span on its card.
    assert "Test Article One (translated)" in list_html
    # Pattern check on card titles wrapped by .article-card-title h3.
    card_titles = re.findall(
        r'<h3 class="article-card-title">\s*(.*?)\s*</h3>',
        list_html,
        re.DOTALL,
    )
    assert card_titles, "no article-card-title nodes found"
    # At least one card must contain BOTH a zh span and an en span (the seeded row).
    seeded_card = next(
        (c for c in card_titles if "Test Article One (translated)" in c),
        None,
    )
    assert seeded_card is not None
    assert 'data-lang="zh"' in seeded_card
    assert 'data-lang="en"' in seeded_card


@pytest.mark.integration
def test_homepage_card_titles_dual_span(export_module_for_w4, tmp_path: Path, fixture_db: Path):
    """`index.html` homepage card titles also use the dual-span pattern."""
    _seed_one_translated_row(fixture_db)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    home_html = (out / "index.html").read_text(encoding="utf-8")
    # Homepage shows up to 20 most recent; seeded id=1 is in the fixture's KOL set.
    assert 'data-lang="zh"' in home_html
    assert 'data-lang="en"' in home_html


@pytest.mark.integration
def test_untranslated_card_falls_back_to_original_title(
    export_module_for_w4, tmp_path: Path, fixture_db: Path
):
    """Untranslated rows render original title in both zh and en spans (locked A4)."""
    # NOTE: do NOT seed any translation here — fixture rows other than id=1
    # have title_translated IS NULL, exercising the `or article.title` fallback.
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    list_html = (out / "articles" / "index.html").read_text(encoding="utf-8")
    # Pick any non-seeded fixture title we know exists (id=3 KOL: "Agent 框架对比").
    assert "Agent 框架对比" in list_html
    # The card containing this title must have BOTH spans — the en span carries
    # the same Chinese text via the `or` fallback (no "[Translation pending]").
    card_pattern = re.compile(
        r'<h3 class="article-card-title">\s*(.*?Agent 框架对比.*?)\s*</h3>',
        re.DOTALL,
    )
    m = card_pattern.search(list_html)
    assert m is not None, "non-translated card not found"
    inner = m.group(1)
    zh_count = inner.count("Agent 框架对比")
    assert zh_count == 2, (
        f"expected 2 occurrences of original title (zh + en fallback), got {zh_count}"
    )
    # No translation marker per locked A4
    assert "Translation pending" not in inner
    assert "[translated]" not in inner.lower()


# ---- KB_DEFAULT_LANG injection in rendered base.html -----------------------


@pytest.mark.integration
def test_kb_default_lang_zh_cn_default_in_rendered_html(
    export_module_for_w4, tmp_path: Path, monkeypatch
):
    """Unset KB_DEFAULT_LANG → SSG injects window.KB_DEFAULT_LANG = "zh-CN"."""
    monkeypatch.delenv("KB_DEFAULT_LANG", raising=False)
    # Rebuild env so globals pick up the (now unset) value.
    importlib.reload(export_module_for_w4)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    home = (out / "index.html").read_text(encoding="utf-8")
    inject_idx = home.find('window.KB_DEFAULT_LANG = "zh-CN"')
    lang_js_idx = home.find('static/lang.js')
    assert inject_idx != -1, "window.KB_DEFAULT_LANG injection missing"
    assert lang_js_idx != -1, "lang.js script tag missing"
    assert inject_idx < lang_js_idx, (
        "KB_DEFAULT_LANG injection MUST precede lang.js script tag (so the IIFE "
        f"sees the value at runtime). Got inject_idx={inject_idx}, lang_js_idx={lang_js_idx}"
    )


@pytest.mark.integration
def test_kb_default_lang_en_explicit_in_rendered_html(
    export_module_for_w4, tmp_path: Path, monkeypatch
):
    """KB_DEFAULT_LANG=en → SSG injects window.KB_DEFAULT_LANG = "en"."""
    monkeypatch.setenv("KB_DEFAULT_LANG", "en")
    importlib.reload(export_module_for_w4)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'window.KB_DEFAULT_LANG = "en"' in home
    # Defensive: zh-CN value should NOT appear under explicit en config.
    assert 'window.KB_DEFAULT_LANG = "zh-CN"' not in home


@pytest.mark.integration
def test_kb_default_lang_bogus_falls_back_in_rendered_html(
    export_module_for_w4, tmp_path: Path, monkeypatch
):
    """Bogus KB_DEFAULT_LANG → SSG silently uses zh-CN fallback (operator-typo safe)."""
    monkeypatch.setenv("KB_DEFAULT_LANG", "fr")
    importlib.reload(export_module_for_w4)
    out = tmp_path / "out"
    rc = export_module_for_w4.main(["--output-dir", str(out)])
    assert rc == 0
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'window.KB_DEFAULT_LANG = "zh-CN"' in home
    assert 'window.KB_DEFAULT_LANG = "fr"' not in home
