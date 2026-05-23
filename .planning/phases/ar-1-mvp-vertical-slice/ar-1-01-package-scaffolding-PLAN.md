---
phase: ar-1-mvp-vertical-slice
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/research/__init__.py
  - lib/research/types.py
  - lib/research/config.py
  - lib/research/orchestrator.py
  - lib/research/stages/__init__.py
  - lib/research/README.md
  - pyproject.toml
  - scripts/check_contract.sh
  - tests/unit/research/__init__.py
  - tests/unit/research/test_types.py
  - tests/unit/research/test_config.py
autonomous: true
requirements:
  - LIB-01
  - LIB-02
  - LIB-03
  - LIB-04
  - LIB-05
  - LIB-06
  - LIB-07
  - LIB-09
  - CONFIG-01
  - CONFIG-02
  - TEST-01
  - CONTRACT-01
  - CONTRACT-02

must_haves:
  truths:
    - "Package importable as both `lib.research` (physical) and `omnigraph.research` (declared via pyproject namespace mapping)"
    - "All 7 frozen dataclasses match the verbatim shapes locked in CONTEXT.md (no field renames, no extra fields, no missing defaults)"
    - "`ResearchConfig.from_env()` reads env vars ONCE at construction; hot path uses dataclass fields only"
    - "`research_stream()` signature exists and raises `NotImplementedError(\"ar-4\")` — body deferred"
    - "CONTRACT-01 grep hook returns 0 hits (no forbidden `omnigraph_search` imports beyond `omnigraph_search.query`)"
    - "CONTRACT-02 grep returns 0 hits for hardcoded `~/.hermes` or `omonigraph-vault` paths outside config.py"
  artifacts:
    - path: "lib/research/types.py"
      provides: "7 frozen dataclasses + Status alias + ResearchState"
      contains: "Source, WebBaseline, RetrievedImage, RetrieverOutput, ReasonerOutput, VerifierOutput, SynthesizerOutput, ResearchState, ResearchResult, ResearchConfig"
    - path: "lib/research/config.py"
      provides: "ResearchConfig.from_env() factory"
      contains: "OMNIGRAPH_BASE_DIR / OMNIGRAPH_LLM_PROVIDER / OMNIGRAPH_RESEARCH_OUTPUT_DIR / OMNIGRAPH_RESEARCH_TELEMETRY_JSONL / TAVILY_API_KEY / BRAVE_SEARCH_API_KEY env reads"
    - path: "lib/research/orchestrator.py"
      provides: "async def research() skeleton + async def research_stream() (NotImplementedError ar-4)"
      contains: "Pipeline order WebBaseline → Retriever → Reasoner → Verifier → Synthesizer (stubs called from ar-1-02)"
    - path: "pyproject.toml"
      provides: "Namespace mapping omnigraph.research → lib/research/ (LIB-09 option a)"
      contains: "[project] table + [tool.setuptools.packages.find] or [tool.setuptools.package-dir]"
    - path: "scripts/check_contract.sh"
      provides: "CONTRACT-01 grep hook for forbidden omnigraph_search imports"
    - path: "lib/research/README.md"
      provides: "Human-facing — packaging choice (LIB-09), dev quickstart, CONTRACT checklist"
  key_links:
    - from: "lib/research/orchestrator.py"
      to: "lib.research.config / lib.research.types"
      via: "from .config import ResearchConfig; from .types import ResearchResult, ResearchState"
      pattern: "from .config import|from .types import"
    - from: "tests/unit/research/test_types.py"
      to: "lib.research.types"
      via: "from lib.research.types import ..."
      pattern: "from lib\\.research\\.types import"
    - from: "external consumer (skill / CLI)"
      to: "lib.research"
      via: "from omnigraph.research import research, ResearchConfig"
      pattern: "from omnigraph\\.research import"
---

<objective>
Bootstrap the `lib/research/` Python package skeleton: 7 frozen dataclasses + ResearchConfig env-driven factory + orchestrator skeleton with `async def research()` and `async def research_stream()` (deferred body). Add namespace mapping in `pyproject.toml` so `omnigraph.research` resolves to `lib/research/` (LIB-09 option a). Land CONTRACT-01 grep hook and unit tests for types + config.

Purpose: Every later plan in this phase imports `lib.research.types` for dataclass shapes and `lib.research.config` for env-driven configuration. This plan must land first so plans 02/03/04 have stable types to import.

Output: 11 new files (lib/research/*.py + tests/unit/research/* + pyproject.toml edit + scripts/check_contract.sh + README) all importable, all CONTRACT grep clean.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-Agentic-RAG-v1.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@docs/design/agentic_rag_internal_api.md
@pyproject.toml
@config.py
@CLAUDE.md

<interfaces>
**7 frozen dataclasses — verbatim shapes from CONTEXT.md § "Seven frozen dataclasses (verbatim shapes)"**

Copy verbatim into `lib/research/types.py` — do NOT rename fields, do NOT add fields, do NOT remove defaults:

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

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

**ResearchConfig is a frozen dataclass but the design doc explicitly classifies it as a config dataclass (Axis 2 "no module-level singletons"). It lives in `types.py` alongside the 6 stage outputs + ResearchResult + ResearchState, so all type imports are one-stop.**

`ResearchState` is the ONLY mutable dataclass — orchestrator writes one stage field at a time as the pipeline advances.

**ResearchConfig.from_env() — implementation pattern (lib/research/config.py)**

`config.py` re-exports `ResearchConfig` from `types.py` AND adds the `from_env()` factory. Pattern mirrors the project root `config.py` (see `@config.py`):

```python
from __future__ import annotations
import os
from pathlib import Path

from .types import ResearchConfig


def _skipped_web_search(query: str) -> list[dict]:
    """Stub web_search used when TAVILY_API_KEY is unset (ar-1 default).

    Returns empty list. WebBaseline stage detects this and emits status='skipped'
    with reason='TAVILY_API_KEY unset — ar-1 stub mode'.
    """
    return []


def from_env() -> ResearchConfig:
    """Read env once and compose a ResearchConfig.

    All env reads happen here. Hot path uses ResearchConfig fields only (Axis 3).
    """
    base_dir = Path(os.environ.get("OMNIGRAPH_BASE_DIR")) if os.environ.get("OMNIGRAPH_BASE_DIR") \
        else Path.home() / ".hermes" / "omonigraph-vault"  # 'omonigraph' typo is canonical

    rag_working_dir = base_dir / "lightrag_storage"

    # LLM provider — default deepseek; routes via OMNIGRAPH_LLM_PROVIDER
    from lib.llm_complete import get_llm_func  # noqa: E402  -- avoid eager import at module scope
    llm_complete = get_llm_func()

    from lib.lightrag_embedding import embedding_func  # noqa: E402

    # Vision cascade duck-typed (CONTEXT.md axis 2 — injected, not module-level)
    from lib.vision_cascade import VisionCascade  # noqa: E402
    vision_cascade = VisionCascade()

    # Web search — ar-1 stub (Tavily lands in ar-3)
    if os.environ.get("TAVILY_API_KEY"):
        # Real Tavily callable wired in ar-3; ar-1 still uses stub since
        # tavily-python integration is out of scope.
        web_search = _skipped_web_search
    else:
        web_search = _skipped_web_search

    web_search_fallback = None  # ar-3 wires Brave when BRAVE_SEARCH_API_KEY set
    web_extract = None
    google_search_grounding = None  # ar-3 wires Vertex Grounding when llm_complete is Vertex

    output_dir = Path(os.environ["OMNIGRAPH_RESEARCH_OUTPUT_DIR"]) \
        if os.environ.get("OMNIGRAPH_RESEARCH_OUTPUT_DIR") else None
    telemetry_jsonl = Path(os.environ["OMNIGRAPH_RESEARCH_TELEMETRY_JSONL"]) \
        if os.environ.get("OMNIGRAPH_RESEARCH_TELEMETRY_JSONL") else None

    return ResearchConfig(
        rag_working_dir=rag_working_dir,
        llm_complete=llm_complete,
        embedding_func=embedding_func,
        vision_cascade=vision_cascade,
        web_search=web_search,
        web_search_fallback=web_search_fallback,
        web_extract=web_extract,
        google_search_grounding=google_search_grounding,
        output_dir=output_dir,
        telemetry_jsonl=telemetry_jsonl,
    )


# Re-export so callers can do `from lib.research.config import ResearchConfig`
__all__ = ["ResearchConfig", "from_env"]
```

**orchestrator.py skeleton (stages wired in plan ar-1-02)**

```python
"""Agentic-RAG-v1 orchestrator (ar-1 skeleton).

Stages are wired by ar-1-02. This file establishes:
  - async def research(query, config) -> ResearchResult
  - async def research_stream(query, config) -> AsyncIterator[Event]
    (signature only; body raises NotImplementedError('ar-4'))
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from .config import ResearchConfig, from_env
from .types import ResearchResult, ResearchState


async def research(query: str, config: ResearchConfig | None = None) -> ResearchResult:
    """Run the 5-stage research pipeline. Strict sequential order (Axis 1).

    Stages are imported lazily so import-time failures in any stage don't
    poison module load. Each stage best-effort try/excepts (Axis 3).
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())

    # Stages wired in ar-1-02:
    # from .stages.web_baseline import run as run_web_baseline
    # state.web_baseline = await run_web_baseline(query, cfg)
    # from .stages.retriever import run as run_retriever
    # state.retrieved = await run_retriever(query, cfg)
    # ... (Reasoner, Verifier, Synthesizer)

    raise NotImplementedError("Stage wiring lands in ar-1-02")


async def research_stream(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of research(). Body lands in ar-4 with telemetry.

    Signature exists in ar-1 to lock the API rule (Axis 5: streaming peer).
    """
    raise NotImplementedError("ar-4")
    yield {}  # unreachable; kept so type-checker accepts AsyncIterator return
```

**`lib/research/__init__.py` — public API surface (LIB-01)**

```python
"""Agentic-RAG-v1 research package.

Importable as `lib.research` (physical) and `omnigraph.research` (declared in pyproject.toml).
"""
from .config import ResearchConfig, from_env  # noqa: F401
from .orchestrator import research, research_stream  # noqa: F401
from .types import (  # noqa: F401
    Source,
    ResearchResult,
    ResearchState,
)

__all__ = [
    "research",
    "research_stream",
    "ResearchConfig",
    "from_env",
    "ResearchResult",
    "ResearchState",
    "Source",
]
```

**Per-stage dataclasses (LIB-01 nuance)** are NOT re-exported at top level — accessible only via `from lib.research.types import RetrieverOutput` for advanced consumers (HTTP wrapper, CLI --dump-state in ar-4).

**pyproject.toml — Edit (NOT Write) to preserve existing `[tool.pytest.ini_options]`**

Existing 9-line file contains only `[tool.pytest.ini_options]`. Append `[project]` + `[tool.setuptools]` mapping. After edit:

```toml
[project]
name = "omnigraph-vault"
version = "1.0.0"
description = "Personal LightRAG-backed knowledge base + Agentic-RAG-v1 research lib"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["."]
include = ["lib", "lib.*", "omnigraph_search", "omnigraph_search.*"]

[tool.setuptools.package-dir]
"omnigraph.research" = "lib/research"

[tool.pytest.ini_options]
# ... existing block preserved verbatim ...
```

The `package-dir` mapping is what makes `from omnigraph.research import research` resolve to `lib/research/__init__.py`. CONTEXT.md § "LIB-09 Resolution" is the source of truth for this choice.

**scripts/check_contract.sh — CONTRACT-01 grep hook (verbatim from CONTEXT.md § CONTRACT enforcement)**

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
echo "CONTRACT-01 ok"
```

Make executable: `chmod +x scripts/check_contract.sh`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write lib/research/types.py with 7 frozen dataclasses + tests</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Seven frozen dataclasses (verbatim shapes)"
    - docs/design/agentic_rag_internal_api.md § dataclass definitions
    - .planning/REQUIREMENTS-Agentic-RAG-v1.md § LIB-01..07
  </read_first>
  <files>lib/research/__init__.py (placeholder), lib/research/types.py, lib/research/stages/__init__.py, tests/unit/research/__init__.py, tests/unit/research/test_types.py</files>
  <behavior>
    - Test 1: `Source(kind="web", uri="http://x")` constructs; `frozen=True` → `s.uri = "y"` raises `dataclasses.FrozenInstanceError`
    - Test 2: `Source.kind` accepts only `{"kg_chunk", "kg_image", "web", "grounding"}` — pin via Literal type (runtime check NOT required, type-checker only; assert literal values via `typing.get_args`)
    - Test 3: `Status` alphabet is exactly `("ok", "skipped", "failed")` — assert via `typing.get_args(Status)`
    - Test 4: `WebBaseline(queries_used=[], snippets=[])` defaults `status="ok"`, `reason=None`
    - Test 5: `SynthesizerOutput` has NO `status` field — assert `"status" not in {f.name for f in dataclasses.fields(SynthesizerOutput)}`
    - Test 6: `ResearchState` is mutable — `state = ResearchState(query="x", timestamp_start=0.0); state.web_baseline = wb` does NOT raise
    - Test 7: `ResearchConfig` is frozen — `cfg.max_iter_reasoner = 99` raises `FrozenInstanceError`
    - Test 8: `ResearchConfig` defaults: `max_iter_reasoner=5`, `max_iter_verifier=3`, `web_search_fallback=None`, `output_dir=None`, `telemetry_jsonl=None`
    - Test 9: All required fields produce `TypeError` if omitted — assert `Source()` raises (`kind`, `uri` required)
  </behavior>
  <action>
    1. Create empty `lib/research/__init__.py` placeholder (final content lands in Task 4 after orchestrator + config exist).
    2. Create empty `lib/research/stages/__init__.py` (subpackage marker; stage modules land in ar-1-02).
    3. Create `lib/research/types.py` with the verbatim 7-dataclass block from `<interfaces>` above. Add module docstring `"""Agentic-RAG-v1 dataclasses (frozen, except ResearchState)."""`.
    4. Create `tests/unit/research/__init__.py` empty.
    5. Create `tests/unit/research/test_types.py` exercising all 9 behaviors. Use `dataclasses.fields(...)`, `dataclasses.FrozenInstanceError`, `typing.get_args(Status)`. No mocks needed — pure dataclass tests.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.types import Source, ResearchConfig, Status; print('OK')" &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_types.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/types.py` contains exactly 9 dataclass declarations (Source, WebBaseline, RetrievedImage, RetrieverOutput, ReasonerOutput, VerifierOutput, SynthesizerOutput, ResearchState, ResearchResult, ResearchConfig — wait that's 10; the Status alias is NOT a dataclass, ResearchState is the 9th and ResearchConfig the 10th. Re-count: 7 stage dataclasses + ResearchState + ResearchResult + ResearchConfig = 10 dataclass-decorated definitions plus 1 Literal alias)
    - `python -c "from lib.research.types import *"` succeeds with no import error
    - `pytest tests/unit/research/test_types.py -v` exits 0 with ≥9 tests passing
    - `SynthesizerOutput` lacks `status` field (verified by test 5)
    - `Status` Literal contains exactly 3 values (verified by test 3)
  </acceptance_criteria>
  <done>types.py with all 10 dataclasses + Status alias; ≥9 unit tests passing.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write lib/research/config.py with ResearchConfig.from_env() factory + tests</name>
  <read_first>
    - lib/research/types.py (just created — re-export ResearchConfig from here)
    - config.py (root project config — pattern for env-once + lazy imports)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Configuration (CONFIG-01, CONFIG-02)"
    - lib/llm_complete.py (signature of get_llm_func)
    - lib/lightrag_embedding.py (embedding_func signature)
    - lib/vision_cascade.py (VisionCascade class shape)
  </read_first>
  <files>lib/research/config.py, tests/unit/research/test_config.py</files>
  <behavior>
    - Test 1: `from_env()` returns a `ResearchConfig` instance when called with no args
    - Test 2: `from_env()` reads `OMNIGRAPH_BASE_DIR` env override → `cfg.rag_working_dir.parent` matches override (use monkeypatch + `~/.hermes/omonigraph-vault` default when unset)
    - Test 3: `from_env()` with `TAVILY_API_KEY` unset → `cfg.web_search` is the `_skipped_web_search` callable (returns `[]` when called)
    - Test 4: `from_env()` with `BRAVE_SEARCH_API_KEY` unset → `cfg.web_search_fallback is None`
    - Test 5: `from_env()` with `OMNIGRAPH_RESEARCH_OUTPUT_DIR` unset → `cfg.output_dir is None`
    - Test 6: `from_env()` with `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` unset → `cfg.telemetry_jsonl is None`
    - Test 7: env-once contract — call `from_env()`, then `monkeypatch.setenv("OMNIGRAPH_BASE_DIR", "/tmp/x")`, then read `cfg.rag_working_dir` — value is the OLD path (frozen at construction; hot path doesn't re-read env). Then re-call `from_env()` and observe new value.
    - Test 8: `cfg.max_iter_reasoner == 5` and `cfg.max_iter_verifier == 3` (defaults from types.py)
    - Test 9: `_skipped_web_search("any query")` returns `[]`
  </behavior>
  <action>
    Create `lib/research/config.py` with the pattern from `<interfaces>` above. Module docstring: `"""Env-driven ResearchConfig factory — single source of env reads (Axis 3)."""`.

    Key implementation rules:
    - Lazy imports of `lib.llm_complete`, `lib.lightrag_embedding`, `lib.vision_cascade` INSIDE `from_env()` body (not at module scope) — keeps `lib.research` importable even if those modules have init-time side effects.
    - `_skipped_web_search` is a module-level function so its identity is stable across calls (test 3 asserts `cfg.web_search is _skipped_web_search`).
    - Re-export `ResearchConfig` from types: `from .types import ResearchConfig`.
    - `__all__ = ["ResearchConfig", "from_env"]`.

    Then create `tests/unit/research/test_config.py`:
    - Use `pytest.MonkeyPatch` for env manipulation.
    - Use `monkeypatch.delenv("VAR", raising=False)` for unset assertions.
    - Mock `lib.llm_complete.get_llm_func` etc. ONLY if they have heavy import side effects; otherwise let them load normally (they're lightweight per design).
    - PEP 8, type hints, `from __future__ import annotations`.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.config import from_env, ResearchConfig; cfg = from_env(); print(type(cfg).__name__, cfg.max_iter_reasoner)" &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_config.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/config.py` defines `from_env()` and re-exports `ResearchConfig`
    - `python -c "from lib.research.config import from_env; from_env()"` exits 0 (with default env)
    - `pytest tests/unit/research/test_config.py -v` exits 0 with ≥9 tests passing
    - All env reads happen inside `from_env()` body — grep `os.environ` count in config.py is ≤ 8 (one per documented env var)
    - File contains literal `omonigraph` (typo preserved per CLAUDE.md)
  </acceptance_criteria>
  <done>config.py with from_env() + ≥9 tests passing.</done>
</task>

<task type="auto">
  <name>Task 3: Write lib/research/orchestrator.py skeleton (stages deferred to ar-1-02)</name>
  <read_first>
    - lib/research/types.py + lib/research/config.py (just created)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Strict pipeline order (Axis 1)" and § "Five API design rules"
    - docs/design/agentic_rag_internal_api.md § orchestrator pseudocode
  </read_first>
  <files>lib/research/orchestrator.py</files>
  <action>
    Create `lib/research/orchestrator.py` with the skeleton from `<interfaces>` above. Body of `research()` raises `NotImplementedError("Stage wiring lands in ar-1-02")` — explicit deferred marker. Body of `research_stream()` raises `NotImplementedError("ar-4")` per Axis 5 lock + LIB-08 split (signature here, body in ar-4).

    Module docstring documents:
    - The 5-stage strict order (WebBaseline → Retriever → Reasoner → Verifier → Synthesizer)
    - Why `research_stream` exists in ar-1 (locks API rule today; body lands in ar-4)
    - Pure async entrypoint (Axis 1) — no print, no file I/O, no argv parsing in this file

    NO stages are imported at module scope (stages are imported lazily inside `research()` body when ar-1-02 wires them — this prevents stage import-time failures from poisoning the orchestrator module).

    Add minimal smoke-import test at end of `tests/unit/research/test_config.py` (NOT a new file — to avoid bloating test count): `from lib.research.orchestrator import research, research_stream` — confirms orchestrator imports cleanly.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.orchestrator import research, research_stream; import inspect; assert inspect.iscoroutinefunction(research); assert inspect.isasyncgenfunction(research_stream); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/orchestrator.py` defines `async def research(...)` and `async def research_stream(...)`
    - Both functions raise `NotImplementedError` with descriptive messages
    - `research_stream` is an async generator (has `yield` in body, even if unreachable)
    - No top-level imports of `.stages.*` (stages are wired in ar-1-02)
    - File contains zero `print()`, zero `open(...)` calls, zero `sys.argv` references (Axis 1)
  </acceptance_criteria>
  <done>orchestrator.py skeleton; both async functions importable, both raise NotImplementedError with phase-marker messages.</done>
</task>

<task type="auto">
  <name>Task 4: Finalize lib/research/__init__.py public API + smoke import test</name>
  <read_first>
    - lib/research/types.py + lib/research/config.py + lib/research/orchestrator.py (all created)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Module layout"
  </read_first>
  <files>lib/research/__init__.py</files>
  <action>
    Replace placeholder `lib/research/__init__.py` with the public API from `<interfaces>` above:

    ```python
    """Agentic-RAG-v1 research package.

    Importable as `lib.research` (physical) and `omnigraph.research` (declared in pyproject.toml).
    """
    from .config import ResearchConfig, from_env  # noqa: F401
    from .orchestrator import research, research_stream  # noqa: F401
    from .types import (  # noqa: F401
        Source,
        ResearchResult,
        ResearchState,
    )

    __all__ = [
        "research",
        "research_stream",
        "ResearchConfig",
        "from_env",
        "ResearchResult",
        "ResearchState",
        "Source",
    ]
    ```

    Per-stage dataclasses (RetrieverOutput etc.) are NOT in `__all__` — accessed only via `from lib.research.types import ...` (LIB-01 nuance documented in CONTEXT.md).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "import lib.research; print(sorted(lib.research.__all__))"</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/__init__.py` exports exactly 7 names: `research`, `research_stream`, `ResearchConfig`, `from_env`, `ResearchResult`, `ResearchState`, `Source`
    - `python -c "from lib.research import research, ResearchConfig, ResearchResult"` exits 0
    - `python -c "from lib.research import RetrieverOutput"` raises `ImportError` (per-stage types not at top level)
  </acceptance_criteria>
  <done>__init__.py public surface locked at 7 names matching CONTEXT.md § "Module layout" __init__.py contract.</done>
</task>

<task type="auto">
  <name>Task 5: Edit pyproject.toml to add namespace mapping (LIB-09 option a)</name>
  <read_first>
    - pyproject.toml (read existing 9-line content)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "LIB-09 Resolution: Option (a) — Namespace mapping"
  </read_first>
  <files>pyproject.toml</files>
  <action>
    Use the **Edit tool** (NOT Write) to PRESERVE the existing `[tool.pytest.ini_options]` block. PREPEND the following blocks BEFORE the existing content:

    ```toml
    [project]
    name = "omnigraph-vault"
    version = "1.0.0"
    description = "Personal LightRAG-backed knowledge base + Agentic-RAG-v1 research lib"
    requires-python = ">=3.11"

    [tool.setuptools.packages.find]
    where = ["."]
    include = ["lib", "lib.*", "omnigraph_search", "omnigraph_search.*"]

    [tool.setuptools.package-dir]
    "omnigraph.research" = "lib/research"

    ```

    Verify the existing `[tool.pytest.ini_options]` block survives byte-identical (line count grew, but the last 9 lines match the prior content).

    NOTE: `pip install -e .` is DEFERRED to ar-1-03 Task 0 — this plan only declares the `[tool.setuptools.package-dir]` namespace mapping. Tests in ar-1-01 import via `lib.research.*` under `pythonpath = ["."]`, which does NOT require an editable install. The `omnigraph.research` namespace becomes resolvable via `python -m omnigraph.research` only after ar-1-03 Task 0 runs `pip install -e .` against this declared mapping. Verifying `from omnigraph.research import research` is NOT a gate for this plan; ar-1-01 passes if `lib.research`-rooted imports work.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "import tomllib; t = tomllib.loads(open('pyproject.toml').read()); assert t['project']['name'] == 'omnigraph-vault'; assert t['tool']['setuptools']['package-dir']['omnigraph.research'] == 'lib/research'; assert 'pytest' in t['tool']; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `pyproject.toml` parses cleanly via Python 3.11+ `tomllib`
    - `tomllib.loads(...)["project"]["name"] == "omnigraph-vault"`
    - `tomllib.loads(...)["tool"]["setuptools"]["package-dir"]["omnigraph.research"] == "lib/research"`
    - Existing `[tool.pytest.ini_options]` block preserved (asyncio_mode + testpaths + markers all intact)
    - `pytest` discovery still works: `pytest --collect-only tests/unit/research/` lists test_types.py + test_config.py
  </acceptance_criteria>
  <done>pyproject.toml extended with [project] + namespace mapping; existing pytest config preserved.</done>
</task>

<task type="auto">
  <name>Task 6: Create scripts/check_contract.sh (CONTRACT-01 grep hook)</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "CONTRACT enforcement (CONTRACT-01, CONTRACT-02)"
  </read_first>
  <files>scripts/check_contract.sh</files>
  <action>
    Create `scripts/check_contract.sh` with the verbatim shell script from CONTEXT.md § CONTRACT enforcement (also reproduced in `<interfaces>` above).

    Add a CONTRACT-02 check section AFTER the CONTRACT-01 block:

    ```bash
    # CONTRACT-02: no hardcoded ~/.hermes or omonigraph-vault paths outside config.py
    hits2=$(grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
      | grep -vE "config\.py|README\.md|^Binary" \
      || true)
    if [ -n "$hits2" ]; then
      echo "CONTRACT-02 violation: hardcoded ~/.hermes or omonigraph-vault path in lib/research/ outside config.py"
      echo "$hits2"
      exit 1
    fi
    echo "CONTRACT-02 ok"
    ```

    Make the file executable: chmod 755 (use `git update-index --chmod=+x scripts/check_contract.sh` after `git add` so the executable bit lands in the commit on Windows hosts).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/check_contract.sh` exists
    - Running `bash scripts/check_contract.sh` exits 0 and prints `CONTRACT-01 ok` then `CONTRACT-02 ok`
    - File contains the literal string `from omnigraph_search.query` (the allowed-pattern reference)
  </acceptance_criteria>
  <done>CONTRACT-01 + CONTRACT-02 grep hook landed; both passing on the ar-1-01 file set.</done>
</task>

<task type="auto">
  <name>Task 7: Write lib/research/README.md documenting LIB-09 + dev quickstart + CONTRACT checklist</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md (full)
    - .planning/PROJECT-Agentic-RAG-v1.md
  </read_first>
  <files>lib/research/README.md</files>
  <action>
    Write `lib/research/README.md` (human-facing — not loaded by code). Sections:

    1. **What this is** — 3-line summary: lib/research/ is the Agentic-RAG-v1 research lib; backs the omnigraph_research skill, CLI, and future HTTP wrapper; orchestrates 5 stages over LightRAG KG + web search.

    2. **Naming (LIB-09 = option a)** — Physical path is `lib/research/`. Declared name in `pyproject.toml` is `omnigraph.research`. Both work: `from lib.research import research` and `from omnigraph.research import research` resolve to the same module. Rationale: keep all implementation libs at `lib/` (project convention); avoid one-off rename.

    3. **Quickstart** —
       ```bash
       venv/Scripts/python.exe -c "from lib.research import research, from_env; cfg = from_env(); print(cfg.rag_working_dir)"
       venv/Scripts/python.exe -m pytest tests/unit/research/ -v
       ```
       Note: `python -m omnigraph.research "<query>"` lands in ar-1-03.

    4. **CONTRACT checklist (manual; pre-commit infra deferred to v1.1)** —
       - [ ] `bash scripts/check_contract.sh` exits 0 (CONTRACT-01 + CONTRACT-02 clean)
       - [ ] Only `omnigraph_search.query.search` is imported from KG side (CONTRACT-01)
       - [ ] Hardcoded paths exist ONLY in `lib/research/config.py` (CONTRACT-02)
       - [ ] All 7 dataclasses match CONTEXT.md verbatim shapes — diff before any commit touching `types.py`

    5. **Stage status (ar-1)** — table showing each stage's ar-1 implementation:
       | Stage | ar-1 status | Future phase |
       |---|---|---|
       | WebBaseline | stub (`status="skipped"` if web_search returns []) | real Tavily in ar-3 |
       | Retriever | wraps `omnigraph_search.query.search()` directly | refinements ar-2 |
       | Reasoner | stub (`status="skipped"`, `iter_count=0`) | agent loop ar-2 |
       | Verifier | stub (`status="skipped"`, `iter_count=0`) | tools loop ar-3 |
       | Synthesizer | minimal markdown synth + CJK heuristic | prompt iteration ar-2/4 |

    6. **Out of scope for ar-1** — link to CONTEXT.md § "Out of Scope" for the deferral table.

    Markdown only; no code execution beyond the quickstart snippets. Keep under 100 lines.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from pathlib import Path; assert Path('lib/research/README.md').exists(); print('exists')"</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/README.md` exists, ≥40 lines, ≤120 lines
    - Contains the literal string `LIB-09` (linking the README back to the design choice)
    - Contains a CONTRACT checklist with at least 3 checkbox items
    - Mentions `omonigraph` typo as canonical (one-line note)
  </acceptance_criteria>
  <done>README documents naming choice + quickstart + CONTRACT checklist + stage stub table.</done>
</task>

</tasks>

<verification>
- All 7 tasks pass their automated checks
- `venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥18 tests passing
- `python -c "from lib.research import research, research_stream, ResearchConfig, from_env, ResearchResult, ResearchState, Source"` exits 0
- `python -c "from omnigraph.research import research"` is DEFERRED to ar-1-03 Task 0 (which runs `pip install -e .`). This plan only declares the `[tool.setuptools.package-dir]` namespace mapping; the editable install that activates `omnigraph.research` resolution is owned by ar-1-03 Task 0. Verifying this import in ar-1-01 is NOT a gate — ar-1-01 passes if `lib.research`-rooted imports work under `pythonpath=["."]`.
- `bash scripts/check_contract.sh` exits 0 with both CONTRACT-01 and CONTRACT-02 clean
- `tomllib.loads(open("pyproject.toml").read())` parses; `["project"]["name"]` and `["tool"]["setuptools"]["package-dir"]["omnigraph.research"]` both present
- `lib/research/orchestrator.py` calls to `research()` raise `NotImplementedError("Stage wiring lands in ar-1-02")` — wires up exactly so plan ar-1-02 can start
</verification>

<success_criteria>
- 7 frozen dataclasses + ResearchState + ResearchResult + ResearchConfig live in `lib/research/types.py` matching CONTEXT.md verbatim
- `ResearchConfig.from_env()` reads all documented env vars at construction time only (Axis 3)
- `lib/research/__init__.py` exports exactly 7 public names
- `pyproject.toml` declares `omnigraph.research` namespace mapping (LIB-09 option a)
- `scripts/check_contract.sh` enforces CONTRACT-01 + CONTRACT-02
- `lib/research/README.md` documents the packaging choice + CONTRACT checklist
- ≥18 unit tests pass (≥9 for types, ≥9 for config)
- Zero violations of CONTRACT-01 + CONTRACT-02 grep hooks
</success_criteria>

<output>
After completion, create `.planning/phases/ar-1-mvp-vertical-slice/ar-1-01-SUMMARY.md` documenting:
- Files created (count + list)
- Test count + pass status (`pytest tests/unit/research/ -v` output excerpt)
- CONTRACT-01 + CONTRACT-02 grep enforcement result
- pyproject.toml diff (new top-level keys added; existing keys preserved)
- LIB-09 resolution: physical `lib/research/` + declared `omnigraph.research` mapping live
- Any deviations from plan (with reason)
</output>
