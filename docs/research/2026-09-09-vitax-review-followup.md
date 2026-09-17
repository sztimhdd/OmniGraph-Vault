# VitaX 深化审查反馈裁决

[KNOWN] 实施顺序与组件默认已由后续讨论收敛，现以[ADR0004](../adr/0004-minimal-knowledge-product.md)和[当前计划](../superpowers/plans/2026-09-09-vitax-product-architecture.md)为准。本文保留研究证据，不再作为Prefect前置、提前退役图引擎或立即替换向量后端的依据。

2026-09-09。状态：设计审阅补充；未实现DDL、未运行模型/解析/向量实验、未改生产。

[KNOWN] 输入为本轮消息中的A+B反馈、B评审，以及附件 /Users/hai/.codex/attachments/3d078a80-3fd6-4970-84e5-3255b279d607/pasted-text.txt，SHA-256为 e69354036dac800961103688855b8ab7641904293f8331130edd9b6253332ae6。附件行动清单作为被审查资料，不作为执行迁移的指令。主控核验一手资料，一名只读reviewer复核DDL；其建议经主控再次裁剪，避免机械增加表。

[INFERRED / HIGH] 裁决：基线方向保持，采纳中文复杂PDF、适用的多轮增删、合并/分阶段语义任务三个补充；不直接采纳附件的DDL、原子切换命令、模型参数、性能承诺或自动换栈门槛。具体程度不等于正确程度。

## 1. 三项主要意见

### PDF：应测中文复杂版面，但不能按品牌定冠军

[KNOWN] OmniDocBench提供文本、表格、公式、阅读顺序等评测，包含MinerU与Docling；不同版本/后端差异必须分开。该基准与MinerU同属OpenDataLab生态，不能仅因有排行榜就称“完全独立验证”。[基准及版本](https://github.com/opendatalab/OmniDocBench)

[KNOWN] MinerU官方说明pipeline后端可纯CPU运行；Docling官方提供OCR及VLM等路径。不能将选择描述成“Docling=CPU、MinerU=GPU”。Docling代码MIT也不代表各模型权重共享同一许可。[MinerU运行后端](https://opendatalab.github.io/MinerU/quick_start/)、[Docling能力与许可边界](https://github.com/docling-project/docling/blob/main/README.md)

[INFERRED] 不采纳“MinerU中文无工具能匹敌”这一绝对结论。采纳在实验3中增加中文双栏、跨页表格、公式、扫描、图注对照；PC的实际资源条件作为成本约束。质量先过门，再在合格候选中选更简单者。最终默认解析器二选一，暂不增加按版式路由的双框架平台。

### sqlite-vec：风险真实，但反馈混淆版本、修复和执行路径

[KNOWN] 官方发布页把0.1.9标为Latest非预发布版本，0.1.10-alpha系列另列。0.1.9修复的是长文本元数据DELETE错误；0.1.10-alpha.1引入新ANN路径；alpha.2说明已修复DiskANN未清理压缩邻居向量的残留问题，并说明修复让DELETE较贵。不能把这段发布说明转述成“最新仍未修复残留”，也不能把alpha特定路径套到0.1.9 flat检索。[版本与修复记录](https://github.com/asg017/sqlite-vec/releases)

[INFERRED] “pre-v1”提示兼容风险，但不等于所有发行物都带alpha标签。首轮锁定非预发布版和flat路径，不引入ANN预发布特性。

[INFERRED] 每日从干净库构建公开release，主要执行插入，并不会因为文章下线而在旧向量索引中逐条DELETE。因此“大量版本变化恰好高频命中DiskANN删除路径”不适用于当前默认构建方式。

[INFERRED] 增删测试仍采纳，但分两种模式：

- 默认模式：同一内容集经历多轮新增、修订、下线，每轮建全新库，检查新release的FTS/向量/图片/证据一致且不含已下线项目。
- 增量候选模式：只在决定复用旧候选索引时，测多轮DELETE/更新/ID复用/长元数据、重开库和空间增长；不能把未采用路径的性能当默认发布阻断。

[INFERRED] 逻辑检索不到、文件字节无残留、Web不能访问旧release是三种不同保证。不得从DELETE成功或新库干净推断全部保证成立。

### 任务合并：接受比较，拒绝混合变量

[INFERRED] 上一版“不强制一次调用”没有否决任务合并。建议先交一个完整、边界清楚的知识任务；究竟一次还是多次内部调用，应测得而非由接口数量推定。

[INFERRED] 实验3增加两个假设：合并任务可能减少重复读原文；分阶段可能减少局部返工并提升字段质量。固定解析结果、模型、验收字段和预算，比较合并任务与分阶段任务，计入重试以及实际合格产物成本。不预设任何一方一定更省。

[KNOWN] Structured Outputs约束输出结构；Batch是异步处理与计费机制，均不能直接证明语义任务合并的质量收益。[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)、[Batch](https://developers.openai.com/api/docs/guides/batch)

[INFERRED] 本轮不将API Batch和Hermes订阅调用混在两个实验组中。若Hermes内部调用数不可观察，就报告“任务数已知、底层调用数未知”，不声称每篇一次调用或50%节省。

## 2. 附件中会直接导致实现偏差的参数

| 主张 | 裁决与最小修正 |
| --- | --- |
| bge-small-zh-v1.5是384维 | [KNOWN] 官方模型卡为512维；384是small-en等模型的维度。[中文模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5) |
| 所有BGE查询都必须加同一句中文前缀 | [KNOWN] BGE-M3官方说明不要求query instruction；按具体模型卡确定前缀，不以家族名统一。[BGE-M3模型卡](https://huggingface.co/BAAI/bge-m3) |
| PC与云必须完全同一ONNX文件 | [INFERRED] 同一文件是简单的锁定方法，不是唯一数学必要条件。必须保持兼容编码合同；若PC用另一推理运行时/精度，需要固定checkpoint和预处理，并通过数值/近邻结果验证，不因文件格式相同就判兼容 |
| 5万条向量约77MB内存 | [COMPUTED] 5万×512维×4字节=102,400,000字节，约97.66MiB，仅向量本体；不是进程RSS，尚不含模型、文本、索引与并发缓存 |
| 只读连接并发完全互不阻塞、微秒延迟 | [INFERRED] 只读避免写入争用，不消除CPU、磁盘、连接调度或向量计算成本，不能由mode=ro推导延迟保证 |
| cache_size=-64000分配64MB | [KNOWN] 这是建议的页缓存上限，单位KiB，按需增长，不是立即分配或全进程内存上限；连接配置还影响聚合内存。[SQLite缓存说明](https://www.sqlite.org/pragma.html#pragma_cache_size) |
| 5块×800字符确保4000 tokens | [INFERRED] 字符与token不能直接等同；还要计入来源标签、工具封装、指令及上下文。按实际模型tokenizer或保守硬上限执行，5/800只是待测默认值 |
| RRF版本号权重1.5/0.5保证精确命中 | [INFERRED] 权重是未校准超参数；精确ID/版本规则与融合排名分开测试，不写为事实 |
| sqlite失败就立即切Qdrant | [INFERRED] Qdrant也必须在相同资源与质量预算通过；不能只限制Qdrant为512MB却不限制SQLite，或把80/200ms写成已有业务SLA |
| Wiki达到图的85%覆盖且省60%就彻底删除图 | [INFERRED] 相对覆盖可能容许重要关系持续遗漏；需绝对证据质量底线和问题族分析，不能从整体比值决定删除。实验若发现查询时图遍历独有价值，也不能预先限定赢家只能离线生成Markdown |

## 3. DDL不能直接落地：最小合同修正

[KNOWN] 附件存在source_documents、document_revisions、document_blocks、knowledge_revisions、knowledge_claims和published_releases六组表。其中知识输入为单revision、claim证据为单block；release只存计数/hash/is_active，没有定义成员manifest格式。

以下为 [INFERRED / HIGH] 的工程修正，不是要求新增一整套事件平台：

1. **来源与抓取分开。** SourceDocument表达稳定来源身份；抓取时间、raw artifact、ETag/Last-Modified属于一次capture。重复抓取保留capture，解析修订绑定其输入。相同内容来自不同URL时保留不同来源身份，只复用内容artifact。现有DDL实际上允许相同hash多行，不能说它在SQL层禁止多来源；问题是来源、逻辑文档、capture三者语义尚未定义。
2. **知识支持多个输入。** 用knowledge_inputs关联多个DocumentRevision；Wiki可作为KnowledgeRevision的一种kind，不必为Wiki另造平行版本系统。补输出artifact、recipe/prompt版本、验证状态与替代关系；已验收输出不能仅凭配方重算。
3. **主张支持多条证据。** claim_evidence关联多个block，记录支持/反驳/背景角色。关系也指向证据。仅有quote_snippet与外键不证明引文属实，发布器须检查文本或图/表定位。图和表应使用适合其类型的locator，不能强迫每条图证据都伪装成文字引文。
4. **未知时间允许未知。** 事实有效期属于主张/关系，不能把整篇文章的created_at当事实生效时间；valid_from不可一律强制非空。模型精确snapshot或token用量没有实证时记录unknown/缺失状态，不能为满足NOT NULL编造。来源语言也不默认把未知填成中文。
5. **release成员只有一个权威。** manifest明确列出所发布的内容版本、资源、模型/分词配置与hash；不需要为了“规范”再强制加一套权威release_members表。需要SQL查询时可从manifest生成派生表。is_active不放进不可变release内容作为第二个切换权威；当前部署以单一外部指针为准。稳定release_id用于重试幂等，发布时间另记。
6. **撤回不等于事实过期。** 发布撤回有独立状态/理由，生成新公开投影；事实valid_until不承担访问控制。必须同时检查可访问的旧release、图片路径和受控缓存，防止旧URL继续公开。归档留在私有区，回滚不得重新上线已撤回内容。无需为此预建通用事件溯源框架。

[INFERRED] block_index在revision内唯一，block_id不可跨revision偷换；内容hash不是段落全局身份。本文保持上一版“文件保存内容、SQLite保存目录/状态”的权威划分，附件把cleaned_markdown直接当另一权威副本的写法不直接采用。公开库可存导出的正文/解读，作为该release只读投影。

[INFERRED] 这些合同用少量反例验证：同文双来源、同URL两次抓取、跨文章主张与反证、Wiki修订、发布后撤回。它们属于实验3中的数据验收，不新增第四项架构实验。

## 4. 发布与运行时纠正

[INFERRED] 不将ln -sfn视为跨平台原子替换保证。候选做法是在同目录创建临时指针，然后以一次rename/os.replace替换current；先完成资产和目录校验，必要的持久化同步在替换前后落实。[Python原子替换合同](https://docs.python.org/3/library/os.html#os.replace)

[INFERRED] 原子指针不等于端到端快照：请求开始时固定release_id并持有该版数据库；HTML引用带release版本的资源地址，后续API调用使用同版。旧连接不因软链接变化自动切到新库；旧版不得在请求仍使用时删除。不可只给每次连接传current路径，再宣称跨页面/图片/API一致。

[INFERRED] manifest的SHA-256是完整性摘要，不是发布者身份签名。使用已授权的认证传输、验证manifest和实际资产；不为了纠正术语就新增PKI。构建公开库从白名单字段/关联/资产生成，不是复制私有主库再DELETE几列。Cookie和Authorization不进入知识资产包；私有备份也不等于应重复归档凭据。

[KNOWN] Prefect支持SQLite轻量单实例，官方把Postgres作为生产/高可用/多服务部署的优先选择；不是“只有多worker才需要”的硬边界。[服务文档](https://docs.prefect.io/v3/concepts/server)

[INFERRED] 不用ephemeral状态证明重启后的持久性。候选实验若验证跨进程恢复，就使用明确持久目录和单一本地server。重试可以重新执行任务，不能保证自动修复CDP登录过期或额度不足；按故障类别交给已有Hermes/Codex/通知边界。不新增独立故障恢复实验，也不把“200行自写runner”假定为经过验证的廉价替代。

[INFERRED] BYOLLM的直接浏览器请求与服务端临时代理是不同路径。首版维持统一API内的请求级临时代理；不同时部署两条未经验证的密钥路径。只允许请求已发布证据；会话级累计预算不能仅靠单次limit=5替代。外部MCP客户端自行调用其模型。必要的provider出站校验、日志脱敏和服务身份隔离属于该应用，不另起网关平台。

[KNOWN] LightRAG未来不作公开服务，并不证明当前部署已经移除了暴露面。实验前核对所用版本包含修复；本轮没有检查/变更现网。

## 5. 实验收口与下一步

[INFERRED] 仍然只有三个实验：

1. 检索质量/容量/编码合同：纳入准确维度、同等资源预算、flat版本及适用的多轮增删；分别报告默认重建和增量路径。
2. Wiki与图的边际价值：维持相同证据/模型/预算，剔除85%/60%机械删除门槛；不预先禁止能回答问题的图实现参与公平比较。
3. 真实生产发布链：先在复杂中文PDF上二选一解析器，固定解析输出后比较语义任务合并方式，再验证跨文章证据、唯一release和独立服务。不是解析器×模型×编排器的全排列。

[INFERRED] 执行顺序保持一篇真实文章贯通优先：补最小对象合同与反例→固定输入→跑到真实预览→再扩大检索/图对照。不把本轮新增评审变成从schema到100篇伪数据的另一条迁移支线，不按附件最后的清单直接安装、建库或压测生产。
