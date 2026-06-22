# Phase kol-cookie-autorefresh — Context

**Gathered:** 2026-06-19
**Status:** Ready for planning
**Source:** Locked architecture from investigation quick `260615-orv` (all 5 hops empirically live-tested GREEN; this is a BUILD, not research)

<domain>
## Phase Boundary

Build the full self-healing WeChat-cookie auto-refresh chain so the daily KOL scan on Aliyun recovers from cookie expiry without manual operator intervention — automatically for token/account-login expiry (levels A/B), and with a single human QR-scan only on true cookie death (level C), notified via Telegram.

**The problem this closes:** The Aliyun `omnigraph-kol-scan` cron detects cookie expiry (`ret=200003` ≥30% → exit 2 → `OnFailure`) but the alert unit is a **no-op** — it only `date > /root/.hermes/wechat-session-stale` and nothing consumes that flag. No notification, no refresh. Cookie has been dead since ~2026-06-10 (0 new articles in 7+ days). The user currently refreshes by hand (Hermes CDP → scp to Aliyun).

**In scope:** trigger replacement (Aliyun), refresh wrapper on Hermes (路B direct-CDP, levels A/B/C incl. QR→Telegram→poll→resume), atomic writeback to Aliyun, self-heal (relaunch headed Edge if down), 9222/9223 reconciliation, plaintext-credential redaction (#58).

**Out of scope:** changing the scan logic itself; changing the WeChat anti-crawl limits; the daily sync-kol-db cron (already works); any KB/ingest pipeline changes.
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not re-litigate)

### Architecture: Hermes-active, option-A push
- Hermes is the **active executor** — browser, CDP, Telegram all live on the Hermes home-network machine. Aliyun only **detects + hands off**.
- Rationale: Aliyun (cn-shanghai) cannot reach Telegram (GFW); the logged-in Edge browser only exists on Hermes; Hermes can also self-heal the browser via PowerShell. Confirmed with user.

### Hop ① + ② — Trigger (Aliyun-side write; agent can do directly)
- **Modify the existing no-op `omnigraph-kol-scan-alert.service`** (reuse the `OnFailure=` mechanism, minimal change). Replace `date > /root/.hermes/wechat-session-stale` with an `ssh hermes "<invoke refresh>"` (keep touching the stale flag too, as a breadcrumb).
- Aliyun→Hermes ssh is **LIVE** — key authorized on Hermes, `~/.ssh/config` `hermes` stanza written on Aliyun, tested OK post-P0 (`ALIYUN_TO_HERMES_OK / OH-Desktop`).
- This is an **Aliyun-side write** — orchestrator is Aliyun operator (has key), can do directly.

### Hop ③ — Refresh wrapper on Hermes (路B = direct CDP, NOT 58931/MCP)
- A Python script (system `python3` + `websocket-client`, NOT project venv — proven on Hermes) connecting **directly to `localhost:9222` CDP**.
- **MANDATORY gotcha:** the logged-in tab drifts to subpages that may not carry `token=`. The wrapper MUST `Page.navigate` to root `https://mp.weixin.qq.com/`, wait for redirect, read token from the landing URL. Cookies via `Network.getCookies` are always complete regardless of current tab URL.
- Build the cookie string sorted `name=value` (matches kol_config.py expectation).
- Handle the **3 failure levels** (reuse `skills/omnigraph_scan_kol/SKILL.md` decision-tree logic — it documents all of this; do NOT reinvent):
  - **A (token/page stale):** nav root → get new token. Pure script.
  - **B (cookie expired, account-login possible):** fill saved creds (Account-Login-Fallback). Creds from env (see #58 below), NOT hardcoded.
  - **C (true cookie death):** capture QR via canvas `toDataURL()` → `hermes send -t telegram` to user → poll ~5min for scan → resume → re-extract.
- **CSRF token rebind:** after QR/account login, navigate root again to get a token bound to the new session (SKILL.md ret=200040 note).

### Hop ④ — Writeback (Hermes→Aliyun; the SCRIPT runs on Hermes)
- Hermes `scp` the refreshed `kol_config.py` back to Aliyun. Hermes→Aliyun channel works (daily `sync-kol-db-from-aliyun` cron proves it).
- **Atomic write + verify** — write `.tmp` then rename on Aliyun side; verify with a single-account test scan (`batch_scan_kol.py --account <X> --max-articles 1` → expect `ret=0`) before declaring success. Do NOT half-write prod kol_config.py.
- **Secret-redaction trap (SKILL.md):** terminal output may redact TOKEN as `***`; verify via hex/bytes, use CDP `returnByValue=true` (returns real value).

### Hop ⑤ — Notify (Hermes→Telegram)
- `hermes send -t telegram` (scriptable, no LLM/gateway/agent-loop needed for bot-token platforms). Used on: C-level QR request, and a success/failure summary at the end.

### Self-heal — relaunch headed Edge if down
- Pre-step in the wrapper: check `:9222` `/json/version` alive. If not, relaunch a **headed** Edge via WSL→Windows PowerShell interop:
  - Absolute path: `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`
  - `Start-Process "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList "--remote-debugging-port=9222","--remote-debugging-address=127.0.0.1","--remote-allow-origins=*","--user-data-dir=C:\Edge-Auto-Profile","--no-sandbox"`
  - `C:\Edge-Auto-Profile` persists login state across relaunch (live-confirmed).
- Live-tested: interop works via absolute path (bare `powershell.exe` is just a PATH issue in non-interactive shell).

### #57 — Reconcile 9222 vs 9223
- Code/CLAUDE.md say `9223`; the live headed Edge is `9222`. Pick one and update consistently. **Recommendation: standardize on 9222** (it's what's actually running with the logged-in profile) OR relaunch Edge on 9223 to match code — planner to decide and make it consistent across `CDP_URL` default, `ingest_wechat.py`, SKILL.md, and the new wrapper.

### #58 — Plaintext WeChat password in PUBLIC repo (P0 security, fold in)
- `skills/omnigraph_scan_kol/SKILL.md` (Account-Login-Fallback section) has a literal account id + password committed to a public repo.
- Move to env (`${WECHAT_MP_ACCOUNT}` / `${WECHAT_MP_PASSWORD}` read from `~/.hermes/.env`), redact the literals from SKILL.md, note that the password must be rotated. The B-level account-login fallback reads creds from env, never hardcoded.

### Channel discipline (Principle #5) — mark every step's actor
- **Aliyun-write** (orchestrator does directly via key): alert-unit modification, kol_config.py writeback verification.
- **repo-code** (orchestrator does locally, commits): the refresh wrapper script, SKILL.md redaction, 9222/9223 reconcile, CLAUDE.md/config doc updates.
- **Hermes-write** (operator-channel — Hermes RO until 2026-06-22; needs operator prompt OR post-6/22): any Hermes-side cron/systemd registration, placing the wrapper script if not delivered via the existing sync channel, `~/.hermes/.env` new vars. The wrapper SCRIPT can live in the repo and sync to Hermes; only Hermes-side registration/secrets are operator-channel.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Authoritative investigation (READ FIRST)
- `.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md` — full state-of-world, per-hop GREEN/YELLOW/RED evidence, live-test results (CDP cookie grab 5/5 critical cookies; WSL PowerShell interop), the tab-drift gotcha, post-P0 verification. **This IS the phase research.**

### Existing logic to reuse (do NOT reinvent)
- `skills/omnigraph_scan_kol/SKILL.md` — the full A/B/C decision tree: tab-check → 请重新登录 → click-login → Account-Login-Fallback → QR Code Login Flow (canvas toDataURL → Telegram → poll → resume) → credential extraction → write kol_config.py → single-account test scan. Also the secret-redaction trap, CSRF rebind, escape-drift-on-patch notes.
- `batch_scan_kol.py` — detection: `SESSION_INVALID_THRESHOLD=0.30` (line ~42), `ret=200003` detect (line ~228), `sys.exit(2)` on threshold. Single-account test-scan invocation for verification.

### Deploy artifacts (the things being changed)
- `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` — the no-op alert unit to replace (currently only touches the stale flag).
- `deploy/aliyun/systemd/omnigraph-kol-scan.service` + `.timer` — the scan unit with `OnFailure=`.
- `scripts/deploy-aliyun-session-alert.sh` — the deploy script for the alert unit.
- `scripts/capture_qr.py` — existing QR capture via CDP (may be reusable for level C).

### Project disciplines
- `CLAUDE.md` — Principle #5 (don't outsource SSH; Aliyun ops are agent-direct, Hermes writes are operator-channel), Principle #6 (end-to-end real verification mandatory), Principle #8 (right-size ceremony), Principle #10 (ISSUES.md).
- Memory `aliyun_vitaclaw_ssh.md` (new IP 47.117.244.253), `hermes_ssh.md`, `feedback_wechat_cookie_refresh_runbook.md`.
</canonical_refs>

<specifics>
## Specific Ideas / Live-Confirmed Facts

- CDP cookie extraction probe (proven, reuse): `python3` + `websocket` → `ws://localhost:9222/devtools/page/<id>` → `Network.getCookies {urls:["https://mp.weixin.qq.com"]}`. Returned 15 cookies incl. all 5 critical (slave_sid, data_ticket, rand_info, bizuin, slave_user). Token from URL after root-nav (949047506 observed).
- Aliyun→Hermes: `ssh hermes` (config stanza: HostName ohca.ddns.net, Port 49221, User sztimhdd, IdentityFile ~/.ssh/id_ed25519). LIVE post-P0.
- Hermes→Aliyun: new EIP `47.117.244.253` (old `101.133.154.49` dead). Hermes ssh alias `vitaclaw-aliyun` still points at the dead old IP — must update (Hermes-write, operator-channel).
- `hermes` CLI: `send -t telegram[:chat_id]` for notify; `chat '<prompt>'` for one-shot agent (if the trigger uses agent rather than direct script).
- Edge profile `C:\Edge-Auto-Profile` (NOT the Playwright `mcp-chrome-*` headless profile). Headed, port 9222.

## Verification (Principle #6 — MUST be end-to-end real, not just unit tests)
- Exercise the actual chain: simulate/await Aliyun detect → `ssh hermes` trigger → wrapper runs CDP refresh (at least level A path live) → scp writeback → Aliyun single-account test scan returns `ret=0` → confirm a real scan picks up new articles.
- Level C (QR) verification can be a dry-run / manual-confirm (true cookie death is hard to force on demand) but the QR-capture + Telegram-send path must be exercised at least once (send a real test QR image to Telegram).
</specifics>

<deferred>
## Deferred Ideas

- Rotating the WeChat account password itself is a user action (the phase redacts + wires env + notes rotation; the actual rotation is operator-done).
- Full removal of the 58931/MCP remote-CDP layer (路B makes it unused for this purpose) — leave it; not in scope to rip out.
- Scrubbing git history of the leaked password (#58) — phase redacts going forward; history-scrub is a separate decision (rotation is the real mitigation).
</deferred>

---

*Phase: kol-cookie-autorefresh*
*Context gathered: 2026-06-19 — locked architecture from 260615-orv investigation (no fresh research needed; RESEARCH.md is authoritative)*
