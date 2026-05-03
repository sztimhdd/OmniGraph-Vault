# Architecture Research: v3.4 RSS-KOL Alignment

**Domain:** Pipeline integration — RSS full-body ingestion aligned with existing KOL pipeline
**Researched:** 2026-05-03
**Confidence:** HIGH (all claims grounded in source code at specific file:line)

---

## D-Level Decisions (LOCKED)

### D-RSS-SCRAPER-SCOPE: RECOMMENDATION = Option A (Unified Cascade)

**Decision:** Implement one generic URL scraper with full cascade as the shared module.
Both `_classify_full_body` in `batch_ingest_from_spider.py` (KOL) and the rewritten
`rss_ingest.py` (RSS) call it. The UA-only bug at line 940 of `batch_ingest_from_spider.py`
is fixed as a side effect.

#### Evidence

The bug is present and documented in the codebase. `batch_ingest_from_spider.py:940`:

```python
scraped = await ingest_wechat.scrape_wechat_ua(url)
```

This calls `scrape_wechat_ua` directly — a WeChat-specific UA-rotation scraper
(`ingest_wechat.py:415`). WeChat blocks UA scraping routinely (the function itself has
a `_ua_cooldown()` rate limiter baked in). The Day-1 pre-flight article-1 failure was
this call path. The full cascade (Apify → CDP → MCP → UA fallback) is implemented in
`ingest_article` but is not exposed as a standalone function.

**Option A concrete cost analysis:**

| Work item | Files touched | Est. diff lines |
|-----------|--------------|-----------------|
| Extract `scrape_url(url, site_hint) -> ScrapeResult` from `ingest_wechat.py` | `ingest_wechat.py`, new `lib/scraper.py` | ~120 add, ~30 delete |
| Wire KOL `_classify_full_body` (line 940) to use `scrape_url` | `batch_ingest_from_spider.py` | ~8 lines changed |
| Rewrite `rss_ingest.py` to use `scrape_url` | `enrichment/rss_ingest.py` | ~150 lines changed |
| Non-WeChat site adaptations (RSS: Substack, Medium, arXiv) | `lib/scraper.py` | ~40 add |
| Wave 3 E2E regression: KOL + RSS joint | test fixture addition | ~60 lines |
| **Total** | 4 files modified, 1 new | **~380 lines** |

**Option B concrete cost analysis:**

| Work item | Files touched | Est. diff lines |
|-----------|--------------|-----------------|
| New RSS-only scraper | `enrichment/rss_scraper.py` (new) | ~120 add |
| Rewrite `rss_ingest.py` to use it | `enrichment/rss_ingest.py` | ~150 lines |
| KOL bug persists | none | 0 (bug remains) |
| **Total** | 1 file modified, 1 new | **~270 lines** |

Option B is 110 lines smaller upfront but leaves the KOL scrape-on-demand path broken.
The next KOL batch where an article has no body will reproduce the same failure. Option A
costs ~110 extra lines now to close both failure modes simultaneously. The regression
surface is bounded: the only KOL call site is the single `scrape_wechat_ua` call at
`batch_ingest_from_spider.py:940`; the Wave 3 regression test exercises both arms.

**Maintenance burden:** Two separate scrapers (Option B) diverge over time. Any future
cascade provider change (e.g., adding a new Playwright MCP endpoint, rotating Apify tokens)
must be applied twice. A single `lib/scraper.py` with `site_hint: Literal["wechat", "generic"]`
is the natural home for cascade logic.

**Timeline impact:** Option A adds ~1 day of work in Wave 1. Option B defers the KOL
bug to a future unplanned quick — which based on project history (see Phase 17 batch-timeout
management) tends to consume more calendar time when it surfaces in production.

**RECOMMENDATION: Option A.** Fix both call sites in one pass. KOL regression is Wave 3,
which is already planned. The extra diff is concentrated in one new file, not scattered.

---

### D-STUCK-DOC-IDEMPOTENCY: RECOMMENDATION = CLI Tool (runtime-safe)

**Decision:** Build a CLI tool `scripts/cleanup_stuck_docs.py` that can run while
LightRAG is idle OR running, because the LightRAG storage layer uses per-namespace
`asyncio.Lock` with cooperative `index_done_callback` flushing — not file locks.
The safe minimum cleanup removes records from `kv_store_doc_status.json` only for
docs in `FAILED` or `PROCESSING` status, then calls `adelete_by_doc_id` via a fresh
LightRAG instance (which also cleans `kv_store_full_docs.json`, `vdb_*.json`, and
graph entries). Do NOT edit JSON files directly while a LightRAG process is running.

#### Evidence from LightRAG source code

**Storage layer anatomy** (from `lightrag/namespace.py` + `lightrag/lightrag.py:660-737`):

```
lightrag_storage/
  kv_store_doc_status.json       # DocStatus per doc_id — FAILED/PROCESSING live here
  kv_store_full_docs.json        # Raw document content
  kv_store_text_chunks.json      # Chunked text
  kv_store_full_entities.json    # Entity metadata per doc_id
  kv_store_full_relations.json   # Relation metadata per doc_id
  kv_store_entity_chunks.json    # Entity-to-chunk mapping
  kv_store_relation_chunks.json  # Relation-to-chunk mapping
  vdb_entities.json              # NanoVectorDB entity embeddings
  vdb_relationships.json         # NanoVectorDB relationship embeddings
  vdb_chunks.json                # NanoVectorDB chunk embeddings
  graph_chunk_entity_relation/   # Kuzu graph (binary)
```

**Lock semantics** (`lightrag/kg/shared_storage.py:1-96`):

The lock system uses `asyncio.Lock` objects registered in a process-local lock registry.
These are in-memory coroutine locks, NOT file system advisory locks. A separate
process inspecting or modifying the JSON files while a LightRAG process is running
will NOT acquire these locks — they are invisible across process boundaries.

**Persistence timing** (`lightrag/kg/json_doc_status_impl.py:174-222`):

```python
async def index_done_callback(self) -> None:
    async with self._storage_lock:
        if self.storage_updated.value:
            needs_reload = write_json(data_dict, self._file_name)
```

Data is flushed to disk only when `index_done_callback` is called (end of a pipeline
cycle). An in-flight `ainsert` call that LLM-times out will set status `FAILED`
(`lightrag.py:2100-2121`) and call `index_done_callback`. A process crash before
`index_done_callback` leaves the doc in `PROCESSING` status in the JSON file.

**What "stuck doc" means in practice:**

A doc is stuck when:
1. `kv_store_doc_status.json` contains `"status": "failed"` or `"status": "processing"` for the doc_id
2. The corresponding content in `kv_store_full_docs.json` may or may not exist
3. Entity vectors and graph edges may be partially written

**LightRAG's own self-healing path** (`lightrag.py:1603-1733`):

When a new `ainsert` is called, `_validate_and_fix_document_consistency` runs and:
- Docs with `FAILED` status AND no content in `full_docs` → deleted from `doc_status` automatically
- Docs with `FAILED` status AND content in `full_docs` → status reset to `PENDING` (retried)
- Docs with `PROCESSING` status → status reset to `PENDING` (retried)

This means **LightRAG already heals FAILED docs on the next batch** IF the next batch
calls `ainsert` again with the same doc_id. The stuck-doc problem is when `enriched`
was set to 2 in SQLite before the PROCESSED check completed, OR when operators want
to force-clear without waiting for the next batch.

**`adelete_by_doc_id` concurrency contract** (`lightrag.py:3223-3265`):

```
- adelete_by_doc_id can only run when pipeline is idle OR during batch deletion
- Prevents other adelete_by_doc_id calls from running concurrently
```

The method is safe to call from a separate process ONLY if no `ainsert` is in
progress. It acquires a pipeline lock internally. Calling it while a batch is
mid-flight will block until the pipeline is idle — no data corruption, but the
caller may wait indefinitely.

**Minimum-safe cleanup recipe** (for a doc_id `d`):

1. Create a fresh LightRAG instance (same `working_dir`).
2. Call `await rag.initialize_storages()`.
3. Call `await rag.adelete_by_doc_id(d)`.
   - This removes from: `doc_status`, `full_docs`, `full_entities`, `full_relations`, `text_chunks`, VDB vectors, and graph edges.
   - Evidence: `lightrag.py:3361-3441` and `lightrag.py:4017-4036`.
4. Do NOT manually edit any JSON files — they are in-memory during a live process.

**Direct JSON edit (while LightRAG not running):**

If the pipeline is provably stopped (no process), you may edit `kv_store_doc_status.json`
directly to remove a FAILED entry. But this leaves orphaned entries in other KV stores
and the VDB. Prefer `adelete_by_doc_id` which handles all layers atomically.

**Deliverable form justification:**

- **CLI tool** (`scripts/cleanup_stuck_docs.py`): Takes `--doc-id` or `--all-failed`/`--all-processing`,
  creates a fresh LightRAG instance, calls `adelete_by_doc_id`. Safe to run while pipeline
  is idle between batches. The cron orchestrator fires batches once daily; cleanup can run in the
  window between batches. If the pipeline IS running, the CLI blocks on the pipeline lock
  (no corruption, just waits).
- **Cron pre-hook**: Adds startup latency to every cron run. Not needed given the CLI approach
  is safe at idle time.

**RECOMMENDATION: CLI tool only.** Cron pre-hook is not warranted given that (a) LightRAG
self-heals FAILED docs on the next `ainsert` call and (b) the CLI tool is safe at idle.
Deliver: `scripts/cleanup_stuck_docs.py --dry-run / --doc-id / --all-failed / --all-processing`.

---

## Integration Architecture

### 3. Schema Decision: `rss_articles` new columns vs. new table vs. unified

**RECOMMENDATION: Add columns to `rss_articles` only.**

**Evidence:**

Current `rss_articles` schema (from live DB):
```sql
rss_articles (
  id, feed_id, title, url, author, summary,
  content_hash, published_at, fetched_at,
  enriched INTEGER DEFAULT 0, content_length
)
```

Current `articles` (KOL) schema:
```sql
articles (
  id, account_id, title, url, digest, update_time,
  scanned_at, content_hash, enriched INTEGER DEFAULT 0
)
```

The two source tables diverge at the identity level: `rss_articles.feed_id` vs.
`articles.account_id`; `rss_articles.summary` (feed excerpt) vs. `articles.digest`.
A unified table would require nullable columns for both sides or a discriminator column,
adding schema complexity with no query benefit — the orchestrator queries them
separately (`step_7_ingest_all` runs two independent subprocesses).

**New columns needed on `rss_articles`:**

```sql
ALTER TABLE rss_articles ADD COLUMN body TEXT;            -- full scraped text (Wave 1)
ALTER TABLE rss_articles ADD COLUMN body_scraped_at TEXT; -- when body was last fetched
ALTER TABLE rss_articles ADD COLUMN depth INTEGER;        -- from fullbody classify (Wave 2)
ALTER TABLE rss_articles ADD COLUMN topics TEXT;          -- JSON array, from classify (Wave 2)
ALTER TABLE rss_articles ADD COLUMN classify_rationale TEXT; -- from classify (Wave 2)
```

`rss_classifications` keeps per-topic rows (used by `rss_classify.py` step). The new
`depth` / `topics` columns on `rss_articles` mirror the `classifications` KOL pattern
(which has both per-topic rows in `classifications` AND inline depth in the scrape path).
This avoids a JOIN in `rss_ingest.py`'s `_eligible_articles` query.

**Migration risk for 1020-row backlog:**

The `ALTER TABLE ADD COLUMN` DDL with `DEFAULT NULL` is safe on SQLite for any table size.
SQLite defers the physical rewrite; reads of the new column return NULL until explicitly
populated. The 1020 existing rows are not invalidated — they simply get NULL `body`, which
the Wave 2 re-ingest path already handles (scrape-on-demand when `body IS NULL`).

**No new `rss_fulltext` table needed.** Adding it would split the eligibility query
across two tables with a JOIN for a single-user pipeline where simplicity wins.

---

### 4. KOL Checkpoint Reuse: Shared namespace `checkpoints/<hash>/`

**RECOMMENDATION: Use the same `checkpoints/<hash>/` namespace for RSS.**

**Evidence from `lib/checkpoint.py:36-56`:**

```python
STAGE_FILES: dict[str, str] = {
    "scrape": "01_scrape.html",
    "classify": "02_classify.json",
    "image_download": "03_images/manifest.json",
    "text_ingest": "04_text_ingest.done",
    "vision_worker": "05_vision/",
    "sub_doc_ingest": "06_sub_doc_ingest.done",
}
```

The hash key is derived from URL (`lib/checkpoint.py:63-65`):
```python
def get_article_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
```

A WeChat URL and an RSS URL will never produce the same 16-char SHA-256 prefix
under realistic conditions (namespace collision probability: ~2^-64). The stage file
names are source-agnostic. `rss_ingest.py` already computes a hash independently:
```python
article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]  # rss_ingest.py:244
```

For consistency with the checkpoint system, RSS must switch to SHA-256 first-16 (the
`get_article_hash` function) rather than MD5 first-12.

**Verdict:** No `checkpoints/rss/<hash>/` subdirectory. RSS uses the same root
`checkpoints/<hash>/`. The stage set is identical (scrape, classify, image_download,
text_ingest, sub_doc_ingest). `checkpoint_status.py` and `checkpoint_reset.py` already
work against the flat root — no modification needed.

---

### 5. Generalization Scope of `ingest_wechat.py` + `image_pipeline.py`

**`image_pipeline.py` — zero changes needed.**

The module already abstracts all image operations behind clean sync functions:
`download_images`, `filter_small_images`, `describe_images`, `localize_markdown`,
`save_markdown_with_images`. It has no WeChat-specific logic. RSS can import it
directly.

**`ingest_wechat.py` — extract one function, leave rest in place.**

The scraping cascade lives across four functions:
- `scrape_wechat_apify` (line 509) — WeChat-specific Apify actor
- `scrape_wechat_cdp` (line 681) — generic CDP, works on any URL
- `scrape_wechat_mcp` (line 547) — generic Playwright MCP, works on any URL
- `scrape_wechat_ua` (line 415) — WeChat-specific UA spoofing (MicroMessenger header)
- `process_content` (line 725) — generic HTML → Markdown, no WeChat dependency
- `ingest_article` (line 758) — orchestrates the cascade, tied to `rag` parameter

**Right abstraction seam:**

Extract a standalone `lib/scraper.py` with:

```python
@dataclass(frozen=True)
class ScrapeResult:
    title: str
    markdown: str           # html2text output, images already extracted
    img_urls: list[str]     # remote image URLs found in content
    url: str
    publish_time: str
    method: str             # "apify" | "cdp" | "mcp" | "ua" | "requests" | "failed"

async def scrape_url(
    url: str,
    *,
    site_hint: Literal["wechat", "generic"] = "generic",
    apify_token: str | None = None,
    cdp_url: str | None = None,
) -> ScrapeResult | None:
    """
    Cascade: Apify (WeChat-actor if site_hint=wechat, generic-actor if generic)
             → CDP (both modes)
             → MCP (if cdp_url ends with /mcp)
             → UA (WeChat-MicroMessenger header, wechat only)
             → requests + BeautifulSoup (generic fallback)
    Returns None only if all methods fail.
    """
```

**Functions to move:**
- `scrape_wechat_cdp` → becomes `_scrape_via_cdp(url, cdp_url)` in `lib/scraper.py`
- `scrape_wechat_mcp` → becomes `_scrape_via_mcp(url, mcp_url)` in `lib/scraper.py`
- `process_content` → move to `lib/scraper.py` (it is already generic HTML→MD)
- `scrape_wechat_ua` stays in `ingest_wechat.py` but is called internally by `scrape_url`
- `scrape_wechat_apify` stays in `ingest_wechat.py` but is called internally by `scrape_url`

**Functions that stay in `ingest_wechat.py`:**
- `ingest_article` — orchestrates the full ingest (classify + image + LightRAG), not just scrape
- All UA rotation helpers (`_next_ua`, `_ua_cooldown`)
- `get_rag`, `_vision_worker_impl`, `_pending_doc_id` tracking

**`_build_fullbody_prompt` and `_call_deepseek_fullbody` in `batch_classify_kol.py:226-276`:**
These stay in `batch_classify_kol.py`. `rss_ingest.py` imports them directly — same pattern
as `batch_ingest_from_spider.py:953`.

---

### 6. Integration Point: New File vs. Extracted

**Create `lib/scraper.py` (new file, ~200 lines). Modify `enrichment/rss_ingest.py` (rewrite, ~250 lines). Modify `batch_ingest_from_spider.py` (~8 lines at line 940).**

**Call sites of `scrape_url` after refactor:**

| Call site | File | Current code replaced |
|-----------|------|-----------------------|
| KOL classify-on-demand | `batch_ingest_from_spider.py:940` | `ingest_wechat.scrape_wechat_ua(url)` |
| RSS full-body ingest | `enrichment/rss_ingest.py` (new loop body) | `body = row["summary"]` (summary-only) |

`ingest_wechat.ingest_article` keeps its own internal cascade for the original WeChat
article ingestion path — it does more than just scrape (it also runs the vision worker,
checkpoint writes, and direct LightRAG insertion). This path is not refactored in v3.4.

**Suggested module layout:**

```
lib/
  scraper.py          # NEW: scrape_url() + ScrapeResult + process_content (moved)
  checkpoint.py       # unchanged
  lightrag_embedding.py # unchanged
  vision_cascade.py   # unchanged

enrichment/
  rss_ingest.py       # REWRITE: scrape → fullbody classify → image pipeline → LightRAG

batch_ingest_from_spider.py  # PATCH: line 940 only
ingest_wechat.py             # MINOR: remove duplicate process_content if moved to lib
```

---

### 7. Build Order

Given the D-level decisions locked above, here is the dependency-respecting wave order:

```
Wave 1 — lib/scraper.py + KOL hot-fix (unblocks Wave 2 RSS rewrite)
  1a. Extract process_content → lib/scraper.py
  1b. Port scrape_wechat_cdp + scrape_wechat_mcp → lib/scraper.py generic versions
  1c. Implement scrape_url(url, site_hint, ...) with full cascade
  1d. Patch batch_ingest_from_spider.py:940 → scrape_url(..., site_hint="wechat")
  1e. Smoke test: run _classify_full_body on 1 known-body-missing KOL article
      verify: body persisted to articles.body, no UA-only timeout
  verify: all existing tests green (checkpoint_status, KOL ingest path)

Wave 2 — RSS full-body classify + multimodal ingest (depends on Wave 1: scrape_url)
  2a. ALTER TABLE rss_articles ADD COLUMN body TEXT / body_scraped_at / depth / topics / classify_rationale
  2b. Rewrite enrichment/rss_ingest.py:
        per article:
          - scrape_url(url, site_hint="generic") → full markdown
          - persist to rss_articles.body
          - _build_fullbody_prompt + _call_deepseek_fullbody → depth/topics
          - gate: depth >= 2 AND relevant (mirrors KOL gate)
          - image_pipeline.download_images + filter_small_images
          - image_pipeline.describe_images (vision cascade)
          - lib/lightrag_embedding._build_contents multimodal path
          - LightRAG ainsert (doc_id = f"rss-{article_id}")
          - aget_docs_by_ids PROCESSED gate (D-19 pattern, already in rss_ingest.py:148-207)
          - enriched = 2 write
  2c. Keep rss_classify.py summary-only path as a fallback for feeds where scraping
      fails (preserve existing enriched=0 → depth_score gate flow)
  verify: 3 RSS articles end-to-end (scrape → classify → vision → LightRAG)

Wave 3 — E2E regression + stuck-doc tool + backlog re-ingest + cron cutover
  3a. scripts/cleanup_stuck_docs.py (CLI tool, adelete_by_doc_id-based)
  3b. test/fixtures/rss_sample_article/ E2E fixture
  3c. Joint KOL+RSS regression: orchestrate step_7 with 5 KOL + 5 RSS
  3d. Validate stuck-doc tool: deliberately inject a FAILED doc, run tool, verify cleared
  3e. Backlog re-ingest: rss_articles WHERE enriched=0, run in batches of 50
      (matches WeChat 50-article throttle convention; RSS has no WeChat throttle but
       SiliconFlow balance management applies)
  3f. Update register_phase5_cron.sh body to call orchestrate step_7 (cutover)
  verify: success criteria 1-6 from PROJECT.md v3.4 section
```

**Critical dependency chain:**

```
Wave 1 (lib/scraper.py) 
  → Wave 2 (rss_ingest rewrite uses scrape_url)
    → Wave 3 (regression needs Wave 2 working; stuck-doc tool needs LightRAG understanding)
```

**Wave 1 must land before Wave 2 begins.** Wave 3 can start cleanup_stuck_docs.py in
parallel with Wave 2 (it depends only on LightRAG source understanding, not on the
new scraper).

---

## Component Boundaries

| Component | Responsibility | Depends On | Used By |
|-----------|---------------|------------|---------|
| `lib/scraper.py` (new) | URL → (markdown, img_urls, metadata) with full cascade | `requests`, `playwright`, `bs4`, `html2text`, existing CDP/MCP logic | `batch_ingest_from_spider._classify_full_body`, `enrichment/rss_ingest` |
| `image_pipeline.py` | Image download + filter + vision cascade | `lib/vision_cascade`, `SiliconFlow`, `OpenRouter`, `Gemini` | `enrichment/rss_ingest` (new), `ingest_wechat.py` (existing) |
| `lib/checkpoint.py` | Per-article stage persistence | filesystem only | `rss_ingest` (new), `batch_ingest_from_spider` (existing), `ingest_wechat` (existing) |
| `enrichment/rss_ingest.py` (rewrite) | RSS scrape → classify → image → LightRAG | `lib/scraper`, `image_pipeline`, `batch_classify_kol._build_fullbody_prompt`, `lib/checkpoint` | `orchestrate_daily.step_7_ingest_all` |
| `scripts/cleanup_stuck_docs.py` (new) | Remove FAILED/PROCESSING docs from all LightRAG stores | LightRAG `adelete_by_doc_id` | Operator / cron window |
| `batch_classify_kol._build_fullbody_prompt` | Build DeepSeek full-body classify prompt | `requests` (DeepSeek HTTP) | `batch_ingest_from_spider._classify_full_body`, `rss_ingest` (new) |

---

## Data Flow: New RSS Full-Body Path

```
orchestrate_daily.step_7_ingest_all
  └─ enrichment/rss_ingest.run(max_articles)
       ├─ SELECT rss_articles WHERE enriched=0 (eligibility SQL unchanged)
       └─ per article:
            │
            ├─ 01. lib/scraper.scrape_url(url, site_hint="generic")
            │       └─ cascade: requests/BS4 → CDP → MCP
            │       └─ ScrapeResult(markdown, img_urls, ...)
            │       └─ checkpoint: write_stage(hash, "scrape")
            │
            ├─ 02. _build_fullbody_prompt(title, markdown[:8000])
            │       + _call_deepseek_fullbody → {depth, topics, rationale}
            │       └─ write depth/topics/rationale to rss_articles
            │       └─ checkpoint: write_stage(hash, "classify")
            │
            ├─ 03. image_pipeline.download_images(img_urls, dest_dir)
            │       + filter_small_images
            │       └─ checkpoint: write_stage(hash, "image_download")
            │
            ├─ 04. build final_md (localize_markdown + title header)
            │       LightRAG ainsert(final_md, ids=[f"rss-{article_id}"])
            │       aget_docs_by_ids PROCESSED gate (D-19 pattern)
            │       enriched = 2 only on PROCESSED confirmation
            │       └─ checkpoint: write_stage(hash, "text_ingest")
            │
            └─ 05. asyncio.create_task(_vision_worker_impl(...))  [background]
                    describe_images → sub_doc ainsert(f"rss-{article_id}_images")
                    └─ checkpoint: write_stage(hash, "sub_doc_ingest")
```

**Key invariants preserved from KOL path:**
- Checkpoint atomicity: every stage write is `.tmp` → `os.replace()`
- Vision worker is fire-and-forget: exceptions swallowed, text ingest is never blocked
- `enriched = 2` written only after `PROCESSED` status confirmed (D-19)
- LightRAG instance is fresh per `run()` call (D-09.07 STATE-04)

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Direct JSON file editing for stuck-doc cleanup

**What it is:** Opening `kv_store_doc_status.json` in an editor and deleting FAILED entries manually.

**Why it is dangerous:** LightRAG holds the in-memory `_data` dict as the source of truth during
a run (`json_doc_status_impl.py:62-69`). JSON is only the persistence store flushed by
`index_done_callback`. Editing the JSON mid-run produces an inconsistent in-memory vs.
on-disk state. Subsequent `_validate_and_fix_document_consistency` calls may make unexpected
decisions. Orphaned entries in `vdb_*.json`, `kv_store_full_entities.json`, and Kuzu graph
are not cleaned.

**Instead:** Use `scripts/cleanup_stuck_docs.py` which calls `adelete_by_doc_id` — the only
API that cleans all storage layers atomically.

### Anti-Pattern 2: Setting `enriched = 2` before `PROCESSED` status verified

**What it is:** Marking RSS articles as ingested before calling `aget_docs_by_ids` to confirm
`status == "PROCESSED"`.

**Why it is dangerous:** This is the exact bug that the current `rss_ingest.py` does NOT have
(the D-19 gate was correctly implemented at lines 183-206). The new rewritten `rss_ingest.py`
must preserve this gate. If `ainsert` returns without error but the doc ends up `FAILED` (e.g.,
DeepSeek entity-merge timeout), a missing gate leaves `enriched = 2` pointing at a ghost doc
in LightRAG.

**Instead:** Gate `enriched = 2` write on `aget_docs_by_ids` returning `status == "PROCESSED"`
exactly as the current `_ingest_lightrag` function does.

### Anti-Pattern 3: One LightRAG instance shared across multiple RSS articles per `run()` call

**What it is:** Constructing one `LightRAG` instance at the top of `rss_ingest.run()` and
passing it to all articles.

**Why it is dangerous:** The existing KOL path in `batch_ingest_from_spider.py` uses a shared
instance intentionally (for entity merge efficiency). But `rss_ingest.py` currently calls
`asyncio.run(_ingest_lightrag(...))` per article, each with its own `LightRAG` instance.
The rewrite should follow the KOL pattern (one shared instance per `run()` call) for efficiency,
BUT must preserve the `await rag.finalize_storages()` call in a `finally` block so a
Ctrl-C during batch does not leave unflushed buffers.

### Anti-Pattern 4: RSS-only `checkpoints/rss/<hash>/` namespace

**What it is:** Creating a separate `checkpoints/rss/` subdirectory for RSS article state.

**Why it is redundant:** `get_article_hash(url)` produces a deterministic 16-char SHA-256
prefix that is effectively unique for any URL regardless of source. The stage file names
(`01_scrape.html`, `04_text_ingest.done`, etc.) are source-agnostic. `checkpoint_status.py`
and `checkpoint_reset.py` already traverse the flat `checkpoints/` root. A subdirectory
adds path-handling complexity with no benefit.

---

## Confidence Assessment

| Area | Level | Evidence |
|------|-------|----------|
| D-RSS-SCRAPER-SCOPE recommendation | HIGH | `batch_ingest_from_spider.py:940` line read directly; diff estimates from function sizes |
| D-STUCK-DOC-IDEMPOTENCY | HIGH | LightRAG source at `kg/json_doc_status_impl.py`, `kg/shared_storage.py`, `lightrag.py:1603-1733`, `lightrag.py:3223-3441` |
| Schema decision (add columns to rss_articles) | HIGH | Live SQLite schema confirmed; migration DDL is `ALTER TABLE ADD COLUMN` (safe) |
| Checkpoint namespace reuse | HIGH | `lib/checkpoint.py:63-65` hash function; stage names are source-agnostic |
| Scraper API signature | MEDIUM | Design; function bodies reviewed but signature not yet validated in integration |
| Build order | MEDIUM | Dependency graph from code review; actual timing depends on Day-1/2/3 baseline window |

---

## Sources

All evidence is from local source files, read directly.

| File | Relevant lines |
|------|---------------|
| `batch_ingest_from_spider.py` | 904-984 (`_classify_full_body`, scrape-on-demand bug at 940) |
| `batch_classify_kol.py` | 226-276 (`_build_fullbody_prompt`, `_call_deepseek_fullbody`) |
| `ingest_wechat.py` | 415-506 (`scrape_wechat_ua`), 509-545 (`scrape_wechat_apify`), 547-678 (`scrape_wechat_mcp`), 681-724 (`scrape_wechat_cdp`), 725-757 (`process_content`) |
| `image_pipeline.py` | 1-586 (full module; no WeChat-specific logic) |
| `lib/lightrag_embedding.py` | 94-114 (`_build_contents` — localhost regex + multimodal Part assembly) |
| `lib/checkpoint.py` | 36-66 (stage file map, hash function) |
| `enrichment/rss_ingest.py` | 148-207 (`_ingest_lightrag`, D-19 PROCESSED gate), 243-244 (MD5 hash inconsistency) |
| `enrichment/rss_classify.py` | 110-141 (`_eligible_articles` — summary-only query, confirms body column missing) |
| `enrichment/orchestrate_daily.py` | 182-213 (`step_7_ingest_all` — both arms, cutover target) |
| `venv/Lib/site-packages/lightrag/kg/json_doc_status_impl.py` | 31-422 (full doc status storage; lock semantics, FAILED/PROCESSING handling) |
| `venv/Lib/site-packages/lightrag/kg/shared_storage.py` | 1-100 (asyncio.Lock registry, NOT file locks) |
| `venv/Lib/site-packages/lightrag/lightrag.py` | 660-737 (storage namespace → filename mapping), 1603-1733 (self-healing FAILED docs), 3223-3441 (`adelete_by_doc_id` full delete contract) |
| `venv/Lib/site-packages/lightrag/namespace.py` | 1-28 (all storage filenames) |
| SQLite live schema | `data/kol_scan.db` — `rss_articles`, `articles`, `classifications`, `rss_classifications` |
