# Context7 — hkuds/lightrag — raw snippets

Pulled 2026-05-14 by main session for kb-databricks-v1 research. Focus:
LightRAG `working_dir` filesystem expectations and file-storage behavior on
cloud-mounted volumes (the v1 PRIMARY UNCERTAINTY).

## Library ID

- `/hkuds/lightrag` (LightRAG, 485 snippets, versions v1.4.10 / v1.4.9.8 / v1_4_8)

## Key findings — file-based storage classes

For default deploys (no Postgres/Neo4j), LightRAG uses 4 file-based storage
classes routed through `working_dir`:

- `JsonKVStorage` — KV state as JSON files
- `NanoVectorDBStorage` — vector DB on disk
- `NetworkXStorage` — graph as serialized NetworkX
- `JsonDocStatusStorage` — doc-status JSON

Quote (from `docs/ProgramingWithCore.md`):

> For storage types like `JsonKVStorage`, `JsonDocStatusStorage`,
> `NetworkXStorage`, `NanoVectorDBStorage`, and `FaissVectorDBStorage`, data
> isolation is achieved through distinct workspace subdirectories. This
> ensures that each LightRAG instance operates on its own isolated data set
> within the file system.

## Initialization pattern

```python
async def initialize_rag():
    rag = LightRAG(
        working_dir=WORKING_DIR,
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete,
    )
    # Both initialization calls required
    await rag.initialize_storages()
    return rag
```

## Cleanup behavior — relevant for read-only Apps usage

> JsonKVStorage collects all matching keys before deletion, using a snapshot
> approach and lock protection for batch operations, which is efficient due
> to in-memory processing.

In-memory snapshot + lock protection. **For kb-databricks-v1 read-only KB**
the App only calls `aquery()` — no inserts, no deletes — so write paths are
not exercised. This significantly de-risks the FUSE-mount question: the
App's read path likely just opens JSON / NetworkX / NanoVectorDB files.

## Concurrency / merge stage

> LLM requests for the merging stage are prioritized over extraction... To
> prevent race conditions, the merging stage avoids concurrent processing
> of the same entity or relationship, processing them serially if multiple
> files involve them. Each file is an atomic unit; if any error occurs
> during processing, the entire file fails and must be reprocessed.

Concurrency-control happens **inside the LightRAG runtime**, not via OS
file locks. So `/Volumes` FUSE not supporting `flock()` is likely fine for
read-only consumers.

## Implication for kb-databricks-v1

**Strong evidence that read-only LightRAG on `/Volumes/...` will work**
without an adapter, because:

1. The App is a **read-only consumer** (`aquery()` only — `ainsert()` stays
   on Hermes). Read paths just open serialized files.
2. Concurrency control is in-process, not via filesystem locks → FUSE
   limitations on `flock`/`fcntl` don't bite read paths.
3. Workspace-subdirectory isolation is a path concept, not a permission /
   capability concept — `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage`
   is a normal POSIX subdirectory.

**Residual risks researchers should still verify:**

- **Cold-load file-size** — full LightRAG `working_dir` may be MB-to-GB scale.
  FUSE first-read on each file = slow. Do we need warm-up at App startup?
- **Memory-mapped file usage** — NanoVectorDB / NetworkX may `mmap()` files.
  FUSE-backed `mmap` is suspect on some implementations.
- **JSON file partial reads while Hermes uploads new snapshots** — if user
  runs `databricks fs cp` mid-query, the App could read a torn JSON. Mitigation:
  upload to a staging dir then atomic rename, or restart App after upload
  (manual sync workflow already accepts an explicit refresh step).
- **`ainsert()` accidentally invoked from App code** — would require write
  back through FUSE. Even if it works it would corrupt data. Need a hard
  read-only assertion in the App startup path.

## SQLite — separate concern (not LightRAG)

KB-v2 uses SQLite (`kol_scan.db`) as a regular file. Distinct from LightRAG
storage. Researchers should verify SQLite over `/Volumes/...` separately:

- Default journaling mode = ROLLBACK (file-based; should work)
- WAL mode requires shared memory + atomic rename in same dir → **risky on
  FUSE**, may need `PRAGMA journal_mode=DELETE` for App connections
- App is **read-only consumer** → can open with `mode=ro&immutable=1` URI
  param; bypasses journal entirely. **This is the recommended pattern.**

## Existing OmniGraph LightRAG usage in `kg_synthesize.py` (verify in code)

KB-v2 D-19 (async /synthesize 202 + job_id polling) wraps
`kg_synthesize.synthesize_response()`. Researchers should grep for
`working_dir=` in `kg_synthesize.py` / `query_lightrag.py` / `config.py`
to confirm the env-var hand-off path:
`OMNIGRAPH_BASE_DIR=/Volumes/...` → `RAG_WORKING_DIR=$BASE_DIR/lightrag_storage/`.

## Persisted

This file + `context7-apps-cookbook-snippets.md` + the 60KB
`tavily-app-runtime-secrets-envvars.json` are the canonical research
inputs. Researchers MUST `Read` these files; they cannot re-pull MCP
context7 themselves on this Databricks-hosted endpoint.
