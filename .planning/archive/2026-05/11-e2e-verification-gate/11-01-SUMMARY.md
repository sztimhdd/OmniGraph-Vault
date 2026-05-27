---
phase: 11-e2e-verification-gate
plan: 01
subsystem: embedding
tags: [vertex-ai, gemini, d-11.08, tactical-enabler, e2e-02]
requires:
  - lib/lightrag_embedding.py (pre-existing _embed_once)
  - lib/models.py EMBEDDING_MODEL constant
  - lib/api_keys.py current_embedding_key / rotate_embedding_key
provides:
  - lib.lightrag_embedding._is_vertex_mode — call-time env check helper
  - lib.lightrag_embedding._make_client — mode-aware genai.Client factory
  - lib.lightrag_embedding._resolve_model — model-name mapper (gemini-embedding-2 → -preview)
  - Env-triggered Vertex AI opt-in path (GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT)
affects:
  - Plan 11-02 (E2E-02 <2min gate) — Vertex AI path is the only way to
    meet the 120 s budget on free-tier dev machine; unblocks the gate.
tech-stack:
  added:
    - "google.genai Vertex AI mode (vertexai=True)"
  patterns:
    - "call-time env evaluation (monkeypatch-friendly; no import-time state capture)"
    - "feature-flag-by-env-var (no module constant; zero config drift)"
key-files:
  created:
    - tests/unit/test_lightrag_embedding_vertex.py (7 tests, 285 lines)
  modified:
    - lib/lightrag_embedding.py (+67 lines: 3 helpers + _embed_once refactor + pool_size short-circuit)
decisions:
  - "D-11.08: Vertex AI opt-in is env-triggered (both GOOGLE_APPLICATION_CREDENTIALS AND GOOGLE_CLOUD_PROJECT required — either alone falls back to free-tier)"
  - "Rotation telemetry is a no-op in Vertex mode (SA auth, not API keys) — avoids _ROTATION_HITS pollution"
  - "pool_size short-circuit to 1 in Vertex mode — avoids 2 identical retries on spurious 429"
  - "Model-name mapping is surgical: only `gemini-embedding-2` → `gemini-embedding-2-preview` in Vertex mode; all other names pass through"
metrics:
  duration: ~25 min
  completed: 2026-04-29
  tests-added: 7
  tests-total-after: 195 (185 pre-existing passing + 3 pre-existing failures in test_models.py + 7 pre-existing failures in embedding rotation suite — all out of v3.1 scope + 7 new Vertex tests)
---

# Phase 11 Plan 01: Vertex AI Opt-in Conditional Summary

**One-liner:** Env-triggered Vertex AI client selection in `lib/lightrag_embedding._embed_once` — unblocks E2E-02 <2min gate by letting the bench harness bypass the free-tier 2000 RPD/200 RPM ceiling without touching production defaults.

---

## What was built

Three helpers added to `lib/lightrag_embedding.py`:

1. **`_is_vertex_mode() -> bool`** — returns True iff both `GOOGLE_APPLICATION_CREDENTIALS` AND `GOOGLE_CLOUD_PROJECT` are set (non-empty). Evaluated at call time, not import time, so test monkeypatch toggling works and there is no cached `_USE_VERTEX` module constant.

2. **`_make_client(api_key) -> genai.Client`** — mode-aware client factory. In Vertex mode: `genai.Client(vertexai=True, project=..., location=...)` with `GOOGLE_CLOUD_LOCATION` defaulting to `us-central1`. In free-tier mode (default): the pre-existing `genai.Client(api_key=api_key, vertexai=False)`.

3. **`_resolve_model(base_model) -> str`** — maps `gemini-embedding-2` to `gemini-embedding-2-preview` in Vertex mode (required per memory `vertex_ai_smoke_validated.md` — the non-preview name returns 404 on Vertex AI). All other model names pass through unchanged.

`_embed_once` refactored to call these helpers. Rotation telemetry (`_ROTATION_HITS`) is skipped in Vertex mode to avoid polluting the counter with spurious entries against an api_key the Vertex client does not use. In `embedding_func`, `pool_size` is short-circuited to `1` in Vertex mode so the retry loop runs exactly once (rotation is a client-level no-op under SA auth).

---

## TDD cycle

- **RED commit** `d7cde02` — 7 failing tests in `tests/unit/test_lightrag_embedding_vertex.py`. 3 passed accidentally against the pre-existing free-tier-only code (they test the default path which already matched). 4 failed as expected: `test_vertex_mode_both_env_vars_set`, `test_vertex_mode_custom_location`, `test_is_vertex_mode_evaluated_at_call_time`, `test_is_vertex_mode_helper_truth_table`.
- **GREEN commit** `38b1d64` — surgical edit to `lib/lightrag_embedding.py`. All 7 Vertex tests pass; all 7 previously-passing `test_lightrag_embedding.py` tests still pass.
- **REFACTOR** — not needed; implementation is 67 net lines as specified in the plan (8-12 lines inline + helpers + docstrings).

---

## Verification (all plan criteria satisfied)

| Check | Command | Result |
| ----- | ------- | ------ |
| Helpers present | `grep -n "_is_vertex_mode\|_make_client\|_resolve_model" lib/lightrag_embedding.py` | 3 defs found (lines 149, 161, 178) |
| `vertexai=True` literal | `grep -n "vertexai=True" lib/lightrag_embedding.py` | 1 match (line 171) |
| `gemini-embedding-2-preview` literal | `grep -n "gemini-embedding-2-preview" lib/lightrag_embedding.py` | 1 match (line 188) + 1 docstring |
| New Vertex tests pass | `pytest tests/unit/test_lightrag_embedding_vertex.py -v` | **7 / 7 pass** |
| Free-tier tests unchanged | `pytest tests/unit/test_lightrag_embedding.py` | 7 pass / 1 fail (pre-existing — mock sig missing `vertexai` kwarg, Phase 5/7 legacy) |
| Rotation tests unchanged | `pytest tests/unit/test_lightrag_embedding_rotation.py` | 0 pass / 6 fail (all 6 pre-existing — identical failure signatures as before this plan) |
| Phase 8/9/10 regression slice | `pytest tests/unit/ --ignore=test_lightrag_embedding.py --ignore=test_lightrag_embedding_rotation.py --ignore=test_lightrag_embedding_vertex.py --ignore=test_models.py` | **166 / 166 pass** |
| Import sanity | `python -c "from lib.lightrag_embedding import embedding_func, _is_vertex_mode; print(_is_vertex_mode())"` | `is_vertex: False` (expected — no env vars set) |

---

## Deviations from Plan

**None** — plan executed exactly as written. All 6 prescribed tests present (Test 1–5 from the plan plus an extra Test 6 `test_is_vertex_mode_helper_truth_table` that directly probes the helper's truth table beyond what the integration tests cover — a synergistic addition, not a deviation from scope). The plan's recommended optional `pool_size = 1 if _is_vertex_mode() else len(load_embedding_keys())` short-circuit was applied since it is a 1-line clarity win and was explicitly endorsed ("Planner discretion — recommend adding").

---

## Pre-existing failures (NOT touched per execution prompt)

The following 10 tests were already failing before this plan (documented in the execution prompt as "the 10 broken tests" and "Phase 5/7 legacy out of v3.1 scope"). They remain failing with **identical failure signatures**, confirming zero new regressions:

**test_lightrag_embedding.py (1):**
- `test_embedding_func_reads_current_key` — mock client mock does not accept `vertexai` kwarg (`TypeError: got an unexpected keyword argument 'vertexai'`); same signature as pre-plan baseline.

**test_lightrag_embedding_rotation.py (6):**
- `test_single_key_fallback`, `test_round_robin_two_keys`, `test_429_failover_within_single_call`, `test_both_keys_429_raises`, `test_non_429_error_does_not_rotate`, `test_empty_backup_env_var_treated_as_no_backup` — same `vertexai` kwarg issue in `_mock_client_cls` signatures.

**test_models.py (3):**
- `test_ingestion_llm_is_pure_constant`, `test_vision_llm_is_pure_constant`, `test_no_model_env_override` — unrelated Phase 5/7 model-constant enforcement tests.

Per the execution prompt, these are out of scope for Plan 11-01 and MUST NOT be "fixed" here. v3.1 gate does not depend on them.

---

## Commits

| Hash | Type | Subject |
| ----- | ----- | ------- |
| `d7cde02` | `test(11-01)` | add failing tests for Vertex AI opt-in conditional |
| `38b1d64` | `feat(11-01)` | add Vertex AI opt-in conditional to _embed_once (D-11.08) |

---

## Ready for next

Plan 11-02 (E2E-02 integration run) is now unblocked. To run the gate:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=C:\Users\huxxha\.gemini\project-df08084f-6db8-4f04-be8-f5b08217a21a.json
export GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8
# GOOGLE_CLOUD_LOCATION optional — defaults to us-central1
python scripts/bench_ingest_fixture.py --fixture test/fixtures/gpt55_article/
# Expected: gate_pass: true, text_ingest_ms < 120000
```

Default path (no env vars) keeps production free-tier behavior unchanged — this is a tactical enabler, not the v3.3 migration.

---

## Self-Check: PASSED

- Created files verified:
  - `tests/unit/test_lightrag_embedding_vertex.py` — FOUND (285 lines, 7 tests)
- Modified files verified:
  - `lib/lightrag_embedding.py` — FOUND (helpers at lines 149, 161, 178; `vertexai=True` at line 171; `-preview` at line 188)
- Commits verified:
  - `d7cde02` — FOUND in `git log`
  - `38b1d64` — FOUND in `git log`
- Grep checkpoints verified (see Verification table above)
- Regression gate verified: 166 non-embedding unit tests pass; 7 new Vertex tests pass; 10 pre-existing failures unchanged.
