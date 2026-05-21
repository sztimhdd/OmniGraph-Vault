#!/usr/bin/env bash
# Daily KB rebuild: lang detect -> SSG re-render -> FTS5 rebuild -> WAL checkpoint + VACUUM.
#
# Cron entry (recommended; install on Aliyun via crontab -e):
#   0 12 * * * /root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh >> /var/log/kb-rebuild.log 2>&1
#
# Pipeline order rationale (kb-4-04, database-reviewer Skill verdict 2026-05-21):
#   1. detect_article_lang  — backfill articles.lang where NULL (DATA-03 idempotent)
#   2. export_knowledge_base — read-only SSG re-render (read-only URI mode, safe co-runner)
#   3. rebuild_fts          — DROP+CREATE+INSERT FTS5 (~5s window where /api/search?mode=fts may
#                              miss rows; acceptable trade-off T-01 at 12:00 daily / low traffic)
#   4. wal_checkpoint(TRUNCATE) + VACUUM — checkpoint reclaims WAL space (WAL-compatible);
#                                          VACUUM included per kb-4-04 PLAN must_have but wrapped
#                                          non-fatal because VACUUM EXCLUSIVE-lock vs uvicorn
#                                          read transaction can SQLITE_BUSY (R-01 finding).
#                                          Failed checkpoint/VACUUM does not corrupt DB.
set -euo pipefail

# ---- Configuration (Aliyun canonical paths; override via env for local smoke) ----
: "${KB_INSTALL_PREFIX:=/root/OmniGraph-Vault}"
: "${KB_DB_PATH:=/root/OmniGraph-Vault/data/kol_scan.db}"
: "${KB_LOG:=/var/log/kb-rebuild.log}"
: "${KB_PYTHON:=${KB_INSTALL_PREFIX}/venv/bin/python}"
: "${KB_LOG_MAX_BYTES:=10485760}"           # 10 MiB before rotation
: "${KB_SQLITE_BUSY_TIMEOUT_MS:=30000}"     # 30s — VACUUM/checkpoint wait window

cd "${KB_INSTALL_PREFIX}"

log() { printf '[%s][daily-rebuild] %s\n' "$(date -Iseconds)" "$*"; }

# ---- Phase 0: log rotation (single-generation, R-05) ----
if [[ -f "${KB_LOG}" ]]; then
  LOG_SIZE=$(stat -c%s "${KB_LOG}" 2>/dev/null || echo 0)
  if (( LOG_SIZE > KB_LOG_MAX_BYTES )); then
    mv "${KB_LOG}" "${KB_LOG}.1"
    log "rotated log (was ${LOG_SIZE} bytes)"
  fi
fi

log "===== daily rebuild start ====="
log "KB_DB_PATH=${KB_DB_PATH}"
log "KB_INSTALL_PREFIX=${KB_INSTALL_PREFIX}"

# ---- Phase 1: lang detect (idempotent — only fills NULL rows) ----
log "[1/4] detect_article_lang"
"${KB_PYTHON}" -m kb.scripts.detect_article_lang
log "[1/4] OK"

# ---- Phase 2: SSG re-render (read-only URI mode; no write contention) ----
log "[2/4] export_knowledge_base"
"${KB_PYTHON}" kb/export_knowledge_base.py
log "[2/4] OK"

# ---- Phase 3: FTS5 rebuild (DROP+CREATE+INSERT; ~5s, idempotent) ----
log "[3/4] rebuild_fts"
"${KB_PYTHON}" -m kb.scripts.rebuild_fts
log "[3/4] OK"

# ---- Phase 4: WAL checkpoint + VACUUM (LAST per ordering R-09; non-fatal per R-01) ----
# wal_checkpoint(TRUNCATE) is WAL-mode compatible — no full-DB lock, just WAL-level lock.
# VACUUM acquires EXCLUSIVE — may SQLITE_BUSY if uvicorn holds a read transaction at the
# same instant. Wrapped `|| true` so a busy-blocked VACUUM does not fail the whole cron;
# next day's checkpoint reclaims any deferred work. Run manual VACUUM monthly with
# uvicorn stopped if freelist grows large (see T-03 in kb-4-04-SUMMARY.md).
log "[4/4] wal_checkpoint(TRUNCATE) + VACUUM"
sqlite3 "${KB_DB_PATH}" <<SQL || { log "[4/4] BUSY (non-fatal — DB intact, will retry tomorrow)"; true; }
.timeout ${KB_SQLITE_BUSY_TIMEOUT_MS}
PRAGMA wal_checkpoint(TRUNCATE);
VACUUM;
SQL
log "[4/4] OK"

log "===== daily rebuild complete ====="
