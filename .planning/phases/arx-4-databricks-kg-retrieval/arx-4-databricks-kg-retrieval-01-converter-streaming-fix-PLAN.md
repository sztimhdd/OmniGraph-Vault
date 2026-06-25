---
phase: arx-4-databricks-kg-retrieval
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/qdrant_to_nanovdb.py
  - tests/unit/test_qdrant_to_nanovdb.py
autonomous: false
requirements: [ARX4-41]
user_setup: []

must_haves:
  truths:
    - "The converter exports the real 82582-point relationships collection on Aliyun WITHOUT an oom-kill (process exits 0)."
    - "Peak RSS during the relationships export is bounded and demonstrably independent of point-count growth (measured, not assumed)."
    - "vdb_relationships.json on Aliyun is no longer the 49-byte placeholder — it carries the real matrix + data rows."
    - "qdrant-snapshot.timer is re-enabled (enabled + active) so on-disk vdb stays fresh going forward — this is the #41 closure marker."
  artifacts:
    - path: "scripts/qdrant_to_nanovdb.py"
      provides: "Memory-bounded export_collection_to_nanovdb (streaming or chunked matrix build) preserving the atomic .tmp+os.replace write and the nano_vectordb single-base64-blob on-disk schema"
      contains: "os.replace"
    - path: "tests/unit/test_qdrant_to_nanovdb.py"
      provides: "Behavior-anchor test pinning the on-disk schema roundtrips through nano_vectordb.load_storage after the streaming refactor (byte-identical matrix vs the old full-accumulation path on a fixture collection)"
      contains: "load_storage"
  key_links:
    - from: "scripts/qdrant_to_nanovdb.py:export_collection_to_nanovdb"
      to: "nano_vectordb on-disk format"
      via: "array_to_buffer_string single base64 matrix string"
      pattern: "array_to_buffer_string"
    - from: "qdrant-snapshot.timer"
      to: "scripts/qdrant_to_nanovdb.py"
      via: "systemd one-shot service ExecStart"
      pattern: "qdrant-snapshot"
---

<objective>
Fix ISSUES #41: the `scripts/qdrant_to_nanovdb.py` converter OOM-kills on Aliyun (2-core/14G) when exporting the real 82582-point `relationships` collection, because `export_collection_to_nanovdb` accumulates ALL rows + ALL float32 vectors in memory, then builds one giant `np.array(vectors)` + one `array_to_buffer_string` before a single `json.dump`. This converter is the ONLY thing that regenerates Aliyun's on-disk `vdb_*.json` from its fresh Qdrant — it is dead (timer disabled since 2026-06-05), which is why Aliyun's on-disk `vdb_relationships.json` is a 49-byte placeholder and `vdb_chunks.json` is stale (June 6). Plan 03 (#64 regen→sync→re-hydrate) CANNOT run until this converter is non-OOM.

Purpose: unblock the #64 sync chain by restoring the Qdrant→on-disk-vdb bridge under a bounded memory ceiling, validated at REAL scale on Aliyun prod, then re-enable the 6h timer so on-disk vdb never goes stale again (closes the root cause, not just one sync).

Output: a memory-bounded converter (validated against the 82582-point relationships collection), a behavior-anchor test that the on-disk schema still loads via `nano_vectordb.load_storage`, real (non-placeholder) `vdb_*.json` files on Aliyun, and `qdrant-snapshot.timer` re-enabled.

ZERO new features — this repairs an existing, currently-dead script.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-RESEARCH.md

<interfaces>
<!-- The nano_vectordb on-disk format authority (venv/Lib/site-packages/nano_vectordb/dbs.py). -->
<!-- LOAD side (the consumer Databricks/Hermes use) reads the matrix as ONE base64 string and reshapes: -->

```python
# dbs.py:27-28 — encode (what the converter calls)
def array_to_buffer_string(array: np.ndarray) -> str:
    return base64.b64encode(array.tobytes()).decode()

# dbs.py:31-44 — decode (what load_storage does on the consumer side)
def buffer_string_to_array(base64_str: str, dtype=Float) -> np.ndarray:
    return np.frombuffer(base64.b64decode(base64_str), dtype=dtype)

def load_storage(file_name):
    ...
    data["matrix"] = buffer_string_to_array(data["matrix"]).reshape(-1, data["embedding_dim"])
    return data   # Float = np.float32
```

On-disk schema (the single-blob constraint that bounds the streaming approach):
```json
{ "embedding_dim": 3072, "data": [ {"__id__": "...", "__created_at__": 0, ...meta}, ... ], "matrix": "<base64 of float32 row-major bytes>" }
```
KEY FACT: `array_to_buffer_string` is just `base64(array.tobytes())`. The base64 of a concatenation does NOT equal the concatenation of base64s in general (base64 operates on 3-byte groups), so you cannot naively concatenate per-batch base64 strings. The float32 raw bytes for 82582×3072 ≈ 82582*3072*4 ≈ 1.01 GB; base64 of that ≈ 1.35 GB string. The OOM is NOT primarily the b64 string — it is holding the Python `list[list[float]]` of 82582×3072 floats (each float is a boxed Python object in the list-of-lists → multi-GB) PLUS `np.array(vectors)` (≈1 GB) simultaneously. The fix removes the `list[list[float]]` intermediary by streaming raw float32 bytes into one bytearray.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Refactor export_collection_to_nanovdb to a memory-bounded matrix build (kill the list[list[float]] + np.array(vectors) double-hold)</name>
  <files>scripts/qdrant_to_nanovdb.py</files>
  <read_first>
    - scripts/qdrant_to_nanovdb.py (the WHOLE file — esp. :92 export_collection_to_nanovdb, :121-122 the `rows`/`vectors` lists, :143 `vectors.append(list(vec))`, :167-171 `np.array(vectors)` + `array_to_buffer_string`, :182-185 atomic write — PRESERVE it, :238-255 the empty-collection branch in main())
    - venv/Lib/site-packages/nano_vectordb/dbs.py (:27-44 array_to_buffer_string / buffer_string_to_array / load_storage — the single-base64-blob contract this MUST keep producing)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md (the #41 section + the "Constraint the planner MUST resolve" paragraph — single-blob bounds the approach)
  </read_first>
  <behavior>
    - Test 1 (schema roundtrip preserved): given a small in-memory fixture collection of N rows × dim D vectors, the refactored export writes a file that `nano_vectordb.dbs.load_storage(path)` loads to `matrix.shape == (N, D)` AND `data` length == N AND the matrix float32 values are byte-identical to the pre-refactor full-accumulation output (compare base64 strings — they MUST match exactly; the on-disk bytes are a contract).
    - Test 2 (empty collection still valid): N=0 produces `{"data": [], "matrix": ""}` that load_storage reshapes to `(0, D)` without error (preserve current :169-170 behavior).
    - Test 3 (dim-mismatch still raises): a fixture where observed dim != embedding_dim still raises ValueError with the `qdrant_snapshot_dim_mismatch` message (preserve :148-153 HT-7 guard).
    - Test 4 (count roundtrip still raises on mismatch): preserve the `qdrant_snapshot_roundtrip_mismatch` RuntimeError (:156-161) — count check must survive the refactor.
  </behavior>
  <action>
    Refactor `export_collection_to_nanovdb` (scripts/qdrant_to_nanovdb.py:92) to bound peak RSS by eliminating the `list[list[float]]` → `np.array` double materialization. The on-disk format REQUIRES a single base64 string (`load_storage` reshapes one blob — see interfaces above), so the matrix bytes must exist contiguously at encode time; the win is NOT holding them twice and NOT as Python float objects.

    Concrete algorithm (streaming accumulation into ONE float32 byte buffer):
    1. Single scroll pass: keep `rows: list[dict]` (the metadata rows are small — 82582 dicts of ~5 short fields ≈ low-hundreds-MB, acceptable; the killer is the vectors). For the vectors, accumulate directly into a Python `bytearray` (`buf`) by appending `np.asarray(vec, dtype=np.float32).tobytes()` per point — this is raw bytes, NOT boxed Python float objects, so it is ≈ the final 1.0 GB ONCE (no list-of-lists, no separate np.array copy).
    2. On the first vector, capture `dim_observed = len(vec)`; keep the dim-mismatch ValueError guard (:148-153) by checking each point's `len(vec) == embedding_dim` as you append (raise on first mismatch — preserves HT-7, avoids a second pass).
    3. After the scroll loop, keep the Qdrant count roundtrip check (:156-161, `qdrant_count != len(rows)` → RuntimeError).
    4. Build the matrix base64 from the bytearray in ONE call: `matrix_b64 = base64.b64encode(bytes(buf)).decode()` (this is exactly what `array_to_buffer_string` does — `import base64` and inline it, OR call `array_to_buffer_string(np.frombuffer(buf, dtype=Float).reshape(-1, embedding_dim))`; the frombuffer is a zero-copy view so it does NOT double memory). Prefer the direct `base64.b64encode(bytes(buf))` to avoid even the frombuffer reshape allocation — document inline that it is byte-identical to `array_to_buffer_string`.
    5. Empty case (no vectors): `matrix_b64 = ""` (base64 of empty bytes) — matches current :169-171 empty behavior (`array_to_buffer_string(np.zeros((0,dim)))` == "").
    6. PRESERVE the atomic write verbatim (:182-185 `.tmp` + `os.replace`) and the return-metrics dict + logger line (:188-200).

    Add a module-level note comment above the function: peak RSS ≈ (one float32 byte buffer == points×dim×4 bytes) + (rows metadata list) + (transient base64 string at the single encode) — bounded, no list-of-lists, no np.array copy. For relationships (82582×3072) that is ≈ 1.0 GB buffer + ≈1.35 GB transient b64 string ≈ ~2.4 GB peak, well under the 14G box. (If real-scale validation in Task 3 shows this still trips the systemd MemoryMax, fall back to documenting a raised MemoryMax ceiling per CONTEXT option (b) — but the buffer approach should clear it; do NOT pre-emptively raise MemoryMax.)

    Channel: this is a LOCAL repo code edit (Bash/Edit/Read) — no SSH, no Databricks. Match existing PEP8 + type hints + the existing logging style.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "list\[list\[float\]\]" scripts/qdrant_to_nanovdb.py` returns NOTHING (the `vectors: list[list[float]]` intermediary at :122 is gone).
    - `grep -n "np.array(vectors)" scripts/qdrant_to_nanovdb.py` returns NOTHING (the full-array copy at :168 is gone).
    - `grep -nE "bytearray|b64encode|frombuffer" scripts/qdrant_to_nanovdb.py` shows the streaming byte-buffer build.
    - `grep -n "os.replace" scripts/qdrant_to_nanovdb.py` STILL present (atomic write preserved).
    - `grep -nE "qdrant_snapshot_dim_mismatch|qdrant_snapshot_roundtrip_mismatch" scripts/qdrant_to_nanovdb.py` BOTH still present (HT-7 + count guards preserved).
    - `venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v` → all tests pass, INCLUDING the new byte-identical-matrix roundtrip test (Test 1) proving the on-disk bytes match the pre-refactor output.
  </acceptance_criteria>
  <done>The converter builds the matrix from a single contiguous float32 byte buffer (no list-of-lists, no np.array copy), the atomic write + both validation guards survive, and a behavior-anchor test proves the on-disk schema is byte-identical to the old path and loads via nano_vectordb.load_storage.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Behavior-anchor test — pin the on-disk schema + memory shape via in-memory Qdrant fixture</name>
  <files>tests/unit/test_qdrant_to_nanovdb.py</files>
  <read_first>
    - tests/unit/test_qdrant_to_nanovdb.py (if it exists — extend it; otherwise create it next to sibling converter tests)
    - scripts/qdrant_to_nanovdb.py (the refactored export_collection_to_nanovdb + main() + META_FIELDS_BY_NAMESPACE :52-56 + NAMESPACE_TO_QDRANT_COLLECTION :64-68)
    - venv/Lib/site-packages/nano_vectordb/dbs.py (:35-44 load_storage — the assertion target)
    - CLAUDE.md "Behavior-Anchor Harness" project discipline section (pin observable post-conditions, not call shape)
  </read_first>
  <behavior>
    - Test (roundtrip via real load_storage): seed a `QdrantClient(":memory:")` collection with K points of dim D (D small, e.g. 8, to keep it fast) carrying the relationships meta_fields (`src_id, tgt_id, source_id, content, file_path`); run export to a tmp_path; assert `nano_vectordb.dbs.load_storage(out)["matrix"].shape == (K, D)`, `len(loaded["data"]) == K`, and each row has `__id__` + `__created_at__` + the 5 meta_fields (workspace_id dropped, no `__vector__`).
    - Test (byte-identity): compute the expected base64 with the reference path (`array_to_buffer_string(np.array(known_vectors, dtype=np.float32))`) and assert the file's `"matrix"` string equals it EXACTLY — locks the on-disk bytes contract so a future refactor can't silently corrupt consumers.
    - Test (empty collection): export a non-existent / empty collection writes the valid-empty JSON (mirrors main() :238-255 skip-and-write-empty); load_storage gives `(0, D)`.
  </behavior>
  <action>
    Use `pytest.importorskip("qdrant_client")` + `QdrantClient(":memory:")` (the same pattern the module docstring :219-221 references for unit tests). Seed points via `client.upsert(...)` with explicit ids, payloads (including a `created_at` int and `workspace_id` to prove it is dropped), and float32 vectors. Assert against `nano_vectordb.dbs.load_storage` (import it). Mark tests `@pytest.mark.unit`. Keep D small so the suite stays fast — the REAL-scale memory proof is Task 3 on Aliyun, NOT here (toy fixtures can't reproduce the OOM, per CONTEXT specifics).

    This is the behavior-anchor that protects the contract-shape (the on-disk schema) the refactor touches, per the CLAUDE.md harness discipline. Channel: LOCAL repo (Bash/Write/Read) — no SSH/Databricks.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/unit/test_qdrant_to_nanovdb.py` exists and contains `load_storage` AND `QdrantClient(":memory:")` AND `array_to_buffer_string` (the byte-identity assertion).
    - `venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v` exits 0 with ≥3 tests collected and passing.
    - `grep -nE "shape == \(|matrix.*==|load_storage" tests/unit/test_qdrant_to_nanovdb.py` shows the schema + byte-identity assertions.
  </acceptance_criteria>
  <done>A fast, deterministic behavior-anchor test pins the on-disk nano_vectordb schema (shape, data rows, dropped fields) AND the exact matrix base64 bytes through `load_storage`, so any future converter change that breaks the consumer contract fails CI.</done>
</task>

<task type="auto" gate="aliyun-write-op">
  <name>Task 3: [ALIYUN WRITE-OP] Deploy fixed converter to Aliyun prod, run it against the REAL 82582-point relationships collection under RSS monitoring, then re-enable qdrant-snapshot.timer</name>
  <files>scripts/qdrant_to_nanovdb.py (deployed to Aliyun /root/OmniGraph-Vault/scripts/), qdrant-snapshot.timer (Aliyun systemd)</files>
  <read_first>
    - scripts/qdrant_to_nanovdb.py (the refactored version from Task 1 — this is what gets deployed)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md (the #41 "Re-enable trigger" + "Disk headroom" + "Timer re-enable is the closure marker" specifics)
    - MEMORY: aliyun_ssh_manual_trigger_env (manual cmds need `set -a; source /root/.hermes/.env; set +a`)
    - MEMORY: aliyun_vitaclaw_ssh (SSH alias + Aliyun paths)
    - MEMORY: qdrant_docker_no_restart_policy_trap + aliyun_rebuild_docker_tmp_damage (confirm docker/Qdrant is up before running — the converter needs Qdrant on :6333)
  </read_first>
  <action>
    **CHANNEL: ALIYUN WRITE-OP. This task MUTATES Aliyun prod state (deploys code, runs the converter writing real vdb_*.json, re-enables a systemd timer). Per CONTEXT channel-discipline + memory `aliyun_ssh_manual_trigger_env`, the executor runs these via Bash `ssh aliyun-vitaclaw` DIRECTLY (the agent IS the operator for Aliyun ops, v3.5/aim-series precedent). This task is explicitly authorized as a write-op.**

    Steps (executor runs each via `ssh aliyun-vitaclaw "..."`):

    0. PRE-FLIGHT (read-only first): confirm Qdrant up and the 3 collections live:
       `ssh aliyun-vitaclaw "docker ps --format '{{.Names}} {{.Status}}' | grep -i qdrant"` (expect Up)
       `ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; curl -s localhost:6333/collections | python3 -c 'import sys,json; print([(c[\"name\"]) for c in json.load(sys.stdin)[\"result\"][\"collections\"]])'"` (expect the 3 `..._gemini_embedding_2_3072d` collections).
       Confirm disk headroom: `ssh aliyun-vitaclaw "df -h /dev/vda3"` (need ≥ ~3GB free for the regen + the Plan-03 tar; if <3GB, STOP and surface — do NOT touch #61 containerd here, that is out of scope).

    1. DEPLOY the fixed converter to Aliyun. The Aliyun repo is `/root/OmniGraph-Vault`. Copy the local refactored file up:
       `scp scripts/qdrant_to_nanovdb.py aliyun-vitaclaw:/root/OmniGraph-Vault/scripts/qdrant_to_nanovdb.py`
       Then verify the copy landed: `ssh aliyun-vitaclaw "grep -c 'bytearray\|b64encode' /root/OmniGraph-Vault/scripts/qdrant_to_nanovdb.py"` (expect ≥1).
       (If Aliyun repo is git-managed and ahead, reconcile per CLAUDE.md "Reconcile git state" — prefer scp of the single file to avoid a full git dance, then note the drift for a follow-up commit.)

    2. RUN the converter against REAL Qdrant under RSS monitoring (this is the OOM proof at scale — CONTEXT mandates real 82582-point validation, not a toy). Use `/usr/bin/time -v` to capture Maximum resident set size. The converter's `main()` does all 3 namespaces; run it whole so chunks+entities+relationships all regenerate:
       ```
       ssh aliyun-vitaclaw 'set -a; source /root/.hermes/.env; set +a; cd /root/OmniGraph-Vault && /usr/bin/time -v venv-aim1/bin/python scripts/qdrant_to_nanovdb.py 2>&1 | tee /tmp/arx4-converter-run.log'
       ```
       (Use the ingest venv `venv-aim1/bin/python` — it has qdrant_client + nano_vectordb. If that path differs, discover via `ssh aliyun-vitaclaw "ls /root/OmniGraph-Vault/venv*/bin/python"`.)
       Capture from the log: the `Maximum resident set size (kbytes)` line, the per-namespace `qdrant_snapshot_file collection=... points=... wall_s=...` lines, and the final `qdrant_snapshot_ok files_written=3`.

    3. VERIFY the output files are real, not placeholders (read-only):
       `ssh aliyun-vitaclaw "ls -la /root/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json /root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json /root/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json"`
       Then assert data_len via load (read-only):
       `ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; cd /root/OmniGraph-Vault && venv-aim1/bin/python -c 'from nano_vectordb.dbs import load_storage as L; r=L(\"/root/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json\"); c=L(\"/root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json\"); print(\"rel rows\", len(r[\"data\"]), r[\"matrix\"].shape, \"chunk rows\", len(c[\"data\"]), c[\"matrix\"].shape)'"`
       Expect rel rows ≈ 82582, chunk rows ≈ 3851 (the live Qdrant counts), both matrices (N, 3072).

    4. RE-ENABLE the timer (the #41 closure marker — only after steps 2-3 prove the fix works):
       `ssh aliyun-vitaclaw "systemctl enable --now qdrant-snapshot.timer && systemctl status qdrant-snapshot.timer --no-pager | head -5 && systemctl list-timers qdrant-snapshot.timer --no-pager"`
       Expect `enabled` + `active (waiting)` + a NEXT fire time.

    Record all log excerpts (RSS line, per-namespace points/wall, the load_storage row counts, the timer status) into the SUMMARY — they are the #41 closure evidence.
  </action>
  <verify>
    <automated>ssh aliyun-vitaclaw "grep -c 'qdrant_snapshot_ok files_written=3' /tmp/arx4-converter-run.log && systemctl is-enabled qdrant-snapshot.timer && test $(stat -c%s /root/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json) -gt 1000000 && echo VDB_REAL"</automated>
  </verify>
  <acceptance_criteria>
    - `/tmp/arx4-converter-run.log` on Aliyun contains `qdrant_snapshot_ok files_written=3` AND does NOT contain `oom` / `Killed` / `MemoryError` (the OOM is gone at real scale).
    - The `/usr/bin/time -v` `Maximum resident set size (kbytes)` value is recorded in SUMMARY and is < ~3500000 kbytes (~3.4 GB) — i.e. bounded well under the 14G box (or, if MemoryMax fallback was needed per Task 1, the documented ceiling is cited instead).
    - `ssh aliyun-vitaclaw "ls -la .../vdb_relationships.json"` shows size > 1000000 bytes (NOT the 49-byte placeholder).
    - The load_storage probe prints relationships rows ≈ 82582 with matrix shape `(N, 3072)` and chunks rows ≈ 3851 with shape `(N, 3072)`.
    - `ssh aliyun-vitaclaw "systemctl is-enabled qdrant-snapshot.timer"` prints `enabled` AND `systemctl is-active qdrant-snapshot.timer` prints `active`.
  </acceptance_criteria>
  <done>The fixed converter ran on Aliyun prod against the real 82582-point relationships collection with bounded peak RSS (no OOM), wrote real (non-placeholder) vdb_*.json files aligned to live Qdrant counts, and qdrant-snapshot.timer is re-enabled — closing ISSUES #41 (and folding #42, since bounding RSS removes the SLB-throttle trigger).</done>
</task>

</tasks>

<verification>
- Local: `venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v` green (schema + byte-identity + empty + guards).
- Aliyun (read-only re-probe after Task 3): `ssh aliyun-vitaclaw "ls -la .../vdb_relationships.json"` > 1MB; `systemctl is-enabled qdrant-snapshot.timer` == enabled.
- The RSS ceiling from `/usr/bin/time -v` is cited in SUMMARY as the bounded-memory proof.
</verification>

<success_criteria>
- export_collection_to_nanovdb no longer double-holds vectors (no list[list[float]], no np.array(vectors)); atomic write + both guards preserved; on-disk bytes byte-identical to the old path (test-proven).
- Real-scale Aliyun run: exit 0, no OOM, bounded RSS, real vdb_relationships.json (>1MB) + aligned chunk/entity files.
- qdrant-snapshot.timer enabled+active = #41 closure marker set.
</success_criteria>

<output>
After completion, create `.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-01-SUMMARY.md` citing: the pytest result, the Aliyun `/usr/bin/time -v` Maximum-RSS line, the per-namespace points/wall-s, the load_storage row-count probe, and the timer is-enabled/is-active output.
</output>
