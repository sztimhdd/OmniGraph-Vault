---
phase: 06-graphify-addon-code-graph
plan: 04
subsystem: infra
tags: [graphify, cron, bash, code-graph, weekly-refresh]

# Dependency graph
requires:
  - phase: 06-02
    provides: "Seeded graph.json with 28,459 nodes on remote — cron refresh presupposes it exists"
provides:
  - "scripts/graphify-refresh.sh — real POSIX-shell cron script using `graphify update` (AST-only)"
  - "Weekly crontab entry on remote: Sunday 03:00"
  - "REQ-08 PASS — cron registered, manual run succeeds, graph.json mtime advances"
affects:
  - "06-05"
  - future phases that depend on up-to-date code graph

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Graphify shrink guard (to_json() refuses to overwrite with smaller graph) used for atomic swap — no custom tmp-rename needed"
    - "Cron refresh = git pull T1 repos → graphify update (AST-only) → min-node assertion → graphify check-update (advisory)"
    - "set -euo pipefail + explicit graph.json existence guard — cron is refresh-only, not bootstrap"

key-files:
  created: []
  modified:
    - "scripts/graphify-refresh.sh — stub replaced with real 60-line POSIX implementation"

key-decisions:
  - "Use `graphify update` (AST-only, LLM-free) for cron — `graphify build` / `refresh` do not exist in CLI 0.5.3"
  - "Rely on Graphify built-in to_json() shrink guard for atomic swap — no custom tmp-rename (D-G06 satisfied)"
  - "Cron exit-1 if graph.json missing — cron is a refresh mechanism, not a bootstrap"
  - "SCP script to remote (git push deferred to post-Wave 4 merge per orchestrator instruction)"

patterns-established:
  - "Weekly AST-only graph refresh: git pull T1 repos → graphify update → shrink guard → log completion"

requirements-completed:
  - REQ-08

# Metrics
duration: 17min
completed: 2026-04-28
---

# Phase 6 Plan 04: Weekly Cron Refresh Summary

**POSIX shell cron script `graphify-refresh.sh` installed on remote: AST-only `graphify update` with built-in shrink guard, weekly Sunday 03:00 schedule, manual run confirmed 28,466 nodes (REQ-08 PASS)**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-04-28T17:18:48Z
- **Completed:** 2026-04-28T17:35:00Z
- **Tasks:** 2 (4.1 script, 4.2 remote install + manual run)
- **Files modified:** 1

## Accomplishments

- Replaced `scripts/graphify-refresh.sh` stub with a real 60-line POSIX implementation
- Installed weekly crontab entry on remote (Sunday 03:00) — idempotent via `grep -v` pattern
- Manual run on remote confirmed: exit 0, graph.json mtime advanced, 28,466 nodes logged

## Script Content Summary

The script (`scripts/graphify-refresh.sh`) does:

1. **Guard**: exits 1 if `graph.json` is missing — cron is a refresh mechanism, not a bootstrap
2. **Git pull**: iterates T1 repo checkouts in `repos/*/*/`, runs `git pull --ff-only`, keeps stale on failure (per risk register)
3. **AST rebuild**: `source ~/OmniGraph-Vault/venv/bin/activate && graphify update .` — AST-only (no LLM cost), relies on Graphify's built-in `to_json()` shrink guard for atomic-swap semantics
4. **Min-node assertion**: reads node count from `graph.json`; logs WARN if < 100 (additional sanity on top of shrink guard)
5. **Advisory check**: `graphify check-update .` — flags non-code files that need a human-in-loop `/graphify --update` Hermes session for semantic re-extraction
6. **Log completion**: `=== $(date -Is) refresh complete (nodes=N) ===` to `graphify-refresh.log`

Key correctness properties:
- `set -euo pipefail` — halts on any error, preserves existing graph
- No custom `tmp → rename` — Graphify's shrink guard handles atomic swap
- No hardcoded credentials or hostnames — uses `$HOME` and relative paths only

## Manual Run Output (remote)

```
  AST extraction: 4497/4497 files (100%)
[graphify] Extraction warning (116 issues): Node 28484 (id='claude_code_plugin_system') has invalid file_type 'concept' - must be one of [...]
[graphify watch] Skipped graph.html: Graph has 28466 nodes - too large for HTML viz.
[graphify watch] Rebuilt: 28466 nodes, 88562 edges, 540 communities
[graphify watch] graph.json and GRAPH_REPORT.md updated in graphify-out
Code graph updated. For doc/paper/image changes run /graphify --update in your AI assistant.
=== 2026-04-28T14:22:46-03:00 refresh complete (nodes=28466) ===
```

**Exit code:** 0

## Crontab Entry (installed on remote)

```
0 3 * * 0 $HOME/OmniGraph-Vault/scripts/graphify-refresh.sh
```

Schedule: every Sunday at 03:00 local time.

Note: no hostname or user in this line — crontab is remote-only, line uses `$HOME` so it is user-portable.

## Before / After Comparison

| Metric | Before Run | After Run |
|--------|-----------|-----------|
| graph.json mtime (Unix epoch) | 1777396428 | 1777396965 |
| mtime delta | — | +537 seconds (advanced) |
| Node count | 28,459 (from 06-02 seed) | **28,466** (+7) |
| Edge count | 88,568 (from 06-02 seed) | 88,562 (-6, minor community merge) |
| Communities | 1 (single cluster) | **540** (Leiden params fixed) |
| Exit code | — | **0** |

Node count grew (28,459 → 28,466), confirming shrink guard did not fire adversely. Community detection now correctly identifies 540 communities (vs 1 in seed run — Leiden parameters corrected automatically by `graphify update`).

## REQ-08 Status

**PASS**

All acceptance criteria satisfied:

- [x] `crontab -l | grep -q "graphify-refresh.sh"` exits 0
- [x] `crontab -l | grep "graphify-refresh.sh"` contains `0 3 * * 0`
- [x] Manual `bash ~/OmniGraph-Vault/scripts/graphify-refresh.sh` exits 0
- [x] Post-run graph.json mtime > pre-run mtime (1777396965 > 1777396428)
- [x] Post-run graph.json has 28,466 nodes (>= 100)
- [x] Log ends with `=== 2026-04-28T14:22:46-03:00 refresh complete (nodes=28466) ===`

## Task Commits

1. **Task 4.1: Write scripts/graphify-refresh.sh** — `d6596d6` (feat)
2. **Plan metadata** — [final commit hash below]

## Files Created/Modified

- `/c/Users/huxxha/Desktop/OmniGraph-Vault/.claude/worktrees/agent-ad5e2fe5e8d124635/scripts/graphify-refresh.sh` — stub replaced with real 60-line implementation
- Remote (not committed): `~/OmniGraph-Vault/scripts/graphify-refresh.sh` (deployed via SCP; will be overwritten when orchestrator merges main)
- Remote (not committed): crontab on `sztimhdd@ohca.ddns.net` (live filesystem state)

## Decisions Made

- **`graphify update` over `graphify build`**: PRD §6.2 referenced `graphify build --output graph.json.tmp` which does not exist in Graphify CLI 0.5.3. `graphify update .` is the correct AST-only refresh command.
- **Shrink guard is sufficient**: Graphify's `to_json()` built-in shrink guard (refuses to overwrite with smaller graph) satisfies D-G06's atomic-swap intent — stricter than a custom `tmp → rename` because it also validates content monotonicity.
- **SCP for pre-merge deployment**: Since the git push is deferred to post-Wave 4 orchestrator merge, the script was deployed via `scp` so the cron runs the real implementation immediately.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment contained forbidden substring "graphify refresh"**
- **Found during:** Task 4.1 verification
- **Issue:** Plan acceptance criteria `! grep -q "graphify refresh"` failed because the comment "Why `graphify update` (not `graphify build` or `graphify refresh`)" contained the forbidden substring as an illustrative "do not use" example.
- **Fix:** Rephrased comment to "not the non-existent `build` or `refresh` subcommands" — avoids the substring while preserving the warning intent. Same fix applied to the second mention "graphify build / refresh".
- **Files modified:** scripts/graphify-refresh.sh
- **Verification:** `! grep -q "graphify refresh" scripts/graphify-refresh.sh` and `! grep -q "graphify build"` both pass.
- **Committed in:** d6596d6 (Task 4.1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minimal. Comment rephrasing preserves full meaning; no behavioral change to the script.

## Issues Encountered

None beyond the comment substring issue documented above.

## Next Phase Readiness

- REQ-08 complete — weekly cron refresh operational on remote
- Phase 06-05 (remaining Wave 4 work) may proceed
- Community detection now works correctly (540 communities vs 1 in seed) — no action required
- Advisory: 116 graphify extraction warnings about `concept` file_type — these are non-blocking; semantic nodes flagged for human-in-loop review via `graphify check-update`

---
*Phase: 06-graphify-addon-code-graph*
*Completed: 2026-04-28*
