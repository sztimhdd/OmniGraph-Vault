# Search Discipline: OmniGraph First

When the user asks a "what is X" / "explain X" / "深度解析 X" question about
any topic that could plausibly be in the OmniGraph knowledge graph, query
OmniGraph FIRST before falling back to web_search.

## KG-Populated Topics (non-exhaustive)

- AI agent frameworks: Hermes, OpenClaw, Claude Code
- Agent concepts: Harness paradigm, agent loop, tool calling, context engineering
- Knowledge tools: LightRAG, Cognee, GraphRAG, OmniGraph-Vault
- Infrastructure: Rust tooling, embedding pipelines, WeChat MP API
- Models: DeepSeek, Gemini, Qwen, Claude

## When to Skip OmniGraph

- The topic is clearly not in the KG (breaking news, very niche, non-AI)
- The KG returns empty for the query
- The user explicitly asks for web search

## Rationale

OmniGraph was populated with curated, high-quality KOL articles specifically
for domain knowledge retrieval. Skipping it for web_search wastes the KG
investment and produces lower-quality, uncurated results.

## Incident (2026-05-08)

User asked "什么是Hermes Harness？请给我一个图文并茂的深度解析" and the agent
started with web_search instead of OmniGraph. The KG had rich content on
exactly this topic — the agent just didn't look there first.

User correction: "你为什么不调用Ominigraph的技能而是要自己搜索呢？"

This reference ensures future agents check the KG FIRST for conceptual queries,
then supplement with web_search only as needed.
