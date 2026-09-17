# VitaX 检索与知识项目调研

核查日期：2026-09-09。研究子代理检索官方资料，主控复查关键主张并整理本文。只核对上游源码/文档，没有运行引擎、升级生产或获取质量排名。所有取舍为[INFERRED]，不能从stars、论文得分或已安装推出适配VitaX。

| 项目 | [KNOWN] 当前机制与来源 | [INFERRED] 处置 |
| --- | --- | --- |
| LightRAG | 图、向量、KV和文档状态组成检索系统；有多种检索模式、增量和选择性删除，删除重建可依赖索引期缓存。[仓库](https://github.com/HKUDS/LightRAG)、[后端说明](https://github.com/HKUDS/LightRAG/blob/main/docs/LightRAG-API-Server.md) | 图增强候选，和无图基线比较。独立保存原文与结构化证据；不能因已有路径就指定为生产赢家 |
| Qdrant | dense/sparse、多阶段查询和RRF等融合；全文索引、可配置及multilingual tokenizer。[混合查询](https://qdrant.tech/documentation/search/hybrid-queries/)、[全文检索](https://qdrant.tech/documentation/search/text-search/full-text-search/)、[分词](https://qdrant.tech/documentation/manage-data/indexing/#tokenizers) | 混合检索基线候选。中文效果实际评估；不把索引当文章事实源 |
| RAGFlow | 文档解析、chunk及知识库管理；Docker方案依赖文档引擎及MySQL、MinIO、Redis等服务。[部署](https://github.com/infiniflow/ragflow/blob/main/docker/README.md)、[知识库配置](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/configure_knowledge_base.md) | 作为文档产品/解析参照；不因功能多整套引入。PC资源并非已证明不足，代价在于新增服务体系与定制面 |
| Graphiti | 面向Agent的时间图、episode及关系来源、增量时间信息；当前Kuzu仍有driver但已deprecated，官方推荐新项目用Neo4j/FalkorDB。[README](https://github.com/getzep/graphiti)、[依赖](https://github.com/getzep/graphiti/blob/main/pyproject.toml) | 当前不采用；会话/时间记忆与专业文章知识综合不同。出现明确事实有效期需求再专项评估 |
| Microsoft GraphRAG | 图与社区报告、跨文档综合；官方说明主要维护状态及索引成本风险。[仓库](https://github.com/microsoft/graphrag)、[查询](https://microsoft.github.io/graphrag/query/overview/) | 借鉴主题综合方法，不选为新主引擎 |
| LlamaIndex | 可组合文档/检索框架，提供source node和图存储接口。[schema](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/schema.py)、[图接口](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/graph_stores/types.py) | 第一条链不新增第二层框架；某个具体适配器能明显节省实现时再局部采用 |

## 主控纠偏

[KNOWN] 初稿“Qdrant没有文本分析能力”的概括与当前全文索引及multilingual文档不符，已删除；这些功能仍不意味着它是知识图谱或通用NLP框架。Kuzu已改为弃用状态。

[INFERRED] 初稿“保留LightRAG为首选”存在遗留路径偏见，改为候选对照。旧引擎只提供一种可测基线，新文章合同不以其内部状态/ID/存储布局定义。

## 可执行结论

[INFERRED] 分离原始/标准文章、带证据的知识产物、可重建索引、回答证据四层。摘要/Wiki既是内容产品也是检索语料。用同一组真实文章和30个有参考来源的问题，对照关键词、混合检索、图增强；覆盖跨语言专名、关系、变更/撤回、无答案及引用定位。

[INFERRED] 初轮只运行决定下一步的候选，不把六个项目全部部署。固定语料、问题、模型路由与检索预算，分别记录建索引和查询成本。图增益若不成立，优先优化证据检索/摘要；图谱产品能力保留，但不成为所有文章可发布的技术前置。

[KNOWN] 功能存在不等于VitaX接入正确。更新/删除、embedding变化、中文效果和云端资源开销均未在新方案验证；版本在实现试验时固定，本文不授权自动升级生产。

执行入口：[产品架构与执行重排](../superpowers/plans/2026-09-09-vitax-product-architecture.md)。
