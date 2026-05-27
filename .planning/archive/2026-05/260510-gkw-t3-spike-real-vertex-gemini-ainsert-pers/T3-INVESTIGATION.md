# T3-INVESTIGATION — Real Vertex Gemini `ainsert` Persistence Contract

**Date:** 2026-05-10
**Predecessor:** quick `260509-t4i` (T1+T2 mock PASSED, T3 stub default-skipped)
**Production trigger:** 2026-05-10 09:00 ADT cron — 4 `ingestions=ok` wechat,
LightRAG `kv_store_doc_status` today: 1 processed + 1 processing + 7 pending
= 9 doc entries; 21-min gap between `graph_chunk_entity_relation.graphml`
mtime (09:12) and `finalize_storages` log line (09:33).

---

## 1. TL;DR

- **T3a result:** PASSED — `post-await=processed post-finalize=processed
  dt_await=1.6s dt_total=1.6s`.
- **T3b result:** 5/5 post-await processed, 5/5 post-finalize processed
  (total wall 57.4s; finalize 0.0s; per-iter dt=[11.3, 15.3, 8.8, 10.8, 11.1]s).
- **Root-cause inference (one sentence):** At single-doc and 5-doc sequential
  scale on `tmp_path` with `gemini-3.1-flash-lite-preview` + real `embedding_func`,
  the `await rag.ainsert(...)` boundary IS sufficient — `kv_store_doc_status`
  is already `'processed'` when `ainsert` returns and `finalize_storages`
  takes 0.0s; therefore the 09:00 ADT cron bug does **NOT** reproduce at
  this scale and **requires either higher entity/relation density,
  larger batch size, concurrent ainsert via `asyncio` gather, or
  cron-loaded resource pressure** to surface.

---

## 2. Test results raw

Log path: `.scratch/ainsert-t3-vertex-20260510T150857Z.log` (184 lines, gitignored).

Pytest header (UTC start `2026-05-10T15:08:57Z` ≈ `12:08 ADT`):

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.0.3, pluggy-1.6.0
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, mock-3.15.1, typeguard-4.5.1
asyncio: mode=Mode.AUTO
collecting ... collected 5 items / 2 deselected / 3 selected
```

T3 (existing, single-snapshot — confirms baseline still passes):

```
tests/unit/test_ainsert_persistence_contract.py::test_t3_real_vertex_gemini_single_doc
... INFO: Chunk 1 of 1 extracted 0 Ent + 0 Rel chunk-a6bb7bde3251ca2d810d32dadd9e8ae7
INFO: Phase 3: Updating final 0(0+0) entities and  0 relations from doc-t3-real-001
INFO: Completed merging: 0 entities, 0 extra entities, 0 relations
INFO: [] Writing graph with 0 nodes, 0 edges
INFO: In memory DB persist to disk
PASSED
```

T3a verbatim print stanza:

```
[T3a working_dir] C:\Users\huxxha\AppData\Local\Temp\pytest-of-huxxha\pytest-329\test_t3a_real_vertex_post_awai0
INFO: Processing d-id: doc-t3a-real-001
INFO: Chunk 1 of 1 extracted 0 Ent + 0 Rel chunk-a6bb7bde3251ca2d810d32dadd9e8ae7
INFO: Phase 3: Updating final 0(0+0) entities and  0 relations from doc-t3a-real-001
INFO: Completed merging: 0 entities, 0 extra entities, 0 relations
INFO: [] Writing graph with 0 nodes, 0 edges
[T3a status] post-await: processed
INFO: Successfully finalized 12 storages
[T3a status] post-finalize: processed
[T3a verdict] post-await=processed post-finalize=processed dt_await=1.6s dt_total=1.6s
PASSED
```

T3b verbatim print stanzas (5 iters + post-finalize + verdict):

```
[T3b working_dir] C:\Users\huxxha\AppData\Local\Temp\pytest-of-huxxha\pytest-329\test_t3b_sequential_5_real_ver0
[T3b iter 0] doc=doc-t3b-000 status=processed dt=11.3s
[T3b iter 1] doc=doc-t3b-001 status=processed dt=15.3s
[T3b iter 2] doc=doc-t3b-002 status=processed dt=8.8s
[T3b iter 3] doc=doc-t3b-003 status=processed dt=10.8s
[T3b iter 4] doc=doc-t3b-004 status=processed dt=11.1s
INFO: Successfully finalized 12 storages
[T3b post-finalize] doc=doc-t3b-000 status=processed
[T3b post-finalize] doc=doc-t3b-001 status=processed
[T3b post-finalize] doc=doc-t3b-002 status=processed
[T3b post-finalize] doc=doc-t3b-003 status=processed
[T3b post-finalize] doc=doc-t3b-004 status=processed
[T3b verdict] post-await processed: 5/5
[T3b verdict] post-finalize processed: 5/5
[T3b timing] loop_elapsed=57.4s finalize_elapsed=0.0s total=57.4s per_iter=['11.3s', '15.3s', '8.8s', '10.8s', '11.1s']
PASSED
```

Final summary:

```
=========== 3 passed, 2 deselected, 46 warnings in 68.43s (0:01:08) ===========
PYTEST_PIPE_EXIT=0
```

Notable LightRAG INFO observations during T3b: each iter triggered live LLM
extraction (`== LLM cache == saving:` lines, 3 ent + ~2 rel per chunk),
real entity merges across iters (`Merged: \`Lorem Ipsum\` | 1+1`, `2+1`,
`3+1`, `4+1`), and the on-disk graphml grew from 3 nodes/2 edges (iter 0)
to 7 nodes/7 edges (iter 4). Real ainsert path was exercised — not
short-circuited by cache.

---

## 3. Timing data

- **T3a `dt_await`:** 1.6s.
- **T3a `dt_total` (post-finalize):** 1.6s.
- **T3a finalize-phase delta (`dt_total - dt_await`):** 0.0s (rounding floor;
  the `Successfully finalized 12 storages` log line is observably present
  but added no measurable wall time).
- **T3b per-iter `dt`:** [11.3s, 15.3s, 8.8s, 10.8s, 11.1s] (mean 11.5s,
  range 8.8-15.3s).
- **T3b loop wall:** 57.4s.
- **T3b finalize wall:** 0.0s.
- **T3b total (loop + finalize):** 57.4s.

**Sync-vs-async inference:**

The contract hypothesis under test was: *"`ainsert` returns BEFORE
doc_status flips to 'processed'; the flip happens during a later
`finalize_storages()` or background task"*. The local evidence does
**not** support this hypothesis at the tested scale — `dt_await ==
dt_total` for T3a (both 1.6s), and every T3b iter shows
`status=processed` *immediately* after `ainsert` returns, not after
`finalize_storages`.

LightRAG's INFO logs corroborate: `In memory DB persist to disk` is
emitted **inside the ainsert path** (before `[T3b iter N]` is printed),
and the `Successfully finalized 12 storages` line at the end shows
finalize is essentially a no-op when persist-to-disk has already
happened mid-ainsert. So at small scale + small graph, the
production-bug shape (ainsert returning early relative to status
flip) cannot be reproduced.

---

## 4. Reproduces production bug?

Comparison vs 2026-05-10 09:00 ADT cron forensic:

| Signal | Production (09:00 ADT) | Local T3a (single doc) | Local T3b (5-doc) |
|---|---|---|---|
| ingestions=ok rows | 4 | 1 (test passes) | 5 (test passes) |
| kv_store_doc_status='processed' | 1-2 of 9 | 1/1 | 5/5 |
| graphml mtime → finalize log gap | 21 min | 0.0s | 0.0s |
| post-await status `'processed'` | unobserved (production never snapshotted) | yes | 5/5 yes |

**Verdict:** **DOES NOT REPRODUCE locally — production bug requires
higher entity/relation density, larger batch size, concurrent
ainsert via `asyncio.gather`, or cron-loaded concurrency that the
local 5-doc sequential spike does not replicate.**

Specifically, at the local scale tested:

- T3 doc was `"x" * 5000` → LLM extracted 0 ent + 0 rel (degenerate content).
- T3a doc was `"x" * 5000` → 0 ent + 0 rel (same).
- T3b docs (lorem ipsum + 中文样本) → 3 ent + ~2 rel each, peak graph
  7 nodes / 7 edges. Production has dozens-to-hundreds of articles
  per cron with vastly richer entity/relation extraction; the merge
  + graphml-write phase cost scales with that, not with the
  scaffolding-mode 7-node graph.
- Local concurrency: pytest serial execution, ONE LightRAG instance,
  no other workload. Production cron runs alongside scrape-cascade,
  vision-cascade, and possibly multiple agents — resource
  pressure differs by at least an order of magnitude.

The hypothesis "ainsert returns before status flips" is **not
disproven** for the production scale — it is **not reproducible at
the scale the local spike could afford**. The bug surface is now
narrowed to: graph-merge phase under high entity-count batch,
or concurrent-ainsert resource contention, or cron-process timeout
truncating finalize. The next investigation must target one of
those three vectors.

---

## 5. Next quick (fix range — NOT IN THIS QUICK)

This is a fix-options enumeration for the user's decision, not a
recommendation to implement.

Possible approaches (ordered by LOC / risk):

1. **Add `await rag.finalize_storages()` after every `ainsert` in
   `ingest_wechat.py` / `batch_ingest_from_spider.py` ainsert call
   sites.** LOC ~3-5. **Risk:** per-article finalize may serialize batch
   throughput (current 5-15 min/article × 20+ articles already
   borderline against the 28800s `HERMES_CRON_TIMEOUT` ceiling); needs
   a Hermes-side batch-timing measurement before commit.

2. **Move the `ingestions=ok` write to AFTER a single
   `finalize_storages()` at end-of-batch in
   `batch_ingest_from_spider.py`.** LOC ~10-15. **Risk:** failure of one
   article's persistence would block the whole batch's ingestions
   ledger update — operationally fragile under the 09:00 ADT failure
   mode (where multiple articles already fail today). Also changes
   semantics: today's "we tried to ingest 4, succeeded on 1-2" becomes
   "we ingested all-or-nothing".

3. **Poll `kv_store_doc_status.json[doc_id]['status'] == 'processed'`
   with a bounded wait (e.g. 30s) after `await rag.ainsert(...)`
   before writing `ingestions=ok`.** LOC ~15-20 (helper +
   integration). **Risk:** bounded wait may exceed cron per-article
   budget on slow articles; need to pick a ceiling that's compatible
   with the existing ~5-15 min/article observed budget.

4. **Reproduce the production bug locally first via a higher-scale
   spike (15-30 docs, real WeChat content with rich entities, real
   embedding) BEFORE fixing.** LOC = 0 (new test only). **Risk:** none
   technical, but lengthens time-to-fix by one quick. Highest-value
   if Option 1/2/3 each have non-trivial throughput cost — picking
   the wrong one without ground-truth reproduction is a real
   regression risk on a daily cron path.

**Recommended first attempt:** Option 4 — reproduce locally before
fixing. The local 5-doc spike is too small to surface the bug; a
15-30 doc spike with realistic WeChat content (or a fixture-
captured production batch) will both prove reproducibility AND
provide a regression test for whichever fix the user chooses. If
Option 4 reproduces RED, Option 1 becomes the safest first fix
(smallest LOC + most localized blast radius).

**Fix is the user's call, post-decision.** This investigation
deliberately does not commit to a fix path.

---

## 6. Open questions

1. **Does `finalize_storages` itself await all background tasks, or only
   flush in-memory caches?** The local `Successfully finalized 12 storages`
   log line at finalize is 0.0s, but production's 21-min gap suggests it
   either spawns or awaits something heavy. Reading
   `lightrag.LightRAG.finalize_storages` source would resolve this.

2. **What is the actual concurrency level of the production cron loop?**
   `batch_ingest_from_spider.py` — N=1 sequential per article? N>1 via
   asyncio gather? A single `pipeline_status` shared across articles? The
   bug shape (4 ok / 1-2 processed) is consistent with concurrent ainserts
   racing on the same `kv_store_doc_status.json` write, but that is
   speculation without seeing the loop structure.

3. **Does `gemini-3.1-flash-lite-preview` (test) have materially different
   merge timing from production's actual model setting?** The test used
   `OMNIGRAPH_LLM_MODEL=gemini-3.1-flash-lite-preview`; production model
   per `~/.hermes/.env` may differ. Worth confirming in next quick.

4. **Is the 21-min gap (graphml mtime 09:12 → finalize log 09:33) caused by
   a single huge merge, or by polling-for-completion overhead?** The
   answer determines whether Option 1 (per-article finalize) actually
   helps or just shifts the cost.

5. **Does WeChat-ingestion content (heavy CJK, image-link footnotes, etc.)
   produce entity/relation density that the lorem ipsum + 中文样本 fixture
   in T3b underestimates?** Likely yes — production graph grows by
   thousands of nodes per batch, T3b grows 7 nodes per 5 docs. This
   density gap is the main reason the bug doesn't reproduce locally.
