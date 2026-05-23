---
phase: ar-3-verifier-web-tools
milestone: Agentic-RAG-v1
status: planned
last_updated: "2026-05-23"
plans: []
requirements_in_scope: 7
requirements:
  - ORCH-04
  - TOOL-01
  - TOOL-02
  - TOOL-03
  - CONFIG-03
  - TEST-02
  - TEST-04
---

# ar-3 — Verifier + Web Tools (Phase Context)

> **Parallel-track milestone**: this phase belongs to `Agentic-RAG-v1`, not v3.4.
> Sibling files: `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-Agentic-RAG-v1.md`.
> `gsd-tools.cjs` does NOT recognize the `-Agentic-RAG-v1` suffix — every gate in
> this phase is hand-driven by the orchestrator. Do NOT call `gsd-tools.cjs init`
> for this phase.

## Goal

Replace the ar-1 stub Verifier with a **real bounded LLM agent loop** that
fact-checks the Reasoner's output against external web sources, and wire three
real web tools — **Tavily** (primary), **Brave Search** (fallback), and
**Vertex Gemini Google Search Grounding** (opt-in, only when LLM provider is
Vertex Gemini).

Concretely, after ar-3 completes:

1. `Verifier.run()` executes a tool-using LLM loop with `web_search`,
   `web_extract`, and conditionally `google_search_grounding` exposed as tools;
   loop terminates at `iter_count <= cfg.max_iter_verifier` (default 3) and the
   returned `VerifierOutput.iter_count` reflects the real number of turns;
   `confidence: float` is the model-reported fact-check confidence (0.0–100.0)
2. `cfg.web_search` is a live Tavily REST callable: `(query: str) -> list[dict]`
3. `cfg.web_extract` is a live Tavily extract callable: `(url: str) -> str`
4. `cfg.web_search_fallback` is a live Brave REST callable invoked **exactly
   once** per primary failure (Tavily error / quota / timeout) — verified by a
   mock-based fallback test (TEST-02)
5. `ResearchConfig.from_env()` auto-detects Vertex Gemini provider via either
   `__module__ == "lib.vertex_gemini_complete"` on the bound `llm_complete`
   callable **OR** `OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"`; only in that
   case `cfg.google_search_grounding` is set non-None and added to the Verifier
   tool registry
6. The `--no-grounding` CLI flag (plumbed in ar-2) now actually **enforces
   opt-out** — when set, `cfg.google_search_grounding=None` regardless of
   auto-detection
7. Mock-based cap tests (TEST-04) confirm both loops terminate at their cap
   without raising: Reasoner at `max_iter_reasoner` and Verifier at
   `max_iter_verifier`

The full milestone-close smoke (TEST-05 — Hermes Harness 深度解析 with all 5
pass conditions) and `research_stream()` / `--dump-state` (TEST-05/06, LIB-08,
CLI-02) remain explicitly deferred to ar-4.

ar-3 introduces real external HTTP I/O into the pipeline for the first time.
The contract shape (7 frozen dataclasses + strict pipeline order + best-effort
failure) is identical to ar-1/ar-2 and **does not change** here.

## Locked Design Constraints (from `docs/design/agentic_rag_internal_api.md`)

Treat the design doc as final. All 10 architectural axes + 10 closed Q's are
non-negotiable. ar-1/ar-2's CONTEXT carried this verbatim block; ar-3 inherits
it unchanged. Reproduced here so this CONTEXT is self-contained.

### Five API design rules (Axes 1-5)

1. **Pure async entrypoint** — `async def research(query, config) -> ResearchResult`;
   no `print`, no file I/O, no `argv` parsing inside `lib/research/`. ar-3 keeps
   this — Tavily/Brave callables are constructed at `from_env()` time and
   injected via `ResearchConfig`
2. **No module-level singletons** — every external dep injected via
   `ResearchConfig`. ar-3's Verifier reads `cfg.llm_complete`, `cfg.web_search`,
   `cfg.web_extract`, and conditionally `cfg.google_search_grounding`
3. **Env read once at config construction** — hot path uses dataclass fields
   only; `os.environ[...]` confined to `ResearchConfig.from_env()`. ar-3 reads
   `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY` (and possibly `OMNIGRAPH_LLM_PROVIDER`
   for auto-detect) **only inside `from_env()`** — the Verifier loop and the
   web-tool callables themselves must not read env directly
4. **Opt-in side effects** — `output_dir` and `telemetry_jsonl` nullable;
   default-null run produces no file I/O. ar-3 unchanged. The web tool HTTP
   calls are NOT considered "side effects" in this rule's sense (they are tool
   I/O against external services, governed instead by Axis 3 best-effort)
5. **Streaming peer** — `async def research_stream(query, config) -> AsyncIterator[Event]`
   exists alongside `research()`; the body is still `raise NotImplementedError("ar-4")`.
   ar-3 does NOT touch the body — agent-loop event emission is an ar-4 concern

### Seven frozen dataclasses (verbatim shapes — unchanged from ar-1/ar-2)

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

These shapes do NOT change in ar-3. `VerifierOutput` already carries
`fact_check_summary_md`, `confidence: float`, `external_citations: list[Source]`,
`discrepancies: list[str]`, and `iter_count: int` from ar-1 — ar-3 fills them
with real values rather than empty/zero. The four `ResearchConfig` web/grounding
slots already exist as Callable fields — ar-3 wires them, does not redeclare.

### Strict pipeline order (Axis 1) — unchanged

WebBaseline → Retriever → Reasoner → Verifier → Synthesizer.

Sequential. Parallelism is permitted ONLY within a single stage's internal
agent loop or batched tool calls — **explicitly including** the Verifier
issuing multiple `web_search` / `web_extract` calls in parallel within one
iteration (Axis 6). Inter-stage re-ordering or pipelining is prohibited.

### Best-effort failure handling (Axis 3) — unchanged

Every stage `try`/`except`s its own work. On any exception, return a stub
instance with `status="failed"` + `reason=str(e)`. **The Verifier agent loop
must catch tool-call exceptions, prompt-completion exceptions, and runaway
iter_count overflow.** No stage may raise out to the orchestrator.

**Tool-call exception semantics** (ar-3-specific): a primary `web_search`
exception triggers the Brave fallback exactly once per primary failure. If the
fallback also fails, the tool call returns `[]` to the loop and the loop
records this internally — the loop itself does not fail. The Verifier stage
only fails if the LLM completion call raises or some other non-tool exception
escapes.

### Cap semantics (unchanged from ar-2 Reasoner)

Reaching the cap is NOT a failure — return `status="ok"` with whatever was
collected so far (the cap is a budget, not an error condition); a separate
"cap exhausted" log line is fine but does not change `status`. This applies
to BOTH Reasoner (consolidated test in ar-3 per TEST-04) and Verifier.

### Output language matches query language (Axis 10)

Single Synthesizer prompt instruction. ar-3 does not touch the Synthesizer.
Verifier's `fact_check_summary_md` may be in any language the LLM picks; the
Synthesizer is responsible for output-language coherence.

## Reality-State Deltas (vs design doc 2026-05-06 + post-ar-2 state)

The design doc was authored 2026-05-06. ar-1 closed 2026-05-22 (commits
962f995..cbd432d), ar-2 closed 2026-05-23 (commits 0674f66, 942dc48, 5aedf57,
8ca46ad, 8cd2642, 08edd1d). Reality deltas vs the design that affect ar-3:

| Item | Design state | Current state (post-ar-2) | Effect on ar-3 |
|---|---|---|---|
| `lib/research/` package | not built | shipped, importable as `omnigraph.research` | ar-3 adds `lib/research/tools/web_search.py` (NEW submodule) but no top-level package changes |
| Verifier stub | "deterministic placeholder" | `status="skipped"`, `iter_count=0`, empty lists, `confidence=0.0` (`verifier.py` ar-1 form) | ar-3 replaces the stub body — keep signature `(query, cfg, reasoned) -> VerifierOutput` |
| Reasoner real loop | "deterministic placeholder" in ar-1 | shipped in ar-2 (commit 0674f66) — bounded LLM agent loop with kg_search + vision_analyze tools | ar-3 reuses Reasoner for cap test (TEST-04 Reasoner-half); does NOT modify reasoner.py |
| `cfg.web_search` slot | typed as `Callable[[str], list[dict]]` | populated by `_skipped_web_search` stub (returns `[]`) regardless of `TAVILY_API_KEY` | ar-3 swaps the stub for a live Tavily callable when `TAVILY_API_KEY` set; stub stays as fallback when unset |
| `cfg.web_search_fallback` slot | typed `Callable | None` | always `None` post-ar-2 | ar-3 wires Brave callable when `BRAVE_SEARCH_API_KEY` set |
| `cfg.web_extract` slot | typed `Callable | None` | always `None` post-ar-2 | ar-3 wires Tavily extract callable (separate function from web_search) when `TAVILY_API_KEY` set |
| `cfg.google_search_grounding` slot | typed `Callable | None` | always `None` post-ar-2 | ar-3 wires Vertex Grounding callable IFF (a) Vertex provider auto-detected, (b) `--no-grounding` not set |
| CLI `--no-grounding` flag | not yet plumbed | plumbed in ar-2 (commit 8ca46ad) — sets `overrides["google_search_grounding"] = None` always | ar-3 changes `from_env()` so the flag actually has work to do (i.e., `from_env()` may return non-None grounding which the CLI override then nullifies) |

**None of these deltas invalidate any locked decision.** ar-3 is a
behavior-only phase — no shape changes, no new contracts. New env vars
(`TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`) were already documented as ar-1
CONFIG-01/02 placeholders; ar-3 promotes them from documented-but-stub to
actually-read-and-wired.

## ar-3 component contracts

### TOOL-01: Tavily REST integration (Wave 1)

**Two callables**, constructed inside `from_env()` and injected via
`ResearchConfig`. Both live in a new submodule `lib/research/tools/web_search.py`
to keep `config.py` thin (config.py imports the factories, does not host the
HTTP code).

```python
# lib/research/tools/web_search.py
async def tavily_search(query: str, *, api_key: str, top_k: int = 10) -> list[dict]:
    """Hits POST https://api.tavily.com/search.
    Returns list of result dicts: [{"title": str, "url": str, "content": str, "score": float}, ...].
    Raises on HTTP error / non-2xx / timeout / parse error — caller (cascade) handles.
    """

async def tavily_extract(url: str, *, api_key: str) -> str:
    """Hits POST https://api.tavily.com/extract.
    Returns extracted markdown content as str. Raises on error.
    """
```

**Construction-time bind** (in `from_env()`):

```python
import functools
api_key = os.environ.get("TAVILY_API_KEY")
if api_key:
    web_search = functools.partial(tavily_search, api_key=api_key)
    web_extract = functools.partial(tavily_extract, api_key=api_key)
else:
    web_search = _skipped_web_search  # ar-1 stub
    web_extract = None
```

The bound callables match the `Callable[[str], list[dict]]` /
`Callable[[str], str]` shapes the dataclass declares.

**Timeout policy**: Tavily HTTP timeout is fixed at 15 s per call. No env
override (avoid sprawl; the cap is plenty for a search API). Timeouts surface
as exceptions to the cascade.

### TOOL-02: Brave REST fallback (Wave 1)

Same submodule, separate factory:

```python
async def brave_search(query: str, *, api_key: str, top_k: int = 10) -> list[dict]:
    """Hits GET https://api.search.brave.com/res/v1/web/search?q=...
    Header: X-Subscription-Token: <api_key>.
    Returns list of result dicts: [{"title": str, "url": str, "content": str}, ...].
    Raises on HTTP error / non-2xx / timeout / parse error.
    """
```

**Cascade wiring** (Wave 1 deliverable — lives in `lib/research/tools/web_search.py`):

```python
def make_web_search_with_fallback(
    primary: Callable[[str], list[dict]],
    fallback: Callable[[str], list[dict]] | None,
) -> Callable[[str], list[dict]]:
    """Returns a single async callable that tries primary; on ANY exception,
    invokes fallback exactly once. If fallback is None, exception propagates.
    Per-call independence: failure on call N does NOT disable primary for call N+1.
    """
```

**`from_env()` wiring**:

```python
brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
if brave_key:
    web_search_fallback = functools.partial(brave_search, api_key=brave_key)
else:
    web_search_fallback = None

# Wrap the primary with cascade so cfg.web_search itself becomes the cascade
if api_key and brave_key:
    web_search = make_web_search_with_fallback(
        functools.partial(tavily_search, api_key=api_key),
        functools.partial(brave_search, api_key=brave_key),
    )
elif api_key:
    web_search = functools.partial(tavily_search, api_key=api_key)
else:
    web_search = _skipped_web_search
```

`cfg.web_search_fallback` is exposed for tests / observability, but the Verifier
loop calls `cfg.web_search` (which is already the cascade-wrapped form when both
keys are present).

**Cascade semantics** (locked, do not reinvent): "exactly once per primary
failure" means the wrapper invokes primary; on exception, invokes fallback
exactly once; whatever fallback returns (or raises) is returned/raised by the
wrapper. No retry of primary, no retry of fallback within the wrapper. The
Verifier loop may decide to retry the cascade as a whole on subsequent
iterations — that is loop-level retry, not cascade-level retry.

### ORCH-04: Verifier real LLM agent loop (Wave 2)

**Tool registry** (built inside `Verifier.run()` per-invocation):

```python
async def web_search_tool(query: str) -> list[dict]:
    return await cfg.web_search(query)

async def web_extract_tool(url: str) -> str:
    if cfg.web_extract is None:
        raise RuntimeError("web_extract not configured")
    return await cfg.web_extract(url)

# Conditionally registered:
if cfg.google_search_grounding is not None:
    async def grounding_tool(query: str) -> str:
        return await cfg.google_search_grounding(query)
```

**Loop shape** (mirrors Reasoner pattern from ar-2):

```python
iter_count = 0
collected_citations: list[Source] = []
discrepancies: list[str] = []
while iter_count < cfg.max_iter_verifier:
    iter_count += 1
    tool_call = await cfg.llm_complete(...)  # produces tool calls or final fact-check
    if tool_call.is_final:
        # parse final summary + confidence + discrepancies
        break
    # dispatch tool_call against {web_search_tool, web_extract_tool, [grounding_tool]}
    # accumulate web results into collected_citations
return VerifierOutput(
    fact_check_summary_md=final_summary,
    confidence=final_confidence,
    external_citations=collected_citations,
    discrepancies=discrepancies,
    iter_count=iter_count,
    status="ok",
)
```

Hard requirements:

- `iter_count` is the **post-loop** value (number of agent turns actually
  taken), NOT a counter pre-incremented past the cap
- `iter_count <= cfg.max_iter_verifier` ALWAYS holds (cap enforcement is part
  of the loop condition)
- Any exception inside the loop → return
  `VerifierOutput(status="failed", reason=str(e), iter_count=iter_count, ...)`
  with `confidence=0.0` and empty lists (Axis 3 best-effort)
- Reaching the cap is NOT a failure — return `status="ok"` with whatever was
  collected so far; the model's last reported confidence (if any) is used,
  else `0.0`
- `confidence` is parsed from the LLM's final-answer payload; clamp to
  `[0.0, 100.0]`. If parse fails, default to `0.0` and append a discrepancy
  noting the parse failure
- The Reasoner's output is the verification subject — Verifier's prompt MUST
  include `reasoned.inferences_md` so the LLM has something to fact-check.
  Verifier does NOT touch any other `ResearchState` field

**Tool-call parallelism** (Axis 1 carve-out): a single iteration MAY run
multiple `web_search` / `web_extract` calls in parallel via `asyncio.gather()`
if the LLM emits multiple tool calls in one turn. Same blessing as Reasoner.

### TOOL-03: Vertex Gemini Google Search Grounding (Wave 3)

Conditionally wired in `from_env()`. **Auto-detect** logic:

```python
# Two equivalent signals — either one promotes Grounding to "available":
_provider_env = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "").strip().lower()
_llm_module = getattr(llm_complete, "__module__", "")

is_vertex = (
    _provider_env == "vertex_gemini"
    or _llm_module == "lib.vertex_gemini_complete"
)

if is_vertex:
    from lib.research.tools.web_search import vertex_gemini_grounding
    google_search_grounding = vertex_gemini_grounding  # zero-arg bind; reads its own env at call time
else:
    google_search_grounding = None
```

The Grounding callable wraps a Vertex Gemini search tool invocation. ar-3
implements the wrapper as a thin pass-through — full prompt-engineering is
deferred to ar-4 final-tuning. Hard rule: when not Vertex, `cfg.google_search_grounding`
is **None** unconditionally; the Verifier's tool registry omits the grounding
tool in that case.

**`--no-grounding` interaction** (ties together with CLI-03 plumbing from
ar-2): the CLI sets `overrides["google_search_grounding"] = None` regardless
of `from_env()` value; `dataclasses.replace(cfg, **overrides)` applies the
override. So the precedence is: `--no-grounding` (CLI) > auto-detect (env) >
None (default).

### CONFIG-03: from_env() updates (Wave 1 + Wave 3)

CONFIG-03 spans two waves because the env reads themselves split:

- Wave 1 reads `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY` and wires the web
  cascade. Drops the `_skipped_web_search` placeholder when keys are present.
- Wave 3 adds the Vertex auto-detect logic and the conditional Grounding
  wiring. Touches `from_env()` again but does NOT alter Wave 1's web cascade.

**No new env vars beyond the two already-declared keys.** The auto-detect
reuses `OMNIGRAPH_LLM_PROVIDER` (already documented as part of ar-2 LLM
provider selection).

**Enforcement check** (verifier-side correctness, automatable):

```python
# Construct two configs with different llm_complete origin paths:
deepseek_cfg = ResearchConfig(..., llm_complete=deepseek_complete, ...)
vertex_cfg   = ResearchConfig(..., llm_complete=vertex_gemini_complete, ...)
# After from_env() with OMNIGRAPH_LLM_PROVIDER=vertex_gemini,
# vertex_cfg.google_search_grounding is non-None;
# deepseek_cfg.google_search_grounding is None.
# Verifier tool registry differs by exactly ONE entry: google_search_grounding.
```

This is a CONFIG-03 acceptance test (TEST-04 sibling).

### TEST-02: Brave fallback mock test (Wave 1)

**Behavior asserted** (mock-based, no live HTTP):

1. `cfg.web_search` is a cascade callable wrapping mocked Tavily + mocked Brave
2. Tavily mock raises `httpx.TimeoutException` (or `RuntimeError` proxying for
   any network-level failure) on the first call
3. Brave mock returns `[{"title": "...", "url": "...", "content": "..."}]`
4. After invoking `cfg.web_search(query)`, assert:
   - Tavily mock called exactly 1 time
   - Brave mock called exactly 1 time
   - Returned list equals Brave's mock output (cascade does NOT merge results;
     fallback fully replaces)
5. Second invocation of `cfg.web_search(query)`: Tavily mock is called again
   (per-call independence — failure on call N does NOT disable primary for
   call N+1)

**Negative case**: Tavily succeeds → Brave never called.

### TEST-04: Cap enforcement (Wave 2 Verifier-half + Wave 3 Reasoner-half)

ROADMAP Success Criterion #5 covers BOTH loops. Decomposition:

- **Verifier cap test** (Wave 2 deliverable): mock `cfg.llm_complete` to always
  emit `tool_call(web_search, ...)` (never finalizes); assert
  `result.iter_count == cfg.max_iter_verifier` (default 3) and
  `result.status == "ok"` (cap = budget, not failure)
- **Reasoner cap test** (Wave 3 consolidation): same shape, mock
  `cfg.llm_complete` for Reasoner; assert `result.iter_count == cfg.max_iter_reasoner`
  (default 5) and `result.status == "ok"`

Both tests use mocks — no live LLM. Both tests assert `status="ok"` (the
"cap-hit-is-ok" rule from § Cap semantics above). Tests live in the same
`tests/unit/research/` directory as existing TEST-03 fixtures; suggested
filename `test_caps_consolidated.py` (Wave 3 owns the file but Wave 2 may
add a Verifier-only file `test_verifier_cap.py` that Wave 3 absorbs/extends).

## Configuration

`ResearchConfig.from_env()` reads new env vars in ar-3:

| Env var | Required | Default | ar-3 effect |
|---|---|---|---|
| `TAVILY_API_KEY` | No (recommended for Verifier real path) | unset → `_skipped_web_search` stub | Wave 1: when set, wires Tavily primary `web_search` + `web_extract` callables. When unset, Verifier still runs but `web_search_tool` returns `[]` and the loop typically records this as a discrepancy then finalizes |
| `BRAVE_SEARCH_API_KEY` | No (recommended for fallback) | unset → `web_search_fallback=None` | Wave 1: when set AND Tavily key set, wraps primary in cascade. When set without Tavily, Brave is unused (cascade requires both ends) |
| `OMNIGRAPH_BASE_DIR` | No | `~/.hermes/omonigraph-vault` (typo `omonigraph` is canonical — DO NOT fix) | Unchanged from ar-1/ar-2 |
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | Wave 3: drives Grounding auto-detect; `vertex_gemini` value triggers Grounding wiring |
| `OMNIGRAPH_GEMINI_KEY` / `GEMINI_API_KEY` | (provider-dependent) | — | Read by `from_env()` if Vertex Gemini is selected; the Grounding callable also relies on this for its own auth (read at call time, not at config construction) |
| `OMNIGRAPH_RESEARCH_OUTPUT_DIR` | No | None | Unchanged |
| `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` | No | None | Unchanged (telemetry body lands in ar-4) |

**No HTTP-timeout env vars** introduced. Tavily / Brave timeouts hardcoded at
15 s per call; if they need tuning later it's an ar-4 / v1.1 follow-up.

> **Operator note (carry into every ar-3 PLAN.md):**
> ar-3 execute requires `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` to be
> injected into `~/.hermes/.env` on the Hermes deployment target before any
> Layer 2 (CLI) smoke test or Layer 3 (skill_runner) smoke test can verify
> the live web-tool path. Wave 1 and Wave 2 unit tests use mocks and do NOT
> require live keys. Wave 3 Grounding test also uses mocks. The live-key smoke
> is the phase-close gate, not a per-wave gate.

## CONTRACT enforcement (carried forward — re-check at ar-3 acceptance)

CONTRACT-01 and CONTRACT-02 were enforced in ar-1 and re-verified in ar-2.
ar-3 must NOT introduce any new import or hardcoded path that breaks them.

### CONTRACT-01: only `omnigraph_search.query.search` from KG side

```bash
hits=$(grep -rE "from omnigraph_search" lib/research/ \
  --include='*.py' \
  | grep -vE "from omnigraph_search\.query " \
  | grep -vE "from omnigraph_search\.query$" \
  | grep -vE "import omnigraph_search\.query" \
  || true)
if [ -n "$hits" ]; then
  echo "CONTRACT-01 violation"; echo "$hits"; exit 1
fi
```

ar-3 risk surface: the Verifier does NOT touch `omnigraph_search` (its tools
are external HTTP only). The new `lib/research/tools/web_search.py` file must
import zero `omnigraph_search` symbols.

### CONTRACT-02: no hardcoded `~/.hermes` / `omonigraph-vault` paths

```bash
grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary"
# expected: 0 hits
```

ar-3 risk surface: web tool callables receive `query: str` / `url: str`
arguments — no filesystem paths flow through them. Auto-detect logic in
`from_env()` may read `OMNIGRAPH_BASE_DIR` indirectly via existing `from_env()`
plumbing but does NOT introduce new path literals.

### Cross-milestone contract: `omnigraph_search.query.search` is read-only

ar-3 introduces zero new touchpoints to the KG side. Verifier has no KG
access (by design — it fact-checks against the **external** web).

## Smoke test for ar-3

Three layers, all must pass before phase is marked complete. Layers 1 and 3 are
identical in shape to ar-2; Layer 2 splits into a "no-keys-required" structural
form (cap=0 on Verifier — bypasses tool registry entirely) and a
"keys-required" live form (only run when operator note above is satisfied).

### Layer 1 — pytest

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v
# expected: all green
#   - all 88 ar-1+ar-2 tests still pass (regression guard)
#   - new tests for Tavily callable shape (Wave 1)
#   - new tests for Brave fallback cascade (Wave 1, TEST-02)
#   - new tests for Verifier real loop (Wave 2, ORCH-04)
#   - new tests for Verifier cap (Wave 2, TEST-04 Verifier-half)
#   - new tests for Grounding auto-detect (Wave 3, TOOL-03/CONFIG-03)
#   - new tests for Reasoner cap (Wave 3, TEST-04 Reasoner-half)
# Target ≥110 green (88 baseline + ~25 new across 3 waves)
```

### Layer 2a — cap=0 LLM-free CLI smoke (mandatory, no keys required)

```bash
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 0 \
  --max-iter-verifier 0 \
  --no-grounding \
  "什么是 Hermes Harness 深度解析"
# expected:
#  - exit code 0
#  - stdout: non-empty markdown (≥ 200 chars)
#  - markdown contains query echo
#  - Verifier emits status='ok' with iter_count=0 (cap=0 → loop body never executes)
#  - Synthesizer degradation note line for Verifier may be empty (status=ok → no note)
#    or may show a confidence=0 note line — both acceptable
#  - no stage raises; ResearchState dataclass populates all 5 stage fields
```

This smoke is mandatory at Wave 3 close and exercises the CLI plumbing without
touching live external services.

### Layer 2b — live-key end-to-end CLI smoke (phase-close gate, keys required)

```bash
# requires TAVILY_API_KEY and BRAVE_SEARCH_API_KEY in env / ~/.hermes/.env
venv/Scripts/python.exe -m omnigraph.research \
  "什么是 Hermes Harness 深度解析"
# expected (ar-3 phase-close gate, NOT a per-wave gate):
#  - exit code 0
#  - stdout: non-empty markdown
#  - state.verified.iter_count >= 1
#  - state.verified.confidence > 0.0 (real LLM-reported value)
#  - state.verified.external_citations non-empty (real Tavily results)
#  - no stage raises
```

The full TEST-05 milestone-close gate (≥ 3 inline images, confidence ≥ 60,
≤ 120 s wallclock, language=zh) remains an ar-4 concern.

### Layer 3 — skill_runner

```bash
venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
  --test-file tests/skills/test_omnigraph_research.json
# expected: exit code 0
#  - reuses the existing test JSON from ar-1/ar-2 (same skill, same trigger phrases)
#  - if ar-3 alters stdout structure for any test case, the JSON is updated in
#    the same plan that introduces the structural change (do NOT loosen the assertion)
```

## Out of Scope for ar-3 (deferred)

| Item | Phase | Notes |
|---|---|---|
| `research_stream()` body + JSONL telemetry writes (LIB-08) | ar-4 | ar-1 ships with `raise NotImplementedError("ar-4")`; ar-3 does NOT touch the body |
| `--dump-state <path>` CLI flag (CLI-02) | ar-4 | Distinct from ar-2/ar-3 flags |
| Smoke test all 5 conditions (TEST-05) | ar-4 | Includes ≥3 inline images, confidence≥60, ≤120s — full milestone-close gate |
| Manual side-by-side audit (TEST-06) | ar-4 | Milestone-close manual gate |
| Vertex Grounding prompt-tuning | ar-4 | ar-3 ships a thin pass-through wrapper; final prompt-engineering folds in with Synthesizer prompt tuning |
| HTTP timeout env-var override | ar-4 / v1.1 | ar-3 hardcodes 15 s |
| HTTP endpoint pre-build | post-milestone | Future requirement HTTP-01..03 |
| Pre-commit infra for CONTRACT-01 grep | post-milestone or v1.1 | Documented checklist remains the enforcement vehicle |

## Wave decomposition (orchestrator-confirmed 2026-05-23)

ar-3 is split into 3 strictly sequential waves (no in-phase parallelism).
Capability-first: build primitives → wire consumer → opt-in extension.

- **Wave 1 (ar-3-01) — web-tools**: TOOL-01 (Tavily search + extract), TOOL-02
  (Brave fallback), TEST-02 (mock fallback test), CONFIG-03 (env-read half for
  TAVILY+BRAVE keys; cascade wiring in `from_env()`). Files:
  `lib/research/tools/__init__.py` (NEW), `lib/research/tools/web_search.py`
  (NEW), `lib/research/config.py` (modified), `tests/unit/research/test_web_tools.py`
  (NEW).
- **Wave 2 (ar-3-02) — verifier-loop**: ORCH-04 (Verifier real LLM agent loop),
  TEST-04 Verifier-half (cap test for Verifier). Consumes Wave 1 callables.
  Files: `lib/research/stages/verifier.py` (rewrite), `tests/unit/research/test_verifier_agent_loop.py`
  (NEW), `tests/unit/research/test_verifier_cap.py` (NEW — may be absorbed into
  Wave 3's consolidated cap test file at Wave 3's discretion).
- **Wave 3 (ar-3-03) — grounding + caps**: TOOL-03 (Vertex Gemini Grounding),
  CONFIG-03 finalize (auto-detect logic in `from_env()`), TEST-04 Reasoner-half
  (consolidated cap test for both loops). Files:
  `lib/research/tools/web_search.py` (modify — add `vertex_gemini_grounding`),
  `lib/research/config.py` (modify — auto-detect logic), `tests/unit/research/test_grounding_autodetect.py`
  (NEW), `tests/unit/research/test_caps_consolidated.py` (NEW or
  absorbing-Wave-2's cap file).

## Related artifacts

- `.planning/PROJECT-Agentic-RAG-v1.md` — milestone charter
- `.planning/REQUIREMENTS-Agentic-RAG-v1.md` — full 41-REQ list with ar-3 mapping
- `.planning/ROADMAP-Agentic-RAG-v1.md` — 4-phase decomposition + cross-phase touches
- `docs/design/agentic_rag_internal_api.md` — locked design doc
- `lib/research/stages/verifier.py` — current ar-1 stub (will be rewritten in Wave 2)
- `lib/research/config.py` — `from_env()` extension point (touched in Waves 1 + 3)
