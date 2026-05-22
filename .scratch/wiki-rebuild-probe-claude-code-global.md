# Claude Code: A Comprehensive Wiki

## Overview

**Claude Code** is a production‑grade AI‑powered coding assistant and terminal‑based agent harness developed by **Anthropic** and created by **Boris Cherny**. It operates as a CLI tool that accepts natural language instructions, supports cross‑platform use, real‑time encrypted voice communication, and can be accessed via the Happy client on mobile and web. It integrates with IDEs like IntelliJ IDEA through the ACP protocol, and its visual representation is a light blue node with a robot icon connected to an ACP hub. ^[article:ccreveng02]

Originally an incubator project, Claude Code surpassed **$1 billion in annual revenue** in early 2026 and later reached a **$2.5 billion annual run rate**, achieving a **99.68% uptime** service status. Development has been rapid, with over **45 new features** launched in Q1 2026 alone. ^[article:harness-wechat]

## Architecture

### Technical Stack & Scale

Claude Code is written in **TypeScript** and **React** (using Ink for terminal rendering), totalling approximately **512,664 lines of code** across ~1,884 TSX files. It exposes **43+ tools** and over **100 slash commands**. The runtime is **Bun**, with Commander.js for CLI parsing, Zod v4 for schema validation, and ripgrep (via BashTool) for search. ^[article:ccreveng02]

The system is composed of five agent types that use sub‑agents to pre‑package context and tools, a seven‑level hierarchical permission system with an AI classifier, and a four‑level compaction pipeline managing a **200K‑token context window**. ^[article:ccreveng02] The core agent loop (ReAct pattern) lives in `src/query.ts` (68 KB) and is a `while(true)` loop processing messages → LLM → tool calls. The entry point is `src/main.tsx` (803 KB).

![Architecture overview of Claude Code's six-layer harness infrastructure](http://localhost:8765/5a362bf61e/0.jpg)

### Agent Loop & Tool System

The **Agent Loop** is the heart of Claude Code – a ReAct (Reasoning + Acting) pattern where the model iteratively thinks, selects tools, executes, and observes results. The three most frequently called tools – **AgentTool**, **BashTool**, and **FileWriteTool** – account for **80% of all tool calls**. Claude Code emphasizes the ReAct pattern for agent loop and task management. ^[article:harness-wechat]

### Sub‑Agent System & Multi‑Agent Orchestration

Claude Code contains a **Sub‑Agent System** for multi‑agent orchestration, supporting **five agent types** and Swarm orchestration. The **Fork Sub‑Agent** technique copies the parent's assistant messages and replaces tool results with placeholder text to maximize prompt cache hit rate. ^[article:ccreveng02]

### Compaction & Context Engineering

With a 200K token context window, Claude Code employs a **four‑level compaction pipeline** to manage context. The system sends previous context during each dialogue for cache hits, achieving a **95.2% cache hit rate**. Loading and prefetch are lazy and parallel. ^[article:ccreveng02]

### Permission & Security Model

Security is implemented through **six layers of defense**: sandboxing (file, network, process isolation), tool call filtering, AI classifiers (including a two‑stage YOLO classifier for automatic approval), compile‑time feature gating, user permission prompts, and hard‑coded denial (not configurable, not bypassable). There are five permission modes (allow/deny/ask) and a seven‑level hierarchical system. ^[article:ccreveng02]

## Key Features

### Project Grounding with CLAUDE.md

When working on a project, Claude Code automatically reads `.claude/CLAUDE.md` for agent grounding. This file defines project‑specific rules and conventions. A project’s CLAUDE.md is the primary way to inject persistent context and guide the agent’s behaviour. ^[article:harness-wechat]

### Memory & Logging

Persistent memory is **file‑based** – conversational logs are stored locally in JSONL files, analyzable by the **CC Log Workbench** or other tools. The built‑in memory can remember project iterations across sessions, though some users report issues with context retention. ^[article:harness-wechat]

### Plan Mode & Work Review Cycle

Claude Code includes a **Plan Mode** built on an asynchronous generator stream architecture, with a five‑stage planning workflow (Plan Work Review Cycle). Plan Mode is implemented as a tool‑restricted sub‑agent (EnterPlanModeTool) rather than a state machine, avoiding common deadlock problems. ^[article:ccreveng02]

### Model Integration

Claude Code integrates multiple model providers including **Sonnet 4.6**, **Opus 4.7**, and **DeepSeek‑V4‑Pro**. It runs as an AI agent in executor or project manager modes, executing coding tasks in isolated worktrees. Claude Opus 4.7 is used by Coding Agents for high‑quality code generation. ^[article:ccreveng02]

### Plugin Manager & Skills

The tool features a plugin manager with commands such as `/goal`. It also supports the **Agent Skills standard** and integrates with **SkillClaw** – a skill‑sharing system that allows Claude Code to share and evolve skills with Hermes for cross‑platform reuse. Skills can be defined in SKILL.md files. ^[article:skillclaw-wechat]

### Hooks System

A native **Hook system** supports **26 events** across four types, providing lifecycle hooks for customisation and extensibility. ^[article:ccreveng02]

### MCP Integration

Claude Code fully supports the **Model Context Protocol (MCP)**, allowing it to extend its capabilities by connecting to external MCP servers. The tool uses the MCP SDK as one of its core protocols. ^[article:ccreveng02]

## Agent Harness Engineering

### Defining Harness

**Harness Engineering** is the discipline of designing the environment, constraints, feedback loops, and infrastructure that make an AI agent reliable at scale. Martin Fowler (2026) defined Harness Engineering as a trust‑building model around coding agents, using context, constraints, feedback loops, and engineering structure. ^[article:harness-wechat] Anthropic itself describes **Claude Code as an excellent harness** and discusses long‑running agent harness design in its engineering blog. ^[article:harness-wechat]

The equation is often visualised as:

**Agent = Model + Harness**  
*Harness = Everything else (rules, tools, processes, checks, guardrails)*

![Visual diagram of Agent = Model + Harness](http://localhost:8765/d6d818a670/5.jpg)

### Claude Code as a Reference Harness

Claude Code provides the most complete production‑grade reference implementation of an agent harness, covering:

- **Role & Rules** – via CLAUDE.md, system prompts, agent types.
- **Memory System** – file‑based persistent memory, logs.
- **Context Loading** – lazy loading, parallel prefetch, four‑level compaction.
- **Stable Execution** – ReAct loop, 43+ tools, safety checks.
- **Permission Model** – five modes, seven levels, YOLO classifier.
- **Hooks** – 26 events for lifecycle customisation.
- **Sandbox & Security** – six layers of defense.
- **MCP Integration** – protocol‑based extension. ^[article:ccreveng02]

### Comparison with Other Harness Implementations

| Dimension | Claude Code | OpenClaw | Hermes |
|-----------|-------------|----------|--------|
| **Role & Rules** | Tool‑as‑process; roles pre‑built into system | Human‑written Skills, rigid boundaries | Flexible, lets agent decide skill generation |
| **Memory** | File‑based, emphasises handoff artifacts | Minimal / replaceable | Comprehensive: MEMORY.md + external providers + session search |
| **Context** | Compaction pipeline, 200K window, 95.2% cache hit | Skills loading as context filter | Session search + context engine plugin |
| **Stability** | Six‑layer defense, 43 tools | Security‑first runtime | Backend‑switchable execution |
| **Skills** | SkillClaw integration, SKILL.md files | Skill‑centric (human‑authored) | Self‑evolving skills (meta‑agent decides skill creation) |
| **Ecosystem** | MCP, plugins, Claude API | Agent‑centric, limited plug‑ins | Skill sharing, multi‑agent orchestration |

^[article:harness-wechat] ^[article:ccreveng02] ^[article:skillclaw-wechat]

## Integration with Other Systems

### SkillClaw & Skills Sharing

SkillClaw supports the Claude Code agent framework for skill sharing, enabling Claude Code to share and evolve skills similarly to Hermes. It can integrate with Claude Code’s default skills directory, and users can configure SkillClaw as a local proxy or evolve server. ^[article:skillclaw-wechat]

### Everything‑Claude‑Code Project

The **Everything‑Claude‑Code** project acts as a performance enhancement system for AI agent harnesses including Claude Code, Codex, Cursor, and OpenCode. It is designed to upgrade AI from chat assistant to a standardised engineering system with persistent memory, standardised workflows, automated checks, and continuous learning. The project contains over **30 agents** with specific roles in the development pipeline. ^[article:harness-wechat]

### Archon Harness Builder

**Archon** is the first open‑source harness builder for AI coding, making AI coding deterministic and repeatable. It provides workflow‑driven integrations and can be used with Claude Code via workflows like `archon-assist`, which provides general Q&A, debugging, code search, and a full Claude Code agent with all tools. ^[article:archon-trend]

![Archon project's GitHub repository with 21.4k stars](http://localhost:8765/1908ad7a33/2.jpg)

### Bridge System & IDE Integration

Claude Code integrates with IDEs via a **Bridge System** for bidirectional communication and session synchronisation. It supports the ACP protocol to run inside editors like IntelliJ IDEA. ^[article:ccreveng02]

## Use Cases & Community Feedback

Claude Code is used for code generation, testing, debugging, MVP development, code auditing, security scanning, compliance documentation, hardening codebases, building technical infrastructure, and integration interfaces. Notable users include **engineers at Apple**, **Andrej Karpathy**, **Allie K. Miller**, **Simon Willison**, **Justin Searls**, **Scott Werner**, and **Martin Alderson**. ^[article:ccreveng02]

It has been used to decompile and binary‑patch Windows DLLs for Wine compatibility, automate reverse engineering and sysadmin tasks, build a clone of Linear, generate report templates and scripts, act as a tax agent, convert Excel to Python models, and port source code to C#. ^[article:ccreveng02]

### Known Limitations & Criticism

Despite its strengths, Claude Code has faced criticism for no longer reliably following developer‑defined rules, a context management bug, system prompt optimisation challenges, occasional quality degradation, a source code leak, and unsubscriptions due to model downgrades and KYC requirements. The tool does not support selective disabling of MCP tools and lacks a steering panel. ^[article:ccreveng02] Some users report that Claude Code no longer obeys or respects CLAUDE.md, hooks, rules, and other defined guidelines after updates. ^[article:archon-trend]

## Comparison with Other Agent Frameworks

### Claude Code vs. OpenClaw

OpenClaw is a more **skill‑centric** system where Skills are human‑authored, rules are predefined, and the agent operates within a strict framework. Claude Code is more **tool‑driven**, where tools define workflows. OpenClaw has a “replaceable capability slot” for memory, while Claude Code uses file‑based memory with emphasis on handoff artifacts. ^[article:harness-wechat]

### Claude Code vs. Hermes

Hermes is more **flexible and self‑evolving** – it allows the agent to decide when to generate or update skills, and has a comprehensive memory system with external providers. Claude Code is more **rigid but reliable** – its six‑layer security and strict permission model make it suitable for production environments. ^[article:harness-wechat] Hermes’ session search and context engine plugin provide more dynamic context loading compared to Claude Code’s compaction pipeline.

### Claude Code vs. Codex / Cursor / OpenCode

**Codex** (by OpenAI) emphasises code generation with large context windows. **Cursor** provides editor‑native integration with 8 parallel agents and worktree isolation. **OpenCode** is an open‑source alternative with plugin architecture. Claude Code distinguishes itself with its **deep permission system**, **six‑layer defense**, **40+ tools**, and **SkillClaw integration**. All share common patterns: project‑level config files (CLAUDE.md / .cursorrules), ReAct tool calling, permission mechanisms, and MCP support. ^[article:ccreveng02]

## Major Design Decisions

### Why ReAct?

Claude Code chose the **ReAct (Reasoning + Acting)** pattern as its core agent loop because it provides a simple, interpretable framework for combining reasoning with tool execution. This design is validated by academic research showing that ReAct outperforms pure reasoning or acting alone for complex tasks. ^[article:harness-wechat]

### Context Window Management

The **200K‑token context window** is managed through a **four‑level compaction pipeline** that summarises and prunes older content. This, combined with **prompt caching** (95.2% hit rate), allows Claude Code to maintain long‑running sessions without context degradation. ^[article:ccreveng02]

### Security as a First‑Class Concern

With six layers of defense (sandbox, tool filtering, classifiers, feature gating, user prompts, hard‑coded denial), Claude Code is designed to safely execute dangerous commands like `rm` and `git push` in production. The **YOLO classifier** provides two‑stage AI permission approval for common operations. ^[article:ccreveng02] This design philosophy is summarised in the tutorial: “Constraint is power, not limitation.”

### Tool‑First Architecture

The **Tool system** is central – with **43+ standardised interfaces** for file operations, shell commands, web search, MCP, and sub‑agents. The three most used tools (AgentTool, BashTool, FileWriteTool) handle 80% of all calls, indicating that a small number of well‑designed tools can cover most agent needs. ^[article:ccreveng02]

### Terminal CLI over IDE Plugin

Anthropic chose a terminal‑based CLI to maximise performance, automation, and headless operation. The CLI allows seamless CI/CD integration, remote execution, and multi‑session parallelisation using Git worktrees. IDE integration is provided through a secondary protocol (ACP) rather than being the primary interface. ^[article:ccreveng02]

## Conclusion

Claude Code represents the current state‑of‑the‑art in production‑grade AI agent harness design. With over half a million lines of engineered TypeScript, a six‑layer security model, advanced context management, deep SkillClaw integration, and proven revenue scale, it serves as both a practical tool and a reference architecture. As agentic coding evolves, Claude Code’s design decisions – particularly around constraints, tools, and security – will continue to inform the Harness Engineering discipline.

### References

- [1] Claude Code源码逆向工程与系统性分析！Harness Engineering:基于Claude Code的完全指南 (http://mp.weixin.qq.com/s?__biz=MjM5ODkzMzMwMQ==&mid=2650451487)
- [2] Harness 到底是什么？看看 OpenClaw、Hermes、Claude Code 的演绎吧 (http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767)
- [3] 斩获21.4k Star！编程智能体harness builder开源 (Image references from http://localhost:8765/1908ad7a33/)
- [4] 1.3k Stars！阿里高德开源Agent Skills自进化框架，还能实现Hermes与Claude Code技能共享 (http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767)
- [5] 大模型技术综述推介：Code as Agent Harness及LALM语音大模型梳理 (Image references from http://localhost:8765/f31803442a/)