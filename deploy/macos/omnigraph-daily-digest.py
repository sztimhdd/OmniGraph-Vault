#!/usr/bin/env python3
"""OmniGraph daily digest → stdout (piped into WeChat notification)."""
import subprocess
from datetime import datetime

ALIYUN = "root@47.117.244.253"
DB = "/root/.hermes/omonigraph-vault/kol_scan.db"

def ssh(cmd):
    """Run a command on Aliyun, return stdout or 'ERR'."""
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        ALIYUN, cmd], capture_output=True, text=True, timeout=20)
    return r.stdout.strip() if r.returncode == 0 else "ERR"

def sql(q):
    return ssh(f'sqlite3 -separator "|" {DB} "{q}"')

now = datetime.now()

# Core stats (single query for performance)
stats = sql("""
SELECT
  (SELECT COUNT(*) FROM articles WHERE scanned_at >= datetime('now','localtime','-24 hours')),
  (SELECT COUNT(*) FROM articles),
  (SELECT COUNT(*) FROM ingestions),
  (SELECT COUNT(*) FROM ingestions WHERE ingested_at >= datetime('now','localtime','-24 hours'))
""")

if stats == "ERR" or not stats:
    print("OmniGraph digest: SSH/DB query failed")
    sys.exit(1)

new_arts, total, total_ing, scans = stats.split("|")

# Cookie freshness (hours since last successful ingest)
cookie_sql = "SELECT CAST((julianday('now','localtime')-julianday(MAX(ingested_at)))*24 AS INT) FROM ingestions WHERE status='ok'"
cookie_h = sql(cookie_sql)

# Scan failures in past 48h (from journal)
failures = ssh(
    f'journalctl -u "omnigraph-kol-scan-batch@*" --since "48 hours ago" --no-pager '
    f'| grep -c "invalid session" || echo 0'
)

# Failed ingestions in past 24h
failed = sql("""
SELECT COUNT(*) FROM ingestions
WHERE ingested_at >= datetime('now','localtime','-24 hours')
AND status = 'failed'
""")

# Today's articles
today = sql("""
SELECT COUNT(*) FROM articles
WHERE date(scanned_at) = date('now','localtime')
""")

lines = [
    f"📊 OmniGraph {now.strftime('%m/%d %H:%M')}",
    f"近24h: {scans} 次摄入 → {new_arts} 新文章 (今日 {today})",
    f"总量: {total} 篇 / {total_ing} 次摄入",
    f"Cookie: {cookie_h}h前活跃",
]

if failures and failures.strip() != "0":
    lines.append(f"🔴 近48h invalid-session: {failures.strip()} 次")
    lines.append("⚠️ 需重新扫码")

if failed and failed != "0":
    lines.append(f"⚠️ 摄入失败: {failed} 次")

if scans == "0":
    lines.append("⚠️ 近24h 无摄入活动")

print("\n".join(lines))
