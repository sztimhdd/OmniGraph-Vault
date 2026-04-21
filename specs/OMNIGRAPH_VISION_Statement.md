# OmniGraph-Vault: Phase 2-4 Vision & Architecture
**For:** Claude Code / Hermes implementation reference  
**Status:** Design spec, not yet implemented  
**Prerequisite:** Phase 1 complete (Gate 1-6), core pipeline validated

---

## Core Insight: Tool-Centric Knowledge Graph

The AI domain knowledge structure is tool-anchored. Every user query resolves to a **Tool node**:

```
"How to use Cursor faster"        → Cursor
"LightRAG vs GraphRAG"            → LightRAG, GraphRAG  
"n8n automation workflow"         → n8n
"Hermes + Telegram setup"         → Hermes, Telegram
```

### Canonical Tool Node Schema

```python
ToolNode:
  # Identity
  name: str                    # "LightRAG"
  aliases: List[str]           # ["Light RAG", "轻量RAG"]
  category: List[str]          # ["RAG", "KnowledgeGraph", "Framework"]
  github_url: str
  stars: int
  last_updated: datetime
  confidence_score: float      # 0.0-1.0, based on source count

  # Knowledge layers (filled from multiple sources)
  official_docs: List[Chunk]   # README + /docs
  community_zh: List[Chunk]    # WeChat + Zhihu
  community_en: List[Chunk]    # English blogs + RSS
  issues_bugs: List[Chunk]     # GitHub Issues + Zhihu complaints
  tutorials: List[Chunk]       # Step-by-step guides only
  comparisons: List[Chunk]     # vs other tools

  # Graph relationships
  BASED_ON: List[ToolNode]     # theoretical predecessors
  INTEGRATES: List[ToolNode]   # works natively with
  COMPETES: List[ToolNode]     # alternative tools
  USED_WITH: List[ToolNode]    # common combinations
  PART_OF: List[ToolNode]      # larger ecosystems
```

---

## Phase 2: Multi-Source Ingestion (Month 1)

### Week 1-2: Batch Content Ingestion

**Task 1: WeChat batch ingestion**
- Use `wechat_spider` + CDP to extract all articles from top 20 AI KOL accounts
- Store FAKEIDS in `accounts.json`
- Script: `sync_wechat_accounts.py`
  - Auto-login to `mp.weixin.qq.com` via CDP
  - Extract token + cookie automatically
  - Iterate FAKEIDS → collect all article URLs
  - Filter already-ingested URLs (check against local processed list)
  - Pass new URLs to `ingest_wechat.py` batch queue

**Task 2: RSS ingestion for English sources**
- Source: Karpathy's curated list (93 high-quality AI blogs/newsletters)
- Filter criteria: tutorials / guides / howto only — NO news, NO paper summaries
- Script: `ingest_rss.py`
  - Use `feedparser` library (no CDP needed, no auth)
  - Pre-classification via Gemini Flash before ingestion:
    ```
    KEEP: tutorial, guide, howto, walkthrough, tips, deep-dive
    SKIP: news, announcement, paper_summary, opinion
    ```
  - Feed into same LightRAG index as WeChat content

**Task 3: GitHub Top 100 AI tools**
- Use GitHub public API (no CDP, no auth beyond token)
- Per repo, ingest:
  - `README.md`
  - All `.md` files under `/docs`
  - Issues labeled: `question`, `help wanted`, `tutorial`
  - High-upvote Discussions
- Filter: stars > 1000, updated within 6 months, tool/framework (not personal project)
- Script: `ingest_github.py`

**Task 4: Zhihu top answerers**
- Target: top 20 AI practitioners on Zhihu (by answer quality, not follower count)
- Ingest ALL answers per user (not by topic — by person)
- High-value content types:
  - "踩坑/避坑" (pitfall) answers
  - "X vs Y" comparison answers  
  - High-upvote comments on popular answers
- Script: `ingest_zhihu.py` (CDP-based, reuse existing bridge)

---

## Phase 3: Multi-Source Cross-Validation (Month 2)

### The Three Knowledge Preprocessors

These are NOT primary knowledge sources. They are **free aggregation engines** that surface existing content for further validation.

```
Zhihu AI (好问)     → aggregates Zhihu ecosystem (Chinese practitioner experience)
Gemini + Grounding  → aggregates global web (Google index, covers English sources)
Claude + WebSearch  → second opinion, cross-validation
```

### Workflow: Seed → Query → Validate → Ingest

```
Trigger: high-quality WeChat article ingested
    ↓
Extract key tool/concept entities from article
    ↓
Parallel queries to all three preprocessors:
  "What do practitioners say about [entity]? 
   Focus on practical usage, pitfalls, integrations."
    ↓
Three outputs → diff analysis:
  All three mention X     → high confidence (score: 1.0)
  Two mention X           → medium confidence (score: 0.7)  
  Only one mentions X     → possible unique insight (score: 0.4, flag for review)
  Sources contradict      → flag for human review
    ↓
Follow original source links from preprocessor outputs
    ↓
Gemini quality evaluation on each source:
  PASS criteria:
  - Contains actionable steps or code
  - Specific tools/params/configs mentioned
  - Written from hands-on experience (not pure theory)
  - Information density > filler ratio
    ↓
PASS → ingest into LightRAG with confidence score attached
FAIL → discard
```

### Confidence Score Storage

Each chunk ingested carries metadata:
```python
chunk.metadata = {
  "source_count": 3,          # how many sources corroborate
  "confidence": 0.85,
  "sources": ["wechat", "zhihu_ai", "gemini_grounding"],
  "last_verified": datetime,
  "content_type": "tutorial"  # tutorial/pitfall/comparison/official
}
```

**Important:** Use simple counting for v1. Do NOT implement semantic similarity models yet — wait for real data to inform what needs optimization.

---

## Phase 4: Self-Completing Knowledge Graph (Month 3)

### Gap Detection

Trigger conditions for automatic gap-filling (simple rules, no ML needed for v1):

```python
# A node needs enrichment if:
node.relationship_count < 3          # poorly connected
node.community_zh.count == 0         # no Chinese practitioner content  
node.tutorials.count == 0            # no how-to content
node.last_updated < 30_days_ago      # stale
node.issues_bugs.count == 0          # no real-world usage signals
```

### Self-Completion Loop

```
Gap detected on Tool node X
    ↓
Generate targeted queries:
  "X practical tutorial Chinese"     → WeChat/Zhihu search
  "X common issues and solutions"    → GitHub Issues + Zhihu
  "X vs alternatives comparison"     → all sources
    ↓
Run through standard ingest pipeline
    ↓
Node enrichment logged to cognee_batch.log
```

### Claude/Gemini as Knowledge Navigator (NOT knowledge source)

Use LLMs to find gaps, not fill them:

```python
# Blind spot detection prompt:
"""
For the tool [X], a complete knowledge graph should contain:
- Core concepts and architecture
- Common integrations  
- Known limitations
- Typical use cases
- Comparison with alternatives

Based on this checklist, what topics are likely 
missing from a knowledge base about [X]?
Return as search queries I should use to find content.
"""
```

LLM output → list of search queries → feed into ingestion pipeline → validate against real sources → ingest if quality passes.

**Rule:** LLM output never goes directly into the graph. Always requires source validation.

---

## Preset Domain Graph Strategy

### What to pre-build before user onboarding

```
AI Engineering Domain Graph (pre-populated):
├─ ~100 Tool nodes (GitHub Top 100 AI tools)
├─ ~50,000 estimated entity nodes
├─ ~200,000 estimated relationship edges
├─ Bilingual entity alignment (CN/EN canonicalized via Cognee)
└─ Continuously auto-updated
```

### User onboarding model

```
Day 1 user experience:
  NOT: empty vault, start from scratch (Notion/Obsidian problem)
  YES: plug into mature AI engineering knowledge graph
       + add personal content on top
       = immediately useful, gets more personal over time
```

### Per-user isolation

- Each user has independent LightRAG instance
- Each user has independent Cognee memory
- Preset graph = read-only shared layer (cost-efficient)
- User content = personal layer on top
- BYOK: user provides own API keys, pays own inference costs

---

## Query Pattern Coverage

The Tool-centric schema handles all user query types:

| Query Type | Example | Resolution Path |
|------------|---------|-----------------|
| How-to | "How to configure LightRAG with Ollama?" | Tool.official_docs + Tool.tutorials |
| Comparison | "LightRAG vs RAGFlow?" | Tool.COMPETES → both nodes, comparison layer |
| Integration | "LightRAG + Cognee together?" | Tool.USED_WITH → integration tutorials |
| Pitfall | "LightRAG production gotchas?" | Tool.issues_bugs |
| Selection | "Best RAG framework for personal KB?" | category:RAG → cross-node synthesis |
| Unknown | "What is X?" | Entity lookup → definition + context |

---

## Implementation Notes for Claude Code

1. **Start simple on confidence scoring** — counting sources is enough for v1, don't over-engineer
2. **Atomic writes for canonical_map.json** — always write to `.tmp` then rename, never direct overwrite
3. **entity_buffer/ idempotency** — write `.processed` marker after each batch run, never delete originals
4. **Cognee is async, always** — never block ingestion fast-path on any Cognee operation
5. **GitHub API rate limits** — authenticated requests: 5000/hour, structure batch jobs accordingly
6. **Zhihu CDP reuse** — same bridge as WeChat, just different URL patterns and DOM selectors
7. **Quality filter before LightRAG** — Gemini Flash classification is cheap; better to filter early than pollute the graph
8. **Tool node creation is additive** — new GitHub repo → create sparse node immediately, fill knowledge layers progressively as content is found

---

## Files to Create (Phase 2-4)

```
OmniGraph-Vault/
├─ sync_wechat_accounts.py     # CDP auto-login + batch URL collection
├─ ingest_rss.py               # Karpathy list RSS ingestion + classification
├─ ingest_github.py            # GitHub API → README + docs + issues
├─ ingest_zhihu.py             # CDP-based Zhihu answerer ingestion
├─ knowledge_preprocessor.py   # Zhihu AI + Gemini + Claude parallel queries
├─ cross_validator.py          # Multi-source diff + confidence scoring
├─ gap_detector.py             # Node completeness check + auto-fill trigger
└─ accounts.json               # FAKEIDS + RSS feeds + GitHub repos config
```

---
*Document generated from design session. Implement phases sequentially. Validate each phase with real data before proceeding.*
