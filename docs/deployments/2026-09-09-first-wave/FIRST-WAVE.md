# VitaX 首波账本与证据收拢

日期：2026-09-09。状态：进行中；本文件不构成部署、生产验收或全项目完成声明。

## 精确事实

| 工作项 | 当前事实 | 未完成或 UNKNOWN |
| --- | --- | --- |
| VX-003 | 本地与远端离线验收完成，部署脚本已安装。 | 真实定时同步未运行。 |
| VX-004 | **partial**：config 门已 local accepted；实验 Hermes text adapter 已获主控接受，完成本地 fake 测试和一次 OHPC 合成调用。见[真实 probe](../2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md)；七文件组合回归为 56 passed。 | 隔离单篇 E2E、完整残留恢复、发布站点和部署未完成。 |
| VX-005 | 三份 service 模板的 `--dry-run` 第一切片已获 accepted (local)，README 已更新。 | 未部署；完整残留恢复未实现。 |
| VX-006 | 原始失败证据保留；修正实验的 Codex/Hermes/tool-handoff 功能已 functional accepted。 | 该实验只做合成算术，不等于完整自动故障修复；四类权限拒绝未实现；resolved Codex model、attempt、fallback 为 **UNKNOWN**。 |
| DOC-001 | 规格工单初版已获主控接受；12 个工单的编号唯一且 DAG 已验。 | 全项目仍进行。 |
| Fermat | 已接受 experimental adapter 的 local + 一次 OHPC 合成 text-adapter 范围；证据见[真实 probe](../2026-09-09-hermes-adapter/REAL_ADAPTER_PROBE.md)。 | 非生产；不标记 VX-004 整项完成。 |

## 证据范围与偏差

- `vitax-config-isolation-evidence.md` 和 `vitax-prestart-test-evidence.md` 从 `/tmp` 复制前已做秘密模式检查；未发现匹配项。文件内容未在本次收拢中打印。
- VX-004 早期一次 config 组合测试漏加 `OMNIGRAPH_LOAD_ENV=0`，因此可能读取 `~/.hermes/.env`。该文件内容未打印；该命令不作为隔离证据。其后记录的最终命令显式设置该开关。
- 已对两份证据所描述的选定测试、`config.py` 与 `kb/config.py` 进行静态范围审阅；未见网络调用或生产写入。此为静态判断，不是运行时网络或生产环境验收。

## 本目录的修改范围

- 原样保留两份脱敏、离线测试证据副本；其来源 SHA-256 分别为 `948c180d33bcd2091d970dc7d4a7415ad9877c548abf7b49afabc917297aa97e` 与 `5660b4c12062efd7f7a7f94c605796f2af97349658ff2f586ed2130b523c0d8d`。
- 本汇总仅收拢已有主控事实与未决项；未执行远端命令、模型调用、部署、服务重启、采集或数据迁移。

## 后续阻塞

1. VX-004 的 config gate 与实验 adapter 已接受；后续由主控按现有计划划定隔离空 namespace、单篇 E2E 与验收范围。
2. VX-005 需设计和实施完整残留恢复，并在单独授权后执行部署验证。
3. VX-006 需修复完整故障路径、验证四类权限拒绝，并收集请求关联的路由账本后才能解析三个 UNKNOWN 字段。
4. 发布一致性合同、版本化云端发布和真实站点/FTS 均仍在后续工单中，不能由 VX-004 的实验 adapter 证据替代。
