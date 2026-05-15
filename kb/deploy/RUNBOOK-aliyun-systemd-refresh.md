# RUNBOOK — Aliyun systemd unit refresh for kb-v2.1-1 KG-mode hardening

**Author:** kb-v2.1-1 phase (2026-05-15)
**Audience:** vitaclaw-site go-live agent OR human operator on Aliyun ECS
**Goal:** Apply the kb-v2.1-1 memory bounds + KG-mode env-var changes to the
running `kb-api.service`, with zero downtime and a documented rollback path.

## Background

Production observation 2026-05-14 (Aliyun ECS, 3.4Gi RAM):

1. KG search triggered LightRAG embedding init. Logged error referencing
   `/home/sztimhdd/.hermes/gcp-paid-sa.json` — that path does not exist on
   Aliyun (user is `kb`, not `sztimhdd`).
2. One KG search exhausted memory — `kb-api.service` was OOM-killed; systemd
   auto-restart recovered, but the host became fragile to KG-mode traffic.

Phase kb-v2.1-1 closes this:

- **Code change** (already on `origin/main`): `kb-api` now boots in
  controlled-degraded mode when `KB_KG_GCP_SA_KEY_PATH` /
  `GOOGLE_APPLICATION_CREDENTIALS` are unset OR point to a missing/unreadable
  file. `/api/search?mode=kg` returns HTTP 200 with `kg_unavailable=true`
  instead of 500.
- **Operator change** (this RUNBOOK): refresh the systemd unit to add
  `MemoryMax=2G` + `MemoryHigh=1.5G` + start-limit guards.

## Pre-flight

```bash
# 1. Confirm the host is at or past the kb-v2.1-1 commit on origin/main
cd /home/kb/OmniGraph-Vault
git fetch --quiet origin
git log --oneline origin/main -5
# expect: most recent commit subject mentions kb-v2.1-1 KG mode hardening

# 2. Pull latest (fast-forward only — no surprise merges)
git pull --ff-only origin main

# 3. Confirm the new kb/deploy/kb-api.service reference is present
ls -la kb/deploy/kb-api.service
```

## Apply the refresh

```bash
# 4. Capture current systemd unit BEFORE editing — for rollback
sudo cp /etc/systemd/system/kb-api.service \
        /etc/systemd/system/kb-api.service.bak-$(date +%Y%m%d-%H%M%S)

# 5. Diff the current vs new reference (manual review)
sudo diff /etc/systemd/system/kb-api.service \
          /home/kb/OmniGraph-Vault/kb/deploy/kb-api.service

# 6. Apply the new unit. Either:
#    (a) overwrite wholesale if your unit matches the reference layout
sudo cp /home/kb/OmniGraph-Vault/kb/deploy/kb-api.service \
        /etc/systemd/system/kb-api.service
#    OR (b) hand-merge ONLY these directives into your existing [Service]:
#        MemoryHigh=1.5G
#        MemoryMax=2G
#        CPUQuota=200%
#        Restart=on-failure
#        RestartSec=5
#        StartLimitBurst=5
#        StartLimitIntervalSec=60
#    The KB_KG_GCP_SA_KEY_PATH env var is OPTIONAL — leave it unset for
#    controlled-degraded boot (recommended on Aliyun until a real SA JSON
#    is provisioned).

# 7. Reload + restart
sudo systemctl daemon-reload
sudo systemctl restart kb-api.service
```

## Verify

```bash
# 8. Service is up
sudo systemctl status kb-api.service --no-pager
# expect: active (running), recent log lines do NOT include OOM

# 9. Memory bounds applied (cgroup view)
sudo systemctl show kb-api.service -p MemoryMax -p MemoryHigh
# expect: MemoryMax=2147483648 (2G), MemoryHigh=1610612736 (1.5G)

# 10. Health endpoint live
curl -sS http://127.0.0.1:8766/health
# expect: {"status":"ok",...}

# 11. KG-mode controlled-degraded behaviour (assumes no SA JSON yet)
curl -sS -o /tmp/kg-resp.json -w '%{http_code}\n' \
    "http://127.0.0.1:8766/api/search?q=langchain&mode=kg"
# expect: HTTP code 200
cat /tmp/kg-resp.json
# expect: {"items":[],"total":0,"mode":"kg","kg_unavailable":true,
#          "reason":"kg_disabled" OR "kg_credentials_missing",
#          "fallback_suggestion":"Use mode=fts ..."}

# 12. FTS mode unaffected
curl -sS "http://127.0.0.1:8766/api/search?q=langchain&mode=fts" | head -c 400
# expect: regular {items:[...], total: N, mode:"fts"} response

# 13. Watch for ~5 minutes — confirm no restart loop
sudo journalctl -u kb-api.service --since "5 minutes ago" | grep -E "Started|Stopped|killed"
# expect: at most 1 "Started" entry from step 7; nothing about killed/OOM
```

## Rollback

If verification fails:

```bash
# Restore the prior unit file
sudo cp /etc/systemd/system/kb-api.service.bak-<timestamp> \
        /etc/systemd/system/kb-api.service
sudo systemctl daemon-reload
sudo systemctl restart kb-api.service

# The code change on origin/main is forward-compatible (the kb_unavailable
# response shape is additive; existing clients that ignored the new fields
# keep working). No git revert needed for code unless a new bug surfaces.
```

## Notes

- The kb-v2.1-1 code makes `KB_KG_GCP_SA_KEY_PATH` and
  `GOOGLE_APPLICATION_CREDENTIALS` optional from the kb-api perspective. KG
  mode is "off-by-default-on-Aliyun" until the operator provisions a real
  SA JSON and sets the env var.
- Once a real SA JSON is provisioned: drop it at `/home/kb/.hermes/gcp-paid-sa.json`
  (mode 0400, owner kb), then add
  `Environment=KB_KG_GCP_SA_KEY_PATH=/home/kb/.hermes/gcp-paid-sa.json` plus
  `Environment=GOOGLE_CLOUD_PROJECT=...` + `Environment=GOOGLE_CLOUD_LOCATION=global`
  to the unit and `daemon-reload + restart`. The flag will flip at next boot.
- The 2G memory cap is conservative for the current article volume (~94
  articles in graph as of 2026-05-15). Re-evaluate when the corpus crosses
  500 articles or when KG queries exceed 50/day on Aliyun.
