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
QR_EXPIRED_MARKER = "二维码已过期"
QR_SELECTOR = "img.login__type__container__scan__qrcode"
QR_PNG_PATH = "/tmp/wx_qr_code.png"

# Aliyun ssh target. Default to the alias `vitaclaw-aliyun` (Plan 04 repoints it
# to 47.117.244.253); --aliyun-ssh overrides for explicit root@IP testing.
ALIYUN_SSH = "vitaclaw-aliyun"
ALIYUN_REPO = "/root/OmniGraph-Vault"
ALIYUN_VENV_PY = "venv-aim1/bin/python"

# WSL→Windows PowerShell interop relaunch (RESEARCH.md Test 2, live-confirmed).
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EDGE_PROFILE = r"C:\Edge-Auto-Profile"

# Hex of "***" — the terminal-redaction trap (SKILL.md Step 3 / Step 4).
REDACTED_HEX = "373937343438373930"  # see SKILL.md hex-verify guard


# --- Telegram notify (capability-gated for image — WARNING 3) ----------------

_HERMES_IMAGE_SUPPORTED = None  # one-time cache of `hermes send --help` probe


def notify(text):
    """Send a one-line Telegram summary/warning via `hermes send`."""
    try:
        subprocess.run(["hermes", "send", "-t", "telegram", text], check=False)
    except FileNotFoundError:
        logger.warning("hermes CLI not found; would have sent: %s", text)


def _hermes_supports_image():
    """One-time probe of `hermes send --help` for an `--image` flag."""
    global _HERMES_IMAGE_SUPPORTED
    if _HERMES_IMAGE_SUPPORTED is not None:
        return _HERMES_IMAGE_SUPPORTED
    try:
        out = subprocess.run(
            ["hermes", "send", "--help"],
            capture_output=True, text=True, check=False,
        )
        _HERMES_IMAGE_SUPPORTED = "--image" in (out.stdout + out.stderr)
    except FileNotFoundError:
        _HERMES_IMAGE_SUPPORTED = False
    return _HERMES_IMAGE_SUPPORTED


def notify_image(png_path, caption):
    """Send a QR png to Telegram if `hermes send --image` is supported.

    Capability-gated (WARNING 3): if `--image` is NOT supported on this Hermes
    build, fall back to a text notify carrying the caption + png path so the
    operator can open it. Plan 05 asserts the SAME gate: "image delivered if
    --image supported, else QR png at /tmp + path sent as text." Do NOT block
    the wrapper on the unverified flag.
    """
    if _hermes_supports_image():
        subprocess.run(
            ["hermes", "send", "-t", "telegram", "--image", png_path, caption],
            check=False,
        )
    else:
        logger.warning("hermes send --image unsupported; sending text + path")
        notify(f"{caption} — QR saved at {png_path}")


# --- Self-heal: relaunch headed Edge if :9222 is down (KCA-6) -----------------

def relaunch_edge():
    """Relaunch headed Edge via WSL→Windows PowerShell interop.

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


def ensure_browser_alive(client):
    """STEP 0 self-heal: if :9222 is down, relaunch Edge and poll ~30s.

    Returns True if alive (eventually), False if relaunch failed.
    """
    if client.is_alive():
        return True
    logger.warning("CDP :9222 down — relaunching headed Edge via PowerShell")
    relaunch_edge()
    for _ in range(30):  # ~30s, 1s interval
        time.sleep(1)
        if client.is_alive():
            logger.info("CDP :9222 back up after relaunch")
            return True
    notify("⚠️ Edge CDP :9222 relaunch failed")
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


def detect_and_recover(client, force_level=None):
    """Detect the failure level and recover the session.

    Returns the level string ("A"/"B"/"C") that was handled, or raises on a
    needs-human timeout (caller maps to exit 2). After recovery the caller
    re-navigates root (STEP 2) to rebind the CSRF token before extract.
    """
    landing = root_nav(client)
    text = _page_text(client)
    token = extract_token_from_url(landing)

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
    if force_level == "B" or (
        force_level is None and ACCOUNT_LOGIN_MARKER in text and not _is_dashboard(text)
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
            text = _page_text(client)
            if _is_dashboard(text):
                return "B"
        # Linked-account security-page pitfall → do NOT retry, fall to Level C.
        logger.info("Level B did not reach dashboard; falling through to Level C")

    # --- Level C: true cookie death (QR scan) --------------------------------
    logger.info("Level C: capturing QR for human scan")
    return _level_c_qr_login(client)


def _js_str(value):
    """JSON-encode a string for safe embedding in an evaluate() expression."""
    import json
    return json.dumps(value)


def _capture_qr(client):
    """Capture the QR via canvas toDataURL, save to QR_PNG_PATH. True on success."""
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
    """Capture QR → Telegram → poll ~5min for dashboard. Raises on timeout."""
    refreshes = 0
    if not _capture_qr(client):
        notify("⚠️ WeChat MP 登录页面异常，无法捕获二维码")
        raise TimeoutError("QR element not found")
    notify_image(QR_PNG_PATH, "请扫码登录 WeChat 公众号以刷新 KOL 扫描凭证")

    for _ in range(30):  # 30 × 10s = 5 min
        time.sleep(10)
        text = _page_text(client)
        if _is_dashboard(text):
            return "C"
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


# --- writeback_to_aliyun is implemented in Task 3 (same file) ----------------


# --- Main flow ----------------------------------------------------------------

def run(cdp_url, force_level, dry_run, test_account, aliyun_ssh):
    global ALIYUN_SSH
    if aliyun_ssh:
        ALIYUN_SSH = aliyun_ssh

    client = CdpClient(base_url=cdp_url)

    # STEP 0 — SELF-HEAL (KCA-6)
    if not ensure_browser_alive(client):
        return 1

    # STEP 1 — CONNECT + LEVEL DETECT
    try:
        client.connect()
    except NoWeChatTab as exc:
        logger.error("connect failed: %s", exc)
        # No page target — relaunch and try once more.
        if not ensure_browser_alive(client):
            return 1
        client.connect()

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

    # STEP 5 — NOTIFY (KCA-5)
    if dry_run:
        logger.info("dry-run: skipped writeback notify")
        return 0
    if ok:
        notify(f"✅ KOL cookie refreshed (level {level}); Aliyun test-scan ret=0")
        return 0
    notify("❌ refresh failed: Aliyun test-scan did not pass (rolled back)")
    return 1


def main():
    parser = argparse.ArgumentParser(description="Refresh WeChat KOL cookie on Hermes")
    parser.add_argument("--cdp-url", default="http://localhost:9222",
                        help="CDP endpoint (default: http://localhost:9222)")
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
