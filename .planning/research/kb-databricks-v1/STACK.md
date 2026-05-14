# STACK — Raw Materials

> Verbatim extracts from MS Learn (Azure Databricks docs) + local Databricks CLI v0.260.0 + Apps Cookbook (context7 `/databricks-solutions/databricks-apps-cookbook`). Pulled 2026-05-14 by main session.

## 1. Canonical `app.yaml` schema (MS Learn)

Source: <https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/app-runtime>
(Last updated 2026-03-17 per page footer)

### Supported settings

| Setting | Type | Description |
|---------|------|-------------|
| `command` | sequence | Custom command to run the app. Default for Python is `python <my-app.py>` (first `.py` in tree); for Node.js, `npm run start`. **Apps does NOT run command in a shell** — env vars defined outside app config aren't visible. **One exception:** `DATABRICKS_APP_PORT` is substituted at runtime in the command. Optional. |
| `env` | list | Apps automatically sets several default env vars (see system-env doc). This top-level key adds more. Each item: `name` + one of (`value` literal, OR `valueFrom` resource-key reference). Optional. |

File location: **root of project directory**. Both `.yaml` and `.yml` extensions accepted.

### Verbatim Streamlit example

```yaml
command: ['streamlit', 'run', 'app.py']
env:
  - name: 'DATABRICKS_WAREHOUSE_ID'
    value: 'quoz2bvjy8bl7skl'
  - name: 'STREAMLIT_GATHER_USAGE_STATS'
    value: 'false'
```

### Verbatim Flask + UC Volume example

```yaml
command:
  - gunicorn
  - app:app
  - -w
  - 4
env:
  - name: 'VOLUME_URI'
    value: '/Volumes/catalog-name/schema-name/dir-name'
```

### Verbatim secret reference example

```yaml
env:
  - name: WAREHOUSE_ID
    valueFrom: sql_warehouse
  - name: SECRET_KEY
    valueFrom: secret
```

> The string after `valueFrom:` is the **resource key** defined in the app's "App resources" block (NOT a path, NOT a `secretKeyRef:` Kubernetes-style block). Default resource key for a Secret is literal string `secret`.

### `valueFrom` resolution table (MS Learn)

| Resource type | Resolved value | Example |
|---------------|---------------|---------|
| Databricks app | App name | `my-app` |
| Genie Space | Space ID | `01ef1fa2b3c45678` |
| Lakebase Autoscaling DB | Endpoint path | `projects/my-project/branches/main/endpoints/ep123` |
| Lakebase Provisioned DB | Host | `postgres-host.example.com` |
| Lakeflow job | Job ID | `123456789` |
| MLflow experiment | Experiment ID | `456789012` |
| Model serving endpoint | Endpoint name | `my-serving-endpoint` |
| **Secret** | **Decrypted secret value** | _(the secret value)_ |
| SQL warehouse | Warehouse ID | `a1b2c3d4e5f67890` |
| Unity Catalog connection | Connection name | `my_connection` |
| Unity Catalog table | Table full name | `catalog.schema.table` |
| **Unity Catalog volume** | **Volume path** | **`/Volumes/catalog/schema/volume`** |
| User-defined function | Function full name | `catalog.schema.my_function` |
| Vector search index | Index full name | `catalog.schema.my_index` |

## 2. Apps secret resource — UI + CLI flow (MS Learn + CLI)

Source: <https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/secrets>

### UI flow (workspace)

1. App resources section → **+ Add resource → Secret**
2. Choose secret scope
3. Select key within scope
4. Choose permission level **on the scope** (not individual secret): `Can read` / `Can write` / `Can manage`
5. (Optional) Custom resource key — default `secret`. This is what `valueFrom:` references in `app.yaml`

### CLI alternative — `databricks apps create --json @input.json`

From context7 (`/databricks/cli`):

```json
{
  "name": "test-name",
  "description": "My app description.",
  "resources": [
    {
      "name": "api-key",
      "description": "API key for external service.",
      "secret": {
        "key": "my-key",
        "permission": "READ",
        "scope": "my-scope"
      }
    }
  ]
}
```

### Best-practice constraints (MS Learn verbatim)

> *"Never store sensitive values directly in environment variables or your app code. Instead, pass the resource key to Azure Databricks as an environment variable, and retrieve the secret value securely at runtime."*

> *"Secret values injected directly as environment variables appear in plaintext on the app's Environment page. To avoid this, reference the secret using the `valueFrom` field in your app configuration and retrieve the value securely within your app code."*

Note: secret permissions apply at **scope level**, not individual secret. Recommendation: **separate scope per app**. → for our project: scope name `omnigraph-kb`.

## 3. Local CLI v0.260.0 — verbatim sub-help

Captured 2026-05-14 from `databricks --version` → `Databricks CLI v0.260.0`.

### `databricks secrets create-scope SCOPE`

```
Usage:
  databricks secrets create-scope SCOPE [flags]

Flags:
  --initial-manage-principal string       The principal that is initially granted MANAGE permission to the created scope.
  --json JSON                             either inline JSON string or @path/to/file.json with request body
  --scope-backend-type ScopeBackendType   Supported values: [AZURE_KEYVAULT, DATABRICKS]
```

Constraints (verbatim from help):
- Scope name: alphanumeric + dashes/underscores/periods, ≤ 128 chars
- If `initial_manage_principal` not specified → ACL with MANAGE granted to API issuer's identity
- Default backend = `databricks` (workspace storage)

### `databricks secrets put-secret SCOPE KEY`

```
Usage:
  databricks secrets put-secret SCOPE KEY [flags]

Flags:
  --bytes-value string    If specified, value will be stored as bytes.
  --json JSON
  --string-value string   If specified, note that the value will be stored in UTF-8 (MB4) form.
```

Three input methods (verbatim):
1. `--string-value` flag
2. Interactive prompt
3. Pass via stdin (multi-line)

Constraints: key ≤ 128 chars, secret value max 128 KB, max 1000 secrets per scope.
**Caller needs WRITE or MANAGE on the scope.**

### `databricks apps create NAME`

```
Usage:
  databricks apps create NAME [flags]

Flags:
  --budget-policy-id string
  --description string        The description of the app.
  --json JSON                 either inline JSON string or @path/to/file.json with request body
  --no-compute                If true, the app will not be started after creation.
  --no-wait                   do not wait to reach ACTIVE state
  --timeout duration          maximum amount of time to reach ACTIVE state (default 20m0s)
```

App name constraint: lowercase alphanumeric + hyphens, unique within workspace.

### `databricks apps deploy APP_NAME`

```
Usage:
  databricks apps deploy APP_NAME [flags]

Flags:
  --deployment-id string
  --json JSON
  --mode AppDeploymentMode    Supported values: [AUTO_SYNC, SNAPSHOT]
  --no-wait                   do not wait to reach SUCCEEDED state
  --source-code-path string   The workspace file system path of the source code used to create the app deployment.
  --timeout duration          maximum amount of time to reach SUCCEEDED state (default 20m0s)
```

### `databricks fs cp SOURCE_PATH TARGET_PATH`

```
Flags:
  --overwrite   overwrite existing files
  -r, --recursive   recursively copy files from directory
```

> Paths in DBFS / UC Volumes: must use `dbfs:` scheme (e.g. `dbfs:/foo/bar`). NOTE — to address UC Volumes specifically, the path is `dbfs:/Volumes/<catalog>/<schema>/<volume>/...`. Local paths are absolute or relative as usual.

## 4. CRITICAL — `DATABRICKS_APP_PORT` substitution

> *"Because Azure Databricks doesn't run the command in a shell, environment variables defined outside the app configuration aren't available to your app. The one exception is `DATABRICKS_APP_PORT`, which is substituted with the actual port number in the command at runtime."*

This means **inside `command:` you can use `$DATABRICKS_APP_PORT`** as a literal string and Apps will substitute it. Inside Python code, `os.environ['DATABRICKS_APP_PORT']` resolves at runtime.

For our FastAPI app, `command:` should be:

```yaml
command:
  - uvicorn
  - app:app
  - --host
  - 0.0.0.0
  - --port
  - $DATABRICKS_APP_PORT
```

(or hardcode `8080` since that's the documented runtime value).

## 5. Apps service principal — runtime-injected env vars

From Apps Cookbook FastAPI example (context7) — confirmed env vars Apps runtime injects:

- `DATABRICKS_CLIENT_ID` — service principal client ID
- `DATABRICKS_CLIENT_SECRET` — service principal client secret
- `DATABRICKS_HOST` — workspace host (e.g. `adb-XXXX.X.azuredatabricks.net`)
- `DATABRICKS_APP_PORT` — assigned port (substituted in `command`)

`WorkspaceClient()` from `databricks-sdk` picks these up automatically via the default config chain — **no manual auth code required** in app.

## 6. UC Volume access from FastAPI — pattern reference

From Apps Cookbook FastAPI Volumes streaming example: uses OAuth client_credentials flow against `https://{DATABRICKS_HOST}/oidc/v1/token` with `scope=all-apis`, then GETs `/api/2.0/fs/files{file_path}` with the bearer token.

For our use case (POSIX-style file read at `/Volumes/...`), a simpler approach: **the Apps runtime mounts UC Volumes via FUSE** when the service principal has `READ VOLUME`. Confirmed by Cookbook patterns that simply pass `/Volumes/...` paths to standard Python file ops (`open()`, `os.listdir()`).

**Required UC grants for our service principal** (`omnigraph-kb` Apps SP):
- `USE CATALOG` on `mdlg_ai_shared`
- `USE SCHEMA` on `mdlg_ai_shared.kb_v2`
- `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault`
- (For sync UAT: `WRITE VOLUME` granted to user `hhu@edc.ca`, NOT to the App SP)
