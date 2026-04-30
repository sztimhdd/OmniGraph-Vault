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

## Working Directory

All commands below assume you are **in the repo root** (`/home/sztimhdd/OmniGraph-Vault`).
If running via cron, the default cwd may be `/root/project` — explicitly `cd` to the repo root
using `terminal` before proceeding.

The scan script at `./skills/omnigraph_scan_kol/scripts/scan_kol.sh` resolves the repo root
internally (via `$(cd "$SCRIPT_DIR/../../.." && pwd)`), so it works from any cwd as long as
the path is correct. However, other checks (DB path, config path) use relative paths, so
always ensure you're in the repo root first.

## Decision Tree

### Trigger: user asks to scan / cron fires

1. **cd to repo root**: `cd /home/sztimhdd/OmniGraph-Vault`
2. **Check session**: `browser_navigate` to `https://mp.weixin.qq.com/` (ROOT URL — not `/cgi-bin/home`).
   The root auto-redirects with a fresh `?token=...` parameter. Subpath without token
   shows "请重新登录" even when cookies are still valid server-side.
3. **If dashboard visible** (user stats, recent articles) → session active, run the scan:
   ```bash
   bash ./skills/omnigraph_scan_kol/scripts/scan_kol.sh
   ```
   **Set terminal timeout >= 300s** — scan takes ~4.5 min (54 accounts × 5s delay + Python overhead).
4. **If "请重新登录" visible** → session expired but cookies still valid:
   - `browser_click` on the "登录" link/button
   - Wait 3s for redirect to dashboard
   - Verify with `browser_snapshot` (look for user content)
   - Then run scan as in step 3.
5. **If clicking login still shows re-login page** → cookies truly expired, notify user via Telegram: "WeChat MP session expired. Please open mp.weixin.qq.com in your browser, scan the QR code, then say 'scan KOL'."

### Retry on rate limit

If `scan_kol.sh` exits with SESSION_ERROR (ret=200013 mid-scan), wait 30 minutes then re-run the full Decision Tree (step 1–5). If retry also fails, stop and notify.

### Trigger: cron fires

Same as above, but on cookie-level failure, deliver Telegram notification
(since user may not be watching the chat).

## Guard Clauses

- **DB not found**: If `data/kol_scan.db` does not exist, respond:
  "Knowledge base not initialized. Run `python batch_scan_kol.py --days-back 120` first to do the initial full scan."
- **kol_config.py not found**: Respond:
  "WeChat credentials not configured. See `docs/KOL_COLDSTART_SETUP.md`."

## Health Check Procedure (Pre-Scan, ~5min before daily scan)

Automated pre-flight checkout for the daily scan. Validates CDP browser reachability,
checks WeChat MP session validity, auto-refreshes credentials, and verifies with a
single-account test scan. **Credentials must be refreshed every run** because the
WeChat MP page token and some cookies (`_clck`, `_clsk`, `ua_id`) change with each
pageload — even when the session is technically still valid.

### Step 1: Verify CDP & navigate to WeChat MP

Use the **root URL** (`https://mp.weixin.qq.com/`), NOT `/cgi-bin/home` — the root
auto-redirects with a fresh `?token=` parameter, while subpaths show "请重新登录"
even when cookies are still valid.

```
browser_navigate("https://mp.weixin.qq.com/")
```

Expected: automatic redirect to
`https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=XXXXX`

### Step 2: Check session status

```
browser_snapshot()
```

- **Dashboard visible** (username "AI老兵日记", user stats with 原创/总用户数/近期发表,
  "新的创作" buttons) → session active, proceed to Step 3.
- **"请重新登录" visible** → cookies still valid but page token stale:
  1. `browser_click` on the "登录" link/button (ref=e2)
  2. Wait 3s for redirect
  3. `browser_snapshot()` again
  4. Dashboard visible → session recovered, proceed to Step 3.
  5. Still "请重新登录" → cookies truly expired → send Telegram:
     "⚠️ WeChat MP cookie 已过期，请手动扫码登录 mp.weixin.qq.com" → STOP.
- **CDP unreachable** (browser_navigate fails) → send Telegram:
  "⚠️ CDP 浏览器不可达（端口 9223）" → STOP.

### Step 3: Extract credentials via CDP

```
# 3a. Get all browser targets
browser_cdp(method="Target.getTargets")
# → Find the mp.weixin.qq.com page entry; note its targetId and extract token from URL

# 3b. Get cookies scoped to mp.weixin.qq.com
browser_cdp(
    method="Network.getCookies",
    params={"urls": ["https://mp.weixin.qq.com"]},
    target_id="<the target ID from step 3a>"
)
```

**TOKEN** is visible in the URL from `Target.getTargets` output:
`url: "...?t=home/index&lang=zh_CN&token=1466571383"` — extract `1466571383`.

**COOKIE** string is built from all returned cookies, sorted alphabetically by name:
```python
cookie_parts = sorted([f"{c['name']}={c['value']}" for c in cookies])
cookie_str = "; ".join(cookie_parts)
```

Include ALL cookies (both `mp.weixin.qq.com` and `.qq.com` domain cookies).

### Step 4: Write credentials to kol_config.py

`patch()` the TOKEN line and any changed cookie values in
`/home/sztimhdd/OmniGraph-Vault/kol_config.py`:

- **TOKEN**: replace the existing value with the newly extracted token
- **Cookies**: typically only `_clck`, `_clsk`, `ua_id` change between page loads.
  Critical auth cookies (`slave_sid`, `data_ticket`, `rand_info`, `bizuin`,
  `slave_user`, `xid`, `wxuin`) persist across sessions.

**Important:** The `read_file`/`grep` tools may redact secret-looking values as `***`
in display. Verify actual file content with:
```bash
python3 -c "
with open('/home/sztimhdd/OmniGraph-Vault/kol_config.py', 'rb') as f:
    data = f.read()
idx = data.find(b'TOKEN=')
print(f'TOKEN bytes: {data[idx:idx+30]}')
print(f'TOKEN hex:   {data[idx:idx+30].hex()}')
"
```

### Step 5: Verify with single-account test scan

```bash
cd /home/sztimhdd/OmniGraph-Vault
venv/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1
```

Expected output includes `"Scan complete: 1 ok, 0 failed"` with exit code 0.

- **ret=0** → credentials valid, health check passed
- **ret=200003** → invalid session (possibly truncated `slave_sid`). Re-run from Step 1.
- **ret=200013** → rate limited. Wait 30min and retry.

### Step 6: Report

When health check passes, report confirmation with what changed. Example:
```
✅ KOL扫描就绪：凭证已刷新，验证通过。08:00 启动全量扫描。
更新: _clck: g5m→g5n, _clsk: 17uy5vr→14ikovi
```

When it fails, include the exact error code and remediation. On failure,
**send Telegram notification** since the cron runs unattended.

### Retry on rate limit

If the verification scan returns ret=200013, wait 30 minutes then re-run the full
Health Check from Step 1. If the retry also fails, stop and notify.

## Anti-Crawl & Reliability

- **SESSION_LIMIT = 54** (in `batch_scan_kol.py:35`): one API request per KOL account.
  WeChat real limit is ~60 per session. 54 leaves 6-request headroom for pagination.
  If you add accounts, raise this proportionally — but never exceed 58.
- **Account order is RANDOMIZED** (`random.shuffle` before iteration). This ensures
  that if SESSION_LIMIT truncation happens, different accounts get skipped each day.
- **Inter-account delay = 5.0s** (`RATE_LIMIT_SLEEP_ACCOUNTS` in `spiders/wechat_spider.py:22`).
  54 accounts × 5s = 4.5 min total.
- **Health check cron** (07:55 daily): runs the [Health Check Procedure](#health-check-procedure-pre-scan-5min-before-daily-scan)
  above — validates CDP, auto-refreshes credentials into `kol_config.py`, verifies
  with single-account test scan. Sends Telegram on failure; silent on success.

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
4. **Verify DB coverage**: Use Python (sqlite3 CLI may not be installed):
   ```python
   import sqlite3
   c = sqlite3.connect("data/kol_scan.db")
   rows = c.execute(
       "SELECT a.account_id, k.name, COUNT(*)"
       " FROM articles a JOIN accounts k ON a.account_id = k.id"
       " WHERE a.scanned_at LIKE 'YYYY-MM-DD%'"
       " GROUP BY a.account_id"
   ).fetchall()
   print(f"Accounts with articles: {len(rows)} out of {c.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]}")
   for aid, name, cnt in rows: print(f"  {name}: {cnt}")
   c.close()
   ```
   — if count < 53, some accounts were skipped.

## References

- Session refresh steps: `references/session-refresh.md`
- Crawl safety: `scripts/scan_kol.sh` stops before WeChat's ~60 request limit
