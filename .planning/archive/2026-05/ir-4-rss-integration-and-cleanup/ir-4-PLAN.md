# Phase ir-4 — RSS integration into batch ingest + legacy pipeline cleanup

**Milestone:** v3.5-Ingest-Refactor
**Wave structure:** W0 audit (no commit) → W1..W4 atomic commits → W5 close-out
**Started:** 2026-05-08 evening (local Windows session)
**Code-complete:** 2026-05-09 (W4 commit `9ff330d`)
**Status:** code on local main; **not pushed to origin/main yet** — single push at W5
close-out per atomic-forward-only principle. Hermes deploy gated on user `继续`.

## Context

ir-1 (commit `f1a963b`) and ir-2 (commit `f8e90ef`) shipped real Layer 1 +
Layer 2 inside `lib.article_filter`, wired into KOL only. The dual-source
candidate SQL was deferred; RSS still flowed through the legacy
`enrichment/rss_classify.py` (DeepSeek per-article classify) and
`enrichment/rss_ingest.py` (translate → ainsert). Two pipelines, two cron
jobs, two failure modes. ir-4 unifies the RSS path into the same
`batch_ingest_from_spider --from-db` invocation that handles KOL.

## Scope deviation from REQUIREMENTS-v3.5-Ingest-Refactor.md

The original REQUIREMENTS doc scoped ir-4 with these 4 REQs:

- **LF-4.4** (RSS integration): "Adds `rss_ingest.py` wiring to
  `layer1_pre_filter` + `layer2_full_body_score`" — **kept**, but the
  implementation diverges: rather than wiring the legacy
  `enrichment/rss_ingest.py` to the placeholders, the dual-source candidate
  SQL inside `batch_ingest_from_spider --from-db` now pulls RSS rows into
  the same Layer 1/2 + scrape + persist + ainsert pipeline as KOL. The
  legacy RSS scripts become redundant and are retired (W3 + W4).
- **LF-5.1** (as written): "Delete `_classify_full_body`,
  `_call_deepseek_fullbody`, `_build_fullbody_prompt` from
  `batch_ingest_from_spider.py`" — **deferred** (out of W3/W4 scope; these
  functions are still called from KOL graded-classify path).
- **LF-5.2** (as written): "Delete `batch_classify_kol.py` entirely" —
  **deferred** (file is still the entrypoint for the daily-classify-kol
  cron at "15 8 * * *"; would require coordinated cron-removal first).
- **LF-5.3** (as written): "Migration 008: DROP TABLE classifications;
  DROP TABLE rss_classifications" — **deferred** (REQ explicitly marks
  "optional, run only after operator confirms no consumer reads these
  tables for 7 days post-cleanup").

**Effective ir-4 cleanup track (per user prompt 2026-05-08 evening):**

- **Retire `enrichment/rss_classify.py`** (W3) — the file was the legacy
  DeepSeek-only RSS classifier. The 06:00 ADT `rss-classify` cron and the
  step_2_classify_rss orchestrator step go with it.
- **Retire `enrichment/rss_ingest.py`** (W4) — the file was the legacy RSS
  ingest pipeline. step_7_ingest_all collapses from two parallel sub-commands
  into a single dual-source invocation.

Both retired files are direct duplicates of work now done by `lib.article_filter`
+ `batch_ingest_from_spider --from-db`. The original LF-5.1/5.2 deletions
remain pending and may be picked up in a follow-up cleanup phase.

## REQ coverage (as executed)

| REQ | Wave | Status | Commit | Notes |
|---|---|---|---|---|
| LF-4.4 | W1 + W2 | DONE | `5d943f8` + `df495c8` | Dual-source UNION ALL + dispatch helpers + auto-route |
| LF-5.1 (REQ-text) | — | **deferred** | — | KOL graded-classify still uses these functions; out of ir-4 scope |
| LF-5.1 (effective) | W4 | DONE | `9ff330d` | `enrichment/rss_ingest.py` deleted; step_7 + harness unified |
| LF-5.2 (REQ-text) | — | **deferred** | — | `batch_classify_kol.py` still has live cron caller; out of ir-4 scope |
| LF-5.2 (effective) | W3 | DONE | `4cc3757` | `enrichment/rss_classify.py` deleted; step_2 + cron registration removed |
| LF-5.3 | — | **deferred** | — | `classifications` table drop is post-observation operator decision |

## Wave manifest

| Wave | Plan file | Commit | Description |
|---|---|---|---|
| W0 | `ir-4-00-PLAN.md` | (audit only — no commit) | Pre-flight audit of feeds table name, layer2 col presence, persist function source-awareness, scrape_url public API. Report at `.scratch/ir-4-w0-preflight-20260508-175008.md` |
| W1 | `ir-4-01-PLAN.md` | `5d943f8` | migration 008 ingestions dual-source rebuild + `_build_topic_filter_query` UNION ALL + ingest_from_db consumer 7-col unpack + 24+13 new tests |
| W2 | `ir-4-02-PLAN.md` | `df495c8` | `_needs_scrape` helper + `_persist_scraped_body` source dispatch + scrape_url auto-route + 16 new dispatch tests |
| W3 | `ir-4-03-PLAN.md` | `4cc3757` | Retire `enrichment/rss_classify.py` + step_2 + rss-classify cron registration + grep verify (-774 lines) |
| W4 | `ir-4-04-PLAN.md` | `9ff330d` | Retire `enrichment/rss_ingest.py` + step_7 unification + harness rss mode hint + grep verify (-886 lines) |
| W5 | `CLOSURE.md` | (this commit) | Close-out: PLAN dir + HERMES-DEPLOY runbook + STATE/ROADMAP update |

Net delta across W1..W4: **+1062 / -944 lines = -882 lines after W1's migration + tests added**.

## Gate evidence chain (.scratch/, gitignored)

- W0 audit: `.scratch/ir-4-w0-preflight-20260508-175008.md`
- Migration 007 local catch-up: `.scratch/ir-4-w1-mig007-local.log`
- W1 G1 migration 008 idempotency: `.scratch/ir-4-w1-mig008-1st.log`,
  `.scratch/ir-4-w1-mig008-2nd.log`, `.scratch/ir-4-w1-integrity.log`
- W1 G2 dual-source SQL: `.scratch/ir-4-w1-dualsql.log`
- W1 G3 pytest: `.scratch/ir-4-w1-pytest-w1tests.log`
- W1 G4 harness smoke: `.scratch/ir-4-w1-kol-dryrun.log`
- W2 pytest: `.scratch/ir-4-w2-pytest.log`
- W2 harness regression: `.scratch/ir-4-w2-kol-dryrun.log`
- W3 pytest: `.scratch/ir-4-w3-pytest.log`
- W3 harness regression: `.scratch/ir-4-w3-kol-dryrun.log`
- W4 pytest: `.scratch/ir-4-w4-pytest.log`
- W4 harness rss-mode hint + kol regression: `.scratch/ir-4-w4-rss-mode.log`,
  `.scratch/local-e2e-kol-20260509-103557.log`

## STOP gates honored

- After W0: STOP, user reviewed audit + answered 4 open questions, batch'd "继续" → W1.
- After W1: STOP, user verified `git log` + diff stat + 37/37 tests + 1749 candidates + 4 deviations rust-but-verify'd, batch'd "继续" → W2.
- W2/W3/W4: continued without per-wave STOP per user's W1 ack ("4 deviations all ack'd, 继续").
- After W5 close-out (this commit): **STOP** — user triggers Hermes deploy via `HERMES-DEPLOY-ir-4.md` operator steps.

## Out-of-scope (not touched in ir-4)

- 5 LightRAG sites scoped to v3.6 (kg_synthesize / multimodal_ingest /
  query_lightrag / omnigraph_search / ingest_github)
- Layer 2 LLM provider (LF-2.3 contract pin DeepSeek)
- Migration 008 NOT attempted to drop `classifications` /
  `rss_classifications` tables (LF-5.3 deferred per REQUIREMENTS)
- Production Hermes cron jobs.json (operator side, applied per HERMES-DEPLOY-ir-4.md)
- ir-3's 7-day observation window (calendar wait, not code work)
