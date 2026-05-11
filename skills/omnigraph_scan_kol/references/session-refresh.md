# WeChat MP Session Refresh

## When
Scan returns `SESSION_ERROR` or `ret=200013` on the first few accounts, OR health check
detects "请重新登录" that cannot be recovered via simple re-login click.

## Automated QR Code Recovery (Hermes CDP → Telegram)

Hermes now handles cookie expiration automatically via the **QR Code Login Flow**:

1. Hermes detects "cookies truly expired" during health check
2. Navigates to `https://mp.weixin.qq.com/` via CDP → login page with QR code
3. **Capture QR code (preferred method):** Download the QR image directly using cookies from CDP.
   - Get QR code `<img>` src via `Runtime.evaluate`:
     ```js
     document.querySelector('img.login__type__container__scan__qrcode, img[src*="qrcode"]').src
     ```
   - Get cookies via `Network.getCookies` (key cookies: `wxuin`, `ua_id`, `xid`, `cert`, `uuid`, `wxtokenkey`)
   - Download the QR image with `requests.get(url, cookies=cookies)` — returns JPEG or PNG at native resolution (472×472)
   - Convert to PNG if needed, save to `/tmp/wx_qr_code.png`
   - **Pitfall (2026-05-08):** `Page.captureScreenshot` with clip coordinates times out after 30-60s on the WeChat MP page. The `Runtime.evaluate` → canvas → `toDataURL` approach also works but the base64 output is truncated by CDP's inline value size limit. The cookie-based direct download approach is the most reliable.
4. Sends the QR code to Telegram: "📱 请用微信扫描二维码登录，5分钟内有效"
5. Polls every 10 seconds (max 5 minutes) checking `browser_snapshot` for dashboard indicators
6. When dashboard appears (login succeeded) → extracts credentials → runs test scan → resumes
7. If QR expires during polling → refreshes page to get new QR code and re-sends (max 2 refreshes)

## Manual Recovery (Fallback)

If the automated QR flow fails (e.g., CDP unreachable, page in unusual state):

1. Open a browser (Chrome or Edge) to `https://mp.weixin.qq.com`
2. Scan the QR code with your WeChat app (live camera only — WeChat blocks album scanning)
3. Once you see the Official Account dashboard, refresh the page (F5)
4. Confirm you can see your subscribed accounts in the left sidebar
5. Come back to Hermes and say: "scan KOL"

## How Hermes tries first
Before alerting you, Hermes will attempt `browser_navigate` to `https://mp.weixin.qq.com`, wait 3 seconds, then click the "登录" link if shown. If the CDP browser already has a valid WeChat MP session cookie, this succeeds silently. Only when cookies are truly expired does the QR code flow activate.

## Known Limitations
- **WeChat QR codes cannot be scanned from photo albums** — live camera only. If receiving QR on Telegram, use the "two-phone" workaround: one phone displays QR, second phone scans with WeChat.
- **CDP browser must be on a visible display** (not headless) — WeChat blocks headless browsers.
- **QR codes expire in ~5 minutes** — the polling loop handles refresh if needed.
