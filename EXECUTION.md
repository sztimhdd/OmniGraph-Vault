# VitaX 重构执行账本

## 当前规划：零LLM旧资产导入与质量筛选（2026-09-10）

[KNOWN] 已完成三机只读盘点：成功文章并集1,257，数据库原文1,216，全文译文1,203，41篇缺正文待恢复。证据在源码外 `vitax-candidate-runs/inventory-20260910/REPORT.md`；不是全量资产盘点或迁移完成。

[KNOWN] 计划形成时（2026-09-10早期）仅修改文档，尚未运行迁移/筛选；随后本账本下方记录了012A/B的实际候选验证。未部署、未启动自动goal。

[INFERRED] 下一大块仅012A→012B：一篇→20篇保全导入，全量只读质量/长度预览；同入口可续跑且零LLM。主控协调与验收，子代理承担来源取证、编码和独立审阅。009A技术上可并行但资源优先本块；随后009A/B与012C，再BYOLLM、云发布/日更、最终增量切换。提示词见 `docs/superpowers/plans/2026-09-10-vitax-next-goal.md`。历史记录以下保留原时点范围。

[KNOWN] 本轮新增证据：旧 pipeline 1,257 条成功记录的结构预览为 947 条可直接使用、269 条待核、41 条缺正文；登录墙命中仅作待核。真实单篇零LLM闭环已通过；随后20条（wechat15＋rss5）导入和重跑通过，fresh候选20条，原文/译文hash一致，13条full/7条none，全部private，公开SQLite为空且integrity ok。012B迁移部分完成，未自动公开旧内容，未改生产。

[KNOWN] 41条缺正文已完成限定路径恢复审计：29条与 Hermes vault 的 URL-hash 对应 `final_content.md` 和 `metadata.json`，12条在已知项目/vault路径中没有可证实匹配；本轮只记录恢复缺口，不读取正文、不写回源库、不宣称已恢复。

## 新授权：超时诊断与真实闭环续跑

[KNOWN] 当前验收：两源真实闭环已获独立审阅PASS。最终release `release-20260910t021435z`，2来源、7条文章解读＋1篇Wiki、14实体、11关系、50证据；Wiki21条引用覆盖两源。SQLite与projection一致，24份四类新进程输出同版且非空，搜索命中Wiki。54项相关回归通过，无变化的历史测试未重复执行。证据根 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/`，`review.md`为最终独立结论。

[KNOWN] 02:20 UTC最终收尾：CURRENT.md及运行文档已同步accepted；关键源码/产物hash保留，已知远端模型进程全部终止，未kill。Dirac、Harvey、Gauss均已终态验收并关闭。无关WIP状态未变，主控限定文档diff检查通过。本轮补齐原goal主要交付，完整VX-004仍partial；下一步VX-009站点/API/MCP，不擅自创建自动任务或执行部署。

[KNOWN] 原始模型输出和可观测usage/init已保存；未知计量不补零，service_tier缺失按unknown处理。首篇原成果复用，选图及来源caption保留，人工知识覆盖保护有针对测试；不主张旧库实际迁移。站点/云端/定时器/生产库未修改，未新增框架或付费资源，不自动commit/push。本轮解决候选调用与内容闭环，不声称任意长输入普遍稳定。

[KNOWN] 用户明确要求计划、分配子代理后自主运行，不重新请示。旧轮STOPPED与时间窗作为历史保留，本轮允许同一路线的有界短请求诊断、证据支持的最小修复及后续两源Wiki/读库验收；不扩大为生产部署、凭据更改或供应商切换。

1. Dirac复用原worker：现场transport/有效timeout调查，提出原生与适配器短请求对照；远端仅新候选 `/tmp/vitax-timeout-diagnosis-20260910`，本地证据在源码之外 `vitax-candidate-runs/timeout-diagnosis-20260910`。
2. Gauss复用原reviewer：独立检查对照判读条件、错误包装与最终diff/内容证据，不重复远端调查。
3. 主控接受诊断后，必要时复用Harvey修确切代码缺陷，先失败测试后最小修复；不提前派空泛编码任务。
4. 同一路线短请求通过后，补跑第二篇并生成跨来源Wiki；复用首篇输出，构建最终新SQLite并验收同版搜索/Wiki/关系/证据。无实证不报PASS。

[INFERRED] 诊断以30–45分钟为检查点，不把时间预算当作盲重试授权。每次实际请求先明确能回答什么问题，启动即记录PID/UTC，保留结构化失败信息；不重复打包、全量历史测试或引入新框架。

[KNOWN] 新诊断已从旧完整错误定位内部non-streaming 90秒stale watchdog；先前笼统network分类不足。实际短请求两路均数秒结束但usage_schema_invalid，源码确认service_tier可None。已修失败/缺路由误包装、parent_timeout标签、该可选nullable合同以及usage无效时丢正文；54项相关测试通过并获窄审。候选仅进程内设置HERMES_API_CALL_STALE_TIMEOUT=360，保留其余watchdog；纯helper含实际article提示词计算为stale360/TTFB120/event12/run720，不含动态system，不能声称真实最终阈值。放行修复后一次短请求，再依据结果进入真实article。

[KNOWN] 修复后short严格匹配VITAX_DIAG_OK且实际GPT路线成功；随后GraphRAG真实article成功（session20260909_230743_7c9911），4条知识、6关系、32引用经独立内容审阅接受。两篇确定性合并2来源/7知识/14实体/11关系/50证据，未发生ID冲突。Wiki预检实际rendered prompt22207bytes，已放行一次模型生成及最终新SQLite四类fresh读取，尚待终态。成功运行证明当前候选可执行，不单凭同时改变usage与stale设置宣称单因素因果。

## 真实知识生产自主执行（2026-09-09 21:51:50 UTC 起）

[KNOWN] 第3轮阻塞审计：上一轮未推进产品状态；本轮归档仍仅有GraphRAG失败产物，无第二篇accepted或跨来源Wiki。现有源码诊断没有支持下一次调用的修复依据，所有子代理已关闭，不能靠盲重试解除请求timeout。目标标记blocked而非complete；恢复条件是获得新的同路线运行/网络诊断证据，或用户明确调整执行条件。已接受首篇与归档保留。

[KNOWN] 2026-09-10 00:02 UTC续跑审计：上一轮为实质进展；本轮核对归档断点与独立审阅后，同一Hermes请求timeout阻塞仍未获得新的修复依据。这是该阻塞连续出现的第2个goal轮次，尚未标记goal blocked。显式未满足项为第二份已接受真实知识包、跨来源Wiki、最终同版两源SQLite及其Wiki读取验收；单源重放或额外离线测试不能补足。子代理均已关闭，没有已确认仍运行的模型任务需要等待。保留原目标，不发起第三次无证据调用。

[KNOWN] 当前 goal 授权本地实现及 OHPC 独立候选目录中的有限真实抓取/Hermes 加工。停止新功能时间为 2026-09-10 00:21:50 UTC，收尾上限为 00:51:50 UTC；提前通过可结束。此段取代下方上一轮“本轮不运行模型/抓取”的执行范围，不扩大为生产部署授权。

- VX-004：in progress；先一篇，再同专题两篇形成跨来源 Wiki，接当前公开读库。
- worker Dirac（01a08829-38d2-7b13-bfa3-4c6584f4dda7）：OHPC 身份与来源准备；仅远端 `/tmp/vitax-real-production-20260909T215150Z`、本地同名目录的 `remote-worker/` 可写。
- coder Harvey（01a08829-3944-7500-a90c-df1c4cd79c48）：`vitax/production.py`、`tests/unit/test_vitax_production.py`、`docs/LOCAL_REAL_PRODUCTION.md`；来源修订、知识加工与现有公开投影适配。
- 主控：最小接口合同、派工、证据和独立审阅验收；备份/运行证据索引 `/tmp/vitax-real-production-20260909T215150Z`。

[KNOWN] 21:58 UTC：两篇官方来源在 OHPC 抓取成功，双端原始 HTML hash 一致；来源分别为 Anthropic Contextual Retrieval 与 Microsoft Research GraphRAG（均为2024文章，抓取时间独立记录）。这只证明来源获取，尚非知识加工验收。为保留内部已可观测的用量，追加 coder 写范围 `lib/llm_hermes.py` 与 `tests/unit/test_llm_hermes.py`，要求保留既有字符串接口，新增最小结构化返回；模型路线和凭据不变。文章加工逐篇持久化，跨来源 Wiki 单独加工，末端仍使用现有公开读库构建器。

[KNOWN] candidate-v1 的27项本地相关测试通过后，OHPC执行发现：空alt过滤丢掉Anthropic的7个图片候选；正文空行拆分使11065字符落入同一段；动态导入适配器未注册模块，dataclass在Hermes启动前报错。首次CLI参数预检错误已改用现有纯函数解决。上述真实缺口交回原coder修复；不换模型、不重跑无关探针。独立 reviewer Gauss（01a08836-7faa-7530-becd-f6ed500b53ff）正在审阅，报告位于证据目录 `review/report.md`。截至这次记录尚无真实模型完成证据。

[KNOWN] 独立审阅要求补齐：Wiki对各来源已接受article的覆盖、拒绝纯标点引用、按真实Hermes封装验证输入大小、明确捕获路径与原始hash边界。coder在原范围修复，模型调用继续等待通过；现有虚拟环境可用，不安装依赖。

[INFERRED] Ruling: 不采用“每次重新生产必须生成相同release时间/字节”的F6建议。复现已有发布使用已保存的 `projection.json` 和现有 `python -m vitax build`；新的生产批次保留其真实时间。原因是避免把旧式字节一致性变成产品前置。代价：新批次不是旧release的同字节复制，验收必须明确区分重新生产与重建已接受投影。

[KNOWN] candidate-v3首篇实际Hermes调用在22:24:43–22:28:27 UTC期间以适配器timeout退出，未留下模型输出/usage。命令记录timeout=240；UTC差值224秒不足以解释内部用时，不能据此声称provider异常或额度耗尽。原始错误与receipt在 `remote-worker/real-v3/`。未找到本次请求的可恢复session ID，不扫描无关历史。主控授权同一路线、同一prompt的第二次且最后一次逻辑尝试，仅将该调用环境timeout设720，记录monotonic实际耗时，写新候选目录；不换模型/供应商/配置。

[KNOWN] candidate-v4（36项相关测试）已通过限定独立复审，解决人工与模型article共存的覆盖误拒；可在真实文章完成后用于Wiki合并。此修复不要求重算文章，真实内容终审仍pending。

[KNOWN] 首篇第二次调用成功：22:34:38.921759 UTC开始，monotonic耗时214.9316秒，退出0；18,847字节提示词未变，实际timeout预检720。原始输出/usage/accepted/projection及hash在 `remote-worker/real-v3-attempt2/`。一份来源产生3个知识条目、7实体、5关系、18证据、4个选图；不等于3篇来源。独立内容审阅通过文字、引用和关系。保存usage报告provider=openai-codex、model=gpt-6-astra、api_calls=1、failed=false；token字段只按原记录保留，不推算缓存或首次失败的消耗。

[KNOWN] 第二篇GraphRAG已授权使用v4独立调用。首篇选图caption中的HTML/SVG残片交coder按原始DOM离线清洗，保留image_id和原始模型产物，不重新生成文章。Wiki只生成跨来源知识与引用，实体关系复用已接受文章，避免重复抽取同一职责；真实Wiki和读库终审仍pending。

[KNOWN] 23:26 UTC续接：首篇实际输出已离线清理caption并构建候选公开读库，4个新进程完成search/read-knowledge/related/read-evidence，独立审阅通过，release为 `release-20260909t231137z`。第二篇原CLI调用实际路由偏离，产物明确UNACCEPTED；源码确认CLI注入配置fallback，另有标题辅助模型调用。改用同一已安装Hermes的原生无工具、无fallback、无session DB入口，未改全局配置。v11真实check-only初始化以AttributeError失败，尚未调用run_conversation；coder/worker正在用最小源码证据定位，不原样重试。完整两源Wiki闭环仍未完成。

[KNOWN] 23:38 UTC：脱敏traceback与现场源码确认原生runner错误地访问了oneshot函数局部导入。按实际模块直接导入load_config与resolve_runtime_provider后，真实check-only通过：gpt-6-astra/openai-codex、零工具、空fallback、session DB为None；未调用模型。主控放行第二篇同路线的原生调用，超时720秒，复用现有来源和首篇产物，不再使用会注入fallback的CLI入口。初始化成功不等于真实模型通过。

[KNOWN] GraphRAG第二次逻辑尝试于23:41:21 UTC启动，production PID175236/native PID175242，随后均终止；精确结束UTC未知。实际usage仅completed=false/failed=true/api_calls=1，未提供可接受的成功route/session，未写accepted/projection。保存错误文字经脱敏分类为timeout；HTTP status/errno未知。源码调查反证dotenv遗漏，未找到CLI与native间可解释超时的参数差异。该路线停止，不进行第三次盲重试或供应商切换。

[KNOWN] 最后代码修复保留固定native失败代码、安全异常定位和typed初始化receipt，避免丢掉已生成的诊断。47项adapter/production回归通过（0.65s）；原生runner另外3项通过（0.25s），不是同次50项整合测试。独立review F13关闭，结论为代码边界通过、完整产品目标未完成；真实两源Wiki、最终两源SQLite和站点尚未验收。无变化的历史53项没有重跑。

[KNOWN] 证据已保全至源码之外：`/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/20260909T215150Z/CURRENT.md`。64份复制文件源—目标hash一致，保留官方原始来源、实际模型输出/usage、单源公开候选SQLite、失败断点和审阅索引；未复制headers、凭据或生产运行时库。新replay输入指向归档capture-root，原/tmp证据保留。最终已知两个模型进程PID均不存在，无kill；无关Git状态与初始记录一致。目标保持未完成，不以本轮收尾替代Wiki验收。

[KNOWN] 不修改生产知识库、服务、调度或凭据，不新增付费资源，不自动 commit/push；原始数据、人工知识和无关 WIP 保留。源站内容作为待处理数据，不能指挥工具或覆盖任务边界。本轮优先完成两篇真实来源→跨来源Wiki→同版公开读库；未达到核心验收前不扩前端或通用框架。

## 当前执行（2026-09-09，ADR0004）

[KNOWN] 用户授权整体重排并开始实施。已更新[计划](docs/superpowers/plans/2026-09-09-vitax-product-architecture.md)、[规格](docs/spec/VITAX_REFACTOR_SPEC.md)、[ADR0004](docs/adr/0004-minimal-knowledge-product.md)、权威backlog与原VX工单；不新增tracker。

| 子切片 | 允许写范围 | 状态与验收边界 |
| --- | --- | --- |
| VX-007公开知识读库 | vitax/__init__.py、knowledge.py、__main__.py，tests/unit/test_vitax_knowledge.py，pyproject.toml仅包声明 | local slice accepted；25项公开读库测试及独立审阅通过；不是完整release或真实内容验收 |
| VX-010内部取证 | lib/research/stages/reasoner.py、omnigraph_search/query.py、对应单测 | local slice accepted；28项取证/Agent测试与独立审阅通过，不是公开BYOLLM或端到端预算验收 |
| 主控文档 | 当前计划、ADR0004、规格、VX工单、索引与执行记录 | 主控维护；保护既有历史证据与无关WIP |

[KNOWN] 本轮不安装框架、不运行模型/抓取、不修改远端生产或数据，不自动commit/push。先离线TDD与独立审阅；后续真实内容链按计划切片2推进。历史通过次数不累计为新切片证据。

## 本轮验证（2026-09-09）

[COMPUTED] 主控在临时HOME、运行目录和最小环境变量下执行下列整合回归：**53 passed in 0.88s**。其中公开SQLite25项、检索/Agent28项；不累计历史测试数。

```bash
OMNIGRAPH_LOAD_ENV=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_vitax_knowledge.py \
  tests/unit/test_search_query_context.py \
  tests/unit/research/test_reasoner_agent_loop.py \
  tests/unit/research/test_caps_consolidated.py -q -p no:cacheprovider
```

[COMPUTED] 通过[可重放示例](docs/LOCAL_PUBLIC_KNOWLEDGE.md)的5个新进程完成构建、搜索、Wiki读取、related与证据追溯：命中1篇解读＋1篇Wiki，Wiki关联2份来源，2条关系均可定位证据，release一致。示例是人工摘录官方资料，不是自动ingestion结果。

[KNOWN] 两轮/三轮工具测试证明新检索证据实际进入后续模型输入，第一条大结果不会永久遮蔽后来结果；完整Source结果仍保留原顺序。初始/追加证据各最多6000字符（包括截断标记），不等于token预算或整个模型上下文限制。显式top_k同时下传到图候选与chunk候选，限制1–10；其它调用默认保持。图字段含义核对了[锁定LightRAG 1.4.15源码](https://github.com/HKUDS/LightRAG/blob/v1.4.15/lightrag/base.py)。

[KNOWN] 独立审阅发现的“只传证据条数、不传正文”和测试模块污染已修正并回归；最终独立审阅P1/P2已关闭，主控接受当前两个本地子切片。本地仍缺LightRAG包，测试替代外部RAG边界，不能宣称真实LightRAG集成、模型质量或生产已验收。图片查询证据与全流程预算留在VX-010完整验收，不新增组件绕过。

[KNOWN] 现场日志/示例输出与源码hash在本机临时证据目录 `/var/folders/y4/b7fx08tj715gknw6fdvt0vr80000gn/T/vitax-implementation-evidence-e1m59uee`；前态备份在 `/var/folders/y4/b7fx08tj715gknw6fdvt0vr80000gn/T/vitax-replan-before-plq_hpa0`。临时目录不是长期数据备份；重放入口和测试已留在源码。旧backlog历史字节段及930项删除WIP状态核对未变。

[KNOWN] 本轮全部子代理已完成并由主控安排关闭。当前下一前沿为VX-004真实来源→Hermes知识包→当前公开投影；不用重跑合成图/Wiki探针，不先安装Prefect或迁移向量库。

## 历史执行（以下保留原状态与范围）

状态：主控执行中。计划已授权执行；每项生产变更仍须逐任务验收，并遵守 ADR 0002 的四类例外。首次派工不得直接切换生产。

[KNOWN] 当前主线已按用户纠偏切换为[产品架构重建](docs/superpowers/plans/2026-09-09-vitax-product-architecture.md)：旧pipeline仅作参考，暂停追加兼容探针与迁移式补丁。以下为历史进度，未完成任务按新计划重排。

[KNOWN] 本轮完成源码边界取证、核心上游项目调研与计划审阅。选择模块化重建方向；Prefect为编排首个实验候选，LightRAG与混合检索须同语料对照，未指定生产引擎赢家。只修改文档和项目工作指引，未安装新框架、运行新pipeline或变更生产。下一执行切片为新文章合同、代表性真实来源与私有预览纵向链。

- 仅在具体派工的允许范围内变更；保留无关 WIP。
- 每项仅写互斥范围；保护约 930 个删除 WIP、其他未跟踪整理文件和其他任务输出。
- 禁止自动 commit、push，以及未在已批准工单中精确列出的部署、服务重启、采集、同步和数据迁移；VX-003 的 Hermes 单文件原子替换已获批准但仍须原 hash 一致。
- 保留证据；仅主控可改为 accepted、blocked 或 rejected。

| 工作项 | 状态 | 责任 | 互斥写范围 | 主控验收 |
| --- | --- | --- | --- | --- |
| VX-001 漂移分类 | partial evidence | explorer | docs/work-items/vitax-refactor/VX-001-source-drift-classification.md 和证据目录 | 分类候选已存在；尚非全差异结案 |
| VX-002 环境核实 | accepted (preflight) | uat | docs/work-items/vitax-refactor/VX-002-environment-verification.md 和证据目录 | 现场核查已接受；资源与部署适配仍待实测 |
| VX-003 同步退出码 | delivered; local/remote offline accepted | coder | scripts/sync-from-aliyun.sh、离线测试、docs/deployments/2026-09-09-sync-exit-fix/DEPLOYMENT_EVIDENCE.md | 本地 4 测试、远端 fake rsync failure=1/success=0、SHA/备份已验收；真实定时同步未验收 |
| DOC-001 规格和工单 | accepted (initial specification; program active) | controller | docs/spec/VITAX_REFACTOR_SPEC.md、docs/work-items/vitax-refactor/、docs/README.md、EXECUTION.md | 主控已接受初版；12 个工单的 DAG 已验，无重复编号；全项目仍进行 |
| VX-004 隔离单篇闭环 | partial | coder + uat | 已接受范围：config.py、tests/unit/test_config_env_loading.py、lib/llm_hermes.py、lib/llm_complete.py、tests/unit/test_llm_hermes.py、docs/deployments/2026-09-09-hermes-adapter/ | config gate 已本地 accepted；实验 adapter 已本地接受并完成一次 OHPC 合成 text-adapter 调用，见 [真实 probe](docs/deployments/2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md)；七文件组合为 56 passed。完整单篇 E2E、残留恢复和发布站点仍未完成 |
| VX-005 启动前置只读切片 | partial (local slice accepted; recovery incomplete; not deployed) | Pascal | deploy/aliyun/systemd/omnigraph-{daily,afternoon,evening}-ingest.service、tests/unit/test_ingest_prestart_read_only.py | 三份 service 的 dry-run 切片及 README 已更新；完整残留恢复仍未实现 |
| VX-006 Hermes 到 Codex 修复升级 | functional accepted (synthetic handoff only) | coder + uat | docs/deployments/2026-09-09-agent-handoff-probe/、隔离 harness、经批准源码 | 原始失败证据保留；修正实验的 Codex/Hermes/tool-handoff 功能已接受，但只覆盖合成算术，不等于完整自动故障修复；四类权限拒绝和 resolved Codex model/attempt/fallback 仍未完成或为 UNKNOWN |
| Fermat 实验适配器 | accepted (experimental; non-production) | Fermat | lib/llm_hermes.py、lib/llm_complete.py、tests/unit/test_llm_hermes.py、docs/deployments/2026-09-09-hermes-adapter/ | 主控接受 local + 一次 OHPC 合成 text-adapter 范围；[真实 probe](docs/deployments/2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md) 与 56 项组合测试已记录，不得据此标记 VX-004 整项、VX-006 或全项目完成 |

主控裁决（2026-09-09）：计划已授权执行；生产变更按逐任务验收和 ADR 0002 四类例外执行。24 小时恢复窗口未确认。首波局部离线通过不改变全项目的进行中状态。

[第二阶段计划审阅](docs/superpowers/plans/2026-09-09-vitax-second-wave-review.md)：隔离单篇主线，离线发布合同和最小恢复并行；不把子切片 accepted 当整项完成。

## 第二阶段当前派工（2026-09-09）

用户已授权按审阅计划实施。当前仅下列精确切片；候选经过审阅与整合回归后由主控接受，不代表生产允许。

| 子任务 | 责任 | 允许写范围 | 验收边界 |
| --- | --- | --- | --- |
| VX-004 隔离入口 | Locke | scripts/vitax_isolated_ingest.py、对应单测、second-wave/VX004.md | 离线隔离门；live尚未派工 |
| VX-005 最小清理保护 | Maxwell | scripts/cleanup_stuck_docs.py、cleanup与prestart单测、second-wave/VX005.md | processing拒绝、真实竞争测试；不把单方锁当生产互斥 |
| VX-007 发布清单 | Godel | lib/publication_manifest.py、对应单测、second-wave/VX007.md | 离线组件/版本/路径/hash验证；不发布 |
| VX-001 E2E现场子集 | Sagan | 无（OHPC只读） | 入口hash与依赖元数据；不读取凭据或业务内容 |

第二阶段收尾：参见[主控验收报告](docs/deployments/2026-09-09-second-wave/SECOND-WAVE.md)及同目录 REGRESSION.md。VX-004 仅预检布局，VX-005 仅禁止不安全删除，VX-007 仅离线文件合同；整项均 partial，无生产部署。

主控最终验收：第二阶段本地切片 accepted，整合回归 75 passed；Standards/Spec 问题关闭。全部子代理已关闭。未部署，未运行真实 ingest；整体计划仍进行。

## 第三阶段：真实单篇候选（2026-09-09）

用户已授权下一步隔离样本执行。Faraday 实现 scripts/vitax_single_article_probe.py 与对应离线测试、single-article 证据；Peirce 只读核OHPC并允许一次短合成 embedding 请求。当前真实LLM/候选运行等待主控代码与运行边界审阅，不修改生产目录。目标是实际 ingest_article、持久化、重新打开后的查询，显式标记未覆盖抓取/翻译/图片/Wiki。

第三阶段主控放行：runner SHA 14514de3d51d81a943d88f2765f6cd0691e292ddecc39c395938dc95cc0c1a73 经 Standards/Spec 复审。Leibniz 仅在 vitax-vx001.H8iYB3wq 候选运行一次固定样本，4文件覆盖需核SHA，临时loopback隧道，1200秒外层上限、12completion；首次失败保留证据后回主控，不自动重跑。此为代码级trusted probe，不主张内核sandbox。

第三阶段运行已回报READY_FOR_REVIEW：固定样本双入库/双freshreader通过，1chunk/8entities/8relations，Hermes4次，reader0次；隧道已关闭。Helmholtz仅只读复核落盘文件，禁止重跑query或模型。全量VX004仍partial。

第三阶段主控最终验收（2026-09-09）：固定合成缓存文本 accepted；两轴源码审阅通过，84项离线回归通过，真实run exit0，双freshreader通过；独立核26字段一致及文档→chunk→图来源关联。目标1chunk/8实体/8关系，Hermes completion4次，reader0次。额外dup-* failed是LightRAG重复提交诊断，不能据此声称status store全干净；不改运行数据。临时隧道已关闭，生产/Qdrant/Wiki/抓取仍未验收。见single-article/ACCEPTANCE.md（位于docs/deployments/2026-09-09-single-article/）。

## 第四阶段：Wiki 候选（2026-09-09）

[KNOWN] 主控放行固定样本的 Wiki 候选验证；Turing 实现最薄 probe，Singer 独立源码复审，Darwin 执行。复用现有 W3 adapter、assembler 和 engine，直接读取第三阶段持久文档，不新增 SQLite、不重新调用模型。仅允许候选 code 中新增 runner，以及 runs 下新建 vitax-wiki-candidate-*；生产及原样本保持不变。

[COMPUTED] Runner SHA-256 为 `199e6589bb8d483373c98cf6615af84f23a8123aaf1527f09aca7e5e699a0a0b`。补齐项目声明的 python-frontmatter/PyYAML 后，3 项核心测试实际通过，pip check 通过。独立复审关闭错误库默认写路径、测试缺陷和运行哈希约束问题。远端须先核对既有 GraphML 哈希并保存全输入清单，方可单次执行；此时运行验收待完成。见 [执行边界](docs/deployments/2026-09-09-wiki-candidate/APPROACH.md)。

[COMPUTED] 第四阶段主控最终接受：远端单次运行 exit 0 / APPLIED；候选 `vitax-wiki-candidate-mt6cr6le` 产生一份实体页面及锁文件，正文摘录和来源引用可追溯到已处理文档。独立审阅核对 runner、原始/脱敏 receipt、页面哈希及20文件输入清单通过；执行者核对29文件原 Wiki 清单未变。仅接受合成样本的候选编译与来源链，不接受公开发布、语义质量、生产自动 Wiki hook 或整个 VX-004。所有子代理已关闭。见 [验收证据](docs/deployments/2026-09-09-wiki-candidate/ACCEPTANCE.md)。下一步为计划中的真实来源抓取、清洗、翻译和关键图片验证。
