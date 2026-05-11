"""Quick task 260509-t4i — LightRAG ``ainsert`` persistence contract tests.

Codifies the implicit production contract:

    await rag.ainsert(content=..., ids=[doc_id])  returns
    ⇒ doc_id MUST land in kv_store_doc_status.json with status="processed".

2026-05-09 ADT production evidence (Hermes):

* ``ingestions`` table: ``status='ok' AND source='wechat' AND date=2026-05-09``
  → 41 rows.
* ``kv_store_doc_status.json``: ``status='processed' AND date=2026-05-09``
  → 15 unique doc_ids.
* Delta: 26 silent contract violations — ingest path reported success but
  LightRAG storage did not finalize.
* ``graph_chunk_entity_relation.graphml`` mtime frozen at 18:41 ADT despite
  the ingestions ledger continuing to write ``ok`` rows past 22:00 ADT.

Three-tier isolation (regression-only — no source code changes):

* T1 single-doc with mocked LLM/embed   — if FAIL: LightRAG single-doc path itself broken.
* T2 sequential N=7 with mocked LLM/embed — if FAIL: state leak across articles.
* T3 single-doc with real Vertex Gemini   — gated; default-skipped via skipif.

Reading ``kv_store_doc_status.json`` directly off disk (not via the LightRAG
API) is deliberate — the bug surface is the persisted file, exactly what
production observed.

Mock LLM returns just the LightRAG completion delimiter (``<|COMPLETE|>``)
which the parser accepts as "no entities found"
(see ``lightrag/operate.py:_process_extraction_result``).

pyproject.toml already sets ``asyncio_mode = "auto"`` — no decorator needed.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc

# Production embedding dim per CLAUDE.md (gemini-embedding-2). Hardcoded to
# match production shape — do NOT shrink to make a test pass.
_PRODUCTION_EMBEDDING_DIM = 3072


async def _fake_llm(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    **kwargs: Any,
) -> str:
    """Mock LLM that returns the LightRAG completion delimiter only.

    LightRAG's ``_process_extraction_result`` (operate.py:937) parses the
    string for ``entity<|#|>...`` records, then a trailing ``<|COMPLETE|>``.
    Returning just the delimiter is interpreted as "no entities found" and
    proceeds to the persistence step without raising.
    """
    return "<|COMPLETE|>"


async def _fake_embed(texts: list[str], **kwargs: Any) -> np.ndarray:
    """Mock embedding that returns zero-vectors at production dim."""
    return np.zeros((len(texts), _PRODUCTION_EMBEDDING_DIM), dtype=np.float32)


def _make_embedding_func() -> EmbeddingFunc:
    """Wrap ``_fake_embed`` in LightRAG's required ``EmbeddingFunc`` shell."""
    return EmbeddingFunc(
        embedding_dim=_PRODUCTION_EMBEDDING_DIM,
        func=_fake_embed,
    )


async def _build_rag(tmp_path: Path) -> LightRAG:
    """Instantiate LightRAG against ``tmp_path`` with mocked LLM + embed."""
    rag = LightRAG(
        working_dir=str(tmp_path),
        llm_model_func=_fake_llm,
        embedding_func=_make_embedding_func(),
        # Disable LLM cache so every chunk forces a fresh LLM call —
        # exercises the parser path under test.
        enable_llm_cache=False,
        enable_llm_cache_for_entity_extract=False,
    )
    await rag.initialize_storages()
    return rag


def _assert_doc_status_processed(tmp_path: Path, doc_id: str) -> None:
    """Assert ``kv_store_doc_status.json`` has ``doc_id`` with ``status='processed'``.

    Reads the file directly off disk — the bug surface is the persisted
    file, not the in-memory LightRAG API.
    """
    status_path = tmp_path / "kv_store_doc_status.json"
    assert status_path.exists(), (
        f"kv_store_doc_status.json missing at {status_path}; ainsert did not "
        f"flush document status to disk."
    )
    raw = status_path.read_text(encoding="utf-8")
    try:
        store = json.loads(raw)
    except json.JSONDecodeError as e:  # pragma: no cover — surface the bytes
        raise AssertionError(
            f"kv_store_doc_status.json is not valid JSON: {e}\n"
            f"first 200 chars: {raw[:200]!r}"
        )
    assert doc_id in store, (
        f"doc_id {doc_id!r} missing from kv_store_doc_status.json. "
        f"Keys present: {sorted(store.keys())}"
    )
    entry = store[doc_id]
    assert isinstance(entry, dict), (
        f"kv_store_doc_status entry for {doc_id!r} is not a dict: {entry!r}"
    )
    assert entry.get("status") == "processed", (
        f"doc_id {doc_id!r} has status={entry.get('status')!r}, expected "
        f"'processed'. Full entry: {entry!r}"
    )


# ---------------------------------------------------------------------------
# T1 — single-doc with mocked LLM/embed
# ---------------------------------------------------------------------------

async def test_t1_single_doc_persists_status_processed(tmp_path: Path) -> None:
    """Single doc: ainsert returns ⇒ doc_id present + processed in status file.

    If RED: LightRAG single-doc persistence is broken at the framework
    level — the bug is below the call site in ``ingest_wechat.ingest_wechat``.
    """
    rag = await _build_rag(tmp_path)
    doc_id = "doc-t1-001"
    # ≥1 chunk worth (default chunk_token_size=1200 ≈ 4800 chars).
    content = "x" * 5000
    # ``ainsert`` first positional param is ``input`` (verified against
    # lightrag-hku 1.4.15 signature); production sites pass content
    # positionally, e.g. ``rag.ainsert(excerpt)`` in scripts/wave0c_smoke.py.
    await rag.ainsert(content, ids=[doc_id])
    _assert_doc_status_processed(tmp_path, doc_id)


# ---------------------------------------------------------------------------
# T2 — sequential N=7 with mocked LLM/embed (state-leak detection)
# ---------------------------------------------------------------------------

async def test_t2_sequential_seven_docs_no_state_leak(tmp_path: Path) -> None:
    """Seven sequential ainsert calls on the SAME LightRAG instance.

    All 7 doc_ids must be present + processed in kv_store_doc_status.json
    after the loop.

    If RED: state leaks between articles in the same LightRAG instance —
    e.g. the second flush silently overwrites the first, or a per-instance
    cache corrupts state across documents.
    """
    rag = await _build_rag(tmp_path)
    doc_ids: list[str] = []
    for i in range(7):
        doc_id = f"doc-t2-{i:03d}"
        doc_ids.append(doc_id)
        content = f"prefix-{i} " + ("x" * 5000)
        await rag.ainsert(content, ids=[doc_id])

    for doc_id in doc_ids:
        _assert_doc_status_processed(tmp_path, doc_id)


# ---------------------------------------------------------------------------
# T3 — single doc with real Vertex Gemini (slow, gated)
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.skipif(
    not Path(".dev-runtime/gcp-paid-sa.json").is_file()
    or not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="T3 requires .dev-runtime/gcp-paid-sa.json + GOOGLE_CLOUD_PROJECT env var",
)
async def test_t3_real_vertex_gemini_single_doc(tmp_path: Path) -> None:
    """Single doc with real Vertex Gemini LLM + embed — 5min wait_for ceiling.

    Default-skipped: the skipif above fires unless both the SA JSON file and
    GOOGLE_CLOUD_PROJECT env var are present. Even when both are present,
    a default ``pytest`` run does NOT pass ``-m slow``, so collection still
    excludes it unless the operator opts in explicitly.

    If PASS: real-stack + persistence both healthy.
    If TIMEOUT (5min): persistence flush hangs against the live LLM/embed —
    the in-the-wild failure mode.
    """
    # ``importorskip`` triggers a clean skip if module names diverge from
    # the spec (e.g., ``lib.lightrag_embedding`` not yet promoted with
    # the public ``gemini_embed`` alias). The actual public name in this
    # repo is ``embedding_func`` — reflect that.
    vertex_mod = pytest.importorskip("lib.vertex_gemini_complete")
    embed_mod = pytest.importorskip("lib.lightrag_embedding")

    vertex_gemini_model_complete = getattr(
        vertex_mod, "vertex_gemini_model_complete", None
    )
    real_embedding_func = getattr(embed_mod, "embedding_func", None)
    if vertex_gemini_model_complete is None or real_embedding_func is None:
        pytest.skip(
            "Required public names not found: "
            "lib.vertex_gemini_complete.vertex_gemini_model_complete or "
            "lib.lightrag_embedding.embedding_func"
        )

    rag = LightRAG(
        working_dir=str(tmp_path),
        llm_model_func=vertex_gemini_model_complete,
        embedding_func=real_embedding_func,
    )
    await rag.initialize_storages()
    doc_id = "doc-t3-real-001"
    content = "x" * 5000
    await asyncio.wait_for(
        rag.ainsert(content, ids=[doc_id]),
        timeout=300,
    )
    _assert_doc_status_processed(tmp_path, doc_id)


# ---------------------------------------------------------------------------
# Quick 260510-gkw — T3a + T3b multi-snapshot real-Vertex contract spike
# ---------------------------------------------------------------------------
# T1+T2 (mock) PASSED in predecessor 260509-t4i ⇒ LightRAG framework healthy.
# Original T3 (single-doc real-Vertex, single post-finalize snapshot) leaves
# the production-bug surface unobserved: did doc_status flip to 'processed'
# at post-AWAIT (where production marks ingestions=ok), or only later at
# post-FINALIZE? T3a + T3b add the missing snapshots.
#
# 2026-05-10 09:00 ADT cron forensic: 4 ingestions=ok wechat, but only
# 1-2 LightRAG kv_store_doc_status='processed', 21min gap between graphml
# mtime (09:12) and finalize log (09:33). Hypothesis under test: ainsert
# returns BEFORE doc_status flips to 'processed'.
# ---------------------------------------------------------------------------


def _read_doc_status(tmp_path: Path, doc_id: str) -> str | None:
    """Return ``store[doc_id]['status']`` or ``None`` if file/key missing.

    Reads ``kv_store_doc_status.json`` directly off disk — same surface the
    production bug observes. Does NOT raise on missing file (lets caller
    distinguish "file does not exist yet" from "file exists, key missing").
    """
    status_path = tmp_path / "kv_store_doc_status.json"
    if not status_path.exists():
        return None
    raw = status_path.read_text(encoding="utf-8")
    try:
        store = json.loads(raw)
    except json.JSONDecodeError:
        return None
    entry = store.get(doc_id)
    if not isinstance(entry, dict):
        return None
    val = entry.get("status")
    return val if isinstance(val, str) else None


@pytest.mark.slow
@pytest.mark.skipif(
    not Path(".dev-runtime/gcp-paid-sa.json").is_file()
    or not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="T3a requires .dev-runtime/gcp-paid-sa.json + GOOGLE_CLOUD_PROJECT env var",
)
async def test_t3a_real_vertex_post_await_vs_post_finalize(tmp_path: Path) -> None:
    """T3a — single doc, real Vertex, snapshot status at post-await + post-finalize.

    Diagnostic value: if ``post_await_status != 'processed'`` but
    ``post_finalize_status == 'processed'``, the contract violation is
    isolated to the post-await window — production's ingestions=ok marker
    fires before LightRAG has flipped the status file.

    Main assertion (literal): ``post_await_status == 'processed'``.
    """
    vertex_mod = pytest.importorskip("lib.vertex_gemini_complete")
    embed_mod = pytest.importorskip("lib.lightrag_embedding")

    vertex_gemini_model_complete = getattr(
        vertex_mod, "vertex_gemini_model_complete", None
    )
    real_embedding_func = getattr(embed_mod, "embedding_func", None)
    if vertex_gemini_model_complete is None or real_embedding_func is None:
        pytest.skip(
            "Required public names not found: "
            "lib.vertex_gemini_complete.vertex_gemini_model_complete or "
            "lib.lightrag_embedding.embedding_func"
        )

    rag = LightRAG(
        working_dir=str(tmp_path),
        llm_model_func=vertex_gemini_model_complete,
        embedding_func=real_embedding_func,
    )
    await rag.initialize_storages()

    doc_id = "doc-t3a-real-001"
    content = "x" * 5000  # ≥1 chunk at default chunk_token_size=1200

    print(f"\n[T3a working_dir] {tmp_path}", flush=True)

    # --- Snapshot 1: post-await ainsert ---
    t_before = time.monotonic()
    await asyncio.wait_for(
        rag.ainsert(content, ids=[doc_id]),
        timeout=300,
    )
    t_post_await = time.monotonic()
    post_await_elapsed = t_post_await - t_before

    status_path = tmp_path / "kv_store_doc_status.json"
    assert status_path.exists(), (
        f"[T3a] ainsert returned but kv_store_doc_status.json does not exist "
        f"at {status_path}"
    )
    post_await_status = _read_doc_status(tmp_path, doc_id)
    print(
        f"[T3a status] post-await: {post_await_status}",
        flush=True,
    )

    # --- Snapshot 2: post-finalize_storages ---
    await rag.finalize_storages()
    t_post_finalize = time.monotonic()
    post_finalize_elapsed = t_post_finalize - t_before

    post_finalize_status = _read_doc_status(tmp_path, doc_id)
    print(
        f"[T3a status] post-finalize: {post_finalize_status}",
        flush=True,
    )

    print(
        f"[T3a verdict] post-await={post_await_status} "
        f"post-finalize={post_finalize_status} "
        f"dt_await={post_await_elapsed:.1f}s "
        f"dt_total={post_finalize_elapsed:.1f}s",
        flush=True,
    )

    # Main assertion — literal string compare per plan.
    assert post_await_status == "processed", (
        f"contract violation: post-await status={post_await_status!r}, "
        f"expected 'processed'. post-finalize status={post_finalize_status!r}. "
        f"dt_await={post_await_elapsed:.1f}s dt_total={post_finalize_elapsed:.1f}s"
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not Path(".dev-runtime/gcp-paid-sa.json").is_file()
    or not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="T3b requires .dev-runtime/gcp-paid-sa.json + GOOGLE_CLOUD_PROJECT env var",
)
async def test_t3b_sequential_5_real_vertex_per_article_status(
    tmp_path: Path,
) -> None:
    """T3b — 5 sequential ainserts on ONE rag instance, real Vertex, per-doc snapshot.

    For each iter ``i``:
      * Call ``await asyncio.wait_for(rag.ainsert(...), 300)``
      * Snapshot ``kv_store_doc_status.json[doc_id]['status']``
      * Print ``[T3b iter {i}] doc={doc_id} status=... dt={iter_elapsed:.1f}s``

    After loop:
      * Call ``rag.finalize_storages()`` once.
      * Re-snapshot status for all 5 doc_ids.

    Verdict lines:
      * ``[T3b verdict] post-await processed: X/5``
      * ``[T3b verdict] post-finalize processed: Y/5``

    Main assertion: ``not not_processed`` where ``not_processed`` = list of
    ``(doc_id, status)`` from the post-await snapshot list with
    ``status != 'processed'``.

    Loop runs all 5 iters before asserting — observable X/5 ratio in log
    even if iter 0 already violates.
    """
    vertex_mod = pytest.importorskip("lib.vertex_gemini_complete")
    embed_mod = pytest.importorskip("lib.lightrag_embedding")

    vertex_gemini_model_complete = getattr(
        vertex_mod, "vertex_gemini_model_complete", None
    )
    real_embedding_func = getattr(embed_mod, "embedding_func", None)
    if vertex_gemini_model_complete is None or real_embedding_func is None:
        pytest.skip(
            "Required public names not found: "
            "lib.vertex_gemini_complete.vertex_gemini_model_complete or "
            "lib.lightrag_embedding.embedding_func"
        )

    rag = LightRAG(
        working_dir=str(tmp_path),
        llm_model_func=vertex_gemini_model_complete,
        embedding_func=real_embedding_func,
    )
    await rag.initialize_storages()

    print(f"\n[T3b working_dir] {tmp_path}", flush=True)

    post_await_snapshots: list[tuple[str, str | None]] = []
    iter_elapsed_list: list[float] = []
    doc_ids: list[str] = []
    t_loop_start = time.monotonic()

    for i in range(5):
        doc_id = f"doc-t3b-{i:03d}"
        doc_ids.append(doc_id)
        # ~3KB unique content per doc — mixed ASCII + CJK, ≥ chunk threshold.
        content = (
            f"article-{i}-prefix "
            + ("lorem ipsum " * 200)
            + ("中文样本 " * 100)
        )

        t_iter_start = time.monotonic()
        await asyncio.wait_for(
            rag.ainsert(content, ids=[doc_id]),
            timeout=300,
        )
        iter_elapsed = time.monotonic() - t_iter_start
        iter_elapsed_list.append(iter_elapsed)

        current_status = _read_doc_status(tmp_path, doc_id)
        post_await_snapshots.append((doc_id, current_status))
        print(
            f"[T3b iter {i}] doc={doc_id} status={current_status} "
            f"dt={iter_elapsed:.1f}s",
            flush=True,
        )

    t_loop_end = time.monotonic()

    # --- Single post-finalize_storages call after the loop ---
    await rag.finalize_storages()
    t_finalize_end = time.monotonic()

    post_finalize_snapshots: list[tuple[str, str | None]] = [
        (doc_id, _read_doc_status(tmp_path, doc_id)) for doc_id in doc_ids
    ]
    for doc_id, status in post_finalize_snapshots:
        print(
            f"[T3b post-finalize] doc={doc_id} status={status}",
            flush=True,
        )

    not_processed = [
        (d, s) for d, s in post_await_snapshots if s != "processed"
    ]
    not_processed_final = [
        (d, s) for d, s in post_finalize_snapshots if s != "processed"
    ]

    print(
        f"[T3b verdict] post-await processed: "
        f"{5 - len(not_processed)}/5",
        flush=True,
    )
    print(
        f"[T3b verdict] post-finalize processed: "
        f"{5 - len(not_processed_final)}/5",
        flush=True,
    )
    print(
        f"[T3b timing] loop_elapsed={t_loop_end - t_loop_start:.1f}s "
        f"finalize_elapsed={t_finalize_end - t_loop_end:.1f}s "
        f"total={t_finalize_end - t_loop_start:.1f}s "
        f"per_iter={[f'{x:.1f}s' for x in iter_elapsed_list]}",
        flush=True,
    )

    # Main assertion — literal per plan.
    assert not not_processed, (
        f"contract violation: {len(not_processed)}/5 docs not 'processed' "
        f"at post-await: {not_processed!r}. "
        f"post-finalize not_processed: {not_processed_final!r}"
    )
