---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:8a5a502c8b
- article:28c974c2cd
- article:c8fb07ed4c
- article:e781713458
- article:54a36baa97
- article:9b4f7b24e0
- article:9f75b25295
- article:f39e186f16
- article:8a6f3af80a
- article:064f03c965
- article:1950549023
- article:c8cc5b1fb7
- article:9cf5b4b857
- article:e85fd44dd4
- article:781c9ac2c3
- article:805773ee29
title: OpenClaw
---

# OpenClaw

## Definition / Overview

**OpenClaw** is an open-source, self-hosted personal AI assistant and agent runtime framework. Branded with a red lobster mascot (🦞) and the tagline *"THE AI THAT ACTUALLY DOES THINGS,"* it differentiates itself from chatbots by executing concrete actions — browser automation, file manipulation, scheduled jobs, messaging — across the user's own computer, phone, or cloud server ^[article:c8cc5b1fb7]^[article:e781713458].

The project was previously known as **ClawdBot** and **MoltBot** before its current naming, and is colloquially called *龙虾* ("lobster") in the Chinese AI community ^[article:c8cc5b1fb7]. As of release **V2026.2.14**, it offers integration with 12+ messaging platforms (WhatsApp, Telegram, Slack, Discord, iMessage, Microsoft Teams, etc.), supports macOS/iOS/Android voice I/O, and renders a real-time **Canvas** UI controlled by the agent ^[article:e781713458].

According to the official GitHub README, OpenClaw installs as a global npm package (`npm install -g openclaw@latest`) and uses an `openclaw onboard --install-daemon` flow to register a Gateway daemon (launchd/systemd) that keeps the agent persistently running. It is licensed under MIT.

![OpenClaw landing page and release info](/static/img/e781713458/10.jpg)

## Architecture / Design

OpenClaw follows a **hub-and-spoke architecture**: a single Gateway acts as the control plane between user-facing channels and a central Agent Runtime ^[article:c8cc5b1fb7]. According to ppaolo.substack.com's architecture overview, the Gateway is a WebSocket server (default port `:18789`) that connects messaging platforms and control interfaces (CLI, macOS app, web UI, iOS/Android nodes) and dispatches each routed message to the runtime, which then assembles context, calls the model, executes tool calls, and persists state.

### Multi-Agent Sub-Session Model

Internally, OpenClaw is built as a **multi-agent, event-driven** system. Sub-tasks are delegated to **sub-agents** hosted inside **sub-sessions**, which are unified under a single session/runtime/permission/lifecycle hierarchy ^[article:c8cc5b1fb7]. A unified entry point handles control parameters such as runtime type, session persistence, context isolation, and sandbox policy when spawning a child session ^[article:c8cc5b1fb7].

![OpenClaw multi-agent architecture diagram](/static/img/861242ae2f/18.jpg)

Critically, sub-agent results are **not returned via function return** — they are posted as **completion events** that the parent session listens for, captures, and converges. This event-driven design allows nested sub-agents, parallel execution, and recovery from interruptions ^[article:c8cc5b1fb7].

![Sub-session creation flow](/static/img/861242ae2f/20.jpg)
![Result-return mechanism](/static/img/861242ae2f/21.jpg)

### Context, Memory & Skills

OpenClaw assembles context from a workspace of plain Markdown files: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `MEMORY.md`, `HEARTBEAT.md`, plus a daily ephemeral log under `~/.openclaw/workspace/memory/`. As described on Bibek Poudel's Medium walkthrough, this Markdown-first design makes memory inspectable and editable by the user.

The framework employs a **three-layer hybrid memory system** — a pyramid of *raw layer → knowledge layer → semantic layer* — to progressively abstract data from raw inputs to semantic understanding ^[article:c8cc5b1fb7].

![Three-layer memory storage structure](/static/img/9954261402/0.jpg)

**Skills** are domain-specific capability bundles loaded as `~/.openclaw/workspace/skills/<skill>/SKILL.md`. The community curates them in repositories like `VoltAgent/awesome-openclaw-skills` ^[article:8a5a502c8b].

### Task Execution Loop & Reliability Mechanisms

OpenClaw uses a classic ReAct-style **Task Execution Loop**: understand problem → decide next step → use tool/read file/run code → check result → repeat ^[article:c8cc5b1fb7]. To stabilize long-running execution, the system layers in a **Lane Queue Mechanism** to serialize concurrent operations and eliminate race conditions, plus an **Interruption Recovery** layer for timeouts, session changes, and failures ^[article:c8cc5b1fb7].

## History / Origin

OpenClaw was founded by **Peter Steinberger** and started in late 2025 as a side project called *Clawdbot*. According to dextralabs.com, within months — and after a rebrand through *Moltbot* to *OpenClaw* — it became one of the fastest-growing open-source repositories in GitHub history. Article reporting puts star counts between 143K and 367K within roughly eight weeks of viral attention ^[article:8a5a502c8b]^[article:c8cc5b1fb7].

The OpenClaw boom triggered a "百虾大战" (hundred-lobster war) in early 2026, with virtually every major Chinese tech company shipping a Claw variant: Tencent's **QClaw / WorkBuddy**, ByteDance's **ArkClaw**, Alibaba's **CoPaw / JVSClaw**, Xiaomi's **MiClaw**, Huawei's **小艺Claw**, Baidu's **DuClaw**, MiniMax's **MaxClaw**, Moonshot's **Kimi Claw**, Zhipu's **AutoClaw**, and more ^[article:c8cc5b1fb7]^[article:54a36baa97].

In the AI Product Ranking for February 2026, OpenClaw ranked **#1 globally** in the Claw Agent category with **27 million web visits** and a **925.04% traffic increase** ^[article:781c9ac2c3].

![Top 10 Claw Agent product ranking, February 2026](/static/img/781c9ac2c3/24.jpg)

A major naming/infrastructure milestone came with **OpenClaw 2.6**, which migrated the documentation index from `docs.clawd.bot` to `docs.openclaw.ai` ^[article:c8cc5b1fb7].

## Key Concepts / Components

- **Gateway** — WebSocket-based control plane connecting 15+ messaging platforms to the central Pi Agent Runtime ^[article:c8cc5b1fb7].
- **Agent Runtime** — Executes the AI loop, assembles context, invokes models, and runs tools.
- **Skills** — On-demand capability modules (e.g. `data-analysis`, `remotion-video-generator`, `xlsx`) discoverable via the `awesome-openclaw-skills` repo ^[article:8a5a502c8b].
- **Sub-Agents & Session System** — Sub-sessions host delegated agents with isolated context, role/permission scoping, and event-based result return ^[article:c8cc5b1fb7].
- **Three-Layer Hybrid Memory** — Raw / knowledge / semantic layers stored as Markdown for inspectability ^[article:c8cc5b1fb7].
- **Heartbeat / Cron** — Proactive scheduler that runs tasks 7×24 without human prompting ^[article:c8cc5b1fb7].
- **Canvas UI** — Real-time A2UI surface where the agent emits HTML and receives interactive events.
- **Ten Personalities** — Selectable agent personas including an "evil" mode used in workplace humor scenarios ^[article:54a36baa97].

### Pain Points & Successors

OpenClaw's reliance on Node.js and CLI-driven onboarding raises the bar for non-technical users — community charts label it explicitly as **高门槛** (high threshold) ^[article:c8cc5b1fb7]. Heavy token consumption is widely reported: one user @kevinzhow burned ~150 million tokens in a single day, then 400 million tokens overall, attributing much of it to OpenClaw's bugs ^[article:8a5a502c8b].

Two successor frameworks have emerged to address these gaps:

- **EdgeClaw** — Open-source secure cloud-edge collaborative agent framework with **Action Guard** and **Memory Guard**, addressing privacy and token-waste issues. It loads as an OpenClaw plugin ^[article:c8cc5b1fb7].
- **ZeroClaw** — A 100% Rust rewrite focused on minimal binary size (~3.4MB), <10ms startup, and 22+ pluggable provider traits, released MIT and announced as a farewell-and-replacement for OpenClaw ^[article:e781713458].

![ZeroClaw architecture](/static/img/e781713458/13.jpg)

### Model Compatibility

OpenClaw is model-agnostic. While Claude Sonnet 4.5 remains a top-of-leaderboard performer, the **PinchBench** verified runs show `google/gemini-3-flash` (95.1%), `minimax/minimax-m2.1` (93.6%), `moonshotai/kimi-k2.5` (93.4%), and `anthropic/claude-sonnet-4.5` (92.7%) leading on success rate ^[article:781c9ac2c3]. Zhipu's **GLM-5-Turbo** is marketed as the *first lobster-specific model*, claiming superior tool-call stability and long-instruction decomposition versus M2.5/K2.5 ^[article:54a36baa97].

![PinchBench success rates by model](/static/img/781c9ac2c3/25.jpg)

The reinforcement-learning framework **Claw-R1**, from USTC's Cognitive Intelligence National Key Laboratory, performs RL training directly on Agent Runtimes like OpenClaw, bridging simplified training environments with real agent systems ^[article:c8cc5b1fb7].

## Notable Use Cases / Examples

1. **Workplace "evil personality" assistant** — Reading and triaging messages from people the user is avoiding, summarizing group @mentions, and escalating Feishu messages via the platform's *加急* feature ^[article:54a36baa97].
2. **Scheduled news digests** — Daily 8 AM AI-news roundups pulling from X, Reddit, and HuggingFace model cards (e.g. monitoring DeepSeek V4 release) ^[article:781c9ac2c3]^[article:54a36baa97].
3. **Public-account research → Excel → video pipeline** — Tencent's WorkBuddy Claw with `data-analysis` skill harvests WeChat public-account articles into a formatted XLSX, then `remotion-video-generator` turns articles into short-form MP4 videos ^[article:8a5a502c8b].
4. **OpenClaw Visualization System** — A user-built Vue 3 + Canvas + Node.js virtual-office UI orchestrated through GLM-5-Turbo and OpenClaw ^[article:c8cc5b1fb7].
5. **Enterprise messaging integrations** — Tencent Cloud → QQ, Alibaba Cloud → DingTalk, Volcano Engine → Feishu, with cloud servers as low as ¥9.9–20/month ^[article:8a5a502c8b].
6. **Higher-education deployment** — As described by ibl.ai, hardened OpenClaw deployments for universities add FERPA-compliant audit logging, role-based access tied to identity providers, and SIEM integration.
7. **Book / curriculum** — *《OpenClaw 极简入门与应用》* presents a 3-step deployment method, a 4-step personality configuration method, dual-layer memory, heartbeat mechanism, and 36 case studies covering personal efficiency, content creation, student exam prep, workplace skills, zero-basis IT development, and one-person AI startups ^[article:f39e186f16].
8. **Beginner site** — `hermes101.dev`-style **OpenClaw 入门站** offers a 7-day tutorial plus 70+ curated resources ^[article:8a6f3af80a].

## Cross-references

- [[zeroclaw]]
- [[edgeclaw]]
- [[hermes-agent]]
- [[claude-code]]
- [[harness-engineering]]
- [[claw-r1]]
- [[workbuddy-claw]]
- [[moltbook]]
- [[glm-5-turbo]]
- [[minimax-m2]]
- [[kimi-k2-5]]
- [[peter-steinberger]]
- [[multi-agent-architecture]]
- [[task-execution-loop]]
- [[three-layer-hybrid-memory-system]]

## Further Reading

- [OpenClaw AI Agent Framework: What It Is, How It Works & How to Set It Up](https://dextralabs.com/blog/openclaw-ai-agent-frameworks/) — Origin story (Clawdbot → OpenClaw) and overview of multi-agent routing and persistent memory.
- [OpenClaw: The Reliable AI Agent Orchestrator](https://fedresources.com/openclaw-the-reliable-ai-agent-orchestrator/) — Framing OpenClaw as the "central nervous system" around LLM brains, with home-automation use cases.
- [What Is OpenClaw? Complete Guide to the Open-Source AI Agent](https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md) — Deep dive on the agent loop, control plane on `:18789`, and the Moltbook agent-only social platform.
- [OpenClaw Architecture, Explained](https://ppaolo.substack.com/p/openclaw-system-architecture-overview) — Hub-and-spoke architecture, A2UI Canvas, and separation of interface vs runtime layers.
- [OpenClaw AI Agent Framework for Organizations](https://ibl.ai/service/openclaw) — Enterprise hardening, FERPA compliance, and higher-education deployment patterns from ibl.ai.
- [openclaw/openclaw on GitHub](https://github.com/openclaw/openclaw) — Official repo: install instructions, agent workspace layout, and stable/beta/dev release channels.
- [How OpenClaw Works: Understanding AI Agents Through a Real Architecture](https://bibek-poudel.medium.com/how-openclaw-works-understanding-ai-agents-through-a-real-architecture-5d59cc7a4764) — Practical breakdown of `~/.openclaw/workspace` files, ReAct loop, and skills.
- [OpenClaw Security: Architecture and Hardening Guide](https://nebius.com/blog/posts/openclaw-security) — Gateway trust boundaries, sandboxing untrusted skills, and self-hosted vs managed comparison.