---
phase: kb-2-topic-pillar-entity-pages
plan: 08
subsystem: ui-template
tags: [jinja2, template, article-detail, css, ui-spec]
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/article.html
  - kb/static/style.css
autonomous: true
requirements:
  - LINK-01
  - LINK-02

must_haves:
  truths:
    - "kb/templates/article.html wraps existing .article-body in .article-detail-layout grid container"
    - "Adds .article-aside sibling to .article-body (NOT nested) per UI-SPEC §3.4 'Position rule'"
    - "Aside contains 2 conditional sections: related_entities (3-5 chips) + related_topics (1-3 chips)"
    - "Section MUST NOT render if its list is empty (no orphan headings)"
    - "Desktop ≥1024px: grid 1fr 280px with sticky aside (top: 88px); Mobile <1024px: stacked"
    - "Existing kb-1 .article-footer Ask AI CTA UNTOUCHED — surgical changes principle"
    - "ZERO new chip variants — .chip--entity (defined in plan 05) and .chip--topic (NEW minor variant only adds hover hue) reuse .chip"
  artifacts:
    - path: "kb/templates/article.html"
      provides: "EXTENDED with .article-detail-layout wrapper + .article-aside containing related-entities + related-topics rows"
      contains: "article-detail-layout, article-aside, related_entities, related_topics, chip--topic"
    - path: "kb/static/style.css"
      provides: "+CSS for .article-detail-layout grid + .article-aside sticky + .chip--topic hover variant"
  key_links:
    - from: "kb/templates/article.html related-entities chips"
      to: "kb/templates/entity.html (plan 06) via /entities/{slug}.html"
      via: "anchor href"
      pattern: "/entities/.*\\.html"
    - from: "kb/templates/article.html related-topics chips"
      to: "kb/templates/topic.html (plan 05) via /topics/{slug}.html"
      via: "anchor href"
      pattern: "/topics/.*\\.html"
---

<objective>
Extend `kb/templates/article.html` per `kb-2-UI-SPEC.md §3.4` — wrap `.article-body` in `.article-detail-layout` grid + add `.article-aside` sibling with related_entities + related_topics chip rows. Sticky on desktop ≥1024px, stacked on mobile. Zero modifications to `.article-footer` Ask AI CTA.

Append article-aside CSS to `kb/static/style.css`.

Purpose: LINK-01 + LINK-02 surface entity + topic discovery from inside an article — sidebar on desktop, footer-ish below body on mobile.

Output: 1 file extended (article.html) + ~50 LOC CSS appended.
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
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-08-article-detail-template-PLAN.md
@kb/templates/article.html
@kb/templates/_icons.html
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/static/style.css
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Render context expectation (extended by plan 09 driver):

```python
context = {
    # ... existing kb-1 context ...
    "related_entities": list[{"name": str, "slug": str}],   # 3-5 from related_entities_for_article()
    "related_topics": list[{"slug": str, "localized_name": str}],  # 1-3 from related_topics_for_article()
}
```

Empty-state contract: if `related_entities` is empty, the section MUST NOT render (no empty heading). Same for `related_topics`. If BOTH are empty, the entire `.article-aside` skip via outer `{% if %}`.

Position rule (UI-SPEC §3.4): aside is SIBLING to .article-body inside `.article-detail-layout`. NOT nested inside body. NOT inside .article-footer. The kb-1 .article-footer Ask AI CTA stays UNCHANGED below the layout container.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + extend article.html with .article-detail-layout + .article-aside per UI-SPEC §3.4</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.4 (HTML skeleton verbatim) + §4.5 (desktop diagram) + §4.6 (mobile diagram)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (chip + state baseline rules)
    - kb/templates/article.html (full file — find existing `.article-body` block + `.article-footer`; wrap body in layout container, do NOT touch footer)
    - kb/templates/_icons.html (verify tag + folder-tag icons exist after plan 03)
  </read_first>
  <files>kb/templates/article.html</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes the named UI Skills:

    Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.4 (article detail related-link rows) into Jinja2 markup. Verify design constraints: (1) Position rule — .article-aside is SIBLING to .article-body inside .article-detail-layout, NOT nested in body, NOT in footer; (2) restraint — kb-1 .article-footer Ask AI .glow CTA remains the page's signature moment; new aside is subdued chips (no glow); (3) two conditional sections inside aside (related_entities + related_topics) — empty list means section MUST NOT render (no orphan heading); (4) Desktop ≥1024px: 2-col grid (1fr 280px) with sticky aside (top: 88px = kb-1 64px nav + 24px breathing); (5) Mobile <1024px: 1-col stacked, aside flows below body; (6) chip-row for entities uses .chip--entity (defined plan 05); chip-row for topics uses NEW .chip--topic minor variant — only adds accent-green hover hue distinguishing from .chip--entity; (7) prefers-reduced-motion: sticky positioning is fine (no animation), but no scroll-behavior: smooth applied here.")

    Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.4 verbatim into kb/templates/article.html. Surgical wrap: locate the existing `.article-body` block. WRAP it + a new `<aside class='article-aside'>` in `<div class='article-detail-layout'>`. Do NOT touch the existing .article-footer — it sits BELOW the layout container, unchanged. Aside contains 2 conditional `<section class='article-aside__group'>` blocks: related_entities (chips with tag icon) + related_topics (chips with folder-tag icon). Empty-list guard: `{% if related_entities %}` / `{% if related_topics %}`. .chip--topic is a NEW minor variant — only `:hover { border-color: var(--accent-green-30); color: var(--accent-green); }` per UI-SPEC §3.4. ZERO modifications to article body markdown rendering, JSON-LD, breadcrumb, or any other kb-1 article.html element.")

    **Edit `kb/templates/article.html`:** Locate the existing `<article class="article-body">` block. Wrap it + add aside sibling (verbatim from UI-SPEC §3.4):

    ```jinja2
    <div class="article-detail-layout">
      <article class="article-body">
        {{ body_html | safe }}
      </article>

      {% if related_entities or related_topics %}
      <aside class="article-aside" aria-label="{{ 'article.related_aria' | t(lang) }}">
        {% if related_entities %}
        <section class="article-aside__group">
          <h2 class="article-aside__heading">
            {{ icon('tag', size=14) }}
            <span data-lang="zh">{{ 'article.related_entities' | t('zh-CN') }}</span><span data-lang="en">{{ 'article.related_entities' | t('en') }}</span>
          </h2>
          <ul class="article-aside__list" role="list">
            {% for e in related_entities %}
            <li>
              <a class="chip chip--entity" href="/entities/{{ e.slug }}.html">
                {{ icon('tag', size=12) }}
                <span class="chip-label">{{ e.name }}</span>
              </a>
            </li>
            {% endfor %}
          </ul>
        </section>
        {% endif %}

        {% if related_topics %}
        <section class="article-aside__group">
          <h2 class="article-aside__heading">
            {{ icon('folder-tag', size=14) }}
            <span data-lang="zh">{{ 'article.related_topics' | t('zh-CN') }}</span><span data-lang="en">{{ 'article.related_topics' | t('en') }}</span>
          </h2>
          <ul class="article-aside__list" role="list">
            {% for t in related_topics %}
            <li>
              <a class="chip chip--topic" href="/topics/{{ t.slug }}.html">
                {{ icon('folder-tag', size=12) }}
                <span class="chip-label">{{ t.localized_name }}</span>
              </a>
            </li>
            {% endfor %}
          </ul>
        </section>
        {% endif %}
      </aside>
      {% endif %}
    </div>
    ```

    **Surgical-changes principle (CRITICAL):** existing `{{ body_html | safe }}` block content UNCHANGED. The `.article-footer` (Ask AI CTA) remains BELOW the new `.article-detail-layout` div, UNTOUCHED. JSON-LD, breadcrumb, lang badge, all other kb-1 article.html elements are UNCHANGED.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); env.get_template('article.html'); content = open('kb/templates/article.html', encoding='utf-8').read(); assert 'article-detail-layout' in content; assert 'article-aside' in content; assert 'related_entities' in content; assert 'related_topics' in content; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "article-detail-layout" kb/templates/article.html` (UI-SPEC accept #19)
    - `grep -q "article-aside" kb/templates/article.html` (UI-SPEC accept #20)
    - `grep -q "related_entities" kb/templates/article.html` (UI-SPEC accept #21)
    - `grep -q "related_topics" kb/templates/article.html` (UI-SPEC accept #22)
    - `grep -q "chip--topic" kb/templates/article.html` (UI-SPEC accept #22 — also in style.css per Task 2)
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-08-article-aside-PLAN.md`
    - `grep -q "Skill(skill=\"frontend-design\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-08-article-aside-PLAN.md`
    - Jinja2 parses without error
    - Surgical regression: existing kb-1 article.html elements still present — `grep -q "article-footer" kb/templates/article.html && grep -q "body_html" kb/templates/article.html`
  </acceptance_criteria>
  <done>article.html extended with .article-detail-layout wrapper + .article-aside sibling; kb-1 article-body content + footer untouched.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Append article-aside CSS to kb/static/style.css per UI-SPEC §3.4</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.4 (CSS verbatim — .article-detail-layout grid + sticky aside + .article-aside__group + .chip--topic)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §2.1 (no new :root tokens)
    - kb/static/style.css (kb-1 + plans 05/06/07 additions — APPEND only)
  </read_first>
  <files>kb/static/style.css</files>
  <action>
    Skill(skill="frontend-design", args="Append article-aside CSS to kb/static/style.css. Verbatim from kb-2-UI-SPEC.md §3.4. ZERO new :root vars. Selectors: .article-detail-layout (grid 1fr default, 1fr 280px at min-width:1024), .article-aside sticky (top: 88px = kb-1 nav 64px + 24px breathing) + max-height calc(100vh - 104px) + overflow-y auto, .article-aside__group + .article-aside__group separator, .article-aside__heading (uppercase tertiary), .article-aside__list (flex-wrap on mobile, flex-col full-width chips on desktop), .chip--topic minor variant adds ONLY hover (border-color accent-green-30 + color accent-green).")

    **Append to `kb/static/style.css`** (verbatim from UI-SPEC §3.4):

    ```css
    /* ============================================================
       kb-2 — Article Detail Aside (UI-SPEC §3.4)
       Sticky sidebar on desktop ≥1024; stacked below body on mobile.
       ZERO new :root tokens.
       ============================================================ */

    .article-detail-layout {
      display: grid;
      grid-template-columns: 1fr;
      gap: 2rem;
    }
    @media (min-width: 1024px) {
      .article-detail-layout {
        grid-template-columns: minmax(0, 1fr) 280px;
        align-items: start;
      }
      .article-aside {
        position: sticky;
        top: 88px;          /* kb-1 nav 64px + 24px breathing */
        max-height: calc(100vh - 104px);
        overflow-y: auto;
      }
    }

    .article-aside__group + .article-aside__group {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }
    .article-aside__heading {
      font-size: 0.8125rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-tertiary);
      margin-bottom: 0.75rem;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }
    .article-aside__list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    @media (min-width: 1024px) {
      .article-aside__list { flex-direction: column; }
      .article-aside__list .chip { width: 100%; justify-content: flex-start; }
    }

    /* Topic chip variant — minor hover hue distinguishes from .chip--entity */
    .chip--topic:hover {
      border-color: var(--accent-green-30);
      color: var(--accent-green);
    }
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "css = open('kb/static/style.css', encoding='utf-8').read(); assert '.article-detail-layout' in css; assert '.article-aside' in css; assert '.chip--topic' in css; assert 'position: sticky' in css; print('CSS OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "article-detail-layout" kb/static/style.css`
    - `grep -q "article-aside" kb/static/style.css`
    - `grep -q "chip--topic" kb/static/style.css`
    - `grep -q "position: sticky" kb/static/style.css`
    - Token discipline preserved: `^\s*--[a-z]` line count unchanged
    - File still under kb-2 LOC budget: `[ "$(wc -l < kb/static/style.css)" -le 1937 ]`
  </acceptance_criteria>
  <done>~50 LOC appended; article-aside CSS classes present; .chip--topic hover variant defined; zero new :root tokens.</done>
</task>

</tasks>

<verification>
- article.html has .article-detail-layout wrapper + .article-aside sibling with both conditional sections
- All 4 UI-SPEC §8 accept patterns for article extensions satisfied (#19-22)
- CSS classes appear in style.css; zero new :root tokens
- Skill invocations literal in PLAN.md
- kb-1 .article-footer + body_html UNTOUCHED (surgical regression check)
</verification>

<success_criteria>
- LINK-01 enabled: related-entities chip row in sidebar/footer
- LINK-02 enabled: related-topics chip row in sidebar/footer
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-08-SUMMARY.md` documenting:
- article.html extension + article-aside structure
- ~50 LOC CSS additions
- Sticky desktop / stacked mobile layout
- Literal Skill(skill="ui-ux-pro-max") + Skill(skill="frontend-design") strings
- Foundation for plan 09 (driver provides related_entities + related_topics in article context)
</output>
