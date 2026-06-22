# Quick 260530-gf1 — Doc Housekeeping (4 issues) — SUMMARY

**Status:** ✅ COMPLETE — 4 commits landed on `main` (NOT pushed; P2-3 still in flight 9 commits ahead).

## What changed

4 file-disjoint doc-tier issues from `.planning/ISSUES.md` cleared in a single quick. Zero behavioral / runtime change. All file targets disjoint with in-flight P2-3 T6 working tree.

| Issue | Severity | Action | Files | Commit |
|---|---|---|---|---|
| #19 | 🔵 Doc | PRINCIPLE #3 wiki cross-link reverse-link exception added | `CLAUDE.md` | `ce59612` |
| #10 | 🟠 P2 | KB_BASE_PATH asymmetry warnings (Databricks root vs Aliyun /kb) | `databricks-deploy/deploy.sh`, `kb/scripts/daily_rebuild.sh` | `1a1e31d` |
| #20 | 🔵 Doc | `databricks-deploy/_ssg/.README.md` build-artifact warning (force-added, gitignored) | `databricks-deploy/_ssg/.README.md` | `758e21b` |
| #12 | 🟠 P2 | Memory v3+v4 merged into combined "systemd Requires= cascade traps (bidirectional)" sub-section | `~/.claude/projects/.../memory/aliyun_drift_recovery_260528_lessons.md` (out-of-tree, no commit) | n/a |

## Per-issue detail

### #19 — CLAUDE.md PRINCIPLE #3 wiki cross-link exception (commit `ce59612`)

PRINCIPLE #3 (Surgical Changes) had no explicit handling for the wiki-cross-link reverse-edit case (when writing a new wiki entity, you also want backlinks `[[your-slug]]` added in other people's wiki pages). 2026-05-29 commit `f5da904` exercised this — wiki agent silently edited other people's wiki files inline; user accepted as a one-off but the lesson never propagated to CLAUDE.md.

Added 4 lines (例外 paragraph + 处理 + 理由 + 参考 line) at the end of PRINCIPLE #3 declaring: reverse-links are a separate-quick scope, current quick only writes its own entity. Reference: 2026-05-29 commit `f5da904`.

### #10 — KB_BASE_PATH asymmetry warnings (commit `1a1e31d`)

Two SSG bake scripts have asymmetric `KB_BASE_PATH` requirements that future readers can easily get wrong:

- `databricks-deploy/deploy.sh` — Databricks Apps serves at root URL, KB_BASE_PATH MUST stay empty (default), HTML emits `/static/*`
- `kb/scripts/daily_rebuild.sh` — Aliyun Caddy serves under `/kb/*` path prefix, KB_BASE_PATH MUST stay `/kb`, HTML emits `/kb/static/*`

2026-05-30 commit `d7b3749` was a hot-fix for exactly this trap (Aliyun deployed with empty default → all CSS/img 404 via Caddy SPA catch-all).

Added a 4-line cross-reference banner comment to each script pointing at the OTHER deploy target and ISSUES.md #10. Comments only — zero behavioral change.

### #20 — _ssg/.README.md build-artifact warning (commit `758e21b`)

`databricks-deploy/_ssg/` is a build artifact regenerated on every `bash deploy.sh` run (Pass 0 `cp -R kb/output ./_ssg/`), but the path looks like committed source. Future readers may edit it and lose work on next deploy.

Wrote `databricks-deploy/_ssg/.README.md` (leading dot — keeps `ls` quiet) explaining: DO NOT EDIT, regen mechanism, hot-patch path (allowed for diagnostic, must be promoted to upstream), permanent fix routes (kb/output / kb/static / kb/templates).

**Force-add note:** root `.gitignore` line 91 has `databricks-deploy/_ssg/`, so `git add -f` was required to track the README. Deploy-time `rm -rf ./databricks-deploy/_ssg` will delete it from the working tree on every deploy run; `git status` will show it as deleted-tracked. `git checkout databricks-deploy/_ssg/.README.md` restores. Acceptable trade-off — README serves fresh-clone readers, post-local-deploy noise is ignorable. No runtime impact (Databricks Apps doesn't serve dotfiles).

### #12 — Memory v3+v4 merge (out-of-tree, no commit)

`~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/aliyun_drift_recovery_260528_lessons.md` Lesson 1 had v1 + v2 (a) + v3 + v2 (b) + v4 — v3 and v4 described the SAME root mechanism (systemd `Requires=` bidirectional cascade) but in two separate sub-sections, making it hard for future readers to recognize they're symmetric.

Merged v3 + v4 into a single "Lesson 1 v3+v4 — systemd `Requires=` cascade traps (bidirectional)" sub-section:

- Single paragraph explains bidirectional cascade (forward: `start TIMER` fires SERVICE; reverse: `stop SERVICE` deactivates TIMER)
- Lean unit template (v4's `[Timer] Unit=` only, no `[Unit] Requires=`) preserved
- Corrected re-arm playbook (v4's 4-step procedure) preserved
- Diagnostic checklist preserved
- Mitigating factor (v3's "no in-flight workload OK to let catch-up complete") preserved
- Observation timeline lists both 2026-05-29 events
- Standalone v4 sub-section replaced with a pointer note ("merged into v3+v4 above") so the file's chronology is still readable

v1 and both v2 instances untouched. Memory file is OUTSIDE the git repo (lives under `~/.claude/projects/...`), so no commit landed for this T4 — the edit is filesystem-only.

## Final commit (this SUMMARY + PLAN + STATE.md)

A 5th commit will land covering `260530-gf1-PLAN.md`, this SUMMARY, and STATE.md "Quick Tasks Completed" row append.

## Constraints all honored

- **A** No edits to `.py` / `.yaml` / `.json` / `kb/static` / `kb/templates` substantive content ✅
- **B** Atomic commits — 4 separate repo commits (one per issue, T4 had no commit since out-of-tree); plus 5th commit for PLAN+SUMMARY+STATE.md ✅
- **C** No push (origin/main HEAD = `cc692e7`, P2-3 in flight 9 commits ahead — wait for P2-3 to complete) ✅
- **D** No edits inside P2-3 working tree (kb/api.py / kg_synthesize.py / kb/services/synthesize.py / kb/api_routers/search.py / requirements.txt / databricks-deploy/requirements.txt / pyproject.toml / tests/eval/* / tests/integration/kb/test_p2_p3_*) ✅ verified via git log per-commit
- **E** Chinese in conversation, simple language ✅

## ISSUES.md update (orchestrator transcribes; agent does not edit ISSUES.md per CLAUDE.md PRINCIPLE #10)

Move from "Open issues" to "Resolved (recent)":

| # | Issue | Resolved | Commit(s) | Quick |
|---|---|---|---|---|
| #19 | CLAUDE.md PRINCIPLE #3 wiki cross-link reverse-link boundary not documented | 2026-05-30 | `ce59612` | `260530-gf1` |
| #10 | KB_BASE_PATH asymmetry between deploy.sh + daily_rebuild.sh undocumented | 2026-05-30 | `1a1e31d` | `260530-gf1` |
| #20 | `databricks-deploy/_ssg/` confusing build-artifact path needs README | 2026-05-30 | `758e21b` | `260530-gf1` |
| #12 | Memory `aliyun_drift_recovery_260528_lessons.md` Lesson 1 v3 + v4 overlap | 2026-05-30 | (out-of-tree memory edit, no commit) | `260530-gf1` |

## Verification

```
$ git log --oneline -5
<filled at commit time>

$ git status -sb
## main...origin/main [ahead 13]
?? .planning/quick/20260525-200047-synthesize-audit/
?? databricks-deploy/_aliyun_pull/
```

(13 ahead = 9 P2-3 + 4 quick commits; .planning/quick/260530-gf1-.../ tracked, _ssg/.README.md tracked. Untracked entries are pre-existing.)

## Out-of-scope / not done

- Did NOT edit `.planning/ISSUES.md` (per user prompt: orchestrator maintains; my SUMMARY transcribes the deltas above)
- Did NOT push (constraint C)
- Did NOT touch any P2-3 file (constraint D)
- Did NOT fix the markdown lint warnings (MD031/MD032) on the memory file — pre-existing style issues outside my edit scope (PRINCIPLE #3 surgical: don't fix unrelated formatting)

## Wall-clock

~12 min total (~3 min recon + ~6 min 4 atomic edits + ~3 min PLAN/SUMMARY/STATE).
