---
phase: kb-1-ssg-export-i18n-foundation
plan: 07
type: execute
wave: 3
depends_on: ["kb-1-03-i18n-locale", "kb-1-04-static-css-js"]
files_modified:
  - kb/templates/base.html
  - kb/templates/index.html
  - kb/templates/articles_index.html
  - kb/templates/ask.html
autonomous: true
requirements:
  - I18N-03
  - I18N-08
  - UI-04
  - UI-05
  - UI-07

must_haves:
  truths:
    - "base.html provides the chrome layout with top nav (brand + lang toggle), footer, and og:* meta tag block"
    - "Both zh-CN and en versions of every chrome string emit inline as <span data-lang='zh|en'> pairs"
    - "Pages reference /static/style.css + /static/lang.js with correct relative paths"
    - "Article list page (articles_index.html) renders cards with title + lang badge + source badge + date"
    - "Q&A entry page (ask.html) is a placeholder form (POSTs to /api/synthesize wired in kb-3)"
    - "Homepage (index.html) shows hero + latest articles section + Ask AI CTA"
  artifacts:
    - path: "kb/templates/base.html"
      provides: "Jinja2 base template with chrome + og:* meta + breadcrumb slot"
      min_lines: 100
    - path: "kb/templates/index.html"
      provides: "Homepage template (extends base.html)"
    - path: "kb/templates/articles_index.html"
      provides: "Article list template with filter UI (extends base.html)"
    - path: "kb/templates/ask.html"
      provides: "Q&A entry placeholder (extends base.html)"
  key_links:
    - from: "all 4 templates"
      to: "kb.i18n.t"
      via: "Jinja2 filter `{{ key | t(lang) }}`"
      pattern: "\\| t\\("
    - from: "all 4 templates"
      to: "/static/style.css + /static/lang.js"
      via: "link rel=stylesheet + script src"
      pattern: "static/style\\.css|static/lang\\.js"
---

<objective>
Build the chrome layout (`base.html`) plus three of the four page templates: homepage, article list, Q&A entry. Article DETAIL template (`article.html`) is plan kb-1-08 — separated because it has higher complexity (content lang axis, JSON-LD, Pygments rendering, breadcrumb).

Purpose: All chrome pages share the same `<head>`, nav, footer, and og:* tags via base.html. The 3 simpler page templates extend base.html with one block override each. This keeps i18n duplication out of pages.

Output: 4 Jinja2 template files. No code execution at this stage; rendering happens in plan kb-1-09.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-03-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04-SUMMARY.md
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/static/style.css
@kb/docs/03-ARCHITECTURE.md
@CLAUDE.md

<interfaces>
i18n filter usage (from kb/i18n.py created in plan 03):

```jinja
{# In any template, lang is passed via render context #}
{{ 'nav.home' | t(lang) }}                    {# returns localized string for current chrome lang #}

{# Or for explicit dual-lang emission inline (the canonical pattern): #}
<span data-lang="zh">{{ 'nav.home' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.home' | t('en') }}</span>

{# Block-level dual-lang (less common — only for paragraph-scale content): #}
<div class="lang-block" data-lang="zh">{{ 'home.hero_subtitle' | t('zh-CN') }}</div>
<div class="lang-block" data-lang="en">{{ 'home.hero_subtitle' | t('en') }}</div>
```

CSS classes available (from kb/static/style.css):
- `.container`, `.card`, `.btn`, `.btn-secondary`
- `.nav`, `.nav-brand`, `.nav-links`, `.lang-toggle`
- `.article-card`, `.article-card-title`, `.article-card-meta`, `.lang-badge`
- `.breadcrumb`
- `[data-lang]`, `.lang-block[data-lang]` (i18n span/block toggling)

JS bootstrap (from kb/static/lang.js): expects `<button class="lang-toggle">` somewhere on the page. On detail pages, `<html data-fixed-lang="true">` prevents the JS from overwriting the server-set content lang.

Render context variables expected (provided by export driver in plan kb-1-09):
- `lang`: chrome lang for the page ('zh-CN' default; 'en' if generating English-default)
- For now plan-09 will render both pages with `lang='zh-CN'` since the JS does the actual chrome switching client-side. The dual-span emission means the HTML carries both languages regardless of `lang` context.
- `articles`: list of ArticleRecord-shaped dicts (for index + articles_index)
- `og`: dict with og:title / og:description / og:image / og:type / og:locale per-page
- `page_url`: canonical URL for og:url
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write kb/templates/base.html — chrome layout + og: meta + i18n filter usage</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "i18n string namespace" + "Web courtesy meta tags (UI-05, UI-06)"
    - kb/locale/zh-CN.json (Task 3 plan-03 output — see what keys exist)
    - kb/static/style.css (read class names available)
    - kb/docs/03-ARCHITECTURE.md "页面内部链接地图" (header + footer expectations)
  </read_first>
  <files>kb/templates/base.html</files>
  <action>
    Create `kb/templates/base.html` — the Jinja2 base template extended by all other pages. Use Jinja2's `{% block %}` mechanism with these blocks:
    - `{% block title %}` — overridden per page
    - `{% block og %}` — og:* meta tags (per-page override; default sensible site-level values)
    - `{% block extra_head %}` — for JSON-LD on detail pages
    - `{% block content %}` — main content area
    - `{% block extra_scripts %}` — for any page-specific JS

    Exact content (substitute Jinja2 syntax for actual rendering):

    ```html
    <!DOCTYPE html>
    <html lang="{{ lang|default('zh-CN') }}">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{% block title %}{{ 'site.title' | t('zh-CN') }} / {{ 'site.title' | t('en') }}{% endblock %}</title>
      <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
      <link rel="stylesheet" href="/static/style.css">
      {% block og %}
      <meta property="og:title" content="{{ 'site.title' | t('zh-CN') }}">
      <meta property="og:description" content="{{ 'site.tagline' | t('zh-CN') }}">
      <meta property="og:image" content="/static/VitaClaw-Logo-v0.png">
      <meta property="og:type" content="website">
      <meta property="og:locale" content="zh_CN">
      <meta property="og:url" content="{{ page_url|default('/') }}">
      {% endblock %}
      {% block extra_head %}{% endblock %}
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
          {% block content %}{% endblock %}
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
      {% block extra_scripts %}{% endblock %}
    </body>
    </html>
    ```

    Notes:
    - The dual-span pattern (`<span data-lang="zh">...</span><span data-lang="en">...</span>`) is used for EVERY chrome string. The CSS in plan kb-1-04 makes only one visible at a time based on `<html lang>`.
    - Lang toggle button text shows the OPPOSITE language (current=zh shows "EN" to switch to English, current=en shows "中" to switch to Chinese). Hence the asymmetric pairing: under `data-lang="zh"` shows `lang.toggle_to_en` (which has value "EN"); under `data-lang="en"` shows `lang.toggle_to_zh` (which has value "中").
    - `og:url` defaults to `/` — overridden per page.
    - `onerror="this.style.display='none'"` on the logo handles the placeholder-asset case from plan kb-1-04 gracefully.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; from kb.i18n import register_jinja2_filter; env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True); register_jinja2_filter(env); tpl = env.get_template('base.html'); print(tpl.render(lang='zh-CN', page_url='/')[:500])"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/base.html` exists with line count ≥ 40
    - Contains exact Jinja2 block declarations: `{% block title %}`, `{% block og %}`, `{% block extra_head %}`, `{% block content %}`, `{% block extra_scripts %}`
    - Contains string `<html lang="{{ lang|default('zh-CN') }}">`
    - Contains `link rel="stylesheet" href="/static/style.css"`
    - Contains `script src="/static/lang.js"`
    - Contains `og:title`, `og:description`, `og:image`, `og:type`, `og:locale`, `og:url`
    - Contains `class="lang-toggle"` (I18N-08)
    - Contains AT LEAST 4 `<span data-lang="zh">...</span><span data-lang="en">...</span>` dual-span pairs (chrome strings emitted in both langs)
    - Renders without Jinja2 error when `lang='zh-CN'` and `page_url='/'` are passed (verified by command above)
  </acceptance_criteria>
  <done>base.html chrome complete with all 5 blocks + og:* + i18n dual-span.</done>
</task>

<task type="auto">
  <name>Task 2: Write kb/templates/index.html — homepage extending base.html</name>
  <read_first>
    - kb/templates/base.html (Task 1 — extends this)
    - kb/locale/zh-CN.json (Look up keys: home.hero_title, home.hero_subtitle, home.section_latest, home.section_ask_cta, home.section_ask_desc)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Page set (EXPORT-03)"
  </read_first>
  <files>kb/templates/index.html</files>
  <action>
    Create `kb/templates/index.html`:

    ```html
    {% extends "base.html" %}

    {% block title %}{{ 'site.brand' | t('zh-CN') }} / {{ 'site.brand' | t('en') }} — {{ 'site.tagline' | t('zh-CN') }}{% endblock %}

    {% block content %}
    <section class="hero">
      <h1 class="lang-block" data-lang="zh">{{ 'home.hero_title' | t('zh-CN') }}</h1>
      <h1 class="lang-block" data-lang="en">{{ 'home.hero_title' | t('en') }}</h1>
      <p class="lang-block" data-lang="zh">{{ 'home.hero_subtitle' | t('zh-CN') }}</p>
      <p class="lang-block" data-lang="en">{{ 'home.hero_subtitle' | t('en') }}</p>
    </section>

    <section class="latest-articles">
      <h2>
        <span data-lang="zh">{{ 'home.section_latest' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.section_latest' | t('en') }}</span>
      </h2>
      {% for article in articles %}
      <article class="card article-card">
        <h3 class="article-card-title">
          <a href="/articles/{{ article.url_hash }}.html">{{ article.title }}</a>
        </h3>
        <div class="article-card-meta">
          <span class="lang-badge">
            {% if article.lang == 'zh-CN' %}{{ 'article.lang_zh' | t('zh-CN') }}{% elif article.lang == 'en' %}{{ 'article.lang_en' | t('zh-CN') }}{% else %}—{% endif %}
          </span>
          <span>{{ article.update_time }}</span>
          <span>{{ article.source }}</span>
        </div>
      </article>
      {% else %}
      <p>
        <span data-lang="zh">{{ 'articles.empty' | t('zh-CN') }}</span><span data-lang="en">{{ 'articles.empty' | t('en') }}</span>
      </p>
      {% endfor %}
    </section>

    <section class="ask-cta card">
      <h2>
        <span data-lang="zh">{{ 'home.section_ask_cta' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.section_ask_cta' | t('en') }}</span>
      </h2>
      <p class="lang-block" data-lang="zh">{{ 'home.section_ask_desc' | t('zh-CN') }}</p>
      <p class="lang-block" data-lang="en">{{ 'home.section_ask_desc' | t('en') }}</p>
      <a href="/ask/" class="btn">
        <span data-lang="zh">{{ 'nav.ask' | t('zh-CN') }} →</span><span data-lang="en">{{ 'nav.ask' | t('en') }} →</span>
      </a>
    </section>
    {% endblock %}
    ```

    Render context expectation: `articles` is a list of dicts with keys `title`, `url_hash`, `lang`, `update_time`, `source` — populated by export driver in plan kb-1-09 from ArticleRecord instances.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; from kb.i18n import register_jinja2_filter; env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True); register_jinja2_filter(env); tpl = env.get_template('index.html'); html = tpl.render(lang='zh-CN', articles=[{'title':'T','url_hash':'abc','lang':'zh-CN','update_time':'2026-01-01','source':'wechat'}], page_url='/'); print('OK' if 'home.hero_title' not in html else 'FAIL: i18n key leaked'); print(len(html))"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/index.html` exists; renders without Jinja2 error
    - Contains string `{% extends "base.html" %}`
    - Contains string `{% block content %}`
    - Contains string `for article in articles`
    - Contains string `articles.empty` (empty-state branch)
    - Contains string `home.section_ask_cta` (Ask AI CTA)
    - Renders WITHOUT exposing raw `home.hero_title` literal (i.e., the i18n filter resolves it)
    - Contains AT LEAST 3 dual-span chrome string pairs (data-lang="zh"/data-lang="en")
  </acceptance_criteria>
  <done>index.html renders with hero + article list + Ask CTA.</done>
</task>

<task type="auto">
  <name>Task 3: Write kb/templates/articles_index.html — article list with filter UI</name>
  <read_first>
    - kb/templates/base.html (Task 1)
    - kb/templates/index.html (Task 2 — pattern to mirror for article cards)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Page set (EXPORT-03)" — articles list page expectations + I18N-04 SSG-side filter UI (JS-only filtering of pre-rendered cards)
    - kb/locale/zh-CN.json (keys: articles.page_title, articles.filter_lang, articles.filter_source, articles.filter_all, articles.filter_lang_zh, articles.filter_lang_en, articles.filter_source_wechat, articles.filter_source_rss)
  </read_first>
  <files>kb/templates/articles_index.html</files>
  <action>
    Create `kb/templates/articles_index.html`:

    ```html
    {% extends "base.html" %}

    {% block title %}{{ 'articles.page_title' | t('zh-CN') }} / {{ 'articles.page_title' | t('en') }} — {{ 'site.brand' | t('zh-CN') }}{% endblock %}

    {% block content %}
    <h1>
      <span data-lang="zh">{{ 'articles.page_title' | t('zh-CN') }}</span><span data-lang="en">{{ 'articles.page_title' | t('en') }}</span>
    </h1>

    <div class="filter-bar card">
      <label>
        <span data-lang="zh">{{ 'articles.filter_lang' | t('zh-CN') }}:</span><span data-lang="en">{{ 'articles.filter_lang' | t('en') }}:</span>
        <select id="filter-lang" onchange="applyFilters()">
          <option value="">{{ 'articles.filter_all' | t('zh-CN') }} / {{ 'articles.filter_all' | t('en') }}</option>
          <option value="zh-CN">{{ 'articles.filter_lang_zh' | t('zh-CN') }}</option>
          <option value="en">{{ 'articles.filter_lang_en' | t('zh-CN') }}</option>
        </select>
      </label>
      <label>
        <span data-lang="zh">{{ 'articles.filter_source' | t('zh-CN') }}:</span><span data-lang="en">{{ 'articles.filter_source' | t('en') }}:</span>
        <select id="filter-source" onchange="applyFilters()">
          <option value="">{{ 'articles.filter_all' | t('zh-CN') }}</option>
          <option value="wechat">{{ 'articles.filter_source_wechat' | t('zh-CN') }} / {{ 'articles.filter_source_wechat' | t('en') }}</option>
          <option value="rss">RSS</option>
        </select>
      </label>
    </div>

    <div id="article-list">
      {% for article in articles %}
      <article class="card article-card" data-lang="{{ article.lang or 'unknown' }}" data-source="{{ article.source }}">
        <h3 class="article-card-title">
          <a href="/articles/{{ article.url_hash }}.html">{{ article.title }}</a>
        </h3>
        <div class="article-card-meta">
          <span class="lang-badge">
            {% if article.lang == 'zh-CN' %}{{ 'article.lang_zh' | t('zh-CN') }}{% elif article.lang == 'en' %}{{ 'article.lang_en' | t('zh-CN') }}{% else %}—{% endif %}
          </span>
          <span>{{ article.update_time }}</span>
          <span>{{ article.source }}</span>
        </div>
      </article>
      {% else %}
      <p id="empty-msg">
        <span data-lang="zh">{{ 'articles.empty' | t('zh-CN') }}</span><span data-lang="en">{{ 'articles.empty' | t('en') }}</span>
      </p>
      {% endfor %}
    </div>
    {% endblock %}

    {% block extra_scripts %}
    <script>
      // I18N-04 SSG-side: JS-only filter of pre-rendered cards. Reads ?lang= and ?source= from URL,
      // syncs select values, and toggles card visibility.
      (function () {
        var params = new URLSearchParams(window.location.search);
        var initLang = params.get('lang') || '';
        var initSrc = params.get('source') || '';
        var langSel = document.getElementById('filter-lang');
        var srcSel = document.getElementById('filter-source');
        if (langSel) langSel.value = initLang;
        if (srcSel) srcSel.value = initSrc;
        window.applyFilters = function () {
          var l = langSel ? langSel.value : '';
          var s = srcSel ? srcSel.value : '';
          var cards = document.querySelectorAll('#article-list .article-card');
          cards.forEach(function (c) {
            var matchLang = !l || c.getAttribute('data-lang') === l;
            var matchSrc = !s || c.getAttribute('data-source') === s;
            c.style.display = (matchLang && matchSrc) ? '' : 'none';
          });
        };
        applyFilters();
      })();
    </script>
    {% endblock %}
    ```

    Note: I18N-04 in kb-1 is the SSG-side filter. The actual server-side `/api/articles?lang=` filter (also I18N-04) lives in kb-3. The pattern in this template (data-lang attribute + JS show/hide) is what enables `?lang=en` to filter the pre-rendered list to English-only cards.

    NOTE on the data-lang attribute conflict: the article card uses `data-lang="zh-CN"` for FILTER purposes, but plan-04's CSS uses `[data-lang]` on inline spans for VISIBILITY toggling. These are two different uses of the same attribute. The CSS targets `html[lang="X"] [data-lang="Y"]` (descendant selector with html-lang prefix), so cards with data-lang as filter metadata are NOT affected by the chrome-toggling CSS. This is intentional but worth flagging for plan kb-1-09 (export driver) verification.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; from kb.i18n import register_jinja2_filter; env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True); register_jinja2_filter(env); tpl = env.get_template('articles_index.html'); html = tpl.render(lang='zh-CN', articles=[{'title':'T','url_hash':'abc','lang':'en','update_time':'2026','source':'rss'}], page_url='/articles/'); assert 'data-lang=\"en\"' in html and 'data-source=\"rss\"' in html; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/articles_index.html` exists; renders without Jinja2 error
    - Contains string `{% extends "base.html" %}`
    - Contains `id="filter-lang"` AND `id="filter-source"` (two filter controls)
    - Contains `data-lang="{{ article.lang or 'unknown' }}"` (cards carry filter attribute)
    - Contains `data-source="{{ article.source }}"`
    - Contains `applyFilters` JS function
    - Contains `URLSearchParams` (reads ?lang= and ?source=)
    - Renders with sample article data — output contains `data-source="rss"` (verified by command above)
  </acceptance_criteria>
  <done>articles_index.html with filter UI + JS-side card hiding.</done>
</task>

<task type="auto">
  <name>Task 4: Write kb/templates/ask.html — Q&A entry placeholder</name>
  <read_first>
    - kb/templates/base.html (Task 1)
    - kb/locale/zh-CN.json (keys: ask.page_title, ask.input_placeholder, ask.submit, ask.hot_questions, ask.disclaimer)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Page set (EXPORT-03)" — ask.html is a "Q&A entry placeholder (form posts to /api/synthesize later, kb-3 wires)"
  </read_first>
  <files>kb/templates/ask.html</files>
  <action>
    Create `kb/templates/ask.html` — placeholder Q&A entry page. The form does NOT actually submit yet (kb-3 wires the FastAPI backend); the JS just shows a placeholder message.

    ```html
    {% extends "base.html" %}

    {% block title %}{{ 'ask.page_title' | t('zh-CN') }} / {{ 'ask.page_title' | t('en') }} — {{ 'site.brand' | t('zh-CN') }}{% endblock %}

    {% block content %}
    <h1>
      <span data-lang="zh">{{ 'ask.page_title' | t('zh-CN') }}</span><span data-lang="en">{{ 'ask.page_title' | t('en') }}</span>
    </h1>

    <form id="ask-form" class="card" onsubmit="return submitAsk(event)">
      <textarea
        id="ask-input"
        rows="4"
        placeholder="{{ 'ask.input_placeholder' | t('zh-CN') }} / {{ 'ask.input_placeholder' | t('en') }}"
        required></textarea>
      <button type="submit" class="btn">
        <span data-lang="zh">{{ 'ask.submit' | t('zh-CN') }}</span><span data-lang="en">{{ 'ask.submit' | t('en') }}</span>
      </button>
    </form>

    <div id="ask-result" class="card" style="display: none; margin-top: 1rem;"></div>

    <p class="disclaimer">
      <span data-lang="zh">{{ 'ask.disclaimer' | t('zh-CN') }}</span><span data-lang="en">{{ 'ask.disclaimer' | t('en') }}</span>
    </p>
    {% endblock %}

    {% block extra_scripts %}
    <script>
      // Placeholder: real submission goes to /api/synthesize in kb-3. For SSG MVP show a "coming soon" message.
      function submitAsk(e) {
        e.preventDefault();
        var result = document.getElementById('ask-result');
        result.style.display = 'block';
        result.textContent = 'Q&A backend will be wired in kb-3 (FastAPI /api/synthesize). For now, this form is a placeholder.';
        return false;
      }
    </script>
    {% endblock %}
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; from kb.i18n import register_jinja2_filter; env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True); register_jinja2_filter(env); tpl = env.get_template('ask.html'); html = tpl.render(lang='zh-CN', page_url='/ask/'); assert 'ask-form' in html and 'ask-input' in html; print('OK')"    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; from kb.i18n import register_jinja2_filter; env = Environment(loader=FileSystemLoader('kb/templates'), autoescape=True); register_jinja2_filter(env); tpl = env.get_template('ask.html'); html = tpl.render(lang='zh-CN', page_url='/ask/'); assert 'ask-form' in html and 'ask-input' in html; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/ask.html` exists; renders without Jinja2 error
    - Contains string `{% extends "base.html" %}`
    - Contains `id="ask-form"` AND `id="ask-input"` AND `id="ask-result"`
    - Contains `function submitAsk` (placeholder JS handler)
    - Contains a `disclaimer` class element
    - Renders with sample context — output asserts `ask-form` + `ask-input` (verified above)
  </acceptance_criteria>
  <done>ask.html placeholder Q&A entry page complete.</done>
</task>

</tasks>

<verification>
- All 4 templates render via Jinja2 with the i18n filter registered (each verify command above exits 0)
- `kb/templates/base.html`, `index.html`, `articles_index.html`, `ask.html` all exist
- Jinja2 syntax valid: each template parsed without error
- Both languages emitted as inline dual-spans on chrome strings (CSS toggles visibility)
</verification>

<success_criteria>
- I18N-03 satisfied across 4 templates: chrome strings emit via t() filter in dual-span pattern
- I18N-08 satisfied: lang-toggle button present in base.html nav
- UI-04 satisfied: VitaClaw-Logo-v0.png referenced in nav (with onerror graceful degrade)
- UI-05 satisfied: og:title/description/image/type/locale/url emit on every page
- UI-07 partial: breadcrumb slot reserved in base.html; full breadcrumb on detail page is plan kb-1-08
- All 4 templates render without Jinja2 error
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-07-SUMMARY.md` documenting:
- 4 template files (line counts)
- Confirmed renders (each verify command exit code)
- Dual-span chrome string count (grep `data-lang="zh"` per file)
</output>
