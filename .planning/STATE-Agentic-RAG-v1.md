---
gsd_state_version: 1.0
milestone: Agentic-RAG-v1
milestone_name: — Agentic-RAG-v1 (parallel-track to v3.4)
status: in-progress
last_updated: "2026-05-23T01:30:00Z"
last_activity: 2026-05-23 — ar-3 phase planned. /gsd:plan-phase ar-3 --skip-research executed. 4 artifacts written (ar-3-CONTEXT.md 31KB + 3 PLAN.md files at 41-61KB each, total ~190KB). Capability-first 3-wave decomposition orchestrator-confirmed before planner spawn. gsd-plan-checker iter-1 verdict PASS_WITH_NITS, 0 required patches, all 5 ROADMAP success criteria covered, 7 ambiguities ruled (httpx per-call ALLOWED, vertex_gemini_grounding async MUST, Wave 3 absorption-and-delete of test_verifier_cap.py MUST, AsyncMock vs respx ALLOWED, Brave-only 10th test SHOULD-NOT, deepseek-dummy smoke ALLOWED, Branch A vs B impl ALLOWED). 7 non-blocking nits documented for executor (highlight: nit #1 Wave 1 from_env tests should monkeypatch.delenv OMNIGRAPH_LLM_PROVIDER proactively to avoid Wave 3 retrofit). Wave order: ar-3-01 (Tavily+Brave+cascade+TEST-02+CONFIG-03 env-half) → ar-3-02 (Verifier real loop ORCH-04+TEST-04 Verifier-half) → ar-3-03 (Vertex Grounding TOOL-03+CONFIG-03 autodetect+TEST-04 Reasoner-half consolidation). Mandatory operator note (TAVILY+BRAVE keys before live-key Layer 2b smoke) verbatim on last line of every PLAN.md. Phase ready for /gsd:execute-phase ar-3.
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 10
  completed_plans: 7
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
Phase: ar-3 — Verifier + web tools — **planned** (3/3 plans authored, plan-check PASS_WITH_NITS iter-1, 0 required patches)
Plan: ready for `/gsd:execute-phase ar-3` — Wave 1 (ar-3-01) first
Status: ar-1 = closed (4/4 plans, commits 962f995..cbd432d); ar-2 = closed (3/3 plans, commits 0674f66, 942dc48, 5aedf57, 8ca46ad, 8cd2642, 08edd1d); ar-3 = planned, 3 PLAN.md files written.
Last activity: 2026-05-23 — /gsd:plan-phase ar-3 --skip-research authored ar-3-CONTEXT.md + 3 PLAN.md files; gsd-plan-checker verdict PASS_WITH_NITS, all 5 ROADMAP success criteria covered, 7 ambiguities ruled, 7 non-blocking nits documented.

### Phase plan

| Phase | Goal | REQs | T-shirt | Status |
| ----- | ---- | ---- | ------- | ------ |
| ar-1 | MVP vertical slice (skeleton runs end-to-end) | 25 | L | complete (4/4) |
| ar-2 | Reasoner + vision deepening | 5 | M | complete (3/3) |
| ar-3 | Verifier + Tavily/Brave/Grounding | 7 | L | planned (0/3 executed) |
| ar-4 | Telemetry, streaming, smoke pass + audit | 4 | M | not started |

Total: 41/41 v1 REQs mapped, 30/41 delivered (ar-1: 25, ar-2: 5), 0 orphans.

### Immediate next step

`/gsd:execute-plan .planning/phases/ar-3-verifier-web-tools/ar-3-01-web-tools-PLAN.md`

ar-3 wave order (strictly sequential — no in-phase parallelism):

- Wave 1: ar-3-01 web-tools — Tavily search+extract callables, Brave fallback callable, cascade wrapper, from_env() env-half wiring (REQs: TOOL-01, TOOL-02, TEST-02, CONFIG-03 env-half)
- Wave 2: ar-3-02 verifier-loop — real bounded LLM agent loop with web_search/web_extract/conditional grounding tools; consumes Wave 1 cascade (REQs: ORCH-04, TEST-04 Verifier-half)
- Wave 3: ar-3-03 grounding-caps — Vertex Gemini Grounding pass-through, from_env() two-signal auto-detect, consolidated cap test for both Reasoner+Verifier loops; absorbs and deletes Wave 2's standalone test_verifier_cap.py (REQs: TOOL-03, CONFIG-03 autodetect-half, TEST-04 Reasoner-half)

### Ambiguity rulings (folded into PLAN files; SUMMARYs at execute close should record adoption)

1. httpx per-call vs shared session — ALLOWED (per-call planner default)
2. vertex_gemini_grounding sync vs async — MUST be async (matches Tavily/Brave callable shape)
3. Wave 3 absorption-and-delete of Wave 2's test_verifier_cap.py — MUST delete (single source of truth for cap tests)
4. httpx mocking via unittest.mock.AsyncMock vs respx — ALLOWED (planner default mock; respx if already in requirements)
5. Brave-only edge-case explicit test (10th) — SHOULD-NOT add (covered by implication; defer to ar-4 if time)
6. Layer 2a smoke LLM provider choice — ALLOWED either deepseek-dummy or Vertex VS Code metadata (cap=0 → no LLM call)
7. Vertex Grounding impl Branch A (helper) vs Branch B (inline genai) — ALLOWED, executor decides at Task 1 read_first

### Operator dependency for ar-3 live-key smoke (phase-close gate)

`TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` must be injected into `~/.hermes/.env` on the Hermes deployment target before the **Layer 2b live-key CLI smoke** can be performed. Wave 1+2 unit tests use mocks; Wave 3 Grounding test uses mocks; Layer 2a cap=0 smoke is mock-equivalent (no LLM call). Live-key Layer 2b is the phase-close gate, NOT a per-wave gate. Procurement should happen during ar-3 execution.

### Closed ar-2 wave summary (for cross-reference)

- Wave 1 (ar-2-01 reasoner-agent-loop, commit `0674f66`): real bounded LLM agent loop with kg_search + vision_analyze tools — ORCH-03, TOOL-04, TEST-03/Reasoner-half. 7 unit tests, 69/69 green.
- Wave 2 (ar-2-02 synthesizer-caption-embeds, commits `942dc48` + `5aedf57`): alt text source = `state.reasoned.analyzed_images[*].caption` with ar-1 filename fallback — ORCH-05, TEST-03/Synthesizer-half. 10 unit tests, 79/79 green. additional_chunks→sources tightened to gate on `state.reasoned.status=="ok"`.
- Wave 3 (ar-2-03 cli-flags, commits `8ca46ad` + `8cd2642`): `--max-iter-reasoner / --max-iter-verifier / --no-grounding` via `dataclasses.replace()`; NO `--llm-provider` (env-only) — CLI-03. 9 unit tests, 88/88 green. `_amain` body 15 LOC (≤18 cap). L2 cap=0 LLM-free CLI smoke exit 0.

### Operator dependency for ar-3 (must land before ar-3 execute begins)

`TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` must be injected into `~/.hermes/.env` on the Hermes deployment target before `/gsd:execute-phase ar-3` starts. ar-2 closed without requiring either key (stubs from ar-1 covered the WebBaseline/Verifier paths through ar-2). **STATUS at ar-2 close (2026-05-23): keys not yet confirmed injected — must verify before /gsd:plan-phase ar-3 advances past planning into execute.**

### VisionCascade adapter (deferred to ar-3+, Option A)

Production `lib/vision_cascade.py:VisionCascade.describe(id, bytes, mime)` (sync) does NOT match Reasoner's expected `await describe(image_path, question)` (async). ar-2 stayed mock-only (mock IS the contract for ar-2). Adapter wiring is in ar-3 production scope (Verifier loop + real-tool wiring will surface the same need). Do NOT add adapter retroactively into ar-2 stages.

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
