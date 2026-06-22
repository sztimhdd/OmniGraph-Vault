---
phase: arx-2-finish
plan: 00
wave: 1
status: complete
completed: 2026-06-12
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3]
---

# Wave 0 (plan 00) — Scaffold + GAP-D confirm — SUMMARY

## What was built

Test scaffolding (RED floor for GAP-A) + a recorded GAP-D liveness confirmation.
No production code changed — the synthesizer is untouched (Wave 1's job).

### Task 1 — conftest autouse mock + 3 RED synthesizer-LLM tests (CODE)

- **`tests/unit/research/conftest.py`** (NEW): autouse function-scoped fixture
  patching `lib.research.stages.synthesizer.get_llm_func` → no-op async provider
  (`"# Stub\n\nStub body."`). Protects the 10 existing caption tests from hitting
  the real DeepSeek dispatcher once Wave 1 makes synthesizer call `get_llm_func()`.
- **`tests/unit/research/test_synthesizer_llm.py`** (NEW): 3 behavioral tests, bodies
  verbatim from RESEARCH §Risk C (lines 436-493), import block + `_make_minimal_cfg`
  mirrored from `test_synthesizer_caption_embeds.py`:
  - `test_synthesizer_uses_all_chunks_in_prompt` — prompt contains all 3 chunk snippets.
  - `test_synthesizer_degrades_gracefully_on_llm_failure` — LLM raise → note_line + non-empty markdown, no raise.
  - `test_synthesizer_real_prose_not_chunks0_verbatim` — real prose replaces `chunks[0].snippet` verbatim.

## Deviation (recorded per pre-execution gate)

**`create=True` added to all 4 `mock.patch` sites** (conftest + 3 tests). Plan 00 Task 1's
own NOTE flagged this risk ("adjust the patch target ... verify when Wave 1 lands"). The
current synthesizer module has no `get_llm_func` attribute, so `mock.patch(..., create=False)`
raised `AttributeError` at patch **setup** → tests ERRORED instead of failing on assertions.
Plan 00 acceptance is explicit: *"A collection ERROR ... is NOT acceptable — failures must be
assertion failures."* `create=True` makes the patch valid at Wave 0 (synthesizer unchanged) so
the tests fail on the ASSERTION (RED, against the real stub `run()`), and is a harmless no-op at
Wave 1 once the attribute exists.

**Forward-constraint surfaced for Wave 1 (plan 01):** the patch target
`lib.research.stages.synthesizer.get_llm_func` is pinned in 4 places (conftest, 3 tests) AND
in plan 00's `key_links`. For patch-where-used to intercept, **Wave 1 MUST import
`get_llm_func` at MODULE level** (`from lib.llm_complete import get_llm_func` at top of
synthesizer.py), NOT a function-body-level import (a function-body re-import reads the source
module each call → the synthesizer-namespace patch would never fire → the 3 tests would call
the real provider and fail). Module-level import is cheap (the DeepSeek import is deferred
*inside* `get_llm_func()` per llm_complete.py:47-49). This reconciles plan 01's "lazy import"
wording with the patch contract: lazy w.r.t. the heavy provider, eager w.r.t. the dispatcher.

### Task 2 — GAP-D liveness CONFIRM (orchestrator-run read-only SSH, Principle #5)

Run by the orchestrator itself (not the executor; not handed to the user):

```
ssh aliyun-vitaclaw: REPO=/root/OmniGraph-Vault
  git merge-base --is-ancestor 38a7286 HEAD → ANCESTOR_OK
  HEAD=ba1121c
  kb-api LISTEN 127.0.0.1:8766 (python pid 3918143)
  curl POST http://127.0.0.1:8766/api/research {"query":"ping","max_iterations":1}
    → HTTP=200 time=12.000s (held the full SSE window, streamed — NOT 404)
```

**GAP D = CONFIRMED LIVE.** Aliyun HEAD `ba1121c` has `38a7286` as ancestor; `/api/research`
returns 200 + streams SSE. NO pull, NO kb-api restart performed (Fact 6 holds in prod).
Recorded port `8766` + repo path `/root/OmniGraph-Vault` for Wave 4.

## Verification

| Check | Result |
|-------|--------|
| `pytest tests/unit/research/test_synthesizer_llm.py -v` | 3 FAILED on **assertions** (RED), 0 errors ✅ |
| `pytest tests/unit/research/test_synthesizer_caption_embeds.py -v` | 10 passed ✅ |
| `pytest tests/unit/research/` | 169 passed, 3 failed (only the intentional RED), 0 collection errors ✅ |
| GAP-D ancestry | ANCESTOR_OK (38a7286 ⊆ ba1121c) ✅ |
| GAP-D endpoint | HTTP 200 + 12s SSE hold, not 404 ✅ |

## Key files

- created: `tests/unit/research/conftest.py`
- created: `tests/unit/research/test_synthesizer_llm.py`

## Self-Check: PASS

3 RED GAP-A tests collected + failing on assertions; conftest autouse mock present; 10 caption
tests green; GAP-D confirmed live with no deploy action.
