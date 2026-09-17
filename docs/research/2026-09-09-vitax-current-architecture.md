# VitaX 当前架构取证：从遗留流水线到产品边界

**范围。** 本文只依据本检出中的源码、当前重构规格和工单索引作结构判断；没有运行导入、测试、服务、SSH 或部署，因而不声称任何运行环境、数据完整性或站点健康现状。`docs/spec/VITAX_REFACTOR_SPEC.md:1-57` 将生产/发布验收另行约束；其描述是产品目标，不是本文的运行时证据。

## 已实现的代码路径

```text
KOL/RSS SQLite 候选
  -> Layer 1 元数据判别 -> 抓取并回写 body -> Layer 2 正文判别
  -> ingest_wechat.ingest_article -> LightRAG 文档/图/向量
                              \-> 图片后台描述、磁盘 Markdown/metadata
  -> 翻译列（标题内联，正文另一个 cron）
  -> 成功 article ref -> Wiki evidence/patch -> kb/wiki/*.md
SQLite + kb/wiki + 图片 -> export_knowledge_base -> kb/output 静态树
SQLite FTS5 / LightRAG 合成 -> /api/search
```

1. **采集与分类。** `batch_ingest_from_spider.ingest_from_db` 既建/补 ingestion 表又选候选（`batch_ingest_from_spider.py:1787-1865`），批量调用 Layer 1 并持久化判词（`:1873-1969`）。候选按 URL 调用通用抓取器、把正文回写到来源表（`:2372-2401`），再进入 Layer 2；`ok` 才调用单篇入库（`:2121-2197`）。这是当前 WeChat/RSS 汇流处，来源表仍不同。
2. **清洗、正文与图。** `ingest_wechat.ingest_article` 是单 URL CLI 与批处理共享的入口，并允许复用 LightRAG 实例（`ingest_wechat.py:1182-1188`）。图片模块下载、尺寸过滤、将 Markdown URL 改成本地静态路径（`image_pipeline.py:143-211`, `:214-297`），再用临时文件加 `os.replace` 保存 `final_content.md` 与 `metadata.json`（`:474-489`）。图片描述由后台 worker 启动，故文本入图与视觉补全不是同一提交边界（`ingest_wechat.py:554-680`）。
3. **图与“规范文档”。** Layer 2 通过后直接调 `ingest_article`，该编排器只以 `success && doc_confirmed` 写入 `ok`（`batch_ingest_from_spider.py:2195-2218`）。目前没有一个由类型定义约束、同时承载原文、清洗文、翻译、图片出处、质量判词和发布资格的 CanonicalDocument；可见的是 SQLite 行、LightRAG 文档和磁盘 `final_content.md` 的组合。
4. **翻译。** 标题在成功入图后内联回写 `title_translated/translated_lang/translated_at`；失败仅记录警告（`batch_ingest_from_spider.py:2220-2259`）。正文翻译是独立的 `translate_body_with_deepseek_tavily`，它取 Tavily 上下文并在异常时返回 `None`（`lib/translate.py:246-295`）。这证明翻译是旁路增强，而非 CanonicalDocument 的原子版本。
5. **Wiki。** 批处理仅把本批 `ok + doc_confirmed` 的 `(source, md5(url)[:10])` 收集为 Wiki 引用（`batch_ingest_from_spider.py:2210-2218`）。生成器则从 LightRAG、SQLite chunk 映射和可选 Web 检索取证，构造 `EvidencePack -> WikiPatch` 后交给共享编译器（`scripts/wiki_generate_pages.py:1085-1154`）。编译模型强制 article evidence 为十位十六进制 ref（`kb/wiki_compiler/models.py:65-103`），引擎对页面使用锁与原子替换（`kb/wiki_compiler/engine.py:519-600`）。
6. **发布与搜索。** 静态导出明确只读 SQLite/文件系统、只写 `kb/output`，并要求同一输入产生字节相同的输出（`kb/export_knowledge_base.py:1-18`）。导出从 `ArticleRecord` 选择/改写正文及图片（`kb/data/article_query.py:594-780`）。FTS 使用 SQLite trigram，且将来源、正文与两层质量词作为查询条件（`kb/services/search_index.py:67-155`）；API 可同步 FTS 或异步 LightRAG（`kb/api_routers/search.py:200-251`）。根目录有 `KB-v2-site.zip`，但未找到 `ZIPsite` 目录/源码引用，不能把它纳入上述发布链。

## 五项最高影响结构负债

1. **编排器承担全部领域责任。** `ingest_from_db` 同时管理 schema、来源适配、LLM 判别、抓取、超时、LightRAG 生命周期、翻译、状态写入和 Wiki 输入（`batch_ingest_from_spider.py:1828-1854`, `:2010-2266`）。任何产品规则改变都会穿透这个脚本，难以单独重放或替换。
2. **同一文章有多套身份与完整性判断。** Wiki ref 是 `md5(url)[:10]`（`:2210-2218`），Wiki 模型只接受十位 ref（`kb/wiki_compiler/models.py:72-103`），搜索又分别以 WeChat `content_hash` 和 RSS 截断 hash 关联（`kb/services/search_index.py:131-146`）。`ingestions` 因双来源故意没有 FK，完整性由应用层维持（`batch_ingest_from_spider.py:1829-1834`）。这使跨存储的一致性成为约定而非可验证合同。
3. **状态机分散且以 NULL/覆盖写表达恢复。** Layer 1/2 判词、checkpoint stage、`ingestions.status` 和 `doc_confirmed` 共同决定推进；Layer 2 的 `NULL` 代表待重试并另靠时间回退（`:2049-2114`），`INSERT OR REPLACE` 又覆盖 ingestion 行（`:2137-2142`, `:2261-2266`）。这不保留一次加工的不可变审计事件，也不提供统一幂等键。
4. **加工产物没有版本化发布单元。** 图片文件与 Markdown 可原子写，但图入库、翻译列、Wiki 和 `kb/output` 在不同路径/时刻生成；静态导出只保证其输入不变时确定（`kb/export_knowledge_base.py:1-10`），不证明 SQLite、图、图片、Wiki 是同一版本。VX-007 也仍把跨分量版本/校验/原子可见性列为未完成验收（`docs/work-items/vitax-refactor/VX-007-publication-contract.md:11-15`）。
5. **公开读模型仍直接耦合加工库与模型可用性。** FTS 直接查询生产式来源表并复述过滤逻辑（`kb/services/search_index.py:131-146`）；默认 API 路径启动进程内 background job（`kb/api_routers/search.py:243-251`），job state 也在内存（文件头 `:1-18`）。这阻碍可独立、可版本化的公开读取面。

## 可复用资产

1. **两层质量门及其持久化语义**已经把低成本初筛与正文判定分开（`batch_ingest_from_spider.py:1873-1969`, `:2021-2124`），可迁移为 CanonicalDocument 的质量阶段。
2. **source-aware 的文章解析层**已有 `canonical_article_ref`、`lightrag_doc_id`、跨来源索引和 chunk 映射（`kb/wiki_articles.py:56-314`），适合作为统一 ID 迁移的适配层，而不是继续在调用点算 hash。
3. **图片来源与原子文件输出**已有可用的本地化/metadata 边界（`image_pipeline.py:283-297`, `:474-489`）。
4. **Wiki 编译器**已有不可变 EvidencePack、确定 patch ID、页面基线摘要、锁和原子写（`kb/wiki_compiler/models.py:35-58`, `:110-206`; `kb/wiki_compiler/engine.py:568-600`）。它是最接近“内容变更必须可追溯”的产品内核。
5. **静态导出与 FTS 的读侧分离意图**明确：导出不写源数据（`kb/export_knowledge_base.py:1-10`），FTS 输入作转义与质量约束（`kb/services/search_index.py:38-64`, `:125-155`）。两者可成为不可变发布包的消费者。

## 产品不变量与偶然遗留合同

**应保留为产品不变量：** 来源可追溯；质量门可解释且可重试；图片与正文出处绑定；公开内容只能来自已验证的发布批次；Wiki 必须携带可校验的证据；公开检索不得绕过质量/权限边界；发布必须可识别版本并能回滚。这与重构规格的“正文/翻译、图、Wiki 候选、caption 来源、公开查询引用”验收一致（`docs/spec/VITAX_REFACTOR_SPEC.md:20-47`）。

**应视为可替换的遗留实现合同：** `articles`/`rss_articles` 双表和无 FK 的 ingestion 联接；十位 MD5/截断 hash；在业务脚本内建表/补列；以 NULL、sleep、环境变量和 `INSERT OR REPLACE` 表达恢复；标题内联而正文 cron 异步；直接以 LightRAG 成功作为文档确认；`kb/output` 目录即发布候选；进程内 search job。它们解释当前路径，但没有理由成为下一代产品 API。

**重构边界建议（非实施方案）：** 把 CanonicalDocument、加工阶段事件、证据引用和不可变 PublicationManifest 定为显式合同；采集/模型/图/Wiki/导出只读写各自的契约输入输出。这样保留已有质量、证据、原子写和静态读侧资产，同时解除脚本、存储布局与发布语义的捆绑。
