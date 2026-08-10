#!/usr/bin/env python3
"""Bounded-memory REST canary for relationships migration.

Reads only the first N records and corresponding matrix rows from the
NanoVectorDB file through mmap. It never json.loads the whole file and never
builds a full PointStruct list.
"""
import argparse
import base64
import hashlib
import json
import mmap
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

WORKSPACE = "_"
COLLECTION = "lightrag_vdb_relationships_gemini_embedding_2_3072d"
DATA_PATH = Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage" / "vdb_relationships.json"


def point_id(raw_key: str) -> str:
    digest = hashlib.sha256((WORKSPACE + raw_key).encode("utf-8")).digest()
    return uuid.UUID(bytes=digest[:16], version=4).hex


def json_object_end(data: mmap.mmap, start: int) -> int:
    """Return the exclusive end offset of a JSON object/array."""
    opener = data[start]
    if opener not in (ord("{"), ord("[")):
        raise ValueError(f"expected JSON object/array at offset {start}")
    closer = ord("}") if opener == ord("{") else ord("]")
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(data)):
        char = data[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == ord("\\"):
                escaped = True
            elif char == ord('"'):
                in_string = False
            continue
        if char == ord('"'):
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return pos + 1
        elif char in (ord("{"), ord("[")):
            depth += 1
        elif char in (ord("}"), ord("]")):
            depth -= 1
    raise ValueError("unterminated JSON value")


def first_records(data: mmap.mmap, limit: int) -> list[dict]:
    marker = b'"data"'
    key_pos = data.find(marker)
    if key_pos < 0:
        raise ValueError("top-level data key not found")
    array_start = data.find(b"[", key_pos + len(marker))
    if array_start < 0:
        raise ValueError("data array not found")

    records = []
    pos = array_start + 1
    while len(records) < limit:
        while pos < len(data) and data[pos] in b" \t\r\n,":
            pos += 1
        if pos >= len(data) or data[pos] == ord("]"):
            break
        end = json_object_end(data, pos)
        records.append(json.loads(data[pos:end]))
        pos = end
    return records


def first_matrix_rows(data: mmap.mmap, rows: int, dim: int) -> np.ndarray:
    marker = b'"matrix"'
    key_pos = data.rfind(marker)
    if key_pos < 0:
        raise ValueError("top-level matrix key not found")
    colon = data.find(b":", key_pos + len(marker))
    quote = data.find(b'"', colon + 1)
    if colon < 0 or quote < 0:
        raise ValueError("matrix string not found")

    byte_count = rows * dim * 4
    encoded_count = ((byte_count + 2) // 3) * 4
    encoded = bytes(data[quote + 1 : quote + 1 + encoded_count])
    decoded = base64.b64decode(encoded)
    matrix = np.frombuffer(decoded[:byte_count], dtype=np.float32)
    return matrix.reshape(rows, dim)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    with DATA_PATH.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        records = first_records(data, args.limit)
        if not records:
            raise RuntimeError("no records found")
        dim = json.loads(data[data.find(b"embedding_dim") : data.find(b"embedding_dim") + 80].split(b":", 1)[1].split(b",", 1)[0])
        vectors = first_matrix_rows(data, len(records), dim)

    points = []
    seen = set()
    for index, record in enumerate(records):
        raw_key = record.get("__id__", record.get("entity_name", str(index)))
        pid = point_id(raw_key)
        if pid in seen:
            continue
        seen.add(pid)
        vector = vectors[index].tolist()
        if len(vector) != dim or not np.isfinite(vectors[index]).all():
            raise ValueError(f"invalid vector at source index {index}: len={len(vector)}")
        payload = {"workspace_id": WORKSPACE, **record}
        points.append(models.PointStruct(id=pid, vector=vector, payload=payload))

    print(f"source_records={len(records)} unique_canary_points={len(points)} dim={dim}", flush=True)
    client = QdrantClient(url="http://127.0.0.1:6333", timeout=120, check_compatibility=False)
    for start in range(0, len(points), args.batch_size):
        batch = points[start : start + args.batch_size]
        result = client.upsert(COLLECTION, points=batch, wait=True)
        print(f"upserted={start + len(batch)}/{len(points)} status={result.status}", flush=True)

    exact = client.count(collection_name=COLLECTION, exact=True).count
    print(f"qdrant_exact_count_after_canary={exact}", flush=True)


if __name__ == "__main__":
    main()
