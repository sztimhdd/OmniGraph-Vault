# Feature Landscape — v3.4 RSS-KOL Alignment

**Domain:** RSS-to-graph-RAG pipeline — full-body extraction + multimodal ingest
**Researched:** 2026-05-03
**Scope:** SUBSEQUENT MILESTONE — closes the gap between the existing RSS arm
(summary-only, text-only) and the KOL arm (full-body, multimodal). Zhihu
enrichment is permanently excluded (D-07 REVISED). Existing stable features
(Vision Cascade, checkpoints, KOL classify/ingest) are not re-listed.

---

## Table Stakes

Features whose absence makes v3.4 fail its success criteria. Every item here
must ship.

| Feature | Why Expected | Complexity | Category | Dependency |
|---------|--------------|------------|----------|------------|
| RSS full-body scrape via generic cascade | Summary-only RSS makes depth classification worthless; all 6 success criteria require full-body text | Med | Scrape | `ingest_wechat.py` scrape functions |
| Full-body classification for RSS articles (port `_build_fullbody_prompt`) | Success criterion 1 requires classify-on-full-body; current `rss_classify.py` uses `summary[:4000]` — a 200-500 char truncated feed snippet | Med | Classify | `batch_classify_kol._build_fullbody_prompt`, `_call_deepseek_fullbody` |
| Image download from scraped RSS body | RSS articles on Arxiv/Substack/personal blogs carry high-value figures; without download they never enter the Vision Cascade | Med | Multimodal | `image_pipeline.download_images`, `filter_small_images` |
| Vision Cascade description for RSS images | Success criterion 1 requires "图片语义可检索"; Vision Cascade (SiliconFlow → OpenRouter → Gemini) is already validated | Low | Multimodal | `image_pipeline.describe_images` — no new code, call existing function |
| `localize_markdown` rewrite to localhost for RSS images | Current `rss_ingest.py` never calls `localize_markdown`; Gemini Vision ingest requires `http://localhost:8765/…` URLs, not CDN URLs | Low | Multimodal | `image_pipeline.localize_markdown` at `_DEFAULT_IMAGE_BASE_URL` |
| Multimodal `ainsert` for RSS (replaces summary-only insert) | Without it all 479+ RSS docs remain text-only; success criterion 1 requires "LightRAG 中文内容 + 图片语义可检索" | Low | Multimodal | `rss_ingest._ingest_lightrag` — pass `final_md` with localized img URLs |
| `stuck-doc` CLI cleanup tool | Success criterion 6: "故意制造一次失败，验证后续 batch 不受干扰"; without this Wave 3 cannot close | Med | Ops | LightRAG `adelete_by_doc_id` API (validated in `phase0_delete_spike.py`) |
| Checkpoint system for RSS articles (5-stage markers) | 1020 backlog re-ingest must be resumable; failure mid-batch without checkpoints means restart from scratch | Med | Ops | `lib/checkpoint.py` — same 5-stage schema as KOL path |
| E2E fixture `test/fixtures/rss_sample_article/` | Success criterion 3 mandatory; CI cannot regress without a fixture | Low | Validation | `test/fixtures/gpt55_article/` as template |
| `aget_docs_by_ids` post-ingest verification gate | Already in `rss_ingest.py` as Task 4.2 — must be retained after rewrite; without it, PROCESSING stuck-docs go undetected | Low | Validation | `rss_ingest._ingest_lightrag` lines 184-207 — keep as-is |

---

## Differentiators

Features that improve quality beyond success criteria but are not required to
ship. Decide per-wave based on effort budget.

| Feature | Value Proposition | Complexity | Category | Condition to Include |
|---------|-------------------|------------|----------|----------------------|
| D-RSS-SCRAPER-SCOPE Option A: shared cascade used by KOL `_classify_full_body` too | One cascade module, both arms use it; fixes the Day-1 pre-flight `batch_ingest_from_spider.py:940` UA-only regress at the same time | Med | Scrape | Adopt if KOL regression risk from shared module is low (Wave 3 regression test covers it) |
| Content-type routing in generic scraper (Arxiv→abstract+PDF, Substack→HTML body, Medium→member-gate detection) | RSS sources are heterogeneous; without routing, code assumes Arxiv returns HTML like a blog — it doesn't | Med | Scrape | Required for Arxiv sources if any RSS feeds include arxiv.org |
| trafilatura as fallback extractor layer | trafilatura excels at boilerplate removal on arbitrary HTML; preserves code fences and `<pre>` blocks; handles most personal blogs correctly. Install is `pip install trafilatura` (~1 MB, no system deps). Use ONLY as a fallback tier below BeautifulSoup+html2text | Low | Scrape | Include only if BeautifulSoup extraction quality is unacceptable after Wave 1 smoke; do NOT add as a primary extractor |
| Image size/type pre-filter for RSS images | Skip 1×1 tracking pixels, button images < 5 KB; `filter_small_images` already exists for KOL path | Low | Multimodal | Already exists — call it; no new code |
| SQLite column `body` on `rss_articles` (mirror KOL `articles.body`) | Enables re-classify without re-scrape for RSS, same pattern as KOL | Low | Classify | High value — ~10 lines migration in `init_db`; add in Wave 1 |
| Per-article progress logging to `rss_ingest.log` (structured JSON lines) | Enables `checkpoint_status.py`-style monitoring for RSS batch runs | Low | Ops | Low effort; include in Wave 2 |
| `batch_validation_report.json` for RSS batches (provider_usage breakdown) | Matches KOL batch report; shows Vision Cascade health per run | Low | Validation | Port from KOL batch with minimal changes |

---

## Anti-Features

Features to explicitly NOT build in v3.4. Each has a concrete justification.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| LLM-based body extraction (prompt Gemini/DeepSeek to "extract article body from HTML") | Costs tokens per article; latency 2–5s per article vs <100ms for BeautifulSoup; hallucination risk on code blocks. BeautifulSoup+html2text already handles the KOL arm correctly. trafilatura (if needed) is the right fallback, not an LLM | Use BeautifulSoup+html2text (existing); add trafilatura as fallback only if extraction quality fails |
| Site-specific CSS selectors per RSS source (Substack `.post-content`, Medium `article`, etc.) | Maintenance hell: selectors break every time the site redesigns. Already proven in KOL arm: WeChat's `js_content` div is the only site-specific selector tolerated. RSS sources are more numerous and less stable | Use generic content extraction (readability heuristics); allow fallback cascade to degrade gracefully |
| Readability.js / mozilla-readability via subprocess or Playwright | Extra dependency, Playwright subprocess overhead, no better than trafilatura for Python RSS pipelines | trafilatura (Python, no subprocess) if heuristic extraction is needed |
| Translation for RSS articles (current `rss_ingest.py` translates EN→CN via DeepSeek) | Translation doubles LLM cost per EN article, adds 5–10s latency, and loses nuance in code-heavy technical posts. The KOL arm does NOT translate. Knowledge graph retrieval quality is not measurably better in CN vs EN for tech content | Store original language; classification prompt already handles EN→CN via D-08; skip translation entirely in rewrite |
| Duplicate detection beyond URL hash | URL UNIQUE constraint in `rss_articles` already prevents duplicates. Content hash (`content_hash` column) is stored but only used for delta detection. LightRAG's `filter_keys` deduplicates at the doc level. A third similarity layer (MinHash, embedding cosine) is over-engineering for a single-user tool | URL UNIQUE + LightRAG `filter_keys` is sufficient |
| Cron pre-hook for stuck-doc cleanup (running `adelete_by_doc_id` automatically before each batch) | LightRAG already resets PROCESSING/FAILED docs to PENDING at `initialize_storages()` time (source: `lightrag.py:1687-1735`). An additional pre-hook would delete docs that LightRAG would self-heal on the next ainsert, causing unnecessary re-ingestion | Rely on LightRAG self-heal; build a manual CLI tool for operator-initiated cleanup only |
| Runtime analytics dashboard / Prometheus metrics for RSS pipeline | Logs + `checkpoint_status.py` + `batch_validation_report.json` cover all operational visibility needed. A metrics server adds a new runtime dependency and maintenance burden for a personal tool | Use structured log lines + existing checkpoint scripts |
| Parallel/concurrent RSS article ingest | Current KOL ingest is sequential by design (embedding quota, Vision Cascade SiliconFlow balance, LightRAG pipeline lock). Adding concurrency to RSS would require the same quota management infrastructure. Premature optimization — fix correctness first | Sequential with checkpoint/resume covers the 1020-article backlog adequately |
| Zhihu 好问 enrichment for RSS articles | D-07 REVISED permanent exclusion. No exceptions in v3.4. | (out of scope, period) |

---

## Feature Dependencies

```
Wave 1 — Generic scraper module
  generic_scraper(url) → (markdown, images, metadata)
    depends on: ingest_wechat.scrape_wechat_ua (refactored to non-WeChat URLs)
    depends on: ingest_wechat.scrape_wechat_apify (generalized or bypassed for non-WeChat)
    depends on: ingest_wechat.scrape_wechat_cdp (generalized or bypassed for non-WeChat)
  rss_articles.body column (SQLite migration)
    depends on: init_db() in batch_classify_kol.py / orchestrate_daily schema

Wave 2 — RSS full pipeline rewrite
  rss full-body classify
    depends on: Wave 1 generic_scraper (needs body text)
    depends on: batch_classify_kol._build_fullbody_prompt (port, no change)
    depends on: batch_classify_kol._call_deepseek_fullbody (reuse as-is)
  RSS image download
    depends on: Wave 1 generic_scraper (needs img_urls list from scraped body)
    depends on: image_pipeline.download_images (reuse as-is)
    depends on: image_pipeline.filter_small_images (reuse as-is)
  Vision Cascade for RSS
    depends on: RSS image download
    depends on: image_pipeline.describe_images (reuse as-is)
  localize_markdown for RSS
    depends on: RSS image download (needs url_to_local mapping)
    depends on: image_pipeline.localize_markdown (reuse as-is)
  multimodal ainsert
    depends on: localize_markdown for RSS
    depends on: Vision Cascade for RSS
    depends on: rss_ingest._ingest_lightrag (rewrite to use full_md, not summary)
  checkpoint system for RSS
    depends on: lib/checkpoint.py (reuse as-is)
    gate: must be in place BEFORE 1020-article backlog re-ingest

Wave 3 — Ops + validation
  stuck-doc CLI tool
    depends on: LightRAG adelete_by_doc_id (validated, phase0_delete_spike.py)
    note: safe only when no concurrent ainsert/pipeline is running — CLI enforces this
  E2E fixture rss_sample_article
    depends on: Wave 2 pipeline complete (fixture exercises full path)
  1020-article backlog re-ingest
    depends on: checkpoint system (Wave 2)
    depends on: stuck-doc tool (Wave 3, for cleanup before/after batch)
  cron cutover (register_phase5_cron.sh step_7 body)
    depends on: E2E fixture passing
    depends on: Day-1/2/3 baseline complete (~2026-05-06)
```

---

## Open Decision: D-RSS-SCRAPER-SCOPE (Option A vs B)

**Context:** Day-1 pre-flight found `batch_ingest_from_spider.py:940` uses
`scrape_wechat_ua` (UA-only) for KOL scrape-on-demand, which fails on WeChat
articles that block UA rotation. The user prefers Option A (shared cascade,
KOL also benefits).

| | Option A (shared cascade, both arms) | Option B (RSS-only new module) |
|--|--------------------------------------|-------------------------------|
| Code written once | Yes — cascade module used by both `_classify_full_body` and `rss_ingest` | No — two parallel scraper paths |
| KOL regression risk | Medium — `_classify_full_body` caller must be updated; requires Wave 3 regression | Zero — KOL path untouched |
| Fixes Day-1 KOL scrape bug | Yes — same fix for `batch_ingest_from_spider.py:940` | No — KOL bug deferred |
| Effort | ~1.5× Wave 1 scope | ~1× Wave 1 scope |
| **Recommendation** | **Option A**, conditioned on Wave 3 KOL regression test with 5 articles | |

**Rationale:** The cascade is the same logic (Apify → CDP → MCP → UA →
fallback). Writing it once and reusing it in both arms prevents the divergence
that caused the v3.4 problem in the first place. The KOL regression is low
risk because `_classify_full_body` is the only caller of `scrape_wechat_ua`
in `batch_ingest_from_spider.py`, and it is already guarded by a
`if not body:` check — the refactor is surgical.

---

## Open Decision: D-STUCK-DOC-IDEMPOTENCY (CLI vs cron pre-hook)

**Recommendation: CLI tool only. Not a cron pre-hook.**

**Evidence from LightRAG source** (`lightrag.py:1687-1735`): On every call to
`initialize_storages()`, LightRAG automatically resets any doc whose status is
`PROCESSING` or `FAILED` (and whose content is still present in `full_docs`)
back to `PENDING`. This means every new batch invocation self-heals stuck docs
before re-processing them. An automatic cron pre-hook that calls
`adelete_by_doc_id` on FAILED docs would delete docs that LightRAG would have
retried for free.

**Safe execution window:** `adelete_by_doc_id` uses a pipeline lock
(`pipeline_status_lock`) and rejects calls when the pipeline is busy with
non-deletion tasks (source: `lightrag.py:3247`). The CLI tool must therefore:
1. Check that no `ainsert` batch is running (check `pipeline_status` shared namespace).
2. Run `adelete_by_doc_id` only after the batch exits.
3. This is an operator-initiated operation — never automated.

**Storage layers affected:** `doc_status` (JsonDocStatusStorage), `full_docs`
(KV store), entity graph (kuzu), chunk vectors (LanceDB). `adelete_by_doc_id`
handles all four; no manual file-level surgery is needed.

---

## MVP Recommendation (feature priority for Wave ordering)

**Wave 1 must deliver:**
1. Generic scraper module with cascade (Apify → CDP → MCP → UA → plain HTTP fallback) for non-WeChat URLs
2. `rss_articles.body` SQLite column migration

**Wave 2 must deliver:**
3. RSS full-body classifier (port `_build_fullbody_prompt` + `_call_deepseek_fullbody`)
4. RSS image download + Vision Cascade + `localize_markdown`
5. Multimodal `ainsert` replacing summary-only insert
6. Checkpoint/resume system for RSS articles

**Wave 3 must deliver:**
7. `stuck-doc` CLI tool (`scripts/rss_stuck_doc_cleanup.py`)
8. E2E fixture `test/fixtures/rss_sample_article/`
9. 1020-article backlog re-ingest
10. Cron cutover

**Defer to post-v3.4:**
- trafilatura as optional fallback (add only if Wave 1 extraction quality fails on real RSS sources)
- Option D RSS classifier batch refactor (already capped at 500 via env; performance optimization deferred)
- DeepSeek 600s merge timeout (Phase 17 tracking issue)

---

## Complexity Estimates

| Feature | Effort (person-days) | Notes |
|---------|----------------------|-------|
| Generic scraper module (Wave 1) | 1.5d | New file `lib/generic_scraper.py`; refactor 4 scrape functions from `ingest_wechat.py`; Option A means updating `_classify_full_body` caller too |
| `rss_articles.body` migration | 0.25d | 10-line `ALTER TABLE IF NOT EXISTS` in `init_db` |
| RSS full-body classifier (Wave 2) | 0.5d | Direct port of `_build_fullbody_prompt` + `_call_deepseek_fullbody`; adapt `rss_classify.py` to call fullbody path |
| RSS image download + localize | 0.5d | Call `image_pipeline.download_images` + `filter_small_images` + `localize_markdown` in `rss_ingest.py` |
| Vision Cascade for RSS | 0.25d | Call `image_pipeline.describe_images`; no new code |
| Multimodal ainsert rewrite | 0.5d | Rewrite `_ingest_lightrag` to accept `final_md` with localized imgs; keep PROCESSED gate |
| Checkpoint system for RSS | 0.75d | Map 5 KOL stages to RSS equivalents; adapt `lib/checkpoint.py` calls |
| Stuck-doc CLI tool | 0.75d | `scripts/rss_stuck_doc_cleanup.py`; list FAILED docs, call `adelete_by_doc_id`, print report; pipeline-busy guard |
| E2E fixture | 0.5d | Sample article scraped/stored; fixture JSON for `skill_runner.py` |
| Backlog re-ingest + cron cutover | 1.0d | Script to enumerate `rss_articles` with `enriched=0`; checkpoint-aware; cron body swap in `register_phase5_cron.sh` |
| **Total** | **~6.5d** | |

---

## Sources

- `batch_classify_kol.py` lines 226-310 — `_build_fullbody_prompt` and `_call_deepseek_fullbody` (existing, port directly)
- `enrichment/rss_ingest.py` — current summary-only ingest path (rewrite target)
- `enrichment/rss_classify.py` lines 110-141 — current summary-based classify (rewrite target)
- `ingest_wechat.py` lines 415-506 — `scrape_wechat_ua` cascade pattern to generalize
- `image_pipeline.py` lines 271-285, 44 — `localize_markdown` + localhost base URL
- `batch_ingest_from_spider.py` lines 904-980 — `_classify_full_body` KOL scrape-on-demand (Option A target)
- `venv/Lib/site-packages/lightrag/lightrag.py` lines 1687-1735 — self-healing PROCESSING→PENDING reset at `initialize_storages()`
- `venv/Lib/site-packages/lightrag/lightrag.py` lines 3223-3265 — `adelete_by_doc_id` concurrency contract
- `.claude/worktrees/agent-a02a812b76ae0b9f9/scripts/phase0_delete_spike.py` — validated `adelete_by_doc_id` spike
- `.planning/PROJECT.md` — v3.4 target features (waves), success criteria, open decisions, carve-outs
- CLAUDE.md — Vision Cascade provider order, SiliconFlow balance management, checkpoint stage schema
