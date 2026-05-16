# Roadmap — kb-databricks-v1 (rev 3)

> Parallel-track milestone. Phases use `kdb-N-*` prefix. Sibling roadmaps: `ROADMAP-KB-v2.md` (`kb-N-*`), `ROADMAP-Agentic-RAG-v1.md` (`ar-N-*`), `ROADMAP-v3.5-Ingest-Refactor.md` (`ir-N-*`). Main `ROADMAP.md` is owned by v3.4 / v3.5 main track.
>
> **rev 3 strategic constraints (user-locked 2026-05-15):** ALL LLM via MosaicAI Model Serving (DeepSeek retired); Hermes runtime-separated (one-shot SEED replaces ongoing SYNC); synthesis = `databricks-claude-sonnet-4-6`; embedding = `databricks-qwen3-embedding-0-6b`; "zero `kb/` edits" relaxed for `lib/llm_complete.py` + `kg_synthesize.py`. See REQUIREMENTS rev 3 frontmatter for full list.

## Milestone size

T-shirt **M** — 2–4 days end-to-end. Driver: kdb-2.5 NEW phase (re-index LightRAG storage as Databricks Job, 8–30h wallclock + $20–100 cost). Without kdb-2.5 we'd be at S; the re-index step is the structural cost of switching to MosaicAI embeddings.

## Phase summary

| # | Phase | Goal | REQs covered | Success criteria | T-shirt |
|---|-------|------|--------------|------------------|---------|
| **kdb-1** | UC Volume + Seed + Preflight + Spike | Volume in place; one-shot SQLite + images uploaded; Model Serving + grant capability preflighted; `/Volumes/...` Apps-runtime access spiked | STORAGE-DBX-01..05 (verify), SEED-DBX-01, PREFLIGHT-DBX-01..02, SPIKE-DBX-01a..01e | 6 | XS-S (½ to 1 day; longer if PREFLIGHT escalation) |
| **kdb-1.5** ✅ | LightRAG-Databricks provider adapter (conditional) — **COMPLETE 2026-05-16** | Adapter pattern for `/Volumes/...` access if SPIKE blockers found, AND LightRAG factory adapter (LLM-DBX-03) e2e-tested | STORAGE-DBX-05 (alt path), LLM-DBX-03 (factory adapter validation) | 2 | XS (≤ half-day) |
| **kdb-2** | Databricks App Deploy | App created + grants set + LLM-DBX provider integrated + first deploy reaches RUNNING + Smoke 1+2 PASS (RAG path may be FTS5-only until kdb-2.5 closes) | AUTH-DBX-01..05, LLM-DBX-01/02/04/05, DEPLOY-DBX-01..09, OPS-DBX-01, OPS-DBX-02 | 5 | S (1 day) |
| **kdb-2.5** ⭐ | Re-index LightRAG storage (Databricks Job) | Full corpus (~2000 articles) re-embedded with Qwen3 + entity-extracted with Claude sonnet-4-6; Volume holds MosaicAI-indexed LightRAG storage | SEED-DBX-02, SEED-DBX-03 | 4 | S-M (½ to 1 day wallclock; $20–100 Model Serving cost) |
| **kdb-3** | UAT Close | Smoke 3 (KB-v2 verbatim, full bilingual RAG via MosaicAI) + CONFIG audit (incl. exemption list) + RUNBOOK + sign-off | CONFIG-DBX-01..02, QA-DBX-01..03, OPS-DBX-03..05 | 5 | XS (half-day) |

**Default path:** kdb-1 → kdb-2 → kdb-2.5 → kdb-3 (4 phases). Insert kdb-1.5 between kdb-1 and kdb-2 only if SPIKE-DBX-01a..01e surfaces a blocker OR LLM-DBX-03 factory adapter needs an e2e dry-run before kdb-2.

---

## Phase kdb-1 — UC Volume + Seed + Preflight + Spike

**Goal:** Lay down the storage layer (schema + volume + one-shot user upload), preflight the two highest-risk milestone blockers (Model Serving access + grant capability), AND prove whether `/Volumes/...` is usable from the Apps runtime — before committing to the deploy phase.

**Requirements:** STORAGE-DBX-01..04, STORAGE-DBX-05 (verify only), SEED-DBX-01, PREFLIGHT-DBX-01, PREFLIGHT-DBX-02, SPIKE-DBX-01a..01e

**Phase wave structure:**

- **Wave 1 (preflight, ~30 min):** PREFLIGHT-DBX-01 (Model Serving query smoke against `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b` from a workspace serverless cluster) + PREFLIGHT-DBX-02 (grant capability test). Either ❌ blocks the rest of the phase pending escalation
- **Wave 2 (storage + seed, ~30 min + upload time):** STORAGE-DBX-01..04 + SEED-DBX-01 — create schema + volume + populate sub-directories + user one-shot uploads SQLite (WAL-checkpointed) + images directory from local Hermes-pulled snapshot
- **Wave 3 (spike, 30-min hard timer):** SPIKE-DBX-01a..01e — deploy a throwaway test-app `omnigraph-kb-spike`, run the 5 sub-checks against the populated volume INCLUDING in-app Model Serving call (SPIKE-DBX-01e)

**Success criteria:**

1. PREFLIGHT-DBX-01 ✅ + PREFLIGHT-DBX-02 ✅ (both must pass before Wave 2 starts)
2. `mdlg_ai_shared.kb_v2.omnigraph_vault` volume created with 4 sub-directories populated by one-shot user upload (NO Hermes runtime touchpoint after the snapshot pull)
3. `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data` lists `kol_scan.db` (no `-wal`/`-shm` sidecars); 1-article integrity check passes (queryable, `content_hash` matches source byte-for-byte)
4. `kdb-1-PREFLIGHT-FINDINGS.md` documents PREFLIGHT-01/02 outcomes with evidence (Model Serving response codes + latency, grant SQL output)
5. `kdb-1-SPIKE-FINDINGS.md` answers all 5 sub-checks (01a-01e) with evidence (each sub-check has either ✅ + log excerpt or ❌ + reproduction or `INCONCLUSIVE` if 30-min timer elapsed)
6. `databricks-deploy/RUNBOOK.md` Section 1 (one-shot seed runbook) authored with the exact commands that produced the upload — explicitly NO Hermes-side commands; user runs from local dev box only

**Non-goals:** Production App creation, deploy, grants, LLM provider code work — all in kdb-2. Re-index Job — kdb-2.5. (The kdb-1 spike test-app is throwaway and uses minimal config.)

**Decision gate at end of phase:**

| Outcome | Action |
|---------|--------|
| PREFLIGHT-01 ❌ | Milestone BLOCKED. Likely SP grant gap (CAN_QUERY missing) — escalate. Do NOT proceed to spike or kdb-2 until resolved |
| PREFLIGHT-02 ❌ | Spike CAN proceed (uses pre-existing volume); kdb-2 BLOCKED pending workspace-admin grant escalation |
| All PREFLIGHT ✅ + all SPIKE 01a-01e ✅ | Proceed directly to kdb-2 (4-phase happy path: kdb-1 → kdb-2 → kdb-2.5 → kdb-3) |
| All PREFLIGHT ✅ + ANY SPIKE 01a-01e ❌ | Insert kdb-1.5 (LightRAG storage adapter pattern AND/OR LLM-DBX-03 factory dry-run) |
| All PREFLIGHT ✅ + ANY SPIKE INCONCLUSIVE-at-30-min | Insert kdb-1.5 (don't burn more time investigating; default to adapter). Hard timer rule: phase orchestrator stops the spike at 30 min wall-clock from Wave 3 start; whatever's still INCONCLUSIVE counts as ❌ |

---

## Phase kdb-1.5 — LightRAG-Databricks Provider Adapter (conditional) — ✅ COMPLETE 2026-05-16

> **Verification: PASSED** (21/21 must-haves green per `kdb-1.5-VERIFICATION.md`). 9/9 tests green (5 unit + 4 dry-run against REAL MosaicAI Model Serving). Cost <$0.10. Risk #2 (SDK shape) + Risk #3 (Qwen3 bilingual) resolved PASS. Success criteria #1-#3 PASS; #4 (`app.yaml` wiring) intentionally deferred to kdb-2 DEPLOY-DBX-04 — see VERIFICATION.md note.

**Goal:** Two purposes (either or both, depending on what kdb-1 surfaced):

1. **Storage adapter:** copy-to-/tmp pattern so App can read `/Volumes/...` once at startup, then operate against `/tmp/` — bypassing FUSE / read-only mount issues (if SPIKE-DBX-01a/01b/01c failed)
2. **LightRAG-Databricks factory adapter dry-run:** validate that LLM-DBX-03's `make_llm_func()` + `make_embedding_func()` actually work end-to-end with a real LightRAG `ainsert(small_doc) + aquery("test")` round-trip BEFORE committing to the kdb-2.5 full re-index Job

**Requirements:** STORAGE-DBX-05 (alternative satisfaction path), LLM-DBX-03 (factory adapter validation)

**Success criteria:**

1. (Conditional on storage spike fail) New module `databricks-deploy/startup_adapter.py` (NOT under `kb/`) implements copy-on-startup pattern using either `shutil.copytree` (if FUSE) or `databricks-sdk` `w.files.download_directory` (if Files API only); idempotent across restarts
2. (Always when phase fires) `databricks-deploy/lightrag_databricks_provider.py` (LLM-DBX-03 file) instantiated against MosaicAI endpoints in a small e2e test: pick 5 articles from on-Volume `kol_scan.db`, run `ainsert` + `aquery` against a temporary `/tmp/lightrag_storage_test/`, confirm graphml + vector json files emit correctly with embedding dim 1024
3. Adapter (storage and/or factory) integration documented in `kdb-1.5-VERIFICATION.md`
4. `app.yaml` updated to invoke storage adapter via wrapper shell or pre-uvicorn step (if storage adapter fired)

**Triggered by:** SPIKE-DBX-01a..01e finding 1+ blocker, OR risk #4 (adapter compat) materializing during kdb-1 Wave 3 in-app probe.

**Time-box:** half day total. If LLM-DBX-03 dry-run reveals fundamental LightRAG-Databricks SDK shape mismatch, fall back to small custom HTTP wrapper around Model Serving REST API (still under `databricks-deploy/`, no `kb/` edits beyond exemption list).

---

## Phase kdb-2 — Databricks App Deploy

**Goal:** Stand up `omnigraph-kb` App, integrate MosaicAI provider via `lib/llm_complete.py` + `kg_synthesize.py` (both per CONFIG-EXEMPTIONS.md), get to RUNNING state, prove Smoke 1 + Smoke 2 work end-to-end. NOTE: full RAG round-trip (Smoke 3) is NOT in scope here — that requires the kdb-2.5 re-index to land. Smoke 1+2 use FTS5-only path which works immediately.

**Requirements:** AUTH-DBX-01..05, LLM-DBX-01, LLM-DBX-02, LLM-DBX-04, LLM-DBX-05, DEPLOY-DBX-01..09, OPS-DBX-01, OPS-DBX-02

**Success criteria:**

1. `databricks apps get omnigraph-kb` shows `state: RUNNING` and a non-null URL
2. App SP grants verifiable: `SHOW GRANTS ON CATALOG mdlg_ai_shared TO 'app-omnigraph-kb'` returns USE_CATALOG; same for SCHEMA + READ_VOLUME on volume; `databricks serving-endpoints get-permissions databricks-claude-sonnet-4-6` shows App SP with QUERY (same for embedding endpoint)
3. `lib/llm_complete.py` `databricks_serving` provider branch unit-tested + integrated; `kg_synthesize.py` routes through dispatcher (per LLM-DBX-02); `databricks-deploy/CONFIG-EXEMPTIONS.md` records both edits with diff scope
4. **Smoke 1 PASS:** App URL renders home page after SSO; Apps Logs tab shows zero ERROR during cold start; logs confirm `OMNIGRAPH_BASE_DIR` resolved correctly + 3 LLM env literals (`OMNIGRAPH_LLM_PROVIDER`, `KB_LLM_MODEL`, `KB_EMBEDDING_MODEL`) present
5. **Smoke 2 PASS:** `/api/search?q=AI+Agent` returns ≥3 zh-CN hits; `/api/search?q=langchain&lang=en` returns ≥3 en hits; clicking any article renders detail page with images served via `/static/img/...`. **(RAG path expected degraded to FTS5 fallback at this point — Smoke 3 deferred to kdb-3 post-re-index.)**

**Hard constraints (verified during phase):**

- `app.yaml` at root of `--source-code-path`
- `command:` uses `$DATABRICKS_APP_PORT` substitution
- 3 literal LLM env values present (`OMNIGRAPH_LLM_PROVIDER=databricks_serving`, `KB_LLM_MODEL=...`, `KB_EMBEDDING_MODEL=...`)
- Zero `valueFrom:` for any LLM-related env (Apps SP injection carries auth)
- Zero DeepSeek references in `databricks-deploy/`, `app.yaml`, or `requirements.txt`
- LLM-DBX-02 diff scope strictly limited to `kg_synthesize.py` import + call site swap; broader edits = block

**Phase deliverables:**

- `databricks-deploy/app.yaml` (committed)
- `databricks-deploy/Makefile` (`make deploy`, `make logs`, `make stop` recipes)
- `databricks-deploy/requirements.txt` (no DeepSeek deps)
- `databricks-deploy/lightrag_databricks_provider.py` (final, post-kdb-1.5 spike if applicable)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (records `lib/llm_complete.py` + `kg_synthesize.py` allowed edits)
- `lib/llm_complete.py` (`databricks_serving` branch added; tests added)
- `kg_synthesize.py` (dispatcher routing; minimal diff)
- Apps Logs evidence captured in `kdb-2-SMOKE-EVIDENCE.md`

---

## Phase kdb-2.5 ⭐ — Re-index LightRAG Storage (Databricks Job)

**Goal:** Re-build the LightRAG knowledge graph end-to-end using MosaicAI sonnet-4-6 (entity extraction) + Qwen3-0.6B (embeddings), so post-kdb-3 Smoke 3 KG-mode RAG round-trips return high-quality bilingual results.

**Requirements:** SEED-DBX-02, SEED-DBX-03

**Why a Job, not in-App:**

- Re-index walltime is hours; Apps runtime is request-driven, not suited for hours-long batch
- Job can be tuned for parallelism (multiple Spark tasks → multiple LightRAG `ainsert` calls in flight)
- Cost is bounded + measurable per-Job-run (Model Serving + compute)
- Failure isolation: a single article failing does not impact the App

**Phase structure:**

- **Step 1 (small-batch validation, ~30 min, $1–3 cost):** Define Job, run on first 50 articles. Measure: avg time per `ainsert`, total wallclock, total Model Serving cost. Extrapolate to full corpus (~2000 articles). If extrapolation > 30h or > $200 → **STOP, escalate**: tune batch size, concurrency, or scope down (e.g., recent articles only). Document in `kdb-2.5-SMALLBATCH-FINDINGS.md`.
- **Step 2 (full re-index, half day–1 day wallclock):** Job runs full corpus. `articles` table (~600 KOL) + `rss_articles` table (~1400 RSS). Per-article: `lightrag.ainsert(content)` with single-article exception trap (log + skip + continue, NOT fail-fast). Failed articles list emitted as `kdb-2.5-FAILURES.csv`.
- **Step 3 (post-check, ~30 min):** SEED-DBX-03 sanity (5–10 random entities have dim-1024 vectors; entity names cover zh + en; 2 KG-mode queries — 1 zh, 1 en — return non-empty bilingual responses).

**Success criteria:**

1. Job final state = `SUCCEEDED` (or `SUCCEEDED_WITH_FAILURES` if tolerable failure rate, see below); `databricks jobs runs get <run-id>` confirms
2. `dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/` contains:
   - `vdb_*.json` files (NanoVectorDB output) with embedding vectors of dim 1024
   - `graph_*.graphml` files (NetworkX output) with entity nodes + edges
   - `kv_store_*.json` files (key-value cache)
3. Failure tolerance: ≤ 5% of articles fail re-index (≤ 100 of ~2000). Higher = phase REOPENED for retry / debugging.
4. SEED-DBX-03 post-check: 5–10 random entities verified dim 1024; bilingual coverage; 2 round-trip queries return reasonable answers
5. Total cost recorded in `kdb-2.5-VERIFICATION.md` (extrapolated from Model Serving billing dashboard)

**Phase deliverables:**

- `databricks-deploy/jobs/reindex_lightrag.py` (Job script)
- `databricks-deploy/jobs/reindex_lightrag.yml` (Job resource definition for `databricks bundle deploy`)
- `kdb-2.5-SMALLBATCH-FINDINGS.md` (50-article extrapolation evidence)
- `kdb-2.5-FAILURES.csv` (failed article hashes, if any)
- `kdb-2.5-VERIFICATION.md` (post-check + cost record)

**Decision gate at end of phase:**

| Outcome | Action |
|---------|--------|
| Step 1 extrapolation > 30h OR > $200 | STOP, escalate. Tune (concurrency, scope) and re-run Step 1. Don't fire Step 2 blindly. |
| Step 2 succeeds (≤ 5% failures) | Proceed to kdb-3 |
| Step 2 succeeds with > 5% failures | Phase REOPENED — investigate failure pattern; common causes: corpus quality (truncated bodies, encoding issues) > Model Serving issue. Selectively retry from `kdb-2.5-FAILURES.csv`. |
| Step 3 sanity fail (e.g., embedding dim ≠ 1024, queries return empty) | Phase REOPENED — likely LLM-DBX-03 factory bug or wrong endpoint name. Roll back Job artifacts on Volume, fix factory, re-run Step 1+2 |

**Hard constraints (verified during phase):**

- Job must NOT silently overwrite existing `lightrag_storage/` if previously populated (avoid data loss). First Step 2 run requires explicit empty-target confirmation
- Per-article failures logged with `content_hash` + truncated error message (no PII, no path leak)
- Cost monitored in real-time (alert if Step 2 burn rate exceeds Step 1 extrapolation by > 50%)

---

## Phase kdb-3 — UAT Close

**Goal:** Final smoke (Smoke 3 RAG round-trip — now full bilingual via MosaicAI), CONFIG audit (including exemption list), runbook complete, sign-off.

**Requirements:** CONFIG-DBX-01..02, QA-DBX-01..03, OPS-DBX-03, OPS-DBX-04, OPS-DBX-05

**Success criteria:**

1. **Smoke 3 PASS (KB-v2 verbatim, MosaicAI-backed):**
   - 中文输入 "LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown 答复 + 来源链接
   - 英文输入 "What is the difference between LangGraph and CrewAI?" → 异步 → 英文 markdown 答复 + 来源链接
   - Apps Logs confirm Model Serving sonnet-4-6 + qwen3-embedding both 200
   - Negative-path tests: all 4 reason codes (`kg_disabled` / `kg_credentials_missing` / `kg_credentials_unreadable` / `kg_serving_unavailable`) return HTTP 200 + FTS5 fallback (NEVER 500/502)
2. **CONFIG audit PASS:**
   - `databricks-deploy/CONFIG-EXEMPTIONS.md` exists, lists exactly `lib/llm_complete.py` + `kg_synthesize.py`, with diff scope summary
   - Verification command (per CONFIG-DBX-01) returns empty: `git log <milestone-base>..HEAD --grep '(kdb-' --name-only -- kb/ lib/ | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' | sort -u`
   - `git log --all -p -- databricks-deploy/` audit clean (no DeepSeek tokens / API keys / GCP SA contents)
3. `databricks-deploy/RUNBOOK.md` complete: first-time deploy, one-shot seed (SEED-DBX-01), re-index Job (SEED-DBX-02), App restart, Model Serving troubleshooting (CAN_QUERY missing, endpoint not found, 503/429), kdb-2.5 cost monitoring guide
4. `VERIFICATION-kb-databricks-v1.md` authored with all rev 3 REQs ✅ (or noted as deferred with reasoning); milestone marked complete in `STATE-kb-databricks-v1.md`

**Phase deliverables:**

- `kdb-3-VERIFICATION.md` — checkbox status of all rev 3 REQs with evidence
- `databricks-deploy/RUNBOOK.md` complete
- `databricks-deploy/CONFIG-EXEMPTIONS.md` finalized
- Final state-update commit + sign-off

---

## Wave / parallelization analysis

This milestone is **mostly sequential** (kdb-1 → kdb-2 → kdb-2.5 → kdb-3) because each phase strictly depends on the previous. Within phases, parallelization is limited:

- **kdb-1 internal parallelism:** Wave 1 (preflight) and the user-side snapshot pull (preparing for Wave 2 SEED-DBX-01) can run concurrently — preflight runs in workspace, snapshot pull runs locally. Wave 2 storage commands and Wave 3 spike are sequential because the spike reads what Wave 2 wrote.
- **kdb-1.5 internal parallelism:** storage adapter implementation + LightRAG factory dry-run can run in parallel if both fire (independent files: `startup_adapter.py` vs `lightrag_databricks_provider.py`).
- **kdb-2 internal parallelism:** ACL grants + `lib/llm_complete.py` / `kg_synthesize.py` provider work + `app.yaml` authoring can run in 3 concurrent lanes for ~half the phase, then merge for first deploy.
- **kdb-2.5 internal parallelism:** Step 1 small-batch is mandatorily serial vs Step 2 full re-index. Step 3 post-check can start as soon as Step 2 completes.
- **kdb-3 internal parallelism:** Smoke 3 (manual UAT) + CONFIG audit (git commands) + RUNBOOK authoring are independent; can run concurrently.

No cross-phase parallelization. Phase boundaries are fenced by deploy gates (kdb-1 spike → kdb-2 OK to deploy; kdb-2 RUNNING → kdb-2.5 OK to start Job; kdb-2.5 SUCCEEDED → kdb-3 final UAT).

## Coverage validation (orchestrator hand-driven, per parallel-track caveat)

36 unique REQ items in REQUIREMENTS rev 3 → 36 mapped to phases (table below). 100% coverage.

| REQ-ID | Phase | Verification mechanism |
|--------|-------|------------------------|
| STORAGE-DBX-01 | kdb-1 | `databricks-mcp-server list_schemas mdlg_ai_shared` shows `kb_v2` |
| STORAGE-DBX-02 | kdb-1 | `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` succeeds |
| STORAGE-DBX-03 | kdb-1 | Same `ls` shows 4 sub-dirs |
| STORAGE-DBX-04 | kdb-1 | `databricks fs ls dbfs:/Volumes/.../data` shows `kol_scan.db` only (no sidecars); 1-article integrity check passes |
| STORAGE-DBX-05 | kdb-1 spike OR kdb-1.5 | SPIKE 01a-01e result OR adapter test |
| AUTH-DBX-01..03 | kdb-2 | `SHOW GRANTS ... TO 'app-omnigraph-kb'` |
| AUTH-DBX-04 | kdb-2 | `databricks serving-endpoints get-permissions databricks-claude-sonnet-4-6` shows QUERY (and embedding endpoint) |
| AUTH-DBX-05 | kdb-2 | App URL prompts SSO (manual UAT) |
| LLM-DBX-01 | kdb-2 | `pytest tests/unit/test_llm_complete.py::test_databricks_serving_provider` PASS |
| LLM-DBX-02 | kdb-2 | `git diff` of `kg_synthesize.py` shows minimal import + call-site swap; tests still pass; `databricks-deploy/CONFIG-EXEMPTIONS.md` records edit |
| LLM-DBX-03 | kdb-1.5 | `databricks-deploy/lightrag_databricks_provider.py` instantiated in e2e test; `ainsert + aquery` round-trip succeeds with dim-1024 vectors |
| LLM-DBX-04 | kdb-2 | Manual test: temporarily set `KB_LLM_MODEL` to non-existent endpoint, POST `/synthesize`, confirm HTTP 200 + FTS5 fallback markdown + `kg_serving_unavailable` reason logged |
| LLM-DBX-05 | kdb-2 | `cat databricks-deploy/app.yaml` shows 3 literal env values |
| DEPLOY-DBX-01..06 | kdb-2 | `databricks apps get omnigraph-kb` returns RUNNING + URL + Smoke 1 |
| DEPLOY-DBX-07 | kdb-2 | `cat databricks-deploy/requirements.txt` lists kb runtime deps; ZERO DeepSeek deps |
| DEPLOY-DBX-08 | kdb-2 | `cat databricks-deploy/app.yaml` shows `OMNIGRAPH_LLM_PROVIDER=databricks_serving` literal |
| DEPLOY-DBX-09 | kdb-2 | `grep -E "KB_KG_GCP_SA_KEY_PATH\|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml` returns empty |
| SEED-DBX-01 | kdb-1 (Wave 2) | `databricks fs ls dbfs:/Volumes/.../data` + `/images` show populated state matching local snapshot inventory |
| SEED-DBX-02 | kdb-2.5 | `databricks jobs runs get <run-id>` shows `SUCCEEDED`; `lightrag_storage/` populated with vdb + graphml + kv_store files |
| SEED-DBX-03 | kdb-2.5 | 5–10 random entities verified dim 1024; 2 KG-mode round-trip queries (zh + en) return non-empty answers; documented in `kdb-2.5-VERIFICATION.md` |
| QA-DBX-01..03 | kdb-3 | Smoke 3 evidence in VERIFICATION (covers all 4 reason codes including `kg_serving_unavailable`) |
| CONFIG-DBX-01 | kdb-3 | `git log <milestone-base>..HEAD --grep '(kdb-' --name-only -- kb/ lib/ \| grep -v -E '^lib/llm_complete\.py$\|^kg_synthesize\.py$'` returns empty |
| CONFIG-DBX-02 | kdb-3 | `ls databricks-deploy/` shows all config files including `CONFIG-EXEMPTIONS.md` and `lightrag_databricks_provider.py` |
| PREFLIGHT-DBX-01 | kdb-1 (Wave 1) | Notebook `WorkspaceClient().serving_endpoints.query()` against both endpoints returns HTTP 200 |
| PREFLIGHT-DBX-02 | kdb-1 (Wave 1) | Test grant SQL succeeds (or escalation path documented if denied) |
| SPIKE-DBX-01a | kdb-1 (Wave 3) | `os.path.ismount(...)` + `os.listdir(...)` from test-app |
| SPIKE-DBX-01b | kdb-1 (Wave 3) | `os.makedirs(..., exist_ok=True)` no-raise from test-app with READ VOLUME only |
| SPIKE-DBX-01c | kdb-1 (Wave 3) | `sqlite3.connect("file:.../kol_scan.db?mode=ro", uri=True)` + `SELECT count(*)` succeeds |
| SPIKE-DBX-01d | kdb-1 (Wave 3) | Time test-app start → `/health` 200; < 60s |
| SPIKE-DBX-01e | kdb-1 (Wave 3) | In-app `WorkspaceClient().serving_endpoints.query()` against both endpoints returns HTTP 200 |
| OPS-DBX-01 | kdb-2 | KB-v2 Smoke 1 evidence (双语 UI 切换) |
| OPS-DBX-02 | kdb-2 | KB-v2 Smoke 2 evidence (双语搜索 + 详情页 + UC Volume image render) |
| OPS-DBX-03 | kdb-3 | KB-v2 Smoke 3 evidence (双语 RAG via MosaicAI + 4 reason-code fallbacks) |
| OPS-DBX-04 | kdb-3 | `kdb-3-VERIFICATION.md` authored |
| OPS-DBX-05 | kdb-3 | `databricks-deploy/RUNBOOK.md` complete (no DeepSeek content) |

---

## Risks (top 5)

1. **kdb-1 spike surfaces multiple blockers** → kdb-1.5 cost expands beyond half-day → milestone slips. **Mitigation:** spike scoped to 30-min hard timebox; if 30 min in we have no answers, default to copy-to-/tmp adapter without further spiking.
2. **kdb-2.5 re-index Job time + cost overrun** — small-batch extrapolation underestimates full-corpus cost; full re-index takes > 30h or burns > $200. **Mitigation:** mandatory Step 1 small-batch validation (50 articles, ~30 min, ~$1–3) BEFORE Step 2; STOP-and-tune gate if extrapolation exceeds budget; failure tolerance ≤ 5% (skip + continue, not fail-fast); per-article exception trap; cost monitored in real-time during Step 2.
3. **Qwen3-0.6B embedding bilingual quality** — team has not used this model on the KB corpus before; Chinese retrieval may underperform versus BGE / GTE / Vertex embeddings. **Mitigation:** during kdb-1.5 LLM-DBX-03 dry-run, explicitly run 5 zh-CN + 5 en queries on the small e2e test set; if retrieval results are obviously poor, escalate to user BEFORE kdb-2.5 commits to full corpus re-embedding. Worst-case: swap to BGE (which would require new endpoint creation but preserves the rest of the architecture).
4. **LightRAG ↔ Databricks Model Serving SDK shape mismatch** — LightRAG defaults to OpenAI / Hugging Face callable signatures; Databricks SDK is a thin wrapper that may not match LightRAG's expected `llm_model_func` / `embedding_func` interfaces. **Mitigation:** `databricks-deploy/lightrag_databricks_provider.py` (LLM-DBX-03) is the wrapping layer — written + tested in kdb-1.5 BEFORE kdb-2 / kdb-2.5 commits to it. If mismatch is fundamental, fall back to small custom HTTP wrapper around Model Serving REST API (still under `databricks-deploy/`).
5. **App SP grants are workspace-admin-only operations** → user (`hhu@edc.ca`) may not have admin → grant request adds days. **Mitigation:** closed by **PREFLIGHT-DBX-02** in kdb-1 Wave 1 (test grant on throwaway target proves capability BEFORE kdb-2). If PREFLIGHT-02 ❌: escalate to workspace admin in parallel with kdb-1 Wave 2/3, hold kdb-2 until grants land.

---

## ROADMAP CREATED

4 phases default + conditional kdb-1.5 (5 max) | 36 REQs mapped | All covered ✓

**Revision history:**

- 2026-05-15 rev 3 — Strategic restructure per user constraints #1–#5: ALL LLM via MosaicAI (DeepSeek retired); Hermes runtime-separated; sonnet-4-6 + qwen3-0.6b locked; "zero `kb/` edits" relaxed for `lib/llm_complete.py` + `kg_synthesize.py`. Phase shape: kdb-1 (now includes one-shot SEED-DBX-01) → kdb-1.5 (now includes LLM-DBX-03 factory dry-run scope) → kdb-2 (LLM-DBX provider work + DEPLOY) → **kdb-2.5 NEW** (Re-index Job, $20–100, 8–30h) → kdb-3. Risks restructured: removed DeepSeek-egress risk; added re-index time/cost (#2), Qwen3 bilingual quality (#3), LightRAG-Databricks adapter compat (#4). T-shirt: **S → M**.
- 2026-05-15 rev 2.2 — kb-v2.1-1 KG MODE HARDENING absorbed (commit `eff934f` upstream): added DEPLOY-DBX-09; QA-DBX-03 expanded; PITFALLS B1 severity downgraded.
- 2026-05-15 rev 2.1 — doc self-consistency cleanup.
- 2026-05-15 rev 2 — incorporated user P0/P1/P2 adjustments.
- 2026-05-15 rev 1 — initial draft, 30 REQs / 9 categories.
