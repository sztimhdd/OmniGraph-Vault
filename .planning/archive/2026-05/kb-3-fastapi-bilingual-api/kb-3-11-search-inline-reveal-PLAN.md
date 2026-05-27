---
phase: kb-3-fastapi-bilingual-api
plan: 11
subsystem: ui-search-inline
tags: [frontend, javascript, jinja2, ui-ux-pro-max, frontend-design, additive-js]
type: execute
wave: 4
depends_on: ["kb-3-03", "kb-3-06"]
files_modified:
  - kb/templates/index.html
  - kb/templates/articles_index.html
  - kb/static/search.js
  - kb/static/style.css
  - tests/integration/kb/test_search_inline_reveal.py
autonomous: true
requirements:
  - SEARCH-01
  - SEARCH-03

must_haves:
  truths:
    - "Homepage (index.html) and article list page (articles_index.html) reveal inline search results below the existing search input — no new /search page (D-6 restraint)"
    - "Empty / loading / error states reuse kb-1 .empty-state / .skeleton / .error-state classes (per UI-SPEC §3.6 — REUSE, do NOT redesign)"
    - "Each result chip reuses kb-1 .article-card styling verbatim"
    - "Lang filter respected via query param ?lang= taken from current page URL"
    - "JS module is purely additive — page works without it (form posts to /api/search?q=... as fallback if JS disabled)"
    - "Token discipline: zero new :root vars; zero new component patterns (per UI-SPEC §10 component restraint — search is a JS pattern, not a new component)"
  artifacts:
    - path: "kb/static/search.js"
      provides: "additive JS module: hooks search input, debounces, fetches /api/search?mode=fts, injects .search-results below form"
      min_lines: 120
    - path: "kb/templates/index.html"
      provides: "extended with `<div class='search-results' hidden></div>` below search form + `<script src='/static/search.js' defer></script>`"
    - path: "kb/templates/articles_index.html"
      provides: "same additive extension"
    - path: "kb/static/style.css"
      provides: "+~20 LOC for .search-results container only (reuses existing .article-card / .empty-state / .skeleton)"
    - path: "tests/integration/kb/test_search_inline_reveal.py"
      min_lines: 80
  key_links:
    - from: "kb/static/search.js"
      to: "GET /api/search?q=&mode=fts&lang= (kb-3-06)"
      via: "fetch + render"
      pattern: "fetch\\(.*'/api/search'|/api/search\\?"
    - from: "kb/templates/index.html + articles_index.html"
      to: "kb/static/search.js"
      via: "<script src='/static/search.js' defer>"
      pattern: "search\\.js"
---

<objective>
Add inline search results to homepage + article list page via additive JS. Per kb-3-UI-SPEC §3.6 + D-6, NO new template / page is created — the existing search input reveals results directly below it. Result cards reuse kb-1's `.article-card` class verbatim. The JS is purely additive — JS-disabled users fall back to the existing form submission behavior (form posts to a server endpoint OR triggers no-op).

Purpose: Search is the discovery secondary surface (browse is primary). Per restraint principle, we do NOT add a /search page (rejected option in UI-SPEC §3.6). Instead, "search becomes a magnifying glass inside existing surfaces" — type → see results below the input → click through to detail.

Output: 1 new `kb/static/search.js`, 2 templates extended (homepage + list page), ~20 LOC CSS, 1 integration test file.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-03-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md
@kb/templates/index.html
@kb/templates/articles_index.html
@kb/static/style.css
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
search.results.* locale keys (kb-3-03 added):
- `search.results.empty` — "未找到相关结果" / "No results found"
- `search.results.loading` — "搜索中..." / "Searching..."
- `search.results.error` — "搜索失败,请重试" / "Search failed, please retry"
- `search.results.view_all` — "查看全部" / "View all"
- `search.results.count` — "找到 {n} 条结果" / "{n} results found"

Backend endpoint (kb-3-06):
- GET /api/search?q=...&mode=fts&lang=...&limit=20 → `{items: [...], total, mode: "fts"}`
- items[i] = {hash, title, snippet, lang, source}

Existing search input markup in homepage (verify in current index.html — likely a form with name="q" or similar). The JS must be tolerant: `document.querySelector('form[role="search"], #search-form, input[name="q"]')` — locate whichever is the canonical search input.

Existing reusable classes (kb-1 baseline, locked — REUSE verbatim):
- `.article-card` — for each result row
- `.empty-state` — for "No results found" message
- `.skeleton` — for loading placeholder
- `.error-state` — for error message
- `.lang-badge` (zh-CN blue / en green / unknown grey) — for per-result lang chip
- `.source-icon` — for wechat/rss icon
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + create kb/static/search.js + extend index.html + articles_index.html + minimal CSS</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §3.6 (search inline reveal — DO NOT redesign; implement verbatim) + §10 (component restraint)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (.article-card / .empty-state / .skeleton / .error-state — REUSE verbatim)
    - kb/templates/index.html (existing search input — locate canonical selector)
    - kb/templates/articles_index.html (same — locate canonical search input)
    - kb/static/style.css (NO new tokens — append ~20 LOC for `.search-results` container only)
  </read_first>
  <files>kb/static/search.js, kb/templates/index.html, kb/templates/articles_index.html, kb/static/style.css</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this is a UI surface — invoke named Skills as tool calls:

    Skill(skill="ui-ux-pro-max", args="Implement the kb-3-UI-SPEC §3.6 search inline reveal pattern. Spec is locked: NO new /search page (D-6 rejected). The search input on homepage + list page already exists (kb-1). This task INSERTS a `<div class='search-results' hidden></div>` container directly below the existing search form, then JS injects content into it on debounced input (300ms). Each result is a `.article-card` (kb-1 class verbatim — DO NOT redesign). Empty / loading / error states use kb-1 `.empty-state` / `.skeleton` / `.error-state`. Restraint: a 'View all' link at the bottom (search.results.view_all) goes to /articles?q=... (existing list endpoint with q-filter from kb-3-05). NO new component patterns — search inline reveal is a JS pattern, not a new component (UI-SPEC §10 last bullet).")

    Skill(skill="frontend-design", args="Wire the ui-ux-pro-max output: kb/static/search.js as a single IIFE, debounces 300ms on `input` event, fetches /api/search?q=...&mode=fts&lang=... (lang inferred from document.documentElement.lang or window.location), injects results into `.search-results` div. Append script tag to index.html + articles_index.html: `<script src='/static/search.js' defer></script>`. Add the `<div class='search-results' hidden></div>` immediately after the existing search form. Append ~20 LOC to style.css for `.search-results` container ONLY (margin, padding, background) — DO NOT touch .article-card / .empty-state / .skeleton (those are kb-1 contracts). Pure ES2017 — no transpiler.")

    **Step 1 — Inspect existing search inputs** in `kb/templates/index.html` and `kb/templates/articles_index.html`. Find the canonical selector (likely `<input>` with `name="q"`, possibly inside a `<form role="search">`). Note the location for INSERTING the results container.

    **Step 2 — Add `<div class="search-results" hidden></div>`** immediately below the search form in BOTH `index.html` AND `articles_index.html`. Pattern:

    ```jinja2
    <!-- Existing search form (kb-1) — DO NOT modify the form itself -->
    <form ...>
      <input name="q" ... />
      <button>...</button>
    </form>

    <!-- ADD: kb-3 inline reveal container -->
    <div class="search-results" hidden role="region" aria-live="polite"></div>
    ```

    **Step 3 — Add `<script src="/static/search.js" defer></script>`** inside each page's `{% block extra_scripts %}` (or append at end of body if no such block). Both index.html and articles_index.html.

    **Step 4 — Create `kb/static/search.js`**:

    ```javascript
    /* kb/static/search.js — inline search reveal for index.html + articles_index.html.
     *
     * Per kb-3-UI-SPEC §3.6: NO new /search page. Search input reveals results
     * directly below the form, reusing kb-1 .article-card / .empty-state / .skeleton.
     *
     * Skill(skill="ui-ux-pro-max", args="...")
     * Skill(skill="frontend-design", args="...")
     */
    (function () {
      'use strict';

      var DEBOUNCE_MS = 300;
      var MIN_QUERY_LEN = 2;

      var input = null;
      var resultsEl = null;
      var debounceTimer = null;
      var inFlight = null;  // AbortController for the current fetch

      function $(sel, root) { return (root || document).querySelector(sel); }

      function locateInput() {
        return $('form[role="search"] input[name="q"]')
            || $('#search-form input')
            || $('input[name="q"]')
            || $('input[type="search"]');
      }

      function locateResults() {
        return $('.search-results');
      }

      function getLang() {
        var l = (document.documentElement.lang || '').toLowerCase();
        return l.indexOf('en') === 0 ? 'en' : 'zh-CN';
      }

      function showLoading() {
        if (!resultsEl) return;
        resultsEl.hidden = false;
        resultsEl.innerHTML = '<div class="skeleton" aria-busy="true"></div>';
      }

      function showEmpty() {
        if (!resultsEl) return;
        resultsEl.hidden = false;
        resultsEl.innerHTML = '<div class="empty-state">'
          + '<span class="lang-zh">未找到相关结果</span>'
          + '<span class="lang-en">No results found</span>'
          + '</div>';
      }

      function showError(msg) {
        if (!resultsEl) return;
        resultsEl.hidden = false;
        resultsEl.innerHTML = '<div class="error-state" role="alert">'
          + '<span class="lang-zh">搜索失败,请重试</span>'
          + '<span class="lang-en">Search failed, please retry</span>'
          + (msg ? '<span class="error-detail">' + msg + '</span>' : '')
          + '</div>';
      }

      function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, function (c) {
          return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
      }

      function renderItems(items, total, q) {
        if (!resultsEl) return;
        if (!items || items.length === 0) { showEmpty(); return; }
        var html = '<ul class="search-results-list" role="list">';
        items.forEach(function (it) {
          var langCls = it.lang === 'en' ? 'lang-badge lang-badge--en'
            : (it.lang === 'zh-CN' ? 'lang-badge lang-badge--zh' : 'lang-badge lang-badge--unknown');
          var langText = it.lang === 'en' ? 'English' : (it.lang === 'zh-CN' ? '中文' : '?');
          var sourceCls = 'source-icon source-icon--' + (it.source || 'web');
          html += '<li class="article-card">'
            + '<a class="article-card__link" href="/article/' + encodeURIComponent(it.hash) + '">'
            + '<h3 class="article-card__title">' + escapeHtml(it.title || '') + '</h3>'
            + '<p class="article-card__snippet">' + (it.snippet || '') + '</p>'
            + '<div class="article-card__meta">'
            + '<span class="' + langCls + '">' + langText + '</span>'
            + '<span class="' + sourceCls + '"></span>'
            + '</div>'
            + '</a></li>';
        });
        html += '</ul>';
        if (total > items.length) {
          html += '<div class="search-results-footer">'
            + '<a href="/articles?q=' + encodeURIComponent(q) + '" class="btn btn-link">'
            + '<span class="lang-zh">查看全部 (' + total + ')</span>'
            + '<span class="lang-en">View all (' + total + ')</span>'
            + '</a></div>';
        }
        resultsEl.hidden = false;
        resultsEl.innerHTML = html;
      }

      function runSearch(q) {
        if (inFlight) inFlight.abort();
        inFlight = (typeof AbortController === 'function') ? new AbortController() : null;
        showLoading();
        var url = '/api/search?q=' + encodeURIComponent(q) + '&mode=fts&lang=' + encodeURIComponent(getLang()) + '&limit=10';
        fetch(url, { signal: inFlight ? inFlight.signal : undefined })
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          })
          .then(function (data) {
            renderItems(data.items || [], data.total || 0, q);
          })
          .catch(function (e) {
            if (e && e.name === 'AbortError') return;  // Superseded by newer query
            showError(e && e.message ? e.message : '');
          });
      }

      function onInput(e) {
        clearTimeout(debounceTimer);
        var q = ((e.target && e.target.value) || '').trim();
        if (q.length < MIN_QUERY_LEN) {
          if (resultsEl) { resultsEl.hidden = true; resultsEl.innerHTML = ''; }
          return;
        }
        debounceTimer = setTimeout(function () { runSearch(q); }, DEBOUNCE_MS);
      }

      document.addEventListener('DOMContentLoaded', function () {
        input = locateInput();
        resultsEl = locateResults();
        if (!input || !resultsEl) return;
        input.addEventListener('input', onInput);
      });
    })();
    ```

    **Step 5 — APPEND ~20 LOC to `kb/static/style.css`** at the end:

    ```css
    /* ---- kb-3 search inline reveal (UI-SPEC §3.6) ---- */
    /* Reuses kb-1 .article-card / .empty-state / .skeleton / .lang-badge */
    /* — adds NO new tokens or component patterns. */

    .search-results {
      margin-top: 1rem;
      padding: 1rem;
      background: var(--bg-card);
      border-radius: .5rem;
    }
    .search-results[hidden] { display: none; }
    .search-results-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .5rem; }
    .search-results-footer { padding-top: 1rem; text-align: center; }
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && test -f kb/static/search.js && grep -q "search-results" kb/templates/index.html && grep -q "search-results" kb/templates/articles_index.html && grep -qE "^\\.search-results" kb/static/style.css</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/static/search.js` exists with ≥120 LOC
    - `grep -q "fetch.*'/api/search'\\|fetch.*\"/api/search\"\\|/api/search?" kb/static/search.js`
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" kb/static/search.js`
    - `grep -q "Skill(skill=\"frontend-design\"" kb/static/search.js`
    - `grep -q "search-results" kb/templates/index.html`
    - `grep -q "search-results" kb/templates/articles_index.html`
    - `grep -q "search.js" kb/templates/index.html`
    - `grep -q "search.js" kb/templates/articles_index.html`
    - `grep -qE "^\\.search-results" kb/static/style.css`
    - Token discipline: `grep -cE '^\\s*--[a-z-]+:' kb/static/style.css` outputs `31` (no new vars from this plan either)
    - CSS budget: `wc -l < kb/static/style.css` ≤ 2100 (after kb-3-10 + this plan)
    - No regression in kb-1 article-card / empty-state / skeleton classes (locate them in CSS — should be untouched)
  </acceptance_criteria>
  <done>search.js + index.html + articles_index.html extended; ~20 LOC CSS appended; no new tokens; Skills invoked literal.</done>
</task>

<task type="auto">
  <name>Task 2: Integration tests for search inline reveal — rendered HTML grep + JS structural checks</name>
  <read_first>
    - kb/static/search.js (Task 1 output)
    - kb/templates/index.html + kb/templates/articles_index.html (Task 1 — extended with .search-results div)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §3.6 (acceptance criteria)
  </read_first>
  <files>tests/integration/kb/test_search_inline_reveal.py</files>
  <action>
    Skill(skill="writing-tests", args="Integration tests verifying the rendered index.html + articles_index.html contains the search-results container and the search.js script tag. JS-structure tests against kb/static/search.js verify the fetch path uses /api/search?mode=fts, debounce timer is implemented, AbortController used to cancel superseded requests, AND empty/loading/error states are rendered with kb-1 reusable class names (.empty-state, .skeleton, .error-state, .article-card).")

    **Create `tests/integration/kb/test_search_inline_reveal.py`**:

    ```python
    """Search inline reveal regression — UI-SPEC §3.6 grep patterns."""
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
        return env.get_template("index.html").render(lang="zh-CN", request=None, articles=[])


    @pytest.fixture(scope="module")
    def rendered_articles_index() -> str:
        env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
        env.filters["t"] = lambda key, lang="zh-CN": key
        return env.get_template("articles_index.html").render(
            lang="zh-CN", request=None, articles=[], page=1, total=0, has_more=False,
        )


    def test_index_has_search_results_container(rendered_index):
        assert "search-results" in rendered_index


    def test_articles_index_has_search_results_container(rendered_articles_index):
        assert "search-results" in rendered_articles_index


    def test_index_includes_search_js(rendered_index):
        assert "search.js" in rendered_index


    def test_articles_index_includes_search_js(rendered_articles_index):
        assert "search.js" in rendered_articles_index


    def test_search_js_uses_api_search_endpoint():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        assert "/api/search" in text


    def test_search_js_uses_fts_mode():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        assert "mode=fts" in text or "&mode=fts" in text or "'mode': 'fts'" in text


    def test_search_js_debounces():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        assert "setTimeout" in text and "clearTimeout" in text


    def test_search_js_uses_abort_controller():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        assert "AbortController" in text


    def test_search_js_renders_kb1_reusable_classes():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        # UI-SPEC §3.6 requires: empty / loading / error / result-card states reuse kb-1 classes
        assert "article-card" in text
        assert "empty-state" in text
        assert "skeleton" in text
        assert "error-state" in text


    def test_search_js_skill_invocations_present():
        text = (STATIC / "search.js").read_text(encoding="utf-8")
        assert 'Skill(skill="ui-ux-pro-max"' in text
        assert 'Skill(skill="frontend-design"' in text


    def test_no_new_search_html_template():
        """UI-SPEC §3.6 D-6 rejection: no kb/templates/search.html should exist."""
        assert not (TEMPLATES / "search.html").exists(), \
            "UI-SPEC §3.6 D-6 rejected creating /search page; got search.html"


    def test_css_search_results_container_present():
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        assert re.search(r"^\.search-results", css, re.MULTILINE)


    def test_css_no_new_root_vars_after_kb3_10_and_11():
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
        assert var_count == 31, f"kb-1 baseline = 31 :root vars; got {var_count}"


    def test_css_budget_within_2100():
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        line_count = css.count("\n") + 1
        assert line_count <= 2100, f"style.css = {line_count} lines (budget 2100)"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_search_inline_reveal.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/integration/kb/test_search_inline_reveal.py` exists with ≥80 lines
    - `pytest tests/integration/kb/test_search_inline_reveal.py -v` exits 0 with ≥14 tests passing
    - Negative regression: `pytest tests/integration/kb/ -v` (kb-1 + kb-2 + kb-3-04..10 tests) exits 0
  </acceptance_criteria>
  <done>≥14 tests verifying search inline reveal structural correctness; UI-SPEC §3.6 acceptance covered.</done>
</task>

</tasks>

<verification>
- Search inline reveal pattern implemented per UI-SPEC §3.6 — no new /search page (D-6 enforced)
- Skill invocations literal in search.js (regex-verifiable: ui-ux-pro-max + frontend-design)
- Token discipline preserved: 31 :root vars (kb-1 baseline)
- Reuses kb-1 .article-card / .empty-state / .skeleton / .error-state verbatim
- Tests verify kb-1 reusable classes are present in JS render path (not redesigned)
</verification>

<success_criteria>
- SEARCH-01: FTS5 query consumed by inline reveal
- SEARCH-03: lang filter inferred from document.documentElement.lang
- Component restraint upheld (UI-SPEC §10): no new component patterns
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-11-SUMMARY.md` documenting:
- search.js + 2 templates extended + ~20 LOC CSS
- ≥14 tests passing
- Skill invocation strings literal in code:
  - `Skill(skill="ui-ux-pro-max", ...)`
  - `Skill(skill="frontend-design", ...)`
- Token discipline preserved (31 :root vars unchanged)
- No /search page created (D-6 restraint upheld)
- Reused kb-1 classes verbatim
</output>
</content>
</invoke>