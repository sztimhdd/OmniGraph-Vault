#!/bin/bash
# Aliyun -> backup_prod@139.159.179.249 server-to-server backup.
# Self-contained, runs via nohup. User can disconnect anytime.
# Progress: ssh aliyun-vitaclaw 'tail -f /root/aliyun-backup-260610.log'

set -uo pipefail   # NOT -e; tolerate per-tier partial fail

B="backup_prod@139.159.179.249"
DST="/home/backup_prod/aliyun-backup-260610"
LOG="/root/aliyun-backup-260610.log"
SSH_OPTS="-o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=10"

log() { echo "[$(date -Is)] $*" | tee -a "$LOG"; }

stream_to_backup() {
  # $1 = local-tar-cmd-string;  $2 = remote-filename
  local cmd="$1"
  local fn="$2"
  log "  ... starting $fn"
  local t0=$(date +%s)
  bash -c "$cmd" | ssh $SSH_OPTS "$B" "cat > $DST/$fn"
  local pipe=("${PIPESTATUS[@]}")
  local rc=${pipe[0]:-0}
  local rc2=${pipe[1]:-0}
  local t1=$(date +%s)
  if [[ $rc -eq 0 && $rc2 -eq 0 ]]; then
    local sz
    sz=$(ssh $SSH_OPTS "$B" "stat -c %s $DST/$fn")
    log "  OK  $fn  $((sz/1024/1024)) MB  $((t1-t0))s"
  else
    log "  FAIL $fn  tar=$rc ssh=$rc2  $((t1-t0))s"
  fi
}

# ISSUES #48: quiesce probe. An ingest service stuck in the #45 post-completion
# hang reports `active running` indefinitely even though its work is committed
# to disk and there is no in-flight I/O. _is_quiesced deep-probes a service PID:
# returns 0 (quiesced, safe to proceed) only when ALL three hold —
#   1. 0 real-file fds open (only stdin->/dev/null + journal pipes/sockets remain)
#   2. 0 *.tmp orphans in the storage dir (no atomic-write rename in flight)
#   3. graphml parses cleanly (file is complete, not torn)
# else returns 1 (still genuinely active — keep waiting).
QUIESCE_PY="${QUIESCE_PY:-/root/OmniGraph-Vault/venv-aim1/bin/python}"

_count_real_fds() {
  # $1 = fd dir (e.g. /proc/$PID/fd). Counts fds backed by a real file —
  # symlinks to an absolute path (excluding /dev/null), or, for test mocks,
  # plain regular files. anon_inode/socket/pipe fds are NOT real-file fds.
  local fd_dir="$1" n=0 fd tgt
  [[ -d "$fd_dir" ]] || { echo 0; return; }
  for fd in "$fd_dir"/*; do
    [[ -e "$fd" || -L "$fd" ]] || continue
    if [[ -L "$fd" ]]; then
      tgt=$(readlink "$fd" 2>/dev/null || echo "")
      case "$tgt" in
        ""|/dev/null|anon_inode:*|socket:*|pipe:*) ;;
        /*) n=$((n + 1)) ;;
        *) ;;
      esac
    elif [[ -f "$fd" ]]; then
      n=$((n + 1))
    fi
  done
  echo "$n"
}

_is_quiesced() {
  # $1 = fd dir, $2 = storage dir. Echoes nothing; returns 0 = quiesced.
  local fd_dir="$1" storage_dir="$2"
  [[ "$(_count_real_fds "$fd_dir")" -eq 0 ]] || return 1
  [[ "$(ls "$storage_dir"/*.tmp 2>/dev/null | wc -l)" -eq 0 ]] || return 1
  "$QUIESCE_PY" -c "import networkx as nx; nx.read_graphml('$storage_dir/graph_chunk_entity_relation.graphml')" >/dev/null 2>&1 || return 1
  return 0
}

# Testability seam (ISSUES #48): `bash aliyun-backup-260610.sh __quiesce_probe
# <fd_dir> <storage_dir>` runs ONLY the quiesce probe and exits with its status.
# Used by tests/unit/test_backup_quiesce_gate.py — no systemctl/Aliyun needed.
if [[ "${1:-}" == "__quiesce_probe" ]]; then
  _is_quiesced "${2:-}" "${3:-}"
  exit $?
fi

# --ignore-active-if-quiesced (default true on Aliyun): proceed past PHASE 0 when
# an active ingest service is merely hung-but-quiesced (#45). Pass
# --no-ignore-active-if-quiesced to restore strict wait-for-stop behavior.
IGNORE_ACTIVE_IF_QUIESCED=true
STORAGE_DIR="/root/.hermes/omonigraph-vault/lightrag_storage"
for arg in "$@"; do
  case "$arg" in
    --ignore-active-if-quiesced) IGNORE_ACTIVE_IF_QUIESCED=true ;;
    --no-ignore-active-if-quiesced) IGNORE_ACTIVE_IF_QUIESCED=false ;;
  esac
done

##### Phase 0: wait for in-flight ingest to finish #####
log "=== PHASE 0: wait for in-flight omnigraph ingest service ==="
WAIT_DEADLINE=$(($(date +%s) + 4*3600))
while systemctl is-active --quiet omnigraph-daily-ingest.service \
   || systemctl is-active --quiet omnigraph-afternoon-ingest.service \
   || systemctl is-active --quiet omnigraph-evening-ingest.service; do
  if [[ "$IGNORE_ACTIVE_IF_QUIESCED" == "true" ]]; then
    quiesced=true
    for svc in omnigraph-daily-ingest omnigraph-afternoon-ingest omnigraph-evening-ingest; do
      systemctl is-active --quiet "$svc.service" || continue
      pid=$(systemctl show -p MainPID --value "$svc.service" 2>/dev/null)
      if [[ -z "$pid" || "$pid" == "0" ]] || ! _is_quiesced "/proc/$pid/fd" "$STORAGE_DIR"; then
        quiesced=false
        break
      fi
    done
    if [[ "$quiesced" == "true" ]]; then
      log "  QUIESCED — proceeding (active ingest svc has 0 fds + 0 .tmp + parseable graphml; #45 hang, data safe — ISSUES #48)"
      break
    fi
  fi
  if (( $(date +%s) > WAIT_DEADLINE )); then
    log "WARNING: 4h wait exceeded; proceeding anyway (graphml may be inconsistent)"
    break
  fi
  log "  ingest still active, sleeping 60s..."
  sleep 60
done
log "  no ingest active, proceeding"

##### Phase 1: TIER 0 - omnigraph core #####
log "=== PHASE 1: TIER 0 (omnigraph core) ==="

# 1.1 secrets bundle
stream_to_backup "tar -czf - /root/.hermes/.env /root/.hermes/auth.json /root/.hermes/gcp-paid-sa.json /root/.hermes/config.yaml /root/.ssh/id_ed25519 /root/.ssh/id_ed25519.pub /root/.ssh/authorized_keys /root/.ssh/known_hosts 2>/dev/null" "tier0/secrets-260610.tgz"

# 1.2 system configs
iptables-save > /tmp/iptables-260610.rules 2>&1 || true
ufw status verbose > /tmp/ufw-260610.txt 2>&1 || true
crontab -l > /tmp/crontab-260610.txt 2>&1 || true
systemctl list-timers --all --no-pager > /tmp/timers-260610.txt 2>&1 || true
systemctl list-unit-files --type=service --no-pager > /tmp/units-260610.txt 2>&1 || true
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' > /tmp/docker-ps-260610.txt 2>&1 || true
docker volume ls > /tmp/docker-volumes-260610.txt 2>&1 || true
docker image ls --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' > /tmp/docker-images-260610.txt 2>&1 || true

stream_to_backup "tar -czf - /etc/caddy/Caddyfile /etc/hosts /etc/systemd/system/kb-api.service /etc/systemd/system/kb-api.service.d/ /etc/systemd/system/omnigraph-*.service /etc/systemd/system/omnigraph-*.timer /etc/systemd/system/omnigraph-*.service.d/ /etc/systemd/system/qdrant-snapshot.service /etc/systemd/system/qdrant-snapshot.timer /etc/systemd/system/vitaclaw-site.service /etc/cron.d/ /etc/vitaclaw/ /var/lib/caddy/.config/caddy/autosave.json /etc/ssh/ssh_host_* /tmp/iptables-260610.rules /tmp/ufw-260610.txt /tmp/crontab-260610.txt /tmp/timers-260610.txt /tmp/units-260610.txt /tmp/docker-ps-260610.txt /tmp/docker-volumes-260610.txt /tmp/docker-images-260610.txt 2>/dev/null" "tier0/sysconf-260610.tgz"
rm -f /tmp/iptables-260610.rules /tmp/ufw-260610.txt /tmp/crontab-260610.txt /tmp/timers-260610.txt /tmp/units-260610.txt /tmp/docker-ps-260610.txt /tmp/docker-volumes-260610.txt /tmp/docker-images-260610.txt

# 1.3 kol_scan.db (sqlite consistent backup)
log "  prep sqlite hot-backup..."
sqlite3 /root/OmniGraph-Vault/data/kol_scan.db ".backup /tmp/kol_scan-260610.db"
log "  sqlite backup done: $(stat -c %s /tmp/kol_scan-260610.db) bytes"
stream_to_backup "cat /tmp/kol_scan-260610.db" "tier0/kol_scan-260610.db"
rm -f /tmp/kol_scan-260610.db

# 1.4 LightRAG live state (graphml + 5 kv_store, exclude bak/archive/dual-storage vdb)
stream_to_backup "tar -czf - -C /root/.hermes/omonigraph-vault --exclude='*.bak-*' --exclude='*.corrupt-*' --exclude='*.truncated-bak' --exclude='*.repaired-bak' --exclude='lightrag_storage.aliyun-pre-aim2-*' --exclude='lightrag_storage/vdb_archive_*.json' --exclude='lightrag_storage/vdb_chunks.json' --exclude='lightrag_storage/vdb_entities.json' lightrag_storage" "tier0/lightrag_live-260610.tgz"

# 1.5 Qdrant data (1.9G - briefly stop kb-api for consistent tar)
log "  Qdrant: stopping kb-api for consistent snapshot..."
systemctl stop kb-api.service
sleep 3
stream_to_backup "tar -czf - -C /var/lib qdrant" "tier0/qdrant-260610.tgz"
log "  Qdrant: restarting kb-api..."
systemctl start kb-api.service
sleep 5
if systemctl is-active --quiet kb-api.service; then
  log "  kb-api back up"
else
  log "  WARN kb-api not active!"
fi

##### Phase 2: TIER 0.6 - vitaclaw-site #####
log "=== PHASE 2: TIER 0.6 (vitaclaw-site source + public videos) ==="
stream_to_backup "tar -czf - -C /opt/vitaclaw/control-plane/vitaclaw-site --exclude='node_modules' --exclude='dist' --exclude='dist.backup*' --exclude='backups' --exclude='.playwright-mcp' --exclude='.opencode' ." "tier0_6/vitaclaw-site-src-260610.tgz"

##### Phase 3: TIER 0.7 - vitaclaw SaaS code+config #####
log "=== PHASE 3: TIER 0.7 (vitaclaw SaaS source+config) ==="

stream_to_backup "tar -czf - -C /opt/vitaclaw vitaclaw-planb-deploy" "tier0_7/vitaclaw-planb-deploy-260610.tgz"

stream_to_backup "tar -czf - -C /opt/vitaclaw --exclude='planb-local-m1/vitaclaw-local/tenants/tenantB/data' --exclude='planb-local-m1/vitaclaw-local/tenants/tenantB/db' --exclude='planb-local-m1/vitaclaw-local/tenants/viaproxy' --exclude='planb-local-m1/vitaclaw-local/tenants/finalfinal' --exclude='planb-local-m1/vitaclaw-local/tenants/debug2' --exclude='planb-local-m1/vitaclaw-local/tenants/cacheclear' --exclude='planb-local-m1/vitaclaw-local/tenants/bugfixtest' --exclude='planb-local-m1/vitaclaw-local/tenants/uat-*' --exclude='planb-local-m1/vitaclaw-local/web-prebuilt' --exclude='planb-local-m1/vitaclaw-local/web-src/*/node_modules' --exclude='planb-local-m1/vitaclaw-local/web-src/*/dist' --exclude='planb-local-m1/upstream/*/node_modules' --exclude='planb-local-m1/upstream/*/dist' --exclude='planb-local-m1/upstream/*/build' planb-local-m1" "tier0_7/planb-local-m1-260610.tgz"

stream_to_backup "tar -czf - -C /opt/vitaclaw --exclude='.incoming/kubectl.gz' --exclude='.incoming/vitaclaw-planb-images.tar.gz' .deploy-backups .incoming README.md 2>/dev/null" "tier0_7/vitaclaw-extras-260610.tgz"

stream_to_backup "tar -czf - /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed /opt/vitaclaw/planb-local-m1/.env /opt/vitaclaw/planb-local-m1/.env.local 2>/dev/null" "tier0_7/saas-secrets-260610.tgz"

##### Phase 4: TIER 1 - vdb_archive (Hermes RO unlock fallback) #####
log "=== PHASE 4: TIER 1 (vdb_archive load-bearing) ==="
stream_to_backup "tar -czf - -C /root/.hermes/omonigraph-vault/lightrag_storage vdb_archive_relationships.json" "tier1/vdb_archive_rel-260610.tgz"
stream_to_backup "tar -czf - -C /root/.hermes/omonigraph-vault/lightrag_storage vdb_archive_chunks.json vdb_archive_entities.json" "tier1/vdb_archive_other-260610.tgz"

##### Phase 5: TIER 2 - accumulated investment #####
log "=== PHASE 5: TIER 2 (images + aux + repo) ==="

stream_to_backup "tar -czf - -C /root/.hermes/omonigraph-vault images" "tier2/images-260610.tgz"

stream_to_backup "tar -czf - -C /root/.hermes/omonigraph-vault checkpoints entity_buffer canonical_map.json query_history.jsonl synthesis_archive synthesis_output.md README.qdrant-migration.txt 2>/dev/null" "tier2/omnigraph-aux-260610.tgz"

stream_to_backup "tar -czf - -C /root --exclude='OmniGraph-Vault/venv' --exclude='OmniGraph-Vault/venv-aim1' --exclude='OmniGraph-Vault/__pycache__' --exclude='OmniGraph-Vault/data/kol_scan.db.bak-*' --exclude='OmniGraph-Vault/data/kol_scan.db.backup-*' --exclude='*.pyc' OmniGraph-Vault" "tier2/omnigraph-repo-260610.tgz"

##### Phase 6: verification on backup host #####
log "=== PHASE 6: verification on backup host ==="
ssh $SSH_OPTS "$B" "cd $DST && echo '=== files (size, name) ===' && find . -type f -printf '%s %p\n' | sort -rn && echo '=== md5 manifest ===' && md5sum tier0/*.tgz tier0/*.db tier0_6/*.tgz tier0_7/*.tgz tier1/*.tgz tier2/*.tgz 2>/dev/null > manifest-260610.md5 && cat manifest-260610.md5 && echo '=== total bytes ===' && du -sb . && echo '=== sample untar tests ===' && tar -tzf tier0/lightrag_live-260610.tgz | grep graphml | head -3 && tar -tzf tier0/qdrant-260610.tgz | grep lightrag_vdb_relationships | head -3 && tar -tzf tier0/sysconf-260610.tgz | grep -E 'Caddyfile|kb-api.service|hosts' | head -5 && python3 -c \"import sqlite3; c=sqlite3.connect('tier0/kol_scan-260610.db'); print('articles=', c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]); print('rss=', c.execute('SELECT COUNT(*) FROM rss_articles').fetchone()[0])\"" 2>&1 | tee -a "$LOG"

##### Phase 7: restart omnigraph timers #####
log "=== PHASE 7: restart omnigraph timers ==="
systemctl start omnigraph-daily-ingest.timer omnigraph-afternoon-ingest.timer omnigraph-evening-ingest.timer omnigraph-rss-fetch.timer omnigraph-translate.timer omnigraph-rss-rescrape.timer omnigraph-rss-layer2-classify.timer omnigraph-reconcile.timer omnigraph-daily-digest.timer omnigraph-kol-classify.timer omnigraph-kol-enrich.timer omnigraph-kol-zombie-cleanup.timer omnigraph-vertex-probe.timer 2>&1 | tee -a "$LOG"
# NOT restarting kol-scan.timer (known-failed)
log "  active timers:"
systemctl list-timers 'omnigraph-*' --no-pager | head -20 | tee -a "$LOG"

log "=== ALL DONE ==="
log "Backup location: $B:$DST"
log "Manifest: $B:$DST/manifest-260610.md5"
log "Resume tail anytime with: ssh aliyun-vitaclaw 'tail -f $LOG'"
