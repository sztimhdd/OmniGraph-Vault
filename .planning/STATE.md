# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-27)

**Core value:** Local, graph-based personal knowledge base that gives Hermes/OpenClaw persistent memory — WeChat scan → classify → LightRAG ingest → synthesis.
**Current focus:** Phase 4 — knowledge-enrichment-zhihu

## Current Position

Phase: 4 of 4 (knowledge-enrichment-zhihu)
Plan: 7 of 8 in current phase (04-00, 04-01, 04-02, 04-03, 04-04, 04-05, 04-06 complete; next 04-07 ingest_wechat integration)
Status: In progress — Wave 4 complete (04-06 enrich_article top-level skill, Hermes discovery confirmed)
Last activity: 2026-04-27 — Wave 4 complete (04-06 enrich_article SKILL.md + README.md, deployed + discovered on remote)

Progress: [████████░░] ~87.5% (7 of 8 plans complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~55 min (range: ~25 min for 04-01 to ~2h for 04-00 with checkpoint)
- Total execution time: ~3h

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 4 | 3/8 | ~3h | ~55 min |

**Recent Trend:**
- Last 5 plans: 04-00 (~2h, checkpoint), 04-01 (~25 min, TDD), 04-05 (~25 min, markdown skill), 04-02 (~15 min), 04-03 (~25 min), 04-04 (~5 min)
- Trend: Improving — Wave 3 plan executed extremely fast (~5 min TDD)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table and `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md`.
Recent decisions affecting current work:

- Phase 4: 16 locked decisions captured in 04-CONTEXT.md (D-01 through D-16)
- Phase 4: Hermes review integrated 2026-04-27 — Draft.js input method, grounding fallback, URL capture, zhimg sizing
- 04-00: Orchestrator captured golden fixtures via SSH (human-action checkpoint); all 3 remote articles had metadata.images==2, captured all 3 (acceptance criteria met)
- 04-00: LightRAG spike script created locally; remote execution is the Wave 1 gate (phase0_spike_report.md) — pending at time of this STATE update
- 04-01: TDD-first refactor; image_pipeline.py exports 4 public functions; ingest_wechat.py had two orphans cleaned (removed `from PIL import Image` and a stale `describe_image()` call in `ingest_pdf`)
- 04-05: Pure-Markdown Hermes skill (D-02); task 5.3 remote connectivity smoke-test passed; full E2E skill invocation deferred (requires interactive Hermes session after deploy)
- 04-06: enrich_article top-level skill (D-01/D-02); 208-line SKILL.md with 4-step orchestration + per-question for-loop; deployed via scp (remote has untracked zhihu-haowen-enrich blocking git checkout); `hermes skills list` confirmed `enrich_article | local | local | enabled`

### Pending Todos

None tracked.

### Blockers/Concerns

- Phase 4 runtime depends on remote Edge CDP (`localhost:9223`) being available for Zhihu fetch integration tests; integration tests in wave 2+ may be stubbed until a live CDP is reachable.
- **Gemini free-tier 20-RPM burst on `flash-lite`**: LightRAG default launches 4 parallel workers × ~2-5 chunks per doc = instant quota saturation. Environmental, not a phase-4 bug. Sequential-worker mode (`llm_model_max_async=1`) would fix but is out of phase-4 scope.
- **SQLite migration deployment gap (ACTION REQUIRED for 04-07)**: 04-00's `_ensure_column` migration only runs when `batch_scan_kol.init_db()` is called. The live `~/OmniGraph-Vault/data/kol_scan.db` had no `enriched` column until the orchestrator manually ran `init_db()` during Wave 3 validation. 04-07 must formalize this as either (a) an auto-migrate on `ingest_wechat.py` startup or (b) a documented `python -c "from batch_scan_kol import init_db; init_db(path)"` deploy step in README.
- **Spike script async race (non-blocking)**: `scripts/phase0_delete_spike.py` doesn't await LightRAG's async entity extraction before measuring counts — its report contract passes but entity counts are vacuous. Documented in `phase0_spike_report.md`. Not blocking; ticketable refactor later.

## Waiting / Blocked On

**Wave 4 E2E test by user**: `docs/testing/04-06-enrich_article-manual-test.md` (on branch `gsd/phase-04`, pushed to `origin/gsd/phase-04` as of commit `4f0aa5c`). User runs this on the remote Hermes PC via interactive `hermes agent` session — drives the full `enrich_article` orchestration (extract_questions → zhihu-haowen-enrich × N → fetch_zhihu × N → merge_and_ingest).

Expected outcomes from that test (fills gaps SSH can't cover):
- D-13 Telegram login-recovery fallback actually fires and works
- Per-question for-loop is correctly executed by the Hermes agent (not mis-skipping questions)
- CDP → Zhihu → image filter → Vision → LightRAG full pipeline end-to-end on one real article
- Acceptance checklist in §4 of the test guide

When user returns with results:
- If PASS: proceed to Wave 5 (04-07) — and ensure 04-07 closes the SQLite-migration deployment gap listed above.
- If FAIL with 04-06 defects: fix `skills/enrich_article/` on `gsd/phase-04`, redeploy, retest.
- If FAIL with upstream defects (e.g., 04-05 D-13 broken): open gap-closure plan, fix, retest.

## Session Continuity

Last session: 2026-04-27
Stopped at: Wave 4 complete on `gsd/phase-04` (pushed to origin as of `4f0aa5c`) — 04-06 enrich_article SKILL.md + README.md + manual test guide. Orchestrator compacted context here while waiting for user's manual Hermes E2E test results before starting Wave 5 (04-07 ingest_wechat integration).
Resume file: `docs/testing/04-06-enrich_article-manual-test.md`
Next command after test results return: plan/execute 04-07 with SQLite-migration deploy-step added to its scope.
