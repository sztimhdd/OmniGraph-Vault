---
phase_id: quick-260509-t4i
description: Write LightRAG ainsert persistence contract regression tests
status: complete
type: quick
mode: quick
created: 2026-05-09
completed: 2026-05-09
---

# Quick Task 260509-t4i — Summary

## Outcome

- **T1** `test_t1_single_doc_persists_status_processed` — **PASSED** (mock LLM/embed)
- **T2** `test_t2_sequential_seven_docs_no_state_leak` — **PASSED** (mock LLM/embed, 7 sequential)
- **T3** `test_t3_real_vertex_gemini_single_doc` — **SKIPPED** (default skipif on `.dev-runtime/gcp-paid-sa.json` + `GOOGLE_CLOUD_PROJECT`)

**Local result:** T1=PASSED, T2=PASSED — bug does NOT reproduce locally with
mocked LLM + zero-vector embed. Production-shape contract holds at the mock
boundary. Suggests the 41-vs-15 production divergence lives in the real
LLM / network / Vertex-stack surface, NOT in LightRAG's single-doc or
sequential-flush path itself.

**Log path:** `.scratch/ainsert-contract-fast-20260510T000741Z.log`
(2 passed, 1 skipped, 3 warnings in 2.43s — exit code 0).

## What Was Built

- **File:** `tests/unit/test_ainsert_persistence_contract.py` (229 lines, single file)
- **Contract asserted (3 tiers):**
  > `await rag.ainsert(content, ids=[doc_id])` returns ⇒ `doc_id` MUST appear
  > in `kv_store_doc_status.json` with `status="processed"`.
  Asserted by reading the persisted JSON file directly off disk via
  `_assert_doc_status_processed(tmp_path, doc_id)` — the bug surface is
  the filesystem, not the LightRAG API.
- **Mock LLM:** returns just the LightRAG completion delimiter `<|COMPLETE|>`
  (verified against `lightrag-hku==1.4.15`,
  `lightrag/operate.py:_process_extraction_result`).
- **Mock embed:** wrapped in `EmbeddingFunc(embedding_dim=3072, func=...)`
  to match `gemini-embedding-2` production dim (CLAUDE.md).
- **T3 import strategy:** `pytest.importorskip("lib.vertex_gemini_complete")`
  + `getattr(...)` to discover `vertex_gemini_model_complete` and
  `embedding_func` (the real public name in `lib.lightrag_embedding`,
  not `gemini_embed` as the plan suggested).
- **Slow marker:** `@pytest.mark.slow` emits one expected
  `PytestUnknownMarkWarning` (marker not registered in
  `pyproject.toml` — by design; do not modify config).

### One deviation from plan APPENDIX A

The plan listed `await rag.ainsert(content=content, ids=[doc_id])` as
keyword-arg form. The actual `lightrag-hku==1.4.15` signature is
`ainsert(input, split_by_character=None, ..., ids=None, ...)` — first
positional param is `input`, NOT `content`. First test run failed at
collection for both T1+T2 with `TypeError: LightRAG.ainsert() got an
unexpected keyword argument 'content'`. Corrected to positional form
`rag.ainsert(content, ids=[doc_id])` (matches production usage in
`scripts/wave0c_smoke.py:83`). This is API-contract fidelity, not test
coercion — anti-fabrication rule satisfied (the contract under test
requires a working API call). Captured in test docstring on line 144.

## What Was NOT Touched

Surgical-change verification — the only files staged are:

- `tests/unit/test_ainsert_persistence_contract.py` (new)
- `.planning/quick/260509-t4i-write-lightrag-ainsert-persistence-contr/260509-t4i-PLAN.md`
- `.planning/quick/260509-t4i-write-lightrag-ainsert-persistence-contr/260509-t4i-SUMMARY.md`

NOT touched (verified explicitly):

- `lib/` — no source changes
- `ingest_wechat.py`, `batch_ingest_from_spider.py` — no source changes
- Any other test under `tests/unit/` — no edits
- `requirements.txt`, `pyproject.toml`, `pytest.ini` — no config changes
- `.gitignore`, `conftest.py` — untouched (`.scratch/` already gitignored)
- No SSH to Hermes, no remote push, no cron change

## STOP Gate

This quick task is **regression-isolation only**. The 26 silent contract
violations in 2026-05-09 ADT production
(ingestions=41 OK wechat / kv_store_doc_status=15 unique processed;
graphml mtime frozen at 18:41 ADT) are NOT fixed by this commit.

T3 (real Vertex Gemini, gated by `@pytest.mark.slow` + skipif) was NOT
run per plan constraints — it's the next investigative step and belongs
in a follow-up quick.

The actual source-code fix is deferred to a future quick task once T3
results identify whether the divergence is in:

- the Vertex Gemini LLM call surface
- the embedding flush path (`lib.lightrag_embedding.embedding_func`)
- a state-leak only visible under real network latency
- something else entirely

**No source code changed.** Bug fix deferred.
