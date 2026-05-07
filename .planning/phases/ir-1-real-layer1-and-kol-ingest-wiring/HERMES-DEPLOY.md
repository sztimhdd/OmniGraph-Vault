# HERMES Deploy Runbook — Phase ir-1

**REQ:** LF-4.1
**Scope:** Apply migration 006 + ship ir-1-00..02 code to Hermes; verify
end-to-end Layer 1 path on a 5-article smoke; resume `daily-ingest` cron.
**Pre-condition:** Local sign-off on ir-1-00..02 (PLAN files in this directory),
local `.dev-runtime` smoke green per
`.scratch/ir-1-local-smoke-2026-05-07-1949.md`,
all commits pushed to `main`.
**Operator:** runs all steps SSH-side. Agent does not SSH.

---

## Step 0 — Pre-flight

```bash
# On local machine — confirm pushed state
git log --oneline -10
git status -sb     # expect clean
git rev-parse main # capture local HEAD; you'll match it on Hermes
```

Expected local HEAD at deploy time: matches the commit immediately after
`docs(ir-1): HERMES-DEPLOY runbook + local smoke evidence (LF-4.1)`.

Note local HEAD: `<paste short SHA here at deploy time>`.

## Step 1 — Connect to Hermes (operator)

```bash
# Use SSH details from ~/.claude/projects/c--*-OmniGraph-Vault/memory/hermes_ssh.md
ssh -p <port> <user>@<host>
```

On Hermes:

```bash
cd ~/OmniGraph-Vault
git fetch origin
git status -sb
hostname; pwd; git rev-parse --abbrev-ref HEAD
```

Expected: branch `main`, clean working tree.

If Hermes is ahead of GitHub (per CLAUDE.md "Remote Hermes Deployment" —
the remote PC is also the Hermes-integration dev machine and may have
unpushed commits): STOP. Push from Hermes, pull locally, reconcile, then
restart this runbook.

## Step 2 — Backup (mandatory)

```bash
# DB backup — per CLAUDE.md Lessons 2026-05-06 #2
cp data/kol_scan.db data/kol_scan.db.backup-pre-ir1-mig006-$(date +%Y%m%d-%H%M%S)
ls -lh data/kol_scan.db.backup-pre-ir1-mig006-*

# Cron registry backup
cp ~/.hermes/cron/jobs.json ~/.hermes/cron/jobs.json.pre-ir1.$(date +%Y%m%d-%H%M%S)
```

## Step 3 — Pause `daily-ingest` cron

> Reason: avoid mid-run column-mismatch when migration 006 lands while a batch
> is in-flight. Migration is fast (<1s) but mid-batch races are not worth the
> risk.

Use the Hermes CLI command appropriate to your cron driver. The driver is
`hermes-cron` per `~/.hermes/cron/jobs.json` registry. Example shape (verify
exact command on the operator's machine):

```bash
hermes cron disable daily-ingest
hermes cron list --all | grep daily-ingest
# Expect: enabled=false (paused jobs require --all to show)
```

## Step 4 — Pull main + verify HEAD matches

```bash
git pull --ff-only origin main
git rev-parse HEAD
# Compare against local HEAD captured in Step 0 — must match.
```

If FAILS to fast-forward: stop. Investigate (Hermes ahead? Local not pushed?).
Per CLAUDE.md "Remote Hermes Deployment", reconcile before proceeding.

## Step 5 — Apply migration 006

```bash
python migrations/006_layer1_columns.py data/kol_scan.db
```

Expected output:

```
ADD  articles.layer1_verdict
ADD  articles.layer1_reason
ADD  articles.layer1_at
ADD  articles.layer1_prompt_version
ADD  rss_articles.layer1_verdict
ADD  rss_articles.layer1_reason
ADD  rss_articles.layer1_at
ADD  rss_articles.layer1_prompt_version

migration 006: applied 8 column(s); skipped 0 (already present)
```

Verify schema:

```bash
sqlite3 data/kol_scan.db "PRAGMA table_info(articles)"     | grep layer1_
sqlite3 data/kol_scan.db "PRAGMA table_info(rss_articles)" | grep layer1_
# Expect 4 lines per table = 8 lines total
```

Re-run migration once to confirm idempotency:

```bash
python migrations/006_layer1_columns.py data/kol_scan.db
# Expect: applied 0 column(s); skipped 8 (already present)
```

## Step 6 — Smoke 5 articles (dry-run)

```bash
source venv/bin/activate
python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run \
  2>&1 | tee /tmp/ir-1-smoke-dry-$(date +%Y-%m-%d-%H%M).log
```

Verify log:

```bash
grep '\[layer1\] batch' /tmp/ir-1-smoke-dry-*.log | head -3
# Expect at least 1 line shaped:
# [layer1] batch 0 n=N candidate=Y reject=Z null=0 wall_ms=...
```

DB verification:

```bash
sqlite3 data/kol_scan.db "
  SELECT id, layer1_verdict, layer1_prompt_version
  FROM articles
  WHERE layer1_at IS NOT NULL
  ORDER BY layer1_at DESC
  LIMIT 10;
"
# Expect: rows with verdict ∈ {candidate, reject} and prompt_version='layer1_v0_20260507'
```

> **Note on `--max-articles 5` semantics:** the cap counts
> *successfully-processed* rows in the per-article loop. Layer 1 batch runs
> upstream and tags **all** loaded rows. Local smoke at 531-row scale showed
> `[layer1] batch` × 18 chunks running before the per-article loop hits the
> cap — this is expected and matches LF-3.6 (dry-run validates the filter
> pipeline end-to-end). The smoke is "successful" if at least one
> `[layer1] batch` line shows `null=0` and the DB query returns rows with
> non-NULL `layer1_verdict`.

## Step 7 — Smoke 1 article (real ingest, optional but recommended)

```bash
python batch_ingest_from_spider.py --from-db --max-articles 1 \
  2>&1 | tee /tmp/ir-1-smoke-real-$(date +%Y-%m-%d-%H%M).log
# Expect: layer1 verdict, then either skipped (reject) or scrape→layer2→ainsert success
```

If 1-article smoke fails: STOP. Investigate. Do NOT resume cron.

Hermes-side env reminder: production Vertex Gemini routing requires
`GOOGLE_APPLICATION_CREDENTIALS=/home/sztimhdd/.hermes/gcp-sa.json` (or
equivalent), `GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8`, and
`GOOGLE_CLOUD_LOCATION=global` to be set in `~/.hermes/.env`. These should
already be in place per the v3.4 milestone deploy; if not, this is the
gating fix for Layer 1.

## Step 8 — Resume `daily-ingest` cron

```bash
hermes cron enable daily-ingest
hermes cron list | grep daily-ingest
# Expect: enabled=true
```

## Step 9 — First-cron-run watch

> ⚠ **Day-1 backlog warning** (per ROADMAP § ir-1 Notes): the first cron run
> after this deploy will see Layer-1-NULL on the entire post-charter accumulated
> backlog (since 2026-05-07 ~14:33 ADT). Expect 5–15 batches × ~5–8s wall-clock
> + extra Gemini Flash Lite quota draw on day 1. Subsequent runs settle to
> 2–3 batches/day in steady state.
>
> Local smoke at 531-row scale showed 18 batches × 4–7s = ~91s total Layer 1
> wall-clock. Production-shape backlog may be higher; budget the first cron
> run for up to ~3 minutes Layer 1 phase BEFORE per-article work begins.

Monitor first cron tick (typically next 09:00 ADT; check
`hermes cron list | grep daily-ingest` for the precise schedule):

```bash
tail -f ~/.hermes/cron/logs/daily-ingest.<latest>.log
# Watch for: [layer1] batch lines, candidate/reject counts, null=0, no exceptions
# Reject rate sanity: should be 50–80% per Layer 1 v0 spike + local smoke
```

If `null != 0` on multiple consecutive batches → Layer 1 LLM endpoint
issue (timeout / quota / non-JSON). Rows stay NULL and will be re-evaluated
on the next ingest tick — no manual intervention needed UNLESS the failure
persists across multiple cron runs. In that case follow CLAUDE.md
§ "Vertex AI Migration Path" trigger guidance.

## Step 10 — Sign-off

After first cron run completes successfully:

1. Update `.planning/STATE-v3.5-Ingest-Refactor.md` — append a § "ir-1 deploy
   sync" entry with:
   - Deploy timestamp (UTC + ADT)
   - First-cron-run wall-clock + batch count
   - layer1 reject rate observed (sanity: should be 50–80% per spike + local smoke)
   - Any anomalies
2. Commit STATE update on local + push.

---

## Rollback

### Path A — Simple (recommended)

ir-1 deploy is non-destructive: migration 006 only ADDs nullable columns; code
changes are commits that can be reverted.

```bash
# On Hermes
hermes cron disable daily-ingest

git log --oneline -5  # find the ir-1 commits
# Revert in reverse-dependency order: plan 02 first (tests), then plan 01
# (ingest loop), then plan 00 (lib + migration .py + .sql).
git revert <sha-of-ir-1-02>      # tests/unit/test_article_filter.py + test_batch_ingest_topic_filter.py
git revert <sha-of-ir-1-01>      # batch_ingest_from_spider.py ingest loop wiring
git revert <sha-of-ir-1-00>      # lib/article_filter rewrite + migration 006 files

git push origin main             # if Hermes deploys via git pull-only

# layer1_* columns can stay in place — they are nullable, ignored by reverted code.
# Do NOT DROP columns unless you have a strong reason; SQLite DROP COLUMN
# requires table-rebuild on older versions, see Path B.

hermes cron enable daily-ingest
```

### Path B — Invasive (only if Path A insufficient)

Restore from backup (atomic, fastest):

```bash
hermes cron disable daily-ingest
mv data/kol_scan.db data/kol_scan.db.bad-$(date +%Y%m%d-%H%M%S)
cp data/kol_scan.db.backup-pre-ir1-mig006-<TIMESTAMP> data/kol_scan.db
# Then revert commits per Path A.
hermes cron enable daily-ingest
```

This loses any post-deploy ingestions (typically a small loss; backup is taken
moments before deploy). Acceptable rollback only in serious-regression scenarios.

DROP COLUMN in SQLite < 3.35 requires CREATE TABLE new + INSERT SELECT + DROP +
RENAME. Hermes SQLite version (verify with `sqlite3 --version` on Hermes) is
typically 3.40+ which supports `ALTER TABLE ... DROP COLUMN` directly, but it
is still slow on large tables. The backup-restore path is preferred over
explicit DROP COLUMN.

---

## STOP gate (per session direction 2026-05-07)

This runbook is authored as part of ir-1-03-PLAN. Per user direction:
**agent does NOT execute this runbook**. Operator triggers the deploy at the
operator's chosen window (likely overlapping with `daily-ingest` 09:00 ADT
schedule; see Step 9 backlog warning).

After deploy completes, operator:

- Updates STATE-v3.5-Ingest-Refactor.md per Step 10 sign-off.
- Decides whether to proceed to ir-2 (real Layer 2 + DeepSeek) or pause for
  observation. Per ROADMAP, ir-2 starts immediately if ir-1 deploy is clean
  (the 7-day observation window is ir-3, post-ir-2 deploy).

---

## References

- PROJECT-v3.5-Ingest-Refactor.md § "6 User-Locked D-Decisions" (D-LF-1..6)
- REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-4.1 + LF-1.6
- ROADMAP-v3.5-Ingest-Refactor.md § Phase ir-1 Notes (Day-1 backlog warning)
- STATE-v3.5-Ingest-Refactor.md § "Current Hermes Operational State"
- ir-1-00-PLAN.md (migration 006 + lib/article_filter source)
- ir-1-01-PLAN.md (ingest loop wiring source)
- ir-1-02-PLAN.md (LF-1.9 unit tests)
- .scratch/ir-1-local-smoke-2026-05-07-1949.md (local sanity evidence: 531 rows,
  18 batches, 0 NULL, reject rate 76%, prompt_version=layer1_v0_20260507 on all rows)
- Foundation Quick HERMES-DEPLOY.md:
  `.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md` (structural model)
