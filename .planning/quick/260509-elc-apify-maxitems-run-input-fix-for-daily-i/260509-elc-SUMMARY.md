---
phase: 260509-elc
plan: 01
type: execute
subsystem: scraper
tags: [apify, scraper, daily-cron, ingest-fix, pay-per-result]
requires: []
provides:
  - "_apify_call passes max_items=1 to ApifyClient.actor(...).call()"
  - "Unit test mocking ApifyClient class to assert max_items=1 reaches .call() kwargs"
affects:
  - "ingest_wechat.py:_apify_call"
key-files:
  modified:
    - ingest_wechat.py
  created:
    - tests/unit/test_apify_run_input.py
decisions:
  - "max_items is a RUN-LEVEL kwarg on .call(), NOT a key inside run_input — verified in apify_client SDK source"
  - "max_items=1 because WeChat URL = 1 article expected per call (one URL in startUrls)"
  - "Test mocks at ApifyClient class level (one layer deeper than test_apify_rotation.py which mocks _apify_call) to capture .call() kwargs"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-09"
---

# Quick 260509-elc: Apify max_items=1 fix for daily-ingest cron

## One-liner

Pass `max_items=1` as a kwarg on `ApifyClient.actor(...).call()` in `_apify_call` to unblock the pay-per-result actor `zOQWQaziNeBNFWN1O` that rejected 5/5 articles on the 2026-05-08 09:00 ADT cron with "Maximum charged results must be greater than zero".

## Diff applied

| File | Change |
|---|---|
| `ingest_wechat.py:574` | 1-line: added `, max_items=1` kwarg to `.call()` lambda inside `loop.run_in_executor` |
| `tests/unit/test_apify_run_input.py` | NEW (130 lines): 1 async test `test_apify_call_passes_max_items_1` mocking `ApifyClient` class to capture `.call()` kwargs |

`git diff --stat ingest_wechat.py` → `1 file changed, 1 insertion(+), 1 deletion(-)`.

## must_haves status

| Truth / artifact / key_link | Status |
|---|---|
| **truths.0** Pay-per-result actor receives non-zero max_items run-option on every invocation | DELIVERED — test asserts `kwargs["max_items"] == 1` and exactly one `.call()` per `_apify_call`. |
| **truths.1** F1a dual-token rotation behavior preserved | DELIVERED — `test_apify_rotation.py` 3/3 still PASS after the change. |
| **truths.2** WeChat URL = 1 article so max_items=1 is correct | DELIVERED — value is 1; rationale documented in commit body. |
| **truths.3** No live Apify network calls during pytest | DELIVERED — test replaces `ingest_wechat.ApifyClient` via `monkeypatch.setattr` with a fake factory; no token, no HTTP. |
| **artifacts.0** `ingest_wechat.py` — `_apify_call passes max_items=1`; contains `.call(run_input=run_input, max_items=1)` | DELIVERED — line 574 verbatim matches. |
| **artifacts.1** `tests/unit/test_apify_run_input.py` exists; contains `max_items` | DELIVERED — file present, asserts `max_items` 4 distinct ways (presence, value=1, NOT in run_input, NOT as `maxItems` in run_input). |
| **key_links.0** `ingest_wechat.py:_apify_call` → `apify_client.ActorClient.call` via `max_items` kwarg | DELIVERED — pattern `\.call\(run_input=run_input, max_items=1\)` matches line 574. |
| **key_links.1** test → `_apify_call` via monkeypatch on ApifyClient class | DELIVERED — `monkeypatch.setattr(ingest_wechat, "ApifyClient", _factory)`. |

## Forensic evidence

- **Cron session**: `~/.hermes/sessions/session_cron_2b7a8bee53e0_20260508_090038.json` — 2026-05-08 09:00 ADT cron run that surfaced the failure.
- **Bug report**: `docs/bugreports/2026-05-08-cron-ingest-failure.md` — 5/5 articles erroring with the same message.
- **Error literal (verbatim)**: `Maximum charged results must be greater than zero`.
- **SDK source**: `venv/Lib/site-packages/apify_client/clients/resource_clients/actor.py:322` declares `max_items: int | None = None` as a kwarg on `ActorClient.call()`. Lines 367-378 forward it to `start()`, which on line 296 maps it to API param `maxItems` in the run-creation request.

## Verification

### RED (Task 1 — pre-fix)

- Command: `venv/Scripts/python.exe -m pytest tests/unit/test_apify_run_input.py -x -v`
- Log: `.scratch/quick-260509-elc-pytest-red-20260509-103919.log`
- Result: FAILED at `tests/unit/test_apify_run_input.py:104` (the `assert "max_items" in kwargs` assertion). Exit code 1, 1 test, 1 failure.

### GREEN (Task 2 — post-fix)

- Command: `venv/Scripts/python.exe -m pytest tests/unit/test_apify_run_input.py tests/unit/test_apify_rotation.py -v`
- Log: `.scratch/quick-260509-elc-pytest-green-20260509-103954.log`
- Result: 4 passed, 9 warnings. Exit code 0. Lines from log:
  - `tests/unit/test_apify_run_input.py::test_apify_call_passes_max_items_1 PASSED [ 25%]`
  - `tests/unit/test_apify_rotation.py::test_primary_success_skips_backup PASSED [ 50%]`
  - `tests/unit/test_apify_rotation.py::test_primary_raise_invokes_backup PASSED [ 75%]`
  - `tests/unit/test_apify_rotation.py::test_both_raise_propagates PASSED     [100%]`

## Scope-boundary verification

Forbidden files (parallel ir-4 W2 agent territory) were not modified:

- `batch_ingest_from_spider.py` — untouched (no entry in `git diff --name-only`)
- `lib/scraper.py` — untouched
- `enrichment/orchestrate_daily.py` — untouched (already-committed W2/W3/W4 work was upstream of this quick)
- Migration / SQL / Layer 1 / Layer 2 code — untouched

Post-commit `git diff --name-only HEAD~1 HEAD` shows ONLY:
- `ingest_wechat.py`
- `tests/unit/test_apify_run_input.py`
- `.planning/quick/260509-elc-apify-maxitems-run-input-fix-for-daily-i/260509-elc-PLAN.md`
- `.planning/quick/260509-elc-apify-maxitems-run-input-fix-for-daily-i/260509-elc-SUMMARY.md`

(The `.planning/phases/ir-4-rss-integration-and-cleanup/` untracked directory and the W2 agent's already-committed ingest-pipeline changes are explicitly NOT included in this commit.)

## Commit

- Hash: `<filled in below after commit>`
- Subject: `fix(scraper-260509-apify): add max_items=1 to Apify .call() to unblock pay-per-result actor`
- Forward-only single commit; explicit `git add <named-files>` (NO `-A`); no stash/reset/rebase/amend/force-push.

## Self-Check

- Created `tests/unit/test_apify_run_input.py` — FOUND
- Modified `ingest_wechat.py:574` — FOUND (1-line diff verified)
- RED log `.scratch/quick-260509-elc-pytest-red-20260509-103919.log` — FOUND
- GREEN log `.scratch/quick-260509-elc-pytest-green-20260509-103954.log` — FOUND
- All 4 tests PASS post-fix — VERIFIED via grep on green log
- Forbidden files untouched — VERIFIED via `git status --short`
- No literal secrets in diff — VERIFIED via `grep -iE "(token|key|secret|apify_api_)"` (only matches were the `token:` parameter name in unchanged context lines)

## Self-Check: PASSED
