# VitaX 三份外部研究报告：证据审查与统一方案

[KNOWN] 实施顺序与组件默认已由后续讨论收敛，现以[ADR0004](../adr/0004-minimal-knowledge-product.md)和[当前计划](../superpowers/plans/2026-09-09-vitax-product-architecture.md)为准。本文保留研究证据，不再作为Prefect前置、提前退役图引擎或立即替换向量后端的依据。

2026-09-09。状态：评审建议，尚未执行选型实验或变更生产。

[KNOWN] 后续反馈的事实核验与DDL裁决见 [深化审查补充](2026-09-09-vitax-review-followup.md)。本文实验1/3已纳入适用的增删、中文复杂PDF和语义任务合并对照；附件DDL没有直接成为工程规范。

[KNOWN] 本轮阅读三份附件、当前产品架构文档，并检查 KB-v2-site.zip 的 package.json 和前端入口。两名只读研究子代理分别核验检索组件与论文，主控核对关键来源、处理冲突并综合。没有安装、调用模型加工文章、SSH、部署、修改生产、提交或推送。

本文的 [KNOWN] 表示附件、源码或本轮一手来源可核查的事实；[COMPUTED] 表示计算；[INFERRED] 表示设计判断。事实核验置信度 HIGH；VitaX 的性能、质量、成本胜负在实验前为 UNKNOWN。

## 1. 输入与结论

| 编号 | 文件 | SHA-256 |
| --- | --- | --- |
| R1 | /Users/hai/Downloads/2026-09-09-vitax-A-B-research.md | 41f7939b87bd838ac5c1d2733ababa56d8ca993ee677290eb9639198329be53f |
| R2 | /Users/hai/.codex/attachments/e27e7b78-3d31-40f7-8f27-d603d97028e5/pasted-text.txt | f1f1f1bd9d07b135cb2607f244964f9f54a82c9a3a212d2b55d48f079743333d |
| R3 | /Users/hai/.codex/attachments/96d3dbe4-1be5-4b9c-8de1-c68eb27da0a3/pasted-text.txt | d89a4f2eedf8863ac757909d5b7eff519c05c4059d4816bd3f4b0cd62ba04491 |

[INFERRED / HIGH] 推荐“版本化内容资产 + PC 单一生产控制者 + 单云只读发布 + SQLite 优先检索 + 有界 BYOLLM”。图增强保留为实验对照；不把 LightRAG、Wiki、Qdrant、SQLite、Graphiti 的所有推荐串在一条生产链上。

[KNOWN] 三份报告均未直接审查完整项目源码/当前生产。R1 引入 Cognee、Apify、40万向量等背景；R2 从“可能2C/2G–4G”滑向“小云必然承受不住”；这些均不是本轮确认的部署事实。它们不能决定容量、删除范围或安全暴露状态。

[INFERRED] R1 的主要价值是来源适配、分层生产和图增强的条件性价值；R2 提供最具体的精简方案，但模型兼容、资源承诺和 Wiki 等价替代缺乏证据；R3 有比较意识，但多处只有资料名、没有精确链接，外推范围过大。按主张裁决，不给整篇报告投可信票。

## 2. 哪些共同结论有证据，哪些只是重复

| 共同方向 | 一手证据实际支持 | 可作出的决定 |
| --- | --- | --- |
| 词法、向量及融合可组合 | [KNOWN] SQLite FTS5 有 BM25；Qdrant 有 dense/sparse/fusion；scrydb 实现 SQLite 词法/向量融合 | [INFERRED] 建立词法基线、测语义增益；不能推出 hybrid 在每个数据集最佳 |
| 图对复杂关系问题可能有价值 | [KNOWN] RAGSearch 在多跳任务有明显收益，普通 QA 增益较小；其他图基准也显示任务差异 | [INFERRED] 图不作普通文章发布前置，也不提前永久删除 |
| 内容与引擎内部存储分离 | [KNOWN] FTS5 可对外部内容建索引；Docling 区分内容结构与来源位置 | [INFERRED] 保存版本化文章、证据和知识产物；引擎负责派生索引，不占有业务身份 |
| PC 生产、云独立服务 | [KNOWN] 这是用户明确的产品约束，并非三组研究独立发现 | [INFERRED] 一次发布完整公开读模型，在线请求不回连 PC |
| Wiki 离线生成，回答按需生成 | [KNOWN] 报告提出了该设计；所引论文未证明 Wiki 可普遍替代图检索 | [INFERRED] Wiki 是内容产品和检索语料，效果交实验裁决 |

来源：[FTS5](https://www.sqlite.org/fts5.html)、[Qdrant 混合查询](https://qdrant.tech/documentation/search/hybrid-queries/)、[scrydb 论文](https://arxiv.org/html/2608.24060)、[RAGSearch](https://arxiv.org/html/2604.09666)、[Docling 文档模型](https://docling-project.github.io/docling/concepts/docling_document/)。

[KNOWN] 来源依赖关系：

- R1/R2/R3 对 LightRAG 能力的描述主要回到同一上游仓库；它们是重复阅读，不是三次独立实现验证。
- R1 的 PYSEC、R2 的 CVE、OSV 与 GitHub Advisory 是同一漏洞的不同登记，不是两个独立安全发现。
- Qdrant 官方文档与 FastEmbed 官方资料由同一项目生态维护，可以证明能力存在，不能算两家独立生产性能验证。
- R2 的 SQLite 推荐与 R3 的 scrydb 引用都依赖 FTS5/sqlite-vec；scrydb 论文提供额外实验，但仍是该库作者评估，且没有在 VitaX 上复现。
- RAGSearch、scrydb、STaRK-Prime 论文是不同实验；它们的问题、语料、模型和度量不同，不能将“结论方向接近”累计为同口径多数票。
- R1 的浏览器“80%确定性/20%AI”反复出现，但所列主要是对比博客与 gist，没有共同口径的统计依据。

[INFERRED] 重复来源不等于错误；应计为一条能力证据。只有独立方法、数据与实测结果才能增加性能结论的置信度。

## 3. 事实冲突裁决

| 争议 | 本轮核验 | 对方案的影响 |
| --- | --- | --- |
| R1：PYSEC-2026-3475；R2：CVE-2026-61740 | [KNOWN] 二者互为别名，均关联 GHSA-f4vv-55c2-5789；与 CVE-2026-30762 是不同认证配置路径。OSV 标记修复于1.5.4，1.5.4 release 明列修复 PR3319；原仓库 advisory 仍显示旧的“Patched None” | 不按编号重复计数，不把陈旧 advisory 字段当仍无修复；实际暴露需核对版本、认证模式与网络边界，本轮未检查生产 |
| R1 GPT-6 具体规格 vs R3 未确认 | [KNOWN] 官方 Astra 页确认1,050,000上下文、Structured Outputs、标准价输入$10/输出$50每百万token、Batch/Flex为标准价50%；超过272K输入另有加价条件 | R1这些具体数值获证实；但 API Batch 和订阅 Agent 会话不同，不能把折扣套到 Hermes 路由 |
| R2 FastEmbed“6.x” | [KNOWN] PyPI当前最新发布为0.8.0；官方支持CPU、GPU与批量处理 | 版本错误；“不适合PC批量”与报告后文GPU批处理也自相矛盾 |
| R2 BGE-M3/Qwen 普遍内置支持 | [KNOWN] 本轮查阅的 Python dense 模型列表未列出这些模型；允许自定义ONNX模型不等于已提供开箱兼容 | 逐模型验证；不凭库名承诺换运行时后向量兼容 |
| R2 FTS5“配置jieba/正则分词即可” | [KNOWN] 内置tokenizer为unicode61/ascii/porter/trigram等，jieba不是内置选项；trigram全文查询少于3个Unicode字符不命中 | 中文两字词、标点版本号须验证；可预分词或扩展，但需计入依赖与查询一致性 |
| R1 LightRAG 与 community summaries | [KNOWN] Microsoft GraphRAG含社区报告；LightRAG主要采用实体/关系与向量的双层检索，不应按同一算法估算成本 | 分开比较，不把两者归为同一个“图成本” |
| R2 sqlite-vec成熟度与20万阈值 | [KNOWN] 当前稳定发布0.1.9，项目仍pre-v1；稳定路线以精确扫描为基线，没有普适20万条容量承诺 | 锁版本并实测；不直接采用alpha ANN替代方案 |
| R2/R3 GraphRAG贵5–15倍/10–40倍、500页$50–200/45分钟 | [KNOWN] 所给材料没有能复现这些通用比值的统一模型、分块、语料、价格与对照；RAGSearch附录有图方法各自成本，但不足以支持上述倍率 | 从预算中剔除这些数字；分别记录建库、增量、查询及实际支付口径 |
| R2 Qdrant150–500MB、FastEmbed10–30ms、全栈低于180/200MB | [KNOWN] 未提供对应模型、精度、硬件、缓存与并发的测量记录 | 不能用来排除Qdrant或保证SQLite |
| R2 Kuzu轻量备选 | [KNOWN] Graphiti明确标为deprecated、上游不再维护 | 不进入新方案候选 |

关键来源：[OSV别名与修复范围](https://osv.dev/vulnerability/PYSEC-2026-3475)、[原始安全公告](https://github.com/HKUDS/LightRAG/security/advisories/GHSA-f4vv-55c2-5789)、[1.5.4发布](https://github.com/HKUDS/LightRAG/releases/tag/v1.5.4)、[Astra官方规格](https://developers.openai.com/api/docs/models/gpt-6-astra)、[FastEmbed PyPI](https://pypi.org/project/fastembed/)、[模型源码](https://github.com/qdrant/fastembed/blob/main/fastembed/text/onnx_embedding.py)、[FTS5 tokenizer](https://www.sqlite.org/fts5.html#tokenizers)、[LightRAG](https://github.com/HKUDS/LightRAG)、[sqlite-vec releases](https://github.com/asg017/sqlite-vec/releases)、[Graphiti](https://github.com/getzep/graphiti)。

[COMPUTED] 仅作量级示例：40,000个1024维float32向量本体为163,840,000字节，即156.25MiB，还不含文本、模型、索引和进程。它不是RSS下界，因为可用磁盘映射/分页；同样也不能据此承诺整套服务180MB。

[KNOWN] R1的“40万向量”、R2的主机规格未在本轮验证。R1“搜狗2023后失效”“CDP唯一/最主流”“MinerU中文无可匹敌”和44%浏览器提速，缺少可迁移到本项目的一手条件与复现材料，本轮不纳入选型依据；保留既有登录浏览器适配器不依赖这些泛化主张。

### 论文究竟证明了什么

- [KNOWN] RAGSearch（2604.09666）比较六个Wikipedia QA数据集。R1引用的+0.47/+27.23确实见于论文，但属于单次推理条件，不是GPT-6或VitaX测试。它支持“多跳不能提前放弃图”的少数派意见。[论文](https://arxiv.org/html/2604.09666)
- [KNOWN] scrydb（2608.24060）基于FTS5与sqlite-vec，评估8个BEIR数据集；部分数据集纯语义优于RRF hybrid。它支持轻量实现可行性，不证明中文专有词效果、公开并发或180MB预算。[论文](https://arxiv.org/html/2608.24060)
- [KNOWN] 2606.25656使用单一STaRK-Prime精密医学数据集和预定义KG，其上下文优化结果不等于自动从技术文章抽图的收益。[论文](https://arxiv.org/html/2606.25656)
- [KNOWN] “GraphRAG-Bench”至少指向两项不同工作：小说/医学任务的比较，以及20本计算机教材的领域推理基准。R3不提供精确标识，不能据此追认成本数字。[第一项](https://arxiv.org/abs/2506.05690)、[第二项](https://arxiv.org/abs/2506.02404)

## 4. 接口冲突与重复基础设施

以下裁决均为 [INFERRED / HIGH]，除注明的一手能力外，不声称已在生产验证。

1. **权威源冲突。** R1“原始资料+配方唯一权威”、R2“Markdown唯一权威”又称“SQLite主表”、R3“Wiki可重建”混在一起会产生三个主库。改为：不可变文件保存内容版本；SQLite目录保存身份、版本选择与发布状态。字段只由一个位置主写。原始快照、标准文章、验收后的解读/翻译/Wiki及人工修订都保留；配方用于溯源，重跑产生新知识版本，不承诺生成结果相同。
2. **向量空间冲突。** PC的文档编码与云的query编码必须来自同一兼容模型配置，锁模型revision、tokenizer、query/document前缀、pooling、归一化、维度。不能将BGE-M3文档向量与小型BGE查询向量混用；维度相等也不够。切模型则重建该release的语义索引。
3. **分词与排名冲突。** FTS5、Qdrant payload全文过滤、Qdrant稀疏BM25不是同一个调用接口。RRF不会保证精确版本号一定排第一；精确ID/版本的过滤或提权属于单独业务规则。当前Qdrant文档还明确某些BM25 tokenizer选项不受FastEmbed支持。[Qdrant全文文档](https://qdrant.tech/documentation/search/text-search/full-text-search/)
4. **发布与备份冲突。** Litestream恢复、rsync传文件、SQL dump不是等价发布协议。禁止复制写入中的主库当release；PC先构建并关闭公开库，传不可变包并验hash/完整性，再原子提升。SQLite在线备份API提供一致快照，但不自动完成静态页、图片与模型manifest的整体发布。[备份API](https://www.sqlite.org/backup.html)
5. **公开边界冲突。** 只按visibility筛文章行仍可能携带私有字段、关联表和图片。另建公开投影，列/关系/资产均使用白名单。Cookie、Authorization及Agent日志不成为文章资产。私有备份可留云端，但公开进程无读取权限。
6. **知识图谱语义冲突。** wikilinks是页面链接，不能等同带类型、证据、有效期的事实关系。保留claim/relation及证据定位；初期关系表服务有限邻接查询，复杂图推理需实验，不自行实现通用图引擎。
7. **重复检索与数据库。** SQLite+Qdrant并非天然重复：一个可作内容目录，一个作向量索引。真正的重复是两套权威内容、两套向量索引、两套独立词法排名。推荐架构只部署一套公开向量后端；Postgres+pgvector若无既有Postgres，仍新增数据库服务，不能记为“零服务”。
8. **重复控制者。** Prefect管业务批次时，Hermes cron不再同时调度文章；Hermes负责语义/修复，Codex接升级问题。不要再加LangGraph、Temporal、Celery、Redis来共同管理相同状态。
9. **BYOLLM边界。** MCP是工具接口，不是密钥托管方案。网站BYOLLM通过同一API服务的有界请求调用用户选定provider，key只在请求内存存在；不进日志、URL、数据库或任务队列，不回退站点key。外部MCP客户端自行管理自己的模型。对外provider目标需校验，不能成为任意内网代理。
10. **真实站点接口缺口。** ZIP的package.json是React/Vite/Tailwind，App导入MOCK_ARTICLES/MOCK_WIKI_ENTRIES；这些报告没有验收其数据接线。保留界面资产，接统一公开API和release数据，不保留mock成功兜底，也不为它另设Express/Gemini后端。

## 5. 值得保留的少数派意见

- [INFERRED] **R1：保留来源专用CDP能力。** 用户的登录环境是可复用资产；网页解析器或云浏览器不自动替代会话与来源枚举。
- [INFERRED] **R1：图在多跳上可能不可替代。** 本轮论文依据比“强模型让图过时”更扎实；保留图实验，但普通检索先行。
- [INFERRED] **R2：离线Wiki是值得优先投资的产品。** 一次生产可供多次阅读/检索；保留这一方向，同时拒绝“Wiki链接等于KG”的等价替换。
- [INFERRED] **R2：SQLite单文件公开读模型。** 对PC批量生产、单云只读发布确实简化release和回滚；不接受附带的未经测量的内存承诺。
- [INFERRED] **R2：静态搜索可作为特定产品形态。** 若将来只有静态浏览，Pagefind值得重评；当前已有MCP/BYOLLM统一服务，另加它会出现第二套检索语义，因此本版不引入。
- [INFERRED] **不把“最新”当赢家。** Qwen等新embedding不能仅凭榜单触发全库重算；兼容、中文证据召回和云query成本需一起胜出。

## 6. 推荐的一套技术方案

[INFERRED / MED] 这是单一推荐基线，需通过下节准入实验。先选清晰的数据与部署合同，再决定是否需要更重引擎。没有实验结果时不宣称SQLite或Wiki已胜出，也不删除旧库。

数据流：

Hermes PC：来源适配 → 原始资料归档 → 标准文章revision → Hermes/GPT-6知识包 → Wiki/关系版本 → 公开投影 → 完整release

单台阿里云：静态站点 + 单个VitaX API/MCP服务 → 只读公开SQLite及该release图片；另设不可被公开进程读取的私有备份区；vitaclaw-site独立部署边界保持。

### 内容、生产和服务合同

[INFERRED] 沿用产品层四个对象：SourceDocument、DocumentRevision、KnowledgeRevision、PublishedRelease。一个doc_id对应多次修订；内容相同可复用artifact，不能因内容hash相同而丢掉不同来源。每条主张/关系/图片caption指向原文revision和段落/页码/图片位置。时间分清来源发布时间、抓取时间、事实有效期和站点发布时间。

[INFERRED] Prefect作为PC单一批次编排候选；Hermes/GPT-6接有界知识任务，一篇可以多次内部调用。确定性程序处理提取、hash、去重、schema与发布验证；模型判断解读、选图、关系、Wiki更新。保持现有模型路线，不新增付费fallback，不把所有加工强塞“一次LLM调用”。每次保存实际输出与用量。

[INFERRED] 公开检索基线为SQLite FTS5；语义增强候选为sqlite-vec+FastEmbed，实验1后才定模型和发布依赖。入库与query使用同一编码合同；云端query本地完成。匿名关键词查询无需生成模型；返回原文证据摘录/已发布解读，不把FTS宣称为自由生成回答。

[INFERRED] BYOLLM Agent只能使用search、read_evidence、related等有限工具；网站与MCP共用实现、visibility规则和release_id。工具调用、候选条数、上下文和超时有界。IP限流保护服务器，不能替代生成预算；站点不为访客生成垫付额度。API key输入临时使用，不保存。

[INFERRED] Wiki是可浏览内容，进入普通检索；类型化关系先存SQLite，提供有界邻接和证据展示。LightRAG仅参加图增强对照，不作为默认服务、不承担文章存在性。如果实验2证明它有不可替代增益，再只引入这一图实现，仍从同一内容资产派生并绑定release。

[INFERRED] 08:00 Asia/Shanghai提升最近已通过验收的release；失败保留前一版并显示最后内容发布时间。构建新公开SQLite、静态页、图片和manifest后整体发布，禁止从私有活库直接服务。私有备份与公开发布分开，恢复时验证artifact哈希、目录关系和引用。

### 每项依赖具体替代什么

以下均为 [INFERRED] 的采用/拒绝决策，节省项是待验证的工程收益，不是测得成本。

| 组件 | 处置 | 替代与节省 | 新增负担/准入条件 |
| --- | --- | --- | --- |
| Python + FastAPI + MCP SDK | 统一后端，复用现有基础 | 合并网站查询与MCP业务逻辑；不另起LightRAG公开API或Express应用 | 一个VitaX应用服务；HTTP/MCP只是两种传输 |
| SQLite + FTS5 | 内容目录及公开读库 | 避免为元数据另设Postgres；事务内管理公开关系与词法索引 | FTS5分词合同与SQL迁移仍需维护 |
| sqlite-vec | 语义后端首个候选 | 通过实验后替代公开Qdrant服务及跨库向量release同步 | 增加一个扩展；pre-v1版本固定，容量与删除测试通过才准入 |
| FastEmbed / ONNX | 语义查询候选 | 替代云端完整PyTorch推理或回连PC的embedding服务 | 仍有模型文件、RSS和计算成本；逐模型验证，非任意BGE/Qwen开箱支持 |
| Prefect单PC自托管 | 保留为唯一编排候选 | 替代分散业务cron、脚本内调度/重试与各自运行历史，避免自写通用工作流引擎 | 增加PC服务和运行数据库；实验3检验实际收益。它不替代文章catalog或release合同 |
| Trafilatura | 普通HTML提取候选 | 替代重复DOM正文抽取和不必要的LLM去导航工作 | 只替换可证明正文/图/表不丢失的提取路径 |
| 现有CDP来源适配 | 复用 | 保留登录会话与站点枚举；不额外部署Browser-use/Stagehand/Crawl4AI全套 | 来源改版后局部修复；若未来引入Crawl4AI必须明确退役哪个适配器 |
| Docling / MinerU | PDF解析器二选一，Docling为起始候选 | 替代多套PDF/OCR/表格抽取胶水；最终只保留胜出实现 | 实验3增加中文复杂版面对照；质量先过门，再比较PC资源成本，标准HTML无需经过它 |
| ZIP中React/Vite/Tailwind | 复用UI，构建时生成内容页 | 替代旧站点展示层；不新增Next.js/Astro或常驻Node服务 | mock→真实数据、路由/SEO仍需实现；React内建预渲染接口可用，需用release数据验证 |
| 现有反向代理/服务管理 | 复用 | TLS、静态资源及进程管理不再引入一套网关/容器平台 | 不把私有备份挂给Web用户 |

能力来源：[Prefect自托管与状态](https://docs.prefect.io/v3/concepts/server)、[Trafilatura](https://github.com/adbar/trafilatura)、[Docling](https://docling-project.github.io/docling/concepts/docling_document/)、[React预渲染说明](https://react.dev/reference/react-dom/server/renderToString#alternatives)。

[INFERRED] 若容量实验证明sqlite-vec不够，Qdrant只替代向量后端，不与sqlite-vec长期双跑；SQLite仍是内容目录和免费FTS，首轮不同时重写词法路径。如果以后统一到Qdrant BM25，必须明确退役原FTS排名实现，不能叠加第三路词法服务。

[INFERRED] 本版不引入：Postgres/pgvector、Graphiti/Kuzu/Neo4j、RAGFlow、Cognee、LlamaIndex/LangChain、LangGraph、Temporal、Celery/Redis、Pagefind/scrydb包装层、实时数据库复制服务。它们尚未证明替代了本方案中足够多的工作；不等于这些项目没有价值。

[INFERRED] 与上一版计划相比，收敛点是：公开检索实验优先SQLite，Qdrant改作容量对照；Crawl4AI不预先增加；图、模型运行时与Wiki质量均需实测；Prefect仍是编排候选而非已验收组件。本文不改写现有执行计划或发布配置。

## 7. 仅三个决定性实验

[INFERRED] 以下是预注册的实验设计，不是已经执行。共享一份版本化真实样本和参考证据，不搭通用benchmark平台。12篇可以先发现工程错误；涉及选型再扩大到50–100篇、约60问；规模阈值是采样方案而非统计充分性证明。问题分层用于找失效类型，不能用人为一半多跳来推断真实访客多跳占比。

### 实验1：公开检索的质量、容量与embedding合同

- 决定：SQLite是否够用，语义检索是否值得加入，哪个云端编码配置可行。
- 同一公开语料、chunk、模型、精度、过滤、硬件和并发，比较FTS基线、SQLite词法+sqlite-vec、相同词法+Qdrant向量；先固定embedding比较引擎，再只对胜出基线测当前BGE方案与一个可用的小型多语言ONNX候选，避免全排列。不得一组本地embedding、一组外部API后归因数据库。
- 覆盖中文两字词、中英互查、缩写、版本号、表格、无答案；分别记录Recall@10、nDCG@10、MRR@10及引用定位。MRR是首个相关结果倒数排名均值，不是Top-k准确率或召回率。
- 使用真实公开库规模及合理增长副本压测；容量数据可扩展，但不得用重复文档制造质量集。计量embedding、数据库和端到端P95/RSS，包含冷启动、模型加载、同机其他站点资源及发布时磁盘需求。
- 固定稳定版flat检索作为sqlite-vec基线，不混入alpha DiskANN。用同一组多轮内容变更，分别验证“干净库重建release”和“若采用增量构建时的插入/更新/删除”；检查旧记录不可检索、长元数据、ID复用、重开库、结果/空间/耗时。逻辑删除、物理残留和旧release撤回是不同指标。仅在实际启用增量索引时把DELETE性能作为容量门槛。
- 裁决：先在跑分前依据目标云机可用资源固定预算。SQLite满足预算且质量不劣时选SQLite；资源失败且Qdrant改善则只替换向量层。轻量模型若跨语言/专名显著退化，不通过压小模型偷换质量目标。两者皆失败就记录未决，不能自动再加USearch、第三模型服务或付费API。
- 输出：一张质量/资源表、锁定的model/tokenizer/precision manifest、唯一采用的后端；不得引用报告中的120ms/180MB作为已达成指标。

### 实验2：Wiki与图增强的独立边际价值

- 决定：要不要引入LightRAG，以及图解决的究竟是哪类问题。
- 在同一底层证据检索上比较：A文章证据；B文章+预编译Wiki/类型关系；C在B上增加LightRAG图增强。必要时加“文章+图”的消融行，仍属于同一个实验，不引入第三图框架。
- 固定回答模型、检索调用上限和上下文预算，分别跑直接回答与有界Agent策略。Wiki生成不得看到留出问题；新旧版本、来源冲突、多跳和负例必须存在。参考答案先由原文证据定义，审阅者不知道候选标签。
- 记录正确且有证据支持的答案比例、关键关系遗漏、错误引用；成本包括Wiki/图首次构建、一次增量更新、一次撤回重建、在线token与延迟。API美元和订阅实际付款/额度占用分开列，不用名义API价冒充现金支出。
- 裁决：默认B。只有C对关键问题族产生可复现、不能由补齐检索/证据解释的质量收益，且在预定日更/查询预算内，才引入图；不以“图节点更多”或未经论证的统一15%门槛决胜。效果接近或样本不足时保留更简单B，记录不确定性。

### 实验3：一批真实文章贯通生产与独立发布

- 决定：推荐的解析器、Hermes任务边界、Prefect与发布合同能否共同交付产品，而不是各库分别能启动。
- 同一批真实中英HTML/CDP/PDF、图片和版本更新，完成原始归档→结构化知识包→Wiki→公开库→ZIP界面。选图按价值，保留出处caption。只设置一次中断/重复触发，检查已验收内容复用及唯一release，不扩大为通用恢复项目。
- PDF子对照固定中文双栏、跨页表格、公式、扫描与图注样本，对比具体版本/后端/模型的Docling和MinerU。先看关键数字、阅读顺序、表格、证据定位与图片配对是否正确，再看CPU/GPU和处理成本；不以框架品牌或CPU标签定胜负。
- 解析结果固定后，对照“一个合并语义任务”和“分阶段语义任务”，保持同模型、同来源与同验收合同；记录实际调用次数、重试、字段质量、引用和每篇合格产物用量。一个Hermes任务可能含多次模型调用，不能标成一次。Batch API是另一条计费/调度维度，不与任务合并混为一个变量，本轮沿既有订阅路线设计。
- 注入一个不合格产物和一个私有测试标记，验证拒绝发布/无越界；隔离候选云服务的PC网络后验证页面、免费FTS、语义查询及BYOLLM工具可独立运行。BYOLLM真实provider请求在后续获授权的验证范围执行；本轮不付费调用。
- 看可读性、证据定位、关键图/表完整性、字段有效性、已付模型成本/额度、人工介入次数；验收一次增量更新及前版继续可读。发布结果要能指向实际文章，不能仅用schema通过或HTTP200。
- 裁决：出现私有泄露、来源丢失、混合release即拒绝；任一新增组件若增加依赖却没有取代旧工作，移出首版。采集质量失败先定位来源/解析器，不靠更换全部架构补救。通过后才进入分批旧数据导入与单云切换。

## 8. 审查边界

[KNOWN] 当前所得是可追溯的报告裁决和统一设计，不是新pipeline健康证明。安全公告已确认存在，但没有据此声称现网遭入侵或一定暴露。云机资源、实际公开语料量、现有安装版本、Hermes无人值守吞吐与选型胜负仍需对应实验或新鲜检查。

[INFERRED] 下一步应优先让实验3的一篇真实文章纵向贯通，并并行准备实验1的固定证据集；同一批内容复用到实验2。研究在这三个选择点收口，避免继续扩展候选清单。
