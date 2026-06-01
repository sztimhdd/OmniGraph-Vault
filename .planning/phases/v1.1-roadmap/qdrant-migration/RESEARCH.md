# RESEARCH — v1.1.qdrant-migration

**Status:** Reference shim (research already completed in `/.planning/quick/260601-qdrant-research/`).
**Do not re-do research.** Path 2 is locked.

## Canonical research artifact

`.planning/quick/260601-qdrant-research/RESEARCH.md` (399 lines, authored 2026-06-01).

Read it whole before planning or executing. The orchestrator and gsd-planner have
both consumed it; this file exists only so future readers landing in the phase
directory have a one-hop pointer.

## Locked decisions (do NOT re-evaluate)

1. **Path 2 (Aliyun dual-write)** is the chosen architecture.
   - Path 1 BLOCKED — LightRAG `qdrant_impl.py` hardcodes `url=` (does not plumb
     `path=`); even with monkey-patch, qdrant-client local mode uses portalocker
     exclusive SQLite lock → incompatible with Aliyun's two-process layout
     (kb-api + batch_ingest concurrently).
   - Path 3 BLOCKED — cross-station HTTP would add 1.5–2.5 s per long_form
     query (200–300 ms RTT × 6–10 round-trips), introduce Aliyun as a hard
     dependency for Databricks read-traffic, and require Caddy + TLS + api-key
     ops surface. Reliability regression vs current rsync-snapshot model.

2. **Aliyun = Qdrant (write+read); Databricks/Hermes = NanoVectorDB (read).**
   Cross-station data flow stays as today (rsync). Only the upstream producer
   changes: instead of LightRAG writing nano-vectordb JSON natively, a 6-h
   converter cron snapshots Qdrant → vdb_*.json at the same path.

3. **Re-ingest pool = 252 articles** (238 ok + 14 failed with body), measured
   2026-06-01 via `sqlite3 ... GROUP BY status`. NOT 287 (PR #4 estimate is off).
   Wall-clock 8–24 h depending on per-article DeepSeek tail latency; Path 2
   re-ingest must use 6 batches of ≤50 (WeChat throttle floor), spread over
   3–5 days.

4. **rerank env block** (4 `OMNIGRAPH_LLM_RERANK_*` lines) folded from ISSUES
   row #26 into this phase. Single Aliyun kb-api restart applies Qdrant cutover
   + rerank env + structural hydrate fix together (minimizes #27 throttle blast
   radius — see canonical RESEARCH §"Cross-deps surfaced").

5. **HT-6 N=4 lock-break test** (transferred A → B → #26 → #25). Aliyun has
   direct SSH + uvicorn access (Databricks Apps OAuth proxy blocks pytest from
   local PAT). Must run against deployed Aliyun kb-api post-cutover and cite
   evidence in VERIFICATION.md.

6. **vdb_archive_*.json deferred-delete** extended to **2026-06-22** (Hermes
   RO-freeze unfreeze date, HC-7). Existing vdb_*.json renamed pre-cutover and
   retained as fallback until Hermes can re-ingest deltas.

## Aliyun read-only diagnostic snapshot (2026-06-01)

| Fact | Value | How verified |
|------|-------|--------------|
| LightRAG version | **1.4.16** | `venv-aim1/bin/python -c 'import lightrag; print(lightrag.__version__)'` |
| Qdrant docker present | **NO** (cleanslate) | `docker ps -a \| grep qdrant` empty |
| qdrant-client python lib | **NOT installed in venv-aim1** | `python -c 'import qdrant_client'` → ModuleNotFoundError |
| `vdb_chunks.json` | 58.98 MB | `ls -la lightrag_storage/` |
| `vdb_entities.json` | 778.88 MB | same |
| `vdb_relationships.json` | 1120.51 MB | same |
| `/data` directory | **DOES NOT EXIST** (PR #4 path wrong) | `df -h /data` → "No such file or directory" |
| `/var/lib/` available | yes (49 GB free on /) | `df -h /` |
| `/var/www/kb_export/` | **DOES NOT EXIST** (must create) | `ls -la` |
| `/var/www/kb/` (Caddy) | exists, served by Caddy | `ls -ld` |
| override.conf | 6 lines (memory + 4 KB env) | `cat /etc/systemd/system/kb-api.service.d/override.conf` |
| /etc/hosts Vertex pin | present (3 lines) | `grep` |
| Free RAM | 8.2 GB | `free -h` |
| Free disk on / | 43 GB | `df -h /` |
| Article DB body-NOT-NULL | 238 ok + 14 failed + 540 skipped | `sqlite3 ... GROUP BY status` |
| **Re-ingest candidate pool** | **252** (238 + 14) | same |
| Docker installed | yes (29.1.3) | `which docker && docker --version` |

## Hard findings surfaced to plan

1. **PR #4 is incomplete** — patches `ingest_wechat.py` only. `kb/api.py:89`
   ALSO instantiates LightRAG (lifespan singleton, RAM 2.4 GB on Aliyun), and
   `kg_synthesize.py:155` does too (CLI fallback). Plan extends to 3 sites.

2. **`/data` doesn't exist on Aliyun** — PR #4 docker volume target wrong.
   Plan uses `/var/lib/qdrant` instead.

3. **Snapshot landing dir.** RESEARCH suggested `/var/www/kb_export/`. To
   minimize sync_to_databricks.sh changes, plan writes converter output
   in-place to `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json`
   (pre-cutover archive of existing files goes to
   `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_archive_*.json`). Step 3
   tarball already covers everything in `lightrag_storage/`. Optional
   `kb_export/` mirror is a deferred enhancement, not a phase requirement.

4. **No `sync_to_hermes.sh` exists in repo.** RESEARCH mentioned it but it's
   not present. Hermes-side rsync mechanism is operator-driven (Hermes pulls
   from Aliyun on its own schedule). Plan does NOT introduce a new
   sync_to_hermes.sh — Hermes is RO until 2026-06-22 (HC-7) and the existing
   pull mechanism continues to work since vdb_*.json filenames + path are
   unchanged.

5. **Q2 LightRAG rerank payload-key compat** is listed UNCERTAIN in canonical
   RESEARCH. `QdrantVectorDBStorage.query()` returns `{**dp.payload, "distance",
   "created_at"}` (no `__id__` / `__created_at__` double-underscore). If
   `apply_rerank_if_enabled` walks keys looking for `__id__`, rerank silently
   degrades to no-op on Qdrant queries. Plan includes a smoke task post-cutover
   that asserts mode='mix' P2-3 LLM rerank still fires (grep the JSON-batch
   marker in journalctl).

## What this phase does NOT decide / build

- New LightRAG SDK fork. We use `vector_storage="QdrantVectorDBStorage"` as
  shipped in 1.4.16.
- Hermes-side change. HC-7 freeze.
- Databricks-side LightRAG / vector_storage change. Stays NanoVectorDBStorage,
  reads vdb_*.json from rsync.
- Cohere / OpenAI / external rerank paths. P2-3-perf-fix-A's LLM rerank
  (Vertex Gemini batch JSON) stays the default.
- Caddy reverse-proxy / TLS / api-key on Qdrant. Bind 127.0.0.1:6333 only.

## References

- Canonical RESEARCH: `.planning/quick/260601-qdrant-research/RESEARCH.md`
- ISSUES rows referencing this work: #25 (P0 root), #26 (folded), #27 (folded),
  #22 (perf-fix-B history)
- Roadmap: `.planning/phases/v1.1-roadmap/ROADMAP.md` HC-1..HC-9
- State: `.planning/phases/v1.1-roadmap/STATE-v1.1.md` row B (perf-fix-B
  CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED)
- PR #4 design (incomplete): `git show pr-4-qdrant:.planning/qdrant-migration.md`
- LightRAG 1.4.16 `qdrant_impl.py` (local venv copy verified matches Aliyun pin)
- CLAUDE.md PRINCIPLE #1, #2, #5, #7, #9, #10 + HC-1..HC-9
