#!/usr/bin/env python3
"""MCP pipeline health + service checks. Returns 0 if OK, 1 if down.
On MCP failure: SSH back to WSL via repair tunnel, run diagnostics + self-repair.

v2 (2026-08-10): 修复 8/5-8/9 结构性失明——
  * 新增吞吐/新鲜度检查: kol-scan timers stale、ingest 最新 ok、kg-sync 日志、
    rss-fetch 成功率、新旧机点数 drift
  * 告警: problems 非空 → Telegram (ssh hermes send)
  * 自动恢复(非凭证类): scan timers 暂停但 capability ret=0 → 恢复;
    kb-api/kg-sync down → restart
  * 约束: 200013/200003/扫码仍只告警不自动修 (用户硬性规则)
"""
import json, urllib.request, sys, os, subprocess, logging, sqlite3, time, re

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("omnigraph-healthcheck")
problems = []

# ── Config ──
DB = "/root/OmniGraph-Vault/data/kol_scan.db"
KG_SYNC_LOG = "/var/log/omnigraph-kg-sync.log"
SCAN_TIMERS = ["omnigraph-kol-scan-batch@%d.timer" % i for i in (1, 2, 3, 4)]
STALE_SCAN_HOURS = 48      # normal cadence 4x/day; 48h = 2 missed days
STALE_INGEST_HOURS = 48    # RSS alone is thin; 48h no ok = acquisition dead
STALE_KGSYNC_HOURS = 26    # daily 02:30; 26h = one missed cycle + margin
RSS_OK_MIN_RATIO = 0.5
PROBE = "/root/OmniGraph-Vault/scripts/wechat_probe.py"
PY = "/root/OmniGraph-Vault/venv-aim1/bin/python"
NEW_QDRANT = "http://172.18.12.150:6333"
OLD_QDRANT = "http://127.0.0.1:6333"
# Alert throttle: same problem set re-alerts at most once per window,
# otherwise a multi-day stale condition would spam Telegram every 15 min.
ALERT_STATE = "/var/lib/omnigraph-healthcheck-state.json"
ALERT_THROTTLE_HOURS = 6


def notify_telegram(text: str) -> None:
    """Send Telegram via ssh hermes (stdin pipe avoids quote nesting)."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "hermes",
             "~/.local/bin/hermes send -t telegram"],
            input=text, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            print(f"  [telegram] send failed rc={r.returncode}")
    except Exception as e:
        print(f"  [telegram] error {e}")


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

# ── Service checks (existing, keep) ──

def _http(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

# 1. kb-api
if not _http("http://127.0.0.1:8766/health"):
    problems.append(("kb-api", "down"))
    # Auto-recover: kb-api restart is cheap and safe (no credentials involved)
    subprocess.run(["systemctl", "restart", "kb-api.service"], capture_output=True, timeout=30)
    time.sleep(3)
    if _http("http://127.0.0.1:8766/health"):
        print("  [kb-api] restarted and recovered")
    else:
        print("  [kb-api] restart did NOT recover")

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

# ── v2: throughput / freshness checks ──

def _ts_hours_ago(ts_str: str) -> float:
    """Parse '%Y-%m-%d %H:%M:%S' (naive local) into hours since now."""
    if not ts_str:
        return float("inf")
    try:
        dt = time.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        return (time.time() - time.mktime(dt)) / 3600.0
    except (ValueError, OSError):
        return float("inf")

# 4. KOL scan timers stale — the 8/5-8/9 blind spot
try:
    r = subprocess.run(["systemctl", "show"] + SCAN_TIMERS + ["-p", "LastTriggerUSec", "--value"],
                       capture_output=True, text=True, timeout=10)
    triggers = [ln.strip() for ln in r.stdout.splitlines() if ln.strip() and ln.strip() != "n/a"]
    if not triggers:
        problems.append(("kol-scan", "no-trigger-record"))
    else:
        raw = max(triggers)  # lexicographic works for ISO-ish timestamps
        m = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", raw)
        if m:
            hours = _ts_hours_ago(m.group(0))
            if hours > STALE_SCAN_HOURS:
                problems.append(("kol-scan", f"last-trigger {hours:.0f}h ago"))
        else:
            problems.append(("kol-scan", f"unparseable {raw[:40]}"))
except Exception as e:
    problems.append(("kol-scan", f"check-error {e}"))

# 5. Ingest staleness — latest ok ingestion
try:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    row = conn.execute("SELECT ingested_at FROM ingestions WHERE status='ok' ORDER BY ingested_at DESC LIMIT 1").fetchone()
    conn.close()
    hours = _ts_hours_ago(row[0] if row else "")
    if hours > STALE_INGEST_HOURS:
        problems.append(("ingest", f"latest-ok {hours:.0f}h ago"))
    else:
        log.info(json.dumps({"check": "ingest", "latest_ok_hours": round(hours, 1)}))
except Exception as e:
    problems.append(("ingest", f"check-error {e}"))

# 6. kg-sync staleness (daily 02:30 job) + auto-restart
try:
    with open(KG_SYNC_LOG) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", tail)
    if m:
        hours = _ts_hours_ago(m.group(1))
        if hours > STALE_KGSYNC_HOURS:
            problems.append(("kg-sync", f"last-log {hours:.0f}h ago"))
            subprocess.run(["systemctl", "start", "omnigraph-kg-sync.service"], capture_output=True, timeout=60)
            print("  [kg-sync] restart-triggered")
    else:
        problems.append(("kg-sync", "no-log-entry"))
except Exception as e:
    problems.append(("kg-sync", f"check-error {e}"))

# 7. RSS feed health (last rss-fetch run)
try:
    r = subprocess.run(
        ["journalctl", "-u", "omnigraph-rss-fetch.service", "--since", "48 hours ago", "--no-pager", "-o", "cat"],
        capture_output=True, text=True, timeout=10)
    m_ok = re.search(r"feeds_ok['\"]?\s*[:=]\s*(\d+)", r.stdout)
    m_fail = re.search(r"feeds_fail['\"]?\s*[:=]\s*(\d+)", r.stdout)
    if m_ok and m_fail:
        ok, fail = int(m_ok.group(1)), int(m_fail.group(1))
        total = ok + fail
        if total and ok / total < RSS_OK_MIN_RATIO:
            problems.append(("rss-fetch", f"feeds_ok={ok}/{total}"))
        else:
            log.info(json.dumps({"check": "rss-fetch", "feeds_ok": ok, "feeds_fail": fail}))
    else:
        problems.append(("rss-fetch", "no-run-in-48h"))
except Exception as e:
    problems.append(("rss-fetch", f"check-error {e}"))

# 8. New vs old Qdrant point counts (sync drift)
try:
    def _count(url, coll):
        req = urllib.request.Request(f"{url}/collections/{coll}/points/count",
                                     data=json.dumps({"exact": True}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())["result"]["count"]
    colls = ["lightrag_vdb_entities_bge_m3_1024d", "lightrag_vdb_chunks_bge_m3_1024d", "lightrag_vdb_relationships_bge_m3_1024d"]
    for coll in colls:
        try:
            old_c = _count(OLD_QDRANT, coll)
            new_c = _count(NEW_QDRANT, coll)
            if new_c < old_c:
                problems.append(("kg-sync-drift", f"{coll}: new={new_c} < old={old_c}"))
        except Exception:
            pass  # collection may not exist on either side yet — best-effort
except Exception:
    pass

# ── Auto-recovery: scan timers paused but capability healthy ──
# Only when the ONLY scan problem is staleness (not a live 200013/200003).
# Probe is single-shot; if capability is limited (ret=200013) we keep paused
# and the problem stays in the alert. Never force QR / re-login.
scan_stale = any(n == "kol-scan" for n, _ in problems)
if scan_stale:
    try:
        r = subprocess.run([PY, PROBE, "both"], capture_output=True, text=True, timeout=60)
        out = (r.stdout + r.stderr)[-500:]
        # probe exits: 0 = session+list OK, 1 = session OK but list limited,
        #              2 = session invalid, 3 = probe error
        if r.returncode == 0:
            for t in SCAN_TIMERS:
                subprocess.run(["systemctl", "start", t], capture_output=True, timeout=15)
            print("  [kol-scan] capability OK — timers restarted")
            problems = [(n, s) for n, s in problems if n != "kol-scan"]
        elif r.returncode == 1:
            print("  [kol-scan] capability limited (ret=200013) — keep paused")
        elif r.returncode == 2:
            print("  [kol-scan] session INVALID — keep paused (operator QR required)")
        else:
            print(f"  [kol-scan] probe error rc={r.returncode}")
    except Exception as e:
        print(f"  [kol-scan] probe failed {e}")

# ── Report ──
if problems:
    detail = "; ".join(f"{name}={status}" for name, status in problems)
    log.warning(json.dumps({"health": "problems", "checks": [dict(name=n, status=s) for n, s in problems]}))

    # Throttle: only notify if the problem signature changed or the last
    # notify was > ALERT_THROTTLE_HOURS ago. Persist signature + ts.
    sig = ";".join(f"{n}={s}" for n, s in sorted(problems))
    now = time.time()
    should_notify = True
    try:
        with open(ALERT_STATE) as f:
            st = json.load(f)
        if st.get("sig") == sig and now - st.get("ts", 0) < ALERT_THROTTLE_HOURS * 3600:
            should_notify = False
    except Exception:
        pass
    if should_notify:
        notify_telegram(f"🔴 OmniGraph 健康检查告警: {detail}")
        try:
            with open(ALERT_STATE, "w") as f:
                json.dump({"sig": sig, "ts": now}, f)
        except Exception:
            pass
    sys.exit(1)

log.info(json.dumps({"health": "ok"}))
sys.exit(0)
