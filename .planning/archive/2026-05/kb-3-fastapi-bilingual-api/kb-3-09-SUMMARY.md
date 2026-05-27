---
phase: kb-3-fastapi-bilingual-api
plan: 09
subsystem: services/synthesize
tags: [QA-04, QA-05, SEARCH-01, fts5_fallback, NEVER-500]
status: complete
completed: 2026-05-14
---

# kb-3-09 — FTS5 Fallback + Timeout — Execution Summary

## Skills invoked

- `Skill(skill="python-patterns", args="Replace the broad except branch in kb_synthesize with two-stage handling: (1) wrap synthesize_response in asyncio.wait_for(..., timeout=KB_SYNTHESIZE_TIMEOUT) — TimeoutError caught explicitly; (2) general Exception catches everything else. Both call the same _fts5_fallback helper with a `reason` arg. _fts5_fallback queries fts_query(question, limit=3) — cross-lang for graceful degradation — concats top-3 (title + snippet) into markdown with a banner. The banner copy uses the SAME locale key concept as qa.fallback.explainer (kb-3-03) but is hard-coded bilingual in the markdown for non-i18n contexts (Hermes agent skill consumers). Last-resort: if fts_query itself raises (DB unavailable), still set job status='done' with confidence='no_results' — /api/synthesize MUST NEVER 500. Type hints throughout.")` — produced the two-stage exception handling structure + asyncio.wait_for placement + cross-lang FTS query for graceful degradation.

- `Skill(skill="writing-tests", args="Extend test_synthesize_wrapper.py with 5 fallback-path tests. Cover: exception path → fts5_fallback, timeout path → fts5_fallback (use sleep > timeout), top-3 hits in result, sources list populated, FTS5-also-fails → no_results last-resort. For the timeout test, set KB_SYNTHESIZE_TIMEOUT=1 and patch synthesize_response with `await asyncio.sleep(2)` — must time out within 2s wall-time. Extend test_api_synthesize.py with 3 API-level integration tests verifying /api/synthesize returns 202 + eventually 200/done with confidence='fts5_fallback' (never 500). Reuse the populated articles_fts fixture pattern from test_api_search.py.")` — drove the 5 unit-level fallback test cases + 3 API-level integration tests, all hitting real SQLite + real FTS5 (no mocks of the search index).

## Implementation

`kb/services/synthesize.py` extended with:

- `KB_SYNTHESIZE_TIMEOUT: int = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))` — env-overridable per CONFIG-02
- `_fts5_fallback(question, lang, job_id, reason)` helper:
  - Calls `fts_query(question, limit=3)` from `kb.services.search_index` (kb-3-06)
  - cross-lang query (lang=None) for graceful degradation when target-lang fails
  - Concats top-3 (title + snippet) into markdown with bilingual banner
  - Last-resort `try/except` around `fts_query` itself: if SQLite/FTS5 dies, still sets `confidence='no_results'` (NEVER 500)
- `kb_synthesize` two-stage exception handling:
  - Stage 1: `asyncio.wait_for(synthesize_response(...), timeout=KB_SYNTHESIZE_TIMEOUT)` → on `asyncio.TimeoutError` → `_fts5_fallback(reason='timeout')`
  - Stage 2: `except Exception` → `_fts5_fallback(reason='exception')`
  - Both paths set `status='done'`, `fallback_used=True`, `confidence='fts5_fallback'` (or `'no_results'` on catastrophic FTS5 failure)

C1 contract preserved verbatim — `kg_synthesize.synthesize_response` signature untouched.

## Tests

8 new tests across 2 files:

| File | Tests | What |
|---|---|---|
| `tests/integration/kb/test_synthesize_wrapper.py` | 5 unit-level | timeout→fallback, exception→fallback, top-3 hits, sources list, fts5-also-fails→no_results |
| `tests/integration/kb/test_api_synthesize.py` | 3 API-level | timeout path → 200 done + fts5_fallback, exception path → 200 done + fts5_fallback, catastrophic path → 200 done + no_results (NEVER 500) |

```bash
$ venv/Scripts/python.exe -m pytest tests/integration/kb/test_synthesize_wrapper.py tests/integration/kb/test_api_synthesize.py -q
25 passed in 7.96s
```

## Acceptance criteria status

- [x] `kb/services/synthesize.py` wraps C1 call in `asyncio.wait_for` + try/except → fallback
- [x] On timeout (KB_SYNTHESIZE_TIMEOUT default 60s): job ends `done`, `fallback_used=True`, `confidence='fts5_fallback'`, NEVER 500
- [x] On LightRAG exception: same fallback path
- [x] On FTS5 itself unavailable (catastrophic): `confidence='no_results'`, still HTTP 200 from poll
- [x] Tests cover synthesize-success path (no fallback — kb-3-08 baseline), timeout-fallback, exception-fallback, double-failure
- [x] kb-3-04/05/06/07/08 baselines still pass (no regression — verified isolation)
- [x] Skill literal strings present (this SUMMARY + module docstring of kb/services/synthesize.py + commit message of cfc7a9e)
- [x] Commits with --no-verify + explicit `git add` (no `git add -A`)

## Commits

- `2d6679d` test(kb-3-09): add failing tests for FTS5 fallback + timeout (RED)
- `cfc7a9e` feat(kb-3-09): FTS5 fallback + KB_SYNTHESIZE_TIMEOUT in kb_synthesize (GREEN)
- `060447f` test(kb-3-09): add 3 API-level integration tests for FTS5 fallback (deferred from cfc7a9e)

## Notes / deferrals

The agent that executed kb-3-09 did not get to the docs commit before the session ended — this SUMMARY is being written orchestrator-side at session resume time. Implementation + tests + Skill discipline regex are all green; only the SUMMARY artifact was missing. Test additions (+117 LOC) for `test_api_synthesize.py` were also uncommitted at session-end and are committed in `060447f` to close kb-3-09 cleanly.

REQUIREMENTS-KB-v2.md update for QA-04 + QA-05 was not yet applied at the time of this SUMMARY; the kb-3 phase verifier (kb-3-12 Wave 5) will pick it up.
