# 260710-health-audit — OmniGraph 全管线健康体检报告

**Quick ID:** 260710-u67 (dir pinned to goal-specified `260710-health-audit/`)
**Audit window:** 2026-07-11 08:45–09:05 CST（阿里云时间）/ 2026-07-10 21:45–22:05 ADT
**Mode:** 只读取证。零 systemctl 变更、零文件修改、零 kill。所有 sqlite 查询走 `file:...?mode=ro`。
**Auditor:** Claude Code (local session), SSH alias `aliyun-vitaclaw`

---

## 总结论（L4）

**用户"ingestion 管线已恢复正常"的声称：基本成立（as of 2026-07-11 06:28 CST）。**

恢复的实际发生链（由 GitHub 新 commit + journal + 备份文件时间戳交叉证实）：

1. **Jul 10 ~19:00 CST** — WeChat MP API session 过期（31 天寿命），15/15 扫描账号 `ret=200003`，管线上游断供。
2. **Jul 11 04:00 / 06:00 CST cron** — Layer1 仍在用 Vertex `gemini-3.1-flash-lite-preview`，该模型 404 NOT_FOUND，270 篇候选全部 NULL，"nothing to ingest"（连续两个 no-op cron）。
3. **Jul 11 06:19–06:28 CST** — 操作者（Hermes agent, 见 `docs/HANDOFF-2026-07-11.md`）完成三件事：
   - Mac CDP 提取新 TOKEN+cookie 写回 `kol_config.py`（备份 `kol_config.bak2.py` @ 06:19）
   - Layer1 从 Vertex Gemini 切到 DeepSeek（commit `cb42271`，阿里云以工作区热补丁形式部署，diff 与 GitHub 逐字节一致 ✅）
   - mcp-tunnel 单元加 9222/58932 端口转发（Jul 10 21:22 CST 编辑 + daemon-reload）
4. **Jul 11 08:00 CST cron（修复后第一枪）** — Layer1 DeepSeek 分类 238 篇（219 candidate / 19 reject / 8 NULL 待下轮）、Layer2 判 211 篇 ok、去重跳过 204 篇（checkpoint 已入库）、**实际新入库 5 篇 ok**、graphml 增长至 39,909 节点 / 58,634 边（mtime 08:41，当场在写）。

管线主链（scan → L1 → L2 → scrape → vision → ainsert → graphml）**已端到端打通**。但体检发现 **1 个红灯 + 5 个黄灯**（见下）。

---

## L1 — 用户 drift 发现 【WARN】

### live units vs repo `deploy/aliyun/systemd/`（38 个文件全量 diff）

| 单元 | 状态 | 内容 |
|---|---|---|
| 33 个 service/timer | ✅ IDENTICAL | 与 repo 逐字节一致（忽略首尾空白） |
| `omnigraph-mcp-tunnel.service` | ⚠️ DIFFERS | **本次用户运维的核心改动**：`-L 8931` → `-L 8931 -L 9222 -L 58932`（Mac Brave CDP + ohca proxy 转发），文件 mtime Jul 10 21:22。repo 未同步。 |
| `omnigraph-daily-digest.service` | ⚠️ DIFFERS（旧 drift） | ExecStart 换成 `export_vitaclaw_agent_news.py --output .../agent-news.json`（喂 vitaclaw-site）。文件 mtime May 25 — 非本次改动，长期未回写 repo。 |
| `omnigraph-{afternoon,evening}-ingest.timer` / `kol-scan.timer` | ✅（已知 drift） | 均 disabled（260624 freq-up 合并到 daily-ingest every-2h），仅注释/Requires 行差异 |
| `omnigraph-translate.{service,timer}` + override | ⚠️ NOT IN REPO | 260528-mi6 时代的历史缺口，live-only。override 把 `--limit 20` 提到 `--limit 50` |
| `omnigraph-{afternoon,evening}-ingest.service.d/override.conf` | ⚠️ NOT IN REPO | Qdrant 环境 + RuntimeMaxSec=10800（daily-ingest 的 override 在 repo 且一致，另两个不在） |
| `omnigraph-vertex-proxy-env.conf` | ⚠️ 孤儿文件 | `ALL_PROXY=socks5h://127.0.0.1:18080`（已退役的 SOCKS5 代理残留）。**全 /etc/systemd/system 无任何单元引用它** — 无害但应清理 |

### 手动运维痕迹（journalctl + 备份文件）

- **Jul 8 23:28 CST** — daemon-reload ×4（对应 7/8 zombie vertex-proxy 清理，时间线已知 ✅）
- **Jul 10 21:22 CST** — mcp-tunnel Stopping + Reloading（单元编辑 + 重启，本次运维）
- **Jul 11 06:19 CST** — `kol_config.bak2.py` + `kol_config.old.20260711.py`（cookie 刷新备份）
- **Jul 11 03:20 CST** — `scripts/rewrite_body_cron.py` 落盘阿里云（SCP，kb-v2.3 D-14）
- `/root/omnigraph-vertex-proxy.service.bak-pre-l9g-260707` 等历史备份健在，无异常删除

### 阿里云 git 状态 ⚠️

- `main...origin/main [ahead 28]` — **假象**：origin ref 陈旧（443 阻断 fetch），28 个"ahead" commit 实际都已在 GitHub。HEAD=`a5d3694`，落后 GitHub 3 个 commit（`6ff947f`/`cb42271`/`b786d19`）。
- `lib/article_filter.py` 以 **未提交工作区修改** 形式携带 cb42271 内容（diff 验证逐字节一致）。下次在阿里云 `git pull/merge` 会因本地修改报错 — 需要先 stash/checkout（内容一致，无冲突风险）。

---

## L2 — 依赖健康 【WARN】

| 依赖 | 结果 | 证据 |
|---|---|---|
| **WG wg-gcp-sg** | ✅ PASS | handshake=1783731397（epoch，= 探测时刻新鲜）；transfer rx 224MB / tx 84MB；`ip route get 74.125.20.95 → dev wg-gcp-sg src 10.0.0.2` |
| **Google 直连** | ✅ PASS | `curl -4 oauth2.googleapis.com` → **404 @ 0.23s**（快速非超时，走隧道） |
| **Vertex embedding** | ✅ PASS（运行态 ⚠️） | 冒烟 `EMBED OK dim=3072`。但 08:00 run journal 中 **Vertex embedding 429 RPM/RPD 风暴**（26h 内 41 条 402/429/traceback 类日志，全部为 429 quota；retry 后成功，未丢数据，拖慢批次） |
| **DeepSeek** | ✅ PASS | max_tokens=5 测试 → `deepseek-v4-flash` 返回 "ok"，finish_reason=stop，非 402 |
| **SiliconFlow** | ✅ PASS（余额字段为已知误报） | balance API 返回 `totalBalance:"-58.3709"`，但 **该字段语义不可靠是既有结论（ISSUES #46，260608-e8l 首次发现）** — 用户确认以 API 可调用为准。实测：vision 调用 200 成功（今日 3/3，provider_mix 100% siliconflow，零 402/拒付）→ 判 PASS。`SKIP_BALANCE_CHECK=1` 正是对该误报的既有防御。**真正的告警信号是 vision 级联里出现 SF 402/拒付或 Gemini 占比 >10%** — 本次均未出现 |
| **Qdrant** | ✅ PASS | 容器 Up 2 weeks，RestartPolicy=**unless-stopped** ✅；3 个 3072d collection 正常。⚠️ 小项：client 1.18.0 vs server 1.11.5 版本不匹配 warning（journal 持续刷） |
| **qdrant-snapshot cron** | 🔴 FAIL | timer 状态 `active (elapsed)`，**上次真正运行 = Jun 6**，service journal 30 天无记录。根因推断：timer 是 `OnBootSec=15min + OnUnitActiveSec=6h` 组合；Jun 17 重建后开机 +15min 时 docker.service 尚未安装（g6e 记录 docker 6/23 才装好），service 启动失败 → OnUnitActiveSec 永不再武装 → timer 永久 elapsed。**Path X（Qdrant→nanovdb 快照，#44 graphml↔vdb 错位的自愈通道）已停摆 ~3.5 周** |
| **mcp-tunnel（Mac 通道）** | ⚠️ WARN | 此刻 active（08:53 起 >5min）且 `ssh hermes echo` OK、WeChat session ret=0。但 flap 历史严重：7/6=242、7/7=1346、7/8=1092、7/9=235、7/10=210、7/11 上午已 85 次 Start。模式 = 起动 15s 后 exit 255（ConnectTimeout）→ 等 300s 重试 = Mac 端反向隧道（`-R 49221`）间歇性死亡（Mac 睡眠/网络）。**Jul 10 19:03 cookie 刷新首次尝试正是因此失败**，拖到次日 06:19 才成功 |
| **磁盘** | ⚠️ WARN | `/` 84%（79G/99G，余 16G）；journal 占 3.9G；`omonigraph-vault` 5.4G |

---

## L3 — 管线数据健康 【PASS（带尾巴）】

DB: `/root/OmniGraph-Vault/data/kol_scan.db`（只读查询；列名先 PRAGMA 验证过）

### 分类积压 — 402 storm 与 7/1 积压均已清零 ✅

| 指标 | 7/1–7/2 基线 | 现在 | 判定 |
|---|---|---|---|
| layer1 NULL | ~194 | **44**（全部 scanned_at 2026-04-27 ~ 05-04 的化石行，无 7 月新增） | ✅ 已消化 |
| layer2 NULL（candidate 中） | 402 storm 批次 23-28 全 NULL | **33** = 25 条 2026-05-12 化石 + **8 条今天 08:00 刚 L1 完、等下轮** | ✅ 402 遗留清零 |
| layer2 分布 | — | ok=617 / reject=224 / NULL=1559（NULL 大头是 L1 reject 行，不进 L2，正常） | ✅ |

### 入库吞吐 — 管线确实在跑 ✅

- 近 7 天 ingest ok：7/4=30, 7/6=10, 7/7=1, 7/9=12, 7/10=8, **7/11=5（08:00 一轮，被 1h RuntimeMaxSec 截断前）**
- 7/11 08:00 run：L1 238 篇 → L2 211 ok → 204 `skipped_ingested`（checkpoint 去重，已在 KG）→ 5 ok + 4 failed + 42 skipped
- **09:00:01 命中 RuntimeMaxSec=3600 被 SIGTERM**（设计如此：every-2h timer + 1h 硬墙 + `Restart=on-failure` RestartSec=10min → 实际近似连续处理）。graphml 原子写补丁已确认在 venv-aim1（`tmp + os.replace`）✅，中断安全。

### "relevant 未入库积压 89 → 267"的真相 ✅（会计假象）

267 拆解：**198 篇 `skipped_ingested`（KG 里已有，只是 ingestions 表缺 ok 行——历史记账缺口，非真积压）** + 63 skipped + 5 failed + 1 never_attempted。**真实待入库 ≈ 60-70 篇**。按当前节奏（~5 ok/小时窗 × 全天近似连续跑），**预计 2-3 天消化完**，前提是 SiliconFlow/Vertex quota 不断供。

### graphml ✅

46MB，mtime Jul 11 08:41（审计时正在被当轮 run 写入）；iterparse 计数 **39,909 nodes / 58,634 edges**（7/10 handoff 之前基线 ~34k → 明显增长）。

### checkpoint ⚠️

~10 条 in_flight 化石（10–47 天：`fe089cde` 47d、`fa1e1068` 17d、若干无 URL 的 `?` 行）+ 1 条新鲜 in_flight（55m，image_download，= 被 09:00 硬墙截断的当轮文章，下轮自动续）。化石行不阻塞管线，属清理项。

### vision cascade ✅（运行面）

今日 3 张图全部 siliconflow 一次成功（8.3s/7.6s/11.4s，desc 508-1118 字），Gemini 占比 0% < 10% 阈值。风险全在 L2 的余额问题。

### translate / rewrite cron

- **translate ✅**：7/10 22:00 CST 轮 `attempted=23 ok=22 fail=1`（1 条 300s 超时留 NULL 下轮重试）；覆盖 **599/617 = 97%**
- **rewrite ⚠️**：`body_rewritten` 覆盖 **331/617 = 54%**；脚本 7/11 03:20 已 SCP 到阿里云，但 **无 systemd unit、无 crontab 条目**（`grep -rl rewrite_body_cron /etc/systemd` 空 + `crontab -l` 空）— 与历史"translate 无自动化"同款坑，覆盖率只能靠手动跑涨

### WeChat 扫描上游 ✅（带余震）

- 会话：`ret=0 err_msg=ok`（新 TOKEN 933841234 生效）
- 余震：batch@4 在 06:20 刷新后重试时连吃 `ret=200013` 频控（手动扫描与批扫重叠所致，handoff 已知模式），30min 超时退出。**下一轮 batch@1 今 09:30 CST** — 频控是时间窗问题，非结构故障。

---

## 红黄灯清单

| 灯 | 事项 | 影响 | 建议后续 |
|---|---|---|---|
| 🔴 | **qdrant-snapshot timer 死于 Jun 17 重建**（elapsed 态，最后运行 Jun 6） | #44 graphml↔Qdrant 错位的自愈通道（Path X）停摆 3.5 周，长期恶化 long_form 检索质量 | quick：`systemctl restart qdrant-snapshot.timer` 级修复 + timer 加 OnCalendar 兜底；先手动跑一次 service 验证 |
| ~~🔴~~✅ | ~~SiliconFlow 余额 -58.37 元~~ **降级：已知误报（ISSUES #46）**，用户确认以 API 可调用为准；API 实测 200 正常 | 真告警信号 = vision 级联出现 SF 402/拒付或 Gemini 占比 >10%（本次均无） | 无需动作；仅当 API 调不通时提示用户充值 |
| 🟡 | mcp-tunnel 高频 flap（Mac 反向隧道间歇死；今晨 85 次重启） | WeChat scrape #3 兜底 + cookie 刷新通道半可用（7/10 晚刷新因此延误 11h） | Mac 侧查 caffeinate/防睡眠 + autossh 健康；或接受现状（RestartSec=300 自愈设计已生效） |
| 🟡 | Vertex embedding 429 RPM 风暴（每轮 run 数十条，retry 可恢复） | 拖慢 ainsert、加剧 1h 硬墙截断 | 观察；恶化则查 GCP quota 或降 embedding 并发 |
| ~~🟡~~✅ | ~~rewrite_body_cron 无自动化 hook~~ **已修（2026-07-11 本线程）**：`omnigraph-rewrite.{service,timer}` 已部署+enable，每日 02:30 CST，--limit 150；手动点火验证运行中 | 覆盖率将自动收敛（audit 时 331 → 手动 backfill 后 498 → 队列剩 ~111） | 无需动作；下轮观察 journal 确认 timer 自触发 |
| 🟡 | 磁盘 84% + journal 3.9G | 余 16G，按当前增速数周内告警 | `journalctl --vacuum-size=1G` 级清理（需用户点头） |
| ~~🔵~~✅ | ~~repo drift~~ **已回写（2026-07-11 本线程，ISSUES #80）**：mcp-tunnel 3-forward、daily-digest vitaclaw ExecStart、translate 单元、afternoon/evening override 全部从 live dump 回填 `deploy/aliyun/systemd/` | repo 现与 live 一致（仅余 vertex-proxy-env.conf 孤儿 + 阿里云 article_filter.py 未提交热补丁两个有意留置项） | 孤儿 conf 删除并入 qdrant-snapshot quick 的 ops 窗口 |
| 🔵 | Qdrant client 1.18.0 vs server 1.11.5 版本警告 | 目前功能正常 | 与 LightRAG pin 升级一并处理 |

## ISSUES.md 转录处置（2026-07-11 用户裁决后更新）

1. ✅ 已转录为 **#78** P1 `260712-qdrant-snapshot-timer-revive` — qdrant-snapshot.timer elapsed since Jun 17 rebuild；修复走独立 GSD quick（提示词已交付用户）。
2. ❌ 不转录 — SF 余额为已知误报（既有 **#46** 已覆盖该结论），用户确认以 API 可调用为准；本报告 L2 行已改判 PASS。
3. ✅ 已修复（本线程），不转录 — `omnigraph-rewrite.{service,timer}` 部署 + enable + 实测。
4. ✅ 已转录为 **#79** P1 `260712-mac-tunnel-flap` — Mac 端反向隧道间歇死（与已解决的 #77 阿里云侧风暴区分）。
5. ✅ 已回写修复（本线程），转录为 **#80**（resolved inline）— 单元 drift 回填 repo。

---

## 原始证据索引

- 单元全量 dump + diff：`.scratch/260710-health-audit/live-units-dump.txt`、`unit-diff-report.txt`（本地）
- 关键 journal 摘录、sqlite 查询结果：见本报告各节内嵌（audit session transcript 2026-07-10 ADT 晚间）
- 恢复动作的书面记录：`docs/HANDOFF-2026-07-11.md`（commit b786d19，Hermes agent 撰写）
