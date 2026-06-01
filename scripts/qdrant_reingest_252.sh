#!/usr/bin/env bash
# scripts/qdrant_reingest_252.sh — 6-batch WeChat-throttle-aware re-ingest
# wrapper for v1.1.qdrant-migration T9.
#
# Goal: re-ingest the 252 article candidate pool (238 layer2_verdict='ok' +
# 14 failed-with-body, measured 2026-06-01 via sqlite) into the freshly
# provisioned Qdrant docker on Aliyun. WeChat enforces a 50-articles-per-
# batch throttle floor + cooldown, so we run at most 6 batches × 50.
#
# Count-driven early exit (D9 fix — robust against article-count drift
# between plan time and execute time): before each batch, query
# Qdrant `lightrag_vdb_chunks.count`. If count >= 252, exit immediately.
# The 6th batch (when it runs) ingests only the remainder; WeChat throttle
# tolerates batches < 50 silently.
#
# Halt-on-failure (set -euo pipefail): any non-zero batch exit aborts and
# emits qdrant_reingest_halt marker. No retry — operator triages.
#
# HT-10 invariant: this script touches NO Hermes-side code, env, or runtime.
# `/root/.hermes/.env` is the Aliyun-local typo path, NOT the Hermes server.
#
# NOTE on flag names: PLAN.md T3 originally referenced --topics and
# --reset-checkpoint=false, but batch_ingest_from_spider.py uses
# --topic-filter (no plural) and has no --reset-checkpoint flag. This
# wrapper uses the real flag names. Resume behavior is the default (not
# reset) — checkpoints survive across batches.
#
# Usage:
#   bash /root/OmniGraph-Vault/scripts/qdrant_reingest_252.sh
#
# Env vars:
#   BATCH_COOLDOWN_S   cooldown between batches (default 3600 = 1h)
#   QDRANT_URL         Qdrant endpoint (default http://127.0.0.1:6333)
#   TARGET_CHUNKS      early-exit chunk count (default 252)
#
# Author: v1.1.qdrant-migration T3 (commit-pending)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_ROOT="${REPO_ROOT:-/root/OmniGraph-Vault}"
VENV_PYTHON="${VENV_PYTHON:-${REPO_ROOT}/venv-aim1/bin/python}"
ENV_FILE="${ENV_FILE:-/root/.hermes/.env}"
LOG_DIR="${LOG_DIR:-/root/.hermes}"
BATCH_COOLDOWN_S="${BATCH_COOLDOWN_S:-3600}"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
TARGET_CHUNKS="${TARGET_CHUNKS:-252}"
MAX_BATCHES="${MAX_BATCHES:-6}"
BATCH_SIZE="${BATCH_SIZE:-50}"
TOPIC_FILTER="${TOPIC_FILTER:-ai}"

# ---------------------------------------------------------------------------
# Logging helpers (stderr, ISO timestamp)
# ---------------------------------------------------------------------------
log() {
  printf '%s qdrant_reingest %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

# ---------------------------------------------------------------------------
# Source env (wraps DEEPSEEK_API_KEY + GOOGLE creds + LightRAG knobs)
# ---------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  log "FATAL env file missing: $ENV_FILE"
  exit 2
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ---------------------------------------------------------------------------
# Qdrant chunk-count probe
# ---------------------------------------------------------------------------
qdrant_chunk_count() {
  "$VENV_PYTHON" - <<PY
from qdrant_client import QdrantClient
try:
    c = QdrantClient(url="${QDRANT_URL}")
    print(c.count("lightrag_vdb_chunks", exact=True).count)
except Exception:
    # Collection may not exist yet on first run — treat as 0 so first
    # batch fires and creates it via ingest_wechat upsert.
    print(0)
PY
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
log "start target_chunks=${TARGET_CHUNKS} max_batches=${MAX_BATCHES} batch_size=${BATCH_SIZE} cooldown_s=${BATCH_COOLDOWN_S}"

# Always run from repo root so checkpoints/, logs/, etc. resolve correctly.
cd "$REPO_ROOT"

for i in $(seq 1 "$MAX_BATCHES"); do
  count_before="$(qdrant_chunk_count)"
  log "batch=${i}/${MAX_BATCHES} pre_count=${count_before}"

  if [ "$count_before" -ge "$TARGET_CHUNKS" ]; then
    log "qdrant_reingest_done batches=$((i - 1)) chunks=${count_before} (early exit, target met)"
    exit 0
  fi

  log "batch=${i} starting ingest"
  batch_log="${LOG_DIR}/qdrant-reingest-batch-${i}.log"
  if ! "$VENV_PYTHON" "$REPO_ROOT/batch_ingest_from_spider.py" \
        --from-db \
        --topic-filter "$TOPIC_FILTER" \
        --max-articles "$BATCH_SIZE" \
        2>&1 | tee "$batch_log"; then
    log "qdrant_reingest_halt batch=${i} (batch script returned non-zero)"
    exit 3
  fi

  count_after="$(qdrant_chunk_count)"
  log "batch=${i} done post_count=${count_after} delta=$((count_after - count_before))"

  if [ "$count_after" -ge "$TARGET_CHUNKS" ]; then
    log "qdrant_reingest_done batches=${i} chunks=${count_after} (target met after batch)"
    exit 0
  fi

  if [ "$i" -lt "$MAX_BATCHES" ]; then
    log "cooldown sleep_s=${BATCH_COOLDOWN_S}"
    sleep "$BATCH_COOLDOWN_S"
  fi
done

final_count="$(qdrant_chunk_count)"
log "qdrant_reingest_done batches=${MAX_BATCHES} chunks=${final_count} total_wall_s=${SECONDS}"

if [ "$final_count" -lt "$TARGET_CHUNKS" ]; then
  log "WARNING final_count=${final_count} target=${TARGET_CHUNKS} (under-met after ${MAX_BATCHES} batches; investigate per HT-8)"
  exit 4
fi

exit 0
