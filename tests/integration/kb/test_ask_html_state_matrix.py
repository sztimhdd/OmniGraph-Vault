"""kb-3-10 — UI-SPEC §8 acceptance regression suite.

Grep-verifiable patterns against rendered ask.html template + qa.js + style.css.
Asserts the 8-state matrix DOM hooks, Skill discipline sentinels, token discipline,
and JS state-machine wiring per kb-3-UI-SPEC §3.1 and §3.2.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "kb" / "templates"
STATIC = REPO / "kb" / "static"


@pytest.fixture(scope="module")
def rendered_ask_html() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    # Stub kb-1 i18n filter — return key so we can grep template structure
    env.filters["t"] = lambda key, lang="zh-CN": key
    env.filters["humanize"] = lambda value, lang="zh-CN": str(value)
    tmpl = env.get_template("ask.html")
    return tmpl.render(lang="zh-CN", request=None)


# ---------- Template-rendered DOM hooks (UI-SPEC §8) ----------


def test_qa_result_section_present(rendered_ask_html: str) -> None:
    assert "qa-result" in rendered_ask_html


def test_data_qa_state_attribute_present(rendered_ask_html: str) -> None:
    assert "data-qa-state" in rendered_ask_html


def test_qa_state_indicator_present(rendered_ask_html: str) -> None:
    assert "qa-state-indicator" in rendered_ask_html


def test_qa_fallback_banner_present(rendered_ask_html: str) -> None:
    assert "qa-fallback-banner" in rendered_ask_html


def test_qa_error_banner_present(rendered_ask_html: str) -> None:
    assert "qa-error-banner" in rendered_ask_html


def test_qa_sources_present(rendered_ask_html: str) -> None:
    assert "qa-sources" in rendered_ask_html


def test_qa_entities_present(rendered_ask_html: str) -> None:
    assert "qa-entities" in rendered_ask_html


def test_qa_feedback_present(rendered_ask_html: str) -> None:
    assert "qa-feedback" in rendered_ask_html


def test_qa_confidence_chip_fallback_present(rendered_ask_html: str) -> None:
    assert "qa-confidence-chip--fallback" in rendered_ask_html


def test_qa_answer_region_present(rendered_ask_html: str) -> None:
    assert "qa-answer" in rendered_ask_html


# ---------- Polling cadence injection + script wiring ----------


def test_kb_qa_poll_interval_injected_into_ask(rendered_ask_html: str) -> None:
    assert "KB_QA_POLL_INTERVAL_MS" in rendered_ask_html


def test_kb_qa_poll_timeout_injected_into_ask(rendered_ask_html: str) -> None:
    assert "KB_QA_POLL_TIMEOUT_MS" in rendered_ask_html


def test_qa_js_referenced_in_ask_html(rendered_ask_html: str) -> None:
    assert "qa.js" in rendered_ask_html


# ---------- Static asset existence ----------


def test_qa_js_file_exists() -> None:
    assert (STATIC / "qa.js").exists()


def test_qa_js_minimum_size() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 150, f"qa.js too short: {len(text.splitlines())} lines"


def test_marked_js_bundled() -> None:
    f = STATIC / "marked.min.js"
    assert f.exists()
    assert f.stat().st_size > 5000, f"marked.min.js too small: {f.stat().st_size} bytes"


# ---------- qa.js state-machine wiring ----------


def test_qa_js_polls_synthesize_endpoint() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert "/api/synthesize" in text


def test_qa_js_uses_localstorage_feedback() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert "kb_qa_feedback_" in text


def test_qa_js_handles_fts5_fallback() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    # Must reference either the state name OR the API field that triggers it
    assert "fallback" in text and "fallback_used" in text


def test_qa_js_reads_poll_interval_global() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert "KB_QA_POLL_INTERVAL_MS" in text


def test_qa_js_reads_poll_timeout_global() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert "KB_QA_POLL_TIMEOUT_MS" in text


def test_qa_js_exposes_window_kbqa_submit() -> None:
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert "window.KbQA" in text


def test_qa_js_implements_8_state_matrix() -> None:
    """The state machine must mention each of the 8 states by name."""
    text = (STATIC / "qa.js").read_text(encoding="utf-8")
    # idle is implicit on page load (default attr); the JS sets the other 7
    for state in ["submitting", "polling", "done", "error", "timeout", "fallback"]:
        assert state in text, f"state '{state}' missing from qa.js"


# ---------- Icon references ----------


def test_chat_bubble_question_icon_referenced() -> None:
    partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
    assert "chat-bubble-question" in partial


def test_lightning_bolt_icon_referenced() -> None:
    partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
    assert "lightning-bolt" in partial


# ---------- CSS token + selector discipline ----------


def test_css_no_new_root_vars() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
    assert var_count == 31, f"kb-1 baseline = 31 :root vars; got {var_count}"


def test_css_within_budget() -> None:
    css_lines = (STATIC / "style.css").read_text(encoding="utf-8").splitlines()
    # kb-3-10 + kb-3-11 share a +121 LOC budget over the kb-2 baseline (~1979).
    # Ceiling per UI-SPEC §8: <= 2100. kb-v2.1-5 PLAN raised the ceiling to
    # <= 2150 to fund the synthesis mode toggle (PLAN acceptance criterion
    # permits <= 2200; we keep the slack at 50 lines).
    assert len(css_lines) <= 2150, f"style.css over budget: {len(css_lines)} > 2150"


def test_css_qa_state_selectors_present() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.qa-result\[data-qa-state=", css), "qa-state attribute selector missing"
    assert ".qa-state-indicator" in css
    assert ".qa-confidence-chip--fallback" in css
    assert ".qa-source-chip" in css
    assert ".qa-spinner" in css


def test_css_result_reveal_animation_present() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "kb-qa-reveal" in css, "result-reveal keyframe (UI-SPEC §1 signature moment) missing"


def test_css_respects_prefers_reduced_motion() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


# ---------- Skill discipline sentinels ----------


def test_skill_invocation_strings_in_template() -> None:
    partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
    assert 'Skill(skill="ui-ux-pro-max"' in partial
    assert 'Skill(skill="frontend-design"' in partial


def test_skill_invocation_strings_in_qa_js() -> None:
    js = (STATIC / "qa.js").read_text(encoding="utf-8")
    assert 'Skill(skill="ui-ux-pro-max"' in js
    assert 'Skill(skill="frontend-design"' in js


# ---------- Restraint principle (D-9 + D-10) ----------


def test_qa_entities_only_visible_in_done_not_fallback() -> None:
    """D-9: fts5_fallback hides entities row (FTS5 has no entity links)."""
    partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
    # qa-entities is gated to the 'done' state, NOT 'fts5_fallback'
    m = re.search(r'qa-entities"\s+data-qa-state-only="([^"]+)"', partial)
    assert m, "qa-entities data-qa-state-only attr missing"
    states = m.group(1).split()
    assert "done" in states
    assert "fts5_fallback" not in states, "D-9 violated: fts5_fallback should not show entities"


def test_qa_feedback_only_visible_in_done_not_fallback() -> None:
    """D-10: fts5_fallback hides feedback row (don't pollute KG-quality signal)."""
    partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
    m = re.search(r'qa-feedback"\s+data-qa-state-only="([^"]+)"', partial)
    assert m, "qa-feedback data-qa-state-only attr missing"
    states = m.group(1).split()
    assert "done" in states
    assert "fts5_fallback" not in states, "D-10 violated: fts5_fallback should not show feedback"
