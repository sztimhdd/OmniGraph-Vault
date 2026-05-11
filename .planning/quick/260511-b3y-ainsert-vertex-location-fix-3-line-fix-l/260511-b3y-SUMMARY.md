---
phase: quick-260511-b3y
plan: 01
subsystem: lib/lightrag_embedding
tags: [vertex-ai, embedding, location-fix, quick]
key-files:
  modified:
    - lib/lightrag_embedding.py
    - tests/unit/test_lightrag_embedding_vertex.py
    - scripts/local_e2e.sh
decisions:
  - "Default GOOGLE_CLOUD_LOCATION to 'global' in _make_client(); aligns with all other Vertex clients in repo"
  - "Update test assertion to lock in correct default (was documenting buggy us-central1)"
  - "Add defensive export to local_e2e.sh harness so it works without operator pre-setting the var"
metrics:
  completed: "2026-05-11"
  tasks: 3
  files_modified: 3
---

# Quick 260511-b3y: Vertex Embedding Location Fix — SUMMARY

**One-liner:** Fixed `_make_client()` default from `us-central1` to `global` so `gemini-embedding-2` resolves correctly; ainsert now writes `status=processed` instead of `status=failed`.

---

## What Was Done

Root cause confirmed in `DEBUG.md` (Hypothesis F, evidence E-01 through E-06): `lib/lightrag_embedding.py:141` defaulted `GOOGLE_CLOUD_LOCATION` to `"us-central1"`, but `gemini-embedding-2` is only available on Vertex's `global` endpoint. The 404 was caught by LightRAG which wrote `DocStatus.FAILED`, and `_verify_doc_processed_or_raise` raised a RuntimeError after 30 retries.

Three deterministic changes applied:

### Change 1 — `lib/lightrag_embedding.py`

- `_make_client()` line 141: `"us-central1"` → `"global"`
- Docstring lines 134-135: updated to say `Location defaults to ``global`` when ... (gemini-embedding-2 GA endpoint).`
- Net: 2 lines changed (1 code + 1 docstring)

### Change 2 — `tests/unit/test_lightrag_embedding_vertex.py`

- Line 142: `assert ckw.get("location") == "us-central1"` → `== "global"` (with updated inline comment)
- Line 129 docstring: updated to reference `location='global'`
- Net: 2 lines changed (test assertion + docstring)

### Change 3 — `scripts/local_e2e.sh`

- Header comment block (line 31): added `GOOGLE_CLOUD_LOCATION` entry documenting the global default and referencing the debug dir
- Export section (line 86): added `export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"` after `OMNIGRAPH_BASE_DIR`
- Net: 4 lines added (3 comment + 1 export)

---

## Verification Evidence

### Unit tests

```
PYTHONIOENCODING=utf-8 venv/Scripts/python -m pytest tests/unit/test_lightrag_embedding_vertex.py -v --no-header

7 passed in 2.91s
```

All 7 tests pass including `test_vertex_mode_both_env_vars_set` which now asserts `location == "global"`.

### E2E wechat smoke

Command:
```bash
GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8 PYTHONIOENCODING=utf-8 \
  bash scripts/local_e2e.sh wechat "https://simonwillison.net/2026/May/6/vibe-coding-and-agentic-engineering/"
```

Log file: `.scratch/local-e2e-wechat-20260511-080610.log`

Exit code: **0** (`[local-e2e] EXIT=0  log=.scratch/local-e2e-wechat-20260511-080610.log`)

Terminal success line (log end):
```
INFO: Phase 3: Updating final 24(24+0) entities and  24 relations from wechat_590ef2d9d3
INFO: Completed merging: 24 entities, 0 extra entities, 24 relations
INFO: [] Writing graph with 272 nodes, 333 edges
INFO: In memory DB persist to disk
INFO: Completed processing file 1/1: unknown_source
...
✅ Cached article processed (scrape skipped)
[local-e2e] EXIT=0  log=.scratch/local-e2e-wechat-20260511-080610.log
```

### kv_store_doc_status.json

doc_id: `wechat_590ef2d9d3`
status: **`processed`**
error_msg: `(none)`
updated_at: `2026-05-11T11:17:02.193418+00:00`

Previous status (DEBUG.md E-02): `"status": "failed"` with `error_msg: "404 NOT_FOUND. Publisher Model .../locations/us-central1/publishers/google/models/gemini-embedding-2 was not found..."`

### No 404 in smoke log

The previous failure signal `ERROR: Embedding func: Error in decorated function for task ...: 404 NOT_FOUND` does not appear anywhere in `.scratch/local-e2e-wechat-20260511-080610.log`. The embedding calls instead show Vertex SDK INFO messages confirming project/location override — no errors.

---

## Commit

Single atomic commit covering all three file changes:

`b1e7fc8` — `fix(quick-260511-b3y): default Vertex embedding location to global (gemini-embedding-2 GA endpoint)`

---

## Deviations from Plan

None — plan executed exactly as written. The test docstring at line 129 was also updated (in addition to line 142 assertion) to avoid misleading documentation, which falls within the "same logical edit" scope described in the plan.

---

## Hermes Deploy Note

Per `CLAUDE.md:520`, Hermes's `~/.hermes/.env` already contains `GOOGLE_CLOUD_LOCATION=global`. If that is correct, Hermes was NOT affected by this bug — the fix makes local dev and the harness consistent with Hermes production. Verify before next cron fires:

```bash
ssh -p <port> <user>@<host> "grep GOOGLE_CLOUD_LOCATION ~/.hermes/.env"
```

Expected output: `GOOGLE_CLOUD_LOCATION=global`

If absent: add `GOOGLE_CLOUD_LOCATION=global` to `~/.hermes/.env` via operator side-channel (do not commit).

---

## Self-Check: PASSED

- `lib/lightrag_embedding.py` modified: confirmed (line 141 default = `"global"`)
- `tests/unit/test_lightrag_embedding_vertex.py` modified: confirmed (line 142 = `== "global"`)
- `scripts/local_e2e.sh` modified: confirmed (line 86 export present)
- Commit `b1e7fc8` exists: confirmed via `git log --oneline -1`
- Unit tests: 7/7 passed
- Smoke log EXIT=0: confirmed
- `kv_store_doc_status.json` status=processed: confirmed
