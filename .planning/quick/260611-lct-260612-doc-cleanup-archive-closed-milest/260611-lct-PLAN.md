---
phase: quick-260611-lct
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/*-Agentic-RAG-v1.md
  - .planning/*-Aliyun-Ingest-Migration-v1.md
  - .planning/*-kb-databricks-v1.md
  - .planning/MILESTONE_*.md
  - .planning/MILESTONE-v1.0.y.md
  - .planning/ROADMAP.md
  - .planning/ARCHITECTURE-*-Ingest-Pipeline-v1.md
  - .planning/REQUIREMENTS.md
  - .planning/STATE.md
  - .planning/quick/{2026-05 dirs}
  - .planning/archive/closed-milestones/
  - .planning/archive/quick-2026-05/
autonomous: true
requirements: [HOUSEKEEPING]
---

<objective>
Archive closed-milestone planning docs + stale 2026-05 quick dirs to `.planning/archive/`, fix STATE.md stale frontmatter/Current-Position drift, leave a clean active `.planning/` workspace. PURE housekeeping — zero touches outside `.planning/`, zero runtime/code change. All moves via `git mv` to preserve history.

Purpose: `.planning/` has 40 root .md files + 45 quick dirs, many from CLOSED milestones cluttering the active workspace. Reduce root to ~23 .md files, move ~28 stale 2026-05 quick dirs to archive, fix STATE.md milestone/focus/position drift to 2026-06-12 reality.

Output: ~16 root .md files moved to `.planning/archive/closed-milestones/`, ~29 quick dirs moved to `.planning/archive/quick-2026-05/`, 2 archive README index files, STATE.md frontmatter + Current Position rewritten, broken-ref grep clean, single forward-only commit pushed to origin/main.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/ISSUES.md
@.planning/STATE.md
@CLAUDE.md

<facts>
Mirror these verified facts (from ISSUES.md + STATE.md, 2026-06-12) when rewriting STATE.md — invent NOTHING:

- Closed milestones (no active phase in flight): Agentic-RAG-v1 (closed 2026-05-24, superseded by v1.1), Aliyun-Ingest-Migration-v1 (closed 2026-05-25), kb-databricks-v1 / kdb (closed 2026-05-20), v1.0.y (closed 2026-05-17), v3.4 (closed 2026-05-09).
- Active/canonical PROJECT lines: KB-v2 (Bilingual Agent-Tech Content Site), Agentic-RAG-v1.1, Ingest-Refactor-v3.5 (a.k.a. v3.5-Ingest-Refactor).
- Most recent activity (last_activity / last_updated already current): 2026-06-11/12 — quick 260611-hl6 (260612-spike-native-parallel-insert) CLOSED: native `ainsert(list, max_parallel_insert=4)` is deadlock-safe but only ~1.27-1.31x speedup < 1.4x threshold → ISSUES #40 VERDICT BLOCKED, v1.2 concurrent-ingest research thread CLOSED (all paths measured). Prior: 260610-rgm 4-issue cluster ACCEPTED (#45/#47/#48/#29 → Resolved R29-R32), #49 filed.
- No active phase EXECUTING as of 2026-06-12. The STATE "Current focus: Phase kdb-1.5" + "Current Position: kdb-1.5 EXECUTING" + "KB-v2 1 of 3 phases complete" are STALE.
- Next-candidate options (do NOT pick one — list them): kb-2 (KB entity/topic pages — revived, not started) OR arx-2 (Deep Research API) OR ir-3 audit (overdue v3.5 closure). ISSUES #40 alternatives for batch concurrency: (a) parallel systemd services, (b) ProcessPoolExecutor, (c) raise MAX_ARTICLES + denser cron.
</facts>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pre-flight cross-ref verify + archive Set A (closed-milestone root docs)</name>
  <files>
  .planning/archive/closed-milestones/ (new dir)
  .planning/*-Agentic-RAG-v1.md, .planning/*-Aliyun-Ingest-Migration-v1.md, .planning/*-kb-databricks-v1.md,
  .planning/MILESTONE_v3.1_MORNING_SUMMARY.md, .planning/MILESTONE_v3.2_PLAN_PHASE_PROMPT.md, .planning/MILESTONE_v3.2_REQUIREMENTS.md,
  .planning/MILESTONE_v3.3_REQUIREMENTS.md, .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md, .planning/MILESTONE-v1.0.y.md,
  .planning/ROADMAP.md, .planning/ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md, .planning/ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md,
  .planning/REQUIREMENTS.md (KEEP candidate — header note only)
  </files>
  <action>
  STEP 1 — ENUMERATE actual files (do NOT trust a hardcoded list; the milestone glob filenames must be discovered live):
    `ls -1 .planning/*.md`
  Build the candidate Set A from these intent groups (match against the live `ls`):
    - All `*-Agentic-RAG-v1.md` (PROJECT / REQUIREMENTS / ROADMAP / STATE — 4 files; NOT the `-v1.1` variants which are KEPT)
    - All `*-Aliyun-Ingest-Migration-v1.md` (4 files)
    - All `*-kb-databricks-v1.md` (4 files)
    - `MILESTONE_v3.1_MORNING_SUMMARY.md`, `MILESTONE_v3.2_PLAN_PHASE_PROMPT.md`, `MILESTONE_v3.2_REQUIREMENTS.md`, `MILESTONE_v3.3_REQUIREMENTS.md`, `MILESTONE_Agentic-RAG-v1_AUDIT.md`
    - `MILESTONE-v1.0.y.md`
    - `ROADMAP.md` (the ROOT bare one — NOT any `ROADMAP-*.md` suffix variant)
    - `ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md`, `ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md`

  STEP 2 — PRE-FLIGHT cross-ref guard. For EACH candidate filename, confirm it is NOT cited as authoritative by an ACTIVE doc:
    `grep -rl "<filename>" .planning/PROJECT-KB-v2.md .planning/PROJECT-Agentic-RAG-v1.1.md .planning/PROJECT-Ingest-Refactor-v3.5.md .planning/PROJECT-v3.5-Ingest-Refactor.md .planning/STATE.md CLAUDE.md README.md 2>/dev/null`
    - If a candidate is referenced by an active doc → DO NOT move it. Instead KEEP it in `.planning/` and prepend a one-line header note: `> CLOSED <closed-date>, retained for cross-ref by <active-doc>.` Record it in SUMMARY as "kept-with-note".
    - KNOWN CASE: `REQUIREMENTS.md` (v3.4 closed, but KB-v2/aim PROJECTs cite it) — KEEP, add header note `> CLOSED 2026-05-09 (v3.4), retained — KB-v2 / aim PROJECTs cross-reference it.` Do NOT move REQUIREMENTS.md.
    - For `ROADMAP.md` (root): grep specifically to confirm nothing treats it as the live roadmap (suffix `ROADMAP-*.md` files are the live ones). If clean → archive it; if an active doc points at bare `ROADMAP.md` → keep-with-note instead.

  STEP 3 — Create archive dir + move confirmed Set A files via `git mv` (preserve history; NEVER rm + recreate):
    `mkdir -p .planning/archive/closed-milestones`
    For each CONFIRMED-MOVABLE file: `git mv .planning/<file> .planning/archive/closed-milestones/<file>`

  Report in SUMMARY: count moved, list of any kept-with-note (incl. REQUIREMENTS.md), and the exact filename set discovered.
  </action>
  <verify>
  - `ls -1 .planning/archive/closed-milestones/*.md | wc -l` ≥ 14 (≈16 expected: 12 suffix + 5 MILESTONE + ROADMAP + 2 ARCHITECTURE, minus any kept-with-note)
  - `git status --porcelain | grep '^R' | wc -l` shows renames (git mv tracked, NOT delete+add)
  - `.planning/REQUIREMENTS.md` still exists in `.planning/` (NOT moved) and its first line is the CLOSED header note
  - No file moved that grep flagged as active-referenced
  </verify>
  <done>Confirmed Set A files in `.planning/archive/closed-milestones/`; kept-with-note files (incl. REQUIREMENTS.md) annotated and still in `.planning/`; all moves are git renames.</done>
</task>

<task type="auto">
  <name>Task 2: Archive Set B (stale 2026-05 quick dirs) + write both archive READMEs</name>
  <files>
  .planning/archive/quick-2026-05/ (new dir)
  .planning/quick/{260517-* .. 260530-* dirs}, .planning/quick/20260529-wiki-copilot-studio
  .planning/archive/closed-milestones/README.md (new)
  .planning/archive/quick-2026-05/README.md (new)
  </files>
  <action>
  STEP 1 — ENUMERATE quick dirs live (do NOT hardcode):
    `ls -1d .planning/quick/*/`
  Build Set B = every quick dir whose name has a 2026-05 date prefix:
    - Prefix `2605` followed by month `17`..`30` (i.e. `260517-*` through `260530-*`) — ~28 dirs
    - PLUS `20260529-wiki-copilot-studio` (malformed 8-digit prefix, but 5月)
  EXCLUDE (leave in place):
    - Every `2026-06` quick dir: prefix `2606*` (260601-ipo, 260601-qdrant-research, 260605-*, 260606-bd, 260608-e8l, 260609-*, 260610-*, 260611-*) — some actively cross-referenced (probe line, rgm, hl6).
    - This quick's own dir `260611-lct-*` (June) — STAYS.
    - The existing `.planning/quick/archive/` dir — STAYS (do not nest).

  STEP 2 — SANITY gate per Set B dir before moving:
    For each candidate dir, confirm its SUMMARY.md (glob `*-SUMMARY.md` inside the dir) exists and reads CLOSED / complete.
    - If a 5月 dir has NO SUMMARY.md OR its SUMMARY shows in-flight / HALTED-without-close → SKIP it (leave in `.planning/quick/`), and record `SKIPPED: <dir> — <reason>` in SUMMARY.md.
    - Note: a quick that HALTED but reached a documented close verdict (e.g. probe quicks with "BLOCKED" verdict + SUMMARY) counts as closed → OK to move. The gate is "has a SUMMARY documenting an end-state", not "succeeded".

  STEP 3 — Move confirmed Set B dirs via `git mv`:
    `mkdir -p .planning/archive/quick-2026-05`
    For each CONFIRMED dir: `git mv .planning/quick/<dir> .planning/archive/quick-2026-05/<dir>`

  STEP 4 — Write `.planning/archive/quick-2026-05/README.md`: terse index, one line per archived dir — `<dir> | <milestone/topic> | <closed-date from SUMMARY> | <why-archived>`. Derive milestone/date/why from each dir's SUMMARY frontmatter or first heading; if unclear, use the slug's descriptive tail.

  STEP 5 — Write `.planning/archive/closed-milestones/README.md` (covers Task 1's Set A): one line per archived root file — `<file> | <milestone> | <closed-date> | <why-archived>`. Use the milestone closed-dates from <facts> (Agentic-RAG-v1=2026-05-24, Aliyun-Ingest-Migration-v1=2026-05-25, kb-databricks-v1=2026-05-20, v1.0.y=2026-05-17, v3.1/v3.2/v3.3 MILESTONE docs=superseded, ROADMAP.md root=2026-05-06-era superseded by suffix ROADMAPs, ARCHITECTURE-*-Ingest-Pipeline-v1=one-time verdict actioned).
  </action>
  <verify>
  - `ls -1d .planning/archive/quick-2026-05/*/ | wc -l` ≈ 29 (28 + wiki-copilot-studio, minus any SKIPPED)
  - `ls -1d .planning/quick/*/` shows NO `2605(17..30)` dirs remaining (except any SKIPPED), `2606*` dirs all present, `260611-lct-*` present, `archive/` present
  - Both README.md files exist and are non-empty (`test -s`)
  - `git status --porcelain | grep '^R'` shows the dir renames
  </verify>
  <done>Confirmed Set B dirs moved to `.planning/archive/quick-2026-05/`; 2026-06 + current-quick dirs untouched; any not-closed dirs SKIPPED + noted; both archive README index files written.</done>
</task>

<task type="auto">
  <name>Task 3: Fix STATE.md drift + broken-ref grep + atomic commit + push</name>
  <files>.planning/STATE.md</files>
  <action>
  Read STATE.md frontmatter (lines 1-14) + Current Position block (lines 20-36) + ISSUES.md facts FIRST. Mirror real facts from <facts> above; invent NO status.

  STEP 1 — Fix STATE.md FRONTMATTER (top of file):
    - `milestone: v3.5` → leave as-is OR set to the real current line if clearer (v3.5-Ingest-Refactor is active; v3.5 is acceptable). Do NOT invent a new milestone.
    - `milestone_name: candidate, not Phase 5 scope.` → this is a GARBAGE spilled value. Replace with a real name, e.g. `milestone_name: "Ingest-Refactor-v3.5"` OR clear to empty `milestone_name: ""`. Pick whichever is truthful; if unsure, clear it.
    - Leave `last_updated` and `last_activity` AS-IS (already current from 260611-hl6 / 260610-rgm — do NOT rewrite the long activity log).
    - `status` / `stopped_at`: if they reference kdb (closed) or a stale phase, update to reflect "no active phase in flight; v1.2 concurrent-ingest research CLOSED 2026-06-12 (#40 BLOCKED)". Keep terse.

  STEP 2 — Fix Current Position block (the `## Current Position` + `**Current focus:**` lines):
    - `**Current focus:** Phase kdb-1.5 — lightrag-databricks-provider-adapter` → REWRITE: kdb CLOSED 2026-05-20. Set focus to 2026-06-12 reality: `**Current focus:** No active phase in flight. v1.2 concurrent-ingest research CLOSED 2026-06-12 (ISSUES #40 BLOCKED — native parallel-insert 1.27x < 1.4x).`
    - `Phase: kdb-1.5 (...) — EXECUTING` + `Plan: 1 of 2` + `KB-v2 ... 1 of 3 phases complete` block → REWRITE to: no active phase EXECUTING; recent activity = perf-line #40 research closed via 260611-hl6; next candidates = kb-2 (KB entity/topic pages, revived not started) OR arx-2 (Deep Research API) OR ir-3 audit (overdue v3.5 closure). List them as options, do NOT pick one.
    - Update the `### Immediate next step` section if it still points at the stale `/gsd:discuss-phase 20` (v3.4-era) — replace with the three candidate next-steps above as user-decision options. Keep historical "v3.4 Phase Overview" / "v3.3 closed state" sections AS-IS (clearly marked retained-for-history).

  Keep edits surgical — only the stale frontmatter values + Current Position/focus/immediate-next-step. Do NOT reflow the activity log or historical sections.

  STEP 3 — BROKEN-REF grep across whole repo (exclude /archive/). For every file moved in Task 1 + Task 2:
    ```
    for f in <basename of each moved root file> <each moved quick dir name>; do
      grep -rl "$f" --include="*.md" . | grep -v "/archive/"
    done
    ```
    - If a KEPT (non-archived) doc still points at a moved file → update that link to the new archive path (e.g. `.planning/archive/closed-milestones/<file>` or `.planning/archive/quick-2026-05/<dir>`). Surgical edit only.
    - Re-run the grep until it returns CLEAN (no non-archive hits) BEFORE commit. Report findings in SUMMARY.

  STEP 4 — COMMIT (atomic, forward-only). Explicit `git add` of EVERY moved/created/edited path (NEVER `-A`):
    - All git-mv'd Set A files (old+new paths tracked by rename)
    - All git-mv'd Set B dirs
    - `.planning/archive/closed-milestones/README.md`, `.planning/archive/quick-2026-05/README.md`
    - `.planning/STATE.md`
    - any kept-with-note files edited in Task 1 (REQUIREMENTS.md etc.)
    - any broken-ref link fixes from STEP 3
    - this plan + the SUMMARY.md in `.planning/quick/260611-lct-260612-doc-cleanup-archive-closed-milest/`
    Commit message: `chore(planning): archive closed-milestone docs + 5月 quicks, fix STATE drift`
    NO `--amend`, NO `reset`, NO `--force-push`. Then `git pull --ff-only` and `git push origin main`.
  </action>
  <verify>
  - STATE.md frontmatter `milestone_name` no longer contains the garbage `candidate, not Phase 5 scope.` string: `grep -c "candidate, not Phase 5 scope" .planning/STATE.md` returns 0
  - STATE.md Current focus no longer says `Phase kdb-1.5 ... EXECUTING`: `grep -c "kdb-1.5.*EXECUTING" .planning/STATE.md` returns 0
  - Broken-ref grep clean: the STEP 3 loop produces NO output lines outside `/archive/`
  - `git log --oneline -1` shows the chore(planning) commit; `git status` clean working tree
  - `git rev-parse HEAD` == `git rev-parse origin/main` (push succeeded)
  - Root .md count dropped: `ls -1 .planning/*.md | wc -l` ≈ 23 (was 40)
  </verify>
  <done>STATE.md drift fixed (no garbage milestone_name, no stale kdb-1.5 EXECUTING, Current Position reflects 2026-06-12 reality with candidate options); broken-ref grep clean; single forward-only commit pushed to origin/main; root .md count ≈ 23.</done>
</task>

</tasks>

<verification>
- `.planning/` root .md files reduced from 40 → ≈ 23.
- `.planning/quick/` dirs reduced (2026-05 dirs + wiki-copilot-studio archived; 2026-06 + current-quick dirs retained).
- `.planning/archive/closed-milestones/` + `.planning/archive/quick-2026-05/` populated with files + README index each.
- STATE.md frontmatter + Current Position fixed, mirroring ISSUES.md/STATE-body facts (no invented status).
- All moves are `git mv` renames (history preserved); broken-ref grep returns clean outside `/archive/`.
- Single forward-only commit on main, pushed. Zero touches outside `.planning/`.
</verification>

<success_criteria>
- Set A (root closed-milestone docs) + Set B (5月 quick dirs) archived; counts reported in SUMMARY.
- REQUIREMENTS.md (and any other active-referenced candidate) KEPT with CLOSED header note, NOT moved.
- Any not-closed 5月 quick SKIPPED with reason recorded.
- STATE.md: garbage milestone_name cleared/fixed; stale kdb-1.5 focus + Current Position rewritten to 2026-06-12 reality (no active phase; #40 research closed; candidates kb-2 / arx-2 / ir-3 listed as options).
- Broken-ref grep clean BEFORE commit.
- Final `.planning/` root .md count ≈ 23.
- Commit `chore(planning): archive closed-milestone docs + 5月 quicks, fix STATE drift` pushed to origin/main; no --amend/reset/force.
</success_criteria>

<output>
After completion, create `.planning/quick/260611-lct-260612-doc-cleanup-archive-closed-milest/260611-lct-SUMMARY.md` reporting:
- Count archived: Set A (root files) + Set B (quick dirs)
- Files KEPT-with-note (incl. REQUIREMENTS.md) + the note text
- Any quick dir SKIPPED (not-closed) + reason
- STATE.md fields fixed (frontmatter + Current Position lines)
- Broken-ref grep result (MUST be clean — list any link fixes applied)
- Final `.planning/` root .md file count (expect ≈ 23 from 40)
- Commit hash + push confirmation
</output>
