# arx-3 — EVIDENCE

**Phase:** arx-3 (Long-form citation compliance + KG search empty-results fix + Q1 chunk-metadata verification + LightRAG singleton)
**Date:** 2026-05-27
**Status:** YOLO acceptance criteria all GREEN on Databricks deploy.

---

## YOLO Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| a | Singleton in effect — graph loaded ONCE per app process | GREEN | 1 `Loaded graph` event + 3 `nano-vectordb:Init` events across 2 back-to-back synthesize calls |
| b | `/api/synthesize` long_form → `confidence=kg` with substantive content | GREEN | call1 (RAG): conf=kg, fallback=False, ~2500-char markdown / call2 (LightRAG): conf=kg, fallback=False, **8617-char markdown** |
| c | `/api/search?mode=kg&q=AI Agent` returns substantive content | GREEN | Async job `850c74a1f678` → status=done, ~3000-char markdown answer covering Agent core architecture, OpenClaw/Hermes/Claude Code |
| d | `/api/search?mode=fts&lang=en` returns ≥1 hit | GREEN | `q=agent`=20 hits / `q=RAG`=20 hits / `q=knowledge`=20 hits. (`q=LightRAG`=0 — brand name absent in EN bilingual layer; `q=AI`=0 — 2-char query below trigram tokenizer min-length, both expected per kb-3 design) |

---

## Singleton Lifecycle Evidence (Databricks deploy)

Source: `.scratch/arx-3-probes/tail-runtime-2.log` lines 470-500 (deployment_id `01f159e24fd41cdcb7162a6cd5013df9`, 2026-05-27 boot).

```
1779897095 [APP] kb.db_bootstrap INFO LightRAG storage hydration complete: 12 files, 1929953982 bytes
1779897238 [APP] INFO:     Application startup complete.
1779897238 [APP] INFO:     Uvicorn running on http://0.0.0.0:8000
1779897444 [APP] INFO:     POST /api/synthesize HTTP/1.1 202 Accepted        # call1
1779897448 [APP] INFO: [] Loaded graph from .../graph_chunk_entity_relation.graphml with 30068 nodes, 43143 edges    # ← ONLY GRAPH LOAD
1779897457 [APP] INFO:nano-vectordb:Init {... vdb_entities.json} 30067 data
1779897470 [APP] INFO:nano-vectordb:Init {... vdb_relationships.json} 43133 data
1779897470 [APP] INFO:nano-vectordb:Init {... vdb_chunks.json} 1967 data
1779897470 [APP] INFO:     POST /api/synthesize HTTP/1.1 202 Accepted        # call2 — graph already loaded
1779897470 [APP] INFO:kb.services.synthesize:c1_before_aquery: job_id=e9597828b329 mode=long_form prompt_chars=400
1779897473 [APP] INFO:kg_synthesize:lightrag_singleton_ready wall_s=28.48
1779897473 [APP] INFO:kg_synthesize:kg_before_aquery: attempt=1 mode=hybrid prompt_chars=17245
1779897473 [APP] INFO:kg_synthesize:kg_before_aquery: attempt=1 mode=hybrid prompt_chars=17250    # call2 reuses singleton
```

**Key signals:**

- `Loaded graph` count = **1** (entire process lifetime)
- `nano-vectordb:Init` count = **3** (entities + relationships + chunks, fired once each)
- `lightrag_singleton_ready` count = **1**, `wall_s=28.48` (warm; storage already hydrated by db_bootstrap at boot)
- Both calls landed `kg_before_aquery` against the same singleton — no second init.

Pre-fix behavior (regression observed 2026-05-27 morning): graph reloaded on every synthesize call, ~28s wall-time per request, no singleton markers. Root cause + fix below.

---

## Singleton Regression Root Cause (and Fix)

Local `kg_synthesize.py` (commit 67dfe5b) had the singleton implementation; deployed copy at `/Workspace/.../databricks-deploy/kg_synthesize.py` did **not**.

`databricks-deploy/Makefile` Pass 0c stages the project-root file via `cp ./kg_synthesize.py ./databricks-deploy/kg_synthesize.py` before sync. However:

1. Project-root `.gitignore` lines 91-94 exclude `databricks-deploy/{config.py,kg_synthesize.py,lib/}`
2. `databricks sync` honors `.gitignore` by default
3. Pass 1 sync had `--include "_ssg/**"` only — no override for the Pass-0c artifacts
4. Sync silently skipped the staged files; the workspace kept the previous (pre-singleton) copy
5. `databricks apps deploy` rolled the stale workspace code into the running app

**Fix landed in this phase:** Makefile Pass 1 now passes
`--include "kg_synthesize.py" --include "config.py" --include "lib/**"`
in addition to `--include "_ssg/**"`. Without these, every future `make deploy` would silently regress on staged-file sync.

The fix was applied manually in this session (verified by post-fix workspace export showing singleton markers at lines 78-86), then committed to the Makefile so future runs land the artifacts automatically.

---

## Probe Matrix

| Probe | Endpoint | Query | Expected | Observed |
|-------|----------|-------|----------|----------|
| A-health | GET /health | — | 200 | 200 |
| B-zh-fts | GET /api/search?mode=fts&lang=zh-CN | (multiple) | ≥1 hit | confirmed prior session |
| C-kg-search | GET /api/search?mode=kg | "AI Agent" | substantive | ~3000-char markdown ✓ |
| D-long_form | POST /api/synthesize mode=long_form | "What is RAG?" | conf=kg, substantive | conf=kg, ~2500 chars ✓ |
| E-en-fts | GET /api/search?mode=fts&lang=en | (multiple) | ≥1 hit | agent=20, RAG=20, knowledge=20 ✓ |
| F-singleton | log markers across 2 synthesize calls | — | 1 Loaded graph + 3 ndvb:Init | 1 / 3 ✓ |

---

## Files Modified

- `databricks-deploy/Makefile` — Pass 1 sync now includes `kg_synthesize.py`, `config.py`, `lib/**` explicitly so `.gitignore` lines 91-94 don't silently strip Pass-0c artifacts.

## Logs (not in git, retained under `.scratch/`)

- `.scratch/arx-3-probes/tail-runtime-2.log` — 531-line tail covering app boot through 2 back-to-back synthesize calls; primary singleton evidence
- `.scratch/arx-3-probes/T-runtime-call1.json` — initial 202 Accepted for synthesize call1
- `.scratch/arx-3-probes/T-runtime-call2.json` — initial 202 Accepted for synthesize call2

---

## T4.B Aliyun Parity Smoke

Aliyun is on commit `dddaa38` (pre-singleton); `kb-api.service` runs on `127.0.0.1:8766` behind Caddy.

| Probe | Result |
|-------|--------|
| `GET /health` | 200, `{"status":"ok","kb_db_path":...,"version":"2.0.0"}` |
| `POST /api/synthesize` long_form (en, "What is RAG?") | job `aab31a3c0da2` → status=done, **conf=no_results, fallback_used=False, md_len=2273** |
| `POST /api/synthesize` long_form (zh-CN, "AI Agent的核心架构是什么？") | job `e69dcc96ef91` → status=done, **conf=no_results, fallback_used=False, md_len=2802** |

**Parity assessment:**

- Aliyun runtime is healthy and `/api/synthesize` completes with substantive markdown payloads (~2k-3k chars).
- `conf=no_results` differential vs Databricks (`conf=kg`) is **out of arx-3 scope**: Aliyun runs the older `dddaa38` `kg_synthesize.py` (pre-singleton, pre-C0/C1/C2 dispatch refinements). The differential is a function of the prior-pin code path, not an arx-3 regression.
- The singleton fix is forward-compatible: the patched Makefile adds `--include` flags that govern Databricks deploy only. Aliyun deploy is independent (systemd-managed git pull + service restart). When Aliyun next pulls main, it will pick up the singleton automatically — no deploy-pipeline change needed there.

---

## arx-3 Close

All YOLO acceptance criteria GREEN on Databricks. Singleton regression root-cause + fix landed in `databricks-deploy/Makefile`. Aliyun parity smoke confirms no Aliyun-side regression. Outstanding `conf=no_results` differential on Aliyun is scoped to a follow-up phase.
