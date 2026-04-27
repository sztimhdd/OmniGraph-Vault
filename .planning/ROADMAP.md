# Roadmap

**Last Updated:** 2026-04-27

## Done

- WeChat article ingestion (Apify → CDP → MCP triple path)
- LightRAG knowledge graph with Cognee async memory
- Gemini Vision image description pipeline
- Entity canonicalization (entity_buffer + canonical_map)
- KOL SQLite pipeline: scan → classify → ingest from DB
- Gemini classifier option (free tier, alongside DeepSeek)
- Entity layer migration to SQLite (Phase 2: dual-write, DB-first read)
- 4 Hermes skills: omnigraph_ingest, omnigraph_query, omnigraph_architect, hermes_claude_code_bridge
- Skill runner with test suites

## Current

- Large-scale batch KOL ingestion (1000+ articles from 54 WeChat accounts)
- SQLite entity pipeline stabilization (monitoring DB-first path vs file fallback)

## Next

- Not yet planned — focus is on populating the knowledge base with quality KOL content
