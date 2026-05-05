# DB Reset Plan — 2026-05-05

## Current State Inventory

| Cohort | Body | Count | Root Cause |
|--------|------|:-----:|------------|
| `overnight_scr06` | no_body | 113 | SCR-06 scrape-first flow: scrape ran but body NOT persisted to `articles.body`. All skipped by graded probe false-negative or depth gate. |
| `older` | has_body | 15 | Pre-5/4 articles with body intact. Skipped by older classification/depth gate. |
| `older` | no_body | 2 | Pre-5/4 articles never scraped (body=NULL). |
| `today_other` | has_body | 8 | Today's ingestion (E2E + misc). Body in DB. |
| `today_other` | no_body | 7 | Today's ingestion, no body. |
| **Total** | | **145** | |

## Recovery Cost Matrix

| Cohort | Count | Body Recoverable | Scrape Cost (per article) | Total Scrape Cost | Risk |
|--------|:-----:|:----------------:|:-------------------------:|:-----------------:|------|
| `overnight_scr06` | 113 | ❌ (SCR-06 bug) | ~150s (UA scrape) | ~4.7 hours | Re-scrape same URLs — WeChat may anti-crawl. CDP overhead if UA blocked. |
| `older/has_body` | 15 | ✅ already present | 0 | 0 | Re-classify + ingest only. |
| `older/no_body` | 2 | ❌ | ~150s | ~5 min | Low volume, low risk. |
| `today_other/has_body` | 8 | ✅ already present | 0 | 0 | Re-classify + ingest only. |
| `today_other/no_body` | 7 | ❌ | ~150s | ~17.5 min | Low volume. |

## Proposed Reset SQL

### Phase 2a: Low-cost reset (has_body rows)
These articles already have body content — just need re-classification and ingestion. No scrape cost.

```sql
-- Reset has_body skipped rows to allow re-ingest
DELETE FROM ingestions
WHERE status = 'skipped'
  AND article_id IN (
    SELECT a.id FROM articles a
    JOIN ingestions i ON i.article_id = a.id
    WHERE i.status = 'skipped' AND length(coalesce(a.body, '')) > 500
  );
```

Expected: **23 rows** (15 older + 8 today_other) — ~23 × 30s ingest ≈ 11.5 min.

### Phase 2b: SCR-06 overnight victims (no_body)
These 113 articles need full re-scrape. Two approaches:

**Option A — Batch re-scrape (risky):** Reset all 113 and let cron re-scrape.
- Cost: ~4.7 hours serial, ~113 WeChat HTTP requests (risks rate-limit)
- SQL:
  ```sql
  DELETE FROM ingestions
  WHERE status = 'skipped'
    AND ingested_at BETWEEN '2026-05-05 00:57' AND '2026-05-05 01:43';
  ```

**Option B — No-reset (safe):** Leave as-is. These articles were scraped once, body was lost. If they're high-value, manually re-ingest via `omnigraph_ingest` skill (one-off).

### Phase 2c: older/today_other no_body (9 rows)
Same as SCR-06 — needs re-scrape. Low volume, low risk.

```sql
DELETE FROM ingestions
WHERE status = 'skipped'
  AND article_id IN (
    SELECT a.id FROM articles a
    JOIN ingestions i ON i.article_id = a.id
    WHERE i.status = 'skipped' AND length(coalesce(a.body, '')) <= 500
      AND i.ingested_at NOT BETWEEN '2026-05-05 00:57' AND '2026-05-05 01:43'
  );
```

Expected: **9 rows** — ~9 × 150s ≈ 22.5 min scrape.

## Risk Analysis

1. **WeChat rate-limit**: 113 re-scrape requests in one batch may trigger `ret=200013` (freq control). Recommend splitting into 3 batches of ~38 with 30-min cooldown between.
2. **Content hash gap**: `post-ainsert` verification has a case-sensitivity bug (`'processed'` vs `'PROCESSED'`). Even successful re-ingests won't get `content_hash` written. Data is ingested correctly; tracking is broken. Fix pending in separate quick.
3. **SCR-06 root cause**: Body was scraped (UA HTTP 200 confirmed in logs) but `_scrape_wechat` cascade result wasn't persisted to `articles.body` column. Root cause may be in the scrape-first re-classify loop (`batch_ingest_from_spider.py` ~line 1240 area) — investigate separately.
4. **Day-1 cron interaction**: Reset should be done AFTER Day-1 cron completes (avoid race on ingestions table). Or reset before 06:00 ADT so cron picks up reset rows fresh.

## Decision Points

- [ ] **Phase 2a** (23 has_body): Safe, low cost. Do immediately?
- [ ] **Phase 2b** (113 SCR-06): Expensive re-scrape. Execute Option A (reset all) or Option B (manual only)?
- [ ] **Phase 2c** (9 no_body older/today): Low risk. Include with Phase 2a?
- [ ] **Timing**: Before or after Day-1 cron?
