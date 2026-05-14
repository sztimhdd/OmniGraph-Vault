# Milestone KB-v2 Requirements — Bilingual Agent-Tech Content Site

**Status:** ACTIVE (started 2026-05-12).

**Milestone goal:** Build a useful, public, bilingual (zh-CN / en) Agent-tech content site
on top of OmniGraph's existing data assets. List / detail / search / RAG Q&A — full
i18n switch, zero login, runs on a single Ubuntu server. **Not** an SEO funnel; the site
exists because Agent practitioners actually want to use it.

**Gate:** All 3 smoke-test scenarios in `PROJECT-KB-v2.md` pass + no contract C1-C4 break +
Lighthouse LCP < 2.5s on article detail page.

**Locked decisions (from `kb/docs/02-DECISIONS.md` + `kb/docs/09-AGENT-QA-HANDBOOK.md`):**

- D-04: Q&A 复用 `kg_synthesize.synthesize_response()` (~50 LOC HTTP 包装)
- D-08: Python Jinja2 SSG (no Astro / Next.js / SPA framework)
- D-13: 部署在单台 Ubuntu 服务器 (systemd + Caddy)
- D-14: 详情页 `final_content.md` 优先 → `articles.body` fallback
- D-15: FastAPI :8766 接管图片服务,`:8765` 下线
- D-17: `http://localhost:8765/` → `/static/img/` 运行时正则重写
- D-18: 默认 SQLite FTS5 trigram tokenizer (built-in 3.34+, 中英通杀)
- D-19: `/synthesize` 异步 BackgroundTasks + 轮询
- D-20: URL 用 `content_hash md5[:10]`
- K-1: env-driven config (路径 / 端口 / 语言)
- K-2: content_hash 运行时计算,不改 DB
- K-4: systemd + uvicorn,**不依赖 Hermes agent runtime**
- bilingual scope (this milestone): UI chrome 双语 + 内容原文不翻译 + cookie/query 切换

**Cross-milestone contracts (do NOT break — see PROJECT-KB-v2.md):**

| C1 | `kg_synthesize.synthesize_response()` signature | 守住 |
| C2 | `omnigraph_search.query.search()` signature | 守住 |
| C3 | `kol_scan.db` schema (adding nullable column = non-breaking) | 守住 |
| C4 | `images/{hash}/final_content.md` path | 守住 |

---

## v2.0 Requirements (63 REQs across 12 categories)

> **Revision 2026-05-13:** kb-2 (Topic Pillar pages + Entity pages + cross-link network) revived from "deferred to v2.1" → in-scope this milestone. Triggered by Hermes prod data verification: `classifications` has 3945 rows (5 topics × 789 articles), `extracted_entities` has 5257 rows / 3319 distinct names with 91 entities at ≥5-article frequency / 26 at ≥10-article frequency. The earlier "13 canonical entities can't support entity surface" judgment was based on local dev DB (which had 0 classifications). Real production data supports 5 topic pillar pages + 26-91 entity pages today without requiring upstream LLM canonicalization. Three new REQ categories added: TOPIC (5) / ENTITY (4) / LINK (3) = 12 new REQs.

### I18N — Bilingual Core (8)

- [x] **I18N-01**: System detects user's preferred language from the `Accept-Language` HTTP header on first visit. Defaults to `zh-CN` if neither `zh` nor `en` is acceptable.
- [x] **I18N-02**: User can switch UI language via `?lang=en` or `?lang=zh` query param. Selection persists for 1 year via `kb_lang` cookie.
- [x] **I18N-03**: All UI chrome strings (nav, labels, buttons, footer, page titles, form placeholders) load from `kb/locale/zh-CN.json` + `kb/locale/en.json` via a `{{ t('key.path') }}` Jinja2 filter. Estimated ~50 string keys. *(Shipped kb-1-03: 45 keys, 8/8 tests pass.)*
- [x] **I18N-04**: User can filter article list by content language via `?lang=zh-CN` or `?lang=en`; default shows all languages mixed.
- [x] **I18N-05**: Article detail page sets `<html lang="zh-CN">` or `<html lang="en">` matching the article's **content** language (independent of UI chrome language).
- [x] **I18N-06**: Article detail page shows a visible badge ("中文" / "English") indicating content language at the top of the article.
- [ ] **I18N-07**: Q&A endpoint accepts `lang` parameter (`zh` / `en`); KB layer prepends `"请用中文回答。\n\n"` or `"Please answer in English.\n\n"` directive to the query before calling `kg_synthesize.synthesize_response()`. **Function signature unchanged** (C1 preserved).
- [x] **I18N-08**: Language switcher control visible in top nav on all pages — text label "中 / EN" or equivalent, click toggles `?lang=` and updates cookie.

### DATA — Data Layer (7)

- [x] **DATA-01**: One-time SQLite migration adds nullable `lang TEXT` column to both `articles` and `rss_articles` tables. Idempotent — re-running is safe (uses `PRAGMA table_info` pre-check). *(kb-1-02, 2026-05-12)*
- [x] **DATA-02**: `kb/scripts/detect_article_lang.py` populates `lang` column based on Chinese character ratio: `> 30%` → `zh-CN`, otherwise `en`. Produces stdout coverage report (`{zh-CN: N, en: M, unknown: K}`). *(kb-1-02 algorithm only — kb/data/lang_detect.py; driver in kb-1-05)*
- [x] **DATA-03**: `kb/scripts/detect_article_lang.py` runs incrementally — only updates rows where `lang IS NULL`. Safe to re-invoke daily via cron.
- [x] **DATA-04**: `kb/data/article_query.py` exposes `list_articles(lang=None, source=None, limit=20, offset=0)` returning paginated `ArticleRecord` dataclass list sorted by `update_time DESC`.
- [x] **DATA-05**: `kb/data/article_query.py` exposes `get_article_by_hash(hash: str)` resolving `md5[:10]` hash → `ArticleRecord | None`. Searches both KOL `articles` and RSS `rss_articles` tables.
- [x] **DATA-06**: `content_hash` URL identifier resolution: KOL articles with `content_hash` set use it directly (4/653); KOL articles with `content_hash IS NULL` get `md5(body)[:10]` computed at runtime; RSS articles use `content_hash[:10]` (truncate full md5). **No DB writes** (K-2).
- [ ] **DATA-07**: Content-quality filter for article-list query functions. `list_articles()` and all kb-2 list-style query functions (`topic_articles_query`, `entity_articles_query`, `cooccurring_entities_in_topic`) MUST exclude rows that fail any of: (a) `body IS NULL OR body = ''` (no scraped body in DB), (b) `layer1_verdict != 'candidate'` (Layer 1 reject or not yet classified), (c) `layer2_verdict = 'reject'` (Layer 2 reject; NULL is allowed for backwards-compat with rows pre-Layer 2). Applies symmetrically to KOL `articles` and RSS `rss_articles` (both tables have these columns since v3.5 ir-4). Single-article-by-hash lookup (`get_article_by_hash`) is NOT filtered — direct URL access to a known hash still works (search hits, bookmarks, KG synthesize sources). Expected v2.0 visibility on Hermes prod data: ~6% of scanned rows (~160/2501) at filter time; this is a 94% reduction from the current "show every scanned row" behavior and is the intended quality bar. Env override `KB_CONTENT_QUALITY_FILTER=off` allows disabling for debugging — default is `on`. Cross-phase impact: kb-1's article list page (`articles_index.html`) and kb-2's topic/entity article lists inherit this filter automatically once kb-3 ships the data-layer change; next SSG re-render produces filtered output. *(kb-3 — see `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md`)*

### EXPORT — SSG Build (6)

- [x] **EXPORT-01**: `kb/export_knowledge_base.py` is the single entry point generating all static HTML output to `kb/output/`. Re-running produces identical files for unchanged inputs (idempotent).
- [x] **EXPORT-02**: Export reads from SQLite + filesystem only; **never writes to either** (read-only consumption of OmniGraph data).
- [x] **EXPORT-03**: Export generates the minimum page set: `kb/output/index.html` (homepage with latest articles + Q&A entry CTA), `kb/output/articles/{hash}.html` (per-article detail), `kb/output/ask/index.html` (Q&A entry page). KB-2 entity / topic pages explicitly excluded.
- [x] **EXPORT-04**: Article detail page renders markdown body (preferring `final_content.enriched.md` → `final_content.md` → `articles.body` fallback per D-14) with Pygments code-block syntax highlighting.
- [x] **EXPORT-05**: Article detail page rewrites `http://localhost:8765/` → `/static/img/` in markdown body before rendering (D-17).
- [x] **EXPORT-06**: Export generates `kb/output/sitemap.xml` (all article URLs + homepage with `<lastmod>`) and `kb/output/robots.txt` (`User-agent: *`, `Sitemap: /sitemap.xml`). **Web courtesy baseline, not SEO push.**

### UI — Presentation (7)

- [x] **UI-01**: Global design tokens inherited from vitaclaw-site暗色主题: `--bg: #0f172a` / `--bg-card: #1e293b` / `--text: #f0f4f8` / `--accent: #3b82f6` / `--accent-green: #22d3a0`. Defined in single `kb/static/style.css` file.
- [x] **UI-02**: Font stack: `'Inter', 'Noto Sans SC', system-ui, sans-serif` — covers Latin and Chinese glyphs without external font loading on first paint.
- [x] **UI-03**: All pages responsive across mobile (320-767px), tablet (768-1023px), desktop (1024px+). No horizontal scroll on mobile viewport.
- [x] **UI-04**: Brand assets reused from vitaclaw-site (logo `VitaClaw-Logo-v0.png` in nav, `favicon.svg`). No new asset files in this milestone. *(kb-1: placeholder favicon + MISSING.txt logo accepted via approved-placeholder; real PNG carry-forward to kb-4 deploy.)*
- [x] **UI-05**: Every page emits Open Graph meta tags: `og:title`, `og:description`, `og:image`, `og:type`, `og:locale` (matches `<html lang>` for content pages). Web courtesy for IM share previews.
- [x] **UI-06**: Article detail pages emit JSON-LD `Article` schema with `inLanguage` field matching article content language. **Web courtesy baseline, not SEO push.**
- [x] **UI-07**: Article detail page shows breadcrumb navigation: Home > Articles > [Title]. Breadcrumb labels localized via i18n.

### API — FastAPI Backend (8)

- [x] **API-01**: `kb/api.py` is a single FastAPI application served by `uvicorn` on port 8766 (configurable via `KB_PORT` env). *(kb-3-04, 2026-05-14)*
- [x] **API-02**: `GET /api/articles?page=1&limit=20&source=&lang=&q=` returns paginated article list as JSON. Filters: `source` (`wechat` / `rss`), `lang` (`zh-CN` / `en`), `q` (LIKE search on title only — full-text via `/api/search`). P50 latency < 100ms. *(kb-3-05, 2026-05-14 — prod-shape DB p50=43.7ms)*
- [x] **API-03**: `GET /api/article/{hash}` returns `{hash, title, body_md, body_html, lang, source, images, metadata, body_source: "vision_enriched"|"raw_markdown"}`. 404 on hash miss. *(kb-3-05, 2026-05-14 — prod-shape DB p50=58.1ms; DATA-07 carve-out preserved)*
- [ ] **API-04**: `GET /api/search?q=&mode=fts&lang=&limit=20` performs SQLite FTS5 trigram search; returns top results in JSON with `snippet` field (200 chars, FTS5 `snippet()` function with match highlighting). P50 latency < 100ms.
- [ ] **API-05**: `GET /api/search?q=&mode=kg&lang=` triggers async LightRAG hybrid search via `omnigraph_search.query.search()`. Returns 202 + `job_id`; result polled via `GET /api/search/{job_id}`. **C2 preserved.**
- [ ] **API-06**: `POST /api/synthesize` accepts `{question: str, lang: "zh"|"en"}`; returns 202 + `job_id`. KB layer prepends language directive (per I18N-07) and calls `kg_synthesize.synthesize_response()` in BackgroundTasks. **C1 preserved.**
- [ ] **API-07**: `GET /api/synthesize/{job_id}` returns `{status: "running"|"done"|"failed", result?: {markdown: str, sources: [...]}, fallback_used: bool, confidence: "kg"|"fts5_fallback"}`. In-memory job store, single-worker MVP.
- [x] **API-08**: FastAPI mounts static images: `app.mount("/static/img", StaticFiles(directory=KB_IMAGES_DIR))`. Replaces independent `python -m http.server 8765`. *(kb-3-04, 2026-05-14)*

### SEARCH — FTS5 (3)

- [ ] **SEARCH-01**: SQLite FTS5 virtual table `articles_fts` is created with `tokenize='trigram'` (built-in SQLite ≥ 3.34, no jieba dep). Covers `articles.title + articles.body` AND `rss_articles.title + rss_articles.body` via UNION-fed view.
- [x] **SEARCH-02**: `kb/scripts/rebuild_fts.py` performs full FTS5 index rebuild. Invoked by daily cron after each export run. ~2300 rows, completes in < 5 seconds. *(kb-3-07, 2026-05-14)*
- [ ] **SEARCH-03**: FTS5 search results respect `lang` filter — `?lang=en` excludes rows where `articles.lang != 'en'`. Searches honor matched-snippet highlighting (max 200 chars per row).

### QA — Q&A Wrapping (5)

- [ ] **QA-01**: KB layer wraps `kg_synthesize.synthesize_response()` without modifying its signature. Wrapper lives in `kb/services/synthesize.py` (~50 LOC).
- [ ] **QA-02**: Language directive prepended to query per I18N-07: `lang="zh"` → `"请用中文回答。\n\n"`; `lang="en"` → `"Please answer in English.\n\n"`. **No other prompt manipulation.**
- [ ] **QA-03**: BackgroundTasks executes synthesize call asynchronously. In-memory job store maps `job_id → {status, result, fallback_used, started_at}`. Single uvicorn worker (`--workers 1`). Multi-worker known limitation deferred to v2.1.
- [ ] **QA-04**: Synthesize timeout default 60 seconds (override via `KB_SYNTHESIZE_TIMEOUT` env). On timeout, fallback path triggers; in-memory job state set to `done` with `fallback_used: true`.
- [ ] **QA-05**: KB-side fallback path: query FTS5 for top-3 articles matching the question, concatenate `(title + 200-char snippet)` of each into a markdown response. Returns `{status: "done", confidence: "fts5_fallback", fallback_used: true}`. **Never returns 500 on synthesize failure.**

### DEPLOY — Ubuntu Production (5)

- [ ] **DEPLOY-01**: `kb/deploy/kb-api.service` is a systemd service unit running `uvicorn kb.api:app --host 127.0.0.1 --port 8766 --workers 1`. `Restart=always`, `Environment=PYTHONPATH=/opt/OmniGraph-Vault`, `User=` follows server convention.
- [ ] **DEPLOY-02**: `kb/deploy/Caddyfile.snippet` provides Caddy config snippet routing `/static/img/*` → `localhost:8766`, `/api/*` → `localhost:8766`, and `/*` → `kb/output/` (static SSG files served by Caddy directly, not through FastAPI).
- [ ] **DEPLOY-03**: `kb/deploy/install.sh` is the canonical install / update script: installs unit file, runs `systemctl daemon-reload && systemctl enable --now kb-api.service`, reloads Caddy. Idempotent — safe to re-run.
- [ ] **DEPLOY-04**: `kb/scripts/daily_rebuild.sh` is a cron-invoked script that runs `detect_article_lang.py` → `export_knowledge_base.py` → `rebuild_fts.py` in sequence. Logs to `/var/log/kb-rebuild.log`. Fires daily at 12:00 server-local time.
- [ ] **DEPLOY-05**: Deployment supports same-host setup (KB on the box where `~/.hermes/omonigraph-vault/` lives, zero data sync) by env config. Different-host setup with bind-mount / NFS is not in scope this milestone but is not architecturally blocked (paths configurable per CONFIG-01).

### TOPIC — Topic Pillar Pages (5) [kb-2 NEW 2026-05-13]

- [x] **TOPIC-01**: Generate `kb/output/topics/{slug}.html` for each of 5 hardcoded topics (Agent / CV / LLM / NLP / RAG). Slug = topic.lower(). Topic list derives from `classifications.topic` distinct values; 5 hardcoded for v2.0 since the LLM classifier writes only these 5.
- [x] **TOPIC-02**: Topic page lists articles where `classifications.depth_score >= 2 AND (articles.layer1_verdict = 'candidate' OR articles.layer2_verdict = 'ok')`. Same JOIN handles `rss_articles` via UNION. Sorted by `update_time DESC`.
- [x] **TOPIC-03**: Topic page header has localized topic name + 1-2 line description (i18n keys `topic.{slug}.name` + `topic.{slug}.desc`) + article count. Sub-source filter (kbol / rss) optional via JS-only chip toggle (mirrors articles_index.html pattern).
- [x] **TOPIC-04**: Topic page emits JSON-LD `CollectionPage` schema with `name`, `description`, `numberOfItems`, `inLanguage` per UI chrome lang.
- [x] **TOPIC-05**: Topic page sidebar (or footer on mobile) lists top 5 entities co-occurring in this topic's articles (computed from `extracted_entities` ∩ topic article set, ordered by article frequency). Each entity links to `/entities/{slug}.html`.

### ENTITY — Entity Pages (4) [kb-2 NEW 2026-05-13]

- [x] **ENTITY-01**: Generate `kb/output/entities/{slug}.html` for each entity in `extracted_entities` with `COUNT(DISTINCT article_id) >= 5` (~91 pages on Hermes prod data). Threshold env-overridable via `KB_ENTITY_MIN_FREQ` for tuning.
- [x] **ENTITY-02**: Slug derivation: lowercase + URL-safe (replace spaces with `-`, drop `/` and other special chars), preserve Unicode (Chinese names like `叶小钗` URL-encoded). Stable across re-runs (no random hashing).
- [x] **ENTITY-03**: Entity page lists all articles mentioning this entity (sorted by article `update_time DESC`). Reuses `.article-card` from kb-1 redesigned templates. Page header shows entity name + total article count + lang distribution chip row.
- [x] **ENTITY-04**: Entity page emits JSON-LD `Thing` schema with `name`, `alternateName` (if any inferred dups), generic `@type: Thing` (specific typing — Person / Organization / SoftwareApplication — deferred to v2.1 because `entity_canonical.entity_type` is NULL across the corpus).

### LINK — Cross-page Internal Linking (3) [kb-2 NEW 2026-05-13]

- [x] **LINK-01**: `kb/templates/article.html` adds a sidebar (desktop) / footer-section (mobile) listing 3-5 related entities (from `extracted_entities` for that article_id, top by global frequency). Each entity is a chip linking to `/entities/{slug}.html`.
- [x] **LINK-02**: `kb/templates/article.html` adds 1-3 topic chips (from `classifications` WHERE `depth_score >= 2 AND article_id = ?`). Each topic chip links to `/topics/{slug}.html`.
- [x] **LINK-03**: Homepage (`kb/output/index.html`) gains 2 new sections: "🗂 Browse by Topic" (5 topic chip cards with article count) and "💡 Featured Entities" (top 12 entities by frequency, chip cloud). These sit between the existing "Latest Articles" section and the "Try AI Q&A" CTA.

### CONFIG — Env-Driven Configuration (2)

- [x] **CONFIG-01**: `kb/config.py` reads all paths and ports from environment variables with sensible defaults. Required keys: `KB_DB_PATH` (default `~/.hermes/data/kol_scan.db`), `KB_IMAGES_DIR` (default `~/.hermes/omonigraph-vault/images`), `KB_OUTPUT_DIR` (default `kb/output`), `KB_PORT` (default `8766`), `KB_DEFAULT_LANG` (default `zh-CN`), `KB_SYNTHESIZE_TIMEOUT` (default `60`).
- [x] **CONFIG-02**: KB does not introduce new LLM provider env vars. Q&A delegates to existing `lib.llm_complete.get_llm_func()` which honors `OMNIGRAPH_LLM_PROVIDER={deepseek, vertex_gemini}` (K-1). *(kb-3-04, 2026-05-14)*

---

## Future Requirements (deferred to v2.1+ — not implemented this milestone)

### v2.1 candidates

- **CANON-\***: LLM 实体规范化 — 跑全量 `extracted_entities` (3319 distinct names) 通过 LLM canonicalize → 写入 `entity_canonical` (目标 ≥150 canonical 实体);消除 dup (Anthropic / anthropic / Anthropic 公司 → 1 个 canonical)
- **TYPED-\***: `entity_canonical.entity_type` 列规范填充 (Person / Organization / SoftwareApplication / Concept) → kb-2 实体页升级为 typed JSON-LD `@type` (替代 generic `Thing`)
- **TOPIC-HIER-\***: 主题层级 (sub-topic → parent-topic 树) — 当前 5 个 topics (Agent / CV / LLM / NLP / RAG) 是平的,v2.1 设计层级 taxonomy
- **REPO-\***: Repository pattern 数据层抽象(`kb/data/repository.py` Protocol),为 Databricks 路径降本
- **DBX-\***: Databricks Apps EDC 内部预览部署(Foundation Model serving 替代 DeepSeek,Volume 挂 images)
- **RATE-\***: Rate limiting 公开端点(/synthesize Redis 令牌桶,防 LLM 配额炸)
- **MULTI-WORKER-\***: 替换 in-memory job store 为 SQLite-backed,支持 `--workers > 1`

### v2.2 candidates

- **TRANS-\***: 文章内容 LLM 自动翻译(中文文章 → 英文版本,反之)
- **CROSS-LANG-\***: 跨语言搜索(中文 query 匹配英文 corpus)+ 跨语言 Q&A
- **AGENTIC-RAG-\***: Agentic-RAG-v1 接入 `/synthesize` 端点(替代 kg_synthesize 直调)+ SSE 流式响应

---

## Out of Scope (explicit exclusions, do NOT add)

| Item | Why excluded |
|------|--------------|
| **Multi-user login / 评论 / 订阅 / 用户系统** | D-07 完全公开零门槛 |
| **CMS 后台 / 内容编辑界面** | 内容由 OmniGraph 管道产出,不手工编辑 |
| **OmniGraph pipeline 配置 / 爬虫控制 UI** | 不暴露上游管道,KB 是只读消费者 |
| **Astro / Next.js / React SPA 迁移** | D-08 极简 MVP 用 Python Jinja2 |
| **百度站长 API / 主动推送 / 关键词矩阵 / SEO 推送** | 项目目标调整 — 做"有用爱用的内容站",不做"SEO 吸铁石" |
| **HTTPS / TLS 自动续期** | Caddy 自动 TLS 即可,运维事项不在 milestone scope |
| **Analytics / 访问统计 / 埋点** | v2.0 不做(等真有人用再说),v2.1 候选 |
| **Hermes agent runtime / Hermes cron 调度** | K-4 锁定不依赖 |

---

## Traceability

> Mapped by `gsd-roadmapper` 2026-05-12 — see `.planning/ROADMAP-KB-v2.md` for
> phase decomposition rationale, success criteria, and T-shirt sizing.
> 50/50 v2.0 REQs mapped, 0 orphans, 0 duplicates.

| REQ | Phase | Status |
|-----|-------|--------|
| I18N-01 | kb-1 | Complete (kb-1-04) |
| I18N-02 | kb-1 | Complete (kb-1-04) |
| I18N-03 | kb-1 | Complete (kb-1-03) |
| I18N-04 | kb-1 | Not started |
| I18N-05 | kb-1 | Not started |
| I18N-06 | kb-1 | Not started |
| I18N-07 | kb-3 | Not started |
| I18N-08 | kb-1 | Complete (kb-1-04) |
| DATA-01 | kb-1 | Complete (kb-1-02) |
| DATA-02 | kb-1 | Complete — algorithm (kb-1-02); driver pending kb-1-05 |
| DATA-03 | kb-1 | Not started |
| DATA-04 | kb-1 | Not started |
| DATA-05 | kb-1 | Not started |
| DATA-06 | kb-1 | Not started |
| DATA-07 | kb-3 | Not started (added 2026-05-13) |
| EXPORT-01 | kb-1 | Not started |
| EXPORT-02 | kb-1 | Not started |
| EXPORT-03 | kb-1 | Not started |
| EXPORT-04 | kb-1 | Not started |
| EXPORT-05 | kb-1 | Not started |
| EXPORT-06 | kb-1 | Not started |
| UI-01 | kb-1 | Complete (kb-1-04) |
| UI-02 | kb-1 | Complete (kb-1-04) |
| UI-03 | kb-1 | Complete (kb-1-04) |
| UI-04 | kb-1 | Not started |
| UI-05 | kb-1 | Not started |
| UI-06 | kb-1 | Not started |
| UI-07 | kb-1 | Not started |
| API-01 | kb-3 | Complete |
| API-02 | kb-3 | Complete |
| API-03 | kb-3 | Complete |
| API-04 | kb-3 | Not started |
| API-05 | kb-3 | Not started |
| API-06 | kb-3 | Not started |
| API-07 | kb-3 | Not started |
| API-08 | kb-3 | Complete |
| SEARCH-01 | kb-3 | Not started |
| SEARCH-02 | kb-3 | Complete (kb-3-07) |
| SEARCH-03 | kb-3 | Not started |
| QA-01 | kb-3 | Not started |
| QA-02 | kb-3 | Not started |
| QA-03 | kb-3 | Not started |
| QA-04 | kb-3 | Not started |
| QA-05 | kb-3 | Not started |
| DEPLOY-01 | kb-4 | Not started |
| DEPLOY-02 | kb-4 | Not started |
| DEPLOY-03 | kb-4 | Not started |
| DEPLOY-04 | kb-4 | Not started |
| DEPLOY-05 | kb-4 | Not started |
| CONFIG-01 | kb-1 | Complete |
| CONFIG-02 | kb-3 | Complete |

**Phase totals:** kb-1 = 27, kb-3 = 18, kb-4 = 5 → **50 total**.
