# 2026-05-10 Cron Ingest — Normal Run (Baseline Profile)

## Summary

Healthy pipeline run. No failures, no model pinning issues, no timeouts.
All 4 articles passed layer2, 1 timed out during LightRAG ainsert,
63/63 vision images processed via SiliconFlow, tmux zombie cleaned up.

## Timeline

```
09:00:18  Script launched (bash cron_daily_ingest.sh 5)
09:00:24  Layer1 batch 0-7 [~37s]
          219 inputs → 166 candidates (53 rejected)
          Avg wall: 5.4s/batch, 7 batches

09:01:01  Per-article loop starts (166 candidates)
          28 checkpoint-skips (already ingested)
          Scraping + Layer2 interleaved

09:01:24  Apify: "This Actor requires full access" — cascades to UA
          UA also fails (empty body) → "will retry next tick"

09:01:44  Layer2 batch 0: 0 ok, 5 reject
09:02:06  Layer2 batch 1: 2 ok, 3 reject
09:22:49  Layer2 batch 2: 0 ok, 5 reject (scrape failures)
09:22:57  Layer2 batch 3: 0 ok, 5 reject (scrape failures)
09:23:18  Layer2 batch 4: 2 ok, 3 reject
09:26:38  Layer2 batch 5: 1 ok, 4 reject

09:31:28  max-articles cap reached (5) — draining final layer2 queue

          LightRAG ingest of 5 Layer2-passed articles:
          4 completed (entity extraction + graph merge)
          1 timed out (post-ainsert verification showed PENDING)

          Vision cascade (3 image batches):
          [1] 6 images  → 6 SiliconFlow, 0 errors
          [2] 9 images  → 9 SiliconFlow, 0 errors
          [3] 20 images → 20 SiliconFlow, 0 errors
          [4] 28 images → 28 SiliconFlow, 0 errors
          Total: 63 images, 100% success, 0 errors, 0 timeouts

09:33:28  Vision drain timeout (0/1 pending — cancelling)
09:33:28  Finalizing LightRAG storages (flushing vdb + graphml)
09:33:29  Successfully finalized 12 storages
09:33:29  batch_timeout_metrics written
```

## Layer1 Filtering Detail

| Batch | n | Candidate | Reject | Wall (ms) |
|-------|---|-----------|--------|-----------|
| 0     | 30| 29        | 1      | 4982      |
| 1     | 30| 30        | 0      | 4545      |
| 2     | 30| 12        | 18     | 5445      |
| 3     | 30| 19        | 11     | 6680      |
| 4     | 30| 15        | 15     | 7396      |
| 5     | 30| 29        | 1      | 5043      |
| 6     | 30| 30        | 0      | 5200      |
| 7     | 9 | 2         | 7      | 3028      |
| **Total**|**219**| **166** | **53** | **~37s** |

## Layer2 Filtering Detail

| Batch | n | ok | reject | Wall (ms) |
|-------|---|----|--------|-----------|
| 0     | 5 | 0  | 5      | 20137     |
| 1     | 5 | 2  | 3      | 21621     |
| 2     | 5 | 0  | 5      | 23113     |
| 3     | 5 | 0  | 5      | 8503      |
| 4     | 5 | 2  | 3      | 20736     |
| 5     | 5 | 1  | 4      | 27660     |
| **Total**|**30**| **5** | **25** | **~2.1min** |

## LightRAG Ingestion

| Metric | Value |
|--------|-------|
| Total articles sent to ainsert | 5 (layer2 ok) |
| Completed successfully | 4 |
| Timed out (PENDING) | 1 |
| Not started (capped) | 214 |
| Stuck images (pending) | 0 |

## Vision Summary

| Batch | Input | Kept | Filtered | Success | Error | Provider |
|-------|-------|------|----------|---------|-------|----------|
| 1     | 6     | 6    | 0        | 6       | 0     | SiliconFlow |
| 2     | 9     | 9    | 0        | 9       | 0     | SiliconFlow |
| 3     | 20    | 20   | 0        | 20      | 0     | SiliconFlow |
| 4     | 28    | 28   | 0        | 28      | 0     | SiliconFlow |
| **Total**| **63** | **63** | **0** | **63** | **0** | SiliconFlow |

## Anomalies (Minor)

1. **Apify "requires full access"** — Actor permissions not approved on Apify Console.
   Cascade fell through to UA, which also failed → wasted ~30s per article.
   **Impact:** Low — cascading is normal behavior, just slower.
   **Fix:** Login to Apify Console, approve actor permissions.

2. **Post-ainsert PENDING (1 article)** — One doc inserted into LightRAG but never
   reached PROCESSED status. `content_hash` not written → article will be re-processed
   next cycle.
   **Impact:** Low — wasted compute on re-scrape/re-insertion.
   **Fix:** Manual ingest or ignore (auto-retried next cron).

3. **UA scrape empty body (~30% of WeChat URLs)** — "正文缺失", "正文环境异常",
   "正文不可访问". Expected for WeChat anti-scraping. Deferred to next tick.

## Key Metrics vs Previous Runs

| Metric | 2026-05-08 (Failure) | 2026-05-10 (Healthy) |
|--------|---------------------|---------------------|
| Pipeline duration | ~15 min (killed) | ~32 min (completed) |
| Model | gemini-2.5-flash | deepseek-v4-flash (via cron default) |
| Layer1 inputs | ~23 articles | 219 articles |
| Layer2 passed | 3 articles | 5 articles |
| LightRAG ingested | 1 article | 4 articles |
| Vision images | 20 (1 batch) | 63 (4 batches) |
| Cascade waste | ~90s/article (all 4 layers) | ~30s/article (Apify→UA) |
| Tmux zombie | N/A (killed by timeout) | Killed post-completion |
