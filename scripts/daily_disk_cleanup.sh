#!/bin/bash
# Daily disk cleanup for OmniGraph-Vault on Aliyun
#
# Purpose: Maintain disk space by removing stale checkpoints and journal entries
# Schedule: Daily via systemd timer (omnigraph-disk-cleanup.timer)
# Safety: All deletions are >7 days old; read-only pre-flight checks before mutation
#
# Usage: ./daily_disk_cleanup.sh [--dry-run]

set -u

readonly BASE_DIR="${OMNIGRAPH_BASE_DIR:=/root/.hermes/omonigraph-vault}"
readonly CHECKPOINT_DIR="${BASE_DIR}/checkpoints"
readonly LOG_FILE="/var/log/omnigraph-disk-cleanup.log"
readonly DRY_RUN="${1:---execute}"  # --dry-run or --execute (default)

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] [$level] $msg" | tee -a "$LOG_FILE"
}

# Pre-flight: verify checkpoint dir exists and is readable
preflight_check() {
    if [[ ! -d "$CHECKPOINT_DIR" ]]; then
        log "ERROR" "checkpoint dir not found: $CHECKPOINT_DIR"
        return 1
    fi
    if [[ ! -r "$CHECKPOINT_DIR" ]]; then
        log "ERROR" "checkpoint dir not readable: $CHECKPOINT_DIR"
        return 1
    fi
    log "INFO" "preflight OK: checkpoint dir accessible"
    return 0
}

# Count and estimate space of checkpoints >7 days old
cleanup_stale_checkpoints() {
    log "INFO" "scanning for checkpoint dirs older than 7 days..."

    local count=0
    local space_mb=0
    local stale_dirs

    # Find dirs modified >7d ago; estimate their size
    stale_dirs=$(find "$CHECKPOINT_DIR" -maxdepth 1 -type d -mtime +7 2>/dev/null)

    if [[ -z "$stale_dirs" ]]; then
        log "INFO" "no stale checkpoint dirs found (>7d)"
        return 0
    fi

    while read -r dir; do
        ((count++))
        local size_kb
        size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        space_mb=$((space_mb + size_kb / 1024))
    done <<< "$stale_dirs"

    log "INFO" "found $count stale checkpoint dirs (~${space_mb} MB total)"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log "INFO" "[DRY RUN] would delete $count dirs, freeing ~${space_mb} MB"
        echo "$stale_dirs" | head -5 | while read -r dir; do
            log "INFO" "[DRY RUN]   delete: $dir"
        done
        if [[ $count -gt 5 ]]; then
            log "INFO" "[DRY RUN]   ... and $((count - 5)) more"
        fi
        return 0
    fi

    # Execute deletion
    log "INFO" "deleting $count stale checkpoint dirs..."
    echo "$stale_dirs" | while read -r dir; do
        if rm -rf "$dir" 2>/dev/null; then
            log "INFO" "deleted: $dir"
        else
            log "WARN" "failed to delete: $dir"
        fi
    done

    log "INFO" "checkpoint cleanup complete: freed ~${space_mb} MB"
    return 0
}

# Vacuum journal: keep entries from last 14 days
cleanup_journal() {
    log "INFO" "vacuuming journal (keep 14 days)..."

    local before_size
    before_size=$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9\.]+[KMG]' | head -1)
    log "INFO" "journal size before vacuum: $before_size"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        # Estimate: vacuuming 14d typically retains ~30-40% of full journal
        log "INFO" "[DRY RUN] would vacuum journal to 14-day window (estimate: frees ~1-2 GB)"
        return 0
    fi

    # Vacuum journal: keep entries >=14 days old, delete older ones
    if journalctl --vacuum-time=14d 2>/dev/null; then
        local after_size
        after_size=$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9\.]+[KMG]' | head -1)
        log "INFO" "journal size after vacuum: $after_size"
        log "INFO" "journal cleanup complete"
    else
        log "WARN" "journalctl vacuum failed"
        return 1
    fi

    return 0
}

# Report disk space before/after
report_disk_space() {
    log "INFO" "disk space summary:"

    local root_used
    local root_pct
    root_used=$(df / | tail -1 | awk '{print $3}')
    root_pct=$(df / | tail -1 | awk '{print $5}')

    log "INFO" "  / (root): ${root_used}K used (${root_pct})"

    if [[ -d "$BASE_DIR" ]]; then
        local omnigraph_size
        omnigraph_size=$(du -sh "$BASE_DIR" 2>/dev/null | cut -f1)
        log "INFO" "  omonigraph-vault: $omnigraph_size"
    fi

    return 0
}

main() {
    log "INFO" "====== OmniGraph daily disk cleanup started (mode: $DRY_RUN) ======"

    preflight_check || {
        log "ERROR" "preflight check failed; aborting"
        exit 1
    }

    report_disk_space

    cleanup_stale_checkpoints
    cleanup_journal

    report_disk_space

    log "INFO" "====== cleanup complete ======"
}

main "$@"
