#!/usr/bin/env python3
"""Check Qdrant collection status."""
import json, urllib.request

collections = [
    "lightrag_vdb_entities_gemini_embedding_2_3072d",
    "lightrag_vdb_chunks_gemini_embedding_2_3072d",
    "lightrag_vdb_relationships_gemini_embedding_2_3072d",
]

targets = {
    "lightrag_vdb_entities_gemini_embedding_2_3072d": 94557,
    "lightrag_vdb_chunks_gemini_embedding_2_3072d": 6198,
    "lightrag_vdb_relationships_gemini_embedding_2_3072d": 112037,
}

for name in collections:
    url = f"http://127.0.0.1:6333/collections/{name}"
    resp = urllib.request.urlopen(url)
    d = json.loads(resp.read())["result"]
    ok = "✓" if d["points_count"] == targets[name] else "✗"
    print(f"{ok} {name}: points={d['points_count']}/{targets[name]} status={d['status']}")
