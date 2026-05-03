---
phase: quick-260503-sd7
plan: 01
subsystem: batch-ingest
tags: [case-insensitive, sql, topic-filter, day1-cron, bugfix]
dependency_graph:
  requires: []
  provides: [_build_topic_filter_query helper, case-insensitive topic filter SQL]
  affects: [batch_ingest_from_spider.ingest_from_db]
tech_stack:
  added: []
  patterns: [pure helper extraction, SQL parameterization]
key_files:
  created:
    - tests/unit/test_batch_ingest_topic_filter.py
  modified:
    - batch_ingest_from_spider.py
decisions:
  - Helper placed at module level (not inside ingest_from_db) for direct importability by tests
  - LOWER() applied to column side only; params normalized via strip+lower on Python side
  - No change to cron command, classifier write path, or any sibling functions
metrics:
  duration: "~8 min"
  completed: "2026-05-03"
  tasks: 1
  files: 2
---

# Phase quick-260503-sd7 Plan 01: Case-Insensitive Topic Filter SQL Summary

**One-liner:** Extracted `_build_topic_filter_query` helper from `ingest_from_db`, flipping `c.topic IN (...)` to `LOWER(c.topic) IN (...)` with stripped+lowercased params — zero-config fix for Day-1 cron that passes `agent` but finds only classifier-written `Agent` rows.

---

## Commit

| Commit | Message | Files |
|--------|---------|-------|
| `e59bc42` | fix(ingest): case-insensitive topic filter SQL (Day-1 cron blocker) | `batch_ingest_from_spider.py` (+30 lines), `tests/unit/test_batch_ingest_topic_filter.py` (+56 lines) |

---

## Diff Shape

**`batch_ingest_from_spider.py`** — two changes:

1. **New module-level helper** inserted between `_classify_article_fullbody` and `async def ingest_from_db` (lines ~985-1017):
   ```python
   def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
       ...
       sql = f"""... WHERE (c.topic IS NULL OR LOWER(c.topic) IN ({placeholders})) ..."""
       normalized = tuple(t.strip().lower() for t in topics)
       return sql, normalized
   ```

2. **Call site delegation** inside `ingest_from_db` (replaces 10-line inline SELECT with 2 lines):
   ```python
   sql, params = _build_topic_filter_query(topics)
   rows = conn.execute(sql, params).fetchall()
   ```

**`tests/unit/test_batch_ingest_topic_filter.py`** — 9 tests (7 named + 2 parametrize variants):

---

## Test Results

### New tests (9/9 green)

| Test | Status |
|------|--------|
| `test_sql_uses_lower_on_topic_column` | PASSED |
| `test_params_are_stripped_and_lowercased` | PASSED |
| `test_case_equivalence` | PASSED |
| `test_null_branch_preserved` | PASSED |
| `test_order_by_a_id_preserved` | PASSED |
| `test_placeholder_count_matches_topics_count[1]` | PASSED |
| `test_placeholder_count_matches_topics_count[3]` | PASSED |
| `test_placeholder_count_matches_topics_count[5]` | PASSED |
| `test_return_types` | PASSED |

### Existing suite

Run: `venv/Scripts/python -m pytest tests/unit/ -v -x --ignore=tests/unit/test_batch_ingest_topic_filter.py`

Result: **197 passed, 1 failed** — the single failure is `test_lightrag_embedding.py::test_embedding_func_reads_current_key` which is a **pre-existing baseline failure** (confirmed by running on the unmodified baseline via `git stash`). It's caused by a mock not expecting the `vertexai` kwarg added to `genai.Client` in the Vertex AI migration; unrelated to this task's changes.

---

## Grep Verification

```
$ grep -n "LOWER(c.topic)" batch_ingest_from_spider.py
991:    and applies LOWER(c.topic) on the column side so rows written by
1009:        WHERE (c.topic IS NULL OR LOWER(c.topic) IN ({placeholders}))
```
SQL occurrence: **exactly 1** (line 1009). Line 991 is the docstring.

```
$ grep -n "c\.topic IN (" batch_ingest_from_spider.py
(none)
```
Bare case-sensitive form: **fully removed**.

```
$ grep -n "ORDER BY a.id" batch_ingest_from_spider.py
997:      - ORDER BY a.id (FIFO ingest order)
1011:        ORDER BY a.id
```
ORDER BY preserved at line 1011 (SQL) and line 997 (docstring).

---

## Non-Negotiables Confirmation

| Invariant | Status |
|-----------|--------|
| `ORDER BY a.id` preserved | CONFIRMED (line 1011, also covered by `test_order_by_a_id_preserved`) |
| `c.topic IS NULL OR ...` branch preserved | CONFIRMED (line 1009, also covered by `test_null_branch_preserved`) |
| Column list unchanged (`a.id, a.title, a.url, acc.name, c.depth_score, a.body`) | CONFIRMED |
| `AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')` unchanged | CONFIRMED |
| Cron command on Hermes requires zero config change | CONFIRMED — fix is purely server-side SQL + param normalization |
| Classifier write path unchanged | CONFIRMED — classifier still writes `Agent` / `LLM` (pre-existing rows untouched) |

---

## Sanity Check

```
$ DEEPSEEK_API_KEY=dummy venv/Scripts/python -c "
    from batch_ingest_from_spider import _build_topic_filter_query
    sql, p = _build_topic_filter_query(['Agent','LLM'])
    print(p)
    assert p == ('agent','llm'), p
    print('SANITY PASS')
"
('agent', 'llm')
SANITY PASS
```

(DEEPSEEK_API_KEY=dummy needed due to known Phase 5 eager-import coupling documented in CLAUDE.md; test suite handles this via mocks.)

---

## Time to Day-1 Cron Fire

Commit landed at ~2026-05-03 20:30 ADT. Day-1 cron fires at 2026-05-04 06:00 ADT.
Window remaining at commit: **~9.5 hours**.

---

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `e59bc42` confirmed in `git log --oneline -1`
- `tests/unit/test_batch_ingest_topic_filter.py` exists and 9/9 pass
- `batch_ingest_from_spider.py` modified with helper + delegation
- All grep assertions hold
