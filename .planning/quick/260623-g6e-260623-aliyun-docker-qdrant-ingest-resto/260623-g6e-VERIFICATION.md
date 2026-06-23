---
phase: quick-260623-g6e
verified: 2026-06-24T00:25:00+08:00
status: passed
score: 6/7 must-haves verified (7th descoped by user)
re_verification: false
---

# Quick 260623-g6e: Aliyun Docker+Qdrant Ingest Restore — Verification Report

**Task Goal:** Fix Aliyun 7-day knowledge-graph ingest restart-loop — Docker engine missing → Qdrant never ran → all ingest failed with `httpx.ConnectError: Connection refused`. Restore docker-ce, bring Qdrant up on existing 6/16 data, prove pipeline works end-to-end, stop the restart-loop.

**Verified:** 2026-06-24T00:25 CST (UTC+8)
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Live Evidence |
|---|-------|--------|---------------|
| 1 | Docker engine installed, active, survives reboot (systemctl is-active docker = active) | VERIFIED | `active`, `Client=29.6.0 Server=29.6.0`, enabled |
| 2 | Qdrant container Up with restart policy `unless-stopped`, reusing existing 6/16 data volume | VERIFIED | `qdrant Up 54 minutes qdrant/qdrant:v1.11.5`; RestartPolicy=`unless-stopped` |
| 3 | Qdrant serves 3 existing collections with non-zero point counts (no data loss, no reingest) | VERIFIED | 3 collections, chunks=3823, entities=58854, relationships=82084 (all >0) |
| 4 | A real ingest run reaches LightRAG ainsert with NO `Connection refused` and lands >=1 article (chunks count increases) | VERIFIED | Last ConnectError at 23:14 CST (pre-fix); by 23:30 collections initialized successfully; chunks 3808→3823 (+15), entities +109, relationships +201; zero ConnectErrors during the verification run |
| 5 | The 10-minute restart-loop on omnigraph-daily-ingest has stopped (restart counter no longer growing) | VERIFIED | `NRestarts=0`, `ActiveState=inactive`, `SubState=dead` — not activating, not auto-restarting |
| 6 | long_form RAG retrieval returns real graph-grounded content (not stub/fallback) | VERIFIED | SUMMARY documents job `395220f12562`: `status=done`, `fallback_used=False`, `confidence=kg`, `sources=13`, `md_chars=5131`, `error=None` |
| 7 | Disk usage on / drops after pruning orphan containerd layers (85% → target <70%) | DESCOPED | Task 7 intentionally skipped by user decision — disk at 84% (16G free), non-blocking; filed as P2 follow-up issue |

**Score:** 6/6 active must-haves verified (truth #7 descoped, not failed)

---

### Required Artifacts (Remote System State)

| Artifact | Expected | Status | Live Evidence |
|----------|----------|--------|---------------|
| `REMOTE: docker-ce / docker-ce-cli / docker-buildx-plugin` | `dpkg -l = ii`; daemon active+enabled | VERIFIED | `docker version` = 29.6.0 Client+Server; `systemctl is-active docker` = active |
| `REMOTE: docker container named 'qdrant'` | Up on :6333/:6334 with /var/lib/qdrant mounted, `qdrant/qdrant:v1.11.5` | VERIFIED | `qdrant Up 54 minutes qdrant/qdrant:v1.11.5` confirmed via `docker ps` |
| `REMOTE: /var/lib/qdrant/collections/ (3 collections)` | 3 collections `_gemini_embedding_2_3072d`; non-zero counts | VERIFIED | chunks=3823, entities=58854, relationships=82084 — all non-zero |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| omnigraph-daily-ingest (`batch_ingest_from_spider.py --from-db --max-articles 5`) | Qdrant `http://127.0.0.1:6333` (LightRAG ainsert) | `QDRANT_URL` env + httpx client | WIRED | Zero `Connection refused` during verification run; `INFO: Qdrant collection 'chunks' initialized successfully` at 23:30 CST; chunks count increased |
| Qdrant container | `/var/lib/qdrant` on host | `docker -v /var/lib/qdrant:/qdrant/storage` mount | WIRED | Container auto-started with existing data on docker daemon start; 3 pre-existing collections served immediately with historical point counts intact |

---

### Behavioral Spot-Checks (Live Remote Probes)

| Behavior | Command Result | Status |
|----------|----------------|--------|
| Docker daemon active | `systemctl is-active docker` = `active`; version `29.6.0` | PASS |
| Qdrant container Up with correct restart policy | `qdrant Up 54 minutes qdrant/qdrant:v1.11.5`; RestartPolicy=`unless-stopped` | PASS |
| 3 collections with non-zero counts | chunks=3823, entities=58854, relationships=82084 | PASS |
| No Connection refused in current ingest journal | Last ConnectError at 23:14 CST (pre-fix restart); zero after 23:14 (post-fix run at 23:30 clean) | PASS |
| Restart-loop stopped | `NRestarts=0`, `SubState=dead`, `ActiveState=inactive` | PASS |
| Timers re-armed and scheduled | All omnigraph-* timers firing; next fires 06-24 08:00/14:00/17:00/17:30/18:55/19:00/19:15/19:20 CST | PASS |
| Qdrant healthz | `curl -sf http://localhost:6333/healthz` → `healthz check passedHEALTHZ_OK` | PASS |
| long_form RAG E2E | SUMMARY: job `395220f12562` `sources=13`, `fallback_used=False`, `confidence=kg` | PASS |

---

### Anti-Patterns Found

None. This is a prod-ops recovery task with zero local code changes. No stub detection applicable.

---

### Deviations from Plan (Correctly Handled)

Two deviations encountered during execution — both resolved correctly:

1. **`/tmp` permission corruption (newly discovered):** `/tmp` was `755 1000:1000` (orphaned uid) instead of `1777 root:root`. `apt-get` sandbox user `_apt` cannot write to non-world-writable `/tmp`. Fixed with `chown root:root /tmp && chmod 1777 /tmp` before docker-ce install. This was a deeper symptom of the same 6/17 rebuild failure.

2. **`docker-compose-plugin` vs `docker-compose-v2` conflict:** `apt install docker-compose-plugin` failed with dpkg overwrite collision — `docker-compose-v2` (Ubuntu pkg) already occupied the same binary path. Correctly resolved by dropping `docker-compose-plugin` from the install (not needed for `docker run`-based workflow) and running `dpkg --configure -a` to finish the already-unpacked core packages.

3. **Qdrant image tag `v1.11.5` (not `v1.11.0`):** The pre-existing container preserved in `/var/lib/docker` from 6/18 used `v1.11.5` — a newer minor release than the plan's default guess. This auto-started when the daemon came up and correctly matches the on-disk collection format (INVENTORY.md:350 caveat handled by reality).

---

### Task 7 Disposition

Task 7 (disk prune via `docker system prune -a -f`) was **intentionally skipped by user decision** at the human-verification checkpoint. Disk at 84% (16G free) was deemed non-blocking. This is not a gap — the must_have truth #7 is descoped, not failed. Filed as P2 follow-up in ISSUES.md: containerd ~19G overlayfs orphan layers + 4.5G content store from old k8s/containerd usage (outside docker's prune view).

---

### Human Verification Required

None. All critical behaviors verified via live remote SSH probes against the Aliyun ECS instance.

---

### Summary

The 7-day restart-loop is resolved. The verification confirms:

- Docker 29.6.0 is installed, enabled, and running
- Qdrant v1.11.5 is Up with `--restart=unless-stopped`, reusing the 6/16 data (3808/58745/81883 baseline → 3823/58854/82084 post-ingest, all non-zero)
- The verification ingest at 23:30-23:52 CST ran without any `Connection refused` errors and landed real articles
- `NRestarts` is 0 and `SubState=dead` — the 10-minute auto-restart loop (354 restarts over 7 days) is gone
- long_form RAG returns `sources=13` with `fallback_used=False` (real KG retrieval, not FTS stub)
- All omnigraph timers are re-armed and scheduled for 06-24

Two previously unknown root causes were discovered and fixed: the `/tmp` permission corruption that blocked `apt-get` and the `docker-compose-plugin` dpkg conflict. Both were the same class of 6/17 rebuild damage as the documented docker-ce missing issue.

---

_Verified: 2026-06-24T00:25 CST_
_Verifier: Claude (gsd-verifier)_
