# Aliyun Backup Inventory — 2026-06-10/11

**Source**: Aliyun ECS `101.133.154.49` (`iZuf6gqyu1mv5fhhjyhxpgZ` / `aliyun-vitaclaw`)
**Backup window**: 2026-06-10 evening → 2026-06-11 02:56 UTC+8 finalize
**Backup target**: `backup_prod@139.159.179.249:/home/backup_prod/aliyun-backup-260610/`
**Total**: 15 tarballs + 1 sqlite + manifest = ~5.6 GB
**Source HEAD git SHA at backup**: see `tier2/omnigraph-repo-260610.tgz` `.git/HEAD` (4 commits behind `origin/main` — record SHA via `git -C /tmp/extracted log -1 --format=%H` post-extract)
**Backup consistency**: `omnigraph-*-ingest.timer` units NOT explicitly stopped pre-tar — tarballs are **crash-consistent during ingest window**, NOT quiesced point-in-time. Verify Section 9 graphml node count + Qdrant points; if mismatch, plan re-ingest pass.

---

## TOC

0. [Quick start (TL;DR)](#0-quick-start-tldr)
1. [Directory layout](#1-directory-layout)
2. [Per-tarball inventory](#2-per-tarball-inventory)
3. [Restore order](#3-restore-order)
4. [SaaS sub-restore (optional)](#4-saas-sub-restore-only-if-vitaclaw-planb-local-m1-needed)
5. [Vitaclaw 主网站 sub-restore](#5-vitaclaw-主网站-sub-restore)
6. [Pitfalls — pre-restore](#6a-pitfalls--pre-restore)
7. [Pitfalls — post-restore](#6b-pitfalls--post-restore)
8. [DO NOT block (绝对禁止)](#7-do-not-block-绝对禁止)
9. [Decision unknowns](#8-decision-unknowns)
10. [Source repos](#9-source-repos)
11. [Verify (success criteria)](#10-verify-success-criteria)

---

## 0. Quick start (TL;DR)

```bash
# 1. Verify integrity FIRST (refuse to extract if md5 fails)
cd /home/backup_prod/aliyun-backup-260610
md5sum -c manifest-260610.md5 || { echo "ABORT: corrupted backup"; exit 1; }

# 2. Disk + tz precheck on TARGET host
df -h / | awk 'NR==2 {if ($4+0 < 40) {print "ABORT: <40GB free"; exit 1}}'
timedatectl set-timezone Asia/Shanghai   # match Aliyun source tz (CST UTC+8)

# 3. STOP all services that touch restore data (idempotent)
for s in kb-api omnigraph-daily-ingest.timer omnigraph-evening-ingest.timer \
         omnigraph-kol-scan.timer qdrant-snapshot.timer vitaclaw-site caddy; do
  systemctl stop "$s" 2>/dev/null || true
done
docker stop qdrant 2>/dev/null || true
docker rm qdrant 2>/dev/null || true

# 4. Dry-run inventory (confirm top-level dir of each tarball)
for t in tier*/*.tgz; do echo "=== $t ==="; tar -tzf "$t" | head -3; done

# 5. Then follow Section 3 Step 1-10 in order, verify Section 10.
```

**Success criteria**: all 5 Section 10 checks PASS + `journalctl -u kb-api -n 20` shows zero errors for 5 min after enable.

---

## 1. Directory layout

```
aliyun-backup-260610/
├── manifest-260610.md5
├── INVENTORY.md                    (this file)
├── kol_scan-260610.db              (66M — sqlite hot-backup, NOT inside tarball)
├── tier0/        (omnigraph 命门 / restore-or-die)
│   ├── secrets-260610.tgz
│   ├── sysconf-260610.tgz
│   ├── lightrag_live-260610.tgz
│   └── qdrant-260610.tgz
├── tier0_6/      (vitaclaw 主网站 / main marketing site)
│   └── vitaclaw-site-src-260610.tgz
├── tier0_7/      (vitaclaw SaaS / optional planb)
│   ├── vitaclaw-planb-deploy-260610.tgz
│   ├── planb-local-m1-260610.tgz
│   ├── vitaclaw-extras-260610.tgz
│   └── saas-secrets-260610.tgz
├── tier1/        (Hermes RO unlock fallback until 2026-06-22)
│   ├── vdb_archive_rel-260610.tgz
│   └── vdb_archive_other-260610.tgz
└── tier2/        (累积投入 / nice-to-have)
    ├── images-260610.tgz
    ├── omnigraph-aux-260610.tgz
    └── omnigraph-repo-260610.tgz
```

**Tier 含义**: T0 = 必先恢复 / T0.6 = 主网站 / T0.7 = SaaS optional / T1 = Hermes fallback / T2 = 累积资产, 可重生.

**全局 invariant** (1次说清楚, 后续不再重复):

- 路径 `omonigraph-vault` 是 **typo canonical** — `config.py` 硬编码. **绝对不要 "fix" 成 `omnigraph`**. 任何 well-meaning agent 改名 = 全部路径 silent break.
- Qdrant collection 名 suffix `_gemini_embedding_2_3072d` 由 LightRAG 自动加. **DO NOT RENAME** — 改名 hybrid retrieve silent return 0 sources.
- LightRAG vendored `networkx_impl.py` write 非原子. SIGTERM mid-graphml-write → file truncate. 必须打 atomic-write patch (Step 8).

---

## 2. Per-tarball inventory

### Tier 0 — omnigraph 命门

| File | Size | Source path | Extract cmd | Top-level entry | Critical caveats |
|------|------|-------------|-------------|-----------------|------------------|
| `tier0/secrets-260610.tgz` | 5.9K | `/root/.hermes/` + `/root/.ssh/` | `tar -xzf tier0/secrets-260610.tgz -C /` | `root/.hermes/`, `root/.ssh/` | 解压后 `chmod 600 .ssh/id_ed25519 .ssh/authorized_keys .hermes/.env .hermes/gcp-paid-sa.json`. 含 GCP SA JSON (Vertex AI), DeepSeek/SiliconFlow/Gemini API keys, SSH host + user keys. |
| `tier0/sysconf-260610.tgz` | 17K | `/etc/` selective | `tar -xzf tier0/sysconf-260610.tgz -C /` | `etc/` | 含 systemd units (`kb-api`, `omnigraph-*`, `qdrant-snapshot`, `vitaclaw-site`) + 4× `override.conf` (含 daily-ingest `RuntimeMaxSec=10800` hot-fix 防 graphml SIGTERM corruption) + Caddyfile + `/etc/hosts` (Vertex pin `142.250.73.106`) + `iptables-save.txt` + `ufw-status.txt` (TEXT dumps, 需 `iptables-restore < /etc/iptables-save.txt`). **Caddyfile 改 hostname** 后才能 `systemctl start caddy`. |
| `kol_scan-260610.db` | 66M | `/root/OmniGraph-Vault/data/kol_scan.db` (`sqlite3 .backup` hot-copy) | `cp kol_scan-260610.db /root/OmniGraph-Vault/data/kol_scan.db` (NOT a tarball) | n/a | 14 tables: articles=1807 / rss_articles=2200 / classifications / extracted_entities / accounts etc. **解压后必跑 `sqlite3 ... 'PRAGMA integrity_check;'`** 期望 `ok`. |
| `tier0/lightrag_live-260610.tgz` | 28M | `/root/.hermes/omonigraph-vault/lightrag_storage/` | `tar -xzf tier0/lightrag_live-260610.tgz -C /root/.hermes/omonigraph-vault/` | `lightrag_storage/` | Live graphml 30558 nodes / 44030 edges (finalized 2026-06-11 02:56) + 5× `kv_store_*.json`. **排除**: `*.bak` `*.corrupt` `archive/`. |
| `tier0/qdrant-260610.tgz` | 1.75G | `/var/lib/qdrant/` | `tar -xzf tier0/qdrant-260610.tgz -C /var/lib` | `qdrant/` | 3 collections (suffix `_gemini_embedding_2_3072d`): chunks=3665 pts / entities=57242 / relationships=79394 + `raft_state.json` + aliases. **DO NOT RENAME**. **解压前** 必须 `docker stop qdrant && docker rm qdrant && rm -rf /var/lib/qdrant/*` — 否则 file lock corruption. |

### Tier 0.6 — vitaclaw 主网站

| File | Size | Source path | Extract cmd | Top-level entry | Critical caveats |
|------|------|-------------|-------------|-----------------|------------------|
| `tier0_6/vitaclaw-site-src-260610.tgz` | 329M | `/opt/vitaclaw/control-plane/vitaclaw-site/` | `tar -xzf tier0_6/vitaclaw-site-src-260610.tgz -C /opt/vitaclaw/control-plane/` | `vitaclaw-site/` | Vite + Node + `.git` + `public/` (含 `hero.mp4` 128M + 4 demo videos). **排除**: `node_modules/`, `dist/`. **当前 branch** `aliyun-backup` + 3 uncommitted `.tsx` (`src/components/{business,navbar,pricing}.tsx`). **GitHub canonical**: `github.com/sztimhdd/vitaclaw-site.git`. **Node version** 看 `package.json#engines` — mismatch (e.g. host node 22 vs project node 18) → `npm ci` fail. |

### Tier 0.7 — vitaclaw SaaS

| File | Size | Source path | Extract cmd | Top-level entry | Critical caveats |
|------|------|-------------|-------------|-----------------|------------------|
| `tier0_7/vitaclaw-planb-deploy-260610.tgz` | 26M | `/opt/vitaclaw/vitaclaw-planb-deploy/` | `tar -xzf tier0_7/vitaclaw-planb-deploy-260610.tgz -C /opt/vitaclaw/` | `vitaclaw-planb-deploy/` | Canonical git tracked. **目录名 `vitaclaw-planb-deploy` ≠ GitHub repo 名 `vitaclaw-planb-local-m1`** (`github.com/sztimhdd/vitaclaw-planb-local-m1.git`); fresh clone 后 rename: `git clone <repo> vitaclaw-planb-deploy`. main clean. |
| `tier0_7/planb-local-m1-260610.tgz` | 49M | `/opt/vitaclaw/planb-local-m1/` | `tar -xzf tier0_7/planb-local-m1-260610.tgz -C /opt/vitaclaw/` | `planb-local-m1/` | **Top-level 不是 git repo**, 是 live working tree. **vendored `upstream/geekclaw/.git` + `upstream/geekskill/.git` 是 git repo**. Hand-edits 在 `compose/` `templates/` `web-src/` (relative to `vitaclaw-planb-deploy`). **排除**: `tenantB/{data,db,.env*}` + 5 dead tenants + `node_modules` + `dist`. |
| `tier0_7/vitaclaw-extras-260610.tgz` | 362M | `/opt/vitaclaw/{.deploy-backups,.incoming,README.md}` | `tar -xzf tier0_7/vitaclaw-extras-260610.tgz -C /opt/vitaclaw/` | `.deploy-backups/`, `.incoming/`, `README.md` | Deploy artifacts. **排除**: `kubectl.gz`, `vitaclaw-planb-images.tar.gz` (image archive on source host but NOT in this backup; agent ask user for registry hostname OR re-pull from `vitaclaw-planb-images.tar.gz` location TBD). |
| `tier0_7/saas-secrets-260610.tgz` | 2.7K | 4× `.env` files | `tar -xzf tier0_7/saas-secrets-260610.tgz -C /` | `opt/vitaclaw/...` | JWT keypair + POSTGRES_PASSWORD + INTERNAL_SERVICE_TOKEN. **不含** runtime data. 解压后 `chmod 600 /opt/vitaclaw/planb-local-m1/.env*` etc. |

### Tier 1 — vdb_archive (Hermes RO fallback until 2026-06-22)

| File | Size | Source path | Extract cmd | Top-level entry | Critical caveats |
|------|------|-------------|-------------|-----------------|------------------|
| `tier1/vdb_archive_rel-260610.tgz` | 833M | `vdb_archive_relationships.json` | `tar -xzf tier1/vdb_archive_rel-260610.tgz -C /root/.hermes/omonigraph-vault/lightrag_storage/` | `vdb_archive_relationships.json` | 1.1G uncompressed. **关键** — Databricks fallback. Restore 仅当 Hermes RO 解锁前需要 fallback. |
| `tier1/vdb_archive_other-260610.tgz` | 596M | `vdb_archive_chunks.json` + `vdb_archive_entities.json` | `tar -xzf tier1/vdb_archive_other-260610.tgz -C /root/.hermes/omonigraph-vault/lightrag_storage/` | `vdb_archive_chunks.json`, `vdb_archive_entities.json` | Paranoid 备份 — Qdrant tier0 已含 live 等价. 2026-06-22 解锁后可 drop. |

### Tier 2 — 累积投入

| File | Size | Source path | Extract cmd | Top-level entry | Critical caveats |
|------|------|-------------|-------------|-----------------|------------------|
| `tier2/images-260610.tgz` | 1.75G | `/root/.hermes/omonigraph-vault/images/` | `tar -xzf tier2/images-260610.tgz -C /` | `root/.hermes/omonigraph-vault/images/` | 465 article-image dirs. SiliconFlow vision pipeline 累积 ¥0.0013/img. **Rebuild cost** ~¥6-7 paid. |
| `tier2/omnigraph-aux-260610.tgz` | 5.7M | `checkpoints/`, `entity_buffer/`, `canonical_map.json`, `query_history.jsonl`, `synthesis_archive`, `synthesis_output.md` | `tar -xzf tier2/omnigraph-aux-260610.tgz -C /` | `root/.hermes/omonigraph-vault/...` | 325 ingest checkpoints + 273 entity_buffer. Resume safety net. |
| `tier2/omnigraph-repo-260610.tgz` | 195M | `/root/OmniGraph-Vault/` | `tar -xzf tier2/omnigraph-repo-260610.tgz -C /root/` | `OmniGraph-Vault/` | **排除** `venv/`, `venv-aim1/`, `__pycache__/`, `data/kol_scan.db.bak-*`. **当前 4 commits BEHIND `origin/main`** + 3 untracked. **首选 fresh clone** `github.com/sztimhdd/OmniGraph-Vault.git` + `git checkout <SHA-from-backup-HEAD>` 匹配 backup state. |

---

## 3. Restore order

**Pre-flight already done in Section 0 TL;DR** (md5 verify, disk check, tz set, services stopped). 不重复.

```bash
# === Step 1: OS prereqs ===
apt update && apt install -y docker.io caddy sqlite3 python3.11 python3.11-venv \
  python3-pip nodejs npm rsync iptables-persistent
# (drop nginx — Aliyun used Caddy; nginx conflicts on :80)
useradd -r -s /usr/sbin/nologin vitaclaw 2>/dev/null || true
python3.11 --version || { echo "ABORT: python3.11 required (LightRAG 1.4.15 pin)"; exit 1; }

# === Step 2: sysconf — systemd units + Caddy + /etc/hosts pin + firewall ===
tar -xzf tier0/sysconf-260610.tgz -C /
systemctl daemon-reload   # do NOT enable yet — data not in place
iptables-restore < /etc/iptables-save.txt 2>/dev/null || echo "WARN: iptables restore skipped"
# EDIT Caddyfile if target hostname != source (vitaclaw.cn etc.):
#   sed -i 's/old.host/new.host/g' /etc/caddy/Caddyfile
# Verify Vertex pin reachable: dig us-central1-aiplatform.googleapis.com +short
# If 142.250.73.106 stale (GFE rolling), update /etc/hosts before SA token refresh

# === Step 3: secrets — .ssh + .hermes/.env ===
tar -xzf tier0/secrets-260610.tgz -C /
chmod 600 /root/.ssh/id_ed25519 /root/.ssh/authorized_keys \
          /root/.hermes/.env /root/.hermes/gcp-paid-sa.json
chmod 644 /root/.ssh/id_ed25519.pub /root/.ssh/known_hosts
# Confirm OMNIGRAPH_BASE_DIR in /root/.hermes/.env points to /root/.hermes/omonigraph-vault
grep '^OMNIGRAPH_BASE_DIR=' /root/.hermes/.env

# === Step 4: Qdrant — pre-clean, extract, start docker ===
# Pre-condition: Section 0 already stopped/removed any prior container + wiped /var/lib/qdrant
[ -z "$(ls -A /var/lib/qdrant 2>/dev/null)" ] || { echo "ABORT: /var/lib/qdrant not empty — run Section 0 cleanup"; exit 1; }
tar -xzf tier0/qdrant-260610.tgz -C /var/lib

# Qdrant version: backup did NOT preserve original image tag explicitly.
# Inspect raft_state.json + collection meta for version hint:
grep -r '"version"' /var/lib/qdrant/storage/collections/*/config.json 2>/dev/null | head -3
# If unclear, default to v1.11.0 (known-good as of backup era). If image pull fails (corp net):
#   docker load < <offline-qdrant.tar>   # if available on target
docker run -d --name qdrant --restart=unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v /var/lib/qdrant:/qdrant/storage \
  qdrant/qdrant:v1.11.0
sleep 5
curl -sf http://localhost:6333/collections | jq '.result.collections[].name' || \
  { echo "ABORT: Qdrant not loading — try alternate version tag"; exit 1; }

# === Step 5: lightrag_live — graphml + kv_store ===
# Pre-condition: kb-api + omnigraph-*-ingest stopped (Section 0)
mkdir -p /root/.hermes/omonigraph-vault   # 'omonigraph' typo canonical
tar -xzf tier0/lightrag_live-260610.tgz -C /root/.hermes/omonigraph-vault/

# === Step 6: kol_scan.db — 1807 articles + symlink ===
mkdir -p /root/OmniGraph-Vault/data
cp kol_scan-260610.db /root/OmniGraph-Vault/data/kol_scan.db
sqlite3 /root/OmniGraph-Vault/data/kol_scan.db 'PRAGMA integrity_check;' | grep -q '^ok$' || \
  { echo "ABORT: kol_scan.db corrupt"; exit 1; }
ln -sfn /root/OmniGraph-Vault/data/kol_scan.db \
        /root/.hermes/omonigraph-vault/kol_scan.db
readlink /root/.hermes/omonigraph-vault/kol_scan.db   # should print /root/OmniGraph-Vault/data/kol_scan.db

# === Step 7: OmniGraph-Vault repo — fresh clone preferred ===
cd /root && git clone https://github.com/sztimhdd/OmniGraph-Vault.git
cd /root/OmniGraph-Vault
# Match backup HEAD SHA (from tier2 tarball .git/HEAD):
# git checkout <SHA-recorded-at-top-of-this-doc>
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
# Fallback if GitHub unreachable:
#   tar -xzf tier2/omnigraph-repo-260610.tgz -C /root/   # extracts to OmniGraph-Vault/

# === Step 8: CRITICAL — re-apply LightRAG atomic-write patch ===
# Without this: SIGTERM mid-graphml-write truncates live file. Reproduces 2026-06-08 outage.
# `pip install --force-reinstall lightrag` WIPES this — keep .bak guarded.
NX=/root/OmniGraph-Vault/venv/lib/python3.11/site-packages/lightrag/kg/networkx_impl.py
cp "$NX" "${NX}.bak-pre-atomic-$(date +%Y%m%d)"

# Apply patch inline (replace `nx.write_graphml(...)` body in `write_nx_graph` func):
# BEFORE:
#     nx.write_graphml_lxml(self._graph, self._graph_xml_file_path)
# AFTER:
#     tmp_path = self._graph_xml_file_path + ".tmp"
#     nx.write_graphml_lxml(self._graph, tmp_path)
#     os.replace(tmp_path, self._graph_xml_file_path)
python3 -c "
import re, pathlib
p = pathlib.Path('$NX')
s = p.read_text()
old = 'nx.write_graphml_lxml(self._graph, self._graph_xml_file_path)'
new = '''tmp_path = self._graph_xml_file_path + \".tmp\"
        nx.write_graphml_lxml(self._graph, tmp_path)
        import os; os.replace(tmp_path, self._graph_xml_file_path)'''
assert old in s, 'PATCH FAIL: target line not found — inspect manually'
p.write_text(s.replace(old, new))
print('PATCH OK')
"
python3 -c "import lightrag; print('lightrag', lightrag.__version__)"   # expect 1.4.15

# === Step 9: images + aux ===
tar -xzf tier2/images-260610.tgz -C /
tar -xzf tier2/omnigraph-aux-260610.tgz -C /

# === Step 10: enable services + verify ===
systemctl daemon-reload
systemctl enable --now kb-api.service                       # port 8000
systemctl enable --now caddy.service                         # :80 reverse-proxy
systemctl enable --now omnigraph-daily-ingest.timer
systemctl enable --now omnigraph-evening-ingest.timer
systemctl enable --now qdrant-snapshot.timer
# DO NOT enable omnigraph-kol-scan.timer — known-failed pre-backup (WeChat session stale)

# Watch for 5 min, expect zero errors:
journalctl -u kb-api -n 20 -f &
JOURNAL_PID=$!; sleep 300; kill $JOURNAL_PID
# Then run Section 10 verify checks (a)-(f).
```

---

## 4. SaaS sub-restore (only if vitaclaw planb-local-m1 needed)

```bash
mkdir -p /opt/vitaclaw
tar -xzf tier0_7/vitaclaw-planb-deploy-260610.tgz -C /opt/vitaclaw/   # canonical git first
tar -xzf tier0_7/planb-local-m1-260610.tgz       -C /opt/vitaclaw/    # live tree second
tar -xzf tier0_7/vitaclaw-extras-260610.tgz      -C /opt/vitaclaw/    # deploy artifacts
tar -xzf tier0_7/saas-secrets-260610.tgz         -C /                 # 4 .env files
chmod 600 /opt/vitaclaw/planb-local-m1/.env* /opt/vitaclaw/planb-local-m1/tenants/tenantB/.env*
```

**Caveats**:
- Compose orchestration **partial** — only `compose/conversation-store.yml` + `compose/delivery.yml` captured. Other 18 service launchers source unknown — see Section 8 unknowns.
- Runtime data **NOT included** — `tenantB` postgres + 7 docker volumes + 11 custom images. **Must rebuild OR re-pull** custom images from registry (hostname TBD — ask user; likely Aliyun ACR or Docker Hub private).
- Postgres `tenantB` init: NOT covered here. Source schema lives in `vitaclaw-planb-deploy/admin-dashboard/migrations/` — manual run after `docker compose up postgres`.
- Boot order: `docker compose -f compose/conversation-store.yml up -d` first, then `compose/delivery.yml`, then per-tenant launchers. **No master `docker compose up`** found in source.

---

## 5. Vitaclaw 主网站 sub-restore

```bash
mkdir -p /opt/vitaclaw/control-plane
tar -xzf tier0_6/vitaclaw-site-src-260610.tgz -C /opt/vitaclaw/control-plane/
chown -R vitaclaw:vitaclaw /opt/vitaclaw/control-plane/vitaclaw-site
cd /opt/vitaclaw/control-plane/vitaclaw-site
# Confirm node version match BEFORE npm ci:
node -v && cat package.json | jq -r '.engines.node // "unspecified"'
sudo -u vitaclaw npm ci
sudo -u vitaclaw npm run build   # 生成 dist/
systemctl enable --now vitaclaw-site.service   # port 3200
# Caddy serves dist/ at :80 + reverse-proxy /api/* → 127.0.0.1:3200 (per Caddyfile)
```

**Resume from clean canonical** (drop aliyun-backup branch edits):
```bash
cd /opt/vitaclaw/control-plane/vitaclaw-site
git stash && git checkout main && git pull origin main
```

---

## 6a. Pitfalls — pre-restore

| Pitfall | Mitigation |
|---------|-----------|
| Disk space on target | `df -h /` ≥ 40GB free. Section 0 aborts if not. |
| 0 swap on target | `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`. Graphml load + ainsert 会 spike RSS. |
| Wrong tz | `timedatectl set-timezone Asia/Shanghai`. systemd `OnCalendar=*-*-* 03:00:00` interprets in system tz — UTC default → cron fires 8h early. |
| Qdrant container already running on target | Section 0 stops + removes. **DO NOT extract qdrant tarball over running container** — file lock corruption silent. |
| Existing `/var/lib/qdrant/*` on target | Section 0 wipes. Mixing old + new collection state = silent ghost data. |
| kb-api / omnigraph-ingest running on target | Section 0 stops. Mid-write graphml during extract = same corruption as 2026-06-08 outage. |
| Manifest md5 not verified | Section 0 aborts. Tarball corruption mid-network-transfer is real. |
| Docker registry unreachable for `qdrant/qdrant:v1.11.0` | Save image offline on source: `docker save qdrant/qdrant:v1.11.0 > qdrant-img.tar`. Load on target: `docker load < qdrant-img.tar`. (NOT in this backup — agent ask user.) |
| Python ≠ 3.11 on target | LightRAG 1.4.15 pin verified on 3.11. Step 1 aborts if absent. |

## 6b. Pitfalls — post-restore

| Pitfall | Mitigation |
|---------|-----------|
| LightRAG atomic-write patch wiped by `pip install --force-reinstall lightrag` | Step 8 saves `.bak-pre-atomic-YYYYMMDD`. Re-apply on every venv rebuild. |
| systemd schedule overlap → mid-graphml-write SIGTERM | sysconf includes `daily-ingest` `RuntimeMaxSec=10800` (3h) + `Conflicts=evening-ingest`. Don't disable. |
| WeChat session stale | `WEIXIN_TOKEN` in `.env` 几天 expire. Refresh via Hermes `wechat-cdp-credential-refresh` skill → 2-hop scp. **Do NOT enable `omnigraph-kol-scan.timer`** until refreshed. |
| FTS5 search returns 0 despite indexed rows | Restart `kb-api`: stale FTS5 connection cached over uptime (memory: kb-api restart fixes search endpoint). |
| Vertex pin IP `142.250.73.106` stale | GFE rolling. `dig us-central1-aiplatform.googleapis.com +short`, update `/etc/hosts` if SA token refresh times out. |
| `DEEPSEEK_API_KEY` missing on Vertex-only deploys | `lib/__init__.py` eagerly imports DeepSeek client → ImportError. Set `DEEPSEEK_API_KEY=dummy` in `.env`. |

---

## 7. DO NOT block (绝对禁止)

- ❌ **DO NOT** rename `omonigraph-vault` → `omnigraph-vault`. Typo is canonical. Path 全部 silent break.
- ❌ **DO NOT** rename Qdrant collection suffix `_gemini_embedding_2_3072d`. LightRAG 自动加, hybrid retrieve 0 sources.
- ❌ **DO NOT** extract `qdrant-260610.tgz` 在 docker container 还跑. File lock corruption silent.
- ❌ **DO NOT** extract `lightrag_live-260610.tgz` 在 kb-api / omnigraph-*-ingest 还跑. Mid-write corruption.
- ❌ **DO NOT** `pip install --force-reinstall lightrag` 之后忘记重打 atomic-write patch. 下一次 SIGTERM = graphml 截断.
- ❌ **DO NOT** `systemctl enable --now omnigraph-daily-ingest.timer` 之前没验证 Step 8 patch. First cron tick 可能 non-atomic write.
- ❌ **DO NOT** `systemctl enable omnigraph-kol-scan.timer` 之前没刷新 WeChat session. 已知 fail.
- ❌ **DO NOT** `docker run qdrant` 不带 `--restart=unless-stopped`. 6/7 outage 35h Qdrant down 因为没 restart policy.
- ❌ **DO NOT** install `nginx` — Caddy 跑 :80, conflict.
- ❌ **DO NOT** skip md5 verify. Tarball 中途坏掉 extract 出来 worse than nothing.

---

## 8. Decision unknowns

| Unknown | Resolution path |
|---------|----------------|
| 5 dead tenants (`viaproxy`, `finalfinal`, `debug2`, `cacheclear`, `bugfixtest`) excluded | Probably unrecoverable past their (untracked) live-tree state. `vitaclaw-planb-deploy` canonical 仅 `tenantA` template. Ask user via console if business-critical. |
| Compose master orchestration for full SaaS stack | Only 2 of 20 service compose files captured. Other 18 may live in separate ops repo not on this disk. **Action**: `grep -rln 'docker compose' /opt/vitaclaw/planb-local-m1/scripts/` post-extract; 若空 ask user via Hermes operator channel for ops repo URL. |
| `vdb_archive_*.json` future status | Load-bearing as Hermes RO fallback **until 2026-06-22** unlock. After unlock 可 drop. PLAN doc in `omnigraph-aux-260610.tgz`. |
| Qdrant exact docker image tag | NOT preserved in backup. Default `v1.11.0`. Confirm via `grep -r '"version"' /var/lib/qdrant/storage/collections/*/config.json` post-extract. If mismatch, ask user. |
| `vitaclaw-planb-images.tar.gz` registry source | NOT captured. Ask user for registry hostname (likely Aliyun ACR `registry.cn-shanghai.aliyuncs.com/...` or private Docker Hub). |
| Rollback if Section 10 verify fails | (a) graphml=0 nodes → re-extract `tier0/lightrag_live-260610.tgz` after `rm -rf /root/.hermes/omonigraph-vault/lightrag_storage/`. (b) Qdrant 0 collections → re-extract after `docker stop qdrant && rm -rf /var/lib/qdrant/*`. (c) FTS=0 → restart kb-api 3x; if still 0, re-extract sqlite + verify integrity_check. (d) hybrid sources=0 → check graphml + Qdrant points first; if both ok, kb-api stale connection. (e) all fail → restore from prior backup `aliyun-backup-260605/` if exists. |

---

## 9. Source repos

| Project | GitHub | Branch at backup | State |
|---------|--------|------------------|-------|
| OmniGraph-Vault | `github.com/sztimhdd/OmniGraph-Vault.git` | `main` | 4 commits behind origin + 3 untracked. **Prefer fresh clone + `git checkout <SHA-from-backup>`**. |
| vitaclaw-site | `github.com/sztimhdd/vitaclaw-site.git` | `aliyun-backup` | 3 uncommitted `.tsx` |
| vitaclaw-planb (dir name `vitaclaw-planb-deploy`) | `github.com/sztimhdd/vitaclaw-planb-local-m1.git` | `main` | clean. **Repo name ≠ dir name**. |
| geekclaw upstream | `github.com/geekclaw-dot/geekclaw.git` | `main` | clean (vendored in `planb-local-m1/upstream/`) |
| geekskill upstream | `github.com/geekclaw-dot/geekskill.git` | `main` | clean (vendored in `planb-local-m1/upstream/`) |

---

## 10. Verify (success criteria)

All 6 must PASS before declaring restore done.

- [ ] **(a) sqlite article count = 1807**
  ```bash
  sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT COUNT(*) FROM articles;"
  ```

- [ ] **(b) graphml nodes=30558 edges=44030**
  ```bash
  python3 -c "import networkx as nx; g=nx.read_graphml('/root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml'); print(f'nodes={g.number_of_nodes()} edges={g.number_of_edges()}')"
  ```

- [ ] **(c) Qdrant 3 collections, points match**
  ```bash
  for c in chunks entities relationships; do
    curl -sf "http://localhost:6333/collections/${c}_gemini_embedding_2_3072d" \
      | jq -r '"\(.result.config.params.vectors.size)d \(.result.points_count) pts"'
  done
  # expect: 3072d 3665 pts / 3072d 57242 pts / 3072d 79394 pts
  ```

- [ ] **(d) FTS search returns hits**
  ```bash
  curl -sf "http://localhost/kb/api/search?q=AI&mode=fts" | jq '.total'
  # expect >0. If 0: systemctl restart kb-api && retry (memory: stale FTS5 connection)
  ```

- [ ] **(e) hybrid synthesize returns ≥3 sources**
  ```bash
  curl -sf -X POST "http://localhost/kb/api/synthesize" \
    -H 'Content-Type: application/json' \
    -d '{"query":"What are recent trends in AI agents?","mode":"hybrid"}' \
    | jq '.sources | length'
  ```

- [ ] **(f) LightRAG version pin matches**
  ```bash
  /root/OmniGraph-Vault/venv/bin/python -c "import lightrag; print(lightrag.__version__)"
  # expect 1.4.15
  ```

- [ ] **(g) journalctl clean for 5 min**
  ```bash
  journalctl -u kb-api --since "5 min ago" | grep -iE 'error|traceback' | wc -l
  # expect 0
  ```

**Optional resume-state tracking**: maintain `/restore/restore-state.json` updated after each step:
```json
{"step_2_sysconf":"done","step_4_qdrant":"done","step_5_lightrag":"done","step_8_atomic_patch":"done","verify_a":true,"verify_b":true,"verify_c":true,"verify_d":true,"verify_e":true,"verify_f":true,"verify_g":true}
```
Interrupted restore → resume from first incomplete step instead of restart.

---

**End of INVENTORY.md** — pair with `manifest-260610.md5`. Generated 2026-06-11 for restore agent.