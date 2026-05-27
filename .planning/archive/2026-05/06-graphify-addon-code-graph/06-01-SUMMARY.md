---
plan: 06-01
phase: 06-graphify-addon-code-graph
wave: 2
status: complete
completed: 2026-04-28
---

# Plan 06-01 Summary — graphify skill install on remote

## Outcome: PASS

All three tasks completed inline in main session (SSH checkpoint tasks).

## Task 1.1 — graphify skill install on Hermes

**Commands run on remote:**
```
source ~/OmniGraph-Vault/venv/bin/activate
graphify install --platform hermes
cd ~/OmniGraph-Vault && graphify hermes install
```

**Results:**
- `graphify install --platform hermes` → skill installed at `/home/sztimhdd/.hermes/skills/graphify/SKILL.md` (47359 bytes)
- `graphify hermes install` → section written to `/home/sztimhdd/OmniGraph-Vault/AGENTS.md`
- `hermes skills list | grep -i graphify` → `│ graphify │ │ local │ local │ enabled │`

**REQ-01 status: PASS** — graphify skill functional on Hermes; `hermes skills list` confirms `enabled`.

**REQ-02 status: PARTIAL / DEFERRED** — D-S10 scope = hermes-only (claw binary absent on remote per 06-remote-probe-result.md). OpenClaw install not attempted. Skill file could be written to `~/.openclaw/skills/` best-effort but no CLI verification possible.

## Task 1.2 — Clone T1 repos on remote

**Commands run on remote:**
```
graphify clone https://github.com/openclaw/openclaw \
  --out ~/.hermes/omonigraph-vault/graphify/repos/openclaw/openclaw
graphify clone https://github.com/anthropics/claude-code \
  --out ~/.hermes/omonigraph-vault/graphify/repos/anthropics/claude-code
```

**Results:**
- `~/.hermes/omonigraph-vault/graphify/repos/openclaw/openclaw` — cloned (AGENTS.md, CHANGELOG.md, CLAUDE.md, CONTRIBUTING.md, Dockerfile, ... present)
- `~/.hermes/omonigraph-vault/graphify/repos/anthropics/claude-code` — cloned (CHANGELOG.md, LICENSE.md, README.md, SECURITY.md, Script, ... present)

Both T1 repos ready for Plan 06-02 graph seed.

## Task 1.3 — Commit AGENTS.md locally

**Commit:** `f46a962` — `feat(06-01): add AGENTS.md with graphify rules for Hermes`

AGENTS.md content (from remote via SCP):
```
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer graphify query/path/explain
- After modifying code files in this session, run `graphify update .` to keep graph current
```

## Acceptance Criteria

- [x] `~/.hermes/skills/graphify/SKILL.md` exists on remote (47359 bytes)
- [x] `hermes skills list | grep -i graphify` returns enabled row
- [x] `~/.hermes/omonigraph-vault/graphify/repos/openclaw/openclaw` exists
- [x] `~/.hermes/omonigraph-vault/graphify/repos/anthropics/claude-code` exists
- [x] AGENTS.md committed locally at `f46a962`
- [x] REQ-01: graphify on Hermes — PASS
- [x] REQ-02: graphify on OpenClaw — PARTIAL (hermes-only scope per D-S10; claw absent on remote)

## Notes

- Hermes binary at `~/.local/bin/hermes` (not in non-interactive SSH PATH; added by shell rc)
- Storage path: `~/.hermes/omonigraph-vault/graphify/repos/` (preserves `omonigraph` typo)
- Plan 06-02 next: graph seed via live Hermes session using the T1 repos just cloned
