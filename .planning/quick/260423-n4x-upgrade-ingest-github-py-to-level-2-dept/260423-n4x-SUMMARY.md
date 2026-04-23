---
task_id: 260423-n4x
type: quick
phase: quick
plan: n4x
subsystem: ingestion
tags: [lightrag, github, ingestion, multi-segment]
files_modified:
  - ingest_github.py
commits:
  - f970a03
  - ea49568
duration_minutes: 12
completed_date: "2026-04-23"
---

# Quick Task 260423-n4x: Upgrade ingest_github.py to Level 2 Multi-Segment Ingestion

**One-liner:** Replaced monolithic `fetch_repo_content()` with 5 focused segment fetchers (`_fetch_identity`, `_fetch_docs`, `_fetch_releases`, `_fetch_deps`, `_fetch_top_issues`), each calling `rag.ainsert()` separately for cleaner LightRAG entity extraction.

---

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Refactor fetch_repo_content into segment fetchers + multi-segment ingest | f970a03 | Done |
| 2 | Smoke test with a real repo (NousResearch/hermes-agent) | ea49568 | Done |

---

## What Changed

**`ingest_github.py`** (net +103 lines / -10 lines):

- Removed `fetch_repo_content()` (monolithic blob builder)
- Added 5 segment fetch functions:
  - `_fetch_identity(org, repo)` — metadata, tree, README
  - `_fetch_docs(org, repo)` — `.md`/`.rst` files from `docs/`
  - `_fetch_releases(org, repo)` — last 5 releases with notes
  - `_fetch_deps(org, repo)` — first of `requirements.txt`, `pyproject.toml`, `package.json`
  - `_fetch_top_issues(org, repo)` — top 10 issues by reaction count, PRs filtered out
- Updated `ingest_github()` to build a `segments` list, call `rag.ainsert()` per non-None segment
- Dedup hash computed on combined content of all segments (backward-compatible)
- Registry entry now includes `"segments": [...]` list

**Smoke test result (hermes-agent):** 4 segments fetched — `identity`, `releases`, `deps`, `issues`. `docs` skipped (no `docs/` directory — correct graceful skip).

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Windows cp1252 UnicodeDecodeError in `_gh_api()`**
- **Found during:** Task 2 smoke test
- **Issue:** `subprocess.run(..., text=True)` with no `encoding` argument used the Windows system default (`cp1252`). GitHub API responses containing non-ASCII characters (Hermes-agent releases include Unicode emoji) caused the reader thread to crash with `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90`. This made `result.stdout` come back as `None`, which caused `json.loads(None)` to raise `TypeError`, caught by the generic `except Exception` — silently returning `None` for the releases and issues endpoints.
- **Fix:** Added `encoding="utf-8"` to `subprocess.run()` in `_gh_api()`.
- **Files modified:** `ingest_github.py` (1 line)
- **Commit:** ea49568
- **Impact:** Without the fix, only 2 segments (identity + deps) were ingested. With the fix, 4 segments (identity, releases, deps, issues) were ingested for hermes-agent.

---

## Success Criteria Verification

- [x] 5 segment fetchers in `ingest_github.py` (`_fetch_identity`, `_fetch_docs`, `_fetch_releases`, `_fetch_deps`, `_fetch_top_issues`)
- [x] Each non-None segment inserted via separate `rag.ainsert()` call
- [x] Dedup hash computed on combined content (backward-compatible)
- [x] Registry entry includes `"segments"` list
- [x] Graceful fallback: `docs/` missing returns None, no releases/issues return None — all skip silently
- [x] Old monolithic `fetch_repo_content()` removed
- [x] Smoke test passed: hermes-agent ingested with 4 segments; `identity` + >=1 other

---

## Self-Check

Files:
- `ingest_github.py` — modified in place (verified via Read tool)
- `.planning/quick/260423-n4x-upgrade-ingest-github-py-to-level-2-dept/260423-n4x-SUMMARY.md` — this file

Commits:
- `f970a03` — Task 1 refactor
- `ea49568` — Rule 1 fix + smoke test confirmation

## Self-Check: PASSED
