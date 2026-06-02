---
gsd_state_version: 1.0
milestone: v1.0.y
milestone_name: — Stability + small-scope fixes following v1.0.x closeout (2026-05-16) and Aliyun-Ingest-Migration-v1 closure (2026-05-25)
status: in-progress
stopped_at: "v1.0.y-0 IN-PROGRESS — KB_SYNTHESIZE_TIMEOUT=240 single-line app.yaml fix + Makefile 6-pass redeploy + smoke verify markdown_len > 0"
last_updated: "2026-05-25T22:30:00Z"
last_activity: "2026-05-25 — milestone chartered following Aliyun-Ingest-Migration-v1 closure (6/6 phases). 9-ticket backlog converted to 6-phase plan (v1.0.y-0 IN-PROGRESS, v1.0.y-1..5 PLANNED). P0 v1.0.y-0 root cause already verified in `.planning/quick/260525-c1-no-content-at-64s/REPORT.md` Steps 1-2; this milestone wraps the fix + landing + verification."
progress:
  total_phases: 7
  completed_phases: 0
  in_progress_phases: 1
  total_plans: 7
  completed_plans: 0
  superseded_phases: 1
---

# Project State — v1.0.y (small-scope stability follow-ups)

## Project Reference

See: parent project `.planning/PROJECT.md` (v1.0 Knowledge Collection + Ingestion subsystem)
Predecessor milestones (closed):

- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` — closed 2026-05-25 (6/6 phases)
- `.planning/STATE-Agentic-RAG-v1.md` — closed 2026-05-24 (41/41 REQs)
- v1.0.x stable closed 2026-05-16 (two-layer timeout fix; see memory `project_v1_0_x_closure_260516.md`)

## Current Position

Milestone: v1.0.y (parallel-track stability)
Phase: v1.0.y-0 IN-PROGRESS (P0 single-line app.yaml drift fix)
Plan: v1.0.y-0
Status: 0/7 complete; 1/7 in-progress; 5/7 planned; 1/7 superseded
Last activity: 2026-05-25 (late) — v1.0.y-3 SUPERSEDED (scope misdiagnosis: probe `.scratch/v1.0.y-3-arag-b-probe-20260525-152744.md` falsified the ARAG-Reasoner-strip hypothesis — `_build_prompt` lines 73-108 emit only counts/labels, never chunk text; consumer recon shows `kb/static/qa.js:269` calls `/api/synthesize` not `/api/research`). Replaced by `v1.0.y-3-synth-img` scoped narrowly to the `/api/synthesize` path.

### Phase plan

| Phase | Goal | Priority | T-shirt | Status | Blocker |
| ----- | ---- | -------- | ------- | ------ | ------- |
| v1.0.y-0 | Add `KB_SYNTHESIZE_TIMEOUT=240` to `databricks-deploy/app.yaml`; redeploy via Makefile 6-pass; smoke verify `markdown_len > 0` on long_form | P0 | XS | 🟡 IN-PROGRESS | none |
| v1.0.y-1 | Implement per-mode timeout dispatch in `kb_synthesize` (qa=60 / long_form=240) — closes `kg_synthesize.py:64-70` comment promise | P1 | M | ⏸ PLANNED | v1.0.y-0 landed |
| v1.0.y-2 | Diagnose + fix zh-CN 27-char query FTS5 zero-hit (tokenizer / index / query-side) | P1 | M | ⏸ PLANNED | none |
| v1.0.y-3 | ~~Fix ARAG (b) Synthesizer→Reasoner→Retriever pipeline `image_ref` markdown stripping~~ | ~~P1~~ | ~~M~~ | 🚫 SUPERSEDED | scope misdiagnosis — see SUPERSEDED block in plan file; replaced by v1.0.y-3-synth-img |
| v1.0.y-3-synth-img | Restore `![alt](url)` preservation through `POST /api/synthesize` so final `result.markdown` contains `/static/img/<hash>/<file>` refs intact | P1 | S | ⏸ PLANNED | none (probe gates execute, not authoring) |
| v1.0.y-4 | Reconcile `articles.lang` schema drift between prod (Aliyun) and dev (`.dev-runtime/`) | P2 | S | ⏸ PLANNED | none |
| v1.0.y-5 | aim-2/aim-3 cutover residual cache cleanup (Hermes lightrag_storage cold-backup, stale Aliyun pre-aim2 backup, etc.) | P2 | S | ⏸ PLANNED | none |

Total: 7 phases (1 superseded). P0 + 3xP1 = 4 phases gate "v1.0.y closeable"; P2x2 spillable to v1.0.z if scope creeps (per Q5 default assumption). v1.0.y-3 SUPERSEDED does not count toward closeable; v1.0.y-3-synth-img replaces it as the P1 closeable.

P3 parked (overview only, NOT phase-allocated):

- `lightrag-cache-write-perms` — Aliyun LightRAG cache dir write perms (V1.1-E follow-up; not P0 since aim-3 already live)
- `tavily-key-rotation` — periodic Tavily API key rotation discipline

P4 observation only (NOT phase-allocated):

- `aliyun-cron-first-unattended` — 2026-05-26 06:00 / 12:00 / 14:00 UTC first unattended cron post aim-3 cutover. Watch via journalctl; nothing to plan unless it fails.

### Immediate next step

Execute v1.0.y-0 Task 1 (edit `databricks-deploy/app.yaml`) → Task 2 (Makefile 6-pass redeploy) → Task 3 (smoke `databricks-claude-sonnet-4-6` long_form `markdown_len > 0`).

## Cross-milestone contract

**This milestone touches NO ingestion / KG-write paths.** All 6 phases are read-side / synthesis-side / config / schema cleanup only.

- LightRAG storage on-disk format unchanged
- `omnigraph_search.query.search()` signature stable (Agentic-RAG-v1 contract honored)
- kb-api `POST /api/synthesize` semantics preserved (timeout threshold changes, behavior unchanged)
- Aliyun-Ingest-Migration-v1 cron substrate (kol-scan / kol-classify / daily-ingest systemd timers) untouched
- v1.0.x ingest stack (`batch_ingest_from_spider.py`, h09 PROCESSED-gate, image_count_row contract) untouched

## Hard Constraints (project CLAUDE.md inheritance)

The 8 HARD CONSTRAINTS from project CLAUDE.md apply by default to every phase in this milestone:

1. No `git add -A` / `git add .` — explicit filenames only
2. No `git commit --amend` (forward-only correction commits)
3. No `git push --force` (especially not to `main`)
4. No literal secrets in prompts / commits / artifacts
5. Atomic stage-commit-push (Edit → add → commit → push in single chained Bash invocation)
6. Commit body MUST cite `.scratch/<log>:line` for any "I verified" claim
7. Never bypass LightRAG (no DeepSeek-only / FTS5-only long_form proposals — see memory `feedback_lightrag_is_core_asset_no_bypass.md`)
8. `omonigraph` typo is canonical — do NOT "fix" without coordinated migration

PRINCIPLE 5 OVERRIDE (aim-N pattern; carried forward as awareness): for any phase that mutates Aliyun state, agent SSHes via `aliyun-vitaclaw` alias directly. Hermes operator-channel for any Hermes mutating ops. v1.0.y phases are mostly local-edit + Databricks-deploy + Aliyun-read-only; no expected Aliyun mutation.

## Operator Channel

User runs main session locally (Windows). Agent owns:

- All file edits under `c:\Users\huxxha\Desktop\OmniGraph-Vault`
- All `databricks sync` / `databricks apps deploy` / `databricks apps logs` calls (Principle #7 — autonomous Databricks deploy)
- All read-only diagnostic SSH to Aliyun via `aliyun-vitaclaw` alias when needed
- All `git add <explicit>` + `git commit` + `git push` per HARD CONSTRAINT #5

User retains decision authority over:

- Phase ordering / prioritization shifts
- Scope expansion (e.g., promoting P3 parked to a phase)
- Milestone close decision

## Accumulated Context

### Roadmap evolution

- 2026-05-25 — milestone v1.0.y chartered following Aliyun-Ingest-Migration-v1 closure. 9-ticket backlog (P0=1, P1=3, P2=2, P3 parked=2, P4 observation=1) decomposed into 6 phase plans. Default assumptions Q1-Q5 accepted by user (skeleton review).

### Decisions (Q1-Q5 default assumptions; locked 2026-05-25)

- **Q1** — ~~v1.0.y-3 b-branch probe is execute-gating only (not plan-authoring blocker). Plan now; the task-list itself contains a `<halt>` block that fires only at execute time.~~ **REVISED 2026-05-25 (late):** v1.0.y-3 SUPERSEDED after probe `.scratch/v1.0.y-3-arag-b-probe-20260525-152744.md` mechanically falsified the ARAG hypothesis (Reasoner `_build_prompt` lines 73-108 emit only counts/labels — never chunk text — so the LLM cannot strip image markdown it never sees). Consumer-side recon also showed `kb/static/qa.js:269` calls `/api/synthesize` (NOT `/api/research`), so any user-visible defect lives in the synthesize wrapper, not ARAG. Replaced by `v1.0.y-3-synth-img` (probe-gated execute, narrow scope: `kb/services/synthesize.py` qa template + `_LEGACY_IMAGE_URL_PATTERN`).
- **Q2** — v1.0.y-2 = single phase with two tasks (diagnose → fix). Not split into two phases.
- **Q3** — v1.0.y-0 uses forward-planning体例 with `status: IN-PROGRESS` and an "Already-done snapshot from `260525-c1-no-content-at-64s/REPORT.md`" block at the top of Acceptance criteria.
- **Q4** — No separate `CONTEXT.md` for v1.0.y. Findings inline as a `## Background` section per plan.
- **Q5** — P1 closed = milestone closeable. P2 (`v1.0.y-4`, `v1.0.y-5`) spillable to v1.0.z if scope creeps.

### Pending Todos

- v1.0.y-0 plan authored ✅ 2026-05-25; execute next.
- v1.0.y-1 plan authored ✅ 2026-05-25; blocked on v1.0.y-0 landed.
- v1.0.y-2 plan authored ✅ 2026-05-25; no blocker, parallelizable with v1.0.y-1.
- v1.0.y-3 plan authored ✅ 2026-05-25; **🚫 SUPERSEDED 2026-05-25 (late)** — scope misdiagnosis; rationale + carry-forward constraints recorded in plan file's SUPERSEDED block.
- v1.0.y-3-synth-img plan authored ✅ 2026-05-25 (late); narrow scope `/api/synthesize` qa template + legacy URL regex; probe-gated execute (Task 0).
- v1.0.y-4 plan authored ✅ 2026-05-25; no blocker, can run any time.
- v1.0.y-5 plan authored ✅ 2026-05-25; no blocker, last per default ordering.

Open follow-ups outside this milestone (carried from predecessor closures):

- Hermes `lightrag_storage` cold-backup retention deadline: **2026-06-22** (set by aim-2-5; persists across this milestone — touched by v1.0.y-5 only as a reference checkpoint, not modified).
- Databricks SYNC-03 first real verification (24h post Aliyun first real wiki commit) — operator action documented in `docs/runbooks/aim-4-databricks-sync03-verify.md`.
- v1.1 backlog (Agentic-RAG-v1 V1.1-A/B/C/D/E) — separate milestone; do NOT pull into v1.0.y.

### Blockers/Concerns

- **v1.0.y-0** is single-line config + redeploy + smoke; the only risk is Makefile 6-pass surprise (e.g., SSG-bake regression on a fresh sync). Treat as XS unless redeploy hits an unrelated failure.
- **v1.0.y-1** depends on v1.0.y-0 landing — to avoid double-thrash on the same module (`kb/services/synthesize.py`). Once v1.0.y-0 is verified PASS, v1.0.y-1 can start.
- **v1.0.y-2** zh-CN FTS5 zero-hit could be tokenizer (CJK split issue), index drift (rebuild needed), or query-side normalization. Diagnosis task gates the fix task.
- ~~**v1.0.y-3** ARAG `image_ref` strip needs the b-branch probe report before execute. If the report does not arrive within the milestone window, v1.0.y-3 can be parked to v1.0.z without blocking close.~~ **SUPERSEDED — no longer a concern** (plan retired; replaced by v1.0.y-3-synth-img).
- **v1.0.y-3-synth-img** image-ref preservation through `/api/synthesize` needs a local probe report (Task 0) classifying the defect as `prompt-side` / `regex-side` / `frontend-side` / `data-side` / `multiple` before execute. Probe is local code-read against `main`, no external SSH dependency. If probe classifies as `data-side` (chunks lack image refs at retrieval time) or `frontend-side` requiring sanitizer overhaul, halt + park to a follow-up phase rather than execute here. F2 (Reasoner `only_context=True` missing on `_kg_search_tool`) parked to v1.1, alongside the real ARAG production rollout.
- **v1.0.y-5** cache cleanup is the lowest-leverage phase; only run after the other 5 are PASS or all explicitly parked.

## Performance Metrics

(populated as phases complete)

Expected outcomes after v1.0.y close:

- Long_form `POST /api/synthesize` returns `markdown_len > 0` on Databricks deploy (was 0 pre v1.0.y-0)
- zh-CN short-query (≥27 char) FTS5 fallback hit rate > 0 (was 0 pre v1.0.y-2)
- `POST /api/synthesize` (kb-3 Q&A) preserves `![alt](url)` markdown image refs end-to-end — final `result.markdown` contains `/static/img/<hash>/<file>` URL form for retrieved chunks bearing image markdown (was missing pre v1.0.y-3-synth-img); ARAG Reasoner left untouched (proven defect-free by probe)
- `articles.lang` column schema parity prod ↔ dev (was drifted pre v1.0.y-4)
- Stale aim-2 backup directory + Hermes cold-backup deadline both confirmed present + dated (was untracked pre v1.0.y-5)

## Session Continuity

Last session: 2026-05-25T22:30:00Z
Stopped at: v1.0.y-0 IN-PROGRESS — milestone scaffold + 6 phase plans authored; ready to execute v1.0.y-0 next.
Resume file: `.planning/phases/v1.0.y/v1.0.y-0-app-yaml-drift.md`
Next command: `/gsd:execute-phase v1.0.y-0` (or direct execution per project Principle #7 autonomous Databricks deploy)
