# ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1

> **Target audience:** OmniGraph architect agent  
> **Purpose:** Architectural root-cause analysis of the cron ingest pipeline,  
> identifying systemic design flaws (not tactical bugs), and proposing a staged  
> migration toward an event-driven architecture.  
> **Data basis:** 564 commits (May 1–May 16), 12 cron run logs, production DB state.

Created: 2026-05-17

---

## 1. Current Architecture: Monolithic Batch Pipeline

The production ingest path runs as a single Python process invoked daily at 09:00 CST:

```
cron_daily_ingest.sh 5
  └─ batch_ingest_from_spider.py --from-db --max-articles 5
       └─ ingest_wechat.ingest_article()
```

### 1.1 System Model

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      batch_ingest_from_spider.py                         │
│                                                                           │
│  Stage 0: Load 135–219 articles from SQLite                              │
│  Stage 1: Layer1 classify (DeepSeek, 30-article batches)                 │
│  Stage 2: Layer2 classify (DeepSeek, 5-article batches)                  │
│  Stage 3: Per-article loop:                                              │
│    ├─ Scrape body (UA scrape or Apify)                                   │
│    ├─ Extract entities (LightRAG via DeepSeek LLM)                       │
│    ├─ Extract image entities (SiliconFlow Vision)                        │
│    ├─ Merge into graph (LightRAG + Vertex AI embedding)                  │
│    └─ Write graph to disk (GraphML)                                      │
│  Stage 4: Finalize — flush storages, write metrics                       │
│                                                                           │
│  CAP: MAX_ARTICLES=5 (99% of candidates discarded each day)             │
│  BUDGET: batch_budget=28800s (8h) — never hit, always stops earlier     │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
┌────────┐    ┌──────────────┐    ┌──────────────┐
│ SQLite │◄──►│ ingestions   │    │ LightRAG     │
│  DB    │    │ table (OK/   │    │ doc_status   │
│        │    │  FAILED/     │    │ JSON KV      │
│        │    │  SKIPPED)    │    │              │
└────────┘    └──────────────┘    └──────────────┘
     ▲              ▲                    ▲
     │              │                    │
     └──────────────┴────────────────────┘
               DUAL-WRITE
       (no transactional consistency)
```

### 1.3 Key Metrics (Production, May 11–15)

| Date | Input Articles | L1 Candidates | Actually Ingested | Wall Clock | Rejection Rate |
|------|---------------|---------------|-------------------|------------|----------------|
| May 11 09:01 | 195 | 129 | 4 | 12.7 min | 96.9% |
| May 11 14:12 | 158 | 151 | 5 | 30.8 min | 96.7% |
| May 11 17:43 | 146 | 109 | 2 | 16.2 min | 98.2% |
| May 11 19:35 | 135 | 134 | 7 | 41.5 min | 94.8% |
| May 12 09:00 | 138 | 118 | 1 | 6.0 min | 99.2% |

**99% of candidates are discarded every day.** The MAX_ARTICLES cap discards 214+ articles per run, most of which have already been checkpoint-skipped (ingested before).

---

## 2. Five Architectural Defects

### Defect 1: Monolith — No Stage Separation

**Manifestation:** A single Python process (`batch_ingest_from_spider.py`, 47 commits in 16 days) handles the entire pipeline from SQL query to graph write.

**Architectural problem:** The process bundles responsibilities across 4 distinct domains:
- **Fetch/Scrape** — network I/O, WeChat rate limits, Apify credits
- **Classify** — DeepSeek LLM calls, prompt engineering, topic scoring
- **Extract** — DeepSeek LLM calls, entity/relation extraction
- **Merge/Embed** — Vertex AI embedding, graph serialization

Each domain has its own failure modes and rate limits, but they all share a single process, a single timeout budget, and a single retry strategy.

**Cascading failure chain observed in production:**

```
402 Insufficient Balance (DeepSeek)
  → Classify fails
    → Extract fails
      → Image Vision succeeds (SiliconFlow, unaffected)
        → Merge fails (no entities to merge)
          → ENTIRE BATCH ABORTED
```

The 402 should only block Classify and Extract. Image Vision and Merge do not use DeepSeek. But because they're in the same process, all work stops.

**Refactored by `commit 564`?** No. Each of the 47 commits to `batch_ingest_from_spider.py` was a single-line tactical fix — adding a retry, bumping a timeout, adjusting a cap. The file grew organically without decomposition.

### Defect 2: Push Model — No Backpressure

**Manifestation:** 135–219 articles are loaded from SQLite in a single `SELECT`. They are pushed through Layer1→Layer2→ingest in sequence. When the downstream ingest stage is slow (40–60% of time spent on image Vision), the only control is the MAX_ARTICLES cap.

**Architectural problem:** This is a classic push-based batch system. The upstream produces without regard for downstream capacity. The solution is a hydraulic dam (MAX_ARTICLES=5), not a canal system.

**What a pull model would do:** Each stage consumes work as capacity allows. When the Extract worker is saturated, the Classify worker slows down. When DeepSeek is unavailable, Classify and Extract drain their queues and pause — Image Vision and Merge continue.

**Structural issue:** The MAX_ARTICLES cap conflates two independent concerns:
1. **Rate limiting** (how many DeepSeek calls can I afford per day?)
2. **Throughput capping** (how many articles can I process before the 900s terminal timeout?)

A pull model separates these: rate limiting is per-stage budget management; throughput is queue depth + timeout per article.

### Defect 3: Dual-Write Inconsistency — No Single Source of Truth

**Manifestation:** 106 "Mystery Rows" discovered across 5 production runs (May 5–10). The `ingestions` table marks articles as `ok`, but LightRAG `doc_status` shows them as `pending` or `failed`.

**Architectural problem:** Two independent state stores:

```
ingestions table (SQLite)          LightRAG doc_status (JSON KV)
─────────────────────────          ─────────────────────────────
id=5529, status='ok'               wechat_e51159998a: {'status': 'pending'}
id=5530, status='ok'               wechat_38cd26912b: {'status': 'processed'}
```

The write sequence is:
1. `ingest_wechat.py` calls LightRAG `ainsert(doc)` — this is async
2. Immediately writes `status='ok'` to `ingestions` table
3. LightRAG's async `ainsert` may fail later (402, timeout, race condition)
4. `ingestions` already says `ok` — state divergence

**This is a distributed transaction problem.** Two stores, no two-phase commit. The `_verify_doc_processed_or_raise` function (added in commit 949e3f4) polls LightRAG for 300 retries — but this is a polling hack, not a consistency guarantee.

**Correct architecture:** LightRAG `doc_status` is the **single source of truth** for ingestion state. The `ingestions` table should be a **derived view**, updated only after LightRAG confirms `processed`, or generated on query from `doc_status`.

### Defect 4: Tight Coupling — No Dependency Isolation

**Manifestation:** All four external APIs share the same process, same retry loop, same error handler.

```
┌──────────────────────────────────────────────┐
│         batch_ingest_from_spider.py           │
│                                               │
│  DeepSeek (LLM) ────────┐                    │
│  Vertex AI (embedding) ─┤ same process        │
│  SiliconFlow (vision) ──┤ same retry          │
│  WeChat MP (scrape) ────┘ same timeout        │
└──────────────────────────────────────────────┘
```

**Architectural problem:** Dependencies that should be independently managed are tightly coupled:

| API | Failure Mode | Recovery Strategy | Current Handling |
|-----|-------------|-------------------|-----------------|
| DeepSeek | 402 balance, 503 overload | Pause LLM stages, recharge | Manually detect + recharge |
| Vertex AI | 429 rate limit, quota | Exponential backoff, degraded mode | Retry 3x in-process |
| SiliconFlow | timeout, malformed image | Skip image, continue | Retry 3x, then skip |
| WeChat MP | 200013 rate limit, auth expiry | Pause scrape, retry later | Fail entire batch |

The 402 pattern is the clearest example of this defect. When DeepSeek returns 402:
- **What happens:** Entire batch aborts. All queued work lost.
- **What should happen:** Classify and Extract stages pause. Image Vision and Merge continue. Scanner keeps fetching new articles. When DeepSeek recovers, queued items are processed.
- **Why it doesn't:** All stages share the same process. One API failure → one process crash → all stages dead.

### Defect 5: Batch-Only — No Incremental Model

**Manifestation:** Every day at 09:00, the pipeline loads ALL articles from SQLite, re-classifies them all, and discards 99%. There is no concept of "this article was classified yesterday, just ingest it."

**Architectural problem:** The pipeline has no persistent stage state. Each run starts from zero knowledge:

```
DAY N:   Load 219 articles → Classify 219 → Ingest 5 → Discard 214
DAY N+1: Load 219 articles → Classify 219 → Ingest 5 → Discard 214
         (including the 214 that were classified yesterday and are STILL classified the same way)
```

This wastes:
- **DeepSeek API calls**: 219 classifications/day × 5 days = 1095 calls. An incremental model would classify each article once, then only process new arrivals (~10–20/day).
- **LightRAG initialization**: Loading 12138 nodes + 16435 edges from GraphML on every run.
- **Human attention**: Every run produces the same checkpoint-skip noise in logs.

**What an incremental model would do:**

```
DAY N:   Classify 10 new articles → Ingest 10 → Done (15 min)
DAY N+1: Classify 8 new articles → Ingest 8 → Done (12 min)
```

Articles already classified stay classified. Articles already ingested stay ingested. Only net-new work is done.

---

## 3. Target Architecture: Staged Event-Driven Pipeline

### 3.1 System Model

```
┌──────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌──────────┐
│ Scanner  │   │ Classify  │   │ Extract   │   │  Merge    │   │ Graph    │
│ (RSS/    │──→│  Queue    │──→│  Queue    │──→│  Queue    │──→│  Write   │
│  WeChat) │   │           │   │           │   │           │   │          │
└──────────┘   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘   └──────────┘
                     │               │               │
               ┌─────▼─────┐   ┌────▼──────┐   ┌────▼──────┐
               │ Classify  │   │ Extract   │   │ Embedding │
               │  Worker   │   │  Worker   │   │  Worker   │
               │ (DeepSeek)│   │ (DeepSeek)│   │(Vertex AI)│
               └───────────┘   └───────────┘   └───────────┘
                                              ┌───────────┐
                                              │  Image    │
                                              │  Worker   │
                                              │(SiliconF) │
                                              └───────────┘
```

### 3.2 Stage Definitions

#### Stage 0: Scanner (unchanged)
- **Input:** RSS feeds, WeChat KOL accounts
- **Output:** `articles` rows in SQLite with `stage = 'discovered'`
- **Isolation:** Runs independently of all other stages. No LLM dependency.
- **Schedule:** Multiple times/day for RSS, daily for KOL scan.

#### Stage 1: Classify Worker
- **Input:** Articles with `stage = 'discovered'` or `stage_status = 'pending'`
- **Processing:** Layer1 topic filter → Layer2 depth scoring (single DeepSeek call)
- **Output:** `stage = 'classified', stage_status = 'ok' | 'rejected'`
- **Isolation:** Owns its DeepSeek API budget. 402 pauses this stage only.
- **Budget:** 60s/article timeout, 50 calls/hour rate limit.
- **Recovery:** Failed classifications retry on next tick. Already-classified articles not re-processed.

#### Stage 2: Extract Worker
- **Input:** Articles with `stage = 'classified', stage_status = 'ok'`
- **Processing:** Scrape body → LightRAG entity extraction (DeepSeek LLM) → buffer entities
- **Output:** `stage = 'extracted', stage_status = 'ok' | 'failed'`
- **Isolation:** Owns its DeepSeek API budget. Parallelizable (multiple articles in flight).
- **Budget:** 180s/article timeout.
- **Recovery:** Failed extractions retry with checkpoint clearing.

#### Stage 3: Image Worker (NEW — extracted from Extract)
- **Input:** Images from extracted articles
- **Processing:** SiliconFlow Vision API → image entities
- **Output:** Image entities written to buffer, `image_status = 'ok' | 'skipped'`
- **Isolation:** FULLY independent of DeepSeek. Continues during 402 outages.
- **Budget:** 30s/image timeout, skip on timeout (not fail).
- **Parallelism:** Can run concurrently with Stage 2 (article extract) and Stage 4 (merge).

#### Stage 4: Merge Worker
- **Input:** Extracted entities + image entities
- **Processing:** Vertex AI embedding → LightRAG merge → graph write
- **Output:** `stage = 'merged', stage_status = 'ok'`
- **Isolation:** Owns Vertex AI budget. 429 handling isolated to this stage.
- **Budget:** 120s/batch timeout.
- **Single Source of Truth:** This stage writes to LightRAG `doc_status`. The `ingestions` table becomes a derived view, refreshed from `doc_status` on query.

### 3.3 Unified State Machine

**Single source of truth: LightRAG `doc_status` JSON KV.**

```
                    ┌─────────────┐
                    │  discovered │  (Scanner writes)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  classified │  (Classify Worker writes)
                    └──┬──────┬──┘
                       │      │
                 ok    │      │  rejected → terminal
                       │      │
              ┌────────▼──┐   │
              │ extracted  │   │  (Extract Worker writes)
              └──┬─────┬──┘   │
                 │     │      │
           ok    │     │ failed → retry on next tick
                 │     │
         ┌───────▼──┐  │
         │  merged   │  │  (Merge Worker writes)
         └─────┬─────┘  │
               │        │
         ok    │        │ failed → retry on next tick
               │        │
         ┌─────▼─────┐  │
         │ processed │  │  (terminal success)
         └───────────┘  │
```

**What changes for `ingestions` table:**
- No longer written by ingest workers.
- Becomes a derived view: `SELECT article_id, MAX(doc_status.status) FROM lightrag_doc_status GROUP BY article_id`.
- Or: a materialized view refreshed after each Merge batch completes.

### 3.4 Dependency Isolation

```
                    ┌─────────────────────────────────────────┐
                    │           DeepSeek API                   │
                    │  ┌──────────┐    ┌──────────┐          │
                    │  │ Classify │    │ Extract  │          │
                    │  │  Worker  │    │  Worker  │          │
                    │  └──────────┘    └──────────┘          │
                    │       │               │                 │
                    │  402 detected ──→ both paused           │
                    └───────┼───────────────┼─────────────────┘
                            │               │
                    ┌───────▼───────┐ ┌─────▼──────────────┐
                    │ Image Worker  │ │  Merge Worker      │
                    │ (SiliconFlow) │ │  (Vertex AI)       │
                    │ UNINTERRUPTED │ │  UNINTERRUPTED     │
                    └───────────────┘ └────────────────────┘
                            │               │
                    ┌───────▼───────┐ ┌─────▼──────────────┐
                    │ Scanner       │ │  Graph Write       │
                    │ (WeChat/RSS)  │ │  (GraphML)         │
                    │ UNINTERRUPTED │ │  UNINTERRUPTED     │
                    └───────────────┘ └────────────────────┘
```

When DeepSeek 402 fires:
1. Classify Worker and Extract Worker go to `paused` state.
2. Image Worker continues processing queued images (SiliconFlow is independent).
3. Merge Worker continues merging entities already extracted (Vertex AI is independent).
4. Scanner continues fetching new articles (WeChat/RSS are independent).
5. When DeepSeek recovers: paused workers auto-resume from their queues.

### 3.5 Pull Model with Backpressure

Each worker pulls work from SQLite:

```python
# Classify Worker (runs every 10 min)
def tick():
    articles = db.execute("""
        SELECT * FROM articles 
        WHERE stage = 'discovered' AND stage_status = 'pending'
        ORDER BY scanned_at ASC 
        LIMIT 10
    """)
    for article in articles:
        classify(article)  # 60s budget
        db.execute("UPDATE articles SET stage='classified', stage_status='ok' WHERE id=?", [article.id])
```

Backpressure emerges naturally:
- If Classify Worker is fast: queue drains quickly, no articles back up.
- If Extract Worker is slow: classified queue grows, Classify Worker stays capped at 10 pull.
- If no Worker is running: articles sit in their queues, no work lost.

No MAX_ARTICLES cap needed. No batch_budget needed. Each article gets its own per-stage timeout budget.

### 3.6 Scheduling Architecture

**Replaces:** Single 09:00 cron → batch_ingest_from_spider.py

**New model:** Lightweight scheduler, frequent ticks.

```
┌────────────────────────────────────────────────────────────┐
│                    Scheduler (cron, every 10 min)           │
│                                                             │
│  1. Scan articles table for pending work per stage          │
│  2. Check API health (DeepSeek 402? Vertex 429?)           │
│  3. Launch workers based on queue depth + API health:       │
│     - Classify:  if pending > 0 AND DeepSeek OK → launch   │
│     - Extract:   if pending > 0 AND DeepSeek OK → launch   │
│     - Image:     if pending > 0 → launch (no API dep)      │
│     - Merge:     if pending > 0 AND Vertex OK → launch     │
│  4. Each worker processes up to 5 articles, then exits      │
│  5. Scheduler writes stage_counts to metrics               │
└────────────────────────────────────────────────────────────┘
```

**Why 10-minute ticks?** 
- Small enough to react quickly to 402 recovery.
- Large enough to avoid overlapping worker instances.
- With 5 articles/tick × 6 ticks/hour × 24 hours = 720 articles/day capacity (far exceeding current 1–7/day).

**Worker lifecycle:**
- Launch as subprocess (or thread if lightweight).
- Process up to 5 articles, then exit.
- If article-level timeout fires: mark that article failed, continue to next.
- If worker-level timeout fires (5 min): kill worker, mark remaining as pending (retry next tick).

---

## 4. Migration Path (4 Phases, ~5 Days)

### Phase 1: Stage Decomposition (days 1–2)

**Goal:** Split the monolith into 4 independent worker scripts. No logic changes — only separation of concerns.

**Output:**
```
scripts/
  ingest_classify_worker.py   ← Layer1 + Layer2 logic extracted
  ingest_extract_worker.py    ← scrape + entity extraction logic
  ingest_image_worker.py      ← image vision logic (NEW)
  ingest_merge_worker.py      ← LightRAG merge + graph write
  ingest_scheduler.py         ← launch workers based on queue state
```

**Validation:** Run each worker independently on production DB. Same output as current pipeline, same article count.

**Risk:** Low. Logic unchanged, only call boundaries moved.

### Phase 2: Unified State Machine (day 3)

**Goal:** LightRAG `doc_status` becomes single source of truth. `ingestions` table becomes derived view. Add `stage` and `stage_status` columns to `articles` table.

**Migration script:**
```sql
ALTER TABLE articles ADD COLUMN stage TEXT DEFAULT 'discovered';
ALTER TABLE articles ADD COLUMN stage_status TEXT DEFAULT 'pending';
-- Backfill from existing ingestions + doc_status
```

**Validation:** Reconcile script: `SELECT article_id WHERE ingestions.status != doc_status.stage_status` → must return 0 rows.

**Risk:** Medium. Column addition is safe; backfill logic must handle 106 known mystery rows.

### Phase 3: Event-Driven Scheduling (day 4)

**Goal:** Replace single 09:00 cron with 10-minute scheduler ticks. Workers launch on demand.

**Cron changes:**
```
# REMOVE:  0 9 * * * cron_daily_ingest.sh 5
# ADD:     */10 * * * * scripts/ingest_scheduler.py
```

**Scheduler logic:**
1. Query `articles` for pending per stage.
2. Check API health (ping DeepSeek, Vertex AI).
3. Launch workers if work pending + API healthy.
4. Log queue depths per stage.

**Validation:** Run in shadow mode alongside existing 09:00 cron for 1 day. Compare output.

**Risk:** Medium. New scheduler logic; must handle worker zombie detection.

### Phase 4: Backpressure + Degradation (day 5)

**Goal:** Per-stage time budgets. Automatic degradation on timeout.

**Budgets per article:**
| Stage | Timeout | On Timeout |
|-------|---------|------------|
| Classify | 60s | Mark failed, retry next tick |
| Extract | 180s | Mark failed, clear checkpoint, retry |
| Image | 30s/image | Skip image, mark `image_skipped` |
| Merge | 120s/batch | Mark failed, retry next tick |

**402 auto-detection:**
```python
def check_deepseek_health():
    resp = deepseek.chat("ping")
    if resp.error_code == 402:
        set_stage_paused('classify', reason='deepseek_402')
        set_stage_paused('extract', reason='deepseek_402')
        return False
    set_stage_active('classify')
    set_stage_active('extract')
    return True
```

**Validation:** Trigger 402 by using empty API key. Verify Classify/Extract pause, Image/Merge continue.

**Risk:** Low. Budget management is additive, not destructive.

---

## 5. What NOT to Change

These components are working correctly and should be preserved:

1. **Scanner layer (RSS/KOL fetch):** Stable. Handles WeChat rate limits adequately. No architectural change needed.

2. **Layer1/Layer2 classification logic:** Quality is good. 60% of articles correctly rejected as off-topic. Keep the prompts, keep the DeepSeek model, just move it to the Classify Worker.

3. **LightRAG entity extraction:** Entity quality is good (42 entities/article, high merge rates). The issue is only the async `ainsert` race condition — solved by Phase 2's single-source-of-truth.

4. **Image Vision pipeline:** Works correctly when not blocked by unrelated API failures. 92% of images successfully processed. Just needs to be an independent stage.

5. **Graph serialization:** GraphML writes are reliable. 20951 nodes, 29347 edges, consistent across runs.

6. **Checkpoint system:** Although manual cleanup is annoying, the checkpoint logic itself is correct — it prevents expensive re-processing.

---

## 6. Success Criteria

| Metric | Current | Target (Post Phase 4) |
|--------|---------|----------------------|
| Daily ingest throughput | 1–7 articles | 10–30 articles (unconstrained by cap) |
| 402 recovery time | Manual (hours) | Auto-detect + auto-resume (10 min) |
| Mystery rows | 106 in 10 days | 0 (single source of truth) |
| DeepSeek API calls wasted | 214/day re-classified | 0 (incremental) |
| Zombie processes | vision drain zombies | 0 (worker lifecycle management) |
| Manual intervention | per-run (checkpoint, reconciles) | 0 (auto-healing) |
| Stage isolation | None (all or nothing) | Full (402 blocks only LLM stages) |

---

## 7. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| SQLite polling over Kafka/Redis | Current scale (<200 articles/day) doesn't justify external queue infrastructure | 2026-05-17 |
| 4 stages, not 5 | Image processing is a sub-stage of Extract, not a top-level concern | 2026-05-17 |
| Keep existing scripts as-is, add new worker scripts | Minimize regression risk during migration | 2026-05-17 |
| LightRAG doc_status as source of truth | Only store that has complete processing lifecycle; SQLite is a cache | 2026-05-17 |
| 10-minute scheduler ticks | Balance between responsiveness and overhead | 2026-05-17 |
| MAX_ARTICLES deprecated after Phase 3 | Pull model handles throughput via queue depth, not hard cap | 2026-05-17 |
| Per-stage budget, not global batch_budget | Different APIs have different failure modes and SLAs | 2026-05-17 |
