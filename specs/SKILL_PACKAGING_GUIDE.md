# OmniGraph-Vault Skill Packaging Guide

Contributor-facing condensed guide for building SkillHub-ready skills.
Full canonical reference: `.planning/SKILLHUB_REQUIREMENTS.md`

---

## Directory Structure

Every skill is a directory, not a single file:

```
skill-name/
├── SKILL.md              # Required. Frontmatter + instructions (≤500 lines)
├── scripts/              # Shell/Python wrappers the agent executes
├── references/           # Reference docs loaded on demand (heavy content, >300 lines)
├── evals/                # Eval suite
│   └── evals.json
└── assets/               # Optional. Templates, icons, output artifacts
```

**Progressive disclosure:**
- Hermes loads name + description (~100 words) at Level 0 for all skills
- SKILL.md body loads when the skill triggers (Level 1)
- `references/` files load only when SKILL.md explicitly instructs (Level 2)

Keep SKILL.md under 500 lines. Move API docs, full examples, and troubleshooting tables to `references/`.

---

## SKILL.md Format

### Frontmatter

```yaml
---
name: skill-identifier           # snake_case, matches directory name
description: |
  Use this skill when [user action] to [outcome]. Triggers include: "[phrase 1]",
  "[phrase 2]", "[phrase 3]". This skill handles [edge case 1], [edge case 2].
  Do NOT use when [adjacent task 1] — use [other-skill] instead.
  Do NOT use when [adjacent task 2] — leave to agent default.
compatibility: |                  # Optional. Required external services or binaries.
  Requires: GEMINI_API_KEY, Python venv at $OMNIGRAPH_ROOT/venv
---
```

**Description rules (100–200 words):**
- Start with: "Use this skill when [user action] to [outcome]."
- Include 3–5 specific trigger phrases as quoted examples
- Include "This skill handles..." to enumerate edge cases covered
- End with "Do NOT use when..." for 2–3 adjacent tasks with redirects
- Be pushy — Claude tends to undertrigger; explicit "when to use" counters this

### Body Structure

Prefer **Pattern 1: Quick Reference** for skills with repeatable workflows:

```markdown
## Quick Reference

| Task | Trigger | How |
|------|---------|-----|
| Ingest WeChat article | URL + "add to KB" | `scripts/ingest.sh <url>` |
| Ingest PDF | .pdf path | `scripts/ingest.sh <path>` |

## When to Use
[Specific trigger contexts]

## When NOT to Use
[Adjacent tasks + redirect skill names]

## Decision Tree
### Case 1: [condition]
[steps, command, expected output]

### Case 2: [condition]
...

## Error Handling
| Error | Response |
|-------|----------|
...
```

---

## scripts/ — Wrapper Contract

Scripts in `scripts/` are operational entrypoints. For skills that wrap an existing Python pipeline, use shell wrappers.

### Required behaviors

1. **CWD independence** — resolve project root from `OMNIGRAPH_ROOT` env var (never `$(dirname "$0")`):
   ```bash
   OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"
   cd "$OMNIGRAPH_ROOT"
   ```

2. **Env validation before running** — check required vars and exit with human-readable error:
   ```bash
   if [[ -z "${GEMINI_API_KEY:-}" ]]; then
     echo "⚠️ Configuration error: GEMINI_API_KEY is not set." >&2
     echo "   Add it to ~/.hermes/.env and restart." >&2
     exit 1
   fi
   ```

3. **Venv activation** — check both Windows and Unix paths:
   ```bash
   if [[ -f "$OMNIGRAPH_ROOT/venv/Scripts/activate" ]]; then
     source "$OMNIGRAPH_ROOT/venv/Scripts/activate"
   elif [[ -f "$OMNIGRAPH_ROOT/venv/bin/activate" ]]; then
     source "$OMNIGRAPH_ROOT/venv/bin/activate"
   else
     echo "⚠️ Setup error: venv not found. Run: pip install -r requirements.txt" >&2
     exit 1
   fi
   ```

4. **Clean exit codes** — exit 0 on success, exit 1 on error. Never let a Python traceback surface to the user.

5. **Announce before running** — print expected wait time before invoking slow operations:
   ```bash
   echo "Starting ingestion — this may take 30–120 seconds..."
   ```

### For Python scripts with argparse (new scripts, not wrappers)

Use the template at `.planning/SKILLHUB_REQUIREMENTS.md` §11. Key rules:
- Accept paths via `--input`/`--output` flags, not stdin
- Progress to stdout, errors to stderr
- LLM calls through `scripts/llm_interface.py` abstraction
- Document required env vars in module docstring

---

## evals/ — Eval Suite

### evals.json schema

```json
{
  "skill_name": "skill-identifier",
  "evals": [
    {
      "id": 0,
      "name": "descriptive_test_name",
      "prompt": "User message that should trigger the skill and test a specific behavior",
      "expected_output": "Description of what the skill should do/say",
      "files": []
    }
  ]
}
```

**Minimum: ≥3 test cases per skill.** Cover:
1. Golden path (correct trigger + expected behavior)
2. Guard clause (non-matching input → graceful rejection or redirect)
3. Error condition (missing env var, invalid input → human-readable message)

### Assertions in eval_metadata.json (optional, for benchmark viewer)

```json
{
  "eval_id": 0,
  "assertions": [
    {
      "text": "Skill runs ingest script, not query script",
      "passed": true,
      "evidence": "Response contains 'ingest' command, not 'kg_synthesize.py'"
    }
  ]
}
```

Assertions must be objective and verifiable — no "output quality is good."

---

## Anti-Drift: Repo as Source of Truth

**Never copy skill files into `~/.hermes/skills/`.** Hermes should load skills directly from the repo via `skills.external_dirs` configuration.

Correct Hermes config:
```json
{
  "skills": {
    "external_dirs": ["~/Desktop/OmniGraph-Vault/skills"]
  }
}
```

Rationale: Copied skills drift from the repo. Changes in `skills/omnigraph_ingest/SKILL.md` won't reach Hermes until re-copied. Direct loading eliminates this class of bug.

**Before any Hermes deployment, verify:**
```bash
hermes skills list  # must show skills sourced from ~/Desktop/OmniGraph-Vault/skills/
```

---

## Packaging Readiness Checklist

Before committing a skill or opening a PR:

- [ ] `SKILL.md` description is 100–200 words, starts with "Use this skill when..."
- [ ] `SKILL.md` body is ≤500 lines
- [ ] `SKILL.md` has explicit "When NOT to Use" section with redirects
- [ ] `scripts/` wrapper resolves project root from `OMNIGRAPH_ROOT`, activates venv, validates env
- [ ] `scripts/` wrapper announces wait time before slow operations
- [ ] `references/api-surface.md` documents CLI args, env vars, exit codes, error messages
- [ ] `evals/evals.json` has ≥3 test cases covering golden path + guard clause + error
- [ ] No hardcoded paths in any script (use `OMNIGRAPH_ROOT`)
- [ ] `skill_runner.py` tests pass for this skill

---

## Runtime Path Separation

| Path | Purpose |
|------|---------|
| `~/Desktop/OmniGraph-Vault/` | Source repo — skills, scripts, tests |
| `~/.hermes/omonigraph-vault/` | Runtime data — LightRAG index, images, canonical_map.json |

**Note:** The runtime path has a typo (`omonigraph` not `omnigraph`). This is intentional — it is baked into `config.py` and deployed environments. Do not rename.

Scripts always call repo Python scripts (from `$OMNIGRAPH_ROOT`). Runtime data lives under `~/.hermes/omonigraph-vault/` and is never in the repo.
