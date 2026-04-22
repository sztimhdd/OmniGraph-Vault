"""
test_mcp.py — Standalone test for MCP Playwright server interaction.

Usage:
    python test_mcp.py                          # default: http://ohca.ddns.net:58931/mcp
    python test_mcp.py http://localhost:8931/mcp # custom endpoint
"""
import sys
import json
import time
import re
import requests

sys.stdout.reconfigure(encoding='utf-8')

MCP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://ohca.ddns.net:58931/mcp"
WECHAT_URL = "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"

session_id = None
msg_id = 0


def call(method, params=None, timeout=120):
    global session_id, msg_id
    msg_id += 1
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        payload["params"] = params

    resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=timeout)
    resp.encoding = "utf-8"

    if "mcp-session-id" in resp.headers:
        session_id = resp.headers["mcp-session-id"]

    if resp.status_code != 200:
        print(f"  [{method}] HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    result = None
    for m in re.finditer(r'data: ({.+})', resp.text, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            if "result" in obj:
                result = obj["result"]
            if "error" in obj:
                print(f"  [{method}] ERROR: {obj['error']}")
        except json.JSONDecodeError:
            pass
    return result


def notify(method):
    global session_id
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    payload = {"jsonrpc": "2.0", "method": method}
    requests.post(MCP_URL, json=payload, headers=headers, timeout=10)


def tool(name, arguments=None):
    params = {"name": name}
    if arguments:
        params["arguments"] = arguments
    return call("tools/call", params)


def text(r):
    if not r or "content" not in r:
        return ""
    return "".join(c["text"] for c in r["content"] if c.get("type") == "text")


def extract_eval(t):
    if "### Result\n" in t:
        return t.split("### Result\n")[1].split("\n### Ran")[0].strip()
    return t


print("=" * 60)
print(f"MCP Test: {MCP_URL}")
print("=" * 60)

# --- Init ---
print("\n[1] Initialize...")
r = call("initialize", {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "omnigraph-test", "version": "1.0"},
})
if not r:
    print("FAILED: Could not initialize")
    sys.exit(1)
server = r.get("serverInfo", {})
print(f"  Server: {server.get('name')} v{server.get('version')}")
notify("notifications/initialized")
print(f"  Session: {session_id}")

# --- example.com sanity check ---
print("\n[2] Navigate to example.com...")
r = tool("browser_navigate", {"url": "https://example.com"})
print(f"  Result: {text(r)[:150]}")

print("\n[3] Evaluate title on example.com...")
r = tool("browser_evaluate", {"function": "() => document.title"})
print(f"  Title: {extract_eval(text(r))}")

# --- WeChat ---
print(f"\n[4] Navigate to WeChat: {WECHAT_URL}")
r = tool("browser_navigate", {"url": WECHAT_URL})
nav = text(r)
print(f"  Nav result: {len(nav)} chars")
if nav:
    print(f"  {nav[:300]}")

# Immediate follow-up — no wait
print("\n[5] Immediate evaluate (title)...")
r = tool("browser_evaluate", {"function": "() => document.title"})
if r:
    print(f"  Title: {extract_eval(text(r))}")
else:
    print("  FAILED - session may be dead")
    print("\n[5b] Re-initializing session...")
    call("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "omnigraph-test", "version": "1.0"},
    })
    notify("notifications/initialized")
    print(f"  New session: {session_id}")

    print("\n[5c] Navigate to WeChat again...")
    r = tool("browser_navigate", {"url": WECHAT_URL})
    nav = text(r)
    print(f"  Nav: {len(nav)} chars — {nav[:200]}")

    print("\n[5d] Wait 5s then evaluate...")
    time.sleep(5)
    r = tool("browser_evaluate", {"function": "() => document.title"})
    if r:
        print(f"  Title: {extract_eval(text(r))}")
    else:
        print("  Still FAILED. Session dies after WeChat navigate.")
        print("\n  DIAGNOSIS: The remote CDP browser crashes when loading WeChat.")
        print("  The MCP server session is destroyed because the browser connection drops.")
        sys.exit(1)

print("\n[6] Wait 8s for dynamic content...")
time.sleep(8)

print("\n[7] Check #js_content...")
r = tool("browser_evaluate", {
    "function": '() => { var e = document.querySelector("#js_content"); return e ? "FOUND:" + e.innerHTML.length : "NOT_FOUND:" + document.body.innerHTML.length; }'
})
if r:
    print(f"  Content: {extract_eval(text(r))}")

print("\n[8] Text preview...")
r = tool("browser_evaluate", {
    "function": '() => { var e = document.querySelector("#js_content") || document.body; return e.innerText.substring(0, 500); }'
})
if r:
    print(f"  Preview: {extract_eval(text(r))[:500]}")

print("\n[9] Publish time...")
r = tool("browser_evaluate", {
    "function": '() => { var e = document.querySelector("#publish_time"); return e ? e.innerText : "NOT_FOUND"; }'
})
if r:
    print(f"  Time: {extract_eval(text(r))}")

print("\n[10] Image count...")
r = tool("browser_evaluate", {
    "function": "() => document.querySelectorAll('img').length"
})
if r:
    print(f"  Images: {extract_eval(text(r))}")

print(f"\n{'=' * 60}")
print("TEST COMPLETE")
print(f"{'=' * 60}")
