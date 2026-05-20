---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
title: Memory System
---

# Memory System

## Definition / Overview

A **Memory System** is the architectural layer of an AI agent (or, more generally, an LLM-driven application) that is responsible for storing, organizing, retrieving, and updating contextual information across turns, sessions, and tasks. Because large language models are intrinsically stateless — the model itself retains nothing between API calls — any sense of continuity, personalization, or learning that an agent appears to exhibit is provided externally by a memory system layered on top of the model.

In the Harness framework documented in the Claude Code reverse-engineering analysis, the memory system is described as the second layer of the harness, holding intermediate results, sub-tasks, discussions, user preferences, history, errors, and successes across sessions, with different frameworks implementing it differently^[article:5a362bf61e]. More broadly, a Memory System in agent architectures is "a component responsible for storing, retrieving, and managing contextual information," ranging from layered abstractions to file-based persistent stores^[article:5a362bf61e].

Industry articles converge on the same point: ChatGPT and Claude appear to "remember" because product teams layer memory systems on top of stateless models, and developers building their own agents must implement that layer themselves (Redis, *Build Smarter AI Agents*).

## Architecture / Design

Modern memory systems are typically organized along two orthogonal axes: **temporal scope** (short-term vs. long-term) and **content type** (episodic, semantic, procedural, etc.).

### Short-term vs. long-term

- **Short-term / working memory** holds the current conversation buffer and intermediate scratch state for a single session or agent loop. It is cleared once the session ends.
- **Long-term memory** persists across sessions in a database, vector store, or filesystem, enabling cross-session continuity and personalization (IBM, *What Is AI Agent Memory*).

### Content-typed memory

Following the cognitive-science taxonomy popularized by LinkedIn's Cognitive Memory Agent (CMA) and IBM's framing, three canonical types are distinguished:

- **Episodic memory** — captures interaction history and dialogue events so an agent can recall past exchanges.
- **Semantic memory** — stores structured factual knowledge distilled from interactions (user attributes, entities, preferences).
- **Procedural memory** — encodes learned workflows and behavioral patterns; in advanced systems (e.g., LangMem), an agent can even rewrite its own system prompt based on accumulated feedback (Atlan, *Best AI Agent Memory Frameworks 2026*).

LinkedIn's CMA is positioned as a **shared memory infrastructure layer** sitting between application agents and the underlying language model, so that planners, reasoners, and executors in a multi-agent system all read and write a common memory rather than maintaining redundant per-agent state (InfoQ via *AI 前线*).

![Agent Conversational Memory Store architecture](/static/img/c434b61d8e/1.jpg)

### Layered memory architectures

A widely adopted pattern is **layered (Lₙ) memory**, where information is progressively distilled from raw logs into stable user/project profiles. The TencentDB Agent Memory project exemplifies this with an L0–L3 hierarchy:

- **L0 — raw records**: the unedited transcript and task trace, kept as ground-truth evidence.
- **L1 — atomic memories**: short, retrieval-friendly facts (preferences, instructions, project rules).
- **L2 — scenario memories**: clustered notes that bind L1 atoms into coherent scenes (e.g., "the user's writing style on this project").
- **L3 — long-term profile**: stable cross-scene traits, written conservatively to avoid one-shot mischaracterizations (e.g., "don't promote a single coffee comment to 'coffee-driven human'") (TencentDB Agent Memory write-up).

![Layered memory L0–L3](/static/img/26b555ac6b/3.jpg)

A closely related layered design appears inside Claude Code's harness, where a **Generic Agent's Layered Memory Architecture** spans L0 Meta Rules → L1 Insight Index → L2 Global Facts → L3 Skills/SOPs → L4 Session Archive, plus an Experience Memory side-channel that records task process and reusable lessons^[article:5a362bf61e].

### File-based memory in Claude Code's Harness

The Claude Code analysis describes a concrete, file-based memory backend located at `src/memdir/`, supporting four memory types — `user`, `feedback`, `project`, and `reference` — backed by structured Markdown files with typed YAML frontmatter and a `MEMORY.md` index capped at 200 lines to prevent runaway growth^[article:5a362bf61e]. Key design decisions documented in the source include:

- A `scanMemoryFiles` routine that reads only the first `FRONTMATTER_MAX_LINES` of each `.md` file, sorts by mtime, and caps results at `MAX_MEMORY_FILES = 200`^[article:5a362bf61e].
- Use of `Promise.allSettled` (rather than `Promise.all`) so that a single corrupted memory file cannot abort the whole scan — defensive engineering characteristic of a production harness^[article:5a362bf61e].
- A formatted **memory manifest** (`[type] filename (timestamp): description`) used both in the memory-selection prompt and in extraction-agent prompts^[article:5a362bf61e].
- A philosophy of **"explicit over implicit"**: memory is structured Markdown, not an opaque database, and memory scanning runs in parallel with API calls (prefetching) so it adds no latency^[article:5a362bf61e].

The harness also contains a separate **dynamic memory index** (200 lines) distinct from the static `CLAUDE.md` file, allowing adaptive context handling, and uses **memory prefetching** driven by context pressure to preload relevant context before it is needed^[article:5a362bf61e].

### Three-layer storage in OpenClaw

A complementary design appears in OpenClaw, which uses a **three-layer pyramid** — Raw Layer → Knowledge Layer → Semantic Layer — coupled with a "memory file semantic positioning and access strategy" that performs semantic encoding for precise retrieval^[article:5a362bf61e].

![OpenClaw three-layer memory architecture](/static/img/9954261402/0.jpg)

## History / Origin

The need for an explicit memory system surfaced early in the LLM era. As Grant Slatton recalls about GPT-3, with only a 4K-token window an "amnesiac author" cannot keep characters, settings, or motivations consistent across a novella; this drove practitioners toward external state stores (Slatton, *LLM Memory*). Slatton also emphasizes a foundational issue still relevant today: **all knowledge has an explicit or implicit reference frame** (temporal, spatial, fictional), and naive key-value memories collapse under temporal change ("capital of Germany" is Berlin, Bonn, or Flensburg depending on era and timeline).

Early implementations relied almost entirely on vector databases — embeddings of past turns retrieved by cosine similarity. By the GPT-4 era, practitioners recognized that vectors alone struggle with episodic ordering, conflict resolution, and reasoning, prompting the move toward **hybrid layered systems** combining graphs, structured tables, and vectors (Slatton; Vectorize, *Best AI Agent Memory Systems*).

Around 2024–2026, three trends crystallized:

1. **Memory as infrastructure.** LinkedIn's CMA and Databricks' MemAlign reposition memory as a horizontal platform shared across agents rather than a per-agent afterthought (Databricks, *Memory scaling for AI agents*).
2. **Externalization as a design philosophy.** Industry slides on Agent system design now frame memory externalization, skill externalization, and protocol externalization as the defining shift — progress comes not from bigger models but from offloading cognitive burden to explicit, reusable components.
3. **Memory operating systems.** Concepts like **MemOS** (referenced in 李志宇's talk on memory engineering) treat memory lifecycle, classification, extraction, integration, and forgetting as first-class OS-level services^[article:5a362bf61e].

## Key Concepts / Components

**Memory Lifecycle Management.** A complete memory system includes classification, extraction, integration, and forgetting, often organized into stages such as Session Memory (real-time extraction), KAIROS Daily Log (persistent logging), Auto-Dream (cross-session consolidation), and four canonical memory types (User Preference, Project Information, Feedback Correction, External Reference)^[article:5a362bf61e].

**Memory Prefetching.** A technique to preload relevant context from memory based on context pressure, used in Claude Code to avoid latency penalties^[article:5a362bf61e].

**Memory Manifest / Index.** A compact, human-readable listing of available memories (filename, type, timestamp, description) used to let the LLM choose what to load — analogous to a card catalog rather than dumping the full library into context^[article:5a362bf61e].

**Experience Memory.** A side-channel that records task process, results, and reusable lessons — what worked, common pitfalls, and priorities for next time — turning memory from static storage into a feedback-updated system^[article:5a362bf61e].

**Memory Scope (Global vs. Local).** A taxonomy axis from the *Complex Networks of AI Agentic Systems* survey, classifying systems by whether agents share global memory or maintain local memory, with direct consequences for coordination and scalability.

**Token-budgeted memory.** Empirical work cited in the Claude Code analysis shows that **Condensed Memory** (165 tokens) achieves the same Task Success Rate (66.48%) as a **Redundant Memory** baseline (288 tokens), versus 13.87% for No-Memory and 52.44% for Full-Memory — strong evidence that distillation, not raw retention, drives utility^[article:5a362bf61e].

**Hardware substrate.** At the inference layer, "memory" also means GPU **HBM** (storing weights, KV cache, activations) and on-chip **SRAM** (staging data for tensor cores); HBM↔SRAM bandwidth is the dominant bottleneck in the decode phase^[article:5a362bf61e]. Cerebras's 44 GB on-chip SRAM is one attempt to flatten this hierarchy.

## Notable Use Cases / Examples

- **Claude Code (Harness).** File-based memdir with four memory types, MEMORY.md index, prefetching, and structured Markdown — a reference implementation of "explicit over implicit" memory^[article:5a362bf61e].
- **Hermes Agent.** A three-layer memory system supporting search and editing, persisting conversation history to disk while keeping system-prompt snapshots^[article:5a362bf61e].
- **OpenClaw.** Three-layer hybrid memory (Raw / Knowledge / Semantic) with a semantic positioning and access strategy and a QMD-backed local search backend^[article:5a362bf61e].
- **TencentDB Agent Memory.** Open-source L0–L3 layered memory targeted at long-running companion agents (Alice, Cola) where "aha moments" depend on durable, well-curated user models.
- **LinkedIn Cognitive Memory Agent (CMA).** Shared-memory infrastructure for the Hiring Assistant; combines episodic, semantic, and procedural memory plus near-context retrieval, semantic search, and summarization-based compaction (InfoQ).
- **Databricks MemAlign on Genie Space.** Demonstrates **memory scaling**: agent accuracy and efficiency improve as more interactions accumulate into a structured + unstructured store backed by Lakebase.
- **Redis Agent Memory Server.** Two-tier (working memory in RAM, long-term in RediSearch VSS) backend integrated with LangGraph, Mem0, and LangMem (Redis blog).
- **MemAgent.** Storage component accessed by Read and Write Heads, iteratively updated with relevant document chunks^[article:5a362bf61e].
- **Memory-Layered Context (governance pattern).** An architectural pattern combining an Agent, Memory Bank (long-term), Memory Profiles (working memory), Agent Gateway, Agent Identity, and Agent Registry — treating memory like a microservice with governance^[article:5a362bf61e].

![Memory-Layered Context pattern](/static/img/26b555ac6b/2.jpg)

## Cross-references

- [[harness]]
- [[claude-code]]
- [[openclaw]]
- [[hermes-agent]]
- [[layered-memory-architecture]]
- [[memory-prefetching]]
- [[experience-memory]]
- [[context-engineering]]
- [[cognitive-memory-agent]]
- [[memos]]
- [[hbm]]
- [[kv-cache]]
- [[tencentdb-agent-memory]]
- [[memalign]]

## Further Reading

- [LLM Memory — Grant Slatton](https://grantslatton.com/llm-memory) — Foundational essay on reference frames, vector embedding limitations, and why naive memory schemes break under temporal/fictional context.
- [Best AI Agent Memory Systems in 2026 — Vectorize](https://vectorize.io/articles/best-ai-agent-memory-systems) — Side-by-side comparison of Mem0, Zep, Letta, LangMem, LlamaIndex Memory, and others.
- [Best AI Agent Memory Frameworks in 2026 — Atlan](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) — Deep dive on LangMem's procedural memory and Redis's two-tier backend.
- [What Is AI Agent Memory? — IBM](https://www.ibm.com/think/topics/ai-agent-memory) — Canonical taxonomy of episodic, semantic, and procedural memory.
- [Memory scaling for AI agents — Databricks](https://www.databricks.com/blog/memory-scaling-ai-agents) — Argues that agent quality scales with accumulated memory, plus the MemAlign experiment.
- [How to Build AI Agents with Redis Memory Management — Redis](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/) — Practical patterns for short-term + long-term memory on Redis + LangGraph.
- [The 5 Types of AI Agent Memory Every Developer Needs to Know — dev.to](https://dev.to/sreeni5018/the-5-types-of-ai-agent-memory-every-developer-needs-to-know-part-1-52fn) — Developer-oriented walkthrough of STM, working memory, and LTM tooling.
- [Three Types of AI Agent Memory — Cobus Greyling](https://cobusgreyling.substack.com/p/three-types-of-ai-agent-memory) — Factual vs. experiential memory and case/strategy/skill decomposition.
- [Intro to Memory Management in AI Agents (YouTube)](https://www.youtube.com/watch?v=n-slj72yx8w) — Talk on the agent-memory lifecycle and multi-agent memory transfer.
- [为 AI 智能体设计记忆机制：揭秘 LinkedIn 的认知记忆智能体](http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767&idx=1&sn=b3d620a57e8833c4928da40f67fdecd1&chksm=ce76a5dbf9012ccdd1b4702fc96b85fe496591549c109333872f89d16b133323ade3b9e07a94#rd) — Translation of LinkedIn's CMA architecture article (episodic / semantic / procedural memory in production).
- [聊聊 Agent 的记忆系统，到底应该记什么？](https://mp.weixin.qq.com/s/iDS_d_fcSkrpXtDa-r_pWA) — TencentDB Agent Memory's L0–L3 layered scheme explained in plain language.