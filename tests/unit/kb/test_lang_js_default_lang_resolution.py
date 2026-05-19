"""kb-v2.2-7 Wave 5: behavioral tests for kb/static/lang.js.

Real `lang.js` is executed inside a Node `vm` sandbox via the
`_lang_js_runner.js` driver in this directory. Mocks live ONLY at the
host-language boundary (window/document/navigator) — the unit under test
runs unmodified, so refactors to lang.js's internal helpers do NOT break
tests as long as observable behavior holds.

Mandatory cases (per orchestrator Wave 5 GO):
  1. First-visit + window.KB_DEFAULT_LANG='en' + browser=ja-JP
     → writes cookie='en' + applyLang('en')
  2. First-visit + window.KB_DEFAULT_LANG='xx-INVALID' + browser=ja-JP
     → falls back to 'zh-CN' + writes cookie='zh-CN'
  3. First-visit + window.KB_DEFAULT_LANG undefined + browser=ja-JP
     → falls back to 'zh-CN' (script-level safe default)
  4. Existing cookie wins — window.KB_DEFAULT_LANG ignored when cookie set
  5. applyLang sets <html lang> even with stray data-fixed-lang="true"
     (regression guard against the deleted Wave 5 guard branch sneaking back)

Skill(skill="writing-tests") — invoked + Testing Trophy applied
(integration depth via real JS execution; minimal mocking).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


_RUNNER_JS = Path(__file__).parent / "_lang_js_runner.js"


def _node_available() -> bool:
    return shutil.which("node") is not None


# Skip the whole module cleanly if Node is missing — the existing pytest
# integration suites do not require Node either, so this stays a soft skip
# rather than a hard failure on minimal environments.
pytestmark = pytest.mark.skipif(
    not _node_available(),
    reason="Node.js not installed; lang.js behavioral tests need a JS engine",
)


def _run_lang_js(**params) -> dict:
    """Execute lang.js inside the Node sandbox; return captured side effects.

    Returns a dict with keys:
      - cookie_writes: list[str]    — every value assigned to document.cookie
      - set_attrs:     list[[k,v]]  — every documentElement.setAttribute call
      - final_lang_attr: str | None — last 'lang' value set on <html>
      - final_cookie:  str          — final document.cookie state
    """
    proc = subprocess.run(
        ["node", str(_RUNNER_JS)],
        input=json.dumps(params),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node runner failed (rc={proc.returncode}):\n"
            f"  stderr: {proc.stderr.strip()}\n"
            f"  stdout: {proc.stdout.strip()}"
        )
    return json.loads(proc.stdout)


def _cookie_value_in_writes(writes: list[str], name: str) -> str | None:
    """Return the last value written for cookie `name`, or None."""
    last = None
    for w in writes:
        head = w.split(";")[0].strip()
        if head.startswith(name + "="):
            last = head.split("=", 1)[1]
    return last


# ---- Case 1: KB_DEFAULT_LANG='en' first-visit persistence ------------------


def test_first_visit_with_kb_default_lang_en_writes_en_cookie_and_sets_lang_en():
    """KB_DEFAULT_LANG='en' + cookie absent + browser ja-JP (no zh/en match)
    → DEFAULT_LANG='en' is the cascade fallback; first-visit persists it.
    """
    result = _run_lang_js(
        window_kb_default_lang="en",
        navigator_languages=["ja-JP"],   # neither zh nor en — exits browser-detect via fallback
        initial_cookie="",
        location_search="",
        data_fixed_lang_on_html=False,
    )
    assert result["final_lang_attr"] == "en", (
        f"<html lang> should be 'en'; got {result['final_lang_attr']!r}. "
        f"setAttribute calls: {result['set_attrs']}"
    )
    assert _cookie_value_in_writes(result["cookie_writes"], "kb_lang") == "en", (
        f"first visit must persist 'en' to kb_lang cookie; writes: {result['cookie_writes']}"
    )


# ---- Case 2: invalid KB_DEFAULT_LANG → zh-CN fallback ---------------------


def test_first_visit_with_invalid_kb_default_lang_falls_back_to_zh_cn():
    """Invalid KB_DEFAULT_LANG ('xx-INVALID') + cookie absent + browser ja-JP
    → DEFAULT_LANG validation rejects invalid value; falls back to 'zh-CN'.
    """
    result = _run_lang_js(
        window_kb_default_lang="xx-INVALID",
        navigator_languages=["ja-JP"],
        initial_cookie="",
        location_search="",
        data_fixed_lang_on_html=False,
    )
    assert result["final_lang_attr"] == "zh-CN", (
        f"<html lang> should fall back to 'zh-CN' on invalid KB_DEFAULT_LANG; "
        f"got {result['final_lang_attr']!r}"
    )
    assert _cookie_value_in_writes(result["cookie_writes"], "kb_lang") == "zh-CN", (
        f"first visit must persist 'zh-CN' fallback to cookie; writes: {result['cookie_writes']}"
    )


# ---- Case 3: KB_DEFAULT_LANG undefined → zh-CN ----------------------------


def test_first_visit_with_undefined_kb_default_lang_falls_back_to_zh_cn():
    """window.KB_DEFAULT_LANG is undefined + cookie absent + browser ja-JP
    → script-level safe default 'zh-CN' applies.
    """
    result = _run_lang_js(
        # window_kb_default_lang OMITTED — runner leaves the property unset
        navigator_languages=["ja-JP"],
        initial_cookie="",
        location_search="",
        data_fixed_lang_on_html=False,
    )
    assert result["final_lang_attr"] == "zh-CN"
    assert _cookie_value_in_writes(result["cookie_writes"], "kb_lang") == "zh-CN"


# ---- Case 4: existing cookie wins (user preference priority) ---------------


def test_existing_cookie_wins_over_kb_default_lang():
    """Cookie kb_lang=en already set + window.KB_DEFAULT_LANG='zh-CN'
    → cookie value wins; KB_DEFAULT_LANG is ignored on subsequent visits.
    """
    result = _run_lang_js(
        window_kb_default_lang="zh-CN",   # would override if cookie absent
        navigator_languages=["ja-JP"],
        initial_cookie="kb_lang=en",
        location_search="",
        data_fixed_lang_on_html=False,
    )
    assert result["final_lang_attr"] == "en", (
        "Existing kb_lang=en cookie must win over window.KB_DEFAULT_LANG='zh-CN' "
        "(user preference priority). Got: " + repr(result["final_lang_attr"])
    )


def test_existing_cookie_does_not_trigger_first_visit_write():
    """Pre-existing cookie path must NOT re-write the cookie (no churn)."""
    result = _run_lang_js(
        window_kb_default_lang="zh-CN",
        navigator_languages=["ja-JP"],
        initial_cookie="kb_lang=en",
        location_search="",
        data_fixed_lang_on_html=False,
    )
    # No new write for kb_lang (the cookie was honored, not re-set).
    kb_lang_writes = [w for w in result["cookie_writes"] if w.split(";")[0].startswith("kb_lang=")]
    assert kb_lang_writes == [], (
        f"existing cookie path should NOT churn the cookie; got writes: {kb_lang_writes}"
    )


# ---- Case 5: data-fixed-lang guard removed (regression guard) -------------


def test_apply_lang_sets_html_lang_even_with_stray_data_fixed_lang_attribute():
    """Wave 5 deleted the `if html.getAttribute('data-fixed-lang') !== 'true'`
    guard. Even if a stray <html data-fixed-lang="true"> attribute appears
    (e.g. cached HTML from a pre-Wave 4 deploy), applyLang must still set
    `<html lang>` so the toggle button + dual-span rendering work.
    """
    result = _run_lang_js(
        window_kb_default_lang="en",
        navigator_languages=["ja-JP"],
        initial_cookie="",
        location_search="",
        data_fixed_lang_on_html=True,    # <html data-fixed-lang="true"> present
    )
    # Despite the legacy attribute, lang must be set.
    assert result["final_lang_attr"] == "en", (
        "applyLang must set <html lang> unconditionally — Wave 5 guard removal. "
        f"setAttribute calls: {result['set_attrs']}"
    )
    # Defensive: the lang setAttribute call must actually appear in the trace.
    lang_calls = [v for k, v in result["set_attrs"] if k == "lang"]
    assert lang_calls and lang_calls[-1] == "en", (
        "expected at least one setAttribute('lang', ...) call; "
        f"got set_attrs={result['set_attrs']}"
    )


# ---- Source-level guard: deleted helpers do not return ---------------------
#
# In addition to the runtime tests above, assert that the lang.js source
# does not contain the deleted `data-fixed-lang` branch. This is a cheap
# regression guard against the guard re-appearing in a later edit.


def test_lang_js_source_no_data_fixed_lang_branch():
    """lang.js source must not have an ACTIVE data-fixed-lang branch — Wave 5
    deleted the runtime guard. A historical mention in a comment block is OK
    (documents what was removed); only the runtime check is forbidden.
    """
    src = (Path(__file__).resolve().parents[3] / "kb" / "static" / "lang.js").read_text(encoding="utf-8")
    # Strip /* ... */ block comments + // line comments before scanning so we
    # only assert against runtime code paths, not documentation.
    import re
    code_only = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    code_only = re.sub(r"//[^\n]*", "", code_only)
    forbidden = [
        "getAttribute('data-fixed-lang')",
        'getAttribute("data-fixed-lang")',
    ]
    for needle in forbidden:
        assert needle not in code_only, (
            f"kb/static/lang.js must not run {needle!r} after Wave 5 — "
            "the guard branch was deleted per locked decision A1."
        )
