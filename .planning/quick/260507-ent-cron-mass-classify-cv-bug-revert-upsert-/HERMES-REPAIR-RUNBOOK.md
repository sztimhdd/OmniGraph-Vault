# Hermes CV mass-classify repair runbook

**Quick:** 260507-ent (2026-05-07)
**Origin commit:** 428b16f (fix(classify): revert UPSERT to ON CONFLICT(article_id, topic))
**Target:** Hermes production WSL2 (ohca.ddns.net)
**Operator:** user (SSH from local; agent does NOT SSH)

---

## What this runbook does

Repairs the 2026-05-07 08:29 ADT cron mass-classify incident on Hermes:

1. Pull the fix commit (428b16f) onto the deployed code.
2. Drop the `idx_classifications_article_id` unique index that migration 004
   added (migration 005).
3. Re-classify all candidate articles from the last 30 days so the corrupted
   `topic='CV'` rows get replaced with correct multi-topic rows.
4. Smoke-test the ingest cron with the topic filter
   `agent,hermes,openclaw,harness` — must yield candidates this time.

Total wall-clock: ~30-90 minutes (the bulk is re-classify of 30 days × ~20-30 articles/day).

---

## Pre-flight

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net
cd ~/OmniGraph-Vault
git pull --ff-only
# Expected: HEAD = 428b16f or newer
git log --oneline -3
```

If `git pull --ff-only` fails because Hermes has divergent local commits,
**stop and triage with the user** — do NOT force-pull. Hermes occasionally
holds untracked local edits (CLAUDE.md "Remote Hermes Deployment" section).

---

## Step 1: Pause the classify cron

The classify cron must NOT run while migration 005 + re-classify is in
progress, otherwise it could re-write the CV rows over the repaired data
mid-run.

```bash
# Inspect the current cron entries to find the classify cron line
crontab -l | grep -i classify

# Comment it out (preserve history)
crontab -l | sed 's|^\(.*batch_classify_kol\.py.*\)|# QUICK 260507-ent paused \1|' | crontab -
crontab -l | grep -i classify  # verify the line is commented
```

If Hermes uses a non-cron scheduler (systemd timer / Hermes agent task),
disable that mechanism instead. The user knows the deployed scheduler
shape.

---

## Step 2: Backup the DB

**CRITICAL — per CLAUDE.md Lessons 2026-05-06 #2.** Backup the file before
any destructive DDL.

```bash
cp data/kol_scan.db data/kol_scan.db.backup-pre-mig005-$(date +%Y%m%d-%H%M%S)
ls -la data/kol_scan.db.backup-pre-mig005-* | tail -3
```

The backup must exist on disk before proceeding. If the rollback path is
needed: `cp data/kol_scan.db.backup-pre-mig005-<timestamp> data/kol_scan.db`.

---

## Step 3: Deploy migration 005

```bash
sqlite3 data/kol_scan.db < migrations/005_drop_article_id_unique_index.sql
```

Verify the index is gone:

```bash
venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/kol_scan.db')
print('=== indexes on classifications post-mig-005 ===')
for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='classifications'\").fetchall(): print(r)
print()
print('Expected: idx_classifications_article_id is GONE')
"
```

Expected output: a list of indexes that does NOT include
`idx_classifications_article_id`. The auto-index from `UNIQUE(article_id, topic)`
(`sqlite_autoindex_classifications_*`) and any topic/article indexes from prior
schemas should remain.

If the migration fails or the index is still present, **stop and rollback**:
```bash
cp data/kol_scan.db.backup-pre-mig005-<timestamp> data/kol_scan.db
```

---

## Step 4: Re-classify (multi-topic, 30 days back)

The cron runs `batch_classify_kol.py` once per topic — sequentially for the
5 topics in the production filter list. Repeat that pattern manually for
the 30-day window.

```bash
source venv/bin/activate

# Optional: unset OMNIGRAPH_LLM_TIMEOUT_SEC if a previous session set a
# non-default value.
unset OMNIGRAPH_LLM_TIMEOUT_SEC

# Run each topic in sequence. --days-back is NOT a real CLI flag; the
# original buggy cron pre-filtered with batch_scan_kol.py first, so the
# operative date filter lives in scan, not classify. To replay the cron's
# net effect, re-run the WHOLE classify pipeline (all unclassified or
# CV-corrupted articles in the candidate pool):
for TOPIC in Agent LLM RAG NLP CV; do
  echo "=== classify --topic ${TOPIC} starting $(date -Iseconds) ==="
  venv/bin/python batch_classify_kol.py --topic "${TOPIC}" --min-depth 2 \
    2>&1 | tee /tmp/cv-repair-reclassify-${TOPIC}-$(date +%Y%m%d-%H%M%S).log
done
```

**Why no `--days-back`:** as of 428b16f the CLI does not have a `--days-back`
flag (only `--topic`, `--min-depth`, `--classifier`, `--dry-run`). The CV
mass-classify wrote 'CV' across the entire candidate pool surfaced by
batch_scan_kol.py, so the repair must touch the same pool. If the operator
has reason to scope down (e.g. "only repair last 7 days"), they need to
manually wipe the corrupted rows for that window first:

```bash
# OPTIONAL targeted wipe — only run if scoping the repair
sqlite3 data/kol_scan.db "DELETE FROM classifications WHERE topic='CV' AND classified_at >= datetime('now', '-7 days')"
```

---

## Step 5: Verify

```bash
venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/kol_scan.db')
print('=== topic distribution post-repair ===')
for r in c.execute('SELECT topic, COUNT(*) FROM classifications GROUP BY topic ORDER BY 2 DESC LIMIT 20').fetchall(): print(r)
print()
print('=== articles with multiple topic rows (should be many post-repair) ===')
print(c.execute('SELECT COUNT(*) FROM (SELECT article_id FROM classifications GROUP BY article_id HAVING COUNT(DISTINCT topic) > 1)').fetchone()[0], 'articles have >1 topic row')
"
```

**Expected outcome:**
- `topic='CV'` count is no longer overwhelming (was 653 / 100% pre-fix).
- Several topics each have hundreds of rows (Agent, LLM, RAG, NLP all
  populated).
- Many articles have >1 topic row (the multi-topic schema is restored).

If `topic='CV'` is still ≥ 90% of rows, **stop**. Either re-classify did not
produce non-CV labels, or something is still wrong with the SQL. Triage
with the user.

---

## Step 6: Re-enable the classify cron

```bash
# Restore the cron line by uncommenting it
crontab -l | sed 's|^# QUICK 260507-ent paused \(.*\)|\1|' | crontab -
crontab -l | grep -i classify  # verify the line is back, no leading #
```

---

## Step 7: Smoke ingest

Confirm the ingest cron now finds candidates with the production topic
filter:

```bash
venv/bin/python batch_ingest_from_spider.py \
  --from-db --topic-filter agent,hermes,openclaw,harness --min-depth 2 \
  --max-articles 3 \
  2>&1 | tee /tmp/cv-repair-smoke-$(date +%Y%m%d-%H%M%S).log
```

Expected: ≥ 1 candidate found, attempts ingest. If 0 candidates, either:
- The repair didn't surface enough non-CV topics to match the filter — go
  back to Step 4 and broaden the topic re-classify pass; OR
- The topic filter literals don't match the LLM's actual topic strings
  (e.g. classify produced "AI Agent" not "agent"). Inspect the topic
  distribution from Step 5 to confirm matching.

---

## Rollback (if anything goes wrong)

At any step:

```bash
# Restore DB
ls -la data/kol_scan.db.backup-pre-mig005-* | tail -1   # find latest
cp data/kol_scan.db.backup-pre-mig005-<timestamp> data/kol_scan.db

# Restore cron (if Step 1 was run)
crontab -l | sed 's|^# QUICK 260507-ent paused \(.*\)|\1|' | crontab -

# Roll code back to pre-fix
git log --oneline -5
git reset --hard <previous-good-sha>   # ⚠️ destructive — confirm with user
```

---

## Post-repair: tomorrow's 06:00 ADT cron

After this runbook completes successfully, the next 06:00 ADT classify cron
will run with the fixed SQL and accumulate new (article_id, topic) rows
correctly. The downstream ingest cron at 08:29 ADT should then find
candidates matching the filter.

If tomorrow's cron also returns 0 candidates, the issue is NOT the
classification SQL — it's a candidate-pool problem (topic-filter literal
mismatch, scan finding nothing new, etc.). At that point reroute to the
v3.5 candidate-pool refactor (.planning/PROJECT-Ingest-Refactor-v3.5.md).
