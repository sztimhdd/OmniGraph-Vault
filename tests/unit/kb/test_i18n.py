"""I18N-03: tests for kb.i18n bilingual chrome-string filter.

Covers all 8 behaviors specified in plan kb-1-03 Task 2:
1. zh-CN lookup
2. en lookup
3. missing key returns key literal + WARN log
4. None lang defaults to KB_DEFAULT_LANG (zh-CN)
5. unsupported lang falls back to KB_DEFAULT_LANG + WARN log
6. validate_key_parity returns True on parity, raises ValueError on mismatch
7. register_jinja2_filter wires `t` filter usable in templates
8. load_locales returns dict[lang_code -> dict[key -> value]]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_locales_cache():
    """Clear the module-level locale cache between tests so monkeypatched
    locale dirs in test 6 take effect."""
    import kb.i18n
    kb.i18n._LOCALES.clear()
    yield
    kb.i18n._LOCALES.clear()


def test_t_zh_cn_returns_chinese_string():
    from kb.i18n import t
    assert t("nav.home", "zh-CN") == "首页"


def test_t_en_returns_english_string():
    from kb.i18n import t
    assert t("nav.home", "en") == "Home"


def test_t_missing_key_returns_key_literal_and_logs_warn(caplog):
    from kb.i18n import t
    with caplog.at_level(logging.WARNING, logger="kb.i18n"):
        result = t("nonexistent.key", "en")
    assert result == "nonexistent.key"
    assert any("nonexistent.key" in rec.message for rec in caplog.records)


def test_t_no_lang_defaults_to_kb_default_lang():
    """KB_DEFAULT_LANG is 'zh-CN' (kb/config.py), so no-lang call returns Chinese."""
    from kb.i18n import t
    assert t("nav.home") == "首页"


def test_t_unsupported_lang_falls_back_and_logs_warn(caplog):
    """Unsupported lang 'fr' → fall back to KB_DEFAULT_LANG ('zh-CN') + WARN."""
    from kb.i18n import t
    with caplog.at_level(logging.WARNING, logger="kb.i18n"):
        result = t("nav.home", "fr")
    assert result == "首页"
    assert any("fr" in rec.message for rec in caplog.records)


def test_validate_key_parity_true_on_match_and_raises_on_mismatch(tmp_path, monkeypatch):
    """validate_key_parity returns True on parity; ValueError listing the diff on mismatch."""
    import kb.i18n

    # First: real locale files have parity → True
    assert kb.i18n.validate_key_parity() is True

    # Second: inject mismatched locale dir → ValueError
    locale_dir = tmp_path / "locale"
    locale_dir.mkdir()
    (locale_dir / "zh-CN.json").write_text(
        json.dumps({"nav.home": "首页", "nav.articles": "文章"}),
        encoding="utf-8",
    )
    (locale_dir / "en.json").write_text(
        json.dumps({"nav.home": "Home"}),  # missing nav.articles
        encoding="utf-8",
    )
    monkeypatch.setattr(kb.i18n, "_LOCALE_DIR", locale_dir)
    kb.i18n._LOCALES.clear()

    with pytest.raises(ValueError, match="parity"):
        kb.i18n.validate_key_parity()


def test_register_jinja2_filter_renders_in_template():
    from jinja2 import Environment

    from kb.i18n import register_jinja2_filter

    env = Environment(autoescape=False)
    register_jinja2_filter(env)
    tmpl = env.from_string("{{ 'nav.home' | t('en') }}")
    assert tmpl.render() == "Home"


def test_load_locales_returns_both_languages():
    from kb.i18n import load_locales

    locales = load_locales()
    assert "zh-CN" in locales
    assert "en" in locales
    assert locales["zh-CN"]["nav.home"] == "首页"
    assert locales["en"]["nav.home"] == "Home"
