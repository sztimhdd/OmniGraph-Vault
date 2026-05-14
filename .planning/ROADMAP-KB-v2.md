# Roadmap: KB-v2 (Bilingual Agent-Tech Content Site)

**Milestone:** KB-v2 (parallel-track to v3.4 / v3.5 / Agentic-RAG-v1)
**Created:** 2026-05-12
**Phase prefix:** `kb-N-*` (sibling to `ar-N-*`; main project uses 19-22)
**Granularity:** Standard (4 phases — kb-1, kb-2, kb-3, kb-4) — **revised 2026-05-13:** kb-2 (Topic Pillar + Entity pages + cross-link) un-skipped after Hermes prod data verification
**Coverage:** 62/62 v2.0 REQs mapped, no orphans, no duplicates

> **Locked design:** `kb/docs/01-PRD.md` (§4 SEO 章节作废), `kb/docs/02-DECISIONS.md`,
> `kb/docs/03-ARCHITECTURE.md`, `kb/docs/09-AGENT-QA-HANDBOOK.md`.
> **Cross-milestone contracts:** C1 `kg_synthesize.synthesize_response()`, C2
> `omnigraph_search.query.search()`, C3 `kol_scan.db` schema (additive only),
> C4 `images/{hash}/final_content.md` path. **Read-only**, do NOT break.

> **Note on REQ count history:**
> - 2026-05-12 initial roadmap mapped 50 REQs across 9 categories.
> - 2026-05-13 kb-2 revival added 12 REQs across 3 new categories (TOPIC 5 + ENTITY 4 + LINK 3) → **62 REQs total across 12 categories**.
> - kb-2 was originally "explicitly skipped" based on local dev DB data (0 classifications, 13 canonical entities). Hermes prod data (3945 classifications, 5257 extracted_entities, 91 entities at ≥5-article freq) supports kb-2 implementation today. Three v2.1 dependencies — LLM canonicalization (CANON-*), entity_type fill (TYPED-*), topic taxonomy hierarchy (TOPIC-HIER-*) — are explicitly deferred and won't block this milestone.

---

## Phase decomposition rationale

**Decomposition style chosen: layered foundation → service → ops.**

The KB-v2 architecture is a classic 3-tier static-then-dynamic web app:

1. **kb-1** produces the SSG output and the data layer that any consumer (SSG export
   OR FastAPI runtime) depends on. The export step is read-only against SQLite +
   filesystem, so it surfaces every data-shape question (lang detection, content_hash
   resolution, body fallback chain) before any HTTP code lands. Without lang columns
   populated and content_hash resolution working, neither the API nor deploy is
   testable.
2. **kb-3** wraps that data layer in FastAPI, adds FTS5 + KG search modes, and wraps
   `kg_synthesize.synthesize_response()` with the language-directive injection. By
   the time kb-3 starts, all data-shape risk is gone — kb-3 only adds HTTP semantics,
   async job stores, and timeout/fallback behavior on top of an already-working data
   layer.
3. **kb-4** is pure ops: systemd, Caddy, install script, daily cron, smoke. No new
   functional code; only deploy artifacts and verification.

**Counter-rationale considered (vertical-slice MVP-first à la Agentic-RAG-v1):**
rejected because the KB-v2 surface area is ~3× larger (50 REQs vs 41) and the
data-shape risks (`lang IS NULL` rows blocking filters, RSS-vs-KOL hash format
divergence, body fallback chain D-14 not landing on disk) are concentrated in the
data layer. A vertical slice would force kb-1 to ship a thin column of every
capability, then kb-2 / kb-3 to retroactively backfill — which buys nothing here
because the SSG export is already the natural "thin slice" (it exercises the full
data layer end-to-end on a static target). Layered decomposition is strictly
simpler given this risk profile.

**Phase count: 4** — kb-1 → kb-2 → kb-3 → kb-4. The numbering preserves cross-reference compatibility with `kb/docs/04-KB1` / `05-KB2-ENTITY-SEO.md` / `06-KB3` / `07-KB4` execution specs (kb-2 doc was authored 2026-05-12 anticipating this phase).

**kb-2 placement rationale (after kb-1, before kb-3):** kb-2 is pure SSG (Jinja2 templates + data layer queries against existing tables — `classifications`, `extracted_entities` — plus extensions to kb-1's `article_query.py`). It produces topic + entity HTML pages that kb-3 then mounts via FastAPI and kb-4 deploys. kb-2 inherits the kb-1 redesigned UI tokens (chips, glow, icons, state classes from `kb-1-UI-SPEC.md`) — it does NOT re-design components.

**Original 2026-05-12 reasoning that turned out to be wrong:** "only 13 canonical entities exist today, can't support a real entity-page surface" was true for the local dev DB (which had 0 classifications and 13 manually-seeded canonical entities). Hermes prod has 5 classified topics × 789 articles + 91 entities at ≥5-article frequency — entirely sufficient for v2.0 scope. The lesson: **always verify against production data before deferring scope** (now captured in `feedback_parallel_track_gates_manual_run.md` memory).

---

## Phases

- [x] **Phase kb-1: SSG Export + i18n Foundation** — Completed 2026-05-13. Bilingual data layer, content_hash runtime resolution, Jinja2 SSG templates, sitemap/robots/og/JSON-LD baseline. The full read path goes from `kol_scan.db` to static HTML. (26/27 REQs satisfied; UI-04 placeholder accepted, real PNG carried to kb-4. 4 human-verifiable browser UAT items in kb-1-HUMAN-UAT.md. UI redesign in progress 2026-05-13 to close design-dimension audit findings — `kb-1-DESIGN-AUDIT.md`.)
- [x] **Phase kb-2: Topic Pillar + Entity Pages + Cross-Link Network** — Completed 2026-05-13. Generates `/topics/{slug}.html` × 5 (Agent / CV / LLM / NLP / RAG) + `/entities/{slug}.html` × ~91 (entities ≥5 articles, 6 in fixture) + JSON-LD CollectionPage / Thing. Article detail page gains related-entities + related-topics sidebar. Homepage adds "Browse by Topic" + "Featured Entities" sections. Inherits kb-1 redesigned UI tokens — no re-design. (12/12 REQs satisfied; full Skill discipline regex passes; 58 integration tests covering 37 UI-SPEC §8 acceptance grep patterns; 12/12 Playwright UAT viewports zero horizontal scroll.)
- [ ] **Phase kb-3: FastAPI Backend + Bilingual API + Search + Q&A** — `/api/articles` / `/api/article/{hash}` / `/api/search` (FTS5 + KG mode) / `/api/synthesize` (async + lang directive + FTS5 fallback) / `/static/img` mount.
- [ ] **Phase kb-4: Ubuntu Deploy + Cron + Smoke Verification** — systemd unit + Caddy snippet + `install.sh` + `daily_rebuild.sh` cron + 3 smoke scenarios pass.

---

## Phase Details

### Phase kb-1: SSG Export + i18n Foundation
**Goal:** Bilingual SSG output renders from a clean `kol_scan.db`-plus-filesystem data
layer. Article list, article detail, and Q&A entry pages are produced as static HTML
with full UI i18n, badge-correct content language, image URL rewriting, and SEO/share
courtesy tags.
**Depends on:** Nothing (first phase).
**Requirements:** I18N-01, I18N-02, I18N-03, I18N-04, I18N-05, I18N-06, I18N-08,
DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, EXPORT-01, EXPORT-02,
EXPORT-03, EXPORT-04, EXPORT-05, EXPORT-06, UI-01, UI-02, UI-03, UI-04, UI-05,
UI-06, UI-07, CONFIG-01 (27 REQs)
**Success Criteria** (what must be TRUE):
  1. `kb/scripts/detect_article_lang.py` runs on the live `kol_scan.db` and reports
     `articles.lang` + `rss_articles.lang` 100% non-NULL afterward (DATA-01..03);
     re-running is a no-op (idempotent).
  2. `python kb/export_knowledge_base.py` produces `kb/output/index.html`,
     `kb/output/articles/{hash}.html` for every passable KOL + RSS row, and
     `kb/output/ask/index.html` (EXPORT-01..03). The build completes without
     writing to SQLite or to `images/` (EXPORT-02).
  3. Opening a generated article detail HTML in a browser shows: correct
     `<html lang="zh-CN">` or `<html lang="en">` matching content (I18N-05);
     visible "中文" / "English" content-language badge (I18N-06); rendered
     markdown body with Pygments code highlighting (EXPORT-04); all
     `localhost:8765/` URLs rewritten to `/static/img/` (EXPORT-05); breadcrumb
     "Home > Articles > [Title]" with localized labels (UI-07).
  4. Loading any generated page with `?lang=en` switches all UI chrome strings
     to English; reloading without the param keeps English via `kb_lang` cookie
     (I18N-02, I18N-03, I18N-08). The `Accept-Language` detection produces
     `zh-CN` as default fallback when neither `zh` nor `en` is acceptable (I18N-01).
     Article list filter `?lang=en` returns only English articles (I18N-04).
  5. `kb/output/sitemap.xml` lists every article URL + homepage with `<lastmod>`;
     `kb/output/robots.txt` allows all with `Sitemap: /sitemap.xml` (EXPORT-06).
     Article detail pages carry `og:title`, `og:description`, `og:image`,
     `og:type`, `og:locale` matching `<html lang>` (UI-05) and JSON-LD `Article`
     schema with `inLanguage` (UI-06).
  6. Mobile (320-767px) and desktop (1024px+) viewports render without horizontal
     scroll on home / list / detail / Q&A entry pages (UI-03); design tokens
     (`--bg`, `--text`, `--accent`, etc.) and font stack (`Inter`, `Noto Sans SC`)
     load from a single `kb/static/style.css` with no external font requests on
     first paint (UI-01, UI-02). Logo + favicon reused from vitaclaw-site (UI-04).
  7. `kb/data/article_query.list_articles(lang, source, limit, offset)` returns
     paginated `ArticleRecord` lists sorted by `update_time DESC` (DATA-04);
     `get_article_by_hash(hash)` resolves md5[:10] across both KOL and RSS tables
     (DATA-05). content_hash resolution works for KOL rows with NULL content_hash
     (runtime md5[:10] from body), KOL rows with content_hash set (used directly),
     and RSS rows (truncate full md5 to 10 chars) — all without DB writes
     (DATA-06).
  8. `kb/config.py` reads `KB_DB_PATH`, `KB_IMAGES_DIR`, `KB_OUTPUT_DIR`, `KB_PORT`,
     `KB_DEFAULT_LANG`, `KB_SYNTHESIZE_TIMEOUT` from env with documented defaults;
     no path is hardcoded outside config.py (CONFIG-01).
**Plans:** 10 plans across 5 waves (kb-1-10 gap-closure added 2026-05-13 by gsd-phase-planner)
- [x] kb-1-01-config-skeleton-PLAN.md — kb/ package skeleton + env-driven kb/config.py (Wave 1)
- [x] kb-1-02-migration-lang-detect-PLAN.md — DATA-01 migration + lang_detect helper (Wave 1)
- [x] kb-1-03-i18n-locale-PLAN.md — zh-CN.json + en.json + Jinja2 t() filter (Wave 1)
- [x] kb-1-04-static-css-js-PLAN.md — style.css + lang.js (Wave 1)
- [x] kb-1-04b-brand-assets-checkpoint-PLAN.md — favicon.svg placeholder + VitaClaw-Logo-v0.png.MISSING.txt + provenance README (Wave 1, approved-placeholder)
- [x] kb-1-05-detect-script-driver-PLAN.md — detect_article_lang.py CLI driver (Wave 2)
- [x] kb-1-06-article-query-PLAN.md — DATA-04..06 read-only query layer (Wave 2)
- [x] kb-1-07-base-template-pages-PLAN.md — base.html + index/articles_index/ask templates (Wave 3)
- [x] kb-1-08-article-detail-template-PLAN.md — article.html with content lang + JSON-LD (Wave 4)
- [x] kb-1-09-export-driver-PLAN.md — export_knowledge_base.py SSG entry + integration test (Wave 5)
- [x] kb-1-10-gap-time-normalization-PLAN.md — gap-closure: KOL update_time epoch INT->ISO normalization + _ensure_lang_column defensive guard (Wave 1 of gap-closure, shipped 2026-05-13)
**UI hint:** yes
**Notes:**
- I18N-04 lives in kb-1 because the filter capability is grounded in `DATA-04`
  (`list_articles(lang=None, ...)`); the FastAPI endpoint API-02 in kb-3 reuses the
  same query function. This is a "first-delivered-here, touched-again-in-kb-3"
  pattern — do not re-map the REQ.
- I18N-07 (Q&A lang directive) is intentionally NOT in kb-1; it belongs to kb-3
  with the rest of the synthesize wrapper (QA-01..05).
- DATA-01 schema migration is **schema-extending non-breaking** per C3 contract —
  adding nullable `lang TEXT` column does not require a `BREAKING:` commit tag.
- The `?lang=` semantics are dual-purpose by design: when used as a UI chrome
  switch (I18N-02, applies to all pages) and when used as a content-language
  filter on list endpoints (I18N-04, applies only to list views). UI implementation
  must distinguish these. Document both code paths in the implementation plan.
- vitaclaw-site brand assets (`VitaClaw-Logo-v0.png`, `favicon.svg`, `#0f172a`
  暗色 palette) are reused as-is per UI-04 — no new design files in this milestone.

---

### Phase kb-2: Topic Pillar + Entity Pages + Cross-Link Network
**Goal:** Generate topic pillar pages (`/topics/{slug}.html` × 5) and entity pages (`/entities/{slug}.html` × ~91) with cross-linking from article details. Homepage gains topic + entity discovery sections. Pure SSG (Jinja2 + data layer extensions); no HTTP, no new LLM calls. Inherits kb-1 redesigned UI tokens.
**Depends on:** Phase kb-1 (article_query.py + kb-1-UI-SPEC.md tokens for chips/glow/icons/state-classes; templates `base.html` + `article.html` to extend; export driver to extend).
**Requirements:** TOPIC-01..05, ENTITY-01..04, LINK-01..03 (12 REQs)
**Success Criteria** (what must be TRUE):
  1. `python kb/export_knowledge_base.py` against Hermes-prod-shape DB produces:
     - `kb/output/topics/agent.html`, `cv.html`, `llm.html`, `nlp.html`, `rag.html` (5 files)
     - `kb/output/entities/<slug>.html` for ~91 entities (verified by `ls kb/output/entities/*.html | wc -l ≥ 50` against threshold KB_ENTITY_MIN_FREQ=5)
  2. Each topic page header shows localized name + description + accurate article count; lists articles where `classifications.depth_score >= 2 AND (layer1='candidate' OR layer2='ok')`, sorted by `update_time DESC`. UNION over KOL + RSS articles.
  3. Each topic page sidebar lists 5 co-occurring entities (top by article frequency in this topic's article set), each linking to `/entities/{slug}.html`.
  4. Each entity page lists all articles mentioning that entity, reusing kb-1 redesigned `.article-card` (no re-design). Header shows entity name + article count + lang distribution chip row.
  5. Article detail page (`kb/templates/article.html`) gains a related-entities chip row (3-5 entities) + related-topics chip row (1-3 topics), wired through render context from export driver.
  6. Homepage gains 2 new sections between "Latest Articles" and "Try AI Q&A": "🗂 Browse by Topic" (5 topic chip cards) + "💡 Featured Entities" (top 12 entities).
  7. `kb/output/sitemap.xml` includes all topic + entity URLs (recursive `Path.rglob("*")` — auto-handles new pages).
  8. Topic pages emit JSON-LD `CollectionPage` schema; entity pages emit JSON-LD `Thing` schema (generic `@type`, `entity_type` typing deferred to v2.1 CANON-* / TYPED-* per REQUIREMENTS).
**Plans:** 10 plans across 5 waves (planned 2026-05-13)
- kb-2-01-fixture-extension — test fixture: classifications + extracted_entities tables (Wave 1)
- kb-2-02-locale-keys — 28 new keys in zh-CN.json + en.json per UI-SPEC §5 (Wave 1)
- kb-2-03-svg-icons — 2 new icons (folder-tag + users) per UI-SPEC §3.5 (Wave 1)
- kb-2-04-query-functions — 5 new functions in kb/data/article_query.py + TDD (Wave 2)
- kb-2-05-topic-template — NEW kb/templates/topic.html per UI-SPEC §3.1 (Wave 3)
- kb-2-06-entity-template — NEW kb/templates/entity.html per UI-SPEC §3.2 (Wave 3)
- kb-2-07-homepage-extension — EXTEND kb/templates/index.html with 2 sections per UI-SPEC §3.3 (Wave 3)
- kb-2-08-article-aside — EXTEND kb/templates/article.html with related-link rows per UI-SPEC §3.4 (Wave 3)
- kb-2-09-export-driver-extension — EXTEND kb/export_knowledge_base.py with topic + entity loops + render context (Wave 4)
- kb-2-10-integration-test — Full SSG pipeline integration test + UI-SPEC §8 grep regression (Wave 5)
**UI hint:** **yes** — kb-2 ships new page types (topic, entity) with new component requirements (chip cards on homepage, sidebar layouts, related-link rows). Even though tokens are inherited from kb-1, the layouts are new.
**Required Skills (HARD — see kb/docs/10-DESIGN-DISCIPLINE.md):**
- `Skill(skill="ui-ux-pro-max", ...)` — at plan time, design (a) topic pillar page layout (header + article list + sidebar with co-occurring entities), (b) entity page layout (header with lang distribution + article list), (c) homepage chip-card patterns for topics + entity cloud, (d) related-link sidebar/footer pattern for article detail. Output → `kb-2-UI-SPEC.md`. MUST reference kb-1-UI-SPEC.md and reuse its chip/glow/icon/state tokens.
- `Skill(skill="frontend-design", ...)` — at plan time, implement spec into 2 new templates (`topic.html`, `entity.html`) + extend `index.html` (add 2 sections) + extend `article.html` (related sidebar). Reuse kb-1 redesigned tokens — do NOT re-design.
- `Skill(skill="python-patterns", ...)` — at code time, idiomatic data layer extensions: `topic_articles_query(topic, depth_min)`, `entity_articles_query(entity_name, min_freq)`, `related_entities_for_article(article_id)`, `related_topics_for_article(article_id)`, `cooccurring_entities_in_topic(topic)`. All read-only, follow kb-1's `article_query.py` conventions.
- `Skill(skill="writing-tests", ...)` — at test time, TDD for new query functions (table-driven against fixture mirroring Hermes-prod schema with classifications + extracted_entities) + integration test for export driver topic/entity rendering.
**Pre-execution gate:** `kb-2-UI-SPEC.md` MUST exist before any code task. `kb-1-UI-SPEC.md` (from kb-1 redesign) MUST be in `<read_first>` of every UI-touching task — kb-2 reuses kb-1 chip / glow / icon / state classes verbatim. `tests/integration/kb/test_export.py` fixture MUST add `classifications` + `extracted_entities` table data (mirroring Hermes prod shape) BEFORE testing — local dev DB has 0 classifications, can't be used as ground truth.
**Notes:**
- TOPIC-02 cohort filter `depth_score >= 2 AND (layer1='candidate' OR layer2='ok')` is the right balance: depth >= 3 alone is only 19-38 per topic (too sparse), depth >= 2 alone is 650-720 per topic (too noisy — multi-topic LLM gives every article depth=2 for everything). The Layer 1/2 quality gate prunes the noise.
- ENTITY-01 threshold `>= 5 articles` produces ~91 entity pages on Hermes prod (verified 2026-05-13). Lower threshold (>= 3) yields ~198 entities but quality drops; higher (>= 10) yields 26 — sparse. v2.0 picks 5 as the sweet spot, env-overridable via `KB_ENTITY_MIN_FREQ`.
- ENTITY-04 emits `@type: Thing` (generic) rather than `Person/Organization/SoftwareApplication` because `entity_canonical.entity_type` is NULL across the corpus. v2.1 CANON-* + TYPED-* will populate this.
- Cross-link discovery (LINK-01, LINK-02) is computed by the export driver at build time, not at request time — render context for `article.html` includes pre-computed `related_entities[]` and `related_topics[]` lists.
- LINK-03 homepage chip cards reuse kb-1 redesigned `.article-card` styling (rounded-2xl, hover glow, etc.) — do NOT introduce a new card variant unless ui-ux-pro-max recommends one.
- **Verification regex (run before declaring kb-2 complete):**
  `grep "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-2-*/*-SUMMARY.md` — must return ≥1 match. Same for `frontend-design`. Zero matches = phase NOT complete regardless of REQ checkboxes.

---

### Phase kb-3: FastAPI Backend + Bilingual API + Search + Q&A
**Goal:** A single FastAPI app on port 8766 exposes the KB data layer over HTTP,
runs FTS5 trigram search across both languages, and serves bilingual RAG Q&A via
async wrapping of `kg_synthesize.synthesize_response()` with KB-side language
directive injection and never-500 fallback to FTS5 top-3.
**Depends on:** Phase kb-1 (needs `kb.config`, `kb.data.article_query`,
populated `lang` columns, runtime content_hash resolution, and SSG output that the
FastAPI app reads `final_content.md` from per D-14).
**Requirements:** DATA-07, I18N-07, API-01, API-02, API-03, API-04, API-05, API-06,
API-07, API-08, SEARCH-01, SEARCH-02, SEARCH-03, QA-01, QA-02, QA-03, QA-04, QA-05,
CONFIG-02 (19 REQs — DATA-07 added 2026-05-13: content-quality filter, see
`.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md`)
**Success Criteria** (what must be TRUE):
  1. `uvicorn kb.api:app --port 8766` boots and serves all endpoints listed below;
     port is overridable via `KB_PORT` env (API-01). `app.mount("/static/img", ...)`
     replaces the standalone `:8765` image server — fetching
     `/static/img/{hash}/<file>` returns the same bytes as the legacy server (API-08).
  2. `GET /api/articles?page=1&limit=20&source=&lang=&q=` returns paginated JSON
     from `list_articles()`; P50 latency < 100ms on the live `kol_scan.db` (API-02).
     `GET /api/article/{hash}` resolves md5[:10] for both KOL and RSS rows and
     returns `{hash, title, body_md, body_html, lang, source, images, metadata,
     body_source}` with `body_source` = `"vision_enriched"` when
     `final_content.enriched.md` or `final_content.md` exists, else
     `"raw_markdown"` (API-03, D-14 fallback chain). Unknown hash → 404.
  3. `GET /api/search?q=&mode=fts&lang=&limit=20` runs the FTS5 trigram query and
     returns hits with `snippet()` highlighting trimmed to 200 chars; lang filter
     excludes non-matching rows (API-04, SEARCH-01, SEARCH-03). P50 latency < 100ms
     on the populated index. `kb/scripts/rebuild_fts.py` performs full index
     rebuild against `articles_fts` (UNION of KOL + RSS) in < 5 seconds and is
     called by daily cron (SEARCH-02).
  4. `GET /api/search?q=&mode=kg&lang=` returns 202 + `job_id`; the job calls
     `omnigraph_search.query.search()` async (C2 preserved); `GET /api/search/{job_id}`
     polls and returns the result when ready (API-05).
  5. `POST /api/synthesize` with `{question, lang}` returns 202 + `job_id`. The
     KB layer prepends `"请用中文回答。\n\n"` (lang=zh) or `"Please answer in
     English.\n\n"` (lang=en) to the question and calls
     `kg_synthesize.synthesize_response()` in BackgroundTasks (I18N-07, QA-01,
     QA-02, API-06). **Function signature unchanged** (C1 preserved). Single uvicorn
     worker; in-memory `job_id → state` store (QA-03). `GET /api/synthesize/{job_id}`
     returns `{status, result?, fallback_used, confidence}` (API-07).
  6. On synthesize timeout (default 60s, override via `KB_SYNTHESIZE_TIMEOUT`) or
     LightRAG failure, the wrapper triggers FTS5-fallback: top-3 articles matching
     the question, `(title + 200-char snippet)` concatenated as markdown; job
     status becomes `done` with `fallback_used: true` and
     `confidence: "fts5_fallback"`. Synthesize **never returns 500** (QA-04, QA-05).
  7. `kb/services/synthesize.py` (the wrapper) imports `kg_synthesize` directly
     and `lib.llm_complete.get_llm_func()` honors `OMNIGRAPH_LLM_PROVIDER` —
     the KB layer adds zero new LLM provider env vars (CONFIG-02).
  8. **Content-quality filter (DATA-07)** applies to ALL list-style query
     functions in `kb/data/article_query.py` — `list_articles()`,
     `topic_articles_query()`, `entity_articles_query()`,
     `cooccurring_entities_in_topic()`, `related_entities_for_article()`,
     `related_topics_for_article()`. Filter excludes rows where
     `body IS NULL OR body = ''` OR `layer1_verdict != 'candidate'` OR
     `layer2_verdict = 'reject'`. Symmetric across KOL `articles` and RSS
     `rss_articles` (both have all 3 columns since v3.5 ir-4). Single-article
     hash lookup `get_article_by_hash()` is NOT filtered (direct URL access
     remains intact for search hits / KG synthesize sources / bookmarks).
     Env override `KB_CONTENT_QUALITY_FILTER=off` for debug; default `on`.
     Expected visibility on Hermes prod: ~6% of scanned rows (~160/2501).
     Cross-phase impact: kb-1 list page + kb-2 topic/entity pages inherit
     automatically on next SSG re-render (no template changes needed).
     See `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md`
     for SQL clauses, fixture coordination, and rollout plan.
**Plans:** 12 plans across 5 waves (planned 2026-05-13 by gsd-planner)
- [ ] kb-3-01-api-contract-PLAN.md — REST API contract lock (api-design Skill); kb-3-API-CONTRACT.md
- [ ] kb-3-02-data07-filter-PLAN.md — DATA-07 content-quality filter on 6 list-style query functions; carve-out for get_article_by_hash
- [ ] kb-3-03-locale-icons-PLAN.md — 20 new locale keys + chat-bubble-question + lightning-bolt icons (foundation for kb-3-10/11)
- [ ] kb-3-04-fastapi-skeleton-PLAN.md — kb/api.py FastAPI app + /health + /static/img mount (D-15)
- [x] kb-3-05-articles-endpoints-PLAN.md — GET /api/articles + GET /api/article/{hash} (DATA-07 + carve-out) — completed 2026-05-14
- [ ] kb-3-06-search-endpoint-PLAN.md — GET /api/search (FTS5 sync + KG async via job_store)
- [ ] kb-3-07-rebuild-fts-script-PLAN.md — kb/scripts/rebuild_fts.py CLI (cron-invoked daily)
- [x] kb-3-08-synthesize-wrapper-PLAN.md — kb/services/synthesize.py + POST /api/synthesize + GET /api/synthesize/{job_id} (C1 unchanged) — completed 2026-05-14
- [ ] kb-3-09-fts5-fallback-PLAN.md — kb_synthesize timeout + exception → FTS5 top-3 fallback (NEVER 500)
- [ ] kb-3-10-qa-state-matrix-ui-PLAN.md — _qa_result.html partial + qa.js state machine (8 states; ui-ux-pro-max + frontend-design Skills)
- [ ] kb-3-11-search-inline-reveal-PLAN.md — additive search.js on homepage + list page (no /search page; ui-ux-pro-max + frontend-design Skills)
- [ ] kb-3-12-full-integration-test-PLAN.md — end-to-end + UI-SPEC §8 + DATA-07 acceptance + Skill discipline + REQ coverage regression
**UI hint:** **yes** (revised 2026-05-13 per kb-1-DESIGN-AUDIT.md — ask.html result region is a non-trivial UI surface, even though most of kb-3 is backend)
**Required Skills (HARD — see kb/docs/10-DESIGN-DISCIPLINE.md):**
- `Skill(skill="ui-ux-pro-max", ...)` — at plan time, design Q&A result component (markdown render container + source-article chip row + entity chip row + feedback +/- buttons + state matrix: loading/streaming/done/error/timeout/fallback). Output → `kb-3-UI-SPEC.md`.
- `Skill(skill="frontend-design", ...)` — at plan time, implement the spec into `kb/templates/ask.html` result region + `kb/static/qa.js` (or extend lang.js). Reuse kb-1 redesign tokens (chips, glow, icons, state classes) — do NOT re-design.
- `Skill(skill="api-design", ...)` — at plan time, lock REST contract for /api/articles, /api/article/{hash}, /api/search, /api/synthesize before implementation.
- `Skill(skill="python-patterns", ...)` — at code time, FastAPI dependency injection, BackgroundTasks, async/sqlite patterns.
- `Skill(skill="writing-tests", ...)` — at test time, Testing Trophy: integration tests against real SQLite + LightRAG, unit tests only for pure helpers.
**Pre-execution gate:** `kb-3-UI-SPEC.md` MUST exist before any code task. `kb-1-UI-SPEC.md` (from kb-1 redesign) MUST be in `<read_first>` of every UI-touching task — kb-3 inherits the locked design language, does not re-design.
**Notes:**
- I18N-07 lives in kb-3 (not kb-1) because it is a Q&A-endpoint behavior, not a
  UI chrome rule. The directive is injected at the wrapper layer, not at the
  template layer.
- API-05 (KG-mode search) and API-06 (synthesize) both use BackgroundTasks +
  in-memory job stores. The two stores can share a single dict-backed registry
  module — but plan to keep them logically separate so v2.1 multi-worker SQLite
  backing can replace one at a time.
- CONFIG-02 is a "non-action" requirement (we explicitly add no new LLM env
  vars). Verification is by grep — `grep -r "os.environ" kb/services/ kb/api.py |
  grep -i "llm\|deepseek\|gemini" | grep -v lib/llm_complete` should be empty.
- Caddy is **not** configured in kb-3; that's kb-4. Until kb-4, all access is
  direct via `localhost:8766`.
- **Verification regex (run before declaring kb-3 complete):**
  `grep "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-3-*/*-SUMMARY.md` — must return ≥1 match. Same for `frontend-design` / `api-design`. Zero matches = phase NOT complete regardless of REQ checkboxes.

---

### Phase kb-4: Ubuntu Deploy + Cron + Smoke Verification
**Goal:** A clean Ubuntu host runs `install.sh`, gets the systemd unit + Caddy
snippet active, daily cron rebuilds SSG + FTS5, and the 3 smoke-test scenarios
defined in PROJECT-KB-v2.md all PASS.
**Depends on:** Phase kb-3 (smoke #2 and #3 require the FastAPI + synthesize +
fallback all working; smoke #1 requires kb-1's i18n).
**Requirements:** DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05 (5 REQs)
**Success Criteria** (what must be TRUE):
  1. `kb/deploy/install.sh` is idempotent: re-running on an installed host produces
     no errors and leaves `systemctl is-active kb-api.service` = `active`;
     `journalctl -u kb-api --since '5 minutes ago'` shows zero ERROR lines
     (DEPLOY-01, DEPLOY-03). The systemd unit runs `uvicorn kb.api:app --host
     127.0.0.1 --port 8766 --workers 1` with `Restart=always` and the documented
     `Environment=PYTHONPATH` (DEPLOY-01).
  2. Caddy reload (after appending `kb/deploy/Caddyfile.snippet`) routes
     `/static/img/*` and `/api/*` to `localhost:8766` while serving everything
     else from `kb/output/` directly (DEPLOY-02). `curl -I` against any
     `kb/output/articles/{hash}.html` returns 200 from Caddy without hitting
     uvicorn.
  3. `kb/scripts/daily_rebuild.sh` runs the sequence
     `detect_article_lang.py → export_knowledge_base.py → rebuild_fts.py` end-to-end,
     logs to `/var/log/kb-rebuild.log`, and exits 0. Cron entry fires at 12:00
     server-local daily; manual invocation produces a fresh `kb/output/` tree and
     a freshly-rebuilt FTS5 index in < 1 minute on the production data scale
     (DEPLOY-04).
  4. Same-host deploy (KB on the box where `~/.hermes/omonigraph-vault/` lives)
     works with **only the documented env vars set** — no NFS / bind-mount /
     external sync needed (DEPLOY-05). Different-host deploy paths are not
     blocked architecturally (paths are env-driven per CONFIG-01) but are not
     verified in this milestone.
  5. **All 3 smoke scenarios in PROJECT-KB-v2.md PASS** (the milestone gate):
     - Smoke 1 (双语 UI 切换): Accept-Language 探测 + cookie 持久化 + `?lang=`
       硬切 — all 4 sub-steps PASS.
     - Smoke 2 (双语搜索 + 详情页): 中文 query 返回 ≥3 中文文章 + 英文 query
       返回 ≥3 英文文章 + 详情页 `<html lang>` + badge + og:image/og:title
       正确 — all 5 sub-steps PASS.
     - Smoke 3 (RAG 问答双语 + 失败降级): 中英 query 各返回正确语言答复 + 模拟
       LightRAG 不可用时 fallback 返回 FTS5 top-3 摘要 + `confidence:
       "fts5_fallback"`,**not 500** — all 3 sub-steps PASS.
  6. Lighthouse on a representative article detail page reports `LCP < 2.5s` and
     `CLS < 0.1` (PROJECT-KB-v2.md "Pass conditions" §3); `articles.lang` +
     `rss_articles.lang` are 100% non-NULL post-rebuild (PROJECT-KB-v2.md "Pass
     conditions" §4).
**Plans:** TBD
**UI hint:** **conditional yes** (revised 2026-05-13 — smoke verification at 3 viewports against production-data-rendered output is the milestone gate; visual regressions surfaced by smoke MUST be closed by re-invoking design Skills, not by ad-hoc CSS patches)
**Required Skills (HARD — see kb/docs/10-DESIGN-DISCIPLINE.md):**
- `Skill(skill="ui-ux-pro-max", ...)` — IF smoke discovers visual gaps (overflow, truncation, responsive issues, RTL chars, long-title wrapping, etc.), invoke to design proper component-level fix — do NOT band-aid with one-off CSS overrides.
- `Skill(skill="frontend-design", ...)` — IF kb-4 needs polish iteration, invoke alongside ui-ux-pro-max output. Do NOT hand-write CSS / template patches.
- `Skill(skill="database-reviewer", ...)` — at cron-script time, review `kb/scripts/daily_rebuild.sh` for race conditions with running uvicorn / ingest cron / lock contention against SQLite + LightRAG storage.
- `Skill(skill="security-reviewer", ...)` — at deploy time, review systemd unit + Caddy snippet + FastAPI /api/* surface for info-leakage / path-traversal / ReDoS / JSON-injection. Public deploy without auth means API surface needs scrutiny.
**Pre-execution gate:** kb-4 inherits `kb-1-UI-SPEC.md` + `kb-3-UI-SPEC.md` as locked design contracts. Smoke verification MUST compare Playwright screenshots vs kb-1 + kb-3 baselines; any visual regression = phase NOT complete. Real PNG sourced for `kb/static/VitaClaw-Logo-v0.png` (UI-04 carry-forward gate from kb-1 + kb-1-04b).
**Notes:**
- DEPLOY-05 is intentionally narrow: the milestone verifies same-host only.
  Different-host deploy is "not blocked" but not certified — calling that out
  prevents a future operator from assuming the bind-mount path was tested.
- Smoke 3 sub-step 3 (LightRAG-unavailable simulation) is the most fragile —
  expect 1-2 plan-internal iterations on the fallback-trigger conditions
  (timeout vs exception vs storage-path missing). Budget time accordingly.
- No Caddy TLS / HTTPS / ICP-备案 in scope — Caddy automatic TLS is a deploy
  concern handled by the operator, not a milestone artifact.
- **Verification regex (run before declaring kb-4 complete):**
  If any visual gap was closed in this phase, `grep "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/kb-4-*/*-SUMMARY.md` must return ≥1 match. Same for `frontend-design` if templates/CSS were touched. `Skill(skill="security-reviewer"` must always match (deploy surface review is non-negotiable).
- No new functional code in this phase. Any code change beyond
  `kb/deploy/*` + `kb/scripts/daily_rebuild.sh` is a regression patch on kb-1 /
  kb-3 surfaced by smoke; allowed but should be flagged in the plan.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| kb-1: SSG Export + i18n Foundation | 11/11 + redesign-quick-in-progress | Complete pre-redesign (26/27 REQs; UI-04 partial → kb-4 PNG carry-forward); UI redesign quick task in progress 2026-05-13 to close design-dimension audit | 2026-05-13 |
| kb-2: Topic Pillar + Entity Pages + Cross-Link Network | 10/10 | Complete (12/12 REQs; full Skill discipline; 58 integration tests; 12/12 UAT viewports) | 2026-05-13 |
| kb-3: FastAPI Backend + Bilingual API + Search + Q&A | 0/? | Not started | — |
| kb-4: Ubuntu Deploy + Cron + Smoke Verification | 0/? | Not started | — |

---

## Coverage validation

**62/62 v2.0 requirements mapped, no orphans, no duplicates.**

| Phase | Count | REQs |
|-------|-------|------|
| kb-1 | 27 | I18N-01, I18N-02, I18N-03, I18N-04, I18N-05, I18N-06, I18N-08, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, EXPORT-01, EXPORT-02, EXPORT-03, EXPORT-04, EXPORT-05, EXPORT-06, UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, CONFIG-01 |
| kb-2 | 12 | TOPIC-01, TOPIC-02, TOPIC-03, TOPIC-04, TOPIC-05, ENTITY-01, ENTITY-02, ENTITY-03, ENTITY-04, LINK-01, LINK-02, LINK-03 |
| kb-3 | 18 | I18N-07, API-01, API-02, API-03, API-04, API-05, API-06, API-07, API-08, SEARCH-01, SEARCH-02, SEARCH-03, QA-01, QA-02, QA-03, QA-04, QA-05, CONFIG-02 |
| kb-4 | 5 | DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05 |
| **Total** | **62** | |

By category breakdown:

- I18N (8): kb-1 has 7 (01-06, 08), kb-3 has 1 (07) ✓
- DATA (6): kb-1 has all 6 ✓
- EXPORT (6): kb-1 has all 6 ✓
- UI (7): kb-1 has all 7 ✓
- TOPIC (5): kb-2 has all 5 ✓ [NEW 2026-05-13]
- ENTITY (4): kb-2 has all 4 ✓ [NEW 2026-05-13]
- LINK (3): kb-2 has all 3 ✓ [NEW 2026-05-13]
- API (8): kb-3 has all 8 ✓
- SEARCH (3): kb-3 has all 3 ✓
- QA (5): kb-3 has all 5 ✓
- DEPLOY (5): kb-4 has all 5 ✓
- CONFIG (2): kb-1 has 1 (CONFIG-01), kb-3 has 1 (CONFIG-02) ✓

---

## T-shirt effort estimates

Coarse calibration; refined per-plan inside `/gsd:plan-phase`.

| Phase | T-shirt | Reasoning |
|-------|---------|-----------|
| kb-1 | **L** (3-4 days, +0.5 day for redesign quick) | 27 REQs and the broadest surface area: 3 categories' worth of templates (UI), full data layer (DATA), SSG renderer (EXPORT), and the bilingual chrome system (I18N). Most work is straightforward Jinja2 + SQL queries, but volume + cross-cutting concerns (i18n filter on every template, content_hash resolution in 3 places) push this above M. content_hash format mismatch between KOL (md5[:10]) and RSS (full md5 truncated) needs care per `kb/docs/09-AGENT-QA-HANDBOOK.md` Q1. **+0.5d UI redesign quick added 2026-05-13** to close design-dimension audit gaps (Skill-invocation discipline + D-12 token compliance + chip / glow / icon / state-class system). |
| kb-2 | **M** (1.5-2 days) | 12 REQs across 3 new categories (TOPIC + ENTITY + LINK). Pure SSG (Jinja2 + data layer extensions); no HTTP, no LLM, no new infra. Reuses kb-1 redesigned tokens — does NOT re-design components. Main work: 5 query functions in `kb.data.article_query`, 2 new templates (`topic.html`, `entity.html`), 2 new homepage sections in `index.html`, 1 sidebar extension to `article.html`, ~96 new HTML pages rendered by export driver (5 topic + ~91 entity), JSON-LD CollectionPage + Thing schemas. Sub-1-day if not for the entity-slug edge cases (Unicode names, dup variants, threshold tuning). |
| kb-3 | **L** (3-4 days) | 18 REQs but the highest behavioral complexity: two BackgroundTasks-backed async job stores, FTS5 trigram setup including UNION view of KOL + RSS, `/synthesize` wrapper with timeout + never-500 fallback, KG-mode search wrapper (C2-stable), and the static image mount replacing `:8765`. Multi-worker known limitation tabled to v2.1 (QA-03), but single-worker still has subtle timing edges (job_id collision with restart, in-memory loss). |
| kb-4 | **S** (1 day) | 5 REQs, all ops: install.sh (one shell file), systemd unit (one ini-style file), Caddy snippet (one block), cron script (one shell file). The dominant work is the 3 smoke scenarios and any debug-and-patch loop that surfaces — but those are observation, not coding. Budget +0.5 day for one regression iteration on smoke 3. |

**Milestone total: ~9-11 days of focused work** (was ~7-9 before kb-2 revival; +1.5-2d for kb-2 + 0.5d for kb-1 redesign quick). Likely longer wall-clock with parallel-track context switching against v3.4 / v3.5 / Agentic-RAG-v1, smoke-test debug iteration, and Ubuntu deploy environment quirks.

---

## Dependencies

- kb-1 depends on: nothing (greenfield within milestone; existing `kol_scan.db` +
  `~/.hermes/omonigraph-vault/images/` are read-only inputs).
- kb-2 depends on: kb-1 (`kb.config`, `kb.data.article_query` for extension, `kb-1-UI-SPEC.md` redesigned tokens, `kb/templates/article.html` to extend, `kb/export_knowledge_base.py` to extend with topic + entity rendering loops). Also reads new tables `classifications` + `extracted_entities` directly (read-only — no schema changes).
- kb-3 depends on: kb-1 (`kb.config`, `kb.data.article_query`, populated `lang`
  columns, content_hash resolution, SSG output for `final_content.md` consumption) + kb-2 (its new query functions become candidates for HTTP exposure: `/api/topic/{slug}`, `/api/entity/{slug}` — though API-* REQs don't currently mandate them, kb-3 plan can add them as bonus).
- kb-4 depends on: kb-3 (smoke 2 + smoke 3 exercise the API and synthesize
  endpoints).

No phase-internal parallelism is recommended; phases are strictly sequential.

---

## Cross-phase touches (for `/gsd:plan-phase` awareness)

These REQs are first-delivered in the listed phase but have legitimate touch-points
in later phases. Document in plan files when those touches happen, but do NOT
re-map the REQ.

| REQ | First delivered | Touch-points |
|-----|----------------|--------------|
| I18N-04 | kb-1 | kb-3 reuses `list_articles(lang=...)` for API-02 — same query function, same lang filter semantics; do not duplicate logic |
| DATA-04 | kb-1 | kb-2 + kb-3 API-02 import it directly. kb-2 may extend with `topic_articles_query` / `entity_articles_query` in same module |
| DATA-05 | kb-1 | kb-3 API-03 imports it directly |
| DATA-06 | kb-1 | kb-3 API-03 reuses runtime content_hash resolution for unified URL handling. kb-2 entity / topic page links use same hash format |
| EXPORT-05 | kb-1 | kb-3 API-03 reuses the `localhost:8765` → `/static/img/` rewrite when serving `body_md` over JSON. kb-2 entity-page article-card images need same rewrite |
| CONFIG-01 | kb-1 | kb-2 adds `KB_ENTITY_MIN_FREQ` env var to `kb/config.py`; kb-3 reads `KB_PORT` and `KB_SYNTHESIZE_TIMEOUT`; kb-4 reads paths for systemd `Environment=` |
| TOPIC-* / ENTITY-* / LINK-* | kb-2 | kb-3 may expose `/api/topic/{slug}` / `/api/entity/{slug}` (bonus; not in current API-* REQs). kb-4 smoke verifies topic + entity pages render at 3 viewports without horizontal scroll |
| Article-card component | kb-1 (redesign) | kb-2 reuses verbatim for entity/topic article lists. kb-3 result page may reuse for source-articles section |
| Chip component (lang chip / topic chip / entity chip) | kb-1 (redesign) | kb-2 entity-cloud + topic-card homepage sections + LINK-01/02 sidebars all reuse |
| SEARCH-01 | kb-3 | kb-4 `daily_rebuild.sh` invokes `rebuild_fts.py` which is owned by SEARCH-02 — kb-4 does not modify the rebuild script, only schedules it |

---

## Open notes

- **REQUIREMENTS-KB-v2.md header text says "37 REQs"; actual count is 50.** Roadmap
  uses 50. Do not modify REQUIREMENTS-KB-v2.md scope; reconciliation is a separate
  doc-fix task.
- **Smoke test gate:** PROJECT-KB-v2.md "Pass conditions" defines 5 must-hold
  conditions for milestone close. Roadmap's kb-4 success criterion #5-#6 mirror
  these. Both must agree on every criterion at milestone-close audit.
- **Cross-milestone contracts (C1-C4) are read-only.** No phase modifies
  `kg_synthesize.synthesize_response()` (C1), `omnigraph_search.query.search()`
  (C2), `kol_scan.db` non-additive schema (C3), or `images/{hash}/final_content.md`
  path (C4). Adding nullable `lang` column (DATA-01) is C3-additive non-breaking.
- **Out of scope reminders** (do NOT include in any phase): KB-2 entity / topic
  pages, content auto-translation, cross-language search, Databricks Apps deploy,
  rate limiting, Repository pattern abstraction, SEO push (百度 / Google submit),
  multi-user / login / 评论, HTTPS / TLS rotation. See PROJECT-KB-v2.md "Out of
  Scope" table for full list.
- **No research stage** — `kb/docs/01-09` covers design end-to-end. The `gsd-roadmapper`
  consumed those directly; no `gsd-project-researcher` agents spawned.

---

*Roadmap created: 2026-05-12 by `gsd-roadmapper`.*
*Last updated: 2026-05-12 — initial draft.*
