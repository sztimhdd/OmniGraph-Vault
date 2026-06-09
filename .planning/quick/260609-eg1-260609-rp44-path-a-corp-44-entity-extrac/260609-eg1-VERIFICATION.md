---
quick: 260609-eg1
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES.md row #44 (P0)
status: passed
verdict: "DOES-NOT-REPRODUCE — 3/3 docs ingest cleanly with entities on Corp Vertex Gemini"
followup_slug: "260610-rp44b-deepseek-or-aliyun-side-investigation"
followup_mode: "/gsd:quick (read-only investigation)"
---

# 260609-eg1 VERIFICATION — #44 entity-extract 0-entity Path A reproduction

**Quick:** 260609-eg1
**Filed:** 2026-06-09
**Mode:** diagnostic (NO code change, NO prod state mutation)
**Issue:** [ISSUES.md row #44](../../ISSUES.md) (P0 — graphml↔Qdrant 14-day divergence; long_form 0 sources visible symptom)

## Premise correction (PLAN deviation tracked in SELECTION.md)

The PLAN.md cited "96 Aliyun docs" for the 0-entity bad set per ISSUES #44. **Actual count via correct chunks_list × source_id join: 11 processed docs**. Of those 11, only 3 are pure article docs (rest are `_images` companions); only 2 of those 3 still exist in sqlite. Bad-set distribution does NOT permit SHORT/MEDIUM/LONG selection. We ran 3 docs total — the 2 sqlite-present article docs plus 1 anti-bot-boilerplate row for evidence. See `.scratch/repro44/SELECTION.md` for the corrected query and audit trail.

## Environment

- Local LightRAG version: **1.4.15** (matches Aliyun prod per memory `lightrag_pin_drift_115_vs_116`)
- Atomic-write patch status: **mirrored from Aliyun then REVERTED** — Aliyun's patch (`os.fsync(fd)` after `os.O_RDONLY` open) is **Linux-specific** and raises `[Errno 9] Bad file descriptor` on Windows fsync of a read-only fd. Probe ran with vanilla LightRAG `nx.write_graphml(graph, file_name)` (no atomic guard); persistence verified post-run by graphml node count = 24 / 47 / 5. **NEW ISSUE surfaced** — patch needs Windows-compat fix before any future cross-platform LightRAG work; logged for follow-up (does NOT block this verdict, since #44 question is about content/provider behavior, not Windows fsync semantics).
- LLM provider: **vertex_gemini** (gemini-3.1-flash-lite-preview, GOOGLE_CLOUD_LOCATION=global, project=project-df08084f-6db8-4f04-be8)
- Vertex smoke pre-run: **PASS** ("ok" reply from `say ok` system prompt, response_len=2)
- Cert rebuild: **applied** (`.scratch/260525-rebuild-cacert.py`; pre-rebuild 119/0 corp → post-rebuild 123/4 corp; required because vanilla certifi failed `oauth2.googleapis.com` TLS handshake — known Cisco Umbrella MITM)
- Storage isolation: per-doc working_dir under `.dev-runtime/repro44/{hash}/lightrag_storage`
- Vision provider skip: `siliconflow,openrouter` (text-only ingest; no images involved in this probe regardless)

## Selected docs (from .scratch/repro44/SELECTION.md)

| Slot | doc_hash | sqlite_id | body_len | image_count | account_id |
|------|----------|-----------|----------|-------------|------------|
| MEDIUM | c7fb080361 | 500 | 5592 | 7 | 41 (Claude Code workbench article) |
| LARGE | edc745d793 | 2445 | 9880 | 11 | 5 |
| SHORT | 75c8e99998 | 515 | 85 | 4 | 41 (anti-bot boilerplate "环境异常") |

## Reproduction results

| Slot | wall_s | exception | doc_status | chunks_count | entity_count | graphml | outcome |
|------|--------|-----------|------------|--------------|--------------|---------|---------|
| MEDIUM (c7fb080361) | 84.2 | None | processed | 3 | **24** | ok | **NORMAL** (does not reproduce) |
| LARGE (edc745d793)  | 166.83 | None | processed | 6 | **47** | ok | **NORMAL** (does not reproduce) |
| SHORT (75c8e99998)  | 22.55 | None | processed | 1 | **5** | ok | **NORMAL** (does not reproduce) |

**Reproduction count: 0/3** (0 reproduce locally; all 3 produce entities cleanly)

## Sample LLM extraction evidence (from logs)

From `.scratch/repro44/c7fb080361.log` (chunk-by-chunk extraction trace; no LLM secrets in this excerpt):

```
INFO: Chunk 1 of 3 extracted 7 Ent + 6 Rel chunk-c12590505854af352986ea5d902eb5eb
INFO: Chunk 2 of 3 extracted 7 Ent + 6 Rel chunk-03b14581db5823e6e8fc384974343d02
INFO: Chunk 3 of 3 extracted 10 Ent + 8 Rel chunk-573f858e1bcbbadf94e0927cf40d50f1
INFO: Phase 1: Processing 23 entities from c7fb080361 (async: 8)
INFO: Phase 2: Processing 20 relations from c7fb080361 (async: 8)
INFO: Phase 3: Updating final 24(23+1) entities and  20 relations from c7fb080361
INFO: Completed merging: 23 entities, 1 extra entities, 20 relations
INFO: [] Writing graph with 24 nodes, 20 edges
```

From `.scratch/repro44/75c8e99998.log` (boilerplate body, 85 chars):

```
INFO: Chunk 1 of 1 extracted 5 Ent + 4 Rel chunk-b13ee97eb5901ed00b00847f79544a1e
INFO: Phase 3: Updating final 5(5+0) entities and  4 relations from 75c8e99998
INFO: [] Writing graph with 5 nodes, 4 edges
```

Even from the WeChat anti-bot "环境异常" stub, Vertex Gemini extracted 5 entities (likely "环境", "WeChat", "Video Mini Program", etc.) — entity-extraction is robust at the LLM layer.

## Verdict

**DOES NOT REPRODUCE — 0/3 (not 3/3, not mixed)**

All 3 docs from the actual Aliyun 0-entity bad set ingest cleanly through the local Corp Vertex Gemini pipeline, producing 24 / 47 / 5 entity nodes respectively. The same content that on Aliyun has 0 entities locally has substantial entity counts. This decisively maps onto the **DEEPSEEK-SPECIFIC-OR-ALIYUN-SIDE-CONDITIONS** verdict slot in the PLAN's matrix.

Per the plan's verdict→follow-up mapping, this means:

- The bug is **NOT** in LightRAG's code path or in the document content itself (otherwise both providers would reproduce)
- The bug is either **DeepSeek-specific** (entity-extract LLM behavior gap when DeepSeek receives entity-extract prompts) OR **Aliyun-side run-condition specific** (e.g., truncation during Hermes 5/24 transplant + 14-day Qdrant divergence per ISSUE #44, OR a particular OOM-kill window during ingest that left doc_status='processed' but graphml entries unwritten)

The N=3 evidence is genuinely insufficient to disambiguate between "DeepSeek prompt-following gap on these specific texts" and "Aliyun-side flush race / partial-write window during the 6/7 graphml truncation event". Both hypotheses survive.

## Recommended follow-up

**Slug:** `260610-rp44b-deepseek-or-aliyun-side-investigation`
**Mode:** `/gsd:quick` (read-only investigation; ≤2h budget)
**Rationale:** Narrow remaining hypotheses without committing to either of #44's expensive paths X / Y prematurely. Two short read-only probes:

1. **DeepSeek replay (read-only on Aliyun):** SSH Aliyun to a read-only `venv-aim1/python3 -c 'await rag.ainsert(<body>, ids=[hash])'` against a fresh isolated `working_dir=/tmp/repro44_<hash>`, with `OMNIGRAPH_LLM_PROVIDER=deepseek` (Aliyun's prod provider). If 0 entities reproduce → DeepSeek-specific (entity-extract LLM gap on this content). If entities produced → Aliyun-side run-condition issue (transplant gap or OOM window).
2. **Cross-check against the 6/7 SIGTERM graphml truncate window** (per `260608-e8l-SUMMARY.md`): inspect ingest journal lines around 6/7 08:40 CST for any of the 3 hashes. If they were in flight at SIGTERM, that's the smoking gun — the doc_status='processed' marker survived but the graphml write was killed mid-stream, leaving entities never persisted.

Either outcome dramatically reduces #44 path cost:
- DeepSeek-specific verdict → fix prompt-template fidelity for DeepSeek; defer Hermes batch to 2026-06-22 (PATH Y unchanged but more confident).
- Aliyun-side run-condition verdict → re-ingest only the 11-doc bad set on next nightly cron (free), much smaller than #44's "1-2 weeks of cron" Path X estimate.

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md) — long_form 0 sources visible symptom; 14-day graphml↔Qdrant divergence
- [260608-e8l SUMMARY.md](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md) — graphml truncation 6/7 08:40 CST, atomic write structural fix shipped
- Memory `graphml_qdrant_cross_version_divergence`
- Memory `lightrag_pin_drift_115_vs_116` (1.4.15 prod parity)
- Memory `lightrag_networkx_write_not_atomic` (atomic-write patch — has Windows-compat issue, surfaced this run)
- Memory `corp_pem_rebuild_pattern` (cert rebuild applied during pre-flight)
- Memory `vertex_ai_smoke_validated` (SA + endpoint matrix)
- This quick's evidence: `.scratch/repro44/SELECTION.md`, per-doc logs, per-doc result JSONs
