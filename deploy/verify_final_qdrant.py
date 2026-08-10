from qdrant_client import QdrantClient

client = QdrantClient(url="http://127.0.0.1:6333", timeout=30, check_compatibility=False)
for namespace in ("entities", "chunks", "relationships"):
    collection = f"lightrag_vdb_{namespace}_gemini_embedding_2_3072d"
    info = client.get_collection(collection)
    exact = client.count(collection, exact=True).count
    points, _ = client.scroll(collection, limit=3, with_payload=True, with_vectors=False)
    print(
        f"{namespace}: exact={exact} status={info.status} "
        f"approx_points={info.points_count} payload_samples={len(points)}"
    )
    if points:
        payload = points[0].payload or {}
        print(
            f"  sample_id={points[0].id} workspace={payload.get('workspace_id')} "
            f"keys={sorted(payload)[:12]}"
        )

collections = [item.name for item in client.get_collections().collections]
print("temporary_probe_collections:", [name for name in collections if "probe" in name or "migration" in name])
