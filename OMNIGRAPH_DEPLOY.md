# OmniGraph 部署文档 — ack-node-2-kg

> **服务器：** 阿里云杭州 ECS `47.103.73.20`（内网 `172.18.12.150`）  
> **OS：** Ubuntu 22.04.5 LTS · **RAM：** 14 GB + 8 GB swap · **Python：** 3.10.12  
> **代码仓库：** `/root/OmniGraph-Vault` · **虚拟环境：** `venv-aim1`
>
> **⚠️ 数据新鲜度警告：** 本机 KG 数据冻结于 2026-07-31 快照（172,907 点）。
> 无增量同步机制。当前**不能保证查询到 2026-08-01 之后的文章**。
> 最新数据在建图机 `47.117.244.253`（234k+ 点，持续 ingest）。
> 解决后删除本警告。见 `.planning/REPAIR-PLAN-2026-08-04.md` T4。

> **最后验证：** 2026-08-04 — Ponytail 审计后全量修正。
> 取证命令见各节 `verify:` 标签。

---

## 架构

```
外部 MCP 客户端 ──→ :8767 (MCP Server, FastMCP StreamableHTTP)
                         │ HTTP proxy
                    :8766 (KB-API, FastAPI + LightRAG)
                         │
                    ┌────┴────┐
                    │         │
               :7997      :6333
           embed-server   Qdrant
          (BGE-M3 1024d) (Docker, on_disk=true)
```

| 服务 | 端口 | 绑定 | systemd unit | 状态(2026-08-04) |
|---|---|---|---|---|
| **Qdrant** | 6333 | `127.0.0.1` + `172.18.12.150` | Docker `--restart=always` | ✅ Up 5 days |
| **embed-server** | 7997 | `0.0.0.0` | `embed-server.service` | BGE-M3 本地嵌入 HTTP |
| **KB-API** | 8766 | `127.0.0.1` | `omni-kb-api.service` | LightRAG + FTS 搜索 |
| **MCP Server** | 8767 | `0.0.0.0` | `omni-mcp.service` | FastMCP，代理到 KB-API |
| **Health** | 8768 | `0.0.0.0` | 内嵌于 MCP | `GET /health` → `{"status":"ok"}` |

所有服务均 `systemctl enable`，开机自启。
verify: `systemctl is-enabled embed-server omni-kb-api omni-mcp && systemctl is-active embed-server omni-kb-api omni-mcp`

---

## 组件详解

### 1. Qdrant（向量数据库）

```bash
docker run -d --name qdrant \
  --restart=always \
  -p 127.0.0.1:6333:6333 \
  -p 127.0.0.1:6334:6334 \
  -p 172.18.12.150:6333:6333 \
  -v /root/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:v1.11.5
```
verify: `docker inspect qdrant --format '{{.HostConfig.RestartPolicy.Name}}'` → `always`

**Collections（BGE-M3 1024 维，2026-08-04 快照）：**

| Collection | 点数 | 说明 |
|---|---|---|
| `lightrag_vdb_entities_bge_m3_1024d` | 70,671 | 实体节点 |
| `lightrag_vdb_chunks_bge_m3_1024d` | 5,552 | 文本块 |
| `lightrag_vdb_relationships_bge_m3_1024d` | 96,684 | 关系边 |
| **合计** | **172,907** | |
verify: `curl -s http://127.0.0.1:6333/collections | python3 -c "import sys,json;[print(c['name'],c['points_count']) for c in json.load(sys.stdin)['result']['collections']]"`

### Gemini 3072d 旧 collections 退役清单

**当前状态：** 保留作为回滚保险。**禁止删除**，直到以下条件全部满足：

- [ ] 新机 KG 同步管道就绪，查询 8/1+ 文章验证通过
- [ ] BGE-M3 Qdrant collections 连续 7 天无 entity_name KeyError
- [ ] embed-server 连续 7 天无重启
- [ ] 创建 Qdrant snapshot 备份到异地（`curl -X POST :6333/collections/{name}/snapshots`）
- [ ] snapshot 下载验证：SHA256 校验通过
- [ ] 旧机 BGE-M3 生产稳定运行 ≥14 天（参考 `BGE_M3_MIGRATION.md`）

**删除命令（所有条件满足后执行）：**
```bash
for coll in lightrag_vdb_entities_gemini_embedding_2_3072d \
            lightrag_vdb_chunks_gemini_embedding_2_3072d \
            lightrag_vdb_relationships_gemini_embedding_2_3072d; do
  curl -X DELETE "http://127.0.0.1:6333/collections/$coll"
done
```

### 2. embed-server（BGE-M3 本地嵌入）

**文件：** `/root/OmniGraph-Vault/embed_server.py` — 已纳入 Git（commit `04b3907`）
SHA256: `1ddb117a7930bf3944202bc1f9e66d293a458be3894e9d1a8c4ab198bcce9556`

- 模型：`BAAI/bge-m3`（`local_files_only=True`）
- 端点：`POST :7997/embeddings` → `{"input": "text", "model": "bge-m3"}`
- 内存占用：~2.5 GB（2026-07-30 实测）
- 不依赖 Google / 翻墙
verify: `curl -sf -X POST :7997/embeddings -H 'Content-Type: application/json' -d '{"input":["test"]}' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["data"][0]["embedding"]))'` → `1024`

**systemd：**
```ini
[Service]
Environment=EMBED_MODEL_PATH=/models/bge-m3/models/BAAI--bge-m3/snapshots/master
Environment=EMBED_PORT=7997
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/embed_server.py
Restart=always
MemoryMax=5G
```
verify: `systemctl show embed-server.service -p Environment -p ExecStart -p MemoryMax`

### 3. KB-API（LightRAG + FTS 搜索）

**文件：** `/root/OmniGraph-Vault/kb/api.py`

```bash
uvicorn kb.api:app --host 127.0.0.1 --port 8766 --workers 1
```

**端点：**

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | `{"status":"ok","version":"v2.0.0"}` |
| `/api/search?q=...&mode=fts&limit=...` | GET | 全文检索，同步（2026-07-30 实测 ~50-150ms p50） |
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
verify: `systemctl show omni-kb-api.service -p Environment | tr ' ' '\n' | grep OMNIGRAPH`

**LLM：** DeepSeek（`deepseek-v4-flash`，通过 `lib/llm_deepseek.py`）  
**嵌入：** BGE-M3 本地 `:7997`（设置 `OMNIGRAPH_LOCAL_EMBED=1`）  
**⚠ 环境变量优先级：** systemd drop-in `Environment=` > 代码 `os.getenv()` default > `.env`。
`.env` 中的变量对 systemd 服务**不生效**（systemd 不自动读取 `.env`），必须通过 drop-in 注入。

**`.env` 必需变量（仅供非 systemd 手动运行，systemd 服务通过 drop-in 注入）：**
```
DEEPSEEK_API_KEY=sk-...
```

### 4. MCP Server（对外服务）

**文件：** `/root/OmniGraph-Vault/mcp_server_standalone.py` — 已纳入 Git（commit `04b3907`）
SHA256: `f80bd8229b13bf3cf3ff3342e2867b723377324c026b136f2bb0a3338bc0e992`

- 协议：FastMCP StreamableHTTP
- 纯 HTTP 代理到 KB-API，不初始化 LightRAG（零 collection 风险）
- 2 工具：`fts_search`、`kg_search`
- Health 通过独立线程 + 独立端口（`:8768`），不触碰 FastMCP internals

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

**⚠ 当前状态（2026-08-04）：** `0.0.0.0/0` 完全开放——无认证、无 TLS、无限流。
见 `.planning/REPAIR-PLAN-2026-08-04.md` H1 安全加固项。

**iptables（已持久化 `/etc/iptables/rules.v4`）：**
```
ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  tcp dpt:8767
ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0  tcp dpt:8768
```
verify: `iptables -L INPUT -n | grep -E '8767|8768'`

**阿里云安全组（控制台）：** 需放行 TCP **8767**（MCP）和 **8768**（health）。

---

## 数据备份 / 恢复

### 当前恢复源（2026-08-04）

| 恢复源 | 类型 | 数据范围 | 适用场景 |
|---|---|---|---|
| Qdrant BGE-M3 collections（172,907 点） | 主存储 | 冻结于 2026-07-31 | 单 collection 误删、索引损坏 |
| Qdrant snapshot | 快照备份 | 同主存储 | 全量恢复、迁移 |
| NanoVectorDB JSON（`lightrag_storage/vdb_*.json`） | **历史快照** | 94,557 entities / 6,198 chunks / 112,037 rels | **仅作参考**——比当前 Qdrant 少 ~60k 点，恢复会发生静默数据回退 |

**⚠ NanoVectorDB 不是当前恢复源。** 其数据为迁移前的快照，
点数少于当前 Qdrant。用它恢复会丢失 2026-07-31 之后的所有数据变更。
verify: `ls -lh /root/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json`

**Qdrant 快照备份（推荐恢复路径）：**
```bash
# 创建快照
curl -X POST http://127.0.0.1:6333/collections/{name}/snapshots
# 下载
curl http://127.0.0.1:6333/collections/{name}/snapshots/{snapshot_name} -o backup.snapshot
# 验证 SHA256
sha256sum backup.snapshot
```

---

## 已知问题 & 修复

### 1. LightRAG entity_name KeyError ❗

**症状：** KG 查询报 `KeyError: 'entity_name'`（`operate.py:5162`）

**根因：** LightRAG v1.5.4 查询时从 Qdrant payload 读取 `entity_name`，部分实体缺失此字段。

**修复（已应用，2026-07-30）：** venv site-packages monkey-patch。
详见 `scripts/patch_lightrag_entity_name.sh`（热补丁脚本，含前置断言和回归测试）。

**⚠ 重建 venv 或 `pip install --upgrade lightrag` 后补丁会丢失。** 执行：
```bash
bash /root/OmniGraph-Vault/scripts/patch_lightrag_entity_name.sh
```

**当前补丁代码（参考——不要手动执行）：**
```python
# /root/OmniGraph-Vault/venv-aim1/lib/python3.10/site-packages/lightrag/operate.py:5162
# 原代码：
node_ids = [r["entity_name"] for r in results]
# 修复后：
node_ids = [r.get("entity_name", r.get("__id__", str(i))) for i, r in enumerate(results)]
```
备份文件：`operate.py.bak`

**数据完整性验证：**
```bash
python3 -c "
from qdrant_client import QdrantClient
c = QdrantClient('http://localhost:6333')
pts, _ = c.scroll('lightrag_vdb_entities_bge_m3_1024d', limit=100, with_vectors=False)
missing = [p.id for p in pts if 'entity_name' not in p.payload]
print(f'{len(missing)}/100 missing entity_name')
"
```
verify: missing ≤ 5（容忍少量缺失，fallback 到 `__id__`）

### 2. Collection 命名（bge-m3 vs bge_m3）

LightRAG 将模型名中的连字符规范化为下划线。迁移脚本创建的 `bge-m3` collections 在 LightRAG 初始化时不可见。

**修复（已应用，2026-07-30）：** 通过 Qdrant snapshot → recover 克隆 `bge-m3` → `bge_m3`。

### 3. MCP 跨公网间歇超时

**症状：** Hermes/Claude Code 客户端偶尔 `ConnectTimeout`，3 次重试后 park。

**根因：** 阿里云单 ECS 公网直连，跨境 TCP 丢包。
实测丢包率（2026-07-30，`mtr --report 47.103.73.20` 从北美 VPS，100 包）：~8-12%。

**缓解措施：**
- `/health` 端点（`:8768`）供客户端轻量探测
- Hermes 用户：`/mcp reconnect omnigraph` + `/new`
- 本地 SSH 隧道绕开公网抖动：`ssh -N -L 8767:127.0.0.1:8767 aliyun-new`
- 根本方案：前面加阿里云 SLB（负载均衡 + 健康检查 + 自动摘除）

---

## 运维命令

```bash
# 查看所有服务
systemctl status embed-server omni-kb-api omni-mcp

# 查看日志
journalctl -u omni-kb-api -f
journalctl -u omni-mcp -f
tail -f /var/log/embed-server.log

# 健康检查（三级：进程存活 → 依赖就绪 → 深度状态）
curl http://127.0.0.1:8768/health          # MCP 进程存活（仅证明进程在跑）
curl http://127.0.0.1:8766/health          # KB-API 进程存活 + LightRAG 初始化成功
curl http://127.0.0.1:8766/api/search?q=test&mode=fts&limit=1  # 实际查询链路（KB-API + Qdrant + FTS5）
curl http://127.0.0.1:7997/health          # embed-server 进程存活

# 完整的端到端 MCP UAT（推荐替代裸 curl tools/list）
python3 /root/OmniGraph-Vault/scripts/mcp_uat.py

# 内存
free -h
docker stats qdrant --no-stream

# 重启单个服务
systemctl restart omni-kb-api
```

---

## 代码关键文件

| 文件 | 说明 | Git SHA (2026-08-04) |
|---|---|---|
| `mcp_server_standalone.py` | MCP 服务入口（FastMCP，代理到 KB-API） | `04b3907` |
| `embed_server.py` | BGE-M3 本地嵌入 HTTP 服务 | `04b3907` |
| `kb/api.py` | KB-API 入口 | tracked |
| `kb/api_routers/search.py` | `/api/search` 端点 | tracked |
| `lib/models.py` | `EMBEDDING_DIM=1024, EMBEDDING_MODEL="bge-m3"` | `04b3907` |
| `lib/lightrag_embedding.py` | 嵌入函数（本地 BGE-M3 / Vertex 双路径） | `04b3907` |
| `lib/llm_deepseek.py` | DeepSeek LLM 客户端 | tracked |
| `deploy/migrate_all_bounded.py` | NanoVectorDB→Qdrant 灾难恢复迁移 | `04b3907` |
| `scripts/patch_lightrag_entity_name.sh` | entity_name KeyError 热补丁 | TBD |

---

## 服务器漂移记录

**2026-08-04 Ponytail 审计发现：**
- 服务器 `/root/OmniGraph-Vault` **不是 git 仓库**（`.git` 目录不存在）
- 生产代码通过 scp/rsync 部署，无版本跟踪
- 以下生产文件已回收并纳入 Git（commit `04b3907`）：
  - `embed_server.py`
  - `mcp_server_standalone.py`
  - `lib/models.py`（BGE-M3 变更）
  - `lib/lightrag_embedding.py`（`_embed_local` 分支）

**剩余未跟踪文件（server-only，未纳入 Git）：**
- `kol_config.py` — WeChat token/cookie，`.gitignore`（含密钥）
- `kg_api.py` — 旧版 KG API（直接连 LightRAG，已废弃）
- `mcp_kg_server.py` — 旧版 MCP server（直接连 LightRAG，已废弃）
- `deploy/systemd/` — systemd unit 文件（部分可能与 Git `deploy/aliyun/systemd/` 不同）
verify: `ssh aliyun-new 'ls /root/OmniGraph-Vault/*.py' | while read f; do git ls-files -- "$(basename $f)" >/dev/null 2>&1 || echo "untracked: $f"; done`

### 重建部署检查清单

在新主机上从 Git 重建完整服务：

1. `git clone https://github.com/sztimhdd/OmniGraph-Vault.git /root/OmniGraph-Vault`
2. `cd /root/OmniGraph-Vault && python3 -m venv venv-aim1 && source venv-aim1/bin/activate && pip install -r requirements.txt`
3. 从备份恢复 `/models/bge-m3/`（4.3 GB，ModelScope 下载或从旧机 scp）
4. 从备份恢复 `/root/qdrant_storage/`（Qdrant 数据目录）
5. 从备份恢复 `/root/.hermes/.env`（含 `DEEPSEEK_API_KEY`）
6. 安装 systemd unit：`cp deploy/aliyun/systemd/*.service deploy/aliyun/systemd/*.timer /etc/systemd/system/ && systemctl daemon-reload`
7. 创建 drop-in：`/etc/systemd/system/omni-kb-api.service.d/embed.conf`
8. 运行 `scripts/patch_lightrag_entity_name.sh`
9. `systemctl enable --now embed-server omni-kb-api omni-mcp`
10. 运行 `scripts/mcp_uat.py` — 全部 8 项通过
