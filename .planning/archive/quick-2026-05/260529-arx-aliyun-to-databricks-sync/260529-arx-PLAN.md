# 260529-arx — Aliyun → Databricks data sync script (PLAN)

**Quick ID:** 260529-arx
**Date:** 2026-05-29
**Mode:** quick (interactive, ad-hoc operator tooling)
**Goal:** Wrap the 22-step manual procedure validated 2026-05-28 (260528-f1s drift recovery) into a reusable bash script + runbook for ad-hoc, user-triggered Aliyun → Databricks data sync.

## Context

User runs the sync manually, no cron / no timer (per requirement #4 "手动不定期"). Aliyun = data SoT (daily-ingest + translate cron); Databricks = read-only replica served via UC Volume + omnigraph-kb app. Reverse direction (Databricks → Aliyun) does not exist.

## Recon (Phase 0 READ-ONLY)

| Source | Finding |
|---|---|
| `.planning/quick/260528-f1s-260528-aliyun-drift-recovery/260528-f1s-SUMMARY.md` | 22-step procedure (D5 backfill + SCP-1/2/3 + UC Volume push + apps stop+start+deploy + smoke 4) verified GREEN |
| `databricks-deploy/deploy.sh` | Reference for echo `>>> Step N` styling; `MSYS_NO_PATHCONV=1` wrapping for `/Workspace/`+`dbfs:/Volumes/` paths |
| `scripts/sync-from-aliyun.sh` | Reverse direction (Hermes ← Aliyun) — different shape, not directly reusable |
| `ssh aliyun-vitaclaw "du -sh ..."` | lightrag_storage 2.6G, images 892M, kol_scan.db 43M (symlink → /root/OmniGraph-Vault/data/kol_scan.db) |
| `databricks fs ls $UC_VOLUME -o json` | Existing UC Volume layout: data/ + images/ + lightrag_storage/ + output/ + gcp-paid-sa.json (data/images/lightrag baseline = 1969-12-31 placeholder; first sync overwrites) |
| `~/.ssh/config` | Host `aliyun-vitaclaw` block present (host=101.133.154.49, port=22, key=aliyun_orchestrator_ed25519) |
| `databricks-deploy/.databricksignore` | `_aliyun_pull/` already covered (drift recovery added it) |

## DECIDE (3 candidates → user-locked)

| # | Question | User pick | Rationale |
|---|---|---|---|
| D1 | Script path | (a) `scripts/sync_to_databricks.sh` | Symmetric with `scripts/sync-from-aliyun.sh` (reverse direction); sync scripts unified under scripts/ |
| D2 | Local staging | (a) `databricks-deploy/_aliyun_pull/` | Reuses drift-recovery validated path; `.databricksignore` already guards |
| D3 | SSH config | (a) `~/.ssh/config` alias `aliyun-vitaclaw` | Already configured; Memory `aliyun_vitaclaw_ssh.md` documents the alias; cleanest script (no env vars, no MD parsing) |

## Atomic execution sequence (the script wraps these steps)

```
1.  Pre-flight: ssh + databricks CLI auth checks; warn if _aliyun_pull/ has stale content
2.  Prep local staging (_aliyun_pull/{lightrag_storage,images,data}/)
3.  SCP-1: tar lightrag_storage on Aliyun → scp → local extract → cleanup Aliyun /tmp tarball
4.  SCP-2: tar images → scp → local extract → cleanup
5.  SCP-3: scp kol_scan.db (no tarball — it's small)
6.  databricks fs cp -r --overwrite lightrag_storage → UC Volume
7.  databricks fs cp -r --overwrite images → UC Volume
8.  databricks fs cp --overwrite kol_scan.db → UC Volume
9.  apps stop + apps start + apps deploy (memory: stop+start wipes deployment artifact)
10. Echo 4 paste-ready browser-console smoke snippets (/health, /api/articles, /api/search?mode=fts, /api/synthesize long_form)
```

Total wall-clock ~70 min at corp egress 0.77 MB/s (bandwidth-bound).

## Halt triggers

- H1: ssh alias unreachable in Step 1 → exit 1, fix ~/.ssh/config
- H2: databricks CLI not authenticated → exit 1, run `databricks auth login --profile dev`
- H3: SCP fails mid-step → exit (3-5), Aliyun /tmp tarball preserved for resume
- H4: UC Volume push fails → exit (6-8), re-run script (`--overwrite` is idempotent)
- H5: apps stop+start state=UNAVAILABLE persists → Step 9c `apps deploy` is the fix (memory `databricks_apps_stop_start_wipes_deployment`)

## Out of scope

- Incremental sync (rsync delta). Simple full pull is acceptable at 70 min.
- Cron / systemd timer. User explicit: "手动不定期".
- Reverse Hermes ← Aliyun sync. `scripts/sync-from-aliyun.sh` already covers it.
- Cleanup of `_aliyun_pull/` residue. Script just `ls` and warn — user decides.
- Touching `.databricksignore`. Already configured by drift recovery.

## Cross-references

- Origin procedure: [260528-f1s SUMMARY](../260528-f1s-260528-aliyun-drift-recovery/260528-f1s-SUMMARY.md) — D4 SCP-1 through Pass 3 (2nd) deploy + the apps stop+start surprise
- Companion runbook: [scripts/sync_to_databricks.md](../../../scripts/sync_to_databricks.md)
- Memory: `databricks_apps_stop_start_wipes_deployment` (the stop+start surprise)
- Memory: `aliyun_vitaclaw_ssh` (SSH alias documentation)
