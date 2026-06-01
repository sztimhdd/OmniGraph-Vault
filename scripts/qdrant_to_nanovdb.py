"""Convert Qdrant collections to nano-vectordb on-disk JSON snapshots.

Bridges the v1.1.qdrant-migration two-station model:
  - Aliyun writes/reads Qdrant docker (127.0.0.1:6333, mmap-backed)
  - Databricks + Hermes read NanoVectorDBStorage from `vdb_*.json` snapshots

This script scrolls each Qdrant collection, transforms each point's
payload + vector into the exact on-disk schema NanoVectorDB expects, and
writes `vdb_chunks.json` / `vdb_entities.json` / `vdb_relationships.json`
into ``$LIGHTRAG_STORAGE_DIR``. Triggered every 6h by
``deploy/aliyun/systemd/qdrant-snapshot.{service,timer}``.

Schema reference (verified against installed nano_vectordb 0.0.4.x at
``venv/Lib/site-packages/nano_vectordb/dbs.py``):

    {
      "embedding_dim": <int>,
      "data": [{"__id__": <str>, "__created_at__": <int>, ...meta_fields}, ...],
      "matrix": "<base64-encoded float32 buffer string>"
    }

The matrix is **NOT** a list-of-lists — list-of-lists silently corrupts
NanoVectorDB load with TypeError on the consumer side. See PLAN.md T2
for the full schema contract and rationale.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# nano_vectordb is the on-disk JSON authority — use its public helper for
# matrix base64 encoding so future nano_vectordb upgrades remain compatible.
from nano_vectordb.dbs import Float, array_to_buffer_string  # type: ignore[import]

logger = logging.getLogger("qdrant_to_nanovdb")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)


# Per LightRAG `lightrag/lightrag.py:716/722/728`. Listed verbatim so any
# upstream meta_fields drift surfaces here, not in a silent producer/consumer
# schema mismatch on Databricks/Hermes.
META_FIELDS_BY_NAMESPACE: dict[str, set[str]] = {
    "chunks": {"full_doc_id", "content", "file_path"},
    "entities": {"entity_name", "source_id", "content", "file_path"},
    "relationships": {"src_id", "tgt_id", "source_id", "content", "file_path"},
}

# Maps the Qdrant collection name to the on-disk vdb_<n>.json filename
# LightRAG NanoVectorDBStorage expects. Collection naming follows
# QdrantVectorDBStorage's `final_namespace = f"lightrag_vdb_{namespace}"`
# (qdrant_impl.py:450) when no model_suffix is set.
NAMESPACE_TO_QDRANT_COLLECTION: dict[str, str] = {
    "chunks": "lightrag_vdb_chunks",
    "entities": "lightrag_vdb_entities",
    "relationships": "lightrag_vdb_relationships",
}


def _build_data_row(payload: dict[str, Any], meta_fields: set[str]) -> dict[str, Any]:
    """Translate a Qdrant payload into a NanoVectorDB on-disk `data[]` row.

    Qdrant payload (qdrant_impl.py:637-643): {id, workspace_id, created_at, ...meta_fields}.
    NanoVectorDB row (dbs.py + nano_vector_db_impl.py:108-115): {__id__, __created_at__, ...meta_fields}.
    `workspace_id` is dropped (NanoVectorDB has no workspace concept).
    `__vector__` is NOT included (nano_vectordb strips it pre-save at dbs.py:101,112).
    `vector` (the optional Float16+zlib+Base64 compressed copy NanoVectorDBStorage
    adds for storage optimization) is NOT included either — it is stripped from
    query results at nano_vector_db_impl.py:165 and recomputing it is dead weight.
    """
    row: dict[str, Any] = {
        "__id__": payload["id"],
        "__created_at__": int(payload.get("created_at", 0)),
    }
    for k in meta_fields:
        if k in payload:
            row[k] = payload[k]
    return row


def export_collection_to_nanovdb(
    client: Any,
    collection_name: str,
    output_path: str,
    embedding_dim: int = 3072,
    meta_fields: set[str] | None = None,
    scroll_batch: int = 500,
) -> dict[str, Any]:
    """Scroll a Qdrant collection and write a NanoVectorDB-loadable JSON file.

    Args:
        client: An initialized ``qdrant_client.QdrantClient``.
        collection_name: Qdrant collection name (e.g. ``lightrag_vdb_chunks``).
        output_path: Absolute path to write the ``vdb_<n>.json`` file.
        embedding_dim: Expected vector dimensionality (default 3072 = Vertex Gemini).
        meta_fields: Set of payload keys to carry over (per LightRAG namespace).
            If ``None``, all non-LightRAG-special keys in payload are kept.
        scroll_batch: Per-scroll page size (Qdrant default-OK at 500).

    Returns:
        ``{"points_written": int, "dim_observed": int, "wall_s": float}``.

    Raises:
        ValueError: vector dim observed ≠ ``embedding_dim`` (HT-7).
        RuntimeError: ``len(data)`` ≠ ``client.count(collection_name).count``.
    """
    t0 = time.monotonic()
    fields = meta_fields if meta_fields is not None else set()

    rows: list[dict[str, Any]] = []
    vectors: list[list[float]] = []

    next_offset: Any = None
    while True:
        page, next_offset = client.scroll(
            collection_name=collection_name,
            limit=scroll_batch,
            offset=next_offset,
            with_payload=True,
            with_vectors=True,
        )
        for point in page:
            payload = point.payload or {}
            row = _build_data_row(payload, fields)
            rows.append(row)
            vec = point.vector
            if vec is None:
                raise RuntimeError(
                    f"Qdrant point id={point.id} returned vector=None "
                    "(scroll with_vectors=True did not yield a vector)"
                )
            vectors.append(list(vec))
        if next_offset is None:
            break

    dim_observed = len(vectors[0]) if vectors else embedding_dim
    if vectors and dim_observed != embedding_dim:
        raise ValueError(
            f"qdrant_snapshot_dim_mismatch collection={collection_name} "
            f"expected={embedding_dim} observed={dim_observed} "
            f"points={len(vectors)} (HT-7)"
        )

    # Roundtrip smoke: compare against Qdrant's authoritative count.
    qdrant_count = client.count(collection_name=collection_name).count
    if qdrant_count != len(rows):
        raise RuntimeError(
            f"qdrant_snapshot_roundtrip_mismatch collection={collection_name} "
            f"qdrant_count={qdrant_count} scrolled={len(rows)}"
        )

    # Build matrix in nano_vectordb's on-disk format: a single base64-encoded
    # float32 buffer. Empty matrix is represented as a 0-row, embedding_dim-col
    # array — array_to_buffer_string returns an empty string, which loads
    # cleanly via NanoVectorDB.
    if vectors:
        matrix_arr = np.array(vectors, dtype=Float)
    else:
        matrix_arr = np.zeros((0, embedding_dim), dtype=Float)
    matrix_b64 = array_to_buffer_string(matrix_arr)

    nano_format = {
        "embedding_dim": embedding_dim,
        "data": rows,
        "matrix": matrix_b64,
    }

    # Atomic write: tmp + os.replace. os.replace replaces symlinks atomically
    # on POSIX, which is intentional — see PLAN.md T6 + L1 rollback notes for
    # the symlink invalidation contract.
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(nano_format, f, ensure_ascii=False)
    os.replace(tmp_path, output_path)

    wall_s = time.monotonic() - t0
    metrics = {
        "points_written": len(rows),
        "dim_observed": dim_observed,
        "wall_s": round(wall_s, 3),
    }
    logger.info(
        "qdrant_snapshot_file collection=%s points=%d dim=%d wall_s=%.3f",
        collection_name,
        metrics["points_written"],
        metrics["dim_observed"],
        metrics["wall_s"],
    )
    return metrics


def main() -> int:
    """Entry point for the systemd one-shot.

    Reads ``LIGHTRAG_STORAGE_DIR`` (default ``/root/.hermes/omonigraph-vault/lightrag_storage``)
    and ``QDRANT_URL`` (default ``http://127.0.0.1:6333``); converts each of
    the 3 LightRAG namespaces. Returns 0 on full success, 1 on any failure.
    """
    storage_dir = Path(
        os.environ.get(
            "LIGHTRAG_STORAGE_DIR",
            "/root/.hermes/omonigraph-vault/lightrag_storage",
        )
    )
    qdrant_url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    embedding_dim = int(os.environ.get("OMNIGRAPH_EMBEDDING_DIM", "3072"))

    # Imported here so the module remains importable without qdrant_client
    # (unit tests use ``QdrantClient(":memory:")`` via importorskip).
    from qdrant_client import QdrantClient  # type: ignore[import]

    storage_dir.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(url=qdrant_url)

    t_total = time.monotonic()
    files_written = 0
    for namespace, qdrant_collection in NAMESPACE_TO_QDRANT_COLLECTION.items():
        output_path = str(storage_dir / f"vdb_{namespace}.json")
        try:
            export_collection_to_nanovdb(
                client=client,
                collection_name=qdrant_collection,
                output_path=output_path,
                embedding_dim=embedding_dim,
                meta_fields=META_FIELDS_BY_NAMESPACE[namespace],
            )
            files_written += 1
        except Exception as exc:
            logger.error(
                "qdrant_snapshot_file_failed collection=%s err=%s",
                qdrant_collection,
                exc,
            )
            return 1

    total_wall_s = round(time.monotonic() - t_total, 3)
    logger.warning(
        "qdrant_snapshot_ok files_written=%d total_wall_s=%.3f",
        files_written,
        total_wall_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
