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

*Last updated: 2026-04-27*
