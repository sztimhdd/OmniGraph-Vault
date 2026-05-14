# ARCHITECTURE — Raw Materials

> Pulled 2026-05-14 by main session. Combines Apps Cookbook patterns + LightRAG storage analysis + v1 sync-strategy options.

## 1. Read-side topology — `omnigraph-kb` Databricks App

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Databricks Apps runtime (per-App container, Linux, Python 3.11 base)     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ FastAPI app (kb/api/main.py — UNCHANGED from KB-v2)                │  │
│  │   ├─ command:  uvicorn app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT │
│  │   ├─ port:     8080 (substituted from DATABRICKS_APP_PORT)          │  │
│  │   ├─ env:      OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault │
│  │   │            DEEPSEEK_API_KEY (valueFrom: secret)                  │  │
│  │   │            DATABRICKS_HOST, DATABRICKS_CLIENT_ID/SECRET (auto)   │  │
│  │   └─ Routes:   /                  → SSG fallback                     │  │
│  │                /api/articles      → SQLite read                      │  │
│  │                /api/article/{h}   → SQLite + filesystem read         │  │
│  │                /api/search        → SQLite FTS5                      │  │
│  │                /static/img/{h}/*  → StaticFiles mount on Volume      │  │
│  │                /synthesize        → kg_synthesize.synthesize_response │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                            │                                              │
│       reads via FUSE       ▼                                              │
└────────────────────────────┼──────────────────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────────────────┐
│ UC Volume: /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault   (managed)      │
│  ├─ /data/kol_scan.db       (SQLite, WAL-checkpointed before upload)      │
│  ├─ /images/{hash}/...      (PNG/JPEG + final_content.md per article)     │
│  ├─ /lightrag_storage/...   (4 storage backends: kv/networkx/vdb)         │
│  └─ /output/                (run output, optional)                        │
└───────────────────────────────────────────────────────────────────────────┘
                             ▲
                             │ Hermes → UC sync (3 options below)
                             │
┌────────────────────────────┴──────────────────────────────────────────────┐
│ Hermes prod (WSL2 Linux, no changes for kb-databricks-v1)                 │
│  ~/.hermes/omonigraph-vault/                                              │
└───────────────────────────────────────────────────────────────────────────┘
```

## 2. Hermes → UC Volume sync — 3 options

User locked v1 default = **Option A (manual)**. The other two are documented for v2 planning.

### Option A — Manual user-driven `databricks fs cp` (v1 LOCKED)

```bash
# On Windows dev box, after pulling fresh Hermes snapshot via scp / rsync:
LOCAL_SNAPSHOT=~/Desktop/hermes-omnigraph-snapshot
VOLUME=dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault

databricks fs cp -r --overwrite "$LOCAL_SNAPSHOT/data" "$VOLUME/data"
databricks fs cp -r --overwrite "$LOCAL_SNAPSHOT/images" "$VOLUME/images"
databricks fs cp -r --overwrite "$LOCAL_SNAPSHOT/lightrag_storage" "$VOLUME/lightrag_storage"
```

**Pros:**
- Zero infrastructure to build / maintain in v1
- User controls timing — refresh KB on demand, no surprise mid-day
- Easy rollback: keep last 3 local snapshot dirs, `databricks fs cp` whichever
- Idempotent — `--overwrite` makes it safe to re-run

**Cons:**
- ~Manual. Forgettable. KB will go stale if user travels / busy
- Network bandwidth from Windows dev box → workspace; could be slow on large `/images/` directory (94 articles → not a problem yet; 5000 articles → maybe)
- No history / change log — overwrites in place
- App must be restarted (or at least re-loaded) after sync to pick up new state if using copy-to-/tmp pattern (kdb-1.5)

**Failure modes:**
- Partial sync: `databricks fs cp -r` is not transactional. If interrupted mid-dir, App reads inconsistent state. Mitigation: sync to staging path first, then atomic rename — but `databricks fs` lacks an atomic-rename primitive. Alternative: use `--overwrite` + accept that "overwrite during App reads" may surface stale-but-consistent reads, since each file is overwritten atomically by the underlying storage.

**Pre-sync checklist (v1 runbook):**
1. SSH to Hermes, snapshot to local: `scp -r hermes:~/.hermes/omonigraph-vault/ ~/Desktop/hermes-snapshot/`
2. WAL-checkpoint SQLite: `sqlite3 ~/Desktop/hermes-snapshot/data/kol_scan.db "PRAGMA wal_checkpoint(TRUNCATE);"`
3. Delete `-wal`/`-shm` sidecars: `rm -f ~/Desktop/hermes-snapshot/data/kol_scan.db-{wal,shm}`
4. `databricks fs cp -r --overwrite` to Volume
5. Restart App: `databricks apps stop omnigraph-kb && databricks apps start omnigraph-kb`

### Option B — Workspace Job triggered by manual button (v2)

```yaml
# databricks.yml job definition
resources:
  jobs:
    sync_omnigraph_to_volume:
      name: "[sync] OmniGraph snapshot → UC Volume"
      tasks:
        - task_key: pull_and_sync
          notebook_task:
            notebook_path: ./notebooks/sync_from_hermes.py
```

Notebook calls Hermes via SSH-over-MCP / SFTP / GitHub release API; pulls snapshot; uploads to Volume.

**Pros:** centralized, audit trail in workspace, button-click trigger
**Cons:** requires Hermes outbound credentials in workspace secrets; SSH from serverless compute is fiddly; needs design phase

### Option C — Continuous push from Hermes (v2+)

Hermes-side cron writes directly to UC Volume after each ingest cycle, using `databricks-sdk` against the workspace.

**Pros:** zero manual overhead, near-realtime KB freshness
**Cons:** Hermes needs workspace PAT or OAuth creds (security surface widening); requires Hermes-side env update; can't "stage" changes for review; adds another failure point to the daily-ingest cron

### Decision

v1 = **Option A**. Re-evaluate once user does manual sync 5+ times and pain accumulates.

## 3. App service principal flow — Apps runtime → UC Volume

From Apps Cookbook + MS Learn:

```
1. App is created with `databricks apps create omnigraph-kb`
   → Apps service auto-creates Service Principal `app-omnigraph-kb`
   → SP client_id + client_secret stored in workspace, NEVER exposed in app config

2. At App start, Apps runtime injects into the container env:
   DATABRICKS_CLIENT_ID  = <SP client id>
   DATABRICKS_CLIENT_SECRET = <SP client secret>
   DATABRICKS_HOST       = adb-2717931942638877.17.azuredatabricks.net
   DATABRICKS_APP_PORT   = 8080

3. Application code:
   from databricks.sdk import WorkspaceClient
   w = WorkspaceClient()   # default config picks up the 3 env vars above

4. UC Volume access:
   - POSIX read at /Volumes/... (FUSE mount, if Apps runtime mounts it)
   - OR programmatic: w.files.download("/Volumes/...")

5. Required UC grants for `app-omnigraph-kb` SP (set BEFORE first start):
   GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO `app-omnigraph-kb`;
   GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO `app-omnigraph-kb`;
   GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO `app-omnigraph-kb`;

6. Secret access:
   - Add Secret resource in App config: scope=omnigraph-kb, key=deepseek_api_key
   - app.yaml: env: - name: DEEPSEEK_API_KEY  valueFrom: <resource-key>
   - Required workspace-side ACL: app-omnigraph-kb SP has READ on scope omnigraph-kb
```

## 4. In-App static file serving from `/Volumes/...`

KB-v2 currently uses FastAPI `StaticFiles` mount (per `PROJECT-KB-v2.md` D-15):

```python
# kb/api/main.py (existing, unchanged for kb-databricks-v1)
from fastapi.staticfiles import StaticFiles
app.mount("/static/img", StaticFiles(directory=os.environ["OMNIGRAPH_BASE_DIR"] + "/images"), name="img")
```

When `OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault`, `StaticFiles` mounts the FUSE path. **Works iff Volume is FUSE-mounted in the Apps runtime.** If not, must replace with a proxy route that calls `w.files.download()`. Verify in kdb-2 smoke.

## 5. /synthesize Q&A flow inside the App

```
Browser → POST /synthesize {query}
       → 202 + job_id
       → background task:
           kg_synthesize.synthesize_response(query, mode="hybrid")
             ├─ load LightRAG from working_dir (= OMNIGRAPH_BASE_DIR/lightrag_storage)
             ├─ aquery() → graph retrieval
             └─ DeepSeek chat completion (api.deepseek.com via DEEPSEEK_API_KEY)
       → result cached at /Volumes/.../output/synthesis_archive/... if writable, OR App-local /tmp
       → polling endpoint GET /synthesize/{job_id} returns markdown
```

**Key constraint:** kg_synthesize.py imports `from lightrag.llm.deepseek import deepseek_model_complete`. This requires `DEEPSEEK_API_KEY` env var at LightRAG init time. App.yaml `valueFrom: <secret-resource-key>` resolves the env var before app code runs. ✅ no code changes needed.

**External egress:** Apps runtime must allow outbound HTTPS to `api.deepseek.com`. EDC corp net is irrelevant here — the App runs in Azure Databricks's compute, not on user's machine. **Verify in kdb-2 smoke** that DeepSeek call succeeds (no Apps-runtime egress filter blocking).

## 6. App restart semantics & state

- App restart wipes ephemeral disk (anything outside `/Volumes/...`)
- Volume content persists across restarts
- Implication for "copy lightrag_storage to /tmp at startup" pattern: every restart re-copies from Volume. Acceptable as long as cold-start latency stays reasonable.

## 7. Known integration risks (carry into PITFALLS)

- App SP has NO grants by default — first start will fail with `PERMISSION_DENIED` if grants forgotten. Pre-deploy checklist must verify all 3 grants.
- DeepSeek API key rotation: putting new value into secret scope updates the value on next App restart, NOT live. After `databricks secrets put-secret` of new value → must restart App.
- `/Volumes/...` path is **case-sensitive** in the Volume name; `mdlg_ai_shared` (all lowercase) confirmed via `databricks-mcp-server list_catalogs` 2026-05-14.
- Apps default compute size = `MEDIUM`. Cold-start latency for a copy-to-/tmp pattern with a few MB lightrag_storage should be sub-30s. If LightRAG state grows past ~100 MB, revisit.
