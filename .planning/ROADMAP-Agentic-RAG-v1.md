# Roadmap: Agentic-RAG-v1

**Milestone:** Agentic-RAG-v1 (parallel-track to v3.4)
**Created:** 2026-05-06
**Phase prefix:** `ar-N` (avoids collision with v3.4 phases 19-22)
**Granularity:** Standard (4 phases for 41 v1 REQs)
**Coverage:** 41/41 requirements mapped

> **Locked design:** `docs/design/agentic_rag_internal_api.md` — treated as final, no re-derivation.
> **Cross-milestone contract:** `omnigraph_search.query.search(query_text, mode)` is the ONLY KG-side dependency. Read-only.

---

## Phase decomposition rationale

**Decomposition style chosen: vertical-slice MVP-first.**

Three reasons drive the choice:

1. **Risk concentration is at integration points, not individual stages.** The 7 dataclasses are dictated verbatim by the design doc — they have zero design ambiguity. The real risk is "do all 5 stages compose into a working pipeline at all?" An orchestrator-first decomposition would defer that question to the last phase; vertical-slice answers it on Day 1.
2. **The smoke test (TEST-05) is a Chinese-language deep-dive that touches every stage.** A stub-pipeline that produces *some* end-to-end output, even if shallow, surfaces async-boundary, config-injection, and contract-isolation bugs when fixes are cheap. Deepening Reasoner / Verifier behavior in subsequent phases is incremental, not architectural.
3. **The two LLM agent loops (Reasoner, Verifier) are the highest behavioral risk.** Vertical-slice forces a deterministic-stub version of each loop to exist from Day 1, which fixes the loop's interface to `ResearchState` before the LLM-driven version is wired in. This is exactly the "scaffold-then-fill" pattern the author's instinct points at.

**Counter-rationale considered (orchestrator-first):** would simplify ar-1 to "just dataclasses + skeleton" and push all stage logic to ar-2..ar-N. Rejected because (a) the lib has only ~7 dataclasses + 5 trivial stage shells; the orchestrator-first scaffold is so thin that splitting it from a vertical slice creates artificial boundaries, and (b) it would defer the "does anything actually run end-to-end?" answer to ar-2, raising integration cost.

**Phase count: 4** — below 4 bundles too much risk into one phase; above 4 creates artificial splits between Reasoner-deepening and Verifier-deepening that aren't independent (both share agent-loop scaffolding, telemetry plumbing, and prompt-engineering iterations).

---

## Phases

- [ ] **Phase ar-1: MVP vertical slice** — End-to-end skeleton runs (skill→CLI→lib→all 5 stages stubbed→markdown out); smoke executes without crashing.
- [ ] **Phase ar-2: Reasoner + vision deepening** — Real LLM agent loop in Reasoner with `kg_search` + `vision_analyze` tools, cap enforcement, image-caption anchoring in Synthesizer output.
- [ ] **Phase ar-3: Verifier + web tools** — Real LLM agent loop in Verifier; Tavily primary + Brave fallback + Grounding opt-in; fact-check confidence scoring.
- [ ] **Phase ar-4: Telemetry, streaming, smoke pass + milestone audit** — JSONL telemetry, `research_stream()` event emission, `--dump-state` debug flag, smoke test all 5 pass conditions, manual side-by-side audit at milestone close.

---

## Phase Details

### Phase ar-1: MVP vertical slice
**Goal:** End-to-end skeleton runs from skill trigger through all 5 stages and emits a markdown answer without crashing — even if the answer is shallow or stub-quality.
**Depends on:** Nothing (first phase).
**Requirements:** LIB-01, LIB-02, LIB-03, LIB-04, LIB-05, LIB-06, LIB-07, LIB-09, ORCH-01, ORCH-02, ORCH-06, ORCH-07, ORCH-08, ORCH-09, SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, CLI-01, CONFIG-01, CONFIG-02, TEST-01, CONTRACT-01, CONTRACT-02 (25 REQs)
**Success Criteria** (what must be TRUE):
  1. `python -m omnigraph.research "test query"` exits 0 and prints a non-empty markdown answer to stdout (CLI-01 + ORCH-01..02..05..06 stubs)
  2. `skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json` is green for at least the trigger-routing test cases (SKILL-01..05)
  3. Stages execute in strict WebBaseline → Retriever → Reasoner → Verifier → Synthesizer order and every stub stage returns `status="ok"` or `status="skipped"` — no stage raises (ORCH-06, ORCH-09)
  4. `from omnigraph.research import research, ResearchConfig, ResearchResult` succeeds; `from omnigraph.research.types import WebBaseline, RetrieverOutput, ...` also succeeds (LIB-01, LIB-09)
  5. Cross-milestone contract is enforced: `grep -r 'from omnigraph_search' lib/research/ | grep -v 'omnigraph_search.query'` returns empty; `BASE_IMAGE_DIR` is consumed only via `config.py`, never hardcoded (CONTRACT-01, CONTRACT-02)
  6. Local image HTTP server on port 8765 is running (or auto-started) before any markdown with image embeds is emitted (ORCH-08)
**Plans:** TBD
**Notes:**
- LIB-08 (`research_stream`) is intentionally deferred to ar-4. ar-1 implements `research()` only.
- LLM agent loops in Reasoner/Verifier are stubbed with deterministic placeholders (e.g., Reasoner picks first 3 images by glob order; Verifier returns hardcoded `confidence=70.0`). The real loops land in ar-2 / ar-3.
- TEST-01 (dataclass unit tests) is in ar-1 because the dataclasses are defined here. Subsequent phases add behavioral tests (TEST-02..04) for the parts they introduce.
- LIB-01 cross-phase touch: subsequent phases will add new exports as new functionality lands; the `__init__.py` is owned by ar-1 but appended-to by later phases.
- CONFIG-01 / CONFIG-02 read env vars *at config construction* even though Tavily / Brave are not yet wired (stub callables can be installed in `web_search` / `web_search_fallback` slots). Real wiring is ar-3.
- CLI-01 has only the bare `<query>` positional in ar-1; flags `--max-iter-*`, `--no-grounding`, `--dump-state` land in ar-2 / ar-4 (CLI-03 / CLI-02).

---

### Phase ar-2: Reasoner + vision deepening
**Goal:** Reasoner becomes a real LLM agent loop that selects KG chunks and images intelligently; Synthesizer emits markdown with image embeds anchored to vision-generated captions.
**Depends on:** Phase ar-1 (needs `ResearchState`, stub Reasoner shell, `vision_cascade` integration point, Synthesizer skeleton).
**Requirements:** ORCH-03, ORCH-05, TOOL-04, CLI-03, TEST-03 (5 REQs)
**Success Criteria** (what must be TRUE):
  1. Reasoner executes a bounded LLM agent loop with `kg_search(query, top_k)` and `vision_analyze(image_path, question)` as tools; loop terminates at `iter_count <= max_iter_reasoner` (default 5) and returns `iter_count` in `ReasonerOutput` (ORCH-03)
  2. Synthesizer's emitted markdown contains inline `![desc](http://localhost:8765/...)` image references where `desc` is anchored to a vision-generated caption from `ReasonerOutput.analyzed_images`, not a placeholder (ORCH-05)
  3. Reasoner uses `lib/vision_cascade.py` directly for `vision_analyze` (no new vision infrastructure introduced — verified by import-graph inspection) (TOOL-04)
  4. CLI accepts `--max-iter-reasoner`, `--max-iter-verifier`, and `--no-grounding` flags; values propagate into `ResearchConfig` and override defaults (CLI-03). Note: `--no-grounding` is plumbed-but-no-op until ar-3 wires Grounding.
  5. Mock-based test exercises Reasoner agent loop calling `vision_analyze` ≥1 time and confirms the resulting caption is embedded in Synthesizer's input prompt (TEST-03)
**Plans:** TBD
**UI hint:** no
**Notes:**
- ORCH-05 belongs in ar-2 (not ar-1) because the *quality* of image-caption anchoring is what distinguishes a real Synthesizer from the ar-1 stub. The ar-1 stub Synthesizer can emit raw image URLs; ar-2 makes them caption-anchored.
- CLI-03 is in ar-2 because `--max-iter-reasoner` is meaningful only after the Reasoner loop is real. `--max-iter-verifier` flag is plumbed in ar-2 but enforces a real cap only after ar-3 lands the Verifier loop. This is intentional — flag plumbing is cheap, behavior delivery follows naturally.

---

### Phase ar-3: Verifier + web tools (Tavily / Brave / Grounding)
**Goal:** Verifier becomes a real LLM agent loop that fact-checks the Reasoner's output against external web sources; Tavily primary + Brave fallback + Vertex Grounding opt-in.
**Depends on:** Phase ar-2 (needs deepened Reasoner output for Verifier to consume).
**Requirements:** ORCH-04, TOOL-01, TOOL-02, TOOL-03, CONFIG-03, TEST-02, TEST-04 (7 REQs)
**Success Criteria** (what must be TRUE):
  1. Verifier executes a bounded LLM agent loop with tools `web_search`, `web_extract`, and conditionally `google_search_grounding`; loop terminates at `iter_count <= max_iter_verifier` (default 3) and returns `iter_count` and a real `confidence: float` in `VerifierOutput` (ORCH-04)
  2. Tavily REST integration is live: `web_search` callable hits Tavily API and returns `list[dict]`; `web_extract` callable hits Tavily extract endpoint (TOOL-01)
  3. Brave REST integration is live: `web_search_fallback` is invoked when Tavily errors, quotas, or times out — verified by mock-based test that asserts the fallback is called exactly once per failed primary call (TOOL-02, TEST-02)
  4. `ResearchConfig.from_env()` auto-detects Vertex Gemini `llm_complete` (via `__module__ == "lib.vertex_gemini_complete"` OR `OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"`) and adds `google_search_grounding` to Verifier tool registry only in that case; `--no-grounding` flag from ar-2 now enforces opt-out (TOOL-03, CONFIG-03)
  5. Mock-based tests confirm cap enforcement on both loops: Reasoner's `iter_count` reaches `max_iter_reasoner` and terminates without raising; Verifier's `iter_count` reaches `max_iter_verifier` and terminates without raising (TEST-04)
**Plans:** TBD
**Notes:**
- TEST-04 covers BOTH loops (Reasoner cap + Verifier cap). Reasoner cap is technically testable starting ar-2, but consolidating both cap tests in ar-3 reduces duplication and lets one mock harness cover both loops.
- Brave fallback (TOOL-02) is tested with mocks (TEST-02) before going live — the order is: implement Tavily, implement Brave, write mock test, then run live integration smoke (informal — no live API smoke required for ar-3 close; that's TEST-05 in ar-4).
- CONFIG-03 enforcement check: feeding `ResearchConfig` two different `llm_complete` callables (one Vertex, one DeepSeek) and asserting that `Verifier.tool_registry` differs by exactly one entry (`google_search_grounding`).

---

### Phase ar-4: Telemetry, streaming, smoke pass + milestone audit
**Goal:** Smoke test passes all 5 conditions on `"Hermes Harness 深度解析"`; manual side-by-side audit vs Hermes ground truth scores ≥3/5 on every dimension; streaming + telemetry land for HTTP-readiness.
**Depends on:** Phase ar-3 (needs full pipeline before smoke pass is meaningful).
**Requirements:** LIB-08, CLI-02, TEST-05, TEST-06 (4 REQs)
**Success Criteria** (what must be TRUE):
  1. `async def research_stream(query, config) -> AsyncIterator[Event]` exists alongside `research()` and emits incremental progress events (one per stage minimum, ideally per-tool-call) (LIB-08)
  2. CLI accepts `--dump-state <path>` flag that writes the full `ResearchState` as JSONL (per-stage entries) to the given path; consumable by debug tooling (CLI-02)
  3. Smoke test on `"Hermes Harness 深度解析"` produces markdown that satisfies ALL 5 pass conditions: (a) ≥3 inline `![desc](http://localhost:8765/...)` images, (b) `state.verified.confidence >= 60`, (c) wall time ≤ 120 s, (d) no stage with `status="failed"` in JSONL telemetry, (e) answer language is Chinese (TEST-05)
  4. Manual side-by-side audit vs `session_20260506_105324_b7b9f4.json` Telegram answer: scores ≥3/5 on each of 5 dimensions (coverage breadth, technical depth, philosophical framing, source attribution, image relevance); scores recorded in `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (TEST-06 — milestone-close gate)
**Plans:** TBD
**Notes:**
- TEST-05 is the milestone-close gate. The phase containing TEST-05 (ar-4) gates the entire milestone — completion of ar-4 = completion of Agentic-RAG-v1.
- TEST-06 (manual audit) is performed AT milestone close, not within an individual plan inside ar-4. Treat it as the final gate after ar-4's other plans complete.
- LIB-08 (`research_stream`) lands here rather than ar-1 because (a) it's only useful with real telemetry to stream, (b) HTTP-readiness is a milestone-end concern not a Day-1 scaffolding concern. The blocking `research()` from ar-1 satisfies all earlier phases.
- JSONL telemetry plumbing introduced in ar-4 retroactively benefits all earlier stages — every stage's stub or real output dataclass already carries `status` + `reason`, so writing them to JSONL is purely a sink-layer concern.
- If smoke test fails any of the 5 conditions on first run, debugging happens *within* ar-4 (regression fixes to ar-2 / ar-3 stages are allowed). The phase is not complete until smoke passes.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| ar-1: MVP vertical slice | 0/? | Not started | — |
| ar-2: Reasoner + vision deepening | 0/? | Not started | — |
| ar-3: Verifier + web tools | 0/? | Not started | — |
| ar-4: Telemetry, streaming, smoke + audit | 0/? | Not started | — |

---

## Coverage validation

**41/41 v1 requirements mapped, no orphans, no duplicates.**

| Phase | Count | REQs |
|-------|-------|------|
| ar-1 | 25 | LIB-01, LIB-02, LIB-03, LIB-04, LIB-05, LIB-06, LIB-07, LIB-09, ORCH-01, ORCH-02, ORCH-06, ORCH-07, ORCH-08, ORCH-09, SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, CLI-01, CONFIG-01, CONFIG-02, TEST-01, CONTRACT-01, CONTRACT-02 |
| ar-2 | 5 | ORCH-03, ORCH-05, TOOL-04, CLI-03, TEST-03 |
| ar-3 | 7 | ORCH-04, TOOL-01, TOOL-02, TOOL-03, CONFIG-03, TEST-02, TEST-04 |
| ar-4 | 4 | LIB-08, CLI-02, TEST-05, TEST-06 |
| **Total** | **41** | |

By category breakdown:

- LIB (9): ar-1 has 8, ar-4 has 1 (LIB-08) ✓
- ORCH (9): ar-1 has 6, ar-2 has 2 (ORCH-03, ORCH-05), ar-3 has 1 (ORCH-04) ✓
- TOOL (4): ar-2 has 1 (TOOL-04), ar-3 has 3 (TOOL-01, 02, 03) ✓
- SKILL (5): ar-1 has all 5 ✓
- CLI (3): ar-1 has 1 (CLI-01), ar-2 has 1 (CLI-03), ar-4 has 1 (CLI-02) ✓
- CONFIG (3): ar-1 has 2 (CONFIG-01, 02), ar-3 has 1 (CONFIG-03) ✓
- TEST (6): ar-1 has 1 (TEST-01), ar-2 has 1 (TEST-03), ar-3 has 2 (TEST-02, 04), ar-4 has 2 (TEST-05, 06) ✓
- CONTRACT (2): ar-1 has both ✓

---

## T-shirt effort estimates

Coarse calibration; refined per-plan inside `/gsd:plan-phase`.

| Phase | T-shirt | Reasoning |
|-------|---------|-----------|
| ar-1 | **L** (2-3 days) | 25 REQs but most are scaffolding — package, dataclasses, skill files, CLI entrypoint, all stubs. Real work concentrated in image-server bring-up (ORCH-08) + skill_runner test wiring + cross-milestone contract enforcement (CONTRACT-01 grep hook). |
| ar-2 | **M** (1 day) | 5 REQs but Reasoner agent loop is the most behaviorally complex single piece. Vision integration is glue (TOOL-04 reuses existing cascade). CLI flags are 1-line each. Caption-anchored Synthesizer is prompt iteration. |
| ar-3 | **L** (2-3 days) | Three external API integrations (Tavily / Brave / Grounding) with fallback semantics. Two require live API keys. Mock infrastructure for TEST-02 / TEST-04 needs to handle both async loops. |
| ar-4 | **M** (1 day) | LIB-08 streaming is mostly refactoring `research()` into an event-emitting variant. `--dump-state` is a serialization pass over `ResearchState`. Smoke + audit are observation, not coding — but allow buffer for one or two regression fixes if smoke conditions fail on first try. |

**Milestone total: ~6-8 days of focused work.** Likely longer wall-clock with API key procurement, debugging, and parallel-track context switching against v3.4.

---

## Dependencies

- ar-1 depends on: nothing (greenfield within milestone)
- ar-2 depends on: ar-1 (`ResearchState`, stub Reasoner shell, `vision_cascade` import path, Synthesizer skeleton)
- ar-3 depends on: ar-2 (deepened Reasoner output is what Verifier consumes; CLI flag plumbing from CLI-03)
- ar-4 depends on: ar-3 (full pipeline must work end-to-end before smoke is meaningful)

No phase-internal parallelism is recommended; phases are strictly sequential.

---

## Cross-phase touches (for `/gsd:plan-phase` awareness)

These REQs are first-delivered in the listed phase but have legitimate touch-points in later phases. Document in plan files when those touches happen, but do NOT re-map the REQ.

| REQ | First delivered | Touch-points |
|-----|----------------|--------------|
| LIB-01 | ar-1 | ar-2/ar-3/ar-4 each append new exports to `__init__.py` (e.g., `research_stream` in ar-4) — append-only, no breaking changes |
| ORCH-05 | ar-2 | ar-4 may iterate Synthesizer prompt to hit smoke pass condition #1 (≥3 inline images) — prompt iteration, not contract change |
| ORCH-06 | ar-1 | All later phases must preserve best-effort semantics in their stage upgrades (Reasoner loop fail → status=skipped, not raise) |
| CLI-03 | ar-2 | ar-3 wires `--no-grounding` to real Grounding tool registry (flag exists in ar-2, behavior in ar-3) |

---

## Open notes

- **Operator-side dependencies:** `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` are tracked as CONFIG-01 / CONFIG-02 requirements. ar-1 can complete with these unset (callables are stubbed). ar-3 needs at least Tavily live; Brave can stay mocked until smoke. Coordinate procurement around ar-2 → ar-3 boundary.
- **Parallel-track coordination with v3.4:** ar-3's web-tool integrations and ar-4's streaming touch *no* file outside `lib/research/`, `skills/omnigraph_research/`, `tests/`, or this milestone's planning artifacts. Zero overlap with v3.4 Phases 20-22 expected.
- **No research stage:** Per project memory, design doc is final. `/gsd:plan-phase ar-1` should jump straight from spec → planning → execute, no `research/SUMMARY.md` produced.

---

*Roadmap created: 2026-05-06 by `gsd-roadmapper`.*
*Last updated: 2026-05-06 — initial draft.*
