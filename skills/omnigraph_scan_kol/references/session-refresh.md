# WeChat MP Session Refresh

## When
Scan returns `SESSION_ERROR` or `ret=200013` on the first few accounts, OR health check
detects "请重新登录" that cannot be recovered via simple re-login click.

## Automated QR Code Recovery (Hermes CDP → Telegram)

Hermes now handles cookie expiration automatically via the **QR Code Login Flow**:

1. Hermes detects "cookies truly expired" during health check
2. Navigates to `https://mp.weixin.qq.com/` via CDP → login page with QR code
3. Captures the QR code via `browser_vision` or `Page.captureScreenshot`
4. Sends the QR code screenshot to Telegram: "📱 请用微信扫描二维码登录"
5. Polls every 10 seconds (max 5 minutes) checking `browser_snapshot` for dashboard indicators
6. When dashboard appears (login succeeded) → extracts credentials → runs test scan → resumes
7. If QR expires during polling → refreshes and re-sends (max 2 refreshes)
8. If 5-minute timeout → notifies user and stops

## Manual Recovery (Fallback)

If the automated QR flow fails (e.g., CDP unreachable, page in unusual state):

1. Open a browser (Chrome or Edge) to `https://mp.weixin.qq.com`
2. Scan the QR code with your WeChat app
3. Once you see the Official Account dashboard, refresh the page (F5)
4. Confirm you can see your subscribed accounts in the left sidebar
5. Come back to Hermes and say: "scan KOL"

## How Hermes tries first
Before alerting you, Hermes will attempt `browser_navigate` to `https://mp.weixin.qq.com`, wait 3 seconds, then click the "登录" link if shown. If the CDP browser already has a valid WeChat MP session cookie, this succeeds silently. Only when cookies are truly expired does the QR code flow activate.

## Why this happens
WeChat MP API sessions expire after a period of inactivity (typically a few days). The scan uses the same session cookies as the browser, so refreshing the page renews the session.
