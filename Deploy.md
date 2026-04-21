# OmniGraph-Vault 部署指南

本文档说明如何把 **OmniGraph-Vault** 接入真实运行中的 **Hermes Agent / Openclaw**，并避免最常见的部署错误。

最重要的原则只有一条：

- **Git 仓库是源码与技能定义的唯一真相来源**
- **`~/.hermes/omonigraph-vault/` 是运行时数据目录，不是 Git 仓库**

不要把源码、虚拟环境、LightRAG 源码副本、图谱数据和技能副本混在同一个目录里。Hermes/Openclaw 不应该“自己猜”项目在哪里；我们要显式告诉它。

## 1. 系统要求

- 操作系统：Linux / WSL2 (Ubuntu 20.04+) 或 macOS
- Python：3.11+
- Git
- Hermes Agent 或 Openclaw
- Google Gemini API Key
- Apify Token（可选）
- Windows Edge 或 Chrome CDP 调试入口（可选，用于抓取后备）

## 2. 目标目录结构

推荐目录如下：

```text
~/OmniGraph-Vault/                 # Git 仓库：源码、skills、tests、docs
~/.hermes/.env                     # Hermes / OmniGraph-Vault 共用环境变量
~/.hermes/omonigraph-vault/        # 运行时数据：图谱、图片、输出、缓存
```

其中：

- `~/OmniGraph-Vault` 必须保持为正常 Git 仓库
- `~/.hermes/omonigraph-vault` 必须保留 `omonigraph` 这个拼写，**不要擅自改成 `omnigraph`**
- `config.py` 会读取 `~/.hermes/.env`

## 3. 安装源码仓库

```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git ~/OmniGraph-Vault
cd ~/OmniGraph-Vault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

验证：

```bash
git status --short --branch
python -c "import lightrag; print('LightRAG OK')"
python -c "import cognee; print('Cognee OK')"
```

## 4. 初始化运行时数据目录

```bash
mkdir -p ~/.hermes/omonigraph-vault/images
mkdir -p ~/.hermes/omonigraph-vault/lightrag_storage
mkdir -p ~/.hermes/omonigraph-vault/outputs
```

这一步只创建运行时目录，不复制源码，不复制整个仓库，不在这里再建第二个 Git repo。

## 5. 配置环境变量

在 `~/.hermes/.env` 中放置项目需要的变量：

```bash
GEMINI_API_KEY=your_gemini_key
APIFY_TOKEN=your_apify_token
CDP_URL=http://localhost:9223
```

如果你在 WSL 中调用 Windows Edge 进行 CDP 抓取，先在 Windows 主机启动：

```powershell
Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
```

## 6. 启动图像服务器

图像服务器必须直接指向运行时图片目录：

```bash
cd ~/.hermes/omonigraph-vault
python3 -m http.server 8765 --directory images
```

如果要后台运行：

```bash
cd ~/.hermes/omonigraph-vault
nohup python3 -m http.server 8765 --directory images > image_server.log 2>&1 &
```

## 7. 把 Git 仓库显式连接到 Hermes

这是部署里最关键的一步。

### 7.1 不要复制 skills 到随机目录

不推荐：

```bash
cp -r ~/OmniGraph-Vault/skills/* ~/.hermes/skills/
```

因为这样很容易让 Git 仓库和 Hermes 实际使用的技能副本发生漂移。

### 7.2 推荐做法：让 Hermes 直接加载仓库内的 `skills/`

```bash
hermes config set skills.external_dirs '["/home/<your-user>/OmniGraph-Vault/skills"]'
```

如果 CLI 版本不接受 JSON 数组，也可以直接编辑 `~/.hermes/config.yaml`：

```yaml
skills:
  external_dirs:
    - /home/<your-user>/OmniGraph-Vault/skills
```

然后重启网关：

```bash
hermes gateway restart
```

验证：

```bash
hermes skills list | grep -E 'omnigraph|omonigraph'
```

你应该至少看到：

- `omnigraph_ingest`
- `omnigraph_query`

## 8. Openclaw / Hermes 技能最佳实践

为了让代理尽量少猜测，项目技能必须遵循下面的约束：

- 技能只描述明确职责，不做大而全的“万能技能”
- 技能中的命令应调用 Git 仓库里的脚本，而不是运行时目录里的副本
- 所有路径都应以环境变量或稳定绝对路径表达
- 对缺失 URL、文件路径、API key 的情况，必须给出 guard clause
- 不要要求代理自行推断 repo 路径、数据路径、图片目录、CDP 端口

本项目推荐的技能职责：

| 技能 | 职责 |
|------|------|
| `omnigraph_ingest` | 把 URL / PDF 写入图谱 |
| `omnigraph_query` | 从图谱检索并生成回答 |

这些技能应始终把：

- **源码执行目录** 视为 `~/OmniGraph-Vault`
- **运行时数据目录** 视为 `~/.hermes/omonigraph-vault`

## 9. 建议给代理的固定执行模式

如果你要让 Hermes/Openclaw 在没有太多人工干预的情况下工作，建议让技能或包装脚本显式执行：

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate && python ingest_wechat.py "<URL>"
```

以及：

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate && python kg_synthesize.py "<QUESTION>" hybrid
```

这样可以避免：

- 从错误目录执行脚本
- 使用错误的 Python
- 把运行时目录误当作源码目录

## 10. 部署后验证

### 10.1 验证仓库与技能连接

```bash
cd ~/OmniGraph-Vault && git status --short --branch
hermes skills list | grep omnigraph
hermes chat -s omnigraph_ingest -q "add this to my kb"
```

预期：

- Git 仓库状态正常
- Hermes 能看到 `omnigraph_ingest`
- 当没有提供 URL / PDF 时，技能返回 guard clause，而不是报错

### 10.2 验证直接脚本调用

```bash
cd ~/OmniGraph-Vault
source venv/bin/activate
python query_lightrag.py "test query"
```

### 10.3 验证合成输出

```bash
cd ~/OmniGraph-Vault
source venv/bin/activate
python kg_synthesize.py "What do I know about OmniGraph-Vault?" hybrid
cat ~/.hermes/omonigraph-vault/synthesis_output.md
```

## 11. 升级流程

更新项目时：

```bash
cd ~/OmniGraph-Vault
git pull --ff-only origin main
source venv/bin/activate
pip install -r requirements.txt
hermes gateway restart
```

不要更新 `~/.hermes/omonigraph-vault/` 里的源码副本，因为那里本来就不应该有源码副本。

## 12. 常见问题

| 问题 | 原因 | 解决方式 |
|------|------|----------|
| 技能显示不出来 | Hermes 没有加载 repo `skills/` | 检查 `skills.external_dirs`，然后 `hermes gateway restart` |
| 技能和 GitHub 内容不一致 | 复制了一份旧 skills 到 `~/.hermes/skills/` | 删除旧副本，改为直接加载 repo `skills/` |
| 图谱数据目录混乱 | 把源码和运行时数据放在一个目录 | 恢复为 `~/OmniGraph-Vault` + `~/.hermes/omonigraph-vault` 双目录结构 |
| 查询脚本找不到数据 | 运行时目录拼写被改了 | 恢复 `~/.hermes/omonigraph-vault` |
| CDP 抓取失败 | Windows Edge 未开启 remote debugging | 启动 Edge `--remote-debugging-port=9223` |

## 13. 成功标准

成功部署后，应满足：

1. `~/OmniGraph-Vault` 是 Git 仓库
2. `~/.hermes/omonigraph-vault` 只存运行时数据
3. `~/.hermes/.env` 中已有必需 API key
4. Hermes 能看到 `omnigraph_ingest` 与 `omnigraph_query`
5. Hermes/Openclaw 通过 repo 中的脚本执行 OmniGraph-Vault
6. 图片服务器能从 `http://localhost:8765/...` 提供本地图片

如需更详细的产品与架构背景，请继续参考 [README.md](README.md) 与 [specs/PRD_TDD.md](specs/PRD_TDD.md)。
