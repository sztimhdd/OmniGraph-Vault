# Phase arx-4: Databricks KG-Retrieval Quality Restoration — Context

**Gathered:** 2026-06-24
**Status:** Ready for planning
**Source:** plan-phase triage (RESEARCH.md) + user fix-path decisions (2 AskUserQuestion gates)
**Milestone:** Agentic-RAG-v1.1 (parallel-track; suffix files — `gsd-tools init` returns `phase_found=false`, gates hand-driven per `feedback_parallel_track_gates_manual_run`)

<domain>
## Phase Boundary

This phase restores **vector-similarity retrieval + rerank** on the deployed **Databricks** KB app, which currently runs 100% on a degraded WEIGHT-fallback path. It closes ISSUES **#64** (UC-Volume vector-chunk misalignment) and **#65** (rerank configured-but-inactive), and — as the unblocking prerequisite for #64 — fixes **#41** (the OOM-dead Qdrant→nanovectordb converter).

**The causal chain (all live-probed 2026-06-24):**
1. Databricks app reads **on-disk** `vdb_*.json` (NanoVectorDBStorage — no Qdrant on Databricks; `kb/api.py:92` defaults to `nanovectordb`).
2. `sync_to_databricks.sh` Step 3 copies Aliyun's **on-disk** `vdb_*.json` to the UC Volume.
3. Aliyun's on-disk vdb is **stale + broken**: `vdb_chunks.json` = 2026-06-06 / 3294 entries (vs graphml today 32056 nodes), `vdb_relationships.json` = **49-byte empty placeholder**.
4. The converter that regenerates on-disk vdb from Aliyun's *fresh* Qdrant (`scripts/qdrant_to_nanovdb.py`) is **OOM-dead** (#41); its `qdrant-snapshot.timer` is **disabled** since 2026-06-05.
5. ∴ Databricks serves a stale/misaligned snapshot → `0 vector chunks` every query → WEIGHT fallback. Aliyun's freshness lives only in Qdrant, which does NOT sync.

**Therefore the locked path (Path A+):** fix #41 streaming-write → regenerate Aliyun on-disk vdb from its fresh Qdrant (now aligned to the fresh graphml) → `sync_to_databricks.sh` to the UC Volume → re-hydrate Databricks → fix #65 rerank wiring → re-verify.

**This is finish-existing / fix-known-broken work — ZERO new features.** Every artifact already exists; this phase repairs them.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Fix-path (user-decided, 2026-06-24)
- **Focus = #64 + #65** (Databricks KG-retrieval quality). Confirmed over ops-hardening (#60) and quick-only alternatives.
- **#64 path = "Path A+ — fix #41 first, then sync."** Chosen AFTER the initial "sync-from-Aliyun" choice was falsified by probe (Aliyun on-disk vdb is the stale/broken artifact; its freshness is Qdrant-only and the Qdrant→vdb converter is dead). Path B (serverless reindex Job) was rejected for this phase due to its dim=1024-vs-deployed-3072 reconciliation cost + LLM re-extraction spend.
- **Embedding dim stays 3072** (`gemini-embedding-2`, Vertex SA) end-to-end — matches `app.yaml:51` (arx-2 decision) and Aliyun's live Qdrant (`..._gemini_embedding_2_3072d`). No dim flip.

### #41 — converter streaming-write fix
- Root cause (confirmed): `export_collection_to_nanovdb` (`scripts/qdrant_to_nanovdb.py:92`) accumulates ALL `rows` + `vectors` in memory (lines 121-122), then `np.array(vectors)` (line 168) + `array_to_buffer_string` (line 171) before a single `json.dump`. Relationships = 82582 × 3072 float32 ≈ multi-GB peak RSS on a 14G box → systemd `oom-kill` (~2h47min wall on the 2026-06-05 fire).
- **Constraint the planner MUST resolve:** the nano_vectordb on-disk format stores the matrix as a **single base64 string** (`{"embedding_dim", "data":[...], "matrix": "<b64>"}` — `dbs.py` schema, lines 16-20 + 173-177). A naive "stream rows to disk" does NOT trivially bound the matrix encode. The planner must determine the actual viable memory-bounding approach — candidates: (a) batched float32 accumulation into a single pre-allocated `np.memmap` / chunked buffer-string build; (b) raise systemd `MemoryMax` and accept a higher-but-bounded ceiling; (c) per-namespace processing already exists (relationships is the killer). Must be validated against the REAL 82582-point relationships collection on Aliyun, not a toy.
- **Atomic write already present** (line 182-185: `.tmp` + `os.replace`) — preserve it.
- **Re-enable trigger:** ISSUES #41 says re-enable `qdrant-snapshot.timer` only after the streaming-write fix lands. This phase does that.

### #64 — sync + re-hydrate
- Use the existing `scripts/sync_to_databricks.sh` (validated 2026-05-28, 260528-f1s). It tars Aliyun on-disk `lightrag_storage` → UC Volume `fs cp -r --overwrite` → app stop/start/**redeploy** (stop+start alone wipes the deployment artifact — memory `databricks_apps_stop_start_wipes_deployment`; the script's Step 9c redeploy handles this).
- **Pre-sync gate (NEW, mandatory):** before running the sync, assert Aliyun on-disk vdb is FRESH + aligned post-#41-regen: `vdb_chunks.json` data_len ≈ Qdrant chunks count (3851±) AND `vdb_relationships.json` > 49 bytes (not the empty placeholder) AND graphml node count ≈ vdb_entities data_len. The whole point is to not transplant the stale state again.

### #65 — rerank init-vs-query reconcile
- Wiring is present: `kb/api.py:_build_llm_rerank()` (:50) → `app.state.reranker` + `app.state.rerank_disabled` (:86-88) → `LightRAG(rerank_model_func=rerank_func)` (:100). Query paths thread `rerank_disabled` into mode selection (`mix` if enabled else `hybrid`) — `kb/api_routers/search.py:73,249`, `kb/api_routers/synthesize.py:68`, `kb/services/synthesize.py:628`.
- The deployed symptom: startup logs `llm_rerank_init_ok provider=databricks_serving` BUT every query logs `WARNING: Rerank is enabled but no rerank model is configured` (that WARNING originates **inside LightRAG** at query time).
- **Investigation (planner):** trace whether LightRAG's query path needs `enable_rerank=True` as an explicit ctor kwarg ALONGSIDE `rerank_model_func=` (LightRAG 1.4.x may gate rerank on a separate `enable_rerank` flag that the app never sets), OR whether `rerank_model_func` isn't surviving into the query call. Decide: **wire it** (add the missing kwarg/flag) OR **set `enable_rerank=False`** to drop the misleading warning. Whichever the trace proves. Bounded ~10-40 LoC.
- Rerank provider on Databricks = `databricks_serving` (`lib/llm_rerank.py` → `lightrag_databricks_rerank.make_rerank_func()`).

### Verification (Principle #6 — local UAT + deployed re-UAT mandatory)
- **Databricks deployed re-UAT** is the acceptance gate (not tests alone). Re-run the arx-2 Deep Research UAT at iterations=1.
- **Pass bar:** deployed backend log shows `Raw search results: >0 vector chunks` (NO `falling back to WEIGHT method` WARNING) AND (#65: rerank wired → no `no rerank model is configured` WARNING; OR disabled → warning gone by design) AND Deep Research / long_form returns `sources>0` + cited report still renders.
- Cite evidence in `arx-4-...-VERIFICATION.md` per Principle #6 (commands, log excerpts, before/after WARNING diff).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### #41 — converter (the OOM fix)
- `scripts/qdrant_to_nanovdb.py` — `export_collection_to_nanovdb` (:92, the OOM site: full-accumulation lines 121-122/168/171); `main()` (:203, per-namespace loop + env vars). Atomic write at :182-185 (preserve).
- `venv/Lib/site-packages/nano_vectordb/dbs.py` — the on-disk matrix base64 format authority (`Float`, `array_to_buffer_string`); the single-blob constraint that bounds the streaming approach.
- ISSUES.md **#41** row — root-cause analysis + "streaming-write ~50-100 LoC" estimate + re-enable trigger.
- ISSUES.md **#42** — sibling SLB-throttle (folds into #41; bounding RSS removes the throttle trigger).

### #64 — sync + UC Volume
- `scripts/sync_to_databricks.sh` — full 10-step sync (Step 3 lightrag_storage tar→UC Volume; Step 9 stop/start/redeploy). Header lines 25-30 explain the converter-derived vdb dependency.
- `scripts/sync_to_databricks.md` — companion runbook.
- `databricks-deploy/startup_adapter.py` — `hydrate_lightrag_storage_from_volume` (:56) UC-Volume → `/tmp` hydration; idempotency short-circuit (:83 — **a re-hydrate after sync may need the /tmp cache cleared or the app restarted to re-copy**).
- `databricks-deploy/app.yaml:51` — 3072-dim Vertex SA embedding declaration (the dim contract).

### #65 — rerank wiring
- `kb/api.py:50-120` — `_build_llm_rerank()` + `lifespan()` LightRAG ctor (`rerank_model_func=` at :100, `rerank_disabled` state at :88).
- `databricks-deploy/lib/llm_rerank.py` — `get_rerank_func()` provider dispatcher (databricks_serving default).
- `databricks-deploy/lightrag_databricks_rerank.py` — `make_rerank_func()` (the actual Databricks serving rerank callable).
- `kb/api_routers/search.py:73,249` + `kb/api_routers/synthesize.py:68` + `kb/services/synthesize.py:564,628` — query-path `rerank_disabled` → mode (`mix`/`hybrid`) threading.

### Memory (retrieval/concurrency landscape — read before planning)
- `databricks-kg-weight-fallback-residue` — the exact #64/#65 deployed-log symptom.
- `databricks-apps-sse-300s-cap` — why #63 (iterations≥2) is OUT of scope (async-rearch = new-build).
- `graphml-qdrant-cross-version-divergence` + `2026_06_08_aliyun_recovery_postmortem` — the #44 divergence pattern + detection script.
- `lightrag-networkx-write-not-atomic` — atomic-write discipline for storage files.
- `feedback_parallel_track_gates_manual_run` — suffix-milestone gate hand-driving.
- `claude_databricks_deployment_autonomous` + `databricks_apps_stop_start_wipes_deployment` — Claude owns deploys; redeploy after stop/start.
- `aliyun_ssh_manual_trigger_env` — Aliyun manual cmds need `set -a; source /root/.hermes/.env; set +a` (DEEPSEEK_API_KEY=dummy else).
- `corp_pem_rebuild_pattern` — if Databricks SDK calls hit SSL.
</canonical_refs>

<specifics>
## Specific Ideas / Constraints

- **Channel discipline (PRINCIPLE #5 + #7):** Aliyun read-only diagnostics → run SSH yourself via Bash. Aliyun WRITE ops (run the fixed converter on prod, regenerate vdb, re-enable timer) → these MUTATE Aliyun prod state. Per the boundary memory `feedback_ssh_readonly_vs_writeop_boundary`, write-ops are phase-gated: the executor may run them via Bash SSH **only if the plan explicitly authorizes that task as a write-op**; otherwise author a Hermes/operator prompt. Lock this in the plan per-task. Databricks deploy → Claude runs CLI directly (PRINCIPLE #7).
- **#41 fix must be tested on the REAL relationships collection** (82582 points) on Aliyun, not a synthetic fixture — the OOM only manifests at scale. The behavior-anchor harness discipline applies if touching the converter's contract.
- **Aliyun box is 2-core / 14G** — the #41 fix must demonstrably keep peak RSS bounded (target the row-count-independent ceiling the ISSUES #41 row specifies, ~50-100 MB if pure-streaming is achievable; else a documented MemoryMax ceiling).
- **Disk headroom:** Aliyun `/dev/vda3` at 85% (15G free). Regenerating vdb_*.json writes ~1GB+ (`vdb_entities.json` alone is 873MB). Verify free space before the regen + sync tar (`/tmp` tar adds transient ~2.6GB). #61 containerd 23G is reclaimable if space gets tight — but that's a separate issue, only touch if blocked.
- **Timer re-enable is the #41 closure marker** — `systemctl enable --now qdrant-snapshot.timer` after the fix is verified, so on-disk vdb stays fresh going forward (closes the root cause, not just this one sync).
- **vdb_archive_*.json** (the 2026-05-30 SoT fallbacks, 1.1GB relationships) are the current Databricks relationships source per #41 row — the regen replaces the live `vdb_relationships.json` placeholder with real data, so confirm the sync ships the real file not the archive.
</specifics>

<deferred>
## Deferred Ideas (explicit out-of-scope for arx-4)

- **#63 Databricks iterations≥2 (async-job rearchitecture)** — new-build; the SSE arch cannot defeat the ~300s duration cap. Natural arx-3 follow-up. NOT this phase.
- **#40 in-process ingest concurrency** — research-CLOSED BLOCKED (1.27x). Do not re-attempt.
- **#36 single-article 48min wall** — fix candidates are new infra. Park.
- **#60 instance-rebuild checklist** — real ops work but preventive-script, separate quick.
- **#61 containerd 23G reclaim / #51 disk-trend** — ops cleanup quick (touch only if disk blocks the regen).
- **#54 roadmap stub, #23 deps trim, #53 translate-1258, #49 ZH-dedupe** — individual `/gsd:quick`s in their own windows.
- **#3 wiki-bilingual / #5 suggestions queue / #28 image-emit-rate** — decision-gated or measurement-first; not fixes.
- **#58 WeChat password rotation / #18 PAT rotation** — user-only.
- **Aliyun #44** — already self-healed (live-verified sources=13); this phase only addresses the Databricks residue. (The #41 fix DOES re-align Aliyun's own on-disk vdb as a side effect, a bonus, but Aliyun's *runtime* Qdrant path was never broken.)
</deferred>

---

*Phase: arx-4-databricks-kg-retrieval*
*Context gathered: 2026-06-24 via plan-phase triage + 2 user fix-path gates*
