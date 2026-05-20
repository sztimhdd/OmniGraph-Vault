---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
- article:064f03c965
- article:1272b434a5
- article:82539b4eed
- article:4b7c022702
- article:9b4f7b24e0
- article:19c08ca449
- article:5f2dcd15d6
- article:443b50d6c4
- article:61fc48cae6
- article:5a26fee489
- article:c7fb080361
- article:1f3abd3428
- article:381f4ec9b6
- article:c1dd81698d
- article:1908ad7a33
- article:99a2043522
- article:e85fd44dd4
- article:781c9ac2c3
- article:9c53e463b1
- article:b75ac3d32c
- article:8a6f3af80a
- article:1950549023
- article:c8fb07ed4c
title: Claude Code
---

# Claude Code

## Definition / Overview

Claude Code is a terminal-based, AI-powered coding assistant and production-grade agent application developed by Anthropic^[article:5a362bf61e]^[article:4b7c022702]. It operates as a "vibe coding" environment that accepts natural language instructions, integrates with multiple model providers (including Sonnet 4.6, Opus 4.7, and via switchers DeepSeek‑V4‑Pro), and is widely regarded as the reference implementation of an AI agent **harness**^[article:5a362bf61e]^[article:b75ac3d32c]. Rather than a "batteries-included" IDE plugin, Claude Code is intentionally minimal magic: it is just Claude in a tool-use loop with a CLI, using the filesystem and standard utilities like `cat`, `grep`, `sed`, and `find`. As Grant Slatton notes on his blog, that lack of opacity is precisely what makes it easy to extend and trust.

Claude Code surpassed $1 billion in annual revenue in early 2026 and later reached a $2.5 billion annual run rate, with over 45 new features launched in Q1 2026 alone^[article:4b7c022702]. It is used both internally at Anthropic — where the Claude Code Team has all members, including managers and non-engineers, writing code with it — and externally by engineers at Apple, Andrej Karpathy, Simon Willison, Martin Alderson, and many others^[article:064f03c965].

![Claude Code v2.1.121 terminal interface](/static/img/443b50d6c4/10.jpg)

## Architecture / Design

Claude Code is written in TypeScript and React, comprising approximately 500,000–512,664 lines of code spread across roughly 1,900 files^[article:5a362bf61e]^[article:4b7c022702]. The architecture is structured as six layers of "harness" infrastructure surrounding the LLM^[article:5a362bf61e]:

1. **Tool System** — 43+ tools, where AgentTool, BashTool, and FileWriteTool account for ~80% of all tool calls^[article:5a362bf61e].
2. **Permission Model** — a seven-level hierarchical permission system with an AI classifier and five permission modes^[article:5a362bf61e].
3. **Hook System** — a native Hook system supporting 26 events across 4 types, enabling guard rules and lifecycle extensibility^[article:5a362bf61e].
4. **Sandbox & Security** — six layers of defense including file/network/process isolation, tool-call filtering, classifiers, compile-time feature gating, and user permission prompts^[article:5a362bf61e].
5. **Context Engineering** — a `CLAUDE.md` configuration file plus a memory system plus a four-level compaction pipeline managing the 200K token context window^[article:5a362bf61e].
6. **Settings & Configuration** — a 7-level hierarchy spanning user, project, and enterprise levels^[article:5a362bf61e].

The **Agent Loop** — described as "the heart of the harness" — is implemented as an infinite `while(true)` loop operating on a single State object, with seven distinct continue sites for fine-grained control^[article:5a362bf61e]. Entry points include CLI, MCP, and SDK, with lazy loading and parallel prefetch.

![Harness Engineering architecture overview](/static/img/5a362bf61e/0.jpg)

A particularly notable architectural feature is the **memory subsystem**. Claude Code distinguishes four memory types — user preferences, feedback corrections, project information, and external references — and writes memories across three layers: real-time Session Memory (triggered after 10K tokens with 5K-token deltas), cross-session Auto-Dream (≥24-hour gap, ≥5 new sessions), and a permanent KAIROS Daily Log with append-only writes plus nightly distillation^[article:4b7c022702]. The compression mechanism uses a structured 9-section template that mandates preservation of code snippets and verbatim user messages^[article:4b7c022702].

For multi-agent coordination, the source code contains **three distinct multi-agent systems** under `src/utils/swarm/`: a file-mailbox-based Swarm/Teammate system, a Coordinator "project manager" mode with only three tools (Agent, SendMessage, TaskStop), and a Fork mechanism designed for byte-level prompt-cache sharing^[article:4b7c022702]. A UDS_INBOX mechanism enables cross-instance communication via Unix Domain Sockets.

## History / Origin

Claude Code began as an internal incubator project at Anthropic, created by Boris Cherny. The team built it to scratch their own itch — a CLI-first agent harness that put Claude's strong tool-use post-training to maximum use. Anthropic released it publicly in early 2025, and as Grant Slatton observed, its appeal was the "lack of magic": it really is just Claude in a tool-use loop with a nice CLI.

Following its release, Claude Code rapidly became the canonical example of "Harness Engineering" — a term formalized in early 2026 by OpenAI's engineering team to describe the discipline of designing environments, constraints, feedback loops, and infrastructure that let AI agents operate reliably at scale^[article:5a362bf61e]. By Q1 2026, Anthropic shipped 45+ features, including remote-execution Bridge modes (Headless, Remote MCP, Teleport, Full Remote) and Ultraplan, which spins up Opus 4.6 in remote Plan Mode for up to 30-minute deep planning sessions^[article:4b7c022702].

The product has not been without controversy. In April 2026, Anthropic published *"An update on recent Claude Code quality reports"* admitting that three Harness-layer optimizations had inadvertently degraded model intelligence: a March 4 default reasoning effort downgrade from "high" to "medium," a March 26 buggy thinking-history clear that fired on every turn instead of once, and a third prompt-caching change. All three were fixed by version 2.1.116 on April 20, and Anthropic reset all subscription users' usage limits as compensation^[article:c8fb07ed4c]. A separate incident — a leak of `CLAUDE.md` from an Apple App on iOS — exposed Apple's internal Juno AI conversational support architecture; the file was deleted within 24 hours^[article:064f03c965].

![CLAUDE.md leak from Apple App](/static/img/064f03c965/0.jpg)

## Key Concepts / Components

### CLAUDE.md
`CLAUDE.md` is the project-level Markdown configuration file Claude Code reads at session start. It records tech stack, coding conventions, architecture decisions, naming rules, testing instructions, and known issues, and acts as a "soft constraint" with roughly 95% compliance^[article:5a362bf61e]. It is created via the `/init` command. Anthropic's documentation recommends keeping it under ~200 lines because every line is injected into the system prompt on each API call^[article:c8fb07ed4c]. A common workaround for adherence drift, popularized by Grant Slatton, is to start sessions with "read CLAUDE.md" and put a self-repeating instruction at the top of the file.

### Tool System and MCP
Claude Code provides 43+ built-in tools plus extensions via the Model Context Protocol (MCP), enabling integrations with services like Slack, Linear, Context7 (for technical documentation lookup), and GitNexus (for code-graph context)^[article:c1dd81698d]^[article:5a362bf61e]. The Claude Agent SDK exposes these same tools, the agent loop, and context management as a programmable API in Python and TypeScript, as documented in Anthropic's official Agent SDK docs.

### Skills, Subagents, and Plugins
Claude Code supports a Skills system, sub-agent spawning (via the Task tool), and a plugin marketplace. The `/plugin marketplace add` command, e.g. `anthropics/skills`, lets users install bundled capabilities^[article:1f3abd3428]. Notable third-party Skill collections include **Superpowers** (178k+ stars), **Scientific Agent Skills** (135 skills installable with one command), and **superpowers-zh** for Chinese-localized workflows^[article:82539b4eed]^[article:1f3abd3428].

### Memory and Context Engineering
Beyond the `CLAUDE.md` static layer, Claude Code uses a file-based persistent memory system at `src/memdir/`, plus 4-level context compaction once the 200K window pressures^[article:5a362bf61e]^[article:c8fb07ed4c].

### Hook System
26 events across 4 hook types (PreToolUse, PostToolUse, SessionStart, etc.) provide deterministic guard rails — used by Superpowers, OpenWolf, and GitNexus to inject context, enforce policies, or block dangerous operations^[article:82539b4eed]^[article:c1dd81698d].

### Ecosystem Tools
- **Happy** — 19.4k-star mobile/web client for remote-controlling Claude Code sessions with realtime voice and end-to-end encryption^[article:443b50d6c4].
- **OpenClaw / OpenWolf** — third-party harness layers that reduce Claude Code token consumption by ~80% via memory systems and project-intelligence indexing^[article:5a26fee489]^[article:781c9ac2c3]^[article:8a6f3af80a].
- **CC Switch** — model switcher allowing Claude Code to point at DeepSeek-V4-Pro and other providers^[article:b75ac3d32c]^[article:1950549023].
- **CC Log Workbench** — desktop tool for searching and visualizing Claude Code's local JSONL conversation logs^[article:c7fb080361].
- **GitNexus** — 32.9k-star tool that builds a code knowledge graph and exposes it to Claude Code via MCP and hooks^[article:c1dd81698d].
- **Archon** (harness builder) — 21.4k-star workflow engine wrapping Claude Code with engineering constraints^[article:1908ad7a33].
- **Everything Claude Code** — performance-enhancement system for AI agent harnesses including Claude Code, Codex, and Cursor^[article:381f4ec9b6].

![CC Log Workbench desktop tool](/static/img/d3ea02e629/0.jpg)

## Notable Use Cases / Examples

**Code generation and engineering.** Claude Code is heavily used for production code at Anthropic itself, where the Claude Code Team reports it writes nearly 100% of the team's internal code. Boris Cherny has merged many PRs entirely written through it. Andrej Karpathy uses it as part of his AI-assisted coding workflow, and Simon Willison treats it as a semi-black box for production tasks, trusting outputs based on repeated successful runs.

**Reverse engineering and sysadmin.** Martin Alderson has documented using Claude Code to decompile and binary-patch Windows DLLs for Wine compatibility, manage server infrastructure, port Photoshop 1's source to C# in 30 minutes, and automate Linux migration tasks (see Martin Alderson's blog).

**Domain agents.** Alderson also built a UK tax professional agent using only a `CLAUDE.md` file with statute references; it scored 2.5/3 on a real ATT exam question that even Opus alone got wrong^[article:5a26fee489]. Similar patterns now extend to non-engineering professional services.

**Vibe coding from anywhere.** Through Happy, the iLink WeChat integration, and SDK wrappers, users now run Claude Code from phones and chat apps, achieving truly remote agentic coding sessions^[article:443b50d6c4]^[article:9b4f7b24e0].

![Happy mobile client interface](/static/img/443b50d6c4/11.jpg)

**Knowledge management.** Teams use Claude Code as the query interface to LLM Wikis, with subagents performing research, synthesis, and documentation pipeline work^[article:19c08ca449].

**Office automation.** Open-source tools like 飞书CLI bring Lark/Feishu document workflows into Claude Code as MCP-driven Agent capabilities^[article:5f2dcd15d6], and Baidu's DuMate has even been demonstrated tutoring users on Claude Code itself^[article:381f4ec9b6].

**Cost optimization.** The combination "OpenClaw + Claude" achieves dramatic token savings — though Anthropic later moved to block third-party harnesses from drawing on subscription quotas, prompting wider community discussion^[article:781c9ac2c3]^[article:8a6f3af80a].

**Competitive landscape.** Claude Code is frequently compared with OpenAI Codex, Cursor, OpenCode, and Kimi Code; some power users (including the author of *"退订Claude Code！全面拥抱Codex"*) migrated to Codex after the April quality regressions^[article:9c53e463b1]. The DeepSeek-TUI project, a Rust-built "DeepSeek version of Claude Code," gained 11k+ stars in days^[article:b75ac3d32c]. Despite competition, evaluations show Claude Code achieves 100% success on long-horizon complex tasks, though using more tokens (537,413) than minimalist alternatives like GenericAgent (188,829)^[article:5a362bf61e].

## Cross-references

- [[anthropic]]
- [[claude]]
- [[claude-md]]
- [[claude-agent-sdk]]
- [[harness-engineering]]
- [[agent-loop]]
- [[mcp]]
- [[openclaw]]
- [[happy]]
- [[superpowers]]
- [[gitnexus]]
- [[cc-log-workbench]]
- [[deepseek-tui]]
- [[codex]]
- [[cursor]]
- [[everything-claude-code]]
- [[scientific-agent-skills]]
- [[archon]]
- [[mini-harness]]
- [[juno-ai]]

## Further Reading

- [Claude Code (Grant Slatton)](https://grantslatton.com/claude-code) — Hands-on tips covering CLAUDE.md adherence, ripgrep-based context-gathering workflow, and what makes claude-code feel "magic-free."
- [Building a Tax Agent with Claude Code (Martin Alderson)](https://martinalderson.com/posts/building-a-tax-agent-with-claude-code/?utm_source=rss&utm_medium=rss&utm_campaign=feed) — Walkthrough of building a domain agent for UK tax exams using only CLAUDE.md and statute folders.
- [Solving Claude Code's API Blindness with Static Analysis Tools (Martin Alderson)](https://martinalderson.com/posts/claude-code-static-analysis/?utm_source=rss&utm_medium=rss&utm_campaign=feed) — On combining static analysis with Claude Code to overcome its codebase-context limits.
- [Self-improving CLAUDE.md Files (Martin Alderson)](https://martinalderson.com/posts/self-improving-claude-md-files/?utm_source=rss&utm_medium=rss&utm_campaign=feed) — Pattern for letting the agent update its own rules file over time.
- [How I Use Claude Code to Manage Sysadmin Tasks (Martin Alderson)](https://martinalderson.com/posts/how-i-use-claude-code-to-manage-sysadmin-tasks/?utm_source=rss&utm_medium=rss&utm_campaign=feed) — Real-world infrastructure automation with the agent.
- [Agent SDK overview (Anthropic Docs)](https://code.claude.com/docs/en/agent-sdk/overview) — Official documentation for the Claude Agent SDK exposing the same loop and tools as Claude Code.
- [How to Use Claude Code: A Guide to Slash Commands, Agents, Skills (Product Talk)](https://www.producttalk.org/how-to-use-claude-code-features/) — Clear taxonomy of Markdown files, slash commands, agents, and skills.
- [Claude Code: Build Your First AI Agent (YouTube — Teacher's Tech)](https://www.youtube.com/watch?v=gHB4JFG9i3k) — Beginner-oriented video on agentic workflows with VS Code + Claude Code.
- [How I Made Claude Code Agents Coordinate 100% (Medium — Ilyas Ibrahim)](https://medium.com/@ilyas.ibrahim/how-i-made-claude-code-agents-coordinate-100-and-solved-context-amnesia-5938890ea825) — Practitioner notes on simplifying agent fleets.
- [How I Built an Autonomous AI Startup System with 37 Agents (DEV)](https://dev.to/asklokesh/how-i-built-an-autonomous-ai-startup-system-with-37-agents-using-claude-code-2p79) — Open-source "Loki Mode" using Claude Code skills for end-to-end product orchestration.
- [No, it doesn't cost Anthropic $5K per Claude Code user (Martin Alderson)](https://martinalderson.com/posts/no-it-doesnt-cost-anthropic-5k-per-claude-code-user/?utm_source=rss&utm_medium=rss&utm_campaign=feed) — Counter-analysis of Claude Code unit economics.
- [Coding Agent in a microVM with Nix (Michael Stapelberg)](https://michael.stapelberg.ch/posts/2026-02-01-coding-agent-microvm-nix/) — Sandboxing Claude Code in disposable VMs.
- [The biggest advance in AI since the LLM (Gary Marcus)](https://garymarcus.substack.com/p/the-biggest-advance-in-ai-since-the) — Argument that Claude Code represents neurosymbolic-style progress.