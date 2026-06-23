# Quick Task 260623-g6e: Aliyun Docker+Qdrant ingest restore — SUMMARY

**Completed:** 2026-06-23 ~23:53 CST
**Mode:** --discuss --full (prod-ops recovery; agent = Aliyun operator, Principle #5)
**Outcome:** ✅ 7-day knowledge-graph ingest restart-loop RESOLVED. Full pipeline restored end-to-end.
**Execution model:** ZERO local repo code edits / ZERO git fix-commits. All work was live SSH ops on Aliyun ECS `iZj1imk39yc55iZ` (EIP 47.117.244.253, cn-shanghai) via alias `aliyun-vitaclaw`.

---

## Root Cause (deeper than the original report)

The 6/17 instance rebuild caused **two compounding install-time failures**, not just the one diagnosed:

1. **Docker engine half-install** (the known one): `containerd.io` (official) was installed and `containerd.service` running since 6/18, the official apt repo (`mirrors.aliyun.com/docker-ce`) was configured, but `docker-ce`/`docker-ce-cli` engine packages were never installed. No Docker daemon → the Qdrant vector-DB container never started → every ingest failed at LightRAG `ainsert` with `httpx.ConnectError: [Errno 111] Connection refused`. `omnigraph-daily-ingest` (`Restart=on-failure RestartSec=10min`) burned **354 restarts**.

2. **`/tmp` permission corruption** (newly discovered, was blocking the fix itself): `/tmp` was `drwxr-xr-x` (755) owned by `1000:1000` (an orphaned uid with no passwd entry) instead of canonical `drwxrwxrwt` (1777) `root:root`. `apt-get` drops to the `_apt` sandbox user for repo fetches + `apt-key` temp files, which **cannot write to a non-world-writable /tmp** → `Couldn't create temporary file /tmp/apt.conf.* for passing config to apt-key`. This blocked installing docker-ce at all until `/tmp` was fixed to 1777.

Both are the same class of damage: a botched/incomplete 6/17 rebuild. → motivates the rebuild-checklist hardening ISSUE.

---

## What Was Done (Tasks 1-6; Task 7 skipped by user)

### Task 1 — Stop restart-loop FIRST
- Baseline captured: `NRestarts=354`, `ActiveState=activating`, `SubState=auto-restart`.
- `systemctl stop omnigraph-daily-ingest` → `inactive`/`dead`. Burn halted.
- Window check: CST was 23:17; all ingest timers fire 06-24 (08:00/14:00/20:00) — clear of window, no timer masking needed.

### Task 2 — Install docker-ce engine (clean apt, NO wipe) — with 2 deviations
- **Deviation A (`/tmp` fix):** `apt-get update` failed with `/tmp` temp-file errors. Diagnosed `/tmp` = 755 `1000:1000`. Fixed: `chown root:root /tmp && chmod 1777 /tmp` → apt clean. (Standard, safe, universally-correct perm.)
- **Deviation B (compose-plugin conflict):** `apt-get install docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin` failed — `docker-compose-plugin` collides with already-installed `docker-compose-v2` over `/usr/libexec/docker/cli-plugins/docker-compose` (dpkg overwrite error, whole txn rolled back). Resolved by dropping `docker-compose-plugin` (this task uses `docker run`, not compose; `docker-compose-v2` already provides compose) and running `dpkg --configure -a` to finish the already-unpacked `docker-ce`/`docker-ce-cli`/`docker-buildx-plugin`.
- `systemctl enable --now docker`.
- **Result:** Docker **29.6.0** (Client+Server), `systemctl is-active docker` = active, **enabled**; `containerd` still active (undisturbed); `docker info` → `Server=29.6.0 Runtime=runc Root=/var/lib/docker`. `/var/lib/docker` + `/var/lib/containerd` NOT wiped.

### Task 3 — Qdrant up (auto-started; no manual `docker run` needed)
- **Unexpected (good):** when the daemon started, a pre-existing Qdrant container definition preserved in `/var/lib/docker` (configured 6/18) **auto-started**. Inspect confirmed it already matches/exceeds the required recipe:
  - Image `qdrant/qdrant:**v1.11.5**` (the actual 6/18 tag — newer than the plan's v1.11.0 default guess; correctly matches the on-disk data format, avoiding a forward-version load refusal — INVENTORY.md:350 caveat handled by reality).
  - `RestartPolicy=**unless-stopped**` ✅ (mandatory; memory `qdrant_docker_no_restart_policy_trap`).
  - Mount `/var/lib/qdrant => /qdrant/storage` ✅, Port `127.0.0.1:6333` (localhost-bound).
- No wipe, no reingest. Existing 6/16 data reused (LOCKED decision #2).

### Task 4 — Qdrant health + collections (C_before)
- `/healthz` → `healthz check passed`.
- 3 collections, correct suffix `_gemini_embedding_2_3072d`.
- **C_before point counts:** chunks=**3808**, entities=**58745**, relationships=**81883** (all non-zero; consistent with — and slightly above — the 6/10 INVENTORY backup baseline 3665/57242/79394, confirming live evolved data, no loss).

### Task 5 — Verification ingest + restart-loop gone + timers re-armed (LOCKED #3: this IS the natural drain, `--max-articles 5`, no catch-up batch)
- `systemctl start omnigraph-daily-ingest` (EnvironmentFile → env correct). `reset-failed` cleared the stale 354 counter.
- Journal evidence: Layer-1 classify → Apify scrape SUCCEEDED (`wechat_31314bcec8`) → vision image processing → **Embedding workers initialized** (real Vertex Gemini calls) → **LLM extract workers** → `Chunk N of 14 extracted X Ent + Y Rel` → Qdrant commits.
- **Counts climbed live:** chunks 3808→3823, entities 58745→**58854** (+109), relationships 81883→**82084** (+201).
- **`Connection refused` count over the full run = 0.** (was 100% of runs for 7 days)
- `NRestarts=0`, `SubState=running` (then will go dead/exited) — NOT auto-restart. Loop gone.
- Timers re-armed: daily/afternoon/evening all scheduled (next fires 06-24, CST).

### Task 6 — long_form RAG smoke (graph queryable E2E)
- `POST /api/synthesize {mode:"long_form"}` (kb-api `127.0.0.1:8766`), question "AI Agent 和大模型最近有哪些重要进展?", polled job `395220f12562`.
- **Result:** `status=done`, **`fallback_used=False`** (real KG retrieve, NOT FTS fallback), `confidence=kg`, **`sources=13`**, `md_chars=5131` graph-grounded markdown with inline citations, `error=None`.
- Confirms Qdrant ↔ LightRAG hybrid retrieve ↔ synthesis all wired correctly.

### Task 7 — Disk prune — **SKIPPED per user decision**
- Disk at 84% (79G/99G, 16G free) — sufficient, non-blocking. User chose to skip the `docker system prune -a -f`.
- Filed as ISSUES.md follow-up (containerd ~19G overlayfs orphan layers + 4.5G content reclaim).

---

## Decisions Honored (from CONTEXT.md, all LOCKED)
1. ✅ Docker = clean apt install, NO wipe of `/var/lib/docker` or `/var/lib/containerd` (containerd untouched, still active).
2. ✅ Qdrant = reuse existing 6/16 `/var/lib/qdrant` (auto-started container mounts it; NO wipe, NO reingest).
3. ✅ Backlog 197 = cron natural drain; verification ingest was ONE `omnigraph-daily-ingest` run (`--max-articles 5`), NO big catch-up batch.
4. ✅ Disk prune AFTER verification PASS, gated by checkpoint — user opted to skip.

---

## Evidence Quick-Reference
| Metric | Before | After |
|---|---|---|
| docker daemon | absent (NO_DOCKER_BIN) | 29.6.0 active+enabled |
| Qdrant container | never running | v1.11.5 Up, unless-stopped |
| chunks points | 3808 | 3823 (+) |
| entities points | 58745 | 58854 (+109) |
| relationships points | 81883 | 82084 (+201) |
| `Connection refused` / run | every run (7 days) | 0 |
| NRestarts | 354 (climbing /10min) | 0 (stable) |
| long_form RAG | broken (Qdrant down) | sources=13, fallback=False, confidence=kg |
| /tmp perms | 755 1000:1000 (apt-broken) | 1777 root:root |

---

## Follow-up Issues Surfaced (orchestrator → ISSUES.md)
1. **Instance-rebuild checklist gap** (P1): the 6/17 rebuild shipped without Docker engine AND with a corrupted `/tmp` (755, orphan uid 1000) AND an orphaned uid-1000 ownership. A rebuild checklist must assert: docker-ce installed + daemon active, Qdrant container Up with `--restart=unless-stopped`, `/tmp` = 1777 root:root, no orphaned uid ownership on system dirs.
2. **containerd orphan-layer disk reclaim** (P2): ~19G `/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs` + 4.5G content store from old k8s/containerd usage, outside docker's prune view. Needs a separate careful reclaim task (do NOT hand-rm live runtime dirs).
3. **`docker-compose-plugin` vs `docker-compose-v2` conflict** (P3/Doc): future `apt install docker-compose-plugin` will conflict with the Ubuntu `docker-compose-v2` pkg over `/usr/libexec/docker/cli-plugins/docker-compose`. Pick one. Not needed for OmniGraph (uses `docker run`).
4. **(known, not new)** post-completion asyncio hang on ingest services (memory `ingest_service_post_completion_asyncio_hang`) — ingest may show `active/running` ~50min after the batch coroutine finishes. Did not affect this verification (the landing is what matters). Out of scope.
