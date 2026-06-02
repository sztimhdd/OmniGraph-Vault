# Ainsert Async Pipeline Race — Debug Report

## Bug summary

**Title:** LightRAG `ainsert()` always writes `DocStatus.FAILED` when Vertex AI embedding mode is active.

**Repro frequency:** 100% — every article ingest attempt since the Vertex AI embedding path became active.

**Impact scope:** Every `ingest_wechat.py` / `batch_ingest_from_spider.py` run that uses Vertex AI embedding (`GOOGLE_APPLICATION_CREDENTIALS` set, `GOOGLE_CLOUD_PROJECT` set). Hermes production cron has `~/.hermes/.env` with `GOOGLE_CLOUD_LOCATION=global`, so Hermes is not affected. Local dev and the local_e2e harness are affected because `local_e2e.sh` does not set `GOOGLE_CLOUD_LOCATION`, so the embedding client defaults to `us-central1`.

**Note on bug name:** The bug was labelled "ainsert async race" based on initial hypothesis. Investigation reveals it is NOT a race condition. It is a **wrong Vertex AI location for the embedding client**. The `PROCESSED` verification never times out waiting — it consistently sees `FAILED` because LightRAG's `process_document` pipeline caught a real 404 API error and wrote `status=FAILED` before `ainsert()` returned to the caller.

---

## Reproduction

```bash
cd c:/Users/huxxha/Desktop/OmniGraph-Vault
GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8 \
PYTHONIOENCODING=utf-8 \
bash scripts/local_e2e.sh wechat "https://simonwillison.net/2026/May/6/vibe-coding-and-agentic-engineering/"
```

**Expected:** `--- Successfully Ingested! ---` with no RuntimeError.
**Actual:** `RuntimeError: post-ainsert PROCESSED verification failed for doc_id=wechat_590ef2d9d3 after 30 retries (backoff 2.0s). Last status=<DocStatus.FAILED: 'failed'>, last_exc=None.`

**Log file:** `.scratch/local-e2e-wechat-20260510-210647.log`

---

## Evidence chain

### E-01 — 404 NOT_FOUND in primary failure log

`.scratch/local-e2e-wechat-20260510-210647.log:36`:

```
ERROR: Embedding func: Error in decorated function for task ...: 404 NOT_FOUND.
{'error': {'code': 404, 'message': 'Publisher Model
`projects/project-df08084f-6db8-4f04-be8/locations/us-central1/publishers/google/models/gemini-embedding-2`
was not found or your project does not have access to it.'}}
```

**The Vertex AI client is calling `us-central1`, but `gemini-embedding-2` is only
available on the `global` endpoint.** This is a deterministic 404, not an async race.

### E-02 — LightRAG status KV store confirms FAILED with the 404 error message

`.dev-runtime/lightrag_storage/kv_store_doc_status.json:153-171` (written 2026-05-11T00:07:54):

```json
"wechat_590ef2d9d3": {
    "status": "failed",
    "error_msg": "404 NOT_FOUND. {'error': {'code': 404, 'message': 'Publisher Model
    `projects/project-df08084f-6db8-4f04-be8/locations/us-central1/publishers/google/models/gemini-embedding-2`
    was not found...'}}",
    ...
}
```

LightRAG's `process_document` at `lightrag.py:2100-2121` catches the exception from the
embedding call and writes `DocStatus.FAILED` with the verbatim error_msg — this is what
`_verify_doc_processed_or_raise()` polls and sees.

### E-03 — Default location is `us-central1` in `lib/lightrag_embedding.py`

`lib/lightrag_embedding.py:134-141`:

```python
def _make_client(api_key: str) -> "genai.Client":
    """...Location defaults to ``us-central1`` when
    ``GOOGLE_CLOUD_LOCATION`` is unset.
    """
    if _is_vertex_mode():
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),  # <-- BUG
        )
```

### E-04 — `gemini-embedding-2` requires the `global` endpoint (not `us-central1`)

`CLAUDE.md:520`:
> "The production-recommended value is `GOOGLE_CLOUD_LOCATION=global` (not `us-central1`).
> Hermes's `~/.hermes/.env` uses `global` to pool embedding quota across GCP projects.
> Embedding model naming is endpoint-dependent: gemini-embedding-2 is GA on global;
> gemini-embedding-2-preview is regional-only."

`lib/lightrag_embedding.py:4-7` (module docstring):
> "gemini-embedding-2 is GA as of 2026-04-22 on the `global` endpoint. Use the unsuffixed name
> as-is; no alias layer. gemini-embedding-2-preview is regional-only (us-central1 etc.) and
> does not exist on the global endpoint"

### E-05 — `scripts/local_e2e.sh` does NOT set `GOOGLE_CLOUD_LOCATION`

`scripts/local_e2e.sh` (full file): no `GOOGLE_CLOUD_LOCATION` export anywhere.
The comment at line 46 says "gemini-embedding-2 (global) and gemini-3.1-flash-lite-preview
(global) live-probed OK" — but the env var setting that makes this true is missing.

### E-06 — Location inconsistency across modules

| File | Default when `GOOGLE_CLOUD_LOCATION` unset |
|---|---|
| `lib/lightrag_embedding.py:141` | `us-central1` (**WRONG for `gemini-embedding-2`**) |
| `lib/vertex_gemini_complete.py:61,92` | `global` (correct) |
| `image_pipeline.py:327` | `global` (correct) |
| `batch_ingest_from_spider.py:1248` | `global` (correct) |

**Four of five locations default to `global`. Only the embedding client defaults to `us-central1`.**

### E-07 — LightRAG `process_document` catches exception and writes FAILED

`venv/Lib/site-packages/lightrag/lightrag.py:2040,2051-2121`:

```python
await asyncio.gather(*first_stage_tasks)  # line 2040 — chunks_vdb.upsert raises here
# ...
except Exception as e:  # line 2051
    # ...
    await self.doc_status.upsert({  # line 2100
        doc_id: {
            "status": DocStatus.FAILED,
            "error_msg": str(e),
            ...
        }
    })
```

`first_stage_tasks` includes `chunks_vdb_task` (=`chunks_vdb.upsert(chunks)`) at `lightrag.py:2024-2035`.
The chunks VDB upsert calls `embedding_func` which hits the 404. The exception propagates through
`asyncio.gather`, is caught by the outer `except Exception as e`, and LightRAG writes FAILED.
`ainsert()` does NOT re-raise — it returns normally to the caller. This is correct LightRAG behavior
(FAILED is a terminal status for the doc, signaling it needs retry).

### E-08 — Unit test documents the wrong default (test needs correction)

`tests/unit/test_lightrag_embedding_vertex.py:142`:

```python
assert ckw.get("location") == "us-central1"  # default when GOOGLE_CLOUD_LOCATION unset
```

This test asserts the broken default, i.e. it was written to document current behavior, not
correct behavior. It will need updating when the fix is applied.

### E-09 — Layer 1 smoke succeeded in same env (proves Vertex connectivity OK)

`.scratch/local-e2e-layer1-20260510-205132.log`: Layer 1 (uses `lib.article_filter` → Vertex LLM)
completed 5/5 in the same environment. This proves `GOOGLE_APPLICATION_CREDENTIALS`,
`GOOGLE_CLOUD_PROJECT`, and network access to Vertex are all fine. The bug is model-specific,
not credential-level.

### E-10 — Prior cron success before Vertex embedding activation

`kv_store_doc_status.json` contains 7 entries with `status=processed` dated 2026-05-05, all
from a period when Vertex embedding was either not active or using a correct location.
The consistent FAILED pattern only emerged after the Vertex path became the active path.

---

## Hypothesis verdicts

| Hyp | Verdict | Evidence | Notes |
|---|---|---|---|
| **A — Vision worker not drained before ainsert** | **FALSIFIED** | E-01, E-07. The 404 fires inside `chunks_vdb.upsert` during LightRAG's stage-1 pipeline, which runs BEFORE entity extraction and has nothing to do with vision tasks. The stack trace in the log ends at `lightrag/kg/nano_vector_db_impl.py:124 → lightrag/utils.py:747 → lib/lightrag_embedding.py:217` — no vision path involved. | Vision drain is irrelevant to this failure path. |
| **B — Vertex Gemini async concurrency throws silent exception** | **PARTIALLY CONFIRMED (wrong hypothesis, right layer)** | E-01, E-07. An exception IS thrown inside the Vertex embedding call. But it is NOT silent (it propagates fully and LightRAG writes `FAILED` + stores `error_msg` in the KV file). The exception is a deterministic 404, not a timeout/429/socket-reset. `last_exc=None` in the RuntimeError is because `_verify_doc_processed_or_raise` catches no exception from `aget_docs_by_ids` — it just sees FAILED status. | The "silent" description was wrong; the exception IS logged and stored. |
| **C — `lib/lightrag_embedding.py:207` serial loop try/except boundary bug** | **FALSIFIED** | `lib/lightrag_embedding.py:219-224`: `except Exception as exc: if _is_429(exc): ... else: raise`. The code re-raises non-429 errors immediately (`raise` at line 224). A 404 `ClientError` is NOT a 429 (check via `_is_429`), so it propagates immediately out of `embedding_func`. The serial loop error boundary is correct. | The 404 propagates up the full stack as shown in E-01. |
| **D — Vertex embed batch size doesn't match Vertex API limit** | **FALSIFIED** | E-01, E-03. The error is `404 NOT_FOUND` (model not found at this endpoint), not `400 INVALID_ARGUMENT` or `429 RESOURCE_EXHAUSTED`. `embedding_batch_num=64` is irrelevant because the call never succeeds at all — it is rejected at the routing layer before payload validation. | Batch size is not the issue. |
| **E — `260509-p1n` vision drain set misses LightRAG-internal tasks** | **FALSIFIED** | E-01, E-07. The `ainsert` call raises (internally) and writes FAILED before any vision task is created (`url_to_path` is empty for this article: `Found 0 unique potential images` at log:154). The drain set is irrelevant. Even if it were non-empty, the failure is at the embedding call inside stage-1, not at process exit. | No images, no vision tasks. Drain set irrelevant here. |

### New hypothesis F (root cause)

| Hyp | Verdict | Evidence |
|---|---|---|
| **F — `lib/lightrag_embedding.py` defaults to `us-central1` but `gemini-embedding-2` only exists on `global` endpoint** | **CONFIRMED AS ROOT CAUSE** | E-01 through E-06. The Vertex embedding client is constructed with `location="us-central1"` (E-03), but the model `gemini-embedding-2` is only available on the `global` endpoint (E-04). The resulting 404 causes LightRAG to write `DocStatus.FAILED` (E-02, E-07). All other modules in the repo use `global` as the default (E-06). |

---

## Root cause

**File:** `lib/lightrag_embedding.py`, line 141

**Code:**

```python
location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
```

**Why it breaks:** `gemini-embedding-2` (the production embedding model per `lib/models.py:17`) is
only available via the Vertex AI **`global`** endpoint, not regional endpoints like `us-central1`.
When `GOOGLE_CLOUD_LOCATION` is not set in the environment (which is the case for local
`scripts/local_e2e.sh` runs), the client uses `us-central1`, the Vertex API returns
`404 NOT_FOUND`, and LightRAG catches the exception and writes `DocStatus.FAILED`.

**Why `last_exc=None` in the RuntimeError:** `_verify_doc_processed_or_raise` calls
`rag.aget_docs_by_ids([doc_id])` which returns the KV entry (with `status=FAILED`) without
raising. The verifier sees FAILED status and loops. After 30 attempts it raises, but `last_exc`
tracks exceptions from `aget_docs_by_ids` itself — not from the original embedding error.
The actual exception's text is stored in `kv_store_doc_status.json["wechat_590ef2d9d3"]["error_msg"]`.

**Why Hermes production cron fails the same way:** The CLAUDE.md states Hermes's
`~/.hermes/.env` uses `GOOGLE_CLOUD_LOCATION=global`. If this is set correctly, Hermes
would NOT hit the 404. However: if Hermes was recently updated and the env var was removed,
renamed, or not present in the env file, the same 404 would occur there too.

**Timing confirmation:** `kv_store_doc_status.json` shows `created_at=2026-05-11T00:07:52`
and `updated_at=2026-05-11T00:07:54` — only 2 seconds elapsed between doc registration and
FAILED status write. This is consistent with an immediate API rejection (no retries for non-429),
not a timeout scenario.

---

## Proposed fix

### Change site 1 (required): `lib/lightrag_embedding.py:141`

Change the default from `"us-central1"` to `"global"`:

```python
# Before (broken):
location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),

# After (correct):
location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
```

**Justification:** `gemini-embedding-2` is GA on `global`. All other Vertex clients in the repo
(`lib/vertex_gemini_complete.py:61`, `image_pipeline.py:327`, `batch_ingest_from_spider.py:1248`)
already use `global` as their default. This aligns with CLAUDE.md § Vertex endpoint + model
pairing.

### Change site 2 (required): `tests/unit/test_lightrag_embedding_vertex.py:142`

Update the assertion to reflect the corrected default:

```python
# Before:
assert ckw.get("location") == "us-central1"  # default when GOOGLE_CLOUD_LOCATION unset

# After:
assert ckw.get("location") == "global"  # default when GOOGLE_CLOUD_LOCATION unset; gemini-embedding-2 requires global endpoint
```

### Change site 3 (defensive, recommended): `scripts/local_e2e.sh`

Add an explicit export of the correct location near the other Vertex env vars (after line 72):

```bash
# Vertex embedding requires global endpoint — gemini-embedding-2 not available on us-central1.
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
```

This makes the harness self-documenting and resistant to the default being wrong.

### No changes needed

- `ingest_wechat.py` — the ainsert call site and `_verify_doc_processed_or_raise` are
  correct. The 30-retry budget is appropriate for genuinely slow processing. The bug was
  that ainsert was always hitting a terminal 404 error, not that the retry window was too short.
- `lib/vertex_gemini_complete.py` — already uses `global` as default; no change needed.
- LightRAG library code — behaves correctly (writes FAILED + stores error_msg).

### Estimated LOC: 3 lines total (1 in lib, 1 in tests, 1 in harness)

### Risk

**Low.** The `global` endpoint supports `gemini-embedding-2` per official Vertex AI model
documentation and CLAUDE.md. All other Vertex clients in the repo already use `global`.
Hermes production already sets `GOOGLE_CLOUD_LOCATION=global` in `~/.hermes/.env`
(per CLAUDE.md), so production behavior is unchanged by this fix.

**Potential concern:** If a future consumer needs a regional embedding endpoint (e.g., data
residency requirement), they should set `GOOGLE_CLOUD_LOCATION` explicitly — the env var
override still works. The default change only affects callers that don't set it.

---

## Hermes deploy notes

### Before deploying

1. Confirm `GOOGLE_CLOUD_LOCATION=global` is present in Hermes's `~/.hermes/.env`.
   The CLAUDE.md states it IS there, but verify directly:

   ```bash
   grep GOOGLE_CLOUD_LOCATION ~/.hermes/.env
   ```

   If the line is present, Hermes has been shielded from this bug even before the fix ships.
   If the line is ABSENT, Hermes production cron is hitting the exact same 404.

2. If `GOOGLE_CLOUD_LOCATION` is absent from `~/.hermes/.env`, add it immediately
   (before or alongside the code fix):

   ```
   GOOGLE_CLOUD_LOCATION=global
   ```

### After deploying

1. Run the T3 contract test from the local harness:

   ```bash
   PYTHONIOENCODING=utf-8 \
   GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8 \
   venv/Scripts/python -m pytest tests/unit/test_ainsert_persistence_contract.py \
     -v -m slow --no-header -s
   ```

   Expected: T3, T3a, T3b all PASS. T3a should log `post-await: processed`.

2. Run a single-article wechat smoke via the harness:

   ```bash
   PYTHONIOENCODING=utf-8 \
   bash scripts/local_e2e.sh wechat "https://simonwillison.net/2026/May/6/vibe-coding-and-agentic-engineering/"
   ```

   Expected: exits 0, `--- Successfully Ingested! ---`, no RuntimeError.

3. On Hermes: trigger a manual ingest of one article (not the full cron) and verify
   `kv_store_doc_status.json` shows `status=processed` for the new doc_id.

### Regression check

After applying the fix, confirm no existing PASSED status entries in `kv_store_doc_status.json`
have changed. The existing 7 `processed` entries (all from 2026-05-05 with the free-tier path)
should remain intact.

---

## Open questions / unresolved

### Q1 — Why did prior runs (2026-05-05) work?

The 7 `status=processed` entries in `kv_store_doc_status.json` are dated 2026-05-05.
At that time either: (a) `GOOGLE_CLOUD_LOCATION=global` was set in the environment,
(b) Vertex mode was not active (free-tier `GEMINI_API_KEY` path was used instead), or
(c) a different location/model combination was in use. The CLAUDE.md Phase 11 D-11.08
comment suggests the Vertex opt-in was added progressively — prior successful runs may
have predated Vertex mode activation.

### Q2 — Is Hermes production cron actually failing due to this bug?

CLAUDE.md states `~/.hermes/.env` uses `GOOGLE_CLOUD_LOCATION=global`. If that is true,
Hermes should NOT hit the 404 and should produce `status=processed`. The "0 OK ingests"
symptom reported in the bug description may be caused by a DIFFERENT issue on Hermes
(possibly the LLM provider is DeepSeek on Hermes, which is corp-blocked locally, or
another Hermes-specific config difference). A direct `grep GOOGLE_CLOUD_LOCATION ~/.hermes/.env`
on the Hermes box is needed to confirm.

### Q3 — T3 test with `GOOGLE_CLOUD_LOCATION=global` should be run to confirm fix

The T3/T3a/T3b tests in `tests/unit/test_ainsert_persistence_contract.py` are guarded
by `@pytest.mark.slow` and the SA + project env vars. They should be run with the fix
applied to confirm that `post_await_status == 'processed'` with real Vertex embedding.

### Q4 — The `lib/llm_client.py:51` also defaults to `us-central1`

`lib/llm_client.py:51` (not in the primary search scope) also appears to default to
`us-central1`. If any code path uses this client for embedding (not LLM), it would
hit the same bug. This file should be audited in a follow-up quick.

### Q5 — Is the h09b PROCESSED_VERIFY retry budget still needed?

After this fix, `ainsert()` should succeed and write `status=processed` before returning.
The 30-retry, 60s budget added in quick `260510-h09b` becomes a long-tail safety net
rather than the primary mechanism. It should remain (genuine slow-processing cases exist
for large articles), but the nominal case should resolve on attempt 1 after the fix.
