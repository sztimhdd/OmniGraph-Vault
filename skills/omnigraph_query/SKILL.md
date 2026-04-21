---
name: omnigraph_query
description: Query the OmniGraph-Vault knowledge graph by natural language and return a synthesized Markdown report.
triggers:
  - "what do I know about"
  - "search my knowledge base"
  - "search my kb"
  - "find in graph"
  - "query the knowledge base"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_query

## Purpose

Query the OmniGraph-Vault knowledge graph using natural language. Retrieves relevant entities and relationships from LightRAG, combines them with Cognee memory context, and generates a synthesized Markdown report via Gemini.

## When to trigger this skill

- User asks "what do I know about X"
- User asks "search my kb for X"
- User asks "find information about X in my knowledge base"
- User asks for a comparison, summary, or explanation of topics that may have been ingested

## When NOT to trigger this skill

- User wants to add or ingest new content → use `omnigraph_ingest` instead
- User wants a formal long-form synthesis report → use `omnigraph_synthesize` instead
- User asks about graph health, node counts, or pipeline status → use `omnigraph_status` instead
- User wants to delete entities or manage the graph → use `omnigraph_manage` instead

## Decision tree

### Case 1: Standard natural-language query

Run:
```bash
python kg_synthesize.py "<user question>" hybrid
```

Use `hybrid` mode by default. It combines vector and graph retrieval for the best results.

### Case 2: User explicitly requests a retrieval mode

Supported modes: `naive`, `local`, `global`, `hybrid`, `mix`

Run:
```bash
python kg_synthesize.py "<user question>" <mode>
```

For example, if user says "use local mode" or "local search only":
```bash
python kg_synthesize.py "What are AI agent architectures?" local
```

### Case 3: User asks to delete, clear, or modify graph data

Do NOT perform any deletion. Respond:
"⚠️ Modifying the knowledge graph is handled by the `omnigraph_manage` skill. Please use that skill for any delete, reindex, or entity management operations."

### Case 4: GEMINI_API_KEY not set

Respond: "⚠️ Configuration error: GEMINI_API_KEY is not set. Please add it to ~/.hermes/.env and restart."

### Case 5: Query returns no results

If `kg_synthesize.py` returns an empty or low-confidence response, tell the user:
"No relevant content found for '<query>' in the knowledge graph. Try ingesting relevant articles first using the `omnigraph_ingest` skill."

## Query modes explained

| Mode | Use when |
|------|----------|
| `naive` | Simple keyword retrieval, fastest |
| `local` | Entity-centric: relationships around specific nodes |
| `global` | Theme-level: broader conceptual patterns |
| `hybrid` | Default: combines local + global for balanced results |
| `mix` | Combines vector search + graph traversal |

## Output format

- Results with more than 5 items: Markdown table with columns Entity, Confidence, Sources
- Results with 5 or fewer items: bullet list
- COUNT queries (e.g. "how many articles about X"): plain number — "3 articles about AI agents in the graph"
- Errors: "⚠️ [Error type]: [What happened]. [What to do next]."

The synthesized report is also saved to `~/.hermes/omonigraph-vault/synthesis_output.md`.

## Related skills

- To ingest new content before querying: `omnigraph_ingest`
- To generate a long-form synthesis report: `omnigraph_synthesize`
- To check graph health and statistics: `omnigraph_status`
- To delete or manage graph entities: `omnigraph_manage`
