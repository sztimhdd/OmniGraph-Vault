#!/usr/bin/env python3
"""Migrate NanoVectorDB JSON → Qdrant.  Matrix is ONE base64 blob — decoded
once into bytes, then sliced row-by-row to avoid OOM."""
from __future__ import annotations

import argparse, base64, hashlib, json, mmap, struct, sys, time, uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

DATA_DIR   = Path.home() / ".hermes/omonigraph-vault/lightrag_storage"

FILES = {
    "entities":      "vdb_entities.json",
    "chunks":        "vdb_chunks.json",
    "relationships": "vdb_relationships.json",
}
COLLECTIONS = {
    ns: f"lightrag_vdb_{ns}_gemini_embedding_2_3072d"
    for ns in FILES
}
WORKSPACE = "_"
DIM       = 3072
ROW_BYTES = DIM * 4  # 12288


def point_id(raw_key: str) -> str:
    h = hashlib.sha256(f"{WORKSPACE}{raw_key}".encode()).digest()[:16]
    return str(uuid.UUID(bytes=h))


def find_matrix_b64(data: bytes) -> bytes:
    """Extract the single base64 matrix string from JSON bytes."""
    tag = b'"matrix"'
    pos = data.find(tag)
    if pos == -1:
        raise ValueError("matrix key not found")
    colon = data.find(b':', pos)
    q1 = data.find(b'"', colon)
    q2 = q1 + 1
    while q2 < len(data):
        if data[q2] == ord('"') and data[q2-1] != ord('\\'):
            break
        q2 += 1
    return data[q1+1:q2]


def parse_records(data: mmap.mmap) -> list[dict]:
    """Parse all JSON objects from the 'data' array.  Returns list of {__id__, ...}."""
    tag = b'"data": ['
    pos = data.find(tag)
    if pos == -1:
        raise ValueError("data array not found")
    pos += len(tag)

    records = []
    while pos < len(data):
        # Find next '{'
        brace = data.find(b'{', pos)
        if brace == -1:
            break
        # Find matching '}' — simple depth counter
        depth, i, in_str, escaped = 1, brace + 1, False, False
        while i < len(data) and depth > 0:
            b = data[i]
            if escaped:
                escaped = False
            elif b == ord('\\'):
                escaped = True
            elif b == ord('"'):
                in_str = not in_str
            elif not in_str:
                if b == ord('{'):
                    depth += 1
                elif b == ord('}'):
                    depth -= 1
            i += 1
        if depth != 0:
            break
        obj_bytes = data[brace:i]
        try:
            records.append(json.loads(obj_bytes))
        except json.JSONDecodeError:
            pass
        pos = i
    return records


def migrate(namespace: str, batch_size: int, dry_run: bool):
    fname = FILES[namespace]
    coll   = COLLECTIONS[namespace]
    path   = DATA_DIR / fname
    if not path.exists():
        print(f"  SKIP {path}", flush=True)
        return

    fsize = path.stat().st_size
    print(f"\n[{namespace}] {fsize/1e9:.2f}GB → {coll}", flush=True)

    with open(path, "rb") as fh:
        raw_bytes = fh.read()

    print(f"  read {len(raw_bytes)/1e9:.2f}GB into memory", flush=True)

    # Parse records
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        print("  parsing records...", flush=True)
        records = parse_records(mm)
        mm.close()

    total = len(records)
    print(f"  records={total}", flush=True)

    # Decode matrix
    print("  decoding matrix...", flush=True)
    t0 = time.time()
    b64 = find_matrix_b64(raw_bytes)
    matrix = base64.b64decode(b64)
    expected = total * ROW_BYTES
    print(f"  matrix={len(matrix)/1e6:.2f}MB expected={expected/1e6:.2f}MB "
          f"{time.time()-t0:.1f}s", flush=True)

    if len(matrix) != expected:
        print(f"  WARNING: size mismatch! records*row_bytes={expected} "
              f"actual={len(matrix)}", flush=True)

    del raw_bytes  # free memory

    client = QdrantClient(
        url="http://127.0.0.1:6333", timeout=60,
        check_compatibility=False,
    )

    seen: set[str] = set()
    submitted, dup_skipped, bad_skipped = 0, 0, 0
    batch_points = []
    t0 = time.time()

    for i, rec in enumerate(records):
        raw_id = rec.get("__id__", "")
        pid = point_id(raw_id)
        if pid in seen:
            dup_skipped += 1
            continue

        # Extract vector row
        offset = i * ROW_BYTES
        row = matrix[offset:offset + ROW_BYTES]
        vec = list(struct.unpack(f"<{DIM}f", row))
        if any(v != v for v in vec):
            bad_skipped += 1
            continue

        seen.add(pid)
        batch_points.append(models.PointStruct(
            id=pid,
            vector=vec,
            payload={"workspace_id": WORKSPACE, "__id__": raw_id},
        ))

        if len(batch_points) >= batch_size:
            if not dry_run:
                client.upsert(collection_name=coll, points=batch_points, wait=True)
            submitted += len(batch_points)
            batch_points.clear()

        if (i + 1) % 20000 == 0:
            print(f"  {i+1}/{total} submitted={submitted} "
                  f"dup={dup_skipped} bad={bad_skipped} "
                  f"{time.time()-t0:.0f}s", flush=True)

    if batch_points:
        if not dry_run:
            client.upsert(collection_name=coll, points=batch_points, wait=True)
        submitted += len(batch_points)

    elapsed = time.time() - t0
    if not dry_run:
        exact = client.count(collection_name=coll, exact=True).count
    else:
        exact = -1
    print(f"  DONE submitted={submitted} exact={exact} "
          f"dup={dup_skipped} bad={bad_skipped} "
          f"{elapsed:.0f}s", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=list(FILES.keys()))
    args = parser.parse_args()

    ns_list = [args.only] if args.only else list(FILES.keys())
    for ns in ns_list:
        migrate(ns, args.batch_size, args.dry_run)

    if not args.dry_run:
        print("\n=== SUMMARY ===")
        client = QdrantClient(url="http://127.0.0.1:6333", timeout=10,
                              check_compatibility=False)
        for ns in ns_list:
            print(f"  {ns}: {client.count(COLLECTIONS[ns], exact=True).count}")


if __name__ == "__main__":
    main()
