---
phase: 10-classification-and-ingest-decoupling
plan: 00
subsystem: database
tags: [deepseek, sqlite, classification, scrape, rate-limit, tdd]

# Dependency graph
requires:
  - phase: 09-timeout-state-management
    provides: "ingest_article wrapper with rollback-on-timeout + get_rag(flush=True) contract (untouched by 10-00; preserved as-is)"
  - phase: 05-pipeline-automation
    provides: "batch_ingest_from_spider.py orchestrator + WeChat spider rate-limit constants (RATE_LIMIT_SLEEP_ACCOUNTS, RATE_LIMIT_COOLDOWN, SESSION_REQUEST_LIMIT) reused verbatim"
provides:
  - "batch_classify_kol._build_fullbody_prompt + _call_deepseek_fullbody — full-body {depth, topics, rationale} classifier (D-10.02)"
  - "batch_ingest_from_spider._classify_full_body — async per-article pre-flight: scrape-on-demand → DeepSeek → persist → gate (D-10.01/02/04)"
  - "batch_ingest_from_spider._ensure_fullbody_columns — idempotent additive SQLite migration (articles.body, classifications.{depth, topics, rationale})"
  - "ingest_from_db (--from-db path) rewired: LEFT JOIN classifications + per-article classify + depth-gated ingest"
  - "9 unit tests in test_scrape_first_classify.py gating D-10.01..04"
affects:
  - 10-01-text-first-ingest-split
  - 10-02-async-vision-subdoc

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-column ALTER TABLE idempotent migration via PRAGMA table_info guard (pattern reuse from batch_scan_kol._ensure_column)"
    - "Full-body single-article DeepSeek prompt returning a JSON OBJECT (not array — distinguishes from legacy batch prompt)"
    - "No fail-open for scrape-first classifier (return None → caller skips)"

key-files:
  created:
    - "tests/unit/test_scrape_first_classify.py"
    - ".planning/phases/10-classification-and-ingest-decoupling/deferred-items.md"
  modified:
    - "batch_classify_kol.py"
    - "batch_ingest_from_spider.py"

key-decisions:
  - "Schema migration is ADDITIVE (D-10.04 option (a)): new classifications columns {depth, topics, rationale} coexist with legacy {depth_score, topic, reason} — batch-scan path unchanged."
  - "DeepSeek full-body prompt truncates body to FULLBODY_TRUNCATION_CHARS=8000 (D-10.02 suggested budget); single-article JSON OBJECT response shape, not JSON array."
  - "No fail-open on scrape-first classifier failure — _classify_full_body returns None and caller writes ingestions.status='skipped'. Distinguishes from batch-scan _call_deepseek which fails open."
  - "Scrape-on-demand reuses ingest_wechat.scrape_wechat_ua directly (D-10.03) — no new rate-limit constants, _ua_cooldown already provides throttling."
  - "_classify_full_body persists classifications row BEFORE returning (D-10.04 strict ordering) — caller never ingests an article that doesn't have a committed classifications row for it."
  - "ingest_from_db SELECT changed from inner JOIN classifications (pre-filter by depth) to LEFT JOIN (per-article classify inside the loop). Depth gating now happens per-row after classify."

patterns-established:
  - "Schema-additive per-column migration helper: _ensure_fullbody_columns(conn) guards each column with PRAGMA table_info check before ALTER TABLE. Pattern reusable for any future additive migration in this DB."
  - "Scrape-first classification: scrape → persist body → classify → persist classifications row → gate ingest. All inside a single async helper, testable in isolation."

requirements-completed: [CLASS-01, CLASS-02, CLASS-03, CLASS-04]

# Metrics
duration: 6min
completed: 2026-05-01
---

# Phase 10 Plan 00: Scrape-First Classification Summary

**Full-body DeepSeek classifier replacing digest-based classify, with scrape-on-demand → persist-before-ingest → no-fail-open gating in batch_ingest_from_spider's --from-db flow.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-01T01:13:34Z
- **Completed:** 2026-05-01T01:19:20Z
- **Tasks:** 3 (Task 1 + Task 2 TDD, Task 3 verification-only)
- **Files modified:** 3 (batch_classify_kol.py, batch_ingest_from_spider.py, tests/unit/test_scrape_first_classify.py)

## Accomplishments

- **CLASS-01 (scrape-first):** `_classify_full_body` scrapes article body on-demand via `ingest_wechat.scrape_wechat_ua` when `articles.body` is empty, writes body back to DB, and feeds that body — NOT the WeChat digest — to the classifier.
- **CLASS-02 (full-body DeepSeek + new schema):** `_build_fullbody_prompt` + `_call_deepseek_fullbody` in `batch_classify_kol.py` emit a prompt that instructs DeepSeek to return one JSON object `{depth: 1-3, topics: [...], rationale: str}`. Legacy `_build_prompt`/`_call_deepseek` preserved for batch-scan back-compat.
- **CLASS-03 (rate-limit reuse):** source-grep test confirms `RATE_LIMIT_SLEEP_ACCOUNTS` + `RATE_LIMIT_COOLDOWN` imports are present and no new rate-limit constants introduced (`SCRAPE_ON_DEMAND_SLEEP`, `PER_ARTICLE_DELAY`, etc.). Scrape-on-demand reuses existing `_ua_cooldown` via `scrape_wechat_ua`.
- **CLASS-04 (persist-before-ingest):** schema-additive `_ensure_fullbody_columns` adds `articles.body` + `classifications.{depth, topics, rationale}` idempotently. `_classify_full_body` writes the classifications row BEFORE returning; orchestrator only proceeds to ingest if the returned dict's depth ≥ min_depth.
- **No-fail-open:** DeepSeek returns `None` → `_classify_full_body` returns `None` → orchestrator writes `ingestions.status='skipped'` and continues. No silent pass-through.

## Task Commits

1. **Task 0 (RED phase):** `756477d` — `test(10-00): add failing tests for scrape-first full-body classification` (9 tests, 8 failing as expected)
2. **Task 1 (GREEN):** `3194710` — `feat(10-00): add full-body DeepSeek classifier + schema-additive migration`
3. **Task 2 (GREEN):** `8332066` — `feat(10-00): wire scrape-first classify into ingest_from_db (D-10.01/03/04)`
4. **Task 3 (verify):** no source changes — regression suites + smoke imports verified green (no commit needed)

## Files Created/Modified

- `batch_classify_kol.py` — added `FULLBODY_TRUNCATION_CHARS` constant, `_build_fullbody_prompt`, `_call_deepseek_fullbody`. Legacy `_build_prompt` + `_call_deepseek` untouched.
- `batch_ingest_from_spider.py` — added `_ensure_fullbody_columns`, `_classify_full_body`; rewrote `ingest_from_db` inner loop to use scrape-first per-article classify; SELECT changed from inner-JOIN-on-depth to LEFT-JOIN with in-loop depth gating.
- `tests/unit/test_scrape_first_classify.py` — 9 unit tests mocking `requests.post`, `ingest_wechat.scrape_wechat_ua`, `ingest_wechat.process_content`, `_call_deepseek_fullbody`. All external deps mocked — zero live API calls.
- `.planning/phases/10-classification-and-ingest-decoupling/deferred-items.md` — logs 10 pre-existing unit test failures (test_lightrag_embedding*, test_models) confirmed out-of-scope.

## Decisions Made

- **Schema migration is ADDITIVE (D-10.04 option a).** Per-column PRAGMA table_info guard + individual ALTER TABLE (pattern: `batch_scan_kol._ensure_column`). Rationale: batch-scan path in `batch_classify_kol.run` still writes to the legacy `depth_score`/`topic`/`reason` columns; breaking them would ripple to Phase 5 plans.
- **FULLBODY_TRUNCATION_CHARS = 8000.** Matches D-10.02 suggested upper bound. Single-article calls never truncate below this.
- **No fail-open on classify error.** `_classify_full_body` returns `None` on any of: scrape failure, empty content_html, DeepSeek HTTP error, DeepSeek JSON parse error, missing `depth`/`topics` keys. Caller writes `ingestions.status='skipped'` and moves on. Distinguishes from `batch_classify_articles` which pass-through on API failure (that behavior preserved for batch-scan).
- **Legacy columns in classifications row stay populated.** `_classify_full_body`'s INSERT writes BOTH new and legacy columns (first topic → legacy `topic`, depth → legacy `depth_score`) so batch-scan queries that join on the legacy schema still work against rows created by scrape-first.
- **`ingest_from_db` SELECT changed from INNER JOIN to LEFT JOIN.** Pre-Phase-10 query required an existing classifications row with `depth_score >= min_depth`; now the query returns all pending articles (classified or not) and per-article `_classify_full_body` handles the gating. Enables scrape-first over articles the legacy classifier never saw.

## Deviations from Plan

**None auto-fixed — plan executed exactly as written.**

Plan specified all design decisions (schema-additive, no fail-open, 8000-char truncation, rate-limit reuse). Implementation matches plan artifacts exactly:

- `_build_fullbody_prompt` in `batch_classify_kol.py` ✓
- `_call_deepseek_fullbody` in `batch_classify_kol.py` ✓
- `_ensure_fullbody_columns` in `batch_ingest_from_spider.py` ✓
- `_classify_full_body` in `batch_ingest_from_spider.py` ✓
- 9 unit tests (plan asked for 5+) ✓
- No new rate-limit constants ✓ (source-grep test enforces)

**Total deviations:** 0
**Impact on plan:** Plan design pre-resolved all architectural discretion points — execution was mechanical. No scope creep.

## Issues Encountered

- **Pre-existing unit test failures discovered:** 10 failures in `test_lightrag_embedding*` + `test_models` that already failed on baseline HEAD (verified via `git stash` + pytest diff — same 10 failures before and after my edits). Logged in `deferred-items.md` under the phase directory. OUT OF SCOPE — plan 10-00 did not modify `lib/models.py`, `lib/embedding*.py`, or any of the affected test files.

## Regression Gate Evidence

- **Phase 8 (image pipeline):** 22/22 green — `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py`
- **Phase 9 (timeout + state):** 21/21 green — 6 get_rag_contract + 4 rollback_on_timeout + 2 prebatch_flush + 3 lightrag_timeout + 6 timeout_budget
- **Phase 10 new (scrape_first_classify):** 9/9 green — 5 Task-1 unit + 3 Task-2 async flow + 1 source-grep rate-limit
- **Combined verification pass:** 43/43 (the Task 3 gated suite) + 21/21 (full Phase 9) = 64/64 green.
- **Smoke imports:** `import batch_ingest_from_spider` and `import batch_classify_kol` both succeed with `DEEPSEEK_API_KEY=dummy`.
- **Schema migration verified on real tmp SQLite file:** idempotent 2x call, all 4 new columns present with correct types, legacy columns preserved, INSERT+SELECT round-trip with JSON-serialized topics works.

## User Setup Required

None — no external service configuration required. Scrape-first path reuses `DEEPSEEK_API_KEY` already required for batch-scan and `~/.hermes/.env` loading already in place.

## Next Phase Readiness

**Ready for Plan 10-01 (text-first ingest split — D-10.05).**

- `ingest_from_db` scrape-first pre-flight is in place and tested.
- `_classify_full_body` is isolated from `ingest_wechat.ingest_article` — plan 10-01 can modify `ingest_article` freely without touching classification.
- Schema migration is stable. 10-01 does not need to touch SQLite schema.
- Phase 9 rollback-on-timeout behavior preserved. `ingest_article(url, dry_run, rag)` wrapper is unchanged.

**No blockers. No known concerns.**

---

## Self-Check: PASSED

Verified all claims in the frontmatter, accomplishments, and task commits:

- [x] `batch_classify_kol._build_fullbody_prompt` — exists (source inspection + passing test `test_fullbody_prompt_includes_body_not_digest`).
- [x] `batch_classify_kol._call_deepseek_fullbody` — exists (source inspection + passing test `test_call_deepseek_returns_new_schema`).
- [x] `batch_ingest_from_spider._ensure_fullbody_columns` — exists + idempotent (passing test `test_schema_migration_idempotent` + manual tmp-DB verification).
- [x] `batch_ingest_from_spider._classify_full_body` — exists (source inspection + passing tests `test_scrape_on_demand_when_body_empty`, `test_classifier_persistence_before_ingest_decision`, `test_deepseek_failure_skips_ingest`).
- [x] `ingest_from_db` wired to call `_classify_full_body` per article before `ingest_article` — confirmed by source inspection of `batch_ingest_from_spider.py` lines 752-788 (new depth-gated block).
- [x] No new rate-limit constants — `test_rate_limit_constants_reused` green.
- [x] All 4 per-commit hashes present in git log: `756477d`, `3194710`, `8332066` (Task 3 has no source commit — verification only).
- [x] Phase 8 (22/22) + Phase 9 (21/21) regression green.
- [x] 9 new scrape_first_classify tests green.
- [x] Deferred-items.md exists at the phase directory.

---
*Phase: 10-classification-and-ingest-decoupling*
*Plan: 00 (scrape-first-classification)*
*Completed: 2026-05-01*
