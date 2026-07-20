# OmniGraph 阿里云运维 Handoff — 2026-07-20

> 粘贴到新 Hermes session 作为第一条消息。包含连接方式、当前状态、已修复项、待处理项。

---

## 服务器连接

```
SSH: vitaclaw-aliyun (47.117.244.253, hostname iZj1imk39yc55iZ)
用户: root
密钥: ~/.ssh/id_ed25519 (已配)
仓库: /root/OmniGraph-Vault
运行时: /root/.hermes/omonigraph-vault/ (注意拼写: omonigraph, 不是 omnigraph)
虚拟环境: /root/OmniGraph-Vault/venv-aim1
环境变量: /root/.hermes/.env
```

首次连接验证身份：
```bash
ssh vitaclaw-aliyun 'hostname; readlink -f /root/OmniGraph-Vault; ls /root/OmniGraph-Vault/data/kol_scan.db'
# 期望: iZj1imk39yc55iZ /root/OmniGraph-Vault (文件存在)
```

---

## 当前生产状态 (2026-07-20 最新)

### 服务与定时任务

| 服务 | 状态 | 说明 |
|------|------|------|
| `omnigraph-daily-ingest.timer` | enabled, 每2h | 入库主调度 (UTC 00/2:00) |
| `omnigraph-kol-scan-batch@1` | oneshot | WeChat KOL 扫描，4 个分区 |
| `kb-api` | active | FastAPI + LightRAG + Qdrant, 端口 8766 |
| `qdrant` (docker) | running | 端口 6333/6334, v1.11.0 |
| `caddy` | active | 反向代理, 端口 80/443 |
| `mcp-healthcheck.timer` | enabled, 每15min | MCP 管道健康监测 (journalctl -u mcp-healthcheck) |
| `afternoon/evening-ingest.timer` | **disabled** | 已由每2h的 daily timer 替代 |

### 数据库 (`kol_scan.db`)

| 指标 | 值 |
|------|-----|
| `ingestions.ok` | 650 |
| `ingestions.failed` | 4 (全部 body-too-short，确定性失败) |
| `ingestions.skipped` | 4695 |
| WeChat backlog (未入库) | ~582 |
| RSS backlog (未入库) | ~654 |
| LightRAG doc_status | processed=1157, processing=0 |

### 核心参数

| 参数 | 值 | 位置 |
|------|-----|------|
| embedding 间隔 | 5.5s | `lib/lightrag_embedding.py:73` |
| embedding 并发 | 2 (共享 asyncio.Lock) | `ingest_wechat.py:418` + `lib/lightrag_embedding.py:72` |
| 每轮最大文章数 | 10 | systemd ExecStart |
|| 单篇超时下限 | 3600s | `batch_ingest_from_spider.py:160` |
| 正文最小长度 | 500 | `ingest_wechat.py:76` |
| DeepSeek L1 batch | 30 | `lib/article_filter.py` |
| DeepSeek L2 batch | 5 | `lib/article_filter.py` |
| Vertex 项目 | banded-totality-485901 (已付费) | `GOOGLE_CLOUD_PROJECT` |

---

## 近期已修复

### 修复 1: WeChat 凭证刷新 (2026-07-19/20)
- 通过 CDP (Edge :9223) 从登录后的 dashboard 提取 TOKEN + 16 cookies
- `slave_sid` 长度 192 字符 (完整，未截断)
- Token 必须先回根 URL 绑定 (CSRF)，再写入 `kol_config.py`
- Cookie 写入使用 AST 定位单行赋值，不假设多行格式
- 结果: KOL 扫描恢复，`15 ok / 0 failed`
- 技能已更新: `wechat-cdp-credential-refresh` 的 Step 4

### 修复 2: Vertex embedding 并发限流 (PR #5, merged)
- `lib/lightrag_embedding.py`: 新增 `_VERTEX_ADMISSION_LOCK = asyncio.Lock()`
- 间隔从 1.2s 提高到 5.5s (经验安全值)
- 新增回归测试: `test_concurrent_embed_once_respects_vertex_gap_lock`
- 结果: primary 429 = 0

### 修复 3: 短正文重复重试 (776a6f2, pushed to main)
- `batch_ingest_from_spider.py` `_build_topic_filter_query()` anti-join 增加 `OR status = 'failed'`
- 4 篇 body-too-short (article_id 1258/3149/3288/5089) 不再每轮重复进入候选
- 结果: 候选数从 298→294，body-too-short 错误 = 0

### 修复 4: MCP 管道全链路硬化 (2026-07-20)
- `batch_ingest_from_spider.py`: `ingest_article()` 抓取返回 None 时不再误报 `ok` (commit `fix: batch ingest`)
- `ingest_wechat.py`: Playwright MCP 工具名同步 — `browser_run_code_unsafe` → `browser_run_code`
- `ingest_wechat.py`: 增加 `Host: localhost:8931` header 通过 MCP host check
- `batch_ingest_from_spider.py`: 单篇超时下限 1800s→3600s，容纳大 entity 文章
- WSL 侧: `playwright-mcp.service` (systemd user) + `aliyun-tunnel.service` (SSH + systemd Restart=always)
- Windows: `EdgeCDP` Task Scheduler (登录时自动启动 Edge + CDP)
- 阿里云侧: `mcp-healthcheck.timer` (每 15 分钟检测)
- 零新依赖（不用 autossh，不用额外脚本）
- 详情: `~/.hermes/plans/2026-07-20_214500-omnigraph-pipeline-hardening.md`

---

## 已知待处理项

### 优先级 P1: 入库吞吐量低
- 单篇完整 pipeline (DeepSeek L1+L2 + Apify + Vision + LightRAG) 耗时 ~1500s
- 每 2 小时最多处理 ~4 篇
- 582+654 backlog 需要数天清空
- **不建议降低 5.5s 间隔** — 已验证 0 429
- 长期优化方向 (建议不作为当前阻塞):
  - Vision 描述从同步 pipeline 拆出
  - 预抓取 body 缓存到 DB
  - 多篇合并到同一 LightRAG batch insert

### 优先级 P2: 成功文章标题元数据
- 部分成功入库的文章日志显示 `Article: Untitled`
- 需确认标题是否正确写入 LightRAG doc 元数据 (非阻塞)

### 优先级 P3: Qdrant snapshot 超时
- `qdrant-snapshot` service 历史超时 (Result=timeout, ExecMainStatus=15)
- 在线 Qdrant 正常，仅 export/snapshot 有问题
- 独立根因，不与 embedding/scan 混修

---

## MCP 抓取链路

### 链路拓扑

```
Edge (Windows) → CDP :9223
     ↑
Playwright MCP (WSL) :8931
     ↑
SSH tunnel (systemd user) Aliyun:58931 ← WSL:8931
     ↑
ingest_wechat.py → http://127.0.0.1:58931/mcp
```

### 启动顺序

| 层级 | 组件 | 启动方式 | 自愈能力 |
|------|------|----------|---------|
| 1 | Edge CDP | Windows Task Scheduler (EdgeCDP) | 登录时自动 |
| 2 | Playwright MCP | `systemctl --user playwright-mcp` | Restart=always |
| 3 | SSH 隧道 | `systemctl --user aliyun-tunnel` | Restart=always (autossh 不用) |
| 4 | 健康检查 | `systemctl mcp-healthcheck.timer` | 15min 检测 + journal 告警 |

### 快速诊断

```bash
# WSL 侧
systemctl --user status playwright-mcp      # MCP 进程
systemctl --user status aliyun-tunnel        # SSH 隧道
ss -tlnp | grep -E "8931|9223"             # 端口监听
curl -s :9223/json/version                 # CDP 响应

# 阿里云侧
systemctl status mcp-healthcheck.timer      # 健康检查定时器
journalctl -u mcp-healthcheck --since -1h   # 最近结果
/root/OmniGraph-Vault/scripts/mcp-healthcheck.py; echo $?  # 手动检查
```

### 已知问题

- Edge Windows 更新后可能丢失 CDP 参数重启 → Task Scheduler 登录后重新触发
- WSL 重启后 MCP/tunnel 自动恢复（systemd user services）
- 阿里云重启后 healthcheck timer 自动恢复（systemd system timer）

---

## 运维常用命令

### 查看服务状态
```bash
ssh vitaclaw-aliyun 'systemctl status omnigraph-daily-ingest.service kb-api --no-pager'
```

### 查看最近的入库日志
```bash
ssh vitaclaw-aliyun "journalctl -u omnigraph-daily-ingest.service --since '1 hour ago' --no-pager | grep -E '(Done —|Ingested|429|503|504|Body too short)' | tail -20"
```

### 查看 KOL 扫描日志
```bash
ssh vitaclaw-aliyun 'for i in 1 2 3 4; do echo "=== batch $i ==="; journalctl -u omnigraph-kol-scan-batch@$i.service --since "2 days ago" --no-pager | grep "Scan complete" | tail -3; done'
```

### 查看数据库状态
```bash
ssh vitaclaw-aliyun 'cd /root/OmniGraph-Vault && python3 -c "
import sqlite3
c=sqlite3.connect(\"file:data/kol_scan.db?mode=ro\",uri=True)
for r in c.execute(\"SELECT status,COUNT(*) FROM ingestions GROUP BY status\"): print(r[0],r[1])
"'
```

### 查看候选队列
```bash
ssh vitaclaw-aliyun 'cd /root/OmniGraph-Vault && python3 /tmp/verify_failed_exclusion.py'
```

### 触发手动入库
```bash
ssh vitaclaw-aliyun 'systemctl start omnigraph-daily-ingest.service'
```

### 检查 embedding 429
```bash
ssh vitaclaw-aliyun "journalctl -u omnigraph-daily-ingest.service --since '24 hours ago' --no-pager | grep -c 'ERROR: Embedding func:.*Vertex AI embedding quota 429'"
```

### 清理 zombie processing 文档
```bash
ssh vitaclaw-aliyun 'cd /root/OmniGraph-Vault && venv-aim1/bin/python scripts/clean_lightrag_zombies.py'
```

---

## 关键文件路径

| 文件 | 说明 |
|------|------|
| `/root/OmniGraph-Vault/batch_ingest_from_spider.py` | 入库编排器 (候选选择 + L1/L2 + per-article) |
| `/root/OmniGraph-Vault/ingest_wechat.py` | 单篇文章入库 (scrape + ainsert) |
| `/root/OmniGraph-Vault/lib/lightrag_embedding.py` | Vertex embedding + 限流 + admission lock |
| `/root/OmniGraph-Vault/kol_config.py` | WeChat TOKEN + COOKIE (gitignored) |
| `/root/OmniGraph-Vault/data/kol_scan.db` | SQLite 主数据库 |
| `/root/.hermes/omonigraph-vault/lightrag_storage/` | LightRAG graph + kv_store |
| `/root/.hermes/.env` | 环境变量 (GCP SA, API keys) |
| `/etc/systemd/system/omnigraph-*.service` | systemd units |
| `/var/lib/qdrant/` | Qdrant 向量数据 |

---

## 凭证刷新流程 (简化版)

当 KOL 扫描报 `ret=200003` 时：

1. 确认 CDP 可达: `curl -s http://127.0.0.1:9223/json/version`
2. 导航到微信后台: `browser_navigate("https://mp.weixin.qq.com/")`
3. 提取 TOKEN (从 URL) + 全量 cookies (Network.getCookies)
4. 用 AST 定位 `kol_config.py` 的 TOKEN/COOKIE 赋值行，替换
5. 单账号验证: `venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1`
6. scp 到阿里云，重复语法检查 + 验证
7. 技能参考: `wechat-cdp-credential-refresh`

---

## 重要约束

- `omonigraph-vault` 是 canonical typo — 不要重命名
- Qdrant collection 后缀 `_gemini_embedding_2_3072d` 由 LightRAG 自动添加 — 不要改名
- `journalctl` 时间格式用 `YYYY-MM-DD HH:MM:SS` (服务器本地)，不要用 RFC3339 T/offset
- 不要在生产 DB 上执行写操作 (UPDATE/DELETE/INSERT) 除非明确授权
- 不要同时降低 embedding 间隔和增加并发数 — 已验证 5.5s + Lock = 0 429
- Token 提取必须从 CDP Runtime.evaluate 获取完整值，注意 terminal redaction 陷阱
- Cookie 提取必须通过 CDP Network.getCookies，DevTools UI 会截断 `slave_sid`
