# omnigraph_search — API Surface Reference

## Entry Point

Shell wrapper: `skills/omnigraph_search/scripts/query.sh`

## CLI Interface

```bash
scripts/query.sh '<query text>'
scripts/query.sh '<query text>' <mode>
```

## Arguments

| Argument | Required | Description |
|---|---|---|
| `<query text>` | Yes | Natural language question or topic. Quote with single or double quotes. |
| `<mode>` | No (default: `hybrid`) | Retrieval mode: `naive`, `local`, `global`, `hybrid`, `mix` |

## Required Environment Variables

| Variable | Source | Description |
|---|---|---|
| `GEMINI_API_KEY` | `~/.hermes/.env` | Required. LLM call for retrieval and embedding. |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OMNIGRAPH_ROOT` | `$HOME/OmniGraph-Vault` | Path to the repo root. |

## Query Modes

| Mode | Description |
|---|---|
| `naive` | Simple keyword retrieval; fastest |
| `local` | Entity-centric graph traversal |
| `global` | Theme-level conceptual patterns |
| `hybrid` | Default; combines local + global |
| `mix` | Vector search + graph traversal |

## Output

- **stdout only** — raw retrieval text from LightRAG, rendered as Markdown in chat
- No writeback to disk (this skill does not save output to any file)
- No inline images (no image server dependency)

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success (empty-result is not an error) |
| 1 | Error — see stderr for human-readable message |

## Error Messages

| Condition | Stderr Message |
|---|---|
| `GEMINI_API_KEY` not set | `⚠️ Configuration error: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env` |
| Repo not found | `⚠️ Setup error: OmniGraph-Vault repo not found at <path>` |
| venv not found | `⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv` |
| No query given | `⚠️ Usage: query.sh '<question>' [mode]` |

## Runtime Data Paths

| Path | Content |
|---|---|
| `~/.hermes/omonigraph-vault/lightrag_storage/` | LightRAG knowledge graph queried for retrieval (read-only) |

## Repo / Runtime Separation

| Path | Purpose |
|---|---|
| `$OMNIGRAPH_ROOT` | Source repo — `omnigraph_search/query.py`, skill, tests |
| `~/.hermes/omonigraph-vault/` | Runtime data — LightRAG index (read-only for this skill) |

## Relationship to Sibling Skills

- `omnigraph_query` — same LightRAG backend, adds a synthesis layer (long-form report) and memory recall; use it when you need a formatted report
- `graphify` — queries the CODE graph (different `graph.json` file), NOT the domain graph
