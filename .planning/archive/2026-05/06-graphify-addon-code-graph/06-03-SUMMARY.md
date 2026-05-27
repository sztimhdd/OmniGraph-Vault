---
phase: 06-graphify-addon-code-graph
plan: "03"
subsystem: omnigraph_search-skill
tags: [skill, lightrag, hermes, openclaw, query, disambiguation]
dependency_graph:
  requires: [06-00]
  provides: [skills/omnigraph_search, omnigraph_search/query.py, tests/skills/test_omnigraph_search.json]
  affects: []
tech_stack:
  added: []
  patterns: [lightrag-hybrid-query, hermes-skill-directory, bash-venv-wrapper]
key_files:
  created:
    - tests/skills/test_omnigraph_search.json
    - skills/omnigraph_search/SKILL.md
    - skills/omnigraph_search/scripts/query.sh
    - skills/omnigraph_search/references/api-surface.md
    - omnigraph_search/__init__.py
    - omnigraph_search/query.py
  modified: []
decisions:
  - "D-G09 honored: omnigraph_search/query.py is a trimmed copy of query_lightrag.py with no Cognee, no get_rag() helper"
  - "chmod +x skipped on Windows — git sets executable bit in index (test -x passes via Git Bash)"
  - "Added omnigraph_search/__init__.py to make the directory a proper Python package for python -m invocation"
metrics:
  duration_minutes: 9
  tasks_completed: 4
  files_created: 6
  files_modified: 0
  completed_date: "2026-04-28"
---

# Phase 6 Plan 03: omnigraph_search Skill Implementation Summary

**One-liner:** LightRAG hybrid-mode search skill with SKILL.md disambiguation, bash wrapper, API reference doc, and importable query.py — no Cognee, no synthesis layer (D-G09).

## Files Written

| File | Lines | Purpose |
|------|-------|---------|
| `tests/skills/test_omnigraph_search.json` | 48 | 8 routing test cases: golden path + 5 sibling disambiguation + 2 guard/mode cases |
| `skills/omnigraph_search/SKILL.md` | 115 | Full skill body: frontmatter, Quick Reference, Decision Tree, When-to-Use/NOT, Error Handling, Related Skills |
| `skills/omnigraph_search/scripts/query.sh` | 65 | Bash wrapper: 6-step pattern (root resolve, env load, arg validate, GEMINI_API_KEY check, venv activate, python -m run) |
| `skills/omnigraph_search/references/api-surface.md` | 81 | API reference: CLI interface, env vars, modes, exit codes, error messages, runtime paths |
| `omnigraph_search/__init__.py` | 1 | Package marker to enable `python -m omnigraph_search.query` invocation |
| `omnigraph_search/query.py` | 109 | LightRAG wrapper: async search(), main() CLI, RAG_WORKING_DIR, QueryParam(mode=mode) |

## Commits

| Task | Hash | Message |
|------|------|---------|
| 3.1 | `b6b3c01` | test(06-03): add 8 routing test cases for omnigraph_search skill |
| 3.2 | `738dbfc` | feat(06-03): add omnigraph_search SKILL.md with full body and disambiguation |
| 3.3 | `1fb4725` | feat(06-03): add omnigraph_search query.sh and api-surface.md |
| 3.4 | `9816b0c` | feat(06-03): implement omnigraph_search/query.py LightRAG hybrid-mode wrapper |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written with the following minor deviation:

**1. [Rule 2 - Missing critical file] Added omnigraph_search/__init__.py**
- **Found during:** Task 3.4
- **Issue:** `python -m omnigraph_search.query` requires the directory to be a Python package (needs `__init__.py`). Without it the `-m` flag would fail with `No module named omnigraph_search`.
- **Fix:** Created a 1-line `__init__.py` package marker.
- **Files modified:** `omnigraph_search/__init__.py`
- **Commit:** `9816b0c`

**2. [Note - Windows] chmod +x not applicable**
- `chmod +x skills/omnigraph_search/scripts/query.sh` was skipped — Windows NTFS does not support Unix executable bits.
- `test -x` still passes in Git Bash because Git for Windows emulates executable mode from the index.
- When deployed to remote WSL2 Linux via `git pull`, the executable bit will be set correctly if the file was staged with `git update-index --chmod=+x` or if the umask allows it. This is tracked as a known platform difference, not a defect.

## Collateral Damage Check

The following files were NOT modified (surgical change principle verified):

- `kg_synthesize.py` — unchanged
- `query_lightrag.py` — unchanged
- `config.py` — unchanged
- `skills/omnigraph_query/*` — unchanged (back-reference to omnigraph_search deferred to Plan 06-03b)

Verified with: `git diff HEAD~4 -- kg_synthesize.py query_lightrag.py config.py skills/omnigraph_query/`

## Live Smoke Testing Status

**Deferred to Plan 06-03b** (as designed).

Plan 06-03 covers file authoring and import/syntax validation only. Full runtime validation (`skill_runner --validate`, `skill_runner --test-file`, live LightRAG query) happens in Plan 06-03b, which depends on:
1. Plan 06-02 having seeded the remote code graph
2. Remote LightRAG storage confirmed non-empty

## Known Stubs

None — all files are fully implemented. The `search()` function has a real LightRAG call (not mocked), the SKILL.md body satisfies all routing assertions in the test JSON, and the shell wrapper covers both Windows and Linux venv paths.

## Verification Summary

All acceptance criteria passed:

- `python -c "import json; assert len(json.load(open('tests/skills/test_omnigraph_search.json'))) == 8"` — exit 0
- `grep -c "omnigraph_query|graphify|omnigraph_ingest|omnigraph_status|omnigraph_manage" tests/skills/test_omnigraph_search.json` — returned 11 (>= 5)
- `grep -q "^name: omnigraph_search$" skills/omnigraph_search/SKILL.md` — exit 0
- `wc -l skills/omnigraph_search/SKILL.md` — 115 lines (>= 80)
- `bash -n skills/omnigraph_search/scripts/query.sh` — exit 0
- `grep -q "python -m omnigraph_search.query"` — exit 0
- `grep -q "Entry Point" skills/omnigraph_search/references/api-surface.md` — exit 0
- No cognee in api-surface.md or query.py — confirmed
- `python -c "import omnigraph_search.query"` — exit 0
- `search` is async coroutine — confirmed
- `python -m omnigraph_search.query` (no args) — prints Usage to stderr, exit 1

## Self-Check: PASSED
