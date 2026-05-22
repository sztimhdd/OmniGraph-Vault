---
phase: ar-1-mvp-vertical-slice
plan: 01
subsystem: agentic-rag-v1
tags: [scaffolding, types, config, contract, packaging]
requires:
  - python>=3.11
  - lib/llm_complete.py (existing)
  - lib/lightrag_embedding.py (existing)
  - lib/vision_cascade.py (existing)
provides:
  - lib/research/ package skeleton
  - 7 frozen dataclasses + ResearchState + ResearchResult + ResearchConfig
  - ResearchConfig.from_env() env-once factory (Axis 3)
  - async research() / async research_stream() orchestrator skeleton
  - omnigraph.research namespace mapping (LIB-09 option a)
  - scripts/check_contract.sh CONTRACT-01 + CONTRACT-02 grep hooks
affects:
  - pyproject.toml (added [project], setuptools.packages.find, package-dir)
tech-stack:
  added:
    - python dataclasses (frozen + mutable)
    - typing.Literal alphabets (Status, Source.kind)
  patterns:
    - env-once factory with lazy provider imports
    - frozen-everywhere except orchestrator scratchpad
    - streaming-peer signature lock (Axis 5)
key-files:
  created:
    - lib/research/__init__.py
    - lib/research/types.py
    - lib/research/config.py
    - lib/research/orchestrator.py
    - lib/research/stages/__init__.py
    - lib/research/README.md
    - scripts/check_contract.sh
    - tests/unit/research/__init__.py
    - tests/unit/research/test_types.py
    - tests/unit/research/test_config.py
  modified:
    - pyproject.toml
decisions:
  - "LIB-09 option a confirmed: physical lib/research/ + declared omnigraph.research via package-dir mapping"
  - "ResearchConfig lives in types.py (single import point), with from_env() factory in config.py"
  - "_skipped_web_search is module-level (stable identity for `is` test)"
  - "Lazy imports of llm_complete/lightrag_embedding/vision_cascade inside from_env() (avoid eager init-time side effects)"
  - "research_stream() raises NotImplementedError('ar-4') — signature locked today, body deferred per LIB-08 split"
metrics:
  duration_seconds: 294
  duration_human: "~5 minutes"
  tasks_completed: 7
  files_created: 10
  files_modified: 1
  unit_tests: 21
  unit_test_pass_rate: "21/21 (100%)"
  completed: "2026-05-22"
requirements_satisfied:
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
---

# Phase ar-1 Plan 01: Package Scaffolding Summary

Bootstrap of `lib/research/` package skeleton: 10 dataclass-decorated types
(7 stage outputs + ResearchState + ResearchResult + ResearchConfig) plus the
`Status` Literal alias, env-driven `ResearchConfig.from_env()` factory, async
`research()` / `research_stream()` orchestrator skeleton with deferred bodies,
`omnigraph.research` namespace mapping in `pyproject.toml`, CONTRACT-01 +
CONTRACT-02 grep hooks, and unit tests pinning every contract — all under
the corp-network-aware harness conventions of OmniGraph-Vault.

## Files Created (10) + Modified (1)

| File | Role |
|---|---|
| `lib/research/__init__.py` | 7-name public API surface |
| `lib/research/types.py` | 10 dataclasses + `Status` Literal (verbatim from CONTEXT.md) |
| `lib/research/config.py` | `from_env()` env-once factory + `_skipped_web_search` stub |
| `lib/research/orchestrator.py` | `async research()` + `async research_stream()` skeletons |
| `lib/research/stages/__init__.py` | Subpackage marker (stage modules in ar-1-02) |
| `lib/research/README.md` | LIB-09 doc + CONTRACT checklist + stage-status table |
| `scripts/check_contract.sh` | CONTRACT-01 + CONTRACT-02 grep enforcement |
| `tests/unit/research/__init__.py` | Test package marker |
| `tests/unit/research/test_types.py` | 10 unit tests for dataclass shapes |
| `tests/unit/research/test_config.py` | 11 unit tests for env-once factory + orchestrator smoke |
| `pyproject.toml` | **modified** — added `[project]`, `[tool.setuptools.*]` blocks |

## Test Results

```
$ venv/Scripts/python.exe -m pytest tests/unit/research/ -v
========================= 21 passed in 2.30s =========================
```

- 10/10 in `test_types.py` — frozen-ness, Literal alphabets, defaults, field-presence
- 11/11 in `test_config.py` — env-once contract, omonigraph typo preservation,
  stub web_search identity, default iter caps, orchestrator import smoke

## CONTRACT Enforcement

```
$ bash scripts/check_contract.sh
CONTRACT-01 ok
CONTRACT-02 ok
```

- **CONTRACT-01** (forbidden `omnigraph_search.*` imports beyond `.query`): 0 hits
- **CONTRACT-02** (`~/.hermes` / `omonigraph-vault` paths outside `config.py`): 0 hits

## pyproject.toml Diff

**Added (prepended above the existing `[tool.pytest.ini_options]`):**

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

**Preserved verbatim:** the entire `[tool.pytest.ini_options]` block (testpaths,
pythonpath, asyncio_mode, markers).

`tomllib` parse confirms `project.name == "omnigraph-vault"` and
`tool.setuptools.package-dir["omnigraph.research"] == "lib/research"`.

## LIB-09 Resolution

Option (a) shipped: physical `lib/research/` + declared `omnigraph.research`
namespace via `[tool.setuptools.package-dir]`. Both import paths resolve to
the same module:

- `from lib.research import research` — works today (under `pythonpath=["."]`)
- `from omnigraph.research import research` — resolves after ar-1-03 Task 0
  runs `pip install -e .` (deferred, per plan)

## Public API Surface (LIB-01)

```python
>>> import lib.research
>>> sorted(lib.research.__all__)
['ResearchConfig', 'ResearchResult', 'ResearchState', 'Source', 'from_env',
 'research', 'research_stream']
```

Per-stage dataclasses (`RetrieverOutput`, `ReasonerOutput`, `VerifierOutput`,
`SynthesizerOutput`, `WebBaseline`, `RetrievedImage`) are intentionally NOT
re-exported at top level — accessed via `from lib.research.types import ...`
for advanced consumers (HTTP wrapper, CLI `--dump-state`).

## Commits (7)

| Hash | Message |
|---|---|
| `7a26fed` | test(ar-1-01): add lib/research/types.py with 7 frozen dataclasses + 10 unit tests |
| `bb939d7` | feat(ar-1-01): add config.from_env() factory + orchestrator skeleton + 11 tests |
| `b2d9ec3` | feat(ar-1-01): finalize lib/research/__init__.py with 7-name public API |
| `f34bf55` | feat(ar-1-01): declare omnigraph.research namespace mapping in pyproject.toml |
| `536a0f0` | chore(ar-1-01): add scripts/check_contract.sh for CONTRACT-01 + CONTRACT-02 |
| `d6dc04b` | docs(ar-1-01): add lib/research/README.md with LIB-09 + CONTRACT checklist |
| (this) | docs(ar-1-01): SUMMARY |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PEP 563 stringified-annotation in test_source_kind_literal_alphabet**

- **Found during:** Task 1 verification (first pytest run)
- **Issue:** Initial test asserted `get_args(Source.__annotations__["kind"])`,
  but `from __future__ import annotations` (required by CONTEXT.md) makes
  annotations string objects at runtime, so `get_args()` returns `()` and
  the assertion failed.
- **Fix:** Resolved annotations via `typing.get_type_hints(Source)` which
  evaluates string annotations to live `Literal[...]` objects, then
  `get_args()` returns the 4-tuple alphabet correctly.
- **Files modified:** `tests/unit/research/test_types.py`
- **Commit:** folded into `7a26fed` (the introducing commit; bug found and
  fixed before commit landed in repo)

No other deviations. Plan executed task-for-task as written.

## Self-Check: PASSED

All claimed files exist:

- `lib/research/__init__.py`, `types.py`, `config.py`, `orchestrator.py`,
  `stages/__init__.py`, `README.md` — all present
- `scripts/check_contract.sh` — present, executable bit set via
  `git update-index --chmod=+x`
- `tests/unit/research/__init__.py`, `test_types.py`, `test_config.py` — present

All claimed commits exist in `git log --oneline`:

- `7a26fed`, `bb939d7`, `b2d9ec3`, `f34bf55`, `536a0f0`, `d6dc04b` — verified

All claimed verifications pass:

- `pytest tests/unit/research/ -v` → 21 passed
- `from lib.research import <7 names>` → all importable
- `bash scripts/check_contract.sh` → exit 0, both CONTRACT-01 + CONTRACT-02 ok
- `tomllib.loads(pyproject.toml)` → `project.name` + `package-dir` both present,
  `[tool.pytest.ini_options]` preserved

## L1 smoke status: PASS

- 21/21 unit tests pass on first clean run
- Public API import `from lib.research import research, research_stream, ResearchConfig, from_env, ResearchResult, ResearchState, Source` succeeds
- CONTRACT-01 + CONTRACT-02 grep hooks both clean (0 hits)
- pyproject.toml namespace mapping declared + parseable
- No environmental blockers; ar-1-02 stage stubs may proceed
