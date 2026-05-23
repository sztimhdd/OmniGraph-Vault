---
phase: ar-4-telemetry-streaming-smoke
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/research/telemetry.py
  - lib/research/orchestrator.py
  - lib/research/__main__.py
  - tests/unit/research/test_telemetry.py
  - tests/unit/research/test_research_stream.py
  - tests/unit/research/test_dump_state.py
autonomous: true
status: planned
last_updated: "2026-05-23"
requirements:
  - LIB-08
  - CLI-02

must_haves:
  truths:
    - "lib/research/telemetry.py exposes 4 event-type constants: EVENT_PIPELINE_START='pipeline_start', EVENT_STAGE_START='stage_start', EVENT_STAGE_END='stage_end', EVENT_PIPELINE_END='pipeline_end' (LIB-08)"
    - "make_event(event_type: str, stage: str, **payload) -> dict returns a dict carrying at minimum {event_type, stage, ts: float}; extra payload keys are merged in; ts is time.time() at construction (LIB-08)"
    - "write_event(sink_path: Path | None, event: dict) -> None appends one JSON line to sink_path when non-None and is a no-op when None; OSError raised by the file open/write is swallowed (best-effort observability — Axis 3) (LIB-08)"
    - "write_event uses a JSON default fallback that converts Path -> str and dataclass instances -> asdict(); other unserializable values fall through to str() (LIB-08)"
    - "research_stream(query, config) is an async iterator that yields one EVENT_PIPELINE_START, then for each of the 5 stages a (stage_start, stage_end) pair in strict pipeline order (web_baseline -> retriever -> reasoner -> verifier -> synthesizer), then EVENT_PIPELINE_END (LIB-08)"
    - "research() and research_stream() share ONE source-of-truth emission sequence; no duplicated stage-emit logic between the two surfaces (LIB-08)"
    - "research() returns ResearchResult with the same final state research_stream() would produce; both surfaces honour cfg.telemetry_jsonl identically — sink-disabled (None) does no file I/O, sink-enabled writes the same events the iterator yields (LIB-08, Axis 4)"
    - "stage_end events carry status (ok|skipped|failed) for non-terminal stages; the synthesizer stage_end omits status (terminal-stage rule, Axis 8) and instead carries note_line_count (LIB-08)"
    - "stage_end events carry stage-specific payload counts: snippet_count (web_baseline), chunk_count + image_candidate_count (retriever), iter_count + image_analyzed_count (reasoner), iter_count + confidence + external_citation_count (verifier), embedded_image_count + note_line_count + confidence (synthesizer) (LIB-08)"
    - "lib/research/__main__.py grows _amain by exactly one if-branch (≤ 3 net LOC); post-ar-4 _amain body is ≤ 18 LOC (cap from ar-2-03 carried forward) (CLI-02)"
    - "--dump-state <path> CLI flag is additive: when set, it triggers _write_dump_state(result.state, path) AFTER research() returns; print(markdown) to stdout still happens unchanged (CLI-02)"
    - "_write_dump_state(state: ResearchState, path: Path) -> None writes a header line + one line per non-None stage (web_baseline, retrieved, reasoned, verified, synthesized) as JSONL; header carries {kind:'header', query, timestamp_start, schema_version:'ar-4'}; each stage line carries {kind:'stage', stage:<name>, **asdict(stage_obj)} (CLI-02)"
    - "_write_dump_state lives in __main__.py (not lib/research/ proper) so the lib/research/ package retains pure-async no-CLI-side-effect Axis 1 cleanliness (CLI-02, Axis 1)"
    - "tests/unit/research/test_telemetry.py adds ≥ 4 mock-based tests: event-builder shape; sink None no-op; sink writes valid JSONL; sink swallows OSError on disk-write failure (LIB-08)"
    - "tests/unit/research/test_research_stream.py adds ≥ 4 tests: emits PIPELINE_START first; emits 5 stage_start/stage_end pairs in pipeline order; emits PIPELINE_END last; sink-disabled vs sink-enabled both emit the same iterator events (LIB-08)"
    - "tests/unit/research/test_dump_state.py adds ≥ 4 tests: helper writes header + ≤ 5 stage lines; header has schema_version='ar-4'; Path values serialize as strings; missing stages skipped silently; subprocess CLI smoke with --dump-state validates exit 0 + file exists + valid JSONL (CLI-02)"
    - "Layer 1 pytest target post-Wave-1 is ≥ 123 green (113 ar-3 baseline + ≥ 10 new ar-4 W1 tests); the 1 known flake test_main_cli_flags::test_subprocess_smoke_with_max_iter_zero is tolerated (passes in isolation; intermittent under full suite — pre-existing, NOT introduced by ar-4)"
    - "Layer 2a cap=0 LLM-free CLI smoke with --dump-state .scratch/ar-4-l2a-dumpstate.jsonl exits 0 + the dump-state file exists with header + ≥ 1 stage line + valid JSONL"
  artifacts:
    - path: "lib/research/telemetry.py"
      provides: "Event builder + sink writer module — single source of JSONL serialization for both research() and research_stream()"
      contains: "Event-type constants (EVENT_PIPELINE_START / EVENT_STAGE_START / EVENT_STAGE_END / EVENT_PIPELINE_END), make_event(event_type, stage, **payload) -> dict, write_event(sink_path, event) -> None, _json_default(obj) -> Any helper"
    - path: "lib/research/orchestrator.py"
      provides: "research() and research_stream() share ONE pipeline-emit sequence — research_stream() body filled (replaces NotImplementedError('ar-4'))"
      contains: "research_stream() async iterator yielding pipeline_start + 5 stage pairs + pipeline_end; research() refactored to consume the same emission sequence and build ResearchResult from the final state; both honour cfg.telemetry_jsonl"
    - path: "lib/research/__main__.py"
      provides: "CLI entrypoint extended with --dump-state <path> flag; _amain body remains ≤ 18 LOC; _write_dump_state helper at module scope"
      contains: "argparse argument --dump-state (type=lambda s: Path(s), default=None); _write_dump_state(state, path) helper writing JSONL header + per-stage lines; _amain calls helper after research() returns when ns.dump_state is non-None"
    - path: "tests/unit/research/test_telemetry.py"
      provides: "Mock-based unit tests for the event builder + sink writer (≥ 4 tests)"
      contains: "test_make_event_carries_event_type_stage_ts, test_make_event_merges_payload, test_write_event_none_sink_is_noop, test_write_event_writes_valid_jsonl, test_write_event_swallows_oserror"
    - path: "tests/unit/research/test_research_stream.py"
      provides: "Async-iterator behavior tests for research_stream + research/research_stream emission equivalence (≥ 4 tests)"
      contains: "test_research_stream_yields_pipeline_start_first, test_research_stream_yields_5_stage_pairs_in_order, test_research_stream_yields_pipeline_end_last, test_research_stream_sink_none_no_file_io, test_research_stream_sink_set_writes_valid_jsonl_matching_iterator_events"
    - path: "tests/unit/research/test_dump_state.py"
      provides: "JSONL dump-state serializer tests + subprocess CLI smoke (≥ 4 tests)"
      contains: "test_write_dump_state_writes_header_plus_stages, test_write_dump_state_header_has_schema_version_ar4, test_write_dump_state_serializes_path_as_str, test_write_dump_state_skips_missing_stages, test_subprocess_cli_smoke_with_dump_state"
  key_links:
    - from: "lib/research/orchestrator.py"
      to: "lib/research/telemetry.py"
      via: "from .telemetry import make_event, write_event, EVENT_PIPELINE_START, EVENT_STAGE_START, EVENT_STAGE_END, EVENT_PIPELINE_END"
      pattern: "from \\.telemetry import"
    - from: "lib/research/__main__.py"
      to: "lib/research/orchestrator.py"
      via: "from .orchestrator import research (existing import — unchanged)"
      pattern: "from \\.orchestrator import research"
    - from: "lib/research/__main__.py"
      to: "lib/research/types.py"
      via: "_write_dump_state consumes ResearchState fields via dataclasses.asdict — no new types.py touches"
      pattern: "asdict\\("
    - from: "lib/research/orchestrator.py"
      to: "cfg.telemetry_jsonl"
      via: "research() and research_stream() pass cfg.telemetry_jsonl into write_event() at every emission site"
      pattern: "telemetry_jsonl"
    - from: "tests/unit/research/test_research_stream.py"
      to: "lib/research/orchestrator.py"
      via: "import via package: `from omnigraph.research.orchestrator import research, research_stream`"
      pattern: "from omnigraph\\.research\\.orchestrator import"
---

<objective>
Wave 1 of ar-4 wires the **observability surfaces** that close out Agentic-RAG-v1's API contract: the streaming peer (`research_stream`) gets a real body, the telemetry sink (`cfg.telemetry_jsonl`) is honored for the first time since ar-1, and the CLI gets a `--dump-state <path>` flag for offline ResearchState inspection. All three pieces share one JSONL serialization layer in a new `lib/research/telemetry.py` module — no duplicate serializers, no skew between `research()` and `research_stream()`.

Purpose:
- **LIB-08** — `research_stream(query, config) -> AsyncIterator[dict]` body lands. The streaming peer rule (Axis 5) becomes real, not just a signature stub. Telemetry events flow through the iterator AND optionally append to `cfg.telemetry_jsonl` when configured (Axis 4 opt-in side effect). `research()` is refactored so both surfaces share the same emit sequence.
- **CLI-02** — `--dump-state <path>` CLI flag dumps the final `ResearchState` as JSONL (one header line + one line per non-None stage). The flag is additive: stdout markdown is preserved unchanged. The serializer helper `_write_dump_state` lives in `__main__.py` so `lib/research/` retains its pure-async no-CLI-side-effects character.

Output:
- One new module: `lib/research/telemetry.py` (~80-120 LOC: event-type constants + 2 functions + 1 helper).
- One new file: `lib/research/__main__.py` gains an argparse argument + a 10-15 LOC helper; `_amain` body grows by exactly one if-branch (≤ 18 LOC cap preserved).
- One file rewritten: `lib/research/orchestrator.py` — `research_stream()` body filled; `research()` refactored to consume the same emission generator.
- Three new test files: `test_telemetry.py`, `test_research_stream.py`, `test_dump_state.py` (≥ 10 tests across the three).
- ar-1 + ar-2 + ar-3 regression suite still green; full `tests/unit/research/` count after Wave 1 ≥ 113 baseline + ≥ 10 new = ≥ 123, modulo the 1 known pre-existing flake.

This plan does NOT touch the 5 stage modules, the dataclasses, or the web tools. It does NOT add new env vars (`OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` was declared in ar-1 and read by `from_env()` already — Wave 1 just makes the path actually flow into the new sink writer). It does NOT run the milestone smoke (TEST-05) or audit (TEST-06) — those are Wave 2 (ar-4-02).

The new `lib/research/telemetry.py` module imports zero `omnigraph_search` symbols and contains zero hardcoded `~/.hermes` / `omonigraph-vault` literals — CONTRACT-01 + CONTRACT-02 clean.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-CONTEXT.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/ROADMAP-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/orchestrator.py
@lib/research/__main__.py
@scripts/check_contract.sh

<interfaces>
**`ResearchConfig` dataclass slots (from `lib/research/types.py`, UNCHANGED across ar-N):**

```python
@dataclass(frozen=True)
class ResearchConfig:
    rag_working_dir: Path
    llm_complete: Callable
    embedding_func: Callable
    vision_cascade: object
    web_search: Callable[[str], list[dict]]
    web_search_fallback: Callable[[str], list[dict]] | None = None
    web_extract: Callable[[str], str] | None = None
    google_search_grounding: Callable | None = None
    output_dir: Path | None = None
    telemetry_jsonl: Path | None = None    # ar-4 Wave 1 honors this for the first time
    max_iter_reasoner: int = 5
    max_iter_verifier: int = 3
```

**`ResearchState` dataclass slots (from `lib/research/types.py`, UNCHANGED):**

```python
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

**Event-type constants (NEW, in `lib/research/telemetry.py`):**

```python
EVENT_PIPELINE_START = "pipeline_start"
EVENT_STAGE_START = "stage_start"
EVENT_STAGE_END = "stage_end"
EVENT_PIPELINE_END = "pipeline_end"
```

**Telemetry module surface (NEW):**

```python
def make_event(event_type: str, stage: str, **payload: Any) -> dict:
    """Build a wire-format event dict. Always carries event_type, stage, ts.
    Extra payload merged in. ts = time.time() at call time."""

def write_event(sink_path: Path | None, event: dict) -> None:
    """Append one JSON line to sink_path when non-None; no-op when None.
    Uses _json_default fallback for non-trivial types. Swallows OSError
    (sink failure must not poison the pipeline — Axis 3 best-effort)."""

def _json_default(obj: Any) -> Any:
    """JSON encoder fallback: Path -> str; dataclass -> asdict(); other -> str()."""
```

**Streaming peer signature (existing in ar-1 stub form; body filled in ar-4 W1):**

```python
async def research_stream(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of research(). Yields per-stage events.
    Pipeline order: web_baseline -> retriever -> reasoner -> verifier -> synthesizer.
    When cfg.telemetry_jsonl is non-None, each event is also appended via write_event."""
```

**Stage-end payload shape** (one per stage; `status` omitted for synthesizer per Axis 8):

```python
# web_baseline stage_end
{event_type:"stage_end", stage:"web_baseline", ts, status, reason, duration_s, snippet_count}
# retriever stage_end
{event_type:"stage_end", stage:"retriever", ts, status, reason, duration_s, chunk_count, image_candidate_count}
# reasoner stage_end
{event_type:"stage_end", stage:"reasoner", ts, status, reason, duration_s, iter_count, image_analyzed_count}
# verifier stage_end
{event_type:"stage_end", stage:"verifier", ts, status, reason, duration_s, iter_count, confidence, external_citation_count}
# synthesizer stage_end (NO status — terminal stage, Axis 8)
{event_type:"stage_end", stage:"synthesizer", ts, duration_s, embedded_image_count, note_line_count, confidence}
```

**`--dump-state <path>` CLI flag (NEW, in `lib/research/__main__.py`):**

```python
parser.add_argument(
    "--dump-state",
    type=lambda s: Path(s),
    default=None,
    help="Optional path. When set, writes the final ResearchState as JSONL "
         "(header line + one line per stage). Stdout markdown is unchanged.",
)
```

**`_write_dump_state` helper (NEW, in `lib/research/__main__.py`):**

```python
def _write_dump_state(state: ResearchState, path: Path) -> None:
    """JSONL dump of ResearchState. One header line + one line per non-None stage.
    Schema version 'ar-4'. Path I/O is __main__-only; lib/research/ stays pure."""
```

**Dump-state JSONL schema:**

```json
{"kind":"header", "query":"<str>", "timestamp_start":<float>, "schema_version":"ar-4"}
{"kind":"stage", "stage":"web_baseline", "queries_used":[...], "snippets":[...], "status":"ok", "reason":null}
{"kind":"stage", "stage":"retrieved", "chunks":[...], "image_candidates":[...], "status":"ok", "reason":null}
{"kind":"stage", "stage":"reasoned", "inferences_md":"...", "additional_chunks":[...], "analyzed_images":[...], "iter_count":<int>, "status":"ok", "reason":null}
{"kind":"stage", "stage":"verified", "fact_check_summary_md":"...", "confidence":<float>, "external_citations":[...], "discrepancies":[...], "iter_count":<int>, "status":"ok", "reason":null}
{"kind":"stage", "stage":"synthesized", "markdown":"...", "confidence":<float>, "sources":[...], "embedded_images":[...], "note_lines":[...]}
```

**Existing `_amain` body (15 LOC post-ar-2-03; budget = 3 net LOC for Wave 1):**

```python
async def _amain(ns: argparse.Namespace) -> str:
    cfg = from_env()
    overrides: dict = {}
    if ns.max_iter_reasoner is not None:
        overrides["max_iter_reasoner"] = ns.max_iter_reasoner
    if ns.max_iter_verifier is not None:
        overrides["max_iter_verifier"] = ns.max_iter_verifier
    if ns.no_grounding:
        overrides["google_search_grounding"] = None
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)
    base_image_dir = cfg.rag_working_dir.parent / "images"
    if base_image_dir.is_dir():
        ensure_image_server(base_image_dir)
    result = await research(ns.query, cfg)
    if ns.dump_state is not None:
        _write_dump_state(result.state, ns.dump_state)
    return result.markdown
```

Post-Wave-1 _amain: 17 LOC (15 + 2 net for the dump-state branch). Cap is 18; one LOC of headroom remains.

</interfaces>
</context>

## Files

| Path | NEW or MODIFY | LOC est. | Notes |
|---|---|---|---|
| `lib/research/telemetry.py` | NEW | ~80-120 | Event constants + make_event + write_event + _json_default |
| `lib/research/orchestrator.py` | MODIFY (rewrite research_stream body; refactor research) | +60 / -10 | Single emission generator shared by both surfaces |
| `lib/research/__main__.py` | MODIFY | +18 | Add argparse arg + helper; _amain grows by 2 LOC (15 → 17) |
| `tests/unit/research/test_telemetry.py` | NEW | ~80-100 | ≥ 4 mock-based tests for builder + sink |
| `tests/unit/research/test_research_stream.py` | NEW | ~120-180 | ≥ 4 async-iterator emission-order tests |
| `tests/unit/research/test_dump_state.py` | NEW | ~100-140 | ≥ 4 helper tests + 1 subprocess CLI smoke |

## Implementation steps

### Step 1 — Author `lib/research/telemetry.py`

Module skeleton:

```python
"""ar-4 telemetry sink — single source of JSONL serialization.

Used by both research() and research_stream() (LIB-08). Pure observability:
sink failures are swallowed (Axis 3). No external network calls; no LLM access.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

EVENT_PIPELINE_START = "pipeline_start"
EVENT_STAGE_START = "stage_start"
EVENT_STAGE_END = "stage_end"
EVENT_PIPELINE_END = "pipeline_end"


def make_event(event_type: str, stage: str, **payload: Any) -> dict:
    """Build a wire-format event dict. Carries event_type, stage, ts (float).
    Extra payload merged in (must be JSON-serializable via _json_default)."""
    return {"event_type": event_type, "stage": stage, "ts": time.time(), **payload}


def write_event(sink_path: Path | None, event: dict) -> None:
    """Append one JSON line to sink_path if non-None. Swallow OSError —
    observability must not poison the pipeline (Axis 3 best-effort)."""
    if sink_path is None:
        return
    try:
        with sink_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=_json_default) + "\n")
    except OSError:
        pass


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback: Path -> str, dataclass -> asdict(), else str()."""
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return str(obj)
```

CONTRACT-01 verification: zero `from omnigraph_search` imports. CONTRACT-02 verification: zero `~/.hermes` / `omonigraph-vault` literals.

### Step 2 — Author `tests/unit/research/test_telemetry.py`

Required tests (≥ 4):

```python
# test_make_event_carries_event_type_stage_ts
def test_make_event_carries_event_type_stage_ts():
    ev = make_event(EVENT_PIPELINE_START, "pipeline")
    assert ev["event_type"] == "pipeline_start"
    assert ev["stage"] == "pipeline"
    assert isinstance(ev["ts"], float) and ev["ts"] > 0

# test_make_event_merges_payload
def test_make_event_merges_payload():
    ev = make_event(EVENT_STAGE_END, "verifier", iter_count=2, confidence=75.0)
    assert ev["iter_count"] == 2 and ev["confidence"] == 75.0

# test_write_event_none_sink_is_noop  (no exception, no file created)
def test_write_event_none_sink_is_noop(tmp_path):
    write_event(None, {"event_type": "x", "stage": "y", "ts": 0.0})
    assert list(tmp_path.iterdir()) == []

# test_write_event_writes_valid_jsonl
def test_write_event_writes_valid_jsonl(tmp_path):
    p = tmp_path / "tel.jsonl"
    write_event(p, {"event_type": "stage_end", "stage": "reasoner", "ts": 1.5, "iter_count": 3})
    line = p.read_text(encoding="utf-8").strip()
    assert json.loads(line) == {"event_type": "stage_end", "stage": "reasoner", "ts": 1.5, "iter_count": 3}

# test_write_event_swallows_oserror  (use a directory-as-path to force OSError)
def test_write_event_swallows_oserror(tmp_path):
    bad = tmp_path  # path-is-a-directory triggers OSError on open(append)
    write_event(bad, {"event_type": "x", "stage": "y", "ts": 0.0})
    # If we got here without raising, swallow worked.

# test_json_default_handles_path_and_dataclass
def test_json_default_handles_path_and_dataclass(tmp_path):
    from lib.research.types import Source
    s = Source(kind="kg_chunk", uri="file://x", title="t", snippet="s")
    p = tmp_path / "tel.jsonl"
    write_event(p, {"event_type": "x", "stage": "y", "ts": 0.0, "source": s, "path": tmp_path})
    parsed = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(parsed["source"], dict) and parsed["source"]["kind"] == "kg_chunk"
    assert isinstance(parsed["path"], str)
```

### Step 3 — Refactor `lib/research/orchestrator.py`

**Decision: Pattern A** — extract a private async generator `_run_pipeline(query, cfg)` that runs all 5 stages and yields events. `research_stream()` returns directly from this generator. `research()` consumes the generator and pulls the final state from a closure-captured `ResearchState` instance built inside the generator.

Rationale for Pattern A over Pattern B (research_stream as master, research walks it pulling state from pipeline_end event payload):

1. State capture via closure is cleaner than embedding a full ResearchState dataclass into every pipeline_end event payload (the latter would bloat the JSONL telemetry file with a duplicate of the dump-state schema).
2. `research()` already returns ResearchResult — building it from a captured state at the end of the generator walk is idiomatic.
3. Pattern A keeps the emission generator pure (it yields events only, never state) — easier to test in isolation.

Implementation skeleton:

```python
"""Agentic-RAG-v1 orchestrator (ar-4 telemetry-wired).

Single source of stage emissions: _run_pipeline async generator.
research_stream() returns from it directly; research() walks it and builds
ResearchResult from the captured final state.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from .config import ResearchConfig, from_env
from .telemetry import (
    EVENT_PIPELINE_START, EVENT_STAGE_START, EVENT_STAGE_END, EVENT_PIPELINE_END,
    make_event, write_event,
)
from .types import ResearchResult, ResearchState


async def _run_pipeline(
    query: str, cfg: ResearchConfig, state: ResearchState
) -> AsyncIterator[dict]:
    """Master pipeline emission generator (Pattern A). Yields events only;
    populates `state` in-place as a side effect (state is mutable by design)."""
    sink = cfg.telemetry_jsonl

    # Lazy stage imports — preserves clean module load
    from .stages.web_baseline import run as run_web_baseline
    from .stages.retriever import run as run_retriever
    from .stages.reasoner import run as run_reasoner
    from .stages.verifier import run as run_verifier
    from .stages.synthesizer import run as run_synthesizer

    ev = make_event(EVENT_PIPELINE_START, "pipeline", query=query)
    write_event(sink, ev); yield ev

    # WebBaseline
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "web_baseline"); write_event(sink, ev); yield ev
    state.web_baseline = await run_web_baseline(query, cfg)
    ev = make_event(EVENT_STAGE_END, "web_baseline",
                    status=state.web_baseline.status,
                    reason=state.web_baseline.reason,
                    duration_s=time.time() - t0,
                    snippet_count=len(state.web_baseline.snippets))
    write_event(sink, ev); yield ev

    # Retriever
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "retriever"); write_event(sink, ev); yield ev
    state.retrieved = await run_retriever(query, cfg)
    ev = make_event(EVENT_STAGE_END, "retriever",
                    status=state.retrieved.status,
                    reason=state.retrieved.reason,
                    duration_s=time.time() - t0,
                    chunk_count=len(state.retrieved.chunks),
                    image_candidate_count=len(state.retrieved.image_candidates))
    write_event(sink, ev); yield ev

    # Reasoner
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "reasoner"); write_event(sink, ev); yield ev
    state.reasoned = await run_reasoner(query, cfg, state.retrieved)
    ev = make_event(EVENT_STAGE_END, "reasoner",
                    status=state.reasoned.status,
                    reason=state.reasoned.reason,
                    duration_s=time.time() - t0,
                    iter_count=state.reasoned.iter_count,
                    image_analyzed_count=len(state.reasoned.analyzed_images))
    write_event(sink, ev); yield ev

    # Verifier
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "verifier"); write_event(sink, ev); yield ev
    state.verified = await run_verifier(query, cfg, state.reasoned)
    ev = make_event(EVENT_STAGE_END, "verifier",
                    status=state.verified.status,
                    reason=state.verified.reason,
                    duration_s=time.time() - t0,
                    iter_count=state.verified.iter_count,
                    confidence=state.verified.confidence,
                    external_citation_count=len(state.verified.external_citations))
    write_event(sink, ev); yield ev

    # Synthesizer (NO status field — Axis 8 terminal-stage rule)
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "synthesizer"); write_event(sink, ev); yield ev
    state.synthesized = await run_synthesizer(query, cfg, state)
    ev = make_event(EVENT_STAGE_END, "synthesizer",
                    duration_s=time.time() - t0,
                    embedded_image_count=len(state.synthesized.embedded_images),
                    note_line_count=len(state.synthesized.note_lines),
                    confidence=state.synthesized.confidence)
    write_event(sink, ev); yield ev

    ev = make_event(EVENT_PIPELINE_END, "pipeline",
                    duration_s=time.time() - state.timestamp_start)
    write_event(sink, ev); yield ev


async def research(query: str, config: ResearchConfig | None = None) -> ResearchResult:
    """Run the 5-stage research pipeline. Strict sequential order (Axis 1)."""
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    async for _ev in _run_pipeline(query, cfg, state):
        pass  # events flow through write_event sink; state captured via closure
    return ResearchResult(
        markdown=state.synthesized.markdown,
        confidence=state.synthesized.confidence,
        sources=state.synthesized.sources,
        images_embedded=state.synthesized.embedded_images,
        state=state,
    )


async def research_stream(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of research(). Yields per-stage events (LIB-08)."""
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    async for ev in _run_pipeline(query, cfg, state):
        yield ev
```

Verification: `research()` and `research_stream()` BOTH route through `_run_pipeline()` — single source of emission ordering. Sink behavior identical between the two surfaces.

### Step 4 — Author `tests/unit/research/test_research_stream.py`

Required tests (≥ 4):

```python
import json
from pathlib import Path
import pytest
from omnigraph.research.orchestrator import research_stream, research
# Use existing fixtures from tests/unit/research/conftest.py for stub stages

@pytest.mark.asyncio
async def test_research_stream_yields_pipeline_start_first(stub_cfg):
    events = []
    async for ev in research_stream("test query", stub_cfg):
        events.append(ev)
    assert events[0]["event_type"] == "pipeline_start"
    assert events[0]["stage"] == "pipeline"
    assert events[0]["query"] == "test query"

@pytest.mark.asyncio
async def test_research_stream_yields_5_stage_pairs_in_order(stub_cfg):
    events = []
    async for ev in research_stream("q", stub_cfg):
        events.append(ev)
    expected_stages = ["web_baseline", "retriever", "reasoner", "verifier", "synthesizer"]
    stage_pairs = [(e["event_type"], e["stage"]) for e in events
                   if e["event_type"] in ("stage_start", "stage_end")]
    # Each stage in order: start then end
    for i, name in enumerate(expected_stages):
        assert stage_pairs[2*i] == ("stage_start", name)
        assert stage_pairs[2*i+1] == ("stage_end", name)

@pytest.mark.asyncio
async def test_research_stream_yields_pipeline_end_last(stub_cfg):
    events = []
    async for ev in research_stream("q", stub_cfg):
        events.append(ev)
    assert events[-1]["event_type"] == "pipeline_end"
    assert events[-1]["stage"] == "pipeline"
    assert "duration_s" in events[-1]

@pytest.mark.asyncio
async def test_research_stream_sink_none_no_file_io(stub_cfg, tmp_path):
    # stub_cfg has telemetry_jsonl=None
    cfg = stub_cfg  # explicit: no replace
    async for _ev in research_stream("q", cfg):
        pass
    # No JSONL file created anywhere under tmp_path
    assert list(tmp_path.iterdir()) == []

@pytest.mark.asyncio
async def test_research_stream_sink_set_writes_valid_jsonl_matching_iterator(stub_cfg, tmp_path):
    import dataclasses
    p = tmp_path / "tel.jsonl"
    cfg = dataclasses.replace(stub_cfg, telemetry_jsonl=p)
    iter_events = []
    async for ev in research_stream("q", cfg):
        iter_events.append(ev)
    file_lines = p.read_text(encoding="utf-8").strip().splitlines()
    file_events = [json.loads(line) for line in file_lines]
    assert len(iter_events) == len(file_events)
    # event_type+stage match by index
    for ie, fe in zip(iter_events, file_events):
        assert ie["event_type"] == fe["event_type"]
        assert ie["stage"] == fe["stage"]

@pytest.mark.asyncio
async def test_research_consumes_same_pipeline_as_stream(stub_cfg, tmp_path):
    """Both surfaces share emission ordering — file from research() and from
    research_stream() must contain the same events in the same order."""
    import dataclasses
    p_blocking = tmp_path / "blocking.jsonl"
    p_streaming = tmp_path / "streaming.jsonl"
    cfg_b = dataclasses.replace(stub_cfg, telemetry_jsonl=p_blocking)
    cfg_s = dataclasses.replace(stub_cfg, telemetry_jsonl=p_streaming)
    await research("q", cfg_b)
    async for _ev in research_stream("q", cfg_s):
        pass
    blocking = [json.loads(l)["event_type"] + ":" + json.loads(l)["stage"]
                for l in p_blocking.read_text(encoding="utf-8").strip().splitlines()]
    streaming = [json.loads(l)["event_type"] + ":" + json.loads(l)["stage"]
                 for l in p_streaming.read_text(encoding="utf-8").strip().splitlines()]
    assert blocking == streaming
```

The `stub_cfg` fixture is reused from existing `tests/unit/research/conftest.py` (provides a no-LLM, no-network ResearchConfig with stub stages). If a fresh fixture variant is needed, add it to conftest.py.

### Step 5 — Modify `lib/research/__main__.py`

```python
# imports (additions only):
from pathlib import Path
import json
from dataclasses import asdict, fields
from .types import ResearchState

# argparse argument (add inside _parse_args, after --no-grounding):
parser.add_argument(
    "--dump-state",
    type=lambda s: Path(s),
    default=None,
    help="Optional path. When set, writes the final ResearchState as JSONL "
         "(header + one line per stage). Stdout markdown is unchanged. (CLI-02)",
)

# helper at module scope (between _parse_args and _amain):
def _write_dump_state(state: "ResearchState", path: Path) -> None:
    """JSONL dump of ResearchState. Header line + one line per non-None stage."""
    def default(obj):
        if isinstance(obj, Path):
            return str(obj)
        return str(obj)
    stage_names = ("web_baseline", "retrieved", "reasoned", "verified", "synthesized")
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "header",
            "query": state.query,
            "timestamp_start": state.timestamp_start,
            "schema_version": "ar-4",
        }, default=default) + "\n")
        for name in stage_names:
            stage_obj = getattr(state, name, None)
            if stage_obj is None:
                continue
            f.write(json.dumps({
                "kind": "stage",
                "stage": name,
                **asdict(stage_obj),
            }, default=default) + "\n")

# _amain body — adds 2 LOC (15 → 17):
async def _amain(ns: argparse.Namespace) -> str:
    cfg = from_env()
    overrides: dict = {}
    if ns.max_iter_reasoner is not None:
        overrides["max_iter_reasoner"] = ns.max_iter_reasoner
    if ns.max_iter_verifier is not None:
        overrides["max_iter_verifier"] = ns.max_iter_verifier
    if ns.no_grounding:
        overrides["google_search_grounding"] = None
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)
    base_image_dir = cfg.rag_working_dir.parent / "images"
    if base_image_dir.is_dir():
        ensure_image_server(base_image_dir)
    result = await research(ns.query, cfg)
    if ns.dump_state is not None:
        _write_dump_state(result.state, ns.dump_state)
    return result.markdown
```

LOC count check: _amain post-Wave-1 = 17 LOC (under 18 cap). 1 LOC of headroom for any future flag.

CONTRACT verification: `_write_dump_state` lives in `__main__.py`, NOT in `lib/research/` proper — preserves the package's pure-async no-CLI-side-effects character (Axis 1).

### Step 6 — Author `tests/unit/research/test_dump_state.py`

Required tests (≥ 4):

```python
import json, subprocess, sys
from pathlib import Path
import pytest
from lib.research.__main__ import _write_dump_state
from lib.research.types import (
    ResearchState, WebBaseline, RetrieverOutput, ReasonerOutput,
    VerifierOutput, SynthesizerOutput, Source,
)

def _full_state(query="q"):
    return ResearchState(
        query=query, timestamp_start=1.0,
        web_baseline=WebBaseline(queries_used=[query], snippets=[]),
        retrieved=RetrieverOutput(chunks=[], image_candidates=[]),
        reasoned=ReasonerOutput(inferences_md="m", additional_chunks=[],
                                 analyzed_images=[], iter_count=1),
        verified=VerifierOutput(fact_check_summary_md="s", confidence=80.0,
                                 external_citations=[], discrepancies=[], iter_count=2),
        synthesized=SynthesizerOutput(markdown="md", confidence=80.0, sources=[],
                                       embedded_images=[], note_lines=[]),
    )

def test_write_dump_state_writes_header_plus_5_stages(tmp_path):
    p = tmp_path / "ds.jsonl"
    _write_dump_state(_full_state(), p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # 1 header + 5 stages

def test_write_dump_state_header_has_schema_version_ar4(tmp_path):
    p = tmp_path / "ds.jsonl"
    _write_dump_state(_full_state(), p)
    header = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert header["kind"] == "header"
    assert header["schema_version"] == "ar-4"
    assert header["query"] == "q"

def test_write_dump_state_serializes_path_as_str(tmp_path):
    state = _full_state()
    state.synthesized = SynthesizerOutput(
        markdown="md", confidence=80.0, sources=[],
        embedded_images=[Path("/tmp/img1.jpg"), Path("/tmp/img2.png")],
        note_lines=[],
    )
    p = tmp_path / "ds.jsonl"
    _write_dump_state(state, p)
    syn_line = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])
    assert syn_line["stage"] == "synthesized"
    assert all(isinstance(x, str) for x in syn_line["embedded_images"])

def test_write_dump_state_skips_missing_stages(tmp_path):
    state = ResearchState(query="q", timestamp_start=1.0)  # all stages None
    p = tmp_path / "ds.jsonl"
    _write_dump_state(state, p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # header only, no stage lines

def test_subprocess_cli_smoke_with_dump_state(tmp_path):
    """Cap=0 LLM-free CLI smoke + --dump-state. No live LLM, no live network.
    Validates exit 0 + file exists + valid JSONL."""
    dump_path = tmp_path / "subprocess-dumpstate.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "omnigraph.research",
         "--max-iter-reasoner", "0", "--max-iter-verifier", "0",
         "--no-grounding",
         "--dump-state", str(dump_path),
         "test query"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}: stderr={result.stderr}"
    assert dump_path.exists()
    lines = dump_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2  # header + at least 1 stage
    header = json.loads(lines[0])
    assert header["kind"] == "header" and header["schema_version"] == "ar-4"
    for line in lines[1:]:
        ev = json.loads(line)
        assert ev["kind"] == "stage" and ev["stage"] in (
            "web_baseline", "retrieved", "reasoned", "verified", "synthesized"
        )
```

### Step 7 — Run pytest, verify ≥ 123 green

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v --tb=short
# expected: ≥ 123 green
#  - 113 ar-3 baseline (modulo the 1 known flake test_subprocess_smoke_with_max_iter_zero)
#  - ≥ 10 new ar-4 W1 tests (≥ 4 telemetry + ≥ 4 stream + ≥ 4 dump-state)
# If the flake fails under full-suite run, re-run JUST that test in isolation
# to confirm it's the known flake (not a real regression):
venv/Scripts/python.exe -m pytest tests/unit/research/test_main_cli_flags.py::test_subprocess_smoke_with_max_iter_zero -v
```

### Step 8 — Layer 2a cap=0 LLM-free CLI smoke

```bash
mkdir -p .scratch
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 0 \
  --max-iter-verifier 0 \
  --no-grounding \
  --dump-state .scratch/ar-4-l2a-dumpstate.jsonl \
  "什么是 Hermes Harness 深度解析"
# expected:
#  - exit code 0
#  - stdout: non-empty markdown (>= 100 chars)
#  - .scratch/ar-4-l2a-dumpstate.jsonl exists; valid JSONL; ≥ 2 lines (header + ≥ 1 stage)
#  - header line carries schema_version='ar-4'
```

If `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` is also set in the env, the smoke should ALSO write a separate telemetry JSONL with pipeline_start + per-stage events + pipeline_end (different file from --dump-state).

## Acceptance criteria

Each must_haves.truth maps to one of the verification surfaces below. Wave 1 is complete when every truth has a green test or smoke result.

| Truth (abbreviated) | Verified by |
|---|---|
| 4 event-type constants exist | `test_telemetry::test_make_event_carries_event_type_stage_ts` (uses constants) |
| make_event shape | `test_telemetry::test_make_event_carries_event_type_stage_ts` + `test_make_event_merges_payload` |
| write_event None no-op | `test_telemetry::test_write_event_none_sink_is_noop` |
| write_event swallows OSError | `test_telemetry::test_write_event_swallows_oserror` |
| _json_default Path + dataclass | `test_telemetry::test_json_default_handles_path_and_dataclass` |
| research_stream emits PIPELINE_START first | `test_research_stream::test_research_stream_yields_pipeline_start_first` |
| research_stream emits 5 stage pairs in order | `test_research_stream::test_research_stream_yields_5_stage_pairs_in_order` |
| research_stream emits PIPELINE_END last | `test_research_stream::test_research_stream_yields_pipeline_end_last` |
| sink None no file I/O | `test_research_stream::test_research_stream_sink_none_no_file_io` |
| sink set writes JSONL matching iterator | `test_research_stream::test_research_stream_sink_set_writes_valid_jsonl_matching_iterator` |
| research() + research_stream() share emission | `test_research_stream::test_research_consumes_same_pipeline_as_stream` |
| _write_dump_state writes header + 5 stages | `test_dump_state::test_write_dump_state_writes_header_plus_5_stages` |
| header schema_version='ar-4' | `test_dump_state::test_write_dump_state_header_has_schema_version_ar4` |
| Path values serialize as str | `test_dump_state::test_write_dump_state_serializes_path_as_str` |
| Missing stages skipped | `test_dump_state::test_write_dump_state_skips_missing_stages` |
| --dump-state CLI subprocess smoke | `test_dump_state::test_subprocess_cli_smoke_with_dump_state` |
| _amain ≤ 18 LOC | manual code review at commit time + grep-and-count |
| Layer 2a cap=0 smoke exit 0 + JSONL | step-8 manual run; record output in SUMMARY |
| Pytest ≥ 123 green | step-7 manual run; record count in SUMMARY |
| CONTRACT-01 + CONTRACT-02 clean | `bash scripts/check_contract.sh` (exits 0) |

## Smoke test layers

### Layer 1 — pytest (mandatory)

```bash
venv/Scripts/python.exe -m pytest tests/unit/research/ -v --tb=short
# target: ≥ 123 green; tolerate 1 known flake on test_subprocess_smoke_with_max_iter_zero
```

### Layer 2a — cap=0 LLM-free CLI smoke (mandatory, no keys required)

See step 8.

### Layer 3 — skill_runner

```bash
venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
  --test-file tests/skills/test_omnigraph_research.json
# expected: exit code 0
# Reuses ar-1/2/3 test JSON; ar-4 W1 doesn't change stdout structure for any
# existing test case (--dump-state is opt-in; default off keeps behaviour identical)
```

### Layer 2b — DEFERRED to Wave 2 (ar-4-02)

Live-key milestone smoke (TEST-05 with 5 pass conditions on `"Hermes Harness 深度解析"`) belongs to Wave 2. Wave 1 is exclusively observability infrastructure — no live tools required.

## CONTRACT enforcement

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
echo "CONTRACT-01 clean"
```

Wave 1 risk surface: NEW `lib/research/telemetry.py` MUST import zero `omnigraph_search` symbols (it doesn't need any KG access — it's pure JSON serialization).

### CONTRACT-02: no hardcoded `~/.hermes` / `omonigraph-vault` paths

```bash
hits=$(grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary" || true)
if [ -n "$hits" ]; then
  echo "CONTRACT-02 violation"; echo "$hits"; exit 1
fi
echo "CONTRACT-02 clean"
```

Wave 1 risk surface: telemetry sink path comes from `cfg.telemetry_jsonl` (injected via `from_env()`); dump-state path comes from CLI argv. NEITHER hardcodes any filesystem literal in `lib/research/`.

## Forward-only commit discipline

**Never `--amend`. Never `git reset --soft/--mixed/--hard`. Always explicit `git add <files>`.** Wave 1 commit chain (atomic, single Bash invocation per commit):

```bash
# After all 6 files exist + tests green + smoke green:
git add \
  lib/research/telemetry.py \
  lib/research/orchestrator.py \
  lib/research/__main__.py \
  tests/unit/research/test_telemetry.py \
  tests/unit/research/test_research_stream.py \
  tests/unit/research/test_dump_state.py \
&& git commit -m "feat(ar-4): telemetry sink + research_stream body + --dump-state CLI flag

LIB-08: lib/research/telemetry.py with event-type constants + make_event +
write_event + _json_default. research_stream() body filled; research() refactored
to share emission via _run_pipeline async generator. Single source of truth for
stage-emit ordering; both surfaces honour cfg.telemetry_jsonl identically.

CLI-02: --dump-state <path> argparse flag added; _write_dump_state helper in
__main__.py writes JSONL header + per-stage lines with schema_version='ar-4'.
_amain body 17 LOC (≤ 18 cap).

Tests: ≥10 new (4 telemetry + 5 research_stream + 5 dump-state including
subprocess CLI smoke). Layer 2a cap=0 LLM-free CLI smoke exit 0 with valid
dump-state JSONL.

CONTRACT-01 + CONTRACT-02 clean. omonigraph typo preserved (canonical).
" \
&& git push
```

If a later forward-fix is needed (e.g., adding a missed test case or a docstring tweak), commit a NEW forward-only commit — DO NOT amend. SUMMARY.md hash backfill (if needed) goes via a separate `docs(ar-4): backfill commit hashes` commit per `feedback_no_amend_in_concurrent_quicks.md` discipline.

> **Operator note**: ar-4 Wave 1 unit tests use mocks + tmp paths — NO live keys required. Live-key milestone smoke (TEST-05) is Wave 2 (ar-4-02) and runs on Hermes; it requires TAVILY_API_KEY + BRAVE_SEARCH_API_KEY in `~/.hermes/.env` (and Vertex creds if `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`).
