---
phase: ar-3-verifier-web-tools
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/research/tools/__init__.py
  - lib/research/tools/web_search.py
  - lib/research/config.py
  - tests/unit/research/test_web_tools.py
autonomous: true
status: planned
last_updated: "2026-05-23"
requirements:
  - TOOL-01
  - TOOL-02
  - TEST-02
  - CONFIG-03

must_haves:
  truths:
    - "tavily_search(query, *, api_key, top_k=10) issues POST https://api.tavily.com/search and returns list[dict] with keys {title, url, content, score}; raises on non-2xx / timeout / parse error (TOOL-01)"
    - "tavily_extract(url, *, api_key) issues POST https://api.tavily.com/extract and returns the extracted content as str; raises on non-2xx / timeout / parse error (TOOL-01)"
    - "brave_search(query, *, api_key, top_k=10) issues GET https://api.search.brave.com/res/v1/web/search with header X-Subscription-Token=<api_key> and returns list[dict] with keys {title, url, content}; raises on error (TOOL-02)"
    - "make_web_search_with_fallback(primary, fallback) returns a single async callable: invokes primary; on ANY exception invokes fallback exactly once; per-call independent (failure on call N does NOT disable primary on call N+1) (TOOL-02 cascade semantics)"
    - "When TAVILY_API_KEY is set, ResearchConfig.from_env() binds cfg.web_search = functools.partial(tavily_search, api_key=...) and cfg.web_extract = functools.partial(tavily_extract, api_key=...) (CONFIG-03 Wave-1 half)"
    - "When BRAVE_SEARCH_API_KEY is set, cfg.web_search_fallback = functools.partial(brave_search, api_key=...) (regardless of Tavily presence — exposed for observability)"
    - "When BOTH TAVILY_API_KEY and BRAVE_SEARCH_API_KEY are set, cfg.web_search = make_web_search_with_fallback(tavily_partial, brave_partial) (cascade-wrapped) — Verifier loop calls cfg.web_search and gets free fallback"
    - "When TAVILY_API_KEY is unset, cfg.web_search remains the ar-1 _skipped_web_search stub regardless of BRAVE_SEARCH_API_KEY (cascade requires both ends — primary gating)"
    - "When TAVILY_API_KEY is unset, cfg.web_extract is None (the dataclass declares it Optional)"
    - "TEST-02 mock-based fallback: cfg.web_search invocation calls mocked Tavily once + mocked Brave once; returns Brave's mock output verbatim (cascade does NOT merge)"
    - "TEST-02 negative case: Tavily mock succeeds → Brave mock never called (zero calls)"
    - "TEST-02 per-call independence: second invocation of cfg.web_search calls Tavily mock again — failure on call 1 does NOT disable primary for call 2"
  artifacts:
    - path: "lib/research/tools/__init__.py"
      provides: "Submodule re-exports — tavily_search, tavily_extract, brave_search, make_web_search_with_fallback"
      contains: "from .web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback; __all__"
    - path: "lib/research/tools/web_search.py"
      provides: "Live HTTP web-tool callables (Tavily search + extract, Brave search) and the cascade wrapper factory"
      contains: "async def tavily_search, async def tavily_extract, async def brave_search, def make_web_search_with_fallback"
    - path: "lib/research/config.py"
      provides: "from_env() reads TAVILY_API_KEY + BRAVE_SEARCH_API_KEY and wires the cascade — drops _skipped_web_search when keys present"
      contains: "import functools, three-way conditional binding for cfg.web_search, separate binding for cfg.web_search_fallback / cfg.web_extract"
    - path: "tests/unit/research/test_web_tools.py"
      provides: "Mock-based unit tests for the 3 HTTP callables, the cascade wrapper, and from_env() integration"
      contains: "test_tavily_search_returns_list_of_dicts, test_tavily_extract_returns_str, test_brave_search_returns_list_of_dicts, test_cascade_calls_primary_only_on_success, test_cascade_falls_back_exactly_once_on_primary_exception, test_cascade_per_call_independence, test_from_env_no_keys_uses_skipped_stub, test_from_env_tavily_only_uses_tavily_no_fallback, test_from_env_both_keys_wraps_with_cascade"
  key_links:
    - from: "lib/research/tools/web_search.py"
      to: "https://api.tavily.com/search and https://api.tavily.com/extract"
      via: "httpx.AsyncClient POST with api_key in JSON body, timeout=15.0"
      pattern: "api\\.tavily\\.com"
    - from: "lib/research/tools/web_search.py"
      to: "https://api.search.brave.com/res/v1/web/search"
      via: "httpx.AsyncClient GET with X-Subscription-Token header, timeout=15.0"
      pattern: "api\\.search\\.brave\\.com"
    - from: "lib/research/config.py"
      to: "lib/research/tools/web_search.py"
      via: "from .tools.web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback"
      pattern: "from \\.tools\\.web_search import"
    - from: "lib/research/config.py"
      to: "os.environ['TAVILY_API_KEY'] and os.environ['BRAVE_SEARCH_API_KEY']"
      via: "os.environ.get(...) inside from_env() — read once at config construction (Axis 3)"
      pattern: "TAVILY_API_KEY|BRAVE_SEARCH_API_KEY"
---

<objective>
Wave 1 of ar-3 builds the **web-tool primitives**: three live HTTP callables (Tavily search, Tavily extract, Brave search) plus a cascade wrapper that gives the Verifier a single `cfg.web_search(query)` callable transparently backed by Tavily-primary + Brave-fallback. Wave 1 also touches `from_env()` — the Wave-1 half of CONFIG-03 — so the new env vars (`TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`) are actually read and the cascade is wired into `ResearchConfig.web_search` / `web_search_fallback` / `web_extract`.

Purpose:
- **TOOL-01** — Tavily REST integration: two callables (`tavily_search` for query results, `tavily_extract` for full-page extraction). Both async, both raise on any failure (the cascade wrapper handles retry).
- **TOOL-02** — Brave fallback: one callable (`brave_search`) plus the cascade factory `make_web_search_with_fallback` that pairs primary + fallback into a single async callable with strict "exactly-once-per-primary-failure" semantics and per-call independence.
- **TEST-02** — Mock-based fallback test (no live HTTP): Tavily mock raises, Brave mock returns results, cascade returns Brave's output exactly; per-call independence verified by a second invocation that calls Tavily again.
- **CONFIG-03 (Wave-1 half)** — `from_env()` reads two new env vars and wires the cascade. The Vertex Grounding auto-detect half lands in Wave 3 (ar-3-03).

Output:
- One new submodule: `lib/research/tools/__init__.py` (~15 LOC re-export shim) + `lib/research/tools/web_search.py` (~150 LOC: 3 HTTP callables + cascade factory).
- One file modified: `lib/research/config.py` (~25 LOC added: imports + key-conditional binding for `cfg.web_search`, `web_search_fallback`, `web_extract`).
- One new test file: `tests/unit/research/test_web_tools.py` (≥9 tests — 3 callable-shape, 3 cascade-behavior, 3 from_env-integration).
- ar-1 + ar-2 regression suite still green; full `tests/unit/research/` count after Wave 1 ≥ 88 baseline + ≥9 new = ≥97.

This plan does NOT touch the Verifier (Wave 2 owns that), the Reasoner, the orchestrator, the CLI, the dataclasses, or any stage. It does NOT introduce Vertex Grounding (Wave 3). It does NOT add new env vars beyond the two already-documented `TAVILY_API_KEY` / `BRAVE_SEARCH_API_KEY`.

The HTTP client is `httpx.AsyncClient` — already a transitive dependency via existing requirements. No new top-level deps.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/ROADMAP-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/config.py
@lib/research/stages/retriever.py
@scripts/check_contract.sh

<interfaces>
**`ResearchConfig` dataclass slots (from `lib/research/types.py`, UNCHANGED):**

```python
@dataclass(frozen=True)
class ResearchConfig:
    rag_working_dir: Path
    llm_complete: Callable
    embedding_func: Callable
    vision_cascade: object
    web_search: Callable[[str], list[dict]]                  # ar-3 Wave 1 wires Tavily primary OR cascade
    web_search_fallback: Callable[[str], list[dict]] | None = None  # ar-3 Wave 1 wires Brave when key set
    web_extract: Callable[[str], str] | None = None          # ar-3 Wave 1 wires Tavily extract when key set
    google_search_grounding: Callable | None = None          # ar-3 Wave 3 wires Vertex Grounding
    output_dir: Path | None = None
    telemetry_jsonl: Path | None = None
    max_iter_reasoner: int = 5
    max_iter_verifier: int = 3
```

**Three HTTP callables (NEW in `lib/research/tools/web_search.py`):**

```python
async def tavily_search(
    query: str,
    *,
    api_key: str,
    top_k: int = 10,
) -> list[dict]:
    """POST https://api.tavily.com/search with body
    {"api_key": api_key, "query": query, "max_results": top_k, "search_depth": "basic"}.
    Returns list[dict] of {"title": str, "url": str, "content": str, "score": float}.
    Raises httpx.HTTPError / TimeoutException / ValueError on any failure.
    Timeout: 15.0s (hardcoded — no env override per CONTEXT § Configuration).
    """

async def tavily_extract(
    url: str,
    *,
    api_key: str,
) -> str:
    """POST https://api.tavily.com/extract with body
    {"api_key": api_key, "urls": [url]}.
    Returns the extracted markdown content as a single str (joins multi-result responses).
    Raises on any failure.
    Timeout: 15.0s.
    """

async def brave_search(
    query: str,
    *,
    api_key: str,
    top_k: int = 10,
) -> list[dict]:
    """GET https://api.search.brave.com/res/v1/web/search?q=<query>&count=<top_k>
    with header X-Subscription-Token: <api_key>.
    Returns list[dict] of {"title": str, "url": str, "content": str}.
    Raises on any failure. Timeout: 15.0s.
    """
```

**Cascade factory (NEW in `lib/research/tools/web_search.py`):**

```python
def make_web_search_with_fallback(
    primary: Callable[[str], Awaitable[list[dict]]],
    fallback: Callable[[str], Awaitable[list[dict]]] | None,
) -> Callable[[str], Awaitable[list[dict]]]:
    """Returns a single async callable that:
      1. Invokes primary(query)
      2. On ANY exception from primary, invokes fallback(query) exactly once
      3. Whatever fallback returns (or raises) is returned/raised by the wrapper
      4. If fallback is None and primary raises, the exception propagates
    Per-call independence: failure on call N does NOT disable primary for call N+1.
    No retry of primary. No retry of fallback. The Verifier loop may decide to
    retry the cascade as a whole on subsequent iterations — that is loop-level
    retry, not cascade-level retry.
    """
```

**`from_env()` wiring (modifications to `lib/research/config.py`):**

The current ar-1 stub-mode block (lines 50-58 of `config.py`):

```python
if os.environ.get("TAVILY_API_KEY"):
    web_search = _skipped_web_search
else:
    web_search = _skipped_web_search
web_search_fallback = None
web_extract = None
```

Becomes:

```python
import functools
from .tools.web_search import (
    tavily_search,
    tavily_extract,
    brave_search,
    make_web_search_with_fallback,
)

tavily_key = os.environ.get("TAVILY_API_KEY")
brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")

# Brave fallback callable (exposed regardless of Tavily — observability slot)
if brave_key:
    web_search_fallback = functools.partial(brave_search, api_key=brave_key)
else:
    web_search_fallback = None

# Tavily extract callable (only when Tavily key present)
if tavily_key:
    web_extract = functools.partial(tavily_extract, api_key=tavily_key)
else:
    web_extract = None

# Three-way primary cascade for web_search:
#   - both keys → cascade-wrapped Tavily+Brave
#   - Tavily only → bare Tavily partial (no fallback)
#   - neither (or Brave-only) → ar-1 _skipped_web_search stub
if tavily_key and brave_key:
    web_search = make_web_search_with_fallback(
        functools.partial(tavily_search, api_key=tavily_key),
        functools.partial(brave_search, api_key=brave_key),
    )
elif tavily_key:
    web_search = functools.partial(tavily_search, api_key=tavily_key)
else:
    web_search = _skipped_web_search
```

The rest of `from_env()` is unchanged.

**`lib/research/tools/__init__.py` — re-export shim:**

```python
"""Web-tool callables for the Verifier stage agent loop.

Submodule layout (subject to extension in ar-4):
  - web_search.py — Tavily search/extract, Brave fallback, cascade factory
"""
from __future__ import annotations

from .web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
)

__all__ = [
    "brave_search",
    "make_web_search_with_fallback",
    "tavily_extract",
    "tavily_search",
]
```

**Hard rules (verbatim from CONTEXT.md § TOOL-01 / TOOL-02):**

1. HTTP timeouts hardcoded at **15.0s** per call. NO env override (avoid sprawl).
2. HTTP client: `httpx.AsyncClient` (already in transitive deps; do NOT add new top-level deps).
3. Cascade semantics — "exactly once per primary failure": invokes primary; on exception invokes fallback exactly once; whatever fallback returns/raises is returned/raised. NO retry of primary. NO retry of fallback within the wrapper.
4. Per-call independence: a separate cascade invocation on call N+1 calls primary fresh, regardless of call N's outcome.
5. Brave-only (no Tavily): cascade requires both ends — `cfg.web_search` stays the `_skipped_web_search` stub; `cfg.web_search_fallback` MAY still be set for observability (the dataclass slot exists).
6. NO new env vars beyond the two already documented (`TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`).
7. The HTTP-call factories MUST NOT read env vars — keys are bound via `functools.partial` inside `from_env()` and live in the closure of the partial. The hot path (Verifier loop) gets a key-bound callable, never reads env.

**TEST-02 mock harness (verbatim shape — no live HTTP):**

```python
# tests/unit/research/test_web_tools.py
import asyncio
import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lib.research.tools.web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
)


# --- Callable-shape tests (mock httpx) ---

@pytest.mark.asyncio
async def test_tavily_search_returns_list_of_dicts():
    """Mock httpx response; assert tavily_search returns list[dict] with expected keys."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "results": [
            {"title": "T1", "url": "https://e.com/1", "content": "c1", "score": 0.9},
            {"title": "T2", "url": "https://e.com/2", "content": "c2", "score": 0.7},
        ],
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await tavily_search("test query", api_key="fake_key", top_k=10)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(r, dict) for r in result)
    assert result[0]["title"] == "T1"
    assert "url" in result[0]
    assert "content" in result[0]


@pytest.mark.asyncio
async def test_tavily_extract_returns_str():
    """Mock httpx response; assert tavily_extract returns str."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "results": [{"url": "https://e.com/x", "raw_content": "extracted markdown body"}],
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await tavily_extract("https://e.com/x", api_key="fake_key")

    assert isinstance(result, str)
    assert "extracted markdown body" in result


@pytest.mark.asyncio
async def test_brave_search_returns_list_of_dicts():
    """Mock httpx response; assert brave_search returns list[dict]."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "web": {"results": [
            {"title": "B1", "url": "https://e.com/b1", "description": "bc1"},
            {"title": "B2", "url": "https://e.com/b2", "description": "bc2"},
        ]},
    })
    mock_response.raise_for_status = MagicMock()

    with patch("lib.research.tools.web_search.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await brave_search("brave query", api_key="fake_key", top_k=10)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["title"] == "B1"
    assert "url" in result[0]
    assert "content" in result[0]  # brave_search normalizes 'description' → 'content'


# --- Cascade-behavior tests (mock the partials directly — no httpx) ---

@pytest.mark.asyncio
async def test_cascade_calls_primary_only_on_success():
    """When primary succeeds, fallback is never called."""
    primary = AsyncMock(return_value=[{"title": "P", "url": "u", "content": "c"}])
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    result = await cascade("q")

    assert result == [{"title": "P", "url": "u", "content": "c"}]
    assert primary.await_count == 1
    assert fallback.await_count == 0


@pytest.mark.asyncio
async def test_cascade_falls_back_exactly_once_on_primary_exception():
    """When primary raises, fallback is called exactly once and its result is returned."""
    primary = AsyncMock(side_effect=httpx.TimeoutException("primary timed out"))
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    result = await cascade("q")

    assert result == [{"title": "F", "url": "u", "content": "c"}]
    assert primary.await_count == 1
    assert fallback.await_count == 1


@pytest.mark.asyncio
async def test_cascade_per_call_independence():
    """Failure on call N does NOT disable primary for call N+1."""
    # Primary: raises on call 1, succeeds on call 2.
    primary = AsyncMock(side_effect=[
        httpx.TimeoutException("call-1 boom"),
        [{"title": "P2", "url": "u", "content": "c"}],
    ])
    fallback = AsyncMock(return_value=[{"title": "F", "url": "u", "content": "c"}])

    cascade = make_web_search_with_fallback(primary, fallback)
    r1 = await cascade("q1")
    r2 = await cascade("q2")

    assert r1 == [{"title": "F", "url": "u", "content": "c"}]
    assert r2 == [{"title": "P2", "url": "u", "content": "c"}]
    assert primary.await_count == 2  # called fresh each time
    assert fallback.await_count == 1  # only call 1 needed fallback


# --- from_env() integration tests ---

def test_from_env_no_keys_uses_skipped_stub(monkeypatch, tmp_path):
    """Neither TAVILY_API_KEY nor BRAVE_SEARCH_API_KEY set → web_search is _skipped_web_search."""
    from lib.research.config import _skipped_web_search, from_env

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    # Patch lazy imports inside from_env() to avoid touching the real LLM/embedding/vision modules.
    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.web_search is _skipped_web_search
    assert cfg.web_search_fallback is None
    assert cfg.web_extract is None


def test_from_env_tavily_only_uses_tavily_no_fallback(monkeypatch, tmp_path):
    """TAVILY_API_KEY set, BRAVE_SEARCH_API_KEY unset → cfg.web_search is bare Tavily partial."""
    import functools

    from lib.research.config import from_env
    from lib.research.tools.web_search import tavily_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly_test_key")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    # web_search is a functools.partial of tavily_search bound to api_key
    assert isinstance(cfg.web_search, functools.partial)
    assert cfg.web_search.func is tavily_search
    assert cfg.web_search.keywords == {"api_key": "tvly_test_key"}
    assert cfg.web_search_fallback is None  # Brave key unset
    assert cfg.web_extract is not None      # Tavily extract bound


def test_from_env_both_keys_wraps_with_cascade(monkeypatch, tmp_path):
    """Both keys set → cfg.web_search is the cascade wrapper (not a bare partial)."""
    import functools

    from lib.research.config import from_env
    from lib.research.tools.web_search import tavily_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly_test_key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave_test_key")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    # web_search is the cascade wrapper, NOT a bare functools.partial of tavily_search
    assert not (isinstance(cfg.web_search, functools.partial) and cfg.web_search.func is tavily_search)
    # web_search_fallback is the bare Brave partial (observability slot)
    assert cfg.web_search_fallback is not None
    assert isinstance(cfg.web_search_fallback, functools.partial)
    # web_extract is the bare Tavily extract partial
    assert cfg.web_extract is not None
```

The tests use `monkeypatch.setenv` / `monkeypatch.delenv` for env isolation and `unittest.mock.patch` for the lazy imports inside `from_env()` (LLM provider, embedding func, vision cascade). The tests do NOT make real HTTP calls — `httpx.AsyncClient` is patched in the callable-shape tests; the cascade tests mock primary/fallback directly with `AsyncMock`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create lib/research/tools/__init__.py + lib/research/tools/web_search.py with 3 HTTP callables and cascade factory</name>
  <read_first>
    - lib/research/types.py (ResearchConfig dataclass — confirm web_search / web_search_fallback / web_extract slot signatures; do NOT modify)
    - lib/research/config.py (current ar-1 _skipped_web_search stub — preserves the public name; still imported in Wave 2 + the test)
    - lib/research/stages/retriever.py (existing async-call style reference for httpx-style awaits — though retriever uses omnigraph_search not httpx)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TOOL-01" + § "TOOL-02" (verbatim cascade semantics)
    - requirements.txt (confirm httpx is already present transitively or as a top-level — if missing, see "Hard rules" #2 below)
  </read_first>
  <files>lib/research/tools/__init__.py, lib/research/tools/web_search.py</files>
  <behavior>
    `lib/research/tools/web_search.py` MUST satisfy:
    - `tavily_search(query, *, api_key, top_k=10) -> list[dict]` calls POST `https://api.tavily.com/search` with body `{"api_key": api_key, "query": query, "max_results": top_k, "search_depth": "basic"}`, parses `response.json()["results"]`, normalizes each entry to `{"title", "url", "content", "score"}` shape, returns the list. Raises on non-2xx (`response.raise_for_status()`), on `httpx.TimeoutException`, or on JSON parse error.
    - `tavily_extract(url, *, api_key) -> str` calls POST `https://api.tavily.com/extract` with body `{"api_key": api_key, "urls": [url]}`, parses `response.json()["results"]`, joins each result's `raw_content` with `"\n\n"` and returns the resulting str. Raises on error.
    - `brave_search(query, *, api_key, top_k=10) -> list[dict]` calls GET `https://api.search.brave.com/res/v1/web/search?q=<urlencoded query>&count=<top_k>` with header `X-Subscription-Token: <api_key>`, parses `response.json()["web"]["results"]`, normalizes each entry: map `description` → `content` so the returned dict shape matches Tavily's (caller doesn't care which provider). Raises on error.
    - `make_web_search_with_fallback(primary, fallback) -> Callable` returns an async wrapper that: invokes primary; on ANY exception invokes fallback exactly once; if fallback is None and primary raises, the exception propagates. Per-call independent (each invocation is fresh — no global state, no closure flag).
    - All three HTTP callables use `httpx.AsyncClient(timeout=15.0)` inside an `async with` block. Timeout is hardcoded 15.0s. No env override.
    - Module body contains NO `os.environ` reads (env reads live exclusively in `config.py:from_env()` per Axis 3).
    - Module body contains NO `~/.hermes` / `omonigraph-vault` literals (CONTRACT-02).
    - Module body contains NO `omnigraph_search.*` imports (CONTRACT-01 — web tools have no KG access by design).

    `lib/research/tools/__init__.py` MUST satisfy:
    - Re-exports the four public names: `tavily_search`, `tavily_extract`, `brave_search`, `make_web_search_with_fallback`.
    - Defines `__all__ = ["brave_search", "make_web_search_with_fallback", "tavily_extract", "tavily_search"]`.
  </behavior>
  <action>
    1. Create directory `lib/research/tools/` if it does not exist.

    2. Create `lib/research/tools/__init__.py` with the verbatim re-export shim from `<interfaces>` § "lib/research/tools/__init__.py — re-export shim".

    3. Create `lib/research/tools/web_search.py`. Module docstring:
       ```python
       """Web-tool callables for the Verifier stage agent loop.

       Three live HTTP callables + a cascade factory:
         - tavily_search(query, *, api_key, top_k) → list[dict]   (TOOL-01 search)
         - tavily_extract(url, *, api_key) → str                  (TOOL-01 extract)
         - brave_search(query, *, api_key, top_k) → list[dict]    (TOOL-02 fallback)
         - make_web_search_with_fallback(primary, fallback)       (TOOL-02 cascade)

       Hardcoded 15.0s timeout per call. No env reads in this module — keys are
       bound via functools.partial in from_env() (Axis 3).
       """
       ```

    4. Imports — keep minimal:
       ```python
       from __future__ import annotations

       from typing import Awaitable, Callable
       from urllib.parse import urlencode

       import httpx
       ```
       NO `os`, NO `omnigraph_search.*`, NO `lib.research.types` (web tools are agnostic of dataclass shapes; they return raw `list[dict]` / `str`).

    5. Implement `tavily_search`:
       ```python
       _TAVILY_TIMEOUT_S = 15.0

       async def tavily_search(
           query: str,
           *,
           api_key: str,
           top_k: int = 10,
       ) -> list[dict]:
           body = {
               "api_key": api_key,
               "query": query,
               "max_results": top_k,
               "search_depth": "basic",
           }
           async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
               response = await client.post(
                   "https://api.tavily.com/search", json=body
               )
               response.raise_for_status()
               data = response.json()
           # Normalize: ensure list of dicts with the four required keys
           results = data.get("results", [])
           return [
               {
                   "title": str(r.get("title", "")),
                   "url": str(r.get("url", "")),
                   "content": str(r.get("content", "")),
                   "score": float(r.get("score", 0.0)),
               }
               for r in results
           ]
       ```

    6. Implement `tavily_extract`:
       ```python
       async def tavily_extract(
           url: str,
           *,
           api_key: str,
       ) -> str:
           body = {"api_key": api_key, "urls": [url]}
           async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
               response = await client.post(
                   "https://api.tavily.com/extract", json=body
               )
               response.raise_for_status()
               data = response.json()
           results = data.get("results", [])
           return "\n\n".join(str(r.get("raw_content", "")) for r in results)
       ```

    7. Implement `brave_search`:
       ```python
       async def brave_search(
           query: str,
           *,
           api_key: str,
           top_k: int = 10,
       ) -> list[dict]:
           params = urlencode({"q": query, "count": top_k})
           url = f"https://api.search.brave.com/res/v1/web/search?{params}"
           headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
           async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
               response = await client.get(url, headers=headers)
               response.raise_for_status()
               data = response.json()
           web_results = data.get("web", {}).get("results", [])
           # Normalize: map Brave's 'description' → 'content' so callers see the same shape.
           return [
               {
                   "title": str(r.get("title", "")),
                   "url": str(r.get("url", "")),
                   "content": str(r.get("description", "")),
               }
               for r in web_results
           ]
       ```

    8. Implement `make_web_search_with_fallback`:
       ```python
       def make_web_search_with_fallback(
           primary: Callable[..., Awaitable[list[dict]]],
           fallback: Callable[..., Awaitable[list[dict]]] | None,
       ) -> Callable[..., Awaitable[list[dict]]]:
           async def cascade(query: str) -> list[dict]:
               try:
                   return await primary(query)
               except Exception:  # noqa: BLE001 — cascade-level catch, intentional
                   if fallback is None:
                       raise
                   return await fallback(query)
           return cascade
       ```
       Per-call independence is provided automatically — there is NO module/closure state.
       The `try/except Exception` catch is intentional and documented (cascade-level
       behavior is "swallow primary exception once, attempt fallback once").

    9. Module-level `__all__`:
       ```python
       __all__ = [
           "brave_search",
           "make_web_search_with_fallback",
           "tavily_extract",
           "tavily_search",
       ]
       ```

    10. Smoke import: `venv/Scripts/python.exe -c "from lib.research.tools.web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback; print('OK')"` — must succeed.

    11. Smoke import via package root: `venv/Scripts/python.exe -c "from lib.research.tools import tavily_search, brave_search, make_web_search_with_fallback, tavily_extract; print('OK')"` — must succeed.

    12. CONTRACT-01 audit: `grep -n "omnigraph_search" lib/research/tools/` — expected 0 hits. CONTRACT-02 audit: `grep -nE "/.hermes|omonigraph-vault" lib/research/tools/` — expected 0 hits. `bash scripts/check_contract.sh` — must exit 0.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.tools.web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback; from lib.research.tools import tavily_search as ts2; print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/tools/__init__.py` exists; re-exports the four public names.
    - `lib/research/tools/web_search.py` exists; ≤200 LOC; defines `tavily_search`, `tavily_extract`, `brave_search`, `make_web_search_with_fallback`.
    - `from lib.research.tools.web_search import ...` and `from lib.research.tools import ...` both succeed.
    - Module body contains zero `omnigraph_search.*` imports (CONTRACT-01).
    - Module body contains zero `~/.hermes` / `omonigraph-vault` literals (CONTRACT-02).
    - Module body contains zero `os.environ` references (Axis 3 — env reads only in config.py).
    - `bash scripts/check_contract.sh` exits 0.
    - Module body contains the literal `httpx.AsyncClient(timeout=15.0)` (timeout-hardcoded proof) — or equivalent named constant `_TAVILY_TIMEOUT_S = 15.0` used as `timeout=`.
  </acceptance_criteria>
  <done>web_search.py + tools/__init__.py created; all 4 public callables importable; CONTRACT-01 + CONTRACT-02 still clean; smoke imports pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire web cascade into ResearchConfig.from_env() — drop _skipped_web_search when keys present, expose web_extract + web_search_fallback</name>
  <read_first>
    - lib/research/config.py (current from_env() — Wave 1 modifies the web_search / web_search_fallback / web_extract block ONLY; do NOT touch other env reads)
    - lib/research/tools/web_search.py (just-written — Task 1 dependency)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "CONFIG-03: from_env() updates" (Wave 1 half — TAVILY+BRAVE; Wave 3 adds Vertex auto-detect)
  </read_first>
  <files>lib/research/config.py</files>
  <behavior>
    `from_env()` MUST satisfy after this task:
    - When `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY` are BOTH unset: `cfg.web_search is _skipped_web_search`, `cfg.web_search_fallback is None`, `cfg.web_extract is None`.
    - When `TAVILY_API_KEY` is set and `BRAVE_SEARCH_API_KEY` is unset: `cfg.web_search` is a `functools.partial` of `tavily_search` with `api_key=<value>`; `cfg.web_search_fallback is None`; `cfg.web_extract` is a `functools.partial` of `tavily_extract` with `api_key=<value>`.
    - When `BRAVE_SEARCH_API_KEY` is set and `TAVILY_API_KEY` is unset: `cfg.web_search is _skipped_web_search` (cascade requires both ends — primary gating); `cfg.web_search_fallback` is a `functools.partial` of `brave_search` (still exposed for observability per CONTEXT § TOOL-02); `cfg.web_extract is None`.
    - When BOTH keys are set: `cfg.web_search` is the cascade wrapper from `make_web_search_with_fallback(tavily_partial, brave_partial)`; `cfg.web_search_fallback` is the bare Brave partial; `cfg.web_extract` is the bare Tavily extract partial.
    - The rest of `from_env()` (rag_working_dir, llm_complete, embedding_func, vision_cascade, output_dir, telemetry_jsonl, max_iter_*) is BYTE-FOR-BYTE UNCHANGED.
    - `_skipped_web_search` symbol stays exported (it's used as the unset-keys sentinel + the Wave 3 grep test asserts identity).
  </behavior>
  <action>
    1. Open `lib/research/config.py`. Add `import functools` to the import block (alphabetized — between `import os` and `from pathlib import Path`).

    2. Add a NEW import block AFTER the existing `from .types import ResearchConfig` line:
       ```python
       from .tools.web_search import (
           brave_search,
           make_web_search_with_fallback,
           tavily_extract,
           tavily_search,
       )
       ```

    3. Replace the current ar-1 stub block (current lines 50-58 of `config.py` — the `if os.environ.get("TAVILY_API_KEY"): web_search = _skipped_web_search else: web_search = _skipped_web_search ; web_search_fallback = None ; web_extract = None ; google_search_grounding = None`):
       - DROP the dead-branch `if/else` (both branches assigned the same stub — that was the ar-1 placeholder).
       - REPLACE with the three-way cascade wiring from `<interfaces>` § "from_env() wiring":
       ```python
       tavily_key = os.environ.get("TAVILY_API_KEY")
       brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")

       # Brave fallback callable — exposed regardless of Tavily presence (observability slot).
       if brave_key:
           web_search_fallback = functools.partial(brave_search, api_key=brave_key)
       else:
           web_search_fallback = None

       # Tavily extract callable — only when Tavily key set.
       if tavily_key:
           web_extract = functools.partial(tavily_extract, api_key=tavily_key)
       else:
           web_extract = None

       # Three-way cascade for web_search:
       #   - both keys → cascade-wrapped Tavily+Brave
       #   - Tavily only → bare Tavily partial
       #   - neither (or Brave-only) → ar-1 _skipped_web_search stub (cascade requires both ends)
       if tavily_key and brave_key:
           web_search = make_web_search_with_fallback(
               functools.partial(tavily_search, api_key=tavily_key),
               functools.partial(brave_search, api_key=brave_key),
           )
       elif tavily_key:
           web_search = functools.partial(tavily_search, api_key=tavily_key)
       else:
           web_search = _skipped_web_search

       google_search_grounding = None  # Wave 3 wires Vertex auto-detect
       ```

    4. The `ResearchConfig(...)` constructor call at the bottom of `from_env()` is UNCHANGED — same 12 keyword args.

    5. CONTRACT-02 audit on the modified file: `grep -nE "/.hermes|omonigraph-vault" lib/research/config.py | grep -v "omonigraph-vault'  # 'omonigraph' typo is canonical"` — only the existing `~/.hermes/omonigraph-vault` default-path literal stays (that's the canonical typo per CLAUDE.md and is allowed by `check_contract.sh` — it's the SOLE allow-listed file).

    6. CONTRACT-01 audit: `grep -n "omnigraph_search" lib/research/config.py` — expected 0 hits.

    7. Smoke import: `venv/Scripts/python.exe -c "from lib.research.config import from_env, _skipped_web_search; print('OK')"` — must succeed.

    8. Run `bash scripts/check_contract.sh` — must exit 0.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.config import from_env, _skipped_web_search; print('OK')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/config.py` imports `functools`, `tavily_search`, `tavily_extract`, `brave_search`, `make_web_search_with_fallback`.
    - The ar-1 dead-branch `if os.environ.get("TAVILY_API_KEY"): web_search = _skipped_web_search else: web_search = _skipped_web_search` is gone (replaced).
    - The new three-way conditional binding for `web_search` is present (verified by literal `make_web_search_with_fallback(` substring in the file).
    - `web_extract` and `web_search_fallback` are conditionally bound by their own respective key checks.
    - `_skipped_web_search` symbol still exists in the module (stays as the unset-keys sentinel).
    - `bash scripts/check_contract.sh` exits 0.
    - Smoke import succeeds.
  </acceptance_criteria>
  <done>from_env() reads TAVILY+BRAVE keys, wires the cascade, exposes web_extract; ar-1 dead-branch dropped; CONTRACT-01 + CONTRACT-02 still clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Write TEST-02 + TOOL-01/02 + CONFIG-03 Wave-1 mock test suite (≥9 tests) and verify ar-1+ar-2 regression suite still green</name>
  <read_first>
    - tests/unit/research/test_config.py (existing ar-1 from_env() test patterns — monkeypatch + lazy-import patches)
    - tests/unit/research/test_stages_stubs.py (mock setup conventions for ResearchConfig)
    - lib/research/tools/web_search.py (just-written — gives test the exact callable shapes to mock)
    - lib/research/config.py (just-modified — gives test the exact env var names and the binding shapes)
    - .planning/phases/ar-3-verifier-web-tools/ar-3-CONTEXT.md § "TEST-02: Brave fallback mock test" (verbatim assertions)
    - pyproject.toml § `[tool.pytest.ini_options]` (confirm `asyncio_mode = "auto"`)
  </read_first>
  <files>tests/unit/research/test_web_tools.py</files>
  <behavior>
    Test file `test_web_tools.py` covers ≥9 tests:

    Group 1 — Callable-shape (3 tests, mocking `httpx.AsyncClient`):
    - `test_tavily_search_returns_list_of_dicts` — mock httpx returns Tavily-shaped JSON; assert `tavily_search` returns `list[dict]` with `{title, url, content, score}` keys.
    - `test_tavily_extract_returns_str` — mock httpx returns Tavily extract-shaped JSON; assert `tavily_extract` returns str containing the mocked raw_content.
    - `test_brave_search_returns_list_of_dicts` — mock httpx returns Brave-shaped JSON (with `description` key); assert `brave_search` returns `list[dict]` with `description` normalized to `content`.

    Group 2 — Cascade behavior (3 tests, mocking the partials directly):
    - `test_cascade_calls_primary_only_on_success` — primary returns; fallback never called (TEST-02 negative case).
    - `test_cascade_falls_back_exactly_once_on_primary_exception` — primary raises `httpx.TimeoutException`; fallback called exactly once; cascade returns fallback's output verbatim (TEST-02 positive case).
    - `test_cascade_per_call_independence` — primary raises on call 1, succeeds on call 2; primary's `await_count == 2`, fallback's `await_count == 1` (TEST-02 per-call independence).

    Group 3 — `from_env()` integration (3 tests, monkeypatched env + lazy-import patches):
    - `test_from_env_no_keys_uses_skipped_stub` — neither key set; `cfg.web_search is _skipped_web_search`; `cfg.web_search_fallback is None`; `cfg.web_extract is None`.
    - `test_from_env_tavily_only_uses_tavily_no_fallback` — Tavily key set, Brave unset; `cfg.web_search` is bare `functools.partial(tavily_search, api_key=...)`; `cfg.web_search_fallback is None`; `cfg.web_extract` is bound.
    - `test_from_env_both_keys_wraps_with_cascade` — both keys set; `cfg.web_search` is the cascade wrapper (NOT a bare `functools.partial` of `tavily_search`); `cfg.web_search_fallback` is the bare Brave partial; `cfg.web_extract` is the bare Tavily extract partial.

    All tests use mocks — NO live HTTP. Tests are independent (fresh mocks, fresh env per test via monkeypatch).
  </behavior>
  <action>
    1. Create `tests/unit/research/test_web_tools.py`. Imports:
       ```python
       import asyncio
       import functools
       from unittest.mock import AsyncMock, MagicMock, patch

       import httpx
       import pytest

       from lib.research.tools.web_search import (
           brave_search,
           make_web_search_with_fallback,
           tavily_extract,
           tavily_search,
       )
       ```

    2. Implement Group 1 callable-shape tests (3 tests). Pattern: patch `lib.research.tools.web_search.httpx.AsyncClient` to return an async context-manager mock whose `.post` (or `.get` for Brave) returns a `MagicMock` with `status_code=200`, `raise_for_status` no-op, `.json()` returning the canonical provider response shape. Verbatim shapes from `<interfaces>` § "TEST-02 mock harness".

    3. Implement Group 2 cascade-behavior tests (3 tests). Mock primary + fallback as `AsyncMock` directly — no `httpx` involvement. The cascade factory's logic is verified end-to-end by counting `await_count` on each mock and inspecting the returned value.

    4. Implement Group 3 from_env() integration tests (3 tests). Pattern:
       ```python
       def test_from_env_<scenario>(monkeypatch, tmp_path):
           # Set / unset env vars
           monkeypatch.setenv("TAVILY_API_KEY", "tvly_test_key")  # or delenv
           monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

           # Patch lazy imports inside from_env() (they touch real LLM/embedding/vision modules
           # that are slow / require auth — use mocks for unit-test speed)
           with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
                patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
                patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
               from lib.research.config import from_env, _skipped_web_search
               cfg = from_env()

           # Assertions per scenario
       ```

    5. The test for "tavily-only uses tavily no fallback" specifically asserts:
       ```python
       assert isinstance(cfg.web_search, functools.partial)
       assert cfg.web_search.func is tavily_search
       assert cfg.web_search.keywords == {"api_key": "tvly_test_key"}
       ```
       This pins the exact wrapping (a bare partial, NOT the cascade) so a future regression where someone wraps the partial unconditionally will be caught.

    6. The test for "both keys wraps with cascade" specifically asserts the OPPOSITE — `cfg.web_search` is NOT a bare `functools.partial` of `tavily_search`:
       ```python
       is_bare_tavily_partial = (
           isinstance(cfg.web_search, functools.partial)
           and cfg.web_search.func is tavily_search
       )
       assert not is_bare_tavily_partial, (
           "When both keys are set, cfg.web_search should be the cascade wrapper, not a bare Tavily partial"
       )
       ```
       It does not pin the exact callable identity (the cascade wrapper is a closure with no stable `__name__`); the negative assertion is sufficient.

    7. Run the new test file in isolation FIRST: `venv/Scripts/python.exe -m pytest tests/unit/research/test_web_tools.py -v`. All 9 must pass.

    8. Then run the full ar-1 + ar-2 + ar-3 Wave 1 regression suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total test count must be `≥ 88 (ar-1+ar-2 baseline) + 9 (this plan) = ≥ 97`.

    9. If ANY ar-1/ar-2 test fails, STOP and audit the diff. The most likely regression source is `test_config.py` if it asserted on the OLD ar-1 dead-branch shape (`cfg.web_search is _skipped_web_search` regardless of TAVILY_API_KEY). If so, the surgical fix is in `test_config.py`: any test that pre-set `TAVILY_API_KEY` and asserted `cfg.web_search is _skipped_web_search` MUST be updated to either (a) `delenv("TAVILY_API_KEY")` first (preserving the assertion) or (b) `assert isinstance(cfg.web_search, functools.partial)` (reflecting the new behavior). Document any such update in SUMMARY.md.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_web_tools.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_web_tools.py` exists with ≥9 tests; all pass.
    - Test names match the spec: 3 callable-shape, 3 cascade-behavior, 3 from_env-integration.
    - The cascade fallback test specifically asserts `primary.await_count == 1` AND `fallback.await_count == 1` AND the returned value equals fallback's mock output (TEST-02 hard requirements).
    - The cascade per-call-independence test specifically asserts `primary.await_count == 2` after two cascade invocations (TEST-02 independence requirement).
    - The from_env-tavily-only test specifically asserts `cfg.web_search.func is tavily_search` AND `cfg.web_search_fallback is None` (CONFIG-03 Wave-1 partial-binding requirement).
    - The from_env-both-keys test specifically asserts `not (isinstance(cfg.web_search, functools.partial) and cfg.web_search.func is tavily_search)` (cascade-wrapping requirement).
    - Full `tests/unit/research/` suite has ≥97 tests passing (ar-1+ar-2 baseline ≥88 + Wave 1 ≥9).
    - Any `test_config.py` edits are SURGICAL (≤10 line diffs total) and documented in SUMMARY.md.
  </acceptance_criteria>
  <done>≥9 new web-tool tests pass; full ar-1+ar-2 regression suite still green (≥97 total tests); test_config.py edits surgical if needed.</done>
</task>

</tasks>

<verification>
- All three tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥97 tests passing.
- CONTRACT-01 grep re-check (must return zero forbidden hits — Wave 1 adds zero `omnigraph_search.*` imports anywhere in `lib/research/tools/`):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ \
    --include='*.py' \
    | grep -vE "from omnigraph_search\.query " \
    | grep -vE "from omnigraph_search\.query$" \
    | grep -vE "import omnigraph_search\.query" \
    || true) && \
  if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
  ```
  Expected: 0 hits. (Existing 2 allowed lines from retriever.py + reasoner.py are filtered by the exclusion list; no new lines added.)
- CONTRACT-02 grep re-check (web_search.py must contain ZERO `~/.hermes` / `omonigraph-vault` literals):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits.
- `bash scripts/check_contract.sh` exits 0.
- Smoke import paths:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -c "
  from lib.research.tools.web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback
  from lib.research.tools import tavily_search as t2
  from lib.research.config import from_env, _skipped_web_search
  import inspect
  assert inspect.iscoroutinefunction(tavily_search)
  assert inspect.iscoroutinefunction(tavily_extract)
  assert inspect.iscoroutinefunction(brave_search)
  print('All Wave 1 imports OK')
  "
  ```
- Layer 2 smoke (cap=0 LLM-free CLI smoke remains the Wave 3 owner — Wave 1 does NOT exercise the upgraded smoke. The Wave 1 verification is purely the Layer 1 pytest above.)
</verification>

<success_criteria>
- ROADMAP § "Phase ar-3: Verifier + web tools" Success Criterion #1 (Verifier real loop): NOT delivered by Wave 1 — that's Wave 2's job.
- ROADMAP Success Criterion #2 (cfg.web_search live Tavily callable when TAVILY_API_KEY set): ✓ delivered by Tasks 1+2 (`functools.partial(tavily_search, api_key=...)` is the live callable).
- ROADMAP Success Criterion #3 (cfg.web_search_fallback live Brave callable invoked exactly once per primary failure, verified by mock test): ✓ delivered by Tasks 1+2+3 (cascade factory + TEST-02 mock test).
- ROADMAP Success Criterion #4 (Vertex Grounding auto-detect): NOT delivered by Wave 1 — that's Wave 3's job.
- ROADMAP Success Criterion #5 (cap tests for both loops): NOT delivered by Wave 1 — Wave 2 owns Verifier-half, Wave 3 owns Reasoner-half.
- REQ TOOL-01 (Tavily search + extract callables) ✓ delivered by Task 1.
- REQ TOOL-02 (Brave fallback callable + cascade factory) ✓ delivered by Task 1.
- REQ TEST-02 (mock-based fallback test) ✓ delivered by Task 3 (cascade-behavior group).
- REQ CONFIG-03 Wave-1 half (TAVILY+BRAVE env reads + cascade wiring) ✓ delivered by Task 2; Vertex auto-detect half lands in Wave 3.
- CONTRACT-01 + CONTRACT-02 still clean.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-3-verifier-web-tools/ar-3-01-SUMMARY.md` documenting:
- Files created + LOC count for each (web_search.py, tools/__init__.py, test_web_tools.py).
- Files modified + diff line count (config.py — should be ~25 lines added, ~3 lines removed for the dead branch).
- Test count: total in `tests/unit/research/test_web_tools.py`, total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (paste raw output — should be 0 forbidden hits).
- Any `test_config.py` surgical updates: list each test edited with line-count delta and one-line rationale (e.g., "test had pre-set TAVILY_API_KEY and asserted skipped_stub — added monkeypatch.delenv to preserve original intent").
- Any deviations from plan with one-line rationale — particularly: (a) whether the executor used `httpx.AsyncClient` per-call or introduced a shared session (per-call is the planner default — see Planner-flagged ambiguities below); (b) whether Tavily / Brave response normalization differed from the spec'd shape; (c) whether the cascade factory's exception type is `Exception` or narrower.
- Smoke import checks output (4 imports per § Verification "Smoke import paths").
- Live-key Layer 2b smoke is NOT executed in Wave 1 — defer to phase-close per CONTEXT § Smoke test Layer 2b.
</output>

## Planner-flagged ambiguities

The orchestrator may want to rule on these via plan-checker; the planner has noted defaults below:

1. **`httpx.AsyncClient` per-call vs shared session.** The planner spec uses per-call `async with httpx.AsyncClient(...)` blocks (simpler; one HTTP connection per tool call; no lifecycle to manage). A shared session would amortize TLS handshake but introduces a session-lifetime question (per-from_env? per-process?). Per-call is the default; shared session is an ar-4/v1.1 optimization.

2. **Cascade factory's `except Exception` breadth.** The wrapper catches `Exception` broadly (per `<interfaces>` § cascade implementation). A narrower `except (httpx.HTTPError, asyncio.TimeoutError)` would miss `ValueError` / `KeyError` from JSON parse failures, defeating the cascade's intent. Broad catch is intentional and documented with a `# noqa: BLE001` comment in the implementation.

3. **Where the new `tools/` submodule lives in the import graph.** The planner spec has `lib/research/tools/web_search.py` as a self-contained submodule (no imports from `lib.research.types` — web tools return raw `list[dict]` / `str`, not Source dataclasses). This keeps the module pure-HTTP. Wave 2 (Verifier) is responsible for converting cascade output dicts into `Source(kind="web", ...)` instances at consumption time.

4. **Mocking `httpx.AsyncClient` vs using `respx`.** The planner spec uses `unittest.mock.patch("lib.research.tools.web_search.httpx.AsyncClient")` — pure `unittest.mock`, no new test deps. `respx` would be cleaner but adds a dependency. Default to mock-based; revisit if `respx` is already a transitive dep (check `requirements.txt` during read_first).

5. **Brave-only edge case (Brave key set, Tavily unset).** Per CONTEXT § TOOL-02, the cascade requires both ends — `cfg.web_search` stays the stub. But CONTEXT also says `cfg.web_search_fallback` MAY still be set "for tests / observability". The planner spec retains Brave's partial regardless of Tavily presence (3 tests in Group 3 cover the no-key, Tavily-only, and both-keys cases; the Brave-only case is implicitly covered by the same logic — `web_search_fallback` is a bare Brave partial whenever the key is set). If the orchestrator wants explicit coverage, add a 10th test `test_from_env_brave_only_keeps_skipped_stub_but_exposes_fallback`.

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env (Wave 1+2 unit tests use mocks; Wave 3 Grounding test uses mocks; live-key Layer 2b smoke is the phase-close gate).
