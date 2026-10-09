# Guard Rails for Hermes-Claude Code Bridge

## 1. Budget Cap

### Configuration

Budget limits are stored in `~/.hermes/budget.json`:

```json
{
  "claude_code_bridge": {
    "default_max_turns": {
      "low": 10,
      "medium": 20,
      "high": 30
    },
    "daily_turn_limit": 100,
    "monthly_cost_limit_usd": 50.0
  }
}
```

### How It Works

- `max-turns` is passed to Claude Code as `--max-turns N` in `acp_args`
- Claude Code counts each tool invocation as one turn
- Hermes tracks total turns used per day (sum across all delegations)
- If daily_turn_limit is exceeded, Hermes refuses further delegations and tells the user

### Per-Task Override

Users can override the budget inline:
- "use max 5 turns" → sets max_turns=5 regardless of complexity
- "take your time" / "no budget limit" → doubles the default
- "I'll pay whatever" → triples the default

### Cost Estimation

| Model (Claude Code default) | $/turn (approximate) |
|---|---|
| Sonnet 4.5 | ~$0.15–0.30 |
| Opus 4 | ~$1.50–3.00 |

Hermes announces estimated cost before delegating:
> "Delegating with max 20 turns. Estimated cost: ~$3–6. Say 'use max 50' to adjust."

## 2. Review-Before-Commit

### Why This Exists

Claude Code can implement anything. The user stays the reviewer. Hermes is the gatekeeper.

### Flow

```
Claude Code returns → Hermes runs git diff → Hermes presents diff to user
                                                    ↓
                                         User says "commit"
                                                    ↓
                                         Hermes runs git commit
```

### What Hermes Reviews

1. **File count and scope** — did Claude Code touch more files than expected?
2. **Diff size** — is the change proportionate to the task?
3. **Skill/config boundary violation** — did Claude Code touch anything in skills/ or config.py? If yes, REVERT immediately.
4. **Test/verification** — did the change include tests or at least a verification command?

### What the User Sees

```
## Claude Code completed — here's what changed:

### Files modified: 3
- src/parser.py (+45/-12)
- src/models.py (+23/-0)
- tests/test_parser.py (+67/-0)

### Summary:
1. Added new AST node type for async generators
2. Updated parser combinator to handle yield expressions
3. Added 12 test cases covering edge cases

### Diff:
+++ src/parser.py
...

Ready to commit? Say "commit" to proceed or "revert" to discard.
```

### Boundary Violation Handling

If Hermes detects that Claude Code modified a forbidden area:
```
⚠️ Boundary violation detected:
   Claude Code modified skills/ (FORBIDDEN zone)
   Changes reverted automatically.
   
   I'll handle this myself or we can redelegate with stricter instructions.
```

## 3. Scope Boundaries

### Hermes Territory (Claude Code MUST NOT touch)

| Zone | Files/Dirs | Reason |
|------|------------|--------|
| Skills | `skills/` | Hermes manages its own skills; skills define Hermes' behavior |
| Configuration | `config.py`, `.env` files, `~/.hermes/` | Environment and secrets are Hermes-managed |
| Knowledge Graph | `kg_synthesize.py`, `query_lightrag.py`, `ingest_wechat.py`, `cognee_wrapper.py`, `cognee_batch_processor.py` | KG operations are Hermes' core domain |
| Data stores | `lightrag_storage/`, `entity_buffer/`, `canonical_map.json` | Never modify KG data via Claude Code |
| Planning docs | `.planning/` | Planning is Hermes' domain; Claude Code implements, not decides |

### Claude Code Territory (free to modify)

| Zone | Files/Dirs | Reason |
|------|------------|--------|
| Source code | `src/`, `lib/`, `*.py` (non-KG) | Implementation code |
| Tests | `tests/`, `test_*.py`, `*_test.py` | Claude Code can and should write tests |
| Spiders | `spiders/` | Web scraping logic (not the ingest pipeline) |
| Documentation | `README.md`, `docs/` (non-KG) | Claude Code can update docs |
| Config schemas | `*.json` (non-KG, non-secret) | Schema files, type definitions |

### Ambiguous Cases

If it's unclear whether a file is in Claude Code's scope:
1. **Default to Hermes** — if in doubt, keep it in Hermes
2. **Ask the user** — "Should Claude Code modify `<file>`? It's a config-adjacent file."
3. **Split the task** — Hermes handles the KG/config parts, Claude Code handles the implementation
