# 🧠 OmniGraph-Vault (全域图谱金库)

[English](#english-version) | [中文版](#中文版)

---

<a name="english-version"></a>
# English Version

**OmniGraph-Vault** is a next-generation personal knowledge management system that transforms web content (WeChat articles) and local documents (PDFs) into an evolving, stateful **Knowledge Graph (KG)**. It leverages **LightRAG** for deep structural indexing and **Cognee** for session-aware memory and cross-session learning.

## 🚀 Key Features
- **Self-Healing Scraper**: Dual-path scraping using Apify AI with a fallback to a **CDP (Chrome DevTools Protocol)** Edge browser bridge to bypass advanced anti-bot measures.
- **Multimodal KG Ingestion**: Automatic extraction of text and images. Every image is semantically described by **Gemini Vision** and indexed into the graph.
- **Stateful Intelligence**: Integrated with **Cognee** to remember your query history, learn your preferences, and canonicalize entities (e.g., merging "知识图谱" and "Knowledge Graph").
- **Local Media Persistence**: A built-in local image server (port 8765) ensuring that your knowledge base remains visually rich even if original online links expire.

## 🛠 Tech Stack
- **KG Engine**: [LightRAG](https://github.com/HKU-Smart-OT/LightRAG)
- **Memory Layer**: [Cognee](https://github.com/topoteretes/cognee)
- **LLM / Vision**: Google Gemini 1.5 Pro & 1.5 Flash
- **Automation**: Playwright & Apify SDK

## 📦 Quick Start

### 1. Installation
```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git
cd OmniGraph-Vault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file:
```bash
GEMINI_API_KEY=your_gemini_key
APIFY_TOKEN=your_apify_token  # Optional
```

### 3. Basic Usage
```bash
# Ingest a WeChat article or PDF
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# Generate a synthesized report
python kg_synthesize.py "Synthesize everything you know about AI Agents."

# Direct KG query
python query_lightrag.py "What are the core components of OmniGraph?"
```

---

<a name="中文版"></a>
# 中文版

**OmniGraph-Vault** 是一款下一代个人知识管理系统。它将网页内容（如微信公众号文章）和本地文档（PDF）转化为一个不断进化的、有状态的**知识图谱 (Knowledge Graph)**。系统利用 **LightRAG** 进行深度的结构化索引，并结合 **Cognee** 实现会话感知记忆和跨会话学习。

## 🚀 核心特性
- **自愈式爬虫**: 采用双路径抓取逻辑。优先使用 Apify AI 抓取，若遇到高强度反爬（如验证码），自动回退到基于 **CDP (Chrome DevTools Protocol)** 的 Edge 浏览器桥接模式。
- **多模态图谱入库**: 自动提取文本和图片。每一张图片都会通过 **Gemini Vision** 生成语义描述，并直接索引到知识图谱中。
- **有状态智能**: 集成 **Cognee** 记忆层，能够记住您的查询历史、学习您的偏好，并实现概念归一化（例如自动合并“知识图谱”和“Knowledge Graph”节点）。
- **本地媒体持久化**: 内置本地图片服务器（端口 8765），确保即使原始链接失效，您的知识库依然图文并茂。

## 🛠 技术栈
- **图谱引擎**: [LightRAG](https://github.com/HKU-Smart-OT/LightRAG)
- **记忆层**: [Cognee](https://github.com/topoteretes/cognee)
- **大模型 / 视觉**: Google Gemini 1.5 Pro & 1.5 Flash
- **自动化**: Playwright & Apify SDK

## 📦 快速上手

### 1. 安装
```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git
cd OmniGraph-Vault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置
创建 `.env` 文件并填入密钥：
```bash
GEMINI_API_KEY=您的Gemini密钥
APIFY_TOKEN=您的Apify密钥  # 可选
```

### 3. 基础操作
```bash
# 采集微信文章或 PDF
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# 生成深度综合报告
python kg_synthesize.py "综合分析我的知识库中关于 AI Agent 的所有信息。"

# 直接查询图谱
python query_lightrag.py "OmniGraph 的核心组件有哪些？"
```

---

## 🔌 Windows Edge 桥接模式
若因机器人检测导致抓取失败，请在 Windows 宿主机上开启 Edge 调试模式：
```powershell
Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
```

## 📄 开源协议
MIT License.
