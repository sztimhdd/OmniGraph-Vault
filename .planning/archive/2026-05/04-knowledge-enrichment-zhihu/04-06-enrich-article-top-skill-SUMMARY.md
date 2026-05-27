---
phase: 04-knowledge-enrichment-zhihu
plan: 06
subsystem: hermes-skills
tags: [hermes, enrichment, orchestration, zhihu, d-01, d-02, knowledge-enrichment, skill]

requires:
  - phase: 04-05
    provides: skills/zhihu-haowen-enrich — child skill invoked per question
  - phase: 04-02
    provides: enrichment/extract_questions.py — question extraction helper
  - phase: 04-03
    provides: enrichment/fetch_zhihu.py — Zhihu answer fetcher
  - phase: 04-04
    provides: enrichment/merge_and_ingest.py — merge + LightRAG + SQLite runner

provides:
  - "skills/enrich_article/SKILL.md: top-level per-article enrichment orchestrator (D-01)"
  - "skills/enrich_article/README.md: human-facing install and remote-only test guide"
  - "skills/enrich_article/references/: Level-2 pipeline notes directory"

affects:
  - 04-07-ingest-wechat-integration (will call this skill's trigger flow)

tech-stack:
  added: []
  patterns:
    - "D-01: top-level orchestration in pure Markdown — no Python orchestrator file"
    - "D-02: per-question for-loop in SKILL.md body across 3 iterations (~60 turns)"
    - "D-03: stdout JSON contract documented for all 3 Python helpers in SKILL.md"
    - "D-07: enriched == 2 (partial/full success) and enriched == -2 (all-fail) branches"
    - "Progressive disclosure: lean SKILL.md body, references/pipeline-notes.md for Level-2"

key-files:
  created:
    - "skills/enrich_article/SKILL.md"
    - "skills/enrich_article/README.md"
    - "skills/enrich_article/references/ (empty placeholder for Level-2)"
  modified: []

key-decisions:
  - "D-01 enforced: no Python helper; Markdown IS the orchestrator"
  - "D-02 enforced: no scripts/ subdirectory created"
  - "Per-question for-loop: 3 iterations × ~20 turns = ~60 turns; fits under max_turns=90"
  - "Remote deploy via scp (not git branch checkout) because remote has untracked zhihu-haowen-enrich files blocking git checkout"
  - "Full E2E invocation deferred (requires interactive Hermes session + live LLM calls)"

patterns-established:
  - "enrich_article is the D-01 top-level entry point for Phase 4 — all production ingest goes through it"
  - "Skill body documents error-table + output-format contract so the agent can report consistently"

requirements-completed: [D-01, D-02, D-03, D-07]

duration: 20min
completed: 2026-04-27
---

# Phase 04 Plan 06: enrich_article Top-Level Skill Summary

**Pure-Markdown Hermes orchestration skill with 4-step decision tree (extract_questions + per-question /zhihu-haowen-enrich for-loop + fetch_zhihu + merge_and_ingest) and Hermes discovery confirmed on remote**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-27T18:00:00Z
- **Completed:** 2026-04-27T18:20:00Z
- **Tasks:** 2 (6.1 SKILL.md, 6.2 README.md)
- **Files created:** 2 (+ references/ directory placeholder)

## Accomplishments

- Created `skills/enrich_article/SKILL.md` — 208 lines; complete D-01/D-02 compliant orchestrator with 4-step decision tree, per-question for-loop, D-03 stdout contracts, D-07 state handling, and error table
- Created `skills/enrich_article/README.md` — 63 lines; install guide, prerequisites, REMOTE-ONLY test section
- Deployed skill to remote via scp and confirmed Hermes discovery: `enrich_article | local | local | enabled`

## Task Commits

1. **Task 6.1: Create SKILL.md** — `1f4102c` (feat)
2. **Task 6.2: Create README.md** — `17f6146` (feat)

**Plan metadata (this commit):** docs(04-06)

## Files Created

- `skills/enrich_article/SKILL.md` — 208 lines; Hermes skill body with 4-step orchestration, per-question for-loop, D-03 contracts, D-07 enriched-state branches, error table
- `skills/enrich_article/README.md` — 63 lines; install steps, REMOTE-ONLY integration test, D-01 design notes

## Smoke-Test Check Results

| Check | Result |
|-------|--------|
| 1 — SSH connectivity | PASS — `OH-Desktop` reachable at port 49221 |
| 2 — scp deploy | PASS — `skills/enrich_article/` copied to remote via scp |
| 3 — Hermes discovery | PASS — `hermes skills list` shows `enrich_article | local | local | enabled` |
| 4 — YAML frontmatter | PASS — `yaml.safe_load()` parses; `name=enrich_article`, `metadata.openclaw` present |
| 5 — D-02 compliance | PASS — `find skills/enrich_article -name "*.py"` returns 0 files |
| 6 — Line count | PASS — 208 lines (min 120) |
| 7 — All key patterns | PASS — `name:`, `/zhihu-haowen-enrich`, `extract_questions`, `fetch_zhihu`, `merge_and_ingest`, `haowen.json`, `enriched == 2`, `enriched == -2`, `skipped` all grep successfully |

**Deferred — full E2E invocation:** Interactive end-to-end validation (agent invoking the skill
in a live Hermes session and producing enriched WeChat + Zhihu LightRAG docs) requires an
interactive Hermes session + live article URL + Gemini/CDP/Zhihu credentials. This is NOT a
blocker — the Hermes discovery check is a strong structural signal. Deploy after next `git push`
to `main` (or merge of gsd/phase-04) with `ssh remote 'cd OmniGraph-Vault && git pull'`.

**Remote deploy note:** The remote is on `main` branch and has untracked `skills/zhihu-haowen-enrich/`
files that block `git checkout gsd/phase-04`. Used `scp -r` to copy the skill directly as a
workaround. Git state will reconcile when gsd/phase-04 merges to main.

## Decisions Made

- D-01/D-02 enforced: SKILL.md is 208 lines of pure Markdown; no `scripts/` dir, no Python helper
- Per-question for-loop design: Hermes agent iterates 3 times, ~20 turns per question, ~60 turns total (fits max_turns=90)
- References/pipeline-notes.md created as an empty Level-2 placeholder (pattern from zhihu-haowen-enrich/references/flow.md)

## Deviations from Plan

None — plan executed exactly as written. SKILL.md content was created per the plan's verbatim specification with all acceptance criteria passing.

## Known Stubs

None. This plan creates pure documentation/instruction files with no runtime data sources to wire.
The skill cannot be tested locally (D-06: remote-only).

## Issues Encountered

Remote git branch checkout failed (`git checkout gsd/phase-04`) because the remote has
untracked `skills/zhihu-haowen-enrich/` files placed there outside of git history. Resolved by
using `scp -r` to copy the skill directory directly. This is a dev-workflow issue, not a blocking
bug — the skill is deployed and Hermes can discover it.

## User Setup Required

None — no new environment variables, no new external service configuration required beyond what
Wave 1-3 plans already set up.

## Next Phase Readiness

- `skills/enrich_article/` complete, deployed, and Hermes-discoverable on remote
- Plan 04-07 (`ingest_wechat_integration`) can proceed: it wires `ingest_wechat.py` to emit
  `enriched=-1` for short articles and document the D-07 supersession of the `--enrich` flag
- Full E2E validation (invoke `enrich_article` in Hermes with a real WeChat article) is the
  integration test for the entire Phase 4 pipeline — deferred post-04-07

## Self-Check

### Files exist

- `skills/enrich_article/SKILL.md` — FOUND
- `skills/enrich_article/README.md` — FOUND

### Commits exist

- `1f4102c` feat(04-06): add enrich_article SKILL.md — FOUND
- `17f6146` feat(04-06): add enrich_article README.md — FOUND

### D-02 compliance

- No `scripts/` directory — CONFIRMED
- No `.py` files anywhere under skill — CONFIRMED

### Remote discovery

- `hermes skills list | grep enrich_article` → `enrich_article | local | local | enabled` — CONFIRMED

## Self-Check: PASSED

---
*Phase: 04-knowledge-enrichment-zhihu*
*Completed: 2026-04-27*
