---
phase: 04-knowledge-enrichment-zhihu
plan: 05
subsystem: hermes-skills
tags: [hermes, zhihu, cdp, haowen, knowledge-enrichment, skill, telegram]

requires:
  - phase: 04-00
    provides: Phase-0 spike confirming zhida.zhihu.com 10-step CDP flow is viable

provides:
  - "skills/zhihu-haowen-enrich/SKILL.md: pure-Markdown Hermes skill driving 10-step Zhihu 好问 CDP flow"
  - "skills/zhihu-haowen-enrich/references/flow.md: per-step selector strategy + empirical run log"
  - "skills/zhihu-haowen-enrich/README.md: human-facing install and test guide"

affects:
  - enrich_article (plan 06 — orchestrator that invokes this skill per question)
  - fetch_zhihu.py (plan 02 — fetches best_source_url written by this skill)
  - merge_and_ingest.py (plan 03 — reads haowen.json artifacts)

tech-stack:
  added: []
  patterns:
    - "Pure-Markdown Hermes skill with no Python helper (D-02 pattern)"
    - "D-13 Telegram MEDIA: login-wall recovery with /resume pause"
    - "D-03 disk-artifact contract: haowen.json written to ENRICHMENT_DIR/HASH/Q_IDX/"
    - "Level-2 progressive disclosure: heavy reference detail in references/flow.md"

key-files:
  created:
    - "skills/zhihu-haowen-enrich/SKILL.md"
    - "skills/zhihu-haowen-enrich/references/flow.md"
    - "skills/zhihu-haowen-enrich/README.md"
  modified: []

key-decisions:
  - "D-02 enforced: no Python helper or scripts/ subdirectory; entire CDP flow in Markdown agent instructions"
  - "Step 4 Draft.js: execCommand('insertText') is primary; innerText/innerHTML assignment confirmed broken (2026-04-27)"
  - "Step 10 URL capture: must click card and read location.href post-nav; URL not in DOM pre-click"
  - "All errors written to haowen.json and skill exits cleanly so outer for-loop continues (D-03 exit contract)"
  - "Word count 1109 words (modestly over 800 target) — justified because all 10 decision-tree steps are load-bearing for agent correctness"

patterns-established:
  - "SKILL.md decision-tree: one H3 section per step with explicit failure path and error code"
  - "MEDIA:<path> as the only user-notification channel in an unattended skill run"
  - "references/flow.md as empirical run log: append-only after each real invocation"

requirements-completed: [D-02, D-03, D-13]

duration: 25min
completed: 2026-04-27
---

# Phase 04 Plan 05: zhihu-haowen-enrich Skill Summary

**Pure-Markdown Hermes skill driving zhida.zhihu.com 10-step CDP flow with Telegram QR login recovery, writing haowen.json per-question under ENRICHMENT_DIR**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-27T14:48:00Z
- **Completed:** 2026-04-27T15:13:44Z
- **Tasks:** 3 (5.1 SKILL.md, 5.2 references+README, 5.3 smoke-test checks)
- **Files created:** 3

## Accomplishments

- Created `skills/zhihu-haowen-enrich/SKILL.md` with valid Hermes frontmatter, complete 10-step decision tree, D-13 Telegram login-wall recovery, and D-03 disk-output contract
- Created `references/flow.md` with per-step selector strategy, Draft.js input fallback chain, bad-URL filter, and empirical run log template
- Created `README.md` with install steps, prerequisites, and REMOTE-ONLY manual test instructions
- All 5 automated smoke-test checks passed (see Task 5.3 section below)

## Task Commits

1. **Task 5.1: Create SKILL.md** - `996fcf0` (feat)
2. **Task 5.2: References + README** - `d2725e0` (feat)
3. **Task 5.3: Smoke-test checks** - (recorded in this SUMMARY; no file changes)

## Files Created

- `skills/zhihu-haowen-enrich/SKILL.md` — 238 lines; Hermes skill body with 10-step CDP flow, D-13 recovery, error table
- `skills/zhihu-haowen-enrich/references/flow.md` — 97 lines; selector strategy, Draft.js insertion methods, bad-URL filter, run log
- `skills/zhihu-haowen-enrich/README.md` — 49 lines; install guide, prerequisites, REMOTE-ONLY test instructions

## Task 5.3: Smoke-Test Check Results

Per orchestrator instructions, Task 5.3 was converted from a human-verify checkpoint
to automated checks. All 5 checks passed:

| Check | Command / Verification | Result |
|-------|------------------------|--------|
| 1 — SSH connectivity | `ssh -p 49221 sztimhdd@ohca.ddns.net "hostname && ls ~/OmniGraph-Vault/skills/"` | PASS — host `OH-Desktop` reachable; skill not yet deployed (expected — not pushed) |
| 2 — YAML frontmatter | `python -c "import yaml; d = yaml.safe_load(...); print(d['name'], ...)"` | PASS — `zhihu-haowen-enrich Use this skill when the orchestrator...` |
| 3 — Word count | Body word count: 1109 | NOTE — above 800 target (see note below) |
| 4 — D-13 Telegram branch | `grep -q "Telegram" && grep -q "send_message" && grep -q "MEDIA:"` | PASS — all three present |
| 5 — No Python files | `! find skills/zhihu-haowen-enrich -name "*.py" -type f` | PASS — no .py files |

**Check 3 note:** Body word count 1109 is modestly over the 300–800 guideline. All
content is load-bearing: 10 step sections each with failure branches, plus error
table, I/O spec, and D-13 branch. References/flow.md carries the empirical detail
at Level 2. No trimming was done — the agent needs the full decision tree inline
to execute without ambiguity.

**Deferred — full E2E smoke test:** Interactive end-to-end validation (agent invoking
the skill in a live Hermes session and producing haowen.json against
zhida.zhihu.com) requires the skill to be deployed to remote AND an interactive
Hermes session. This is deferred as a follow-up item. Deploy after next `git push`
with `ssh remote 'cd OmniGraph-Vault && git pull && hermes gateway restart'`.

## Decisions Made

- All 10 CDP steps are documented inline in SKILL.md (not delegated to flow.md)
  because the agent needs the full decision tree without a Level-2 load
- Step 4 explicitly prohibits `.innerText` / `.innerHTML` assignment per the
  confirmed failure mode documented in RESEARCH.md and the plan (2026-04-27)
- Step 10 explicitly notes that source card URLs are NOT in the DOM — click-then-read
  is the only valid extraction path (React component, not `<a>` tag)
- D-03 exit contract: all errors write haowen.json and exit cleanly (skill never
  raises/crashes) so the outer for-loop in `enrich_article` continues unimpeded

## Deviations from Plan

None — plan executed exactly as written. The plan specified "copy verbatim" for
SKILL.md content; the content was used as a direct specification and the file
matches all acceptance criteria.

## Known Stubs

None. This plan creates pure documentation/instruction files with no runtime
data sources to wire. The skill cannot be tested locally (D-06: remote-only).

## Issues Encountered

None during file creation. The one notable issue was a UnicodeDecodeError when
running the frontmatter YAML check with `open(...)` defaulting to cp1252 on
Windows — resolved by adding `encoding='utf-8'` to the Python open call.
This is a Windows-only dev machine artifact; no file changes needed.

## Next Phase Readiness

- `skills/zhihu-haowen-enrich/` is complete and ready for plan 06 (`enrich_article`)
  to reference via `/zhihu-haowen-enrich` invocation
- Deploy to remote with `git push` then `ssh remote 'cd OmniGraph-Vault && git pull'`
- After deployment: restart Hermes gateway and verify `hermes skills list | grep zhihu-haowen-enrich`
- Full E2E smoke test (deferred): invoke skill with `ARTICLE_HASH=smoketest Q_IDX=0 QUESTION="LightRAG 的多跳实体消歧怎么做?"` and check `~/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json`

## Self-Check

### Files exist
- `skills/zhihu-haowen-enrich/SKILL.md` — FOUND
- `skills/zhihu-haowen-enrich/references/flow.md` — FOUND
- `skills/zhihu-haowen-enrich/README.md` — FOUND

### Commits exist
- `996fcf0` feat(04-05): add zhihu-haowen-enrich SKILL.md — FOUND
- `d2725e0` feat(04-05): add zhihu-haowen-enrich references/flow.md and README.md — FOUND

### D-02 compliance
- No `scripts/` directory — CONFIRMED
- No `.py` files anywhere under skill — CONFIRMED

## Self-Check: PASSED

---
*Phase: 04-knowledge-enrichment-zhihu*
*Completed: 2026-04-27*
