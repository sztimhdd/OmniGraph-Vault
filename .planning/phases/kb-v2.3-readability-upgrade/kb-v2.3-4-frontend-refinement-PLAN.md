---
phase: kb-v2.3-readability-upgrade
plan: 4
type: execute
wave: 4
depends_on: [kb-v2.3-3]
files_modified:
  - kb/static/style.css
  - kb/templates/article.html
autonomous: false
requirements: [FRONTEND-REFINE, UAT-PRINCIPLE-6, DEPLOY-PRINCIPLE-9]
must_haves:
  truths:
    - "article.html + style.css refined via ui-ux-pro-max: responsive clamp body type, mobile line-height 1.6, refreshed code-block theme, improved blockquote + secondary-text contrast"
    - "D-12 token NAMES preserved, 760px measure preserved, i18n [data-lang] + lang.js intact, sticky sidebar + motion tokens + reduced-motion preserved"
    - "CSS works with bare <img> (content is pre-rendered raw img, no figure wrappers assumed)"
    - "Local browser UAT on >= 3 REWRITTEN articles at desktop/tablet/mobile confirms clean readable layout"
    - "Final deploy runs the FULL Makefile/daily_rebuild.sh (Pass 0 SSG bake onward), not sync-only"
  artifacts:
    - path: "kb/static/style.css"
      provides: "Refined article typography + code-block + blockquote + contrast tokens (refinement, not rebuild)"
    - path: "kb/templates/article.html"
      provides: "Refined article template (optional back-to-top/TOC per ui-ux-pro-max recommendation)"
    - path: ".planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-4-VERIFICATION.md"
      provides: "Local UAT section: launcher, curl smoke of /api/article/{hash}, screenshot paths, D-12 preservation grep evidence"
  key_links:
    - from: "kb/static/style.css article body rules"
      to: "responsive typography"
      via: "font-size clamp(...) + line-height 1.6 mobile (was 16px fixed / 1.8)"
      pattern: "clamp\\("
    - from: "final deploy"
      to: "SSG bake"
      via: "kb/scripts/daily_rebuild.sh full pipeline (Pass 0 onward) — kb/static + kb/templates touched (Principle #9)"
      pattern: "daily_rebuild"
---

<objective>
ui-ux-pro-max REFINEMENT (not rebuild) of the article reading page, verified against the CLEAN rewritten articles produced by Stage 1. Then deploy via the FULL Makefile pipeline (Principle #9) and run mandatory browser UAT (Principle #6).

Purpose: This runs LAST because dirty articles make it impossible to judge layout vs content — you cannot tell if a page reads badly because of CSS or because of surviving ads/boilerplate. With Stage 1 backfill done, the layout work is judged on genuinely clean content. Scope is refinement of the existing 2271-line :root token system, NOT a redesign.

Output: A polished 2026-tech-blog reading experience, deployed through the full SSG bake, UAT-verified at 3 viewports on clean articles, cited in VERIFICATION.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH-WEB.md
@kb/static/style.css
@kb/templates/article.html

<skills>
Use the ui-ux-pro-max skill to DRIVE all visual design decisions (palette, type scale, code-block theming, contrast, back-to-top/TOC pattern, light-mode yes/no recommendation). Do NOT hand-pick values — RESEARCH-WEB Section C notes the skill already carries 2026 style/palette/font-pairing intelligence. Invoke it via the Skill tool at the start of Task 1.
</skills>

<current_css_values>
<!-- Measured current values (CONTEXT.md specifics) — the refinement baseline. -->
- font body: Inter + Noto Sans SC, 16px FIXED (target: responsive clamp)
- article line-height: 1.8 (target: mobile 1.8 -> 1.6; RESEARCH-WEB Section C: 1.8 is caption-only)
- measure: 760px (LOCKED — keep; may express as min(760px, 92vw) or ch-based per RESEARCH-WEB C, but 760px measure must be preserved)
- bg #0f172a; text-primary #f0f4f8; text-secondary #94a3b8 (4.5:1 AA — target AAA)
- accent-blue #3b82f6; accent-green #22d3a0 (inline-code accent)
- code blocks: dated Monokai (target: refresh, align with #22d3a0 inline-code accent)
- images: PRE-RENDERED raw img, NO figure/figcaption — CSS MUST work with bare img, cannot assume figure wrappers
- blockquote: bland (bg same as card #1e293b — target: distinguish)
- container 1200px; breakpoints 480/640/768/1024/1200
- dark-only, no light mode (light-mode yes/no = ui-ux-pro-max design call — give a recommendation)
- no back-to-top / TOC anchor nav (target: consider adding)
</current_css_values>

<preservation_constraints>
<!-- Must survive the refinement (CONTEXT.md Stage 2 gate) — grep-verifiable. -->
- D-12 token NAMES preserved (do not rename/delete existing :root custom properties — refine VALUES, keep NAMES).
- 760px measure preserved.
- i18n [data-lang] attribute selectors + lang.js integration intact.
- sticky sidebar behavior preserved.
- motion tokens + prefers-reduced-motion reduced-motion block preserved.
</preservation_constraints>
</context>

<tasks>

<task type="auto">
  <name>Task 1: ui-ux-pro-max refinement of style.css + article.html</name>
  <files>kb/static/style.css, kb/templates/article.html</files>
  <read_first>
    - kb/static/style.css (FULL — the 2271-line :root token system; identify the article-body, code-block, blockquote, secondary-text, and breakpoint rules to refine; note all :root token NAMES for the preservation grep)
    - kb/templates/article.html (the template — [data-lang] blocks, sidebar structure, lang.js hook)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH-WEB.md (Section C 2026 tech-blog design: clamp type, line-height 1.5-1.6, ch-based measure, container queries optional, Stripe/Vercel/Linear as the bar, subtle code-block theming)
    - kb-v2.3-CONTEXT.md (decisions Frontend section — known improvement targets with measured current values; Deferred: light-mode is plan-optional)
    - ui-ux-pro-max SKILL.md (invoke the skill for design decisions)
  </read_first>
  <action>
Invoke the ui-ux-pro-max skill first (Skill tool) to drive design decisions, then apply REFINEMENTS (not a rebuild) to kb/static/style.css and kb/templates/article.html. Concrete targets (CONTEXT.md measured baseline):

1. Body typography: replace the hardcoded article-body `font-size: 16px` with a fluid clamp, e.g. `font-size: clamp(1rem, 0.9rem + 0.5vw, 1.25rem)` (final values per ui-ux-pro-max). Change mobile `line-height` from 1.8 -> ~1.6 (1.8 is caption-only per RESEARCH-WEB C). Use rem; must survive 200% zoom (WCAG 1.4.4).
2. Measure: KEEP the 760px measure. Optionally express as `min(760px, 92vw)` or a ch-based form, but 760px must remain the effective measure (preservation constraint).
3. Code blocks: refresh the dated Monokai theme to align with the #22d3a0 inline-code accent — a restrained, consistent code-block palette (ui-ux-pro-max call; Stripe/Vercel/Linear bar).
4. Blockquote: distinguish from card bg #1e293b (border accent / subtle bg shift).
5. Secondary text contrast: raise #94a3b8 (currently 4.5:1 AA) toward AAA where feasible without breaking the palette.
6. Images: ensure the refined CSS works with BARE img (content is pre-rendered raw img — NO figure/figcaption wrappers). Do NOT add rules that assume figure.
7. Optional (ui-ux-pro-max recommendation): back-to-top button and/or TOC anchor nav in article.html. Include or defer per the skill's recommendation — document the call in SUMMARY.
8. Light mode: include or defer per ui-ux-pro-max recommendation — document the call in SUMMARY (CONTEXT.md leaves this plan-optional).

Refine VALUES, preserve token NAMES. Do NOT rebuild the design system, do NOT delete D-12 tokens, do NOT rip out existing SSG regex (out of scope). Match existing CSS style/structure (Surgical Changes).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "css=open('kb/static/style.css',encoding='utf-8').read(); assert 'clamp(' in css and '760px' in css and 'prefers-reduced-motion' in css and '[data-lang' in css; print('css guards ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "clamp(" kb/static/style.css` >= 1 (fluid type applied).
    - `grep -c "760px" kb/static/style.css` >= 1 (measure preserved).
    - `grep -c "prefers-reduced-motion" kb/static/style.css` >= 1 (reduced-motion block preserved).
    - `grep -c "\[data-lang" kb/static/style.css kb/templates/article.html` >= 1 (i18n intact).
    - D-12 :root token NAMES preserved: capture the `--` custom-property names before the edit (`grep -oE "^\s*--[a-z0-9-]+" kb/static/style.css | sort -u`) and confirm the same set exists after (no NAME deleted; VALUES may change).
    - The css-guards inline assertion passes.
    - SUMMARY documents the light-mode and back-to-top/TOC decisions (include or defer + why).
  </acceptance_criteria>
  <done>style.css + article.html refined via ui-ux-pro-max (clamp type, 1.6 mobile line-height, refreshed code blocks, distinguished blockquote, improved secondary contrast, bare-img-safe); all preservation constraints grep-verified; light-mode + back-to-top decisions documented.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Full-Makefile deploy (Principle #9) + browser UAT on 3 clean articles at 3 viewports (Principle #6)</name>
  <files>kb/output/ (SSG bake artifacts), .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-4-VERIFICATION.md, .playwright-mcp/kb-v2.3-uat-*.png</files>
  <action>
This is a human-verify checkpoint. The executor performs the LOCAL UAT + REMOTE full-Makefile deploy + VERIFICATION.md authoring documented in <how-to-verify> (Claude owns deploy per Principle #7), then PAUSES for the operator to review the 9 UAT screenshots + VERIFICATION.md before the phase is marked complete (Principle #6).
  </action>
  <read_first>
    - kb/scripts/daily_rebuild.sh (the 5-phase full bake — Stage-2 deploy MUST run this, NOT sync-only, per Principle #9)
    - .scratch/local_serve.py (single-port :8766 launcher for local UAT per Principle #6)
    - kb-v2.3-CONTEXT.md (success_criteria Stage 2 — Principle #6 + #9 gates verbatim)
    - CLAUDE.md Principle #9 (touching kb/static or kb/templates REQUIRES full Makefile deploy — sync-only silently ships stale _ssg/ assets) and Principle #6 (KB local UAT mandatory before phase complete)
    - MEMORY.md: aliyun_kb_serve_dir_gap.md (bake writes kb/output/, Caddy serves /var/www/kb/ — RESOLVED via daily_rebuild Phase 5 rsync; confirm the deploy uses daily_rebuild so the rsync fires), databricks_ssg_lang_flip.md (SSG lang-flip recipe if the bake touches lang)
  </read_first>
  <what-built>
    Refined article.html + style.css (ui-ux-pro-max: clamp typography, 1.6 mobile line-height, refreshed code blocks, distinguished blockquote, higher secondary-text contrast, bare-img-safe) with all D-12 preservation constraints grep-verified. This step bakes the refinements through the full SSG pipeline and verifies them in a browser on CLEAN (rewritten) articles.
  </what-built>
  <how-to-verify>
    Executor performs (Claude owns deploy per Principle #7):

    LOCAL UAT (Principle #6 — mandatory, do BEFORE remote deploy):
    1. Refresh kb/output/ so the SSG renders the refined template + CSS against clean bodies (run the bake locally, or the SSG-bake portion of daily_rebuild).
    2. Start `venv/Scripts/python.exe .scratch/local_serve.py` (single port :8766 serves SSG + /api/* + /static/*).
    3. curl-smoke `/api/article/{hash}` for 3 articles that HAVE body_rewritten (pick from the Stage 1 backfill — confirm the returned body is the clean rewritten version, no 关注公众号 boilerplate).
    4. Browser UAT (Playwright MCP) on those 3 REWRITTEN articles at desktop (1280), tablet (768), mobile (390): confirm clean readable layout, no horizontal scroll, code blocks + blockquotes + images render, i18n lang toggle works. Screenshots to `.playwright-mcp/kb-v2.3-uat-{article}-{viewport}.png` (9 shots: 3 articles x 3 viewports).
    5. browser_console_messages(level="error") + browser_network_requests: confirm no 4xx/5xx, no CSS 404.

    REMOTE DEPLOY (Principle #9 — FULL pipeline, NOT sync-only):
    6. Run the FULL kb/scripts/daily_rebuild.sh (Pass 0 SSG bake onward) on Aliyun so the refined kb/static + kb/templates reach the served _ssg/ + /var/www/kb/ (the Phase-5 rsync closes the aliyun_kb_serve_dir_gap). Do NOT sync-only — that ships stale assets.
    7. Post-deploy: curl the live article page + one clean article; confirm the refined CSS is served (grep the served CSS for `clamp(`).

    VERIFICATION.md:
    8. Write `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-4-VERIFICATION.md` with a "Local UAT" section: launcher used, env values, curl smoke results (status + key fields showing clean body), the 9 screenshot paths, D-12 preservation grep evidence, and the full-Makefile deploy confirmation.
  </how-to-verify>
  <resume-signal>Type "approved" after reviewing the 9 UAT screenshots + VERIFICATION.md, or describe layout issues to iterate Task 1.</resume-signal>
  <verify>
    <automated>curl -s http://127.0.0.1:8766/static/style.css | grep -c 'clamp('  # served CSS carries the refinement; and ls .playwright-mcp/kb-v2.3-uat-*.png | wc -l == 9</automated>
  </verify>
  <done>Local UAT ran on >= 3 rewritten articles at desktop/tablet/mobile (9 screenshots under .playwright-mcp/kb-v2.3-uat-*.png); curl /api/article/{hash} shows clean body (0 boilerplate); no console/network errors; final deploy ran FULL daily_rebuild.sh (not sync-only), served CSS contains clamp; kb-v2.3-4-VERIFICATION.md cites all UAT evidence.</done>
  <acceptance_criteria>
    - Local UAT ran on >= 3 REWRITTEN articles at desktop/tablet/mobile; 9 screenshots exist under `.playwright-mcp/kb-v2.3-uat-*.png`.
    - curl `/api/article/{hash}` for the 3 UAT articles returns the CLEAN body (0 boilerplate markers like 关注公众号 in the served body).
    - No console errors, no 4xx/5xx, no CSS 404 in the UAT network log.
    - Final deploy ran the FULL daily_rebuild.sh (Pass 0 onward), NOT sync-only — evidenced by the bake log; served CSS contains `clamp(` (grep the live/deployed CSS).
    - kb-v2.3-4-VERIFICATION.md exists with the Local UAT section (launcher, curl results, 9 screenshot paths, D-12 grep evidence, full-Makefile deploy confirmation).
    - Phase NOT marked complete until this UAT is performed and cited (Principle #6).
  </acceptance_criteria>
</task>

</tasks>

<verification>
- Refinement grep-verified: clamp present, 760px measure preserved, prefers-reduced-motion preserved, [data-lang] intact, D-12 token NAMES unchanged.
- Local UAT on 3 clean rewritten articles at 3 viewports; 9 screenshots; curl shows clean body; no console/network errors.
- Full daily_rebuild.sh deploy (Principle #9), NOT sync-only; served CSS contains clamp.
- kb-v2.3-4-VERIFICATION.md cites all UAT evidence.
</verification>

<success_criteria>
CONTEXT.md Stage 2 gates satisfied:
- "ui-ux-pro-max refinement applied to article.html + style.css; D-12 token NAMES preserved (grep), 760px measure preserved, i18n [data-lang] + lang.js intact, sticky sidebar + motion tokens + reduced-motion preserved."
- "Principle #6 (mandatory): local_serve.py + browser UAT on >= 3 REWRITTEN articles at desktop/tablet/mobile; screenshots to .playwright-mcp/kb-v2.3-uat-*.png; cited in VERIFICATION.md with curl smoke of /api/article/{hash} showing the clean body."
- "Principle #9 (mandatory): final deploy runs the FULL Makefile / daily_rebuild.sh (Pass 0 SSG bake onward), NOT sync-only, because kb/static + kb/templates are touched."
</success_criteria>

<output>
After completion, create `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-4-frontend-refinement-SUMMARY.md` and `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-4-VERIFICATION.md`.
</output>
