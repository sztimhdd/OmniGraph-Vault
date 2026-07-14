#!/usr/bin/env python3
"""Hermes-side self-healing WeChat-cookie refresh orchestrator.

Runs on Hermes with system python3 + websocket-client (NOT the project venv).
Connects directly to the headed Edge CDP on localhost:9222, detects which of
three failure levels applies (A token/page stale, B account-login, C true
cookie death), recovers the session, extracts a fresh TOKEN + cookie string,
writes it back to Aliyun's kol_config.py atomically with a single-account
test-scan verify, and notifies via Telegram (hermes send) on the C-level human
request and on the final success/failure summary.

This is the active executor of the locked option-A chain: Aliyun detects +
hands off (Plan 03); ALL browser/CDP/Telegram work lives here on Hermes.

A/B/C decision-tree logic, selectors, poll cadence, CSRF rebind, and
secret-redaction discipline are the scriptified form of
skills/omnigraph_scan_kol/SKILL.md — do NOT reinvent.

Invoked on Hermes as:  cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py
"""
import argparse
import base64
import logging
import os
import shutil
import subprocess
import sys
import time

# IMPORT PATH (INFO 7): pin the script's own dir at the front of sys.path so the
# sibling `lib/cdp_client.py` resolves whether invoked as
# `python3 scripts/refresh_wechat_cookie.py` from the repo root OR
# `python3 refresh_wechat_cookie.py` from inside scripts/. Do NOT use
# `from scripts.lib...` (no guaranteed __init__.py; breaks from-repo-root cwd).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.cdp_client import (  # noqa: E402
    CdpClient,
    NoWeChatTab,
    build_cookie_string,
    extract_token_from_url,
    critical_cookies_present,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("refresh_wechat_cookie")

# --- Constants ---------------------------------------------------------------
DASHBOARD_MARKERS = ("AI老兵日记", "原创", "新的创作")
RELOGIN_MARKER = "请重新登录"
ACCOUNT_LOGIN_MARKER = "使用账号登录"
# DECISION 1: primary login-expired signal (gates Level B) — extract_token_from_url
# being None is the definitive expiry signal; these markers corroborate it.
LOGIN_PAGE_MARKERS = ("使用账号登录", "立即注册", "微信扫一扫")
QR_EXPIRED_MARKER = "二维码已过期"
QR_SELECTOR = "img.login__type__container__scan__qrcode"
QR_PNG_PATH = "/tmp/wx_qr_code.png"

# Aliyun ssh target. Default to the alias `vitaclaw-aliyun` (Plan 04 repoints it
# to 47.117.244.253); --aliyun-ssh overrides for explicit root@IP testing.
ALIYUN_SSH = "vitaclaw-aliyun"
ALIYUN_REPO = "/root/OmniGraph-Vault"
ALIYUN_VENV_PY = "venv-aim1/bin/python"

# CDP connection targets (fallback chain: Hermes primary → Mac Chrome backup).
# HERMES_CDP_URL: Hermes PC Edge CDP (ohca.ddns.net:9222 or localhost:9222 if ssh-tunneled).
# MAC_CDP_URL: Mac Chrome local fallback (localhost:9222 — only used if Hermes unreachable).
HERMES_CDP_URL = os.environ.get("HERMES_CDP_URL", "http://localhost:9222")
MAC_CDP_URL = "http://localhost:9222"  # Mac is local-only fallback

# WSL→Windows PowerShell interop relaunch (RESEARCH.md Test 2, live-confirmed).
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EDGE_PROFILE = r"C:\Edge-Auto-Profile"

# Hex of "***" — the terminal-redaction trap (SKILL.md Step 3 / Step 4).
REDACTED_HEX = "373937343438373930"  # see SKILL.md hex-verify guard


# --- Telegram notify ----------------------------------------------------------


def _resolve_hermes_bin():
    """Resolve the `hermes` CLI path.

    The wrapper is launched non-interactively (ssh hermes "nohup python3 ..."),
    where ~/.local/bin is NOT on PATH, so a bare `hermes` lookup fails even
    though it works in an interactive login shell. Prefer the known install
    location, then fall back to PATH resolution.
    """
    candidate = os.path.expanduser("~/.local/bin/hermes")
    if os.path.exists(candidate):
        return candidate
    found = shutil.which("hermes")
    return found or "hermes"  # last resort: bare name (will FileNotFoundError if absent)


HERMES_BIN = _resolve_hermes_bin()


def notify(text):
    """Send a one-line Telegram summary/warning via `hermes send`."""
    try:
        subprocess.run([HERMES_BIN, "send", "-t", "telegram", text], check=False)
    except FileNotFoundError:
        logger.warning("hermes CLI not found; would have sent: %s", text)


def _send_photo_via_telegram_api(png_path, caption):
    """Deliver an image to Telegram via the Bot API sendPhoto endpoint.

    `hermes send` is text-only (no --image/--photo flag — verified on the live
    Hermes build), so a QR png path in a text message is useless to the user on
    their phone. The Bot API sendPhoto endpoint uploads the actual image. Reads
    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from the environment (already set in
    ~/.hermes/.env). multipart/form-data: data={chat_id, caption}, files={photo}.
    Returns True on ok, False otherwise.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not in env; cannot sendPhoto")
        return False
    try:
        import requests  # lazy import — only needed for the level-C QR path
        with open(png_path, "rb") as fh:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": fh},
                timeout=20,
            )
        ok = bool(resp.ok and resp.json().get("ok"))
        if not ok:
            logger.warning("Telegram sendPhoto failed: HTTP %s %s", resp.status_code, resp.text[:200])
        return ok
    except Exception as exc:  # network / json / file error — fall back to text
        logger.warning("Telegram sendPhoto error: %s", exc)
        return False


def notify_image(png_path, caption):
    """Deliver a QR png to Telegram so the user can scan it from their phone.

    Primary: Telegram Bot API sendPhoto (uploads the real image — the only path
    that actually puts a scannable QR on the user's device). Fallback: a text
    notify carrying the path (operator-on-Hermes can open it) — used only if
    sendPhoto fails (missing token, network error). The earlier `hermes send
    --image` approach was a dead end: the CLI has no image flag.
    """
    if _send_photo_via_telegram_api(png_path, caption):
        return
    logger.warning("sendPhoto unavailable; sending text + path as fallback")
    notify(f"{caption} — QR saved at {png_path}")


# --- Self-heal: relaunch headed Edge if :9222 is down (KCA-6) -----------------

def relaunch_edge_local():
    """Relaunch headed Edge via WSL→Windows PowerShell interop (Hermes only).

    Uses the absolute powershell.exe path and a base64 -EncodedCommand
    (UTF-16LE) to avoid SSH/quoting pain (RESEARCH.md Test 2).
    """
    ps = (
        'Start-Process "{exe}" -ArgumentList '
        '"--remote-debugging-port=9222",'
        '"--remote-debugging-address=127.0.0.1",'
        '"--remote-allow-origins=*",'
        '"--user-data-dir={profile}",'
        '"--no-sandbox"'
    ).format(exe=EDGE_EXE, profile=EDGE_PROFILE)
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        [POWERSHELL, "-NoProfile", "-EncodedCommand", encoded],
        check=False,
    )


def ensure_browser_alive(client, endpoint_name="CDP"):
    """STEP 0 self-heal: if the endpoint is down, relaunch Edge and poll ~30s.

    DECISION 3 (locked 2026-07-14): the script runs ON Hermes, so local
    PowerShell relaunch is the only relaunch path — no remote-SSH branch.

    Returns True if alive (eventually), False if relaunch failed.
    """
    if client.is_alive():
        return True

    logger.warning("%s down — relaunching headed Edge via local PowerShell", endpoint_name)
    relaunch_edge_local()

    # Poll for up to 30s
    for attempt in range(30):
        time.sleep(1)
        if client.is_alive():
            logger.info("%s back up after relaunch (attempt %d)", endpoint_name, attempt + 1)
            return True

    notify(f"⚠️ {endpoint_name} relaunch failed or timeout")
    return False


# --- Level detection + recovery ----------------------------------------------

def _page_text(client):
    """First 500 chars of body.innerText (returnByValue avoids `***` trap)."""
    try:
        return client.evaluate("document.body.innerText.substring(0,500)") or ""
    except Exception as exc:  # noqa: BLE001 — DOM read is best-effort
        logger.warning("page-text read failed: %s", exc)
        return ""


def _is_dashboard(text):
    return any(m in text for m in DASHBOARD_MARKERS)


def root_nav(client, wait=3.0):
    """Navigate to root, wait for redirect, return the landing URL.

    Token MUST come from the landing URL after root-nav, NEVER the drifted
    current tab (RESEARCH.md gotcha). This is the root-nav used at level-detect.
    """
    client.navigate("https://mp.weixin.qq.com/")
    time.sleep(wait)
    return client.current_url()


def connect_browser(hermes_first=True, hermes_host="hermes-pc", retry_after_launch=True):
    """Connect to browser via fallback chain: Hermes primary → Mac Chrome backup.

    Returns (CdpClient, str) — the client + endpoint name ("Hermes Edge" or "Mac Chrome").
    Raises RuntimeError if all endpoints are unreachable.

    If retry_after_launch=True and all endpoints fail, attempts to SSH to Hermes
    and launch Edge, then retries once.
    """
    endpoints = []
    if hermes_first:
        endpoints = [
            (HERMES_CDP_URL, "Hermes Edge"),
            (MAC_CDP_URL, "Mac Chrome"),
        ]
    else:
        endpoints = [(MAC_CDP_URL, "Mac Chrome"), (HERMES_CDP_URL, "Hermes Edge")]

    for attempt in (1, 2):  # Try once, then again after relaunch if enabled
        for endpoint_url, endpoint_name in endpoints:
            logger.info("[Attempt %d] Trying %s at %s", attempt, endpoint_name, endpoint_url)
            try:
                client = CdpClient(base_url=endpoint_url)
                client.connect()
                logger.info("Connected to %s", endpoint_name)
                return client, endpoint_name
            except Exception as exc:  # noqa: BLE001 — all errors are fallback-worthy
                logger.warning("%s connection failed: %s", endpoint_name, exc)
                continue

        # After first attempt, if all failed and retry enabled: try launching Edge remotely
        if attempt == 1 and retry_after_launch:
            logger.warning("All endpoints failed on attempt 1; attempting remote Edge launch on %s", hermes_host)
            relaunch_edge_remote(hermes_host)
            time.sleep(5)  # Wait for Edge to boot
            continue

    # All attempts exhausted
    msg = f"All browser endpoints unreachable: {', '.join(e[1] for e in endpoints)}"
    logger.error(msg)
    notify(f"🔴 WeChat refresh FAILED: {msg}")
    raise RuntimeError(msg)


def detect_and_recover(client, force_level=None):
    """Detect the failure level and recover the session.

    Returns the level string ("A"/"B"/"C") that was handled, or raises on a
    needs-human timeout (caller maps to exit 2). After recovery the caller
    re-navigates root (STEP 2) to rebind the CSRF token before extract.

    DECISION 1 (locked 2026-07-14): extract_token_from_url(landing) is the
    definitive login-valid signal — URL carries token= => valid; no token=
    (stays at mp.weixin.qq.com/) => expired. DASHBOARD_MARKERS text-guessing
    is kept only as a corroborating signal inside recovery bodies, not as the
    primary gate.
    """
    landing = root_nav(client)
    text = _page_text(client)
    token = extract_token_from_url(landing)

    # --- Already valid: URL carries a token, nothing to recover --------------
    if force_level is None and token:
        logger.info("Login valid: landing URL carries token=; nothing to recover")
        return "A"

    # --- Level A: dashboard present, token stale/missing ---------------------
    if force_level == "A" or (force_level is None and _is_dashboard(text)):
        logger.info("Level A: dashboard present; re-nav root for fresh token")
        if RELOGIN_MARKER in text:
            # "请重新登录" → click the login link, re-check (SKILL.md step 4).
            try:
                client.evaluate("document.querySelector('a, .login').click()")
            except Exception as exc:  # noqa: BLE001
                logger.warning("login-link click failed: %s", exc)
            time.sleep(3)
        landing = root_nav(client)
        token = extract_token_from_url(landing)
        if token:
            return "A"
        logger.info("Level A re-nav produced no token; escalating")

    # --- Level B: account-login landing --------------------------------------
    # Gated on login-page markers + token-absence (not dashboard-absence).
    if force_level == "B" or (
        force_level is None and token is None and any(m in text for m in LOGIN_PAGE_MARKERS)
    ):
        logger.info("Level B: account-login landing; filling env creds")
        account = os.environ.get("WECHAT_MP_ACCOUNT")
        password = os.environ.get("WECHAT_MP_PASSWORD")
        if not account or not password:
            logger.error("WECHAT_MP_ACCOUNT / WECHAT_MP_PASSWORD not in env")
        else:
            try:
                client.evaluate(
                    "document.querySelector('.login__type__container__account, a').click()"
                )
                time.sleep(1)
                # Fill the SPA login form (values from env — NEVER hardcoded).
                client.evaluate(
                    "(function(c,p){var f=document.querySelectorAll("
                    "'.login__type__container__account input');"
                    "if(f.length>=2){f[0].value=c;f[1].value=p;}})("
                    + _js_str(account) + "," + _js_str(password) + ")"
                )
                client.evaluate("document.querySelector('.btn_login').click()")
            except Exception as exc:  # noqa: BLE001
                logger.warning("account-login fill/click failed: %s", exc)
            time.sleep(5)
            landing = root_nav(client)
            if extract_token_from_url(landing):
                return "B"
        # Linked-account security-page pitfall → do NOT retry, fall to Level C.
        logger.info("Level B did not produce a fresh token; falling through to Level C")

    # --- Level C: true cookie death (QR scan) --------------------------------
    logger.info("Level C: capturing QR for human scan")
    return _level_c_qr_login(client)


def _js_str(value):
    """JSON-encode a string for safe embedding in an evaluate() expression."""
    import json
    return json.dumps(value)


def _ensure_scan_login_view(client):
    """Click the 扫码登录 (scan-login) tab so the QR <img> renders.

    WeChat's login landing defaults to the ACCOUNT-login view (使用账号登录), where
    the scan QR element does not exist yet. Live testing showed _capture_qr bailing
    with 'QR element not found' for exactly this reason. Clicking the 扫码登录 tab
    first switches to the scan view and renders QR_SELECTOR. No-op if already on it.
    """
    client.evaluate(
        "(function(){var els=Array.from(document.querySelectorAll('a,div,span,li,button'));"
        "var t=els.find(function(e){return e.textContent.trim()==='扫码登录';});"
        "if(t){t.click();return 'clicked';}return 'no_scan_tab';})()"
    )
    time.sleep(2)


def _capture_qr(client):
    """Capture the QR via canvas toDataURL, save to QR_PNG_PATH. True on success."""
    # WeChat defaults to account-login; switch to the scan view so the QR renders.
    _ensure_scan_login_view(client)
    exists = client.evaluate(
        "document.querySelector('" + QR_SELECTOR + "') ? 'found' : 'not_found'"
    )
    if exists != "found":
        return False
    data_url = client.evaluate(
        "(async function(){var q=document.querySelector('" + QR_SELECTOR + "');"
        "if(!q) return 'no_element';"
        "var c=document.createElement('canvas');c.width=q.naturalWidth;"
        "c.height=q.naturalHeight;var ctx=c.getContext('2d');ctx.drawImage(q,0,0);"
        "return c.toDataURL('image/png');})()"
    )
    if not data_url or not data_url.startswith("data:image"):
        return False
    b64 = data_url.split(",", 1)[1]
    with open(QR_PNG_PATH, "wb") as fh:
        fh.write(base64.b64decode(b64))
    return True


def _level_c_qr_login(client):
    """Capture QR → Telegram → poll ~5min for a fresh token. Raises on timeout.

    NOTE (memory wechat_mp_login_expiry_page_signature): after login-expiry the
    QR img is already rendered in the DOM, so _ensure_scan_login_view (called by
    _capture_qr) is a harmless no-op in that path — it is still needed when the
    account-login view is the default landing state.
    """
    refreshes = 0
    if not _capture_qr(client):
        notify("⚠️ WeChat MP 登录页面异常，无法捕获二维码")
        raise TimeoutError("QR element not found")
    notify_image(QR_PNG_PATH, "请扫码登录 WeChat 公众号以刷新 KOL 扫描凭证")

    for _ in range(30):  # 30 × 10s = 5 min
        time.sleep(10)
        # DECISION 1: success is a fresh token from a root re-nav, not dashboard text.
        landing = root_nav(client)
        if extract_token_from_url(landing):
            return "C"
        text = _page_text(client)
        if QR_EXPIRED_MARKER in text and refreshes < 2:
            refreshes += 1
            root_nav(client)
            if _capture_qr(client):
                if refreshes == 2:
                    notify("⚠️ 二维码再次过期，请尽快扫码")
                notify_image(QR_PNG_PATH, "二维码已刷新，请扫码")
    notify("⏰ 扫码超时（5分钟），请稍后手动触发 scan KOL")
    raise TimeoutError("QR scan timed out after 5 minutes")


# --- Extract (STEP 3) ---------------------------------------------------------

def extract_credentials(client, token):
    """Get cookies, assert all 5 critical present, build the cookie string.

    Logs only lengths + first 6 chars for diagnostics (secret-redaction
    discipline — never print full secret values)."""
    cookies = client.get_cookies()
    names = [c["name"] for c in cookies]
    if not critical_cookies_present(names):
        missing = [c for c in ("slave_sid", "data_ticket", "rand_info", "bizuin",
                               "slave_user") if c not in names]
        raise RuntimeError(f"critical cookies missing: {missing}")
    cookie_str = build_cookie_string(cookies)
    logger.info(
        "extracted token len=%d (%s…), cookie len=%d",
        len(token), token[:6], len(cookie_str),
    )
    return cookie_str


# --- Writeback to Aliyun (KCA-4): atomic .tmp+rename + verify + rollback -----

def _default_run_ssh(command):
    """Real ssh executor: run `ssh {ALIYUN_SSH} <command>` and return the result."""
    return subprocess.run(
        ["ssh", ALIYUN_SSH, command],
        capture_output=True, text=True, check=False,
    )


def writeback_to_aliyun(token, cookie_str, test_account, dry_run, *, run_ssh=None):
    """Push refreshed creds to Aliyun kol_config.py atomically, then verify.

    Atomic write (.tmp + os.replace) preserving FAKEIDS, verify via a single
    account test scan (ret=0 gate), rollback to kol_config.py.bak-pre-refresh on
    a bad-creds verify result. The ssh executor is INJECTABLE (`run_ssh`) so the
    verify + rollback branches are unit-testable without a live Aliyun.

    Returns True on success (verify scan ret=0), False on failure (and rolls
    back). The three non-negotiables: atomic write, verify-before-success,
    rollback on bad creds (CONTEXT Hop ④: do NOT half-write prod kol_config.py).
    """
    if run_ssh is None:
        run_ssh = _default_run_ssh

    cfg = f"{ALIYUN_REPO}/kol_config.py"
    bak = f"{cfg}.bak-pre-refresh"
    tmp = f"{cfg}.tmp"

    # Pass token + cookie base64-encoded to dodge shell-escaping ; + = / in the
    # cookie string (decoded inside the remote python one-liner).
    tok_b64 = base64.b64encode(token.encode("utf-8")).decode("ascii")
    cookie_b64 = base64.b64encode(cookie_str.encode("utf-8")).decode("ascii")

    if dry_run:
        logger.info(
            "dry-run writeback: TOKEN=%s… cookie_len=%d → would atomic-write %s",
            token[:6], len(cookie_str), cfg,
        )
        return True

    # Remote atomic edit: backup → replace TOKEN/COOKIE lines → .tmp → os.replace.
    # Preserves FAKEIDS (only the two assignment lines are rewritten).
    remote_write = (
        "python3 - <<'PYEOF'\n"
        "import base64, os, re, shutil\n"
        f"cfg = {cfg!r}\n"
        f"bak = {bak!r}\n"
        f"tmp = {tmp!r}\n"
        f"tok = base64.b64decode('{tok_b64}').decode('utf-8')\n"
        f"cookie = base64.b64decode('{cookie_b64}').decode('utf-8')\n"
        "shutil.copy2(cfg, bak)\n"
        "src = open(cfg, encoding='utf-8').read()\n"
        "src = re.sub(r'(?m)^TOKEN\\s*=.*$', 'TOKEN = \"%s\"' % tok, src, count=1)\n"
        "src = re.sub(r'(?m)^COOKIE\\s*=.*$', 'COOKIE = \"%s\"' % cookie, src, count=1)\n"
        "open(tmp, 'w', encoding='utf-8').write(src)\n"
        "os.replace(tmp, cfg)\n"
        "print('WRITE_OK')\n"
        "PYEOF"
    )
    res = run_ssh(remote_write)
    if getattr(res, "returncode", 1) != 0:
        logger.error("remote atomic write failed: %s", getattr(res, "stderr", ""))
        _rollback(run_ssh, cfg, bak)
        return False

    # Hex-verify guard (SKILL.md trap): the remote TOKEN must NOT hex-decode to
    # "***" (373937343438373930) — guards the terminal-redaction-wrote-stars bug.
    guard = (
        "python3 -c \"import sys;"
        f"d=open({cfg!r},'rb').read();i=d.find(b'TOKEN=');"
        f"sys.exit(1 if bytes.fromhex('{REDACTED_HEX}') in d[i:i+40] else 0)\""
    )
    gres = run_ssh(guard)
    if getattr(gres, "returncode", 1) != 0:
        logger.error("hex-verify guard tripped: TOKEN looks redacted (***)")
        _rollback(run_ssh, cfg, bak)
        return False

    # VERIFY (KCA-4): single-account test scan. ret=0 → valid; nonzero or
    # WECHAT_SESSION_INVALID / ret=200003 in stderr → bad creds → rollback.
    verify = (
        f"cd {ALIYUN_REPO} && {ALIYUN_VENV_PY} "
        f"batch_scan_kol.py --account {test_account} --max-articles 1"
    )
    vres = run_ssh(verify)
    rc = getattr(vres, "returncode", 1)
    stderr = getattr(vres, "stderr", "") or ""
    if rc != 0 or "WECHAT_SESSION_INVALID" in stderr or "ret=200003" in stderr:
        logger.error("verify test-scan failed (rc=%s); rolling back", rc)
        _rollback(run_ssh, cfg, bak)
        return False

    logger.info("verify test-scan ret=0; writeback success")
    return True


def _rollback(run_ssh, cfg, bak):
    """Restore kol_config.py from its .bak-pre-refresh copy (atomic os.replace)."""
    restore = (
        f"python3 -c \"import os; os.replace({bak!r}, {cfg!r})\""
    )
    run_ssh(restore)
    logger.info("rolled back %s from %s", cfg, bak)


# --- Main flow ----------------------------------------------------------------

def run(cdp_url, force_level, dry_run, test_account, aliyun_ssh):
    global ALIYUN_SSH
    if aliyun_ssh:
        ALIYUN_SSH = aliyun_ssh

    # STEP 0 — CONNECT via fallback chain (Hermes primary → Mac Chrome backup)
    try:
        # Allow override via --cdp-url for testing; otherwise use fallback chain
        if cdp_url != "http://localhost:9222":
            # Explicit URL provided — use it directly
            client = CdpClient(base_url=cdp_url)
            client_name = "CDP (explicit)"
        else:
            # Default: use fallback chain (with auto-relaunch if on Aliyun)
            client, client_name = connect_browser(hermes_first=True, hermes_host=hermes_host)
    except RuntimeError as exc:
        logger.error("all browser endpoints exhausted: %s", exc)
        return 1

    logger.info("connected to %s", client_name)

    # STEP 0-HEAL — SELF-HEAL (KCA-6)
    if not ensure_browser_alive(client, endpoint_name=client_name):
        return 1

    # STEP 1 — CONNECT + LEVEL DETECT
    try:
        client.connect()
    except NoWeChatTab as exc:
        logger.error("connect failed: %s", exc)
        # No page target — relaunch and try once more (only if Hermes).
        if "Edge" in client_name:
            if not ensure_browser_alive(client, endpoint_name=client_name):
                return 1
            client.connect()
        else:
            # Mac fallback — no auto-relaunch
            notify(f"❌ WeChat tab not found on {client_name}; manual intervention needed")
            return 1

    try:
        level = detect_and_recover(client, force_level=force_level)
    except TimeoutError as exc:
        logger.error("needs-human: %s", exc)
        return 2

    # STEP 2 — CSRF REBIND (KCA-2): navigate root AGAIN to bind a fresh token to
    # the new session (SKILL.md ret=200040 note). The post-login token is not
    # yet bound; this second root-nav rebinds it. Token comes from the landing
    # URL only, never the drifted current tab (RESEARCH.md gotcha).
    client.navigate("https://mp.weixin.qq.com/")
    time.sleep(3.0)
    landing = client.current_url()
    token = extract_token_from_url(landing)
    if not token:
        logger.error("CSRF rebind produced no token from landing URL")
        notify("❌ refresh failed: no token after CSRF rebind")
        return 1

    # STEP 3 — EXTRACT
    try:
        cookie_str = extract_credentials(client, token)
    except RuntimeError as exc:
        logger.error("extract failed: %s", exc)
        notify(f"❌ refresh failed: {exc}")
        return 1
    finally:
        client.close()

    # STEP 4 — WRITEBACK (KCA-4)
    ok = writeback_to_aliyun(
        token=token,
        cookie_str=cookie_str,
        test_account=test_account,
        dry_run=dry_run,
    )

    # STEP 5 — NOTIFY (KCA-5) + SESSION EXPIRY DETECTION
    if dry_run:
        logger.info("dry-run: skipped writeback notify")
        return 0

    if ok:
        notify(f"✅ KOL cookie refreshed (level {level}); Aliyun test-scan ret=0")
        # SUCCESS: new creds are valid. Session will expire in ~14-31 days.
        # Operator will see the next ret=200003 from the daily-scan cron,
        # which will trigger this refresh script again.
        return 0

    # WRITEBACK FAILED — test-scan produced ret=200003 or other error
    notify("❌ refresh failed: Aliyun test-scan did not pass (rolled back)")

    # DIAGNOSTIC: if verify scan returned ret=200003 specifically, log it as a signal
    # that the session is already expired BEFORE refresh attempt — likely a case where
    # the refresh script is too late or the browser session was already stale.
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Refresh WeChat KOL cookie on Hermes (fallback chain: Hermes primary → Mac Chrome backup)"
    )
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        help="CDP endpoint for explicit targeting; if localhost:9222 (default), uses fallback chain",
    )
    parser.add_argument("--level", choices=["A", "B", "C"], default=None,
                        help="Force a failure level (testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do everything except STEP 4 writeback")
    parser.add_argument("--test-account", default="叶小钗",
                        help="Account for the single-account verify scan")
    parser.add_argument("--aliyun-ssh", default=None,
                        help="Override the Aliyun ssh target (alias or root@IP)")
    args = parser.parse_args()

    sys.exit(run(
        cdp_url=args.cdp_url,
        force_level=args.level,
        dry_run=args.dry_run,
        test_account=args.test_account,
        aliyun_ssh=args.aliyun_ssh,
    ))


if __name__ == "__main__":
    main()
