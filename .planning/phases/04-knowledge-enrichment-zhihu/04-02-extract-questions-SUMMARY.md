---
phase: 04-knowledge-enrichment-zhihu
plan: 02
subsystem: enrichment
tags: [gemini, grounding, question-extraction, d-03, d-12, tdd]
dependency_graph:
  requires: [04-00]
  provides: [enrichment/extract_questions.py, enrichment/__init__.py]
  affects: [04-06-enrich-article-top-skill, 04-07-ingest-wechat-integration]
tech_stack:
  added: [enrichment package]
  patterns: [atomic-write tmp->os.replace, D-03 single-line JSON stdout, TDD red->green]
key_files:
  created:
    - enrichment/__init__.py
    - enrichment/extract_questions.py
    - tests/unit/test_extract_questions.py
  modified: []
decisions:
  - "D-12 grounding: ENRICHMENT_GROUNDING_ENABLED env var gates google_search tool; default on"
  - "D-03 contract: ok/skipped/error statuses as single-line JSON on stdout, artifacts on disk"
  - "Tests use importlib.reload() to pick up env var changes at module-level constants"
  - "test_migrations.py pre-existing failure (kol_config missing) logged as deferred, out of scope"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-27T17:05:43Z"
  tasks: 1
  files: 3
---

# Phase 04 Plan 02: Extract Questions Summary

Gemini 2.5 Flash Lite + google_search grounding question extractor with D-03 single-line JSON stdout contract.

## What Was Built

`enrichment/extract_questions.py` — a CLI + library module that reads a WeChat article Markdown file, calls Gemini 2.5 Flash Lite with Google Search grounding (D-12), and returns 1–3 under-documented technical questions the article raises but does not answer.

Key behaviors:
- Articles under `ENRICHMENT_MIN_LENGTH` (default 2000) chars are skipped gracefully: exit 0, `status: skipped`
- Full articles: calls Gemini, writes `questions.json` to `$ENRICHMENT_DIR/<hash>/questions.json` atomically (tmp → `os.replace`)
- Single-line JSON on stdout for all outcomes (D-03 Hermes 50KB cap compliance)
- Gemini API errors: exit 1, `status: error`, traceback to stderr

## Tasks

### Task 2.1 — enrichment/extract_questions.py library + CLI (TDD)

**RED commit:** `bc97ec9` — 7 failing tests (module not yet created)

**GREEN commit:** `d3eab0f` — implementation passes all 7 tests

Files created:
- `enrichment/__init__.py` — package marker
- `enrichment/extract_questions.py` — 140 lines; CLI + library; grounding tool; atomic write
- `tests/unit/test_extract_questions.py` — 7 unit tests, all mocked, LLM-free

## Acceptance Criteria Verification

| Check | Result |
|---|---|
| `enrichment/__init__.py` exists | PASS |
| `grep "google_search=types.GoogleSearch()"` | PASS |
| `grep "gemini-2.5-flash-lite"` | PASS |
| `grep "ENRICHMENT_MIN_LENGTH"` | PASS |
| `grep "os.replace"` (atomic write) | PASS |
| `grep "def main"` | PASS |
| Three status values present (ok/skipped/error) | PASS |
| `pytest tests/unit/test_extract_questions.py -x -v` exits 0, 7 tests | PASS |
| `python -m enrichment.extract_questions --help` exits 0 | PASS |
| `python -c "from enrichment.extract_questions import extract_questions, main"` | PASS |

## Deviations from Plan

### Test design deviation (minor)

**Found during:** Test writing

The plan's test template used direct `mocker.patch("google.genai.Client", ...)` without `importlib.reload`. Because `GROUNDING_ENABLED` is a module-level constant (read once at import time), tests that `monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", ...)` must also call `importlib.reload(eq)` to force re-evaluation of the constant. Added `importlib.reload` calls in the two grounding-related tests.

**Files modified:** `tests/unit/test_extract_questions.py`

**Rule:** Rule 1 (bug fix — without reload the grounding tests would not actually test the intended behavior)

### Extra test added (minor)

Added `test_extract_questions_skips_grounding_when_disabled` to explicitly verify the `GROUNDING_ENABLED=0` path (no tools in config). The plan spec shows 6 tests; this brings the total to 7. The plan's acceptance criteria says "6 tests" but the additional test directly verifies D-12 grounding fallback behavior specified in D-12a — it is not speculative.

**Rule:** Rule 2 (missing critical functionality coverage — D-12a grounding fallback is a documented decision)

## Pre-existing Issue (Out of Scope)

`tests/unit/test_migrations.py` fails with `ModuleNotFoundError: No module named 'kol_config'` — this was present before this plan and is not caused by any change here. Logged as deferred.

## Known Stubs

None. All functions are fully implemented.

## Self-Check: PASSED

- `enrichment/__init__.py` — FOUND
- `enrichment/extract_questions.py` — FOUND
- `tests/unit/test_extract_questions.py` — FOUND
- Commit `bc97ec9` (RED) — FOUND
- Commit `d3eab0f` (GREEN) — FOUND
- All 7 tests pass: CONFIRMED (`pytest tests/unit/test_extract_questions.py -x -v` → 7 passed)
