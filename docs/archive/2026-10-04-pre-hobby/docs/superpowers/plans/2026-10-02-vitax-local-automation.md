# VitaX 本地自动闭环执行计划

Spec: [本地自动闭环规格](../../spec/VITAX_LOCAL_AUTOMATION_SPEC.md)。Status: authorized / executing。复用既有issue及模板，.planning/ISSUES.md仍权威；不重新建GSD/.scratch tracker。

## 依赖与票级主控

| 票 | 交付 | Blocked by | 主控/工作面 |
| --- | --- | --- | --- |
| L1 VX-004E | 一轮有界微信/RSS公平筛选、明确翻译/失败结果并持久化 | None | 当前可写6.1-Sol；已有本地Python与原SSH部署面，Luna只读取证/测试 |
| L2 VX-009E | 正常历史文章/译文全可读，完整镜像自动导出并可原子刷新，内部链接有效 | None | Sol实现；Luna合同/入口核查；现有localhost+已授权deterministic harness |
| L3 VX-004F | 真实来源→文章解读/跨源Wiki/实体关系→可接受新投影，重跑复用 | L1运行门可提供新来源；L2快照入口（输入准备可并行） | Sol；先核主生产面及原生绑定，再用既有producer；不调用失败的coderroute |
| L4 VX-011A | 自动同版镜像+知识包→本地网页发布，坏包保旧版，正常次轮更新/链接验收 | L1、L2、L3 | Sol编排单入口/原生scheduler；Spec/Standards独立Sol复审，Luna定向验收 |

R1资源已缓解不重复扩容；旧R4/R5变化保留，R2控制重入并入L1仅必要子切片；R7/8知识与Wiki并入L3；旧R9同源门并入L4；旧R6深问查询副本继续open但本轮不作为本地读用的阻塞。

## L1 最小实现/验证

- batch_ingest_from_spider.py::_build_topic_filter_query改现有复合查询的排序：源内FIFO、跨源交错；8列schema/原反连接与拒绝/failed规则保留。不扩大max10/6300s批次或公众号扫描预算。
- tests/unit/test_ingest_from_db_orchestration.py加真实入口有限批次前两条各来源一次RED；tests/unit/_ingest_fixtures.py及现有dual-source/filter/max-cap检查匹配。
- scripts/translate_body_cron.py只修实际部分失败/零成功仍exit0接缝，复用现有helper。若路径不一致先源码hash/已配置DB pin证据再修，不猜或让placeholderkey覆盖生产凭据。
- 受控失败重入按原VX-005B具体门：有真实需求才添加标记/原子消费，普通failed不放开；无界修复不打包。
- 生产仅同preimage所涉文件备份、parse、原子应用；当前在写batch不强停，下一原timer读取新代码。一微信一RSS真实正常正文/hash/成功字段读回；整个批次结果/下次timer分别记状态，不从active称PASS。

## L2 最小实现/验证

- 复用vitax/local_articles.py的只读字段/receipt验签，新增scripts/export_vitax_library.py单入口：source SQLite完整dual表必要字段，不按ingestion-ok过滤；已有rawartifact补回仅通过已有来源hash映射，不能拿rewrite充原文。
- 输出source外NEW snapshot目录，DB+receipt同目录，chmod700/600，snapshotID/UTC observed/hash。验证成功后一个current symlink原子提升。CLI能够独立运行、本地或已有SSH一次export路径，不复制秘密/account表。
- 复用vitax/api.py dynamic DB路径和site route；需要重开本地server仅为初始配置指向current，新版本提升不重启。仅localhost，公开默认仍不含全文。
- 对已有Body/Evidence/Link组件做必要复用；所选正常文章原文/译文/引用路由/实体/刷新/跨100条、无效ID与安全HTTP(S)链接，借已有测试入口；不检查10k第三方外链网络，不把客户端browser拒绝当server错。

## L3 最小实现/验证

- existing accepted产物/usage按source hash/recipe优先重放；核当前已授权Hermes解释器/runner/SDK路径，不读secret值、不失败后换provider。
- scripts/build_vitax_source_packet.py选1–2真实技术来源（完整正文，32KiB最终prompt门）；vitax.production.run existing article/wiki stage+usage，accept_model_output引用逐字、稳定来源/独立URL、实体关系和基线合并。
- 有实质旧Wiki建议且已有consumer时用scripts/wiki_evolve.py limit1既有主业务provider；同主题只有指定一次生产，RETRY/REJECT/占位不称applied。若涉及kb源码按kb/docs/10-DESIGN-DISCIPLINE.md先本地E2E。
- tests/unit/test_vitax_production.py和source_packet/实际原生receipt、Wiki/evidence本地生成及KB节点/关系持久化证据；长文明确保全/待分段，不截原文制造成功。

## L4 最小实现/验证

- 脚本单一可重跑入口接已核source snapshot、已有/新accepted产物、原scripts/build_vitax_release.py。使用现有95条public基线显式merge，不整包抹掉旧知识。
- manifest/sqlite/site/receipt验证成功才提升到current；失败保旧，无每次重启。一个scheduler调度本地刷新入口，复用现有采集/翻译/建图日程而非二次触发付费采集；model failure保持原provider与旧版。
- 真实源同一身份/body hash→本地原文→处理/图谱→Wiki/已接受投影→新release→HTTP与页面；重复运行数据无损/不重复模型，坏包不提升，原文仍私有。MCP只做既有兼容回归，不建设deep-question产品化。
- Spec/Standards审阅本轮前后增量，修其具体错误，然后最小针对检查/git diff --check/manifest全路径与API静态资源链接。注册原生scheduler前有可review单次运行结果、回滚范围与成功原日程证据。

## 预算与结果

E=docs/deployments/2026-10-02-closed-loop-execution：START/WIP/STATE/每票receipt/错误账/模型实际请求/最终REPORT。当前0%起点→10%硬停止；8不新票、9checkpoint。正常并发2–3含父，硬4；每子fresh短packet、无孙、五字段结果、wait/inspect/close。历史失败计数继承，同一branch第二次失败止。跨多个自然周期不能伪称长期稳定，必要时持久化观察门而不是空等数周。
