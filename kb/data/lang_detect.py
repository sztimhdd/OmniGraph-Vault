"""DATA-02: Chinese vs English language detection by char ratio.

Algorithm (locked in CONTEXT.md):
- Chinese char ratio > 30% → 'zh-CN'
- Chinese char ratio <= 30% → 'en'
- Text length < 200 chars → 'unknown' (insufficient sample)

Pure function, no DB, no network. The driver script that walks the DB
and updates rows lives in kb/scripts/detect_article_lang.py (plan kb-1-04).
"""
from __future__ import annotations

from typing import Literal

LangCode = Literal["zh-CN", "en", "unknown"]

# CJK Unified Ideographs basic block. 0x4e00-0x9fff covers 99% of modern
# Chinese articles in this corpus. Extension blocks (3400-4dbf, 20000-2a6df)
# are rare in tech KOL writing — accept the ~1% false-negative rate over
# adding `unicodedata` import + slower per-char lookup.
_CJK_LO = "一"
_CJK_HI = "鿿"

MIN_TEXT_LEN: int = 200
ZH_THRESHOLD: float = 0.30


def chinese_char_ratio(text: str) -> float:
    """Return ratio of Chinese chars in text. Empty string → 0.0 (no div-by-zero)."""
    if not text:
        return 0.0
    cjk_count = sum(1 for c in text if _CJK_LO <= c <= _CJK_HI)
    return cjk_count / len(text)


def detect_lang(text: str) -> LangCode:
    """Detect language by Chinese char ratio.

    Returns:
        'zh-CN' if Chinese char ratio > 30% AND len(text) >= 200
        'en' if Chinese char ratio <= 30% AND len(text) >= 200
        'unknown' if len(text) < 200
    """
    if len(text) < MIN_TEXT_LEN:
        return "unknown"
    return "zh-CN" if chinese_char_ratio(text) > ZH_THRESHOLD else "en"
