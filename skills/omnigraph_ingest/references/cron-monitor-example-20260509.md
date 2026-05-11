# Cron Monitor Example — 2026-05-09

Live production example of monitoring an overlapping cron tick (session already
running when the cron job tried to launch).

## Situation

Previous tick's `batch_ingest_from_spider.py --from-db --max-articles 10` was
still running (~3.5h in). The cron tried to launch a new session with
`bash scripts/cron_daily_ingest.sh 10` and got exit code 1:

```
ERROR: session daily-ingest-20260509 already running
```

## Monitor Steps

### 1. Check tmux session

```
$ tmux ls | grep daily-ingest
daily-ingest-20260509: 1 windows (created Sat May  9 16:26:38 2026)
```

### 2. Find and tail the latest log file

The cron script names logs as `/tmp/daily-ingest-YYYYMMDD-HHMM.log`:

```
$ ls -lt /tmp/daily-ingest-20260509*.log | head -1
/tmp/daily-ingest-20260509-1626.log  147.8K
```

Two log files existed — one from an earlier attempt (1527, 245K) and the
current run (1626, 148K). Always pick the latest.

### 3. Read log tail

Log head showed the full pipeline chain:

```
16:27:02 INFO __main__ 376 articles to process (scrape-first) for topics []
16:27:07 INFO __main__ [layer1] batch 0 n=30 candidate=30 reject=0 null=0 wall_ms=4204
...
16:28:05 INFO __main__ [layer1] total inputs=376 candidates=206 (per-article loo...
```

376 input → 206 candidates after Layer1 classification. Then Layer2 ingest:

```
16:28:12 INFO __main__ [1/206] [AINLP] 李宏毅老师详解 Harness Engineering
...
16:49:45 INFO __main__ [20/206] [PaperWeekly] Harness开始自己进化了...
16:50:03 INFO __main__ [layer2] batch 2 n=5 ok=3 reject=2 null=0 wall_ms=17914
```

Progress indicator: `[N/206]` = article N of 206 through Layer2 pipeline.
Layer2 batches process 5 articles each with ok/reject/null breakdown.

Image vision cascade also visible:

```
16:52:06 INFO lib.vision_cascade image_id=img_006 provider=siliconflow
    attempt=1/3 result=200 latency_ms=11556 desc_chars=621
```

### 4. Query SQLite ingestion count

The ingest script uses `~/OmniGraph-Vault/data/kol_scan.db` (NOT the
0B stub at `~/OmniGraph-Vault/kol_scan.db`). Use Python since sqlite3 CLI
may not be installed:

```python
import sqlite3
conn = sqlite3.connect('/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db')
cur = conn.execute(
    "SELECT status, COUNT(*) FROM ingestions"
    " WHERE date(ingested_at) = date('now', 'localtime')"
    " GROUP BY status"
)
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]}')
```

Output on 2026-05-09:

```
ok: 7
skipped: 1547
skipped_ingested: 4
```

**Interpretation:**
- `skipped: 1547` — Layer1 classification rejections (articles filtered as
  irrelevant during the classifier pass). This is the bulk of the rows.
- `ok: 7` — articles successfully ingested into LightRAG graph
- `skipped_ingested: 4` — articles that passed Layer1 but were deemed
  redundant/low-value during Layer2
- Total unique articles processed through Layer2: 11/206 candidates
- Remaining: ~195 still queued

### 5. Graph state (from log)

```
INFO: [] Writing graph with 7206 nodes, 9325 edges
```

This gets updated incrementally as new articles are added.

## Completion Estimate

At ~1 article per 2 minutes (including SiliconFlow vision processing at
~9-12s/image), expect:
- 195 remaining / ~2 min per article ≈ 6.5 hours remaining
- Total run time: ~10 hours for 206 articles
- This is consistent with the "~4-5 min per article" rate on earlier batches

## Pitfalls Verified

| Pitfall | Status |
|---------|--------|
| `sqlite3` CLI not installed | ✅ Used python3 correctly |
| MCP SQLite points at wrong DB | ✅ Real DB at data/kol_scan.db |
| Two log files for same date | ✅ Picked latest by timestamp |
| Script exit 1 (session exists) | ✅ Correctly switched to monitor mode |
