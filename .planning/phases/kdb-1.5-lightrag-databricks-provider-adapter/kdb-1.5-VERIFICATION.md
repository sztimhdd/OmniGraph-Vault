---
artifact: VERIFICATION
phase: kdb-1.5
created: 2026-05-16
status: in-progress
---

# Phase kdb-1.5 — Verification

> Authored during Plan 01 (storage adapter). Plan 02 (factory + dry-run e2e) appends its own evidence section after landing.

## Phase kdb-1.5 ROADMAP success criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `databricks-deploy/startup_adapter.py` implements copy-on-startup pattern, idempotent across restarts | ✅ Plan 01 (this PLAN) |
| 2 | `databricks-deploy/lightrag_databricks_provider.py` instantiated against MosaicAI in dry-run e2e (5 articles, ainsert + aquery, embedding_dim=1024 verified) | ✅ Plan 02 |
| 3 | Adapter integration documented in `kdb-1.5-VERIFICATION.md` | ✅ This file |
| 4 | `app.yaml` updated to invoke storage adapter via wrapper shell or pre-uvicorn step | ⚠️ **Intentionally deferred to kdb-2 DEPLOY-DBX-04 (ROADMAP line 99)**. Rationale: kdb-2 owns `app.yaml` end-to-end; splitting authoring across phases risks merge-drift. Adapter MODULE shipped here; wiring is a 1-line `command:` invocation kdb-2 first-deploy adds alongside the 4 required literal env vars (`OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` + 3 LLM vars per LLM-DBX-05). |

## Plan 01 evidence (storage adapter)

- File: `databricks-deploy/startup_adapter.py` — implements `hydrate_lightrag_storage_from_volume() -> CopyResult` with FUSE primary + SDK fallback + idempotency + empty-source skip + /tmp-not-writable defensive raise
- Tests: `databricks-deploy/tests/test_startup_adapter.py` — 5 unit tests, all green
- Adjunct files: `databricks-deploy/CONFIG-EXEMPTIONS.md` (initial-empty ledger; populated in kdb-2), `databricks-deploy/requirements.txt` (databricks-sdk + lightrag-hku pins)

```bash
$ pytest databricks-deploy/tests/test_startup_adapter.py -v
=========================== 5 passed in 0.07s ===========================
```

## Plan 02 evidence (factory + dry-run e2e)

_Pending — added when Plan 02 lands._
