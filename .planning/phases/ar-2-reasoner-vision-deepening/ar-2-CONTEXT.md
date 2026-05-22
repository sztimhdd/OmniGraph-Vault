---
phase: ar-2-reasoner-vision-deepening
milestone: Agentic-RAG-v1
status: planned
last_updated: "2026-05-22"
plans: []
requirements_in_scope: 5
requirements:
  - ORCH-03
  - ORCH-05
  - TOOL-04
  - CLI-03
  - TEST-03
---

# ar-2 — Reasoner + Vision Deepening (Phase Context)

> **Parallel-track milestone**: this phase belongs to `Agentic-RAG-v1`, not v3.4.
> Sibling files: `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-Agentic-RAG-v1.md`.
> `gsd-tools.cjs` does NOT recognize the `-Agentic-RAG-v1` suffix — every gate in
> this phase is hand-driven by the orchestrator. Do NOT call `gsd-tools.cjs init`
> for this phase.

## Goal

Replace the ar-1 deterministic-stub Reasoner with a **real bounded LLM agent loop**,
and lift the Synthesizer's image-embed alt text from filename placeholders
(`![5.jpg](...)`) to **vision-generated captions** anchored on the
`ReasonerOutput.analyzed_images` field.

Concretely, after ar-2 completes:

1. `Reasoner.run()` executes a tool-using LLM loop with `kg_search(query, top_k)`
   and `vision_analyze(image_path, question)` exposed as tools; loop terminates
   at `iter_count <= cfg.max_iter_reasoner` (default 5) and the returned
   `ReasonerOutput.iter_count` reflects the real number of tool turns
2. `Synthesizer.run()` emits inline images of the form
   `![<vision-caption>](http://localhost:8765/<hash>/<N>.jpg)` where
   `<vision-caption>` comes from `state.reasoned.analyzed_images[*].caption`
   (NOT the bare filename) — terminal stage still has no `status` field; degradation
   note_lines unchanged from ar-1
3. CLI accepts three new flags — `--max-iter-reasoner`, `--max-iter-verifier`,
   `--no-grounding` — and propagates them into `ResearchConfig` overrides via
   `dataclasses.replace()`; LLM provider remains env-only (`OMNIGRAPH_LLM_PROVIDER`)
   per CLI-03's hard rule
4. Mock-based test (TEST-03) exercises a Reasoner loop that calls `vision_analyze`
   ≥1 time and confirms the resulting caption shows up in the Synthesizer's
   prompt input (i.e., the data flow Reasoner → state.reasoned → Synthesizer is
   asserted, not just shape-checked)

The deeper Verifier loop, Tavily/Brave/Grounding wiring, and `--no-grounding`
**real** behavior are explicitly deferred to ar-3. The `--no-grounding` flag in
ar-2 is plumbed-but-no-op (CLI-03 deliberately splits flag plumbing from
behavior delivery — see ROADMAP § Cross-phase touches).

ar-2 is the first phase that introduces real LLM behavior into the pipeline. The
contract shape (7 frozen dataclasses + strict pipeline order + best-effort
failure) is identical to ar-1 and **does not change** here.

## Locked Design Constraints (from `docs/design/agentic_rag_internal_api.md`)

Treat the design doc as final. All 10 architectural axes + 10 closed Q's are
non-negotiable. ar-1's CONTEXT carried this verbatim block; ar-2 inherits it
unchanged. Reproduced here so this CONTEXT is self-contained.

### Five API design rules (Axes 1-5)

1. **Pure async entrypoint** — `async def research(query, config) -> ResearchResult`;
   no `print`, no file I/O, no `argv` parsing inside `lib/research/`. ar-2 keeps
   this — CLI flag plumbing happens in `__main__.py`, NOT in stages
2. **No module-level singletons** — every external dep injected via
   `ResearchConfig`. ar-2's Reasoner reads `cfg.llm_complete`, `cfg.vision_cascade`,
   and (via Retriever's stub `kg_search` callable) `omnigraph_search.query.search`
3. **Env read once at config construction** — hot path uses dataclass fields only;
   `os.environ[...]` confined to `ResearchConfig.from_env()`. ar-2 must NOT read
   any env var inside the Reasoner agent loop
4. **Opt-in side effects** — `output_dir` and `telemetry_jsonl` nullable;
   default-null run produces no file I/O. Unchanged
5. **Streaming peer** — `async def research_stream(query, config) -> AsyncIterator[Event]`
   exists alongside `research()`; ar-1 ships the signature with a deferred body
   (`raise NotImplementedError("ar-4")`). ar-2 does NOT touch the body — the
   real agent-loop event emission is an ar-4 concern coupled with telemetry

### Seven frozen dataclasses (verbatim shapes — unchanged from ar-1)

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

These shapes do NOT change in ar-2. `ReasonerOutput` already carries
`analyzed_images: list[RetrievedImage]` and `iter_count: int` from ar-1 — ar-2
fills them with real values rather than empty/zero. `RetrievedImage.caption: str | None`
is the slot the vision_analyze tool writes into.

### Strict pipeline order (Axis 1) — unchanged

WebBaseline → Retriever → Reasoner → Verifier → Synthesizer.

Sequential. Parallelism is permitted ONLY within a single stage's internal agent
loop or batched tool calls — **explicitly including** the Reasoner running
multiple `vision_analyze` calls in parallel within one iteration (Axis 6).
Inter-stage re-ordering or pipelining is prohibited.

### Best-effort failure handling (Axis 3) — unchanged

Every stage `try`/`except`s its own work. On any exception, return a stub
instance with `status="failed"` + `reason=str(e)`. **The Reasoner agent loop
must catch tool-call exceptions, prompt-completion exceptions, and runaway
iter_count overflow.** No stage may raise out to the orchestrator. Synthesizer
(terminal) instead appends a degradation note line — no status field.

### Output language matches query language (Axis 10)

Single Synthesizer prompt instruction. ar-1's CJK-ratio heuristic is fine for
the bare-skeleton Synthesizer; ar-2 does NOT need to swap it for LLM-driven
detection (deferred to ar-4 alongside final prompt tuning). The Synthesizer's
output prompt instruction itself carries the language directive.

## Reality-State Deltas (vs design doc 2026-05-06)

The design doc was authored 2026-05-06. ar-1 closed 2026-05-22 with all 4 plans
executed (commits 962f995..cbd432d) and the 3-layer smoke harness passing.
Reality deltas vs the design that affect ar-2:

| Item | Design state | Current state (post-ar-1) | Effect on ar-2 |
|---|---|---|---|
| `lib/research/` package | not built | shipped, importable as `omnigraph.research` | Reasoner edits only `lib/research/stages/reasoner.py`; no package-level changes |
| Reasoner stub | "deterministic placeholder" | `status="skipped"`, `iter_count=0`, empty lists (`reasoner.py` ar-1 form) | ar-2 replaces the stub body — keep signature `(query, cfg, retrieved) -> ReasonerOutput` |
| Synthesizer image alt text | "caption-anchored" | uses `img.name` (filename) as alt text — placeholder | ar-2 replaces alt text with `state.reasoned.analyzed_images[*].caption`; falls back to filename if caption is None |
| `vision_cascade` reuse | "exists, plug-in via Reasoner" | `lib/vision_cascade.py` battle-tested in v1.0 ingest, `cfg.vision_cascade` already wired by `from_env()` in ar-1 | TOOL-04: Reasoner imports nothing new — calls `cfg.vision_cascade` directly |
| `omnigraph_search.query.search` | unverified | imported by Retriever stage in ar-1 (CONTRACT-01 already enforced) | `kg_search` tool wraps the same callable; **no second import path** allowed |
| LLM clients | "exists" | `cfg.llm_complete` already injected by `from_env()` (DeepSeek default; Vertex Gemini opt-in via `OMNIGRAPH_LLM_PROVIDER`) | Reasoner agent loop dispatches against `cfg.llm_complete`; no provider branching in stage code |
| CLI surface | bare `<query>` positional | `_parse_args()` is the extension point in `lib/research/__main__.py` | ar-2 extends parser; calls `dataclasses.replace(cfg, **overrides)` before invoking `research()` |
| `pyproject.toml` editable install | working (`pip install -e .` ran in ar-1-03) | `omnigraph.research` namespace resolves | ar-2 adds NO new top-level modules; if a new submodule is needed (e.g. `lib/research/agent_loop.py`), no install rerun required because `package-dir` mapping picks it up automatically |

**None of these deltas invalidate any locked decision.** ar-2 is a
behavior-only phase — no shape changes, no new contracts, no new env vars.

## ar-2 component contracts

### ORCH-03 + TOOL-04: Reasoner agent loop

**Tool registry** (built inside `Reasoner.run()`, NOT in `ResearchConfig` —
it's per-invocation, not session-level):

```python
async def kg_search(query: str, top_k: int = 10) -> str:
    # Wraps the SAME omnigraph_search.query.search callable Retriever uses.
    # CONTRACT-01: only this single import path allowed in lib/research/.
    return omnigraph_search.query.search(query, mode="hybrid")

async def vision_analyze(image_path: str, question: str) -> str:
    # Wraps cfg.vision_cascade — TOOL-04: no new vision infra.
    # Returns a caption string suitable for inline image alt text.
    return await cfg.vision_cascade.describe(image_path, question)
```

**Loop shape** (deterministic, bounded):

```python
iter_count = 0
collected_chunks: list[Source] = []
collected_images: list[RetrievedImage] = []  # captions filled in
while iter_count < cfg.max_iter_reasoner:
    iter_count += 1
    tool_call = await cfg.llm_complete(...)  # produces tool call(s) or final answer
    if tool_call.is_final:
        break
    # dispatch tool_call against {kg_search, vision_analyze}
    # accumulate results into collected_chunks / collected_images
return ReasonerOutput(
    inferences_md=final_answer,
    additional_chunks=collected_chunks,
    analyzed_images=collected_images,
    iter_count=iter_count,
    status="ok",
)
```

The loop body shape is descriptive — gsd-planner refines exact LLM-tool-protocol
mechanics during planning. Hard requirements:

- `iter_count` is the **post-loop** value (number of agent turns actually
  taken), NOT a counter pre-incremented past the cap
- `iter_count <= cfg.max_iter_reasoner` ALWAYS holds (cap enforcement is part
  of the loop condition, not a post-loop assertion)
- Any exception inside the loop → return `ReasonerOutput(status="failed",
  reason=str(e), iter_count=iter_count, ...)` per Axis 3 (best-effort)
- Reaching the cap is NOT a failure — return `status="ok"` with whatever was
  collected so far (the cap is a budget, not an error condition); a separate
  "cap exhausted" log line is fine but does not change `status`

**Vision parallelism** (Axis 1 carve-out): a single iteration MAY run multiple
`vision_analyze` calls in parallel via `asyncio.gather()` if the LLM emits
multiple vision tool calls in one turn. This is the only blessed in-stage
parallelism in this phase.

### ORCH-05: Synthesizer caption-anchored image embeds

**Inline image format** (after ar-2):

```markdown
![<caption from state.reasoned.analyzed_images[i].caption>](http://localhost:8765/<hash>/<N>.jpg)
```

**Source of `<caption>`**:

1. Iterate `state.reasoned.analyzed_images` (post-ar-2 contains real captions
   for images the Reasoner chose to analyze)
2. For each `RetrievedImage`, derive the URL from `image_path.parent.name` (the
   article hash) + `image_path.name` (the filename like `5.jpg`)
3. Use `caption` (always non-None when image came from `analyzed_images`) as
   the alt text
4. Fall back to **non-analyzed** images from `state.retrieved.image_candidates`
   if `state.reasoned.analyzed_images` is empty (Reasoner skipped/failed) — in
   that case alt text falls back to `img.name` exactly as ar-1 did. This
   preserves the best-effort principle (Axis 3 / ORCH-06)

**No status field on Synthesizer** (Axis 8) — degradation note_lines mechanism
unchanged from ar-1. If Reasoner returned `status="failed"` or `status="skipped"`,
Synthesizer still produces a markdown answer; the failure is surfaced as
`> ❌ Reasoner failed: <reason>` or `> ℹ️ Reasoner skipped: <reason>` appended
at the end (this code path already works in ar-1 and needs no changes).

### CLI-03: three new CLI flags

Extension point: `_parse_args()` in `lib/research/__main__.py`.

| Flag | Type | Default | Behavior in ar-2 |
|---|---|---|---|
| `--max-iter-reasoner` | int | None (use cfg default = 5) | Override `cfg.max_iter_reasoner` via `dataclasses.replace()` before calling `research()` |
| `--max-iter-verifier` | int | None (use cfg default = 3) | Override `cfg.max_iter_verifier`. Note: Verifier is still a stub in ar-2; the override is plumbed into the dataclass but exercised behaviorally only after ar-3 lands real Verifier loop. Plumbing now is cheap and avoids a CLI surface change in ar-3 |
| `--no-grounding` | flag (store_true) | False | Plumbed-but-no-op until ar-3. ar-2 implementation: store the flag value in `ResearchConfig.google_search_grounding` slot — set the slot to `None` if `--no-grounding` is passed (currently always None anyway, since Grounding is unwired). When ar-3 wires Grounding into `from_env()`, the flag will already be respected |

**LLM provider selection remains env-only** (`OMNIGRAPH_LLM_PROVIDER`) — NO CLI
override, per CLI-03's hard rule. Do NOT add `--llm-provider` or any equivalent
in this phase.

`__main__.py` shape after ar-2 (proximate — gsd-planner refines):

```python
def _parse_args(argv):
    parser = argparse.ArgumentParser(...)
    parser.add_argument("query")
    parser.add_argument("--max-iter-reasoner", type=int, default=None)
    parser.add_argument("--max-iter-verifier", type=int, default=None)
    parser.add_argument("--no-grounding", action="store_true")
    return parser.parse_args(argv)

async def _amain(ns):
    cfg = from_env()
    overrides = {}
    if ns.max_iter_reasoner is not None:
        overrides["max_iter_reasoner"] = ns.max_iter_reasoner
    if ns.max_iter_verifier is not None:
        overrides["max_iter_verifier"] = ns.max_iter_verifier
    if ns.no_grounding:
        overrides["google_search_grounding"] = None
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)
    ...
```

Pure wrapper rule (LIB-04 / Rule 1) is preserved: `__main__.py` still has zero
business logic beyond argument parsing and dataclass override.

### TEST-03: Reasoner loop mock test

**Behavior asserted** (mock-based, no live LLM / vision call):

1. `cfg.llm_complete` is replaced with a stub that emits a deterministic
   tool-call sequence: turn 1 = `vision_analyze(image_path=..., question=...)`,
   turn 2 = final answer
2. `cfg.vision_cascade` is replaced with a stub whose `describe()` returns a
   fixed string `"<MOCK_CAPTION>"`
3. After `Reasoner.run()` returns, assert:
   - `result.iter_count >= 1`
   - `result.analyzed_images` is non-empty
   - At least one entry has `caption == "<MOCK_CAPTION>"`
   - `cfg.vision_cascade.describe` was called ≥ 1 time
4. Then run a synthesizer-only assertion: feed a `ResearchState` whose
   `reasoned.analyzed_images` contains the mocked entry; assert the resulting
   `SynthesizerOutput.markdown` contains the literal substring
   `<MOCK_CAPTION>` somewhere inside an image markdown reference (`![<MOCK_CAPTION>](...)`)

This is the data-flow test — Reasoner → state.reasoned → Synthesizer prompt
input — that the ROADMAP's Success Criterion #5 demands. Single test file
covers both stages.

## Configuration (carried forward — no new env vars)

`ResearchConfig.from_env()` reads exactly the same env vars as ar-1. No
additions in ar-2:

| Env var | Required | Default | ar-2 effect |
|---|---|---|---|
| `TAVILY_API_KEY` | No | stub `_skipped_callable` | Unused in ar-2 (ar-3 wires this) |
| `BRAVE_SEARCH_API_KEY` | No | None | Unused in ar-2 (ar-3 wires this) |
| `OMNIGRAPH_BASE_DIR` | No | `~/.hermes/omonigraph-vault` (typo `omonigraph` is canonical — DO NOT fix) | Used by Retriever/Synthesizer for image paths; Reasoner reads `cfg.rag_working_dir` only |
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | Drives `cfg.llm_complete` selection at config construction; Reasoner does not branch on it |
| `OMNIGRAPH_GEMINI_KEY` / `GEMINI_API_KEY` | (provider-dependent) | — | Read by `from_env()` if Vertex Gemini is selected; Reasoner does not read directly |
| `OMNIGRAPH_RESEARCH_OUTPUT_DIR` | No | None | Unchanged from ar-1 |
| `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` | No | None | Unchanged from ar-1 (telemetry body lands in ar-4) |

> **Operator note for ar-3 (carry into every ar-2 PLAN.md):**
> ar-3 execute begins after ar-2 closes. Before ar-3 starts execution, the
> operator must inject `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` into
> `~/.hermes/.env` on the Hermes deployment target. ar-2 does NOT need either
> key — the stubs from ar-1 cover the WebBaseline/Verifier paths through ar-2
> close. Procurement should happen during ar-2 execution so ar-3 is unblocked
> at handoff.

## CONTRACT enforcement (carried forward — re-check at ar-2 acceptance)

CONTRACT-01 and CONTRACT-02 were enforced in ar-1 via documented checklist in
`lib/research/README.md` plus grep snippets. ar-2 must NOT introduce any new
import or hardcoded path that breaks them.

### CONTRACT-01: only `omnigraph_search.query.search` from KG side

```bash
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

ar-2 risk surface: when the Reasoner builds its `kg_search` tool wrapper, the
implementer must reuse the same `omnigraph_search.query.search` import the
Retriever already has (ideally factor it into a shared helper inside
`lib/research/stages/`). Do NOT add a second import line in `reasoner.py` that
re-imports anything beyond `omnigraph_search.query`.

### CONTRACT-02: no hardcoded `~/.hermes` / `omonigraph-vault` paths

```bash
grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary"
# expected: 0 hits
```

ar-2 risk surface: image paths flow `cfg.rag_working_dir` → Retriever →
`RetrievedImage.image_path` → Reasoner (`vision_analyze` argument) → Synthesizer
URL. None of those steps may stringify a hardcoded `~/.hermes` literal. The
`omonigraph` typo is canonical (per ar-1 LIB-09 resolution) — DO NOT "fix" it.

## Smoke test for ar-2

Three layers, all must pass before phase is marked complete. Layers 1 and 3 are
identical in shape to ar-1; Layer 2 is upgraded to assert ar-2-specific
behavior.

### Layer 1 — pytest

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v
# expected: all green
#   - all ar-1 tests still pass (regression guard)
#   - ≥ 1 new test exercising the Reasoner agent loop with mocked
#     llm_complete + vision_cascade (TEST-03 — see § ar-2 component contracts)
#   - ≥ 1 new test exercising the Synthesizer caption-anchoring path
```

### Layer 2 — end-to-end CLI (upgraded)

```bash
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 2 \
  --max-iter-verifier 1 \
  --no-grounding \
  "什么是 Hermes Harness 深度解析"
# expected:
#  - exit code 0
#  - stdout: non-empty markdown (≥ 200 chars)
#  - markdown contains query echo
#  - if `OMNIGRAPH_LLM_PROVIDER` is set to a working provider AND the user has
#    populated KB image candidates for the query: ≥ 1 inline image with
#    non-filename alt text (e.g. `![A diagram showing ...](http://localhost:8765/.../5.jpg)`)
#  - if LLM provider is unset OR no image candidates: Reasoner gracefully
#    skips (status="skipped"), Synthesizer falls back to ar-1 behavior, the
#    full degradation note line shows up — exit code is still 0
#  - port 8765 image server brought up on demand
#  - no stage raises; ResearchState dataclass populates all 5 stage fields
```

The CLI smoke is **environment-conditional** in ar-2: full caption-anchored
behavior depends on a working LLM provider key. Structural pass conditions
(exit 0, non-empty markdown, no raises) hold unconditionally. The full smoke
test (TEST-05 — `≥ 3 inline images`, `confidence >= 60`, `≤ 120 s`) is an
ar-4 milestone-close gate, NOT an ar-2 gate.

### Layer 3 — skill_runner

```bash
venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
  --test-file tests/skills/test_omnigraph_research.json
# expected: exit code 0
#  - reuses the existing test JSON from ar-1 (same skill, same trigger phrases)
#  - test cases must still pass; if any change in stdout structure breaks a
#    case, update the JSON in the same plan that introduces the structural
#    change (do NOT loosen the assertion)
```

## Out of Scope for ar-2 (deferred to later ar-* phases)

| Item | Phase | Notes |
|---|---|---|
| Real Verifier agent loop with web tools | ar-3 | Verifier remains the ar-1 stub through ar-2 close; `--max-iter-verifier` flag is plumbed but not exercised |
| Tavily REST primary + Brave REST fallback live integration | ar-3 | Operator note above: keys must land in `~/.hermes/.env` before ar-3 execute |
| Vertex Gemini `google_search_grounding` opt-in (TOOL-03 / CONFIG-03) | ar-3 | `--no-grounding` flag is plumbed in ar-2 but its **behavior** activates only after ar-3 wires Grounding into `from_env()` |
| `--dump-state <path>` CLI flag (CLI-02) | ar-4 | Distinct from ar-2's three flags; do NOT add it now |
| `research_stream()` body + telemetry JSONL writes (LIB-08) | ar-4 | ar-1 ships the function with `raise NotImplementedError("ar-4")`; ar-2 does NOT touch the body |
| Smoke test on `"Hermes Harness 深度解析"` with all 5 conditions (≥3 imgs, conf≥60, ≤120s, lang=zh, no failed stage) (TEST-05) | ar-4 | The query may be exercised in ar-2 Layer 2 smoke for behavior verification, but the formal pass-condition gate is ar-4 |
| Side-by-side review vs ground-truth Telegram session (TEST-06) | ar-4 | Manual milestone-close gate |
| Synthesizer prompt engineering for final tuning | ar-4 | ar-2 lands caption-anchoring (the alt-text shape change); prompt-quality polish for image relevance / verbosity matching is ar-4 |
| LLM-driven query language detection | ar-4 | ar-1's CJK-ratio heuristic stays; swap-in lands alongside final Synthesizer prompt tuning |
| HTTP endpoint pre-build | post-milestone | Future requirement HTTP-01..03 |
| Pre-commit infra for CONTRACT-01 grep | post-milestone or v1.1 | Documented checklist remains the enforcement vehicle |

## Related artifacts

- `.planning/PROJECT-Agentic-RAG-v1.md` — milestone charter
- `.planning/REQUIREMENTS-Agentic-RAG-v1.md` — full 41-REQ list with ar-2 mapping
- `.planning/ROADMAP-Agentic-RAG-v1.md` — 4-phase decomposition + cross-phase touches
- `.planning/STATE-Agentic-RAG-v1.md` — current milestone state (ar-1 closed; will be updated end of ar-2 planning)
- `.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md` — sibling phase context (this CONTEXT mirrors its template)
- `.planning/phases/ar-1-mvp-vertical-slice/ar-1-04-SUMMARY.md` — ar-1 close evidence
- `docs/design/agentic_rag_internal_api.md` — locked design doc (final)
- `lib/research/stages/reasoner.py` — ar-1 stub; ar-2 replaces body
- `lib/research/stages/synthesizer.py` — ar-1 minimal synth; ar-2 changes alt-text source
- `lib/research/__main__.py` — CLI entrypoint; ar-2 extends `_parse_args` + `_amain`
- `lib/vision_cascade.py` — TOOL-04 dependency (no edits — reuse only)
- `omnigraph_search/query.py` — KG dependency via `kg_search` tool (no edits — reuse only)

## Plan-file authoring conventions (orchestrator handoff to gsd-planner)

Each plan in this phase follows the kb-1-01 template (same as ar-1):

- YAML frontmatter: `phase`, `plan`, `type`, `wave`, `depends_on`, `files_modified`,
  `autonomous: true`, `requirements`, `must_haves` (truths / artifacts / key_links)
- `<objective>` — purpose + output
- `<execution_context>` — `@$HOME/.claude/get-shit-done/workflows/execute-plan.md`
  + `templates/summary.md`
- `<context>` — `@`-references for files the executor must read first; `<interfaces>`
  block for cross-cutting type contracts
- `<tasks>` — atomic numbered tasks each with `<read_first>`, `<files>`, `<behavior>`
  (TDD when applicable), `<action>`, `<verify>`, `<acceptance_criteria>`, `<done>`
- `<verification>` — phase-level (must include CONTRACT-01 + CONTRACT-02 grep re-check)
- `<success_criteria>` — phase-level (must include the 5 ROADMAP success criteria for ar-2)
- `<output>` — SUMMARY.md path the executor writes after completion

**MANDATORY operator note** — every ar-2 PLAN.md must end with the following
literal line (so it surfaces in execute-plan agent context regardless of which
plan ships first):

```
> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env
```

---

*Phase context authored 2026-05-22 by `/gsd:plan-phase ar-2 --skip-research` orchestrator.
Manual GSD gates (parallel-track milestone) — gsd-tools.cjs not invoked.*
