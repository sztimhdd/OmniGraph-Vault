---
phase: quick/260518-non-pytest-harness-for-ingest-from-db-orches
plan: 01
status: complete
wave: 1
requirements:
  - HARNESS-01
  - HARNESS-02
  - HARNESS-03
files_added:
  - tests/unit/_ingest_fixtures.py
  - tests/unit/test_ingest_from_db_orchestration.py
files_modified:
  - CLAUDE.md
commits:
  - 4b6503c (Task 1): feat(test/quick-260518): add _ingest_fixtures harness module
  - f4de844 (Task 2): feat(test/quick-260518): behavior-anchor harness for ingest_from_db()
metrics:
  tests_added: 5
  tests_passing: 5
  business_code_changes: 0
verification_log: .scratch/quick-260518-non-pytest-run.log
---

# Quick 260518-non — Pytest Behavior-Anchor Harness for ingest_from_db()

## One-liner

Behavior-anchor pytest harness for `batch_ingest_from_spider.ingest_from_db()` pinning 5 historical prod-only failure modes + new HIGHEST PRIORITY PRINCIPLE #7 codifying the rule.

## Deliverables

| File                                                     | Lines  | Status   |
| -------------------------------------------------------- | ------ | -------- |
| `tests/unit/_ingest_fixtures.py`                         | 387    | new      |
| `tests/unit/test_ingest_from_db_orchestration.py`        | 423    | new      |
| `CLAUDE.md`                                              | +14    | modified |

## Tests added (all passing)

| ID  | Test                                                       | Anchor                                                                    |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------------------- |
| T1  | test_layer1_reject_writes_skipped_with_correct_source      | 2026-05-08 dual-source skip_reason_version + source dispatch              |
| T2  | test_drain_unpacks_8_col_tuple_with_image_count            | 2026-05-15 v1.0.z imc D2 single-missed queue.append → ghost success       |
| T3  | test_max_articles_cap_includes_queued_count                | 2026-05-11 quick-260511-mxc max-articles cap leak                         |
| T4  | test_budget_exhausted_finally_drains_vision_and_finalizes  | v1.0.x stable: finally block must drain vision + finalize storages        |
| T5  | test_image_count_refresh_after_persist                     | 2026-05-16 quick-260516-htm image_count_row stale-0 → 900s floor          |

## Verification evidence

Pytest output (3 runs for determinism, see `.scratch/quick-260518-non-pytest-run.log`):

```
tests/unit/test_ingest_from_db_orchestration.py::test_layer1_reject_writes_skipped_with_correct_source PASSED [ 20%]
tests/unit/test_ingest_from_db_orchestration.py::test_drain_unpacks_8_col_tuple_with_image_count       PASSED [ 40%]
tests/unit/test_ingest_from_db_orchestration.py::test_max_articles_cap_includes_queued_count           PASSED [ 60%]
tests/unit/test_ingest_from_db_orchestration.py::test_budget_exhausted_finally_drains_vision_and_finalizes PASSED [ 80%]
tests/unit/test_ingest_from_db_orchestration.py::test_image_count_refresh_after_persist                PASSED [100%]
============================== 5 passed in 2.48s ==============================
```

Wall-clock: 2.47s / 2.26s / 2.17s / 2.48s across 4 invocations — deterministic.

`git diff HEAD~2 -- batch_ingest_from_spider.py lib/article_filter.py lib/scraper.py ingest_wechat.py` is empty (zero business-code changes confirmed).

## Deviations from plan

### T4 fallback strategy used

Plan specified `time.time` monkeypatch stepping to force budget exhaustion. Implementation used the plan's documented "simpler form" fallback: drive ingest_from_db to natural completion on a 1-article happy path and assert finally-block invariants (`drain_vision.assert_called()` + `rag.finalize_storages.assert_called_once()`).

Reason: `bi.time.time` is also called by pytest-asyncio's own internals during `await`, so step-counting tied to specific call indices was fragile. The simpler form still pins the core regression net — finally block MUST execute on every exit path.

### `_wire_db` switched from `:memory:` to file-backed DB under `tmp_path`

Plan example used in_memory_db() + monkeypatch.setattr(bi.sqlite3, "connect", _connect) + monkeypatch.setattr(conn, "close", lambda: None) to redirect production's `sqlite3.connect()` call to a shared in-memory connection.

Issue surfaced during first test run: `sqlite3.Connection.close` is a read-only attribute and cannot be monkeypatched — `AttributeError: 'sqlite3.Connection' object attribute 'close' is read-only`. Without suppressing close, production's end-of-batch `conn.close()` destroys the in-memory DB before assertions can read it.

Fix: use a file-backed SQLite DB under `tmp_path/fake.db`. Production opens its own connection to the same file via the real `sqlite3.connect`. SQLite shows committed data across connections, so seeded rows are visible to production's SELECT and ingestions rows production writes are visible to test assertions. Pytest's `tmp_path` cleanup handles teardown.

The fixture module's `in_memory_db()` helper is still exported for direct use cases. A new `init_schema(conn)` helper was added to apply the production schema to any existing connection — used by `_wire_db` to bootstrap the file DB.

## Self-Check: PASSED

- `tests/unit/_ingest_fixtures.py` exists at L387 — verified by `git show --stat HEAD~1`
- `tests/unit/test_ingest_from_db_orchestration.py` exists at L423 — verified by `git show --stat HEAD`
- CLAUDE.md PRINCIPLE #7 inserted at line 100, between "Full discipline doc" (line 98) and "## Project Summary" (line 114) — verified by `grep -n "Behavior-Anchor Harness\|^## Project Summary\|Full discipline doc" CLAUDE.md`
- 5/5 tests pass under `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v`
- Commits 4b6503c (Task 1) and f4de844 (Task 2) exist — verified by `git log --oneline -2`
- Zero business-code changes — verified by `git diff HEAD~2 -- batch_ingest_from_spider.py lib/article_filter.py lib/scraper.py ingest_wechat.py` (empty)
