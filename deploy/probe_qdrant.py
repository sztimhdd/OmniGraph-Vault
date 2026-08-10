#!/usr/bin/env python3
"""Probe Qdrant: why are upserts not persisting?"""
import json, urllib.request

coll = "lightrag_vdb_entities_gemini_embedding_2_3072d"
base = "http://127.0.0.1:6333"

# 1. Check collection exists
info = json.loads(urllib.request.urlopen(f"{base}/collections/{coll}").read())
cfg = info["result"]["config"]
print(f"status={info['result']['status']} points={info['result']['points_count']}")
print(f"vec_on_disk={cfg['params']['vectors']['on_disk']} hnsw_m={cfg['hnsw_config']['m']}")

# 2. Upsert 1 point via REST
point_id = "00000000000000000000000000000001"
body = json.dumps({
    "points": [{
        "id": point_id,
        "vector": [0.001] * 3072,
        "payload": {"workspace_id": "_", "test": "probe", "orig_id": "test_entity"}
    }]
}).encode()

req = urllib.request.Request(
    f"{base}/collections/{coll}/points",
    data=body,
    headers={"Content-Type": "application/json"},
    method="PUT"
)
resp = urllib.request.urlopen(req)
print(f"\nUpsert HTTP {resp.status}: {resp.read().decode()}")

# 3. Read it back
verify = json.loads(urllib.request.urlopen(
    f"{base}/collections/{coll}/points/{point_id}"
).read())
print(f"Read back: {json.dumps(verify, indent=2)[:300]}")

# 4. Scroll to see all points
scroll = json.loads(urllib.request.urlopen(
    f"{base}/collections/{coll}/points/scroll",
    data=json.dumps({"limit": 5, "with_payload": True, "with_vector": False}).encode(),
    headers={"Content-Type": "application/json"}
).read())
print(f"\nScroll result ({len(scroll['result']['points'])} points):")
for p in scroll["result"]["points"]:
    print(f"  id={p['id'][:20]}... payload_keys={list(p['payload'].keys())}")

# 5. Final count
info2 = json.loads(urllib.request.urlopen(f"{base}/collections/{coll}").read())
print(f"\nFinal count: {info2['result']['points_count']}")
