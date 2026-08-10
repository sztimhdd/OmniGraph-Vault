#!/usr/bin/env python3
"""Bounded-memory, idempotent relationships migration via REST.

The source file is memory-mapped, not json.load'ed. Records are parsed one at
a time; matrix bytes are decoded only for the current batch. Duplicate
LightRAG IDs are skipped before upsert. REST + wait=True is intentional:
Qdrant v1.11.5 rejects this client's gRPC vector encoding.
"""
import argparse
import base64
import hashlib
import json
import mmap
import sys
import time
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


def locate_data_array(data: mmap.mmap) -> int:
    key_pos = data.find(b'"data"')
    if key_pos < 0:
        raise ValueError("top-level data key not found")
    array_start = data.find(b"[", key_pos + 6)
    if array_start < 0:
        raise ValueError("data array not found")
    return array_start + 1


def locate_matrix_string(data: mmap.mmap) -> int:
    key_pos = data.rfind(b'"matrix"')
    if key_pos < 0:
        raise ValueError("top-level matrix key not found")
    colon = data.find(b":", key_pos + 8)
    quote = data.find(b'"', colon + 1)
    if colon < 0 or quote < 0:
        raise ValueError("matrix string not found")
    return quote + 1


def read_embedding_dim(data: mmap.mmap) -> int:
    key_pos = data.find(b'"embedding_dim"')
    colon = data.find(b":", key_pos)
    end = data.find(b",", colon)
    return int(data[colon + 1 : end].strip())


def decode_batch(data: mmap.mmap, matrix_start: int, start_index: int, rows: int, dim: int) -> np.ndarray:
    row_bytes = dim * 4
    if row_bytes % 3:
        raise ValueError("matrix row byte length is not base64-aligned")
    chars_per_row = row_bytes // 3 * 4
    encoded_start = matrix_start + start_index * chars_per_row
    encoded_end = encoded_start + rows * chars_per_row
    decoded = base64.b64decode(bytes(data[encoded_start:encoded_end]))
    expected = rows * row_bytes
    if len(decoded) != expected:
        raise ValueError(f"decoded matrix bytes={len(decoded)} expected={expected}")
    return np.frombuffer(decoded, dtype=np.float32).reshape(rows, dim)


def flush_batch(client, data, matrix_start, records, start_index, dim, seen, stats, dry_run=False):
    vectors = decode_batch(data, matrix_start, start_index, len(records), dim)
    points = []
    for offset, record in enumerate(records):
        stats["source_records"] += 1
        raw_key = record.get("__id__", record.get("entity_name", str(start_index + offset)))
        pid = point_id(raw_key)
        if pid in seen:
            stats["duplicates"] += 1
            continue
        seen.add(pid)
        vector = vectors[offset]
        if vector.size != dim or not np.isfinite(vector).all():
            raise ValueError(f"invalid vector source_index={start_index + offset} id={raw_key}")
        payload = dict(record)
        payload["workspace_id"] = WORKSPACE
        points.append(models.PointStruct(id=pid, vector=vector.tolist(), payload=payload))

    if not points or dry_run:
        stats["submitted_unique"] += len(points)
        stats["batches"] += 1
        return
    result = client.upsert(COLLECTION, points=points, wait=True)
    if str(result.status).lower().endswith("completed") is False:
        raise RuntimeError(f"upsert status not completed: {result}")
    stats["submitted_unique"] += len(points)
    stats["batches"] += 1
    print(
        f"batch source={start_index + len(records)}/{stats['source_records']} "
        f"unique={stats['submitted_unique']} duplicates={stats['duplicates']} "
        f"status={result.status}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise ValueError("batch size must be positive")

    client = QdrantClient(url="http://127.0.0.1:6333", timeout=120, check_compatibility=False)
    seen = set()
    stats = {"source_records": 0, "duplicates": 0, "submitted_unique": 0, "batches": 0}
    started = time.time()

    with DATA_PATH.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        dim = read_embedding_dim(data)
        data_pos = locate_data_array(data)
        matrix_start = locate_matrix_string(data)
        print(f"file={DATA_PATH} dim={dim} batch_size={args.batch_size}", flush=True)

        batch = []
        batch_start = data_pos
        source_index = 0
        while True:
            while data_pos < len(data) and data[data_pos] in b" \t\r\n,":
                data_pos += 1
            if data_pos >= len(data) or data[data_pos] == ord("]"):
                break
            end = json_object_end(data, data_pos)
            batch.append(json.loads(data[data_pos:end]))
            data_pos = end
            source_index += 1
            if len(batch) >= args.batch_size:
                first_index = source_index - len(batch)
                flush_batch(client, data, matrix_start, batch, first_index, dim, seen, stats, args.dry_run)
                batch = []

        if batch:
            first_index = source_index - len(batch)
            flush_batch(client, data, matrix_start, batch, first_index, dim, seen, stats, args.dry_run)

    exact = None if args.dry_run else client.count(collection_name=COLLECTION, exact=True).count
    print(f"source_records={stats['source_records']}", flush=True)
    print(f"duplicate_records={stats['duplicates']}", flush=True)
    print(f"unique_submitted={stats['submitted_unique']}", flush=True)
    print(f"batches={stats['batches']}", flush=True)
    print(f"qdrant_exact_count={exact}", flush=True)
    print(f"elapsed_seconds={time.time() - started:.1f}", flush=True)
    if stats["source_records"] != 112037:
        raise RuntimeError(f"source record count mismatch: {stats['source_records']}")
    if stats["submitted_unique"] != 96684:
        raise RuntimeError(f"unique ID count mismatch: {stats['submitted_unique']}")
    if not args.dry_run and exact != 96684:
        raise RuntimeError(f"Qdrant exact count mismatch: {exact}")


if __name__ == "__main__":
    main()
