#!/usr/bin/env python3
"""Migrate NanoVectorDB JSON data to Qdrant (on_disk, 3072-dim).
v2: use gRPC, larger batches, wait=False, tmux-safe logging.

Usage: python3 migrate_nano_to_qdrant_v2.py [--qdrant-url http://127.0.0.1:6333]
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
BATCH_SIZE = 512

DATA_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage"

FILES = {
    "entities": "vdb_entities.json",
    "chunks": "vdb_chunks.json",
    "relationships": "vdb_relationships.json",
}


def qdrant_id(raw_key: str) -> str:
    """Deterministic UUID matching LightRAG's compute_mdhash_id_for_qdrant."""
    import hashlib
    hashed = hashlib.sha256((WORKSPACE + raw_key).encode("utf-8")).digest()
    return uuid.UUID(bytes=hashed[:16], version=4).hex


def load_nanovectordb(path: str):
    """Load NanoVectorDB JSON and return (embedding_dim, records, matrix)."""
    print(f"[{time.strftime('%H:%M:%S')}] Loading {path}...", flush=True)
    with open(path, "rb") as f:
        raw = json.load(f)

    dim = raw["embedding_dim"]
    records = raw["data"]
    encoded = raw["matrix"]

    raw_bytes = base64.b64decode(encoded)
    vectors = np.frombuffer(raw_bytes, dtype=np.float32).reshape(-1, dim)

    assert vectors.shape[0] == len(records), (
        f"Matrix rows ({vectors.shape[0]}) != records ({len(records)})"
    )
    print(f"  dim={dim}, records={len(records)}, matrix={vectors.shape}", flush=True)
    return dim, records, vectors


def migrate_file(client, namespace: str, json_path: str):
    coll = f"lightrag_vdb_{namespace}_{SUFFIX}"
    dim, records, vectors = load_nanovectordb(json_path)

    batch = []
    inserted = 0
    start = time.time()

    for i, rec in enumerate(records):
        rid = rec.get("__id__", rec.get("entity_name", str(i)))
        payload = {"workspace_id": WORKSPACE}
        for k, v in rec.items():
            payload[k] = v

        vec = vectors[i]
        assert len(vec) == dim, f"Record {i} ({rid}): expected {dim}d, got {len(vec)}d"
        assert all(math.isfinite(float(x)) for x in vec), f"Record {i} ({rid}): NaN/Inf"

        batch.append(models.PointStruct(
            id=qdrant_id(rid),
            vector=vec.tolist(),
            payload=payload,
        ))

        if len(batch) >= BATCH_SIZE:
            client.upsert(coll, points=batch, wait=False)
            inserted += len(batch)
            elapsed = time.time() - start
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  [{time.strftime('%H:%M:%S')}] {namespace}: {inserted}/{len(records)} ({rate:.0f} pts/s)", flush=True)
            batch.clear()

    if batch:
        client.upsert(coll, points=batch, wait=False)
        inserted += len(batch)

    elapsed = time.time() - start
    print(f"[{time.strftime('%H:%M:%S')}] ✓ {namespace}: submitted {inserted} points in {elapsed:.1f}s", flush=True)
    return inserted


def verify_counts(client):
    """After all submits, wait and verify Qdrant counts."""
    targets = {"entities": 94557, "chunks": 6198, "relationships": 112037}
    print("\n=== Verifying counts ===", flush=True)
    for ns, expected in targets.items():
        coll = f"lightrag_vdb_{ns}_{SUFFIX}"
        # Wait a moment for async writes to settle
        time.sleep(5)
        info = client.get_collection(coll)
        actual = info.points_count
        ok = "✓" if actual == expected else "✗"
        print(f"{ok} {ns}: {actual}/{expected}", flush=True)
    print("")


def enable_hnsw(client, namespace: str):
    coll = f"lightrag_vdb_{namespace}_{SUFFIX}"
    print(f"Updating HNSW config for {coll}...", flush=True)
    client.update_collection(
        coll,
        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100, on_disk=True),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    client = QdrantClient(
        url=args.qdrant_url,
        prefer_grpc=True,
        grpc_port=6334,
        timeout=120,
        check_compatibility=False,
    )

    total = 0
    for namespace, filename in FILES.items():
        json_path = DATA_DIR / filename
        if not json_path.exists():
            print(f"Skipping {filename}: not found", flush=True)
            continue
        n = migrate_file(client, namespace, str(json_path))
        total += n

    print(f"\n=== Total submitted: {total} points ===", flush=True)

    if not args.skip_verify:
        verify_counts(client)


if __name__ == "__main__":
    main()
