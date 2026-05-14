# FEATURES — Raw Materials

> Verbatim source-grep + behavioral analysis. Pulled 2026-05-14 by main session.
> **Primary v1 uncertainty:** does LightRAG `working_dir=/Volumes/...` work?

## 1. LightRAG storage backends — what runs at __post_init__

Source: `venv/Lib/site-packages/lightrag/kg/*.py` (LightRAG package shipping with this repo).

### Universal pattern (4 default storage classes)

`JsonKVStorage`, `JsonDocStatusStorage`, `NetworkXStorage`, `NanoVectorDBStorage`
all run **identical** init logic:

```python
# lightrag/kg/json_kv_impl.py:29-43 (representative)
def __post_init__(self):
    working_dir = self.global_config["working_dir"]
    if self.workspace:
        workspace_dir = os.path.join(working_dir, self.workspace)
    else:
        workspace_dir = working_dir
        self.workspace = ""

    os.makedirs(workspace_dir, exist_ok=True)   # ← WRITE OPERATION at instantiation
    self._file_name = os.path.join(workspace_dir, f"kv_store_{self.namespace}.json")
```

Verified locations:
- `lightrag/kg/json_kv_impl.py:39` — `os.makedirs(workspace_dir, exist_ok=True)`
- `lightrag/kg/networkx_impl.py:50` — same
- `lightrag/kg/nano_vector_db_impl.py:54` — same

**Implication for read-only Volume mount:** `os.makedirs` with `exist_ok=True` is logically a no-op when the dir exists, but on FUSE-backed read-only mounts it may still raise `OSError: [Errno 30] Read-only file system` because the kernel-level call enters the write path before the existence check resolves the no-op.

### Verbatim read paths (no writes)

- `JsonKVStorage` — `load_json(file_name)` → in-memory dict (utils.py:1146)
- `NetworkXStorage` — `nx.read_graphml(file_name)` (networkx_impl.py:30)
- `NanoVectorDBStorage` — `NanoVectorDB(embedding_dim, storage_file=...)` then `client.query(embedding, top_k)`

All read paths are **memory-mapped at construction**, then in-memory ops thereafter.
**No fsync, flock, mmap-write semantics.**

## 2. `write_json` is NOT atomic

Source: `lightrag/utils.py:1235-1269` verbatim:

```python
def write_json(json_obj, file_name):
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(json_obj, f, indent=2, ensure_ascii=False)
        return False

    except (UnicodeEncodeError, UnicodeDecodeError) as e:
        logger.debug(f"Direct JSON write failed, using sanitizing encoder: {e}")

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, indent=2, ensure_ascii=False, cls=SanitizingJSONEncoder)
```

**No** `.tmp` then `os.rename()`. **No** `f.flush()` + `os.fsync(f.fileno())`.
A crash mid-write leaves partially-written JSON.

**Implication for UC Volume:** if our App ever called `ainsert()` against `working_dir=/Volumes/...` and was killed mid-flight (App restart, OOM, deploy), the on-Volume JSON files could be corrupted with no recovery semantics in LightRAG.

## 3. Decision matrix — `working_dir=/Volumes/...` viability

| Scenario | Verdict | Mechanism |
|---|---|---|
| **Read-only LightRAG state, App SP has READ VOLUME only** | ⚠️ **HIGH RISK** | `os.makedirs(..., exist_ok=True)` may raise on read-only FUSE even when dir exists. Untested in this exact Apps runtime. |
| **Read-only LightRAG state, App SP has READ + WRITE VOLUME** | 🟡 **WORKS but risky** | `os.makedirs` no-op succeeds. Reads succeed. But App could *accidentally* trigger writes (e.g., LightRAG cache namespace creation, query LLM cache writes). Volume becomes mutable. |
| **Copy `/Volumes/.../lightrag_storage/` → App-local `/tmp/lightrag_storage/` at startup** | ✅ **SAFE** | App reads Volume once via `databricks-sdk` `w.files.download()` recursive (or shutil.copytree if FUSE-mounted), points `working_dir=/tmp/...`. All write paths land on App ephemeral disk. Cold-start latency = sum of file sizes / network bandwidth. |
| **Mount Volume RW + accept ainsert from App** | ❌ **NO** | Out of v1 scope (Hermes owns ingest). Would also expose LightRAG non-atomic writes to multi-App-instance races. |

### Recommended pattern (subject to kdb-1.5 verification)

```python
# Pseudocode for App startup
import shutil, os
VOL = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage"
LOCAL = "/tmp/lightrag_storage"
if not os.path.exists(LOCAL):
    shutil.copytree(VOL, LOCAL)   # one-shot at startup, idempotent
os.environ["OMNIGRAPH_BASE_DIR"] = "/tmp"   # so working_dir resolves to /tmp/lightrag_storage
```

Caveats:
- Cold-start cost grows with KG size. As of 2026-05-14: 94 articles → likely a few MB, fast copy. Future scale-up = revisit.
- App-local writes are **lost on every App restart**. That's fine because Hermes is the source of truth; restart = re-copy fresh from Volume.
- If user `databricks fs cp` updates the Volume copy, App must restart to pick up new state.

**Open question for kdb-1**: is `/Volumes/...` exposed as a FUSE mount inside the Apps runtime container, or only via Files API? If FUSE: `shutil.copytree` works. If Files API only: must use `w.files.download()` per file.

## 4. SQLite WAL semantics on UC Volume

For `kol_scan.db` reads from `/Volumes/...`:

- KB-v2 currently opens SQLite read-only: `kb/data/article_query.py` opens with `:?mode=ro` URI (verify at kdb-1)
- WAL mode requires writes (`-wal` and `-shm` sidecar files). Read-only mounts → SQLite refuses WAL → falls back to rollback journal, or refuses to open if WAL files exist
- **Mitigation:** snapshot `kol_scan.db` to UC Volume **after** running `PRAGMA wal_checkpoint(TRUNCATE);` on Hermes side, so the Volume copy has no `-wal`/`-shm` sidecars
- Or: copy SQLite to App-local `/tmp` at startup (same pattern as LightRAG), avoid the question entirely

## 5. UC Volume — read access patterns from Apps

From Apps Cookbook (context7) — three observed patterns:

| Pattern | Code | Use when |
|---|---|---|
| **POSIX mount** (`/Volumes/...`) | `open("/Volumes/cat/sch/vol/file")` | FUSE-mounted by Apps runtime. Confirmed working in Cookbook examples (`VOLUME_URI` env var set to `/Volumes/...`). |
| **`databricks-sdk` Files API** | `w.files.download("/Volumes/cat/sch/vol/file")` | Programmatic access; works regardless of FUSE mount status. Required for byte streams. |
| **OAuth + REST `/api/2.0/fs/files`** | `requests.get(f"{host}/api/2.0/fs/files{path}", headers={"Authorization": f"Bearer {token}"})` | Streaming downloads (Range header support). |

For our v1 use case (read SQLite + LightRAG storage + image files, serve images via FastAPI StaticFiles), the POSIX mount pattern is simplest IF Apps runtime mounts UC Volumes. **Verification step in kdb-1** is to confirm this on the actual `omnigraph-kb` App.

## 6. NanoVectorDB write semantics

`nano_vectordb` package is a separate dep — `NanoVectorDB(storage_file=...)` instantiates a `dict`-backed in-memory DB that persists to JSON. Behaviorally similar to JsonKVStorage. Same caveats apply.

## 7. Summary table — kdb-1.5 trigger

| Question | Answer | kdb-1.5 needed? |
|---|---|---|
| Does `os.makedirs(volume_path, exist_ok=True)` succeed on a writable UC Volume mount? | **Likely yes** (standard FUSE) | No |
| Does it succeed if App SP has only `READ VOLUME`? | **Untested — likely fails** | **YES** if grants are read-only |
| Does `write_json` corruption risk matter for a read-only consumer App? | **No** (App never calls it on Volume) | No |
| Does SQLite WAL work on `/Volumes/...`? | **Probably no** (FUSE ≠ POSIX) | Conditional on snapshot pre-checkpoint |
| Is "copy to /tmp at startup" a safe v1 default? | **Yes** | Reduces kdb-1.5 risk |

**Decision rule for kdb-1.5 phase insertion:** if kdb-1 validation finds *any* of the following, insert kdb-1.5:
1. `os.makedirs` raises `[Errno 30]` even when dir exists on the Volume
2. `LightRAG(working_dir="/Volumes/.../lightrag_storage")` raises at construction
3. SQLite refuses to open `/Volumes/.../kol_scan.db` (WAL or otherwise)
4. App cold-start time exceeds 60s with simple FUSE access (suggests LightRAG load via `/Volumes/...` is too slow)

If any fire → kdb-1.5 implements the **copy-to-/tmp** adapter pattern. Otherwise stays at 3 phases.
