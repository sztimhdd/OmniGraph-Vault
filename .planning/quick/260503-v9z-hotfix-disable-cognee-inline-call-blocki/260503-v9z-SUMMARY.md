---
quick_id: 260503-v9z
type: execute
status: complete
completed: 2026-05-03
commits:
  - e2d16e4 fix(ingest): gate cognee remember_article behind OMNIGRAPH_COGNEE_INLINE (default off)
  - 3f6d065 test(ingest): unit coverage for OMNIGRAPH_COGNEE_INLINE gate + document env var
files_touched:
  - ingest_wechat.py
  - tests/unit/test_ingest_wechat_cognee_gate.py
  - CLAUDE.md
requirements:
  - HOTFIX-COGNEE-GATE
---

# 260503-v9z Summary — Cognee Inline-Call Env Gate Hotfix

## What Shipped

Pre-Day-1 KOL cron band-aid that gates the inline
`cognee_wrapper.remember_article` call in `ingest_wechat.ingest_article()`
behind a new `OMNIGRAPH_COGNEE_INLINE` env var. **Default is OFF** (env unset
or `"0"`), so the KOL fast-path no longer pays the minutes-long LiteLLM retry
loop caused by Cognee mis-routing `gemini-embedding-2` to AI Studio.

Strict `== "1"` match (not truthy-string) — operators must explicitly set
`OMNIGRAPH_COGNEE_INLINE=1` to re-enable once the root fix lands.

## Files Touched (exactly 3)

| File | Change |
|---|---|
| `ingest_wechat.py` | Added module-level `_cognee_inline_enabled()` helper above `ingest_article`; wrapped the existing `try/await cognee_wrapper.remember_article/except Exception: pass` block in `if _cognee_inline_enabled():` with a hotfix rationale comment. Zero other lines changed. |
| `tests/unit/test_ingest_wechat_cognee_gate.py` | **New file.** 17 mock-only unit tests — predicate-level (unset, `"0"`, `"1"`, empty, truthy-strings `"true"/"yes"/"TRUE"/"True"/"YES"/"y"/"on"`) + call-level (off/zero/truthy skip, `"1"` invokes with correct kwargs). No real cognee/LiteLLM/HTTP. |
| `CLAUDE.md` | One new row in the Environment Variables table for `OMNIGRAPH_COGNEE_INLINE`, inserted after the `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` row. |

## Test Results

```
venv/Scripts/python -m pytest tests/unit/test_ingest_wechat_cognee_gate.py -v
=> 17 passed, 9 warnings in 9.84s
```

All 17 tests pass:
- 4 predicate-level explicit tests (`unset`, `"0"`, `"1"`, empty string) → PASS
- 7 predicate-level parametrized truthy-string tests → PASS (strict match enforced)
- 2 call-level "gate off" tests (unset + `"0"`) → PASS
- 3 call-level parametrized truthy-string tests → PASS (strict match enforced at call site)
- 1 call-level "gate on" test (`"1"`) → PASS (kwargs `title/url/entities/summary_gist` verified)

Sanity regression note: `test_cognee_vertex_model_name.py` (2 failures) +
`test_batch_ingest_topic_filter.py` (5 failures) have 7 pre-existing failures
confirmed present **before** this task's changes via `git stash` cross-check.
Not introduced by this hotfix. They match the STATE.md baseline of "464 passed /
13 pre-existing failed".

## Verification (plan steps all passed)

- `grep -n "OMNIGRAPH_COGNEE_INLINE" ingest_wechat.py` → 5 matches (docstring + env.get + 2 comments) ✓
- `grep -n "await cognee_wrapper.remember_article" ingest_wechat.py` → exactly 1 match at line 1131 ✓
- `grep -n "def _cognee_inline_enabled" ingest_wechat.py` → exactly 1 match at line 758 (module scope) ✓
- Gate precedes call: `if _cognee_inline_enabled():` at line 1129 → `await cognee_wrapper.remember_article` at line 1131 ✓
- `grep -n "OMNIGRAPH_COGNEE_INLINE" CLAUDE.md` → exactly 1 match at line 157 ✓
- `git diff --stat HEAD~2 HEAD` → exactly 3 files touched, +145 / -9 lines ✓

## Commits

```
3f6d065 test(ingest): unit coverage for OMNIGRAPH_COGNEE_INLINE gate + document env var
e2d16e4 fix(ingest): gate cognee remember_article behind OMNIGRAPH_COGNEE_INLINE (default off)
```

Pushed to `origin/main` at 2026-05-03.

## Rollback

Two rollback paths, depending on whether the root fix has landed:

1. **Before v3.4 Phase 20/21 lands (root fix still pending):**
   Set `OMNIGRAPH_COGNEE_INLINE=1` in `~/.hermes/.env` on the Hermes box to
   restore the pre-hotfix behavior (inline Cognee call active). Do NOT use
   unless the LiteLLM routing has been repaired — will re-introduce the
   minutes-long retry loop that blocked Day-1 cron.

2. **Full revert of the hotfix (code + tests + docs):**
   ```
   git revert 3f6d065 e2d16e4
   git push --no-verify origin main
   ```

## Root Fix Pointer

Deferred to **v3.4 Phase 20/21** (Cognee LiteLLM routing repair). When
embedding requests are properly routed to Vertex AI for
`gemini-embedding-2` (currently Vertex-exclusive on the `global` endpoint),
flip the env var to `1` on all deployed environments and consider whether to
remove the gate entirely in a future follow-up.

## Self-Check: PASSED

- `ingest_wechat.py` exists
- `tests/unit/test_ingest_wechat_cognee_gate.py` exists
- `CLAUDE.md` exists
- `.planning/quick/260503-v9z-hotfix-disable-cognee-inline-call-blocki/260503-v9z-SUMMARY.md` exists
- Commit `e2d16e4` (fix(ingest): gate cognee...) present in git log
- Commit `3f6d065` (test(ingest): unit coverage...) present in git log
- Both commits pushed to `origin/main`
