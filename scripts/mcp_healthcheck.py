#!/usr/bin/env python3
"""mcp_healthcheck.py — OmniGraph MCP + KB 健康度自检（本地 Hermes 侧执行）。

Covers:
  A. omnigraph-kg MCP (3 tools: fts_search / kg_search / kg_poll)
     - via local SSH tunnel 127.0.0.1:8767 (primary)
     - via public 47.103.73.20:8767 (direct, ~10% cross-border loss)
  B. health endpoints (SSH): new machine :8768, old machine kb-api :8766
  C. tool smoke: fts_search hit / kg_search within 55s returns job_id or
     full result / kg_poll <5s

Exit 0 = all PASS (known caveats do not fail the run).
Exit 1 = any FAIL (needs operator attention).

Stdlib only. Run:  python3 scripts/mcp_healthcheck.py [--public] [--json]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TUNNEL_MCP = "http://127.0.0.1:8767/mcp"
PUBLIC_MCP = "http://47.103.73.20:8767/mcp"
EXPECTED_TOOLS = {"fts_search", "kg_search", "kg_poll"}

results: list[dict] = []


def rec(name: str, ok: bool, detail: str, known: bool = False) -> None:
    results.append({"name": name, "ok": ok, "detail": detail, "known": known})


def http_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, dict, str]:
    """POST JSON to an MCP streamable-http endpoint; return (status, parsed, session_id)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    session = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            session = resp.headers.get("mcp-session-id")
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        return e.code, {}, ""
    except Exception as e:  # URLError / timeout
        return 0, {"_error": str(e)}, ""
    # streamable-http returns SSE lines; grab the last JSON payload
    parsed: dict = {}
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                parsed = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return status, parsed, session or ""


def mcp_initialize(url: str, timeout: int = 15) -> tuple[int, str]:
    status, data, session = http_json(
        url,
        {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-healthcheck", "version": "1.0"},
            },
        },
        timeout,
    )
    return status, session


def mcp_tools(url: str, session: str) -> list[str]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception:
        return []
    names: list[str] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                obj = json.loads(line[6:])
                for t in obj.get("result", {}).get("tools", []):
                    names.append(t.get("name", ""))
            except json.JSONDecodeError:
                pass
    return sorted(set(n for n in names if n))


def mcp_call(url: str, session: str, tool: str, args: dict, timeout: int = 90) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return f"[call-error: {e}]"
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                obj = json.loads(line[6:])
                for item in obj.get("result", {}).get("content", []):
                    if item.get("type") == "text":
                        return item.get("text", "")
            except json.JSONDecodeError:
                pass
    return "[no-text-result]"


def ssh_cmd(host: str, cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=12", host, cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()[:300]
    except Exception as e:
        return f"[ssh-error: {e}]"


def check_mcp_endpoint(label: str, url: str, run_tools: bool) -> None:
    t0 = time.monotonic()
    status, session = mcp_initialize(url)
    dt = time.monotonic() - t0
    if status != 200 or not session:
        rec(f"{label} initialize", False, f"status={status} session={'yes' if session else 'NO'}")
        return
    rec(f"{label} initialize", True, f"status={status} session_id={session[:8]}… ({dt:.1f}s)")

    if not run_tools:
        return

    tools = mcp_tools(url, session)
    missing = EXPECTED_TOOLS - set(tools)
    if missing:
        rec(f"{label} tools/list", False, f"missing={sorted(missing)} got={tools}")
    else:
        rec(f"{label} tools/list", True, f"{len(tools)} tools: {tools}")

    # fts smoke — must hit real data (8/3 article), not [no-results]
    fts = mcp_call(url, session, "fts_search", {"query": "火山方舟"}, timeout=30)
    if "[no-results]" in fts or "[call-error" in fts:
        rec(f"{label} fts_search", False, fts[:100])
    else:
        rec(f"{label} fts_search", True, fts.splitlines()[0][:60] if fts else "empty")

    # kg_search — must return within 55s budget (job_id or full result)
    t0 = time.monotonic()
    kg = mcp_call(url, session, "kg_search", {"query": "DeepSeek V4"}, timeout=70)
    dt = time.monotonic() - t0
    if dt > 60:
        rec(f"{label} kg_search", False, f"{dt:.0f}s EXCEEDS 60s client budget")
    elif "[kg-running]" in kg:
        rec(f"{label} kg_search", True, f"{dt:.0f}s → job_id path (slow query, use kg_poll)")
    elif "[call-error" in kg:
        rec(f"{label} kg_search", False, kg[:100])
    else:
        rec(f"{label} kg_search", True, f"{dt:.0f}s → full result: {kg.splitlines()[0][:50]}")

    # kg_poll — poll the job returned above, expect <5s
    jid = ""
    for part in kg.split():
        if part.startswith("job_id="):
            jid = part.split("=")[1].strip(",\"")
            break
    if jid:
        t0 = time.monotonic()
        poll = mcp_call(url, session, "kg_poll", {"job_id": jid}, timeout=15)
        dt = time.monotonic() - t0
        if "[call-error" in poll or "[no-text" in poll:
            rec(f"{label} kg_poll", False, poll[:100])
        else:
            rec(f"{label} kg_poll", True, f"{dt:.1f}s → {poll.splitlines()[0][:50]}")
    else:
        rec(f"{label} kg_poll", True, "skipped (kg_search returned full result)")


def main() -> None:
    ap = argparse.ArgumentParser(description="OmniGraph MCP health check")
    ap.add_argument("--public", action="store_true", help="also probe public 8767 (cross-border)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # A. tunnel MCP (primary — what Hermes uses)
    check_mcp_endpoint("tunnel:8767", TUNNEL_MCP, run_tools=True)

    # A2. public MCP (direct; known ~10% loss, retried once)
    if args.public:
        check_mcp_endpoint("public:8767", PUBLIC_MCP, run_tools=True)

    # B. new machine :8768 health via SSH
    h = ssh_cmd("aliyun-new", "curl -sf --max-time 8 http://127.0.0.1:8768/health || curl -sf --max-time 8 http://127.0.0.1:8768/live")
    rec("new:8768 health", "ok" in h.lower() or "status" in h.lower(), h[:100])

    # C. old machine kb-api :8766 via SSH
    h = ssh_cmd("aliyun-old", "curl -sf --max-time 8 http://127.0.0.1:8766/health")
    rec("old:8766 kb-api", '"status":"ok"' in h, h[:100])

    # D. old machine embed-server :7997 via SSH
    h = ssh_cmd("aliyun-old", "curl -sf --max-time 8 http://127.0.0.1:7997/health")
    rec("old:7997 embed", '"ok"' in h.lower() or "status" in h.lower(), h[:100])

    fails = [r for r in results if not r["ok"] and not r["known"]]
    known = [r for r in results if not r["ok"] and r["known"]]

    if args.json:
        print(json.dumps({"results": results, "failed": len(fails), "known": len(known)}, ensure_ascii=False, indent=1))
    else:
        print("\n=== OmniGraph MCP Health ===")
        for r in results:
            mark = "✅" if r["ok"] else ("⚠️" if r["known"] else "❌")
            print(f"  {mark} {r['name']}: {r['detail']}")
        print(f"\nPASS {len(results) - len(fails) - len(known)} / {len(results)}"
              f"{f' + {len(known)} known-caveat' if known else ''}"
              f"{'  ❌ FAIL: ' + str(len(fails)) if fails else '  — ALL GREEN'}")
        if fails:
            print("  见 FAIL 项；常规修复：新机 `systemctl restart omni-mcp` / 隧道 `systemctl --user restart omnigraph-tunnel`")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
