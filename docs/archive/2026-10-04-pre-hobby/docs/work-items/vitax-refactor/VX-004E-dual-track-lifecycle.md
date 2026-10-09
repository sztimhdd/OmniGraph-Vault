# 有界双轨采集处理与翻译可对账

**Status:** ready-for-agent / authorized。  
**Blocked by:** None。  
**Risk / controller:** L / 可写6.1-Sol票级主控，Luna定向取证/测试、Sol复审，无孙。

**What to build:** 微信/RSS各正常记录在一个受限批次得到完整处理并保存结果；同源状态与失败/翻译阶段真实对账，不让一轨长期占满预算。

- [ ] 有限批次包含双源，源内FIFO/8列/当前拒绝与failed保护不变
- [ ] 已存正文优先复用、成功和部分失败持久化，翻译未完成不称完成
- [ ] 已有名单/定时/10条处理与20号×2页扫描预算不扩
- [ ] 针对RED→GREEN与同preimage生产读回，后续原timer结果可核

实施接缝/命令见[本轮计划](../../superpowers/plans/2026-10-02-vitax-local-automation.md)，范围与接受边界见[规格](../../spec/VITAX_LOCAL_AUTOMATION_SPEC.md)。关联既有#93–#99、VX-004/005/009/011；不再新建同义问题。用户已授权规划后执行，遵守同branch两失败与10%预算，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT。
