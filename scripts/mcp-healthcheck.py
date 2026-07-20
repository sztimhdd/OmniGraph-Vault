#!/usr/bin/env python3
"""MCP pipeline health + service checks. Returns 0 if OK, 1 if down.
On MCP failure: SSH back to WSL via repair tunnel, run diagnostics + self-repair."""
import json, urllib.request, sys, os, subprocess, logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("omnigraph-healthcheck")
problems = []

# ── MCP check (existing, keep) ──

URL = "http://127.0.0.1:58931/mcp"
PAYLOAD = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"hc","version":"1"}}}).encode()
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Host": "localhost:8931"}

def mcp_ok():
    try:
        req = urllib.request.Request(URL, data=PAYLOAD, headers=HEADERS, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return '"serverInfo"' in resp.read().decode()
    except Exception:
        return False

def ssh_repair():
    cmd = [
        "ssh", "-i", "/root/.ssh/wsl_repair_key",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=8",
        "-p", "58932",
        "sztimhdd@localhost",
        "set -e; "
        "echo '=== MCP Healthcheck Repair ==='; "
        "echo '--- services ---'; "
        "systemctl --user is-active playwright-mcp aliyun-tunnel 2>&1 || true; "
        "echo '--- restart tunnel ---'; "
        "systemctl --user restart aliyun-tunnel 2>&1 || true; "
        "echo '--- restart MCP ---'; "
        "systemctl --user restart playwright-mcp 2>&1 || true; "
        "echo '--- CDP check ---'; "
        "curl -s --max-time 3 http://127.0.0.1:9223/json/version | head -1 || echo 'CDP FAIL'; "
        "echo '--- verify ---'; "
        "sleep 3 && ss -tlnp | grep -E '8931|9223' || echo 'ports MISSING'; "
        "echo '--- notify ---'; "
        "/home/sztimhdd/.local/bin/hermes cron list 2>&1 | head -3 || true; "
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        for line in result.stdout.splitlines():
            print(f"  [WSL] {line}")
        if result.stderr:
            for line in result.stderr.splitlines():
                print(f"  [WSL:err] {line}")
        return result.returncode == 0
    except Exception as e:
        print(f"  [WSL] SSH repair failed: {e}")
        return False

# ── MCP main ──

if not mcp_ok():
    print("MCP DOWN on 58931 — attempting SSH repair to WSL")
    ssh_repair()
    if mcp_ok():
        print("MCP RECOVERED after SSH repair")
    else:
        print("MCP STILL DOWN after repair")
        problems.append(("mcp", "down"))

# ── Service checks (new) ──

def _http(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

# 1. kb-api
if not _http("http://127.0.0.1:8766/health"):
    problems.append(("kb-api", "down"))

# 2. Disk (>90%)
try:
    r = subprocess.run(["df", "--output=pcent", "/"], capture_output=True, text=True, timeout=5)
    pct = int(r.stdout.strip().splitlines()[-1].rstrip("%"))
    if pct >= 90:
        problems.append(("disk", f"{pct}% used"))
except Exception:
    problems.append(("disk", "check-failed"))

# 3. 429 counter (informational, not fatal)
try:
    r = subprocess.run(
        ["journalctl", "-u", "omnigraph-daily-ingest.service",
         "--since", "24 hours ago", "--no-pager", "-o", "cat"],
        capture_output=True, text=True, timeout=10)
    n429 = r.stdout.count("429")
    if n429 > 0:
        log.info(json.dumps({"check": "429", "count_last_24h": n429}))
except Exception:
    pass

# ── Report ──
if problems:
    for name, detail in problems:
        log.warning(json.dumps({"check": name, "status": detail}))
    sys.exit(1)

log.info(json.dumps({"health": "ok"}))
sys.exit(0)
