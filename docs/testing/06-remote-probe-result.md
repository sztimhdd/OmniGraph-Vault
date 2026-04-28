# Phase 6 — Remote Probe Result

**Probed:** 2026-04-28

## Binary availability (from `command -v` on remote non-interactive SSH session)

hermes: present (at `~/.local/bin/hermes` — not in non-interactive SSH PATH, but installed and functional in interactive sessions)
claw:   absent

## Directory availability

~/.hermes/skills:   present
~/.openclaw/skills: absent

## Python

/usr/bin/python3

## Repo state

7a89c26 fix(05-00): run multimodal probe before RPM burn [Rule 1]

Note: remote is ahead of local main — has Phase 5 work in progress. Phase 6 scaffold plans not yet synced.

## D-S10 Scope Decision

scope: hermes-only

**Rationale:**
- `hermes` binary is present at `~/.local/bin/hermes` (confirmed with `find` — not visible to `command -v` in non-interactive SSH). Hermes is operational.
- `claw` binary: not found in `~/.local/bin`, `~/.nvm`, `/usr/local` — truly absent.
- `~/.openclaw/skills`: absent — OpenClaw skills directory does not exist.
- Decision rule: `claw: absent` → scope = hermes-only.
- Plan 01 will install `graphify` on Hermes only. REQ-02 (graphify on OpenClaw) is deferred — skill file can be written to `~/.openclaw/skills/` best-effort, but no CLI verification possible until claw is installed.
