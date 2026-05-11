#!/usr/bin/env python3
"""
Capture WeChat MP login QR code using CDP browser cookies.

Usage:
  python capture_qr.py [--cdp-url http://localhost:9223] [--output /tmp/wx_qr.png]

Requires:
  - A Chromium/Edge browser with --remote-debugging-port=9223
  - The browser already navigated to https://mp.weixin.qq.com/
    (showing the QR login page, not dashboard)

Pitfall: Direct HTTP requests to the QR URL return 0 bytes without
browser auth cookies. This script extracts cookies via CDP first.
"""

import argparse
import base64
import json
import os
import sys
import time
import requests
from PIL import Image

CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")


def cdp_call(method: str, params: dict = None, timeout: int = 15) -> dict:
    """Call a CDP method."""
    payload = {"id": int(time.time() * 1000), "method": method}
    if params:
        payload["params"] = params

    resp = requests.post(
        f"{CDP_URL}/json/version",
        timeout=5,
    )
    resp.raise_for_status()

    # Get the actual WebSocket debugger URL for the WeChat page
    pages = requests.get(f"{CDP_URL}/json", timeout=5).json()
    target = None
    for p in pages:
        if "mp.weixin.qq.com" in p.get("url", ""):
            target = p
            break

    if not target:
        raise RuntimeError(
            "No mp.weixin.qq.com tab found. Navigate to https://mp.weixin.qq.com/ first."
        )

    ws_url = target["webSocketDebuggerUrl"]
    ws_base = ws_url.rsplit("/", 1)[0]

    # Send CDP command via HTTP (Chrome supports HTTP-based CDP endpoint too)
    cdp_http = f"http://localhost:9223{target['devtoolsFrontendUrl'].split('?')[0].replace('/devtools/inspector.html', '')}"
    # Actually, use the /devtools/page/ endpoint
    # Simpler: just use the WebSocket via websocket-client, or use the HTTP + CDP protocol

    # Fall back to using the browser_cdp Hermes tool pattern:
    # For standalone use, we use the CDP HTTP protocol
    sid = requests.put(
        f"http://{CDP_URL.split('://')[1]}/json/protocol",
        headers={"Content-Type": "application/json"},
    )
    # Chrome DevTools Protocol over HTTP is available at:
    # http://localhost:9223/devtools/page/PAGE_ID

    # Use the simpler HTTP approach
    page_id = target["id"]

    def _cdp(method, params=None):
        url = f"http://{CDP_URL.split('://')[1]}/devtools/page/{page_id}"
        body = {"method": method}
        if params:
            body["params"] = params
        r = requests.put(url, json=body, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"CDP error {r.status_code}: {r.text}")
        result = r.json()
        print(f"  CDP {method} → {json.dumps(result)[:200]}")
        return result

    return _cdp


def main():
    parser = argparse.ArgumentParser(description="Capture WeChat MP QR code via CDP")
    parser.add_argument(
        "--cdp-url", default=CDP_URL, help="CDP endpoint (default: http://localhost:9223)"
    )
    parser.add_argument(
        "--output", default="/tmp/wx_qr_code.png", help="Output PNG path"
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge"],
        default="edge",
        help="Browser type for user-agent matching",
    )
    args = parser.parse_args()

    print(f"🔍 Connecting to CDP at {args.cdp_url}...")

    try:
        cdp = cdp_call(args.cdp_url)
    except Exception as e:
        print(f"❌ CDP connection failed: {e}")
        sys.exit(1)

    # Step 1: Find QR code element
    print("📱 Looking for QR code on WeChat MP page...")
    qr_result = cdp(
        "Runtime.evaluate",
        {
            "expression": """
            (function() {
                var q = document.querySelector(
                    'img.login__type__container__scan__qrcode, ' +
                    'img[src*="qrcode"], ' +
                    'img[src*="scanlogin"]'
                );
                if (!q) return JSON.stringify({found: false});
                return JSON.stringify({
                    found: true,
                    src: q.src,
                    width: q.naturalWidth,
                    height: q.naturalHeight
                });
            })()
            """,
            "returnByValue": True,
        },
    )

    qr_data = json.loads(qr_result["result"]["result"]["value"])
    if not qr_data.get("found"):
        print("❌ No QR code found on page. Make sure the login page is visible.")
        sys.exit(1)

    qr_url = qr_data["src"]
    print(f"  QR URL: {qr_url[:80]}...")

    # Step 2: Extract cookies
    print("🍪 Extracting browser cookies...")
    cookie_result = cdp("Network.getCookies")

    cookies_list = cookie_result["result"]["cookies"]
    cookies = {}
    for c in cookies_list:
        cookies[c["name"]] = c["value"]

    print(f"  Got {len(cookies)} cookies")

    # Check critical cookies
    required = ["cert", "uuid", "wxuin", "ua_id", "mm_lang"]
    missing = [k for k in required if k not in cookies]
    if missing:
        print(f"⚠️  Missing critical cookies: {missing}")
        print("   QR download may return 0 bytes.")
    else:
        print("  ✅ All critical auth cookies present")

    # Step 3: Download QR code with cookies
    print("⬇️  Downloading QR code...")
    user_agents = {
        "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    }

    r = requests.get(
        qr_url,
        cookies=cookies,
        timeout=15,
        headers={
            "User-Agent": user_agents[args.browser],
            "Referer": "https://mp.weixin.qq.com/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )

    if len(r.content) == 0:
        print("❌ Downloaded 0 bytes — cookies may be stale or QR expired.")
        print("   Refresh the login page and retry.")
        sys.exit(1)

    print(f"  Downloaded {len(r.content)} bytes ({r.headers.get('content-type', 'unknown')})")

    # Step 4: Save as JPEG first (WeChat returns JPEG), then convert to PNG
    temp_jpg = args.output + ".tmp.jpg"
    with open(temp_jpg, "wb") as f:
        f.write(r.content)

    try:
        img = Image.open(temp_jpg)
        img = img.convert("RGB")
        img.save(args.output, "PNG")
        os.remove(temp_jpg)
        print(f"✅ QR code saved: {args.output} ({img.size[0]}x{img.size[1]})")
    except Exception as e:
        print(f"⚠️  Image conversion failed: {e}")
        print(f"   Raw JPEG saved at {temp_jpg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
