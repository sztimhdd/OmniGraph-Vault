# h09 Smoke Test — Contract Reconciliation

Repeatable procedure for verifying that a hot-fix actually prevents mystery rows.
Run BEFORE the next cron window if a fix touching the ainsert→ingestion boundary
was deployed.

## When to Run

- After deploying any commit that touches `ingest_wechat.py` (especially `_verify_doc_processed_or_raise`)
- After mig 009 (skip_reason_version) or any schema change that affects ingestion status tracking
- As a pre-cron sanity check when the pipeline has been modified

## What It Tests

The core contract: `ingestions.status='ok'` MUST equal `LightRAG doc_status='processed'`.
Any mismatch = mystery row = the fix didn't work.

## Procedure (4 steps, ~15-25 min wall clock)

### Step 1 — Baseline

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate
echo "=== HEAD ==="; git log --oneline -3
echo "=== today's ingestions baseline (BEFORE smoke) ==="
python -c "
import sqlite3
c = sqlite3.connect('data/kol_scan.db')
print('today total:', c.execute(\"SELECT COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime')\").fetchone()[0])
print('today by status:', c.execute(\"SELECT status, COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime') GROUP BY status\").fetchall())
"
echo "=== LightRAG processed doc count baseline ==="
python -c "
import json
from pathlib import Path
p = Path.home() / '.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json'
data = json.loads(p.read_text())
processed = [k for k,v in data.items() if v.get('status')=='processed']
print('total processed:', len(processed))
"
```

Record: T_before_total, T_before_ok, T_before_failed, T_before_processed.

### Step 2 — Trigger smoke

```bash
cd ~/OmniGraph-Vault && bash scripts/cron_daily_ingest.sh 3
```

Records: tmux session name, log path. max-articles=3 ensures fast execution.

### Step 3 — Poll for completion

```bash
for i in 1 2 3 4 5 6; do
    if tmux has-session -t "daily-ingest-$(date +%Y%m%d)" 2>/dev/null; then
        echo "[t=$((i*5))min] tmux still running"
        sleep 300
    else
        echo "[t=$((i*5))min] tmux ENDED"
        break
    fi
done
```

**Guard:** If 30min elapsed and still running, kill and report (likely edge case).
Do NOT kill prematurely — the ainsert Phase 3 graph flush takes ~2-3 min at the end.

### Step 4 — Contract reconciliation

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate
python << 'PY'
import sqlite3, json, hashlib
from pathlib import Path

c = sqlite3.connect('data/kol_scan.db')
ok_today = c.execute("""
    SELECT i.article_id, a.url
    FROM ingestions i JOIN articles a ON i.article_id=a.id
    WHERE date(i.ingested_at)=date('now','localtime') AND i.status='ok'
""").fetchall()
print(f"ingestions=ok today: {len(ok_today)} rows")

ds_path = Path.home() / '.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json'
ds = json.loads(ds_path.read_text())

mystery = []
processed_ok = []
for art_id, url in ok_today:
    did = f"wechat_{hashlib.md5(url.encode()).hexdigest()[:10]}"
    status = ds.get(did, {}).get('status', '<MISSING>')
    if status == 'processed':
        processed_ok.append((art_id, did))
    else:
        mystery.append((art_id, did, status))

print(f"PROCESSED matched: {len(processed_ok)}")
print(f"MYSTERY: {len(mystery)}")
for m in mystery:
    print(f"  art_id={m[0]} doc_id={m[1]} actual_status={m[2]}")

if mystery:
    print("VERDICT: FAIL — h09 did NOT fully prevent mystery rows")
elif processed_ok:
    print("VERDICT: PASS — all ingestions=ok rows have status=processed")
else:
    print("VERDICT: INCONCLUSIVE — no new ok rows (all rejected by Layer1/Layer2)")
PY

echo "=== h09 helper invocation count in log ==="
LOG=$(ls -t /tmp/daily-ingest-*.log | head -1)
echo "log: $LOG"
echo "PROCESSED verification PASS:"
grep -c "PROCESSED verification" "$LOG" 2>/dev/null || echo 0
echo "h09 raise events:"
grep -c "post-ainsert PROCESSED verification failed" "$LOG" 2>/dev/null || echo 0
```

## Verdict Criteria

| Verdict | Condition | Action |
|---------|-----------|--------|
| ✅ PASS | mystery=0, processed_ok >= 1 | Fix works. Safe for cron. |
| ❌ FAIL | mystery >= 1 | Fix incomplete. Investigate actual_status. Revert to 'failed' per mystery-row-cleanup.md. |
| ⚠️ INCONCLUSIVE | mystery=0 AND processed_ok=0 | Candidates all rejected by Layer1/Layer2. h09 was never triggered. Run again with different pool or accept risk. |

## STOP Gates

- ❌ Don't SSH-transcribe external data — run commands locally
- ❌ Don't run cleanup_stuck_docs.py — tomorrow's cron auto-runs it
- ❌ Don't mutate ingestions or kv_store_doc_status during verification
- ❌ Don't fabricate log line numbers or grep counts — cite real paths and real numbers
- ❌ Don't force-quit tmux unless >30min elapsed
- ✅ FAIL is a valid signal — surface it, don't hide it

## h09b Variant — Production Load Test (60s Budget)

When h09b (commit 099712d: 6s→60s budget) is deployed, verify with N=10
varied-load run instead of N=3 smoke. This validates the 60s budget handles
production-scale articles with varied body lengths and image counts.

### Pre-Flight — Full Timeout Chain Verification

BEFORE launching, verify the entire timeout chain:

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate
echo "=== h09b budget ==="
python -c "import ingest_wechat as i; print(f'RETRIES={i.PROCESSED_VERIFY_MAX_RETRIES} BACKOFF={i.PROCESSED_VERIFY_BACKOFF_S}s budget={i.PROCESSED_VERIFY_MAX_RETRIES * i.PROCESSED_VERIFY_BACKOFF_S}s')"
echo "=== env overrides ==="
grep -E "^OMNIGRAPH_PROCESSED_RETRY|^OMNIGRAPH_PROCESSED_BACKOFF|^HERMES_CRON_TIMEOUT" ~/.hermes/.env || echo "(using defaults → 60s budget)"
```

| Timeout | Default | Governed by | Risk |
|---------|---------|-------------|------|
| Hermes activity | 600s | `HERMES_CRON_TIMEOUT` env | ✅ tmux bypass |
| outer ingest_article | 1500s | `batch_ingest` `effective_timeout` | ✅ |
| h09b PROCESSED gate | 60s | `OMNIGRAPH_PROCESSED_RETRY × BACKOFF` | ⚠️ long-tail |
| LightRAG LLM | 600s | `LIGHTRAG_LLM_TIMEOUT` | ✅ |
| Vision drain | 30s | hardcoded | ⚠️ large image sets |
| Apify scrape | ~120s | per-call | ✅ |
| UA scrape | ~75s | per-call | ✅ |

### h09b Trigger

```bash
cd ~/OmniGraph-Vault && bash scripts/cron_daily_ingest.sh 10
```

Expected wall clock: 50-100 min (N=10 + cap bug expansion). Do NOT poll —
return immediately after launch confirmation. Reconcile after tmux exits.

### h09b Verification

Same Step 4 contract reconciliation as main procedure. Additional checks:

```bash
# All today's ok rows — verify each individually
cd ~/OmniGraph-Vault && source venv/bin/activate
python << 'PY'
import sqlite3, json, hashlib
from pathlib import Path
c = sqlite3.connect('data/kol_scan.db')
ok_today = c.execute("""
    SELECT i.id, i.article_id, a.url FROM ingestions i JOIN articles a ON i.article_id=a.id
    WHERE date(i.ingested_at)=date('now','localtime') AND i.status='ok'
    ORDER BY i.id
""").fetchall()
ds = json.loads((Path.home() / '.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json').read_text())
processed_keys = {k for k, v in ds.items() if v.get('status') == 'processed'}
mystery = 0
for ing_id, art_id, url in ok_today:
    did = f"wechat_{hashlib.md5(url.encode()).hexdigest()[:10]}"
    in_lr = did in processed_keys
    print(f"  ingest={ing_id} art={art_id} {'✅' if in_lr else '❌ MYSTERY'} doc={did}")
    if not in_lr:
        mystery += 1
print(f"\nmystery: {mystery}/{len(ok_today)}")
PY
```

### Production Record

2026-05-10: h09b N=10 run — 10/10 articles passed ainsert, 0 mystery.
Combined with earlier smoke (4/4), achieved 14/14 clean — first zero-mystery
production run in OmniGraph-Vault history. 60s budget was sufficient for all
14 articles including the 8-chunk 3269MB RSS Hermes Agent article.
