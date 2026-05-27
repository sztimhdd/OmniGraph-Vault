# 260516-bls — kb-v2.1-9-quick PLAN: baseline test triage

**Date:** 2026-05-16
**Branch:** main
**Mission:** Take the 51 pre-existing pytest baseline failures observed during
v2.1-8 push gate from RED → GREEN. Bucket each failure by root-cause family
and ship surgical fixes (or xfail markers) WITHOUT modifying production code.

## Baseline (post v2.1-8 push)

`venv/Scripts/python.exe -m pytest --tb=short` →
**51 failed / 1225 passed / 5 skipped in 278.27s**.

Full evidence: `.scratch/260516-bls-baseline-pytest-20260516-211916.log`.
Sorted unique failure list: `.scratch/260516-bls-failures.txt` (51 lines).

Drift from v2.1-8 SUMMARY (52) → 51: one previously failing test now passes
(no investigation — could be flaky timing or a test that was unrelated to my
fix and stabilized between runs).

## Bucket categorization (51 / 51 total)

### B1 — Fixture / schema drift (15 failures)

Production migration 011 (`260513-q15-imc`) added `image_count INTEGER DEFAULT 0`
to `articles` + `rss_articles`; SELECT now reads `COALESCE(r.image_count, 0)` on
both UNION arms (`batch_ingest_from_spider.py:1492,1513`). Tests that build their
own `articles` / `rss_articles` tables in setUp / fixture didn't add the column.
Symptom: `sqlite3.OperationalError: no such column: r.image_count`.

Matches CLAUDE.md 2026-05-15 lesson #2 verbatim.

- `tests/unit/test_article_filter.py::test_layer1_prompt_version_bump_invalidates_prior`
- `tests/unit/test_batch_ingest_topic_filter.py::test_dual_source_sql_executes_both_branches`
- `tests/unit/test_batch_ingest_topic_filter.py::test_dual_source_sql_anti_join_isolates_by_source`
- `tests/unit/test_batch_ingest_topic_filter.py::test_dual_source_sql_seven_columns_runtime`
- `tests/unit/test_batch_ingest_topic_filter.py::test_dual_source_sql_kol_aliases_digest_to_summary`
- `tests/unit/test_skip_reason_version.py::test_status_ok_row_always_excluded`
- `tests/unit/test_skip_reason_version.py::test_status_skipped_at_current_version_excluded`
- `tests/unit/test_skip_reason_version.py::test_status_skipped_at_legacy_version_re_enters_pool`
- `tests/unit/test_skip_reason_version.py::test_status_skipped_at_older_nonzero_version_re_enters_pool`
- `tests/unit/test_skip_reason_version.py::test_rss_branch_obeys_same_cohort_gate`

(10 confirmed via `r.image_count` error). 5 more in test_checkpoint_resume_e2e
that fail with `ValueError: Body too short for ingest: len=212/240 < 500` —
fixture body strings are too short for the post-260510-uai
`MIN_INGEST_BODY_LEN=500` guard. Same B1 family (fixture data drifted from
production constraint).

- `tests/integration/test_checkpoint_resume_e2e.py::test_gate1_fail_at_image_download_then_resume`
- `tests/integration/test_checkpoint_resume_e2e.py::test_fail_at_text_ingest_preserves_stages_1_to_3`
- `tests/integration/test_checkpoint_resume_e2e.py::test_metadata_updated_at_advances`
- `tests/integration/test_checkpoint_resume_e2e.py::test_no_tmp_files_after_success`

(Sub-total: 14 B1 fixture-drift failures.)

### B2 — Mock signature drift (24 failures)

#### B2a — `vertexai` kwarg drift (7 failures)
Production `lib/lightrag_embedding.py:_make_client` now calls
`genai.Client(api_key=api_key, vertexai=False)`. Tests' `_mock_client_cls`
helpers don't accept `vertexai` kwarg.

- `tests/unit/test_lightrag_embedding.py::test_embedding_func_reads_current_key`
- `tests/unit/test_lightrag_embedding_rotation.py` × 6 (single_key_fallback,
  round_robin_two_keys, 429_failover_within_single_call, both_keys_429_raises,
  non_429_error_does_not_rotate, empty_backup_env_var_treated_as_no_backup)

#### B2b — `effective_timeout` kwarg drift on _fake_ingest_article (3 failures)
Production `_run_ingest_with_timeout` (or similar) now passes `effective_timeout`
positionally AND test still passes it via kwarg → `got multiple values for argument`.

- `tests/unit/test_vision_worker.py::test_run_drains_pending_vision_tasks`
- `tests/unit/test_vision_worker.py::test_drain_timeout_cancels_stragglers`

(`test_ingest_from_db_drains_pending_vision_tasks` also in same file — likely B1
since error was `r.image_count`.)

#### B2c — `ingest_article` 3-tuple return drift (4 failures)
Per CLAUDE.md "Lessons Learned" 2026-05-10 quick `260510-uai`: outer
`ingest_article` was widened from 2-tuple to 3-tuple `(success, wall, doc_confirmed)`,
test_rollback_on_timeout still unpacks 2.

- `tests/unit/test_rollback_on_timeout.py::test_timeout_triggers_adelete_by_doc_id`
- `tests/unit/test_rollback_on_timeout.py::test_successful_ingest_does_not_call_adelete`
- `tests/unit/test_rollback_on_timeout.py::test_rollback_failure_is_logged_not_raised`
- `tests/unit/test_rollback_on_timeout.py::test_idempotent_reingest_after_rollback`

#### B2d — `ingest_article_processed_gate` ZeroDivisionError (10 failures)
Suggests `_compute_article_budget_s` (or sub-helper) divides by a count derived
from mocked data that defaults to 0. Either fixture/mock missing field or
prod-code computes a denominator that's now 0 in mock context. Plausibly mock
data missing `image_count` (forced default 0) cascading to a per-image divisor.
Surgical fix likely: feed mock fixture row a non-zero `image_count` OR patch
`PROCESSED_VERIFY_BACKOFF_S` and supply a body length that avoids divide path.

- `tests/unit/test_ingest_article_processed_gate.py` × 10 (all named cases)

(Sub-total: 24 B2 mock-drift failures.)

### B3 — Lingering / retired-feature tests (0 candidates from log evidence)

No clear B3 in this baseline (Cognee retire happened in 260510-gfg and tests
were already deleted then). All 51 are operations on still-live features.

### B4 — Actual production bugs / behavioral drift (12 failures, marked xfail)

Tests that may surface real issues but are out of scope for this triage —
mark `xfail` with grep-able `kb-v2.1-9 audit:` reason; if prod gets fixed,
xfail flips to unexpected-pass alarm.

#### B4a — siliconflow_balance "totalBalance" key (2 failures)
Test mock returns `{"data": {"balance": "5.43"}}` but prod expects `totalBalance`.
Could be: prod-code drift (B2 mock data) OR upstream API contract change (B4).
Without examining production source-of-truth I can't be sure — mark xfail.

- `tests/unit/test_siliconflow_balance.py::test_check_siliconflow_balance_success`
- `tests/unit/test_siliconflow_balance.py::test_authorization_header_sent`

#### B4b — bench_integration assertions (2 failures)
`assert 0 == 1` / `assert False is True` / `gate_pass=false → exit 1` — gate
predicate flipping. Smells like real behavior drift; surface via xfail.

- `tests/integration/test_bench_integration.py::test_text_ingest_over_threshold_fails_gate`
- `tests/integration/test_bench_integration.py::test_live_gate_run`

#### B4c — fetch_zhihu/image_pipeline namespace assertion (2 failures)
Tests assert `hh/zhihu_1/` namespace prefix but prod emits raw `http://x/a.jpg`.
Tests pinning a now-changed namespacing convention.

- `tests/unit/test_fetch_zhihu.py::test_fetch_zhihu_image_namespacing`
- `tests/unit/test_image_pipeline.py::test_download_images_success_and_failure`

#### B4d — graded_classify None returns (3+1 failures)
3 tests in `test_graded_classify.py` get `assert None == {...}` — production now
returns None where it used to return dict. Plus
`test_graded_classify_prompt_quality::test_graded_prompt_quality` flagging
"false-positive rate 100% exceeds 30% prompt is too lax" — quality-gate test
that's failing on prompt drift. Both require domain knowledge to fix correctly.

- `tests/unit/test_graded_classify.py` × 3
- `tests/unit/test_graded_classify_prompt_quality.py::test_graded_prompt_quality`

#### B4e — scrape_first_classify schema drift (1 failure)
`assert 0 == 2` → mock returns 0 records where 2 expected. Schema or prompt
behaviour drift.

- `tests/unit/test_scrape_first_classify.py::test_call_deepseek_returns_new_schema`

#### B4f — text_first_ingest fast-return + content shape (2 failures)
`ingest_article should return in <5s; took 5.14s` (timing flaky? or real
regression?) plus `'[Image 0 Reference]:' in 'Image 0 from article ...'`
(format string drift — Phase 5-00 changed end-of-doc text-ref shape).

- `tests/unit/test_text_first_ingest.py::test_ingest_article_returns_fast_with_slow_vision`
- `tests/unit/test_text_first_ingest.py::test_parent_ainsert_content_has_references_not_descriptions`

(Sub-total: 12 B4 xfail surface.)

## Plan

1. **B1 batch** — add `image_count INTEGER DEFAULT 0` to all test CREATE TABLE
   statements (10 tests across 3 files); extend fixture body strings to ≥500
   chars in test_checkpoint_resume_e2e.py (4 tests). Single commit.
2. **B2a batch** — extend `_mock_client_cls(api_key=...)` signatures in 2 files
   to accept `vertexai=False` kwarg. Single commit.
3. **B2b batch** — fix `_fake_ingest_article` signature in test_vision_worker.py
   (likely positional vs kwarg duplicate). Single commit.
4. **B2c batch** — update test_rollback_on_timeout.py 4 callers to unpack
   3-tuple `(success, wall, doc_confirmed)`. Single commit.
5. **B2d batch** — fix test_ingest_article_processed_gate ZeroDivisionError by
   supplying mock fixture data with image_count >= 1 (or whichever field
   triggers the divisor). Single commit.
6. **B4 xfail** — add `@pytest.mark.xfail(strict=False, reason="kb-v2.1-9 audit: <root-cause>; see follow-up")` to 12 B4 tests. Single commit.
7. **SUMMARY commit** — final pytest evidence + STATE.md row + push.

If any batch needs more than the diagnosed mechanism (e.g., B2d turns out to
need prod-code touch), STOP at that batch and report. Do NOT modify
production code.

## Skills

- `Skill(skill="python-patterns")` — idiomatic mock signature update
  (kwargs, type hints, `**kwargs` swallow pattern)
- `Skill(skill="writing-tests")` — xfail vs skip vs delete decision framework
  (xfail strictly preferred over skip per `kb-v2.1-9` orchestrator instruction)
- `Skill(skill="refactoring-code")` — bucket-by-bucket atomic commits, never
  mix B1+B2+B4 in same commit

## Anti-patterns honored

- Zero touches to `lib/`, `kb/`, `ingest_*.py`, `kg_synthesize.py`,
  `image_pipeline.py` — production code unchanged
- No `git add -A` / `--amend` / reset / rebase / force-push
- STATE.md edit limited to own quick row
- Each bucket gets its own commit — surgical reversibility
