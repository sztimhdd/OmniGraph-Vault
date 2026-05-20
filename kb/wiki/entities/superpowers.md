---
confidence_level: medium
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:9c53e463b1
title: Superpowers
---

# Superpowers

## Definition / Overview

**Superpowers** is an open-source agentic skills framework and software development methodology designed to enforce professional engineering discipline on AI coding agents. Rather than providing new code-execution capabilities, it functions as a *behavior-shaping system* that injects structured workflow constraints into an agent's context, transforming best practices from polite suggestions into hard, enforceable rules ^[article:9c53e463b1]. The project, originally authored by Jesse Vincent and published via AgentBuff, has reportedly garnered around 178k stars on GitHub, making it one of the most prominent skill libraries in the AI coding ecosystem ^[article:9c53e463b1].

The framework's core insight is captured succinctly in its source material: "代理不需要'被建议'怎么做，而是需要'被强制'怎么做" — agents do not need to be advised how to work, they need to be *forced* to work correctly ^[article:9c53e463b1]. According to the Termdock analysis of the framework, this stems from observations that agents respond to structure: "A skill that says 'write tests first' is ignored. A skill that says 'NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. Write code before the test? Delete it. Start over.' is followed."

Superpowers covers eight major coding agent platforms: Claude Code, Codex CLI, Codex App, Cursor, Gemini CLI, OpenCode, GitHub Copilot CLI, and Factory Droid ^[article:9c53e463b1].

## Architecture / Design

Superpowers is built around a single, platform-agnostic principle: a **behavior constraint model** unified through a shared `skills/` directory, with platform-specific adaptation layers handling the bootstrap mechanics ^[article:9c53e463b1].

### Repository Structure

The repository contains roughly seven top-level pieces ^[article:9c53e463b1]:

- `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.opencode/` — per-platform plugin manifests
- `hooks/` — session-start scripts (`session-start`, `run-hook.cmd`) and platform-specific hook configs
- `skills/` — the **core asset**: 14 skill directories, each containing a `SKILL.md`
- `scripts/` — version management (`bump-version.sh`) and codex sync utilities
- `CLAUDE.md`, `GEMINI.md`, `AGENTS.md` — per-platform context files
- `tests/`, `docs/` — integration tests and documentation

### Three Bootstrap Paths

While the behavior constraint model is unified, the *injection mechanism* differs per platform ^[article:9c53e463b1]:

- **Path A — Hook-driven (Claude Code, Cursor, GitHub Copilot CLI):** A `hooks/session-start` Bash script reads `skills/using-superpowers/SKILL.md`, escapes it as a JSON string, and emits it inside an `<EXTREMELY_IMPORTANT>` block as `additionalContext` (or `additional_context` for Cursor).
- **Path B — Plugin transform (OpenCode):** Instead of a shell hook, `.opencode/plugins/superpowers.js` registers the `skills/` directory and uses `experimental.chat.messages.transform` to prepend bootstrap text to the first user message.
- **Path C — Context file (Gemini CLI):** A `gemini-extension.json` declares `GEMINI.md` as the context file, which then explicitly references `@./skills/using-superpowers/SKILL.md`.

The piece that all three paths converge on is the `using-superpowers` skill — the true shared behavior entry point ^[article:9c53e463b1].

### Cross-Platform Hook Compatibility

`run-hook.cmd` is a polyglot script that functions as both a Windows batch file and a Unix bash script, using the extension-less hook filename to dodge Windows preprocessing of `.sh` files. A noted edge case: if Windows cannot locate `bash`, the hook silently exits with code 0 — the plugin doesn't crash, but loses its context-injection capability ^[article:9c53e463b1].

## History / Origin

Superpowers was created by Jesse Vincent and published through the `AgentBuff` channel, which authored the canonical "Superpowers 深度实战指南" (Superpowers In-Depth Practical Guide) ^[article:9c53e463b1]. According to Termdock's writeup, Superpowers grew out of Vincent's frustrations with Claude Code on serious software work: "Left to its own devices, it would skip tests, implement features before understanding requirements, and apply quick fixes to bugs it had not properly diagnosed."

A localized fork, **superpowers-zh**, adapts the original 14 English skills for Chinese developers and adds 6 original skills targeting Chinese development scenarios — including Chinese-style code review (replacing Western direct-feedback culture) and Gitee/Coding-CI workflows in place of GitHub Actions defaults ^[article:9c53e463b1].

The framework's prominence is part of a broader 2025–2026 industry shift from Prompt Engineering → Context Engineering → **Harness Engineering** — the discipline of building systems that turn raw model capability into stable, verifiable product behavior ^[article:9c53e463b1]. As one popular formulation goes: *Model = brain; Harness = body + workbench + operating procedures + supervision* ^[article:9c53e463b1].

## Key Concepts / Components

### The 14 Skills

The `skills/` directory is not a grab-bag of tips but a complete development pipeline broken into stages ^[article:9c53e463b1]:

| Stage | Skills |
|-------|--------|
| Entry & dispatch | `using-superpowers`, `dispatching-parallel-agents`, `subagent-driven-development` |
| Up-front design | `brainstorming` |
| Planning & execution | `writing-plans`, `executing-plans` |
| Engineering discipline | `test-driven-development`, `systematic-debugging`, `verification-before-completion` |
| Delivery & wrap-up | `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch`, `using-git-worktrees` |
| Meta | `writing-skills` |

Each skill is a `SKILL.md` file with YAML frontmatter, where the `description` field deliberately encodes only *trigger conditions* (e.g. "Use when...") rather than the full workflow — letting the agent search-match the skill, then read the body to execute ^[article:9c53e463b1].

### Iron Laws

Each core skill carries an inviolable **Iron Law** — and "violating the letter is violating the spirit," cutting off the rationalization escape hatch ^[article:9c53e463b1]:

| Skill | Iron Law |
|-------|----------|
| TDD | No production code without a failing test first |
| Debugging | No fix proposal without root-cause investigation |
| Verification | No completion claim without fresh verification evidence |

### Rationalization Prevention

Every skill contains three layered defenses against agents skipping discipline under pressure ^[article:9c53e463b1]:

1. **Red Flags table** — signals the agent can self-check
2. **Common Rationalizations table** — every common excuse paired with its rebuttal
3. **Concrete Good/Bad work examples**

The `using-superpowers` entry skill, for instance, includes a red-flag table that catches excuses like "this is just a simple problem" → "the problem *is* the task; check skills" ^[article:9c53e463b1].

### HARD-GATE

The `brainstorming` skill enforces a HARD-GATE rule: *no implementation skill may be invoked, no code written, and no project scaffolded until a design has been presented and approved by the user.* The only skill that may follow `brainstorming` is `writing-plans` — direct jumps to implementation are forbidden ^[article:9c53e463b1].

### Priority Order and "Human Partner" Language

Superpowers establishes an explicit instruction priority: user's `CLAUDE.md`/`GEMINI.md`/`AGENTS.md` (highest) > Superpowers skills > default system prompt. This means a user can override any Superpowers behavior in their context file ^[article:9c53e463b1]. The framework also deliberately uses the phrase "your human partner" rather than "the user" to frame the relationship as collaborative rather than service-oriented ^[article:9c53e463b1].

### Subagent-Driven Development

Once a plan exists, the master agent dispatches fresh subagents per task — implementer, then spec-reviewer, then code-quality-reviewer — providing isolated context and a two-stage review before marking each task complete ^[article:9c53e463b1]. According to LinkedIn discussion of the framework, this design lets agents "run for 2+ hours without hallucinating."

## Notable Use Cases / Examples

### Installation Across Platforms

Superpowers offers near-uniform installation flows ^[article:9c53e463b1]:

- **Claude Code:** `/plugin install superpowers@claude-plugins-official`
- **Codex CLI / App:** `/plugins` → search Superpowers (CLI and App share `.codex-plugin/plugin.json`; the App reads additional `interface` UI metadata)
- **Cursor:** `/add-plugin superpowers`
- **Gemini CLI:** `gemini extensions install https://github.com/obra/superpowers`
- **OpenCode:** add `"superpowers@git+https://github.com/obra/superpowers.git"` to the `plugin` array in `opencode.json`
- **GitHub Copilot CLI / Factory Droid:** marketplace add + install pointing at `obra/superpowers-marketplace`

### Comparative Positioning

Per Pulumi's framework comparison, Superpowers is the right pick when "code works today, breaks tomorrow" is the recurring failure mode, because "it forces every change through a failing test first." Pulumi positions it alongside GSD (good for first-hour quality drop-off via fresh context per phase) and GSTACK (product review before engineering), suggesting Superpowers' TDD layer can be bolted onto GSTACK direction-setting.

### Custom Skills and Acceptance Testing

Users can author personal skills in `~/.claude/skills` (Claude Code), `~/.agents/skills/` (Codex), or `~/.config/opencode/skills/` (OpenCode), and project-level skills in `.opencode/skills/` ^[article:9c53e463b1]. The recommended authoring loop is itself TDD-based:

1. **RED** — run a stress scenario with no skill, log the agent's violations
2. **GREEN** — write the minimal skill that prevents those specific violations
3. **REFACTOR** — find new rationalizations, plug them, re-validate ^[article:9c53e463b1]

For new platform integrations, the project requires an acceptance transcript: open a clean session, send "Let's make a react todo list," and the `brainstorming` skill must auto-trigger ^[article:9c53e463b1].

### Performance Budgets

Because `using-superpowers` loads in *every* session, it is held under 150 words; frequently-referenced skills target <200 words; other skills <500 words. Cross-references are preferred over duplication, and code examples use only one language since "agents are good at porting" ^[article:9c53e463b1].

## Cross-references

- [[claude-code]]
- [[codex-cli]]
- [[codex-app]]
- [[cursor]]
- [[gemini-cli]]
- [[opencode]]
- [[github-copilot-cli]]
- [[factory-droid]]
- [[superpowers-zh]]
- [[skill-md]]
- [[skills-system]]
- [[test-driven-development]]
- [[harness]]
- [[agent-skills]]
- [[jesse-vincent]]
- [[agentbuff]]

## Further Reading

- [obra/superpowers (GitHub)](https://github.com/obra/superpowers) — Canonical repository for the framework, including quickstart, skills library, and contribution rules.
- [Superpowers 深度实战指南 (AgentBuff)](https://mp.weixin.qq.com/s/BvrB7td8iJd4vNQW3T_UFg) — Original deep practical guide by AgentBuff covering architecture, install paths, and skill-by-skill walkthrough.
- [顶流编码Skill！superpowers 凭什么狂揽178k Stars? (字节笔记本)](http://mp.weixin.qq.com/s?__biz=MzIzMzQyMzUzNw==&mid=2247516115&idx=2&sn=8b6fd6d4ff0552dc38113aecb7d74e76) — Chinese commentary explaining the framework's popularity and the superpowers-zh localization.
- [What Is the Superpowers Plugin for Claude Code? (MindStudio)](https://www.mindstudio.ai/blog/what-is-superpowers-plugin-claude-code/) — Accessible overview of the 14 skills and how they integrate with Claude Code's `CLAUDE.md` system.
- [Superpowers: Skills Framework Reshaping AI Dev (Termdock)](https://www.termdock.com/en/blog/superpowers-framework-agent-skills) — Background on Jesse Vincent's motivation and the philosophical core of the framework.
- [Superpowers, GSD, and GSTACK comparison (Pulumi)](https://www.pulumi.com/blog/claude-code-orchestration-frameworks/) — Side-by-side framework comparison with practical "when to use which" guidance.
- [Agentic Skills Frameworks Compared (Ry Walker)](https://rywalker.com/research/agentic-skills-frameworks) — Comparative research with a real-feature case study using Superpowers on a Next.js project.
- [Kevin O'Hara on Superpowers (LinkedIn)](https://www.linkedin.com/posts/kevinmohara_github-obrasuperpowers-an-agentic-skills-activity-7437667432636403714-F4Eb) — Industry commentary emphasizing that "process, not intelligence, is the bottleneck" in production agent work.
- [Claude Code + SUPERPOWERS Tutorial (YouTube, EricTech)](https://www.youtube.com/watch?v=TX91PdBn_IA) — Full walkthrough of the brainstorm → spec → plan → subagent → review workflow on a production app.
- [Agentic Engineering with 'Superpowers' (SitePoint)](https://www.sitepoint.com/agentic-engineering-superpowers-framework-agent-capabilities/) — Conceptual treatment of the "superpowers" pattern as an architectural abstraction over flat tool registries.