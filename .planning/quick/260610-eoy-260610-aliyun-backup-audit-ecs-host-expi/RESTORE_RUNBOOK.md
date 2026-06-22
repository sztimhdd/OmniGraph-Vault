# 260610-eoy — New Environment Restore Runbook

**Purpose:** Restore the 3 production projects (omnigraph, vitaclaw SaaS, vitaclaw site) on a new host (ECS / ACK / VM / k8s).
**Source artifacts:** Backup tarballs from `BACKUP_PLAN.md` + Aliyun snapshot if applicable.
**Audience:** future-you, post-host-cutover.

**⚠️ Scope:** this runbook tells you HOW to redeploy what was on the old host. It does NOT prescribe ACK cluster topology, namespace layout, or k8s vs docker-compose decisions — that depends on user's current ACK plan.

---

## Prerequisites checklist

Before restoring:

- [ ] **New host reachable** — SSH key installed, can login as root or sudo user
- [ ] **Disk** — at least 100G free (live footprint ~70G + headroom for snapshots)
- [ ] **OS** — Ubuntu 22.04 or 24.04 (matches /etc/hosts + systemd unit format)
- [ ] **Domain DNS** — A record updated to point to new host's public IP. Caddy will auto-issue HTTP cert; if site-to-be is HTTPS, plan a brief downtime window between snapshot taken and DNS propagation.
- [ ] **Outbound network** — verify Vertex AI accessible from new host:
  ```bash
  curl -v https://us-central1-aiplatform.googleapis.com 2>&1 | head -20
  ```
  If TLS fails (rare but seen on Aliyun), apply `/etc/hosts` pin (step 5 below).
- [ ] **Software** — install via apt:
  ```bash
  apt update && apt install -y docker.io docker-compose-plugin caddy sqlite3 python3.11-venv python3-pip nodejs npm gpg jq curl wget rsync git
  systemctl enable --now docker caddy
  ```
  - **Python version:** must match Aliyun's Python 3.11+. If new host defaults to 3.12, that's fine — venv re-created from requirements.txt.
  - **Node version:** verify `node --version` matches what vitaclaw-site expects. If unclear, default to Node 20 LTS.
- [ ] **User accounts** — create `vitaclaw` system user for vitaclaw-site systemd service:
  ```bash
  useradd -r -s /usr/sbin/nologin -d /opt/vitaclaw -M vitaclaw
  ```

---

## Restore order (CRITICAL — follow this sequence)

The order matters because services depend on each other:

```
1. Filesystem restore + secrets decryption     (no services running yet)
2. SSH keys + system configs                   (Caddy, /etc/hosts)
3. Qdrant docker container                      (vector DB — kb-api needs it)
4. Vitaclaw shared infrastructure               (timescaledb, nats, postgres)
5. Vitaclaw services (orchestrator, ag-ui, ai-infra-rs, document-service)
6. Vitaclaw tenant containers (tenantB)
7. OmniGraph venv + kb-api systemd unit
8. Vitaclaw-site systemd unit
9. OmniGraph cron timers (DO NOT enable until #1-#8 verified)
10. Smoke tests + DNS cutover
```

---

## Step-by-step

### Step 1 — Restore filesystem layout

```bash
# On new host
export BACKUP_DIR=/mnt/backup-260610   # mount external SSD or rsync from laptop
mkdir -p /root/.hermes /root/.ssh /opt/vitaclaw /var/www /var/lib/qdrant /etc/vitaclaw

# OmniGraph live data
cd /root/.hermes && \
  tar -xzf $BACKUP_DIR/omnigraph-vault/lightrag_storage-260610.tgz   # creates /root/.hermes/lightrag_storage but we want /root/.hermes/omonigraph-vault/lightrag_storage
# Fix: explicitly target the canonical typo path
mkdir -p /root/.hermes/omonigraph-vault
cd /root/.hermes/omonigraph-vault && \
  tar -xzf $BACKUP_DIR/omnigraph-vault/lightrag_storage-260610.tgz
tar -xzf $BACKUP_DIR/omnigraph-vault/article-images-260610.tgz       # extracts images/
tar -xzf $BACKUP_DIR/omnigraph-vault/omg-aux-260610.tgz                # extracts checkpoints/, entity_buffer/, etc

# OmniGraph code repo — Option A (clone from GitHub, preferred)
cd /root && \
  git clone https://github.com/<owner>/OmniGraph-Vault.git
# OR Option B (restore from tarball if GitHub unreachable)
# cd /root && tar -xzf $BACKUP_DIR/omnigraph-vault/omnigraph-repo-260610.tgz

# Restore production DB to canonical path
cp $BACKUP_DIR/omnigraph-vault/kol_scan-260610.db /root/OmniGraph-Vault/data/kol_scan.db

# Recreate the symlink that .hermes expects
ln -sf /root/OmniGraph-Vault/data/kol_scan.db /root/.hermes/omonigraph-vault/kol_scan.db

# KB SSG output (Caddy serves from /var/www/kb)
cd /var/www && tar -xzf $BACKUP_DIR/omnigraph-vault/kb-www-260610.tgz

# Vitaclaw site
mkdir -p /opt/vitaclaw/control-plane && \
  cd /opt/vitaclaw/control-plane && \
  tar -xzf $BACKUP_DIR/vitaclaw-site/vitaclaw-site-260610.tgz       # extracts as ./, rename to vitaclaw-site
mv ./vitaclaw-site-restore /opt/vitaclaw/control-plane/vitaclaw-site || \
  cd /opt/vitaclaw/control-plane && mkdir vitaclaw-site && mv $BACKUP_DIR/vitaclaw-site/vitaclaw-site-260610.tgz . && tar -xzf vitaclaw-site-260610.tgz -C vitaclaw-site

chown -R vitaclaw:vitaclaw /opt/vitaclaw/control-plane/vitaclaw-site
( cd /opt/vitaclaw/control-plane/vitaclaw-site && npm ci )

# Vitaclaw planb-local-m1 (configs only — tenant data restored separately)
mkdir -p /opt/vitaclaw/planb-local-m1
cd /opt/vitaclaw/planb-local-m1 && \
  tar -xzf $BACKUP_DIR/vitaclaw-saas/planb-config-260610.tgz
tar -xzf $BACKUP_DIR/vitaclaw-saas/vitaclaw-upstream-260610.tgz -C upstream/

# Vitaclaw tenantB data
mkdir -p /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB
cd /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB && \
  tar -xzf $BACKUP_DIR/vitaclaw-saas/tenantB-data-260610.tgz
chown -R 1000:1000 /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB
```

### Step 2 — Decrypt + place secrets

```bash
# Decrypt the bundle (interactive password prompt)
gpg -d -o /tmp/secrets-260610.tgz $BACKUP_DIR/secrets-encrypted/secrets-260610.tgz.gpg
mkdir -p /tmp/secrets-untar
cd /tmp/secrets-untar && tar -xzf /tmp/secrets-260610.tgz

# Place secrets in canonical paths (preserve perms!)
install -m 600 -o root -g root /tmp/secrets-untar/root/.hermes/.env                      /root/.hermes/.env
install -m 600 -o root -g root /tmp/secrets-untar/root/.hermes/auth.json                 /root/.hermes/auth.json
install -m 600 -o root -g root /tmp/secrets-untar/root/.hermes/gcp-paid-sa.json          /root/.hermes/gcp-paid-sa.json
install -m 600 -o root -g root /tmp/secrets-untar/root/.hermes/config.yaml               /root/.hermes/config.yaml

mkdir -p /root/.ssh && chmod 700 /root/.ssh
install -m 600 /tmp/secrets-untar/root/.ssh/id_ed25519                                   /root/.ssh/id_ed25519
install -m 644 /tmp/secrets-untar/root/.ssh/id_ed25519.pub                               /root/.ssh/id_ed25519.pub
install -m 600 /tmp/secrets-untar/root/.ssh/authorized_keys                              /root/.ssh/authorized_keys
install -m 600 /tmp/secrets-untar/root/.ssh/known_hosts                                  /root/.ssh/known_hosts

mkdir -p /etc/vitaclaw && chgrp vitaclaw /etc/vitaclaw && chmod 750 /etc/vitaclaw
install -m 640 -g vitaclaw /tmp/secrets-untar/etc/vitaclaw/vitaclaw-site.env             /etc/vitaclaw/vitaclaw-site.env

install -m 600 -o 1000 -g 1000 /tmp/secrets-untar/opt/vitaclaw/planb-local-m1/.env       /opt/vitaclaw/planb-local-m1/.env
install -m 600 -o 1000 -g 1000 /tmp/secrets-untar/opt/vitaclaw/planb-local-m1/.env.local /opt/vitaclaw/planb-local-m1/.env.local
install -m 600 -o 1000 -g 1000 \
    /tmp/secrets-untar/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env \
    /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env
install -m 600 -o 1000 -g 1000 \
    /tmp/secrets-untar/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed \
    /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed

# IMMEDIATELY wipe the plaintext temp directory
shred -u /tmp/secrets-260610.tgz
rm -rf /tmp/secrets-untar
```

### Step 3 — System configs

```bash
mkdir -p /tmp/sysconf && cd /tmp/sysconf && \
  tar -xzf $BACKUP_DIR/system/system-configs-260610.tgz

# Caddy
install -m 644 /tmp/sysconf/etc/caddy/Caddyfile                                          /etc/caddy/Caddyfile
mkdir -p /var/lib/caddy/.config/caddy /var/lib/caddy/.local/share/caddy
chown -R caddy:caddy /var/lib/caddy
install -m 600 -o caddy -g caddy /tmp/sysconf/var/lib/caddy/.config/caddy/autosave.json /var/lib/caddy/.config/caddy/autosave.json

# /etc/hosts (preserves Vertex pin)
cp /etc/hosts /etc/hosts.orig
sort -u /tmp/sysconf/etc/hosts /etc/hosts > /etc/hosts.merged
mv /etc/hosts.merged /etc/hosts

# systemd units
cp /tmp/sysconf/etc/systemd/system/kb-api.service                  /etc/systemd/system/
cp /tmp/sysconf/etc/systemd/system/vitaclaw-site.service           /etc/systemd/system/
cp /tmp/sysconf/etc/systemd/system/qdrant-snapshot.service         /etc/systemd/system/
cp /tmp/sysconf/etc/systemd/system/qdrant-snapshot.timer           /etc/systemd/system/
cp /tmp/sysconf/etc/systemd/system/omnigraph-*.service             /etc/systemd/system/
cp /tmp/sysconf/etc/systemd/system/omnigraph-*.timer               /etc/systemd/system/

# CRITICAL: copy the override.conf hot-fixes
mkdir -p /etc/systemd/system/{kb-api,omnigraph-daily-ingest,omnigraph-afternoon-ingest,omnigraph-evening-ingest}.service.d
cp /tmp/sysconf/etc/systemd/system/kb-api.service.d/override.conf                    /etc/systemd/system/kb-api.service.d/
cp /tmp/sysconf/etc/systemd/system/omnigraph-daily-ingest.service.d/override.conf    /etc/systemd/system/omnigraph-daily-ingest.service.d/
cp /tmp/sysconf/etc/systemd/system/omnigraph-afternoon-ingest.service.d/override.conf /etc/systemd/system/omnigraph-afternoon-ingest.service.d/
cp /tmp/sysconf/etc/systemd/system/omnigraph-evening-ingest.service.d/override.conf  /etc/systemd/system/omnigraph-evening-ingest.service.d/

# crontab + cron.d
crontab /tmp/sysconf/tmp/crontab-root-260610.txt 2>/dev/null || \
  (cd /tmp/sysconf/tmp && crontab crontab-root-260610.txt) 2>/dev/null || \
  (echo "0 12 * * * /root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh >> /var/log/kb-rebuild.log 2>&1" | crontab -)

# iptables (apply only if firewall ruleset still relevant; review first)
# iptables-restore < /tmp/sysconf/tmp/iptables-260610.rules

systemctl daemon-reload
systemctl restart caddy
```

### Step 4 — Qdrant restore

```bash
# Restore filesystem
cd /var/lib && tar -xzf $BACKUP_DIR/qdrant/qdrant-data-260610.tgz   # extracts qdrant/
chown -R 1000:1000 /var/lib/qdrant   # qdrant container UID

# Run Qdrant container — bind to 127.0.0.1 only (Caddy doesn't proxy to it; only kb-api needs internal access)
docker pull qdrant/qdrant:v1.11.5
docker run -d \
  --name qdrant \
  --restart unless-stopped \
  -p 127.0.0.1:6333:6333 \
  -v /var/lib/qdrant:/qdrant/storage \
  qdrant/qdrant:v1.11.5

# Verify collections present
sleep 5
curl -sS http://127.0.0.1:6333/collections | jq '.result.collections[].name'
# Expected:
#   "lightrag_vdb_chunks_gemini_embedding_2_3072d"
#   "lightrag_vdb_entities_gemini_embedding_2_3072d"
#   "lightrag_vdb_relationships_gemini_embedding_2_3072d"
```

### Step 5 — /etc/hosts pin (only if needed)

```bash
# If Vertex AI calls fail with cert error or DNS failure, pin to known-good IP
grep -q "aiplatform.googleapis.com" /etc/hosts || cat >> /etc/hosts <<EOF
142.250.73.106 aiplatform.googleapis.com
142.250.73.106 oauth2.googleapis.com
142.250.73.106 us-central1-aiplatform.googleapis.com
EOF
```

### Step 6 — Vitaclaw shared infra + tenants

```bash
# Pull registry images
for img in postgres:16-alpine timescale/timescaledb:2.17.2-pg16 nats:2.10 \
           oven/bun:1.3.4 oven/bun:1.3.4-slim minio/minio:RELEASE.2025-02-07T23-21-09Z \
           nginx:alpine; do
  docker pull "$img"
done

# Load custom-built images
for f in $BACKUP_DIR/docker-images/img-*.tgz; do
  echo "loading $f"
  gunzip -c "$f" | docker load
done

# Restore docker volumes (each gets its own helper)
for v in vitaclaw-shared_convstore_runtime \
         vitaclaw-shared_delivery_runtime \
         vitaclaw-shared_inbox_runtime \
         vitaclaw-shared_push_runtime \
         vitaclaw-shared_timescaledb_data \
         vitaclaw-shared_nats_data \
         vc_tb_minio_data; do
  docker volume create "$v"
  docker run --rm -v "$v":/data -v $BACKUP_DIR/vitaclaw-saas:/dump alpine \
    sh -c "cd /data && tar -xzf /dump/vol-$v-260610.tgz"
done

# Compose-up the shared services first (verify .env paths in compose files match restored secrets)
cd /opt/vitaclaw/planb-local-m1/vitaclaw-local && \
  docker compose -f compose/conversation-store.yml up -d
sleep 10 && docker ps | grep vc-

# Restore tenantB Postgres (after vc_tb-postgres-1 is up)
docker exec -i vc_tb-postgres-1 psql -U postgres < <(gunzip -c $BACKUP_DIR/vitaclaw-saas/vctb-pgdump-260610.sql.gz)

# Verify
docker exec vc_tb-postgres-1 psql -U postgres -c '\l'
```

**Caveat:** the planb-local-m1 docker-compose orchestration is NOT fully captured in `BACKUP_PLAN.md` — only the visible compose files (conversation-store, delivery) are. The user may have additional compose files / scripts launching the other 18 containers. Cross-reference with `docker ps` output captured in `BACKUP_INVENTORY.md` and the `compose/` dir contents to identify what spins up each service.

### Step 7 — OmniGraph Python venv

```bash
cd /root/OmniGraph-Vault && \
  python3 -m venv venv && \
  venv/bin/pip install --upgrade pip && \
  venv/bin/pip install -r requirements.txt

# Apply the LightRAG atomic-write patch (CRITICAL — protects graphml from SIGTERM corruption)
# The patch is in lib/lightrag_atomic_write_patch.py per memory
# After fresh `pip install lightrag`, the venv ships with non-atomic write_nx_graph
# that streams to target file — this is the 6/7 corruption root cause.
# The patch must be re-applied after every fresh install or pip --force-reinstall lightrag.
python -c "import lightrag; print(lightrag.__file__)"
# Apply via the in-repo patch script (verify path on new host):
# bash scripts/apply_lightrag_atomic_write_patch.sh
# (Confirm the script exists in OmniGraph-Vault/scripts/ — if absent, manually edit
#  lightrag/kg/networkx_impl.py to write to .tmp + os.replace.)
```

### Step 8 — kb-api + vitaclaw-site

```bash
systemctl enable --now kb-api.service
sleep 5
journalctl -u kb-api.service -n 30 --no-pager

# Probe
curl -sS http://127.0.0.1:8766/health
# Expected: 200 + JSON

systemctl enable --now vitaclaw-site.service
sleep 3
journalctl -u vitaclaw-site.service -n 30 --no-pager
curl -sS http://127.0.0.1:3200/health
```

### Step 9 — Smoke tests (END TO END)

```bash
# 9.1 Caddy reverse proxy
curl -sS http://127.0.0.1/health
# Expected: "vitaclaw demo host ok"

# 9.2 KB site (front)
curl -sS http://127.0.0.1/kb/ -I
# Expected: 200 OK, Content-Type: text/html

# 9.3 KB API
curl -sS "http://127.0.0.1/kb/api/search?q=AI&mode=fts&limit=3"
# Expected: JSON with non-empty `items` (sanity: production has 1807 articles)

# 9.4 KB synthesize (full LightRAG roundtrip — verifies Vertex + Qdrant + graphml)
curl -sS -X POST http://127.0.0.1:8766/api/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is RAG?","mode":"hybrid"}' | head -50
# Expected: JSON containing `markdown` field with non-empty body and `sources` array
```

### Step 10 — Enable cron timers ONLY after smoke green

```bash
systemctl enable --now omnigraph-daily-ingest.timer \
                       omnigraph-afternoon-ingest.timer \
                       omnigraph-evening-ingest.timer \
                       omnigraph-kol-scan.timer \
                       omnigraph-kol-classify.timer \
                       omnigraph-kol-enrich.timer \
                       omnigraph-kol-zombie-cleanup.timer \
                       omnigraph-rss-fetch.timer \
                       omnigraph-rss-rescrape.timer \
                       omnigraph-rss-layer2-classify.timer \
                       omnigraph-reconcile.timer \
                       omnigraph-translate.timer \
                       omnigraph-daily-digest.timer \
                       omnigraph-vertex-probe.timer \
                       qdrant-snapshot.timer

systemctl list-timers --no-pager | grep omnigraph
```

### Step 11 — DNS cutover

```bash
# Once smoke is green:
# 1. Take a fresh ECS snapshot of NEW host
# 2. Update domain A record → new public IP
# 3. Wait for DNS propagation (5-30 min)
# 4. Re-test from external network: curl https://<domain>/kb/api/search?q=test&mode=fts
# 5. Stop omnigraph cron on OLD host (avoid double-runs writing to two graphs)
#    ssh aliyun-vitaclaw 'systemctl stop omnigraph-*.timer'
# 6. Monitor new host journal for 24h before decommissioning old ECS
```

---

## Known pitfalls (from project history)

1. **Directory typo** — runtime data uses `omonigraph` (NOT `omnigraph`). Preserve verbatim. Code references it via `config.py`.
2. **LightRAG atomic write patch** — vendored networkx_impl.py streams write directly. Patch in BOTH venvs (`venv/` + any second venv if recreated). `pip install --force-reinstall lightrag` wipes the patch. (memory: lightrag-networkx-write-not-atomic)
3. **Qdrant collection naming suffix** — LightRAG appends `_<embed_model>_<dim>d`. Hardcoding short names = 404. Don't rename collections.
4. **DeepSeek API key required even on Vertex path** — `lib/__init__.py` eager-imports `deepseek_model_complete`. Set `DEEPSEEK_API_KEY=dummy` if not using DeepSeek. (memory: confirmed in `.env`)
5. **`auth_type='pat'` for SDK** — only relevant for Databricks calls; ignore for Vertex (uses SA JWT exchange).
6. **WeChat scrape throttle** — 50 articles per batch + cooldown. Don't expect to re-scrape 1807 articles in one go.
7. **Vision cascade SiliconFlow balance** — pre-batch check `¥1.00 / 770 images = ¥0.0013 each`. Top up before resuming heavy ingest.
8. **systemd schedule overlap** — daily-ingest + evening-ingest can collide if RuntimeMaxSec>6h. The override.conf caps at 10800s (3h) — preserve it. (memory: systemd-schedule-overlap-sigterm-corruption)
9. **`omnigraph-kol-scan.service` was failing on old host** — verify reason on new host before enabling. Probably WeChat session auth. See ISSUES tracker.
10. **Apify SDK 3.0** — recent commit (a5ccc0c) fixed `Run typed not subscriptable`. Make sure deps install picks up the updated apify-client.
11. **Qdrant container restart policy** — old host had no `--restart`. New host: include `--restart unless-stopped` (memory: qdrant-docker-no-restart-policy-trap).
12. **No TLS state to restore** — Caddyfile uses HTTP. If switching to HTTPS, let Caddy auto-issue (uncomment `:443` block + add cert directives).

---

## Per-project quick-reference

### omnigraph
- **Code:** `/root/OmniGraph-Vault` (git pull or P1.12 tarball)
- **Venv:** `/root/OmniGraph-Vault/venv/` (re-create from requirements.txt)
- **Runtime data:** `/root/.hermes/omonigraph-vault/` (from P1.4 + P2.1 + P2.2)
- **DB:** `/root/OmniGraph-Vault/data/kol_scan.db` (from P1.3)
- **Qdrant:** docker container `qdrant`, data at `/var/lib/qdrant/` (from P1.5)
- **Service:** `kb-api.service` (port 8766) + 14 omnigraph-* timers
- **SSG output:** `/var/www/kb/` (from P1.13)
- **Smoke:** `curl localhost:8766/health` + `curl localhost/kb/api/search?q=test&mode=fts`

### vitaclaw SaaS (planb-local-m1)
- **Code:** `/opt/vitaclaw/planb-local-m1/` (from P1.11)
- **Tenant data:** `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/` (from P1.7)
- **Postgres:** docker `vc_tb-postgres-1` (from P1.6 dump)
- **Volumes:** 7 shared docker volumes (from P1.8)
- **Services:** ~20 docker containers via compose (orchestrator, ag-ui, document-service, identity-service, persona-service, skill-service, tenant-web, ai-infra-rs, conversation-store, delivery, inbox, push, timescaledb, nats, minio, admin-dashboard, management-service)
- **Smoke:** `curl tenantB.<new-host>.nip.io:3102` ; `docker exec vc_tb-postgres-1 psql ... -c '\l'`

### vitaclaw site
- **Code:** `/opt/vitaclaw/control-plane/vitaclaw-site/` (from P1.9)
- **Service:** `vitaclaw-site.service` (Node, port 3200, User=vitaclaw)
- **Routing:** Caddy `:80` `handle / *` → file_server on `dist/` ; `handle /api/* → 127.0.0.1:3200`
- **Smoke:** `curl localhost:3200` and `curl localhost/`

---

## Rollback plan

If restore fails after substantial work:

1. Aliyun snapshot (taken before cutover) is the canonical fallback. Spin up a fresh ECS from snapshot, point DNS back, you're whole again.
2. The targeted backup tarballs in `$BACKUP_DIR` remain available for selective re-extraction.
3. Encrypted secrets bundle remains encrypted — only decrypt on success path.

---

## Decommission checklist for OLD ECS

After 7-day burn-in on new host:

- [ ] Confirm new host journal has 7d clean omnigraph cron history
- [ ] Confirm Qdrant snapshot timer fired at least once on new host
- [ ] Confirm `articles_fts` count on new host matches old host's count at cutover time
- [ ] Confirm domain DNS pointing to new host > 6h
- [ ] Take final ECS snapshot of OLD host (insurance)
- [ ] Stop OLD host omnigraph timers: `ssh aliyun-vitaclaw 'systemctl disable --now omnigraph-*.timer'`
- [ ] Release public IP from OLD host
- [ ] Schedule OLD ECS for deletion (after subscription expires naturally OR explicit termination)
