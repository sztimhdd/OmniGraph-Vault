# VitaX 稳定闭环技术与验收合同

2026-10-03。对应 [获批计划](../superpowers/plans/2026-10-03-vitax-stable-deepseek.md)。不修改深问API/MCP生产架构。

## 现有路径与状态

`WeChat轮转 / RSS → 原始SQLite → L1/L2 → 正文摄取与实体图谱 → 翻译/显示改写 → 私有完整快照 → DeepSeek文章解读 → 已有Wiki更新 → public DTO → build/prerender/manifest → 原子current → VitaX网页`。

原文不因发布审核被过滤。读库默认提供全量记录；网页默认勾选“仅有正文”，可取消。译文独立保留，公开站只使用验收后的知识和必要证据。现有旧显示改写不覆盖原文；尚有837篇改写引用旧localhost图片地址，本轮没有将这些内容直接当成本地完整可用页面。

| 阶段 | 已有证据/状态 | 不允许的推断 |
|---|---|---|
| 抓取 | 来源错误计数、正文是否存在 | metadata行不代表正文抓取成功 |
| 过滤 | layer1/2 verdict、prompt version、backoff | NULL不是拒绝，也不是成功 |
| 入库建图 | ingestions.status=ok且doc_confirmed；batch metrics | 服务启动不是图谱成功 |
| 翻译 | body/title译文分别持久化；ok/partial/fail聚合 | 单字段成功不能标完整成功 |
| 显示改写 | body_rewritten、rewritten_at；保留body | 老localhost图片路径不等于本地资源可达 |
| 知识生成 | 实际DeepSeek请求/model/usage/output SHA | 配置intent不代表真实完成 |
| 发布 | 完整manifest、reader release id、实际页面 | HTTP健康检查不等于全部链接可用 |

## 最小实现

- 使用单调时钟建立批次预算。过期clamp返回0，保留60秒flush预算。实际DB入口的L1/L2/scrape/标题翻译受同一预算限制。Tavily使用生产已安装的Async客户端。必要的存储flush不强杀；自然批次总时长另外验收。
- 每日生成使用ACK现有DeepSeek API凭据，保留请求名与实测返回名。当前直连请求`deepseek-v4-flash`，返回`deepseek-flash`。不改变OCX/Codex全局角色。不回退Hermes/OCX。
- 日常上限两篇、三次新模型请求，SDK零重试，JSON输出、非思考、12000输出token上限。debug实验不伪装成日常三次调用，单独记账。失败当日不按小时重计费。
- 通用DeepSeek文本wrapper也拒绝已知截断finish_reason，译文/改写/图谱调用不得把截断文本当成功。
- `deepseek-chat.v1`回执包含实际request_id、requested_model、model、api_calls、finish_reason、prompt/completion/total tokens、output_sha256。失败、空实际模型、截断或SHA不匹配不得验收。旧Hermes回执继续按旧规则重放。
- 当前公开最小切片采用显式Harness主题，稳定Wiki ID由调度参数指定`legacy-harness`。不模糊合并其他主题。更新保存旧证据ID，新证据必须属于本次真实来源，current替换前核对旧版本。
- revision与标准化共用段落JSON哈希规则。普通验收失败按revision/recipe/article计数，两次后跳过；provider故障不永久隔离来源。输出及失败目录保留。失败原生结果每日最多补一次，重放成功结果不计新调用。
- citation_bank使用原文精确片段，模型只选择citation_id。未知ID拒绝。旧quote形式仍支持，唯一空白换行恢复保留原文真实span，不改词或标点。实体/关系符号ID规范化小写，碰撞与闭包失败在构建前拒绝。
- 公共包通过现有build/prerender完整生成，不做sync-only。manifest覆盖所有文件、哈希与release id一致后原子切换。坏包保留旧current。

当前引用库每段最多40个片段，过长或特殊结构不是“完整深度处理已完成”的证据。全部原文完整保留；旧改写30000字符阈值和超长文分段改写仍属下一步，不通过删正文伪装完成。

## TDD与实际验收

先失败复现，再最小修复：预算过期不启动、慢翻译后ok保存、墙钟回拨、真实回执/SHA、模型别名、未知引用ID、段落前导空白、关系大小写碰撞、已发布版本不重选、只有失败的revision隔离、坏包保留旧版、正常正文筛选。

定向运行使用`OMNIGRAPH_LOAD_ENV=0`与合成凭据。orchestration测试用临时DB和匹配8列fixture。历史timeout公式测试显式固定`OMNIGRAPH_CHUNK_FLOOR_S=1200`；生产3600秒配置未被修改。

实际证明见[执行目录](../deployments/2026-10-03-stable-deepseek-execution/REPORT.md)：两篇DeepSeek解读、已有Wiki更新、旧引用保留、完整包发布、2960篇正文API逐篇SHA一致、浏览器/手机/全部公开内部链接。自然两批使用只读观察脚本另存结果，未发生前保持WAITING。

DeepSeek参数与别名由[官方聊天API](https://api-docs.deepseek.com/api/create-chat-completion/)及[官方集成文档](https://api-docs.deepseek.com/guides/codex)核对，实际回执才作为生产路由证据。
