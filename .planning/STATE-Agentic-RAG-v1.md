---
gsd_state_version: 1.0
milestone: Agentic-RAG-v1
milestone_name: — Agentic-RAG-v1 (parallel-track to v3.4)
status: ready-for-discuss-phase
last_updated: "2026-05-06T21:00:00Z"
last_activity: 2026-05-06 — ROADMAP-Agentic-RAG-v1.md created by gsd-roadmapper; 41/41 v1 REQs mapped across 4 phases (ar-1..ar-4); vertical-slice MVP-first decomposition chosen.
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State — Agentic-RAG-v1 (parallel)

## Project Reference

See: `.planning/PROJECT-Agentic-RAG-v1.md` (this milestone)
Parent project: `.planning/PROJECT.md`
Locked design: `docs/design/agentic_rag_internal_api.md`
Ground truth: `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`
Roadmap: `.planning/ROADMAP-Agentic-RAG-v1.md`
Requirements: `.planning/REQUIREMENTS-Agentic-RAG-v1.md`

## Current Position

Milestone: Agentic-RAG-v1 (parallel-track)
Phase: Not started — roadmap approved, ready for first phase planning
Plan: —
Status: Ready for `/gsd:discuss-phase ar-1`
Last activity: 2026-05-06 — ROADMAP committed, 41/41 REQs mapped

### Phase plan

| Phase | Goal | REQs | T-shirt |
|-------|------|------|---------|
| ar-1 | MVP vertical slice (skeleton runs end-to-end) | 25 | L |
| ar-2 | Reasoner + vision deepening | 5 | M |
| ar-3 | Verifier + Tavily/Brave/Grounding | 7 | L |
| ar-4 | Telemetry, streaming, smoke pass + audit | 4 | M |

Total: 41/41 v1 REQs mapped, 0 orphans.

### Immediate next step

`/gsd:discuss-phase ar-1` (or `/gsd:plan-phase ar-1` if ready to skip discussion).

## Parallel-Track Boundary

This STATE file tracks Agentic-RAG-v1 ONLY. v3.4 progress remains in `.planning/STATE.md`.

The two milestones share:

- The same git working tree (commits land on `main`)
- The same Hermes deployment target (separate test slots coordinated by hand)
- The same `omnigraph_search.query.search()` cross-milestone contract (KG-stable, see PROJECT-Agentic-RAG-v1.md)

The two milestones do NOT share:

- Phase numbering (v3.4 uses 19-22; this uses ar-N)
- Sibling planning files (this file vs `STATE.md`)
- Execute gates / blockers

## Accumulated Context

### Roadmap Evolution

- 2026-05-06 — Milestone Agentic-RAG-v1 initialized parallel to v3.4. Sibling-files
  layout chosen; ar-N phase prefix; design doc treated as final (research skipped).
- 2026-05-06 — REQUIREMENTS-Agentic-RAG-v1.md committed (41 v1 REQs, 8 categories).
- 2026-05-06 — ROADMAP-Agentic-RAG-v1.md created by `gsd-roadmapper`. Decomposition:
  vertical-slice MVP-first across 4 phases (ar-1..ar-4). All 41 REQs mapped, no
  orphans, no duplicates. Traceability table in REQUIREMENTS file populated.

### Decisions

Decisions are logged in `PROJECT-Agentic-RAG-v1.md` § Locked Architectural Choices
(echoes design doc § Architecture decisions, axes 1-10).

This-session decisions:

- 2026-05-06 — Sibling-files layout (`PROJECT-Agentic-RAG-v1.md` etc.) chosen over
  subdirectory or worktree, preserving v3.4 GSD tooling untouched
- 2026-05-06 — Phase prefix `ar-N` chosen over continuing `23+` numbering, since
  the parallel-track chronology would be misleading otherwise
- 2026-05-06 — Research stage skipped — design doc `docs/design/agentic_rag_internal_api.md`
  treated as final per user instruction; no `gsd-project-researcher` agents spawned
- 2026-05-06 — **Vertical-slice MVP-first decomposition** chosen over
  orchestrator-first. Three drivers: (1) integration risk, not stage risk, is
  what an end-to-end skeleton flushes out earliest; (2) smoke test (TEST-05)
  exercises every stage, so a stub-pipeline catches contract bugs cheaply;
  (3) Reasoner / Verifier agent loops are the highest behavioral risk, and
  vertical-slice forces deterministic-stub versions to exist Day 1, fixing the
  loop interface before LLM-driven version is wired in. Full rationale in
  ROADMAP-Agentic-RAG-v1.md § "Phase decomposition rationale".
- 2026-05-06 — **4 phases**, not 3 or 5. Below 4 bundles too much risk into a
  single phase; above 4 creates artificial Reasoner-deepening / Verifier-deepening
  splits that share scaffolding (agent-loop harness, telemetry, prompt iteration).

### Pending Todos

None tracked. Awaiting `/gsd:discuss-phase ar-1` or `/gsd:plan-phase ar-1` invocation.

### Blockers/Concerns

- **None for milestone init or roadmap.** Operator-side dependencies
  (`TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`) are tracked as CONFIG-01 / CONFIG-02
  requirements — both belong to ar-1 (env reads at config construction time).
  ar-1 can complete with both unset (callables are stubbed); ar-3 requires at
  least Tavily live for TOOL-01 to land. Coordinate procurement around the
  ar-2 → ar-3 boundary.

## Performance Metrics

(populated as plans complete)

## Session Continuity

Last session: 2026-05-06T21:00:00Z
Stopped at: Roadmap committed; 41/41 REQs mapped; phase plan locked at ar-1..ar-4
Resume file: None
Next command: `/gsd:discuss-phase ar-1` (preferred) or `/gsd:plan-phase ar-1`
