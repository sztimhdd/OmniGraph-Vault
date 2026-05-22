"""Tests for 260522 Postmortem #9 — translated-body image parity helpers.

Pinning strategy (per feedback_test_mirrors_impl): fixtures pin on independently
verifiable shapes (real <img> / markdown blocks, real paragraph counts, real
hash strings) — NOT on the regex used in the implementation.
"""
from __future__ import annotations

import pytest

from kb.data.article_query import (
    ArticleRecord,
    _extract_image_blocks,
    _splice_images_into_body,
    rewrite_translated_body_with_image_parity,
)


# ---------- _extract_image_blocks ----------


def test_extract_html_img_tags():
    """HTML <img> tags are returned in document order."""
    body = (
        '<p>Intro</p>\n\n'
        '<img src="/static/img/a/0.jpg" alt="image 0" loading="lazy">\n\n'
        '<p>Middle</p>\n\n'
        '<img src="/static/img/a/1.jpg" alt="image 1" loading="lazy">\n'
    )
    blocks = _extract_image_blocks(body)
    assert len(blocks) == 2
    assert "/static/img/a/0.jpg" in blocks[0]
    assert "/static/img/a/1.jpg" in blocks[1]


def test_extract_markdown_image_syntax():
    """Markdown ![alt](url) image syntax is returned."""
    body = "intro\n\n![cover](/static/img/a/0.jpg)\n\nmore\n\n![](/static/img/a/1.jpg)\n"
    blocks = _extract_image_blocks(body)
    assert len(blocks) == 2
    assert blocks[0] == "![cover](/static/img/a/0.jpg)"
    assert blocks[1] == "![](/static/img/a/1.jpg)"


def test_extract_mixed_html_and_markdown():
    """Mixed HTML + markdown both detected."""
    body = '![](/img/a.jpg)\n\nbody\n\n<img src="/img/b.jpg">'
    blocks = _extract_image_blocks(body)
    assert len(blocks) == 2


def test_extract_empty_body_returns_empty_list():
    assert _extract_image_blocks("") == []
    assert _extract_image_blocks(None) == []  # type: ignore[arg-type]


def test_extract_no_images_returns_empty_list():
    assert _extract_image_blocks("just text\n\nno images\n") == []


# ---------- _splice_images_into_body ----------


def test_splice_no_missing_images_returns_body_unchanged():
    """No images to splice — body returns identical."""
    body = "p1\n\np2\n\np3"
    assert _splice_images_into_body(body, []) == body


def test_splice_into_no_paragraph_body_appends_at_end():
    """Single-paragraph body has no internal boundary — append at end."""
    body = "single line of text"
    out = _splice_images_into_body(body, ['<img src="/x.jpg">'])
    assert out.startswith("single line of text")
    assert '<img src="/x.jpg">' in out


def test_splice_one_image_into_three_paragraphs_lands_in_middle():
    """1 image, 3 paragraphs: insertion floor((1)*3/2) = 1, so AFTER para 1."""
    body = "p1\n\np2\n\np3"
    out = _splice_images_into_body(body, ["IMG"])
    parts = out.split("\n\n")
    # Expected order: p1, IMG, p2, p3
    assert parts == ["p1", "IMG", "p2", "p3"]


def test_splice_two_images_into_four_paragraphs_distributes_evenly():
    """2 images, 4 paragraphs: positions floor(1*4/3)=1, floor(2*4/3)=2."""
    body = "p1\n\np2\n\np3\n\np4"
    out = _splice_images_into_body(body, ["A", "B"])
    parts = out.split("\n\n")
    # Expected: p1, A, p2, B, p3, p4
    assert parts == ["p1", "A", "p2", "B", "p3", "p4"]


def test_splice_does_not_double_insert_after_same_paragraph_overflow():
    """3 images, 2 paragraphs: clamping puts them all after paragraph 1."""
    body = "p1\n\np2"
    out = _splice_images_into_body(body, ["A", "B", "C"])
    parts = out.split("\n\n")
    # All 3 images clamp to position 1 — they go after p1 in stable order.
    assert parts == ["p1", "A", "B", "C", "p2"]


def test_splice_empty_body_with_missing_images_concatenates():
    """Empty body + images: just join with blank lines."""
    out = _splice_images_into_body("", ["A", "B"])
    assert out == "A\n\nB"


# ---------- rewrite_translated_body_with_image_parity ----------


def _make_rec(
    *,
    body: str = "",
    body_translated: str | None = None,
    body_repositioned: str | None = None,
    body_cleaned: str | None = None,
    content_hash: str = "abc1234567",
) -> ArticleRecord:
    return ArticleRecord(
        id=1,
        source="wechat",
        title="t",
        url="u",
        body=body,
        content_hash=content_hash,
        lang="zh-CN",
        update_time="2026-05-21",
        publish_time=None,
        title_translated="T",
        body_translated=body_translated,
        translated_lang="en",
        body_cleaned=body_cleaned,
        body_repositioned=body_repositioned,
    )


def test_parity_returns_none_when_no_translated_body(tmp_path, monkeypatch):
    """No translated body → None (template fallback to body_html kicks in)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    rec = _make_rec(body="some zh body", body_translated=None)
    assert rewrite_translated_body_with_image_parity(rec) is None


def test_parity_passthrough_when_translated_has_equal_images(tmp_path, monkeypatch):
    """Translated body has same image count → return as-is (no splice)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    monkeypatch.setattr(kb_config, "KB_BASE_PATH", "")
    src = (
        "p1\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        "p2\n"
    )
    trans = (
        "EN p1\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        "EN p2\n"
    )
    rec = _make_rec(body=src, body_translated=trans)
    out = rewrite_translated_body_with_image_parity(rec)
    assert out is not None
    assert out.count("<img") == 1
    assert "EN p1" in out and "EN p2" in out


def test_parity_splices_missing_source_images(tmp_path, monkeypatch):
    """Translated body has 0 images, source has 2 → splice both into translated."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    monkeypatch.setattr(kb_config, "KB_BASE_PATH", "")
    src = (
        "intro\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        "middle\n\n"
        '<img src="/static/img/abc1234567/1.jpg" alt="image 1" loading="lazy">\n\n'
        "outro"
    )
    # Translator dropped both images.
    trans = "EN intro\n\nEN middle\n\nEN outro\n"
    rec = _make_rec(body=src, body_translated=trans)
    out = rewrite_translated_body_with_image_parity(rec)
    assert out is not None
    # Both source <img> tags should now be present in EN body.
    assert out.count('<img') == 2
    assert "/static/img/abc1234567/0.jpg" in out
    assert "/static/img/abc1234567/1.jpg" in out
    # English text preserved.
    assert "EN intro" in out and "EN middle" in out and "EN outro" in out


def test_parity_splices_only_the_difference(tmp_path, monkeypatch):
    """Source has 3 images, translated has 1 → splice only 2 missing (last two)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    monkeypatch.setattr(kb_config, "KB_BASE_PATH", "")
    src = (
        "p1\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        "p2\n\n"
        '<img src="/static/img/abc1234567/1.jpg" alt="image 1" loading="lazy">\n\n'
        "p3\n\n"
        '<img src="/static/img/abc1234567/2.jpg" alt="image 2" loading="lazy">\n\n'
        "p4"
    )
    trans = (
        "EN p1\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        "EN p2\n\n"
        "EN p3\n\n"
        "EN p4\n"
    )
    rec = _make_rec(body=src, body_translated=trans)
    out = rewrite_translated_body_with_image_parity(rec)
    assert out is not None
    assert out.count('<img') == 3
    # All three source URLs are now in EN body.
    assert "/static/img/abc1234567/0.jpg" in out
    assert "/static/img/abc1234567/1.jpg" in out
    assert "/static/img/abc1234567/2.jpg" in out


def test_parity_uses_repositioned_over_translated(tmp_path, monkeypatch):
    """body_repositioned wins over body_translated when both populated (Pass 3)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    monkeypatch.setattr(kb_config, "KB_BASE_PATH", "")
    src = "p1\n\np2\n"
    rec = _make_rec(
        body=src,
        body_translated="OLD translation should NOT win",
        body_repositioned="REPOSITIONED EN p1\n\nREPOSITIONED EN p2\n",
    )
    out = rewrite_translated_body_with_image_parity(rec)
    assert out is not None
    assert "REPOSITIONED" in out
    assert "OLD translation" not in out


def test_parity_drops_external_wechat_image_from_source(tmp_path, monkeypatch):
    """Source body's external mmbiz <img> is stripped before count comparison —
    translator-dropped local images are spliced; mmbiz-only sources do NOT
    inflate parity expectations."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    monkeypatch.setattr(kb_config, "KB_BASE_PATH", "")
    # Source has 1 local <img> + 1 mmbiz <img>; mmbiz should be stripped.
    src = (
        "p1\n\n"
        '<img src="/static/img/abc1234567/0.jpg" alt="image 0" loading="lazy">\n\n'
        '<img src="https://mmbiz.qpic.cn/foo.jpg">\n\n'
        "p2"
    )
    trans = "EN p1\n\nEN p2\n"
    rec = _make_rec(body=src, body_translated=trans)
    out = rewrite_translated_body_with_image_parity(rec)
    assert out is not None
    # Only the 1 local image should be spliced into EN — mmbiz is gone.
    assert out.count('<img') == 1
    assert "mmbiz" not in out
    assert "/static/img/abc1234567/0.jpg" in out
