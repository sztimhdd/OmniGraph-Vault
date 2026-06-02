# Qdrant Migration Cross-Station Research

> **Scope:** PR #4 (`ops/qdrant-migration`) only patches Aliyun ingest. This research covers how Databricks + Hermes (read-only RAG consumers) get vector data after Aliyun cuts over to Qdrant.
>
> **Author:** sub-session research (2026-06-01, ~50 min)
> **Read by:** orchestrator (main session), to decide next step
> **Status:** READ-ONLY. No code changes. No PR mutation.

---

## Ground-truth facts (collected this session)

| Fact | Value | Source |
|------|-------|--------|
| LightRAG version on Aliyun | **1.4.16** (NOT 1.4.15 as memory says — drift) | `ssh aliyun-vitaclaw "venv-aim1/bin/python -c 'import lightrag; print(lightrag.__version__)'"` |
| Aliyun RAM / cores / disk | 14 GB / 2 vCPU / 99 GB (52 used, 43 free) | `free -h && df -h /root && nproc` |
| Aliyun current memory state | 4.3 GB used (kb-api 2.4 GB RSS), 9.4 GB free | `free -h && cat /proc/3319394/status` |
| `vdb_chunks.json` | 59 MB | `ls -la /root/.hermes/omonigraph-vault/lightrag_storage/` |
| `vdb_entities.json` | 743 MB | same |
| `vdb_relationships.json` | 1.07 GB | same |
| **Total vdb JSON** | **1.85 GB** | |
| Articles in DB w/ body | 238 ok + 14 failed + 540 skipped | `sqlite3 kol_scan.db "SELECT i.status, COUNT(*) FROM ingestions i JOIN articles a ON a.id=i.article_id WHERE a.body NOT NULL GROUP BY status"` |
| **Re-ingest candidate pool** | **~252** (PR #4 estimate "287" off) | same |
| embedding_dim | 3072 | head of `vdb_chunks.json` |
| Qdrant docker on Aliyun | NOT running (PR #4 not deployed yet) | `docker ps -a \| grep qdrant` empty |
| `omnigraph-afternoon-ingest.service` | `failed` (OOM) | `systemctl list-units` |
| `omnigraph-evening-ingest.service` | `failed` (OOM) | same |
| kb-api on Aliyun | running, port 8766, RSS 2.4 GB | `ps -ef + /proc/PID/status` |
| `ingest_wechat.py:392` `LightRAG(...)` call | matches PR #4 BEFORE block (no `vector_storage=` arg) | `grep -n` |

### Per-article ingest timing (real prod, journalctl `batch_timeout_metrics`)

| Date | avg article time | total batch elapsed | completed / total | timed_out |
|------|------------------|--------------------|--------------------|-----------|
| May 25 (52 art batch) | **113 s** | 643 s | 5/52 | 0 |
| May 25 evening | **303 s** | 1610 s | 5/192 | 0 |
| May 26 | **349 s** | 4604 s | 9/212 | 1 |
| May 29 morning | **242 s** | 3759 s | 9/166 | 1 |
| May 29 evening | **708 s** | 5357 s | 3/173 | 0 |

**Histogram of article time-buckets seen**: `0-60s`, `60-300s`, `300-900s`, `900s+` all populated. Variance is dominated by article entity density and DeepSeek LLM tail latency.

---

## Path 1: LightRAG `QdrantVectorDBStorage` local file mode

**Verdict: BLOCKED upstream; FEASIBLE-but-broken with monkey-patch.**

### Evidence

`venv/Lib/site-packages/lightrag/kg/qdrant_impl.py:582-591` (LightRAG 1.4.16 — verified on local venv, identical to Aliyun pin):

```python
if self._client is None:
    self._client = QdrantClient(
        url=os.environ.get(
            "QDRANT_URL", config.get("qdrant", "uri", fallback=None)
        ),
        api_key=os.environ.get(
            "QDRANT_API_KEY",
            config.get("qdrant", "apikey", fallback=None),
        ),
    )
```

LightRAG hard-codes `url=`. The `path=` parameter (which qdrant-client itself supports, per [docs.langchain.com](https://docs.langchain.com/oss/python/integrations/vectorstores/qdrant) and [qdrant-client README](https://github.com/qdrant/qdrant-client)) is NEVER plumbed through. To use local mode you must:

- Monkey-patch `QdrantVectorDBStorage.__init__` to swap in `QdrantClient(path=os.environ["QDRANT_PATH"])`, OR
- Fork LightRAG.

### Even if patched, multi-process is unsafe

`qdrant_client/local/qdrant_local.py` (per [DeepWiki summary](https://deepwiki.com/qdrant/qdrant-client/2.2-local-mode)) uses **`portalocker` non-blocking exclusive lock** on the SQLite file. Single writer per file. Aliyun runs **two** LightRAG-instantiating processes simultaneously: `kb-api` (always-on, reads) and `batch_ingest` (cron, writes). Local mode is fundamentally incompatible with this layout.

### Cross-station rsync angle

Even if Aliyun used local mode (it can't — Q1 above), shipping `qdrant_local/` to Databricks via rsync only works if BOTH ends are local mode. But local mode = SQLite file format. Server mode = Qdrant binary segments under `/qdrant/storage/`. **The two formats are NOT interchangeable** — you cannot rsync server-mode storage and have local mode read it, and vice versa.

### Implementation sketch (rejected)

N/A — blocked.

### Verdict

**BLOCKED.** Even at the cost of a fork, the SQLite single-writer lock kills the multi-process layout we need.

---

## Path 2: Aliyun dual-write — Qdrant + nano-vectordb JSON snapshot

**Verdict: VIABLE.** ~150–200 LoC converter + 1 cron timer. Recommended path.

### Architecture

```
Aliyun ECS:
  ┌───────────────┐      ┌──────────┐
  │ ingest_wechat │─────▶│  Qdrant  │  (docker, :6333, mmap-backed)
  └───────────────┘      │  server  │
                         └─────┬────┘
                               │
  ┌───────────────┐            │
  │    kb-api     │◀───────────┘  (queries via QDRANT_URL=localhost:6333)
  └───────────────┘            │
                               ▼
                         ┌──────────────────────┐
                         │ qdrant_to_nanovdb.py │  (cron, e.g. every 6h)
                         └────────┬─────────────┘
                                  │ produces fresh vdb_*.json
                                  ▼
                         ┌──────────────────────┐
                         │  /var/www/kb_export  │
                         └────────┬─────────────┘
                                  │ rsync (existing scripts/sync_to_databricks.sh, scripts/sync_to_hermes.sh)
                                  ▼
              Databricks lightrag_storage/          Hermes lightrag_storage/
              (NanoVectorDBStorage reads JSON)      (NanoVectorDBStorage reads JSON)
```

### Why this works

1. **Aliyun OOM solved** — both ingest_wechat AND kb-api point at Qdrant (NanoVectorDBStorage no longer instantiated → 1.85 GB JSON never loaded into Python heap).
2. **Databricks + Hermes unchanged** — keep using NanoVectorDBStorage. They get fresh vdb_*.json from cron snapshots. No infra change there.
3. **No new outbound network** — Databricks doesn't query Aliyun. Hermes doesn't query Aliyun. Cross-station data flow stays as today (rsync).
4. **No new attack surface** — Qdrant stays bound to `127.0.0.1:6333` on Aliyun (already in PR #4 spec).

### Conversion complexity

`qdrant_to_nanovdb.py` (~150–200 LoC):

```python
# Pseudo-code, ~150-200 LoC
import json
import os
from qdrant_client import QdrantClient

def export_collection_to_nanovdb(client, collection_name, output_path, embedding_dim):
    points = []
    matrix = []
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not batch:
            break
        for p in batch:
            # Map Qdrant payload back to nano-vectordb format
            entry = {
                "__id__": p.payload["id"],
                "__created_at__": p.payload.get("created_at", 0),
                "content": p.payload.get("content", ""),
                # ... preserve meta_fields (file_path, full_doc_id, ...)
            }
            for k in ("file_path", "full_doc_id", "tokens", "chunk_order_index", "src_id", "tgt_id"):
                if k in p.payload:
                    entry[k] = p.payload[k]
            points.append(entry)
            matrix.append(p.vector)
        if next_offset is None:
            break
        offset = next_offset

    nano_format = {
        "embedding_dim": embedding_dim,
        "data": points,
        "matrix": matrix,  # list of lists; nano-vectordb stores as packed array on disk
    }
    tmp = output_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(nano_format, f)
    os.replace(tmp, output_path)

# Run for each: lightrag_vdb_chunks_*, lightrag_vdb_entities_*, lightrag_vdb_relationships_*
```

LoC count includes: error handling, atomic .tmp+rename, dim mismatch guard, namespace-to-filename mapping, and a `verify_roundtrip()` smoke that asserts `len(nano["data"]) == client.count(...).count`.

### Maintenance burden: **MEDIUM**

Risk surface = LightRAG nano-vectordb internal format. The `vdb_*.json` schema (`{embedding_dim, data: [...], matrix: [...]}`) has been stable across LightRAG 1.3.x → 1.4.16, but the converter must be revalidated on every LightRAG upgrade. If LightRAG renames `__id__` → `id` or moves to a binary format upstream, the converter breaks. Mitigation: pin a smoke test that loads converter output via `NanoVectorDBStorage.initialize()` and runs a known query; CI should fail loudly if format drifts.

### Cron cadence

Realistic 6 h cadence. Snapshot a 1.85 GB collection takes ~30–60 s on Aliyun's disk. rsync to Databricks (workspace upload via `databricks workspace import`) is the slow step — ~2 GB over Aliyun → Databricks ≈ 5–15 min depending on backbone. 6 h cadence = staleness floor of 6 h for Databricks RAG; acceptable per user constraint that Databricks is "read-only KB serve, not real-time".

### Verdict

**VIABLE.** Recommended unless the converter LoC budget is unacceptable. ~200 LoC + 1 systemd timer + minor `scripts/sync_to_databricks.sh` integration.

---

## Path 3: Databricks HTTP → Aliyun Qdrant

**Verdict: VIABLE w/ ops + security caveats.**

### Network reachability

- Aliyun public IP `101.133.154.49` (per project memory `aliyun_vitaclaw_ssh.md`)
- Databricks Apps egress to public Internet **is** allowed by default for non-Databricks domains (the corp Cisco Umbrella issue is local-machine outbound; Databricks Apps run in Azure infra without that proxy).
- Latency: Aliyun-Shanghai ↔ Azure-Eastus2 RTT ≈ **200–300 ms** (typical TransPacific)
- Bandwidth: not the bottleneck; vector queries are small (3072 floats × 4 bytes = 12 KB per vector returned, top_k typically ≤ 60).

### Latency cost on long_form RAG

LightRAG `naive` + `local` + `global` modes each issue 1–3 vector queries per namespace (chunks/entities/relationships). long_form total ≈ **6–10 round-trips**. At 250 ms RTT: **+1.5 to +2.5 s per long_form query**.

P2-3 SC#2 budget is 65 s for long_form. +2.5 s eats ~4% of budget. Acceptable but not free; entity-rich queries that already approach the ceiling could tip over.

### Security

`docker run -p 0.0.0.0:6333:6333 qdrant/qdrant` with no auth = **catastrophic**. Anyone with the IP queries the entire vector DB.

Mitigation stack required:

1. **Caddy reverse-proxy** in front of Qdrant on Aliyun, bind public 443 only.
2. **api-key auth** via `QDRANT__SERVICE__API_KEY` env on the docker container.
3. **TLS** — Caddy auto-cert via Let's Encrypt for some `qdrant.<your-domain>.com`.
4. **IP allowlist** — Databricks Apps IPs are NOT static (Azure runtime rotates them). Either:
    - allowlist all Azure-Eastus2 ranges (huge surface, ~millions of IPs), OR
    - rely solely on api-key (good if key has > 256 bits entropy AND key rotation is automated)
5. **Rate limit** at Caddy — Databricks should not exceed N req/min; throttle DDoS.

Ops effort: ~half-day to set up + ongoing key rotation discipline.

### Reliability

Every Databricks long_form query becomes dependent on:

1. Aliyun ECS uptime
2. Aliyun → public Internet route
3. Caddy + Qdrant docker liveness on Aliyun

Today, Databricks long_form depends only on Databricks itself (NanoVectorDBStorage reads local JSON shipped via rsync). Path 3 introduces Aliyun as a hard dependency for read traffic. If Aliyun crashes (this exact OOM scenario!), Databricks RAG goes down too.

### Implementation sketch

```python
# Databricks Apps env (databricks-deploy/app.yaml):
env:
  - name: QDRANT_URL
    value: "https://qdrant.<your-domain>.com"
  - name: QDRANT_API_KEY
    valueFrom: <secret-name>

# kb/api.py LightRAG init:
rag = LightRAG(
    working_dir=...,
    vector_storage="QdrantVectorDBStorage",   # ← same as PR #4
    ...
)
```

### Verdict

**VIABLE but fragile.** Use only if Path 2 converter LoC is rejected. The hard dependency on Aliyun for Databricks read-traffic is a real reliability regression vs current rsync-snapshot architecture.

---

## Q1–Q4 short answers

### Q1: Qdrant local mode multi-process safety

**UNSAFE.** `qdrant_client/local/qdrant_local.py` uses `portalocker` exclusive lock. Aliyun's kb-api + batch_ingest cannot share a local-mode file. Local mode is single-process by design. (Source: [DeepWiki](https://deepwiki.com/qdrant/qdrant-client/2.2-local-mode), reads "Acquires a non-blocking exclusive lock using portalocker to prevent concurrent access").

### Q2: Qdrant + LLM rerank (P2-3-perf-fix-A) compat

**UNCERTAIN — needs smoke test.**

`QdrantVectorDBStorage.query()` (line 717-724) returns `[{**dp.payload, "distance": dp.score, "created_at": ...}]`. Payload keys include: `id`, `workspace_id`, `created_at`, plus meta_fields.

`NanoVectorDBStorage.query()` returns dict shape with `__id__`, `__created_at__` (double-underscore convention).

P2-3 LLM rerank (`apply_rerank_if_enabled` in LightRAG `utils.py:2696`) walks the returned list and reads keys to build the rerank prompt. **If it accesses `__id__` instead of `id`, Qdrant results break rerank silently** (graceful degrade to no-rerank).

**Action item (NOT in this research scope):** when PR #4 deploys, run a long_form query and verify the LLM rerank stage actually fires (check `databricks-deploy/_aliyun_pull/...` logs for `apply_rerank_if_enabled` markers).

### Q3: Re-ingest 287 articles real duration

**~8–24 hours, NOT 15 min.** PR #4 doc estimate is **off by 2 orders of magnitude**.

Real journalctl `batch_timeout_metrics` over 5 batches show avg article time **113s → 708s**, with full histogram coverage of 60–300s, 300–900s, and 900s+ buckets.

Math:

- Best case: 252 articles × 113 s = 28,476 s ≈ **7.9 hours**
- Median: 252 × 300 s = 75,600 s ≈ **21 hours**
- Worst observed avg: 252 × 708 s = 178,416 s ≈ **49 hours**

**Mitigation strategy** during backfill window:

1. Rename existing `vdb_*.json` → `vdb_archive_*.json` (KEEP, do not delete).
2. Aliyun kb-api stays on QdrantVectorDBStorage with empty Qdrant collections + FTS5 fallback (already implemented per P2-3).
3. Background ingest_wechat re-ingest in chunks of 50 (WeChat throttle), expected ~10 batches over ~3 days realistic schedule.
4. Hermes + Databricks consume the LAST GOOD pre-cutover `vdb_archive_*.json` via existing rsync until first Path 2 snapshot lands.
5. Delete `vdb_archive_*.json` only after Aliyun Qdrant collection has count >= original article count AND verification query returns expected results.

PR #4's "delete vdb_*.json after re-ingest" step (`rm -f /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json`) should be **deferred 1+ weeks** for safety, not run immediately post-cutover.

### Q4: Qdrant docker on Aliyun resources

Aliyun current state: 4.3 GB used (kb-api 2.4 GB), 9.4 GB free, 4 GB swap (793 MB used).

Post-Qdrant projection:

- kb-api drops from 2.4 GB → ~0.5 GB (no NanoVectorDBStorage JSON load)
- batch_ingest drops from 10.9 GB → ~0.5 GB (per PR #4 prediction)
- Qdrant docker: ~1–2 GB at 80k vectors @ 3072d, mmap-backed (per [Qdrant docs](https://qdrant.tech/articles/memory-consumption/) "1.2 GB serves 1M vectors")
- System + ancillaries: ~1 GB
- **Total ~5 GB.** 9 GB headroom on a 14 GB box. Comfortable.

Disk:

- Delete vdb_*.json → +1.85 GB recovered
- Qdrant binary segments at 80k × 3072d ≈ 0.8–1.2 GB (more compact than JSON)
- **Net disk +0.6 to +1 GB recovered.** Currently 43 GB free → ample.

**No resource concerns for Qdrant on Aliyun.**

---

## Cross-deps surfaced

### Vs B execute (P2-3 Vertex Gemini reranker B)

- B already merged at HEAD `91b33f1` per session summary. No conflict point.
- Q2 above (Qdrant payload key compat with `apply_rerank_if_enabled`) is the only soft coupling — verify post-cutover.

### Re-ingest window strategy

Critical path: PR #4 deploy → Qdrant backfill (~8–24h) → Path 2 converter cron deploy → first vdb_*.json snapshot ships to Databricks/Hermes.

- During this window, Databricks + Hermes serve `vdb_archive_*.json` (last good pre-cutover snapshot).
- Aliyun kb-api will return FTS5-only / no-rerank degraded responses for queries hitting freshly-ingested but not-yet-converged Qdrant collections.
- Acceptable per user constraint that Databricks long_form is the "important" RAG path; Aliyun kb-api degrade for ~24h tolerable.

### Databricks deploy gate

Path 2 requires NO Databricks code change. Databricks keeps reading NanoVectorDBStorage. Only configuration change: `databricks-deploy/app.yaml` env doesn't change. Just need fresh vdb_*.json delivered via existing `scripts/sync_to_databricks.sh` step 7.

Path 3 requires Databricks code change: `kb/api.py` LightRAG init plumbs `vector_storage="QdrantVectorDBStorage"` + env. Coupled to PR #4 timing.

---

## Recommendation

**Path 2 (Aliyun dual-write via Qdrant snapshot → vdb_*.json converter cron).**

### Why

1. **Zero new attack surface** — Qdrant stays `127.0.0.1:6333` on Aliyun.
2. **Zero new latency on Databricks long_form** — Databricks keeps reading local NanoVectorDB JSON; no remote query penalty.
3. **Zero new reliability dependency** — Databricks isn't coupled to Aliyun uptime for read-traffic.
4. **Solves Aliyun OOM** — both kb-api and batch_ingest point at local Qdrant.
5. **Cleanly extends current architecture** — Aliyun → Databricks/Hermes data flow is already rsync-based; we're just replacing the upstream vdb_*.json producer.
6. **Reasonable LoC budget** — ~200 LoC converter + 1 systemd timer + 1 line in `scripts/sync_to_databricks.sh`.

### Risks

1. **Converter format drift** on LightRAG upgrade. Mitigation: pinned smoke test that round-trips a known fixture; CI fails if format changes.
2. **Snapshot staleness** for Databricks (6 h cadence floor). Acceptable per user constraint "Databricks is RAG read-only frontend, not real-time ingest".
3. **Re-ingest window 8–24 h.** Deferred-delete strategy for `vdb_archive_*.json` covers gap.
4. **Aliyun kb-api code path** — PR #4 ONLY patches `ingest_wechat.py:392`. **kb-api at `kb/api.py` ALSO instantiates LightRAG** and ALSO needs the `vector_storage="QdrantVectorDBStorage"` change. PR #4 is incomplete as currently written — it'll solve the ingest OOM but kb-api will continue loading vdb_*.json and contributing 2 GB+ to memory pressure (and on first ingest after PR #4, kb-api JSON view diverges from Qdrant truth).

### Rollback

1. Stop Path 2 cron timer.
2. `docker stop qdrant && docker rm qdrant`
3. Restore last good `vdb_*.json` from `vdb_archive_*.json`.
4. Revert `vector_storage="QdrantVectorDBStorage"` arg in `ingest_wechat.py` AND `kb/api.py`.
5. systemctl restart kb-api + ingest services.

Total rollback time: ~5 min. Low-risk.

---

## Hard finding to surface to orchestrator

**PR #4 is incomplete.** It only patches `ingest_wechat.py`. The Aliyun `kb-api` (`kb/api.py`) ALSO holds a LightRAG instance and ALSO loads vdb_*.json into memory (currently 2.4 GB RSS, of which ~2 GB is the JSON). Without patching kb/api.py too:

- Aliyun OOM is partially fixed (batch_ingest no longer 10.9 GB) but kb-api still 2.4 GB and growing as vdb_*.json grows.
- Worse: post-PR-4 ingest writes to Qdrant; kb-api reads stale vdb_*.json. **kb-api becomes wrong** — returns search results from a frozen-in-time vector DB while ingest moves on.

**This is a P0 blocker** for PR #4 as currently authored. Either:

- Extend PR #4 to also patch `kb/api.py` LightRAG init (likely +5 LoC, similar shape to ingest_wechat patch), OR
- Reject PR #4 as-is and request a v2 PR that covers both producers.

Not in this research's scope to make that decision — orchestrator should pick.

---

## Sources

- [LightRAG 1.4.16 qdrant_impl.py](file:///c:/Users/huxxha/Desktop/OmniGraph-Vault/venv/Lib/site-packages/lightrag/kg/qdrant_impl.py) (local venv, verified matches Aliyun pin)
- [qdrant-client GitHub README](https://github.com/qdrant/qdrant-client) — local mode `path=` parameter
- [qdrant-client local mode source](https://python-client.qdrant.tech/_modules/qdrant_client/local/qdrant_local) — portalocker SQLite lock
- [DeepWiki qdrant-client 2.2 local mode](https://deepwiki.com/qdrant/qdrant-client/2.2-local-mode) — exclusive lock confirmation
- [Qdrant memory consumption article](https://qdrant.tech/articles/memory-consumption/) — 1.2 GB / 1M vectors baseline
- [Qdrant snapshots tutorial](https://qdrant.tech/documentation/tutorials-operations/create-snapshot/) — for future server-mode export option
- Aliyun ECS prod state via `ssh aliyun-vitaclaw` (read-only diagnostic, no mutation)
