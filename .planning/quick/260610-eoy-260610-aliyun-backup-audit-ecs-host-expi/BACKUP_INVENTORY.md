# 260610-eoy — Aliyun ECS Backup Inventory

**Audit date:** 2026-06-10
**Host:** aliyun-vitaclaw (101.133.154.49, /dev/vda3 99G, 82G used = 88%)
**Audit type:** read-only SSH; nothing mutated.

## Disk usage rollup (top-level)

| Path | Size | Notes |
|---|---|---|
| `/var` | 49G | 24G containerd + 21G docker + 1.9G qdrant |
| `/opt` | 17G | 16G vitaclaw (planb-local-m1 11G + control-plane 4.3G) |
| `/root` | 11G | 6.2G `.hermes/` + 2.8G OmniGraph-Vault (2.3G venvs) + 856M old tar archives |
| `/tmp` | 8.1G | **PURE WASTE** — old tarballs from May/June |
| `/usr` | 4.5G | system; SKIP |
| `/swapfile` | 4.1G | system; SKIP |
| `/snap` | 1.2G | system; SKIP |
| `/boot` | 244M | system; SKIP |

**Total user-data footprint (MUST + SHOULD):** ~14-17G actual project content
(rest is regenerable / docker cache / system / cruft)

---

## Tier legend

| Tier | Meaning | Default action |
|---|---|---|
| 🔴 **MUST** | Not reconstructible — secrets / state / production data | Backup |
| 🟡 **SHOULD** | Reconstructible but expensive (LLM ingest, scrape, paid quota) | Backup |
| ⚪ **SKIP** | Fully regenerable — venv / node_modules / build cache / registry images | Drop |

---

## Project 1: omnigraph (OmniGraph-Vault)

### 🔴 MUST (hard requirements — total ~3.0G + tiny configs)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/root/.hermes/.env` | 2.7K | 5/5 | Apify + Gemini + DeepSeek + Vertex SA path + WeChat tokens. Re-acquiring some keys = days. |
| `/root/.hermes/gcp-paid-sa.json` | 2.4K | 4/5 | Vertex SA JWT key. Rotate within 90d → can re-issue, but lose service if expired |
| `/root/.hermes/auth.json` + `config.yaml` | 1.3K | 3/5 | Hermes gateway state |
| `/root/.ssh/id_ed25519` (+pub +authorized_keys +known_hosts) | 411-978B | 2/5 | Cross-host SSH (Hermes auth + git deploy) |
| `/root/OmniGraph-Vault/data/kol_scan.db` | 63M | **5/5** | Production SSG DB. **1807 articles + 2200 RSS + 14 tables** (articles, classifications, ingestions, articles_fts, rss_articles, etc). Re-scan = WeChat throttle 50/batch + cooldown × weeks. |
| `/root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml` | 34M | **5/5** | LightRAG knowledge graph. Re-build = full re-ingest of 1807 articles via paid LLM. NOTE: atomic-write patch in venv — see RESTORE_RUNBOOK |
| `/var/lib/qdrant/collections/lightrag_vdb_entities_gemini_embedding_2_3072d/` | 767M | 4/5 | Qdrant entities collection (3072-d Vertex Gemini-2 embeddings) |
| `/var/lib/qdrant/collections/lightrag_vdb_relationships_*` | 1010M | 4/5 | Relationships collection |
| `/var/lib/qdrant/collections/lightrag_vdb_chunks_*` | 111M | 4/5 | Chunks collection |
| `/var/lib/qdrant/aliases/`, `raft_state.json` | <8K | 2/5 | Qdrant cluster metadata |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_full_docs.json` | 11M | 4/5 | Full doc bodies cache (latest only — drop dated .bak rotation) |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_text_chunks.json` | 14M | 4/5 | Chunk store |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_relation_chunks.json` | 17M | 4/5 | Relation→chunk index |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_entity_chunks.json` | 11M | 4/5 | Entity→chunk index |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_llm_response_cache.json` | 29M | 3/5 | LLM cache (regenerable but saves quota on re-query) |
| `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json` | 65M | 3/5 | NetworkX-side chunks vector store (dual w/ Qdrant) |
| `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json` | 833M | 3/5 | Dual-stored in Qdrant. Decide: keep both for safety, or drop in favor of Qdrant |
| `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_archive_*.json` | 1.7G | 3/5 | Archive copies — verify if still load-bearing post-Qdrant migration |
| `/root/.hermes/omonigraph-vault/canonical_map.json` | <4K | 3/5 | Entity name canonicalization |
| `/var/www/kb/` | 74M | 3/5 | SSG output (rebuildable from kol_scan.db via daily_rebuild.sh, but quicker to copy) |
| `/etc/caddy/Caddyfile` | ~1.2K | 5/5 | Reverse proxy + KB site routing rules |
| `/etc/systemd/system/omnigraph-*.{service,timer}` (29 units) | <40K | 5/5 | All omnigraph cron via timers (daily ingest, kol-scan, classify, enrich, rss, translate, vertex-probe, etc) |
| `/etc/systemd/system/omnigraph-*.service.d/override.conf` (4 files) | <8K | **5/5** | Hot-fix overrides — RuntimeMaxSec=10800, TimeoutStopSec=300, OMNIGRAPH_VECTOR_STORAGE=qdrant. **Without these the daily-ingest hangs (ISSUES #45)** |
| `/etc/systemd/system/kb-api.service` + `.d/override.conf` | <4K | 5/5 | KB FastAPI unit (port 8766) + 12G memory cap + KB_DEFAULT_LANG=zh-CN + qdrant URL |
| `/etc/hosts` | <1K | 5/5 | Vertex pin: `142.250.73.106 → aiplatform/oauth2/us-central1.googleapis.com` |
| `crontab -l` | 1 line | 4/5 | `0 12 * * * /root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh >> /var/log/kb-rebuild.log 2>&1` |

### 🟡 SHOULD (expensive to reconstruct — total ~2.0G)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/root/.hermes/omonigraph-vault/images/` | 1.7G | 4/5 | 465 article-image dirs from SiliconFlow vision pipeline. Regenerable but ~¥0.0013/img × N images. |
| `/root/.hermes/omonigraph-vault/checkpoints/` | 45M | 3/5 | 325 in-flight resume markers (atomic stage flags 01_scrape → 05_ingest) |
| `/root/.hermes/omonigraph-vault/entity_buffer/` | 1.1M | 4/5 | 273 raw LLM entity extracts (per-article hash JSON) |
| `/root/.hermes/omonigraph-vault/query_history.jsonl` | 372K | 2/5 | HYG-03 past-query memory |
| `/root/.hermes/omonigraph-vault/synthesis_archive/` | 32K | 3/5 | Past synthesis outputs (analysis history) |
| `/root/OmniGraph-Vault/` (excl venv*, __pycache__, .bak.* tarballs) | ~500M | 1/5 | Code repo. **Has uncommitted: kol_config.py.bak-260610, scripts/qdrant_reingest_252.sh.bak, venv-aim1/.** Currently 4 commits behind origin. Safer to back up `data/` separately + git pull on new host. |
| `/root/OmniGraph-Vault/data/` (excl venv) | 269M | 4/5 | Includes kol_scan.db (63M, MUST) + 9 historical .bak.* (190M, can drop oldest) + a few coldstart_*.json |
| `/root/OmniGraph-Vault/kb/` | 76M | 1/5 | Source code (in git). SKIP if git pull on new host works. |

### ⚪ SKIP (regenerable / cruft)

| Path | Size | Why skip |
|---|---|---|
| `/root/OmniGraph-Vault/venv` | 1.1G | regenerate via `pip install -r requirements.txt` |
| `/root/OmniGraph-Vault/venv-aim1` | 1.2G | regenerate (also: untracked, possibly orphan) |
| `/root/OmniGraph-Vault/__pycache__` | 1M | bytecode |
| `/root/.hermes/omonigraph-vault/lightrag_storage.aliyun-pre-aim2-bak-20260523T231949Z/` | 752M | pre-aim2 frozen backup (snapshot covers) |
| `/root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml.corrupt-20260607-0840` | 40M | corruption forensic (postmortem complete, ISSUES #43 RESOLVED) |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_full_docs.json.bak-260606..260610` | 5×11M=55M | daily rotation; keep latest live, drop dated copies |
| `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json.{truncated-bak,repaired-bak}` | 2×215M=430M | forensic |
| `/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_llm_response_cache.json.bak-pre-arx1-cachebust` | 105M | old cache pre-rebuild |
| `/root/.hermes/omonigraph-vault/spider.db` (0B), `kol_scan.db.empty-bak-260528` (0B) | 0B | empty placeholder |
| `/root/OmniGraph-Vault/data/kol_scan.db.bak-*` (8 historical) | 190M | only most-recent .bak worth keeping (already MUST'd current live DB) |
| `/root/OmniGraph-Vault.tar.gz` (May 8) | 594M | superseded by snapshot |
| `/root/omnigraph-runtime-min.tar.gz` (May 8) | 237M | superseded |
| `/root/hermes-agent.tar.gz` (May 8) | 26M | superseded |
| `/tmp/lr_storage_arx2.tgz`, `/tmp/lightrag_storage_aim2_*.tar.gz`, `/tmp/lightrag_storage_arx2.tar.gz` | 1.3+1.3+1.2=3.8G | old phase backups |
| `/tmp/vitaclaw-*-images.tar.gz`, `/tmp/orchestrator-*.tar.gz`, etc | ~3G | old phase artifacts |
| `/var/log/journal/` | 761M | journal (rotates; keep last 7d if useful) |
| `/var/cache/apt/` | 151M | regenerable |
| `/var/lib/docker/buildkit/` | 95M | build cache |
| Docker build cache (`docker system df`) | **12.58G reclaimable** | run `docker builder prune -af` after backup |

---

## Project 2: vitaclaw SaaS (planb-local-m1 stack — 20 active containers)

### 🔴 MUST (~7.5G)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/opt/vitaclaw/planb-local-m1/.env` | 311B | 4/5 | Tenant routing config (TENANT_A/B port + qdrant prefix + schema) |
| `/opt/vitaclaw/planb-local-m1/.env.local` | 53B | 4/5 | DEEPSEEK_API_KEY |
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env` | 3.5K | **5/5** | JWT keypair + DB password + service tokens — production tenant secrets |
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed` | 87B | 5/5 | Seed for first-boot |
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/db/` | 94M | **5/5** | Postgres data dir (live PG cluster — pg_wal 49M + base 46M) |
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/data/` | 2.2G | **5/5** | App state — `app/` (1.5G — most likely model/conversation/uploads), `web/` (710M static), `uploads/` (780K), `workspaces/`, `ai-infra/`, `persona-uploads/` |
| Docker volume `vitaclaw-shared_convstore_runtime` | 1.3G | 4/5 | Conversation store runtime data |
| Docker volume `vitaclaw-shared_delivery_runtime` | 1.3G | 4/5 | Delivery service state |
| Docker volume `vitaclaw-shared_inbox_runtime` | 1.3G | 4/5 | Inbox service state |
| Docker volume `vitaclaw-shared_push_runtime` | 1.3G | 4/5 | Push service state |
| Docker volume `vitaclaw-shared_timescaledb_data` | 68M | 4/5 | TimescaleDB metrics/observability |
| Docker volume `vitaclaw-shared_nats_data` | 244K | 4/5 | NATS persistence |
| Docker volume `vc_tb_minio_data` | 184K | 3/5 | MinIO objects (small but referenced — verify) |
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/compose/{conversation-store,delivery}.yml` | <8K | 5/5 | Live compose definitions |
| `/opt/vitaclaw/planb-local-m1/upstream/geekclaw/docker-compose{,.prod}.yml` | <8K | 5/5 | Upstream compose |
| `/opt/vitaclaw/planb-local-m1/dockerfiles/`, `scripts/`, `prompts/`, `charts/`, `templates/` | <300K | 4/5 | Build / deploy / Helm definitions |
| Custom Docker images (locally built, NOT in registry): `vitaclaw-admin-dashboard:latest`, `vc-conversation-store:local`, `vitaclaw-management-service:latest`, `vitaclaw-skill/persona/identity-service:v0.1.0`, `vitaclaw-orchestrator:v0.1.0`, `vitaclaw-ag-ui-server:v0.1.0`, `vitaclaw-tenant-web:v0.1.0`, `vitaclaw-ai-infra-rs:v0.1.0`, `vc-ai-infra-rs:local` | ~5G total | 5/5 | Without source build context, must be saved as `docker save` tarballs |

### 🟡 SHOULD (~150M after pruning bak/uat tenants)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/opt/vitaclaw/planb-local-m1/upstream/` | 105M | 1/5 | Vendored geekclaw upstream code (clone-able from upstream repo if reference docs available) |

### ⚪ SKIP

| Path | Size | Why skip |
|---|---|---|
| `/opt/vitaclaw/planb-local-m1/vitaclaw-local/web-prebuilt/`, `web-src/` | 20+14=34M | regenerable from build |
| Tenants `viaproxy/`, `finalfinal/`, `debug2/`, `cacheclear/`, `bugfixtest/` (all containers Exited 3 days ago) | 5×~1.6G = 8G | orphan/QA tenants — verify with user; default skip |
| `tenants/uat-*` (5 dirs) | ~280M | UAT tenants from old phases |
| `/opt/vitaclaw/vitaclaw-planb-deploy/` | 38M | older deploy snapshot |
| `/opt/vitaclaw/vitaclaw-planb-local-m1/` | 124M | older renamed copy (predates planb-local-m1) |
| `/opt/vitaclaw/vitaclaw-planb-local-m1.bak.20260527063046/`, `.bak.20260527063907/` | 16+28=44M | timestamped backups |
| Registry-pullable images: `postgres:16-alpine`, `oven/bun:1.3.4{,-slim}`, `nats:2.10`, `qdrant/qdrant:v1.11.5`, `timescale/timescaledb:2.17.2-pg16`, `minio/minio:RELEASE.2025-02-07T23-21-09Z`, `nginx:alpine`, `busybox:latest`, `portainer/portainer-ce:latest`, `ghcr.io/kite-org/kite:latest`, `curlimages/curl:latest` | ~5G | re-pull on new env |
| Docker volumes 5e2b... through f08c... (14 anonymous local volumes, ~46M each) | ~650M | likely Postgres ephemeral data from exited containers — verify, default skip |
| Docker `Build Cache` (per `docker system df`) | 12.58G | regenerable |
| Containers Exited 3 days ago (vc_finalfinal-*, vc_viaproxy-*, vc_debug2-*, vc_cacheclear-*, vc_bugfixtest-*, t5-pg, t2-identity-service, test-*, ops-portainer, ops-kite) | — | dead state |
| `/tmp/vitaclaw-*` (1.7G optimize + 691M images.tar.gz + 16M helm.tgz + 8.8M admin-dashboard.tar.gz) | ~2.4G | old build artifacts |
| `/tmp/orchestrator-*` | 1.6G | old |

---

## Project 3: vitaclaw 主网站 (control-plane/vitaclaw-site)

### 🔴 MUST (~427M)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/opt/vitaclaw/control-plane/vitaclaw-site/dist/` | 213M | 3/5 | Production Vite build (currently served by Caddy at `:80/`) |
| `/opt/vitaclaw/control-plane/vitaclaw-site/public/` | 212M | 3/5 | Static assets (likely hero video + images) |
| `/opt/vitaclaw/control-plane/vitaclaw-site/server.js` | <4K | 4/5 | Node API runtime |
| `/opt/vitaclaw/control-plane/vitaclaw-site/package.json` + `package-lock.json` | 152K | 5/5 | Dependency lock |
| `/opt/vitaclaw/control-plane/vitaclaw-site/vite.config.ts`, `tsconfig.json`, `index.html`, `metadata.json` | <16K | 5/5 | Build config |
| `/opt/vitaclaw/control-plane/vitaclaw-site/src/` | 292K | 4/5 | Source (if not in git anywhere — verify) |
| `/opt/vitaclaw/control-plane/vitaclaw-site/server/` | 14M | 4/5 | Backend Node code (verify if in git) |
| `/etc/vitaclaw/vitaclaw-site.env` (+1 .bak) | 83B | 5/5 | DEEPSEEK_API_KEY + NODE_ENV=production + PORT |
| `/etc/systemd/system/vitaclaw-site.service` | <2K | 5/5 | systemd unit (User=vitaclaw, working dir + EnvironmentFile=/etc/vitaclaw/vitaclaw-site.env) |

### 🟡 SHOULD (~200K)

| Path | Size | Difficulty | Notes |
|---|---|---|---|
| `/opt/vitaclaw/control-plane/vitaclaw-site/docs/`, `CLAUDE.md`, `AGENTS.md`, `README.md` | <200K | 1/5 | Reference docs |

### ⚪ SKIP

| Path | Size | Why skip |
|---|---|---|
| `/opt/vitaclaw/control-plane/vitaclaw-site/node_modules/` | 217M | npm reproducible |
| `/opt/vitaclaw/control-plane/vitaclaw-site/backups/` (15 dist.* dirs since 5/13) | 2.6G | dist version history; keep current dist only |
| `/opt/vitaclaw/control-plane/vitaclaw-site/dist.backup.*` (5 timestamped) | ~1.05G | timestamped dist clones |

---

## Cross-project / system

### 🔴 MUST

| Path | Size | Notes |
|---|---|---|
| `/etc/systemd/system/{kb-api,vitaclaw-site,omnigraph-*,qdrant-snapshot}.{service,timer}` | <80K | 30+ units (counted: 29 omnigraph + kb-api + vitaclaw-site + qdrant-snapshot) |
| `/etc/systemd/system/*.service.d/override.conf` (4 files) | <8K | Critical hot-fixes |
| `/etc/caddy/Caddyfile` | ~1.2K | All routing |
| `/etc/hosts` | <1K | Vertex pin |
| `/var/lib/caddy/.config/caddy/autosave.json` | 2.8K | Caddy persisted live config |
| `/var/lib/caddy/.local/share/caddy/instance.uuid`, `last_clean.json` | <1K | Caddy state |
| `/etc/cron.d/` (sysstat, e2scrub_all) + `crontab -l` | <2K | (Only 1 user crontab line — daily kb_rebuild.sh) |
| `/etc/iptables/` or `iptables-save` | varies | Firewall (Docker chains + UFW) — see UNKNOWNS |

### 🟡 SHOULD

| Path | Size | Notes |
|---|---|---|
| `/var/log/journal/` (filtered last 7d) | ~100M selected | Postmortem on new env |

### ⚪ SKIP

| Path | Size | Why skip |
|---|---|---|
| `/var/log/journal/` (full) | 761M | rotates anyway; only keep recent slice |
| `/var/cache/apt/` | 151M | regenerable |
| `/var/lib/snapd/` | 457M | snap reinstalls |
| `/var/lib/docker/buildkit/` | 95M | build cache |
| `/opt/alibabacloud/` | 998M | hbrclient — Aliyun host backup agent (the new ACK host gets its own) |
| `/var/lib/dpkg/`, `/var/lib/apt/`, etc | <500M | system DB |
| `/var/log/syslog*`, `kern.log*`, etc | ~80M | rotating logs |

---

## Surprises / orphans surfaced

1. **`/tmp` = 8.1G of pure waste** — old phase tarballs (lr_storage_arx2.tgz, lightrag_storage_aim2*, vitaclaw-all-images, orchestrator-*, hermes_sync_imgs, hermes-graphml-20260608.xml, etc). Safe to wipe in old environment after backup.
2. **Docker build cache 12.58G reclaimable** — `docker builder prune -af` can reclaim before / instead of backing up.
3. **5 tenant directories under planb-local-m1 with Exited containers** (viaproxy, finalfinal, debug2, cacheclear, bugfixtest) — ~8G of probable QA tenant junk. **User decision needed** (UNKNOWNS).
4. **`omnigraph-kol-scan.service` is `failed`** — known but flagged here.
5. **`/root/OmniGraph-Vault` is 4 commits BEHIND origin AND has uncommitted untracked files** (kol_config.py.bak-260610, scripts/qdrant_reingest_252.sh.bak-pre-collection-suffix, venv-aim1/). Resolve before backup or copy as-is.
6. **`/root/.hermes/omonigraph-vault/kol_scan.db` is symlink** → `/root/OmniGraph-Vault/data/kol_scan.db`. Backup the target, recreate symlink on restore.
7. **`spider.db` 0-byte placeholder** — never written, but referenced by config; safe to leave.
8. **No TLS certs to back up** — Caddyfile is `:80` only. New env can re-issue with Caddy auto-TLS once domain DNS points there (or stay HTTP).
9. **5 daily `kv_store_full_docs.json.bak-260606..260610`** — 55M of redundant rotation. Keep live, drop dated.
10. **3 different `.env` formats across vitaclaw stack** — tenantB has the **real** secrets (3521 bytes); planb-local-m1 root only has tenant routing; .env.local just has DEEPSEEK_API_KEY. Don't assume one .env covers all — back up all paths listed.

---

## Total backup footprint estimate

| Tier | Bytes (approx) |
|---|---|
| MUST — omnigraph code + state | ~3.0 G |
| MUST — vitaclaw SaaS state + custom images | ~7.5 G |
| MUST — vitaclaw site | ~430 M |
| MUST — system configs (systemd / caddy / hosts / ssh) | ~100 K |
| MUST subtotal | **~11 G** |
| SHOULD — omnigraph (images + checkpoints + entity_buffer + repo) | ~2.0 G |
| SHOULD — vitaclaw upstream | ~105 M |
| SHOULD — site docs + journal slice | ~100 M |
| SHOULD subtotal | **~2.2 G** |
| **GRAND TOTAL (compressed est. ~50%)** | **~6.5 G compressed** |

Net transfer: 6.5G fits comfortably on a corp laptop SSD.
