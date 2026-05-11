#!/usr/bin/env python3
"""Monitor daily-ingest batch. Outputs progress or completion report.

Usage: python3 daily_ingest_monitor.py

Deploy as no_agent cron:
  hermes cronjob create --name daily-ingest-50-monitor --schedule "every 30m" \
    --deliver telegram --script daily_ingest_monitor.py --no-agent

Stdout output is delivered verbatim to Telegram. When completion is detected,
a /tmp/daily_ingest_done sentinel prevents repeated delivery.
"""
import sqlite3, subprocess, sys, os, time
from datetime import datetime

LOG = "/tmp/daily-ingest-20260509-1626.log"
DB = os.path.expanduser("~/OmniGraph-Vault/data/kol_scan.db")
SESSION = "daily-ingest-20260509"

def db_counts():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT source, status, COUNT(*) FROM ingestions "
        "WHERE date(ingested_at) = date('now','localtime') "
        "GROUP BY source, status"
    ).fetchall()
    conn.close()
    return {f"{r[0]}/{r[1]}": r[2] for r in rows}

def log_grep(pattern, tail_n=100):
    r = subprocess.run(
        f"grep -E '{pattern}' {LOG} | tail -{tail_n}",
        shell=True, capture_output=True, text=True
    )
    return r.stdout.strip()

def tail_log(n=5):
    r = subprocess.run(["tail", f"-{n}", LOG], capture_output=True, text=True)
    return r.stdout.strip()

def main():
    # Sentinel: already reported as done, be silent
    if os.path.exists("/tmp/daily_ingest_done"):
        return

    # Check if log exists
    if not os.path.exists(LOG):
        print("❌ Log file not found")
        return

    counts = db_counts()
    capped = "max-articles cap reached" in log_grep("max-articles cap reached")
    processed_all = "articles processed" in tail_log(20)

    if capped or processed_all:
        # Completion detected — verify stable counts
        counts1 = db_counts()
        time.sleep(30)
        counts2 = db_counts()
        stable = counts1 == counts2

        if not stable:
            print("⚠️ Completion detected but DB still changing, re-check next cycle")
            return

        # Kill zombie tmux
        subprocess.run(["tmux", "kill-session", "-t", SESSION],
                       capture_output=True)

        lines = ["✅ daily-ingest done"]
        if capped:
            lines.append("Trigger: max-articles cap reached (50)")
        else:
            lines.append("Trigger: all articles processed")
        lines.append("")
        lines.append("DB counts (today):")
        for k in sorted(counts2.keys()):
            lines.append(f"  {k:25s} {counts2[k]}")
        lines.append("")
        lines.append(f"Zombie cleanup: tmux kill-session -t {SESSION}")
        lines.append(f"Log: {LOG}")
        lines.append("Grep: grep -E '(ok|failed|skipped|capped)' " + LOG)
        print("\n".join(lines))

        # Write sentinel — silence future runs
        with open("/tmp/daily_ingest_done", "w") as f:
            f.write(datetime.now().isoformat())
    else:
        # Progress update
        last_layers = log_grep(r"\[layer[12]\] batch")
        last_lines = last_layers.split("\n")[-3:] if last_layers else ["(no layer info)"]
        last_article = log_grep(r"\[\d+/\d+\]", tail_n=1)

        lines = ["📊 daily-ingest progress"]
        lines.append("")
        lines.append("DB counts (today):")
        for k in sorted(counts.keys()):
            lines.append(f"  {k:25s} {counts[k]}")
        lines.append("")
        lines.append("Last layer batches:")
        for l in last_lines[-3:]:
            lines.append(f"  {l.strip()}")
        if last_article:
            lines.append(f"  {last_article.strip()}")
        print("\n".join(lines))

if __name__ == "__main__":
    main()
