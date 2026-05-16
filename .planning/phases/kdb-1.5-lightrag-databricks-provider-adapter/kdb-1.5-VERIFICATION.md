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

- File: `databricks-deploy/lightrag_databricks_provider.py` — implements `make_llm_func()` + `make_embedding_func()` factories wrapping MosaicAI Model Serving (`databricks-claude-sonnet-4-6` LLM + `databricks-qwen3-embedding-0-6b` dim=1024). Lazy SDK import + `loop.run_in_executor` async wrap (Pitfall 4) + `@wrap_embedding_func_with_attrs` single-wrap (Pitfall 5)
- Tests: `databricks-deploy/tests/test_provider_dryrun.py` — 4 dry-run tests against REAL MosaicAI Model Serving; all green
- Adjunct files: `databricks-deploy/pytest.ini` (dryrun marker), `databricks-deploy/tests/fixtures/article_*.txt` (5 short bilingual fixtures), `databricks-deploy/requirements.txt` updated with pytest + pytest-asyncio test deps

```bash
$ DATABRICKS_CONFIG_PROFILE=dev REQUESTS_CA_BUNDLE=<combined-ca> SSL_CERT_FILE=<combined-ca> PYTHONIOENCODING=utf-8 \
  pytest databricks-deploy/tests/test_provider_dryrun.py -v -m dryrun --tb=short -s
======================== 4 passed in 156.54s (0:02:36) ========================

$ pytest databricks-deploy/tests/ -v -m "" --tb=short
======================== 9 passed in 153.15s (0:02:33) ========================
```

**Dry-run measurements:** Test 1 LLM smoke 1.72s; Test 2 embedding smoke 1.00s (shape (1, 1024) float32); Test 3 e2e roundtrip 143.06s (132.90s ingest + 10.17s query) with structured markdown response identifying all 3 frameworks + dim=1024 verified in vdb_chunks.json; Test 4 bilingual ZH 3.33s + EN 2.75s (Test 4 hit cross-test dedup but plan acceptance `len > 50` met). Total cost < $0.10 (well under $0.20-$0.80 budget).

**Risk #2 (SDK shape mismatch):** RESOLVED. `databricks-sdk==0.108.0` `ServingEndpointsAPI.query()` accepts `input: Optional[Any] = None` directly. No fallback to OpenAI-compat shape needed.

**Risk #3 (Qwen3-0.6B bilingual quality):** PASS at small-corpus scale. Test 3's English query response correctly synthesized information across the bilingual (2 zh + 3 en) corpus. No `NEEDS-INVESTIGATION` escalation for kdb-2.5; recommend confirming on a larger corpus during kdb-2.5 small-batch validation.

Full SUMMARY: [`kdb-1.5-02-SUMMARY.md`](./kdb-1.5-02-SUMMARY.md)
