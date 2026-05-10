# LightRAG ainsert Pipeline Investigation — quick 260510-gqu

**Date:** 2026-05-10
**SDK:** lightrag 1.4.15 (`venv/Lib/site-packages/lightrag/lightrag.py`)
**Scope:** investigation only — zero production-code changes
**Parallel quicks:** 260510-gkw (T3 spike, untouched), 260510-gfg (Cognee retire, untouched), 260509-t4i (T1+T2 contract test, locked)
**Evidence:**
- Source-trace dump → `.scratch/lightrag-ainsert-trace-20260510T120848.md`
- Mock timing run → `.scratch/lightrag-pipeline-mock-timing-20260510T1207.log`
- Diagnostic scripts → `scripts/lightrag_diag/probe_ainsert_timing.py`, `scripts/lightrag_diag/dump_ainsert_source_trace.py`

---

## TL;DR

1. **`await rag.ainsert(content, ids=[doc_id])` does NOT guarantee `doc_status[doc_id].status == DocStatus.PROCESSED` on return.** When another `ainsert` call is concurrently in flight, the second call sees `pipeline_status["busy"] = True`, sets `request_pending = True`, and **returns immediately at `lightrag.py:1796-1800`** without ever processing the doc itself. The doc transitions are: `apipeline_enqueue_documents` writes `PENDING` (`:1436`) → ainsert returns. The first ainsert's pipeline is responsible for picking up the second doc via the `request_pending` flag — a fragile chain that production breaks under cancellation / process exit.

2. **Production smoking gun reproduced offline.** `probe_ainsert_timing.py` Scenario 4 fires two concurrent ainserts; second returns in 4 ms with `docB.status='pending'`; first task is then cancelled (mimicking `_drain_pending_vision_tasks` timeout); final state `docA='processing' docB='pending'` — bit-identical to prod observation (4/4 docs stuck pending/processing, 0 processed).

3. **Recommended fix (5–10 LOC at one site):** after every `await rag.ainsert(content, ids=[doc_id])` in production code that gates `ingestions.status='ok'`, **poll `rag.doc_status.get_by_id(doc_id)` until `status==PROCESSED` (success), `FAILED` (failure), or wall-clock budget elapsed (timeout → mark failed, do NOT mark ok).** The SDK exposes everything needed (`doc_status.get_by_id`, the `DocStatus` enum); no wait/drain helper exists in 1.4.15 to do this for us.

---

## 1. ainsert call chain — verbatim source + line cites

All citations are from `venv/Lib/site-packages/lightrag/lightrag.py` (lightrag 1.4.15). Verbatim dumps in `.scratch/lightrag-ainsert-trace-20260510T120848.md`; condensed inline below.

### 1.1 `LightRAG.ainsert` — `:1237-1270`

```python
async def ainsert(
    self,
    input: str | list[str],
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
    track_id: str | None = None,
) -> str:
    """Async Insert documents with checkpoint support
    ...
    Returns:
        str: tracking ID for monitoring processing status
    """
    if track_id is None:
        track_id = generate_track_id("insert")
    await self.apipeline_enqueue_documents(input, ids, file_paths, track_id)
    await self.apipeline_process_enqueue_documents(
        split_by_character, split_by_character_only
    )
    return track_id
```

`ainsert` is a thin two-step shim: enqueue, then process. The method **awaits both** sequentially, so a single sequential caller does experience end-to-end synchronous semantics. The bug is what `apipeline_process_enqueue_documents` does when it sees an already-busy pipeline.

### 1.2 `LightRAG.apipeline_enqueue_documents` — `:1344-1509` (excerpt)

`:1394-1431` builds the `contents: dict[doc_id, {content, file_path}]` dict.
`:1433-1447` writes the initial doc record:

```python
# 2. Generate document initial status (without content)
new_docs: dict[str, Any] = {
    id_: {
        "status": DocStatus.PENDING,           # :1436 — first state write
        "content_summary": get_content_summary(content_data["content"]),
        "content_length": len(content_data["content"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "file_path": content_data["file_path"],
        "track_id": track_id,
    }
    for id_, content_data in contents.items()
}
```

`:1449-1506` filters duplicates (creates a separate `dup-…` record with `status=DocStatus.FAILED` at `:1477` for already-enqueued docs — orthogonal to the bug).

### 1.3 `LightRAG.apipeline_process_enqueue_documents` — `:1740-2316`

**Critical busy-check / early-return — `:1766-1800`:**

```python
async with pipeline_status_lock:
    # Ensure only one worker is processing documents
    if not pipeline_status.get("busy", False):
        to_process_docs: dict[str, DocProcessingStatus] = await self.doc_status.get_docs_by_statuses(
            [DocStatus.PROCESSING, DocStatus.FAILED, DocStatus.PENDING]
        )
        if not to_process_docs:
            logger.info("No documents to process")
            return
        pipeline_status.update({
            "busy": True,
            "job_name": "Default Job",
            "job_start": datetime.now(timezone.utc).isoformat(),
            "docs": 0,
            "batchs": 0,
            "cur_batch": 0,
            "request_pending": False,
            "cancellation_requested": False,
            "latest_message": "",
        })
        del pipeline_status["history_messages"][:]
    else:
        # Another process is busy, just set request flag and return       ← THE BUG
        pipeline_status["request_pending"] = True
        logger.info(
            "Another process is already processing the document queue. Request queued."
        )
        return                                                            # ← :1800 hot exit
```

When two ainsert calls overlap, the second one's `apipeline_process_enqueue_documents` hits the `else` branch at `:1794-1800`: sets `request_pending=True`, returns immediately, and the second ainsert's own `await` resolves before any processing has happened for its doc. The doc remains at `PENDING`.

**Per-doc status writes inside the loop (only reachable in the FIRST ainsert):**

```python
# :2000-2023 — Stage 1: PROCESSING
doc_status_task = asyncio.create_task(
    self.doc_status.upsert({
        doc_id: {
            "status": DocStatus.PROCESSING,    # :2004 — second state write
            ...
        }
    })
)
# ... entity extraction at :2042-2048 ...
# ... merge_nodes_and_edges at :2136-2153 ...
# :2158-2178 — final state
await self.doc_status.upsert({
    doc_id: {
        "status": DocStatus.PROCESSED,         # :2161 — terminal state
        ...
    }
})
```

**`request_pending` re-fetch — `:2285-2304`:**

```python
# Check if there's a pending request to process more documents (with lock)
has_pending_request = False
async with pipeline_status_lock:
    has_pending_request = pipeline_status.get("request_pending", False)
    if has_pending_request:
        pipeline_status["request_pending"] = False

if not has_pending_request:
    break                                       # :2294 — pipeline drains and returns

log_message = "Processing additional documents due to pending request"
logger.info(log_message)
...
to_process_docs = await self.doc_status.get_docs_by_statuses(
    [DocStatus.PROCESSING, DocStatus.FAILED, DocStatus.PENDING]
)                                               # :2302
```

When the first ainsert's gather completes, it re-checks `request_pending`. If the second ainsert set it to True (just before `:1800`), the first ainsert loops back, re-fetches `to_process_docs`, and processes the second doc. But: the second ainsert **has already returned** to its caller, regardless of whether the first ainsert actually picks up the work or is cancelled/killed before it can.

**`finally` block — `:2306-2316`:**

```python
finally:
    log_message = "Enqueued document processing pipeline stopped"
    logger.info(log_message)                    # :2308 — production smoking gun log
    async with pipeline_status_lock:
        pipeline_status["busy"] = False
        pipeline_status["cancellation_requested"] = False
        ...
```

This `finally` runs whether the loop completed normally, raised `PipelineCancelledException` (`:2273-2283`, doc tasks cancelled, **no FAILED status set in cancellation path**), or any other exception propagated out of `gather`.

### 1.4 `LightRAG.finalize_storages` — `:797-843`

```python
async def finalize_storages(self):
    """Asynchronously finalize the storages with improved error handling"""
    if self._storages_status == StoragesStatus.INITIALIZED:
        storages = [
            ("full_docs", self.full_docs),
            ("text_chunks", self.text_chunks),
            ("full_entities", self.full_entities),
            ...
            ("doc_status", self.doc_status),
        ]
        for storage_name, storage in storages:
            if storage:
                try:
                    await storage.finalize()
                ...
        self._storages_status = StoragesStatus.FINALIZED
```

`finalize_storages` **does not trigger** any pending pipeline work. It just calls each storage's `finalize()` (close DB connections, flush in-memory caches, write graphml). If a doc is at `PENDING` when finalize runs, it stays at `PENDING` after finalize — its content is in `full_docs` but no entities/relations have been extracted, no chunks vectorized, nothing in the graph.

---

## 2. doc_status state-transition map

| State | Site | Trigger |
|---|---|---|
| `PENDING` | `lightrag.py:1436` | every successful `apipeline_enqueue_documents` (de-duped) |
| `PROCESSING` | `lightrag.py:2004` | `process_document` Stage 1 — set BEFORE entity extraction |
| `PROCESSED` | `lightrag.py:2161` | `process_document` after `merge_nodes_and_edges` succeeds |
| `FAILED` | `lightrag.py:1477` | duplicate-record sentinel (separate `dup-…` doc id) |
| `FAILED` | `lightrag.py:1579` | data-consistency repair (full_docs missing content) |
| `FAILED` | `lightrag.py:2103` | per-doc exception in `process_document` (NOT `PipelineCancelledException`) |
| `FAILED` | `lightrag.py:2235` | `merge_nodes_and_edges` raised after `PROCESSING` set |

**Critical asymmetry** — `process_document` distinguishes user cancellation from genuine failure (`:2053-2074`). Cancellation logs a brief warning but DOES NOT execute the FAILED-upsert at `:2099-2121`. So a doc cancelled mid-flight stays at:

- `PENDING` if cancellation hit before the Stage 1 PROCESSING upsert at `:2004`
- `PROCESSING` if cancellation hit between `:2004` and `:2161`

This matches production: 4/4 docs stuck pending/processing, 0 in FAILED state.

---

## 3. Local call-pattern audit + persistence-contract gap

Grep summary (filtered for production hot path):

| File:line | Call | Wraps with wait/poll? |
|---|---|---|
| `ingest_wechat.py:382` | `await rag.ainsert(sub_doc_content, ids=[sub_doc_id])` (Vision worker sub-doc) | ❌ none |
| `ingest_wechat.py:933` | `await rag.ainsert(full_content, ids=[doc_id])` (cache-hit re-ingest) | ❌ none |
| `ingest_wechat.py:1173` | `await rag.ainsert(full_content, ids=[doc_id])` (parent doc — primary ingest) | ❌ none |
| `multimodal_ingest.py:151` | `await rag.ainsert(final_content)` (PDF) | ❌ none |
| `enrichment/merge_and_ingest.py:138, 142` | `await rag.ainsert(...)` (legacy RSS, retired in ir-4) | ❌ none |
| `ingest_github.py:266` | `await rag.ainsert(seg_content)` | ❌ none |
| `scripts/wave0c_smoke.py:83` | `await rag.ainsert(excerpt)` (smoke) | ❌ none |
| `scripts/wave0_reembed.py:216, 260` | `await rag.ainsert(content)` (reembed) | ❌ none |
| `scripts/bench_ingest_fixture.py:401` | `await rag.ainsert(full_content, ids=[doc_id])` | ❌ none |
| `scripts/phase0_delete_spike.py:116, 159` | `await rag.ainsert(...)` (delete spike) | ❌ none |
| `.planning/quick/260506-pa7-.../spike_cleanup_probe.py:155` | spike — N/A | ❌ none |

**Persistence contract gate (the line that writes `ingestions.status='ok'`):**

`batch_ingest_from_spider.py:1730-1750`:

```python
success, wall = await ingest_article(
    url_d, dry_run, rag, effective_timeout=effective_timeout
)
if dry_run:
    status = "dry_run"
elif success:
    status = "ok"                              # :1736 — declared success
    ...
else:
    status = "failed"
    ...
conn.execute(
    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
    "VALUES (?, ?, ?, ?)",                     # :1746 — persist 'ok'
    (art_id_d, source_d, status, SKIP_REASON_VERSION_CURRENT),
)
conn.commit()
```

`ingest_article` calls `ingest_wechat()` which awaits `rag.ainsert(parent_content, ids=[doc_id])` at `ingest_wechat.py:1173`, then **fires a Vision worker as `asyncio.create_task` at `:1190`** (not awaited), then returns. The Vision worker eventually calls a SECOND `await rag.ainsert(sub_doc_content, ids=[sub_doc_id])` at `:382`.

**This is the production race:**

1. Article N's `ingest_wechat` returns after its parent ainsert. Vision worker N is fire-and-forget, still running in the background.
2. Loop body writes `ingestions(article_id=N).status='ok'` and commits SQL.
3. Loop iterates to article N+1. `ingest_article` for N+1 starts.
4. Article N+1's parent ainsert and Vision worker N's sub-doc ainsert can now overlap. Whichever loses the busy-flag race takes the `:1796-1800` early-return; its doc stays at `PENDING`.
5. Eventually `_drain_pending_vision_tasks` at `:860` / `:1942` (timeout 120 s) cancels still-pending Vision tasks. Cancellation propagates into the active pipeline's `gather`, raises `PipelineCancelledException` (`:2273`); doc tasks are cancelled at various points; doc states stay at `PENDING` or `PROCESSING`.
6. `await rag.finalize_storages()` runs; `doc_status` is flushed in whatever state it had. Process exits.

This explains 100% of the 2026-05-10 09:00 ADT cron observation:
- `ingestions(status='ok' AND source='wechat') = 4` (the application's view — every ainsert returned without raising)
- `kv_store_doc_status[*].status='processed' = 0` (LightRAG's view — only the first ainsert's doc could have reached PROCESSED, and even that one races with cancellation)
- `4/4` stuck at `pending`/`processing` — exactly matches what the cancellation path leaves.

**No production caller polls / waits / verifies after ainsert.** Every site assumes "ainsert returned ⇒ persisted."

**Existing T1+T2 contract test** (`tests/unit/test_ainsert_persistence_contract.py`, quick 260509-t4i) PASSED both at the mocked-LLM boundary — single-doc and sequential-N=7. That is **consistent with this finding**: T1 and T2 do not exercise concurrent ainsert / Vision-worker overlap. T3 (real Vertex) is the only one that exercises real concurrency, and it is gated `@pytest.mark.skipif`. The bug surface is *concurrency under cancellation*, not *single-doc happy path*.

---

## 4. Upstream SDK pattern (lightrag 1.4.15)

- **No `adrain()` / `await_processed()` / `wait_for_pipeline()` exists.** Confirmed by exhaustive grep on the SDK package: `adrain|await_processed|wait_for_processing|wait_until_processed|wait_pipeline` returns zero matches.
- **The `track_id` returned by `ainsert`** can be paired with `doc_status.get_docs_by_track_id(track_id)` (`base.py:830-833`) to look up status. This is the closest the SDK gets to a "wait" handle. There is no built-in poll loop — the application has to write one.
- **`apipeline_process_enqueue_documents()` is idempotent and safe to invoke directly** after `apipeline_enqueue_documents()` (it's literally what `ainsert` does). Calling it AGAIN after `ainsert` returns can re-pickup any docs left in `PENDING` by the busy-race. But this is racy with the active pipeline's loop — the lock blocks it from making progress until the active pipeline drains. Acceptable when a previous run died — not a substitute for genuine wait.
- **The `pipeline_status` dict is module-global** (per `workspace`). External code can read `pipeline_status["busy"]` and `pipeline_status["request_pending"]` to introspect.

The author's only documented pattern in the source is "fire ainsert, then assume processed" — which is the same trap our code fell into. SDK 1.4.15 does not have a stronger contract.

---

## 5. Mock timing experiment — empirical proof

`scripts/lightrag_diag/probe_ainsert_timing.py` runs four scenarios against an in-memory LightRAG with mock LLM (50 ms simulated extraction) and mock embedder (10 ms zero-vector). Full log: `.scratch/lightrag-pipeline-mock-timing-20260510T1207.log`.

| Scenario | T1 docs | T2 docs | Verdict |
|---|---|---|---|
| 1. Sequential `await ainsert(doc1)` | `doc1=processed` (+0.245 s) | — | ✅ contract holds for sequential |
| 2. Concurrent `gather(ainsert(doc1_v2), ainsert(doc2))` | `doc1_v2=processed doc2=processed` (+ 0.252 s) | — | ✅ both eventually processed (the first ainsert picks up doc2 via `request_pending` and waits inside its own `await` — gather blocks both callers until both done) |
| 3. **Forced race** — task_a created, 5 ms yield, then `await ainsert(doc_b)` | `docA=processing docB=pending` (+0.004 s — second ainsert returned BEFORE its doc was processed) | `docA=processed docB=processed` (+0.403 s — task_a awaited → its loop drained the request_pending) | ⚠️ **second ainsert returns early; doc B stays at `pending`** |
| 4. **Production failure mode** — same as 3, but task_a is cancelled immediately after second ainsert returns | `docA=processing docB=pending` (+0.004 s — application would write ingestions=ok HERE) | `docA=processing docB=pending` (+0.010 s — final persisted state after cancel) | 🔴 **bit-identical to production smoking gun** |

Key SDK log line emitted by Scenario 4: `INFO: Another process is already processing the document queue. Request queued.` — comes straight from `lightrag.py:1797-1799`. Followed by `INFO: Enqueued document processing pipeline stopped` (`:2308`) on cancellation. This is the same log signature observed in production at 09:33:28 ADT.

The probe burns < 1 s wall-clock total, runs offline, no API keys needed.

---

## 6. Fix candidates — LOC, risk, side-effects

Each candidate is scoped to the production hot path: parent-doc ainsert at `ingest_wechat.py:1173` and sub-doc ainsert at `:382`. Other ainsert sites (PDF, github, scripts) are out of cron path; can opt-in once Pattern X stabilizes.

### Pattern A — Poll `doc_status` after ainsert until terminal

| | |
|---|---|
| **Change** | After every `await rag.ainsert(content, ids=[doc_id])` in production, poll `await rag.doc_status.get_by_id(doc_id)` until `status in {PROCESSED, FAILED}` or per-call wall-clock budget elapses. On terminal-PROCESSED return success; on terminal-FAILED or timeout return failure. |
| **LOC** | New helper `lib/lightrag_persistence.py::wait_for_processed(rag, doc_id, deadline_s) -> bool` — ~25 LOC. Apply at 2 production sites (`ingest_wechat.py:1173`, `:382`) — ~6 LOC each (1 new line + budget plumbing). Total: **~37 LOC** (helper + 2 callers). |
| **Risk: false negatives** | Poll budget shorter than real merge time → spurious failure. Mitigation: budget = remaining article timeout from `_compute_article_budget_s` (already plumbed). Floor 60 s. |
| **Risk: poll cadence** | Sleep ≥ 0.5 s between polls or hammer the doc_status backend (NanoVectorDB / nx graphml) with O(1000) reads on a long article. Production-tested cadence: 0.5–2.0 s exponential backoff. |
| **Risk: process exit kills active pipeline** | If the cron process still SIGTERMs the active pipeline, the poll just times out → marked failed → `ingestions.status='failed'` instead of misleading 'ok'. **Strict improvement** over today: today silent corruption, after fix loud failure. |
| **Side effect: Vision worker sub-doc** | Sub-doc ainsert at `:382` is in a fire-and-forget Vision worker. Polling there blocks the Vision worker's task lifetime, NOT the parent ingest. Drain timeout still applies. Acceptable. |
| **Compat with parallel quicks** | T3 contract test (260509-t4i, quick 260510-gkw spike) tests at the SDK boundary; Pattern A is a wrapper above SDK; both compose cleanly. Cognee retire (260510-gfg) is orthogonal. |
| **Verdict** | ✅ **Recommended.** Smallest viable change, no SDK monkey-patching, observable failure mode, transferrable to Hermes by `git push`. |

### Pattern B — Re-invoke `apipeline_process_enqueue_documents` after ainsert

| | |
|---|---|
| **Change** | After every `await rag.ainsert(content, ids=[doc_id])`, immediately call `await rag.apipeline_process_enqueue_documents()` to drain anything left in `PENDING`. |
| **LOC** | 2 production sites × 1 LOC = **2 LOC**. |
| **Risk: still racy** | The second invocation also has to acquire the busy-flag lock. If the first ainsert's pipeline is still running (busy=True), the second invocation just sets `request_pending=True` and returns. **Same bug, lower probability.** Does not solve the cancellation case. |
| **Risk: contention** | If multiple Vision workers + parent ingest all call `apipeline_process_enqueue_documents` simultaneously, lock contention scales with concurrency — but the underlying processing is serialized regardless (only one pipeline at a time). |
| **Side effect: silent latency** | Adds N extra `apipeline_process_enqueue_documents` calls per article. Each one acquires the lock once and (usually) returns immediately when busy. Overhead negligible. |
| **Verdict** | ❌ **Insufficient on its own.** Reduces but does not eliminate the failure under concurrent ainsert + cancellation. May mask the symptom enough to hide the bug, which is worse. |

### Pattern C — Serialize all ainsert calls via an application-level asyncio.Lock

| | |
|---|---|
| **Change** | Wrap every production `await rag.ainsert(...)` with a shared `asyncio.Lock`. Two ainsert calls cannot overlap. |
| **LOC** | New `lib/ainsert_serializer.py::ainsert_lock = asyncio.Lock()` + helper. Apply at 2 sites. **~15 LOC**. |
| **Risk: throughput collapse** | Sub-doc ainsert at `:382` runs inside Vision worker (fire-and-forget). Serializing it means parent ingest of article N+1 waits for Vision-N to finish describing 30 images (~120 s) AND complete its sub-doc ainsert before article N+1's parent ainsert can begin. Cron throughput drops ~3–5×. |
| **Risk: deadlock** | Vision worker holds lock while waiting for parent's `_drain_pending_vision_tasks` → drain holds lock acquisition → ainsert hangs → drain timeout fires. Recoverable but ugly. |
| **Side effect: defeats the entire D-10.06 ARCH-02 design** | Phase 12 explicitly designed Vision worker as fire-and-forget so parent ingest doesn't block on slow Vision API. Pattern C inverts that decision. |
| **Verdict** | ❌ **Wrong tradeoff.** Solves the bug at unacceptable throughput cost. Use only as last resort if Patterns A/D both fail. |

### Pattern D — Synchronous wrapper ditches Vision-worker concurrency for parent ingest only

| | |
|---|---|
| **Change** | Apply Pattern A only at the **parent** ainsert (`:1173`). Sub-doc ainsert (`:382`) remains best-effort — if a sub-doc gets stuck at PENDING after Vision drain, accept the loss (entities re-extracted on next ingest). |
| **LOC** | Pattern A helper (~25 LOC) + 1 caller site (~6 LOC). Total: **~31 LOC**. |
| **Risk: image-side entity loss** | Sub-doc image-side entities may be missed if Vision drain cancels the second ainsert mid-flight. CLAUDE.md `lib/vision_tracking.py:69-71` already documents: "Losing some image-side entities is acceptable — next ingest of the same article re-adds them." Pattern D extends the existing trade-off. |
| **Risk: ingestions=ok still slightly misleading for sub-doc loss** | But the parent doc IS persisted, which is the load-bearing claim. Status='ok' on the parent is honest under Pattern D. |
| **Side effect: honors existing arch decision** | Vision worker stays fire-and-forget at the orchestration layer; only the persistence-contract gate moves. |
| **Verdict** | ✅ **Acceptable** if user prefers narrower change scope. **Pattern A is better** (covers sub-doc too) at +6 LOC cost. |

---

## 7. Recommended fix path

**Pattern A (Poll `doc_status` after ainsert until terminal).** Reasoning:

1. **Smallest viable fix that fully eliminates the silent-corruption mode.** The other patterns either don't fix the bug (B), break throughput (C), or accept partial loss (D). Pattern A leaves cron throughput unchanged and converts every silent failure into an explicit `ingestions.status='failed'` row.

2. **Uses only the SDK's public API.** No monkey-patching. Survives `pip install lightrag --upgrade` to 1.5.x as long as `doc_status.get_by_id` and the `DocStatus` enum stay in the public surface (they're documented in `base.py:818-833`).

3. **Per-article wall-clock budget already exists.** `batch_ingest_from_spider.py:_compute_article_budget_s` produces an int seconds budget that's already wired through `effective_timeout` at `:1718`. Pattern A reuses it as the poll deadline — no new tuning knob.

4. **Composable with parallel quicks.** Quick 260510-gkw (T3 spike with real Vertex Gemini) tests the SDK boundary; Pattern A wraps the SDK boundary; T3 should still pass after Pattern A is applied. Quick 260510-gfg (Cognee retire) is orthogonal.

5. **Failure is loud.** Today: status='ok' on a doc that never reached PROCESSED. Post-fix: status='failed' with `error_msg` mentioning "doc_status timeout after Ns" — operationally legible.

**Suggested implementation sketch** (for follow-up fix quick — DO NOT execute now):

```python
# lib/lightrag_persistence.py  (NEW FILE, ~25 LOC)
import asyncio
import logging
from lightrag.base import DocStatus

logger = logging.getLogger(__name__)


async def wait_for_processed(
    rag, doc_id: str, deadline_s: float = 600.0, poll_min_s: float = 0.5
) -> bool:
    """Poll rag.doc_status[doc_id] until terminal or deadline.

    Returns True only on DocStatus.PROCESSED.
    Returns False on FAILED, deadline, or doc not found.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()
    sleep_s = poll_min_s
    while True:
        raw = await rag.doc_status.get_by_id(doc_id)
        if raw is not None:
            s = raw.get("status")
            s = getattr(s, "value", str(s))
            if s == "processed":
                return True
            if s == "failed":
                return False
        elapsed = loop.time() - start
        if elapsed >= deadline_s:
            logger.warning(
                "wait_for_processed: %s did not reach terminal in %.0fs (status=%s)",
                doc_id, deadline_s, raw.get("status") if raw else "<missing>",
            )
            return False
        await asyncio.sleep(min(sleep_s, max(0.1, deadline_s - elapsed)))
        sleep_s = min(sleep_s * 1.5, 4.0)  # backoff, max 4 s


# ingest_wechat.py:1173-1179 — UPDATED
        _register_pending_doc_id(ckpt_hash, doc_id)
        try:
            await rag.ainsert(full_content, ids=[doc_id])
            persisted = await wait_for_processed(rag, doc_id, deadline_s=remaining_budget_s)
            if not persisted:
                raise RuntimeError(f"LightRAG persistence contract violated for {doc_id}")
        finally:
            _clear_pending_doc_id(ckpt_hash)
```

Total: **~37 LOC across 1 new file + 2 production-call-site edits** (parent + sub-doc). Three new mock-only unit tests covering: terminal=PROCESSED ⇒ True, terminal=FAILED ⇒ False, no terminal before deadline ⇒ False (with elapsed time assertion).

**STOP gate:** Recommendation only. The follow-up fix quick is the user's decision — this quick does not start it.

---

## 8. Open questions for the follow-up fix quick

1. **Per-doc deadline policy.** Current `_compute_article_budget_s` returns a per-article budget that includes `ainsert + Vision`. After Pattern A, the poll deadline is "remaining budget after ainsert returned." Should poll have its own minimum (e.g., 60 s) to avoid 0-budget poll on slow ainsert? Or trust article-budget math?

2. **Sub-doc deadline.** Vision worker is fire-and-forget; the orchestrator drain has 120 s ceiling. If sub-doc ainsert poll hits 120 s and times out, we mark sub-doc as "image-side loss" but leave parent's `ingestions.status='ok'` untouched. Confirm this matches existing `lib/vision_tracking.py:69-71` design.

3. **`get_by_id` return shape stability.** `doc_status.get_by_id` returns `dict | None` per the storage interface; the `status` field is sometimes a `DocStatus` enum and sometimes a string (lifted from JSON). The probe uses `getattr(s, 'value', str(s))` to normalize — confirm this for the production NanoVectorDB / NetworkX storage backend on Hermes.

4. **Pattern A interaction with `cancellation_requested`.** If the orchestrator initiates pipeline cancellation (`pipeline_status["cancellation_requested"]=True`), the active pipeline's docs land at PENDING/PROCESSING (no FAILED upsert). Pattern A's poll observes that and times out → marks failed. This is correct, but means a planned shutdown produces `ingestions.status='failed'` for every in-flight doc. May or may not be desired (currently they get silent-success — Pattern A makes them loud-failure). Worth tracking but not a blocker.

5. **NanoVectorDB read-after-write consistency.** Inside `process_document` Stage 1, `doc_status.upsert` is fired as `asyncio.create_task` at `:2000-2023` and gather'd at `:2040`. Pattern A reads `get_by_id` directly. If the storage backend has eventual consistency, polling could observe stale state. NanoVectorDB writes appear synchronous on the same event loop, but verify on Hermes with a single-article smoke before declaring fix shipped.

6. **What about kg_synthesize.py query path?** `kg_synthesize.aquery` reads the graph at query time. If a doc is at PENDING (entities not yet extracted), the query returns empty graph results for that doc — incomplete, but not corrupt. Out of scope for ainsert persistence fix; surfaces independently as "synthesis empty for recently-ingested doc."

---

**END OF INVESTIGATION**
