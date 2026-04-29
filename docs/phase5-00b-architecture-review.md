# Phase 5-00b Execution Post-Mortem: Batch Architecture Review

> **Audience:** Claude Code — review this and give final verdict on refactor approach.
> **Requested by:** Hermes Agent (remote WSL) after 3 failed batch runs.
> **Status:** OPEN — awaiting Claude Code's recommendation.

---

## 1. Symptoms Observed

### 1.1 19/351 Articles Ingested After 6+ Hours

```
Attempt 1: 9 articles (ad-hoc subprocess.run wrapper)
Attempt 2: 0 articles (flash-lite 20 RPD exhausted — killed)
Attempt 3: 10 articles (zombie cleanup discovered 1 extra)
Current:   19 articles / 351 candidate pool (5.4%)
Runtime:   >6 hours cumulative across 3 restarts
```

### 1.2 Zombie Process Chains

```
After each kill: 4-5 parent processes + N child ingest_wechat.py orphans
Orphans continue running independently, consuming Gemini quota
Command `pkill -9 -f batch_ingest|ingest_wechat` blocked by Hermes safety filter
```

### 1.3 Flash-Lite Quota Exhaustion

```
gemini-2.5-flash-lite: 20 RPD exhausted within first ~5 articles
Root cause: lib/models.py GA migration switched VISION_LLM from 
  gemini-3.1-flash-lite-preview (1,500+ RPD) → gemini-2.5-flash-lite (20 RPD)
```

### 1.4 Case-Sensitive Topic Filter

```
--topic-filter 'agent' → SQL WHERE c.topic IN ('agent') → 0 matches
--topic-filter 'Agent' → SQL WHERE c.topic IN ('Agent') → 145 matches
```

---

## 2. Root Cause Analysis

### R1: Subprocess-per-Article Architecture (PRIMARY)

```
batch_ingest_from_spider.py:89
  └→ subprocess.run(["python", "ingest_wechat.py", url], timeout=600)
```

**Why this is the root cause:**

| Problem | Mechanism |
|---------|-----------|
| **LightRAG re-init per article** | `ingest_wechat.py` imports LightRAG, loads graphml, initializes vdb every invocation. 15-30s overhead per article × 202 articles = 50-100 minutes wasted. |
| **Zombie processes** | `subprocess.run` creates independent child process. Killing parent leaves child orphaned with its own Gemini API connections. |
| **Timeout semantics** | `subprocess.run(timeout=600)` kills the Python runtime but not the Apify actor or in-flight API calls. |
| **No shared state** | Each subprocess reads `kol_scan.db` independently, writes `ingestions` table independently. No coordination. |

### R2: Model Version Regression (lib/models.py GA Migration)

```
Before GA migration:
  VISION_LLM = gemini-3.1-flash-lite-preview  (1,500+ RPD zero-cost)

After GA migration (lib/models.py D-11):
  VISION_LLM = gemini-2.5-flash-lite           (20 RPD)
  INGESTION_LLM = gemini-2.5-flash-lite        (20 RPD)
```

This single-line change silently reduced daily throughput by **75×**. Fixed in-session to `gemini-2.5-flash` (250 RPD) for INGESTION and `gemini-3.1-flash-lite-preview` for VISION.

### R3: Artifact-Level Rate Limiting

```
SLEEP_BETWEEN_ARTICLES = 60  # Designed for Gemini Flash 15 RPM free tier
```

With DeepSeek (no RPM concern) + dual-key Gemini embedding (150+ RPM combined), 60s sleep is 6× too conservative. Fixed to 10s.

### R4: Incomplete DeepSeek Swap

```
LightRAG entity extraction:  ✅ DeepSeek (lightrag_llm.py)
extract_entities() in ingest: ❌ Gemini (config.gemini_call → INGESTION_LLM)
```

`extract_entities()` still routes through the deprecated `gemini_call` shim to Gemini. Swapping to `deepseek_model_complete` would remove the last avoidable Gemini dependency (Vision is unavoidable but is now on 3.1-preview at 1,500+ RPD).

---

## 3. Proposed Fix: In-Process Architecture

### 3.0 Design Principle

**Treat `ingest_wechat.py` as a library, not a CLI tool.**

### 3.1 Changes to `ingest_wechat.py`

```python
# NEW: expose fetch logic as importable function (no subprocess)
async def fetch_and_parse(url: str) -> dict:
    """
    Fetch a WeChat article, parse HTML, download images, describe via Vision.
    Returns: {"markdown": str, "images": list, "title": str, "word_count": int}
    Does NOT touch LightRAG or SQLite.
    """
    ...

# NEW: expose LightRAG ingest as importable function
async def ingest_to_rag(rag: LightRAG, content: str, url: str) -> bool:
    """
    Insert content into a pre-initialized LightRAG instance.
    Extracts entities, embeds, ainserts.
    """
    ...

# Keep __main__ for backward compatibility (one-shot CLI)
if __name__ == "__main__":
    asyncio.run(main())
```

### 3.2 Changes to `batch_ingest_from_spider.py`

```python
# BEFORE (current):
for article in articles:
    subprocess.run(["python", "ingest_wechat.py", url], timeout=600)

# AFTER (proposed):
from ingest_wechat import fetch_and_parse, ingest_to_rag, get_rag

async def batch_ingest_from_db(topics, min_depth):
    rag = await get_rag()  # Init ONCE
    
    for article in articles:
        try:
            result = await fetch_and_parse(article.url)
            await ingest_to_rag(rag, result["markdown"], article.url)
            _mark_ingested(article.id)  # SQLite write
        except Exception as e:
            _mark_failed(article.id, str(e))
            continue  # Per-article isolation
    
    await rag.close()
```

### 3.3 What Stays the Same

- `lightrag_embedding.py` — dual-key rotation (proven)
- `lightrag_llm.py` — DeepSeek wrapper (proven)
- `lib/models.py` — model constants (already fixed)
- `batch_classify_kol.py` — classification pipeline (proven)
- `classifications` + `ingestions` SQLite schema (unchanged)

---

## 4. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|:---:|------------|
| `ingest_wechat.py` refactor breaks existing one-shot CLI | Low | Keep `__main__` block; add unit test |
| In-process LightRAG instance grows unbounded | Low | LightRAG manages memory internally; ~200 docs is within budget |
| Single-article failure crashes entire batch | Low | Per-article try/except (already in current code) |
| Async event loop conflict between fetch and ingest | Medium | Use `asyncio.to_thread()` for sync fetch operations |
| Graph corruption if batch killed mid-write | Low | LightRAG writes are atomic at doc level; KV store tolerates interruption |

---

## 5. Quantified Impact

| Metric | Current (subprocess) | Proposed (in-process) |
|--------|:---:|:---:|
| Per-article init overhead | 15-30s | 0s (one-time) |
| 202-article runtime | ~5 hours | ~1.5 hours |
| Zombie process risk | High (subprocess orphans) | Zero (no subprocess) |
| Gemini quota waste | ~15% spent on re-init | 0% |
| Debuggability | Poor (separate stdout) | Good (single log stream) |

---

## 6. Decision Request

**Should we proceed with the in-process refactor, or continue with the subprocess architecture with the rate-limiting fixes already applied?**

Current state:
- 19/351 ingested (5.4%)
- Subprocess batch running but slow (60→10s sleep fix not yet in running batch)
- lib/models.py model fix not yet in running batch (flash-lite → flash + 3.1)

Option A: Kill, refactor (1 hour), re-run (2 hours) → total 3 hours to 100%
Option B: Let current batch continue with rate-limit fixes (~4 hours) → total 5 hours

---

*Document version: 1.0 · 2026-04-29*
