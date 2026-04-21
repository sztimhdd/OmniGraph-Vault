# 🧠 OmniGraph-Vault: AI Agent Personal Knowledge Base

**[English](#english-version) | [中文版](#chinese-version)**

---

<a name="english-version"></a>
## English Version

**OmniGraph-Vault** is a **personal knowledge base solution** specifically designed for **Openclaw** and **Hermes Agent** AI assistants. It transforms web content (WeChat articles, blogs, documentation) into a stateful, evolving **Knowledge Graph (KG)** that serves as long-term memory and contextual intelligence for your AI agents.

### 🎯 Why OmniGraph-Vault for AI Agents?
Modern AI agents (like Openclaw and Hermes Agent) excel at task execution but lack persistent, structured memory across sessions. OmniGraph-Vault fills this gap by providing:
- **Structured Knowledge Storage**: Content is indexed as a graph (entities, relationships, concepts) rather than flat text.
- **Multimodal Context**: Images are downloaded, described by vision AI, and stored locally — enabling rich visual context in agent responses.
- **Session-Aware Memory**: Integrated with **Cognee** to remember user preferences, query patterns, and canonicalize entities over time.
- **Local & Private**: All data stays on your machine; no external knowledge-base SaaS required.

### 🚀 Core Features
- **Triple-Path Scraper**: Primary scraping via **Apify AI**; fallback to **local CDP** (Edge ) in production, or **remote Playwright MCP** server for local dev/testing — auto-detected from .
- **Multimodal KG Ingestion**: Extracts text and images from articles. Every image receives a semantic description from **Gemini Vision** and is linked in the knowledge graph.
- **Stateful Intelligence**: **Cognee** memory layer tracks conversation history, learns user interests, and merges synonymous concepts (e.g., “知识图谱” ↔ “Knowledge Graph”).
- **Local Media Persistence**: Built‑in image server (port 8765) ensures visual content remains accessible even if original online links disappear.
- **Agent‑Ready APIs**: Simple Python interfaces for ingestion, query, and synthesis that can be called from Openclaw, Hermes Agent, or any other automation workflow.

### 🛠 Technology Stack
- **KG Engine**: [LightRAG](https://github.com/HKU-Smart-OT/LightRAG)
- **Memory Layer**: [Cognee](https://github.com/topoteretes/cognee)
- **LLM / Vision**: Google Gemini 2.5 Pro & Flash models
- **Scraping**: Apify SDK + Playwright CDP (local production) / Playwright MCP server (remote testing)
- **Infrastructure**: Python 3.11+, local HTTP server, config‑driven paths

### 📦 Quick Start

#### 1. Clone & Setup
```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git
cd OmniGraph-Vault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. Configuration
Put your runtime secrets in `~/.hermes/.env` because `config.py` loads from that location:
```bash
GEMINI_API_KEY=your_gemini_key
APIFY_TOKEN=your_apify_token  # optional, for primary scraping
CDP_URL=http://localhost:9223  # local CDP; use http://host:port/mcp for remote Playwright MCP
```

Important deployment rule:

- `~/OmniGraph-Vault` = Git repo, source code, tests, skills
- `~/.hermes/omonigraph-vault` = runtime data only

Do not turn `~/.hermes/omonigraph-vault` into a second copy of the repo.

#### 3. Basic Usage
```bash
# Ingest a WeChat article (text + images → KG)
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# Generate a synthesized report from your knowledge base
python kg_synthesize.py "What are the latest trends in AI Agents?"

# Direct KG query (for debugging or agent‑side retrieval)
python query_lightrag.py "Explain the architecture of OmniGraph‑Vault."
```

#### 4. Integration with AI Agents
OmniGraph‑Vault is designed to be called from Openclaw or Hermes Agent scripts. Example integration snippet:
```python
import subprocess
import json

def query_kg(question: str) -> str:
    """Call OmniGraph‑Vault from an agent."""
    result = subprocess.run(
        ["python", "kg_synthesize.py", question],
        capture_output=True, text=True
    )
    return result.stdout
```

#### 5. Connect Hermes To The Repo
Hermes should load the repository's `skills/` directory directly instead of using copied skill files.

```bash
hermes config set skills.external_dirs '["/home/<your-user>/OmniGraph-Vault/skills"]'
hermes gateway restart
hermes skills list | grep omnigraph
```

Expected skills:

- `omnigraph_ingest`
- `omnigraph_query`

This keeps GitHub, local development, and live Hermes behavior aligned.

#### 6. Test Skills Locally (skill_runner)

Validate skill routing without Hermes using `skill_runner.py`:

```bash
# Ingest skill — 9 test cases (decision tree routing)
python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json

# Query skill — 10 test cases
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
```

Exit code 0 = all cases pass. Requires `GEMINI_API_KEY` to be set (loaded from `~/.hermes/.env`).

Eval definitions (SkillHub format) live in each skill's `evals/evals.json`.

### 🔌 Browser Fallback (CDP or Playwright MCP)

`ingest_wechat.py` auto-selects the fallback method based on `CDP_URL`:

**Local mode (production default)** — start Edge with remote debugging:
```powershell
Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
```
Set `CDP_URL=http://localhost:9223` in `~/.hermes/.env`.

**Remote MCP mode (local dev / testing)** — point to a running Playwright MCP server:
```bash
CDP_URL=http://host:port/mcp  # e.g. http://ohca.ddns.net:58931/mcp
```
The `/mcp` suffix triggers the MCP client path automatically. No Edge browser needed locally.

### 📁 Project Structure
```
OmniGraph‑Vault/
├── config.py              # Centralized paths & environment loading
├── ingest_wechat.py       # WeChat article ingestion (Apify + CDP/MCP)
├── kg_synthesize.py       # Synthesis & report generation
├── query_lightrag.py      # Direct KG queries
├── cognee_wrapper.py      # Cognee memory integration
├── cognee_batch_processor.py # Batch processing for Cognee
├── data_assets/           # Local copies of ingested images & markdown
├── specs/                 # Design specifications & test plans
└── tests/                 # Unit & integration tests
```

**Runtime data** is stored under `~/.hermes/omonigraph-vault/`. The `omonigraph` spelling is intentional and currently baked into `config.py`, so preserve it unless you are doing a coordinated migration.

### 🤖 Agent Deployment Notes

For Hermes/Openclaw skill best practices, this project assumes:

- skills are narrow in scope and explicit about when to trigger
- skills call repo scripts, not ad-hoc copies in runtime folders
- agents should not guess the repo path, data path, or Python environment
- guard clauses should fire early when the user omitted a URL, file path, or API key

Recommended command shape inside agent wrappers:

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate && python ingest_wechat.py "<URL>"
cd ~/OmniGraph-Vault && source venv/bin/activate && python kg_synthesize.py "<QUESTION>" hybrid
```

If you are deploying to Hermes, see [Deploy.md](Deploy.md) for the full connection flow.

### 📄 License
MIT License.

---

<a name="chinese-version"></a>
## 中文版

**OmniGraph‑Vault** 是专为 **Openclaw** 与 **Hermes Agent** 等 AI 助手设计的**个人知识库解决方案**。它将网页内容（微信公众号文章、博客、技术文档）转化为有状态、可进化的**知识图谱（KG）**，作为 AI 代理的长期记忆与上下文智能核心。

### 🎯 为何选择 OmniGraph‑Vault 作为 AI 代理的知识库？
现代 AI 代理（如 Openclaw、Hermes Agent）擅长执行任务，但缺乏跨会话的持久化、结构化记忆。OmniGraph‑Vault 填补了这一空白：
- **结构化知识存储**：内容以图谱（实体、关系、概念）形式索引，而非扁平文本。
- **多模态上下文**：图片被下载、通过视觉 AI 描述并本地存储，使代理回复具备丰富的视觉语境。
- **会话感知记忆**：集成 **Cognee**，记忆用户偏好、查询模式，并随时间推移进行实体归一化。
- **本地与私有**：所有数据留存于本地，无需外部知识库 SaaS。

### 🚀 核心特性
- **双路爬虫**：主路径通过 **Apify AI** 抓取；检测到反爬时自动回退至 **CDP（Chrome DevTools Protocol）**。
- **多模态图谱入库**：从文章中提取文本与图片。每张图片均由 **Gemini Vision** 生成语义描述并链接到知识图谱。
- **有状态智能**：**Cognee** 记忆层跟踪对话历史、学习用户兴趣，合并同义概念（如“知识图谱”↔“Knowledge Graph”）。
- **本地媒体持久化**：内置图片服务器（端口 8765）确保原始链接失效后视觉内容仍然可访问。
- **代理就绪的 API**：提供简单的 Python 接口用于入库、查询与合成，可供 Openclaw、Hermes Agent 或其他自动化工作流调用。

### 🛠 技术栈
- **图谱引擎**：[LightRAG](https://github.com/HKU-Smart-OT/LightRAG)
- **记忆层**：[Cognee](https://github.com/topoteretes/cognee)
- **大模型 / 视觉**：Google Gemini 2.5 Pro 与 Flash 模型
- **爬虫**：Apify SDK + Playwright（CDP 后备）
- **基础设施**：Python 3.11+、本地 HTTP 服务器、配置驱动的路径管理

### 📦 快速开始

#### 1. 克隆与设置
```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git
cd OmniGraph-Vault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. 配置
将运行时密钥放在 `~/.hermes/.env` 中，因为 `config.py` 会从该位置加载环境变量：
```bash
GEMINI_API_KEY=你的_gemini_密钥
APIFY_TOKEN=你的_apify_token  # 可选，用于主爬虫
CDP_URL=http://localhost:9223  # 本地 CDP；远程测试用 http://host:port/mcp
```

部署时请始终遵循：

- `~/OmniGraph-Vault` 是 Git 仓库、源码目录、技能目录
- `~/.hermes/omonigraph-vault` 是运行时数据目录

不要把 `~/.hermes/omonigraph-vault` 当成第二份源码仓库。

#### 3. 基础使用
```bash
# 采集微信公众号文章（文本 + 图片 → 知识图谱）
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# 从知识库生成深度综合报告
python kg_synthesize.py "AI 代理领域的最新趋势是什么？"

# 直接查询知识图谱（用于调试或代理端检索）
python query_lightrag.py "解释 OmniGraph‑Vault 的架构。"
```

#### 4. 与 AI 代理集成
OmniGraph‑Vault 设计为可被 Openclaw 或 Hermes Agent 脚本调用。示例集成片段：
```python
import subprocess

def query_kg(question: str) -> str:
    """从代理调用 OmniGraph‑Vault。"""
    result = subprocess.run(
        ["python", "kg_synthesize.py", question],
        capture_output=True, text=True
    )
    return result.stdout
```

### 🔌 浏览器后备（CDP 或 Playwright MCP）

`ingest_wechat.py` 根据 `CDP_URL` 自动选择后备方式：

**本地模式（生产默认）** — 开启 Edge 远程调试：
```powershell
Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
```
在 `~/.hermes/.env` 中设置 `CDP_URL=http://localhost:9223`。

**远程 MCP 模式（本地开发/测试）** — 指向进行中的 Playwright MCP 服务器：
```bash
CDP_URL=http://host:port/mcp
```
`/mcp` 后缀自动触发 MCP 客户端路径，本地无需启动 Edge。

### 📁 项目结构
```
OmniGraph‑Vault/
├── config.py              # 集中化的路径与环境加载
├── ingest_wechat.py       # 微信文章入库（Apify + CDP/MCP）
├── kg_synthesize.py       # 综合与报告生成
├── query_lightrag.py      # 直接图谱查询
├── cognee_wrapper.py      # Cognee 记忆集成
├── cognee_batch_processor.py # Cognee 批处理
├── data_assets/           # 已入库图片与 Markdown 的本地副本
├── specs/                 # 设计规格与测试计划
└── tests/                 # 单元与集成测试
```

**运行时数据**存储在 `~/.hermes/omonigraph-vault/` 下。这里的 `omonigraph` 拼写是当前实现的一部分，请保留，不要在部署时自行改名。

### 🤖 代理部署说明

为了让 Hermes / Openclaw 少猜路径、少猜命令，建议始终遵循：

- `~/OmniGraph-Vault` 作为 Git 仓库与源码目录
- `~/.hermes/omonigraph-vault` 作为运行时数据目录
- 让 Hermes 直接加载仓库的 `skills/`，不要手工复制出第二份旧技能

推荐连接命令：

```bash
hermes config set skills.external_dirs '["/home/<your-user>/OmniGraph-Vault/skills"]'
hermes gateway restart
hermes skills list | grep omnigraph
```

技能中的推荐执行方式：

```bash
cd ~/OmniGraph-Vault && source venv/bin/activate && python ingest_wechat.py "<URL>"
cd ~/OmniGraph-Vault && source venv/bin/activate && python kg_synthesize.py "<QUESTION>" hybrid
```

完整部署步骤请参考 [Deploy.md](Deploy.md)。

### 📄 开源协议
MIT 协议。
