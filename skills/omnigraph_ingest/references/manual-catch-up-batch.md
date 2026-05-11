# Manual Catch-Up Batch — Full Workflow

## When to Use

- User says "run daily-ingest catch-up", "batch ingest N articles", "manual catch-up batch"
- Cron is paused (ir-4 deploy in progress) but user wants fresh articles
- Testing pipeline at scale after fixes landed

## Safety Constraints

- Do NOT enable/resume daily-ingest cron — only manual run
- Kill old same-date tmux sessions first (script detects and exits 1)
- Never attach to tmux session (accidental Ctrl+C)
- Never `git pull`, `systemctl restart`, or modify code during run

## Full Step-by-Step

### 1. Kill Old Session

```bash
tmux kill-session -t daily-ingest-$(date +%Y%m%d) 2>/dev/null
```

### 2. Launch Batch

```bash
cd ~/OmniGraph-Vault && bash scripts/cron_daily_ingest.sh 50
```

Output: `tmux session daily-ingest-YYYYMMDD launched, log: /tmp/daily-ingest-YYYYMMDD-HHMM.log`

### 3. Wait 30s for Init

```bash
sleep 30 && tail -80 /tmp/daily-ingest-*.log
```

Expected: `N articles to process` + `[layer1] batch 0 n=30 ...`

### 4. Set Up Monitoring Cron

Create a self-cleaning cronjob that:
- Runs every 30 min
- Checks log + DB progress
- On completion: validates DB stable, kills zombie tmux, sends Telegram report, **deletes itself**

Cron prompt pattern:
```
Monitor daily-ingest batch progress. Log: /tmp/daily-ingest-YYYYMMDD-HHMM.log. DB: ~/OmniGraph-Vault/data/kol_scan.db.

1. tail -20 LOG — look for progress/errors
2. python3 -c "import sqlite3; ..." — query today's DB counts
3. grep -c "max-articles cap reached" LOG — detect completion

IF complete: wait 60s, re-query DB twice (30s apart), if stable → kill tmux, send Telegram report, self-delete cron.
IF not: send brief Telegram progress update.
```

### 5. Completion Detection

Any of:
- `max-articles cap reached (50)` in log
- `N articles processed` (pool exhausted before cap)

Then verify:
```bash
# DB counts stable across 30s
python3 -c "
import sqlite3, time
db = '/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db'
for _ in range(2):
    conn = sqlite3.connect(db)
    rows = conn.execute(\"SELECT source, status, COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime') GROUP BY source, status\").fetchall()
    conn.close()
    print(dict(rows))
    time.sleep(30)
"
```

### 6. Cleanup

```bash
tmux kill-session -t daily-ingest-$(date +%Y%m%d)
```

### 7. Report

Telegram format:
```
✅ daily-ingest done
ok: wechat=N rss=M
failed: X
skipped: Y

DB query: sqlite3 ~/OmniGraph-Vault/data/kol_scan.db "SELECT source,status,COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime') GROUP BY source,status"
Log: /tmp/daily-ingest-YYYYMMDD-HHMM.log
Grep: grep -E '(ok |failed|skipped|capped)' /tmp/daily-ingest-YYYYMMDD-HHMM.log
```

## Expected Timings

| Stage | Article Count | Wall Time |
|-------|:---:|---:|
| Layer 1 filter | 376 articles | ~2 min (30/batch, ~4s/batch) |
| Layer 2 + scrape + ainsert | ~25 pass (50% reject) | 3-5 hours (10-12 min/article) |
| Total (cap=50) | 50 attempted | ~4-5 hours |

## Environment

- WSL home: `/home/sztimhdd` (NOT `/home/hai`)
- `sqlite3` CLI may not be in PATH → use `python3 -c "import sqlite3;..."`
- Tmux session name: `daily-ingest-YYYYMMDD`
- Log path: `/tmp/daily-ingest-YYYYMMDD-HHMM.log`

## Known Failure Modes

| Failure | Cause | Fix |
|---------|-------|-----|
| Script exits 1 "session already exists" | Old tmux from earlier smoke | Kill old session (Step 1) |
| 0 candidates in pool | Layer 1 batched all rejects | Wait for next day's scan |
| Vision drain hang (10+ min after final article) | D-10.09 async vision worker doesn't exit | Zombie cleanup (Step 6) |
| Apify "max charged > 0" | Fixed in commit 5b22078 | Should not occur |
| Layer 2 timeout on large articles | Fixed in commit 2f6b316 | Should not occur |
