# Phase kdb-2.5 — Context

**Phase mission:** Re-build the LightRAG knowledge graph end-to-end on Databricks using
MosaicAI Model Serving (`databricks-claude-sonnet-4-6` for entity extraction,
`databricks-qwen3-embedding-0-6b` dim=1024 for embeddings). Runs as a Databricks Job
(not in-App) because walltime is hours. The result — a populated
`/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/` — enables
post-kdb-3 KG-mode RAG round-trips.

**Milestone:** kb-databricks-v1 (parallel track, docs suffix `*-kb-databricks-v1.md`)
**Phase dir:** `.planning/phases/kdb-2.5-reindex-lightrag-storage/`
**Phase tooling:** Parallel-track; `gsd-tools.cjs init` returns `phase_found=false`.
All gates are hand-driven by the orchestrator.

---

## 7 Locked Decisions

| # | Decision | Source |
|---|----------|--------|
| D-01 | **Corpus scope STRICT** — filter: `body IS NOT NULL AND body != '' AND content_hash IS NOT NULL AND layer1_verdict='candidate' AND (layer2_verdict IS NULL OR layer2_verdict!='reject')`. Yields ~170 articles (~$17, ~1.4h). Hardcoded — no `--filter-mode` flag exposed to the cost gate. Read-side parity with `kb/data/article_query.py` DATA-07 fragment. | Research Q2 + orchestrator |
| D-02 | **2-plan split** — kdb-2.5-01 owns Job script + YAML + Step 1 smallbatch validation + cost gate. kdb-2.5-02 owns Step 2 fullreindex + Step 3 postcheck + VERIFICATION. Natural seam = cost gate: Plan 01's deliverable is "is it safe?"; Plan 02's deliverable is "it ran + PASS". | Research Plan Decomposition + orchestrator |
| D-03 | **Job principal = `hhu@edc.ca`** (Option A). Bundle deploy with `--profile dev` runs as the schema owner. App SP keeps `READ_VOLUME` only (AUTH-DBX-03 invariant). Plan 02 pre-flight verifies WRITE_VOLUME grant before triggering Step 2. | Research Q7 + orchestrator |
| D-04 | **NO ThreadPoolExecutor.** Single LightRAG instance, single thread driving sequential `await rag.ainsert()`. LightRAG's internal `embedding_func_max_async=8` × `llm_model_max_async=4` provides 12-way HTTP concurrency. Multiple instances corrupt shared `lightrag_storage/` (single-writer constraint). | Research Q1 + Q6 + Decision 2 |
| D-05 | **Doc-status post-check required.** `ainsert` can SILENTLY fail (`apipeline_process_enqueue_documents` catches per-chunk LLM errors, marks doc FAILED, never raises). Job MUST `await rag.doc_status.get_docs_by_ids([f"doc-{content_hash}"])` post-ainsert; only `status == "PROCESSED"` counts as success. `try/except Exception` alone is insufficient. | Research Q1 + orchestrator |
| D-06 | **Idempotency via `ids=[content_hash]`** — `await rag.ainsert(content, ids=[content_hash])` auto-skips PROCESSED docs on retry (LightRAG `filter_keys` at `:1453`). Combined with progress CSV: safe + cheap retries without re-ingesting already-OK articles. | Research Q1 + orchestrator |
| D-07 | **Empty-target safety** — First Step 2 run: `--init-empty` REQUIRED; verify `/Volumes/.../lightrag_storage/` is empty. Subsequent retries: `--force-overwrite` REQUIRED; display existing artifact mtimes in the error message. YAML default parameters MUST NOT include either flag. Plan 02 first task = empty-target pre-flight (BLOCKED if non-empty AND neither flag present). | Research Q7 + orchestrator |

---

## Plan Decomposition Rationale

| Plan | Slug | Wave | REQs | Core purpose |
|------|------|------|------|--------------|
| kdb-2.5-01 | job-script-and-smallbatch-validation | 1 | SEED-DBX-02 (Step 1) | Author Job script + YAML + unit tests; deploy bundle; run Step 1 (50 articles); author SMALLBATCH-FINDINGS; pass cost gate |
| kdb-2.5-02 | fullreindex-and-postcheck | 2 | SEED-DBX-02 (Step 2) + SEED-DBX-03 (Step 3) | WRITE_VOLUME pre-flight; trigger Step 2 fullreindex; collect FAILURES.csv; trigger Step 3 postcheck; author VERIFICATION |

Wave 2 depends on Wave 1 passing the cost gate. The seam is intentional — the
operator reviews SMALLBATCH-FINDINGS before triggering Step 2. Automating this
review away would make the $200/30h gate performative.

---

## Scope Boundaries

**In scope (kdb-2.5 only):**
- `databricks-deploy/jobs/reindex_lightrag.py` (NEW)
- `databricks-deploy/jobs/reindex_lightrag.yml` (NEW)
- `databricks-deploy/jobs/tests/` (NEW — 6 unit + 1 integration + fixtures + conftest)
- `.planning/phases/kdb-2.5-*/` planning artifacts

**Strictly read-only (must not modify):**
- `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 frozen)
- `databricks-deploy/startup_adapter.py` (kdb-1.5 frozen)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (kdb-2 frozen; NOT extended by kdb-2.5)
- `kb/`, `lib/`, top-level `*.py` (CONFIG-DBX-01 invariant)
- `tests/integration/kb/` (kdb-2 / KB-v2 territory)

**Deferred (not kdb-2.5):**
- kdb-3 UAT close, Smoke 3 RAG round-trip
- Embedding-side dispatcher (`lib/embedding_complete.py`)
- 429 auto-retry with exponential backoff (requires modifying frozen factory)
- `--max-article-chars` body truncation flag (user decision at Step 1 review)
