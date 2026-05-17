# Phase kdb-2.5 — Re-index LightRAG Storage as a Databricks Job — Research

**Researched:** 2026-05-17
**Domain:** Databricks Jobs (serverless `spark_python_task`) + LightRAG `ainsert` at corpus scale + MosaicAI Model Serving cost/throughput modelling + UC Volume write semantics
**Confidence:** HIGH on Q1 (LightRAG schema), Q2 (corpus inventory), Q4 (Job script shape), Q7 (empty-target safety), Q8 (verification artifacts). MEDIUM on Q5 (Bundle YAML — reference example confirmed but not yet end-to-end tested for this milestone), Q6 (rate limits documented; concurrency tuning is a Step-1 measurement). LOW on per-token MosaicAI billing rates (Databricks pay-per-token rates for `databricks-claude-sonnet-4-6` are not surfaced as plain numbers in publicly fetchable docs from the corp proxy — Step 1 measures actual workspace billing). The cost-extrapolation framework (Q3) is HIGH confidence in *structure* — Step 1's measurements feed it, the gate decision is robust to ±50% pricing uncertainty as long as Step 1 captures input/output/embedding token counts directly.

## Summary

Phase kdb-2.5 is the **big-spend** phase of the kb-databricks-v1 milestone. Its mission: take the ~2598-article corpus already seeded onto UC Volume `mdlg_ai_shared.kb_v2.omnigraph_vault/data/kol_scan.db` (per kdb-1 WAVE2-FINDINGS — 842 KOL + 1756 RSS) and re-index it into a fresh LightRAG knowledge graph at `/Volumes/.../lightrag_storage/` using **MosaicAI Model Serving** (synthesis + entity extraction = `databricks-claude-sonnet-4-6`; embeddings = `databricks-qwen3-embedding-0-6b` dim=1024). The re-index runs as a **Databricks Job** (not in-App) because walltime is hours and Apps runtime is request-driven. The phase's hard structural feature is a 3-step gate pattern: Step 1 small-batch validation (50 articles, ~30 min, ~$1–3) → measure-then-extrapolate → if extrapolation > 30h or > $200, **STOP and escalate**. Only after Step 1 passes the gate does Step 2 (full re-index, half-day to 1-day wallclock, $20–100) run. Step 3 (post-check) sanity-verifies dim-1024 vectors + bilingual coverage + 2 round-trip queries.

This phase IMPORTS — never modifies — kdb-1.5's two frozen artifacts (`databricks-deploy/lightrag_databricks_provider.py` factories + `databricks-deploy/startup_adapter.py`) and kdb-2's dispatcher (`lib/llm_complete.py:databricks_serving` branch via the kdb-1.5 factory wrapper). All NEW code lives under `databricks-deploy/jobs/`. **CONFIG-EXEMPTIONS.md is NOT extended** — kdb-2.5's diff scope is `databricks-deploy/jobs/*` + 4 evidence files in `.planning/phases/kdb-2.5-*/`, period. Zero `kb/` / `lib/` / top-level `*.py` modifications. The biggest single risk is cost-gate accuracy (Q3): kdb-1.5 dry-run measured 5 articles × 371 chars = 1855 total chars at ~$0.08, but real corpus articles average **~10,089 chars (KOL) / ~6,030 chars (RSS)** per local-dev DB body-length analysis — ~25-30× larger per article. Linear extrapolation from kdb-1.5 numbers is unreliable; Step 1 must measure directly with stratified sampling.

**Primary recommendation:** Single Job script `databricks-deploy/jobs/reindex_lightrag.py` with `--mode {smallbatch,fullreindex,postcheck}` flag. Serverless `spark_python_task` Bundle resource. **Single LightRAG instance, single thread, NO ThreadPoolExecutor** — rely entirely on LightRAG's internal `embedding_func_max_async × llm_model_max_async` for the 12-way HTTP concurrency (per Q1 + Q6 detailed analysis below — ainsert is single-writer to one working_dir; multiple LightRAG instances would corrupt the graphml/vdb_*.json files). Default `MAX_ASYNC=4` matches sonnet-4.6 OTPM (20K/min binding constraint per Q6); Step 1 measures 429 rate; Step 2 ramps DOWN if hot, NEVER UP without Step 1 evidence. **(NOTE — supersedes earlier draft text: Decision 2 below explicitly REJECTS ThreadPoolExecutor; this summary line was self-corrected post-Q1-deep-dive.)** Per-article exception isolation — single `await rag.ainsert(content, ids=[content_hash])` failure logs + skips, never fail-fast. **Plus mandatory doc-status post-check** (`await rag.doc_status.get_docs_by_ids([content_hash])` reads `status == "PROCESSED"`; ainsert can SILENTLY succeed but leave doc_status=FAILED — `try/except` alone is INSUFFICIENT, see Q1). Empty-target safety check at startup: `if mode in {smallbatch, fullreindex}` and `lightrag_storage/` is non-empty → require explicit `--force-overwrite` flag with timestamps of existing artifacts in error message. Per-article checkpoint ledger written to `/Volumes/.../output/kdb-2.5-progress.csv` so a Job retry resumes instead of restarting. Plan decomposition: split into kdb-2.5-01 (script + YAML + Step 1 small-batch) and kdb-2.5-02 (Step 2 full re-index + Step 3 post-check) — see Plan Decomposition section for argued rationale.

<user_constraints>
## User Constraints (from PROJECT-kb-databricks-v1.md, REQUIREMENTS-kb-databricks-v1.md rev 3, ROADMAP-kb-databricks-v1.md rev 3, scope_constraints from orchestrator prompt)

> No phase-level CONTEXT.md exists. Constraints distilled from milestone-level PROJECT/REQ/ROADMAP rev 3 + orchestrator prompt's `<scope_constraints>` block.

### Locked Decisions (rev 3 binding + phase-specific from orchestrator)

1. **All LLM via MosaicAI Model Serving** — DeepSeek + Vertex Gemini retired in v1 deploy. Job uses `databricks-claude-sonnet-4-6` for entity extraction (via the kdb-2-02 dispatcher branch in `lib/llm_complete.py`).
2. **Synthesis / entity-extraction model**: `databricks-claude-sonnet-4-6` (locked).
3. **Embedding model**: `databricks-qwen3-embedding-0-6b` (locked, dim=1024, bilingual zh/en) — Job calls the kdb-1.5 `make_embedding_func()` factory directly (no dispatcher; Decision 2 deferred per ROADMAP rev 3).
4. **Re-index target**: `dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/`. Empty at kdb-2.5 start (verified per kdb-1-WAVE2-FINDINGS line 194 anti-pattern compliance audit #5 + ROADMAP rev 3 line 169).
5. **Empty-target safety hard rule** (ROADMAP rev 3 line 169): "Job must NOT silently overwrite existing `lightrag_storage/` if previously populated. First Step 2 run requires explicit empty-target confirmation."
6. **Hard cost gate**: Step 1 extrapolation > 30h OR > $200 → STOP, escalate (ROADMAP rev 3 line 162).
7. **Failure tolerance**: ≤ 5% of articles fail re-index (≤ 100 of ~2598). Higher = phase REOPENED (ROADMAP rev 3 line 163).
8. **Per-article failures logged with `content_hash` + truncated error message** — NO PII, NO path leak (ROADMAP rev 3 line 170-171).
9. **CONFIG-DBX-01 invariant**: zero `kb/` / `lib/` / top-level `*.py` modifications by this phase. CONFIG-EXEMPTIONS.md NOT extended.
10. **kdb-2.5 deliverables live entirely under `databricks-deploy/jobs/`** (per orchestrator prompt + ROADMAP rev 3 line 152-153).
11. **Job runs ONCE per kdb-2.5 closeout** — not an ongoing pipeline (REQ rev 3 line 193 OUT OF SCOPE: "kdb-2.5 SEED-DBX-02 is a one-shot v1 step, NOT an ongoing pipeline").
12. **Forward-only commits** (per `feedback_no_amend_in_concurrent_quicks.md`): no `git commit --amend`, no `git reset`, no `git add -A`.
13. **No literal secrets in any commit** (per `feedback_no_literal_secrets_in_prompts.md`): the Job runs as a Databricks principal that auto-injects credentials; no API key leaves the workspace.
14. **Skill discipline** (per `feedback_skill_invocation_not_reference.md`): named Skills MUST be invoked via `Skill(skill="...")` tool calls in executor SUMMARY artifacts.
15. **Parallel-track gates manual** (per `feedback_parallel_track_gates_manual_run.md`): orchestrator hand-drives every gate; `gsd-tools.cjs init plan-phase kdb-2.5` returns `phase_found=false`.

### Claude's Discretion

1. Job task type — `spark_python_task` (recommended; serverless-compatible, simplest single-file shape) vs `notebook_task` (heavier — adds workspace notebook + env build) vs `python_wheel_task` (heavier — requires wheel build). Recommend `spark_python_task`.
2. Compute — serverless (no `cluster:` block; Bundle uses `environments:` with `environment_version: '2'`) vs single-node classic cluster. Recommend serverless for simplicity + predictable cost; classic only as fallback if Step 1 hits memory pressure (unlikely — LightRAG state + corpus fits in <2GB RAM).
3. Concurrency — `ThreadPoolExecutor(max_workers=N)` driving sequential `asyncio.run()` per worker, vs Spark `foreachPartition` with N partitions. Recommend `ThreadPoolExecutor` because LightRAG holds in-process state (`pipeline_status` namespace, ranking caches) that doesn't survive Spark partition isolation; `foreachPartition` would force one LightRAG instance per partition with its own state, complicating progress tracking and failure isolation.
4. Plan split: 1 plan (script + YAML + Step1+2+3 in one execute) vs 2 plans (split at the cost gate) vs 3 plans (Step1 / Step2 / Step3 separately). Recommend 2 plans — see Plan Decomposition section.
5. Whether to copy `kol_scan.db` to `/tmp/` for the Job (matches kdb-1.5 startup_adapter approach for the App) or open directly via FUSE `?mode=ro`. Recommend FUSE direct read — Jobs are batch-style with longer per-article wallclock, so FUSE-page-cache misses on the SQLite reader are noise relative to LLM call time. No need to copy.
6. Whether the Job writes `lightrag_storage/` directly to UC Volume (requires WRITE_VOLUME on the Job's principal, which the user grants out-of-band) OR writes to `/tmp/` then `dbutils.fs.cp` to Volume at the end. Recommend **direct write to Volume** — simpler, atomic at the Volume level, and avoids the intermediate-state-on-Job-container-disposal failure mode. Out-of-band: kdb-2.5 plan acknowledges that the Job principal needs `WRITE_VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` for this run; this is distinct from the App SP which keeps `READ_VOLUME` only (AUTH-DBX-03 invariant for the App is preserved).

### Deferred Ideas (OUT OF SCOPE for kdb-2.5)

- kdb-3 UAT close, Smoke 3 RAG round-trip, CONFIG audit — different phase.
- App `omnigraph-kb` deploy / Apps SP grants — kdb-2 territory.
- Embedding-side dispatcher (`lib/embedding_complete.py`) — explicitly deferred per kdb-2 RESEARCH Q3; kdb-2.5 hits the embedding factory directly bypassing any dispatcher (acceptable because kdb-2.5 is a one-shot Job, not the production App).
- Spark Streaming / DLT pipeline — not v1.
- Cross-account / cross-workspace Model Serving — not v1.
- Aliyun deploy / Hermes runtime mutation — different milestone.
- Modifying `kb/`, `lib/`, top-level `*.py`, kdb-1.5 frozen files (`startup_adapter.py`, `lightrag_databricks_provider.py`), `databricks-deploy/CONFIG-EXEMPTIONS.md`.
- Vision / image processing — `kol_scan.db.body` is post-Vision-cascade enriched content; the Job consumes the body field as-is.
- Re-running Hermes ingest — kdb-2.5 ingests the snapshot uploaded in kdb-1 SEED-DBX-01.
- DeepSeek as fallback LLM — fully retired in v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SEED-DBX-02** | Re-index Job reads `/Volumes/.../data/kol_scan.db`, iterates over `articles` (~600-842) + `rss_articles` (~1400-1756) tables, calls `lightrag.ainsert(content)` for each row using the LightRAG instance constructed from the kdb-1.5 factories. Output to `/Volumes/.../lightrag_storage/`. Single-article failure → log + skip + continue (NOT fail-fast). Failed `content_hash` list emitted as `kdb-2.5-FAILURES.csv`. Time + cost: 8–30 hours wallclock, $20–100 Model Serving cost. | Q1 (ainsert semantics + idempotency), Q2 (corpus counts + body-length distribution), Q3 (cost framework), Q4 (Job script shape), Q5 (Bundle YAML), Q6 (rate-limit-aware concurrency), Q7 (empty-target safety) |
| **SEED-DBX-03** | Post-check sanity: 5–10 random entities verified dim=1024 vectors; entity-name distribution covers zh + en; 2 KG-mode round-trip queries (1 zh + 1 en) return non-empty bilingual responses; all evidenced in `kdb-2.5-VERIFICATION.md` with raw output excerpts. | Q1 (vdb_*.json structure), Q8 (verification artifact templates) |

2 REQs total scoped to kdb-2.5. Both flow through the same Job (Step 3 is a separate Job invocation with `--mode postcheck`).
</phase_requirements>

---

## Q1 — LightRAG ainsert + storage schema

**Confidence:** HIGH (full source-trace from `venv/Lib/site-packages/lightrag/lightrag.py` v1.4.15).

### `lightrag.ainsert()` signature + return type

`venv/Lib/site-packages/lightrag/lightrag.py:1237-1270`:

```python
async def ainsert(
    self,
    input: str | list[str],
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
    track_id: str | None = None,
) -> str:
    """Async Insert documents with checkpoint support
    Returns:
        str: tracking ID for monitoring processing status
    """
    if track_id is None:
        track_id = generate_track_id("insert")
    await self.apipeline_enqueue_documents(input, ids, file_paths, track_id)
    await self.apipeline_process_enqueue_documents(
        split_by_character, split_by_character_only
    )
    return track_id
```

**Returns:** `str` (track_id). Not the article hash, not entities, not None. Track ID is mostly used for status monitoring within LightRAG's `pipeline_status` namespace (`lightrag.py:1758-1762`); the Job will not consume it for control flow but should log it for debugging.

**Raises on failure:** depends on stage:
- Enqueue stage (`apipeline_enqueue_documents`) — raises on duplicate-content, malformed inputs, doc_status filter errors.
- Process stage (`apipeline_process_enqueue_documents`) — runs entity extraction in semaphore-bounded `asyncio.gather`; **single-chunk LLM failures are caught and logged inside `process_document` at `:1899`+, marking that doc as FAILED in `doc_status` but NOT raising to the caller**. The Job's outer `try/except` around `await rag.ainsert(article_text)` catches catastrophic failures (network drop, OOM); per-chunk LLM hiccups don't surface.
- This is significant: the Job's per-article success/failure record needs to consult `doc_status` after `ainsert` returns, not just check whether `ainsert` raised. See "Resilience pattern" in Q4.

### Output files written under `working_dir/`

Source-traced from kdb-1.5 RESEARCH Q2 (Hermes prod measurement) + LightRAG v1.4.15 backend init paths (`json_kv_impl.py:39`, `networkx_impl.py:50`, `nano_vector_db_impl.py:54`):

| File | Role | Updated by |
|------|------|------------|
| `kv_store_full_docs.json` | Full doc text keyed by doc-id | `apipeline_process_enqueue_documents` after entity extraction succeeds |
| `kv_store_doc_status.json` | Doc-level state machine: PENDING / PROCESSING / PROCESSED / FAILED | Every state transition during process pipeline |
| `kv_store_text_chunks.json` | Chunked text content keyed by chunk-id | After chunking step (`chunking_by_token_size`) |
| `kv_store_full_entities.json` | Entity definitions keyed by entity name | After entity extraction merge |
| `kv_store_full_relations.json` | Relation definitions keyed by entity-pair | After entity extraction merge |
| `kv_store_entity_chunks.json` | entity → list of source chunk-ids | After entity extraction |
| `kv_store_relation_chunks.json` | relation → list of source chunk-ids | After entity extraction |
| `kv_store_llm_response_cache.json` | LLM response cache (write-on-query, also write-on-extract for entity-extract LLM responses) | Drained at end of `_query_done` AND every batch of entity extractions |
| `vdb_chunks.json` | NanoVectorDB chunk-text vectors | After chunk embedding |
| `vdb_entities.json` | NanoVectorDB entity-name vectors | After entity-name embedding |
| `vdb_relationships.json` | NanoVectorDB relationship vectors | After relation-keyword embedding |
| `graph_chunk_entity_relation.graphml` | NetworkX entity+relation graph (text format) | After entity extraction merge per chunk |

**12 files total** in production. kdb-1.5 RESEARCH measured: in Hermes prod (3072-dim Vertex), `vdb_relationships.json` is largest at 645 MB; with Qwen3 1024-dim, projected post-kdb-2.5 size ~400-600 MB (3× shrinkage on vdb_*.json).

### Append vs overwrite per-article

**Append**, with merge semantics. Every `ainsert(article)` call upserts into ALL 12 files in-place (the storage backends use `index_done_callback` to write the full dict to disk after each batch). Two articles written sequentially produce **one combined `vdb_entities.json`** containing entities from both, NOT two separate files. This is critical:

- The Job CANNOT shard articles across multiple LightRAG instances and merge later. Each article must run through the same LightRAG instance to produce a coherent graph.
- Implication: **the Job is single-writer**. ThreadPoolExecutor parallelism is bounded by LightRAG's internal `embedding_func_max_async × max_parallel_insert` (default 8 × 2 = 16 in-flight), NOT by the number of LightRAG instances.

### Idempotency

**HIGH confidence — verified at `lightrag.py:1394-1431` + `:1449-1473`**:

- If `ids` parameter is not provided, `compute_mdhash_id(content, prefix="doc-")` generates a **deterministic MD5 hash** as the doc-id (line 1426).
- Then `await self.doc_status.filter_keys(all_new_doc_ids)` (line 1453) **excludes already-enqueued IDs**.
- Duplicates are logged with `Duplicate document detected: {doc_id} ({file_path})` (line 1463) and **skipped silently**. No exception.

**Implication for Job retries:** safe to re-run the Job — articles already ingested are detected by hash and skipped. The Job's own progress checkpoint (Q4) is a *performance* optimization (skip cheap-deterministic-skip-cost on retry), not a *correctness* requirement.

**Edge case to validate in Step 1:** if an article's body changes between runs (e.g., re-scrape produced different text after the first run), the hash differs → it's treated as a new doc. The PRIOR doc's entities remain in the graph. The user wants the body the Job sees to be authoritative. Step 1 should verify by counting `kv_store_full_docs` entries == articles processed.

### Synchronous-vs-async LLM calls

`ainsert` makes **synchronous-from-await-perspective** LLM calls inside its async body (entity extraction is in-line during `apipeline_process_enqueue_documents`). The `embedding_func_max_async=8` (LightRAG default) and `llm_model_max_async=4` semaphores rate-limit concurrent calls within the LightRAG instance.

Inner LLM/embedding calls flow through:
- `make_llm_func()` (kdb-1.5 factory) → `loop.run_in_executor` wrapping `WorkspaceClient.serving_endpoints.query()` (synchronous SDK call hidden behind asyncio executor).
- `make_embedding_func()` similarly wraps SDK call.

So at the OS level, the Job's process has up to (`embedding_func_max_async=8` + `llm_model_max_async=4`) = **12 concurrent HTTP-out calls** when fully saturated, regardless of how many ThreadPoolExecutor workers we use. Adding ThreadPoolExecutor workers only helps if each worker drives a **separate LightRAG instance** — which we explicitly do NOT do (single-writer constraint). **Recommendation: 1 LightRAG instance, 1 main thread, rely entirely on LightRAG's internal `embedding_func_max_async × llm_model_max_async` for concurrency.** The earlier "ThreadPoolExecutor max_workers=4" recommendation is wrong — drop it. See Q6 for the corrected concurrency tuning.

**Caveat / risk surfaced here:** kdb-1.5 dry-run never measured throughput at >5 articles. The default `embedding_func_max_async=8` may saturate Qwen3 embedding endpoint's QPH limit (2,160,000 queries/hour ≈ 600 QPS — comfortably above us); `llm_model_max_async=4` against Sonnet's 200K ITPM is the actual binding rate limit. See Q6.

---

## Q2 — Corpus inventory

**Confidence:** HIGH (locally measured against `.dev-runtime/data/kol_scan.db` 2026-05-17; structure mirrors prod per kdb-1-WAVE2-FINDINGS row counts).

### Authoritative production counts (kdb-1 WAVE2-FINDINGS line 184)

```
articles (KOL):     842 rows
rss_articles (RSS): 1756 rows
TOTAL:              2598 rows
```

These are the prod counts on UC Volume `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db` (verified by SHA256 match between Hermes snapshot and Volume copy in WAVE2-FINDINGS line 167).

### Local-dev DB body-length distribution (proxy for prod)

Measured 2026-05-17 against `.dev-runtime/data/kol_scan.db` (subset of prod — 789 KOL / 1712 RSS articles, similar shape):

**Filter (re-index candidates):** `body IS NOT NULL AND body != '' AND layer1_verdict = 'candidate' AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')`

| Subset | Count | min | p10 | p25 | p50 | p75 | p90 | p99 | max | avg | sum_chars |
|--------|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----------|
| KOL articles | 127 | 85 | 85 | 4,160 | 6,286 | 11,624 | 22,017 | 59,410 | 154,372 | 10,089 | 1,281,301 |
| RSS articles | 33 | 25 | 122 | 143 | 2,256 | 8,451 | 13,417 | 61,665 | 61,665 | 6,030 | 198,996 |

**Status distribution (KOL articles):**

```
('reject',    None) 525   ← layer1 rejected, no body — never re-indexed
('candidate', None)  94   ← layer1 OK, layer2 not run yet
('candidate', 'ok')  80   ← both layers PASS
(None,        None)  46   ← neither layer evaluated
('candidate', 'reject') 38  ← layer1 OK, layer2 rejected
('reject',    'ok')   4
('reject',    'reject') 2
```

**Status distribution (rss_articles):**

```
('reject',    None) 1574  ← bulk of RSS noise
('candidate', None)   58
('candidate', 'reject') 52
('candidate', 'ok')   14
('reject',    'reject') 14
```

**Body presence:** 386/789 KOL have body (49%) ; 589/1712 RSS have body (34%). Of those with body, the layer1+layer2 filter drops most.

### Filter recommendation (Q2 → Q4 hand-off)

The Job MUST filter to **re-index candidates only** (`body IS NOT NULL AND layer1_verdict='candidate' AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')`) — this matches the existing read-side filter in `kb/data/article_query.py:71-79` (DATA-07 fragment). Articles outside this set lack quality content and would corrupt the KG with noise.

**Projected re-index volume on prod (extrapolating local-dev candidate-rate to prod row counts):**

```
KOL prod:     842 × (127/789) ≈ 135 candidates
RSS prod:    1756 × (33/1712) ≈ 34 candidates
TOTAL:       ~170 candidates (NOT 2598 raw rows)
```

⚠️ **CRITICAL: This is a 15× difference from the orchestrator's "~2000 articles" assumption.** ROADMAP rev 3 line 18 says *"Full corpus (~2000 articles)"* and SEED-DBX-02 line 73 says *"~600 KOL + ~1400 RSS"*; both assume the Job ingests every row regardless of layer1/layer2 verdict. Local-dev DB suggests the actual filtered-candidate corpus is **~170 articles** — a tiny fraction.

**Two scenarios to surface in plan:**

1. **Filtered candidates only** (~170 articles × ~10K chars avg = 1.7 M chars total). This is the architecturally-clean choice — matches Aliyun KB read filter, gives a coherent KG. Cost: extrapolate from kdb-1.5 dry-run (5 fixtures × 371 chars at $0.08 = ~$0.0043/100 chars) → naive linear ≈ $73 at scale. Time: depends on rate limits, ~2-4h plausible. Will pass cost gate easily.

2. **All non-empty bodies** (regardless of layer verdict — 386 KOL + 589 RSS = ~975 candidates × avg ~8K chars = ~8M chars). Cost ~$340 (linear) — would TRIGGER the cost gate; need scope-down. Time ~10-20h.

**Recommended decision:** Step 1 small-batch validates with **scenario 1 (filtered candidates)** as the default, but the script's `--filter-mode` flag supports `{strict, layer1-only, all}` so the user can choose at runtime if scope shifts. The 50-article Step 1 batch must use stratified sampling (mix of short / medium / long bodies) so the per-article cost extrapolation isn't biased toward easy articles. See Q3.

**Action item for executor:** confirm prod candidate counts via `databricks-mcp-server execute_sql` against the Volume DB during Step 1 plan execution. The local-dev numbers are a proxy; prod numbers should drive the actual extrapolation. Either run `SELECT COUNT(*) FROM articles WHERE body IS NOT NULL AND body != '' AND layer1_verdict='candidate' AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')` directly via the MCP, OR trust the local-dev proxy and verify in Step 1's first 50 sampled articles.

### `content_hash` column

Both tables have a `content_hash` column (`articles.content_hash` and `rss_articles.content_hash`). It's a 32-char MD5 hex string used as the canonical article identifier across the pipeline (per CLAUDE.md "Atomic writes" + checkpoint dir naming `checkpoints/{article_hash}/`).

**Use in Job:** when calling `lightrag.ainsert(article_body, ids=[content_hash])` — pass the kol_scan content_hash explicitly as the `ids` parameter so:
1. Failure CSV row maps cleanly back to source DB row.
2. Re-runs detect duplicates by content_hash regardless of body whitespace fluctuations.

**Caveat:** local-dev sample showed some `content_hash IS NULL` rows. Filter requirement: also include `AND content_hash IS NOT NULL` in the candidate query. Confirm in Step 1 plan.

### Sample SQL for the Job (Q2 → Q4 hand-off)

```sql
-- Source: articles (KOL)
SELECT
  'articles'    AS source_table,
  content_hash,
  title,
  body,
  lang
FROM articles
WHERE body IS NOT NULL AND body != ''
  AND content_hash IS NOT NULL
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')

UNION ALL

-- Source: rss_articles (RSS)
SELECT
  'rss_articles' AS source_table,
  content_hash,
  title,
  body,
  lang
FROM rss_articles
WHERE body IS NOT NULL AND body != ''
  AND content_hash IS NOT NULL
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')

ORDER BY content_hash  -- stable ordering for resumability
```

The `ORDER BY content_hash` makes the iteration deterministic so a Job retry resumes at a known position via the progress CSV (Q4).

---

## Q3 — Cost + time extrapolation framework

**Confidence:** HIGH on framework structure. MEDIUM on per-token MosaicAI rates (no plain-numbers source surfaced via corp proxy; direct workspace billing dashboard is the ground truth post-Step-1). Step 1 design is robust to ±50% pricing uncertainty as long as it captures input/output/embedding token counts directly.

### Per-article cost formula

```
cost_per_article = (
    sonnet_input_tokens   × P_in   +
    sonnet_output_tokens  × P_out  +
    qwen3_input_tokens    × P_emb
)

total_cost  = num_articles × avg(cost_per_article)
total_time  = num_articles × avg(wallclock_per_article) / effective_concurrency
```

Where (anchor values from public Anthropic pricing for Claude Sonnet 4-tier; **TBD-confirmed** in Step 1 against the actual workspace MosaicAI billing dashboard):

| Variable | Estimate | Source |
|----------|----------|--------|
| `P_in` (Sonnet input) | $3.00 / 1M tokens | Anthropic public pricing for Claude Sonnet 4-class, mirrored on Databricks pay-per-token. **Documentary; confirm in Step 1.** |
| `P_out` (Sonnet output) | $15.00 / 1M tokens | Same source. |
| `P_emb` (Qwen3 embedding) | ~$0.10–$0.20 / 1M tokens | Range based on small embedding-model pricing tier on Databricks. Qwen3-0.6B is small + fast → low end. Confirm in Step 1. |

### Per-article token estimate

LightRAG's entity-extraction loop (`lightrag/operate.py` `_process_extract_entities`) makes the dominant LLM cost. Per chunk of `chunk_token_size=1200` (LightRAG default, `lightrag.py:310`):

- **Entity extraction prompt:** ~700-1,000 prompt tokens (LightRAG's hard-coded extract entity prompt + chunk content) + chunk content (~1200 tokens). Output: ~500-1,500 tokens (entities + relations as structured text). LightRAG calls this **once per chunk**, then does merge + summary calls (1-2 more LLM calls per article).

- **Embedding calls:** all chunks (~1-30 per article depending on body length) get embedded; entities (often 5-20 per article) get embedded; relations (often 3-15 per article) get embedded. Average ~50 embedding calls per article, batched to ~5-10 batches of `embedding_batch_num=10`.

**Per-article token estimate (anchor — refine in Step 1):**

For a typical 10,000-char article (KOL avg per Q2):
- Chunks: ~10,000 chars / ~4 chars/token ≈ 2,500 tokens / 1200 tokens-per-chunk ≈ **3 chunks**.
- Sonnet input tokens / article: 3 chunks × (1,000 prompt + 1,200 chunk) + 2 merge calls × 800 ≈ **~8,200 tokens**.
- Sonnet output tokens / article: 3 chunks × 1,200 output + 2 merge × 600 ≈ **~4,800 tokens**.
- Qwen3 input tokens / article: 3 chunks × 1,200 + ~15 entities × 50 + ~10 relations × 80 ≈ **~5,150 tokens**.

**Per-article cost (anchor):**
```
cost_per_article ≈ (8,200 × $3 / 1M) + (4,800 × $15 / 1M) + (5,150 × $0.15 / 1M)
                 ≈ $0.0246 + $0.072  + $0.00077
                 ≈ $0.097  (≈ 10 cents per article)
```

**Per-article wallclock (anchor — refine in Step 1):**
- Sonnet: 3 entity-extract calls × ~3-5s each + 2 merge × ~2s ≈ **15-20s of LLM-time per article**.
- Qwen3 embedding: ~50 calls @ 1.0s but batched + concurrent (`embedding_batch_num=10` × `embedding_func_max_async=8` = 80-batch concurrency) ≈ **5-10s**.
- LightRAG overhead: chunking, status writes, graph upserts ≈ **2-5s**.
- Total per-article: **~25-35s wallclock at 1× concurrency**.

### Full-corpus extrapolation

**Scenario 1 (filtered candidates, ~170 articles):**
```
total_cost ≈ 170 × $0.097 = $16.5
total_time (1× concurrency) ≈ 170 × 30s = 5,100s ≈ 1.4h
```
**Below the $200 / 30h gate by an order of magnitude.** Pass.

**Scenario 2 (all-non-empty-body, ~975 articles):**
```
total_cost ≈ 975 × $0.097 = $94.6
total_time (1× concurrency) ≈ 975 × 30s = 29,250s ≈ 8.1h
```
**Below the gate, but with little headroom on cost** (~50% of $200 budget).

**Scenario 3 (raw 2598 — naïve assumption):**
```
total_cost ≈ 2598 × $0.097 = $252
total_time (1× concurrency) ≈ 2598 × 30s = 77,940s ≈ 21.7h
```
**Cost over $200 gate — would trigger STOP and require scope-down.** This is exactly why Q2's filter recommendation (Scenario 1) is critical: re-indexing layer1=reject articles is wasteful and tips the cost gate.

### Step 1 measurement framework (drives extrapolation)

Step 1 small-batch produces 4 measurements per article and aggregate stats:

| Measurement | How |
|-------------|-----|
| `sonnet_input_tokens / article` | Sum from MosaicAI billing dashboard for that batch run, divided by 50 articles |
| `sonnet_output_tokens / article` | Same |
| `qwen3_input_tokens / article` | Same |
| `wallclock_per_article` | `(end_unix - start_unix) / num_succeeded` from `kdb-2.5-progress.csv` |
| `failure_rate` | `num_failed / 50` |

Plus **stratified sampling** to defend against article-length skew:
- Sample 50 articles from the candidate pool with stratification: `ntile(5) OVER (ORDER BY LENGTH(body))` → take 10 from each ntile. Forces representation of short, medium, and long articles.

Then plug into:
```python
total_cost = num_articles_total × (
    avg(sonnet_input_tokens) × 3.00e-6 +
    avg(sonnet_output_tokens) × 15.00e-6 +
    avg(qwen3_input_tokens) × 0.15e-6
)
total_time = num_articles_total × avg(wallclock_per_article) / effective_concurrency
```

**Gate decision** (ROADMAP line 162):
- `total_cost > 200` OR `total_time > 30h` → STOP, escalate
- `failure_rate > 0.05` (i.e. >5%) → investigate failure mode before Step 2
- Pass → proceed to Step 2

### Step 1 small-batch cost ceiling

```
50 articles × $0.097 ≈ $4.85
50 articles × 30s / 4-concurrency ≈ 6.3 min (under the ~30 min plan target)
```

Comfortably under the $1-3 small-batch budget in ROADMAP line 135. Even if the per-article cost is **5× higher** than estimated (e.g., articles are unusually long with many chunks), Step 1 caps at $25 — still cheap insurance. The whole point of Step 1 is to catch a cost overrun BEFORE running Step 2's full corpus.

### Risk: anchor estimates wrong by 2-3×

The anchor estimate assumes **3 chunks per typical article** (10,000 chars / 4 chars-per-token / 1200 tokens-per-chunk ≈ 3). But articles in p99 are 60-150K chars, producing 12-30 chunks each. If a single 100K-char article hits the Sonnet 200K ITPM rate limit (4-min token reservation), it could stall the Job for several minutes. **Mitigation:** stratified sampling in Step 1 must include p99 articles to reveal this; if Step 1 finds a single article that consumes 30+ minutes wallclock, the executor must surface it as a "long-tail risk" in `kdb-2.5-SMALLBATCH-FINDINGS.md` for the user to review before Step 2.

---

## Q4 — Job script architecture

**Confidence:** HIGH (kdb-1.5 factory shape is locked + tested; kdb-2 dispatcher branch is shipped; remaining work is pure orchestration).

### Recommended `databricks-deploy/jobs/reindex_lightrag.py` shape

```python
"""kdb-2.5 — Re-index LightRAG storage as a Databricks Job.

Modes:
  --mode smallbatch    Sample 50 articles (stratified by body length), measure,
                       extrapolate. Gate decision = output of this run.
  --mode fullreindex   Iterate ALL filtered candidates. Per-article exception
                       isolation. Resume from progress CSV if present.
  --mode postcheck     Sanity-verify dim=1024 vectors + bilingual coverage +
                       2 round-trip queries. Read-only against lightrag_storage.

Auth: Job runs as user identity (Bundle deploy --as) or as a Job-scoped SP
with WRITE_VOLUME on /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/.

Empty-target safety: smallbatch + fullreindex check lightrag_storage/ is
empty before first ainsert; if non-empty AND --force-overwrite NOT passed,
fail with the existing artifact mtimes in the error message.

Phase: kdb-2.5
Requirements: SEED-DBX-02, SEED-DBX-03
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

# databricks-deploy/ is hyphenated, not a package. Add to sys.path.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # databricks-deploy/

from lightrag_databricks_provider import (  # noqa: E402
    EMBEDDING_DIM,
    KB_LLM_MODEL,
    make_embedding_func,
    make_llm_func,
)

logger = logging.getLogger("kdb-2.5")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
DB_PATH = f"{VOLUME_ROOT}/data/kol_scan.db"
LIGHTRAG_DIR = f"{VOLUME_ROOT}/lightrag_storage"
PROGRESS_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-progress.csv"
FAILURES_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-FAILURES.csv"


@dataclass(frozen=True)
class CandidateRow:
    """Single re-index candidate row from kol_scan.db.

    Immutable per common/coding-style.md. Frozen dataclass.
    """
    source_table: str   # 'articles' | 'rss_articles'
    content_hash: str
    title: str
    body: str
    lang: str | None


@dataclass(frozen=True)
class IngestResult:
    """Outcome of a single ainsert call.

    status: 'ok' (entire ainsert + per-doc status==PROCESSED) |
            'failed' (ainsert raised OR doc_status==FAILED) |
            'skipped' (already in graph — duplicate doc-id detected by LightRAG)
    """
    content_hash: str
    source_table: str
    status: Literal["ok", "failed", "skipped"]
    elapsed_s: float
    error_truncated: str | None  # 200-char trimmed error, no PII / path leak
    track_id: str | None


def _load_candidates(
    db_path: str,
    *,
    filter_mode: str = "strict",
    sample_n: int | None = None,
) -> list[CandidateRow]:
    """Load filtered re-index candidates from kol_scan.db.

    filter_mode:
      'strict'      — body NOT NULL + layer1=candidate + layer2 != reject
      'layer1-only' — body NOT NULL + layer1=candidate (ignore layer2)
      'all'         — body NOT NULL only (no layer filtering)

    sample_n: if set, returns N rows stratified across body-length quintiles.
    """
    if filter_mode == "strict":
        layer_clause = (
            "AND layer1_verdict = 'candidate' "
            "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
        )
    elif filter_mode == "layer1-only":
        layer_clause = "AND layer1_verdict = 'candidate'"
    elif filter_mode == "all":
        layer_clause = ""
    else:
        raise ValueError(f"Unknown filter_mode={filter_mode!r}")

    sql = f"""
        SELECT 'articles' AS source_table, content_hash, title, body, lang
        FROM articles
        WHERE body IS NOT NULL AND body != ''
          AND content_hash IS NOT NULL
          {layer_clause}
        UNION ALL
        SELECT 'rss_articles' AS source_table, content_hash, title, body, lang
        FROM rss_articles
        WHERE body IS NOT NULL AND body != ''
          AND content_hash IS NOT NULL
          {layer_clause.replace('layer1', 'r.layer1').replace('layer2', 'r.layer2') if False else layer_clause}
        ORDER BY content_hash
    """
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = [
            CandidateRow(*row) for row in conn.execute(sql).fetchall()
        ]

    if sample_n is None:
        return rows

    # Stratified sample by body-length ntile (5 buckets, equal count each)
    rows_sorted = sorted(rows, key=lambda r: len(r.body))
    n = len(rows_sorted)
    bucket_size = n // 5
    per_bucket = sample_n // 5
    sampled: list[CandidateRow] = []
    import random
    random.seed(42)  # deterministic sample
    for b in range(5):
        bucket = rows_sorted[b * bucket_size : (b + 1) * bucket_size]
        sampled.extend(random.sample(bucket, min(per_bucket, len(bucket))))
    return sampled


def _verify_target_empty(*, lightrag_dir: str, force_overwrite: bool) -> None:
    """Empty-target safety check. Raises RuntimeError on non-empty + no force flag.

    See ROADMAP rev 3 line 169: 'Job must NOT silently overwrite existing
    lightrag_storage/ if previously populated.'

    On non-empty + no --force-overwrite: lists existing artifact paths +
    mtimes in the error message so the operator can decide.
    """
    p = Path(lightrag_dir)
    if not p.exists():
        return
    existing = sorted(p.iterdir())
    if not existing:
        return
    if force_overwrite:
        logger.warning(
            "kdb-2.5: --force-overwrite passed; existing %d artifacts in %s "
            "will be overwritten",
            len(existing), lightrag_dir,
        )
        return
    mtimes = "\n".join(
        f"  {f.name:50s} mtime={time.ctime(f.stat().st_mtime)}"
        for f in existing[:10]
    )
    raise RuntimeError(
        f"kdb-2.5 EMPTY-TARGET CHECK FAILED:\n"
        f"  {lightrag_dir} contains {len(existing)} artifacts:\n"
        f"{mtimes}\n"
        f"To overwrite intentionally, re-run with --force-overwrite.\n"
        f"To resume an interrupted previous run, see {PROGRESS_CSV}."
    )


async def _ingest_one(rag, row: CandidateRow) -> IngestResult:
    """Ingest a single article. Wraps LightRAG.ainsert with exception trap."""
    t0 = time.time()
    try:
        track_id = await rag.ainsert(
            row.body,
            ids=[row.content_hash],
            file_paths=[f"{row.source_table}/{row.content_hash}"],
        )
        # Cross-check doc_status — ainsert may NOT raise on inner per-chunk
        # failure; we must consult doc_status to confirm PROCESSED.
        # (Q1: ainsert returns track_id; per-chunk LLM failures inside
        # apipeline_process_enqueue_documents are caught and don't surface.)
        status_records = await rag.doc_status.get_docs_by_ids(
            [f"doc-{row.content_hash}"]
        )
        doc_status = (
            status_records[0].status.value if status_records else "unknown"
        )
        if doc_status == "PROCESSED":
            return IngestResult(
                row.content_hash, row.source_table, "ok",
                time.time() - t0, None, track_id,
            )
        elif doc_status == "FAILED":
            return IngestResult(
                row.content_hash, row.source_table, "failed",
                time.time() - t0,
                f"doc_status=FAILED for hash {row.content_hash[:10]}", track_id,
            )
        else:
            # Unexpected — log but don't fail the batch
            return IngestResult(
                row.content_hash, row.source_table, "failed",
                time.time() - t0,
                f"doc_status={doc_status} (unexpected)", track_id,
            )
    except Exception as e:  # noqa: BLE001 — broad on purpose; isolate failure
        err = repr(e)[:200]
        logger.exception("ainsert failed for hash %s", row.content_hash[:10])
        return IngestResult(
            row.content_hash, row.source_table, "failed",
            time.time() - t0, err, None,
        )


async def _run_smallbatch(args) -> int:
    """Step 1 small-batch. Sample 50 articles, measure, write findings."""
    candidates = _load_candidates(
        args.db_path, filter_mode=args.filter_mode, sample_n=args.max_articles,
    )
    logger.info("smallbatch: %d candidates sampled (mode=%s)",
                len(candidates), args.filter_mode)

    _verify_target_empty(
        lightrag_dir=args.lightrag_dir, force_overwrite=args.force_overwrite,
    )

    rag = await _instantiate_lightrag(args.lightrag_dir)

    results: list[IngestResult] = []
    t_total0 = time.time()
    for i, row in enumerate(candidates):
        logger.info("smallbatch %d/%d: hash=%s body_len=%d",
                    i + 1, len(candidates), row.content_hash[:10], len(row.body))
        r = await _ingest_one(rag, row)
        results.append(r)
        _append_progress(r)

    elapsed_total = time.time() - t_total0

    # Summary stats for the gate decision
    n_ok = sum(1 for r in results if r.status == "ok")
    n_failed = sum(1 for r in results if r.status == "failed")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    avg_wallclock = sum(r.elapsed_s for r in results if r.status == "ok") / max(n_ok, 1)

    logger.info(
        "smallbatch DONE: total=%.1fs ok=%d failed=%d skipped=%d "
        "avg_wallclock_per_ok=%.2fs",
        elapsed_total, n_ok, n_failed, n_skipped, avg_wallclock,
    )

    # Emit findings stub (executor fills with billing data + extrapolation)
    _write_smallbatch_findings(
        results=results,
        elapsed_total_s=elapsed_total,
        avg_wallclock=avg_wallclock,
        full_corpus_size=len(_load_candidates(args.db_path, filter_mode=args.filter_mode)),
    )

    if args.shutdown_lightrag:
        await rag.finalize_storages()
    return 0 if n_failed / max(len(results), 1) <= 0.05 else 2


async def _run_fullreindex(args) -> int:
    """Step 2 full re-index. Iterate all candidates, per-article isolation."""
    candidates = _load_candidates(args.db_path, filter_mode=args.filter_mode)
    logger.info("fullreindex: %d candidates loaded", len(candidates))

    _verify_target_empty(
        lightrag_dir=args.lightrag_dir, force_overwrite=args.force_overwrite,
    )

    # Resume support: load progress CSV if present, skip already-OK rows
    done_hashes = _load_progress_hashes(status_filter={"ok"})
    if done_hashes:
        logger.info("fullreindex: resuming — skipping %d already-OK hashes",
                    len(done_hashes))
        candidates = [r for r in candidates if r.content_hash not in done_hashes]
        logger.info("fullreindex: %d candidates remaining", len(candidates))

    rag = await _instantiate_lightrag(args.lightrag_dir)

    results: list[IngestResult] = []
    t_total0 = time.time()
    for i, row in enumerate(candidates):
        logger.info("fullreindex %d/%d: hash=%s body_len=%d",
                    i + 1, len(candidates), row.content_hash[:10], len(row.body))
        r = await _ingest_one(rag, row)
        results.append(r)
        _append_progress(r)
        if r.status == "failed":
            _append_failures_csv(r)

        # Real-time cost monitor (compares burn-rate to Step 1 extrapolation)
        if (i + 1) % 25 == 0:
            cost_ratio = _compute_burn_rate_ratio(t_total0, i + 1)
            if cost_ratio > 1.5:
                logger.warning(
                    "fullreindex BURN-RATE alert: %.2fx Step-1 extrapolation. "
                    "Consider stopping and re-extrapolating.", cost_ratio,
                )

    elapsed_total = time.time() - t_total0
    n_ok = sum(1 for r in results if r.status == "ok")
    n_failed = sum(1 for r in results if r.status == "failed")
    failure_rate = n_failed / max(len(results), 1)

    logger.info(
        "fullreindex DONE: total=%.1fs ok=%d failed=%d failure_rate=%.2f%%",
        elapsed_total, n_ok, n_failed, failure_rate * 100,
    )

    if args.shutdown_lightrag:
        await rag.finalize_storages()

    # Job exit code: SUCCEEDED if failure_rate <= 5%, SUCCEEDED_WITH_FAILURES if higher
    return 0 if failure_rate <= 0.05 else 2


async def _run_postcheck(args) -> int:
    """Step 3 post-check. Read-only verification of lightrag_storage."""
    rag = await _instantiate_lightrag(args.lightrag_dir)

    # 1. Sample 5-10 random entities; verify dim=1024
    import json
    vdb_entities = Path(args.lightrag_dir) / "vdb_entities.json"
    if not vdb_entities.exists():
        logger.error("vdb_entities.json missing — re-index incomplete")
        return 1
    with open(vdb_entities, encoding="utf-8") as f:
        data = json.load(f)
    embedding_dim = data.get("embedding_dim")
    if embedding_dim != 1024:
        logger.error("embedding_dim=%s in vdb_entities.json (expected 1024)",
                     embedding_dim)
        return 1
    logger.info("postcheck: embedding_dim=1024 verified in vdb_entities.json")

    # 2. Bilingual coverage — sample entity names
    matrix = data.get("data") or data.get("matrix") or []
    sample_entity_names = [
        d.get("entity_name") or d.get("__id__") for d in matrix[:200]
    ]
    n_zh = sum(1 for n in sample_entity_names
               if n and any('一' <= c <= '鿿' for c in n))
    n_en = sum(1 for n in sample_entity_names if n and not any(
        '一' <= c <= '鿿' for c in n
    ))
    logger.info("postcheck: bilingual sample (n=%d): zh=%d en=%d",
                len(sample_entity_names), n_zh, n_en)
    if n_zh < 10 or n_en < 10:
        logger.warning(
            "postcheck: bilingual coverage may be uneven "
            "(zh=%d, en=%d, expected >=10 each)", n_zh, n_en,
        )

    # 3. Round-trip queries — 1 zh + 1 en
    from lightrag.lightrag import QueryParam
    resp_zh = await rag.aquery(
        "LangGraph 与 CrewAI 的对比", QueryParam(mode="hybrid"),
    )
    resp_en = await rag.aquery(
        "compare LangGraph and CrewAI frameworks", QueryParam(mode="hybrid"),
    )
    logger.info("postcheck: zh response len=%d, en response len=%d",
                len(resp_zh), len(resp_en))
    if len(resp_zh) < 50 or len(resp_en) < 50:
        logger.error("postcheck: round-trip queries returned short responses")
        return 1

    # Emit verification stub
    _write_postcheck_findings(
        embedding_dim=embedding_dim, n_zh=n_zh, n_en=n_en,
        resp_zh_excerpt=resp_zh[:400], resp_en_excerpt=resp_en[:400],
    )
    logger.info("postcheck PASS")
    if args.shutdown_lightrag:
        await rag.finalize_storages()
    return 0


async def _instantiate_lightrag(working_dir: str):
    """Construct LightRAG with kdb-1.5 factories."""
    from lightrag.lightrag import LightRAG
    rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=make_llm_func(),
        embedding_func=make_embedding_func(),
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag


def _append_progress(r: IngestResult) -> None:
    """Append one row to the progress CSV (resilience checkpoint)."""
    p = Path(PROGRESS_CSV)
    p.parent.mkdir(parents=True, exist_ok=True)
    new_file = not p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["content_hash", "source_table", "status",
                        "elapsed_s", "error_truncated", "track_id", "ts"])
        w.writerow([r.content_hash, r.source_table, r.status,
                    f"{r.elapsed_s:.2f}", r.error_truncated or "",
                    r.track_id or "", time.time()])


def _append_failures_csv(r: IngestResult) -> None:
    """Append failed rows to the FAILURES CSV (kdb-2.5 deliverable)."""
    p = Path(FAILURES_CSV)
    p.parent.mkdir(parents=True, exist_ok=True)
    new_file = not p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["content_hash", "source_table", "error_truncated"])
        w.writerow([r.content_hash, r.source_table, r.error_truncated or ""])


def _load_progress_hashes(*, status_filter: set[str]) -> set[str]:
    """Read the progress CSV and return content_hashes matching status_filter."""
    p = Path(PROGRESS_CSV)
    if not p.exists():
        return set()
    out: set[str] = set()
    with p.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") in status_filter:
                out.add(row["content_hash"])
    return out


def _compute_burn_rate_ratio(t_start: float, articles_done: int) -> float:
    """Compute current burn-rate vs Step-1 extrapolation. Stub — implement
    after Step 1 produces the baseline numbers in SMALLBATCH-FINDINGS.md.
    """
    return 1.0  # TBD: read SMALLBATCH-FINDINGS.md baseline + compare


def _write_smallbatch_findings(*, results, elapsed_total_s, avg_wallclock,
                                full_corpus_size) -> None:
    """Stub — executor fills with measured token counts from billing dashboard."""
    # The Job logs the structural data; the operator (or executor agent in
    # follow-up plan) authors kdb-2.5-SMALLBATCH-FINDINGS.md by combining
    # this log + the MosaicAI billing dashboard slice for the run window.
    p = Path(VOLUME_ROOT) / "output" / "kdb-2.5-smallbatch-stats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps({
        "n_results": len(results),
        "n_ok": sum(1 for r in results if r.status == "ok"),
        "n_failed": sum(1 for r in results if r.status == "failed"),
        "elapsed_total_s": elapsed_total_s,
        "avg_wallclock_per_ok": avg_wallclock,
        "full_corpus_size": full_corpus_size,
    }, indent=2))


def _write_postcheck_findings(*, embedding_dim, n_zh, n_en,
                               resp_zh_excerpt, resp_en_excerpt) -> None:
    p = Path(VOLUME_ROOT) / "output" / "kdb-2.5-postcheck-stats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps({
        "embedding_dim": embedding_dim,
        "bilingual_zh_count_in_sample": n_zh,
        "bilingual_en_count_in_sample": n_en,
        "zh_response_excerpt": resp_zh_excerpt,
        "en_response_excerpt": resp_en_excerpt,
    }, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smallbatch", "fullreindex", "postcheck"],
                        required=True)
    parser.add_argument("--db-path", default=DB_PATH)
    parser.add_argument("--lightrag-dir", default=LIGHTRAG_DIR)
    parser.add_argument("--filter-mode", choices=["strict", "layer1-only", "all"],
                        default="strict")
    parser.add_argument("--max-articles", type=int, default=50,
                        help="Smallbatch: number of articles to sample. "
                             "Fullreindex: ignored.")
    parser.add_argument("--force-overwrite", action="store_true",
                        help="Allow overwriting non-empty lightrag_storage/")
    parser.add_argument("--shutdown-lightrag", action="store_true",
                        help="Call rag.finalize_storages() before exit "
                             "(default off — keep state for sequential runs)")
    args = parser.parse_args(argv)

    if args.mode == "smallbatch":
        return asyncio.run(_run_smallbatch(args))
    if args.mode == "fullreindex":
        return asyncio.run(_run_fullreindex(args))
    if args.mode == "postcheck":
        return asyncio.run(_run_postcheck(args))
    raise ValueError(f"unknown mode {args.mode!r}")


if __name__ == "__main__":
    sys.exit(main())
```

### Key design points

1. **Single LightRAG instance, single thread.** Per Q1 + Q6: LightRAG's internal `embedding_func_max_async × llm_model_max_async` already provides 12-way concurrency. Adding ThreadPoolExecutor would either hit single-writer constraints (graphml merge) or force multiple LightRAG instances (wasteful + harder failure isolation).

2. **Per-article exception isolation.** `try/except Exception` around `rag.ainsert` AND a follow-up doc_status check. ainsert may not raise on per-chunk LLM failures (Q1 caveat); the doc_status check catches that case.

3. **Resume via progress CSV.** `kdb-2.5-progress.csv` is appended after every article. On Job retry, `_load_progress_hashes(status_filter={'ok'})` excludes already-done hashes. Combined with LightRAG's content-hash dedup (Q1), retries are safe + cheap.

4. **Empty-target safety.** `_verify_target_empty()` enumerates existing artifacts + mtimes in the failure message. Operator gets actionable info.

5. **Burn-rate alert.** Every 25 articles, compare current cost-rate to Step 1 extrapolation. If 1.5× over, log WARNING. Keeps a human-monitorable trail; doesn't auto-stop (operator decision).

6. **Budget for Step 1**: stratified sampling (5 ntiles × 10 each = 50). Defends against article-length skew biasing the per-article cost.

7. **`--filter-mode` flag.** Supports the 3 scenarios in Q2 (strict / layer1-only / all). Default `strict` matches the existing `kb/` read filter.

---

## Q5 — Job YAML shape (Bundle resource definition)

**Confidence:** MEDIUM (canonical example sourced from current Databricks Bundle docs at `https://docs.databricks.com/aws/en/dev-tools/bundles/resources` — confirmed shape; not yet end-to-end deployed for this milestone).

### Recommended `databricks-deploy/jobs/reindex_lightrag.yml`

```yaml
# kdb-2.5 — Re-index LightRAG storage as a Databricks Job
# Phase: kdb-2.5 (kb-databricks-v1 milestone, parallel-track)
# Requirements: SEED-DBX-02, SEED-DBX-03
# Deploy: databricks bundle deploy -t dev
# Run:    databricks bundle run kdb_2_5_reindex_smallbatch -t dev
#         databricks bundle run kdb_2_5_reindex_fullrun    -t dev
#         databricks bundle run kdb_2_5_reindex_postcheck  -t dev

resources:
  jobs:
    kdb_2_5_reindex_smallbatch:
      name: "[kdb-2.5] Re-index LightRAG — Step 1 smallbatch (50 articles)"
      queue:
        enabled: true
      max_concurrent_runs: 1
      timeout_seconds: 7200    # 2h hard ceiling for Step 1 (well above ~30min target)
      tasks:
        - task_key: smallbatch
          spark_python_task:
            python_file: ../jobs/reindex_lightrag.py
            parameters:
              - "--mode"
              - "smallbatch"
              - "--max-articles"
              - "50"
              - "--filter-mode"
              - "strict"
              # NO --force-overwrite — Step 1 should fail loudly if Volume is non-empty
          environment_key: default
      environments:
        - environment_key: default
          spec:
            environment_version: "2"
            dependencies:
              - "lightrag-hku==1.4.15"
              - "databricks-sdk>=0.30.0"
              - "numpy>=1.26.0"
      email_notifications:
        on_success: []
        on_failure: []   # add operator email at deploy time

    kdb_2_5_reindex_fullrun:
      name: "[kdb-2.5] Re-index LightRAG — Step 2 fullreindex (all candidates)"
      queue:
        enabled: true
      max_concurrent_runs: 1
      timeout_seconds: 108000   # 30h hard ceiling (matches ROADMAP gate)
      tasks:
        - task_key: fullreindex
          spark_python_task:
            python_file: ../jobs/reindex_lightrag.py
            parameters:
              - "--mode"
              - "fullreindex"
              - "--filter-mode"
              - "strict"
              # NO --force-overwrite — operator passes via override on retry
          environment_key: default
      environments:
        - environment_key: default
          spec:
            environment_version: "2"
            dependencies:
              - "lightrag-hku==1.4.15"
              - "databricks-sdk>=0.30.0"
              - "numpy>=1.26.0"

    kdb_2_5_reindex_postcheck:
      name: "[kdb-2.5] Re-index LightRAG — Step 3 postcheck"
      queue:
        enabled: true
      max_concurrent_runs: 1
      timeout_seconds: 1800   # 30min ceiling — postcheck is read-only, fast
      tasks:
        - task_key: postcheck
          spark_python_task:
            python_file: ../jobs/reindex_lightrag.py
            parameters:
              - "--mode"
              - "postcheck"
          environment_key: default
      environments:
        - environment_key: default
          spec:
            environment_version: "2"
            dependencies:
              - "lightrag-hku==1.4.15"
              - "databricks-sdk>=0.30.0"
              - "numpy>=1.26.0"
```

### Key choices

1. **`spark_python_task`** with serverless `environments:` block (`environment_version: "2"`) — simplest single-file Job shape, Databricks-recommended for serverless. Confirmed canonical from current Bundle docs.

2. **No `cluster:` block.** Serverless compute autoscales; we don't manage cluster lifecycle.

3. **Three separate Jobs** (smallbatch / fullrun / postcheck) rather than one Job with conditional tasks. Reasons:
   - **Independent invocation:** operator runs Step 1, reviews findings, then triggers Step 2 manually. Mixing them risks accidentally firing Step 2 before reviewing Step 1.
   - **Distinct timeouts:** Step 1 (2h ceiling), Step 2 (30h ceiling), Step 3 (30min ceiling). One Job can't have task-specific timeouts in a clean way.
   - **Distinct cost gates:** the Step 2 Job's `timeout_seconds: 108000` is the literal 30h gate.

4. **`max_concurrent_runs: 1`** on all three. LightRAG storage is single-writer; two Jobs writing concurrently to the same `lightrag_storage/` would corrupt the graph.

5. **`queue.enabled: true`** — if Step 2 is triggered while Step 1 is still running (operator mistake), the second Job queues instead of erroring out.

6. **`bundle.databricks.yml` parent** (top-level Bundle config) is owned by kdb-2's `databricks-deploy/` setup. kdb-2.5's contribution is just the new `databricks-deploy/jobs/reindex_lightrag.yml` resource, included via the parent's `include:` block.

### Outstanding question (resolved at execute time)

- Does `python_file` accept relative paths from the YAML location? Per docs, **yes** — `../jobs/reindex_lightrag.py` resolves against the YAML's directory. If kdb-2's bundle structure puts YAMLs under `databricks-deploy/resources/`, the path adjusts. Executor confirms.

---

## Q6 — Concurrency tuning

**Confidence:** HIGH on rate-limit numbers (sourced from current Databricks Foundation Model APIs limits page); MEDIUM on actual saturation under our workload (Step 1 measures).

### Documented rate limits (per Databricks docs)

| Endpoint | ITPM | OTPM | QPH | Source |
|----------|------|------|-----|--------|
| Claude Sonnet 4.6 | 200,000 | 20,000 | 360,000 | docs.databricks.com/aws/en/machine-learning/foundation-model-apis/limits — Anthropic Claude models table |
| Qwen3-Embedding-0.6B | N/A | N/A | 2,160,000 | Same — Embedding models table |

**Plus workspace-level QPS limit: 200/sec** (Per-workspace, applies across all endpoints).

### Saturation analysis

**Sonnet 4.6 — input-token bottleneck:**
- Per-article: ~8,200 Sonnet input tokens (Q3 anchor).
- 200,000 ITPM / 8,200 tokens-per-article = ~24 articles/min token-budget.
- At ~30s wallclock per article (Q3 anchor), 24 articles/min implies **12 articles in flight simultaneously** to saturate.
- LightRAG default `llm_model_max_async = 4` → 4 articles' worth of LLM concurrency in-flight per LightRAG instance.
- Headroom: we're at ~33% of token budget by default. Safe.

**Sonnet 4.6 — output-token bottleneck:**
- Per-article: ~4,800 Sonnet output tokens.
- 20,000 OTPM / 4,800 = ~4.2 articles/min output-budget.
- This is the **tighter** binding constraint than input tokens.
- At 30s wallclock + 4.2 articles/min output budget → equilibrium with LightRAG default `llm_model_max_async=4`. **Defaults are matched to the rate limit by design.**

**Qwen3 embedding — QPH bottleneck:**
- Per-article: ~50 embedding calls / `embedding_batch_num=10` ≈ 5 batched queries.
- 2,160,000 QPH / 5 queries-per-article × 60 = 36,000 articles/min budget. **Effectively unconstrained for our scale.**

**QPS workspace cap (200/sec):**
- LightRAG with `embedding_func_max_async=8` + `llm_model_max_async=4` peaks at ~12 in-flight HTTP calls. Latency ~1-3s per call → ~6 QPS sustained. Far under 200 QPS limit.

### Concurrency recommendation

**Default LightRAG settings are appropriate for kdb-2.5:**
- `llm_model_max_async = 4` (matches Sonnet OTPM headroom)
- `embedding_func_max_async = 8` (matches Qwen3 QPH; even doubled would be safe)
- `embedding_batch_num = 10` (matches HTTP batching efficiency)
- `max_parallel_insert = 2` (LightRAG default — controls how many docs are in the chunk-extraction pipeline simultaneously; with 2 we get 2 articles' worth of in-flight chunks → consistent with Sonnet headroom)

**No environment-variable overrides needed at Step 1.** Step 1 measures actual:
- 429 errors (count from logs; the kdb-1.5 SDK lazy-imports `databricks.sdk.errors.RateLimitError` ≈ HTTP 429)
- p50 + p95 latency per article
- Average tokens per article

If Step 1 shows zero 429s and Step 2 has burn-rate slack, **and** the operator wants faster Step 2, raise `MAX_ASYNC=8` (env var; LightRAG reads at instance construct time per `lightrag.py:424`). Step 1 BEFORE bumping. Don't push to 16 — Sonnet OTPM gets tight.

### 429 handling

LightRAG does NOT auto-retry on 429. The kdb-1.5 factory wraps SDK calls in `loop.run_in_executor`; the executor surfaces SDK `RateLimitError` as a regular Python exception. Inner per-chunk failures are caught by LightRAG's `_process_extract_entities` exception handler (logs + marks doc FAILED in doc_status) — they do NOT re-raise.

**Implication:** if Step 1 hits 429 storms, articles will appear in `kdb-2.5-FAILURES.csv` with error string containing "429" or "rate_limit_exceeded". Step 1 plan must check failure rate AND error-string distribution; if >5% are 429s, scale `MAX_ASYNC` DOWN before Step 2.

**Optional enhancement (DEFERRED — not in v1 scope):** wrap `make_llm_func` / `make_embedding_func` returns in retry-with-exponential-backoff that intercepts 429 and waits `Retry-After` seconds. Would require modifying the kdb-1.5 factory file (which is FROZEN per scope constraint #2). Defer to v1.1.

---

## Q7 — Empty-target safety implementation

**Confidence:** HIGH (FUSE access verified working in kdb-1 spike + kdb-1.5 dry-run).

### Approach

Two failure modes to guard:

1. **First Step 2 run on previously populated `lightrag_storage/`** — must FAIL loudly with mtimes of existing artifacts.
2. **Step 2 Job retried after partial failure** — must safely SKIP already-OK articles (resume support).

**(1) is solved by `_verify_target_empty(force_overwrite)` (Q4 sketch).** Operator must explicitly pass `--force-overwrite` to overwrite. The error message includes file paths + mtimes so the operator decides knowingly.

**(2) is solved by progress CSV (`/Volumes/.../output/kdb-2.5-progress.csv`)** + LightRAG's content-hash dedup. The Job at `_run_fullreindex` start:
- Reads progress CSV → set of OK content_hashes.
- Filters candidates list: `[r for r in candidates if r.content_hash not in done_hashes]`.
- LightRAG's content-hash dedup is the second line of defense (if progress CSV is missing, articles still get correctly skipped by the duplicate-hash check at `lightrag.py:1463`).

### Volume access pattern

Job reads from `/Volumes/...` via FUSE mount (verified working from Apps runtime in kdb-1.5 RESEARCH; also works from Jobs containers per Databricks docs). FUSE-on-UC-Volume:
- `Path("/Volumes/...").exists()` → returns true if Volume is mounted, false if not (or if SP lacks access).
- `Path("/Volumes/...").iterdir()` → lists files; raises `PermissionError` on no-access, `FileNotFoundError` on missing.
- Writing to FUSE: `Path("/Volumes/...").write_bytes(...)` works IFF Job principal has `WRITE_VOLUME` grant.

**Out-of-band requirement for kdb-2.5:** the Job must run as a principal with `WRITE_VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault`. Two options:

- **Option A (recommended):** Job runs as user `hhu@edc.ca` (Bundle deploy with `--profile dev` runs as the deployer). User has the schema ownership and can grant themselves WRITE.
- **Option B:** Create a dedicated kdb-2.5 SP, grant WRITE_VOLUME, run Job as that SP. After kdb-2.5 closes, revoke the SP's WRITE.

Option A is simpler for v1 (one-shot Job). Document in plan: "User must have `WRITE_VOLUME` at run time; verify with `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO 'hhu@edc.ca'` before triggering the Job."

This is **distinct** from the App SP grants (AUTH-DBX-03 is `READ_VOLUME` only for the App). The App is read-only; the Job is a one-shot writer.

### SDK Files API as fallback?

`databricks-sdk WorkspaceClient.files.upload` / `.download_directory` works as an alternative to FUSE. kdb-1.5 startup_adapter uses Files API as a fallback path for the App. For the Job, FUSE is preferred because:
- Job containers reliably have FUSE mounts (per docs + kdb-1 evidence).
- Files API would require more code (chunked upload of LightRAG state files; the Job writes 12 files, some up to ~225MB).
- FUSE writes are append-friendly: LightRAG's `index_done_callback` writes the full dict each time; with FUSE, each write completes atomically at the syscall level.

**Recommendation:** FUSE primary, no Files API fallback for the Job. If Step 1 fails on FUSE access, the executor raises an issue requiring out-of-band fix (grant WRITE_VOLUME) rather than implementing a code-side fallback in v1.

---

## Q8 — kdb-2.5-VERIFICATION + kdb-2.5-FAILURES.csv shape

**Confidence:** HIGH (templates derived from ROADMAP rev 3 success criteria + kdb-1.5 / kdb-1 precedent).

### `kdb-2.5-FAILURES.csv` — schema

```csv
content_hash,source_table,error_truncated
abc123def456789abc123def456789ab,articles,RateLimitError: 429 ITPM exceeded; retry_after=15
def456abc789abc456def123abc789de,rss_articles,doc_status=FAILED for hash def456abc7
ghi789abc123def456ghi789abc123de,articles,sqlite3.OperationalError: database is locked
```

Constraints:
- 32-char content_hash (MD5 hex).
- `source_table` ∈ {`articles`, `rss_articles`}.
- `error_truncated`: 200-char trimmed `repr(exception)`. Stripped of: file paths, hostnames, secrets. The Job's `_ingest_one` does `repr(e)[:200]` — ensure this is true at code-review time (e.g., add a sanity assertion that the error string contains no `/`, no `\\`, no `@` patterns).

### `kdb-2.5-VERIFICATION.md` — template

```markdown
---
artifact: VERIFICATION
phase: kdb-2.5
created: <date>
verified: <date>
status: passed | failed | reopened
score: <X/Y> must-haves verified
---

# Phase kdb-2.5 — Verification

## Phase ROADMAP success criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Job final state = `SUCCEEDED` (or `SUCCEEDED_WITH_FAILURES` if tolerable) | <PASS/FAIL> |
| 2 | `dbfs:/Volumes/.../lightrag_storage/` populated with vdb_*.json + graph_*.graphml + kv_store_*.json | <PASS/FAIL> |
| 3 | Failure rate ≤ 5% of articles | <PASS/FAIL> (n_failed=X / n_total=Y → Z%) |
| 4 | Post-check: 5-10 entities verified dim 1024; bilingual coverage; 2 round-trip queries | <PASS/FAIL> |
| 5 | Total cost recorded (extrapolated from Model Serving billing) | $<X> recorded |

## Step 1 small-batch findings

(See `kdb-2.5-SMALLBATCH-FINDINGS.md` for full data.)

| Measurement | Value |
|-------------|-------|
| Articles sampled | 50 |
| Filter mode | strict |
| Stratification | 5 ntiles × 10 each |
| Avg sonnet input tokens / article | <X> |
| Avg sonnet output tokens / article | <X> |
| Avg qwen3 embedding tokens / article | <X> |
| Avg wallclock / article | <X.Y>s |
| 429 error count | <N> |
| Step 1 cost | $<X> |
| Extrapolated full-corpus cost | $<X> (formula: <show formula>) |
| Extrapolated full-corpus wallclock | <X.Y>h |
| Cost gate decision | PASS / FAIL (under $200 + under 30h) |

## Step 2 full re-index

| Property | Value |
|----------|-------|
| Job run ID | <run-id> from databricks jobs runs list |
| Start time | <ISO ts> |
| End time | <ISO ts> |
| Wallclock | <X.Y>h |
| Articles processed | <X> |
| Articles OK | <X> |
| Articles failed | <X> (rate: <X.Y>%) |
| Total cost | $<X> (from MosaicAI billing dashboard) |
| Volume artifact size | <X> MB |
| Volume artifact list | <X> files matching pattern (vdb_*.json + graph_*.graphml + kv_store_*.json) |

## Step 3 post-check

| Check | Result |
|-------|--------|
| `vdb_entities.json` `embedding_dim` field | <X> (expect 1024) |
| Bilingual coverage in 200-entity sample | zh=<N>, en=<N> (expect both >=10) |
| Zh round-trip query response | len=<X> chars; first 400: <excerpt> |
| En round-trip query response | len=<X> chars; first 400: <excerpt> |

## Files emitted under `databricks-deploy/jobs/`

- `reindex_lightrag.py` (<X> lines)
- `reindex_lightrag.yml`

## Files emitted under `.planning/phases/kdb-2.5-*/`

- `kdb-2.5-RESEARCH.md`
- `kdb-2.5-01-PLAN.md`
- `kdb-2.5-01-SUMMARY.md`
- `kdb-2.5-02-PLAN.md`
- `kdb-2.5-02-SUMMARY.md`
- `kdb-2.5-SMALLBATCH-FINDINGS.md`
- `kdb-2.5-FAILURES.csv` (Step 2 output, copied from `/Volumes/.../output/`)
- `kdb-2.5-VERIFICATION.md` (this file)

## Skill discipline

Plans 01 + 02 SUMMARY.md files MUST contain literal `Skill(skill="...")` substrings per `feedback_skill_invocation_not_reference.md`:

- Plan 01: `Skill(skill="databricks-patterns")`, `Skill(skill="python-patterns")`
- Plan 02: `Skill(skill="databricks-patterns")`, `Skill(skill="writing-tests")`

## Commit ledger

| Wave | Hash | Type | Message (truncated) |
|------|------|------|---------------------|
| Pre  | <hash> | docs | docs(kdb-2.5): RESEARCH + plans + SMALLBATCH-FINDINGS template |
| 01 W1 | <hash> | feat | feat(kdb-2.5): reindex Job script + YAML |
| 01 W2 | <hash> | test | test(kdb-2.5): smallbatch — Step 1 against prod (n=50) |
| 01 W2 | <hash> | docs | docs(kdb-2.5-01): SMALLBATCH-FINDINGS + cost-gate decision |
| 02 W1 | <hash> | run | run(kdb-2.5): fullreindex Job triggered, run-id=<x> |
| 02 W2 | <hash> | test | test(kdb-2.5): postcheck PASS |
| 02 W3 | <hash> | docs | docs(kdb-2.5-02): VERIFICATION + STATE backfill |

All commits forward-only per `feedback_no_amend_in_concurrent_quicks.md`. No `git commit --amend`, no `git reset`, no `git add -A`.

## Status

PASSED — proceed to kdb-3 (UAT close).
```

### `kdb-2.5-SMALLBATCH-FINDINGS.md` template (executor populates)

```markdown
# kdb-2.5 Step 1 — Small-batch Findings

**Run:** <date> (Job run-id <x>)
**Mode:** smallbatch
**Sample size:** 50 articles (stratified, 5 ntiles × 10 each)
**Filter mode:** strict (body NOT NULL + layer1=candidate + layer2 != reject)

## Per-article measurements (averages over 50 sampled articles)

| Measurement | Value | Source |
|-------------|-------|--------|
| Sonnet input tokens | <X> | MosaicAI billing dashboard, run window <start-end> |
| Sonnet output tokens | <X> | Same |
| Qwen3 embedding tokens | <X> | Same |
| Wallclock per article | <X.Y>s | progress CSV |
| 429 errors | <N> | progress CSV (error_truncated contains "429") |

## Cost extrapolation

```
total_cost = num_articles_total × (
    avg_sonnet_input × $3.00e-6 +
    avg_sonnet_output × $15.00e-6 +
    avg_qwen3_embedding × $0.15e-6
)

= <full_corpus_size> × (
    <X> × $3.00e-6 +
    <Y> × $15.00e-6 +
    <Z> × $0.15e-6
)
= $<TOTAL>
```

## Time extrapolation

```
total_time = num_articles_total × avg_wallclock / effective_concurrency
           = <full_corpus_size> × <wallclock>s / 1
           = <X>s
           = <Y>h
```

## Gate decision

| Gate | Threshold | Actual | Decision |
|------|-----------|--------|----------|
| Cost | < $200 | $<X> | PASS / FAIL |
| Time | < 30h | <Y>h | PASS / FAIL |
| Failure rate | < 5% | <Z>% | PASS / FAIL |

## Long-tail risk

Longest single article wallclock: <X>s (hash <abc...>, body length <Y> chars). <Risk-assessment text>

## Decision

PROCEED to Step 2 / STOP and escalate / NEEDS-INVESTIGATION.
```

---

## Architectural Decisions

### Decision 1 — Single-script multi-mode design

**Choice:** One `databricks-deploy/jobs/reindex_lightrag.py` with `--mode` flag (smallbatch / fullreindex / postcheck), three Bundle Jobs invoking it with different parameters.

**Why not three separate scripts:** ~80% of code (auth, factory instantiation, candidate query, doc_status check, progress CSV) is shared. Splitting forces duplication. Single-script keeps the contract surface narrow and testable.

**Why not one Bundle Job with three sequential tasks:** distinct timeouts (Step 1: 2h, Step 2: 30h, Step 3: 30min) + distinct manual gates (operator reviews Step 1 SMALLBATCH-FINDINGS before triggering Step 2). One Job auto-fires all tasks; that fights the cost-gate design.

### Decision 2 — Single LightRAG instance, no ThreadPoolExecutor

**Choice:** One LightRAG instance, single main thread driving sequential `await rag.ainsert()` per article. LightRAG's internal `embedding_func_max_async × llm_model_max_async` provides 12-way HTTP concurrency.

**Why not ThreadPoolExecutor:** LightRAG has shared state (`pipeline_status` namespace, graphml + vdb_*.json under single-writer). Multiple LightRAG instances would either corrupt each other's state OR force per-instance working_dirs that you'd then have to merge — a complex problem with no upstream support.

**Why not Spark `foreachPartition`:** same issue. Spark partitions imply per-partition processing isolation, which breaks the single-graphml constraint.

### Decision 3 — Direct write to UC Volume (FUSE)

**Choice:** Job runs with `WRITE_VOLUME` (out-of-band grant; user-or-Job-SP-level), writes `lightrag_storage/` directly to `/Volumes/...`.

**Why not write to `/tmp` then copy:** intermediate `/tmp` state is lost on Job container disposal; if Job stops mid-Step-2 (timeout, OOM, manual cancel), all work is lost. Direct-to-Volume gives durable per-article progress.

**Why not Files API:** more code, more failure modes (chunked uploads of 200+MB files), no atomicity benefit.

### Decision 4 — Empty-target safety + progress CSV resume

**Choice:** `_verify_target_empty(force_overwrite)` at start of smallbatch + fullreindex. Progress CSV at `/Volumes/.../output/kdb-2.5-progress.csv` for retry resume. LightRAG's content-hash dedup as second-line defense.

**Why not just LightRAG's dedup:** LightRAG dedup runs INSIDE `apipeline_enqueue_documents`, after the candidate is loaded into memory + chunked. Skipping at the Job level (BEFORE handing to LightRAG) is cheaper on retry.

### Decision 5 — Default LightRAG concurrency settings

**Choice:** No env-var overrides for Step 1. Use LightRAG defaults (`MAX_ASYNC=4`, `EMBEDDING_FUNC_MAX_ASYNC=8`, `EMBEDDING_BATCH_NUM=10`, `MAX_PARALLEL_INSERT=2`).

**Why:** Q6 analysis shows defaults are matched to Sonnet OTPM constraint. Step 1 measures actual 429 rate; tune from data, not from prediction. Push up only if Step 1 shows zero 429s + slack on cost gate.

### Decision 6 — Cost formula anchors with ±50% uncertainty

**Choice:** Anchor estimate of $0.097/article based on Anthropic-public-pricing for Sonnet 4-tier + small-embedding-tier estimate for Qwen3. Mark MEDIUM confidence on absolute numbers, HIGH confidence on the formula structure.

**Why:** the Step 1 measurement WILL produce ground-truth numbers from the workspace billing dashboard. The framework is robust as long as Step 1 captures (input_tokens, output_tokens, embedding_tokens, wallclock) per article. The anchor exists to set expectations + size the gate sanity check, not to be the gate decision itself.

---

## Risks

### Risk 1: Step 1 small-batch underestimates full-corpus cost

**Probability:** MEDIUM. kdb-1.5 dry-run measured 5 articles × 371 chars at ~$0.08 = $0.0043/100 chars. Real corpus avg 10K chars/article (KOL) — naive linear says $0.43/article, but real per-article cost should be lower because token-cost is dominated by chunk-level entity extraction (relatively constant per chunk regardless of total chunks per article) — cost scales sub-linearly with body length once you exceed 1 chunk.

**Impact:** Step 1 says "$50 total"; Step 2 actually costs $300. Burn-rate alarm catches at ~25 articles in (per Q4 burn-rate monitor), but $X already spent.

**Mitigation:**
- Stratified sampling in Step 1 (5 ntiles × 10) — captures p99 long articles.
- Real-time burn-rate alert in Step 2 every 25 articles (warn at 1.5× Step-1 extrapolation).
- Hard cost ceiling (`timeout_seconds: 108000`) caps Step 2 at 30h regardless.
- If Step 2 burns through Step-1 budget by ~50% mark, operator manually cancels and re-runs Step 1 with refined sampling.

### Risk 2: Sonnet 4.6 OTPM (output tokens / minute) saturation → 429 storms

**Probability:** MEDIUM. Default `llm_model_max_async=4` is matched to OTPM headroom, but actual entity-extract output sizes can vary 2-3× from anchor.

**Impact:** Articles fail with 429; resume CSV catches them on next run, but Step 2 wallclock balloons.

**Mitigation:**
- Step 1 measures 429 rate. If >1% during Step 1, **reduce** `MAX_ASYNC` env var to 2 BEFORE Step 2 (don't increase blindly).
- Out-of-scope (DEFERRED): wrap factory calls in retry-with-backoff. Would modify kdb-1.5 frozen file.

### Risk 3: Storage corruption from partial Step 2 failure

**Probability:** LOW. LightRAG writes via `index_done_callback` after each batch; partial-write at the file level is rare (atomic at syscall level on FUSE).

**Impact:** `vdb_*.json` parse error on Step 3 postcheck → postcheck fails, phase REOPENED.

**Mitigation:**
- Per-article ainsert + post-check verifies dim + roughly-balanced entity counts (Q1 + Q4 + Q8).
- Operator runbook (kdb-3 deliverable; not this phase): "if `vdb_entities.json` parse fails, restore from `kol_scan.db.backup-*` snapshot + re-run with `--force-overwrite` and reduced `MAX_ASYNC`".
- Independent verification: Step 3 runs `aquery` round-trip — if it succeeds, the storage is in a queryable state.

### Risk 4: Empty-target safety bypassed accidentally

**Probability:** LOW. The `_verify_target_empty` check is structural; safe-by-default.

**Impact:** Re-running Step 2 on populated `lightrag_storage/` silently overwrites prior good state. Loss of ~$20-100 of indexing work.

**Mitigation:**
- `_verify_target_empty` lists existing artifact paths + mtimes in error message. Operator must explicitly `--force-overwrite` after reading.
- Bundle YAML's smallbatch + fullrun Jobs do NOT include `--force-overwrite` in default `parameters`; operator passes via `databricks bundle run kdb_2_5_reindex_fullrun -t dev --params force-overwrite=true` only when actually intended.
- Procedural: kdb-2.5 plan documents that the first Step 2 run on the prod Volume is the ONLY run that should not need `--force-overwrite`. Subsequent retries / re-runs require explicit operator decision.

### Risk 5: Long-tail article (>100K chars, >30 chunks) consumes 30+ min wallclock alone

**Probability:** LOW (1-2% of corpus per Q2 distribution).

**Impact:** Cost-gate extrapolation is wrong if Step 1's stratified sample misses the p99. Step 2 wallclock balloons by single-article share.

**Mitigation:**
- Stratified sampling MUST include the top ntile (longest 20% of bodies).
- Step 1 SMALLBATCH-FINDINGS.md should report longest-article wallclock + body-length explicitly so operator sees the long-tail risk before triggering Step 2.
- Optional plan-time hardening: cap article-body to 50K chars in the Job (`row.body[:50000]`); rare longer articles get truncated. This is a CONTENT MUTATION — surface to user before adopting; default OFF.

---

## Validation Architecture

> Per `.planning/config.json` workflow.nyquist_validation default (treat as enabled).

### Test framework
| Property | Value |
|----------|-------|
| Framework | pytest 7+ (existing project venv; pinned in `databricks-deploy/requirements.txt`) |
| Config file | `databricks-deploy/pytest.ini` (existing from kdb-1.5; reuses asyncio_mode=auto + dryrun marker) |
| Quick run command | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v` |
| Full suite command | `pytest databricks-deploy/ -v -m ""` |

### Phase requirements → test map

| REQ | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SEED-DBX-02 (cand query) | `_load_candidates(filter_mode='strict')` returns rows matching DATA-07 fragment | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_load_candidates_strict_filter -x` | ❌ Wave 0 |
| SEED-DBX-02 (stratified sample) | `_load_candidates(sample_n=50)` returns 50 rows distributed across 5 body-length ntiles | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_stratified_sample_distribution -x` | ❌ Wave 0 |
| SEED-DBX-02 (empty-target safety) | `_verify_target_empty` raises on non-empty + no force; passes on empty OR force | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_empty_target_safety -x` | ❌ Wave 0 |
| SEED-DBX-02 (per-article isolation) | `_ingest_one` returns IngestResult(status='failed') instead of raising on simulated ainsert error | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_ingest_one_isolates_failures -x` | ❌ Wave 0 |
| SEED-DBX-02 (resume) | `_load_progress_hashes(status_filter={'ok'})` returns OK content_hashes; fullreindex skips those | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_resume_skips_already_ok -x` | ❌ Wave 0 |
| SEED-DBX-02 (Step 1 e2e) | Step 1 runs against fixture DB (5-10 articles), produces SMALLBATCH-stats JSON | integration | `pytest databricks-deploy/jobs/tests/test_reindex_integration.py::test_smallbatch_against_fixture_db -x` (requires Model Serving auth; cost ~$0.50) | ❌ Wave 0 |
| SEED-DBX-02 (cost gate decision) | `_compute_burn_rate_ratio` returns >1.5 when current cost-rate exceeds Step-1 baseline by 50% | unit (post-Step1) | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_burn_rate_alert_threshold -x` | ❌ Wave 0 (deferred to plan 02 since baseline values come from Step 1) |
| SEED-DBX-02 (Step 2 prod) | Job final state SUCCEEDED (or SUCCEEDED_WITH_FAILURES); fullreindex log shows ≤5% failure | manual-only | `databricks jobs runs get <run-id>` + `databricks bundle logs ...` | n/a — prod Job |
| SEED-DBX-03 (postcheck) | `_run_postcheck` returns 0 against post-Step-2 Volume; vdb dim=1024; bilingual coverage >=10/10 | manual-only | `databricks bundle run kdb_2_5_reindex_postcheck -t dev` + check `kdb-2.5-postcheck-stats.json` | n/a — prod Job |
| FAILURES.csv schema | After simulated failure, FAILURES.csv has 3 cols (content_hash, source_table, error_truncated); error contains no `/` or `\` chars | unit | `pytest databricks-deploy/jobs/tests/test_reindex_unit.py::test_failures_csv_schema_no_path_leak -x` | ❌ Wave 0 |

### Sampling rate

- **Per task commit:** `pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v` (~5s)
- **Per wave merge:** `pytest databricks-deploy/jobs/tests/ -v` (full suite — unit + integration; ~5min if integration runs against Model Serving)
- **Phase gate:** unit suite green + Step 1 SMALLBATCH-FINDINGS.md cost-gate PASS before triggering Step 2 + Step 3 postcheck PASS before phase close

### Wave 0 gaps

- [ ] `databricks-deploy/jobs/__init__.py` — empty pkg marker
- [ ] `databricks-deploy/jobs/reindex_lightrag.py` — main Job script (~400 LOC)
- [ ] `databricks-deploy/jobs/reindex_lightrag.yml` — Bundle resource
- [ ] `databricks-deploy/jobs/tests/__init__.py`
- [ ] `databricks-deploy/jobs/tests/test_reindex_unit.py` — 6 unit tests covering: candidate filter, stratified sample, empty-target safety, per-article isolation, resume, FAILURES.csv schema
- [ ] `databricks-deploy/jobs/tests/test_reindex_integration.py` — 1 integration test (smallbatch against fixture DB; requires Model Serving auth)
- [ ] `databricks-deploy/jobs/tests/fixtures/kol_scan_fixture.db` — small synthetic SQLite (5-10 articles spanning body-length ntiles) for integration test
- [ ] `databricks-deploy/jobs/tests/conftest.py` — shared fixtures (tmp working_dir, mock LightRAG factories for unit tests)

---

## Code Examples

### LightRAG ainsert + idempotency (reference, no edit)

```python
# databricks-deploy/jobs/reindex_lightrag.py — _ingest_one excerpt (Q4 sketch)
async def _ingest_one(rag, row: CandidateRow) -> IngestResult:
    """Ingest a single article. Wraps LightRAG.ainsert with exception trap.

    Pass content_hash explicitly as `ids=[row.content_hash]` so:
      1. LightRAG's content-hash dedup at apipeline_enqueue_documents:1453
         skips already-ingested articles deterministically.
      2. The FAILURES.csv content_hash maps cleanly back to source DB row.
    """
    t0 = time.time()
    try:
        track_id = await rag.ainsert(
            row.body,
            ids=[row.content_hash],
            file_paths=[f"{row.source_table}/{row.content_hash}"],
        )
        # Cross-check doc_status — ainsert may NOT raise on inner per-chunk
        # failure; consult doc_status to confirm PROCESSED.
        status_records = await rag.doc_status.get_docs_by_ids(
            [f"doc-{row.content_hash}"]
        )
        doc_status = (
            status_records[0].status.value if status_records else "unknown"
        )
        if doc_status == "PROCESSED":
            return IngestResult(...)
        elif doc_status == "FAILED":
            return IngestResult(..., status="failed",
                                error_truncated=f"doc_status=FAILED")
    except Exception as e:
        return IngestResult(..., status="failed",
                            error_truncated=repr(e)[:200])
```

### Existing LightRAG factory consumption (kdb-1.5 — reference, no modification)

```python
# kdb-1.5 frozen file: databricks-deploy/lightrag_databricks_provider.py — DO NOT MODIFY
KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
KB_EMBEDDING_MODEL = os.environ.get("KB_EMBEDDING_MODEL",
                                    "databricks-qwen3-embedding-0-6b")
EMBEDDING_DIM = 1024
EMBEDDING_MAX_TOKEN_SIZE = 8192

def make_llm_func(): ...   # closes over WorkspaceClient(); dispatches via run_in_executor

@wrap_embedding_func_with_attrs(embedding_dim=EMBEDDING_DIM,
                                max_token_size=EMBEDDING_MAX_TOKEN_SIZE)
async def _embed(texts: list[str], **_kwargs) -> np.ndarray: ...

def make_embedding_func() -> EmbeddingFunc:
    return _embed  # already wrapped
```

### Bundle YAML reference shape (Q5 — verbatim from Databricks docs)

See Q5 above. Key shape: `spark_python_task` + `environment_key: default` + `environments:` block with `environment_version: '2'` + `dependencies:` listing pip packages.

---

## Common Pitfalls

### Pitfall 1: Confusing LightRAG `ainsert` return value

**What goes wrong:** Treating `track_id` as a success indicator. It's just a tracking string — it's returned even if downstream entity extraction fails on every chunk.

**Source evidence:** `lightrag.py:1237-1270` — return is unconditional.

**How to avoid:** consult `doc_status.get_docs_by_ids([f"doc-{content_hash}"])` to confirm PROCESSED status (Q4 sketch).

### Pitfall 2: Spawning multiple LightRAG instances for "parallelism"

**What goes wrong:** Each instance writes to the same `working_dir` → graphml + vdb_*.json corruption.

**How to avoid:** Q1 + Decision 2 — single LightRAG instance, rely on internal `embedding_func_max_async × max_parallel_insert` for in-process concurrency.

### Pitfall 3: Hardcoding article count = 2598 instead of querying the filter

**What goes wrong:** ROADMAP says "~2000 articles"; orchestrator prompt says "~2598 raw rows". But the candidate filter (DATA-07) drops to ~170 articles in local dev. Plans that assume 2598 over-budget the cost gate.

**How to avoid:** Q2 + Q4 — `_load_candidates(filter_mode='strict')` is the SOURCE OF TRUTH for re-index volume; SMALLBATCH-FINDINGS.md reports actual count.

### Pitfall 4: Step 1 sample biased toward easy short articles

**What goes wrong:** Fast random sample picks short articles (cheap) → underestimates p99 cost → Step 2 blows the gate.

**How to avoid:** Q4 `_load_candidates(sample_n=50)` uses NTILE-stratified sampling (5 buckets × 10 each); explicitly includes top body-length ntile.

### Pitfall 5: WRITE_VOLUME grant assumption

**What goes wrong:** Job kicks off, hits FUSE write fail at first `index_done_callback`, hangs or fails confusingly.

**How to avoid:** Q7 — out-of-band runbook step: verify `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO 'hhu@edc.ca'` includes WRITE_VOLUME before running Step 2. Plan 02 (Step 2 trigger) MUST list this verification as a pre-flight item.

### Pitfall 6: Forgetting `databricks-deploy/` is hyphenated, not a Python package

**What goes wrong:** `from databricks-deploy.lightrag_databricks_provider import make_llm_func` is a syntax error.

**How to avoid:** Q4 sketch — `sys.path.insert(0, str(HERE.parent))` + bare `from lightrag_databricks_provider import ...`. Same pattern as kdb-2-02 dispatcher (lib/llm_complete.py:73-74).

### Pitfall 7: `--force-overwrite` accidentally hardcoded into Bundle YAML

**What goes wrong:** kdb-2.5 plan deploys YAML with `--force-overwrite` in default parameters → first Step 2 run silently overwrites kdb-2's prior good state (if any).

**How to avoid:** Q5 + Q7 — YAML default parameters EXPLICITLY exclude `--force-overwrite`. Operator passes via run-time `--params` override only when intended. Document in plan.

### Pitfall 8: Treating MosaicAI 503/429 as transient → silent skip in production

**What goes wrong:** A 429 storm at the start of Step 2 fails the first 50 articles; FAILURES.csv has 50 rows; operator looks at "5% failure rate" PASS criterion and doesn't notice all failures are RATE_LIMIT_EXCEEDED.

**How to avoid:** Q4 `_run_fullreindex` should classify failures by error-pattern in the burn-rate alert. Plan should document: "If >50% of FAILURES.csv rows match `429|rate_limit_exceeded`, REOPEN — this is rate-limit collapse, not corpus quality. Reduce `MAX_ASYNC` and re-run."

---

## State of the Art

| Old Approach | Current Approach (this phase) | When Changed | Impact |
|--------------|-------------------------------|--------------|--------|
| Hermes-side LightRAG `ainsert` (Vertex Gemini, dim=3072) | Databricks Job `ainsert` (MosaicAI Sonnet + Qwen3, dim=1024) | kdb-2.5 (this phase) | Replaces the Hermes runtime for Databricks deploy. App SP stays READ_VOLUME; kdb-2.5 runs as a separate principal with WRITE_VOLUME (one-shot). |
| 1 cron-fired daily-ingest on Hermes | One-shot kdb-2.5 Job (manual trigger) | kdb-2.5 (this phase) | v3+ would reintroduce daily ingest on Databricks; v1 is one-shot per ROADMAP rev 3 line 193. |
| LightRAG instance constructed at App startup | LightRAG instance constructed in Job process | kdb-2.5 (this phase) | App imports kdb-1.5 factory + reads pre-built lightrag_storage; Job constructs full LightRAG and writes lightrag_storage. |

**Deprecated/outdated:**
- DeepSeek as entity-extract LLM — fully retired in v1 deploy.
- Vertex Gemini as embedding — retired (3072-dim incompatible with Qwen3 1024-dim).

---

## Open Questions

1. **Per-token MosaicAI billing rates for `databricks-claude-sonnet-4-6` and `databricks-qwen3-embedding-0-6b`**
   - What we know: Anthropic public-pricing tier for Claude Sonnet 4-class is $3/$15 per M tokens (input/output); Qwen3-0.6B small-model embedding tier ~$0.10-$0.20/M. Documentary only — Databricks corp-proxy blocked us from fetching the workspace pricing page directly.
   - What's unclear: actual per-token rate against THIS workspace.
   - Recommendation: Step 1 measures actual workspace billing dashboard ($ spent during the 30-min window); divide by token counts to get effective rates. Plug back into formula for Step 2 extrapolation.

2. **WRITE_VOLUME grant pattern for Job principal**
   - What we know: User `hhu@edc.ca` is the schema owner and has implicit WRITE access; can grant self/others.
   - What's unclear: whether Bundle deploy with `--profile dev` runs the Job as user (Option A) or as a workspace SP (Option B).
   - Recommendation: kdb-2.5-01 plan plays-through both options; Option A (user) is the simpler default; pivot to Option B (dedicated SP) only if Step 1 hits permission errors.

3. **Long-tail article cost (single 100K-char article)**
   - What we know: p99 = ~60K chars (KOL); max = 154K chars; rare.
   - What's unclear: whether Sonnet entity-extract handles 30+ chunks gracefully or hits per-chunk timeout.
   - Recommendation: Step 1 stratified sample includes the top ntile; SMALLBATCH-FINDINGS.md reports longest-article wallclock + body-length. If single-article > 30 min, surface to user as long-tail risk.

4. **Sonnet 4.6 OTPM behavior under sustained load**
   - What we know: documented limit 20,000 OTPM; LightRAG default `MAX_ASYNC=4` matches.
   - What's unclear: whether bursty loads (multiple articles' chunks completing simultaneously) cause transient 429 spikes.
   - Recommendation: Step 1 logs 429 count + retry-after distribution. If significant, document as "tune `MAX_ASYNC` down to 2 before Step 2".

5. **Whether to truncate ultra-long articles (>50K chars)**
   - What we know: 1-2% of corpus is >50K chars; consumes disproportionate tokens.
   - What's unclear: whether truncating at 50K chars meaningfully degrades graph quality vs cost savings.
   - Recommendation: defer to v1.1; for kdb-2.5 v1, ingest articles as-is. Long-tail risk surfaced in plan; user decides at Step 1 review whether to add `--max-article-chars` flag for Step 2.

---

## Environment Availability

> Job runs in Databricks serverless `spark_python_task` environment, NOT on local dev box. The "Available" column is for the JOB CONTEXT, not the developer's local machine. Local development of the Job script + unit tests is done in `databricks-deploy/` venv per kdb-1.5 setup.

| Dependency | Required By | Available (Job Env) | Version | Fallback |
|------------|-------------|---------------------|---------|----------|
| Python 3.11+ | All | ✓ (serverless `environment_version: '2'`) | 3.11 | — |
| `lightrag-hku` | Q1 ainsert + Q1 doc_status check | ✓ via `dependencies:` in YAML | 1.4.15 (pinned in `databricks-deploy/requirements.txt`) | — |
| `databricks-sdk` | kdb-1.5 factory `WorkspaceClient` | ✓ | >=0.30.0 | — |
| `numpy` | factory return type | ✓ | >=1.26.0 | — |
| MosaicAI Sonnet 4.6 endpoint | LLM calls | ✓ READY (kdb-1 PREFLIGHT-FINDINGS) | `databricks-claude-sonnet-4-6` | — |
| MosaicAI Qwen3 endpoint | embeddings | ✓ READY (kdb-1 PREFLIGHT-FINDINGS) | `databricks-qwen3-embedding-0-6b` (dim 1024) | — |
| `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db` | candidate query | ✓ uploaded (kdb-1 WAVE2-FINDINGS, SHA verified) | 20.5 MB | — |
| `WRITE_VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` for Job principal | LightRAG `index_done_callback` writes | ⚠ TBD-confirmed at run time | — | Pivot to dedicated Job SP if user grant fails (Option B in Q7) |
| `databricks` CLI 0.260+ | bundle deploy + run | ✓ (local dev box) | 0.260.0 | — |

**Missing dependencies with no fallback:** none if WRITE_VOLUME grant resolves at run time.

**Missing dependencies with fallback:** WRITE_VOLUME — fallback is dedicated Job SP with the grant. Plan 02 includes the grant verification as the first pre-flight task.

---

## Files Affected

| Path | Action | Notes |
|------|--------|-------|
| `databricks-deploy/jobs/` | **NEW (directory)** | mkdir |
| `databricks-deploy/jobs/__init__.py` | **NEW** | empty pkg marker |
| `databricks-deploy/jobs/reindex_lightrag.py` | **NEW** | Main Job script (~400 LOC; Q4) |
| `databricks-deploy/jobs/reindex_lightrag.yml` | **NEW** | Bundle resource (Q5) |
| `databricks-deploy/jobs/tests/__init__.py` | **NEW** | |
| `databricks-deploy/jobs/tests/conftest.py` | **NEW** | shared fixtures |
| `databricks-deploy/jobs/tests/test_reindex_unit.py` | **NEW** | 6 unit tests |
| `databricks-deploy/jobs/tests/test_reindex_integration.py` | **NEW** | 1 integration test |
| `databricks-deploy/jobs/tests/fixtures/kol_scan_fixture.db` | **NEW** | small synthetic SQLite |
| `.planning/phases/kdb-2.5-reindex-lightrag-storage/` | **NEW (directory)** | phase dir; mkdir done |
| `.planning/phases/kdb-2.5-.../kdb-2.5-RESEARCH.md` | **NEW** (this file) | |
| `.planning/phases/kdb-2.5-.../kdb-2.5-01-PLAN.md` | **NEW** (planner) | Plan 01: Job + smallbatch |
| `.planning/phases/kdb-2.5-.../kdb-2.5-02-PLAN.md` | **NEW** (planner) | Plan 02: fullreindex + postcheck |
| `.planning/phases/kdb-2.5-.../kdb-2.5-01-SUMMARY.md` | **NEW** (executor) | |
| `.planning/phases/kdb-2.5-.../kdb-2.5-02-SUMMARY.md` | **NEW** (executor) | |
| `.planning/phases/kdb-2.5-.../kdb-2.5-SMALLBATCH-FINDINGS.md` | **NEW** (executor) | After Step 1 run |
| `.planning/phases/kdb-2.5-.../kdb-2.5-FAILURES.csv` | **NEW** (executor) | Copied from `/Volumes/.../output/` after Step 2 |
| `.planning/phases/kdb-2.5-.../kdb-2.5-VERIFICATION.md` | **NEW** (orchestrator) | |
| `databricks-deploy/lightrag_databricks_provider.py` | **READ-ONLY (kdb-1.5 frozen)** | Job IMPORTS, never modifies |
| `databricks-deploy/startup_adapter.py` | **READ-ONLY (kdb-1.5 frozen)** | Not used by Job (Job runs in own container, no adapter needed) |
| `databricks-deploy/CONFIG-EXEMPTIONS.md` | **READ-ONLY (kdb-2 frozen)** | NOT extended in kdb-2.5 |
| `kb/`, `lib/`, `*.py` (top-level) | **READ-ONLY** | Zero modifications |
| `STATE-kb-databricks-v1.md` | **MODIFIED (orchestrator)** | "Current Position" + "Last activity" backfill via 2-forward-commit pattern |

**Diff scope at end of phase:** all changes under `databricks-deploy/jobs/` and `.planning/phases/kdb-2.5-*/`. Plus a `STATE-kb-databricks-v1.md` "Last activity" backfill commit. **CONFIG-DBX-01 verification at kdb-3 will return empty for this phase's commits** (zero `kb/` / `lib/` / top-level `*.py` touches).

---

## Plan Decomposition Recommendation

**Recommended split: 2 plans.**

### kdb-2.5-01 — Job script + Step 1 smallbatch validation

**Scope:**
- Author `databricks-deploy/jobs/reindex_lightrag.py` (Q4)
- Author `databricks-deploy/jobs/reindex_lightrag.yml` (Q5)
- Author 6 unit tests + 1 integration test (Validation Architecture)
- Deploy bundle to dev workspace: `databricks bundle deploy -t dev`
- Trigger Step 1: `databricks bundle run kdb_2_5_reindex_smallbatch -t dev --params filter-mode=strict,max-articles=50`
- Wait for completion (~30 min)
- Read SMALLBATCH stats from `/Volumes/.../output/kdb-2.5-smallbatch-stats.json`
- Pull MosaicAI billing dashboard slice for the run window
- Author `kdb-2.5-SMALLBATCH-FINDINGS.md` with cost extrapolation + gate decision

**Gate:** SMALLBATCH-FINDINGS extrapolation < $200 + < 30h + failure rate < 5%. If FAIL → STOP, escalate to user; do NOT trigger Plan 02.

**Time:** ~4-6h dev work + ~30 min Job run + ~30 min findings authoring.

### kdb-2.5-02 — Step 2 full re-index + Step 3 post-check + Verification

**Scope:**
- Pre-flight: verify WRITE_VOLUME grant on the Job principal (Q7)
- Trigger Step 2: `databricks bundle run kdb_2_5_reindex_fullrun -t dev`
- Monitor: `databricks jobs runs get <run-id>` + watch `/Volumes/.../output/kdb-2.5-progress.csv` updates
- Step 2 completion (~half-day to 1-day wallclock)
- Pull `kdb-2.5-FAILURES.csv` from `/Volumes/.../output/`
- Trigger Step 3: `databricks bundle run kdb_2_5_reindex_postcheck -t dev`
- Author `kdb-2.5-VERIFICATION.md` with Step 2 totals + Step 3 evidence + skill discipline
- Backfill commit hashes into STATE-kb-databricks-v1.md (2-forward-commit pattern)

**Gate:** Job state SUCCEEDED + failure rate ≤ 5% + post-check PASS (dim=1024 + bilingual + round-trip queries). If FAIL → phase REOPENED; selectively retry from FAILURES.csv.

**Time:** ~30 min pre-flight + ~½-1 day Step 2 + ~30 min Step 3 + ~30 min verification authoring.

### Why 2 plans, not 1 or 3

**Argument for 2 plans:**
- Cost gate is the natural seam. Plan 01's deliverable is "is it safe to run Step 2?"; Plan 02's deliverable is "Step 2 ran + verification PASS".
- Step 2 operator-trigger between the two plans is a hard gate — cannot be automated cleanly within one plan because the operator REVIEWS SMALLBATCH-FINDINGS before deciding.
- Plan 01 produces evidence Plan 02 consumes (SMALLBATCH baseline drives burn-rate alert in Plan 02).

**Argument against 1 plan:**
- Bundling creates pressure to skip the gate — "we already wrote the code, let's just run Step 2 too". The 30h / $200 gate becomes performative.
- Skill invocation discipline: `Skill(skill="databricks-patterns")` for Plan 01 (Bundle authoring) is different from `Skill(skill="writing-tests")` for Plan 02 (verification). 1-plan blends the focus.

**Argument against 3 plans (Step1 / Step2 / Step3 separately):**
- Step 3 is short (~30 min) and tightly coupled to Step 2 (postcheck reads the just-written Volume state). Splitting Step 3 into its own plan adds ceremony without payoff.
- The operator-trigger gate at Step 2 → Step 3 is auto-pass-IF Step-2-SUCCEEDED. No human decision needed between them.

### Plan 01 Skill picks

| Skill | Why |
|-------|-----|
| `databricks-patterns` | Bundle YAML + serverless `spark_python_task` + `databricks bundle deploy/run` workflow |
| `python-patterns` | Idiomatic LightRAG instantiation, async/await with `asyncio.run`, dataclasses, pathlib, sqlite3 URI mode |
| `writing-tests` | 6 unit tests using mocked LightRAG factory + `tmp_path` Volume mock; 1 integration test with stratified-sample fixture DB |
| `search-first` | Verify `databricks bundle deploy` shape from current docs before authoring YAML |

### Plan 02 Skill picks

| Skill | Why |
|-------|-----|
| `databricks-patterns` | `databricks bundle run`, `jobs runs get`, monitoring + log retrieval |
| `writing-tests` | Step 3 post-check sanity assertions (dim=1024 verification, bilingual sample threshold, round-trip query length-check) |
| `python-patterns` | Idiomatic verification artifact authoring |
| `systematic-debugging` | If Step 2 hits >5% failure rate, structured-failure-mode analysis |

---

## Sources

### Primary (HIGH confidence)

- `venv/Lib/site-packages/lightrag/lightrag.py` v1.4.15 — ainsert internals, idempotency at `:1394-1473`, defaults at `:310, :372, :375, :423, :461`
- `venv/Lib/site-packages/lightrag/constants.py` — `DEFAULT_MAX_ASYNC=4`, `DEFAULT_MAX_PARALLEL_INSERT=2`, `DEFAULT_LLM_TIMEOUT=180`
- `venv/Lib/site-packages/lightrag/kg/json_kv_impl.py:39` — storage init `os.makedirs(workspace_dir, exist_ok=True)` confirmed
- `databricks-deploy/lightrag_databricks_provider.py` — kdb-1.5 frozen factory (full file read; consumed by Job)
- `databricks-deploy/startup_adapter.py` — kdb-1.5 frozen adapter (NOT used by Job; reference only)
- `databricks-deploy/requirements.txt` — pinned deps (databricks-sdk>=0.30.0, lightrag-hku==1.4.15, numpy>=1.26.0, fastapi, uvicorn, jinja2, pytest, pytest-asyncio)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` — exemption ledger (NOT extended by kdb-2.5)
- `lib/llm_complete.py` v post kdb-2-02 — dispatcher with `databricks_serving` branch
- `kb/data/article_query.py:71-79` — DATA-07 candidate filter fragment (Q2 reference)
- `.dev-runtime/data/kol_scan.db` — local-dev DB schema + body-length distribution (Q2 measurements)
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-WAVE2-FINDINGS.md` — Volume populated; 842 KOL + 1756 RSS prod counts; SHA-verified
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md` — Sonnet 4.6 + Qwen3-0.6B endpoints READY; 2.65s + 1.33s latency baseline
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-SPIKE-FINDINGS.md` — Apps SP + UC grant patterns confirmed (relevant for Job principal)
- `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md` — full architectural context
- `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-VERIFICATION.md` — 21/21 must-haves green; 9/9 tests
- `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-02-SUMMARY.md` — dry-run measurements: 5 fixtures × 371 chars at $0.08, 156.54s wallclock, dim=1024 verified
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q2 + Q3 — dispatcher shape; embedding-side handling rationale
- `REQUIREMENTS-kb-databricks-v1.md` rev 3 — SEED-DBX-02 + SEED-DBX-03 spec
- `ROADMAP-kb-databricks-v1.md` rev 3 — phase kdb-2.5 spec lines 120-172; cost-gate; failure-tolerance; empty-target safety
- `STATE-kb-databricks-v1.md` rev 3 — milestone-base hash `cfe47b4`; current position kdb-1.5 COMPLETE
- `PROJECT-kb-databricks-v1.md` rev 3 — locked architectural choices #8 (sonnet-4-6) + #9 (one-shot seed)
- `docs.databricks.com/aws/en/machine-learning/foundation-model-apis/limits` (curl-fetched 2026-05-17) — Sonnet 4.6 ITPM 200K / OTPM 20K / QPH 360K; Qwen3-Embedding-0.6B QPH 2.16M; workspace QPS 200; 597s per-request execution-duration ceiling
- `docs.databricks.com/aws/en/machine-learning/model-serving/foundation-model-overview` (curl-fetched 2026-05-17) — supported pay-per-token endpoints incl. databricks-claude-sonnet-4-6 + databricks-qwen3-embedding-0-6b
- `docs.databricks.com/aws/en/dev-tools/bundles/resources` (curl-fetched 2026-05-17) — canonical Bundle Job example with `spark_python_task` + serverless `environments:` + `dependencies:` block

### Secondary (MEDIUM confidence)

- Anthropic public pricing for Claude Sonnet 4-class: $3/$15 per 1M input/output tokens (used as anchor for cost extrapolation; corp-blocked from anthropic.com directly; sourced from training data + cross-check against kdb-1.5 dry-run measurements)
- Qwen3-Embedding-0.6B small-model embedding tier estimate: $0.10-$0.20 / 1M tokens (anchor; ground truth from Step 1 billing dashboard)
- `databricks-mcp-server execute_sql` for prod corpus row count verification — usable but not yet executed against prod Volume DB; local-dev DB used as proxy

### Tertiary (LOW confidence)

- Per-token MosaicAI workspace billing rates — public pricing pages JS-rendered + corp-proxy-blocked. Step 1 measures actual workspace billing.
- Long-tail article wallclock (>30 min for single 100K-char article): theoretical risk; never measured. Step 1 stratified sample reveals.
- WRITE_VOLUME grant pattern for Job runs (Option A vs B) — both work in principle; Option A simpler.

---

## Metadata

**Confidence breakdown:**

- Q1 LightRAG ainsert + storage schema: HIGH (full source-trace)
- Q2 corpus inventory: HIGH (local-dev DB measured; prod row counts SHA-verified in WAVE2-FINDINGS)
- Q3 cost framework: HIGH on framework, MEDIUM on per-token rates anchor (Step 1 measures)
- Q4 Job script architecture: HIGH (kdb-1.5 factory frozen + tested; Q4 sketch is mechanical orchestration)
- Q5 Bundle YAML shape: MEDIUM (canonical example sourced; not yet end-to-end deployed)
- Q6 concurrency tuning: HIGH on rate limits (sourced from current docs); MEDIUM on saturation (Step 1 measures)
- Q7 empty-target safety: HIGH (FUSE access verified working in kdb-1 + kdb-1.5)
- Q8 verification artifact templates: HIGH (template structure derived from kdb-1.5 / kdb-1 precedent)

**Research date:** 2026-05-17

**Valid until:** 2026-06-17 (30 days; LightRAG 1.4.x stable; Databricks SDK + Bundle CLI no announced breaking changes; MosaicAI endpoints stable).

Sources:
- [Foundation Model APIs limits and quotas (Databricks AWS docs)](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/limits)
- [Foundation Model overview (supported endpoints)](https://docs.databricks.com/aws/en/machine-learning/model-serving/foundation-model-overview)
- [Databricks Asset Bundle resources reference](https://docs.databricks.com/aws/en/dev-tools/bundles/resources)
