# 内容补全预算

复用现有 `vitax/backfill_budget.py` 与运行根的 `backfill-budget.json`，总额100元，已发生费用继续累计。
同一入口持有 `refresh.lock`，成功缓存直接复用。请求结果未知先查原结果，避免重复付费。
预算不足保存进度并报警。批次汇总费用，主控无需逐请求批准或另建预算体系。
当前内容执行已暂停；源码位置与下一步见 [TDD](../../spec/VITAX_HOBBY_TDD.md)。
