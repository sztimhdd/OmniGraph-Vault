# Phase 5-00b Batch Run — Diagnostic Report

> **Audience:** Claude Code — root cause + fix needed before rerun.
> **Run ID:** PID 656660, ~3.5h, Agent+LLM topics
> **Status:** KILLED — embedding 429 death spiral

---

## 1. What Happened

```
Ingested: 56/282 (20%)
Articles started: 20, Successfully Ingested: 10
Runtime: 3.5h (~12 min per successful article)

Errors in log:
  7,645 × 429       (embedding quota exhausted)
  3,532 × RESOURCE_EXHAUSTED
  1,767 × "Failed to extract document"
    185 × 503       (server overload)

Rate: 1 article / 10 minutes (target was 1/min)
```

## 2. Root Cause: Embedding Death Spiral

```
LightRAG ainsert(doc)
  → chunk document into N chunks
  → extract entities per chunk (DeepSeek ✅)
  → embed entities (Gemini embedding)
  → 429 → retry → 429 → retry → 429 → ...
  → 1 doc = ~200 embedding retries = self-reinforcing

Both Gemini keys exhausted:
  Key1: 1,000 RPD 
  Key2: 1,000 RPD
  Total calls burned on retries: ~11,200 (all 429)
  Actual successful embedding: < 500
```

**The retry loop amplifies the problem.** Each failed document triggers 100+ retries, each burning quota points, each returning 429. LightRAG's retry logic (3 attempts per entity, N entities per doc) creates a feedback loop that consumes the entire quota pool without making progress.

## 3. Architecture Verdict

The in-process architecture (C1-C3) **works correctly**:
- ✅ Single LightRAG init (one log line, confirmed)
- ✅ No subprocess zombies (confirmed)
- ✅ DeepSeek swap for extract_entities (C2, confirmed)
- ✅ rag.finalize_storages() on KeyboardInterrupt (C3)

**The bottleneck is not architecture — it's embedding quota.** The subprocess architecture would have the same problem (in fact worse, because each subprocess re-inits LightRAG and starts its own retry loop independently).

## 4. Required Fix

### Option 1: Cooldown on embedding 429 (targeted, low risk)

Add a cooldown timer to `lightrag_embedding.py` when both keys return 429:

```python
# In embedding_func, after both keys fail:
if consecutive_429s > 5:
    logger.warning("Embedding quota exhausted — cooling down 5 min")
    await asyncio.sleep(300)
    consecutive_429s = 0
```

This lets the per-minute quota window reset before retrying.

### Option 2: Reduce LightRAG embedding concurrency (quick, low risk)

Current: `embedding_func_max_async=1` (serial). But LightRAG's batch happens per-doc — one doc with 50 entities = 50 sequential embedding calls. The per-minute window can't absorb this.

Suggested: Add per-doc rate limiting — pause 1 second between embedding batches within a single doc.

### Option 3: Switch to DeepSeek embeddings (high impact, medium risk)

DeepSeek offers embedding via `deepseek-chat` compatible endpoint. Free tier quota unknown but likely higher than Gemini's 1,000 RPD. Would completely eliminate Gemini embedding dependency.

### Recommendation

**Do Options 1 + 2 immediately** (cooldown + per-doc throttling). They are surgical (~20 lines in `lightrag_embedding.py`) and fix the retry death spiral without changing the embedding provider.

**Evaluate Option 3** separately — it's a strategic decision that affects the entire embedding pipeline.

## 5. Current State After Kill

```
Ingested:     56/282 (20%)
LightRAG:     107 docs, 438 entities, 35 chunks
Classified:   Agent: 145, LLM: 206 (ready)
Unprocessed:  226 articles remaining
Gemini keys:  Both exhausted — need UTC reset (~midnight PT)
```

## 6. Next Run

After fix is applied: rerun same command. The 56 already-ingested articles are skipped via `ingestions` table dedup. 226 remaining.

```bash
python batch_ingest_from_spider.py --from-db --topic-filter 'Agent,LLM' --min-depth 2
```

---

*Report: 2026-04-29 · Phase 5-00b*
