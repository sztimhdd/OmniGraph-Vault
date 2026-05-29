# sync_to_databricks.sh — Aliyun → Databricks data sync runbook

One-way data sync from Aliyun (data SoT) to Databricks UC Volume + app
restart with redeploy. Wraps the 22-step procedure validated 2026-05-28
in [.planning/quick/260528-f1s-260528-aliyun-drift-recovery/SUMMARY.md](../.planning/quick/260528-f1s-260528-aliyun-drift-recovery/260528-f1s-SUMMARY.md).

User runs **manually, no cron, no timer**. Typical cadence: ~monthly when
~50+ new articles have been ingested on Aliyun and you want them visible
on Databricks.

## When to run

- New ingest delta accumulated on Aliyun (~50+ articles since last sync)
- Monthly cadence regardless of delta
- After Aliyun-side schema or LightRAG storage changes you want reflected on Databricks

## Pre-flight checklist

1. **Aliyun is quiet.** No active daily-ingest / translate run (avoid SQLite
   lock during DB SCP). Check via: `ssh aliyun-vitaclaw "ps aux | grep -E 'ingest|translate' | grep -v grep"`
2. **Databricks app is currently RUNNING.** Verify via:
   `databricks --profile dev apps get omnigraph-kb -o json | grep state`
   (If the app is already stopped, Step 9 still works; but you want to know
   the baseline before tearing it down.)
3. **Code is in sync.** This script syncs DATA only — it reuses whatever
   `_ssg/` + Python code is currently in the workspace. If you have new code
   to ship, run `bash databricks-deploy/deploy.sh` FIRST, then this script.
4. **You have ~70 minutes of unattended time.** Bandwidth-bound on corp
   egress (~0.77 MB/s measured). The script will block at Steps 3, 4, 6, 7
   for the SCP and UC Volume push. Step 1 prompts y/N if `_aliyun_pull/`
   has stale content; everything else is hands-off.

## Run

```bash
bash scripts/sync_to_databricks.sh
```

## What it does (10 steps)

| Step | Action | ~Duration |
|---|---|---|
| 1 | Pre-flight: ssh + databricks CLI checks; warn if `_aliyun_pull/` not empty | <5s |
| 2 | Prep `databricks-deploy/_aliyun_pull/{lightrag_storage,images,data}/` | <1s |
| 3 | SCP-1: tar lightrag_storage on Aliyun, scp, extract locally (~2.6GB) | ~25-50min |
| 4 | SCP-2: tar images on Aliyun, scp, extract locally (~892MB) | ~10-20min |
| 5 | SCP-3: scp kol_scan.db (~43MB) | <1min |
| 6 | `databricks fs cp -r --overwrite` lightrag_storage → UC Volume | ~30min |
| 7 | `databricks fs cp -r --overwrite` images → UC Volume | ~18min |
| 8 | `databricks fs cp --overwrite` kol_scan.db → UC Volume | <1min |
| 9 | `apps stop` + `apps start` + `apps deploy` (memory: stop+start wipes deployment) | ~3min |
| 10 | Echo 4 paste-ready browser-console smoke snippets | instant |

Total wall-clock: **~70 min** at corp egress 0.77 MB/s. Network-bound; CPU
is idle most of the time.

## Smoke verification (Step 10)

The script outputs 4 JS snippets you paste into your browser console while
logged into the app via SSO. Expected results:

| # | Endpoint | Expected |
|---|---|---|
| 1 | `GET /health` | `status=ok version=2.0.0` |
| 2 | `GET /api/articles?limit=5` | `total > 270` (or whatever your Aliyun snapshot count was) |
| 3 | `GET /api/search?q=AI&mode=fts` | non-empty `results` |
| 4 | `POST /api/synthesize` long_form | `status=done`, `fallback_used=false`, real markdown in `result.response` (NOT fts5_fallback) |

Smoke 4 takes ~80 seconds (LightRAG cold-start ~30s + hybrid query ~50s on
Databricks /tmp tmpfs). The browser console will print poll updates every
5 seconds; clearInterval fires when status flips.

## Failure modes + recovery

| Symptom | Fix |
|---|---|
| Step 1 ssh fails | Check `~/.ssh/config` has `Host aliyun-vitaclaw` block. Memory: [aliyun_vitaclaw_ssh](../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/aliyun_vitaclaw_ssh.md). |
| Step 1 databricks CLI fails | `databricks auth login --profile dev` to refresh OAuth. |
| Step 3/4 SCP times out mid-pull | Tar archive on Aliyun is preserved at `/tmp/*.tar.gz` for ~24h until `/tmp` rotates. Re-run script — Aliyun-side cleanup at the end of each step is best-effort, so re-tar wastes a few minutes but is safe. To save the round trip: `ssh aliyun-vitaclaw "ls -la /tmp/*.tar.gz"` to confirm tarball exists, then resume manually with scp + tar x. |
| Step 6/7 fs cp times out | Re-run script. UC Volume `--overwrite` is safe to repeat. (Memory: cp `-r --overwrite` MERGES, doesn't replace — old subdirs may linger; harmless but tracked as "Aliyun-side UC Volume historical image residue" backlog.) |
| Step 9b state=UNAVAILABLE persists | Step 9c redeploy is the fix per memory [databricks_apps_stop_start_wipes_deployment](../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/databricks_apps_stop_start_wipes_deployment.md). If Step 9c also fails, manually run: `databricks --profile dev apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy` |
| Step 9c "no source code at workspace path" | Workspace `databricks-deploy/` has nothing to deploy. Run `bash databricks-deploy/deploy.sh` first to push code, then re-run this script. |
| Smoke 4 returns `fallback_used=true` | LightRAG hydrate failed. Check Databricks app logs via `make logs` (memory: [databricks_apps_logs_websocket](../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/databricks_apps_logs_websocket.md)). Common cause: `lightrag_storage/` push truncated; re-run script. |

## Manual rollback

This script does not have an explicit rollback. Recovery options:

1. **Stale `_aliyun_pull/`:** `rm -rf databricks-deploy/_aliyun_pull/*` to clear
   local staging; re-run the script.
2. **Bad UC Volume push:** Re-run the script. `--overwrite` is idempotent.
3. **App deployment failed:** Run `bash databricks-deploy/deploy.sh` to redeploy
   from the canonical code path.

The previous Databricks UC Volume snapshot is overwritten by Step 6-8;
there is no automatic backup. If you need to roll back to a known-good
data snapshot, re-run sync from the same Aliyun state via this script
(or revert Aliyun first via its own snapshot mechanism, if any).

## Known costs

- **Aliyun bandwidth:** outbound traffic for ~3.5GB tarballs. Aliyun ECS
  outbound is metered; check your billing config.
- **Local disk:** `databricks-deploy/_aliyun_pull/` will hold ~3.5GB
  uncompressed after Step 5. `.databricksignore` prevents this from
  being uploaded to the workspace.
- **Databricks UC Volume:** overwrites in place — no incremental
  storage cost.
- **App downtime:** Step 9a-9c wipes + redeploys. Total downtime ~2-3
  minutes from `apps stop` to `apps deploy` returning success.

## Cross-references

- Origin procedure: [260528-f1s SUMMARY](../.planning/quick/260528-f1s-260528-aliyun-drift-recovery/260528-f1s-SUMMARY.md) — D4 SCP-1 through Pass 3 (2nd) deploy
- Code+SSG deploy: [databricks-deploy/deploy.sh](../databricks-deploy/deploy.sh) — runs FIRST when shipping new code
- Reverse direction (Hermes ← Aliyun): [scripts/sync-from-aliyun.sh](sync-from-aliyun.sh) — separate, unrelated
