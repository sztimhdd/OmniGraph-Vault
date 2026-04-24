# OmniGraph-Vault Deployment Guide

The authoritative guide for deploying OmniGraph-Vault skills into a running Hermes Agent or Openclaw instance.

**One principle governs everything:**

- **The Git repo is the single source of truth** for code, skills, and tests
- **`~/.hermes/omonigraph-vault/`** is runtime data only — graph index, images, synthesis output
- Never mix source code and runtime data in the same directory

---

## 1. System Requirements

| Requirement | Minimum |
|---|---|
| OS | Linux / WSL2 (Ubuntu 20.04+) / macOS / Windows with Git Bash |
| Python | 3.11+ |
| Git | Any recent version |
| Agent | Hermes Agent or Openclaw |
| API Key | Google Gemini API Key (`GEMINI_API_KEY`) |
| Optional | `APIFY_TOKEN` (primary scraper), Edge/Chrome CDP (scraping fallback), `GITHUB_TOKEN` (GitHub ingestion) |

---

## 2. Directory Layout

```
~/OmniGraph-Vault/                  # Git repo: code, skills/, tests/, docs
├── skills/
│   ├── omnigraph_ingest/           # Ingest WeChat articles + PDFs
│   ├── omnigraph_query/            # Query the knowledge graph
│   └── omnigraph_architect/        # Architecture advice + GitHub repo ingestion
├── rules_engine.json               # 28 solo-dev architecture rules
├── skill_runner.py                 # Local skill test harness (multi-turn)
├── tests/skills/                   # Test suites for all 3 skills
├── config.py                       # Loads ~/.hermes/.env, sets all paths
└── venv/                           # Python virtual environment

~/.hermes/.env                      # Shared env vars (Hermes + OmniGraph-Vault)
~/.hermes/omonigraph-vault/         # Runtime data ONLY (note: "omonigraph" typo is intentional)
├── lightrag_storage/               # LightRAG knowledge graph index
├── images/{hash}/                  # Downloaded article images
├── entity_buffer/                  # Extracted entities awaiting canonicalization
├── canonical_map.json              # Entity normalization map
└── synthesis_output.md             # Last synthesis output
```

**Critical:** the runtime directory is `omonigraph-vault` (with the typo). This is baked into `config.py` and all deployed environments. Do NOT rename it.

---

## 3. Skills Catalog

| Skill | Modes | Trigger Phrases | Entry Script |
|---|---|---|---|
| `omnigraph_ingest` | WeChat URL, PDF path | "add this to my KB", "ingest this article", "save this" | `scripts/ingest.sh <url-or-path>` |
| `omnigraph_query` | naive, local, global, hybrid, mix | "what do I know about X", "search my KB" | `scripts/query.sh "<question>" [mode]` |
| `omnigraph_architect` | propose, query, ingest | "what stack should I use", "recommend tech for", "add this GitHub repo" | `scripts/architect.sh <mode> "<input>"` |

### omnigraph_architect modes

| Mode | What it does | Example |
|---|---|---|
| `propose` | Multi-turn guided stack recommendation using 28 rules from `rules_engine.json` | `architect.sh propose "AI chatbot for customer support"` |
| `query` | Single-turn architecture question answered via the knowledge graph | `architect.sh query "What is LightRAG?"` |
| `ingest` | Add a GitHub repo's README + metadata to the knowledge graph | `architect.sh ingest "https://github.com/org/repo"` |

---

## 4. Installation

### 4.1 Clone the repo

```bash
git clone https://github.com/sztimhdd/OmniGraph-Vault.git ~/OmniGraph-Vault
cd ~/OmniGraph-Vault
```

### 4.2 Create venv and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate          # Linux/macOS
# source venv/Scripts/activate    # Windows Git Bash
pip install -r requirements.txt
```

### 4.3 Verify imports

```bash
python -c "import lightrag; print('LightRAG OK')"
python -c "import cognee; print('Cognee OK')"
python -c "from google import genai; print('google-genai OK')"
```

### 4.4 Restore KB Snapshot (recommended)

Download the pre-built knowledge graph from the GitHub Release instead of starting with an empty graph. This avoids re-ingesting 49 GitHub repos + 7 KOL articles (~60 minutes).

```bash
mkdir -p ~/.hermes/omonigraph-vault/images

# Download release assets
cd ~/OmniGraph-Vault
gh release download v2.0-kb -p "lightrag_storage_v2.0.tar.gz"

# Extract into runtime directory
tar -xzf lightrag_storage_v2.0.tar.gz -C ~/.hermes/omonigraph-vault/

# Verify
ls ~/.hermes/omonigraph-vault/lightrak_storage/
# Expected: graph_chunk_entity_relation.graphml  kv_store_*.json  vdb_*.json
```

`entity_registry.json` (the ingestion dedup registry) is committed to the repo and already present after `git clone`. It prevents `ingest_github.py` from re-indexing already-ingested repos.

**If you skip the snapshot** (empty graph), run this once after setup to re-build (~60 min):

```bash
cd ~/OmniGraph-Vault
source venv/bin/activate
python batch_ingest_github.py
```

### 4.5 Configure environment variables

Create `~/.hermes/.env`:

```bash
GEMINI_API_KEY=your_gemini_key_here
APIFY_TOKEN=your_apify_token          # optional
CDP_URL=http://localhost:9223          # optional
GITHUB_TOKEN=your_github_token        # optional, for ingest_github.py
```

### 4.6 Start image server (optional, for inline images in synthesis output)

```bash
cd ~/.hermes/omonigraph-vault && python3 -m http.server 8765 --directory images &
```

---

## 5. Connect Skills to Hermes

**This is the most important deployment step.**

### DO NOT copy skills into `~/.hermes/skills/`

Copying creates drift between the repo and what Hermes actually uses. Instead, point Hermes at the repo directly.

### Configure `skills.external_dirs`

```bash
hermes config set skills.external_dirs '["/home/<your-user>/OmniGraph-Vault/skills"]'
```

Or edit `~/.hermes/config.yaml` directly:

```yaml
skills:
  external_dirs:
    - /home/<your-user>/OmniGraph-Vault/skills
```

Then restart the gateway:

```bash
hermes gateway restart
```

### Verify skill registration

```bash
hermes skills list | grep omnigraph
```

Expected output (3 skills):

```
omnigraph_ingest     — Ingest WeChat articles and PDFs into the knowledge graph
omnigraph_query      — Query the knowledge graph by natural language
omnigraph_architect  — Architecture advice, knowledge queries, and GitHub repo ingestion
```

---

## 6. Verification Commands

### 6.1 Structural validation (no API calls)

```bash
cd ~/OmniGraph-Vault
source venv/bin/activate
python skill_runner.py skills/ --validate --test-all
```

Expected: `PASS omnigraph_architect`, `PASS omnigraph_ingest`, `PASS omnigraph_query`

### 6.2 Full test suite (calls Gemini API)

```bash
python skill_runner.py skills/ --test-all
```

Expected: `30/30 passed` (11 architect + 9 ingest + 10 query)

### 6.3 Direct script tests

```bash
# Query mode
python kg_synthesize.py "What do I know about AI agent architectures?" hybrid

# Ingest a test article (uses Gemini API)
python ingest_wechat.py "https://mp.weixin.qq.com/s/<article-id>"

# Architect propose mode (loads rules_engine.json)
bash skills/omnigraph_architect/scripts/architect.sh propose "solo AI chatbot"

# Architect query mode
bash skills/omnigraph_architect/scripts/architect.sh query "What is FAISS?"
```

### 6.4 Hermes live dispatch test

```bash
hermes chat -s omnigraph_ingest -q "add this to my kb"
# Expected: guard clause asking for URL (no crash)

hermes chat -s omnigraph_query -q "what do I know about LightRAG?"
# Expected: synthesis from knowledge graph

hermes chat -s omnigraph_architect -q "what stack should I use for a solo AI chatbot?"
# Expected: default guess + asks Q1 (project type)
```

---

## 7. Gate 7 Validation Checklist

Run these checks after deployment to confirm the system works end-to-end.

| # | Check | Command | Pass Criteria |
|---|-------|---------|---------------|
| G7-1 | Skills registered from repo | `hermes skills list \| grep omnigraph` | Shows 3 skills sourced from `~/OmniGraph-Vault/skills/` |
| G7-2 | Shell wrappers work from `/tmp` | `cd /tmp && bash ~/OmniGraph-Vault/skills/omnigraph_ingest/scripts/ingest.sh` | Exits non-zero with "Usage: ingest.sh" message (no Python traceback) |
| G7-3 | Ingest routing | `hermes chat "add this article to my knowledge base"` | Routes to `omnigraph_ingest`, asks for URL |
| G7-4 | Query routing | `hermes chat "what do I know about LightRAG?"` | Routes to `omnigraph_query`, returns synthesis |
| G7-5 | Architect routing | `hermes chat "what stack should I use for my project?"` | Routes to `omnigraph_architect`, starts propose flow |
| G7-6 | Config error guard | Unset `GEMINI_API_KEY`, run `ingest.sh "<url>"` | Human-readable error message, no traceback |
| G7-7 | Cross-article synthesis | `kg_synthesize.py "Compare Hermes and OpenClaw architectures" hybrid` | Response references entities from 2+ ingested articles |
| G7-8 | Skill_runner green | `python skill_runner.py skills/ --test-all` | 30/30 passed |
| G7-9 | No skill drift | Skills sourced from repo, not `~/.hermes/skills/` | `hermes skills list` shows repo path |
| G7-10 | Architect ingest mode | `architect.sh ingest "https://github.com/NousResearch/hermes-agent"` | Repo indexed, no crash |

---

## 8. Upgrading

```bash
cd ~/OmniGraph-Vault
git pull --ff-only origin main
source venv/bin/activate
pip install -r requirements.txt
hermes gateway restart
```

Never update `~/.hermes/omonigraph-vault/` — it's runtime data, not source code.

---

## 9. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Skills not showing | Hermes not loading repo `skills/` | Check `skills.external_dirs` → `hermes gateway restart` |
| Skills out of date | Copied old skills to `~/.hermes/skills/` | Delete copies, use `external_dirs` |
| Runtime data missing | Wrong directory path | Ensure `~/.hermes/omonigraph-vault` (with typo) exists |
| Query returns nothing | Empty knowledge graph | Restore KB snapshot (section 4.4), or run `python batch_ingest_github.py` |
| CDP scraping fails | Edge not in debug mode | Start Edge: `msedge --remote-debugging-port=9223` |
| GitHub ingest rate-limited | No `GITHUB_TOKEN` set | Add token to `~/.hermes/.env` (60 req/hr → 5000/hr) |
| `rules_engine.json` not found | architect propose mode fails | Ensure file exists at repo root (28 rules) |
