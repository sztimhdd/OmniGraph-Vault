#!/usr/bin/env bash
# scripts/sync_to_databricks.sh — Aliyun → Databricks one-way data sync.
#
# Pulls lightrag_storage + images + kol_scan.db from Aliyun (data SoT),
# pushes them to Databricks UC Volume, restarts the omnigraph-kb app with
# redeploy. Wraps the 22-step manual procedure validated 2026-05-28 in
# .planning/quick/260528-f1s-260528-aliyun-drift-recovery/SUMMARY.md.
#
# This is data-only sync. It does NOT re-bake _ssg/ or push code to the
# workspace; for code+SSG sync run databricks-deploy/deploy.sh first, then
# this script. The redeploy at Step 9 reuses whatever artifact is currently
# in $WORKSPACE_ROOT/databricks-deploy.
#
# Usage:
#   bash scripts/sync_to_databricks.sh
#
# Requires:
#   - SSH alias 'aliyun-vitaclaw' in ~/.ssh/config (verified 2026-05-29)
#   - databricks --profile dev configured (~/.databrickscfg)
#   - Run from a shell where 'databricks' CLI is on PATH (Git Bash on Windows OK;
#     MSYS_NO_PATHCONV=1 wrapping handles /Workspace/ + dbfs:/Volumes/ paths)
#
# Companion runbook: scripts/sync_to_databricks.md
#
# 2026-06-XX — post v1.1.qdrant-migration cutover: vdb_*.json under
# lightrag_storage/ is now derived from Qdrant docker on Aliyun by a 6h
# converter cron (qdrant-snapshot.timer + scripts/qdrant_to_nanovdb.py).
# The on-disk schema is unchanged for consumers (nano_vectordb format —
# embedding_dim + data[] + base64-float32 matrix string), so this sync
# script needs ZERO behavior change. Schema reference: T2 commit a3b08eb.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
ASSUME_YES=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help)
      echo "Usage: $0 [-y|--yes]"
      echo "  -y, --yes   Skip the Step 1 staging-overwrite confirm prompt"
      echo "              (required when stdin is not a tty, e.g. background runs)"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Config (edit if Aliyun paths change)
# ---------------------------------------------------------------------------
ALIYUN_SSH=aliyun-vitaclaw
ALIYUN_LIGHTRAG=/root/.hermes/omonigraph-vault/lightrag_storage
ALIYUN_IMAGES=/root/.hermes/omonigraph-vault/images
ALIYUN_DB=/root/OmniGraph-Vault/data/kol_scan.db   # symlink target on Aliyun

LOCAL_STAGING=databricks-deploy/_aliyun_pull       # .databricksignore'd
UC_VOLUME=dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault
APP_NAME=omnigraph-kb
WORKSPACE_ROOT=/Workspace/Users/hhu@edc.ca/omnigraph-kb
PROFILE=dev

cd "$(dirname "$0")/.."
echo ">>> CWD: $(pwd)"
echo ">>> Quick reference: 22-step drift recovery 2026-05-28 (260528-f1s)"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Pre-flight checks (read-only)
# ---------------------------------------------------------------------------
echo ">>> Step 1: pre-flight checks"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$ALIYUN_SSH" "echo aliyun-ssh-ok" \
  || { echo "STEP 1 FAILED: ssh alias '$ALIYUN_SSH' not reachable. Check ~/.ssh/config."; exit 1; }

databricks --profile "$PROFILE" current-user me >/dev/null \
  || { echo "STEP 1 FAILED: databricks CLI profile '$PROFILE' not authenticated. Run 'databricks auth login --profile $PROFILE'."; exit 1; }

if [ -d "$LOCAL_STAGING" ] && [ -n "$(ls -A "$LOCAL_STAGING" 2>/dev/null)" ]; then
  echo ""
  echo "WARNING: $LOCAL_STAGING already has content from a previous sync:"
  ls -la "$LOCAL_STAGING/" | head -10
  echo ""
  echo "Step 3-5 SCP will OVERWRITE these. If you want a clean slate, Ctrl+C now"
  echo "and run: rm -rf $LOCAL_STAGING/*"
  echo ""
  if [ "$ASSUME_YES" = "1" ]; then
    echo "  --yes given, proceeding without prompt"
  elif [ -t 0 ]; then
    read -p "Continue? [y/N] " -r confirm
    [ "$confirm" = "y" ] || [ "$confirm" = "Y" ] || { echo "Aborted by user."; exit 0; }
  else
    echo "ERROR: stdin not a tty and --yes not given. Re-run with --yes." >&2
    exit 3
  fi
fi

echo "  ssh ok, databricks CLI ok"

# ---------------------------------------------------------------------------
# Step 2: Prep local staging
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 2: prep local staging $LOCAL_STAGING"
mkdir -p "$LOCAL_STAGING/lightrag_storage" "$LOCAL_STAGING/images" "$LOCAL_STAGING/data"

# ---------------------------------------------------------------------------
# Step 3: SCP-1 lightrag_storage (~2.6GB, ~25-50min at corp 0.77 MB/s)
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 3: SCP lightrag_storage from Aliyun (~2.6GB)"
echo "  (Step 3 carries Qdrant-derived vdb_*.json from $ALIYUN_LIGHTRAG/, refreshed every 6h by qdrant-snapshot.timer — see v1.1.qdrant-migration phase, T2 commit a3b08eb)"
echo "  Aliyun: tar czf /tmp/lightrag_storage.tar.gz $ALIYUN_LIGHTRAG"
ssh "$ALIYUN_SSH" "cd $(dirname "$ALIYUN_LIGHTRAG") && tar czf /tmp/lightrag_storage.tar.gz $(basename "$ALIYUN_LIGHTRAG")/" \
  || { echo "STEP 3 FAILED: Aliyun tar"; exit 3; }

echo "  scp /tmp/lightrag_storage.tar.gz → $LOCAL_STAGING/"
scp "$ALIYUN_SSH:/tmp/lightrag_storage.tar.gz" "$LOCAL_STAGING/" \
  || { echo "STEP 3 FAILED: scp"; exit 3; }

echo "  local extract"
rm -rf "$LOCAL_STAGING/lightrag_storage"
tar xzf "$LOCAL_STAGING/lightrag_storage.tar.gz" -C "$LOCAL_STAGING/" \
  || { echo "STEP 3 FAILED: local tar x"; exit 3; }
rm -f "$LOCAL_STAGING/lightrag_storage.tar.gz"

echo "  Aliyun cleanup"
ssh "$ALIYUN_SSH" "rm -f /tmp/lightrag_storage.tar.gz" || true

du -sh "$LOCAL_STAGING/lightrag_storage" || true

# ---------------------------------------------------------------------------
# Step 4: SCP-2 images (~892MB, ~10-20min)
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 4: SCP images from Aliyun (~892MB)"
ssh "$ALIYUN_SSH" "cd $(dirname "$ALIYUN_IMAGES") && tar czf /tmp/images.tar.gz $(basename "$ALIYUN_IMAGES")/" \
  || { echo "STEP 4 FAILED: Aliyun tar"; exit 4; }

scp "$ALIYUN_SSH:/tmp/images.tar.gz" "$LOCAL_STAGING/" \
  || { echo "STEP 4 FAILED: scp"; exit 4; }

rm -rf "$LOCAL_STAGING/images"
tar xzf "$LOCAL_STAGING/images.tar.gz" -C "$LOCAL_STAGING/" \
  || { echo "STEP 4 FAILED: local tar x"; exit 4; }
rm -f "$LOCAL_STAGING/images.tar.gz"

ssh "$ALIYUN_SSH" "rm -f /tmp/images.tar.gz" || true

du -sh "$LOCAL_STAGING/images" || true

# ---------------------------------------------------------------------------
# Step 5: SCP-3 kol_scan.db (~43MB, ~30s)
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 5: SCP kol_scan.db from Aliyun (~43MB)"
scp "$ALIYUN_SSH:$ALIYUN_DB" "$LOCAL_STAGING/data/kol_scan.db" \
  || { echo "STEP 5 FAILED: scp"; exit 5; }
ls -la "$LOCAL_STAGING/data/kol_scan.db"

# ---------------------------------------------------------------------------
# Step 6: Push UC Volume — lightrag_storage (memory: fs cp -r --overwrite merges, not replaces)
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 6: push lightrag_storage → $UC_VOLUME/lightrag_storage/"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" fs cp -r --overwrite \
  "$LOCAL_STAGING/lightrag_storage" "$UC_VOLUME/lightrag_storage" \
  || { echo "STEP 6 FAILED"; exit 6; }

# ---------------------------------------------------------------------------
# Step 7: Push UC Volume — images
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 7: push images → $UC_VOLUME/images/"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" fs cp -r --overwrite \
  "$LOCAL_STAGING/images" "$UC_VOLUME/images" \
  || { echo "STEP 7 FAILED"; exit 7; }

# ---------------------------------------------------------------------------
# Step 8: Push UC Volume — kol_scan.db
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 8: push kol_scan.db → $UC_VOLUME/data/kol_scan.db"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" fs cp --overwrite \
  "$LOCAL_STAGING/data/kol_scan.db" "$UC_VOLUME/data/kol_scan.db" \
  || { echo "STEP 8 FAILED"; exit 8; }

# ---------------------------------------------------------------------------
# Step 9: Restart app (memory: stop+start wipes deployment artifact, must redeploy)
# ---------------------------------------------------------------------------
echo ""
echo ">>> Step 9a: stop $APP_NAME"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps stop "$APP_NAME" \
  || { echo "STEP 9a FAILED"; exit 9; }

echo ""
echo ">>> Step 9b: start $APP_NAME (state will be UNAVAILABLE until redeploy)"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps start "$APP_NAME" \
  || { echo "STEP 9b FAILED"; exit 9; }

# 'apps start' implicitly creates a SNAPSHOT pending deployment from the
# last-known source_code_path. Step 9c 'apps deploy' will race that pending
# and 409 with 'Cannot deploy ... pending deployment in progress'. Poll
# until the auto-pending clears (state empty or SUCCEEDED) before 9c.
echo ""
echo ">>> Step 9b': wait for auto-pending deployment from apps start to clear"
if command -v jq >/dev/null 2>&1; then
  jq_available=1
else
  jq_available=0
fi
for i in $(seq 1 30); do
  app_json=$(MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps get "$APP_NAME" -o json 2>/dev/null || echo '')
  if [ "$jq_available" = "1" ]; then
    pending_state=$(printf '%s' "$app_json" | jq -r '.pending_deployment.status.state // ""')
  else
    # grep-only fallback: extract pending_deployment block first 200 chars,
    # then grab the first "state":"..." inside it. Brittle but works for the
    # current API response shape (verified 2026-05-29).
    pending_state=$(printf '%s' "$app_json" | grep -o '"pending_deployment".*' | head -c 400 | grep -o '"state":"[^"]*"' | head -1 | cut -d'"' -f4)
  fi
  if [ -z "$pending_state" ] || [ "$pending_state" = "SUCCEEDED" ]; then
    echo "  pending cleared (iter $i, state='$pending_state')"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "STEP 9b' FAILED: pending deployment still '$pending_state' after 30min"
    exit 9
  fi
  echo "  pending state='$pending_state' (iter $i/30, sleep 60s)"
  sleep 60
done

echo ""
echo ">>> Step 9c: redeploy $APP_NAME from $WORKSPACE_ROOT/databricks-deploy"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_ROOT/databricks-deploy" \
  || { echo "STEP 9c FAILED"; exit 9; }

echo ""
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps get "$APP_NAME" -o json | head -30

# ---------------------------------------------------------------------------
# Step 10: Smoke snippets (paste into browser console while logged into the app)
# ---------------------------------------------------------------------------
APP_URL=$(MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps get "$APP_NAME" -o json \
  | grep -o '"url"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
APP_URL=${APP_URL:-https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com}

echo ""
echo "================================================================"
echo "Sync complete. Run these 4 smoke checks in your BROWSER CONSOLE"
echo "(while logged into the app via SSO):"
echo "================================================================"
echo ""
echo "// Smoke 1: health"
echo "fetch('$APP_URL/health').then(r => r.json()).then(console.log);"
echo ""
echo "// Smoke 2: articles list (expect total > 270)"
echo "fetch('$APP_URL/api/articles?limit=5').then(r => r.json()).then(d => console.log('total:', d.total, 'first:', d.items[0]));"
echo ""
echo "// Smoke 3: FTS search (expect non-empty hits)"
echo "fetch('$APP_URL/api/search?q=AI&mode=fts').then(r => r.json()).then(d => console.log('hits:', d.results?.length));"
echo ""
echo "// Smoke 4: synthesize long_form (expect markdown, NOT fts5_fallback; ~80s)"
echo "fetch('$APP_URL/api/synthesize', {method:'POST', headers:{'Content-Type':'application/json'},"
echo "  body:JSON.stringify({query:'What is LightRAG?', mode:'long_form'})}).then(r => r.json()).then(j => {"
echo "  console.log('job_id:', j.job_id);"
echo "  const poll = setInterval(() => fetch('$APP_URL/api/synthesize/' + j.job_id).then(r => r.json()).then(s => {"
echo "    console.log('status:', s.status, 'fallback_used:', s.fallback_used);"
echo "    if (s.status === 'done' || s.status === 'error') { clearInterval(poll); console.log(s); }"
echo "  }), 5000);"
echo "});"
echo ""
echo "Expected: Smoke 4 → status=done, fallback_used=false, real markdown in result.response"
echo "================================================================"
