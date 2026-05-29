# 260529-arx — Aliyun → Databricks data sync script (SUMMARY)

**Quick ID:** 260529-arx
**Date:** 2026-05-29
**Status:** ✅ **CLOSED 2026-05-29** — script + runbook authored; bash -n syntax OK; not pushed (awaiting user review)
**Duration:** ~30 min (Phase 0 recon 8 min, Phase 1 decide 3 min, Phase 2 write 12 min, Phase 3-5 verify+commit 7 min)

## Outcome

Authored `scripts/sync_to_databricks.sh` (190 LoC) + `scripts/sync_to_databricks.md` runbook wrapping the 22-step manual Aliyun → Databricks data-sync procedure validated 2026-05-28 in `260528-f1s` drift recovery. Single-command operator tool: `bash scripts/sync_to_databricks.sh`. Hands-off ~70 min at corp egress 0.77 MB/s.

## Files

| File | LoC | Purpose |
|---|---|---|
| `scripts/sync_to_databricks.sh` | 190 | 10-step bash script: pre-flight → SCP × 3 → fs cp × 3 → apps stop+start+deploy → smoke snippets echo |
| `scripts/sync_to_databricks.md` | 100 | Operator runbook — when to run, pre-flight checklist, failure modes, rollback, costs |

## What the script does (10 steps)

| Step | Action | ~Duration |
|---|---|---|
| 1 | Pre-flight: ssh + databricks CLI checks; warn+prompt if `_aliyun_pull/` has content | <5s |
| 2 | Prep `databricks-deploy/_aliyun_pull/{lightrag_storage,images,data}/` | <1s |
| 3 | SCP-1: tar lightrag_storage on Aliyun + scp + local extract (~2.6GB) | ~25-50min |
| 4 | SCP-2: tar images on Aliyun + scp + local extract (~892MB) | ~10-20min |
| 5 | SCP-3: scp kol_scan.db (~43MB; no tarball, it's small) | <1min |
| 6 | `databricks fs cp -r --overwrite` lightrag_storage → UC Volume | ~30min |
| 7 | `databricks fs cp -r --overwrite` images → UC Volume | ~18min |
| 8 | `databricks fs cp --overwrite` kol_scan.db → UC Volume | <1min |
| 9 | `apps stop` + `apps start` + `apps deploy` (memory: stop+start wipes deployment) | ~3min |
| 10 | Echo 4 paste-ready browser-console smoke snippets (no auto-run — needs SSO) | instant |

## Design notes

- **`echo ">>> Step N: ..."` pattern** matches `databricks-deploy/deploy.sh` styling so debug/log scanning feels consistent.
- **`|| { echo "STEP N FAILED"; exit N; }`** at every external-tool call — explicit halt with error code per step (set -e alone is too quiet).
- **Tar single-shot per directory** (not rsync) — tar at corp egress beats rsync per-file overhead on lightrag's many small JSON/graphml files.
- **Local extract verification implicit** — `tar xzf` errors out non-zero on truncation; `du -sh` after extract gives operator size check.
- **Smoke snippets echo only, NOT auto-execute** — smoke needs SSO browser session, not bash. User pastes 4 JS blocks into browser console.
- **`MSYS_NO_PATHCONV=1`** wrapping every `databricks fs cp` and `apps deploy` so Git Bash on Windows doesn't path-mangle `dbfs:/Volumes/...` or `/Workspace/...`.
- **Pre-flight prompt for `_aliyun_pull/` non-empty** lets operator decide whether to clear stale staging (drift recovery left content there); `read -p` on Step 1 only.

## Verification

| Check | Result |
|---|---|
| `bash -n scripts/sync_to_databricks.sh` | ✅ exit 0 (syntax OK) |
| `chmod +x scripts/sync_to_databricks.sh` | applied |
| `wc -l scripts/sync_to_databricks.sh` | 190 lines |
| `wc -l scripts/sync_to_databricks.md` | 100 lines |
| Aliyun data sizes (recon) | lightrag 2.6G + images 892M + kol_scan.db 43M = ~3.5GB at 0.77 MB/s = ~76 min budget |
| ssh alias `aliyun-vitaclaw` | ✅ present in `~/.ssh/config` |
| `_aliyun_pull/` exists in `databricks-deploy/.databricksignore` | ✅ guarded |
| UC Volume baseline `dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/` | ✅ data/ images/ lightrag_storage/ output/ + gcp-paid-sa.json (overwrite-target paths exist) |

## NOT executed

- Did not actually run the sync — too expensive (~70 min) for syntax-validation alone.
- Did not test apps stop+start+deploy cycle — destructive on prod, validated by 260528-f1s already.
- Did not run shellcheck (not installed on dev box).

## Constraints honored

| # | Constraint | Honored |
|---|---|---|
| A | One-way Aliyun → Databricks; no reverse logic | ✅ |
| B | No cron, no systemd timer | ✅ |
| C | Read-only on Aliyun side (tar + scp pull only) | ✅ |
| D | Don't touch daily-ingest / translate / Aliyun timers | ✅ |
| E | apps stop+start MUST be followed by apps deploy | ✅ Step 9c is `apps deploy --source-code-path` |
| F | Atomic commit, no push | ✅ commit only, push deferred |
| G | Chinese explanations, English artifacts | ✅ |
| H | No prod-grade retry/recovery/monitoring | ✅ explicit `STEP N FAILED` exit, operator handles |

## Discipline

- **Explicit `git add`** of the 4 files only (NEVER `-A`) per `feedback_git_add_explicit_in_parallel_quicks.md`
- **NO `--amend` / `git reset` / force-push** per `feedback_no_amend_in_concurrent_quicks.md`
- **Single forward-only commit** on main carrying script + runbook + PLAN + SUMMARY
- **`omonigraph` typo preserved** in path constants (Aliyun-side `~/.hermes/omonigraph-vault/`)

## Out of scope (stays as backlog)

- **Incremental sync** (rsync delta) — full pull is acceptable at 70 min for monthly cadence
- **Cron / timer registration** — user explicit: 手动不定期
- **`_aliyun_pull/` cleanup automation** — script just `ls` + prompt; operator decides
- **`smoke` automation** — needs SSO browser session, not bash; runbook documents the snippets
- **Image residue cleanup** — `fs cp -r --overwrite` merges (not replaces); old subdirs from prior syncs accumulate harmlessly. Tracked in 260528-f1s backlog.

## Cross-references

- Origin procedure: [260528-f1s SUMMARY](../260528-f1s-260528-aliyun-drift-recovery/260528-f1s-SUMMARY.md)
- Plan: [260529-arx-PLAN.md](./260529-arx-PLAN.md)
- Companion runbook: [scripts/sync_to_databricks.md](../../../scripts/sync_to_databricks.md)
- Script: [scripts/sync_to_databricks.sh](../../../scripts/sync_to_databricks.sh)
- Memory: `databricks_apps_stop_start_wipes_deployment`, `aliyun_vitaclaw_ssh`, `claude_databricks_deployment_autonomous`

## Status

**CLOSED 2026-05-29** — script + runbook + PLAN + SUMMARY committed atomically; bash -n syntax OK; **not pushed** (awaiting user review per constraint F).
