"""260530-card-render-direction-fix: unit tests for bilingual lang-direction
helpers in kb/export_knowledge_base.py.

Bug context: prior templates hard-assumed `article.title` is Chinese and
`article.title_translated` is English. RSS English sources (lang='en',
translated_lang='zh-CN') violated this — EN site showed Chinese translation,
zh-CN site showed English raw.

Fix: Python layer derives an effective source lang and pairs raw/translated
into title_zh/title_en (and snippet_zh/snippet_en) so templates just read
derived fields.
"""

from __future__ import annotations

import pytest

from kb.export_knowledge_base import (
    _effective_source_lang,
    _localize_pair,
)


class TestEffectiveSourceLang:
    def test_canonical_zh_cn_returns_zh_cn(self):
        assert _effective_source_lang("zh-CN", "wechat") == "zh-CN"
        assert _effective_source_lang("zh-CN", "rss") == "zh-CN"

    def test_canonical_en_returns_en(self):
        assert _effective_source_lang("en", "rss") == "en"
        assert _effective_source_lang("en", "wechat") == "en"

    def test_unknown_rss_falls_back_to_en(self):
        # Aliyun prod has 1426 RSS rows with lang='unknown'; user decision
        # 260530: rss → en, wechat → zh-CN (right >99% of the time).
        assert _effective_source_lang("unknown", "rss") == "en"

    def test_unknown_wechat_falls_back_to_zh_cn(self):
        assert _effective_source_lang("unknown", "wechat") == "zh-CN"

    def test_unknown_other_source_falls_back_to_zh_cn(self):
        assert _effective_source_lang("unknown", "web") == "zh-CN"
        assert _effective_source_lang("unknown", None) == "zh-CN"
        assert _effective_source_lang("unknown", "") == "zh-CN"


class TestLocalizePair:
    def test_zh_cn_source_zh_is_raw_en_is_translated(self):
        # WeChat article: raw is Chinese, translated is English.
        zh, en = _localize_pair("中文标题", "English title", "zh-CN")
        assert zh == "中文标题"
        assert en == "English title"

    def test_en_source_zh_is_translated_en_is_raw(self):
        # RSS English source: raw is English, translated is Chinese.
        zh, en = _localize_pair("English title", "中文翻译", "en")
        assert zh == "中文翻译"
        assert en == "English title"

    def test_zh_cn_source_with_no_translation_falls_back_to_raw(self):
        # Untranslated zh-CN row: en side falls back to raw zh.
        zh, en = _localize_pair("中文标题", None, "zh-CN")
        assert zh == "中文标题"
        assert en == "中文标题"

    def test_en_source_with_no_translation_falls_back_to_raw(self):
        # Untranslated en row: zh side falls back to raw en.
        zh, en = _localize_pair("English title", None, "en")
        assert zh == "English title"
        assert en == "English title"

    def test_empty_translation_falls_back(self):
        # Empty string is falsy in Python — fallback should still trigger.
        zh, en = _localize_pair("English title", "", "en")
        assert zh == "English title"
        assert en == "English title"


@pytest.mark.parametrize(
    "canonical,source,raw,translated,expected_zh,expected_en",
    [
        # zh-CN wechat (legacy primary path)
        ("zh-CN", "wechat", "中文", "Chinese", "中文", "Chinese"),
        # en rss (the bug case — must flip)
        ("en", "rss", "English", "中文翻译", "中文翻译", "English"),
        # unknown rss → en bucket
        ("unknown", "rss", "English raw", "中文 trans", "中文 trans", "English raw"),
        # unknown wechat → zh-CN bucket
        ("unknown", "wechat", "中文 raw", "English trans", "中文 raw", "English trans"),
        # untranslated en rss
        ("en", "rss", "English raw", None, "English raw", "English raw"),
    ],
)
def test_end_to_end_pairing(
    canonical, source, raw, translated, expected_zh, expected_en
):
    effective = _effective_source_lang(canonical, source)
    zh, en = _localize_pair(raw, translated, effective)
    assert zh == expected_zh
    assert en == expected_en
