# OOM Diagnosis & Qdrant Migration

> **Date**: 2026-06-01  
> **Machine**: Aliyun ECS 14GB (101.133.154.49)  
> **Incident**: 3 consecutive OOM kills on ingest jobs

## Root Cause

LightRAG's default `NanoVectorDBStorage` loads the entire vector JSON into Python heap.
3072-dim Gemini embedding vectors stored as JSON float arrays → devastating memory amplification.

### Memory Accounting

```
Disk (LightRAG storage at ~/.hermes/omonigraph-vault/lightrag_storage/):
  vdb_relationships.json   1.1 GB
  vdb_entities.json        743 MB
  vdb_chunks.json           57 MB
  graph_chunk.graphml       36 MB
  kv_stores                 ~50 MB
  ─────────────────────────────
  Total disk               2.7 GB

Python memory (after loading):
  3072 floats × 36 bytes (PyObject) × ~50,000 vectors  ≈ 5.4 GB  (pure vectors)
  Content strings                                      ≈ 1.5 GB
  NetworkX graph structure                             ≈ 0.5 GB
  Python dict/list metadata overhead                   ≈ 3.0 GB
  ────────────────────────────────────────────────────────────────
  Python RSS                                           ≈ 10.9 GB

Amplification: 2.7 GB disk → 10.9 GB RAM (4×)
```

### Why It Just Started Failing

| File | May 9 | May 30 | Growth |
|------|-------|--------|--------|
| vdb_entities.json | 1.5 MB | 743 MB | 495× |
| vdb_relationships.json | 1.5 MB | 1.1 GB | 733× |

As knowledge graph grew, the Python RSS crossed the 10 GB threshold.
Combined with kb-api (2.2 GB) + Docker (0.8 GB) → exceeds 14 GB machine limit.

## Diagnosis Commands

### Check OOM killer logs
```bash
dmesg | grep -i "oom\|killed\|out of memory" | tail -20
```
Look for `Out of memory: Killed process <pid> (python) total-vm:... anon-rss:...`

### Check LightRAG storage size
```bash
du -sh ~/.hermes/omonigraph-vault/lightrag_storage/
ls -lhS ~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json
```

### Check vector dimensions
```bash
head -c 500 ~/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json
# → "embedding_dim": 3072
```

### Count vectors
```bash
grep -c '"vector"' ~/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json
grep -c '"vector"' ~/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json
```

### Check RSS of running ingest
```bash
ps aux | grep batch_ingest | awk '{print $2, $6/1024 " MB"}'
```

## Community Research (2026-06-01)

After diagnosing the 10GB RAM problem, the user asked to search community solutions.
This section captures the research methodology and findings.

### Search Strategy

Three parallel searches to cover different angles:

1. `lightrag memory optimization huge RAM usage vector storage alternative milvus qdrant`
2. `lightrag nano-vectordb memory blowup 10GB fix numpy faiss chromadb`
3. `LightRAG vector storage backend postgres pgvector reduce memory usage production`

### Findings: 8 Vector Storage Backends

LightRAG supports 8 vector storage backends (from `docs/ProgramingWithCore.md`):

| Backend | Python RSS | External Service | Memory Model |
|---------|-----------|-----------------|-------------|
| NanoVectorDB | 10.9 GB | None | JSON → Python objects (4× amp) |
| FaissVectorDB | ~200 MB | None | Disk-backed IVF+SQ8 |
| QdrantVectorDB | ~100 MB | Qdrant binary | mmap, separate process |
| PGVector | ~50 MB | PostgreSQL | pgvector in DB process |
| MilvusVectorDB | ~100 MB | Milvus | Standalone, GPU optional |
| ChromaVectorDB | ~200 MB | None (embedded) | SQLite-based |

### Community Consensus (Reddit, DEV, GitHub Issues)

Three dominant patterns emerged:

1. **FaissVectorDB** — "zero-dependency switch" for smallest change. No external service.
   Downside: FAISS index still in-process; metadata JSON still loads into Python.

2. **PGVector (PostgreSQL)** — "all-in-one" for teams already running Postgres.
   Vectors live in the DB process; Python client only gets query results.

3. **Qdrant** — "production standard" for dedicated vector workloads.
   Single binary, mmap storage, Python client is thin wrapper over REST API.
   Community benchmarks: 1M × 768-dim vectors → 3-4 GB (Qdrant process, not Python).

### Decision Framework

When presenting options to the user, use this structure:

1. **Fastest fix**: FaissVectorDB (zero new services, 2-line change)
2. **Best stability**: Qdrant (mmap, production-grade, free/open source)
3. **Best if Postgres exists**: PGVector (no new service needed)

User chose Qdrant based on: minimal ops overhead, 5-year stability, free, open source.

## Solution: Qdrant

Switch `vector_storage` from `NanoVectorDBStorage` to `QdrantVectorDBStorage`.

### Memory After Migration

| Process | Before | After |
|---------|--------|-------|
| batch_ingest (Python) | 10.9 GB | ~0.5 GB |
| Qdrant (separate) | — | ~2 GB (mmap) |
| kb-api | 2.2 GB | 2.2 GB |
| **Total** | **13+ GB → OOM** | **~5 GB ✓** |

### Changes (2-line code diff)

**File**: `ingest_wechat.py`, function `get_rag()`, line ~392

```python
rag = LightRAG(
    working_dir=RAG_WORKING_DIR,
    vector_storage="QdrantVectorDBStorage",   # ← ADD THIS
    llm_model_func=get_llm_func(),
    embedding_func=embedding_func,
    # ... rest unchanged
)
```

**Env var**: `QDRANT_URL=http://localhost:6333`

### Install Qdrant
```bash
docker run -d --restart=always --name qdrant \
  -p 127.0.0.1:6333:6333 \
  -v /data/qdrant:/qdrant/storage \
  qdrant/qdrant:latest
```

### Data Migration

nano-vectordb vectors cannot be directly imported into Qdrant (different internal key formats).
Migration = re-ingest all `status='ok'` articles from `kol_scan.db`.

```bash
cd ~/OmniGraph-Vault
source venv-aim1/bin/activate
# Clear old vectors
rm -f ~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json

# Re-ingest 287 articles (~15 min, <$0.01 embedding cost)
python3 -c "
import asyncio, sqlite3
from ingest_wechat import get_rag, ingest_article

async def main():
    c = sqlite3.connect('data/kol_scan.db')
    rows = c.execute('''
        SELECT a.id, a.url FROM articles a
        JOIN ingestions i ON a.id = i.article_id
        WHERE i.status='ok' AND a.body IS NOT NULL AND a.body != ''
        ORDER BY a.id
    ''').fetchall()
    
    rag = await get_rag(flush=True)
    for i, (aid, url) in enumerate(rows):
        print(f'[{i+1}/{len(rows)}] {url[:60]}')
        await ingest_article(url, source='wechat', rag=rag)
    await rag.finalize_storages()
    print('Done')

asyncio.run(main())
"
```

### LightRAG Vector Storage Backends (All 8)

| Backend | Python RSS | External Service | Notes |
|---------|-----------|-----------------|-------|
| NanoVectorDB | 10.9 GB | None | Default, JSON-based |
| FaissVectorDB | ~200 MB | None | IVF+SQ8 quantization |
| QdrantVectorDB | ~100 MB | Qdrant | mmap, production-grade |
| PGVector | ~50 MB | PostgreSQL | pgvector extension |
| MilvusVectorDB | ~100 MB | Milvus | Heavy, GPU optional |
| ChromaVectorDB | ~200 MB | None (embedded) | SQLite-based |
| MongoVectorDB | ~100 MB | MongoDB | — |
| OpenSearchVectorDB | ~100 MB | OpenSearch | — |

### Verification

```bash
# Qdrant health
curl http://localhost:6333/health

# Check no OOM in recent dmesg
dmesg | grep -i "oom.*batch_ingest\|oom.*python" | tail -3

# Ingest service exit code
systemctl status omnigraph-daily-ingest --no-pager | grep "result\|exit"
```
