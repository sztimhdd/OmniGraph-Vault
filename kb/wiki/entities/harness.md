---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
- article:8a5a502c8b
title: Harness
---

# Harness

## Definition / Overview

In the context of AI agent engineering, a **Harness** is the complete infrastructure surrounding a large language model (LLM) — every piece of code, configuration, tool, rule, and execution logic that is *not* the model itself. The compact formulation popularized by LangChain is **Agent = Model + Harness**: the model supplies intelligence, while the harness turns that intelligence into reliable, repeatable work in real environments.

The term draws its metaphor from horse tack — if the AI model is the horse, the harness comprises the reins, route plan, and guardrails the rider uses to direct it. Practically, a harness is the work environment and workflow built around the model: project rules, tools, task decomposition, testing, permission systems, error recovery, observability, and sandboxing^[article:5a362bf61e].

A Harness is distinguished from related concepts:
- It goes **beyond Prompt Engineering** (2022–2024, "make the model understand you") and **Context Engineering** (2025, "feed the right info at the right time"), evolving into the third stage focused on **stable task completion** in production^[article:5a362bf61e].
- It is **not** the model itself, nor a fine-tuning recipe — it is the engineering stability layer that converts language-based judgments into dependable real-world actions.

![Harness as work environment around the model](/static/img/3df8419440/0.jpg)

## Architecture / Design

A modern Harness is a multi-layered system. Drawing from reverse-engineered analyses of Claude Code as the canonical reference implementation^[article:5a362bf61e], a production-grade harness typically contains:

1. **LLM core** — the reasoning engine.
2. **Tool system** — standardized interfaces (file I/O, shell, web, MCP servers) that let the agent act in the world.
3. **Agent Loop / Runtime** — the orchestration core handling task advancement, tool dispatch, state saving, error handling, permission control, and context management.
4. **Context Architecture** — `CLAUDE.md` / `AGENTS.md` style layered documents, on-demand loading, dynamic context (cwd, OS, git state, date), and a 4-level compression pipeline with full-transcript backup before autocompact.
5. **Permission Model** — declarative allow/deny/ask rules, permission modes, and the **YOLO Classifier** (a two-stage AI classifier serving as the fourth layer of defense in depth).
6. **Hooks System** — programmable lifecycle callbacks (PreToolUse, PostToolUse, SessionStart, etc.) for custom logic injection.
7. **Sandbox** — the last line of defense: isolated execution environments with network and filesystem restrictions.
8. **Memory System** — cross-session structured storage, often filesystem-backed, with skill extraction and session memories.
9. **Architecture Guardrails** — pre-commit hooks, dependency linters, git checkpoints for safe rollback.
10. **Sub-Agent / Multi-Agent Orchestration** — context isolation via fork, parallel worktree isolation, Plan→Work→Review loops.

![Claude Code harness architecture](/static/img/3df8419440/12.jpg)

The **Harness Design Philosophy** is often summarized as *"hard tracking, soft execution"* — enforce critical checkpoints rigidly while leaving execution paths flexible. Closely related is the **Harness Principle**: design the system so components can be independently disabled as model capabilities improve, rather than baking dependencies in permanently^[article:5a362bf61e].

The Microsoft Agent Framework team frames the same idea as connecting "model reasoning to real execution: shell and filesystem access, approval flows, and context management across long-running sessions," surfacing shell harnesses, filesystem harnesses, and approval flows as first-class building blocks (see Microsoft devblogs in Further Reading).

![Harness layers](/static/img/3df8419440/26.jpg)

## History / Origin

Harness is not a 2026 invention — it is the latest crystallization of a decade-long practice^[article:5a362bf61e]:

- **2022–2024 — Prompt Engineering.** Role assignment, output formatting, few-shot examples, chain-of-thought.
- **2025 — Context Engineering.** RAG, AGENTS.md, memory, context compression — putting the *right* information in front of the model at the *right* time.
- **2026 — Harness Engineering.** Adds tools, task decomposition, self-correction, guardrails, and observability so agents can complete entire tasks reliably^[article:5a362bf61e].

The term gained traction in early 2026 through several converging events:
- Anthropic published *"Harness Design for Long-Running Application Development"* on its engineering blog (March 24, 2026), naming Claude Code itself as an exemplary harness.
- Martin Fowler defined Harness Engineering as a **trust-building model** for coding agents, organized around context, constraints, feedback loops, and engineering structure.
- A LangChain experiment kept the model fixed and optimized only the harness, lifting Terminal Bench 2.0 scores from 52.8% to 66.5% — jumping from outside the top 30 into the top 5^[article:5a362bf61e].
- An OpenAI team of three reportedly used a well-tuned harness to guide AI generation of over a million lines of code, resulting in an internally deployed product^[article:5a362bf61e].
- Boris (Anthropic) publicly argued that the harness layer will *shrink* as models improve, but is essential today for transforming raw capability into dependable products.

The Parallel.ai writeup traces the emergence of harnesses to practical gaps the bare LLM could not fill: long-running tasks across sessions, tool/API orchestration, persistent memory, and safe interaction with complex environments.

## Key Concepts / Components

**Prompt → Context → Harness.** A unified framework: the prompt expresses intent, the context grounds it, and the harness executes it reliably^[article:5a362bf61e].

**Three pillars of Harness Engineering:**
- **Context Architecture** — layered docs, on-demand loading, memory and compression.
- **Execution Capability** — tool calling, code execution, multi-agent collaboration.
- **Feedback Mechanisms & Guardrails** — linters, automated tests, browser-use validation, agent mutual review, architecture constraints linter, pre-commit hooks.

**Defense in Depth (six layers).** Permission rules → permission modes → hooks → YOLO Classifier → sandbox → enterprise MDM policy.

**Harness Maturity Levels^[article:5a362bf61e]:**

| Level | Scope | Effort | Contents |
|---|---|---|---|
| **Level 1** | Individual | 1–2 hours | CLAUDE.md + pre-commit hooks + test suite |
| **Level 2** | Small team | 1–2 days | AGENTS.md, CI constraints, shared MCP servers, team Skills |
| **Level 3** | Organization | 1–2 weeks | Custom middleware, observability, scheduling agents, MDM-locked policy |

**Harness-as-Policy** — a mode where deterministic code (not the LLM) makes the policy decision, used for high-stakes guardrails such as blocking `sudo`, `rm -rf`, force pushes, or writes to `.env` / SSH keys.

![Harness module 5: architecture guardrails](/static/img/3df8419440/22.jpg)

**Quantitative impact^[article:5a362bf61e]:**
- LangChain case: +14% on Terminal Bench 2.0 from harness optimization alone.
- OpenAI case: ~10× development cycle compression on a million-line codebase.
- ROI vs. fine-tuning: a 30-minute CLAUDE.md edit can yield 20–40% project-specific gains, versus weeks of training compute for fine-tuning.

## Notable Use Cases / Examples

**Claude Code (Anthropic).** The most-cited reference implementation — ~1,884 TypeScript files, ~512K LOC, 43+ tools, 100+ slash commands, MCP integration, OAuth/JWT/keychain auth, OpenTelemetry. Its async-generator streaming architecture (`async function* query() → AsyncGenerator<StreamEvent>`) lets users see and interrupt model thinking in real time^[article:5a362bf61e].

**OpenClaw / Hermes.** Independent agent products that focus on implementing the Harness concept — task decomposition, gateway/memory/skills/multi-agent runtime layering — and provide alternative interpretations of the harness pattern^[article:5a362bf61e].

**claude-code-harness (GitHub, 21.4k stars).** An open-source project that wraps Claude Code in a workflow engine with 13 hardcoded guard rules (R01–R13: block sudo, deny writes to `.git`/`.env`/SSH keys, require confirmation outside project root, forbid `git push --force`, etc.) — implemented as PreToolUse hooks^[article:5a362bf61e].

**Microsoft Agent Framework (MAF).** Ships explicit "Agent Harness" primitives for shell tool, filesystem, and approval flows in both .NET and Python.

**Compiler-style knowledge layer (Nexus).** The Nexus project frames a different angle on the same problem — providing a compiler-AI knowledge layer that sits between models and codebases, complementary to harness-style runtime control^[article:8a5a502c8b].

**Practical project templates** built end-to-end on Harness Engineering include the *万能视频下载总结器*, *AI热点监控工具*, *GitHub文档翻译器*, and *AI闯关学习小程序* — each following the full requirement-analysis → testing pipeline.

## Cross-references

- [[claude-code]]
- [[harness-engineering]]
- [[context-engineering]]
- [[prompt-engineering]]
- [[agent-loop]]
- [[openclaw]]
- [[hermes-agent]]
- [[mcp]]
- [[yolo-classifier]]
- [[architecture-guardrails]]
- [[claude-md]]
- [[agents-md]]
- [[sub-agent]]
- [[permission-model]]
- [[sandbox]]
- [[langchain]]
- [[anthropic]]
- [[nexus]]

## Further Reading

- [The Anatomy of an Agent Harness — LangChain](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness) — Vivek Trivedy's canonical post deriving "Agent = Model + Harness" and enumerating the components today's agents need.
- [What is an agent harness? — Parallel.ai](https://parallel.ai/articles/what-is-an-agent-harness) — Clear taxonomy distinguishing harness from framework and orchestrator, with real-world examples.
- [Agent Harness in Agent Framework — Microsoft DevBlogs](https://devblogs.microsoft.com/agent-framework/agent-harness-in-agent-framework/) — Concrete shell, filesystem, and approval-flow harness patterns in Python and .NET.
- [Building Effective AI Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents) — Anthropic's guidance on when to use workflows vs. agents, and the role of harness-like scaffolding.
- [microsoft/agent-framework — GitHub](https://github.com/microsoft/agent-framework) — Open-source multi-language framework that exposes harness primitives as first-class APIs.
- [AI Agent Frameworks: Choosing the Right Foundation — IBM](https://www.ibm.com/think/insights/top-ai-agent-frameworks) — Background on agentic frameworks, communication protocols, and orchestration patterns.
- [AI Agent Frameworks: A Practical Guide (2026) — Salesforce](https://www.salesforce.com/agentforce/ai-agents/ai-agent-frameworks/) — Industry-oriented overview of selection criteria for production agent stacks.
- [今年爆火的 Harness Engineering 是什么？一文彻底讲明白 — 程序员鱼皮](http://mp.weixin.qq.com/s?__biz=MzI1NDczNTAwMA==&mid=2247586245&idx=2&sn=8b6fd6d4ff0552dc38113aecb7d74e76) — Accessible Chinese walkthrough of Harness Engineering with worked examples.
- [Harness 到底是什么？看看 OpenClaw、Hermes、Claude Code 的演绎 — 叶小钗](http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767&idx=1&sn=b3d620a57e8833c4928da40f67fdecd1) — Comparative reading of three real harness implementations.