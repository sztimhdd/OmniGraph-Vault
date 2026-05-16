"""kb-3-11 — UI-SPEC §3.6 inline search reveal regression suite.

Skill(skill="writing-tests", args="Integration tests verifying the rendered
index.html + articles_index.html contains the search-results container and
the search.js script tag. JS-structure tests against kb/static/search.js
verify the fetch path uses /api/search?mode=fts, debounce timer is
implemented, AbortController used to cancel superseded requests, AND
empty/loading/error states are rendered with kb-1 reusable class names
(.empty-state, .skeleton, .error-state, .article-card).")

Grep-verifiable patterns against rendered index.html + articles_index.html
templates and against kb/static/search.js + kb/static/style.css. Asserts
the inline reveal DOM hook, Skill discipline sentinels, kb-1 reusable-class
reuse, AbortController + debounce wiring, and token / LOC budget discipline.
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
def rendered_index() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.filters["t"] = lambda key, lang="zh-CN": key
    env.filters["humanize"] = lambda value, lang="zh-CN": str(value)
    return env.get_template("index.html").render(
        lang="zh-CN",
        request=None,
        articles=[],
        topics=[],
        featured_entities=[],
    )


@pytest.fixture(scope="module")
def rendered_articles_index() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.filters["t"] = lambda key, lang="zh-CN": key
    env.filters["humanize"] = lambda value, lang="zh-CN": str(value)
    return env.get_template("articles_index.html").render(
        lang="zh-CN",
        request=None,
        articles=[],
    )


# ---------- Template-rendered DOM hooks (UI-SPEC §3.6) ----------


def test_index_has_search_results_container(rendered_index: str) -> None:
    assert "search-results" in rendered_index


def test_articles_index_has_search_results_container(rendered_articles_index: str) -> None:
    assert "search-results" in rendered_articles_index


def test_index_includes_search_js(rendered_index: str) -> None:
    assert "search.js" in rendered_index


def test_articles_index_includes_search_js(rendered_articles_index: str) -> None:
    assert "search.js" in rendered_articles_index


# ---------- search.js structural checks ----------


def test_search_js_uses_api_search_endpoint() -> None:
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "/api/search" in text


def test_search_js_uses_fts_mode() -> None:
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "mode=fts" in text


def test_search_js_debounces() -> None:
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "setTimeout" in text and "clearTimeout" in text


def test_search_js_uses_abort_controller() -> None:
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "AbortController" in text


def test_search_js_renders_kb1_reusable_classes() -> None:
    """UI-SPEC §3.6: empty / loading / error / result-card states reuse kb-1 classes."""
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "article-card" in text
    assert "empty-state" in text
    assert "skeleton" in text
    assert "error-state" in text


def test_search_js_skill_invocations_present() -> None:
    """Per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1 — literal Skill() strings."""
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert 'Skill(skill="ui-ux-pro-max"' in text
    assert 'Skill(skill="frontend-design"' in text


def test_search_js_lang_inferred_from_html() -> None:
    """SEARCH-03 — lang directive inferred from document.documentElement.lang."""
    text = (STATIC / "search.js").read_text(encoding="utf-8")
    assert "documentElement.lang" in text


# ---------- D-6 restraint: NO new search.html template ----------


def test_no_new_search_html_template() -> None:
    """UI-SPEC §3.6 D-6 rejected creating /search page; got search.html."""
    assert not (TEMPLATES / "search.html").exists(), (
        "UI-SPEC §3.6 D-6 rejected creating /search page; got search.html"
    )


# ---------- CSS token + LOC discipline ----------


def test_css_search_results_container_present() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert re.search(r"^\.search-results", css, re.MULTILINE)


def test_css_no_new_root_vars_after_kb3_10_and_11() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
    assert var_count == 31, f"kb-1 baseline = 31 :root vars; got {var_count}"


def test_css_budget_within_2100() -> None:
    """kb-v2.1-5 raised the budget to <= 2150 to fund synthesis mode toggle."""
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    line_count = css.count("\n") + 1
    assert line_count <= 2150, f"style.css = {line_count} lines (budget 2150)"
