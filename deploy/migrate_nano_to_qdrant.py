#!/usr/bin/env python3
"""Migrate NanoVectorDB JSON data to Qdrant (on_disk, 3072-dim).

Usage: python3 migrate_nano_to_qdrant.py [--qdrant-url http://127.0.0.1:6333]

Reads vdb_entities.json, vdb_chunks.json, vdb_relationships.json from
~/.hermes/omonigraph-vault/lightrag_storage/ and upserts into Qdrant.
"""

import argparse
import base64
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

SUFFIX = "gemini_embedding_2_3072d"
WORKSPACE = "_"
BATCH_SIZE = 256

DATA_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage"

FILES = {
    "entities": "vdb_entities.json",
    "chunks": "vdb_chunks.json",
    "relationships": "vdb_relationships.json",
}


def qdrant_id(raw_key: str) -> str:
    """Deterministic UUID from raw_key, matching LightRAG's compute_mdhash_id_for_qdrant."""
    import hashlib
    hashed = hashlib.sha256((WORKSPACE + raw_key).encode("utf-8")).digest()
    return uuid.UUID(bytes=hashed[:16], version=4).hex


def load_nanovectordb(path: str):
    """Load NanoVectorDB JSON and return (embedding_dim, records, matrix)."""
    print(f"Loading {path}...", flush=True)
    with open(path, "rb") as f:
        raw = json.load(f)

    dim = raw["embedding_dim"]
    records = raw["data"]
    encoded = raw["matrix"]

    # Decode base64 matrix to float32 array
    raw_bytes = base64.b64decode(encoded)
    vectors = np.frombuffer(raw_bytes, dtype=np.float32).reshape(-1, dim)

    assert vectors.shape[0] == len(records), (
        f"Matrix rows ({vectors.shape[0]}) != records ({len(records)})"
    )
    print(f"  dim={dim}, records={len(records)}, matrix={vectors.shape}", flush=True)
    return dim, records, vectors


def validate_vector(v, dim: int, idx: int, rid: str):
    """Validate vector dimension and content."""
    assert len(v) == dim, f"Record {idx} ({rid}): expected {dim}d, got {len(v)}d"
    assert all(math.isfinite(float(x)) for x in v), f"Record {idx} ({rid}): NaN/Inf in vector"


def migrate_file(client, namespace: str, json_path: str):
    """Migrate one NanoVectorDB file to its Qdrant collection."""
    coll = f"lightrag_vdb_{namespace}_{SUFFIX}"
    dim, records, vectors = load_nanovectordb(json_path)

    batch = []
    inserted = 0
    start = time.time()

    for i, rec in enumerate(records):
        rid = rec.get("__id__", rec.get("entity_name", str(i)))

        # Build payload: all record fields except __vector__ (which doesn't exist here)
        # but skip internal NanoVectorDB fields
        payload = {
            "workspace_id": WORKSPACE,
        }
        for k, v in rec.items():
            if k in ("__vector__",):
                continue
            payload[k] = v

        vec = vectors[i]
        validate_vector(vec, dim, i, rid)

        batch.append(models.PointStruct(
            id=qdrant_id(rid),
            vector=vec.tolist(),
            payload=payload,
        ))

        if len(batch) >= BATCH_SIZE:
            client.upsert(coll, points=batch, wait=True)
            inserted += len(batch)
            elapsed = time.time() - start
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  {namespace}: {inserted}/{len(records)} ({rate:.0f} pts/s)", flush=True)
            batch.clear()

    if batch:
        client.upsert(coll, points=batch, wait=True)
        inserted += len(batch)

    elapsed = time.time() - start
    print(f"✓ {namespace}: {inserted} points upserted in {elapsed:.1f}s", flush=True)
    return inserted


def enable_hnsw(client, namespace: str):
    """After migration, update HNSW config to build the index."""
    coll = f"lightrag_vdb_{namespace}_{SUFFIX}"
    print(f"Updating HNSW config for {coll}...", flush=True)
    client.update_collection(
        coll,
        hnsw_config=models.HnswConfigDiff(
            m=16,
            ef_construct=100,
            on_disk=True,
        ),
    )


def wait_for_index(client, namespace: str, expected: int, timeout: int = 600):
    """Poll Qdrant until all vectors are indexed."""
    coll = f"lightrag_vdb_{namespace}_{SUFFIX}"
    start = time.time()
    while True:
        info = client.get_collection(coll)
        points = info.points_count
        indexed = info.indexed_vectors_count
        status = info.status
        print(f"  {coll}: points={points} indexed={indexed} status={status}", flush=True)
        if points >= expected and indexed >= expected:
            print(f"✓ {coll}: fully indexed", flush=True)
            return
        if time.time() - start > timeout:
            print(f"⚠ {coll}: timeout waiting for index", flush=True)
            return
        time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="Migrate NanoVectorDB → Qdrant")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--skip-index", action="store_true", help="Skip HNSW index rebuild at end")
    args = parser.parse_args()

    client = QdrantClient(url=args.qdrant_url, check_compatibility=False)

    total = 0
    for namespace, filename in FILES.items():
        json_path = DATA_DIR / filename
        if not json_path.exists():
            print(f"Skipping {filename}: not found", flush=True)
            continue
        n = migrate_file(client, namespace, str(json_path))
        total += n

    print(f"\n=== Total: {total} points migrated ===", flush=True)

    if not args.skip_index:
        print("\n=== Enabling HNSW indexing (m=16) ===", flush=True)
        for namespace in FILES:
            enable_hnsw(client, namespace)

        print("\n=== Waiting for index build ===", flush=True)
        for namespace in FILES:
            json_path = DATA_DIR / FILES[namespace]
            if not json_path.exists():
                continue
            _, records, _ = load_nanovectordb(str(json_path))
            wait_for_index(client, namespace, len(records))


if __name__ == "__main__":
    main()
