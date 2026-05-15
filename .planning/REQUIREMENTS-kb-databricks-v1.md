# Requirements — kb-databricks-v1

> Parallel-track milestone. Sibling: REQUIREMENTS-KB-v2.md, REQUIREMENTS-Agentic-RAG-v1.md, REQUIREMENTS-v3.5-Ingest-Refactor.md. Main `REQUIREMENTS.md` is owned by v3.4 / v3.5 main track and is **untouched** by this milestone.
>
> Per `feedback_parallel_track_gates_manual_run.md`: gsd-tools.cjs init does NOT recognize suffix files; orchestrator hand-drives every gate.

## v1 Requirements

Requirements grouped by category. REQ-ID format: `[CATEGORY]-NN`. Continuation of KB-v2's `STORAGE/AUTH/...` namespace is intentional — these are NEW requirements unique to the Databricks deploy target, NOT a re-statement of KB-v2.

### STORAGE — UC Volume + data layout

- [ ] **STORAGE-DBX-01**: UC schema `mdlg_ai_shared.kb_v2` exists in workspace, owned by `hhu@edc.ca`
- [ ] **STORAGE-DBX-02**: UC managed volume `omnigraph_vault` created under `mdlg_ai_shared.kb_v2`
- [ ] **STORAGE-DBX-03**: Volume layout populated with 4 sub-directories: `/data`, `/images`, `/lightrag_storage`, `/output` (initial empty markers OK)
- [ ] **STORAGE-DBX-04**: `data/kol_scan.db` synced to Volume from Hermes snapshot, with WAL pre-checkpointed and `-wal`/`-shm` sidecars stripped
- [ ] **STORAGE-DBX-05**: Volume content readable from App container at path `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` (FUSE mount confirmed) OR via `databricks-sdk` Files API with documented fallback adapter

### AUTH — App service principal grants

- [ ] **AUTH-DBX-01**: App service principal `app-omnigraph-kb` has `USE CATALOG` on `mdlg_ai_shared`
- [ ] **AUTH-DBX-02**: App SP has `USE SCHEMA` on `mdlg_ai_shared.kb_v2`
- [ ] **AUTH-DBX-03**: App SP has `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` (no `WRITE VOLUME` in v1)
- [ ] **AUTH-DBX-04**: App SP has `READ` on workspace secret scope `omnigraph-kb`
- [ ] **AUTH-DBX-05**: App access gated by Databricks workspace SSO (Apps default; no anonymous access)

### SECRETS — DeepSeek API key injection

- [ ] **SECRETS-DBX-01**: Workspace secret scope `omnigraph-kb` exists (created via `databricks secrets create-scope`)
- [ ] **SECRETS-DBX-02**: Secret key `deepseek_api_key` populated in scope (via `databricks secrets put-secret`)
- [ ] **SECRETS-DBX-03**: App resource of type Secret added (binds `omnigraph-kb`/`deepseek_api_key` to a resource key)
- [ ] **SECRETS-DBX-04**: `app.yaml` resolves `DEEPSEEK_API_KEY` env var via `valueFrom: <resource-key>` (NOT `value:` literal)
- [ ] **SECRETS-DBX-05**: Audit `git log --all -p -- app.yaml` shows zero literal `sk-...` token strings ever

### DEPLOY — App create + app.yaml + first deploy

- [ ] **DEPLOY-DBX-01**: App `omnigraph-kb` created via `databricks apps create omnigraph-kb`
- [ ] **DEPLOY-DBX-02**: `app.yaml` lives at root of `--source-code-path` (NOT in nested subdirectory)
- [ ] **DEPLOY-DBX-03**: `app.yaml` `command:` invokes uvicorn with `--port $DATABRICKS_APP_PORT` substitution (NOT hardcoded `:8766`)
- [ ] **DEPLOY-DBX-04**: `app.yaml` `env:` list sets `OMNIGRAPH_BASE_DIR` (literal `/Volumes/.../omnigraph_vault` OR `/tmp` if adapter pattern) and `DEEPSEEK_API_KEY` (`valueFrom:`)
- [ ] **DEPLOY-DBX-05**: First `databricks apps deploy omnigraph-kb` reaches `RUNNING` state within 20 min default timeout
- [ ] **DEPLOY-DBX-06**: App URL returns 200 on `/` after workspace SSO

### CONFIG — zero `kb/` code changes invariant

- [ ] **CONFIG-DBX-01**: `git diff main..HEAD -- kb/` returns empty across this milestone (purely env-var + deploy-config delivery)
- [ ] **CONFIG-DBX-02**: All Databricks-target config lives in `databricks-deploy/` directory at repo root: `app.yaml`, `databricks.yml` (if bundle used), `Makefile` recipes, runbook docs

### SYNC — Hermes → UC Volume manual flow

- [ ] **SYNC-DBX-01**: 5-step manual sync runbook documented in `databricks-deploy/RUNBOOK.md`: SSH snapshot from Hermes → WAL checkpoint → sidecar cleanup → `databricks fs cp -r --overwrite` → App restart
- [ ] **SYNC-DBX-02**: Initial snapshot executed once during kdb-1, articles + lightrag state visible in Volume after first sync
- [ ] **SYNC-DBX-03**: Runbook re-executed after a deliberate Hermes-side change (e.g., 1 new article ingested), new article appears in App after restart

### QA — /synthesize round-trip with DeepSeek

- [ ] **QA-DBX-01**: `POST /synthesize {query}` returns `202 + job_id`, polling endpoint returns markdown answer (KB-v2 D-19 contract preserved across deploy targets)
- [ ] **QA-DBX-02**: Underlying call to `kg_synthesize.synthesize_response()` succeeds (KB-v2 C1 contract preserved); LLM call routes to `api.deepseek.com` (verified via App log line)
- [ ] **QA-DBX-03**: Negative-path: simulate LightRAG storage absence → `/synthesize` returns FTS5-fallback markdown with `confidence: "fts5_fallback"`, NOT 500

### SPIKE — kdb-1 viability gate

- [ ] **SPIKE-DBX-01**: kdb-1 spike answers all 5 viability questions (Volume FUSE mount? `os.makedirs` on read-only mount? SQLite WAL on Volume? Cold-start time? Apps→DeepSeek egress?). Answers committed to `kdb-1-SPIKE-FINDINGS.md`. If any blocker → trigger kdb-1.5.

### OPS — smoke tests + sign-off

- [ ] **OPS-DBX-01**: Smoke 1 PASS — App reachable + reads UC Volume + zero ERROR in `journalctl`-equivalent (Apps Logs tab) during cold start
- [ ] **OPS-DBX-02**: Smoke 2 PASS — search returns hits in zh-CN + en, article detail renders incl. images
- [ ] **OPS-DBX-03**: Smoke 3 PASS — RAG Q&A round-trips + DeepSeek key resolved (no 401) + fallback fires correctly
- [ ] **OPS-DBX-04**: kdb-3 verification report `VERIFICATION-kb-databricks-v1.md` cites all OPS smokes with evidence (screenshots, log excerpts, curl outputs)
- [ ] **OPS-DBX-05**: User-facing runbook `databricks-deploy/RUNBOOK.md` covers: first-time deploy, manual sync, App restart-after-sync, secret rotation, troubleshoot common errors (PERMISSION_DENIED, valueFrom typo, FUSE mount missing)

## Future Requirements (deferred)

Tracked for v2 / v2.x but explicitly NOT in scope for v1:

- **v2 — Foundation Model swap (FM-DBX-01..0N):** DeepSeek → `databricks-claude-sonnet-4-6` for both Q&A and ingest paths, single cutover, secret scope retired in favor of model-serving auth
- **v2 — Automated sync (SYNC-AUTO-DBX-01..0N):** Workflow / Job replacing manual `databricks fs cp`; design phase + Hermes-side push or workspace-side pull decided
- **v2 — Per-user OBO auth (OBO-DBX-01..0N):** `X-Forwarded-Access-Token` for audit + private documents
- **v2 — Concurrent-write safety (CONC-DBX-01..0N):** atomic write_json upstream patch OR adapter pattern; needed only if App ever writes to Volume
- **v3 — Ingest pipeline migration (INGEST-DBX-01..0N):** daily-ingest cron → Workflow + Jobs; scrape providers re-evaluated for Apps runtime constraints

## Out of Scope (v1 — explicit exclusions with reasoning)

| Item | Why excluded |
|------|--------------|
| **SQLite → Delta migration** | SQLite is a file, not a table. Migrating = rewriting every SQL query in `kb/`, `omnigraph_search/`, `kg_synthesize.py`. Months of work. Tracked for v2+ only if a concrete pain point materializes. |
| **Foundation Model `databricks-claude-sonnet-4-6` swap** | Bundled with ingest-LLM swap in v2 — both Q&A and ingest LLMs cut over together for consistency. |
| **Public access / zero-login KB on Databricks** | Apps gates on workspace SSO. Public access happens on Aliyun deploy (KB-v2 / kb-4). |
| **Hermes sunset** | Ingest pipeline stays on Hermes; Hermes remains upstream writer. |
| **Ingest pipeline on Databricks** | Daily ingest = scheduled work + LLM + scrape; Apps cannot run scheduled scripts (would need Workflows + Jobs). Big lift, separate milestone. |
| **Per-user OBO auth** | All v1 users see same KB; no row filtering. v2 if private documents added. |
| **Ingest-side LightRAG `ainsert()` to UC Volume** | Requires Hermes to mount UC Volume (auth + driver). v1 keeps ainsert on Hermes local fs, then user `databricks fs cp` snapshot up. |
| **Apps horizontal scaling / multi-instance** | Single instance; LightRAG `write_json` is non-atomic (verified `lightrag/utils.py:1255`). |
| **Modifying `kb/` source tree** | v1 hard-rule: zero `kb/` edits. Delivered purely via env-var + deploy config. CONFIG-DBX-01 enforces. |

## Traceability (filled by ROADMAP)

| REQ-ID | Phase |
|--------|-------|
| STORAGE-DBX-01..04 | kdb-1 |
| STORAGE-DBX-05 | kdb-1 (verify) + conditional kdb-1.5 (fix) |
| AUTH-DBX-01..05 | kdb-2 |
| SECRETS-DBX-01..04 | kdb-2 |
| SECRETS-DBX-05 | kdb-3 (audit) |
| DEPLOY-DBX-01..06 | kdb-2 |
| CONFIG-DBX-01..02 | kdb-3 (final audit) |
| SYNC-DBX-01..02 | kdb-1 |
| SYNC-DBX-03 | kdb-3 |
| QA-DBX-01..03 | kdb-3 |
| SPIKE-DBX-01 | kdb-1 |
| OPS-DBX-01 | kdb-2 |
| OPS-DBX-02 | kdb-2 |
| OPS-DBX-03..05 | kdb-3 |

## Last Updated

2026-05-15 — Initial REQs drafted in main session by orchestrator (no roadmapper agent — express path per user direction). 30 REQs across 9 categories, mapped to 3 phases with conditional kdb-1.5.
