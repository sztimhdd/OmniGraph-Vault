---
status: in_progress
phase: arx-4-databricks-kg-retrieval
source: [arx-4-databricks-kg-retrieval-01-SUMMARY.md, arx-4-databricks-kg-retrieval-02-SUMMARY.md, arx-4-databricks-kg-retrieval-03-SUMMARY.md]
updated: 2026-06-26
requirements: [ARX4-41, ARX4-64, ARX4-65, ARX4-UAT]
---

# arx-4-databricks-kg-retrieval — VERIFICATION

## Result: [PENDING final deployed re-UAT — awaiting human SSO query on deploy 3ffb68]

This phase set out to close three deployed-Databricks KG-retrieval issues: #41
(converter OOM), #64 (0 vector chunks / WEIGHT fallback), #65 (rerank
configured-but-inactive). The investigation **overturned the original #64 and
#65 premises** (both were misdiagnosed as a UC-Volume data problem; the real
cause was the research retriever using `hybrid` mode + a fresh reranker-less
LightRAG). The data sync + converter fix still stand as correctness/quality
wins; the load-bearing #64/#65 fix is a 12-LoC retriever change.

---

## #41 (ARX4-41) — converter OOM — ✅ CLOSED

Root cause: `export_collection_to_nanovdb` held a per-row Python float list +
a separate `np.array` copy simultaneously (~tens of GB for 84572×3072).

Fix (commit `5d57c0b`): stream raw float32 bytes into ONE `bytearray`, encode
once. Byte-identical to the old path (4 new behavior-anchor tests, 9/9 green).

**Aliyun real-scale proof** (`/usr/bin/time -v`, the actual 84572-point
relationships collection):
```
qdrant_snapshot_file collection=...chunks...        points=3970  dim=3072 wall_s=7.636
qdrant_snapshot_file collection=...entities...      points=60754 dim=3072 wall_s=99.311
qdrant_snapshot_file collection=...relationships... points=84572 dim=3072 wall_s=145.951
qdrant_snapshot_ok files_written=3 total_wall_s=253.254
Maximum resident set size (kbytes): 6401664        ← ~6.4 GB, no OOM (was OOM-killed)
CONVERTER_EXIT=0
```
- `vdb_relationships.json`: 49-byte placeholder → **1.42 GB** real file.
- `qdrant-snapshot.timer` **re-enabled** (`is-enabled=enabled`, `is-active=active`)
  — the #41 closure marker. SET 2026-06-26 01:45 CST.

---

## #64 (ARX4-64) — 0 vector chunks / WEIGHT fallback — [fix shipped, UAT pending]

**Original premise (WRONG):** "graphml↔vdb-chunk misalignment in the UC-Volume
snapshot." The 50-min sync transplanted a fresh, alignment-verified (95.8%)
snapshot — and the symptom DID NOT CHANGE (`Raw search results: ... 0 vector
chunks` still logged). So misalignment was never the cause.

**True root cause (code-confirmed):** LightRAG `operate.py:3695` gates
vector-chunk retrieval to `query_param.mode == "mix"` ONLY. The research
retriever (`lib/research/stages/retriever.py:39`) hardcoded `mode="hybrid"`,
which never queries `chunks_vdb` → always 0 vector chunks → WEIGHT fallback.
The working `/api/synthesize` + `/api/search` paths already use
`mode="mix"` (synthesize.py:628, search.py:73); research was the lone holdout.

**Fix (commit `324a507`):** `retriever.py:39` + `reasoner.py:126`
`mode="hybrid"` → `"mix"`.

**Deployed pre-fix log (2026-06-26, deploy 01f170e2):**
```
Raw search results: 36 entities, 304 relations, 0 vector chunks
No entity-related chunks selected by vector similarity, falling back to WEIGHT method
```
**Deployed post-fix log (deploy 3ffb68):** [PENDING — human re-UAT: expect
`Raw search results: ... K vector chunks` with K>0, WEIGHT-fallback lines ABSENT.]

The synced 1.42 GB relationships vdb + fresh chunks remain a genuine
relationship-retrieval quality + correctness improvement (the placeholder was
real), even though it was not the #64 symptom cause.

---

## #65 (ARX4-65) — rerank configured-but-inactive — [fix shipped, UAT pending]

**Original premise (WRONG):** Plan 02's `rerank_diag` measured
`app.state.lightrag` (the lifespan instance) and found `global_config_has_func=True`,
concluding "wiring correct, no fix." But that was the WRONG instance.

**True root cause (code-confirmed):** the research path builds a FRESH
LightRAG without `rerank_model_func` (`omnigraph_search/query.py:82`, the
`rag is None` branch) because `retriever.py:39` passed no `rag=`. Query-time
`global_config["rerank_model_func"]` is None → `utils.py:2640-2645` warns.
`/api/synthesize` avoids this by passing `rag=app.state.lightrag`.

**Fix (commit `324a507`):** thread the lifespan `app.state.lightrag` (with
reranker) through `ResearchConfig.rag` → retriever/reasoner reuse it instead of
building a fresh instance. Also avoids a second cold LightRAG init per call.

**Deployed pre-fix log:** `WARNING: Rerank is enabled but no rerank model is configured.`
**Deployed post-fix log (deploy 3ffb68):** [PENDING — expect that WARNING ABSENT.]

---

## Boot-timeout (surfaced + fixed in-phase) — ✅ RESOLVED

Syncing the real 1.42 GB relationships vdb made the first redeploy FAIL ("App
process did not start within 10 minutes"): `_db_bootstrap.hydrate_lightrag_storage`
downloaded all 147 UC-Volume files SEQUENTIALLY before uvicorn binds → blew the
600s deadline.

Fix (commit `8ceef46`, mirrors the proven `hydrate_images_dir` pattern):
`ThreadPoolExecutor(max_workers=8)` parallel download + junk-skip filter
(`.bak/.corrupt/.repaired/.truncated`). One-time purge of 135 junk files
(1.03 GB) from UC Volume (→ 12 real files, 2.50 GB) + Aliyun SoT. Redeploy
`01f170e2` = SUCCEEDED. (Boot binds the port only after the lifespan matrix
load, so SUCCEEDED proves no OOM on the 1.42 GB parse.)

---

## Deployed re-UAT (ARX4-UAT) — [PENDING]

Query: `POST /api/research {query:"what is a harness for agent", max_iterations:1}`
on deploy `3ffb68` (the #64/#65 fix). Entra-SSO blocks Playwright → human-run.

Pass-bar (4 conditions):
- `POST /api/research 200` ✓ (already confirmed status 200 on pre-fix deploy)
- `vector chunks` count > 0 [PENDING]
- NO `falling back to WEIGHT method` [PENDING]
- NO `Rerank is enabled but no rerank model is configured` [PENDING]
- report renders with sources > 0 [PENDING]

## Known limitations carried forward

- #63 (iterations≥2 async-job) remains OUT of scope — the SSE 300s duration cap
  is unchanged by this phase.

## Process notes (3 premise reversals this phase)

1. #64 was misdiagnosed as data-misalignment (real cause: hybrid vs mix mode).
2. #65's Plan-02 trace measured the wrong LightRAG instance.
3. The vdb sync surfaced an unrelated boot-timeout that had to be fixed first.

Each was caught by ground-truth verification (the deployed log, the code trace,
the failed boot) rather than accepted on the prior plan's premise.
