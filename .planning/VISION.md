# OmniGraph-Vault — Product Vision

**Last Updated:** 2026-04-23
**Status:** Active — guiding v2.0 Knowledge Infrastructure MVP

---

## What We're Building

A **local, personal knowledge infrastructure** that gives Hermes Agent (and OpenClaw) persistent,
opinionated memory about AI tools and engineering practices. The primary user-facing surface is one
skill: `/architect` — a virtual CTO that gives safe defaults, explicit don't-use lists, and TDD
templates to vibe coders.

> **Core value:** When a solo developer asks "what stack should I use?", they don't get a generic
> ChatGPT answer. They get a rule-engine-backed recommendation drawn from real GitHub tools and
> real practitioner opinions — with explicit "don't use X because Y" guidance.

---

## The /architect Skill

`/architect` is a single portal with three modes:

| Mode | Trigger | What happens |
|------|---------|--------------|
| **Propose** | "Help me choose my stack", "architect my project" | GSD:DISCUSS 4-step flow → rules engine + KB → safe defaults + don't-use list + TDD template |
| **Query** | "What is LangChain?", "how does LlamaIndex work?" | Direct KB lookup via `kg_synthesize.py` hybrid mode |
| **Ingest** | "Add this tool to my KB: github.com/…" | `ingest_github.py` → LightRAG → `entity_registry.json` |

The Propose mode is the primary value. It is NOT a cutting-edge recommendation engine — it is
a **conservative advisor** that prevents overengineering for the solo/indie dev context.

### GSD:DISCUSS Conversation Flow (Propose mode)

```
Turn 1 → Default Guess:    "For a solo project, I'd default to [monolith + SQLite + FastAPI]"
Turn 2 → Q1 (context):     "What type of project is this — hobby, indie SaaS, or research?"
Turn 3 → Q2 (constraint):  "What's your primary constraint — time, scale, or learning?"
Turn 4 → Output:           Stack recommendation + ⚠️ Don't Use + TDD template hint
```

---

## Knowledge Sources

Two source types feed the same LightRAG knowledge graph:

| Source | Ingestion | Volume |
|--------|-----------|--------|
| **GitHub READMEs** | `ingest_github.py` → GitHub REST API | 50–100 AI tool repos |
| **KOL articles** | `ingest_wechat.py` | 5–10 WeChat/Zhihu/GitHub issue posts |

**Integration:** Both sources call `rag.ainsert()` on the same LightRAG instance. Entities are
linked at the graph level. `canonical_map.json` (Cognee) normalizes Chinese↔English name variants.
At query time, `rag.aquery(mode=hybrid)` retrieves across both sources simultaneously.
See `REQUIREMENTS.md` → "Knowledge Source Integration Model" for the full technical explanation.

---

## Rules Engine

`rules_engine.json` (20–30 rules) is the stable, opinionated core. It is bootstrapped from
Copilot deep research (Prompts 1–5 in [MILESTONE-2-SIMPLE-GUIDE.md](MILESTONE-2-SIMPLE-GUIDE.md))
and covers:

- Overengineering traps (enterprise tools for solo scale)
- Tech debt from wrong tool selection
- Solo-dev framework decision framework
- AI agent architecture anti-patterns
- TDD adoption patterns for vibe coders

Schema: `{ id, condition, recommendation, dont_use[], weight, tags[], test_scenario }`

The KB (LightRAG) provides explanatory depth behind each rule. The rules drive the output; the
KB provides the "why" when the user asks follow-up questions in Query mode.

---

## What Is NOT In Scope

- Multi-user or team sharing — single user, intentionally
- Real-time scraping beyond WeChat/GitHub — future milestone
- Cutting-edge recommendations — conservative safe defaults only
- Hermes deployment (Phase 3 / v1.1) — prerequisite for v2.0 but separate milestone
- Graphify MCP — does not exist; replaced by GitHub REST API

---

## Execution Map

```
v1.1 (current, in progress)
├── Phase 1: Bug Fixes + Gate 6 Validation        [1/2 plans complete]
│   └── Gate 6 manual checkpoint still pending → PREREQUISITE for v2.0
├── Phase 2: SkillHub-Ready Skill Packaging       [COMPLETE]
└── Phase 3: Hermes Deployment + Gate 7           [not started]

v2.0 Knowledge Infrastructure MVP
├── Phase 4: Foundation Patch + Rules Bootstrap
│   ├── ingest_github.py (GitHub REST API)
│   ├── config.py additions (ENTITY_REGISTRY_FILE, GITHUB_TOKEN)
│   └── rules_engine.json (20–30 rules from Copilot research)
├── Phase 5: KB Population + Rules Quality Gate
│   ├── 50+ GitHub repos ingested
│   ├── 5–10 KOL articles ingested
│   └── Integration gate: hybrid query returns multi-source results
└── Phase 6: /architect Skill + Multi-Turn Testing
    ├── omnigraph_architect SKILL.md (3-mode decision tree)
    ├── architect.sh (mode dispatch wrapper)
    ├── skill_runner.py multi-turn enhancement
    └── 28+ test cases passing (9 ingest + 10 query + 9 architect)
```

**Entry point for execution sessions:** [MILESTONE-2-SIMPLE-GUIDE.md](MILESTONE-2-SIMPLE-GUIDE.md)
**Detailed requirements:** [REQUIREMENTS.md](REQUIREMENTS.md)
**Architecture decisions:** [research/ARCHITECTURE.md](research/ARCHITECTURE.md)

---

## Technology Bets (Non-Negotiable)

| Decision | Choice | Why |
|----------|--------|-----|
| LLM | Gemini 2.5 Flash/Pro | Already integrated; no migration |
| KG engine | LightRAG (kuzu backend) | Already deployed; handles 60–100 docs comfortably |
| Memory | Cognee | Entity canonicalization + query recall |
| GitHub ingestion | GitHub REST API via `requests` | No new dependencies; 3-4 GET calls per repo |
| Rules format | JSON file, `json.load()` | Local-first, no database, version-controlled |
| Scraping | Apify (primary) → CDP (fallback) | Already working for WeChat |
| Platform | Windows (Git Bash) + Python venv | User's constraint; all scripts must work in Git Bash |
