#!/usr/bin/env python3
"""Diagnose why Qdrant rejects ~15% of upserted points with 'expected dim: 3072, got 0'.
Run this on the new machine after migration data.
"""
import json, base64, sys
from pathlib import Path

import numpy as np

SUFFIX = "gemini_embedding_2_3072d"
WORKSPACE = "_"
DATA_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage"

FILES = {
    "entities": "vdb_entities.json",
    "chunks": "vdb_chunks.json",
    "relationships": "vdb_relationships.json",
}

def qdrant_id(raw_key: str) -> str:
    import hashlib, uuid
    hashed = hashlib.sha256((WORKSPACE + raw_key).encode("utf-8")).digest()
    return uuid.UUID(bytes=hashed[:16], version=4).hex

for namespace, filename in FILES.items():
    path = DATA_DIR / filename
    print(f"\n=== {namespace} ===")
    
    with open(path, "rb") as f:
        raw = json.load(f)
    
    records = raw["data"]
    dim = raw["embedding_dim"]
    vectors = np.frombuffer(base64.b64decode(raw["matrix"]), dtype=np.float32).reshape(-1, dim)
    
    print(f"records: {len(records)}, matrix shape: {vectors.shape}")
    assert vectors.shape[0] == len(records)
    
    # 1. Check for legacy __vector__ field in records
    has_vec = [i for i, r in enumerate(records) if "__vector__" in r]
    empty_vec = [i for i in has_vec if len(records[i]["__vector__"]) == 0]
    nonempty_vec = [i for i in has_vec if len(records[i]["__vector__"]) > 0]
    print(f"records with __vector__ field: {len(has_vec)}")
    print(f"  of which empty __vector__: {len(empty_vec)}")
    print(f"  of which non-empty __vector__: {len(nonempty_vec)}")
    
    # 2. Check vector quality
    finite_rows = np.isfinite(vectors).all(axis=1)
    zero_rows = np.all(vectors == 0, axis=1)
    print(f"non-finite vector rows: {int((~finite_rows).sum())}")
    print(f"all-zero vector rows: {int(zero_rows.sum())}")
    
    # 3. Check for ID collisions
    raw_keys = [r.get("__id__", r.get("entity_name", str(i))) for i, r in enumerate(records)]
    point_ids = [qdrant_id(k) for k in raw_keys]
    from collections import Counter
    dup_keys = [k for k, c in Counter(raw_keys).items() if c > 1]
    dup_ids = [pid for pid, c in Counter(point_ids).items() if c > 1]
    print(f"unique raw keys: {len(set(raw_keys))}")
    print(f"unique point ids: {len(set(point_ids))}")
    if dup_keys:
        print(f"  WARNING: {len(dup_keys)} duplicate raw keys (e.g. {dup_keys[:3]})")
    if dup_ids:
        print(f"  WARNING: {len(dup_ids)} duplicate point IDs")
    
    # 4. If empty_vec found, check matrix at those positions
    if empty_vec:
        n_sample = min(3, len(empty_vec))
        for idx in empty_vec[:n_sample]:
            i = int(idx)
            row = vectors[i]
            print(f"  empty_vec sample [{i}]: id={records[i].get('__id__','?')[:30]}...")
            print(f"    matrix row shape: {row.shape}, first 8 vals: {row[:8].tolist()}")
            print(f"    norm: {float(np.linalg.norm(row)):.4f}, all_zero: {bool(np.allclose(row, 0))}")
    else:
        # 5. If NO legacy field — check possible wait=False / batch.clear corruption
        # by examining if batches might have been sent with wrong content
        print(f"  No legacy __vector__ field found in any record")
        print(f"  Root cause likely NOT in field precedence")