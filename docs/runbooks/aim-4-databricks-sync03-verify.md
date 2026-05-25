# Runbook — Databricks SYNC-03 verification

**Scope:** Verify SYNC-03 — the Databricks consumer pulls wiki + DB
increments via its existing `git pull` workflow on the repo checkout.
24h after the first SYNC-02 fire (Hermes daily-pull timer's first
**natural** fire at 02:00 ADT), running `git log -1 kb/wiki/` on
Databricks should show a commit timestamp ≥ the aim-4 deploy
timestamp.

**This runbook installs no new code on Databricks; uses existing
`git pull` workflow.** No new cron, no new service, no new container
config — verification only.

## Preconditions

All of these must be TRUE before running this verification, otherwise
defer:

1. **aim-4-3 deployed on Hermes** —
   `omnigraph-daily-pull.timer` is `enabled` + `active` on Hermes
   (see `aim-4-3-EVIDENCE.md`).
2. **First SYNC-02 timer fire happened naturally** — at least one
   natural fire of the daily-pull at 02:00 ADT after aim-4-3 deploy.
   The manual fire from aim-4-3 Task 3 does **not** count — SYNC-03
   wording says "24h after first SYNC-02 fire" which is the natural
   cadence.
3. **Aliyun manual wiki commit ran** — at least one commit on `main`
   touching `kb/wiki/` from Aliyun, post aim-4 deploy. Per Q4c, this
   is the manual `git push` runbook in the sibling
   `aim-4-aliyun-wiki-commit.md`. Without it, Databricks `git pull`
   would not see new wiki content and verification would falsely
   "pass" with a stale pre-aim-4 commit.

If any precondition is FALSE, defer verification.

## Verification command

```bash
# On Databricks — in the Databricks Repos checkout of OmniGraph-Vault
cd <databricks-repo-checkout>

# Pull latest (this is the existing workflow — no new code)
git pull

# Inspect last commit touching kb/wiki/
git log -1 kb/wiki/ --format='%H %ai %s'

# Cross-check the deploy/hermes systemd files used by aim-4 (timer / service)
git log -1 -- deploy/hermes/systemd/ --format='%H %ai %s' 2>/dev/null || \
  git log -1 -- scripts/sync-from-aliyun.sh --format='%H %ai %s'
```

## Pass criterion

The timestamp from `git log -1 kb/wiki/` ≥ **aim-4 deploy timestamp**
(= aim-4-3 commit timestamp on `main`).

The aim-4 deploy timestamp can be retrieved on the corp dev box:

```bash
# Find the aim-4-3 systemd-install commit on main
git log --oneline --all --grep='aim-4-3\|daily-pull systemd\|SYNC-02' | head -5

# Then for that hash:
git log -1 <aim-4-3-hash> --format='%ai'
```

The aim-4 deploy timestamp is also recorded in this plan's evidence
file `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` for
quick lookup.

## Fail diagnosis

| Symptom | Diagnosis | Fix |
| --- | --- | --- |
| `git log -1 kb/wiki/` shows commit older than aim-4 deploy timestamp | Most likely: Aliyun manual wiki commit didn't run yet. Less likely: Databricks `git pull` failed/skipped silently. | Run `docs/runbooks/aim-4-aliyun-wiki-commit.md` on Aliyun; re-run `git pull` on Databricks; re-verify. |
| `git pull` on Databricks fails with merge conflict / dirty tree | Databricks repo checkout has uncommitted local changes | Inspect `git status`; clean working tree (commit / stash / discard as appropriate); retry pull. |
| Hermes systemd timer never fired naturally | aim-4-3 deploy issue. Check `systemctl list-timers omnigraph-daily-pull.timer` on Hermes. | If `Last triggered: n/a` after >24h post-deploy, re-deploy aim-4-3 (timer not enabled or `Persistent=true` not honored on offline host). |
| `git log -1 kb/wiki/` returns nothing | `kb/wiki/` directory does not exist in the Databricks checkout (very stale repo) | `git pull` then re-check. If still empty, the milestone has not produced wiki content yet — defer verification until the first wiki commit lands. |

## Captured evidence

When this verification passes, append the following to
`.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` (forward-only
edit, separate commit — never amend):

- Date of verification (ISO timestamp)
- aim-4 deploy timestamp (reference, copied from same evidence file)
- Aliyun wiki commit hash (the latest one referenced by `git log -1 kb/wiki/`)
- Databricks `git log -1 kb/wiki/` stdout (verbatim copy)
- PASS / FAIL verdict

## SYNC-03 Q4c trade-off

Per Q4c, manual Aliyun → repo wiki commit is the cadence during
aim-4..aim-5. If Aliyun's manual cadence lags > 24h, SYNC-03
verification slips to that lag window. This is the documented
trade-off, not a regression. Auto-write-back is deferred to
`LLM-Wiki-Integration-P2`.

## References

- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` SYNC-03
- `.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md` FINDING 8
- `docs/runbooks/aim-4-aliyun-wiki-commit.md` (sibling runbook)
