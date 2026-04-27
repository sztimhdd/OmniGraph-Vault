# WeChat MP Session Refresh

## When
Scan returns `SESSION_ERROR` or `ret=200013` on the first few accounts.

## Steps

1. Open a browser (Chrome or Edge) to `https://mp.weixin.qq.com`
2. If not logged in, scan the QR code with your WeChat app
3. Once you see the Official Account dashboard, refresh the page (F5)
4. Confirm you can see your subscribed accounts in the left sidebar
5. Come back to Hermes and say: "scan KOL"

## How Hermes tries first
Before alerting you, Hermes will attempt `browser_navigate` to `https://mp.weixin.qq.com`, wait 3 seconds, then retry the scan. If the CDP browser already has a valid WeChat MP session cookie, this succeeds silently.

## Why this happens
WeChat MP API sessions expire after a period of inactivity (typically a few days). The scan uses the same session cookies as the browser, so refreshing the page renews the session.
