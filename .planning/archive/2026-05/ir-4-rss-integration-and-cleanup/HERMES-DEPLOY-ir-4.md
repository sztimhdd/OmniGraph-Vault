# Hermes deploy runbook — Phase ir-4

**Target:** Hermes production (SSH per `~/.claude/projects/.../memory/hermes_ssh.md`).
**Code state:** local main HEAD = ir-4 W5 close-out commit (NOT pushed yet at
local-tip-time of writing). Operator pulls after the W5 push lands.

**Deploy contract:**
- ir-4 ships **all 5 commits as one main update** (W1+W2+W3+W4+W5).
- migration 008 is the **only schema change** (single rebuild on `ingestions`).
- Operator must remove the existing `rss-classify` cron job manually because
  W3's `register_phase5_cron.sh` edit is idempotent for adds, not removes.

---

## Pre-flight — read before running anything

1. **Backup** the production DB before applying migration 008. The rebuild
   is reversible only by restoring this backup.
2. **Pause** the daily-ingest cron during migration to avoid a race where
   cron picks up the partly-rebuilt schema.
3. **Verify** local main HEAD lines up with what you intend to deploy.

---

## Step 1 — SSH + git pull

```bash
ssh -p <port> <user>@<host>      # connection details from project memory
cd ~/OmniGraph-Vault
git fetch origin
git log --oneline origin/main..HEAD   # MUST be empty — Hermes side has no local commits
git pull --ff-only
```

Expected new commits (5):

```
<W5 hash>  docs(ir-4 W5): close-out — PLAN dir + HERMES-DEPLOY + CLOSURE + STATE/ROADMAP
9ff330d   refactor(ir-4 W4): retire enrichment/rss_ingest.py + step_7 RSS branch + harness rss hint (LF-5.1)
4cc3757   refactor(ir-4 W3): retire enrichment/rss_classify.py + step_2 + cron registration (LF-5.2)
df495c8   feat(ir-4 W2): _needs_scrape helper + _persist_scraped_body source dispatch (LF-4.4)
5d943f8   feat(ir-4 W1): migration 008 dual-source ingestions + UNION ALL candidate SQL (LF-4.4)
```

If anything diverges, STOP and reconcile before proceeding.

---

## Step 2 — Pause daily-ingest cron

```bash
hermes cron list | grep daily-ingest    # capture the cron ID
hermes cron pause 2b7a8bee53e0          # known ID from prior session memory; verify with cron list
```

Expected output: cron entry shows `paused`.

---

## Step 3 — Backup production DB

```bash
cp ~/OmniGraph-Vault/data/kol_scan.db \
   ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mig008-$(date +%Y%m%d-%H%M%S)
ls -la ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mig008-*
```

The backup file is the rollback target if migration 008 surfaces any issue.

---

## Step 4 — Apply migration 008

```bash
cd ~/OmniGraph-Vault
source venv/bin/activate
python migrations/008_ingestions_dual_source.py data/kol_scan.db
```

Expected output (verbatim format from local validation):

```
pre-rebuild row count: <N>
applied: <N> rows migrated, all source='wechat'
  CHECK status preserved (6 values)
  CHECK source added: ('wechat', 'rss')
  FK to articles(id) dropped (dual-source semantics at app layer)
  UNIQUE(article_id) replaced with UNIQUE(article_id, source)
  index idx_ingestions_article_source created
  integrity_check: ok; foreign_key_check: clean
```

Non-zero exit → STOP, restore backup, report.

### Verify the rebuild

```bash
python -c "
import sqlite3
c = sqlite3.connect('data/kol_scan.db')
print('schema:', c.execute(\"SELECT sql FROM sqlite_master WHERE name='ingestions'\").fetchone()[0])
print('rows:', c.execute('SELECT COUNT(*), source FROM ingestions GROUP BY source').fetchall())
print('integrity:', c.execute('PRAGMA integrity_check').fetchall())
print('fk:', c.execute('PRAGMA foreign_key_check').fetchall())
"
```

Expected: source column visible in CREATE TABLE; all rows source='wechat'
(production has not yet ingested any RSS via the new pipeline);
integrity:[(ok,)]; fk:[].

### Idempotency double-check

Re-run the migration:

```bash
python migrations/008_ingestions_dual_source.py data/kol_scan.db
```

Expected: `SKIP: source column already exists, skipping all 5 ops`.

---

## Step 5 — Remove the legacy `rss-classify` cron job

The W3 retirement deleted `enrichment/rss_classify.py` from git. The cron
job, however, was registered in Hermes's runtime store at `0 7 * * *` and
still tries to invoke the now-deleted file. The W3
`scripts/register_phase5_cron.sh` edit is idempotent for adds, not removes;
operator must remove the live job:

```bash
hermes cron list | grep rss-classify    # capture ID
hermes cron remove <rss-classify-id>
hermes cron list | grep rss-classify    # verify gone
```

Expected: empty output after `remove`.

---

## Step 6 — Count expected post-deploy candidates

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate
python -c "
import sqlite3, sys
sys.path.insert(0, '.')
from batch_ingest_from_spider import _build_topic_filter_query
sql, params = _build_topic_filter_query([])
c = sqlite3.connect('data/kol_scan.db')
n_kol = c.execute(f'SELECT COUNT(*) FROM ({sql}) WHERE source=\"wechat\"', params).fetchone()[0]
n_rss = c.execute(f'SELECT COUNT(*) FROM ({sql}) WHERE source=\"rss\"', params).fetchone()[0]
print(f'KOL: {n_kol}, RSS: {n_rss}, total: {n_kol+n_rss}')
"
```

Local validation showed KOL=149 + RSS=1600 = 1749 candidates against the
local snapshot. Production numbers will differ — capture them as the
day-0 baseline.

---

## Step 7 — Manual smoke (max=2)

Same pattern as ir-1 / ir-2 deploys: run an explicit cron-equivalent batch
with a tight cap before resuming the cron schedule.

```bash
cd ~/OmniGraph-Vault && bash scripts/cron_daily_ingest.sh 2
```

Expected:
- Two articles processed end-to-end (Layer 1 → Layer 2 → ainsert).
- DB shows two `ingestions(status='ok')` rows. At least one should have
  `source='rss'` because the FIFO `ORDER BY source DESC, id` puts KOL
  first, but RSS pool is much larger so the second slot likely lands on
  an RSS row depending on the 149 KOL backlog.
- Verify:

```bash
sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
  "SELECT id, article_id, source, status, ingested_at
   FROM ingestions WHERE date(ingested_at) = date('now')
   ORDER BY id DESC LIMIT 5"
```

If both rows are source='wechat': fine — the KOL backlog is being burned
down first. RSS will start landing once the KOL queue thins.

If any error path is hit (`failed`, `skipped` with unexpected reason): STOP,
inspect the journal log, report.

---

## Step 8 — Resume daily-ingest cron

```bash
hermes cron resume 2b7a8bee53e0
hermes cron list | grep daily-ingest    # verify state=active
```

The cron will fire on its scheduled cadence (next 06:00 ADT or similar).

---

## Step 9 — Backlog drain plan (operator-paced, 1 week)

Post-ir-4 the candidate pool is ~149 KOL + ~1600 RSS articles. The default
`daily-ingest` cron runs `--max-articles 10` — that's 150 days at 1 batch/day.

**Recommended catch-up cadence (first week):**
- Day 1: run `bash scripts/cron_daily_ingest.sh 50` once, off-peak. Wall-clock
  ~3-4h depending on scrape + ainsert mix.
- Day 2-7: same — 1 extra burst per day, 50 articles each.
- After 7 days: ~350 articles ingested, ~1400 remaining. Ratchet down to
  `--max-articles 30` per day for the rest of the month, then back to 10.

Layer 1 + Layer 2 typically reject ~40-50% of articles, so the actual ainsert
count is roughly half of the candidate count. The backlog drains in 4-5 weeks
at the recommended cadence, faster if the operator schedules more bursts.

---

## Step 10 — Day-1 audit (24h after Step 8)

```bash
sqlite3 ~/OmniGraph-Vault/data/kol_scan.db <<'EOF'
.headers on
.mode column
SELECT source, status, COUNT(*) FROM ingestions
 WHERE date(ingested_at) = date('now')
 GROUP BY source, status;
EOF
```

Expected shape:

| source | status | count |
|---|---|---|
| wechat | ok | <K1> |
| wechat | skipped | <K2> |
| rss    | ok | <R1> |
| rss    | skipped | <R2> |

If `rss` rows are missing entirely, something gated all RSS candidates —
inspect the cron run log and Layer 1 verdicts on a sample of rss_articles.

---

## Failure / Rollback

### Migration 008 fails or integrity_check non-ok

```bash
hermes cron resume 2b7a8bee53e0   # do NOT leave cron paused indefinitely
cp ~/OmniGraph-Vault/data/kol_scan.db.backup-pre-mig008-<ts> \
   ~/OmniGraph-Vault/data/kol_scan.db
git revert <W1 hash>..<W5 hash>   # or reset to pre-W1 main if push hasn't happened
```

Then report the failure mode + integrity_check output.

### Dual-source SQL returns 0 candidates in production

If Step 6 shows `KOL=0, RSS=0` despite known un-ingested rows:

1. Verify migration 008 actually ran (`PRAGMA table_info(ingestions)` shows
   `source` column).
2. Verify `articles.layer1_verdict` and `rss_articles.layer1_verdict`
   distributions: 100% NULL means SQL should pull all of them; if they're
   all 'reject' something Layer 1 wrote them all wrong.
3. Run `python -c "...; print(_build_topic_filter_query([]))"` and compare
   the SQL byte-for-byte to `.scratch/ir-4-w1-dualsql.log`.

### `rss-classify` cron not removed in Step 5

The cron will fire and immediately fail with `enrichment/rss_classify.py:
No such file or directory`. Fix forward: re-run Step 5 to remove the job.
The failed run is benign — it logs the error and exits non-zero, no DB
mutation.

---

## Out-of-scope (do NOT execute as part of this deploy)

- LF-5.1/5.2/5.3 as written in REQUIREMENTS-v3.5-Ingest-Refactor.md
  (`_classify_full_body` / `batch_classify_kol.py` / DROP TABLE
  classifications). All deferred per ir-4-PLAN.md scope deviation note.
- ir-3 7-day observation window — calendar wait, not code work.
- Hermes-side LightRAG / KG storage migrations. ir-4 does not touch
  storage backends.
