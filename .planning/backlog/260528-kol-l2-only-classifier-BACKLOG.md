# BACKLOG — KOL L2-only classifier

**Filed:** 2026-05-28
**Source:** quick `260528-mi6` (translate-completeness) — Phase 0C surfaced gap
**Status:** Standby — does NOT block v1.1

---

## Problem

`articles.layer2_verdict` for ~57 KOL rows on Aliyun prod is `NULL`. These
rows have:
- `layer1_verdict = 'candidate'`
- `body IS NOT NULL` (already scraped)
- `body_translated IS NULL` (translate cron's WHERE excludes them — needs L2='ok')

They render in the displayable pool (DATA-07 filter accepts L2 IS NULL) but
appear as Chinese-only cards on the bilingual SSG site, breaking the
ZH/EN toggle UX.

## Why no quick-fix path exists today

`articles.layer2_verdict` is **only** written by:
1. `batch_ingest_from_spider.py` via `lib/article_filter.py:persist_layer2_verdicts`
   — but this also runs scrape + LightRAG `ainsert()`, mutating the graph
   and contending for LightRAG locks with the production ingest timers
   (`omnigraph-{daily,afternoon,evening}-ingest.timer`).

There is **no** standalone "L2-only classifier" for KOL articles. RSS has
`batch_classify_rss_layer2.py` (idempotent, body-only) which serves as the
template for this backlog item. KOL was never given an equivalent because
the original v1.0 design assumed L2 always co-runs with scrape.

## Proposed solution

New script: `scripts/kol_layer2_classify_only.py` (~80 LoC)

Mirrors `batch_classify_rss_layer2.py` shape:
- SELECT `id, title, body, url` from `articles` WHERE
    `layer1_verdict='candidate' AND layer2_verdict IS NULL AND body IS NOT NULL`
- Reuse existing `lib/article_filter.run_layer2` + `persist_layer2_verdicts`
- LAYER2_BATCH_SIZE=5 (parity with RSS)
- No scrape, no LightRAG touch — pure DB write
- Idempotent (predicate excludes existing 'ok'/'reject' rows)

New systemd unit: `omnigraph-kol-layer2-classify.service` + `.timer`
- Schedule: `*-*-* 11:18:00 UTC` (between kol-classify @ 11:15 and rss-l2 @ 11:20)
- `EnvironmentFile=/root/.hermes/.env`
- `Persistent=true`

Tests: ≥3 unit tests in `tests/unit/` mirroring `test_translate.py` pattern
(in-memory schema + mocked `run_layer2`).

## Boundary vs `omnigraph-kol-classify.service`

| Service | Reads | Writes | LLM cost |
|---------|-------|--------|----------|
| `omnigraph-kol-classify.service` (existing) | KOL `articles` (title+digest) | `classifications` table (topic+depth_score) | DeepSeek L1-equivalent topic tag (~$0.02/run) |
| `omnigraph-kol-layer2-classify.service` (NEW) | KOL `articles` (title+body, where `layer1_verdict='candidate' AND layer2_verdict IS NULL`) | `articles.layer2_*` (4 cols) | Vertex Gemini Flash L2 (~$0.30/57 rows initial backfill) |

Different tables, different stages, different LLM endpoints — no overlap.
Existing `kol-classify.service` is **not** replaced or modified.

## Trigger conditions to revisit

1. BL-1 (260528-mi6) shipped to prod and verified
2. User explicitly confirms KOL L2 backfill is desired (cost ~$0.30 initial,
   then ~$0.005/day steady-state for new candidates)
3. v1.1 P5 (or whichever current milestone) does NOT depend on
   layer2_verdict being filled for displayability — confirmed: DATA-07 filter
   accepts `layer2_verdict IS NULL` so card visibility is already handled

## Estimate

| Step | Wallclock | Cost |
|------|-----------|------|
| Implementation + tests | 60-90 min | 0 |
| Code review + commit + push | 15 min | 0 |
| Aliyun pull + service install | 15 min | 0 |
| Initial 57-row backfill run | 15-30 min | ~$0.30 |
| Re-bake SSG + Databricks deploy | 60 min | 0 |
| Steady-state daily (per timer fire) | 1-3 min | ~$0.005 |
| **Total first-run** | **~3 hours** | **~$0.30** |

## Does NOT block

- v1.1 KB phases — KOL L2-NULL rows already render via DATA-07; only the
  bilingual EN-card population is degraded. v1.1 P5 / P6 / etc do not
  require this filled.
- aim-3 systemd timers cutover — already LIVE, this is additive.
- Translate cron (260528-mi6 BL-1 fix) — independent; this backlog only
  unlocks the body-translate pipeline FOR rows that L2 confirms as 'ok'.

## Cross-refs

- BL-1 PLAN: `.planning/quick/260528-mi6-260528-translate-completeness/260528-mi6-PLAN.md`
- Recon: `.scratch/260528-translate-completeness-recon-1912.md`
- RSS L2 template: `batch_classify_rss_layer2.py` (already in repo)
- L2 verdict persister: `lib/article_filter.py:816 persist_layer2_verdicts`
