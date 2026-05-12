"""DATA-02: unit tests for kb.data.lang_detect.

Tests the pure-function language detector. No DB, no network.
"""
from __future__ import annotations

import pytest

from kb.data.lang_detect import (
    MIN_TEXT_LEN,
    ZH_THRESHOLD,
    chinese_char_ratio,
    detect_lang,
)


# --- chinese_char_ratio tests ---


def test_ratio_mixed_text_hand_computed():
    """Mixed Chinese + English text — exact hand-computed ratio.

    Text: '人工智能 Agent 框架对比 LangChain CrewAI'
    Chinese chars: 人工智能 + 框架对比 = 8 chars
    Total chars: 32 (including spaces)
    Ratio: 8 / 32 = 0.25
    """
    text = "人工智能 Agent 框架对比 LangChain CrewAI"
    ratio = chinese_char_ratio(text)
    assert ratio == pytest.approx(8 / 32)


def test_ratio_pure_english_zero():
    """Pure English text returns 0.0."""
    assert chinese_char_ratio("LangGraph and CrewAI compared") == 0.0


def test_ratio_empty_string_zero():
    """Empty string returns 0.0 — no division-by-zero."""
    assert chinese_char_ratio("") == 0.0


def test_ratio_pure_chinese_one():
    """Pure Chinese text returns 1.0."""
    assert chinese_char_ratio("纯中文文章" * 100) == 1.0


# --- detect_lang tests ---


def test_detect_long_english():
    """Long English text → 'en'."""
    text = "LangGraph framework architecture deep dive ..." * 20
    assert detect_lang(text) == "en"


def test_detect_long_chinese():
    """Long Chinese text → 'zh-CN'."""
    text = "人工智能 Agent 框架解析 ..." * 30
    assert detect_lang(text) == "zh-CN"


def test_detect_short_text_unknown():
    """Text < MIN_TEXT_LEN chars → 'unknown'."""
    assert detect_lang("short text") == "unknown"


def test_detect_empty_unknown():
    """Empty string → 'unknown'."""
    assert detect_lang("") == "unknown"


def test_detect_long_ascii_en():
    """Long string of 'a' (no Chinese) → 'en'."""
    assert detect_lang("a" * 250) == "en"


def test_detect_long_chinese_only_zh():
    """Long string of 中 (100% Chinese) → 'zh-CN'."""
    assert detect_lang("中" * 250) == "zh-CN"


# --- constants sanity (locked thresholds, do not drift) ---


def test_min_text_len_constant():
    assert MIN_TEXT_LEN == 200


def test_zh_threshold_constant():
    assert ZH_THRESHOLD == 0.30
