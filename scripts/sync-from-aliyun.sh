#!/usr/bin/env bash
# scripts/sync-from-aliyun.sh
#
# Pull articles SSG output / kol_scan.db / images / kb/wiki from
# Aliyun (47.117.244.253, root) → Hermes ${HERMES_DATA_DIR}.
# Runs as oneshot on Hermes (systemd timer). Pure bash + rsync + ssh.
#
# Idempotent (re-run on same day = no-op transfer). Exit 0 on full
# success across all 4 targets; non-zero on any rsync failure after 3
# retries with exponential backoff (60s / 300s / 1800s).
#
# Retry exhaustion writes /tmp/aliyun-sync-failed-<date> marker per
# SYNC-04. Stale markers (any failed-<date>) are cleaned up on next
# success per FINDING 10 (prevents aim-5 STAB-03 false-trip).
#
# REQs: SYNC-01 (script + idempotency + exit semantics)
#       SYNC-04 (retry/backoff/marker logic)
#
# Aliyun side prep: aim-4-1 installed Hermes pubkey on
# /root/.ssh/authorized_keys.

set -u

# --- Config (overridable via env) -------------------------------------
ALIYUN_SSH_HOST="${ALIYUN_SSH_HOST:-root@47.117.244.253}"
ALIYUN_SSH_KEY="${ALIYUN_SSH_KEY:-${HOME}/.ssh/hermes_to_aliyun_ed25519}"
HERMES_DATA_DIR="${HERMES_DATA_DIR:-${HOME}/.hermes/omonigraph-vault}"

SSH_OPTS="-i ${ALIYUN_SSH_KEY} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
RSYNC_OPTS="-az --delete"

# --- Sync targets: SRC (Aliyun) → DST (Hermes) ------------------------
# Order: cheapest first so a fail-fast on later targets still gets
# small early targets to disk. Verified 2026-05-24 via SSH probe.
SYNC_PAIRS=(
  "/root/OmniGraph-Vault/data/kol_scan.db|${HERMES_DATA_DIR}/kol_scan.db"
  "/root/OmniGraph-Vault/kb/wiki/|${HERMES_DATA_DIR}/kb/wiki/"
  "/root/OmniGraph-Vault/kb/output/articles/|${HERMES_DATA_DIR}/articles/"
  "/root/.hermes/omonigraph-vault/images/|${HERMES_DATA_DIR}/images/"
)

# --- Helpers ----------------------------------------------------------
log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

ensure_parent_dirs() {
  mkdir -p \
    "${HERMES_DATA_DIR}/kb/wiki" \
    "${HERMES_DATA_DIR}/articles" \
    "${HERMES_DATA_DIR}/images"
}

do_one_rsync() {
  local src="$1" dst="$2"
  rsync ${RSYNC_OPTS} \
    -e "ssh ${SSH_OPTS}" \
    "${ALIYUN_SSH_HOST}:${src}" \
    "${dst}"
}

do_rsync_all() {
  local rc=0
  for pair in "${SYNC_PAIRS[@]}"; do
    local src="${pair%%|*}"
    local dst="${pair##*|}"
    log "rsync ${src} → ${dst}"
    if ! do_one_rsync "${src}" "${dst}"; then
      local code=$?
      log "  → rsync FAILED (exit ${code}) for ${src}"
      rc=${code}
    fi
  done
  return ${rc}
}

clean_stale_markers() {
  # FINDING 10: clear all markers on success so a transient old
  # failure does not falsely trip aim-5 STAB-03.
  rm -f /tmp/aliyun-sync-failed-* 2>/dev/null || true
}

write_failure_marker() {
  local date_str
  date_str="$(date +%Y-%m-%d)"
  touch "/tmp/aliyun-sync-failed-${date_str}"
  log "MARKER /tmp/aliyun-sync-failed-${date_str} written"
}

# --- Main retry loop --------------------------------------------------
main() {
  ensure_parent_dirs

  local delays=(60 300 1800)
  local attempt

  for attempt in 0 1 2; do
    if do_rsync_all; then
      clean_stale_markers
      log "sync OK on attempt $((attempt + 1))"
      exit 0
    fi
    local d="${delays[${attempt}]}"
    log "attempt $((attempt + 1)) failed; sleeping ${d}s before retry"
    sleep "${d}"
  done

  # 4th and final attempt
  if do_rsync_all; then
    clean_stale_markers
    log "sync OK on final attempt (4)"
    exit 0
  fi

  write_failure_marker
  echo "ERROR: aliyun sync exhausted 3 retries on $(date +%Y-%m-%d)" >&2
  exit 1
}

main "$@"
