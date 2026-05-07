# Hermes deploy runbook — v3.5 Ingest Refactor foundation cutover

**Quick:** 260507-lai (V35-FOUND-04)
**Origin commits (in order):**
  - `bd735ae` feat(filter): `lib/article_filter.py` with Layer 1/2 placeholders
  - `5d37232` test(filter): pin Layer 1/2 placeholder interface contract
  - `f1a963b` feat(ingest): bypass `_classify_full_body` — wire to placeholder Layer 1/2 (v3.5 foundation)
  - this runbook (companion docs commit)
**Target:** Hermes production WSL2 (`ohca.ddns.net`)
**Operator:** user (SSH from local; agent does NOT SSH)

---

## What this runbook does

After this morning's CV mass-classify disaster (`428b16f`), the Hermes
classify cron is structurally unsafe — any future schema/SQL change can
re-block ingest the same way. The v3.5 foundation removes the dependency
entirely: `batch_ingest_from_spider.py` no longer calls
`_classify_full_body`, and the candidate SELECT no longer joins
`classifications`. Layer 1/2 placeholder filters in `lib/article_filter.py`
always pass, so the ingest path is unblocked while real filter logic is
designed out-of-band.

This runbook deploys that change to Hermes:

1. Pull the foundation commits.
2. Remove three obsolete Hermes cron jobs (classify + enrich + RSS-classify).
3. Edit the `daily-ingest` cron to drop the now-ignored `--topic-filter`.
4. Resume `daily-ingest` and confirm next-fire timestamp.
5. Optional smoke: 1-article dry-run on Hermes to confirm Layer 1/2 wiring.
6. Rollback path if anything goes wrong.

Total wall-clock: ~5–10 minutes. No DB migrations, no destructive DDL.

---

## Pre-flight

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net
cd ~/OmniGraph-Vault
git pull --ff-only
git log --oneline -6
```

Expected `git log --oneline -6` (most recent first; commits may be
followed by an even-newer SUMMARY commit added by the quick workflow):

```
docs(quick-260507-lai): plan + summary + STATE update    ← workflow-added
docs(deploy): v3.5 foundation Hermes deploy runbook
feat(ingest): bypass _classify_full_body — wire to placeholder Layer 1/2 (v3.5 foundation)
test(filter): pin Layer 1/2 placeholder interface contract
feat(filter): lib/article_filter.py with Layer 1/2 placeholders
docs(v3.5-ingest-refactor): ...
```

If `git pull --ff-only` fails because Hermes has divergent local commits
(per CLAUDE.md "Remote Hermes Deployment" — Hermes occasionally holds
untracked local edits), **stop and triage with the user** — do NOT
force-pull.

---

## Step 1: Remove three obsolete Hermes cron jobs

The classifier is no longer called from the ingest loop, so the daily
classify cron is obsolete. Likewise, the RSS-classify and daily-enrich
crons depend on the classifications table that v3.5 abandons. All three
should be removed.

Use the Hermes scheduler CLI (`cronjob remove <id>`):

```bash
# 1. daily-classify-kol — runs batch_classify_kol.py multi-topic loop
#    (this is the cron whose 5-topic sequential CLI invocation triggered
#    the 2026-05-07 CV mass-classify; never run it again on production)
cronjob remove b50ec39b889f

# 2. daily-enrich — runs the enrichment hop on already-classified rows
cronjob remove fc768319e0c1

# 3. rss-classify — RSS analogue of daily-classify-kol
cronjob remove c7ded378de8f
```

Confirm:

```bash
cronjob list | grep -E "classify|enrich"
# Expected: only entries unrelated to the three IDs above
```

If `cronjob remove` is not the right command on this Hermes instance,
substitute the equivalent (e.g. `crontab -e` to comment out the lines, or
`systemctl disable <unit>` if these are systemd timers). The user knows
the deployed scheduler shape.

---

## Step 2: Edit `daily-ingest` to drop the now-ignored `--topic-filter`

The `daily-ingest` cron (id: `2b7a8bee53e0`) currently passes
`--topic-filter agent,hermes,openclaw,harness` to
`batch_ingest_from_spider.py`. After v3.5 foundation, the topic-filter
flag is silently ignored — but leaving it on the command line is noise
and a future maintenance trap (someone may later assume it works).

Remove that flag from the command. Example using a hypothetical
`cronjob update`:

```bash
cronjob update 2b7a8bee53e0 \
  --command "venv/bin/python batch_ingest_from_spider.py --from-db --max-articles 50"
```

Or, if `cronjob update` is not available, edit the underlying crontab /
systemd unit file directly to remove the
`--topic-filter agent,hermes,openclaw,harness` token (and any preceding
or trailing whitespace) from the command line.

Confirm:

```bash
cronjob list | grep daily-ingest
# Expected: command no longer contains --topic-filter
```

> **Optional:** `--min-depth 2` is also silently ignored after v3.5
> foundation but it's harmless (defaults to 2 anyway). You may leave it
> or remove it — operator's choice.

---

## Step 3: Resume `daily-ingest` and verify next-fire

```bash
cronjob enable 2b7a8bee53e0  # if Step 2 disabled it; otherwise no-op
cronjob list | grep daily-ingest
# Expected: enabled, next_fire timestamp visible
```

The Hermes ingest cron will fire at its scheduled time and exercise the
v3.5 path end-to-end. The first run will hit Layer 1 (placeholder
always-pass) → scrape → Layer 2 (placeholder always-pass) → LightRAG
ainsert. No classify gate; no `classifications` table read.

---

## Step 4: Optional smoke test (1-article dry-run on Hermes)

```bash
source venv/bin/activate
DEEPSEEK_API_KEY=$(grep DEEPSEEK_API_KEY ~/.hermes/.env | cut -d= -f2-) \
  venv/bin/python batch_ingest_from_spider.py \
    --from-db --max-articles 1 --dry-run \
    2>&1 | tee /tmp/v3.5-foundation-smoke-$(date +%Y%m%d-%H%M%S).log
```

Expected: enumerates ≥ 1 candidate from the production DB and exits
cleanly without crashing. The Layer 1/2 placeholders are gated by
`if not dry_run:` so they will not log in dry-run mode — the smoke is
purely an interface-integrity check (SQL parses, row tuple shape is
correct, no `_classify_full_body` import error).

If `dry-run` exits at "No articles found" but you expect candidates,
verify by querying the DB directly:

```bash
venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/kol_scan.db')
print('articles:', c.execute('SELECT COUNT(*) FROM articles').fetchone()[0])
print('ingested ok:', c.execute(\"SELECT COUNT(*) FROM ingestions WHERE status='ok'\").fetchone()[0])
print('candidate after anti-join:', c.execute(\"SELECT COUNT(*) FROM articles a WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status='ok')\").fetchone()[0])
"
```

If the candidate count is > 0 but dry-run finds none, something is wrong
with the deploy — escalate.

---

## Step 5: Rollback

If the next `daily-ingest` cron run misbehaves (for example: scrape
errors at scale, LightRAG ingest collisions, unexpected memory growth),
revert the v3.5 foundation commits and re-add the cron jobs. The revert
is a single `git revert` chain since the changes are isolated to
`lib/article_filter.py`, the test files, and the ingest module.

```bash
cd ~/OmniGraph-Vault
git fetch origin
# Revert in reverse order (most recent first), matching the topological
# order of the original commits. Skip the workflow-added plan/summary
# commit — it does not need a revert (artifacts only).
git revert --no-edit f1a963b   # ingest loop bypass
git revert --no-edit 5d37232   # test pin
git revert --no-edit bd735ae   # filter module
git push origin main
```

Then re-add the three cron jobs from Step 1 (record their original
schedule + command before deleting them, so the restoration is exact).

> **Why three reverts and not one:** atomic commits per CLAUDE.md
> Lessons #5; reverting the chain individually keeps the audit trail
> clean and lets a partial rollback (e.g. revert only the ingest patch
> while keeping the placeholder library) if that's the right call later.

---

## What this runbook does NOT do

- Does NOT touch the `classifications` table or any schema.
- Does NOT delete `_classify_full_body` / `_call_deepseek_fullbody` /
  `_build_fullbody_prompt` from the codebase. Those function bodies are
  retained — only the ingest-loop CALL was removed in `f1a963b`. Future
  quicks may delete the dead code.
- Does NOT enable or configure real Layer 1/2 logic. Layer 1/2 ship as
  placeholders that always pass; real logic lands in follow-up quicks
  per `.planning/PROJECT-Ingest-Refactor-v3.5.md` Phase B+C.

---

## Post-deploy: where to put real Layer 1/2 logic

When ready, the next quick should:

1. Replace `layer1_pre_filter` body in `lib/article_filter.py` with the
   real cheap-signal filter (e.g. title regex, summary keyword check).
2. Replace `layer2_full_body_score` body with the real LLM-scored
   filter (e.g. graded probe, full-body keyword/topic alignment check).
3. Update `tests/unit/test_article_filter.py` — the 7 contract tests
   pin the (passed, reason) interface, but the always-pass + placeholder
   substring assertions must be replaced with real behavioural tests.
4. The ingest loop in `batch_ingest_from_spider.py` does NOT need to
   change again. The Layer 1/2 wiring is the stable contract.
