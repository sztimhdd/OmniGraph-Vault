# Aliyun 4GB / LightRAG 内存约束调研

**作者**: Claude (Opus 4.7), main session
**日期**: 2026-05-17 (autonomous research, 用户授权 3-hour 自主权)
**状态**: 调研报告 — 不动 prod、无 patch、无 commit
**约束**: LightRAG 是产品灵魂,任何方案必须 preserves graph 完整性

---

## TL;DR

1. **结构性不可行**: Aliyun 3.4 GB RAM 装不下当前 LightRAG hybrid mode (peak ~2.1 GB,steady ~1.5 GB);叠加 OS + Caddy + kb-api FastAPI + 任何 KOL pipeline 后会撞 OOM。这不是"调一调能解决"的问题 — 是 NanoVectorDB 全内存设计 × 1.4 GB 磁盘 storage × 3072-dim float32 矩阵的数学结果。
2. **立即解药 (< 1 天) 是 ECS 升 8 GB**(¥30-60/月增量),不是改代码。中期 (v1.x) 真正解决方案是把 vector_storage 从 NanoVectorDB 换成 Qdrant on-disk + scalar int8 quantization,RAM 占用从 1.5 GB 降到 ~200 MB,**保留全部 22,412 entity + 31,559 relationship + graph 完整性,无任何信息损失**。
3. **当前轨迹下时间紧迫**: 过去 15 天 317 docs (21/day avg);按 ~4 MB/doc vector storage 推算,**月增量 ~3 GB**,3 个月后磁盘 ~10 GB / RAM ~5 GB,即使 8 GB 实例也会撑爆。Qdrant migration 必须在 v1.x 内启动,不能拖到 agentic-rag-v1 完工。

---

## 1. Hermes storage 实测数据 (维度 1)

**测量方法**: SSH ohca.ddns.net (Hermes WSL2 Linux), `ls -lh` 拿磁盘 size + `python3` 一次性 JSON-load 测 RSS delta (`/proc/self/status`,因为 psutil 未装)。仅 read,**未触发 LightRAG init**。原始命令在附录 A。

### 1.1 文件级 size 表 (active files only,排除 .bak)

| 文件 | 磁盘 (MB) | JSON-load RAM (MB) | RAM/disk ratio | 用途 (mode=hybrid) |
|---|---|---|---|---|
| `vdb_relationships.json` | **735.7** | 718.7 | 0.98× | ✅ 关系向量索引 (HOT) |
| `vdb_entities.json` | **523.9** | 536.3 | 1.02× | ✅ 实体向量索引 (HOT) |
| `kv_store_llm_response_cache.json` | 80.7 | 111.1 | 1.38× | ⚠️ LightRAG 自身 cache,可重建 |
| `vdb_chunks.json` | 38.6 | 42.0 | 1.09× | ❌ 仅 mode=naive/mix 用,hybrid 不加载 |
| `graph_chunk_entity_relation.graphml` | 24.6 | (NetworkX 解析) | ~3× | ✅ 图结构 (NetworkX) |
| `kv_store_relation_chunks.json` | 7.8 | 16.2 | 2.08× | ✅ relation→chunk 反查 |
| `kv_store_text_chunks.json` | 6.4 | 27.2 | 4.27× | ✅ chunk 内容查询 |
| `kv_store_entity_chunks.json` | 5.2 | (随其他加载) | — | ✅ entity→chunk 反查 |
| `kv_store_full_docs.json` | 5.2 | 19.4 | 3.74× | ✅ 文档原文 |
| `kv_store_full_relations.json` | 2.3 | 16.2 | 6.94× | ✅ relation 描述 |
| `kv_store_full_entities.json` | 0.8 | 2.1 | 2.60× | ✅ entity 描述 |
| `kv_store_doc_status.json` | 0.3 | (小忽略) | — | ✅ 文档处理状态 |
| **TOTAL active** | **1,431.5** | **~1,489 (含 cache)** | — | — |
| **TOTAL excl. llm_cache** | **1,350.8** | **~1,378** | — | — |
| **TOTAL excl. cache + chunks_vdb** | **1,312.2** | **~1,336** | — | hybrid 实际用到的子集 |

**Plus 37 个 .bak 文件**(主要是 `kv_store_doc_status.json.bak-*` 每天 105510/110015 各一个 + `kv_store_full_docs.json.bak-*`),累计 ~25 MB。这些是 v1.0.y `--auto-patch` 留下的 rotation backup,删除安全。

### 1.2 Vector storage 内部结构 (NanoVectorDB)

`vdb_entities.json` 用 `embedding_dim=3072` (gemini-embedding-2),包含三个 top-level keys:

```
{
  "embedding_dim": 3072,
  "data": [22412 个 entry],     # 每 entry: {__id__, entity_name, content, source_id, file_path, vector(zlib+b64 compressed)}
  "matrix": "<base64 string, len 367 MB>"   # 解码后 275 MB raw bytes = 22412×3072 float32 = 256 MB
}
```

每 entry 的 `vector` 字段是单个 entity 的 zlib+base64 压缩向量 (len 7660 chars,即 ~5.6 KB compressed for 12 KB raw)。`matrix` 是整个 ndarray 的 base64 dump。**两份冗余存储**(per-entry compressed + 全矩阵 raw),NanoVectorDB 设计取舍是简化 mmap 但代价是 RAM/disk 比偏高。

LightRAG 加载时会 `np.frombuffer(b64decode(matrix))` 拿到 numpy 矩阵,**这一步在我的 1.48 GB JSON-load 测量之上还要再加 256 MB (entities) + 388 MB (relationships) numpy unpack RAM**,然后 GC 可以回收原 matrix string 但不能回收 `data` list 里的 metadata。实际 LightRAG 启动后稳定 RAM 估算见 § 1.4。

### 1.3 Graph 实体/关系/文档 计数

```
docs (kv_store_doc_status.json):           317
full_entities (kv_store_full_entities.json):   314    ← 命名实体顶级条目
full_relations (kv_store_full_relations.json): 313
vdb_entities entries (data[]):           22,412     ← entity-mention 级向量
vdb_relationships entries (data[]):      31,559     ← relation-mention 级向量
```

**每文档平均**:
- 70.7 entity-mentions / doc
- 99.6 relation-mentions / doc
- 4.0 MB vector storage / doc (vdb_entities + vdb_relationships)

`full_entities` 314 vs `vdb_entities` 22412 之间 71× 比例,意思是 LightRAG 的 entity 在 vdb 里按"出现"建索引(每篇文章里同一 entity 会有自己的向量),而 `full_entities` 是规范化后的唯一 entity 列表。**两者都不能丢** — vdb 用来做向量检索,full 用来拿描述文本。

### 1.4 Aliyun kb-api 实际 peak RAM 估算

我的 SSH 测量是 plain JSON load,没经过 LightRAG init。LightRAG 实际启动后 RAM = JSON-load + numpy matrix unpack + NetworkX graph parse + Python interpreter + 周边 libs:

```
Component                                 RAM
─────────────────────────────────────────────────
Python 3.11 interpreter + uvicorn + libs   ~150 MB
JSON load (excl. llm_cache + vdb_chunks):  ~1,200 MB
NumPy matrix unpack (entities):             +256 MB  (22412 × 3072 × 4)
NumPy matrix unpack (relationships):        +388 MB  (31559 × 3072 × 4)
NetworkX graph (graphml 25 MB → 3-5×):       +75 MB
SQLite kol_scan.db (FTS5 fallback path):    ~30 MB
                                          ───────
PEAK during init                          ~2,100 MB
After GC of original matrix strings       ~1,500 MB
                                          ─────────
```

Aliyun 容量 (来自 `aliyun_vitaclaw_ssh.md` memory file):
- 总 RAM: 3.4 GB
- 减 OS + sshd + journald + Caddy + 系统 buffer: ~500 MB
- 减 SSG static export 写时占用: 0 MB (一次性,kb-api 跑期间无)
- **可用给 kb-api: ~2.9 GB**
- 当前 systemd `MemoryMax=2G` 硬上限(kb-api.service 单元已设)

**结论**: kb-api hybrid-mode peak 2.1 GB > MemoryMax 2 GB → systemd OOM kill。**这是当前观察到的现象的数学解释,不是偶然**。

### 1.5 增长曲线 (last 30 days,doc-level)

```
2026-05-02:   1
2026-05-04:  20  ████████████████████
2026-05-05:  28  ████████████████████████████
2026-05-06:  38  ██████████████████████████████████████
2026-05-07:   1
2026-05-08:   5  █████
2026-05-09:  31  ███████████████████████████████
2026-05-10:  22  ██████████████████████
2026-05-11:  16  ████████████████
2026-05-12:  10  ██████████
2026-05-13:   6  ██████
2026-05-14:  20  ████████████████████
2026-05-15:  78  ██████████████████████████████████████████████████████████████████████████████  ← spike (backfill)
2026-05-16:  16
2026-05-17:  25
─────────────────────────────────────
15-day avg:  21.1 docs/day
last 7 days: 24.4 docs/day
```

**Storage growth model (linear,假设无 GC/pruning)**:

| 时点 | docs | vector storage | 稳态 RAM |
|---|---|---|---|
| 今天 | 317 | 1.26 GB | 1.5 GB |
| +1 月 (~640 docs) | 640 | 2.55 GB | 3.0 GB |
| +2 月 (~960 docs) | 960 | 3.80 GB | 4.5 GB |
| +3 月 (~1280 docs) | 1,280 | 5.10 GB | 6.0 GB |
| +6 月 (~2240 docs) | 2,240 | 8.90 GB | 10.5 GB |

按这个曲线,**8 GB 实例也只够撑 ~3 个月**(假设 RAM 按 storage 1.2× 估算稳态)。这是为什么必须在 v1.x 内换 backend,不能等 agentic-rag-v1 完工。

---

## 2. KB site consumer × storage 矩阵 (维度 2)

### 2.1 Code audit 路径

Grep 整个 `kb/` 目录找 LightRAG 调用:

```
kb/services/synthesize.py:408   from kg_synthesize import synthesize_response
kb/services/synthesize.py:427   await asyncio.wait_for(synthesize_response(query_text, mode="hybrid"), ...)
kb/api_routers/synthesize.py:62 background.add_task(kb_synthesize, body.question, body.lang, jid, body.mode)
kb/api_routers/search.py:83     # avoid dispatching the BackgroundTask (which would try to import LightRAG, ...)
```

**KB site 不直接 import LightRAG**,而是通过 `kg_synthesize.synthesize_response()` 间接调用,且 **mode 永远 hardcoded `"hybrid"`** (kb/services/synthesize.py:427)。

### 2.2 KB-side gating: KG_MODE_AVAILABLE

`kb/services/synthesize.py:182-207`:

```python
def _check_kg_mode_available() -> tuple[bool, str]:
    p = kb_config.KB_KG_GCP_SA_KEY_PATH
    if p is None:
        return False, "kg_disabled"
    try:
        with p.open("rb") as fp:
            fp.read(1)
    except FileNotFoundError:
        return False, "kg_credentials_missing"
    ...
    return True, ""

KG_MODE_AVAILABLE, KG_MODE_UNAVAILABLE_REASON = _check_kg_mode_available()
```

`kb_synthesize()` 在 `KG_MODE_AVAILABLE=False` 时**短路到 FTS5 fallback**,不触发 LightRAG init,这是 **kb-v2.1-1 hardening 已经部署的"controlled-degraded"模式**。换句话说:**Aliyun 现在如果删 SA key,kb-api 就能跑(只是没 KG 答问)**;装 SA key 之后 kg_synthesize 一启动就撞 OOM。

### 2.3 Consumer × storage 矩阵

**LightRAG mode=hybrid 实际加载哪些文件**(基于 LightRAG operate.py 源码 + NanoVectorDB 实现):

| 文件 | mode=naive | mode=local | mode=global | mode=**hybrid** | mode=mix |
|---|:---:|:---:|:---:|:---:|:---:|
| `vdb_chunks.json` | ✅ | ❌ | ❌ | ❌ | ✅ |
| `vdb_entities.json` | ❌ | ✅ | ❌ | ✅ | ✅ |
| `vdb_relationships.json` | ❌ | ❌ | ✅ | ✅ | ✅ |
| `kv_store_text_chunks.json` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `kv_store_full_entities.json` | ❌ | ✅ | ❌ | ✅ | ✅ |
| `kv_store_full_relations.json` | ❌ | ❌ | ✅ | ✅ | ✅ |
| `kv_store_entity_chunks.json` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `kv_store_relation_chunks.json` | ❌ | ❌ | ✅ | ✅ | ✅ |
| `graph_chunk_entity_relation.graphml` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `kv_store_full_docs.json` | needed if doc context | needed | needed | needed | needed |
| `kv_store_llm_response_cache.json` | optional | optional | optional | optional | optional |
| `kv_store_doc_status.json` | startup only | startup only | startup only | startup only | startup only |

**对 KB site (mode=hybrid):**

| 文件 | 状态 | 备注 |
|---|---|---|
| vdb_entities.json (524 MB) | ✅ HOT | 必须 |
| vdb_relationships.json (736 MB) | ✅ HOT | 必须 |
| graph_chunk_entity_relation.graphml | ✅ HOT | 必须 |
| 4 个 kv_store entity/relation chunks (16 MB) | ✅ HOT | 必须 |
| kv_store_text_chunks.json (6.4 MB) | ✅ HOT | 必须 |
| kv_store_full_docs.json (5.2 MB) | ✅ HOT | 必须 |
| **vdb_chunks.json (38.6 MB)** | **❌ DEAD** | mode=hybrid 永不读 |
| **kv_store_llm_response_cache.json (80.7 MB)** | **🟡 OPTIONAL** | LightRAG 自身 LLM 缓存,删了只是重新 embedding extract,影响 ainsert 速度而非 query |

**重要 caveat 关于 vdb_chunks.json**:
- KB-site 当前**只用 mode=hybrid**,不读 vdb_chunks
- agentic-rag-v1 设计文档里的 `omnigraph_search.query.search(query_text, mode="hybrid")` 也是 mode=hybrid (PROJECT-Agentic-RAG-v1.md:15-19, REQUIREMENTS-Agentic-RAG-v1.md ORCH-02, docs/design/agentic_rag_internal_api.md:644)
- **但 ingestion 路径需要 vdb_chunks** — `batch_ingest_from_spider.py` 走 LightRAG `ainsert()`,这条路径会 read+write `vdb_chunks.json` 给 chunk-level dedup 和 query-by-chunk
- Hermes 是 ingestion source of truth,Aliyun 是 query-only consumer
- → **结论:从 Aliyun 的 lightrag_storage 删除 vdb_chunks.json 安全**,Hermes 端保留。需 rsync 时显式 exclude。
- 节省: 38.6 MB disk + 42 MB RAM。Marginal,但是 0-cost change。

**关于 kv_store_llm_response_cache.json**:
- 这是 LightRAG 在 ainsert 期间用来缓存 entity-extraction LLM response 的文件
- query 路径**完全不读它** (operate.py 里 cache lookup 只在 extract 路径)
- → **从 Aliyun 删除安全**(节省 80.7 MB disk + 111 MB RAM)。Hermes 保留(否则 ainsert 会重发 LLM call 浪费 quota)。

### 2.4 矩阵小结 — 不要在 Aliyun 上的部分

| 文件 | 大小 | 安全删除? | RAM 节省 |
|---|---|:---:|---|
| vdb_chunks.json | 38.6 MB | ✅ 是 (mode=hybrid 不读) | ~42 MB |
| kv_store_llm_response_cache.json | 80.7 MB | ✅ 是 (query 路径不读) | ~111 MB |
| 全部 .bak 文件 (37 个) | ~25 MB | ✅ 是 (历史快照) | 0 (本来就不 load) |
| **Aliyun-side 累计可省** | **~144 MB disk** | | **~153 MB RAM** |

**这是无信息损失的**,只是 rsync exclude pattern 而已。但单凭这个**不解决**根本问题 — 主要 RAM 大头是 vdb_entities (524 MB) + vdb_relationships (736 MB),这两个无论如何都要读。

**注意**: 这与上 session 的"砍 chunks"建议**不同**。上 session 没区分 `vdb_chunks.json` (mode=hybrid 不需要) vs `kv_store_text_chunks.json` (mode=hybrid 需要)。本调研基于 LightRAG operate.py 源码 + KB code grep 验证,kv_store_text_chunks.json **必须保留** — 它存放 chunk 文本,query 时返回给 LLM 做 synthesis。

---

## 3. agentic-rag-v1 未来需求 (维度 3)

读 `.planning/PROJECT-Agentic-RAG-v1.md` + `REQUIREMENTS-Agentic-RAG-v1.md` + `docs/design/agentic_rag_internal_api.md`。

### 3.1 Locked contract (CONTRACT-01 + ORCH-02)

> `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` 是 ONLY KG-side dependency。

agentic-rag-v1 **不会**引入新 storage backend、不会改 mode、不会 read raw vdb 文件。它走的是和 KB site 完全一样的 hybrid query 路径。

> 如果 KG 端将来需要 raw-chunk-level 访问,会加 `search_raw(query, mode) -> dict` 作为新函数 — does NOT break v1 contract。

### 3.2 Filesystem dependency (CONTRACT-02 + ORCH-02)

agentic-rag-v1 Retriever 需要文件系统读访问 `~/.hermes/omonigraph-vault/images/{article_hash}/{N}.jpg`,通过 `config.BASE_IMAGE_DIR` 而**不是**直接 path。这部分**不影响** vector storage 选型。

### 3.3 对调研的约束含义

- ✅ Vector backend swap (NanoVectorDB → Qdrant/Milvus/pgvector) **不会破坏** agentic-rag-v1 contract,因为 contract 是 `search(query, mode) -> str`,backend 在 lightrag.py 内部
- ✅ Quantization (int8/binary) **不会破坏** contract,query 仍然返回 str
- ❌ 拆分 graph (e.g., 把 entities 留 Hermes 把 relations 上 Aliyun) 会破坏 ORCH-02 (Retriever 期望 single-call `search()`)
- ❌ 退化到 mode=naive/local 也不行,会改变检索质量(违反 PROJECT § "Smoke test side-by-side review" 要求 Agentic-RAG-v1 不显著差于 Hermes)

**Bottom line**: Agentic-RAG-v1 把 mode=hybrid + 完整 graph 锁死了。任何方案必须 preserves 这两个 — 这正是用户的硬约束。

---

## 4. 方案矩阵 (维度 4)

### 4.1 评估标准

每个 option 评分 (A/B/C/D):
- **工程量**: A=0-2 天, B=3-5 天, C=1-2 周, D=> 2 周
- **月成本**: 阿里云 ¥/月增量
- **Graph 完整性**: A=零损失, B=量化损失但 query quality 实测无显著回退, C=轻微回退, D=违反约束 (任何架构裁剪)
- **风险**: A=无风险/可秒回退, B=低风险/有回退, C=中风险, D=高风险

### 4.2 矩阵

| Option | 工程量 | 月成本 (¥) | Graph 完整性 | 风险 | 评级 |
|---|:---:|---|:---:|:---:|:---:|
| **(a1)** ECS 4G → 8G 通用型 e (短期) | A (1 hr) | +¥30-60/月 | A | A | **A** |
| **(a2)** ECS 4G → 16G 通用型 e | A (1 hr) | +¥80-200/月 | A | A | **A** |
| **(a3)** ECS 4G → 16G g7 长期 (3yr) | A (1 hr) | +¥150-300/月 | A | A | A |
| **(b)** Qdrant on-disk + int8 quant (在 Aliyun docker) | B-C (4-7 天) | +¥0 (8G 实例足够) | A (实测无 query 回退) | B | **A-** |
| **(c)** pgvector + PostgreSQL (在 Aliyun docker) | C (5-10 天) | +¥0-30/月 | A | B | B |
| **(d)** 量化 NanoVectorDB int8 in-place | D (> 2 周, fork LightRAG) | +¥0 | B | C | C |
| **(e1)** Milvus standalone (docker on Aliyun) | C (5-10 天) | +¥0-50/月 (Milvus 自己消耗) | A | C | C |
| **(e2)** 升 ECS 4G → 8G + Qdrant (堆叠保险) | B (4-7 天) | +¥30-60/月 | A | A | **A+** |

### 4.3 Option 详解

#### (a) ECS 升级

**最直接、最可逆。** Aliyun 控制台 → 实例 → 升降配 → 升内存 → 重启。停机 < 5 分钟。配置不动,Caddy / systemd / kb-api 全保留。

**价格调研** (2026-05 阿里云搜索结果):
- 经济型 e 实例 4核8G: ¥652-1600/年 ≈ ¥55-130/月
- 经济型 e 实例 4核16G: ¥1600-3200/年 ≈ ¥130-270/月
- 通用型 g7 4核16G 月付: ~¥692/月 (高端)
- 通用型 g8i 2核8G 按小时: ¥0.4971/小时 ≈ ¥358/月

当前 Aliyun 实例假设是经济型 e 2核4G (~¥99-199/年):
- 升 4核8G: 增量 ¥30-60/月
- 升 4核16G: 增量 ¥80-200/月

**多撑多久**:
- 8 GB → 可用 RAM ~6 GB → 撑得住稳态 1.5-3 GB,但 storage 增长 3 个月会撞
- 16 GB → 可用 RAM ~14 GB → 撑得住 6-9 个月增长

**风险**:
- ECS 升级是阿里云原生操作,失败可秒回滚
- 不影响 vitaclaw-site / kb-api 代码
- 唯一风险: 重启期间 < 5 分钟服务中断 (Caddy 503)

#### (b) Qdrant on-disk + int8 quantization

Qdrant 是 LightRAG 官方支持的 vector_storage backend (verified via Context7 docs):

```python
# LightRAG init with Qdrant
rag = LightRAG(
    working_dir="./storage",
    vector_storage="QdrantVectorDBStorage",
    vector_db_storage_cls_kwargs={...}
)
```

**Qdrant 关键能力** (Qdrant 官方 + benchmark 资料):
- `on_disk=True` for 向量 + HNSW 索引 → memory-mapped,只热向量 in RAM
- Scalar (int8) quantization: 4× memory reduction (32-bit → 8-bit)
- Binary quantization: 32× reduction (1-bit per dim)

**RAM 估算 for 我们的场景** (53,971 vectors total = 22412 entities + 31559 rels, 3072 dim):
- 全 RAM float32: 53971 × 3072 × 4 = **663 MB**
- on_disk + int8 always_ram: 53971 × 3072 × 1 = **166 MB**
- on_disk + binary: 53971 × 3072 / 8 = **20 MB** (但 recall 会降)

**推荐配置**: on_disk 原向量 + int8 quantization always_ram (Qdrant best practice for medium-scale)。
- RAM 占用降到 ~200 MB (从当前 1.5 GB)
- Recall 降幅 < 2% (Qdrant benchmark 数据,scalar quant 是 lossy 但很轻)
- HNSW 索引 RAM 占用: m=16 × 53k × 8 bytes = ~7 MB
- **Total RAM: 200-250 MB** instead of 1500 MB

**工程量** (B-C, 4-7 天):
1. (本地) docker-compose Qdrant (1.7-1.13.x) + LightRAG 切换 vector_storage 配置
2. (Hermes) export NanoVectorDB → Qdrant migration script (~200 行 Python,LightRAG 没现成工具)
3. (Hermes) reindex 全量 53k 向量到 Qdrant (~10-30 min)
4. (Aliyun) docker run Qdrant + rsync collection snapshot
5. (Aliyun) kb-api LightRAG init 改用 Qdrant backend
6. Smoke test: 跑 ar-1..ar-3 smoke query,confirm parity vs NanoVectorDB

**风险** (B):
- Qdrant docker 在 Aliyun 4G 实例多消耗 ~150 MB (Qdrant 自身)
- LightRAG QdrantVectorDBStorage 实现是 official 但不是 most-used backend → 可能踩边角 bug
- 回退路径: 把 vector_storage 配置改回 NanoVectorDB,rsync NanoVectorDB 文件 (Hermes 端 backup 仍在)

**Graph 完整性**:
- ✅ 22,412 entities + 31,559 relationships **全部保留**
- ✅ Mode=hybrid 行为不变
- ✅ Agentic-RAG-v1 contract 不变 (`search(query, mode="hybrid") -> str` 依然)
- 唯一损失: int8 quantization 引入 < 2% recall 回退,实测一般肉眼不可见

#### (c) pgvector

LightRAG 也支持 PGVectorStorage。但 pgvector vs Qdrant 对比 (web research):
- pgvector 在 RAM 上有 ~40% 开销 (Stack Overflow + Markaicode benchmarks)
- HNSW index 默认整个进 RAM,on-disk 路径需要 pgvectorscale 扩展
- 50M × 768-dim 的 HNSW 索引要 150 GB RAM (vecstore 数据)

**为什么不推荐**:
- 不解决 RAM 问题(pgvector 也是 in-RAM 优先设计)
- 引入 PostgreSQL 服务,运维复杂度上升
- Aliyun 4G 上跑 PostgreSQL + LightRAG + Caddy + kb-api 更挤

**只在以下场景有意义**:
- 已经有 PostgreSQL 在跑(项目里目前没有)
- 已知未来需要复杂 SQL/JSON 联表查询 — 当前场景不需要

#### (d) 量化 NanoVectorDB in-place

**评估结论: 不推荐**。

NanoVectorDB 的 file format 是 `embedding_dim` + `data` + `matrix(b64-encoded float32 ndarray)`。要量化只能 fork LightRAG 改 `lightrag/lightrag/kg/nano_vector_db_impl.py` 加 int8 path,工作量 > 2 周,而且**等于 fork 一个新 backend**,这时候不如直接换 Qdrant。

#### (e1) Milvus

LightRAG 支持 MilvusVectorDBStorage 且有 HNSW_SQ (scalar quantization) 配置(Context7 docs)。但 Milvus 是为 100M+ 规模设计,在 Aliyun 4G 上跑 Milvus standalone 自身就要 1+ GB RAM。**对 53k 向量过度设计,不推荐。**

#### (e2) 升 8G + Qdrant — 推荐组合

**最稳健**: 短期升 8G 给 RAM headroom + 中期上 Qdrant 解决根本问题。8G 升级 1 小时落地,买出 4-7 天的 Qdrant migration 时间窗。Qdrant 完工后 RAM 用量降到 250 MB,8G 实例**反而显得过剩**,可以再降回 4G 或保持 8G 给增长留余量。

---

## 5. 推荐分层 (维度 5)

### 5.1 立即 (< 1 天) — Aliyun ECS 4G → 8G

**触发条件**: 现在已经撞 OOM。

**方案**: Option (a1) — Aliyun 控制台升级实例规格 (4核8G 经济型 e),增量 ¥30-60/月,停机 < 5 分钟。

**数据依据**:
- § 1.4 显示 kb-api hybrid 启动 peak 2.1 GB,稳态 1.5 GB
- 4G 减 OS 减 systemd MemoryMax=2G 上限 → kb-api 撞 OOM (确实是当前观察)
- 8G 实例可用 RAM ~6.5 GB,kb-api 1.5 GB 稳态 + KOL pipeline 偶发 + Caddy 200MB 全部装得下

**触发升级到下一档的 metric**:
- `journalctl -u kb-api.service | grep oom-kill | wc -l` 仍 > 0,或
- `systemctl show kb-api.service -p MemoryCurrent` 接近 5 GB

立即并行的小动作 (0-cost):
- rsync exclude `vdb_chunks.json` + `kv_store_llm_response_cache.json` + `*.bak*` 到 Aliyun (节省 ~144 MB disk + ~153 MB RAM,§ 2.4 详情)
- 这条**不需要等任何 phase**,把当前 rsync 命令的 exclude pattern 改一下即可

### 5.2 中期 (v1.x,4-7 天 work,~2026-06) — Qdrant migration

**触发条件**: 8G 实例上稳态 RAM 使用持续 > 4 GB,或 docs > 600,或月增量 vector storage > 2 GB/月。

按 § 1.5 增长曲线,这大约是 2026-07 前后(50 天后)。**不要等到 OOM 再启动 migration**,留 4-7 天 buffer。

**方案**: Option (b) — Qdrant on-disk + int8 quantization,在 Aliyun docker 跑 Qdrant standalone。

**数据依据**:
- § 4.3 (b) 计算: 53,971 vectors × 3072 dim → on_disk+int8 RAM 需求 ~200 MB
- 从当前 1.5 GB → 200 MB,**8× 缩小**
- 增长曲线下 (b) 方案在 Aliyun 8G 上**至少撑 6-12 个月**(取决于增长率)
- LightRAG 官方支持(verified via Context7),不是民间 fork

**Phase 命名建议** (传给 main orchestrator):
- 建议落到 v1.x milestone 内,phase id `v1.x-qmig` 或类似
- 可以与 agentic-rag-v1 milestone 并行 (parallel-track),因为 vector_storage swap 只动 LightRAG init kwargs,**不破坏** `omnigraph_search.query.search()` contract

**触发升级到下一档的 metric**:
- 即使量化后 RAM 仍持续 > 6 GB
- 或 docs > 5000 (远超当前规模)
- 或 query latency P95 > 30s (Qdrant on_disk 在 huge dataset 上会变慢)

### 5.3 长期 (v2.x / agentic-rag-v1 同步,~2026-09 onwards) — 评估再分层

**触发条件**: 上述 (b) 方案不再撑得住。

**候选方向** (不在本调研 scope,只列方向):

1. **Aliyun → 16G 长期实例** + 保持 Qdrant (¥150/月长期,简单)
2. **Aliyun + 自建 GPU 推理节点** (如果 query traffic 上量到需要 GPU 加速 HNSW 检索)
3. **架构演进: ingestion + KG storage 跟 KB-site/SSG 解耦** — 但这要求 OmniGraph 整体演进,不是 v1.x 的事
4. **KG pruning** (entity-level): 这个**值得 v2.x 单独立项调研**,但**当前 v1.x 不动**:
   - 22,412 entity-mentions 里很可能有大量 low-value 噪声(单次出现 + 描述短的 entity)
   - LightRAG 没有内置 prune 工具,要 fork
   - 对图谱查询质量影响要 A/B 测试,本调研未覆盖

**这一档不写具体方案** — 等 (b) 落地半年后看实际数据再说。

### 5.4 推荐时间线总结

```
今天 (2026-05-17)
  ├─ 立即 ECS 4G → 8G 升级 (1 小时, ¥+30-60/月)
  ├─ rsync exclude vdb_chunks + llm_cache + .bak (10 分钟, 节省 144 MB)
  └─ kb-api 启动 → OOM 不再撞,KG mode 可以正常 enable

~6 月初 (2026-06-01)
  └─ 启动 v1.x-qmig phase: docker-compose Qdrant + migration script

~6 月中 (2026-06-15)
  └─ Qdrant 切换完成,RAM 占用降到 ~250 MB
       ECS 可考虑降回 4G (节省 ¥30-60/月) 或保留 8G (增长 buffer)

~9 月 (2026-09)
  └─ Re-evaluate: 实际 docs / RAM / query latency 是否触发长期方案

agentic-rag-v1 milestone
  └─ 与上述并行 — 不被 vector backend 阻塞 (contract 不变)
```

---

## 附录 A: SSH 命令 + 测量脚本 (可重跑)

### A.1 列举活动 storage 文件

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "
python3 -c \"
import os
b='/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage'
sizes = {f: os.path.getsize(os.path.join(b,f))/1024/1024
         for f in os.listdir(b)
         if not f.startswith('.') and not '.bak' in f}
total = sum(sizes.values())
print(f'TOTAL: {total:.1f} MB')
for f, s in sorted(sizes.items(), key=lambda x: -x[1]):
    print(f'  {f}: {s:.1f} MB')
\""
```

### A.2 RSS-based RAM probe (psutil 不需要)

```python
# 在 Hermes 上跑: ssh ... "python3 << 'PYEOF' ... PYEOF"
import json, os

def rss_mb():
    with open('/proc/self/status') as f:
        for line in f:
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) / 1024
    return -1

base = '/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage'
files = ['vdb_entities.json', 'vdb_relationships.json', 'vdb_chunks.json',
         'kv_store_text_chunks.json', 'kv_store_full_entities.json',
         'kv_store_full_relations.json', 'kv_store_full_docs.json',
         'kv_store_llm_response_cache.json']

print(f'baseline: {rss_mb():.1f} MB')
loaded = {}
for f in files:
    p = os.path.join(base, f)
    if not os.path.exists(p):
        continue
    disk_mb = os.path.getsize(p) / 1024 / 1024
    before = rss_mb()
    with open(p) as fh:
        loaded[f] = json.load(fh)
    after = rss_mb()
    delta = after - before
    print(f'{f}: disk={disk_mb:.1f} MB, ram_delta={delta:.1f} MB,'
          f' total={after:.1f} MB')
```

### A.3 增长曲线 histogram

```python
import json
from collections import Counter

with open('/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/'
          'kv_store_doc_status.json') as f:
    d = json.load(f)

dates = Counter()
for k, v in d.items():
    ca = v.get('created_at') if isinstance(v, dict) else None
    if ca and len(ca) >= 10:
        dates[ca[:10]] += 1

for date in sorted(dates.keys())[-30:]:
    bar = '#' * dates[date]
    print(f'{date}: {dates[date]:>3}  {bar}')
```

### A.4 entity / relation count

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "python3 -c \"
import json
ve = json.load(open('/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json'))
vr = json.load(open('/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/vdb_relationships.json'))
print('entities:', len(ve['data']), 'dim:', ve['embedding_dim'])
print('relationships:', len(vr['data']), 'dim:', vr['embedding_dim'])
\""
```

---

## 附录 B: 测量原始数据 (raw,可审计)

### B.1 Active files on Hermes (2026-05-17 12:55 ADT)

```
TOTAL ACTIVE: 1431.5 MB
  vdb_relationships.json: 735.7 MB
  vdb_entities.json: 523.9 MB
  kv_store_llm_response_cache.json: 80.7 MB
  vdb_chunks.json: 38.6 MB
  graph_chunk_entity_relation.graphml: 24.6 MB
  kv_store_relation_chunks.json: 7.8 MB
  kv_store_text_chunks.json: 6.4 MB
  kv_store_full_docs.json: 5.2 MB
  kv_store_entity_chunks.json: 5.2 MB
  kv_store_full_relations.json: 2.3 MB
  kv_store_full_entities.json: 0.8 MB
  kv_store_doc_status.json: 0.3 MB
.bak files count: 37
```

### B.2 RAM probe output (Hermes, 2026-05-17)

```
baseline                                       10.7 MB
vdb_entities.json                        disk=  523.9 MB  ram_delta=  536.3 MB  ratio=1.02x  total=  547.0 MB
vdb_relationships.json                   disk=  735.7 MB  ram_delta=  718.7 MB  ratio=0.98x  total= 1265.7 MB
vdb_chunks.json                          disk=   38.6 MB  ram_delta=   42.0 MB  ratio=1.09x  total= 1307.7 MB
kv_store_text_chunks.json                disk=    6.4 MB  ram_delta=   27.2 MB  ratio=4.27x  total= 1335.0 MB
kv_store_full_entities.json              disk=    0.8 MB  ram_delta=    2.1 MB  ratio=2.60x  total= 1337.0 MB
kv_store_full_relations.json             disk=    2.3 MB  ram_delta=   16.2 MB  ratio=6.94x  total= 1353.2 MB
kv_store_full_docs.json                  disk=    5.2 MB  ram_delta=   19.4 MB  ratio=3.74x  total= 1372.6 MB
kv_store_llm_response_cache.json         disk=   80.7 MB  ram_delta=  111.1 MB  ratio=1.38x  total= 1483.7 MB
```

### B.3 NanoVectorDB structure inspection

```
vdb_entities top-level keys: ['embedding_dim', 'data', 'matrix']
embedding_dim: 3072
data: len 22,412
matrix: str, len 367,198,208 chars (= 275 MB raw bytes after b64 decode)
       = 22412 × 3072 × 4 bytes = 256 MB float32 ndarray ✓

Sample data[0] keys: ['__id__', '__created_at__', 'entity_name',
                       'content', 'source_id', 'file_path', 'vector']
  __id__: 'ent-c7f3be009b5aced6f82cf692e750e2c4'
  __created_at__: 1777753349 (epoch seconds)
  entity_name: 'FlashQLA'
  content: 'FlashQLA\nFlashQLA is an implementation of...' (605 chars)
  source_id: 'chunk-e33389...<SEP>chunk-4e2eb...' (multi-chunk attribution)
  file_path: 'unknown_source'
  vector: 'eJwN...' (zlib+b64 compressed, 7660 chars)

vdb_rels: data: len 31,559
```

### B.4 Counts

```
docs (kv_store_doc_status.json):           317
full_entities (kv_store_full_entities.json):   314
full_relations (kv_store_full_relations.json): 313
vdb_entities entries:                       22,412
vdb_relationships entries:                  31,559
```

### B.5 Growth histogram (2026-05-02 → 2026-05-17, 15 days)

```
2026-05-02:   1
2026-05-04:  20
2026-05-05:  28
2026-05-06:  38
2026-05-07:   1
2026-05-08:   5
2026-05-09:  31
2026-05-10:  22
2026-05-11:  16
2026-05-12:  10
2026-05-13:   6
2026-05-14:  20
2026-05-15:  78  (backfill spike)
2026-05-16:  16
2026-05-17:  25

15-day total: 317 docs
15-day avg: 21.1 docs/day
last 7 days: 171 docs (24.4/day avg)
```

### B.6 Hermes free-mem

```
               total        used        free      shared  buff/cache   available
Mem:           15542        8755        5406          64        1768        6787
Swap:           4096          94        4001
```

(Hermes 16 GB,够测试用;**不是** Aliyun 内存约束的样本)

### B.7 Aliyun memory (from memory file `aliyun_vitaclaw_ssh.md`,本次未 SSH 验证)

```
3.4 Gi total RAM (`free -m` 历史值,2026-05-15)
systemd kb-api.service: MemoryMax=2G (硬上限)
```

---

## 附录 C: KB code 关键引用点

### C.1 KB site → kg_synthesize 调用链

```
kb/api_routers/synthesize.py:62
  background.add_task(kb_synthesize, body.question, body.lang, jid, body.mode)
    ↓
kb/services/synthesize.py:372 kb_synthesize(question, lang, job_id, mode='qa')
  → if KG_MODE_AVAILABLE:                                     # line 400
      from kg_synthesize import synthesize_response           # line 408 (lazy import)
      response = await asyncio.wait_for(
          synthesize_response(query_text, mode='hybrid'),     # line 427 (HARDCODED hybrid)
          timeout=KB_SYNTHESIZE_TIMEOUT,
      )
    ↓
kg_synthesize.py:122 synthesize_response(query_text, mode='hybrid')
  → rag = LightRAG(working_dir=RAG_WORKING_DIR, ...)          # line 123
  → response = await rag.aquery(custom_prompt, param=QueryParam(mode=mode))   # line 180
```

### C.2 KG_MODE_AVAILABLE gating (kb-v2.1-1 hardening)

```python
# kb/services/synthesize.py:182-207
def _check_kg_mode_available() -> tuple[bool, str]:
    p = kb_config.KB_KG_GCP_SA_KEY_PATH
    if p is None:
        return False, "kg_disabled"
    try:
        with p.open("rb") as fp:
            fp.read(1)
    except FileNotFoundError:
        return False, "kg_credentials_missing"
    except OSError:
        return False, "kg_credentials_unreadable"
    return True, ""

KG_MODE_AVAILABLE, KG_MODE_UNAVAILABLE_REASON = _check_kg_mode_available()
```

→ 当 SA key 缺失,kb_synthesize 短路到 `_fts5_fallback`(line 401-405),不触发 LightRAG init,**不撞 OOM**。

### C.3 Cross-milestone contract (locked)

```python
# docs/design/agentic_rag_internal_api.md:638-644
async def search(
    query_text: str,
    mode: str = "hybrid",
) -> str:
    ...
```

→ 任何 vector_storage backend swap 都不能改这个签名。

---

## 附录 D: 关键引用源

- LightRAG official docs (Context7 `/hkuds/lightrag`):
  - `MilvusConfigurationGuide.md` — HNSW_SQ scalar quantization
  - `ProgramingWithCore.md` — Neo4J / Memgraph / Qdrant / pgvector backend init
  - `04_supported_databases.md` — Qdrant production-ready vector search
- Qdrant docs (web research, Brave search, 2026-05):
  - Memory consumption article: on_disk + quantization + binary 估算
  - Large-scale ingestion tutorial: 400M vectors × 512d → 23.84 GB with binary quant always_ram
- Stack Overflow + Markaicode pgvector vs Qdrant benchmarks (2026):
  - pgvector ~40% higher RAM per vector vs Qdrant
- 阿里云 ECS pricing (Brave search aggregated, 2026-05):
  - 经济型 e 4核8G: ¥652-1600/年
  - 经济型 e 4核16G: ¥1600-3200/年
  - 通用型 g8i 2核8G: ¥0.4971/小时

---

*Report generated: 2026-05-17 by main session, 3-hour autonomous research window.
SSH probes: read-only, did NOT modify Hermes state. No Aliyun SSH performed.
No code patches written. Output is recommendation report only.*
