# Agent Ecosystem 2026 — VitaClaw Architecture Intelligence

## Purpose

`data/agent_ecosystem_2026.opml` is a curated, custom-namespaced OPML file that
replaces the previous `data/karpathy_hn_2025.opml` 92-feed snapshot for OmniGraph-Vault's
Phase 5 RSS pipeline. The Karpathy HN 2025 list is a general "best blogs on Hacker News"
collection (programming languages, lifestyle, tech philosophy) — high quality, but
mostly off-topic for VitaClaw, whose scope is **agent runtimes, memory systems, MCP,
sandbox, evaluation, browser automation, and graph-based RAG**.

This OPML carries **three custom-namespace attributes** (`omg:dimension`, `omg:priority`,
`omg:source_type`) on every leaf so Phase 5's classifier (`enrichment/rss_classify.py`)
and daily-digest grouping (`enrichment/daily_digest.py`) have meaningful structure
without an LLM round-trip per source.

Consumers:

- `scripts/seed_rss_feeds.py` (Phase 5 Plan 05-01) — parses the OPML and writes
  rows into the `rss_feeds` table, populating new `dimension`, `priority`,
  `source_type` columns.
- `enrichment/rss_classify.py` (Phase 5 Plan 05-03) — emits `dimensions: list[str]`
  per article using the same 7-dimension taxonomy enumerated in this file.
- `enrichment/daily_digest.py` (Phase 5 Plan 05-05) — groups RSS articles by primary
  `dimension` for the daily digest's per-section rendering; KOL articles render flat.

## Custom namespace

```xml
<opml version="2.0" xmlns:omg="https://omnigraph-vault/ns">
```

Three attributes are required on every `<outline type="rss">` leaf:

| Attribute            | Allowed values                                                                  | Meaning                                                                                                          |
| -------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `omg:dimension`      | `architecture` \| `project` \| `library` \| `framework` \| `skill` \| `tool` \| `idea` | Primary taxonomic dimension for daily-digest grouping. One value per source.                                     |
| `omg:priority`       | `core` \| `peripheral`                                                          | `core` = directly relevant to VitaClaw architecture; `peripheral` = adjacent or general industry signal.         |
| `omg:source_type`    | `github_release` \| `official_eng_blog` \| `curated_blog`                       | Origin type. Drives downstream UX (release notes get a different render than essays).                            |

Group folders (non-leaf `<outline>` elements that organize feeds into categories like
`Memory Systems`, `Coding Agents`, `MCP`) carry only `text` / `title` and do **not**
need `omg:*` attributes.

### Dimension taxonomy reference

These 7 values are mirrored in `enrichment/rss_classify.py::VALID_DIMENSIONS` so the
LLM classifier and the OPML schema stay aligned:

- **architecture** — graph databases, KG-RAG topologies, agent orchestration patterns
  (LightRAG, graphrag, langgraph, neo4j, kuzu).
- **project** — runnable user-facing applications (aider, open-interpreter, claude-code,
  codex, cline, openclaw, vitaclaw).
- **library** — focused single-purpose Python/JS packages (pydantic-ai, instructor,
  outlines, lancedb, MCP SDKs, vendor SDKs).
- **framework** — multi-component agent toolkits (langchain, autogen, crewAI, dspy,
  llama_index, smolagents, letta).
- **skill** — evaluation harnesses and benchmark suites (SWE-bench, openai/evals,
  promptfoo).
- **tool** — runtime infrastructure (memory stores, browser drivers, sandboxes,
  routers — mem0, browser-use, e2b, daytona, litellm, ollama, firecrawl).
- **idea** — protocols, conceptual frameworks, engineering blogs, opinion essays
  (MCP specification, gvisor, all official_eng_blog and curated_blog entries).

## Curation rationale (per category)

- **Memory Systems** — mem0, cognee, zep, letta. Drops vector-only stores and
  closed-source memory products. All four are core to VitaClaw's multi-tier
  memory architecture.
- **Graph and KG-RAG** — LightRAG (already in production), graphrag (Microsoft's
  reference implementation), neo4j (storage backend), kuzu (alternative graph DB),
  llm-graph-builder (Neo4j Labs reference). Direct architectural intel.
- **Agent Frameworks** — Twelve frameworks across the spectrum: production-grade
  (langchain, autogen, crewAI, dspy, llama_index, openai-agents-python,
  claude-agent-sdk-python), Chinese-ecosystem (Qwen-Agent), and lightweight
  alternatives (smolagents, letta, haystack). MetaGPT and camel were dropped to
  stay under the 80-cap; both are still healthy projects, just lower signal density.
- **Coding Agents** — aider, open-interpreter, continue, cline, codex, claude-code.
  Direct competitors-and-peers to VitaClaw's coding-agent surface.
- **Browser Automation and Sandboxing** — Playwright (canonical browser driver),
  browser-use (LLM-driven browser), e2b + daytona (sandbox runtimes), gvisor
  (sandbox primitive), firecrawl (scrape API), tavily-python (search API).
  trycua/cua dropped — peripheral relative to firecrawl/playwright.
- **MCP** — Specification, servers, python-sdk, typescript-sdk. All four are essential
  to the MCP-as-tool-protocol vision for VitaClaw.
- **LLM Routing and Serving** — litellm (the routing layer), vllm, ollama. sglang
  and llama.cpp dropped — peripheral relative to litellm + vllm coverage.
- **Validation and Structured Output** — pydantic-ai, outlines, instructor. These
  are the canonical structured-output libraries; everyone else wraps one of these.
- **Vector Stores and Embeddings** — lancedb (current production choice for
  OmniGraph-Vault), chroma (broad popularity), pgvector (Postgres-native).
  qdrant dropped — peripheral; if VitaClaw needs a heavier vector store later,
  this is where to add it back.
- **Evaluation and Observability** — SWE-bench, openai/evals, langfuse, promptfoo.
  Phoenix/Arize and opik dropped — peripheral; both are observability players
  similar in scope to langfuse.
- **Document Processing and SDKs** — markitdown (Microsoft's Office-to-Markdown
  converter, used in OmniGraph-Vault ingestion), unstructured, anthropic-sdk-python,
  openai-python.
- **User-Mandated** — `openclaw/openclaw` (368k stars, "your own personal AI
  assistant — the lobster way") and `vitaclaw/vitaclaw` (16 stars, user's namesake
  repo). See **Known blind spots** for the user-named entries that could not be
  resolved to canonical repos.
- **Engineering Blogs** — 8 official_eng_blog entries: HuggingFace, LangChain,
  Cloudflare, GitHub, Microsoft Old New Thing, AWS Machine Learning, Stack Overflow,
  Vercel. Anthropic, OpenAI, DeepMind, Mistral were probed but their canonical RSS
  feeds either 404'd or were blocked by the local Cisco Umbrella proxy at probe
  time — operator should re-test on the production Hermes host before acceptance.
- **Curated Karpathy Survivors** — 13 entries kept from the upstream Karpathy 92.
  Selection rule: agent/AI/LLM commentary or directly relevant systems-engineering
  perspective. Kept: simonwillison.net, gwern.net, dwarkesh.com, garymarcus.substack.com,
  minimaxir.com, lucumr.pocoo.org, mitchellh.com, antirez.com, matklad.github.io,
  eli.thegreenplace.net, geoffreylitt.com, wheresyoured.at, rachelbythebay.com.
  Dropped: ~75 generic programming/lifestyle/security blogs that don't move the
  needle for VitaClaw scope. The pruning rule was "would a VitaClaw reader find
  this useful for daily digest" — an aggressive cut.

The Karpathy 92 → 13 reduction (~85% drop) reflects how mismatched the upstream
list is against this scope. The 79 dropped entries are not low-quality — they're
just outside the agent ecosystem.

## How to add a new feed

1. **Verify the repo has ≥1000 stars** (for `github_release` feeds):
   ```bash
   gh api repos/<owner>/<repo> --jq .stargazers_count
   ```
   If <1000 and not user-mandated, do not add. Document the rejection in
   "Known blind spots" if the case is interesting.

2. **Verify the feed URL returns 200** (or note environmental block):
   ```bash
   curl -sIL -m 8 -A 'Mozilla/5.0' '<xmlUrl>' | head -1
   ```
   For GitHub `releases.atom`: the URL is mechanical — `https://github.com/<owner>/<repo>/releases.atom` —
   no curl probe needed.

3. **Assign all 3 omg attributes**:
   - `omg:dimension` ∈ {architecture, project, library, framework, skill, tool, idea}
   - `omg:priority` ∈ {core, peripheral}
   - `omg:source_type` ∈ {github_release, official_eng_blog, curated_blog}

4. **Place under the correct category folder** in the OPML (Memory Systems,
   Agent Frameworks, etc.). Add a new folder if no existing one fits — but the
   schema does not require folder presence; flat OPML would still parse.

5. **Re-run** `tests/verify_rss_opml.py` (created by Phase 5 Plan 05-01 Task 1.3)
   to confirm the new entry parses, all 3 omg:* attrs are non-empty, and total
   leaf count is still in `[60, 80]`.

## Known blind spots

- **Twitter / X excluded** — no public RSS endpoints for X.com. Many AI researchers
  publish their primary thoughts on X first; that signal is not captured here.
  Out-of-band (e.g. nitter feeds, third-party wrappers) is brittle and was rejected.
- **Closed-source-only tools excluded** — Devin, Cursor IDE, Windsurf. No
  releases.atom, no engineering blog with structured release notes. They appear
  in news coverage that arrives via the `Curated Karpathy Survivors` channel
  (simonwillison.net, dwarkesh.com).
- **Engineering blogs that 404'd or were proxy-blocked at curation time**:
  Anthropic news (`https://www.anthropic.com/news/rss.xml`), OpenAI blog
  (`https://openai.com/blog/rss.xml`), DeepMind research (`https://research.google/blog/rss/`),
  Mistral news (`https://mistral.ai/news/rss.xml`), Netflix/Uber/Airbnb engineering.
  Some of these are likely environmental blocks (Cisco Umbrella proxy on the
  curator's machine). Operator should re-probe on the Hermes production host before
  Phase 5 execution; if any return 200, add them under the `Engineering Blogs`
  folder.
- **User-named repos that could not be resolved to a canonical GitHub repo**:
  - **hermes** / **hermes-agent** — no canonical public repo found at
    `hermes-agent/hermes-agent` or `hermes-agent/hermes`. Hermes Agent itself is
    invoked through the Hermes CLI/Cron and may be closed-source or distributed
    privately. Excluded from the OPML; ingestion of Hermes release notes can be
    added later if a public release feed is published.
  - **gsd** — multiple unrelated repos use this name (game/dev shorthand).
    No canonical match for the GSD workflow tool that the OmniGraph-Vault project
    references. Excluded.
  - **MerkleTree** — generic data-structure name. `merkletreejs/merkletreejs`
    (1236 stars) exists but is unrelated to the agent ecosystem. Excluded; if a
    specific Merkle-tree-based agent or memory project becomes relevant later
    (e.g. for verifiable memory), add then.
- **vitaclaw is included with 16 stars** because the user explicitly mandated it
  and it is presumably a private/early-stage canonical repo that will gain stars.
  Star-cap exception documented here per curation rules.

## Cron compatibility note

This OPML is consumed by `scripts/seed_rss_feeds.py` (Phase 5 Plan 05-01) to populate
the `rss_feeds` table. The seed script reads `omg:dimension`, `omg:priority`, and
`omg:source_type` and writes them into matching columns. After Phase 5 ships, the
cron pipeline (`rss_fetch.py` → `rss_classify.py` → `daily_digest.py`) consumes
`rss_feeds.dimension` etc. without ever re-reading the OPML. To swap source lists,
re-run the seed script with `--reset` (not implemented yet — Phase 5 follow-up if
needed).
