---
name: omnigraph_architect
description: |
  Use this skill when the user wants architecture advice for a solo-dev project,
  wants to query the knowledge graph about architecture patterns, or wants to ingest
  a GitHub repository into the knowledge base. Trigger phrases include: "what stack
  should I use", "recommend a tech stack", "architect my project", "what architecture
  for", "should I use X or Y", "add this GitHub repo to my KB", "ingest this repo".

  This skill has three modes: Propose (guided stack recommendation using 28 solo-dev
  rules from rules_engine.json), Query (freeform architecture question answered via
  the knowledge graph), and Ingest (add a GitHub repo's README and metadata to the
  knowledge graph). Propose mode runs a 2-4 turn conversation; Query and Ingest are
  single-turn.

  Do NOT use this skill when: the user wants to ingest a WeChat article or PDF — use
  omnigraph_ingest instead. Do NOT use when the user wants a general KB query not
  about architecture — use omnigraph_query instead. Do NOT use when the user asks
  about graph health or node counts — use omnigraph_status.
compatibility: |
  Requires: GEMINI_API_KEY in ~/.hermes/.env, Python venv at $OMNIGRAPH_ROOT/venv,
  rules_engine.json at $OMNIGRAPH_ROOT/rules_engine.json.
  Optional: GITHUB_TOKEN (avoids GitHub API rate limiting for Ingest mode).
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
---

# omnigraph_architect

## Quick Reference

| Task | Input | Command |
|------|-------|---------|
| Stack recommendation | Design question | `scripts/architect.sh propose "<question>"` |
| Architecture query | Factual question | `scripts/architect.sh query "<question>"` |
| Ingest GitHub repo | GitHub URL | `scripts/architect.sh ingest "<github-url>"` |

## When to Use

- User asks "what stack should I use for X" or "recommend technologies for Y"
- User asks "should I use X or Y" about an architecture choice
- User asks a factual architecture question ("what is LangChain", "how does FAISS work")
- User provides a GitHub URL and wants the repo added to the knowledge base
- User says "architect my project" or "help me choose a stack"

## When NOT to Use

- User wants to ingest a WeChat article or PDF → use `omnigraph_ingest`
- User wants a general KB query not about architecture → use `omnigraph_query`
- User asks about graph health or node counts → use `omnigraph_status`
- User wants to delete or manage entities → use `omnigraph_manage`

## Mode Selection

Determine the mode from the user's intent before calling architect.sh:

| User intent | Mode | Example |
|------------|------|---------|
| Wants stack advice or "what should I use" | `propose` | "What stack for a solo AI chatbot?" |
| Asks a factual architecture question | `query` | "What is the difference between FAISS and pgvector?" |
| Provides a GitHub URL to add to KB | `ingest` | "Add https://github.com/user/repo to my KB" |
| Ambiguous — could be advice or factual | `propose` | Default to propose; it includes KB context |

## Decision Tree

### Mode 1: Propose (Guided Stack Recommendation)

This is a multi-turn conversation. Follow these steps exactly:

**Turn 1 — Default Guess:**

Present a confident starting assumption:

> "Based on what you're asking, here's my starting assumption: you're a solo developer
> building a web app or API, moderate scale. My default recommendation would be:
>
> PostgreSQL + FastAPI (or Next.js) monolith, deployed to Vercel/Render, with managed auth.
>
> Two quick questions will let me sharpen this — or say 'go' if that already sounds right
> and I'll give you the full breakdown."

**If user says "go" or "that sounds right":** Skip to Turn 4 output using Web/SaaS + Time defaults.

**Turn 2 — Q1 (Project Type):**

> "What type of project is this? Pick the closest:
> **(A)** AI/LLM app — chatbot, RAG, agent, or anything calling an LLM
> **(B)** Web app or SaaS — users, pages, API, database
> **(C)** Data pipeline or CLI tool — ETL, scraping, automation scripts"

**Turn 3 — Q2 (Primary Constraint):**

> "What's your biggest constraint right now?
> **(A)** Time — I need to ship fast
> **(B)** Scale — I expect growth and need to not paint myself into a corner
> **(C)** Learning — I want to learn the stack properly, even if it's slower"

**Turn 4 — Output:**

Run:
```bash
scripts/architect.sh propose "<Q1 answer> <Q2 answer> <original question>"
```

Present the output in this exact format:

```
## Stack Recommendation
- **Label:** One-line rationale (3-5 bullets)

## Don't Use
- **Name** — reason (rule_NNN) (3-5 bullets)

## TDD Quick Start
(one concrete command sequence for the recommended stack)
```

**Edge cases:**
- User's answer doesn't map to A/B/C → treat as (B) Web/SaaS, say so explicitly
- User skips questions → use Web/SaaS + Time defaults, add caveat: "Say 'refine' to adjust"
- User gives hybrid answer ("web app with LLM") → use Web/SaaS primary, append AI integration notes
- User asks a factual question mid-flow → switch to Query mode, then resume Propose

### Mode 2: Query (Architecture Knowledge)

Single-turn. Run immediately:

```bash
scripts/architect.sh query "<user question>"
```

Present the result directly. No conversation flow needed.

### Mode 3: Ingest (GitHub Repository)

Single-turn. Validate the URL is a GitHub repository URL first.

Announce: "Adding repository to knowledge base — this may take 30–60 seconds..."

Run:
```bash
scripts/architect.sh ingest "<github-url>"
```

**Guard clause:** If the URL is not a `github.com` URL, respond:
"⚠️ Ingest mode only accepts GitHub repository URLs (github.com/owner/repo). For WeChat articles or PDFs, use the `omnigraph_ingest` skill."

### Mode 4: Invalid or missing input

Respond: "I can help with architecture in three ways:
1. **Stack recommendation** — tell me what you're building
2. **Architecture query** — ask me a factual question
3. **Ingest a repo** — give me a GitHub URL to add to the knowledge base

What would you like?"

## Error Handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`" |
| `rules_engine.json` not found | "⚠️ Setup error: rules_engine.json not found at project root" |
| venv missing | "⚠️ Setup error: venv not found. Run: `pip install -r requirements.txt`" |
| GitHub URL invalid | "⚠️ Ingest mode only accepts GitHub repository URLs (github.com/owner/repo)" |
| Empty KB result | "No relevant architecture content found. Try ingesting relevant repos or articles first." |

For full script interface (env vars, exit codes, mode dispatch), see
`references/api-surface.md`.

## Related Skills

- To ingest WeChat articles or PDFs: `omnigraph_ingest`
- To query non-architecture topics: `omnigraph_query`
- To check graph health and statistics: `omnigraph_status`
- To delete or manage graph entities: `omnigraph_manage`
