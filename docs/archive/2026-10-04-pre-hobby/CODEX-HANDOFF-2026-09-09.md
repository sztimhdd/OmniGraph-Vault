# OmniGraph-Vault 项目交接文档 — 给 Codex 接管

> **生成日期：** 2026-09-09（含 9/9 10:13 三机只读审计实测）
> **交接对象：** Codex（AI 编程/运维 Agent）
> **交接范围：** Hermes 本级（WSL）+ 两台阿里云（旧机/新机）共 3 个代码库 + 知识库 + 全部附属脚本/技能/文档/模型配置
> **凭证纪律：** 本文档**不含任何密钥/Token/Cookie/SA JSON 值**，只标位置与变量名，值一律 `[REDACTED]`。

---

## 0. 当前实时状态与告警（9/9 审计，Codex 首日必须看）

**生产存在 4 处需立即关注的告警（按严重度）：**

| 严重度 | 问题 | 证据 |
|---|---|---|
| 🔴 P0 | 旧机实体提取遇 DeepSeek **`402 Insufficient Balance`** | 9/9 07:38 实体抽取 APIStatusError；DeepSeek 共享账户余额耗尽/不足，入库主 LLM 已中断 |
| 🔴 P0 | 新机磁盘 **100% 满**（`/dev/vda3` 99G，avail 0） | 主要消耗 `/var/lib/docker` 48G、vault 6.0G、omonigraph-vault 6.3G、`/root/qdrant_storage` 5.3G |
| 🟡 P1 | 旧机→新机 **KG 同步断裂** | 新机 `kol_scan.db` mtime 停在 09-06、`kv_store_*.bak` 停在 07-28；旧机 `omnigraph-kg-sync.service` **failed** |
| 🟡 P1 | 旧机 ingest **连续 6 次 timeout kill** | 9/9 08:05→18:05 每小时 `Failed with result timeout`，当前轮 20:00 起 running |
| 🟠 P2 | 本地 Qwen3.8-27B **已停止** | `qwen3.8-27b.service` inactive/dead，8001 无监听，unit disabled |
| 🟠 P2 | 旧机 Caddy **脱离 systemd 管理** | `:80` caddy 进程 pid 3134716（6/25 启动，ppid 1），unit inactive |

**核心栈（稳定事实）：** 生产文本=DeepSeek（`deepseek-v4-flash`）、嵌入=本地 BGE-M3 1024d（embed-server :7997）、Vision=DeepSeek 视觉模型（有意代码漂移，8/23）。历史故障（Vision 单 provider 告警、实体提取卡死）已根治。

**代码/数据严格分离：** `~/OmniGraph-Vault` = Git 仓库（代码/技能/测试）；`~/.hermes/omonigraph-vault/` = 纯运行时数据（图谱/图片/缓冲）。**`omonigraph` 是刻意拼写（typo canonical），禁止"修正"。**

---

## 1. 访问与主机拓扑（实测）

| 节点 | 地址 / SSH 别名 | 主机名 | 用户 | 角色 | 状态 |
|---|---|---|---|---|---|
| 本地 WSL | 本机 | `OH-Desktop` | `sztimhdd` | 代码主仓库 / Hermes 网关 / 运维跳板 | ✅ |
| 阿里云旧机 | `47.117.244.253`，alias `aliyun-old`（= `vitaclaw-aliyun`） | `iZj1imk39yc55iZ` | `root` | 采集 + 建图 + 调度 + kb-api + embed | ✅（up 84 天） |
| 阿里云新机 | `47.103.73.20`，alias `aliyun-new` | `ack-node-2-kg` | `root` | 对外 KG/MCP 查询服务 | ⚠️（磁盘 100% 满） |
| 历史/备用 | `101.133.154.49`，alias `aliyun-sync` | — | `root` | 旧地址 | ❌ SSH 超时 |

- **SSH 密钥：** `~/.ssh/id_ed25519`（私钥），`~/.ssh/id_ed25519.pub`（公钥）。SSH config 在 `~/.ssh/config`（6 个 Host 别名，`aliyun-new` L26、`aliyun-old` L32）。
- **⚠️ 别名易错点：** `vitaclaw-aliyun` 指向**旧机 47.117.244.253**；新机必须用 `aliyun-new` 或 `root@47.103.73.20`，不要写反。
- **Hermes PC 远程（DDNS）：** alias `hermes-pc` → `ohca.ddns.net:49221`，user `sztimhdd`（见 `docs/HERMES-PC-SSH-SETUP.md`）。
- **凭证位置（只标位置，不标值）：**
  - 本机：`~/.hermes/.env`（2761B，DeepSeek/Bailian 等）、`~/.hermes/config.yaml`（27636B，Hermes 配置）
  - 旧机：`/root/.hermes/.env`（kb-api 经 `EnvironmentFile` 读取）
  - 新机：`/root/.hermes/.env`（**仅 3 键**：`OMNIGRAPH_LOCAL_EMBED`、`OMNIGRAPH_LOCAL_EMBED_URL`、`DEEPSEEK_API_KEY`）
  - 微信：旧机 `/root/OmniGraph-Vault/kol_config.py`（TOKEN + Cookie，`.gitignore`，含密钥）

---

## 2. 三份代码库（Git 状态与禁忌，9/9 实测）

| 位置 | Git 状态 | 说明 |
|---|---|---|
| `/home/sztimhdd/OmniGraph-Vault`（本机 WSL） | `main` @ **`dca7c772`**，与 `origin/main` 同步 | 代码主仓库。**工作区保留他人未提交改动**：M `scripts/wiki_evolve.py`、M `tests/unit/test_wiki_w5b_bootstrap.py` + 3 个 untracked docs（DSH/HERMES/MASTER handoff）。**禁止 reset/clean/stash/force-push 他人改动。** commit 链 `dca7c772`→`fd0b94ab`→`858022c5`→`728399d5`→`c07590ea` |
| `/root/OmniGraph-Vault`（旧机） | **Git 漂移 fork**：HEAD `a5d3694`（kb-v2.3 系列），**23+ 文件未提交**（batch_*.py、image_pipeline、ingest_wechat、lib/{vision_cascade,llm_*,article_filter,scraper,models}.py、scripts/qdrant_to_nanovdb.py 等） | **禁 `git pull/reset/rebase/checkout/clean/stash`**。部署 = 清单化 file-level SCP + sha256 校验 + 原子 mv（见 §13） |
| `/root/OmniGraph-Vault`（新机） | **不是 Git 仓库**（无 `.git`，全盘 /root /opt /srv /home 均无 `.git`） | 纯部署副本，服务从 `venv-aim1` 运行。无版本历史、无 systemd 定义、无 timer |

- 本机另有 `/home/sztimhdd/OmniGraph-Vault-phase04`（**非 git**，1.7M，2026-04-27 phase-04 时代快照，历史工作副本）。
- GitHub canonical：`github.com/sztimhdd/OmniGraph-Vault.git`，分支 `main`。
- 本机其余 6 个无关仓库（nvm、project-nexus-openclaw-agent-swarm、qwen38-16gb-deploy、firecrawl、super-yolo-engine、vitaclaw-planb-local-m1、vitaclaw-site）与 OmniGraph 无关。

---

## 3. 服务与端口清单（9/9 实测）

### 旧机 `47.117.244.253`（采集+建图+服务入口）

| 服务 | 端口 | 状态 | 说明 |
|---|---|---|---|
| Qdrant（Docker v1.11.5） | `127.0.0.1:6333` | ✅ | 3 个 `bge_m3_1024d` collection |
| kb-api | `127.0.0.1:8766` | ✅ | `/health`→`{"status":"ok"}`，venv-aim1 + `EnvironmentFile=/root/.hermes/.env` |
| embed-server | `0.0.0.0:7997` | ✅ | BGE-M3 1024d，独立 venv `/root/embed-venv`（python3.10） |
| kg_api | `0.0.0.0:8933` | ✅ | 旧版 KG API（废弃保留），`/` 404 正常 |
| caddy | `*:80` | ⚠️ | **进程 pid 3134716 脱离 systemd**（unit inactive/dead） |
| mcp-healthcheck.timer | 每 15min | ✅ | 健康检查 → Telegram |

- 系统单元：active ✅ 的 `embed-server`、`kb-api`、`omnigraph-daily-ingest`、`cron`；**failed**：`omnigraph-evening-ingest`、`omnigraph-kg-sync`、`omnigraph-kol-scan-batch@{1..4}`、`qdrant-snapshot`。触发型 timer（static/disabled）：mcp-healthcheck、dajiala-scan（下次 Sun 09-13 23:01）、rss-*、kol-classify、reconcile、rewrite、translate、disk-cleanup、ingest-daily-summary。

### 新机 `47.103.73.20`（对外 KG/MCP 查询）

| 服务 | 端口 | systemd unit | 说明 |
|---|---|---|---|
| Qdrant（Docker） | `127.0.0.1:6333` + `172.18.12.150:6333` | — | **9 个 collection**（3 现行 + 6 遗留） |
| embed-server | `0.0.0.0:7997` | `embed-server.service` | BGE-M3 |
| KB-API | `127.0.0.1:8766` | `omni-kb-api.service` | FastAPI + LightRAG + FTS5 |
| MCP Server | `0.0.0.0:8767`+`:8768` | `omni-mcp.service` | FastMCP，与 KB 同进程 pid 2440870 |

- **无任何 timer**（纯服务节点）；单元均**无 EnvironmentFile**（其余配置在代码/Environment=）。`/health` → `{"status":"ok","uptime_s":2938858}`。
- MCP 3 工具：`fts_search`（同步 <100ms）、`kg_search`（45s 上限，超时返回 `[kg-running] job_id=`）、`kg_poll(job_id)`。客户端配置：
  ```json
  {"omnigraph": {"url": "http://47.103.73.20:8767/mcp", "transport": "streamable-http",
    "headers": {"Accept": "application/json, text/event-stream"}, "timeout": 300}}
  ```

### 本机 WSL（运维跳板 + 本地模型）

| 服务 | 端口 | 状态 | 说明 |
|---|---|---|---|
| hermes-gateway | `:9119` | ✅ running | Hermes 网关 |
| playwright-mcp | `:8931` | ✅ running/enabled | Playwright MCP（ohca cookie） |
| aliyun-tunnel | autossh `-R 58931:127.0.0.1:8931` | ✅ running/enabled | 反向隧道供旧机健康检查探测 |
| omnigraph-tunnel | `ssh -L 8767:127.0.0.1:8767 aliyun-new` | ✅ running/enabled | 本地→新机 MCP |
| qwen3.8-27b | `:8001` | ❌ **inactive/dead** | 本地 LLM，未接入生产（见 §9） |
| vertex-proxy | — | ⚠️ auto-restart 崩循环 | 已退役的 proxy 残留 |

---

## 4. 数据与存储（9/9 实测）

### SQLite（`kol_scan.db`）

- **生产库 = `~/.hermes/omonigraph-vault/kol_scan.db`（本机 155MB）** / 旧机 `/root/OmniGraph-Vault/data/kol_scan.db`（148MB）——**两者同一份数据的镜像**。
- ⚠️ **本机另有两份陈旧副本**：`OmniGraph-Vault/data/kol_scan.db`（150MB，旧 ~350 篇）、仓库根 `kol_scan.db` 与 `~/.hermes/hermes-agent/data/kol_scan.db`（0B 空壳）。**写/读一律以 vault 生产库为准，勿误操作 repo data/ 副本。**
- 关键表：`accounts`、`articles`、`rss_articles`、`classifications`、`rss_classifications`、`ingestions`、`extracted_entities`、`entity_canonical`、`rss_feeds`、`articles_fts*`
- **当前行数：** articles **5056** / rss_articles **3596** / ingestions **8577** / classifications **52268** / accounts 58
- **layer1_verdict：** reject 3531 / candidate 1481 / NULL 44
- **layer1_prompt_version：** `layer1_v2_20260810` 3599 / `layer1_v1_20260512` 1413 / NULL 44
- 关键列：`layer1_verdict`（candidate/reject/NULL）、`layer1_prompt_version`、`layer1_reason`、`layer1_at`、`layer2_verdict`、`layer2_at`

### LightRAG 存储（`~/.hermes/omonigraph-vault/lightrag_storage/`）

- 本机 3.4G / 旧机 6.9G / 新机 4.3G（三份独立）
- `graph_chunk_entity_relation.graphml`（主图谱，本机 69M/旧机 125M/新机 70M）+ `kv_store_*.json` + `vdb_*.json`
- 图片：`images/{hash}/`（`metadata.json` + `final_content.md`，本机 1532 项）
- 实体缓冲 `entity_buffer/`、规范化映射 `canonical_map.json`、检查点 `checkpoints/{hash}/`（592 项）
- ⚠️ 新机遗留 `vdb_entities.json.tmp`(7/28 47M) 与 `vdb_relationships.json.tmp`(7/23 50M)——大文件 `.tmp` 即写入未完成，可清理

### Qdrant collections（命名后缀即嵌入维度）

- 旧机：**3 个 `bge_m3_1024d`**（BGE-M3 迁移已完成，Gemini 3072d 已清）——chunks **9194** / entities **129275** / relationships **205762**
- 新机：**9 个** = 现行 `*_bge_m3_1024d`（chunks **12366** / entities **168831** / relationships **250885**）+ 遗留 `*_bge-m3_1024d`（连字符）+ `*_gemini_embedding_2_3072d`（**未清理，占磁盘**）
- **禁止重命名 collection 后缀**（LightRAG 自动加后缀，改名 hybrid retrieve 静默 0 sources）

### 新旧机同步（重要，当前**已断裂**）

- 方向：**旧机 → 新机**，每天 **02:30 CST**，脚本 `/root/OmniGraph-Vault/deploy/sync_kq_to_new.py`
- 机制：Qdrant 点 ID 差集（旧机有、新机无 → 取向量+payload upsert）；SQLite `.backup` → scp → `mv` 原子替换
- **新机是超集**（只增不删），不要假设两机点数相等
- ⚠️ **当前状态：旧机 `omnigraph-kg-sync.service` failed**，新机 `kol_scan.db` 停在 09-06、`kv_store_*.bak` 停在 07-28 → **同步已断 3+ 天**，Codex 接手后需排查恢复

### 生产备份（旧机 `/root/OmniGraph-Vault/`）

`.t7-backup-20260903T183039Z/`（T2/T4/T5 旧版）、`.t6-deploy-backup-20260903T184234Z/`（T5 版 batch_ingest）、`.healthcheck-backup-20260904-025758/`（mcp-healthcheck 旧版）、`.w5b-backup-20260815003447/`、`.w5b-backup-20260815-011736/`。异地备份清单见 `INVENTORY.md`（`backup_prod@139.159.179.249`）。

---

## 5. Pipeline 架构

```
dajiala API 周扫(Sun 23:00, --top 20 --pages 2)  +  RSS(rss_fetch 17:00)
        │  写 kol_scan.db articles / rss_articles
        ▼
batch_classify_kol.py (00:00)  ── Layer1 过滤(L1, v2 prompt 7 topics) ── Layer2 深度打分
        │  candidate/reject 落库
        ▼
batch_ingest_from_spider.py --from-db --max-articles 10 --batch-timeout 6300 (每 2h)
        │  Layer1 → scrape(Apify/CDP/MCP) → Layer2 → enrich → ainsert → reconcile
        ▼
LightRAG 建图 → Qdrant(bge_m3_1024d) + graphml  →  embed-server:7997(BGE-M3)
        ▼
旧机 kb-api:8766 / kg_api:8933   ──02:30 sync──▶  新机 omni-mcp:8767 / omni-kb-api:8766
```

**关键脚本：**

| 脚本 | 用途 |
|---|---|
| `ingest_wechat.py` | 单篇微信/网页入库（Apify→CDP→MCP 三路爬虫 + Vision + 实体提取 + ainsert） |
| `batch_scan_kol.py` | KOL 扫描 → SQLite |
| `batch_classify_kol.py` | Layer1/Layer2 分类（DeepSeek） |
| `batch_ingest_from_spider.py` | 批量入库主循环（`ingest_from_db()` 核心编排器，600+ LOC） |
| `batch_classify_rss_layer2.py` | RSS Layer2 深度分类 |
| `kg_synthesize.py` | 综合报告（LightRAG hybrid + DeepSeek Markdown） |
| `query_lightrag.py` | 原始 KG 调试查询 |
| `multimodal_ingest.py` | PDF + 图片入库 |
| `scripts/dajiala_kol_scan.py` | dajiala KOL 周扫 API（`history_by_ghid`，**严禁一次拉全历史**；**仅旧机有**，新机无此脚本） |
| `scripts/mcp-healthcheck.py` | 健康检查（旧机，15min→Telegram；9/4 已部署 `dca7c772` 版，当前 md5 `5c7b65be…`） |
| `scripts/wechat_probe.py` | 微信会话/能力探针（诊断 200013/200003） |
| `scripts/refresh_wechat_cookie.py` | 微信 cookie 自愈（Hermes Edge CDP → 写回 kol_config.py） |
| `scripts/sync_kq_to_new.py` | 旧机→新机 KG 同步 |
| `scripts/local_e2e.sh` | 本地冒烟/E2E（**必须走它**，corp 网络感知） |
| `scripts/readonly_audit.py` | 只读数据面审计 |
| `scripts/checkpoint_status.py` / `checkpoint_reset.py` | 检查点状态/重置 |
| `scripts/patch_lightrag_entity_name.sh` | LightRAG `entity_name` KeyError 热补丁 |

**检查点机制：** 每文章 `checkpoints/{hash}/` 分阶段标记，原子写（`.tmp`+`os.rename`），重启续传。批量中断前先停服务，勿删 in-flight metadata.json。

---

## 6. 模型路由（当前生产，9/9 实测）

| 用途 | 模型 | Provider | 备注 |
|---|---|---|---|
| 入库主 LLM / 实体提取 | `deepseek-v4-flash` | DeepSeek | `lib/llm_deepseek.py`，`OMNIGRAPH_LLM_PROVIDER=deepseek`；⚠️ 9/9 起 `402 Insufficient Balance` |
| Layer1/Layer2 分类 | `deepseek-v4-flash` | DeepSeek | `batch_classify_kol.py` |
| 翻译 / 综合报告 | `deepseek-v4-flash` | DeepSeek | `kg_synthesize.py` |
| **Vision（生产）** | DeepSeek 视觉模型 | DeepSeek | **⚠️ 代码漂移**：生产 `lib/vision_cascade.py` 工作树 sha `db74e375`（8/23 mtime）≠ git HEAD blob `0a9ac95c`，**未 commit**；本地仓库是 bailian 基线。**严禁覆盖/回滚/格式化生产该文件** |
| Vision（历史） | `qwen3-vl-flash` | Bailian（百炼） | 8/11 全切纯 bailian，8/23 被 DeepSeek 视觉取代 |
| Embedding | `BGE-M3` 1024d | 本地 embed-server `:7997` | `OMNIGRAPH_LOCAL_EMBED=1`；⚠️ `.env` 里 `EMBEDDING_MODEL=gemini-embedding-2` 是**残留旧值**，实际走本地 BGE-M3 |

**⚠️ 文档 drift：** `README.md`、`Deploy.md`、部分 CLAUDE 段落仍写 SiliconFlow/Gemini Vision、Vertex embedding、Cognee——均已过时。以 `lib/models.py`、`lib/vision_cascade.py`（生产版）、`lib/lightrag_embedding.py` 和现场 `.env` 为准。

**旧机 `.env` 关键变量（9/9 实测，只标名）：**
- `OMNIGRAPH_LLM_PROVIDER=deepseek`、`DEEPSEEK_API_KEY`
- `OMNIGRAPH_VECTOR_STORAGE=qdrant`
- `OMNIGRAPH_LOCAL_EMBED=1` + `OMNIGRAPH_LOCAL_EMBED_URL=http://localhost:7997/embeddings`
- `VISION_INTER_IMAGE_SLEEP=1.0`（T3 尖峰控制）
- `OMNIGRAPH_VISION_SKIP_PROVIDERS=openrouter`、`OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1`
- `EMBEDDING_MODEL=gemini-embedding-2`（残留）、`BAILIAN_MODEL=qwen3.7-flash`、`BAILIAN_EMBED_MODEL=qwen3.7-text-embedding`、`AUXILIARY_VISION_MODEL=gemini-2.5-flash`（历史残留）
- 其余密钥型仅列名 `[REDACTED]`：GEMINI_API_KEY/BACKUP、APIFY_TOKEN/BACKUP、TELEGRAM_BOT_TOKEN、BRAVE/TAVILY/FIRECRAWL/OPENROUTER/SILICONFLOW/HINDSIGHT、RAILWAY、OMNIGRAPH_GEMINI_KEY、OMNIGRAPH_EMBEDDING_KEYS/EMBED_TOKEN、BAILIAN_API_KEY、WEIXIN_TOKEN、TELEGRAM_CHAT_ID
- **⚠️ kb-api 读 .env 走 EnvironmentFile，但 ingest 单元不读 .env**——新增变量必须写 drop-in override（如 `omni-kb-api.service.d/embed.conf`），不能只写 .env

---

## 7. 知识库 `kb/` + Databricks 部署

- `kb/` = FastAPI + Jinja2 SSG 知识库站：FTS5 快速搜索 + `?mode=kg` 深度问答（复用 `kg_synthesize`）
- 双入口：`/api/search?q=...&mode=fts`（同步）| `mode=kg`（异步 job）| `/api/synthesize`（POST）
- **契约（不可单方面改）：** `kg_synthesize.synthesize_response(query_text, mode)` 签名、`omnigraph_search.query.search(query_text, mode)` 签名、`kol_scan.db` 表结构、`images/{hash}/final_content.md` 路径。改契约 commit 必须带 `BREAKING: kb-contract-X`。
- **Databricks Apps 部署：** `databricks-deploy/`，Makefile `make deploy|logs|smoke|stop`（PowerShell 跑，Git Bash 会破坏 `/Workspace/...` 路径）
- **规则：** 动 `kb/static/` 或 `kb/templates/` 必须走完整 Makefile 管线（Pass 0a SSG bake → 0b → 0c → 0d → Pass 1→2→3）。sync-only（Pass 2+3）只对 `kb/services/`、`kb/api_routers/`、`kb/api.py` 安全。Databricks 服务 `databricks-deploy/_ssg/static/` 只由 Pass 0a 重新生成。
- **KB 变更上线前强制本地 UAT：** `.scratch/local_serve.py` → `:8766`，curl 每个端点族 + 浏览器 UAT（见 `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3）

---

## 8. 附属脚本与技能清单

### 仓库内技能（`skills/`，11 个）
`omnigraph_ingest`、`omnigraph_query`、`omnigraph_architect`、`omnigraph_scan_kol`、`enrich_article`、`zhihu-haowen-enrich`、`omnigraph_cloud_synthesize`、`omnigraph_research`、`omnigraph_search`、`hermes_claude_code_bridge`、`wechat-cdp-credential-refresh`

### Hermes 运维技能（`~/.hermes/skills/`，25 个，交接优先加载）
- **`devops/omnigraph-aliyun-ops`**（最权威运维手册，含 strict-file-level-deploy / ijson-streaming / diagnostic-queries 三 references）
- `knowledge-management/`（17 个）：omnigraph-mcp-server、omnigraph-mcp-healthcheck、omnigraph-pipeline-verify、omnigraph-handoff-verification、omnigraph-kg-sync、omnigraph-model-swap、omnigraph-milestone-closeout、omnigraph-wiki-compiler、omnigraph-topic-classification、omnigraph-knowledge-enrichment、omnigraph-dajiala-kol-scan、omnigraph-cdp-browser-ops、omnigraph-kol-batch、omnigraph-production-repair、omnigraph-production-patterns、omnigraph-integration-strategy、omnigraph-regression-benchmark
- `omnigraph/`（4 个）：omnigraph-export、aliyun-deploy、wiki、rss
- `omnigraph_architect`（含 `omnigraph-w5-0-gate-f-closed` 门禁标记）

---

## 9. 本地模型（Qwen3.8-27B，**当前已停止**，尚未接入生产）

- 模型：`Qwen3.8-27B-UD-IQ3_XXS`（GGUF 10.9GB），llama.cpp `llama-server`
- 位置：`~/.local/share/qwen3.8-27b-in-16gb/`（bin/llama-server + .gguf + run.sh + config.env）
- 端点：`http://127.0.0.1:8001`（OpenAI-compatible）
- systemd user unit：`~/.config/systemd/user/qwen3.8-27b.service`（ExecStart=run.sh，Restart=on-failure，含 `.bak-20260829-170902`）
- **当前状态：inactive/dead，8001 无监听，unit disabled**（9/9 实测）→ 重启 WSL 后不自启；启动 = `systemctl --user restart qwen3.8-27b`（只 start/restart，**不 enable**，enable 需用户另行决策）
- 配置：`PORT=8001`、`HOST=127.0.0.1`、`CTX=65536`、`PARALLEL=1`、`-ngl 99`、KV `q8_0/q4_0`
- 实测吞吐 ≈40.5 tok/s；GPU RTX 4070 16GB，占用 ~14.9/16.4 GiB（余量 ~1.5GB，与 Windows 桌面抢 VRAM 会 OOM）
- **接入状态：0 调用 / 0 token 已移交生产**。分阶段接入路线：T0 端点稳定 → T1 分类 canary（标签一致率≥95%、解析错误 0）→ T2 实体提取格式验证 → T3 Vision 永不纳入；本地失败最多一次 DeepSeek fallback。T1 canary 只跑了 4 条（4/4 一致、1 超时），未汇总到 20 条，临时脚本已清理。

---

## 10. 测试与验收

```bash
venv/Scripts/python.exe -m pytest tests/unit -v                    # Windows 本地（默认单测层）
venv/bin/python -m pytest tests/unit -v                            # Hermes/Aliyun
python skill_runner.py skills/ --test-all                          # 技能验证（exit 0 = 全过）
```

- Markers（`pyproject.toml`）：`unit`（快，mocked）· `integration`/`remote`（活依赖，仅远程 WSL）· `slow`/`eval`（opt-in）。`asyncio_mode=auto`。
- **行为锚定 harness（强制）：** 对 `ingest_from_db()` 任何契约形状改动（candidate_rows tuple 列、SKIP_REASON_VERSION、layer2 verdict 成员、持久化列、mid-loop early-exit），必须新增 `tests/unit/test_ingest_from_db_orchestration.py` 测试 + 同步更新 `tests/unit/_ingest_fixtures.py:in_memory_db()` + 该文件 pytest 通过。此规则只适用于 `{ingest_from_db}`。
- **已知 pre-existing 失败（不阻塞）：** `test_classify_ingest_bridge.py`（`_SCHEMA_DDL` 缺 `layer1_verdict` 列）、`test_classify_full_body_topic_hint.py`（活网）、`test_lightrag_llm.py::test_missing_api_key_raises_runtime_error`、`test_batch_ingest_topic_filter` 的 `os._exit(0)` 截断输出（用 `-k "not sys_exit"`）、5 个 stale Gemini-era 测试（ISSUES #90）。
- **本地冒烟/E2E 一律走 `scripts/local_e2e.sh <mode>`**（`kol|wechat <url>|layer1 N|layer2 N|cleanup`），corp 网络感知，raw 脚本会绕过。

---

## 11. 成本红线（关键）

| 项 | 规则 |
|---|---|
| **DeepSeek** | 生产与 WSL/Hermes **共享账户**，无 token/cost ledger；**9/9 已出现 `402 Insufficient Balance`** → Codex 接手先查余额/充值，否则入库主 LLM 全线停 |
| dajiala API | 余额 < 5 元停扫描；任何 `20001`（金额不足）即停；**严禁一次拉全历史**（上次 452 篇全拉烧 6 元、67% 被拒）。只跑周扫 `--top 20 --pages 2`（≈5.6 元/周） |
| 百炼 bailian | ¥0.0013/图（历史 vision），低 |
| 大 JSON | 禁止 `json.load()` 读 1.5-1.8G `vdb_*.json`（14G 内存机器），必须 `ijson` 流式 |

---

## 12. 危险操作红线（绝对禁止）

- ❌ 旧机 `git pull/reset/rebase/checkout/clean/stash`（漂移 fork）
- ❌ 一次拉全 dajiala 历史
- ❌ `json.load()` 读大 `vdb_*.json`
- ❌ 双 LightRAG 实例同跑（Qdrant + ingest 内存 OOM）
- ❌ 输出/提交任何密钥、Token、Cookie、SA JSON、私钥
- ❌ 删除 `lightrag_storage/`、`images/`、`/var/lib/qdrant`、`/root/qdrant_storage`
- ❌ 改 `omonigraph-vault` 拼写、改 Qdrant collection 后缀
- ❌ systemd 服务依赖 `.env` 自动生效——ingest 单元不读 .env，新变量必须 drop-in override
- ❌ 生产写操作（DB UPDATE/INSERT/DELETE、systemctl restart/stop、Qdrant 写）未经用户明确授权
- ⚠️ `ssh X && scp Y` 短路陷阱：scp 单独跑，落地 `ls -la`/`sha256sum` 验证
- ⚠️ SSH 内联 Python/heredoc 引号剥离：复杂脚本写文件再 scp 执行
- ⚠️ 部署后必须 grep 验证实体符号，防 scp 路径错误静默失败
- ⚠️ `pip install --force-reinstall lightrag` 后必须重打 atomic-write patch（否则下次 SIGTERM 截断 graphml）

---

## 13. 生产部署协议（strict file-level）

旧机/新机都是**非可信 Git 工作树**，部署 = 清单化 file-level SCP：

1. 记录目标文件 pre-state（sha256 / mtime / hostname / service 状态）
2. 备份到 `/root/OmniGraph-Vault/.<feature>-backup-<ts>/`（含 MANIFEST：sha/mtime/mode/hostname/source-commit）
3. `scp` 本地文件 → 远端 `/tmp/<file>.<tmptag>` → 远端 sha256 校验 == 本地
4. 原子 `mv` 到目标路径 → 清 tmp + stale `__pycache__`/`.pyc`
5. 回读 sha256 比对 + `py_compile` + grep 实体符号验证
6. 契约复核：systemd `Restart=no`、`RuntimeMaxSec=14400`、`TimeoutStopSec=300`、`--from-db --max-articles 10 --batch-timeout 6300`、timer `00/2h UTC` `Persistent=true`、legacy timers disabled
7. 服务运行中不盲杀（等待或报告 blocker）；不停 timer、不重启、不 daemon-reload（除非必要）；不部署测试文件/vision/image_pipeline/.env

---

## 14. 已知问题（`.planning/ISSUES.md` 是唯一事实源，171K/848K）

**9/9 审计新增（尚未入 ISSUES，Codex 接手应转录）：**
- 🔴 DeepSeek `402 Insufficient Balance`（9/9 07:38 实体抽取）——生产入库中断
- 🔴 新机磁盘 100% 满——需清理 docker 48G / 遗留 gemini+bge-m3 旧 collection / `.tmp` 残留
- 🟡 旧机→新机 KG 同步断裂（kg-sync.service failed，新机 kol_scan.db 停在 09-06）
- 🟡 旧机 ingest 连续 6 次 timeout kill（`RuntimeMaxSec` 制，需查是否长文 chunk 串行超 4h）
- 🟠 旧机 caddy 进程脱离 systemd 管理

**历史关键（ISSUES.md 已有）：**
- 🟡 P1：PROCESSED 验证死等（BACKOFF 35s 治标，治本=锚定 graph 写入信号）；RSS 日入库 1-3 篇（设计行为）
- 🟠 P2：旧机 git 漂移 fork；dwarkesh.com RSS（已 `active=0`）；embed 路由 HTTP 明文（#88，等用户开 :443）
- 🟢 P3：5 个 stale Gemini 测试（#90）；topic-v2 i18n key 缺失（#92）；翻译 id=1258 卡住

**完整清单以 `.planning/ISSUES.md` 为准**（agents 只读；orchestrator 在 close-out 时新增/归档行，30 天后归档 `.planning/archive/`）。

---

## 15. 进行中状态与待办（2026-09-09）

1. **尖峰控制 T 系列**（T1-T9 已部署，剩 T10 观察）：
   - T2 `lib/llm_deepseek.py` `max_retries=1`（commit `1daa3546`）；T3 `.env` `VISION_INTER_IMAGE_SLEEP=1.0`；T4 `batch_classify_kol.py` batch 间隔 2s（`728399d5`）；T5 Layer2 整批 NULL 退避（`858022c5`）；T8 Layer1 调用前分桶（`fd0b94ab`）；T11 MCP 告警 `mcp=down`→`ohca-mcp=down`（`dca7c772`）
   - **T10 待办：** 48h 观察指标对比（受 402 余额中断影响，观察窗口需顺延）
2. **本地模型接入**（进行中）：端点已启动过、现已停；T1 分类 canary 只完成 4/20 条（4/4 一致、1 超时）；尚未切生产流量
3. **KG 同步恢复**：旧机 kg-sync.service failed，需排查恢复（否则新机 KB/MCP 查询停留在 09-06 数据）

---

## 16. 关键坑（Pitfalls）

- **journalctl 时间格式**：用 `YYYY-MM-DD HH:MM:SS`（服务器本地），**不用 RFC3339**；`--since '24 hours ago'` 也行
- **Caddy 常 dead 而 kb-api 内部健康**——交接文档常假设 Caddy 还活着，要独立验证 :80/:443 路径（旧机当前 caddy 进程脱离 systemd，unit inactive）
- **`depth_score` 在 `classifications` 表，不在 `articles`**
- **429 grep 假阳性**：URL hash 含 "429"，用全串 `'Vertex AI embedding quota 429'`
- **`mcp-session-id` 只在 initialize 响应 header**，body 无；后续调用要带
- **`GOOGLE_GENAI_USE_VERTEXAI=true`** 会污染所有 `genai.Client`，用前 `os.environ.pop`
- **router provider normalize**：`batch_classify_kol.py` 顶部要把 `router` → `deepseek`（否则 `ValueError: Unknown OMNIGRAPH_LLM_PROVIDER=router`）
- **vision 单 provider 告警语义**：`vision fallback active (single provider)` 是信息性的，非健康信号；真实退化看 `result=http_503`/`timeout` 或 `circuit_open=true`
- **本地 importlib 加载 `article_filter.py`**：必须 `sys.modules[spec.name] = module` 再 `exec_module`（否则 dataclass `AttributeError`）
- **FTS5 长查询 AND 语义**可能 no-results（短词正常），非数据问题
- **embedding 429 全串**见上；**kb-api venv 指向 `venv-aim1`**（旧 `venv/` 已删）
- **双 kol_scan.db**：本机 vault 生产库（155MB，最新）vs repo `data/` 副本（150MB，旧 350 篇）vs 仓库根空壳——读写以 vault 为准
- **新机非 git 且无 `dajiala_kol_scan.py`、无 backups、无 timer**——别在旧机上找不到就以为没了，也别误以为新机有采集能力

---

## 17. Codex 接管首日建议动作（按严重度排序）

1. **查 DeepSeek 余额**（402 余额不足）：确认 `DEEPSEEK_API_KEY` 账户余额，决定充值或暂停 ingest（入库主 LLM 已中断）
2. **清理新机磁盘**（100% 满）：`docker system prune`、清理遗留 gemini/bge-m3 旧 collection、`vdb_*.tmp` 残留（先备份、只读确认再删）
3. **恢复 KG 同步**：排查旧机 `omnigraph-kg-sync.service` failed 原因，恢复 02:30 同步（新机数据停在 09-06）
4. **处理旧机 ingest timeout 循环**：6 连 kill，查是否长文 chunk 串行超 `RuntimeMaxSec`
5. 只读复核现场（不要改生产）：
   ```bash
   cd /home/sztimhdd/OmniGraph-Vault && git status -sb && git log --oneline -5
   ssh aliyun-old 'hostname; df -h / | tail -1; free -h | head -2; systemctl --failed; systemctl list-timers --all | grep -i omnigraph'
   ssh aliyun-new 'hostname; df -h / | tail -1; systemctl is-active omni-kb-api omni-mcp embed-server; ss -tlnp | grep -E "8766|8767|8768|6333|7997"'
   ```
6. 加载 `~/.hermes/skills/devops/omnigraph-aliyun-ops/SKILL.md` + references（strict-file-level-deploy / ijson-streaming / diagnostic-queries）
7. 读 `docs/HERMES-OMNIGRAPH-OPERATIONS-HANDOFF-20260822.md`（**带 `docs/DSH-MASTER-HANDOFF-20260822.md` §8 的 6 处纠错阅读**）+ `.planning/ISSUES.md` 全文
8. 未得到用户明确授权前，不做任何生产写操作

---

## 18. 关键文档索引（优先级）

1. `~/.hermes/skills/devops/omnigraph-aliyun-ops/SKILL.md` — 最权威运维手册
2. `docs/HERMES-OMNIGRAPH-OPERATIONS-HANDOFF-20260822.md` — 8/22 运营 handoff（6 处错误见 DSH §8）
3. `docs/DSH-MASTER-HANDOFF-20260822.md` — 主控 handoff（含实测事实 + 红线 + 纠错）
4. `docs/OPERATIONS.md` — 运维参考（env var、命令、checkpoint、vision、batch）
5. `OMNIGRAPH_DEPLOY.md` — 新机部署专档
6. `docs/HERMES-OMNIGRAPH-ALIYUN-HANDOFF-2026-07-20.md` — 阿里云运维交接
7. `docs/HERMES-PC-SSH-SETUP.md` — SSH 连接
8. `docs/OPERATOR_RUNBOOK.md` — 批量入库/恢复
9. `INVENTORY.md` — 备份/恢复/禁止操作
10. `.planning/ISSUES.md` — 已知问题唯一事实源
11. `BGE_M3_MIGRATION.md` — BGE-M3 迁移方案
12. `CLAUDE.md` + `kb/README.md` + `kb/docs/10-DESIGN-DISCIPLINE.md` — 工程原则/KB 契约

---

*文档完。全部实时数据来自 2026-09-09 10:13 三机只读审计（本机 WSL + 旧机 47.117.244.253 + 新机 47.103.73.20），零写操作、零密钥回显。*
