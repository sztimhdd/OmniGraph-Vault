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
5. **If clicking login still shows re-login page** → cookies truly expired, enter **QR Code Login Flow** (below). This flow captures the WeChat login QR code via CDP, sends it to Telegram, polls until the user scans, then resumes the scan automatically.

### Retry on rate limit

If `scan_kol.sh` exits with SESSION_ERROR (ret=200013 mid-scan), wait 30 minutes then re-run the full Decision Tree (step 1–5). If retry also fails, stop and notify.

### Trigger: cron fires

Same as above, but on cookie-level failure, enter **QR Code Login Flow** — capture
QR code via CDP, send to Telegram, poll for scan, then resume automatically.
No manual intervention needed.

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
  5. Still "请重新登录" → cookies truly expired → enter **QR Code Login Flow** (see full procedure below). After login succeeds, proceed to Step 3 (credential extraction). If login times out → STOP.
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

## QR Code Login Flow (CDP → Telegram → Poll → Resume)

When WeChat MP cookies have fully expired and the health check reaches
"cookies truly expired," Hermes performs an automated QR-code login recovery
instead of stopping and waiting for manual intervention.

### Known Limitations

- **WeChat QR codes cannot be scanned from a photo album or screenshot.** The
  WeChat app's "Scan" function only works via live camera — pointing the phone
  at a QR code image displayed on another screen or printed out WILL fail.
  This is a WeChat security restriction, not a technical bug.
- **Two-phone workaround:** Use one phone to display the QR code (open Telegram
  and view the image Hermes sent), and a second phone with the WeChat app to
  scan the first phone's screen. Confirmed working in live test 2026-05-01.
- **CDP browser must be on a visible display.** The Edge instance running on the
  Windows host at port 9223 must have a real screen — headless mode won't work
  because WeChat checks for rendering surface.

### Step Q1: Navigate to the WeChat MP login page

From any state where "请重新登录" is visible, navigate to the login entry:

```
browser_navigate("https://mp.weixin.qq.com/")
```

If the page redirects to a login page (URL contains `qrcode` or the snapshot
shows a QR code image), proceed to Q2.

If the page shows an unusual state (CAPTCHA, error page, blank), take a
screenshot via `browser_vision`, send it to Telegram with the message:
"⚠️ WeChat MP 登录页面异常，见截图", and STOP.

### Step Q2: Capture and send the QR code

**CRITICAL — avoid `Page.captureScreenshot` base64 freeze:** The CDP
screenshot method returns enormous base64 data (2MB+) that will freeze
Hermes for 2+ minutes. The QR code expires in ~2 minutes, so any delay
is fatal.

**Correct approach — crop from the auto-saved browser_vision screenshot:**

```
# Step 1: Get QR code position from DOM (fast, no base64)
browser_cdp(method="Runtime.evaluate",
    params={"expression": "(function(){var q=document.querySelector('img.login__type__container__scan__qrcode'); if(!q) return 'not found'; var r=q.getBoundingClientRect(); return JSON.stringify({x:r.left, y:r.top, w:r.width, h:r.height});})()",
    target_id="<tab-id>")

# Step 2: Take a full-page screenshot via browser_vision (saves to disk automatically)
browser_vision(question="Describe this page briefly")

# Step 3: Crop the QR code from the screenshot using Python
# Use execute_code or terminal python to:
#   from PIL import Image
#   img = Image.open("<screenshot_path from browser_vision>")
#   scale = 1.875  # devicePixelRatio from Runtime.evaluate
#   qr = img.crop((int(x*scale)-20, int(y*scale)-20, int((x+w)*scale)+20, int((y+h)*scale)+20))
#   qr.save("/tmp/wx_qr.png")

# Step 4: Send cropped QR code to Telegram
send_message(target="telegram:Hai Hu (dm)",
    message="📱 WeChat MP 登录已过期，请用微信扫描下方二维码登录（5分钟内有效）\nMEDIA:/tmp/wx_qr.png")
```

**If `browser_vision` 503s (model overload):** The screenshot is still saved to disk
even when vision analysis fails — the `screenshot_path` is returned in the error.
Use that path directly. Always save the screenshot_path for fallback.

**Why `Page.captureScreenshot` is dangerous:** A full-viewport screenshot in base64
at scale=2 on a 2560px display = ~3MB of base64 text. Hermes freezes trying to
process this in the tool response. The QR code expires while Hermes is frozen.
Always use the file-based approach above.

### Step Q3: Poll for successful login

After sending the QR code, start a polling loop:

```
repeat up to 30 times (5 minutes total, every 10 seconds):
  1. browser_snapshot(full=false)
  2. Check if snapshot contains dashboard indicators:
     - "AI老兵日记" (username)
     - "新的创作" (button text)
     - "原创" (stats label)
  3. If dashboard found → login succeeded! Break out of loop → go to Q4.
  4. Check if QR code has expired (snapshot shows "二维码已过期" or similar):
     → Go back to Step Q1 to get a new QR code (max 2 refreshes total).
     On the 2nd refresh, send Telegram "⚠️ 二维码再次过期，请尽快扫码" and continue.
  5. Wait 10 seconds, then next iteration.
```

**Edge cases during polling:**
- **Page navigated away** (e.g., WeChat auto-redirect): `browser_navigate("https://mp.weixin.qq.com/")` and continue polling.
- **CDP connection lost**: Send Telegram "⚠️ CDP 连接中断，无法完成登录" → STOP.
- **Timeout (5 min / 30 polls)**: Send Telegram "⏰ 扫码超时（5分钟），请稍后手动触发 scan KOL" → STOP.

### QR Code Capture Pitfalls (verified 2026-05-01 live test)

These pitfalls were discovered during end-to-end testing of the QR flow and apply
to any skill that captures login QR codes via CDP and sends them via Telegram.

**Pitfall 1: `browser_vision` returns 503 (model overload).**

`browser_vision` relies on Gemini Vision API which can return 503 under load.
The screenshot is still saved to disk (the `screenshot_path` field is populated),
but the AI analysis fails. **Fix:** Fall back to CDP `Runtime.evaluate` for DOM
inspection to find the QR code element:

```
browser_cdp(method="Runtime.evaluate",
  params={"expression":"document.querySelector('img[src*=\"qrcode\"]') ? 'QR found' : 'no QR'",
          "returnByValue": true},
  target_id="<tab-id>"
)
```

If the QR code exists, use the already-captured screenshot file from the failed
`browser_vision` call (the `screenshot_path` field) — proceed to Pitfall 2.

**Pitfall 2: Telegram rejects screenshots with "Photo_invalid_dimensions".**

Full-page screenshots (2040px+ wide at 1.875x devicePixelRatio) produce images
that Telegram's photo API rejects. **Fix:** Use PIL to crop the screenshot to
only the QR code area before sending:

```python
from PIL import Image
img = Image.open(screenshot_path)
# QR code position from CDP Runtime.evaluate: getBoundingClientRect()
# Multiply by devicePixelRatio for actual pixels
cropped = img.crop((x, y, x+w+40, y+h+40))  # 40px padding
cropped.save("/tmp/wx_qr_code.png", "PNG")
```

Target output: ~20–30KB. Then send via `send_message(target="telegram", message="📱 ... MEDIA:/tmp/wx_qr_code.png")`.

**Pitfall 3: `Page.captureScreenshot` returns enormous base64 that freezes the agent.**

The CDP `Page.captureScreenshot` with a clip still returns the full data inline,
and Hermes can freeze for 2+ minutes processing large base64 payloads. **Fix:**
Do NOT use `Page.captureScreenshot`. Instead, use the screenshot file path from
a prior `browser_vision` call and crop with PIL (Pitfall 2). If no
`browser_vision` call was made, use `browser_vision` with a simple question to
trigger screenshot capture (even if the AI analysis fails with 503, the file
is saved).

**Pitfall 4: DOM selectors for QR code vary by site.**

The WeChat MP login page uses `img.login__type__container__scan__qrcode`.
Other sites (Zhihu, etc.) use different selectors. Always verify via
`Runtime.evaluate` before attempting to get coordinates. Fallback: search
for any `img` with `qrcode` or `scanlogin` in the `src` attribute.

### Step Q4: Post-login credential extraction

Login succeeded — the dashboard is now visible. Proceed to the normal
**Health Check Step 3** (extract credentials via CDP → write to kol_config.py).

Then run the single-account test scan (Health Check Step 5) to verify
credentials work. If test passes → report success and continue to main scan.

### Step Q5: Report login recovery

```
send_message(target="telegram", message="✅ WeChat MP 登录已恢复，继续执行 KOL 扫描...")
```

Then proceed to run `bash ./skills/omnigraph_scan_kol/scripts/scan_kol.sh`.

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
