"""DATA-02 v2: unit tests for kb.data.lang_detect (title-first CJK rule).

Tests the pure-function language detector. No DB, no network.

Skill(skill="python-patterns") — CJK regex + classification rule; pure functions
Skill(skill="writing-tests") — Testing Trophy unit > integration; parametrize for clarity

9 required cases (spec from kb-v2.1-7 PLAN):
1. CN title + EN body → zh-CN
2. EN title + CN body → zh-CN
3. All-English → en
4. Short English body → unknown
5. Japanese kana title → en (NOT zh-CN)
6. Empty title + empty body → unknown
7. Korean Hangul title → en (NOT zh-CN)
8. Mixed title with single CJK char → zh-CN
9. Extension-A char (U+3400) in title → zh-CN
"""
from __future__ import annotations

import pytest

from kb.data.lang_detect import detect_lang, has_cjk


# ---------------------------------------------------------------------------
# has_cjk unit tests
# ---------------------------------------------------------------------------


def test_has_cjk_with_chinese_char():
    """String containing a Han ideograph returns True."""
    assert has_cjk("如何用") is True


def test_has_cjk_with_kana_returns_false():
    """Pure katakana/hiragana does NOT trigger has_cjk."""
    assert has_cjk("カタカナのテスト") is False


def test_has_cjk_with_hangul_returns_false():
    """Pure Hangul does NOT trigger has_cjk."""
    assert has_cjk("한국어 테스트") is False


def test_has_cjk_with_extension_a_char():
    """Extension A char U+3400 (㐀) triggers has_cjk."""
    assert has_cjk("㐀") is True


def test_has_cjk_empty_returns_false():
    assert has_cjk("") is False


def test_has_cjk_none_returns_false():
    assert has_cjk(None) is False


# ---------------------------------------------------------------------------
# detect_lang: 9 required spec cases
# ---------------------------------------------------------------------------


# Case 1: Chinese title + English-heavy body → zh-CN
def test_chinese_title_english_body_returns_zh_cn():
    """Title has CJK → zh-CN even when body is English-heavy."""
    title = "如何用 LightRAG 构建知识图谱"
    body = "Use embedding vector store and entity extraction. " * 10  # all English, >50 chars
    assert detect_lang(title, body) == "zh-CN"


# Case 2: English title + Chinese body → zh-CN
def test_english_title_chinese_body_returns_zh_cn():
    """Title has no CJK but body has CJK → zh-CN."""
    title = "LightRAG Tutorial"
    body = "中" * 200  # pure Chinese body
    assert detect_lang(title, body) == "zh-CN"


# Case 3: All-English → en
def test_all_english_returns_en():
    """Long all-English title + body → en."""
    title = "How to build a knowledge base"
    body = "a " * 200  # long all-English body (>50 chars)
    assert detect_lang(title, body) == "en"


# Case 4: Short English body → unknown
def test_short_english_body_returns_unknown():
    """Title with no CJK + body shorter than 50 chars → unknown."""
    title = "Hi"
    body = "short"  # len("short") == 5 < 50
    assert detect_lang(title, body) == "unknown"


# Case 5: Japanese kana-only title → en (NOT zh-CN)
def test_japanese_kana_title_returns_en_not_zh_cn():
    """Pure katakana title MUST NOT classify as zh-CN."""
    title = "カタカナのテスト"  # pure katakana
    body = "a " * 200  # long English body
    result = detect_lang(title, body)
    assert result != "zh-CN"
    assert result == "en"


# Case 6: Empty title and empty body → unknown
def test_empty_title_and_body_returns_unknown():
    """Both title and body empty → unknown."""
    assert detect_lang("", "") == "unknown"


# Case 7: Korean Hangul-only title → en (NOT zh-CN)
def test_korean_hangul_title_returns_en_not_zh_cn():
    """Pure Hangul title MUST NOT classify as zh-CN."""
    title = "한국어 테스트"  # pure Hangul
    body = "a " * 200  # long English body
    result = detect_lang(title, body)
    assert result != "zh-CN"
    assert result == "en"


# Case 8: Mixed title with single CJK char → zh-CN
def test_mixed_title_single_cjk_returns_zh_cn():
    """Single Han ideograph in otherwise-English title triggers zh-CN."""
    title = "Build a 知识 graph"
    body = "a " * 200  # all English body
    assert detect_lang(title, body) == "zh-CN"


# Case 9: CJK Extension A char (U+3400) in title → zh-CN
def test_extension_a_cjk_in_title_returns_zh_cn():
    """Extension A character U+3400 (㐀) in title → zh-CN."""
    title = "Test 㐀 char"  # U+3400 is 㐀, Extension A
    body = "some text " * 20
    assert detect_lang(title, body) == "zh-CN"


# ---------------------------------------------------------------------------
# detect_lang: None input handling
# ---------------------------------------------------------------------------


def test_detect_lang_none_title_and_body_returns_unknown():
    """None title and None body → unknown (no error)."""
    assert detect_lang(None, None) == "unknown"


def test_detect_lang_none_title_chinese_body():
    """None title, Chinese body → zh-CN (body CJK path)."""
    assert detect_lang(None, "中" * 200) == "zh-CN"
