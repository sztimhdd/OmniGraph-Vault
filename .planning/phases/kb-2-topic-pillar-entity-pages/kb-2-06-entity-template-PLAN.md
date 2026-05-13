---
phase: kb-2-topic-pillar-entity-pages
plan: 06
subsystem: ui-template
tags: [jinja2, template, entity-page, css, ui-spec]
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/entity.html
  - kb/static/style.css
autonomous: true
requirements:
  - ENTITY-01
  - ENTITY-04

must_haves:
  truths:
    - "kb/templates/entity.html exists, extends base.html, renders entity header + article list"
    - "Entity h1 is SOLID --text color (no gradient — restraint principle, UI-SPEC §3.2)"
    - "Lang-distribution chip row (zh-CN blue / en green / unknown grey) is the entity page signature moment"
    - "Article list reuses kb-1 .article-card verbatim — NO new card variant"
    - "JSON-LD generic Thing schema emitted in {% block extra_head %} (UI-SPEC §6)"
    - "alternateName is empty array for v2.0 (TYPED-* deferred to v2.1 per UI-SPEC §6)"
    - "Empty state uses kb-1 .empty-state with 'inbox' icon"
  artifacts:
    - path: "kb/templates/entity.html"
      provides: "NEW entity page template (extends base.html)"
      min_lines: 60
    - path: "kb/static/style.css"
      provides: "Entity-page CSS additions per UI-SPEC §3.2 (entity-header + entity-lang-distribution)"
      contains: "entity-header, entity-header__title, entity-lang-distribution"
  key_links:
    - from: "kb/templates/entity.html"
      to: "kb/locale/{zh-CN,en}.json (plan 02 keys)"
      via: "{{ 'entity.lang_distribution_aria' | t(lang) }}, {{ 'breadcrumb.entities' | t(lang) }}, etc."
      pattern: "entity\\..*\\| t|breadcrumb\\.entities"
    - from: "kb/templates/entity.html JSON-LD"
      to: "schema.org/Thing"
      via: "{% block extra_head %} <script type='application/ld+json'>"
      pattern: '@type.*Thing'
---

<objective>
Build NEW Jinja2 template `kb/templates/entity.html` per `kb-2-UI-SPEC.md §3.2` verbatim. Extends `kb-1/base.html`. Renders entity pages (`/entities/{slug}.html`) with header (solid h1 + lang-distribution chip row + article count), article list (reuses `.article-card`), and Thing JSON-LD.

Append entity-page CSS to `kb/static/style.css` (token reuse — ZERO new :root vars per UI-SPEC §2.1).

Purpose: Plan 09 driver loops over qualifying entities (≥KB_ENTITY_MIN_FREQ=5) and renders this template into `kb/output/entities/{slug}.html` (~91 pages on Hermes prod).

Output: 1 new template file + ~30 LOC CSS appended to style.css.
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
    "lang": "zh-CN" | "en",            # UI chrome lang
    "entity": {
        "name": str,                    # display name (raw from extracted_entities)
        "slug": str,                    # URL slug (slugify_entity_name output)
        "article_count": int,           # total article count
        "lang_zh": int,                 # KOL+RSS where article.lang == 'zh-CN'
        "lang_en": int,
        "lang_unknown": int,
    },
    "articles": list[ArticleRecord],   # from entity_articles_query()
    "page_url": str,
    "origin": str,
}
```

Article-card markup REUSED from kb-1 articles_index.html (same as plan 05). The pre-render context (snippet, url_hash, update_time_human, etc.) is computed by plan 09 driver — template just reads attributes.

JSON-LD Thing (UI-SPEC §6 verbatim):
```json
{
  "@context": "https://schema.org",
  "@type": "Thing",
  "name": "{{ entity.name }}",
  "url": "{{ page_url }}",
  "alternateName": []
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + create kb/templates/entity.html per UI-SPEC §3.2</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.2 (HTML skeleton verbatim)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §6 (Thing JSON-LD verbatim)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (lang-badge classes — REUSE: zh-CN blue, en green, unknown grey)
    - kb/templates/base.html (extend pattern)
    - kb/templates/articles_index.html (article-card markup to copy verbatim)
    - kb/templates/_icons.html (verify articles + chevron-right + home + inbox icons exist)
  </read_first>
  <files>kb/templates/entity.html</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes the named UI Skills BEFORE template authoring:

    Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.2 (entity page) into a Jinja2 template structure. Verify the design contract is preserved: (1) RESTRAINT — entity h1 is SOLID --text color (NO gradient — entities are data, not hero copy per UI-SPEC §1 'per-page signature moment' table); (2) signature moment is the lang-distribution chip row, NOT the title; (3) chip row uses kb-1 .lang-badge classes verbatim (zh-CN blue / en green / unknown grey) — composes existing lang-badge styling; (4) article list reuses kb-1 .article-card; (5) skip lang-badge chips with count=0 (don't render zero-density buckets); (6) JSON-LD Thing uses generic @type only — NO Person/Organization/SoftwareApplication typing (UI-SPEC §6 + REQUIREMENTS-KB-v2 ENTITY-04 reasoning); (7) word-break: break-word on h1 for long Latin entity names (LangChain, AutoGen). Confirm template structure honors all 7 constraints.")

    Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.2 verbatim into kb/templates/entity.html. Reuse kb-1 redesigned tokens exclusively. Article list reuses kb-1 .article-card markup from articles_index.html (copy structure verbatim, do NOT re-design). Lang-distribution chip row: 3 .lang-badge chips with data-lang='zh-CN'|'en'|'unknown' attribute (kb-1 classes color-code via attribute selector). Each chip wrapped with a {% if entity.lang_X > 0 %} guard. role='group' + localized aria-label on the wrapping div. Empty state path delegates to kb-1 .empty-state. JSON-LD Thing in {% block extra_head %} per UI-SPEC §6 verbatim — generic Thing only, alternateName: []. Breadcrumb: Home > Entities > [entity name]. No inline <style>.")

    **Create `kb/templates/entity.html`:**

    ```jinja2
    {% extends "base.html" %}
    {% set page_lang = lang %}
    {% block title %}{{ entity.name }} — {{ 'site.brand' | t(lang) }}{% endblock %}

    {% block extra_head %}
    <meta name="description" content="{{ entity.name }} — {{ entity.article_count }} {{ 'entity.article_count_label' | t(lang) }}">
    <meta property="og:title" content="{{ entity.name }}">
    <meta property="og:type" content="website">
    <meta property="og:locale" content="{{ lang }}">
    <link rel="canonical" href="{{ page_url }}">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Thing",
      "name": {{ entity.name | tojson }},
      "url": {{ page_url | tojson }},
      "alternateName": []
    }
    </script>
    {% endblock %}

    {% block content %}
    <main>
      <div class="container">
        <nav class="breadcrumb" aria-label="breadcrumb">
          <a href="/">{{ icon('home', size=14) }} {{ 'breadcrumb.home' | t(lang) }}</a>
          {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
          <a href="/entities/">{{ 'breadcrumb.entities' | t(lang) }}</a>
          {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
          <span class="breadcrumb__current">{{ entity.name }}</span>
        </nav>

        <header class="entity-header">
          <h1 class="entity-header__title">{{ entity.name }}</h1>
          <div class="entity-header__meta">
            <span class="chip chip--count">
              {{ icon('articles', size=13) }}
              {{ entity.article_count }} {{ 'entity.article_count_label' | t(lang) }}
            </span>
            <div class="entity-lang-distribution" role="group"
                 aria-label="{{ 'entity.lang_distribution_aria' | t(lang) }}">
              {% if entity.lang_zh > 0 %}
              <span class="lang-badge" data-lang="zh-CN">
                {{ entity.lang_zh }} {{ 'article.lang_zh' | t(lang) }}
              </span>
              {% endif %}
              {% if entity.lang_en > 0 %}
              <span class="lang-badge" data-lang="en">
                {{ entity.lang_en }} {{ 'article.lang_en' | t(lang) }}
              </span>
              {% endif %}
              {% if entity.lang_unknown > 0 %}
              <span class="lang-badge" data-lang="unknown">
                {{ entity.lang_unknown }} {{ 'article.lang_unknown' | t(lang) }}
              </span>
              {% endif %}
            </div>
          </div>
        </header>

        <section class="entity-articles" aria-label="{{ entity.name }}">
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
            <h2>{{ 'entity.empty_title' | t(lang) }}</h2>
            <p>{{ 'entity.empty_hint' | t(lang) }}</p>
          </div>
          {% endif %}
        </section>
      </div>
    </main>
    {% endblock %}
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); tpl = env.get_template('entity.html'); print('parse OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/templates/entity.html`
    - `grep -q "entity-header" kb/templates/entity.html` (UI-SPEC accept #9)
    - `grep -q "entity-lang-distribution" kb/templates/entity.html` (UI-SPEC accept #10)
    - `grep -q "lang-badge" kb/templates/entity.html` (UI-SPEC accept #11 — kb-1 reuse)
    - `grep -q "article-card" kb/templates/entity.html` (UI-SPEC accept #12 — kb-1 reuse)
    - `grep -qE '@type.{0,4}.{0,4}Thing' kb/templates/entity.html` (UI-SPEC accept #13)
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-06-entity-template-PLAN.md`
    - `grep -q "Skill(skill=\"frontend-design\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-06-entity-template-PLAN.md`
    - Jinja2 parses without error
    - `grep -q "{% extends \"base.html\" %}" kb/templates/entity.html`
    - Negative: `grep -q "Person\|Organization\|SoftwareApplication" kb/templates/entity.html` returns 0 (UI-SPEC §6 — generic Thing only)
  </acceptance_criteria>
  <done>kb/templates/entity.html exists, parses, follows UI-SPEC §3.2 verbatim with all required structural classes + Thing JSON-LD.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Append entity-page CSS to kb/static/style.css per UI-SPEC §3.2</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §2.1 (NO new :root tokens)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.2 (CSS verbatim)
    - kb/static/style.css (kb-1 baseline + plan 05 additions — APPEND only)
  </read_first>
  <files>kb/static/style.css</files>
  <action>
    Skill(skill="frontend-design", args="Append entity-page CSS to kb/static/style.css. Verbatim from kb-2-UI-SPEC.md §3.2 'Header — restraint principle' block. ZERO new :root vars. Selectors: .entity-header, .entity-header__title (SOLID --text color, NOT gradient), .entity-header__meta, .entity-lang-distribution. Use word-break: break-word on h1 for long Latin entity names. clamp(1.5rem, 3vw, 2.25rem) for h1 size — slightly smaller than topic page (which is signature h1).")

    **Append to `kb/static/style.css`** (verbatim from UI-SPEC §3.2):

    ```css
    /* ============================================================
       kb-2 — Entity Page (UI-SPEC §3.2)
       Entity h1 is SOLID color — restraint principle (no gradient).
       Lang-distribution chip row is the page's signature moment.
       ============================================================ */

    .entity-header {
      padding: 2rem 0 1.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2rem;
    }
    .entity-header__title {
      font-size: clamp(1.5rem, 3vw, 2.25rem);
      font-weight: 700;
      letter-spacing: -0.015em;
      color: var(--text);    /* SOLID — entities are data, not hero copy */
      margin-bottom: 0.75rem;
      word-break: break-word;
    }
    .entity-header__meta {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    .entity-lang-distribution {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 0.375rem;
      align-items: center;
    }
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "css = open('kb/static/style.css', encoding='utf-8').read(); assert '.entity-header' in css; assert '.entity-lang-distribution' in css; assert 'word-break: break-word' in css; print('CSS OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "entity-header" kb/static/style.css`
    - `grep -q "entity-lang-distribution" kb/static/style.css`
    - `grep -q "word-break: break-word" kb/static/style.css`
    - Token discipline preserved: count of `^\s*--[a-z]` lines unchanged
    - File still under kb-2 LOC budget: `[ "$(wc -l < kb/static/style.css)" -le 1937 ]`
  </acceptance_criteria>
  <done>~25 LOC appended; entity-page CSS classes present; zero new :root tokens.</done>
</task>

</tasks>

<verification>
- entity.html parses + extends base.html + renders all UI-SPEC §3.2 elements
- CSS classes appear in style.css; zero new :root tokens
- Skill invocations literal in PLAN.md
- Generic Thing JSON-LD only (no Person/Org typing)
</verification>

<success_criteria>
- ENTITY-01 enabled: template ready for plan 09 driver to render `/entities/{slug}.html` × ~91
- ENTITY-04 enabled: Thing JSON-LD emitted with @type=Thing + alternateName=[]
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-06-SUMMARY.md` documenting:
- entity.html LOC + structural class checklist
- CSS additions LOC + token discipline confirmation
- Literal Skill(skill="ui-ux-pro-max") + Skill(skill="frontend-design") strings
- Foundation for plan 09 (driver renders this template)
</output>
