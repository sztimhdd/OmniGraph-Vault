"""Unit tests for quick-260519-s65 long_form prompt template enforcement.

Pure-function tests for `_wrap_question_for_mode` (mode='long_form') and the
module-level `_LONG_FORM_PROMPT_TEMPLATE_ZH/EN` constants — no DB, no LightRAG.

Behaviors covered:
    1. ZH long_form template contains `/article/` citation directive
    2. EN long_form template contains `/article/` citation directive
    3. ZH long_form template contains `/static/img/` image-path directive
    4. EN long_form template contains `/static/img/` image-path directive
    5. ZH long_form template explicitly forbids `localhost:8765`
    6. EN long_form template explicitly forbids `localhost:8765`
    7. `_wrap_question_for_mode(mode='long_form', lang='zh')` selects ZH template
    8. `_wrap_question_for_mode(mode='long_form', lang='en')` selects EN template
    9. .format(question=...) leaves literal {hash} for the LLM (doubled-brace trick)
"""
from __future__ import annotations

from kb.services.synthesize import (
    _LONG_FORM_PROMPT_TEMPLATE_EN,
    _LONG_FORM_PROMPT_TEMPLATE_ZH,
    _wrap_question_for_mode,
)


def test_long_form_zh_template_has_article_citation_directive() -> None:
    assert "articles/" in _LONG_FORM_PROMPT_TEMPLATE_ZH, (
        "ZH long_form template must instruct /article/{hash}.html citation format"
    )


def test_long_form_en_template_has_article_citation_directive() -> None:
    assert "articles/" in _LONG_FORM_PROMPT_TEMPLATE_EN, (
        "EN long_form template must instruct /article/{hash}.html citation format"
    )


def test_long_form_zh_template_has_static_img_directive() -> None:
    assert "/static/img/" in _LONG_FORM_PROMPT_TEMPLATE_ZH, (
        "ZH long_form template must instruct /static/img/ image-path format"
    )


def test_long_form_en_template_has_static_img_directive() -> None:
    assert "/static/img/" in _LONG_FORM_PROMPT_TEMPLATE_EN, (
        "EN long_form template must instruct /static/img/ image-path format"
    )


def test_long_form_zh_template_forbids_localhost_8765() -> None:
    """Template must explicitly mention `localhost:8765` as a forbidden literal."""
    assert "localhost:8765" in _LONG_FORM_PROMPT_TEMPLATE_ZH, (
        "ZH long_form template must explicitly forbid `localhost:8765` "
        "(legacy IMAGE_URL_DIRECTIVE prefix from kg_synthesize.py)"
    )


def test_long_form_en_template_forbids_localhost_8765() -> None:
    """Template must explicitly mention `localhost:8765` as a forbidden literal."""
    assert "localhost:8765" in _LONG_FORM_PROMPT_TEMPLATE_EN, (
        "EN long_form template must explicitly forbid `localhost:8765` "
        "(legacy IMAGE_URL_DIRECTIVE prefix from kg_synthesize.py)"
    )


def test_wrap_question_long_form_zh_uses_zh_template() -> None:
    result = _wrap_question_for_mode("Agent 框架有哪些?", "zh", "long_form")
    assert "Agent 框架有哪些?" in result
    assert "请用中文回答" in result
    assert "articles/" in result
    assert "/static/img/" in result


def test_wrap_question_long_form_en_uses_en_template() -> None:
    result = _wrap_question_for_mode("What is an Agent?", "en", "long_form")
    assert "What is an Agent?" in result
    assert "Please answer in English." in result
    assert "articles/" in result
    assert "/static/img/" in result


def test_long_form_template_constants_use_doubled_braces_for_format() -> None:
    """Templates use {{hash}}/{{n}} so str.format(question=...) leaves the
    literal `{hash}` / `{n}` for the LLM — not a Python format-key error."""
    zh = _LONG_FORM_PROMPT_TEMPLATE_ZH.format(question="test")
    en = _LONG_FORM_PROMPT_TEMPLATE_EN.format(question="test")
    assert "{hash}" in zh, "ZH template after format() should still contain literal {hash} for LLM"
    assert "{hash}" in en, "EN template after format() should still contain literal {hash} for LLM"
