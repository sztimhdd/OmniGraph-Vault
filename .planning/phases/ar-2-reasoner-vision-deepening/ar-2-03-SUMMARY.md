---
phase: ar-2-reasoner-vision-deepening
plan: 03
milestone: Agentic-RAG-v1
wave: 3
status: complete
last_updated: "2026-05-22"
requirements_delivered:
  - CLI-03
files_modified:
  - lib/research/__main__.py (extended _parse_args + _amain; +28 LOC)
  - tests/unit/research/test_main_cli_flags.py (new — 9 tests)
  - tests/unit/research/test_main_cli.py (surgical: allowed_stdlib +"dataclasses")
---

# ar-2-03 — CLI Flags --max-iter-reasoner / --max-iter-verifier / --no-grounding Summary

## One-liner

Extended `lib/research/__main__.py` with three CLI override flags
(`--max-iter-reasoner`, `--max-iter-verifier`, `--no-grounding`) wired
through `dataclasses.replace(cfg, **overrides)` only when overrides are
non-empty (preserves the ar-1 default-cfg path byte-for-byte). LLM
provider selection stays env-only via `OMNIGRAPH_LLM_PROVIDER` per
CLI-03 hard rule — NO `--llm-provider` flag added. Pure-wrapper rule
(LIB-04) preserved: `_amain` body is 15 non-blank-non-comment lines
(≤ 18 cap).

## Files modified

| File | LOC delta | Change |
|---|---|---|
| `lib/research/__main__.py` | ~28 added (52 → 80 total) | Added `import dataclasses`; 3 new `parser.add_argument` calls; `_amain` signature changed from `(query: str)` → `(ns: argparse.Namespace)`; built `overrides` dict + guarded `dataclasses.replace`; updated `main()` to pass `ns` instead of `ns.query` |
| `tests/unit/research/test_main_cli_flags.py` | 196 (new) | 9 tests — 6 fast `_parse_args` unit tests + 2 fast `_amain` async tests (with `from_env` + `research` patched) + 1 slow subprocess cap=0 LLM-free smoke |
| `tests/unit/research/test_main_cli.py` | +1/-1 (surgical) | `allowed_stdlib` set extended from `{argparse, asyncio, sys}` to `{argparse, asyncio, dataclasses, sys}` to match new import; comment added linking to ar-2-03 |

## Test count

- New ar-2-03 tests: **9** (all green, including slow subprocess test)
- Full `tests/unit/research/` suite: **88 / 88 passing** (79 baseline + 9 new)
- ar-1 baseline + ar-2-01 + ar-2-02: 79 passing
- ar-2-03 delta: **+9 new tests, 0 ar-1/ar-2-01/ar-2-02 regressions**

```
============================= 88 passed in 69.04s (0:01:09) ==============================
```

## Test list (new file)

Fast unit tests (no asyncio-loop heavy work):

1. `test_parse_args_defaults` — no flags → all override slots default to `None`/`False`
2. `test_parse_args_max_iter_reasoner` — `--max-iter-reasoner 2 test` parses correctly
3. `test_parse_args_max_iter_verifier` — `--max-iter-verifier 1 test` parses correctly
4. `test_parse_args_no_grounding` — `--no-grounding test` → `ns.no_grounding is True`
5. `test_parse_args_all_three_flags` — combined flags → all three override slots populated; query parsed
6. `test_parse_args_invalid_int_rejected` — `--max-iter-reasoner not-an-int` raises `SystemExit` (argparse type=int)

Fast async tests (patch `from_env` + `research` to capture cfg):

7. `test_amain_builds_overrides` — all 3 flags → captured cfg has `max_iter_reasoner=2`, `max_iter_verifier=1`, `google_search_grounding is None`
8. `test_amain_no_flags_preserves_default_cfg` — no flags → captured cfg has `max_iter_reasoner=5`, `max_iter_verifier=3` (ResearchConfig defaults — proves `if overrides:` guard works)

Slow integration test:

9. `test_subprocess_smoke_with_max_iter_zero` (`@pytest.mark.slow`) — `python -m omnigraph.research --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding "test query"` exits 0 with non-empty stdout. `cap=0` makes Reasoner agent loop exit immediately on first iteration check (status="ok", iter_count=0), so no LLM provider is invoked. This is the L2 LLM-free smoke specified in the plan's verification block.

## Pure-wrapper enforcement

Output of `grep -E "^(import|from)" lib/research/__main__.py`:

```
from __future__ import annotations
import argparse
import asyncio
import dataclasses
import sys
from .config import from_env
from .image_server import ensure_image_server
from .orchestrator import research
```

Exactly the 8 expected imports — no extras. `dataclasses` is stdlib (added for `dataclasses.replace`).

`_amain` body LOC count (non-blank, non-comment): **15** (cap is 18). Body:

```python
cfg = from_env()                                          # 1
overrides: dict = {}                                       # 2
if ns.max_iter_reasoner is not None:                       # 3
    overrides["max_iter_reasoner"] = ns.max_iter_reasoner  # 4
if ns.max_iter_verifier is not None:                       # 5
    overrides["max_iter_verifier"] = ns.max_iter_verifier  # 6
if ns.no_grounding:                                        # 7
    overrides["google_search_grounding"] = None            # 8
if overrides:                                              # 9
    cfg = dataclasses.replace(cfg, **overrides)            # 10
base_image_dir = cfg.rag_working_dir.parent / "images"     # 11
if base_image_dir.is_dir():                                # 12
    ensure_image_server(base_image_dir)                    # 13
result = await research(ns.query, cfg)                     # 14
return result.markdown                                     # 15
```

## CONTRACT-01 + CONTRACT-02 grep results

CONTRACT-01 (`from omnigraph_search` should appear ONLY as `.query` import in retriever.py + reasoner.py):

```
lib\research\stages\reasoner.py:11:CONTRACT-01: this module adds the SECOND ``from omnigraph_search.query import
lib\research\stages\reasoner.py:35:from omnigraph_search.query import search as kg_search
lib\research\stages\retriever.py:23:from omnigraph_search.query import search as kg_search
```

Two real import lines (retriever.py + reasoner.py) plus one comment-line in reasoner.py docstring. Zero forbidden hits. ✓

CONTRACT-02 (`/.hermes` or `omonigraph-vault` literal allowed only in `config.py`):

```
lib\research\config.py:35:        else Path.home() / ".hermes" / "omonigraph-vault"  # 'omonigraph' typo is canonical
```

One hit, in `config.py` (the canonical fallback). Zero forbidden hits. ✓

## CLI-03 hard rule check

`grep -nE "llm-provider|OMNIGRAPH_LLM_PROVIDER" lib/research/__main__.py`:

```
5:selection remains env-only (OMNIGRAPH_LLM_PROVIDER) — NO --llm-provider flag
```

Single hit in module docstring documenting the rule itself — there is no `--llm-provider` argparse flag. ✓

## ar-1 regression: `test_main_cli.py` surgical edit

Single change: `allowed_stdlib` set in `test_main_imports_only_allowed_modules` extended from `{"argparse", "asyncio", "sys"}` to `{"argparse", "asyncio", "dataclasses", "sys"}`. Required because ar-2-03 added `import dataclasses` to `__main__.py` for `dataclasses.replace`. No `_amain(...)` call sites needed updating — `test_main_returns_none` passes `["test query"]` to `cli_mod.main(...)` which routes through `_parse_args` → `_amain(ns)`, so the signature change is transparent at the test layer.

Line-count delta: +1 / -1 (set membership extended; comment added). Rationale: `dataclasses` is stdlib and explicitly required by CLI-03; no pure-wrapper rule violation (only stdlib + relative `.config`/`.image_server`/`.orchestrator` permitted).

## Slow subprocess test (Test 9) result

Command run inside test:

```
python -m omnigraph.research --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding "test query"
```

- Exit code: 0
- stdout: non-empty (>200 chars typical on dev box; 308 chars on the L2 manual smoke run, see below)
- stderr: LightRAG init logs only (no exceptions)

## L2 cap=0 LLM-free CLI smoke (manual, executed)

Per orchestrator instructions, ran the L2 smoke directly:

```
venv/Scripts/python.exe -m omnigraph.research --max-iter-reasoner 0 --max-iter-verifier 0 --no-grounding "什么是 Hermes Harness 深度解析"
```

Captured to `.scratch/ar-2-03-l2-smoke-260522.stdout` + `.stderr`:

- Exit code: **0**
- stdout chars: **308** (≥ 200 expected; markdown body)
- Markdown contains query echo: `# 关于「什么是 Hermes Harness 深度解析」的研究答复` ✓
- Degradation note lines from Synthesizer present:
  - `> ℹ️ WebBaseline skipped: web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)`
  - `> ❌ Retriever failed: Embedding dim mismatch, expected: 3072, but loaded: 768`
  - `> ℹ️ Verifier skipped: ar-1 stub — verifier loop lands in ar-3`
- No exceptions raised; ResearchState dataclass populated via standard discipline (Retriever failure cascades skips downstream stages — Reasoner cap=0 path was bypassed by Retriever failure, but the CLI flag plumbing itself is exercised correctly: argparse parsed all 3 flags, `dataclasses.replace` applied, exit code 0)

stdout excerpt (verbatim):

```markdown
# 关于「什么是 Hermes Harness 深度解析」的研究答复
## 知识图谱检索结果

(no chunks retrieved)


---

> ℹ️ WebBaseline skipped: web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)
> ❌ Retriever failed: Embedding dim mismatch, expected: 3072, but loaded: 768
> ℹ️ Verifier skipped: ar-1 stub — verifier loop lands in ar-3
```

The Retriever embedding-dim mismatch is a pre-existing local dev-graph state issue (the local `lightrag_storage` was built with a 768-dim embedding before the v3.4 migration to 3072-dim), NOT a regression from this plan. The point of the L2 smoke is to prove (a) all 3 flags parse, (b) `dataclasses.replace` propagates, (c) the orchestrator exits cleanly even when downstream stages skip/fail. All three are verified.

## Deviations from plan

1. **Test 9 not relaxed.** Plan offered the option to relax Test 9 from a real subprocess to a unit-only override-path test if subprocess proved flaky. The cap=0 subprocess ran cleanly in 6 sec on the dev box; no relaxation needed.
2. **`from_env` patched in async tests.** Plan's illustrative test code monkeypatched only `research` and set `OMNIGRAPH_BASE_DIR=tmp_path`, which would have invoked the real `from_env()` and incurred lazy LLM client init. To keep async unit tests fast and isolated (matching `test_main_returns_none`'s pattern in `test_main_cli.py`), I additionally patched `lib.research.__main__.from_env` to return a minimal stub `ResearchConfig` and `ensure_image_server` to a no-op. This is a stricter version of the plan's intent and exercises the same override semantics.
3. **No `--run-slow` flag exists.** Plan's verification block referenced `pytest --run-slow`, but the project uses `pytest.mark.slow` with opt-in via `-m slow` (per `pyproject.toml` line 34). Default `pytest tests/unit/research/` runs all 9 new tests including the slow one (slow markers are warnings-only; not gated). Verification command in plan still works.
4. **`ar-1 test_main_cli.py` edit smaller than plan estimated.** Plan said "≤ 5 lines" — actual change was 2 lines (one set literal extension + one comment line). No `_amain(query)` direct callers existed to update — all ar-1 CLI tests went through `cli_mod.main([...])` which is signature-stable.

## Pure-wrapper LOC: confirmed ≤ 18

`_amain` body: **15 non-blank, non-comment lines** (well under 18 cap). See breakdown above.

## Commit hash

To be backfilled via forward-only follow-up commit per Wave 2 precedent (commit `5aedf57`).
