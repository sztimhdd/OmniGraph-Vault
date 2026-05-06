# Requirements: Agentic-RAG-v1

**Defined:** 2026-05-06
**Core value:** Internalize the agentic RAG flow as a stand-alone Python lib + ONE skill, removing Hermes-runtime dependency for non-Hermes consumers.

**Source of truth:** `docs/design/agentic_rag_internal_api.md` (10 architectural axes + 10 closed requirement questions, 2026-05-06).
**Ground truth for smoke test:** `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`.

Every requirement below traces to a specific design-doc decision. Categories
are derived from the design doc's structure (lib API, stage orchestration,
external tools, skill packaging, CLI surface, env config, tests, cross-milestone
contract).

---

## v1 Requirements

### Library / orchestrator core (LIB)

Maps design doc § "Library API design rules" + § "Stage data contracts".

- [ ] **LIB-01**: `lib/research/` Python package exists; `__init__.py` exports `research`, `research_stream`, `ResearchConfig`, `ResearchResult`, `ResearchState`, `Source`. Per-stage dataclasses (`WebBaseline`, `RetrieverOutput`, `ReasonerOutput`, `VerifierOutput`, `SynthesizerOutput`, `RetrievedImage`) accessible via `lib.research.types` submodule for advanced consumers (HTTP wrapper, CLI `--dump-state`); not re-exported at top level
- [ ] **LIB-02**: Five stage-output dataclasses (`WebBaseline`, `RetrieverOutput`, `ReasonerOutput`, `VerifierOutput`, `SynthesizerOutput`) plus two helper dataclasses (`Source`, `RetrievedImage`) match design § Stage data contracts schema. The first four (intermediate stages) carry `status: Literal["ok","skipped","failed"]` + `reason: str | None`. `SynthesizerOutput` is terminal — degradation surfaced via `note_lines: list[str]` per Axis 8, NOT a status field
- [ ] **LIB-03**: `ResearchState` dataclass holds `query`, `timestamp_start`, and one nullable field per stage (`web_baseline`, `retrieved`, `reasoned`, `verified`, `synthesized`)
- [ ] **LIB-04**: `async def research(query: str, config: ResearchConfig) -> ResearchResult` is the only top-level entrypoint; pure async function; no `print`, no file I/O, no `argv` parsing in the lib (Rule 1)
- [ ] **LIB-05**: Lib has zero module-level singletons; LightRAG client / vision cascade / web-search clients are all injected via `ResearchConfig` (Rule 2)
- [ ] **LIB-06**: `ResearchConfig` reads env vars exactly once at construction; hot path uses dataclass fields only — no `os.environ[...]` scattered through role modules (Rule 3)
- [ ] **LIB-07**: `ResearchConfig.output_dir` and `ResearchConfig.telemetry_jsonl` are nullable; default-null run produces no file I/O (Rule 4)
- [ ] **LIB-08**: `async def research_stream(query, config) -> AsyncIterator[Event]` exists alongside `research()`; emits incremental progress events (Rule 5)
- [ ] **LIB-09**: Package is importable as `omnigraph.research` (matching `python -m omnigraph.research` in CLI-01). Phase 1 picks ONE of: (a) keep `lib/research/` and add namespace mapping in `setup.py`/`pyproject.toml` so `omnigraph.research` resolves to it, OR (b) rename physical path to `omnigraph/research/`. Choice + rationale documented in module README. Resolves design-doc internal inconsistency between line 25 (`omnigraph.research_api`), line 287 (`omnigraph.research`), and line 625 (`lib/research/`)

### Stage orchestration (ORCH)

Maps design doc § Axis 1 (5-stage pipeline + 2 agent-loops) + Axis 3 (best-effort) + Axis 6 (Reasoner-as-vision-host) + Axis 10 (output language).

- [ ] **ORCH-01**: WebBaseline stage runs broad public web search via `config.web_search` (a `Callable[[str], list[dict]]`); on Tavily failure (error/quota/timeout) falls back to `config.web_search_fallback`; never raises. WebBaseline maps the tools' `list[dict]` results into `list[Source]` internally before writing to state — `Source` does NOT cross the tool boundary
- [ ] **ORCH-02**: Retriever stage wraps `omnigraph_search.query.search(query, mode="hybrid")` and surfaces image candidates by globbing `~/.hermes/omonigraph-vault/images/{article_hash}/` for each `article_hash` mentioned in the returned text. Article hashes are 10-char hex strings (existing convention, see image directory layout); extract via regex `\b[0-9a-f]{10}\b` against `search()` return text. Implementation may refine the pattern if false-positive rate is observed in smoke test
- [ ] **ORCH-03**: Reasoner stage executes a bounded LLM agent loop with tools `kg_search(query, top_k)` and `vision_analyze(image_path, question)`; loop capped by `config.max_iter_reasoner` (default 5); returns `iter_count` in output
- [ ] **ORCH-04**: Verifier stage executes a bounded LLM agent loop with tools `web_search`, `web_extract`, optional `google_search_grounding`; loop capped by `config.max_iter_verifier` (default 3); returns `iter_count` in output
- [ ] **ORCH-05**: Synthesizer stage produces final markdown with image embeds anchored to vision captions; reads stage stubs and **appends** (not prepends) a single visible degradation note line at the end of the markdown for each stage with `status != "ok"` (e.g., `> ℹ️ Verifier skipped: API quota exhausted.`) — per Axis 8
- [ ] **ORCH-06**: Best-effort failure handling: every stage returns a stub with `status="skipped"` or `status="failed"` + `reason=...` rather than raising; no single role can kill the run
- [ ] **ORCH-07**: Synthesizer prompt detects query language and outputs full answer in same language (mixed-query default to dominant); no separate translation step
- [ ] **ORCH-08**: Orchestrator (or skill/CLI wrapper) ensures local image HTTP server (`python -m http.server 8765 --directory <BASE_IMAGE_DIR>`) is running before Synthesizer emits image-embedded markdown. If not detected, auto-starts in background. Mirrors Hermes behavior at `session_20260506_105324_b7b9f4.json` msg 27. Phase planner picks the boundary (lib vs wrapper) at implementation time
- [ ] **ORCH-09**: Pipeline executes stages in strict sequential order: WebBaseline → Retriever → Reasoner → Verifier → Synthesizer. Parallelism is permitted ONLY within a single stage's internal agent loop or in tool batch calls (e.g., Reasoner running 3 `vision_analyze` in parallel). Inter-stage reordering or parallelization is prohibited per Axis 1

### External tools (TOOL)

Maps design doc § Axis 9 (Tavily + Brave + Grounding) + Finding 1 (vision-cascade reuse).

- [ ] **TOOL-01**: Tavily REST integration — `web_search: Callable[[str], list[dict]]` and `web_extract: Callable[[str], str]` callables, configured via `TAVILY_API_KEY`. Returned `list[dict]` shape is the tool's native shape; `Source` mapping happens in-stage (see ORCH-01)
- [ ] **TOOL-02**: Brave REST integration — `web_search_fallback: Callable[[str], list[dict]]`, configured via `BRAVE_SEARCH_API_KEY`; invoked only when primary Tavily errors/quotas/times out. Same dict-not-Source contract as TOOL-01
- [ ] **TOOL-03**: Vertex Gemini Grounding integration — `google_search_grounding` tool added to Verifier registry ONLY when `config.llm_complete` is detected as Vertex Gemini (opt-in)
- [ ] **TOOL-04**: Reasoner uses existing `lib/vision_cascade.py` via the `vision_analyze(image_path, question)` tool — no new vision infrastructure introduced this milestone

### Skill packaging (SKILL)

Maps design doc § "Skill exposure principle: orchestration is internal".

- [ ] **SKILL-01**: `skills/omnigraph_research/SKILL.md` published with frontmatter (`name`, `description`, `triggers`, `metadata.openclaw.requires`); description is concise, single-line, accuracy-critical (Level 0 visibility)
- [ ] **SKILL-02**: `skills/omnigraph_research/scripts/research.sh` thin wrapper validates env vars then invokes the Python CLI; ~50 lines max; references README.md for human-facing docs
- [ ] **SKILL-03**: ONLY ONE new skill in this milestone — internal stages (web baseline / retriever / reasoner / verifier / synthesizer / vision) NEVER exposed as separate skills (hard constraint per design doc § Skill exposure)
- [ ] **SKILL-04**: `omnigraph_research` coexists with `omnigraph_search` and `omnigraph_query` (does not subsume them); README documents the cost/quality/latency table
- [ ] **SKILL-05**: Skill directory follows standard layout per CLAUDE.md § "Skill Directory Structure": `SKILL.md` (required), `scripts/research.sh` (required), `references/` (optional, advanced docs), `README.md` (human install + usage docs)

### CLI surface (CLI)

Maps design doc § "Library API design rules" Rule 4 + Skill exposure § "intermediate-state visibility for debugging is a CLI flag, NOT a new skill".

- [ ] **CLI-01**: `python -m omnigraph.research "<query>"` runs the lib end-to-end and prints final markdown to stdout; exit code 0 on success
- [ ] **CLI-02**: `--dump-state <path>` flag writes the full `ResearchState` JSONL (per-stage) to the given path for debug
- [ ] **CLI-03**: CLI supports `--max-iter-reasoner`, `--max-iter-verifier`, `--no-grounding` overrides (REQ-introduced, not in design doc — Phase planner may refine names); works from any cwd; no hardcoded paths. **LLM provider selection is env-only** via `OMNIGRAPH_LLM_PROVIDER` — NO CLI override (simplicity per § "Library API design rules" Rule 3)

### Environment / config wiring (CONFIG)

Maps design doc § Axis 9 (env vars) + § Library API design rules Rule 3.

- [ ] **CONFIG-01**: `TAVILY_API_KEY` env var read by `ResearchConfig` constructor; clear error message when missing and Tavily is selected as primary
- [ ] **CONFIG-02**: `BRAVE_SEARCH_API_KEY` env var read by `ResearchConfig` constructor; clear log line when missing (silently demotes fallback)
- [ ] **CONFIG-03**: `ResearchConfig.from_env()` factory auto-detects whether `llm_complete` is Vertex Gemini and auto-adds `google_search_grounding` to Verifier tool registry when so. Detection mechanism: `llm_complete.__module__ == "lib.vertex_gemini_complete"` OR `OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"` env var (whichever the implementer prefers; both must result in Grounding enablement)

### Tests / smoke (TEST)

Maps design doc § "Smoke test (acceptance criterion for milestone done)".

- [ ] **TEST-01**: Unit tests for each stage's data contract — fields present, status defaults to `"ok"`, reason defaults to `None`
- [ ] **TEST-02**: Mock-based test exercises Tavily failure → Brave fallback path; asserts `web_search_fallback` is called exactly once per failed primary call
- [ ] **TEST-03**: Mock-based test exercises Reasoner agent loop calling `vision_analyze` ≥1 time and embedding the caption into the synthesizer's input; asserts vision-cascade was invoked
- [ ] **TEST-04**: Mock-based tests for `max_iter_reasoner` and `max_iter_verifier` cap enforcement — looping LLM is forced to `iter_count == cap` then loop terminates without raising
- [ ] **TEST-05**: Smoke test on `"Hermes Harness 深度解析"` produces markdown that satisfies all five pass conditions: ≥3 inline images via `![desc](http://localhost:8765/...)`, `state.verified.confidence >= 60`, wall time ≤ 120 s, no stage with `status="failed"`, answer language Chinese. (depends on ORCH-08 image server being up)
- [ ] **TEST-06**: Side-by-side review vs `session_20260506_105324_b7b9f4.json` Telegram answer scores ≥3/5 on each of 5 dimensions: coverage breadth, technical depth, philosophical framing, source attribution, image relevance. **Manual review** performed by milestone owner at the milestone-close gate (NOT per-Phase). Scores recorded in `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`. This is the only subjective gate; eval framework remains out-of-scope (Q8)

### Cross-milestone contract (CONTRACT)

Maps design doc § "Cross-milestone KG API contract".

- [ ] **CONTRACT-01**: `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` is the ONLY KG-side dependency referenced from `lib/research/`; no other `omnigraph_search.*` import allowed in this milestone's code. **Enforced via** grep-based pre-commit hook (`grep -r 'from omnigraph_search' lib/research/ | grep -v 'omnigraph_search.query'` must be empty) OR documented code-review checklist if hook infra unavailable; Phase 1 implementer picks
- [ ] **CONTRACT-02**: Filesystem dependency consumed via `config.BASE_IMAGE_DIR` constant (env-driven by `OMNIGRAPH_BASE_DIR` per CLAUDE.md; do NOT confuse `BASE_IMAGE_DIR` with an env var). Orchestrator MUST NOT hardcode `~/.hermes/omonigraph-vault/images/` — always read through `config.py`

---

## Future Requirements (deferred)

Tracked but not in current roadmap.

### HTTP endpoint

- **HTTP-01**: FastAPI server `server/api.py` exposes `POST /research` returning `application/json` with `ResearchResult` JSON
- **HTTP-02**: SSE streaming variant `POST /research/stream` for incremental rendering
- **HTTP-03**: Auth via single shared bearer token (env var); single-user scope

Design rules in LIB-04 / LIB-05 / LIB-08 guarantee this is ~50 lines of FastAPI;
not pre-built per scope decision.

### Cognee / query-history injection

- **COG-01**: Optional `CogneeRecall` stage between WebBaseline and Retriever, gated by `config.use_cognee`
- **COG-02**: `query_history.jsonl` (HYG-03) injection as follow-up context, gated separately

Deferred until v3.4 Phase 20/21 + Cognee revival lands. Design Axis 7.

---

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Eval framework | Hobby project, defer indefinitely (design Q8) |
| Cost cap mechanism | ~$0.05/run measured; not a concern at single-user scale (design Q9) |
| Multi-turn UX / interactive follow-up | One-shot only; design Q5 |
| Multi-language translation step | Modern LLMs are language-agnostic; one prompt instruction suffices (Q7) |
| LLM A/B vs Sonnet/Opus | DeepSeek-v4-pro empirically sufficient per Hermes session evidence (Q1) |
| HTTP endpoint pre-build | Future Phase via design Rules 1-5; not built in v1 |
| Tavily / Brave API key procurement | Operator task, not a code requirement |
| Replacement of `omnigraph_search` / `omnigraph_query` skills | Coexistence, not subsumption (design § Skill exposure) |
| Internal stages exposed as separate skills | Hard constraint per design § Skill exposure (counter-pattern) |
| Re-derivation of design decisions | Design doc treated as final; no re-discussion |

---

## Traceability

Populated by `gsd-roadmapper` 2026-05-06.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIB-01 | ar-1 | Pending |
| LIB-02 | ar-1 | Pending |
| LIB-03 | ar-1 | Pending |
| LIB-04 | ar-1 | Pending |
| LIB-05 | ar-1 | Pending |
| LIB-06 | ar-1 | Pending |
| LIB-07 | ar-1 | Pending |
| LIB-08 | ar-4 | Pending |
| LIB-09 | ar-1 | Pending |
| ORCH-01 | ar-1 | Pending |
| ORCH-02 | ar-1 | Pending |
| ORCH-03 | ar-2 | Pending |
| ORCH-04 | ar-3 | Pending |
| ORCH-05 | ar-2 | Pending |
| ORCH-06 | ar-1 | Pending |
| ORCH-07 | ar-1 | Pending |
| ORCH-08 | ar-1 | Pending |
| ORCH-09 | ar-1 | Pending |
| TOOL-01 | ar-3 | Pending |
| TOOL-02 | ar-3 | Pending |
| TOOL-03 | ar-3 | Pending |
| TOOL-04 | ar-2 | Pending |
| SKILL-01 | ar-1 | Pending |
| SKILL-02 | ar-1 | Pending |
| SKILL-03 | ar-1 | Pending |
| SKILL-04 | ar-1 | Pending |
| SKILL-05 | ar-1 | Pending |
| CLI-01 | ar-1 | Pending |
| CLI-02 | ar-4 | Pending |
| CLI-03 | ar-2 | Pending |
| CONFIG-01 | ar-1 | Pending |
| CONFIG-02 | ar-1 | Pending |
| CONFIG-03 | ar-3 | Pending |
| TEST-01 | ar-1 | Pending |
| TEST-02 | ar-3 | Pending |
| TEST-03 | ar-2 | Pending |
| TEST-04 | ar-3 | Pending |
| TEST-05 | ar-4 | Pending |
| TEST-06 | ar-4 | Pending |
| CONTRACT-01 | ar-1 | Pending |
| CONTRACT-02 | ar-1 | Pending |

**Coverage:**

- v1 requirements: 41 total (LIB:9 / ORCH:9 / TOOL:4 / SKILL:5 / CLI:3 / CONFIG:3 / TEST:6 / CONTRACT:2)
- Mapped to phases: 41 ✓
- Unmapped: 0 ✓

**Phase distribution:** ar-1 (25) / ar-2 (5) / ar-3 (7) / ar-4 (4) = 41 ✓

---
*Requirements defined: 2026-05-06*
*Last updated: 2026-05-06 — phase mapping populated by `gsd-roadmapper` after roadmap creation. Previous update: independent review (3 BLOCK + 10 FLAG + 3 NIT applied: LIB-02 stage-output count corrected; LIB-09 added for package-import path; TOOL-01/02 callable signatures realigned to design `Callable[[str], list[dict]]`; ORCH-02 article-hash regex pinned; ORCH-05 changed to append-only per Axis 8; ORCH-08 image-server auto-bring-up added; ORCH-09 strict pipeline order added; SKILL-05 standard skill layout added; CLI-03 LLM-provider env-only clarified; CONFIG-03 Vertex detection mechanism pinned; TEST-05 cross-ref ORCH-08; TEST-06 manual-review owner + audit file; CONTRACT-01 enforcement mechanism added; CONTRACT-02 BASE_IMAGE_DIR clarified as constant not env var)*
