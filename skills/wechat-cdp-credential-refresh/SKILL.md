---
name: wechat-cdp-credential-refresh
description: |-
  Refresh WeChat MP API credentials (TOKEN + COOKIE) via CDP-connected browser.
  Automates the DevTools manual workflow — connects to CDP port 9222, detects
  existing login, extracts credentials, and saves to kol_config.py.
  First tries cookie-based session recovery (click "登录", no QR needed);
  falls back to HITL QR code scan only when cookies are truly invalidated.

  Trigger phrases: "refresh credentials", "credentials expired", "update wechat token",
  "wechat cookie expired", "login expired", "need new wechat session".
compatibility: |
  Requires: Edge/Chrome on Windows with CDP flag (--remote-debugging-port=9222)
  Requires: WSL2 with mirrored networking OR cd to Windows port 9222
  File target: $OMNIGRAPH_ROOT/kol_config.py
---

# wechat-cdp-credential-refresh

## Overview

Refreshes WeChat MP (mp.weixin.qq.com) credentials — **TOKEN** (short-lived CSRF)
and **COOKIE** (session cookie string) — by connecting to a CDP-debuggable browser
on Windows via **WebSocket protocol** (not browser_navigate tool).

**⚠️ CRITICAL: Always use CDP WebSocket (`Network.getCookies`) for cookie extraction.
Never ask the user to manually copy cookies from DevTools → Application tab.**
The displayed `slave_sid` value in DevTools UI is truncated (long Base64 strings
get cut off mid-value). The CDP API returns the **full, untruncated** value.

**HITL requirement:** If no logged-in session is found, the agent navigates to
the WeChat MP login page. The user must scan the QR code with their phone to log
**HITL requirement (last resort):** If the login button trick fails (i.e., the cookie itself is invalidated, not just the token), navigate to the WeChat MP login page. The user must scan the QR code with their phone to log in. After that, the agent extracts and saves credentials automatically.

## Procedure

### Step 0: Try cookie-based session recovery first

Before any credential extraction, attempt to revive the existing session:

1. `browser_navigate` to `https://mp.weixin.qq.com/` (ROOT URL — NOT `/cgi-bin/home?t=home/index&lang=zh_CN`).
   The root auto-redirects with a fresh `?token=...` parameter and loads the dashboard when session cookies exist.
   The subpath URL without a token parameter shows "请重新登录" even when cookies are valid.

2. `browser_snapshot` — **check which of THREE possible outcomes occurred:**

   **A) Dashboard visible** (URL redirects to `/cgi-bin/home?t=home/index&token=XXXXX`, user "AI老兵日记", stats):
   → Session already valid, proceed to Step 2.

   **B) "请重新登录" visible** (URL is `/cgi-bin/home?t=home/index&token=XXXXX`, heading "登录超时，请重新登录"):
   → Cookies still valid but page token stale. `browser_click` the "登录" link (ref=e2).
      Wait 3s → dashboard should load. If still "请重新登录" → cookies truly expired, proceed to Step 3-C (QR code login, HITL).

   **C) Public homepage visible** (URL stays at `https://mp.weixin.qq.com/`, title "微信公众平台", shows "使用账号登录" and "立即注册" but NO "请重新登录" message):
   → **No session cookies at all in the browser.** Auth cookies (`slave_sid`, `data_ticket`, `rand_info`, `bizuin`, `slave_user`) are completely absent.
   **DO NOT** click "使用账号登录" — it won't auto-redirect. Proceed directly to Step 3-C (QR code login, HITL).
   Optionally confirm with CDP: `Network.getCookies` on the mp.weixin.qq.com tab will return
   only tracking cookies (`_clck`, `_qimei_*`, `ua_id`, `wxuin`, `xid`) — no auth cookies.

**Why the click-login trick works:** WeChat MP session cookies persist in the browser even after the page token expires. The page shows "请重新登录" because the CSRF token is stale, but the cookies (`slave_sid`, `slave_user`, etc.) are still valid server-side. Clicking "登录" triggers a cookie-based re-authentication that refreshes the token without requiring the user to scan.

**Why the public homepage is different:** When the root URL doesn't auto-redirect at all and stays on the public page, it means the browser has ZERO session cookies for mp.weixin.qq.com — not even expired ones. The login-button trick won't work because there's no session to recover. CDP cookie inspection will confirm `slave_sid` and `data_ticket` are absent.

```bash
curl -s http://127.0.0.1:9222/json/version
```

Expected: JSON with `webSocketDebuggerUrl`. If empty/refused:
- Ensure Edge/Chrome was started with `--remote-debugging-port=9222`
- In WSL2, verify mirrored networking: `/etc/wsl.conf` should have `networkingMode=mirrored`

### Step 2: Connect to CDP and find the WeChat MP page

```python
import asyncio, json, websockets, re

async def find_wechat_page():
    async with websockets.connect('ws://127.0.0.1:9222/devtools/browser/...') as ws:
        # List all pages
        await ws.send(json.dumps({'id': 1, 'method': 'Target.getTargets'}))
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        targets = json.loads(resp).get('result', {}).get('targetInfos', [])
        
        # Find WeChat MP page
        for t in targets:
            if 'mp.weixin.qq.com' in t.get('url', ''):
                return t['targetId']
        
        # Not found — user needs to log in first
        return None
```

### Step 3-A: Session exists — extract credentials (Preferred: browser_cdp)

If a WeChat MP page exists with a valid dashboard:

**Method A — browser_cdp tool (simplest, no Python needed):**

1. Get the page's target_id from `browser_cdp(method='Target.getTargets')` — 
   find the entry with `url` containing `mp.weixin.qq.com/cgi-bin/home` and a `token=` parameter.

2. Extract token directly from the URL (already visible in Target.getTargets output):
   ```
   token=1466571383  ← extract this
   ```

3. ⚠️ **Prerequisite: attach to target first.** On some CDP backends (especially Browserbase's CDP proxy), `Network.getCookies` returns `'method not found'` unless you first establish a real session:
   ```
   browser_cdp(
     method='Target.attachToTarget',
     params={'targetId': 'B908EE02...', 'flatten': True}
   )
   ```
   `flatten: true` is critical — without it the returned session ID may not work with `target_id` in subsequent calls.

4. Extract cookies via CDP using the **same target_id**:
   ```
   browser_cdp(
     method='Network.getCookies',
     params={'urls': ['https://mp.weixin.qq.com']},
     target_id='B908EE02...'
   )
   ```
   This returns ALL cookies (including HttpOnly ones like `slave_sid`, `data_ticket`) with full, untruncated values.

5. Build the COOKIE string: sort cookies by name (e.g. `_clck` comes before `_qimei_*`), join as `name=value; ` pairs. Include all cookies — even session cookies — the WeChat API validates the full set.

6. Update `kol_config.py` with `patch()` — replace TOKEN and the changed cookie values. Only `_clck` and `_clsk` typically change between page loads; the critical auth cookies (`slave_sid`, `data_ticket`, `rand_info`, `bizuin`, etc.) persist across sessions.

**Method B — Python websockets (legacy, when raw CDP access is needed):**

```python
import asyncio, json, re, websockets

# 1. Connect to the specific page's WebSocket
async with websockets.connect(f'ws://127.0.0.1:9222/devtools/page/{page_id}') as ws:
    # 2. Get token from page URL (not from /json endpoint — it's redacted there)
    await ws.send(json.dumps({
        'id': 1, 'method': 'Runtime.evaluate',
        'params': {'expression': 'window.location.href'}
    }))
    resp = await asyncio.wait_for(ws.recv(), timeout=3)
    page_url = json.loads(resp)['result']['result']['value']
    token = re.search(r'token=([^&]+)', page_url).group(1)

    # 3. Get cookies for mp.weixin.qq.com domain only
    await ws.send(json.dumps({'id': 2, 'method': 'Network.enable'}))
    await asyncio.wait_for(ws.recv(), timeout=3)
    await ws.send(json.dumps({'id': 3, 'method': 'Network.getCookies',
        'params': {'urls': ['https://mp.weixin.qq.com']}}))
    resp = await asyncio.wait_for(ws.recv(), timeout=3)
    cookies = json.loads(resp)['result']['cookies']

    # 4. Build cookie string — preserve order from browser
    #    Use sorted by name for consistency
    cookie_parts = sorted(
        f"{c['name']}={c['value']}" for c in cookies
    )
    cookie_str = '; '.join(cookie_parts)
```

**Key difference from manual copy:** `Network.getCookies` with URL filter returns the
**complete** cookie values as stored by the browser engine — no truncation.

### Step 3-B: Verify slave_sid length (truncation guard)

After extracting cookies, check that the `slave_sid` value is the same length as
what's currently saved in `kol_config.py`. If the new one is significantly longer,
the old one was truncated:

```python
# Compare slave_sid length
extracted_sid = next(c for c in cookies if c['name'] == 'slave_sid')['value']
old_config = open('kol_config.py').read()
old_match = re.search(r'slave_sid=([^;]+)', old_config)
if old_match:
    old_sid = old_match.group(1)
    if len(extracted_sid) > len(old_sid):
        print(f'WARNING: Old slave_sid was truncated! (old={len(old_sid)} chars, new={len(extracted_sid)} chars)')
        # The new value is authoritative — use it
```

Also check these critical cookies for changes:
- `data_ticket` (used for article URL access)
- `rand_info` (used in signature verification)
- `xid` (session ID — changes on relogin)

### Step 3-C: Refresh stale non-critical cookies

Some cookies like `_clsk`, `_clck`, and `ua_id` change with page reloads. While
not critical for API auth (only `slave_sid`, `slave_user`, `data_ticket`, `rand_info`,
`bizuin`, `xid`, `wxuin` matter), updating them keeps parity with the browser
session. Use `Network.getCookies` to get the full cookie set and update all values.

### Step 3-D: No session — HITL login flow

If no WeChat MP page is found:

1. Navigate the browser to `https://mp.weixin.qq.com/` (use browser_navigate tool)
2. Present the screenshot to the user: "📱 **请扫描二维码登录微信公众平台** — Scan the QR code with WeChat on your phone to log in"
3. Wait for user confirmation after scanning
4. After login, the browser will redirect to the homepage — navigate to `https://mp.weixin.qq.com/cgi-bin/appmsg?token=&lang=zh_CN`
5. Extract credentials as in Step 3-A

### Step 4: Save to kol_config.py

Update `$OMNIGRAPH_ROOT/kol_config.py`:

```python
# Replace TOKEN line
old_token_line = f'TOKEN="{old_value}"'
new_token_line = f'TOKEN="{token}"'

# Replace COOKIE block — match from 'COOKIE = (' to the closing ')'
# Format the cookie string with proper indentation
cookie_pairs = cookie_str.split('; ')
formatted_cookie = '; '.join(cookie_pairs) + '; '
```

Use `patch()` tool to replace `TOKEN="***"` and the `COOKIE = (...)` block.

**⚠️ Escape-drift when patching string continuation lines:**

`kol_config.py` uses Python implicit string concatenation inside `COOKIE = (...)`,
so each cookie line ends with `" ` (a `"` character before the line-end). When you
pass `\"` in the `old_string` or `new_string` to `patch()`, it triggers an
**"Escape-drift detected"** error because the tool's string parser interprets
your `\"` as a literal escaped quote rather than matching the file's actual `"`
character.

**Fix:** When patching individual cookie values, match only the VALUE portion:

```python
# DON'T (triggers escape-drift):
patch(old_string='_clck=3964447985|1|g5x|0; "',
      new_string='_clck=3964447985|1|g5y|0; "')

# DO (match only the value text):
patch(old_string='_clck=3964447985|1|g5x|0',
      new_string='_clck=3964447985|1|g5y|0')
```

This works because the value portion is unique enough within each line. For TOKEN
line patching, match `TOKEN="797448790"` directly (quotes are fine there since
they're part of the `TOKEN=` assignment, not line-continuation strings).

### Step 5: Verify

```bash
cd $OMNIGRAPH_ROOT
python3 -c "
import sys; sys.path.insert(0, '.')
from spiders.wechat_spider import list_articles
import kol_config

first = list(kol_config.FAKEIDS.keys())[0]
fakeid = kol_config.FAKEIDS[first]
articles = list_articles(kol_config.TOKEN, kol_config.COOKIE, fakeid, days_back=1, max_articles=1)
print(f'VALID — got {len(articles)} article(s)')
for a in articles:
    print(f'  {a[\"title\"]}')
"
```

Expected output: `VALID — got 1 article(s)` with a title. No `invalid csrf token` error.

## Pitfalls

- **`invalid csrf token` error** after refresh: The TOKEN may have rotated on login. Re-run the full extraction.
- **`invalid session` (ret=200003) after refresh — TRUNCATED slave_sid**: This is the #1 gotcha and the #1 reason to **never ask the user to manually copy cookies**. When copying from DevTools → Application → Cookies in the browser UI, the displayed `slave_sid` value is **truncated** (the UI clips long Base64 strings with `...` mid-value). The CDP `Network.getCookies` API always returns the **full, untruncated** value. If the current config was manually copied, always re-extract via CDP and compare character-by-character.
- **CDP connection refused**: Edge/Chrome may have been restarted. Start it with: `msedge --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\Users\%USERNAME%\cdp_temp" --no-sandbox`
- **Browser is headless**: Some CDP modes launch headless. User won't see the login page. Use visible mode instead.
- **Multiple CDP pages**: There may be multiple `mp.weixin.qq.com` pages. Use the one with `/cgi-bin/home` or `/cgi-bin/appmsg` in the URL — these are the authenticated pages.
- **Token is hidden** in CDP `/json` endpoint: The CDP REST API redacts `token=***` in page URLs. Always extract via `Runtime.evaluate('window.location.href')` on the page's WebSocket connection.
- **Verify immediately after saving**: Credential write can succeed even with wrong values. Run the verification test right after saving. If `invalid session` error occurs, it's almost always a truncated `slave_sid` — re-extract via CDP WebSocket and check lengths.
- **Stale admin cookies (`_clsk`, `_clck`, `ua_id`)**: These change on page reload and may cause login page redirects in the browser but are NOT checked by the API. Only `slave_sid`, `slave_user`, `data_ticket`, `rand_info`, `bizuin`, `xid`, and `wxuin` are critical for API auth. Don't get stuck on stale cookies — update them if convenient but don't treat failure to match as a real problem.
- **Use `Network.getCookies` with URL filter**, not `Network.getAllCookies`: The filter `'urls': ['https://mp.weixin.qq.com']` returns only the relevant cookies. Without the filter, you pick up cookies from other domains the browser might have open.
