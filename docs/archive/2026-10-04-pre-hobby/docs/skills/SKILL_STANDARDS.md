# OpenClaw / Hermes Skill Writing Standards

> Synthesized from: docs.openclaw.ai/tools/creating-skills, dench.com/blog/openclaw-skill-writing-advanced,
> hermes-agent.ai/blog/hermes-agent-skills-guide, lushbinary.com/blog/hermes-agent-custom-skills-development-guide,
> hermes-agent.nousresearch.com/docs/user-guide/features/skills

## Skill Directory Structure

Every skill is a **directory**, not a single file:

```
my-skill/
├── SKILL.md           # Agent-facing instructions + metadata (required)
├── references/        # Docs the agent reads on-demand (Level 2 loading)
│   └── api-docs.md
├── scripts/           # Shell scripts the agent executes via exec
│   └── run-query.sh
└── README.md          # Human-facing: install guide, examples
```

`references/` = documents the agent reads. `scripts/` = scripts the agent runs. Never mix.

## SKILL.md Frontmatter

```yaml
---
name: omnigraph_query          # snake_case, unique, required
description: >-                # one-line, shown to agent at Level 0 — accuracy is critical
  Query the OmniGraph-Vault knowledge graph by natural language.
triggers:                      # Hermes auto-match phrases
  - "search the knowledge base"
  - "what do I know about"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---
```

Required: `name`, `description`. Optional but impactful: `triggers`, `metadata.openclaw.requires.*`.

## Progressive Disclosure (Hermes Token Efficiency)

```
Level 0: skills_list()           → name + description only (~3k tokens for full catalog)
Level 1: skill_view(name)        → full SKILL.md content
Level 2: skill_view(name, path)  → specific file in references/
```

Keep SKILL.md lean. Put heavy reference material in `references/` — it stays at Level 2 until explicitly requested.

## OpenClaw Loading Precedence

| Location | Precedence | Scope |
|---|---|---|
| `<workspace>/skills/` | Highest | Per-agent |
| `<workspace>/.agents/skills/` | High | Per-workspace agent |
| `~/.agents/skills/` | Medium | Shared agent profile |
| `~/.openclaw/skills/` | Medium | Shared (all agents) |
| Bundled | Low | Global |
| `skills.load.extraDirs` | Lowest | Custom shared |

Reload: `/new` in chat or `openclaw gateway restart`.

## Instruction Writing Patterns

**1. Explicit decision trees, not vague instructions.** Write if/then branches for every trigger scenario and every "when NOT to trigger" case. The agent should never guess.

**2. Focused scope.** One skill per pipeline stage (`omnigraph_ingest`, `omnigraph_query`, `omnigraph_synthesize`, `omnigraph_status`, `omnigraph_manage`), not a monolithic skill.

**3. Guard clauses before destructive actions.** Any skill that deletes/overwrites KG data must: show what will change, ask for explicit confirmation, wait for "yes"/"y"/"confirm", and never batch-delete >10 nodes without listing them.

**4. Consistent output formatting.** Define in the skill body: >5 items = markdown table, ≤5 = bullet list, COUNT = plain number, errors = `⚠️ [Type]: [What happened]. [What to do next].`

**5. Environment variables, not hardcoded paths.** Reference env vars by name in the skill body (`GEMINI_API_KEY`, `OMNIGRAPH_DATA_DIR`, `OMNIGRAPH_IMAGE_PORT`).

**6. Skill composition via references.** Skills can't call each other directly. Document dependencies explicitly: "For ingestion, see the `omnigraph_ingest` skill."

## Planned Skills for This Project

| Skill | Description | Triggers |
|---|---|---|
| `omnigraph_ingest` | Ingest a URL into the knowledge graph | "add this to my kb", "ingest", "save this article" |
| `omnigraph_query` | Query the KG by natural language | "what do I know about", "search my kb" |
| `omnigraph_synthesize` | Generate a synthesized report from the KG | "write a report on", "summarize what I know about" |
| `omnigraph_status` | Check pipeline health and graph stats | "kg status", "how many nodes" |
| `omnigraph_manage` | List, delete, or re-index KG entities | "remove entity", "list all tools", "reindex" |

## Testing Skills

- `openclaw agent --message "<trigger phrase>"` exercises the golden path
- Test with missing env vars — guard clause should fire cleanly
- Test destructive actions — confirmation prompt must appear
- Test edge cases (empty result, ambiguous entity) — output format must hold
- `openclaw skills list` to verify skill appears with correct description

## Publishing

```bash
# OpenClaw → ClawHub
openclaw skills publish my-skill --to clawhub

# Hermes → GitHub
hermes skills publish skills/omnigraph-query --to github --repo sztimhdd/OmniGraph-Vault
```

SkillHub reviewers check: metadata correctness, focused scope, guard clauses on destructive ops, references/scripts separation, README.md present.

## Agent-Created Skills (Hermes Self-Improvement)

After 5+ tool calls on a complex task, Hermes evaluates whether to auto-create a skill at `~/.hermes/skills/[category]/`. Let these accumulate during development — they capture real usage patterns. Review periodically and promote good ones to the project skills directory.
