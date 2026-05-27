---
phase: kb-1-ssg-export-i18n-foundation
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/locale/zh-CN.json
  - kb/locale/en.json
  - kb/i18n.py
  - tests/unit/kb/test_i18n.py
autonomous: true
requirements:
  - I18N-03

must_haves:
  truths:
    - "Both zh-CN.json and en.json have IDENTICAL key sets (no missing translations)"
    - "Jinja2 filter `t(key, lang)` returns the localized string"
    - "Missing key returns the key literal as fallback (visible in UI for fast debugging)"
    - "~50 key namespace covers nav, article meta, footer, lang switcher, breadcrumbs"
  artifacts:
    - path: "kb/locale/zh-CN.json"
      provides: "Chinese UI chrome strings"
      contains: "nav.home, nav.articles, nav.ask, footer.copyright"
    - path: "kb/locale/en.json"
      provides: "English UI chrome strings"
      contains: "nav.home, nav.articles, nav.ask, footer.copyright"
    - path: "kb/i18n.py"
      provides: "register_jinja2_filter(env) + t(key, lang) function"
      exports: ["t", "register_jinja2_filter", "load_locales", "validate_key_parity"]
  key_links:
    - from: "kb/templates/*.html (later plans)"
      to: "kb.i18n.t"
      via: "Jinja2 filter `{{ 'nav.home' | t(lang) }}`"
      pattern: "filters\\['t'\\]|env\\.filters\\['t'\\]"
---

<objective>
Build the bilingual i18n foundation: locale JSON dictionaries for ~50 chrome strings + Python helper exposing `t(key, lang)` as a Jinja2 filter.

Purpose: I18N-03 is the spine of the bilingual chrome system. Templates in plans kb-1-06 and kb-1-07 use `{{ 'nav.home' | t(lang) }}` everywhere; if the locale JSON is missing a key or lang asymmetry exists, every template breaks. Build it once with a key-parity check upfront.

Output: 2 JSON files (zh-CN + en), 1 Python helper module, 1 test file.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@kb/docs/03-ARCHITECTURE.md
@CLAUDE.md

<interfaces>
**Per CONTEXT.md § "i18n filter implementation (I18N-03)":**
- Custom Jinja2 filter `t(key, lang='zh-CN')` — NOT Babel, NOT gettext
- Loads `kb/locale/zh-CN.json` + `kb/locale/en.json` at module import
- Templates use `{{ 'nav.home' | t(lang) }}` — `lang` passed explicitly from render context
- BOTH languages emitted in HTML output via `<span data-lang="zh">{{ 'nav.home' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.home' | t('en') }}</span>`
- Missing key → return `key` literal + log WARN (so missing translations are visible)

**Key namespace (from CONTEXT.md):** dot-notation, ~50 keys total covering:
- `nav.*` — navigation labels
- `article.*` — article meta labels (read_more, source_label, lang_label, published_at)
- `articles.*` — article list page (title, filter labels)
- `footer.*` — footer text
- `lang.*` — language switcher labels
- `breadcrumb.*` — breadcrumb labels
- `home.*` — homepage hero/sections
- `ask.*` — Q&A entry page
- `site.*` — site-level (title, tagline, brand name)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author kb/locale/zh-CN.json + kb/locale/en.json with ~50 key parity</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md § "i18n string namespace"
    - kb/docs/03-ARCHITECTURE.md § "页面内部链接地图" + § "双搜索/问答入口交互设计" (for actual UI labels in zh-CN)
    - kb/docs/01-PRD.md § "5 UX" (if exists — gives concrete UI text examples)
  </read_first>
  <files>kb/locale/zh-CN.json, kb/locale/en.json</files>
  <action>
    Author two JSON dictionaries. Both MUST have IDENTICAL key sets. Brand name per V-3 decision (handbook 09): main "企小勤", English aux "VitaClaw".

    Create `kb/locale/zh-CN.json` with the following exact key set + Chinese values:

    ```json
    {
      "site.brand": "企小勤",
      "site.brand_aux": "VitaClaw",
      "site.tagline": "AI Agent 技术圈双语知识库",
      "site.title": "企小勤知识库 — AI Agent 技术内容站",

      "nav.home": "首页",
      "nav.articles": "文章",
      "nav.ask": "AI 问答",
      "nav.search_placeholder": "搜索文章、实体、主题…",

      "lang.toggle_to_en": "EN",
      "lang.toggle_to_zh": "中",
      "lang.current_zh": "中文",
      "lang.current_en": "English",
      "lang.switcher_aria": "切换语言",

      "home.hero_title": "AI Agent 技术圈双语知识库",
      "home.hero_subtitle": "汇聚 KOL 文章、技术分析、问答合成",
      "home.section_latest": "最新文章",
      "home.section_ask_cta": "试试智能问答",
      "home.section_ask_desc": "基于知识图谱的深度问答,3-10 秒返回",

      "articles.page_title": "全部文章",
      "articles.filter_lang": "语言",
      "articles.filter_source": "来源",
      "articles.filter_all": "全部",
      "articles.filter_lang_zh": "中文",
      "articles.filter_lang_en": "English",
      "articles.filter_source_wechat": "公众号",
      "articles.filter_source_rss": "RSS",
      "articles.empty": "暂无文章",
      "articles.read_more": "阅读全文",

      "article.lang_zh": "中文",
      "article.lang_en": "English",
      "article.source_label": "来源",
      "article.published_at": "发布于",
      "article.body_source_enriched": "已增强",
      "article.body_source_raw": "原始内容",
      "article.cta_ask": "对这篇文章有疑问?问 AI →",

      "breadcrumb.home": "首页",
      "breadcrumb.articles": "文章",

      "ask.page_title": "AI 智能问答",
      "ask.input_placeholder": "输入你的问题,基于知识库为你解答…",
      "ask.submit": "深度问答",
      "ask.hot_questions": "热门问题",
      "ask.disclaimer": "回答由 AI 基于知识库合成,仅供参考",

      "footer.copyright": "© 2026 企小勤 VitaClaw",
      "footer.about": "关于",
      "footer.contact": "联系我们"
    }
    ```

    Create `kb/locale/en.json` with the EXACT SAME keys (do not add or remove any) + English values:

    ```json
    {
      "site.brand": "VitaClaw",
      "site.brand_aux": "企小勤",
      "site.tagline": "Bilingual AI Agent Tech Knowledge Base",
      "site.title": "VitaClaw KB — AI Agent Tech Content",

      "nav.home": "Home",
      "nav.articles": "Articles",
      "nav.ask": "Ask AI",
      "nav.search_placeholder": "Search articles, entities, topics…",

      "lang.toggle_to_en": "EN",
      "lang.toggle_to_zh": "中",
      "lang.current_zh": "中文",
      "lang.current_en": "English",
      "lang.switcher_aria": "Switch language",

      "home.hero_title": "Bilingual AI Agent Tech Knowledge Base",
      "home.hero_subtitle": "KOL articles, deep analysis, RAG Q&A",
      "home.section_latest": "Latest Articles",
      "home.section_ask_cta": "Try AI Q&A",
      "home.section_ask_desc": "Deep KG-backed Q&A — 3-10 seconds",

      "articles.page_title": "All Articles",
      "articles.filter_lang": "Language",
      "articles.filter_source": "Source",
      "articles.filter_all": "All",
      "articles.filter_lang_zh": "中文",
      "articles.filter_lang_en": "English",
      "articles.filter_source_wechat": "WeChat",
      "articles.filter_source_rss": "RSS",
      "articles.empty": "No articles yet",
      "articles.read_more": "Read more",

      "article.lang_zh": "中文",
      "article.lang_en": "English",
      "article.source_label": "Source",
      "article.published_at": "Published",
      "article.body_source_enriched": "Enriched",
      "article.body_source_raw": "Raw content",
      "article.cta_ask": "Question about this article? Ask AI →",

      "breadcrumb.home": "Home",
      "breadcrumb.articles": "Articles",

      "ask.page_title": "AI Knowledge Q&A",
      "ask.input_placeholder": "Type your question — KB-backed answer in seconds…",
      "ask.submit": "Ask",
      "ask.hot_questions": "Popular Questions",
      "ask.disclaimer": "Answer synthesized by AI from knowledge base — for reference only",

      "footer.copyright": "© 2026 VitaClaw 企小勤",
      "footer.about": "About",
      "footer.contact": "Contact"
    }
    ```

    Note: keys `lang.current_zh`, `lang.current_en`, `articles.filter_lang_zh`, `articles.filter_lang_en`, `article.lang_zh`, `article.lang_en` intentionally have IDENTICAL values across both locale files — these are language NAMES displayed as-is regardless of UI chrome. This is correct.

    Use Write tool for both files. Validate JSON parses cleanly (no trailing commas).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import json; zh=json.load(open('kb/locale/zh-CN.json',encoding='utf-8')); en=json.load(open('kb/locale/en.json',encoding='utf-8')); assert set(zh.keys())==set(en.keys()), f'Key mismatch: {set(zh.keys())^set(en.keys())}'; print(f'OK: {len(zh)} keys parity')"</automated>
  </verify>
  <acceptance_criteria>
    - Both files exist and parse as valid JSON
    - Both files have IDENTICAL key set (Python `set(zh.keys()) == set(en.keys())` is True)
    - Total key count is between 45 and 55 (~50 per CONTEXT.md estimate)
    - `kb/locale/zh-CN.json` value for `nav.home` is exactly `"首页"`
    - `kb/locale/en.json` value for `nav.home` is exactly `"Home"`
    - Both files contain key `site.brand`, `nav.home`, `nav.articles`, `nav.ask`, `lang.toggle_to_en`, `lang.toggle_to_zh`, `footer.copyright`, `breadcrumb.home`, `breadcrumb.articles`, `articles.page_title`
    - `grep -c "lang.current_zh" kb/locale/zh-CN.json` returns 1
  </acceptance_criteria>
  <done>Two locale JSONs with ~50 keys each, perfect key parity.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write kb/i18n.py with t() function + Jinja2 filter registration + tests</name>
  <read_first>
    - kb/locale/zh-CN.json (created in Task 1 — must exist before this task)
    - kb/locale/en.json (created in Task 1)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md § "i18n filter implementation (I18N-03)"
  </read_first>
  <files>kb/i18n.py, tests/unit/kb/test_i18n.py</files>
  <behavior>
    - Test 1: `t('nav.home', 'zh-CN')` returns `'首页'` (from zh-CN.json)
    - Test 2: `t('nav.home', 'en')` returns `'Home'`
    - Test 3: `t('nonexistent.key', 'en')` returns the literal string `'nonexistent.key'` AND logs a WARN-level message
    - Test 4: `t('nav.home')` (no lang arg) defaults to `KB_DEFAULT_LANG` from kb.config (which is `'zh-CN'`) → returns `'首页'`
    - Test 5: `t('nav.home', 'fr')` (unsupported lang) falls back to `KB_DEFAULT_LANG` → returns `'首页'`, logs WARN
    - Test 6: `validate_key_parity()` returns True when both locale files have identical key sets; raises `ValueError` listing the diff if asymmetric
    - Test 7: `register_jinja2_filter(env)` registers `t` filter on a Jinja2 Environment such that template `"{{ 'nav.home' | t('en') }}"` renders to `"Home"`
    - Test 8: `load_locales()` returns dict of `{lang_code: {key: value}}` with both `zh-CN` and `en` keys
  </behavior>
  <action>
    Create `kb/i18n.py` with this exact content:

    ```python
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
    ```

    Then create `tests/unit/kb/test_i18n.py` with all 8 behaviors above. For test 3 and 5, use `caplog` fixture to verify WARN log emission. For test 7, build a `jinja2.Environment` with `Environment(autoescape=False)`, register the filter, render a tiny template string.

    Use Python `logging` not `print` per `.claude/rules/python/hooks.md`.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_i18n.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `kb/i18n.py` exists; `python -c "from kb.i18n import t; print(t('nav.home', 'zh-CN'))"` outputs `首页`
    - `python -c "from kb.i18n import t; print(t('nav.home', 'en'))"` outputs `Home`
    - `python -c "from kb.i18n import t; print(t('missing.key', 'en'))"` outputs `missing.key` (literal fallback)
    - `python -c "from kb.i18n import validate_key_parity; print(validate_key_parity())"` outputs `True`
    - `pytest tests/unit/kb/test_i18n.py -v` exits 0 with 8 tests passing
    - `kb/i18n.py` does NOT contain `print(` (uses logging only — library code)
    - `kb/i18n.py` contains the exact strings: `_SUPPORTED_LANGS`, `register_jinja2_filter`, `validate_key_parity`, `env.filters["t"] = t`
  </acceptance_criteria>
  <done>i18n module + JSON files complete, 8 tests pass, key parity verified.</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/kb/test_i18n.py -v` exits 0 (8 tests pass)
- `validate_key_parity()` returns True (no asymmetric keys)
- Both locale JSON files load without parse error
</verification>

<success_criteria>
- I18N-03 satisfied: ~50 keys, Jinja2 filter registered, both langs in parity
- Missing-key visible in UI for fast debugging (returns key literal + logs WARN)
- All 8 unit tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-03-SUMMARY.md` documenting:
- Files created (+ key count)
- Test pass count
- Confirmed: zh-CN/en key parity
</output>
