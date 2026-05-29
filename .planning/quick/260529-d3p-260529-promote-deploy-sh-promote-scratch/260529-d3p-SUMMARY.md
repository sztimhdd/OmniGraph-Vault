---
quick_id: 260529-d3p
description: Promote .scratch/deploy_inline_260528.sh to databricks-deploy/deploy.sh, Makefile delegates
status: completed
date: 2026-05-29
commit: c2cfe0c
---

# Quick Task 260529-d3p — Summary

## Outcome

Promoted `.scratch/deploy_inline_260528.sh` to `databricks-deploy/deploy.sh` as the single source of truth. The Makefile `deploy:` target shrunk from 94 lines of bash recipe to a 3-line delegation. `.scratch/` inline removed. One atomic commit on `main`, not pushed.

## What Changed

| File | Change | LoC |
| --- | --- | --- |
| `databricks-deploy/deploy.sh` | NEW (copy of `.scratch/deploy_inline_260528.sh` + reframed header) | +87 |
| `databricks-deploy/Makefile` | `deploy:` target: 94-line recipe → 3-line `bash $(CURDIR)/deploy.sh` delegation | -94 / +6 |
| `.scratch/deploy_inline_260528.sh` | Removed (was untracked, in `.gitignore`) | -93 (untracked) |

Net: 2 tracked files, -94/+93 LoC. Commit `c2cfe0c`.

## Verification

| Must-have | Result |
| --- | --- |
| MH-1: `databricks-deploy/deploy.sh` exists, executable | `-rwxr-xr-x ... 4380 bytes` ✓ |
| MH-2: `bash -n` exits 0 | `OK` ✓ |
| MH-3: `Makefile` `deploy:` is 3-line delegation | confirmed via `grep -A 5 '^deploy:'` ✓ |
| MH-4: 6 other Makefile targets preserved | `deploy-clean / logs / logs-tail / stop / smoke / sp-grants` all present ✓ |
| MH-5: `.scratch/deploy_inline_260528.sh` removed | `ls` returns ENOENT ✓ |
| MH-6: `cd "$(dirname "$0")/.."` resolves to repo root from `databricks-deploy/` | path math identical to `.scratch/X.sh` form (parent of script dir = repo root in both cases) ✓ |
| MH-7: 4 critical `--include` flags preserved | `grep '^\s*--include' deploy.sh` returns 4: `_ssg/**`, `kg_synthesize.py`, `config.py`, `lib/**` ✓ |
| MH-8: Atomic commit on `main`, no push | `c2cfe0c` on `main`, `## main...origin/main [ahead 1]` ✓ |

## Constraint Compliance

| Constraint | Status |
| --- | --- |
| A. Inline byte content unchanged (only path + header rewritten) | ✓ Body of `deploy.sh` from line 17 onwards is byte-identical to former `.scratch/deploy_inline_260528.sh` from its line 23 onwards |
| B. Atomic commit | ✓ One commit `c2cfe0c` covers both files |
| C. No push | ✓ `origin/main` still at `e698cd4`, local `main` is ahead 1 |
| D. Chinese explanations | ✓ Phase narration done in Chinese, artifacts in English |
| E. No `kb/static/` or `kb/templates/` changes | ✓ All changes confined to `databricks-deploy/` |

## Halt Triggers — None Fired

- `bash -n` syntax check passed
- Makefile post-rewrite is 81 lines (well under 200 — no targets accidentally deleted)
- Last P5 deploy WAS using this inline (`.scratch/deploy-inline-20260528-195659.log` confirms deployment ID `01f15aeb208f1cb09400bd1ea9ef4957` matches user-cited `01f15aeb`)

## Why This Matters

Closes the recurring `.scratch/deploy_inline_*.sh` drift problem. Since 2026-05-25:

- 2026-05-25 inline (`.scratch/deploy_inline_260525.sh`) missed 3 `--include` flags → arx-3 singleton REGRESSION → ~28s wall-time per synthesize call (graph reloaded per request)
- 2026-05-27 Makefile fix landed those flags but inline copy was not regenerated
- 2026-05-28 inline (`.scratch/deploy_inline_260528.sh`) was hand-resynced and used for P5 GREEN deploys (`01f15aeb` + `01f15af3`)

Pattern: every drift = manual diff between Makefile and a transient `.scratch/` copy. By owning a single canonical `deploy.sh` and having Makefile delegate, future deploy-recipe changes can ONLY land in one place. Both Windows hosts (no `make`) and Linux hosts (with `make`) execute the same code path.

## Follow-ups (Out of Scope for This Quick)

- None. `deploy-clean:` recursion via `$(MAKE) deploy` continues to work (delegates through to `deploy.sh`).
- User may push when ready: `git push origin main`.

## Lessons / Memory Candidates

Not novel enough for a memory entry — this is bookkeeping to close the .scratch/ drift problem documented in [feedback_no_amend_in_concurrent_quicks.md](../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_no_amend_in_concurrent_quicks.md) and the inline header itself. Single-source-of-truth deploy script is now self-documenting.
