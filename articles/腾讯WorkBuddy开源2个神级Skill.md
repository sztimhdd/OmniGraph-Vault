# 刚刚，腾讯WorkBuddy开源了2个神级Skill

> 来源：微信公众号 PaperSkill  
> 作者：学长阿珑  
> 原文链接：https://mp.weixin.qq.com/s/KOlERMmvHjF_KHjJo-hUZw

---

大家好，我是学长阿珑

今天分享腾讯WorkBuddy团队最新开源的2个Skill：**wbbench-report-skills**，**wbbench-run-setup**

先说下WorkBuddy Bench，它是 WorkBuddy 产品工程实践的副产品——腾讯把内部用于模型选型、Harness 回归测试和任务分布分析的那套体系，整体打包成了一个开源基准测试。

把多模型 Agent 工作台在选型上的底牌摊到了台面上：**GLM-5.2 在安全场景下完胜闭源模型，GPT-5.5 的 token 消耗最低，Claude Opus 综合能力最强**——这三项结果恰好说明了 WorkBuddy 为什么选择多模型动态切换，而不是死磕自家的混元。

但榜单数字不是这篇的重点。重点是他们为了让别人也能复现这套选型，在仓库的 `.agents/skills/` 下放了两个 agent skill——一个管把评测跑起来，一个管把报告写对。你在 Claude Code 或 CodeBuddy Code 这类 skill 感知的客户端里一句话唤起，它就一阶段一确认地带你跑完整轮评测。

真正值钱的不是基准本身那 260 道任务（Code 80、Web 70、Office 50、Security 60），而是这两个 skill 把跑评测和写报告里最容易踩的坑，直接固化成了 agent 能执行的 playbook。

WorkBuddy Bench 四子集总览

而仓库里这两个 skill 的分工很干净：**wbbench-run-setup** 负责把评测跑起来，**wbbench-report-skills** 负责把报告写对。一个管跑，一个管分析。

---

## Skill 1：7 阶段把评测跑起来，顺手把坑填了

**wbbench-run-setup** 是一个 7 阶段（0 到 6）的交互式 playbook，从零配置的 checkout 一路带到跑完分析：

| 阶段 | 内容 |
|------|------|
| 0 | 拉数据集 |
| 1 | 配环境 |
| 2 | 写模型配置 |
| 3 | 填 `.env` 凭据 |
| 4 | 写 job 文件 |
| 5 | dry-run 确认后跑 |
| 6 | 交给 report skill 出报告 |

wbbench-run-setup 七阶段流程与避坑要点

它的设计有几条反常识的硬规矩：
- **读实时模板**，不靠记忆里的字段名
- **运行时发现选项**，不硬编码可能过时的列表
- **一阶段一确认**，而且全程用你的语言回复

也就是说，skill 不会因为模板演进了还拿旧字段糊弄你。

---

## Skill 2：把报告写对，比跑出来更难

**wbbench-report-skills** 路由 Office、Web、Code 三个 benchmark 的报告生成。它的第一步不是分析，而是**先甄别你给的 RUN_DIR 到底是哪一层**。

### Harbor 目录三层结构

| 层级 | 特征 | 用途 |
|------|------|------|
| JOB | 只有时间戳子目录，无 `job.log` | 批量任务 |
| **RUN** ✅ | 有 `job.log` + `<task>__<attempt>/` 子目录 | **单次评测运行（这才是正确层）** |
| TRIAL | 有 `trial.log` + `verifier/` | 单道题 |

选错了层，整份报告就错了。skill 明确：**选不出唯一候选就回头问你，绝不猜默认路径。**

甄别完，三步生成报告：
1. 校验 `RUN_DIR`
2. 跑 `workbuddy_bench.scorer.metrics` 生成 `metrics.json`
3. 写 `report.md`

输入产物全程只读，只往 `REPORT_DIR` 写东西，不动 Harbor 原件，也不重跑昂贵的评测。

wbbench-report-skills 工作流与报告卫生

### 报告卫生守则

**reward ≠ pass_rate，不能混：**

| 指标 | 定义 | 计算方式 |
|------|------|----------|
| reward | 主分 | 每任务 reward 的均值，build_error 记 0 进分母 |
| pass_rate | 整题全过率 | verifier 得分 ≥ 1.0 的 trial 占比 |

一个衡量平均做对多少，一个衡量整题全过的比例。

**另两条硬规矩：**
1. **Rule-only 和 Rule+Judge 评分契约不同，不能直接比** — Office 任务用 CompositeVerifier，配了 LLM judge 路由才有 Judge 分，没配就只有 Rule 分
2. **每个判断必须绑 task id + 证据**，不能只甩个均分。连只改测试、不动产品代码的改动都不算有效修复，除非任务本身就是 Test Generation

---

## 论文与仓库

- **论文：** *Tencent WorkBuddy Bench: A Multi-Domain Coding-Agent Benchmark with Contamination-Resistant Task Construction*
- **arxiv：** [2607.20911](https://arxiv.org/abs/2607.20911)
- **GitHub：** <https://github.com/Tencent/workbuddy-bench>
