"""Tests for _strip_hermes_metadata_prefix (UAT 2026-05-21 #2, Postmortem #7).

Pinning strategy (per feedback_test_mirrors_impl): fixtures are independently
verifiable copies of real Hermes ``localize_markdown.py`` output captured from
``databricks-deploy/_hermes_pull/images/1633058d58/final_content.md``. They are
NOT regenerated from the regex used in the implementation — if implementation
and fixture both drift, both don't pass together.
"""
from __future__ import annotations

import pytest

from kb.data.article_query import (
    ArticleRecord,
    _strip_hermes_metadata_prefix,
    get_article_body,
)


# Real Hermes-output sample copied verbatim from
# databricks-deploy/_hermes_pull/images/1633058d58/final_content.md (lines 1-8).
# Note the 2 spaces after the second '#' — this is exact Hermes output shape.
HERMES_PREFIX_SAMPLE = (
    "# 北大提出首个可验证的仓库级生成基准RepoZero，评测LLM能否从0生成一个代码仓库\n"
    "\n"
    "URL: http://mp.weixin.qq.com/s?__biz=MzIwNzc2NTk0NQ==&mid=2247616919\n"
    "Time: 2026-05-21 05:47:18\n"
    "\n"
    "#  北大提出首个可验证的仓库级生成基准RepoZero，评测LLM能否从0生成一个代码仓库\n"
    "\n"
)
HERMES_BODY_SAMPLE = (
    "北京大学、百度 北京大学、百度 [ 夕小瑶科技说 ](javascript:void\\(0\\);)\n"
    "\n"
    "real article content goes here\n"
)


# ---------- direct helper tests ----------


def test_strip_helper_removes_full_hermes_prefix():
    """Real Hermes prefix is stripped, body remains intact."""
    full = HERMES_PREFIX_SAMPLE + HERMES_BODY_SAMPLE
    out = _strip_hermes_metadata_prefix(full)
    assert out == HERMES_BODY_SAMPLE
    assert "URL:" not in out
    assert "Time:" not in out


def test_strip_helper_idempotent():
    """Second pass on already-stripped body returns same string."""
    full = HERMES_PREFIX_SAMPLE + HERMES_BODY_SAMPLE
    once = _strip_hermes_metadata_prefix(full)
    twice = _strip_hermes_metadata_prefix(once)
    assert once == twice == HERMES_BODY_SAMPLE


def test_strip_helper_passes_through_clean_body():
    """Body that doesn't start with the Hermes pattern is unchanged."""
    clean = "# Just a regular markdown title\n\nsome content here\n"
    assert _strip_hermes_metadata_prefix(clean) == clean


def test_strip_helper_passes_through_empty():
    """Empty / falsy inputs pass through (None-ish guard)."""
    assert _strip_hermes_metadata_prefix("") == ""
    assert _strip_hermes_metadata_prefix(None) is None  # type: ignore[arg-type]


def test_strip_helper_does_not_strip_partial_match():
    """Body with URL: line but not the full pattern stays intact."""
    partial = "# Title\n\nMid-paragraph URL: http://example.com matters here\n"
    assert _strip_hermes_metadata_prefix(partial) == partial


def test_strip_helper_only_strips_at_start():
    """Hermes pattern occurring in the middle of a body is NOT stripped."""
    embedded = "# Real title\n\nsome intro\n\n" + HERMES_PREFIX_SAMPLE + "more body"
    out = _strip_hermes_metadata_prefix(embedded)
    assert out == embedded


def test_strip_helper_handles_single_space_after_hash_in_dup():
    """Some Hermes outputs use '# Title' (one space) for the duplicate, not '#  '."""
    sample = (
        "# Title A\n"
        "\n"
        "URL: http://example.com\n"
        "Time: 2026-01-01 00:00:00\n"
        "\n"
        "# Title A\n"
        "\n"
        "body proper\n"
    )
    assert _strip_hermes_metadata_prefix(sample) == "body proper\n"


def test_strip_helper_does_not_strip_when_url_line_missing():
    """If URL: line absent, the full prefix shape is broken — leave body alone."""
    no_url = (
        "# Title\n"
        "\n"
        "Time: 2026-01-01 00:00:00\n"
        "\n"
        "# Title\n"
        "\n"
        "body\n"
    )
    assert _strip_hermes_metadata_prefix(no_url) == no_url


# ---------- integration via get_article_body ----------


def _make_rec(*, content_hash: str = "1633058d58", body: str = "") -> ArticleRecord:
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
    )


def test_get_article_body_strips_hermes_prefix_from_final_content_md(
    tmp_path, monkeypatch
):
    """End-to-end: final_content.md with real Hermes prefix renders without it."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    article_dir = tmp_path / "1633058d58"
    article_dir.mkdir()
    full = HERMES_PREFIX_SAMPLE + HERMES_BODY_SAMPLE
    (article_dir / "final_content.md").write_text(full, encoding="utf-8")

    body, source = get_article_body(_make_rec())

    assert source == "vision_enriched"
    assert "URL: http://" not in body
    assert "Time: 2026-05-21 05:47:18" not in body
    assert "real article content goes here" in body
    # The duplicate '#  北大...' header line should also be gone — the
    # whole 7-line block is removed atomically.
    assert body.count("北大提出首个可验证的仓库级生成基准RepoZero") == 0


def test_get_article_body_strips_hermes_prefix_from_enriched_md(
    tmp_path, monkeypatch
):
    """final_content.enriched.md gets the strip too (same code path)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    article_dir = tmp_path / "1633058d58"
    article_dir.mkdir()
    full = HERMES_PREFIX_SAMPLE + HERMES_BODY_SAMPLE
    (article_dir / "final_content.enriched.md").write_text(full, encoding="utf-8")

    body, source = get_article_body(_make_rec())

    assert source == "vision_enriched"
    assert "URL:" not in body
    assert "real article content" in body


def test_get_article_body_does_not_strip_db_body(tmp_path, monkeypatch):
    """rec.body fallback path is DB-sourced and clean — strip MUST NOT touch it.

    Defends against false-positive strip on DB content that happens to start
    with a markdown title (most articles do). Pin: even when DB body looks
    like '# X\\n\\nURL: ...\\nTime: ...\\n\\n# X\\n\\n', the strip is on the
    file-read paths only, not on rec.body.
    """
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", str(tmp_path))
    # No file on disk → falls through to rec.body
    db_shape = HERMES_PREFIX_SAMPLE + "DB body fallback content\n"
    body, source = get_article_body(_make_rec(body=db_shape))

    assert source == "raw_markdown"
    # The rec.body path must NOT call the strip — DB content is canonical.
    # If this assert fires, the strip leaked into the wrong code path.
    assert "URL: http://" in body
    assert "DB body fallback content" in body
