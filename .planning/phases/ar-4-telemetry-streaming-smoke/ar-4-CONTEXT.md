---
phase: ar-4-telemetry-streaming-smoke
milestone: Agentic-RAG-v1
status: planned
last_updated: "2026-05-23"
plans: []
requirements_in_scope: 4
requirements:
  - LIB-08
  - CLI-02
  - TEST-05
  - TEST-06
---

# ar-4 — Telemetry, streaming, smoke pass + milestone audit (Phase Context)

> **Parallel-track milestone**: this phase belongs to `Agentic-RAG-v1`, not v3.4.
> Sibling files: `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-Agentic-RAG-v1.md`.
> `gsd-tools.cjs` does NOT recognize the `-Agentic-RAG-v1` suffix — every gate in
> this phase is hand-driven by the orchestrator. Do NOT call `gsd-tools.cjs init`
> for this phase.

> **Milestone-closing phase.** ar-4 closes Agentic-RAG-v1. Successful completion
> of TEST-05 (smoke) + TEST-06 (manual audit) = closure of the milestone.
> No further ar-N phase exists after ar-4.

## Goal

Three deliverables wrap the milestone:

1. **Telemetry plumbing + streaming peer body** (LIB-08): `research_stream(query, config)`
   becomes a real `AsyncIterator[dict]` that emits one event per stage minimum;
   when `cfg.telemetry_jsonl` is set, the same events also append to a JSONL
   file. The blocking `research()` is augmented to write the same JSONL when
   the sink is configured (one shared serializer; no double implementation).
2. **`--dump-state <path>` CLI flag** (CLI-02): dumps `ResearchState` as
   per-stage JSONL entries so debug tooling can replay or inspect any run
   without re-running the pipeline.
3. **Milestone-close gates** (TEST-05 + TEST-06): the Hermes Harness 深度解析
   smoke must satisfy ALL 5 pass conditions, and a manual side-by-side audit
   against the ground-truth Telegram session must score ≥3/5 on each of 5
   audit dimensions. Audit results are recorded in
   `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`.

Concretely, after ar-4 completes:

1. `research_stream(query, config)` yields a typed event dict per stage at
   minimum; supports per-tool-call events when convenient. Each event has at
   least `{"event_type": str, "stage": str, "ts": float, ...}` plus
   stage-specific payload fields.
2. `cfg.telemetry_jsonl` (existing dataclass field) is honored: when non-None,
   each emitted event is appended as one JSON line to the file. When None,
   events flow only through the iterator (no file I/O — Axis 4 opt-in).
3. `python -m omnigraph.research --dump-state <path> "<query>"` runs the
   blocking `research()` and writes the resulting `ResearchState` as JSONL
   (one line per stage, plus a header line with query/timestamp). Existing
   markdown stdout output is preserved; `--dump-state` is purely additive.
4. Smoke test `python -m omnigraph.research "Hermes Harness 深度解析"`
   produces markdown that satisfies ALL 5 conditions (see § TEST-05 below).
5. Manual side-by-side audit produces a written verdict in
   `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` with 5 scored dimensions,
   each ≥3/5, plus narrative justification. This is the milestone-close gate.

ar-4 introduces the **first real file-I/O sink** in the pipeline (telemetry
JSONL). All file I/O remains opt-in via nullable config fields (Axis 4).
The contract shape (7 frozen dataclasses + strict pipeline order + best-effort
failure) does NOT change here.

## Locked Design Constraints (from `docs/design/agentic_rag_internal_api.md`)

Treat the design doc as final. All 10 architectural axes + 10 closed Q's are
non-negotiable. ar-1/ar-2/ar-3's CONTEXT carried this verbatim block; ar-4
inherits it unchanged. Reproduced here so this CONTEXT is self-contained.

### Five API design rules (Axes 1-5)

1. **Pure async entrypoint** — `async def research(query, config) -> ResearchResult`;
   no `print`, no `argv` parsing inside `lib/research/`. ar-4 keeps this — the
   blocking entrypoint stays pure; `--dump-state` lives entirely in `__main__.py`.
2. **No module-level singletons** — every external dep injected via
   `ResearchConfig`. ar-4's telemetry sink is read from `cfg.telemetry_jsonl`,
   never `os.environ` at the call site.
3. **Env read once at config construction** — hot path uses dataclass fields
   only; `os.environ[...]` confined to `ResearchConfig.from_env()`. ar-4 reads
   `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` (already documented since ar-1) ONLY
   inside `from_env()`.
4. **Opt-in side effects** — `output_dir` and `telemetry_jsonl` nullable;
   default-null run produces no file I/O. ar-4 lights up the `telemetry_jsonl`
   half. `--dump-state <path>` is opt-in via the CLI flag (default off).
5. **Streaming peer** — `async def research_stream(query, config) -> AsyncIterator[Event]`
   exists alongside `research()`; ar-4 fills the body. Both `research()` and
   `research_stream()` MUST share the same telemetry-emission code path —
   a single sink-layer function consumed by both surfaces. No double
   implementation; no skew.

### Seven frozen dataclasses (verbatim shapes — unchanged from ar-1/ar-2/ar-3)

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

These shapes do NOT change in ar-4. The `telemetry_jsonl` field already exists
on `ResearchConfig` from ar-1 (declared but not honored). ar-4 honors it.
**No new dataclass fields** — telemetry events are plain `dict` payloads, NOT
a frozen dataclass. This is intentional: events are wire-format-only, with
flexibility to evolve fields without bumping `types.py`.

### Strict pipeline order (Axis 1) — unchanged

WebBaseline → Retriever → Reasoner → Verifier → Synthesizer.

Telemetry events are emitted **at stage boundaries** (one per stage minimum).
Per-tool-call events inside Reasoner / Verifier loops are permitted but NOT
required for ar-4 close — the milestone gate (TEST-05) requires only stage-level
telemetry.

### Best-effort failure handling (Axis 3) — unchanged

Every stage `try`/`except`s its own work. Telemetry sink failure must NOT
poison the pipeline: if the JSONL append raises (disk full, permission error,
etc.), swallow the exception (log to stderr if useful) and continue. Telemetry
is observability; it does not control execution.

### Cap semantics (unchanged)

Reaching the cap is NOT a failure — return `status="ok"` with whatever was
collected so far. Telemetry events for cap-hit cases SHOULD include the
`iter_count` value and `status="ok"` so smoke condition (d) — "no stage with
status=failed" — sees a clean state.

### Output language matches query language (Axis 10)

ar-4 does NOT touch the Synthesizer prompt directly. **Exception**: if TEST-05
condition (e) (Chinese language) fails on first run because the model picks
English mid-stream, ar-4 IS allowed to iterate the Synthesizer prompt to
restore Chinese output (per ROADMAP § Cross-phase touches: ORCH-05 may iterate
prompts in ar-4 to hit smoke conditions). This is a contract-preserving
adjustment, not a contract change.

## Reality-State Deltas (vs design doc 2026-05-06 + post-ar-3 state)

The design doc was authored 2026-05-06. ar-1 closed 2026-05-22, ar-2 closed
2026-05-23 morning, ar-3 closed 2026-05-23 evening (commits 6bc7db7, e594363,
17a8fca, phase-close 7a3727f). Reality deltas vs the design that affect ar-4:

| Item | Design state | Current state (post-ar-3) | Effect on ar-4 |
|---|---|---|---|
| `lib/research/` package | not built | shipped, importable as `omnigraph.research`; 5 stages all real (Reasoner ar-2, Verifier ar-3, others ar-1) | ar-4 adds `lib/research/telemetry.py` (NEW) and a `_dump_state` helper in `__main__.py`; no top-level package surface changes |
| `research_stream()` body | "AsyncIterator[Event] alongside research()" | `raise NotImplementedError("ar-4")` at `lib/research/orchestrator.py:65-73` | ar-4 fills the body; both `research()` and `research_stream()` route emissions through one shared sink module |
| `cfg.telemetry_jsonl` slot | "nullable; default-null produces no file I/O" | declared on dataclass, never read | ar-4 honors it; `from_env()` already reads `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` env var |
| `_amain` body in `__main__.py` | not yet built | 15 LOC (pre-ar-4 state, under the 18-LOC cap) | ar-4 adds `--dump-state <path>` flag; `_amain` MUST stay ≤ 18 LOC — heavy lifting goes into a helper function (e.g., `_write_dump_state(state, path)`) inside `__main__.py` |
| Verifier loop | `status="skipped"` stub | real bounded LLM agent loop, returns ok/failed | ar-4's smoke (TEST-05) exercises the live Verifier path with real Tavily/Brave/optionally Vertex Grounding |
| Reasoner loop | "deterministic placeholder" | real bounded agent loop (ar-2-01) | ar-4's smoke exercises Reasoner image-selection + caption-anchored Synthesizer (ar-2-02) — 5-pass condition (a) (≥3 inline images) is satisfied by ar-2 path |
| Cross-milestone contract `omnigraph_search.query.search` | KG-side stable, read-only | unchanged through ar-1/2/3; CONTRACT-01 clean | ar-4 does NOT introduce new touchpoints |
| Local KG embedding dim | 768 (post-ar-2 fixture) | 3072 expected by some chunks vs 768 loaded in others — pre-existing mismatch surfaced as `Retriever status="failed"` in cap=0 smokes | ar-4's TEST-05 live-key smoke MUST run on a Hermes deployment where the KG is freshly re-ingested and dim consistent. Local-dev workstation cap=0 smoke (L2a) tolerates Retriever degradation; the milestone gate runs on Hermes |
| Pytest baseline | 88 (post-ar-2) | 113 (post-ar-3); **1 known flake**: `test_subprocess_smoke_with_max_iter_zero` passes in isolation but occasionally fails in full suite (sub-process spawn / env state pollution; not a regression introduced by ar-3) | ar-4 L1 pytest target is "all green modulo the known flake"; new tests for telemetry + dump-state add ≥10 cases |

**None of these deltas invalidate any locked decision.** ar-4 is a behavior
+ observability phase — no shape changes, no new contracts. New env vars are
already declared (`OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` since ar-1).

## ar-4 component contracts

### LIB-08: research_stream() body + telemetry sink (Wave 1)

**New module**: `lib/research/telemetry.py` (~80-120 LOC).

```python
# lib/research/telemetry.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# Event-type constants — used by both research() and research_stream()
EVENT_PIPELINE_START = "pipeline_start"
EVENT_STAGE_START = "stage_start"
EVENT_STAGE_END = "stage_end"
EVENT_PIPELINE_END = "pipeline_end"

def make_event(event_type: str, stage: str, **payload: Any) -> dict:
    """Build a wire-format event dict. Always carries event_type, stage, ts.
    Extra payload merged in (must be JSON-serializable)."""
    return {"event_type": event_type, "stage": stage, "ts": time.time(), **payload}

def write_event(sink_path: Path | None, event: dict) -> None:
    """Append one JSON line to sink_path if non-None. Swallow I/O exceptions
    (sink failure must not poison the pipeline — Axis 3 best-effort)."""
    if sink_path is None:
        return
    try:
        with sink_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=_json_default) + "\n")
    except OSError:
        pass  # observability is best-effort

def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for Path / dataclass instances."""
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    return str(obj)
```

**Stage-end payload shape** (one per stage, recorded after the stage runs):

```python
{
  "event_type": "stage_end",
  "stage": "web_baseline" | "retriever" | "reasoner" | "verifier" | "synthesizer",
  "ts": <float>,
  "status": "ok" | "skipped" | "failed",  # synthesizer omits — terminal stage
  "reason": <str|null>,                      # if status != "ok"
  "duration_s": <float>,                    # ts - stage_start_ts
  # stage-specific:
  "iter_count": <int>,                      # reasoner / verifier only
  "snippet_count": <int>,                   # web_baseline only
  "chunk_count": <int>,                     # retriever only
  "image_candidate_count": <int>,           # retriever only
  "image_analyzed_count": <int>,            # reasoner only
  "confidence": <float>,                    # verifier / synthesizer only
  "embedded_image_count": <int>,            # synthesizer only
  "note_line_count": <int>,                 # synthesizer only
}
```

**Orchestrator integration** (in `research()` and `research_stream()`):

```python
# research_stream body (replaces the NotImplementedError):
async def research_stream(query, config=None):
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    yield _emit(cfg.telemetry_jsonl, EVENT_PIPELINE_START, stage="pipeline", query=query)

    # WebBaseline
    t0 = time.time()
    yield _emit(cfg.telemetry_jsonl, EVENT_STAGE_START, stage="web_baseline")
    state.web_baseline = await run_web_baseline(query, cfg)
    yield _emit(cfg.telemetry_jsonl, EVENT_STAGE_END, stage="web_baseline",
                status=state.web_baseline.status, reason=state.web_baseline.reason,
                duration_s=time.time()-t0,
                snippet_count=len(state.web_baseline.snippets))
    # ... 4 more stages identically wrapped ...

    yield _emit(cfg.telemetry_jsonl, EVENT_PIPELINE_END, stage="pipeline",
                duration_s=time.time()-state.timestamp_start)

# Where _emit is a tiny helper:
def _emit(sink_path, event_type, **payload):
    event = make_event(event_type, **payload)
    write_event(sink_path, event)
    return event
```

`research()` is then **refactored** to consume `research_stream()` internally:

```python
async def research(query, config=None) -> ResearchResult:
    cfg = config if config is not None else from_env()
    state_holder: dict = {}  # captures the final state via a closure trick
    async for event in research_stream(query, cfg):
        if event["event_type"] == EVENT_PIPELINE_END:
            state_holder["state"] = event["state"]  # research_stream attaches final state
    return ResearchResult.from_state(state_holder["state"])
```

**Alternative implementation** (orchestrator-decision-pending): keep `research()`
as the master loop with stage-level emit, and have `research_stream()` re-walk
the same logic. Both forms are acceptable — gsd-planner picks one. Hard rule:
exactly ONE place defines the stage-emit sequence; both surfaces consume it.

### CLI-02: --dump-state CLI flag (Wave 1)

**Flag**: `--dump-state <path>`. Type: writable-path. Default: None (off).

**Behavior** (in `lib/research/__main__.py`):

1. Run `research()` as today (blocking, returns markdown).
2. If `--dump-state <path>` set, after `research()` returns, serialize
   `result.state` (the `ResearchState` instance) as JSONL:
   - Line 1: `{"kind": "header", "query": ..., "timestamp_start": ..., "schema_version": "ar-4"}`
   - Line 2: `{"kind": "stage", "stage": "web_baseline", ...asdict(state.web_baseline)}`
   - Lines 3-6: same for retrieved / reasoned / verified / synthesized
3. `print(markdown)` to stdout as today (unchanged).

**Implementation** (helper inside `__main__.py`, NOT inside `lib/research/`
package proper — keeps the package pure async):

```python
def _write_dump_state(state: ResearchState, path: Path) -> None:
    """JSONL dump of ResearchState. One header line + one line per stage.
    Path I/O is __main__-only; lib/research/ stays pure."""
    from dataclasses import asdict
    import json
    def default(obj):
        if isinstance(obj, Path):
            return str(obj)
        return str(obj)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "header", "query": state.query,
                            "timestamp_start": state.timestamp_start,
                            "schema_version": "ar-4"}, default=default) + "\n")
        for stage_name in ("web_baseline", "retrieved", "reasoned", "verified", "synthesized"):
            stage_obj = getattr(state, stage_name, None)
            if stage_obj is not None:
                f.write(json.dumps({"kind": "stage", "stage": stage_name,
                                    **asdict(stage_obj)}, default=default) + "\n")
```

**`_amain` LOC budget**: post-ar-4 must remain ≤ 18 LOC. ar-2-03 left it at
15 LOC; ar-4 adds `if ns.dump_state is not None: _write_dump_state(...)` — 2
LOC body, total 17 LOC. The serializer body lives in the helper, not in `_amain`.

**Distinction from telemetry JSONL**: `--dump-state` writes the **final state**
post-pipeline (one shot, full `ResearchState`). Telemetry JSONL writes
**incremental events** during the pipeline (start / per-stage / end).
Different files, different schemas, different consumers.

### TEST-05: Milestone smoke (Wave 2)

**Query**: `"Hermes Harness 深度解析"` — the canonical Chinese-language
deep-dive query established by the design doc.

**Pass conditions** (ALL 5 must hold):

| # | Condition | Verification method |
|---|---|---|
| (a) | Markdown contains ≥ 3 inline `![desc](http://localhost:8765/...)` images | Regex count: `re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", markdown)` ≥ 3 |
| (b) | `state.verified.confidence >= 60` | Read from `result.state.verified.confidence` |
| (c) | Total wall time ≤ 120 s | `time.time() - state.timestamp_start <= 120.0` |
| (d) | No stage with `status="failed"` in JSONL telemetry | Parse `<telemetry_jsonl>`, ensure all `stage_end` events have `status` ∈ {ok, skipped, None for synthesizer} |
| (e) | Answer language is Chinese | Heuristic: ≥ 50% of non-image, non-URL characters in markdown are CJK (`一-鿿`); reuse logic from existing language detector if any, else a small inline check |

**Smoke driver** (NEW script, `scripts/smoke_milestone.py`, NOT inside
`lib/research/`):

```python
# scripts/smoke_milestone.py
import asyncio, json, re, sys, time
from pathlib import Path
from omnigraph.research import research, from_env
import dataclasses

QUERY = "Hermes Harness 深度解析"

async def main():
    telemetry_path = Path(".scratch") / f"smoke-telemetry-{int(time.time())}.jsonl"
    telemetry_path.parent.mkdir(exist_ok=True)
    cfg = dataclasses.replace(from_env(), telemetry_jsonl=telemetry_path)
    t0 = time.time()
    result = await research(QUERY, cfg)
    elapsed = time.time() - t0

    # condition (a)
    image_count = len(re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", result.markdown))
    # condition (b)
    confidence = result.state.verified.confidence if result.state.verified else 0.0
    # condition (c)
    # elapsed already measured
    # condition (d)
    failed_stages = []
    for line in telemetry_path.read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("event_type") == "stage_end" and ev.get("status") == "failed":
            failed_stages.append(ev["stage"])
    # condition (e)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)|https?://\S+", "", result.markdown)
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    non_ws = sum(1 for c in text if not c.isspace())
    cjk_ratio = cjk / max(non_ws, 1)

    verdict = {
        "a_image_count": image_count, "a_pass": image_count >= 3,
        "b_confidence": confidence, "b_pass": confidence >= 60.0,
        "c_elapsed_s": elapsed, "c_pass": elapsed <= 120.0,
        "d_failed_stages": failed_stages, "d_pass": len(failed_stages) == 0,
        "e_cjk_ratio": cjk_ratio, "e_pass": cjk_ratio >= 0.5,
    }
    all_pass = all(v for k, v in verdict.items() if k.endswith("_pass"))
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    asyncio.run(main())
```

**Live-key requirement**: TEST-05 runs against the LIVE pipeline — Tavily +
Brave + (optionally) Vertex Grounding live keys must be present in
`~/.hermes/.env` on the smoke target. The smoke MUST run on a Hermes
deployment, NOT the local-dev workstation, because:

1. The local-dev KG has the 3072/768 embedding dim mismatch (pre-existing
   v1.0.y operator-side issue) which causes `Retriever status="failed"`.
2. `BASE_IMAGE_DIR` and the local image HTTP server (port 8765) are populated
   on Hermes from real ingested articles, NOT on the dev workstation.
3. Wallclock ≤ 120 s requires real concurrency from the Hermes box's network
   path, not corp-network-blocked local Tavily/Brave calls.

**Failure handling**: if ANY condition fails on first run, ar-4 is allowed
to iterate **inside** ar-4 (regression patches to ar-2/ar-3 stages permitted
per ROADMAP § Cross-phase touches). The phase is NOT complete until all 5
conditions pass simultaneously in one smoke run.

### TEST-06: Manual side-by-side audit (Wave 2, milestone-close gate)

**Reference**: `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`
(259 KB — confirmed exists). This file contains the Telegram session that
served as the design doc's golden ground truth — the "what answer would a
deep-dive really look like" yardstick.

**Audit dimensions** (5, scored 1–5; ≥ 3 on EACH required):

| # | Dimension | What "≥ 3" looks like |
|---|---|---|
| 1 | Coverage breadth | The agentic-RAG output mentions at least 60% of the distinct topics (architecture pieces, design choices, examples) the Telegram answer mentions |
| 2 | Technical depth | For at least 3 topics, the agentic-RAG answer goes beyond surface-level — names internal modules, cites specific files / classes / data shapes, or describes interaction logic |
| 3 | Philosophical framing | The answer captures the "why" behind Hermes Harness's design choices, not just the "what" — at least one paragraph or section discusses motivation or trade-offs |
| 4 | Source attribution | Inline citations or a sources section maps claims to KG chunks (kg_chunk URIs) and/or external URLs (Tavily/Brave/grounding) — readers can verify ≥ 50% of factual claims |
| 5 | Image relevance | The ≥ 3 embedded images are anchored to captions describing the system being explained — not generic placeholder images. At least 2 of 3 images add visible information to the answer |

**Audit document**: `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (NEW, ar-4
deliverable). Contains:

- Header with date, smoke-run command, telemetry JSONL path, dump-state JSONL path
- Verbatim quote of the agentic-RAG markdown output (or a `cat` reference)
- Verbatim quote of relevant excerpts from the Telegram session JSON
- Per-dimension table: dimension name, score 1–5, narrative justification (2-4 sentences)
- Final verdict: PASS / FAIL based on minimum-score-≥-3 rule
- Operator signoff line (date + agent identifier)

**Audit reviewer**: the audit is performed by the orchestrator (Claude Code
session). User reviews the audit doc before milestone is declared closed.
"Manual" here means "not automated in pytest" — the orchestrator IS the
human-stand-in agent.

**Failure handling**: if any dimension scores < 3, the audit is marked
INCOMPLETE; specific deficits drive a follow-on iteration (prompt tweaks
to Synthesizer or Reasoner; possibly new web tool prompts to lift
attribution). Audit can be re-run within ar-4. Milestone close is gated on
PASS verdict.

## Configuration

`ResearchConfig.from_env()` reads no NEW env vars in ar-4. The single relevant
env var is already documented since ar-1:

| Env var | Required | Default | ar-4 effect |
|---|---|---|---|
| `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` | No | None | When set, `cfg.telemetry_jsonl = Path(value)`; both `research()` and `research_stream()` append events to this file |
| `TAVILY_API_KEY` | (TEST-05 live-smoke gate) | unset → smoke uses degraded path | Wave 2 smoke MUST have this set on the Hermes target |
| `BRAVE_SEARCH_API_KEY` | (TEST-05 live-smoke gate) | unset → no fallback | Wave 2 smoke SHOULD have this set; Hermes target must populate before smoke |
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | If `vertex_gemini`, smoke exercises Vertex Grounding path; otherwise pure Tavily/Brave |
| `OMNIGRAPH_BASE_DIR` | No | `~/.hermes/omonigraph-vault` (typo `omonigraph` is canonical — DO NOT fix) | Unchanged from ar-1/2/3 |

**No new env vars introduced.** Telemetry sink path env var was declared in
ar-1; ar-4 honors it for the first time.

> **Operator note (carry into every ar-4 PLAN.md):**
> ar-4 Wave 2 TEST-05 milestone-close smoke requires the following env vars
> populated in `~/.hermes/.env` on the Hermes deployment target before the
> smoke can be run:
>
> - `TAVILY_API_KEY` (mandatory — primary web-search path)
> - `BRAVE_SEARCH_API_KEY` (mandatory — fallback web-search path)
> - Vertex Gemini credentials (`GOOGLE_APPLICATION_CREDENTIALS` SA JSON path,
>   `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`) IF the smoke is
>   run with `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` to exercise the Grounding
>   path. If LLM provider is DeepSeek, Vertex creds are optional.
>
> Wave 1 unit tests use mocks and tmp paths — NO live keys required for Wave 1.
> The live-key TEST-05 smoke is the milestone-close gate, run on Hermes after
> Wave 1 lands and Wave 2 driver script is in place.

## CONTRACT enforcement (carried forward — re-check at ar-4 acceptance)

CONTRACT-01 and CONTRACT-02 were enforced in ar-1 and re-verified in ar-2
and ar-3. ar-4 must NOT introduce any new import or hardcoded path that
breaks them.

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

ar-4 risk surface: NEW file `lib/research/telemetry.py` MUST import zero
`omnigraph_search` symbols (it does not need any KG access — it's pure
JSON serialization).

### CONTRACT-02: no hardcoded `~/.hermes` / `omonigraph-vault` paths

```bash
grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary"
# expected: 0 hits
```

ar-4 risk surface: telemetry sink path comes from `cfg.telemetry_jsonl`
(injected via `from_env()`); dump-state path comes from CLI argv. NEITHER
hardcodes any filesystem literal. The smoke driver script `scripts/smoke_milestone.py`
lives OUTSIDE `lib/research/` and is NOT subject to CONTRACT-02 (the contract
applies to library code only).

### Cross-milestone contract: `omnigraph_search.query.search` is read-only

ar-4 introduces zero new touchpoints to the KG side. Telemetry + dump-state
+ smoke all observe state shaped by ar-1..ar-3 stages; they do not query KG.

## Smoke test for ar-4

Three layers, all must pass before phase is marked complete. Layer 2 uses the
NEW `--dump-state` flag as part of its assertions. Layer 2b is the milestone
gate (TEST-05) and runs on Hermes only.

### Layer 1 — pytest

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v
# expected: all green modulo the 1 known flake
#   - all 113 ar-3 tests still pass (regression guard)
#   - new tests for telemetry.py event-builder + sink writer (Wave 1)
#   - new tests for research_stream body emission (Wave 1)
#   - new tests for --dump-state CLI flag (Wave 1)
#   - new tests for stage-emit-sequence equivalence: research() and
#     research_stream() emit the same events in the same order (Wave 1)
# Target ≥123 green (113 baseline + ≥10 new across Wave 1)
# Known flake: tests/unit/research/test_main_cli_flags.py::test_subprocess_smoke_with_max_iter_zero
#  — passes in isolation; occasional failure under full suite due to
#    sub-process spawn / env state pollution. NOT introduced by ar-4. Tolerated.
```

### Layer 2a — cap=0 LLM-free CLI smoke (mandatory, no keys required)

```bash
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 0 \
  --max-iter-verifier 0 \
  --no-grounding \
  --dump-state .scratch/ar-4-l2a-dumpstate.jsonl \
  "什么是 Hermes Harness 深度解析"
# expected:
#  - exit code 0
#  - stdout: non-empty markdown (>= 100 chars; lower bar than ar-3 because cap=0
#    is a structural smoke, not a content smoke)
#  - .scratch/ar-4-l2a-dumpstate.jsonl exists, has >= 2 lines (header + at least
#    1 stage); is valid JSONL
#  - if OMNIGRAPH_RESEARCH_TELEMETRY_JSONL is set in env, that file also exists
#    with at least pipeline_start + per-stage events + pipeline_end
#  - no stage raises; ResearchState dataclass populates all 5 stage fields
```

### Layer 2b — milestone-close smoke (TEST-05, runs on Hermes only)

```bash
# On Hermes target, with TAVILY_API_KEY + BRAVE_SEARCH_API_KEY in ~/.hermes/.env:
python scripts/smoke_milestone.py
# expected:
#  - exit code 0
#  - JSON verdict on stdout with all 5 *_pass = true
#  - telemetry JSONL written to .scratch/smoke-telemetry-<ts>.jsonl
#  - markdown saved to ~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md
```

This is the milestone-close gate. Failure on any condition opens a remediation
sub-cycle within ar-4.

### Layer 3 — skill_runner

```bash
venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
  --test-file tests/skills/test_omnigraph_research.json
# expected: exit code 0
#  - reuses the existing test JSON from ar-1/ar-2/ar-3
#  - if ar-4 alters stdout structure for any test case, the JSON is updated in
#    the same plan that introduces the structural change
```

## Out of Scope for ar-4 (deferred / post-milestone)

| Item | Phase / track | Notes |
|---|---|---|
| LightRAG 1.5+ upgrade spike | post-milestone independent task | Not in ar-4 main line per user directive 2026-05-23 |
| Local KG embedding dim mismatch fix | v1.0.y operator-side KG re-ingest | Not an agentic-RAG-v1 deliverable |
| HTTP endpoint pre-build (HTTP-01..03) | post-milestone | Future requirement; `research_stream()` body lands in ar-4 to make HTTP-readiness possible later |
| Telemetry retention / rotation policy | post-milestone or v1.1 | ar-4 just appends; no rotation, no compression |
| Per-tool-call telemetry events | post-milestone | ar-4 emits stage-level events; per-tool-call events are nice-to-have but not gate-blocking |
| Synthesizer prompt-engineering deep tuning | post-milestone or in-flight | ar-4 IS allowed to iterate the Synthesizer prompt to satisfy TEST-05 conditions, but only to the minimum extent needed to flip a failing condition to passing |
| Pre-commit infra for CONTRACT-01 grep | post-milestone or v1.1 | Documented checklist remains the enforcement vehicle |

## Wave decomposition (orchestrator-confirmed 2026-05-23)

ar-4 is split into 2 strictly sequential waves (no in-phase parallelism).
Implementation-then-gate: build the observability surfaces → run the milestone
gates that depend on them.

- **Wave 1 (ar-4-01) — telemetry + dump-state**: LIB-08 (telemetry.py module +
  research_stream() body + research() refactor to share the sink) + CLI-02
  (--dump-state flag and helper). These two REQs are tightly coupled because
  they share the JSONL serialization layer — separating them creates duplicate
  serializers. Files:
  `lib/research/telemetry.py` (NEW),
  `lib/research/orchestrator.py` (rewrite — fill research_stream body, refactor
   research() to share emit sequence),
  `lib/research/__main__.py` (add --dump-state flag + _write_dump_state helper;
   _amain stays ≤ 18 LOC),
  `tests/unit/research/test_telemetry.py` (NEW — event builder + sink writer),
  `tests/unit/research/test_research_stream.py` (NEW — async iterator emits
   stage events in correct order; sink-disabled vs sink-enabled both work),
  `tests/unit/research/test_dump_state.py` (NEW — --dump-state writes valid
   JSONL; header + 1-5 stage lines; serializer handles Path / dataclass).
- **Wave 2 (ar-4-02) — milestone smoke + audit**: TEST-05 (driver script +
  5 pass conditions) + TEST-06 (manual audit doc + verdict). Mostly observation
  + minimal driver code; allows regression patches to ar-2/ar-3 stages if any
  of the 5 smoke conditions fails on first run. Files:
  `scripts/smoke_milestone.py` (NEW),
  `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (NEW — created during the audit),
  any minimal touch to `lib/research/stages/synthesizer.py` IF prompt iteration
  needed for condition (a) ≥3 images or (e) Chinese language (cross-phase touch
  per ROADMAP).

## Related artifacts

- `.planning/PROJECT-Agentic-RAG-v1.md` — milestone charter
- `.planning/REQUIREMENTS-Agentic-RAG-v1.md` — full 41-REQ list with ar-4 mapping
- `.planning/ROADMAP-Agentic-RAG-v1.md` — 4-phase decomposition + cross-phase touches
- `docs/design/agentic_rag_internal_api.md` — locked design doc
- `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json` — TEST-06 ground truth
- `lib/research/orchestrator.py` — current research_stream stub (Wave 1 fills body)
- `lib/research/__main__.py` — current 15-LOC _amain (Wave 1 grows to ≤ 18 LOC)
- `lib/research/types.py` — LOCKED, NOT modified in ar-4
- `lib/research/stages/*.py` — LOCKED for telemetry plumbing; allowed touch in Wave 2 only if smoke fails a condition (cross-phase touch)
- `.planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md` — template precedent for this CONTEXT
