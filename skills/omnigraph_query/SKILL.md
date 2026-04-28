---
name: omnigraph_query
description: |
  Use this skill when the user wants to query or search their OmniGraph-Vault knowledge
  graph by natural language. Trigger phrases include: "what do I know about X", "search
  my knowledge base for X", "search my KB", "find in my graph", "query the knowledge
  base", or any request to retrieve and synthesize information that may have been
  previously ingested. Also triggers on comparison, summary, or explanation requests
  for topics likely to have been saved.

  This skill runs kg_synthesize.py with hybrid retrieval (combining LightRAG graph
  traversal and Cognee memory context) and generates a Markdown report saved to
  ~/.hermes/omonigraph-vault/synthesis_output.md. It warns if the image server
  (port 8765) is not running when inline images are expected in the output.

  Do NOT use this skill when: the user wants to add or ingest new content — use
  omnigraph_ingest instead. Do NOT use when the user wants a formal long-form synthesis
  report — use omnigraph_synthesize. Do NOT use when the user asks about graph health
  or node counts — use omnigraph_status. Do NOT use when the user wants to delete or
  manage entities — use omnigraph_manage. Do NOT use for general web search — leave
  that to the agent's default search capability. Do NOT use when the user wants raw
  entity-attributed retrieval without synthesis — use `omnigraph_search` instead
  (same backend, simpler output, no synthesis).
compatibility: |
  Requires: GEMINI_API_KEY in ~/.hermes/.env, Python venv at $OMNIGRAPH_ROOT/venv.
  Image server on port 8765 recommended for inline images in synthesis output.
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_query

## Quick Reference

| Task | How | Mode |
|------|-----|------|
| Natural language query | `scripts/query.sh "<question>"` | hybrid (default) |
| Explicit mode | `scripts/query.sh "<question>" <mode>` | naive/local/global/hybrid/mix |
| Empty KB | No results → advise user to ingest first | — |

## When to Use

- User asks "what do I know about X"
- User asks "search my KB for X" or "find information about X in my knowledge base"
- User wants a comparison, summary, or explanation of topics that may have been ingested
- User asks "tell me about X" and X could plausibly be in their personal KB

## When NOT to Use

- User wants to add or ingest new content → use `omnigraph_ingest` instead
- User wants a formal long-form synthesis report → use `omnigraph_synthesize` instead
- User asks about graph health, node counts, or pipeline status → use `omnigraph_status` instead
- User wants to delete entities or manage the graph → use `omnigraph_manage` instead
- User wants raw entity-attributed retrieval without long-form synthesis → use `omnigraph_search` instead
- User wants general web search (not personal KB) → leave to agent default

## Image Server Note

If the user expects inline images in the synthesis output, the image server must be
running on port 8765:

```bash
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &
```

If images are not loading, mention this to the user.

## Decision Tree

### Case 1: Standard natural-language query

Announce: "Querying knowledge graph — this may take 15–60 seconds..."

Run:
```bash
scripts/query.sh "<user question>"
```

Uses `hybrid` mode by default. Combines local entity traversal and global theme
retrieval for balanced results.

### Case 2: User explicitly requests a retrieval mode

Supported modes: `naive`, `local`, `global`, `hybrid`, `mix`

Run:
```bash
scripts/query.sh "<user question>" <mode>
```

For example, if user says "use local mode":
```bash
scripts/query.sh "What are AI agent architectures?" local
```

### Case 3: User asks to delete, clear, or modify graph data

Do NOT perform any deletion or modification. Respond:
"⚠️ Modifying the knowledge graph is handled by the `omnigraph_manage` skill. Please use that skill for any delete, reindex, or entity management operations."

### Case 4: GEMINI_API_KEY is not set

Respond: "⚠️ Configuration error: GEMINI_API_KEY is not set. Please add it to `~/.hermes/.env` and restart."

### Case 5: Query returns no results

If `kg_synthesize.py` returns an empty or low-confidence response:
"No relevant content found for '<query>' in the knowledge graph. Try ingesting relevant articles first using the `omnigraph_ingest` skill."

## Query Modes

| Mode | Use when |
|------|----------|
| `naive` | Simple keyword retrieval, fastest |
| `local` | Entity-centric: relationships around specific nodes |
| `global` | Theme-level: broader conceptual patterns |
| `hybrid` | Default: combines local + global for balanced results |
| `mix` | Combines vector search + graph traversal |

## Output Format

- Synthesis report rendered as Markdown in chat
- Report also saved to `~/.hermes/omonigraph-vault/synthesis_output.md`
- Results with >5 items: Markdown table (Entity, Confidence, Sources)
- Results with ≤5 items: bullet list
- COUNT queries (e.g. "how many articles about X"): plain number
- Errors: "⚠️ [Error type]: [What happened]. [What to do next]."

## Error Handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`" |
| venv missing | "⚠️ Setup error: venv not found. Run: `pip install -r requirements.txt`" |
| Empty result | Advise user to ingest relevant articles first |

For full script interface (env vars, exit codes, all modes), see
`references/api-surface.md`.

## Related Skills

- To ingest new content before querying: `omnigraph_ingest`
- To generate a long-form synthesis report: `omnigraph_synthesize`
- To check graph health and statistics: `omnigraph_status`
- To delete or manage graph entities: `omnigraph_manage`
- For raw entity-attributed retrieval without synthesis: `omnigraph_search`
