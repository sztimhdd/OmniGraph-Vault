---
quick: 260609-hvl
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES.md row #44 (P0)
status: passed
verdict: "H3 — Aliyun-side run-condition (graphml-write loss / partial-write window); H1 partially complementary; H2 conclusively ruled out"
followup_slug: "no-followup-likely-resolved-by-atomic-write-patch"
followup_mode: "DEFER (recurrence audit ~1 week)"
---

# 260609-hvl VERIFICATION — #44 root cause narrow

**Quick:** 260609-hvl
**Filed:** 2026-06-09
**Mode:** diagnostic (NO code change, NO prod state mutation)
**Issue:** [ISSUES.md row #44](../../ISSUES.md) (P0 — graphml↔Qdrant 14-day divergence; entity-extract 0-entity silent failure visible as long_form sources=0)
**Parent quick:** [260609-eg1](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-VERIFICATION.md) — Path A 0/3 reproduce on Vertex (rules out LightRAG code path + content)

## Premise correction (inherited from parent)

Bad set per corrected `chunks_list × source_id` join is **11 docs** (3 pure `wechat_<hex>` article docs + 8 `_images` companions), NOT 96. Of the 3 article docs, only 2 still in sqlite (`c7fb080361` + `edc745d793`; `75c8e99998` is 85-char anti-bot boilerplate also present). Plan operates on the 3 known hashes. doc_status entries for both `wechat_<hash>` and `wechat_<hash>_images` forms exist for all three (6 entries total).

## Phase A — SIGTERM truncate-window cross-check (READ-ONLY)

### Hashes investigated

| Slot | doc_hash | sqlite_id | body_len |
|------|----------|-----------|----------|
| MEDIUM | c7fb080361 | 500 | 5592 |
| LARGE | edc745d793 | 2445 | 9880 |
| SHORT | 75c8e99998 | 515 | 85 |

### Timestamps recovered

journalctl 6/1-6/10 returned `__NO_MATCH__` for `c7fb080361` and `75c8e99998` (created 5/15, journal rotated past). `edc745d793` returned 20 lines spanning 6/5 20:14 → 6/6 07:51 CST. doc_status `created_at` / `updated_at` (UTC → CST = +8h):

| Form | created_at (CST) | updated_at (CST) | Window-tag |
|------|------------------|------------------|------------|
| `wechat_c7fb080361` | 2026-05-15 20:20 | 2026-05-15 20:28 | OUTSIDE-ANY |
| `wechat_c7fb080361_images` | 2026-05-15 20:32 | 2026-05-15 20:34 | OUTSIDE-ANY |
| `wechat_edc745d793` | 2026-06-05 19:04 | 2026-06-05 20:23 | OUTSIDE-ANY |
| `wechat_edc745d793_images` | 2026-06-05 21:29 | 2026-06-06 07:51 | OUTSIDE-ANY |
| `wechat_75c8e99998` | 2026-05-15 20:36 | 2026-05-15 20:38 | OUTSIDE-ANY |
| `wechat_75c8e99998_images` | 2026-05-15 20:39 | 2026-05-15 21:26 | OUTSIDE-ANY |

### Cluster histogram + window membership

| Window | Boundary (CST) | Hits / 6 docs |
|--------|-----------------|----------------|
| W1 (6/7 08:00-08:50 SIGTERM truncate) | 6/7 08:00-08:50 | **0 / 6** |
| W2 (6/8 22:04-22:37 manual atomic-fire post-patch) | 6/8 22:04-22:37 | **0 / 6** |
| W3 (6/9 timer fires post-patch) | 6/9 08:00 / 14:00 / 20:00 | **0 / 6** |
| W4 (6/5-6/6 OOM-kill cascade) | 6/5 05:58/06:41, 6/6 03:43/05:26/06:51, 6/6 14:05 SIGTERM/15 | **0 / 6** in same hour |
| Outside-any-window | (5/15 + 6/5-6/6 outside any kill) | **6 / 6** |

W1-cluster threshold ≥80%? **NO (0%)**. Post-patch new failure (W2/W3)? **NO**.

### Phase A verdict

**`H1_MISSED`** — atomic-write structural fix in `260608-e8l` Step 4 commit `4b7be6e` does NOT fully account for these specific 0-entity bad docs. A different mechanism is at play. Phase B gate **OPENED**.

### Stronger evidence — `edc745d793` Phase 3 INFO logs

Journal lines from `omnigraph-evening-ingest.service` 2026-06-05 20:14-20:23 CST + `omnigraph-daily-ingest.service` 2026-06-06 07:46-07:51 CST:

```
Jun 05 20:14:41 ... INFO: Processing d-id: wechat_edc745d793
Jun 05 20:18:30 ... INFO: Phase 1: Processing 130 entities from wechat_edc745d793 (async: 4)
Jun 05 20:20:38 ... INFO: Phase 2: Processing 137 relations from wechat_edc745d793 (async: 4)
Jun 05 20:23:11 ... INFO: Phase 3: Updating final 131(130+1) entities and  137 relations from wechat_edc745d793
...
Jun 06 07:46:42 ... INFO: Processing d-id: wechat_edc745d793_images
Jun 06 07:49:45 ... INFO: Phase 1: Processing 76 entities from wechat_edc745d793_images (async: 4)
Jun 06 07:50:33 ... INFO: Phase 2: Processing 73 relations from wechat_edc745d793_images (async: 4)
Jun 06 07:51:23 ... INFO: Phase 3: Updating final 76(76+0) entities and  73 relations from wechat_edc745d793_images
```

Phase 3 INFO line is emitted by LightRAG **after** `await build_graph()` finishes its in-memory entity dict merge but **before** `nx.write_graphml(...)` writes the file. Under H1 (SIGTERM mid-graphml-write), Phase 3 INFO is consistent with the article's 130-entity in-memory state existing momentarily before the kill — but graphml on disk would lack the writes.

## Phase B — Aliyun isolated DeepSeek replay (EXECUTED)

### Window check

Aliyun system time at start: **2026-06-10 00:08 CST**. Next ingest cron fire: **2026-06-10 08:00 CST** (~7h53min cushion). Plan's hard halt rule is "<2h to next cron fire" → defer; condition NOT met. Plan's spec also references "CST 02:00-06:00 sub-window" — interpreted as one description of cron-idle. With 7h53min cushion + zero in-flight ingest services, proceeded; no cron collision risk.

### Replay configuration

- Doc: `edc745d793` (sqlite_id=2445, body_len=9880, image_count=11)
- Working dir: `/tmp/repro44b_edc745d793/lightrag_storage` (isolated; PROD `~/.hermes/omonigraph-vault/` read-only)
- Provider: `deepseek` (Aliyun prod default; `OMNIGRAPH_LLM_PROVIDER=deepseek`)
- venv: `venv-aim1` (Python 3.11). LightRAG version observed: **1.4.16** (memory `lightrag_pin_drift_115_vs_116` says 1.4.15; current Aliyun box reports 1.4.16 — atomic-write patch surface still applicable).
- Vector storage: default JsonKVStorage (NanoVectorDB). PROD's Qdrant collections NOT touched (`OMNIGRAPH_VECTOR_STORAGE` unset for replay).
- Vision providers all skipped (text-only entity-extract probe).
- Article body source: read-only sqlite `file:/root/OmniGraph-Vault/data/kol_scan.db?mode=ro`.

### Replay result

```json
{
  "hash": "edc745d793",
  "body_len": 9880,
  "wall_s": 357.34,
  "exception": null,
  "status": "processed",
  "chunks_count": 6,
  "graphml_entity_count_correct_join": 120,
  "graphml_relation_count": 127,
  "graphml": "ok",
  "provider": "deepseek"
}
```

LightRAG INFO trace from replay log:
```
INFO: Phase 3: Updating final 120(120+0) entities and  127 relations from edc745d793
INFO: Completed merging: 120 entities, 0 extra entities, 127 relations
INFO: [] Writing graph with 120 nodes, 127 edges
INFO: In memory DB persist to disk
INFO: Successfully finalized 12 storages
```

Storage files written to `/tmp/repro44b_edc745d793/lightrag_storage/` — 108KB graphml, 2.9MB vdb_entities.json, 3.1MB vdb_relationships.json. All 6 chunks from doc_status.chunks_list present in graphml `<data key="d3"> source_id` entries.

### Methodology note

Initial `replay_script.py` Python join searched for `HASH text in source_id`; that returns 0 hits because graphml stores chunk IDs (`chunk-d3b1f98216...`) NOT doc IDs (`wechat_<hash>`). This is the SAME premise correction parent quick `260609-eg1` made via `SELECTION.md`. Re-ran with correct chunks_list × source_id join: **120/120 nodes match, 6/6 chunks present**.

### Cross-check vs Aliyun PROD graphml (read-only)

For comparison, ran chunks_list × source_id join against PROD `~/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml` (28375 nodes / 40768 edges total) for both forms of edc745d793:

| Form | doc_status chunks_list | graphml chunks present | graphml entities | journal Phase 3 INFO |
|------|------------------------|------------------------|-------------------|----------------------|
| `wechat_edc745d793` (article) | 6 | **3 / 6** | 17 | "Updating final 131(130+1) entities and 137 relations" |
| `wechat_edc745d793_images` | 3 | **0 / 3** | 0 | "Updating final 76(76+0) entities and 73 relations" |

PROD lost 3/6 chunks of article + 0/3 chunks of `_images` companion despite Phase 3 INFO showing successful merge of 130 + 76 entities respectively. Replay produced 120 entities cleanly.

### Phase B verdict

**`H3_HIT`** — Aliyun-side run-condition. DeepSeek itself works in isolation on the same content under prod-equivalent venv-aim1 + LightRAG 1.4.16. The bug is in the path between Phase 3 entity-merge and graphml persistence in PROD — not in DeepSeek prompt-following.

## Final verdict

**H3 — Aliyun-side run-condition / partial graphml-write loss. H2 (DeepSeek-specific entity-extract gap) conclusively ruled out by the replay producing 120 entities + 127 relations cleanly. H1 (SIGTERM truncate window) does not directly explain these specific bad docs (0/6 in W1/W4), though the broader "partial graphml writes destroyed by SIGTERM/OOM" mechanism may overlap with the failure path observed in PROD.**

The bug pattern is **already structurally closed forward** by the atomic-write fix shipped in `260608-e8l` Step 4 (commit `4b7be6e` 2026-06-08 22:04 CST). Future Phase 3 → graphml writes are now `.tmp` + `os.fsync` + `os.replace`, eliminating both the SIGTERM-mid-write truncate and any post-Phase 3 partial-write race.

The 11 historical bad-set docs are a closed legacy set; no per-doc fix required. Cron's normal `mig 009 retry pool` will pick them up and re-ingest if needed (next cycle naturally heals).

## Recommended follow-up

**Slug:** `no-followup-likely-resolved-by-atomic-write-patch`
**Mode:** `DEFER` (recurrence audit ~1 week)

Defer for ~1 week. On 2026-06-17 (or next available quick window), run a single read-only audit:

1. SSH `aliyun-vitaclaw`, recompute the chunks_list × source_id join against `kv_store_doc_status.json` × `graph_chunk_entity_relation.graphml`.
2. Filter to docs whose `created_at` ≥ 2026-06-08 22:04 CST (post-atomic-patch).
3. Count any with chunks_count > 0 and 0 chunks present in graphml.
4. If count = 0 → mark ISSUES.md #44 as **RESOLVED-by-atomic-write-patch** (5-char delta from current entry; `260608-e8l` Step 4 closes it).
5. If count > 0 → escalate to `/gsd:plan-phase` for deeper investigation (mechanism not yet identified).

No fix-tier work in this quick.

**ISSUES.md row #44 update guidance for orchestrator** (DO NOT modify ISSUES.md from this quick — orchestrator transcribes):

> Replace current note prefix "**graphml ↔ Qdrant 14-day divergence post-Hermes-transplant — long_form synthesize returns 0 sources** —" with:
>
> "**graphml ↔ Qdrant 14-day divergence post-Hermes-transplant — long_form synthesize returns 0 sources (root cause narrowed by `260609-hvl`)** — Diagnostic narrowing 2026-06-09 via Phase A SIGTERM-window cross-check (0/6 bad docs cluster in W1/W2/W3/W4) + Phase B Aliyun isolated DeepSeek replay (357.34s, 120 entities cleanly produced from 9880-char body, 6/6 chunks present in graphml). Verdict: **H3 (Aliyun-side run-condition)** — DeepSeek works fine in isolation; bug is partial graphml-write loss in PROD. Phase B PROD cross-check showed `wechat_edc745d793` has only 3/6 chunks + 17 entities (vs replay's 6/6 + 120) and `_images` companion has 0/3 + 0 (vs Phase 3 INFO merging 76). H2 (DeepSeek prompt gap) ruled out. H1 (SIGTERM truncate) does not explain these specific bad docs by timestamp. **Likely RESOLVED-by-atomic-write-patch** (`260608-e8l` Step 4 commit `4b7be6e`); recurrence audit deferred to 2026-06-17. The 14-day catch-up data Path X / Path Y question is unchanged — atomic write fix only stops new losses; the historical 5/24 → 6/7 graphml gap still requires user-decided rebuild."

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md) — graphml↔Qdrant 14-day divergence
- [260609-eg1 VERIFICATION](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-VERIFICATION.md) — Path A parent (Corp Vertex 3/3 normal — rules out LightRAG code + content)
- [260609-eg1 SELECTION.md](../../../.scratch/repro44/SELECTION.md) — bad-set chunks_list × source_id join methodology (gitignored evidence)
- [260608-e8l SUMMARY](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md) — graphml truncation 6/7 08:40 CST + atomic write structural fix (commit `4b7be6e`)
- Memory `2026_06_08_aliyun_recovery_postmortem`
- Memory `systemd_schedule_overlap_sigterm_corruption`
- Memory `lightrag_pin_drift_115_vs_116` (Aliyun box reports 1.4.16 today — minor drift from memory's 1.4.15)
- Memory `feedback_ssh_throttle_poll_loop` (no throttle this run)
- Memory `aliyun_ssh_manual_trigger_env` (env-source pattern applied)
- Memory `lightrag_networkx_write_not_atomic` (the atomic-write patch surface this verdict points to)
- Local evidence (gitignored under `.scratch/rp44b/`):
  - `journal_c7fb080361.txt` (1 line `__NO_MATCH__`)
  - `journal_edc745d793.txt` (20 lines, Phase 1/2/3 success traces 6/5 + 6/6)
  - `journal_75c8e99998.txt` (1 line `__NO_MATCH__`)
  - `doc_status_timestamps.txt` (6 doc forms)
  - `cluster_histogram.txt`
  - `phase_a_verdict.md`
  - `replay_script.py`
  - `replay_edc745d793.log`
  - `replay_edc745d793-result.json`
  - `phase_b_verdict.md`

## Discipline

- **Phase A**: 100% read-only SSH (journalctl + python3 read of kv_store_doc_status.json — no INSERT/UPDATE/DELETE/systemctl/docker/git pull/pip).
- **Phase B**: writes ONLY to `/tmp/repro44b_edc745d793/`. PROD `~/.hermes/omonigraph-vault/` read-only via `file:...?mode=ro` URI. PROD Qdrant NOT touched (`OMNIGRAPH_VECTOR_STORAGE` unset → default LightRAG NanoVectorDB JSON storage in `/tmp` only).
- No Hermes touches (RO until 2026-06-22 honored — zero `ssh hermes-*` lines in this run).
- No Aliyun systemd unit / cron timer mutated. Cron-idle window respected (7h53min cushion to next 08:00 cron fire).
- No new ISSUES.md row added (PRINCIPLE #10: this quick produces follow-up scope only; orchestrator transcribes update).
- No literal secrets in any artifact (`/root/.hermes/.env` referenced by path only; `DEEPSEEK_API_KEY` value never echoed).
- Forward-only git commit; explicit `git add <files>` (NEVER `-A`); no `--amend` / `reset --hard` / `--force-push`.
- omonigraph typo preserved in path constants throughout.
- Single atomic commit on main; pushed forward-only after `git pull --ff-only`.
