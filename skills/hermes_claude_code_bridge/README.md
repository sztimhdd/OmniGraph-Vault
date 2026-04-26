# Hermes-Claude Code Bridge

A Hermes skill that delegates complex multi-file implementation tasks to Claude Code via ACP bridge, with guard rails for budget, review, and scope.

## Install

1. Copy this directory to your Hermes skills folder:
   ```bash
   cp -r skills/hermes_claude_code_bridge ~/.hermes/skills/
   ```

2. Make the script executable:
   ```bash
   chmod +x ~/.hermes/skills/hermes_claude_code_bridge/scripts/delegate.sh
   ```

3. Ensure Claude Code CLI is installed:
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

4. (Optional) Configure budget limits:
   ```bash
   cp ~/.hermes/budget.example.json ~/.hermes/budget.json
   # Edit to set your turn and cost limits
   ```

## How It Works

```
User: "Implement a caching layer for the API"
  ↓
Hermes checks scope → ✅ not a skill/config/KG change
  ↓
Hermes runs preflight → budget: 20 turns, scope: clear
  ↓
Hermes queries KG for context → "we use Redis in the stack, see synthesis report..."
  ↓
Hermes delegates: delegate_task(acp_command="claude", --max-turns 20)
  ↓
Claude Code implements → returns summary
  ↓
Hermes shows git diff → user says "commit"
  ↓
Hermes commits
```

## Guard Rails

| Rail | What | How |
|------|------|-----|
| Budget cap | Limit Claude Code turns per task | `--max-turns N` in acp_args |
| Review-before-commit | User approves all changes | Hermes shows `git diff`, waits for "commit" |
| Scope boundaries | Claude Code never touches skills/KG/configs | Preflight validation + post-task diff check |

See `references/guard-rails.md` for full details.

## Budget Config

Create `~/.hermes/budget.json`:
```json
{
  "claude_code_bridge": {
    "default_max_turns": { "low": 10, "medium": 20, "high": 30 },
    "daily_turn_limit": 100,
    "monthly_cost_limit_usd": 50.0
  }
}
```

## Triggers

- "implement X"
- "fix the bug in Y"
- "add feature Z"
- "refactor W"
- "rewrite V to use U"

## Not For

- Single-file edits (<20 lines) → keep in Hermes
- Skill/config/KG changes → Hermes territory
- Ingestion or queries → use omnigraph_ingest / omnigraph_query
