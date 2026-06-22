---
phase: kol-cookie-autorefresh
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/refresh_wechat_cookie.py
  - scripts/lib/cdp_client.py
  - tests/unit/test_refresh_wechat_cookie.py
autonomous: true
requirements: [KCA-2, KCA-3, KCA-5, KCA-6, KCA-4]
actor: REPO-CODE
must_haves:
  truths:
    - "The wrapper connects directly to localhost:9222 CDP via system python3 + websocket (no venv, no MCP)"
    - "The wrapper navigates to root https://mp.weixin.qq.com/ and reads the token from the landing URL, never from the current tab"
    - "The wrapper builds the cookie string as sorted name=value joined by '; '"
    - "Level A (token/page stale) recovers by root-nav alone; Level B fills env creds; Level C captures QR via canvas toDataURL and sends to Telegram via hermes send"
    - "After QR/account login the wrapper re-navigates root to rebind the CSRF token before writeback"
    - "The wrapper checks :9222 /json/version alive first; if down it relaunches headed Edge via WSL PowerShell interop"
    - "Writeback is atomic (.tmp then rename) on Aliyun and verified by a single-account test scan returning ret=0 before declaring success; a bad-creds verify result triggers rollback to the .bak-pre-refresh copy"
  artifacts:
    - path: "scripts/refresh_wechat_cookie.py"
      provides: "Hermes-side self-healing refresh orchestrator (A/B/C + self-heal + writeback + notify)"
      min_lines: 200
    - path: "scripts/lib/cdp_client.py"
      provides: "Direct CDP-over-websocket helper (Network.getCookies, Runtime.evaluate, Page.navigate)"
      min_lines: 60
    - path: "tests/unit/test_refresh_wechat_cookie.py"
      provides: "Unit coverage for cookie-string build, level detection, token-from-URL extraction, AND the writeback rollback-on-bad-creds branch"
      min_lines: 80
  key_links:
    - from: "scripts/refresh_wechat_cookie.py"
      to: "ws://localhost:9222/devtools/page/<id>"
      via: "scripts/lib/cdp_client.py Network.getCookies / Runtime.evaluate / Page.navigate"
      pattern: "Network.getCookies"
    - from: "scripts/refresh_wechat_cookie.py"
      to: "Aliyun kol_config.py"
      via: "scp .tmp + ssh atomic rename + single-account test scan verify"
      pattern: "batch_scan_kol.py --account"
    - from: "scripts/refresh_wechat_cookie.py (level C)"
      to: "Telegram"
      via: "hermes send -t telegram"
      pattern: "hermes send"
---

<objective>
Build the Hermes-side self-healing WeChat-cookie refresh wrapper — a standalone Python script
(system python3 + websocket-client, NOT the project venv) that connects directly to the headed
Edge CDP on localhost:9222, detects which of the three failure levels (A token/page stale,
B account-login, C true cookie death) applies, recovers the session, extracts a fresh TOKEN +
cookie string, writes it back to Aliyun's kol_config.py atomically with a single-account test-scan
verify, and notifies via Telegram (hermes send) on the C-level human request and on the final
success/failure summary. Includes the self-heal pre-step that relaunches headed Edge if :9222 is down.

Purpose: This is the active executor of the locked option-A chain. Aliyun only detects + hands off
(Plan 03); ALL browser/CDP/Telegram work lives here on Hermes. Reuses the proven A/B/C decision-tree
logic from skills/omnigraph_scan_kol/SKILL.md and the proven direct-CDP probe from RESEARCH.md — do
NOT reinvent.

Output: scripts/refresh_wechat_cookie.py (the orchestrator) + scripts/lib/cdp_client.py (CDP helper)
+ tests/unit/test_refresh_wechat_cookie.py (unit coverage). The script lives in the repo and syncs
to Hermes via the existing channel; Hermes-side registration is Plan 04 (operator).

Actor: [REPO-CODE] — orchestrator writes the script + tests locally + commits. The script is
DESIGNED to run on Hermes but is authored and unit-tested in the repo. No Aliyun/Hermes write here.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md
@skills/omnigraph_scan_kol/SKILL.md
@batch_scan_kol.py

<interfaces>
<!-- PROVEN direct-CDP probe (RESEARCH.md Test 1, runs on Hermes with system python3 + websocket). -->
<!-- Reuse this exact pattern; do NOT use playwright, the project venv, or the MCP /mcp layer. -->
Connect:  GET http://localhost:9222/json  → list of targets; pick the one whose url contains
          "mp.weixin.qq.com"; take target["webSocketDebuggerUrl"]
          (ws://localhost:9222/devtools/page/<id>).
Probe:    GET http://localhost:9222/json/version  → liveness check (self-heal pre-step).
CDP send: over the websocket, JSON-RPC {"id":N,"method":..,"params":..}; read until matching id.
Methods used:
  - Page.navigate {url:"https://mp.weixin.qq.com/"}    → root nav (token rebind)
  - Page.getNavigationHistory                          → read current/landing URL after redirect
       (token is the ?token=NNNN query param of the entry whose url is /cgi-bin/home...)
  - Runtime.evaluate {expression, returnByValue:true}  → DOM checks; returnByValue avoids the
       terminal `***` redaction trap (SKILL.md Step 3 note) — returns REAL values
  - Network.getCookies {urls:["https://mp.weixin.qq.com"]}  → ALWAYS returns complete cookies
       regardless of current tab URL (RESEARCH.md: 15 cookies, all 5 critical present)

<!-- IMPORT PATH (INFO 7 — pin this so Plan 03's invocation `cd ~/OmniGraph-Vault && python3
     scripts/refresh_wechat_cookie.py` resolves the sibling lib). The wrapper is invoked with cwd
     = repo root (~/OmniGraph-Vault) and script path scripts/refresh_wechat_cookie.py, so the
     script's own directory (scripts/) is NOT automatically on sys.path for `scripts.lib` package
     imports. Pin the import by inserting the script's own dir at the front of sys.path at the top
     of refresh_wechat_cookie.py, BEFORE importing the helper:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib.cdp_client import CdpClient, build_cookie_string, extract_token_from_url, critical_cookies_present
     This resolves `lib/cdp_client.py` whether run as `python3 scripts/refresh_wechat_cookie.py`
     from the repo root OR `python3 refresh_wechat_cookie.py` from inside scripts/. Do NOT use a
     `from scripts.lib...` package import (no __init__.py guaranteed; breaks from-repo-root cwd). -->

<!-- kol_config.py shape the writeback must preserve (verified). -->
kol_config.py:
  TOKEN = "<digits>"
  COOKIE = "<name=value; name=value; ...>"   # single line, sorted name=value joined by "; "
  FAKEIDS = { ... }                            # leave untouched

<!-- 5 critical auth cookies that MUST be present post-extract (RESEARCH.md). -->
slave_sid, data_ticket, rand_info, bizuin, slave_user

<!-- Verify contract on Aliyun (SKILL.md Step 5 / batch_scan_kol.py). -->
ssh aliyun "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --account <X> --max-articles 1"
  → exit 0 == ret=0 == valid; nonzero / 'WECHAT_SESSION_INVALID' == still bad
  (test account from SKILL.md example: 叶小钗)

<!-- Self-heal relaunch (RESEARCH.md Test 2, live-confirmed). -->
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command \
  'Start-Process "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList \
   "--remote-debugging-port=9222","--remote-debugging-address=127.0.0.1","--remote-allow-origins=*",\
   "--user-data-dir=C:\Edge-Auto-Profile","--no-sandbox"'
  (use base64 -EncodedCommand UTF-16LE for the PS payload to avoid SSH quoting pain)

<!-- Telegram notify (RESEARCH.md): scriptable, no gateway/agent loop needed. -->
hermes send -t telegram "<message>"          # success/failure summary
hermes send -t telegram --image /tmp/wx_qr_code.png "<caption>"   # C-level QR send
  (CAPABILITY-GATED — see Task 2: the `hermes send --image` flag is NOT yet confirmed on the local
   Hermes build. The wrapper MUST probe `hermes send --help` for `--image` support at runtime; if
   supported → send the image; if NOT supported → fall back to sending the text caption + the
   /tmp/wx_qr_code.png path so the operator can open it. Plan 04's operator prompt independently
   confirms `--image` support on Hermes. Plan 05 acceptance is gated on the SAME capability:
   "image delivered if --image supported, else QR png at /tmp + path sent as text." Do NOT block the
   wrapper on the unverified flag.)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: [REPO-CODE] CDP-over-websocket helper + cookie/token primitives (KCA-2)</name>
  <read_first>
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (Test 1 probe: /json target pick, ws connect, Network.getCookies; the tab-drift gotcha — token from root-nav landing URL, NOT current tab)
    - skills/omnigraph_scan_kol/SKILL.md (Step 3 "Extract credentials via CDP": cookie string = sorted name=value joined "; "; the `***` redaction trap → use returnByValue=true; CSRF rebind note)
    - scripts/capture_qr.py (existing CDP-via-HTTP attempt — note it is the OLD fragile HTTP approach; the new helper uses websocket-client directly, cleaner)
  </read_first>
  <behavior>
    - build_cookie_string([{name:"b",value:"2"},{name:"a",value:"1"}]) == "a=1; b=2"  (sorted by name)
    - build_cookie_string([]) == ""
    - extract_token_from_url("https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=949047506") == "949047506"
    - extract_token_from_url("https://mp.weixin.qq.com/misc/appmsgcomment?x=1") is None  (subpage w/o token → None, must trigger root-nav retry, not crash)
    - critical_cookies_present(["slave_sid","data_ticket","rand_info","bizuin","slave_user","ua_id"]) is True
    - critical_cookies_present(["ua_id","_clck"]) is False  (missing the 5 critical)
  </behavior>
  <action>
    Create `scripts/lib/cdp_client.py` (system-python3-compatible, stdlib + `websocket-client` only;
    NO project-venv imports, NO playwright). Provide:

    - `class CdpClient:` constructor `(base_url="http://localhost:9222", url_filter="mp.weixin.qq.com")`.
      - `is_alive() -> bool` — GET `{base_url}/json/version`, return True iff HTTP 200 within 5s.
      - `connect()` — GET `{base_url}/json`, pick the first target whose `url` contains `url_filter`
        (fall back to first `type=="page"` target if none match, so root-nav can still proceed on a
        blank tab), open the websocket to `target["webSocketDebuggerUrl"]`. Raise `NoWeChatTab` if no
        page target at all.
      - `send(method, params=None) -> dict` — JSON-RPC over the ws with an incrementing id; block-read
        frames until the response with matching id; raise on CDP `error`.
      - convenience wrappers: `navigate(url)` (Page.navigate), `current_url()` (Page.getNavigationHistory
        → entries[currentIndex].url), `evaluate(expression)` (Runtime.evaluate with
        `returnByValue=true, awaitPromise=true` → returns the `.result.value`), `get_cookies()`
        (Network.getCookies `{urls:["https://mp.weixin.qq.com"]}` → list of cookie dicts).

    Add three pure helper functions (importable + unit-testable WITHOUT a live browser) at module top
    of `scripts/lib/cdp_client.py`:
    - `build_cookie_string(cookies: list[dict]) -> str` — `"; ".join(sorted(f"{c['name']}={c['value']}" for c in cookies))`.
    - `extract_token_from_url(url: str) -> str | None` — parse the `token` query param; return None if absent.
    - `CRITICAL_COOKIES = ("slave_sid","data_ticket","rand_info","bizuin","slave_user")` +
      `critical_cookies_present(names: list[str]) -> bool` — all 5 in names.

    Write `tests/unit/test_refresh_wechat_cookie.py` covering the six behaviors above (pure functions,
    no network). Use plain pytest; these run in the repo venv during CI even though the script runs on
    Hermes system-python at runtime. (Task 3 adds one more test to this same file for the rollback
    branch.)
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/lib/cdp_client.py` exists and contains the literal string `Network.getCookies`.
    - `grep -n "returnByValue" scripts/lib/cdp_client.py` returns ≥ 1 (avoids the `***` redaction trap).
    - `grep -n "sorted" scripts/lib/cdp_client.py` returns ≥ 1 (cookie string is sorted).
    - `venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v` → all 6 behavior tests pass.
    - The module imports with stdlib + websocket only: `grep -nE "^import |^from " scripts/lib/cdp_client.py` shows NO `import playwright`, NO `import config`, NO project-venv module.
  </acceptance_criteria>
  <done>cdp_client.py provides a websocket CDP client + the 3 pure helpers; 6 behavior tests pass; no venv/playwright/MCP dependency.</done>
</task>

<task type="auto">
  <name>Task 2: [REPO-CODE] A/B/C refresh orchestrator + self-heal + Telegram notify (KCA-2, KCA-3, KCA-5, KCA-6)</name>
  <read_first>
    - scripts/lib/cdp_client.py (just created — the CDP primitives this orchestrator drives; note the pinned import path in <interfaces>)
    - skills/omnigraph_scan_kol/SKILL.md (FULL A/B/C tree: Decision Tree steps 1-5, Account Login Fallback, QR Code Login Flow Q1-Q5 incl. canvas toDataURL selector `img.login__type__container__scan__qrcode`, poll loop ~5min/30×10s, CSRF rebind, secret-redaction trap)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (tab-drift gotcha → root-nav for token; Test 2 PowerShell relaunch absolute path + base64 EncodedCommand)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Hop ③ levels A/B/C definitions; #58 env-cred wiring; self-heal spec)
  </read_first>
  <action>
    Create `scripts/refresh_wechat_cookie.py` (system python3, stdlib + websocket-client + the
    sibling `lib/cdp_client.py`). It is the orchestrator. Structure as small functions, main flow:

    IMPORT PATH (INFO 7 — pin so Plan 03's `cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py`
    resolves the helper): at the very top, BEFORE importing the helper, do
       `import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`
    then `from lib.cdp_client import CdpClient, build_cookie_string, extract_token_from_url, critical_cookies_present`.
    Do NOT use `from scripts.lib...` (package import breaks when cwd is the repo root). This makes the
    import work both from the repo root and from inside scripts/.

    STEP 0 — SELF-HEAL (KCA-6): build `CdpClient()`. If `not client.is_alive()`: relaunch headed
    Edge via WSL→Windows PowerShell interop. Use the absolute path
    `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe` and pass the Start-Process command
    (the msedge.exe + ArgumentList from <interfaces>) as a base64 `-EncodedCommand` (UTF-16LE) to avoid
    SSH/quoting issues. Then poll `is_alive()` up to ~30s (1s interval); if still dead, send Telegram
    `⚠️ Edge CDP :9222 relaunch failed` and exit 1.

    STEP 1 — CONNECT + LEVEL DETECT: `client.connect()`. `navigate("https://mp.weixin.qq.com/")`,
    wait ~3s for redirect, read `current_url()`. Determine level via DOM check
    (`evaluate("document.body.innerText.substring(0,500)")` look for "AI老兵日记"/"原创"/"新的创作"
    = logged-in dashboard) AND `extract_token_from_url(current_url())`:
      - Level A (token/page stale): dashboard text present but token missing/stale → re-navigate root,
        re-read token. If "请重新登录" visible → click the 登录 link via
        `evaluate("document.querySelector('a, .login').click()")` (per SKILL.md step 4), wait, re-check.
      - Level B (account-login): no dashboard, login landing with "使用账号登录" → read creds from
        env `WECHAT_MP_ACCOUNT` / `WECHAT_MP_PASSWORD` (os.environ; NEVER hardcoded — KCA-8), click
        account-login, fill fields + click `.btn_login` via Runtime.evaluate (SKILL.md Account Login
        Fallback steps), wait 5s, re-check dashboard. On the linked-account security-page pitfall
        (different account name on 安全保护 page) → do NOT retry, fall through to Level C.
      - Level C (true cookie death — KCA-3): capture QR via canvas toDataURL
        (`document.querySelector('img.login__type__container__scan__qrcode')` → canvas drawImage →
        toDataURL('image/png')), save to `/tmp/wx_qr_code.png`, send to Telegram via the
        capability-gated `notify_image()` helper (KCA-5 — see NOTIFY below). Poll up to ~5min (30 ×
        10s) for dashboard text; on QR expiry ("二维码已过期") refresh QR (max 2 refreshes). On
        timeout → Telegram `⏰ 扫码超时（5分钟），请稍后手动触发` and exit 1.

    STEP 2 — CSRF REBIND (KCA-2): after ANY login (B or C) OR token-stale fix, `navigate` root AGAIN,
    wait for redirect, read the NEW token from the landing URL (SKILL.md ret=200040 note — the
    post-login token is not yet bound; root-nav rebinds it). The token MUST come from the landing URL,
    never the current/drifted tab (RESEARCH.md gotcha).

    STEP 3 — EXTRACT: `get_cookies()`, assert `critical_cookies_present(...)` (all 5). Build
    `cookie_str = build_cookie_string(cookies)`. Hold `token` (from Step 2) and `cookie_str`.
    Do NOT print full secret values (use the SKILL.md hex/returnByValue discipline — log only lengths
    + first 6 chars for diagnostics).

    STEP 4 — WRITEBACK (KCA-4): hand off to the writeback function (Task 3). On its success/failure,
    STEP 5 — NOTIFY (KCA-5): `hermes send -t telegram` a one-line summary:
    `✅ KOL cookie refreshed (level {A|B|C}); Aliyun test-scan ret=0` OR `❌ refresh failed: {reason}`.

    NOTIFY helpers (KCA-5, capability-gated for image — WARNING 3 resolution):
    - `notify(text)` — `hermes send -t telegram "<text>"`. Used for summaries + warnings.
    - `notify_image(png_path, caption)` — FIRST probe `hermes send --help` (or a cached one-time check)
      for an `--image` flag. If present: `hermes send -t telegram --image <png_path> "<caption>"`. If
      absent: fall back to `notify(caption + " — QR saved at " + png_path)` (text-only) and log that
      the image flag is unsupported. This is the SAME capability gate Plan 05 Task 2 asserts against
      ("image delivered if --image supported, else QR png at /tmp + path sent as text") — keep the two
      consistent. Do NOT hard-require `--image`; do NOT block the wrapper on it.

    Add `argparse`: `--cdp-url` (default http://localhost:9222), `--level` (optional force A/B/C for
    testing), `--dry-run` (do everything except STEP 4 writeback — print what WOULD be written),
    `--test-account` (default 叶小钗, passed to the verify scan). Exit codes: 0 success, 1 failure,
    2 needs-human (C-level timeout).

    Reuse — do NOT reinvent — the A/B/C decision logic, selectors, poll cadence, CSRF-rebind, and
    secret-redaction discipline from skills/omnigraph_scan_kol/SKILL.md; this script is the
    scriptified form of that agent tree.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import ast,sys; ast.parse(open('scripts/refresh_wechat_cookie.py').read()); print('parse_ok')" && grep -c "hermes send" scripts/refresh_wechat_cookie.py</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/refresh_wechat_cookie.py` parses as valid Python (ast.parse prints `parse_ok`).
    - `grep -n "sys.path.insert" scripts/refresh_wechat_cookie.py` returns ≥ 1 (pinned import path — INFO 7).
    - `grep -n "is_alive" scripts/refresh_wechat_cookie.py` returns ≥ 1 (self-heal pre-step, KCA-6).
    - `grep -n "EncodedCommand\|powershell" scripts/refresh_wechat_cookie.py` returns ≥ 1 (PowerShell relaunch, KCA-6).
    - `grep -n "WECHAT_MP_ACCOUNT" scripts/refresh_wechat_cookie.py` returns ≥ 1 AND `grep -n "Hardun\|huhai" scripts/refresh_wechat_cookie.py` returns 0 (env creds, never literal — KCA-8).
    - `grep -n "login__type__container__scan__qrcode" scripts/refresh_wechat_cookie.py` returns ≥ 1 (level C canvas QR — KCA-3).
    - `grep -n "hermes send --help\|--image" scripts/refresh_wechat_cookie.py` returns ≥ 1 (capability-gated image notify — WARNING 3).
    - `grep -c "hermes send" scripts/refresh_wechat_cookie.py` returns ≥ 2 (C-level QR + summary — KCA-5).
    - `grep -n "navigate(\"https://mp.weixin.qq.com/\")\|navigate('https://mp.weixin.qq.com/')" scripts/refresh_wechat_cookie.py` returns ≥ 2 (root-nav for level detect AND CSRF rebind — KCA-2).
  </acceptance_criteria>
  <done>refresh_wechat_cookie.py implements self-heal pre-step, A/B/C detect+recover, CSRF rebind via root-nav, capability-gated QR-to-Telegram for level C, env-based B creds, pinned import path, and a notify summary; parses clean; no literal secrets.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: [REPO-CODE] Atomic writeback to Aliyun + single-account test-scan verify + tested rollback (KCA-4)</name>
  <read_first>
    - batch_scan_kol.py (the --account / --max-articles path; SESSION_INVALID_THRESHOLD; sys.exit(2) on WECHAT_SESSION_INVALID — the verify contract)
    - skills/omnigraph_scan_kol/SKILL.md (Step 4 write to kol_config.py — patch TOKEN + cookie line; the escape-drift + hex-verify discipline; Step 5 single-account test scan ret=0)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Hop ④: atomic write .tmp+rename, verify with test scan BEFORE declaring success, secret-redaction trap)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (Hermes→Aliyun channel works via sync-kol-db cron; new EIP 47.117.244.253; ssh alias vitaclaw-aliyun is STALE → use explicit IP or the alias only after Plan 04 updates it)
  </read_first>
  <behavior>
    - writeback_to_aliyun, when the injected ssh-test-scan runner returns a NONZERO exit code (bad
      creds), MUST: (a) invoke the rollback restore of kol_config.py.bak-pre-refresh, (b) NOT declare
      success, (c) return a falsey/failure result. Pin this with a unit test that injects a fake
      runner returning nonzero and asserts the rollback path ran + failure returned (no live Aliyun).
  </behavior>
  <action>
    Add a `writeback_to_aliyun(token, cookie_str, test_account, dry_run, *, run_ssh=<injectable>)`
    function in `scripts/refresh_wechat_cookie.py` (or a small `scripts/lib/` helper imported by it).
    It runs on Hermes and pushes the refreshed credentials to Aliyun atomically, then verifies.
    Make the ssh-command executor an INJECTABLE callable (default = real subprocess runner) so the
    verify + rollback branches are unit-testable without a live Aliyun (see <behavior>).

    Procedure:
    1. Build a new kol_config.py CONTENT in memory: read a local template OR (preferred) generate the
       two lines `TOKEN = "{token}"` and `COOKIE = "{cookie_str}"` and SED-replace them into the
       remote file rather than overwriting FAKEIDS. Since FAKEIDS must be preserved and lives only on
       Aliyun, do the edit REMOTELY: write a tiny remote python one-liner (passed over ssh) that:
       FIRST copies `/root/OmniGraph-Vault/kol_config.py` → `kol_config.py.bak-pre-refresh` (the
       rollback source), then reads the original, replaces the `TOKEN = "..."` line and the
       `COOKIE = "..."` line with the new values, writes to `kol_config.py.tmp` in the same dir, then
       `os.replace("kol_config.py.tmp", "kol_config.py")` (atomic). Pass token + cookie via stdin or
       a base64-encoded arg to avoid shell-escaping the cookie string (it contains `;`, `+`, `=`, `/`).
       Define the Aliyun ssh target as a module constant `ALIYUN_SSH` — default to the alias
       `vitaclaw-aliyun` (which Plan 04 repoints to 47.117.244.253); allow `--aliyun-ssh` override so
       the operator can pass the explicit `root@47.117.244.253` + key during testing before the alias
       is fixed.
    2. If `dry_run`: print the new TOKEN (first 6 chars) + cookie length + the remote command that
       WOULD run, and return without touching Aliyun.
    3. VERIFY (KCA-4): run over ssh (via the injectable runner)
       `cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --account {test_account} --max-articles 1`
       Capture exit code. ret=0 (exit 0) → success. Nonzero or stderr contains `WECHAT_SESSION_INVALID`
       / `ret=200003` → FAILURE: the writeback produced bad creds. On failure, attempt ONE rollback —
       restore `kol_config.py.bak-pre-refresh` via `os.replace` (over ssh) and return failure so
       STEP 5 notifies `❌`.
    4. Hex-verify guard (SKILL.md trap): before declaring success, read back the remote TOKEN bytes
       via ssh `python3 -c "...data.find(b'TOKEN=')..."` and assert it does NOT hex-decode to `***`
       (`373937343438373930` pattern) — guards against the terminal-redaction-wrote-stars failure.

    Keep the function ≤ ~70 lines; it is glue. The atomic-write + verify-before-success + rollback are
    the three non-negotiables (CONTEXT Hop ④: "Do NOT half-write prod kol_config.py").

    THEN add ONE behavioral unit test to `tests/unit/test_refresh_wechat_cookie.py` (per <behavior>):
    construct `writeback_to_aliyun(...)` with `run_ssh=` a fake that records calls and returns a
    NONZERO exit code for the verify scan; assert (a) a rollback ssh command targeting
    `kol_config.py.bak-pre-refresh` was issued, and (b) the function returns failure / does not raise
    "success". This pins the most dangerous path (writes prod kol_config.py) WITHOUT a live Aliyun —
    closing the WARNING 5 untested-rollback gap before Plan 05's live exercise.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/refresh_wechat_cookie.py').read()); print('parse_ok')" && venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v && grep -n "os.replace\|\.tmp" scripts/refresh_wechat_cookie.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "writeback_to_aliyun\|writeback" scripts/refresh_wechat_cookie.py` returns ≥ 1.
    - `grep -n "os.replace\|\.tmp" scripts/refresh_wechat_cookie.py` returns ≥ 1 (atomic write — KCA-4).
    - `grep -n "batch_scan_kol.py --account" scripts/refresh_wechat_cookie.py` returns ≥ 1 (test-scan verify — KCA-4).
    - `grep -n "bak-pre-refresh\|rollback" scripts/refresh_wechat_cookie.py` returns ≥ 1 (rollback on bad creds).
    - `grep -n "run_ssh" scripts/refresh_wechat_cookie.py` returns ≥ 1 (injectable ssh runner for testability — WARNING 5).
    - `grep -n "373937343438373930\|\*\*\*" scripts/refresh_wechat_cookie.py` returns ≥ 1 (hex redaction guard).
    - `venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v` → ALL tests pass, including the new rollback-branch test (asserts rollback ran + failure returned when verify scan exits nonzero — WARNING 5).
    - File still parses (`parse_ok`).
  </acceptance_criteria>
  <done>writeback_to_aliyun does atomic remote .tmp+os.replace preserving FAKEIDS, verifies via single-account test scan (ret=0 gate), rolls back to kol_config.py.bak-pre-refresh on failure, and guards the `***` redaction trap; success is declared ONLY after the verify scan passes; the rollback-on-bad-creds branch is pinned by a behavioral unit test using an injectable ssh runner (no live Aliyun needed — closes WARNING 5).</done>
</task>

</tasks>

<verification>
- `venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v` → all behavior tests pass (KCA-2 primitives + the WARNING 5 rollback-branch test).
- `python -c "import ast; ast.parse(open('scripts/refresh_wechat_cookie.py').read())"` → no syntax error.
- grep gates above confirm: pinned import path (INFO 7), self-heal (KCA-6), A/B/C + CSRF rebind (KCA-2), level-C QR→Telegram capability-gated (KCA-3, WARNING 3), notify (KCA-5), atomic writeback + test-scan verify + tested rollback (KCA-4, WARNING 5), env creds not literals (KCA-8).
- NOTE: live CDP/scp behavior is NOT exercised here (no logged-in Edge in the repo env) — that is Plan 05 end-to-end real verification on Hermes/Aliyun (Principle #6). The rollback branch, however, IS unit-tested here via the injectable runner (no longer live-only).
</verification>

<success_criteria>
- A standalone Hermes-runnable refresh wrapper exists with the full A/B/C tree, self-heal, CSRF rebind, atomic writeback + verify + tested rollback, and capability-gated Telegram notify, reusing the SKILL.md logic.
- Pure primitives + the rollback branch are unit-tested green; the orchestrator + writeback parse and pass all grep contract gates.
- The script reads B-level creds from env (KCA-8), targets port 9222 by default (consistent with Plan 01, KCA-7), and uses a pinned sys.path import so Plan 03's repo-root invocation resolves the helper (INFO 7).
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-02-SUMMARY.md`
</output>
