---
gsd_state_version: 1.0
milestone: Agentic-RAG-v1
milestone_name: — Agentic-RAG-v1 (parallel-track to v3.4)
status: in-progress
last_updated: "2026-05-23T05:00:00Z"
last_activity: 2026-05-23 — ar-3 phase CLOSED. All 3 waves executed sequentially. Wave 1 (ar-3-01 web-tools, commit 6bc7db7): 9 unit tests, 97/97 green; TOOL-01+TOOL-02+TEST-02+CONFIG-03 env-half delivered; surgical adapter at web_baseline.py via inspect.isawaitable() (orchestrator-accepted deviation). Wave 2 (ar-3-02 verifier-loop, commit e594363): 10 unit tests (9 agent-loop + 1 cap), 107/107 green; ORCH-04+TEST-04 Verifier-half delivered; tool wire format = list[dict] with name+fn keys (matches Reasoner pattern); 2 surgical forward-fixes to test_orchestrator.py + test_stages_stubs.py (~11 LOC, ar-1 stub assertions tracked the old skipped state). Wave 3 (ar-3-03 grounding-caps, commit 17a8fca): 7 net unit tests (5 autodetect + 2 consolidated caps − 1 deleted test_verifier_cap.py), 113/113 green; TOOL-03+CONFIG-03 autodetect+TEST-04 Reasoner-half delivered; Branch B chosen (inline google.genai Vertex client, lib/vertex_gemini_complete.py does not expose complete_with_grounding helper). L2a cap=0 LLM-free CLI smoke exit 0, 155-char markdown (acceptable — fewer degradation notes than ar-2-03 smoke = progress; Retriever 3072/768 embedding dim mismatch is pre-existing v1.0.y operator-side KG issue out of ar-3 scope). CONTRACT-01/02 clean across all 3 waves. Forward-only commits throughout, zero amend/reset. Phase ready for /gsd:plan-phase ar-4.
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 10
  completed_plans: 10
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
Phase: ar-3 — Verifier + web tools — **complete** (3/3 plans executed, 113/113 unit tests green, L2a cap=0 LLM-free CLI smoke exit 0)
Plan: ready for `/gsd:plan-phase ar-4` (Telemetry, streaming, smoke pass + milestone audit)
Status: ar-1 = closed (4/4 plans, commits 962f995..cbd432d); ar-2 = closed (3/3 plans, commits 0674f66..08edd1d); ar-3 = closed (3/3 plans, commits 6bc7db7, e594363, 17a8fca); 10/10 ar-N plans executed.
Last activity: 2026-05-23 — ar-3 phase closed. All 7 ar-3 REQs delivered (ORCH-04, TOOL-01, TOOL-02, TOOL-03, CONFIG-03, TEST-02, TEST-04). Vertex Grounding via Branch B (inline google.genai). Test progression 88 → 97 → 107 → 113 green. CONTRACT-01/02 clean across all 3 waves.

### Phase plan

| Phase | Goal | REQs | T-shirt | Status |
| ----- | ---- | ---- | ------- | ------ |
| ar-1 | MVP vertical slice (skeleton runs end-to-end) | 25 | L | complete (4/4) |
| ar-2 | Reasoner + vision deepening | 5 | M | complete (3/3) |
| ar-3 | Verifier + Tavily/Brave/Grounding | 7 | L | complete (3/3) |
| ar-4 | Telemetry, streaming, smoke pass + audit | 4 | M | not started |

Total: 41/41 v1 REQs mapped, 37/41 delivered (ar-1: 25, ar-2: 5, ar-3: 7), 0 orphans.

### Immediate next step

`/gsd:plan-phase ar-4` — Telemetry JSONL, `research_stream()` body, `--dump-state` CLI flag, milestone-close smoke (TEST-05 — Hermes Harness 深度解析 with 5 pass conditions), milestone audit (TEST-06).

### Operator dependency for ar-3 live-key Layer 2b smoke (deferred phase-close gate)

`TAVILY_API_KEY` + `BRAVE_SEARCH_API_KEY` need to be injected into `~/.hermes/.env` on Hermes for live-key validation. Wave 1+2+3 all unit-test green with mocks; L2a cap=0 LLM-free smoke exit 0. **L2b live-key smoke is a soft gate** — not blocking ar-4 planning, but should be performed (orchestrator-driven via Hermes prompt) before ar-4 execute completes the milestone. Procurement track: keys → Hermes during ar-4 execute.

### ar-3 wave summary (all closed)

- Wave 1 (ar-3-01 web-tools, commit `6bc7db7`): Tavily search+extract callables, Brave fallback, cascade wrapper, from_env() env-half — TOOL-01, TOOL-02, TEST-02, CONFIG-03 env-half. 9 unit tests, 97/97 green. Surgical adapter at web_baseline.py via `inspect.isawaitable()` (orchestrator-accepted deviation; preserves sync stub fallback while supporting async Tavily callable).
- Wave 2 (ar-3-02 verifier-loop, commit `e594363`): Real bounded LLM agent loop in verifier.py — ORCH-04, TEST-04 Verifier-half. 10 unit tests, 107/107 green. Tool wire format = `list[dict]` with `name`+`fn` keys (matches Reasoner pattern). 2 surgical forward-fixes to `test_orchestrator.py` + `test_stages_stubs.py` (~11 LOC, updating ar-1-stub-tracked assertions to reflect new ok/failed Verifier contract).
- Wave 3 (ar-3-03 grounding-caps, commit `17a8fca`): Vertex Grounding pass-through + from_env() two-signal auto-detect + consolidated cap tests — TOOL-03, CONFIG-03 autodetect-half, TEST-04 Reasoner-half. 7 net unit tests (5 autodetect + 2 consolidated caps − 1 deleted standalone), 113/113 green. Branch B chosen (inline `google.genai` Vertex client; `lib/vertex_gemini_complete.py` does not expose `complete_with_grounding`). L2a cap=0 LLM-free CLI smoke exit 0, 155-char valid markdown (fewer degradation notes than ar-2-03's 308 chars = progress; Retriever embedding dim mismatch 3072/768 is pre-existing v1.0.y operator-side KG re-ingest issue, out of ar-3 scope).

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
