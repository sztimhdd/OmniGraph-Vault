import argparse
import time

from qdrant_client import QdrantClient, models

parser = argparse.ArgumentParser()
parser.add_argument("namespace", choices=("entities", "chunks", "relationships"))
parser.add_argument("--timeout", type=int, default=900)
args = parser.parse_args()

collection = f"lightrag_vdb_{args.namespace}_gemini_embedding_2_3072d"
client = QdrantClient(url="http://127.0.0.1:6333", timeout=30, check_compatibility=False)
print("before", client.get_collection(collection), flush=True)
client.update_collection(
    collection_name=collection,
    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100, on_disk=True),
)
print("update_submitted", collection, flush=True)
started = time.time()
while True:
    info = client.get_collection(collection)
    print(
        f"elapsed={time.time()-started:.1f}s status={info.status} "
        f"points={info.points_count} indexed={info.indexed_vectors_count}",
        flush=True,
    )
    if info.status == models.CollectionStatus.GREEN and time.time() - started >= 10:
        break
    if time.time() - started >= args.timeout:
        raise TimeoutError(f"HNSW timeout: {info}")
    time.sleep(10)
print("done", collection, flush=True)
