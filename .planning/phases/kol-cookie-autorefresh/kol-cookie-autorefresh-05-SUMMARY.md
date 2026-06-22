# Plan 05 SUMMARY — end-to-end verification (KCA-9)

**Status:** COMPLETE — **LIVE branch, phase fully verified**
**Actor:** ALIYUN-WRITE + Hermes read/execute (main session, user-authorized)
**Date:** 2026-06-23 CST

## Branch taken: LIVE (Plan 04 = EXECUTED, Step B deferred)

Plan 04 synced the wrapper to Hermes, alias repointed, `--image` capability recorded (not-supported). Step B (password rotation) deferred but does NOT gate Level A/C. So the LIVE branch ran.

## Result: PASSED — full self-healing chain proven end-to-end

The cookie dead since 2026-06-10 (13 days) was recovered live:
- **A-level chain:** token `1670861112` + 5 critical cookies extracted from the live Edge session → `writeback_to_aliyun` atomic write → `verify test-scan ret=0; writeback success` → `writeback_result: True`.
- **Recovery proof:** `MAX(scanned_at)` advanced **2026-06-10 01:58 → 2026-06-23 03:02:15**; real scan `1 ok, 0 failed, SCAN_EXIT=0` (no ret=200003); COUNT 1807→1808 (confirmatory).
- **C-level:** QR captured (472×472 ~10KB canvas PNG) + delivered to Telegram via `sendPhoto` (`ok:true`); user scanned it and the session bound (proven by the A-level dashboard + cookies).

Full evidence + KCA-1..9 coverage table in `kol-cookie-autorefresh-VERIFICATION.md`.

## 3 real bugs caught by live testing (Principle #6)

All passed unit tests + plan review yet failed live; all fixed + committed:
1. `hermes` not on non-interactive PATH (`b6a1037`)
2. `hermes send` text-only → QR never reached phone → Telegram `sendPhoto` API (`76a6c93`)
3. WeChat defaults to account-login → QR `<img>` absent → click 扫码登录 first (`c69c6e2`)

## Deferred / residual

- Step B password rotation (user-only) — enables Level-B runtime; Level A/C already live.
- Level-C QR-session-binding caveat → ISSUES candidate (canvas-copied QR + page reload prevents the Edge browser from receiving the scan callback; the in-Edge live QR is the reliable path; the wrapper's own poll loop is in-place/correct).

## Discipline

Main-session SSH; no secret values in artifacts; forward-only commits; explicit git add.
