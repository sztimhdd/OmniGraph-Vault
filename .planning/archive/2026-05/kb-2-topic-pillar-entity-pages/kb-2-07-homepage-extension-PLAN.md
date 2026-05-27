---
phase: kb-2-topic-pillar-entity-pages
plan: 07
subsystem: ui-template
tags: [jinja2, template, homepage, css, ui-spec]
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/index.html
  - kb/static/style.css
autonomous: true
requirements:
  - LINK-03

must_haves:
  truths:
    - "kb/templates/index.html gains 2 NEW sections: section--topics + section--entities"
    - "Both sections sit BETWEEN .section--latest (kb-1 Latest Articles) and .section--ask-cta (kb-1 Try AI Q&A) — order: Hero → Latest → Topics → Entities → Ask CTA → footer"
    - "section--topics: 5 topic cards in .article-list--topics grid; cards REUSE .article-card (no .topic-card variant) per LINK-03"
    - "section--entities: top 12 entity chip cloud using .chip--entity-cloud (composes .chip primitive)"
    - "Both sections have section-header with localized i18n title + 'View all →' link"
    - "ZERO new card variants — only minor article-card--topic modifier hook for grid override"
    - "Existing kb-1 sections .section--latest + .section--ask-cta UNTOUCHED (surgical changes principle)"
  artifacts:
    - path: "kb/templates/index.html"
      provides: "EXTENDED with 2 new sections inserted between Latest Articles and Ask CTA"
      contains: "section--topics, section--entities, article-list--topics, entity-cloud, chip--entity-cloud"
    - path: "kb/static/style.css"
      provides: "+CSS for .article-list--topics responsive grid + .entity-cloud + .chip--entity-cloud"
  key_links:
    - from: "kb/templates/index.html section--topics"
      to: "kb/templates/topic.html (plan 05) via /topics/{slug}.html"
      via: "anchor href"
      pattern: "/topics/.*\\.html"
    - from: "kb/templates/index.html section--entities"
      to: "kb/templates/entity.html (plan 06) via /entities/{slug}.html"
      via: "anchor href"
      pattern: "/entities/.*\\.html"
---

<objective>
Extend `kb/templates/index.html` per `kb-2-UI-SPEC.md §3.3` — add 2 new sections (Browse by Topic + Featured Entities) BETWEEN existing Latest Articles section and Ask AI CTA section. Topic cards reuse `.article-card`; entity cloud reuses `.chip` primitive. ZERO new card variants.

Append responsive grid + entity-cloud CSS to `kb/static/style.css`.

Purpose: LINK-03 surfaces topic + entity discovery from the homepage. Without these sections, users have no way to discover the new topic/entity pages from the front door.

Output: 1 file extended (index.html) + ~30 LOC CSS appended.
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
@kb/templates/index.html
@kb/templates/_icons.html
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/static/style.css
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Render context expectation (provided by export driver in plan 09):

```python
context = {
    "lang": "zh-CN" | "en",
    "topics": [                  # 5 fixed topics ordered by article_count DESC
        {
            "slug": str,           # 'agent' | 'cv' | 'llm' | 'nlp' | 'rag'
            "raw_topic": str,
            "localized_name": str,
            "localized_desc": str,
            "article_count": int,
        }, ...
    ],
    "featured_entities": [       # top 12 by global frequency DESC, alpha tiebreak
        {
            "name": str,
            "slug": str,
            "article_count": int,
        }, ...
    ],
    # ... plus kb-1 existing context (latest_articles, etc.)
}
```

Hooks: kb-1 `kb/templates/index.html` already exists. The 2 new sections are inserted with NO modification to existing sections. Insert point is identifiable by HTML comment marker or pattern matching the existing Latest Articles closing tag → Ask CTA opening tag.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + extend index.html with 2 new sections per UI-SPEC §3.3</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.3 (HTML skeletons §3.3.1 + §3.3.2 verbatim)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §4.4 (homepage composition diagram)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (chip + section-header patterns to reuse)
    - kb/templates/index.html (full file — find existing .section--latest closing + .section--ask-cta opening; INSERT between them)
    - kb/templates/_icons.html (verify folder-tag + sparkle + arrow-right + articles icons exist after plan 03 + kb-1)
  </read_first>
  <files>kb/templates/index.html</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes the named UI Skills:

    Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.3 (homepage Browse by Topic + Featured Entities sections) into Jinja2 markup. Verify design constraints: (1) topic cards REUSE .article-card per LINK-03 — no .topic-card variant (UI-SPEC §1 + §3.3.1 'Why .article-card and not a new .topic-card'); (2) entity cloud REUSES .chip primitive (same one used in .hero-chips) — no new .entity-card variant; (3) sections sit BETWEEN .section--latest and .section--ask-cta — insertion order: Hero → Latest → Topics → Entities → Ask → footer; (4) section-header style mirrors kb-1 .section--latest's section-header (icon + title + 'View all →' link); (5) no breakpoint cliffs — topic grid degrades 5→3→2→1 cols, entity cloud is flex-wrap (intrinsic content widths). Confirm template extension preserves all 5 constraints.")

    Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.3.1 + §3.3.2 verbatim into kb/templates/index.html. Surgical changes: locate the closing `</section>` of .section--latest and the opening `<section class=\"section section--ask-cta\">` of Ask CTA; INSERT the 2 new <section> blocks BETWEEN them. Topic cards use .article-card.article-list--topics grid wrapper + .article-card--topic modifier hook (no visual change — just a hook for `.article-list--topics .article-card { ... }` grid override). Entity cloud uses .entity-cloud > .chip.chip--entity-cloud links. Section headers use existing kb-1 .section-header pattern with `{{ icon('folder-tag', size=20) }}` for Topics + `{{ icon('sparkle', size=20) }}` for Entities. Both 'View all →' hint links use href='/topics/' or '/entities/'. ZERO modifications to .section--latest or .section--ask-cta — surgical principle.")

    **Insert these 2 sections** into `kb/templates/index.html` between the existing Latest Articles section and Ask CTA section (verbatim from UI-SPEC §3.3.1 + §3.3.2):

    ```jinja2
    {# kb-2 LINK-03: Browse by Topic — 5 topic cards reusing .article-card #}
    <section class="section section--topics" aria-labelledby="topics-title">
      <header class="section-header">
        <h2 id="topics-title">
          {{ icon('folder-tag', size=20) }}
          <span data-lang="zh">{{ 'home.section.topics_title' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.section.topics_title' | t('en') }}</span>
        </h2>
        <a class="section-header__hint" href="/topics/">
          <span data-lang="zh">{{ 'home.view_all' | t('zh-CN') }} →</span><span data-lang="en">{{ 'home.view_all' | t('en') }} →</span>
        </a>
      </header>

      <div class="article-list article-list--topics">
        {% for t in topics %}
        <a class="article-card article-card--topic" href="/topics/{{ t.slug }}.html"
           data-topic-slug="{{ t.slug }}">
          <div class="article-card-meta">
            <span class="chip chip--count">
              {{ icon('articles', size=12) }} {{ t.article_count }}
            </span>
          </div>
          <h3 class="article-card-title">{{ t.localized_name }}</h3>
          <p class="article-card-snippet">{{ t.localized_desc }}</p>
          <span class="article-card-readmore">
            <span data-lang="zh">{{ 'home.topic.browse' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.topic.browse' | t('en') }}</span>
            {{ icon('arrow-right', size=14) }}
          </span>
        </a>
        {% endfor %}
      </div>
    </section>

    {# kb-2 LINK-03: Featured Entities — top 12 chip cloud reusing .chip #}
    <section class="section section--entities" aria-labelledby="entities-title">
      <header class="section-header">
        <h2 id="entities-title">
          {{ icon('sparkle', size=20) }}
          <span data-lang="zh">{{ 'home.section.entities_title' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.section.entities_title' | t('en') }}</span>
        </h2>
        <a class="section-header__hint" href="/entities/">
          <span data-lang="zh">{{ 'home.view_all' | t('zh-CN') }} →</span><span data-lang="en">{{ 'home.view_all' | t('en') }} →</span>
        </a>
      </header>

      <div class="entity-cloud" role="list">
        {% for e in featured_entities %}
        <a class="chip chip--entity-cloud" href="/entities/{{ e.slug }}.html" role="listitem">
          <span class="chip-label">{{ e.name }}</span>
          <span class="chip-sep" aria-hidden="true">·</span>
          <span class="chip-count">{{ e.article_count }}</span>
        </a>
        {% endfor %}
      </div>
    </section>
    ```

    **Surgical-changes principle (CRITICAL):** the existing `.section--latest` and `.section--ask-cta` blocks must be UNTOUCHED. Only the 2 new sections are inserted. No reformatting, no fixing of unrelated whitespace, no "improvements" to kb-1 markup.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); tpl = env.get_template('index.html'); print('parse OK'); content = open('kb/templates/index.html', encoding='utf-8').read(); assert 'section--topics' in content and 'section--entities' in content; print('sections present')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "section--topics" kb/templates/index.html` (UI-SPEC accept #14)
    - `grep -q "section--entities" kb/templates/index.html` (UI-SPEC accept #15)
    - `grep -q "article-list--topics" kb/templates/index.html` (UI-SPEC accept #16)
    - `grep -q "entity-cloud" kb/templates/index.html` (UI-SPEC accept #17)
    - `grep -q "chip--entity-cloud" kb/templates/index.html` (UI-SPEC accept #18)
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-07-homepage-extension-PLAN.md`
    - `grep -q "Skill(skill=\"frontend-design\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-07-homepage-extension-PLAN.md`
    - Jinja2 parses without error
    - Surgical regression: existing kb-1 sections still present — `grep -q "section--latest" kb/templates/index.html && grep -q "section--ask-cta" kb/templates/index.html`
    - Insertion order verified: line number of `section--topics` > line number of `section--latest` AND < line number of `section--ask-cta` (use `grep -n` to extract)
  </acceptance_criteria>
  <done>index.html extended with 2 new sections in correct position; kb-1 sections untouched; UI-SPEC accept patterns 14-18 satisfied.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Append homepage chip-card CSS to kb/static/style.css per UI-SPEC §3.3</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.3.1 (.article-list--topics grid CSS verbatim) + §3.3.2 (.entity-cloud + .chip--entity-cloud CSS verbatim)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §2.1 (no new :root tokens)
    - kb/static/style.css (kb-1 + plans 05/06 additions)
  </read_first>
  <files>kb/static/style.css</files>
  <action>
    Skill(skill="frontend-design", args="Append homepage section CSS to kb/static/style.css. Verbatim from kb-2-UI-SPEC.md §3.3.1 .article-list--topics grid + §3.3.2 .entity-cloud + .chip--entity-cloud. ZERO new :root vars. Selectors: .article-list--topics (5/3/2/1 col responsive grid), .entity-cloud (flex-wrap), .chip--entity-cloud (composes .chip with chip-sep + chip-count layout), .chip--entity-cloud:hover .chip-count tinted. Note: .article-list (1/2/3 col kb-1 default) is INHERITED — .article-list--topics adds the 5/3/2/1 override.")

    **Append to `kb/static/style.css`** (verbatim from UI-SPEC §3.3.1 + §3.3.2):

    ```css
    /* ============================================================
       kb-2 — Homepage Sections (UI-SPEC §3.3)
       Topics: 5/3/2/1 col grid (different from kb-1 .article-list 1/2/3).
       Entities: flex-wrap chip cloud.
       ZERO new :root tokens.
       ============================================================ */

    /* §3.3.1 — Browse by Topic grid (5 cards = 5 cols at full desktop) */
    .article-list--topics {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 1rem;
    }
    @media (max-width: 1199px) {
      .article-list--topics { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 767px) {
      .article-list--topics { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 479px) {
      .article-list--topics { grid-template-columns: 1fr; }
    }

    /* §3.3.2 — Featured Entities chip cloud */
    .entity-cloud {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .chip--entity-cloud {
      display: inline-flex;
      align-items: baseline;
      gap: 0.375rem;
    }
    .chip--entity-cloud .chip-sep {
      color: var(--text-tertiary);
      margin: 0 0.125rem;
    }
    .chip--entity-cloud .chip-count {
      color: var(--text-tertiary);
      font-variant-numeric: tabular-nums;
      font-size: 0.8125rem;
    }
    .chip--entity-cloud:hover .chip-count {
      color: var(--text-secondary);
    }
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "css = open('kb/static/style.css', encoding='utf-8').read(); assert '.article-list--topics' in css; assert '.entity-cloud' in css; assert '.chip--entity-cloud' in css; assert 'repeat(5, 1fr)' in css; print('CSS OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "article-list--topics" kb/static/style.css`
    - `grep -q "entity-cloud" kb/static/style.css`
    - `grep -q "chip--entity-cloud" kb/static/style.css`
    - `grep -q "repeat(5, 1fr)" kb/static/style.css`
    - Token discipline preserved: `^\s*--[a-z]` line count unchanged
    - File still under kb-2 LOC budget: `[ "$(wc -l < kb/static/style.css)" -le 1937 ]`
  </acceptance_criteria>
  <done>~30 LOC appended; homepage chip-card CSS present; zero new :root tokens.</done>
</task>

</tasks>

<verification>
- index.html has 2 new sections in correct position
- All 5 UI-SPEC §8 accept patterns for homepage extensions satisfied (#14-18)
- CSS classes appear in style.css; zero new :root tokens
- Skill invocations literal in PLAN.md
- kb-1 sections .section--latest + .section--ask-cta untouched (surgical)
</verification>

<success_criteria>
- LINK-03 enabled: homepage gains discovery surfaces for topics + entities
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-07-SUMMARY.md` documenting:
- 2 new sections inserted between existing kb-1 sections
- ~30 LOC CSS additions
- ZERO new card variants — .article-card reused for topic cards per UI-SPEC §3.3.1 + LINK-03
- Literal Skill(skill="ui-ux-pro-max") + Skill(skill="frontend-design") strings
- Foundation for plan 09 (driver provides `topics` + `featured_entities` in render context)
</output>
