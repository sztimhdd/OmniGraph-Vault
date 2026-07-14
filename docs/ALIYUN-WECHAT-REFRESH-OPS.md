# 阿里云 WeChat Cookie 自动刷新 — 运维 Ops 标准

**作用**：定义 Aliyun 生产环境如何自动检测 WeChat 登录失效、触发 Hermes PC 刷新凭证、写回 Aliyun 配置的完整运维流程。

**架构决策日期**：2026-07-14（实测验证）

---

## 架构总览

```
┌─ Aliyun (47.117.244.253) ────────────────────────────────┐
│  omnigraph-kol-refresh.timer (每日 pre-scan 前触发)        │
│    └─→ omnigraph-kol-refresh.service                      │
│         ExecStart: SSH 直连 Hermes PC 跑刷新脚本            │
│                                                            │
│  omnigraph-kol-scan.timer (每日扫描)                       │
│    └─→ 若 ret=200003 (session 过期)                        │
│         └─→ OnFailure: kol-scan-alert.service              │
│              └─→ 重试刷新脚本 (belt-and-suspenders)         │
└────────────────────────────────────────────────────────────┘
              │ SSH -p 49221 sztimhdd@ohca.ddns.net
              ▼
┌─ Hermes PC (ohca.ddns.net:49221, WSL2 Ubuntu, 24/7) ──────┐
│  refresh_wechat_cookie.py                                  │
│    1. 连本地 Edge CDP (headed, profile=C:\Edge-Auto-Profile)│
│    2. 检测登录状态 (URL 有无 token=)                        │
│    3a. 有效 → 提取 token+cookie                             │
│    3b. 过期 → 二维码 → Telegram 通知用户扫码 → 等待          │
│    4. 原子写回 Aliyun kol_config.py + verify scan + rollback│
│    5. Telegram 通知结果                                     │
│                                                            │
│  Edge (headed, --user-data-dir=C:\Edge-Auto-Profile)      │
│    登录态持久化在 profile 目录，重启浏览器不丢               │
└────────────────────────────────────────────────────────────┘
```

**关键原则**：
- Aliyun **只做检测 + 触发**，所有浏览器/CDP/Telegram 工作都在 Hermes 上
- Aliyun **直连 Hermes PC 公网**（`ohca.ddns.net:49221`），**不走** Mac 反向隧道（已废弃）
- 刷新是 **best-effort**：不阻塞扫描；扫描 + OnFailure 是安全网

---

## 关键路径与凭证

| 项 | 值 |
|---|---|
| Aliyun SSH（本机→Aliyun） | `ssh aliyun-vitaclaw`（47.117.244.253，root） |
| Hermes SSH（Aliyun→Hermes） | `ssh -p 49221 sztimhdd@ohca.ddns.net`（免密 key） |
| Hermes 仓库 | `/home/sztimhdd/OmniGraph-Vault` |
| Hermes hermes CLI | `/home/sztimhdd/.local/bin/hermes`（非登录 shell 需全路径） |
| Hermes Edge CDP | `http://localhost:9222`（生产标准端口） |
| Hermes Edge profile | `C:\Edge-Auto-Profile`（登录态持久化目录） |
| Aliyun 配置文件 | `/root/OmniGraph-Vault/kol_config.py`（TOKEN + COOKIE 行） |
| Aliyun verify venv | `venv-aim1/bin/python` |
| 通知渠道 | Telegram（`hermes send --to telegram`，chat_id 6749597705） |

---

## Hermes Edge 持久化前提（重要）

刷新脚本依赖 Hermes 上有一个 **headed Edge 实例监听 CDP 端口，且使用 `C:\Edge-Auto-Profile` profile**。

**登录态存在 profile 目录里**，不在端口上——重启 Edge（同 profile）登录态保留。只有真正 session 过期（微信侧 14-31 天）才需要重新扫码。

**启动持久 Edge（Hermes PowerShell）**：
```powershell
Start-Process "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList @(
  "--remote-debugging-port=9222",
  "--remote-debugging-address=127.0.0.1",
  "--remote-allow-origins=*",
  "--user-data-dir=C:\Edge-Auto-Profile",
  "--no-sandbox"
)
```

脚本的 `relaunch_edge_local()` 在检测到 CDP 端口无响应时会自动执行上述启动（同 profile）。

**运维建议**：把 Edge 启动做成 Windows 开机自启（任务计划程序），确保 24/7 可用。当前状态见 `docs/HERMES-PC-SSH-SETUP.md`。

---

## 手动操作命令

### 检查 Aliyun 当前 token
```bash
ssh aliyun-vitaclaw 'grep "^TOKEN" /root/OmniGraph-Vault/kol_config.py'
```

### 手动触发刷新（从本机 SSH 到 Aliyun，Aliyun 再触发 Hermes）
```bash
ssh aliyun-vitaclaw 'timeout 260 ssh -o BatchMode=yes -o ConnectTimeout=20 -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && timeout 240 python3 scripts/refresh_wechat_cookie.py"'
```

### 直接在 Hermes 上手动刷新（调试用，本机→Hermes）
```bash
# dry-run（不写回，只验证能连 + 提取）
ssh hermes-pc 'cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --dry-run'

# 真实刷新（写回 Aliyun + verify + 通知）
ssh hermes-pc 'cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --test-account 叶小钗'
```

### 检查 refresh service 状态
```bash
ssh aliyun-vitaclaw 'systemctl status omnigraph-kol-refresh.service; systemctl list-timers omnigraph-kol-refresh.timer'
```

### 查看刷新日志
```bash
ssh aliyun-vitaclaw 'journalctl -u omnigraph-kol-refresh.service -n 50 --no-pager'
# Hermes 端刷新日志
ssh hermes-pc 'tail -50 ~/.hermes/kol-refresh.log'
```

---

## 失效恢复流程（session 真过期，需扫码）

当微信 session 真正过期（14-31 天一次）：

1. **自动检测**：daily scan 遇到 ret=200003 → OnFailure 触发 refresh
2. **脚本检测**：refresh 脚本连 Edge，发现 URL 无 token=（过期）→ 进入 Level C
3. **二维码通知**：脚本截取二维码 → Telegram sendPhoto 发到你手机
4. **你扫码**：用手机微信扫 Telegram 里的二维码 → 确认登录
5. **脚本轮询**：脚本每 10s 检查一次，最多 5 分钟；检测到登录成功（URL 出现 token=）→ 提取新凭证
6. **写回 + 验证**：原子写回 Aliyun kol_config.py → verify scan ret=0 → Telegram 通知成功

**超时（5 分钟没扫）**：脚本 Telegram 通知超时，退出。下次 scan 会再触发。

---

## 故障排除

| 症状 | 根因 | 处理 |
|------|------|------|
| refresh service 静默失败 | Aliyun→Hermes SSH 不通 | `ssh aliyun-vitaclaw 'ssh -p 49221 sztimhdd@ohca.ddns.net whoami'` 测连通 |
| 脚本报 CDP down | Hermes Edge 没跑或端口错 | Hermes 启动 headed Edge（见上）；脚本会自动 relaunch |
| relaunch 后无登录态 | profile 目录不对 | 确保 `--user-data-dir=C:\Edge-Auto-Profile` |
| writeback 后 verify 失败 | 提取的凭证无效 | 脚本自动 rollback；检查 Edge 是否真登录 |
| Telegram 没收到二维码 | TELEGRAM_BOT_TOKEN 缺失 | 检查 Hermes `~/.hermes/.env` |
| ret=-2 rate limited（微信通知） | 用了 weixin 渠道 | 已改用 telegram，忽略 |

---

## 已知设计约束

- **不用 Mac 隧道**：旧的 `Host hermes`（Aliyun `localhost:49221` 反向隧道→Mac）已废弃，改直连 Hermes PC 公网
- **Hermes 24/7**：整个方案依赖 Hermes PC 常开 + DDNS + 49221 端口转发
- **登录态 14-31 天过期**：正常，扫码一次续期；proactive timer 每日 pre-scan 前刷新可延长有效期
- **脚本在 Hermes 跑**：全 localhost CDP，无跨网络延迟；Aliyun 只 SSH 触发

---

## 更新历史

- **2026-07-14**：架构锁定 + 实测验证
  - 发现并修复 Aliyun refresh service 指向失效 Mac 隧道 + 不存在的 run_refresh.sh
  - 改为直连 Hermes PC（sztimhdd@ohca.ddns.net:49221）
  - 脚本 3 大改造：URL-token 检测、Telegram 通知、简化 relaunch
  - 端到端实测：token 933841234→1284035398，verify ret=0，Telegram 通知成功
