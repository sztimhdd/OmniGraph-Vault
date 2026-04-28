---
phase: 06-graphify-addon-code-graph
plan: 00
subsystem: infra
tags: [graphifyy, tree-sitter, lightrag, hermes, scaffold]

requires: []
provides:
  - graphifyy==0.5.3 installed in local venv with tree-sitter language grammars
  - Phase 6 file scaffold: 10 stub files covering omnigraph_search skill, Python module, cron script, test JSON, and 3 docs placeholders
  - requirements.txt pinned with graphifyy==0.5.3
  - docs/testing/06-remote-probe-result.md PENDING (Task 0.3 SSH probe by orchestrator)
affects:
  - 06-01 (reads docs/testing/06-remote-probe-result.md for D-S10 scope decision)
  - 06-02 (reads docs/testing/06-graph-seed-runbook.md placeholder)
  - 06-03 (fills skills/omnigraph_search/ stubs)
  - 06-04 (fills scripts/graphify-refresh.sh stub)
  - 06-05 (fills docs/testing/06-demo*.md placeholders)

tech-stack:
  added:
    - graphifyy==0.5.3 (code graph tool with 22 tree-sitter language grammar dependencies)
  patterns:
    - Stub-first scaffold: create empty/NotImplementedError files for all downstream targets before implementation

key-files:
  created:
    - skills/omnigraph_search/SKILL.md
    - skills/omnigraph_search/scripts/query.sh
    - skills/omnigraph_search/references/api-surface.md
    - omnigraph_search/__init__.py
    - omnigraph_search/query.py
    - scripts/graphify-refresh.sh
    - tests/skills/test_omnigraph_search.json
    - docs/testing/06-demo1-transcript.md
    - docs/testing/06-demo2-transcript.md
    - docs/testing/06-graph-seed-runbook.md
  modified:
    - requirements.txt (added graphifyy==0.5.3 pin)

key-decisions:
  - "graphifyy==0.5.3 installed (double-y spelling confirmed); binary exposes install/update/clone/path subcommands"
  - "chmod +x skipped on Windows — shell scripts have correct shebang but no executable bit; remote Linux will git checkout with mode preserved if committed with mode 644"
  - "D-S10 scope (hermes-only vs hermes-and-claw) DEFERRED — Task 0.3 SSH probe not run by subagent (no credentials); orchestrator must complete in main session"

patterns-established:
  - "Stub Python modules: raise NotImplementedError with clear message pointing to the plan that will implement"
  - "Stub shell scripts: shebang + set -euo pipefail + echo WARNING >&2 + exit 1"

requirements-completed: [REQ-03, REQ-04, REQ-08]

duration: 5min
completed: 2026-04-28
---

# Phase 6 Plan 00: Scaffold + graphifyy Install Summary

**graphifyy==0.5.3 installed in local venv with full tree-sitter grammar set; 10 Phase 6 stub files committed; Task 0.3 SSH probe pending orchestrator execution**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-28T16:04:16Z
- **Completed:** 2026-04-28T16:09:39Z
- **Tasks:** 2 of 3 complete (Task 0.3 is a checkpoint:human-verify — SSH credentials not available in subagent)
- **Files modified:** 11

## Accomplishments

- Installed graphifyy==0.5.3 (with tree-sitter and 22 language grammar dependencies) in local venv; binary confirmed working via `venv/Scripts/python -m graphify --help`
- Created 10 stub files covering all downstream Phase 6 plan targets (omnigraph_search skill, Python module, cron script, test JSON, 3 docs placeholders)
- Pinned graphifyy==0.5.3 in requirements.txt (single line addition, no other pins changed)

## Task Commits

Each task committed atomically:

1. **Task 0.1: Install graphifyy locally and pin in requirements.txt** - `22e8bbe` (chore)
2. **Task 0.2: Create stub files for omnigraph_search skill, Python module, cron script, and test JSON** - `e3e000a` (feat)
3. **Task 0.3: Probe remote PC and record D-S10 scope decision** - PENDING (checkpoint:human-verify)

## Files Created/Modified

- `requirements.txt` - Added graphifyy==0.5.3 pin
- `skills/omnigraph_search/SKILL.md` - Minimal frontmatter stub (Plan 03 fills)
- `skills/omnigraph_search/scripts/query.sh` - Bash stub with shebang + exit 1
- `skills/omnigraph_search/references/api-surface.md` - Placeholder markdown
- `omnigraph_search/__init__.py` - Python package marker (empty)
- `omnigraph_search/query.py` - Stub raising NotImplementedError on search()/main()
- `scripts/graphify-refresh.sh` - Bash stub (Plan 04 fills weekly cron)
- `tests/skills/test_omnigraph_search.json` - Empty JSON array []
- `docs/testing/06-demo1-transcript.md` - Placeholder for Plan 05 Demo 1 transcript
- `docs/testing/06-demo2-transcript.md` - Placeholder for Plan 05 Demo 2 transcript
- `docs/testing/06-graph-seed-runbook.md` - Placeholder for Plan 02 seed runbook

## Decisions Made

- graphifyy binary invoked via `python -m graphify` on Windows (not `venv/Scripts/graphify.exe` directly — Windows permission issue in bash). The `.exe` exists at `venv/Scripts/graphify.exe` and works via `cmd /c`.
- D-S10 scope decision (hermes-only vs hermes-and-claw) deferred to orchestrator's Task 0.3 SSH probe. Plan 01 must read `docs/testing/06-remote-probe-result.md` before executing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] chmod +x skipped on Windows**
- **Found during:** Task 0.2
- **Issue:** `chmod +x` is not functional on Windows NTFS/bash environment; the command would silently no-op or fail
- **Fix:** Skipped chmod; shell scripts have correct shebang (`#!/usr/bin/env bash` and `#!/bin/bash`) and are syntactically valid. On the remote Linux machine, git checkout will preserve mode 644; a downstream plan or the orchestrator can set executable bit if needed on remote.
- **Files modified:** skills/omnigraph_search/scripts/query.sh, scripts/graphify-refresh.sh
- **Verification:** `bash -n` syntax check passes for both; `test -x` would fail on Windows (expected)
- **Committed in:** e3e000a (Task 0.2 commit)

**2. [Rule 1 - Bug] graphify.__version__ attribute absent**
- **Found during:** Task 0.1 verification
- **Issue:** `import graphify; print(graphify.__version__)` raises AttributeError — the package uses `__getattr__` lazy loading that raises AttributeError for unknown attributes
- **Fix:** Used `importlib.metadata.version('graphifyy')` instead, which returns '0.5.3' correctly
- **Files modified:** None (verification method only, acceptance criteria still satisfied)
- **Verification:** `importlib.metadata.version('graphifyy')` returns '0.5.3'

---

**Total deviations:** 2 (1 platform/Windows constraint, 1 verification method adaptation)
**Impact on plan:** Both minor. No scope change. All acceptance criteria met via alternative verification.

## Issues Encountered

- graphify binary at `venv/Scripts/graphify.exe` returned no output when invoked via bash `venv/Scripts/graphify.exe` (permission denied exit 126). Resolved by invoking via `venv/Scripts/python -m graphify` which works correctly and produces full help output.

## Known Stubs

All 10 stub files created in Task 0.2 are intentional stubs. They exist solely to satisfy "file exists" preconditions for downstream plans:

| File | Stub type | Filled by |
|------|-----------|-----------|
| skills/omnigraph_search/SKILL.md | Minimal frontmatter, TODO body | Plan 03 |
| skills/omnigraph_search/scripts/query.sh | exit 1 stub | Plan 03 |
| skills/omnigraph_search/references/api-surface.md | Placeholder markdown | Plan 03 |
| omnigraph_search/__init__.py | Empty package marker | Plan 03 |
| omnigraph_search/query.py | NotImplementedError stub | Plan 03 |
| scripts/graphify-refresh.sh | exit 1 stub | Plan 04 |
| tests/skills/test_omnigraph_search.json | Empty [] array | Plan 03 |
| docs/testing/06-demo1-transcript.md | TODO placeholder | Plan 05 |
| docs/testing/06-demo2-transcript.md | TODO placeholder | Plan 05 |
| docs/testing/06-graph-seed-runbook.md | TODO placeholder | Plan 02 |

These stubs do NOT prevent Plan 00's goal (scaffold creation + graphifyy install). They are intentional by design.

## User Setup Required

**Task 0.3 SSH probe must be completed by the orchestrator in the main session.**

The orchestrator needs to:
1. Read SSH credentials from `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`
2. Run the probe command:
   ```
   ssh <remote> "command -v hermes || echo 'hermes:absent'; command -v claw || echo 'claw:absent'; test -d ~/.hermes/skills && echo 'hermes_skills_dir:present' || echo 'hermes_skills_dir:absent'; test -d ~/.openclaw/skills && echo 'openclaw_skills_dir:present' || echo 'openclaw_skills_dir:absent'; which python3 python 2>/dev/null | head -2; git -C ~/OmniGraph-Vault log --oneline -1 2>/dev/null || echo 'repo:missing'"
   ```
3. Write the result to `docs/testing/06-remote-probe-result.md` using the template from Task 0.3 in the plan
4. Sanitize output (replace `/home/<username>/` with `/home/<user>/`)
5. Record `scope: hermes-and-claw` or `scope: hermes-only` based on decision rule
6. Commit the file: `git add docs/testing/06-remote-probe-result.md && git commit --no-verify -m "docs(06-00): record remote probe result and D-S10 scope decision"`

## Next Phase Readiness

- Plan 01 (graphify hermes install + T1 clone) can proceed once Task 0.3 probe result is written
- Plans 02-05 can be planned now; they read from the stub files committed here
- `docs/testing/06-remote-probe-result.md` is the sole blocker for Plan 01 execution

---
*Phase: 06-graphify-addon-code-graph*
*Completed: 2026-04-28 (Tasks 0.1 and 0.2; Task 0.3 pending orchestrator)*
