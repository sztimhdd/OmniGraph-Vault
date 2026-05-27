---
phase: 11-e2e-verification-gate
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/lightrag_embedding.py
  - tests/unit/test_lightrag_embedding_vertex.py
autonomous: true
requirements: [E2E-02]

must_haves:
  truths:
    - "When neither GOOGLE_APPLICATION_CREDENTIALS nor GOOGLE_CLOUD_PROJECT are set, embedding calls use free-tier path (vertexai=False + api_key=current_embedding_key()) AND model name is gemini-embedding-2 (current behavior preserved)"
    - "When BOTH env vars are set, embedding calls construct genai.Client(vertexai=True, project=..., location=...) AND model name is gemini-embedding-2-preview"
    - "When only ONE of the two env vars is set (not both), embedding falls back to the free-tier path (both-required semantics)"
    - "Rotation logic (current_embedding_key / rotate_embedding_key) becomes a no-op when _USE_VERTEX is active — no spurious ROTATION_HITS recording against a key Vertex does not use"
    - "All 16 existing lightrag_embedding tests pass unchanged (Phase 7 + rotation — 14 in test_lightrag_embedding.py + 2 in test_lightrag_embedding_rotation.py)"
  artifacts:
    - path: "lib/lightrag_embedding.py"
      provides: "_is_vertex_mode() function + _make_client() helper + _resolve_model() helper integrated into _embed_once"
      contains: "_USE_VERTEX|_is_vertex_mode|vertexai=True"
    - path: "tests/unit/test_lightrag_embedding_vertex.py"
      provides: "Unit tests for Vertex conditional: 3 path-selection tests + 1 regression test"
      min_lines: 90
  key_links:
    - from: "lib/lightrag_embedding.py"
      to: "genai.Client"
      via: "_make_client(api_key) — selects vertexai=True vs vertexai=False based on env vars"
      pattern: "genai\\.Client\\(vertexai=True"
    - from: "lib/lightrag_embedding.py"
      to: "EMBEDDING_MODEL"
      via: "_resolve_model(base_model) — returns -preview variant when _USE_VERTEX"
      pattern: "gemini-embedding-2-preview"
---

<objective>
Add an env-triggered Vertex AI opt-in conditional to `lib/lightrag_embedding.py` so that the
E2E-02 <2min gate (plan 11-02) can pass on the developer's machine — free-tier Gemini (2000
RPD / 2 keys) is mathematically inadequate for the ~1800 embed calls a heavy article requires
within 2 minutes.

Purpose: UNBLOCK the benchmark gate. This is a TACTICAL enabler, NOT the v3.3 migration.
Production default (no env vars) uses the free-tier path unchanged. v3.3 does the real migration.

Output: 8-12 line conditional that switches `genai.Client` to Vertex AI mode when
`GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` are both set, and resolves the model
name to `gemini-embedding-2-preview` (empirically required per memory
`vertex_ai_smoke_validated.md` — `gemini-embedding-2` returns 404 on Vertex AI).

This plan is INDEPENDENT of 11-00 (different files, no shared code). Can execute in parallel.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/11-e2e-verification-gate/11-PRD.md
@.planning/phases/11-e2e-verification-gate/11-CONTEXT.md
@lib/lightrag_embedding.py
@lib/models.py
@lib/api_keys.py
@tests/unit/test_lightrag_embedding.py

<interfaces>
<!-- Key contracts the executor needs. Extract from codebase. -->

Current `_embed_once` signature (lib/lightrag_embedding.py:148-171):
```python
async def _embed_once(contents: list, model: str) -> np.ndarray:
    api_key = current_embedding_key()
    client = genai.Client(api_key=api_key, vertexai=False)
    response = await client.aio.models.embed_content(
        model=model,
        contents=contents,
        config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
    )
    _ROTATION_HITS[api_key] = _ROTATION_HITS.get(api_key, 0) + 1
    vec = np.asarray(response.embeddings[0].values, dtype=np.float32)
    return vec
```

Current `embedding_func` decorator (line 174-180):
```python
@wrap_embedding_func_with_attrs(
    embedding_dim=EMBEDDING_DIM,
    send_dimensions=True,
    max_token_size=EMBEDDING_MAX_TOKENS,
    model_name=EMBEDDING_MODEL,  # This is "gemini-embedding-2"
)
async def embedding_func(texts: list[str], **kwargs: Any) -> np.ndarray:
    ...
    model = EMBEDDING_MODEL  # Line 194 — passed as `model` kwarg to _embed_once
```

From memory `vertex_ai_smoke_validated.md`:
- Vertex AI model name: `gemini-embedding-2-preview` (REQUIRED — `gemini-embedding-2` returns 404)
- SA JSON path: `C:\Users\huxxha\.gemini\project-df08084f-6db8-4f04-be8-f5b08217a21a.json` (for
  manual local testing; NOT committed)
- Project ID: `project-df08084f-6db8-4f04-be8`; Location: `us-central1`
- Vertex AI API enabled + billing active + $300 credit accessible

Existing test pattern (tests/unit/test_lightrag_embedding.py lines 21-34) — `_reset_api_keys_state`
autouse fixture clears module state. Reuse this pattern for Vertex tests (add monkeypatch.delenv
for GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION so Vertex
tests set what they need and free-tier tests are guaranteed not to activate Vertex mode).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add Vertex AI opt-in conditional to _embed_once + resolve model name</name>
  <files>lib/lightrag_embedding.py, tests/unit/test_lightrag_embedding_vertex.py</files>
  <behavior>
    Test 1 — Default (no env vars) path unchanged:
      - With `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT` both unset:
      - `genai.Client` called with `api_key=<current_embedding_key>` and `vertexai=False`
      - `embed_content` called with `model="gemini-embedding-2"`
      - `_ROTATION_HITS[api_key]` incremented (rotation still active)
      - Matches current behavior exactly → all 14 existing `test_lightrag_embedding.py` tests pass

    Test 2 — Vertex AI mode when both env vars set:
      - `monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")`
      - `monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project-123")`
      - Invoke embedding_func; assert:
        - `genai.Client` called with kwargs `vertexai=True, project="my-project-123", location="us-central1"`
          (default location)
        - `embed_content` called with `model="gemini-embedding-2-preview"` (suffix applied)
        - `api_key` arg NOT passed (or passed as None) — Vertex uses SA JSON, not API keys
        - `_ROTATION_HITS` unchanged (rotation is no-op in Vertex mode)

    Test 3 — Custom location respected:
      - All 3 env vars set: `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT`,
        `GOOGLE_CLOUD_LOCATION=europe-west4`
      - `genai.Client` called with `location="europe-west4"`

    Test 4 — Only ONE env var set → falls back to free tier (both-required semantics):
      - Only `GOOGLE_APPLICATION_CREDENTIALS` set → free-tier path (vertexai=False, model=gemini-embedding-2)
      - Only `GOOGLE_CLOUD_PROJECT` set → free-tier path (vertexai=False, model=gemini-embedding-2)

    Test 5 — `_is_vertex_mode()` evaluated at call time (not import time):
      - Module imported with no env vars → free-tier path active
      - monkeypatch sets both env vars → next call uses Vertex path
      - monkeypatch.delenv both → next call reverts to free-tier
      - (Ensures no cached `_USE_VERTEX` constant captured at import)

    Test 6 — Regression: 61 cumulative tests still pass:
      - Run full unit test suite, assert 0 failures. Specifically the 14 in test_lightrag_embedding.py
        and 2 in test_lightrag_embedding_rotation.py must all remain green.
  </behavior>
  <action>
    Edit `lib/lightrag_embedding.py`:

    1. Add `import os` at top (if not already present — it isn't per current file read).

    2. Add helper functions BEFORE `_embed_once` (around line 148):
       ```python
       def _is_vertex_mode() -> bool:
           """Return True iff both Vertex AI env vars are set.

           Evaluated at CALL TIME, not import time — supports test monkeypatch
           toggling and preserves the v3.3-migration-deferred scope of D-11.08.
           """
           return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")) and \
                  bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


       def _make_client(api_key: str) -> "genai.Client":
           """Construct a genai.Client for the current mode (D-11.08).

           Vertex mode (both env vars set) uses SA JSON auth — api_key is ignored.
           Free-tier mode uses the rotation-managed api_key as before.
           """
           if _is_vertex_mode():
               return genai.Client(
                   vertexai=True,
                   project=os.environ["GOOGLE_CLOUD_PROJECT"],
                   location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
               )
           return genai.Client(api_key=api_key, vertexai=False)


       def _resolve_model(base_model: str) -> str:
           """Map free-tier model name to Vertex AI equivalent when in Vertex mode.

           Memory ref: vertex_ai_smoke_validated.md — gemini-embedding-2 returns
           404 on Vertex AI; gemini-embedding-2-preview is the working multimodal
           model name. Only applied when _is_vertex_mode() is True AND base_model
           matches the free-tier name; other model names pass through unchanged.
           """
           if _is_vertex_mode() and base_model == "gemini-embedding-2":
               return "gemini-embedding-2-preview"
           return base_model
       ```

    3. Modify `_embed_once` (lines 148-171) to use the new helpers:
       ```python
       async def _embed_once(contents: list, model: str) -> np.ndarray:
           """Place ONE embed_content call against the current rotation key OR Vertex SA."""
           use_vertex = _is_vertex_mode()
           api_key = current_embedding_key() if not use_vertex else ""
           client = _make_client(api_key)
           resolved_model = _resolve_model(model)
           response = await client.aio.models.embed_content(
               model=resolved_model,
               contents=contents,
               config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
           )
           # Rotation telemetry is meaningful only for the key-rotated free-tier path.
           # In Vertex mode the SA handles auth and rotation is a no-op; skip the
           # telemetry to avoid polluting _ROTATION_HITS with non-key entries.
           if not use_vertex:
               _ROTATION_HITS[api_key] = _ROTATION_HITS.get(api_key, 0) + 1
           vec = np.asarray(response.embeddings[0].values, dtype=np.float32)
           return vec
       ```

    4. In `embedding_func` body (around line 192-194), consider the rotation loop behavior in
       Vertex mode. Current rotation loop retries SAME text on 429 with next key; in Vertex
       mode 429 semantics differ (billing-backed, rare). Keep the retry loop AS IS —
       `rotate_embedding_key()` is already a cheap pointer advance; the actual client in
       `_make_client` ignores the api_key in Vertex mode, so rotation is a no-op at the client
       level. This preserves the identical code path between modes and minimizes diff.

       Optionally, add a tiny short-circuit at loop entry:
       ```python
       # D-11.08: Vertex mode: rotation is a no-op (SA auth). Single attempt suffices.
       pool_size = 1 if _is_vertex_mode() else len(load_embedding_keys())
       ```
       This ensures the `for _ in range(pool_size)` loop runs exactly once in Vertex mode
       (avoids 2 identical retries on a spurious 429). Planner discretion — recommend adding
       this since it's 1 line and makes the test surface cleaner.

    5. DO NOT modify:
       - `@wrap_embedding_func_with_attrs` decorator args (`model_name=EMBEDDING_MODEL` stays)
       - `EMBEDDING_MODEL` / `EMBEDDING_DIM` / `EMBEDDING_MAX_TOKENS` constants in `lib/models.py`
       - Any other file in `lib/`
       - Rotation logic in `embedding_func` beyond the optional `pool_size` short-circuit above

    Create `tests/unit/test_lightrag_embedding_vertex.py`:

    1. Module docstring: "Tests for Vertex AI opt-in conditional (D-11.08 / Plan 11-01)."
    2. Imports match `test_lightrag_embedding.py` patterns: `from __future__ import annotations`,
       `from unittest.mock import AsyncMock, MagicMock, patch`, `import numpy as np`, `import pytest`.
    3. Autouse fixture clearing rotation state AND Vertex env vars:
       ```python
       @pytest.fixture(autouse=True)
       def _reset_state(monkeypatch):
           monkeypatch.setenv("GEMINI_API_KEY", "test-free-tier-key")
           monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
           monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)
           monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
           monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
           monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
           monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
           import lib.api_keys as k
           k._cycle = None
           k._current = None
           k._rotation_listeners.clear()
           import lib.lightrag_embedding as lem
           lem._ROTATION_HITS.clear()
       ```
    4. Test 1 — `test_free_tier_path_default`: no env vars set. Mock `genai.Client` via
       `monkeypatch.setattr(lem.genai, "Client", captured_mock)`. Invoke embedding_func, assert
       the captured mock was called with `api_key="test-free-tier-key"`, `vertexai=False`. Assert
       `embed_content` called with `model="gemini-embedding-2"`.
    5. Test 2 — `test_vertex_mode_both_env_vars_set`: monkeypatch both env vars. Assert
       `genai.Client` called with `vertexai=True, project="my-project-123", location="us-central1"`.
       Assert `embed_content` called with `model="gemini-embedding-2-preview"`.
    6. Test 3 — `test_vertex_mode_custom_location`: also set `GOOGLE_CLOUD_LOCATION=europe-west4`;
       assert `location="europe-west4"`.
    7. Test 4a — `test_only_credentials_set_falls_back`: only `GOOGLE_APPLICATION_CREDENTIALS` set.
       Assert free-tier path taken.
    8. Test 4b — `test_only_project_set_falls_back`: only `GOOGLE_CLOUD_PROJECT` set.
       Assert free-tier path taken.
    9. Test 5 — `test_is_vertex_mode_evaluated_at_call_time`: invoke once with no env vars
       (assert free-tier). Set both env vars. Invoke again (assert Vertex). delenv both.
       Invoke third time (assert free-tier). Proves import-time capture bug is absent.

    Compliance:
    - Windows: `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_lightrag_embedding_vertex.py -v`
    - Type hints on all new helper functions.
    - `logger` for diagnostics, no `print` (lib/ module convention).
    - Secrets via env only — no committed SA JSON path strings in tests (tests use `/fake/sa.json` sentinel).
    - Do not set `_USE_VERTEX` as a module-level constant — env var evaluation at call time is
      required for monkeypatch testability.

    Implements decision per D-11.08 (Vertex AI opt-in conditional).
  </action>
  <verify>
    <automated>set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_lightrag_embedding_vertex.py tests/unit/test_lightrag_embedding.py tests/unit/test_lightrag_embedding_rotation.py -v</automated>
  </verify>
  <done>
    - `lib/lightrag_embedding.py` has `_is_vertex_mode`, `_make_client`, `_resolve_model` helpers
    - `_embed_once` uses the helpers and conditionally skips rotation telemetry in Vertex mode
    - `tests/unit/test_lightrag_embedding_vertex.py` has ≥ 6 tests, all passing
    - All 14 existing tests in `test_lightrag_embedding.py` pass unchanged
    - All 2 tests in `test_lightrag_embedding_rotation.py` pass unchanged
    - Full regression (61 + 6 = 67 tests) green
    - `grep -n "gemini-embedding-2-preview" lib/lightrag_embedding.py` returns 1 match in `_resolve_model`
    - `grep -n "vertexai=True" lib/lightrag_embedding.py` returns 1 match in `_make_client`
  </done>
</task>

</tasks>

<verification>
Phase-level checks for this plan:

1. `grep -n "_is_vertex_mode\|_make_client\|_resolve_model" lib/lightrag_embedding.py` → 3 helper definitions found
2. `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_lightrag_embedding_vertex.py -v` → 6+ tests passing
3. `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_lightrag_embedding.py tests/unit/test_lightrag_embedding_rotation.py -v` → 14 + 2 = 16 tests passing (zero regressions)
4. Full regression: `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/ -x` → ≥ 67 tests passing
5. Import sanity: `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -c "from lib.lightrag_embedding import embedding_func, _is_vertex_mode; print(_is_vertex_mode())"` prints `False` (env vars unset)
</verification>

<success_criteria>
- Free-tier path preserved — no regressions in existing embedding tests
- Vertex AI path activated only when BOTH env vars set (not either alone)
- Model name correctly resolves to `gemini-embedding-2-preview` in Vertex mode
- Env var check happens at call time, not import time (monkeypatch-friendly)
- Rotation telemetry skipped in Vertex mode (no pollution of _ROTATION_HITS)
- Total of ≥ 67 unit tests passing (61 prior + 6 new)
</success_criteria>

<output>
After completion, create `.planning/phases/11-e2e-verification-gate/11-01-SUMMARY.md` following the
standard plan summary template.
</output>
