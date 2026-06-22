---
quick_id: 260610-eoy
slug: 260610-aliyun-backup-audit
date: 2026-06-10
status: closed
mode: read-only audit; 5 deliverables; 0 mutations
---

# 260610-eoy — Aliyun ECS Backup Audit (SUMMARY)

## Goal

ECS host expiring; user has snapshot but unsure of new ACK migration smoothness. Need pre-cutover read-only inventory + actionable backup + restore plan.

## What was done

100% read-only SSH `aliyun-vitaclaw`. Scanned disk, projects, secrets, systemd, docker, Caddy, Qdrant, sqlite. Wrote 5 deliverables (NO commands run on prod, NO transfers initiated).

## Deliverables

| File | Purpose |
|---|---|
| `BACKUP_INVENTORY.md` | Project × file × size × tier (MUST/SHOULD/SKIP) × difficulty 1-5 |
| `BACKUP_PLAN.md` | Pass 1 + Pass 2 + Pass 3 sequenced commands (review first; user triggers) |
| `RESTORE_RUNBOOK.md` | 11-step new-host bring-up: filesystem → secrets → Qdrant → vitaclaw → kb-api → smoke → cron → DNS |
| `SECRETS_INVENTORY.md` | Paths + key NAMES only (no values); verification checklist |
| `UNKNOWNS.md` | 12 items requiring user decision before BACKUP_PLAN runs |

## Key findings

- **Disk:** 82G/99G (88%). User-data ~14-17G; rest is docker cruft + system + /tmp waste.
- **Total backup footprint:** ~11G live MUST + ~2G SHOULD = **~7-8G compressed**. Fits on corp laptop SSD.
- **Pre-flight reclaim available:** docker build cache 12.58G + /tmp old tarballs ~14G = up to 26G freeable on Aliyun BEFORE backup → snapshot smaller too.
- **Production data:**
  - `kol_scan.db`: 1807 articles + 2200 RSS + 14 tables (63M)
  - LightRAG graphml: 34M live (atomic-write patch in venv must be re-applied on restore)
  - Qdrant: 1.9G (3 collections, all `_gemini_embedding_2_3072d`-suffixed)
  - vitaclaw tenantB: 2.2G app data + 94M Postgres (live cluster) + 5.9G shared docker volumes
  - Custom docker images NOT in registry: ~5G across 11 images (must `docker save`)
- **Critical hot-fixes captured:** 4 systemd `override.conf` (RuntimeMaxSec=10800, TimeoutStopSec=300, KB_SYNTHESIZE_TIMEOUT=240, OMNIGRAPH_VECTOR_STORAGE=qdrant) — without these, daily-ingest hangs and kb-api OOM-kills.
- **Vertex AI /etc/hosts pin:** `142.250.73.106 → aiplatform/oauth2/us-central1.googleapis.com` — captured for restore.

## Surprises surfaced

1. `/tmp` = 8.1G of phase tarballs (lr_storage_arx2.tgz, lightrag_storage_aim2*, vitaclaw-all-images, orchestrator*, etc) — pure waste.
2. 5 dead tenant dirs under planb-local-m1 (~8G, all containers Exited 3d ago) — UNKNOWN if needed.
3. `vdb_archive_*.json` = 1.7G — UNKNOWN if still load-bearing post-Qdrant migration.
4. `docker system df` reports 12.58G reclaimable build cache.
5. OmniGraph repo on Aliyun is **4 commits behind origin/main** + 3 untracked items — git source-of-truth question.
6. `compose/` dir has only 2 yml files but `docker ps` shows 20 containers — UNKNOWN where the master compose orchestration lives.
7. `omnigraph-kol-scan.service` is `failed` (likely WeChat session expiry).
8. `kol_scan.db` lives at `/root/OmniGraph-Vault/data/`, NOT in `~/.hermes/` (the latter has a symlink) — backup target is the real path.

## User decisions required

12 items in `UNKNOWNS.md`. The 5 critical ones:

1. Tenant cleanup: skip 5 dead tenant dirs? (saves 8G)
2. VDB archive: still needed post-Qdrant? (saves 1.7G if dropped)
3. Repo source: GitHub `origin/main` or live Aliyun working tree?
4. Compose orchestration master location?
5. Days until ECS expires (timeline gating)?

## Constraints honored

- ✅ 100% read-only SSH (df / du / ls / cat / stat / sqlite3 read-only / docker inspect)
- ✅ NO files written to ECS
- ✅ NO secrets values echoed (only paths + sizes + key NAMES)
- ✅ NOT touched: systemd / docker / Caddy / Hermes (RO until 06-22)
- ✅ NO backup commands actually run (plan only)
- ✅ Deliverables under `.planning/quick/260610-eoy-*/`
- ✅ ISSUES.md NOT modified (this is deliverable, not bug)

## Atomic commit

`docs(quick-260610-eoy): aliyun ECS backup audit — 5 deliverables, read-only`

## Next steps for user

1. Read `UNKNOWNS.md`, answer the 5 critical questions.
2. Read `BACKUP_PLAN.md` Pass 1 commands; review each block; trigger when ready.
3. After Pass 1+2 complete, verify with `BACKUP_PLAN.md` Pass 3.
4. When new ACK environment ready, follow `RESTORE_RUNBOOK.md`.
