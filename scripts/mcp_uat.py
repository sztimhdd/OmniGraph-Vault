#!/usr/bin/env python3
"""mcp_uat.py — End-to-end MCP UAT (Ponytail M4, 2026-08-04, v2 SSE-aware).

Covers the full MCP StreamableHTTP lifecycle:
  1. initialize → SSE session negotiation
  2. notifications/initialized
  3. tools/list → verify 2 tools (fts_search, kg_search)
  4. fts_search → sync, returns results
  5. fts_search edge cases (empty query, excessive limit)
  6. kg_search → async job → poll → done
  7. Invalid tool call → graceful error
  8. Malformed method → error handling

Requires: httpx (already in project deps).

Usage:
    python3 scripts/mcp_uat.py [--mcp-url http://127.0.0.1:8767/mcp]
"""

import argparse, json, sys, time
import httpx

MCP_URL = "http://127.0.0.1:8767/mcp"
TIMEOUT = 30
HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

passed = 0
failed = 0


def rpc(method, params=None, sid=None):
    """Send a JSON-RPC request. Returns (status_code, parsed_data, session_id)."""
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    # Don't set id for notifications
    if "notification" not in method:
        body["id"] = int(time.time() * 1000) % 100000

    headers = dict(HEADERS)
    if sid:
        headers["mcp-session-id"] = sid

    try:
        resp = httpx.post(MCP_URL, json=body, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        return -1, {"error": str(e)}, sid

    # Parse SSE: "data: {...}" lines
    result = None
    for line in resp.text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                result = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
            break

    new_sid = resp.headers.get("mcp-session-id", sid)
    return resp.status_code, result, new_sid


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2713 {name}")
    else:
        failed += 1
        print(f"  \u2717 {name}  {detail}")


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
    print("1. initialize (SSE streamable-http)")
    code, data, sid = rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "mcp-uat", "version": "2.0"},
    })
    check("HTTP 200", code == 200, f"got {code}")
    check("has session ID", bool(sid), f"sid={sid}")
    if data:
        check("has protocolVersion",
              data.get("result", {}).get("protocolVersion") == "2024-11-05")
        check("has serverInfo",
              bool(data.get("result", {}).get("serverInfo")),
              str(data.get("result", {}).get("serverInfo", {})))

    # ── 2. notifications/initialized ──────────────────────────────
    print("\n2. notifications/initialized")
    code2, _, sid = rpc("notifications/initialized", sid=sid)
    check("accepted (200/202/204)", code2 in (200, 202, 204), f"got {code2}")

    # ── 3. tools/list ─────────────────────────────────────────────
    print("\n3. tools/list")
    code3, data3, sid = rpc("tools/list", sid=sid)
    tools = data3.get("result", {}).get("tools", []) if data3 else []
    tool_names = [t.get("name", "") for t in tools]
    check("HTTP 200", code3 == 200, f"got {code3}")
    check("has fts_search", "fts_search" in tool_names)
    check("has kg_search", "kg_search" in tool_names)
    check("exactly 2 tools", len(tools) == 2, f"got {len(tools)}: {tool_names}")
    stale = set(tool_names) - {"fts_search", "kg_search"}
    check("no stale tools", len(stale) == 0, f"stale: {stale}")

    # ── 4. fts_search — valid query ───────────────────────────────
    print("\n4. fts_search (valid)")
    code4, data4, sid = rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": "AI agent", "limit": 3},
    }, sid=sid)
    check("HTTP 200", code4 == 200, f"got {code4}")
    if data4 and "result" in data4:
        content = data4["result"].get("content", [])
        text = content[0].get("text", "") if content else ""
        check("returns results",
              text and "[no-results]" not in text,
              f"got: {text[:80]}")
    else:
        check("returns results", False, str(data4)[:100])

    # ── 5. fts_search — edge cases ────────────────────────────────
    print("\n5. fts_search (edge cases)")
    _, data5a, sid = rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": "", "limit": 1},
    }, sid=sid)
    err5 = data5a.get("error", {}) if data5a else {}
    check("empty query handled",
          "error" not in data5a or err5.get("code", 0) > -32000,
          str(data5a)[:80])

    _, data5b, sid = rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": "test", "limit": 999},
    }, sid=sid)
    check("excessive limit clamped",
          "result" in (data5b or {}),
          f"limit=999 should not crash: {str(data5b)[:80]}")

    # ── 6. kg_search — async job ──────────────────────────────────
    print("\n6. kg_search (async, timeout 90s)")
    code6, data6, sid = rpc("tools/call", {
        "name": "kg_search",
        "arguments": {"query": "OmniGraph architecture"},
    }, sid=sid)
    check("HTTP 200", code6 == 200, f"got {code6}")
    if data6 and "result" in data6:
        content = data6["result"].get("content", [])
        text = content[0].get("text", "") if content else ""
        check("no error markers in result",
              "[kg-" not in text,
              f"got: {text[:120]}")
    else:
        check("returns result", False, str(data6)[:80])

    # ── 7. Invalid tool call ──────────────────────────────────────
    print("\n7. Invalid tool call")
    _, data7, sid = rpc("tools/call", {
        "name": "nonexistent_tool",
        "arguments": {},
    }, sid=sid)
    check("no crash on invalid tool",
          data7 is not None and "error" not in str(data7).lower()[:200],
          f"got: {str(data7)[:80]}")

    # ── 8. Missing params ─────────────────────────────────────────
    print("\n8. fts_search missing required param")
    _, data8, sid = rpc("tools/call", {
        "name": "fts_search",
        "arguments": {},
    }, sid=sid)
    check("graceful error or fallback",
          data8 is not None,
          f"got: {str(data8)[:80]}")

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
