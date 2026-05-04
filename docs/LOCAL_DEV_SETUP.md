# Local Dev Setup — OmniGraph-Vault (Windows)

> Part of quick task 260504-g7a. This document is the canonical source for
> the five `OMNIGRAPH_*` env vars that enable local pipeline runs on the
> user's Windows dev box against `.dev-runtime/`.

## 1. Purpose & scope

Local dev lets you exercise the full ingestion / classification / vision
pipeline on your Windows workstation without SSH'ing into the production
Hermes PC and without risking DeepSeek quota. Cisco Umbrella intercepts
outbound TLS, so we isolate the pipeline onto Vertex AI (SA auth) and
route all runtime data into `.dev-runtime/` outside the Hermes-owned
`~/.hermes/omonigraph-vault/` directory.

What local dev is:

- A debugging + smoke-test harness for ingestion, classification, and
  vision cascade behavior.
- A way to reproduce user-reported issues against code changes before
  pushing to Hermes.

What local dev is NOT:

- A replacement for the production Hermes E2E pipeline.
- A cron schedule — Windows dev has no cron; Hermes remains the operator
  of record for scheduled scans.
- Stateful between sessions in the same sense as Hermes (LightRAG state
  in `.dev-runtime/lightrag_storage/` persists, but Cognee / SQLite DB
  data are scoped to that runtime root).

## 2. Prerequisites

- Python 3.11+ with `venv/` activated (Windows layout: `venv\Scripts\`).
- `.dev-runtime/` pre-populated with the following subdirectories:
  - `data/` (SQLite databases — `articles.db`, etc.)
  - `digests/` (daily digest outputs)
  - `gcp-paid-sa.json` (Vertex AI Service Account credentials)
  - `images/` (per-article image caches)
  - `lightrag_storage/` (knowledge graph state)
  - `logs/` (bootstrap + image server output)
  - `rss_content/` (cached RSS article bodies)
- `gcp-paid-sa.json` Service Account JSON file present at the path
  referenced by `GOOGLE_APPLICATION_CREDENTIALS`.

## 3. `.dev-runtime/` layout

| Subdir | Contents |
|--------|----------|
| `data/` | SQLite — `kol_scan.db`, `articles.db`, `rss_articles.db`. |
| `digests/` | Daily digest Markdown outputs. |
| `images/` | Per-article image subdirectories (served by image server on 8765). |
| `lightrag_storage/` | NanoVectorDB + Kuzu graph state for LightRAG. |
| `logs/` | Bootstrap + image-server + pipeline stdout/stderr. |
| `rss_content/` | Cached `content_html` bodies for RSS arm. |
| `gcp-paid-sa.json` | Vertex AI SA JSON (referenced by env, not served). |

## 4. The five `OMNIGRAPH_*` env vars

Add these to `.dev-runtime/.env`. The bootstrap script (§ 7) loads this
file without overwriting pre-existing process env, so `~/.hermes/.env`
fallback values survive for dev variables not yet overridden here.

| Var | Required | Default | Purpose |
|-----|----------|---------|---------|
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | `deepseek` (production parity) or `vertex_gemini` (local sandbox). Unset == DeepSeek. |
| `OMNIGRAPH_LLM_MODEL` | No | `gemini-3.1-flash-lite-preview` | Vertex Gemini model ID. Applies when `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`. |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS` | No | _(empty)_ | Comma-list of providers to drop from the Vision cascade. Typical local value: `siliconflow,openrouter` (no paid balances / no keys). |
| `OMNIGRAPH_BASE_DIR` | Yes for local dev | `~/.hermes/omonigraph-vault` | Absolute path to runtime data root. Typical local value: `C:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime`. |
| `OMNIGRAPH_LLM_TIMEOUT_SEC` | No | `600` | Int seconds; applied to Vertex Gemini LLM calls only. DeepSeek path unaffected. |

### 4.1 SA auth env (Vertex mode)

For `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` you also need:

| Var | Required | Example |
|-----|----------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | `C:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime\gcp-paid-sa.json` |
| `GOOGLE_CLOUD_PROJECT` | Yes | `banded-totality-485901` (or your project id) |
| `GOOGLE_CLOUD_LOCATION` | No | `global` (default; production recommended) |

### 4.2 DeepSeek cross-coupling note

`lib/__init__.py` eagerly imports `lib.llm_deepseek` which raises at
import time if `DEEPSEEK_API_KEY` is unset. Even in full `vertex_gemini`
mode you must set a value — use a dummy if you don't have a real one:

```
DEEPSEEK_API_KEY=dummy
```

This is CLAUDE.md § Phase 5 DeepSeek cross-coupling (FLAG 2).

## 5. Image server

The LightRAG embedding path resolves `http://localhost:8765/<hash>/<file>.jpg`
to locally cached images during synthesis. Start the server from your
`OMNIGRAPH_BASE_DIR`'s images directory:

PowerShell (Windows):

```powershell
cd $env:OMNIGRAPH_BASE_DIR\images
venv\Scripts\python -m http.server 8765
```

Bash / WSL:

```bash
cd "$OMNIGRAPH_BASE_DIR/images"
venv/Scripts/python -m http.server 8765
```

The bootstrap script in § 7 handles this automatically in the background.

## 6. First smoke command + expected output

```powershell
venv\Scripts\python -c "from lib.llm_complete import get_llm_func; print(get_llm_func().__name__)"
# Expect: vertex_gemini_model_complete  (if OMNIGRAPH_LLM_PROVIDER=vertex_gemini)
# Expect: deepseek_model_complete       (if unset / deepseek)

venv\Scripts\python -c "import config; print(config.BASE_DIR)"
# Expect: your OMNIGRAPH_BASE_DIR value (or ~/.hermes/omonigraph-vault if unset)
```

## 7. Bootstrap scripts

```powershell
# Windows primary path:
scripts\local_dev_start.ps1
```

```bash
# WSL / Git Bash fallback:
bash scripts/local_dev_start.sh
```

Either script verifies the 5 prereqs, loads `.dev-runtime/.env` without
overwriting existing env, starts the image server on 8765, and prints
the next-step smoke commands.

## 8. `PYTHONIOENCODING=utf-8` trap

Windows `cmd.exe` and PowerShell default stdout to cp1252. Python scripts
that write UTF-8 Markdown (Chinese article content, emoji, graph
synthesis outputs) will raise `UnicodeEncodeError: 'charmap' codec can't
encode ...` when stdout is redirected to a file.

Fix: always set `PYTHONIOENCODING=utf-8` before any pipeline command.

The bootstrap scripts (§ 7) set this automatically on startup. For
persistence across shell sessions, add to your PowerShell profile:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

or `~/.bashrc` (WSL):

```bash
export PYTHONIOENCODING=utf-8
```

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `google.genai.errors.ServerError: 503` repeated 4× | Vertex Gemini intermittent | Retry is already implemented (2s/4s/8s backoff); if persistent, temporarily set `OMNIGRAPH_LLM_PROVIDER=deepseek`. |
| `ApifyClient: quota exceeded` | Apify free tier daily cap | Set `APIFY_TOKEN=` (empty) to force CDP → MCP fallback per CLAUDE.md "Testing the CDP / MCP Scraping Path". |
| `MCP server 404 / timeout` | Remote MCP test server down | Set `CDP_URL=http://localhost:9223` + start Edge with `--remote-debugging-port=9223` (CLAUDE.md Path 2). |
| `LightRAG schema drift` / empty graph | Old `lightrag_storage/` dims mismatch | Wipe `$OMNIGRAPH_BASE_DIR/lightrag_storage` and restart. |
| `UnicodeEncodeError: 'charmap'` | Windows cp1252 stdout | `set PYTHONIOENCODING=utf-8` (§ 8). |
| `DEEPSEEK_API_KEY is not set` on import | Phase 5 cross-coupling (CLAUDE.md FLAG 2) | Set `DEEPSEEK_API_KEY=dummy` in `.dev-runtime/.env` even when using Vertex (§ 4.2). |
| `GOOGLE_CLOUD_PROJECT is not set` when calling Vertex | SA env missing / blocked by `config.py` pop guard | Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set BEFORE `config.load_env()` runs. The bootstrap script handles ordering. |
| Vision cascade stalls on SiliconFlow | No balance / no key | Set `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter` to fall straight to Gemini Vision. |

## 10. Switch back to Hermes-parity mode

To simulate production Hermes locally (no Vertex, no BASE_DIR override):

| Local | Hermes | Notes |
|-------|--------|-------|
| `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` | unset | Hermes uses DeepSeek by default. |
| `OMNIGRAPH_LLM_MODEL=...` | unset | N/A on DeepSeek. |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter` | unset | Hermes has paid balances + keys. |
| `OMNIGRAPH_BASE_DIR=C:\...\.dev-runtime` | unset | Hermes uses `~/.hermes/omonigraph-vault/`. |
| `OMNIGRAPH_LLM_TIMEOUT_SEC=600` | unset | Only applies to Vertex path. |

Unsetting all five reverts to production Hermes behavior byte-for-byte.

## 11. Smoke sequence

Once the bootstrap script has succeeded, the typical smoke flow is:

```powershell
# 1. Verify dispatcher + BASE_DIR
venv\Scripts\python -c "from lib.llm_complete import get_llm_func; print(get_llm_func().__name__)"
venv\Scripts\python -c "import config; print(config.BASE_DIR)"

# 2. Single-article ingest (bandwidth-dependent)
venv\Scripts\python ingest_wechat.py "https://mp.weixin.qq.com/s/<test-article-id>"

# 3. Query the graph
venv\Scripts\python query_lightrag.py "What is LightRAG?"
```

Stop the image server by killing the PID printed by the bootstrap script
(`Stop-Process -Id <pid>` on Windows, `kill <pid>` on bash).
