# OmniGraph-Vault 部署指南

本文档指导如何将 **OmniGraph‑Vault**（专为 Openclaw 与 Hermes Agent 设计的个人知识库解决方案）部署到全新的 Hermes 环境。部署过程分为 **环境初始化**、**技能配置** 和 **端到端验证** 三个阶段。

## 1. 系统要求

- **操作系统**：Linux / WSL2 (Ubuntu 20.04+) 或 macOS
- **Python**：3.11 或更高版本
- **Git**：版本控制
- **Hermes Agent**：已安装并配置（CLI 或 Gateway 模式）
- **API 密钥**：
  - Google Gemini API 密钥（用于 LLM 与视觉描述）
  - Apify Token（可选，用于优先抓取）
  - 其他环境变量（详见下文）

## 2. 环境初始化

### 2.1 克隆代码库
```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git ~/OmniGraph-Vault
cd ~/OmniGraph-Vault
```

### 2.2 创建虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2.3 安装依赖
```bash
pip install -r requirements.txt
```

### 2.4 配置环境变量
在 `~/.hermes/.env` 中设置以下变量（若文件不存在则创建）：
```bash
GEMINI_API_KEY=your_gemini_key
APIFY_TOKEN=your_apify_token          # 可选，用于主抓取路径
CDP_URL=http://localhost:9223         # 可选，CDP 后备抓取
```

### 2.5 验证核心组件
```bash
# 检查 LightRAG 与 Cognee 是否可导入
python -c "import lightrag; print('LightRAG OK')"
python -c "import cognee; print('Cognee OK')"
```

### 2.6 启动本地图像服务器
```bash
# 确保图像存储目录存在
mkdir -p ~/.hermes/omonigraph-vault/images

# 在后台启动 HTTP 服务器（端口 8765）
cd ~/.hermes/omonigraph-vault
python -m http.server 8765 --directory images &
```

## 3. 技能配置

OmniGraph‑Vault 依赖以下 Hermes 技能（均已预置在技能库中）。请确保它们已安装并启用。

### 3.1 核心技能清单

| 技能名称 | 类别 | 作用 |
|----------|------|------|
| **omonigraph‑vault‑ops** | `omonigraph‑vault` | OmniGraph‑Vault 操作指南 – 涵盖 WeChat 抓取、图像描述、图谱合成全流程 |
| **wechat_ingest** | 根目录 | WeChat 文章抓取专用技能 – Apify 优先、CDP 后备、图像处理逻辑 |
| **cdp‑browser‑setup** | 根目录 | Windows Edge 桥接配置 – 为 CDP 后备抓取提供 WSL‑Windows 浏览器连接 |

### 3.2 技能安装与启用

#### 方法一：使用 Hermes CLI（推荐）
```bash
# 查看已安装技能
hermes skills list

# 搜索 OmniGraph 相关技能（若在官方技能中心）
hermes skills search omonigraph-vault

# 安装技能（若尚未安装）
hermes skills install omonigraph-vault-ops
hermes skills install wechat_ingest
hermes skills install cdp-browser-setup

# 启用技能平台可见性
hermes skills config
# 在界面中确保上述技能在 CLI / Telegram 等平台勾选
```

#### 方法二：手动复制技能文件（适用于本地开发）
```bash
# 假设技能文件位于项目下的 skills/ 目录
cp -r ~/OmniGraph-Vault/skills/* ~/.hermes/skills/

# 重新加载技能列表
hermes skills check
```

### 3.3 验证技能配置
```bash
# 查看技能详情
hermes skills inspect omonigraph-vault-ops

# 在会话中加载测试
hermes chat -s omonigraph-vault-ops -q "如何抓取微信文章？"
```

## 4. 端到端验证

### 4.1 测试单篇文章抓取
```bash
# 使用示例 WeChat 文章 URL（请替换为真实 URL）
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# 预期输出：
# - 文章文本提取为 Markdown
# - 图片下载至 ~/.hermes/omonigraph-vault/images/{article_hash}/
# - Gemini Vision 生成图像描述
# - 内容索引到 LightRAG 知识图谱
```

### 4.2 测试知识图谱查询
```bash
python query_lightrag.py "测试查询"

# 应返回图谱中的实体与关系
```

### 4.3 测试合成报告生成
```bash
python kg_synthesize.py "简要介绍抓取的文章内容"

# 预期输出：
# - 从知识图谱检索相关内容
# - Cognee 记忆层提供上下文
# - Gemini 2.5 Pro 生成综合报告
# - 报告保存至 ~/.hermes/omonigraph-vault/synthesis_output.md
# - 报告中包含本地图片链接（http://localhost:8765/...）
```

### 4.4 检查输出文件
```bash
cat ~/.hermes/omonigraph-vault/synthesis_output.md
```

## 5. 与 Openclaw / Hermes Agent 集成

OmniGraph‑Vault 设计为可被 AI 代理直接调用。在您的 Agent 脚本中添加以下模块：

```python
# omnigraph_integration.py
import subprocess
import json
from pathlib import Path

def ingest_to_kg(url: str) -> dict:
    """抓取文章并存入知识图谱"""
    result = subprocess.run(
        ["python", Path.home() / "OmniGraph-Vault/ingest_wechat.py", url],
        capture_output=True, text=True
    )
    return {"success": result.returncode == 0, "output": result.stdout}

def query_kg(question: str) -> str:
    """从知识图谱生成合成报告"""
    result = subprocess.run(
        ["python", Path.home() / "OmniGraph-Vault/kg_synthesize.py", question],
        capture_output=True, text=True
    )
    return result.stdout
```

## 6. 自动化与监控

### 6.1 创建健康检查 Cron 任务
```bash
hermes cron create "0 */6 * * *" \
  --prompt "检查 OmniGraph‑Vault 服务：1) 图像服务器端口 8765 2) LightRAG 存储目录 3) Cognee 内存连接" \
  --name "omonigraph-vault-health"
```

### 6.2 启动网关服务（若使用 Telegram 等平台）
```bash
hermes gateway install
hermes gateway start
```

## 7. 故障排除

### 7.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| **LightRAG 导入失败** | 依赖未正确安装 | `pip install lightrag --upgrade` |
| **Cognee 密钥错误** | `GEMINI_API_KEY` 未设置 | 检查 `~/.hermes/.env` 文件 |
| **CDP 连接失败** | Windows Edge 未启动调试模式 | 运行 `cdp-browser-setup` 技能配置桥接 |
| **图像服务器无法访问** | 端口 8765 被占用或服务未启动 | `lsof -i:8765` 检查，重启服务器 |
| **技能未显示** | 技能未启用对应平台 | `hermes skills config` 中勾选相应平台 |

### 7.2 日志位置
- **Hermes 网关日志**：`~/.hermes/logs/gateway.log`
- **OmniGraph‑Vault 运行日志**：`~/OmniGraph-Vault/cognee_batch.log`
- **Python 错误**：查看终端输出或使用 `try/except` 捕获

## 8. 升级与维护

### 8.1 更新代码库
```bash
cd ~/OmniGraph-Vault
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### 8.2 更新技能
```bash
hermes skills update
```

### 8.3 备份知识图谱数据
```bash
tar -czf kg-vault-backup-$(date +%Y%m%d).tar.gz ~/.hermes/omonigraph-vault/
```

## 9. 总结

成功部署的标志：
1. ✅ 环境变量配置正确（`~/.hermes/.env`）
2. ✅ 虚拟环境激活且依赖安装完成
3. ✅ 图像服务器运行在端口 8765
4. ✅ 核心技能已安装并启用
5. ✅ 单篇文章抓取测试通过
6. ✅ 知识图谱查询返回结果
7. ✅ 合成报告生成且包含本地图片链接

完成上述步骤后，OmniGraph‑Vault 即可作为 **Openclaw 和 Hermes Agent 的持久化知识库**，为 AI 代理提供长期记忆、结构化检索和跨会话上下文。

如需进一步协助，请查阅项目 [README.md](README.md) 或 [specs/PRD_TDD.md](specs/PRD_TDD.md) 文档。
