"""Locale key tests for kb-3 (qa.* + search.* additions per UI-SPEC §5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LOCALE_DIR = REPO / "kb" / "locale"

NEW_KB3_KEYS = [
    "qa.state.submitting",
    "qa.state.polling",
    "qa.state.streaming",
    "qa.state.error.network",
    "qa.state.error.server",
    "qa.state.timeout.message",
    "qa.fallback.label",
    "qa.fallback.explainer",
    "qa.sources.title",
    "qa.entities.title",
    "qa.feedback.prompt",
    "qa.feedback.thanks_up",
    "qa.feedback.thanks_down",
    "qa.retry.button",
    "qa.question.echo_label",
    "search.results.empty",
    "search.results.loading",
    "search.results.error",
    "search.results.view_all",
    "search.results.count",
]


def _load(lang: str) -> dict:
    return json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def _resolve(d: dict, dotted_key: str) -> str | None:
    """Resolve 'a.b.c' against either flat or nested dict. Returns None if missing."""
    if dotted_key in d:
        return d[dotted_key]
    cur = d
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, str) else None


@pytest.mark.parametrize("key", NEW_KB3_KEYS)
def test_zh_cn_has_key(key):
    data = _load("zh-CN")
    val = _resolve(data, key)
    assert val is not None and val.strip() != "", f"zh-CN missing key: {key}"


@pytest.mark.parametrize("key", NEW_KB3_KEYS)
def test_en_has_key(key):
    data = _load("en")
    val = _resolve(data, key)
    assert val is not None and val.strip() != "", f"en missing key: {key}"


def test_zh_cn_and_en_key_sets_symmetric():
    """Either flat or nested — both languages must have all NEW_KB3_KEYS."""
    zh = _load("zh-CN")
    en = _load("en")
    for k in NEW_KB3_KEYS:
        assert _resolve(zh, k) is not None, f"zh-CN missing: {k}"
        assert _resolve(en, k) is not None, f"en missing: {k}"


def test_count_template_preserves_placeholder():
    """search.results.count must contain '{n}' placeholder for runtime substitution."""
    zh = _load("zh-CN")
    en = _load("en")
    assert "{n}" in _resolve(zh, "search.results.count")
    assert "{n}" in _resolve(en, "search.results.count")


def test_existing_kb1_kb2_keys_preserved():
    """Spot-check: a few kb-1 / kb-2 anchor keys still resolve (additive change)."""
    zh = _load("zh-CN")
    for anchor in ("nav.home", "nav.articles", "nav.ask", "site.brand"):
        # At least one of these should resolve (kb-1 baseline keys)
        if _resolve(zh, anchor) is not None:
            return
    pytest.fail("None of the kb-1 anchor keys resolved — possible regression")


# ---- kb-3-03 Task 2: icon presence tests ----

ICONS_PATH = REPO / "kb" / "templates" / "_icons.html"


def test_chat_bubble_question_icon_added():
    text = ICONS_PATH.read_text(encoding="utf-8")
    assert "name == 'chat-bubble-question'" in text


def test_lightning_bolt_icon_added():
    text = ICONS_PATH.read_text(encoding="utf-8")
    assert "name == 'lightning-bolt'" in text


def test_icons_html_macro_still_valid_jinja():
    """Render a smoke template that calls icon('chat-bubble-question') and icon('lightning-bolt')."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(REPO / "kb" / "templates")))
    # Simple inline template that imports the macro and invokes both new icons
    tmpl = env.from_string(
        "{% from '_icons.html' import icon %}"
        "[A]{{ icon('chat-bubble-question') }}"
        "[B]{{ icon('lightning-bolt') }}"
        "[C]{{ icon('home') }}"  # smoke: existing icon still works
    )
    out = tmpl.render()
    assert "[A]<svg" in out and "[B]<svg" in out and "[C]<svg" in out
    # Crude content check: the new bolt path uses our specific path data
    assert "13 2L4.5 13.5" in out  # lightning-bolt path data
