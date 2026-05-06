# Cron Failure Mode Predictions — 2026-05-06 06:00 ADT

**Audience:** debug session tomorrow morning when cron data is in.
**Goal:** predict where cron is most likely to fail, what symptoms to grep, what queries confirm.
**Method:** code analysis of `batch_ingest_from_spider.py` + today's fix history (commits af01315, 359058b, e3116d8, 8ac3cb1, 5c602a3, ca51bdd, 5d7f4e5, ecaa2df, e15c17a).

---

## TL;DR — Top 3 most-likely failure modes

| Rank | Mode | Probability | Impact |
|------|------|-------------|--------|
| 1 | **Phase 2b+ collision** if not finished by 06:00 | 50% | shared resource race |
| 2 | **async-drain hang (D-10.09)** mid-batch | 70% partial | per-event 5-15min delay |
| 3 | **content_hash post-ainsert "not PROCESSED" warning** still firing | 30% | content_hash NULL → unnecessary re-scrape next run |

If everything works, expected outcome: **8-15 OK ingests** in 1-3h cron window.

---

## Code-grounded analysis

### Candidate selection (line 1298-1310)

```sql
SELECT a.id, a.title, a.url, acc.name, c.depth_score, a.body, a.digest
FROM articles a
JOIN accounts acc ON a.account_id = acc.id
LEFT JOIN classifications c ON ...
WHERE (c.topic IS NULL OR ({topic LIKE patterns}))
  AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
ORDER BY a.id
```

**Anchor facts:**
- Excludes only `status='ok'`. **Articles with `skipped`, `skipped_graded`, `failed`, `skipped_ingested` ARE re-pulled.** This is by design — auto-recovery after code fixes.
- FIFO `ORDER BY a.id` — cron processes lowest article IDs first.
- `--max-articles N` caps SUCCESSFUL ingests (line 1332-1334), not total processed. Skip events don't count toward cap.

**Implication for tomorrow:**
- Phase 2b+ articles already 'ok'-ed are excluded. Already-skipped articles get retried.
- If Phase 2b+ ate the easy articles, cron starts on harder leftovers (low depth, dead URLs, lengthy 60-img beasts).

---

## Failure modes, ranked

### 🔴 1. Phase 2b+ Collision

**Trigger:** Phase 2b+ tmux still running at 06:00 ADT.

**Risk paths:**
- Both processes call Apify → quota contention (Apify standard token usually fine, but bursts could 429)
- Both write to `ingestions` table → row-level lock or `INSERT OR REPLACE` race
- Both write to LightRAG storage (shared `lightrag_storage/` dir) → vdb_*.json full-rewrite races
- Both write to `articles.body` → idempotency guard `length(body) < 500` partially protects, but small-body race possible

**Symptoms:**
- DB query: `ingestions` rows interleaved between two timestamps' bursts
- Log query: 2 separate log files writing simultaneously
- Anomaly: same `article_id` appearing in two `ingestions` rows with different timestamps (INSERT OR REPLACE means only one survives)

**Confirm:**
```bash
ssh hermes "tmux ls 2>&1 && pgrep -af batch_ingest"
# If 2+ batch_ingest processes alive at 06:00 → collision
```

```sql
SELECT article_id, COUNT(*) cnt
FROM ingestions
WHERE date(ingested_at) = '2026-05-06'
GROUP BY article_id
HAVING cnt > 1;
-- Expected 0 rows (UNIQUE constraint on article_id) — but inspect timestamps
```

**Quick fix if happens:** kill the older process (Phase 2b+), let cron continue. Phase 2b+ progress is preserved in articles.body.

---

### 🔴 2. async-drain Hang (D-10.09, unfixed)

**Trigger:** post-ainsert async cleanup of vision/embedding workers.
Pre-existing architectural bug. Bug 1 (timeout 1800s) reduces frequency but doesn't fix root cause.

**Symptoms:**
- DB: ingestions row marked `ok`
- Process: still running, no new DB writes for 5-15 minutes
- Log: stops at "Storage finalize" or "Vision drain" stage

**Confirm:**
```bash
# At 06:30, 07:00, 07:30 — check process activity
pgrep -af batch_ingest_from_spider
# DB last write timestamp:
sqlite3 data/kol_scan.db "SELECT MAX(ingested_at) FROM ingestions WHERE date(ingested_at)='2026-05-06'"
# If process alive but DB last write > 10 min ago → hang
```

**Symptom signature in log:**
```
Vision drain: 12 tasks pending, 120s deadline
... (silence for 10+ min) ...
```

**Quick fix if hang dominates:** accept lower throughput (each hang = 5-15 min). If >40% articles hang → kill, restart with smaller batch.

---

### 🟡 3. content_hash Post-Ainsert "not PROCESSED" Warning (regression check on 359058b)

**Trigger:** `aget_docs_by_ids` returns a `DocStatus.PROCESSED` enum that my fix (`_status_is_processed`) doesn't recognize. Possible if LightRAG version on Hermes differs from local, or enum behavior changes.

**Symptoms in log:**
```
post-ainsert verification: doc <hash> status=<DocStatus.PROCESSED: 'processed'> (not PROCESSED) — skipping content_hash write
```

**This is the SAME warning that fired pre-359058b.** If still firing, my fix didn't transfer.

**Confirm:**
```bash
# Count occurrences in cron log:
grep -c "not PROCESSED.*skipping content_hash write" /tmp/cron-2026-05-06.log
# Pre-fix baseline: ~all OK ingests had this firing. Post-fix: should be 0.
```

**DB query:**
```sql
SELECT COUNT(*) FROM articles
WHERE content_hash IS NULL
  AND id IN (SELECT article_id FROM ingestions WHERE status='ok' AND date(ingested_at)='2026-05-06');
-- Expected 0. If non-zero → content_hash write blocked → regression confirmed.
```

**Impact if still firing:** `articles.content_hash` stays NULL → next run can't checkpoint → re-scrapes unnecessarily. Doesn't fail ingest, just inefficient.

---

### 🟡 4. 60s Embedding Worker Timeout (known, Track 3 + Phase 2b+)

**Trigger:** sub-doc (image) embedding. Hard-coded 60s timeout vs LLM 1800s asymmetry.

**Symptoms:**
- Log: `EmbeddingTimeout` or `embedding worker timeout`
- DB: article still gets 'ok' status (subdoc failure doesn't kill main ingest)
- Graph quality degraded — image entities for that article have fewer relations

**Confirm:**
```bash
grep -cE "Embedding.*timeout|worker.*60" /tmp/cron-2026-05-06.log
```

**Severity:** depends on frequency. 10-20% of articles → ignore for now. >50% → escalate.

**Quick fix:** raise embedding timeout to 300s (env var or hardcoded). Out of tonight's scope — defer to post-cron analysis.

---

### 🟡 5. Pool Exhaustion / Depth-1 Articles

**Trigger:** Phase 2b+ already processed all depth>=2 articles in the topic-matched pool. Cron starts on depth=1 articles which `min_depth=2` filter rejects.

**Symptoms:**
- DB: Cron era shows mostly `skipped` rows with no `ok`
- Log: "filtered out: depth=1 < min_depth=2" repeated
- Possible: cron exits cleanly with 0 OK because pool depleted of qualifying articles

**Confirm:**
```sql
SELECT i.status, c.depth_score, COUNT(*)
FROM ingestions i
JOIN classifications c ON c.article_id = i.article_id
WHERE date(i.ingested_at) = '2026-05-06'
GROUP BY i.status, c.depth_score
ORDER BY i.status, c.depth_score;
```

**Impact:** disappointing low OK count, but not a bug — pool is what it is.

**Quick fix:** lower `--min-depth` to 1 in next run, OR scan more KOLs to grow pool.

---

### 🟢 6. Apify Cascade Path (likely WORKS — fixes verified)

**Why monitored:** ecaa2df + SCR-06 should mean cascade short-circuits on Apify markdown success. Audit (ece03ae) flagged remaining 🟡 issues but no 🔴.

**Confirm working:**
```bash
# Should NOT see 4-layer-cascade waste any more
grep -c "Failed to connect to CDP" /tmp/cron-2026-05-06.log
# Pre-ecaa2df: every article × 6 sub-pages ≈ thousands. Post: should be 0.
```

If non-zero: ecaa2df regression somewhere. Investigate.

---

### 🟢 7. UA img_urls Merge (af01315) — should work

**Why monitored:** mock-tested, mirrors legacy. UA fallback path now preserves img_urls.

**Confirm:**
```bash
grep "UA scrape:" /tmp/cron-2026-05-06.log | head -5
# Look for articles using UA fallback. Then for each, check if image entities make it to graph.
```

Real verification requires Vertex graph inspection; cheap heuristic: count vision_success per UA-fallback article in log.

---

### 🟢 8. Bug 3 body persist (8ac3cb1) — should work

**Why monitored:** verified in Track 3 (article 339).

**Confirm:**
```sql
SELECT COUNT(*) FROM articles a
WHERE length(coalesce(body, '')) > 500
  AND id IN (
    SELECT article_id FROM ingestions
    WHERE status IN ('ok','failed','skipped')
      AND date(ingested_at) = '2026-05-06'
  );
```

Pre-fix: failed/skipped articles often had body=NULL despite scrape success. Post-fix: should be very high (most processed articles have body persisted).

---

### 🟢 9. Cognee structlog noise (e3116d8) — should work

**Confirm:**
```bash
wc -l /tmp/cron-2026-05-06.log
# Pre-e3116d8: ~600 noise lines per run. Post: dramatically lower.
```

If log is still huge → fix didn't transfer (LOG_LEVEL env not respected for some reason).

---

## Tomorrow morning's debug command sequence

When 09:27 ADT alarm wakes me with the morning analysis, the priority queries:

```bash
# 1. Process state
ssh hermes "tmux ls; pgrep -af batch_ingest"

# 2. DB outcome
sqlite3 data/kol_scan.db "
SELECT status, COUNT(*) FROM ingestions
WHERE date(ingested_at) = '2026-05-06' GROUP BY status
"

# 3. Per-article timing
sqlite3 data/kol_scan.db "
SELECT id, article_id, status, ingested_at FROM ingestions
WHERE date(ingested_at) = '2026-05-06' ORDER BY ingested_at
"

# 4. Regression checks
LOG=/tmp/cron-2026-05-06-XXXX.log
echo "359058b regression:"
grep -c "not PROCESSED.*skipping content_hash write" $LOG

echo "ecaa2df regression:"
grep -c "Failed to connect to CDP" $LOG

echo "60s timeout count:"
grep -cE "Embedding.*timeout|EmbeddingTimeout" $LOG

echo "async-drain hangs (gap detection):"
# Look for gaps > 10 min between log timestamps when process alive

# 5. Graph state
ssh hermes "ls -la ~/.hermes/omonigraph-vault/lightrag_storage/*.json *.graphml | head -5"
```

---

## Severity-action matrix

| Outcome | Action |
|---------|--------|
| 8-15 OK, no regressions | ✅ Day-1 success. Phase 5 wave 1 unblocked. |
| 4-7 OK, some hangs/timeouts | 🟡 Acceptable. Schedule fix for 60s embedding timeout. |
| 1-3 OK, multiple regressions | 🔴 Investigate which fix didn't transfer. Possibly rollback. |
| 0 OK | 🚨 Major regression OR pool exhaustion. Inspect candidate query first. |

---

## Confidence

This document is **predictive**, written 2026-05-05 evening before cron fires. Some predictions will be wrong — those mismatches are themselves data.

If a failure mode I didn't list dominates, that's the most interesting finding (unknown unknown).

*End of predictions.*
