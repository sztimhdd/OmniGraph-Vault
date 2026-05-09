# Roadmap: v3.5-Ingest-Refactor

**Milestone:** v3.5-Ingest-Refactor (parallel-track to v3.4 + Agentic-RAG-v1)
**Created:** 2026-05-07
**Phase prefix:** `ir-N` (avoids collision with v3.4 phases 19-22 and Agentic-RAG-v1 `ar-N`)
**Granularity:** Standard (4 phases for 30 v1 REQs)
**Coverage:** 30/30 requirements mapped

> **Locked design:** `.planning/PROJECT-v3.5-Ingest-Refactor.md` — 6 D-decisions
> + Layer 1 v0 prompt verbatim, treated as final, no re-derivation.
> **Cross-milestone contract:** `omnigraph_search.query.search(query_text, mode)`
> stays stable. Migration 006/007 are additive; existing rows untouched.

---

## Phase decomposition rationale

**Decomposition style chosen: layer-vertical, observation-gated.**

Three reasons drive the choice:

1. **Layer 1 and Layer 2 are independently spike-validated.** Layer 1 has a
   passing 30-article spike at `.scratch/layer1-validation-20260507-151608.md`
   (21 reject / 9 candidate / 0 误杀 / 0 漏放). Layer 2's prompt is unspiked.
   Splitting them lets ir-1 ship a real Layer 1 against the validated prompt,
   while ir-2 carries the cost of writing + spike-validating the Layer 2
   prompt without holding ir-1 hostage to that work.
2. **The 1-week observation window is non-overlapping with code work.**
   Phase ir-3 is observation-only (no code, no schema, just operator audit +
   metric collection). A separate phase makes the gating boundary explicit:
   ir-3 must pass before ir-4 cleanup runs; if observation flags issues, ir-4
   stays blocked indefinitely while ir-1/ir-2 fixes land.
3. **Cleanup is post-observation by design.** The `_classify_full_body` /
   `batch_classify_kol.py` deletions in LF-5 are irreversible (well, reversible
   via git revert, but operator-visible). They run only after observation
   confirms the new pipeline is healthy. Folding LF-5 into ir-2 would risk
   shipping deletions before the new path has 7 days of production data.

**Counter-rationale considered (vertical-slice MVP-first, like Agentic-RAG-v1):**
rejected because v3.5 has no risky integration question — the integration
points are already wired by Foundation Quick 260507-lai placeholders. The
question is solely "does the LLM-backed filter perform under real workload?"
which is a behavior/quality question, best answered by ir-1 → real-traffic
observation rather than by orchestrator-style scaffolding.

**Phase count: 4** — below 4 forces ir-3 (observation gate) to merge into ir-2
or ir-4, blurring the deploy-vs-cleanup boundary; above 4 creates artificial
splits between LF-1 and LF-3 wiring (which are tightly coupled).

---

## Phases

- [ ] **Phase ir-1: Real Layer 1 + KOL ingest wiring** — Replace placeholder `layer1_pre_filter` with Gemini Flash Lite call backed by validated v0 prompt; persist verdicts on `articles.layer1_*` / `rss_articles.layer1_*` columns; ingest loop calls real Layer 1 before scrape.
- [ ] **Phase ir-2: Real Layer 2 + full-body scoring** — Replace placeholder `layer2_full_body_score` with DeepSeek call; design + spike-validate the Layer 2 prompt; persist verdicts on `articles.layer2_*` / `rss_articles.layer2_*`; ingest loop calls real Layer 2 after scrape.
- [ ] **Phase ir-3: Production cutover + 1-week observation** — Hermes deploy (migrations 006 + 007 already applied via ir-1/ir-2 deploys); 7-day observation window; operator-audit 30-article sample; measure cost / reject rate / pass rate.
- [ ] **Phase ir-4: RSS integration + dead-code cleanup** — (optional, gated on ir-3 pass) Wire RSS path to same `lib/article_filter.py`; delete `_classify_full_body` / `batch_classify_kol.py`; migration 008 drops empty classifications tables.

---

## Phase Details

### Phase ir-1: Real Layer 1 + KOL ingest wiring

**Goal:** Replace `layer1_pre_filter` placeholder with a real Gemini Flash Lite call against the v0 prompt; persist verdicts on `articles.layer1_*` / `rss_articles.layer1_*`; ingest loop reads `layer1_verdict='candidate'` rows for scrape.
**Depends on:** Foundation Quick 260507-lai (placeholder interface contract). If 260507-lai has not shipped to `main` by ir-1 start, ir-1 absorbs its deliverables (4 V35-FOUND requirements).
**Requirements:** LF-1.1, LF-1.2, LF-1.3, LF-1.4, LF-1.5, LF-1.6, LF-1.7, LF-1.8, LF-1.9, LF-3.1, LF-3.4, LF-3.5, LF-3.6, LF-4.1 (14 REQs)
**Success Criteria** (what must be TRUE):

  1. `lib/article_filter.layer1_pre_filter(...)` makes a real Gemini Flash Lite call and returns 1:1 results for batches up to 30 (LF-1.1, LF-1.2, LF-1.3)
  2. Migration 006 applied; `articles` and `rss_articles` each carry the 4 layer1_* columns; existing rows have all four NULL (LF-1.6)
  3. Layer 1 v0 prompt text in `lib/article_filter.py` matches PROJECT § "Layer 1 v0 Prompt" verbatim; `prompt_version="layer1_v0_20260507"` (LF-1.4)
  4. `.dev-runtime` smoke run on a 30-article candidate batch produces a layer1_verdict for every row, reject rate falls in 50–70% (LF-1.9, LF-1.7)
  5. Failure-mode unit tests (LLM timeout, partial JSON, row-count mismatch) all GREEN; in each case all 30 rows in the batch end with `verdict=NULL` and the batch is re-evaluated next run (LF-1.5, LF-1.9)
  6. Ingest loop in `batch_ingest_from_spider.py` calls `layer1_pre_filter` on a candidate batch BEFORE scrape; rejects write `ingestions(status='skipped', reason='layer1_reject:<verdict.reason>')`; passes go to scrape (LF-3.1, LF-3.5)
  7. `_build_topic_filter_query` (or successor) selects WHERE `layer1_verdict IS NULL` for unscraped rows; `--topic-filter` and `--min-depth` CLI flags are silently ignored (LF-3.4, LF-3.6)
  8. `--dry-run --max-articles 5` smoke produces real Layer 1 calls + persistence but no scrape, no ainsert (LF-3.6)
  9. Hermes deploy runbook `.planning/phases/ir-1-*/HERMES-DEPLOY.md` complete: pull → migration 006 → cron edit/resume → smoke 5; rollback path documented (LF-4.1)

**Plans:** TBD
**T-shirt:** L (3-4 days)
**Notes:**

- LF-3.2, LF-3.3 (Layer 2 wiring) are deferred to ir-2 — ir-1 ships Layer 1 and leaves the Layer 2 placeholder still in place. Articles passing Layer 1 still pass through the placeholder Layer 2 (always-pass) and reach LightRAG; this is intentional, gives a half-step rollout.
- LF-1.6 migration 006 must precede first LF-1 unit test run; CI / local dev must apply 006 before pytest.
- Foundation Quick 260507-lai's `_build_topic_filter_query` rewrite (V35-FOUND-03 in its PLAN) already drops the classifications JOIN; ir-1 only needs to add the `layer1_verdict IS NULL` predicate.
- **Backlog warning — first cron resume after ir-1 deploy will hit a larger-than-normal candidate pool.** Verified 2026-05-07 via read-only SSH against `~/.hermes/cron/jobs.json`:
  - **Paused** (today 14:03–14:33 ADT, `enabled=false`, jobs still in registry — not removed): `daily-classify-kol`, `daily-enrich`, `rss-classify`, `daily-ingest`. Resume is a one-shot Hermes CLI flip (no recreate).
  - **Still scheduled and active** (continuing to produce data while the ingest pipeline is paused): `每日KOL扫描` (08:00 ADT daily, hits `articles` table), `KOL扫描前健康检查` (07:55 ADT daily), `rss-fetch` (06:00 ADT daily, hits `rss_articles` table), `daily-digest` (09:30 ADT daily — emits empty Telegram digest while `daily-ingest` is paused; expected, ignore).
  - **Implication for ir-1 deploy:** between v3.5 charter (2026-05-07 ~14:33 ADT) and ir-1 deploy day, KOL扫描 + rss-fetch will keep adding rows. The first cron run of resumed `daily-ingest` post-ir-1 will see `layer1_verdict IS NULL` on the entire backlog, not just one day's articles. Layer 1 batch count on day 1 will be `ceil(backlog_size / 30)` — at ~30–50 new articles/day across both sources, expect 5–15 batches × 8s wall-clock + Gemini Flash Lite quota cost on day 1, vs ~2–3 batches in steady state. ir-1 HERMES-DEPLOY.md should warn the operator about this and budget extra wall-clock for the first cron run.
  - **Implication for STATE doc accuracy:** the current STATE-v3.5 § "Current Hermes Operational State" describes the 3 paused crons as "Permanently removed" — that's a documentation drift. STATE patch is deferred until ir-1 Hermes deploy completes (one-shot patch with verified ground truth, per user direction).

---

### Phase ir-2: Real Layer 2 + full-body scoring

**Goal:** Replace `layer2_full_body_score` placeholder with a real DeepSeek call against a spike-validated v0 Layer 2 prompt; persist verdicts on `articles.layer2_*` / `rss_articles.layer2_*`; ingest loop calls Layer 2 between scrape and ainsert; only `layer2_verdict='ok'` rows reach LightRAG.
**Depends on:** Phase ir-1 (needs real Layer 1 in place; Layer 2 only sees rows that already passed Layer 1).
**Requirements:** LF-2.1, LF-2.2, LF-2.3, LF-2.4, LF-2.5, LF-2.6, LF-2.7, LF-2.8, LF-3.2, LF-3.3, LF-4.2 (11 REQs)
**Success Criteria** (what must be TRUE):

  1. Layer 2 prompt designed and spike-validated on a 20-article hand-curated set; spike report at `.scratch/layer2-validation-<ts>.md` shows zero 误杀 + zero 漏放 (LF-2.4)
  2. `lib/article_filter.layer2_full_body_score(...)` makes a real DeepSeek call; batches of 5–10 articles return 1:1 results (LF-2.1, LF-2.2, LF-2.3)
  3. Migration 007 applied; `articles` and `rss_articles` each carry the 4 layer2_* columns; existing rows NULL (LF-2.5)
  4. `.dev-runtime` smoke on 10 scraped articles produces a layer2_verdict for every row; the verdict semantics ("ok" vs "reject") match the spike report's manual labels (LF-2.7, LF-2.8)
  5. Failure-mode unit tests for Layer 2 GREEN: LLM timeout / partial JSON / row-count mismatch → all NULL, scrape result preserved (LF-2.6, LF-2.8)
  6. Ingest loop calls `layer2_full_body_score` AFTER scrape + atomic body persist, BEFORE LightRAG ainsert; "reject" rows write `ingestions(status='skipped', reason='layer2_reject:<verdict.reason>')` and never reach ainsert (LF-3.2, LF-3.3)
  7. `_build_topic_filter_query` for the Layer 2 stage selects `layer1_verdict='candidate' AND layer2_verdict IS NULL AND body IS NOT NULL` rows (LF-3.4 from ir-1, refined here)
  8. End-to-end `.dev-runtime` smoke: 5 fresh KOL URLs run Layer 1 → scrape → Layer 2 → ainsert; cost measured per article ≤ ¥0.05 (LF-2.4 spike report records this)
  9. Hermes deploy runbook `.planning/phases/ir-2-*/HERMES-DEPLOY.md` complete: migration 007 → smoke → resume cron (LF-4.2)

**Plans:** TBD
**T-shirt:** L (3-5 days; Layer 2 prompt design + spike adds variance)
**Notes:**

- The Layer 2 spike (LF-2.4) is the gating artifact for ir-2 wrap. Without a passing spike, ir-2 cannot close. Allow buffer for prompt iterations.
- `--dry-run` continues end-to-end through Layer 2 (real LLM calls + persistence, no scrape, no ainsert) — this is intentional per LF-3.6 ir-1 design.

---

### Phase ir-3: Production cutover + 1-week observation

**Goal:** Hermes runs the new pipeline in production cron for 7 consecutive days; operator-audit confirms zero 误杀; measured cost / reject rate / pass rate match success-criteria targets.
**Depends on:** Phase ir-2 (full pipeline must be live; both Layer 1 and Layer 2 making real LLM calls and persisting verdicts).
**Requirements:** LF-4.3 (1 REQ — observation criteria + audit)
**Success Criteria** (what must be TRUE):

  1. Hermes cron runs 7 consecutive days with zero failed runs; "failure" = run produced zero ingested articles when the candidate pool was non-empty (PROJECT § Success criteria #2)
  2. Observed Layer 1 reject rate per day falls in 50–70% band (PROJECT § #4); rates outside the band trigger investigation (prompt drift OR candidate-pool shift)
  3. Operator draws a 30-article sample uniformly from a real cron run on day 7; manual audit confirms zero 误杀 (PROJECT § #3)
  4. Measured monthly LLM cost extrapolated from 7-day window < ¥10/month (PROJECT § #1)
  5. End-to-end ingest pass rate (articles passing Layer 1 + Layer 2 that successfully reach LightRAG ainsert) ≥ 90% (PROJECT § #5)
  6. Daily observation entries logged in `.planning/phases/ir-3-*/OBSERVATION.md` with timestamp, cron run ID, candidate count, layer1 reject count, layer2 reject count, ainsert count, total LLM cost, anomalies (if any)

**Plans:** TBD
**T-shirt:** S (3 working days for setup + audit; 7 days wall-clock observation)
**Notes:**

- ir-3 has no code work — it is observation + audit. The phase plan is a checklist + an OBSERVATION.md scaffold.
- If any criterion fails on day N, ir-3 does NOT close — it remains open while a fix lands (treated as a regression on ir-1 or ir-2). The observation window restarts on day 0 from the day the fix lands.
- ir-4 cleanup is **gated** on ir-3 pass. Do not start ir-4 cleanup deletes while ir-3 is still observing.

---

### Phase ir-4: RSS integration + dead-code cleanup (optional)

**Goal:** Extend the same `lib/article_filter.py` to the RSS ingest path; delete the now-dead `_classify_full_body` family + `batch_classify_kol.py`; (optionally) drop the empty `classifications` + `rss_classifications` tables.
**Depends on:** Phase ir-3 (1-week observation must pass; cleanup is irreversible).
**Requirements:** LF-4.4, LF-5.1, LF-5.2, LF-5.3 (4 REQs)
**Success Criteria** (what must be TRUE):

  1. `rss_ingest.py` calls `layer1_pre_filter` and `layer2_full_body_score` on RSS rows; RSS path produces verdicts in the same `rss_articles.layer1_*` / `layer2_*` columns introduced by migrations 006/007 (LF-4.4)
  2. RSS smoke (5 fresh RSS URLs) produces end-to-end ingest with verdicts persisted; reject rate similar to KOL spike (LF-4.4)
  3. `grep -rn "_classify_full_body\|_call_deepseek_fullbody\|_build_fullbody_prompt" .` returns zero hits across `lib/` + repo-root `*.py` (LF-5.1)
  4. `batch_classify_kol.py` deleted; no caller remains (verified via grep) (LF-5.2)
  5. (Optional) Migration 008 applied: `classifications` + `rss_classifications` tables dropped. Idempotent — re-applying is a no-op. Gated behind `--include-classifications-drop` migration-runner flag (LF-5.3)
  6. All deletions land in **separate atomic commits** (one per LF-5 REQ) so any single deletion can be reverted without disturbing the others.

**Plans:** TBD
**T-shirt:** M (2-3 working days)
**Notes:**

- ir-4 is **optional** — if ir-3 observation is borderline (e.g. day-7 audit reveals one ambiguous false-negative), the milestone owner can defer ir-4 to a follow-up milestone and close v3.5 at ir-3 PASS.
- LF-5.3 (migration 008) is gated by an explicit flag; the migration runner refuses to apply it without `--include-classifications-drop` so an autonomous run can never accidentally drop the tables.
- If RSS integration (LF-4.4) reveals new edge cases (e.g. RSS articles with empty body), Phase ir-4 may extend. Allow time buffer.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
| ----- | -------------- | ------ | --------- |
| ir-1: Real Layer 1 + KOL wiring | 4/4 | DONE | 2026-05-07 |
| ir-2: Real Layer 2 + full-body scoring | 4/4 | DONE | 2026-05-07 |
| ir-3: Production cutover + 1-week observation | — | in progress (calendar wait) | (target ~2026-05-16) |
| ir-4: RSS integration + dead-code cleanup | 5/5 | code-complete on local main; awaiting user `继续` for push + Hermes deploy | 2026-05-09 |

---

## Coverage validation

**30/30 v1 requirements mapped, no orphans, no duplicates.**

| Phase | Count | REQs |
|-------|-------|------|
| ir-1 | 14 | LF-1.1, LF-1.2, LF-1.3, LF-1.4, LF-1.5, LF-1.6, LF-1.7, LF-1.8, LF-1.9, LF-3.1, LF-3.4, LF-3.5, LF-3.6, LF-4.1 |
| ir-2 | 11 | LF-2.1, LF-2.2, LF-2.3, LF-2.4, LF-2.5, LF-2.6, LF-2.7, LF-2.8, LF-3.2, LF-3.3, LF-4.2 |
| ir-3 | 1 | LF-4.3 |
| ir-4 | 4 | LF-4.4, LF-5.1, LF-5.2, LF-5.3 |
| **Total** | **30** | |

By category breakdown:

- LF-1 (9): ir-1 has all 9 ✓
- LF-2 (8): ir-2 has all 8 ✓
- LF-3 (6): ir-1 has 4 (3.1, 3.4, 3.5, 3.6), ir-2 has 2 (3.2, 3.3) ✓
- LF-4 (4): ir-1 has 1 (4.1), ir-2 has 1 (4.2), ir-3 has 1 (4.3), ir-4 has 1 (4.4) ✓
- LF-5 (3): ir-4 has all 3 ✓

---

## T-shirt effort estimates

| Phase | T-shirt | Reasoning |
|-------|---------|-----------|
| ir-1 | **L** (3-4 days) | 14 REQs but Layer 1 prompt is already validated by spike. Real work concentrated in (a) wiring `lib/vertex_gemini_complete` integration to JSON-strict response parsing, (b) migration 006 idempotency, (c) batch persistence transaction semantics, (d) Hermes deploy runbook. |
| ir-2 | **L** (3-5 days) | 11 REQs, but Layer 2 prompt requires fresh design + spike validation. Allow 1-2 days for prompt iteration. DeepSeek wiring reuses existing `lib/llm_deepseek.py`. |
| ir-3 | **S** (3 days setup + 7 days wall-clock) | No code work — observation + audit only. 7-day calendar window is the bottleneck, not engineering effort. |
| ir-4 | **M** (2-3 days) | LF-5.x deletions are mechanical. RSS wiring (LF-4.4) is the variance — may surface edge cases at scrape level (RSS feeds with HTML cruft) that need targeted handling. |

**Milestone total: ~9-12 working days, ~3 weeks wall-clock** (driven by the 7-day ir-3 window). Likely longer with operator-side coordination on Hermes deploys.

---

## Dependencies

- ir-1 depends on: Foundation Quick 260507-lai (placeholder shape). If Foundation Quick has not shipped to `main` by ir-1 start, ir-1 absorbs its 4 V35-FOUND requirements before LF-1 work begins.
- ir-2 depends on: ir-1 (real Layer 1 must filter the candidate pool before Layer 2 sees rows; otherwise Layer 2 spike is contaminated by off-topic articles).
- ir-3 depends on: ir-2 (full pipeline must be production-deployed before observation is meaningful).
- ir-4 depends on: ir-3 (cleanup deletions are irreversible; observation must pass first).

No phase-internal parallelism is recommended; phases are strictly sequential.

---

## Cross-phase touches

| REQ | First delivered | Touch-points |
|-----|----------------|--------------|
| LF-3.4 | ir-1 (`layer1_verdict IS NULL` predicate) | ir-2 refines to `layer1_verdict='candidate' AND layer2_verdict IS NULL AND body IS NOT NULL` |
| LF-3.5 | ir-1 (Layer 1 logging) | ir-2 adds `[layer2]` tag for Layer 2 log lines |
| LF-3.6 | ir-1 (Layer 1 dry-run) | ir-2 extends dry-run end-to-end through Layer 2 |
| `prompt_version` constants | ir-1 (`layer1_v0_20260507`) | ir-2 adds `layer2_v0_<ts>` constant |

---

## Open notes

- **Foundation Quick 260507-lai status uncertainty:** at charter time (2026-05-07) the Foundation Quick PLAN exists at `.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/260507-lai-PLAN.md` but the placeholder code has not yet shipped to `main`. ir-1 plan-phase must (a) check `git log --oneline | grep 260507-lai` to confirm shipping status, (b) absorb V35-FOUND-01..04 if not shipped, (c) treat the existing PLAN as the contract for the placeholder shape regardless.
  - **If absorb path is taken** (Foundation Quick not shipped): the ir-1 plan MUST sequence the work as **two task groups**:
    1. **Group A — placeholder ship** (V35-FOUND-01..04): create `lib/article_filter.py` with `FilterResult` + always-pass `layer1_pre_filter` / `layer2_full_body_score`; add interface-contract unit tests; bypass `_classify_full_body` in `batch_ingest_from_spider.py`; rewrite `_build_topic_filter_query` to drop the `classifications` JOIN. Exact deliverables verbatim from `260507-lai-PLAN.md` § "must_haves.truths".
    2. **Group B — Layer 1 real implementation** (LF-1.1..1.9 + LF-3.x): everything currently scoped in ir-1's success criteria.
  - **Group B success criteria are unchanged** (they assume the placeholder interface exists — Group A guarantees that).
  - **Group A success criteria are added on top**, lifted from `260507-lai-PLAN.md` § "must_haves.truths" verbatim:
    - SC-A1: `lib/article_filter.py` exposes `FilterResult` dataclass + `layer1_pre_filter()` + `layer2_full_body_score()` placeholder functions (always-pass).
    - SC-A2: `tests/unit/test_article_filter.py` — 7 contract tests pin placeholder interface; all GREEN.
    - SC-A3: `batch_ingest_from_spider.py` ingest loop calls layer1 BEFORE scrape and layer2 AFTER scrape; no longer calls `_classify_full_body`.
    - SC-A4: `_build_topic_filter_query` SELECT no longer joins `classifications` and no longer references `c.depth_score` / `c.topic`.
    - SC-A5: `--min-depth` / `--topic-filter` CLI flags retained for back-compat (silently ignored).
    - SC-A6: Dry-run smoke (`--dry-run --max-articles 1`) reaches layer1/layer2 placeholder code without crashing.
    - SC-A7: HERMES-DEPLOY runbook (placeholder cutover scope only — Group B's LF-4.1 runbook is separate) exists.
  - Group A → Group B is a hard sequence: Group B's LLM wiring assumes the placeholder shape from Group A is in place.
  - **If Foundation Quick HAS shipped before ir-1 starts** (skip absorb path): Group A is fully delivered upstream; ir-1 plan only writes Group B tasks; ir-1 success criteria stay at the 9 items already listed.
- **Parallel-track coordination with v3.4 (Phase 20-22) and Agentic-RAG-v1 (`ar-N`):** ir-1..ir-4 touch only `lib/article_filter.py`, `lib/llm_*.py` (read-only reuse), `batch_ingest_from_spider.py`, `rss_ingest.py` (ir-4), `migrations/`, `tests/unit/`, planning artifacts under `.planning/phases/ir-*`. Zero overlap with v3.4 Phases 20-22 or Agentic-RAG-v1 expected.
- **No research stage:** Per spike validation already done (`.scratch/layer1-validation-20260507-151608.md`) and locked design (`.planning/PROJECT-v3.5-Ingest-Refactor.md`), `/gsd:plan-phase ir-N` should jump from spec → planning → execute. No `gsd-project-researcher` agents.

---
*Roadmap created: 2026-05-07.*
*Last updated: 2026-05-07 — ir-1 Notes add backlog warning derived from SSH-verified Hermes cron registry (4 paused, 4 still active); STATE patch deferred to post-ir-1-deploy.*
