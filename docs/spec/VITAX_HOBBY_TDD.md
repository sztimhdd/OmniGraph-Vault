# VitaX技术方案：现有双轨采集、图谱与云端读站

更新：2026-10-09。运行现状见[唯一issues](../../.planning/ISSUES.md)，执行顺序见[当前计划](../superpowers/plans/2026-10-04-vitax-next-stage.md)。不另建tracker或工作流平台。

## 部署与责任

- ack-node-2 / iZj1imk39yc55iZ：原库、采集、清洗/筛选、LightRAG/Qdrant、Flash加工与producer。
- Hermes：微信Edge/CDP及登录态；阿里云调度调用既有链路，需扫码才找用户。
- ack-node-1 / ack-node-2-kg：Python3.12 reader、文章/知识SQLite、SPA及媒体；原KB/MCP保留。
- Mac：开发与免费镜像；不是付费producer。collector沿用同一100元账本、锁、缓存。

## 采集到可读正文（03，依赖05加工补缺）

复用enrichment/rss_fetch.py、scripts/dajiala_kol_scan.py、lib/scraper.py、batch_ingest_from_spider.py。RSS失败源与成功源分开；微信保持每周20号×2页轮转。原文保存后即可阅读，不能等建图成功。
先处理最新5篇尝试/0篇完成的正文拒绝：从真实已下载内容判断Sign in属于导航还是正文登录墙。只修共性提取/质量门，保留真实登录墙检查。网络/DNS永久坏源单列，暂时错误按现有退避，不要求91源全绿。
复用现有images目录和正文内引用；检查新文章图片确实保存并到达网站机，不能把首次7661文件传输视为未来自动同步。用已有SSH/rsync或发布器补传新增引用媒体，不每次全量重传。
翻译复用Flash全文/分块入口，原文和有效旧稿保留。旧translate_body_cron仍有Pro/搜索增强路径，需合并任务归属或取消重复付费调度；改动前核对实际候选、锁和进行中的任务，不盲停其他采集服务。

## 内容补缺与发布（02、05）

复用scripts/refresh_vitax_local.py、vitax/production.py、lib/llm_deepseek.py。从原库缺口选稿，先复用有效稿，再做所缺步骤。50是队列规模，每篇独立缓存，主题Wiki合并更新。文章成功先保存/发布，Wiki失败保留旧版，不逐篇审批。
长文按容量分块，不经过短解读提示词；保留代码/表格/链接。写回已有body_translated/body_rewritten字段，检查正文版本，不能覆盖后来原文或有效稿。图谱关联与Wiki pending分别报告，不把知识包条数当图谱节点数。
共享账本100元；成功缓存避免重复费，未知请求先查结果。每批只汇总成功/复用/失败/剩余/Wiki/耗时/费用。暂不引入并行模型调用优化，先理顺失败隔离与任务归属。
producer复用venv启动钩子，wrapper设置OMNIGRAPH_REPO_ROOT=$CODE。部署带lib包入口/依赖与原子写补丁；离线检查实际导入路径与长文分块，不用付费模型做部署烟测。10/9修复后自然业务结果仍待核。
发布复用SQLite快照、已有SSH和systemd，失败留旧版本。媒体需要随新增内容更新。定时运行不依赖主控聊天；持续无产出、费用不足、扫码或恢复失败才报警。

## 图谱与API（06）

复用batch_ingest_from_spider.py的LightRAG写入、现有图存储与kb/api_routers/search.py、research.py、lib/research。先确认一个正常入库文章已进入实体/边/正文chunks且可查，再接自然日程。不为每篇模型派代理。
reader知识SQLite中的entities/relations不是LightRAG/Qdrant自动写入证明。需要明确当前实际图谱写入与查读路径，避免再次出现网站更新而查询副本停在旧数据。
优先核对已有采集机KB/API能否提供当前图查询；可复用则读端沿既有连接查它。否则沿现有同步补必要图谱/分块结果，不新建图引擎或第二套生产链。
普通搜索复用/api/library和旧/api/search?mode=fts，以已知正常文章验证命中。普通浏览/搜索不调用业务模型。深度调研复用/api/research，先离线覆盖结果/错误，再进行一例有界真实调用，使用批准的业务预算与Flash；输出来源与明确错误。路由存在或OpenAPI注册不等于真实调研可用。
本次只做API基础可用；MCP生产化、复杂多Agent调研和全库图谱重建仍延后。不要把旧MCP随新站公开。

## 云站和UX（01、04）

复用vitax/local_articles.py、api.py、vitax-site及scripts/publish_vitax_release.py。所有正常历史正文可读，原文/译文/整理稿标明类型，Markdown/HTML安全渲染，表格/代码/图片/来源链接可用。
网站先用47.103.73.20:8767（原生映射到内部8788），保留--no-mcp，只开放阅读入口。域名后接HTTPS；不建设账号平台。公网访问需同时验证应用监听及实际外部HTTP，不能只看systemd active。
UI #100–#110按当前已实现行为做少量实际阅读、搜索、返回、Wiki/来源关联检查，发现缺口直接归原票。#102归组、#108复杂定位、#111–#114增强先延后，不借验收整站重设计。

## 相关检查入口

| 票 | 最小相关检查 |
|---|---|
| 01/04 | test_export_vitax_library.py、test_vitax_local_articles.py、前端local-articles.test.ts；云端实际阅读/搜索/图片/返回 |
| 02/05 | test_refresh_vitax_local.py、test_deepseek_completion_receipt.py、test_backfill_budget.py、test_publish_vitax_release.py；自然批次摘要与已付缓存续跑 |
| 03 | test_ingest_from_db_orchestration.py和对应fixture；质量门/来源提取相关回归；自然微信/RSS正文入库 |
| 06 | 现有实体入图、搜索、research相关测试；已知文章检索和一例有界调研结果 |

使用.venv/bin/python，离线OMNIGRAPH_LOAD_ENV=0；该变量本身不隔离网络。源码/WIP、凭据、原始库和成功产物保留，检查改动diff，不自动commit/push。

## 06源码核查补充（Sol只读核查，主控复读关键位置）

- vitax/production.py的实体/关系只进入知识投影/SQLite，不写LightRAG；真实建图复用batch_ingest_from_spider.py→ingest_wechat.ingest_article→rag.ainsert。
- batch_ingest_from_spider.py约426行将None判失败，而ingest_wechat.py约1656行成功验证后返回vision_task，无图片时是None。修复需分开文档成功与视觉任务，缓存/失败分支都检查，不能简单把所有None当成功。
- kb普通FTS与KG任务、POST /api/research已实现；research最终来源只合入KG，漏WebBaseline/Verifier来源。先修来源合并和一个旧KG测试mock错误，再做一例有界真实调研。
- 06优先查采集机当前kb.api/存储与新文章可见性，能复用则沿已有连接查它，不同步整图作为前置。新主站免费文章检索继续复用/api/library，不为同一搜索再造代理API。
- 本地缺LightRAG/qdrant-client，不能声称完整图谱/API测试通过。子代理20个相关文件语法检查，不是业务运行证明。

10/9实际API核对：research可完成，但retriever把KG上下文URI固定为内部符号，后续用已有文档/原文URL映射，不虚构可点击来源。旧MCP已废弃，公网8767现为阅读站；新MCP端口留未来任务，不在本票恢复。
