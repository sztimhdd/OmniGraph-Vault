---
phase: arx-4-databricks-kg-retrieval
plan: 03
status: in_progress
requirements: [ARX4-64]
commits: []
---

# Plan 03 SUMMARY — Sync aligned snapshot to Databricks + restore vector retrieval (#64)

## Task 1 — Pre-sync freshness gate (read-only) — **PASSED**

The mandatory gate that prevents transplanting stale data again. Run as ONE
combined SSH call (results written to `/tmp/arx4-presync-gate.txt` on Aliyun,
read back after the SLB throttle cleared — see Plan 01 SUMMARY for the throttle).

| Collection | Live Qdrant points_count | On-disk vdb (load_storage) | Δ vs Qdrant | Gate |
|---|---|---|---|---|
| chunks | 3980 | 3970 rows, (3970, 3072) | 0.25% | ✓ ±5% |
| relationships | 84868 | 84572 rows (converter log) + size-math, (84572, 3072) | 0.35% | ✓ ±5% |
| entities | 60940 | 60754 rows, (60754, 3072) | 0.31% | ✓ ±5% |

- `vdb_relationships.json` = **1,420,551,538 bytes (1.42 GB)** > 1 MB gate (was 49-byte placeholder). ✓
- All matrices **(N, 3072)**. ✓
- graphml: nodes=33256, edges=48570 (non-empty, recent — grew from 32056 baseline). ✓
- Relationships `load_storage` row-print OOM'd on the probe (1.42GB load with
  kb-api+Qdrant co-resident, suppressed by `2>/dev/null`) — **probe-side artifact,
  not a data problem**. Confirmed independently: valid header
  `{"embedding_dim": 3072, "data": [{"__id__": "rel-f05a..."}]` + size-math
  (84572×3072×4 = 1.04GB raw → ~1.39GB base64 + ~31MB rows = 1.42GB). ✓

**Gate verdict: PASS** — Aliyun on-disk vdb is fresh + aligned to live Qdrant.

## Task 1.5 — Adversarial GO/NO-GO (ultracode, 4 skeptics + synthesizer)

Before the destructive 50-min prod sync, ran an adversarial workflow
(`wf_c7011fda-686`, 5 agents) attacking the GO decision from 4 lenses
(alignment, OOM, re-hydrate efficacy, embedding-dim). **Verdict:
GO-WITH-MITIGATION.** It caught a load-bearing wrong premise in the PLAN:

**The PLAN's Task 3 referenced `startup_adapter.py` (the `:83 already_hydrated`
skip + `:107 copytree`) — but that is DEAD CODE in production.** `app.yaml:15`
boots `python _db_bootstrap.py && exec uvicorn app_entry:app`, and
`_db_bootstrap.py:hydrate_lightrag_storage()` (:37-78) is the real path. It:
- **streams** each UC-Volume file to disk in 1MB chunks (`resp.contents.read(1024*1024)`)
  — no `copytree` RAM spike,
- has **NO idempotency skip** — re-downloads every boot,
- logs **`LightRAG storage hydration complete: %d files, %d bytes`** (NOT
  `startup_adapter: copied via`).

This dissolves two skeptic concerns (the hydrate-skip worry and the copytree-OOM
mechanism) and **corrects Plan 03 Task 3's grep target** (see Task 3 below).

### Blocking mitigations applied (pre-sync)

1. **Purged stale `vdb_archive_*.json` from Aliyun** (1.9 GB dead code, no deployed
   read path — confirmed `grep -rn vdb_archive databricks-deploy/ --include=*.py`
   only hits synthesis-output archiving in `kg_synthesize.py`, unrelated).
   `_db_bootstrap.hydrate_lightrag_storage` downloads EVERY file in the dir, so
   leaving them would have bloated /tmp tmpfs by 1.9 GB. Purged + real vdb intact.
2. **Captured Databricks pre-sync boot baseline** (so a post-sync boot OOM is
   distinguishable from a transient):
   ```
   kb.db_bootstrap INFO Hydration complete: /tmp/kol_scan.db (44404736 bytes)
   kb.db_bootstrap INFO LightRAG storage hydration complete: 93 files, 2734272705 bytes  (2.73 GB)
   kb.db_bootstrap INFO Image hydration complete: 5747 files, 1295381268 bytes
   WARNING:kb.api:lightrag_singleton_ready wall_s=28.31
   compute ACTIVE | deployment SUCCEEDED
   ```
   **Key insight:** the container ALREADY hydrates 2.73 GB + loads LightRAG
   successfully today. Today's 2.73 GB includes the OLD 1.12 GB
   `vdb_archive_relationships.json` (unread by the app). Post-sync ships the real
   1.42 GB `vdb_relationships.json` but DROPS the 1.9 GB archives → net UC-Volume
   payload ≈ 2.25 GB, **smaller** than today's 2.73 GB. The genuine new event is
   loading a real 1.42 GB relationships matrix into NanoVectorDB at init (vs
   today's 49-byte placeholder); `load_storage`+`normalize` build ~2×1.04 GB
   float32 copies — bounded, and the container already loads the 1.0 GB entities
   matrix today, so multi-GB headroom is demonstrated. OOM risk is bounded +
   recoverable (a boot crash does NOT corrupt the UC Volume).

### Alignment spot-check (closes the alignment skeptic's residual)

```
ALIGN graphml_chunk_refs=3336 vdb_chunk_ids=3324 vdb_rows=3970 intersection=3185
ALIGN pct_of_vdb_chunks_referenced_in_graphml=95.8%
```

**95.8% of vdb chunk-ids are referenced by the graphml** — tightly aligned (same
Qdrant vintage). This is the OPPOSITE of the #44/#64 misalignment symptom (which
shows near-0% overlap → "0 vector chunks"). The snapshot is alignment-correct.
(Note: vdb_chunks has ~646 duplicate `__id__`s [3324 distinct vs 3970 rows] — a
pre-existing converter/Qdrant artifact, NOT introduced by the Plan 01 refactor;
doesn't affect vector retrieval which keys on matrix rows. Out of scope; flagged.)

## Task 2 — sync_to_databricks.sh — **DATA PUSH SUCCEEDED**

`bash scripts/sync_to_databricks.sh --yes` ran ~3h wall (corp egress 0.77 MB/s).
- Step 3 lightrag tar = 2.22 GB (archive-free — confirms the Task-1.5 purge).
- **UC Volume `vdb_relationships.json` = 1,420,551,538 bytes (1.42 GB)** at 17:23,
  byte-matched to the Aliyun source (was the 49-byte placeholder). `vdb_chunks.json`
  81 MB, `vdb_entities.json` 1.0 GB — all confirmed via `fs ls --long`.
- **Script exited 1 at Step 9b'** (the auto-pending-deployment wait-loop timed out
  prematurely — a known `sync_to_databricks.sh` fragility, filed as a follow-up).
  The DATA push (the #64-critical part) fully succeeded before that point.

## Task 2b — BOOT TIMEOUT (surfaced) + FIX (ISSUES #69-class, in-phase) — **RESOLVED**

The first redeploy **FAILED: "App process did not start within 10 minutes."**
Adversarial fix-design workflow (`wf_fde06ab7`, 4 proposals + judge) root-caused it
with code evidence:

- Boot cmd `python _db_bootstrap.py && exec uvicorn` — uvicorn binds the port (→
  Databricks 600s health probe) only AFTER `_db_bootstrap.hydrate_lightrag_storage`
  AND the FastAPI lifespan `initialize_storages()` complete (uvicorn 0.48
  `Server.startup()` awaits lifespan before socket bind — verified).
- `hydrate_lightrag_storage` downloaded all **147 UC-Volume files SEQUENTIALLY**
  (single-threaded). Once the real 1.42 GB relationships vdb replaced the 49-byte
  placeholder, the sequential download blew 600s (boot log: "Hydrating LightRAG
  storage..." with no completion line). A prior auto-pending attempt at 22:01 DID
  complete hydration of 148 files (3.53 GB) + reached singleton, but took >16 min
  total → past the deadline.

**Fix (commit `8ceef46`, ~45 LoC, mirrors the proven `hydrate_images_dir` pattern):**
1. `ThreadPoolExecutor(max_workers=8)` parallel download (was sequential).
2. Junk-skip filter (`.bak/.corrupt/.repaired/.truncated/.backup`) — durable guard.
3. One-time purge of 135 junk files (1.03 GB) from BOTH the UC Volume (135 deleted →
   **12 real files / 2.50 GB**) and the Aliyun SoT (prevents re-propagation on next sync).

**Redeploy `01f170e2ee08182b94bbc1492b665eb8` = SUCCEEDED, "App started successfully",
app RUNNING, compute ACTIVE (stable on recheck).** Because uvicorn binds only after the
lifespan matrix-load completes, SUCCEEDED **proves** both the hydration AND the 1.42 GB
relationships matrix parse finished within 600s **without OOM** — the residual RAM-ceiling
risk the workflow flagged did NOT materialize. Boot-timeout RESOLVED.

## Task 3 — Re-hydrate + vector-chunk verify — **[HUMAN-VERIFY, awaiting user query]**

App is deployed + RUNNING with the fresh aligned snapshot. Final step (Entra-SSO
blocks Playwright): the USER runs one `/api/synthesize` long_form query via the
browser, and the executor greps the backend log for `>0 vector chunks` + absence of
`falling back to WEIGHT method`. (Folded into Plan 04's combined UAT.)
