# 旧机 BGE-M3 嵌入模型搬迁方案

> **目标：** 扫描/入库机 `47.117.244.253` 从 Gemini 3072d 切换到 BGE-M3 1024d 本地嵌入，彻底脱离 Google 依赖，与 KG 机 `47.103.73.20` 嵌入层统一。
>
> **审核后执行，每步独立验证。**

---

## 0. 当前状态

| 项 | 旧机 (47.117.244.253) | 新机 (47.103.73.20) |
|---|---|---|
| 角色 | 扫描 + 入库 | KG 查询 + MCP |
| Python | 3.11.0rc1 | 3.10.12 |
| LightRAG | 1.4.16 | 1.5.4 |
| Qdrant 集合 | `gemini_embedding_2_3072d` ×3 | `bge_m3_1024d` ×3 |
| 嵌入模型 | `gemini-embedding-2` → Vertex AI | `bge-m3` → localhost:7997 |
| FlagEmbedding | 未安装 | 已安装 |
| BGE-M3 模型 | 无 | `/models/bge-m3/` |
| 翻墙 | ✅ | ❌ |
| 磁盘剩余 | **18 GB**（2026-07-31 清理后，原 7.1 GB） | 31 GB |
| 空闲内存 | 6.4 GB | 5.4 GB |
| systemd units | 30 个（ingest/kb-api 无） | 3 个（embed/kb-api/mcp） |
| LLM | DeepSeek | DeepSeek |

**磁盘清理记录（2026-07-31 已执行）：**
| 删除项 | 大小 |
|---|---|
| `/root/.rustup` | 1.4 GB |
| `/root/.bun` | 1.4 GB |
| `OmniGraph-Vault/venv`（旧 venv） | 1.1 GB |
| `/root/.npm`（缓存） | 585 MB |
| `/root/.cache/pip`（缓存） | 520 MB |
| `lightrag_storage.aliyun-pre-aim2-bak-*`（5/23 旧备份） | 752 MB |
| `/root/.cache/prisma` + docker prune | ~100 MB |
| **合计** | **~10 GB（93% → 82%）** |

**风险点：**
- ~~磁盘仅剩 7.1 GB~~ → **已解除**：18 GB 可用，BGE-M3 ~2.2 GB + 重迁临时文件 ~500 MB 无压力
- Python 3.11 vs 3.10，FlagEmbedding 需验证兼容性
- LightRAG 1.4.16 vs 1.5.4，monkey patch 位置可能不同

---

## 1. 前置准备（只读，不修改）

```bash
# 1.1 确认服务状态
ssh aliyun-old '
  systemctl is-active omnigraph-daily-ingest.timer
  systemctl is-active qdrant-snapshot.timer
  docker ps | grep qdrant
  free -h
  df -h /
'

# 1.2 备份关键文件
ssh aliyun-old '
  mkdir -p /root/backups/bge-m3-migration-$(date +%Y%m%d)
  cp /root/OmniGraph-Vault/lib/models.py /root/backups/bge-m3-migration-$(date +%Y%m%d)/
  cp /root/OmniGraph-Vault/lib/lightrag_embedding.py /root/backups/bge-m3-migration-$(date +%Y%m%d)/
  cp /root/.hermes/.env /root/backups/bge-m3-migration-$(date +%Y%m%d)/
  echo "backup done"
'
# 1.3 确认旧机向量存储后端（**必须先做，决定 Phase 7 方向**）

旧机 Qdrant 与 NanoVectorDB **同时存在**（2026-07-31 实测），主存储必须确认：

```bash
ssh aliyun-old '
  # A. Qdrant 状态
  docker ps --filter name=qdrant --format "{{.Names}} {{.Status}}"
  curl -sf http://127.0.0.1:6333/collections | python3 -m json.tool

  # B. NanoVectorDB 文件（注意 .tmp 后缀 = 写入未完成）
  ls -lh /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json*

  # C. LightRAG 1.4.16 初始化代码指向哪个存储（决定性证据）
  grep -n "VectorStorage\|NanoVector\|Qdrant\|vector_storage" \
    /root/OmniGraph-Vault/kg_synthesize.py 2>/dev/null | head -10
  # 或查 lightrag 配置:
  grep -rn "vector_storage\|QDRANT\|NANO" \
    /root/OmniGraph-Vault/kb/*.py /root/OmniGraph-Vault/lib/*.py 2>/dev/null | head -10
'
```

**判定：**
- 初始化代码用 `QdrantVectorStorage` → **Qdrant 主存储**，Phase 7 用 scroll + re-embed（新机 `migrate_all_bounded.py` 的 Qdrant 变体），不读 JSON
- 初始化代码用 `NanoVectorStorage` → **NanoVDB 主存储**，Phase 7 需另写 JSON 读取脚本，且迁移后要切换 LightRAG 初始化到 Qdrant（新机方案可参考）
- 两者都配 → 以 LightRAG 实际读取路径为准（Qdrant 优先，NanoVDB 是 `qdrant-snapshot.timer` 导出的快照）

**验证：** 明确主存储 + Phase 7 方向确定后，继续 Phase 2。

---

## 2. 安装 FlagEmbedding + 下载模型

```bash
# 2.1 安装（旧机能翻墙，直接从 PyPI）
ssh aliyun-old '
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  pip install FlagEmbedding
  python3 -c "import FlagEmbedding; print(FlagEmbedding.__version__)"
'

# 2.2 下载 BGE-M3 模型（HuggingFace，~2.2 GB）
# ⚠ 用 snapshot_download(local_dir=) 直接落到 embed_server 期望的路径
#   （/models/bge-m3/BAAI/bge-m3，见 embed_server.py 默认 EMBED_MODEL_PATH）
#   不要用 BGEM3FlagModel(cache_dir=) 的 HF cache 布局（models--BAAI--bge-m3/snapshots/...）
ssh aliyun-old '
  mkdir -p /models/bge-m3
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  python3 -c "
from huggingface_hub import snapshot_download
p = snapshot_download(
    \"BAAI/bge-m3\",
    local_dir=\"/models/bge-m3/BAAI/bge-m3\",
    local_dir_use_symlinks=False,
)
print(\"downloaded to:\", p)
"
'

# 2.3 验证模型文件 + 加载测试
ssh aliyun-old '
  ls /models/bge-m3/BAAI/bge-m3/ | head -8
  # 应包含: config.json, model.safetensors(或 pytorch_model.bin), tokenizer.json
  du -sh /models/bge-m3/BAAI/bge-m3
'
```

**验证：** `FlagEmbedding` import 成功；`encode(["test"])` 返回 `(1, 1024)`。

---

## 3. 部署 embed-server

从新机拷贝文件到旧机：

```bash
# 3.1 拷贝 embed_server.py（新机版本 = FlagEmbedding 直读本地路径，非 Infinity）
scp aliyun-new:/root/OmniGraph-Vault/embed_server.py /tmp/embed_server.py
scp /tmp/embed_server.py aliyun-old:/root/OmniGraph-Vault/embed_server.py

# 3.2 确认 embed_server.py 模型加载方式（应输出 BGEM3FlagModel + local_files_only）
ssh aliyun-old 'grep -n "MODEL_PATH\|BGEM3FlagModel\|local_files_only" /root/OmniGraph-Vault/embed_server.py'
# 预期: MODEL_PATH 默认 /models/bge-m3/BAAI/bge-m3（Phase 2.2 已下载到该路径，无需覆盖）
```

**创建 systemd unit：**（EMBED_MODEL_PATH 用默认值即可，与 Phase 2.2 下载路径一致）

```bash
ssh aliyun-old 'cat > /etc/systemd/system/embed-server.service << "UNIT"
[Unit]
Description=Embedding Server (BGE-M3 1024d)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
Environment=EMBED_MODEL_PATH=/models/bge-m3/BAAI/bge-m3
Environment=EMBED_PORT=7997
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/embed_server.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/embed-server.log
StandardError=append:/var/log/embed-server.log

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now embed-server
'
```

**验证：**
```bash
# 3.3 确认 embed-server 启动
ssh aliyun-old 'sleep 5 && curl -sf --max-time 5 -X POST http://127.0.0.1:7997/embeddings \
  -H "Content-Type: application/json" \
  -d "{\"input\":\"test\",\"model\":\"bge-m3\"}" | python3 -c "import sys,json; r=json.load(sys.stdin); print(len(r[\"data\"][0][\"embedding\"]))"'
# 预期: 1024
```

---

## 4. 更新代码：切换到本地嵌入

### 4.1 更新 `lib/models.py`

旧机当前：`EMBEDDING_MODEL="gemini-embedding-2"` `EMBEDDING_DIM=3072`

```bash
ssh aliyun-old '
cd /root/OmniGraph-Vault
# 直接替换两行
sed -i "s/EMBEDDING_MODEL\s*=.*/EMBEDDING_MODEL = \"bge-m3\"/" lib/models.py
sed -i "s/EMBEDDING_DIM\s*=.*/EMBEDDING_DIM = 1024   # BGE-M3 full-capacity dim/" lib/models.py
grep "EMBEDDING_MODEL\|EMBEDDING_DIM" lib/models.py
'
```

### 4.2 更新 `lib/lightrag_embedding.py`

旧机当前只有 Vertex AI / Gemini 路径，需添加本地嵌入分支。

从新机拷贝完整文件（新机已含双路径）：

```bash
# 先备份旧机版本
ssh aliyun-old 'cp /root/OmniGraph-Vault/lib/lightrag_embedding.py /root/OmniGraph-Vault/lib/lightrag_embedding.py.vertex-backup'

# 拷贝新机版本
scp aliyun-new:/root/OmniGraph-Vault/lib/lightrag_embedding.py /tmp/lightrag_embedding.py
scp /tmp/lightrag_embedding.py aliyun-old:/root/OmniGraph-Vault/lib/lightrag_embedding.py

# 验证关键函数存在
ssh aliyun-old 'grep -n "_embed_local\|OMNIGRAPH_LOCAL_EMBED" /root/OmniGraph-Vault/lib/lightrag_embedding.py'
# 预期: 213:async def _embed_local(...), 231:if os.environ.get("OMNIGRAPH_LOCAL_EMBED") == "1":
```

**验证：**
```bash
ssh aliyun-old '
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  python3 -c "
import os
os.environ[\"OMNIGRAPH_LOCAL_EMBED\"] = \"1\"
os.environ[\"OMNIGRAPH_LOCAL_EMBED_URL\"] = \"http://127.0.0.1:7997/embeddings\"
from lib.lightrag_embedding import embedding_func
# 不做实际调用，只确认 import 路径不报错
print(\"import OK\")
"
'
```

---

## 5. 更新 .env 配置

```bash
# 幂等写入：存在则替换，不存在则追加（避免重复变量）
ssh aliyun-old '
  grep -q "^OMNIGRAPH_LOCAL_EMBED=" /root/.hermes/.env \
    && sed -i "s/^OMNIGRAPH_LOCAL_EMBED=.*/OMNIGRAPH_LOCAL_EMBED=1/" /root/.hermes/.env \
    || echo "OMNIGRAPH_LOCAL_EMBED=1" >> /root/.hermes/.env

  grep -q "^OMNIGRAPH_LOCAL_EMBED_URL=" /root/.hermes/.env \
    && sed -i "s|^OMNIGRAPH_LOCAL_EMBED_URL=.*|OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings|" /root/.hermes/.env \
    || echo "OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings" >> /root/.hermes/.env
'

# 确认写入（必须只有 1 次出现）
ssh aliyun-old 'grep -c "OMNIGRAPH_LOCAL_EMBED" /root/.hermes/.env'
# 预期: 2（OMNIGRAPH_LOCAL_EMBED 和 OMNIGRAPH_LOCAL_EMBED_URL 各 1 次）
```

**不删除的旧变量（暂留 7 天做回退保险）：**
- `GEMINI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `OMNIGRAPH_EMBEDDING_KEYS`

---

## 6. 更新所有 ingest systemd unit（注入 embed env vars）

旧机有多个 ingest timer，需确保每个都能读到 `OMNIGRAPH_LOCAL_EMBED=1`+`OMNIGRAPH_LOCAL_EMBED_URL`。

**方案：per-unit drop-in**（不改原 unit，systemd 原生合并，可逆性最好）：

```bash
ssh aliyun-old '
cd /etc/systemd/system
for unit in omnigraph-*.service; do
  [[ $unit == *.bak* ]] && continue
  svcname=$(basename "$unit")
  mkdir -p "${svcname}.d"
  cat > "${svcname}.d/embed.conf" << "EOF"
[Service]
Environment=OMNIGRAPH_LOCAL_EMBED=1
Environment=OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
EOF
done
systemctl daemon-reload
echo "drop-ins created: $(ls -d omnigraph-*.service.d 2>/dev/null | wc -l)"
'
```

**验证：**
```bash
# 抽查 3 个活跃 unit 是否生效（Environment 合并来自 drop-in）
ssh aliyun-old '
  systemctl show omnigraph-daily-ingest.service -p Environment | tr " " "\n" | grep OMNIGRAPH_LOCAL_EMBED
  systemctl show omnigraph-kol-scan.service -p Environment | tr " " "\n" | grep OMNIGRAPH_LOCAL_EMBED
  systemctl show omnigraph-rewrite.service -p Environment | tr " " "\n" | grep OMNIGRAPH_LOCAL_EMBED
'
# 每个都应输出 2 行：OMNIGRAPH_LOCAL_EMBED=1 + OMNIGRAPH_LOCAL_EMBED_URL=...
```

**回退：** 删除所有 drop-in 即可
```bash
ssh aliyun-old 'rm -rf /etc/systemd/system/omnigraph-*.service.d && systemctl daemon-reload'
```

---

## 7. 重迁向量数据到 BGE-M3（方向由 Phase 1.3 决定）

> ⚠ **前置：必须先完成 Phase 1.3 确认旧机主存储（Qdrant 或 NanoVectorDB），本节按不同后端选择脚本。**
> 共同点：逐条（或分批）读取旧向量 → embed-server 重算 1024d → 写入 `bge_m3_1024d` 新集合。

```bash
# 7.0 按 Phase 1.3 结果选择迁移脚本
# 后端 = Qdrant：用 scroll + re-embed（新机 migrate_all_bounded.py 的 Qdrant 变体，改 Qdrant 源）
# 后端 = NanoVDB：用新机 migrate_all_bounded.py（JSON 源，mmap 流式），逐条 embed 写入 Qdrant
# 无论哪种：embed URL 改 http://127.0.0.1:7997/embeddings，collection 后缀 _bge_m3_1024d
```

```bash
# 7.1 停止所有 ingest timer（防止写入冲突）
ssh aliyun-old '
  systemctl stop omnigraph-daily-ingest.timer
  systemctl stop omnigraph-afternoon-ingest.timer
  systemctl stop omnigraph-evening-ingest.timer
  echo "ingest timers stopped"
'

# 7.2 创建目标 Qdrant collections
ssh aliyun-old '
cd /root/OmniGraph-Vault
source venv-aim1/bin/activate
python3 << "PY"
from qdrant_client import QdrantClient, models
c = QdrantClient(url="http://127.0.0.1:6333", timeout=10)

for name in ["entities", "chunks", "relationships"]:
    coll = f"lightrag_vdb_{name}_bge_m3_1024d"
    # 删除可能存在的旧同名集合
    try:
        c.delete_collection(coll)
        print(f"deleted {coll}")
    except Exception:
        pass
    c.create_collection(
        collection_name=coll,
        vectors_config=models.VectorParams(
            size=1024,
            distance=models.Distance.COSINE,
            on_disk=True,               # 向量落盘，双 collection 并存期防 OOM
        ),
        on_disk_payload=True,           # payload 落盘
        hnsw_config=models.HnswConfigDiff(m=0),       # bulk load 期间关 HNSW 索引
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0),  # 延迟建索引
    )
    print(f"created {coll}")
print("all collections created")
PY
'
```

**验证：**
```bash
ssh aliyun-old 'curl -sf http://127.0.0.1:6333/collections | python3 -c "
import sys,json
cols=json.load(sys.stdin)[\"result\"][\"collections\"]
[print(c[\"name\"]) for c in cols]
"'
# 预期: 6 个集合（3 个 gemini_embedding_2_3072d + 3 个 bge_m3_1024d）
```

### 7.3 运行迁移脚本（核心）

拷贝新机的 `migrate_all_bounded.py` 并适配：

```bash
# 拷贝迁移脚本
scp aliyun-new:/root/OmniGraph-Vault/deploy/migrate_all_bounded.py /tmp/migrate_all_bounded.py

# 修改嵌入 URL 为本地（新机脚本硬编码了 embed URL）
# 检查脚本中的 embed URL 配置
grep -n "embed\|7997\|dense\|vector" /tmp/migrate_all_bounded.py | head -10
```

**如果脚本需改动，关键修改点：**
- 嵌入 URL 指向 `http://127.0.0.1:7997/embeddings`
- 目标 Qdrant collection 名使用 `bge_m3_1024d` 后缀
- 向量维度 1024

```bash
# 传入旧机并执行（预计 30-60 分钟，取决于数据量和 embed-server 吞吐）
scp /tmp/migrate_all_bounded.py aliyun-old:/root/OmniGraph-Vault/deploy/migrate_all_bounded.py

ssh aliyun-old '
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  python3 deploy/migrate_all_bounded.py
'
```

**监控：**
```bash
# 另开终端
watch -n 10 "ssh aliyun-old 'curl -sf http://127.0.0.1:6333/collections/lightrag_vdb_entities_bge_m3_1024d/points/count -d \"{\\\"exact\\\":true}\" | python3 -c \"import sys,json; print(json.load(sys.stdin)[\\\"result\\\"][\\\"count\\\"])\"'"
```

**验证迁移结果：**
```bash
ssh aliyun-old 'for coll in entities chunks relationships; do
  echo -n "lightrag_vdb_${coll}_bge_m3_1024d: "
  curl -sf "http://127.0.0.1:6333/collections/lightrag_vdb_${coll}_bge_m3_1024d/points/count" \
    -d "{\"exact\":true}" | python3 -c "import sys,json; print(json.load(sys.stdin)[\"result\"][\"count\"])"
done'
```

---

## 8. 打 LightRAG monkey patch（entity_name）

```bash
# 8.1 确认旧机 LightRAG operate.py 路径
ssh aliyun-old 'find /root/OmniGraph-Vault/venv-aim1 -name operate.py -path "*/lightrag/*" | head -1'
# 预期: /root/.../lightrag/operate.py

# 8.2 检查旧机 LightRAG 版本（1.4.16 vs 新机 1.5.4）
ssh aliyun-old '
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  python3 -c "import lightrag; print(lightrag.__version__)"
'

# 8.3 前置验证：1.4.16 中 entity_name 读取模式是否与新机相同（**必须输出匹配行**）
ssh aliyun-old 'grep -n "entity_name" /root/OmniGraph-Vault/venv-aim1/lib/python3.11/site-packages/lightrag/operate.py | grep "for.*in.*results"'
# 如果无输出 → 1.4.16 的 entity 读取逻辑不同（可能无此 bug 或 patch 点不同），
#   停下，先定位 1.4.16 实际读取 Qdrant payload 的代码再决定是否 patch
# 如果输出类似 "node_ids = [r[\"entity_name\"] for r in results]" → 继续 8.4
```

根据实际行号执行 patch。脚本：

```bash
ssh aliyun-old 'python3 << "PY"
import re

FILES = [
    "/root/OmniGraph-Vault/venv-aim1/lib/python3.11/site-packages/lightrag/operate.py",
]

for path in FILES:
    with open(path) as f:
        src = f.read()

    old = 'node_ids = [r["entity_name"] for r in results]'
    new = 'node_ids = [r.get("entity_name", r.get("__id__", str(i))) for i, r in enumerate(results)]'

    if old not in src:
        print(f"SKIP {path}: pattern not found")
        continue

    with open(path + ".bge-backup", "w") as f:
        f.write(src)
    src2 = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src2)
    print(f"PATCHED {path}")
PY
'
```

---

## 9. 灰度验证：单篇文章 ingest 端到端

在确认全量迁移和代码改动正确前，先跑一篇文章验证端到端通路：

```bash
# 9.1 启动 embed-server（如未启动）
ssh aliyun-old 'systemctl start embed-server && sleep 5 && systemctl is-active embed-server'

# 9.2 测试单篇 ingest（选文章库中已有的一篇）
ssh aliyun-old '
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  export OMNIGRAPH_LOCAL_EMBED=1
  export OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
  python3 ingest_wechat.py "https://mp.weixin.qq.com/s/A_TEST_URL" --dry-run 2>&1 | tail -20
'
```

**验证：**
- ingest 日志中不应出现 `Vertex AI`、`gemini-embedding-2`
- 应出现 `local embed` 或 `localhost:7997`
- Qdrant 新 collection 点数应 +1

```bash
# 验证 Qdrant 点数增加
ssh aliyun-old 'curl -sf http://127.0.0.1:6333/collections/lightrag_vdb_entities_bge_m3_1024d/points/count -d "{\"exact\":true}" | python3 -c "import sys,json; print(json.load(sys.stdin)[\"result\"][\"count\"])"'
```

---

## 10. 恢复定时任务

```bash
ssh aliyun-old '
  systemctl start omnigraph-daily-ingest.timer
  systemctl start omnigraph-afternoon-ingest.timer
  systemctl start omnigraph-evening-ingest.timer
  systemctl list-timers --no-pager | grep omnigraph
'
```

**⚠ 注意：** 前几个 cron 执行时需人工观察日志，确认无 Vertex AI / Gemini embedding 调用：

```bash
ssh aliyun-old 'journalctl -u omnigraph-daily-ingest -f | grep -E "embed|Embed|7997|vertex|gemini"'
```

---

## 11. 清理（7 天后，确认稳定）

```bash
# 11.1 删除旧 Gemini collections（释放 Qdrant 空间）
ssh aliyun-old '
  curl -X DELETE http://127.0.0.1:6333/collections/lightrag_vdb_entities_gemini_embedding_2_3072d
  curl -X DELETE http://127.0.0.1:6333/collections/lightrag_vdb_chunks_gemini_embedding_2_3072d
  curl -X DELETE http://127.0.0.1:6333/collections/lightrag_vdb_relationships_gemini_embedding_2_3072d
'

# 11.2 清理 .env 中的 Gemini/Vertex 变量
ssh aliyun-old '
  sed -i "/GEMINI_API_KEY/d" /root/.hermes/.env
  sed -i "/GOOGLE_APPLICATION_CREDENTIALS/d" /root/.hermes/.env
  sed -i "/OMNIGRAPH_EMBEDDING_KEYS/d" /root/.hermes/.env
  sed -i "/GOOGLE_GENAI_USE_VERTEXAI/d" /root/.hermes/.env
  sed -i "/OMNIGRAPH_GEMINI_KEY/d" /root/.hermes/.env
  sed -i "/OMNIGRAPH_VERTEX_SA/d" /root/.hermes/.env
  echo "cleaned .env"
'

# 11.3 清理 /models 下载缓存（保留实际模型文件）
ssh aliyun-old 'ls /models/bge-m3/ && du -sh /models/bge-m3/'
```

---

## 12. 回退方案

如果验证失败或 ingest 异常，恢复到 Gemini：

```bash
# 恢复代码
ssh aliyun-old '
  cp /root/backups/bge-m3-migration-*/models.py /root/OmniGraph-Vault/lib/models.py
  cp /root/backups/bge-m3-migration-*/lightrag_embedding.py /root/OmniGraph-Vault/lib/lightrag_embedding.py
  cp /root/backups/bge-m3-migration-*/.env /root/.hermes/.env
'

# 回退 systemd units（git 重新部署或手动还原）

# 停止 embed-server
ssh aliyun-old 'systemctl stop embed-server && systemctl disable embed-server'

# 重启 ingest
ssh aliyun-old 'systemctl restart omnigraph-daily-ingest.timer'
```

---

## 13. 搬迁后的同步配置（TODO — 独立实现）

两台机统一 BGE-M3 嵌入后，Qdrant collection 结构一致，可配置定期同步。

> **TODO（本计划不含）：** 待 Phase 1-12 验证通过后，独立设计同步方案
> （候选：旧机 `qdrant-snapshot.timer` 后追加 snapshot → scp → 新机 recover；
> 或旧机 ingest 双写新机 Qdrant。需确认 Qdrant snapshot 流式传输的可行性后定稿。）

---

## 执行顺序总结

```
1. 前置准备 ───→ ✓ 备份完成
1.3 后端确认 ──→ ⛔ GATE：Qdrant vs NanoVDB 主存储判定，决定 Phase 7 脚本方向
2. 安装模型 ───→ ✓ FlagEmbedding + BGE-M3 下载成功
3. embed-server → ✓ :7997 返回 1024d 向量
4. 更新代码 ───→ ✓ models.py + lightrag_embedding.py
5. 更新 .env ──→ ✓ OMNIGRAPH_LOCAL_EMBED=1（幂等写入）
6. 更新 systemd ─→ ✓ per-unit drop-in 注入 env vars
7. 重迁 Qdrant ─→ ✓ bge_m3_1024d 三集合点数匹配（脚本取决于 1.3）
8. monkey patch → ✓ entity_name fallback（先 8.3 验证 1.4.16 模式）
9. 灰度验证 ───→ ✓ 单篇 ingest 通
10. 恢复定时 ──→ ✓ ingest timers 启动
11. 观察 7 天 ──→ ✓ 零 Vertex AI 调用
12. 清理 ─────→ ✓ 删 Gemini 集合 + .env 变量
13. 同步配置 ──→ TODO 独立实现
```
