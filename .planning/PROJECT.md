# OmniGraph-Vault

## What This Is

A local, graph-based personal knowledge base that gives Hermes Agent (and OpenClaw)
persistent memory. The primary pipeline: **scan WeChat KOL accounts → classify articles
by topic via LLM → ingest into LightRAG knowledge graph → synthesize on demand**.

All article and entity metadata is persisted in a single SQLite database
(`data/kol_scan.db`), enabling repeated classification runs without re-scanning.

## Core Pipeline

```
batch_scan_kol.py ──→ articles in SQLite
        ↓
batch_classify_kol.py ──→ classifications in SQLite (DeepSeek or Gemini)
        ↓
batch_ingest_from_spider.py --from-db ──→ LightRAG knowledge graph
        ↓
kg_synthesize.py ──→ Markdown synthesis report
```

**Key capability:** scan once (120 days, 54 accounts), classify many times with different
topics. No re-scraping needed to re-classify.

## Long-Term Product North Star

OmniGraph's long-term role is not "a better search box." It is the architecture
intelligence layer for **VitaClaw**, a Rust-native intelligent agent runtime inspired
by, but not limited to, OpenClaw and Hermes.

The product goal is to help a human CTO and a coding agent answer questions like:

> "How should VitaClaw integrate Mem0 for multi-layer memory, using current agent
> framework best practices plus the real OpenClaw, Hermes, and VitaClaw codebases?"

For that class of question, OmniGraph should compile evidence from multiple graphs
into an engineering decision and an implementation brief. The desired output is not a
pile of retrieved snippets. It is a source-grounded recommendation with:

- what the external agent ecosystem currently believes is best practice
- how OpenClaw and Hermes actually structure the related code paths
- where VitaClaw's Rust architecture should receive the capability
- which tradeoffs, risks, and tests matter
- what should be delegated to a coding agent as a clear task brief

The strategic upgrade path is from **knowledge base** to **VitaClaw engineering
decision system**.

## Target Knowledge Architecture

Future planning should treat OmniGraph as a federated graph system:

- **Domain graph:** LightRAG over frontier articles, guides, papers, technical docs,
  release notes, and operator experience. It answers "what is the current best
  thinking and why?"
- **Reference code graphs:** Graphify over OpenClaw and Hermes source. They answer
  "how do the reference systems actually implement this?"
- **VitaClaw code graph:** Graphify over VitaClaw. It answers "where does this belong
  in our Rust codebase, and what would the change touch?"
- **Decision graph:** an OmniGraph-owned layer of architectural decisions,
  bridge concepts, rejected options, verification results, and drift findings. It
  answers "what have we decided, why, and is it still true?"

Keep these graphs logically separate. Do not force article concepts and source-code
symbols into one physical graph unless research proves a better architecture. Cross-graph
reasoning should happen through explicit bridge concepts and query orchestration.

## Long-Term Product Requirements

- OmniGraph should support architecture questions that require both external best
  practice and repository-specific source evidence.
- VitaClaw must become a first-class graph target. A Rust rewrite cannot be guided
  well if its own crate/module/trait structure is absent from the graph system.
- Hermes and OpenClaw should be treated as reference systems, not as templates to copy
  blindly. Their patterns are evidence; VitaClaw's Rust-native architecture remains the
  product owner.
- OmniGraph should preserve architectural judgment: selected designs, rejected designs,
  rationale, validation evidence, and supersession history.
- Coding-agent outputs should be task briefs, not just explanations: relevant context,
  source evidence, constraints, risks, expected tests, and acceptance criteria.
- The system should be evaluated against ordinary web search and documentation lookup
  on real VitaClaw architecture tasks. The core metric is better engineering decisions:
  fewer hallucinated APIs, better module placement, clearer tradeoffs, and more reliable
  implementation plans.

## Autonomy For Future Claude Planning

These principles are intentionally not an implementation plan. Future Claude runs should
research the current state of LightRAG, Graphify, Mem0, MCP, OpenClaw, Hermes, VitaClaw,
and the broader agent ecosystem before proposing concrete milestones. If evidence shows
that a named tool is no longer the best fit, Claude should surface that and recommend a
better architecture while preserving the product requirements above.

## Validated (what works)

- WeChat article scraping: Apify (primary) → CDP fallback → MCP fallback
- Image download + Gemini Vision description
- LightRAG graph insertion + hybrid retrieval
- Cognee async entity canonicalization (DB-first, file fallback)
- Entity extraction → entity_buffer + SQLite dual-write (Phase 2)
- Canonical entity map in SQLite `entity_canonical` table (Phase 2)
- Gemini and DeepSeek classifiers with 15 RPM rate limiting
- PDF ingestion with embedded image extraction
- Synthesis engine generating Markdown reports
- Local image HTTP server (port 8765)
- 4 Hermes skills: ingest, query, architect, claude-code-bridge
- Skill runner with test suites

## Tech Stack

- Python 3.11+, LightRAG (kuzu), Cognee
- Gemini 2.5 Flash (LLM + Vision + Embedding)
- DeepSeek (classification), `google-genai` SDK
- SQLite (article/entity persistence)
- Apify + Playwright CDP (scraping)
- BeautifulSoup + html2text (content extraction)

## Constraints

- **Privacy:** All data local; only Gemini API + Apify make external calls
- **Platform:** Windows-primary (Edge for CDP); WSL for git/github
- **Single user:** No auth, no isolation
- **Runtime data:** `~/.hermes/omonigraph-vault/` (typo is intentional, baked into config.py)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite for KOL pipeline | One-scan-many-classify; dedup by URL UNIQUE | Good |
| Entity dual-write (file + DB) | No migration risk; file stays primary during transition | In progress |
| Cognee decoupled from ingestion fast-path | Async path preserves <200ms target | Good |
| DeepSeek default classifier, Gemini free option | Cost optimization; fail-open on both | Good |
| Two Skills (ingest + query) not one unified | Clearer intent mapping | Working |

## Current Milestone: v3.1 Single-Article Ingest Stability

**Goal:** Rebuild and locally verify the single-article ingestion pipeline against `test/fixtures/gpt55_article/` so that text ingest + graph connectivity completes in <2 min with no crash. This unblocks Phase 5 Wave 1+ (RSS, daily digest, cron) and is the immediate prerequisite gate.

**Target features (6-scope, Hermes-adjusted):**

- Image pipeline correctness: `min(w,h)<300` filter, inter-image sleep=0, per-image logging
- Scrape-first full-text classification (DeepSeek) — stop relying on unreliable WeChat `digest`
- LightRAG state management: pre-batch buffer flush + rollback on async timeout
- Text-first ingest (ingest/enrich decoupling): article body into LightRAG immediately, Vision runs asynchronously to append image sub-docs
- LLM timeout alignment: env `LLM_TIMEOUT=600`, DeepSeek client-side timeout, dynamic per-chunk scaling
- E2E verification harness: fixture benchmark with <2min text-ingest gate + stage-level timing report

**Explicit carve-outs (moved to future milestones):**

- v3.2 (Phase 5 Wave 1 Batch Reliability): checkpoint/resume, Vision cascade circuit breaker, regression fixtures, operator runbook
- v3.3 (independent infra): Vertex AI SA migration + GCP project isolation
- Phase 5-00b full re-run on Hermes (belongs in Phase 5)

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

*Last updated: 2026-04-30 (Milestone v3.1 started)*
