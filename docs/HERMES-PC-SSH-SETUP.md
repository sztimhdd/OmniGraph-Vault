# Hermes PC — SSH 连接指南

**作用**：远程访问 Hermes PC（WSL2 Ubuntu），用于操作 Edge CDP、运行 PowerShell 命令、部署脚本等。

---

## 快速连接

```bash
ssh hermes-pc "command here"
```

例如：

```bash
# 查看 Edge 中打开的标签页
ssh hermes-pc "curl -s http://localhost:9222/json"

# 在 Hermes PC 上运行 PowerShell
ssh hermes-pc "powershell.exe -NoProfile -Command 'Get-Process'"

# 启动 Edge CDP
ssh hermes-pc "powershell.exe -NoProfile -Command 'Start-Process msedge.exe -ArgumentList @(\"--remote-debugging-port=9222\")'"
```

---

## 一次性配置（已完成）

### 1. SSH 密钥

本机已有 SSH 密钥：
```
~/.ssh/id_ed25519          (私钥)
~/.ssh/id_ed25519.pub      (公钥)
```

### 2. SSH 配置（~/.ssh/config）

添加以下条目：

```
Host hermes-pc
    HostName ohca.ddns.net
    Port 49221
    User sztimhdd
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
    ServerAliveInterval 60
```

**说明**：
- `HostName`: Hermes PC 的 DDNS 地址
- `Port 49221`: 外部 SSH 端口（映射到内部 22）
- `User sztimhdd`: Hermes PC 用户名
- `IdentityFile`: 使用本机的 ED25519 密钥（免密登录）
- `ServerAliveInterval 60`: 每 60 秒发送一次心跳，防止连接超时

### 3. Hermes PC 端

Hermes PC 的 `~/.ssh/authorized_keys` 已包含本机公钥，允许免密 SSH 连接。

---

## Hermes PC 上的关键服务

### Edge CDP (端口 9222)

```bash
# 查询当前打开的标签页（JSON 格式）
ssh hermes-pc "curl http://localhost:9222/json"

# 在 Hermes PC 上启动新的 Edge 实例（如果宕了）
ssh hermes-pc "powershell.exe -NoProfile -Command 'Start-Process \"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe\" -ArgumentList @(\"--remote-debugging-port=9222\", \"--remote-debugging-address=127.0.0.1\", \"--remote-allow-origins=*\", \"--user-data-dir=C:\\Edge-Auto-Profile\")'"
```

### Playwright MCP (端口 58931)

```bash
# 查询 MCP 状态
ssh hermes-pc "curl http://localhost:58931/health"
```

### Hermes Harness (WSL2)

```bash
# 检查 Hermes 运行状态
ssh hermes-pc "ps aux | grep hermes"

# 重启 Hermes gateway
ssh hermes-pc "sudo systemctl restart hermes-gateway"
```

---

## 故障排除

### 连接超时

**症状**：`ssh hermes-pc` 挂起，30 秒后超时

**解决**：
1. 检查 DDNS 是否生效：`nslookup ohca.ddns.net`
2. 检查网络连接：`ping ohca.ddns.net`
3. 检查防火墙是否允许 49221 端口

### 权限拒绝

**症状**：`Permission denied (publickey,password)`

**解决**：
1. 确认 `~/.ssh/id_ed25519` 存在
2. 确认 SSH config 中的 User 是 `sztimhdd`
3. 在 Hermes PC 上检查 `~/.ssh/authorized_keys` 是否包含本机公钥

### 连接一半卡住

**症状**：SSH 连上但命令没有响应

**解决**：使用 timeout：
```bash
timeout 10 ssh hermes-pc "curl http://localhost:9222/json"
```

---

## 常见操作

### 检查 Edge 是否在线

```bash
ssh hermes-pc "curl -s http://localhost:9222/json | head -c 50"
```

### 获取微信公众平台的当前页面

```bash
ssh hermes-pc "curl -s http://localhost:9222/json | python3 -m json.tool | grep -A 3 'weixin'"
```

### 远程启动 PowerShell 命令

```bash
ssh hermes-pc "powershell.exe -NoProfile -Command 'Write-Host \"Hello from Hermes\"'"
```

---

## 更新历史

- **2026-07-14**: 初始配置完成，记录 SSH 连接方式
  - 添加 SSH config entry for hermes-pc
  - 验证免密登录正常
  - 文档化关键命令
