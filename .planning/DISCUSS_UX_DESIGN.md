# /architect Propose Mode: Conversation Design

**Status:** Decided
**Covers:** ARCH-01 — GSD:DISCUSS 4-step flow for Propose mode
**Inputs:** rules_engine.json (28 rules), VISION.md, REQUIREMENTS.md, ARCHITECTURE.md

---

## 1. QUESTION SELECTION

### Q1: "What are you building?"

**The question (Turn 2):**

> "What type of project is this? Pick the closest:
> **(A)** AI/LLM app — chatbot, RAG, agent, or anything calling an LLM
> **(B)** Web app or SaaS — users, pages, API, database
> **(C)** Data pipeline or CLI tool — ETL, scraping, automation scripts"

**Why this question:** The 28 rules split cleanly into three relevance tiers based on project type. AI-specific rules (vector stores, agent orchestration, MLOps, feature stores, LLM API strategy) are noise for a standard web app. Frontend rules (state management, WebSockets, UI frameworks) are noise for a CLI pipeline. This is the single question that eliminates the most irrelevant rules per answer.

**Rule activation by answer:**

| Answer | Primary rules (condition matches directly) | Secondary rules (general architecture, always apply) | Rules excluded |
|--------|---------------------------------------------|------------------------------------------------------|----------------|
| **(A) AI/LLM** | 002 (local_vector_store), 009 (direct_llm_api), 010 (api_over_self_hosting), 011 (single_agent_first), 012 (skip_mlops_early), 013 (skip_feature_store) | 001, 003, 005, 021, 022, 023, 024, 025 | 004 (api), 006 (auth), 017 (frontend), 018 (state mgmt), 019 (websockets), 020 (managed auth) |
| **(B) Web/SaaS** | 001, 003, 004, 005, 006, 007, 008, 014, 016, 017, 018, 019, 020, 021, 022, 023, 026, 027 | 024, 025, 028 | 002 (vector), 009 (llm api), 010 (self-host llm), 011 (agents), 012 (mlops), 013 (feature store) |
| **(C) Pipeline/CLI** | 001, 007, 015 (workflow orchestration) | 003, 005, 022, 023, 024, 025, 026 | 004, 006, 008, 017, 018, 019, 020, 027 (web/frontend rules), 011, 012, 013 (agent/ML rules) |

**Partition quality:** Answer A activates 6 AI-specific rules that B/C never see. Answer B activates 12 web-specific rules that A/C never see. Answer C activates 1 unique rule (015 workflow) and shares a small general-architecture subset. This means Q1 eliminates 6-12 irrelevant rules per answer — the highest-leverage single question possible given the rule set.

### Q2: "What's your primary constraint?"

**The question (Turn 3):**

> "What's your biggest constraint right now?
> **(A)** Time — I need to ship fast
> **(B)** Scale — I expect growth and need to not paint myself into a corner
> **(C)** Learning — I want to learn the stack properly, even if it's slower"

**Why this question:** After Q1 narrows the rule set by project type, Q2 re-weights the surviving rules by priority. It determines whether the output emphasizes speed (managed services, skip testing), future-proofing (modular monolith, database choice), or craft (TDD, avoid shortcuts).

**Weight modifiers by answer:**

| Answer | Rules weighted UP (show first, stronger language) | Rules weighted DOWN (mention briefly or skip) |
|--------|--------------------------------------------------|----------------------------------------------|
| **(A) Time** | 021 (managed_infra, +2), 005 (simple_deployment, +1), 020 (managed_auth, +1), 022 (avoid_niche, +1) | 024 (tdd_where_it_matters, -2), 025 (risk_based_testing, -1), 016 (orm_profiling, -1) |
| **(B) Scale** | 001 (sql_first, +1), 003 (modular_monolith, +2), 008 (cache_after_measuring, +1), 023 (no_premature_abstractions, +1) | 021 (managed_infra, -1), 026 (scripted_deploys, -1) |
| **(C) Learning** | 024 (tdd_where_it_matters, +2), 025 (risk_based_testing, +1), 028 (tdd_anti_patterns, +1), 016 (orm_with_eyes_open, +1) | 021 (managed_infra, -1) — still recommend managed, but emphasize understanding what it hides |

**Why not team size as Q2?** All 28 rules already assume solo-dev (every rule is tagged `solo-dev`). Asking "how big is your team?" would not change any rule activation — the engine has no team-scaled rules. The constraint axis is the only remaining discriminator that reshuffles priority within the post-Q1 subset.

**Why not budget/cost?** Budget maps nearly 1:1 to the Time constraint (low budget = ship fast with managed free tiers). Adding it as a separate axis would produce answers indistinguishable from "Time."

---

## 2. DEFAULT GUESS DESIGN

**The default guess (Turn 1):**

> "Based on what you're asking, here's my starting assumption: you're a **solo developer building a web app or API**, moderate scale. My default recommendation would be:
>
> **PostgreSQL + FastAPI (or Next.js) monolith, deployed to Vercel/Render, with managed auth.**
>
> Two quick questions will let me sharpen this — or say 'go' if that already sounds right and I'll give you the full breakdown."

**Rationale:**
- **Solo developer** — all 28 rules are solo-dev tagged; this is the only persona the engine serves.
- **Web app** — answer (B) is the most common Q1 response. It activates 18 of 28 rules, the broadest coverage. Starting here means the default is useful even if the user skips questions.
- **PostgreSQL** — rule_001 (weight 9) and rule_027 (weight 8) both recommend it. It's the single strongest default in the engine.
- **Monolith** — rule_003 (weight 10, highest in the engine). Non-negotiable starting point.
- **Managed hosting** — rule_005 (weight 9) and rule_021 (weight 8). The solo-dev consensus.
- **Managed auth** — rule_006 (weight 8) and rule_020 (weight 9). Rolling custom auth is the highest-risk DIY.

**Why confident, not hedging:** The VISION.md states "conservative advisor that prevents overengineering." A hedge ("it depends on your needs") is the opposite of the product's value proposition. The default guess should feel like advice from a senior engineer who's seen this pattern 100 times.

**Early exit:** If the user says "go" or "that sounds right," skip Q1/Q2 and jump to Turn 4 output using the web/SaaS + Time defaults (most common profile). The agent should not force 4 turns when 2 suffice.

---

## 3. OUTPUT FORMAT CONTRACT

**Turn 4 output — exact structure:**

```markdown
## Stack Recommendation

- **Database:** PostgreSQL (single instance, JSONB for flexible fields)
- **Backend:** FastAPI with sync endpoints — async only where you need it
- **Frontend:** Next.js static export with Tailwind (or skip if API-only)
- **Auth:** Clerk or Supabase Auth (never roll your own)
- **Deploy:** Vercel (frontend) + Render/Fly.io (backend) — one environment, no staging

## Don't Use

- **Kubernetes** — you have one service; a $5 VPS or PaaS handles it (rule_005)
- **Microservices** — function calls, not network calls, until you feel team-coordination pain (rule_003)
- **Redis** — profile first; your DB's buffer pool is probably fine (rule_008)
- **LangChain** — direct API calls for <3 sequential LLM calls (rule_009) [only if AI project]
- **MongoDB** — your data has relationships; PostgreSQL handles JSON too (rule_027)

## TDD Quick Start

```bash
# For a FastAPI project:
pip install pytest httpx
# Write one integration test for your critical endpoint before anything else:
# tests/test_api.py → POST /users with valid data → assert 201
pytest tests/ -x --tb=short
```
```

**Format rules:**

| Element | Constraint |
|---------|-----------|
| Recommended stack | Exactly 3-5 bullet points. Each bullet: **bold label** + one-line rationale. |
| Don't Use | Exactly 3-5 bullet points. Each bullet: **bold name** + one-line reason + `(rule_NNN)` citation. Only include rules that match the user's Q1 project type. |
| TDD Quick Start | One concrete command sequence for the recommended stack. Not a generic "write tests first" — an actual command they can run. Matches the recommended backend framework. |
| Total length | Skimmable in <30 seconds. No paragraphs. No "it depends" qualifiers. |

**Stack selection logic:**

The output is not freeform. `architect.sh` prepends rules to `kg_synthesize.py`. The synthesis prompt should instruct Gemini to:
1. Filter rules by Q1 project type (include/exclude per table in Section 1)
2. Sort surviving rules by `weight` descending, then apply Q2 weight modifiers
3. Pick top 5 recommendations (highest adjusted weight)
4. Pick top 5 dont_use entries from those rules
5. Generate TDD template matching the top recommendation's stack

This is deterministic enough that two identical Q1+Q2 answers always produce the same core recommendation, with KB-sourced details varying.

---

## 4. EDGE CASES

### User's answer doesn't map to any Q1 option

**Example:** "I'm building a mobile game" or "hardware firmware"

**Decision:** Treat as **(B) Web/SaaS** and say so explicitly:

> "My knowledge base is strongest on web/API and AI/LLM projects. I'll give you general architecture advice using my web/SaaS rule set — take the stack-specific recommendations directionally."

Rationale: The rule engine has no mobile, game, or embedded rules. Better to give explicitly-scoped advice than to hallucinate rules that don't exist. The general architecture rules (003 monolith, 023 no premature abstractions, 024 TDD) apply universally.

### User skips Q1/Q2 and demands output directly

**Example:** "Just tell me what stack to use for my project" (no type/constraint info)

**Decision:** Use the default guess profile (Web/SaaS + Time constraint) and produce output immediately with a caveat:

> [Output using default profile]
>
> *This assumes a solo web app prioritizing speed. Say 'refine' if your project is AI/LLM or data-pipeline focused — I'll adjust.*

Rationale: The VISION says "confident and specific, not a hedge." Forcing questions when the user wants answers violates the product's value. The default profile (Web/SaaS + Time) is the highest-probability correct answer. Offering a one-word refinement path ("refine") keeps the door open without blocking.

### User gives a hybrid answer to Q1

**Example:** "It's a web app but it uses LLM for one feature"

**Decision:** Use Web/SaaS as primary set, then append the 3 highest-weight AI rules (009 direct_llm_api, 011 single_agent_first, 010 api_over_self_hosting) as a supplementary section:

> **AI Integration Notes** (since you're using LLM features):
> - Call the LLM API directly — no LangChain needed for <3 calls (rule_009)
> - One agent with 2-5 tools max (rule_011)
> - Use hosted inference, not self-hosted (rule_010)

### User asks a Query-mode question during Propose flow

**Example:** After Q1, user says "Wait, what is LangChain exactly?"

**Decision:** The SKILL.md decision tree handles this. If the user's message is a factual question (not a design question), the agent switches to Query mode mid-conversation: call `architect.sh query "<question>"` and return the KB answer. Then resume Propose flow: "Back to your stack — what's your biggest constraint?"

---

## Summary: Conversation Transcript (Golden Path)

```
AGENT (Turn 1 — Default Guess):
  "Based on what you're asking, here's my starting assumption: you're a solo
   developer building a web app or API, moderate scale. My default would be:
   PostgreSQL + FastAPI monolith, deployed to Vercel/Render, with managed auth.
   Two quick questions will sharpen this — or say 'go' for the full breakdown."

USER (Turn 2 answer): "It's an AI chatbot"

AGENT (Turn 2 — Q1 acknowledged + Q2):
  "Got it — AI/LLM app. What's your biggest constraint right now?
   (A) Time — ship fast  (B) Scale — don't paint into a corner  (C) Learning"

USER (Turn 3 answer): "Time, definitely"

AGENT (Turn 4 — Output):
  ## Stack Recommendation
  - **LLM:** Use hosted API (GPT-4/Claude) directly via SDK — no orchestration framework
  - **Vector store:** FAISS or LanceDB locally — move to pgvector if you add Postgres
  - **Backend:** FastAPI monolith with async endpoints for LLM calls
  - **Auth:** Skip for now — add Clerk when you have users
  - **Deploy:** Single Cloud Run service or Render

  ## Don't Use
  - **LangChain** — direct API calls for <3 LLM calls; framework adds complexity without value (rule_009)
  - **Multi-agent frameworks** (CrewAI, AutoGPT) — one agent, 2-5 tools max (rule_011)
  - **Pinecone** — local vector store handles <100K embeddings fine (rule_002)
  - **MLflow** — version prompts in Git, evaluate with scripts (rule_012)
  - **Self-hosted LLaMA** — use hosted API until volume justifies GPU cost (rule_010)

  ## TDD Quick Start
  ```bash
  pip install pytest httpx
  # Test your core chain: embed query → retrieve → LLM call → structured response
  # tests/test_chain.py → mock LLM response, assert output schema
  pytest tests/ -x --tb=short
  ```
```
