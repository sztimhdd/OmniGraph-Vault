# Agentic RAG Architecture — Discussion Summary 2026-05-06

**Status**: Draft — discussion document (not spec, not commitment)
**Origin session**: 2026-05-06 afternoon, OmniGraph-Vault main session
**Purpose**: Capture architecture thinking for "全网最强 query" agent before context drifts

---

## Background

- OmniGraph-Vault current state: KG has 116 OK ingested articles, 5305 entities / 6829 edges, mostly Chinese WeChat KOL content from Apr 29 mass-scan + later Phase 2b+ batch
- v3.4 milestone in progress (RSS-KOL alignment, cron stability)
- Open question raised mid-debugging: **does KG actually deliver value for query answering, or is web search enough?**

## Test 1: Can KG answer technical questions?

**Question used**:
> Hermes、OpenClaw、Claude Code、LangGraph 这些 agent 框架在架构设计上的核心差异是什么?各自最适合什么场景?请引用具体的技术细节,例如工具调用机制、上下文管理、状态持久化、harness/skill 系统等。

**Method**: `kg_synthesize.py` hybrid mode, no fallback to web

**Result**:
- 7869 bytes / 71 lines structured answer
- 4 framework comparison + decision tree + summary table
- Captured the "OpenClaw 先把 agent 管住 vs Hermes 先让 agent 长本事" philosophical framing
- 0 image embeddings despite KG having ~331 chunk vectors (synthesis didn't request them)
- Output: [`docs/queries/agent_frameworks_comparison_2026_05_06.md`](../queries/agent_frameworks_comparison_2026_05_06.md)

**Verdict**: KG produces a coherent, useful answer.

## Test 2: A/B vs Brave Search

**Setup**: Same question, Claude (Sonnet) + `mcp__brave-search__brave_web_search`, NO KG access.

**Result**:
- 8946 bytes / 95 lines with 13 source URLs
- Richer technical detail (e.g., "Claude Code 27 hook events" from arxiv paper, "OpenClaw Snyk sandbox bypass research", "LangGraph Checkpointer + Reducers")
- Source-traceable to public web
- Output: [`docs/queries/agent_frameworks_comparison_brave_2026_05_06.md`](../queries/agent_frameworks_comparison_brave_2026_05_06.md)

**Head-to-head**: [`docs/queries/AB_comparison_kg_vs_brave_2026_05_06.md`](../queries/AB_comparison_kg_vs_brave_2026_05_06.md)

| Dimension | Winner |
|-----------|--------|
| Coverage breadth | Tie |
| LangGraph depth | Brave |
| Claude Code depth | Brave |
| OpenClaw depth | Brave |
| Hermes depth | Tie |
| Philosophical framing | KG |
| Decision tree | Tie |
| Source attribution | Brave |
| Image embedding | Tie (both 0) |
| Generation cost | Tie |

**6/11 Brave wins, 4/11 tied, 1/11 KG wins.**

## Why KG didn't win this question

**Data source ceiling**: KG ingest pipeline only fed from Chinese WeChat KOLs (~50 accounts as of Apr 29). KOL content scope is what bounds KG knowledge.

What's IN KG:
- ✅ Chinese community takes on Hermes/OpenClaw
- ✅ Translated/summarized arxiv content via WeChat (partial)
- ✅ Domestic AI dev community zeitgeist

What's NOT in KG:
- ❌ arxiv papers in English (Claude Code paper 2604.14228, OpenClaw security taxonomy 2603.27517)
- ❌ GitHub READMEs / AGENTS.md
- ❌ Snyk/Anthropic/LangChain official documentation
- ❌ English-language community discussion (Reddit / X / Substack)

**For technical questions where English-language sources dominate, KG is structurally disadvantaged.**

## The naive "fix" rejected

Initial intuition: "just add Brave Web full data to KG."

This was rejected because:
1. **Volume**: Even 1% of agent-topic web pages = 5K-50K articles
2. **Cost**: $0.15-0.50 per article × 5K-50K = $750-25,000 just for ingest
3. **LightRAG super-linear scaling**: nano-vectordb full-rewrite per upsert at N=5305 already 245MB; at N=50K would be 2.4GB+ per ainsert — catastrophic
4. **Redundancy**: indexing public web that Brave already indexes is reverse-engineering Brave's job, slowly + expensively
5. **Staleness**: KG snapshot vs Brave real-time; KG always behind

## Right architecture: Hybrid Agentic RAG

The user's correctly-articulated design:

```
                       ┌──────────────────┐
                       │  USER QUESTION   │
                       └────────┬─────────┘
                                ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 1: PUBLIC BASELINE (broad)           │
       │   ─ Brave Search (web)                     │
       │   ─ Tavily (research)                      │
       │   ─ GitHub Search (code/repos)             │
       │   ─ arxiv / Google Scholar (papers)        │
       │   Multiple parallel via MCP tools          │
       └────────────────┬───────────────────────────┘
                        │ baseline answer
                        ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 2: KG ENHANCE (deep / private)       │
       │   ─ kg_synthesize.py hybrid mode           │
       │   ─ STAGE 1 answer as query context        │
       │   ─ KG provides:                           │
       │     · Chinese KOL takes                    │
       │     · Team-private content                 │
       │     · Community-specific insights          │
       │     · Cross-article relationships          │
       └────────────────┬───────────────────────────┘
                        │ enhanced answer
                        ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 3: GAP DETECTION                     │
       │   LLM judges: "what's still unclear?"      │
       │   Categorize gaps:                         │
       │   ─ Missing technical detail → 4a          │
       │   ─ Missing recent updates → 4b            │
       │   ─ Missing concrete cases → 4c            │
       │   ─ Missing dissenting views → 4d          │
       └────────────────┬───────────────────────────┘
                        │ gap list
                        ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 4: TARGETED RE-SEARCH                │
       │   Per gap, dispatch right tool:            │
       │   ─ Brave (general)                        │
       │   ─ Tavily (research-grade)                │
       │   ─ KG re-query (different mode)           │
       │   ─ Cognee recall (history)                │
       └────────────────┬───────────────────────────┘
                        │ all sources
                        ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 5: MULTI-SOURCE SYNTHESIS            │
       │   ─ Sonnet/Opus reasoning                  │
       │   ─ Cite web URLs + KG entity_ids          │
       │   ─ Tag "public / private / community"     │
       │   ─ EMBED IMAGES (KG's killer feature)     │
       └────────────────┬───────────────────────────┘
                        │ final answer
                        ▼
       ┌────────────────────────────────────────────┐
       │ STAGE 6: COGNEE MEMORY                     │
       │   Save synthesis for future recall         │
       └────────────────────────────────────────────┘
```

### Why public-first ordering matters

| Order | Tradeoff |
|-------|----------|
| **Public → KG enhance** (proposed) | ✅ Always have baseline. KG only adds value, never subtracts. |
| KG → public supplement | ❌ KG gaps may "feel complete," web bypassed. Bias toward private data. |
| KG only (current) | ❌ Demonstrated 4/11 loss vs Brave for public-coverage questions |
| Public only | ❌ Loses KG's curation + private data + community insight |

## Components inventory

| Component | Status | Notes |
|-----------|--------|-------|
| Brave Search MCP | ✅ Already user-scope global | `mcp__brave-search__brave_web_search` |
| Tavily | ⚠️ Not confirmed installed | Quick add if needed |
| GitHub Search | ✅ `gh` CLI available | rich search |
| arxiv/Scholar | ⚠️ No direct MCP, but accessible via WebFetch | minimal effort |
| KG query | ✅ kg_synthesize.py + omnigraph_query skill | hybrid/local/global modes |
| Cognee memory | ✅ cognee_wrapper.py exists | remember/recall functions |
| Multi-tool agent | ✅ Hermes Agent skill system | trigger-able skills |
| Synthesis LLM | ✅ DeepSeek (paid) / Sonnet / Opus | choose by quality/cost |

**~95% components exist**. Missing: orchestrator skill that wires them.

## Cost model

| Component | Cost | Notes |
|-----------|------|-------|
| Today KG-only synthesis | ~$0.01/query | 1 LLM call + Vertex embedding |
| Hybrid agentic RAG (proposed) | ~$0.05-0.20/query | 4-8 tool calls + Sonnet/Opus synthesis |
| Multiplier | 5-20× | for ~50% quality improvement |

Per-query cost is still cents — economically viable for personal use.

## Implementation phases (estimated)

```
Phase 1: Single-skill prototype (1 week)
  ─ omnigraph_research_deep skill
  ─ Brave search → baseline
  ─ kg_synthesize → enhance
  ─ LLM gap detection
  ─ 1 round targeted re-search
  ─ Synthesis with citations

Phase 2: Multi-tool + Cognee (1 week)
  ─ Tavily + GitHub + arxiv added to STAGE 1
  ─ Cognee STAGE 6 wired in
  ─ User-controllable depth (Quick / Deep / Exhaustive)

Phase 3: Eval + tuning (1 week)
  ─ A/B test against KG-only and Web-only baselines
  ─ Tune prompts, gap detection threshold, tool selection
  ─ Document quality wins per question category
```

**Total**: ~3 weeks engineering, post-v3.4 stabilization.

## Strategic positioning

**Where KG does win** (proven by today's experiment):

- ✅ Philosophical framing / narrative synthesis from Chinese KOL ecosystem
- ✅ Topics where Western web search misses (Chinese AI community zeitgeist)
- ✅ Topics where curation > breadth
- ✅ Image-rich content (POTENTIAL — current synth doesn't use it)

**Where Brave wins** (also proven):

- arxiv/papers
- GitHub repos / official docs
- English-language security research / community discussion
- Source-attributable answers

**Hybrid wins both**: combining curated private depth with broad public reach. Neither approach can deliver this alone.

## Strategic insight

> "全网最强" is not achieved by KG alone or web alone. It requires the orchestration layer that calls both, mediates gaps, and synthesizes with proper citations.

KG is **a feature of agentic RAG**, not a competitor to search. This reframes KG's role from "search engine replacement" to "private knowledge enhancement layer in a multi-tool research agent."

## Open questions for next session

1. **Synthesis LLM choice**: Sonnet (cheaper, fast) vs Opus (better at multi-source reasoning) per query?
2. **Tool selection in STAGE 1**: parallel call all tools always, or LLM-routed based on question type?
3. **Gap detection threshold**: when does LLM say "good enough, skip STAGE 4"? Confidence-based or coverage-based?
4. **Cognee integration depth**: recall full prior session or just final conclusions? Memory bloat tradeoff.
5. **User-facing UX**: explicit `/research` slash command? Auto-detect "deep question" via prompt?
6. **Image embedding**: how does synthesizer KNOW to insert image markdown? Tool-side hint or prompt instruction?
7. **Multi-language source merging**: KG (Chinese) + arxiv (English) — synthesis in user's language requires translation step?
8. **Eval methodology**: how to systematically prove hybrid > either alone? Need eval question set.
9. **Cost cap**: per-query budget? Per-day budget? Auto-degrade to KG-only when budget exhausted?
10. **Where in roadmap**: v3.5 candidate? v3.6? After Phase 5 wave 1 completes?

## References

- `docs/queries/agent_frameworks_comparison_2026_05_06.md` — KG synthesis output
- `docs/queries/agent_frameworks_comparison_brave_2026_05_06.md` — Brave Search baseline
- `docs/queries/AB_comparison_kg_vs_brave_2026_05_06.md` — A/B verdict
- `kg_synthesize.py` — current KG synthesis entry point
- `cognee_wrapper.py` — memory layer
- `~/.claude/CLAUDE.md` — global agent setup including MCP tools
- `CLAUDE.md` — project context (OmniGraph-Vault architecture)

---

*This is a discussion document, not a spec. Captured 2026-05-06 to seed next session's deeper design work.*
