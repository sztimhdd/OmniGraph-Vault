# Project Research Summary

**Project:** OmniGraph-Vault v3.4 RSS-KOL Alignment
**Domain:** Brownfield pipeline alignment — RSS arm catch-up to KOL full-body + multimodal standard
**Researched:** 2026-05-03
**Confidence:** HIGH (all claims grounded in source code at specific file:line; no web-search inferences)

---

## Executive Summary

OmniGraph-Vault's RSS pipeline currently produces structurally inferior knowledge-graph entries: summary-only text (200–500 chars) with no images, vs. the KOL arm which delivers full-body classification, Vision Cascade image descriptions, and 3072-dim multimodal chunk embeddings. The v3.4 milestone closes this gap across three waves. The research establishes that the right approach is a single shared cascade module (`lib/scraper.py`) consumed by both arms — not a parallel RSS-only scraper. This is because `batch_ingest_from_spider.py:940` is already broken (UA-only path, no cascade), and building Option A simultaneously fixes the Day-1 regression and the architectural divergence. The only new dependency is `trafilatura==2.0.0`; all other pipeline components (image_pipeline.py, lib/checkpoint.py, the Vision Cascade, LightRAG) are reused without modification.

The critical execution risk is not the scraper extraction itself — that is well-understood — but four interaction effects: DeepSeek rate limits detonating on the 1020-article backlog if throttle is not raised to 4.5s; legacy RSS summary-only docs silently short-circuiting re-ingest (LightRAG idempotency guard returns PROCESSED on existing doc IDs without updating content); orphaned NanoVectorDB vectors surviving an `adelete_by_doc_id` rollback; and the LightRAG `get_rag()` call order between the KOL and RSS subprocesses overwriting KOL vectors. All four are preventable with concrete code patterns identified in the research.

Two D-level decisions needed locking before Wave 1 begins. Both are now locked per domain consensus (2:1 on scraper scope) and user stated preference. See the Locked Decisions section.

---

## CRITICAL: Research Deltas and Conflicts

**These two items must be surfaced in every phase CONTEXT.md. Do not bury them.**

---

### Delta 1: D-RSS-SCRAPER-SCOPE — Researcher Conflict (LOCKED = Option A)

**The conflict:** Three of four research files (Architecture, Pitfalls, Features) independently recommend **Option A** (unified `lib/scraper.py`, both KOL and RSS arms use it). STACK.md recommends **Option B** (new `scrape_generic_url` function parallel to `scrape_wechat_ua`, KOL path untouched).

**Stack's reasoning for B:** "KOL sources are WeChat-only so there is no Day-1 regression risk." This reasoning is incorrect because it misses the pre-existing breakage context: `batch_ingest_from_spider.py:940` ALREADY calls `scrape_wechat_ua` (UA-only, no cascade), and this is the path that failed on Day-1 pre-flight article 1. KOL sources ARE WeChat — but WeChat under anti-abuse throttle consistently blocks UA-only calls, which is exactly why the full cascade (Apify → CDP → MCP → UA fallback) was built. Option B leaves a confirmed broken path untouched.

**Domain consensus (2:1 files explicitly recommend A; Stack's dissent rests on missed context):**
- Architecture (HIGH confidence): Option A — line 940 is the Day-1 article 1 fail bug, already broken
- Pitfalls CP-01 (Critical): Option A — Option B leaves "silent hollow-doc bomb" in 1020-backlog re-ingest
- Features: Option A — "fixes Day-1 KOL scrape bug" listed as key differentiator
- Stack: Option B — based on incorrect assumption that KOL path is not broken

**User stated preference:** Option A (stated 2026-05-03).

**LOCKED = Option A.** Implement `lib/scraper.py::scrape_url(url, site_hint)` as the shared abstraction. Patch `batch_ingest_from_spider.py:940` in Wave 1. KOL regression test is Wave 3 (already planned).

---

### Delta 2: D-STUCK-DOC-IDEMPOTENCY — Confidence Gap (LOCKED = CLI tool)

**The gap:** Architecture and Pitfalls both recommend a CLI tool (not cron pre-hook), but differ on confidence for one sub-claim.

**Architecture (HIGH confidence):** `adelete_by_doc_id` atomically cleans all 4 storage layers (kv_store_doc_status + kv_store_full_docs + VDB + Kuzu). LightRAG `shared_storage.py` uses asyncio.Lock (process-local, not file-system locks). A separate process calling `adelete_by_doc_id` is safe; it blocks on the pipeline lock during active `ainsert` but does NOT corrupt data.

**Pitfalls (MEDIUM confidence):** Flags that "whether NanoVectorDB vectors truly get cleaned needs a 30-minute spike against live LightRAG version." Specifically: CP-04 documents that `adelete_by_doc_id` may not remove vectors from NanoVectorDB if they were flushed before the timeout fired. Recommends CLI tool with active-process guard, NOT cron pre-hook.

**Both agree on:** CLI tool, not cron pre-hook. LightRAG self-heals FAILED docs on the next `ainsert` call (lightrag.py:1687-1735). A cron pre-hook would delete docs LightRAG would retry for free.

**LOCKED = CLI tool (`scripts/cleanup_stuck_docs.py`).** Wave 3 Task 1 should be a 30-minute diagnostic spike to confirm NanoVectorDB cleanup behavior against the live LightRAG version before writing the full CLI. This spike is cheap insurance against building a cleanup tool with incomplete coverage.

---

## Key Findings

### Recommended Stack

The stack delta for v3.4 is minimal by design. The entire new-dependency footprint is one package: `trafilatura==2.0.0`. It outperforms all alternatives (newspaper4k, goose3, readability-lxml) on the specific OmniGraph site mix (Substack, Medium, arXiv, HuggingFace blog, GitHub Blog, personal WordPress/Ghost). Key advantages: native Markdown output with code-fence preservation (PR #776, merged 2025-02-07), no system dependencies beyond lxml (already in stack), and actively maintained (HuggingFace, IBM, Microsoft Research are known users, 5.8k GitHub stars).

One known limitation: trafilatura's `MANUALLY_CLEANED` list strips `<figure>`, `<math>`, `<svg>`, and `<picture>` tags. For `arxiv.org/abs/*` URLs this means inline LaTeX is lost. Mitigation is URL routing: arXiv abstract → trafilatura for metadata, arXiv PDF → existing PyMuPDF path for full paper content. This routing table is implementable with `urllib.parse.urlparse` stdlib — `tldextract` is explicitly deferred.

**Stack additions:**

| Technology | Version | Purpose | Justification |
|------------|---------|---------|---------------|
| `trafilatura` | `>=2.0.0,<3.0` | Full-body extraction from non-WeChat HTML | Highest recall + precision for open-web article URLs; Markdown output native; code-fence support; actively maintained |

**Stack unchanged (zero changes required):**

| Component | Status |
|-----------|--------|
| `image_pipeline.py` | Zero changes — reused as-is by RSS arm |
| `lib/checkpoint.py` | Zero changes — flat `checkpoints/<hash>/` namespace works for RSS |
| `ingest_wechat.py` | Minor extraction only — `process_content` moves to `lib/scraper.py`; WeChat-specific functions stay |
| `requests`, `playwright`, `bs4`, `html2text` | Unchanged — consumed by new `lib/scraper.py` |
| LightRAG, kuzu, Cognee | Unchanged |

**Version compatibility note:** trafilatura 2.0 requires `lxml >= 5` and has an open incompatibility issue with `lxml >= 6`. Pin `lxml>=4.9,<6` in requirements.txt until resolved.

**Cascade layer order for `lib/scraper.py`:**

```
Layer 1: trafilatura UA fetch (PRIMARY — all non-WeChat URLs)
Layer 2: requests UA-spoofed fetch + trafilatura extract (SECONDARY)
Layer 3: CDP / MCP browser render (TERTIARY — Medium skip layers 1-2)
Layer 4: RSS summary fallback (LAST RESORT — flags as summary_only, not enriched=2)
```

Content quality gate: `len(text) >= 500` AND no login-wall keywords. HTTP 429 → exponential backoff (30s/60s/120s), not immediate cascade.

---

### Expected Features

**Table Stakes (must ship — failure makes v3.4 miss its success criteria):**

| Feature | Success Criterion |
|---------|-------------------|
| RSS full-body scrape via generic cascade | SC-1: full-body text required for classification |
| Full-body classification for RSS (`_build_fullbody_prompt` port) | SC-1: currently classifies on 200-char summary |
| Image download from scraped RSS body | SC-1: "图片语义可检索" requires images in graph |
| Vision Cascade description for RSS images | SC-1: reuse `image_pipeline.describe_images` — no new code |
| `localize_markdown` for RSS images | SC-1: Gemini Vision ingest requires localhost:8765 URLs |
| Multimodal `ainsert` replacing summary-only insert | SC-1: 479+ residual docs are text-only |
| Checkpoint system for RSS articles (5-stage) | SC-4: 1020-article backlog must be resumable |
| `stuck-doc` CLI cleanup tool | SC-6: deliberately fail + verify no contamination |
| E2E fixture `test/fixtures/rss_sample_article/` | SC-3: mandatory for CI regression |
| `aget_docs_by_ids` PROCESSED gate in rewritten rss_ingest.py | SC-6: D-19 pattern already in current code; must be preserved in rewrite |

**Should Have (differentiators — include based on effort budget):**

| Feature | Value | Condition |
|---------|-------|-----------|
| Option A: shared cascade for KOL `_classify_full_body` | Fixes Day-1 KOL scrape bug simultaneously | LOCKED = A (see Delta 1 above) |
| `rss_articles.body` column (SQLite) | Enables re-classify without re-scrape | ~10 lines; include in Wave 1 |
| Referer header in `download_images` for non-WeChat domains | Substack/Medium/HuggingFace CDN require it | Required for any non-WeChat image source |
| SVG filter in `download_images` | Prevents SiliconFlow circuit-breaker from opening on Arxiv batches | Required before any Arxiv RSS feeds processed |
| Kill-switch flag file in cron body | Fast rollback without editing cron | Low effort; include before cutover |
| Per-article progress logging (JSON lines) | Operational visibility for 1020-article batch | Low effort; include in Wave 2 |

**Anti-Features (explicitly excluded from v3.4):**

| Anti-Feature | Reason |
|--------------|--------|
| LLM-based body extraction | Tokens per article; hallucination risk on code; trafilatura is the right fallback |
| Site-specific CSS selectors per RSS source | Maintenance hell; selectors break on redesigns |
| EN→CN translation in RSS ingest | Doubles LLM cost; loses nuance; KOL arm does not translate; skip entirely in rewrite |
| Duplicate detection beyond URL hash | URL UNIQUE + LightRAG `filter_keys` is sufficient |
| Cron pre-hook for stuck-doc cleanup | LightRAG self-heals FAILED docs on next `ainsert`; cron pre-hook would delete retryable docs |
| Parallel/concurrent RSS article ingest | Fix correctness first; SiliconFlow quota management applies same as KOL |
| Zhihu 好问 enrichment | D-07 REVISED permanent exclusion — no exceptions |
| Option D RSS classifier batch refactor | Deferred; env cap `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP=500` is sufficient short-term |

---

### Architecture Approach

The architecture is a targeted extension of the existing KOL pipeline, not a redesign. One new file (`lib/scraper.py`, ~200 lines) extracts the cascade scraping logic from `ingest_wechat.py` and makes it callable by both arms. `enrichment/rss_ingest.py` is rewritten (~250 lines) to use the full 5-stage pipeline. `batch_ingest_from_spider.py` receives a surgical 8-line patch at line 940. `image_pipeline.py` receives zero changes. The checkpoint namespace is flat and shared — RSS articles use `checkpoints/<sha256-16>/<stage>` just like KOL articles, with one hash function migration required (MD5→SHA256 in `batch_ingest_from_spider.py:275`).

**Major components and their v3.4 changes:**

| Component | File | Change | Responsibility |
|-----------|------|--------|----------------|
| `lib/scraper.py` | NEW | ~200 lines | `scrape_url(url, site_hint)` → `ScrapeResult`; 4-layer cascade; URL routing; process_content (moved from ingest_wechat.py) |
| `enrichment/rss_ingest.py` | REWRITE | ~250 lines | RSS scrape → classify → image pipeline → LightRAG (mirrors KOL path) |
| `batch_ingest_from_spider.py` | PATCH | ~8 lines | Line 940: `scrape_wechat_ua` → `scrape_url(..., site_hint="wechat")` |
| `image_pipeline.py` | ZERO CHANGE | — | Image download + filter + Vision cascade (already source-agnostic) |
| `lib/checkpoint.py` | ZERO CHANGE | — | Per-article stage persistence; RSS uses same flat namespace |
| `scripts/cleanup_stuck_docs.py` | NEW | ~100 lines | CLI: `adelete_by_doc_id` for FAILED/PROCESSING docs; pipeline-busy guard |
| `rss_articles` (SQLite) | 5-col ALTER | DDL only | `body`, `body_scraped_at`, `depth`, `topics`, `classify_rationale` |

**Data flow for new RSS full-body path:**

```
orchestrate_daily.step_7_ingest_all
  └─ rss_ingest.run(max_articles)
       └─ per article:
            01. lib/scraper.scrape_url(url, "generic") → ScrapeResult
                └─ checkpoint: 01_scrape.html
            02. _build_fullbody_prompt + _call_deepseek_fullbody → depth/topics
                └─ write to rss_articles; checkpoint: 02_classify.json
            03. image_pipeline.download_images + filter_small_images
                └─ checkpoint: 03_images/manifest.json
            04. localize_markdown + LightRAG ainsert + PROCESSED gate
                └─ enriched=2 only on PROCESSED confirmation (D-19)
                └─ checkpoint: 04_text_ingest.done
            05. asyncio.create_task(_vision_worker_impl) [fire-and-forget]
                └─ describe_images → sub_doc ainsert
                └─ checkpoint: 05_vision/ (sub_doc_ingest)
       finally: _drain_pending_vision_tasks(); rag.finalize_storages()
```

**Key invariants preserved from KOL path:**
- Checkpoint writes: `.tmp` → `os.replace()` (atomic)
- Vision worker: fire-and-forget; text ingest never blocked
- `enriched=2`: only after `aget_docs_by_ids` confirms PROCESSED status
- `get_rag()`: called inside `main()`, not at module scope (prevents KOL vector overwrite)
- LightRAG instance: one shared instance per `run()` call with `finalize_storages()` in `finally`

**Schema migration (5 columns, Wave 1):**
```sql
ALTER TABLE rss_articles ADD COLUMN body TEXT;
ALTER TABLE rss_articles ADD COLUMN body_scraped_at TEXT;
ALTER TABLE rss_articles ADD COLUMN depth INTEGER;
ALTER TABLE rss_articles ADD COLUMN topics TEXT;
ALTER TABLE rss_articles ADD COLUMN classify_rationale TEXT;
```
SQLite `ADD COLUMN` with `DEFAULT NULL` is safe at any table size; 1020 existing rows return NULL until populated.

---

### Critical Pitfalls

**CP-01 (Critical — Wave 1 prevention): Cascade inverted — UA-only path silently survives KOL side**

If Wave 1 only wires RSS to the new cascade (Option B), `batch_ingest_from_spider.py:940` keeps UA-only. The Day-1 pre-flight already confirmed this path fails under WeChat anti-abuse throttle. Empty body passes through DeepSeek classifier (still returns JSON); hollow doc enters LightRAG; retrieval collapses. Warning sign: `batch_validation_report.json` shows `scrape_method_distribution.ua > 0` for KOL articles. Prevention: LOCKED = Option A, assert `body_chars_count > 200` before classifying.

**CP-02 (Critical — Wave 2 prevention): DeepSeek 15 RPM detonation on 1020-article backlog**

Current `THROTTLE_SECONDS=0.3` (200 RPM effective) was set for summary-only calls. Full-body at 8,000 chars/call hits the 15 RPM wall within 30 calls; DeepSeek returns 429; `rss_classify.py` silently skips articles with `depth_score=NULL`; they never pass depth gate 2; none of the 1020 articles get ingested. Prevention: `FULLBODY_THROTTLE_SECONDS=4.5` (60s/15RPM + 10% margin), exponential backoff on 429 (cap 60s, max 3 retries), run backlog in `--max-articles 100` increments.

**CP-03 (Critical — Wave 2+3 prevention): Duplicate doc insert silently skips full-body update**

Legacy summary-only docs already in LightRAG share the same `doc_id = f"rss-{article_id}"`. LightRAG's idempotency guard returns PROCESSED on existing IDs without re-inserting. Pipeline logs success; `enriched=2` is written; graph still contains the 3-sentence summary. Prevention: before Wave 3 backlog re-ingest, sample 10 legacy doc IDs via `aget_docs_by_ids` — if chunk_count=1 and text<500 chars, call `adelete_by_doc_id` before re-inserting. Add `UPDATE_MODE=true` env var to the rewritten `rss_ingest.py` that wraps the delete-before-insert pattern.

**CP-04 (Critical — Wave 2 prevention): Stuck doc leaves orphaned NanoVectorDB vectors**

`rss_ingest.py` currently has no `asyncio.wait_for` timeout wrapper. Any network hiccup during `ainsert` leaves a partial doc with no cleanup. Even with `adelete_by_doc_id`, NanoVectorDB vectors may survive if they were flushed before the timeout fired (Architecture=HIGH confidence; Pitfalls=MEDIUM confidence on VDB cleanup completeness — see Delta 2). Prevention: Wave 2 adds `asyncio.wait_for` + rollback pattern (`get_pending_doc_id` / `_clear_pending_doc_id`) identical to `batch_ingest_from_spider.py`. Wave 3 CLI tool includes a VDB orphan detection check.

**CP-05 (Critical — Wave 2 prevention): Vision drain missing — digest polluted by in-flight tasks**

Without `_drain_pending_vision_tasks()` before `finalize_storages()`, step_7 subprocess exits cleanly but Vision workers are still running when step_8 (digest) queries LightRAG. Sub-doc embeddings injected mid-query produce undefined behavior. Prevention: mirror the drain pattern from `batch_ingest_from_spider.py:94-138` in the `finally:` block of rewritten `rss_ingest.py`.

**MP-01 (Moderate — Wave 1): Substack/Medium/HuggingFace CDN requires Referer header**

`image_pipeline.download_images()` sends plain GET with no Referer. Non-WeChat CDNs return HTTP 403. Images silently skipped; text-only ingest. Prevention: pass `source_domain` from scraper to `download_images`; add `Referer: https://{source_domain}` header.

**MP-03 (Moderate — Wave 1): SVG from Arxiv/GitHub opens SiliconFlow circuit breaker**

PIL raises `UnidentifiedImageError` on SVG; fail-safe keep passes it to Vision as wrong MIME type; SiliconFlow HTTP 400 × 3 = circuit open; entire batch degrades. Prevention: add `.svg` to blocked-extension list in `download_images` before `requests.get`.

**MP-08 (Moderate — Wave 3 pre-flight): Checkpoint hash mismatch MD5 vs SHA256**

`batch_ingest_from_spider.py:275` uses `hashlib.md5[:10]`; `lib/checkpoint.py:get_article_hash` uses SHA256[:16]. Mixed-length checkpoint dirs; `checkpoint_reset.py` cannot find KOL article dirs. Prevention: migrate `batch_ingest_from_spider.py:275` to `from lib.checkpoint import get_article_hash` BEFORE the 1020-article backlog run. Warning sign: `ls checkpoints/` shows mixed 10-char and 16-char directory names.

---

## Locked Decisions

These decisions are locked based on domain consensus across research files. Write them into every phase CONTEXT.md verbatim.

| ID | Decision | Value | Evidence |
|----|----------|-------|----------|
| D-RSS-SCRAPER-SCOPE | Unified cascade for both KOL and RSS arms | **Option A** | Architecture+Pitfalls+Features 3:1; Stack's Option B rests on incorrect premise (line 940 is already broken); user stated preference A |
| D-STUCK-DOC-IDEMPOTENCY | Stuck-doc cleanup delivery form | **CLI tool** (`scripts/cleanup_stuck_docs.py`) — NOT cron pre-hook | Architecture+Pitfalls both agree; LightRAG self-heals FAILED docs on next `ainsert`; cron pre-hook would delete retryable docs |
| trafilatura scope | Only new external dependency | **trafilatura==2.0.0 only** — tldextract deferred | 6-domain routing table solvable with `urllib.parse`; no other new packages |
| image_pipeline.py scope | No changes to image pipeline | **Zero changes** | Module is already source-agnostic; RSS arm imports it directly |
| Checkpoint namespace | Flat shared vs RSS-specific subdirectory | **Flat/shared** `checkpoints/<hash>/` | `get_article_hash` SHA256[:16] is effectively unique across sources; subdirectory adds no benefit |
| rss_articles schema | New table vs columns on existing | **Add 5 columns to `rss_articles`** | No query benefit from a separate table; `ALTER TABLE ADD COLUMN NULL` is safe on SQLite at any size |
| Hash migration | Migrate KOL MD5 hash before backlog | **Before Wave 3 backlog run** | MP-08: mixed hash dirs make checkpoint tooling unreliable; must land in Wave 1 or Wave 3 Task 0 |

---

## Implications for Roadmap

### Wave 1: Generic Scraper Module + KOL Hot-Fix

**Rationale:** All downstream work (RSS rewrite, classifer, image pipeline calls) requires `scrape_url()` to exist. The KOL line-940 patch is a surgical 8-line change that closes the Day-1 failure mode permanently and costs almost nothing alongside the scraper extraction. This is the blocker for everything else.

**Delivers:**
- `lib/scraper.py` — `scrape_url(url, site_hint)` with 4-layer cascade and `ScrapeResult` dataclass
- `batch_ingest_from_spider.py:940` patched to call `scrape_url(..., site_hint="wechat")`
- `rss_articles` schema migration (5-column ALTER TABLE)
- Hash migration: `batch_ingest_from_spider.py:275` → `lib.checkpoint.get_article_hash`
- `download_images` enhancements: Referer header, SVG filter, base64 decoder, Content-Type check, max_dim resize

**Addresses table stakes:** RSS full-body scrape, image download groundwork
**Avoids:** CP-01 (cascade inverted), MP-01 (CDN Referer), MP-03 (SVG circuit breaker), MP-08 (hash mismatch)
**Research flag:** Standard patterns — scraper extraction and cascade are well-documented in the codebase; no additional research needed.

### Wave 2: RSS Full-Body Classify + Multimodal Ingest Rewrite

**Rationale:** Depends entirely on Wave 1 `scrape_url()`. All three sub-components (classify, image pipeline calls, LightRAG ingest) change simultaneously in `rss_ingest.py` — they share the same article object and cannot be split further without creating intermediate partial states. The drain call and timeout wrapper must ship in this wave, not Wave 3.

**Delivers:**
- `rss_classify.py` rewrite: `_build_fullbody_prompt` + `_call_deepseek_fullbody` port; `FULLBODY_THROTTLE_SECONDS=4.5`; 429 backoff
- `rss_ingest.py` full rewrite: scrape → classify → image pipeline → multimodal `ainsert` with PROCESSED gate
- `asyncio.wait_for` + rollback pattern in rss_ingest (CP-04 prevention)
- `_drain_pending_vision_tasks()` drain call in `finally:` block (CP-05 prevention)
- `get_rag()` called inside `main()`, not at module scope (MP-07 prevention)

**Uses:** `lib/scraper.py` (Wave 1), `image_pipeline.py` (unchanged), `batch_classify_kol._build_fullbody_prompt` (import)
**Avoids:** CP-02 (DeepSeek rate limit), CP-04 (stuck doc), CP-05 (digest pollution), MP-07 (KOL vector overwrite)
**Research flag:** Needs Wave 2 CONTEXT.md to specify `FULLBODY_THROTTLE_SECONDS=4.5` and the exact delete-before-insert pattern for CP-03.

### Wave 3: E2E Regression + Stuck-Doc Tool + Backlog Re-Ingest + Cron Cutover

**Rationale:** Only executable after Wave 2 is functional end-to-end. Task ordering within Wave 3 is constrained: (1) VDB cleanup spike first (Delta 2 resolution) → (2) CLI tool → (3) fixture → (4) joint KOL+RSS regression → (5) backlog in 50-100 article increments → (6) cron cutover. The stuck-doc tool and kill-switch must exist BEFORE the 1020-article backlog run.

**Delivers:**
- Wave 3 Task 1: 30-min diagnostic spike — confirm NanoVectorDB cleanup completeness in live LightRAG version (resolves Delta 2 confidence gap)
- `scripts/cleanup_stuck_docs.py` CLI tool: `--dry-run`, `--doc-id`, `--all-failed`, `--all-processing`, pipeline-busy guard
- Kill-switch flag file check in `register_phase5_cron.sh` (`~/.hermes/omnigraph_rss_pause`)
- `test/fixtures/rss_sample_article/` E2E fixture
- Joint KOL+RSS regression: 5 KOL + 5 RSS articles through `orchestrate_daily.step_7`
- 1020-article backlog re-ingest in `--max-articles 100` increments (delete-before-insert for legacy docs)
- `register_phase5_cron.sh` body cutover to `orchestrate step_7`

**Avoids:** CP-03 (duplicate doc insert), MP-08 (hash mismatch — must be done before backlog), MP-05 (cron overlap), MP-06 (no kill-switch)
**Research flag:** Wave 3 Task 1 (VDB cleanup spike) is the one remaining open question. 30 minutes against live LightRAG resolves it. Everything else is standard operations patterns.

### Phase Ordering Rationale

The three waves are sequentially dependent: Wave 1 unblocks Wave 2 (scrape_url must exist before rss_ingest.py can call it); Wave 2 unblocks Wave 3 (fixtures cannot exercise a path that doesn't work yet; backlog cannot run before delete-before-insert is implemented). The only Wave 3 work that can start in parallel with Wave 2 is `cleanup_stuck_docs.py` — it depends only on LightRAG source understanding (already complete), not on the new scraper.

**Execution window constraint:** Execute phase is blocked until Day-1/2/3 KOL cron baseline completes (~2026-05-04 → 2026-05-06 ADT). Research and planning phases can proceed; no code changes until baseline is confirmed stable.

### Research Flags

Research complete — all waves have established patterns:
- **Wave 1:** Standard refactoring patterns; scraper extraction and cascade well-documented in codebase; no additional research needed.
- **Wave 2:** `_build_fullbody_prompt` port is a direct copy from `batch_classify_kol.py:226-276`; LightRAG `ainsert` pattern is validated. No additional research needed. CONTEXT.md must specify `FULLBODY_THROTTLE_SECONDS=4.5`.
- **Wave 3:** One remaining open question (VDB cleanup spike, Delta 2) — budget 30 minutes as Task 1 before building the CLI tool.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | trafilatura v2.0.0 verified via GitHub releases API; source code inspection of `htmlprocessing.py`, `settings.py`, PR #776; all alternatives verified via their respective release APIs and open issue trackers |
| Features | HIGH | All feature analysis grounded in live source files at specific line numbers; `_build_fullbody_prompt` at `batch_classify_kol.py:226-310`, current `rss_classify.py:110-141`, `rss_ingest.py:148-207` |
| Architecture | HIGH | All integration points verified via direct source code read; LightRAG storage anatomy from `lightrag.py:660-737`, `1603-1733`, `3223-3441`; live SQLite schema confirmed |
| Pitfalls | HIGH | Derived from actual codebase + prior milestone post-mortems (STATE.md, CLAUDE.md, PROJECT.md); CP-01 through CP-05 each have specific file:line evidence. One MEDIUM sub-claim: NanoVectorDB cleanup completeness in CP-04 (Delta 2 — needs 30-min spike) |

**Overall confidence: HIGH**

### Gaps to Address

1. **NanoVectorDB cleanup completeness (Wave 3, Task 1):** Architecture (HIGH) says `adelete_by_doc_id` cleans all 4 storage layers including VDB. Pitfalls (MEDIUM) flags that vectors flushed before a timeout may survive. Resolution: 30-minute spike against live LightRAG version — create a test doc, timeout during `ainsert`, call `adelete_by_doc_id`, inspect `vdb_entities.json` before and after. Write the result into Wave 3 CONTEXT.md before building the CLI tool.

2. **Medium.com scraping reliability (MEDIUM confidence):** Stack research notes that UA+trafilatura succeeds "often" for free Medium articles but characterizes this as MEDIUM confidence (site policies change). Practical mitigation: RSS feeds from Medium only surface articles the author made public; if UA+trafilatura fails, the cascade falls to CDP/MCP. For v3.4, treat as acceptable given the fallback exists. Revisit if Medium becomes a primary RSS source.

3. **SiliconFlow vision quota for 1020-article backlog:** ~2,630 images at ¥0.0013/image = ~¥3.42 minimum. Budget ≥¥10 before starting. No research gap, just an operator pre-flight item.

---

## Sources

### Primary (HIGH confidence — direct source code inspection)

- `batch_ingest_from_spider.py:940` — KOL scrape-on-demand UA-only bug confirmed present
- `batch_classify_kol.py:226-276` — `_build_fullbody_prompt`, `_call_deepseek_fullbody` (port source)
- `enrichment/rss_ingest.py:148-207` — D-19 PROCESSED gate (must be preserved in rewrite)
- `enrichment/rss_ingest.py:243-244` — MD5 hash inconsistency confirmed (MP-08)
- `image_pipeline.py` (full) — no WeChat-specific logic; reusable as-is
- `lib/checkpoint.py:36-66` — SHA256 hash function, stage file map
- `venv/Lib/site-packages/lightrag/lightrag.py:1603-1733` — FAILED doc self-healing at `initialize_storages()`
- `venv/Lib/site-packages/lightrag/lightrag.py:3223-3441` — `adelete_by_doc_id` full delete contract
- `venv/Lib/site-packages/lightrag/kg/shared_storage.py:1-96` — asyncio.Lock semantics (process-local)
- `venv/Lib/site-packages/lightrag/kg/json_doc_status_impl.py:31-422` — FAILED/PROCESSING flush timing
- `data/kol_scan.db` — live SQLite schema confirmed for `rss_articles`, `articles`, `rss_classifications`
- trafilatura GitHub releases API — v2.0.0 confirmed 2024-12-03
- trafilatura source `htmlprocessing.py::_is_code_block()`, `settings.py::MANUALLY_CLEANED` — direct inspection
- trafilatura PR #776 merged 2025-02-07 — code-fence fix confirmed

### Secondary (HIGH confidence — GitHub issue tracking)

- newspaper4k open issues: "Medium.com `<section>` problems", "Silent failing on medium article"
- trafilatura open issue: "Incompatibility with `lxml` 6" (active as of 2026-05-03)
- goose3 v3.1.21 release notes — no Markdown output, no code block support confirmed

### Tertiary (MEDIUM confidence — community knowledge)

- Medium.com and Substack anti-bot assessment — site policies change; verified against known scraping community knowledge as of 2025

---

*Research completed: 2026-05-03*
*Ready for roadmap: yes — execute phase blocked until Day-1/2/3 baseline complete (~2026-05-06 ADT)*
