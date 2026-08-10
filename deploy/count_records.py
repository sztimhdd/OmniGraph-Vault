#!/usr/bin/env python3
"""Count records in NanoVectorDB JSON files by counting __id__ occurrences."""

import os

paths = {
    "entities": "/root/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json",
    "chunks": "/root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json",
    "relationships": "/root/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json",
}

for name, path in paths.items():
    size = os.path.getsize(path)
    count = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)  # 4MB chunks
            if not chunk:
                break
            count += chunk.count(b'__id__')
    print(f"{name}: {count} records, file={size/1024**3:.2f}GB")
