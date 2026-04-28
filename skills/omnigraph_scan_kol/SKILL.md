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

1. **Check session**: `browser_navigate` to `https://mp.weixin.qq.com/` (ROOT URL — not `/cgi-bin/home`).
   The root auto-redirects with a fresh `?token=...` parameter. Subpath without token
   shows "请重新登录" even when cookies are still valid server-side.
2. **If dashboard visible** (user stats, recent articles) → session active, run `scripts/scan_kol.sh`
3. **If "请重新登录" visible** → session expired but cookies still valid:
   - `browser_click` on the "登录" link/button
   - Wait 3s for redirect to dashboard
   - Verify with `browser_snapshot` (look for user content)
   - Then run `scripts/scan_kol.sh`
4. **If clicking login still shows re-login page** → cookies truly expired, notify user via Telegram: "WeChat MP session expired. Please open mp.weixin.qq.com in your browser, scan the QR code, then say 'scan KOL'."

### Trigger: cron fires

Same as above, but on cookie-level failure, deliver Telegram notification
(since user may not be watching the chat).

### Retry on rate limit

If `scan_kol.sh` exits with SESSION_ERROR (ret=200013 mid-scan), wait 30 minutes then re-run the full Decision Tree (step 1–4). If retry also fails, stop and notify.

## Guard Clauses

- **DB not found**: If `data/kol_scan.db` does not exist, respond:
  "Knowledge base not initialized. Run `python batch_scan_kol.py --days-back 120` first to do the initial full scan."
- **kol_config.py not found**: Respond:
  "WeChat credentials not configured. See `docs/KOL_COLDSTART_SETUP.md`."

## Anti-Crawl & Reliability

- **SESSION_LIMIT = 54** (in `batch_scan_kol.py:35`): one API request per KOL account.
  WeChat real limit is ~60 per session. 54 leaves 6-request headroom for pagination.
  If you add accounts, raise this proportionally — but never exceed 58.
- **Account order is RANDOMIZED** (`random.shuffle` before iteration). This ensures
  that if SESSION_LIMIT truncation happens, different accounts get skipped each day.
- **Inter-account delay = 5.0s** (`RATE_LIMIT_SLEEP_ACCOUNTS` in `spiders/wechat_spider.py:22`).
  54 accounts × 5s = 4.5 min total.
- **Health check cron** (`e7afccd9931b`, 07:55 daily): validates CDP reachable,
  WeChat session valid, auto-refreshes TOKEN + COOKIE via CDP WebSocket into
  `kol_config.py`, then verifies with a single-account test scan. Sends Telegram
  on failure; silent on success.

## Cron Reliability — Diagnosing Failures

When the unattended cron fails, diagnose in this order:

1. **Check the cron session dump**: `~/.hermes/sessions/session_cron_df7dc3fa0390_*.json`
   — `model` field tells you which LLM was used. If `gemini-3-flash-preview`,
   DeepSeek was unreachable and Hermes fell back to a model that rejects API keys.
2. **Check the request dump**: `~/.hermes/sessions/request_dump_cron_df7dc3fa0390_*.json`
   — `reason` + `error.message` reveals the exact API error.
3. **Common root causes**:
   - DeepSeek API down → fallback to gemini-3-flash-preview → 401 UNAUTHENTICATED
     (fix: set `fallback_providers` in `~/.hermes/config.yaml` to `gemini-3.1-flash-lite-preview`)
   - **VERTEXAI environment contamination**: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_API_KEY`,
     `GOOGLE_APPLICATION_CREDENTIALS` in `~/.bashrc` or `~/.gemini/.env` force ALL
     Gemini calls through Vertex AI OAuth2 → 401 even with valid API keys.
     Fix: remove/comment those lines from bashrc, verify with `echo $GOOGLE_CLOUD_PROJECT` (should be empty).
   - `kol_config.py` TOKEN stale → ret=200003 (fix: run health check to auto-refresh)
   - `kol_config.py` COOKIE stale → ret=200003 (same fix)
   - SESSION_LIMIT too low → accounts silently truncated
   - CDP browser not running → browser_navigate fails (health check catches this)
4. **Verify DB coverage**: `SELECT DISTINCT account_id FROM articles WHERE scanned_at LIKE '<today>%'`
   — if count < 53, some accounts were skipped.

## References

- Session refresh steps: `references/session-refresh.md`
- Crawl safety: `scripts/scan_kol.sh` stops before WeChat's ~60 request limit
