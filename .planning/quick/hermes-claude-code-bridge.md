# Hermes → Claude Code Bridge Pattern

## Status: Backlog

## Vision

Hermes orchestrates, Claude Code implements.

| Role | Agent | Responsibility |
|------|-------|----------------|
| **Orchestrator** | Hermes | KG retrieval, context assembly, diff review, commit decision, skill management |
| **Implementer** | Claude Code (ACP) | Focused multi-file code changes, bug fixes, feature implementation |

## Mechanism

```python
delegate_task(
    goal="Implement X",
    context="Full context: files, specs, error messages",
    acp_command="claude",
    acp_args=["--acp", "--stdio", "--max-turns", "20"]
)
```

Hermes spawns Claude Code via ACP subprocess transport. Claude Code gets an isolated context + terminal session. Only the final summary enters Hermes' context window.

## Guard Rails

| Guard Rail | Mechanism | Why |
|---|---|---|
| **Budget cap** | `acp_args=["--acp", "--stdio", "--max-turns", "N"]` | Claude Code per-API-call costs; agent spawning agent cascades costs |
| **Review-before-commit** | Hermes reads diff with `git diff`, shows user, waits for "commit" | User stays the reviewer, not the middleman |
| **Scope boundaries** | Hermes owns orchestration + KG queries + skills; Claude Code only touches source code | Never let Claude Code modify skills, KG configs, or run ingest scripts |

## When to Use

- Multi-file feature implementation (like the topic-depth filter)
- Bug fixes requiring deep codebase context
- Tasks that would benefit from Claude Code's autonomous file exploration

## When NOT to Use

- Single-file edits or simple changes — keep in Hermes (cheaper, faster)
- Anything touching skills, configs, or knowledge graph — Hermes territory
- Tasks requiring user interaction mid-stream (Claude Code can't ask questions)

## Workflow

1. Hermes retrieves context (KG query, file reads, error logs)
2. Hermes delegates to Claude Code: `delegate_task(acp_command="claude", ...)`
3. Claude Code implements autonomously
4. Hermes reads the diff, presents to user
5. User approves → Hermes commits the change
6. (Optional) Hermes updates relevant skills if the pattern changed

## Relationship to Existing Skills

- **subagent-driven-development**: Parallel task dispatch with 2-reviewer cycles. Use when you want N independent tasks with spec+quality reviews.
- **Hermes-Claude Code Bridge** (this doc): Single focused agent implementation with Hermes-as-reviewer. Use when you want one deep session doing a complex feature.
