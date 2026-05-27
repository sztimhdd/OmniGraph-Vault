---
phase: kb-1-ssg-export-i18n-foundation
plan: 08
type: execute
wave: 4
depends_on: ["kb-1-03-i18n-locale", "kb-1-04-static-css-js", "kb-1-07-base-template-pages"]
files_modified:
  - kb/templates/article.html
autonomous: true
requirements:
  - I18N-05
  - I18N-06
  - UI-06
  - UI-07
  - EXPORT-04

must_haves:
  truths:
    - "article.html sets <html lang> via render context to MATCH the article CONTENT lang (zh-CN or en) — independent of UI chrome lang (I18N-05)"
    - "article.html sets <html data-fixed-lang='true'> so lang.js does NOT override the content-set lang"
    - "Visible lang badge ('中文' or 'English') appears at top of article body (I18N-06)"
    - "Breadcrumb 'Home > Articles > [Title]' with localized labels (UI-07)"
    - "JSON-LD Article schema with inLanguage matching content lang (UI-06)"
    - "Article body is pre-rendered HTML (Pygments highlighting baked in) — template just emits {{ body_html | safe }}"
  artifacts:
    - path: "kb/templates/article.html"
      provides: "Per-article detail template (extends base.html)"
      min_lines: 60
  key_links:
    - from: "kb/templates/article.html"
      to: "rendered HTML by markdown library + Pygments codehilite"
      via: "{{ body_html | safe }}"
      pattern: "body_html.*safe"
    - from: "article.html <head>"
      to: "JSON-LD schema.org Article"
      via: "{% block extra_head %}<script type='application/ld+json'>"
      pattern: "application/ld\\+json"
---

<objective>
Build the article detail template — the highest-stakes template because it carries content-language semantics (`<html lang>` set to article content lang, NOT user UI chrome lang), the lang badge, breadcrumb, JSON-LD article schema, and the pre-rendered Pygments-highlighted body HTML.

Purpose: I18N-05 is the cardinal rule — article DETAIL pages set `<html lang>` to content language so search engines, screen readers, and IM share previews see the right language. UI-06 emits structured data. UI-07 emits breadcrumbs. EXPORT-04 means the body comes pre-rendered as HTML (the export driver does the markdown→HTML+Pygments conversion before passing to template).

Output: 1 Jinja2 template file.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-07-SUMMARY.md
@kb/templates/base.html
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/static/style.css
@kb/docs/03-ARCHITECTURE.md
@CLAUDE.md

<interfaces>
Render context expectation (provided by export driver in plan kb-1-09):

```python
context = {
    "lang": article.lang,          # 'zh-CN' | 'en' | 'unknown' — drives <html lang>
    "article": {
        "title": str,
        "url_hash": str,             # 10-char URL hash
        "lang": str,                 # same as outer 'lang' but accessible via article.lang
        "lang_label": str,           # '中文' or 'English' for badge
        "url": str,                  # source URL
        "source": str,               # 'wechat' | 'rss'
        "update_time": str,
        "body_source": str,          # 'vision_enriched' | 'raw_markdown'
    },
    "body_html": str,                # PRE-RENDERED HTML — markdown.markdown() + Pygments already applied
    "og": {
        "title": str,
        "description": str,
        "image": str,                # /static/img/{hash}/cover.png OR fallback to logo
        "type": "article",
        "locale": str,               # 'zh_CN' or 'en_US' — matches article lang
    },
    "page_url": str,                 # canonical /articles/{hash}.html
    "json_ld": dict,                 # {"@context": "https://schema.org", "@type": "Article", ...}
}
```

CSS classes available (from style.css plan-04):
- `.breadcrumb` — top crumb trail
- `.lang-badge` — content lang indicator
- `.article-body` — main content max-width 720px
- Pygments `.codehilite` (Monokai) for code blocks

The KEY axis distinction (CONTEXT.md "Content language vs UI language (two axes)"):
- DETAIL pages: `<html lang>` = content lang (fixed at SSG time, server-set)
- Detail pages set `<html data-fixed-lang="true">` so lang.js does NOT override
- BUT: chrome elements (nav links, breadcrumb, footer) STILL emit dual-span — user can read article body in English while UI chrome is Chinese
- Article BODY content displays in its original language regardless of UI chrome lang
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write kb/templates/article.html — detail page with content lang + breadcrumb + JSON-LD + body</name>
  <read_first>
    - kb/templates/base.html (extends this; understand block structure)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Content language vs UI language (two axes)" + "Web courtesy meta tags (UI-05, UI-06)"
    - .planning/REQUIREMENTS-KB-v2.md I18N-05, I18N-06, UI-06, UI-07, EXPORT-04
    - kb/locale/zh-CN.json (keys: breadcrumb.home, breadcrumb.articles, article.lang_zh, article.lang_en, article.source_label, article.published_at, article.body_source_enriched, article.body_source_raw, article.cta_ask)
  </read_first>
  <files>kb/templates/article.html</files>
  <action>
    Create `kb/templates/article.html`. Note the CRITICAL difference from other templates: article.html OVERRIDES the `<html>` tag from base.html since `lang` and `data-fixed-lang` need to be set differently. Achieve this by NOT extending base.html and instead inlining the chrome — OR by passing a `data_fixed_lang` flag through to base.html and overriding the html tag emit.

    The cleaner solution is to NOT extend base.html for article.html and instead inline the structure. This avoids surgical hackery on base.html.

    Use this exact content:

    ```html
    <!DOCTYPE html>
    <html lang="{{ article.lang }}" data-fixed-lang="true">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{{ article.title }} — {{ 'site.brand' | t('zh-CN') }} / {{ 'site.brand' | t('en') }}</title>
      <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
      <link rel="stylesheet" href="/static/style.css">

      {# UI-05 og:* meta — article type, locale matches content lang #}
      <meta property="og:title" content="{{ og.title }}">
      <meta property="og:description" content="{{ og.description }}">
      <meta property="og:image" content="{{ og.image }}">
      <meta property="og:type" content="article">
      <meta property="og:locale" content="{{ og.locale }}">
      <meta property="og:url" content="{{ page_url }}">

      {# UI-06 JSON-LD Article schema with inLanguage #}
      <script type="application/ld+json">
      {{ json_ld | tojson }}
      </script>
    </head>
    <body>
      <header class="nav-wrap">
        <div class="container">
          <nav class="nav">
            <a href="/" class="nav-brand">
              <img src="/static/VitaClaw-Logo-v0.png" alt="" onerror="this.style.display='none'">
              <span data-lang="zh">{{ 'site.brand' | t('zh-CN') }}</span><span data-lang="en">{{ 'site.brand' | t('en') }}</span>
            </a>
            <div class="nav-links">
              <a href="/"><span data-lang="zh">{{ 'nav.home' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.home' | t('en') }}</span></a>
              <a href="/articles/"><span data-lang="zh">{{ 'nav.articles' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.articles' | t('en') }}</span></a>
              <a href="/ask/"><span data-lang="zh">{{ 'nav.ask' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.ask' | t('en') }}</span></a>
              <button class="lang-toggle" type="button" aria-label="{{ 'lang.switcher_aria' | t('zh-CN') }}">
                <span data-lang="zh">{{ 'lang.toggle_to_en' | t('zh-CN') }}</span><span data-lang="en">{{ 'lang.toggle_to_zh' | t('en') }}</span>
              </button>
            </div>
          </nav>
        </div>
      </header>

      <main>
        <div class="container">
          {# UI-07 breadcrumb with localized labels #}
          <nav class="breadcrumb" aria-label="breadcrumb">
            <a href="/">
              <span data-lang="zh">{{ 'breadcrumb.home' | t('zh-CN') }}</span><span data-lang="en">{{ 'breadcrumb.home' | t('en') }}</span>
            </a>
            <span> &gt; </span>
            <a href="/articles/">
              <span data-lang="zh">{{ 'breadcrumb.articles' | t('zh-CN') }}</span><span data-lang="en">{{ 'breadcrumb.articles' | t('en') }}</span>
            </a>
            <span> &gt; </span>
            <span>{{ article.title }}</span>
          </nav>

          <article class="article-body">
            <header>
              <h1>{{ article.title }}</h1>
              {# I18N-06 visible content lang badge — emits as the FIXED content lang #}
              <div class="article-meta">
                <span class="lang-badge">
                  {% if article.lang == 'zh-CN' %}{{ 'article.lang_zh' | t('zh-CN') }}{% elif article.lang == 'en' %}{{ 'article.lang_en' | t('zh-CN') }}{% else %}—{% endif %}
                </span>
                <span>
                  <span data-lang="zh">{{ 'article.source_label' | t('zh-CN') }}:</span><span data-lang="en">{{ 'article.source_label' | t('en') }}:</span>
                  {{ article.source }}
                </span>
                <span>
                  <span data-lang="zh">{{ 'article.published_at' | t('zh-CN') }}:</span><span data-lang="en">{{ 'article.published_at' | t('en') }}:</span>
                  {{ article.update_time }}
                </span>
                {% if article.body_source == 'vision_enriched' %}
                <span class="badge-enriched">
                  <span data-lang="zh">{{ 'article.body_source_enriched' | t('zh-CN') }}</span><span data-lang="en">{{ 'article.body_source_enriched' | t('en') }}</span>
                </span>
                {% endif %}
              </div>
            </header>

            {# EXPORT-04 body — pre-rendered HTML with Pygments highlighting baked in #}
            <div class="article-content">
              {{ body_html | safe }}
            </div>

            <footer class="article-footer">
              <a href="/ask/" class="btn btn-secondary">
                <span data-lang="zh">{{ 'article.cta_ask' | t('zh-CN') }}</span><span data-lang="en">{{ 'article.cta_ask' | t('en') }}</span>
              </a>
            </footer>
          </article>
        </div>
      </main>

      <footer class="footer">
        <div class="container">
          <p>
            <span data-lang="zh">{{ 'footer.copyright' | t('zh-CN') }}</span><span data-lang="en">{{ 'footer.copyright' | t('en') }}</span>
          </p>
        </div>
      </footer>
      <script src="/static/lang.js"></script>
    </body>
    </html>
    ```

    Key structural notes:
    - Does NOT use `{% extends "base.html" %}` — inlines the chrome because of the `<html lang>` and `data-fixed-lang` divergence
    - Trade-off: ~80 lines of chrome duplication vs hacking base.html. Surgical Changes principle prefers duplication over extending base.html with conditionals
    - `{{ body_html | safe }}` — body is pre-rendered HTML; `| safe` disables auto-escape (otherwise Pygments classes get escaped)
    - `{{ json_ld | tojson }}` — Jinja2's tojson filter properly escapes for `<script>` context
    - Lang badge emits ONLY in the article's content lang (no dual-span here — the badge is a content marker, not chrome)
    - Article meta labels (`article.source_label`, `article.published_at`) are CHROME (dual-span)
    - Article title (h1) renders as-is (it's content, in the article's content lang)
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "
from jinja2 import Environment, FileSystemLoader
from kb.i18n import register_jinja2_filter
env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True)
register_jinja2_filter(env)
tpl = env.get_template('article.html')
ctx = {
    'lang': 'en',
    'article': {'title': 'Test EN article', 'url_hash':'abc', 'lang':'en', 'url':'http://e.x', 'source':'wechat', 'update_time':'2026', 'body_source':'raw_markdown'},
    'body_html': '&lt;p&gt;Body HTML&lt;/p&gt;',
    'og': {'title':'T', 'description':'D', 'image':'/static/x.png', 'type':'article', 'locale':'en_US'},
    'page_url': '/articles/abc.html',
    'json_ld': {'@context':'https://schema.org','@type':'Article','inLanguage':'en'},
}
html = tpl.render(**ctx)
assert 'lang=\"en\"' in html, 'html lang must match content lang'
assert 'data-fixed-lang=\"true\"' in html, 'data-fixed-lang attr missing'
assert 'application/ld+json' in html, 'JSON-LD missing'
assert 'lang-badge' in html, 'lang badge missing'
assert 'breadcrumb' in html, 'breadcrumb missing'
print('OK')
"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/article.html` exists with line count ≥ 60
    - Contains exact string `<html lang="{{ article.lang }}" data-fixed-lang="true">`
    - Contains string `application/ld+json` (UI-06 JSON-LD)
    - Contains string `class="lang-badge"` (I18N-06)
    - Contains string `class="breadcrumb"` (UI-07)
    - Contains string `og:type` with value `article` (not `website`)
    - Contains string `{{ body_html | safe }}` (EXPORT-04 — pre-rendered HTML)
    - Contains string `{{ json_ld | tojson }}` (proper script-context escaping)
    - Renders without Jinja2 error when given the test context above (verify command exits 0)
    - Test context with `lang='en'` produces HTML containing `lang="en"` (content lang propagation works)
    - Does NOT contain `{% extends "base.html" %}` (inlines chrome by design)
  </acceptance_criteria>
  <done>article.html detail template complete with content-lang axis + JSON-LD + breadcrumb.</done>
</task>

</tasks>

<verification>
- `kb/templates/article.html` renders with sample context (verify command above exits 0)
- Content lang propagates correctly: `lang='en'` context produces `<html lang="en">`
- JSON-LD script tag includes inLanguage matching content lang
</verification>

<success_criteria>
- I18N-05 satisfied: `<html lang>` set per content lang (not chrome lang); `data-fixed-lang="true"` prevents JS override
- I18N-06 satisfied: visible lang badge near article title
- UI-06 satisfied: JSON-LD Article schema with inLanguage
- UI-07 satisfied: breadcrumb with localized labels
- EXPORT-04 satisfied: body emits as pre-rendered HTML (template doesn't render markdown — driver does)
- og:* meta tags present with og:type='article'
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-08-SUMMARY.md` documenting:
- article.html line count
- Content lang propagation proof (test render with lang='en' → output has `lang="en"`)
- All 5 REQs satisfied (I18N-05, I18N-06, UI-06, UI-07, EXPORT-04)
</output>
