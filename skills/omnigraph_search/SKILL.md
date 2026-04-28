---
name: omnigraph_search
description: |
  Use this skill when the user wants raw, entity-attributed retrieval from the
  OmniGraph-Vault domain knowledge graph (WeChat + Zhihu articles). Trigger phrases:
  "why was X designed this way", "what's the best practice for Y", "how does
  OpenClaw handle Z", "what are the pitfalls for A", "find sources about B",
  "entity-level search".

  This skill runs scripts/query.sh which invokes omnigraph_search/query.py — a
  LightRAG hybrid-mode wrapper. Returns graph retrieval WITHOUT synthesis (no
  long-form report, no inline images, no Cognee memory). Output is the raw
  retrieval text with entity attribution.

  Do NOT use this skill when: the user asks about code structure, function
  signatures, call chains, imports, or module dependencies — that's the
  `graphify` skill's job. Do NOT use when the user wants a long-form synthesis
  report with inline images — use `omnigraph_query`. Do NOT use when the user
  wants to ingest new content — use `omnigraph_ingest` or `enrich_article`. Do
  NOT use when the user asks about graph health or node counts — use
  `omnigraph_status`. Do NOT use when the user wants to delete or manage
  entities — use `omnigraph_manage`.
compatibility: |
  Requires: GEMINI_API_KEY in ~/.hermes/.env, Python venv at $OMNIGRAPH_ROOT/venv,
  populated LightRAG index at ~/.hermes/omonigraph-vault/lightrag_storage/.
  Companion skill: use alongside `graphify` for queries that need both design
  rationale (this skill) AND code structure (graphify).
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_search

## Quick Reference

| Task | How | Mode |
|------|-----|------|
| Natural-language search | `scripts/query.sh "<question>"` | hybrid (default) |
| Explicit mode | `scripts/query.sh "<question>" <mode>` | naive/local/global/hybrid/mix |
| Empty KB | No results → advise user to ingest first | — |

## When to Use

- User asks "why was X designed this way" — design rationale retrieval
- User asks "what's the best practice for Y" — practice patterns
- User asks "what are the pitfalls for Z" — gotcha/anti-pattern retrieval
- User asks "find sources about W" or "search my KB" and wants raw retrieval, not a synthesized report

## When NOT to Use

When redirecting to another skill, name only the target skill in your response — do NOT mention this skill's own name.

- User asks about code structure / call chains / signatures → use `graphify` (queries the code graph, not the domain graph)
- User wants a formal long-form synthesis report with inline images → use `omnigraph_query`
- User wants to add/ingest new content → use `omnigraph_ingest` or `enrich_article`
- User asks about graph health / node counts → use `omnigraph_status`
- User wants to delete or manage entities → use `omnigraph_manage`
- User wants general web search → leave to agent default

## Decision Tree

### Case 1: Standard natural-language search
Announce: "Searching knowledge graph — this may take 10–30 seconds..."
Run: `scripts/query.sh "<user question>"`
Uses `hybrid` mode by default.

### Case 2: User requests a specific retrieval mode
Supported: `naive`, `local`, `global`, `hybrid`, `mix`
Run: `scripts/query.sh "<question>" <mode>`

### Case 3: User asks to delete, clear, or modify graph data
Do NOT execute any delete operation. Respond: "⚠️ Please use the `omnigraph_manage` skill for delete, reindex, or entity management operations."

### Case 4: GEMINI_API_KEY not set
Respond: "⚠️ Configuration error: GEMINI_API_KEY is not set. Add it to `~/.hermes/.env` and restart."

### Case 5: Empty result
Respond: "No relevant content found. Try ingesting relevant articles first via `omnigraph_ingest`."

## Query Modes

| Mode | Use when |
|------|----------|
| `naive` | Simple keyword retrieval, fastest |
| `local` | Entity-centric: relationships around specific nodes |
| `global` | Theme-level: broader conceptual patterns |
| `hybrid` | Default: combines local + global |
| `mix` | Vector search + graph traversal |

## Output Format

- Retrieval text rendered as Markdown in chat
- Results with >5 items: Markdown table (Entity, Confidence, Sources)
- Results with ≤5 items: bullet list
- Errors: "⚠️ [Error type]: [What happened]. [What to do next]."

## Error Handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`" |
| venv missing | "⚠️ Setup error: venv not found. Run: `pip install -r requirements.txt`" |
| Empty result | Advise user to ingest relevant articles first |

For full script interface (env vars, exit codes, all modes), see `references/api-surface.md`.

## Related Skills

- For synthesized long-form reports: `omnigraph_query`
- For code structure / call chains: `graphify`
- To ingest new content: `omnigraph_ingest` / `enrich_article`
- Graph health and stats: `omnigraph_status`
- Delete or manage entities: `omnigraph_manage`
