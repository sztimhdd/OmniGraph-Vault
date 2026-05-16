"""Dry-run e2e test for the LightRAG-Databricks provider factory.

Runs against REAL Model Serving endpoints (not mocked). Auth via user OAuth
from ``~/.databrickscfg [dev]`` profile. Cost: ~$0.20-$0.80 per full run.
Time: ~10 min wallclock.

Skip in CI by default - use ``pytest -m dryrun`` to opt in. For local
pre-deploy validation only (kdb-1.5 LLM-DBX-03 acceptance test).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pytest


def _safe_print(msg: str) -> None:
    """Print, falling back to ASCII-safe repr on Windows cp1252 consoles
    that can't encode emoji / CJK characters from Model Serving responses.
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="backslashreplace").decode("ascii"))

# Make databricks-deploy/ importable in test context
sys.path.insert(0, str(Path(__file__).parent.parent))
from lightrag_databricks_provider import (  # noqa: E402
    EMBEDDING_DIM,
    KB_EMBEDDING_MODEL,
    KB_LLM_MODEL,
    make_embedding_func,
    make_llm_func,
)

pytestmark = pytest.mark.dryrun

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures() -> list[str]:
    """Load all 5 fixture article texts in lexicographic order."""
    articles = []
    for path in sorted(FIXTURES_DIR.glob("article_*.txt")):
        articles.append(path.read_text(encoding="utf-8"))
    return articles


def _find_vector_of_dim(obj, expected_dim: int) -> bool:
    """Walk a nested JSON-decoded object; return True iff at least one of:
      (a) a top-level / nested int field literally equal to ``expected_dim``
          under a key named ``embedding_dim`` or ``dim``, OR
      (b) a list of numeric values with length ``expected_dim``.

    Key-name-agnostic: nano-vectordb's on-disk schema stores vectors as a
    base64-encoded ``matrix`` blob (NOT a JSON float list), with a sibling
    integer ``embedding_dim: 1024`` field. Earlier schema versions or other
    backends may inline raw float lists. Cover both.
    """
    if isinstance(obj, list):
        if obj and all(isinstance(x, (int, float)) for x in obj) and len(obj) == expected_dim:
            return True
        return any(_find_vector_of_dim(item, expected_dim) for item in obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("embedding_dim", "dim") and isinstance(v, int) and v == expected_dim:
                return True
            if _find_vector_of_dim(v, expected_dim):
                return True
    return False


@pytest.mark.asyncio
async def test_llm_factory_smoke():
    """Test 1: LLM factory smoke (~5s, ~$0.01).

    Round-trip a trivial prompt through the make_llm_func() factory and
    assert non-empty string response within 10s latency budget.
    """
    llm = make_llm_func()
    t0 = time.time()
    response = await llm(
        "Reply with exactly the word: pong",
        system_prompt="You are a test bot.",
    )
    elapsed = time.time() - t0
    _safe_print(f"\n[Test 1] LLM smoke latency: {elapsed:.2f}s; response={response!r}")
    assert isinstance(response, str)
    assert len(response) > 0
    assert elapsed < 10.0, f"LLM call took {elapsed:.2f}s (expected <10s)"


@pytest.mark.asyncio
async def test_embedding_factory_smoke():
    """Test 2: Embedding factory smoke (~3s, ~$0.001).

    Verify the SDK kwarg shape (input=texts) works for the embedding
    endpoint and the response decodes to (1, 1024) float32 ndarray.
    Surface Risk #2 (SDK shape mismatch) early.
    """
    emb = make_embedding_func()
    t0 = time.time()
    vec = await emb(["hello world"])
    elapsed = time.time() - t0
    _safe_print(
        f"\n[Test 2] Embedding smoke latency: {elapsed:.2f}s; "
        f"shape={vec.shape}; dtype={vec.dtype}"
    )
    assert vec.shape == (1, EMBEDDING_DIM)
    assert vec.dtype == np.float32
    assert emb.embedding_dim == EMBEDDING_DIM
    assert emb.max_token_size == 8192


@pytest.mark.asyncio
async def test_lightrag_e2e_roundtrip(tmp_path):
    """Test 3: LightRAG e2e roundtrip (~5 min, ~$0.20-$0.80).

    The LLM-DBX-03 acceptance test. Instantiate REAL LightRAG against REAL
    Model Serving, ainsert 5 fixture articles, aquery, assert graph + vdb
    files emitted. Verify embedding_dim=1024 contract end-to-end via
    key-name-agnostic walk (NIT 6 / RESEARCH.md vdb shape uncertainty).
    """
    from lightrag import LightRAG, QueryParam

    tmp_dir = tmp_path / f"lightrag_storage_dryrun_{int(time.time())}"
    tmp_dir.mkdir()
    try:
        rag = LightRAG(
            working_dir=str(tmp_dir),
            llm_model_func=make_llm_func(),
            embedding_func=make_embedding_func(),
        )
        await rag.initialize_storages()

        t0 = time.time()
        for art in _load_fixtures():
            await rag.ainsert(art)
        ingest_elapsed = time.time() - t0

        q_t0 = time.time()
        response = await rag.aquery(
            "What multi-agent frameworks are mentioned?",
            QueryParam(mode="hybrid"),
        )
        query_elapsed = time.time() - q_t0
        total_elapsed = time.time() - t0

        _safe_print(
            f"\n[Test 3] e2e wallclock: ingest={ingest_elapsed:.2f}s; "
            f"query={query_elapsed:.2f}s; total={total_elapsed:.2f}s"
        )
        _safe_print(f"[Test 3] Response excerpt (first 300 chars): {response[:300]!r}")

        assert isinstance(response, str)
        assert len(response) > 50, f"Got short response: {response!r}"

        graphml = tmp_dir / "graph_chunk_entity_relation.graphml"
        assert graphml.exists(), f"Expected {graphml} to exist"

        vdb_files = list(tmp_dir.glob("vdb_*.json"))
        assert vdb_files, "No vdb_*.json files emitted"

        # Key-name-agnostic dim verification: walk the JSON and find at least
        # one float-list of length EMBEDDING_DIM. Avoids hard-coding the JSON
        # key name (embedding_dim / dim / nested data[i].embedding) which
        # varies across nano-vectordb schema versions.
        verified_dim_in_file = None
        for vdb_file in vdb_files:
            with open(vdb_file, encoding="utf-8") as f:
                vdb_data = json.load(f)
            if _find_vector_of_dim(vdb_data, EMBEDDING_DIM):
                verified_dim_in_file = vdb_file.name
                break
        assert verified_dim_in_file is not None, (
            f"None of {[f.name for f in vdb_files]} contains a length-"
            f"{EMBEDDING_DIM} float vector - embedding dim contract not "
            f"verified end-to-end"
        )
        _safe_print(f"[Test 3] Verified dim={EMBEDDING_DIM} vector in {verified_dim_in_file}")
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_dryrun_bilingual(tmp_path):
    """Test 4: Bilingual sanity (~3 min, ~$0.10-$0.30).

    Risk #3 early warning: surface Qwen3-0.6B Chinese retrieval quality
    against zh + en queries on the 5-article fixture corpus. Print full
    response excerpts for human review post-test.
    """
    from lightrag import LightRAG, QueryParam

    tmp_dir = tmp_path / f"lightrag_bilingual_{int(time.time())}"
    tmp_dir.mkdir()
    try:
        rag = LightRAG(
            working_dir=str(tmp_dir),
            llm_model_func=make_llm_func(),
            embedding_func=make_embedding_func(),
        )
        await rag.initialize_storages()
        for art in _load_fixtures():
            await rag.ainsert(art)

        zh_t0 = time.time()
        resp_zh = await rag.aquery(
            "LangGraph 与 CrewAI 的对比",
            QueryParam(mode="hybrid"),
        )
        zh_elapsed = time.time() - zh_t0

        en_t0 = time.time()
        resp_en = await rag.aquery(
            "compare LangGraph and CrewAI frameworks",
            QueryParam(mode="hybrid"),
        )
        en_elapsed = time.time() - en_t0

        _safe_print(f"\n[Test 4] ZH query latency: {zh_elapsed:.2f}s")
        _safe_print(f"[Test 4] EN query latency: {en_elapsed:.2f}s")
        _safe_print("\n--- BILINGUAL DRY-RUN ---")
        _safe_print("ZH query response (first 400 chars):")
        _safe_print(resp_zh[:400])
        _safe_print("\nEN query response (first 400 chars):")
        _safe_print(resp_en[:400])
        _safe_print("--- END BILINGUAL DRY-RUN ---")

        assert len(resp_zh) > 50, f"Chinese query returned short response: {resp_zh!r}"
        assert len(resp_en) > 50, f"English query returned short response: {resp_en!r}"
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
