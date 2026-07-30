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
| 磁盘剩余 | 7.1 GB | 31 GB |
| 空闲内存 | 6.4 GB | 5.4 GB |
| systemd units | 30 个（ingest/kb-api 无） | 3 个（embed/kb-api/mcp） |
| LLM | DeepSeek | DeepSeek |

**风险点：**
- 磁盘仅剩 7.1 GB，BGE-M3 ~2.2 GB + 重迁临时文件 ~500 MB = 3 GB 余量，刚好够
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

# 1.3 确认 NanoVectorDB 源数据完整性
ssh aliyun-old '
  ls -lh /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json
'
# 预期: entities ~1.5G, relationships ~1.8G, chunks ~122M
# 不应有 .tmp 文件（如有说明上次写入未完成）
```

**验证：** 三个文件完整 + 备份已创建。

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
ssh aliyun-old '
  mkdir -p /models/bge-m3
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate
  python3 -c "
from FlagEmbedding import BGEM3FlagModel
model = BGEM3FlagModel(\"BAAI/bge-m3\", cache_dir=\"/models/bge-m3\")
print(\"model loaded OK\")
print(model.encode([\"test\"])[\"dense_vecs\"].shape)
"
'
# 预期: (1, 1024)

# 2.3 确认模型路径
ssh aliyun-old 'ls /models/bge-m3/models--BAAI--bge-m3/snapshots/*/'
# 记下 snapshots 后的 hash 目录名，用于 systemd 配置
```

**验证：** `FlagEmbedding` import 成功；`encode(["test"])` 返回 `(1, 1024)`。

---

## 3. 部署 embed-server

从新机拷贝文件到旧机：

```bash
# 3.1 拷贝 embed_server.py
scp aliyun-new:/root/OmniGraph-Vault/embed_server.py /tmp/embed_server.py
scp /tmp/embed_server.py aliyun-old:/root/OmniGraph-Vault/embed_server.py

# 3.2 修改 embed_server.py 中的模型路径（如需要）
# 检查新机的模型路径配置
ssh aliyun-new 'grep -n "model_path\|BGE\|FlagEmbedding\|snapshots" /root/OmniGraph-Vault/embed_server.py'

# 如果旧机 snapshots hash 不同，更新 embed_server.py
# EMBED_MODEL_PATH 通过 systemd env 传入，无需改代码
```

**创建 systemd unit：**

```bash
ssh aliyun-old 'cat > /etc/systemd/system/embed-server.service << "UNIT"
[Unit]
Description=Embedding Server (BGE-M3 1024d)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
Environment=EMBED_MODEL_PATH=/models/bge-m3/models--BAAI--bge-m3/snapshots/REPLACE_WITH_HASH
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
ssh aliyun-old 'cat >> /root/.hermes/.env << "ENV"

# BGE-M3 local embedding (replaces Gemini/Vertex)
OMNIGRAPH_LOCAL_EMBED=1
OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
ENV

# 确认写入
ssh aliyun-old 'grep "OMNIGRAPH_LOCAL_EMBED" /root/.hermes/.env'
# 预期: OMNIGRAPH_LOCAL_EMBED=1, OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
```

**不删除的旧变量（暂留 7 天做回退保险）：**
- `GEMINI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `OMNIGRAPH_EMBEDDING_KEYS`

---

## 6. 更新所有 ingest systemd unit（注入 embed env vars）

旧机有多个 ingest timer，需确保每个都能读到 `OMNIGRAPH_LOCAL_EMBED=1`+`OMNIGRAPH_LOCAL_EMBED_URL`。

方案：创建全局 drop-in 不现实（不同 unit 读取不同 env），最简是一次性 `sed` 批量追加。

```bash
ssh aliyun-old '
cd /etc/systemd/system
# 所有 omnigraph-*.service 且不含 backup 的，追加 embed env
for f in omnigraph-*.service; do
  [[ $f == *.bak* ]] && continue
  [[ $f == *.d ]] && continue
  # 检查是否已有 OMNIGRAPH_LOCAL_EMBED
  if ! grep -q "OMNIGRAPH_LOCAL_EMBED" "$f"; then
    echo "patching $f"
    # 在第一个 Environment= 行后追加
    sed -i "0,/^Environment=/s/^Environment=/Environment=OMNIGRAPH_LOCAL_EMBED=1\\nEnvironment=OMNIGRAPH_LOCAL_EMBED_URL=http:\\/\\/localhost:7997\\/embeddings\\nEnvironment=/" "$f"
  fi
done
systemctl daemon-reload
echo "done"
'
```

**验证：**
```bash
ssh aliyun-old 'grep -l "OMNIGRAPH_LOCAL_EMBED" /etc/systemd/system/omnigraph-*.service | wc -l'
# 预期: >= 15（所有活跃 unit）
```

---

## 7. 重迁 NanoVectorDB → Qdrant（BGE-M3 重嵌入）

这是最耗时步骤。思路同新机：遍历 NanoVectorDB JSON，逐条用本地 embed-server 重算 1024d 向量，写入新 Qdrant collection。

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
        vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
        on_disk_payload=True,
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

# 8.3 查找 entity_name 行（旧版可能在不同行）
ssh aliyun-old 'grep -n "entity_name.*for.*r.*in.*results" /root/OmniGraph-Vault/venv-aim1/lib/python3.11/site-packages/lightrag/operate.py'
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

## 13. 搬迁后的同步配置

两台机统一 BGE-M3 嵌入后，Qdrant collection 结构一致，可配置定期同步：

**方案 A：Qdrant snapshot → scp → recover（已有 qdrant-snapshot.timer）**

在旧机 `qdrant-snapshot.service` 末尾追加：

```bash
# 创建快照 → scp 到新机 → 新机 recover
ExecStartPost=/bin/bash -c '\
  for coll in entities chunks relationships; do \
    SNAP=$(curl -sf http://127.0.0.1:6333/collections/lightrag_vdb_${coll}_bge_m3_1024d/snapshots | python3 -c "import sys,json; print(json.load(sys.stdin)[\"result\"][-1][\"name\"])"); \
    curl -sf http://127.0.0.1:6333/collections/lightrag_vdb_${coll}_bge_m3_1024d/snapshots/$SNAP | ssh 172.18.12.150 "curl -X PUT http://127.0.0.1:6333/collections/lightrag_vdb_${coll}_bge_m3_1024d/snapshots/recover -H \"Content-Type: application/octet-stream\" --data-binary @-" ; \
  done'
```

**方案 B：旧机 ingest 时双写新机 Qdrant（需改 ingest 代码）**

```python
# 在 _persist_to_qdrant() 调用后追加
_fast_copy_to_remote_qdrant(entity_points, "172.18.12.150")
```

**推荐先完成搬迁验证，同步方案独立 quick 再实现。**

---

## 执行顺序总结

```
1. 前置准备 ───→ ✓ 备份完成
2. 安装模型 ───→ ✓ FlagEmbedding + BGE-M3 下载成功
3. embed-server → ✓ :7997 返回 1024d 向量
4. 更新代码 ───→ ✓ models.py + lightrag_embedding.py
5. 更新 .env ──→ ✓ OMNIGRAPH_LOCAL_EMBED=1
6. 更新 systemd ─→ ✓ 所有 unit 注入 env vars
7. 重迁 Qdrant ─→ ✓ bge_m3_1024d 三集合点数匹配
8. monkey patch → ✓ entity_name fallback
9. 灰度验证 ───→ ✓ 单篇 ingest 通
10. 恢复定时 ──→ ✓ ingest timers 启动
11. 观察 7 天 ──→ ✓ 零 Vertex AI 调用
12. 清理 ─────→ ✓ 删 Gemini 集合 + .env 变量
13. 同步配置 ──→ 独立 quick
```
