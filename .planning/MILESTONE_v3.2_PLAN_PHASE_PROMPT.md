# Milestone v3.2 — GSD Plan-Phase Kickoff Prompt

> **用途：** 在新 Claude session 中粘贴这份提示词（全文），然后运行下方的 `/gsd:plan-phase` 命令，完成 v3.2 的 6 个 phase 规划。
> **生成时间：** 2026-04-30
> **上游产物：** `.planning/MILESTONE_v3.2_REQUIREMENTS.md`（需求文档，24KB，已冻结）

---

## === 粘贴以下全部内容到新 session ===

我要对 OmniGraph-Vault 项目的 Milestone v3.2（Batch Reliability + Infra）进行 GSD 规划。请先读取以下上下文，然后按照我指定的 Phase 编号和决策锁定，执行 `/gsd:plan-phase` 工作流。

### 前置阅读（必读，按顺序）

1. `CLAUDE.md`（HIGHEST PRIORITY PRINCIPLES + Architecture + Lessons Learned）
2. `.planning/MILESTONE_v3.2_REQUIREMENTS.md` — v3.2 完整需求文档（scope B1–B5 + Phase 12）
3. `.planning/ROADMAP.md` — 项目全局阶段与 v3.1 phases 8–11
4. `C:\Users\huxxha\.claude\plans\merry-discovering-moonbeam.md` — Milestone v3.1 完整 plan（v3.2 的直接依赖）
5. `.planning/phases/07-model-key-management/07-CONTEXT.md` + `07-REQUIREMENTS.md` — 最近一次 GSD 规划的格式参考

### 决策锁定（不需要重新讨论，直接进入 plan 工作流）

#### 1. Milestone 组成
Milestone v3.2 = 批量可靠性 + 基础设施，共 **6 个 phase**，按顺序编号 **Phase 12–17**：

| Phase | 代号 | 目录名 | 内容 | 预估工时 |
|---|---|---|---|---|
| 12 | B1 | `12-checkpoint-resume` | 5 阶段 checkpoint 数据结构 + resume 逻辑 | 2–3 天 |
| 13 | B2 | `13-vision-cascade` | SiliconFlow → OpenRouter → Gemini 三级 cascade + 熔断器 | 1–2 天 |
| 14 | B3 | `14-regression-fixtures` | 5 个 fixtures + `validate_regression_batch.py` + JSON 报告 | 1 天 |
| 15 | B4 | `15-docs-runbook` | CLAUDE.md 更新 + `OPERATOR_RUNBOOK.md` + `DEPLOY.md` 补充 | 1–2 天 |
| 16 | B5 | `16-vertex-ai-design` | `docs/VERTEX_AI_MIGRATION_SPEC.md` + SA 模板 + 成本估算脚本（纯设计，无代码改动） | 0.5–1 天 |
| 17 | Ph12 | `17-batch-timeout-management` | 批量总耗时跟踪 + 单篇/批量联动 + checkpoint flush 交互 + 监控指标（仅规划，实现留 post-v3.2） | 1 天 |

> **注：** 原提示词里的 "Phase 12" 在此按顺序编号为 Phase 17，避免与 v3.1 的 phases 8–11 冲突。

#### 2. 依赖锁定（与 v3.1 的接口）

Milestone v3.2 **gate-passing 前提**：v3.1（Phases 8–11）必须 gate-passing。v3.2 直接依赖的 v3.1 产物：

- **来自 Phase 8**：`image_pipeline.filter_images()`, `describe_images()` with per-image logging, `_DESCRIBE_INTER_IMAGE_SLEEP_SECS=0`
- **来自 Phase 9**：`ingest_article(..., timeout_budget=...)`, `get_rag(flush=True)`, `asyncio.wait_for` 包装，单篇 timeout 公式 `max(120 + 30*chunk_count, 900)`
- **来自 Phase 10**：`_vision_worker()` async callable, text-first `ainsert()` contract
- **来自 Phase 11**：`scripts/benchmark_single_article.py` 验证脚本 + `benchmark_result.json` schema

#### 3. 并行策略

- Phase 15（B4 docs）和 Phase 16（B5 Vertex AI 设计）**无代码依赖**，可与 v3.1 执行并行启动
- Phase 12（B1 Checkpoint）设计阶段可在 v3.1 Phase 9 完成后即启动
- Phase 13（B2 Cascade）、Phase 14（B3 Fixtures）需等 v3.1 整体 gate-passing 后才能集成测试
- Phase 17（批量超时）依赖 Phase 12 checkpoint API 成型后才能定稿

#### 4. v3.2 Milestone Gate 标准（6 项）

1. 56+ 文章批量 ingest 零未处理异常
2. 瞬时失败（Vision 503 / 网络超时）可自动恢复，不重新 scrape 已完成阶段
3. 5 个回归 fixture 全部通过（multi-image / sparse-image / text-only / mixed-quality / gpt55）
4. `CLAUDE.md` + `OPERATOR_RUNBOOK.md` + `DEPLOY.md` 三份文档齐全
5. SiliconFlow 余额预警在关键 checkpoint 触发（当前 ¥5.43，263 篇需 ¥9.5 → 不足）
6. Vertex AI SA 凭据模板 + quota 隔离设计文档完成（实现延后）

---

### 执行指令

请对以下 6 个 phase **逐个**运行 `/gsd:plan-phase`，每个 phase 产出：

- `.planning/phases/{NN-name}/{NN}-CONTEXT.md`（决策锁定 + 5–15 条 D-xx）
- `.planning/phases/{NN-name}/{NN}-PLAN.md`（任务分解 + 验证循环）
- 需要时补 `{NN}-REQUIREMENTS.md`（从 `MILESTONE_v3.2_REQUIREMENTS.md` 摘录对应 B-段）

**推荐执行顺序：**

```bash
# 先从文档类（无代码依赖）开始，并行度高
/gsd:plan-phase 15 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive
/gsd:plan-phase 16 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive

# 再做核心可靠性
/gsd:plan-phase 12 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive
/gsd:plan-phase 13 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive
/gsd:plan-phase 14 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive

# 最后做批量超时（依赖 Phase 12 API 成型后的设计）
/gsd:plan-phase 17 --prd .planning/MILESTONE_v3.2_REQUIREMENTS.md --skip-research --interactive
```

> `--skip-research` 已在 REQUIREMENTS.md 中涵盖核心研究；`--interactive` 让你对每个决策点确认后再落盘。

### 互动协议

每个 phase plan-phase 启动时：

1. **先汇报当前 phase 目标 + 对 v3.1/其它 v3.2 phase 的依赖清单**
2. **列出 PRD 里待决策项（最多 10 条）+ 你的建议默认值**
3. **一次提问一批决策**（批量 4–5 条，不要一条一问）
4. **我确认后，写 CONTEXT.md + PLAN.md + VERIFICATION.md**
5. **每个 phase 结束前：Git commit 规划产物**（`docs({phase}): plan phase {NN}`）

### 编码约束（从 CLAUDE.md § HIGHEST PRIORITY PRINCIPLES）

- **Simplicity First**：v3.2 是可靠性 + 文档，不引入新抽象；checkpoint 就是 5 个文件，不要搞状态机框架
- **Surgical Changes**：只改 batch 路径（`batch_ingest_github.py`, `ingest_wechat.py` 的 batch 分支）+ 新建 `lib/checkpoint.py`；不碰单篇 fast-path 核心
- **Goal-Driven**：每个 phase PLAN.md 必须写出 "验证指令"（具体命令 + 预期输出 + gate 条件）

### 已知约束（来自 CLAUDE.md）

- `DEEPSEEK_API_KEY` 必须设置（Phase 5 eager import 副作用），即使 Gemini-only 也需 `DEEPSEEK_API_KEY=dummy`
- 所有 checkpoint 写入用原子写：`write .tmp then os.rename()`（与 `canonical_map.json` 同模式）
- 运行时数据路径是 `~/.hermes/omonigraph-vault/`（typo 是 canonical 的，不要"修正"）
- MCP 工具只能在 main session 调用，不能 delegate 给 sub-agent（Databricks proxy 限制）

---

### 开始

请先读取前置 5 份文档，然后回复："📋 准备好开始 Phase 15 规划（B4 docs-runbook，最无依赖，适合首发）"，等我确认后进入 interactive plan-phase 工作流。

## === 粘贴结束 ===
