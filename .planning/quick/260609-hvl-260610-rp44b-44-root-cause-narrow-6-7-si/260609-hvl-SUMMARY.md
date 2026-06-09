---
quick: 260609-hvl
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES #44 (P0)
verdict: "H3 — Aliyun-side run-condition (graphml-write loss); H2 ruled out by clean DeepSeek replay; H1 not directly hit by the 6 bad-doc timestamps"
followup_slug: "no-followup-likely-resolved-by-atomic-write-patch"
---

# Quick 260609-hvl — SUMMARY

Diagnostic-only quick. Goal: narrow ISSUE #44 root cause (graphml↔Qdrant 14-day divergence; long_form sources=0) to ONE of three hypotheses (H1 SIGTERM truncate / H2 DeepSeek-specific / H3 Aliyun-side run-condition) after parent quick `260609-eg1` ruled out LightRAG code path + content (Corp Vertex 0/3 reproduce, all 3 docs cleanly produced 24/47/5 entities).

## Outcome

**H3 hit.** DeepSeek-on-Aliyun cleanly extracted 120 entities + 127 relations from `edc745d793`'s 9880-char body in 357.34s under prod-equivalent venv-aim1 + LightRAG 1.4.16 + isolated working_dir. The bug is **NOT** a DeepSeek prompt gap — it's an Aliyun-side run-condition between Phase 3 entity-merge and graphml persistence. The atomic-write fix shipped in `260608-e8l` Step 4 (commit `4b7be6e`) likely closes this forward; recurrence audit deferred 1 week to 2026-06-17.

## Phase summary

- **Phase A** (SIGTERM cross-check, ~10 min, READ-ONLY SSH):
  - 0/6 bad docs cluster in W1 (6/7 truncate), W2 (6/8 atomic-fire), W3 (6/9 timer), or W4 (6/5-6/6 OOM-kill cascade hour-buckets).
  - Strongest single signal: `edc745d793` ingested 6/5 20:14-20:23 CST and 6/6 07:46-07:51 CST with explicit Phase 1/2/3 INFO success traces (130 ent + 137 rel article; 76 ent + 73 rel `_images`) — but PROD graphml has only 17 entities for the article (3/6 chunks) + 0 entities for `_images` (0/3 chunks).
  - Verdict: `H1_MISSED` → Phase B gate opened.

- **Phase B** (Aliyun isolated DeepSeek replay, ~7 min, write-isolated to `/tmp/repro44b_<hash>/`):
  - Window: 2026-06-10 00:08 CST (~7h53min until next 08:00 cron fire). No cron collision.
  - Replay produced **120 entities + 127 relations** from `edc745d793` body via DeepSeek under venv-aim1 + LightRAG 1.4.16. Wall 357.34s. status='processed'. 6/6 chunks present in graphml `<data key="d3"> source_id`.
  - Initial entity-count check returned 0 because of search-strategy artifact (searched `wechat_<hash>` text in source_id; graphml stores chunk IDs `chunk-<hash>`). Same premise correction parent quick made via `SELECTION.md`. Post-correction: 120/120 nodes match.
  - Cross-check vs PROD graphml: article 3/6 chunks + 17 entities; `_images` 0/3 chunks + 0 entities. Replay extraction was clean — gap is selective graphml-write loss in PROD.
  - Verdict: `H3_HIT`.

## Premise correction

(Inherited from parent quick `260609-eg1`.) Bad set is **11 docs** (3 article + 8 `_images`), NOT 96. Of 3 article docs, only 2 present in sqlite. doc_status entries exist for both `wechat_<hash>` and `wechat_<hash>_images` forms = 6 entries.

## Recommended follow-up

**Slug:** `no-followup-likely-resolved-by-atomic-write-patch`
**Mode:** `DEFER` (1-week recurrence audit on 2026-06-17)

Atomic-write fix (`260608-e8l` Step 4 commit `4b7be6e`) closed the structural failure mode. Run a single read-only audit on 2026-06-17 — recompute chunks_list × source_id join filtered to docs created post-2026-06-08 22:04 CST. If zero new bad-set members → mark ISSUES.md #44 RESOLVED-by-atomic-write-patch. If non-zero → escalate to `/gsd:plan-phase`.

The 14-day catch-up data question (Path X cron rebuild vs Path Y Hermes batch ingest) is **unchanged** by this verdict — atomic write only stops new losses. The historical 5/24 → 6/7 graphml gap still requires user-decided rebuild.

## ISSUES.md #44 row update guidance for orchestrator

> Append to current "Notes" cell (do NOT replace existing context):
>
> "**Diagnostic narrowing 2026-06-09 via `260609-hvl`:** Phase A SIGTERM-window cross-check (0/6 bad docs cluster in W1/W2/W3/W4) + Phase B Aliyun isolated DeepSeek replay (357.34s, 120 entities + 127 relations cleanly produced from 9880-char body, 6/6 chunks present in graphml). Verdict: **H3 (Aliyun-side run-condition; partial graphml-write loss)** — DeepSeek works fine in isolation; H2 ruled out. PROD cross-check confirmed loss pattern: `wechat_edc745d793` 3/6 chunks + 17 entities (vs replay 6/6 + 120); `_images` form 0/3 + 0 (vs Phase 3 INFO 76). Likely RESOLVED-by-atomic-write-patch (`4b7be6e`); recurrence audit deferred 2026-06-17."

## Discipline checklist

- [x] No production source change (`batch_ingest_from_spider.py`, `ingest_wechat.py`, `kb/`, `lib/`, `config.py` untouched)
- [x] No LightRAG fork (no `pip install --force-reinstall lightrag`; atomic-write patch in venv-aim1 NOT modified)
- [x] No Hermes touches (RO until 2026-06-22 honored)
- [x] No Aliyun prod state mutation — Phase A 100% read-only SSH; Phase B writes only to `/tmp/repro44b_edc745d793/`
- [x] PROD Qdrant NOT touched (`OMNIGRAPH_VECTOR_STORAGE` unset for replay → default LightRAG NanoVectorDB JSON storage in `/tmp` only)
- [x] No Aliyun cron collision — 7h53min cushion to next 08:00 CST fire
- [x] No Corp DeepSeek call — Aliyun-side only via SSH-wrapped python; Cisco Umbrella block honored
- [x] No literal secrets in any committed artifact — `/root/.hermes/.env` referenced by path only; DEEPSEEK_API_KEY value never echoed
- [x] Forward-only commit; explicit `git add <files>` (NEVER `-A`)
- [x] No `--amend` / `reset --hard` / `--force-push` per `feedback_no_amend_in_concurrent_quicks`
- [x] omonigraph typo preserved in path constants throughout
- [x] No new ISSUES.md row added (PRINCIPLE #10 — orchestrator curates; this quick produces follow-up scope only)

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md)
- [260609-eg1 SUMMARY](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-SUMMARY.md) (parent — Corp Vertex Path A 0/3 reproduce)
- [260608-e8l SUMMARY](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md) (atomic-write structural fix)
- Local evidence under `.scratch/rp44b/` (gitignored): journal greps, doc_status timestamps, cluster histogram, Phase A verdict, replay script + log + result JSON, Phase B verdict.

## Wall-clock

~30 min total. Phase A SSH grep + doc_status read + cluster: ~10 min. Phase B isolated replay 357.34s wall = ~6 min plus setup + post-replay PROD cross-check + verdict write: ~10 min. VERIFICATION + SUMMARY: ~10 min.
