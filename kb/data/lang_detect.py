"""DATA-02 v2: Title-first CJK language detection.

Rule priority order (applied in sequence, first match wins):
1. Title contains ANY CJK Unified Ideograph (U+4E00–U+9FFF or U+3400–U+4DBF) → 'zh-CN'
2. Title has NO CJK, but body contains ANY CJK Unified Ideograph → 'zh-CN'
3. Body < 50 chars AND no CJK in title → 'unknown' (insufficient sample)
4. Default → 'en'

CJK scope: Han Unified Ideographs (U+4E00–U+9FFF) + CJK Extension A (U+3400–U+4DBF).
Explicitly EXCLUDES Japanese kana (U+3040–U+30FF) and Korean Hangul (U+AC00–U+D7AF),
so a pure-kana or pure-Hangul title does NOT classify as 'zh-CN'.

Pure function, no DB, no network. The driver script that walks the DB and updates
rows lives in kb/scripts/detect_article_lang.py.
"""
from __future__ import annotations

import re
from typing import Literal

LangCode = Literal["zh-CN", "en", "unknown"]

# Matches CJK Unified Ideographs (U+4E00–U+9FFF, 一 to 鿿) and
# CJK Extension A (U+3400–U+4DBF, 㐀 to 䶿).
# Kana (U+3040–U+30FF) and Hangul (U+AC00–U+D7AF) are NOT in this range.
_CJK_PATTERN: re.Pattern[str] = re.compile(r"[一-鿿㐀-䶿]")

_MIN_BODY_LEN: int = 50


def has_cjk(text: str | None) -> bool:
    """Return True if text contains at least one CJK Unified Ideograph.

    Args:
        text: The string to test. None or empty string → False.

    Returns:
        True if any CJK Unified Ideograph (U+4E00–U+9FFF or U+3400–U+4DBF)
        is found; False otherwise. Japanese kana and Korean Hangul do not
        trigger True.
    """
    if not text:
        return False
    return bool(_CJK_PATTERN.search(text))


def detect_lang(title: str | None, body: str | None) -> LangCode:
    """Detect language using title-first CJK rule.

    Args:
        title: Article title (may be None or empty).
        body: Article body text (may be None or empty).

    Returns:
        'zh-CN' if title contains any CJK Unified Ideograph.
        'zh-CN' if title has no CJK but body contains any CJK Unified Ideograph.
        'unknown' if body is shorter than 50 chars and title has no CJK.
        'en' otherwise (default).
    """
    if has_cjk(title):
        return "zh-CN"
    body_text = body or ""
    if has_cjk(body_text):
        return "zh-CN"
    if len(body_text) < _MIN_BODY_LEN:
        return "unknown"
    return "en"
