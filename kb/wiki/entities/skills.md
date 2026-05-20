---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:1272b434a5
- article:9f75b25295
- article:f5f44ab394
- article:8a6f3af80a
- article:c8cc5b1fb7
- article:54a36baa97
- article:5a362bf61e
- article:381f4ec9b6
- article:781c9ac2c3
- article:9c53e463b1
- article:8a5a502c8b
title: Skills
---

# Skills

## Definition / Overview

**Skills** are reusable, modular capability packages that extend an AI agent's behavior beyond what the base model can do unaided. In contemporary agent architectures, a Skill is typically a folder containing a `SKILL.md` file (Markdown plus YAML frontmatter) that describes *how to perform a specific task* — including triggering conditions, step-by-step procedures, red flags, and rationalization tables — together with optional bundled scripts, templates, and reference materials ^[article:c8cc5b1fb7]^[article:5a362bf61e].

Conceptually, Skills sit between **Tools** (atomic operations such as file reads, shell commands, or API calls) and **Agents** (the autonomous executor). Where tools are *what can be done*, Skills are *how to do something well* — codified workflows, Standard Operating Procedures (SOPs), and best practices that migrate human operational knowledge into a reusable form an agent can selectively load ^[article:c8cc5b1fb7]^[article:9f75b25295]. According to the open Agent Skills specification at agentskills.io, Skills are loaded progressively: at startup an agent reads only each skill's `name` and `description`; the full instructions are pulled into context only when a task matches.

![SKILL/Agent/MCP/Plugin overview](/static/img/4f8c76b972/0.jpg)

## Architecture / Design

A canonical Skill file uses YAML frontmatter followed by structured Markdown:

```
---
name: skill-name
description: "Use when [trigger condition]..."
---
# Title
## Overview / When to Use / Checklist / Red Flags / Common Rationalizations
```

The `description` field is deliberately written as a **trigger condition** rather than a feature summary, so that the agent's selection layer can match a task to the right skill without loading the full body ^[article:5a362bf61e].

In the Superpowers framework — a 178k-star open-source skill collection — Skills are organized into a `skills/` directory and surfaced to harnesses (Claude Code, Codex, Cursor, OpenCode, Gemini CLI, Copilot CLI, Factory Droid) through different bootstrap mechanisms: hooks for Claude Code, plugin transforms for OpenCode, `GEMINI.md` references for Gemini CLI ^[article:5a362bf61e]. The system enforces a hard rule via the `using-superpowers` entry skill: *if there is a 1% chance a skill applies, the agent must check it first*.

![mattcock/skills repository](/static/img/f799dcd732/0.jpg)
![Skills philosophy README](/static/img/f799dcd732/1.jpg)

In **OpenClaw**, Skills follow an `AgentSkills`-compatible folder layout. Each skill folder contains a `SKILL.md` whose realpath must resolve inside the configuration root (a sandbox check), and skills are loaded into a registry that distinguishes **Bundled Skills** (built-in), **Managed Skills** (system-controlled, can override plugins), **Plugin Skills** (third-party, lower priority), and **Custom Skills** (user-authored, e.g. `my-deploy.md`) ^[article:c8cc5b1fb7]^[article:781c9ac2c3].

Microsoft's Agent Framework and Spring AI both implement essentially the same pattern (`SkillsProvider` / `AgentSkillsProvider` scanning a directory of `SKILL.md` files), confirming that the format originated by Anthropic has become a de-facto open standard across vendors.

## History / Origin

The Skills concept was introduced by Anthropic as a way to standardize how Claude-family agents acquire reusable capabilities, particularly around CLI usage and domain workflows ^[article:8a6f3af80a]. Anthropic later released the `SKILL.md` format as an open specification (now hosted at agentskills.io), which has been adopted by GitHub Copilot, Codex, Cursor, Gemini, Microsoft Agent Framework, and Spring AI.

Inside the Anthropic ecosystem, Claude Code exposes Skills via the `/skills` command and ships with built-in skills (Anthropic's `example-skills`, including `webapp-testing`). The Codex Desktop App in turn surfaces Skills through a `$` invocation in the input box ^[article:f5f44ab394]^[article:9c53e463b1].

The Chinese agent ecosystem rapidly absorbed the pattern. **OpenClaw** integrated Skills as its core extension mechanism, eventually accumulating 143k+ GitHub stars and a dedicated `awesome-openclaw-skills` repo ^[article:781c9ac2c3]^[article:c8cc5b1fb7]. **Hermes Agent** treats Skills as AI-generated documents that are written *after* a complex task succeeds and improved with each subsequent use; Hermes Skills are equivalent to OpenClaw Playbooks and function as tool manuals defining CLI/API usage, with hermes101.dev hosting an online library of 100+ such skills ^[article:9f75b25295]^[article:8a6f3af80a]. **WorkBuddy Claw** (a Tencent-cloud-aligned product evaluated by DuMate) ships over a hundred built-in Skills as plugins for coding and office automation ^[article:381f4ec9b6].

The latest research direction — exemplified by **CoEvoSkills / SkillGraph** — treats Skills not as static documents but as nodes in an evolving graph that the agent itself maintains.

![SkillGraph framework](/static/img/2c929671e6/0.jpg)
![Skill graph construction](/static/img/2c929671e6/2.jpg)

## Key Concepts / Components

**SKILL.md.** The single required artifact in a skill folder. Contains YAML frontmatter (name, description, optional `applicability_condition`, `category`) and a Markdown body. Loaders enumerate skills from configured roots and accept only paths whose realpath remains inside the root — a critical sandbox rule in OpenClaw ^[article:c8cc5b1fb7].

**Skills System.** The framework that registers, indexes, and dispatches skills. Includes a Built-in Skills Registry (e.g. `/update-config`, `/keybindings-help`, `/debug`, `/simplify`, `/batch`, `/schedule`, `/loop`, `/claude-api`, plus the `skillify` skill) and a Custom Skills loader (`loadSkillsDir`).

**Skills vs Tools.** Tools are atomic — read a file, run a shell command, hit an API. Skills are *workflow definitions* that orchestrate multiple tool invocations under stable rules ^[article:5a362bf61e]. Skills act as a **stabilizer** preventing the model from being too divergent.

**Three-Layer Architecture.** OpenClaw and Hermes both organize automation as **CLI Layer → Skill Layer → Employee Agent Layer**. The Skill Layer holds reusable methods; the CLI Layer executes; the Agent Layer orchestrates ^[article:c8cc5b1fb7]^[article:9f75b25295].

**Skill as Code Methodology.** A discipline that fuses five principles: Skill as Code, Iron Law + Red Flag + Rationalization Table, Sub-agent Architecture, Cross-platform Unification, and TDD Throughout ^[article:5a362bf61e]. The Iron Law / Red Flag / Rationalization pattern explicitly enumerates the *excuses* an agent might invent to skip the skill, neutralizing them before they're rationalized.

**Skill Graph.** A graph G=(V, E) where nodes are skills and edges carry one of three semantic types — *Prerequisite*, *Enhance*, *Co-occur* — each with a dynamic weight w∈[0,1]. Topological sorting over this graph yields an *Ordered Skill Sequence* fed to the policy model ^[article:8a5a502c8b].

![Graph-aware retrieval](/static/img/2c929671e6/3.jpg)
![Graph evolution operators](/static/img/2c929671e6/4.jpg)

**Co-Evolution (CoEvoSkills).** A framework where a Skill Generator and a Skill Validator iteratively produce and prune skills with no human in the loop. Node-level operations include *Insert*, *Merge* (Jaccard similarity ≥ 0.85 of neighbor sets), *Split* (high usage but mid success rate), and *Deprecate* (≥20 uses, success < 0.15). Edge-level operations include *Path Reinforce*, *Co-occur Discovery*, and *Decay & Prune* (γ = 0.99, w_min = 0.05) ^[article:8a5a502c8b].

**Process Skill-ification (流程技能化).** A pattern in next-generation enterprise digital architectures where business processes from OA/BPM/financial systems are decomposed into Skills that an employee Agent can invoke — e.g. a *Reimbursement Process Skill* spanning document submission to ledger sync, with built-in risk screening for duplicate claims ^[article:1272b434a5].

**Externalization.** Skills are increasingly *externalized* from model weights into searchable, hot-updatable assets — part of a broader trend articulated in the Nexus paper toward compiling knowledge as reusable verbs (skills) rather than retrieving facts (RAG) ^[article:8a5a502c8b]^[article:1272b434a5].

![Butler / skill evolution mechanism](/static/img/b41671909d/4.jpg)

## Notable Use Cases / Examples

**Superpowers (mattpocock / obra).** A canonical skills collection (~178k stars) covering the full software development lifecycle: `brainstorming`, `writing-plans`, `executing-plans`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `using-git-worktrees`, `subagent-driven-development`, `dispatching-parallel-agents`, `finishing-a-development-branch`, `writing-skills`, and the bootstrap `using-superpowers` ^[article:5a362bf61e]. A Chinese fork (`superpowers-zh`) added six locale-specific skills for Gitee/Coding-style workflows.

**OpenClaw Skills Ecosystem.** The `awesome-openclaw-skills` repository (6.2k stars, 565 forks) hosts community-contributed skills covering everything from contract review to scheduled tasks and heartbeat automation. OpenClaw distinguishes safe Bundled/Managed Skills from third-party skills which carry context-contamination risk ^[article:c8cc5b1fb7]^[article:781c9ac2c3].

![OpenClaw skills repo](/static/img/42810fecf4/3.jpg)

**Hermes Skills.** Hermes treats every successful complex task as an opportunity to *write a skill afterwards*, then refines it on each subsequent run. Skills become the agent's accumulated tool manual; the MiMo V2 Pro promotion gave users two free weeks specifically to bootstrap their personal skill libraries ^[article:9f75b25295].

**ima skill (Tencent).** A skill packaging knowledge-management automation, marketed as letting users run their information pipeline "fully automatically" via a lobster-army of agents.

**codex/review skill.** Peter Steinberger's script (defined in `agent-scripts/skills/codex-review/SKILL.md`) that runs Codex review in a loop until no errors remain ^[article:9c53e463b1].

**Knowledge Check (快查).** A document-compliance system whose 7-module pipeline — Bootstrap, Rule Extraction, **Skill Writing**, Skill Testing, Distillation, Full Test, Packaging — automatically converts natural-language regulations into executable Rule Skills ^[article:8a5a502c8b].

![Seven-module automation pipeline](/static/img/b41671909d/12.jpg)

**Reshape-Your-Life Skill.** A consumer-facing OpenClaw skill built on NLP logical-levels theory; demonstrates how non-technical users can package a methodology as a Skill folder (`SKILL.md` + `references/nlp-levels-guide.md` + `session-scripts.md`) and install it into a remote agent.

**Enterprise Process Skills.** As argued in the "RAG-shorting" piece, the future enterprise Agent layer is fed by *Process Skill-ification* — taking the workflows already encoded in BPM, OA, and financial systems and rewriting them as auditable, composable Skills owned by each employee's personal Agent ^[article:1272b434a5].

## Cross-references

- [[openclaw]]
- [[hermes-agent]]
- [[claude-code]]
- [[codex]]
- [[superpowers]]
- [[harness-engineering]]
- [[tools]]
- [[agent]]
- [[mcp-server]]
- [[skill-graph]]
- [[coevoskills]]
- [[nexus]]
- [[skill-as-code]]
- [[using-superpowers]]
- [[skill-md]]

## Further Reading

- [Agent Skills Overview — agentskills.io](https://agentskills.io/home) — Official open specification originally released by Anthropic; defines the SKILL.md format and progressive-disclosure loading model.
- [Spring AI Agentic Patterns: Agent Skills](https://spring.io/blog/2026/01/13/spring-ai-generic-agent-skills) — Java-ecosystem implementation showing LLM-portable skills via `spring-ai-agent-utils`.
- [Microsoft Agent Framework: Agent Skills](https://learn.microsoft.com/en-us/agent-framework/agents/skills) — `AgentSkillsProvider` API, multi-root skill discovery, and DI integration.
- [awesome-agent-skills (heilcheng)](https://github.com/heilcheng/awesome-agent-skills) — Curated index of skills and the tools that support them (Claude, Copilot, VS Code, Codex, Gemini, Kiro, Junie, Antigravity).
- [Essential Skills for Building AI Agents — Galileo](https://galileo.ai/blog/7-essential-skills-for-building-ai-agents) — Counterpoint article framing "skills" as developer competencies (NLP, vision, API integration) rather than the SKILL.md artifact.
- [Top Skills to Build AI Agents in 2025 — PromptLayer](https://blog.promptlayer.com/top-skills-to-build-ai-agents-in-2025/) — Practitioner-oriented complement covering programming, data, NLP, and KR&R foundations.
- [The 7 Skills You Need to Build AI Agents (YouTube)](https://www.youtube.com/watch?v=mtiOK2QG9Q0) — Architecture, tool-contract design, and product-thinking perspective on agent construction.
- [AI Agent Frameworks — IBM Think](https://www.ibm.com/think/insights/top-ai-agent-frameworks) — Surveys frameworks (LangGraph, LlamaIndex, Semantic Kernel) into which Skills plug.
- [Harness 到底是什么？OpenClaw / Hermes / Claude Code 的演绎](http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767&idx=1&sn=b3d620a57e8833c4928da40f67fdecd1&chksm=ce76a5dbf9012ccdd1b4702fc96b85fe496591549c109333872f89d16b133323ade3b9e07a94#rd) — Cross-framework comparison of how Skills sit inside a harness.
- [顶流编码Skill！superpowers 凭什么狂揽178k Stars?](http://mp.weixin.qq.com/s?__biz=MzIzMzQyMzUzNw==&mid=2247516115&idx=1&sn=a26122526b05f74970f998c759f2eb8c&chksm=e887280ddff0a11b104352be79d73c1b16bd45dd5ae40540fbcda192e5a6524f4f0b8a99221d#rd) — Deep dive into the Superpowers project and its Chinese localization.