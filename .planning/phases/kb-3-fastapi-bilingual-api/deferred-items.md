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
