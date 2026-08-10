# OmniGraph 向量模型迁移计划：Gemini embedding-2 → 本地 BGE-M3

## 现状

| 项 | 当前值 |
|----|--------|
| 向量模型 | `gemini-embedding-2`（Vertex AI，3072-dim） |
| 向量库 | Qdrant（localhost:6333，qdrant-snapshot 容器） |
| 数据量 | ~50K 实体 + 75K 关系 + ~5K chunks 向量（三个 collection） |
| GraphML | 65MB，50K nodes / 75K edges |
| KV stores | 66 个 JSON 文件，总计 ~120MB |
| 服务器 | 阿里云 ECS，14GB RAM，无 GPU |
| LightRAG 版本 | 1.4.16 |
| 代码位置 | `/root/OmniGraph-Vault` |
| 工作目录 | `/root/.hermes/omonigraph-vault/lightrag_storage` |

## 核心约束

1. **内存压力**：Qdrant 当前占 ~5.5GB。BGE-M3 模型加载 ~2.5GB。re-embed 期间新旧 collection 并存，双倍 Qdrant 内存（~11GB）+ 模型 = 必然 OOM。
2. **Qdrant collection 命名**：LightRAG 内部用 `lightrag_vdb_{collection_name}_{model_name}_{dim}d` 格式，含模型名和维度。换模型后需同时改 LightRAG 配置的 `embedding_dim`。
3. **无 GPU**：BGE-M3 只用 CPU 推理，~15-30 embeddings/s，全量 ~130K 点约需 1.5-2.5 小时。
4. **无人使用，无运维窗口顾虑**：可以停机操作。

## 分步计划

### Phase 1：部署本地 embedding server（CPU 模式）

**目标**：在 ECS 上跑一个 BGE-M3 推理服务，输出 1024-dim 向量，替代 Vertex API 调用。

**步骤**：

```bash
# 1. 安装 Infinity（高性能 embedding server，比 Ollama 快 3-5x）
cd /root/OmniGraph-Vault
pip install infinity-emb[all]

# 2. 启动服务（0.6B 模型，CPU 模式，监听 7997）
#    --model-id BAAI/bge-m3
#    --port 7997
#    --device cpu
#    首次运行自动下载模型（~2.5GB）
infinity_emb v2 --model-id BAAI/bge-m3 --port 7997 --device cpu --batch-size 32
```

**验证**：
```bash
curl -s http://localhost:7997/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "测试文本", "model": "BAAI/bge-m3"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['data'][0]['embedding']))"
# 输出：1024
```

**内存影响**：Infinity + BGE-M3 加载后占 ~2.5GB。**此时立即停掉 ingest 服务**（防止同时加载 LightRAG + 旧 Qdrant）。

---

### Phase 2：镜像现有 Qdrant 数据（避免 OOM）

**关键策略**：Qdrant 当前三个 collection 共占 ~5.5GB 内存。新旧并存 = ~11GB + 模型 = OOM。所以**不能同时在内存中保留新旧 collection**。

**正确做法：逐 collection 迁移，每次只保持一个在内存中。**

```python
# migrate_qdrant.py — 逐 collection 串行迁移，避免双倍内存
import asyncio
from qdrant_client import AsyncQdrantClient, models
import httpx

QDRANT_URL = "http://localhost:6333"
INFINITY_URL = "http://localhost:7997/embeddings"
OLD_COLLECTIONS = [
    "lightrag_vdb_entities_gemini_embedding_2_3072d",
    "lightrag_vdb_relationships_gemini_embedding_2_3072d", 
    "lightrag_vdb_chunks_gemini_embedding_2_3072d",
]
# LightRAG 的 collection 命名规则：{prefix}_{type}_{model}_{dim}d
# 新名称：把 gemini-embedding-2_3072d 换成 bge-m3_1024d
def new_name(old: str) -> str:
    return old.replace("gemini_embedding_2_3072d", "bge-m3_1024d")

BATCH_SIZE = 64
NEW_DIM = 1024

async def embed_texts(texts: list[str]) -> list[list[float]]:
    """通过 Infinity REST API 批量 embedding"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            INFINITY_URL,
            json={"input": texts, "model": "BAAI/bge-m3"},
        )
        data = resp.json()
        return [d["embedding"] for d in data["data"]]

async def migrate_one(client, old_col: str):
    new_col = new_name(old_col)
    print(f"\n{'='*60}")
    print(f"Migrating: {old_col} → {new_col}")
    
    # 1. 创建新 collection（关闭 HNSW 加速导入）
    await client.create_collection(
        collection_name=new_col,
        vectors_config=models.VectorParams(
            size=NEW_DIM, distance=models.Distance.COSINE
        ),
        # 关键：批量导入期间关 HNSW，不建索引，省内存
        hnsw_config=models.HnswConfigDiff(m=0),
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0),
    )
    
    # 2. 逐批迁移
    offset = None
    total = 0
    while True:
        results, offset = await client.scroll(
            collection_name=old_col,
            limit=BATCH_SIZE,
            offset=offset,
            with_vectors=False,      # 不取旧 3072-dim vector，只取 payload
            with_payload=True,
        )
        if not results:
            break
        
        texts = [p.payload.get("content", "") for p in results]
        embeddings = await embed_texts(texts)
        
        await client.upsert(
            collection_name=new_col,
            points=[
                models.PointStruct(
                    id=p.id,
                    vector=embeddings[i],
                    payload=p.payload,
                )
                for i, p in enumerate(results)
            ],
        )
        
        total += len(results)
        print(f"  {old_col}: {total} points")
        if offset is None:
            break
    
    # 3. 建 HNSW 索引
    print(f"  Building HNSW index for {new_col}...")
    await client.update_collection(
        collection_name=new_col,
        hnsw_config=models.HnswConfigDiff(m=16),
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000),
    )
    
    # 4. 等待索引完成
    while True:
        info = await client.get_collection(new_col)
        if info.status == "green":
            break
        print(f"  Indexing... status={info.status}")
        await asyncio.sleep(5)
    
    print(f"  ✓ {new_col} ready")
    
    # 5. ⚠️ 此时 OLD collection 还在内存中
    #    不要立即删，等 ALL 三个都迁移完再一次性处理

async def main():
    client = AsyncQdrantClient(url=QDRANT_URL)
    for col in OLD_COLLECTIONS:
        await migrate_one(client, col)
    print("\n" + "="*60)
    print("All 3 collections migrated. Next: swap & cleanup.")

asyncio.run(main())
```

**内存策略**：Qdrant 的 `on_disk=true` 已经在用（之前 OOM 修复时配的），mmap 模式不会把所有数据加载到内存。加上逐 collection 串行迁移、关闭 HNSW 索引期间，**峰值内存 ≤ 旧 col (~1.8GB mmap) + 新 col (~1GB mmap) + Infinity (~2.5GB) ≈ 5.3GB**，14GB 够用。

**预估耗时**：130K 点 × (1/25 emb/s) ≈ 87 分钟。

---

### Phase 3：代码层切换

**改 3 个地方**：

**3a. `lib/models.py`** — 向量维度和模型名：
```python
# 改前：
EMBEDDING_DIM = 3072
EMBEDDING_MODEL = "gemini-embedding-2"

# 改后：
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "bge-m3"
```

**3b. `lib/lightrag_embedding.py`** — embedding 函数（替换 Vertex API 调用为本地 Infinity HTTP 调用）：

在原文件 `_embed_batch_impl` 函数（约 214 行附近）的 return 之前插入一个本地调用分支。最简单做法是新增一个函数，通过环境变量切换：

```python
# lib/lightrag_embedding.py 新增

import httpx

async def _embed_bge_local(texts: list[str]) -> np.ndarray:
    """BGE-M3 via local Infinity server — replaces Vertex API entirely.
    Returns (N, 1024) float32 ndarray."""
    INFINITY_URL = os.environ.get("OMNIGRAPH_LOCAL_EMBED_URL", "http://localhost:7997/embeddings")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            INFINITY_URL,
            json={"input": texts, "model": "BAAI/bge-m3"},
        )
        data = resp.json()
        embeddings = [d["embedding"] for d in data["data"]]
        return np.array(embeddings, dtype=np.float32)
```

然后在 `embedding_func` 构造那里（约 324 行）改成：
```python
# 改前：
embedding_func = EmbeddingFunc(
    embedding_dim=EMBEDDING_DIM,
    max_token_size=EMBEDDING_MAX_TOKENS,
    func=_embed_batch,  # ← 原来调 Vertex API
)

# 改后：
_use_local = os.environ.get("OMNIGRAPH_LOCAL_EMBED", "0") == "1"
embedding_func = EmbeddingFunc(
    embedding_dim=EMBEDDING_DIM,
    max_token_size=EMBEDDING_MAX_TOKENS,
    func=_embed_bge_local if _use_local else _embed_batch,
)
```

通过环境变量控制：`OMNIGRAPH_LOCAL_EMBED=1` 走本地 BGE，不设就走原 Vertex。灰度切换，出问题随时回滚。

**3c. `.env` 更新**：
```bash
# /root/.hermes/.env 新增：
OMNIGRAPH_LOCAL_EMBED=1
OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
```

---

### Phase 4：Qdrant collection swap + 清理

迁移完成后，3 个新 collection（`lightrag_vdb_*_bge-m3_1024d`）已有数据。LightRAG 在 `initialize_storages()` 时会根据 `embedding_dim` 和 `embedding_model_name` 自动匹配新 collection 名。但 LightRAG 也维护 KV stores 中的 entity/relation 元数据（`kv_store_full_entities.json` 等），这些文件里的 embedding 引用指向旧 collection。

**安全做法**：不删旧 collection，让 LightRAG 自然过渡。新数据写入新 collection，旧数据保持不变。查询时 LightRAG 会根据配置的 `embedding_dim` 只搜新 collection。

**但实际上**，LightRAG 1.4.16 的 collection 选择逻辑可能不会自动切换。最稳的做法是 **alias swap**：

```python
# swap_aliases.py
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333")

old_names = [
    "lightrag_vdb_entities_gemini_embedding_2_3072d",
    "lightrag_vdb_relationships_gemini_embedding_2_3072d",
    "lightrag_vdb_chunks_gemini_embedding_2_3072d",
]
new_names = [n.replace("gemini_embedding_2_3072d", "bge-m3_1024d") for n in old_names]

for old, new in zip(old_names, new_names):
    # 1. 删除旧 collection
    client.delete_collection(old)
    # 2. 创建 alias 让旧名称指向新 collection
    client.update_collection_aliases(
        change_aliases_operations=[{
            "create_alias": {
                "collection_name": new,
                "alias_name": old,
            }
        }]
    )
    print(f"✓ {old} → {new}")
```

**但这有个问题**：LightRAG 代码里会根据 `embedding_dim` 和 model name 构造 collection 名。如果代码里 EMBEDDING_MODEL 还是 "gemini-embedding-2"，它会去找 `lightrag_vdb_entities_gemini_embedding_2_3072d`。但实际存的已经是 1024-dim BGE 向量了——维度不匹配，会报错。

**正确做法**：改代码里的 `EMBEDDING_MODEL` 和 `EMBEDDING_DIM`，让它自然匹配新 collection 名：
- `EMBEDDING_MODEL="bge-m3"` + `EMBEDDING_DIM=1024`
- LightRAG 会自动找 `lightrag_vdb_entities_bge-m3_1024d`、`lightrag_vdb_relationships_bge-m3_1024d`、`lightrag_vdb_chunks_bge-m3_1024d`

这样就**不需要 alias**，新旧 collection 可以共存，旧数据慢慢被新数据覆盖。

---

### Phase 5：验证

```bash
# 1. 启动 ingest 服务（使用本地 BGE）
systemctl start omnigraph-daily-ingest.service

# 2. 观察日志，确认没有 "Vertex" / "API key" 相关错误
journalctl -u omnigraph-daily-ingest.service -f | grep -iE "embed|vertex|bge|error"

# 3. 手动测试一个查询
cd /root/OmniGraph-Vault
venv-aim1/bin/python -c "
import asyncio
from lib.ingest_wechat import get_rag
from lightrag.lightrag import QueryParam

async def test():
    rag = await get_rag(flush=False)
    result = await rag.aquery('Agent Harness最核心的组件是什么？', param=QueryParam(mode='hybrid'))
    print(result[:500])

asyncio.run(test())
"

# 4. 确认 embedding 不再调用 Vertex API（观察 Qdrant 日志或网络流量）
```

---

### Phase 6：清理旧 collection

确认新模型运行稳定（建议观察 48 小时、至少 4 轮 ingest 正常完成后）：
```python
client.delete_collection("lightrag_vdb_entities_gemini_embedding_2_3072d")
client.delete_collection("lightrag_vdb_relationships_gemini_embedding_2_3072d")
client.delete_collection("lightrag_vdb_chunks_gemini_embedding_2_3072d")
```
清出 ~5.5GB 磁盘 + 释放同等 Qdrant mmap 内存。

---

## 内存时间线

| 阶段 | 进程 | 内存 |
|------|------|------|
| 迁移前（当前） | ingest + Qdrant | ~8.7GB |
| Phase 1 | 停 ingest，启 Infinity | ~8GB |
| Phase 2 | Infinity + Qdrant 迁移中 | ~6GB（单 col 交替） |
| Phase 3-5 | Infinity + ingest + 新 Qdrant | ~7GB |
| Phase 6 后 | 删旧 collection | ~5GB（节省 3.7GB） |

## 回滚方案

`OMNIGRAPH_LOCAL_EMBED=0` 恢复 Vertex API，旧 collection 未删期间查询不受影响。

---

## 执行检查清单

- [ ] Phase 1: `infinity_emb` 启动并可通过 `curl` 获取 1024-dim 向量
- [ ] Phase 1: `systemctl stop omnigraph-daily-ingest.service`
- [ ] Phase 2: 跑 `migrate_qdrant.py`，3 个 collection 全部迁移完成
- [ ] Phase 3: 改 `models.py`（EMBEDDING_DIM=1024, EMBEDDING_MODEL="bge-m3"）
- [ ] Phase 3: 改 `lightrag_embedding.py`（新增 `_embed_bge_local`，环境变量控制）
- [ ] Phase 3: 改 `/root/.hermes/.env`（加 OMNIGRAPH_LOCAL_EMBED=1）
- [ ] Phase 5: 启动 ingest，用 `journalctl` 确认无 Vertex API 错误
- [ ] Phase 5: 手动查询 KG 验证召回质量
- [ ] Phase 6: 观察 48h 后删旧 Qdrant collection
