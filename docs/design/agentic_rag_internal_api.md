# Agentic RAG Internal API — Design Notes (in progress)

**Status**: Discussion-in-progress. **NOT a spec, NOT a commitment.** Captures
findings from the 2026-05-06 session and seeds future GSD planning.

**Origin**: Continuation of `docs/spec/agentic_rag_discussion_2026_05_06.md`
(one-shot context-builder; not committed further). This doc is the
persistent record going forward until a proper GSD phase doc supersedes it.

**Author**: 2026-05-06 session, OmniGraph-Vault main session, Claude (Opus 4.7).

---

## Strategic intent (decided 2026-05-06)

We want to **internalize the full agentic RAG flow** as a stand-alone, callable
component — not bound to Hermes. Concretely:

> 我希望能不依赖 Hermes 就能公布一个 API 让用户可以用各种方式 Query。
> 用户甚至可以拿这个 API 做一个 wiki 或者 RAG bot,亦或者是做一个 Skill
> 让 Claude Code 去更有效地查资料。

**Consumer surfaces (anticipated)**:

- **CLI**: `python -m omnigraph.research_api "<question>"` — for shell users
- **Python module**: `from omnigraph.research_api import answer(...)` — for embedded callers
- **HTTP endpoint** (longer-term): wiki backend, RAG bot, Claude Code skill via MCP

**What this is NOT**:

- Not a replacement for Hermes' agent loop (Hermes uses this; doesn't depend on it)
- Not a distributed/multi-tenant service (single-user, local-first, like the rest of OmniGraph)
- Not a "general-purpose chat agent" — a research-and-synthesis API specifically

---

## What we found by reverse-engineering Hermes (the 12-step flow)

User asked Hermes "Hermes Harness 深度解析" on 2026-05-06 ~10:55 ADT and got back
4 Telegram messages + 3 inline images of high quality. Source: SSH'd to remote
Hermes, found `~/.hermes/sessions/session_20260506_105324_b7b9f4.json`
(downloaded to `docs/queries/hermes_session_2026_05_06/`). Tool-call tally:

| Tool | Count | Role |
|------|-------|------|
| `terminal` | 7 | KG query, image-server bring-up, file find/probe |
| `send_message` | 6 | Telegram delivery (4 msgs + image embeds) |
| `web_search` | 4 | Public baseline (broad → narrow) |
| `todo` | 3 | Internal task tracking |
| `vision_analyze` | 3 | Per-image description (the secret sauce — see Finding 1) |
| `skill_view` | 2 | Self-discovery of available KG skills |
| `session_search` | 1 | Past-session memory check |
| `read_file` | 1 | Read `synthesis_output.md` |
| `web_extract` | 1 | Targeted public deep-dive (3 URLs in one call) |

**Sequence (msg index → tool):**

```
msg 02  session_search "Hermes Harness"
        web_search     "Hermes Harness AI agent framework"

msg 05  web_search × 3 (parallel, refined queries)

msg 09  skill_view omnigraph_query  + skill_view omnigraph_search

msg 12  terminal: bash skills/omnigraph_query/scripts/query.sh "..." hybrid
        → invokes kg_synthesize.py

msg 14  read_file ~/.hermes/omonigraph-vault/synthesis_output.md

msg 16  terminal: probe localhost:8765 image server
        web_extract: 3 URLs in parallel
          - kenhuangus.substack.com/.../harness-paradigm-claude
          - github.com/nousresearch/hermes-agent
          - hermes-agent.nousresearch.com/docs/

msg 19  terminal: find images/*43ccc4b10e* → enumerate KG-stored images

msg 22  vision_analyze × 3 (one per chosen image)

msg 27, 29  terminal: start http.server 8765 (was not running)
msg 31      terminal: curl-verify image server

msg 33+ send_message × 6 (4 telegram texts + image MEDIA: refs)
```

**Cost envelope**: ~12 API calls per full run.
- 4 web_search + 1 web_extract = ~$0.02 (Brave)
- 1 KG query (DeepSeek + Vertex embedding) = ~$0.01
- 3 vision_analyze (SiliconFlow) = ¥0.004 ≈ $0.001
- 1 final synthesis call = ~$0.01-0.02
- **Total: ~$0.05/question**, well within doc's earlier $0.05-0.20 estimate.

**Synthesis LLM was DeepSeek-v4-pro**, NOT Claude. This falsifies the earlier
"need Sonnet/Opus for image-aware synthesis" hypothesis.

---

## Three findings that change the design

### Finding 1: `vision_analyze` is the real "图文并茂" mechanism

Hermes did NOT just feed image paths to the synthesis LLM with an
`IMAGE_URL_DIRECTIVE` prompt directive (which is what `kg_synthesize.py:34-39`
currently does — and gets 0 images out, see `AB_comparison:23`).

Hermes:

1. Used the article hash (43ccc4b10e) returned by KG retrieval to `find` the
   image directory on disk
2. Picked 3 representative images
3. Ran `vision_analyze` on each — explicit per-image LLM pre-pass that
   produced detailed Chinese descriptions
4. Fed those descriptions (anchored to image paths) into the final synthesis
   prompt

So the synthesizer saw not just `images/43ccc4b10e/2.jpg` but also
"this image shows: Harness 运行时架构 - 六大模块围绕 LLM 核心". That's why it
could place each image at the right spot in the answer.

**Implication for our API**: a `vision_analyze` pre-pass MUST be a built-in
stage. We have the infra in `lib/vision_cascade.py` (SiliconFlow → OpenRouter
→ Gemini); reuse it. Don't try to fake this with prompt-only directives —
that path is empirically broken.

### Finding 2: doc's "public-first ordering" is empirically validated

doc's STAGE 1 (public) → STAGE 2 (KG) → STAGE 4 (targeted re-search) ordering
is exactly what Hermes did. Specifically:

- 4 broad web_search BEFORE touching KG
- Then 1 KG query
- Then 1 web_extract on 3 specific URLs (the KG result + broad web results
  surfaced these as worth deep-diving)

→ STAGE 3 (gap detection) does NOT need a separate "detection algorithm" —
it's the LLM agent loop's natural decision after seeing STAGE 2's output.
That's a simplification: we don't need a confidence threshold or coverage
metric in the design.

### Finding 3: `session_search` + `skill_view` are cheap meta-steps worth keeping

- `session_search` ≈ "check past memory" — replaces what Cognee was supposed
  to do. Costs ~10ms (local sqlite/jsonl read).
- `skill_view` lets the agent self-discover available KG tools instead of
  burning context on a static catalog. Costs 1-2 file reads.

If the API is meant to be Claude-Code-Skill-friendly (per strategic intent),
both deserve to be first-class steps in the orchestrator.

---

## Current state of OmniGraph's "agentic" code (honest assessment)

The whole "agentic RAG module" today is one LightRAG `aquery(mode=hybrid)`
call, wrapped in 5 supporting steps:

```
skills/omnigraph_query/SKILL.md
  ↓ leaves web search to "agent default" (line 21, explicit)
skills/omnigraph_query/scripts/query.sh
  ↓ shell wrapper (env validation + venv activation)
kg_synthesize.py (177 lines)
  ├─ canonical_map lookup (DB-first, JSON fallback)
  ├─ query_history.jsonl read (10 most-recent entries)
  ├─ custom_prompt = IMAGE_URL_DIRECTIVE + history + query
  ├─ LightRAG.aquery(mode=hybrid) with DeepSeek + Vertex embedding
  └─ append to query_history.jsonl + write synthesis_output.md
```

**Mapping to doc's 6 stages**:

| Doc STAGE | Today | Where |
|-----------|-------|-------|
| 1 Public | ❌ | Explicitly out-of-scope per `omnigraph_query/SKILL.md:21` |
| 2 KG | ✅ | `kg_synthesize.py:90-148` |
| 3 Gap detection | ❌ | — |
| 4 Targeted re-search | ❌ | — |
| 5 Multi-source synthesis | ⚠️ | LightRAG.aquery's internal LLM call, no multi-source merge |
| 6 Memory | ⚠️ | JSONL append (HYG-03 replaced Cognee, see CLAUDE.md) |

The "agenticness" in this codebase today is **0**. It lives in the **caller**
(Hermes for production, Claude Code agent loop for dev). The strategic intent
is to **move that orchestration in-tree** so non-Hermes consumers can use it.

---

## Component reuse map (what we already have)

| Stage need | What exists | Where | Notes |
|-----------|-------------|-------|-------|
| Web search | Brave MCP (user-scope global) | `mcp__brave-search__brave_web_search` | Main session only — sub-agents can't call MCP per CLAUDE.md |
| Web fetch/extract | WebFetch tool, Tavily MCP | builtin / `mcp__tavily__*` | Available |
| KG query | `omnigraph_search/query.py` (raw) and `kg_synthesize.py` (with prompt) | repo root | Both exist; use raw one and let orchestrator do its own prompt |
| Vision analysis | `lib/vision_cascade.py` (SF/OR/Gemini fallback) | `lib/` | Already production-grade |
| LLM (router + synthesis) | `lib/llm_deepseek.py`, `lib/vertex_gemini_complete.py` | `lib/` | DeepSeek-v4-pro empirically sufficient |
| Image enumeration | `~/.hermes/omonigraph-vault/images/{hash}/` | filesystem | KG retrieval surfaces hash; orchestrator does `find` |
| Image server | `python -m http.server 8765` | manual today | Orchestrator should auto-bring-up if needed |
| Past-query memory | `query_history.jsonl` | runtime data | HYG-03; ~/.hermes/omonigraph-vault/ |
| Session/skill self-discovery | (not present in OmniGraph; Hermes-side) | — | Can be added cheaply if API targets Claude Code skill consumer |

**Missing**: the orchestrator file itself. Estimated ~300-500 lines of Python,
no new infra dependencies.

**Not reusable from Hermes** (Hermes-internal): `session_search`,
`skill_view`, `send_message` (telegram), `todo`. We do NOT need these for an
internal API — they're Hermes-shell concerns.

---

## Requirements questions — all closed 2026-05-06

All 10 closed. Resolution table:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Synthesis LLM: Sonnet vs Opus? | **DeepSeek-v4-pro by default.** Hermes session evidence shows it produces high-quality multi-image output. LLM choice is not the bottleneck. Sonnet/Opus reserved for adversarial debugging only. |
| 2 | STAGE 1 tool selection + ordering: parallel-all vs LLM-routed; web-first vs KG-first | **Tavily primary + Brave fallback + Gemini Grounding (when Vertex)** for STAGE 1 web baseline; Tavily/GitHub/arxiv specialty fanout deferred until evidence shows gap. **Web-first ordering** chosen over KG-first: Hermes 12-step reverse engineering empirically shows broad public baseline first, then KG, then targeted web_extract; A/B data showed KG-only loses on English public-source topics. Architecture pipeline (Axis 1) reflects this: WebBaseline → Retriever → Reasoner → Verifier → Synthesizer. |
| 3 | Gap detection threshold | **No separate detector.** LLM orchestrator handles it implicitly via Verifier-style fact-checking. |
| 4 | Memory layer (Cognee replacement) | **`query_history.jsonl` (HYG-03).** Cognee disabled since Phase 18-02. Append-only JSONL is sufficient. |
| 5 | User UX: command vs auto-detect | **Skill-shaped.** Published as a Hermes/Claude/OpenClaw skill. Input: user question via CLI/Telegram/skill trigger. Output: image-rich markdown answer (md blob), one-shot. No interactive multi-turn. |
| 6 | Image embedding mechanism | **`vision_analyze` pre-pass** + caption-anchored synthesis prompt (per Finding 1). `lib/vision_cascade.py` reused. |
| 7 | Multi-language source merging | **No translation step.** Modern LLMs are language-agnostic; pass mixed-language sources directly to synthesizer. |
| 8 | Eval methodology | **Out of scope.** Hobby project, defer indefinitely. May revisit if quality regressions become a pattern. |
| 9 | Cost cap | **No cap.** Cost not a concern at single-user scale (~$0.05/run measured). |
| 10 | Roadmap placement | **Standalone milestone, parallel development.** Only dependency: KG query API stability. KG team can keep changing KG internals; we depend on the function signatures of `omnigraph_search/query.py` (or equivalent) only. |

**Implications for milestone scope:**

- **In scope**: orchestrator + 4 LLM-driven specialist roles (Retriever / Reasoner / Verifier / Synthesizer) + WebBaseline non-LLM pre-stage + Reasoner's internal vision agent-loop + skill-packaging for 3 surfaces (Hermes/Claude Code/OpenClaw)
- **Out of scope**: eval framework, cost-cap mechanism, multi-turn UX, multi-language translation, LLM A/B against Sonnet/Opus, query-history-as-context (deferred until Cognee plans clarify — see Axis 7)
- **All 10 architectural axes locked** — see "Architecture decisions" section below

---

## Architecture decisions (locked 2026-05-06)

Ten architectural axes, all decided after requirements close.

### Axis 1: Workflow shell with two embedded agent-loops (Hybrid)

- Outer shell is a **fixed 5-stage pipeline**:
  WebBaseline → Retriever → Reasoner → Verifier → Synthesizer
- **Two stages contain bounded LLM agent loops**:
  - **Reasoner** has KG-search and vision-analyze tools — decides which
    deeper KG chunks to fetch and which images to caption. Capped by
    `max_iter_reasoner` (default 5).
  - **Verifier** has web-search/web-extract/grounding tools — decides how
    many to invoke for fact-checking. Capped by `max_iter_verifier`
    (default 3).
- Three stages (WebBaseline, Retriever, Synthesizer) are pure single-call
  steps with no agent loop.
- This bounds non-determinism to two well-isolated stages. Outer-level
  cost, telemetry, debugging stay simple.
- Rejected alternatives: pure Workflow (Google ADK style, no internal
  loops) — too rigid for variable-depth fact-checking and image selection;
  pure Agent-loop (Hermes style, all in one LLM) — non-deterministic, hard
  to test, blocks portability.

### Axis 2: Shared dataclass state

A single `ResearchState` dataclass flows through stages. Each role writes
its own field; no cross-stage mutation of others' fields. The dataclass
serializes to JSONL = automatic per-run telemetry log.

Rejected alternatives: chained pure-function args (loses telemetry shape);
event bus / pub-sub (overkill for single-process).

### Axis 3: Best-effort failure handling

Each role's prompt explicitly instructs how to fail soft: return a stub
with `status="skipped"` + `reason=...` rather than raise. Synthesizer
accepts stubs and downgrades the answer accordingly. No single role can
kill the whole run.

Rejected alternatives: strict (any role fail = whole-run fail) — too
fragile for hobby project with flaky free-tier APIs; cascade-to-cheaper —
overlap with Verifier's internal agent loop, redundant.

### Axis 4: Lib + thin wrappers (NOT skill-IS-orchestrator)

Orchestrator lives in `lib/research/` (or similar Python module). Three
parallel wrappers, all consuming the same lib:

- **Skill wrapper**: `skills/omnigraph_research/scripts/research.sh` —
  minimal shell calling Python CLI
- **CLI wrapper**: `python -m omnigraph.research "<query>"` — for shell users
- **HTTP wrapper** (future Phase): `server/api.py` — FastAPI + SSE

All three are thin (~50 lines). Lib is portable across them.

Rejected alternative: skill IS orchestrator (single SKILL.md system prompt
+ tool registry, Hermes-style) — would couple us to a specific host agent's
runtime, defeats the "non-Hermes consumers" strategic intent.

### Axis 5: Data contracts — lightweight dataclasses, one per stage

Each role consumes/produces a small `@dataclass` with 3-5 fields. Plain
Python — no Pydantic, no schema validation, no versioning. Lightweight by
construction (small team, no eval framework, fast iteration).

Each stage output dataclass includes the failure-handling tuple:
`status: Literal["ok", "skipped", "failed"]` and `reason: str | None`.
Synthesizer reads these to handle stubs.

Detailed schemas in the "Stage data contracts" section below.

### Axis 6: Reasoner has KG-search + vision-analyze as tools

Vision is **not** a separate stage. Retriever surfaces *image candidates*
(article-hash + path, no captions yet) along with chunks. Reasoner decides
— based on the user query + retrieved chunks — which images to caption via
`vision_analyze`, and whether to fetch additional KG chunks for deeper
relationships.

This mirrors what Hermes did empirically (msg 19+22 in
`session_20260506_105324_b7b9f4.json`): enumerate 19 images, then
selectively analyze only 3 based on relevance.

Reasoner's tool registry:

- `kg_search(query, top_k)` — additional retrieval beyond Retriever's
  first pass
- `vision_analyze(image_path, question)` — caption an image, with
  optional query-specific framing

Capped by `max_iter_reasoner` (default 5; Hermes used 3).

### Axis 7: Query-history injection — DEFERRED

The current `query_history.jsonl` (HYG-03) lives in `kg_synthesize.py`
only. Whether this milestone's orchestrator should also inject recent
queries as follow-up context is **deferred until the Cognee plan
clarifies** (see CLAUDE.md `OMNIGRAPH_COGNEE_INLINE` and v3.4
Phase 20/21).

For now: orchestrator does NOT read `query_history.jsonl`. Each query is
treated as standalone. When Cognee revival lands, a `CogneeRecall` step
can be added cheaply as a new stage between WebBaseline and Retriever.

### Axis 8: Failure telemetry — minimum viable

When a role returns a stub:

- The stub is written to JSONL telemetry (already covered by Axis 2)
- Synthesizer adds a single visible note line at the end of the markdown
  answer, e.g. `> ℹ️ Verifier skipped: API quota exhausted. Answer based
  on internal KG only.`
- NO stderr warnings in CLI output (stdout is the markdown blob)
- NO separate alert system, no retries beyond what's inside the agent
  loops

Lightweight by design. The user sees the degradation; the JSONL captures
the full state for debug.

### Axis 9: Web tool selection — Tavily primary, Brave fallback

| Tool | Provider | Use |
|---|---|---|
| `web_search` (primary) | Tavily REST API | broad public baseline (STAGE 1), Verifier grounding (STAGE 4) |
| `web_search` (fallback) | Brave Search REST API | invoked when Tavily errors / quota / timeout |
| `web_extract` | Tavily extract endpoint | targeted URL extraction (Verifier deep-dive) |
| `google_search_grounding` | Vertex AI Gemini Grounding | OPT-IN, only when `llm_complete` is Gemini Vertex |

The Verifier's tool registry is composed at config construction time:

- Always: Tavily + Brave fallback
- Conditional: if config detects Gemini Vertex `llm_complete`, Grounding
  is added as a third tool

**Important:** MCP tools (`mcp__tavily__*`, `mcp__brave-search__*`) are
main-session-only per global CLAUDE.md and CANNOT be called from our
Python orchestrator (Databricks proxy strips `tool_reference` blocks
before sub-process tool discovery). We use Tavily and Brave REST APIs
directly via their Python SDKs.

Required new env vars:

- `TAVILY_API_KEY` — for `tavily-python` SDK
- `BRAVE_SEARCH_API_KEY` — for direct Brave REST calls

Both have free tiers sufficient for hobby-scale usage.

### Axis 10: Output language matches query language

Synthesizer's prompt ends with: "Detect the language of the user's
original query. Output the entire answer in that same language. If the
query mixes languages, default to the dominant one."

Modern LLMs handle this trivially with a one-line prompt instruction. No
translation step, no language config, no detection library.

---

## Stage data contracts (Axis 5 detail)

Plain Python dataclasses. ~50 lines total. Lives in
`lib/research/types.py` (or similar).

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Status = Literal["ok", "skipped", "failed"]

@dataclass(frozen=True)
class Source:
    kind: Literal["kg_chunk", "kg_image", "web", "grounding"]
    uri: str                             # entity_id, URL, or local path
    title: str | None = None
    snippet: str | None = None

@dataclass(frozen=True)
class WebBaseline:                       # STAGE 1 output
    queries_used: list[str]
    snippets: list[Source]
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class RetrievedImage:
    article_hash: str                    # e.g. "43ccc4b10e"
    image_path: Path
    caption: str | None = None           # filled by Reasoner via vision_analyze

@dataclass(frozen=True)
class RetrieverOutput:                   # STAGE 2 output
    chunks: list[Source]                 # kind="kg_chunk"
    image_candidates: list[RetrievedImage]
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class ReasonerOutput:                    # STAGE 3 output
    inferences_md: str                   # bulleted markdown
    additional_chunks: list[Source]      # from follow-up kg_search calls
    analyzed_images: list[RetrievedImage]   # captions filled in
    iter_count: int                      # how many agent-loop steps
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class VerifierOutput:                    # STAGE 4 output
    fact_check_summary_md: str
    confidence: float                    # 0-100
    external_citations: list[Source]     # kind="web" or "grounding"
    discrepancies: list[str]             # KG vs web disagreements
    iter_count: int
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class SynthesizerOutput:                 # STAGE 5 output
    markdown: str
    confidence: float                    # passed through from Verifier
    sources: list[Source]                # union of KG + web
    embedded_images: list[Path]
    note_lines: list[str]                # Axis 8 visible degradation notes

@dataclass
class ResearchState:
    query: str
    timestamp_start: float
    web_baseline: WebBaseline | None = None
    retrieved: RetrieverOutput | None = None
    reasoned: ReasonerOutput | None = None
    verified: VerifierOutput | None = None
    synthesized: SynthesizerOutput | None = None
```

`ResearchResult` (returned to caller from `research()`) is a thin façade
over `state.synthesized`:

```python
@dataclass(frozen=True)
class ResearchResult:
    markdown: str                        # = state.synthesized.markdown
    confidence: float                    # = state.synthesized.confidence
    sources: list[Source]                # = state.synthesized.sources
    images_embedded: list[Path]          # = state.synthesized.embedded_images
    state: ResearchState                 # full state for debug/eval/HTTP raw
```

---

## Library API design rules (HTTP-ready by construction)

Five rules govern the lib API so adding a future HTTP endpoint is ~50 lines
of FastAPI, not an architectural rework.

1. **Top-level entrypoint is a pure async function.**
   `async def research(query: str, config: ResearchConfig) -> ResearchResult`.
   Returns the result object; does not print, write files, or parse argv.
2. **No global state.**
   LightRAG client, vision cascade, web-search client are all injected via
   `ResearchConfig`. The orchestrator does not hold module-level singletons.
   Caller decides per-call vs pooled lifetime.
3. **Config via dataclass, env read once.**
   `ResearchConfig` reads env once at construction. Hot path uses only the
   dataclass. No `os.environ[...]` scattered through role modules.
4. **Side effects are opt-in.**
   `output_dir` and `telemetry_jsonl` fields are nullable. Default = no file
   I/O; the lib returns markdown as a string and the caller decides where
   to put it.
5. **Streaming is a first-class peer to blocking.**
   Provide both `research()` (collected) and
   `research_stream() -> AsyncIterator[Event]` (incremental). CLI can render
   progress, HTTP can SSE, skill can ignore.

### Proposed API shape

```python
@dataclass(frozen=True)
class ResearchConfig:
    # ── core ──
    rag_working_dir: Path
    llm_complete: Callable                                # DeepSeek default; Gemini Vertex enables Grounding (Axis 9)
    embedding_func: Callable
    vision_cascade: VisionCascade                         # used by Reasoner per Axis 6
    # ── web tools (Axis 9) ──
    web_search: Callable[[str], list[dict]]               # primary, e.g. Tavily
    web_search_fallback: Callable[[str], list[dict]] | None = None   # e.g. Brave
    web_extract: Callable[[str], str] | None = None       # e.g. Tavily extract
    google_search_grounding: Callable | None = None       # opt-in, only with Gemini Vertex
    # ── side effects (Axis 4 rule 4) ──
    output_dir: Path | None = None
    telemetry_jsonl: Path | None = None
    # ── agent-loop caps (Axis 1) ──
    max_iter_reasoner: int = 5
    max_iter_verifier: int = 3

@dataclass
class ResearchResult:
    markdown: str
    confidence: float          # 0-100
    sources: list[Source]
    images_embedded: list[ImagePath]
    state: ResearchState

async def research(query: str, config: ResearchConfig) -> ResearchResult: ...
async def research_stream(
    query: str, config: ResearchConfig
) -> AsyncIterator[Event]: ...
```

The three wrappers all consume the same API. HTTP wrapper at a future Phase
is ~50 lines of FastAPI + SSE; no architectural changes needed.

---

## Skill exposure principle: orchestration is internal

**One milestone deliverable = one new skill.** When users install the
`omnigraph_research` skill into Hermes / Claude Code / OpenClaw, they see
exactly ONE new entry:

```text
$ <host> skills list | grep omnigraph
omnigraph_ingest
omnigraph_search
omnigraph_query
omnigraph_research    ← NEW (this milestone)
```

The internal stages (web baseline, retriever, reasoner, verifier, vision,
synthesizer) are **never** exposed as skills.

### Why this matters

- The orchestration logic IS the value. Exposing internal stages would force
  every host agent to re-implement the orchestration in its own agent loop.
- Skills represent user-facing capabilities. "Run a deep research" is one
  capability. "Reason over a context blob" is not — no user wants that
  standalone.
- Encapsulation = stability. With one skill we can refactor stage boundaries
  freely; with multiple skills the role split becomes a public API.

### Counter-pattern (NEVER DO)

```text
❌ skills/omnigraph_kg_retrieve/    ← exposes retriever as skill
❌ skills/omnigraph_kg_reason/      ← exposes reasoner as skill
❌ skills/omnigraph_kg_verify/      ← exposes verifier as skill
❌ skills/omnigraph_kg_synthesize/  ← exposes synthesizer as skill
```

A host agent installing those would have to figure out how to chain them,
what data flows between, how to fall back. That is exactly what the
orchestrator encapsulates.

### Coexistence with prior skills

`omnigraph_search` and `omnigraph_query` are NOT subsumed by
`omnigraph_research`. They are distinct user-facing capabilities at
different cost/quality points:

| Skill | Use when | Cost | Latency |
|-------|----------|------|---------|
| `omnigraph_search` | "show me raw KG chunks" | ~$0.01 | 10-20s |
| `omnigraph_query` | "answer from KG only, single-source" | ~$0.01 | 30-60s |
| `omnigraph_research` | "full hybrid agentic, image-rich" | ~$0.05 | 30-60s |

The host agent (or user) picks the right tool. Choosing among skills is
host-agent work; orchestrating internal stages of one skill is NOT.

### Hard constraint for `/gsd:plan-phase`

When the GSD planner decomposes this milestone into Phases, **no Phase
shall introduce a second skill**. If a Phase wants intermediate-state
visibility for debugging, that is a CLI flag (`--dump-state`) or a config
field, NOT a new skill.

---

## Milestone-ready pin-downs (locked 2026-05-06)

Final operational decisions before `/gsd:new-milestone`.

### Milestone name and naming map

| Object | Name |
|---|---|
| Milestone | **Agentic-RAG-v1** |
| Python package path | `lib/research/` |
| Skill name | `omnigraph_research` |
| Skill directory | `skills/omnigraph_research/` |

### Cross-milestone KG API contract

The Agentic-RAG-v1 milestone depends on the OmniGraph KG side via **a
single Python function**, plus filesystem read access to a stable
directory layout.

**Hard contract** (KG team must NOT break):

```python
# omnigraph_search/query.py
async def search(
    query_text: str,
    mode: str = "hybrid",        # at minimum "hybrid" must be supported
) -> str:                        # LLM-synthesized text from LightRAG aquery
    ...
```

The Retriever role wraps it directly:

```python
# lib/research/roles/retriever.py — only KG dependency in the entire milestone
from omnigraph_search.query import search

async def retrieve(query: str) -> str:
    return await search(query, mode="hybrid")
```

**KG team free to change** (no coordination needed):
LightRAG version, embedding model, storage backend, canonical-map
implementation, retrieval algorithm, internal prompt templates.

**Filesystem dependency** (also part of contract):

- Image storage layout: `~/.hermes/omonigraph-vault/images/{article_hash}/{N}.jpg`
- The Retriever extracts `article_hash` mentions from `search()`'s returned
  text and globs this directory for image candidates.

If KG side ever needs raw-chunk-level access (e.g., for stricter retrieval
control), a new function `search_raw(query, mode) -> dict` can be added
alongside `search()` — does NOT break the v1 contract.

### Smoke test (acceptance criterion for milestone done)

Single curated query, run end-to-end.

**Query**: `"Hermes Harness 深度解析"`
(intentionally same as `session_20260506_105324_b7b9f4.json` so we have
human ground truth to compare against)

**Pass conditions** (all must hold):

1. Output markdown contains ≥ 3 inline images via
   `![desc](http://localhost:8765/...)` syntax
2. `state.verified.confidence >= 60`
3. End-to-end wall time ≤ 120 s
4. JSONL telemetry shows no stage with `status="failed"`
   (`status="skipped"` is acceptable — that's the best-effort design from
   Axis 3)
5. Answer language is Chinese (validates Axis 10 — query was Chinese)

**Comparison baseline**:

The Hermes session at
`docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`
contains the full Telegram answer in `send_message` tool-call arguments
(4 message segments + 3 images). For each milestone-end review:

- Read both answers side-by-side (Agentic-RAG-v1 output vs Hermes Telegram)
- Score 5 dimensions on a 0-5 scale subjectively:
  coverage breadth, technical depth, philosophical framing,
  source attribution, image relevance
- Pass criterion: each dimension ≥ 3/5 (i.e., **not significantly worse than
  Hermes** — we are not required to "win", but we must not be visibly
  inferior on any dimension)

This is the only smoke test for the milestone. Eval framework remains
out-of-scope (Q8).

---

## What NOT in this doc

- Phase plan / task breakdown — defer to `/gsd:plan-phase`
- Detailed function signatures beyond the proposed shape — refine during
  Phase 1 implementation
- Hermes session log forensics beyond the tool-call tally — already enough
  signal in this doc; full reproduction not needed

---

## Cross-session pointers

- `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`
  — full Hermes session that produced "Hermes Harness 深度解析" Telegram
  answer (52 messages, 28 tool calls, DeepSeek-v4-pro). Source of truth for
  this doc.
- `docs/queries/hermes_session_2026_05_06/session_20260506_110229_f1b587.json`
  — second related session (64 messages, 34 tool calls). Cross-reference.
- `docs/spec/agentic_rag_discussion_2026_05_06.md` — original sketch.
  **Frozen**, not for further commits.
- `docs/queries/AB_comparison_kg_vs_brave_2026_05_06.md` — A/B data point
  (KG-only vs Brave-only on the same question).
- `kg_synthesize.py` — current single-shot KG path, the STAGE 2 building block.
- `lib/vision_cascade.py` — vision-analyze infrastructure to reuse for
  Finding 1.
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/` — cross-session memory.

---

*Working doc. Update as discussion proceeds. When discussion converges, this
doc becomes input to `/gsd:plan-phase` and is preserved as research record.*
