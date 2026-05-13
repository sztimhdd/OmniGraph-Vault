---
status: gaps_found
phase: kb-1-ssg-export-i18n-foundation
audit_type: design_dimension_skip_audit
audit_date: 2026-05-13
auditor: orchestrator (post-HUMAN-UAT visual review)
trigger: User feedback "网页好丑 你确定按照文档进行了设计?调用了 frontend-design 和 ui-ux-pro-max 的设计能力?"
severity: structural — design dimension was bypassed across the entire phase
---

# Phase kb-1 — Design Dimension Skip Audit

## Executive Summary

**The kb-1 phase satisfied every codebase-checkable acceptance criterion (26/27 REQs, 73/73 tests, 4/8 truths VERIFIED + 4 human-verifiable PASS) — but the visual / design dimension was systematically skipped at every layer.**

Confirmed by user visual inspection 2026-05-13: "网页好丑". Subsequent code/spec audit confirms:

- **No `kb-1-UI-SPEC.md` ever produced** — the `/gsd:plan-phase` Step 5.6 "UI Design Contract Gate" was bypassed
- **`frontend-design` skill: 0 invocations** across all 11 plans
- **`ui-ux-pro-max` skill: 0 invocations** across all 11 plans, despite `kb/docs/02-DECISIONS.md` D-10 / `kb/docs/03-ARCHITECTURE.md` § "ui-ux-pro-max 设计系统推荐" explicitly mandating its adoption
- **D-12 specific tokens (`rounded-2xl`, `.glow`, `.glow-green`, `hover:border-accent/30`) absent from `kb/static/style.css`**
- **Templates implement REQ checkboxes; do NOT implement design language**

Contrast with what the milestone source documents specified:

| Source | Specified |
|---|---|
| `kb/docs/00-KB-KICKOFF-PROMPT.md:163` | "设计风格:Minimalism & Swiss Style,暗色主题" |
| `kb/docs/01-PRD.md` §5 | Full ASCII mockups (首页 / 文章页 / 实体页 / 问答页) with hero, sidebar, CTA layout |
| `kb/docs/02-DECISIONS.md` D-10 | "ui-ux-pro-max 设计指引" — adopt FAQ/Documentation Landing pattern |
| `kb/docs/02-DECISIONS.md` D-12 | "卡片: rounded-2xl border border-card-border bg-card hover:border-accent/30 transition" + "CTA按钮: .glow 类" |
| `kb/docs/03-ARCHITECTURE.md` §双搜索/问答入口交互设计 | Detailed UI patterns per page type |
| `kb/docs/03-ARCHITECTURE.md` §ui-ux-pro-max 设计系统推荐 | "Pattern: FAQ/Documentation Landing", "首屏:搜索栏突出 + 热门分类 + FAQ", "风格:Minimalism & Swiss Style(暗色适配版)" |
| `kb/docs/05-KB2-ENTITY-SEO.md` (out of scope) | — kb-2 skipped, OK |

## Root Cause: Where the gate failed

The `/gsd:plan-phase` workflow Step 5.6 is the safety gate that should have caught this:

```
PHASE_HAS_UI=$(echo "$PHASE_SECTION" | grep -qi "UI hint.*yes" && echo "true" || echo "false")
# If HAS_UI is true AND no UI-SPEC.md exists → AskUserQuestion: Generate UI-SPEC first?
```

**`.planning/ROADMAP-KB-v2.md:134` literally says `**UI hint:** yes` for kb-1.** The gate detection condition was met.

**Why it failed to fire:**

1. `gsd-tools.cjs init plan-phase kb-1` returned `phase_found: false` because the parallel-track suffix-files convention (`-KB-v2.md`) is unrecognized by the standard tooling (gsd-tools reads main `.planning/ROADMAP.md`, not `ROADMAP-KB-v2.md`)
2. With `phase_found=false`, the orchestrator drove `/gsd:plan-phase` manually with a hand-crafted `<plan_decomposition_hint>` that pre-baked structural decomposition WITHOUT a design contract step
3. The orchestrator (me) read the phase-has-UI fact from ROADMAP and chose to "synthesize CONTEXT.md from existing artifacts" via the PRD-express-path equivalent — equating `kb/docs/02-DECISIONS.md` design-token entries with a UI-SPEC. This was the judgment error.
4. `kb/docs/02-DECISIONS.md` mentions ui-ux-pro-max's recommendations as ADVISORY in flat text; nothing in the milestone-level docs explicitly says "agents MUST invoke `ui-ux-pro-max` Skill at plan time"
5. The downstream gsd-planner agent treated `kb/docs/03-ARCHITECTURE.md "ui-ux-pro-max 设计系统推荐"` as a `read_first` reference (text to read), not as an instruction to invoke the named Skill

**Net effect:** Each plan satisfied its REQ checkbox to the letter (token values copied verbatim, page structure matches mockup at the section-name level), but no design-system pass was ever made. The CSS is "vanilla design-token-driven minimal" (587 LOC) — correct but not designed.

## Severity-ranked findings (8 critical-to-low)

### 🔴 #1 [STRUCTURAL] No UI-SPEC.md created — design contract dimension skipped end-to-end

**Evidence:** No `kb-1-UI-SPEC.md` in phase dir. `grep -r "UI-SPEC" .planning/phases/kb-1*/` returns 0 hits. ROADMAP-KB-v2.md:134 has `**UI hint:** yes`. Workflow Step 5.6 was supposed to fire.

**Impact:** Every downstream plan (kb-1-04 / kb-1-07 / kb-1-08 / kb-1-09) had no design contract to verify against. Plan-checker (`gsd-plan-checker`) never had a pillar to score visual quality on. Verification (`gsd-verifier`) was structural only.

**Fix:** Run `/gsd:ui-phase kb-1` retroactively. Output: `kb-1-UI-SPEC.md` with patterns/components/states locked.

### 🔴 #2 [SKILL] `ui-ux-pro-max` and `frontend-design` Skills never invoked

**Evidence:**
- `kb/docs/02-DECISIONS.md` D-10 line 124-130: "采纳ui-ux-pro-max FAQ/Documentation Landing"
- `kb/docs/03-ARCHITECTURE.md` line 325-333: "ui-ux-pro-max 设计系统推荐: Pattern: FAQ/Documentation Landing"
- Grep across all 11 PLAN.md + 11 SUMMARY.md + CONTEXT.md + VERIFICATION.md for "ui-ux-pro-max" returns ONLY ONE hit (`kb-1-04-PLAN.md:107`) and that's a `<read_first>` text reference (i.e., "go read this section of `kb/docs/03-ARCHITECTURE.md`"), NOT a `Skill(skill="ui-ux-pro-max", ...)` tool call
- Grep for "frontend-design" returns 0 hits anywhere

**Impact:** No designer-quality components, no Bento grid evaluation, no glassmorphism / brutalism / claymorphism style consideration, no proper color palette derivation beyond the 5 vitaclaw tokens, no font-pairing validation, no UX guideline cross-check.

**Fix:** kb-1 redesign quick MUST invoke both Skills explicitly:
```python
Skill(skill="ui-ux-pro-max", args="audit kb-1 templates against FAQ/Documentation Landing pattern + Swiss Style; output component spec for hero/cards/lang-chip/breadcrumb/CTA/code-block/Q&A-form")
Skill(skill="frontend-design", args="iterate kb/templates/*.html and kb/static/style.css to match the spec; preserve i18n + content lang axis")
```

### 🔴 #3 [TOKEN] D-12 explicit tokens absent from `kb/static/style.css`

**Evidence:** `grep -nE "rounded-2xl|\.glow|glow-green|hover:border-accent" kb/static/style.css` → 0 hits.

D-12 lock spec (kb/docs/02-DECISIONS.md line 174-198):
| Spec | Reality in style.css |
|---|---|
| `卡片: rounded-2xl border border-card-border bg-card` | `.card { border-radius: 8px }` (8px = `rounded`, not `rounded-2xl` 16px) |
| `hover:border-accent/30 transition-all duration-300` | `.article-card:hover { border-color: var(--accent) }` (hard color swap, not 30% opacity) |
| `CTA按钮: .glow 类` | **`.glow` does not exist** |
| `.glow-green` 类 | **`.glow-green` does not exist** |
| `卡片悬浮: #2a3a4a` (D-12 新增) | **No hover background change implemented** |

**Impact:** Visual identity diverges from sibling vitaclaw-site. Hover states are flat. CTAs lack the shimmer/glow that signal interactivity.

**Fix:** Add to style.css:
- `.card { border-radius: 16px; }` (rounded-2xl = 1rem)
- `.card:hover { background: #2a3a4a; border-color: rgba(59, 130, 246, 0.3); }` (hover bg + 30% accent opacity)
- `.glow { box-shadow: 0 0 24px -4px rgba(59, 130, 246, 0.6); }`
- `.glow-green { box-shadow: 0 0 24px -4px rgba(34, 211, 160, 0.6); }`
- `.btn { transition: all 300ms ease; }` (was 0.15s opacity only)

### 🔴 #4 [LAYOUT] Hero section is bare — no visual treatment

**Evidence:** `kb/templates/index.html:6-11` — hero is just `<h1>` + `<p>`. No search bar, no hot topics chips, no CTA emphasis, no gradient text accent, no decorative element.

`kb/docs/03-ARCHITECTURE.md` § "ui-ux-pro-max 设计系统推荐" + `kb/docs/01-PRD.md` §5.2 mockup explicitly specify:
- 大字号 + gradient 强调词 hero h1
- 副标题层次 (h2/p hierarchy)
- 主搜索框 prominent in hero
- 热门 chips (推荐 categories)
- 双 CTA buttons (开始探索 / 问个问题)

**Impact:** Homepage looks like a plain blog listing instead of a "knowledge platform" landing page.

**Fix:** Redesign hero per PRD §5.2 mockup: gradient h1 + search bar + topic chips + 2 CTAs.

### 🟡 #5 [COMPONENT] Article cards: flat, no snippet, no chip styling

**Evidence:** `kb/templates/index.html:21-29` and `articles_index.html:30-42` — card is title-link + meta-row only. No body snippet, no source icon, lang badge is text-in-pill (uniform green for all langs incl. unknown "—").

`kb/docs/03-ARCHITECTURE.md` line 156-157 specifies card content includes title + 200-char snippet preview. PRD §5.2 mockup shows `来源: 机器之心 · 2026-05-10 · AI智能体 / [snippet 80-120 chars]`.

**Impact:** Cards reveal no content preview. Users must click through to learn anything. Source labels are unstyled raw text (`rss` / `wechat`). Lang badge for `unknown` (1660 articles, 73% of corpus) shows literal `—` em-dash on green pill — visually broken.

**Fix:**
- Add `.article-card-snippet` with body-derived 200-char excerpt (export driver provides; template renders)
- Replace lang-badge logic: `zh-CN` → blue pill, `en` → green pill, `unknown` → grey pill (or hide)
- Source: `rss` → 🌐 RSS icon, `wechat` → 💬 WeChat icon (or proper SVG icons)
- Card hover: glow + slight scale transform

### 🟡 #6 [TYPOGRAPHY/DATA] Date format is raw RFC 822 / ISO

**Evidence:** Article cards display `Wed, 4 Sep 2024 04:31:00 +0000` (RSS RFC 822 raw) or `2026-04-23T00:00:00+00:00` (KOL ISO raw).

**Impact:** Raw machine-readable strings instead of human-friendly relative or formatted dates.

**Fix:** Add a `humanize_date` Jinja2 filter in `kb/i18n.py`:
- `2024-09-04T04:31:00Z` → `2024 年 9 月 4 日` (zh-CN) / `Sep 4, 2024` (en)
- For recent (<7 days): `2 天前` / `2 days ago`

### 🟡 #7 [PAGE] Q&A page is "coming soon" placeholder, not designed

**Evidence:** `kb/templates/ask.html:9-22` — form posts to nothing, JS submission shows literal text "Q&A backend will be wired in kb-3".

`kb/docs/03-ARCHITECTURE.md` §入口2 mockup specifies:
- Hero with input + 深度问答 button (large, glow-styled)
- 🔥 热门问题 list (5-6 hardcoded for v2.0)
- 回答区域 (Markdown render placeholder)
- 📎 来源文章 + 🔗 相关实体 + 🖼️ 图片 sections (post-render)
- ⚠️ 免责声明 styling
- 👍/👎 反馈 buttons
- 底部 CTA 横幅

**Implementation has:** textarea + submit button + result div + flat disclaimer. **Missing:** hot questions list, sections framework, feedback buttons, CTA banner, prominent visual hierarchy.

**Impact:** Even as a placeholder, the Q&A page should LOOK like the spec'd Q&A flow so users (a) know what to expect when kb-3 wires it up, (b) see the visual identity. Currently it looks like a contact form.

**Fix:** Implement full Q&A page LAYOUT per spec; backend stays placeholder with a "kb-3 backend pending" notice in the result region. Hot questions list can be hardcoded for v2.0.

### 🟡 #8 [INTERACTION] No focus states, no transitions beyond 0.15s, no motion

**Evidence:** `grep "transition\|animation\|focus\|focus-visible" kb/static/style.css` → only 4 transitions all at 0.15s ease (opacity, border-color); zero `:focus-visible` outlines (a11y gap); zero animations.

**Impact:** Keyboard navigation has no visible focus indicator (a11y violation). Hovers are abrupt. No micro-interactions on language toggle, card focus, button press.

**Fix:**
- Global `*:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`
- Card hover: `transition: all 300ms cubic-bezier(0.4, 0, 0.2, 1)`
- Lang toggle: subtle bounce on click

### 🟢 #9 [LOW] Breadcrumb separator is text `>` not chevron icon

**Evidence:** `article.html:54-58` uses literal `<span> &gt; </span>` between crumb links.

**Impact:** Cosmetic. Modern sites use SVG chevron or Unicode `›` for visual polish.

**Fix:** Replace `&gt;` with inline SVG chevron or `›` (U+203A).

### 🟢 #10 [LOW] No empty / loading / error states designed

**Evidence:** No `.empty-state`, `.loading-spinner`, `.error-message` classes. Article-list empty case shows a flat `<p>` with i18n text.

**Impact:** When kb-3 wires API and a search returns 0 hits, there's no designed empty state. When `/synthesize` is loading, no skeleton.

**Fix:** Add empty/loading/error component CSS (light scope; kb-3 will populate them).

### 🟢 #11 [LOW] No icons anywhere in the UI

**Evidence:** `grep "<svg\|<i class\|font-awesome\|heroicon" kb/templates/*.html` → 0 hits.

**Impact:** Site feels textual. Source labels (`rss` / `wechat`), nav items, meta info, breadcrumb separator could all carry tiny icons for visual rhythm.

**Fix:** Inline SVG icons for nav/meta/breadcrumb (no external CDN — perform inline `<svg>` in templates).

### 🟢 #12 [LOW] No print stylesheet, no high-contrast variant, no `prefers-reduced-motion` honored

**Evidence:** `grep "@media print\|prefers-contrast\|prefers-reduced-motion" kb/static/style.css` → 0 hits.

**Impact:** A11y / printability gaps. Not blocking but worth noting.

**Fix:** Defer to v2.1 unless critical.

## Cross-template propagation summary

| Template | LOC | Plan | Design dimension status |
|---|---|---|---|
| `base.html` | 53 | kb-1-07 | ⚠️ Functional layout, no design polish (no logo treatment, no nav backdrop, no footer styling beyond text) |
| `index.html` | 47 | kb-1-07 | 🔴 Hero is bare h1+p; cards are flat; ask CTA is small inline card |
| `articles_index.html` | 50+ | kb-1-07 | 🔴 Native `<select>` filters (browser default styling); no chip filter pattern; no pagination |
| `article.html` | 105 | kb-1-08 | 🟡 Has badge + breadcrumb but no TOC sidebar, no reading progress, no copy buttons on code blocks, no related articles section |
| `ask.html` | 28 | kb-1-07 | 🔴 "Coming soon" placeholder — none of the spec'd Q&A page layout |
| `style.css` | 587 | kb-1-04 | 🔴 D-12 tokens absent (rounded-2xl / glow); no `:focus-visible`; no hover bg change; no Pygments wrapper styling |
| `lang.js` | ~104 | kb-1-04 | ✅ Functional 4-tier resolver (this is the one piece that's design-correct) |

## Other GSD-style "skip the design dimension" patterns to watch for in kb-3 / kb-4

This audit revealed a structural pattern that will recur unless addressed:

1. **Parallel-track milestones bypass `gsd-tools.cjs` validation** — The suffix-files convention (`*-KB-v2.md`) is invisible to the toolchain. Every workflow Step that depends on `init` parsing the right ROADMAP / REQUIREMENTS will silently skip checks. **Mitigation:** orchestrator MUST manually run the gate logic (UI Design Contract Gate, Nyquist Validation Gate, Requirements Coverage Gate) when driving parallel-track plan-phase manually.

2. **PRD/decisions docs that recommend Skills as advisory text don't trigger Skill invocations** — `kb/docs/02-DECISIONS.md` D-10 said "采纳 ui-ux-pro-max 模式" but no plan task said "Skill(skill='ui-ux-pro-max', ...)". **Mitigation:** when a milestone-level doc names a Skill by name, kb-1-CONTEXT.md (and equivalent for kb-3 / kb-4) MUST list the Skill in `<canonical_refs>` AS A SKILL TO INVOKE, not just a doc to read.

3. **Plan-checker scores frontmatter + REQ coverage + dependency correctness — but has no Visual Quality dimension** — When UI-SPEC.md is missing, the checker has no Pillar to score against. **Mitigation:** `/gsd:ui-review` (retroactive 6-pillar visual audit) should be called for any phase with `UI hint: yes` after planner runs and before execution begins.

## Remediation plan

### Path A — Run the proper UI workflow retroactively (recommended)

1. `/gsd:ui-phase kb-1` — invoke `gsd-ui-researcher` agent with explicit `Skill(skill="ui-ux-pro-max", ...)` + `Skill(skill="frontend-design", ...)` calls. Output: `kb-1-UI-SPEC.md` design contract.
2. `/gsd:ui-review kb-1` — `gsd-ui-auditor` runs 6-pillar visual audit on existing kb/output/. Output: `kb-1-UI-REVIEW.md` with scored gaps.
3. `/gsd:quick "kb-1-ui-iter1: implement UI-SPEC + close UI-REVIEW gaps"` — single quick task that:
   - Rewrites `kb/static/style.css` against UI-SPEC token + component scale
   - Updates 5 templates (`base.html` / `index.html` / `articles_index.html` / `article.html` / `ask.html`) per UI-SPEC components
   - Adds icons, chips, hover states, focus states, empty/loading/error states
   - Re-renders `kb/output/` and re-runs Playwright UAT for visual + a11y verification
4. Update `kb-1-VERIFICATION.md` and `kb-1-HUMAN-UAT.md` to add a new UAT 5 "Visual quality re-verification — UI-REVIEW score >= passing threshold"

**Workload:** 1-2 days. Output: properly designed bilingual SSG.

### Path B — Quick redesign without UI-SPEC

Single quick task that invokes both Skills + iterates templates + CSS. Skip the formal UI-SPEC artifact.

**Workload:** 0.5-1 day. Risk: kb-3 / kb-4 will recur the same gap because no contract artifact exists for them to inherit.

### Path C — Defer to kb-3 polish pass

Land kb-3 (FastAPI) first; do the visual redesign as part of kb-3 completion. **Not recommended** — entrenches "design as afterthought" anti-pattern across the milestone.

## Recommendation

**Path A.** The UI-SPEC artifact pays back across kb-3 (Q&A polish) + kb-4 (smoke verification) + v2.1 (KB-2 entity pages, when revived). The 0.5-day cost upfront saves the iteration cost on every following phase.

## References

- Triggering user feedback: chat transcript 2026-05-13 ~17:30 UTC
- Source design specs (NOT followed):
  - `kb/docs/00-KB-KICKOFF-PROMPT.md:163` (Minimalism & Swiss Style mention)
  - `kb/docs/01-PRD.md` §5 (full UX mockups)
  - `kb/docs/02-DECISIONS.md` D-10, D-12 (ui-ux-pro-max + token spec)
  - `kb/docs/03-ARCHITECTURE.md` §双搜索/问答入口交互设计 + §ui-ux-pro-max 设计系统推荐
- Workflow gate that should have caught this: `~/.claude/get-shit-done/workflows/plan-phase.md` Step 5.6 "UI Design Contract Gate"
- Available skills (not invoked):
  - `frontend-design` — "Create distinctive, production-grade frontend interfaces with high design quality... avoids generic AI aesthetics"
  - `ui-ux-pro-max` — "UI/UX design intelligence... 50+ styles, 161 color palettes, 57 font pairings, 161 product types, 99 UX guidelines"

---

*Audit performed: 2026-05-13 by orchestrator post-HUMAN-UAT visual review.*
*Closes the gap between "REQ-checkbox-satisfied" and "actually-well-designed".*
