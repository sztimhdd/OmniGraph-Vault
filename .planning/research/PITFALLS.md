# Pitfalls Research

**Domain:** RSS-KOL Alignment — adding full-body scrape + multimodal ingest to OmniGraph-Vault v3.4
**Researched:** 2026-05-03
**Confidence:** HIGH (derived from actual codebase + prior milestone post-mortems documented in STATE.md, CLAUDE.md, PROJECT.md; not web-search inferences)

---

## Prologue: How to Read This Document

Each pitfall is classified by **severity** (Critical / Moderate / Minor) and **wave ownership** (Wave 1 / Wave 2 / Wave 3). The **warning signs** section gives concrete log patterns, file-state indicators, or metric thresholds — not vague advice. Recovery steps are ordered; do not skip steps.

This document is intentionally specific to THIS integration. Generic RAG pitfalls (e.g., "chunk overlap matters") are excluded.

---

## Critical Pitfalls

### CP-01: Cascade Inverted — UA-Only Path Silently Survives KOL Side After Wave 1 Extraction

**What goes wrong:**
Wave 1 extracts the generic scraper from `ingest_wechat.py` into a reusable module. If the extraction only wires RSS to the new cascade (A-option-B half-measure), the KOL `_classify_full_body` path at `batch_ingest_from_spider.py:940` keeps the old UA-only GET. Day-1 pre-flight already proved this path fails on WeChat articles under anti-abuse throttle. When Wave 3 re-ingests 1020 backlog articles through the KOL path, the scrape-on-demand leg silently returns empty `body` — classification succeeds with an empty string (DeepSeek still returns a JSON response), the article passes depth gate 2, and an empty-body doc enters LightRAG. Retrieval looks alive (doc count grows) but query quality collapses.

**Why it happens:**
The Project decision (D-RSS-SCRAPER-SCOPE) is explicitly open: A (cascade for both sides) vs B (RSS only). If the implementer picks B to reduce scope, the KOL scrape path keeps UA-only behavior that was already confirmed broken in Phase 10.

**How to avoid:**
Lock D-RSS-SCRAPER-SCOPE = A in the Wave 1 CONTEXT.md before writing a single line. The generic `scrape_url(url) -> ScrapeResult` function must be called from BOTH `rss_ingest.py` (Wave 2 rewrite) AND the `batch_ingest_from_spider.py:940` scrape-on-demand block. Add a `body_chars_count` field to the `ScrapeResult` dataclass and assert `body_chars_count > 200` before calling the classifier — reject articles where scrape returns fewer characters.

**Warning signs:**
- `batch_ingest_from_spider.py` log line: `"Scraping successful using method: ua"` (not `apify` or `cdp`) during KOL classification
- `classifications.body` in SQLite contains rows where `LENGTH(body) < 200` after a batch run
- `batch_validation_report.json` shows `scrape_method_distribution.ua > 0` for KOL articles

**Wave ownership:** Wave 1 prevention. If missed, Wave 3 regression will detect it (E2E fixture must assert non-empty body scrape).

**Recovery if already fired:**
1. `SELECT id, url, LENGTH(body) FROM articles WHERE LENGTH(body) < 200 AND enriched IS NOT NULL ORDER BY scanned_at DESC` — find affected articles.
2. `python scripts/checkpoint_reset.py --hash {hash}` for each — forces full re-scrape on next batch.
3. Re-run `batch_ingest_from_spider.py --from-db` with fixed cascade wired to KOL path.
4. For LightRAG docs already inserted with empty body: use stuck-doc cleanup tool (see CP-04) with `--doc-id-prefix wechat_` and `--min-chunk-chars 100` filter to identify hollow docs.

---

### CP-02: RSS Full-Body Classify Blows Through DeepSeek 15 RPM on 1020-Article Backlog

**What goes wrong:**
The current `rss_classify.py` has `THROTTLE_SECONDS = 0.3` and classifies summaries (short). When rss_ingest.py is rewritten to do full-body classify (porting Phase 10 `_build_fullbody_prompt` with `FULLBODY_TRUNCATION_CHARS=8000`), each call sends ~8,000 characters instead of ~200. At DeepSeek's 15 RPM free tier, the 1020-article backlog has 5 topics × 1020 articles = 5,100 calls. At 15 RPM that is 340 minutes of classify time — but the real problem is that `THROTTLE_SECONDS = 0.3` (200 RPM effective) will hit the 15 RPM wall within the first 30 calls. The `requests.post` call in `_call_deepseek` has `timeout=120` but no explicit rate-limit backoff. DeepSeek returns HTTP 429; `rss_classify.py` catches and `skip`s the article, logging `"classify failed"`. The batch completes with 4,800+ articles silently unclassified and depth_score=NULL, meaning they never pass the `depth_score >= 2` gate and are never ingested.

**Why it happens:**
`THROTTLE_SECONDS = 0.3` was set when the input was summaries, matching the RPM headroom. Full-body triples or quadruples prompt tokens; the same RPM budget covers far fewer calls per minute under DeepSeek's token-based rate limits (not purely request-count-based).

**How to avoid:**
In Wave 2 CONTEXT.md, set `FULLBODY_THROTTLE_SECONDS = 4.5` (60s / 15 RPM + 10% margin = 4.4s). Add exponential backoff on HTTP 429 (cap at 60s, max 3 retries) inside `_call_deepseek`. For the 1020-article backlog, run with `--max-articles 100` per batch invocation and space runs across the observation window. Do NOT run all 1020 in a single `rss_classify.py` invocation.

**Warning signs:**
- `rss_classify.py` log: `"classify failed"` appearing more than twice in the first 10 articles
- DeepSeek HTTP 429 responses in the classify log within the first 2 minutes
- `SELECT COUNT(*) FROM rss_classifications WHERE depth_score IS NULL` shows > 5% of processed articles after classify completes

**Wave ownership:** Wave 2 prevention (full-body prompt porting). Backlog execution is Wave 3.

**Recovery if already fired:**
1. `SELECT article_id FROM rss_classifications WHERE depth_score IS NULL` — identify unclassified articles.
2. `UPDATE rss_classifications SET depth_score = NULL WHERE article_id IN (...)` is NOT needed — NULL is already the indicator.
3. Fix `FULLBODY_THROTTLE_SECONDS` and backoff logic.
4. Re-run `rss_classify.py --max-articles 100` with 10-minute gaps between invocations.
5. Monitor: `SELECT COUNT(*) FROM rss_classifications WHERE depth_score IS NOT NULL AND depth_score >= 2` growing across runs.

---

### CP-03: Duplicate Doc Insert into LightRAG — RSS Backlog Collides With Legacy Summary Docs

**What goes wrong:**
The existing `rss_ingest.py` (pre-v3.4) inserts docs with `doc_id = f"rss-{article_id}"`. LightRAG's `ainsert` accepts `ids=[doc_id]`. If the same article was previously ingested as a summary-only doc (pre-v3.4), re-ingesting the full-body version reuses the same doc ID. LightRAG does NOT update/replace: it silently skips docs whose ID already exists in the KV store (the `PROCESSED` status check in LightRAG's `adelete_by_doc_id` path returns immediately on an existing ID). The backlog re-ingest reports "PROCESSED" success but the graph contains the old hollow summary-only content. Query retrieval returns fragments of the 3-sentence summary instead of the full technical article.

**Why it happens:**
`rss_articles.enriched` starts at 0 for legacy rows. The rewritten `rss_ingest.py` selects `WHERE enriched < 2` — correct — but LightRAG's own idempotency guard operates on doc IDs, not on the `enriched` column. LightRAG sees the existing doc and returns `PROCESSED` without re-inserting. The code reads the `PROCESSED` response, writes `enriched = 2`, and moves on. Both layers independently declared success; the graph is never updated.

**How to avoid:**
Before the Wave 3 backlog re-ingest, run `aget_docs_by_ids([f"rss-{article_id}"])` for a sample of 10 legacy articles and verify whether they exist in LightRAG and what their chunk count is. If chunk count is 1 and text length < 500 chars, the doc is summary-only. For the backlog run: call `rag.adelete_by_doc_id(f"rss-{article_id}")` BEFORE re-inserting. Wrap this delete-then-insert as an atomic pair in the rewritten `rss_ingest.py` when `UPDATE_MODE=true` env var is set.

**Warning signs:**
- After backlog re-ingest: `aget_docs_by_ids` for any article returns a single chunk < 300 chars
- `rss_articles.enriched = 2` but `SELECT chunk_count FROM ...` (via LightRAG query) shows 1 chunk per doc
- Synthesis query on an RSS topic returns 3-sentence answer despite full-body ingest supposedly completing

**Wave ownership:** Wave 3 prevention. Discovery check in Wave 2 (verify doc ID collision before writing the rewriter).

**Recovery if already fired:**
1. `SELECT id FROM rss_articles WHERE enriched = 2` — get all articles that reported success.
2. For each: call `rag.adelete_by_doc_id(f"rss-{id}")` via a one-off script.
3. `UPDATE rss_articles SET enriched = 0 WHERE id IN (...)` — reset the enriched flag.
4. Re-run `rss_ingest.py` with fixed delete-then-insert logic.
5. Verify: re-query LightRAG for sampled article IDs; expect chunk_count > 1.

---

### CP-04: Stuck Doc After LightRAG ainsert Timeout Leaves Vector/Graph Index Inconsistent

**What goes wrong:**
`ingest_article()` in `batch_ingest_from_spider.py` uses `asyncio.wait_for` with a computed timeout. On timeout, it calls `rag.adelete_by_doc_id(doc_id)` for rollback (D-09.05, STATE-02). LightRAG's `adelete_by_doc_id` is documented to remove the doc from KV and entity graph, but does NOT guarantee removal from NanoVectorDB if the embedding vectors were already flushed before the timeout fired. The result: entity graph and KV store say the doc is gone; the vector index still has orphaned embedding vectors. Future hybrid-mode queries (`aquery(mode="hybrid")`) will surface these orphaned vectors in the cosine-similarity top-K and mix them with real content — producing hallucinated graph neighbors that reference entities from the failed doc.

This risk is amplified for RSS ingest because `rss_ingest.py` currently does NOT use `asyncio.wait_for` + rollback at all (it has no timeout wrapper). Any network hiccup during the 5-7s `ainsert` call leaves a partial doc in LightRAG with no cleanup.

**Why it happens:**
LightRAG's NanoVectorDB flush is synchronous and happens inside `ainsert` as a side effect. `adelete_by_doc_id` was added later and operates on the abstract doc store, not directly on the vector file. This is a known LightRAG architectural gap.

**How to avoid:**
(1) In the rewritten `rss_ingest.py` (Wave 2), wrap `ainsert` in `asyncio.wait_for` with a budget computed by `_compute_article_budget_s(full_content)` — same formula used by `batch_ingest_from_spider.py`. Register the doc ID before `ainsert` via the same `get_pending_doc_id` / `_clear_pending_doc_id` pattern (STATE-02). (2) The stuck-doc cleanup tool (Wave 3 deliverable) must compare doc IDs present in NanoVectorDB's `vdb_entities.json` against doc IDs present in LightRAG's KV store — any vector-only entry (in VDB but not KV) is a stuck fragment. (3) Cleanup tool must run ONLY when the LightRAG process is not active (no concurrent `ainsert`); document this in the tool's `--help`.

**Warning signs:**
- `rag.adelete_by_doc_id` log: `"Rollback FAILED for doc_id=..."` — graph may be inconsistent
- `rss_ingest.py` exits with an unhandled `asyncio.TimeoutError` stack trace (no wrapper yet)
- After a batch: `python scripts/checkpoint_status.py` shows articles stuck at `text_ingest` stage indefinitely
- Synthesis queries return fragments beginning with `"Error describing image:"` — these are vision-failed sub-docs leaking into retrieval

**Wave ownership:** Wave 2 (add timeout + rollback to rss_ingest.py). Wave 3 (stuck-doc cleanup tool as CLI, not cron pre-hook, per D-STUCK-DOC-IDEMPOTENCY open question).

**Recovery if already fired:**
1. Stop all ingest processes. Do not run `rss_ingest.py` or `batch_ingest_from_spider.py` until cleanup completes.
2. Run stuck-doc cleanup tool: `python scripts/stuck_doc_cleanup.py --dry-run` to list candidates.
3. Compare output against `rss_articles` table: IDs that appear in VDB but NOT in `rss_articles.enriched = 2` are safe to purge.
4. `python scripts/stuck_doc_cleanup.py --confirm` — removes orphaned VDB entries.
5. Cross-check: run `rag.aquery("test")` and verify no `"Error describing image:"` fragments appear in top-K results.
6. Resume ingest.

---

### CP-05: Cron Cutover Digest Pollution — RSS Ingest Still In-Flight When Digest Generates

**What goes wrong:**
`orchestrate_daily.py` runs step_7 (ingest) → step_8 (digest) sequentially via `subprocess.run`. Step_7 calls `rss_ingest.py` which calls `rag.ainsert()` — synchronous from the subprocess perspective but the LightRAG Vision worker tasks are fire-and-forget (`asyncio.create_task`). When step_7's subprocess exits, pending Vision tasks may not have flushed their sub-docs to the graph. Step_8 (digest generation via `daily_digest.py`) then calls `rag.aquery()`. The digest may miss sub-doc embeddings that were still in-flight when step_7 exited, producing a partial-quality digest. Worse: if the Vision workers complete AFTER step_8 runs, the sub-doc embeddings are injected into the live graph mid-query — undefined behavior in LightRAG's in-memory vector index.

**Why it happens:**
`_drain_pending_vision_tasks()` exists in `batch_ingest_from_spider.py` and is called before `rag.finalize_storages()`. The rewritten `rss_ingest.py` (Wave 2) will need the same drain call. Without it, the subprocess exits cleanly but Vision workers are abandoned.

**How to avoid:**
In the rewritten `rss_ingest.py`, mirror the `_drain_pending_vision_tasks()` pattern from `batch_ingest_from_spider.py:94-138`. Call it in the `finally:` block before `rag.finalize_storages()`. Add an E2E assertion in the Wave 3 fixture: after `rss_ingest.py` exits, run `rag.aquery()` and verify that `provider_mix` from `get_last_describe_stats()` matches the image count in `rss_content/{hash}/`.

**Warning signs:**
- Step_8 digest contains article titles with missing image descriptions (description field shows `"Error describing image:"` or is absent entirely)
- `orchestrate_daily.py` step_7 log: no `"Vision tasks drained cleanly"` line before subprocess exit
- `daily_digest.py` runs but digest markdown contains fewer bullet points than expected for the day's ingest count

**Wave ownership:** Wave 2 (add drain to rss_ingest.py). Day-1/2/3 observation for residual leaks.

**Recovery if already fired:**
1. Do not re-run the digest for the affected day — it will query stale state.
2. Wait 10 minutes for Vision workers to have completed (they are still running in the background process table — check with `ps aux | grep rss_ingest`).
3. Run `python enrichment/daily_digest.py --date YYYY-MM-DD` directly to regenerate.
4. If Vision workers exited without completing: use stuck-doc cleanup (CP-04 recovery) then re-run `rss_ingest.py --article-id {id}` for the affected articles individually.

---

## Moderate Pitfalls

### MP-01: CDN Hot-Linking Blocked on Non-WeChat Sources — Silent Image Download Failure

**What goes wrong:**
`image_pipeline.download_images()` sends plain GET requests with no `Referer` header. WeChat CDN is permissive on CDN-hosted images. Substack, Medium, and HuggingFace CDNs require `Referer: {source_domain}` or return HTTP 403. The download returns HTTP 403; `download_images` logs `"Image N download failed: HTTP 403"` and silently skips. The article is ingested with no images. Filter stats show `download_failed > 0` but the pipeline does not fail — it proceeds with text-only ingest.

**How to avoid:**
In the Wave 1 generic scraper, extract the article's base domain alongside the image URLs. Pass `source_domain` to a new `download_images(urls, dest_dir, source_domain=None)` signature. When `source_domain` is set, add `"Referer": f"https://{source_domain}"` to the request headers. This is the correct fix: forge Referer to match the article's origin.

**Warning signs:**
- `image_batch_complete` JSON-lines event: `counts.download_failed > counts.input * 0.2` (more than 20% of images failing for a single article)
- Log line: `"Image N download failed: HTTP 403"` appearing for articles from Substack or Medium
- `checkpoint_status.py` shows articles completing `image_download` stage with 0 kept images despite the source article visibly containing images

**Wave ownership:** Wave 1 (generic scraper) — add Referer header to scraper's download step.

**Recovery:** Reset checkpoint for affected articles (`checkpoint_reset.py --hash {hash}`) after fixing the header. Re-run batch; images will be downloaded correctly on next pass.

---

### MP-02: Base64-Embedded Images Bypass `download_images` Entirely

**What goes wrong:**
Some RSS sources (particularly GitHub-hosted documentation and certain personal blogs) embed images as `data:image/png;base64,...` inline in the HTML. BeautifulSoup + html2text preserves these in the Markdown output as `![](data:image/png;base64,AAAA...)`. `download_images()` iterates image URLs; URLs beginning with `data:` are passed to `requests.get()` which raises a `MissingSchema` exception. The exception handler logs a warning and skips. The base64 blob is NOT passed to Vision. The Markdown text that gets LightRAG-inserted contains the raw `data:` string (hundreds of KB of base64 noise) which inflates chunk count, confuses entity extraction, and can cause `ainsert` to time out on what should be a short article.

**How to avoid:**
In `download_images()` (or the pre-processing step in the generic scraper), add a filter: if URL starts with `data:image/`, decode the base64, write to a temp file in `dest_dir`, and return the local path directly — bypassing the HTTP GET entirely. Strip the `data:...` blob from the Markdown before inserting into LightRAG. Add a `base64_images_decoded` counter to `FilterStats`.

**Warning signs:**
- `requests.get(url)` raises `requests.exceptions.MissingSchema` — appears as `"Image N error: Invalid URL..."` in pipeline logs
- `final_content.md` files containing `data:image/` substrings (visible via `grep -l "data:image" ~/.hermes/omonigraph-vault/rss_content/*/final_content.md`)
- `ainsert` timeout on an article that should be < 5KB of meaningful text (chunk count unexpectedly high)

**Wave ownership:** Wave 1 (generic scraper) — add base64 decoder in `download_images`.

**Recovery:** Reset checkpoint for affected articles, apply fix, re-run.

---

### MP-03: SVG Images Crash PIL in `filter_small_images`

**What goes wrong:**
Arxiv papers and GitHub READMEs frequently use SVG for diagrams. `filter_small_images()` calls `PILImage.open(path)` on every downloaded image. PIL does not support SVG — `PIL.UnidentifiedImageError` is raised. The current code handles this in the `except Exception` branch with `size_read_failed += 1` and KEEPS the image (fail-safe behavior per D-08.01). The image is then passed to `describe_images()`. `describe_images()` sends it as `mime="image/jpeg"` (wrong MIME type) to SiliconFlow. SiliconFlow returns HTTP 400 (invalid image format). This counts as a circuit-breaker failure — after 3 SVGs in a row, the SiliconFlow circuit opens and the entire cascade degrades to OpenRouter-primary for the rest of the batch.

**How to avoid:**
Before calling `requests.get(url)`, check if the URL ends in `.svg` or the response `Content-Type` is `image/svg+xml`. Skip SVG downloads entirely (log as `outcome=filtered_svg`) or, if the svg2png conversion library is available (`cairosvg`), convert before saving. The simpler approach is to add `.svg` to a blocked-extension list in `download_images`.

**Warning signs:**
- `describe_images` log: `"SiliconFlow HTTP 400"` appearing 3+ times in rapid succession
- `cascade.status["siliconflow"]["circuit_open"] == True` after processing an Arxiv article
- `batch_validation_report.json`: `circuit_opens: ["siliconflow"]` present after a short batch that should not have triggered the circuit

**Wave ownership:** Wave 1 (generic scraper) — add SVG filter to `download_images`.

**Recovery:** Remove SVG files from affected checkpoint dirs. `python scripts/checkpoint_reset.py --hash {hash}` on articles where the circuit opened. Reset the circuit breaker state file (`provider_status.json` in the VisionCascade checkpoint dir) by deleting it. Re-run batch.

---

### MP-04: High-Resolution Images Blow Vision Token Budget and Trigger 429

**What goes wrong:**
`filter_small_images` filters images with `min(w, h) < 300`. This correctly discards icons and thumbnails but KEEPS all large images — including 4K screenshots (3840×2160) and HuggingFace model card diagrams (often 6000+ pixels). SiliconFlow's Qwen3-VL-32B processes the full image at full resolution; a 4K image uses ~1,500–2,000 vision tokens vs. ~300 for a typical 800×600 screenshot. On a batch of 10 high-res images, the vision token consumption spikes 5× the estimate, exhausting the per-minute vision token quota and triggering cascading 429s even when SiliconFlow balance is adequate.

**How to avoid:**
Add a `max_dim` downscale step in `filter_small_images` (or as a separate `resize_images` step): if `max(w, h) > 1920`, resize to `max_dim=1920` using `PIL.Image.thumbnail((1920, 1920))` before saving. This is a lossy operation but acceptable for a knowledge graph (description quality is nearly identical for diagrams at 1920 vs. 4K). Add `resized_count` to `FilterStats`.

**Warning signs:**
- `image_pipeline.py` logs: `"SiliconFlow HTTP 429"` appearing mid-batch despite adequate balance
- `get_last_describe_stats()["gemini_share"] > 0.05` after a batch with only 5-10 images
- Per-image `ms` in `image_processed` JSON-lines events > 8,000ms for some images (high-res processing time)

**Wave ownership:** Wave 1 (generic scraper) — add resize step to `image_pipeline.filter_small_images` or as a new `resize_for_vision` function.

**Recovery:** No immediate data impact (failed images get error descriptions). Reset circuit breaker state. For already-processed articles with degraded image descriptions, reset checkpoint to `image_download` stage and re-run.

---

### MP-05: Race Condition Between `rss_classify.py` Write and `rss_ingest.py` Read on Same Batch Day

**What goes wrong:**
`orchestrate_daily.py` runs step_2 (rss_classify) then step_7 (rss_ingest) sequentially. However, `rss_classify.py` writes `depth_score` rows to `rss_classifications` via individual `INSERT OR REPLACE` statements — no transaction wrapping the entire batch. If `rss_classify.py` is still running (e.g., throttled mid-batch by the 4.5s/call rate limiter), AND the cron for `rss_ingest.py` fires early (manual trigger, cron overlap), `rss_ingest.py` may read a partially-classified `rss_classifications` table. Articles that have not yet been classified have `depth_score = NULL` and are excluded by the `depth_score >= 2` gate — correct behavior. BUT articles classified in a previous call within the same session may have stale `depth_score` from a prior run if the classifier's `INSERT OR REPLACE` is mid-transaction. The result: non-deterministic article selection across overlapping runs.

**How to avoid:**
`rss_classify.py` already writes per-article (no batch transaction). The real guard is: `orchestrate_daily.py`'s cron bodies must be serialized. Check `scripts/register_phase5_cron.sh` cron schedules — `rss-classify` and `daily-ingest` jobs must have non-overlapping windows with at least 30 minutes between them. Add a lock file (`/tmp/omnigraph_pipeline.lock`) in `orchestrate_daily.py` step_2 and step_7 using `fcntl.flock` (Linux) or equivalent.

**Warning signs:**
- `orchestrate_daily.py` logs: step_2 and step_7 subprocess start times overlap (step_7 start < step_2 finish)
- `SELECT COUNT(*) FROM rss_classifications WHERE date(created_at) = date('now') AND depth_score IS NULL` is non-zero after step_7 reports "ingest complete"

**Wave ownership:** Wave 3 (cron cutover validation). Check during Day-1/2/3 observation window.

**Recovery:** Re-run `rss_classify.py` to complete the partial batch, then re-run `rss_ingest.py --max-articles 50` to pick up newly-classified articles.

---

### MP-06: Kill-Switch Missing for Fast Cron Rollback

**What goes wrong:**
After `register_phase5_cron.sh` body cutover to `orchestrate_daily.py step_7`, if RSS ingest begins producing corrupt LightRAG state (orphaned vectors, malformed chunks), there is no documented fast rollback. The operator must manually edit the cron body or delete the cron job. Hermes's cron management UI (`hermes cronjob list`) supports deletion but not atomic swap. Under incident pressure, manual editing of a cron body with correct escaping is error-prone.

**How to avoid:**
In `register_phase5_cron.sh`, add a flag check at the TOP of the cron body: `if [ -f ~/.hermes/omnigraph_rss_pause ]; then echo "RSS ingest paused via flag file"; exit 0; fi`. This creates a kill-switch: `touch ~/.hermes/omnigraph_rss_pause` instantly pauses RSS ingest without touching the cron schedule. Document this kill-switch in `docs/OPERATOR_RUNBOOK.md`.

**Warning signs:**
- Any of the Critical Pitfalls above have fired in production
- `daily_digest.py` Telegram message quality drops (query returns fragments)
- Step_7 exit code != 0 on two consecutive cron fires

**Wave ownership:** Wave 3 (cron cutover). Add kill-switch before cutover, not after.

**Recovery:** `touch ~/.hermes/omnigraph_rss_pause` — RSS arm stops within the next cron fire. Then diagnose at leisure.

---

### MP-07: `rss_ingest.py` Uses Separate `get_rag()` Call — Shares No State With KOL Ingest

**What goes wrong:**
`batch_ingest_from_spider.py` creates a single LightRAG instance via `get_rag(flush=True)` and passes it to all article ingest calls. `rss_ingest.py` (current) calls `get_rag()` independently. When `orchestrate_daily.py step_7` runs BOTH in sequence via subprocess, each creates its own LightRAG instance pointing to the same `RAG_WORKING_DIR`. LightRAG's NanoVectorDB loads the entire `vdb_entities.json` file into memory at init. If KOL ingest writes new vectors to `vdb_entities.json` and exits (calling `finalize_storages`), then RSS ingest loads a STALE in-memory snapshot (its `get_rag()` was called before KOL wrote), proceeds to insert RSS vectors, and on `finalize_storages` OVERWRITES the KOL-written vectors with its stale-plus-new snapshot. KOL entities ingested in the same day are lost.

**Why it happens:**
Each subprocess creates its own Python process with its own `get_rag()` call. Since they run sequentially (not concurrently), the snapshot staleness depends on timing. If KOL ingest took 30+ minutes and RSS ingest's `get_rag()` was called at subprocess start, the in-memory state is 30+ minutes stale at the time of RSS finalize.

**How to avoid:**
Ensure `rss_ingest.py` calls `get_rag(flush=True)` AFTER its `main()` starts (not at module import) so it loads the post-KOL state. The subprocess model already ensures sequential execution — the guard is: `rss_ingest.py` must NOT cache the `rag` instance at module scope. Verify with `grep -n "get_rag" enrichment/rss_ingest.py` — it must appear only inside `async def main()` or the ingest loop, not at module top level.

**Warning signs:**
- KOL entity count in LightRAG DECREASES after a day when both KOL and RSS ran
- `rag.aquery("recent KOL article topic")` returns empty or reduced results after RSS ingest ran
- `vdb_entities.json` file modification time is AFTER `batch_ingest_from_spider.py` exit but the file size is SMALLER than after the KOL run

**Wave ownership:** Wave 2 (rss_ingest.py rewrite) — confirm `get_rag()` is called inside `main()`, not at module scope.

**Recovery:** If KOL vectors are overwritten: the only clean recovery is to re-run KOL ingest (`batch_ingest_from_spider.py --from-db`) for articles from the affected day. Checkpoint data for KOL articles should still exist (they completed `text_ingest` stage) so the batch will skip scrape/classify stages and only redo the `ainsert` + vector write.

---

### MP-08: Checkpoint Hash Mismatch Between KOL (MD5) and RSS (SHA256)

**What goes wrong:**
`batch_ingest_from_spider.py` computes `article_hash = hashlib.md5(url.encode()).hexdigest()[:10]` (line 275). `lib/checkpoint.py:get_article_hash()` uses SHA256 first-16-hex-chars. `rss_ingest.py` will call `get_article_hash(url)` via `lib.checkpoint`. The checkpoint directory for a given article URL differs depending on which script created it. If a KOL article was partially ingested via `batch_ingest_from_spider.py` (MD5 hash checkpoint exists) and then someone tries to reset it using `checkpoint_reset.py --hash {sha256_hash}`, the tool reports "no checkpoint dir found" because it looks for the SHA256 path. The MD5-based checkpoint remains and is never cleaned up.

**Why it happens:**
Two separate hash functions for the same conceptual "article identity." The MD5 path is in `batch_ingest_from_spider.py` inline code predating `lib/checkpoint.py`; the SHA256 path is the newer canonical implementation.

**How to avoid:**
During Wave 1 or the start of Wave 3, audit `batch_ingest_from_spider.py` line 275 and migrate to `from lib.checkpoint import get_article_hash`. Make the change in ONE commit with a `# MIGRATION: was hashlib.md5` comment. Update the corresponding test in `tests/unit/test_batch_ingest.py`. This must happen BEFORE the backlog re-ingest so all 1020 articles use consistent hash paths.

**Warning signs:**
- `checkpoint_reset.py --hash {hash}` returns exit 1 "no checkpoint dir found" even though the article failed and should have a checkpoint
- `ls ~/.hermes/omonigraph-vault/checkpoints/` shows 10-char dirs (MD5) alongside 16-char dirs (SHA256) — mixed lengths are the indicator
- `checkpoint_status.py` shows fewer articles than the actual `batch_ingest_from_spider.py` log indicated were processed

**Wave ownership:** Wave 3 (pre-backlog-run) — audit and migrate BEFORE running the 1020 backlog.

**Recovery:** Manual: list `~/.hermes/omonigraph-vault/checkpoints/` — 10-char dirs are MD5-based. For each orphaned checkpoint, identify the URL from the article in SQLite by `articles.hash` column, re-compute SHA256 hash, rename the dir. Script this to avoid manual errors.

---

## Minor Pitfalls

### mP-01: `langdetect` Misclassifies Short Titles as Wrong Language

**What goes wrong:**
`rss_ingest.py` calls `langdetect.detect(body)` on the full article body. If the article body is very short (< 100 chars — newsletter-style articles with a teaser body in the RSS feed), `langdetect` returns unreliable results and may misclassify an English article as Spanish or Indonesian. The article is then skipped (`log + skip`) and never ingested.

**How to avoid:**
Add a `len(body) < 100` check before `langdetect.detect()`. For articles with body below this threshold, default to translation (DeepSeek translate call) — a spurious translate-to-Chinese of an already-Chinese article is harmless; a missed article is not.

**Warning signs:**
- `rss_ingest.py` log: `"language detection failed"` or `"unexpected language: es"` for articles from English-language AI newsletters

**Wave ownership:** Wave 2 (rss_ingest.py rewrite).

---

### mP-02: `rss_classify.py` CLASSIFY_PROMPT Content Truncation Clips Chinese Articles Incorrectly

**What goes wrong:**
The current `rss_classify.py` passes `content = {content}` with no truncation. When Wave 2 ports the `FULLBODY_TRUNCATION_CHARS=8000` limit from Phase 10, the truncation slices at a byte index. For UTF-8 Chinese text, slicing at byte 8000 may split a multi-byte character, producing a `\xef\xbf\xbd` replacement character in the prompt. DeepSeek returns a valid JSON response but `reason` field may contain garbled characters — not a crash but corrupted data in `rss_classifications.rationale`.

**How to avoid:**
Truncate at character (not byte) level: `content[:8000]` in Python operates on Unicode codepoints, not bytes, so this is safe as long as the variable holds a Python `str` (not `bytes`). Confirm the `body` column read from SQLite is decoded as `str` before truncation. Add `assert isinstance(body, str)` before the truncation call.

**Warning signs:**
- `rss_classifications.rationale` contains `�` replacement characters
- DeepSeek API logs show prompts with `?` clusters in the content field

**Wave ownership:** Wave 2 (porting fullbody prompt).

---

### mP-03: Images Behind Auth (Notion/Confluence Embeds) Silently Download Redirect Pages

**What goes wrong:**
Some embedded images in technical blog posts (embedded via Notion, Confluence, or corporate wikis) return HTTP 302 to a login page when fetched without auth. `requests.get(url, timeout=10)` follows redirects by default. The final response is HTTP 200 (the login page HTML). `path.write_bytes(resp.content)` writes the HTML. PIL raises `UnidentifiedImageError` in `filter_small_images` — the image is kept (fail-safe) and passed to Vision as a "JPEG." SiliconFlow returns HTTP 400 or a description like "This appears to be a login page." This wastes a SiliconFlow credit and creates noise in the entity graph.

**How to avoid:**
In `download_images()`, check `resp.headers.get("Content-Type", "")` before writing. If Content-Type is `text/html`, treat as a download failure and log `outcome=blocked_auth_redirect`. Do not write the file. This adds one line to the existing download loop.

**Warning signs:**
- Vision descriptions containing "login page", "sign in", or "authentication required"
- `filter_small_images` showing high `size_read_failed` counts for articles from Notion-hosted blogs

**Wave ownership:** Wave 1 (generic scraper, `download_images` enhancement).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep MD5 hash in `batch_ingest_from_spider.py` (not migrate to lib.checkpoint SHA256) | No migration risk | Checkpoint tool can't reset KOL articles; mixed-length dirs confuse operators | Never — fix before backlog run |
| Classify RSS with summary (not full body) during backlog to save DeepSeek quota | Batch completes fast | ~60% of articles get depth_score=1 incorrectly; low-quality articles enter LightRAG | Never — defeats the point of v3.4 |
| Skip drain in rss_ingest.py (rely on step timing) | Simpler code | Vision sub-docs race with digest generation; digest quality non-deterministic | Never |
| Run 1020-article backlog in single batch without --max-articles cap | One command | DeepSeek 429 kills entire batch; LightRAG vector overwrite risk | Never — always use --max-articles 100 |
| Use B-option for D-RSS-SCRAPER-SCOPE (RSS only, not KOL) | Less regression risk | KOL scrape-on-demand path stays broken; Wave 3 KOL regression required anyway | Only if KOL regression is explicitly deferred to a separate milestone in STATE.md |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| DeepSeek + full-body RSS | Keep `THROTTLE_SECONDS=0.3` from summary-era | Set `FULLBODY_THROTTLE_SECONDS=4.5`; add 429 backoff in `_call_deepseek` |
| Substack/Medium CDN | Plain GET without Referer | Pass `source_domain` to `download_images`; set `Referer: https://{domain}` |
| LightRAG NanoVectorDB | Call `get_rag()` at module scope in `rss_ingest.py` | Call `get_rag(flush=True)` inside `main()` after KOL subprocess completes |
| SiliconFlow + SVG files | SVG passes PIL filter (fail-safe keep) and triggers 429 | Filter `.svg` extensions before `requests.get` in `download_images` |
| Checkpoint tool + KOL MD5 hashes | Run `checkpoint_reset.py --hash {sha256}` for KOL article | Migrate KOL hash to `lib.checkpoint.get_article_hash` before backlog run |
| `rss_articles` backlog + LightRAG doc IDs | Re-insert without deleting: old doc silently skips | Delete existing doc via `rag.adelete_by_doc_id` before re-insert in backlog mode |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-body classify without rate limiter | DeepSeek 429 on first 20 articles | `FULLBODY_THROTTLE_SECONDS=4.5` + backoff | First batch attempt after Wave 2 if not fixed |
| LightRAG init per-subprocess in sequential cron | KOL vectors overwritten by RSS re-load | `get_rag()` inside `main()`, not module scope | Any day when both KOL and RSS run via step_7 |
| High-res images (>1920px) in Vision cascade | SiliconFlow 429 despite adequate balance | Resize to max_dim=1920 before Vision | Arxiv/GitHub batches with diagram-heavy articles |
| 1020-article backlog as single run | DeepSeek exhausted; 6-hour ingest window blocks live retrieval | `--max-articles 100` per run; stagger over 5 days | Single-command full backlog run |

---

## "Looks Done But Isn't" Checklist

- [ ] **rss_ingest.py rewrite:** Verify `asyncio.wait_for` + rollback pattern present — grep for `asyncio.wait_for` and `_clear_pending_doc_id` in the new file
- [ ] **rss_ingest.py rewrite:** Verify `_drain_pending_vision_tasks()` called in `finally:` block before `finalize_storages()`
- [ ] **Generic scraper:** Verify `Referer` header set for non-WeChat domains — test with a live Substack URL
- [ ] **KOL path:** Verify `get_article_hash` from `lib.checkpoint` replaces inline MD5 — `grep "hashlib.md5" batch_ingest_from_spider.py` must return 0 matches
- [ ] **Backlog re-ingest:** Verify delete-before-reinsert present for legacy RSS doc IDs — run `aget_docs_by_ids` sample on 3 legacy articles before batch
- [ ] **Cron cutover:** Verify kill-switch flag file check at top of cron body — `grep "omnigraph_rss_pause" scripts/register_phase5_cron.sh` must match
- [ ] **Stuck-doc cleanup tool:** Verify it checks for active ingest process before running — tool must fail with clear message if `rss_ingest.py` or `batch_ingest_from_spider.py` is in the process table
- [ ] **SVG filter:** Verify `.svg` URL extension blocked in `download_images` — test with `https://raw.githubusercontent.com/*/diagram.svg`

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| CP-01: Hollow KOL docs from UA-only scrape | HIGH | Identify hollow docs via chunk count; reset checkpoints; re-scrape with fixed cascade |
| CP-02: DeepSeek 429 kills backlog classify | LOW | Fix throttle; re-run with `--max-articles 100`; no data loss (failed rows stay NULL) |
| CP-03: Duplicate doc insert skips full-body | MEDIUM | Delete legacy doc IDs; reset `enriched=0`; re-run rss_ingest |
| CP-04: Stuck doc / orphaned vectors | HIGH | Stop all ingest; run stuck-doc cleanup tool; resume batch |
| CP-05: Digest polluted by in-flight Vision | LOW | Wait 10min; regenerate digest via `--date` flag |
| MP-01: Substack images HTTP 403 | LOW | Reset checkpoint; fix Referer header; re-run |
| MP-07: KOL vectors overwritten by RSS | HIGH | Re-run KOL ingest for affected day; checkpoint data preserved |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Wave | Verification |
|---------|-----------------|--------------|
| CP-01: Cascade inverted on KOL path | Wave 1 (D-RSS-SCRAPER-SCOPE = A) | E2E fixture: assert `scrape_method != "ua"` for WeChat articles |
| CP-02: DeepSeek 429 on full-body classify | Wave 2 (throttle + backoff) | Dry-run classify on 20 backlog articles; verify no 429s |
| CP-03: Duplicate doc insert | Wave 2 (delete-before-insert) + Wave 3 (backlog) | Sample 3 legacy doc IDs; confirm chunk count > 1 after re-ingest |
| CP-04: Stuck doc / orphaned vectors | Wave 2 (add timeout+rollback to rss_ingest.py) | Deliberately fail an ingest; run cleanup tool; verify no orphans |
| CP-05: Digest pollution from Vision drain | Wave 2 (add drain call) | Assert `"Vision tasks drained cleanly"` in step_7 log |
| MP-01: CDN hot-linking | Wave 1 (Referer header) | Test download_images with Substack URL |
| MP-02: Base64 images | Wave 1 (base64 decoder) | Test with a GitHub README article |
| MP-03: SVG crash | Wave 1 (SVG filter) | Test with Arxiv HTML article containing SVG |
| MP-04: High-res 429 | Wave 1 (resize step) | Test with 4K screenshot article; verify no SiliconFlow 429 |
| MP-06: No kill-switch | Wave 3 (before cutover) | `touch ~/.hermes/omnigraph_rss_pause`; verify next cron fires but skips RSS |
| MP-07: get_rag() scope | Wave 2 (rss_ingest.py rewrite) | `grep "get_rag" enrichment/rss_ingest.py` — must appear only inside `main()` |
| MP-08: Hash mismatch | Wave 3 (pre-backlog migration) | `ls ~/.hermes/omonigraph-vault/checkpoints/ | awk '{print length($0)}'` — all must be 16 |

---

## Sources

- `batch_ingest_from_spider.py` — D-09.05 (STATE-02) rollback pattern; lines 275, 291-314
- `lib/checkpoint.py` — SHA256 hash implementation; stage ordering
- `lib/vision_cascade.py` — CASC-01..06 circuit breaker thresholds
- `image_pipeline.py` — download_images, filter_small_images, describe_images cascade
- `enrichment/rss_ingest.py` — current summary-only path, no timeout/rollback wrapper
- `enrichment/rss_classify.py` — `THROTTLE_SECONDS=0.3`, single-topic classify loop
- `enrichment/orchestrate_daily.py` — step_7 sequential KOL+RSS, step_8 digest
- `.planning/PROJECT.md` — open decisions D-RSS-SCRAPER-SCOPE, D-STUCK-DOC-IDEMPOTENCY, v3.4 wave plan
- `.planning/STATE.md` — Phase 9/10/11 decision log; MD5 hash inline at batch_ingest_from_spider.py:275
- `CLAUDE.md` — Checkpoint mechanism, Vision Cascade, Known Limitations sections

---
*Pitfalls research for: OmniGraph-Vault v3.4 RSS-KOL Alignment*
*Researched: 2026-05-03*
