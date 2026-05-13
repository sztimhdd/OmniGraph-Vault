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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _parse_any_datetime(value: str | int | None) -> datetime | None:
    """Best-effort parse of ISO 8601 / RFC 822 / Unix epoch into UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(value).strip()
    if not s:
        return None
    try:
        # ISO 8601 — support trailing Z
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    try:
        # RFC 822 (e.g. "Wed, 04 Sep 2024 04:31:00 +0000")
        dt = parsedate_to_datetime(s)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def humanize_date(value: str | int | None, lang: str = "zh-CN",
                  now: datetime | None = None) -> str:
    """RFC 822 / ISO 8601 / Unix epoch -> human-readable string per locale.

    < 1 day:  "今天" / "Today"
    < 7 days: "X 天前" / "X days ago"
    else:     "2024 年 9 月 4 日" / "Sep 4, 2024"

    Falls back to the original string on parse failure (never raises).
    `now` is injectable for deterministic tests.
    """
    if value is None or value == "":
        return ""
    dt = _parse_any_datetime(value)
    if dt is None:
        return str(value)
    ref = now or datetime.now(tz=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    delta_days = (ref.date() - dt.date()).days
    is_zh = (lang or "").startswith("zh")
    if delta_days <= 0:
        return "今天" if is_zh else "Today"
    if delta_days < 7:
        return f"{delta_days} 天前" if is_zh else f"{delta_days} day{'s' if delta_days != 1 else ''} ago"
    if is_zh:
        return f"{dt.year} 年 {dt.month} 月 {dt.day} 日"
    return f"{_MONTHS_EN[dt.month - 1]} {dt.day}, {dt.year}"


def humanize_filter(value: str | int | None, lang: str = "zh-CN") -> str:
    """Jinja2 filter wrapper for humanize_date."""
    return humanize_date(value, lang)


def register_jinja2_filter(env: Any) -> None:
    """Register `t` and `humanize` as Jinja2 filters on the given Environment.

    Usage in templates:
      `{{ 'nav.home' | t(lang) }}`
      `{{ article.update_time | humanize('zh-CN') }}`
    """
    env.filters["t"] = t
    env.filters["humanize"] = humanize_filter
