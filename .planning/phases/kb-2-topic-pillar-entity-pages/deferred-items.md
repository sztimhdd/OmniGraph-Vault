# Deferred Items — kb-2 Phase

Items discovered during execution that fall outside the current task's scope.
Per `<deviation_rules>` SCOPE BOUNDARY: log here, do NOT auto-fix.

---

## DEFERRED-1: Test pollution — kb-1 `export_module` fixture's `importlib.reload`
breaks kb-2 unit tests

**Discovered during:** kb-2-10 execution (2026-05-13)

**Symptom:** Running `pytest tests/integration/kb/ tests/unit/kb/` causes 2 failures
in `tests/unit/kb/test_kb2_queries.py`:

- `test_related_entities_for_article` — `assert all(isinstance(r, EntityCount) for r in results)` fails
- `test_cooccurring_entities_in_topic` — same assertion failure

**Root cause:** `tests/integration/kb/test_export.py::export_module` (kb-1) calls
`importlib.reload(kb.data.article_query)` at fixture setup. After reload, the
module's `EntityCount` is a new class object, but already-instantiated dataclass
instances retain the pre-reload class identity. When the kb-2 unit test (run in
the same Python process after kb-1 integration) does `from kb.data.article_query
import EntityCount`, it gets the post-reload class — which `isinstance()` check
fails against pre-reload instances cached anywhere.

**Verification:** kb-2-10's new `test_kb2_export.py` uses `subprocess.run` for the
driver invocation (no in-process module reload), so it does NOT cause this pollution.
The pollution originates entirely from kb-1's `test_export.py`. Verified by:

```bash
# Reproduces failure (kb-1 reload fixture in same process):
pytest tests/integration/kb/test_export.py tests/unit/kb/  # 2 failed

# No failure (kb-2-10's subprocess fixture in same process):
pytest tests/integration/kb/test_kb2_export.py tests/unit/kb/  # all pass
```

**Impact:** kb-2 unit tests are CORRECT in isolation. The combined run order
`test_export.py` → `test_kb2_queries.py` is the only failing path. CI / local
dev should either:

1. Run integration + unit suites separately (workaround), OR
2. Fix `export_module` fixture to use a subprocess invocation OR drop the
   `importlib.reload` (proper fix — likely the right move now that kb-2-10
   demonstrates subprocess works)

**Scope:** OUT-OF-SCOPE for kb-2-10 (the failures are in code kb-2-10 did not
touch — kb-1's `test_export.py` and kb-2-04's unit tests). Logging here for
follow-up. Recommend a quick task to refactor `export_module` away from
`importlib.reload` after kb-2 phase ratification.

**Workaround for kb-2 phase verifier:** Run the two suites separately:
```bash
pytest tests/integration/kb/  # all integration tests pass together
pytest tests/unit/kb/         # all unit tests pass together
```
