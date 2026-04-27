---
name: hermes_claude_code_bridge
description: |
  Use this skill when the user wants you to implement a feature, fix a bug, or
  perform a multi-file code change that would benefit from Claude Code's
  autonomous file exploration and deep codebase context. Trigger phrases include:
  "implement X", "fix the bug", "add feature Y", "refactor Z", "rewrite X to use
  Y", "make X work with Y".

  This skill delegates implementation to Claude Code via ACP bridge
  (`delegate_task(acp_command="claude")`). You (Hermes) own orchestration:
  context retrieval from the knowledge graph, diff review, and commit decisions.
  Claude Code owns focused implementation in a single deep session.

  Also covers the **post-hoc push** scenario: the user ran Claude Code
  independently (not via ACP bridge) and asks Hermes to review, stage, commit,
  push, and explain the changes. Trigger phrases for this variant include:
  "帮我推送", "看看他改了啥", "Claude Code finished", "push his changes".

  Do NOT use this skill when: the change is a single-file edit or trivial fix
  (<20 lines) — keep it in Hermes (cheaper, faster). Do NOT use when the task
  touches skills, KG configs, or runs ingest scripts — those are Hermes territory.
  Do NOT use when the task requires user interaction mid-stream (Claude Code
  cannot ask questions).
compatibility: |
  Requires: claude CLI installed and on PATH, ACP bridge configured in Hermes
  (acp_command="claude"). Hermes must have access to git diff, git commit.
  Budget config in ~/.hermes/budget.json (optional, defaults to max-turns=30).
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["claude", "bash"]
      config: []
---
# Hermes-Claude Code Bridge

**Hermes orchestrates, Claude Code implements.**

| Role | Agent | Responsibility |
|------|-------|----------------|
| Orchestrator | Hermes | KG retrieval, context assembly, diff review, commit decision, skill management |
| Implementer | Claude Code (ACP) | Focused multi-file code changes, bug fixes, feature implementation |

## Quick Reference

| Task | Trigger | Action |
|------|---------|--------|
| Implement a feature | "build X", "add Y", "implement Z" | Preflight → delegate → review → commit → push |
| Fix a bug | "fix X", "this is broken", "debug Y" | Preflight → delegate → review → commit → push |
| Refactor | "refactor X", "rewrite Y" | Preflight → delegate → review → commit → push |
| Push Claude Code changes | "帮他推送", "push his changes", "claudecode在改代码" | Status → commit (if needed) → push → review diff |

## When to Use

- Multi-file feature implementation (3+ files touched)
- Bug fixes requiring deep codebase context (e.g., "why does X fail only when Y is null")
- Codebase-wide refactoring (rename patterns, migrate APIs)
- Tasks benefiting from Claude Code's autonomous file exploration (reading adjacent files, running tests)
- **Post-hoc push**: User ran Claude Code independently and asks you to review, commit, push, and explain the diff. Trigger phrases: "帮我推送", "看看他改了啥", "push his changes", "Claudecode在改代码"

## When NOT to Use

- Single-file edits or trivial fixes (<20 lines) → keep in Hermes (cheaper, faster)
- Anything touching skills/, config.py, or knowledge graph operations → Hermes territory
- Tasks requiring user interaction mid-stream → Claude Code in ACP mode cannot ask questions
- Data ingestion (ingest_wechat.py, kg_synthesize.py queries) → use omnigraph_ingest or omnigraph_query
- If the user has NOT explicitly asked for an implementation → ask what they want built first

## Decision Tree

### Step 1 — Scope Check

Before any delegation, validate the task against scope boundaries:

| Check | If fails |
|---|---|
| Does the task touch skills/ or SKILL.md files? | ❌ Refuse. Respond: "⚠️ Skill management is Hermes territory. I'll handle this myself." |
| Does the task touch config.py or .env files? | ❌ Refuse. Respond: "⚠️ Configuration changes stay with me. I'll handle this directly." |
| Does the task run ingest scripts or KG queries? | ❌ Refuse. Respond: "⚠️ Knowledge graph operations are my domain. Use omnigraph_ingest or omnigraph_query instead." |
| Is the task a single-file <20 line edit? | ℹ️ Respond: "This is a small change — I'll handle it directly (faster and cheaper than delegating)." |
| Does the task need user input mid-stream? | ❌ Refuse. Respond: "⚠️ Claude Code in ACP mode cannot ask questions. Let me gather all needed details from you first." |

If all scope checks pass, proceed to Step 2.

### Step 2 — Preflight (Context Assembly)

Run the preflight script to validate environment, load budget config, and assemble context:

```bash
scripts/delegate.sh preflight "<task-description>" "<estimated-complexity>"
```

Where `estimated-complexity` is one of: `low` (simple bugfix, 2-3 files), `medium` (feature, 4-8 files), `high` (refactor/cross-cutting, 9+ files).

The script outputs:
- Budget cap (max-turns) for the delegation
- Scope boundary validation
- A reminder to gather KG context first

**If the preflight fails** (missing `claude` CLI, unset budget, scope violation), fix the issue or abort.

### Step 3 — Context Retrieval

Before delegating, assemble full context. Run these Hermes-native operations:

1. **Knowledge graph lookup**: Run `scripts/delegate.sh context "<task-description>"` to query the KG for relevant past synthesis reports, ingested articles, and entity references.

2. **Read key files**: Use Hermes' file reading tools to read any files the task will touch.

3. **Assemble the delegation prompt**: Combine the KG context + file contents + user's original request into a single goal string.

### Step 4 — Delegate (Guard Rail: Budget Cap)

Invoke Claude Code via ACP bridge:

```python
delegate_task(
    goal="<the assembled goal with full context>",
    context="<KG context + file contents + user request>",
    acp_command="claude",
    acp_args=["--acp", "--stdio", "--max-turns", "<N>"]
)
```

**Budget cap calculation:**

| Complexity | Default max-turns | Override |
|---|---|---|
| `low` | 10 | User can say "take your time" to double |
| `medium` | 20 | User can say "take your time" to double |
| `high` | 30 | User can say "take your time" to double |
| User-specified | Whatever they say | "use max 50 turns" → 50 |

Always announce the budget before delegating:
> "Delegating to Claude Code with max `<N>` turns. Estimated cost: ~`<$X>`. Say 'take 50 turns' or similar to adjust."

### Step 5 — Review (Guard Rail: Review-Before-Commit)

After Claude Code returns:

1. **Read the diff**: Use Hermes' tools to run `git diff` on the changed files.

2. **Present to user** in this format:
   ```
   ## Claude Code completed — here's what changed:
   
   ### Files modified: (count)
   - file1.py — (+X/-Y)
   - file2.py — (+X/-Y)
   
   ### Summary of changes:
   1. [What was done]
   2. [What was done]
   
   ### Diff:
   ```
   (the actual diff)
   ```
   
   Ready to commit? Say "commit" to proceed or "revert" to discard.
   ```

3. **Wait for user confirmation**: Only commit after the user says "yes", "y", "commit", or "confirm". Never auto-commit.

4. **If the user says no or "revert"**: Restore files from git. Do not commit.

### Step 6 — Commit

Run:
```bash
git add <changed-files> && git commit -m "<Hermes-generated message summarizing the change>"
```

Then inform the user: "Committed as `<hash>`. Let me know if you want me to push or make adjustments."

### Step 7 — Skill Update (Optional, Hermes-Only)

If the implemented change introduces a new workflow pattern that Hermes should learn:

1. Check if a skill already covers this pattern
2. If not, offer to the user: "Should I create a skill for this pattern so I can do it faster next time?"
3. If yes, Hermes creates the skill directly (NEVER delegate skill creation to Claude Code)

## Error Handling

| Error | Response |
|-------|----------|
| `claude` CLI not found | "⚠️ Claude Code is not installed. Install it: `npm install -g @anthropic-ai/claude-code`" |
| ACP bridge not configured | "⚠️ ACP bridge not set up. Check your Hermes config for `acp_command`." |
| Preflight check fails (scope) | "⚠️ This task falls outside Claude Code's scope. I'll handle it directly." |
| Claude Code returns error | Show the error to the user. Offer to retry (same or adjusted context) or handle it in Hermes. |
| Claude Code exceeds max-turns | "⏱️ Claude Code hit the turn limit (N turns). The task may be partially done. Show the diff and ask if they want to continue or delegate again." |
| User says "no" to commit | "Changes discarded. I can try a different approach or help you make the change myself." |

## Budget Config

Budget limits are read from `~/.hermes/budget.json` (see `references/guard-rails.md` for schema). If the file does not exist, use the defaults above (10/20/30 turns). Users can override per-task: "use max 50 turns."

## Output Format (When Delegating)

```
🔧 Delegating to Claude Code
   Task: <one-line summary>
   Complexity: low | medium | high
   Budget: <N> turns (est. <$X>)
   Scope: ✅ all checks passed

[Claude Code runs...]

✅ Claude Code completed in <K> turns

## Files changed:
- <file1> (+X/-Y)
- <file2> (+X/-Y)

## Diff:
<git diff output>

Ready to commit? Say "commit" to proceed or "revert" to discard.
```

## Related Skills

- To search the knowledge base for context before delegating: `omnigraph_query`
- To ingest new articles or repos that provide context: `omnigraph_ingest`, `omnigraph_architect`
- To check KG health/stats: `omnigraph_status`
- For parallel independent task dispatch with reviewers: see `subagent-driven-development` (existing general delegation pattern)
