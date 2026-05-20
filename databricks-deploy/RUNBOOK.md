# Databricks App Operations Runbook — `omnigraph-kb`

> **Phase:** kdb-3 (kb-databricks-v1 milestone)
> **Audience:** Operator running on Windows + Git Bash, Databricks CLI v0.260+, profile `dev`.
> **Scope:** Production-like operations against the Azure Databricks workspace
> `adb-2717931942638877.17.azuredatabricks.net`, app `omnigraph-kb`, app
> SP-mediated UC volume `mdlg_ai_shared.kb_v2.omnigraph_vault`, MosaicAI Model
> Serving endpoints `databricks-claude-sonnet-4-6` (LLM) +
> `databricks-qwen3-embedding-0-6b` (embeddings, dim=1024).
> **Hard rule (rev 3):** This document references **MosaicAI Model Serving only**.
> No external LLM provider names appear anywhere — see CONFIG-EXEMPTIONS.md for
> the audited exceptions inside the synthesize codepath.

---

## 0 — Prereqs (one-time per machine)

| Check | Command | Expected |
|---|---|---|
| Databricks CLI installed | `databricks --version` | `v0.260.0` or newer |
| Profile `dev` configured | `databricks --profile dev current-user me -o json` | JSON with `userName: "hhu@edc.ca"` |
| Local venv | `ls ../venv/Scripts/python.exe` | exists (used by `make logs`) |
| Bundle deploy preflight | `databricks --profile dev bundle validate -t dev` (run from `databricks-deploy/`) | `Validation OK` |

**Windows Git Bash quirk:** every `databricks` CLI call that carries a
`/Workspace/...` path MUST be prefixed with `MSYS_NO_PATHCONV=1` to suppress
MSYS2 path mangling. The `Makefile` already does this; ad-hoc CLI calls must
do so manually.

---

## 1 — First-time deploy

**Goal:** stand up the app from a clean workspace state. Use this whenever
the workspace `databricks-deploy/` tree is suspect, after `.databricksignore`
changes, or after deleting the app entirely.

### 1.1 Verify Unity Catalog grants (AUTH-DBX-01..03)

These were granted in kdb-2-01 to the app SP. Re-run the inspection to
confirm — no destructive effects.

```bash
make sp-grants
```

Expected output: app SP `client_id` followed by the three GRANT statements.
Run those statements via the Databricks SQL editor or
`mcp__databricks-mcp-server execute_sql` only if any are missing.

### 1.2 Clean deploy

```bash
cd databricks-deploy/
make deploy-clean
```

This runs Pass 0/0b/0c/1/2 (SSG copy + lang flip + project-root staging + sync
× 2) followed by `apps deploy`. Wait for `make deploy-clean` to print the
final `databricks --profile dev apps get omnigraph-kb -o json` block — look for:

```json
{"compute_status":{"state":"ACTIVE"}, "app_status":{"state":"RUNNING"}}
```

Expected wallclock: ~3-5 minutes total (sync ~90s, deploy ~120s, app cold
start ~10-15s once apps deploy returns).

### 1.3 Tail boot logs

```bash
make logs
```

Look for the kdb-3 hydration sequence (see §"Boot log evidence" in
`.planning/phases/kdb-3-uat-close/kdb-3-VERIFICATION.md`):

- `[bootstrap] downloading KB DB ... bytes=20.5MB`
- `[bootstrap] hydrate_lightrag_storage: copied 12 files, total ~71MB`
- `INFO:     Uvicorn running on http://0.0.0.0:8080`
- `INFO:     Application startup complete.`

If any of these are missing, see §"6 Troubleshooting".

### 1.4 Browser SSO smoke

The app sits behind workspace SSO + Private Link, so external `curl` cannot
reach it. Open in Edge logged in as `hhu@edc.ca`:

```
https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/
```

Expected: bilingual KB index page renders (Chinese + English `<span>` pairs).

---

## 2 — Incremental deploy (code change)

**Goal:** redeploy after editing `kb/`, `lib/`, `kg_synthesize.py`, `config.py`,
or files inside `databricks-deploy/` (excluding the `_ssg/` regenerated tree).

```bash
cd databricks-deploy/
make deploy
```

Difference from `deploy-clean`: skips the recursive workspace wipe. Safe to
re-run on any commit. The Pass 0c stage rebuilds `databricks-deploy/lib/` +
`config.py` + `kg_synthesize.py` from the project root each time, so stale
copies cannot survive.

**When `make deploy` is NOT enough** — use `make deploy-clean`:

- you edited `.databricksignore`
- you deleted files from `kb/`, `lib/`, or project root that should also
  disappear from the workspace
- the previous deploy left the workspace in a partial state (e.g. CLI killed
  mid-sync)

---

## 3 — One-shot seed (SEED-DBX-01)

**Status (2026-05-20):** the UC volume `mdlg_ai_shared.kb_v2.omnigraph_vault`
is already seeded with `data/kol_scan.db` (172-row FTS5), `images/`, and
`lightrag_storage/` (12 files / 71MB) from the kdb-1.5/kdb-2.5 phases. SEED-DBX-01
is therefore one-shot **only on a fresh workspace** — for the existing
production target it is a no-op.

If you ever need to re-seed (e.g. new region, new workspace):

1. Pre-flight: confirm the target volume is empty.

   ```bash
   databricks --profile dev fs ls "dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/"
   ```

   Expected on a fresh volume: empty list. If files exist and you intend to
   overwrite, run §6 ("force-overwrite") path of the re-index Job — do NOT
   delete from the CLI.

2. Push the source-of-truth artefacts into the volume via `databricks fs cp`:

   ```bash
   # KB DB (FTS5)
   MSYS_NO_PATHCONV=1 databricks --profile dev fs cp \
     ./kb/data/kol_scan.db \
     dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db

   # Images directory (recursive)
   MSYS_NO_PATHCONV=1 databricks --profile dev fs cp -r \
     ./kb/images \
     dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images

   # LightRAG storage (recursive)
   MSYS_NO_PATHCONV=1 databricks --profile dev fs cp -r \
     ./kb/lightrag_storage \
     dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage
   ```

3. Verify counts:

   ```bash
   databricks --profile dev fs ls "dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/" | wc -l
   ```

   Expected: ≥10 files (vdb_chunks.json, vdb_entities.json, vdb_relationships.json,
   graph_chunk_entity_relation.graphml, kv_store_*.json × N).

4. Restart the app to pick up the new hydration:

   ```bash
   databricks --profile dev apps stop omnigraph-kb
   databricks --profile dev apps start omnigraph-kb
   ```

   `_db_bootstrap.py` will re-download the volume contents to `/tmp` on the
   next cold start.

---

## 4 — Re-index Job (SEED-DBX-02 / kdb-2.5)

**Goal:** rebuild the LightRAG vector + graph stores from a populated
`kol_scan.db` after you have ingested new articles or changed embedding
dimensions. The Bundle defines three Jobs in `jobs/reindex_lightrag.yml` —
ALWAYS run them in order.

### 4.1 Deploy the Bundle (registers Jobs)

```bash
cd databricks-deploy/
databricks --profile dev bundle deploy -t dev
```

Verifies + uploads `jobs/reindex_lightrag.py` and registers the three Jobs
under user identity `hhu@edc.ca` (D-03 — Bundle deploys as user, app keeps
SP identity for runtime READ_VOLUME).

### 4.2 Step 1 — smallbatch (50 articles, ~30 min)

ALWAYS run this first. Gates whether Step 2 is safe.

```bash
databricks --profile dev bundle run kdb_2_5_reindex_smallbatch -t dev
```

Outputs land at
`/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-smallbatch-storage/`
— a SEPARATE working_dir from production `lightrag_storage/`, so re-running
is safe (idempotent on the smallbatch dir; `--force-overwrite` is set in
defaults).

After completion, review the operator findings doc
(`.planning/phases/kdb-2.5-reindex/kdb-2.5-SMALLBATCH-FINDINGS.md`). Do not
proceed to Step 2 unless the gate passes:

```
cost_extrap < $200  AND  wallclock_extrap < 30h  AND  failure_rate < 5%
```

If any of those fail, stop and triage — likely root causes are MosaicAI
endpoint throughput (cost), individual article failures (failure rate), or
serial bottleneck (wallclock). Do NOT silently raise the gate.

### 4.3 Step 2 — fullreindex (all candidates, hard ceiling 30h)

```bash
databricks --profile dev bundle run kdb_2_5_reindex_fullrun -t dev
```

The Job has `--filter-mode strict` and **no** `--force-overwrite` in the
defaults — it will fail loudly if `lightrag_storage/` is non-empty (D-07).
This is intentional. If you have a deliberate reason to overwrite production:

```bash
databricks --profile dev bundle run kdb_2_5_reindex_fullrun -t dev \
  --params '["--mode","fullreindex","--filter-mode","strict","--force-overwrite"]'
```

The Job is resumable — progress CSV at
`/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-fullrun-progress.csv`
records each completed article (per D-06). Re-running picks up where the
previous attempt left off.

### 4.4 Step 3 — postcheck

```bash
databricks --profile dev bundle run kdb_2_5_reindex_postcheck -t dev
```

Read-only. Validates final lightrag_storage/ shape (file count, JSON
parseability, vdb dimensions). Should finish in <30 minutes. Report goes to
`/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-postcheck.json`.

### 4.5 Re-deploy the App after re-index

The app caches the hydrated LightRAG storage at `/tmp` on cold start.
After a successful re-index, you must restart the app to pick up the new
graph:

```bash
databricks --profile dev apps stop omnigraph-kb
databricks --profile dev apps start omnigraph-kb
```

---

## 5 — App lifecycle

| Action | Command |
|---|---|
| Start | `databricks --profile dev apps start omnigraph-kb` |
| Stop | `databricks --profile dev apps stop omnigraph-kb` (or `make stop`) |
| Status (JSON) | `databricks --profile dev apps get omnigraph-kb -o json` |
| List deployments | `databricks --profile dev apps list-deployments omnigraph-kb` |
| Logs (15s snapshot) | `make logs` |
| Logs (live tail) | `make logs-tail` |
| Logs (filtered tail) | `make logs-tail FILTER=ERROR` |

**Restart pattern (after env var change in `app.yaml`):** there is no
`apps restart` subcommand on CLI v0.260. Use `make deploy` to push the new
`app.yaml`, then the app auto-restarts on the new deployment. If you only
want to bounce the runtime without redeploying:

```bash
databricks --profile dev apps stop omnigraph-kb && \
databricks --profile dev apps start omnigraph-kb
```

---

## 6 — Troubleshooting

### 6.1 MosaicAI Model Serving — endpoint not found

**Symptom in logs:**
```
RESOURCE_DOES_NOT_EXIST: Endpoint with name 'databricks-claude-sonnet-4-6' not found
```

**Cause:** the workspace lost the foundation-model entitlement, OR a typo in
`KB_LLM_MODEL` / `KB_EMBEDDING_MODEL` env var in `app.yaml`.

**Fix:**

```bash
# Confirm endpoint exists
databricks --profile dev serving-endpoints list -o json | grep -E '(claude-sonnet-4-6|qwen3-embedding-0-6b)'
```

If the LLM endpoint is missing, contact the workspace admin — the
foundation-models entitlement is a per-workspace setting, not a per-app
grant. If only `databricks-qwen3-embedding-0-6b` is missing, embedding
calls will silently return empty (dim=0), and synthesize will degrade to
`confidence=no_results`. Check `app.yaml` env vars match the active
endpoint names exactly.

### 6.2 MosaicAI — `CAN_QUERY` permission missing

**Symptom in logs:**
```
PERMISSION_DENIED: User does not have CAN_QUERY on serving endpoint ...
```

**Cause:** the app SP lacks `CAN_QUERY` on one of the two MosaicAI endpoints
(this should NEVER happen for the system foundation models — they are
workspace-public — but custom endpoints behave differently).

**Fix:** grant via Databricks SDK or workspace UI Permissions tab. The two
required endpoints are:

- `databricks-claude-sonnet-4-6` (LLM)
- `databricks-qwen3-embedding-0-6b` (embeddings)

For both, confirm `CAN_QUERY` is granted to the app SP `client_id`
(retrieve via `make sp-grants`).

### 6.3 MosaicAI — 503 / 429 (throttling)

**Symptom in logs:**
```
TooManyRequestsException: 429 Too Many Requests
ServiceUnavailable: 503
```

**Cause:** request burst above provisioned-throughput unit (PTU) ceiling
during synthesize batches or re-index runs.

**Fix:**

- **Synthesize path** — single user-facing requests rarely hit this.
  `kg_synthesize.py` already retries via `tenacity` with exponential backoff
  (see `lib/llm_complete.py`). Confirm by re-issuing the query; if it
  succeeds on the second attempt, no action needed.
- **Re-index path** — Step 2 fullrun is the throughput-heavy workload. If
  503/429 dominate the progress CSV, pause and contact workspace admin to
  raise PTU. Resuming is safe (D-06 progress CSV).
- **Both paths** — confirm no other workspace tenants are hitting the same
  endpoint at the same time. The system foundation-model endpoints are
  shared across the workspace.

### 6.4 LightRAG storage empty / `[no-context]` answer

**Symptom:** every synthesize call returns
`{"confidence": "no_results", "markdown": "[no-context] ..."}` for queries
that should have hits.

**Cause:** the `_db_bootstrap.py` boot script failed to hydrate
`/tmp/omnigraph_vault/lightrag_storage/` — typically due to UC volume
permission drift OR `RAG_WORKING_DIR` env var mismatch.

**Diagnostic:**

```bash
make logs FILTER=hydrate_lightrag_storage
```

Expected log:
```
[bootstrap] hydrate_lightrag_storage: copied 12 files, total ~71MB
```

If you see `0 files` or `permission denied`:

1. Confirm app SP still has `READ_VOLUME` (re-run `make sp-grants` and the
   `GRANT READ VOLUME` statement).
2. Confirm `KB_VOLUME_LIGHTRAG_DIR` in `app.yaml` matches the actual
   volume path:
   `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage`.
3. Confirm `RAG_WORKING_DIR` matches the local target read by `kb.config`
   and `kg_synthesize.py`: `/tmp/omnigraph_vault/lightrag_storage`.

### 6.5 KB DB hydration failure

**Symptom:** `/health` returns `kb_db_path: /tmp/kol_scan.db` but
`/api/articles` returns 500 with `OperationalError: no such table`.

**Cause:** `_db_bootstrap.py` started but `w.files.download(KB_VOLUME_DB_PATH)`
returned a partial / corrupted file.

**Fix:**

```bash
# Tail the boot log
make logs FILTER=KB
```

Expected:
```
[bootstrap] downloading KB DB from /Volumes/.../kol_scan.db -> /tmp/kol_scan.db
[bootstrap] KB DB ready: bytes=20500000+
```

If bytes are far below 20MB, the volume copy is incomplete. Re-stop +
re-start the app to retry. If the failure persists, fall back to §3 (re-seed
`data/kol_scan.db` via `databricks fs cp`).

### 6.6 Synthesize HTTP 5xx / job stuck in `running`

**Symptom:** `POST /api/synthesize` returns 202 with `job_id` but
`GET /api/synthesize/{job_id}` returns `state: running` indefinitely (>2 min).

**Diagnostic:** check the LightRAG worker thread for an unhandled exception.

```bash
make logs FILTER=synthesize
```

Common patterns:

- `LLM provider not configured` — `OMNIGRAPH_LLM_PROVIDER` env var not set
  or set to a value other than `databricks_serving`. Fix in `app.yaml` and
  redeploy.
- `embedding dim mismatch (3072 vs 1024)` — embedding dispatcher fell back
  to a stale Vertex path. Confirm `KB_EMBEDDING_MODEL=databricks-qwen3-embedding-0-6b`
  in `app.yaml`. The Qwen3 endpoint produces dim=1024.
- silent — kg-mode-hardening rev probably surfaced a non-`databricks-claude-sonnet-4-6`
  edge. File a bug; do not patch the dispatcher in production without first
  reproducing in `kdb-2.5-smallbatch` to measure the cost.

### 6.7 Workspace deploy fails: `/Workspace/...` path errors

**Symptom (Windows Git Bash):**
```
Error: failed to open ... /c/Program Files/Git/Workspace/Users/...
```

**Cause:** missing `MSYS_NO_PATHCONV=1` prefix on the CLI call.

**Fix:** the `Makefile` targets already have this prefix. For ad-hoc CLI
invocations, prefix every `databricks --profile dev sync` /
`databricks --profile dev apps deploy` / `databricks --profile dev workspace`
call.

---

## 7 — kdb-2.5 cost monitoring

The re-index Job is the only workload in this milestone that meaningfully
consumes MosaicAI tokens. Two cost ceilings are gated:

| Ceiling | Source | Enforcement |
|---|---|---|
| Step-1 smallbatch wallclock | `timeout_seconds: 7200` in `jobs/reindex_lightrag.yml` | Job auto-fails at 2h |
| Step-2 fullrun wallclock | `timeout_seconds: 108000` in `jobs/reindex_lightrag.yml` | Job auto-fails at 30h |
| Step-1 → Step-2 cost gate | Operator-reviewed in SMALLBATCH-FINDINGS.md | Manual; `cost_extrap < $200` |

**How to read actual cost** post-Step-2:

1. Open the Step-2 run in the Databricks Jobs UI.
2. Click "Compute → DBU usage" — for serverless this is what you pay.
3. Multiply DBUs by the workspace serverless rate (Azure Pricing Calculator).
4. The MosaicAI token cost is reported in
   `/Volumes/.../output/kdb-2.5-fullrun-progress.csv` at column
   `cost_running_total_usd`.

If the running total in the progress CSV exceeds $200 and Step-2 is still
running, stop the Job — D-07 says fail loudly, the same applies to operator
intervention:

```bash
# Get run_id from `bundle run` output, then:
databricks --profile dev jobs cancel-run --run-id <RUN_ID>
```

The progress CSV preserves state — re-running picks up where it stopped.

**Synthesize-time cost is bounded** by user query volume. A single Smoke 3
ZH round-trip costs ~$0.005 (one Claude Sonnet 4.6 call + one embedding
call against ~10 retrieved chunks). Burst protection comes from the async
job queue + tenacity retries; no separate cost ceiling is enforced.

---

## 8 — Decision references (kdb-2.5 + kdb-3)

These locked decisions inform every operational choice above. Do not
deviate without first amending the originating ROADMAP doc.

| Decision | Anchor |
|---|---|
| **D-rev3-01** — MosaicAI Model Serving is the only LLM/embedding provider | ROADMAP-kb-databricks-v1.md §"Locked decisions" |
| **D-rev3-02** — Boot-time hydration via `_db_bootstrap.py`, not auto-FUSE | ROADMAP §"Decision rev-3" |
| **D-rev3-03** — Async synthesize job pattern (POST 202 + job_id polling) | kb-v2.2 + kdb-2 ROADMAPs |
| **D-rev3-04** — CONFIG-EXEMPTIONS audit (kdb-3 row 3 = approved deviation) | `databricks-deploy/CONFIG-EXEMPTIONS.md` |
| **D-kdb2-01** — Pass 0/0b/0c/1/2 sync architecture | Makefile + kdb-2-04-SUMMARY.md |
| **D-kdb2.5-01** — Bundle deploys as user; app SP READ_VOLUME only | `databricks.yml` + `jobs/reindex_lightrag.yml` |
| **D-06** — Re-index resumability via progress CSV | `jobs/reindex_lightrag.py` |
| **D-07** — `--force-overwrite` opt-in only; default fails loud | `jobs/reindex_lightrag.yml` |

---

## 9 — Quick reference card

```bash
# Daily ops
make logs                                     # 15s snapshot
make logs-tail                                # live tail
make logs-tail FILTER=ERROR                   # live tail filtered

# Deploy
cd databricks-deploy/ && make deploy          # incremental
cd databricks-deploy/ && make deploy-clean    # nuke + sync + deploy

# App lifecycle
databricks --profile dev apps start omnigraph-kb
databricks --profile dev apps stop omnigraph-kb
databricks --profile dev apps get omnigraph-kb -o json

# Re-index (3 steps, in order)
cd databricks-deploy/ && databricks --profile dev bundle deploy -t dev
databricks --profile dev bundle run kdb_2_5_reindex_smallbatch -t dev
# review SMALLBATCH-FINDINGS.md, gate-check, then:
databricks --profile dev bundle run kdb_2_5_reindex_fullrun -t dev
databricks --profile dev bundle run kdb_2_5_reindex_postcheck -t dev

# Restart app after re-index
databricks --profile dev apps stop omnigraph-kb && \
  databricks --profile dev apps start omnigraph-kb
```

---

*RUNBOOK end. Last updated 2026-05-20 by kdb-3 phase close.*
