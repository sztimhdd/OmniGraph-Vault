# OmniGraph-Vault — Parallel Milestone: Agentic-RAG-v1

> Sibling milestone running parallel to v3.4 (RSS-KOL Alignment, Phases 20-22).
> Main project context lives in `PROJECT.md`. This file scopes Agentic-RAG-v1 only.
> Phase directories use the `ar-N-*` prefix to avoid collision with v3.4 phases 19-22.

## What This Milestone Is

Internalize the agentic RAG flow as a stand-alone Python lib in OmniGraph-Vault,
exposed as ONE new skill (`omnigraph_research`). Removes the dependency on Hermes
runtime for non-Hermes consumers — the same lib backs the skill, a CLI, and (in
a future Phase) an HTTP endpoint for a wiki / RAG bot / Claude Code skill via MCP.

**Locked design doc:** `docs/design/agentic_rag_internal_api.md` (treated as final;
all 10 requirements + 10 architecture axes closed 2026-05-06).

**Ground-truth reference:** `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`
(Hermes "Hermes Harness 深度解析" Telegram answer; smoke-test baseline).

## Goal

A `lib/research/` Python package + `skills/omnigraph_research/` skill that takes a
natural-language query and returns an image-rich Markdown answer, end-to-end,
without depending on the Hermes agent loop.

Single user-facing capability: **"run a deep research."** Internal stages
(WebBaseline, Retriever, Reasoner, Verifier, Synthesizer, Vision) are NEVER
exposed as separate skills (hard constraint per design doc § Skill exposure
principle).

## Locked Architectural Choices (do NOT re-discuss)

- **5-stage outer pipeline:** WebBaseline → Retriever → Reasoner → Verifier → Synthesizer
- **Two embedded LLM agent-loops** with caps:
  - Reasoner: tools `kg_search` + `vision_analyze`; `max_iter_reasoner=5`
  - Verifier: tools `web_search` + `web_extract` + (opt-in) `google_search_grounding`; `max_iter_verifier=3`
- **Lib + thin wrappers** — orchestrator in `lib/research/`; skill / CLI / future-HTTP wrappers each ~50 lines
- **Vision is Reasoner's tool, NOT a separate stage** — reuses `lib/vision_cascade.py`
- **DeepSeek-v4-pro default LLM**; Sonnet/Opus reserved for adversarial debugging
- **Tavily REST primary + Brave REST fallback**; Vertex Gemini Grounding opt-in when `llm_complete` is Vertex
- **Best-effort failure handling** — every stage returns `status ∈ {ok, skipped, failed}`; no stage can kill the run
- **Output language matches query language** (single prompt instruction; no translation step)
- **Lightweight dataclasses** — `~7` plain Python `@dataclass`es, no Pydantic, no schema versioning
- **HTTP-ready by 5 design rules** — pure async entrypoint, no global state, dataclass config, opt-in side effects, streaming peer

## Cross-Milestone Contract

The Agentic-RAG-v1 milestone depends on the OmniGraph KG side via **a single
function signature**:

```python
# omnigraph_search/query.py — KG team must NOT break this
async def search(query_text: str, mode: str = "hybrid") -> str: ...
```

Plus filesystem read-only access to image storage layout
`~/.hermes/omonigraph-vault/images/{article_hash}/{N}.jpg`.

KG team is FREE to change LightRAG version, embedding model, storage backend,
canonical-map implementation, retrieval algorithm, and internal prompt templates.
A `search_raw(query, mode) -> dict` may be added later without breaking v1.

## Smoke Test (acceptance criterion)

Single curated query end-to-end: `"Hermes Harness 深度解析"`.

**Pass conditions** (all must hold):

1. Output markdown contains ≥ 3 inline images via `![desc](http://localhost:8765/...)` syntax
2. `state.verified.confidence >= 60`
3. End-to-end wall time ≤ 120 s
4. JSONL telemetry shows no stage with `status="failed"` (`status="skipped"` is acceptable)
5. Answer language is Chinese (validates Axis 10)

**Side-by-side review** vs `session_20260506_105324_b7b9f4.json`:
score 5 dimensions (coverage breadth, technical depth, philosophical framing,
source attribution, image relevance) on 0-5; pass = ≥3/5 on each
(not required to "win", but must not be visibly inferior).

## Out of Scope (do NOT include in any phase)

| Item | Why excluded |
|------|--------------|
| Eval framework | Hobby project, deferred indefinitely (Q8) |
| Cost cap mechanism | ~$0.05/run measured; not a concern at single-user scale (Q9) |
| Multi-turn UX | One-shot only; no interactive follow-up |
| Cognee / query-history injection | Cognee retired 2026-05-10 (quick 260510-gfg, commit `608372e`); memory layer if needed will be designed inside ar-* phase per AGNT-MEM-01 placeholder. |
| HTTP endpoint pre-build | Future Phase within milestone; design rules guarantee easy add (~50 lines FastAPI) |
| Tavily/Brave API key procurement | Operator task, not design |
| Multi-language translation | Modern LLMs are language-agnostic (Q7) |
| LLM A/B vs Sonnet/Opus | DeepSeek-v4-pro empirically sufficient (Q1) |

## Tech Stack (additions only)

Existing: see main `PROJECT.md`.

**New runtime deps for this milestone:**

- `tavily-python` SDK — Tavily REST web search/extract (primary)
- Brave REST API (direct `requests` call; no SDK needed) — fallback
- `vertexai` (already present) — Grounding tool, opt-in

**No new infra.** Vision uses existing `lib/vision_cascade.py`. KG uses existing
`omnigraph_search/query.py`. LLM uses existing `lib/llm_deepseek.py` /
`lib/vertex_gemini_complete.py`.

## Naming Map

| Object | Name |
|--------|------|
| Milestone | **Agentic-RAG-v1** |
| Python package path | `lib/research/` |
| Skill name | `omnigraph_research` |
| Skill directory | `skills/omnigraph_research/` |
| Phase dirs | `.planning/phases/ar-N-*/` |
| Sibling planning files | `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-Agentic-RAG-v1.md` |

## Parallel-Track Constraint

This milestone runs alongside v3.4 (RSS-KOL) Phases 20-22:

- **KG main-line work (v3.4)** is FREE to change LightRAG internals, embeddings,
  canonical map, etc., **as long as `omnigraph_search.query.search(query_text, mode)`
  signature stays stable.**
- **Agentic-RAG-v1** does NOT touch any v3.4 file outside the contract.
- Resources (developer attention, Hermes test slots) shared but coordinated via
  GSD state files; v3.4's `STATE.md` and Agentic-RAG-v1's `STATE-Agentic-RAG-v1.md`
  evolve independently.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "Goal" still accurate? → Update if drifted

**After milestone close** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Smoke test pass-or-not — captured in closure doc
3. Audit Out of Scope — reasons still valid?
4. Update main `PROJECT.md` to fold validated capabilities into project record

---
*Last updated: 2026-05-06 — milestone initialized via `/gsd:new-milestone Agentic-RAG-v1`.*
