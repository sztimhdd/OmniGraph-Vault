# Milestone v3.3 — Daily-Ops Hygiene

**Status:** ACTIVE (started 2026-05-03)
**Predecessor:** v3.2 ✅ CLOSED 2026-05-02
**Milestone goal:** Close the gap between "Phase 5 cron runs" and "cron reliably delivers value for weeks without operator intervention." Address the 6 deferred items from Wave 0 Close-Out + the 2026-05-03 Vertex flip incident.

**Entry criteria:** Phase 5 Wave 3 Task 6.2 passes (3-day observation with user sign-off) + Task 6.3 completes (Phase 5 Exit State written to STATE.md + ROADMAP.md).

**Exit criteria:**
- 6 Phase 18 plans shipped with SUMMARYs
- Daily cron runs 14 consecutive days with ≥ 90% success rate
- Any cron failure triggers Telegram alert with operator-actionable diagnostic
- Vertex live-probe cron in place (monthly) — catches catalog flips before they kill prod
- Lightweight regression smoke CI hook active on ingest/embedding/vision PRs

**Phase:** Phase 18 (single consolidated hygiene phase, 6 plans across 2 waves).

---

## Context — why this milestone exists

Two empirical findings from the Wave 0 Close-Out (2026-05-02) + the 2026-05-03 Vertex flip drive the scope of v3.3:

1. **Model-name contract flipped twice in ~24h** on Vertex AI `us-central1` (2026-05-02: `gemini-embedding-2` 404 / `-preview` 3072-dim OK; 2026-05-03 morning: `gemini-embedding-2` 3072-dim OK / `-preview` 404). Visual review of comments ("preview deprecated" vs "preview required") was empirically wrong in both directions. Automated live-probe is required.
2. **Real-batch runs catch bugs that fixture smoke cannot.** Wave 0's 118-image edge case, async-blocking, and Cognee module-level import issues surfaced only when multiple articles × dense images × live Vertex hit the pipeline together. v3.3 adds a lightweight regression smoke on a single fixture to catch the cheap class of regressions, but keeps real-batch cron as the primary defect yield.

Three additional items were deferred from Wave 0 for scope-control and land here as atomic hygiene plans.

---

## Requirements

| ID | Requirement | Plan | Wave |
|---|---|---|---|
| HYG-01 | Vertex AI embedding model-name live probe (monthly cron; alerts on 404) | 18-00 | 1 |
| HYG-02 | 118-image edge case handling (N-image cap OR entity-merge timeout extension OR both) | 18-01 | 1 |
| HYG-03 | Cognee restoration decision for `kg_synthesize` (restore OR formally abandon with replacement) | 18-02 | 1 |
| HYG-04 | Prompt image-URL directive standardization across `kg_synthesize` + `omnigraph_query` + `omnigraph_synthesize` | 18-03 | 1 |
| HYG-05 | Lightweight regression smoke (gpt55 fixture × `bench_ingest_fixture.py` × 4 hard gates; CI hook + weekly Hermes cron) | 18-04 | 2 |
| HYG-06 | Source-site change detection (enhance 05-04 orchestrator with Telegram alerts on classify error rate / WeChat scan anomaly / RSS `feeds_fail` ratio) | 18-05 | 2 |

---

## Scope boundaries

**In scope:**
- Hardening: probes, alerts, caps, smoke tests
- Decisions inherited from Wave 0 Close-Out (DeepSeek LLM routing, pass-through `_resolve_model`, single regression fixture)
- Operational ergonomics: operator-actionable Telegram messages, monitoring signals

**Out of scope (explicit non-goals):**
- New data sources (GitHub / Twitter / Substack / etc.) — v3.3 is hardening only
- New Hermes skills (`omnigraph_query`, `omnigraph_synthesize`, `omnigraph_ingest`, etc. stay unchanged except for the HYG-04 prompt string)
- UI / query-layer reshape beyond HYG-04
- Re-opening or modifying Phases 7–17 artifacts (all archived/closed)
- Milestone v3.4 decisions (defer until v3.3 data accumulated over 14 days)

---

## Waves

- **Wave 1 (4 plans, no blockers):** 18-00 Vertex live-probe · 18-01 118-image cap · 18-02 Cognee restoration · 18-03 prompt directive.
- **Wave 2 (2 plans, blocked on Phase 5 Wave 3 closure):** 18-04 regression smoke · 18-05 source-site alerts.

Wave 2 unblocks when Phase 5 Task 6.2 (3-day observation) reports `approved` or `approved-with-notes` and Task 6.3 writes the Phase 5 Exit State. Wave 2 stays in PLAN-only state until then.

---

## Success criteria — milestone-level

| Criterion | How verified |
|---|---|
| 6 Phase 18 SUMMARY.md files exist | `ls .planning/phases/18-daily-ops-hygiene/18-0{0..5}-SUMMARY.md` |
| HYG-01 Vertex probe cron registered on Hermes | `ssh hermes 'hermes cron list | grep vertex-probe'` |
| HYG-02 image cap visible in ingest_wechat.py | `grep -q "MAX_IMAGES_PER_ARTICLE" ingest_wechat.py` |
| HYG-03 replacement history mechanism has unit tests | `pytest tests/unit/test_query_history.py -v` (or documented abandonment) |
| HYG-04 directive shared across synth + skill | `grep -q "IMAGE_URL_DIRECTIVE" kg_synthesize.py` |
| HYG-05 regression smoke runs on PR and weekly | `.github/workflows/regression-smoke.yml` exists + Hermes cron registered |
| HYG-06 three alert rules present in `orchestrate_daily.py` | grep for the 3 threshold constants |

---

## Revision history

- **2026-05-03** — initial draft. Composed from:
  - `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` Wave 0 Close-Out Addendum §§ A–G (esp. § C Sub-incident + 2026-05-03 Follow-up, § D Phase 7 D-09 supersession, § F deferred items)
  - Vertex AI flip history in `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/vertex_ai_smoke_validated.md`
  - User YOLO-mode brief (2026-05-03)
