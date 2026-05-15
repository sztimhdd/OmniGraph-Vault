# Phase kdb-1.5 — LightRAG-Databricks Provider Adapter — Research

**Researched:** 2026-05-15
**Domain:** Databricks Apps storage adapter + LightRAG provider factory
**Confidence:** HIGH (most claims verified by file:line refs to LightRAG source + production size measurements; only LOW item is exact /tmp ceiling on Apps runtime, where docs guidance is informal)

## Summary

This phase delivers two artifacts under `databricks-deploy/`: (1) a startup storage adapter that copies the read-only UC Volume payload (`lightrag_storage/`, `data/kol_scan.db`) into App-local `/tmp/` so LightRAG's mandatory `os.makedirs(workspace_dir, exist_ok=True)` succeeds; and (2) `lightrag_databricks_provider.py` — `make_llm_func()` + `make_embedding_func()` factories wrapping MosaicAI Model Serving (`databricks-claude-sonnet-4-6` + `databricks-qwen3-embedding-0-6b` dim=1024). Both are written + dry-run e2e-tested in this phase **before** kdb-2 commits the App and **before** kdb-2.5 burns Model Serving budget on full re-index.

kdb-1.5's trigger is documentary-inferred from kdb-1 Wave 3: Apps SSO + Private Link blocked the live in-app spike, but `READ_VOLUME`-only semantics + LightRAG source-grep (verified at `lightrag/kg/json_kv_impl.py:39`, `networkx_impl.py:50`, `nano_vector_db_impl.py:54`) prove `os.makedirs` will raise `OSError [Errno 30] Read-only file system`. SPIKE-DBX-01b documentary-fail is the design-locked trigger.

**Primary recommendation:** Use `shutil.copytree` (FUSE path) with `databricks-sdk w.files.download_directory` as Files-API fallback. Copy only `lightrag_storage/` to `/tmp/lightrag_storage/`; **leave `kol_scan.db` on `/Volumes/...`** opened via `?mode=ro&immutable=1` URI (the existing pattern in `kb/data/article_query.py:142-143` already does `?mode=ro` and works against any read-only mount). Use LightRAG's existing `lightrag.llm.openai.openai_complete_if_cache` + `openai_embed` with `base_url` pointed at Databricks's OpenAI-compatible serving endpoint (zero new HTTP plumbing); fall back to `WorkspaceClient().serving_endpoints.query()` only if the OpenAI-compat path fails the dry-run.

<user_constraints>
## User Constraints (from CONTEXT.md and ROADMAP-kb-databricks-v1.md rev 3)

> No CONTEXT.md exists for this phase. Constraints are extracted from REQUIREMENTS-kb-databricks-v1.md rev 3 + ROADMAP rev 3 + the orchestrator prompt's `<scope_constraints>` block.

### Locked Decisions

1. **All LLM via MosaicAI Model Serving** — DeepSeek fully retired in v1. No fallback LLM provider in this milestone.
2. **Synthesis model: `databricks-claude-sonnet-4-6`** (locked).
3. **Embedding model: `databricks-qwen3-embedding-0-6b`** (locked, dim=1024, bilingual zh/en).
4. **No `WRITE_VOLUME` grant for App SP** — explicitly forbidden in v1 per AUTH-DBX-03. This is the architectural reason kdb-1.5 exists.
5. **Adapter code lives in NEW `databricks-deploy/` directory** — not under `kb/` or `lib/`. Per CONFIG-DBX-02.
6. **Two `kb/`-source files exempted via CONFIG-EXEMPTIONS.md**: `lib/llm_complete.py` (LLM-DBX-01, kdb-2 territory) + `kg_synthesize.py` (LLM-DBX-02, kdb-2 territory). **Neither is modified in kdb-1.5.**
7. **Time-box:** half day. If LLM-DBX-03 dry-run reveals a fundamental SDK shape mismatch, fall back to a small custom HTTP wrapper around Model Serving REST API (still under `databricks-deploy/`).

### Claude's Discretion

1. Choice between `shutil.copytree` (FUSE) and `databricks-sdk w.files.download_directory` (Files API) for the copy mechanism — both are sanctioned by ROADMAP rev 3 line 71. Recommend FUSE primary, SDK fallback.
2. Choice between LightRAG's existing `lightrag.llm.openai.openai_complete_if_cache` (with `base_url` pointed at Databricks) vs. a custom wrapper around `WorkspaceClient().serving_endpoints.query()`. Recommend OpenAI-compat primary (zero code), `WorkspaceClient` only if compat fails the dry-run.
3. Where the dry-run e2e test lives (suggest `databricks-deploy/tests/test_provider_dryrun.py`, runnable as a standalone pytest with user OAuth — not a deployed App).
4. Whether `kol_scan.db` is copied to `/tmp/data/` or left on `/Volumes/.../data/`. Recommend left-on-Volume (saves cold-start time + simpler adapter).

### Deferred Ideas (OUT OF SCOPE)

- Production App deploy → kdb-2.
- kdb-2.5 re-index Job → separate phase.
- LLM-DBX-01 / LLM-DBX-02 (`lib/llm_complete.py` + `kg_synthesize.py` edits) → kdb-2.
- `app.yaml` authoring (DEPLOY-DBX-04 etc.) → kdb-2.
- AUTH-DBX-01..05 grants → kdb-2.
- Any modification to Aliyun deploy → different milestone.
- Any Hermes mutating ops → forbidden across milestone.
- WRITE_VOLUME grant → forbidden in v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **STORAGE-DBX-05** (alternative satisfaction path) | Volume content readable from App container — original FUSE+`os.makedirs`-on-RO-mount path is broken (documentary inference); alternative path = copy-to-/tmp adapter | Q1 (empty source at build), Q2 (size + cold-start budget), Q3 (LightRAG writes-during-query confirms /tmp need), Q4 (DB on /tmp vs Volume) |
| **LLM-DBX-03** | `databricks-deploy/lightrag_databricks_provider.py` provides `make_llm_func()` + `make_embedding_func()`; e2e tested with `ainsert + aquery` round-trip; embedding dim=1024 verified | Q5 (dry-run venue + auth + test fixture) |

Both REQs MUST land in this phase. Per ROADMAP rev 3 line 67, STORAGE-DBX-05 is the "alternative satisfaction path" for the read-only Volume problem; LLM-DBX-03 is the factory file that kdb-2 imports + kdb-2.5 instantiates against the full corpus.
</phase_requirements>

## Q1 — Source-empty timing (UC Volume `lightrag_storage/` is empty at build time)

**Verdict:** ✅ Confirmed. **`/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/` is empty at kdb-1.5 build time.** kdb-2.5 populates it later via the Databricks Job. The kdb-1.5 deliverable is the **copy mechanism + smoke test against an empty source (or a synthetic test fixture)**, NOT against real data on Volume.

**Evidence:**

- `kdb-1-WAVE2-FINDINGS.md` "Anti-pattern compliance audit" item #5: *"DO NOT copy `lightrag_storage/` from Hermes ✅ Confirmed — `lightrag_storage/` sub-dir created empty; only `kol_scan.db` + `images/` synced"*
- `kdb-1-WAVE2-FINDINGS.md` STORAGE-DBX-03 commands: `databricks fs mkdir` was called for the 4 sub-dirs (`data`, `images`, `lightrag_storage`, `output`); the `mkdir` only creates the dir, no contents.
- `ROADMAP-kb-databricks-v1.md` Phase kdb-2.5 SEED-DBX-02: *"Output written to `/Volumes/.../lightrag_storage/` (graphml + nano-vector-db JSON)"* — the populating step is unambiguously kdb-2.5, not kdb-1 or kdb-1.5.

**Implication for executor:** the dry-run e2e test (LLM-DBX-03) MUST NOT depend on real lightrag_storage data on Volume. The test must:

1. Create a synthetic small fixture (e.g., 5 short test articles inline in the test file or in `databricks-deploy/tests/fixtures/`).
2. Pass `working_dir=/tmp/lightrag_storage_dryrun_<unix-ts>/` (NOT `/Volumes/...`) — this is the LightRAG runtime working dir for the test, ephemeral.
3. Call `await rag.ainsert(article_text)` for each fixture article.
4. Call `await rag.aquery("test query")` with mode=hybrid.
5. Assert `vdb_*.json` + `graph_*.graphml` + `kv_store_*.json` files emit correctly under `/tmp/lightrag_storage_dryrun_*/`.
6. Assert at least one `vdb_*.json` file's `embedding_dim` field == 1024.
7. Tear down `/tmp/lightrag_storage_dryrun_*/`.

The startup adapter dry-run is separate: it can be smoke-tested against an empty source (verify `if not os.listdir("/Volumes/.../lightrag_storage")` short-circuits cleanly to "first-deploy mode") AND against a tiny synthetic source (push 1 fake graphml file to a temp location, verify copy lands intact in `/tmp/`).

## Q2 — /tmp size + cold-start budget

**Verdict:** ⚠️ Cold-start budget at expected post-kdb-2.5 scale is **TIGHT**. Production-only Hermes lightrag_storage is **1.315 GB** (no .bak backups). With Qwen3 1024-dim vs Vertex 3072-dim, vdb file shrinks ~3× → expected post-kdb-2.5 size ≈ **0.4–0.6 GB** (vdb dominated; Qwen3 1024 floats vs Vertex 3072 floats; entity/relation/chunk counts unchanged). This is feasible for `/tmp` copy at startup, but cold-start time will exceed the **9s measured for the empty spike App** (Wave 3, deploy-to-RUNNING). Recommend documenting expected cold start at 30–90s once kdb-2.5 lands (varies by Files-API throughput) and raising the Apps spec budget to **120s** as a safety margin.

**Evidence — measured Hermes prod size (run via SSH 2026-05-15):**

```
SSH host: ohca.ddns.net:49221 user sztimhdd
Command: find ~/.hermes/omonigraph-vault/lightrag_storage -maxdepth 1 -type f
         (excluding .bak* files)
```

| File | Bytes | Notes |
|------|-------|-------|
| `kv_store_doc_status.json` | 280,739 | doc-level status |
| `kv_store_full_entities.json` | 730,537 | entity defs |
| `kv_store_full_relations.json` | 2,169,029 | relation defs |
| `kv_store_entity_chunks.json` | 4,760,215 | entity → chunk index |
| `kv_store_full_docs.json` | 4,764,281 | full doc texts |
| `kv_store_text_chunks.json` | 5,910,792 | chunk texts |
| `kv_store_relation_chunks.json` | 7,171,409 | relation → chunk index |
| `graph_chunk_entity_relation.graphml` | 22,539,673 | NetworkX graph (text) |
| `vdb_chunks.json` | 35,403,338 | chunk vectors (3072-dim) |
| `kv_store_llm_response_cache.json` | 73,125,102 | LLM response cache |
| `vdb_entities.json` | **482,116,568** | **460 MB** entity vectors (3072-dim) |
| `vdb_relationships.json` | **676,031,130** | **645 MB** relation vectors (3072-dim) |
| **TOTAL_BYTES** | **1,315,002,813** | **1.315 GB** |

**Projection to post-kdb-2.5 Databricks state:**

- Vector files: 3072-dim → 1024-dim = **3× shrinkage** on `vdb_*.json`. New estimate: `vdb_chunks.json` ~12 MB, `vdb_entities.json` ~160 MB, `vdb_relationships.json` ~225 MB → vdb subtotal **~400 MB** (was 1.19 GB).
- LightRAG response cache (`kv_store_llm_response_cache.json` 70 MB) is per-query LRU; will be **empty at first deploy** (kdb-2 cold start) and grow over time. Safe to assume **0 MB** at post-kdb-2.5 cold start.
- Graphml + non-vdb kv stores (~50 MB) ≈ unchanged (entity/relation counts roughly equal).
- **Expected post-kdb-2.5 lightrag_storage size: 400–600 MB.** (1.5× corpus growth from Hermes 2598 articles to maybe ~3000–4000 ingested in kdb-2.5 also accounted.)

**Cold-start budget analysis:**

- Apps cold-start spec budget: 60s (per ROADMAP-kb-databricks-v1.md SPIKE-DBX-01d criterion). Wave 3 measured 9s for **empty** spike App.
- `databricks-sdk w.files.download_directory` throughput from UC Volume → App ephemeral disk: research source `.planning/research/kb-databricks-v1/ARCHITECTURE.md:188` says *"Cold-start latency for a copy-to-/tmp pattern with a few MB lightrag_storage should be sub-30s. If LightRAG state grows past ~100 MB, revisit."* — and we are projecting **400–600 MB**, which is **6–60× past that threshold**. Hard data on FUSE `shutil.copytree` throughput from UC Volume is not in the research dimensions (LOW confidence on exact rate; expected: 50–200 MB/s based on Azure private-endpoint metrics for managed-volume reads, which would put a 500 MB copy at 2.5–10s — comfortable).
- The 60s budget is for the App's `/health` to return 200 after `start`; FastAPI module-load + uvicorn bind happens BEFORE the copy begins (if copy is in `@app.on_event("startup")`) which means /health 200 races the copy. **The adapter MUST gate `/health` on copy-completion**, otherwise health-check returns 200 while LightRAG init hasn't seen the data yet, causing the first `/synthesize` request to fail with FileNotFoundError on the not-yet-copied vdb_*.json.

**Recommended cold-start strategy (for kdb-2's `app.yaml` design, but documented here for executor planning):**

1. Adapter runs **before uvicorn binds the port** — i.e., as a pre-startup shell wrapper or a synchronous block at the top of the FastAPI module before `app = FastAPI()`.
2. /health endpoint reports a copy-progress field; Apps internal health check tolerates startup until file copy completes.
3. Set Apps `command:` budget to 120s (or document acceptance of 60s with the understanding that early kdb-2 deploys may need raise if Files API is slow that day).
4. **Optimisation** (deferred to v1.1 if not needed): hash the on-Volume snapshot, cache `/tmp/lightrag_storage/.synced_hash` as a sentinel. Only re-copy if the on-Volume hash changes. Apps containers persist across hot-deploy revisions in some cases (per Apps Cookbook), so this MAY save cold-start time. Confirm in kdb-2 first deploy.

**LOW-confidence flag:** exact UC Volume Files-API throughput from App container is documentary only; needs measurement in kdb-2 first deploy with 500 MB payload. If measurement shows < 50 MB/s, lazy-load (load LightRAG on first /synthesize request, cache instance) becomes attractive.

## Q3 — LightRAG query-path write semantics

**Verdict:** ⚠️ **`aquery` does write to disk** — but only one file: `kv_store_llm_response_cache.json`. /tmp ephemerality is acceptable for v1 (cache loss on App restart = next-query cold-cache penalty, not a correctness issue). No lock files; no telemetry writes; no other query-time writes.

**Evidence — exact write paths during query:**

- `venv/Lib/site-packages/lightrag/lightrag.py:2622` — `async def aquery(...)` is a wrapper around `aquery_llm`.
- `lightrag.py:2884` — `aquery_llm` calls `kg_query` / `naive_query` / bypass branch.
- `lightrag.py:2974` — at end of `aquery_llm` (success path): `await self._query_done()`.
- `lightrag.py:2881` — at end of `aquery_data` (the data-only path): `await self._query_done()`.
- `lightrag.py:3045-3046` — `async def _query_done(self): await self.llm_response_cache.index_done_callback()`.
- `lightrag/kg/json_kv_impl.py:77-92` — `index_done_callback` calls `write_json(data_dict, self._file_name)` against `kv_store_llm_response_cache.json`. **Non-atomic** write — see PITFALL section.
- `lightrag/utils.py:1255-1270` — `write_json()` does `with open(file_name, "w", encoding="utf-8") as f: json.dump(...)`. NO `.tmp` + rename. NO `f.flush()` + `os.fsync()`. Vulnerable to partial-write corruption on concurrent crash.

**Other potential write sources during query (verified via grep):**

- `kg_query` / `naive_query` (in `lightrag/operate.py`, not LightRAG class) — these only **READ** vdb + graph + chunks. The only write is via the `hashing_kv=self.llm_response_cache` parameter passed to them, which is the LLM response cache being upserted (then flushed by `_query_done()`).
- No `.lock` files in any of the storage backend files (`json_kv_impl.py`, `networkx_impl.py`, `nano_vector_db_impl.py`).
- No telemetry / metrics writes (`grep -n "metric\|telemetry\|stat" venv/Lib/site-packages/lightrag/lightrag.py` → 0 production writes; only debug logs).

**Implication for /tmp ephemerality (App restart loses cache):**

- **Correctness:** ✅ Safe. `kv_store_llm_response_cache.json` is a **cache** — its loss does not corrupt the graph. First query after restart re-computes; subsequent identical queries hit cache as before.
- **Performance:** Each App restart = first ~N queries pay LLM cost again. Not a problem for v1 internal-preview low-traffic deploy (1 user). Worth tracking if v1 traffic ramps.
- **Concurrent-write safety on /tmp:** even on /tmp, if the App scales to multiple instances, two instances writing the same `kv_store_llm_response_cache.json` simultaneously can corrupt it (no lock, non-atomic write). v1 hard-locks single-instance per CONFIG-DBX rev 3 (Apps default = 1 instance), so this is moot. Document for v2 if scaling.

**Verdict for adapter design:** the startup copy from `/Volumes/.../lightrag_storage/` → `/tmp/lightrag_storage/` works perfectly — query-time writes go to `/tmp/kv_store_llm_response_cache.json` (which is ephemeral, accepted), and there is **NO requirement to write back to `/Volumes/...`** during runtime. WRITE_VOLUME grant remains correctly forbidden per AUTH-DBX-03.

## Q4 — DB on /tmp WAL sidestep

**Verdict:** ✅ **Leave `kol_scan.db` on `/Volumes/.../data/kol_scan.db`. Do NOT copy to /tmp.** Existing pattern in `kb/data/article_query.py:142-143` already uses `?mode=ro` URI mode, which works correctly against any read-only mount including FUSE-on-UC-Volume.

**Evidence — existing pattern:**

- `kb/data/article_query.py:140-143`:
  ```python
  def _connect() -> sqlite3.Connection:
      """Open a read-only connection to KB_DB_PATH using SQLite URI mode."""
      uri = f"file:{config.KB_DB_PATH}?mode=ro"
      return sqlite3.connect(uri, uri=True)
  ```
- This is the only sqlite3 connector for `kol_scan.db` in `kb/`. `kg_synthesize.py` opens a different DB (`canonical_map.db`, project-internal), not `kol_scan.db`.
- `kb/config.py` resolves `KB_DB_PATH` from `OMNIGRAPH_BASE_DIR` env var. In Apps deploy, set `OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` and `kb/data/article_query.py` opens `/Volumes/.../data/kol_scan.db?mode=ro` directly — works without any /tmp copy.

**Evidence — Hermes DB journal_mode (verified via SSH 2026-05-15):**

```python
import sqlite3
c = sqlite3.connect("data/kol_scan.db")
print(c.execute("PRAGMA journal_mode").fetchone())  # ('delete',)
print(c.execute("PRAGMA page_size").fetchone())     # (4096,)
print(c.execute("PRAGMA page_count").fetchone())    # (5105,)
```

**`journal_mode=delete`** — NOT WAL. So no `-wal` / `-shm` sidecars exist on the current Hermes DB. SEED-DBX-04's "WAL pre-checkpointed and sidecars stripped" requirement was a defensive provision in case Hermes flips to WAL later; the current DB is already in delete mode and trivially safe to copy as-is.

**Why `?mode=ro` (without `&immutable=1`) is sufficient:**

- `?mode=ro` → SQLite opens read-only; will not attempt journal creation, will not create `-shm` shared-memory sidecar (which is what trips up FUSE/network-FS mounts).
- `&immutable=1` is a **stronger** version that asserts the DB will never be modified by anyone (not even another process); this allows additional optimizations and skips even more sidecar attempts. **Recommended addition** for v1: change `kb/data/article_query.py:142` from `?mode=ro` to `?mode=ro&immutable=1` to defend against any future FUSE mount that interprets the bare `mode=ro` differently. **BUT** this is a `kb/`-source edit not on the exemption list (CONFIG-DBX-01 only allows `lib/llm_complete.py` + `kg_synthesize.py`), so it would require explicit user approval before merge. **Recommend NOT modifying article_query.py in kdb-1.5** — the `?mode=ro` pattern is industry-standard and works on FUSE mounts in practice.
- If kdb-2 first deploy actually exhibits a `database is locked` or `unable to open database file` error from `?mode=ro`-on-Volume (the SPIKE-DBX-01c documentary unknown), the fast-fix is to copy `kol_scan.db` to `/tmp/data/kol_scan.db` (~20 MB, ~1s copy time) at startup as part of the same adapter that copies lightrag_storage. **Recommend coding the adapter to optionally copy DB based on env var** (`OMNIGRAPH_DB_COPY_TO_TMP=1`) to give kdb-2 an instant escape hatch if the Volume-direct path fails.

**Implication for adapter design:**

- **Default:** copy lightrag_storage only; leave DB on Volume.
- **Escape hatch:** env-var-toggleable DB copy (off by default; turned on if kdb-2 first deploy fails on DB).
- **Total cold-start /tmp footprint** (default): 400–600 MB (lightrag_storage only). With DB copy: +20 MB ≈ 420–620 MB. Well within typical Apps `/tmp` size (which is sized to multiple GB on Azure managed instances; LOW confidence on exact ceiling — verify in kdb-2).

## Q5 — LLM-DBX-03 factory dry-run venue

**Verdict:** ✅ kdb-1.5 IS the right venue. Dry-run runs as a **standalone pytest** under `databricks-deploy/tests/test_provider_dryrun.py`, executed locally on the dev box with **user OAuth** (not Apps SP — that's kdb-2's first-deploy job). Test instantiates real LightRAG against real MosaicAI Model Serving endpoints (NOT mocked). Auth flows via the same `databricks --profile dev` OAuth used in kdb-1 PREFLIGHT-DBX-01.

**Evidence — auth path:**

- `kdb-1-PREFLIGHT-FINDINGS.md` Sub-test 1.2: `databricks --profile dev serving-endpoints query databricks-claude-sonnet-4-6 ...` → HTTP 200 in 2.65s. **Workspace + endpoints reachable from local dev box via user OAuth.**
- Sub-test 1.3: same path against embedding endpoint → HTTP 200 in 1.33s, dim=1024 confirmed.
- Implication: `WorkspaceClient()` instantiated in a pytest on local dev box reads `~/.databrickscfg` for `[dev]` profile → same OAuth → same path that PREFLIGHT verified. Dry-run will succeed.

**Evidence — adapter shape options:**

LightRAG ships two complementary entry points; the factory wraps these:

1. `lightrag.llm.openai.openai_complete_if_cache(model, prompt, ..., base_url, api_key, ...)` at `venv/Lib/site-packages/lightrag/llm/openai.py:206` — accepts `base_url` and `api_key`, routes through `openai.AsyncOpenAI` client. **Databricks Model Serving exposes an OpenAI-compatible REST endpoint** (per CLAUDE.md note "All endpoints support `llm/v1/chat`" + `openai-compatibility` in Databricks docs URL pattern, content unfortunately blocked from WebFetch in this env, MEDIUM confidence). The OpenAI-compat URL pattern is: `https://<workspace-host>/serving-endpoints` as `base_url` + use `databricks auth token` as the Bearer api_key.
2. `databricks.sdk.WorkspaceClient().serving_endpoints.query(name=..., messages=[ChatMessage(...)])` — confirmed working in PREFLIGHT-01 via CLI proxy (CLI uses the same SDK underneath). **Returns SDK-flavored response object, not OpenAI-compat dict** — adapter must extract `response.choices[0].message.content` (verified in PREFLIGHT response shape).

**Recommended factory implementation:**

```python
# databricks-deploy/lightrag_databricks_provider.py (sketch — final code in PLAN)
import os
from typing import Any
import numpy as np
from lightrag.utils import EmbeddingFunc, wrap_embedding_func_with_attrs

KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
KB_EMBEDDING_MODEL = os.environ.get("KB_EMBEDDING_MODEL", "databricks-qwen3-embedding-0-6b")
EMBEDDING_DIM = 1024  # Qwen3-0.6B locked

def make_llm_func():
    """Return a LightRAG-compatible llm_model_func wrapping MosaicAI Model Serving."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    w = WorkspaceClient()  # picks up DATABRICKS_HOST/CLIENT_ID/SECRET in Apps; ~/.databrickscfg locally

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        history_messages = history_messages or []
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role=ChatMessageRole.SYSTEM, content=system_prompt))
        for m in history_messages:
            role = ChatMessageRole(m.get("role", "user").upper())
            messages.append(ChatMessage(role=role, content=m["content"]))
        messages.append(ChatMessage(role=ChatMessageRole.USER, content=prompt))
        # SDK is sync; spin into thread to keep async contract
        import asyncio
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: w.serving_endpoints.query(name=KB_LLM_MODEL, messages=messages),
        )
        return resp.choices[0].message.content

    return llm_func

@wrap_embedding_func_with_attrs(embedding_dim=EMBEDDING_DIM, max_token_size=8192)
async def _embed(texts: list[str], **_kwargs) -> np.ndarray:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    import asyncio
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: w.serving_endpoints.query(name=KB_EMBEDDING_MODEL, input=texts),
    )
    # SDK returns .data: list[{embedding: list[float]}]; convert to (N, 1024) float32
    return np.array([d.embedding for d in resp.data], dtype=np.float32)

def make_embedding_func():
    """Return an EmbeddingFunc wrapping MosaicAI Qwen3-embedding-0-6b (dim=1024)."""
    return _embed  # already wrapped; returns EmbeddingFunc instance
```

**Plan Caveats** (executor must verify in actual code):

1. `WorkspaceClient.serving_endpoints.query()` for embedding endpoints accepts `input=...` keyword arg — verified via PREFLIGHT-01 sub-test 1.3 CLI command `--json '{"input":["hello world"]}'`. The Python SDK kwarg name should match (`input` per OpenAI-compat); confirm in dry-run test.
2. The SDK is **synchronous** (`w.serving_endpoints.query` is a regular method). Wrapping in `asyncio.to_thread` / `loop.run_in_executor` is required to maintain LightRAG's async contract. This is the recommended pattern; documented in CLAUDE.md "Calling Foundation Model serving endpoints" example.
3. Latency budget: PREFLIGHT measured LLM 2.65s + embedding 1.33s. With `embedding_func_max_async=4` + `embedding_batch_num=64`, kdb-2.5 re-index throughput ≈ 4 concurrent batches × 64 texts / 1.33s ≈ 192 emb/s, or ~10 sec per article (avg ~50 chunks/article). At ~2600 articles, full re-index ≈ 7h — within ROADMAP's 8–30h estimate. Reasonable.

**Dry-run e2e test structure:**

```
databricks-deploy/tests/test_provider_dryrun.py — pytest, runnable as:
  pytest databricks-deploy/tests/test_provider_dryrun.py -v --tb=long

Test 1: test_llm_factory_smoke
  - call make_llm_func()("Hello, world. Reply 'pong'.") → assert "pong" or non-empty string
  - assert latency < 10s

Test 2: test_embedding_factory_smoke
  - call make_embedding_func()(["test"]) → assert shape == (1, 1024)
  - assert dtype == np.float32

Test 3: test_lightrag_e2e_roundtrip (the LLM-DBX-03 acceptance test)
  - tmp_dir = "/tmp/lightrag_storage_dryrun_<unix-ts>/"
  - rag = LightRAG(working_dir=tmp_dir, llm_model_func=make_llm_func(), embedding_func=make_embedding_func())
  - await rag.initialize_storages()
  - 5 fixture articles (short, 200–500 chars each, mixed zh + en)
  - for art in fixtures: await rag.ainsert(art)
  - response = await rag.aquery("What topics appear in the test corpus?", QueryParam(mode="hybrid"))
  - assert len(response) > 50
  - assert os.path.exists(tmp_dir + "vdb_entities.json")
  - assert os.path.exists(tmp_dir + "graph_chunk_entity_relation.graphml")
  - load vdb_entities.json → assert ["embedding_dim"] == 1024
  - shutil.rmtree(tmp_dir)

Test 4 (smoke): test_dryrun_bilingual
  - 2 zh fixtures, 2 en fixtures
  - run zh query + en query
  - assert both return non-empty strings
  - covers risk #3 (Qwen3 bilingual quality) early-warning
```

**Time-box for dry-run:** ~10 min wallclock (5 articles × 2 ainsert avg, plus 4 queries ~ 10s each). Cost: ~$0.20–$0.80 in MosaicAI Model Serving — trivial.

**Dry-run venue verdict:** local pytest on dev box, user OAuth. **NO Apps deploy needed for kdb-1.5.** kdb-2 first deploy is when Apps-SP-injection delta gets exercised; if dry-run passes here, the only kdb-2 unknown is the SP-vs-user-OAuth auth differential, which is one config-string difference (Apps runtime auto-injects `DATABRICKS_CLIENT_ID/SECRET/HOST` per CLAUDE.md "Authentication" section).

## Architectural Decisions

### Decision 1: Copy strategy — `shutil.copytree` primary, `databricks-sdk w.files.download_directory` fallback

**Rationale:**

- FUSE mount is the documented Apps default (verified via Microsoft Learn UC Volume Apps doc, content not directly fetchable but cited via SUMMARY.md research). When FUSE works, `shutil.copytree("/Volumes/...", "/tmp/lightrag_storage/")` is simpler, faster (no SDK overhead), and uses zero auth.
- If FUSE is missing or broken, `WorkspaceClient().files.download_directory()` (Files API) reliably works using auto-injected SP credentials. Confirmed by PREFLIGHT-DBX-02 grant-capability evidence + docs cited in research.
- Adapter detects FUSE availability via `os.path.ismount("/Volumes/mdlg_ai_shared")` (matches SPIKE-DBX-01a probe).

**Sketch:**

```python
# databricks-deploy/startup_adapter.py
import os, shutil, time
from pathlib import Path

VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
TMP_ROOT = "/tmp/omnigraph_vault"

def hydrate_lightrag_storage_from_volume():
    """Copy /Volumes/.../lightrag_storage/ to /tmp/omnigraph_vault/lightrag_storage/.
    Idempotent: if /tmp target already populated, skip (App container reuse case)."""
    src = Path(VOLUME_ROOT) / "lightrag_storage"
    dst = Path(TMP_ROOT) / "lightrag_storage"
    if dst.exists() and any(dst.iterdir()):
        # Already hydrated this container instance
        return {"status": "skipped", "reason": "already_hydrated"}
    dst.mkdir(parents=True, exist_ok=True)

    # Try FUSE primary
    if os.path.ismount(VOLUME_ROOT) or src.exists():
        t0 = time.time()
        if any(src.iterdir()):  # source non-empty (post-kdb-2.5)
            shutil.copytree(src, dst, dirs_exist_ok=True)
            return {"status": "copied", "method": "fuse", "elapsed_s": time.time() - t0}
        else:
            # First deploy (pre-kdb-2.5) — empty source, leave dst empty too
            return {"status": "skipped", "reason": "source_empty_pre_seed"}

    # Fallback: SDK Files API
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    t0 = time.time()
    w.files.download_directory(
        f"/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage",
        str(dst),
        overwrite=True,
    )
    return {"status": "copied", "method": "sdk", "elapsed_s": time.time() - t0}
```

### Decision 2: `/tmp/` layout

```
/tmp/omnigraph_vault/
├── lightrag_storage/      # copied from /Volumes/.../lightrag_storage/
│   ├── vdb_*.json
│   ├── graph_*.graphml
│   ├── kv_store_*.json
│   └── kv_store_llm_response_cache.json   ← writable, query-time cache
└── (no /data/ subdir by default — DB read direct from Volume)
```

`OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` in `app.yaml`. `RAG_WORKING_DIR` resolves to `/tmp/omnigraph_vault/lightrag_storage` via `config.py`. `KB_DB_PATH` separately resolves via env to `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db` (DB stays on Volume). This split is achievable in `kb/config.py` if `KB_DB_PATH` env var is set explicitly (current behavior — `kb/config.py` already supports this).

### Decision 3: Factory file shape — wrap `WorkspaceClient.serving_endpoints.query()`

Sketch above (Q5 evidence section). Use SDK pattern (NOT OpenAI-compat with `base_url`) — rationale:

- SDK is the milestone-locked auth pattern (Apps runtime auto-injects credentials → `WorkspaceClient()` zero-config).
- OpenAI-compat would require manually retrieving `databricks auth token` at runtime as the api_key; doable but adds a moving part.
- SDK shape is verbatim what REQUIREMENTS LLM-DBX-01 (line 38) calls out for `lib/llm_complete.py` — same pattern reused in factory.
- Fallback to OpenAI-compat in dry-run if SDK reveals shape mismatch (per ROADMAP rev 3 line 78 "small custom HTTP wrapper around Model Serving REST API" escape hatch — though OpenAI-compat is the cleaner version of that fallback, since it reuses LightRAG's existing `lightrag.llm.openai.openai_complete_if_cache`).

### Decision 4: Dry-run e2e test — local pytest, user OAuth, real endpoints

Sketch above (Q5 implementation). 4 tests; ~10 min wallclock; ~$0.20–$0.80 cost.

## Risks

### Risk 1: 500–600 MB cold-start copy exceeds 60s budget

**Probability:** MEDIUM. UC Volume → App container throughput is documentary-only (no benchmark in research dimensions).

**Impact:** Apps health check times out → App fails to reach RUNNING → kdb-2 first deploy blocked.

**Mitigation:**
- Adapter sketches a fast-path (FUSE `shutil.copytree`) which on a properly mounted volume should hit local-filesystem speed (>100 MB/s).
- If kdb-2 first deploy fails the 60s budget, two falls back: (a) raise budget to 120s in `app.yaml`, (b) implement lazy-load (defer LightRAG init to first /synthesize request).
- Adapter MUST log copy-elapsed time + bytes so kdb-2 has data to make this call.

### Risk 2: LightRAG ↔ Databricks SDK shape mismatch

**Probability:** LOW–MEDIUM. SDK shape is well-documented + matches OpenAI-compat at the REST level. But edge cases (streaming, tool-use, special tokens) may diverge from what LightRAG's OpenAI client expects.

**Impact:** Dry-run e2e test fails; need to fall back to LightRAG's `openai_complete_if_cache(base_url=...)` pattern, which adds OAuth-token retrieval logic.

**Mitigation:** Dry-run test 3 exercises `ainsert + aquery` round-trip with REAL endpoints — this is exactly where mismatches surface. Time-box of ~30 min for fallback path is in ROADMAP rev 3 line 78.

### Risk 3: Qwen3-0.6B bilingual retrieval quality is poor

**Probability:** LOW–MEDIUM. Untested on this corpus. Per ROADMAP risk #3.

**Impact:** kdb-2.5 re-index burns $20–100 on a model that produces poor retrieval; full re-index needed with different model.

**Mitigation:** Dry-run test 4 (`test_dryrun_bilingual`) runs 2 zh + 2 en queries on small fixture. If retrieval is obviously poor (semantic mismatch, wrong-language hits), escalate to user BEFORE kdb-2.5. **Recommended fixture:** include 2 short zh articles + 2 en articles on **same topic** (e.g., "LangGraph" / "LangGraph 框架"); cross-lingual query "compare LangGraph and CrewAI" should retrieve from both. Cheap, fast, and surfaces the risk.

### Risk 4: `kv_store_llm_response_cache.json` non-atomic write corrupts on container kill

**Probability:** LOW. Apps containers normally drain gracefully on stop; SIGKILL is rare.

**Impact:** Corrupted JSON → next App start can't load cache → LightRAG init may raise on cache parse failure.

**Mitigation:**
- LightRAG's `JsonKVStorage._load_data` (verify in source — quick grep) likely catches JSON parse error and starts with empty cache. If not, document as known bug + add try/except wrapper in adapter.
- Long-term: CONC-DBX (deferred to v2) tackles atomic write properly.
- For v1, accept the rare-edge-case failure mode; document in RUNBOOK that "if App fails to start with cache parse error, delete `/tmp/omnigraph_vault/lightrag_storage/kv_store_llm_response_cache.json`."

### Risk 5: Adapter `os.makedirs(/tmp/...)` itself fails

**Probability:** very LOW. /tmp is the canonical writable scratch area on every Linux container.

**Impact:** Adapter raises at startup; App fails to start.

**Mitigation:** Defensive check at adapter top: `if not os.access('/tmp', os.W_OK): raise RuntimeError(...)` with clear message. Documents the assumption.

## Runtime State Inventory

> This is a refactor/migration phase (introducing a new code path that mirrors existing LightRAG init), not a rename. Most categories are N/A; documented for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — kdb-1.5 doesn't ingest/migrate any data. The lightrag_storage is empty at this phase per Q1. | None |
| Live service config | Apps service principal `app-omnigraph-kb` will be created in kdb-2 (NOT this phase). Spike-app SP from Wave 3 already deleted (verified in SPIKE-FINDINGS). | None for kdb-1.5; verify in kdb-2 |
| OS-registered state | None — adapter is library code, no daemons / cron / systemd | None |
| Secrets/env vars | None new — the 3 env vars (`OMNIGRAPH_LLM_PROVIDER`, `KB_LLM_MODEL`, `KB_EMBEDDING_MODEL`) are kdb-2 territory. Dry-run reads them from local shell env or hardcodes defaults. | None for kdb-1.5 |
| Build artifacts / installed packages | `databricks-sdk` Python package — verify present in `databricks-deploy/requirements.txt` (this file does not yet exist; will be created in kdb-2 per ROADMAP). For kdb-1.5 dry-run on local dev box, SDK must be installable: `pip install databricks-sdk`. | Local pip install if not present; document in dry-run README |

**Nothing significant in any category** — kdb-1.5 introduces NEW files only, modifies nothing.

## Common Pitfalls

### Pitfall 1: LightRAG `os.makedirs(workspace_dir, exist_ok=True)` on read-only Volume

**What goes wrong:** LightRAG's storage backend `__post_init__` raises `OSError [Errno 30] Read-only file system`.

**Source evidence:**
- `lightrag/kg/json_kv_impl.py:30-39` — `working_dir = self.global_config["working_dir"]` then `os.makedirs(workspace_dir, exist_ok=True)`
- `lightrag/kg/networkx_impl.py:41-50` — same pattern
- `lightrag/kg/nano_vector_db_impl.py:43-54` — same pattern

**Why it happens:** App SP has `READ_VOLUME` only (per AUTH-DBX-03); FUSE mount is read-only. `os.makedirs(exist_ok=True)` does NOT short-circuit when the dir already exists if the underlying syscall is `mkdir(2)` — Python checks `exist_ok` after the syscall, and on a RO mount the syscall fails first.

**How to avoid:** Point `working_dir` at `/tmp/omnigraph_vault/lightrag_storage/` (writable), not `/Volumes/...`.

**Warning signs:** App fails at startup; logs show `OSError [Errno 30]` from `lightrag.LightRAG.__init__` traceback.

### Pitfall 2: `write_json` non-atomic on /tmp

**What goes wrong:** Process crash mid-write to `kv_store_llm_response_cache.json` corrupts file.

**Source evidence:**
- `lightrag/utils.py:1255-1270` — direct `open("w") + json.dump`. No `.tmp` + rename. No `f.flush()` + `os.fsync()`.

**Why it happens:** LightRAG upstream design choice; tracked but not patched in v1 (research SUMMARY pitfall #4).

**How to avoid:** v1 accepts the rare-corruption failure mode. v2 CONC-DBX may patch upstream.

**Warning signs:** App fails to start with `json.JSONDecodeError` from `kv_store_llm_response_cache.json`. Recovery: delete the file (it's a cache; loss is recoverable).

### Pitfall 3: Adapter copy completes AFTER FastAPI module-load

**What goes wrong:** Apps health check returns 200 from FastAPI (which is uvicorn-bound) before the adapter has finished copying. First /synthesize request fails with FileNotFoundError.

**How to avoid:** Adapter MUST run **synchronously, before `app = FastAPI()`** or as a pre-uvicorn shell wrapper. Sketch:

```python
# databricks-deploy/main.py (the App's entry point — NOT this phase, but documenting)
from startup_adapter import hydrate_lightrag_storage_from_volume
hydrate_lightrag_storage_from_volume()  # blocks until copy done
# only NOW import + define FastAPI app
from kb.app import app  # or whatever the entry is
```

Or use `app.yaml` `command:` to run `bash -c "python -m startup_adapter && uvicorn ..."`.

**Warning signs:** Intermittent first-request failures on /synthesize after App restart.

### Pitfall 4: SDK call in async path without thread-pool offload

**What goes wrong:** `WorkspaceClient.serving_endpoints.query()` is synchronous; calling it directly in `async def llm_func` blocks the event loop.

**How to avoid:** Wrap in `loop.run_in_executor(None, lambda: w.serving_endpoints.query(...))` (sketch in Q5). Confirmed working pattern in CLAUDE.md "Calling Foundation Model serving endpoints" snippet (which is sync; for async use the executor wrapper).

**Warning signs:** During kdb-2.5 small-batch validation, throughput tanks dramatically — concurrent `embedding_func_max_async=4` calls serialize because event loop is blocked.

### Pitfall 5: `EmbeddingFunc` double-wrapping

**What goes wrong:** Wrapping a function decorated with `@wrap_embedding_func_with_attrs` in another `EmbeddingFunc` causes inner wrapper preprocessing to override outer settings.

**Source evidence:** `lightrag/utils.py:431-441` documents this exact pitfall.

**How to avoid:** Use `@wrap_embedding_func_with_attrs(embedding_dim=1024, ...)` decorator on the inner async function; expose it directly as `make_embedding_func()` return value (which is already an EmbeddingFunc). Do NOT wrap again.

**Warning signs:** Embedding dim mismatch errors at LightRAG init or first ainsert.

## Code Examples

### LightRAG factory (consumed by kdb-2.5 Job + future kdb-2 App)

See Q5 sketch above. Full file lives at `databricks-deploy/lightrag_databricks_provider.py`.

### Storage adapter

See Decision 1 sketch above. Full file lives at `databricks-deploy/startup_adapter.py`.

### Existing read-only DB pattern (reference, no edit)

```python
# kb/data/article_query.py:140-143 — DO NOT MODIFY in this phase
def _connect() -> sqlite3.Connection:
    """Open a read-only connection to KB_DB_PATH using SQLite URI mode."""
    uri = f"file:{config.KB_DB_PATH}?mode=ro"
    return sqlite3.connect(uri, uri=True)
```

### Existing LightRAG instantiation (reference, kdb-2 will swap factories)

```python
# kg_synthesize.py:106 — kdb-1.5 does NOT modify this; kdb-2 LLM-DBX-02 will
rag = LightRAG(
    working_dir=RAG_WORKING_DIR,
    llm_model_func=get_llm_func(),       # → kdb-2 dispatcher; for kdb-1.5 dry-run, factory directly
    embedding_func=embedding_func,        # → kdb-2 / dry-run swaps to make_embedding_func()
)
```

## State of the Art

| Old Approach | Current Approach (this phase) | When Changed | Impact |
|--------------|-------------------------------|--------------|--------|
| LightRAG `working_dir=/Volumes/.../lightrag_storage` direct on read-only mount | `working_dir=/tmp/omnigraph_vault/lightrag_storage` + startup hydration | kdb-1.5 (this phase) | Defends against `os.makedirs` on RO mount; makes query-time cache writes safe; leaves Volume read-only as designed |
| LightRAG `llm_model_func=deepseek_model_complete` + `embedding_func=gemini_embed_func` | `llm_model_func=make_llm_func()` (Databricks Sonnet) + `embedding_func=make_embedding_func()` (Qwen3 1024) | kdb-2 swap; kdb-1.5 validates the factory works | Retires DeepSeek + Gemini in v1 deploy; bilingual zh/en via Qwen3; in-workspace LLM (no external HTTPS) |
| Vector dim 3072 (Vertex Gemini) | Vector dim 1024 (Qwen3) | kdb-1.5 factory pin, kdb-2.5 re-index | 3× shrinkage on vdb_*.json files → ~1.3 GB Hermes → ~400–600 MB on Databricks |

**Deprecated/outdated:**
- DeepSeek provider in v1 Databricks deploy — fully retired per rev 3 constraint #1.
- Vertex Gemini path in v1 Databricks deploy — retired; code paths remain reachable via env var for non-Databricks deploys.

## Open Questions

1. **UC Volume → App `/tmp` throughput**
   - What we know: research suggests sub-30s for "few MB"; documentary only for hundreds of MB.
   - What's unclear: actual MB/s rate.
   - Recommendation: log copy-elapsed-time + bytes in adapter; capture in kdb-2 first-deploy SMOKE-EVIDENCE for benchmarking.

2. **Qwen3-0.6B Chinese retrieval quality on this corpus**
   - What we know: Qwen3 is bilingual, 1024-dim.
   - What's unclear: actual zh-CN retrieval quality on the 600 KOL + 1400 RSS corpus.
   - Recommendation: dry-run test 4 (`test_dryrun_bilingual`) on 2+2 fixture articles surfaces this in 10 min before kdb-2.5 commits to full re-index.

3. **Apps `/tmp` ceiling (exact)**
   - What we know: typically multi-GB on Azure managed-instance Apps; no hard number in research.
   - What's unclear: exact ceiling. With 400–600 MB target + 50–70 MB cache growth ceiling, we are well within typical limits, but a deterministic answer is missing.
   - Recommendation: kdb-2 first deploy can `df -h /tmp` from logs to record actual ceiling.

4. **Atomic-write upstream patch worth pursuing for v1?**
   - What we know: `lightrag/utils.py:1255-1270` is non-atomic; LightRAG version pinned at 1.4.15.
   - What's unclear: whether upstream LightRAG accepts a PR to make `write_json` atomic; whether monkeypatch is acceptable in `databricks-deploy/`.
   - Recommendation: out of scope for v1 (CONC-DBX deferred to v2 per OUT OF SCOPE table). Document in RUNBOOK that cache-corruption recovery = delete the cache file.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All | ✓ | 3.11+ | — |
| LightRAG | dry-run e2e test | ✓ | 1.4.15 (in venv) | — |
| `databricks-sdk` Python | factory + dry-run | ✗ on local dev box (verified — `python -c "from databricks.sdk import WorkspaceClient"` raised `ModuleNotFoundError`) | — | `pip install databricks-sdk` (executor's first task; document in PLAN) |
| `databricks` CLI | dry-run auth (~/.databrickscfg `[dev]` profile) | ✓ | 0.260.0 | — |
| MosaicAI Sonnet endpoint | dry-run LLM smoke + e2e | ✓ READY | `databricks-claude-sonnet-4-6` | — |
| MosaicAI Qwen3 endpoint | dry-run embed smoke + e2e | ✓ READY | `databricks-qwen3-embedding-0-6b` (dim 1024) | — |
| pytest | dry-run runner | ✓ (project venv) | — | — |
| numpy | factory return type | ✓ | (project venv) | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** `databricks-sdk` not installed in local venv — installation is straightforward (`pip install databricks-sdk`); document in PLAN as Wave 0 / setup task.

## Validation Architecture

> Per `.planning/config.json` workflow.nyquist_validation default (treat as enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7+ (existing project venv) |
| Config file | `pytest.ini` (none currently — see Wave 0) |
| Quick run command | `pytest databricks-deploy/tests/test_provider_dryrun.py::test_llm_factory_smoke -x` |
| Full suite command | `pytest databricks-deploy/tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LLM-DBX-03 (LLM factory) | `make_llm_func()` returns callable matching LightRAG signature; round-trip Sonnet | unit | `pytest databricks-deploy/tests/test_provider_dryrun.py::test_llm_factory_smoke -x` | ❌ Wave 0 |
| LLM-DBX-03 (embedding factory) | `make_embedding_func()` returns EmbeddingFunc; (1, 1024) shape | unit | `pytest databricks-deploy/tests/test_provider_dryrun.py::test_embedding_factory_smoke -x` | ❌ Wave 0 |
| LLM-DBX-03 (e2e roundtrip) | LightRAG ainsert + aquery emit graphml + vdb files; embedding_dim=1024 | integration | `pytest databricks-deploy/tests/test_provider_dryrun.py::test_lightrag_e2e_roundtrip -x` | ❌ Wave 0 |
| LLM-DBX-03 (bilingual sanity) | Qwen3 retrieves zh + en on cross-lingual query | integration | `pytest databricks-deploy/tests/test_provider_dryrun.py::test_dryrun_bilingual -x` | ❌ Wave 0 |
| STORAGE-DBX-05 (adapter idempotency) | `hydrate_lightrag_storage_from_volume()` skip-on-repeat + first-deploy-empty-source | unit | `pytest databricks-deploy/tests/test_startup_adapter.py -x` | ❌ Wave 0 |
| STORAGE-DBX-05 (adapter copy correctness) | mocked or tmp_path Volume → /tmp copy preserves file count + bytes | unit | `pytest databricks-deploy/tests/test_startup_adapter.py::test_copy_preserves_files -x` | ❌ Wave 0 |
| STORAGE-DBX-05 (cold-start time measurement) | adapter logs copy-elapsed-time + bytes for kdb-2 calibration | manual-only | `python -m databricks_deploy.startup_adapter` (run with synthetic Volume mock; capture log line) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest databricks-deploy/tests/ -k "smoke" -x` (smokes only, ~30s)
- **Per wave merge:** `pytest databricks-deploy/tests/ -v` (full dry-run, ~10 min, ~$0.20–$0.80)
- **Phase gate:** Full dry-run green + cold-start log captured before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `databricks-deploy/tests/__init__.py` (empty file, marks pkg)
- [ ] `databricks-deploy/tests/conftest.py` — shared fixtures (`tmp_dryrun_dir` w/ teardown; sample articles fixture)
- [ ] `databricks-deploy/tests/test_provider_dryrun.py` — covers LLM-DBX-03 (4 tests above)
- [ ] `databricks-deploy/tests/test_startup_adapter.py` — covers STORAGE-DBX-05 (idempotency + copy correctness)
- [ ] `databricks-deploy/tests/fixtures/` — 4 small articles (2 zh + 2 en, same topic)
- [ ] `databricks-deploy/lightrag_databricks_provider.py` — factory implementation
- [ ] `databricks-deploy/startup_adapter.py` — copy-on-startup implementation
- [ ] Local install: `pip install databricks-sdk` (executor's first task)

## Files Affected

| Path | Action | Notes |
|------|--------|-------|
| `databricks-deploy/` | **NEW** (directory) | Currently does not exist; mkdir |
| `databricks-deploy/lightrag_databricks_provider.py` | **NEW** | Factory file (LLM-DBX-03 deliverable) |
| `databricks-deploy/startup_adapter.py` | **NEW** | Copy-on-startup adapter (STORAGE-DBX-05 alt path) |
| `databricks-deploy/tests/__init__.py` | **NEW** | Test package marker |
| `databricks-deploy/tests/conftest.py` | **NEW** | Shared pytest fixtures |
| `databricks-deploy/tests/test_provider_dryrun.py` | **NEW** | LLM-DBX-03 dry-run e2e tests |
| `databricks-deploy/tests/test_startup_adapter.py` | **NEW** | STORAGE-DBX-05 unit tests |
| `databricks-deploy/tests/fixtures/article_zh_1.txt` etc. | **NEW** | 4 small fixture articles |
| `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/` | **NEW** (this dir) | Already created |
| `.planning/phases/kdb-1.5-.../kdb-1.5-RESEARCH.md` | **NEW** (this file) | This document |
| `lib/llm_complete.py` | **VERIFY-ONLY** | NOT modified in this phase (kdb-2 territory) |
| `kg_synthesize.py` | **VERIFY-ONLY** | NOT modified in this phase (kdb-2 territory) |
| `kb/data/article_query.py` | **VERIFY-ONLY** | NOT modified — existing `?mode=ro` URI works on Volume |
| `kb/config.py` | **VERIFY-ONLY** | NOT modified — `OMNIGRAPH_BASE_DIR` + `KB_DB_PATH` already split as needed |
| `kb/services/synthesize.py` | **VERIFY-ONLY** | NOT modified — existing `KG_MODE_AVAILABLE` graceful-degrade pattern is reused unchanged |

**Diff scope at end of phase:** all changes under `databricks-deploy/` and `.planning/phases/kdb-1.5-*/`. Zero `kb/` / `lib/` / top-level `*.py` changes. CONFIG-DBX-01 verification at kdb-3 will return empty for this phase's commits.

## Skill Picks

| Skill | Why |
|-------|-----|
| `python-patterns` | Adapter + factory are pure Python, async/await, dataclasses, pathlib idioms |
| `writing-tests` | Heavy pytest emphasis; dry-run is the phase's centerpiece; Testing Trophy says integration > unit (and our dry-run is integration) |
| `databricks-patterns` | SDK `WorkspaceClient` patterns, `serving_endpoints.query` shape, `~/.databrickscfg` profile auth |
| `search-first` | Before writing custom HTTP wrapper as fallback, search LightRAG's `lightrag.llm.openai` first (already documented as primary fallback option) |

Skills NOT picked (relevant siblings, but out of scope for this phase):

- `frontend-design` / `ui-ux-pro-max` — backend-only; no UI work
- `e2e-testing` (Playwright) — backend-only; no browser UAT (Rule 3 KB local UAT does NOT apply since no `kb/` template / static / API change)
- `streamlit-patterns` — App is FastAPI, not Streamlit
- `gemini-migration` — Vertex retired; Qwen3 is the new path (no Vertex code touched)

**Skill invocation discipline:** per `feedback_skill_invocation_not_reference.md`, the planner MUST emit explicit `Skill(skill="...")` tool calls in the executor lane prompts (not just list these in `<read_first>`).

## Sources

### Primary (HIGH confidence)

- `venv/Lib/site-packages/lightrag/lightrag.py` — version 1.4.15 (verified `_version.py`); query path traced `aquery → aquery_llm → kg_query → _query_done → llm_response_cache.index_done_callback` (lines 2622, 2884, 2974, 3045-3046)
- `venv/Lib/site-packages/lightrag/kg/json_kv_impl.py:39` — `os.makedirs(workspace_dir, exist_ok=True)` proof
- `venv/Lib/site-packages/lightrag/kg/networkx_impl.py:50` — same
- `venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py:54` — same
- `venv/Lib/site-packages/lightrag/utils.py:1255-1270` — `write_json` non-atomic proof
- `venv/Lib/site-packages/lightrag/utils.py:421-457` — `EmbeddingFunc` class definition + double-wrapping warning
- `venv/Lib/site-packages/lightrag/llm/openai.py:206` — `openai_complete_if_cache(base_url=...)` available fallback shape
- `kb/data/article_query.py:140-143` — existing `?mode=ro` URI pattern (no edit needed)
- `kg_synthesize.py:106` + `ingest_wechat.py:391-405` + `query_lightrag.py:20-23` — existing LightRAG instantiation pattern
- `lib/llm_complete.py` (full file, 49 lines) — existing dispatcher shape that LLM-DBX-01 will extend in kdb-2
- `lib/lightrag_embedding.py:180-240` — existing `embedding_func` shape (Vertex/Gemini); template for Databricks embedding factory
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md` — Model Serving reachability + grant capability ✅ verified
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-WAVE2-FINDINGS.md` — Volume populated; lightrag_storage/ INTENTIONALLY EMPTY (anti-pattern audit #5)
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-SPIKE-FINDINGS.md` — Apps SSO + Private Link blocker → kdb-1.5 trigger
- `.planning/research/kb-databricks-v1/SUMMARY.md` + `FEATURES.md` + `ARCHITECTURE.md` — pre-rev-3 research; size + adapter pattern findings still applicable
- SSH measurement against Hermes: production-only LightRAG storage = 1.315 GB across 12 files; vdb_relationships.json + vdb_entities.json = 1.13 GB combined (verified 2026-05-15)
- SSH measurement against Hermes: kol_scan.db PRAGMA journal_mode = `'delete'` (NOT WAL); 5105 pages × 4096 bytes = ~20 MB (matches WAVE2 evidence)
- REQUIREMENTS-kb-databricks-v1.md rev 3 — LLM-DBX-03 spec (lines 40-44); STORAGE-DBX-05 spec (line 24)
- ROADMAP-kb-databricks-v1.md rev 3 — Phase kdb-1.5 spec (lines 60-78); time-box; success criteria

### Secondary (MEDIUM confidence)

- Databricks Model Serving OpenAI-compatibility — referenced in CLAUDE.md project notes; direct doc fetch blocked by corp proxy (`docs.databricks.com` and `learn.microsoft.com` both inaccessible from WebFetch); inferred from CLI evidence in PREFLIGHT-FINDINGS sub-tests 1.2/1.3 which prove the SDK shape works.
- Apps cold-start budget = 60s — referenced in ROADMAP SPIKE-DBX-01d; documentary only.

### Tertiary (LOW confidence)

- UC Volume → App container Files-API throughput rate. Documentary "sub-30s for few MB"; no benchmark for hundreds of MB. Flagged in Q2 + Risk #1 + Open Question #1.
- Apps `/tmp` ceiling. Typically multi-GB; no exact number. Flagged in Open Question #3.
- Whether `WorkspaceClient.serving_endpoints.query()` accepts `input=...` kwarg directly for embedding endpoints (CLI uses `--json '{"input":[...]}'`; Python SDK kwarg name should match). Flagged in Q5 caveat #1; verifies in dry-run.

## Metadata

**Confidence breakdown:**

- Standard stack (LightRAG + databricks-sdk + pytest + numpy): HIGH — all source-traced
- Architecture (copy-to-/tmp + factory wrap): HIGH — kdb-1 SPIKE-FINDINGS already locked storage adapter as required; factory shape directly mirrors REQUIREMENTS LLM-DBX-03 spec
- Pitfalls: HIGH — all source-traced from venv/Lib/site-packages/lightrag/
- Q1 (empty source): HIGH — kdb-1 WAVE2-FINDINGS explicit
- Q2 (size + cold start): HIGH on size (measured); MEDIUM on cold-start (projected)
- Q3 (writes-during-query): HIGH — source-grep complete
- Q4 (DB on Volume): HIGH — existing pattern verified
- Q5 (dry-run venue): HIGH — auth path mirrors PREFLIGHT-DBX-01 exactly

**Research date:** 2026-05-15

**Valid until:** 2026-06-15 (30 days for stable; LightRAG 1.4.x is mature; Databricks SDK + Apps runtime have no announced breaking changes)
