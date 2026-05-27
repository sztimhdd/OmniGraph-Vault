---
phase: kb-3-fastapi-bilingual-api
plan: 03
subsystem: i18n-foundation
tags: [locale, icons, jinja2, foundation]
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/locale/zh-CN.json
  - kb/locale/en.json
  - kb/templates/_icons.html
  - tests/unit/kb/test_kb3_locale_keys.py
autonomous: true
requirements:
  - I18N-07

must_haves:
  truths:
    - "All 20 NEW locale keys from UI-SPEC §5 present in BOTH zh-CN.json and en.json (symmetric — no missing key on either side)"
    - "Two new SVG icons (chat-bubble-question, lightning-bolt) registered in _icons.html macro library"
    - "Existing kb-1/kb-2 keys untouched (additive only)"
    - "Each new key passes round-trip test: i18n.t(key, lang) returns expected string"
  artifacts:
    - path: "kb/locale/zh-CN.json"
      provides: "20 new qa.* + search.* keys (Chinese values)"
      contains: "qa.state.submitting"
    - path: "kb/locale/en.json"
      provides: "20 new qa.* + search.* keys (English values)"
      contains: "qa.state.submitting"
    - path: "kb/templates/_icons.html"
      provides: "+2 new icon name handlers (chat-bubble-question, lightning-bolt)"
      contains: "chat-bubble-question"
    - path: "tests/unit/kb/test_kb3_locale_keys.py"
      provides: "round-trip + symmetry tests for all 20 new keys"
  key_links:
    - from: "kb/locale/{zh-CN,en}.json"
      to: "kb/templates/ask.html (kb-3-10 consumer) + kb/static/qa.js (kb-3-10) + search inline reveal (kb-3-11)"
      via: "{{ key | t(lang) }} Jinja2 filter + JS data-attribute lookup"
      pattern: "qa\\.state|qa\\.fallback|search\\.results"
    - from: "kb/templates/_icons.html"
      to: "kb/templates/ask.html (qa-question echo + fts5_fallback chip)"
      via: "{{ icon('chat-bubble-question') }} + {{ icon('lightning-bolt') }} macro calls"
      pattern: "icon\\('chat-bubble-question'\\)|icon\\('lightning-bolt'\\)"
---

<objective>
Add 20 new locale keys + 2 new SVG icons that kb-3 UI plans (kb-3-10 ask.html state matrix + kb-3-11 search inline reveal) consume. This is pure foundation work — no behavior change yet, just the i18n + icon vocabulary that downstream UI plans will reference.

Purpose: Per kb-3-UI-SPEC §5, the Q&A result component + search inline reveal need ~20 new strings (state messages, fallback chip copy, sources/entities titles, feedback prompts, retry button, search empty/loading/error/view-all). Per UI-SPEC §3.7, two new icons (chat-bubble-question for question echo, lightning-bolt for fts5_fallback chip) join the existing _icons.html library. Without this Wave 1 task, kb-3-10 and kb-3-11 have nothing to reference.

Output: 2 locale JSON files extended (additive), 1 _icons.html macro extended, 1 unit test file verifying symmetry + round-trip.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/templates/_icons.html
@kb/i18n.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
20 NEW locale keys (verbatim from UI-SPEC §5):

| Key | zh-CN | en |
|---|---|---|
| `qa.state.submitting` | 正在提交... | Submitting... |
| `qa.state.polling` | 正在思考... | Thinking... |
| `qa.state.streaming` | 正在生成... | Generating... |
| `qa.state.error.network` | 网络错误,无法连接到服务器 | Network error, cannot reach server |
| `qa.state.error.server` | 服务器错误,请稍后重试 | Server error, please try again |
| `qa.state.timeout.message` | 超过等待时间,显示快速参考 | Timeout — showing quick reference |
| `qa.fallback.label` | 快速参考 | Quick Reference |
| `qa.fallback.explainer` | 基于关键词检索的快速回答,非完整知识图谱回答。 | Keyword-based quick reference, not full KG answer. |
| `qa.sources.title` | 参考来源 | Sources |
| `qa.entities.title` | 相关实体 | Related Entities |
| `qa.feedback.prompt` | 这个回答有帮助吗? | Was this helpful? |
| `qa.feedback.thanks_up` | 感谢反馈! | Thanks for the feedback! |
| `qa.feedback.thanks_down` | 感谢反馈,我们会改进。 | Thanks — we'll improve. |
| `qa.retry.button` | 重试 | Retry |
| `qa.question.echo_label` | 你的问题 | Your question |
| `search.results.empty` | 未找到相关结果 | No results found |
| `search.results.loading` | 搜索中... | Searching... |
| `search.results.error` | 搜索失败,请重试 | Search failed, please retry |
| `search.results.view_all` | 查看全部 | View all |
| `search.results.count` | 找到 {n} 条结果 | {n} results found |

Two new icons (per UI-SPEC §3.7 — Heroicons-style stroke 1.5 path data, 24x24 viewBox):

- `chat-bubble-question` — for `qa-question` echo and `qa-result` aria header
- `lightning-bolt` — for `qa-confidence-chip--fallback` indicator

Existing icon macro pattern (verbatim from kb/templates/_icons.html lines 11-16):

```jinja2
{% macro icon(name, size=20, cls='') %}
  {%- set sz = size|string -%}
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
       width="{{ sz }}" height="{{ sz }}" aria-hidden="true"
       {% if cls %}class="{{ cls }}"{% endif %}>
  {%- if name == 'home' -%}
    <path d="..."/>
  {%- elif name == 'articles' -%}
    ...
```

Pattern: `{%- elif name == 'chat-bubble-question' -%}` block with `<path d="..."/>` content, then same for `lightning-bolt`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add 20 new locale keys to both zh-CN.json and en.json + symmetry test</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §5 (NEW keys table — verbatim source of truth)
    - kb/locale/zh-CN.json (existing — APPEND only, preserve all existing keys)
    - kb/locale/en.json (existing — APPEND only, preserve all existing keys)
    - kb/i18n.py (existing `t()` filter — verify it handles dotted keys + missing-key fallback)
  </read_first>
  <files>kb/locale/zh-CN.json, kb/locale/en.json, tests/unit/kb/test_kb3_locale_keys.py</files>
  <action>
    Read both `kb/locale/zh-CN.json` and `kb/locale/en.json` first to understand existing structure (likely top-level dict; may use nested or flat-with-dots keys — match existing convention).

    **Step 1 — APPEND 20 new keys to `kb/locale/zh-CN.json`** (using the exact zh-CN values from the table in `<interfaces>`). If the file uses nested structure (e.g. `{"qa": {"state": {"submitting": "..."}}}`), nest accordingly. If flat-with-dots (e.g. `{"qa.state.submitting": "..."}`), use flat. **Match the existing convention** — do NOT mix nesting styles.

    **Step 2 — APPEND same 20 keys to `kb/locale/en.json`** with English values. Both files MUST have identical key sets (symmetry).

    **Step 3 — Create `tests/unit/kb/test_kb3_locale_keys.py`** verifying:

    ```python
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
    ```

    Run via `pytest tests/unit/kb/test_kb3_locale_keys.py -v` — must pass with ≥42 parametrized + standalone tests (20 zh + 20 en + 1 symmetric + 1 count + 1 baseline = 43).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_kb3_locale_keys.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "qa.state.submitting" kb/locale/zh-CN.json`
    - `grep -q "qa.state.submitting" kb/locale/en.json`
    - `grep -q "qa.fallback.label" kb/locale/zh-CN.json`
    - `grep -q "search.results.empty" kb/locale/en.json`
    - `grep -q "search.results.count" kb/locale/zh-CN.json` AND value contains `{n}`
    - `python -c "import json; d=json.load(open('kb/locale/zh-CN.json',encoding='utf-8')); print('OK')"` exits 0 (valid JSON)
    - `python -c "import json; d=json.load(open('kb/locale/en.json',encoding='utf-8')); print('OK')"` exits 0
    - `pytest tests/unit/kb/test_kb3_locale_keys.py -v` exits 0 with ≥43 tests passing
    - kb-1 / kb-2 locale tests still pass: `pytest tests/unit/kb/ -v -k "locale or i18n"` exits 0 (additive change preserves existing tests)
  </acceptance_criteria>
  <done>20 keys × 2 languages added; valid JSON; symmetric; existing keys preserved.</done>
</task>

<task type="auto">
  <name>Task 2: Add chat-bubble-question + lightning-bolt SVG icons to _icons.html macro</name>
  <read_first>
    - kb/templates/_icons.html (existing macro — APPEND new `{%- elif -%}` branches before the closing `{%- endif -%}` and `</svg>` tag)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §3.7 (icon justification + naming)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (existing kb-1 icon set — confirm chat-bubble-question + lightning-bolt are NOT already present)
  </read_first>
  <files>kb/templates/_icons.html, tests/unit/kb/test_kb3_locale_keys.py</files>
  <action>
    Read `kb/templates/_icons.html` fully to find the closing structure (typical pattern: a final `{%- elif -%}` branch followed by `{%- endif -%}` and `</svg>` and `{% endmacro %}`).

    **Step 1 — APPEND two new `{%- elif -%}` branches** before the existing closing `{%- endif -%}`:

    ```jinja2
      {%- elif name == 'chat-bubble-question' -%}
        {# Speech bubble + question mark — for qa-question echo region per kb-3-UI-SPEC §3.1 #}
        <path d="M3 12c0-4.4 4-8 9-8s9 3.6 9 8-4 8-9 8c-1.3 0-2.5-.2-3.6-.6L3 21l1.6-3.4C3.6 16.1 3 14.1 3 12z"/>
        <path d="M9.5 9.5a2.5 2.5 0 0 1 5 0c0 1-.7 1.7-1.5 2-.4.15-.7.5-.7 1"/>
        <circle cx="12.3" cy="14" r="0.5" fill="currentColor"/>
      {%- elif name == 'lightning-bolt' -%}
        {# Bolt — for fts5_fallback "Quick Reference" chip per kb-3-UI-SPEC §3.1 #}
        <path d="M13 2L4.5 13.5h6l-1 8.5L18 10.5h-6L13 2z"/>
    ```

    Place them before the final `{%- endif -%}`. Do NOT modify any existing branches.

    **Step 2 — APPEND icon-presence tests to `tests/unit/kb/test_kb3_locale_keys.py`** (or create a separate test file — doesn't matter, must be in tests dir):

    ```python
    # APPEND to test_kb3_locale_keys.py:

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
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_kb3_locale_keys.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "chat-bubble-question" kb/templates/_icons.html`
    - `grep -q "lightning-bolt" kb/templates/_icons.html`
    - `pytest tests/unit/kb/test_kb3_locale_keys.py -v -k "icon"` exits 0 with ≥3 icon tests passing
    - All previous Task 1 locale tests still pass
    - Existing kb-1 templates that use `icon('home')`, `icon('articles')` etc. still render — verify by `pytest tests/integration/kb/ -v -k "icon or template"` exits 0 (if such tests exist; if not, manual check via Jinja smoke test in this file)
  </acceptance_criteria>
  <done>Two new icons added to macro; existing icons untouched; render smoke test passes.</done>
</task>

</tasks>

<verification>
- 20 new keys × 2 languages = 40 entries added (additive)
- 2 new icons added to macro library
- All locale + icon tests pass (≥46 total)
- No regression in existing kb-1 / kb-2 locale or template tests
</verification>

<success_criteria>
- I18N foundation ready for kb-3-10 (ask.html state matrix consumes qa.* keys + chat-bubble-question + lightning-bolt icons)
- Search foundation ready for kb-3-11 (homepage / articles_index inline reveal consumes search.results.* keys)
- I18N-07 cross-reference: kb-3-08 will inject `qa.state.*` strings during streaming/done state transitions on the client
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-03-SUMMARY.md` documenting:
- 20 new locale keys × 2 languages (40 entries) additive
- 2 new SVG icons in _icons.html macro
- ≥46 unit tests passing (43 locale + 3 icon)
- No Skill invocation needed for this plan (pure mechanical i18n + SVG additions per UI-SPEC §5 + §3.7 — no design choices)
- Foundation consumed by kb-3-10 (ask.html state matrix) + kb-3-11 (search inline reveal)
</output>
</content>
</invoke>