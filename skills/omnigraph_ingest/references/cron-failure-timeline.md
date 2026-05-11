# 2026-05-08 09:00 Cron Ingest — Full Failure Timeline

## Summary

Cron used wrong model (Gemini) + scraping cascade without circuit breaker +
900s terminal timeout = 1/3 articles ingested, process killed mid-vision-drain.
User had to manually re-run via tmux.

## Timeline (ADT, UTC-3)

```
09:00:38  Cron starts
          MODEL: gemini-2.5-flash (WRONG — should be deepseek-v4-flash)
          base_url: http://127.0.0.1:8787 (gateway proxy)

09:00:44  Layer1 batch [4s]
          23 articles → 11 candidates, 12 rejected
          Rejection: 营销/招聘/视觉/CV/具身智能 direction

09:00:48  LightRAG init [7s]
          5643 nodes, 7292 edges, 405 chunks

09:00:55  Layer2 scrape — 5 articles, scrape-first loop [3.5 min]
          EACH ARTICLE hits same cascade:
            Apify → "Maximum charged results > 0" (30s)
            CDP   → "Timeout 30000ms exceeded" (30s)
            MCP   → "unparseable result" (30s × 2 retry)
            UA    → HTTP 200, success (< 5s)

          Articles:
          [1/5] 叶小钗 "画布Agent"          13 imgs
          [2/5] AI前线 "Anthropic黑箱"      15 imgs
          [3/5] AI前线 "Vercel Open Agents"  7 imgs
          [4/5] 字节笔记本 "Obsidian+Coding"  5 imgs
          [5/5] AINLP "DeepSeek-V4并行"     11 imgs

09:04:26  Layer2 classify [18s]
          5 → 3 ok, 2 rejected (产品软文 id=831, 视觉图像 id=850)

09:04:26  Ingest #1: "Anthropic最新论文撬开大模型黑箱"
          ├ Chunks: 5 → 96 entities + 103 relations
          ├ Merge Phase1: 09:08:51-09:09:56 [65s]
          ├ Merge Phase2: 09:09:22-09:09:56 [34s]
          ├ Merge Phase3 (write): 09:09:56-09:10:28 [32s]
          └ Vision Cascade: 20 images, 09:10:28-09:15:21 [~5 min]
            SiliconFlow 20/20 success, 7-28s each

09:15:21  Article #1 complete
          Graph: 5706 nodes, 7394 edges (+63/+102)
          #2 "Vercel Open Agents" and #3 "Obsidian+Coding" queued

09:15:46  ⏰ TERMINAL TIMEOUT (900s)
          Process killed by Hermes terminal tool
          Cron reports: "timed out after 900 seconds"
```

## Root Causes (by impact)

| # | Root Cause | Time Wasted | Fix |
|---|-----------|------------|-----|
| R1 | Gemini model (48% slower, 250 RPD) | +4 min/article | Pin `deepseek-v4-flash` in cron |
| R2 | Cascade no circuit breaker | 600s (67% of budget) | `SCRAPE_CASCADE=ua` or pre-flight probe |
| R3 | 900s timeout | Killed at 908s | tmux detached session |
| R4 | Vision async drain | 5 min at tail | Acceptable — needed for quality |

## Data Loss

- **Planned:** 10 articles
- **Layer2 passed:** 3 articles
- **Ingested:** 1 article (96 entities, 103 relations, 20 vision images)
- **Queued but killed:** 2 articles (#2 Vercel, #3 Obsidian)
- **Layer1 rejected:** 12 articles
- **Never reached:** 8 articles (out of 23 total)

## Residual State

- LightRAG: 93 docs, all `processed`, 0 zombies
  → Article #1 successfully committed before timeout
  → Articles #2/#3: pipeline stopped before LightRAG commit
- `ingestions` table: 14 `skipped` entries, 0 `ok`
  → Ingestions table update was also interrupted

## Manual Remediation Required

Only 1/3 Layer2-passed articles ingested. User launched tmux-based
manual run which processed the remaining 94-article full pool sweep.

**⚠️ Note:** Manual re-run with `--max-articles 2` pulled 3 AINLP articles
("让LLM互相审稿", "从零开始构建自进化智能体", "Claude Code源码逆向工程")
from the backlog instead of the 2 remaining Layer2 candidates
(#2 Obsidian+CodingAgent, #3 DeepSeek-V4并行策略).
The remaining 2 Layer2 articles are still un-ingested as of session end.

**Root cause:** `--from-db` queries all articles without `content_hash`,
sorted by ID, not scoped to today's scan. Use `--days-back 1` to scope.

## References

- Cron session dump: `~/.hermes/sessions/session_cron_2b7a8bee53e0_20260508_090038.json`
- Script: `scripts/cron_daily_ingest.sh` (tmux-based ingest launcher)
- Main ingest: `batch_ingest_from_spider.py --from-db --max-articles 10`
- Scraper cascade: `lib/scraper.py:_scrape_wechat()`
