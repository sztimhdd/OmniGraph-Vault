# Deferred Items — quick 260509-p1n

Pre-existing failures encountered during the regression check that are NOT
caused by this quick's changes. Logged here per the CLAUDE.md scope boundary
rule (auto-fix only issues directly caused by the current task).

## tests/unit/test_vision_worker.py::test_ingest_from_db_drains_pending_vision_tasks

**Status:** FAILED on `main` baseline (verified 2026-05-09 via
`git stash && pytest`). Failure assertion:
`assert drained == ["done"]` → `assert [] == ['done']`.

**Diagnosis:** The fake `_fake_ingest_article` is never invoked during the
`ingest_from_db` flow used in this test, so its task is never spawned and
the `drained` sentinel stays empty.  Likely cause is a path divergence
introduced by a prior phase that updated `ingest_from_db` (post Phase 17 /
Phase 20 RIN-01 work), where the test fixture no longer satisfies the
SELECT criteria the real call now uses.

**This quick's mitigation:** I updated the test's fake to register tasks
via `lib.vision_tracking.track_vision_task` to match the new spawn site
(my changes here do not introduce, mask, or worsen the failure — the
fake is never executed, so the registration helper's behavior is moot
for this case).

**Owner / next step:** Out of scope for 260509-p1n. Track for a follow-up
quick that verifies `ingest_from_db`'s candidate selection still matches
the test's seeded SQLite fixture (rss_articles + rss_feeds were added by
ir-4; the fixture seeds them empty, and the SELECT may be filtering on
a column not present on the seeded `articles` row).
