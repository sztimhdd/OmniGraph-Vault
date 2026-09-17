# VitaX 三环境部署档案

审计日期：2026-09-09；证据窗口约 13:22–13:40 UTC（Halifax 10:22–10:40；中国 21:22–21:40）。每份证据包含独立时间戳，不能将不同时间的计数当作同一事务快照。

**[KNOWN / HIGH] 本文是 SSH 实测、源码核对和有限接口验证形成的部署档案。** 项目名称使用 VitaX；服务器上的 `OmniGraph-Vault`、`omonigraph-vault`、服务名与 collection 名保持现有契约。用户提供的交接文档作为线索，其“清理、修复、重启”等建议未被视为本轮授权。

**[KNOWN / HIGH] 已完成认知审计，不代表生产全面健康或正式 UAT 通过。** 生产源码、服务配置、数据库与向量集合未由本轮修改；对已有 Hermes 会话发起了一次纯文字询问。合成 embedding 输入和 FTS 查询仅用于有界验证，未触发采集、同步或 KG 付费合成。

## 1. 主机身份与连接

| 角色 | 地址 | Mac 上已验证 SSH 别名 | 远端主机名 / 用户 | 代码与数据 |
|---|---|---|---|---|
| [KNOWN] Hermes PC / WSL | `192.168.4.100` | `OHPC` | `OH-Desktop` / `sztimhdd` | `/home/sztimhdd/OmniGraph-Vault`；`/home/sztimhdd/.hermes/omonigraph-vault` |
| [KNOWN] 采集与建图旧机 | `47.117.244.253` | `ack-node-2`、`aliyun-vitaclaw` | `iZj1imk39yc55iZ` / `root` | `/root/OmniGraph-Vault`；`/root/.hermes/omonigraph-vault` |
| [KNOWN] MCP 查询新机 | `47.103.73.20` | `ack-node-1` | `ack-node-2-kg` / `root` | `/root/OmniGraph-Vault`；`/root/.hermes/omonigraph-vault` |

[KNOWN] Mac 未配置可用的 `hermes-pc`、`aliyun-old`、`aliyun-new` 别名；这些名称来自远端 WSL 的配置。尤其不能根据 `ack-node-1/2` 名字猜测主机角色。三台主机均完成 SSH 登录和 hostname 核对。证据：[Hermes](2026-09-09/hermes-inventory.json)、[旧机](2026-09-09/pipeline-inventory.json)、[新机](2026-09-09/mcp-inventory.json)。

## 2. 实际拓扑与数据责任

```text
Hermes PC Windows Edge :9223
  ├─ WSL Playwright MCP :8931
  └─ WSL autossh → 旧机回环 :58931(MCP) / :58932(SSH) / :58933(CDP)

旧机：扫描 → SQLite → 分类 → 抓取/视觉 → LightRAG → Qdrant + graphml/KV/images
  ├─ 本机 embed-server :7997（BGE-M3，实测 1024d）
  ├─ kb-api :8766；另有 kg_api :8933
  ├─ 每日 18:30 UTC：Qdrant 缺失点 + SQLite → 新机
  └─ Hermes 05:00 UTC 拉取：SQLite + wiki + SSG articles + images → WSL vault

新机：MCP :8767 → HTTP → KB-API :8766 → FTS / LightRAG
  ├─ MCP 健康线程 :8768（与 :8767 同 PID）
  ├─ 本机 embed-server :7997 + Qdrant :6333
  └─ graphml / KV 文件独立保留于新机；未找到持续同步它们的已启用任务

客户端：Mac 公网 → 新机 :8767；Hermes 本地 :8767 → SSH 隧道 → 新机 :8767
```

[KNOWN] 图中连接来自活动服务命令、同步脚本和接口探测，不代表每条业务链路都完成了端到端内容验收。旧机仍依赖 Hermes 的浏览器能力，不能把 Hermes 描述为完全脱离生产。证据：[调度](2026-09-09/pipeline-schedules.json)、[Hermes 同步与隧道](2026-09-09/hermes-schedules.json)、[实际脚本](2026-09-09/pipeline-detail.json)。

## 3. 代码版本、WIP 与部署差异

[KNOWN] Mac VitaX 与 Hermes main 基线均为 `dca7c772a8c95125d275ec50b2944ff00713667a`。Hermes main 有两个已跟踪文件修改：`scripts/wiki_evolve.py`、`tests/unit/test_wiki_w5b_bootstrap.py`；另有四份未跟踪交接／主控文档。

[KNOWN] 旧机 Git HEAD 为 `a5d3694faa3d3a59b6a250af2b05813510be9188`，快照中有 26 个已跟踪文件状态变化。新机项目目录没有 `.git`。后者为部署副本；本轮未全盘搜寻无关仓库，不能推断整台主机完全没有 Git 仓库。

[COMPUTED] 以下比较覆盖约定源码目录中的代码、部署与依赖文本；排除运行数据、虚拟环境、缓存、密钥配置及超大文件。是“与 Mac 当前源码的字节比较”，不是旧机相对自己 HEAD 的 Git diff：

| 环境 | 比较文件数 | 与 Mac 相同 | 不同 | 仅远端存在 |
|---|---:|---:|---:|---:|
| Hermes | 573 | 571 | 2 | 0 |
| 旧机 | 520 | 476 | 35 | 9 |
| 新机 | 189 | 165 | 20 | 4 |

[KNOWN] 旧机 `lib/vision_cascade.py` 当前使用 `DEFAULT_PROVIDERS=("deepseek",)`，默认视觉模型 `deepseek-v4-flash-vision-exp`；与 main 的 Bailian 路径不同。日志存在 `provider=deepseek` 运行记录。Hermes Agent 将它解释为 2026-08-23 的有意选择；其他漂移并无完整获批回收清单。不能用 Mac main 整目录覆盖旧机或新机。

[KNOWN] 旧机不同文件还包括 embedding、models、LLM wrappers、部分 KB 实现与部署文件；新机包含批处理、LLM、embedding、KB 与诊断脚本差异。逐文件 SHA-256 和差异名单见 [代码比较](2026-09-09/code-comparison.json) 与各 `*-source.json`。这提供后续逐文件三方比对的分母，尚未完成逐差异功能验收。

### Hermes 工作树

[KNOWN] 八个 W5B 工作树均存在且 `git status --short` 为空；这只说明未发现未提交文件，不代表已经合并、可删除或无人使用。另有两个 `/tmp` 工作树注册项已标记 prunable，未清理。原 main 的两个 WIP 文件保留。

| 工作树末级目录 | HEAD | 状态 |
|---|---|---|
| `omnigraph-w5b-t2` | `f0515516` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t3` | `e2296e0a` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t4` | `21bb9f4a` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t4-retry` | `54a81ce9` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t5` | `4aa662a5` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t6` | `0161a24c` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t7` | `e947d4c5` | [KNOWN] status 为空；归属／合并结论待确认 |
| `omnigraph-w5b-t8` | `8b702de3` | [KNOWN] status 为空；归属／合并结论待确认 |

证据：[工作树与备份目录](2026-09-09/hermes-worktrees-backups.json)、[指定 Agent 回复](2026-09-09/hermes-agent-reply.md)。

## 4. 服务、资源和调度

| 环境 | 服务 / 入口 | 已验证状态与实现 |
|---|---|---|
| [KNOWN] Hermes | `hermes-gateway`，`:9119` | user service active；本轮 CLI 成功续接指定会话并退出 0 |
| [KNOWN] Hermes | `playwright-mcp`、`aliyun-tunnel`、`omnigraph-tunnel` | user services active；实际转发见拓扑 |
| [KNOWN] Hermes | `qwen3.8-27b`，`:8001` | inactive/dead，disabled；未启动或接入生产 |
| [KNOWN] Hermes | `vertex-proxy` | activating/auto-restart；保留的异常残留，未处理 |
| [KNOWN] 旧机 | `kb-api`，`127.0.0.1:8766` | PID 3733493，venv-aim1；health 200；MemoryMax 12 GiB |
| [KNOWN] 旧机 | `embed-server`，`0.0.0.0:7997` | PID 2002587，独立 `/root/embed-venv`；合成输入实测 1024d |
| [KNOWN] 旧机 | `kg_api.py`，`0.0.0.0:8933` | PID 2018841，session scope；另一个常驻查询进程 |
| [KNOWN] 旧机 | Caddy，`:80` / 管理口回环 `:2019` | PID 3134716，session scope；caddy systemd unit inactive；日志路径含 vitaclaw-ip-uat，不能仅凭进程名认定只服务 VitaX |
| [KNOWN] 旧机 | Qdrant，回环 `:6333` | Docker `qdrant/qdrant:v1.11.5`；`/var/lib/qdrant` bind mount；三组现行 collection |
| [KNOWN] 新机 | `omni-kb-api`，回环 `:8766` | PID 488505，独立进程；venv-aim1；MemoryMax 6 GiB |
| [KNOWN] 新机 | `omni-mcp`，`0.0.0.0:8767/8768` | PID 2440870；HTTP 代理；MemoryMax 1 GiB |
| [KNOWN] 新机 | `embed-server`，`0.0.0.0:7997` | PID 338297；venv-aim1；实测 1024d |
| [KNOWN] 新机 | Qdrant | Docker v1.11.5；`/root/qdrant_storage` bind mount；回环 6333/6334、VPC 172.18.12.150:6333 |

[KNOWN] 旧机还运行 kubelet/Cilium/containerd 等共享基础设施。VitaX 运维不能把整机 Docker/containerd 数据视为本项目可删除缓存。

### 活动调度

[KNOWN] 表中 Calendar 是 systemd 当前报告值。描述文本可能仍写旧的 09:00 ADT 等名称，实际以 Calendar / 启动记录为准。

| 主机 | Timer | Calendar / 最近触发 |
|---|---|---|
| Hermes | `omnigraph-daily-pull.timer` | `{ OnCalendar=*-*-* 05:00:00 UTC ; next_elapse=Thu 2026-09-10 02:00:00 ADT }` |
| 旧机 | `mcp-healthcheck.timer` | `Wed 2026-09-09 06:30:01 CST` |
| 旧机 | `omnigraph-daily-digest.timer` | `{ OnCalendar=*-*-* 12:30:00 UTC ; next_elapse=Thu 2026-09-10 20:30:00 CST }` |
| 旧机 | `omnigraph-daily-ingest.timer` | `{ OnCalendar=*-*-* 00/2:00:00 UTC ; next_elapse=Wed 2026-09-09 20:00:00 CST }` |
| 旧机 | `omnigraph-dajiala-scan.timer` | `{ OnCalendar=Sun *-*-* 23:00:00 ; next_elapse=Sun 2026-09-13 23:00:00 CST }` |
| 旧机 | `omnigraph-disk-cleanup.timer` | `{ OnCalendar=*-*-* 04:15:00 UTC ; next_elapse=Thu 2026-09-10 12:15:00 CST }` |
| 旧机 | `omnigraph-ingest-daily-summary.timer` | `{ OnCalendar=*-*-* 09:00:00 ; next_elapse=Thu 2026-09-10 09:00:00 CST }` |
| 旧机 | `omnigraph-kg-sync.timer` | `{ OnCalendar=*-*-* 18:30:00 UTC ; next_elapse=Thu 2026-09-10 02:30:00 CST }` |
| 旧机 | `omnigraph-kol-classify.timer` | `{ OnCalendar=*-*-* 16:00:00 UTC ; next_elapse=Thu 2026-09-10 00:00:00 CST }` |
| 旧机 | `omnigraph-kol-enrich.timer` | `{ OnCalendar=*-*-* 11:30:00 UTC ; next_elapse=Thu 2026-09-10 19:30:00 CST }` |
| 旧机 | `omnigraph-kol-zombie-cleanup.timer` | `{ OnCalendar=*-*-* 10:55:00 UTC ; next_elapse=Thu 2026-09-10 18:55:00 CST }` |
| 旧机 | `omnigraph-reconcile.timer` | `{ OnCalendar=*-*-* 12:30:00 UTC ; next_elapse=Thu 2026-09-10 20:30:00 CST }` |
| 旧机 | `omnigraph-rewrite.timer` | `{ OnCalendar=*-*-* 18:30:00 UTC ; next_elapse=Thu 2026-09-10 02:30:00 CST }` |
| 旧机 | `omnigraph-rss-fetch.timer` | `{ OnCalendar=*-*-* 09:00:00 UTC ; next_elapse=Thu 2026-09-10 17:00:00 CST }` |
| 旧机 | `omnigraph-rss-layer2-classify.timer` | `{ OnCalendar=*-*-* 11:20:00 UTC ; next_elapse=Thu 2026-09-10 19:20:00 CST }` |
| 旧机 | `omnigraph-rss-rescrape.timer` | `{ OnCalendar=*-*-* 09:30:00 UTC ; next_elapse=Thu 2026-09-10 17:30:00 CST }` |
| 旧机 | `omnigraph-translate.timer` | `{ OnCalendar=*-*-* 14:00:00 UTC ; next_elapse=Wed 2026-09-09 22:00:00 CST }` |

[KNOWN] 新机没有检出的 VitaX timer，也没有 root crontab 项。Hermes 另有启用的 Hermes cron `sync-kol-db-from-aliyun`（03:00 本地）；旧的 14 个 OmniGraph Hermes cron 已 disabled。WSL crontab 仍登记 Cognee batch 和 graphify-refresh，是否具备可执行目标／近期成功记录未验收。旧机 root cron 登记每日 KB rebuild。详见三份 `*-schedules.json`，不存在“新机有采集能力”的证据。

### 资源快照及审计中变化

- [KNOWN] Hermes 根分区约 16%；内存总量约 16.4 GB，available 约 11.6 GB。
- [KNOWN] 旧机根分区 68%；最近快照可用约 33.1 GB；内存总量约 15.8 GB，available 约 5.7 GB。
- [KNOWN] 新机 13:24 UTC 根分区 100%、available 0；13:30 UTC 已为 51%；13:36 UTC 仍为 51%、available 49.55 GB。由本轮以外的变更造成，具体执行者／变更清单待确认。
- [KNOWN] 新机 13:30 的 Docker 可见目录约 2.50 GB、containerd 7.81 GB、Qdrant bind mount 5.61 GB。没有发现大于 100 MB 的已删除但仍打开文件。与交接中 Docker 48 GB 的描述不再一致。
- [INFERRED / HIGH] 磁盘问题已在审计中被外部动作缓解；不能据此认定同步、数据一致性或恢复能力已经恢复。

证据：[最初资源](2026-09-09/mcp-inventory.json)、[磁盘复核](2026-09-09/mcp-disk-detail.json)、[最新旧机](2026-09-09/pipeline-runtime-checks.json)、[最新新机](2026-09-09/mcp-runtime-checks.json)。

## 5. 数据路径、数量与新鲜度

[KNOWN] 两台阿里云 KB health 均明确报告 `KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db`、图片目录 `/root/.hermes/omonigraph-vault/images`。旧机 vault 的数据库入口解析到同一实际文件。Hermes 的 repo data DB 与 vault DB 是不同快照；不能互换使用。

[COMPUTED] 下表为只读 SQL 事务内计数。时间字符串保持数据库原样；这些表混用带时区和无时区时间，未把简单 UTC 比较结果当作精确 24h 吞吐。

| 数据入口 | articles | RSS | ingestions | 最新成功微信 / RSS 时间（原值） |
|---|---:|---:|---:|---|
| 旧机 repo data（主采集数据） | 5056 | 3596 | 8578 | 2026-09-09 07:11:33 / 2026-09-08 18:10:41 |
| 新机 repo data（对外查询快照） | 4705 | 3537 | 8237 | 2026-09-03 00:24:59 / 2026-09-03 02:51:58 |
| Hermes vault 镜像 | 5056 | 3581 | 8563 | 2026-09-09 06:53:51 / 2026-09-08 18:10:41 |
| Hermes repo data 旧副本 | 4705 | 3496 | 8198 | 2026-09-02 23:06:04 / 2026-09-03 00:38:35 |

[COMPUTED] 初始快照中新机较旧机少 351 篇 articles、59 篇 RSS、341 条 ingestion 记录。它不是完整的新鲜镜像。新机 SQLite 最后替换成功记录为 2026-09-06 02:34:11 CST，表内最新 ingestion 是 9/5；文件 mtime 与业务时间是不同概念。

### Qdrant 和文件存储

| 当前 collection 族 | 旧机点数 | 新机点数 |
|---|---:|---:|
| [KNOWN] `chunks_bge_m3_1024d` | 9202 | 12366 |
| [KNOWN] `entities_bge_m3_1024d` | 129285 | 168831 |
| [KNOWN] `relationships_bge_m3_1024d` | 206046 | 250885 |

[KNOWN] 新机另保留三组带连字符的 `bge-m3_1024d` 与三组 `gemini_embedding_2_3072d`，共九个 collection；旧机为三组。现行三组均为 1024 维、Cosine、on_disk=true。仅读取集合元数据，没有导出向量或文章 payload。

[KNOWN] 新机总点数较大，但 9/9 同步日志明确记录缺少旧机 1478 个 entity ID。因此“点数更多”不等于“包含旧机全部当前数据”；同步实现只补缺失 ID，不覆盖相同 ID 的更新、不传播删除。

[KNOWN] 新机实际 `graph_chunk_entity_relation.graphml` mtime 为 2026-07-28T16:35:19Z，约 72.55 MB；`kv_store_full_docs.json` 为 2026-07-28T17:00:38Z，约 19.25 MB。这次核对的是实际文件，不只是 `.bak` 文件。

[INFERRED / HIGH] Qdrant、SQLite、graphml/KV 的新鲜度分离，是独立于磁盘容量的检索完整性风险。完整 KG 查询覆盖尚未验证，不能从 FTS 或 `/ready` 成功推断其消失。

## 6. 同步合同与缺口

**[KNOWN] 旧机 → 新机：** `/root/OmniGraph-Vault/deploy/sync_kq_to_new.py`；每日 18:30 UTC（次日 02:30 CST）。临时 SSH 隧道 `旧机127.0.0.1:16333 → 新机127.0.0.1:6333`；依次 entities/chunks/relationships 差集 upsert，成功后 SQLite `.backup` → SCP → 原子替换。upsert 三次失败立即退出，SQLite 阶段不执行。未包含 graphml、KV、images。9/7–9/9 在 entities 首批 HTTP 500 后中止；最后成功为 9/6。

**[KNOWN] 旧机 → Hermes：** Hermes system timer 05:00 UTC 调用 `scripts/sync-from-aliyun.sh`，拉取数据库、wiki、SSG articles、images；另一 Hermes cron 03:00 本地还同步数据库。均不是“旧机→新机 graphml/KV 同步”的替代。

**[KNOWN] 拉取脚本存在失败状态处理缺陷：** `scripts/sync-from-aliyun.sh:68–71` 在 `if ! do_one_rsync ...; then` 内读取 `$?`，得到的是逻辑取反后的 0。相同 shell 结构的确定性验证输出 0。这段源码与 Hermes 实际文件一致。

**[INFERRED / HIGH]** rsync 失败可能被上层报成成功，导致 systemd `Result=success` 和“sync OK”不能单独作为四类数据同步完成的证据。本轮只定位，未修复脚本。

[KNOWN] 在 root crontab、相关 system/user units 和 Hermes cron 范围内，未找到第二条旧机→新机持续 graphml/KV/images 同步。指定 Agent 也表示没有已知实现；是否存在外部平台或人工操作尚为 UNKNOWN。这是有界检索结论，不是全宇宙不存在的断言。

## 7. 模型、依赖和配置来源

| 用途 | 源码／现场证据 | 结论边界 |
|---|---|---|
| [KNOWN] 旧机文本 LLM | `lib/llm_deepseek.py` 默认 `deepseek-v4-flash`；生产环境 provider=deepseek | 已读源码／进程启动环境及历史 API 错误；未发起新付费生成 |
| [KNOWN] 旧机 Vision | DeepSeek 单 provider；默认 `deepseek-v4-flash-vision-exp`；运行日志 provider=deepseek | 有意生产漂移需保留；本轮未发图 |
| [KNOWN] 两机 embedding | `OMNIGRAPH_LOCAL_EMBED=1` + localhost:7997；合成输入均 HTTP 200、1×1024 | 验证实际服务输出维度；未新启动模型 |
| [KNOWN] DeepSeek 账户 | 两机当前配置 key 对官方 balance GET 均返回 `is_available=true`（13:36 UTC） | 历史 402 属实，不能继续断言当前余额耗尽；账户可用不等于完整 ingest 恢复 |
| [KNOWN] Hermes 对接会话 | CLI 恢复 `20260804_142454_aacd1b`，模型标记 deepseek-v4-pro；纯文字答复、退出 0 | 没有替换模型／改全局配置；答复只作历史背景 |
| [KNOWN] Hermes Qwen | service inactive、disabled、8001 未监听 | 未启动、未接入生产；历史 canary 未作为当前证明 |

[KNOWN] 旧机 `omnigraph-daily-ingest.service` 和 `kb-api.service` 都通过 `EnvironmentFiles=/root/.hermes/.env` 加载配置。新机 omni-kb-api/omni-mcp 没有 EnvironmentFile，存在显式 drop-in；项目 `config.py` 还会在进程内读 env 文件。`/proc/PID/environ` 主要是进程初始环境快照，不能证明 Python 后续加载或覆盖的全部值。

[KNOWN] 旧机 env 中 `EMBEDDING_MODEL=gemini-embedding-2` 为现存值；真实 embedding 服务输出为 1024 维。不能单凭该残留变量判断走 Vertex。

[KNOWN] 运行环境版本并不等同于仓库 requirements：旧机 venv-aim1 LightRAG **1.4.16** / qdrant-client **1.18.0**；新机 **1.5.4** / **1.11.3**；Hermes venv 为 LightRAG **1.4.15**，venv-aim1 为 **1.5.4**。包版本来自 dist-info；关键 LightRAG 文件另有 SHA 与补丁标记。补丁标记存在不等于已完成断电／SIGTERM 恢复测试，禁止据此直接重装覆盖。

[KNOWN] 凭据只核对存放路径、变量名和是否设置，未保存 key/token/cookie 值：两机与 Hermes 的 `~/.hermes/.env`；Hermes `~/.hermes/config.yaml`；旧机 `kol_config.py` 与相关忽略文件；SSH key 使用各机现有配置。模型和凭据均未修改。

## 8. 已验证接口与告警纠正

| 项目 | 本次结论 | 证据 |
|---|---|---|
| [KNOWN] 新机 MCP 公网 | initialize、tools/list、fts_search 成功；工具为 fts_search/kg_search/kg_poll | [公网探测](2026-09-09/mcp-public-probe.json) |
| [KNOWN] Hermes → 新机 MCP | 经本地 SSH 隧道完成同样 FTS 调用 | [隧道探测](2026-09-09/mcp-hermes-tunnel-probe.json) |
| [KNOWN] 新机 ready | HTTP 200；源码仅检测 KB `/health` | [初始现场](2026-09-09/mcp-inventory.json) |
| [KNOWN] 浏览器 CDP | WSL :9223、旧机反向 :58933 的 json/version 均 200 | [Hermes](2026-09-09/hermes-schedules.json)、[旧机](2026-09-09/pipeline-schedules.json) |
| [KNOWN] 旧机 :58931 Playwright MCP | 本轮标准 initialize 请求 HTTP 403；未绕过或修复 | [拒绝证据](2026-09-09/browser-reverse-tunnel-probe.json) |
| [KNOWN] 新机磁盘 | 审计中由 100% 降为 51%；本轮未清理 | [时间序列](2026-09-09/mcp-disk-detail.json) |
| [KNOWN] DeepSeek 402 | 9/9 日志确有错误；13:36 账户可用 | [日志](2026-09-09/pipeline-diagnostics.json)、[实时账户状态](2026-09-09/pipeline-runtime-checks.json) |
| [KNOWN] 六轮 ingest timeout | 08:05、10:05、12:05、14:05、16:05、18:05 CST 均为 start-pre 超时 | [systemd 原始消息](2026-09-09/pipeline-timeout-detail.json) |
| [KNOWN] 同步 | 13:36 仍 failed；当前批次未由本轮触发 | [最新状态](2026-09-09/pipeline-runtime-checks.json) |

[KNOWN] 六次失败对应 `TimeoutStartSec=300` 与 `ExecStartPre=...cleanup_stuck_docs.py --all-failed`；不是“每小时一次”，而是每两小时一次。运行 4h 的紧急墙存在，但不是这六次启动前失败的触发点。20:00 CST 本轮服务已经通过启动前阶段，MainPID 460480 正在运行；仍需单独观察持久化成功结果。

[INFERRED / MED] 磁盘满与新机 Qdrant upsert HTTP 500 时间上相符，是同步失败的强候选原因；本轮没有成功取得对应时刻的 Qdrant 服务端磁盘错误文本，不能将因果关系标为已闭环。Docker logs 大量历史读取曾超时，随后改为有界读取实际日志尾部；外部清理后尾部没有旧错误。

## 9. 备份、自动恢复与待确认事项

[KNOWN] 旧机保留 `.t7-backup-20260903T183039Z`、`.t6-deploy-backup-20260903T184234Z`、`.healthcheck-backup-20260904-025758` 等部署备份，以及图谱 KV 历史副本。目录存在不等于整库可恢复。`qdrant-snapshot.service` failed、timer inactive。

[KNOWN] 健康检查 timer 会运行现有 `mcp-healthcheck.py`；其代码／运维资料包含 Telegram 通知和部分自动恢复逻辑。为避免“检查”隐式重启，本轮没有手动执行这个脚本。正式健康与新鲜度应依据持久化数据、任务退出和调用链验证。

[KNOWN] 有界检查未建立近期 graphml/KV/images/SQLite/Qdrant 全套一致性备份和恢复演练的证据；异地备份记录只得到历史说明，未连接第四台备份主机。此项保持 **UNKNOWN**。八个 W5B 工作树的具体负责人、是否已完全合并及是否仍有人使用也保持 **UNKNOWN**。

## 10. 后续工作顺序与验收要求

1. [INFERRED / HIGH] 先核对审计中外部磁盘清理的变更清单，并确认日志轮转和保留策略；不能把 51% 当成长期修复。
2. [INFERRED / HIGH] 恢复旧→新同步前，记录两端数据与代码 manifest，验证 upsert 500 的实际原因；成功标准包含三组缺失 ID、SQLite 完整替换及业务时间，而不是服务 active。
3. [INFERRED / HIGH] 明确 graphml/KV/images 是否属于查询必需的持续同步合同，验证当前 KG 引用／实体／正文的一致性；禁止只补 Qdrant 就宣告完整同步。
4. [INFERRED / HIGH] 调查 cleanup_stuck_docs 启动前阻塞并修复 Hermes 拉取退出码；保持真实失败传播，不靠放宽 4h 参数掩盖启动前问题。
5. [INFERRED / HIGH] 对生产漂移逐文件归属／差异审阅，确认八个 W5B 分支合并关系；再制定回收 main 与版本化部署方案。
6. [INFERRED / HIGH] 补近期完整备份与隔离恢复验证，最后进行有授权的完整 ingest→同步→MCP KG 查询验收。

本轮没有执行上述修复。审计中新增问题记录在本文，不自动改写用户交接文档或把其建议转成生产操作。

## 11. 证据说明与复核入口

[KNOWN] [证据目录索引](2026-09-09/README.md) 包含采集时间、主机身份、服务属性、文件 SHA、只读 SQL 聚合、脱敏日志、探测结果和 Agent 回答。排除了真实凭据、正文、图片和向量 payload；没有复制整个远端数据库或大 JSON。

只读复核示例（使用这台 Mac 已验证的别名）：

```bash
ssh OHPC 'hostname; git -C /home/sztimhdd/OmniGraph-Vault status --short'
ssh ack-node-2 'hostname; systemctl show omnigraph-daily-ingest omnigraph-kg-sync -p ActiveState -p SubState -p Result -p ExecMainStartTimestamp'
ssh ack-node-1 'hostname; df -h /; systemctl is-active omni-kb-api omni-mcp embed-server'
```

[KNOWN] 所有快照都是时间点证据。完整 KG 合成、文章抓取／微信登录状态、正式 UAT、灾难恢复、外部备份覆盖和 WIP 归属没有被这次有限探测证明。
