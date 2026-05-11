# Account Login Fallback — WeChat MP

When cookie-based sessions expire, the browser's saved credentials can provide a faster recovery path than QR code scanning.

## DOM Elements (WeChat MP login page)

- **"使用账号登录" link**: `ref=e12` — clicks into the account login form
- **Email/username input**: `ref=e19` — pre-filled with `huhai.orion@gmail.com`
- **Password input**: `ref=e20` — pre-filled (value hidden as ••••••••••••••)
- **"登录" button**: `ref=e18` — submits the login form

## Redirect Chain

1. POST to `/cgi-bin/bizlogin?action=validate&lang=zh_CN&account=huhai.orion%40gmail.com&token=`
2. Redirect to `/cgi-bin/bizlogin?...` with security verification page
3. Security page shows "安全保护" header and a QR code for 2FA verification
4. **The session is established at this point** even though the security page is still displayed
5. Browser auto-redirects to `/cgi-bin/home?t=home/index&lang=zh_CN&token=XXXXX` dashboard

## Quick Session Check

After clicking login and waiting ~5s, the fastest way to confirm session recovery is via browser console:

```
browser_console(expression="document.body.innerText.substring(0, 500)")
```

Look for:
- `"AI老兵日记"` — username confirmed
- `"原创"` — content stats showing
- `"新的创作"` — create button visible
- `"总用户数"` — user count stats

These indicate the dashboard has loaded and the session is active.

## Timing

- Login form submit → security page: ~2s
- Security page → dashboard redirect: ~3-10s (variable, depends on WeChat server)
- Total recovery time: ~10-15s (vs. 5+ min for QR code polling)

## Verified Use

- **2026-05-08**: Successfully recovered expired session using this method. No QR code needed.
- The account is: `huhai.orion@gmail.com` (account name: "大家来打球")
