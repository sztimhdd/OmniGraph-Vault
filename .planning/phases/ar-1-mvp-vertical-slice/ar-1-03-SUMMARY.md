---
phase: ar-1-mvp-vertical-slice
plan: 03
subsystem: agentic-rag-v1
tags: [cli, image-server, packaging, editable-install, smoke-test]
requires:
  - python>=3.11
  - lib/research/orchestrator.py (ar-1-02 — 5-stage pipeline wired)
  - lib/research/config.py (ar-1-01 — from_env factory)
provides:
  - editable install of omnigraph.research namespace alias for lib/research
  - lib/research/image_server.py — idempotent ensure_image_server() bring-up
  - lib/research/__main__.py — CLI entrypoint (argparse + asyncio.run + print)
  - 16 new unit tests (8 image_server + 8 main_cli; 4 of main_cli are slow)
  - 'slow' pytest marker registered in pyproject.toml
  - Port-8765 image HTTP server (production target) auto-bring-up wired into CLI
affects:
  - pyproject.toml (explicit packages list + slow marker registration)
  - .gitignore (added *.egg-info/)
tech-stack:
  added:
    - editable install (`pip install -e .`) for namespace mapping resolution
    - subprocess detached spawn (`CREATE_NEW_PROCESS_GROUP` on Windows / `start_new_session` on POSIX)
    - sys.stdout.reconfigure('utf-8') for Windows CJK output safety
  patterns:
    - port-probe-before-spawn idempotency
    - pure-wrapper rule (only argparse + asyncio + sys + 3 sibling imports allowed in __main__)
    - subprocess-spawn slow integration tests (`-m slow` opt-in)
key-files:
  created:
    - lib/research/image_server.py
    - lib/research/__main__.py
    - tests/unit/research/test_image_server.py
    - tests/unit/research/test_main_cli.py
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-03-SUMMARY.md
  modified:
    - pyproject.toml
    - .gitignore
decisions:
  - "Switched [tool.setuptools.packages.find] to [tool.setuptools] explicit packages list — the original ar-1-01 package-dir alias did not surface omnigraph.research because the editable finder MAPPING only included physically-existing roots (lib, omnigraph_search). Explicit list pins the alias."
  - "ensure_image_server raises FileNotFoundError on missing base_image_dir BEFORE spawn — refusing to point a server at a non-existent dir is safer than spawning a confused server."
  - "CLI adds sys.stdout.reconfigure('utf-8') guard (1 line over plan's ≤50 LOC budget). Without it, `python -m omnigraph.research \"什么是 ...\"` raises UnicodeEncodeError on Windows cp1252 console. Rule 2 deviation."
  - "Slow integration tests are gated by `-m slow` (newly registered marker) — default pytest run stays fast (58 tests in <8s); operator opts into the 37s subprocess-spawn integration suite explicitly."
  - "Layer 2 smoke test acceptance honors Axis 3: Retriever failure (Embedding dim mismatch — known prod KB issue from kb-3 lesson) surfaces as degradation note, not a raise. The smoke test's 'no stage raises' criterion passes because every stage caught its own exception."
metrics:
  duration_seconds: 1620
  duration_human: "~27 minutes"
  tasks_completed: 4
  files_created: 5
  files_modified: 2
  unit_tests_added: 16
  unit_tests_total_fast: 58
  unit_tests_total_with_slow: 62
  unit_test_pass_rate_fast: "58/58 (100%)"
  unit_test_pass_rate_slow: "4/4 (100%)"
  cli_main_loc: 51
  smoke_log_bytes: 638
  smoke_exit_code: 0
  completed: "2026-05-22"
requirements_satisfied:
  - ORCH-08
  - CLI-01
---

# Phase ar-1 Plan 03: CLI + Image Server Summary

CLI entrypoint `python -m omnigraph.research "<query>"` is now live end-to-end.
The 5-stage pipeline (wired in ar-1-02) emits non-empty markdown to stdout
with all degradation notes surfaced (Axis 8), and the local image HTTP
server on port 8765 is auto-brought-up before `research()` runs (ORCH-08).

`pip install -e .` makes the `omnigraph.research` namespace alias resolvable
for `runpy`-style `-m` invocation. 16 new unit tests across 2 files; 58 fast
+ 4 slow-gated integration tests pass; both CONTRACT grep hooks clean.

## Files Created (4) + Modified (2)

| File | Role |
|---|---|
| `lib/research/image_server.py` | Idempotent `ensure_image_server(base_image_dir, port=8765)` — port-probe-before-spawn, detached subprocess, FileNotFoundError on missing dir |
| `lib/research/__main__.py` | CLI entrypoint — argparse + asyncio.run + UTF-8 print (51 LOC, pure wrapper) |
| `tests/unit/research/test_image_server.py` | 8 unit tests covering port-probe truthiness, spawn/no-spawn paths, idempotency, exact argv shape, missing-dir guard, detached kwargs |
| `tests/unit/research/test_main_cli.py` | 8 tests — 4 fast (help, argparse rejection, programmatic main return None, pure-wrapper import audit) + 4 slow (subprocess CLI smoke: ≥200 chars stdout, query echo, degradation note, port 8765 listening) |
| `pyproject.toml` | **modified** — replaced `[tool.setuptools.packages.find]` with explicit `[tool.setuptools] packages = [...]` list to surface `omnigraph.research` namespace alias; registered `slow` pytest marker |
| `.gitignore` | **modified** — added `*.egg-info/` so editable install artifacts don't leak into commits |

## Test Results

```
$ venv/Scripts/python.exe -m pytest tests/unit/research/ -v -m "not slow"
======================= 58 passed, 4 deselected in 7.83s ======================

$ venv/Scripts/python.exe -m pytest tests/unit/research/test_main_cli.py -v -m "slow"
====================== 4 passed, 4 deselected in 37.46s =======================
```

| File | Tests | Pass |
|---|---|---|
| `test_types.py` (carried) | 10 | 10 |
| `test_config.py` (carried) | 11 | 11 |
| `test_stages_stubs.py` (carried) | 20 | 20 |
| `test_orchestrator.py` (carried) | 5 | 5 |
| `test_image_server.py` (**new**) | 8 | 8 |
| `test_main_cli.py` (**new** — 4 fast + 4 slow) | 8 | 8 |
| **Total** | **62** | **62** |

## CONTRACT Enforcement

```
$ bash scripts/check_contract.sh
CONTRACT-01 ok
CONTRACT-02 ok
```

- CONTRACT-01: `lib/research/image_server.py` and `lib/research/__main__.py` add ZERO new imports from `omnigraph_search.*` (the only existing one remains `from omnigraph_search.query import search` in `retriever.py`).
- CONTRACT-02: zero hardcoded `~/.hermes` / `omonigraph-vault` literals outside `config.py`. The CLI consumes `cfg.rag_working_dir.parent / "images"` — no string literals.

## Layer 2 Smoke Test (CONTEXT.md acceptance)

Command:
```
venv/Scripts/python.exe -m omnigraph.research "什么是 Hermes Harness 深度解析" \
  > .scratch/ar-1-03-smoke-260522.log 2>&1
```

| Acceptance criterion | Result |
|---|---|
| Exit code 0 | **0** |
| stdout ≥ 200 chars | **638 bytes / 570 chars** |
| Query echo present | `# 关于「什么是 Hermes Harness 深度解析」的研究答复` — present |
| ≥ 1 degradation note line | **4 lines** — `WebBaseline skipped`, `Retriever failed`, `Reasoner skipped`, `Verifier skipped` |
| Port 8765 listening after run | LISTENING — HTTP HEAD `/` returns `200 OK` |
| All 5 ResearchState fields populated | True (web_baseline + retrieved + reasoned + verified + synthesized) |
| No stage raises | True — Retriever caught the embedding-dim-mismatch and surfaced via `status="failed"` (Axis 3) |

Excerpt of the log (utf-8 decoded):
```
# 关于「什么是 Hermes Harness 深度解析」的研究答复
## 知识图谱检索结果

(no chunks retrieved)


---

> ℹ️ WebBaseline skipped: web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)
> ❌ Retriever failed: Embedding dim mismatch, expected: 3072, but loaded: 768
> ℹ️ Reasoner skipped: ar-1 stub — agent loop lands in ar-2
> ℹ️ Verifier skipped: ar-1 stub — verifier loop lands in ar-3
```

The Retriever failure is the prod KB's known embedding-dim-mismatch (kb-3 lesson, CLAUDE.md Lessons Learned 2026-05-14): `vdb_chunks.json` was loaded at 768 dims while LightRAG was configured for 3072 dims. This is a real-world prod state, not a bug in this plan — the orchestrator's Axis 3 best-effort handler caught it cleanly and the synthesizer surfaced it as a degradation note. Smoke acceptance criterion "no stage raises" passes because every stage's `try`/`except` worked as designed.

## Port 8765 Probe Before vs After

| Time | State | Cause |
|---|---|---|
| Before slow integration tests ran | (free) | first session start of the day |
| After `test_cli_brings_up_image_server` | LISTENING | the slow integration test brought it up via `ensure_image_server` |
| Before Layer 2 smoke run | LISTENING | leftover from the previous step (idempotent — second invocation sees port busy and returns None) |
| After Layer 2 smoke run | LISTENING | `ensure_image_server` returned None (idempotent); existing server continued |

Idempotency confirmed: re-running the CLI never spawns a duplicate server.

## Commits (3 + this SUMMARY)

| Hash | Message |
|---|---|
| `17afeaa` | chore(ar-1-03): pin omnigraph.research namespace via explicit packages list |
| `756e71c` | feat(ar-1-03): add image_server.py with idempotent ensure_image_server() + 8 tests |
| `6070071` | feat(ar-1-03): add __main__.py CLI entrypoint + 8 tests (4 fast, 4 slow) |
| (this) | docs(ar-1-03): SUMMARY |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pyproject.toml namespace alias didn't actually surface `omnigraph.research`**

- **Found during:** Task 0 verification (`pip install -e .` succeeded but `from omnigraph.research import research` raised `ModuleNotFoundError`)
- **Issue:** ar-1-01 declared `[tool.setuptools.package-dir]` `"omnigraph.research" = "lib/research"` but combined with `[tool.setuptools.packages.find]` `include = ["lib", "lib.*", "omnigraph_search", "omnigraph_search.*"]`. The editable install's finder `MAPPING` dict was therefore `{'lib': ..., 'omnigraph_search': ...}` — the `package-dir` alias was ignored because no `omnigraph` or `omnigraph.research` entry was discovered by `find`. Without this, Task 0's verify (`from omnigraph.research import research`) and Task 2's `python -m omnigraph.research` both fail.
- **Fix:** Replaced the `find` config with an explicit `[tool.setuptools]` `packages = [...]` list including `"omnigraph.research"` and `"omnigraph.research.stages"`, plus `package-dir` mapping for both. Verified `from omnigraph.research import research` succeeds. This is technically a fix to ar-1-01's deliverable, but Task 0's plan body explicitly says "ar-1-01 declares the namespace mapping in pyproject.toml but does NOT install editable" — the assumption was that the declaration would work once the install ran. It didn't. Surgical fix scoped to the two `[tool.setuptools]` tables.
- **Files modified:** `pyproject.toml`
- **Commit:** `17afeaa`

**2. [Rule 2 - Critical functionality] CLI must reconfigure stdout to UTF-8 on Windows**

- **Found during:** mental model trace of Task 3's smoke test on Windows
- **Issue:** The synthesizer emits CJK in the title (`# 关于「{query}」...`). On Windows, `print()` writes through the default cp1252 console codepage, which raises `UnicodeEncodeError` on any character outside Latin-1 — including all CJK. Without a fix, the smoke test crashes before exiting and the entire Task 3 acceptance fails on `什么是 Hermes Harness 深度解析`.
- **Fix:** Added a 1-line `try: sys.stdout.reconfigure(encoding="utf-8")` guard right before `print(markdown)`. This pushes `__main__.py` from 50 LOC to 51 LOC — 1 line over the plan's `< 50` budget. Net: +1 LOC, but the smoke query now round-trips cleanly. The fix is isolated to a single line at the bottom of `main()`; no business logic added.
- **Files modified:** `lib/research/__main__.py`
- **Commit:** `6070071`

**3. [Rule 3 - Blocking] `slow` pytest marker not registered in pyproject.toml**

- **Found during:** first `pytest` run on `test_main_cli.py`
- **Issue:** Several existing tests in the repo (e.g., `test_ainsert_persistence_contract.py`) use `@pytest.mark.slow` but the marker was never registered in pyproject.toml's `[tool.pytest.ini_options]` markers list. Pytest emitted `PytestUnknownMarkWarning` for every slow test — non-blocking on its own, but `pytest -m slow` selection works regardless. Registering it fixes the warnings AND aligns with the plan's expectation that `-m slow` is a first-class opt-in flag.
- **Fix:** Added `"slow: tests that spawn subprocesses or hit live deps; opt in with \`-m slow\`"` to the markers list. The plan referenced `--run-slow` as the gating mechanism, but no such flag exists in this repo's pyproject.toml or conftest.py — the canonical pattern here is `pytest -m slow` (mark-based selection), so I used that instead. No `pytest_addoption` or `pytest_collection_modifyitems` hook was needed.
- **Files modified:** `pyproject.toml`
- **Commit:** folded into `6070071` (the introducing commit for slow tests)

### Plan-text deviations (no code change needed)

**4. Plan referenced `--run-slow` flag; this repo uses `-m slow` selection instead**

- The plan's verify line for Task 2 says `pytest tests/unit/research/test_main_cli.py -v --run-slow`. There is no `--run-slow` custom flag registered in this repo's conftest.py or pyproject.toml, and adding one would require a `pytest_addoption` + `pytest_collection_modifyitems` hook in a new conftest.py — out of scope for ar-1-03 and inconsistent with the existing `@pytest.mark.slow` usage in `test_ainsert_persistence_contract.py`. I substituted the canonical mark-based pattern: `pytest -m slow` to opt in, default run skips. Plan acceptance is unchanged (all 8 tests still pass; slow tests still gated).

## Self-Check: PASSED

All claimed files exist (verified via `Read`/`ls`):

- `lib/research/image_server.py` — present, 70 lines
- `lib/research/__main__.py` — present, 51 lines
- `tests/unit/research/test_image_server.py` — present, 8 tests
- `tests/unit/research/test_main_cli.py` — present, 8 tests (4 fast / 4 slow)
- `pyproject.toml` — modified (explicit packages list + slow marker)
- `.gitignore` — modified (`*.egg-info/`)
- `.scratch/ar-1-03-smoke-260522.log` — present, 638 bytes

All claimed commits exist in `git log --oneline`:
- `17afeaa`, `756e71c`, `6070071` — verified

All claimed verifications pass:
- `pytest tests/unit/research/ -m "not slow"` → 58 passed, 4 deselected
- `pytest tests/unit/research/test_main_cli.py -m slow` → 4 passed
- `bash scripts/check_contract.sh` → exit 0, both CONTRACT-01 + CONTRACT-02 ok
- `python -c "from omnigraph.research import research"` → exit 0
- `python -m omnigraph.research "什么是 Hermes Harness 深度解析"` → exit 0, 638-byte log
- Inline state assertion (all 5 ResearchState fields populated) → True
- Port 8765 HTTP HEAD → 200 OK

## L2 smoke status: PASS

- exit 0
- 638-byte / 570-char log (well above ≥200 acceptance)
- query echo present
- 4 degradation note lines (3 skipped + 1 failed)
- port 8765 LISTENING after run, HTTP 200 OK
- all 5 ResearchState fields populated
- no stage raises (Retriever's embedding-dim-mismatch caught by Axis 3 try/except)
- ar-1-04 (skill packaging) may proceed
