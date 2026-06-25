"""Unit tests for scripts/qdrant_to_nanovdb.py converter.

Pins the on-disk schema contract that Databricks + Hermes (NanoVectorDB
consumers) rely on for hydrate. SC-4 of v1.1.qdrant-migration.

Tests are skip-graceful when qdrant_client is not installed locally so
non-Aliyun CI environments do not block. Aliyun execute-phase has the
package via T5 install (see PLAN.md Wave 2).
"""
from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

# scripts/ is not a package; load the module by file path.
qdrant_client = pytest.importorskip("qdrant_client")
nano_vectordb = pytest.importorskip("nano_vectordb")

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from nano_vectordb import NanoVectorDB
from nano_vectordb.dbs import Float, array_to_buffer_string, load_storage

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "qdrant_to_nanovdb.py"
_spec = importlib.util.spec_from_file_location("qdrant_to_nanovdb", _SCRIPT_PATH)
qdrant_to_nanovdb = importlib.util.module_from_spec(_spec)
sys.modules["qdrant_to_nanovdb"] = qdrant_to_nanovdb
assert _spec.loader is not None
_spec.loader.exec_module(qdrant_to_nanovdb)


_DIM = 8
_COLLECTION = "lightrag_vdb_chunks"


def _seed_collection(client: QdrantClient, n_points: int, dim: int = _DIM) -> list[str]:
    """Create the collection and upsert n_points fixture vectors. Returns the LightRAG ids."""
    if client.collection_exists(_COLLECTION):
        client.delete_collection(_COLLECTION)
    client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )
    lightrag_ids = [f"chunk-{i:04d}" for i in range(n_points)]
    points = []
    for i, lid in enumerate(lightrag_ids):
        vec = (np.arange(dim, dtype=np.float32) + i * 0.01).tolist()
        payload = {
            "id": lid,
            "workspace_id": "test_ws",
            "created_at": 1700000000 + i,
            "content": f"content body {i}",
            "full_doc_id": f"doc-{i:02d}",
            "file_path": f"path/to/file_{i}.md",
        }
        points.append(qmodels.PointStruct(id=i + 1, vector=vec, payload=payload))
    client.upsert(collection_name=_COLLECTION, points=points, wait=True)
    return lightrag_ids


def test_converter_emits_base64_matrix(tmp_path: Path) -> None:
    """SC-4 (4a): output JSON 'matrix' is a base64 string, NOT list-of-lists."""
    client = QdrantClient(":memory:")
    seeded_ids = _seed_collection(client, n_points=5)

    output_path = str(tmp_path / "vdb_chunks.json")
    metrics = qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields={"full_doc_id", "content", "file_path"},
    )

    assert metrics["points_written"] == 5
    assert metrics["dim_observed"] == _DIM

    with open(output_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["embedding_dim"] == _DIM
    assert isinstance(loaded["matrix"], str), "matrix must be a base64 string, not a list"
    base64.b64decode(loaded["matrix"])  # raises if not valid base64
    assert len(loaded["data"]) == 5
    assert loaded["data"][0]["__id__"] in seeded_ids
    assert "full_doc_id" in loaded["data"][0]
    assert "workspace_id" not in loaded["data"][0], "workspace_id must be dropped"
    assert "__vector__" not in loaded["data"][0], "__vector__ must not be in on-disk row"


def test_converter_roundtrip_via_nanovectordb(tmp_path: Path) -> None:
    """SC-4 (4b): NanoVectorDB consumer-side hydrate loads cleanly without TypeError.

    This is the contract that Databricks + Hermes rely on. If the matrix is
    written as list-of-lists, NanoVectorDB.load_storage raises TypeError on
    base64.b64decode([{...}]) — silently breaking SC-11 / SC-6.
    """
    client = QdrantClient(":memory:")
    _seed_collection(client, n_points=5)

    output_path = str(tmp_path / "vdb_chunks.json")
    qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields={"full_doc_id", "content", "file_path"},
    )

    # Real consumer: NanoVectorDB(storage_file=...). MUST NOT raise.
    vdb = NanoVectorDB(embedding_dim=_DIM, storage_file=output_path)
    storage = getattr(vdb, "_NanoVectorDB__storage")
    assert len(storage["data"]) == 5
    assert storage["matrix"].shape == (5, _DIM)
    assert storage["matrix"].dtype == Float


def test_converter_handles_empty_collection(tmp_path: Path) -> None:
    """SC-4 (4c): empty Qdrant collection produces a valid empty NanoVectorDB JSON."""
    client = QdrantClient(":memory:")
    if client.collection_exists(_COLLECTION):
        client.delete_collection(_COLLECTION)
    client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=qmodels.VectorParams(size=_DIM, distance=qmodels.Distance.COSINE),
    )

    output_path = str(tmp_path / "vdb_chunks.json")
    metrics = qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields=set(),
    )

    assert metrics["points_written"] == 0
    # Real consumer hydrates cleanly off the empty file.
    vdb = NanoVectorDB(embedding_dim=_DIM, storage_file=output_path)
    storage = getattr(vdb, "_NanoVectorDB__storage")
    assert len(storage["data"]) == 0
    assert storage["matrix"].shape == (0, _DIM)


def test_main_handles_missing_collections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-4 (4e): main() writes valid empty JSON when Qdrant has no collections.

    Pre-Wave-3 / pre-first-ingest window: kb-api boots Qdrant-on-empty, but
    no collection exists yet (first upsert creates them). The systemd timer
    fires every 6h regardless — so main() must produce valid empty JSON
    instead of returning 1, else the timer stays in failed state until
    reingest lands. Regression guard for the T8 PLAN-defect class B fix.

    Stubs `QdrantClient(url=...)` to return an in-memory client (`":memory:"`)
    so the test does not require a live Qdrant server.
    """
    monkeypatch.setenv("LIGHTRAG_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIGRAPH_EMBEDDING_DIM", str(_DIM))

    def _in_memory_factory(url: str = "", **_: object) -> QdrantClient:
        return QdrantClient(":memory:")

    monkeypatch.setattr("qdrant_client.QdrantClient", _in_memory_factory, raising=True)

    rc = qdrant_to_nanovdb.main()
    assert rc == 0, "main() must return 0 when collections are missing (skip-write-empty)"

    for namespace in ("chunks", "entities", "relationships"):
        out = tmp_path / f"vdb_{namespace}.json"
        assert out.exists(), f"vdb_{namespace}.json missing"
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["embedding_dim"] == _DIM
        assert loaded["data"] == []
        assert isinstance(loaded["matrix"], str)
        # Real consumer hydrate must succeed off the empty JSON.
        vdb = NanoVectorDB(embedding_dim=_DIM, storage_file=str(out))
        storage = getattr(vdb, "_NanoVectorDB__storage")
        assert len(storage["data"]) == 0


def test_converter_dimension_mismatch_raises(tmp_path: Path) -> None:
    """SC-4 (4d) / HT-7: vector dim ≠ embedding_dim raises ValueError."""
    client = QdrantClient(":memory:")
    _seed_collection(client, n_points=3, dim=_DIM)  # vectors are dim=8

    output_path = str(tmp_path / "vdb_chunks.json")
    with pytest.raises(ValueError, match="qdrant_snapshot_dim_mismatch"):
        qdrant_to_nanovdb.export_collection_to_nanovdb(
            client=client,
            collection_name=_COLLECTION,
            output_path=output_path,
            embedding_dim=3072,  # mismatch — vectors are 8-dim
            meta_fields=set(),
        )
    assert not (tmp_path / "vdb_chunks.json").exists(), "must not write on dim error"


# ---------------------------------------------------------------------------
# ISSUES #41 streaming-refactor behavior anchors (arx-4 Plan 01 Task 2).
# These pin the on-disk bytes contract through nano_vectordb.load_storage so a
# future converter change that breaks the consumer (Databricks/Hermes) fails CI.
# ---------------------------------------------------------------------------


def _scroll_vectors_in_order(client: QdrantClient, dim: int) -> list[list[float]]:
    """Replay the converter's exact scroll (same kwargs) to capture vectors in
    the authoritative scroll order — the reference sequence the old
    full-accumulation path (`vectors.append(list(vec))`) would have built."""
    out: list[list[float]] = []
    next_offset = None
    while True:
        page, next_offset = client.scroll(
            collection_name=_COLLECTION,
            limit=500,
            offset=next_offset,
            with_payload=True,
            with_vectors=True,
        )
        for point in page:
            out.append(list(point.vector))
        if next_offset is None:
            break
    return out


def test_streaming_matrix_byte_identical_to_reference(tmp_path: Path) -> None:
    """Plan 01 T2 byte-identity: the streamed matrix base64 EXACTLY equals the
    reference full-accumulation path (`array_to_buffer_string(np.array(...))`)
    built from the SAME scroll order.

    The on-disk bytes are a contract — the streaming refactor must produce the
    identical blob the old per-row-list + np.array path produced, else
    consumers silently corrupt. Locks scroll order + row-major float32 layout.
    """
    client = QdrantClient(":memory:")
    n_points = 7
    _seed_collection(client, n_points=n_points)

    # Reference = the OLD path: collect vectors in scroll order, then
    # array_to_buffer_string(np.array(...)). Both old + new use this same
    # scroll, so byte-identity must hold regardless of seed-vs-scroll order.
    scrolled = _scroll_vectors_in_order(client, _DIM)
    expected_matrix_b64 = array_to_buffer_string(np.array(scrolled, dtype=Float))

    output_path = str(tmp_path / "vdb_chunks.json")
    qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields={"full_doc_id", "content", "file_path"},
    )

    with open(output_path, "r", encoding="utf-8") as f:
        written = json.load(f)

    assert written["matrix"] == expected_matrix_b64, (
        "streamed matrix base64 must be byte-identical to the reference "
        "array_to_buffer_string(np.array(vectors)) path on the same scroll order"
    )

    # And it must reshape correctly through the REAL consumer loader.
    loaded = load_storage(output_path)
    assert loaded["matrix"].shape == (n_points, _DIM)
    assert loaded["matrix"].dtype == Float
    assert len(loaded["data"]) == n_points
    # Row-major scroll order preserved: row i must equal the i-th scrolled vector.
    np.testing.assert_array_equal(
        loaded["matrix"][0], np.array(scrolled[0], dtype=Float)
    )
    np.testing.assert_array_equal(
        loaded["matrix"][-1], np.array(scrolled[-1], dtype=Float)
    )


def test_streaming_load_storage_schema_and_dropped_fields(tmp_path: Path) -> None:
    """Plan 01 T2 schema roundtrip: load_storage yields (K, D) matrix, K data
    rows carrying __id__ + __created_at__ + the meta_fields, workspace_id and
    __vector__ dropped."""
    client = QdrantClient(":memory:")
    seeded_ids = _seed_collection(client, n_points=4)

    output_path = str(tmp_path / "vdb_chunks.json")
    qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields={"full_doc_id", "content", "file_path"},
    )

    loaded = load_storage(output_path)
    assert loaded["matrix"].shape == (4, _DIM)
    assert len(loaded["data"]) == 4
    row = loaded["data"][0]
    assert row["__id__"] in seeded_ids
    assert "__created_at__" in row
    assert "full_doc_id" in row and "content" in row and "file_path" in row
    assert "workspace_id" not in row, "workspace_id must be dropped"
    assert "__vector__" not in row, "__vector__ must not be in on-disk row"


def test_streaming_empty_collection_load_storage(tmp_path: Path) -> None:
    """Plan 01 T2 empty case: N=0 → matrix '' that load_storage reshapes to
    (0, D) without error (preserves the empty-collection behavior)."""
    client = QdrantClient(":memory:")
    if client.collection_exists(_COLLECTION):
        client.delete_collection(_COLLECTION)
    client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=qmodels.VectorParams(size=_DIM, distance=qmodels.Distance.COSINE),
    )

    output_path = str(tmp_path / "vdb_chunks.json")
    qdrant_to_nanovdb.export_collection_to_nanovdb(
        client=client,
        collection_name=_COLLECTION,
        output_path=output_path,
        embedding_dim=_DIM,
        meta_fields=set(),
    )

    with open(output_path, "r", encoding="utf-8") as f:
        written = json.load(f)
    assert written["matrix"] == "", "empty collection → empty matrix string"

    loaded = load_storage(output_path)
    assert loaded["matrix"].shape == (0, _DIM)
    assert len(loaded["data"]) == 0


def test_converter_count_roundtrip_mismatch_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 01 T2 (Test 4): the qdrant_snapshot_roundtrip_mismatch RuntimeError
    survives the streaming refactor — if Qdrant's authoritative count disagrees
    with the scrolled row count, we must NOT write a truncated snapshot."""
    client = QdrantClient(":memory:")
    _seed_collection(client, n_points=5)

    # Force client.count() to lie (report 99 != 5 scrolled) so the guard fires.
    class _FakeCount:
        count = 99

    monkeypatch.setattr(
        client, "count", lambda *a, **k: _FakeCount(), raising=True
    )

    output_path = str(tmp_path / "vdb_chunks.json")
    with pytest.raises(RuntimeError, match="qdrant_snapshot_roundtrip_mismatch"):
        qdrant_to_nanovdb.export_collection_to_nanovdb(
            client=client,
            collection_name=_COLLECTION,
            output_path=output_path,
            embedding_dim=_DIM,
            meta_fields=set(),
        )
    assert not (tmp_path / "vdb_chunks.json").exists(), "must not write on count mismatch"
