# Mystery Row Cleanup

Emergency procedure for when `ingestions` table claims `status='ok'` but the
LightRAG `doc_status` has no corresponding `status='processed'` entry — meaning
these articles were NEVER truly ingested into the knowledge graph despite the DB
claiming success.

## Reconciliation Severity Levels

**LOOSE reconcile** (key-presence only): checks if `wechat_<MD5[:10]>` exists in
`kv_store_doc_status.json` at all. **INSUFFICIENT.** A doc_id can exist with
`status='pending'` or `status='processing'` — meaning ainsert started but never
finished. This produces silent false-negatives (the reconcile says "matched" but
the article's graph data is incomplete and unusable).

**STRICT reconcile** (status='processed' only): checks if the doc_id exists AND
has `v.get('status') == 'processed'`. This is the ONLY valid gate. Use strict
for all cleanup decisions. The h09 hot-fix (commit 949e3f4) adds
`_verify_doc_processed_or_raise` to enforce this at the pipeline level.

**Full-history reconcile**: checks ALL ok wechat rows across all dates, not just
today. Run this periodically to find accumulated mystery rows from before the
per-day cleanup procedures were established. Script: see "Full-History Reconcilation"
section below.

## When This Happens

### Primary Cause: Ainsert Hang (graph building timeout)
- batch_ingest process hangs during LightRAG ainsert phase (graph building)
- `ingestions.status` set to 'ok' BEFORE ainsert completes
- Process dies/stuck → rows stay 'ok' but graph never gets the data
- **Risk:** if NOT cleaned up, cron sees status='ok' and skips these articles
  permanently → silent data loss

### Alternate Cause: LLM API Failure (DeepSeek 402 "Insufficient Balance")
- DeepSeek balance exhausted → ainsert LLM calls return HTTP 402
- LightRAG writes `doc_status='failed'` with `error_msg="Insufficient Balance"`
- h09 gate (`_verify_doc_processed_or_raise`) passes because status is 'failed'
  (not 'processing' or 'pending' — verification logic treats 'failed' as terminal,
  not retry-worthy)
- `ingestions.status` set to 'ok' despite doc never reaching LightRAG
- **Detection:** check `error_msg` field in `kv_store_doc_status.json` BEFORE reverting
- **Recovery:** recharge DeepSeek → revert mystery rows to `status='failed'` →
  verify candidate pool includes them (SKIP_REASON_VERSION_CURRENT gate doesn't
  filter `status='failed'`) → re-fire ingest

## Prerequisites

- Python venv at `~/OmniGraph-Vault/venv`
- DB: `~/OmniGraph-Vault/data/kol_scan.db`
- LightRAG doc_status: `~/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json`
- `.scratch/` directory exists: `mkdir -p ~/OmniGraph-Vault/.scratch`

## Step 1 — Reconcile (Calculate Mystery List)

Run independently — do NOT trust pre-computed ingest_id lists from other sessions.

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF' 2>&1 | tee .scratch/cleanup-$(date +%Y%m%d-%H%M%S)-step1-reconcile.log
import json, sqlite3, hashlib
from pathlib import Path
c = sqlite3.connect('data/kol_scan.db')
ok_today = c.execute("""
    SELECT i.id, i.article_id, a.url, i.ingested_at FROM ingestions i
    JOIN articles a ON i.article_id = a.id
    WHERE date(i.ingested_at) = date('now', 'localtime')
      AND i.status = 'ok' AND i.source = 'wechat'
    ORDER BY i.ingested_at
""").fetchall()
ds_path = Path.home() / '.hermes' / 'omonigraph-vault' / 'lightrag_storage' / 'kv_store_doc_status.json'
ds = json.loads(ds_path.read_text(encoding='utf-8'))
ds_keys = set(ds.keys())
mystery, matched = [], []
for ing_id, art_id, url, ts in ok_today:
    did = 'wechat_' + hashlib.md5(url.encode()).hexdigest()[:10]
    if did in ds_keys:
        matched.append((ing_id, art_id, ts, did))
    else:
        mystery.append((ing_id, art_id, ts, did))
print(f'TOTAL ok wechat today: {len(ok_today)}')
print(f'MATCHED in LightRAG  : {len(matched)}')
print(f'MYSTERY (revert-needed): {len(mystery)}')
print('MYSTERY ingest_ids: ' + ','.join(str(r[0]) for r in mystery))
print('MYSTERY article_ids: ' + ','.join(str(r[1]) for r in sorted(mystery, key=lambda x: x[1])))
PYEOF
```

**Expected output pattern:**
```
TOTAL ok wechat today: 41
MATCHED in LightRAG  : 15
MYSTERY (revert-needed): 26
MYSTERY ingest_ids: 2744,2956,...
MYSTERY article_ids: 80,585,...
```

**Decision:** If mystery=0, nothing to do. If mystery > 0, proceed to Step 2.

### STRICT Reconcile (status='processed' only — RECOMMENDED)

The loose reconcile above checks key-presence only. After h09, use STRICT:

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF'
import json, sqlite3, hashlib
from pathlib import Path
ds = json.loads((Path.home() / '.hermes' / 'omonigraph-vault' / 'lightrag_storage' / 'kv_store_doc_status.json').read_text(encoding='utf-8'))
processed_keys = {k for k, v in ds.items() if v.get('status') == 'processed'}
c = sqlite3.connect('data/kol_scan.db')
ok_today = c.execute("""
    SELECT i.id, i.article_id, a.url FROM ingestions i JOIN articles a ON i.article_id = a.id
    WHERE date(i.ingested_at) = date('now', 'localtime') AND i.status = 'ok' AND i.source = 'wechat'
      AND time(i.ingested_at) > '08:55:00'
""").fetchall()
mystery = [(ing_id, art_id) for ing_id, art_id, url in ok_today
           if 'wechat_' + hashlib.md5(url.encode()).hexdigest()[:10] not in processed_keys]
print(f'STRICT reconcile (status=processed only):')
print(f'  ingestions ok today:  {len(ok_today)}')
print(f'  fully processed:      {len(ok_today) - len(mystery)}')
print(f'  MYSTERY (revert):     {len(mystery)}')
print(f'  ingest_ids:           {[r[0] for r in mystery]}')
print(f'  article_ids:          {sorted([r[1] for r in mystery])}')
PYEOF
```

**Why strict matters:** On 2026-05-10, a loose reconcile claimed 4 matched / 0 mystery.
The strict reconcile revealed all 4 had status='pending'/'processing' — false ok rows
that would have been silently lost. The strict check caught what loose missed.

### Full-History Reconciliation

Checks ALL ok wechat rows ever, not just today. Run this after discovering that
mystery rows accumulated over weeks:

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF'
import json, sqlite3, hashlib
from pathlib import Path
ds = json.loads((Path.home() / '.hermes' / 'omonigraph-vault' / 'lightrag_storage' / 'kv_store_doc_status.json').read_text(encoding='utf-8'))
processed_keys = {k for k, v in ds.items() if v.get('status') == 'processed'}
c = sqlite3.connect('data/kol_scan.db')
all_ok = c.execute("""
    SELECT i.id, i.article_id, a.url, date(i.ingested_at)
    FROM ingestions i JOIN articles a ON i.article_id = a.id
    WHERE i.status = 'ok' AND i.source = 'wechat'
    ORDER BY i.ingested_at
""").fetchall()
mystery = [(ing_id, art_id, date_, did) for ing_id, art_id, url, date_ in all_ok
           if (did := 'wechat_' + hashlib.md5(url.encode()).hexdigest()[:10]) not in processed_keys]
by_date = {}
for _, _, date_, _ in mystery:
    by_date[date_] = by_date.get(date_, 0) + 1
print(f"Total ok wechat (all time): {len(all_ok)}")
print(f"Verified processed:          {len(all_ok) - len(mystery)}")
print(f"MYSTERY (never processed):   {len(mystery)}")
print(f"By date:")
for d in sorted(by_date.keys()):
    print(f"  {d}: {by_date[d]} rows")
print(f"ingest_ids: {[r[0] for r in mystery]}")
print(f"article_ids: {sorted([r[1] for r in mystery])}")
PYEOF
```

**Production finding (2026-05-10):** 76 of 139 ok wechat rows (55%) were mystery,
dating back to April 27 (day 1). Largest single-day loss: April 29 (55 rows).

## Step 2 — Backup DB + Kill Process

```bash
TS=$(date +%Y%m%d-%H%M%S)
# Backup
cp ~/OmniGraph-Vault/data/kol_scan.db ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mystery-revert-${TS}
ls -la ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mystery-revert-${TS}

# Verify size >= 16MB
# Kill tmux session
tmux kill-session -t daily-ingest-$(date +%Y%m%d) 2>&1

# Verify clean
tmux ls 2>&1
ps aux | grep -v grep | grep -E "batch_ingest|cron_daily_ingest" || echo "(clean)"
```

**Guard:** backup file MUST be >= 16MB. If < 10MB, STOP — the backup is incomplete.

## Step 3 — UPDATE Mystery Rows

**CRITICAL:** Use the ingest_ids from YOUR Step 1 output, not hardcoded values.

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF' 2>&1 | tee .scratch/cleanup-$(date +%Y%m%d-%H%M%S)-step3-update.log
import sqlite3
# REPLACE with YOUR step-1 computed IDs
MYSTERY_IDS = [...]  # <-- paste your list here

c = sqlite3.connect('data/kol_scan.db')
# pre-mutation snapshot
pre = c.execute(f"SELECT id, article_id, status FROM ingestions WHERE id IN ({','.join('?' * len(MYSTERY_IDS))})", MYSTERY_IDS).fetchall()
print(f'PRE: rows found = {len(pre)} (expected {len(MYSTERY_IDS)})')
assert len(pre) == len(MYSTERY_IDS), f'MISSING ROWS'
assert all(r[2] == 'ok' for r in pre), f'NON-OK ROWS in mystery list'

# mutation
res = c.execute(f"UPDATE ingestions SET status = 'failed' WHERE id IN ({','.join('?' * len(MYSTERY_IDS))}) AND status = 'ok'", MYSTERY_IDS)
c.commit()
print(f'UPDATE: {res.rowcount} rows changed')

# post snapshot
post = c.execute(f"SELECT status, COUNT(*) FROM ingestions WHERE id IN ({','.join('?' * len(MYSTERY_IDS))}) GROUP BY status", MYSTERY_IDS).fetchall()
print(f'POST: {post} (expect [("failed", {len(MYSTERY_IDS)})])')
PYEOF
```

**Expected:**
```
PRE: rows found = 26 (expected 26)
UPDATE: 26 rows changed
POST: [('failed', 26)]
```

Any assert failure → STOP. Restore from backup:
```bash
cp ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mystery-revert-* ~/OmniGraph-Vault/data/kol_scan.db
```

## Step 4 — Verify Cleanup

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF' 2>&1 | tee .scratch/cleanup-$(date +%Y%m%d-%H%M%S)-step4-verify.log
import json, sqlite3, hashlib
from pathlib import Path
c = sqlite3.connect('data/kol_scan.db')
ok_today = c.execute("""
    SELECT i.id, a.url FROM ingestions i JOIN articles a ON i.article_id = a.id
    WHERE date(i.ingested_at) = date('now', 'localtime')
      AND i.status = 'ok' AND i.source = 'wechat'
""").fetchall()
ds = json.loads((Path.home() / '.hermes' / 'omonigraph-vault' / 'lightrag_storage' / 'kv_store_doc_status.json').read_text(encoding='utf-8'))
ds_keys = set(ds.keys())
mystery_post = [r[0] for r in ok_today if 'wechat_' + hashlib.md5(r[1].encode()).hexdigest()[:10] not in ds_keys]
print(f'POST-cleanup: ok wechat today = {len(ok_today)} (expect {len(matched)})')
print(f'POST-cleanup: mystery ingest_ids = {mystery_post} (expect [])')
print(f'POST-cleanup: today by status:')
for r in c.execute("SELECT status, COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime') AND source='wechat' GROUP BY status").fetchall():
    print(f'  {r}')
PYEOF
```

**Expected:**
```
POST-cleanup: ok wechat today = 15
POST-cleanup: mystery ingest_ids = []
POST-cleanup: today by status:
  ('failed', 29)
  ('ok', 15)
  ('skipped', 56)
  ('skipped_ingested', 4)
```

## What NOT to Do

- ❌ Don't vacuum / rebuild LightRAG storage (graph is fine, don't touch it)
- ❌ Don't delete backup files (keep ≥ 7 days)
- ❌ Don't try to manually re-insert mystery articles into the graph
- ❌ Don't resume daily-ingest cron — let tomorrow's cron naturally retry

## Recovery Path

After cleanup, the 26 reverted articles will be `status='failed'`. Tomorrow's
cron will see them as not-yet-ingested and re-process them through the normal
Layer1→Layer2→ainsert pipeline. This is the correct path — no manual re-insertion.
