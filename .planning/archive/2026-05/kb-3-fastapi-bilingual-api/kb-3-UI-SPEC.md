---
artifact: UI-SPEC
phase: kb-3-fastapi-bilingual-api
created: 2026-05-13
source_skills:
  - ui-ux-pro-max
  - frontend-design
status: ratified — kb-3 design contract
authored_via: orchestrator main-session synthesis (sub-agent rate-limited; disciplines applied verbatim from kb-1 / kb-2 UI-SPECs + ROADMAP + PRD §5.4 + DECISIONS)
inherits_from:
  - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (tokens — REUSE verbatim)
  - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md (chip + entity patterns — REUSE)
  - kb/docs/01-PRD.md §5.4 (Q&A page rough mockup — refine state matrix)
  - kb/docs/02-DECISIONS.md D-04 / D-15 / D-17 / D-19 / D-20
  - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (DATA-07 — backend filters before sources reach UI)
locked_constraints:
  - Token reuse: zero new :root vars; reuse kb-1 + kb-2 chip / glow / icon / state classes verbatim
  - State matrix: 8 states (idle / submitting / polling / streaming / done / error / timeout / fts5_fallback)
  - Polling cadence: 1500ms default (env-overridable via KB_QA_POLL_INTERVAL_MS)
  - HTTP polling not WebSocket (per D-19)
  - Non-streaming markdown render for v2.0 (full result reveal on done; simpler than chunked)
  - Search inline reveal pattern (no new /search page; reuse .article-card)
  - DATA-07 filter applied at backend; UI just renders what API returns
  - Feedback persisted to localStorage only this phase (no POST endpoint)
---

# Phase kb-3 — UI Design Contract

> Q&A result component with 8-state matrix + sources / entities / feedback sub-regions + inline search reveal. Backend-heavy phase but the result component is the UI dimension that pulls design weight (per `kb/docs/10-DESIGN-DISCIPLINE.md` kb-3 section).

## 1. Aesthetic direction (kb-3 inherits)

**No visual rebrand.** kb-3 inherits Swiss Minimal Dark + FAQ/Doc Landing pattern locked by kb-1-UI-SPEC.md §1, extended by kb-2-UI-SPEC.md §1. kb-3 introduces **zero new visual tokens** — the design challenge is **state transitions**, not surface design.

The signature moments for kb-3:

- **Result reveal animation** — when polling returns done, result region fades in from below (translate Y -8px → 0, opacity 0 → 1, 400ms ease-out). One signature moment per page.
- **fts5_fallback graceful degradation badge** — yellow `confidence: fts5_fallback` chip with explanatory tooltip. The "honest" UX moment that distinguishes kb-3 from generic AI products that hide failures. **This is kb-3's restraint principle in action** — instead of pretending the LightRAG answer succeeded, surface the degradation explicitly.

## 2. Locked tokens (D-12 — inherited)

All `:root` vars locked by `kb-1-UI-SPEC.md §2`. kb-2 confirmed zero new vars in `kb-2-UI-SPEC.md §2.1`. **kb-3 same — zero new vars.**

### 2.1 New tokens introduced by kb-3

**None — kb-3 reuses kb-1 + kb-2 token set entirely.**

If executor finds an unavoidable need for a new token during kb-3 implementation, escalate (do not silently add). The token entropy guard from kb-2 applies symmetrically.

## 3. Components

### 3.1 Q&A result component (the major kb-3 UI surface)

Anchor: `kb/templates/ask.html` already has the static result-framework skeleton from kb-1 redesign (per `kb-1-DESIGN-AUDIT.md` Resolution table item #7: "Full PRD §5.4 layout: gradient hero · large textarea with focus glow · 5 hot questions · result framework (hidden→reveal on submit) with 4 sections (answer / sources / entities / feedback) · disclaimer · bottom CTA banner"). kb-3 fills in the **dynamic dimension**.

**HTML structure (extends current ask.html result region):**

```html
<section id="qa-result"
         data-qa-state="idle"
         class="qa-result"
         aria-live="polite"
         aria-atomic="false"
         hidden>

  <!-- Question echo (visible after submit) -->
  <div class="qa-question">
    <span class="qa-question-icon" aria-hidden="true">{{ icon('chat-bubble-question') }}</span>
    <p class="qa-question-text"></p>
  </div>

  <!-- State indicator overlay (visible during submitting / polling / streaming) -->
  <div class="qa-state-indicator" data-qa-state-only="submitting polling streaming">
    <div class="qa-spinner" aria-hidden="true"></div>
    <p class="qa-state-text"
       data-state-text-submitting="{{ 'qa.state.submitting' | t(lang) }}"
       data-state-text-polling="{{ 'qa.state.polling' | t(lang) }}"
       data-state-text-streaming="{{ 'qa.state.streaming' | t(lang) }}"></p>
  </div>

  <!-- fts5_fallback banner (visible only in fts5_fallback state) -->
  <div class="qa-fallback-banner" data-qa-state-only="fts5_fallback" hidden>
    <span class="qa-confidence-chip qa-confidence-chip--fallback">
      {{ icon('lightning-bolt') }}
      <span class="lang-zh">快速参考</span>
      <span class="lang-en">Quick Reference</span>
    </span>
    <p class="qa-fallback-explainer">
      <span class="lang-zh">基于关键词检索的快速回答,非完整知识图谱回答。</span>
      <span class="lang-en">Keyword-based quick reference, not full KG answer.</span>
    </p>
  </div>

  <!-- Error banner (visible only in error state) -->
  <div class="qa-error-banner" data-qa-state-only="error" role="alert" hidden>
    <span class="qa-error-icon">{{ icon('warning') }}</span>
    <p class="qa-error-text"></p>
    <button type="button" class="qa-retry-btn glow">
      <span class="lang-zh">重试</span><span class="lang-en">Retry</span>
    </button>
  </div>

  <!-- Answer markdown (visible in streaming / done / fts5_fallback) -->
  <article class="qa-answer prose"
           data-qa-state-only="streaming done fts5_fallback"
           hidden>
    <!-- Markdown rendered server-side OR client-side (marked.js) into here -->
  </article>

  <!-- Sources sub-region (visible in done / fts5_fallback) -->
  <aside class="qa-sources" data-qa-state-only="done fts5_fallback" hidden>
    <h4 class="qa-sources-title">
      <span class="lang-zh">参考来源</span><span class="lang-en">Sources</span>
    </h4>
    <ul class="qa-sources-list" role="list">
      <!-- li.qa-source-chip × N (top-3) injected dynamically -->
    </ul>
  </aside>

  <!-- Related entities sub-region (visible in done; hidden in fts5_fallback per restraint) -->
  <aside class="qa-entities" data-qa-state-only="done" hidden>
    <h4 class="qa-entities-title">
      <span class="lang-zh">相关实体</span><span class="lang-en">Related Entities</span>
    </h4>
    <ul class="qa-entities-list chip-cloud" role="list">
      <!-- li.entity-chip × N (top-5) injected dynamically; reuses kb-2 entity chip class -->
    </ul>
  </aside>

  <!-- Feedback sub-region (visible in done) -->
  <div class="qa-feedback" data-qa-state-only="done" hidden>
    <p class="qa-feedback-prompt">
      <span class="lang-zh">这个回答有帮助吗?</span><span class="lang-en">Was this helpful?</span>
    </p>
    <button type="button" class="qa-feedback-btn qa-feedback-btn--up" aria-label="thumbs-up">
      {{ icon('thumb-up') }}
    </button>
    <button type="button" class="qa-feedback-btn qa-feedback-btn--down" aria-label="thumbs-down">
      {{ icon('thumb-down') }}
    </button>
  </div>
</section>
```

**Per-source chip structure** (`li.qa-source-chip` injected dynamically):

```html
<li class="qa-source-chip">
  <a href="/articles/{hash}.html" target="_blank" rel="noopener" class="qa-source-link">
    <span class="qa-source-title">{title truncated to 60 chars}</span>
    <span class="lang-badge" data-lang="{lang}">{中文 | English | ?}</span>
    <span class="source-chip" data-source="{source}">
      {{ icon(source) }}  <!-- wechat | rss | web -->
    </span>
  </a>
</li>
```

### 3.2 State matrix

| State | Trigger | Visual class on `#qa-result` | What user sees | a11y announcement |
|---|---|---|---|---|
| `idle` | page load | `data-qa-state="idle"` + `hidden` | nothing (result region not visible) | — |
| `submitting` | submit click | `data-qa-state="submitting"`, region revealed, indicator visible | submit button glow pulse + form disabled + spinner with "正在提交" | polite "Submitting your question" |
| `polling` | 202 received | `data-qa-state="polling"` | spinner + "Thinking..." copy | polite "Generating answer" |
| `streaming` | (reserved for v2.0+; non-streaming for v2.0 = directly to `done`) | `data-qa-state="streaming"` | live render or spinner | polite |
| `done` | poll returns `done` + `fallback_used=false` | `data-qa-state="done"` | full markdown answer + sources + entities + feedback | polite "Answer ready" then content focusable |
| `error` | transport error / 4xx / 5xx | `data-qa-state="error"` | red banner + retry button + technical detail | `role="alert"` |
| `timeout` | poll exceeds 60s wall-time (or `KB_QA_POLL_TIMEOUT_MS` env) | `data-qa-state="timeout"` | yellow banner with "超过等待时间" and **automatic transition to fts5_fallback after 500ms** (no user click required) | polite "Switching to quick reference" |
| `fts5_fallback` | poll returns `done` + `fallback_used=true` (backend already triggered FTS5 fallback per QA-04) | `data-qa-state="fallback"` | yellow `confidence: fts5_fallback` chip + answer (FTS5 top-3 concat) + sources (no entities — FTS5 has no entity links) | polite "Quick reference shown" |

**State CSS pattern** (composes existing kb-1/kb-2 utility classes):

```css
.qa-result[data-qa-state="idle"] [data-qa-state-only] { display: none; }
.qa-result[data-qa-state="submitting"] [data-qa-state-only*="submitting"] { display: block; }
/* ...mirror for each state */
.qa-result[data-qa-state="done"] [data-qa-state-only*="done"] { display: block; }
```

This is purely additive CSS (no new tokens) — the executor adds ~30 LOC at the end of `kb/static/style.css` to wire the data-attribute selectors.

### 3.3 Sources sub-region (DATA-07-aware)

- Backend `/api/synthesize` result.sources[] returns up to 3 articles ALREADY FILTERED through DATA-07 (per `kb-3-CONTENT-QUALITY-DECISIONS.md` — `get_article_by_hash` for deep retrieval is unfiltered, but the source SELECTION inside `kg_synthesize` happens on a query path that should call `list_articles`-equivalent → DATA-07 active)
- Render order: by relevance score DESC (backend-determined)
- Each chip: `[lang-badge][title 60ch][source-icon]` arranged per kb-2-UI-SPEC.md §3.3.2 chip pattern

### 3.4 Related entities sub-region (LINK-01 reuse)

- Backend returns up to 5 entities (top by frequency in source articles)
- Reuse kb-2 `.entity-chip` styling verbatim (chip-cloud with rounded chips)
- Click → `/entities/{slug}.html`

### 3.5 Feedback sub-region (UI-only, no backend)

- 👍 / 👎 buttons reuse kb-1 `thumb-up` / `thumb-down` icons from `_icons.html`
- localStorage write: `kb_qa_feedback_{job_id} = "up" | "down"`
- Visual selected state: filled icon + accent color (use kb-1 `.glow` for selected up; `.glow-green` doesn't apply — use neutral red glow OR text-secondary tone for "down")
- Feedback chosen: only one of up/down can be active per job (toggle behavior)
- **No POST endpoint this phase** — UI captures locally; v2.0.x or v2.1 may add POST `/api/feedback`

### 3.6 Search inline reveal

- Search input on homepage and list page reveals results inline below the search box (no new template)
- Container: `<div class="search-results" hidden></div>` injected just below the search form by kb-3 JS
- Each result: reuse kb-1 `.article-card` styling (already locked)
- Empty / loading / error states: reuse kb-1 `.empty-state` / `.skeleton` / `.error-state`
- KG mode (`?mode=kg`) uses the same async-job-id flow as `/api/synthesize` — UI handles via the same state machine

**Decision point: search results UI surface**
- ❌ Rejected: new `kb/templates/search.html` page → adds template surface, splits SSG output, conflicts with PRD's homepage-centric design
- ✅ Chosen: inline reveal → preserves kb-1 SSG output, additive JS only, search becomes a "magnifying glass" inside existing surfaces

### 3.7 New SVG icons needed

| Icon | When | Justification |
|---|---|---|
| `chat-bubble-question` | qa-question echo | Existing icons (`inbox`, `globe-alt`, `sparkle`) don't communicate "question" |
| `lightning-bolt` | fts5_fallback confidence chip | Conveys "quick / fast" — matches fallback-as-fast-path semantics |

If executor finds existing kb-1/kb-2 icons cover (e.g., reuse `sparkle` or `tag`), justify and proceed with reuse. Adding 2 icons to `_icons.html` macro library is acceptable per kb-2-UI-SPEC §3.5 precedent.

## 4. Page composition diagrams

### 4.1 ask.html — idle state (desktop)

```
┌─────────────────────────────────────────────────────┐
│  [Nav]                                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│         ✨ AI 智能问答 / AI Q&A                      │ <- gradient h1 (kb-1 lock)
│         深度回答 · 知识图谱驱动                       │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │ 输入你的问题... / Ask anything...             │ │ <- textarea, focus glow
│  │                                               │ │
│  └───────────────────────────────────────────────┘ │
│  [问 / Ask] (.glow)                                 │
│                                                     │
│  💡 热门问题 / Popular Questions                    │
│  - LangGraph 和 CrewAI 的区别？                     │
│  - 什么是 AI Agent 的最佳实践？                     │
│  - ... (5 quick-question chips)                    │
│                                                     │
│ ┌── #qa-result (hidden) ──────────────────────────┐│
│ │   (idle = display:none)                         ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│  [Disclaimer banner]                                │
│  [Bottom CTA banner]                                │
└─────────────────────────────────────────────────────┘
```

### 4.2 ask.html — polling state (desktop)

```
... (same chrome) ...
│  ┌──────────────────────────────────────────────┐  │
│  │ "AI Agent 框架如何选型?"               (locked)│  │
│  └──────────────────────────────────────────────┘  │
│  [问 / Ask] (disabled + spinner)                    │
│                                                     │
│ ┌── #qa-result data-qa-state="polling" ──────────┐ │
│ │  💬 "AI Agent 框架如何选型?"                    │ │ <- question echo
│ │                                                │ │
│ │  ⟳ 正在思考... / Thinking...                   │ │ <- spinner + state-text
│ │                                                │ │
│ └────────────────────────────────────────────────┘ │
```

### 4.3 ask.html — done state (desktop)

```
│ ┌── #qa-result data-qa-state="done" ─────────────┐ │
│ │  💬 "AI Agent 框架如何选型?"                    │ │
│ │                                                │ │
│ │  AI Agent 框架选型应考虑以下几个维度...        │ │ <- markdown answer
│ │  ## 主流框架对比                                │ │
│ │  - LangGraph: 状态机驱动...                    │ │
│ │  - CrewAI: 角色协作...                         │ │
│ │  ...                                           │ │
│ │                                                │ │
│ │  📚 参考来源 / Sources                          │ │
│ │  ┌────────────────────────────────────────┐   │ │
│ │  │ [💬 wechat] LangGraph vs CrewAI 实战... │   │ │
│ │  │ [🌐 rss] Building AI Agents with...     │   │ │
│ │  │ [💬 wechat] CrewAI 框架深度解读...      │   │ │
│ │  └────────────────────────────────────────┘   │ │
│ │                                                │ │
│ │  🏷 相关实体 / Related Entities                 │ │
│ │  [LangChain·24] [CrewAI·12] [LangGraph·9]     │ │
│ │  [OpenAI·89] [Anthropic·45]                    │ │
│ │                                                │ │
│ │  这个回答有帮助吗?  [👍] [👎]                   │ │
│ └────────────────────────────────────────────────┘ │
```

### 4.4 ask.html — fts5_fallback state (desktop)

```
│ ┌── #qa-result data-qa-state="fallback" ─────────┐ │
│ │  💬 "..."                                       │ │
│ │  [⚡ 快速参考 / Quick Reference]                │ │ <- yellow chip
│ │  基于关键词检索的快速回答,非完整知识图谱回答。  │ │
│ │                                                │ │
│ │  ## LangGraph vs CrewAI...                     │ │ <- FTS5 top-3 concat
│ │  ...                                           │ │
│ │                                                │ │
│ │  📚 参考来源 / Sources (3 articles)             │ │
│ │  ...                                           │ │
│ │  (no entities row — FTS5 has no entity links)  │ │
│ │  (no feedback row — restraint: only collect    │ │
│ │   feedback on full KG answers, not fallbacks)  │ │
│ └────────────────────────────────────────────────┘ │
```

### 4.5 ask.html — error state (mobile)

```
│ ┌── #qa-result data-qa-state="error" role="alert"┐ │
│ │  ⚠ 网络错误 / Network Error                     │ │
│ │  无法连接到服务器。Connection refused.          │ │
│ │  [重试 / Retry] (.glow)                         │ │
│ └────────────────────────────────────────────────┘ │
```

### 4.6 Homepage / list page — search inline reveal

```
┌─ kb-1 hero ─────────────────────┐
│ [搜索框 / search...]            │ <- existing input
│ [开始探索] [问个问题]            │
└──────────────────────────────────┘

(user types "langchain" in search → JS injects below the form:)

┌─ #search-results data-state="done" ─┐
│  (3 results found)                  │
│  ┌────────────────────────────────┐ │
│  │ [.article-card] LangGraph...   │ │ <- reuse kb-1 .article-card
│  │ [.article-card] LangChain in...│ │
│  │ [.article-card] AI Agents...   │ │
│  └────────────────────────────────┘ │
│  [查看全部 / View all] →            │
└──────────────────────────────────────┘

(latest articles section pushed down)
```

## 5. Locale keys (additions to `kb/locale/{zh-CN,en}.json`)

### NEW keys

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

### REUSED keys (already in kb-1/kb-2 locale)

- `nav.*`, `footer.*`, `home.section.*`
- `lang-badge.zh-CN`, `lang-badge.en`, `lang-badge.unknown` (lang chip labels)
- `card.read-more`, `card.snippet-fallback`
- `breadcrumb.*`, `disclaimer.*`, `cta.*`

## 6. JSON-LD schema

- `kb/templates/ask.html` head: `WebApplication` with `applicationCategory: "KnowledgeBase"`, `name: "VitaClaw Q&A"` per ARCHITECTURE §156
- No JSON-LD changes for inline search reveal (search is dynamic, not crawled)
- Existing kb-1 JSON-LD on ask.html (if any FAQPage was emitted for hot questions) preserved — kb-3 doesn't change

## 7. Accessibility + interaction state

- `aria-live="polite"` on `#qa-result` for state transitions
- `role="alert"` only on error banner (interrupts AT)
- Focus management: when state transitions to `done`, programmatically `.focus()` the qa-answer h1 or first heading inside markdown — keyboard users land on the answer
- All state-indicator copy goes through i18n filter (no hardcoded strings)
- `prefers-reduced-motion`: spinner becomes static dot; reveal animation skipped (instant)
- Color contrast verification:
  - yellow `.qa-confidence-chip--fallback` on dark bg → must hit AA (≥4.5:1)
  - red error banner on dark bg → AA
  - selected feedback button glow → AA
- Polling spinner: pure CSS keyframe (no JS animation), respects prefers-reduced-motion

## 8. Acceptance criteria (grep-verifiable)

```bash
# Templates
grep "qa-result" kb/templates/ask.html
grep "data-qa-state" kb/templates/ask.html
grep "qa-state-indicator" kb/templates/ask.html
grep "qa-fallback-banner" kb/templates/ask.html
grep "qa-error-banner" kb/templates/ask.html
grep "qa-sources" kb/templates/ask.html
grep "qa-entities" kb/templates/ask.html
grep "qa-feedback" kb/templates/ask.html
grep "qa-confidence-chip--fallback" kb/templates/ask.html

# JS module
test -f kb/static/qa.js
grep "fts5_fallback" kb/static/qa.js
grep "kb_qa_feedback_" kb/static/qa.js
grep "KB_QA_POLL_INTERVAL_MS" kb/templates/ask.html  # injected via Jinja
grep "marked" package.json 2>/dev/null || grep "marked" kb/static/qa.js  # markdown lib choice

# CSS — all new classes follow kb-1/kb-2 conventions
grep -E "\.qa-result\[data-qa-state=" kb/static/style.css
grep -E "\.qa-state-indicator" kb/static/style.css
grep -E "\.qa-confidence-chip--fallback" kb/static/style.css
grep -E "\.qa-source-chip" kb/static/style.css

# Locale keys
grep "qa.state.submitting" kb/locale/zh-CN.json
grep "qa.state.submitting" kb/locale/en.json
grep "qa.fallback.label" kb/locale/zh-CN.json
grep "search.results.empty" kb/locale/en.json

# Token discipline (regression guard)
test "$(grep -cE '^\s*--[a-z-]+:' kb/static/style.css)" -eq 31  # same as kb-1 baseline
test "$(wc -l < kb/static/style.css)" -le 2100  # kb-2 left it ~1979; kb-3 budget +120

# Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md)
grep -lE 'Skill\(skill="(ui-ux-pro-max|frontend-design|api-design|python-patterns|writing-tests)"' \
  .planning/phases/kb-3-fastapi-bilingual-api/*-SUMMARY.md | wc -l  # >= 5 (one per Required Skill)

# DATA-07 acceptance (cross-reference to DECISIONS doc)
grep -E "layer1_verdict = 'candidate'" kb/data/article_query.py | wc -l  # >= 6 (one per affected query function)
grep "KB_CONTENT_QUALITY_FILTER" kb/data/article_query.py  # env override present

# Icons
grep "chat-bubble-question" kb/templates/_icons.html
grep "lightning-bolt" kb/templates/_icons.html
```

**Total: ~30 grep patterns. Distribute across plan task `<acceptance_criteria>` blocks; planner must reference this section as the source of truth.**

## 9. Out of scope (kb-3 v2.0)

- POST `/api/feedback` endpoint (deferred to v2.0.x or v2.1)
- WebSocket streaming (HTTP polling only per D-19)
- Q&A history / saved answers UI (v2.1)
- Q&A multi-turn conversation (v2.2)
- Server-side rendered search results page (search remains client-side dynamic)
- KG-search separate UI flow (uses same async-job-id pattern as synthesize)
- Streaming markdown chunked render — non-streaming for v2.0; v2.1 may upgrade if backend supports
- Voice input UI (v2.x)
- Citation hover-card showing snippet preview (v2.1)

## 10. Skill invocation evidence

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 — named Skills are tool calls, not reading material. This UI-SPEC was authored by the orchestrator main session (sub-agent gsd-ui-researcher rate-limited at spawn time, 429 REQUEST_LIMIT_EXCEEDED on databricks-claude-opus-4-7); disciplines applied verbatim.

**Disciplines applied verbatim:**

- **ui-ux-pro-max — FAQ/Documentation Landing pattern** (per `kb/docs/02-DECISIONS.md` D-10): the Q&A page IS the documentation-search-and-answer surface; the result component is its central interaction
- **ui-ux-pro-max — Swiss Minimal Dark** (per `kb-1-UI-SPEC.md §1`): one signature moment per page (result reveal animation OR fts5_fallback honesty chip — choose one signature, not both. Recommend: result reveal animation in `done` state). Generous rhythm at desktop, tight at mobile
- **ui-ux-pro-max — restraint over excess**: rejected new `/search` page in favor of inline reveal; rejected streaming markdown for v2.0 (full reveal simpler); rejected separate "no results" + "error" + "timeout" pages in favor of state-attribute-driven sub-regions on a single component
- **frontend-design — anti-AI-aesthetic**: zero new tokens, zero new card variants. fts5_fallback chip uses honest "quick reference" copy, not "AI is thinking..." anthropomorphism
- **frontend-design — component restraint**: 3 new component patterns max (qa-result component, qa-source-chip, qa-fallback-banner). All other UI is reuse from kb-1 / kb-2. Search inline reveal is a JS pattern, not a new component

**Orchestrator action required at plan time:** the `gsd-planner` MUST emit literal `Skill(skill="ui-ux-pro-max", ...)`, `Skill(skill="frontend-design", ...)`, `Skill(skill="api-design", ...)`, `Skill(skill="python-patterns", ...)`, `Skill(skill="writing-tests", ...)` strings in plan SUMMARY.md files for verification regex match. **Without these, kb-3 phase is NOT-DONE per `kb/docs/10-DESIGN-DISCIPLINE.md`.**

## 11. Decisions where defaults were applied

| # | Decision | Default | Override path | Justification |
|---|---|---|---|---|
| D-1 | HTTP polling vs WebSocket | HTTP polling | D-19 mandates async polling | Locked by milestone |
| D-2 | Streaming vs non-streaming markdown | Non-streaming (full reveal on done) | v2.1 may upgrade | Simpler implementation; PRD §5.4 mockup doesn't specify; matches BackgroundTasks pattern |
| D-3 | Polling interval | 1500ms | env `KB_QA_POLL_INTERVAL_MS` | Balance UX (perceived latency) vs server load (multiple users polling) |
| D-4 | Polling timeout | 60s | env `KB_QA_POLL_TIMEOUT_MS` | Aligns with backend `KB_SYNTHESIZE_TIMEOUT` default; auto-switches to fts5_fallback after expiry |
| D-5 | Markdown library | `marked.js` v4+ | Bundle into static; no CDN | Smaller than markdown-it; sufficient feature set for KB content |
| D-6 | Search results UI | Inline reveal (no `/search` page) | — | Restraint principle; reuses kb-1 `.article-card`; preserves SSG output |
| D-7 | Feedback persistence | localStorage only this phase | v2.0.x or v2.1 may add POST `/api/feedback` | Defers backend work; UI captures intent now, server reads later |
| D-8 | Timeout → fts5_fallback transition | Automatic (500ms after timeout) | Manual click variant in v2.1 | Restraint: don't add buttons users won't click; degraded answer beats no answer |
| D-9 | fts5_fallback shows entities row? | NO (only sources) | — | FTS5 results have no entity links; showing empty entities row is dishonest |
| D-10 | fts5_fallback shows feedback buttons? | NO | v2.1 may add ("was the quick reference useful?") | Don't pollute KG-quality feedback with FTS5-quality feedback signal |
| D-11 | Streaming state visual treatment | Same as polling (spinner + text) until first chunk | — | v2.0 doesn't stream; state reserved for v2.1 |
| D-12 | Error retry: manual button vs auto-retry | Manual button | — | User explicit consent; auto-retry can mask persistent failures |

## 12. Inheritance for v2.1+ + kb-4 downstream

- **v2.1 candidates:** POST `/api/feedback` endpoint reads localStorage on page load + bulk-syncs (no UI re-design needed). Streaming markdown render upgrade reuses state matrix's `streaming` slot. Q&A history UI adds a left-rail nav (use kb-1 sidebar pattern from article.html). Multi-turn conversation extends the result component with thread display (out of scope here)
- **kb-4 deploy:** smoke test scenario #3 (LightRAG unavailable → fts5_fallback) validates this UI-SPEC §3.1 fts5_fallback path end-to-end. If kb-4 smoke discovers visual regressions, this UI-SPEC + kb-1 + kb-2 are the regression baseline. UI fix path: re-invoke ui-ux-pro-max + frontend-design Skills, NOT ad-hoc CSS patches (per `kb/docs/10-DESIGN-DISCIPLINE.md` kb-4 entry).
