import base64
import hashlib
import json
import mmap
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient

DATA = Path.home() / ".hermes/omonigraph-vault/lightrag_storage"
client = QdrantClient(url="http://127.0.0.1:6333", timeout=30, check_compatibility=False)


def object_end(data, start):
    opener = data[start]
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
        elif char in (ord("{"), ord("[")):
            depth += 1
        elif char in (ord("}"), ord("]")):
            depth -= 1
            if depth == 0:
                return pos + 1
    raise ValueError("unterminated JSON object")


def source_sample(path, limit=20):
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        dim_key = data.find(b"embedding_dim")
        dim = int(data[data.find(b":", dim_key) + 1 : data.find(b",", dim_key)].strip())
        data_key = data.find(b'"data"')
        pos = data.find(b"[", data_key) + 1
        records = []
        while len(records) < limit:
            while data[pos] in b" \t\r\n,":
                pos += 1
            end = object_end(data, pos)
            records.append(json.loads(data[pos:end]))
            pos = end
        matrix_key = data.rfind(b'"matrix"')
        quote = data.find(b'"', data.find(b":", matrix_key) + 1) + 1
        row_bytes = dim * 4
        chars_per_row = row_bytes // 3 * 4
        encoded = bytes(data[quote : quote + limit * chars_per_row])
        vectors = np.frombuffer(base64.b64decode(encoded), dtype=np.float32).reshape(limit, dim)
    return records, vectors


for namespace in ("entities", "chunks"):
    records, vectors = source_sample(DATA / f"vdb_{namespace}.json")
    collection = f"lightrag_vdb_{namespace}_gemini_embedding_2_3072d"
    seen = set()
    scores = []
    for index, record in enumerate(records):
        raw_key = record.get("__id__", record.get("entity_name", str(index)))
        point_id = uuid.UUID(bytes=hashlib.sha256(("_" + raw_key).encode()).digest()[:16], version=4).hex
        if point_id in seen:
            continue
        seen.add(point_id)
        points = client.retrieve(collection, ids=[point_id], with_vectors=True, with_payload=False)
        if not points:
            raise RuntimeError(f"missing {namespace} point {point_id}")
        stored = np.asarray(points[0].vector, dtype=np.float32)
        source = vectors[index]
        score = float(np.dot(source, stored) / (np.linalg.norm(source) * np.linalg.norm(stored)))
        scores.append(score)
        if len(scores) == 5:
            break
    print(
        f"{namespace}: checked={len(scores)} "
        f"cosine_min={min(scores):.9f} cosine_max={max(scores):.9f} "
        f"scores={[round(score, 9) for score in scores]}"
    )
