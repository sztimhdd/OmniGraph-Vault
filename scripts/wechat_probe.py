#!/usr/bin/env python3
"""wechat_probe.py — single-shot WeChat MP API probe (read-only, no retry loop).

Two probes:
  1. SESSION probe: does Cookie+token still hold a logged-in session?
     (GET mp.weixin.qq.com root; no article-list call)
  2. CAPABILITY probe: exactly ONE article-list request; print ret/err_msg.

Exit codes: 0 = session OK + list OK; 1 = session OK + list ret!=0;
            2 = session invalid; 3 = probe error.

NEVER retries — diagnosis must not become the rate limit itself.
"""
import json
import sys
import urllib.parse

import requests

sys.path.insert(0, "/root/OmniGraph-Vault")
import kol_config  # noqa: E402

API_URL = "https://mp.weixin.qq.com/cgi-bin/appmsg"
ROOT_URL = "https://mp.weixin.qq.com/"
HEADERS = {
    "Cookie": kol_config.COOKIE,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://mp.weixin.qq.com/",
}


def redact(s: str, keep: int = 6) -> str:
    return s[:keep] + "..." if s and len(s) > keep else s


def session_probe() -> int:
    """Check login state without consuming API quota."""
    try:
        r = requests.get(ROOT_URL, headers=HEADERS, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        print(f"SESSION: request-error {e}")
        return 3
    final_url = r.url
    has_token = "token=" in final_url or "token=" in r.text[:20000]
    is_login_page = "登录" in r.text[:20000] or "扫一扫" in r.text[:20000]
    print(
        f"SESSION: http={r.status_code} final_url={redact(final_url, 40)} "
        f"has_token={has_token} login_page={is_login_page}"
    )
    if r.status_code != 200 or not has_token or is_login_page:
        print("SESSION: INVALID (redirected to login / no token)")
        return 2
    print("SESSION: OK")
    return 0


def capability_probe(fakeid: str = None) -> int:
    """Exactly ONE article-list request. Print ret/err_msg (redacted)."""
    if fakeid is None:
        import sqlite3

        conn = sqlite3.connect(
            "/root/OmniGraph-Vault/data/kol_scan.db", timeout=10
        )
        row = conn.execute(
            "SELECT fakeid FROM accounts ORDER BY last_scanned_at ASC LIMIT 1"
        ).fetchone()
        conn.close()
        fakeid = str(row[0]) if row else None
    if not fakeid:
        print("CAPABILITY: no fakeid available")
        return 3

    params = {
        "token": kol_config.TOKEN,
        "fakeid": fakeid,
        "action": "list_ex",
        "type": "9",
        "count": "5",
        "begin": "0",
        "f": "json",
        "ajax": "1",
    }
    try:
        r = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"CAPABILITY: request-error {e}")
        return 3
    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"CAPABILITY: non-JSON http={r.status_code} body={redact(r.text[:120])}")
        return 3
    base = data.get("base_resp", {})
    ret = base.get("ret")
    err = base.get("err_msg", "")
    n = len(data.get("app_msg_list", []))
    print(f"CAPABILITY: http={r.status_code} ret={ret} err_msg={redact(str(err))} items={n}")
    if ret == 0:
        print("CAPABILITY: OK")
        return 0
    print(f"CAPABILITY: FAIL ret={ret}")
    return 1


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    sess_rc = 0
    if mode in ("both", "session"):
        sess_rc = session_probe()
    cap_rc = 0
    if mode in ("both", "capability"):
        cap_rc = capability_probe()
    if mode == "both":
        print(f"RESULT: session={sess_rc} capability={cap_rc}")
        if sess_rc == 2:
            sys.exit(2)  # session invalid → Level B/C recovery
        if cap_rc != 0:
            sys.exit(1)  # session OK but list limited → interface-level
        sys.exit(0)
    sys.exit(sess_rc if mode == "session" else cap_rc)


if __name__ == "__main__":
    main()
