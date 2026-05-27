# Deferred Items — phase kb-3-fastapi-bilingual-api

Items discovered during plan execution that are out of scope for the current
task and intentionally NOT fixed (per executor scope-boundary rule).

## kb-3-05 — pre-existing test pollution from `test_export.py`

**Discovered:** 2026-05-14 during kb-3-05 execution (regression check).

**Symptom:** Running `pytest tests/integration/kb/ tests/unit/kb/ -q` shows
2 failures in `tests/unit/kb/test_kb2_queries.py`:

- `test_related_entities_for_article`
- `test_cooccurring_entities_in_topic`

Both fail at `assert all(isinstance(r, EntityCount) for r in results)` —
`EntityCount` class identity drifts between import sites.

**Root cause:** `tests/integration/kb/test_export.py:56` calls
`importlib.reload(kb.data.article_query)`. After reload, `EntityCount` and
`TopicSummary` are NEW class objects. `tests/unit/kb/test_kb2_queries.py`
imported `EntityCount` at module load (before the reload), so its
`isinstance()` checks against the post-reload return values fail.

**Verification this is NOT caused by kb-3-05:**

```bash
git stash && pytest tests/integration/kb/ tests/unit/kb/ -q 2>&1 | tail -5 && git stash pop
# → same 2 failures present before kb-3-05 changes
```

**Why kb-3-05 is unaffected:** the kb-3-05 `app_client` fixture only reloads
`kb.config` and `kb.api` — NOT `kb.data.article_query` — precisely to avoid
this kind of class-identity invalidation (lesson learned from kb-3-02
Deviations).

**Scope:** kb-1 / kb-2 territory. The fix is to switch `test_export.py`'s
`importlib.reload(kb.data.article_query)` to `monkeypatch.setattr(...)` per
the kb-3-02 pattern. Out of scope for kb-3-05 (Surgical Changes principle —
do not refactor unrelated tests).

**When to fix:** when kb-1 or kb-2 next has a planning touch (or as a
standalone quick task).

## kb-3-06 — same pre-existing failure re-verified

**Discovered:** 2026-05-14 during kb-3-06 final regression check.

**Symptom:** Identical to the kb-3-05 entry above — same 2 failures in
`test_kb2_queries.py`, same root cause (`test_export.py` reloading
`kb.data.article_query` and invalidating `EntityCount` class identity).

**Verification this is NOT caused by kb-3-06:**

```bash
git stash -u && pytest tests/integration/kb/ tests/unit/kb/test_kb2_queries.py 2>&1 | tail -5 && git stash pop
# → same 2 failures present before kb-3-06 changes
```

**Why kb-3-06 is unaffected:** the new `tests/integration/kb/test_api_search.py`
fixture only reloads `kb.config`, `kb.services.search_index`,
`kb.api_routers.search`, and `kb.api`. It deliberately does NOT reload
`kb.data.article_query` — same defensive choice kb-3-05 made.

**No additional fix needed for kb-3-06.** Same scope/timing as the kb-3-05
entry above.
# Deferred items — kb-3 phase

## 2026-05-14 (kb-3-08 executor)

**Pre-existing test-isolation bug** (NOT caused by kb-3-08):
- `tests/unit/kb/test_kb2_queries.py::test_related_entities_for_article` FAILS in batch with the full kb test suite
- `tests/unit/kb/test_kb2_queries.py::test_cooccurring_entities_in_topic` FAILS in batch with the full kb test suite
- Both tests PASS in isolation (`pytest tests/unit/kb/test_kb2_queries.py`)
- Both tests PASS when run alongside ONLY the kb-3 baseline (no failure when restricted to test_api_*.py + test_synthesize_wrapper.py + test_search_index.py + test_job_store.py + test_rebuild_fts.py)
- Failure mode: `assert all(isinstance(r, EntityCount) for r in results)` returns False — looks like module-state leak (perhaps EntityCount class identity differs across test files due to importlib.reload)
- Pre-existing as of kb-3-08 start: confirmed via `git stash` reproduction — same 2 failures with my changes reverted
- Out of scope for kb-3-08 (the plan only ships /api/synthesize); should be diagnosed by a dedicated kb-2 quick if it blocks downstream work
