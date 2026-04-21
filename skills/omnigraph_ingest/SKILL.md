---
name: omnigraph_ingest
description: |
  Use this skill when the user wants to add a WeChat article URL or local PDF file to
  the OmniGraph-Vault knowledge graph. Trigger phrases include: "add this to my knowledge
  base", "ingest this article", "save this to my KB", "add to knowledge base", or any
  time a WeChat URL (mp.weixin.qq.com) or a .pdf file path is provided with intent to
  index it.

  This skill handles: WeChat article scraping via Apify (primary) or CDP fallback,
  PDF extraction with embedded image processing, image downloading with Gemini Vision
  descriptions, entity extraction queued for async canonicalization, and LightRAG graph
  indexing. It announces expected wait time (30–120 seconds) before running.

  Do NOT use this skill when: the user wants to query or search existing content — use
  omnigraph_query instead. Do NOT use when the user wants a synthesis report — use
  omnigraph_synthesize. Do NOT use when the user asks about graph health or node counts
  — use omnigraph_status. Do NOT use when the user wants to delete or manage entities
  — use omnigraph_manage. Do NOT use for general-purpose web archiving not related to
  this knowledge base.
compatibility: |
  Requires: GEMINI_API_KEY in ~/.hermes/.env, Python venv at $OMNIGRAPH_ROOT/venv.
  Optional: APIFY_TOKEN (enables primary scraping path), CDP_URL (default localhost:9223).
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_ingest

## Quick Reference

| Task | Input | Command |
|------|-------|---------|
| Ingest WeChat article | `mp.weixin.qq.com` URL | `scripts/ingest.sh "<url>"` |
| Ingest local PDF | `.pdf` file path | `scripts/ingest.sh "<path>"` |
| Missing URL/path | No location given | Ask first — do not run |

## When to Use

- User says "add this to my KB", "ingest", "save this article", "add to knowledge base"
- User provides a WeChat URL (`mp.weixin.qq.com/...`) and wants it saved
- User provides a local file path ending in `.pdf` and wants it ingested
- User says "remember this" about an article or document

## When NOT to Use

- User asks "what do I know about X" or "search my KB" → use `omnigraph_query` instead
- User asks for a synthesis report → use `omnigraph_synthesize` instead
- User asks about graph health or node counts → use `omnigraph_status` instead
- User wants to delete or manage entities → use `omnigraph_manage` instead
- URL is not a WeChat article and not a PDF → ask for clarification, do not run blindly

## Decision Tree

### Case 1: WeChat URL provided

Announce: "Starting ingestion — this may take 30–120 seconds..."

Run:
```bash
scripts/ingest.sh "<url>"
```

Expected output: article title, images downloaded/described count, confirmation that
content is indexed and entity extraction is queued.

### Case 2: Local PDF path provided

Announce: "Starting PDF ingestion — this may take 30–120 seconds..."

Run:
```bash
scripts/ingest.sh "<file_path>"
```

### Case 3: No URL or file path provided

Ask the user: "Please provide the WeChat article URL or local PDF path you want to ingest."
Do not run any script until the user provides a location.

### Case 4: GEMINI_API_KEY is not set

Respond: "⚠️ Configuration error: GEMINI_API_KEY is not set. Please add it to `~/.hermes/.env` and restart."
Do not attempt ingestion.

### Case 5: URL is not a WeChat article and not a PDF

Respond: "⚠️ This skill only ingests WeChat articles (mp.weixin.qq.com URLs) or local PDF files. If you want to ingest a different URL, please confirm it is accessible and provide a WeChat article URL."
Do not run `ingest.sh` for arbitrary web URLs without user confirmation.

## Error Handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`" |
| Apify quota exceeded | Script logs warning; CDP fallback is tried automatically — report method used |
| CDP not reachable (`localhost:9223`) | "⚠️ CDP fallback unavailable. Start Edge: `msedge --remote-debugging-port=9223`" |
| File not found (PDF path) | "⚠️ File not found: `<path>`. Check the path and try again." |
| Script not found / venv missing | "⚠️ Setup error: venv not found. Run: `pip install -r requirements.txt` in the repo root." |

## Output Format (Success)

```
Starting ingestion — this may take 30–120 seconds...
[article-title] ingested successfully
Images: X downloaded, Y described
Entity extraction queued. Query it with the omnigraph_query skill.
```

## Privacy Note

Article content is stored locally in `~/.hermes/omonigraph-vault/`. Images are
downloaded locally. Only the Gemini API and optionally Apify receive external data.

For full script interface (env vars, exit codes, dispatch logic), see
`references/api-surface.md`.

## Related Skills

- To query ingested content: `omnigraph_query`
- To generate a long-form synthesis report: `omnigraph_synthesize`
- To check graph health and statistics: `omnigraph_status`
- To delete or manage graph entities: `omnigraph_manage`
