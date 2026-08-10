# OmniGraph MCP Server — Quick Start

让外部 AI（Hermes、Vitaclaw、Claude 等）通过 MCP 协议查询 OmniGraph 知识图谱。

## 架构

```
┌─ Aliyun (采集层) ─────────────────┐
│  KOL scan → ingest → SQLite       │
│  (轻量, 不需要大内存)              │
└──────────────┬────────────────────┘
               │ 定期 rsync
               ▼
┌─ WSL 本机 (服务层) ───────────────┐
│  Qdrant (:6333) — 向量数据库      │
│  kb-api (:8766) — FastAPI + LightRAG │
│  MCP server (:8767) — AI agent 接口 │
│  (独占大内存, 稳定不 OOM)          │
└──────────────┬────────────────────┘
               │ ohca.ddns.net:8766/8767
               ▼
┌─ 外部 AI ─────────────────────────┐
│  Hermes, Vitaclaw K8s, Claude     │
└───────────────────────────────────┘
```

## 前置条件

### 1. 增加 WSL 内存

编辑 Windows 上的 `%USERPROFILE%\.wslconfig`：

```ini
[wsl2]
memory=24GB          # 从 8G 改到 24G
swap=16GB
vmIdleTimeout=-1
firewall=false
networkingMode=mirrored
dnsTunneling=true

[experimental]
hostAddressLoopback=true
```

然后 **PowerShell 管理员**执行：

```powershell
wsl --shutdown
```

重新打开 WSL 终端即可生效。

### 2. 路由器端口转发

在路由器上添加 3 条端口映射（指向 WSL 所在 Windows 机器的内网 IP）：

| 外部端口 | 内部 IP:端口 | 用途 |
|----------|-------------|------|
| 8766 | 192.168.x.x:8766 | kb-api (知识库 API) |
| 8767 | 192.168.x.x:8767 | MCP server (AI agent 接口) |
| 6333 | 192.168.x.x:6333 | Qdrant (可选, 用于远程写入) |

> WSL2 `networkingMode=mirrored` 模式下，WSL 绑定的端口直接暴露在 Windows 宿主 IP 上，不需要额外端口转发。

### 3. Docker Desktop 运行中

WSL 上需要有 Docker 运行。确认：

```bash
docker ps
```

## 一键部署

```bash
cd /home/sztimhdd/OmniGraph-Vault
chmod +x deploy/migrate_kg_to_wsl.sh
./deploy/migrate_kg_to_wsl.sh
```

脚本会自动：
1. 检查内存、Docker、SSH
2. 停止阿里云上的 kb-api 和 Qdrant
3. rsync LightRAG 图数据 (4.2G)
4. rsync SQLite 文章库
5. 在 WSL 上启动 Qdrant (Docker)
6. 导入 Qdrant 向量数据
7. 创建 Python venv + 装依赖
8. 启动 kb-api (:8766)
9. 启动 MCP server (:8767)
10. 运行 smoke test

## Hermes 配置

编辑 `~/.hermes/config.yaml`，在 `mcp_servers:` 段添加：

```yaml
  omnigraph:
    url: http://127.0.0.1:8767/mcp
    timeout: 300
```

重启 Hermes 生效：

```bash
# CLI 模式
/reload-mcp

# Gateway 模式 (Telegram/Discord)
systemctl --user restart hermes-gateway
```

## 可用工具（5 个）

| 工具 | 功能 | 延迟 |
|------|------|------|
| `mcp_omnigraph_fts_search` | 全文关键词搜索文章 | <1s |
| `mcp_omnigraph_kg_query` | 知识图谱语义查询 | 30-120s |
| `mcp_omnigraph_synthesize` | 深度 Q&A 合成（带引用） | 60-300s |
| `mcp_omnigraph_get_article` | 取文章全文 + 实体 | <1s |
| `mcp_omnigraph_health` | 健康检查 | <1s |

## 验证

部署完成后验证：

```bash
# 本地测试
curl http://127.0.0.1:8766/health
curl "http://127.0.0.1:8766/api/search?q=OpenClaw&mode=fts&limit=3"

# 外部测试 (端口转发配置后)
curl http://ohca.ddns.net:8766/health

# MCP 测试
curl http://127.0.0.1:8767/health
```

## 单元测试

```bash
cd /home/sztimhdd/OmniGraph-Vault
venv-aim1/bin/python -m pytest tests/test_omni_mcp.py -v
```

## 数据同步

阿里云采集层持续扫描入库，WSL 需要定期同步最新数据：

```bash
# 手动同步 (运行此命令刷新 KG)
rsync -avz vitaclaw-aliyun:/root/.hermes/omonigraph-vault/lightrag_storage/ \
    /home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/

rsync -avz vitaclaw-aliyun:/root/OmniGraph-Vault/data/kol_scan.db \
    /home/sztimhdd/OmniGraph-Vault/data/kol_scan.db

# 同步后重启 kb-api
pkill -f "uvicorn kb.api:app"
# 然后重新启动 (见 deploy/migrate_kg_to_wsl.sh Step 8)
```

## 服务管理

```bash
# 查看进程
ps aux | grep -E "kb.api|mcp_server|qdrant"

# 查看日志
tail -f /tmp/kb-api-wsl.log
tail -f /tmp/omni-mcp-wsl.log
docker logs -f qdrant

# 停止
pkill -f "kb.api"
pkill -f "mcp_server"
docker stop qdrant
```
