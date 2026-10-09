# 100元共享回填预算：现有owner与最小接缝

最新状态：2026-10-04项目主控指定本内容主控为唯一工程owner，预算源码与零费定向验收已实施。运行owner、唯一运行根/refresh.lock不变。尚未创建生产费用账本或执行收费探测。K与主计划D共用同一100元，不增加额度。最新结果见REPORT.md预算源码章节、BUDGET-verification.json及CONTENT-BUDGET-PRICING.md。下方保留最初只读取证和方案作为实施依据，不再把owner确认当当前阻塞。

## 已核运行归属

- 活跃配置由 Mac LaunchAgent `com.vitax.local-refresh` 调度。`launchctl print gui/<uid>/com.vitax.local-refresh` 实测入口为本机 `.venv/bin/python scripts/refresh_vitax_local.py --root /Users/hai/Projects/ohpc-migration/vitax-candidate-runs/local-automation-20261002 --wiki-id legacy-harness ...`。观测时state=not running、runs=26、last exit code=0。进程退出0不证明费用或生产合同。
- 唯一运行根是 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/local-automation-20261002`。`refresh()` 在 `scripts/refresh_vitax_local.py:210` 进入，并在213–214行持有该根的 `refresh.lock`。该owner持有选稿、accepted缓存、模型调用及本地发布决策。
- 实际收费传输在 `native_turn()`，该文件90–143行。模型密钥归属仍是 `ack-node-2`。已有SSH回调在133行，远端结果缓存为 `/root/.vitax-local-automation/deepseek-turns/<tag>/result.json`。不迁移密钥，不在WSL新增producer。
- `produce()` 在173行复用已有 `accepted/<tag>/accepted.json`。`native_turn()` 在93–98行复用 `native-result.json` 并核prompt hash。远端在114–117行复用result并核prompt hash。模型成功、产品校验失败、构建失败应分别处理，不重复发请求。
- `production-day.json` 是按天调度/尝试标记。`production-failures.json` 是来源修订/阶段失败次数。它们没有人民币余额、费用预留或结算字段，不能冒充100元账本。
- 已检查本机运行根的top-level、native/accepted一级产物，以及远端准确运行根top-level和deepseek-turns结果数。远端hostname实测 `iZj1imk39yc55iZ`，12个已存result。本机读取27份usage文件、11份accepted文件，其中有native→accepted重复usage副本。尚未发现此范围内的回填费用账本。此结论不宣称扫描了全部主机。

证据：隔离目录 `K-next-owner-inventory.json`，以及本次报告中的源码行号和live launchctl/SSH观测。旧plist备份不作为活跃配置证明。

去重回执见 `K-next-cache-accounting.json`：20份DeepSeek usage副本对应9个唯一request_id，9个request均有重复副本。其余7份usage属于历史openai-codex，不纳入本轮DeepSeek回填。实际回填新增调用为0。这些历史token不是本次100元预算的自动支出。

## 必须补的计费字段

`lib/llm_deepseek.py:163–181` 调用目前有 `max_retries=0`、`max_tokens=12000`，成功回执有requested/returned model、request_id、prompt/completion/total tokens和output hash。`validate_completion_receipt()` 在143–160行只保留该白名单。没有cache-hit/cache-miss细分或人民币cost字段。native及accepted同请求的副本不能分别计费。

现有receipt能证明成功调用的身份及部分usage，不能直接证明按命中/未命中价格的精确人民币成本。本轮不引用或假设现行价格。进入收费实施前，owner必须核官方价目、计费币种及适用模型。若缓存细分拿不到，应明确采用实际总输入按已核非缓存价结算的保守上界，不将其写为精确扣款。优先保留提供方原始usage细分并延续output绑定校验。

## 最小实施建议

1. 由当前refresh owner在现有运行根维护**唯一** `backfill-budget.json`。K/D读取同一文件，不在内容主控目录或WSL另建账本。先确认项目主控和并行owner没有正在实现的同义账本，再落该单文件。总额使用人民币整数分10000。状态只包含budget_id、已结算金额、未结预留和按调用键索引的entries。
2. 复用现有 `refresh.lock`。仅在该owner持锁期间改变预算状态，用同目录临时文件和 `os.replace` 原子保存。不新增锁服务、队列或数据库。现有直接 `native_turn()` 调用方若未经过持锁预算路径，不允许新回填收费。
3. 在 `native_turn()` 检查本地成功缓存之后、远端收费请求之前预留。调用键使用全量来源修订、stage、recipe和prompt SHA256，绑定已有tag、远端结果路径及request_id。文章、翻译、分块、Wiki都进入同一backfill budget_id。日常调用明确标记daily，不能把历史usage副本自动算为本轮回填。
4. 预留金额按已核价目、输入量可靠上界和12000输出上限计算。现入口未提供输入token计量器。必须先确定兼容的可靠上界或现有实际token计量接缝，不能用字符数/4猜数。余额不足或调用量无法上界时不发请求。若owner选择逐阶段上限，明确记录它仍是同一100元额度的一部分。
5. 请求完成后，按request_id与实际usage结算一次。native和accepted中的同一request_id只结算一次。产物校验或发布失败不撤销已发生的费用。成功缓存命中不预留新费用，也不发模型请求。未知传输结果保留预留，先只读检查原远端result接续，不自动重发。
6. 每次持锁启动先检查未结预留与现有远端结果。未能确认结果的调用保持unknown，计入可用余额扣减。失败两次继续沿原来源修订/阶段隔离，不能因预算实现而清零。现有native失败缓存的按日期retry逻辑须在回填路径前检查结果与已有attempts，不能绕过unknown预留重发。

最小验证用现有 `test_refresh_vitax_local.py` 和合成回执/只读缓存：余额不足零请求，缓存命中零请求，同request副本只结算一次，成功生成但产品校验失败仍计费，未知结果保留预留，K/D共享余额，以及持锁重启后从原result完成结算。无收费probe。

## 归属与限制

工程owner是现有refresh/业务生产入口owner。内容主控只提供缺口、来源修订和优先级。凭据owner是原ACK生产机。未来部署G2迁移单owner时，预算文件、未结预留、失败次数与accepted/cache须一并迁移，不能同时启Mac/云两个写入owner。本轮不执行该迁移。

首个计费前置：项目主控尚需确认唯一账本owner和落点。落点建议复用当前运行根。随后补官方价目、usage缓存细分及可靠输入上界，再执行零收费回归。只有这些前置通过，后续切片才可考虑真实回填调用。
