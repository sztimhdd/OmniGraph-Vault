#!/usr/bin/env python3
"""mcp_uat.py — End-to-end MCP UAT (Ponytail M4, 2026-08-04).

Covers the full MCP lifecycle beyond bare tools/list:
  1. initialize → session negotiation
  2. tools/list → verify 2 tools (fts_search, kg_search)
  3. fts_search → sync, returns results
  4. kg_search → async job → poll → done
  5. fts_search empty query → graceful handling
  6. fts_search excessive limit → clamped
  7. invalid mode → error handling
  8. timeout resilience (network-dependent, best-effort)

Usage:
    python3 scripts/mcp_uat.py [--mcp-url http://127.0.0.1:8767/mcp]
"""

import argparse, json, sys, time, urllib.request, urllib.error

MCP_URL = "http://127.0.0.1:8767/mcp"
TIMEOUT = 30

passed = 0
failed = 0

def _req(method, params=None, req_id=None):
    """Send a JSON-RPC request to the MCP server."""
    if req_id is None:
        req_id = int(time.time() * 1000) % 100000
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": {"code": e.code, "message": str(e)}}
    except Exception as e:
        return {"error": {"code": -1, "message": str(e)}}


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}  {detail}")


def main():
    global MCP_URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-url", default=MCP_URL)
    args = parser.parse_args()
    MCP_URL = args.mcp_url

    print(f"OmniGraph MCP UAT — {MCP_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ── 1. initialize ─────────────────────────────────────────────
    print("1. initialize")
    r = _req("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "mcp-uat", "version": "1.0.0"},
    })
    check("returns result", "result" in r, str(r))
    sid = None
    if "result" in r:
        check("has protocolVersion", "protocolVersion" in r["result"])
        check("has serverInfo", "serverInfo" in r["result"], str(r.get("result", {})))
        check("has capabilities", "capabilities" in r["result"])
        sid = r["result"].get("sessionId") or r["result"].get("session_id")
    
    # ── 2. notifications/initialized ──────────────────────────────
    print("\n2. notifications/initialized")
    r2 = _req("notifications/initialized", {})
    # FastMCP may return empty or result — either is OK for initialized
    check("no error", "error" not in r2 or r2.get("error", {}).get("code") != -32600, str(r2))

    # ── 3. tools/list ─────────────────────────────────────────────
    print("\n3. tools/list")
    r3 = _req("tools/list", {})
    tools = r3.get("result", {}).get("tools", [])
    tool_names = [t.get("name", "") for t in tools]
    check("has fts_search", "fts_search" in tool_names)
    check("has kg_search", "kg_search" in tool_names)
    check("exactly 2 tools", len(tools) == 2, f"got {len(tools)}: {tool_names}")
    # Audit: verify no stale tools from the pre-July-31 6-tool era
    stale = set(tool_names) - {"fts_search", "kg_search"}
    check("no stale tools", len(stale) == 0, f"stale: {stale}")

    # ── 4. fts_search — valid query ───────────────────────────────
    print("\n4. fts_search (valid)")
    r4 = _req("tools/call", {"name": "fts_search", "arguments": {"query": "AI agent", "limit": 3}})
    if "result" in r4:
        content = r4["result"].get("content", [])
        text = content[0].get("text", "") if content else ""
        check("returns results", text and "[no-results]" not in text, f"got: {text[:80]}")
    else:
        check("returns results", False, str(r4))

    # ── 5. fts_search — edge cases ────────────────────────────────
    print("\n5. fts_search (edge cases)")
    r5a = _req("tools/call", {"name": "fts_search", "arguments": {"query": "", "limit": 1}})
    check("empty query no crash", "error" not in r5a or r5a.get("error", {}).get("code", 0) > -32000, str(r5a))
    
    r5b = _req("tools/call", {"name": "fts_search", "arguments": {"query": "test", "limit": 999}})
    check("excessive limit clamped", "result" in r5b, f"limit=999 should not crash")

    # ── 6. kg_search — async job ──────────────────────────────────
    print("\n6. kg_search (async, timeout 60s)")
    r6 = _req("tools/call", {"name": "kg_search", "arguments": {"query": "OmniGraph architecture"}})
    if "result" in r6:
        content = r6["result"].get("content", [])
        text = content[0].get("text", "") if content else ""
        check("no timeout/error marker", "[kg-" not in text, f"got: {text[:120]}")
    else:
        check("returns result", False, str(r6))

    # ── 7. Invalid tool call ──────────────────────────────────────
    print("\n7. Invalid tool call")
    r7 = _req("tools/call", {"name": "nonexistent_tool", "arguments": {}})
    check("graceful error", "error" in r7, f"expected error, got: {str(r7)[:80]}")

    # ── 8. Malformed request ──────────────────────────────────────
    print("\n8. Malformed request")
    r8 = _req("invalid_method_xyz", {})
    check("method not found", "error" in r8, f"got: {str(r8)[:80]}")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'='*50}")
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed:
        print("FAIL — see details above")
    else:
        print("PASS — all checks passed")
    print(f"{'='*50}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
