# Plan 04 SUMMARY — Hermes operator steps (KCA-8/2/4)

**Status:** EXECUTED (A/C/D done by orchestrator; B deferred by user — does not block main chain)
**Actor:** HERMES-WRITE-OPERATOR — RO window expired 2026-06-22 (today); user authorized Hermes writes. Orchestrator executed A/C/D directly via main-session SSH.
**Commits:** operator prompt `ceffb98`; Hermes field-notes preservation `b5ce059`; Hermes merge `0c9c08a`.
**Date:** 2026-06-22 CST

## Outcome per step

| Step | Result | Detail |
|------|--------|--------|
| **A** sync wrapper | ✅ DONE | Hermes had 2 uncommitted SKILL edits (base64 TOKEN note + F7 OOM) + was 80 behind. Preserved them as commit `b5ce059`, then `git pull --no-rebase` merged origin (`0c9c08a`). `scripts/refresh_wechat_cookie.py` + `scripts/lib/cdp_client.py` now present; `--help` runs (pinned import resolves from repo root). Redaction landed (line 92 = `${WECHAT_MP_ACCOUNT}` placeholder, no literal). Hermes field notes survived the merge. |
| **C** repoint alias | ✅ ALREADY DONE | `vitaclaw-aliyun` HostName already `47.117.244.253`; `ssh vitaclaw-aliyun hostname` → `iZj1imk39yc55iZ` (live Aliyun). |
| **D** `--image` probe | ✅ DONE → **NOT-SUPPORTED** | `hermes send` is text-only (`-f PATH` reads a message *body* from file, not an image attachment; no image/photo/media/attach flag). **Level-C QR delivery = text + /tmp/wx_qr_code.png path fallback** (wrapper already implements this branch). Plan 05 QR acceptance is satisfied by the text-fallback path. |
| **B** rotate pw + env creds | ⏳ DEFERRED (user) | Only the user can rotate the WeChat account password (human login). Writes `WECHAT_MP_ACCOUNT`/`WECHAT_MP_PASSWORD` to `~/.hermes/.env` (currently count=0). **Enables ONLY Level-B (cookie-dead-but-account-login). Does NOT block Level-A (token refresh, the common case) or Level-C (QR scan).** Steps in HERMES-OPERATOR-PROMPT.md STEP B. |

## Plan 05 branch signal

**EXECUTED (with B deferred)** → Plan 05 runs the **Level-A live chain** (token refresh, no password needed) + exercises the QR/Telegram path (text-fallback, since `--image` not-supported). **Level-B live verification is deferred** alongside Step B — to be done after the user rotates the password and sets env creds. Phase closes as **functionally-complete for Level A/C live; Level-B code-complete, runtime-pending**.

## Notes

- Hermes is `ahead 2` of origin after the merge (the field-notes commit + merge commit) — orchestrator pushes these back to origin at phase close so both sides converge.
- `hermes send --image` capability = **not-supported** is now a recorded fact (was an open WARNING-3 assumption). The wrapper's capability-gated `notify_image()` degrades to text correctly.
- No secret passed through the orchestrator; password rotation + env write remain user-only (Step B).

## Discipline

Main-session SSH (RO expired + user-authorized); Hermes field notes preserved (not discarded) per user decision; explicit `git add` on Hermes commit; forward-only merge (no rebase/force); no secret in any artifact.
