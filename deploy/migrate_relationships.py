#!/usr/bin/env python3
"""Re-run ONLY relationships migration with wait=True, verifying dedup."""
import json, base64, time, hashlib, uuid, math, sys
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

SUFFIX = "gemini_embedding_2_3072d"
WORKSPACE = "_"
BATCH_SIZE = 256
DATA_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage"

def qdrant_id(raw_key: str) -> str:
    hashed = hashlib.sha256((WORKSPACE + raw_key).encode("utf-8")).digest()
    return uuid.UUID(bytes=hashed[:16], version=4).hex

def validate_point(point, dim):
    if isinstance(point.vector, dict):
        raise ValueError(f"named vector: {list(point.vector.keys())}")
    if point.vector is None or len(point.vector) != dim:
        raise ValueError(f"invalid dim: {len(point.vector) if point.vector else 0}")

# Load relationships
path = DATA_DIR / "vdb_relationships.json"
print(f"Loading {path}...", flush=True)
with open(path, "rb") as f:
    raw = json.load(f)

records = raw["data"]
dim = raw["embedding_dim"]
vectors = np.frombuffer(base64.b64decode(raw["matrix"]), dtype=np.float32).reshape(-1, dim)
print(f"records={len(records)}, matrix={vectors.shape}", flush=True)

# Track unique IDs to skip duplicates
seen_ids = set()
deduped = []

for i, rec in enumerate(records):
    rid = rec.get("__id__", rec.get("entity_name", str(i)))
    pid = qdrant_id(rid)
    if pid in seen_ids:
        continue
    seen_ids.add(pid)
    
    payload = {"workspace_id": WORKSPACE}
    for k, v in rec.items():
        payload[k] = v
    
    vec = vectors[i]
    assert len(vec) == dim
    assert all(math.isfinite(float(x)) for x in vec)
    
    deduped.append(models.PointStruct(id=pid, vector=vec.tolist(), payload=payload))

print(f"unique points to upsert: {len(deduped)} (skipped {len(records)-len(deduped)} dupes)", flush=True)

# Connect
client = QdrantClient(url="http://127.0.0.1:6333", timeout=120, check_compatibility=False)
coll = f"lightrag_vdb_relationships_{SUFFIX}"

# Upsert in batches with wait=True
start = time.time()
inserted = 0
for batch_idx in range(0, len(deduped), BATCH_SIZE):
    batch = deduped[batch_idx:batch_idx + BATCH_SIZE]
    
    # Validate each point
    for p in batch:
        validate_point(p, dim)
    
    client.upsert(coll, points=batch, wait=True)
    inserted += len(batch)
    elapsed = time.time() - start
    print(f"  {inserted}/{len(deduped)} ({inserted/elapsed:.0f} pts/s)", flush=True)

elapsed = time.time() - start
print(f"✓ Done: {inserted} points in {elapsed:.1f}s", flush=True)

# Verify
time.sleep(5)
info = client.get_collection(coll)
print(f"Qdrant count: {info.points_count} / expected {len(deduped)}", flush=True)
