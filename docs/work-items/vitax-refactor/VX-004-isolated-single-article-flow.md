# VX-004 — 真实来源到知识包与 Wiki 更新

[KNOWN] 当前合同按 [ADR 0004](../../adr/0004-minimal-knowledge-product.md) 与[产品计划切片2](../../superpowers/plans/2026-09-09-vitax-product-architecture.md)执行。下方历史合成测试仅作复用证据，不是当前验收清单。

**What to build:** 一篇真实来源经抓取、标准化与 Hermes 加工，形成带证据的文章解读、Wiki 更新、实体关系与选图结果，并能通过公开读模型查询；逐步扩至代表样本。
**Blocked by:** VX-007 公开读模型子切片用于末端验收；来源/知识生产可独立开发，不依赖 Prefect、VX-001 全量漂移、VX-005 旧链恢复或引擎选型。
**Status:** partial — 两源真实知识生产、跨来源Wiki与同版候选读库切片已接受；代表样本与旧数据导入未完成。

## 最新验收：2026-09-10两源闭环

[KNOWN] 用户重新授权自主诊断后，定位旧错误为内部non-streaming 90秒stale watchdog，修正了失败/缺路由误包装、parent_timeout标签、Hermes合法service_tier=None处理，以及usage无效时丢失正文的问题。54项相关测试通过。仅候选进程设置stale360，保留run720及其余保护；未改全局配置或模型路线。

[KNOWN] 复用首篇，第二篇GraphRAG与Wiki的真实Hermes调用均成功并保留原始输出、实际usage/init。独立审阅接受7条文章知识＋1篇跨来源Wiki、14实体、11关系、50证据；21条Wiki引用覆盖两来源，最终全部证据匹配原文。新SQLite与projection一致，24份四类fresh读取结果非空且属于release `release-20260910t021435z`，搜索命中Wiki。此为两源候选验收，不是站点或生产日更验收。

[KNOWN] 证据根：`/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/`。关键文件：`wiki-output/`、`wiki-public.sqlite`、`wiki-validation/receipt.json`、`review.md`。人工保护由现有拒绝覆盖/同源人工模型共存测试覆盖，不主张真实旧库迁移已完成。

[INFERRED] 下一主线为VX-009站点/API/MCP复用这份真实release；代表来源扩展、旧资料导入与生产日更仍按原计划分别验收。下方失败记录保留为历史，不再表示当前阻塞。

## 2026-09-09真实运行进展

[KNOWN] 入口为 `vitax.production`，见[运行说明](../../LOCAL_REAL_PRODUCTION.md)。OHPC独立候选抓取两篇官方2024文章，来源发布时间与本次抓取时间分别保存。首篇Contextual Retrieval实际GPT输出产生3条解读、7实体、5关系、18证据、4个选图；独立内容审阅通过。离线修正来源caption后构建release `release-20260909t231137z`，search/read-knowledge/related/read-evidence四个新进程结果绑定同版。此为1个来源，不是3篇文章。

[KNOWN] GraphRAG首个CLI请求实际路线偏离，产物标记UNACCEPTED；改用同一Hermes原生入口、禁用fallback与工具后，真实初始化通过，但第二次模型调用以timeout失败，未生成accepted/projection。未换模型、不进行第三次盲重试。CLI还存在辅助标题模型调用，已记录在原始usage补证中；不能声称本轮所有调用均仅使用GPT。

[KNOWN] 原始与脱敏证据在 `/tmp/vitax-real-production-20260909T215150Z/remote-worker/`：`first-release/`为已接受单源候选，`real-graphrag-v12-attempt2/`为失败产物，`native-fixed/check-only-result/`仅证明初始化。完整跨来源Wiki、最终两源读库、站点、日更、生产与旧数据导入均未验收。临时目录不是长期备份；既有原始资料和生产库未迁移。

[INFERRED] 下一步先根据已保存timeout证据恢复同一路线的有界Hermes运行，再复用首篇与第二篇产物生成Wiki；不通过重复旧合成probe或扩大框架来替代该闭环。

[KNOWN] 本轮长期本地证据入口已移到源码之外的 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/20260909T215150Z/CURRENT.md`；旧/tmp路径仅为原始捕获位置。新输入路径、单源候选读库与失败断点均在该索引中。

## 当前验收

- [ ] 来源身份与抓取事件、文章修订分离，正文/表格/图片有定位。
- [ ] 实际 Hermes 输出保存为知识版本，引用可核实，错误/冲突不伪报成功；不新增付费fallback。
- [ ] Wiki 能合并多来源、记录修订，保护已有人工内容；复用旧校验而非照搬旧建议-only政策。
- [ ] 关键原图按价值选择，caption标明出处；图片与正文定位可验证。
- [ ] 公开投影可构建、文章/Wiki可读取，关系可追溯至同一公开release证据。
- [ ] 小批旧文章/已接受解读/Wiki可进入同一合同；缺失历史字段不编造，旧数据不改写。
- [ ] 只对真实失败的解析或语义步骤做对照；不重跑已通过合成probe代替产品进展。

**执行边界：** 只写主控派工的互斥路径；保护原始数据与无关 WIP，不自动 commit/push。远端写入须绑定具体候选/生产任务、当前主机与源码验证，ADR 0002 四类例外始终有效。

## 历史记录（保留原验收范围，不作为新前置）

[KNOWN] 2026-09-09重新定向：下一切片依据[产品架构计划A-B](../../superpowers/plans/2026-09-09-vitax-product-architecture.md)，围绕独立文章revision与证据知识产物重建真实流程。旧入口及下面历史切片不构成新实现的兼容要求；优先贯通真实文章到私有预览，不新增旧链probe。

**What to build:** 合成单篇输入从发现到查询、图和 Wiki 候选可关联验证。

**Blocked by:** None — can start immediately.
**Responsibility:** coder + uat. **Status:** partial — config 门和 experimental Hermes text adapter 已获主控接受；整项隔离单篇闭环尚未验收。

**Accepted scope:** config.py、tests/unit/test_config_env_loading.py 的 local config gate，以及 lib/llm_hermes.py、lib/llm_complete.py、tests/unit/test_llm_hermes.py 的 experimental adapter local + 一次 OHPC 合成 text-adapter 调用。后续独立空 namespace、单篇 E2E 和发布动作由主控按现有计划划定派工范围。
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [ ] 合成单篇输入从发现到查询、图和 Wiki 候选可关联验证。
- [ ] 在执行生产闭环前，明确验证 config.py、凭据加载和网络入口不会读取共享默认 runtime 或 ~/.hermes/.env。
- [x] OMNIGRAPH_LOAD_ENV 未设置或为 1 时保持既有加载行为；显式 0 时禁止读取 ~/.hermes/.env；非法值 fail closed。`OMNIGRAPH_LOAD_ENV=0` 下 18 个组合离线测试重跑通过，20 项 manifest SHA 通过；Curie 限定复审 PASS。
- [x] config 门只经离线 TDD 验证，不构成完整隔离、部署或生产授权。
- [x] experimental Hermes text adapter 已完成 local fake 测试和一次 OHPC 合成调用；[真实 probe](../../deployments/2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md) 记录严格两行返回、usage allowlist 与七文件 56 passed 组合回归。
- [ ] 空 namespace 不使用共享默认 runtime，且其隔离完成证据已通过主控审阅。
- [ ] 完整残留恢复、发布一致性合同与真实站点发布相关工单的独立验收。
- [ ] 同步失败不阻塞本独立验证；重跑不重复，失败不误报。

## 执行附件

```bash
rg -n 'load_dotenv|\.hermes/.env|OMNIGRAPH_BASE_DIR|RAG_WORKING_DIR' config.py scripts/probe_e2e_v3_2.py tests/unit
sed -n '1,220p' config.py
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_config_env_loading.py -q
```

**Tests:** `test_config_env_loading.py`、`test_config_base_dir_override.py` 与 `tests/unit/kb/test_config.py` 的组合离线运行已在 `OMNIGRAPH_LOAD_ENV=0` 下重跑为 18 passed，20 项 manifest SHA 通过。命令必须显式前缀该开关。早期一次测试漏加该开关，可能读取 `~/.hermes/.env`；未打印其内容，且静态审阅未见网络或生产写入。仅在主控确认完整隔离后，记录后续合成闭环与目标回归命令。
**Evidence:** [首波证据](../../deployments/2026-09-09-first-wave/vitax-config-isolation-evidence.md)、[实验 adapter 真实 probe](../../deployments/2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md)、隔离审计、主控确认、输入 ID、namespace、正文处理/翻译、图/Wiki 候选、图片 caption 来源、公开查询引用。

## 第二阶段执行

预检布局已交付；不等于已执行隔离入库。见[第二阶段报告](../../deployments/2026-09-09-second-wave/SECOND-WAVE.md)。

## 第三阶段真实固定文本

2026-09-09：OHPC候选已完成两次缓存文本入库及两次新进程查询，receipt记录1 chunk、8 entities、8 relationships，重跑不增生，4次Hermes completion，查询端0次。该结果仅覆盖NanoVectorDB固定合成缓存文本；embedding经临时隧道复用旧云BGE-M3。抓取、分类、翻译、图片、Wiki与生产Qdrant均未验收，整项继续partial。见[运行报告](../../deployments/2026-09-09-single-article/RUN.md)。

主控最终接受上述固定文本切片，独立26字段对照与来源关联通过。重复提交产生的dup-* failed诊断已解释并保留；不是目标文档失败，但不代表故障恢复/状态库清理已完成。下一子步骤为Wiki候选，不重跑已通过模型探针。

## 第四阶段 Wiki 候选

[COMPUTED] 2026-09-09：主控接受从上述已落盘样本派生的 Wiki 候选。复用 W3 adapter/assembler/engine，远端单次 APPLIED、exit 0；3项实际核心测试通过，独立核对输入20文件未变、文档→来源→页面摘录/引用关联通过。使用确定性正文摘录，无新增模型调用。候选不是公开发布或生产自动 hook 验收，VX-004 继续 partial；下一步为真实来源抓取/清洗/翻译/关键图片。见 [Wiki 验收](../../deployments/2026-09-09-wiki-candidate/ACCEPTANCE.md)。
