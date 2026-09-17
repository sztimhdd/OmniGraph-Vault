# 本地公开知识读库

2026-09-09。范围：VX-007 的第一个离线构建/读取切片。此处说明实际 CLI 合同；完整 ingestion、站点、图片发布、BYOLLM、向量/图引擎选型和云端 release 尚未验收。

## 运行示例

从仓库根目录执行；`vitax` 模块只使用 Python 标准库，不导入旧项目的 provider/config。使用系统 SQLite 提供的 FTS5，不安装模型或新服务。

```bash
vitax_demo_dir=$(mktemp -d /tmp/vitax-public-demo.XXXXXX)
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m vitax build \
  test/fixtures/vitax_public_knowledge.json "$vitax_demo_dir/public.sqlite"
.venv/bin/python -m vitax search "$vitax_demo_dir/public.sqlite" FTS5
.venv/bin/python -m vitax read-knowledge "$vitax_demo_dir/public.sqlite" wiki-sqlite-query
.venv/bin/python -m vitax related "$vitax_demo_dir/public.sqlite" sqlite
.venv/bin/python -m vitax read-evidence "$vitax_demo_dir/public.sqlite" cte-overview
```

[KNOWN] 示例是本次人工整理的公开文档摘录：来源为 [SQLite FTS5 概述](https://www.sqlite.org/fts5.html#overview_of_fts5) 与 [WITH 概述](https://www.sqlite.org/lang_with.html)。包含一份文章解读、一份双来源 Wiki、两条有引用的关系。`*-excerpt-v1` 是本地摘录标识，不是上游正式版本；发布时间是示例元数据，不是生产发布时间。未伪造来源发布时间或抓取时间，未调用模型生成或抓取 pipeline。

## 输入与输出合同

[KNOWN] 输入 JSON 是**已经选择公开内容的投影**，不是原始文章库，也不是第二个知识生产主库。顶层 `schema_version=1`、`release_id`、`published_at`；集合如下：

| 集合 | 核心字段 |
| --- | --- |
| documents | doc_id、revision_id、title、source_url、source_published_at、fetched_at |
| evidence | evidence_id、revision_id、locator、quote |
| knowledge | knowledge_id、kind（article/wiki）、title、body、evidence_ids |
| entities | entity_id、name |
| relations | relation_id、source_id、target_id、relation_type、evidence_ids |

[KNOWN] 每个记录必须明确 `visibility=public/private`。只持久化显式字段；私有记录和未知附加字段不进入公开 SQLite。公开知识和关系必须引用非空、存在且公开的证据；证据必须指向公开文章版本。Wiki/关系可引用多个来源，同一 doc_id 可有多个 revision_id。来源URL不能携带userinfo凭据。来源历史时间可为ISO日期/时间或null，release发布时间必须含时区。未知附加字段被忽略并不等于自动审查 body/quote 内的秘密；上游仍负责选择可公开文本。

[KNOWN] `build(projection, output_path)` 只创建全新目标，先完成验证和暂存再使目标可见；现有文件或链接不能被覆盖。它不是完整云发布器，不切换 current、不上传或删除旧版本，也不替代私有备份。旧 `lib/publication_manifest.py` 的六组件清单尚未接入；完整包在 VX-007 后续切片收敛成单一发布合同。

[KNOWN] Python 接口为 `vitax.knowledge.build` 与上下文管理器 `KnowledgeReader`；读取方法为 `search`、`read_knowledge`、`read_evidence`、`related`。每个响应包含 `release_id` 和 `published_at`。检索得到 knowledge_id，随后可读取正文与 evidence_ids，再读取具体来源和段落定位。关系返回方向、类型、端点和 evidence_ids，不提供任意多跳图遍历。

[KNOWN] 首片查询将输入作为 FTS 字面短语，结果上限1–100，搜索输入至多512字符。默认 `unicode61` 不是中文分词器，连续中文片段中的子词不保证命中；英文多词采用短语语义，也不是自由关键词 AND/OR 查询。中文检索准入、分页、snippet 与产品搜索交互归 VX-009，不把本例命中宣称为检索质量合格。

## 当前验收边界

[INFERRED] 验证对象是实际 SQLite 和 CLI 的公开数据流，而不是 mock 服务健康：构建后重开，文章/Wiki可查，关系证据可追溯，私有与坏引用拒绝，失败不覆盖目标，读取不写库。示例来源是可核验官方文档，但仍不是自动生产闭环或正式站点 UAT。

后续入口：[当前计划](superpowers/plans/2026-09-09-vitax-product-architecture.md)切片2；执行记录见根目录 EXECUTION.md。

[COMPUTED] 本轮主控验收：公开读库25项测试、全部相关切片53项整合测试通过；上述5条CLI命令用独立新进程验证通过。结果与限制见根目录执行账本。
