---
phase: ar-1-mvp-vertical-slice
milestone: Agentic-RAG-v1
status: planned
last_updated: "2026-05-22"
plans:
  - ar-1-01-package-scaffolding
  - ar-1-02-stage-stubs
  - ar-1-03-cli-image-server
  - ar-1-04-skill-packaging
requirements_in_scope: 25
requirements:
  - LIB-01
  - LIB-02
  - LIB-03
  - LIB-04
  - LIB-05
  - LIB-06
  - LIB-07
  - LIB-09
  - ORCH-01
  - ORCH-02
  - ORCH-06
  - ORCH-07
  - ORCH-08
  - ORCH-09
  - SKILL-01
  - SKILL-02
  - SKILL-03
  - SKILL-04
  - SKILL-05
  - CLI-01
  - CONFIG-01
  - CONFIG-02
  - TEST-01
  - CONTRACT-01
  - CONTRACT-02
---

# ar-1 — MVP Vertical Slice (Phase Context)

> **Parallel-track milestone**: this phase belongs to `Agentic-RAG-v1`, not v3.4.
> Sibling files: `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-Agentic-RAG-v1.md`.
> `gsd-tools.cjs` does NOT recognize the `-Agentic-RAG-v1` suffix — every gate in
> this phase is hand-driven by the orchestrator. Do NOT call `gsd-tools.cjs init`
> for this phase.

## Goal

Land an end-to-end skeleton of the `lib/research/` package that:

1. Is importable as both `lib.research` (physical) and `omnigraph.research` (declared)
2. Runs `python -m omnigraph.research "<query>"` and emits non-empty markdown to stdout
3. Walks all 5 stages in strict order (WebBaseline → Retriever → Reasoner → Verifier → Synthesizer)
4. Returns `status ∈ {"ok", "skipped"}` for every stage; never raises
5. Passes `skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json`
6. Auto-brings-up the local image HTTP server on port 8765 when needed

The deeper Reasoner / Verifier / Tavily-Brave-Grounding integrations are explicitly
deferred to ar-2 / ar-3 / ar-4. ar-1 is a contract-shape phase, not a quality phase.

## Locked Design Constraints (from `docs/design/agentic_rag_internal_api.md`)

Treat the design doc as final. All 10 architectural axes + 10 closed Q's are non-negotiable.

### Five API design rules (Axes 1-5)

1. **Pure async entrypoint** — `async def research(query, config) -> ResearchResult`; no `print`, no file I/O, no `argv` parsing inside `lib/research/`
2. **No module-level singletons** — every external dep injected via `ResearchConfig` (LightRAG client, vision cascade, web-search clients)
3. **Env read once at config construction** — hot path uses dataclass fields only; `os.environ[...]` confined to `ResearchConfig.from_env()`
4. **Opt-in side effects** — `output_dir` and `telemetry_jsonl` nullable; default-null run produces no file I/O
5. **Streaming peer** — `async def research_stream(query, config) -> AsyncIterator[Event]` exists alongside `research()`. ar-1 ships the function signature + a deferred body (raise `NotImplementedError("ar-4")`); body lands in ar-4 with telemetry.

### Seven frozen dataclasses (verbatim shapes)

```python
Status = Literal["ok", "skipped", "failed"]

@dataclass(frozen=True)
class Source:
    kind: Literal["kg_chunk", "kg_image", "web", "grounding"]
    uri: str
    title: str | None = None
    snippet: str | None = None

@dataclass(frozen=True)
class WebBaseline:
    queries_used: list[str]
    snippets: list[Source]
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class RetrievedImage:
    article_hash: str
    image_path: Path
    caption: str | None = None

@dataclass(frozen=True)
class RetrieverOutput:
    chunks: list[Source]
    image_candidates: list[RetrievedImage]
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class ReasonerOutput:
    inferences_md: str
    additional_chunks: list[Source]
    analyzed_images: list[RetrievedImage]
    iter_count: int
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class VerifierOutput:
    fact_check_summary_md: str
    confidence: float
    external_citations: list[Source]
    discrepancies: list[str]
    iter_count: int
    status: Status = "ok"
    reason: str | None = None

@dataclass(frozen=True)
class SynthesizerOutput:
    markdown: str
    confidence: float
    sources: list[Source]
    embedded_images: list[Path]
    note_lines: list[str]
    # NO status field — terminal stage; degradation surfaces via note_lines (Axis 8)

@dataclass
class ResearchState:
    query: str
    timestamp_start: float
    web_baseline: WebBaseline | None = None
    retrieved: RetrieverOutput | None = None
    reasoned: ReasonerOutput | None = None
    verified: VerifierOutput | None = None
    synthesized: SynthesizerOutput | None = None

@dataclass(frozen=True)
class ResearchResult:
    markdown: str
    confidence: float
    sources: list[Source]
    images_embedded: list[Path]
    state: ResearchState

@dataclass(frozen=True)
class ResearchConfig:
    rag_working_dir: Path
    llm_complete: Callable
    embedding_func: Callable
    vision_cascade: object  # VisionCascade duck-type
    web_search: Callable[[str], list[dict]]
    web_search_fallback: Callable[[str], list[dict]] | None = None
    web_extract: Callable[[str], str] | None = None
    google_search_grounding: Callable | None = None
    output_dir: Path | None = None
    telemetry_jsonl: Path | None = None
    max_iter_reasoner: int = 5
    max_iter_verifier: int = 3
```

These shapes do NOT change in ar-1 (or any later ar-* phase) without a milestone-level decision.
`ResearchState` is the only mutable dataclass — orchestrator writes one stage field at a time.

### Strict pipeline order (Axis 1)

WebBaseline → Retriever → Reasoner → Verifier → Synthesizer.

Sequential. Parallelism is permitted ONLY within a single stage's internal agent loop or
batched tool calls (e.g. Reasoner running 3 `vision_analyze` in parallel). Inter-stage
re-ordering or pipelining is prohibited.

### Best-effort failure handling (Axis 3)

Every stage `try`/`except`s its own work. On any exception, return a stub instance with
`status="failed"` + `reason=str(e)`. No stage may raise out to the orchestrator.
Synthesizer (terminal) instead appends a degradation note line — no status field.

### Output language matches query language (Axis 10)

Single Synthesizer prompt instruction. No translation step. ar-1 stub uses a heuristic
(CJK char ratio ≥ 0.3 → Chinese; else English). ar-2 swaps in real LLM-driven detection.

## Reality-State Deltas (vs design doc 2026-05-06)

The design doc was authored 2026-05-06; deltas as of 2026-05-22:

| Item | Design state | Current state | Effect on ar-1 |
|---|---|---|---|
| KB API endpoints | "future Phase" | Live on Aliyun (`POST /api/synthesize`, `GET /api/search?mode=kg`) | HTTP wrapper deferred to post-milestone, but API patterns now reusable |
| KG `search()` contract | unverified | `omnigraph_search/query.py:search(query_text, mode="hybrid") -> str` exists and works | Retriever stage can call it directly — no shim |
| Global mode KG | not built | `kv_store_community_reports.json` populated (ar-0-quick-1) | hybrid query truly = local + global |
| canonical_map | static | Expansion candidates at `.scratch/canonical_candidates_*.txt` (ar-0-quick-2) | unrelated to ar-1 — KG side concern |
| Vision cascade | "exists" | `lib/vision_cascade.py` battle-tested in v1.0 ingest | Reasoner can pass it through verbatim in ar-2 |
| LLM clients | "exists" | `lib/llm_deepseek.py`, `lib/vertex_gemini_complete.py`, `lib/llm_complete.py` all in repo | `ResearchConfig.from_env()` can compose from these |
| Lightrag embedding | "exists" | `lib/lightrag_embedding.py` in repo | wrap-able as `embedding_func` |

**None of these deltas invalidate any locked decision.** They reduce ar-3/ar-4 work
(HTTP wrapper is now ~50 lines because Aliyun pattern exists) but ar-1 contract shape is unchanged.

## LIB-09 Resolution: Option (a) — Namespace mapping

The design doc has an internal inconsistency:
- line 25: `omnigraph.research_api`
- line 287: `omnigraph.research`
- line 625: `lib/research/`

ar-1 picks **option (a)**: keep the physical path `lib/research/` and add a namespace
mapping in `pyproject.toml` so `omnigraph.research` resolves to it.

**Why (a) over (b) physical rename**:
- Repo convention: every other implementation lib lives at `lib/` (`lib/llm_deepseek.py`,
  `lib/vision_cascade.py`, `lib/lightrag_embedding.py`). Renaming to `omnigraph/research/`
  would create a one-off layout for this milestone alone — unnecessary churn.
- `omnigraph_search/` is the lone exception (top-level package), and it predates the
  `lib/` convention. Don't propagate the inconsistency.
- Importers in `omnigraph_search/`, `skills/`, and tests can use whichever name they prefer
  once the mapping is in place; both work.

**How**: add a `[project]` table to `pyproject.toml` plus a `[tool.setuptools.packages.find]`
or `[tool.setuptools.package-dir]` mapping. Concrete commands in `ar-1-01-PLAN.md`.

Documented in `lib/research/README.md` (created in plan 01) as the single
source-of-truth for the choice.

## Module layout (after ar-1)

```
lib/research/
├── __init__.py          # exports: research, research_stream, ResearchConfig,
│                        # ResearchResult, ResearchState, Source
├── types.py             # 7 frozen dataclasses + Status alias + ResearchState
├── config.py            # ResearchConfig + from_env() factory
├── orchestrator.py      # async def research() — calls stages in order
├── __main__.py          # `python -m omnigraph.research "<query>"`
├── image_server.py      # local image HTTP server (port 8765) auto-bring-up
├── stages/
│   ├── __init__.py
│   ├── web_baseline.py  # ar-1 stub: status="skipped" if web_search is None
│   ├── retriever.py     # ar-1 wires real omnigraph_search.query.search()
│   ├── reasoner.py      # ar-1 stub: status="skipped" + iter_count=0
│   ├── verifier.py      # ar-1 stub: status="skipped" + iter_count=0
│   └── synthesizer.py   # ar-1 minimal markdown synth + language heuristic
└── README.md            # human-facing — packaging choice, dev quickstart

skills/omnigraph_research/
├── SKILL.md             # frontmatter (name, description, triggers, requires)
├── scripts/research.sh  # ~50-line wrapper invoking python -m omnigraph.research
└── README.md            # human install + cost/quality/latency table

tests/unit/research/
├── __init__.py
├── test_types.py        # field defaults, frozen-ness, Status alphabet
├── test_config.py       # from_env() reads expected env vars
├── test_stages_stubs.py # each stub returns valid dataclass; status alphabet
└── test_orchestrator.py # full research() with all-stub config returns ok/skipped

tests/skills/
└── test_omnigraph_research.json   # skill_runner test harness
```

## Configuration (CONFIG-01, CONFIG-02)

`ResearchConfig.from_env()` reads:

| Env var | Required | Default if unset |
|---|---|---|
| `TAVILY_API_KEY` | No (ar-1) / Yes (ar-3) | `web_search` defaults to a `_skipped_callable` that returns `[]` and a config-time log line |
| `BRAVE_SEARCH_API_KEY` | No | `web_search_fallback = None`; demotes silently |
| `OMNIGRAPH_BASE_DIR` | No | `~/.hermes/omonigraph-vault` (typo `omonigraph` is canonical — DO NOT fix) |
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` (uses `lib.llm_deepseek.deepseek_model_complete`) |
| `OMNIGRAPH_RESEARCH_OUTPUT_DIR` | No | `None` — orchestrator writes nothing to disk |
| `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` | No | `None` — orchestrator emits no telemetry |

ar-1 can complete and pass smoke with `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` BOTH
unset; both stages stub to `status="skipped"` with a clear `reason`.

## CONTRACT enforcement (CONTRACT-01, CONTRACT-02)

**CONTRACT-01**: only `omnigraph_search.query.search` may be imported from KG side.
Enforced via grep hook at `scripts/check_contract.sh`:

```bash
#!/usr/bin/env bash
set -e
hits=$(grep -rE "from omnigraph_search" lib/research/ \
  --include='*.py' \
  | grep -vE "from omnigraph_search\.query " \
  | grep -vE "from omnigraph_search\.query$" \
  | grep -vE "import omnigraph_search\.query" \
  || true)
if [ -n "$hits" ]; then
  echo "CONTRACT-01 violation: forbidden omnigraph_search import in lib/research/"
  echo "$hits"
  exit 1
fi
```

Wired into a documented checklist in `lib/research/README.md` (Phase 1 picks documented
checklist over pre-commit infra — keep ar-1 surface small; pre-commit plumbing can land
later as a v1.1 candidate).

**CONTRACT-02**: orchestrator MUST NOT hardcode `~/.hermes/omonigraph-vault/images/`.
Always read through `config.rag_working_dir` (the BASE_IMAGE_DIR equivalent comes from
`config.from_env()` reading `OMNIGRAPH_BASE_DIR` with the canonical `omonigraph` typo).

Verified by grep at acceptance time:

```bash
grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary"
# expected: 0 hits
```

## Smoke test for ar-1

Two layers, both must pass before phase is marked complete:

### Layer 1 — pytest

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v
# expected: all green; ≥ 1 test per dataclass, ≥ 1 test per stage stub
```

### Layer 2 — end-to-end CLI

```bash
venv/Scripts/python.exe -m omnigraph.research "什么是 Hermes Harness 深度解析"
# expected:
#  - exit code 0
#  - stdout: non-empty markdown (≥ 200 chars)
#  - markdown contains query echo + at least one degradation note line
#    (since web_search and grounding are stubbed in ar-1, Verifier appends:
#    "> ℹ️ Verifier skipped: stub mode (ar-1).")
#  - port 8765 image server is brought up if not already running
#  - no stage raises; ResearchState dataclass populates all 5 stage fields
```

### Layer 3 — skill_runner

```bash
venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
  --test-file tests/skills/test_omnigraph_research.json
# expected: exit code 0
```

## Out of Scope for ar-1 (deferred to later ar-* phases)

| Item | Phase |
|---|---|
| Real Reasoner agent loop with `kg_search` + `vision_analyze` tools | ar-2 |
| `lib/vision_cascade.py` integration as `vision_analyze` tool | ar-2 |
| Synthesizer prompt engineering with image embeds + degradation appending | ar-2 (initial) / ar-4 (final tuning) |
| `--max-iter-reasoner` / `--max-iter-verifier` / `--no-grounding` CLI flags | ar-2 |
| Tavily REST primary + Brave REST fallback live integration | ar-3 |
| Vertex Gemini `google_search_grounding` opt-in | ar-3 |
| `--dump-state` CLI flag | ar-4 |
| `research_stream()` body + telemetry JSONL writes | ar-4 |
| Smoke test on `"Hermes Harness 深度解析"` with all conditions (≥3 imgs, conf≥60, ≤120s, lang=zh) | ar-4 |
| Side-by-side review vs ground-truth Telegram session | ar-4 (manual review) |
| HTTP endpoint pre-build | post-milestone |

## Related artifacts

- `.planning/PROJECT-Agentic-RAG-v1.md` — milestone charter
- `.planning/REQUIREMENTS-Agentic-RAG-v1.md` — full 41-REQ list with ar-1 mapping
- `.planning/ROADMAP-Agentic-RAG-v1.md` — 4-phase decomposition + cross-phase touches
- `.planning/STATE-Agentic-RAG-v1.md` — current milestone state (updated end of ar-1 planning)
- `docs/design/agentic_rag_internal_api.md` — locked design doc (final)

## Plan-file authoring conventions (orchestrator handoff to gsd-planner)

Each plan in this phase follows the kb-1-01 template:

- YAML frontmatter: `phase`, `plan`, `type`, `wave`, `depends_on`, `files_modified`,
  `autonomous: true`, `requirements`, `must_haves` (truths / artifacts / key_links)
- `<objective>` — purpose + output
- `<execution_context>` — `@$HOME/.claude/get-shit-done/workflows/execute-plan.md`
  + `templates/summary.md`
- `<context>` — `@`-references for files the executor must read first; `<interfaces>`
  block for cross-cutting type contracts
- `<tasks>` — atomic numbered tasks each with `<read_first>`, `<files>`, `<behavior>`
  (TDD when applicable), `<action>`, `<verify>`, `<acceptance_criteria>`, `<done>`
- `<verification>` — phase-level
- `<success_criteria>` — phase-level
- `<output>` — SUMMARY.md path the executor writes after completion

---
*Phase context authored 2026-05-22 by `/gsd:plan-phase ar-1` orchestrator.
Manual GSD gates (parallel-track milestone) — gsd-tools.cjs not invoked.*
