---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
- article:8a5a502c8b
- article:1272b434a5
- article:28c974c2cd
- article:54a36baa97
- article:1b90511349
- article:c8cc5b1fb7
- article:f5f44ab394
- article:9b427c8cb5
- article:26b555ac6b
- article:f39e186f16
- article:1908ad7a33
- article:99a2043522
- article:2c929671e6
- article:9cbd555c68
title: Agent
---

# Agent

## Definition / Overview

An **Agent** is an autonomous artificial intelligence entity, typically powered by a large language model (LLM), that proactively interacts with an environment, receives feedback, and performs tasks in a goal-oriented manner. It represents the evolution of LLMs from passive question-answering systems into a unified control interface that understands human intent, plans, invokes tools, and stably completes long-chain tasks ^[article:5a362bf61e]^[article:1908ad7a33].

A widely adopted operational definition frames the agent as a composition:

> **Agent = Model + Harness**

Where the *Model* (an LLM) provides reasoning, intent understanding, and decision-making, while the *Harness* provides the engineering scaffolding — context management, tool invocation, runtime control, error recovery, and permission boundaries — that converts probabilistic language outputs into stable real-world actions ^[article:5a362bf61e]^[article:1908ad7a33]. Without the harness, an agent is just a chat shell; with it, the agent becomes a goal-oriented closed-loop engineering cycle of *planning → tool invocation → observation → path adjustment → continuation* ^[article:99a2043522].

According to Arize AI's framework guide, an agent framework "acts as the control layer around the model. It establishes the order of operations, determines when to invoke a tool, manages state changes, and directs each step according to clear rules" — closely paralleling the model+harness formulation popularized in the Chinese agent-engineering community.

## Architecture / Design

A production-grade agent is built from a small set of recurring architectural components ^[article:5a362bf61e]^[article:f39e186f16]:

1. **Model (LLM core)** — the reasoning brain that generates thoughts, tool calls, and responses.
2. **Reasoning Loop (ReAct)** — a *Think → Act → Observe → Repeat* cycle that allows the agent to course-correct based on intermediate results rather than answering in a single shot ^[article:f39e186f16].
3. **Tool Layer** — functions the agent invokes to read files, run code, search the web, or call APIs. Tool documentation must be written *for agents, not humans* — clearly stating when to use, when not to use, parameter constraints, and failure-recovery guidance ^[article:5a362bf61e].
4. **Memory System** — short-term (the `messages` list maintaining the current session) and long-term (`MEMORY.md`, `USER.md`, vector stores, or external memory providers) ^[article:26b555ac6b]^[article:5a362bf61e].
5. **Context Engineering Layer** — selects, compresses, and routes the right slice of information into each turn so the model is neither under-informed nor drowned in noise ^[article:5a362bf61e].
6. **Skills / Workflows** — reusable, human-authored procedural knowledge the agent loads on demand to perform stable, repeatable operations ^[article:c8cc5b1fb7]^[article:2c929671e6].
7. **Runtime / Orchestration** — iteration budgets, cascade interruption, error classification, sandboxing, and permission checks that keep the agent from burning tokens in infinite loops or executing destructive actions ^[article:5a362bf61e].
8. **Guardrails** — pre-execution validation (permissions, sensitivity, sanity checks) ^[article:f39e186f16].

![Agent harness layered architecture](/static/img/25ccf5edd8/13.jpg)

This layered view — *Role & Rules → Memory → Context Loading → Stable Execution → Runtime* — is what frameworks like OpenClaw and Hermes operationalize ^[article:5a362bf61e]^[article:c8cc5b1fb7].

![Evolution of context retrieval for AI agents](/static/img/4c22075e13/0.jpg)

Beyond the single-agent shape, **Multi-Agent Architectures** introduce orchestrator/worker patterns, generate-review loops, expert routing, and aggregator/mixture-of-agents designs. IBM's overview of agent frameworks notes that frameworks like LlamaIndex, AutoGen, CrewAI, LangGraph, and Semantic Kernel each pick different tradeoffs around step granularity, event-driven communication, and shared state. The Galileo report adds that production agents need a Build / Orchestration / Governance separation so policies (e.g., prompt-injection defense) can be updated fleet-wide rather than hardcoded into each agent.

## History / Origin

The agent concept progresses through three rough stages ^[article:1908ad7a33]^[article:99a2043522]:

- **Answering** — early LLM chatbots: stateless Q&A.
- **Doing** — LLMs gain tool use (Function Calling, MCP) and become *AI Agents* capable of executing actions on the user's behalf.
- **Stable Completion** — engineering disciplines like *Harness Engineering* emerge to make agents reliably finish complex, multi-step tasks instead of stopping early or looping ^[article:1908ad7a33].

Key milestones in the corpus:

- **ReAct** became the canonical reasoning paradigm for tool-using agents ^[article:f39e186f16].
- **Claude Code** (Anthropic) crystallized the model+harness pattern for coding agents, influencing the broader Agentic Engineering wave ^[article:5a362bf61e]^[article:f5f44ab394].
- **OpenClaw** popularized agent frameworks where workspace files (`AGENTS.md`, `SOUL.md`, `USER.md`, `MEMORY.md`) externalize identity, values, user preferences, and learned experience ^[article:28c974c2cd]^[article:c8cc5b1fb7]^[article:f39e186f16].
- **Hermes** (Nous Research) extended this with self-evolving skills, swappable execution backends, session memory persistence, and a 21.4k-star open-source release ^[article:1908ad7a33].
- **Self-improving agents** — Fudan × Peking University demonstrated an agent that rewrites its own harness and outperforms Codex over 10 rounds ^[article:1908ad7a33].

According to Karpathy's late-2025 talk (referenced in the LightRAG corpus), the *Agent-native world* — where every person and organization has agent representatives that talk to each other — is the next horizon, with humans retaining responsibility for taste, judgment, and goal-setting.

![Karpathy on the Agent-native world](/static/img/4683000fcf/12.jpg)

## Key Concepts / Components

### The Reasoning Loop
An agent does not answer in one shot. It thinks, acts, observes, re-evaluates, and repeats — recovering from 404s, retries, and dead ends along the way ^[article:f39e186f16].

### Tool Calling and MCP
The **Model Context Protocol (MCP)** acts as a universal plugin system: tools self-describe, agents discover them at runtime, and one protocol replaces N bespoke integrations ^[article:f39e186f16]. This makes the agent's capabilities extensible without redeployment.

### Memory: Short-term, Long-term, Experience
- *Short-term memory* is the session message list ^[article:f39e186f16].
- *Long-term memory* persists across sessions, often via RAG or files like `MEMORY.md` ^[article:26b555ac6b]^[article:5a362bf61e].
- *Experience memory* lets the agent learn from past trajectories — Hermes uses a "mini Agent" to review conversations after tasks and extract reusable skills ^[article:1908ad7a33].
- **Privacy** is non-trivial: systems like *MemPrivacy* attempt to balance personalization with security ^[article:1b90511349].

### Skills and SkillGraphs
Skills externalize human workflows so agents can execute them stably and reusably ^[article:c8cc5b1fb7]^[article:f39e186f16]. The **SkillGraph** approach extends this with graph-based skill retrieval and evolution: the agent executes skills, generates trajectories, learns from failures, and the graph evolves via topological sorting of skill dependencies ^[article:2c929671e6].

### Guardrails, Sandbox, Permissions
Before destructive actions, the harness validates permissions, parameter sanity, and output safety. Sandboxes restrict reachable actions even when other controls are bypassed ^[article:5a362bf61e]^[article:f39e186f16].

### Context Engineering and Context Rot
Long contexts are not free: attention dilutes, and agents suffer **Context Rot** — performance degradation as task history accumulates, leading to omissions, repetitive behaviors, and hallucinations ^[article:5a362bf61e]. Context engineering — selecting, compressing, and routing only the relevant slice — is therefore arguably the hardest layer of agent engineering.

### Knowledge Compilation (Nexus)
Current agents struggle with raw retrieval. The **Nexus** approach treats the LLM as a *compiler* that produces structured, governable knowledge artifacts agents query directly, instead of doing similarity search over raw corpora ^[article:8a5a502c8b]^[article:1272b434a5]^[article:9b427c8cb5].

### Multi-Agent Patterns
Common patterns include Dispatch–Execution, Hierarchical Orchestration, Expert Routing, Generate–Review, and Ensemble/Mixture-of-Agents ^[article:5a362bf61e]. According to Moxo's framework guide, CrewAI was designed natively for multi-agent coordination, while LangChain's chain-first roots make multi-agent support feel bolted-on.

![Multi-agent decision tool selection guide](/static/img/6b8c197d6a/8.jpg)

## Notable Use Cases / Examples

- **Coding Agents** — Claude Code, Codex, Cursor, and Hermes act as autonomous programming assistants that read code, run tests, and iteratively fix bugs under sandbox+permission constraints ^[article:5a362bf61e]^[article:f5f44ab394]^[article:1908ad7a33].
- **OpenClaw Teams** — 11+ agents holding "group meetings," reviewing transcripts, writing diaries, and self-improving overnight ^[article:28c974c2cd]^[article:54a36baa97]^[article:c8cc5b1fb7].
- **Hermes Agent** — open-source self-evolving agent that grows skills from experience, with a five-layer architecture (Entry / Gateway / Execution / Extension / Storage) ^[article:1908ad7a33].
- **Concurrent Agent Fleets** — Boris-style setups where one user runs hundreds of concurrent agent sessions ^[article:5a362bf61e].
- **Goal-driven Self-loops** — the `/goal` paradigm where the agent receives a defined objective and enters a self-loop until completion ^[article:99a2043522].
- **Enterprise Digitalization** — the predicted future of *systems CLI-ified, processes Skill-ified, employees Agent-ified*, where each employee's Agent inherits their authorization and executes Skills on their behalf ^[article:9cbd555c68].
- **AI Knowledge Layer** — agents consume compiled knowledge from Nexus to generate sales briefs, customer insights, and structured query answers ^[article:8a5a502c8b]^[article:1272b434a5].
- **Long-term Memory with Privacy** — agents using *MemPrivacy*-style systems to remember user preferences without leaking personally identifying information ^[article:1b90511349].

## Cross-references

- [[harness-engineering]]
- [[claude-code]]
- [[openclaw]]
- [[hermes-agent]]
- [[mcp-model-context-protocol]]
- [[react-framework]]
- [[skill]]
- [[skillgraph]]
- [[nexus]]
- [[graphrag]]
- [[context-engineering]]
- [[memory-system]]
- [[multi-agent-system]]
- [[langgraph]]
- [[langchain]]
- [[deep-agents]]
- [[agentic-ai]]
- [[mempr ivacy]]
- [[goal-paradigm]]
- [[ontology-driven-agent]]

## Further Reading

- [Agent Frameworks — Arize AI](https://arize.com/ai-agents/agent-frameworks/) — Operational view of agent frameworks as a control layer over the model, with discussion of observability and tracing.
- [AI Agent Frameworks: Choosing the Right Foundation — IBM](https://www.ibm.com/think/insights/top-ai-agent-frameworks) — Survey of LlamaIndex, Semantic Kernel, AutoGen, and others, including workflow primitives (steps, events, context).
- [AI agent development frameworks — Dust](https://dust.tt/blog/ai-agent-development-frameworks) — Comparison of LangGraph, CrewAI, AutoGen, LangChain, and Semantic Kernel for different team contexts.
- [Best 5 Frameworks To Build Multi-Agent AI Applications — getstream.io](https://getstream.io/blog/multiagent-ai-frameworks/) — Practical comparison of Agno, OpenAI Swarm, LangGraph, AutoGen, CrewAI, and Langflow.
- [AI Agent Architecture: From Patterns to Governance — Galileo](https://galileo.ai/blog/ai-agent-architecture) — Argues for a Build / Orchestration / Governance three-plane architecture so policies can be updated fleet-wide.
- [AI Agent Architecture: Tutorial & Examples — FME by Safe Software](https://fme.safe.com/guides/ai-agent-architecture/) — Code-based vs. low-code agent platforms, with a LangGraph implementation walk-through.
- [Complete guide to agentic AI frameworks — Moxo](https://www.moxo.com/blog/agentic-ai-framework-comparison) — Latency and orchestration tradeoffs across LangGraph, CrewAI, LangChain, AutoGen, and Swarm.
- [AI Agent Frameworks: A Practical Guide (2026) — Salesforce](https://www.salesforce.com/agentforce/ai-agents/ai-agent-frameworks/) — Enterprise-oriented rundown emphasizing tool use, memory, and responsible-AI considerations.
- [10个构建生产级Agent的核心概念 — DeepHub IMBA](http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247515984&idx=1&sn=73927687976cf646db1729d527f1e13e&chksm=feb4f1f1c9c378e73c8c29c183e6fd8d311de0d2cfef6cc4ada6bad972764c75f7ea1a88d2a9#rd) — Walks through MCP, reasoning loops, memory, guardrails, and tool discovery as the ten foundational concepts for production agents.
- [200 行 Python 代码，从零手搓极简 Agent](http://mp.weixin.qq.com/s?__biz=MzI2OTg0MjI2Nw==&mid=2247486336&idx=1&sn=7cab71e54e81daa1179df5d65323bb5a&chksm=eadb69b4ddace0a2d54abf8b871e84b4e33df84d4fdab518f155f539e6932b79d488926a2a12#rd) — Shows that an agent is fundamentally an LLM + a `messages` list + tool functions + a loop.
- [Ontology本体驱动Agent技术起底](http://mp.weixin.qq.com/s?__biz=MzAxMjc3MjkyMg==&mid=2648430440&idx=1&sn=256c2b8b6b0871416dae0588ba3b9c16&chksm=8383c43db4f44d2be18342bf379cf1f53da10bec1a8f55fcbac0da230945025459fe91349cd0#rd) — Decomposes ontology-driven agents into GraphRAG (facts) + rule engine (constraints) + workflow (deterministic execution).