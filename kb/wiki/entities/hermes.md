---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:8a5a502c8b
- article:e85fd44dd4
- article:8a6f3af80a
- article:c8fb07ed4c
title: Hermes
---

# Hermes

## Definition / Overview

**Hermes** (also known as **Hermes Agent**) is an open-source, self-hosted AI agent framework developed by Nous Research. It is designed around a self-improving learning loop in which the agent converts successful task executions into reusable skills, persists user knowledge across sessions, and continuously refines its own capabilities. Unlike chat-shell agents that reset between sessions, Hermes is intended to run persistently — on a laptop, a VPS, a GPU cluster, or a serverless backend — and to accumulate experience over time ^[article:e85fd44dd4]^[article:8a6f3af80a].

Hermes is frequently positioned alongside (and as an alternative to) OpenClaw, having appeared after OpenClaw's surge in popularity and triggered what some Chinese-language commentators dubbed a "百虾大战" (Hundred Shrimp War) of agent frameworks ^[article:c8fb07ed4c]^[article:8a6f3af80a]. According to NVIDIA's developer blog, Hermes crossed 140,000 GitHub stars within three months of release and became, by some measures, the most-used agent on OpenRouter.

## Architecture / Design

Hermes' architecture embeds five key hooks — **delegate, skills, memory, search, and provider hooks** — directly inside the agent loop, rather than treating them as external orchestration concerns. Its runtime, sometimes called **Harness**, manages context, tools, permissions, and execution control, and supports a switchable execution backend across local machines, VPS, GPU clusters, and serverless environments such as Daytona and Modal ^[article:8a5a502c8b].

The article *Harness 到底是什么？看看 OpenClaw、Hermes、Claude Code 的演绎吧* describes Harness as "the runtime around the model" — the model is the capability source, while Harness decides whether that capability can leave the demo stage and survive in real workflows ^[article:8a5a502c8b]. The same article emphasizes that as Agent products mature, the focus shifts from "can the model call a tool?" to "can it act inside a controlled system?" — covering context organization, error classification, permission boundaries, and recovery paths ^[article:8a5a502c8b].

![Harness illustrated by OpenClaw, Hermes, Claude Code](/static/img/682afaec30/3.jpg)

Key architectural properties include:

- **Five-layer system structure**: Entry Layer (CLI + 20+ messaging adapters), Gateway Layer, Execution Layer, Extension Layer, and Storage Layer.
- **In-process multi-agent delegation**: Sub-agents are created in-process as isolated workers with their own context and tool subsets, executed in parallel via thread pools, and aggregated back to the parent agent through synchronous structured returns ^[article:8a6f3af80a].
- **Process-bounded system boundary**: Hermes uses process boundaries (rather than session boundaries, as in OpenClaw) and maintains a child agent runtime status table for state tracking, recursive interruption propagation, and concurrent-write protection.
- **Error classification**: API/tooling failures are routed through a `FailoverReason` enum with 14 categories, surfaced as `ClassifiedError` objects carrying four boolean recovery flags (`retryable`, `should_compress`, `should_rotate_credential`, `should_fallback`). The main loop dispatches on these flags rather than parsing error strings ^[article:8a5a502c8b].
- **Permission control bound to actions and context**, not just tool names — read-only commands flow through, while destructive ones (delete, deploy, send email, modify shared memory) require confirmation ^[article:8a5a502c8b].

According to the official Hermes Agent architecture documentation, the codebase organizes the agent core (`run_agent.py`), CLI (`cli.py`), tool dispatch (`model_tools.py`), an SQLite/FTS5-backed `hermes_state.py`, and a pluggable `ContextEngine` ABC with a default lossy-summarization compressor.

## History / Origin

Hermes was developed by **Nous Research** and released in early 2026, following — and in dialogue with — the rise of OpenClaw. According to commentary from the Chinese AI community, Hermes did not aim to replicate OpenClaw's enterprise-governance ambitions; instead, it iterated on OpenClaw's pain points and prioritized **agent personal improvement over enterprise control** ^[article:c8fb07ed4c].

The Grok-Hermes integration article notes that Grok and Hermes were connected via OAuth, allowing Hermes to use Grok's capabilities for chat, self-learning, persistent memory, and image/video generation ^[article:e85fd44dd4]. Similar OAuth-based integrations exist for ChatGPT (via OpenAI Codex) and Gemini ^[article:e85fd44dd4].

To lower the onboarding barrier for Chinese users — given that the original documentation is dense and English-only — the community launched **hermes101.dev**, providing a 5-minute install path, a 7-day beginner course, and a migration page for OpenClaw users ^[article:8a6f3af80a].

![hermes101.dev launch](/static/img/8a6f3af80a/0.jpg)

Per the NVIDIA blog and the Nous Research GitHub repository, subsequent releases (e.g., v0.12.0 "The Curator", and "The Tenacity Release") added an autonomous background Curator that grades and prunes the skill library, durable multi-agent Kanban with heartbeat/zombie detection, persistent cross-turn goals (the "Ralph loop"), and platform expansions to 20+ messaging platforms.

## Key Concepts / Components

**Learning Loop.** After execution, Hermes evaluates what happened, extracts reusable patterns, and precipitates them into either **Skills** or **Memory**. This is the trait that defines Hermes as a self-evolving agent and that, per the Turing Post comparison, distinguishes it most sharply from OpenClaw's controller-first design ^[article:8a6f3af80a].

**Memory System.** Hermes ships a layered memory system that includes:
- Built-in `MEMORY.md` (general persistent memory) and `USER.md` (user preferences/model).
- Eight external memory providers (only one active at a time, to avoid schema conflicts).
- Session search powered by SQLite full-text search, used as a retrieval method that *processes* historical sessions rather than dumping raw text into context.
- A pluggable Context Engine for compression ^[article:8a5a502c8b].

**Skills.** Skills are open-standard, agentskills.io–compatible units of procedural knowledge. Hermes can dynamically generate new skills, update existing ones, and inherit skills from OpenClaw without reinstallation. The Hermes Skill Hub aggregates community-contributed skills ^[article:8a6f3af80a].

**Multi-Agent / Sub-Agent Delegation.** Parent agents delegate sub-tasks to in-process sub-agents created via a delegation tool. Hermes supports hierarchical delegation, Mixture-of-Agents, single-layer parallel expansion (the default), and a maximum derivation depth parameter that bounds recursion. Results return synchronously as a structured array.

![Hermes multi-agent architecture](/static/img/861242ae2f/23.jpg)

**Multi-Bot / Profiles.** Each Hermes Profile is a fully isolated agent — independent `config.yaml`, `.env`, `SOUL.md`, gateway process, log directory, and memory space. The "multi-Bot methodology" article frames Profiles as "hiring different people," not "switching roles," and recommends partitioning by *role* (daily butler, professional coder, late-night companion) rather than *function* (search bot, writing bot).

**SOUL.md.** Loading a `SOUL.md` file converts the default compliant AI-assistant persona into an autonomous operator with a defined personality, scope, and boundaries.

**Hermes Workspace.** A web console running on port 3000 that exposes six panels — chat, memory, skills, terminal output, tool cards, and multi-agent collaboration — over an Agent Gateway on port 8642. According to the Workspace install guide, deployment requires Node.js ≥ 22, Python ≥ 3.11, and pnpm.

**Model Scheduling Layer / Multi-Model Formation.** Hermes treats itself as a model orchestration platform. The "Hermes 多模型编队" concept routes tasks on demand: the most capable model for the main role, the most stable model as fallback, and cost-effective models for auxiliary roles such as Vision, OCR, Web Extract, Title Generation, and Session Search. Reported integrations include Claude (Anthropic), OpenAI/ChatGPT, Gemini, Grok, Kimi (including Kimi K2.6), GLM-5.1, Qwen, MiniMax, and local models via Ollama or LM Studio ^[article:e85fd44dd4]^[article:c8fb07ed4c].

## Notable Use Cases / Examples

- **Grok integration.** A widely shared article describes Hermes' OAuth-based hookup with xAI's Grok, enabling Hermes to chat, self-learn, persist memory, and generate images and videos through Grok's stack ^[article:e85fd44dd4].

- **GLM-5.1 production pilot.** The article *我把Hermes里23个Agent全切到GLM-5.1* documents switching all 23 agents in a Hermes deployment to GLM-5.1, finding execution stronger than GPT but with one notable weak point ^[article:c8fb07ed4c].

- **Kimi K2.6 SOTA-coding test.** *Hermes 接入 Kimi K2.6 实测* reports SOTA code-generation results inside Hermes, alongside two real pain points around speed and hallucination ^[article:c8fb07ed4c].

- **Replacement for Dify-based intelligent customer service.** A real-world reflection cited in the Nexus / RAG-end article describes a team migrating an exploded Dify-based customer-service system onto Hermes, encountering further problems, and finally moving to a self-built system with Dify as fallback — illustrating both Hermes' broad applicability and the genuine difficulty of production RAG ^[article:8a5a502c8b].

- **OpenClaw-to-Hermes migration.** hermes101.dev provides a dedicated migration page so that existing OpenClaw users can carry over Telegram bot tokens, Honcho memory data, and Agent Profile configurations into Hermes ^[article:8a6f3af80a].

![hermes101.dev migration](/static/img/8a6f3af80a/2.jpg)

- **Conference coverage.** Hermes appears as a focal topic in the AI second-half top-tier conference agenda alongside OpenClaw and Harness engineering, signaling its position as a reference framework for the current Agent paradigm ^[article:c8fb07ed4c].

![Conference agenda](/static/img/c8fb07ed4c/1.jpg)

## Cross-references

- [[openclaw]] — closely related agent framework; Hermes is widely compared with and migrated to from OpenClaw.
- [[harness]] — the runtime concept Hermes most concretely embodies.
- [[claude-code]] — another Harness exemplar, often cited alongside Hermes for permission-prompt UX.
- [[nous-research]] — organization developing Hermes.
- [[soul-md]] — persona/identity file consumed by Hermes.
- [[grok]] — model integrated with Hermes via OAuth.
- [[glm-5-1]] — model used in production by Hermes deployments.
- [[kimi-k2-6]] — code-capable model integrated with Hermes.
- [[hermes101-dev]] — Chinese-language onboarding site for Hermes.
- [[skills-hub]] — community skill registry compatible with Hermes.
- [[context-engineering]] — the engineering layer Hermes operationalizes inside its agent loop.

## Further Reading

- [What Is Hermes Agent? The OpenClaw Alternative with a Built-In Learning Loop](https://www.mindstudio.ai/blog/what-is-hermes-agent-openclaw-alternative/) — overview of the learning-loop design and where Hermes makes sense vs. OpenClaw.
- [AI 101: Hermes vs OpenClaw: Local AI Agents Compared](https://www.turingpost.com/p/hermes) — side-by-side comparison of orchestration philosophies, memory model, and skills.
- [Hermes Agent: The Open-Source AI Agent That Actually Remembers What It Learned Yesterday](https://medium.com/@creativeaininja/hermes-agent-the-open-source-ai-agent-that-actually-remembers-what-it-learned-yesterday-278441cd1870) — narrative account of Hermes' adoption wave and architectural intent.
- [Hermes Unlocks Self-Improving AI Agents, Powered by NVIDIA RTX](https://blogs.nvidia.com/blog/rtx-ai-garage-hermes-agent-dgx-spark/) — NVIDIA's positioning of Hermes for always-on local execution on RTX/DGX Spark hardware.
- [Inside Hermes Agent: A Deep Dive into Its Technical Architecture](https://medium.com/@hecate_he/inside-hermes-agent-a-deep-dive-into-its-technical-architecture-175dcf67d671) — detailed walkthrough of Hermes' agent core, tool, memory, and learning layers.
- [Architecture | Hermes Agent — Nous Research Docs](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture) — official architecture reference, file layout, and data-flow diagrams.
- [Hermes Agent Documentation](https://hermes-agent.nousresearch.com/docs/) — official user-facing documentation, quick links, and feature catalog.
- [NousResearch/hermes-agent — GitHub](https://github.com/nousresearch/hermes-agent) — source code, release notes, and the changelog tracking the Curator and Tenacity releases.