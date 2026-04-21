---
name: omnigraph_ingest
description: Ingest a WeChat article URL or local PDF into the OmniGraph-Vault knowledge graph.
triggers:
  - "add this to my kb"
  - "add this to my knowledge base"
  - "ingest this"
  - "save this article"
  - "save to knowledge base"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_ingest

## Purpose

Ingest web articles (WeChat URLs) or local PDF files into the OmniGraph-Vault knowledge graph. After ingestion, the content is indexed in LightRAG and becomes queryable via the `omnigraph_query` skill.

## When to trigger this skill

- User says "add this to my kb", "ingest", "save this article", "add to knowledge base"
- User provides a URL (especially `mp.weixin.qq.com`) and wants it saved
- User provides a local file path ending in `.pdf` and wants it ingested

## When NOT to trigger this skill

- User asks "what do I know about X" or "search my kb" → use `omnigraph_query` instead
- User asks for a report or synthesis → use `omnigraph_synthesize` instead
- User asks about graph health or node count → use `omnigraph_status` instead
- User wants to delete or manage entities → use `omnigraph_manage` instead

## Decision tree

### Case 1: WeChat URL provided

Run:
```bash
python ingest_wechat.py "<URL>"
```

Expected output: confirmation that content was scraped, images downloaded, and graph updated.

### Case 2: PDF file path provided

Run:
```bash
python multimodal_ingest.py "<file_path>"
```

### Case 3: No URL or file path provided

Ask the user: "Please provide the URL or file path you want to ingest."
Do not attempt to run any script until the user provides a URL or path.

### Case 4: User provides a URL but GEMINI_API_KEY is not set

Respond: "⚠️ Configuration error: GEMINI_API_KEY is not set. Please add it to ~/.hermes/.env and restart."
Do not attempt ingestion.

### Case 5: User provides a URL but it is not a WeChat article

Still run `ingest_wechat.py` — it handles general web URLs as well, not just WeChat.

## Error handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in ~/.hermes/.env" |
| Apify quota exceeded | "⚠️ Apify quota exceeded. The scraper will automatically retry with CDP fallback." |
| CDP not reachable (local `http://localhost:9223`) | "⚠️ CDP fallback unavailable. Start Edge with: `msedge --remote-debugging-port=9223`" |
| Remote MCP server set as CDP_URL | "⚠️ Remote CDP_URL points to a Playwright MCP server, which is not yet supported by ingest_wechat.py. Set CDP_URL to a local browser endpoint (`http://localhost:9223`) or leave it unset to rely on Apify only." |
| File not found (PDF path) | "⚠️ File not found: <path>. Check the path and try again." |

## Output format

On success, report:
- Article title and URL ingested
- Number of images described
- Confirmation: "Content indexed into OmniGraph-Vault. Query it with the `omnigraph_query` skill."

On failure, use: "⚠️ [Error type]: [What happened]. [What to do next]."

## Related skills

- To query ingested content: `omnigraph_query`
- To generate a synthesis report: `omnigraph_synthesize`
- To check how many nodes were added: `omnigraph_status`
