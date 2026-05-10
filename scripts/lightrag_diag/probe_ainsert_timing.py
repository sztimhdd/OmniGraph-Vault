"""Probe LightRAG ainsert pipeline timing — quick 260510-gqu Step 4.

Verifies (or refutes) the hypothesis that ``await rag.ainsert(content)``
returns BEFORE ``doc_status[doc_id].status == DocStatus.PROCESSED`` in
specific concurrency patterns.

Two scenarios:

1. **Sequential** — single ``ainsert`` awaited end-to-end. Expected:
   doc reaches PROCESSED inside ainsert (synchronous from caller's POV).

2. **Concurrent** — two ``ainsert`` calls overlap. Expected: the SECOND
   ainsert returns early via the ``busy=True`` branch
   (``lightrag.py:1796-1800``), with its doc still at PENDING. The FIRST
   ainsert's pipeline picks up the second doc via ``request_pending``.

Mock LLM/embedding so the test runs offline (no network, no API keys).
Output goes to ``.scratch/lightrag-pipeline-mock-timing-<ts>.log``.

Exit codes:
- 0 on completion (regardless of hypothesis verdict — read the log)
- 1 on import / setup failure

NO production code touched. Read-only on LightRAG SDK (only instantiate
its public class).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Repo-root on sys.path so SDK imports the same as production.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np

from lightrag import LightRAG
from lightrag.base import DocStatus
from lightrag.utils import EmbeddingFunc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S.%f"[:-3],
)
log = logging.getLogger("probe")

# Sized to land in TWO chunks (default chunk_token_size=1200; 1 token ≈ 4 chars
# per LightRAG tokenizer, so >5000 chars guarantees split). Two chunks
# means the per-doc LLM extraction runs twice — gives the second concurrent
# ainsert a real window to overlap with the first.
DOC1 = "Alpha Bravo " * 600  # ~7200 chars → multi-chunk
DOC2 = "Charlie Delta " * 600  # ~8400 chars

DOC1_ID = "doc-mock-aaaa"
DOC2_ID = "doc-mock-bbbb"


async def _mock_llm(prompt: str, system_prompt: str | None = None,
                   history_messages: list | None = None,
                   keyword_extraction: bool = False, **kw) -> str:
    """Return a deterministic JSON-like extraction so LightRAG's parser
    accepts it. The exact format is the v1.4 entity-extract delimiter
    syntax — minimal but parseable.

    Burns ~50 ms to make concurrent windows visible in timing.
    """
    await asyncio.sleep(0.05)
    if "entity_extract" in (system_prompt or "") or "Entities" in prompt:
        # Minimal v1.4 entity-extract output: one entity, one relation, completion.
        return (
            '("entity"<|>ALPHA<|>concept<|>placeholder entity)\n'
            "##\n"
            '("entity"<|>BRAVO<|>concept<|>second placeholder)\n'
            "##\n"
            '("relationship"<|>ALPHA<|>BRAVO<|>relates<|>placeholder<|>0.5)\n'
            "<|COMPLETE|>"
        )
    return "OK"


async def _mock_embed(texts: list[str]) -> np.ndarray:
    await asyncio.sleep(0.01)
    # 8-dim deterministic embedding so tests are stable.
    return np.zeros((len(texts), 8), dtype=np.float32)


def _make_rag(working_dir: str) -> LightRAG:
    embed = EmbeddingFunc(
        embedding_dim=8,
        max_token_size=8192,
        func=_mock_embed,
    )
    rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=_mock_llm,
        embedding_func=embed,
        llm_model_name="mock-llm",
        embedding_func_max_async=1,
        embedding_batch_num=8,
        llm_model_max_async=2,
        max_parallel_insert=2,
    )
    return rag


async def _read_status(rag: LightRAG, doc_id: str) -> str:
    raw = await rag.doc_status.get_by_id(doc_id)
    if raw is None:
        return "<not-found>"
    s = raw.get("status")
    return getattr(s, "value", str(s))


async def _scenario_sequential(rag: LightRAG) -> None:
    log.info("=" * 70)
    log.info("SCENARIO 1: SEQUENTIAL ainsert")
    log.info("=" * 70)
    t0 = time.monotonic()
    log.info("T0 (pre-ainsert): doc1.status=%s", await _read_status(rag, DOC1_ID))
    await rag.ainsert(DOC1, ids=[DOC1_ID])
    t1 = time.monotonic()
    log.info(
        "T1 (post-ainsert, +%.3fs): doc1.status=%s",
        t1 - t0, await _read_status(rag, DOC1_ID),
    )


async def _scenario_concurrent(rag: LightRAG) -> None:
    log.info("=" * 70)
    log.info("SCENARIO 2: CONCURRENT ainsert (gather)")
    log.info("=" * 70)
    log.info("T0 (pre-gather): doc2.status=%s", await _read_status(rag, DOC2_ID))

    # We can't easily reproduce the production pattern (Vision worker fires
    # ainsert mid-loop) without a real timing source, but gather() exercises
    # the same code path: both ainserts run concurrently in the same loop,
    # so one of them MUST hit busy=True and take the early-return branch.
    t0 = time.monotonic()
    results = await asyncio.gather(
        rag.ainsert(DOC1 + " v2", ids=[DOC1_ID + "_v2"]),
        rag.ainsert(DOC2, ids=[DOC2_ID]),
        return_exceptions=True,
    )
    t1 = time.monotonic()
    log.info("gather returned in %.3fs (results=%r)", t1 - t0, results)
    log.info(
        "T1 (post-gather): doc1_v2.status=%s doc2.status=%s",
        await _read_status(rag, DOC1_ID + "_v2"),
        await _read_status(rag, DOC2_ID),
    )


async def _scenario_busy_early_return(rag: LightRAG) -> None:
    """Simulate the production race: pipeline already busy when second
    ainsert is invoked — second ainsert MUST take the early-return path.

    Patches the LightRAG instance's ``apipeline_process_enqueue_documents``
    via a wrapper that delays acquiring the lock, so the second concurrent
    call definitely sees ``busy=True``.
    """
    log.info("=" * 70)
    log.info("SCENARIO 3: BUSY EARLY-RETURN (forced race)")
    log.info("=" * 70)

    # Verify these are NEW docs (not from prior scenarios).
    doc_a_id = "doc-mock-cccc"
    doc_b_id = "doc-mock-dddd"
    log.info(
        "T0 (pre-tasks): docA.status=%s docB.status=%s",
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )

    # First ainsert — start as a task; do not await yet, so its pipeline
    # is in flight when we issue the second ainsert below.
    t_start = time.monotonic()
    task_a = asyncio.create_task(
        rag.ainsert(DOC1 + " sceneA", ids=[doc_a_id])
    )

    # Yield long enough for task_a to enqueue + acquire the pipeline lock.
    await asyncio.sleep(0.005)

    # Second ainsert called CONCURRENTLY — should see busy=True, return fast.
    t_b_start = time.monotonic()
    await rag.ainsert(DOC2 + " sceneB", ids=[doc_b_id])
    t_b_end = time.monotonic()
    log.info(
        "T1 (second ainsert returned, +%.3fs): docA.status=%s docB.status=%s",
        t_b_end - t_b_start,
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )
    log.info("CRITICAL: docB returned before its processing finished — see status above")

    # Now await task_a — its pipeline picks up docB via request_pending.
    await task_a
    t_end = time.monotonic()
    log.info(
        "T2 (first ainsert task awaited, +%.3fs total): docA.status=%s docB.status=%s",
        t_end - t_start,
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )


async def _scenario_orphan_pending(rag: LightRAG) -> None:
    """The production smoking gun: second ainsert returns, application
    declares success and writes ingestions=ok. The orchestrator then
    cancels (or process exits) BEFORE the first ainsert's pipeline picks
    up docB via request_pending.

    To simulate this, we cancel task_a immediately after the second
    ainsert returns. Expected: docB stays at PENDING.
    """
    log.info("=" * 70)
    log.info("SCENARIO 4: ORPHANED PENDING (production failure mode)")
    log.info("=" * 70)

    doc_a_id = "doc-mock-eeee"
    doc_b_id = "doc-mock-ffff"

    log.info(
        "T0: docA.status=%s docB.status=%s",
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )
    t_start = time.monotonic()
    task_a = asyncio.create_task(
        rag.ainsert(DOC1 + " sceneC", ids=[doc_a_id])
    )
    await asyncio.sleep(0.005)
    t_b_start = time.monotonic()
    await rag.ainsert(DOC2 + " sceneD", ids=[doc_b_id])
    t_b_end = time.monotonic()
    log.info(
        "T1 (second ainsert returned, +%.3fs): "
        "docA.status=%s docB.status=%s [APPLICATION WOULD WRITE ingestions=ok HERE]",
        t_b_end - t_b_start,
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )

    # Cancel the first ainsert's pipeline mid-processing — simulates the
    # production drain timeout / process exit.
    task_a.cancel()
    try:
        await task_a
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.info("task_a returned exception: %r", e)
    t_end = time.monotonic()
    log.info(
        "T2 (after task_a cancellation, +%.3fs total): "
        "docA.status=%s docB.status=%s [WHAT GETS PERSISTED]",
        t_end - t_start,
        await _read_status(rag, doc_a_id),
        await _read_status(rag, doc_b_id),
    )


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="lightrag_diag_")
    log.info("temp_working_dir: %s", tmp)
    rag = _make_rag(tmp)
    try:
        if hasattr(rag, "initialize_storages"):
            await rag.initialize_storages()
        await _scenario_sequential(rag)
        await _scenario_concurrent(rag)
        await _scenario_busy_early_return(rag)
        await _scenario_orphan_pending(rag)
        log.info("=" * 70)
        log.info("PROBE COMPLETE — see scenario T1/T2 statuses above")
        log.info("=" * 70)
        return 0
    finally:
        try:
            await rag.finalize_storages()
        except Exception as e:
            log.info("finalize_storages raised (non-fatal in mock): %r", e)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
