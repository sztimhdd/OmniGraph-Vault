---
gsd_state_version: 1.0
milestone: v3.5-Ingest-Refactor
milestone_name: — Ingest 筛选重构(双层 LLM filter,替换 classify 架构)
status: ready-for-execute
stopped_at: "Charter 完工 2026-05-07,等 user 起 /gsd:autonomous v3.5-Ingest-Refactor"
last_updated: "2026-05-07T19:42:32Z"
last_activity: "2026-05-07 — Foundation Quick 260507-lai deploy ✅ on Hermes; first v3.5 path execution scheduled 2026-05-08 09:00 ADT."
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State — v3.5-Ingest-Refactor (parallel)

## Project Reference

See: `.planning/PROJECT-v3.5-Ingest-Refactor.md` (this milestone)
Parent project: `.planning/PROJECT.md`
Earlier research artifact: `.planning/PROJECT-Ingest-Refactor-v3.5.md` (superseded by 6 D-decisions in PROJECT-v3.5-Ingest-Refactor.md, retained as design context)
Trigger postmortem: `.planning/quick/260507-ent-cron-mass-classify-cv-bug-revert-upsert-/260507-ent-SUMMARY.md`
Layer 1 v0 spike report: `.scratch/layer1-validation-20260507-151608.md`
Roadmap: `.planning/ROADMAP-v3.5-Ingest-Refactor.md`
Requirements: `.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md`

## Current Position

Milestone: v3.5-Ingest-Refactor (parallel-track to v3.4 Phases 20-22 + Agentic-RAG-v1)
Phase: Not started — charter committed, ready for first phase planning
Plan: —
Status: Ready for `/gsd:autonomous v3.5-Ingest-Refactor`
Last activity: 2026-05-07 — 4 sibling planning docs written + PROJECT.md pointer added

### Phase plan

| Phase | Goal | REQs | T-shirt | Status |
| ----- | ---- | ---- | ------- | ------ |
| ir-1 | Real Layer 1 + KOL ingest wiring | 14 | L | DONE (commit `f1a963b`) |
| ir-2 | Real Layer 2 + full-body scoring | 11 | L | DONE (commit `f8e90ef`) |
| ir-3 | Production cutover + 1-week observation | 1 | S (3 days + 7-day wall-clock) | in progress (calendar wait) |
| ir-4 | RSS integration + dead-code cleanup | 4 | M | **CODE-COMPLETE 2026-05-09** — 5 atomic commits on local main (`5d943f8`/`df495c8`/`4cc3757`/`9ff330d`/W5), awaiting user `继续` to push + Hermes deploy via `.planning/phases/ir-4-rss-integration-and-cleanup/HERMES-DEPLOY-ir-4.md`. **Scope deviation** (ack'd): user prompt redirected LF-5.1/5.2 from REQ-text targets to retiring `enrichment/rss_classify.py` + `rss_ingest.py` instead. Original LF-5.1/5.2/5.3 deletions remain pending in a follow-up. |

Total: 30/30 v1 REQs mapped, 0 orphans.

### Foundation Quick reference (260507-lai)

PLAN file: `.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/260507-lai-PLAN.md`

The Foundation Quick scopes 4 placeholder requirements (V35-FOUND-01..04):

- V35-FOUND-01: `lib/article_filter.py` placeholder API (`FilterResult`, `layer1_pre_filter`, `layer2_full_body_score` — all always-pass)
- V35-FOUND-02: ingest loop bypass of `_classify_full_body`, wired to placeholders
- V35-FOUND-03: candidate SQL drops `classifications` JOIN
- V35-FOUND-04: Hermes operator runbook for cron cleanup + cutover

**Ship status at charter time:** PLAN exists but no code commits to `main` yet. ir-1 plan-phase must check `git log --oneline | grep 260507-lai` and absorb V35-FOUND-01..04 if not shipped before ir-1 starts.

### Immediate next step

`/gsd:autonomous v3.5-Ingest-Refactor` (user-driven, manual; agent does NOT auto-launch).

## Parallel-Track Boundary

This STATE file tracks v3.5-Ingest-Refactor ONLY. v3.4 progress remains in `.planning/STATE.md`. Agentic-RAG-v1 progress remains in `.planning/STATE-Agentic-RAG-v1.md`.

The three milestones share:

- The same git working tree (commits land on `main`)
- The same Hermes deployment target (separate cron-edit slots coordinated by hand)
- The same `omnigraph_search.query.search()` cross-milestone contract (KG-stable; v3.5 does not touch query side)

The three milestones do NOT share:

- Phase numbering (v3.4 uses 19-22; Agentic-RAG-v1 uses `ar-N`; this uses `ir-N`)
- Sibling planning files (this file vs `STATE.md` vs `STATE-Agentic-RAG-v1.md`)
- Execute gates / blockers

## Current Hermes Operational State (post-deploy 2026-05-07 ~16:35 ADT)

Source-of-truth: `~/.hermes/cron/jobs.json` registry on the Hermes box. Verified
post-deploy by operator after Foundation Quick 260507-lai HERMES-DEPLOY.md
execution. Rollback artifact: `~/.hermes/cron/jobs.json.pre-v3.5-foundation.20260507-161555` (13 KB).

| Cron job (`job_id`) | State (post-deploy) |
|---|---|
| `daily-classify-kol` (`b50ec39b889f`) | **Permanently removed from jobs.json registry** by HERMES-DEPLOY.md execution 2026-05-07 ~16:35 ADT. Rollback artifact: `~/.hermes/cron/jobs.json.pre-v3.5-foundation.20260507-161555`. Retired per D-LF-1. |
| `daily-enrich` (`fc768319e0c1`) | **Permanently removed from jobs.json registry** (same deploy event). Off-scope dependency cleaned up alongside `daily-classify-kol`. |
| `rss-classify` (`c7ded378de8f`) | **Permanently removed from jobs.json registry** (same deploy event). RSS will get inline Layer 1/2 wiring in ir-4. |
| `daily-ingest` (`2b7a8bee53e0`) | **Active**, prompt cleaned to `run batch_ingest_from_spider.py --from-db` (no-op flags `--topic-filter` / `--min-depth` removed), next run **2026-05-08 09:00 ADT** (first v3.5 path execution end-to-end). |
| `每日KOL扫描` (`df7dc3fa0390`) | Active, daily 08:00 ADT — KOL scan, untouched by v3.5 deploy. |
| `KOL扫描前健康检查` (`e7afccd9931b`) | Active, daily 07:55 ADT — pre-scan health check, untouched. |
| `rss-fetch` (`29c3facf5023`) | Active, daily 06:00 ADT — RSS feed fetch, untouched. |
| `daily-digest` (`43e85ec247e5`) | Active, daily 09:30 ADT — Telegram digest emission, untouched. |
| `vertex-probe-monthly` (`d6421e78107a`) | Active, monthly — Vertex AI rate-limit canary, untouched. |
| `batch-watchdog` (`9a917f7209eb`) | Disabled since 2026-05-03 00:04 ADT (pre-existing); untouched by v3.5 deploy; unrelated to v3.5 milestone. |

**Total active jobs post-deploy: 6** (`daily-ingest` re-enabled + 5 untouched).

**Implication for ir-1/ir-2/ir-4 HERMES-DEPLOY runbooks:** `daily-ingest` is
now active. Subsequent migration deploys (006/007/008) must temporarily pause
it before schema changes to avoid mid-batch column-mismatch races, then
re-enable after migration verification + smoke. Pause/resume is Hermes
CLI-driven; the cron command shape stays unchanged from the post-260507-lai
cleanup (`run batch_ingest_from_spider.py --from-db`).

**Implication for Phase ir-3 observation:** the 7-day window observes
`daily-ingest` running alongside 5 still-active crons. `每日KOL扫描` + `rss-fetch`
continue to populate `articles` / `rss_articles`; `daily-digest` consumes the
previous day's `daily-ingest` output. **Zero crons write `classifications` rows
anymore** — all filter state lives inline on `articles.layer1_* / layer2_*`
columns. First-run backlog implication still applies per ROADMAP § ir-1 Notes
(2026-05-08 09:00 ADT first run will see post-charter accumulation since
2026-05-07 ~14:33 ADT).

## Hermes Deploy Protocol (operator scope)

Migrations 006, 007, (optional) 008 land on Hermes via per-phase HERMES-DEPLOY.md runbooks at `.planning/phases/ir-N-*/HERMES-DEPLOY.md`. Standard shape:

1. Pull main on Hermes; verify HEAD matches local
2. Backup `data/kol_scan.db` (mandatory per Lessons 2026-05-06 #2)
3. Apply migration via `python migrations/<NNN>_<name>.py` or equivalent runner
4. Verify schema (`PRAGMA table_info(articles)` shows new columns)
5. Edit cron command if needed (Foundation Quick already removed `daily-classify-kol`)
6. Resume cron + smoke 5 articles
7. Tail logs for layer1/layer2 verdict tags

Operator runs all Hermes-side steps via SSH; agent does not SSH.

## Cross-milestone contract

KG-side ingest path changes only. **Agentic-RAG-v1 (query-side) unchanged** — `omnigraph_search.query.search(query_text, mode)` signature is stable. v3.4 main-line work continues independently. No file outside `lib/article_filter.py`, `lib/llm_*.py` (read-only reuse), `batch_ingest_from_spider.py`, `rss_ingest.py` (ir-4 only), `migrations/`, `tests/unit/`, and `.planning/phases/ir-*/` is touched by this milestone.

## Accumulated Context

### Roadmap Evolution

- 2026-05-07 — Milestone v3.5-Ingest-Refactor chartered after CV mass-classify cron disaster (06:00–09:00 ADT). Sibling-files layout chosen; `ir-N` phase prefix; 6 D-decisions locked; Layer 1 v0 prompt validated by 30-article spike; charter doc written. Earlier research artifact `.planning/PROJECT-Ingest-Refactor-v3.5.md` superseded but retained as design context.

### Decisions

D-decisions are logged in `PROJECT-v3.5-Ingest-Refactor.md` § "6 User-Locked D-Decisions" (D-LF-1..6). Echoed here for state-file completeness:

- D-LF-1: Layer 1 接入位置 = ingest pipeline 最前面;`daily-classify-kol` cron 永久删除
- D-LF-2: 持久化 = `articles` + `rss_articles` 各加 4 列(layer1_*),migration 006 additive;Layer 2 同样模式(migration 007)
- D-LF-3: Batch size = Layer 1 30/batch,Layer 2 5–10/batch
- D-LF-4: Failure mode = batch verdict 全 NULL 下轮重判;无 max retry
- D-LF-5: Trigger = inline ingest run 阶段,无新 cron
- D-LF-6: Scope = WeChat (KOL) 先,RSS 后续 phase (ir-4 optional)

This-session decisions:

- 2026-05-07 — Sibling-files layout (`PROJECT-v3.5-Ingest-Refactor.md` etc.) chosen over subdirectory or worktree, mirroring the precedent set by Agentic-RAG-v1
- 2026-05-07 — Phase prefix `ir-N` chosen over continuing `23+` numbering and over a hypothetical extension to `ar-N`, since the parallel-track chronology would be misleading otherwise
- 2026-05-07 — Research stage skipped — Layer 1 v0 prompt is already spike-validated; design is locked in PROJECT-v3.5-Ingest-Refactor.md. `/gsd:autonomous` should jump from spec → planning → execute
- 2026-05-07 — Layer-vertical, observation-gated decomposition chosen over vertical-slice MVP-first. Layer 1 is independently spike-validated; Layer 2 needs its own spike. Observation phase is non-overlapping with code work, justifying its own phase

### Pending Todos

None tracked. Awaiting `/gsd:autonomous v3.5-Ingest-Refactor` invocation.

### Blockers/Concerns

- **Foundation Quick 260507-lai shipping status** — placeholder PLAN exists, code has not yet committed to `main`. ir-1 plan-phase MUST check `git log --oneline | grep 260507-lai` before starting; if foundation has not shipped, ir-1 absorbs V35-FOUND-01..04. If foundation HAS shipped between charter time (2026-05-07T18:43Z) and `/gsd:autonomous` start, ir-1 builds on top.
- **Hermes cron timeout (memory `hermes_agent_cron_timeout.md`)** — applies equally to ir-3 observation runs. If 7-day cron observation reveals timeouts on long Layer 2 batches, mitigation is the existing `HERMES_CRON_TIMEOUT=28800` env var; long-term fix (systemd timer migration) is operational hardening tracked in `MILESTONE_v3.5_CANDIDATES.md` Section 2 — not blocking this milestone.

## Performance Metrics

(populated as plans complete)

## Session Continuity

Last session: 2026-05-07T18:43:14Z
Stopped at: 4 sibling planning docs written + PROJECT.md pointer added; charter complete
Resume file: None
Next command: `/gsd:autonomous v3.5-Ingest-Refactor` (user-driven)
