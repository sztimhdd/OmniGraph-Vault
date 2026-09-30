# Qdrant Vector Storage Migration

> **Status**: Ready for implementation  
> **Date**: 2026-06-01  
> **Author**: Hermes (ops diagnosis) → Claude (code implementation)

## Problem

batch_ingest OOM-kills all 3 daily ingest jobs. dmesg evidence:

```
daily-ingest:    python RSS 10.9 GB, VM 11.6 GB
afternoon-ingest: python RSS 11.0 GB, VM 11.5 GB
evening-ingest:   python RSS 10.9 GB, VM 11.6 GB
```

**Root cause**: LightRAG's default `NanoVectorDBStorage` loads the entire 2.7 GB vector JSON into Python memory. 3072-dim float vectors stored as JSON arrays → 5× memory amplification (12 KB raw → 108 KB in Python). Combined with kb-api (2.2 GB) + Docker (0.8 GB), total exceeds the 14 GB machine limit.

**Vector DB growth trajectory** (why it just started failing):

| File | May 9 | May 30 | Growth |
|------|-------|--------|--------|
| vdb_entities.json | 1.5 MB | 743 MB | 495× |
| vdb_relationships.json | 1.5 MB | 1.1 GB | 733× |

## Solution

Switch LightRAG vector storage from `NanoVectorDBStorage` (in-process JSON) to `QdrantVectorDBStorage` (separate process, mmap-backed).

**Why Qdrant**:
- Free / Apache 2.0
- Single binary, zero-config for single-node
- mmap-based storage — vectors live in kernel page cache, not Python heap
- Production-grade (used by OpenAI, DoorDash, etc.)

**Memory after migration**:

| Process | Before | After |
|---------|--------|-------|
| batch_ingest (Python) | 10.9 GB | ~0.5 GB |
| Qdrant (separate) | — | ~2 GB |
| kb-api | 2.2 GB | 2.2 GB |
| **Total** | **13+ GB → OOM** | **~5 GB ✓** |

## Changes Required

### 1. Install Qdrant on Aliyun (one command)

```bash
docker run -d --restart=always --name qdrant \
  -p 127.0.0.1:6333:6333 \
  -v /data/qdrant:/qdrant/storage \
  qdrant/qdrant:latest
```

### 2. Modify `ingest_wechat.py` (line ~392)

**File**: `/root/OmniGraph-Vault/ingest_wechat.py`  
**Function**: `get_rag()`  
**Change**: Add `vector_storage` parameter

```python
# BEFORE (line 392-406)
rag = LightRAG(
    working_dir=RAG_WORKING_DIR,
    llm_model_func=get_llm_func(),
    embedding_func=embedding_func,
    embedding_func_max_async=4,
    embedding_batch_num=64,
    llm_model_max_async=4,
    max_parallel_insert=3,
    addon_params={"insert_batch_size": 100},
)

# AFTER
rag = LightRAG(
    working_dir=RAG_WORKING_DIR,
    vector_storage="QdrantVectorDBStorage",          # ← ADDED
    llm_model_func=get_llm_func(),
    embedding_func=embedding_func,
    embedding_func_max_async=4,
    embedding_batch_num=64,
    llm_model_max_async=4,
    max_parallel_insert=3,
    addon_params={"insert_batch_size": 100},
)
```

### 3. Set environment variable

Add to systemd service unit OR `.env`:

```
QDRANT_URL=http://localhost:6333
```

### 4. Full re-ingest (data migration)

nano-vectordb JSON vectors cannot be directly imported into Qdrant (different internal key formats). Migration = re-ingest all articles from `kol_scan.db`.

Script to run on Aliyun:

```bash
cd /root/OmniGraph-Vault
source venv-aim1/bin/activate

# Clear old vectors (keep metadata: kv_stores, graph, doc_status)
rm -f /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json

# Re-ingest ALL articles with status='ok' (287 articles, ~15 min)
python3 -c "
import asyncio, sqlite3
from ingest_wechat import get_rag, ingest_article

async def main():
    c = sqlite3.connect('data/kol_scan.db')
    rows = c.execute('''
        SELECT a.id, a.url, a.title FROM articles a
        JOIN ingestions i ON a.id = i.article_id
        WHERE i.status='ok' AND a.body IS NOT NULL AND a.body != ''
        ORDER BY a.id
    ''').fetchall()
    
    rag = await get_rag(flush=True)
    for i, (aid, url, title) in enumerate(rows):
        print(f'[{i+1}/{len(rows)}] {title[:50]}')
        await ingest_article(url, source='wechat', rag=rag)
    
    await rag.finalize_storages()
    print('Done')

asyncio.run(main())
"

# Delete old nano-vectordb JSON (free 2.7 GB disk)
rm -f /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json
```

**Cost**: ~287 articles × ~1250 tokens/article embedding = ~360K tokens. Gemini embedding = $0.000025/1K chars ≈ **<$0.01**.

### 5. Restart services

```bash
systemctl restart omnigraph-daily-ingest
systemctl restart omnigraph-afternoon-ingest
systemctl restart omnigraph-evening-ingest
```

## Verification

After implementation, run one ingest and check:

```bash
# Memory check — Python process should be < 1 GB RSS
ps aux | grep batch_ingest

# Qdrant should be running
curl http://localhost:6333/health

# No OOM in dmesg
dmesg | grep -i "oom.*batch_ingest\|oom.*python" | tail -3

# Ingest should complete with exit=0
systemctl status omnigraph-daily-ingest --no-pager | grep "result\|exit"
```

## Rollback

If needed, revert by removing `vector_storage` parameter and restarting ingest with nano-vectordb:

```bash
# Revert code change, then:
docker stop qdrant && docker rm qdrant
systemctl restart omnigraph-daily-ingest
```
