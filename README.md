# 🧠 OmniGraph-Vault

**OmniGraph-Vault** is a high-performance, autonomous knowledge ingestion and synthesis pipeline. It transforms raw web content (primarily WeChat articles) and PDF documents into a structured, queryable **Knowledge Graph (KG)** powered by LightRAG and Gemini AI.

## 🚀 Key Features

- **Self-Healing Scraper**: A dual-path scraping logic that prioritizes Apify's AI Scraper and automatically falls back to a **CDP (Chrome DevTools Protocol) Bridge** if anti-scraping measures (like WeChat's verification pages) are detected.
- **Multimodal KG Ingestion**: Not just text—it downloads images, stores them locally, and uses **Gemini Vision** to generate detailed semantic descriptions that are indexed directly into the graph.
- **Hybrid RAG Synthesis**: Combines vector similarity with graph-based relationship traversal to produce deep, cross-article synthesized reports using **Gemini 2.5 Pro**.
- **Immersive Local Storage**: Includes a built-in local image server to ensure that your knowledge base remains fully readable with inline images, even if original CDN links expire.

## 🛠️ Tech Stack

- **KG Engine**: [LightRAG](https://github.com/HKU-Smart-OT/LightRAG)
- **Intelligence**: Google Gemini (Pro & Flash)
- **Automation**: Playwright & Apify SDK
- **Backend**: Python (WSL-optimized)

## 📦 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/sztimhdd/OmniGraph-Vault.git
   cd OmniGraph-Vault
   ```

2. Setup a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure your credentials:
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

## ⌨️ Usage

### 1. Ingest a WeChat Article
```bash
python ingest_wechat.py "https://mp.weixin.qq.com/s/your-article-id"
```

### 2. Synthesize Knowledge
```bash
python kg_synthesize.py "Provide a comprehensive guide on AI Agent efficiency based on my vault."
```

### 3. Direct KG Query
```bash
python query_lightrag.py "Who is Andrej Karpathy?"
```

## 🛡️ License

MIT License.
