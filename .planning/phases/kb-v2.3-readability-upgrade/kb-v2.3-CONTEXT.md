# Phase kb-v2.3: KB Article Readability Upgrade — Context

**Gathered:** 2026-07-02
**Status:** Ready for planning
**Source:** Locked-decision brief (PRD-equivalent) + 2026-07-02 5-subsystem read-only map (workflow wf_7c9b1788-287)
**Track:** KB-v2 parallel track (ROADMAP-KB-v2.md; follows kb-v2.2). Suffix-track — gates run manually per `feedback_parallel_track_gates_manual_run`.

<domain>
## Phase Boundary

**Delivers:** KB article pages that read like a 2026 tech blog — clean, well-formatted, bilingual, correct image placement, with ads/boilerplate/format-noise removed. Two ORDERED stages in one phase (dependency, not parallel):

- **Stage 1 (content):** A NEW post-ingest async LLM rewrite pass produces a clean, source-language display version of each article body, stored in a NEW `body_rewritten` column. The existing translation cron then reads `body_rewritten` (instead of the dirty `body`) and produces clean English. Full backfill of all ~572 displayed articles (KOL 463 + RSS 109).
- **Stage 2 (frontend):** ui-ux-pro-max REFINEMENT (not rebuild) of the article template + CSS, verified in a browser against the CLEAN rewritten articles from Stage 1.

**Does NOT deliver / out of scope:**
- Any change to LightRAG KG ingest or entity extraction (KG stays sourced from ORIGINAL `body` — Decision A).
- Rebuilding the design system or deleting D-12 locked tokens (refinement only).
- Ripping out existing SSG regex transforms (Surgical Changes — they become moot for clean articles, don't remove them).
- Throughput/#40 work; the rewrite cron is separate from ingest and must not slow ingest.

**Root cause being fixed (measured 2026-07-02):** the WeChat ingest path (`ingest_wechat.py:1101-1117`) skips trafilatura boilerplate extraction (the RSS/generic path uses it) and does raw BeautifulSoup+html2text — ads/nav/tracking-JS/mangled-tables/duplicated-image-refs survive into `body`. This is an INGEST-layer problem surfacing at display time; the fix is a semantic LLM rewrite into a display-only column, NOT more render-layer regex.
</domain>

<decisions>
## Implementation Decisions (ALL LOCKED — do not re-litigate)

Full rationale in memory `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/decision_rewrite_display_only_kg_uses_original.md` — planner and checker MUST read it.

### ⚠️ CORRECTED PREMISE (LIVE-PROBE-VERIFIED 2026-07-03) — rewrite INPUT is `final_content.md`, NOT DB `body`
**The original context below assumed the rewrite reads DB `body`. That premise was FALSED by live Aliyun probe during Wave 1 execution. Planner MUST re-plan Plans 01 + 03 around this correction; Plan 02 is largely unchanged.**

Verified facts (live Aliyun prod `/root/OmniGraph-Vault/data/kol_scan.db`, read-only):
- **DB `body` has ZERO `http://localhost:8765/` URLs** — `articles` 0/467 displayed, `rss_articles` 0/109. `body` carries WeChat CDN (`https://mmbiz.qpic.cn/...` ×310) + data-URIs (×76). The `localhost:8765` localization happens at the filesystem stage (`image_pipeline.py:localize_markdown` → `final_content.md`), NOT in DB `body`.
- **The localhost URLs + the actual displayed content live in `final_content.md`** (8–48 URLs/file sampled). D-14 (`article_query.py:587-619`) resolves fs `final_content.enriched.md` → `final_content.md` → db `body_cleaned` → db `body`; ~70% of displayed articles land on the fs copy, so `body` is NOT what most users see.
- **`final_content.md` is itself DIRTY** — 4/4 sampled carry `javascript:void`/`原创` boilerplate, same marker hits as `body`. It is the "images-localized version of body" — same dirt + real localhost URLs. Readability-upgrade need is REAL, but must clean the fs display content.

Consequences of the old (body-input) plan — BOTH fatal: (1) URL valve is INERT (∅==∅ always passes, main defense never fires on real corpus); (2) image REGRESSION for ~70% (a `body`-derived `body_rewritten` carrying CDN URLs shadows `final_content.md` → `_strip_external_wechat_images` strips them, SSG never converts CDN → images vanish).

**CORRECTED (LOCKED 2026-07-03):** the rewrite INPUT is the **D-14-resolved DISPLAY content** (what `get_article_body()` returns: `final_content.enriched.md` → `final_content.md` → `body_cleaned` → `body`), which for most is `final_content.md` with real `localhost:8765` URLs. Then the valve has real URLs to diff, images survive, and cleaning targets what's actually read. The `body_rewritten` slot + D-14 prepend (migration 009) design is UNCHANGED. Decision A UNAFFECTED (KG ingest reads original `body` independently). Full rationale + Wave-3 `content_hash`-NULL caveat: memory `decision_rewrite_display_only_kg_uses_original.md` "CRITICAL CORRECTION" section.

Wave-1 Task-1 code KEPT (no rework): `lib/rewrite.py` (`rewrite_body_with_deepseek` + `_extract_image_urls` + URL-set diff valve + 7 mocked tests, commits 0565e3e/0bbcc25/45fdc00/2f05622). Only INPUT wiring + validation-harness sample source change.

### Architecture — display/KG separation (Decision A)
- Rewrite output is **DISPLAY-LAYER ONLY**. LightRAG KG entity/relationship extraction ALWAYS runs on the ORIGINAL scraped `body`, never on the rewritten version. The rewrite pass is SEPARATE from ingest/ainsert; it never feeds the graph. Reads on `feedback_lightrag_is_core_asset_no_bypass`.

### Rewrite → translation wiring (Fork X)
- The rewrite emits ONLY the **source-language clean version** into `body_rewritten`.
- The existing translation cron (`scripts/translate_body_cron.py`) is KEPT and reused; it reads `body_rewritten` (falling back to `body` when NULL) and produces clean `body_translated`. Do NOT make the rewrite emit both languages directly (rejected Fork Y).

### No regex / hand-rolled cleaning
- Content cleaning = a SINGLE LLM semantic rewrite pass bearing the FULL cleaning load: strip ads/boilerplate/tracking-JS, reflow paragraphs, fix headings/lists/code-blocks, correct image references. No deterministic regex pre-pass (user vetoed — the existing SSG pipeline is already a fragile ~6-regex pile with documented edge-case bugs, e.g. the apostrophe-failing `Image N from article '([^']*)'`).
- **Rewrite-prompt quality is the single critical path** — there is NO cheap deterministic safety net. This is why Stage 1 Task 1 is prompt design + validation on real dirty samples BEFORE any batch.

### Storage slot (CRITICAL — caught a fatal flaw)
- Rewrite output → NEW `body_rewritten` column (migration 009), added to BOTH `articles` AND `rss_articles` (schema parity), `TEXT NULL`, additive/non-breaking (no DROP, never touches `layer2_verdict`).
- `get_article_body()` D-14 read chain MUST check `body_rewritten` **FIRST — above the filesystem `final_content.enriched.md`/`final_content.md`.**
- **Why not the existing `body_cleaned` column:** live probe (20-article Aliyun sample) found the D-14 precedence is `final_content.enriched.md` (fs) → `final_content.md` (fs) → `body_cleaned` (db) → `body` (db), and **70% of displayed articles have a `final_content.md` on disk** — filling the pre-wired-but-0-row `body_cleaned` would be SILENTLY SHADOWED for the majority and never displayed. `body_cleaned` is NOT usable.

### Image URLs (rewrite-prompt hard constraint)
- Image URLs `http://localhost:8765/{hash}/{name}` MUST be pinned VERBATIM by the rewrite — the LLM may reformat text around them but must NOT alter the URL string. SSG's `_rewrite_image_paths` depends on the exact `http://localhost:8765/` prefix + `![](...)` form. Preserve the appended `Image N from article '{title}': <url>` reference lines' image URLs too (kg_synthesize image correlation depends on them).

### Host
- The rewrite cron runs on **ALIYUN** (co-located with the DB + the translation cron, which is active on Aliyun firing 22:00 CST daily). Text-only via DeepSeek CN egress — no Vertex/embedding, so the #75 egress outage does NOT block it. (Corrects the stale archived Hermes translate unit the map first read.)

### Backfill scope
- **Full backfill of all ~572 displayed articles** (KOL 463 + RSS 109 after DATA-07 filter). Trivial cost at this scale (avg body ~8.6K chars, max ~154K).

### Rewrite model
- One-time 572 backfill: recommend **Opus-tier** (quality-first, one-shot). Steady-state provider for new articles: decide in plan (DeepSeek parity is the likely steady-state given cron host).

### Frontend (Stage 2) — refinement, ui-ux-pro-max
- Use the ui-ux-pro-max skill. Scope: `kb/templates/article.html` + `kb/static/style.css` (2272 lines, existing :root token system). REFINE, don't rebuild.
- Known improvement targets (measured current values):
  - body font-size 16px hardcoded → responsive clamp; mobile line-height 1.8→1.6
  - dark-only, no light mode (whether to add light mode = ui-ux-pro-max design call; give a recommendation)
  - dated Monokai code blocks, inconsistent with inline-code accent-green (#22d3a0)
  - images have no figure/figcaption (content is PRE-RENDERED raw `<img>` — CSS must work with bare img, cannot assume figure wrappers)
  - bland blockquote (bg same as card #1e293b); secondary text contrast only 4.5:1 (AA, not AAA)
  - no back-to-top / TOC anchor nav

### Re-translation of already-translated articles (LOCKED 2026-07-02)
- The ~464 already-translated KOL rows have `body_translated` derived from the DIRTY `body`. **Re-translate ALL of them** so the English side is also clean (fully delivers the "both languages clean" goal).
- Mechanism: after the rewrite backfill populates `body_rewritten`, the translation cron's idempotency guard `WHERE body_translated IS NULL` would SKIP these rows. So the plan MUST, as an explicit ORDERED step AFTER rewrite backfill completes, NULL out `body_translated`/`title_translated` for rows that now have a `body_rewritten`, so the translation cron re-translates from the clean version. Guard the reset so it only touches rows with a populated `body_rewritten` (never blow away a translation for a row we haven't cleaned).
- This makes Stage 1 a THREE-step ordered sequence: (1) rewrite backfill → body_rewritten; (2) reset body_translated for rewritten rows; (3) let/trigger translation cron re-translate from body_rewritten (COALESCE SELECT).

### Image-URL safety valve (LOCKED — from web research, mitigates the no-regex risk)
- Since there is no deterministic safety net, the rewrite pipeline MUST verify per-article: diff the set of `http://localhost:8765/` image URLs in the INPUT body vs the rewrite OUTPUT. If the sets differ (any URL added/dropped/mutated), REJECT that article's rewrite and leave `body_rewritten` NULL (article falls back to `body`, i.e. current behavior — no regression). This per-article valve makes the 572-batch safe and turns the Task-1 validation into an enforceable programmatic check, not eyeballing.

### Claude's Discretion (not covered by locked decisions — plan may choose)
- Exact rewrite prompt wording and few-shot structure (subject to Task-1 validation gate + the URL-set diff check above).
- Checkpoint/stage integration detail for the rewrite cron (idempotency mechanism).
- Batch size + pacing for the backfill.
- Light-mode yes/no and specific CSS token values (ui-ux-pro-max design decision).
- Whether the steady-state (new-article) rewrite is a separate timer or folded into an existing one.
- Chunking strategy for the ~154K-char max-body articles (mirror translate_kb.py's 15KB-threshold split if needed).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (planner, checker, executor) MUST read these before planning/implementing.**

### Locked decisions (READ FIRST)
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/decision_rewrite_display_only_kg_uses_original.md` — all locked architecture decisions + discovered facts + rationale

### Ingestion (root cause + image/URL contract)
- `ingest_wechat.py` — lines 1073-1119 (process_content: HTML→markdown, the zero-cleanup root cause), 1340 (body construction), 1452-1456 (image reference append), 1505-1576 (ainsert — DO NOT touch)
- `image_pipeline.py` — lines 289-303 (localize_markdown: remote→`http://localhost:8765/` local URL substitution)
- `lib/checkpoint.py` — lines 36-56 (stage markers; if adding a rewrite stage it goes AFTER text_ingest, BEFORE sub_doc_ingest)

### Storage schema + read path (the display slot)
- `kb/data/migrations/008_add_body_cleaned_columns.sql` — the pattern for the new 009 migration
- `kb/data/article_query.py` — lines 587-619 (get_article_body D-14 chain — MODIFY to prefer body_rewritten first), 622-653 (pick_translated_body / rewrite_translated_body), 97-131 (ArticleRecord dataclass — add body_rewritten field), 308-333 (list_articles SELECT — add column)
- `tests/integration/kb/conftest.py` — authoritative CREATE TABLE fixtures — MUST add body_rewritten to keep fixtures synced with the migration (mirrors the CLAUDE.md fixture-drift lesson)

### Translation layer (reuse target)
- `scripts/translate_body_cron.py` — the cron to MIRROR for rewrite_body_cron.py (per-row async, idempotent WHERE guard, batch limit, logging)
- `lib/translate.py` — DeepSeek wrapper + Tavily terminology (reuse patterns; do NOT rebuild)

### SSG bake (Stage-2 deploy contract)
- `kb/export_knowledge_base.py` — lines 78 (MD_EXTENSIONS), 304-307 (_render_body_html), 469-561 (render_article_detail), 735-745 (copy_static_assets)
- `kb/scripts/daily_rebuild.sh` — the 5-phase bake; Stage-2 deploy must run the FULL pipeline (Principle #9)
- `kb/templates/article.html` + `kb/static/style.css` — Stage-2 refinement targets

### Frontend design skill
- ui-ux-pro-max skill (invoke for Stage 2 design decisions)
</canonical_refs>

<success_criteria>
## Verifiable Success Gates (Principle #4 — no subjective language)

### Stage 1 — content rewrite
- **PROMPT VALIDATION GATE (blocks batch):** rewrite prompt run on 5-10 real dirty WeChat samples; for EACH sample:
  - Every `http://localhost:8765/{hash}/{name}` image URL present in the input appears BYTE-IDENTICAL in the output (0 mangled URLs) — grep-diff the URL set.
  - No ad/boilerplate/tracking markers remain (define a checklist: `关注公众号`, `点赞`, `扫码`, subscription CTAs, nav residue).
  - No raw HTML tags leak into the markdown output (`grep -c '<script\|<style\|<div' == 0`).
  - Output passes markdownlint with 0 errors.
  - Output length ≥ 20% of original (guards against over-deletion tripping MIN_INGEST_BODY_LEN=500).
- **Schema:** `migration 009` adds `body_rewritten TEXT` to `articles` AND `rss_articles`; `conftest.py` fixtures updated to match; `pytest tests/integration/kb/` green.
- **Read path:** `get_article_body()` returns `body_rewritten` when non-NULL, ABOVE filesystem sources — provable by a test that seeds body_rewritten + a final_content.md and asserts body_rewritten wins.
- **Cron:** `rewrite_body_cron.py` is idempotent (`WHERE body_rewritten IS NULL`), has a batch limit, mirrors translate_body_cron structure; a dry-run lists candidates without error.
- **Backfill:** all ~572 displayed articles have non-NULL `body_rewritten` after backfill (SQL count == displayed count); translation cron subsequently reads body_rewritten (verify a spot-checked row's body_translated derives from the clean version).

### Stage 2 — frontend (only after Stage 1 clean data exists)
- ui-ux-pro-max refinement applied to article.html + style.css; D-12 token NAMES preserved (grep), 760px measure preserved, i18n `[data-lang]` + lang.js intact, sticky sidebar + motion tokens + reduced-motion preserved.
- **Principle #6 (mandatory):** `local_serve.py` + browser UAT on ≥3 REWRITTEN (clean) articles at desktop/tablet/mobile; screenshots to `.playwright-mcp/kb-v2.3-uat-*.png`; cited in VERIFICATION.md with curl smoke of `/api/article/{hash}` showing the clean body.
- **Principle #9 (mandatory):** final deploy runs the FULL Makefile / daily_rebuild.sh (Pass 0 SSG bake onward), NOT sync-only, because kb/static + kb/templates are touched.
</success_criteria>

<specifics>
## Concrete facts from the 2026-07-02 map (use verbatim)

- Real displayed corpus: **KOL 463 + RSS 109 = 572** (DATA-07 filter: `layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL AND body != ''`). NOT the 2044 scan pool.
- Translation state: 464 KOL translated / 27 not; 121 RSS translated. Translation is ~94% covered and AUTO-RUNNING on Aliyun (supersedes stale `aliyun_translate_pipeline_not_automated`).
- `body_cleaned` column: EXISTS (migration 008) but 0-populated; shadowed by filesystem sources — hence the new `body_rewritten` slot.
- D-14 read precedence (measured): `final_content.enriched.md` → `final_content.md` → `body_cleaned` → `body`. 14/20 sample had `final_content.md`, 6/20 reached DB.
- avg body 8599 chars, max 154372 chars (chunking may be needed for the largest, mirror translate_kb.py's 15KB threshold approach if so).
- Render stack: python-markdown (NOT markdown2/mistune), `MD_EXTENSIONS = [fenced_code, codehilite, tables, toc, nl2br]`.
- image URL rewrite at SSG: `http://localhost:8765/{X}` → `{KB_BASE_PATH}/static/img/{X}`.
- Current CSS values: font body Inter+Noto Sans SC 16px fixed; article line-height 1.8; measure 760px; bg #0f172a; text-primary #f0f4f8; text-secondary #94a3b8 (4.5:1); accent-blue #3b82f6; accent-green #22d3a0; container 1200px; breakpoints 480/640/768/1024/1200.
</specifics>

<deferred>
## Deferred Ideas
- Steady-state (new-article incremental) rewrite automation beyond the backfill — wire the cron timer, but ongoing tuning is post-phase.
- Deleting now-moot SSG regex transforms — explicitly NOT in scope (Surgical Changes); revisit only if a future cleanup quick targets it.
- Light mode — plan may include or defer per ui-ux-pro-max recommendation.
</deferred>

---

*Phase: kb-v2.3-readability-upgrade*
*Context gathered: 2026-07-02 from locked-decision brief + 5-subsystem map (wf_7c9b1788-287)*
