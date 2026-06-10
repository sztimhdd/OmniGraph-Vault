# 260610-eoy — Aliyun ECS Backup Plan (execution sequence)

**Audit base:** `BACKUP_INVENTORY.md`
**Source:** `aliyun-vitaclaw` (101.133.154.49)
**Target:** Windows corp laptop SSD (default) — single-pass scp / tar | scp.

**⚠️ READ FIRST:**
- 100% READ-ONLY audit; nothing executed yet.
- All commands below are PLAN — review every block before running.
- User triggers each pass manually after review.

---

## Pre-flight (mandatory)

### P0.1 — Stop the bleeding (one-time, on Aliyun)

Cuts ~14G of safe waste BEFORE backup so transfer is faster:

```bash
# DO NOT run automatically — review first
# Reclaim docker build cache (12.58G)
ssh aliyun-vitaclaw 'docker builder prune -af'

# Wipe /tmp old phase artifacts (8G)
ssh aliyun-vitaclaw '
  rm -f /tmp/lr_storage_arx2.tgz \
        /tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz \
        /tmp/lightrag_storage_arx2.tar.gz \
        /tmp/vitaclaw-all-images.tar.gz \
        /tmp/orchestrator-pruned.tar.gz \
        /tmp/hermes_sync_imgs.tar.gz \
        /tmp/aim1-smoke \
        /tmp/hermes-graphml-20260608.xml \
        /tmp/web-prebuilt.tgz \
        /tmp/admin-dashboard.tar.gz \
        /tmp/orchestrator-app \
        /tmp/vitaclaw-optimize \
        /tmp/lightrag_storage_arx2.tar.gz 2>/dev/null
  echo "tmp after cleanup:"; du -sh /tmp
'
```

**Defer if:** user wants any /tmp file as evidence.
Net effect: free ~14-20G on /dev/vda3 (88%→~70%) — ECS still alive even if backup is interrupted, and snapshot taken AFTER cleanup is much smaller.

### P0.2 — Verify local laptop disk

```powershell
# On Windows laptop (PowerShell)
Get-PSDrive C | Format-Table Used,Free
```

Need ≥ 20G free for staging. If <20G, mount external SSD as backup target and adjust paths.

### P0.3 — Local target tree

```powershell
$BACKUP_ROOT = "$env:USERPROFILE\Desktop\aliyun-backup-260610"
New-Item -ItemType Directory -Force -Path "$BACKUP_ROOT\hermes",
  "$BACKUP_ROOT\omnigraph-vault","$BACKUP_ROOT\qdrant",
  "$BACKUP_ROOT\vitaclaw-saas","$BACKUP_ROOT\vitaclaw-site",
  "$BACKUP_ROOT\docker-images","$BACKUP_ROOT\system","$BACKUP_ROOT\secrets-encrypted"
```

---

## Pass 1 — MUST tier (critical state)

Sequenced by **risk × size**: smallest+highest-risk first (secrets), then large state, then docker images.

### P1.1 — Secrets (encrypted channel, ~10K total)

**On Aliyun**, package + encrypt secrets with GPG symmetric AES256:

```bash
ssh aliyun-vitaclaw '
  cd /tmp && tar -czf /tmp/secrets-260610.tgz \
    /root/.hermes/.env \
    /root/.hermes/auth.json \
    /root/.hermes/gcp-paid-sa.json \
    /root/.hermes/config.yaml \
    /root/.ssh/id_ed25519 \
    /root/.ssh/id_ed25519.pub \
    /root/.ssh/authorized_keys \
    /root/.ssh/known_hosts \
    /opt/vitaclaw/planb-local-m1/.env \
    /opt/vitaclaw/planb-local-m1/.env.local \
    /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env \
    /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed \
    /etc/vitaclaw/vitaclaw-site.env 2>&1 | tail -5
  ls -la /tmp/secrets-260610.tgz
'

# Encrypt at rest before download (interactive password prompt — paranoid mode)
ssh -t aliyun-vitaclaw 'gpg --symmetric --cipher-algo AES256 -o /tmp/secrets-260610.tgz.gpg /tmp/secrets-260610.tgz && rm /tmp/secrets-260610.tgz'

# Download .gpg only
scp aliyun-vitaclaw:/tmp/secrets-260610.tgz.gpg "$BACKUP_ROOT/secrets-encrypted/"

# Cleanup remote
ssh aliyun-vitaclaw 'rm /tmp/secrets-260610.tgz.gpg'

# Verify local
md5sum "$BACKUP_ROOT/secrets-encrypted/secrets-260610.tgz.gpg"
```

**Estimated time:** <5s (file is tiny)
**Recovery rule:** never decrypt on the corp laptop unless ready to feed directly into new env. Decrypt + immediately copy contents → wipe plaintext copy.

### P1.2 — System configs (read-only, tiny — ~100K)

```bash
ssh aliyun-vitaclaw '
  cd /tmp && tar -czf /tmp/system-configs-260610.tgz \
    /etc/caddy/Caddyfile \
    /etc/hosts \
    /etc/systemd/system/kb-api.service \
    /etc/systemd/system/vitaclaw-site.service \
    /etc/systemd/system/omnigraph-*.service \
    /etc/systemd/system/omnigraph-*.timer \
    /etc/systemd/system/qdrant-snapshot.service \
    /etc/systemd/system/qdrant-snapshot.timer \
    /etc/systemd/system/*.service.d/override.conf \
    /etc/vitaclaw/ \
    /etc/cron.d/ \
    /var/lib/caddy/.config/caddy/autosave.json \
    /var/lib/caddy/.local/share/caddy/ 2>&1 | tail -5
  iptables-save > /tmp/iptables-260610.rules
  crontab -l > /tmp/crontab-root-260610.txt
  systemctl list-timers --all --no-pager > /tmp/timers-260610.txt
  systemctl list-unit-files --type=service --no-pager > /tmp/units-260610.txt
  tar -czf /tmp/system-extras-260610.tgz \
    /tmp/iptables-260610.rules \
    /tmp/crontab-root-260610.txt \
    /tmp/timers-260610.txt \
    /tmp/units-260610.txt
  ls -la /tmp/system-*.tgz /tmp/iptables-260610.rules /tmp/crontab-root-260610.txt
'

scp aliyun-vitaclaw:/tmp/system-configs-260610.tgz "$BACKUP_ROOT/system/"
scp aliyun-vitaclaw:/tmp/system-extras-260610.tgz  "$BACKUP_ROOT/system/"

# Cleanup
ssh aliyun-vitaclaw 'rm /tmp/system-configs-260610.tgz /tmp/system-extras-260610.tgz /tmp/iptables-260610.rules /tmp/crontab-root-260610.txt /tmp/timers-260610.txt /tmp/units-260610.txt'

# Verify
md5sum "$BACKUP_ROOT/system/system-configs-260610.tgz"
ssh aliyun-vitaclaw 'md5sum -- /dev/null 2>/dev/null || true'  # hash already gone after delete; rely on local + sample diff
```

**Estimated time:** <5s
**Verify:** untar locally and `find <extracted> | wc -l` ≥ 50 entries.

### P1.3 — kol_scan.db (production SSG DB, 63M)

```bash
# Hot copy via sqlite3 .backup (consistent snapshot — does NOT lock writers)
ssh aliyun-vitaclaw '
  sqlite3 /root/OmniGraph-Vault/data/kol_scan.db ".backup /tmp/kol_scan-260610.db"
  ls -la /tmp/kol_scan-260610.db
  sqlite3 /tmp/kol_scan-260610.db "SELECT COUNT(*) AS articles FROM articles; SELECT COUNT(*) AS rss FROM rss_articles;"
'

scp aliyun-vitaclaw:/tmp/kol_scan-260610.db "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/kol_scan-260610.db'

# Local verify
sqlite3 "$BACKUP_ROOT/omnigraph-vault/kol_scan-260610.db" "SELECT COUNT(*) FROM articles;"  # expect 1807
sqlite3 "$BACKUP_ROOT/omnigraph-vault/kol_scan-260610.db" "SELECT COUNT(*) FROM rss_articles;"  # expect 2200
```

**Estimated time:** ~10s (100Mbps × 63M).

### P1.4 — LightRAG storage (NetworkX side, ~3.0G live)

Live state needed for restore. Strip `.bak-*` and `.corrupt-*` and `.aliyun-pre-*` siblings:

```bash
ssh aliyun-vitaclaw '
  cd /root/.hermes/omonigraph-vault && \
  tar --exclude="*.bak-*" --exclude="*.corrupt-*" --exclude="*.truncated-bak" --exclude="*.repaired-bak" \
      --exclude="lightrag_storage.aliyun-pre-aim2-*" \
      -czf /tmp/lightrag_storage-260610.tgz lightrag_storage/
  ls -la /tmp/lightrag_storage-260610.tgz
'

scp aliyun-vitaclaw:/tmp/lightrag_storage-260610.tgz "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/lightrag_storage-260610.tgz'

md5sum "$BACKUP_ROOT/omnigraph-vault/lightrag_storage-260610.tgz"
```

**Estimated time:** ~3min @ 100 Mbps (assuming ~50% gzip → 1.5G compressed).

### P1.5 — Qdrant collections (1.9G live)

Qdrant has a built-in snapshot endpoint — use that for consistent restore-able archives:

```bash
ssh aliyun-vitaclaw '
  # Trigger snapshot for each of the 3 collections
  for c in lightrag_vdb_chunks_gemini_embedding_2_3072d \
           lightrag_vdb_entities_gemini_embedding_2_3072d \
           lightrag_vdb_relationships_gemini_embedding_2_3072d; do
    echo "=== snapshot $c ==="
    curl -sS -X POST http://127.0.0.1:6333/collections/$c/snapshots | head -200
  done
  ls -la /var/lib/qdrant/collections/*/snapshots/
'

# Tar the entire qdrant data dir (includes new snapshots + raft state)
ssh aliyun-vitaclaw 'tar -czf /tmp/qdrant-data-260610.tgz -C /var/lib qdrant && ls -la /tmp/qdrant-data-260610.tgz'

# Stream to laptop
scp aliyun-vitaclaw:/tmp/qdrant-data-260610.tgz "$BACKUP_ROOT/qdrant/"
ssh aliyun-vitaclaw 'rm /tmp/qdrant-data-260610.tgz'

md5sum "$BACKUP_ROOT/qdrant/qdrant-data-260610.tgz"
```

**Estimated time:** ~5min @ 100 Mbps (~1G compressed).

### P1.6 — Vitaclaw tenantB Postgres (94M)

Use `pg_dump`, NOT raw filesystem (PG cluster needs consistent snapshot):

```bash
ssh aliyun-vitaclaw '
  # Find tenantB postgres container — adjust if different
  docker ps --filter "name=postgres" --format "{{.Names}}\t{{.Image}}"
  # Confirmed running: vc_tb-postgres-1 (mapped 5402:5432)
  docker exec vc_tb-postgres-1 pg_dumpall -U postgres > /tmp/vctb-pgdump-260610.sql
  gzip /tmp/vctb-pgdump-260610.sql
  ls -la /tmp/vctb-pgdump-260610.sql.gz
'

scp aliyun-vitaclaw:/tmp/vctb-pgdump-260610.sql.gz "$BACKUP_ROOT/vitaclaw-saas/"
ssh aliyun-vitaclaw 'rm /tmp/vctb-pgdump-260610.sql.gz'
```

**Defer if:** docker user / db name / DB connection different — verify via `docker exec vc_tb-postgres-1 psql -U postgres -c '\l'` first.

### P1.7 — Vitaclaw tenantB data dir (2.2G — uploads, app state, web)

```bash
ssh aliyun-vitaclaw '
  cd /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB && \
  tar -czf /tmp/tenantB-data-260610.tgz data/ env/ compose/
  ls -la /tmp/tenantB-data-260610.tgz
'

scp aliyun-vitaclaw:/tmp/tenantB-data-260610.tgz "$BACKUP_ROOT/vitaclaw-saas/"
ssh aliyun-vitaclaw 'rm /tmp/tenantB-data-260610.tgz'
md5sum "$BACKUP_ROOT/vitaclaw-saas/tenantB-data-260610.tgz"
```

**Estimated time:** ~3min @ 100 Mbps.

### P1.8 — Vitaclaw shared docker volumes (5.9G total live)

Each volume needs a separate stop-mount-tar, OR use docker run helper to dump:

```bash
# For each shared runtime volume, dump via temporary helper container
ssh aliyun-vitaclaw '
  for v in vitaclaw-shared_convstore_runtime \
           vitaclaw-shared_delivery_runtime \
           vitaclaw-shared_inbox_runtime \
           vitaclaw-shared_push_runtime \
           vitaclaw-shared_timescaledb_data \
           vitaclaw-shared_nats_data \
           vc_tb_minio_data; do
    echo "=== dumping volume $v ==="
    docker run --rm -v "$v":/data -v /tmp:/dump alpine \
      sh -c "cd /data && tar -czf /dump/vol-$v-260610.tgz ."
  done
  ls -la /tmp/vol-*.tgz
'

# scp them all
for v in vitaclaw-shared_convstore_runtime \
         vitaclaw-shared_delivery_runtime \
         vitaclaw-shared_inbox_runtime \
         vitaclaw-shared_push_runtime \
         vitaclaw-shared_timescaledb_data \
         vitaclaw-shared_nats_data \
         vc_tb_minio_data; do
  scp aliyun-vitaclaw:/tmp/vol-$v-260610.tgz "$BACKUP_ROOT/vitaclaw-saas/"
done
ssh aliyun-vitaclaw 'rm /tmp/vol-vitaclaw-shared_*.tgz /tmp/vol-vc_tb_minio_data-260610.tgz'
```

**Note:** convstore/delivery/inbox/push are bun-runtime services. Dumping while running is **mostly** safe (read-side consistency depends on whether the service flushes regularly). For paranoid consistency, scale services to 0 first via compose, dump, scale back up. Default: hot dump, accept ~1% risk.

**Estimated time:** ~12min @ 100 Mbps total.

### P1.9 — Vitaclaw site dist + public (425M)

```bash
ssh aliyun-vitaclaw '
  cd /opt/vitaclaw/control-plane/vitaclaw-site && \
  tar --exclude="node_modules" --exclude="backups" --exclude="dist.backup*" \
      -czf /tmp/vitaclaw-site-260610.tgz \
      dist/ public/ src/ server/ server.js package.json package-lock.json \
      vite.config.ts tsconfig.json index.html metadata.json README.md AGENTS.md CLAUDE.md docs/
  ls -la /tmp/vitaclaw-site-260610.tgz
'

scp aliyun-vitaclaw:/tmp/vitaclaw-site-260610.tgz "$BACKUP_ROOT/vitaclaw-site/"
ssh aliyun-vitaclaw 'rm /tmp/vitaclaw-site-260610.tgz'
md5sum "$BACKUP_ROOT/vitaclaw-site/vitaclaw-site-260610.tgz"
```

**Estimated time:** ~1min.

### P1.10 — Custom Docker images (~5G)

Save the locally-built images (registry-pullable images SKIP):

```bash
ssh aliyun-vitaclaw '
  for img in vitaclaw-admin-dashboard:latest \
             vc-conversation-store:local \
             vitaclaw-management-service:latest \
             vitaclaw-skill-service:v0.1.0 \
             vitaclaw-persona-service:v0.1.0 \
             vitaclaw-identity-service:v0.1.0 \
             vitaclaw-ag-ui-server:v0.1.0 \
             vitaclaw-orchestrator:v0.1.0 \
             vitaclaw-tenant-web:v0.1.0 \
             vitaclaw-ai-infra-rs:v0.1.0 \
             vc-ai-infra-rs:local; do
    fn=$(echo "$img" | tr "/:" "__")
    echo "=== save $img → $fn ==="
    docker save "$img" | gzip > "/tmp/img-$fn-260610.tgz"
  done
  ls -la /tmp/img-*.tgz
'

# scp each (sequentially — large files)
for img in vitaclaw-admin-dashboard__latest vc-conversation-store__local \
           vitaclaw-management-service__latest vitaclaw-skill-service__v0.1.0 \
           vitaclaw-persona-service__v0.1.0 vitaclaw-identity-service__v0.1.0 \
           vitaclaw-ag-ui-server__v0.1.0 vitaclaw-orchestrator__v0.1.0 \
           vitaclaw-tenant-web__v0.1.0 vitaclaw-ai-infra-rs__v0.1.0 \
           vc-ai-infra-rs__local; do
  scp aliyun-vitaclaw:/tmp/img-$img-260610.tgz "$BACKUP_ROOT/docker-images/"
done
ssh aliyun-vitaclaw 'rm /tmp/img-*.tgz'
```

**Estimated time:** ~10min @ 100 Mbps (compressed images ~50%).
**Tip:** if any image is rebuildable from a Dockerfile in the repo and you have all build context, SKIP that one — much smaller restore footprint.

### P1.11 — Vitaclaw planb-local-m1 build / compose / templates (~300K)

```bash
ssh aliyun-vitaclaw '
  cd /opt/vitaclaw/planb-local-m1 && \
  tar --exclude="vitaclaw-local/tenants/tenantB/data" \
      --exclude="vitaclaw-local/tenants/tenantB/db" \
      --exclude="vitaclaw-local/tenants/viaproxy" \
      --exclude="vitaclaw-local/tenants/finalfinal" \
      --exclude="vitaclaw-local/tenants/debug2" \
      --exclude="vitaclaw-local/tenants/cacheclear" \
      --exclude="vitaclaw-local/tenants/bugfixtest" \
      --exclude="vitaclaw-local/tenants/uat-*" \
      --exclude="vitaclaw-local/web-prebuilt" \
      --exclude="vitaclaw-local/web-src/node_modules" \
      -czf /tmp/planb-config-260610.tgz \
      compose/ dockerfiles/ scripts/ prompts/ charts/ templates/ docs/ README.md \
      vitaclaw-local/compose vitaclaw-local/templates vitaclaw-local/upstream-src
  ls -la /tmp/planb-config-260610.tgz
'

scp aliyun-vitaclaw:/tmp/planb-config-260610.tgz "$BACKUP_ROOT/vitaclaw-saas/"
ssh aliyun-vitaclaw 'rm /tmp/planb-config-260610.tgz'
```

**Note:** sources to non-tenant-data dirs only — secrets already in P1.1.

### P1.12 — OmniGraph-Vault repo (~280M without venv/data)

Already in git (origin/main, currently 4 commits behind). Two options:

- **Option A (preferred):** on the new env, `git clone <github-url>` — no backup needed. But verify GitHub remote is canonical before relying on this.
- **Option B (paranoid):** tar the local repo *minus venv* in case GitHub is unreachable / behind.

```bash
# Option B
ssh aliyun-vitaclaw '
  cd /root && \
  tar --exclude="OmniGraph-Vault/venv" --exclude="OmniGraph-Vault/venv-aim1" \
      --exclude="OmniGraph-Vault/__pycache__" --exclude="OmniGraph-Vault/data/kol_scan.db.bak-*" \
      --exclude="OmniGraph-Vault/data/kol_scan.db.backup-*" \
      --exclude="*.pyc" \
      -czf /tmp/omnigraph-repo-260610.tgz OmniGraph-Vault/
  ls -la /tmp/omnigraph-repo-260610.tgz
'

scp aliyun-vitaclaw:/tmp/omnigraph-repo-260610.tgz "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/omnigraph-repo-260610.tgz'
```

**Estimated time:** ~30s.
**Recovery hint:** if Option A works first try, deletion `rm $BACKUP_ROOT/omnigraph-vault/omnigraph-repo-260610.tgz` is fine.

### P1.13 — KB SSG output (74M)

Live `/var/www/kb/` — Caddy serves this. Rebuildable via daily_rebuild.sh on new env, but copying is faster:

```bash
ssh aliyun-vitaclaw '
  cd /var/www && tar -czf /tmp/kb-www-260610.tgz kb/ && ls -la /tmp/kb-www-260610.tgz
'

scp aliyun-vitaclaw:/tmp/kb-www-260610.tgz "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/kb-www-260610.tgz'
```

---

## Pass 2 — SHOULD tier (reproducible but expensive)

### P2.1 — Article images (1.7G — 465 dirs, paid SiliconFlow vision)

```bash
ssh aliyun-vitaclaw '
  cd /root/.hermes/omonigraph-vault && \
  tar -czf /tmp/article-images-260610.tgz images/
  ls -la /tmp/article-images-260610.tgz
'

scp aliyun-vitaclaw:/tmp/article-images-260610.tgz "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/article-images-260610.tgz'
md5sum "$BACKUP_ROOT/omnigraph-vault/article-images-260610.tgz"
```

**Estimated time:** ~3min.

### P2.2 — Checkpoints + entity_buffer + query_history (~46M)

```bash
ssh aliyun-vitaclaw '
  cd /root/.hermes/omonigraph-vault && \
  tar -czf /tmp/omg-aux-260610.tgz \
      checkpoints/ entity_buffer/ canonical_map.json query_history.jsonl \
      synthesis_archive/ synthesis_output.md README.qdrant-migration.txt
  ls -la /tmp/omg-aux-260610.tgz
'

scp aliyun-vitaclaw:/tmp/omg-aux-260610.tgz "$BACKUP_ROOT/omnigraph-vault/"
ssh aliyun-vitaclaw 'rm /tmp/omg-aux-260610.tgz'
```

### P2.3 — Vitaclaw upstream code (105M)

```bash
ssh aliyun-vitaclaw '
  cd /opt/vitaclaw/planb-local-m1/upstream && \
  tar -czf /tmp/vitaclaw-upstream-260610.tgz .
  ls -la /tmp/vitaclaw-upstream-260610.tgz
'

scp aliyun-vitaclaw:/tmp/vitaclaw-upstream-260610.tgz "$BACKUP_ROOT/vitaclaw-saas/"
ssh aliyun-vitaclaw 'rm /tmp/vitaclaw-upstream-260610.tgz'
```

### P2.4 — Recent journal slice (last 14d, ~50M)

```bash
ssh aliyun-vitaclaw 'journalctl --since "14 days ago" -o short-iso > /tmp/journal-last14d.txt && gzip /tmp/journal-last14d.txt'

scp aliyun-vitaclaw:/tmp/journal-last14d.txt.gz "$BACKUP_ROOT/system/"
ssh aliyun-vitaclaw 'rm /tmp/journal-last14d.txt.gz'
```

---

## Pass 3 — Verification

### P3.1 — Manifest

```powershell
# On laptop
cd $BACKUP_ROOT
Get-ChildItem -Recurse -File | ForEach-Object {
  $h = (Get-FileHash -Algorithm MD5 $_.FullName).Hash.ToLower()
  "$h  $($_.FullName.Substring($BACKUP_ROOT.Length+1))"
} | Out-File -Encoding utf8 manifest-260610.txt

# Sanity totals
"=== TOTAL FILES ==="; (Get-ChildItem -Recurse -File | Measure-Object).Count
"=== TOTAL BYTES ==="; (Get-ChildItem -Recurse -File | Measure-Object Length -Sum).Sum
```

Expected size: **~7-8 GB total** (compressed) for full MUST + SHOULD.

### P3.2 — Sample untar verification

For each tarball, untar to a scratch dir and verify a known-key fact:

| Tarball | Verify |
|---|---|
| `kol_scan-260610.db` | `sqlite3 ... "SELECT COUNT(*) FROM articles"` returns `1807` |
| `lightrag_storage-260610.tgz` | `tar -tzf | grep graph_chunk_entity_relation.graphml` |
| `qdrant-data-260610.tgz` | `tar -tzf | grep "lightrag_vdb_entities_.*/3072d"` matches |
| `vitaclaw-site-260610.tgz` | `tar -tzf | grep "dist/index.html"` matches |
| `tenantB-data-260610.tgz` | `tar -tzf | grep -E "data/(app|web|uploads)/"` matches |
| `secrets-260610.tgz.gpg` | `gpg -d ... | tar -tz | grep gcp-paid-sa.json` |
| `system-configs-260610.tgz` | `tar -tzf | grep -E "Caddyfile|kb-api.service|hosts"` |
| Each docker image tgz | `gunzip -c ... | docker load --quiet` returns image name |

### P3.3 — Aliyun snapshot redundancy

User already taking ECS snapshot. Snapshot + this targeted backup = belt-and-braces:
- Snapshot recovers everything (in-place / new instance) — preferred for full disaster
- Targeted backup recovers selectively — preferred for transplanting to **different** infrastructure (ACK / k8s) where snapshot is incompatible

---

## Sequencing summary

```
Pre-flight
  P0.1 docker prune + /tmp wipe   →  reclaim 14-20G ON aliyun
  P0.2 verify laptop disk         →  ≥20G free
  P0.3 mkdir backup tree          →  staging

Pass 1 (MUST, ~11G live → ~6G compressed)
  P1.1  secrets → encrypted        →  10K
  P1.2  system configs              →  100K
  P1.3  kol_scan.db                 →  63M
  P1.4  lightrag_storage             →  1.5G compressed
  P1.5  qdrant snapshots+data       →  1G compressed
  P1.6  vctb pg_dumpall              →  10M compressed
  P1.7  tenantB data dir            →  1.5G compressed
  P1.8  shared docker volumes       →  3G compressed
  P1.9  vitaclaw-site               →  300M compressed
  P1.10 custom docker images        →  3G compressed
  P1.11 planb-local-m1 configs      →  100K
  P1.12 omnigraph repo              →  150M compressed
  P1.13 kb SSG output               →  60M compressed

Pass 2 (SHOULD, ~2G live → ~1G compressed)
  P2.1  article images               →  900M compressed
  P2.2  omnigraph aux                →  20M compressed
  P2.3  vitaclaw upstream            →  60M compressed
  P2.4  journal slice                →  20M compressed

Pass 3 — verification + manifest
```

**Total compressed:** ~7-8 GB.
**Total wall time @ 100 Mbps:** ~15-25 min for the full Pass 1 + Pass 2.

---

## What this plan does NOT do

- **Does not actually run.** Review every block first.
- **Does not back up Hermes** (06-22 RO; user owns Hermes-side ops).
- **Does not capture deep journal history** (just last 14d). For full retention, add `journalctl --since` widening.
- **Does not download docker images for registry-pullable tags.** Re-pull on new env.
- **Does not handle DNS / domain switchover.** RESTORE_RUNBOOK does that.
- **Does not assume your laptop has 50 G free.** Adjust BACKUP_ROOT to external SSD if not.
- **Does not encrypt everything** — only the secrets bundle (P1.1). Other tarballs travel in cleartext over SSH (channel encrypted by SSH, at-rest unencrypted on laptop). Review threat model.

---

## What user must decide before running

1. **Tenant cleanup question:** keep / delete the 5 dead tenant dirs (viaproxy, finalfinal, debug2, cacheclear, bugfixtest, ~8G)? See UNKNOWNS.md.
2. **VDB archive question:** are `vdb_archive_*.json` (1.7G) still load-bearing post-Qdrant migration? If not, drop them.
3. **OmniGraph-Vault git path:** Option A (clone from GitHub on new env) or Option B (tar P1.12)?
4. **Backup target:** corp laptop SSD (default), or external SSD, or rclone to cloud?
5. **Encryption scope:** secrets-only (default), or whole-bundle with `gpg --symmetric`?
6. **Docker volume consistency:** hot dump (default) or scale-to-zero before dumping (paranoid)?
