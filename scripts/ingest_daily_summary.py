#!/usr/bin/env python3
"""ingest_daily_summary — daily Telegram digest of the OmniGraph ingest pipeline.

Runs via omnigraph-ingest-daily-summary.timer (09:00 daily). Sends ONE message
with: yesterday's ingest count, RSS fetch health, KOL scan (dajiala) status,
candidate-pool depth, kg-sync freshness, and any open problems.

Read-only: queries the DB and systemd; never mutates pipeline state.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

DB = "/root/OmniGraph-Vault/data/kol_scan.db"
DAJIALA_TIMER = "omnigraph-dajiala-scan.timer"
RSS_SERVICE = "omnigraph-rss-fetch.service"
KG_SYNC_LOG = "/var/log/omnigraph-kg-sync.log"


def _q(conn, sql, *args):
    try:
        return conn.execute(sql, args).fetchone()
    except Exception:
        return None


def _ts_hours_ago(ts_str: str) -> float:
    if not ts_str:
        return float("inf")
    try:
        dt = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - dt).total_seconds() / 3600.0
    except ValueError:
        return float("inf")


def collect() -> dict:
    out: dict = {}
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)

    # 1. Yesterday's ingest success (status='ok' per source)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    row = _q(conn, "SELECT COUNT(*) FROM ingestions WHERE status='ok' AND date(ingested_at)=?", yesterday)
    out["yesterday_ok"] = row[0] if row else 0
    row = _q(conn, "SELECT COUNT(*) FROM ingestions WHERE status='ok' AND date(ingested_at)=?"
                    " AND source='rss'", yesterday)
    out["yesterday_rss"] = row[0] if row else 0
    row = _q(conn, "SELECT COUNT(*) FROM ingestions WHERE status='ok' AND date(ingested_at)=?"
                    " AND source='wechat'", yesterday)
    out["yesterday_wechat"] = row[0] if row else 0

    # 2. Today's ingest so far
    today = datetime.now().strftime("%Y-%m-%d")
    row = _q(conn, "SELECT COUNT(*) FROM ingestions WHERE status='ok' AND date(ingested_at)=?", today)
    out["today_ok"] = row[0] if row else 0

    # 3. Latest ok ingestion freshness (blocked pipeline signal)
    row = _q(conn, "SELECT ingested_at FROM ingestions WHERE status='ok' ORDER BY ingested_at DESC LIMIT 1")
    out["latest_ok_hours"] = round(_ts_hours_ago(row[0] if row else ""), 1)

    # 4. Candidate pool depth (articles awaiting layer1/ingest)
    row = _q(conn, "SELECT COUNT(*) FROM articles WHERE layer1_verdict IS NULL OR layer1_verdict='candidate'")
    out["candidate_depth"] = row[0] if row else 0

    conn.close()

    # 5. dajiala KOL scan timer state
    try:
        r = subprocess.run(["systemctl", "is-active", DAJIALA_TIMER], capture_output=True, text=True, timeout=10)
        out["dajiala_timer"] = r.stdout.strip()
    except Exception:
        out["dajiala_timer"] = "unknown"
    try:
        r = subprocess.run(["systemctl", "show", DAJIALA_TIMER, "-p", "LastTriggerUSec", "--value"],
                           capture_output=True, text=True, timeout=10)
        out["dajiala_last_trigger"] = r.stdout.strip().split(";")[0]
    except Exception:
        out["dajiala_last_trigger"] = ""

    # 6. RSS fetch health (last run in journal, 48h window)
    try:
        r = subprocess.run(
            ["journalctl", "-u", RSS_SERVICE, "--since", "48 hours ago", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=10)
        m_ok = re.search(r"feeds_ok['\"]?\s*[:=]\s*(\d+)", r.stdout)
        m_fail = re.search(r"feeds_fail['\"]?\s*[:=]\s*(\d+)", r.stdout)
        out["rss_feeds_ok"] = int(m_ok.group(1)) if m_ok else None
        out["rss_feeds_fail"] = int(m_fail.group(1)) if m_fail else None
    except Exception:
        out["rss_feeds_ok"] = out["rss_feeds_fail"] = None

    # 7. kg-sync freshness
    try:
        with open(KG_SYNC_LOG) as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        tail = lines[-1] if lines else ""
        m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", tail)
        out["kg_sync_hours"] = round(_ts_hours_ago(m.group(1) if m else ""), 1)
    except Exception:
        out["kg_sync_hours"] = float("inf")

    return out


def render(d: dict) -> str:
    """Build the single Telegram message text."""
    lines = ["📊 OmniGraph ingest 日报"]
    lines.append(f"🗓 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"✅ 昨日入库: {d['yesterday_ok']} 篇 (RSS {d['yesterday_rss']} / KOL {d['yesterday_wechat']})")
    lines.append(f"🔄 今日入库: {d['today_ok']} 篇")
    latest = d["latest_ok_hours"]
    lines.append(f"⏱ 最近成功: {latest:.0f}h 前" if latest != float("inf") else "⏱ 最近成功: 无记录")
    lines.append(f"🗂 候选池: {d['candidate_depth']} 篇待处理")
    lines.append("")
    lines.append(f"📡 RSS: {d['rss_feeds_ok']}/{d['rss_feeds_ok'] + d['rss_feeds_fail']} feeds OK"
                 if d["rss_feeds_ok"] is not None else "📡 RSS: 近48h无运行记录")
    timer = d["dajiala_timer"]
    trig = d["dajiala_last_trigger"]
    if timer == "active":
        lines.append(f"🔍 KOL扫描(dajiala): 周扫已启用" + (f", 上次 {trig[:16]}" if trig and trig != "n/a" else ""))
    else:
        lines.append(f"🔍 KOL扫描(dajiala): timer {timer} (未启用)")
    kg = d["kg_sync_hours"]
    lines.append(f"🔗 kg-sync: {kg:.0f}h 前" if kg != float("inf") else "🔗 kg-sync: 无日志")
    lines.append("")
    problems = []
    if latest > 48:
        problems.append(f"ingest 阻塞: 最近成功 {latest:.0f}h 前")
    if d["rss_feeds_ok"] is not None and d["rss_feeds_fail"] is not None:
        total = d["rss_feeds_ok"] + d["rss_feeds_fail"]
        if total and d["rss_feeds_ok"] / total < 0.5:
            problems.append(f"RSS 成功率低: {d['rss_feeds_ok']}/{total}")
    if kg > 26:
        problems.append(f"kg-sync 过期: {kg:.0f}h 前")
    if problems:
        lines.append("🚨 问题:")
        for p in problems:
            lines.append(f"  • {p}")
    else:
        lines.append("✅ 无异常")
    return "\n".join(lines)


def notify_telegram(text: str) -> None:
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "hermes",
             "~/.local/bin/hermes send -t telegram"],
            input=text, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            print(f"[telegram] send failed rc={r.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[telegram] error {e}", file=sys.stderr)


def main() -> None:
    d = collect()
    msg = render(d)
    print(msg)
    if os.environ.get("DRY_RUN"):
        return
    notify_telegram(msg)


if __name__ == "__main__":
    main()
