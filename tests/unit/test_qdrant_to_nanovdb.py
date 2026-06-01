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
from nano_vectordb.dbs import Float

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
