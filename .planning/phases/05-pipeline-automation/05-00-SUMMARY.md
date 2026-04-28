---
phase: 05-pipeline-automation
plan: 00
subsystem: embedding-migration
tags: [embedding, migration, lightrag, gemini, wave0, quota-blocker]
status: FAILED — quality gate did not pass
requires: []
provides: [embedding-3072-shared-module, wave0-reembed-script, wave0-verifiers]
affects: [lightrag_embedding.py, ingest_wechat.py, ingest_github.py, kg_synthesize.py, multimodal_ingest.py, query_lightrag.py, cognee_wrapper.py]
tech-stack:
  added: [gemini-embedding-2, output_dimensionality=3072]
  patterns: [shared-embedding-module, vdb-wipe-reingest-migration]
key-files:
  created:
    - scripts/phase5_wave0_spike.py
    - scripts/wave0_reembed.py
    - tests/verify_wave0_benchmark.py
    - tests/verify_wave0_crossmodal.py
    - tests/fixtures/wave0_golden_queries.json
    - lightrag_embedding.py
    - docs/spikes/embedding-002-contract.md
    - docs/spikes/wave0_reembed_log.md
  modified:
    - ingest_wechat.py
    - ingest_github.py
    - kg_synthesize.py
    - multimodal_ingest.py
    - query_lightrag.py
    - cognee_wrapper.py
    - .planning/phases/05-pipeline-automation/05-PRD.md
decisions:
  - "Wave 0 quality gate FAILED: cross-modal verifier exit 1 after daily embedding quota exhausted"
  - "20/22 docs marked 'failed' by LightRAG's doc_status due to per-doc embedding-quota 429s"
  - "Root cause: Gemini free tier's 1000 req/day embedding cap is below what a 22-doc reindex needs"
metrics:
  date: 2026-04-28
  duration: "reembed ~18 min + ~30 min pre-run planning/debug"
  docs_attempted: 22
  docs_fully_processed: 2
  docs_partially_processed: 20
  embedding_dim_before: 768
  embedding_dim_after: 3072
  entities_final: 182
  relationships_final: 114
  chunks_final: 19
  api_errors_429_per_minute: 63
  api_errors_429_per_day: 435
  api_errors_503: 26
---

# Phase 5 Plan 00: Embedding Migration Summary — FAILED AT QUALITY GATE

Wave 0 of Phase 5 migrated the LightRAG embedding stack from `gemini-embedding-001 / 768-dim` to `gemini-embedding-2 / 3072-dim`. The static code consolidation landed cleanly (Tasks 0.1–0.6 shipped in commits `36ef9c0`, `e1c3adb`, `e83cc24`, `65e33bb`, `5a9c2a6`). The runtime execution (wipe + re-embed + verify) did NOT pass Wave 0's quality gate: the cross-modal verifier exited 1 and the graph is in a partially-rebuilt state with 20/22 docs flagged `failed` by LightRAG.

**Plan status: NOT COMPLETE.** Per the orchestrator's failure-modes instructions, this SUMMARY documents the outcome so the user can decide between rollback and resume-tomorrow.

## Deviations from Plan

### Baseline + 60% overlap check skipped (Option A — user decision pre-run)

The plan's Task 0.5 called for a baseline → re-embed → compare flow with `≥60% top-5 overlap per CN query`. That flow was architecturally unreachable after the 768→3072 plan edit (commit `74053c6`): baseline capture requires LightRAG to query the old 768-dim graph with the new `lightrag_embedding.py` at 3072 dim, which fails NanoVectorDB's `storage["embedding_dim"] == self.embedding_dim` assertion at init. The user chose Option A at the pre-execution checkpoint: skip baseline, run wipe + re-ingest, use the cross-modal verifier as the sole Wave 0 quality gate.

### Doc count was 22, not 18

The plan and 04-era STATE.md both reference 18 existing docs. Actual count at re-embed time was 22 (19 `doc-*` WeChat articles + 3 `zhihu_8ac04218b4_{0,1,2}`). The graph grew 4 docs since the Phase-4 STATE.md snapshot.

### Batch API unavailable on free tier

Spike report (`docs/spikes/embedding-002-contract.md`) recorded `batch_api_available: false` with a 429 RESOURCE_EXHAUSTED on the `batches.create_embeddings` call. Wave 0b MUST use the sync embedding path with throttling — already called out in Wave 0b's planning notes.

### [Rule 1 — Bug] wave0_reembed.py wipe list was incomplete (fixed inline)

**Found during:** initial `--i-understand` run 2026-04-28T13:48 UTC
**Issue:** Original wipe targeted only `vdb_*.json` + `kv_store_full_docs.json`. LightRAG's doc-level dedup lives in `kv_store_doc_status.json`; surviving status entries caused re-ainsert of pre-existing docs to be rejected as duplicates, leaving 19/22 docs with stale state and only 3 docs freshly-ingested.
**Fix:** Expanded wipe to cover all `kv_store_*.json` (preserving only `kv_store_full_docs.json.bak`) and `graph_chunk_entity_relation.graphml`. `--dry-run` and `--i-understand` refusal now print the full wipe list.
**Files modified:** `scripts/wave0_reembed.py`
**Commit:** `5a9c2a6`

## Static Deliverables (complete and committed)

| Task | Deliverable                                                              | Commit      |
|------|--------------------------------------------------------------------------|-------------|
| 0.1  | `scripts/phase5_wave0_spike.py` + `docs/spikes/embedding-002-contract.md` | (prior)     |
| 0.2  | `lightrag_embedding.py` (3072-dim, multimodal, `_priority` handling)     | `e1c3adb`   |
| 0.3  | 6-file consolidation import from `lightrag_embedding`                    | (prior)     |
| 0.4  | `scripts/wave0_reembed.py` (wipe + re-ingest)                            | `36ef9c0`   |
| 0.4  | Wipe-list fix: kv_store_* + graphml                                      | `5a9c2a6`   |
| 0.5  | `tests/verify_wave0_*.py` + `tests/fixtures/wave0_golden_queries.json`   | `e83cc24`   |
| 0.6  | PRD §2.4 model-name typo + 3 supersession notes                          | `65e33bb`   |

## Spike Verdict (from `docs/spikes/embedding-002-contract.md`)

```
batch_api_available: false
batch_detail: "ClientError: 429 RESOURCE_EXHAUSTED"
rpm_ceiling: 100
multimodal_works: true
recommendation: proceed
```

Sync fallback with conservative throttling. Multimodal embedding path confirmed end-to-end.

## Re-embed Runtime Results (from `docs/spikes/wave0_reembed_log.md`)

```
strategy: vdb-wipe-reingest (768->3072 dim migration)
date: 2026-04-28T17:21:12Z
before: entities=68, relationships=72, chunks=19, embedding_dim=3072  # ← polluted by first aborted run
processed: 22 docs                                                     # ← script-level count; misleading
after:  entities=182, relationships=114, chunks=19, embedding_dim=3072
errors: []                                                             # ← only counts Python-level exceptions
```

**The `errors: []` is misleading** — LightRAG treats per-chunk extraction/embedding failures as soft errors (it preserves the failed doc for manual review) and does not raise to `rag.ainsert()`'s caller. The actual doc-level outcome lives in `kv_store_doc_status.json`:

- **status=processed: 2 docs** (`doc-178cefebd82053aeac5c17bde4363fe1`, `doc-90d972e7e3b29df606fc72b513f7d0a5`)
- **status=failed: 20 docs** (all 19 WeChat `doc-*` that were pre-existing, plus the 3 `zhihu_*` never made it into the happy path due to quota exhaustion before they could finish)

### API error breakdown

| Error                             | Count | Cause                                                          |
|-----------------------------------|------:|----------------------------------------------------------------|
| 429 per-minute quota (100 RPM)    |    63 | Expected under free-tier RPM cap; retries handled it           |
| 429 per-day quota (1000 req/day)  |   435 | Hard daily cap hit mid-run; no retry can succeed until midnight UTC |
| 503 UNAVAILABLE (transient)       |    26 | Gemini model high-demand                                       |

## Cross-modal Verifier (the Wave 0 quality gate — FAILED)

Run at 2026-04-28T17:37 UTC after the re-embed. Exit **1**.

- First invocation: crashed on 503 during keyword extraction for `LightRAG 系统架构图`.
- Second invocation: crashed on 429 per-day quota during entity-VDB embedding for `LightRAG 系统架构图`.

The verifier never got past the FIRST cross-modal query because the Gemini free-tier daily embedding quota was already exhausted from the re-embed run. **No cross-modal hit data was captured. The Wave 0 gate cannot be evaluated today.**

## Manual CN spot-check

Skipped. The `query_lightrag.py` path requires at least one query-time embedding call, and the per-day quota is exhausted until UTC midnight (~6 hours after this SUMMARY).

## `EMBEDDING_MODEL` env-var diff (remote WSL `~/.hermes/.env`)

```diff
+ EMBEDDING_MODEL=gemini-embedding-2
```

(Added prior to this run as part of Task 0.3. Verified by `grep -c '^EMBEDDING_MODEL=gemini-embedding-2' ~/.hermes/.env` returning `1`.)

## Current graph state (post-run)

```
embedding_dim: 3072                          ← migration at storage level: DONE
vdb_chunks.json rows: 19                     ← only 2 docs' worth of chunks
vdb_entities.json rows: 182                  ← entity extraction did land for many chunks before quota hit
vdb_relationships.json rows: 114
kv_store_full_docs.json: 22 records          ← all docs restored from backup
kv_store_doc_status.json: 22 records (2 processed, 20 failed)
kv_store_full_docs.json.bak: 600KB preserved ← safe rollback material
```

The graph is **partially migrated**. The storage-level dim is 3072 and some chunks/entities/relationships are present, but the canonical doc_status says 20/22 docs are incomplete. Retrieval quality is unknown because the quality gate could not run.

## Rollback material

- Original 768-dim graph state is NOT preserved on-disk anywhere (the wipe is destructive by design).
- Git-level rollback: `git revert 5a9c2a6 74053c6 e1c3adb 36ef9c0 e83cc24 65e33bb` would restore the code to pre-Wave-0 state, but the LightRAG storage is already wiped — a revert does not recreate the old 768-dim chunks. A fresh ingest from source (not the backup) would be required. **The .bak backup is 3072-compatible only as content source; the old 768-dim embeddings are gone.**

## Decision required (open checkpoint — next-day options)

Per the orchestrator's failure-modes: "Cross-modal verifier fails: DO NOT paper over it. This is the whole Wave 0 quality gate. Return a failure checkpoint with the log; we'll decide whether to roll back via git or accept and proceed."

### Option A — Resume tomorrow after quota resets (RECOMMENDED)

1. Wait until UTC midnight (daily quota reset — ~06:00 local time on 2026-04-29).
2. Re-run `scripts/wave0_reembed.py --i-understand` to re-attempt the 20 failed docs (the content is still in `kv_store_full_docs.json.bak`; the script's dedup will skip the 2 already-processed docs).
3. Run `tests/verify_wave0_crossmodal.py` as the gate.
4. If cross-modal passes: close plan 05-00 normally, advance STATE.md.
5. If cross-modal fails again: escalate for Option B or C.

**Risk:** A second re-run on the same free-tier key may hit the daily cap again if the 20-doc re-attempt plus verifier queries exceeds 1000 embedding calls. Conservative estimate: 20 docs × ~50 embedding calls each ≈ 1000, cutting it fine.

### Option B — Bill Gemini Tier 1 and complete today

1. User upgrades to Gemini paid Tier 1 (removes the 1000/day embedding cap; 1000 RPM instead of 100).
2. Re-run re-embed + verifier in the same session.
3. Highest chance of same-day completion. Budget impact: a few USD for this migration.

### Option C — Accept partial graph and mark Wave 0 degraded

1. Call the current 2-doc graph "good enough for Phase 5 forward motion".
2. Downstream plans (Wave 0b RSS, etc.) will ingest new content at 3072-dim that stacks on top.
3. Historical retrieval quality (the 20 failed docs) degrades until a future reindex window.
4. Cross-modal verifier remains untested until Phase 5 later.

**Not recommended.** This defers the quality gate indefinitely and makes downstream benchmarks impossible to interpret.

## Self-Check

Verifying claims made above:

| Claim                                                             | Verified                                 |
|-------------------------------------------------------------------|------------------------------------------|
| `scripts/wave0_reembed.py` exists                                 | YES (commit 36ef9c0, fix 5a9c2a6)        |
| `lightrag_embedding.py` exists at repo root                       | YES                                      |
| `docs/spikes/embedding-002-contract.md` exists on main branch     | YES                                      |
| `docs/spikes/wave0_reembed_log.md` exists and is committed        | YES (commit `49c4af6`)                   |
| Remote `vdb_chunks.json` embedding_dim == 3072                    | YES (verified via `python3 -c json.load`) |
| Cross-modal verifier exit code                                    | 1 (FAILED)                               |
| `kv_store_full_docs.json.bak` preserved for rollback/retry        | YES (600KB, verified via `ls -la`)       |

## Self-Check: DEFERRED (plan not complete)

The orchestrator's normal Self-Check expects green criteria. This plan has a FAILED quality gate; STATE.md and ROADMAP.md will NOT be advanced until the user selects an option and the cross-modal verifier passes.
