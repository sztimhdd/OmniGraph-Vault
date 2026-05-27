# COG-03 Hermes one-pass retirement runbook

**Status:** Pending operator SSH execution.
**Plan:** Phase 20 Wave 3 Task 3.3 — D-20.14 retire `OMNIGRAPH_COGNEE_INLINE` env gate.
**Strategy:** Opt 5 (one-pass, no Step 1 commit) — single Hermes SSH session
validates all 5 D-20.14 criteria, then either lands retirement (PASS) or
aborts gracefully (FAIL) with no intermediate commits to revert.

## Why one-pass instead of original B-档 two-step

`.dev-runtime/` lacks ≥3 eligible candidates (13 agent-topic articles already
ingested locally; 11 pending depth>=2 articles all on non-agent topics).
Local Step 1 smoke would have given (a)/(c)/(d)/(e) signal, but COG-02 mock
test (5011ms→<100ms, GREEN) already provides prima facie detach evidence.
Skipping local saves ~25min effort + 1 commit + 1 revert path.

## Steps

### Step 0: SSH + git state reconcile

```bash
ssh -p <port> <user>@<host>   # creds in memory/hermes_ssh.md
cd ~/OmniGraph-Vault
git status -sb
git log --oneline -3
git pull --ff-only
```

If remote is ahead of expected 965a4ef+ ancestor: investigate before continuing.

```bash
source venv/bin/activate
```

### Step 1: Pre-flight code verify

```bash
grep -n "asyncio.create_task" cognee_wrapper.py
# expect ≥1 match inside remember_article (line ~110-145)

grep -nE "asyncio.wait_for" cognee_wrapper.py
# expect ≥3 matches in remember_synthesis / recall_previous_context /
# disambiguate_entities — but NOT inside remember_article body

grep -n "_cognee_inline_enabled\|OMNIGRAPH_COGNEE_INLINE" ingest_wechat.py
# expect 2-3 matches still present (helper at ~797-810 + call site at ~1163-1172)
```

If any expectation fails → STOP, don't run smoke.

### Step 2: Pre-smoke Cognee baseline

```bash
venv/bin/python -c "
import asyncio
from cognee_wrapper import recall_previous_context
results = asyncio.run(recall_previous_context('agent'))
print(f'PRE: {len(results)} entries')
" | tee /tmp/cog03-hermes-pre.txt
```

Record N (could be 0 or higher).

### Step 3: 3-article smoke with env gate forced ON

```bash
OMNIGRAPH_COGNEE_INLINE=1 venv/bin/python batch_ingest_from_spider.py \
    --from-db --topic-filter agent --min-depth 2 --max-articles 3 \
    2>&1 | tee /tmp/cog03-hermes-smoke-$(date +%Y%m%d-%H%M%S).log
```

Expected wall-clock: ~12-25 min (4-8 min/article post-Wave-0/1/2).

### Step 4: Validate all 5 D-20.14 criteria

```bash
LOG=$(ls -t /tmp/cog03-hermes-smoke-*.log | head -1)

# (a) total wall-clock < 30 min
head -1 $LOG | awk '{print "Start:", $1, $2}'
tail -10 $LOG | grep -E "completed|done|ingest done"
# manual diff: pass if (last - first) timestamp < 30 min

# (b) zero 422 retry loop  ← THE Hermes-only criterion
echo "422 count: $(grep -c '422' $LOG)"
# expect 0 — sustained 422 retry loop = COG-01 routing fix regressed

# (c) Cognee episodic store grew
venv/bin/python -c "
import asyncio
from cognee_wrapper import recall_previous_context
results = asyncio.run(recall_previous_context('agent'))
print(f'POST: {len(results)} entries')
" | tee /tmp/cog03-hermes-post.txt
# expect POST > PRE

# (d) ≥2/3 ingestions ok (today)
venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/kol_scan.db')
rows = conn.execute(\"SELECT status, COUNT(*) FROM ingestions WHERE date(ingested_at) = date('now') GROUP BY status\").fetchall()
for r in rows: print(r)
"
# expect ('ok', N) with N >= 2

# (e) max per-article wall-clock < 1800s
grep -E "_ingest_one_article|TimeoutError|asyncio.TimeoutError" $LOG | tail -10
# expect: no TimeoutError; per-article ingest under 1800s
```

### Step 5: Decision tree

#### ALL 5 PASS → retire env gate

a) Edit `ingest_wechat.py`:

- DELETE the entire `_cognee_inline_enabled()` helper function (lines ~797-810)
- REPLACE the `if _cognee_inline_enabled():` block at lines ~1163-1172 with unconditional call (keep inner try/except, drop outer if):

```python
try:
    await remember_article(title=title, url=url, entities=extracted_entities, summary_gist=...)
except Exception as exc:
    logger.warning("remember_article failed: %s", exc)
```

b) Edit `CLAUDE.md` — DELETE the entire `OMNIGRAPH_COGNEE_INLINE` row from
the "Environment Variables" table (introduced by quick 260503-v9z).
Keep historical mentions in the Lessons Learned section unchanged.

c) Verify cleanup:

```bash
grep -rn "OMNIGRAPH_COGNEE_INLINE\|_cognee_inline_enabled" --include="*.py" --include="*.md" .
# expect: only matches in .planning/ historical docs (those stay — they
# document why the gate existed)
```

d) Run unit tests — must not regress:

```bash
DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/ --tb=short
# expect: ≤13 pre-existing fails + Phase 20 surface 32 fail unchanged;
# NO new failures
```

e) Commit + push (selective add only — never -A / .):

```bash
git add ingest_wechat.py CLAUDE.md
git commit -m "fix(cog-03): retire OMNIGRAPH_COGNEE_INLINE env gate after Hermes 5/5 D-20.14 PASS"
git push origin main
```

f) Phase 20 milestone close — update `.planning/STATE.md` `last_activity`
field manually in this same SSH session (operator scope).

#### ANY criterion FAIL → ABORT retirement

a) Capture which criterion failed + log path.
b) NO code edits, NO commits, NO push (this is the value of the one-pass plan).
c) Document failure in `.planning/phases/20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix/20-COG-03-FAIL-REPORT.md`:

- Which criterion (a/b/c/d/e)
- Evidence (log line, query output)
- Hypothesized root cause
- Whether to re-attempt or escalate to v3.5

d) Commit + push the fail report only:

```bash
git add .planning/phases/20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix/20-COG-03-FAIL-REPORT.md
git commit -m "docs(cog-03): retirement aborted — criterion <X> failed in Hermes smoke"
git push origin main
```

e) Env gate stays default 0 (production current state) — no operational change.

### Step 6: Resume signal protocol

Report back to the orchestrating session one of:

- `approved`: 5/5 PASS, retirement committed at `<hash>`
- `failed`: criterion `<X>`: `<one-line root cause>`
- `partial`: smoke ran `<N>/<M>`, retirement deferred because `<reason>`

## Notes

- This runbook intentionally packs migration 004 deployment + 06:00 ADT cron result review into a separate runbook — they are independent SSH activities. See `.planning/quick/260506-se5-classifications-upsert-schema-consistenc/260506-se5-SUMMARY.md` for migration 004 runbook.
- "Selective git add" rule (`git add <specific file>` never `-A`/`.`) is enforced per CLAUDE.md Lessons Learned #5 (2026-05-06 commit-attribution race).
- No `git stash` / `reset` / `rebase` / `amend` / force push at any step.
