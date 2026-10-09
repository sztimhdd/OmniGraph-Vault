# 共享回填预算的Flash价目与预留

2026-10-04读取[官方人民币价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。当前Flash高峰单价为每百万tokens：输入命中0.04元、未命中2元、输出8元。旧deepseek-v4-flash别名仍由当前Flash服务。回填入口显式指定该已授权别名，不改变daily配置或provider。

官方上下文为1M。[官方Chat Completions合同](https://api-docs.deepseek.com/api/create-chat-completion/)限制输入加输出总长度，并提供prompt/completion/total及cache-hit/miss tokens。现有客户端max_tokens=12000。

实现采用2^20=1048576作为整个1M窗口的保守输入上界，覆盖system/user和消息开销，不根据正文字符数猜token数。以整个窗口未命中输入加12000输出计算：`1048576×2/1000000 + 12000×8/1000000 = 2.193152元`。向上取整到整数分，单调用预留220分。未从上下文窗口扣除输出，留有进一步余量。

结算使用实际tokens与已保存的命中/未命中细分，统一按官方高峰单价并向上取整到分。**这是费用上界，不是提供方精确扣款。** 如果旧回执缺缓存细分，将实际全部输入按未命中计上界，并标cache_usage_observed=false。周末/空闲低价不用于减少本轮预留或结算上界，避免跨时段和节假日判定产生低估。历史回执缓存只读取复用，不倒计入这次100元预算。

实施或扩大真实回填前，owner需重新核官方价目、适用模型与客户端输出上限。当前price snapshot固定为2026-10-04。账本中的snapshot与代码不一致时停止，保留旧数据，不自动改费用或重置预算。

## 最小启用步骤（本切片未执行）

1. 项目主控独立验收源码、临时根回执和定向测试。保留29条unresolved，不promote494候选。确认选定的两条来源、修订、筛选资格及实际原文，不用K0旧计数代替现场选择。
2. 在既有运行owner的同一运行根，使用现有refresh CLI的 `--backfill --backfill-lane K` 或D，并给出两条显式 `--select source:id`、`--use-existing-snapshot`及既有base-database/wiki-id。不改LaunchAgent，不在WSL启动第二producer。该显式模式首次进入同一refresh.lock后才创建唯一backfill-budget.json，额度10000分。本轮没有在生产根执行此命令。
3. 检查本批ledger entries的source revision/stage/recipe/prompt hash、request_id、预留与实际usage费用上界。出现unknown只读原ACK结果接续，不重发。产品校验失败已经发生的费用保持。余额不足停止该批，daily marker保持。

此接缝沿用原produce的两篇和Wiki路径，没有在本切片去除Harness主题限制、增加长文分块或完成多主题C/D产品工作。后续这些业务路径调用native_turn时必须传相同budget和来源/阶段身份，才能计入同一额度。
