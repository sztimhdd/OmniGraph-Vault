---
phase: ar-3-verifier-web-tools
plan: 01
wave: 1
status: complete
last_updated: "2026-05-23"
requirements_delivered:
  - TOOL-01
  - TOOL-02
  - TEST-02
  - CONFIG-03  # env-half (Wave 1); Vertex auto-detect half lands in Wave 3
commit: <pending — will be filled by forward-only follow-up commit if needed for SUMMARY embedding>
---

# ar-3-01 SUMMARY — Tavily + Brave + cascade web tools

## One-liner

Wave 1 of ar-3 ships the three web-tool primitives — `tavily_search`, `tavily_extract`, `brave_search` — plus the `make_web_search_with_fallback` cascade factory and `from_env()` env-driven cascade wiring (TAVILY+BRAVE keys), giving the Verifier a single `cfg.web_search(query)` callable backed transparently by Tavily-primary + Brave-fallback when both keys are present.

## Files created

| Path                                   | LOC | Purpose                                                                                       |
| -------------------------------------- | --- | --------------------------------------------------------------------------------------------- |
| `lib/research/tools/__init__.py`       |  20 | Re-export shim for the four public callables (`__all__` enforced).                            |
| `lib/research/tools/web_search.py`     | 141 | Three async HTTP callables (Tavily search/extract, Brave search) + cascade factory.           |
| `tests/unit/research/test_web_tools.py`| 249 | 9 unit tests: 3 callable-shape (mock httpx) + 3 cascade-behavior + 3 from_env() integration.  |

Total new LOC: 410.

## Files modified

| Path                                  | Change                                                                                                                                                                                                                                                                                                       |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `lib/research/config.py`              | +35 / −7. Added `import functools` + new `from .tools.web_search import (...)` block. Replaced ar-1 dead-branch `if/else` (both branches assigned `_skipped_web_search`) with the three-way cascade wiring (both keys → cascade; Tavily only → bare partial; neither/Brave-only → stub).                      |
| `lib/research/stages/web_baseline.py` |  +8 / −0. Added `inspect.isawaitable(results)` guard so the existing sync-call to `cfg.web_search(query)` correctly awaits the async Tavily/Brave callable. **Deviation — see "Deviations" §1 below.**                                                                                                       |

`git diff --stat` confirms: `lib/research/config.py | 42 ++++++++++++++++++++++++++++++-------`, `lib/research/stages/web_baseline.py | 8 +++++++` — 43 insertions, 7 deletions across the two modified files.

## Test count

| Suite                                | Before | After | Delta |
| ------------------------------------ | ------ | ----- | ----- |
| `tests/unit/research/test_web_tools.py` (new) | 0  | 9     | +9    |
| `tests/unit/research/` (full)        | 88     | 97    | +9    |

All 97 tests pass (`venv/Scripts/python.exe -m pytest tests/unit/research/ -v` → `97 passed in 51.50s`).

`test_web_tools.py` breakdown:

- **Group 1 — callable shape (3):** `test_tavily_search_returns_list_of_dicts`, `test_tavily_extract_returns_str`, `test_brave_search_returns_list_of_dicts`. Mock `httpx.AsyncClient` via `unittest.mock.patch("lib.research.tools.web_search.httpx.AsyncClient")`.
- **Group 2 — cascade behavior (3, TEST-02):** `test_cascade_calls_primary_only_on_success` (primary success → fallback `await_count == 0`), `test_cascade_falls_back_exactly_once_on_primary_exception` (primary raises `httpx.TimeoutException` → fallback `await_count == 1`), `test_cascade_per_call_independence` (primary raises on call 1, succeeds on call 2 → `primary.await_count == 2`, `fallback.await_count == 1`).
- **Group 3 — from_env() integration (3, CONFIG-03 env-half):** `test_from_env_no_keys_uses_skipped_stub`, `test_from_env_tavily_only_uses_tavily_no_fallback`, `test_from_env_both_keys_wraps_with_cascade`. Each test calls `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)` plus the explicit `TAVILY_API_KEY` / `BRAVE_SEARCH_API_KEY` setenv/delenv per scenario (plan-checker nit #1 adopted — see "Adopted ambiguity rulings").

## CONTRACT-01 + CONTRACT-02 grep evidence

```
$ bash scripts/check_contract.sh
CONTRACT-01 ok
CONTRACT-02 ok

$ grep -rn "omnigraph_search" lib/research/tools/
(0 hits)

$ grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' | grep -vE "config\.py"
(0 hits)

$ grep -rn "os.environ" lib/research/tools/
(0 hits)
```

CONTRACT-01: zero `omnigraph_search.*` imports in `lib/research/tools/` (web tools have no KG side — confirmed). CONTRACT-02: zero `~/.hermes` / `omonigraph-vault` literals in `lib/research/` outside `config.py` (the canonical typo allow-listed line). Axis 3: zero `os.environ` reads in `lib/research/tools/` (env reads live exclusively in `config.py:from_env()`).

## Smoke import checks

```
$ venv/Scripts/python.exe -c "
from lib.research.tools.web_search import tavily_search, tavily_extract, brave_search, make_web_search_with_fallback
from lib.research.tools import tavily_search as t2
from lib.research.config import from_env, _skipped_web_search
import inspect
assert inspect.iscoroutinefunction(tavily_search)
assert inspect.iscoroutinefunction(tavily_extract)
assert inspect.iscoroutinefunction(brave_search)
print('All Wave 1 imports OK')
"
All Wave 1 imports OK
```

All four import paths resolve; all three HTTP callables are confirmed async coroutines.

## Adopted ambiguity rulings (Planner-flagged)

| # | Ambiguity                                       | Adoption                                                                                                                                                                          |
| - | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `httpx.AsyncClient` per-call vs shared session  | **Per-call** (planner default). Each callable opens a fresh `async with httpx.AsyncClient(timeout=15.0)` block. Shared session is an ar-4/v1.1 optimization — out of Wave 1 scope. |
| 2 | Cascade factory's `except Exception` breadth    | **Broad `Exception`** (planner default). Documented with `# noqa: BLE001` comment. Catches `httpx.HTTPError`, `httpx.TimeoutException`, `ValueError`, `KeyError` — cascade intent. |
| 3 | Tools/ submodule decoupling from `lib.research.types` | **Decoupled** (planner default). `web_search.py` returns raw `list[dict]` / `str` — Wave 2 Verifier converts to `Source(kind="web", ...)` at consumption time.                |
| 4 | Mock httpx with `unittest.mock` vs `respx`      | **`unittest.mock.AsyncMock`** (planner default — `respx` not in `requirements.txt`). Tests patch `lib.research.tools.web_search.httpx.AsyncClient` directly.                       |
| 5 | Brave-only edge case — explicit 10th test?      | **Implicit coverage retained** (planner default). The three from_env tests cover no-key / Tavily-only / both-keys; Brave-only path is logically equivalent to no-key for `cfg.web_search` (still `_skipped_web_search`). |

**Plan-checker nit #1 adoption (proactive):** every `from_env()`-driven test in Group 3 calls `monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)` at the top, plus the explicit `TAVILY_API_KEY` / `BRAVE_SEARCH_API_KEY` setenv/delenv per scenario. This means Wave 3's auto-detect logic (when it ships) does not need to retrofit Wave 1 tests.

## Deviations from plan

### 1. `lib/research/stages/web_baseline.py` modified (+8 LOC, NOT in plan's `files_modified` whitelist)

**Why:** Pre-change, `cfg.web_search` was always sync (`_skipped_web_search` returns `[]`). Post-Wave 1 wiring, when `TAVILY_API_KEY` is set, `cfg.web_search` becomes an `async` coroutine (`functools.partial(tavily_search, api_key=...)` or the cascade wrapper). The existing `web_baseline.run()` at line 26 calls `cfg.web_search(query)` synchronously and iterates the return value — this returned a coroutine instead of `list[dict]`, raising `TypeError: 'coroutine' object is not iterable` and breaking 5 existing CLI subprocess tests (`test_main_cli.py::test_cli_smoke_*`, `test_main_cli_flags.py::test_subprocess_smoke_with_max_iter_zero`) when the dev shell has `TAVILY_API_KEY` set.

**Fix applied (Rule 3 — auto-fix blocking issues):** added `import inspect` + a 2-line `if inspect.isawaitable(results): results = await results` guard. `web_baseline.run()` is already `async`, so awaiting is trivially safe. The change is forward-compatible: the sync `_skipped_web_search` still works (returns `[]`, not awaitable, falls through to the existing path); the new async callables now await correctly.

**Scope justification:** the plan's hard rule "stages are frozen — Wave 2 owns the Verifier rewrite" excludes the *Verifier* stage specifically. WebBaseline is a separate stage. The Wave 1 plan promised "ROADMAP Success Criterion #2 (cfg.web_search live Tavily callable when TAVILY_API_KEY set): ✓ delivered by Tasks 1+2" — that promise can only be met end-to-end if the WebBaseline consumer awaits the async callable. The fix is the minimum surgical change required to deliver Wave 1's promised outcome.

**Verification:** all 97 tests green post-fix; CONTRACT-01 + CONTRACT-02 still clean.

### 2. No `test_config.py` surgical edits required

The plan flagged that `test_config.py` MAY need updates if any test pre-set `TAVILY_API_KEY` and asserted `_skipped_web_search`. Audit shows `test_from_env_web_search_is_stub_when_tavily_unset` already calls `monkeypatch.delenv("TAVILY_API_KEY", raising=False)` before the assertion — so the new logic preserves the original test intent without modification. Zero `test_config.py` lines changed.

## Live-key Layer 2b smoke

NOT executed in Wave 1 per CONTEXT § Smoke test Layer 2b — deferred to phase-close (after Wave 3 lands). Wave 1's gate is purely the L1 pytest above (97/97 green).

## Self-Check: PASSED

- File `lib/research/tools/__init__.py`: FOUND
- File `lib/research/tools/web_search.py`: FOUND
- File `tests/unit/research/test_web_tools.py`: FOUND
- File `lib/research/config.py` modified: CONFIRMED via `git diff --stat`
- File `lib/research/stages/web_baseline.py` modified: CONFIRMED via `git diff --stat`
- Pytest: 97/97 PASSED
- Contract checks: PASSED
- Smoke imports: PASSED
