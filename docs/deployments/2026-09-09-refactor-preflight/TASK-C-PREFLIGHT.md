# Task C refactor preflight

**Observed:** 2026-09-09 14:58 UTC. Remote checks used `BatchMode=yes`, `ConnectTimeout=8`, hostname verification, and no more than two SSH commands per host. No environment file, runtime database, article content, service configuration, login state, or service state was changed.

## Gate result

**BLOCKED for global migration; not blocked for a new isolated PC namespace.** Old-to-new KG sync is failed, and the daily-ingest pre-start cleanup can delete `processing` documents while the pipeline only emits a best-effort busy warning. Those facts block neither construction of a fresh isolated PC runtime nor its single-article E2E after routing and isolation acceptance.

## Current topology

| Fact | Evidence | Migration implication |
| --- | --- | --- |
| `ack-node-2` is `iZj1imk39yc55iZ`; Caddy PID 3134716 runs `/etc/caddy/Caddyfile`; the systemd Caddy unit is inactive. | Remote hostname, ps, systemctl status caddy. | Treat Caddy as a shared manually launched process; do not restart, replace, or remove it during VitaX work. |
| Caddy's `http://47.117.244.253` site serves the VitaClaw health routes, static root `/opt/vitaclaw/control-plane/vitaclaw-site/dist`, VitaX `/kb/*` and `/omnigraph/embed`, and trial/assistant API routes. A separate `:80` block proxies management/control-plane routes. | `/etc/caddy/Caddyfile` lines 1-144, filtered only for route declarations. | **Retain the old cloud VM and its Caddy process for now.** VitaX migration must preserve path routing and coordinate with the control plane. |
| `ack-node-1` is `ack-node-2-kg`; `omni-kb-api` and `omni-mcp` are active. Its root disk has about 50 GB free and memory available about 4.5 GB. | Remote hostname, systemctl show, df, free. | It is a query node, not an ingestion target until synchronization and resource envelopes are accepted. |
| OHPC is `OH-Desktop`; about 811 GB disk and 12 GB memory are available. `hermes-gateway`, Playwright MCP, and both tunnels are active. | Remote hostname, df, free, user-service state. | PC has capacity, but its documented local happy path still needs credentials/provider access and an isolated runtime. |

## Verified blockers

### Sync

`omnigraph-kg-sync.service` on the old pipeline is currently `failed` (`exit-code`, last run 2026-09-09 02:30-02:31 CST). In the bounded log window: Sep 4, 5, 7, 8, and 9 each had three entity first-batch HTTP errors followed by a fatal chunk-0 abort. Sep 6 completed once.

The source [deploy/sync_kq_to_new.py](../../../deploy/sync_kq_to_new.py:1) copies only missing Qdrant point IDs and then SQLite after all collections succeed. It does not synchronize graphml, KV files, images, updates to an already-present ID, or deletions. The historical [scripts/sync-from-aliyun.sh](../../../scripts/sync-from-aliyun.sh:68) issue was an `if ! do_one_rsync; then code=$?` exit-status inversion in the separate old-to-Hermes pull path. The local worktree now contains the corrected `if do_one_rsync; then :; else code=$?; fi` form and an uncommitted offline regression test; it is **not production evidence** and remains pending normal review and release.

### Ingest pre-start cleanup and recovery contract

The active old-pipeline daily unit still executes `cleanup_stuck_docs.py --all-failed` as `ExecStartPre`; its latest successful pre-step took two seconds at 20:00 CST. The same day's journal aggregates six `start-pre operation timed out`, six TERM exits, and seven failed-result events over ten starts. Thus the timeout class remains real even though the currently running instance passed pre-start.

[scripts/cleanup_stuck_docs.py](../../../scripts/cleanup_stuck_docs.py:56) selects both `failed` and `processing` and calls `LightRAG.adelete_by_doc_id` once per candidate. Its busy detection only writes a warning when the status file changed within 60 seconds; it does not lock, skip, or serialize deletion. Removing it from `ExecStartPre` needs a replacement contract: preserve timeout rollback; distinguish a proven orphan from a live `processing` document; keep a bounded serialized operator path for failed residue; and prove no concurrent ingest can race cleanup.

The batch has narrower recovery mechanisms, but they do not make this deletion safe: [batch_ingest_from_spider.py](../../../batch_ingest_from_spider.py:426) rolls back its in-memory pending document after its own timeout and flushes a partial checkpoint; [ingest_wechat.py](../../../ingest_wechat.py:97) turns post-insert verification failure into a failed retry-pool row; completed checkpoint markers skip text ingest; and layer-2 all-NULL results receive a four-hour retry backoff. They cannot recover a `processing` document left by process death before in-memory rollback runs.

## Source-difference intake order

The 09-09 comparison plus a fresh hash sample puts these files ahead of any whole-tree copy. `batch_ingest_from_spider.py`, `ingest_wechat.py`, and `deploy/sync_kq_to_new.py` match old pipeline byte-for-byte; preserve them while the blockers are investigated.

| Function | First file set to triage |
| --- | --- |
| LLM / model routing | `lib/llm_router.py`, `lib/models.py`, `lib/llm_client.py` |
| Vision | `lib/vision_cascade.py`, `lib/llm_bailian.py`, `image_pipeline.py` |
| Embedding | `embed_server.py`, `lib/lightrag_embedding.py` |
| KB / query | `kb/export_knowledge_base.py`, `kb/services/synthesize.py`, `omnigraph_search/query.py`, `mcp_kg_server.py` |
| Synchronization | `deploy/sync_kq_to_new.py`, `deploy/macos/omnigraph-sync.sh` |

Old and new embedding checks each returned one 1024-dimensional vector. The old-pipeline Vision, LLM/model, embedding, and KB files differ from main; this is a functional triage queue, not a copy list.

## Isolated single-article E2E entry

The safest existing fixture route is [scripts/bench_ingest_fixture.py](../../../scripts/bench_ingest_fixture.py:1), with `test/fixtures/gpt55_article`; it avoids scraping but intentionally performs real `rag.ainsert`, query validation, and Vision work. The companion [scripts/probe_e2e_v3_2.py](../../../scripts/probe_e2e_v3_2.py:1) writes checkpoints under the configured runtime. This read-only assignment did not run either harness. A future isolated run is authorized in principle after the routing and isolation gates below are accepted; it must never target a shared runtime.

A future run needs a newly created isolated runtime/database/vector namespace, explicit non-production provider route, compatible 1024-d embedding endpoint, fixture dependencies, and a destructive-cleanup prohibition. [scripts/local_e2e.sh](../../../scripts/local_e2e.sh:1) is not a substitute: it sets a shared `.dev-runtime`, imports credential paths, and its documented full happy path may be blocked by provider reachability.

## Scope and limits

This report does not claim formal UAT, data freshness, successful model calls, or that no other Caddy/site deployment exists. No ingestion, cleanup, login, restart, deployment, or runtime-data read was performed.

## Reproducible evidence

- [deployment baseline](../VITAX_DEPLOYMENT_BASELINE.md)
- [pipeline detail](../2026-09-09/pipeline-detail.json)
- [pipeline timeout detail](../2026-09-09/pipeline-timeout-detail.json)
- [code comparison](../2026-09-09/code-comparison.json)
- [machine-readable summary](TASK-C-PREFLIGHT.json)
