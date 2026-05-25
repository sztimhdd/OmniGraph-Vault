---
plan_id: aim-4-4
phase: aim-4
wave: 4
depends_on:
  - aim-4-3
requirements_addressed:
  - SYNC-03
files_modified:
  - docs/runbooks/aim-4-aliyun-wiki-commit.md
  - docs/runbooks/aim-4-databricks-sync03-verify.md
  - .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md
autonomous: true
t_shirt: S
---

# aim-4-4 — Databricks SYNC-03 verification + Aliyun manual wiki commit guide

## Goal

Two deliverables, both documentation-only:

1. **Aliyun manual wiki commit guide** — operator runbook documenting
   the manual `git add kb/wiki/ && git commit && git push` flow that
   produces wiki increments on `main` during aim-4..aim-5. Per Q4c, the
   auto-hook is OUT of scope (deferred to LLM-Wiki-Integration-P2
   milestone). The runbook makes the manual cadence explicit so the
   operator knows what to run and when.

2. **Databricks SYNC-03 verification runbook** — post-deploy
   verification command + acceptance criterion for SYNC-03. Per
   FINDING 8, Databricks already runs `git pull` on its existing repo
   checkout (pre-aim-4 workflow). No new code or cron required.
   Verification = run `git log -1 kb/wiki/` ≥ 24h after first SYNC-02
   fire and confirm timestamp ≥ aim-4 deploy.

This plan covers SYNC-03 only. The `requirements_addressed` is exactly
SYNC-03 — neither runbook installs new code on Databricks; the
verification is operator-driven and is run ONCE 24h after the timer
fires, then evidence is captured.

This plan is autonomous for the runbook authoring + commit. The actual
24h-post-fire verification is a deferred operator step recorded as a
TODO in evidence (it cannot complete during this plan's execute window
because the timer hasn't yet fired its first natural daily run).

## Acceptance criteria

1. `docs/runbooks/aim-4-aliyun-wiki-commit.md` exists in repo with:
   - Purpose: explain the Q4c manual-commit cadence during aim-4..5
   - Step-by-step ssh-from-dev-box `git status / add / commit / push`
   - Pointer to LLM-Wiki-Integration-P2 milestone for auto-hook future
   - Cadence guidance (daily / on-demand — operator's call)
2. `docs/runbooks/aim-4-databricks-sync03-verify.md` exists with:
   - Purpose: SYNC-03 verification post first SYNC-02 fire
   - Exact command sequence on Databricks consumer
   - Acceptance: `git log -1 kb/wiki/` timestamp ≥ aim-4 deploy
   - Note: only valid AFTER first manual Aliyun wiki commit + first
     SYNC-02 fire have both occurred (otherwise timestamp predates
     aim-4 deploy and verification cannot pass)
3. Both runbooks are stand-alone (no implicit context dependencies the
   reader must already know).
4. Evidence markdown
   `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` records:
   - Commit hash for the runbook commit
   - aim-4 deploy timestamp (= aim-4-3 commit timestamp on `main`)
   - TODO marker: "SYNC-03 24h-post-fire verification deferred to
     operator; track via aim-5 STAB checkpoint"
5. No `git pull` is actually run on Databricks during this plan
   (verification is deferred). The runbook merely documents what to
   run.
6. Single forward-only commit on `main` with the 2 runbook files +
   evidence file. Conventional commit message:
   `docs(aim-4): SYNC-03 verification + Aliyun wiki commit runbooks`.
7. `git status` clean post-commit.

## Task list

### Task 1 — Author docs/runbooks/aim-4-aliyun-wiki-commit.md

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 316-329 (Aliyun manual wiki commit pattern)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\PROJECT-Aliyun-Ingest-Migration-v1.md`
  Q4c clause (deferred auto-write-back to LLM-Wiki-Integration-P2)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md`
  line 130 (Q4c manual wiki commit decision)
- Memory `aliyun_vitaclaw_ssh.md` (Aliyun SSH alias `aliyun-vitaclaw`)
- Memory `aliyun_vitaclaw_ssh.md` "Git auth caveat" — `git push` from
  Aliyun may need a deploy key OR an interactive credential prompt;
  document both paths.

**`<acceptance_criteria>`**
- `docs/runbooks/aim-4-aliyun-wiki-commit.md` exists.
- Contains: purpose / when to run / step-by-step / git auth fallback /
  cadence / Q4c context / pointer to LLM-Wiki-Integration-P2.
- `grep -c 'aliyun-vitaclaw' docs/runbooks/aim-4-aliyun-wiki-commit.md`
  returns ≥ 1.
- `grep -c 'kb/wiki/' docs/runbooks/aim-4-aliyun-wiki-commit.md`
  returns ≥ 1.
- `grep -c 'LLM-Wiki-Integration-P2' docs/runbooks/aim-4-aliyun-wiki-commit.md`
  returns 1.

**`<action>`**

Use the Write tool. Suggested skeleton (agent should expand for clarity
but listed sections must all appear):

```markdown
# Runbook — Aliyun manual wiki commit (aim-4..aim-5)

**Scope:** Per Q4c, the Aliyun → repo wiki write-back is manual during
the aim-4..aim-5 window. This runbook is the operator's reference for
when, what, and how to run the manual commit. The auto-hook is deferred
to the `LLM-Wiki-Integration-P2` milestone (separate scope).

## When to run

Trigger conditions (any of these → run the runbook):

1. New wiki content has accumulated under `/root/OmniGraph-Vault/kb/wiki/`
   on Aliyun (e.g., new `concepts/<term>.md`, new `comparisons/<a>-vs-<b>.md`).
2. The Hermes daily-pull and Databricks `git pull` consumers have
   diverged from Aliyun's `kb/wiki/` (visible by comparing
   `~/.hermes/omonigraph-vault/kb/wiki/` on Hermes vs `kb/wiki/` on
   Aliyun).
3. Operator-discretionary cadence — daily / weekly / on-demand. The
   downstream consumers tolerate up to 7 days of drift before SYNC-03
   verification (`git log -1 kb/wiki/`) becomes stale.

## Steps

```bash
# 1. SSH into Aliyun (alias from memory aliyun_vitaclaw_ssh.md)
ssh aliyun-vitaclaw

# 2. Inside Aliyun shell, navigate to the repo
cd /root/OmniGraph-Vault

# 3. Inspect what changed under kb/wiki/
git status kb/wiki/

# 4. Stage + commit (use a date-stamped message for traceability)
git add kb/wiki/
git commit -m "wiki: daily increment $(date +%Y-%m-%d)"

# 5. Push to origin/main
git push origin main
```

## Git auth fallback (if `git push` prompts for credentials)

Aliyun may not have a stored credential helper. Two recovery paths:

**Path A — install a GitHub deploy key on Aliyun (one-time setup):**

```bash
# Generate deploy key on Aliyun
ssh-keygen -t ed25519 -f ~/.ssh/aliyun_omnigraph_deploy -N ""
cat ~/.ssh/aliyun_omnigraph_deploy.pub
# → operator copies pubkey, adds to GitHub repo Settings → Deploy keys
#   with "Allow write access" checked (so push works, not just pull)

# Configure git to use the deploy key
git remote set-url origin git@github.com:<owner>/OmniGraph-Vault.git
echo 'Host github.com' >> ~/.ssh/config
echo '  IdentityFile ~/.ssh/aliyun_omnigraph_deploy' >> ~/.ssh/config
```

**Path B — exit Aliyun shell + push from local dev box:**

```bash
# From corp dev box, with read-access on Aliyun
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
  git format-patch HEAD~1 --stdout' > /tmp/aliyun-wiki.patch
# Then on dev box:
cd ~/Desktop/OmniGraph-Vault
git apply /tmp/aliyun-wiki.patch
git add kb/wiki/
git commit -m "wiki: increment from aliyun $(date +%Y-%m-%d)"
git push origin main
```

Path A is preferred (one-time setup, then frictionless). Path B is the
fallback if deploy key setup is blocked.

## Verification

After successful push:

```bash
# On Aliyun
git log -1 kb/wiki/ --format='%H %ai %s'

# On Databricks (24h later, post-pull)
cd <databricks-checkout>
git pull
git log -1 kb/wiki/ --format='%H %ai %s'
# Both should match the same commit hash.
```

## Cadence guidance

- **Daily**: simplest cadence; matches the daily-pull rhythm of SYNC-02.
- **Weekly**: acceptable if wiki delta is small. SYNC-03 verification
  tolerates up to 7 days of drift before staleness.
- **On-demand**: acceptable if wiki content is rare.

When in doubt: daily.

## Q4c context

This manual flow is the explicit Q4c trade-off. Auto-write-back via
git hook on Aliyun (post-write-to-kb/wiki/ → push to origin) is the
LLM-Wiki-Integration-P2 milestone scope, separate from
Aliyun-Ingest-Migration-v1.

## References

- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` Q4c
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` Decisions Q4c
- LLM-Wiki-Integration-P2 milestone (separate scope, not yet chartered)
```

### Task 2 — Author docs/runbooks/aim-4-databricks-sync03-verify.md

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 132-141 (FINDING 8 — Databricks verification only)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`
  line 73 (SYNC-03 verbatim)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 306-314 (Databricks SYNC-03 verification command)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` "Databricks Apps
  logs WebSocket" memory area (Databricks workspace path conventions)

**`<acceptance_criteria>`**
- `docs/runbooks/aim-4-databricks-sync03-verify.md` exists.
- Contains: purpose / preconditions / verification command / pass
  criterion / fail diagnosis paths.
- `grep -c "git log -1 kb/wiki/" docs/runbooks/aim-4-databricks-sync03-verify.md`
  returns ≥ 1.
- `grep -c 'aim-4 deploy timestamp' docs/runbooks/aim-4-databricks-sync03-verify.md`
  returns ≥ 1.
- States explicitly: "no new code on Databricks; uses existing
  `git pull` workflow".

**`<action>`**

Use the Write tool. Suggested skeleton:

```markdown
# Runbook — Databricks SYNC-03 verification

**Scope:** Verify SYNC-03 — Databricks consumer pulls wiki + DB
increments via existing `git pull` workflow on its repo checkout.
24h after the first SYNC-02 fire, `git log -1 kb/wiki/` on Databricks
should show a commit ≥ aim-4 deploy timestamp.

This runbook installs no new code, no new cron, no new service on
Databricks. It is verification-only.

## Preconditions

All of these must be TRUE before running this verification:

1. **aim-4-3 deployed on Hermes**: `omnigraph-daily-pull.timer` is
   `enabled` + `active` on Hermes (verifiable via `aim-4-3-EVIDENCE.md`).
2. **First SYNC-02 timer fire happened**: at least one natural fire of
   the daily-pull at 02:00 ADT after aim-4-3 deploy. (Manual fire from
   aim-4-3 Task 3 does NOT count — SYNC-03 wording says "24h after
   first SYNC-02 fire" which is the natural cadence.)
3. **Aliyun manual wiki commit ran**: at least one commit on `main` to
   `kb/wiki/` from Aliyun, post aim-4 deploy. (Per Q4c, this is the
   manual `git push` runbook in the sibling
   `aim-4-aliyun-wiki-commit.md`. Without it, Databricks `git pull`
   would not see new wiki content and verification would falsely
   "pass" with a stale pre-aim-4 commit.)

If any precondition is FALSE, defer verification.

## Verification command

```bash
# On Databricks (in the Databricks Repos checkout of OmniGraph-Vault)
cd <databricks-repo-checkout>

# Pull latest
git pull

# Inspect last commit touching kb/wiki/
git log -1 kb/wiki/ --format='%H %ai %s'
```

## Pass criterion

The timestamp from `git log -1 kb/wiki/` ≥ aim-4 deploy timestamp
(= aim-4-3 commit timestamp on `main`).

aim-4 deploy timestamp can be retrieved from:

```bash
# On corp dev box
git log -1 .planning/phases/aim-4-daily-sync/aim-4-3-EVIDENCE.md \
  --format='%ai'
```

(Or look up from `git log` on aim-4-3 commit hash.)

## Fail diagnosis

| Symptom | Diagnosis | Fix |
| --- | --- | --- |
| `git log -1 kb/wiki/` shows commit older than aim-4 deploy | Either Aliyun manual wiki commit didn't run yet (most likely), or Databricks `git pull` failed/skipped | Run the Aliyun wiki commit runbook; re-run `git pull` on Databricks; re-verify |
| `git pull` on Databricks fails | Databricks repo checkout has uncommitted changes / merge conflicts | Inspect `git status`; clean working tree; retry pull |
| Hermes systemd timer never fired | aim-4-3 deploy issue; check `systemctl list-timers omnigraph-daily-pull.timer` on Hermes | Re-deploy aim-4-3 if `Last triggered: n/a` after >24h |

## Captured evidence

When this verification passes, append to
`.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md`:

- Date of verification
- aim-4 deploy timestamp (reference)
- Aliyun wiki commit hash (the latest one referenced by `git log -1 kb/wiki/`)
- Databricks `git log -1 kb/wiki/` stdout
- Pass / fail verdict

## SYNC-03 Q4c trade-off

Per Q4c, manual Aliyun → repo wiki commit is the cadence during
aim-4..aim-5. If Aliyun's manual cadence lags > 24h, SYNC-03
verification slips to that lag window. This is the documented
trade-off, not a regression.

## References

- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` SYNC-03
- `.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md` FINDING 8
- `docs/runbooks/aim-4-aliyun-wiki-commit.md` (sibling runbook)
```

### Task 3 — Author evidence + commit

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` Lessons Learned 2026-05-06 #5 + 2026-05-15 #1
- Memory `feedback_git_add_explicit_in_parallel_quicks.md`

**`<acceptance_criteria>`**
- `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` exists.
- Contains: paths to both runbooks, aim-4 deploy timestamp reference,
  TODO for 24h-post-fire verification (deferred to aim-5 / operator).
- Single forward-only commit on `main` containing the 3 files (2
  runbooks + evidence).
- Commit message:
  `docs(aim-4): SYNC-03 verification + Aliyun wiki commit runbooks`.
- `git status` clean post-commit.

**`<action>`**

Write the evidence file:

```markdown
# aim-4-4 — SYNC-03 runbooks evidence

**Timestamp:** <ts>
**Plan:** aim-4-4
**REQs:** SYNC-03
**Status:** PARTIAL — runbooks committed; 24h-post-fire verification deferred

## Runbooks committed

- `docs/runbooks/aim-4-aliyun-wiki-commit.md` — Aliyun manual wiki commit (Q4c)
- `docs/runbooks/aim-4-databricks-sync03-verify.md` — SYNC-03 verification

## aim-4 deploy timestamp

- aim-4-3 commit on `main`: <hash> @ <ISO timestamp>
- This is the reference timestamp for SYNC-03 pass criterion.

## Deferred operator action (post-aim-4-4)

SYNC-03 verification cannot fully close in this plan's execution
window because:

1. The Hermes systemd timer needs at least one NATURAL fire at 02:00
   ADT (manual fire from aim-4-3 does not count per SYNC-03 wording
   "24h after first SYNC-02 fire").
2. Aliyun operator must execute the wiki commit runbook at least once
   post-aim-4 deploy.
3. Databricks operator must `git pull` on the consumer side.

**TODO** (track via aim-5 STAB checkpoint):

- [ ] Operator: run `docs/runbooks/aim-4-aliyun-wiki-commit.md`
      ≥ once post-aim-4 deploy.
- [ ] Verify: `omnigraph-daily-pull.timer` natural fire happened.
- [ ] Operator: run `docs/runbooks/aim-4-databricks-sync03-verify.md`
      24h after first natural fire.
- [ ] Append PASS verdict + Databricks `git log -1 kb/wiki/` stdout
      to this evidence file (forward-only edit, separate commit).

## References

- aim-4 CONTEXT.md FINDING 8 + §"Databricks SYNC-03 verification command"
- REQUIREMENTS SYNC-03
```

Commit:

```bash
git add docs/runbooks/aim-4-aliyun-wiki-commit.md \
        docs/runbooks/aim-4-databricks-sync03-verify.md \
        .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md
git status   # confirm only the 3 files staged
git commit -m "docs(aim-4): SYNC-03 verification + Aliyun wiki commit runbooks"
git log -1 --name-only
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| `docs/runbooks/` dir does not exist | `mkdir -p docs/runbooks` (will land as part of `git add`). |
| Sibling runbooks already exist with same name | Inspect content. If aim-4 already shipped these, this plan is a re-run; do not overwrite without diff review. |
| Forward-only correction needed post-commit | New commit `docs(aim-4): correction — <reason>`. Do NOT amend. |
| Post-natural-fire SYNC-03 verification fails | Inspect Aliyun manual wiki commit cadence; investigate Databricks `git pull` cadence. Append failure analysis to evidence file (forward-only edit). Do not retroactively edit runbooks unless the runbook itself is incorrect. |

## Evidence to capture

- 2 runbook files + evidence file in repo
- aim-4 deploy timestamp recorded in evidence
- TODO list for deferred operator verification
- Single forward-only commit hash
