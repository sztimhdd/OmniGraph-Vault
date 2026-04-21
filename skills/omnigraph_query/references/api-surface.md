# omnigraph_query — API Surface Reference

## Entry Point

Shell wrapper: `skills/omnigraph_query/scripts/query.sh`

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
| `GEMINI_API_KEY` | `~/.hermes/.env` | Required. LLM synthesis, embedding, and Cognee memory. |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OMNIGRAPH_ROOT` | `$HOME/Desktop/OmniGraph-Vault` | Path to the repo root. Set this if the repo is not at the default location. |

## Query Modes

| Mode | Description | Best for |
|---|---|---|
| `naive` | Simple keyword retrieval | Fastest; exact term lookup |
| `local` | Entity-centric graph traversal | Questions about specific entities and their relationships |
| `global` | Theme-level conceptual patterns | Broad questions, trend analysis, cross-domain topics |
| `hybrid` | Combines local + global | Default; balanced results for most queries |
| `mix` | Vector search + graph traversal | When semantic similarity matters alongside graph structure |

## Output

Synthesis report written to two places simultaneously:

- **stdout** — displayed in chat as Markdown
- `~/.hermes/omonigraph-vault/synthesis_output.md` — persistent copy for reference

Inline image URLs in the report require the image server running at port 8765:
```bash
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &
```

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success (includes "empty result" — no Python error) |
| 1 | Error — see stderr for human-readable message |

## Error Messages

| Condition | Stderr Message |
|---|---|
| `GEMINI_API_KEY` not set | `⚠️ Configuration error: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env` |
| Repo not found at `OMNIGRAPH_ROOT` | `⚠️ Setup error: OmniGraph-Vault repo not found at <path>` |
| venv not found | `⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv` |
| No query given | `⚠️ Usage: query.sh '<question>' [mode]` |
| Empty KB / no results | Python script returns low-confidence response; skill advises user to ingest first |

## Runtime Data Paths

| Path | Content |
|---|---|
| `~/.hermes/omonigraph-vault/lightrag_storage/` | LightRAG knowledge graph queried for retrieval |
| `~/.hermes/omonigraph-vault/canonical_map.json` | Entity normalization map applied to query before retrieval |
| `~/.hermes/omonigraph-vault/synthesis_output.md` | Last synthesis report (overwritten each query) |

## Repo / Runtime Separation

| Path | Purpose |
|---|---|
| `~/Desktop/OmniGraph-Vault/` | Source repo — `kg_synthesize.py`, skills, tests |
| `~/.hermes/omonigraph-vault/` | Runtime data — LightRAG index, canonical map, synthesis output |
