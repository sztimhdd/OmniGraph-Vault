# Context7 — databricks-apps-cookbook + databricks/cli — raw snippets

Pulled 2026-05-14 by main session for kb-databricks-v1 research. Sub-agents
cannot call MCP context7 on this Databricks-hosted Claude endpoint (proxy
strips `tool_reference`); this file is the read-source for all 4 researchers.

## Library IDs queried

- `/databricks-solutions/databricks-apps-cookbook` (Apps Cookbook, 716 snippets)
- `/databricks/cli` (Databricks CLI, 2386 snippets)

## Key findings

### `app.yaml` minimal form (FastAPI)

```yaml
command: ["uvicorn", "app:app"]
```

### `app.yaml` env block — literal value vs secret valueFrom

(From brave-search snippets — andrefurlan-db.github.io/apps-docs and Microsoft
Learn confirm same syntax)

```yaml
command:
  - gunicorn
  - app:app
  - -w
  - 4
env:
  - name: DATABRICKS_WAREHOUSE_ID
    value: "6b39968592b22d12"      # literal value
  - name: "OPENAI_KEY"
    valueFrom: "openai-secret-name"  # references a `resources.secret` named "openai-secret-name" defined when creating the App
```

```yaml
# Streamlit example from learn.microsoft.com (verbatim from brave snippet)
command: ['streamlit', 'run', 'app.py']
env:
  - name: 'DATABRICKS_WAREHOUSE_ID'
    value: 'quoz2bvjy8bl7skl'
  - name: 'STREAMLIT_GATHER_USAGE_STATS'
    value: 'false'
```

### Secret resource — wired up at App-create time, NOT in app.yaml

From `databricks/cli` `apps create --json @input.json` output:

```json
{
  "name": "test-name",
  "resources": [
    {
      "description": "API key for external service.",
      "name": "api-key",
      "secret": {
        "key": "my-key",
        "permission": "READ",
        "scope": "my-scope"
      }
    }
  ],
  "service_principal_client_id": "[UUID]",
  "service_principal_name": "app-test-name",
  "url": "test-name-123.cloud.databricksapps.com"
}
```

**Two-step pattern:**

1. App resource declaration includes a `resources[].secret` entry that names a
   secret-scope key. The `name` field of the resource (`"api-key"` above) is
   the handle used in `app.yaml`'s `valueFrom`
2. App.yaml `env:` references that handle: `valueFrom: "api-key"` →
   the runtime injects the actual secret value as the env var

### Auto-injected env vars (from cookbook FastAPI streaming-video example)

```python
# From: docs/docs/fastapi/building_endpoints/volumes_stream_video.mdx
client_id = os.getenv("DATABRICKS_CLIENT_ID")
client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")
databricks_host = os.getenv("DATABRICKS_HOST")
# Token endpoint:
# token_endpoint = f"https://{databricks_host}/oidc/v1/token"
# scope='all-apis'
```

App service principal credentials are auto-injected by the Apps runtime;
`WorkspaceClient()` with no args picks them up via `databricks-sdk` default
config chain. No user code needed for App→UC auth.

### Port — `DATABRICKS_APP_PORT` (locked default #7)

User-provided locked default: Apps runtime mandates port `:8080`,
read via `os.getenv("DATABRICKS_APP_PORT")`. Apps cookbook examples confirm
uvicorn / streamlit / gunicorn all bind 0.0.0.0:8080.

### UC Volume access from Apps Python — two patterns

**Pattern A — POSIX path (FUSE mount):**
- App code reads `/Volumes/catalog/schema/volume/path/file` as a regular file
- Works for read-heavy / static file serving
- Subject to FUSE mount semantics — relevant for SQLite WAL, LightRAG state

**Pattern B — Files API via SDK / REST:**
```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
response = w.files.download("/Volumes/catalog/schema/volume_name/file.csv")
file_data = response.contents.read()
```
- Or HTTP: `GET /api/2.0/fs/files{path}` with OAuth bearer

### Required UC privileges for App SP

- `USE CATALOG` on catalog
- `USE SCHEMA` on schema
- `READ VOLUME` on volume (for read-only KB)
- `WRITE VOLUME` only if app uploads (kb-databricks-v1 is read-only consumer)

### Bundle deploy alternative

`databricks/cli` shows `databricks bundle deploy` as the canonical CI flow.
For kb-databricks-v1 v1 (manual deploy from dev box): plain
`databricks apps deploy <app-name> --source-code-path /Workspace/Users/...`
matches the existing project CLAUDE.md pattern.

## Gaps still to resolve (research agents tackle these)

1. **LightRAG `working_dir=/Volumes/...`** — does the FUSE mount support the
   file-locking / fsync / partial-write semantics LightRAG expects? Cookbook
   examples are read-mostly; LightRAG storage has VDB writes + index updates.
   ARCHITECTURE / FEATURES researchers must answer this.
2. **SQLite WAL on `/Volumes/...`** — KB-v2 uses SQLite as a file (not table).
   App reads it. WAL mode + `/Volumes` FUSE may have issues; we may need to
   disable WAL or copy to App-local `/tmp` at startup.
3. **Static file serving from `/Volumes/...`** — KB images. Either FastAPI
   `StaticFiles(directory="/Volumes/...")` works directly, or we need a Files
   API streaming proxy (cookbook video-streaming pattern).
4. **App cold-start time + log access** — kdb-2 success criteria.

## Persisted raw extract

See `tavily-app-runtime-secrets-envvars.json` (59KB) for the verbatim
`learn.microsoft.com` extracts of:
- `dev-tools/databricks-apps/app-runtime` (full `app.yaml` reference)
- `dev-tools/databricks-apps/secrets` (secret resource walkthrough)
- `dev-tools/databricks-apps/environment-variables` (env var precedence rules)

Researchers: `Read` that JSON file for canonical source quotes.
