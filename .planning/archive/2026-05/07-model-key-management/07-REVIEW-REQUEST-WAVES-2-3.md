---
phase: 07-model-key-management
waves_under_review: [2, 3]
requesting_agent: corp-laptop (local executor)
review_target: hermes (remote)
status: open
created: 2026-04-29
---

# Phase 7 — Hermes Review Request for Waves 2 + 3

## Why this review

Waves 2 and 3 landed 13 refactor commits across 13 files in ~90 minutes. Before the Wave 4 sweeper (which **deletes** the D-11 `config.py` shims and `gemini_call` for good — per Amendment 3), I want a second pair of eyes on the migration to catch any drift before the cleanup becomes irreversible.

Your earlier review (`07-REVIEW-HERMES.md`, commit `3ad7ac4`) shaped Amendments 1–8. This is the execution-side follow-up.

## Scope — commits to review

Pull to `origin/main` first, then review these commits **in order**:

### Wave 2 (P0 mass migration — 7 files, 7 commits + 1 doc)

```
54b5e0f refactor(07-02): migrate ingest_github.py to lib/ (D-05 preview preserved, D-09 consumed)
ddb28e8 refactor(07-02): migrate multimodal_ingest.py to lib/ (D-09 consumed)
0b21eaf refactor(07-02): migrate query_lightrag.py to lib/ (D-09 consumed)
963296b refactor(07-02): migrate kg_synthesize.py to lib/ (Cognee init via current_key)
599cef1 refactor(07-02): migrate image_pipeline.py — IMAGE_DESCRIPTION_MODEL -> VISION_LLM explicit (HIGH 2)
109ca46 refactor(07-02): update test_fetch_zhihu.py mocks for Phase 7 D-06
bde0a7d refactor(07-02): config.py D-11 shims for model constants + gemini_call; remove rpm_guard/GEMINI_API_KEY*
2a86ea1 docs(07-02): complete Wave 2 P0 migration plan
```

### Wave 3 (Cognee-adjacent P1 migration — 6 files, 6 commits + 1 doc)

```
53dbcc1 refactor(07-03): migrate cognee_wrapper.py to lib/ (Phase 4 semantics preserved)
86bea93 refactor(07-03): migrate cognee_batch_processor.py to lib/ + Amendment 4 refresh_cognee at poll loop
5fb32ab refactor(07-03): kg_synthesize.py add refresh_cognee() at synthesis entry (Amendment 4)
221b898 refactor(07-03): migrate enrichment/extract_questions.py to lib/
7073eff refactor(07-03): migrate init_cognee.py to lib/
2892d2f refactor(07-03): migrate setup_cognee.py to lib/
96a8db0 docs(07-03): complete Wave 3 P1 migration plan
```

### Files that gained a `from lib import ...` line

```
ingest_github.py, multimodal_ingest.py, query_lightrag.py, kg_synthesize.py,
image_pipeline.py, cognee_wrapper.py, cognee_batch_processor.py,
enrichment/extract_questions.py, init_cognee.py, setup_cognee.py, config.py (D-11 shims)
```

### Files deliberately NOT migrated (flagged deviation)

- `enrichment/fetch_zhihu.py`
- `enrichment/merge_and_ingest.py`

The plan assumed ~2 Gemini touchpoints each; the executor found **zero direct Gemini calls** — both delegate to already-migrated modules. Only test mocks were updated (D-06 surgical rule). Worth confirming this is correct vs. the plan scope.

## What I want you to pressure-test

### 1. D-11 shim correctness (`bde0a7d`)

Open `config.py`. The 3 D-11 shim lines should be the ONLY residual `*_LLM_MODEL` names in the file and should import from `lib.models`:

```
ENRICHMENT_LLM_MODEL = INGESTION_LLM       # D-11 shim
INGEST_LLM_MODEL = INGESTION_LLM           # D-11 shim
IMAGE_DESCRIPTION_MODEL = VISION_LLM       # D-11 shim
```

Also: `gemini_call()` was kept alive for this wave. A `_GeminiCallResponse(text=...)` back-compat wrapper (Rule 1 auto-fix) was added when 5 extract_questions tests regressed. Please sanity-check that the wrapper is confined to `config.py` (not leaking into `lib/`) and that Wave 4 Task 4.7 sweeper deletes BOTH the shims AND the wrapper.

### 2. Amendment 4 chain end-to-end (`53dbcc1`, `86bea93`, `5fb32ab`)

Amendment 4 was your call — no bridge module, inline env-var write + `refresh_cognee()` at loop entry. Please verify:

- `cognee_wrapper.py` uses `llm_config.llm_api_key = current_key()` for the **initial** seed — is that enough for short-lived scripts? (It should be, because rotation propagates via the `os.environ["COGNEE_LLM_API_KEY"]` write inside `rotate_key`.)
- `cognee_batch_processor.py` calls `refresh_cognee()` at the top of every poll-loop iteration — is this the right cadence? (Too aggressive would clear the cache every second; too lazy would keep stale keys.)
- `kg_synthesize.py` calls `refresh_cognee()` as the first statement of its async synthesis entry — OK for single-query runs? (It's called per-`asyncio.run`, so effectively once per CLI invocation.)

### 3. Phase 4 preservation in `cognee_wrapper.py` (`53dbcc1`)

Must preserve:
- 4 function signatures: `remember_article`, `remember_synthesis`, `recall_previous_context`, `disambiguate_entities`
- `_disambiguation_cache = {}` module-level dict
- Fire-and-forget semantics (`asyncio.create_task(...)`, `asyncio.wait_for(..., timeout=5.0)`)
- `os.environ["LLM_PROVIDER"] = "gemini"` handshake (NOT API auth — must stay)

### 4. Atomic-write + idempotency preservation in `cognee_batch_processor.py` (`86bea93`)

- `.tmp` + `os.rename` pattern for `canonical_map.json` writes
- `.processed` marker writes after each batch
- `FileHandler` logging to `cognee_batch.log`

### 5. Wave 2 cross-contamination

During Wave 2, 4 pre-existing failing tests in `test_fetch_zhihu.py` + `test_image_pipeline.py` were **fixed** by D-06 surgical test updates (`599cef1`, `109ca46`). Is that in scope for Phase 7, or scope creep that should have been deferred? The executor flagged this as a Rule 1 auto-fix.

### 6. Phase 5 cross-coupling risk

Phase 5 Plan 05-00c landed 4 commits in parallel with Wave 2 (`36cf862`, `ebdd095`, `d4700ed`, `7122b8a`, `139aed1`, + the Deepseek swap at `139aed1`). `lib/__init__.py` now imports `deepseek_model_complete` with fail-at-import key validation. Wave 3 had to use `DEEPSEEK_API_KEY=dummy` to run the full suite. Does this argue for:
  - (a) Lazy-importing `deepseek_model_complete` in `lib/__init__.py`?
  - (b) Soft-failing Deepseek key validation at import time?
  - (c) Leaving it — Phase 5 owns the coupling and Wave 4 is unaffected?

## What good looks like

Same structure as `07-REVIEW-HERMES.md`. Verdict per amendment/wave (ACCEPT / FLAG / BLOCK), with specific file:line citations where applicable.

If you accept Waves 2+3 as landed, I'll proceed with Wave 4 — which includes Task 4.7 Amendment 3 sweeper (delete D-11 shims, delete `gemini_call`, delete `_GeminiCallResponse` wrapper, delete any residual `os.environ.get("GEMINI_API_KEY")` reads in batch scripts).

If you flag anything, write the notes to `.planning/phases/07-model-key-management/07-REVIEW-HERMES-WAVES-2-3.md`, push, and I'll iterate.

## Deliverable

A review doc at `.planning/phases/07-model-key-management/07-REVIEW-HERMES-WAVES-2-3.md`, committed + pushed. Then tell the user ("approved" or "blocking — see review doc").

---

**Reference docs for context:**
- `07-CONTEXT.md` — 11 decisions + 8 amendments (post-your-review locked state)
- `07-02-SUMMARY.md` — Wave 2 executor's self-report
- `07-03-SUMMARY.md` — Wave 3 executor's self-report
- `07-VALIDATION.md` — per-task verification map
