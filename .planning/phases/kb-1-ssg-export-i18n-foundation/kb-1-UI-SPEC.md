---
artifact: UI-SPEC
phase: kb-1-ssg-export-i18n-foundation
created: 2026-05-13
source_skills:
  - ui-ux-pro-max
  - frontend-design
status: ratified — kb-1 redesign quick task source-of-truth
inherits_from:
  - kb/docs/01-PRD.md §5 (UX Design — full ASCII mockups)
  - kb/docs/02-DECISIONS.md D-10 (ui-ux-pro-max FAQ/Documentation Landing) + D-12 (token spec)
  - kb/docs/03-ARCHITECTURE.md §双搜索/问答入口交互设计 + §ui-ux-pro-max 设计系统推荐
  - vitaclaw-site dark theme tokens (locked)
---

# Phase kb-1 — UI Design Contract

> Permanent design artifact. kb-3 + kb-4 inherit.
> Closes audit gap "no UI-SPEC.md ever produced" from `kb-1-DESIGN-AUDIT.md`.

## 1. Aesthetic direction

**Editorial Tech Knowledge — Swiss Minimal, Dark, Quietly Sharp.**

- **Restraint over excess** — one signature moment per page, not five
- **Sharp accents over timid palettes** — dominant `#0f172a` dark base + sharp `#3b82f6` blue + sharp `#22d3a0` green
- **Generous rhythm at desktop, tight at mobile** — 4/8px spacing scale, fluid type via `clamp()`
- **Type pairing:** Inter (Latin display + body) + Noto Sans SC (CJK glyph fallback). Same font stack everywhere; weight + scale + tracking carry the hierarchy.
- **No icon fonts. Inline SVG only.** Single stroke style: 1.5px stroke, currentColor, 24×24 viewbox.

The signature moments:
- **Hero h1** — gradient text fill (`background-clip: text`) with 3-stop gradient `text → accent-blue → accent-green`
- **CTA buttons** — `.glow` and `.glow-green` utility classes (per D-12) with `box-shadow: 0 0 24px -4px rgba(...)`. CTA is felt, not loud.
- **Card hover** — background flips to `#2a3a4a`, border to `rgba(accent, 0.3)`, transform `translateY(-2px)`. 300ms cubic-bezier(0.4, 0, 0.2, 1).
- **Lang chip color-coding** — semantic data clarity. zh-CN=blue, en=green, unknown=neutral grey. Same shape, different hue.

## 2. Locked tokens (D-12 — do NOT redefine)

```css
:root {
  /* Brand surface */
  --bg: #0f172a;             /* page background */
  --bg-card: #1e293b;        /* card resting bg */
  --bg-card-hover: #2a3a4a;  /* card hover bg (D-12 new) */
  --bg-elevated: #1a1f2e;    /* code block, input field bg (one tone darker than card) */

  /* Text */
  --text: #f0f4f8;           /* primary */
  --text-secondary: #94a3b8; /* secondary, meta, captions */
  --text-tertiary: #64748b;  /* hints, disabled */

  /* Brand accents */
  --accent: #3b82f6;         /* blue — primary CTA, links, focus */
  --accent-green: #22d3a0;   /* green — secondary CTA, success */
  --accent-blue-soft: rgba(59, 130, 246, 0.15);   /* lang chip zh-CN bg */
  --accent-blue-30: rgba(59, 130, 246, 0.3);      /* hover border 30% opacity */
  --accent-green-soft: rgba(34, 211, 160, 0.15);  /* lang chip en bg */
  --accent-green-30: rgba(34, 211, 160, 0.3);

  /* Borders */
  --border: rgba(255, 255, 255, 0.08);            /* default */
  --border-strong: rgba(255, 255, 255, 0.16);     /* emphasized */

  /* Typography */
  --font-sans: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;

  /* Scale (D-12: rounded-2xl = 16px = 1rem) */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;          /* rounded-2xl */
  --radius-pill: 9999px;

  /* Motion (D-12 spec: transition-all duration-300) */
  --motion-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --motion-base: 300ms cubic-bezier(0.4, 0, 0.2, 1);

  /* Glow (D-12 .glow / .glow-green) */
  --glow-blue: 0 0 24px -4px rgba(59, 130, 246, 0.55);
  --glow-blue-strong: 0 0 32px -2px rgba(59, 130, 246, 0.7);
  --glow-green: 0 0 24px -4px rgba(34, 211, 160, 0.55);
  --glow-green-strong: 0 0 32px -2px rgba(34, 211, 160, 0.7);
}
```

## 3. Component spec

### 3.1 Top nav (`.nav`)

- Fixed-height 64px, sticky on scroll
- Brand: 32px logo + brand text (or text fallback when logo `onerror` fires — show `VitaClaw` `企小勤` as text with `font-weight: 700`)
- Nav links: 3 items (Home / Articles / Ask AI) with inline SVG icon + label, 1rem gap
- Language toggle: pill button, 4-tier resolver-driven label (中 / EN), focus-visible 2px outline
- On scroll > 20px: `.nav-wrap.scrolled { backdrop-filter: blur(8px); background: rgba(15, 23, 42, 0.85); border-bottom-color: var(--border); }`

### 3.2 Hero (`.hero`)

```
┌─────────────────────────────────────────┐
│         padding-top: 4rem               │
│   ╔═══════════════════════════════════╗ │
│   ║  [gradient text h1, clamp(2,5vw,3.5rem)]
│   ║   Bilingual AI Agent / Knowledge   ║ │
│   ╚═══════════════════════════════════╝ │
│   subtitle (text-secondary, 1.125rem)   │
│                                         │
│   ┌────────────────────────────────┐   │
│   │ 🔍  Search... (placeholder)    │   │ ← .hero-search input (focus glow)
│   └────────────────────────────────┘   │
│                                         │
│   [AI Agent] [RPA] [LLM] [KG] [MCP]    │ ← .hero-chips (5 fixed for v2.0)
│                                         │
│   [开始探索 →]  [问个问题 →]            │ ← .hero-cta-row (.glow + .glow-green)
└─────────────────────────────────────────┘
```

Detail:
- `.hero h1` — `font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 700; letter-spacing: -0.02em;` + gradient `linear-gradient(135deg, var(--text) 0%, var(--accent) 50%, var(--accent-green) 100%)` clipped to text
- `.hero-search` — `max-width: 560px`, `border-radius: var(--radius-lg)`, `border: 1px solid var(--border)`, `background: var(--bg-elevated)`, padding `1rem 1.25rem 1rem 3rem` (left padding for icon), inline SVG search icon absolutely positioned at left:1rem
- Focus state: `border-color: var(--accent)`, `box-shadow: 0 0 0 4px var(--accent-blue-soft)`, transition 300ms
- `.hero-chips` — flexbox wrap, gap 0.5rem; chip = pill button, hover changes border to accent-blue-30
- `.hero-cta-row` — flex gap 1rem; first button `.btn .glow`, second `.btn-secondary .glow-green`

### 3.3 Article card (`.article-card`)

```
┌──────────────────────────────────────────────┐
│ [chip:zh-CN/en/unknown] [💬 WeChat] · 2 days ago
│                                              │
│ Article Title (1.125rem, weight 600)         │
│                                              │
│ Body snippet... (text-secondary, 0.95rem,    │
│ line-height 1.55, 200 chars max, ellipsis)   │
│                                              │
│ Read more →                                  │
└──────────────────────────────────────────────┘
```

Detail:
- `border-radius: var(--radius-lg)` (16px = rounded-2xl)
- `background: var(--bg-card)`, `border: 1px solid var(--border)`
- Padding `1.5rem`
- Hover: `background: var(--bg-card-hover)`, `border-color: var(--accent-blue-30)`, `transform: translateY(-2px)`, `transition: all var(--motion-base)`
- Meta row: flex gap 0.75rem, 0.875rem text-secondary, lang-chip + source-icon-chip + humanized date
- Title: `color: var(--text)`, hover ↓ accent — *but card hover and title link hover should not stack (one or the other)*
- Snippet: `color: var(--text-secondary); line-height: 1.55; -webkit-line-clamp: 3; display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden;`
- "Read more →" link with arrow icon, hover changes color to accent

### 3.4 Lang chip (`.lang-badge`)

Color-coded pill with content language semantic. **Same shape across all langs, only hue differs.**

```css
.lang-badge {
  display: inline-flex; align-items: center; gap: 0.375rem;
  padding: 0.1875rem 0.625rem;
  border-radius: var(--radius-pill);
  font-size: 0.75rem; font-weight: 600;
  letter-spacing: 0.02em;
  border: 1px solid;
}

.lang-badge[data-lang="zh-CN"] {
  background: var(--accent-blue-soft);
  color: var(--accent);
  border-color: var(--accent-blue-30);
}
.lang-badge[data-lang="en"] {
  background: var(--accent-green-soft);
  color: var(--accent-green);
  border-color: var(--accent-green-30);
}
.lang-badge[data-lang="unknown"] {
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-secondary);
  border-color: var(--border-strong);
}
```

`unknown` chip displays a muted dot icon (no em-dash text — was an audit finding).

### 3.5 Source chip (`.source-chip`)

```
[💬 WeChat]   [🌐 RSS]   [🔗 Web]
```

Inline-flex pill with inline SVG icon (16px stroke 1.5) + lowercase label. Resolved from `article.source` (`wechat` / `rss` / fallback `web`).

```css
.source-chip {
  display: inline-flex; align-items: center; gap: 0.375rem;
  padding: 0.1875rem 0.625rem;
  border-radius: var(--radius-pill);
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.source-chip svg { flex-shrink: 0; }
```

### 3.6 Buttons

```css
.btn {
  display: inline-flex; align-items: center; gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border-radius: var(--radius-md);
  background: var(--accent); color: var(--text);
  font-weight: 600; font-size: 0.9375rem;
  border: 1px solid transparent;
  cursor: pointer; user-select: none;
  transition: all var(--motion-base);
}
.btn:hover { transform: translateY(-1px); box-shadow: var(--glow-blue-strong); }
.btn-secondary {
  background: transparent; color: var(--text);
  border-color: var(--border-strong);
}
.btn-secondary:hover { background: var(--bg-card-hover); border-color: var(--accent-green-30); }
.btn-secondary.glow-green:hover { box-shadow: var(--glow-green-strong); }

/* D-12 utility classes (NOT decorative — applied where CTA emphasis matters) */
.glow { box-shadow: var(--glow-blue); }
.glow-green { box-shadow: var(--glow-green); }
```

### 3.7 Breadcrumb

Chevron icon SVG separator (replaces `&gt;` text). Each crumb is a link except the last.

### 3.8 Code block wrapper (`.codehilite`)

- Container: `border-radius: var(--radius-md)` (10px), `padding: 1.25rem 1.5rem`, `background: var(--bg-elevated)`, `border: 1px solid var(--border)`, `overflow-x: auto`
- Top-right corner: language label as `::before` pseudo-element (`content: attr(data-lang-label)`, font-mono, text-tertiary, 0.75rem)
- Wraps existing Pygments span tokens — Pygments-generated colors stay intact

### 3.9 Q&A page (`/ask/`)

Per PRD §5.4, full layout (form is placeholder, layout is real):

```
┌─────────────────────────────────────────────┐
│  Hero h2: AI 知识智能问答 / AI Knowledge Q&A │
│  Subtitle: 基于OmniGraph知识图谱的智能问答  │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ 💬 输入你的AI、自动化相关问题...     │    │ ← .ask-textarea (focus glow)
│  │                                     │    │
│  │                                     │    │
│  │                                     │    │
│  └─────────────────────────────────────┘    │
│  [深度问答 →] (.btn.glow large)             │
│                                              │
│  ━━ 🔥 热门问题 / Hot questions ━━          │
│  → AI Agent 和 RPA 有什么区别?              │
│  → What is LangGraph vs CrewAI?             │
│  → MCP 协议是什么?                          │
│  → 什么是 LightRAG?                         │
│  → How to evaluate RAG retrieval quality?   │
│                                              │
│  [hidden until submit] .ask-result          │
│  ┌─ 🤖 答 / Answer ───────────────────┐    │
│  │ Markdown placeholder...            │    │
│  │                                    │    │
│  │ 📎 来源文章 / Source articles     │    │
│  │ 🔗 相关实体 / Related entities    │    │
│  │ ⚠️  AI 生成内容仅供参考...        │    │
│  │ 👍  👎  反馈                       │    │
│  └────────────────────────────────────┘    │
│                                              │
│  ━━ Bottom CTA banner ━━                    │
│  Browse all articles → /articles/           │
└─────────────────────────────────────────────┘
```

Form `onsubmit`: prevent default, reveal `.ask-result` with placeholder content + "kb-3 backend pending" notice.

### 3.10 Empty / loading / error states

```css
.empty-state {
  padding: 4rem 1rem; text-align: center;
  color: var(--text-secondary);
}
.empty-state__icon {
  width: 48px; height: 48px;
  margin: 0 auto 1rem;
  opacity: 0.5;
  color: var(--text-tertiary);
}
.empty-state__title { font-size: 1.125rem; color: var(--text); margin-bottom: 0.5rem; }
.empty-state__hint { font-size: 0.875rem; }

.skeleton {
  background: linear-gradient(90deg,
    var(--bg-card) 0%,
    var(--bg-card-hover) 50%,
    var(--bg-card) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-md);
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; background: var(--bg-card-hover); }
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
  }
}

.error-state {
  border: 1px solid rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.08);
  color: #fca5a5;
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
}
```

### 3.11 Focus / a11y

```css
*:focus { outline: none; }
*:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 2px;
}
```

### 3.12 Icon set (inline SVG, currentColor, 1.5 stroke)

| Symbol | Use |
|---|---|
| `home` | nav, breadcrumb root |
| `articles` (book/document) | nav, breadcrumb |
| `ask` (chat-bubble) | nav, CTA |
| `chevron-right` | breadcrumb separator |
| `search` (magnifier) | hero search input |
| `arrow-right` | CTA buttons, "read more" links |
| `wechat` (chat-bubble variant) | source chip for `wechat` |
| `rss` (signal-wave) | source chip for `rss` |
| `web` (globe) | source chip fallback |
| `inbox` | empty state default icon |
| `globe-alt` | language toggle (optional) |

All icons inline, 24×24 viewbox, `stroke-width="1.5"`, `stroke="currentColor"`, `fill="none"`.

## 4. Page composition

### 4.1 Homepage (`index.html`)

1. `.hero` — gradient h1, search input, 5 topic chips, dual CTA
2. `.section.section--latest` — h2 "Latest Articles", grid of 6 article cards (responsive: 1 col / 2 col / 3 col)
3. `.section.section--ask-cta` — featured Q&A CTA card with sample question preview + glow CTA button to `/ask/`
4. `.section.section--brand` — short paragraph "OmniGraph 知识图谱驱动 — KOL 文章 + RAG 问答"

### 4.2 Articles list (`articles_index.html`)

1. h1 + subtitle
2. `.filter-bar` — chip-style toggle buttons for `lang` (All / 中文 / English) + `source` (All / WeChat / RSS). NO native `<select>`.
3. Counter: "Showing X / 1800 articles"
4. `.article-list` — grid of cards, all 1800 rendered server-side (lazy-load deferred to v2.1 if needed)
5. Empty state: shown when filter yields 0 — empty-state component with reset link

### 4.3 Article detail (`article.html`)

1. Breadcrumb (with chevron SVG)
2. Title (h1) + meta row (lang-badge + source-chip + humanized date + reading time)
3. Markdown body (Pygments-rendered, code-block wrappers applied)
4. Bottom CTA: "对这篇文章有疑问? 问 AI →" with `.glow`
5. (Out of scope for kb-1 polish: TOC sidebar at ≥1024px — defer to kb-1 ui-iter2 or kb-3.)

### 4.4 Q&A entry (`ask.html`)

Per PRD §5.4 layout above — hero, large textarea with focus glow, hot-questions list (5 hardcoded), result region (hidden by default, revealed on submit with kb-3-pending placeholder), bottom CTA banner.

### 4.5 base.html

Nav with backdrop blur on scroll, footer with 3-column grid (about / nav / language) replacing single-line copyright.

## 5. New locale keys (additive, no removals)

```
hero.search_placeholder         | hero.chip_ai_agent | hero.chip_rpa | hero.chip_llm | hero.chip_kg | hero.chip_mcp
hero.cta_explore                | hero.cta_ask
home.section_brand_text         | home.featured_q    | home.featured_a_preview
articles.counter_template       | articles.empty_title | articles.empty_hint | articles.empty_reset
articles.filter_all_lang        | articles.filter_zh | articles.filter_en
ask.hero_subtitle               | ask.submit_long
ask.hot_questions_title         | ask.hot_q_1 | ask.hot_q_2 | ask.hot_q_3 | ask.hot_q_4 | ask.hot_q_5
ask.result_kb3_pending          | ask.result_sources_title | ask.result_entities_title | ask.feedback_helpful | ask.feedback_unhelpful
ask.bottom_cta                  | article.read_time_template
footer.about_short              | footer.nav_title   | footer.lang_title
breadcrumb.separator_aria
source.wechat | source.rss | source.web
date.relative_today | date.relative_days_ago | date.month_short_jan ... date.month_short_dec
```

## 6. New utility: `humanize_date(value, lang)` Jinja2 filter

Added to `kb/i18n.py`:

```python
def humanize_date(value: str | int | None, lang: str = "zh-CN") -> str:
    """RFC 822 / ISO 8601 / Unix epoch → human-readable per locale.
    < 7 days: 'X 天前' / 'X days ago'
    else:     '2024 年 9 月 4 日' / 'Sep 4, 2024'
    Falls back to original string on parse failure.
    """
```

Registered as `humanize` Jinja2 filter alongside `t`. Used in templates:
`{{ article.update_time | humanize('zh-CN') }}`

## 7. Acceptance — visual checklist

- [ ] Hero h1 has gradient text fill (background-clip: text + linear-gradient with 3 stops)
- [ ] Hero has visible search input + 5 topic chips + 2 CTA buttons
- [ ] Cards render at `border-radius: 16px` (rounded-2xl per D-12)
- [ ] Cards on hover: `background: #2a3a4a`, `border-color: var(--accent-blue-30)`, slight translateY
- [ ] `.glow` class present and applied to primary CTAs (homepage explore button, Q&A submit, article-detail bottom CTA)
- [ ] `.glow-green` class present and applied to secondary CTAs
- [ ] Lang chip color-coded: zh-CN=blue, en=green, unknown=neutral grey
- [ ] Source chip with inline SVG icon (WeChat 💬-equivalent, RSS 🌐-equivalent)
- [ ] Breadcrumb separator is chevron SVG, not `&gt;` text
- [ ] Article meta row shows humanized date ("2 天前" / "Sep 4, 2024"), not RFC 822
- [ ] Code blocks wrapped with rounded container + language label in top-right
- [ ] `:focus-visible` outline visible on tab navigation across nav, buttons, links, form inputs
- [ ] `prefers-reduced-motion` honored: animations disabled, transitions reduced to instant
- [ ] No horizontal scroll at 320 / 375 / 768 / 1024 / 1440 px viewports
- [ ] Q&A page has: hero, large textarea, glow CTA, 5 hot questions, result region (hidden), disclaimer, bottom CTA banner
- [ ] Articles list filter is chip-style toggles, NOT native `<select>`

## 8. Anti-patterns (forbidden)

- ❌ Native `<select>` dropdowns in any user-facing filter (use chip toggles)
- ❌ Em-dash `—` text inside lang chip for `unknown` language (use muted dot icon or hide)
- ❌ Raw RFC 822 date strings in user-facing text (use `humanize` filter)
- ❌ Emoji as structural icons (acceptable as accent in headers / hot-question prefixes only)
- ❌ External font CDN, Tailwind, PostCSS, build pipeline (vanilla CSS + inline SVG only)
- ❌ Light-mode token defaults overriding dark base (D-12 lock — dark is canonical)
- ❌ `transition: all 0.15s ease` only — must use 300ms cubic-bezier for hover state changes
- ❌ Hover-only interaction without focus-visible equivalent (a11y blocker)

## 9. Inheritance for kb-3 + kb-4

This UI-SPEC is the source-of-truth for downstream phases:

- **kb-3** (FastAPI): API HTML responses (if any) MUST use these tokens + components. The `/api/synthesize` result rendering on `ask.html` will populate the `.ask-result` framework defined here.
- **kb-4** (Deploy): smoke tests should visually verify these components survive the production build.

When kb-3 starts, `gsd-ui-researcher` MUST read this file before generating its own UI-SPEC additions; do NOT replan the design from scratch.

---

*UI-SPEC ratified 2026-05-13 by orchestrator after `ui-ux-pro-max` + `frontend-design` Skill invocations. Closes audit findings #1, #2, #3 from kb-1-DESIGN-AUDIT.md.*
