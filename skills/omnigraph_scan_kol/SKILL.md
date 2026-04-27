---
name: omnigraph_scan_kol
description: Daily incremental scan of all WeChat KOL accounts — collects new article titles, URLs, and digests into the SQLite knowledge base. No classification, no full-text ingestion.
triggers:
  - "scan KOL"
  - "check what's new"
  - "scan KOL accounts"
  - "any new articles"
  - "daily scan"
metadata:
  openclaw:
    os: ["linux", "win32"]
    requires:
      bins: ["python", "bash"]
      config: ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
      files: ["kol_config.py", "data/kol_scan.db"]
---

# omnigraph_scan_kol

Daily incremental scan of 54 WeChat KOL accounts. Stores article metadata
(title, URL, digest) into `data/kol_scan.db`. No classification, no LLM calls,
no full-text scraping.

## Cron Setup

```
hermes cronjob add \
  --name "kol-daily-scan" \
  --schedule "0 8 * * *" \
  --prompt "run the omnigraph_scan_kol skill to perform the daily KOL scan"
```

## Decision Tree

### Trigger: user asks to scan

1. Run `scripts/scan_kol.sh`
2. If script succeeds → show summary (N new articles across M accounts)
3. If script fails with session error → attempt browser refresh via `browser_navigate` to `https://mp.weixin.qq.com`, wait 3s, retry once
4. If retry still fails → deliver notification to the user via Telegram:
   "WeChat MP session expired. Please refresh mp.weixin.qq.com in your browser, then say 'scan KOL'."

### Trigger: cron fires

Same as above, but on session failure, always deliver Telegram notification
(since user may not be watching the chat).

## Guard Clauses

- **DB not found**: If `data/kol_scan.db` does not exist, respond:
  "Knowledge base not initialized. Run `python batch_scan_kol.py --days-back 120` first to do the initial full scan."
- **kol_config.py not found**: Respond:
  "WeChat credentials not configured. See `docs/KOL_COLDSTART_SETUP.md`."

## References

- Session refresh steps: `references/session-refresh.md`
- Crawl safety: `scripts/scan_kol.sh` stops before WeChat's ~60 request limit
