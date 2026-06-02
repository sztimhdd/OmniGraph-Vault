---
phase: ar-2-reasoner-vision-deepening
plan: 03
type: execute
wave: 3
depends_on:
  - ar-2-02
files_modified:
  - lib/research/__main__.py
  - tests/unit/research/test_main_cli_flags.py
autonomous: true
requirements:
  - CLI-03

must_haves:
  truths:
    - "_parse_args() accepts three new flags: --max-iter-reasoner (int, default None), --max-iter-verifier (int, default None), --no-grounding (action='store_true', default False)"
    - "When any flag is set, _amain() builds an overrides dict and calls cfg = dataclasses.replace(cfg, **overrides) BEFORE invoking research()"
    - "When no flags are set, the override dict is empty and dataclasses.replace is NOT called (preserves the ar-1 default-cfg path byte-for-byte)"
    - "--no-grounding sets cfg.google_search_grounding to None (currently always None anyway — plumbed-but-no-op until ar-3 wires Grounding into from_env())"
    - "LLM provider selection stays env-only (OMNIGRAPH_LLM_PROVIDER) — NO --llm-provider flag added in ar-2 (CLI-03 hard rule)"
    - "__main__.py remains a pure wrapper — only argparse + dataclasses.replace + asyncio.run + print; NO business logic added"
    - "Allowed imports in __main__.py: argparse, asyncio, dataclasses (NEW for replace), sys, plus relative .config / .image_server / .orchestrator (no new top-level package imports)"
    - "Subprocess integration test exits 0 with non-empty stdout (proves override path end-to-end against the all-stub default config)"
  artifacts:
    - path: "lib/research/__main__.py"
      provides: "Extended CLI with --max-iter-reasoner / --max-iter-verifier / --no-grounding overrides; pure wrapper rule preserved"
      contains: "argparse with 3 new arguments, _amain builds overrides dict, dataclasses.replace(cfg, **overrides) gate"
    - path: "tests/unit/research/test_main_cli_flags.py"
      provides: "Unit tests for _parse_args defaults + override behaviors + integration subprocess test"
      contains: "test_parse_args_defaults, test_parse_args_max_iter_reasoner, test_parse_args_max_iter_verifier, test_parse_args_no_grounding, test_amain_builds_overrides, test_subprocess_max_iter_reasoner_override"
  key_links:
    - from: "lib/research/__main__.py"
      to: "dataclasses.replace"
      via: "cfg = dataclasses.replace(cfg, **overrides) when overrides is non-empty"
      pattern: "dataclasses\\.replace"
    - from: "lib/research/__main__.py"
      to: "ResearchConfig.max_iter_reasoner / .max_iter_verifier / .google_search_grounding"
      via: "overrides dict keys mirror ResearchConfig field names"
      pattern: "max_iter_reasoner|max_iter_verifier|google_search_grounding"
---

<objective>
Extend the CLI entrypoint at `lib/research/__main__.py` with three new flags — `--max-iter-reasoner`, `--max-iter-verifier`, `--no-grounding` — and wire them into a `dataclasses.replace()` override on `ResearchConfig` BEFORE invoking `research()`. Preserve the pure-wrapper rule (LIB-04 / Rule 1) — `__main__.py` still has zero business logic beyond argument parsing and dataclass override.

Purpose:

- CLI-03: deliver the three flags called out in the requirements. `--max-iter-reasoner` is meaningful immediately (ar-2-01 Reasoner agent loop respects `cfg.max_iter_reasoner`). `--max-iter-verifier` and `--no-grounding` are plumbed-but-no-op in ar-2 (Verifier is still the ar-1 stub through ar-2; Grounding is unwired until ar-3) — flag plumbing is cheap and avoids a CLI surface change in ar-3.
- The Layer 2 smoke command from CONTEXT.md becomes runnable after this plan: `python -m omnigraph.research --max-iter-reasoner 2 --max-iter-verifier 1 --no-grounding "什么是 Hermes Harness 深度解析"`.

Output:

- One file modified: `lib/research/__main__.py` (~25 LOC added — three `parser.add_argument` calls + an `overrides` dict + a guarded `dataclasses.replace` call).
- One new test file: `tests/unit/research/test_main_cli_flags.py` (≥6 tests: 4 fast unit tests for `_parse_args`, 1 fast unit test for `_amain` override-dict construction, 1 slow integration subprocess test).
- ar-1 + ar-2-01 + ar-2-02 regression suite still green; full `tests/unit/research/` count after ar-2-03 ≥ 53 (ar-1 ≥35 + ar-2-01 ≥7 + ar-2-02 ≥8 + this plan ≥6).

This plan does NOT touch `ResearchConfig` (the dataclass already has `max_iter_reasoner: int = 5`, `max_iter_verifier: int = 3`, `google_search_grounding: Callable | None = None` slots from ar-1). It does NOT touch any stage. It does NOT add a new helper module — the override logic is ~6 lines and lives inline in `_amain()`.

This plan also documents (but does NOT execute) the upgraded Layer 2 smoke test from CONTEXT.md as a manual verification step — full smoke is environment-conditional (depends on a working LLM provider key) and the orchestrator runs it manually after this plan ships.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/__main__.py
@lib/research/types.py
@lib/research/config.py
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-01-reasoner-agent-loop-PLAN.md
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-02-synthesizer-caption-embeds-PLAN.md

<interfaces>
**Current `__main__.py` structure (post ar-1, verbatim — preserved as the foundation):**

The current file has:

- Module docstring header (single line + paragraph)
- Imports: `argparse`, `asyncio`, `sys`, `from .config import from_env`, `from .image_server import ensure_image_server`, `from .orchestrator import research`
- `_parse_args(argv)` — single positional `query` arg
- `_amain(query: str) -> str` — calls `from_env()`, then `ensure_image_server` (guarded by `is_dir`), then `await research(query, cfg)`, returns `result.markdown`
- `main(argv)` — calls `_parse_args`, `asyncio.run(_amain(ns.query))`, reconfigures stdout to UTF-8, prints
- `if __name__ == "__main__": main(sys.argv[1:])`

**Target `__main__.py` structure after ar-2-03 (changes are LOCALIZED — only `_parse_args` body, `_amain` signature/body, and `main` body change):**

```python
"""CLI entrypoint: ``python -m omnigraph.research "<query>" [flags]``.

CLI-03 (ar-2): adds --max-iter-reasoner / --max-iter-verifier / --no-grounding
overrides on top of the ar-1 bare positional-only invocation. LLM provider
selection remains env-only (OMNIGRAPH_LLM_PROVIDER) — NO --llm-provider flag
per CLI-03's hard rule.

Pure wrapper rule (LIB-04) preserved: argparse + dataclasses.replace +
asyncio.run + print. Anything more sophisticated belongs in orchestrator.py.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses  # NEW in ar-2 — for dataclasses.replace(cfg, **overrides)
import sys

from .config import from_env
from .image_server import ensure_image_server
from .orchestrator import research


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="omnigraph.research",
        description="Run the OmniGraph agentic-RAG research pipeline.",
    )
    parser.add_argument("query", help="Natural-language research query.")
    parser.add_argument(
        "--max-iter-reasoner",
        type=int,
        default=None,
        help="Override Reasoner agent-loop cap (default 5).",
    )
    parser.add_argument(
        "--max-iter-verifier",
        type=int,
        default=None,
        help="Override Verifier agent-loop cap (default 3). "
             "Plumbed in ar-2 — behavior activates after ar-3 lands real Verifier loop.",
    )
    parser.add_argument(
        "--no-grounding",
        action="store_true",
        default=False,
        help="Disable Vertex Gemini Grounding tool. "
             "Plumbed in ar-2 — behavior activates after ar-3 wires Grounding into from_env().",
    )
    return parser.parse_args(argv)


async def _amain(ns: argparse.Namespace) -> str:
    cfg = from_env()

    # CLI-03: collect overrides for dataclasses.replace.
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
    return result.markdown


def main(argv: list[str] | None = None) -> None:
    ns = _parse_args(argv)
    markdown = asyncio.run(_amain(ns))  # CHANGED: pass full namespace, not just query
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    print(markdown)


if __name__ == "__main__":
    main(sys.argv[1:])
```

**Key contract details:**

1. `_amain` now takes the full `argparse.Namespace`, not just the query string. This is the only caller-visible signature change. `main()` is updated to pass `ns` instead of `ns.query`. `_amain` is module-private (single leading underscore), so no public-API contract change.

2. `dataclasses.replace(cfg, **overrides)` is called ONLY when `overrides` is non-empty. This preserves the ar-1 default-cfg code path byte-for-byte when no flags are passed (important for ar-1 regression tests).

3. `--no-grounding` semantics in ar-2: setting `cfg.google_search_grounding = None`. Since `from_env()` currently always returns `google_search_grounding=None` (Grounding wiring lands in ar-3), the flag is effectively a no-op in ar-2. After ar-3 lands, when `from_env()` MAY return a non-None grounding callable (when `OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"`), the flag will actually disable it. This is the "plumbed-but-no-op" pattern.

4. NO `--llm-provider` flag (CLI-03 hard rule). LLM provider selection remains env-only via `OMNIGRAPH_LLM_PROVIDER`. Do NOT add it.

5. NO new top-level package imports. The only new import is stdlib `dataclasses`. The relative imports (`.config`, `.image_server`, `.orchestrator`) are unchanged.

6. The `ResearchConfig` dataclass already has the three target fields:
   - `max_iter_reasoner: int = 5`
   - `max_iter_verifier: int = 3`
   - `google_search_grounding: Callable | None = None`
   So `dataclasses.replace(cfg, max_iter_reasoner=2, max_iter_verifier=1, google_search_grounding=None)` is contract-compatible — no `ResearchConfig` shape change needed.

**Test scope (illustrative — implementer adjusts as needed):**

```python
# tests/unit/research/test_main_cli_flags.py

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.research.__main__ import _parse_args, _amain


# ----- Fast unit tests for _parse_args (no asyncio) -----

def test_parse_args_defaults():
    """No flags → all override slots default to None / False."""
    ns = _parse_args(["test query"])
    assert ns.query == "test query"
    assert ns.max_iter_reasoner is None
    assert ns.max_iter_verifier is None
    assert ns.no_grounding is False


def test_parse_args_max_iter_reasoner():
    ns = _parse_args(["--max-iter-reasoner", "2", "test"])
    assert ns.max_iter_reasoner == 2
    assert ns.query == "test"


def test_parse_args_max_iter_verifier():
    ns = _parse_args(["--max-iter-verifier", "1", "test"])
    assert ns.max_iter_verifier == 1


def test_parse_args_no_grounding():
    ns = _parse_args(["--no-grounding", "test"])
    assert ns.no_grounding is True


def test_parse_args_all_three_flags():
    ns = _parse_args([
        "--max-iter-reasoner", "2",
        "--max-iter-verifier", "1",
        "--no-grounding",
        "test",
    ])
    assert ns.max_iter_reasoner == 2
    assert ns.max_iter_verifier == 1
    assert ns.no_grounding is True


def test_parse_args_invalid_int_rejected():
    with pytest.raises(SystemExit):
        _parse_args(["--max-iter-reasoner", "not-an-int", "test"])


# ----- Fast unit test for _amain override-dict construction -----

@pytest.mark.asyncio
async def test_amain_builds_overrides(monkeypatch, tmp_path):
    """Flags set → _amain calls dataclasses.replace before research()."""
    captured_cfgs = []

    async def fake_research(query, cfg):
        captured_cfgs.append(cfg)
        from lib.research.types import ResearchResult, ResearchState
        return ResearchResult(
            markdown="stub", confidence=0.0, sources=[], images_embedded=[],
            state=ResearchState(query=query, timestamp_start=0.0),
        )

    monkeypatch.setattr("lib.research.__main__.research", fake_research)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    ns = _parse_args([
        "--max-iter-reasoner", "2",
        "--max-iter-verifier", "1",
        "--no-grounding",
        "test query",
    ])
    await _amain(ns)

    assert len(captured_cfgs) == 1
    cfg = captured_cfgs[0]
    assert cfg.max_iter_reasoner == 2
    assert cfg.max_iter_verifier == 1
    assert cfg.google_search_grounding is None


@pytest.mark.asyncio
async def test_amain_no_flags_preserves_default_cfg(monkeypatch, tmp_path):
    """No flags → dataclasses.replace NOT called; cfg is from_env() output verbatim."""
    captured_cfgs = []

    async def fake_research(query, cfg):
        captured_cfgs.append(cfg)
        from lib.research.types import ResearchResult, ResearchState
        return ResearchResult(
            markdown="stub", confidence=0.0, sources=[], images_embedded=[],
            state=ResearchState(query=query, timestamp_start=0.0),
        )

    monkeypatch.setattr("lib.research.__main__.research", fake_research)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))

    ns = _parse_args(["test"])
    await _amain(ns)

    cfg = captured_cfgs[0]
    assert cfg.max_iter_reasoner == 5  # ResearchConfig default
    assert cfg.max_iter_verifier == 3  # ResearchConfig default


# ----- Slow integration subprocess test -----

@pytest.mark.slow
def test_subprocess_max_iter_reasoner_override(tmp_path):
    """End-to-end: `python -m omnigraph.research --max-iter-reasoner 1 "test"` exits 0."""
    env = dict(os.environ)
    env["OMNIGRAPH_BASE_DIR"] = str(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", "--max-iter-reasoner", "1", "test query"],
        capture_output=True, text=True, env=env, cwd=repo_root,
        timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout) > 0
```

</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend _parse_args with three flags + extend _amain to build overrides dict + dataclasses.replace</name>
  <read_first>
    - lib/research/__main__.py (current ar-1 body — preserve everything except _parse_args body and _amain signature/body)
    - lib/research/types.py (ResearchConfig — confirm max_iter_reasoner / max_iter_verifier / google_search_grounding fields exist with correct defaults)
    - lib/research/config.py (from_env() — confirm google_search_grounding is currently always None in ar-2 scope)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "CLI-03: three new CLI flags"
  </read_first>
  <files>lib/research/__main__.py</files>
  <behavior>
    `__main__.py` after this task:
    - `_parse_args` accepts: positional `query`, `--max-iter-reasoner` (int, default None), `--max-iter-verifier` (int, default None), `--no-grounding` (action="store_true", default False).
    - Passing 0 args (no query) still raises SystemExit (argparse default behavior — preserved from ar-1).
    - `_amain(ns)` (now takes Namespace, not query string) calls `from_env()`, builds an `overrides` dict, conditionally calls `dataclasses.replace(cfg, **overrides)` only if `overrides` is non-empty, then proceeds with the existing `ensure_image_server` + `research()` + return-markdown flow.
    - `main(argv)` updated to pass `ns` (not `ns.query`) to `_amain`.
    - The pure-wrapper rule is preserved: zero business logic beyond argparse + dataclasses.replace + asyncio.run + print.
    - Imports: only `dataclasses` is added (stdlib). NO new top-level package imports.
  </behavior>
  <action>
    1. Open `lib/research/__main__.py`. Update the module docstring to reflect ar-2 (per `<interfaces>` § "Target `__main__.py` structure" docstring block).

    2. Add `import dataclasses` to the import block. Place between `import asyncio` and `import sys` (alphabetical order).

    3. Replace the `_parse_args` body to add the three new arguments per `<interfaces>`. The argument names use kebab-case (`--max-iter-reasoner`); argparse automatically maps to snake_case attributes (`ns.max_iter_reasoner`). Verify the `dest` is correct by argparse's default mapping (no need for explicit `dest=`).

    4. Replace `_amain`'s signature from `async def _amain(query: str) -> str:` to `async def _amain(ns: argparse.Namespace) -> str:`. Inside the body:
       a. Call `cfg = from_env()` (unchanged).
       b. Build the `overrides: dict = {}` dict per `<interfaces>`. Three guarded entries: `max_iter_reasoner`, `max_iter_verifier`, `google_search_grounding` (set to None when `--no-grounding`).
       c. `if overrides: cfg = dataclasses.replace(cfg, **overrides)` — guarded so the no-flags path is byte-for-byte unchanged from ar-1.
       d. Continue with the existing `base_image_dir = cfg.rag_working_dir.parent / "images"` block, `ensure_image_server`, `await research(ns.query, cfg)`, `return result.markdown`.

    5. Update `main(argv)`: change `markdown = asyncio.run(_amain(ns.query))` to `markdown = asyncio.run(_amain(ns))`.

    6. Confirm the `sys.stdout.reconfigure(encoding="utf-8")` block is preserved unchanged.

    7. Confirm the `if __name__ == "__main__": main(sys.argv[1:])` line is preserved unchanged.

    8. Pure-wrapper audit: count non-comment, non-blank lines in the modified `_amain` body. Should be ~14 lines. If significantly more, simplify — pure-wrapper rule is non-negotiable.

    9. Smoke check: importable + flags parse correctly.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.__main__ import _parse_args; ns = _parse_args(['--max-iter-reasoner','2','--max-iter-verifier','1','--no-grounding','test']); assert ns.max_iter_reasoner==2 and ns.max_iter_verifier==1 and ns.no_grounding is True and ns.query=='test'; print('all flags parse ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/__main__.py` imports without error.
    - `_parse_args(["--max-iter-reasoner", "2", "test"])` returns a Namespace with `max_iter_reasoner == 2` and `query == "test"`.
    - `_parse_args(["--no-grounding", "test"])` returns a Namespace with `no_grounding is True`.
    - `_parse_args(["test"])` returns a Namespace with `max_iter_reasoner is None`, `max_iter_verifier is None`, `no_grounding is False`.
    - `_parse_args(["--max-iter-reasoner", "abc", "test"])` raises `SystemExit` (argparse rejects non-int).
    - File contains literal `dataclasses.replace(cfg` (override path proof).
    - File contains literal `if overrides:` (guard preserves no-flags path).
    - File does NOT contain `--llm-provider` or `OMNIGRAPH_LLM_PROVIDER` (CLI-03 hard rule — env-only).
    - Pure-wrapper LOC: `_amain` body ≤ 18 non-comment non-blank lines.
  </acceptance_criteria>
  <done>__main__.py has three new flags + dataclasses.replace override gate; pure-wrapper rule preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write CLI flag unit tests + slow integration subprocess test + verify regression suite still green</name>
  <read_first>
    - tests/unit/research/test_main_cli.py (ar-1 patterns — confirms `--run-slow` flag convention, integration-test cwd setup, subprocess.run patterns)
    - lib/research/__main__.py (just-modified body — reference for what _parse_args / _amain return)
    - lib/research/types.py (ResearchConfig defaults — for the no-flags assertion)
    - pyproject.toml § `[tool.pytest.ini_options]` — confirm `markers = ["slow: ..."]` is registered
  </read_first>
  <files>tests/unit/research/test_main_cli_flags.py</files>
  <behavior>
    Test file `test_main_cli_flags.py` covers:
    - Test 1 `test_parse_args_defaults`: no flags → `ns.max_iter_reasoner is None`, `ns.max_iter_verifier is None`, `ns.no_grounding is False`, `ns.query == "test query"`.
    - Test 2 `test_parse_args_max_iter_reasoner`: `--max-iter-reasoner 2 test` → `ns.max_iter_reasoner == 2`, `ns.query == "test"`.
    - Test 3 `test_parse_args_max_iter_verifier`: `--max-iter-verifier 1 test` → `ns.max_iter_verifier == 1`.
    - Test 4 `test_parse_args_no_grounding`: `--no-grounding test` → `ns.no_grounding is True`.
    - Test 5 `test_parse_args_all_three_flags`: combined flags → all three override slots populated, query parsed correctly.
    - Test 6 `test_parse_args_invalid_int_rejected`: `--max-iter-reasoner not-an-int test` raises `SystemExit` (argparse type=int conversion).
    - Test 7 `test_amain_builds_overrides`: with all three flags set, `_amain(ns)` calls `dataclasses.replace(cfg, ...)` before invoking `research()`. Captured cfg has `max_iter_reasoner == 2`, `max_iter_verifier == 1`, `google_search_grounding is None`. Use `monkeypatch.setattr("lib.research.__main__.research", fake_research)` to capture the cfg.
    - Test 8 `test_amain_no_flags_preserves_default_cfg`: no flags → captured cfg has `max_iter_reasoner == 5` (ResearchConfig default), `max_iter_verifier == 3` (default).
    - Test 9 `test_subprocess_max_iter_reasoner_override` (marked `@pytest.mark.slow`): `subprocess.run([sys.executable, "-m", "omnigraph.research", "--max-iter-reasoner", "1", "test query"], ...)` exits 0 with non-empty stdout. Use `OMNIGRAPH_BASE_DIR=tmp_path` env var to avoid touching real runtime data. Set `timeout=120` on subprocess.run to prevent hangs.
  </behavior>
  <action>
    1. Create `tests/unit/research/test_main_cli_flags.py`. Imports per `<interfaces>` § Test scope.

    2. Implement Tests 1-9 above. Tests 1-6 are fast pure-argparse unit tests. Tests 7-8 are fast asyncio tests using `monkeypatch.setattr` to swap out `research`. Test 9 is slow integration via subprocess.

    3. For Tests 7-8, the fake `research` function MUST return a real `ResearchResult` (not a stub) so `_amain` can return `result.markdown` without raising:
       ```python
       async def fake_research(query, cfg):
           captured_cfgs.append(cfg)
           from lib.research.types import ResearchResult, ResearchState
           return ResearchResult(
               markdown="stub", confidence=0.0, sources=[], images_embedded=[],
               state=ResearchState(query=query, timestamp_start=0.0),
           )
       ```

    4. For Test 9, the subprocess MUST run from the repo root (cwd) so `python -m omnigraph.research` resolves the editable install. Use `Path(__file__).resolve().parents[3]` to derive repo root from `tests/unit/research/test_main_cli_flags.py`. Pin `timeout=120` to prevent hangs (real `research()` can take a while if it actually invokes any LLM).

    5. Run new test file in isolation FIRST: `venv/Scripts/python.exe -m pytest tests/unit/research/test_main_cli_flags.py -v --run-slow`. All 9 must pass.

    6. Run full regression suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total ≥ 53 (ar-1 ≥35 + ar-2-01 ≥7 + ar-2-02 ≥8 + this plan ≥6 fast tests; the slow test is gated by `--run-slow`).

    7. ar-1 regression check on `tests/unit/research/test_main_cli.py`: the ar-1 CLI test file calls `_amain(query)` with a string argument in some places (since ar-1's `_amain` took a string). Those calls must be updated to `_amain(ns)` where `ns` is a `_parse_args(["query"])` result. Surgical edit:
       - Find every `await _amain(...)` or `asyncio.run(_amain(...))` call in `test_main_cli.py`.
       - If it passes a string directly, change to passing a parsed Namespace.
       - Document each change in SUMMARY.md.

    8. If subprocess Test 9 turns out to be flaky on CI (e.g. due to slow first-time editable-install resolution), the executor MAY relax to a `--max-iter-reasoner 0` test that exercises the override path without invoking the agent loop at all. Document the relaxation in SUMMARY.md. NOTE: max_iter_reasoner=0 should make the loop body skip entirely; verify by inspecting ar-2-01's reasoner.py logic — `while iter_count < 0` is always false, so the loop body never runs and the function returns `ReasonerOutput(iter_count=0, status="ok", ...)`. This is structurally fine and exits 0.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_main_cli_flags.py -v --run-slow &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_main_cli_flags.py` exists with ≥9 tests; all pass (with `--run-slow` for Test 9).
    - Full `tests/unit/research/` suite has ≥53 tests passing (ar-1 ≥35 + ar-2-01 ≥7 + ar-2-02 ≥8 + this plan's 8 fast tests). Slow Test 9 gates separately.
    - Test 7 specifically asserts `cfg.max_iter_reasoner == 2`, `cfg.max_iter_verifier == 1`, `cfg.google_search_grounding is None` after `_amain(ns)` ran with all three flags.
    - Test 8 specifically asserts `cfg.max_iter_reasoner == 5` and `cfg.max_iter_verifier == 3` (ResearchConfig defaults) when no flags passed — proves the `if overrides:` guard works.
    - Test 9 (slow integration) — subprocess exits 0 with non-empty stdout.
    - ar-1 `test_main_cli.py` surgical edits documented (≤5 lines changed total).
  </acceptance_criteria>
  <done>≥9 new CLI-flag tests pass (with --run-slow); full regression suite ≥53 fast tests; ar-1 _amain(string) callers updated to _amain(Namespace).</done>
</task>

</tasks>

<verification>
- Both tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥53 tests passing (fast tests only).
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v --run-slow` exits 0 (full suite including subprocess test).
- CONTRACT-01 grep re-check (must return zero forbidden hits — exactly 2 allowed `from omnigraph_search.query import search` lines: retriever.py + reasoner.py):
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
  Expected: 0 hits.
- CONTRACT-02 grep re-check:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits.
- `bash scripts/check_contract.sh` exits 0.
- Pure-wrapper rule enforcement: `__main__.py` imports must be ONLY `argparse`, `asyncio`, `dataclasses`, `sys` plus relative `.config`, `.image_server`, `.orchestrator`. Any additional import is a violation. Verify:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -E "^(import|from)" lib/research/__main__.py
  ```
  Expected output (any order, plus `from __future__ import annotations`):
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
  Anything else = pure-wrapper violation; STOP and remove the extra import.

**Manual upgraded Layer 2 smoke test (documented step — orchestrator runs after this plan ships)**

Per CONTEXT.md § "Smoke test for ar-2 → Layer 2 — end-to-end CLI (upgraded)", the upgraded smoke command becomes runnable after this plan ships:

```bash
cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
venv/Scripts/python.exe -m omnigraph.research \
  --max-iter-reasoner 2 \
  --max-iter-verifier 1 \
  --no-grounding \
  "什么是 Hermes Harness 深度解析"
```

Expected (per CONTEXT.md):

- exit code 0
- stdout: non-empty markdown (≥ 200 chars)
- markdown contains query echo
- IF `OMNIGRAPH_LLM_PROVIDER` is set to a working provider AND KB has image candidates for the query: ≥ 1 inline image with non-filename alt text (e.g., `![A diagram showing ...](http://localhost:8765/.../5.jpg)`).
- IF LLM provider is unset OR no image candidates: Reasoner gracefully skips/fails, Synthesizer falls back to ar-1 behavior, full degradation note line shows up — exit code is still 0.
- port 8765 image server brought up on demand
- no stage raises; ResearchState dataclass populates all 5 stage fields

**This smoke test is environment-conditional** and is the orchestrator's responsibility to run AFTER this plan executes. It is NOT a Task 2 verification step (would require a working LLM provider configured locally), but capturing the command + expected outcomes here gives the orchestrator a paste-ready runbook.

Capture log to `.scratch/ar-2-03-smoke-260522.log` if executed.
</verification>

<success_criteria>

- ROADMAP § "Phase ar-2: Reasoner + vision deepening" Success Criterion #4: CLI accepts `--max-iter-reasoner`, `--max-iter-verifier`, and `--no-grounding` flags; values propagate into `ResearchConfig` and override defaults. ✓ delivered by Task 1; verified by Task 2 Tests 1-8.
- REQ CLI-03 (CLI overrides for max-iter-* + --no-grounding; LLM provider env-only) ✓ delivered.
- LIB-04 / Rule 1 (pure async entrypoint; CLI is a pure wrapper) ✓ preserved — no business logic added to `__main__.py`.
- ar-1 + ar-2-01 + ar-2-02 regression suite still green.
- CONTRACT-01 + CONTRACT-02 still clean.
- Upgraded Layer 2 smoke command becomes runnable; orchestrator-runnable manual verification step documented.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-2-reasoner-vision-deepening/ar-2-03-SUMMARY.md` documenting:
- Files modified + LOC count for each (rough proxy for plan-size sanity).
- Test count: total in `tests/unit/research/test_main_cli_flags.py` (split fast vs slow), total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (paste raw output — should be 0 forbidden hits).
- Pure-wrapper enforcement: paste output of `grep -E "^(import|from)" lib/research/__main__.py` and confirm only the 8 expected imports are present.
- ar-1 `test_main_cli.py` surgical edits: list each `_amain(...)` call updated, line-count delta, one-line rationale (or "no edits needed" if all ar-1 CLI tests passed unchanged because they used subprocess/CLI-style invocation rather than direct `_amain` calls).
- Test 9 (slow subprocess) result: command run, exit code, stdout char count, stderr excerpt if any.
- Upgraded Layer 2 smoke command status:
  - If executed by the executor (with a working LLM provider configured): paste `.scratch/ar-2-03-smoke-260522.log` excerpt — exit code, stdout char count, presence of inline images with non-filename alt text, presence of degradation notes.
  - If NOT executed (LLM provider unset locally): note this as a deferred manual step for the orchestrator, with the paste-ready command from `<verification>`.
- Any deviations from plan (with one-line rationale) — particularly:
  - Whether Test 9 was relaxed to `--max-iter-reasoner 0` due to flakiness.
  - Whether any unexpected ar-1 CLI test required updating beyond the planned `_amain(...)` signature change.
- Pure-wrapper LOC: paste the modified `_amain` body and confirm ≤ 18 non-comment non-blank lines.
</output>

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env
