# Hermes Dot 管家调研

日期：2026-10-04。状态：调研与提示词已交付，未配置 Dot、未创建新日程、未变更服务。入口：[可复制提示词](PROMPT.md)。

## 结论

适合让一个 Dot 承担跨服务观察、有限恢复、人工报警。复用 systemd、现有任务回执和原生日程。首版不开发监控平台、插件或事件服务器。

提示词可以讲清职责，不能代替电脑连接、工具权限、日程保存和通知送达验证。优先把长期可用的 Hermes 作为连接电脑，但必须先确认该设备支持和实际工具面。若当前 Dot 已连接 Mac，不自动切换，避免影响现有任务。经 Mac 的 OHPC SSH 路径会额外依赖 Mac 在线。

## 官方能力与实际边界

- Dot 在云端保持可用，使用个人电脑时仍要求电脑在线、ChatGPT app打开。一次只能连接一台个人电脑。Dot 的电脑授权与 Codex连接/Work Sync不同。云浏览器不继承 Hermes Edge 登录。[Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- 固定周期任务需要保存日程，并确认时间、时区、通知条件和发送位置。连接服务不等于已经订阅事件。后台任务也不会自动获得全部历史对话。[Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- 授权范围与平台审批继续生效，自定义规则不能赋予尚未连接的资源权限。[Controls](https://learn.chatgpt.com/docs/dots/controls)
- Dot对话额度与它管理的Work/Codex执行额度有区别，不能把全天代理理解成无限免费运维。[Meet dots](https://learn.chatgpt.com/docs/dots)

本轮没有验证这个账户的 Dot 设备接入、WSL工具、日程或手机通知。30分钟是建议的巡检周期，不是产品保证的故障发现SLA。断电、桌面客户端关闭、权限过期或通知渠道故障都会形成覆盖缺口。先完成一次真实接入与提醒测试，再声称已启用。

## Hermes 新鲜证据

通过既有 `ssh OHPC` 只读采样，hostname为 `OH-Desktop`。主快照 `2026-10-04T20:31:40.453362+00:00`，即 Halifax 17:31。只读取 systemctl 属性与HTTP健康端点，不调用业务模型、不触发采集、发稿或恢复。

| 对象 | 实测 | 能证明 / 不能证明 |
|---|---|---|
| Edge CDP `127.0.0.1:9223/json/version` | HTTP200，Edg/155.0.4283.33 | 浏览器传输可达；公众号登录与全文抓取未验 |
| `playwright-mcp.service` | active/running，NRestarts=1 | 进程存在；真实浏览器工具操作未验 |
| `aliyun-tunnel` / `omnigraph-tunnel` | 均 active/running | 隧道进程存在；云端全链路未在本轮重验 |
| `ai-daily-n8n` / `ai-daily-caddy` | 均 active/running | 服务存在 |
| n8n health/readiness | 两者HTTP200 | 不能替代工作流执行、投递或发布验收 |
| `ai-daily.timer` / `ai-daily.service` | timer active/waiting；service Type=oneshot、inactive/dead、Result=success | 批次间停驻不是故障；工作流启用与暂停清单未知 |
| `hermes-gateway` / `opencodex-proxy` | 均 active/running | 真实消息处理和模型请求未验 |
| `vertex-proxy.service` | activating/auto-restart、Result=exit-code、ExecMainStatus=203、NRestarts=92107 | 异常重启持续存在，不能由此推断仍有业务依赖 |
| `workforce-demo.service` | active/running | 演示服务；是否应常驻待确认 |
| `qwen3.8-27b.service` | disabled、inactive/dead | 不自动当故障，不恢复启动 |

vertex重启计数在本轮连续读取为92059→92091→92107，原属性RestartUSec=5秒。相比只看累计值，计数增长确认仍有反复重启。未读取可能含敏感参数的ExecStart或完整日志，未裁定203的具体配置根因。该异常也曾记录在部署基线，不能套用别台主机旧issue的解决状态。

同轮较早读到 system `omnigraph-daily-pull.timer` 有下一次调度、最近oneshot成功；Docker运行n8n sandbox API/runner及buildkit。这里只登记存在，不据此声称最新文章、图谱和图片已全量同步。

AI Daily的远端AGENTS与README也已读取。README明确 completion receipt 是一次有发送副作用的操作，因此禁止用它作无害探针。当前n8n健康不能推断所有编辑或发布工作流已开启。

## 与现有生产任务分工

VitaX生产仍跨Hermes、两台ECS和Mac，参见[部署基线](../../deployments/VITAX_DEPLOYMENT_BASELINE.md)及[当天部署调研](../2026-10-04-aliyun-deployment/REPORT.md)。本轮没有重新审计两台ECS及Mac站点全链路。

内容轨道的既有主控和 `vitax` heartbeat继续拥有派工、业务预算和内容验收职责。Dot观察后向已有负责人报告，不开第二个producer。

本轮收到内容主控报告：首批3次真实调用已经发布，但Wiki自由正文有5个引用无法在同版证据中解析。状态为 `BLOCKED_CITATION_CLOSURE`，不能因结构字段或API读取通过就接受K3/K4。主控已停止新增收费。本任务没有复验或修复这些内容；见[内容报告](../../work-items/vitax-content/REPORT.md)。这是业务质量报警的具体例子，而非自动重启适用场景。

## 最小落地与验收

1. 在Dot中接通选定电脑，验证目标hostname和实际WSL/SSH工具。不要把已有Codex远程连接视为Dot授权。
2. 交付提示词，完成只读基线、期望状态与未知项。保存唯一巡检日程并读回。
3. 在用户本人渠道发一次明确标注的测试提醒。区分消息写出和终端实际收到。
4. 先验证正常oneshot、disabled服务不误报。用既有vertex异常验证单次报警与去重，不制造故障。
5. 自动恢复只适用于提示词中三个明确服务与全部前置条件；首轮不重启。未证明闲置/上游可用/管理通道独立就转人工。

文档验证：检查新增文件、相对链接和空白错误。未运行产品测试，未声称Dot已上线或24小时可靠性已经验证。
