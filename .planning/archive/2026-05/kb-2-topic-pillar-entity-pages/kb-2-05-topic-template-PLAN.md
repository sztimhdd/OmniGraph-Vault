---
phase: kb-2-topic-pillar-entity-pages
plan: 05
subsystem: ui-template
tags: [jinja2, template, topic-page, css, ui-spec]
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/topic.html
  - kb/static/style.css
autonomous: true
requirements:
  - TOPIC-01
  - TOPIC-04
  - TOPIC-05

must_haves:
  truths:
    - "kb/templates/topic.html exists, extends base.html, renders topic header + article list + sidebar"
    - "Topic h1 uses gradient text fill (kb-1 hero gradient 3-stop) — UI-SPEC §3.1 signature moment"
    - "Article list reuses kb-1 .article-card verbatim — NO new card variant"
    - "Sidebar lists 5 cooccurring entities (kb-1 .chip primitive + .chip--entity composition)"
    - "JSON-LD CollectionPage block emitted in {% block extra_head %}"
    - "Empty state uses kb-1 .empty-state block with 'inbox' icon"
    - "Sub-source filter chips (.chip--toggle) with aria-pressed + role='group' (TOPIC-03)"
    - "Responsive: desktop 1fr 280px grid; tablet 1fr 240px; mobile 1fr stacked + horizontal scroll on sidebar"
  artifacts:
    - path: "kb/templates/topic.html"
      provides: "NEW topic pillar template (extends base.html)"
      min_lines: 80
    - path: "kb/static/style.css"
      provides: "Topic-page CSS additions per UI-SPEC §3.1 (header gradient + grid layout + chip variants)"
      contains: "topic-pillar-header, topic-pillar-layout, topic-pillar-sidebar, chip--count, chip--toggle, chip--entity"
  key_links:
    - from: "kb/templates/topic.html"
      to: "kb/locale/{zh-CN,en}.json (plan 02 keys)"
      via: "Jinja2 filter {{ 'topic.X.name' | t(lang) }}"
      pattern: "topic\\..*\\| t"
    - from: "kb/templates/topic.html"
      to: "kb/templates/_icons.html (plan 03 icons)"
      via: "{{ icon('users', size=16) }} + {{ icon('articles', ...) }} + existing icons"
      pattern: "icon\\('users'"
    - from: "kb/templates/topic.html JSON-LD"
      to: "schema.org/CollectionPage"
      via: "{% block extra_head %} <script type='application/ld+json'>"
      pattern: "CollectionPage"
---

<objective>
Build NEW Jinja2 template `kb/templates/topic.html` per `kb-2-UI-SPEC.md §3.1` verbatim. Extends `kb-1/base.html`. Renders topic-pillar pages (`/topics/{slug}.html`) with header (gradient h1 + localized desc + count + sub-source filter), article list (reuses `.article-card`), sidebar (5 cooccurring entities), and CollectionPage JSON-LD.

Add CSS additions to `kb/static/style.css` per UI-SPEC §3.1 (token reuse — NO new `:root` vars per UI-SPEC §2.1).

Purpose: Plan 09 driver loops over 5 topics and renders this template into `kb/output/topics/{slug}.html`. Without the template, the driver has nothing to call.

Output: 1 new template file + ~70 lines of CSS appended to style.css.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-02-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-03-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-07-base-template-pages-PLAN.md
@kb/templates/base.html
@kb/templates/articles_index.html
@kb/templates/_icons.html
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/static/style.css
@kb/docs/10-DESIGN-DISCIPLINE.md
@kb/docs/05-KB2-ENTITY-SEO.md
@CLAUDE.md

<interfaces>
Render context expectation (provided by export driver in plan 09):

```python
context = {
    "lang": "zh-CN" | "en",            # UI chrome lang (drives <html lang>)
    "topic": {
        "slug": str,                    # 'agent' | 'cv' | 'llm' | 'nlp' | 'rag'
        "raw_topic": str,               # 'Agent' | 'CV' | ...
        "localized_name": str,          # from {{ 'topic.{slug}.name' | t(lang) }}
        "localized_desc": str,          # from {{ 'topic.{slug}.desc' | t(lang) }}
    },
    "articles": list[ArticleRecord],   # from topic_articles_query()
    "cooccurring_entities": list[EntityCount],  # from cooccurring_entities_in_topic()
    "page_url": str,                    # absolute URL for JSON-LD
    "origin": str,                      # site origin for breadcrumbs
}
```

Article-card structure (REUSE — copy from kb-1 articles_index.html — DO NOT modify):
The kb-1 `.article-card` has: meta (lang chip + source chip + date), title (h3 truncated), snippet (p clamped), readmore (span with arrow). Copy this structure verbatim into the article-list inside `topic-pillar-articles`.

Sidebar entity chip (.chip--entity) — UI-SPEC §3.1:
```html
<a class="chip chip--entity" href="/entities/{{ e.slug }}.html">
  {{ icon('tag', size=12) }}
  <span class="chip-label">{{ e.name }}</span>
  <span class="chip-count">{{ e.article_count }}</span>
</a>
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + create kb/templates/topic.html per UI-SPEC §3.1</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.1 (HTML skeleton verbatim — copy do NOT paraphrase)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §6 (CollectionPage JSON-LD verbatim)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (chip + glow + icon + state classes — REUSE verbatim)
    - kb/templates/base.html (extend pattern: `{% extends "base.html" %}`, blocks: `title`, `extra_head`, `content`)
    - kb/templates/articles_index.html (article-card markup to copy verbatim into topic article list)
    - kb/templates/_icons.html (verify `users`, `tag`, `articles`, `chevron-right`, `home`, `wechat`, `rss`, `inbox` exist after plan 03)
  </read_first>
  <files>kb/templates/topic.html</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes the named UI Skills BEFORE template authoring. The UI-SPEC §3.1 was authored under those Skills' discipline at UI-SPEC time; this task re-invokes them as the Skill output is being translated to template code.

    Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.1 (topic pillar page) into a Jinja2 template structure. Verify the design contract is preserved: (1) gradient text fill on h1 only — sidebar/article-list/chips are neutral; (2) restraint principle — no new card variants, .article-card reused verbatim; (3) sub-source filter as chip toggle with aria-pressed (NOT native select) per TOPIC-03 + UI-SPEC §7; (4) sidebar 5 cooccurring entities use .chip--entity composition (NO new entity-chip-card variant); (5) responsive grid: desktop 1fr 280px / tablet 1fr 240px / mobile 1fr stacked with horizontal scroll on sidebar; (6) empty state reuses kb-1 .empty-state with 'inbox' icon. Output: confirm the template structure honors all 6 constraints + CollectionPage JSON-LD per UI-SPEC §6.")

    Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.1 verbatim into kb/templates/topic.html. Reuse kb-1 redesigned tokens exclusively — chip / icon / state classes. Article list reuses kb-1 .article-card markup from articles_index.html (copy structure verbatim, do NOT re-design). Sub-source filter chips use .chip--toggle (defined in CSS task) with aria-pressed='true|false' + role='group' + aria-label. Empty state path delegates to kb-1 .empty-state pattern. JSON-LD CollectionPage block in {% block extra_head %}. Breadcrumb: Home > Topics > [topic name] using kb-1 .breadcrumb pattern + 'home' / 'chevron-right' icons. No inline <style> — all CSS goes to style.css in Task 2.")

    **Create `kb/templates/topic.html`** with the EXACT skeleton from UI-SPEC §3.1, expanded to be a working Jinja2 template:

    ```jinja2
    {% extends "base.html" %}
    {% set page_lang = lang %}
    {% block title %}{{ topic.localized_name }} — {{ 'site.brand' | t(lang) }}{% endblock %}

    {% block extra_head %}
    <meta name="description" content="{{ topic.localized_desc }}">
    <meta property="og:title" content="{{ topic.localized_name }}">
    <meta property="og:description" content="{{ topic.localized_desc }}">
    <meta property="og:type" content="website">
    <meta property="og:locale" content="{{ lang }}">
    <link rel="canonical" href="{{ page_url }}">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      "name": {{ topic.localized_name | tojson }},
      "description": {{ topic.localized_desc | tojson }},
      "url": {{ page_url | tojson }},
      "inLanguage": {{ lang | tojson }},
      "numberOfItems": {{ articles | length }},
      "breadcrumb": {
        "@type": "BreadcrumbList",
        "itemListElement": [
          {"@type": "ListItem", "position": 1, "name": "Home", "item": {{ (origin ~ "/") | tojson }}},
          {"@type": "ListItem", "position": 2, "name": "Topics", "item": {{ (origin ~ "/topics/") | tojson }}},
          {"@type": "ListItem", "position": 3, "name": {{ topic.localized_name | tojson }}}
        ]
      }
    }
    </script>
    {% endblock %}

    {% block content %}
    <main>
      <div class="container">
        <nav class="breadcrumb" aria-label="breadcrumb">
          <a href="/">{{ icon('home', size=14) }} {{ 'breadcrumb.home' | t(lang) }}</a>
          {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
          <a href="/topics/">{{ 'breadcrumb.topics' | t(lang) }}</a>
          {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
          <span class="breadcrumb__current">{{ topic.localized_name }}</span>
        </nav>

        <header class="topic-pillar-header">
          <h1 class="topic-pillar-header__title">{{ topic.localized_name }}</h1>
          <p class="topic-pillar-header__desc">{{ topic.localized_desc }}</p>
          <div class="topic-pillar-header__meta">
            <span class="chip chip--count">
              {{ icon('articles', size=13) }}
              {{ articles | length }} {{ 'topic.article_count_label' | t(lang) }}
            </span>
            <div class="topic-pillar-header__filter" role="group" aria-label="{{ 'articles.filter.source' | t(lang) if 'articles.filter.source' else 'Source filter' }}">
              <button class="chip chip--toggle is-active" data-source="all" aria-pressed="true">All</button>
              <button class="chip chip--toggle" data-source="wechat" aria-pressed="false">
                {{ icon('wechat', size=13) }} WeChat
              </button>
              <button class="chip chip--toggle" data-source="rss" aria-pressed="false">
                {{ icon('rss', size=13) }} RSS
              </button>
            </div>
          </div>
        </header>

        <div class="topic-pillar-layout">
          <section class="topic-pillar-articles" aria-label="{{ topic.localized_name }}">
            {% if articles %}
            <div class="article-list">
              {% for a in articles %}
              <a class="article-card" href="/articles/{{ a.url_hash }}.html" data-source="{{ a.source }}">
                <div class="article-card-meta">
                  {% if a.lang == 'zh-CN' %}
                  <span class="lang-badge" data-lang="zh-CN">{{ 'article.lang_zh' | t(lang) }}</span>
                  {% elif a.lang == 'en' %}
                  <span class="lang-badge" data-lang="en">{{ 'article.lang_en' | t(lang) }}</span>
                  {% else %}
                  <span class="lang-badge" data-lang="unknown">{{ 'article.lang_unknown' | t(lang) }}</span>
                  {% endif %}
                  {% if a.source == 'wechat' %}
                  <span class="source-chip">{{ icon('wechat', size=12) }} {{ 'source.wechat' | t(lang) }}</span>
                  {% else %}
                  <span class="source-chip">{{ icon('rss', size=12) }} RSS</span>
                  {% endif %}
                  <span class="article-card-date">{{ a.update_time_human }}</span>
                </div>
                <h3 class="article-card-title">{{ a.title }}</h3>
                {% if a.snippet %}
                <p class="article-card-snippet">{{ a.snippet }}</p>
                {% endif %}
                <span class="article-card-readmore">
                  {{ 'article.read_more' | t(lang) }} {{ icon('arrow-right', size=14) }}
                </span>
              </a>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
              {{ icon('inbox', size=32) }}
              <h2>{{ 'topic.empty_title' | t(lang) }}</h2>
              <p>{{ 'topic.empty_hint' | t(lang) }}</p>
            </div>
            {% endif %}
          </section>

          {% if cooccurring_entities %}
          <aside class="topic-pillar-sidebar" aria-label="{{ 'topic.cooccurring_entities_title' | t(lang) }}">
            <h2 class="topic-pillar-sidebar__title">
              {{ icon('users', size=16) }}
              {{ 'topic.cooccurring_entities_title' | t(lang) }}
            </h2>
            <ul class="topic-pillar-sidebar__list">
              {% for e in cooccurring_entities %}
              <li>
                <a class="chip chip--entity" href="/entities/{{ e.slug }}.html">
                  {{ icon('tag', size=12) }}
                  <span class="chip-label">{{ e.name }}</span>
                  <span class="chip-count">{{ e.article_count }}</span>
                </a>
              </li>
              {% endfor %}
            </ul>
          </aside>
          {% endif %}
        </div>
      </div>
    </main>
    {% endblock %}
    ```

    Surgical-changes principle: this is a NEW file. Do not touch base.html, articles_index.html, or any other existing template.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); tpl = env.get_template('topic.html'); print('parse OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/templates/topic.html`
    - `grep -q "topic-pillar-header" kb/templates/topic.html` (UI-SPEC accept #3)
    - `grep -q "topic-pillar-layout" kb/templates/topic.html` (UI-SPEC accept #4)
    - `grep -q "topic-pillar-sidebar" kb/templates/topic.html` (UI-SPEC accept #5)
    - `grep -q "chip--entity" kb/templates/topic.html` (UI-SPEC accept #6)
    - `grep -q "article-card" kb/templates/topic.html` (UI-SPEC accept #7 — reuse, no new variant)
    - `grep -q "CollectionPage" kb/templates/topic.html` (UI-SPEC accept #8 — JSON-LD)
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-05-topic-template-PLAN.md`
    - `grep -q "Skill(skill=\"frontend-design\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-05-topic-template-PLAN.md`
    - Jinja2 parses without error (verify command above)
    - `grep -q "{% extends \"base.html\" %}" kb/templates/topic.html`
  </acceptance_criteria>
  <done>kb/templates/topic.html exists, parses, follows UI-SPEC §3.1 verbatim with all required structural classes + JSON-LD.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Append topic-pillar CSS to kb/static/style.css per UI-SPEC §3.1</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §2.1 (NO new :root tokens — hard gate)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.1 (CSS block verbatim)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md §2 (locked tokens — must reuse)
    - kb/static/style.css (kb-1 baseline — APPEND only, do NOT modify existing rules)
  </read_first>
  <files>kb/static/style.css</files>
  <action>
    Skill(skill="frontend-design", args="Append CSS for the topic pillar layout to kb/static/style.css. Verbatim from kb-2-UI-SPEC.md §3.1 'New CSS' block. Hard constraints: ZERO new :root variables (UI-SPEC §2.1), use only existing kb-1 tokens (--text, --text-secondary, --text-tertiary, --accent, --accent-green, --accent-blue-soft, --accent-blue-30, --accent-green-30, --border, --motion-base, --bg-card-hover). Selectors: .topic-pillar-header, .topic-pillar-header__title (gradient signature moment), .topic-pillar-header__desc, .topic-pillar-header__meta, .topic-pillar-layout (CSS grid), .topic-pillar-sidebar__title, .topic-pillar-sidebar__list. Chip variants: .chip--count, .chip--toggle (with [aria-pressed='true'] + .is-active), .chip--entity. Responsive @media: max-width 1023 (240px sidebar) + max-width 767 (1fr stacked + horizontal scroll on sidebar list).")

    **Append the following to `kb/static/style.css`** (verbatim from UI-SPEC §3.1):

    ```css
    /* ============================================================
       kb-2 — Topic Pillar Page (UI-SPEC §3.1)
       ZERO new :root tokens — composes kb-1 locked tokens only.
       ============================================================ */

    .topic-pillar-header {
      padding: 2rem 0 1.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2rem;
    }
    .topic-pillar-header__title {
      font-size: clamp(1.875rem, 4vw, 2.75rem);
      font-weight: 700;
      letter-spacing: -0.02em;
      /* Signature moment — gradient text fill (reuses kb-1 hero gradient stops) */
      background: linear-gradient(135deg, var(--text) 0%, var(--accent) 50%, var(--accent-green) 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      margin-bottom: 0.75rem;
    }
    .topic-pillar-header__desc {
      color: var(--text-secondary);
      font-size: 1.0625rem;
      line-height: 1.55;
      max-width: 64ch;
      margin-bottom: 1.25rem;
    }
    .topic-pillar-header__meta {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    .topic-pillar-header__filter {
      display: inline-flex;
      gap: 0.375rem;
      flex-wrap: wrap;
    }
    .topic-pillar-layout {
      display: grid;
      grid-template-columns: 1fr 280px;
      gap: 2rem;
    }
    @media (max-width: 1023px) {
      .topic-pillar-layout { grid-template-columns: 1fr 240px; }
    }
    @media (max-width: 767px) {
      .topic-pillar-layout { grid-template-columns: 1fr; }
      .topic-pillar-sidebar__list {
        display: flex; flex-direction: row; gap: 0.5rem;
        overflow-x: auto; padding-bottom: 0.5rem;
      }
    }
    .topic-pillar-sidebar__title {
      font-size: 0.875rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-tertiary);
      margin-bottom: 0.75rem;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }
    .topic-pillar-sidebar__list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    /* New chip variants — composed from kb-1 .chip primitive */
    .chip--count {
      cursor: default;
      pointer-events: none;
      border-color: var(--border);
      color: var(--text-secondary);
    }
    .chip--toggle[aria-pressed="true"],
    .chip--toggle.is-active {
      background: var(--accent-blue-soft);
      color: var(--accent);
      border-color: var(--accent-blue-30);
    }
    .chip--entity {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      width: 100%;
      justify-content: space-between;
    }
    .chip--entity .chip-label { flex: 1; text-align: left; }
    .chip--entity .chip-count {
      color: var(--text-tertiary);
      font-variant-numeric: tabular-nums;
      font-size: 0.75rem;
    }
    @media (max-width: 767px) {
      .chip--entity { width: auto; }
    }
    ```

    **Token-discipline regression guard** (UI-SPEC accept #34): no new `:root` vars introduced. Verify by `grep -E "^\s*--" kb/static/style.css | wc -l` BEFORE and AFTER this task — count must be unchanged.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import re; css = open('kb/static/style.css', encoding='utf-8').read(); assert '.topic-pillar-header' in css; assert '.topic-pillar-layout' in css; assert '.chip--entity' in css; assert '.chip--toggle' in css; assert '.chip--count' in css; print('CSS OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "topic-pillar-header" kb/static/style.css`
    - `grep -q "topic-pillar-layout" kb/static/style.css`
    - `grep -q "topic-pillar-sidebar" kb/static/style.css`
    - `grep -q "chip--count" kb/static/style.css`
    - `grep -q "chip--toggle" kb/static/style.css`
    - `grep -q "chip--entity" kb/static/style.css`
    - Token discipline preserved: count of `^\s*--[a-z]` lines in style.css unchanged from kb-1 baseline
    - File still under the kb-2 LOC budget (UI-SPEC accept #35: `wc -l < kb/static/style.css <= 1937`)
  </acceptance_criteria>
  <done>~70 LOC appended; topic-pillar CSS classes present; zero new :root tokens.</done>
</task>

</tasks>

<verification>
- topic.html parses as Jinja2 + extends base.html
- All 8 UI-SPEC accept patterns for topic page present
- CSS classes appear in style.css; zero new :root tokens
- Skill(skill="ui-ux-pro-max") and Skill(skill="frontend-design") strings literal in PLAN.md
</verification>

<success_criteria>
- TOPIC-01 enabled: template ready for plan 09 driver to render `/topics/{slug}.html` × 5
- TOPIC-04 enabled: CollectionPage JSON-LD emitted in extra_head
- TOPIC-05 enabled: cooccurring entities sidebar wired
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-05-SUMMARY.md` documenting:
- topic.html LOC + structural class checklist
- CSS additions LOC + token discipline confirmation (zero new :root)
- Literal Skill(skill="ui-ux-pro-max") + Skill(skill="frontend-design") strings (regex match for kb/docs/10-DESIGN-DISCIPLINE.md Check 1)
- Foundation for plan 09 (driver loop renders this template)
</output>
