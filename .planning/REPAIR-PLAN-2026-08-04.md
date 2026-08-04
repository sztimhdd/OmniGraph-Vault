# REPAIR PLAN — 2026-08-04 全流程健康检查问题修复

> 来源：2026-08-04 全流程健康检查（omnigraph-pipeline-verify 六阶段）
> 状态：**T1/T2/T4/T5 已完成，T3 已修复待观察，T6 收尾中**（2026-08-05 00:40）
> 执行记录：T1（磁盘，无 commit）、T2（DB 变更，无 commit）、T4（`ab6a7a6`）、T3（`34e26d3`）、T5（无 commit）

## 问题清单与优先级

| # | 严重度 | 问题 | 根因（已取证） |
|---|---|---|---|
| P0 | 🔴 | 新机 MCP 查不到 8/1 后文章 | 新机 KG 冻结在 7/31 快照 172,907 点，**无增量同步**；旧机已 234k+ |
| P1 | 🟡 | KOL 扫描全批失败 25h+ | 8/3-8/4 四批次 15/15 全败：先 200003 后 200013 freq control；refresh 8/4 18:55 成功但扫描仍限流 |
| P2 | 🟠 | dwarkesh.com 刮削全败 | A 记录 108.160.161.20 连接失败（被墙），`curl -4` 也 FAIL——非 IPv6 问题，该源旧机物理不可达；每天 ~6 篇 RSS 损失 |
| P3 | 🟠 | 磁盘 96%（4.5G 可用） | swapfile 8.1G + models 4.3G + .hermes 6.4G + repo 6.8G；mcp-healthcheck 因阈值 90% 持续误报 FAIL |

---

## T1 — 磁盘治理（P3，前置——96% 影响一切）

**Objective:** 磁盘可用 ≥ 10G，mcp-healthcheck 不再因磁盘 FAIL。

**Files:** `/etc/systemd/system/mcp-healthcheck.service`（不动）、旧机磁盘

**Steps:**
1. `journalctl --vacuum-size=500M`（journal 通常数百 MB）
2. `du -sh /root/.hermes/omonigraph-vault/*` 找大头；清理 images 残留/旧 synthesis_output
3. 评估 swapfile 8G → 4G 是否安全（内存 available 8G 时 4G swap 足够防 OOM；迁移已结束）
4. 若仍 <10G：阿里云控制台在线扩容系统盘（需用户操作或用户授权 CLI）
5. mcp-healthcheck 磁盘阈值 90 → 95（`scripts/mcp-healthcheck.py:86`，缓解误报直到扩容）

**UAT:**
```bash
ssh aliyun-old 'df -h / | tail -1'   # 可用 ≥ 10G 或 ≥ 8G + 扩容排队
ssh aliyun-old 'systemctl restart mcp-healthcheck.service; systemctl is-active mcp-healthcheck.service'  # active 且 exit 0
```

---

## T2 — dwarkesh.com 不可达（P2）

**Objective:** dwarkesh 文章不再每天 6 篇刮削失败刷 ERROR 日志。

**Files:** RSS feed 表/配置（待定位 feed 源定义处）

**Steps:**
1. 定位 dwarkesh feed 定义（`sqlite3 kol_scan.db "SELECT * FROM rss_feeds WHERE url LIKE '%dwarkesh%'"` 或 rss 配置）
2. 决策：a) 从 feed 列表移除/禁用该源；b) 保留但标记 skip（扫描到 dwarkesh URL 直接跳过刮削）
3. 实施最小改动（倾向 2b：保留数据，刮削跳过）

**UAT:**
```bash
ssh aliyun-old 'journalctl -u omnigraph-daily-ingest --since "10 min ago" | grep -c dwarkesh'  # 0
# 或 rss-fetch 后 dwarkesh 文章不再进入 ingest 候选
```

---

## T3 — KOL 扫描限流恢复（P1）—— ✅ 修复完成，待 24h 后验证

**Objective:** 扫描恢复 ok（至少 1 个账户扫描成功，不再 15/15 全败）。

**根因（2026-08-04 探针确认，非凭证失效）：**
- `scripts/wechat_probe.py` 会话探针：**SESSION OK**（http=200，final_url 到 `cgi-bin/home?t=...` 带 token，非登录页）→ `kol_config.TOKEN`（1748038458）**是有效凭证**
- 能力探针：**ret=200013 freq control**（列表接口单请求即限）→ **接口级频率/能力限制**（与社区 2026-07 底报告吻合：登录正常但文章列表首屏 200013）
- **Verifier 假阳性确认**：`refresh_wechat_cookie.py` verify 只查 stderr `ret=200003`/`WECHAT_SESSION_INVALID`——200013 失败时 batch_scan_kol exit 0 无标记 → 误判"writeback success"（8/3 18:57 实例，随后 30h+ 全批 200013）

**修复（commit `34e26d3`）：**
1. `scripts/refresh_wechat_cookie.py` verifier：stderr 检查改为 `re.search(r"ret=2000\d\d")`（任意非零 WeChat ret 即失败回滚）
2. `spiders/wechat_spider.py`：200013 **不再重试 3 次**（fail-fast，防 45 req/batch 加深惩罚箱）
3. `batch_scan_kol.py`：`scan_account` 返回 `rate_limited` 标志；**连续 3 个 200013 立即 abort 本批**
4. 新增 `scripts/wechat_probe.py`（会话探针 + 能力探针，单请求无循环，禁止把诊断变成限流）

**当前状态：** 4 个 kol-scan-batch timers 已暂停（2026-08-05 00:30），等待微信 200013 惩罚箱恢复（~24-48h）。恢复路径：24h 后手动 `wechat_probe.py both` → capability ret=0 → 重启 timers → 观察首批全量扫描。

**Files:** `scripts/refresh_wechat_cookie.py`、`spiders/wechat_spider.py`、`batch_scan_kol.py`、`scripts/wechat_probe.py`（新增）

---

## T4 — 新机 KG 增量同步（P0 核心）

**Objective:** 新机 KG + SQLite/FTS 与旧机一致；MCP kg_search/fts_search 能返回最新文章。

**设计决策（已取证）：**
- **KG 向量直接搬运**（旧机 bge-m3 1024d = 新机同模型同维度，向量一致，无需重算）
- **增量判定 = 点 ID 差集**（旧机全量 ID scroll ~200 次请求 ≈ 10-20s 本地成本，天然幂等，不依赖 created_at 缺失点；比时间水位可靠）
- **SQLite = 整体备份搬运**（kol_scan.db 123MB，每天一次可接受；原子替换避免新机读到半份）

**Files:**
- 新增 `deploy/sync_kq_to_new.py`（旧机执行：旧 Qdrant scroll ID 差集 → 旧机取向量+payload → 新机 Qdrant upsert；SQLite backup → scp → 新机原子替换）
- 新增 systemd timer `omnigraph-kg-sync.{service,timer}`（每天 02:30 CST，避开扫描/ingest 高峰）
- 水位/状态：`/root/OmniGraph-Vault/data/kg_sync_state.json`

**Steps:**
1. 写 `deploy/sync_kq_to_new.py`：
   - 旧机 Qdrant scroll 3 集合全部点 ID（limit=1000）
   - 新机 Qdrant scroll 同集合全部点 ID
   - 差集（旧 - 新）→ 分批（512）取旧机向量+payload → upsert 新机（重试 3 次，退避）
   - sqlite3 `.backup` → scp（`-o ConnectTimeout` + 重试）→ 新机 `mv` 原子替换 + FTS 重建（若需要）
   - 日志 `/var/log/omnigraph-kg-sync.log`；失败 exit 非 0
2. 旧机部署 + 手动跑一次全量（首次差集 = 全部增量 8/1 后 ~1000+ 点 + SQLite）
3. 建 systemd timer（每天 02:30）
4. 验证 MCP 查询最新文章

**UAT:**
```bash
# 同步后（用本地隧道或公网）：
# kg_search("DeepSeek V4 火山方舟") → 返回内容（非 [no-result]）
# fts_search("DeepSeek V4 火山方舟") → 返回内容（非 [no-results]）
ssh aliyun-new 'for coll in entities chunks relationships; do curl -sf "http://127.0.0.1:6333/collections/lightrag_vdb_${coll}_bge_m3_1024d/points/count" -d "{\"exact\":true}"; done'
# NEW 点数 = OLD 点数（±容忍）
# timer: systemctl list-timers | grep kg-sync → NEXT 正常
```

---

## T5 — mcp-healthcheck 阈值 + 回归（依赖 T1）

**Objective:** healthcheck 全绿，确认无回归。

**Files:** `scripts/mcp-healthcheck.py`

**Steps:**
1. 磁盘阈值 90 → 95（若 T1 未扩容）
2. `systemctl restart mcp-healthcheck.service` → exit 0

**UAT:**
```bash
ssh aliyun-old 'systemctl restart mcp-healthcheck.service; sleep 5; systemctl is-active mcp-healthcheck.service; journalctl -u mcp-healthcheck -n 3 --no-pager'
# active + 无 {"check": "disk"} 失败
```

---

## T6 — 文档 + 全流程回归

**Objective:** 修复闭环，ISSUES.md 更新，下次健康检查全绿。

**Files:** `.planning/ISSUES.md`、`BGE_M3_MIGRATION.md`（同步节）、skill `omnigraph-pipeline-verify`（若流程变化）

**Steps:**
1. 更新 ISSUES.md：P0 同步缺口 Resolved（T4 commit）；P1/P2/P3 各自状态
2. 跑一次完整 `omnigraph-pipeline-verify` 六阶段
3. 报告 VERDICT：全绿或列出剩余项

**UAT:**
```bash
# 完整 skill 报告输出，BLOCKERS 为空或仅剩已接受的项
# git log 显示 T1-T6 各一个 commit + push
```

---

## 执行顺序依赖（修订 2026-08-04，按严重度优先）

```
T1 磁盘（T4 物理前置：96% 磁盘时导出/backup 可能写不下）
  │
  └──> T4 新机同步（P0——同事正在用过期 MCP 数据，每等一个任务就多错一天）
          │
          ├──> T2 dwarkesh（P2，独立，可在 T4 后）
          ├──> T3 扫描限流（P1，独立，可在 T4 后）
          └──> T5 healthcheck 阈值（依赖 T1，可在 T4 后）
                  │
                  └──> T6 回归
```

**顺序原则（修订）：** 严重度优先，仅保留真实依赖。T1→T4 是唯一硬依赖链
（T4 的 SQLite backup + Qdrant 导出在旧机 96% 磁盘下可能 ENOSPC）。T2/T3/T5
与 T4 无依赖，全部排在 T4 之后；若 T4 阻塞（如新机不可达），T2/T3 可先行。

## 风险与回退

- T4 SQLite 整体覆盖：新机若本地有写入会丢——已确认新机 fts 只读（mcp_server_standalone 查询），覆盖安全；替换前备份旧文件 `.bak-<ts>`
- T3 cooldown 提升：拖慢扫描（15 账户 × 3 重试 × 180s），但恢复优先
- T1 swapfile 降级：若 OOM 冻结复发立即还原 8G
- 所有改动在旧机可逆；新机只加数据不改服务
