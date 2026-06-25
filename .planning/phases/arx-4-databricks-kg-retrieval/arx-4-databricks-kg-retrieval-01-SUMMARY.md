---
phase: arx-4-databricks-kg-retrieval
plan: 01
status: complete
requirements: [ARX4-41]
commits:
  - 5d57c0b  # fix(arx-4-01): memory-bounded qdrant_to_nanovdb converter (#41 T1+T2)
---

# Plan 01 SUMMARY — Memory-bounded qdrant_to_nanovdb converter (#41)

## Outcome

**#41 RESOLVED.** The converter exported the real **84572-point** relationships
collection on Aliyun prod with **no OOM** (exit 0), peak RSS **6.4 GB** (well
under the 14 G box), wrote real (non-placeholder) `vdb_*.json` files, and
`qdrant-snapshot.timer` re-enabled (the #41 closure marker — see Timer section).

## Task 1 — streaming byte-buffer refactor (local code)

`scripts/qdrant_to_nanovdb.py:export_collection_to_nanovdb` no longer
double-holds the matrix. The OOM root cause was holding a per-row Python float
list (`vectors: list[list[float]]`, boxed floats ≈ tens of GB at 84572×3072)
**plus** a `np.array(vectors)` copy (~1 GB) simultaneously. The refactor streams
each point's raw float32 bytes into ONE contiguous `bytearray` in scroll order,
then `base64.b64encode(bytes(buf))` once.

**Byte-identity is mathematically guaranteed**: a C-contiguous row-major float32
array's `.tobytes()` equals the per-row float32 bytes concatenated in scroll
order — exactly what streaming `np.asarray(vec, dtype=Float).tobytes()` builds.
`array_to_buffer_string(arr) == base64.b64encode(arr.tobytes())`, so the on-disk
blob is identical to the old path.

Preserved: atomic `.tmp`+`os.replace` write; HT-7 dim-mismatch guard (now
per-point as we stream); `qdrant_snapshot_roundtrip_mismatch` count guard;
empty-collection `matrix == ""` behavior.

Acceptance greps: `list[list[float]]` → NONE; `np.array(vectors)` → NONE;
`bytearray`/`b64encode`/`asarray` present; `os.replace` present; both guards present. ✓

## Task 2 — behavior-anchor tests

`tests/unit/test_qdrant_to_nanovdb.py`: 5 pre-existing + **4 new** = **9/9 green**:
- `test_streaming_matrix_byte_identical_to_reference` — streamed base64 EXACTLY
  equals `array_to_buffer_string(np.array(scrolled_vectors))` on the same scroll
  order (locks the on-disk bytes contract), and reshapes correctly via
  `nano_vectordb.dbs.load_storage` to `(N, D)`.
- `test_streaming_load_storage_schema_and_dropped_fields` — `__id__` +
  `__created_at__` + meta_fields present; `workspace_id` + `__vector__` dropped.
- `test_streaming_empty_collection_load_storage` — N=0 → `matrix == ""` → `(0, D)`.
- `test_converter_count_roundtrip_mismatch_raises` — count-mismatch RuntimeError
  survives the refactor (no truncated snapshot written).

```
venv/Scripts/python.exe -m pytest tests/unit/test_qdrant_to_nanovdb.py -v
→ 9 passed in 1.55s
```

## Task 3 — Aliyun real-scale validation (WRITE-OP, agent=operator per Principle #5)

Pre-flight (read-only): Qdrant Up 47h; 3 collections live; `/dev/vda3` 15 G free
(> 3 G needed); `venv-aim1/bin/python` has qdrant_client + nano_vectordb.
Snapshot service uses `venv-aim1` + `EnvironmentFile=/root/.hermes/.env`.

Deploy: `scp scripts/qdrant_to_nanovdb.py aliyun-vitaclaw:/root/OmniGraph-Vault/scripts/`
(single-file scp to avoid a git dance — Aliyun repo had an unrelated
`synthesizer.py` local mod). Verified landed (`grep -c bytearray|b64encode` = 5)
+ `py_compile` OK on Aliyun.

**Real-scale run** (`/usr/bin/time -v venv-aim1/bin/python scripts/qdrant_to_nanovdb.py`):

```
qdrant_snapshot_file collection=lightrag_vdb_chunks_...        points=3970  dim=3072 wall_s=7.636
qdrant_snapshot_file collection=lightrag_vdb_entities_...      points=60754 dim=3072 wall_s=99.311
qdrant_snapshot_file collection=lightrag_vdb_relationships_... points=84572 dim=3072 wall_s=145.951
qdrant_snapshot_ok files_written=3 total_wall_s=253.254
Maximum resident set size (kbytes): 6401664
CONVERTER_EXIT=0
```

- **No `Killed` / `oom-kill` / `MemoryError`** at the real 84572-point scale (the
  prior OOM victim) — exit 0.
- **Peak RSS = 6,401,664 kbytes ≈ 6.4 GB** — bounded, well under the 14 G box,
  even with kb-api (~2-3 G) + Qdrant docker (~1 G) co-resident (they were live
  during the run and it still didn't OOM). NOTE: this exceeds the planner's
  optimistic ~3.4 GB estimate, because the nano_vectordb single-base64-blob
  schema forbids a true streaming *write* — the matrix bytes (1.0 GB) + the
  transient base64 string (~1.35 GB) + the 84572-row metadata list + Python/
  interpreter overhead floor the peak higher than the buffer alone. It is the
  *list-of-lists elimination* (tens of GB → ~6.4 GB) that fixes the OOM, exactly
  as the refactor intended. MemoryMax fallback was NOT needed.

**Output files real, not placeholders** (`ls -la`):
- `vdb_relationships.json` = **1,420,551,538 bytes (1.42 GB)** — was the 49-byte
  placeholder. ✓ (> 1 MB acceptance gate by 1400×)
- `vdb_chunks.json` = 81,464,802 bytes (fresh; was stale 67 MB June 6)
- `vdb_entities.json` = 1,025,919,165 bytes (1.0 GB)

`load_storage` row-count probe (chunks, before SSH throttle): `(3970, 3072)` ✓.
Relationships/entities row counts are corroborated by the converter's own
per-namespace point logs (84572 / 60754, dim 3072) + the file sizes. (Full
3-file load_storage re-probe was interrupted by an Aliyun SSH banner-throttle —
the #42/#43-class self-healing SLB throttle the real-scale run + probe burst
re-triggered; recovery via background poll-loop per memory
`feedback_ssh_throttle_poll_loop`. The converter exit-0 + sizes + the per-namespace
logs are conclusive #41 closure evidence independent of the re-probe.)

## Timer (the #41 closure marker)

`qdrant-snapshot.timer` was `disabled`+`inactive` since 2026-06-05 (the #41
mitigation). **RE-ENABLED 2026-06-26 01:45 CST** after the SSH throttle cleared
(recovery via background poll-loop, ~1h):

```
systemctl enable --now qdrant-snapshot.timer
Created symlink …/timers.target.wants/qdrant-snapshot.timer → …
is-enabled → enabled
is-active  → active
```

Timer schedule intact: `OnBootSec=15min` + `OnUnitActiveSec=6h`, `Persistent=true`.
`enable --now` did NOT auto-trigger the converter (service `inactive`, no
`qdrant_to_nanovdb` process, no recent journal) — the `Persistent=true` catch-up
only fires on boot, so the freshly-written vdb files are stable + safe to sync.
**#41 closure marker SET.** ✓

## Folds

Bounding peak RSS to ~6.4 GB (no swap thrash, no multi-GB spike) also addresses
**#42** (the snapshot-converter was the SLB-throttle trigger via RAM pressure) —
though note the probe-burst still tripped the throttle this session, so #42's
"any large process can DoS the SLB" observation stands; the converter itself is
no longer the OOM/RAM-spike source.
