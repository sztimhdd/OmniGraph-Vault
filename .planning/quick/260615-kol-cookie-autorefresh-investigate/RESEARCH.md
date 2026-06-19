# RESEARCH — 260615-kol-cookie-autorefresh-investigate

**Status:** ⏸ PAUSED at P0 external blocker (Aliyun egress down, IT pinged). Investigation COMPLETE; two core capabilities LIVE-TESTED OK. Architecture LOCKED with user. Implementation deferred to follow-up quick (blocked on P0).
**Mode:** started read-only/diagnostic → **switched to implementation** mid-session (user said "直接继续修", gave recovery creds, locked architecture). So this is no longer pure read-only — see "Changes made this session" below.
**Stamp:** 2026-06-17 evening ADT / 2026-06-18 ~early CST. (Aliyun=CST UTC+8, laptop=ADT UTC-3, Hermes=ADT.)

---

## TL;DR

User's pain: WeChat-cookie refresh is manual (no expiry notification). Investigation found the auto-chain is **partially built but terminates in a no-op**, AND surfaced a **fresh P0**: the Aliyun box was **rebuilt tonight (boot 20:06 CST 2026-06-17)** and lost all public egress (NAT/SNAT not updated for new private IP). 

**Two architecture-critical capabilities were LIVE-TESTED and WORK:**
1. ★ **CDP cookie extraction** from the logged-in Edge on Hermes — all 5 critical auth cookies retrieved (refutes SKILL.md's HttpOnly worry).
2. ★ **WSL→Windows PowerShell interop** — Hermes WSL can relaunch a headed CDP Edge (self-heal capability confirmed).

Architecture is **locked** (Hermes-active, 选甲/option-A push, 路B/direct-CDP). Only remaining work (trigger wiring + end-to-end test) is **blocked on P0 egress fix** (IT, console-level).

---

## ENVIRONMENT (current, verified this session)

### Aliyun (REBUILT tonight — evidence is from the NEW instance)
- **Live IP: `47.117.244.253`** (key auth works). Old `101.133.154.49` DEAD. `47.103.73.20` rejects key.
- New instance: hostname `iZj1imk39yc55iZ`, instance `i-uf6htkiqj1imk39yc55i`, **booted 2026-06-17 20:06 CST**, region cn-shanghai, vpc-uf6kv36eg68n9dsd7qnum, **new private IP `172.18.12.151`**.
- (Pre-outage box was `iZuf65iclmdqtv2ol6cazcZ` / `i-uf65iclmdqtv2ol6cazc` — different instance. Disk/journal preserved across rebuild: persistent journal back to May 7, both hostnames present.)
- SSH from laptop: `ssh -i ~/.ssh/aliyun_orchestrator_ed25519 -o IdentitiesOnly=yes root@47.117.244.253` (alias `aliyun-vitaclaw` still points at dead old IP — use explicit IP+key for now).
- Project INTACT: `/root/OmniGraph-Vault` git HEAD `ba1121c`, venvs `venv` + `venv-aim1`, `/root/.hermes/`, `kol_config.py` (mtime Jun 10 01:54), `data/kol_scan.db` (1807 articles, **max scanned_at = 2026-06-10 01:58 → 0 new in 7 days**).
- Aliyun pubkey: `ssh-ed25519 AAAAC3...zb8d aliyun@vitaclaw.com`, fp `SHA256:h9LibuLstmLMfGRYho8NJcBy8cU31AxSvz16KnizhzQ`. **User has added this to Hermes authorized_keys ✅** (2026-06-17).

### Hermes (RO until 2026-06-22 — but user is operating it directly tonight)
- `ssh -p 49221 sztimhdd@ohca.ddns.net`. Host `OH-Desktop`, WSL2 (Ubuntu 24.04), DNS `ohca.ddns.net → 142.67.138.72`.
- `hermes` CLI at `~/.local/bin/hermes`: has `send` (scriptable: "no LLM, no agent loop, no running gateway required for bot-token platforms like Telegram"), `chat` (one-shot agent), `cron`. Gateway proc alive since Jun 15.
- Cron `sync-kol-db-from-aliyun` daily 03:00, last run **ok** → **Hermes→Aliyun channel WORKS**. Hermes→Aliyun new IP :22 = REACHABLE.
- Hermes ssh alias `vitaclaw-aliyun` → DEAD old IP `101.133.154.49` (stale, needs update to 47.117.244.253).
- ⚠️ NOTE: WSL was bounced tonight (user "关了WSL"); after restart sshd + portproxy needed re-up. Currently back: :49221 OK.

### CDP / browser topology (Hermes)
- Intended: `npx @playwright/mcp --port 8931` (internal) → `:58931` (external) → `--cdp-endpoint http://localhost:9222` → Edge `:9222` with WeChat MP tab.
- **`:9222` is LIVE** (Edge 150, headed). **`:9223` is DEAD.** ⚠️ Code + CLAUDE.md say `9223` — **MISMATCH to reconcile at implementation.**
- Live Edge launch cmdline (captured): `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --remote-allow-origins="*" --user-data-dir="C:\Edge-Auto-Profile" --no-sandbox`
- Profile `C:\Edge-Auto-Profile` EXISTS; `Default/Network/Cookies` persisted (327KB, mtime 12:06) → **restart reuses profile = login state survives.**
- **No autostart task for this Edge** — manually launched (a self-heal gap option-A must cover).
- MCP `:8931/:58931` NOT currently listening (only headless `npm exec @playwright/mcp --headless` running, unrelated).

---

## 🔴 P0 ROOT CAUSE — Aliyun rebuilt box has NO public egress (THE total blocker)

Hard evidence (cross-verified, real app path not just /dev/tcp):
```
internal metadata 100.100.100.200 → HTTP 200    ✅ (cn-shanghai, vpc-uf6kv36...)
DNS resolve baidu.com → 124.237.177.164          ✅ (local systemd-resolved)
curl baidu / mp.weixin / aliyun.com (public)     🔴 ALL 000
ping baidu IP 124.237.177.164                     🔴 100% loss
ping NAT gw 172.18.15.253 (internal)              ✅ 0% loss
```
**Diagnosis: traffic reaches the NAT gateway but the gateway does NOT SNAT it out.** Cause = rebuild gave new private IP `172.18.12.151`, but Aliyun VPC NAT-gateway SNAT entry / EIP binding still points at the OLD private IP. **Console-level fix (user/IT), not in-box.**

**WireGuard ruled OUT as cause** (user hypothesis, tested & refuted):
- `ip route get 124.237.177.164` → `via 172.18.15.253 dev eth0` — baidu traffic goes via NAT gw, NOT through WG.
- `ip rule show` = only default 3 tables (local/main/default), **no fwmark, no policy routing hijack**.
- WG `AllowedIPs` is a **whitelist** of Google/GitHub/Azure `/32`s only (no `0.0.0.0/0`, no `Table=`) → cannot hijack default route.
- WG tunnel IS independently dead (`0 B received`, handshake ts `0`, endpoint `35.198.243.36:51820` unreachable) but that only breaks Vertex/GitHub/Databricks egress — irrelevant to baidu/wechat.
- Even `https://www.aliyun.com` (domestic, no GFW) = 000 → it's ALL public egress dead, not target-specific/GFW.

**Fix checklist for IT/console:** (1) NAT gateway SNAT entry → update private IP to `172.18.12.151`; (2) or re-associate EIP `47.117.244.253` to new instance's ENI; (3) verify security-group egress not reset to deny on rebuild.

---

## State of the existing auto-chain (what's BUILT / BROKEN / MISSING)

### dv7 "FAILED" root cause CONFIRMED
Jun 10 19:04 (old box): 50/54 accounts `ret=200003` → `WECHAT_SESSION_INVALID: 50/54` → `sys.exit(2)` → systemd `Failed` → `OnFailure` fired → touched `/root/.hermes/wechat-session-stale` (content `2026-06-10T11:04:46Z`, **still there 7 days later, un-actioned**). Cookie dead since ~Jun 10.

### Detection works; alert is a NO-OP (the smoking gun)
- `batch_scan_kol.py:42` `SESSION_INVALID_THRESHOLD = 0.30`; `:228` detect `ret=200003`; `:310-312` `if invalid/total ≥ 0.30: print(WECHAT_SESSION_INVALID); sys.exit(2)`.
- `deploy/aliyun/systemd/omnigraph-kol-scan.service`: `OnFailure=omnigraph-kol-scan-alert.service`.
- 🔴 `omnigraph-kol-scan-alert.service` ExecStart = **only** `mkdir -p /root/.hermes && date > /root/.hermes/wechat-session-stale`. **No Telegram, no SSH, no notify. Nothing consumes the flag.** ← root of "passive, no notification".
- `batch_scan_kol.py` has ZERO telegram/notify/ssh code. All the Telegram/QR logic in SKILL.md is the **Hermes Openclaw agent** path, never invoked by the Aliyun cron.

### Telegram on Aliyun: configured but UNREACHABLE
`.env` has `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` ✅, but Aliyun **cannot reach api.telegram.org** (GFW + not in WG tunnel; real `requests` → ConnectionError). → **Aliyun cannot notify the user directly.** (This killed my pre-outage "fix-A = Telegram curl from Aliyun" idea. Notify must go via Hermes.)

---

## ★ LIVE TESTS (both PASSED — the high-value findings)

### Test 1 — CDP cookie extraction from logged-in Edge ✅
User logged into WeChat MP in the `:9222` Edge (1 tab: `mp.weixin.qq.com/cgi-bin/home?...token=949047506`, title "公众号"). Probe (system `python3` + `websocket`, direct CDP `ws://localhost:9222/devtools/page/...`, `Network.getCookies`):
```
TOKEN_FROM_URL: 949047506
COOKIE_COUNT: 15
CRITICAL_PRESENT: slave_sid ✅ data_ticket ✅ rand_info ✅ bizuin ✅ slave_user ✅
```
**All 5 critical auth cookies retrieved** → refutes SKILL.md's "⚠️ CDP may not return HttpOnly cookies" worry. Pure-script refresh (no QR, no vision) is viable when session is alive. Did NOT need venv or MCP server — **direct CDP is enough → validates 路B.**

### Test 2 — WSL→Windows PowerShell interop / headed-Edge relaunch ✅
- `WSLInterop-late: enabled`; bare `powershell.exe` → `command not found` is just PATH (non-interactive shell), NOT interop off.
- **Absolute path works:** `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "Write-Output PWSH_OK"` → `PWSH_OK`. `/mnt/c` mounted.
- Captured live Edge cmdline + confirmed profile `C:\Edge-Auto-Profile` persists cookies → **Hermes WSL CAN relaunch a headed CDP Edge that restores login.** Relaunch cmd:
  ```bash
  /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command \
   'Start-Process "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList \
    "--remote-debugging-port=9222","--remote-debugging-address=127.0.0.1","--remote-allow-origins=*","--user-data-dir=C:\Edge-Auto-Profile","--no-sandbox"'
  ```
- PS quoting via SSH is painful — use **base64 `-EncodedCommand`** (UTF-16LE) for any non-trivial PS script.

---

## ARCHITECTURE — LOCKED with user

**Three failure levels (key mental model):**
| Level | Symptom | Fix | Headless-automatable? |
|---|---|---|---|
| A token/page stale | cookie alive, URL token old, "请重新登录" | nav root URL / click login | ✅ pure script |
| B cookie expired, account-login | cookie dead, browser-saved pw | account login form | ⚠️ scriptable, security-page risk |
| C true cookie death | must phone-scan QR | human scan | ❌ needs human |

**User decisions:**
1. ✅ Browser/cookie driving = **Hermes** (not Aliyun). Bonus: if CDP Edge crashes, Hermes can PowerShell-relaunch it (Test 2).
2. ✅ **选甲 (option-A push):** Aliyun detects expiry → `ssh hermes` → `hermes chat 'refresh wechat cookie + write back'`.
3. ✅ **路B:** refresh script connects **direct to localhost:9222 CDP**; DROP the 58931/MCP layer (Test 1 proves direct works; MCP-remote-exposure was only needed if Aliyun drove the browser, which it doesn't).
4. ✅ SSH key auth = **full-access key** (user chose over my recommended restricted `command=` lockdown; their home machine, their risk call).

**Locked flow:**
```
Aliyun kol-scan detects ret=200003 ≥30% → exit(2) → OnFailure
  → (NEW) ssh hermes "hermes chat 'refresh wechat cookie and write back to aliyun'"
      → Hermes refresh tree (it can tell A/B/C):
          A → CDP nav → new token
          B → account login → cookie
          C → capture QR → `hermes send -t telegram` to USER → user scans → back to cookie grab
      → Hermes scp kol_config.py BACK to Aliyun (Hermes→Aliyun channel works)
  → next scan recovers
```

---

## Changes made this session (NOT read-only anymore)

1. **Aliyun `~/.ssh/config`**: wrote `Host hermes` stanza (HostName ohca.ddns.net, Port 49221, User sztimhdd, IdentityFile ~/.ssh/id_ed25519, IdentitiesOnly yes, accept-new). Backup: `config.bak-pre-hermes-260617`. Idempotent. **Untested** (P0 blocks `ssh hermes` from Aliyun — currently times out due to egress, not key).
2. **User** added Aliyun pubkey to Hermes `authorized_keys`.
3. **Hermes** `/tmp/cdp_cookie_probe.py` — temp probe (should clean up; harmless).

---

## Remaining work (ALL blocked on P0 egress)

- [ ] (after P0) Test Aliyun→Hermes via new key (`ssh hermes` from Aliyun) — currently timeout.
- [ ] (follow-up quick / implementation) Replace no-op `omnigraph-kol-scan-alert.service` with: trigger `ssh hermes "hermes chat '...refresh...'"`. ~10-30 LoC unit change.
- [ ] Hermes refresh wrapper (路B): direct CDP :9222 → detect A/B/C → grab cookie/token → write kol_config.py → scp to Aliyun → Telegram on C. Size depends on reusing SKILL tree logic as a script (medium; could be plan-phase if C-path QR automation included).
- [ ] Reconcile **9222 vs 9223** mismatch (code/CLAUDE.md say 9223, live is 9222).
- [ ] Optional self-heal: autostart task for the headed CDP Edge (none today).
- [ ] Update Hermes ssh alias `vitaclaw-aliyun` → new IP `47.117.244.253` (Hermes write-op = operator-channel, RO until 06-22).

---

## Candidate ISSUES.md rows (orchestrator transcribes — PRINCIPLE #10)

1. 🔴 **P0: rebuilt Aliyun box has no public egress** — NAT-gateway SNAT/EIP not updated for new private IP `172.18.12.151` after 2026-06-17 20:06 rebuild. All public egress dead (kol-scan, translate, ingest, Hermes-handoff all broken until fixed). Console-level. WireGuard ruled out.
2. 🟡 **kol-scan expiry alert is a no-op** — `omnigraph-kol-scan-alert.service` only touches `/root/.hermes/wechat-session-stale`; no notify/handoff; nothing consumes it. Cookie dead since ~Jun 10, flag un-actioned 7 days. (Target of the follow-up fix quick.)
3. 🔴 **Plaintext WeChat account password in PUBLIC repo** — `skills/omnigraph_scan_kol/SKILL.md:91` literal account + password (Account-Login-Fallback). Public GitHub. Rotate + redact. (Out of scope for cookie-autorefresh but live exposure. Secret NOT reproduced here.)
4. 🔵 **9222/9223 CDP port mismatch** — code/CLAUDE.md `9223`, live Edge `9222`. Reconcile.

---

## Discipline log
- SSH probes/ops run from main session (SSH can't be delegated to sub-agents here).
- Methodology correction (user-flagged twice): raw `/dev/tcp`/`socket` probes are UNRELIABLE in non-interactive SSH context — verified all reachability verdicts via real app path (curl/requests/ping + route inspection).
- Secret at SKILL.md:91 flagged, NOT reproduced.
- Hermes WSL bounce + sshd/portproxy loss diagnosed as user-side (user "关了WSL"), not caused by our changes (we only wrote Aliyun client config).
