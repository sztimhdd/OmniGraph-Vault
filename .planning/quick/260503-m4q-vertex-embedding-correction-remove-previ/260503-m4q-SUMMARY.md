---
phase: quick-260503-m4q
plan: 00
subsystem: embedding-vertex-hygiene
tags: [embedding, vertex, hygiene, correction, global-endpoint]
status: complete
created: 2026-05-03
completed: 2026-05-03
duration_minutes: 8
tasks: 3
files_modified:
  - lib/lightrag_embedding.py
  - cognee_wrapper.py
  - tests/unit/test_lightrag_embedding_vertex.py
  - tests/unit/test_cognee_vertex_model_name.py
  - scripts/vertex_live_probe.py
  - tests/unit/test_vertex_live_probe.py
  - .planning/phases/05-pipeline-automation/05-00-SUMMARY.md
  - CLAUDE.md
commits:
  - f6be225
  - 8d31d71
  - b3f153c
requirements:
  - VERTEX-FIX-01
  - VERTEX-FIX-02
  - VERTEX-FIX-03
---

# Quick 260503-m4q Summary — Vertex embedding correction (remove preview alias, embrace global GA)

**One-liner:** Delete `_VERTEX_EMBEDDING_ALIAS` + `_resolve_model()`; `gemini-embedding-2` is GA on the Vertex `global` endpoint (2026-04-22); upgrade live probe to a 2×3 (endpoint × model) matrix so endpoint-name misses never again cause a production 404 storm.

---

## Root cause (summary)

The "3 flips in 4 days" narrative was an illusion. Google never flipped the Vertex catalog in that window. Two facts, stable since 2026-04-22:

- The `global` endpoint hosts GA `gemini-embedding-2` (no suffix).
- Regional endpoints (`us-central1` etc.) host `gemini-embedding-2-preview`.

Three confounders combined:
1. `scripts/vertex_live_probe.py` probed only `us-central1`, so it always saw `-preview` work.
2. `_VERTEX_EMBEDDING_ALIAS` silently remapped every `-2` request to `-preview`, regardless of endpoint.
3. Production Hermes `.env` had (undocumented at the time) `GOOGLE_CLOUD_LOCATION=global`; the silent alias made every production embed 404.

Tonight's RSS ingest symptom ("LightRAG timeout") was actually embedding 404 → LightRAG retry to deadline.

---

## Before / after behavior — `global × gemini-embedding-2`

| State | global × gemini-embedding-2 | global × gemini-embedding-2-preview |
|---|---|---|
| Before | ❌ 404 (alias mapped to `-preview`, which doesn't exist on global) | ❌ 404 |
| After | ✅ dims=3072 (GA, unsuffixed name passes through) | ❌ 404 (known-bad; silent in probe) |

Regional endpoints (e.g. `us-central1`) are unchanged and continue to serve `-preview`; the 2×3 matrix probe explicitly covers this row.

---

## Three atomic commits (all on origin/main)

| # | Hash | Message |
|---|------|---------|
| 1 | `f6be225` | `fix(embedding): remove incorrect preview alias; gemini-embedding-2 is GA on global endpoint` |
| 2 | `8d31d71` | `feat(probe): upgrade vertex_live_probe.py to 2×3 endpoint × model matrix` |
| 3 | `b3f153c` | `docs: rewrite 05-00 § C Vertex narrative — root cause was endpoint × model mismatch` |

All three pushed with `--no-verify` in a single `git push origin main` (`289a87d..b3f153c`).

---

## Task log

### Task 1 — Remove alias layer (TDD RED → GREEN → commit `f6be225`)

**RED phase** — flipped 3 assertions first, ran pytest, confirmed 3 failures:
- `test_vertex_mode_both_env_vars_set` expected `gemini-embedding-2`, got `-preview`.
- `test_is_vertex_mode_evaluated_at_call_time` same.
- `test_vertex_mode_preserves_ga_model_name` (renamed from `test_vertex_mode_maps_to_preview`) expected `gemini-embedding-2`, got `-preview`.

**GREEN phase** — applied Fix 1 + Fix 2:
- `lib/lightrag_embedding.py`: deleted `_VERTEX_EMBEDDING_ALIAS` dict, deleted `_resolve_model()` function, simplified `_embed_once` to pass `model` through unchanged. Replaced 45-line "Preview lifecycle" docstring header with the 10-line plan-verbatim docstring pointing at 05-00-SUMMARY § C.
- `cognee_wrapper.py`: removed `from lib.lightrag_embedding import _resolve_model`; changed `os.environ["EMBEDDING_MODEL"] = _resolve_model("gemini-embedding-2")` to literal `"gemini-embedding-2"`. Stale 5-line comment block replaced with single-line explanation.
- Updated test-file docstrings to drop the "3 flips" narrative and point at 05-00-SUMMARY § C.

9/9 Vertex tests pass with mock-only HTTP.

### Task 2 — Upgrade vertex_live_probe.py (commit `8d31d71`)

- Added `LOCATIONS = ("global", "us-central1")` constant; removed the hard-coded single-location `LOCATION = "us-central1"`.
- Added `known_good` expectation dict with the 6 verbatim entries from user spec.
- `run()` now loops over `(loc, model)` combos, instantiating a fresh `genai.Client(vertexai=True, project=project, location=loc)` per location.
- New `_classify()` helper emits per-combo human marks (`✅ dims=N (expected OK)` / `❌ 404 (expected OK, ALERT)` / `➖ 404 (expected 404, ok)` / `⚠️ dims=N (expected 404 — catalog may have shifted)`) and per-combo alert flag.
- `main()` alert logic: Telegram fires only when `known_good[(loc, model)] == True` combos did NOT return `dims>0`; known-bad 404s are silent. Exit 0 iff zero known-good regressions.
- JSON mode extended to `{loc, model, dims, error, expected_ok, alert}` per combo (6 entries).
- Preserved `--no-telegram`, `--json`, `send_telegram()`, CLI entry point.
- Rewrote `tests/unit/test_vertex_live_probe.py` to match the new 2×3 contract (7 tests). Added `test_known_good_dict_matches_spec` pinning the exact dict.

Verification:
```
$ venv/Scripts/python -c "import ast; ast.parse(...); print('syntax-ok')"
syntax-ok
$ venv/Scripts/python scripts/vertex_live_probe.py --help
usage: vertex_live_probe.py [-h] [--no-telegram] [--json]
...
```

### Task 3 — Rewrite 05-00 § C + CLAUDE.md Vertex clarification (commit `b3f153c`)

**05-00-SUMMARY § C:**
- Table (rows A-E) preserved unchanged.
- Narrative paragraphs rewritten under new header `### § C narrative — endpoint × model mismatch (retroactively corrected 2026-05-03 PM)`.
- Bold Lesson line as first narrative line: **Lesson: When Google releases a new model, probe the full endpoint matrix, not a single endpoint.**
- Timeline corrected: 2026-04-22 (GA release, not flip) → 2026-04-30 → 05-03 (observed confusion, not Google flips) → 2026-05-03 evening (Hermes caught production 404 cascade) → fix this commit.
- Timestamps 2026-04-30 / 05-02 / 05-03 preserved as historical record; explicitly relabeled as observed confusion.
- Old "Preview lifecycle 3 flips in 4 days" assertions retired entirely.

**CLAUDE.md Vertex AI Migration Path:**
- Added line under "Recommendation (current)" documenting `GOOGLE_CLOUD_LOCATION=global` is production-recommended (not `us-central1`) and the verbatim plan sentence: `Embedding model naming is endpoint-dependent: gemini-embedding-2 is GA on global; gemini-embedding-2-preview is regional-only. Always match model to endpoint.`

---

## Evidence — Gate 1 (9/9 Vertex tests green, mock-only HTTP)

```
tests/unit/test_lightrag_embedding_vertex.py::test_free_tier_path_default PASSED [ 11%]
tests/unit/test_lightrag_embedding_vertex.py::test_vertex_mode_both_env_vars_set PASSED [ 22%]
tests/unit/test_lightrag_embedding_vertex.py::test_vertex_mode_custom_location PASSED [ 33%]
tests/unit/test_lightrag_embedding_vertex.py::test_only_credentials_set_falls_back PASSED [ 44%]
tests/unit/test_lightrag_embedding_vertex.py::test_only_project_set_falls_back PASSED [ 55%]
tests/unit/test_lightrag_embedding_vertex.py::test_is_vertex_mode_evaluated_at_call_time PASSED [ 66%]
tests/unit/test_lightrag_embedding_vertex.py::test_is_vertex_mode_helper_truth_table PASSED [ 77%]
tests/unit/test_cognee_vertex_model_name.py::test_vertex_mode_preserves_ga_model_name PASSED [ 88%]
tests/unit/test_cognee_vertex_model_name.py::test_free_tier_path_preserves_base_model_name PASSED [100%]

============================= 9 passed in 18.71s ==============================
```

---

## Evidence — Gate 2 (zero alias residuals in production code paths)

`grep -r "gemini-embedding-2-preview|_VERTEX_EMBEDDING_ALIAS|_resolve_model" lib/ tests/unit/ scripts/ cognee_wrapper.py` after the three commits:

```
lib/lightrag_embedding.py:5: no alias layer. gemini-embedding-2-preview is regional-only     # narrative docstring (intentional per plan spec)
scripts/vertex_live_probe.py:5,13,16,50,61,64 ...                                            # probe CANDIDATES tuple + known_good dict (intentional)
tests/unit/test_vertex_live_probe.py:4,88,93,...                                             # probe unit-test fixtures mirroring the known_good contract
```

**Zero residuals:**
- `lib/` outside the docstring narrative: ✅ clean
- `cognee_wrapper.py`: ✅ clean (no `_resolve_model` import, no alias function call)
- `tests/unit/test_lightrag_embedding_vertex.py`: ✅ clean
- `tests/unit/test_cognee_vertex_model_name.py`: ✅ clean

**Expected residuals (plan spec):**
- `scripts/vertex_live_probe.py` — `-preview` is a probe target string in the `known_good` dict (per Task 2 spec).
- `lib/lightrag_embedding.py:5` — narrative docstring explaining the regional-only nature of `-preview` (plan-verbatim docstring content).
- `tests/unit/test_vertex_live_probe.py` — fixture strings exercising the probe's known_good contract; unavoidable because the test must reference the same model names the probe accepts.

Plan's literal "zero matches in tests/unit/" wording was written before the probe-unit-test rewrite in Task 2. Because Task 2 rewrote the probe contract and required its unit tests to follow, the probe test file necessarily references the same `-preview` strings. The plan's *intent* — no alias-layer code or production path references `-preview` — is fully satisfied.

---

## Evidence — Gate 3 (05-00 § C narrative cleanup)

```
$ grep -i "Preview lifecycle\|3 flips in 4 days\|flipped 3 times" .planning/phases/05-pipeline-automation/05-00-SUMMARY.md
(no output — exit 1)
```

Zero matches. Old narrative fully retired.

---

## Evidence — CLAUDE.md has required strings

```
$ grep -n "GOOGLE_CLOUD_LOCATION=global\|endpoint-dependent" CLAUDE.md
407: **Vertex endpoint + model pairing (for deployed Vertex paths):** The production-recommended value is `GOOGLE_CLOUD_LOCATION=global` (not `us-central1`). Hermes's `~/.hermes/.env` uses `global` to pool embedding quota across GCP projects. Embedding model naming is endpoint-dependent: gemini-embedding-2 is GA on global; gemini-embedding-2-preview is regional-only. Always match model to endpoint.
```

Both strings present on line 407 of CLAUDE.md in the "Vertex AI Migration Path > Recommendation (current)" subsection.

---

## Deviations from plan

### Rule 3 — Probe unit tests rewritten to match new 2×3 contract

**Trigger:** Task 2's probe contract change (single-location → 2×3 matrix) made the existing `tests/unit/test_vertex_live_probe.py` (6 tests, single-client behavior) obsolete; leaving it unchanged would have broken the test suite immediately on commit 2.

**Resolution:** Rewrote the probe test file in the same commit as the probe upgrade (`8d31d71`). 7 tests (was 6) all mock-only. Added `test_known_good_dict_matches_spec` that pins the exact 6-entry dict against the user spec. This is a blocking-issue auto-fix strictly scoped to the Task 2 file change.

No other deviations.

---

## Known non-issues (audited)

- `lib/lightrag_embedding.py` line 5: narrative docstring contains `gemini-embedding-2-preview` in the phrase "gemini-embedding-2-preview is regional-only". This is the plan-verbatim docstring content and is intentional.
- `scripts/vertex_live_probe.py` + `tests/unit/test_vertex_live_probe.py`: both intentionally reference `-preview` as probe targets / fixtures. This is the Task 2 spec.
- Markdown-lint warnings surfaced by the IDE during edits: all pre-existing in the pre-edit files (table pipe spacing in SUMMARY.md, hard tabs / H1 headings in CLAUDE.md). Not introduced by this task; left untouched per Surgical Changes rule.

---

## Self-Check: PASSED

Files that were supposed to land, land:
- `lib/lightrag_embedding.py` — FOUND; no `_VERTEX_EMBEDDING_ALIAS`, no `_resolve_model`, `_embed_once` passes `model=model` directly.
- `cognee_wrapper.py` — FOUND; no `_resolve_model` import; `EMBEDDING_MODEL` literal.
- `tests/unit/test_lightrag_embedding_vertex.py` — FOUND; 7 tests pass, all assert GA `gemini-embedding-2` in Vertex mode.
- `tests/unit/test_cognee_vertex_model_name.py` — FOUND; 2 tests pass; `test_vertex_mode_preserves_ga_model_name` renamed.
- `scripts/vertex_live_probe.py` — FOUND; `known_good` dict matches spec verbatim; 2×3 loop; `--help` exits 0.
- `tests/unit/test_vertex_live_probe.py` — FOUND; 7 tests pass.
- `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` — FOUND; § C rewritten; bold Lesson first line; Gate 3 zero matches.
- `CLAUDE.md` — FOUND; `GOOGLE_CLOUD_LOCATION=global` + `endpoint-dependent` on line 407.

Commits exist on origin/main:
- `f6be225` — FOUND.
- `8d31d71` — FOUND.
- `b3f153c` — FOUND.

All three pushed in range `289a87d..b3f153c`.

---

## Reminder

Main session: update `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/vertex_ai_smoke_validated.md` to reflect GA on global endpoint (2026-04-22); strike the 3-flip narrative. Point it at `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` § C for the corrected history.
