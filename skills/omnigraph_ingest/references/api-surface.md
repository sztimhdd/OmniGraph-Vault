# omnigraph_ingest — API Surface Reference

## Entry Point

Shell wrapper: `skills/omnigraph_ingest/scripts/ingest.sh`

## CLI Interface

```bash
scripts/ingest.sh <url-or-file-path>
```

Single positional argument: a WeChat URL or an absolute/relative path to a `.pdf` file.

## Required Environment Variables

| Variable | Source | Description |
|---|---|---|
| `GEMINI_API_KEY` | `~/.hermes/.env` | Required. All LLM processing, entity extraction, image description. |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OMNIGRAPH_ROOT` | `$HOME/Desktop/OmniGraph-Vault` | Path to the repo root. Set this if the repo is not at the default location. |
| `APIFY_TOKEN` | (empty) | Enables Apify as the primary scraper. Falls back to CDP if unset or quota exceeded. |
| `CDP_URL` | `http://localhost:9223` | Chrome DevTools Protocol endpoint used as scraping fallback. |

## Dispatch Logic

| Input | Backend Script | Notes |
|---|---|---|
| `*.pdf` / `*.PDF` path | `multimodal_ingest.py <path>` | PDF extraction with embedded image processing |
| `mp.weixin.qq.com/*` URL | `ingest_wechat.py <url>` | WeChat article via Apify → CDP fallback |
| Other URL | Rejected by SKILL.md guard | Wrapper will run ingest_wechat.py if called directly; guard is in the skill |

## Output Format (success)

```
Starting ingestion — this may take 30–120 seconds...
<article-title> ingested successfully
Images: X downloaded, Y described
Entity extraction queued. Query it with the omnigraph_query skill.
```

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Error — see stderr for human-readable message |

## Error Messages

| Condition | Stderr Message |
|---|---|
| `GEMINI_API_KEY` not set | `⚠️ Configuration error: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env` |
| Repo not found at `OMNIGRAPH_ROOT` | `⚠️ Setup error: OmniGraph-Vault repo not found at <path>` |
| venv not found | `⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv` |
| No argument given | `⚠️ Usage: ingest.sh <wechat-url-or-pdf-path>` |
| Apify quota exceeded | Logged as warning; CDP fallback tried automatically |
| CDP not reachable | Python script prints: `⚠️ CDP fallback unavailable. Start Edge: msedge --remote-debugging-port=9223` |

## Runtime Data Paths

All data written to `~/.hermes/omonigraph-vault/` (note: typo in directory name is intentional — baked into config.py):

| Path | Content |
|---|---|
| `~/.hermes/omonigraph-vault/lightrag_storage/` | LightRAG knowledge graph index |
| `~/.hermes/omonigraph-vault/images/<hash>/` | Downloaded article images + metadata |
| `~/.hermes/omonigraph-vault/entity_buffer/` | Extracted entities awaiting batch canonicalization |

## Dependencies

- venv at `$OMNIGRAPH_ROOT/venv` with all `requirements.txt` dependencies installed
- Image server at port 8765 (for inline image URLs in synthesis output — not required for ingestion itself)
- `config.py` loads `~/.hermes/.env` at import time; manual `source ~/.hermes/.env` is not required

## Repo / Runtime Separation

| Path | Purpose |
|---|---|
| `~/Desktop/OmniGraph-Vault/` | Source repo — Python scripts, skills, tests |
| `~/.hermes/omonigraph-vault/` | Runtime data — graph index, images, canonical map |

Scripts always run from the repo root (`$OMNIGRAPH_ROOT`). Runtime data is never in the repo.
