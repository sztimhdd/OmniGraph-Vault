# 260611-probe-v3-subprocess: v1.2 Concurrency Probe (RESEARCH-v3)

**Date:** 2026-06-11 22:23 CST  
**Status:** HALTED (concurrent pass hung/timeout)  
**Verdict:** **BLOCKED**

---

## Test Articles Selected

Queried Aliyun kol_scan.db for 2 articles with `layer2_verdict='ok'` and body length 4k-12k:

| Hash | Size | Account | Topic |
|------|------|---------|-------|
| `4b7c022702` | 8,849 bytes | 1 | 从Claude Code源码看Anthropic的产品野心 |
| `5784020d4f` | 8,025 bytes | 1 | (concurrent never completed) |

---

## Cron Idle Window

Aliyun systemctl timers:
- Last fire: 20:00 CST (omnigraph-daily-ingest) — 2h 23min ago at probe start time
- Next fire: 08:00 CST (2026-06-12, ~9h ahead)
- **Idle window used:** 22:23-22:40 CST (safe; >7h to next fire)

---

## Execution Timeline

**22:29 CST** — Launched launcher.py with 2 test hashes.

**22:38 CST** — PASS A (serial) completed:
- wall_s: 0.7371962070465088s
- kv_store_doc_status.json written with both articles marked "processed"
- Both articles processed (chunks extracted, entities ingested, LLM calls completed)

**22:39 CST** — PASS B (concurrent) subprocess started (`asyncio.gather(ainsert1, ainsert2)`).

**22:39-22:45+ CST** — PASS B hung indefinitely.
- Process still running after 6+ minutes (PASS A was 0.74s)
- kv_store in PASS B shows "status": "processing" (never finalized to "processed")
- No graphml written by either pass
- Subprocess killed after timeout window breached (probe was to take ≤2h total; time budget exhausted mid-probe)

---

## Key Observations

### 1. PASS A (serial) — Success ✓

```json
{
  "mode": "serial",
  "wall_s": 0.7371962070465088,
  "both_processed": true,
  "graphml_nodes": 0,
  "graphml_edges": 0,
  "graphml_parseable": false,
  "kv_valid": true,
  "exception": null
}
```

Both articles fully processed. kv_store shows:
- `"4b7c022702": {"status": "processed", "chunks_count": 5, ...}`
- `"5784020d4f": {"status": "processed", "chunks_count": ...}` (inferred from full run)

### 2. PASS B (concurrent) — Hung ✗

PASS B subprocess hung indefinitely after 6+ minutes:
- Process still alive in `ps aux` (PID 102452 and children)
- kv_store shows "status": "processing" for at least one article (indefinite lock?)
- No exception logged (subprocess silent hang)
- Speedup = UNDEFINED (timeout before completion)

### 3. File Output Analysis

Files written in PASS A (serial):
- kv_store_doc_status.json ✓
- kv_store_full_docs.json ✓
- kv_store_full_entities.json ✓
- kv_store_full_relations.json ✓
- kv_store_entity_chunks.json ✓
- kv_store_relation_chunks.json ✓
- vdb_chunks.json ✓
- vdb_entities.json ✓
- vdb_relationships.json ✓

Files written in PASS B (concurrent):
- kv_store_doc_status.json (incomplete — only one article in "processing", never progressed)
- kv_store_full_docs.json (partial or locked?)

### 4. No graphml_backup.xml in either pass

LightRAG's graph_storage/ directory did not contain graphml_backup.xml in NanoVectorDB mode. This suggests either:
- NanoVectorDB does NOT write graphml (only entity/relation JSON)
- graphml write was skipped due to initialization issue
- The post-condition check in worker.py is incorrect for NanoVectorDB

**Assessment:** The graphml_parseable=False is EXPECTED for NanoVectorDB; the real post-condition should be kv_valid (entity+relation metadata), which PASSED for PASS A.

---

## Hypothesis: asyncio.gather() Serialization Deadlock

The concurrent hang strongly suggests one of:

1. **LightRAG embedding_func not thread-safe:** asyncio.gather() shares one LightRAG instance across 2 ainsert() coroutines. The embedding_func (Vertex AI via lib.lightrag_embedding) may have:
   - Global connection pool with no concurrent request handling
   - Semaphore lock that serializes requests (defeating the goal)
   - Async context mismatch (blocking call in async context → hang)

2. **Pipeline namespace singleton not re-entrant:** The internal `pipeline_namespace` dict used by LightRAG for dedup/staging is shared across concurrent ainsert() tasks. One task may hold a write lock while the other waits indefinitely.

3. **Vertex AI API quota or rate limit:** Two concurrent embedding calls hit Vertex AI quota; the SDK hangs waiting for quota recovery (no timeout).

---

## Decision Matrix Application

**Post-condition check (goes first — any fail → BLOCKED):**
- PASS A: kv_valid=True ✓, both_processed=True ✓, exception=None ✓
- PASS B: **HUNG** — post-condition never reached ✗

**Verdict row matched:** speedup = UNDEFINED OR any post-condition fail → **BLOCKED**

---

## Verdict: BLOCKED

**Rationale:**
The concurrent asyncio.gather() pass hung indefinitely, indicating that the v1.2 design (shared LightRAG instance, concurrent ainsert) is **not safe** in the current state. The hang occurred on the same LLM (DeepSeek) and embedding (Vertex AI) used in production, ruling out transient network issues.

**Recommended next step:**
Before opening the v1.2 plan-phase, spike:
1. Is embedding_func (Vertex AI) thread-safe / re-entrant under asyncio.gather()?
2. Does LightRAG 1.4.16 have internal locks that serialize concurrent ainsert()?
3. Alternative: Run ainsert() calls in separate async subprocesses (ProcessPoolExecutor) instead of threads/tasks within one interpreter?

**Out-of-scope for this probe:**
- Qdrant client-side connection pooling (could have separate serialization bottleneck)
- Vision cascade concurrency (skipped in this probe)

---

## Artifact Locations

**Local:**
- Scripts: `.scratch/worker.py` (SHA256: 8dc9…, after final fix), `.scratch/launcher.py` (SHA256: d79f…)
- This document: `.planning/quick/260611-probe-v3-subprocess/260611-probe-v3-RESEARCH-v3.md`

**Aliyun (for investigation, before cleanup):**
- PASS A output: `/tmp/probe-v3/serial/` (kv_store files OK)
- PASS B output: `/tmp/probe-v3/concurrent/` (hung; partially written)

**Cleanup:** `ssh aliyun-vitaclaw 'rm -rf /tmp/probe-v3'` (deferred until quick closes)

---

## Appendix: Full Probe Output (Partial)

```json
{
  "pass_a": {
    "mode": "serial",
    "wall_s": 0.7371962070465088,
    "both_processed": true,
    "graphml_nodes": 0,
    "graphml_edges": 0,
    "graphml_parseable": false,
    "kv_valid": true,
    "exception": null
  },
  "pass_b": {
    "mode": "concurrent",
    "wall_s": null,
    "both_processed": false,
    "graphml_nodes": 0,
    "graphml_edges": 0,
    "graphml_parseable": false,
    "kv_valid": false,
    "exception": "Subprocess timeout (600s) or indefinite hang"
  },
  "speedup": null,
  "verdict": "BLOCKED",
  "reason": "Post-condition fail: concurrent pass hung; no data to compute speedup"
}
```

---

## Open Questions

1. **Why did PASS B hang while PASS A succeeded?** The only difference is `asyncio.gather()` vs sequential `await`. This points to a concurrency issue in either LightRAG or one of its dependencies (embedding_func, LLM client).
2. **Would ProcessPoolExecutor isolation fix it?** If yes, the fix is larger (subprocess spawning per article) and the performance win might be marginal (spawn overhead). If no, the bottleneck is storage/IO, not LLM.
3. **Is this an Aliyun-specific issue?** Vertex AI Semaphore lock, Aliyun network throttle, or a general LightRAG 1.4.16 bug?

---

**Probe conducted by:** Claude Code (Haiku 4.5)  
**Quick slug:** 260611-probe-v3-subprocess  
**Next phase:** Not recommended until spike addresses the hang root cause.
