# Technology Stack: Hermes Agent Skill Packaging

**Project:** OmniGraph-Vault — Phase 2 (Skill Packaging)
**Researched:** 2026-04-21
**Confidence:** MEDIUM — Official Hermes/OpenClaw docs unreachable from this endpoint (Cisco Umbrella proxy
blocks external fetches). All skill interface findings are sourced from: (a) CLAUDE.md skill writing
standards section (synthesized from those docs by the project author), (b) the project README's canonical
subprocess integration example, (c) direct codebase analysis of the scripts being wrapped.
External docs cited in CLAUDE.md: hermes-agent.ai, docs.openclaw.ai, lushbinary.com, dench.com,
hermes-agent.nousresearch.com — all returned connection errors. Standards below treat CLAUDE.md as the
authoritative source since it was written from those docs.

---

## Recommended Stack for Phase 2

### Skill Interface Layer

| Component | Technology | Purpose | Rationale |
|-----------|------------|---------|-----------|
| Invocation mechanism | `subprocess.run()` | Agent calls Python CLI scripts | Confirmed by README integration snippet and PROJECT.md; subprocess is the stated interface |
| Shell wrapper | `scripts/run-*.sh` | Entry point the agent actually executes | SKILL.md `scripts/` convention; shell indirection gives venv activation + cwd control |
| Frontmatter format | YAML in `SKILL.md` | Agent metadata, trigger phrases, requirements | Hermes/OpenClaw skill loading spec (per CLAUDE.md) |
| Skill directory | One dir per skill | `SKILL.md` + `references/` + `scripts/` | Stated directory structure from CLAUDE.md skill standards |
| Test harness | `skill_runner.py` (local) | Simulate agent loading SKILL.md + running test cases | Specified in PROJECT.md active requirements |

### Script Invocation: subprocess via shell wrapper

The agent does NOT call Python directly. The pattern is:

```
SKILL.md body instructs agent
  → agent executes scripts/run-query.sh (via exec)
    → shell script: cd to project root, activate venv, call python script
      → python script: reads args, runs pipeline, writes stdout
        → agent captures stdout as response
```

**Why shell wrapper over direct python call:**

- Venv activation (`venv/Scripts/activate` on Windows, `venv/bin/activate` on Linux/macOS) cannot be
  done in a single exec call — it requires a shell sourcing step.
- Working directory must be the project root (scripts do relative imports of `config.py`).
- Shell wrapper abstracts platform differences (Windows uses `venv\Scripts\python`, Linux uses
  `venv/bin/python`).
- The `scripts/` directory in a skill is for shell scripts, not Python modules (per CLAUDE.md convention:
  "scripts/ = scripts the agent runs. Never mix [with references/]").

### SKILL.md Frontmatter (Authoritative Format)

```yaml
---
name: omnigraph_ingest          # snake_case, globally unique, required
description: >-                 # one-line, shown at Level 0 — must be accurate, fits ~80 chars
  Ingest a WeChat article URL or PDF path into the OmniGraph knowledge graph.
triggers:                       # Hermes phrase-matching for auto-dispatch
  - "add this to my kb"
  - "ingest"
  - "save this article"
  - "add to knowledge base"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---
```

Required fields: `name`, `description`.
Optional but high-impact: `triggers` (auto-dispatch), `metadata.openclaw.requires` (pre-flight checks).

### Environment Variable Handling in Skills

Skills reference env vars by name in the SKILL.md body — they never hardcode values. The resolution chain:

1. `~/.hermes/.env` — loaded by `config.py` at script import time (already implemented)
2. `metadata.openclaw.requires.config` — Hermes pre-flight check; skill body says "ensure GEMINI_API_KEY
   is set before calling the script"
3. Shell wrapper script checks the variable explicitly and exits with a descriptive error if missing

```bash
# scripts/run-ingest.sh pattern
#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

# Pre-flight: required env vars
if [ -z "$GEMINI_API_KEY" ]; then
  echo "ERROR: GEMINI_API_KEY is not set. Set it in ~/.hermes/.env or your shell environment." >&2
  exit 1
fi

# Activate venv (cross-platform: try both paths)
if [ -f "venv/Scripts/activate" ]; then
  source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "ERROR: Python venv not found. Run: python -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi

python ingest_wechat.py "$1"
```

### Error Surfacing: Script Failures to the Agent

The agent reads stdout and stderr. Exit code signals success/failure. Pattern:

| Signal | Meaning | Agent behavior |
|--------|---------|----------------|
| exit 0 + stdout content | Success | Present stdout to user |
| exit 0 + empty stdout | Ambiguous success | Agent should note "no output" |
| exit 1 + stderr message | Script-level error | Agent surfaces stderr as error context |
| exit 1 + stdout traceback | Python exception | Agent surfaces last stdout line as error |

**How the existing scripts signal errors** (verified from codebase):
- `kg_synthesize.py`: prints `"Error: GEMINI_API_KEY not found."` then `sys.exit(1)` — clean
- `kg_synthesize.py`: on query failure, prints traceback via `traceback.print_exc()` then `sys.exit(1)`
- `ingest_wechat.py`: prints `"Import error: {e}"` then `sys.exit(1)` on import failure
- All scripts use `print()` for user-facing output (not `logging`) — stdout is the response channel

**SKILL.md body instructs the agent how to interpret outputs:**

```markdown
## Error Handling

If the script exits with a non-zero code:
- Check stderr first for a clean error message.
- If stderr is empty, the last line of stdout contains the Python exception.
- Surface to the user as: ⚠️ [ErrorType]: [message]. [remediation step].

Common errors and remediations:
- "GEMINI_API_KEY not found" → Ask user to add key to ~/.hermes/.env
- "Import error: No module named lightrag" → Run: pip install -r requirements.txt
- "CDP connection refused" → Start Edge with: --remote-debugging-port=9223
- "Query attempt 3 failed" → Gemini API quota or rate limit; wait 60s and retry
```

### Progressive Disclosure Structure

```
Level 0: skills_list()     → name + description (~5 tokens per skill)
Level 1: skill_view(name)  → full SKILL.md (decision tree, error handling, examples)
Level 2: skill_view(name, "references/api-surface.md")  → script args, output format details
```

Keep `SKILL.md` under ~150 lines. Long reference material (full argument tables, output schema) goes in
`references/`.

---

## Skill Directory Structure (Per Skill)

```
skills/
├── omnigraph-ingest/
│   ├── SKILL.md              # Agent instructions + frontmatter (required)
│   ├── scripts/
│   │   └── run-ingest.sh     # Shell wrapper the agent executes
│   ├── references/
│   │   └── api-surface.md    # Script args, output format, modes, examples
│   └── README.md             # Human-facing: install, test, publish
│
└── omnigraph-query/
    ├── SKILL.md
    ├── scripts/
    │   └── run-query.sh
    ├── references/
    │   └── api-surface.md
    └── README.md
```

Placement in this repo: `skills/` at project root (highest OpenClaw precedence: `<workspace>/skills/`).

---

## Alternatives Considered

| Decision | Chosen | Alternative | Why Not |
|----------|--------|-------------|---------|
| Script invocation | Shell wrapper → python | Direct `python ingest_wechat.py` from agent | No venv activation possible without shell; cwd not guaranteed |
| Single monolithic skill | Two focused skills (ingest + query) | One `omnigraph` skill | Clearer intent mapping, independent testing, matches PROJECT.md decision |
| Error format | Plain text stderr + exit code | Structured JSON on stdout | Hermes reads stdout as free text; JSON adds parsing complexity with no benefit |
| Env var loading | `config.py` loads `~/.hermes/.env` (already implemented) | Skill sets vars before call | Config.py handles it at import; shell wrapper only needs the pre-flight check |
| venv path | Check both `venv/Scripts/` and `venv/bin/` | Hardcode one | Windows uses Scripts/, Linux/macOS uses bin/ — same repo, cross-platform |

---

## Supporting Files Required

### `skill_runner.py` (local test harness)

Specified in PROJECT.md. Loads `SKILL.md` as system prompt, runs test case JSON files against the same
Gemini backend Hermes uses, without requiring a Hermes install. This is the primary validation path before
Gate 7.

```
tests/skills/
├── test_omnigraph_ingest.json    # trigger phrases, guard clauses, expected outputs
└── test_omnigraph_query.json     # trigger phrases, output format, wrong-skill redirects
```

### Pre-flight fix required: `kg_synthesize.py` missing `import json`

The codebase analysis found a confirmed bug: `kg_synthesize.py` uses `json.load()` at line 54 but does
not import `json`. This will cause `NameError: name 'json' is not defined` once `canonical_map.json`
exists (i.e., after any ingestion run). Fix this before packaging the skill.

### Pre-flight fix recommended: hardcoded paths in multiple scripts

Multiple scripts use `/home/sztimhdd/OmniGraph-Vault/...` instead of `config.py` constants. Specifically:
- `kg_synthesize.py` line 50: `canonical_map.json` path
- `ingest_wechat.py` lines 279, 280, 368: `entity_buffer` path
- `cognee_batch_processor.py` lines 9, 30, 35, 36: log file and buffer paths

These will silently fail on Windows (path doesn't exist) unless the shell wrapper sets `PROJECT_ROOT` and
the scripts are fixed to use `config.py` constants. Fix as part of skill packaging.

---

## Installation / Deployment

```bash
# Skills available immediately at workspace/skills/ — no install command needed
# OpenClaw/Hermes picks them up at /new or gateway restart

# Verify skill appears:
openclaw skills list
# or
hermes skills list

# Test individual skill:
openclaw agent --message "add this article to my kb: https://mp.weixin.qq.com/s/..."
```

---

## Sources

- CLAUDE.md (project), section "OpenClaw / Hermes Skill Writing Standards" — synthesized from
  hermes-agent.ai, docs.openclaw.ai, lushbinary.com, dench.com, hermes-agent.nousresearch.com
  (MEDIUM confidence — original URLs unreachable, CLAUDE.md treated as authoritative proxy)
- README.md integration snippet — subprocess pattern, confirmed (HIGH confidence — in-repo)
- PROJECT.md — subprocess interface stated as design decision (HIGH confidence — in-repo)
- ARCHITECTURE.md (codebase) — entry points, stdout conventions confirmed (HIGH confidence — codebase analysis)
- CONVENTIONS.md (codebase) — error handling patterns, exit codes (HIGH confidence — codebase analysis)
- CONCERNS.md (codebase) — hardcoded path issues and `import json` bug (HIGH confidence — codebase analysis)
- kg_synthesize.py lines 11-13, 89-103 — exit code and stdout conventions (HIGH confidence — source code)
- ingest_wechat.py lines 20-27 — import error pattern (HIGH confidence — source code)
