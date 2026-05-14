# Research SUMMARY — kb-databricks-v1

> Synthesis of STACK / FEATURES / ARCHITECTURE / PITFALLS research, pulled 2026-05-14.
> All claims trace to verbatim sources (MS Learn, LightRAG source, Databricks CLI v0.260.0, Apps Cookbook). Where direct verification is impossible from the dev box, the question is flagged with "verify in kdb-1" or "verify in kdb-2".

## TL;DR for ROADMAP / REQUIREMENTS planning

1. **Verbatim `app.yaml` syntax solved** — `valueFrom: <resource-key>` (NOT Kubernetes `secretKeyRef:`). Resource-key references a `Secret` resource (or Volume / SQL warehouse / etc.) declared separately on the App, either via UI or `databricks apps create --json`. Resolution table for all resource types is in STACK.md §1.
2. **Secret-scope CLI flow solved** — `databricks secrets create-scope <SCOPE>` then `databricks secrets put-secret <SCOPE> <KEY>` with `--string-value` / interactive / stdin. ACL `READ` must be granted to the App SP separately. Verbatim help in STACK.md §3.
3. **LightRAG `working_dir=/Volumes/...` is NOT trivially safe** — every storage backend (`JsonKVStorage`, `NetworkXStorage`, `NanoVectorDBStorage`, `JsonDocStatusStorage`) calls `os.makedirs(workspace_dir, exist_ok=True)` in `__post_init__`. On a strict read-only mount, this likely raises `[Errno 30]`. Plus `write_json` is **non-atomic** (no `.tmp`+rename, no fsync). Strong recommendation: copy `lightrag_storage/` to App-local `/tmp` at startup. **This makes kdb-1.5 likely necessary.**
4. **Hermes → UC sync v1 = manual `databricks fs cp`** — confirmed viable via local CLI; full pre-sync runbook (WAL checkpoint, sidecar cleanup, recursive cp, App restart) is in ARCHITECTURE.md §2 Option A.
5. **22 pitfalls identified across 7 categories** with phase-coverage matrix in PITFALLS.md.

## Key facts (verbatim, traceable to source)

### Stack additions
- **No new Python dependencies** — KB-v2's FastAPI/uvicorn/Jinja2/markdown stack ships unchanged
- **New tooling:** Databricks CLI ≥ v0.260.0 (already on dev box), `databricks-sdk` Python (already in repo's transitive deps)
- **Auto-injected env vars in Apps runtime:** `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, `DATABRICKS_HOST`, `DATABRICKS_APP_PORT` — `WorkspaceClient()` picks them up via default config chain (no explicit auth code in app)
- **Critical CLI subcommands:** `databricks apps create/deploy/start/stop/get`, `databricks secrets create-scope/put-secret/list-acls`, `databricks fs cp -r --overwrite`

### Feature table-stakes (in-scope for v1)
- **Read SQLite** from `/Volumes/.../data/kol_scan.db` (after WAL checkpoint on Hermes side)
- **Read images** from `/Volumes/.../images/{hash}/...` via FastAPI `StaticFiles` mount (or proxy if FUSE not mounted)
- **Read LightRAG state** from `/Volumes/.../lightrag_storage/` (likely via copy-to-/tmp adapter — see kdb-1.5 trigger)
- **/synthesize Q&A** with DeepSeek (status-quo LLM provider; secret injected via Apps secret resource)
- **Workspace SSO** (Apps default; internal preview only)

### Differentiators (deferred to v2 / v3 / out-of-scope)
- Foundation Model `databricks-claude-sonnet-4-6` swap (v2, bundled with ingest LLM)
- Automated Hermes → Volume sync via Workflow / Job (v2)
- Per-user OBO auth (v2)
- Public access (KB-v2 Aliyun deploy, NOT this milestone)
- Ingest pipeline on Databricks (separate future milestone)

### Architecture decisions
- **Topology:** App reads UC Volume; Hermes writes (via user-driven sync) (ARCHITECTURE.md §1)
- **Sync v1:** Manual `databricks fs cp` from Windows dev (Option A locked); 5-step runbook including SQLite WAL checkpoint
- **Auth:** App service principal auto-created on `databricks apps create`; runtime env injection of credentials
- **Secret pattern:** Workspace secret scope `omnigraph-kb` → `DEEPSEEK_API_KEY` key → App resource binding → `valueFrom:` env var in `app.yaml`
- **Static file serving:** FastAPI `StaticFiles` mount on `/Volumes/.../images` — requires Volume FUSE-mounted in Apps runtime (verify in kdb-2)

## Watch Out For (top 5 pitfalls)

| # | Pitfall | Phase to address | Mitigation |
|---|---------|------------------|------------|
| 1 | `os.makedirs` raises `[Errno 30]` on read-only Volume mount → LightRAG init fails | kdb-1 verify, kdb-1.5 fix | Grant `WRITE VOLUME` to App SP **OR** copy lightrag_storage to App-local `/tmp` at startup |
| 2 | SQLite refuses to open from `/Volumes/...` (WAL/locking issues) | kdb-1 verify, kdb-1.5 fix | WAL-checkpoint + sidecar cleanup pre-sync; OR copy DB to `/tmp` at startup |
| 3 | App SP grants forgotten before first start → 100% PERMISSION_DENIED | kdb-2 runbook | Pre-flight checklist verifies `USE CATALOG` / `USE SCHEMA` / `READ VOLUME` / scope `READ` |
| 4 | Literal `DEEPSEEK_API_KEY` value sneaks into commit history | All phases | Pre-commit grep + post-deploy `git log --all -p -- app.yaml` audit |
| 5 | App.yaml in nested directory not picked up → wrong port / no env vars | kdb-2 smoke | Hard-rule: `app.yaml` at root of `--source-code-path` |

## kdb-1.5 trigger (conditional phase)

Insert kdb-1.5 between kdb-1 and kdb-2 if **any** of these surface during kdb-1:

1. `os.makedirs(volume_path, exist_ok=True)` raises on the actual Apps runtime + Volume combination
2. `LightRAG(working_dir="/Volumes/.../lightrag_storage")` raises at construction
3. SQLite refuses to open `kol_scan.db` from `/Volumes/...`
4. Volume not FUSE-mounted (only available via `databricks-sdk` Files API)
5. App cold-start time > 60s with simple FUSE access

If any fire → kdb-1.5 implements the **copy-to-/tmp adapter** pattern (one-shot startup hook that downloads `lightrag_storage/` and `data/kol_scan.db` from `/Volumes/...` to `/tmp/` and rebinds `OMNIGRAPH_BASE_DIR` to `/tmp`).

If none fire → milestone stays at 3 phases, ship via env-var override only (per "zero `kb/` code changes" constraint in PROJECT-kb-databricks-v1.md).

## Verification questions still open after this research pass

These need actual deploy attempts to answer (cannot be settled from docs alone):

| Q | Answer-via | Phase |
|---|------------|-------|
| Is `/Volumes/...` FUSE-mounted in the Apps runtime container? | Run `os.listdir("/Volumes/...")` in App | kdb-1 spike |
| Does `os.makedirs(exist_ok=True)` succeed on FUSE-mounted Volume with `READ VOLUME` only? | Same spike | kdb-1 spike |
| Does SQLite WAL-mode open from `/Volumes/...`? | Same spike | kdb-1 spike |
| Does App cold-start finish within 60s with full lightrag_storage on Volume? | First `databricks apps deploy` | kdb-2 |
| Does Apps runtime allow outbound HTTPS to `api.deepseek.com`? | First `/synthesize` call | kdb-2 smoke 3 |

**Recommendation:** kdb-1 includes a 30-min spike notebook / Apps smoke-instance that answers Q1-Q3 before committing to the storage adapter design. This is cheaper than building kdb-1.5 speculatively.

## Refresh log

- 2026-05-14 v1 — main session compiled from 4 verbatim source pulls (Apps Cookbook context7, MS Learn via Tavily, local CLI v0.260.0 help, LightRAG source grep)
