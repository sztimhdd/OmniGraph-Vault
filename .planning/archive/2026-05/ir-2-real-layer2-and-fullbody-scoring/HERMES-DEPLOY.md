# HERMES Deploy Runbook — Phase ir-2

**REQ:** LF-4.2
**Scope:** Apply migration 007 + ship ir-2-00..02 code to Hermes; verify
end-to-end Layer 1 + Layer 2 path on a 5-article + 1-article smoke; resume
`daily-ingest` cron.
**Pre-condition:** Local sign-off on ir-2-00..03 (PLAN files + tests in this
directory + close-out smoke captured at
`.scratch/layer2-deepseek-validation-<ts>.md`), all commits pushed to `main`.
ir-1 is already deployed (Hermes has migration 006 + Layer 1 wiring live).
**Operator:** runs all steps SSH-side. Agent does not SSH.

---

## Step 0 — Pre-flight

```bash
# On local machine — confirm pushed state
git log --oneline -10
git status -sb     # expect clean
git rev-parse main # capture local HEAD; you'll match it on Hermes
```

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

If Hermes is ahead of GitHub (per CLAUDE.md "Remote Hermes Deployment"): STOP.
Push from Hermes, pull locally, reconcile, then restart this runbook.

## Step 2 — Backup (mandatory)

```bash
# DB backup — per CLAUDE.md Lessons 2026-05-06 #2
cp data/kol_scan.db data/kol_scan.db.backup-pre-ir2-mig007-$(date +%Y%m%d-%H%M%S)
ls -lh data/kol_scan.db.backup-pre-ir2-mig007-*

# Cron registry backup
cp ~/.hermes/cron/jobs.json ~/.hermes/cron/jobs.json.pre-ir2.$(date +%Y%m%d-%H%M%S)
```

## Step 3 — Pause `daily-ingest` cron

> Reason: avoid mid-run column-mismatch when migration 007 lands while a batch
> is in-flight. Migration is fast (<1s) but mid-batch races are not worth the
> risk.

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

## Step 5 — Apply migration 007

```bash
python migrations/007_layer2_columns.py data/kol_scan.db
```

Expected output (excerpt):

```text
ADD  articles.layer2_verdict
ADD  articles.layer2_reason
ADD  articles.layer2_at
ADD  articles.layer2_prompt_version
ADD  rss_articles.layer2_verdict
... (4 more)
migration 007: applied 8 column(s); skipped 0 (already present)
```

Verify schema:

```bash
sqlite3 data/kol_scan.db "PRAGMA table_info(articles)"     | grep layer2_
sqlite3 data/kol_scan.db "PRAGMA table_info(rss_articles)" | grep layer2_
# Expect 4 lines per table = 8 lines total
```

Re-run migration once to confirm idempotency:

```bash
python migrations/007_layer2_columns.py data/kol_scan.db
# Expect: applied 0 column(s); skipped 8 (already present)
```

## Step 6 — Smoke 5 articles (dry-run) — Layer 1 verification

```bash
source venv/bin/activate
python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run \
  2>&1 | tee /tmp/ir-2-smoke-dry-$(date +%Y-%m-%d-%H%M).log
```

Verify log:

```bash
grep '\[layer1\] batch' /tmp/ir-2-smoke-dry-*.log | head -3
# Expect at least 1 line:
# [layer1] batch 0 n=N candidate=Y reject=Z null=0 wall_ms=...

# [layer2] batch lines do NOT appear under dry-run by design — Layer 2 is
# gated by the per-candidate body which dry-run short-circuits (LF-3.6).
```

If `null != 0` on the first Layer 1 batch: STOP. Investigate Vertex Gemini
auth (per ir-1 deploy verification).

## Step 7 — Smoke 1 article (REAL ingest) — Layer 2 happy-path GATE

> ⚠ **This step is the canonical happy-path gate for ir-2.** Local close-out
> smoke validated the LF-1.5 / LF-2.6 failure paths end-to-end (rows stay
> NULL on auth/parse errors). The Layer 2 happy path with `verdict='ok'` /
> `verdict='reject'` actually persisted requires production GCP + DeepSeek
> creds. If `null != 0` here on Layer 2, do NOT resume cron.

```bash
python batch_ingest_from_spider.py --from-db --max-articles 1 \
  2>&1 | tee /tmp/ir-2-smoke-real-$(date +%Y-%m-%d-%H%M).log
```

Verify log MUST contain BOTH lines:

```bash
grep '\[layer1\] batch' /tmp/ir-2-smoke-real-*.log | head -1
# Expect: [layer1] batch 0 n=1 candidate=1 reject=0 null=0 wall_ms=...
#   (or n=N if more rows pulled; null=0 is the success indicator)

grep '\[layer2\] batch' /tmp/ir-2-smoke-real-*.log | head -1
# Expect: [layer2] batch 0 n=1 ok=Y reject=Z null=0 wall_ms=...
#   (sum ok+reject must equal 1; null=0 is the success indicator)
```

DB verification — both layer1 + layer2 verdicts populated:

```bash
sqlite3 data/kol_scan.db "
  SELECT id, layer1_verdict, layer2_verdict, layer1_prompt_version, layer2_prompt_version
  FROM articles
  WHERE layer2_at IS NOT NULL
  ORDER BY layer2_at DESC
  LIMIT 5;
"
# Expect: rows with verdict ∈ {candidate, reject} on layer1 AND
#   verdict ∈ {ok, reject} on layer2. Both prompt_versions set:
#   layer1_v0_20260507 / layer2_v0_20260507.
```

Hermes-side env reminder:

```bash
grep -E "^GOOGLE_(APPLICATION_CREDENTIALS|CLOUD_PROJECT|CLOUD_LOCATION)=" ~/.hermes/.env
grep -E "^DEEPSEEK_API_KEY=" ~/.hermes/.env
grep -E "^DEEPSEEK_MODEL=" ~/.hermes/.env || echo "DEEPSEEK_MODEL unset → defaults to deepseek-v4-flash"
# All env values must be set; DEEPSEEK_MODEL operator sets to deepseek-chat
# if strict LF-2.3 compliance required (otherwise default deepseek-v4-flash).
```

If 1-article smoke fails Layer 2: STOP. Investigate. Do NOT resume cron.

## Step 8 — Resume `daily-ingest` cron

```bash
hermes cron enable daily-ingest
hermes cron list | grep daily-ingest
# Expect: enabled=true
```

## Step 9 — First-cron-run watch

> ⚠ **Day-1 backlog warning** (extends ir-1's): the first cron run after
> this deploy will see Layer-2-NULL on the entire Layer-1-candidate
> backlog (every row that survived Layer 1 since ir-1 deploy). Layer 1
> stage stays at steady-state batch count; Layer 2 stage will issue
> `ceil(candidate_count / 5)` new batches. Day 1 may double the LLM
> wall-clock vs ir-1's deploy day.
>
> Spike measured ~5-7s wall-clock per Layer 2 batch; budget the first
> cron run for an additional ~3-5 minutes Layer 2 phase on top of
> Layer 1's ~3 min.

Monitor first cron tick (typically next 09:00 ADT):

```bash
tail -f ~/.hermes/cron/logs/daily-ingest.<latest>.log
# Watch for:
#   [layer1] batch ... null=0  (Layer 1 healthy)
#   [layer2] batch ... null=0  (Layer 2 healthy)
#   reject rate per layer:
#     Layer 1: 50–70% (per Layer 1 v0 spike .scratch/layer1-validation-20260507-151608.md)
#     Layer 2: ≥30% on Layer-1-passed rows (per Layer 2 spike — 55% on hand-curated)
```

If `[layer2] batch ... null != 0` on multiple consecutive batches → DeepSeek
issue (timeout / quota / non-JSON). Rows stay layer2_verdict=NULL → re-eval
next tick. Investigate via failure mode mapping (timeout / non_json /
partial_json / row_count_mismatch / exception:<ClassName>).

## Step 10 — Sign-off

After first cron run completes successfully:

1. Update `.planning/STATE-v3.5-Ingest-Refactor.md` — append a § "ir-2 deploy
   sync" entry with:
   - Deploy timestamp (UTC + ADT)
   - First-cron-run wall-clock + Layer 1 batch count + Layer 2 batch count
   - Per-layer reject rate observed (Layer 1: 50-70%; Layer 2 on filtered: ≥30%)
   - Per-layer null count (should be 0 / 0 in steady state)
   - Any anomalies
2. Commit STATE update on local + push.

After sign-off: ir-3 (production cutover + 1-week observation) starts on
the next session. ir-3 is observation-only — no code changes.

---

## Rollback

### Path A — Simple (recommended)

ir-2 deploy is non-destructive: migration 007 only ADDs nullable columns;
code changes are commits that can be reverted.

```bash
# On Hermes
hermes cron disable daily-ingest

git log --oneline -10  # find the ir-2 commits
# Revert in reverse-dependency order: plan 03 first (CLOSURE+runbook),
# then 02 (tests), 01 (ingest loop), 00 (lib + migration).
git revert <sha-of-ir-2-03>      # CLOSURE + HERMES-DEPLOY (this file)
git revert <sha-of-ir-2-02>      # tests/unit/test_article_filter.py
git revert <sha-of-ir-2-01>      # batch_ingest_from_spider.py ingest loop wiring
git revert <sha-of-ir-2-00>      # lib/article_filter Layer 2 + migration 007 files

git push origin main             # if Hermes deploys via git pull-only

# layer2_* columns can stay in place — nullable, ignored by reverted code.
# Reverting ir-2-00 returns layer2_full_body_score to placeholder always-pass
# 'candidate', which the reverted ir-2-01 ingest loop still understands.

hermes cron enable daily-ingest
```

### Path B — Invasive (only if Path A insufficient)

Restore from backup (atomic, fastest):

```bash
hermes cron disable daily-ingest
mv data/kol_scan.db data/kol_scan.db.bad-$(date +%Y%m%d-%H%M%S)
cp data/kol_scan.db.backup-pre-ir2-mig007-<TIMESTAMP> data/kol_scan.db
# Then revert commits per Path A.
hermes cron enable daily-ingest
```

This loses any post-deploy ingestions. Acceptable rollback only in
serious-regression scenarios.

DROP COLUMN: Hermes SQLite typically 3.40+ supports
`ALTER TABLE ... DROP COLUMN` directly but slow on large tables. The
backup-restore path is preferred.

---

## STOP gate (per session direction 2026-05-07)

This runbook is authored as part of ir-2-03-PLAN. Per user direction:
**agent does NOT execute this runbook**. Operator triggers the deploy at the
operator's chosen window (likely overlapping with `daily-ingest` 09:00 ADT
schedule; see Step 9 backlog warning).

After deploy completes, operator:

- Updates STATE-v3.5-Ingest-Refactor.md per Step 10 sign-off.
- Decides whether to proceed to ir-3 (production cutover + 1-week observation)
  or pause for observation. Per ROADMAP, ir-3 is the gating observation phase
  before ir-4 (RSS integration + dead-code cleanup).

---

## References

- PROJECT-v3.5-Ingest-Refactor.md § "6 User-Locked D-Decisions" (D-LF-1..6)
- REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-2.x + LF-3.2/3.3 + LF-4.2
- ROADMAP-v3.5-Ingest-Refactor.md § Phase ir-2
- STATE-v3.5-Ingest-Refactor.md § "Current Hermes Operational State"
- ir-2-00-PLAN.md (lib + migration 007)
- ir-2-01-PLAN.md (ingest loop batched Layer 2 wiring)
- ir-2-02-PLAN.md (LF-2.8 unit tests)
- CLOSURE.md (this directory) — ir-2 phase closure with evidence references
- .scratch/layer2-validation-20260507-210423.md (Vertex spike — pre-ir-2)
- .scratch/layer2-deepseek-validation-<ts>.md (DeepSeek close-out — ir-2-03; gitignored)
- ir-1's HERMES-DEPLOY.md at `.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md` (structural model)
