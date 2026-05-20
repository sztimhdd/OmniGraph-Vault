---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
- article:1272b434a5
- article:9b427c8cb5
title: Context Engineering
---

# Context Engineering

## Definition / Overview

**Context Engineering** is the discipline of dynamically curating, structuring, and managing the information that enters a large language model's (LLM) context window so that the model receives the right information, at the right time, in the right form. Unlike Prompt Engineering — which focuses on a single instruction or system prompt — Context Engineering treats the *entire* input payload as the unit of design: system prompts, user instructions, conversation history, retrieved knowledge, tool definitions and results, memory, and runtime state^[article:9b427c8cb5].

It is widely framed as the second stage in the evolution of large model application engineering, sitting between Prompt Engineering (2022–2024) and Harness Engineering (2026)^[article:9b427c8cb5]^[article:5a362bf61e]. As Anthropic's engineering team puts it, context engineering is "the art and science of curating what will go into the limited context window from that constantly evolving universe of possible information" — an *iterative* curation phase performed every inference turn, in contrast to the discrete authorship task of writing a prompt.

![Evolution path: Prompt → Context → Harness Engineering](/static/img/6cde11932a/0.jpg)

## Architecture / Design

At the architectural core of Context Engineering is the **Context** itself — the complete input information set delivered to an LLM on each call. It typically aggregates five sources^[article:9b427c8cb5]:

- **System Prompt** — role, goals, rules, output boundaries
- **User Prompt** — the user's current request
- **Chat History** — prior turns of the conversation
- **Knowledge** — retrieved documents, RAG snippets, private data
- **Tool** — tool schemas, calls, and results

![CONTEXT as the central aggregator of five input sources](/static/img/6cde11932a/1.jpg)

This is sometimes drawn as a **Context Engineering Pipeline**: data flows from heterogeneous sources, is filtered and compressed, and is finally packed into the model's context window. Designers must respect three hard constraints that motivate the entire discipline^[article:9b427c8cb5]:

1. **Finite context window** — even with million-token models, naïvely concatenating chat history, RAG hits, and tool logs blows the budget and causes "request exceeds maximum length" errors.
2. **More context ≠ better performance** — long inputs trigger "lost in the middle," attention dilution, and reasoning degradation.
3. **Context is cost** — every token has a dollar price and a latency cost; longer prompts mean slower, more expensive, harder-to-debug systems.

![Why context engineering is needed: ideal vs. reality](/static/img/6cde11932a/2.jpg)

The standard design response is a three-tool toolkit^[article:9b427c8cb5]:

- **挑选 / Selection (Picking)** — retrieve relevant snippets, choose only the tools the task needs, prune stale history.
- **压缩 / Compression** — summarize chat history, extract structured fields from tool outputs.
- **隔离 / Isolation** — split work across sub-agents or parallel contexts so each sees only what it needs (multi-agent architectures, per-task state).

![Three common methods: Selection, Compression, Isolation](/static/img/6cde11932a/8.jpg)

LangChain frames the same toolkit as **write, select, compress, isolate**, and Anthropic emphasizes structured retrieval (file systems, inboxes, bookmarks) for *just-in-time* context loading rather than dumping everything up front.

## History / Origin

The progression that produced Context Engineering is now standard lore in AI engineering circles^[article:5a362bf61e]^[article:9b427c8cb5]:

- **2022–2024 — Prompt Engineering.** Teach the model to follow instructions: role assignment, output formatting, chain-of-thought, few-shot examples.
- **2025 — Context Engineering.** Andrej Karpathy's widely-cited reframing shifted attention from "writing better prompts" to "filling the context window with the right information." Tooling like RAG, AGENTS.md / CLAUDE.md project files, conversation summarization, and cross-session memory matured into mainstream practice.
- **2026 — Harness Engineering.** OpenAI's engineering team and figures like Martin Fowler began naming the *outer* layer — tools, permission models, feedback loops, sandboxes, task orchestration — as a distinct discipline. Context Engineering is identified as the first (or third) pillar inside this larger Harness^[article:5a362bf61e]^[article:1272b434a5].

LangChain's own benchmark experiments — where optimizing only the harness around a fixed model jumped a coding benchmark from outside the top 30 to the top 5 — helped cement the consensus that the bottleneck is context and harness, not raw model IQ^[article:1272b434a5].

## Key Concepts / Components

**Context as a Scarce Resource.** Every token costs money, latency, and attention budget. Claude Code's published architecture treats this as a first-class design principle, using lazy tool loading, on-demand memory, a four-level compression pipeline, ToolSearch for tool discovery, and "Microcompact" aging to keep the active window lean^[article:5a362bf61e].

**Context Pressure.** The token budget is the design constraint that drives all downstream architecture decisions — including the four-level compression pipeline, tool lazy loading, and memory prefetching strategies^[article:5a362bf61e].

**Memory Systems.** Memory persists across sessions; context is session-specific. Production agents typically combine a long-term **Memory Bank** (curated, durable knowledge) with a working-memory layer of **Memory Profiles** (low-latency, recent state) — the "Memory-Layered Context" pattern. Hermes, for example, ships file-based persistent memory with user, feedback, project, and reference types, plus team-memory synchronization^[article:5a362bf61e].

**Context Architecture.** Structured documentation (AGENTS.md, CLAUDE.md), hierarchical docs, and on-demand loading give the agent a navigable knowledge map rather than a wall of text^[article:5a362bf61e]^[article:1272b434a5].

**Context Fork Mode.** A skill-system pattern (notably in Claude Code) that spawns isolated sub-contexts for delegated work to prevent context pollution of the parent agent^[article:5a362bf61e].

**RAG vs. Context Engineering.** RAG is *one technique* inside Context Engineering — specifically the just-in-time retrieval layer. Increasingly, vendors like LlamaIndex and Weaviate argue that pure-RAG architectures are insufficient for agents and must be wrapped in broader context-engineering systems covering memory, workflow isolation, and tool orchestration^[article:1272b434a5]. Some commentators have framed this as the major RAG vendors "shorting RAG" in favor of full context-engineering stacks^[article:1272b434a5].

**Where it sits in the LLM Engineer roadmap.** In the popularized six-layer learning roadmap, RAG / Context Engineering is the third layer — *after* prompt and workflow design, *before* AI Coding, agents, and evals/observability^[article:1272b434a5].

![LLM Engineer roadmap with Context Engineering as layer 3](/static/img/d3bca4bb17/14.jpg)

## Notable Use Cases / Examples

**Claude Code.** Anthropic's coding agent is the most-dissected real-world Context Engineering case study. Its design treats context as a scarce resource, uses a 200-line memory index, separates a static `CLAUDE.md` from a dynamic memory system, applies a four-level compression pipeline, and defers non-core tools so they don't burn tokens until needed^[article:5a362bf61e]. Architecture-context documents are used to keep structural knowledge stable across sessions^[article:5a362bf61e].

**Hermes.** A self-improving agent framework with built-in `MEMORY.md` / `USER.md`, external memory providers, session search, and context-engine plugins; sub-agents inherit system prompts from a parent agent to maximize prompt-cache hit rate^[article:5a362bf61e].

**Multi-agent isolation.** A common production recipe combines all three classical methods: RAG selects relevant snippets, summarization compresses long sources, then sub-agents isolate disjoint task contexts. Each sub-agent loads only its task-specific tools and maintains its own state, avoiding cross-task pollution^[article:9b427c8cb5].

**Enterprise AI agents.** Mobisoft's writeup on enterprise deployments stresses that engineered context — persistent memory, retrieval precision, workflow isolation — is what separates fragile demos from agents that survive in production. Galileo's "Five Buckets" framework (offload, retrieve, isolate, compress, cache) and Weaviate's "Six Pillars" (agents, query augmentation, retrieval, prompting, memory, tools) are convergent industry vocabularies for the same idea.

**Limits of Context Engineering.** When agents move from QA into long-horizon workflows — code edits, multi-step tool calling, recovery from broken builds — Context Engineering alone is no longer sufficient. The discipline primarily handles input shaping, while task orchestration, permissioning, and feedback loops require Harness Engineering^[article:5a362bf61e]^[article:1272b434a5].

## Cross-references

- [[prompt-engineering]]
- [[harness-engineering]]
- [[claude-code]]
- [[hermes]]
- [[rag]]
- [[memory-system]]
- [[context-window]]
- [[agent-architecture]]
- [[multi-agent-systems]]
- [[context-compression]]
- [[memory-layered-context]]
- [[tool-use]]
- [[langgraph]]
- [[llamaindex]]

## Further Reading

- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Anthropic's canonical framing of context engineering as iterative curation, with concrete strategies for long-horizon agents.
- [Context Engineering for Agents](https://www.langchain.com/blog/context-engineering-for-agents) — LangChain's "write, select, compress, isolate" taxonomy with LangGraph implementation patterns.
- [Context Engineering Guide](https://www.llamaindex.ai/blog/context-engineering-what-it-is-and-techniques-to-consider) — LlamaIndex's overview, including the relationship to workflow engineering and structured outputs.
- [Context Engineering — LLM Memory and Retrieval for AI Agents](https://weaviate.io/blog/context-engineering) — Weaviate's "Six Pillars" framework covering agents, retrieval, memory, prompting, and tools.
- [Deep Dive into Context Engineering for Agents](https://galileo.ai/blog/context-engineering-for-agents) — Galileo's Five Buckets framework plus session-/step-level evaluation metrics.
- [Context Engineering for LLMs — Building Reliable AI Agents](https://mobisoftinfotech.com/resources/blog/ai-development/context-engineering-for-llms-enterprise-ai-agents) — Enterprise-focused perspective on memory, retrieval, and workflow isolation.
- [Optimizing any AI Agent Framework with Context Engineering](https://medium.com/@bijit211987/optimizing-any-ai-agent-framework-with-context-engineering-81ceb09176a0) — Bijit Ghosh's principles for adaptive context windows, context inheritance, and ROI metrics.
- [How to Optimize AI Agents with Context Engineering](https://www.linkedin.com/posts/bijit-ghosh-48281a78_optimizing-any-ai-agent-framework-with-context-activity-7357760656386760705-KI8a) — Companion LinkedIn post emphasizing "the discipline of forgetting well."
- [上下文工程是什么？过时了么？一文讲明白](http://mp.weixin.qq.com/s?__biz=MzI2OTg0MjI2Nw==&mid=2247486345&idx=1&sn=bf02d128383d4b4b232ab94dcbee7537&chksm=eadb69bdddace0abf3008e6f0bb7a2362b19e55ef27bcc95200720fc2b3a5e89402d0b1c2cf6#rd) — Chinese-language walkthrough of selection / compression / isolation with the diagrams used above.
- [今年爆火的 Harness Engineering 是什么](http://mp.weixin.qq.com/s?__biz=MzI1NDczNTAwMA==&mid=2247586245&idx=2&sn=8b6fd6d4ff0552dc38113aecb7d74e76&chksm=e9c37632deb4ff2415ff61cc0d716f21e9cc2cae3a3475a8b69b62e6fd3b2f36cc50a05204a0#rd) — Positions Context Engineering as the predecessor to Harness Engineering.