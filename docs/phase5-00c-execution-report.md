# Phase 5-00c Execution Report: Classification + Keyword-Guided Catch-Up Ingest

> **Audience:** Claude Code — this documents the live run of 2026-04-29 and the issues discovered.
> **Status:** Partial success — 9/31 ingested, 22 blocked by subprocess deadlock.

---

## 1. What Was Executed

| Step | Action | Result |
|------|--------|--------|
| 1 | Verify API connectivity | ✅ DeepSeek OK, Gemini Key1/Key2 OK (3072d embedding) |
| 2 | Run `batch_classify_kol.py --topic Agent --classifier deepseek` | ✅ 303 articles classified: 145 depth≥2, 26 depth=3 |
| 3 | Filter by keyword (openclaw/hermes/agent/harness) + depth≥2 | ✅ 31 articles matched |
| 4 | Ingest matched articles via `ingest_wechat.py` | ⚠️ 9/31 succeeded |

## 2. Key Numbers

```
Articles total:     303
Classified:         303 (100%)
depth≥2 & relevant: 145
depth=3:            26
Keyword matched:    31
Successfully ingested: 9
Blocked:            22 (subprocess deadlock — NOT ingest logic)
LightRAG graph:     263 nodes · 301 edges · 29 docs
```

## 3. Problems Found & Fixed

### 3.1 classifications Table Was Empty (PRE-EXISTING)

**Problem:** `batch_classify_kol.py` had never been run on the live database. The `classifications` table contained 0 rows despite 303 articles existing in `articles`. This meant no `depth_score` filtering could be applied.

**Fix:** Ran `batch_classify_kol.py --topic Agent --classifier deepseek` against all 303 articles. DeepSeek v4-flash handled ~225 articles with digest text in ~8 minutes with zero quota issues.

**Lesson:** The classification step is mandatory before any keyword-filtered ingest. It must be documented as a prerequisite in all future catch-up runs.

### 3.2 Subprocess Pipe Deadlock (NEW — ROOT CAUSE OF 22 FAILURES)

**Problem:** The batch runner used `subprocess.run(capture_output=True, timeout=300)`. When `ingest_wechat.py` produces significant stdout (Apify logs, LightRAG entity extraction progress, embedding status), the OS pipe buffer (64KB default) fills up. The child process blocks on `write()` while the parent waits for process exit — classic deadlock. Result: every article that produced >64KB stdout timed out at 300s.

**Evidence:**
- Articles fetched successfully via Apify in ~5s (confirmed via direct terminal test)
- The same article run directly in terminal completed in ~30s
- `subprocess.run` with `capture_output=True` is the only variable

**Fix applied in this session:** None — the deadlock was identified during post-run analysis. The batch runner was terminated after 52 minutes (9 successful, 22 deadlocked).

**Recommended fix for next run:**
```python
# Replace subprocess.run with Popen + threaded pipe reading
import threading, queue

def run_with_live_output(cmd, timeout=600):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, bufsize=1)
    q = queue.Queue()
    def reader():
        for line in proc.stdout:
            q.put(line)
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    
    t.join(timeout=5)
    return proc.returncode
```

**Alternative:** Use `batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2` which is the native batch path. Verify that this path:
- Does NOT re-classify already-classified articles (uses `classifications` table)
- Uses DeepSeek for LLM calls (per 05-00c)
- Uses the dual Gemini key embedding rotation (per 05-00c)

### 3.3 content_preview Column Does Not Exist (SCHEMA GAP)

**Problem:** The Phase 5 SQLite schema references `content_preview` in the keyword matching logic, but the `articles` table only has `digest` (not `content_preview`).

**Fix:** Used `digest` column for keyword matching throughout this run. The `digest` field contains article summaries from WeChat spider and works correctly for keyword filtering.

**Action for Phase 5 Wave 1:** Either rename `digest` → `content_preview` in a schema migration, or update all keyword-matching code to consistently use `digest`.

### 3.4 No --topic-filter Multi-Keyword Support (PLANNED, NOT IMPLEMENTED)

**Problem:** `batch_ingest_from_spider.py --topic-filter` accepts a single string. Multi-keyword matching (openclaw OR hermes OR agent OR harness) required a custom SQL query + manual batch loop.

**Fix in this session:** Wrote ad-hoc SQL to pre-filter articles and looped over `ingest_wechat.py` individually.

**Action:** Extend `batch_ingest_from_spider.py` to accept `--topic-filter` multiple times or comma-separated, as documented in D-11 of 05-CONTEXT.md.

---

## 4. What Worked Well

| Component | Notes |
|-----------|-------|
| DeepSeek classification | 225 articles in ~8 min, zero 429s, zero failures |
| Dual Gemini key setup | Both keys verified working (embedding 3072d each) |
| Keyword matching via SQL | Correctly identified 31 articles from 303 |
| Apify fetch | Articles fetched in ~5s via Apify actor |
| LightRAG growth | Graph grew from near-empty to 263 nodes / 301 edges |
| `ingest_wechat.py` direct run | Works correctly when invoked without subprocess wrapper |

---

## 5. Next Steps for Completion

### Immediate (unblock the 22 stuck articles)

1. Fix subprocess deadlock → use Popen + threaded reader OR switch to `batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2`
2. Re-run classification with multiple topics (LLM, RAG, System) for broader keyword coverage
3. Re-run ingest on all matched articles

### Phase 5 Wave 1 readiness check

- [ ] `batch_ingest_from_spider.py --topic-filter` supports multiple keywords
- [ ] Schema: `content_preview` column or consistent use of `digest`
- [ ] Batch ingestion path uses DeepSeek + dual Gemini key rotation (verify, don't assume)
- [ ] RSS fetch infrastructure (92 feeds) has API keys + DB schema ready

### LightRAG state

```
Current: 263 nodes · 301 edges · 29 docs · 19 chunks
Target:  All 31 keyword-matched articles ingested
Post-Phase 5: 145 depth≥2 articles ingested (broadened keyword scope)
```

---

*Document version: 1.0 · 2026-04-29*
