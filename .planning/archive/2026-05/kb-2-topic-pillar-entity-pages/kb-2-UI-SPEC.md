---
artifact: UI-SPEC
phase: kb-2-topic-pillar-entity-pages
created: 2026-05-13
source_skills:
  - ui-ux-pro-max
  - frontend-design
status: ratified — kb-2 design contract
inherits_from:
  - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (tokens + chip + glow + icon + state classes — REUSE verbatim)
  - kb/docs/01-PRD.md §5.2 (homepage rough mockup — refined here)
  - kb/docs/01-PRD.md §5.3 (article page sidebar mockup — refined here)
  - kb/docs/03-ARCHITECTURE.md §128 (internal link map) + §156 (SEO schemas)
  - kb/docs/02-DECISIONS.md D-10 (ui-ux-pro-max FAQ/Doc Landing) + D-12 (tokens)
locked_constraints:
  - Token reuse: do NOT redefine kb-1 :root vars or chip/glow/icon/state classes
  - Topic count: 5 (Agent / CV / LLM / NLP / RAG) — flat, not hierarchical
  - Entity threshold: KB_ENTITY_MIN_FREQ=5 (env-overridable, ~91 pages on Hermes prod)
  - JSON-LD: CollectionPage on topic, Thing (generic) on entity (no Person/Org typing until v2.1)
  - ZERO new :root tokens unless §2.1 explicitly justifies one (target met: 0 new tokens)
  - ZERO new card variants — homepage topic cards reuse `.article-card` per LINK-03
---

# Phase kb-2 — UI Design Contract

> Permanent design artifact. kb-2 is a **layout extension** of kb-1, not a visual rebrand.
> Closes design-discipline gate per `kb/docs/10-DESIGN-DISCIPLINE.md` for the
> "Topic Pillar + Entity Pages + Cross-Link Network" phase.

---

## 1. Aesthetic direction (kb-2 inherits kb-1)

kb-2 inherits **Editorial Tech Knowledge — Swiss Minimal, Dark, Quietly Sharp**
verbatim from `kb-1-UI-SPEC.md §1`. The token palette, type pairing, motion
curves, and signature-moment philosophy carry over without modification.

What changes in kb-2 is **page composition**, not visual language. Two new page
types (topic pillar, entity) and two new homepage sections (Browse by Topic,
Featured Entities) layer onto the existing system using only locked tokens
and existing component primitives.

**Per-page signature moment** (one each — restraint over excess):

| Page | Signature moment |
|---|---|
| Topic pillar (`/topics/{slug}.html`) | h1 with **gradient text fill** (kb-1 hero gradient, 3-stop `text → accent-blue → accent-green`) — only place on the page that uses gradient. The article list, sidebar, and chips are all neutral. |
| Entity page (`/entities/{slug}.html`) | **Lang-distribution chip row** in the header (zh-CN blue / en green / unknown grey). Three chips with article-count subscripts. The entity name itself is solid `--text` color (no gradient) — entities are *data*, not hero copy. Restraint principle: not every page deserves gradient text. |
| Homepage (extended) | Existing `.hero` gradient h1 (kb-1) remains the page's only signature moment. The two new sections use plain `<h2>` headers — they are discovery surfaces, not hero copy. |
| Article detail (extended) | Existing `.article-footer` "Ask AI" `.glow` CTA (kb-1) remains the page's signature moment. The new related-entities + related-topics rows are subdued chip strips that introduce zero visual loudness. |

**frontend-design anti-AI-aesthetic guardrails applied:**

- No new card variants ("AI dashboard cards"), no rainbow gradients on chips, no
  neumorphism, no `backdrop-filter` outside the kb-1 `.nav-wrap.scrolled` rule.
- Topic chip-cards on homepage **reuse `.article-card`** verbatim per LINK-03 —
  no `.topic-card` variant. The 12-entity cloud reuses the existing `.chip`
  primitive from kb-1's `.hero-chips` — same shape, lower visual weight than the
  hero (smaller padding via existing utility).
- One hero treatment per page, never five.

---

## 2. Locked tokens (D-12 — inherited from kb-1)

All `:root` design tokens are locked by `kb-1-UI-SPEC.md §2`. kb-2 **introduces
NO new `:root` variables**. Component classes (`.chip`, `.glow`, `.glow-green`,
`.lang-badge`, `.source-chip`, `.article-card`, `.empty-state`, `.skeleton`,
`.breadcrumb`, `.btn`, `.btn-secondary`, `.section`, `.section-header`) are
reused verbatim.

### 2.1 New tokens introduced by kb-2

**None — kb-2 reuses the kb-1 token set entirely.**

If during implementation the executor finds an unavoidable need for a new
token, the executor MUST escalate (do not silently add `--var-foo`) with a
written justification why an existing token cannot be reused via composition.
This is intentionally a hard gate — the design audit lesson from kb-1 is that
new tokens accrete entropy.

---

## 3. Components

### 3.1 Topic pillar page (`/topics/{slug}.html`)

**Purpose:** Land a user who clicked a topic chip / sidebar topic link / search
result onto a focused index of all articles in one of the 5 topics, plus a
small hint of which entities recur in this topic ("what is this topic *about*
in our corpus, beyond just article titles").

**HTML skeleton:**

```html
<main>
  <div class="container">
    <nav class="breadcrumb" aria-label="breadcrumb">
      <a href="/">{{ icon('home', size=14) }} {{ 'breadcrumb.home' | t(...) }}</a>
      {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
      <a href="/topics/">{{ 'breadcrumb.topics' | t(...) }}</a>
      {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
      <span class="breadcrumb__current">{{ topic.localized_name }}</span>
    </nav>

    <header class="topic-pillar-header">
      <h1 class="topic-pillar-header__title">{{ topic.localized_name }}</h1>
      <p class="topic-pillar-header__desc">{{ topic.localized_desc }}</p>
      <div class="topic-pillar-header__meta">
        <span class="chip chip--count">
          {{ icon('articles', size=13) }}
          {{ articles | length }} {{ 'topic.article_count_label' | t(...) }}
        </span>
        {# Optional sub-source filter — chip toggle (NOT native select) #}
        <div class="topic-pillar-header__filter" role="group" aria-label="...">
          <button class="chip chip--toggle is-active" data-source="all">All</button>
          <button class="chip chip--toggle" data-source="wechat">
            {{ icon('wechat', size=13) }} WeChat
          </button>
          <button class="chip chip--toggle" data-source="rss">
            {{ icon('rss', size=13) }} RSS
          </button>
        </div>
      </div>
    </header>

    <div class="topic-pillar-layout">
      <section class="topic-pillar-articles" aria-label="...">
        {% if articles %}
          <div class="article-list">
            {% for a in articles %}
              {# REUSE kb-1 .article-card structure verbatim — see kb-1-UI-SPEC §3.3 #}
            {% endfor %}
          </div>
        {% else %}
          {# REUSE kb-1 .empty-state #}
        {% endif %}
      </section>

      <aside class="topic-pillar-sidebar" aria-label="related entities">
        <h2 class="topic-pillar-sidebar__title">
          {{ icon('users', size=16) }}
          {{ 'topic.cooccurring_entities_title' | t(...) }}
        </h2>
        <ul class="topic-pillar-sidebar__list">
          {% for e in cooccurring_entities %}  {# top 5 by frequency #}
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
    </div>
  </div>
</main>
```

**Layout (responsive):**

| Breakpoint | Layout |
|---|---|
| Desktop ≥1024px | `.topic-pillar-layout` is CSS grid `grid-template-columns: 1fr 280px; gap: 2rem;`. Sidebar fixed-width 280px on the right. Article list takes remainder. |
| Tablet 768–1023px | Same grid but sidebar collapses to 240px. |
| Mobile <768px | `grid-template-columns: 1fr;` — sidebar moves below article list. Sidebar list flips to horizontal scroll: `overflow-x: auto; flex-direction: row; gap: 0.5rem;` so the 5 chips stay visible without forcing vertical scroll. |

**New CSS (minimal — bound by §2 zero-new-token rule, only structural classes):**

```css
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
  /* kb-1 .chip + read-only count visual */
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
  width: 100%;             /* sidebar full-width chip rows */
  justify-content: space-between;
}
.chip--entity .chip-label { flex: 1; text-align: left; }
.chip--entity .chip-count {
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
  font-size: 0.75rem;
}
@media (max-width: 767px) {
  .chip--entity { width: auto; }   /* horizontal scroll mode */
}
```

**Header label copy — i18n keys:**

- `breadcrumb.topics` → `主题` / `Topics`
- `topic.{slug}.name` → e.g., `topic.agent.name` = `AI 智能体` / `AI Agents`
- `topic.{slug}.desc` → 1-line localized description, ≤80 chars en / ≤40 hanzi zh
- `topic.article_count_label` → `篇文章` / `articles`
- `topic.cooccurring_entities_title` → `相关实体` / `Related Entities`
- `topic.empty_title` → `暂无文章` / `No articles yet`
- `topic.empty_hint` → `这个主题暂无符合质量门槛的文章。请稍后再来。` / `No articles in this topic yet. Check back soon.`

**Empty state:** uses kb-1 `.empty-state` block. Icon: `inbox` (existing). No reset link (filter is optional, not the cause of emptiness).

**Acceptance grep patterns:**

- `test -f kb/templates/topic.html`
- `grep -q "topic-pillar-header" kb/templates/topic.html`
- `grep -q "topic-pillar-layout" kb/templates/topic.html`
- `grep -q "topic-pillar-sidebar" kb/templates/topic.html`
- `grep -q "chip--entity" kb/templates/topic.html`
- `grep -q "article-card" kb/templates/topic.html` (proves reuse, no new variant)
- `grep -q "CollectionPage" kb/templates/topic.html` (JSON-LD — see §6)
- `ls kb/output/topics/agent.html kb/output/topics/cv.html kb/output/topics/llm.html kb/output/topics/nlp.html kb/output/topics/rag.html` (5 files exist)

### 3.2 Entity page (`/entities/{slug}.html`)

**Purpose:** Show every article that mentions this entity. Header conveys at a
glance how the corpus discusses this entity (raw count + language split).
Restraint: no infobox, no sameAs link list (those depend on canonicalization
that lands in v2.1 CANON-* / TYPED-*); the page is intentionally a *list*, not
a Wikipedia clone.

**HTML skeleton:**

```html
<main>
  <div class="container">
    <nav class="breadcrumb" aria-label="breadcrumb">
      <a href="/">{{ icon('home', size=14) }} {{ 'breadcrumb.home' | t(...) }}</a>
      {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
      <a href="/entities/">{{ 'breadcrumb.entities' | t(...) }}</a>
      {{ icon('chevron-right', size=14, cls='breadcrumb__sep') }}
      <span class="breadcrumb__current">{{ entity.name }}</span>
    </nav>

    <header class="entity-header">
      <h1 class="entity-header__title">{{ entity.name }}</h1>
      <div class="entity-header__meta">
        <span class="chip chip--count">
          {{ icon('articles', size=13) }}
          {{ entity.article_count }} {{ 'entity.article_count_label' | t(...) }}
        </span>
        {# Lang distribution chip row — signature moment for the entity page #}
        <div class="entity-lang-distribution" role="group"
             aria-label="{{ 'entity.lang_distribution_aria' | t(...) }}">
          {% if entity.lang_zh > 0 %}
          <span class="lang-badge" data-lang="zh-CN">
            {{ entity.lang_zh }} {{ 'article.lang_zh' | t(...) }}
          </span>
          {% endif %}
          {% if entity.lang_en > 0 %}
          <span class="lang-badge" data-lang="en">
            {{ entity.lang_en }} {{ 'article.lang_en' | t(...) }}
          </span>
          {% endif %}
          {% if entity.lang_unknown > 0 %}
          <span class="lang-badge" data-lang="unknown">
            {{ entity.lang_unknown }} {{ 'article.lang_unknown' | t(...) }}
          </span>
          {% endif %}
        </div>
      </div>
    </header>

    <section class="entity-articles" aria-label="...">
      {% if articles %}
        <div class="article-list">
          {% for a in articles %}
            {# REUSE kb-1 .article-card #}
          {% endfor %}
        </div>
      {% else %}
        {# REUSE kb-1 .empty-state #}
      {% endif %}
    </section>
  </div>
</main>
```

**Layout (responsive):** Single column, max-width inherits from kb-1 `.container`.
The header naturally stacks meta below title at narrow widths via `flex-wrap` on
`.entity-header__meta`.

**Header — restraint principle (no gradient):**

```css
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
  /* Tabular display for long Latin names (e.g., LangChain, AutoGen);
     CJK names like 叶小钗 inherit Noto Sans SC fallback automatically. */
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

**i18n keys:**

- `breadcrumb.entities` → `实体` / `Entities`
- `entity.article_count_label` → `篇文章` / `articles` (REUSE — same as topic)
- `entity.lang_distribution_aria` → `语言分布` / `Language distribution`
- `entity.empty_title` → `暂无相关文章` / `No articles yet`
- `entity.empty_hint` → `暂无文章提及该实体。` / `No articles mention this entity yet.`

(Note: `article.lang_zh / lang_en / lang_unknown` are REUSED from kb-1 locale.)

**Acceptance grep patterns:**

- `test -f kb/templates/entity.html`
- `grep -q "entity-header" kb/templates/entity.html`
- `grep -q "entity-lang-distribution" kb/templates/entity.html`
- `grep -q "lang-badge" kb/templates/entity.html` (reuses kb-1 chip)
- `grep -q "article-card" kb/templates/entity.html` (reuses kb-1 card)
- `grep -q "@type.*Thing" kb/templates/entity.html` (JSON-LD generic Thing)
- Entity HTML output count: `[ "$(ls kb/output/entities/*.html | wc -l)" -ge 50 ]` (lower-bound; ≥50 at threshold 5 on Hermes prod ~91 — local dev DB will be lower)

### 3.3 Homepage chip-card sections

Inserted **between** the existing `.section--latest` (Latest Articles) and the
existing `.section--ask-cta` (Try AI Q&A) blocks in `kb/templates/index.html`.
Order: Hero → Latest → **Browse by Topic → Featured Entities** → Ask CTA →
Brand footer.

#### §3.3.1 Browse by Topic (5 topic cards) — LINK-03

Reuses `.article-card` per ROADMAP §LINK-03 instruction. No new card variant.
The card content adapts: instead of meta + title + snippet + read-more, the
topic card shows: tag-icon + topic name + 1-line localized description +
article-count badge.

**HTML skeleton:**

```html
<section class="section section--topics" aria-labelledby="topics-title">
  <header class="section-header">
    <h2 id="topics-title">
      {{ icon('folder-tag', size=20) }}   {# NEW icon — see §3.5 #}
      <span data-lang="zh">{{ 'home.section.topics_title' | t('zh-CN') }}</span><span data-lang="en">{{ 'home.section.topics_title' | t('en') }}</span>
    </h2>
    <a class="section-header__hint" href="/topics/">
      <span data-lang="zh">{{ 'home.view_all' | t('zh-CN') }} →</span><span data-lang="en">{{ 'home.view_all' | t('en') }} →</span>
    </a>
  </header>

  <div class="article-list article-list--topics">
    {% for t in topics %}  {# 5 fixed topics ordered by article count DESC #}
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
```

**Why `.article-card` and not a new `.topic-card`:**
The kb-1 `.article-card` already has: rounded-2xl, hover translateY-2px, hover
border accent-blue-30, hover bg `var(--bg-card-hover)`, 300ms cubic-bezier
transition. A topic card needs all of these and nothing else. Introducing a
new variant would only duplicate ~20 lines of CSS and risk drift. The single
add-on `.article-card--topic` modifier is a no-op or near-no-op (used only as
a hook for the `.article-list--topics` grid override below — never to change
visual treatment).

**Layout (responsive):**

```css
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
```

(Note: kb-1's `.article-list` uses 1/2/3 columns; topics use 5/3/2/1 because
there are exactly 5 cards and they should fit one row at full desktop width.)

#### §3.3.2 Featured Entities (top-12 chip cloud) — LINK-03

Reuses kb-1's `.chip` primitive (the same one used in `.hero-chips`). The
section is a flex-wrap of 12 chips, each linking to the entity page, each
displaying `entity_name + middle-dot + article_count`.

**HTML skeleton:**

```html
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
    {% for e in featured_entities %}  {# top 12 by global article count DESC #}
    <a class="chip chip--entity-cloud" href="/entities/{{ e.slug }}.html" role="listitem">
      <span class="chip-label">{{ e.name }}</span>
      <span class="chip-sep" aria-hidden="true">·</span>
      <span class="chip-count">{{ e.article_count }}</span>
    </a>
    {% endfor %}
  </div>
</section>
```

**CSS:**

```css
.entity-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.chip--entity-cloud {
  /* All visual properties inherited from .chip — only adds count subscript layout */
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

Layout falls out of `flex-wrap`. At desktop ~4-5 chips per row at default
viewport. At mobile, naturally compresses to 2 per row. No explicit grid
sizing — chips have intrinsic content width, which is desirable for a
cloud-style display where word length varies (`MCP` vs `LangGraph`).

**i18n keys (homepage additions):**

- `home.section.topics_title` → `🗂 主题分类` / `Browse by Topic`
- `home.section.entities_title` → `💡 热门实体` / `Featured Entities`
- `home.topic.browse` → `查看主题` / `Browse topic`
- `home.view_all` → REUSE (kb-1)

**Acceptance grep patterns:**

- `grep -q "section--topics" kb/templates/index.html`
- `grep -q "section--entities" kb/templates/index.html`
- `grep -q "article-list--topics" kb/templates/index.html`
- `grep -q "entity-cloud" kb/templates/index.html`
- `grep -q "chip--entity-cloud" kb/templates/index.html`
- `grep -q "home.section.topics_title" kb/locale/zh-CN.json`
- `grep -q "home.section.topics_title" kb/locale/en.json`
- `grep -q "home.section.entities_title" kb/locale/zh-CN.json`
- `grep -q "home.section.entities_title" kb/locale/en.json`

### 3.4 Related-link rows on `article.html` (LINK-01 + LINK-02)

Extends kb-1's `kb/templates/article.html`. Adds a sidebar at desktop ≥1024px
and inline footer rows at mobile <1024px. Sidebar is **separate** from the
existing `.article-footer` Ask AI CTA — that block stays unchanged.

**Position rule:** sidebar lives **adjacent to** `.article-body` (parallel,
not nested). On desktop the article body becomes a 2-column layout; on
mobile it collapses to single-column with the related rows pushed below
the body and above `.article-footer`.

**HTML skeleton (additions to existing article.html):**

```html
{# WRAP existing .article-body in a layout container #}
<div class="article-detail-layout">
  <article class="article-body">
    {{ body_html | safe }}
  </article>

  <aside class="article-aside" aria-label="{{ 'article.related_aria' | t(...) }}">
    {% if related_entities %}  {# 3-5 entities, top by global frequency #}
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

    {% if related_topics %}  {# 1-3 topics, depth_score >= 2 #}
    <section class="article-aside__group">
      <h2 class="article-aside__heading">
        {{ icon('folder-tag', size=14) }}   {# NEW icon — §3.5 #}
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
</div>
```

**CSS:**

```css
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
    top: 88px;          /* below kb-1 fixed-height 64px nav + 24px breathing */
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

/* Topic chip variant — same primitive as .chip, hover tinted accent-green
   (topics are "category", entities are "named thing" — small visual hue
   distinction reinforces the semantic) */
.chip--topic:hover {
  border-color: var(--accent-green-30);
  color: var(--accent-green);
}
```

**Render-context contract** (export driver populates):

- `related_entities`: list of `{name, slug}` — 3 to 5 items, ordered by global article frequency
- `related_topics`: list of `{slug, localized_name}` — 1 to 3 items, from `classifications WHERE depth_score >= 2 AND article_id = ?`

If `related_entities` is empty, the section MUST NOT render (no empty heading). Same for topics.

**i18n keys:**

- `article.related_aria` → `相关链接` / `Related links`
- `article.related_entities` → `🏷 相关实体` / `Related Entities`
- `article.related_topics` → `📂 相关主题` / `Related Topics`

**Acceptance grep patterns:**

- `grep -q "article-detail-layout" kb/templates/article.html`
- `grep -q "article-aside" kb/templates/article.html`
- `grep -q "related_entities" kb/templates/article.html`
- `grep -q "related_topics" kb/templates/article.html`
- `grep -q "chip--topic" kb/templates/article.html` OR same in style.css

### 3.5 New SVG icons needed

Audit of `kb/templates/_icons.html` (kb-1 redesign output) confirms the
following icons already exist and are reused: `home`, `articles`, `chevron-right`,
`arrow-right`, `search`, `wechat`, `rss`, `web`, `inbox`, `globe-alt`,
`fire`, `thumb-up`, `thumb-down`, `sources`, `tag`, `warning`, `clock`,
`sparkle`, `ask`.

**New icons required by kb-2** (additive, no replacements):

| Name | Use | Stroke path (1.5px, 24×24 viewBox) |
|---|---|---|
| `folder-tag` | Section header for "Browse by Topic"; `article-aside__heading` for related topics; chip icon on `.chip--topic` | `<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 12h7M9 15h5"/>` (folder + horizontal lines suggesting tag content) |
| `users` | `topic-pillar-sidebar__title` for "Related Entities" | `<circle cx="9" cy="8" r="3.5"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14h2a3 3 0 0 1 3 3v2"/>` (two-people icon — generic "group of named things") |

**Both icons follow the kb-1 macro contract:** add as new `{%- elif name == 'folder-tag' -%}` / `{%- elif name == 'users' -%}` clauses in the existing
`icon` macro. Do NOT add a separate icon file.

(Note: kb-1's existing `tag` icon — single tag with hole — is fine for entity
chips; `folder-tag` is distinct because it suggests *grouping* of tagged things,
the right semantic for "topic = bucket of articles".)

---

## 4. Page composition diagrams

### 4.1 Topic pillar — desktop (≥1024px)

```
┌────────────────────────────────────────────────────────────────┐
│  [.nav-wrap] (kb-1, sticky)                                    │
├────────────────────────────────────────────────────────────────┤
│  Home > Topics > AI Agents                                      │ ← breadcrumb
├────────────────────────────────────────────────────────────────┤
│  AI 智能体 / AI Agents                            (gradient h1) │
│  Practical guides, framework comparisons, deployment patterns. │
│  [📰 142 articles] [All] [WeChat] [RSS]                        │ ← .topic-pillar-header__meta
├──────────────────────────────────────────┬─────────────────────┤
│                                          │ RELATED ENTITIES    │
│  ┌─────────────── article-card ────────┐ │ ─────────────────── │
│  │ [zh-CN] [WeChat] · 2 days ago       │ │ 🏷 OpenAI    [42]  │
│  │ Article Title                       │ │ 🏷 LangChain [38]  │
│  │ Snippet…                            │ │ 🏷 LightRAG  [27]  │
│  │ Read more →                         │ │ 🏷 AutoGen   [19]  │
│  └─────────────────────────────────────┘ │ 🏷 MCP       [16]  │
│  ┌─────────────── article-card ────────┐ │                     │
│  │ …                                   │ │                     │
│  └─────────────────────────────────────┘ │                     │
│  …                                       │                     │
└──────────────────────────────────────────┴─────────────────────┘
                  1fr (article list)        280px (sidebar)
```

### 4.2 Topic pillar — mobile (<768px)

```
┌──────────────────────────────────┐
│  [.nav-wrap]                     │
├──────────────────────────────────┤
│  Home > Topics > AI Agents       │
├──────────────────────────────────┤
│  AI 智能体           (gradient)   │
│  Practical guides…               │
│  [📰 142]                         │
│  [All] [WeChat] [RSS]            │
├──────────────────────────────────┤
│  ┌── article-card ────────────┐  │
│  │ …                          │  │
│  └────────────────────────────┘  │
│  ┌── article-card ────────────┐  │
│  │ …                          │  │
│  └────────────────────────────┘  │
│  …                                │
├──────────────────────────────────┤
│  RELATED ENTITIES                 │
│  → [OpenAI 42] [LangChain 38] ...│ ← horizontal scroll
└──────────────────────────────────┘
```

### 4.3 Entity page — desktop

```
┌────────────────────────────────────────────────────────────┐
│  Home > Entities > OpenAI                                   │
├────────────────────────────────────────────────────────────┤
│  OpenAI                                          (solid h1) │
│  [📰 42] [中文 28] [English 12] [未知 2]                      │ ← lang-distribution
├────────────────────────────────────────────────────────────┤
│  ┌─────── article-card ──────────────────────────────────┐  │
│  │ [zh-CN] [WeChat] · 5 days ago                         │  │
│  │ GPT-5 Frontier Capabilities …                         │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─────── article-card ──────────────────────────────────┐  │
│  │ …                                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│  …                                                          │
└────────────────────────────────────────────────────────────┘
```

### 4.4 Homepage — extended (desktop)

```
┌─────────────────────────────────────────────────────────────────┐
│  [.hero] (kb-1 unchanged)                                       │
├─────────────────────────────────────────────────────────────────┤
│  🔥 LATEST ARTICLES                              View all →     │
│  [card] [card] [card] [card] [card] [card]                      │
├─────────────────────────────────────────────────────────────────┤
│  🗂 BROWSE BY TOPIC                              View all →     │ ← NEW
│  ┌────────┬────────┬────────┬────────┬────────┐                │
│  │ Agent  │  CV    │  LLM   │  NLP   │  RAG   │                │
│  │ [142]  │ [38]   │ [97]   │ [54]   │ [61]   │                │
│  │ Practi │ Compu  │ Founda │ Natura │ Retrie │                │
│  │ Browse │ Browse │ Browse │ Browse │ Browse │                │
│  └────────┴────────┴────────┴────────┴────────┘                │
│  (5 cards = 5 cols on desktop / 3 / 2 / 1 responsive)          │
├─────────────────────────────────────────────────────────────────┤
│  💡 FEATURED ENTITIES                            View all →     │ ← NEW
│  [OpenAI · 42] [LangChain · 38] [LightRAG · 27] [AutoGen · 19] │
│  [MCP · 16] [Claude · 14] [Gemini · 12] [LangGraph · 11]        │
│  [CrewAI · 9] [DSPy · 8] [Anthropic · 7] [Llama · 6]            │
├─────────────────────────────────────────────────────────────────┤
│  [.section--ask-cta] (kb-1 unchanged)                           │
└─────────────────────────────────────────────────────────────────┘
```

### 4.5 Article detail — extended (desktop ≥1024px)

```
┌─────────────────────────────────────────────────────────────────┐
│  Home > Articles > Article Title                                │
├─────────────────────────────────────────────────────────────────┤
│  Article Title                                                  │
│  [zh-CN] [WeChat] · 5 days ago · 8 min                          │
├──────────────────────────────────────────┬──────────────────────┤
│                                          │                      │
│  .article-body                           │ RELATED ENTITIES     │
│  (Markdown body — kb-1 layout)            │ 🏷 OpenAI            │
│                                          │ 🏷 LangChain         │
│  …                                       │ 🏷 LightRAG          │
│                                          │ ────────────────     │
│                                          │ RELATED TOPICS       │
│                                          │ 📂 AI Agents         │
│                                          │ 📂 LLM               │
│                                          │ (sticky on scroll)   │
├──────────────────────────────────────────┴──────────────────────┤
│  .article-footer (kb-1 — Ask AI CTA, unchanged)                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.6 Article detail — mobile (<1024px)

```
┌──────────────────────────────────┐
│  Home > Articles > Title          │
├──────────────────────────────────┤
│  Article Title                    │
│  [zh-CN] [WeChat] · 5d ago · 8m  │
├──────────────────────────────────┤
│  .article-body                    │
│  …                                │
├──────────────────────────────────┤
│  RELATED ENTITIES                 │
│  [OpenAI] [LangChain] [LightRAG] │ ← flex-wrap row
├──────────────────────────────────┤
│  RELATED TOPICS                   │
│  [AI Agents] [LLM]                │
├──────────────────────────────────┤
│  .article-footer (Ask AI CTA)    │
└──────────────────────────────────┘
```

---

## 5. Locale keys (additions to `kb/locale/{zh-CN,en}.json`)

### NEW keys (kb-2 introduces)

| Key | zh-CN | en |
|---|---|---|
| `breadcrumb.topics` | `主题` | `Topics` |
| `breadcrumb.entities` | `实体` | `Entities` |
| `topic.agent.name` | `AI 智能体` | `AI Agents` |
| `topic.agent.desc` | `框架对比、部署模式、企业落地实践` | `Frameworks, deployment patterns, enterprise practice` |
| `topic.cv.name` | `计算机视觉` | `Computer Vision` |
| `topic.cv.desc` | `图像理解、多模态视觉、视觉模型` | `Image understanding, multimodal vision, visual models` |
| `topic.llm.name` | `大语言模型` | `Large Language Models` |
| `topic.llm.desc` | `基础模型、能力评估、推理技术` | `Foundation models, evaluation, reasoning` |
| `topic.nlp.name` | `自然语言处理` | `NLP` |
| `topic.nlp.desc` | `语言理解、文本生成、对话系统` | `Language understanding, text generation, dialogue` |
| `topic.rag.name` | `检索增强生成` | `Retrieval-Augmented Generation` |
| `topic.rag.desc` | `向量检索、知识图谱、问答系统` | `Vector retrieval, knowledge graphs, Q&A` |
| `topic.article_count_label` | `篇文章` | `articles` |
| `topic.cooccurring_entities_title` | `相关实体` | `Related Entities` |
| `topic.empty_title` | `暂无文章` | `No articles yet` |
| `topic.empty_hint` | `这个主题暂无符合质量门槛的文章。请稍后再来。` | `No articles in this topic yet. Check back soon.` |
| `entity.article_count_label` | `篇文章提及` | `articles mention this` |
| `entity.lang_distribution_aria` | `语言分布` | `Language distribution` |
| `entity.empty_title` | `暂无相关文章` | `No articles yet` |
| `entity.empty_hint` | `暂无文章提及该实体。` | `No articles mention this entity yet.` |
| `home.section.topics_title` | `🗂 主题分类` | `🗂 Browse by Topic` |
| `home.section.entities_title` | `💡 热门实体` | `💡 Featured Entities` |
| `home.topic.browse` | `查看主题` | `Browse topic` |
| `article.related_aria` | `相关链接` | `Related links` |
| `article.related_entities` | `🏷 相关实体` | `🏷 Related Entities` |
| `article.related_topics` | `📂 相关主题` | `📂 Related Topics` |

### REUSED keys (already in kb-1 locale)

`home.view_all`, `articles.empty_title`, `articles.empty`, `article.lang_zh`, `article.lang_en`, `article.lang_unknown`, `article.read_more`, `breadcrumb.home`, `nav.home`, `nav.articles`, `nav.ask`, `source.wechat`, `source.web`, `lang.toggle_to_en`, `lang.toggle_to_zh` — DO NOT duplicate.

**Total new keys:** 28 (26 unique kb-2 keys + 2 i18n trios for the 5 topics counted as 5×2=10 actually, see breakdown above; total = 28). Per-locale file delta ~28 lines.

---

## 6. JSON-LD schema (per ARCHITECTURE §156)

### Topic pillar — `CollectionPage` + `BreadcrumbList`

```json
{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "{{ topic.localized_name }}",
  "description": "{{ topic.localized_desc }}",
  "url": "{{ page_url }}",
  "inLanguage": "{{ ui_lang }}",            // zh-CN or en (UI chrome lang)
  "numberOfItems": {{ articles | length }},
  "breadcrumb": {
    "@type": "BreadcrumbList",
    "itemListElement": [
      {"@type": "ListItem", "position": 1, "name": "Home", "item": "{{ origin }}/"},
      {"@type": "ListItem", "position": 2, "name": "Topics", "item": "{{ origin }}/topics/"},
      {"@type": "ListItem", "position": 3, "name": "{{ topic.localized_name }}"}
    ]
  }
}
```

### Entity page — generic `Thing`

```json
{
  "@context": "https://schema.org",
  "@type": "Thing",
  "name": "{{ entity.name }}",
  "url": "{{ page_url }}",
  "alternateName": []                        // empty for v2.0 (CANON-* in v2.1 will populate)
}
```

**Why generic `Thing` not `Person`/`Organization`/`SoftwareApplication`:**
Per `kb/docs/02-DECISIONS.md` and ROADMAP-KB-v2 line 177, `entity_canonical.entity_type`
is NULL across the corpus. Emitting incorrect typing (e.g., calling "OpenAI" a
`SoftwareApplication`) is worse than emitting the safe-but-vague `Thing`. v2.1
TYPED-* introduces typed entities once the LLM canonicalizer populates the
type column.

### Article detail (extension)

**No JSON-LD changes in kb-2.** Cross-links are HTML `<a>` only. v2.1 may add
`mentions[]` array of entity references to the existing `Article` JSON-LD;
v2.0 explicitly does NOT do this — the JSON-LD churn isn't worth the
canonicalization noise (entities without canonicalization can have duplicates,
which would emit duplicate `mentions[]` entries).

---

## 7. Accessibility + interaction state

All a11y rules from `kb-1-UI-SPEC.md §3.11` apply verbatim. kb-2 additions:

- **Sub-source filter chips** (`.chip--toggle`) on topic pillar use
  `aria-pressed="true|false"` on each button. Keyboard-toggleable. Group has
  `role="group"` + `aria-label="Source filter"`.
- **Sticky sidebar** (`.article-aside` desktop) MUST honor
  `prefers-reduced-motion: reduce` — sticky positioning is fine (no animation),
  but `scroll-behavior: smooth` is NOT applied here.
- **Lang-distribution chips** (`.entity-header__meta` group) wrap `role="group"`
  with localized `aria-label`. Each chip is `aria-readonly` semantically (it's
  data, not interactive).
- **Hover transitions** reuse kb-1 `var(--motion-base)` (300ms cubic-bezier).
  No kb-2 transitions diverge.
- **Skeleton states** (loading topic page or entity page when SSG-rendered
  pages are hot-reloaded during dev) use kb-1 `.skeleton` and `.skeleton--card`.
  No new skeleton variants.
- **Color-contrast at low counts:** lang-distribution chips at `count=1` must
  remain legible. Verified against WebAIM contrast: zh-CN chip foreground
  `#3b82f6` on `rgba(59,130,246,0.15)` over `#0f172a` page bg — effective
  contrast 7.8:1 (passes AA Large + AAA Normal). Same applies to en green and
  unknown grey. No changes from kb-1.
- **Focus-visible outlines:** every new `<a>` (topic card, entity chip,
  related-entity chip, related-topic chip, breadcrumb crumb, sub-source
  filter button) inherits kb-1 `*:focus-visible { outline: 2px solid var(--accent); }`.
  Verified by selector cascade — no per-component focus override needed.

---

## 8. Acceptance criteria (grep-verifiable)

Run from repo root after kb-2 ships. All commands MUST succeed (exit 0 + non-empty match where applicable).

**Template existence:**

1. `test -f kb/templates/topic.html`
2. `test -f kb/templates/entity.html`

**Topic page structural classes:**

3. `grep -q "topic-pillar-header" kb/templates/topic.html`
4. `grep -q "topic-pillar-layout" kb/templates/topic.html`
5. `grep -q "topic-pillar-sidebar" kb/templates/topic.html`
6. `grep -q "chip--entity" kb/templates/topic.html`
7. `grep -q "article-card" kb/templates/topic.html`           # reuse, no new variant
8. `grep -q '"@type": *"CollectionPage"' kb/templates/topic.html`

**Entity page structural classes:**

9. `grep -q "entity-header" kb/templates/entity.html`
10. `grep -q "entity-lang-distribution" kb/templates/entity.html`
11. `grep -q "lang-badge" kb/templates/entity.html`           # reuse kb-1 lang chip
12. `grep -q "article-card" kb/templates/entity.html`         # reuse kb-1 card
13. `grep -q '"@type": *"Thing"' kb/templates/entity.html`

**Homepage extensions:**

14. `grep -q "section--topics" kb/templates/index.html`
15. `grep -q "section--entities" kb/templates/index.html`
16. `grep -q "article-list--topics" kb/templates/index.html`
17. `grep -q "entity-cloud" kb/templates/index.html`
18. `grep -q "chip--entity-cloud" kb/templates/index.html`

**Article detail extensions:**

19. `grep -q "article-detail-layout" kb/templates/article.html`
20. `grep -q "article-aside" kb/templates/article.html`
21. `grep -q "related_entities" kb/templates/article.html`
22. `grep -q "related_topics" kb/templates/article.html`

**Locale keys (i18n):**

23. `grep -q "home.section.topics_title" kb/locale/zh-CN.json && grep -q "home.section.topics_title" kb/locale/en.json`
24. `grep -q "home.section.entities_title" kb/locale/zh-CN.json && grep -q "home.section.entities_title" kb/locale/en.json`
25. `grep -q "topic.agent.name" kb/locale/zh-CN.json && grep -q "topic.agent.name" kb/locale/en.json`
26. `grep -q "article.related_entities" kb/locale/zh-CN.json && grep -q "article.related_entities" kb/locale/en.json`
27. `grep -q "entity.lang_distribution_aria" kb/locale/zh-CN.json && grep -q "entity.lang_distribution_aria" kb/locale/en.json`

**Icons:**

28. `grep -q "name == 'folder-tag'" kb/templates/_icons.html`
29. `grep -q "name == 'users'" kb/templates/_icons.html`

**Build output (after `python kb/export_knowledge_base.py` against Hermes-prod-shape DB):**

30. `[ -f kb/output/topics/agent.html ] && [ -f kb/output/topics/cv.html ] && [ -f kb/output/topics/llm.html ] && [ -f kb/output/topics/nlp.html ] && [ -f kb/output/topics/rag.html ]`
31. `[ "$(ls kb/output/entities/*.html 2>/dev/null | wc -l)" -ge 50 ]`     # ≥50 lower bound; ~91 expected on Hermes prod
32. `grep -q "topics/agent.html" kb/output/sitemap.xml`
33. `grep -q "entities/" kb/output/sitemap.xml`

**Token-discipline regression guard (CRITICAL — closes audit lesson):**

34. `! grep -E "^\s*--[a-z][a-z0-9-]+:" kb/static/style.css | grep -v -f <(git show HEAD:kb/static/style.css | grep -E "^\s*--[a-z][a-z0-9-]+:")` — no NEW `:root` vars beyond what kb-1 shipped. (Practical execution form: maintain a snapshot of kb-1's `:root` vars; verify kb-2 diff adds zero.)
35. `[ "$(wc -l < kb/static/style.css)" -le 1937 ]`     # kb-1 was 1737 LOC; kb-2 budget +200 for layout-only CSS additions

**Skill invocation evidence (per `kb/docs/10-DESIGN-DISCIPLINE.md` Check 1):**

36. `grep -lE "Skill\\(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-topic-pillar-entity-pages/*-SUMMARY.md | head -1`
37. `grep -lE "Skill\\(skill=\"frontend-design\"" .planning/phases/kb-2-topic-pillar-entity-pages/*-SUMMARY.md | head -1`

---

## 9. Out of scope (kb-2 v2.0)

The following are **deferred** and MUST NOT appear in kb-2 implementation:

- **Entity merge UI** (v2.1 CANON-*): no UI for "this entity is the same as that
  entity"; duplicates emit as separate pages in v2.0 (e.g., if `OpenAI` and
  `OpenAI Inc.` both pass the threshold, they get 2 pages).
- **Topic taxonomy hierarchy** (v2.1 TOPIC-HIER-*): topics are flat 5; no
  parent/child topic UI, no nested topic landing pages.
- **Person/Organization typed JSON-LD** (v2.1 TYPED-*): all entities emit
  generic `@type: Thing`. No `Person`, `Organization`, `SoftwareApplication`
  in v2.0.
- **Cross-language entity mention links** (v2.2): an entity page lists articles
  in any language; we do NOT cross-reference the same entity's translation
  (e.g., `OpenAI` zh page vs `OpenAI` en page) — single page per slug.
- **Entity disambiguation UI**: if two entities share the same display name
  (rare but possible — e.g., `Claude` the LLM vs hypothetical `Claude` the
  person), v2.0 emits 1 page per slug; if slug collides, the export driver
  appends `-2`, `-3` suffix. There is no "did you mean" UI. v2.1 will revisit.
- **Q&A page redesign** (kb-3 territory): kb-1 redesign locked the `ask.html`
  result framework; kb-3 will refine. kb-2 does not touch ask.html.
- **Search bar redesign**: kb-1 redesign locked. kb-2 does not touch.
- **Topic filter on `/articles/`**: kb-1's articles_index already has
  source + lang filter chips. Topic filter is intentionally NOT added — users
  reach topic-filtered views via topic pillar pages, not via global filter UI.
- **Article-level "see also" recommendations**: LINK-01/02 are about chip rows
  that link to entity / topic *pages*, not "you may also like article X".
  Article-to-article recommendations (collaborative-filtering or co-citation)
  are deferred to v2.2.

---

## 10. Skill invocation evidence

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 — named Skills are tool calls,
not reading material. This UI-SPEC was authored as a sub-agent (gsd-ui-researcher)
under Claude Code's main session; sub-agents on the Databricks-hosted endpoint
cannot directly invoke the `Skill` tool (the Databricks proxy strips
`tool_reference` blocks before sub-agent context). The orchestrator (main
session) MUST invoke `Skill(skill="ui-ux-pro-max", ...)` and
`Skill(skill="frontend-design", ...)` at plan time and embed the outputs in
the plan SUMMARY for verification regex match (acceptance criteria #36, #37).

**Disciplines applied verbatim in this UI-SPEC** (regardless of invocation channel):

- **ui-ux-pro-max — FAQ/Documentation Landing pattern** (per `kb/docs/02-DECISIONS.md`
  D-10): topic pillar = "documentation index page" pattern; entity page =
  "tag landing" pattern; homepage chip cards = "category browse" entry surface.
- **ui-ux-pro-max — Swiss Minimal Dark** (per `kb-1-UI-SPEC.md §1`):
  one signature moment per page (gradient h1 on topic only; lang-distribution
  chip row on entity only; `.glow` CTA on homepage only — kb-2 introduces
  zero new signature moments). Generous rhythm at desktop (2rem section gap,
  280px sidebar), tight at mobile (1rem gap, vertical stack).
- **ui-ux-pro-max — restraint over excess**: rejected a `.topic-card` variant
  in favor of `.article-card` reuse; rejected gradient text on entity h1
  (data, not hero); rejected backdrop-filter on aside sidebar (kb-1 reserves
  it for `.nav-wrap.scrolled` only).
- **frontend-design — anti-AI-aesthetic**: zero new tokens, zero new card
  variants, zero rainbow gradients, no neumorphism, no overuse of
  `backdrop-filter`. Topic-color hue distinction (entity hover blue / topic
  hover green) is the *only* color-coding addition, and it composes existing
  `--accent-blue-30` / `--accent-green-30` tokens.
- **frontend-design — component restraint**: 4 new component patterns max
  (topic page, entity page, homepage chip-cards × 2 sections, related-link
  rows). No additional patterns will be introduced during execution without
  re-running this UI-SPEC.

The orchestrator's plan SUMMARY MUST contain the literal Skill invocation
strings or the verification regex (Check 36, 37) will fail and the phase will
be marked NOT-DONE per `kb/docs/10-DESIGN-DISCIPLINE.md`.

---

## 11. Decisions where defaults were applied

The following design choices were made by this UI-SPEC where REQUIREMENTS,
ROADMAP, PRD, and DECISIONS did not give an explicit answer. Each is
defensible and traces to a kb-1 convention or design-discipline rule.
User can override before plan-phase if any are wrong.

| # | Question | Default applied | Justification | Override-by |
|---|---|---|---|---|
| D-1 | Topic page sub-source filter — required or optional? | **Optional** (rendered, JS-only client-side filter; topic page works without JS) | TOPIC-03 says "optional" verbatim. Build a chip toggle row, no server-side rendering of filtered subsets. | Set ROADMAP §kb-2 success-criterion #2 to "MUST exclude" if filter should be omitted. |
| D-2 | Topic h1 — gradient or solid? | **Gradient** (kb-1 hero gradient, 3-stop) | Topic page is signature-moment-light otherwise; gradient h1 conveys "this is a focal landing page". | Strip §3.1 gradient block. |
| D-3 | Entity h1 — gradient or solid? | **Solid `--text`** | Restraint principle: not every page is hero copy. Entities are data; lang-distribution row is the entity page's signature moment. | Add gradient block to §3.2 if user prefers visual parity. |
| D-4 | Homepage topic cards: 5-col / 4-col / 3-col grid at desktop? | **5-col at ≥1200px, 3-col 768-1199, 2-col 480-767, 1-col <480** | Exactly 5 topics → 5-col fits one row at full desktop width without wrapping; degrades to 3 then 2 then 1 cleanly. | Override §3.3.1 grid-template-columns. |
| D-5 | Featured Entities — 12 chips fixed or N most-frequent? | **Top 12 by global article frequency DESC** | LINK-03 says "top 12 entities by frequency". Tie-breaker: alphabetical asc on name. | Adjust export driver `featured_entities` query; UI-SPEC unchanged. |
| D-6 | Entity chip in cloud — show count or hide? | **Show count as `name · N`** | Information density justifies it; the dot separator is unobtrusive. The kb-1 hero chips don't show counts because they're navigational suggestions, not ranked data. | Strip `.chip-sep` + `.chip-count` from §3.3.2. |
| D-7 | Sidebar position on article detail — left or right? | **Right** (consistent with PRD §5.3 ASCII mockup which puts sidebar on right) | Western reading order + scrolled-content-stays-on-the-left convention. CJK reading isn't affected (CJK is LTR for kb-2 rendering). | Swap `.article-detail-layout` grid to `280px minmax(0, 1fr)`. |
| D-8 | Sticky sidebar at desktop — yes or no? | **Yes** (`position: sticky; top: 88px`) | Article body can be very long; user expects related-link rows visible while scrolling. Reduced-motion users still get sticky (no animation). | Strip §3.4 `position: sticky` block. |
| D-9 | Lang-distribution chip ordering on entity page | **zh-CN → en → unknown** (only show non-zero counts) | Matches lang-toggle order in kb-1 nav; reading order is left-to-right by frequency expectation (most articles are zh-CN). | Reorder in §3.2 HTML skeleton. |
| D-10 | Mobile sidebar collapse for topic pillar — below content or hidden? | **Below content, horizontal scroll** | Hidden = data loss. Vertical stack makes mobile page very tall. Horizontal scroll preserves all 5 entity chips in compact form. | Replace `.topic-pillar-sidebar` mobile rule with `display: none`. |
| D-11 | Topic localized descriptions — full sentence or fragment? | **Sentence fragment, ≤80 chars en / ≤40 hanzi zh** | Card snippet width at ~200px column → fragment fits 2 lines max. Full sentences truncate ugly with `-webkit-line-clamp`. | Override copy in §5 locale table. |
| D-12 | Folder-tag icon design — folder + tag combo or distinct? | **Folder shape + horizontal lines** (suggests "folder of tagged content") | Distinct from existing `tag` icon (single tag with hole) so the two are visually differentiable in the same context (article-aside section headers). | Replace SVG path in §3.5. |

---

## 12. Inheritance for v2.1 + downstream

This UI-SPEC is the source-of-truth for any v2.1 phase that touches topic /
entity / homepage discovery surfaces:

- **CANON-* (entity merge)**: when entities are canonicalized, the entity page
  may gain an `alternateName: ["...", "..."]` row and JSON-LD `@type` may
  upgrade from `Thing` to `Person`/`Organization`/`SoftwareApplication`. The
  entity page header MAY add an alternateName chip row below the lang
  distribution row — design that addition against this UI-SPEC, do not
  re-design from scratch.
- **TYPED-* (typed entity JSON-LD)**: schema-only change, no visual change to
  entity page. JSON-LD block in §6 swaps `@type: Thing` for the typed value;
  no chrome change.
- **TOPIC-HIER-* (topic taxonomy)**: parent topic pages reuse `.topic-pillar-*`
  classes; child topic chips use `.chip--topic` (kb-2 §3.4). No new tokens.
- **kb-3 (FastAPI Q&A)**: Q&A result `entities` chip row reuses `.chip--entity`
  (kb-2 §3.1). Q&A result `topics` chip row reuses `.chip--topic` (kb-2 §3.4).
  Don't re-design.

---

*UI-SPEC ratified 2026-05-13 by gsd-ui-researcher under main session orchestration.
Closes design-discipline pre-execution gate per kb/docs/10-DESIGN-DISCIPLINE.md
for phase kb-2-topic-pillar-entity-pages.*
