"""Unit tests for `kb.export_knowledge_base._make_snippet`.

Regression target: prior to F3.1-F3.5 strip stages, snippets leaked WeChat
scraper boilerplate (URL: line, Time: line, reader-bait separators, follow-CTA,
duplicate author names, duplicate H1 headings) onto homepage cards. See
`databricks-deploy/_kdb_uat_failure_INVESTIGATION.md` Issue #3 for the
deployed-prod snippet pollution sample that motivated these tests.
"""
from __future__ import annotations

from kb.export_knowledge_base import _make_snippet


def test_strips_url_time_preamble():
    """ingest_wechat.py:1303 preamble (`# Title\\nURL:..\\nTime:..`) gone."""
    body = (
        "# 我来预测下一代企业数字化架构\n\n"
        "URL: https://mp.weixin.qq.com/s/759TfOdXch5zWrT4Yo42xA\n"
        "Time: 2026-05-16 23:13:16\n\n"
        "# 我来预测下一代企业数字化架构\n\n"
        "Real content here."
    )
    snippet = _make_snippet(body)
    assert "URL:" not in snippet
    assert "Time:" not in snippet
    assert "https://mp.weixin.qq.com" not in snippet
    assert "Real content here" in snippet
    assert snippet.count("我来预测下一代企业数字化架构") == 1


def test_strips_reader_bait():
    """`;) ______ + 在小说阅读器读本章 + 去阅读 + 在小说阅读器中沉浸阅读` gone."""
    body = (
        "# Article\n\n"
        ";) ______\n\n"
        "在小说阅读器读本章\n\n"
        "去阅读\n\n"
        "在小说阅读器中沉浸阅读\n\n"
        "Real body."
    )
    snippet = _make_snippet(body)
    assert "在小说阅读器" not in snippet
    assert "______" not in snippet
    assert "去阅读" not in snippet
    assert "Real body" in snippet


def test_strips_reader_bait_without_emoticon_prefix():
    """Reader-bait block also strips when bare `______` not preceded by `;)`."""
    body = (
        "# Article\n\n"
        "______\n\n"
        "在小说阅读器读本章\n\n"
        "去阅读\n\n"
        "在小说阅读器中沉浸阅读\n\n"
        "Real body."
    )
    snippet = _make_snippet(body)
    assert "在小说阅读器" not in snippet
    assert "Real body" in snippet


def test_strips_follow_cta():
    """`**点击上方"X",关注公众号...**` CTA banner gone."""
    body = '**点击上方"Deephub Imba",关注公众号,好文章不错过 !** Real content.'
    snippet = _make_snippet(body)
    assert "关注公众号" not in snippet
    assert "点击上方" not in snippet
    assert "Real content" in snippet


def test_collapses_author_dup():
    """`原创 詹老师 詹老师 詹生Talk` -> `原创 詹老师 詹生Talk`."""
    body = "原创 詹老师 詹老师 詹生Talk\n\n实际正文。"
    snippet = _make_snippet(body)
    assert snippet.count("詹老师") == 1
    assert "詹生Talk" in snippet
    assert "实际正文" in snippet


def test_idempotent_on_clean_body():
    """Plain markdown body unaffected; original strips still applied."""
    body = "Just a normal markdown body with **bold** and `code`."
    snippet = _make_snippet(body)
    assert "Just a normal markdown body" in snippet
    assert "**" not in snippet
    assert "`" not in snippet


def test_real_world_deployed_pollution_sample():
    """End-to-end: deployed homepage card-1 sample becomes clean."""
    body = (
        "# 我来预测下一代企业数字化架构：系统CLI化、流程Skill化、员工Agent化\n\n"
        "URL: https://mp.weixin.qq.com/s/759TfOdXch5zWrT4Yo42xA\n"
        "Time: 2026-05-16 23:13:16\n\n"
        "# 我来预测下一代企业数字化架构：系统CLI化、流程Skill化、员工Agent化\n\n"
        "原创 詹老师 詹老师 [ 詹生Talk ](javascript:void\\(0\\);)\n\n"
        ";) ______\n\n"
        "在小说阅读器读本章\n\n"
        "去阅读\n\n"
        "在小说阅读器中沉浸阅读\n\n"
        "下一代企业数字化的核心趋势,是把传统的图形化操作彻底转化为CLI命令、把业务流程拆解成可组合的Skill、让员工本身成为可调度的Agent。"
    )
    snippet = _make_snippet(body)
    assert "URL:" not in snippet
    assert "Time:" not in snippet
    assert "在小说阅读器" not in snippet
    assert "______" not in snippet
    assert "去阅读" not in snippet
    assert snippet.count("詹老师") == 1
    assert snippet.count("我来预测下一代企业数字化架构") == 1
    assert "下一代企业数字化的核心趋势" in snippet


def test_empty_body_returns_empty_string():
    assert _make_snippet("") == ""
    assert _make_snippet(None) == ""  # type: ignore[arg-type]


def test_max_chars_cap_respected():
    """Long body truncates to max_chars + ellipsis."""
    long_body = "实际正文 " * 200
    snippet = _make_snippet(long_body, max_chars=50)
    assert len(snippet) <= 51  # 50 + ellipsis
    assert snippet.endswith("…")
