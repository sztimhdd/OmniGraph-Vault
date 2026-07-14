---
phase: quick-260713-sxq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/refresh_wechat_cookie.py
autonomous: true
requirements:
  - WCR-1  # URL-token login detection (DECISION 1)
  - WCR-2  # Telegram-only notify verified (DECISION 2)
  - WCR-3  # Simplified local-only relaunch (DECISION 3)
user_setup: []

must_haves:
  truths:
    - "detect_and_recover treats a non-None extract_token_from_url(landing) as the definitive 'login valid' signal (Level A short-circuit), NOT the DASHBOARD_MARKERS text guess"
    - "Level B/C escalation is gated on the login-page markers (使用账号登录 / 立即注册) and/or token-absence, NOT on dashboard-text absence"
    - "_level_c_qr_login detects post-scan success by re-navigating root and checking for a fresh token, not by _is_dashboard(text)"
    - "notify() sends via the full-path hermes CLI (~/.local/bin/hermes) with `send -t telegram` (already correct — verified, unchanged)"
    - "connect_browser / ensure_browser_alive / run / main no longer thread hermes_host through for a remote SSH relaunch; the only relaunch path is local PowerShell (relaunch_edge_local)"
    - "the module still imports cleanly and all existing unit tests pass"
  artifacts:
    - path: "scripts/refresh_wechat_cookie.py"
      provides: "URL-token-gated detect_and_recover + local-only relaunch + verified Telegram notify"
      contains: "extract_token_from_url"
  key_links:
    - from: "detect_and_recover"
      to: "extract_token_from_url(landing)"
      via: "primary login-valid gate before Level A/B/C branching"
      pattern: "token\\s*=\\s*extract_token_from_url"
    - from: "ensure_browser_alive"
      to: "relaunch_edge_local"
      via: "sole relaunch path (no relaunch_edge_remote)"
      pattern: "relaunch_edge_local\\("
---

<objective>
Fix `scripts/refresh_wechat_cookie.py` per the three LOCKED decisions (empirically
validated 2026-07-14 on Hermes Edge CDP):

1. **DECISION 1** — Make `extract_token_from_url(landing)` the definitive login-valid
   signal. URL has `token=` → valid (and that token IS the credential to extract);
   URL has no `token=` (stays at `mp.weixin.qq.com/`) → expired. Deprecate the fragile
   `DASHBOARD_MARKERS` text-guessing as the primary gate; gate Level B/C on login-page
   markers + token-absence instead.
2. **DECISION 2** — Confirm `notify()` uses the local full-path hermes CLI with
   `send -t telegram` (already correct per prior session; verify + leave unchanged).
3. **DECISION 3** — Simplify relaunch to LOCAL PowerShell only (script runs on Hermes).
   Remove `relaunch_edge_remote()`, its `hermes_host` plumbing, and the SSH-relaunch
   retry branch in `connect_browser()`.

Purpose: the current script guesses login state from account-specific dashboard text
(brittle — breaks per-account) and carries dead Aliyun-runs-it remote-relaunch weight
that the locked architecture ("script runs on Hermes") no longer needs.

Output: a leaner, correct `refresh_wechat_cookie.py` that imports cleanly, keeps all
existing tests green, and whose login detection traces to the URL-token signal.

CONSTRAINT (CLAUDE.md Principle #3 — Surgical Changes): touch ONLY what these 3
decisions require. Do NOT rewrite Level A relogin-link click, Level B account-fill,
secret-redaction, CSRF rebind (STEP 2 in run()), extract_credentials, or
writeback_to_aliyun. This is ~30-50 LoC net, single file, single concern.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/wechat_refresh_final_architecture_260714.md
@C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/wechat_mp_login_expiry_page_signature.md
@scripts/refresh_wechat_cookie.py
@scripts/lib/cdp_client.py
@tests/unit/test_refresh_wechat_cookie.py

<interfaces>
<!-- Contracts already present in scripts/lib/cdp_client.py — use directly, no exploration. -->

extract_token_from_url(url: str) -> str | None
    # Returns the `token` query param of url, or None if absent.
    # This is the DECISION-1 primary signal: non-None => login valid; None => expired.

critical_cookies_present(names: list[str]) -> bool
build_cookie_string(cookies: list[dict]) -> str

CdpClient methods used here: navigate(url), current_url(), evaluate(expr),
    get_cookies(), connect(), is_alive(), close()
NoWeChatTab(RuntimeError)  # raised by connect() when no page target

<!-- Empirical page signatures (LOCKED 2026-07-14) — do NOT re-derive: -->
LOGIN VALID  : URL redirects to .../cgi-bin/home?...&token=NNNN ; extract_token_from_url != None
LOGIN EXPIRED: URL stays at https://mp.weixin.qq.com/ (no token=) ;
               body contains 使用账号登录 / 立即注册 / 微信扫一扫，选择公众平台账号登录 ;
               QR img.login__type__container__scan__qrcode already rendered in DOM
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewire detect_and_recover + _level_c_qr_login to the URL-token signal (DECISION 1)</name>
  <files>scripts/refresh_wechat_cookie.py</files>
  <action>
Make `extract_token_from_url(landing)` the definitive login-valid gate. Keep the
Level A relogin-link click, Level B account-fill, and Level C QR-capture bodies
intact — only change what DECIDES the level and what DETECTS post-recovery success.

1. Add a login-page marker constant near line 52-57 (next to DASHBOARD_MARKERS,
   ACCOUNT_LOGIN_MARKER). Add:
       LOGIN_PAGE_MARKERS = ("使用账号登录", "立即注册", "微信扫一扫")
   Keep DASHBOARD_MARKERS / _is_dashboard for backward-compat use inside Level A/B
   recovery bodies, but they are NO LONGER the primary level gate.

2. In `detect_and_recover` (line 321), reorder the decision so the URL token is
   checked FIRST:
   - Compute `landing = root_nav(client)`; `token = extract_token_from_url(landing)`;
     `text = _page_text(client)` (keep for Level A/B recovery bodies).
   - **If `token` is present AND force_level is None → already valid, return "A"
     immediately.** (URL has token = login valid = nothing to recover; the caller's
     STEP 2 CSRF rebind will re-extract a fresh token.)
   - The `force_level == "A"` testing branch: keep the existing re-nav + relogin-link
     click logic, but gate its success on `extract_token_from_url(landing)` being
     non-None (this is already how the tail of the Level A block works — keep it).
   - **Gate Level B on login-page markers, not dashboard absence.** Change the Level B
     condition from `ACCOUNT_LOGIN_MARKER in text and not _is_dashboard(text)` to:
     `force_level == "B" or (force_level is None and token is None and
     any(m in text for m in LOGIN_PAGE_MARKERS))`.
     Inside the Level B body, keep the env-cred fill unchanged; after the fill, detect
     success by re-navigating root and checking for a token (replace the
     `text = _page_text(client); if _is_dashboard(text): return "B"` success check with
     `landing = root_nav(client); if extract_token_from_url(landing): return "B"`).
   - **Level C** stays the fall-through default (true cookie death → QR).

3. In `_level_c_qr_login` (line 431), change the post-scan success detection loop
   (lines 439-450) so it detects success via a fresh token, not dashboard text:
   - Replace `text = _page_text(client); if _is_dashboard(text): return "C"` with a
     re-nav + token check: `landing = root_nav(client);
     if extract_token_from_url(landing): return "C"`.
   - Keep the `QR_EXPIRED_MARKER in text` re-capture branch — it still needs the page
     text, so read `text = _page_text(client)` for that check (you may read text once
     per loop iteration and reuse it for the QR-expired branch; the success check uses
     the token, the expired check uses text).

4. Note in a short inline comment (per the memory signature) that after login-expiry
   the QR img is already rendered, so `_ensure_scan_login_view` is a harmless no-op in
   that path — do NOT remove `_ensure_scan_login_view` (still needed when the account
   -login view is the default).

Do NOT touch: extract_credentials, writeback_to_aliyun, the STEP 2 CSRF rebind in
run(), secret-redaction, or the _js_str / _capture_qr internals.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v</automated>
  </verify>
  <done>
extract_token_from_url is the primary login-valid gate in detect_and_recover (token
present → return "A"); Level B is gated on LOGIN_PAGE_MARKERS + token-absence;
_level_c_qr_login detects success via a fresh token (re-nav + extract_token_from_url),
not _is_dashboard. All 8 existing unit tests still pass.
  </done>
</task>

<task type="auto">
  <name>Task 2: Simplify relaunch to local-only + verify Telegram notify (DECISIONS 2 & 3)</name>
  <files>scripts/refresh_wechat_cookie.py</files>
  <action>
DECISION 3 — remove the remote-SSH relaunch dead weight (script runs on Hermes; local
PowerShell relaunch is the only path):

1. DELETE `relaunch_edge_remote()` entirely (lines 180-205).

2. Simplify `ensure_browser_alive(client, endpoint_name="CDP", hermes_host="hermes-pc")`
   (lines 208-248): drop the `hermes_host` parameter and the platform-detection branch
   that chose between local vs SSH relaunch. It should be: if `client.is_alive()` return
   True; else log a warning, call `relaunch_edge_local()`, poll ~30s for `is_alive()`,
   return True on recovery or notify + return False on timeout. Keep the local-only
   behavior (no is_aliyun_context / is_hermes_context branching).

3. Simplify `connect_browser` (lines 277-318): drop the `hermes_host` param and the
   `retry_after_launch` two-attempt loop that called `relaunch_edge_remote`. Keep the
   Hermes-primary → Mac-Chrome-backup endpoint fallback (single pass over endpoints).
   If all endpoints fail, notify + raise RuntimeError as today. (Local relaunch is
   handled by ensure_browser_alive in the STEP 0-HEAL stage of run(), so connect_browser
   does NOT need its own relaunch.)

4. In `run()` (line 584): remove the `hermes_host="hermes-pc"` parameter and every
   internal `hermes_host=...` argument passed to connect_browser / ensure_browser_alive.
   Remove the `--hermes-host` argparse argument in `main()` (lines 699-700) and the
   `hermes_host=args.hermes_host` in the run() call (line 709). Keep everything else in
   run() unchanged (STEP 0 connect, STEP 0-HEAL, STEP 1 detect, STEP 2 CSRF rebind,
   STEP 3 extract, STEP 4 writeback, STEP 5 notify).

DECISION 2 — verify (do NOT change unless broken):
5. Confirm `_resolve_hermes_bin()` (line 83) returns `~/.local/bin/hermes` when it
   exists, and `notify()` (line 101) calls
   `subprocess.run([HERMES_BIN, "send", "-t", "telegram", text], ...)`. Per the locked
   decision `-t` maps to `--to` and this is ALREADY correct — leave it unchanged.
   Same for `notify_image` / `_send_photo_via_telegram_api` (already correct — KEEP).

Remove any now-orphaned imports YOUR deletions create (e.g. if `base64` is still used
by relaunch_edge_local + writeback it stays; only remove imports that become unused).
Do NOT remove pre-existing dead code unrelated to these deletions.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/refresh_wechat_cookie.py', encoding='utf-8').read()); print('SYNTAX OK')" && venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v</automated>
  </verify>
  <done>
relaunch_edge_remote deleted; ensure_browser_alive + connect_browser + run + main no
longer carry hermes_host / remote-SSH-relaunch plumbing; only relaunch path is
relaunch_edge_local. notify() confirmed to use the full-path hermes CLI with
`send -t telegram` (unchanged). Module parses; all existing unit tests pass.
  </done>
</task>

</tasks>

<verification>
Automated (runnable locally on the corp box):

1. **Syntax / import parse:**
   `venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/refresh_wechat_cookie.py', encoding='utf-8').read()); print('SYNTAX OK')"`

2. **URL-token detection wired in detect_and_recover** (grep should confirm the token
   is the gate, not dashboard text as primary):
   `grep -n "extract_token_from_url" scripts/refresh_wechat_cookie.py` — expect matches
   inside detect_and_recover AND _level_c_qr_login success detection.

3. **Telegram notify path present:**
   `grep -n "send.*-t.*telegram" scripts/refresh_wechat_cookie.py` — expect the
   notify() subprocess.run line.

4. **No remote relaunch remnants:**
   `grep -n "relaunch_edge_remote\|hermes_host\|retry_after_launch" scripts/refresh_wechat_cookie.py`
   — expect ZERO matches.

5. **Existing unit tests green:**
   `venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v` — 8/8 pass.

Manual follow-up (NOT part of this quick — the script needs a live Hermes Edge CDP +
active WeChat MP session, which cannot be exercised on the corp box):
- On Hermes: `cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --dry-run`
  and confirm level detection logs trace to the URL-token signal, and a Telegram test
  message arrives. This is a documented operator step, not a plan gate.
</verification>

<success_criteria>
- detect_and_recover uses extract_token_from_url(landing) as the definitive login-valid
  gate; Level B gated on login-page markers + token-absence; _level_c_qr_login success
  detected via fresh token (not _is_dashboard).
- relaunch_edge_remote + all hermes_host / remote-SSH-relaunch plumbing removed;
  relaunch_edge_local is the sole relaunch path.
- notify() confirmed correct (full-path hermes CLI, `send -t telegram`) — unchanged.
- `ast.parse` succeeds; grep verifications 2-4 pass; all 8 existing unit tests green.
- Net change is surgical (~30-60 LoC, single file); no unrelated refactor of Level A
  relogin-click, secret-redaction, CSRF rebind, extract, or writeback.
</success_criteria>

<output>
After completion, create
`.planning/quick/260713-sxq-refresh-wechat-cookie-py-url-token-herme/260713-sxq-SUMMARY.md`
</output>
</output>
