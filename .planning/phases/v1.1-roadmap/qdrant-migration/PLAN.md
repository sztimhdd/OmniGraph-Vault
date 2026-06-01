---
phase: v1.1-qdrant-migration
parent_milestone: v1.1-roadmap
slug: qdrant-migration
depends_on: []
requirements: [SC-1, SC-2, SC-3, SC-4, SC-5, SC-6, SC-7, SC-8, SC-9, SC-10, SC-11, SC-12]
files_modified:
  - kb/api.py
  - ingest_wechat.py
  - kg_synthesize.py
  - scripts/qdrant_to_nanovdb.py        # new
  - scripts/qdrant_reingest_252.sh      # new
  - scripts/sync_to_databricks.sh       # comment-only
  - deploy/aliyun/systemd/qdrant-snapshot.service  # new
  - deploy/aliyun/systemd/qdrant-snapshot.timer    # new
  - tests/integration/test_aliyun_n4_lock_break.py # new
  - tests/unit/test_qdrant_to_nanovdb.py           # new
  - kb/deploy/kb-api.service.d/override.conf.example  # new — repo mirror of Aliyun additions
  - kb/deploy/omnigraph-ingest-services.service.d/override.conf.example  # new — generalized example for 3 ingest service drop-ins (morning/afternoon/evening)
autonomous: false
estimated_loc: 440-480
tier: plan-phase

must_haves:
  truths:
    - "Aliyun kb-api hydrate completes in ≤ 30 s on `systemctl restart` (was 56 min)."
    - "Aliyun ingest_wechat + kb-api both write/read from Qdrant docker on 127.0.0.1:6333; vdb_*.json no longer loaded into Python heap."
    - "Databricks /api/synthesize long_form returns valid mode='mix' answer reading vdb_*.json snapshots produced by 6-hour Qdrant→nano converter cron."
    - "Aliyun + Databricks both run LLM rerank on mode='mix' queries (HC-6 dual-station parity closed)."
    - "P5 lock contract preserved: kg_synthesize.py:221-226 `async with lightrag_lock: response = await asyncio.wait_for(rag.aquery(...), ...)` shape unchanged; HT-6 N=4 lock-break passes on Aliyun."
    - "Hermes RO until 2026-06-22 honored: zero Hermes-side files, env, or runtime touched. vdb_archive_*.json deferred-delete until 2026-06-22."
  artifacts:
    - path: "deploy/aliyun/systemd/qdrant-snapshot.service"
      provides: "Systemd one-shot that runs scripts/qdrant_to_nanovdb.py to refresh vdb_*.json from Qdrant."
    - path: "deploy/aliyun/systemd/qdrant-snapshot.timer"
      provides: "OnUnitActiveSec=6h timer that fires the snapshot service."
    - path: "scripts/qdrant_to_nanovdb.py"
      provides: "Atomic Qdrant→nano-vectordb JSON converter with embedding_dim+roundtrip guards."
      min_lines: 100
    - path: "scripts/qdrant_reingest_252.sh"
      provides: "6-batch wrapper around batch_ingest_from_spider.py with WeChat throttle pacing AND post-batch Qdrant count check (exits early when chunks ≥ 252)."
    - path: "kb/api.py"
      provides: "Lifespan singleton reads OMNIGRAPH_VECTOR_STORAGE; passes vector_storage='QdrantVectorDBStorage' when set to 'qdrant', otherwise default NanoVectorDBStorage."
    - path: "kb/deploy/kb-api.service.d/override.conf.example"
      provides: "Repo-tracked mirror of Aliyun's drop-in override.conf showing OMNIGRAPH_VECTOR_STORAGE=qdrant + 4 OMNIGRAPH_LLM_RERANK_* lines."
    - path: "kb/deploy/omnigraph-ingest-services.service.d/override.conf.example"
      provides: "Generalized repo-tracked mirror for the 3 Aliyun ingest service drop-ins (morning + afternoon + evening). Single source-of-truth shape; T9 copies these lines to all 3 live drop-ins on Aliyun."
    - path: "tests/integration/test_aliyun_n4_lock_break.py"
      provides: "HT-6 carrier — 4 concurrent /api/synthesize topic-distinct prompts asserting no crosstalk."
  key_links:
    - from: "kb/api.py:lifespan"
      to: "QdrantVectorDBStorage (LightRAG 1.4.16)"
      via: "vector_storage='QdrantVectorDBStorage' kwarg, gated by OMNIGRAPH_VECTOR_STORAGE env"
      pattern: "vector_storage=.*QdrantVectorDBStorage"
    - from: "ingest_wechat.py:_get_or_init_rag"
      to: "QdrantVectorDBStorage"
      via: "same env-gated kwarg"
      pattern: "vector_storage=.*QdrantVectorDBStorage"
    - from: "scripts/qdrant_to_nanovdb.py"
      to: "/root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json"
      via: "atomic .tmp+os.replace write per collection"
      pattern: "os\\.replace.*vdb_.*\\.json"
    - from: "scripts/sync_to_databricks.sh:Step 3"
      to: "Databricks UC Volume lightrag_storage/vdb_*.json"
      via: "tarball of /root/.hermes/omonigraph-vault/lightrag_storage/ (already covered)"
      pattern: "tar.*lightrag_storage"
---

# PLAN — v1.1.qdrant-migration

## Goal

Migrate Aliyun's LightRAG vector storage from in-process `NanoVectorDBStorage` (1.85 GB JSON loaded into Python heap, root cause of ISSUES #25 OOM crashes and #27 56-minute hydrate-on-restart throttle) to a separate `Qdrant` docker (`127.0.0.1:6333`, mmap-backed). Keep Databricks and Hermes on `NanoVectorDBStorage` reading `vdb_*.json`; bridge the two stations with a Python converter cron (`scripts/qdrant_to_nanovdb.py`) running every 6 hours that scrolls Qdrant and writes fresh `vdb_*.json` snapshots into the same `lightrag_storage/` path the existing `scripts/sync_to_databricks.sh` already picks up.

A single Aliyun kb-api restart applies three changes together (Qdrant cutover + 4 rerank env lines folded from #26 + structural #27 hydrate fix) to minimize hydrate-throttle blast radius. Phase closes ISSUES #25 (P0 root), #26 (rerank reconcile), #27 (hydrate throttle structural fix), and HC-6 (Aliyun + Databricks dual-station LLM rerank parity).

## Success Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| SC-1 | Qdrant docker running on Aliyun, bound `127.0.0.1:6333`, `restart=always`, volume `/var/lib/qdrant:/qdrant/storage`. | `ssh aliyun-vitaclaw "docker ps --filter name=qdrant --format '{{.Status}}'"` starts with `Up`; `ssh aliyun-vitaclaw "curl -s http://127.0.0.1:6333/healthz"` returns 200. |
| SC-2 | LightRAG `vector_storage` env-driven via `OMNIGRAPH_VECTOR_STORAGE` (`qdrant` \| `nanovectordb`; default `nanovectordb`); wired in 3 sites: `ingest_wechat.py:392`, `kb/api.py:89`, `kg_synthesize.py:155`. P5 lock contract preserved at `kg_synthesize.py:221-226`. | `grep -c 'OMNIGRAPH_VECTOR_STORAGE' ingest_wechat.py kb/api.py kg_synthesize.py` ≥ 3; `pytest tests/unit/test_kb_api_vector_storage_env.py -x` exits 0; `grep -n 'async with lightrag_lock' kg_synthesize.py` returns line 222 unchanged. |
| SC-3 | Aliyun re-ingest of 252 articles populates Qdrant collections in 6 batches × ≤ 50 articles (WeChat throttle floor) over 3-5 days. | `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'from qdrant_client import QdrantClient; c=QdrantClient(url=\"http://127.0.0.1:6333\"); print(c.get_collections())'"` lists chunks/entities/relationships namespaces; chunks count ≥ 252; sqlite `kol_scan.db` `ingestions.last_ingested_at` updated for the 252 article ids. |
| SC-4 | `scripts/qdrant_to_nanovdb.py` (~150-200 LoC) scrolls all Qdrant collections, writes atomic `.tmp+os.replace` `vdb_*.json` matching `{embedding_dim, data:[…], matrix:[…]}` schema, with embedding-dim guard + roundtrip-count smoke. | `wc -l scripts/qdrant_to_nanovdb.py` between 100 and 250; `python -c "from scripts.qdrant_to_nanovdb import export_collection_to_nanovdb"` imports clean; `pytest tests/unit/test_qdrant_to_nanovdb.py -x` exits 0 (asserts: 5-point fixture → output JSON has `embedding_dim==3072`, `len(data)==5`, `len(matrix)==5`, `data[0]["__id__"]` round-trips). |
| SC-5 | `deploy/aliyun/systemd/qdrant-snapshot.{service,timer}` deployed on Aliyun, cadence `OnUnitActiveSec=6h`, `WantedBy=timers.target`. | `ssh aliyun-vitaclaw "systemctl list-timers --all qdrant-snapshot.timer"` shows enabled + next-fire ≤ 6 h; `ssh aliyun-vitaclaw "journalctl -u qdrant-snapshot.service --since '12h ago'"` shows ≥ 1 successful run with marker `qdrant_snapshot_ok files_written=3 wall_s=…`. |
| SC-6 | `scripts/sync_to_databricks.sh` carries fresh `vdb_*.json` to Databricks (Step 3 tarball already covers `lightrag_storage/`; only added comment + version stamp — no functional change). | `git diff` on `scripts/sync_to_databricks.sh` shows only comment + echo-banner changes; first post-cutover sync run uploads new `vdb_*.json` to UC Volume; `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/ --profile dev` shows freshly-dated files. |
| SC-7 | Aliyun `/etc/systemd/system/kb-api.service.d/override.conf` appended with `OMNIGRAPH_VECTOR_STORAGE=qdrant` + 4 `OMNIGRAPH_LLM_RERANK_*` lines (folded from #26). | `ssh aliyun-vitaclaw "cat /etc/systemd/system/kb-api.service.d/override.conf"` contains all 5 lines verbatim; `ssh aliyun-vitaclaw "systemctl show kb-api.service \| grep -E 'OMNIGRAPH_(LLM_RERANK_\|VECTOR_STORAGE)'"` returns all 5 vars. |
| SC-8 | HT-6 N=4 lock-break test on deployed Aliyun kb-api passes: 4 concurrent `/api/synthesize` requests with topic-distinct prompts return topic-correct answers, no crosstalk, complete within `KB_SYNTHESIZE_TIMEOUT=240 s`. | `pytest tests/integration/test_aliyun_n4_lock_break.py -x` exits 0; pytest asserts 4 distinct topic markers in 4 distinct responses, total wall_s ≤ 270 s; `journalctl -u kb-api.service` emits `lightrag_lock_acquired` 4× and `lightrag_lock_released` 4× per request, no overlap. Evidence captured to `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break.log`. |
| SC-9 | Aliyun kb-api hydrate ≤ 30 s on `systemctl restart kb-api.service` post-cutover (was 56 min — closes #27). | `ssh aliyun-vitaclaw "journalctl -u kb-api.service --since 'last restart' \| grep lightrag_singleton_ready"` returns `wall_s=` ≤ 30 on 3 consecutive restarts. |
| SC-10 | `vdb_archive_*.json` deferred-delete extended to 2026-06-22 (Hermes RO unfreeze date, HC-7). Pre-cutover script renames `vdb_*.json` → `vdb_archive_*.json` AND creates symlinks `vdb_*.json → vdb_archive_*.json` so L1 rollback is a pure env-flip + restart. cleanup commented out / date-guarded; ISSUES.md follow-up reminder filed. | `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_archive_*.json"` shows 3 archive files dated pre-cutover; `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json | grep -v archive"` shows 3 symlinks pointing to corresponding `vdb_archive_*.json`; cleanup script contains either `# DO NOT RUN BEFORE 2026-06-22` comment OR `if [[ $(date +%s) -lt 1750564800 ]]; then exit 0; fi` guard. |
| SC-11 | Databricks deploy gate: first healthy `vdb_*.json` snapshot lands on Databricks UC Volume within 24 h post-cutover; `/api/synthesize` long_form on Databricks returns valid mode='mix' answer. | After first 6-h converter run + first `sync_to_databricks.sh` run completes, `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/vdb_chunks.json --profile dev` shows post-cutover mtime; smoke `curl https://<databricks-app-url>/api/synthesize` (via SSO browser console per existing Step 10 smoke 4) with a known KB-grounded prompt returns 200 with `mode='mix'` evidence in response or backend journal. |
| SC-12 | HC-6 closed: Aliyun + Databricks both run LLM rerank on `mode='mix'` queries; Aliyun via Vertex Gemini (per perf-fix-B + new env block from T7), Databricks via Databricks Haiku (per perf-fix-A, already deployed). | `ssh aliyun-vitaclaw "journalctl -u kb-api.service \| grep llm_rerank_dispatch"` shows `provider=vertex_gemini`; Databricks logz/stream shows `provider=databricks_claude_haiku` (already verified per STATE row B); both stations return non-empty rerank evidence on the same KB-grounded prompt. |

## LoC Estimate

| Component | LoC delta |
|-----------|----------:|
| `kb/api.py` lifespan: env-driven `vector_storage` | +15 |
| `ingest_wechat.py:392` env-driven kwarg | +5 |
| `kg_synthesize.py:155` CLI fallback ctor — same env split | +5 |
| `scripts/qdrant_to_nanovdb.py` converter (new) | +200 |
| `tests/unit/test_qdrant_to_nanovdb.py` (new) | +60 |
| `deploy/aliyun/systemd/qdrant-snapshot.{service,timer}` (new) | +30 |
| `scripts/sync_to_databricks.sh` comment + version stamp | +5 |
| `kb/deploy/kb-api.service.d/override.conf.example` (new repo mirror) | +12 |
| `kb/deploy/omnigraph-ingest-services.service.d/override.conf.example` (new — D13a) | +6 |
| `tests/integration/test_aliyun_n4_lock_break.py` (new HT-6 carrier) | +50 |
| `scripts/qdrant_reingest_252.sh` (new — incl. ~10 LoC for D9 post-batch Qdrant count() check) | +50 |
| `tests/unit/test_kb_api_vector_storage_env.py` (new — env-flag wiring) | +25 |
| **Net total** | **+463** |

**Justification for plan-phase tier at this size:** the +463 LoC ceiling is moderately above the original 400 target but well within plan-phase scope (≤ 600 LoC). The +50 budget for `test_aliyun_n4_lock_break.py` is justified per D13b: it is the SC-8 carrier and HT-6 trigger and must capture per-request evidence (job_id, topic, wall_s, response excerpt). The +6 LoC for the ingest-services drop-in example (D13a) prevents executor drift across 3 live Aliyun service overrides. The +10 LoC inside the reingest wrapper (D9) makes the 6th batch boundary count-driven, not hardcoded — robust against article-count drift between plan time and execute time. None of these increases warrant a tier downgrade.

## Async-Safety Strategy (P5 lock contract)

The P5 contract at `kg_synthesize.py:221-226` is:

```python
if lightrag_lock is not None:
    async with lightrag_lock:
        response = await asyncio.wait_for(
            rag.aquery(custom_prompt, param=param),
            timeout=KB_LIGHTRAG_INNER_TIMEOUT,
        )
```

This shape is observable by HT-6 N=4 lock-break tests and was verified on Databricks `01f15aeb`/`01f15af3`. It MUST NOT be modified by this phase.

The env-driven vector_storage split happens at LightRAG **instantiation**:
- `kb/api.py:89` (lifespan singleton)
- `kg_synthesize.py:155` (CLI fallback ctor)
- `ingest_wechat.py:392` (`_get_or_init_rag` ctor)

Lock acquisition is downstream of instantiation and is unaffected. **HT-3** halts the executor if any commit modifies the lock pattern beyond reading the env to choose vector_storage.

The `app.state.lightrag` + `app.state.lightrag_lock` pair created in `kb/api.py:98-99` remains the singleton handoff to routers. Qdrant changes only the storage backend behind `rag`, not the lock or the singleton.

## Tasks

> **Global halt trigger: HT-10 (Hermes RO breach) applies to every task in this phase.** Any commit, SCP, or systemctl mutation that touches Hermes-side code, env, or runtime — even read-side rsync targets that go beyond the existing operator-driven pull — halts the phase immediately and must be surfaced to the orchestrator for HC-7 violation review. Per-task `<halt_triggers>` lists below enumerate task-specific triggers; HT-10 is implicit in all of them.

<task id="T1" name="Env-driven vector_storage split (3 sites)">
  <wave>1</wave>
  <files>kb/api.py, ingest_wechat.py, kg_synthesize.py, tests/unit/test_kb_api_vector_storage_env.py</files>
  <read_first>
    - kb/api.py:75-110 (lifespan, current LightRAG ctor)
    - ingest_wechat.py:380-422 (_get_or_init_rag ctor)
    - kg_synthesize.py:140-240 (synthesize_response ctor + lock pattern at 221-226)
    - venv/Lib/site-packages/lightrag/kg/qdrant_impl.py:582-591 (LightRAG hard-codes url= from QDRANT_URL env; no path= mode)
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md (locked decision: Path 2)
  </read_first>
  <action>
    Add helper `_resolve_vector_storage()` returning `dict` of LightRAG kwargs, gated by `os.environ.get("OMNIGRAPH_VECTOR_STORAGE", "nanovectordb")`. When the value is `"qdrant"`, return `{"vector_storage": "QdrantVectorDBStorage"}`; otherwise return `{}` (LightRAG default — NanoVectorDBStorage).

    Wire it at three sites:

    1. **kb/api.py:89** — lifespan ctor. Add `**_resolve_vector_storage()` to the LightRAG kwargs. Preserve every existing kwarg verbatim (working_dir, llm_model_func, embedding_func, default_embedding_timeout, rerank_model_func). Emit `_log.warning("lightrag_vector_storage backend=%s", backend)` immediately after the ctor.

    2. **ingest_wechat.py:392** — `_get_or_init_rag` ctor. Same `**_resolve_vector_storage()` add. Preserve embedding_func_max_async / embedding_batch_num / llm_model_max_async / max_parallel_insert / addon_params verbatim. Emit a debug log line for the chosen backend.

    3. **kg_synthesize.py:155** — CLI fallback ctor (when `rag is None`). Same `**_resolve_vector_storage()` add. **DO NOT TOUCH lines 221-226 (lock pattern)** — HT-3.

    Place `_resolve_vector_storage()` once in `lib/vector_storage_env.py` (new ~25 LoC module) and import at all three sites; this avoids drift if a fourth site appears later.

    Write `tests/unit/test_kb_api_vector_storage_env.py` (~25 LoC):
    - Test 1: `OMNIGRAPH_VECTOR_STORAGE` unset → `_resolve_vector_storage()` returns `{}`.
    - Test 2: env `nanovectordb` → returns `{}`.
    - Test 3: env `qdrant` → returns `{"vector_storage": "QdrantVectorDBStorage"}`.
    - Test 4: env `bogus` → returns `{}` (default fallback) AND emits a warning log line.

    DO NOT modify the kg_synthesize.py lock acquisition pattern at lines 221-226 in any way (HT-3).

    Provider note (PRINCIPLE #5): plan-phase does not SSH-write. Execute-phase carries this commit to Aliyun.
  </action>
  <acceptance_criteria>
    - `grep -nE 'OMNIGRAPH_VECTOR_STORAGE|_resolve_vector_storage' kb/api.py ingest_wechat.py kg_synthesize.py lib/vector_storage_env.py` returns ≥ 4 hits.
    - `python -m pytest tests/unit/test_kb_api_vector_storage_env.py -x` exits 0.
    - `grep -nE 'async with lightrag_lock' kg_synthesize.py` returns line 222 unchanged (HT-3 invariant).
    - `python -c "import lib.vector_storage_env"` exits 0 with no ImportError.
    - `python -c "import os; os.environ['OMNIGRAPH_VECTOR_STORAGE']='qdrant'; from lib.vector_storage_env import _resolve_vector_storage; assert _resolve_vector_storage() == {'vector_storage': 'QdrantVectorDBStorage'}"` exits 0.
  </acceptance_criteria>
  <commit_msg>feat(qdrant-migration): env-driven vector_storage split at 3 LightRAG init sites</commit_msg>
  <halt_triggers>HT-3</halt_triggers>
  <addresses_sc>SC-2</addresses_sc>
</task>

<task id="T2" name="Qdrant→nano-vectordb converter + unit test">
  <wave>1</wave>
  <files>scripts/qdrant_to_nanovdb.py, tests/unit/test_qdrant_to_nanovdb.py</files>
  <read_first>
    - venv/Lib/site-packages/lightrag/kg/qdrant_impl.py:626-693 (upsert payload schema — ID_FIELD/WORKSPACE_ID_FIELD/CREATED_AT_FIELD + meta_fields)
    - venv/Lib/site-packages/lightrag/kg/qdrant_impl.py:695-724 (query return shape — `{**dp.payload, "distance", "created_at"}`)
    - .planning/quick/260601-qdrant-research/RESEARCH.md §"Path 2 conversion complexity" (pseudo-code)
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md (Aliyun snapshot — file sizes, embedding_dim=3072, 252 articles)
  </read_first>
  <action>
    Create `scripts/qdrant_to_nanovdb.py` (~200 LoC). Public function:

    ```python
    def export_collection_to_nanovdb(
        client: QdrantClient,
        collection_name: str,
        output_path: str,
        embedding_dim: int = 3072,
    ) -> dict:
        """Scroll a Qdrant collection, write nano-vectordb-format JSON atomically.

        Returns metrics dict: {points_written, dim_observed, wall_s}.
        Raises ValueError if observed dim != embedding_dim (HT-7).
        Raises RuntimeError if Qdrant.count != len(points_written) (roundtrip smoke).
        """
    ```

    Implementation requirements:
    - Use `client.scroll(collection_name=..., limit=500, offset=offset, with_payload=True, with_vectors=True)` until `next_offset is None`.
    - Map each point to `{"__id__": payload[ID_FIELD], "__created_at__": payload.get("created_at", 0), "content": payload.get("content", ""), **{k: payload[k] for k in ("file_path","full_doc_id","tokens","chunk_order_index","src_id","tgt_id") if k in payload}}`.
    - Note key translation: Qdrant stores `id` (no underscores) per `qdrant_impl.py:637`; LightRAG NanoVectorDBStorage expects `__id__`. Same for `created_at` → `__created_at__`.
    - Vector matrix: `[p.vector for p in batch]` (list of 3072-float lists).
    - Emit `nano_format = {"embedding_dim": embedding_dim, "data": [...], "matrix": [...]}`.
    - Validate `embedding_dim == len(matrix[0])` if matrix non-empty — else raise ValueError (HT-7). Empty matrix is valid (empty Qdrant collection produces empty data:[] valid JSON).
    - Validate `len(data) == client.count(collection_name).count` — else raise RuntimeError (roundtrip smoke).
    - Write atomically: `tmp = output_path + ".tmp"; json.dump(nano_format, open(tmp, "w")); os.replace(tmp, output_path)`.

    Top-level `main()`:
    - Read `LIGHTRAG_STORAGE_DIR` env (default `/root/.hermes/omonigraph-vault/lightrag_storage`).
    - Read `QDRANT_URL` env (default `http://127.0.0.1:6333`).
    - For each (collection_suffix → vdb_filename): chunks → vdb_chunks.json, entities → vdb_entities.json, relationships → vdb_relationships.json. Call `export_collection_to_nanovdb` for each.
    - Emit one structured log line per file: `qdrant_snapshot_file collection=<x> points=<n> wall_s=<w>`.
    - Final marker: `qdrant_snapshot_ok files_written=3 total_wall_s=<W>`.

    Write `tests/unit/test_qdrant_to_nanovdb.py` (~60 LoC):
    - Use `qdrant_client` `:memory:` mode (local in-memory ephemeral) to seed a 5-point fixture with payload keys `id`, `created_at`, `content`, `full_doc_id`, `file_path`.
    - Use 8-dim vectors (NOT 3072 — fast). Override `embedding_dim=8` for the test.
    - Call `export_collection_to_nanovdb(...)`; assert returned dict points_written=5, dim_observed=8.
    - Load output JSON; assert `embedding_dim==8`, `len(data)==5`, `len(matrix)==5`, `data[0]["__id__"]` round-trips one of the seeded ids, `data[0]["full_doc_id"]` preserved.
    - Add a guard test: write 8-dim points but call with `embedding_dim=3072` → expect `ValueError` (HT-7 invariant).
    - Add an empty-collection test: 0-point collection → empty data:[] valid JSON, no ValueError fired.

    Note: `qdrant_client` is NOT in `requirements.txt` (Aliyun-only via `venv-aim1`). Test uses `pytest.importorskip("qdrant_client")` so local CI without the package skips gracefully; Aliyun execute-phase has it via T5 install.
  </action>
  <acceptance_criteria>
    - `wc -l scripts/qdrant_to_nanovdb.py` between 100 and 250.
    - `python -c "from scripts.qdrant_to_nanovdb import export_collection_to_nanovdb"` exits 0 (assuming qdrant_client present).
    - `pytest tests/unit/test_qdrant_to_nanovdb.py -x` exits 0 OR emits `SKIPPED [qdrant_client not installed]` (acceptable in environments without qdrant_client).
    - `grep -c 'os.replace' scripts/qdrant_to_nanovdb.py` ≥ 1 (atomic write).
    - `grep -c 'embedding_dim' scripts/qdrant_to_nanovdb.py` ≥ 3 (guard + format key + arg).
  </acceptance_criteria>
  <commit_msg>feat(qdrant-migration): qdrant_to_nanovdb converter + unit test</commit_msg>
  <halt_triggers>HT-7</halt_triggers>
  <addresses_sc>SC-4</addresses_sc>
</task>

<task id="T3" name="Systemd snapshot timer + override.conf examples (kb-api + ingest) + sync-script comment + reingest wrapper">
  <wave>1</wave>
  <files>deploy/aliyun/systemd/qdrant-snapshot.service, deploy/aliyun/systemd/qdrant-snapshot.timer, kb/deploy/kb-api.service.d/override.conf.example, kb/deploy/omnigraph-ingest-services.service.d/override.conf.example, scripts/sync_to_databricks.sh, scripts/qdrant_reingest_252.sh</files>
  <read_first>
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md §"Aliyun read-only diagnostic snapshot" (override.conf 6 existing lines, /var/lib path)
    - .planning/quick/260601-qdrant-research/RESEARCH.md §"Q3 Re-ingest 287 articles real duration" (6-batch strategy, ≤50/batch)
    - scripts/sync_to_databricks.sh (entire — Step 3 tarball already covers lightrag_storage/)
    - .planning/phases/v1.1-roadmap/STATE-v1.1.md row B (existing override.conf has MemoryMax/KB_DEFAULT_LANG/timeouts — append, do NOT replace)
  </read_first>
  <action>
    Create six artifacts (was five — added per D13a fix):

    **1. `deploy/aliyun/systemd/qdrant-snapshot.service`**:
    ```ini
    [Unit]
    Description=OmniGraph Qdrant -> nano-vectordb JSON snapshot
    After=docker.service
    Requires=docker.service

    [Service]
    Type=oneshot
    User=root
    WorkingDirectory=/root/OmniGraph-Vault
    EnvironmentFile=/root/.hermes/.env
    Environment="LIGHTRAG_STORAGE_DIR=/root/.hermes/omonigraph-vault/lightrag_storage"
    Environment="QDRANT_URL=http://127.0.0.1:6333"
    ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/qdrant_to_nanovdb.py
    StandardOutput=journal
    StandardError=journal
    TimeoutStartSec=600
    ```

    **2. `deploy/aliyun/systemd/qdrant-snapshot.timer`**:
    ```ini
    [Unit]
    Description=Run Qdrant -> nano-vectordb JSON snapshot every 6h

    [Timer]
    OnBootSec=15min
    OnUnitActiveSec=6h
    Unit=qdrant-snapshot.service
    Persistent=true

    [Install]
    WantedBy=timers.target
    ```

    **3. `kb/deploy/kb-api.service.d/override.conf.example`** (repo mirror of Aliyun additions, ~12 lines):
    ```ini
    # Aliyun /etc/systemd/system/kb-api.service.d/override.conf — repo mirror.
    # The live file is APPEND-ONLY: existing lines (MemoryMax=12G, KB_DEFAULT_LANG=zh-CN,
    # KB_SYNTHESIZE_TIMEOUT=240, KB_LIGHTRAG_INNER_TIMEOUT=150,
    # LIGHTRAG_EMBEDDING_TIMEOUT=90) are preserved by the executor; this file
    # ONLY documents the lines THIS PHASE adds.
    [Service]
    Environment="OMNIGRAPH_VECTOR_STORAGE=qdrant"
    Environment="OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini"
    Environment="OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite"
    Environment="OMNIGRAPH_LLM_RERANK_TOP_K=30"
    Environment="OMNIGRAPH_LLM_RERANK_TIMEOUT=20"
    ```

    **4. `kb/deploy/omnigraph-ingest-services.service.d/override.conf.example`** (NEW — D13a fix; generalized example for the 3 ingest service drop-ins on Aliyun, ~6 lines):
    ```ini
    # Generalized example — apply to all 3 ingest service drop-ins on Aliyun:
    #   /etc/systemd/system/omnigraph-morning-ingest.service.d/override.conf
    #   /etc/systemd/system/omnigraph-afternoon-ingest.service.d/override.conf
    #   /etc/systemd/system/omnigraph-evening-ingest.service.d/override.conf
    # Existing lines on each live drop-in are preserved (HT-4 pre-check enforced); T9 ONLY appends:
    [Service]
    Environment="OMNIGRAPH_VECTOR_STORAGE=qdrant"
    ```

    **5. `scripts/sync_to_databricks.sh`** — comment-only diff:
    - At Step 3 banner add: `echo "  (Step 3 carries Qdrant→nano snapshot from /root/.hermes/omonigraph-vault/lightrag_storage/, refreshed every 6h by qdrant-snapshot.timer — see v1.1.qdrant-migration phase)"`.
    - At top header block, append a line: `# 2026-06-XX: post v1.1.qdrant-migration cutover — vdb_*.json is now Qdrant-derived (6h snapshot cron). No code change to this script; documenting source-of-truth shift.`

    **6. `scripts/qdrant_reingest_252.sh`** (~50 LoC):
    - Bash. Sources `/root/.hermes/.env` via `set -a; source /root/.hermes/.env; set +a`.
    - **D9 fix:** before each batch, query Qdrant chunk count via `venv-aim1/bin/python -c "from qdrant_client import QdrantClient; c=QdrantClient(url='http://127.0.0.1:6333'); print(c.count('lightrag_vdb_chunks').count)"`. If count ≥ 252, exit early with marker `qdrant_reingest_done batches=${i} chunks=${count} (early exit, target met)`.
    - Otherwise run batch: `cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_ingest_from_spider.py --max-articles 50 --topics ai --reset-checkpoint=false 2>&1 | tee /root/.hermes/qdrant-reingest-batch-${i}.log`.
    - Loop bound: maximum **6 batches**. Wrapper exits when `chunks ≥ 252` OR after 6 batches, whichever first. Final batch will naturally only ingest the remainder (e.g. 252 - 5×50 = 2 articles); WeChat throttle tolerates batches < 50 silently.
    - Between batches sleep `${BATCH_COOLDOWN_S:-3600}` seconds (WeChat throttle floor; 1h default).
    - After each batch: log Qdrant chunk count alongside batch metrics.
    - Halt-on-failure: `set -euo pipefail`; if any batch returns non-zero, exit and emit `qdrant_reingest_halt batch=${i}`.
    - Exit marker on full completion: `qdrant_reingest_done batches=6 chunks=${count} total_wall_s=${SECONDS}`.

    Note (PRINCIPLE #5 + #7): all six artifacts are repo files committed in Wave 1. Wave 2 executor SCPs / installs them via systemd; Wave 3 executor runs reingest. No SSH-write happens during plan-phase.
  </action>
  <acceptance_criteria>
    - `ls deploy/aliyun/systemd/qdrant-snapshot.service deploy/aliyun/systemd/qdrant-snapshot.timer kb/deploy/kb-api.service.d/override.conf.example kb/deploy/omnigraph-ingest-services.service.d/override.conf.example scripts/qdrant_reingest_252.sh` all exist.
    - `grep -c 'OnUnitActiveSec=6h' deploy/aliyun/systemd/qdrant-snapshot.timer` == 1.
    - `grep -c 'OMNIGRAPH_VECTOR_STORAGE=qdrant' kb/deploy/kb-api.service.d/override.conf.example` == 1.
    - `grep -c 'OMNIGRAPH_LLM_RERANK_' kb/deploy/kb-api.service.d/override.conf.example` == 4.
    - `grep -c 'OMNIGRAPH_VECTOR_STORAGE=qdrant' kb/deploy/omnigraph-ingest-services.service.d/override.conf.example` == 1.
    - `git diff scripts/sync_to_databricks.sh` shows only comment + echo additions, zero behavior change (verify with `bash -n scripts/sync_to_databricks.sh` exits 0).
    - `bash -n scripts/qdrant_reingest_252.sh` exits 0 (syntax valid).
    - `grep -c 'qdrant_client.*count\|c.count' scripts/qdrant_reingest_252.sh` ≥ 1 (D9 — count-driven early exit gate present).
    - `grep -c '6h\|--max-articles 50' scripts/qdrant_reingest_252.sh` ≥ 2.
  </acceptance_criteria>
  <commit_msg>feat(qdrant-migration): systemd snapshot timer + override.conf examples (kb-api + ingest) + reingest wrapper</commit_msg>
  <halt_triggers>none (read-only repo file creation)</halt_triggers>
  <addresses_sc>SC-5, SC-6, SC-7, SC-3 (wrapper for re-ingest)</addresses_sc>
</task>

<task id="T4" name="HT-6 N=4 lock-break integration test (network-gated)">
  <wave>1</wave>
  <files>tests/integration/test_aliyun_n4_lock_break.py</files>
  <read_first>
    - .planning/phases/v1.1-roadmap/P5/P5-VERIFICATION.md (Branch A N=4 evidence shape)
    - kg_synthesize.py:221-226 (lock pattern under test)
    - tests/integration/ (whatever conftest.py / fixtures exist for skip-graceful network gates)
  </read_first>
  <action>
    Create `tests/integration/test_aliyun_n4_lock_break.py` (~50 LoC).

    Behavior:
    - Read `ALIYUN_KB_API_URL` env (default `http://127.0.0.1:18766` for SSH-tunnel; or via test runner direct from local laptop).
    - If unreachable (TCP connect fails, or `requests.get(url + "/health", timeout=5)` raises), `pytest.skip("ALIYUN_KB_API_URL unreachable — set var + open SSH tunnel before running this test")`.
    - 4 topic-distinct prompts (each a different known KB-grounded entity, e.g., "LightRAG", "agentic-RAG", "DeepSeek API", "Vertex Gemini reranker"). Hardcode 4 unique topic markers.
    - Use `concurrent.futures.ThreadPoolExecutor(max_workers=4)` to fire 4 simultaneous `POST /api/synthesize {query, mode:"long_form"}`. Poll each job_id until done.
    - Assert: each response contains its OWN topic marker (no crosstalk — topic A response doesn't contain topic B/C/D markers).
    - Assert: total wall-clock ≤ 270 s (KB_SYNTHESIZE_TIMEOUT 240 s + 30 s slack).
    - Write evidence to `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break.log` (append-mode), capturing per-request: job_id, topic, wall_s, first 200 chars of response.

    Use `pytest.mark.integration` so the test is excluded from default unit runs.

    Provider note: this test is the HT-6 carrier transferred A → B → #26 → #25.
  </action>
  <acceptance_criteria>
    - `pytest tests/integration/test_aliyun_n4_lock_break.py --collect-only` lists 1 test (collection ok).
    - `python -c "import tests.integration.test_aliyun_n4_lock_break"` imports clean (no syntax errors).
    - `grep -c 'pytest.skip' tests/integration/test_aliyun_n4_lock_break.py` ≥ 1 (skip-graceful gate present).
    - `grep -c 'ThreadPoolExecutor\|concurrent.futures' tests/integration/test_aliyun_n4_lock_break.py` ≥ 1.
    - Wave 4 T10 will RUN it; Wave 1 T4 only ships the file.
  </acceptance_criteria>
  <commit_msg>test(qdrant-migration): N=4 lock-break integration test for Aliyun kb-api</commit_msg>
  <halt_triggers>none (read-only test file creation; HT-6 fires when Wave 4 T10 runs it)</halt_triggers>
  <addresses_sc>SC-8</addresses_sc>
</task>

<wave1_gate>
**Wave 1 close condition:** All four T1-T4 commits land on `main`. CI (or local pytest) runs `pytest tests/unit/test_kb_api_vector_storage_env.py tests/unit/test_qdrant_to_nanovdb.py -x` and exits 0 (qdrant_to_nanovdb may skip-graceful if qdrant_client not installed locally). PR #4 annotated as superseded by these commits — do NOT merge PR #4.
</wave1_gate>

<task id="T5" name="Aliyun: install qdrant-client + start Qdrant docker">
  <wave>2</wave>
  <files>(Aliyun-side state mutation; no repo file change)</files>
  <read_first>
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md §"Aliyun read-only diagnostic snapshot" (Docker 29.1.3 installed; qdrant-client NOT in venv-aim1; /var/lib free)
    - .planning/quick/260601-qdrant-research/RESEARCH.md §"Q4 Qdrant docker on Aliyun resources" (RAM/disk fits)
    - aliyun_vitaclaw_ssh.md (project memory) for SSH alias
  </read_first>
  <action>
    Executor (Aliyun-side via `ssh aliyun-vitaclaw`, PRINCIPLE #5 write-op):

    **Pre-flight (HT-1):**
    - `df -h /var/lib` → free ≥ 5 GB (HT-2). If less, halt.
    - `ls /root/.hermes/gcp-paid-sa.json` exists; `grep GOOGLE_CLOUD_PROJECT /root/.hermes/.env` returns project line.
    - `docker --version` returns `Docker version 29.x` (or any 20.x+).

    **Install qdrant-client in venv-aim1:**
    - `cd /root/OmniGraph-Vault && venv-aim1/bin/pip install 'qdrant-client>=1.7,<2.0'` (matches LightRAG 1.4.16 expectation).
    - Verify: `venv-aim1/bin/python -c "import qdrant_client; print(qdrant_client.__version__)"` returns ≥ 1.7.

    **Provision /var/lib/qdrant:**
    - `mkdir -p /var/lib/qdrant && chmod 0755 /var/lib/qdrant`.

    **Start Qdrant docker:**
    ```bash
    docker run -d \
      --name qdrant \
      --restart=always \
      -p 127.0.0.1:6333:6333 \
      -v /var/lib/qdrant:/qdrant/storage \
      qdrant/qdrant:v1.11.5
    ```
    Pin to `v1.11.5` (verified compatible with qdrant-client 1.7+ and LightRAG 1.4.16; do not use `:latest` — silent version drift risk).

    **Verify:**
    - `docker ps --filter name=qdrant --format '{{.Status}}'` starts with `Up`.
    - `curl -s http://127.0.0.1:6333/healthz` returns 200.
    - `docker logs qdrant 2>&1 | tail -20` shows `Qdrant HTTP listening on 6333` (or equivalent).
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "docker ps --filter name=qdrant --format '{{.Status}}'"` starts with `Up`.
    - `ssh aliyun-vitaclaw "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:6333/healthz"` returns `200`.
    - `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'import qdrant_client; print(qdrant_client.__version__)'"` returns version ≥ 1.7.
    - `ssh aliyun-vitaclaw "ls -ld /var/lib/qdrant"` shows directory present.
  </acceptance_criteria>
  <commit_msg>(no commit — Aliyun state mutation only; record in execute-phase journal)</commit_msg>
  <halt_triggers>HT-1, HT-2</halt_triggers>
  <addresses_sc>SC-1</addresses_sc>
</task>

<task id="T6" name="Aliyun: archive vdb_*.json + create rollback symlinks (pre-cutover)">
  <wave>2</wave>
  <files>(Aliyun-side state mutation only)</files>
  <read_first>
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md (vdb_*.json sizes 1.85 GB total)
    - .planning/quick/260601-qdrant-research/RESEARCH.md §"Q3 Mitigation strategy" (deferred-delete protocol)
    - HC-7 (Hermes RO until 2026-06-22)
  </read_first>
  <action>
    Executor (Aliyun-side):

    **Stop kb-api gracefully** (so we don't move files out from under a live process):
    ```bash
    ssh aliyun-vitaclaw "systemctl stop kb-api.service"
    sleep 5
    ssh aliyun-vitaclaw "systemctl is-active kb-api.service"  # expect 'inactive'
    ```

    **Rename to archive + create rollback symlinks** (D7 fix — `mv` + `ln -s` keeps L1 rollback as a pure ~30s env-flip + restart; the symlinks let NanoVectorDBStorage transparently read the archive when L1 is invoked, with NO 1.85 GB `cp` step):
    ```bash
    cd /root/.hermes/omonigraph-vault/lightrag_storage
    mv vdb_chunks.json vdb_archive_chunks.json
    mv vdb_entities.json vdb_archive_entities.json
    mv vdb_relationships.json vdb_archive_relationships.json
    # Symlinks for L1 rollback path — when OMNIGRAPH_VECTOR_STORAGE=nanovectordb is restored,
    # LightRAG opens vdb_chunks.json and follows the symlink to vdb_archive_chunks.json.
    ln -s vdb_archive_chunks.json vdb_chunks.json
    ln -s vdb_archive_entities.json vdb_entities.json
    ln -s vdb_archive_relationships.json vdb_relationships.json
    ```

    **Verify the rename + symlinks:**
    ```bash
    ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json
    # Expect 6 entries:
    #   3 regular files: vdb_archive_chunks.json, vdb_archive_entities.json, vdb_archive_relationships.json (totaling ~1.85 GB)
    #   3 symlinks: vdb_chunks.json -> vdb_archive_chunks.json, vdb_entities.json -> vdb_archive_entities.json, vdb_relationships.json -> vdb_archive_relationships.json
    ```

    **CRITICAL — break the symlinks BEFORE the converter cron first runs.** Once T8 enables the timer (or fires the manual run), `qdrant_to_nanovdb.py` will write `vdb_*.json.tmp` then `os.replace(tmp, vdb_*.json)`. `os.replace` REPLACES the symlink atomically with a regular file (the symlinks are NOT followed by `os.replace`). After the first converter run, vdb_*.json is a fresh regular file (Qdrant-derived) and the L1 rollback path requires re-creating the symlinks (documented in L1 rollback step). This is intentional: pre-converter L1 = symlink path; post-converter L1 = `ln -sf` recreate path.

    **Document deferred-delete policy** (D13c fix — README placed in PARENT dir, NOT inside lightrag_storage/, so existing rsync to Databricks UC Volume + Hermes does NOT pick it up; README is for Aliyun operators only):
    - Append to `/root/.hermes/omonigraph-vault/README.qdrant-migration.txt` (new file; **NOTE: parent dir, NOT lightrag_storage/**):
      ```
      vdb_archive_*.json (in lightrag_storage/) — last NanoVectorDBStorage snapshot before Qdrant cutover.
      DO NOT DELETE before 2026-06-22 (Hermes RO unfreeze date — HC-7).
      Hermes pulls from this directory until then.

      vdb_*.json (in lightrag_storage/) — pre-T8 these are SYMLINKS to vdb_archive_*.json (rollback path);
      post-T8 they are regular files written atomically by qdrant_to_nanovdb.py every 6h.

      L1 rollback path:
        - Pre-converter-first-run: env-flip OMNIGRAPH_VECTOR_STORAGE=nanovectordb + restart. Symlinks resolve naturally.
        - Post-converter: env-flip + `ln -sf vdb_archive_*.json vdb_*.json` recreate (3 lines), then restart.
      ```

    NOTE: this task does NOT yet restart kb-api. T7 will, after override.conf is updated.

    Provider note: this is a read-only-from-the-rest-of-the-world transition (rename + symlink ≠ delete). Hermes rsync was already pulling from this dir; with vdb_*.json as symlinks pointing to vdb_archive_*.json, Hermes still sees identical content (rsync follows symlinks for file content by default; for archive disambiguation, Hermes operators can choose to pull either name).
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_archive_*.json"` shows 3 regular files totaling ~1.85 GB.
    - `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json | grep -v archive"` shows 3 symlinks (output starts with `l`), each pointing to `vdb_archive_*.json` (verify with `readlink`).
    - `ssh aliyun-vitaclaw "readlink /root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json"` returns `vdb_archive_chunks.json`.
    - `ssh aliyun-vitaclaw "cat /root/.hermes/omonigraph-vault/README.qdrant-migration.txt"` contains "DO NOT DELETE before 2026-06-22" AND `ssh aliyun-vitaclaw "ls /root/.hermes/omonigraph-vault/lightrag_storage/README.qdrant-migration.txt 2>&1 | grep -c 'No such file'"` ≥ 1 (README is in PARENT dir, NOT under lightrag_storage/, so it does NOT propagate to Databricks UC Volume via Step 3 tarball nor to Hermes via existing rsync).
    - `ssh aliyun-vitaclaw "systemctl is-active kb-api.service"` returns `inactive`.
  </acceptance_criteria>
  <commit_msg>(no commit — Aliyun state mutation only)</commit_msg>
  <halt_triggers>none specific; HT-1 pre-flight covers it</halt_triggers>
  <addresses_sc>SC-10</addresses_sc>
</task>

<task id="T7" name="Aliyun: append override.conf + restart kb-api on Qdrant + verify hydrate ≤30s">
  <wave>2</wave>
  <files>(Aliyun-side state mutation; reads kb/deploy/kb-api.service.d/override.conf.example for content)</files>
  <read_first>
    - kb/deploy/kb-api.service.d/override.conf.example (T3-shipped — what to APPEND on Aliyun)
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/systemd-drift-diff.txt (live override.conf has 6 lines; do NOT replace — append only)
    - HT-4 trigger condition
  </read_first>
  <action>
    Executor (Aliyun-side):

    **HT-4 pre-check — verify live override.conf shape unchanged since perf-fix-B:**
    ```bash
    ssh aliyun-vitaclaw "cat /etc/systemd/system/kb-api.service.d/override.conf"
    # Expect exactly the 6 known lines: MemoryMax=12G, KB_DEFAULT_LANG=zh-CN,
    # KB_SYNTHESIZE_TIMEOUT=240, KB_LIGHTRAG_INNER_TIMEOUT=150,
    # LIGHTRAG_EMBEDDING_TIMEOUT=90, plus the [Service] header.
    ```
    If any unfamiliar line is present (e.g. another phase added something), HALT with HT-4 and surface diff to orchestrator.

    **Backup:**
    ```bash
    ssh aliyun-vitaclaw "cp /etc/systemd/system/kb-api.service.d/override.conf /etc/systemd/system/kb-api.service.d/override.conf.bak-pre-qdrant-migration"
    ```

    **Append the 5 new lines** (single ssh `cat <<'EOF' >> override.conf` — careful to preserve [Service] section semantics; systemd allows multiple Environment= lines under one [Service]):
    ```bash
    ssh aliyun-vitaclaw "cat >> /etc/systemd/system/kb-api.service.d/override.conf <<'EOF'
    Environment=\"OMNIGRAPH_VECTOR_STORAGE=qdrant\"
    Environment=\"OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini\"
    Environment=\"OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite\"
    Environment=\"OMNIGRAPH_LLM_RERANK_TOP_K=30\"
    Environment=\"OMNIGRAPH_LLM_RERANK_TIMEOUT=20\"
    EOF"
    ```

    **Sync repo code to Aliyun** (ensure T1/T2/T3 commits are present on Aliyun): execute-phase has its own commit-and-deploy step; for this plan, document that Aliyun must `cd /root/OmniGraph-Vault && git pull --ff-only origin main` before T7's restart, so kb-api boots with the env-driven vector_storage code.

    **Reload + restart:**
    ```bash
    ssh aliyun-vitaclaw "systemctl daemon-reload && systemctl restart kb-api.service"
    ```

    **Verify the restart applies all 3 changes simultaneously:**
    ```bash
    ssh aliyun-vitaclaw "systemctl show kb-api.service | grep -E 'OMNIGRAPH_(VECTOR_STORAGE|LLM_RERANK_)'"
    # Expect 5 lines, all present.

    ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '5min ago' | grep lightrag_singleton_ready"
    # Expect: lightrag_singleton_ready wall_s=<X.XX>
    # X must be ≤ 30 (HT-5 threshold = 60).
    ```

    **HT-5 trigger:** if `wall_s > 60`, halt; do NOT mark SC-9. Investigate (Qdrant collections empty + no vdb_*.json fallback path → check that LightRAG initialized cleanly against empty Qdrant).

    **First-query smoke (rerank verification, SC-12 partial):**
    ```bash
    ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8766/api/synthesize \
      -H 'Content-Type: application/json' \
      -d '{\"query\":\"What is LightRAG?\", \"mode\":\"long_form\"}'"
    # Then watch journalctl for llm_rerank_dispatch provider=vertex_gemini.
    ```

    Note (PRINCIPLE #5 + #7): execute-phase carries this. Plan-phase only specifies.
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "cat /etc/systemd/system/kb-api.service.d/override.conf | grep -cE 'OMNIGRAPH_(VECTOR_STORAGE|LLM_RERANK_)'"` returns `5`.
    - `ssh aliyun-vitaclaw "systemctl is-active kb-api.service"` returns `active`.
    - `ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '10min ago' | grep -oE 'lightrag_singleton_ready wall_s=[0-9.]+' | head -1"` returns `wall_s=` ≤ 30.
    - `ssh aliyun-vitaclaw "ls /etc/systemd/system/kb-api.service.d/override.conf.bak-pre-qdrant-migration"` exists (rollback path).
    - First synthesize call emits `llm_rerank_dispatch provider=vertex_gemini` in journalctl (SC-12 partial — full SC-12 verified post-reingest).
  </acceptance_criteria>
  <commit_msg>(no commit — Aliyun state mutation only)</commit_msg>
  <halt_triggers>HT-4, HT-5</halt_triggers>
  <addresses_sc>SC-7, SC-9, SC-12 (partial — full needs reingest data)</addresses_sc>
</task>

<task id="T8" name="Aliyun: install + enable qdrant-snapshot.timer; verify first run">
  <wave>2</wave>
  <files>(Aliyun-side state mutation; SCPs deploy/aliyun/systemd/qdrant-snapshot.{service,timer} from T3)</files>
  <read_first>
    - deploy/aliyun/systemd/qdrant-snapshot.service (T3 artifact)
    - deploy/aliyun/systemd/qdrant-snapshot.timer (T3 artifact)
    - scripts/qdrant_to_nanovdb.py (T2 artifact — must be importable on Aliyun via venv-aim1)
  </read_first>
  <action>
    Executor (Aliyun-side):

    **SCP unit files to Aliyun:**
    ```bash
    scp deploy/aliyun/systemd/qdrant-snapshot.service aliyun-vitaclaw:/etc/systemd/system/qdrant-snapshot.service
    scp deploy/aliyun/systemd/qdrant-snapshot.timer aliyun-vitaclaw:/etc/systemd/system/qdrant-snapshot.timer
    ssh aliyun-vitaclaw "chmod 0644 /etc/systemd/system/qdrant-snapshot.{service,timer}"
    ```

    **Confirm script + venv ready:**
    ```bash
    ssh aliyun-vitaclaw "ls /root/OmniGraph-Vault/scripts/qdrant_to_nanovdb.py && venv-aim1/bin/python -c 'import qdrant_client'"
    # Both must succeed.
    ```

    **Enable + dry-run start the service ONCE manually first** (verify it actually works against the EMPTY Qdrant — converter must produce empty vdb_*.json, not crash). NOTE: this first run REPLACES the rollback symlinks created in T6 with regular files (per `os.replace` semantics):
    ```bash
    ssh aliyun-vitaclaw "systemctl daemon-reload && systemctl start qdrant-snapshot.service"
    ssh aliyun-vitaclaw "journalctl -u qdrant-snapshot.service --since '5min ago' | tail -30"
    # Expect: qdrant_snapshot_ok files_written=3 ... (empty Qdrant produces empty data:[] valid JSON; T2 implementation guards `if matrix:` before dim check so empty collection is valid).
    ```

    If dim-guard incorrectly fires on empty collection → halt T8 with HT-7. Re-issue T2 with `if matrix and len(matrix[0]) != embedding_dim: raise ValueError(...)` (guard only when non-empty).

    **Enable timer:**
    ```bash
    ssh aliyun-vitaclaw "systemctl enable qdrant-snapshot.timer && systemctl start qdrant-snapshot.timer"
    ssh aliyun-vitaclaw "systemctl list-timers --all qdrant-snapshot.timer"
    # Expect: NEXT showing within 6h, ACTIVATES showing qdrant-snapshot.service.
    ```

    Note: post-T8, kb-api is on Qdrant with empty collections. mode='mix' queries return FTS5-only / sparse results until T9 reingest converges. Acceptable per RESEARCH §"Re-ingest window strategy".
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "systemctl is-enabled qdrant-snapshot.timer"` returns `enabled`.
    - `ssh aliyun-vitaclaw "systemctl list-timers --all qdrant-snapshot.timer | grep qdrant-snapshot"` shows next-fire ≤ 6 h.
    - `ssh aliyun-vitaclaw "journalctl -u qdrant-snapshot.service --since '15min ago' | grep -c qdrant_snapshot_ok"` ≥ 1.
    - `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json"` shows file (regular file post-converter-run, may be small; empty Qdrant → small JSON).
  </acceptance_criteria>
  <commit_msg>(no commit — Aliyun state mutation only)</commit_msg>
  <halt_triggers>HT-7</halt_triggers>
  <addresses_sc>SC-5, SC-4 (live converter verification)</addresses_sc>
</task>

<wave2_gate>
**Wave 2 close condition (Aliyun deploy gate):** Qdrant `/healthz` 200; override.conf has 5 new lines (1 vector_storage + 4 rerank); kb-api `lightrag_singleton_ready wall_s` ≤ 30 s; qdrant-snapshot.timer enabled; first manual qdrant-snapshot.service run produced 3 vdb_*.json files. **STOP if any condition fails.** Re-ingest (Wave 3) cannot start until this gate is green. (HT-6 N=4 lock-break is NOT part of Wave 2 close — that fires in Wave 4.)
</wave2_gate>

<task id="T9" name="Aliyun: 6-batch re-ingest of 252 articles (3-5 days wall)">
  <wave>3</wave>
  <files>(Aliyun-side state mutation only; uses scripts/qdrant_reingest_252.sh from T3)</files>
  <read_first>
    - scripts/qdrant_reingest_252.sh (T3 artifact)
    - kb/deploy/omnigraph-ingest-services.service.d/override.conf.example (T3 artifact — generalized example for the 3 ingest service drop-ins)
    - .planning/quick/260601-qdrant-research/RESEARCH.md §"Q3 Per-article ingest timing" (113s-708s avg, 8-24h per batch realistic)
    - .planning/phases/v1.1-roadmap/qdrant-migration/RESEARCH.md (252 article candidate pool, sqlite count verified)
  </read_first>
  <action>
    Executor (Aliyun-side):

    **Pre-flight:**
    - Confirm Qdrant collections are empty: `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'from qdrant_client import QdrantClient; c=QdrantClient(url=\"http://127.0.0.1:6333\"); print(c.get_collections())'"`. Empty result is expected; ingest_wechat will create the 3 collections on first upsert.
    - Confirm `OMNIGRAPH_VECTOR_STORAGE=qdrant` is in **all 3 ingest services' env** (Aliyun has `omnigraph-morning-ingest.service` + `omnigraph-afternoon-ingest.service` + `omnigraph-evening-ingest.service`). Use `kb/deploy/omnigraph-ingest-services.service.d/override.conf.example` (T3 artifact) as the source-of-truth shape and append its `Environment=` line to **each of the 3 live drop-in files**. **HT-4 also applies** — read the existing `override.conf` for each service first, halt if any unfamiliar line is present beyond what STATE-v1.1.md row B documents, surface diff to orchestrator. After each append: `systemctl daemon-reload`. Do not restart the ingest service yet (the next scheduled fire will pick up the env).
    - Confirm WeChat `CDP_URL` reachable.

    **Run wrapper (long-running; use tmux or systemd-run):**
    ```bash
    ssh aliyun-vitaclaw "tmux new-session -d -s qdrant-reingest 'bash /root/OmniGraph-Vault/scripts/qdrant_reingest_252.sh 2>&1 | tee /root/.hermes/qdrant-reingest-full.log'"
    ```

    **Wrapper semantics (D9 fix — count-driven early exit):** wrapper runs at most 6 batches × 50 articles, but BEFORE each batch it queries `qdrant_client.count("lightrag_vdb_chunks").count`. If count ≥ 252, it exits immediately with `qdrant_reingest_done batches=${i} chunks=${count} (early exit, target met)`. Robust against article-count drift between plan time (252) and execute time (could be 247 or 256). Final batch will naturally only ingest the remainder.

    **Monitor (every few hours):**
    ```bash
    ssh aliyun-vitaclaw "tmux capture-pane -p -t qdrant-reingest | tail -50"
    ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'from qdrant_client import QdrantClient; c=QdrantClient(url=\"http://127.0.0.1:6333\"); print(\"chunks:\", c.count(\"lightrag_vdb_chunks\").count)'"
    ```

    **HT-8 watch:** if any single batch's average article wall > 1800 s (3× canonical median), halt and investigate. The wrapper script already pipes per-article batch_timeout_metrics; the HT-8 check is a manual review of those logs.

    **Cooldown between batches** (already handled by wrapper; default `BATCH_COOLDOWN_S=3600`). User can shorten or lengthen per WeChat-side observation.

    **Closure:**
    - `ssh aliyun-vitaclaw "cat /root/.hermes/qdrant-reingest-full.log | tail -10"` shows `qdrant_reingest_done` (batches count may be 5 or 6 depending on early-exit gate).
    - Post-batch: `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'from qdrant_client import QdrantClient; c=QdrantClient(url=\"http://127.0.0.1:6333\"); print(\"chunks:\", c.count(\"lightrag_vdb_chunks\").count)'"` returns count ≥ 252.

    Note: during this 3-5 day window, Aliyun kb-api serves degraded (FTS5-fallback) results for entity-rich queries. Hermes + Databricks consume `vdb_archive_*.json` (last good pre-cutover snapshot) until first post-T8 snapshot lands (≤6h after T8). Per user constraint, this is acceptable.
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'from qdrant_client import QdrantClient; c=QdrantClient(url=\"http://127.0.0.1:6333\"); print(c.count(\"lightrag_vdb_chunks\").count)'"` ≥ 252.
    - `ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db 'SELECT COUNT(*) FROM ingestions WHERE last_ingested_at >= strftime(\"%s\", \"now\", \"-7 days\")'"` ≥ 252.
    - `ssh aliyun-vitaclaw "grep -c qdrant_reingest_halt /root/.hermes/qdrant-reingest-full.log"` == 0 (no halt markers).
    - `ssh aliyun-vitaclaw "free -h"` shows kb-api + ingest combined RSS ≤ 4 GB during a batch (was 10.9 GB OOM pre-Qdrant).
    - `ssh aliyun-vitaclaw "dmesg | grep -i 'killed process'"` shows no new OOM-kills since T7.
    - `ssh aliyun-vitaclaw "for s in morning afternoon evening; do grep OMNIGRAPH_VECTOR_STORAGE /etc/systemd/system/omnigraph-\${s}-ingest.service.d/override.conf; done | grep -c qdrant"` == 3 (env propagated to all 3 ingest service drop-ins).
  </acceptance_criteria>
  <commit_msg>(no commit — Aliyun state mutation only)</commit_msg>
  <halt_triggers>HT-8</halt_triggers>
  <addresses_sc>SC-3</addresses_sc>
</task>

<wave3_gate>
**Wave 3 close condition:** Qdrant collections populated (chunks ≥ 252); ≥ 1 successful qdrant-snapshot.service run produced fresh vdb_*.json since reingest completed; no OOM-kills in dmesg over the reingest window. Move to Wave 4.
</wave3_gate>

<task id="T10" name="HT-6 N=4 lock-break test against deployed Aliyun kb-api">
  <wave>4</wave>
  <files>tests/integration/test_aliyun_n4_lock_break.py (run only — no edits)</files>
  <read_first>
    - tests/integration/test_aliyun_n4_lock_break.py (T4 artifact)
    - .planning/phases/v1.1-roadmap/P5/P5-VERIFICATION.md (reference: prior Branch A pattern)
  </read_first>
  <action>
    Executor (laptop or Aliyun-side):

    **Open SSH tunnel to Aliyun kb-api** (from local laptop):
    ```bash
    ssh -N -L 18766:127.0.0.1:8766 aliyun-vitaclaw &
    TUNNEL_PID=$!
    ```

    **Run the test:**
    ```bash
    ALIYUN_KB_API_URL=http://127.0.0.1:18766 \
      pytest tests/integration/test_aliyun_n4_lock_break.py -x -v --tb=short \
      2>&1 | tee .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break-pytest.log
    ```

    **Capture journalctl evidence concurrently** (in a second shell, started just before pytest):
    ```bash
    ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '2min ago' -f" \
      > .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break-journal.log &
    JOURNAL_PID=$!
    # … run pytest …
    kill $JOURNAL_PID
    ```

    **Verify HT-6:**
    - pytest exit 0 (4 topic-distinct responses, no crosstalk).
    - journal evidence shows 4× `lightrag_lock_acquired` and 4× `lightrag_lock_released` markers, no overlap (each release precedes the next acquire — strict serialization is the lock contract).

    If HT-6 fires (crosstalk OR overlap detected), halt phase; do NOT mark SC-8.

    Close SSH tunnel:
    ```bash
    kill $TUNNEL_PID
    ```
  </action>
  <acceptance_criteria>
    - `pytest tests/integration/test_aliyun_n4_lock_break.py -x` exits 0.
    - `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break.log` exists with 4 entries (one per request).
    - `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/n4-lock-break-journal.log` shows ≥ 4 `lightrag_lock_acquired` and ≥ 4 `lightrag_lock_released`.
    - Manual review confirms zero acquire/release overlap (each release timestamp < next acquire timestamp).
  </acceptance_criteria>
  <commit_msg>docs(qdrant-migration): N=4 lock-break evidence captured</commit_msg>
  <halt_triggers>HT-6</halt_triggers>
  <addresses_sc>SC-8</addresses_sc>
</task>

<task id="T11" name="Verify SC-9 hydrate ≤30s × 3 restarts + SC-12 dual-station rerank parity">
  <wave>4</wave>
  <files>(Aliyun-side observation; no repo file change beyond evidence capture)</files>
  <read_first>
    - .planning/phases/v1.1-roadmap/STATE-v1.1.md row P2-3-perf-fix-A (Databricks Haiku rerank already verified)
    - kb/api.py:lifespan (singleton ready marker)
  </read_first>
  <action>
    Executor:

    **3 consecutive Aliyun restarts (SC-9):**
    ```bash
    for i in 1 2 3; do
      ssh aliyun-vitaclaw "systemctl restart kb-api.service"
      sleep 60  # allow hydrate
      ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '90s ago' | grep -oE 'lightrag_singleton_ready wall_s=[0-9.]+'"
    done > .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/hydrate-3-restarts.log
    ```
    Confirm all 3 readings ≤ 30 s.

    **Dual-station rerank parity smoke (SC-12):**

    Aliyun (Vertex Gemini path):
    ```bash
    ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8766/api/synthesize \
      -H 'Content-Type: application/json' \
      -d '{\"query\":\"What is LightRAG hybrid mode?\", \"mode\":\"long_form\"}' " > /tmp/aliyun-resp.json
    ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '2min ago' | grep llm_rerank_dispatch" \
      > .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/aliyun-rerank-evidence.log
    # Expect: provider=vertex_gemini
    ```

    Databricks (Haiku path) — use existing `make logs` + curl through SSO browser console (per scripts/sync_to_databricks.sh Step 10 smoke 4 already documented):
    ```bash
    # User runs Step 10 smoke 4 in browser console; capture logz output via:
    # databricks-deploy/scripts/tail_app_logs.py --since 5min | grep llm_rerank_dispatch
    # > .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/databricks-rerank-evidence.log
    # Expect: provider=databricks_claude_haiku
    ```

    HC-6 closes when both files have non-empty matching markers and both responses are non-empty mode='mix' answers.
  </action>
  <acceptance_criteria>
    - `cat .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/hydrate-3-restarts.log | grep -oE 'wall_s=[0-9.]+' | awk -F= '{ if ($2 > 30) exit 1 }'` exits 0 (all 3 ≤ 30 s).
    - `grep -c 'provider=vertex_gemini' .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/aliyun-rerank-evidence.log` ≥ 1.
    - `grep -c 'provider=databricks_claude_haiku' .planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/databricks-rerank-evidence.log` ≥ 1.
  </acceptance_criteria>
  <commit_msg>docs(qdrant-migration): SC-9 hydrate + SC-12 dual-station rerank evidence</commit_msg>
  <halt_triggers>HT-5 (re-fire if any of 3 restarts > 60 s)</halt_triggers>
  <addresses_sc>SC-9, SC-12</addresses_sc>
</task>

<task id="T12" name="Databricks deploy gate — first vdb_*.json snapshot lands; long_form smoke">
  <wave>4</wave>
  <files>(Databricks-side observation; uses scripts/sync_to_databricks.sh existing pipeline)</files>
  <read_first>
    - scripts/sync_to_databricks.sh (Step 3 covers lightrag_storage tarball)
    - HC-6 + HC-7 invariants
    - PRINCIPLE #9 (Databricks deploy can be sync-only — no Pass 0 SSG bake; this phase touches NO files under kb/static/ or kb/templates/)
  </read_first>
  <action>
    Executor (laptop / orchestrator-driven):

    **Wait for first post-T8 6-h converter run (≤ 6 h after Wave 3 close)**:
    ```bash
    ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json | grep -v archive"
    # Expect 3 regular files dated post-T8 (after empty-Qdrant first snapshot OR after first reingest-converged snapshot). NOT symlinks anymore — converter's os.replace replaced T6's symlinks with regular files on first run.
    ```

    **Run the existing sync script (no functional change — sync-only, NO Pass 0 SSG bake per PRINCIPLE #9):**
    ```bash
    bash scripts/sync_to_databricks.sh --yes
    # Step 3 tarball includes the new vdb_*.json. Steps 6-9 push to UC Volume + redeploy.
    ```

    **Verify UC Volume mtime updated:**
    ```bash
    databricks --profile dev fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/vdb_chunks.json -o json
    # Expect modification_time post-Wave 3 close.
    ```

    **Smoke /api/synthesize on Databricks** (browser console via SSO):
    ```javascript
    // Smoke 4 from sync_to_databricks.sh Step 10:
    fetch('https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/api/synthesize', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:'What is LightRAG hybrid mode?', mode:'long_form'})
    }).then(r => r.json()).then(j => { /* poll job_id */ });
    ```

    **Capture evidence:**
    - Job result has non-empty `result.response` markdown (≥ 200 chars).
    - `make logs` (or `databricks-deploy/scripts/tail_app_logs.py`) shows `mode=mix` + `llm_rerank_dispatch provider=databricks_claude_haiku` since the smoke fired.
    - Save the response + log to `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/databricks-post-cutover-smoke.log`.

    **HT-9 trigger:** if first sync after T8 fails OR Databricks vdb_*.json mtime not advancing within 24 h post-cutover, halt T12 and trace.
  </action>
  <acceptance_criteria>
    - `databricks --profile dev fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/vdb_chunks.json` shows mtime within last 24 h.
    - `.planning/phases/v1.1-roadmap/qdrant-migration/aliyun-evidence/databricks-post-cutover-smoke.log` shows status=done + non-empty markdown.
    - Databricks logz shows `provider=databricks_claude_haiku` for the smoke job.
  </acceptance_criteria>
  <commit_msg>docs(qdrant-migration): Databricks deploy gate evidence captured</commit_msg>
  <halt_triggers>HT-9</halt_triggers>
  <addresses_sc>SC-6, SC-11</addresses_sc>
</task>

<wave4_gate>
**Wave 4 close condition (final phase close):** All 12 SCs verified with cited evidence in qdrant-migration-VERIFICATION.md. Aliyun kb-api running on Qdrant for ≥ 48 h with no OOM-kill. Databricks long_form sub-65s budget retained. ISSUES.md updated by orchestrator: #25 → RESOLVED; #26 → RESOLVED (folded); #27 → RESOLVED; #22 → RESOLVED (B reconcile complete). PR #4 closed-as-superseded.
</wave4_gate>

## Wave Grouping

| Wave | Tasks | Gate | Parallel? |
|------|-------|------|-----------|
| 1 (Code & Local Tests) | T1, T2, T3, T4 | All four commits land; unit tests green | T1+T2+T3+T4 partially parallel (T1 and T2 touch disjoint files; T3 and T4 are pure new-file creation) |
| 2 (Aliyun Provisioning) | T5, T6, T7, T8 | All Aliyun mutations succeed; HT-5 hydrate ≤ 30s | Sequential — T5 → T6 → T7 → T8 (each depends on previous) |
| 3 (Re-ingest, Long Wall) | T9 | Qdrant chunks ≥ 252; no OOM-kills; reingest_done marker | Single-threaded by WeChat throttle |
| 4 (Verify & Close) | T10, T11, T12 | All 12 SCs cite evidence; ISSUES updates pending orchestrator | T10+T11 parallel; T12 after first post-T8 sync run (≤24h) |

## Halt Triggers

| ID | Trigger | Action |
|----|---------|--------|
| HT-1 | Aliyun pre-flight: Qdrant docker not started OR `qdrant-client` not in venv-aim1 OR SA JSON / Vertex env missing in `/root/.hermes/.env`. | Halt before T5. Surface to orchestrator. |
| HT-2 | `/var/lib/` free < 5 GB before Qdrant install. | Halt T5. |
| HT-3 | T1 modifies `kg_synthesize.py:221-226` lock pattern in any way other than reading env to choose vector_storage. | Halt; do not commit. |
| HT-4 | Live Aliyun `override.conf` has unexpected lines beyond the 6 known (perf-fix-B baseline) when T7 begins, OR any of the 3 ingest service drop-ins has unexpected lines when T9 appends `OMNIGRAPH_VECTOR_STORAGE=qdrant`. | Halt; surface diff to orchestrator before mutating. |
| HT-5 | Post-T7 first restart `lightrag_singleton_ready wall_s` > 60 s (or > 30 s on any of T11's 3 consecutive checks). | Halt; do not mark SC-9. |
| HT-6 | T10 N=4 lock-break test shows topic crosstalk OR `lightrag_lock_acquired`/`released` overlap. | Halt T10; revisit P5 contract. |
| HT-7 | `qdrant_to_nanovdb.py` produces vdb_*.json with `embedding_dim != 3072` OR `len(data) > 0 AND len(matrix[0]) != embedding_dim`. | Halt T8; fix converter. |
| HT-8 | During T9, per-article DeepSeek wall_s tail > 1800 s (3× canonical median 300 s × 6). | Halt re-ingest; investigate before continuing. |
| HT-9 | First post-cutover `sync_to_databricks.sh` Step 3 fails OR Databricks vdb_*.json mtime not advancing within 24 h. | Halt T12; trace. |
| HT-10 | Any plan task touches Hermes-side code, env, or runtime. | Halt; HC-7 violation. **(GLOBAL — applies to every task; see prefix callout above the task list.)** |

## Rollback Plan (4 levels, cheapest → most invasive)

| Level | Action | Wall | When to use |
|-------|--------|------|-------------|
| **L1 (env-flag escape, ~30 s)** | (D7 fix — pure env-flip + restart, no 1.85 GB cp.) `ssh aliyun-vitaclaw "sed -i 's/OMNIGRAPH_VECTOR_STORAGE=qdrant/OMNIGRAPH_VECTOR_STORAGE=nanovectordb/' /etc/systemd/system/kb-api.service.d/override.conf && systemctl daemon-reload && systemctl restart kb-api.service"`. Pre-converter-first-run: T6's symlinks (`vdb_*.json → vdb_archive_*.json`) still resolve naturally, kb-api reads archive content. Post-converter-first-run: symlinks have been replaced by regular Qdrant-derived files; before flipping the env, recreate symlinks: `ssh aliyun-vitaclaw "cd /root/.hermes/omonigraph-vault/lightrag_storage && for f in vdb_archive_*.json; do ln -sf \"$f\" \"${f/_archive_/_}\"; done"` (3 lines, milliseconds). | ~30 s | SC-9 fails post-cutover; SC-12 fails; any kb-api hydrate / query regression appears acutely. |
| **L2 (partial revert, 5 min)** | L1 + disable `qdrant-snapshot.timer`; set `OMNIGRAPH_VECTOR_STORAGE=nanovectordb` in all 3 `omnigraph-*-ingest.service.d/override.conf`; promote archives to canonical names: `ssh aliyun-vitaclaw "cd /root/.hermes/omonigraph-vault/lightrag_storage && rm -f vdb_chunks.json vdb_entities.json vdb_relationships.json && for f in vdb_archive_*.json; do mv \"$f\" \"${f/_archive_/_}\"; done"` (rename rather than copy — fast, deterministic). | 5 min | Converter is corrupting snapshots; ingest_wechat is OOM-ing on Qdrant path (unexpected). |
| **L3 (revert code, 10 min)** | L2 + `git revert <T1-T2-T3 commit shas>` on main; `databricks sync` to Aliyun (`cd /root/OmniGraph-Vault && git pull`); `systemctl restart kb-api.service && systemctl restart omnigraph-*-ingest.service`. Qdrant docker stays up but unused. | 10 min | Code-level bug found post-deploy that env flag can't bypass. |
| **L4 (full revert, 20 min)** | L3 + `ssh aliyun-vitaclaw "docker stop qdrant && docker rm qdrant && rm -rf /var/lib/qdrant"`; `systemctl disable --now qdrant-snapshot.timer && rm /etc/systemd/system/qdrant-snapshot.{service,timer} && systemctl daemon-reload`; restore `vdb_archive_*.json` → `vdb_*.json` (rename, not copy). Final check: `free -h` shows kb-api back at ~2.4 GB RSS (pre-cutover baseline). | 20 min | Migration is unsalvageable; full rollback to pre-phase state. |

## Re-ingest 6-Batch Strategy (T9 detail)

- **Pool:** 252 articles (238 `layer2_verdict='ok'` + 14 `failed` with `body NOT NULL`), measured 2026-06-01 via sqlite.
- **Throttle floor:** WeChat 50 articles per batch + cooldown (`ingest_wechat.py` enforces).
- **Batch math (D9 fix — count-driven, not arithmetic):** wrapper runs at most 6 batches × 50 articles. Before each batch it queries `qdrant_client.count("lightrag_vdb_chunks").count`; if count ≥ 252 it exits early. The 6th batch (when it runs) ingests only the remainder (252 - 5×50 = 2 articles minimum); WeChat throttle tolerates batches < 50 silently. Robust against article-count drift between plan time (252) and execute time (could be 247 or 256).
- **Total wall-clock:** 113 s (best) – 708 s (worst observed) per article; median 300 s. Total ≈ 8 – 24 h compute; spread over 3 – 5 calendar days with 1 h cooldown.
- **Pre-batch state:** `vdb_archive_*.json` exists + symlinks `vdb_*.json → vdb_archive_*.json` (T6); Qdrant collections empty (T5+T6+T7); ingest_wechat writes ONLY to Qdrant (env split from T1; HT-3 invariant ensures no nano-vectordb writes mixed in).
- **Per-batch monitoring:** wrapper script logs Qdrant collection count after each batch via `qdrant_client.count(...)`.
- **Mid-window read traffic:** Aliyun kb-api queries Qdrant (returns FTS5-only / sparse results until convergence — acceptable per user constraint).
- **Cross-station read traffic:**
  - Hermes pulls `vdb_archive_*.json` via existing operator-driven rsync (Hermes RO until 2026-06-22; T6 archive files remain canonical for Hermes during this window).
  - Databricks pulls fresh `vdb_*.json` from converter cron once collections start populating (≤ 6 h after T8 enables timer).
- **vdb_archive deferred-delete:** NOT before 2026-06-22. README.qdrant-migration.txt (in `omonigraph-vault/` PARENT dir, NOT inside lightrag_storage/) + ISSUES.md follow-up reminder enforce this.

## Deploy Gates

### Wave 2 close (proceeds to Wave 3)

(D10 fix — Wave-2 close items only; HT-6 N=4 lock-break is NOT in this list, see Wave 4.)

- [ ] Qdrant `docker ps` shows `Up`; `curl 127.0.0.1:6333/healthz` returns 200.
- [ ] `override.conf` (kb-api) contains 5 new Environment lines (1 vector_storage + 4 rerank).
- [ ] `lightrag_singleton_ready wall_s` ≤ 30 s on first restart.
- [ ] `qdrant-snapshot.timer` enabled; first manual qdrant-snapshot.service run produced 3 vdb_*.json files (regular files, having replaced T6's rollback symlinks).

### Wave 4 close (phase done)

(D10 fix — verification gates that close the phase; cite evidence in VERIFICATION.md.)

- [ ] HT-6 N=4 lock-break passes on Aliyun (SC-8).
- [ ] SC-9 hydrate ≤ 30 s verified across 3 consecutive restarts.
- [ ] SC-12 dual-station rerank parity confirmed (Aliyun=vertex_gemini, Databricks=databricks_claude_haiku, both with non-empty mode='mix' answers).
- [ ] SC-11 Databricks deploy gate: first vdb_*.json mtime advanced within 24h post-cutover; long_form smoke returns valid mode='mix' answer.
- [ ] **PRINCIPLE #9 explicit:** this phase touches NO files under `kb/static/` or `kb/templates/`. Therefore Databricks deploy is **sync-only (Pass 1 + Pass 2 + Pass 3)** — Pass 0 SSG bake is **NOT required**. Verify via `git diff <pre-phase>..HEAD --name-only | grep -E 'kb/(static|templates)/'` returns empty.

### PR #4 disposition

PR #4 (`ops/qdrant-migration` branch) only patches `ingest_wechat.py:392`. Wave 1 commits T1 SUPERSEDE PR #4's narrower change (T1 covers all 3 sites: ingest_wechat + kb/api + kg_synthesize, env-driven). PR #4 should be **closed-as-superseded** post-Wave-1 with a comment referencing the T1 commit SHA.

## Final Phase Close Criteria

- [ ] All 12 SCs verified with cited evidence in `qdrant-migration-VERIFICATION.md`.
- [ ] All Wave 1-4 task commits land on `main` (no `--amend`, no `--force`, no `reset --hard`).
- [ ] Aliyun kb-api running on Qdrant for ≥ 48 h with no OOM-kill in `dmesg`.
- [ ] Databricks long_form sub-65s budget retained (perf-fix-A SC#2 floor).
- [ ] HT-6 N=4 lock-break passes on Aliyun (P5 contract preserved).
- [ ] ISSUES.md updated by orchestrator: #25 → RESOLVED with this commit chain; #26 → RESOLVED (folded); #27 → RESOLVED (structural fix landed); #22 → RESOLVED (B reconcile complete via this phase).
- [ ] STATE-v1.1.md row added or updated for `qdrant-migration` showing CLOSED + VERIFICATION.md path.
- [ ] PR #4 closed-as-superseded with commit reference.
- [ ] Follow-up ISSUES row filed (orchestrator-curated): "vdb_archive cleanup on 2026-06-22 — delete `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_archive_*.json` after Hermes unfreeze".

## Follow-up Issues (planner-surfaced, for orchestrator transcription)

1. **vdb_archive cleanup on 2026-06-22.** SC-10 enforces deferred-delete; orchestrator MUST file an ISSUES.md row with target date 2026-06-22 to delete the 3 archive files (~1.85 GB recovery) post Hermes RO unfreeze.
2. **LoC ceiling at +463 (above 400 target).** **Do NOT apply downscope to `tests/integration/test_aliyun_n4_lock_break.py` during this phase.** The ~50 LoC budget is justified by HT-6 evidence-capture requirements (per-request job_id, topic, wall_s, response excerpt — all needed to discriminate crosstalk from latency in post-mortem). Reconsider only as a post-phase tightening exercise after Wave 4 close, AND only if a concrete refactor preserves all 4 evidence fields.
3. **Qdrant-snapshot timer first run on EMPTY Qdrant.** T8 includes a guard against dim-mismatch on empty collections (T2 implementation must `if matrix:` before dim check). T2 acceptance test now includes an empty-collection case explicitly. If T2 ships without that guard, T8 will halt with HT-7 — file the dim-guard fix as a follow-up Quick if it surfaces.
4. **Databricks fingerprint sync caveat.** `databricks_sync_full_false_positive` memory entry: `databricks sync --full` may report OK without pushing when fingerprint cache is stale. Wave 4 T12 verifies UC Volume mtime — if mtime stale, fall back to `workspace import --overwrite`.
5. **Ingest service env propagation (D13a generalized).** T9 requires `OMNIGRAPH_VECTOR_STORAGE=qdrant` in 3 ingest service overrides (`omnigraph-morning-ingest.service.d/override.conf` + afternoon + evening). T3 ships a single generalized example file `kb/deploy/omnigraph-ingest-services.service.d/override.conf.example` as the source-of-truth shape; execute-phase MUST apply it to all 3 live drop-ins, applying HT-4 each time.
6. **L1 rollback symlink invalidation post-converter (D7 fix).** Pre-T8 first run, T6's symlinks (`vdb_*.json → vdb_archive_*.json`) make L1 rollback a pure env-flip + restart. After T8's first converter run, `os.replace` replaces the symlinks with regular Qdrant-derived files. From that point onward, L1 rollback adds 3 `ln -sf` lines (still milliseconds, still ≤30s total). Documented in L1 rollback row above; verify in execute-phase that the rollback playbook is paged before any rollback decision.
