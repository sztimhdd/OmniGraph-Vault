---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:064f03c965
- article:1272b434a5
- article:4b7c022702
- article:796a06b3e5
- article:5a362bf61e
- article:41cabfee7f
- article:99a2043522
- article:b75ac3d32c
- article:e781713458
- article:8a6f3af80a
- article:9c53e463b1
- article:c8fb07ed4c
- article:9cbd555c68
title: Anthropic
---

# Anthropic

## Definition / Overview

Anthropic is a U.S.-based artificial intelligence research and product company best known for developing the **Claude** family of large language models — including Claude Sonnet 4-5, Claude Opus 4.6/4.7, and the Mythos Preview internal model. Beyond foundation models, Anthropic ships an expanding portfolio of AI products: **Claude Code** (a production-grade agentic CLI), **Claude Cowork** (an AI-native collaborative workspace), **Claude Design**, **Loop**, **Routines**, and the **Claude Desktop App**^[article:4b7c022702]. Anthropic also created the **Model Context Protocol (MCP)**, an interoperability protocol that has become a de-facto standard for connecting AI agents to external tools, services, and data sources^[article:c8fb07ed4c].

The company positions itself as an AI-safety-first research lab, but its product strategy has clearly evolved beyond safety research alone. Source-code analyses of Claude Code reveal that Anthropic is "not iterating on a coding tool — they are incubating a new species" of AI agent with persistent memory, autonomous action, and team-collaboration capabilities^[article:4b7c022702].

![Anthropic's roadmap from AI assistant to AI partner](/static/img/4b7c022702/0.jpg)

## Architecture / Design

Anthropic's product stack is layered around the Claude model as the reasoning core, surrounded by **harnesses** — environment and feedback wrappers that turn raw model capability into reliable agent behavior. According to Anthropic's published research on harness engineering, agentic coding requires "stronger environment and feedback wrappers" rather than purely larger models^[article:5a362bf61e].

Key architectural commitments:

- **Hybrid reasoning model.** Unlike Qwen-style models that separate reasoning from tool use, Claude integrates reasoning and tool calling into a single framework, optimized for long-cycle agent workflows^[article:4b7c022702].
- **Memory lifecycle.** Claude Code's source code reveals a four-class memory system (user preferences, feedback corrections, project info, external references) plus a three-layer memory architecture: real-time Session Memory, cross-session Auto-Dream consolidation, and an append-only KAIROS Daily Log^[article:4b7c022702].
- **Context engineering.** Anthropic publicly advocates "just-in-time" context strategies, where agents retrieve information on demand via tools (file systems, search, MCP) rather than pre-loading everything into the prompt — a position described in detail on the Anthropic engineering blog.
- **Skills.** Anthropic defines Skills as **pre-compiled context packages** that ship reusable instructions, tools, and assets to Claude. The official Anthropic Skills Marketplace can be installed into Claude Code via `/plugin marketplace add anthropics/skills`^[article:4b7c022702].
- **Neurosymbolic design.** Anthropic has acknowledged in Claude Code that scaling alone is insufficient and has integrated classical symbolic techniques alongside neural inference^[article:5a362bf61e].

![Claude Code's memory and agent architecture](/static/img/4b7c022702/4.jpg)

## History / Origin

Anthropic was founded in 2021 by former OpenAI executives (including Dario and Daniela Amodei) and has since raised through a Series G funding round announced in late 2025, with Claude Code alone reportedly running at $2.5B annual revenue at that time. Major milestones referenced in our corpus and the wider press:

- **MCP** released by Anthropic Labs as an open protocol — now adopted across LangChain, LangGraph, Semantic Kernel, and most frontier AI products^[article:c8fb07ed4c].
- **Claude Code** launched as a CLI agent harness, eventually open-sourced (50万 lines of TypeScript across 1,900 files) and analyzed publicly^[article:4b7c022702].
- **Founder's Handbook: Building AI-Native Startups** published officially by Anthropic, codifying a four-stage path (Ideation → MVP → Launch → Scale) for AI-native founders^[article:41cabfee7f].

![AI-Native four-stage startup framework](/static/img/cc56a5c6a7/0.jpg)

- **Public quality incident (April 2026):** Anthropic acknowledged that optimizing three Harness-layer bugs inadvertently degraded Claude's intelligence, sparking user backlash and subscription cancellations^[article:9c53e463b1]. Anthropic published a postmortem ("An update on recent Claude Code quality reports") and introduced a **soaking period** rollout policy to prevent recurrence.
- **Compute crunch (2026):** Anthropic visibly tightened rate limits, restricted third-party harnesses (including OpenClaw), and required KYC authentication — moves widely interpreted as symptoms of an AI compute supply shortage^[article:e781713458]^[article:8a6f3af80a]. Martin Alderson's analysis frames Anthropic's product changes as "the canary in the coal mine for inference demand."

## Key Concepts / Components

### Claude (Model Family)

The Claude family — Sonnet, Opus, Haiku, and the internal Mythos line — powers every Anthropic product. Internally, Mike Krieger (CPO) has stated that Claude writes nearly 100% of Anthropic's own code^[article:4b7c022702]. Claude operates with a 200K-token context window in which roughly 1.4% is system prompt and 8.3% is tool definitions^[article:5a362bf61e].

### Claude Code

Anthropic's reference implementation of a Harness — an agentic CLI built on `@anthropic-ai/sdk` that supports executor and project-manager modes, isolated Git worktrees, multi-Claude parallelism, and skill plugins^[article:4b7c022702]^[article:5a362bf61e].

![Claude Code agent execution surface](/static/img/4b7c022702/5.jpg)

### Claude Cowork

A "computer operation assistant" using natural language to orchestrate work across MCP-connected tools (Gmail, Calendar, Slack, internal SaaS). Cowork is Anthropic's bet to disrupt the SaaS market by replacing point tools with skill-driven agentic workflows^[article:41cabfee7f]^[article:9cbd555c68].

### Model Context Protocol (MCP)

Often described as "USB-C for AI devices," MCP standardizes how agents discover, invoke, and connect to tools. It is adopted by OpenAI, Microsoft, and Anthropic alike, and is treated by Anthropic as the tool-layer foundation of a three-layer agent infrastructure^[article:c8fb07ed4c]. Critics note MCP can contribute to "Context Rot" by loading too many tools into LLM context.

### Skills

Pre-compiled context packages that bundle instructions, tool sets, and reference docs. Skills include `alwaysLoad` flags and can be composed with MCP servers as Capability Modules^[article:4b7c022702].

### Founder's Handbook

Anthropic's official manual for AI-native startups, organized around Ideation, MVP, Launch, and Scale stages, with concrete prompts for using Claude, Claude Code, and Claude Cowork at each stage^[article:41cabfee7f].

![Three AI leverage points for lean startups](/static/img/cc56a5c6a7/1.jpg)

### Internal Culture & Org Design

Anthropic maintains a continuous-delivery pipeline, employs PMs with engineering backgrounds, and recruits people who have lived through industry cycles for resilience. Boris Cherny (engineering VP) has described how Anthropic's organizational transformation around AI-generated code shrank development cycles from six months to one day^[article:4b7c022702].

## Notable Use Cases / Examples

- **Apple internal tooling.** Apple runs custom versions of Claude on its own servers for internal product development, even while Anthropic reportedly quoted prices high enough that Apple turned to Google for some workloads^[article:064f03c965]. A Claude.md file briefly appeared in an official Apple App and was deleted within 24 hours^[article:064f03c965].
- **xAI data-center deal.** Anthropic is a counterparty in a notable data-center arrangement with xAI (analyzed by Simon Willison and others).
- **Government refusals.** Anthropic refused a U.S. Department of Defense request for AI technology supporting mass surveillance and autonomous weapons; OpenAI subsequently took the contract. The refusal increased Claude's brand trust and downloads^[article:4b7c022702].
- **Wordsmith, Carta Healthcare, Anything, Cogent, Duvo, Zingage, Kindora.** Featured in the Founder's Handbook as AI-native startups built on Claude and Claude Code, ranging from legal tech to clinical data abstraction to no-code app generation^[article:41cabfee7f].
- **Third-party harness ecosystem.** OpenClaw, ZeroClaw, OpenWolf, Hermes Agent, and the DeepSeek-TUI project all integrate with or compete against Anthropic's harness — DeepSeek-TUI was a Rust-based "DeepSeek version of Claude Code" that hit 11,000+ GitHub stars in days^[article:b75ac3d32c]^[article:e781713458]^[article:796a06b3e5]^[article:8a6f3af80a].

![DeepSeek-TUI as an open alternative to Claude Code](/static/img/b75ac3d32c/0.jpg)

- **Quality regression incident.** A Harness-layer bug fix degraded Claude's reasoning intensity, triggered context forgetting, and led some users to migrate to Codex. Anthropic's postmortem and apology became a case study in AI model demand management^[article:9c53e463b1].
- **Controversial subscription policy.** Anthropic's restriction of OpenClaw's subscription quota triggered the launch of ZeroClaw and migration guides on hermes101.dev^[article:e781713458]^[article:8a6f3af80a].

## Cross-references

- [[claude]]
- [[claude-code]]
- [[claude-cowork]]
- [[mcp-model-context-protocol]]
- [[claude-design]]
- [[skills-anthropic]]
- [[harness-engineering]]
- [[openclaw]]
- [[zeroclaw]]
- [[hermes-agent]]
- [[openai]]
- [[deepseek]]
- [[apple]]
- [[founders-handbook]]
- [[ai-compute-crunch]]
- [[neurosymbolic-ai]]

## Further Reading

- [Building Effective AI Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents) — Anthropic's canonical taxonomy distinguishing workflows from agents.
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Articulates the "just-in-time" context retrieval philosophy now central to Claude Code.
- [Building Effective AI Agents: Architecture Patterns and Implementation Frameworks (PDF)](https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf) — Anthropic's pattern catalogue including dynamic agent generation.
- [How we built our multi-agent research system — Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) — Engineering writeup of a lead-agent-with-subagents pattern, including durable execution.
- [Our framework for developing safe and trustworthy agents — Anthropic](https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents) — Anthropic's principles for human oversight, transparency, and least-privilege defaults in Claude Code.
- [AI Fluency: Framework and Foundations — Anthropic](https://www.anthropic.com/learn/claude-for-you) — Education and Skills resources for Claude users.
- [Anthropic Agents — Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/agents/providers/anthropic) — Reference for using Anthropic models inside Microsoft's Agent Framework, including extended thinking and MCP tooling.
- [Is the AI Compute Crunch Here? — Martin Alderson](https://martinalderson.com/posts/is-the-ai-compute-crunch-here/) — Analysis citing Anthropic's $2.5B Claude Code run-rate and arguing DRAM supply caps inference growth.
- [No, it doesn't cost Anthropic $5k per Claude Code user — Martin Alderson](https://martinalderson.com/posts/no-it-doesnt-cost-anthropic-5k-per-claude-code-user/) — Counter-argument on Anthropic unit economics.
- [Notes on the xAI/Anthropic Data Center Deal — Simon Willison](https://simonwillison.net/2026/May/7/firefox-claude-mythos/#atom-everything) — Commentary on Anthropic's compute partnership landscape.
- [Tracing the Thoughts of a Large Language Model — Anthropic (2025)](https://garymarcus.substack.com/p/the-biggest-advance-in-ai-since-the) — Referenced research on Chain-of-Thought faithfulness in Claude.