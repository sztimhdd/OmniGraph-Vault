# 旧KG一致副本的权威、原生快照与读取绑定

Parent: VX-012 / #98 / 三模块计划R6
Status: proposed / ready-for-review；待执行
Assignee: unassigned
Type: task（Sol只读现场取证，产生决定，不复制/恢复/提升）
Blocked by: None

## Question

怎样在保留目标历史集合和当前服务回滚的前提下，给实际KG consumer一份同版SQLite、graph/KV/chunks与向量副本？

## Required Answer

- [ ] 逐个source-owned collection/文件及实际writer/consumer；哪些目标额外记录归属未明，保留位置是什么。
- [ ] 两端Qdrant实际版本/单机或分布式拓扑、collection snapshot能力/目录、源与目标空间及完整候选的存储/时间预算。
- [ ] 当前LightRAG/KB实际如何绑定候选collection与working_dir，能否用已有设置隔离读取；不能用config intent代替候选调用证据。
- [ ] 枚举影响快照的writer（含cleanup/cache/其它任务），明确静止信号、可授权维护窗、需冻结的具体timer、备份和恢复顺序；不强杀在写进程。
- [ ] 给出固定SOURCE_SET、CANDIDATE_NAMES、CONSUMER_BINDING、QUIESCE_AND_ROLLBACK和R6允许对象；不清楚则明确BLOCKED及第一证据，不写“待定”实现。

默认推荐原生完整collection快照恢复到新集合，同时保留文件与alias配置；不先设计增量哈希/删除watermark。Qdrant快照不包含aliases，恢复版本有约束，新集合应以snapshot priority恢复；必须核当前版本/能力，参考[官方快照说明](https://qdrant.tech/documentation/operations/snapshots/)。这些官方能力不是现场已可用证明。

只使用部署基线已存在的SSH/HTTP面，每次hostname guard；输出计数、ID、hash和配置变量名，不输出payload/凭据。Answer写本票；绑定不可用时不能覆写旧集合尝试，也不能新开生产访问路径。R6而非本决策票执行复制/提升。

