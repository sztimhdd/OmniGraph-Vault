# PROJECT — Aliyun Ingest Migration v1

> **Status:** Q1-Q6 decided (2026-05-20 evening), ready for `/gsd:new-milestone`.
>
> Authored as a follow-up to LLM Wiki Integration W1 phase (2026-05-20). Captures user decision to migrate ingest pipeline from Hermes (家用 PC, WSL2) to Aliyun ECS, retire Hermes as primary, and treat Aliyun as new authoritative ingest node.

---

## 1. Background

### Current State (as of 2026-05-20)

| Concern | Hermes (家用 PC, WSL2) | Aliyun ECS (101.133.154.49) | Databricks App | Local (`.dev-runtime/`) |
|---|---|---|---|---|
| Role | **Ingest 主力** + 历史镜像源 | **只读消费** (Caddy + kb-api) | 只读消费 (双语 SSG) | 开发 + 调试 |
| Daily cron | ✅ 11 个 cron 任务 (scan + ingest + reconcile) | ❌ 无 | ❌ 无 | ❌ 无 |
| LightRAG storage | ✅ 1.6 GB 主拷贝 | ❌ 无 | ❌ 无 | ✅ 1.6 GB 镜像 (今天刚同步) |
| LLM API keys | ✅ DeepSeek + SiliconFlow + Vertex SA | ✅ Vertex SA only (kb-api 用) | ✅ Foundation Model serving | 部分 (corp 网络限 DeepSeek + SiliconFlow) |
| `kol_scan.db` | ✅ 写入主源 | 只读拷贝 | 只读拷贝 | 只读拷贝 |
| Wiki source-of-truth | `~/wiki-omnigraph/` (Hermes-side hand-curated, 1 entry) | ❌ | ❌ | ✅ `kb/wiki/` (repo, 14 entries 由 W1 写入) |

### v1.0 → 1.0.y 现状评估

Hermes 端 cron ingest 已经稳定运行：
- v1.0 stable 自 2026-05-13 declared，11 daily crons
- 94 articles (87 KOL + 7 RSS) 入图
- $1-5/day operating cost
- Ghost success class 已经 surfacced 并 mitigation 部署 (RETRY=300, bidirectional reconcile, MAX_ARTICLES tri-governor)

**用户判断 (2026-05-20):** Hermes 每天 cron ingest 已经很稳，可以迁移阿里云了。

---

## 2. Goal

把 ingest pipeline 从 Hermes 迁到阿里云 ECS，让阿里云成为新的 authoritative ingest node。

**目标终态：**

```
阿里云 ECS (101.133.154.49)
  ├─ systemd timer (取代 Hermes cron)
  ├─ batch_ingest_from_spider.py 主循环
  ├─ LightRAG storage (1.6 GB+，从 Hermes 迁过来)
  ├─ kol_scan.db 写入主源
  ├─ images/ 写入主源
  ├─ wiki write-back: ingest 后自动 commit + push wiki 增量到 repo
  └─ kb-api (continues to serve, but now reads local 写入的 storage)

repo (GitHub)
  └─ kb/wiki/ — wiki 权威源，阿里云 push，所有消费方拉

Hermes
  └─ Retired to read-only backup / dev sandbox 角色

Databricks + 本地 .dev-runtime/
  └─ sync-from-aliyun.sh (手动) 拉 images / db / lightrag
```

---

## 3. 用户已敲定的决策 (2026-05-20)

### Decision 1: Wiki source-of-truth = repo

> "Hermes从repo拉 存量wiki本地已经写好了14个了，增量未来由阿里云主力来写更新到repo，Databricks和Hermes只管拉就行"

- repo 是 wiki 权威源
- 阿里云 ingest 后自动 commit wiki 增量 → push 到 repo
- Hermes / Databricks / 本地 = 都从 repo 拉 wiki，不允许在消费侧编辑

### Decision 2: 同步脚本 — 暂缓

> "(a)先不写 写文档加入milestone"

- 不写过渡性 `sync-from-hermes.sh`
- 等阿里云 ingest 上线后，再写 `sync-from-aliyun.sh`
- 当下临时缺数据用手动 ssh+tar (今天的 18 hash dirs 已经处理掉)

### Decision 3: 迁移触发条件 = "Hermes cron 稳了"

> "我自己感觉hermes每天cron ingest已经很稳 可以迁移阿里云了"

- 不再等 v1.x 加新 feature
- 现在 (2026-05-20) 状态稳定就开始迁

### Decision 4: kb-api 维持现状,Agentic-RAG-v1 接管 query API

- kb-api 在阿里云上仍然只读 SSG + DB,**不集成 LightRAG query**
- 不引入 `/api/synthesize` 端点 (留给 Agentic-RAG-v1 milestone)
- 这个 milestone 只管 ingest 迁移,不动 kb-api

### Decision 5: 每日同步阿里云 → Hermes + Databricks (取代独立 cold-backup milestone)

> "Hermes 停 cron,然后每天搞一个同步阿里云文章、数据库、图片和 wiki 到 Hermes 和 Databricks"

- Hermes 11 个 ingest cron 全部停掉
- 阿里云成为单一写入源
- 每天 (cron) 从阿里云拉:articles + DB + images + wiki → Hermes + Databricks
- 拉模式 (consumer-side cron),阿里云不感知下游
- 替换原 §8 衍生 milestone "Aliyun-Hermes-Coldbackup-v1" 和 "Aliyun-Mirror-Sync-v1"
- 这部分纳入 **本 milestone 主 scope**,不另起新 milestone

---

## 4. 待定 (Open Questions)

下面这些是必须在 /gsd:plan 之前讨论清楚的：

### Q1 — Migration 切换策略

**(a) Cutover** — 阿里云 ingest 先 dry-run 验证一段时间 → 某天双方都跑 1 天对账 → 第二天 Hermes cron 全部停掉，阿里云接管。一刀切，简单。
**(b) Dual-write 过渡期** — 两边并行跑同一份 candidate pool 一段时间 (1-2 周)，对比输出一致性，再 cut over。安全但复杂，要解决 candidate pool 不被双重消费的问题 (`ingestions` 表不能两边都写)。
**(c) Phase migration** — 按 cron job 一个一个迁 (先迁 RSS scan，跑稳了再迁 KOL scan，最后迁 batch ingest)。最稳但最慢。

我倾向 **(a)** — Hermes cron 已 N=20 burst test pass + 0.5% ghost rate，对账机制 (bidirectional reconcile) 健全，没必要 dual-write 增加复杂度。

**Decided (2026-05-20):** **(a) 简单 cutover**。接受丢 1 天文章换取切换简洁。不做 dry-run buffer day，不双写。Cutover 当天 Hermes cron 停掉，阿里云接管，中间 1 天的候选文章接受丢失。

### Q2 — LightRAG storage 迁移方式

**(a) 全量同步** — 1.6 GB tar.gz 直接 scp 过去，阿里云解开就用
**(b) 阿里云从空开始重新 ingest** — 用现在的 `kol_scan.db` 当 candidate pool，重跑 ingest 重建 graph。代价：~$300+ API 重花一次 + 多天时间
**(c) 增量同步** — 不存在，LightRAG 内部是 LanceDB + Kuzu 二进制文件，不可拆解

(a) 是唯一现实选项。但要注意:
- 阿里云 ECS 磁盘空间 (要确认还有 >5 GB free)
- 迁移期间需要 Hermes cron 暂停，避免 storage 在传输中被改

**Decided (2026-05-20):** **(a) 全量 tar.gz**,加 3 个硬约束:

1. **Hermes cron 必须暂停 ≥30min** (整个 tar + scp + 校验窗口),避免 storage 边传边改
2. **rsync --checksum verify** (不只比 size + mtime;tar 解出来后跑 sha256 对比 entity_count + relation_count + chunk_count 全部 ±0%)
3. **30 天双备份**:Hermes 那边的 tar.gz 留 30 天作为冷备,阿里云解压用,Hermes 原 storage 不删 (read-only 保留至少 30 天)

### Q3 — Hermes 退役 ≠ 关机

Hermes 仍然是用户的家用 PC。"Retire" 不是关机，而是：
- 停掉所有 daily cron (取消 `crontab` 11 entries)
- 保留 SSH 通道作为 dev sandbox 用 (E2E 测试、debug)
- 保留 LightRAG storage 一份冷备 (最近 30 天的快照)
- 不再写入 `~/.hermes/omonigraph-vault/` (read-only)

需要决定：cold backup 频率？(每周一次？每月？)

**Decided (2026-05-20):** **每天同步,取代独立 cold-backup milestone** (见 §3 Decision 5)。

- 不再做"每周一次"或"每月一次"的快照
- 每天 cron 从阿里云拉 articles + DB + images + wiki → Hermes + Databricks
- 拉模式 (consumer-side cron),阿里云不感知下游
- 出大事 (阿里云挂)时 Hermes 上的最新一次 daily sync 就是接管起点 (RPO ≤ 24h)
- Hermes "retire" 含义:停 11 个 ingest cron,保留 SSH + read-only,新增 1 个 daily-pull cron

### Q4 — Wiki write-back 的实现

阿里云 ingest 后自动 commit wiki 增量到 repo。但具体怎么触发？

**(a) cron 末尾 hook** — 每次 batch ingest 完，跑一个 wiki update prompt (原 P2 角度 C 设计)，自动写新 entity wiki page，commit + push
**(b) 周度批量** — 每周一次专门跑 wiki update job，不耦合到 ingest cron
**(c) 手动触发** — 用户判断 "这周入了多少新 entity"，手动跑 wiki update

W1 phase 的 LLM Wiki integration 设计文档里 (commit `7eda4ff`) 列出 P2 角度 C 是 "入库末尾 hook 触发 wiki 更新建议"。如果迁移之后才考虑 P2，那 (c) 是当前默认；P2 phase 上线后切到 (a)。

**Decided (2026-05-20):** **(c) 当前 + P2 切 (a)**。

- 迁移期 + 后续 1-2 周:手动 commit wiki 增量到 repo (用户判断节奏)
- LLM-Wiki-Integration-P2 milestone 上线后切到 (a) 自动 hook
- P2 实现需要的额外资产:阿里云 ssh deploy key + git config aliyun-bot identity (在 P2 milestone 处理,不在本 milestone 内)

### Q5 — kb-api 直连 LightRAG vs 间接

阿里云 kb-api 当前只读 SSG + DB。迁移后 kb-api 是否要直连 LightRAG 提供 query API？

**(a) 直连** — kb-api 集成 `kg_synthesize.py` 路径，提供 `/api/synthesize` 端点。同进程内存压力大 (Vertex SDK + LightRAG 加载)
**(b) 间接** — kb-api 仍然只读 SSG + DB，synthesize 由独立 worker 进程提供，kb-api 反代过去
**(c) 不动** — kb-api 维持现状，synthesize 仅在本地或者 Databricks 提供

跟 Agentic-RAG-v1 milestone 强相关，可能 (c) 让 Agentic-RAG-v1 milestone 接管。

**Decided (2026-05-20):** **(c) kb-api 维持现状,Agentic-RAG-v1 接管 query API**。

大白话解释:
- kb-api 现在做 2 件事:(1) 提供静态 SSG (HTML/CSS/JS),(2) 提供 DB 只读 API (`/api/articles`, `/api/article/{hash}` 等)
- 迁移后 LightRAG 数据会落在阿里云上
- 问题是:要不要给 kb-api 加一个新功能 — 用 LightRAG 回答问题 (`/api/synthesize`)?
- 决定:不加。kb-api 还是做原来 2 件事,**问答能力**单独由 Agentic-RAG-v1 milestone 处理
- 这样这个 milestone 只负责 "ingest 搬家",不动 kb-api 行为,scope 收紧

### Q6 — 成本

阿里云 ECS 现规格 (待确认) 是否撑得住 ingest workload？
- LightRAG ainsert 同时跑会消耗 ~2 GB 内存峰值
- Vertex embedding 单条 article 几百次调用，网络是否稳？
- DeepSeek + SiliconFlow 在阿里云 ECS 的延迟 vs Hermes (corp 网络)？

需要在阿里云上跑 1-2 个 article 的 dry-run 测延迟 + 内存峰值。

**Decided (2026-05-20):** **24 小时后阿里云 ECS 升级到 8 vCPU / 16 GB RAM**。

- 16 GB 远大于 LightRAG ainsert ~2 GB 峰值,内存余量充裕
- 8 vCPU 能撑并行 vision + embedding workers
- Phase 1 (readiness 验证) 必须包含:LightRAG 内存峰值 dry-run + DeepSeek/SiliconFlow/Vertex 从阿里云的 RTT 测量
- Hermes 还可用一周,阿里云内存升级 24h 后开始本 milestone Phase 1

---

## 5. Scope

### In Scope (本 milestone 必做)

1. **阿里云 ECS readiness 验证**
   - 磁盘空间 (>5 GB free)
   - LLM provider 网络可达性 (DeepSeek + SiliconFlow + Vertex)
   - LightRAG 内存峰值 dry-run
   - 1-2 article smoke ingest (从 Hermes Apify token 借用)

2. **Provider keys + env 部署到阿里云**
   - `~/.hermes/.env` 等价配置在阿里云 (`/etc/omnigraph/.env`?)
   - DeepSeek API key + SiliconFlow API key + Vertex SA JSON

3. **Code 部署到阿里云**
   - `git clone` (或者复用现有 vitaclaw-site 仓库)
   - venv + requirements.txt
   - `local_e2e.sh` smoke 跑通

4. **systemd timer 取代 Hermes cron**
   - 11 个 cron 任务对应改成 systemd .service + .timer
   - 启动顺序 + 失败重试策略
   - 日志 → journald

5. **LightRAG storage 全量迁移**
   - Hermes 上 tar.gz `~/.hermes/omonigraph-vault/lightrag_storage/`
   - scp 到阿里云
   - 解压 + 验证 entity count + relation count 与 Hermes 一致

6. **kol_scan.db cutover**
   - Hermes cron 暂停
   - 最后一次 db 同步到阿里云
   - 阿里云接管写入
   - Hermes side 改为只读挂载 (或定期从阿里云拉)

7. **Hermes cron 停用 + 监控**
   - 取消 11 个 ingest crontab entries
   - 第一周每天检查阿里云 cron 输出
   - Hermes 保留 SSH + read-only

8. **每日同步阿里云 → Hermes + Databricks** (Decision 5,取代 cold-backup milestone)
   - consumer-side cron 脚本:`scripts/sync-from-aliyun.sh`
   - 拉内容:articles + DB (`data/kol_scan.db`) + images + wiki
   - Hermes 端 cron:每天 1 次,落到 `~/.hermes/omonigraph-vault/` (read-only refresh)
   - Databricks 端:通过 git pull 获取 wiki + DB 增量 (Databricks 不需要 ingest 数据本身)
   - 7 天稳定运行无失败是 milestone 完成条件之一 (见 §7 SC #8)

### Out of Scope (另起 milestone 或 deferred)

- ❌ `sync-from-aliyun.sh` 高级特性 — 增量优化、断点续传、并行多 worker 等性能调优,本 milestone 只做最简 daily full pull;v2 (Aliyun-Sync-v2) 处理
- ❌ Wiki write-back 自动化 — 目前手动 commit 即可；P2 phase 单独做 (LLM-Wiki-Integration-P2 milestone)
- ❌ kb-api 直连 LightRAG / `/api/synthesize` 端点 — Agentic-RAG-v1 milestone 接管 (Decision 4)
- ❌ Hermes 独立 cold backup 周期/月度快照 — 已被 daily sync 取代,不再需要 Aliyun-Hermes-Coldbackup-v1
- ❌ kb-api 行为变更 — 维持现状 (Decision 4)

---

## 6. 风险

| 风险 | 影响 | Mitigation |
|---|---|---|
| 阿里云 ECS 资源不够 (内存/磁盘) | ingest 跑不动 | 24h 后升 8 vCPU / 16 GB RAM (Q6 决策);Phase 1 dry-run 验证内存峰值 |
| LLM provider 在阿里云延迟高 | ingest 时间拉长 | Phase 1 测延迟; SiliconFlow 国内访问应该比 Hermes (corp 网络) 还快 |
| LightRAG 数据迁移损坏 | KG 整个完蛋 | tar.gz + sha256 + entity/relation count ±0% verify (Q2 3 约束); Hermes 原 storage read-only 留 30 天双备份 |
| Cutover 期间漏 ingest | 1 天数据缺失 | 接受 (Q1(a) 决策);cutover 选 Hermes 当天 cron 跑完后立刻执行,把窗口压到最小 |
| Wiki write-back 自动化没到位前，wiki 增量丢失 | 迁移后 entity 没人写 wiki | 接受过渡期手动写 wiki，Q4(c) 默认;P2 milestone 上线后切 (a) auto |
| 成本上升 (阿里云 ECS 升配 + 网络) | $$ | 升级到 8C/16G 是已决定的硬支出;monthly baseline 在 Phase 1 readiness 报告中量化 |
| P2 wiki write-back 需要 ssh deploy key | 阿里云被 git push 暴露面增加 | 走 deploy key (read+write 限定到本 repo) + git config aliyun-bot signing identity;在 P2 milestone 中实现,不在本 milestone 内 |
| Daily sync 失败 (网络/磁盘满/阿里云挂) | Hermes/Databricks 数据滞后 ≤ RPO 24h | sync 脚本失败重试 3 次 + journald 日志;7 天稳定运行作为 SC#8;失败超 48h 触发告警 |

---

## 7. Success Criteria (mile-stone 完成定义)

1. ✅ 阿里云 systemd timer 跑 7 天连续无失败
2. ✅ Hermes 11 个 ingest crontab 全部停 (`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` = 0)
3. ✅ 阿里云 LightRAG entity_count + relation_count = 迁移前 Hermes 的 ±0% (Q2 sha256 + count verify)
4. ✅ Reconcile 7 天对账 ghost_success rate < 1%
5. ✅ Vertex AI quota 月用量 在原预算内 (没飙升)
6. ✅ kb-api 行为无回归 (Decision 4: 维持只读 SSG + DB,不加 `/api/synthesize`)
7. ✅ 所有 cron 输出有 journald 日志可查 (`journalctl -u omnigraph-*`)
8. ✅ Daily sync 阿里云 → Hermes + Databricks 跑 7 天连续无失败 (Decision 5)

---

## 8. 衍生 Milestone 候选

(Decision 5 把 Aliyun-Mirror-Sync-v1 + Aliyun-Hermes-Coldbackup-v1 折叠进本 milestone 主 scope。剩余衍生:)

### Aliyun-Sync-v2 (低优先级,本 milestone 7 天稳定后再考虑)

- 增量同步优化:rsync --partial、断点续传
- 并行多 worker 拉取
- 选择性同步 (只拉 wiki / 只拉 images 等 flag)
- 当前 v1 是 daily full pull,跑稳了再优化

### LLM-Wiki-Integration-P2

- 入库 hook → wiki 自动写 (Q4 决策的 (a) 阶段)
- 跑在阿里云上 (因为 ingest 在那里)
- **新增依赖**:阿里云 ssh deploy key (限定本 repo 的 read+write) + git config aliyun-bot identity
- 写完 commit + push 到 repo,所有消费方下次 daily sync 拉到

---

## 9. Next Step

**Q1-Q6 已 decided (2026-05-20 evening),进 `/gsd:new-milestone` 流程。**

预期 phase 结构 (gsd-roadmapper 会基于本文档生成最终 ROADMAP):

| Phase | 内容 | 依赖 |
|---|---|---|
| **P0 Readiness** | 阿里云 8C/16G 升级后 dry-run:磁盘 free >5GB / DeepSeek+SiliconFlow+Vertex RTT / LightRAG 内存峰值 / 1-2 article smoke ingest | 等阿里云 24h 后升配完成 |
| **P1 Code + env 部署** | git clone + venv + requirements.txt + provider keys + `local_e2e.sh` smoke 跑通 | P0 done |
| **P2 LightRAG storage 全量迁移** | Hermes cron 暂停 ≥30min + tar.gz + scp + 解压 + sha256 + entity/relation count ±0% verify (Q2 3 约束) | P1 done |
| **P3 Cutover** | systemd timer 取代 11 个 Hermes cron + kol_scan.db cutover + Hermes crontab 清空 | P2 done,接受 1 天数据丢失 (Q1) |
| **P4 Daily sync** | `scripts/sync-from-aliyun.sh` consumer-side cron + Hermes/Databricks 端 daily pull | P3 done |
| **P5 7-day stability** | 监控 systemd timer + reconcile + daily sync 全部 7 天无失败,达到 §7 SC #1/#4/#7/#8 | P4 done |

**Milestone 创建时机:现在** (2026-05-20 evening) — 调用 `/gsd:new-milestone Aliyun-Ingest-Migration-v1` 生成 REQUIREMENTS.md + ROADMAP.md。Planning artifact 与 Aliyun 升配并行进行。

**Phase 0 (Readiness) 执行时机:24h 后** — Aliyun ECS 升到 8 vCPU / 16 GB RAM 完成后启动 P0。Hermes 还能继续跑一周,无时间压力。

Out-of-scope 衍生 milestone (LLM-Wiki-Integration-P2 / Aliyun-Sync-v2 / Agentic-RAG-v1) 见 §8,不在本 milestone 内。
