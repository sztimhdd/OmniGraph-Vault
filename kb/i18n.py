"""I18N-03: Bilingual UI chrome strings via Jinja2 `t` filter.

Loads kb/locale/{zh-CN,en}.json once at module import. Templates use
`{{ 'nav.home' | t(lang) }}` — `lang` is passed explicitly from render context
(which sets it per-page based on `<html lang>` axis OR per-span when emitting
both languages inline).

Missing key behavior: return `key` literal + log WARN — visible in rendered
HTML for fast debugging. NOT raise.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from kb import config

logger = logging.getLogger(__name__)

_LOCALE_DIR = Path(__file__).parent / "locale"
_SUPPORTED_LANGS: tuple[str, ...] = ("zh-CN", "en")

# Locales loaded at import; treated as ship-time static. Restart process to reload.
# (REVISION 1 / Issue #7: documented design decision — locales are baked at SSG
# build time and do not change at runtime; lazy module-level cache is intentional.)
# Loaded once at import. dict[lang_code -> dict[key -> value]]
_LOCALES: dict[str, dict[str, str]] = {}


def load_locales() -> dict[str, dict[str, str]]:
    """Load all locale JSON files. Cached after first call."""
    if _LOCALES:
        return _LOCALES
    for lang in _SUPPORTED_LANGS:
        path = _LOCALE_DIR / f"{lang}.json"
        with open(path, encoding="utf-8") as f:
            _LOCALES[lang] = json.load(f)
    return _LOCALES


def validate_key_parity() -> bool:
    """Verify all locale files have IDENTICAL key sets. Build-time check.

    Raises:
        ValueError: with diff if any key is missing in any locale.
    """
    locales = load_locales()
    key_sets = {lang: set(d.keys()) for lang, d in locales.items()}
    all_keys = set().union(*key_sets.values())
    missing = {
        lang: sorted(all_keys - keys)
        for lang, keys in key_sets.items()
        if all_keys - keys
    }
    if missing:
        raise ValueError(f"Locale key parity violation: {missing}")
    return True


def t(key: str, lang: str | None = None) -> str:
    """Translate a dot-notation key. Returns localized string or key-literal fallback.

    Args:
        key: dot-notation key like 'nav.home'
        lang: language code 'zh-CN' or 'en'. Falls back to config.KB_DEFAULT_LANG
            if None or unsupported.

    Returns:
        Localized string from the appropriate locale JSON. Returns the key
        literal (e.g. 'nav.home') if not found, with a WARN log entry.
    """
    locales = load_locales()
    if lang is None or lang not in _SUPPORTED_LANGS:
        if lang is not None:
            logger.warning("Unsupported lang %r, falling back to %s", lang, config.KB_DEFAULT_LANG)
        lang = config.KB_DEFAULT_LANG
    # Final guard: if config.KB_DEFAULT_LANG is also unsupported, pick first supported
    if lang not in _SUPPORTED_LANGS:
        lang = _SUPPORTED_LANGS[0]

    translation = locales[lang].get(key)
    if translation is None:
        logger.warning("Missing translation key %r for lang %s", key, lang)
        return key
    return translation


def register_jinja2_filter(env: Any) -> None:
    """Register `t` as a Jinja2 filter on the given Environment.

    Usage in templates: `{{ 'nav.home' | t(lang) }}`
    """
    env.filters["t"] = t
