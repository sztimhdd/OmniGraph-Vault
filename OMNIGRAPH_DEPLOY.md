# OmniGraph 部署文档 — ack-node-2-kg

> **服务器：** 阿里云杭州 ECS `47.103.73.20`（内网 `172.18.12.150`）  
> **OS：** Ubuntu 22.04.5 LTS · **RAM：** 14 GB + 8 GB swap · **Python：** 3.10.12  
> **代码仓库：** `/root/OmniGraph-Vault` · **虚拟环境：** `venv-aim1`

---

## 架构

```
外部 MCP 客户端 ──→ :8767 (MCP Server, FastMCP)
                         │ HTTP proxy
                    :8766 (KB-API, FastAPI + LightRAG)
                         │
                    ┌────┴────┐
                    │         │
               :7997      :6333
           embed-server   Qdrant
          (BGE-M3 1024d) (Docker)
```

| 服务 | 端口 | 绑定 | systemd unit | 说明 |
|---|---|---|---|---|
| **Qdrant** | 6333 | `127.0.0.1` + `172.18.12.150` | Docker `--restart=always` | 向量数据库，`on_disk=true` |
| **embed-server** | 7997 | `0.0.0.0` | `embed-server.service` | BGE-M3 本地嵌入 HTTP |
| **KB-API** | 8766 | `127.0.0.1` | `omni-kb-api.service` | LightRAG + FTS 搜索 |
| **MCP Server** | 8767 | `0.0.0.0` | `omni-mcp.service` | FastMCP，代理到 KB-API |
| **Health** | 8768 | `0.0.0.0` | 内嵌于 MCP | `GET /health` → `{"status":"ok"}` |

所有服务均 `systemctl enable`，开机自启。

---

## 组件详解

### 1. Qdrant（向量数据库）

```bash
docker run -d --name qdrant \
  -p 127.0.0.1:6333:6333 \
  -p 127.0.0.1:6334:6334 \
  -p 172.18.12.150:6333:6333 \
  -v /root/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:v1.11.5
```

**Collections（BGE-M3 1024 维）：**

| Collection | 点数 | 说明 |
|---|---|---|
| `lightrag_vdb_entities_bge_m3_1024d` | 70,671 | 实体节点 |
| `lightrag_vdb_chunks_bge_m3_1024d` | 5,552 | 文本块 |
| `lightrag_vdb_relationships_bge_m3_1024d` | 96,684 | 关系边 |
| **合计** | **172,907** | |

旧 Gemini 3072d collections 保留作为回滚保险，48h 后可删。

### 2. embed-server（BGE-M3 本地嵌入）

**文件：** `/root/OmniGraph-Vault/embed_server.py`

- 模型：`BAAI/bge-m3`（`local_files_only=True`）
- 端点：`POST :7997/embeddings` → `{"input": "text", "model": "bge-m3"}`
- 内存占用：~2.5 GB
- 不依赖 Google / 翻墙

**systemd：**
```ini
[Service]
Environment=EMBED_MODEL_PATH=/models/bge-m3/models/BAAI--bge-m3/snapshots/master
Environment=EMBED_PORT=7997
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/embed_server.py
Restart=always
```

### 3. KB-API（LightRAG + FTS 搜索）

**文件：** `/root/OmniGraph-Vault/kb/api.py`

```bash
uvicorn kb.api:app --host 127.0.0.1 --port 8766 --workers 1
```

**端点：**

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | `{"status":"ok","version":"v2.0.0"}` |
| `/api/search?q=...&mode=fts&limit=...` | GET | 全文检索，同步，<100ms |
| `/api/search?q=...&mode=kg` | GET | KG 检索，异步，返回 `{job_id}` |
| `/api/search/{job_id}` | GET | 轮询 KG 结果 |

**关键配置：**
```ini
# systemd unit
Environment=OMNIGRAPH_VECTOR_STORAGE=qdrant
Environment=QDRANT_URL=http://127.0.0.1:6333
Environment=OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1

# dropin: /etc/systemd/system/omni-kb-api.service.d/embed.conf
Environment=OMNIGRAPH_LOCAL_EMBED=1
Environment=OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
```

**LLM：** DeepSeek（`deepseek-v4-flash`，通过 `lib/llm_deepseek.py`）  
**嵌入：** BGE-M3 本地 `:7997`（设置 `OMNIGRAPH_LOCAL_EMBED=1`）  
**`.env` 必需变量：**
```
DEEPSEEK_API_KEY=sk-...
OMNIGRAPH_LOCAL_EMBED=1
OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings
```

### 4. MCP Server（对外服务）

**文件：** `/root/OmniGraph-Vault/mcp_server_standalone.py`

- 协议：FastMCP StreamableHTTP
- 纯 HTTP 代理到 KB-API，不初始化 LightRAG（零 collection 风险）
- 2 工具：`fts_search`、`kg_search`

**客户端配置：**
```json
{
  "mcpServers": {
    "omnigraph": {
      "url": "http://47.103.73.20:8767/mcp",
      "transport": "streamable-http",
      "headers": {
        "Accept": "application/json, text/event-stream"
      },
      "timeout": 300
    }
  }
}
```

---

## 防火墙 / 安全组

**iptables（已持久化 `/etc/iptables/rules.v4`）：**
```
ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  tcp dpt:8767
ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  tcp dpt:8768
```

**阿里云安全组（控制台）：** 需放行 TCP **8767**（MCP）和 **8768**（health）。

---

## 数据备份 / 恢复

源 NanoVectorDB 文件仍保留在 `/root/.hermes/omonigraph-vault/lightrag_storage/`（合计 ~3.6 GB）：

| 文件 | 记录数 |
|---|---|
| `vdb_entities.json` | 94,557 |
| `vdb_chunks.json` | 6,198 |
| `vdb_relationships.json` | 112,037 |

**重迁到 Qdrant：** 使用 `/root/OmniGraph-Vault/deploy/migrate_all_bounded.py`（mmap 流式解析，限制 6 GB 虚拟内存）。

**Qdrant 快照备份：**
```bash
# 创建快照
curl -X POST http://127.0.0.1:6333/collections/{name}/snapshots
# 下载
curl http://127.0.0.1:6333/collections/{name}/snapshots/{snapshot_name} -o backup.snapshot
```

---

## 已知问题 & 修复

### 1. LightRAG entity_name KeyError ❗

**症状：** KG 查询报 `KeyError: 'entity_name'`（`operate.py:5162`）

**根因：** LightRAG v1.5.4 查询时从 Qdrant payload 读取 `entity_name`，部分实体缺失此字段。

**修复（已应用）：**
```python
# /root/OmniGraph-Vault/venv-aim1/lib/python3.10/site-packages/lightrag/operate.py:5162
# 原代码：
node_ids = [r["entity_name"] for r in results]
# 修复后：
node_ids = [r.get("entity_name", r.get("__id__", str(i))) for i, r in enumerate(results)]
```
备份文件：`operate.py.bak`

### 2. Collection 命名（bge-m3 vs bge_m3）

LightRAG 将模型名中的连字符规范化为下划线。迁移脚本创建的 `bge-m3` collections 在 LightRAG 初始化时不可见。

**修复（已应用）：** 通过 Qdrant snapshot → recover 克隆 `bge-m3` → `bge_m3`。

### 3. MCP 跨公网间歇超时

**症状：** Hermes/Claude Code 客户端偶尔 `ConnectTimeout`，3 次重试后 park。

**根因：** 阿里云单 ECS 公网直连，跨境 TCP ~10% 丢包。

**缓解措施：**
- `/health` 端点（`:8768`）供客户端轻量探测
- Hermes 用户：`/mcp reconnect omnigraph` + `/new`
- 根本方案：前面加阿里云 SLB（负载均衡 + 健康检查）

---

## 运维命令

```bash
# 查看所有服务
systemctl status embed-server omni-kb-api omni-mcp

# 查看日志
journalctl -u omni-kb-api -f
journalctl -u omni-mcp -f
tail -f /var/log/embed-server.log

# 健康检查
curl http://127.0.0.1:8766/health     # KB-API
curl http://127.0.0.1:8768/health     # MCP health（轻量）
curl http://127.0.0.1:7997/health     # embed-server

# 测试 MCP 工具
curl -X POST http://127.0.0.1:8767/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# 内存
free -h
docker stats qdrant --no-stream

# 重启单个服务
systemctl restart omni-kb-api
```

---

## 代码关键文件

| 文件 | 说明 |
|---|---|
| `/root/OmniGraph-Vault/mcp_server_standalone.py` | MCP 服务入口 |
| `/root/OmniGraph-Vault/kb/api.py` | KB-API 入口 |
| `/root/OmniGraph-Vault/kb/api_routers/search.py` | `/api/search` 端点 |
| `/root/OmniGraph-Vault/embed_server.py` | BGE-M3 嵌入服务 |
| `/root/OmniGraph-Vault/kg_synthesize.py` | LightRAG 合成入口 |
| `/root/OmniGraph-Vault/lib/models.py` | `EMBEDDING_DIM=1024, EMBEDDING_MODEL="bge-m3"` |
| `/root/OmniGraph-Vault/lib/lightrag_embedding.py` | 嵌入函数（本地/Vertex 双路径） |
| `/root/OmniGraph-Vault/lib/llm_deepseek.py` | DeepSeek LLM 客户端 |
| `/root/OmniGraph-Vault/lib/llm_complete.py` | LLM 提供者路由 |
