"""Unit tests for kb-v2.2-4 QA prompt template enforcement.

Pure-function tests for _wrap_question_for_mode — no DB, no LightRAG.

Behaviors covered:
    1. mode='qa', lang='zh' → _QA_PROMPT_TEMPLATE_ZH wrapping question
    2. mode='qa', lang='en' → _QA_PROMPT_TEMPLATE_EN wrapping question
    3. mode='long_form', lang='zh' → _LONG_FORM_PROMPT_TEMPLATE_ZH unchanged (regression)
    4. mode='qa' result contains /article/ citation format instruction
    5. mode='qa' result contains the question verbatim
"""
from __future__ import annotations

from kb.services.synthesize import (
    _QA_PROMPT_TEMPLATE_EN,
    _QA_PROMPT_TEMPLATE_ZH,
    _wrap_question_for_mode,
)


def test_wrap_question_qa_zh_uses_zh_template() -> None:
    result = _wrap_question_for_mode("Agent 框架有哪些?", "zh", "qa")
    assert "Agent 框架有哪些?" in result
    assert "请用中文回答" in result
    assert "articles/" in result, "ZH QA template must instruct articles/{hash}.html citation format"


def test_wrap_question_qa_en_uses_en_template() -> None:
    result = _wrap_question_for_mode("What is LightRAG?", "en", "qa")
    assert "What is LightRAG?" in result
    assert "Please answer in English." in result
    assert "articles/" in result, "EN QA template must instruct articles/{hash}.html citation format"


def test_wrap_question_long_form_unchanged() -> None:
    """Regression: long_form mode must be unaffected by FU-1 QA template changes."""
    result = _wrap_question_for_mode("RAG 发展趋势", "zh", "long_form")
    assert "RAG 发展趋势" in result
    assert "1500-3000" in result, "long_form ZH template should retain word-count instruction"
    assert "请用中文回答" in result


def test_wrap_question_qa_template_contains_image_instruction() -> None:
    """QA template must instruct LLM to include ![alt](URL) for image references."""
    zh = _wrap_question_for_mode("q", "zh", "qa")
    en = _wrap_question_for_mode("q", "en", "qa")
    assert "![" in zh or "alt" in zh, "ZH template should mention image syntax"
    assert "![" in en or "alt" in en, "EN template should mention image syntax"


def test_qa_template_constants_use_doubled_braces_for_hash() -> None:
    """Templates use {{hash}} so str.format(question=...) leaves literal {hash}
    for the LLM — not a Python format-key error."""
    assert "{hash}" in _QA_PROMPT_TEMPLATE_ZH.format(question="test"), (
        "ZH template after format() should still contain literal {hash} for LLM"
    )
    assert "{hash}" in _QA_PROMPT_TEMPLATE_EN.format(question="test"), (
        "EN template after format() should still contain literal {hash} for LLM"
    )
