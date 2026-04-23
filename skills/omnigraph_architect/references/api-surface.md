# omnigraph_architect — API Surface Reference

## Entry Point

Shell wrapper: `skills/omnigraph_architect/scripts/architect.sh`

## CLI Interface

```bash
scripts/architect.sh <mode> "<input>"
```

Three modes: `propose`, `query`, `ingest`.

| Mode | Input | Backend |
|------|-------|---------|
| `propose` | Architecture question + Q1/Q2 context | Loads `rules_engine.json`, prepends rules to query, calls `kg_synthesize.py` in hybrid mode |
| `query` | Freeform architecture question | Calls `kg_synthesize.py` directly in hybrid mode |
| `ingest` | GitHub repository URL | Calls `ingest_github.py` |

## Required Environment Variables

| Variable | Source | Description |
|---|---|---|
| `GEMINI_API_KEY` | `~/.hermes/.env` | Required. All LLM processing. |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OMNIGRAPH_ROOT` | `$HOME/Desktop/OmniGraph-Vault` | Path to the repo root. |
| `GITHUB_TOKEN` | (empty) | Avoids GitHub API rate limiting for Ingest mode. |

## Propose Mode — Rules Injection

The `propose` mode reads `rules_engine.json` from the project root and formats all rules as:

```
[rule_NNN] (weight N) recommendation text | dont_use: item1, item2
```

This formatted block is prepended to the user's question and sent to `kg_synthesize.py` as a single query string. The synthesis engine is not modified — rules context is injected at the shell layer.

## Rules Engine Schema

Each rule in `rules_engine.json`:

```json
{
  "id": "rule_001",
  "name": "sql_first",
  "condition": "when condition applies",
  "recommendation": "what to recommend",
  "dont_use": ["item1", "item2"],
  "weight": 9,
  "tags": ["solo-dev", "database"],
  "test_scenario": "description for testing"
}
```

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Error — see stderr for human-readable message |

## Error Messages

| Condition | Stderr Message |
|---|---|
| `GEMINI_API_KEY` not set | `⚠️ Configuration error: GEMINI_API_KEY is not set` |
| Repo not found | `⚠️ Setup error: OmniGraph-Vault repo not found at <path>` |
| venv not found | `⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv` |
| `rules_engine.json` missing | `⚠️ Setup error: rules_engine.json not found` |
| Non-GitHub URL for ingest | `⚠️ Ingest mode only accepts GitHub repository URLs` |
| No mode argument | `Usage: architect.sh <propose\|query\|ingest> <input>` |
| Unknown mode | `⚠️ Unknown mode: '<mode>'` |

## Runtime Data Paths

| Path | Content |
|---|---|
| `$OMNIGRAPH_ROOT/rules_engine.json` | 28 architecture rules (read-only by architect.sh) |
| `~/.hermes/omonigraph-vault/lightrag_storage/` | LightRAG knowledge graph index |
| `$OMNIGRAPH_ROOT/entity_registry.json` | GitHub URL dedup registry (written by ingest_github.py) |
