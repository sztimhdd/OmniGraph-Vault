# VitaX 第二阶段行动计划与审阅

后续顺序已被用户要求的[产品架构重建](2026-09-09-vitax-product-architecture.md)取代。已完成证据保留；不再为了旧pipeline一致性追加探针。

日期：2026-09-09。范围：代码与现有证据核对、计划审阅；本轮不执行生产操作。首波结果见 [执行账本](../../../EXECUTION.md)。

## 裁决与流程

[INFERRED / HIGH] ask-matt 当前路线是既有规格与工单 → 有界 implement → 独立 review；无需重新 grill、重写规格、另建 tracker 或采用 wayfinder。本计划细化既有 VX 工单，不新增一套平行项目管理体系。

[INFERRED / HIGH] 下一阶段以“隔离单篇正确入库”为主线，并行做发布合同和最小故障恢复。先证明现有接口能完成真实业务，再扩大模型适配或迁移。Hermes 文本响应与 56 项局部测试不能替代文章质量、持久化和生产验收。

## 核对结果

- [KNOWN] 本轮 Git 状态统计仍有 930 个 tracked 删除、10 个修改、18 个未跟踪项；这是状态条目而非文件总数。保留原整理 WIP，不据此批量提交或清理。
- [KNOWN] [首波报告](../../deployments/2026-09-09-first-wave/FIRST-WAVE.md)与[真实适配器探针](../../deployments/2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md)分别限定了局部与合成验证范围。本轮未重复模型调用、56 项测试或 SSH 巡检；主机健康与余额不作为当前已验证事实。
- [KNOWN] `scripts/probe_e2e_v3_2.py:474` 复用 `ingest_article`，但从 checkpoint 开始；`:598` 的执行器会递归清理目标目录。`scripts/bench_ingest_fixture.py:390` 直接调用 `ainsert`，不能代替入口编排验证。
- [KNOWN] `lib/llm_complete.py:45` 默认仍选 DeepSeek；Hermes 是显式选项。分类、embedding 和 Vision 并未统一走该回调。文本适配器不是整条 pipeline 的模型迁移。
- [KNOWN] `ingest_wechat.py:502` 的 402 路径可留下 degraded marker；因此 checkpoint 完成或进程 exit 0 不足以证明图入库成功。需检查实际 doc 状态、实体/关系与查询引用。
- [KNOWN] `batch_ingest_from_spider.py:2478` 的 Wiki hook 与最终 storage flush 不构成同一原子结果；Wiki suggestion-only 不等于公开页面更新。
- [KNOWN] `kb/scripts/rebuild_fts.py:44` 重建 FTS 并填入 `rec.body`；这里是内容质量过滤，不是新公开站点的发布授权边界。`kb/export_knowledge_base.py:427` 只保证单文件替换，不保证整个发布版本一致。
- [KNOWN] `deploy/sync_kq_to_new.py:150` 使用旧端 ID 减新端 ID 的差集；不能据此保证已有 ID 的更新、删除及图/KV 等组件一致。

## 执行顺序与最小任务包

下表为 [INFERRED / HIGH] 主控下一轮派工方案；任务结束须返回 STATUS、CHANGES、EVIDENCE、RISKS、NEXT，实施者无最终验收权。

| 顺序 / 工单 | 实施范围与复用 | 验收门槛 |
| --- | --- | --- |
| 1 / VX-001 E2E 子集、004 隔离前置 | 只核对本次将执行的入口、模型、embedding、storage 与 Wiki 文件的远端漂移；VX-001 全量处置表仍为 partial，不以子集过门关闭；复用现有 `ingest_article` 和 fixture。先离线建立最薄的隔离 harness，不原样调用会 rmtree 的 probe 主执行器 | 所有 DB、RAG、checkpoint、图片、实体 buffer、Wiki 输出均落在新建受控目录；拒绝根目录、共享目录、路径穿越及 symlink 逃逸；启动前禁用默认 env 加载并清理非必要继承凭据；Qdrant 使用已验证的独立实例或独立集合，不把 RAG 目录当向量隔离证据；无隐式 provider 选择；离线验证禁止网络，真实调用只允许派工列出的模型和 embedding 入口，记录拒绝其他出口的证据 |
| 2 / VX-004 单篇图与查询 | 前置门通过后在 PC 隔离目录运行一个小型合成文本；沿 `get_rag → ingest_article → finalize`，复用已验证的 1024d embedding 入口与显式 Hermes 回调 | 文档 processed、无 degraded、实体/关系与 doc ID 可关联；重启读端后查询能引用该文档；第二次输入不重复；模拟超时/额度失败不写成功标记、不自动切换付费模型。记录调用次数、总耗时、实际输入长度和输出格式，不能用一次 30.775s 算术探针推算批量性能 |
| 3 / VX-004 Wiki 候选 | 图结果落盘后，复用现有 `kb/wiki_articles.py` / compiler 产生候选 | Wiki applied 或持久 suggestion 可证明“候选完成”，公开更新另验；输入 doc ID、持久化候选与来源可关联 |
| 4 / VX-004 真实输入 | 候选验收后单独派工，明确来源 URL、CDP、输出目录及允许的调用；验证发现、抓取、清洗、翻译和关键图片 | 图片价值判断、来源 caption 和 doc 映射可追踪；跳过的步骤明确未验收；这一步通过之前不关闭 VX-004，不让抓取故障覆盖图/Wiki 的既有结果 |
| 并行 A / VX-007 发布合同 | 先做离线清单与缺项拒绝，不等 VX-004/005 整项完结。复用 SQLite backup、现有导出与 FTS 代码，优先标准库 JSON/hashlib 与文件操作 | 一个版本关联 SQLite、向量、图/KV、Wiki、图片和公开内容；一致快照边界明确；损坏、缺项、混版本被拒绝。分开定义私有备份与公开服务产物及 FTS/向量允许读取的集合；离线验证产物投影，不能冒充运行查询隔离。真实私有哨兵负向查询由 VX-009 执行 |
| 并行 B / VX-005 最小恢复 | 先用隔离故障 fixture 复现死亡进程遗留 processing 与重复启动；复用现有 checkpoint、超时回滚和平台进程锁，只补缺失行为 | 活任务不被当孤儿清理；同一批次只能有一个写入者，须提供锁获取/拒绝记录和两个竞争进程的碰撞 fixture，不能以存在锁符号代替；重试不丢原始资料、不伪报成功；涉及 batch orchestration 必跑 AGENTS 指定的 orchestration/schema 回归。先离线，不为第一篇验证扩大成通用恢复系统 |
| 后续 / VX-006 修复升级 | 复用已成功的 Hermes→Codex 通道，换成一个可复现的隔离代码故障与确定性测试 | 真实 diff + 红绿验证 + 独立复审；四类受保护动作在执行前拒绝；额度耗尽进入暂停，不升级以绕额度。未取得请求关联路由证据的字段保留 UNKNOWN，不重做无关登录/算术探针 |

## 发布依赖的修正

[INFERRED / HIGH] 区分“合同可以开工”与“生产可以发布”：

1. VX-007 离线合同可立即开始；不依赖旧同步算法 VX-003 或完整恢复 VX-005。VX-002 的现有基线足够定义候选，部署前刷新现场。
2. VX-008 的候选演练依赖 VX-007 清单验证与 VX-004 已验收样本；生产发布另需源端写入/快照一致性控制和目标环境检查，不能因为合同通过就切生产。
3. VX-009 先接一篇公开文章 + FTS，复用 ZIP 界面与现有 KB 数据接口；去掉 mock 成功回退。公开读取集合在 VX-007 定义；运行中的 FTS/向量/引用私有哨兵测试在 VX-009 上线验收之前执行，不能等到 VX-010 才补。
4. VX-010 再接 BYOLLM；VX-011 验证真实日更、暂停续跑与故障通知；VX-012 最后单写入切换和单云收尾。旧云保留是现有证据支持的候选方案，切换前仍检查共享 Caddy 与 vitaclaw-site。

## Ponytail 删减裁决

- [INFERRED] 不做通用 Agent 调度框架、全模型统一网关、新消息队列或自建分布式锁。已有 Hermes、Codex、systemd、checkpoint 和本地锁先满足单机需求。
- [INFERRED] 不重写 ingestion、Wiki compiler、FTS 或整个前端；仅在真实失败处补最小接口。新增包装器须证明既有函数/CLI 无法安全组合；不能包装后隐藏破坏性行为。
- [INFERRED] 不给即将退役的旧同步补全所有功能。若影响当前在用 MCP 的可用性，再单列最小修复；新发布以版本契约实现。
- [INFERRED] 不把每项计划变成新的脚本、配置或文档。首阶段至多 2–3 个独立子任务并行，写范围互斥；审阅者只审具体结果。已通过的测试无新变化不重跑。

## 本轮完成标准

[KNOWN] 本轮完成的是行动计划审阅，不是第二波实施。后续按既有授权由主控划定具体允许路径和运行边界，无需重新询问架构与恢复参数；永久删除原始数据、不可逆迁移、账户/凭据变更及新增付费资源仍保留用户批准边界。

## 独立审阅处置

[KNOWN] 两名子代理分别追踪 E2E 源码与独立审查计划。主控核对并修正了 VX-003 原始退出码措辞；第二轮审阅的四项 Important 已逐项落实：VX-001 子集不冒充全量完成、Wiki 与真实输入拆分、合同与运行查询隔离证据分开、互斥要求实际碰撞证据。此为计划审阅通过，不是功能 PASS。
