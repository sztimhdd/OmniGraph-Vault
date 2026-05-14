---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 08
type: execute
wave: 4
depends_on: ["kb-4-01", "kb-4-02", "kb-4-03", "kb-4-04", "kb-4-05", "kb-4-06", "kb-4-07"]
files_modified:
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
  - .planning/STATE-KB-v2.md
  - .planning/ROADMAP-KB-v2.md
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-08-SUMMARY.md
autonomous: true
requirements: [DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, UI-04]  # close-out plan; produces VERIFICATION.md asserting all prior plans satisfied their REQs
must_haves:
  truths:
    - "kb-4-VERIFICATION.md exists listing all 5 DEPLOY REQs + UI-04 carry-forward as satisfied (or carry-forward documented for option-c paths)"
    - "STATE-KB-v2.md updated to reflect kb-4 complete + KB-v2 milestone status"
    - "ROADMAP-KB-v2.md kb-4 row marked ✅; KB-v2 milestone row marked COMPLETE"
    - "Discipline regex passes: security-reviewer ≥1, database-reviewer ≥1; conditional ui-ux-pro-max + frontend-design ≥1 IFF smoke surfaced gap"
  artifacts:
    - path: ".planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md"
      provides: "phase close artifact — 5 DEPLOY REQs + UI-04 status + discipline regex output"
      min_lines: 100
  key_links:
    - from: "kb-4-VERIFICATION.md"
      to: "STATE-KB-v2.md milestone-complete status"
      via: "verifier sets milestone state"
---

<objective>
Close kb-4 phase. Run the discipline regex from `kb/docs/10-DESIGN-DISCIPLINE.md` Verification regex section. Author `kb-4-VERIFICATION.md` listing each DEPLOY REQ + UI-04 + each must-have truth as VERIFIED/PARTIAL/FAILED with evidence pointers. Update `STATE-KB-v2.md` and `ROADMAP-KB-v2.md` to reflect milestone completion.

Per memory `feedback_parallel_track_gates_manual_run.md`: parallel-track milestones bypass gsd-tools, so STATE/ROADMAP updates are direct edits, NOT via `gsd-tools state advance-plan`.

Purpose: phase close + KB-v2 milestone close.
Output: kb-4-VERIFICATION.md + STATE/ROADMAP edits.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE-KB-v2.md
@.planning/ROADMAP-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@kb/docs/10-DESIGN-DISCIPLINE.md

@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-01-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-02-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-03-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-05-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-06-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-07-SUMMARY.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md

@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-VERIFICATION.md  (model the kb-4 VERIFICATION shape on this)

<interfaces>
- 5 DEPLOY REQs: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05
- UI-04 carry-forward from kb-1 (handled in kb-4-03)
- Discipline regex (10-DESIGN-DISCIPLINE.md Check 1):
  for skill in security-reviewer database-reviewer; do count=$(grep -lE "Skill\\(skill=\"$skill\"" $PHASE_DIR/*-SUMMARY.md | wc -l); echo "$skill: $count"; done
  Expected: security-reviewer ≥1, database-reviewer ≥1
  Conditional: ui-ux-pro-max + frontend-design ≥1 ONLY IF visual gap surfaced
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run discipline regex + author kb-4-VERIFICATION.md</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
  </files>
  <read_first>
    - All 7 prior SUMMARYs in kb-4-ubuntu-deploy-cron-smoke/
    - kb-4-LOCAL-UAT.md
    - kb-4-SMOKE-VERIFICATION.md
    - kb-4-HERMES-PRODSHAPE.md
    - kb-3-VERIFICATION.md (template shape)
  </read_first>
  <action>
    Step 1 — Run discipline regex:
    ```bash
    PHASE_DIR=".planning/phases/kb-4-ubuntu-deploy-cron-smoke"
    for skill in security-reviewer database-reviewer ui-ux-pro-max frontend-design; do
      count=$(grep -lE "Skill\(skill=\"$skill\"" "$PHASE_DIR"/*-SUMMARY.md 2>/dev/null | wc -l)
      echo "$skill: $count plan(s)"
    done
    ```
    Capture output. Mandatory floors: security-reviewer ≥1 (kb-4-01), database-reviewer ≥1 (kb-4-04). Conditional: ui-ux-pro-max + frontend-design ≥1 IFF kb-4-05 or kb-4-07 surfaced visual gaps; otherwise note "0 — no visual gap surfaced this phase, conditional invocation not triggered".

    Step 2 — Author `kb-4-VERIFICATION.md` modeled on kb-3-VERIFICATION.md structure:

    ```markdown
    ---
    phase: kb-4-ubuntu-deploy-cron-smoke
    verified: 2026-05-14T<timestamp>Z
    status: complete | complete-with-carry-forward | reopened
    score: <N>/5 DEPLOY REQs satisfied · UI-04 <satisfied|carry-forward> · 8 plans shipped · all 3 smoke scenarios PASS
    verifier: orchestrator (post-Wave-3 acceptance gate)
    ---

    # Phase kb-4: Ubuntu Deploy + Cron + Smoke Verification — Verification Report

    **Phase Goal:** A clean Ubuntu host runs install.sh, gets the systemd unit + Caddy snippet active, daily cron rebuilds SSG + FTS5, and the 3 PROJECT-KB-v2 smoke scenarios all PASS.

    ## Goal Achievement

    ### Observable Truths

    | # | Truth | Status | Evidence |
    |---|---|---|---|
    | 1 | systemd unit boots uvicorn on 127.0.0.1:8766 with Restart=always | ✓ VERIFIED | kb-4-01-SUMMARY.md (security-reviewer applied) + kb-4-LOCAL-UAT.md `/health` 200 |
    | 2 | Caddy snippet routes /api/* + /static/img/* to 8766; rest from kb/output/ | ✓ VERIFIED | kb-4-01-SUMMARY.md (security-reviewer applied) + kb-4-SMOKE-VERIFICATION.md sub-step evidence |
    | 3 | install.sh idempotent; 6 prereqs checked before mutation | ✓ VERIFIED | kb-4-02-SUMMARY.md (shellcheck output + 6-prereq table) |
    | 4 | Real PNG logo at kb/static/VitaClaw-Logo-v0.png | <✓ VERIFIED | ⚠ CARRY-FORWARD> | kb-4-03-SUMMARY.md (option-{a/b/c}) |
    | 5 | daily_rebuild.sh chains 4 stages atomically; database-reviewer applied | ✓ VERIFIED | kb-4-04-SUMMARY.md (Skill output + race-condition fixes) |
    | 6 | Local UAT exercised all surfaces (15+ screenshots, 6 endpoints) | ✓ VERIFIED | kb-4-LOCAL-UAT.md + .playwright-mcp/kb-4-uat-*.png |
    | 7 | All 3 PROJECT-KB-v2 smoke scenarios PASS | ✓ VERIFIED | kb-4-SMOKE-VERIFICATION.md verdict 4/4 + 5/5 + 3/3 |
    | 8 | Hermes prod-shape verification | ✓ VERIFIED via option-{a/b/c} | kb-4-HERMES-PRODSHAPE.md |

    ### REQ Coverage (5/5 DEPLOY + UI-04 carry-forward)

    | REQ | Plan | Status |
    |---|---|---|
    | DEPLOY-01 (systemd unit) | kb-4-01 | ✓ VERIFIED — kb-deploy/kb-api.service ships with Restart=always + hardening |
    | DEPLOY-02 (Caddy snippet) | kb-4-01 | ✓ VERIFIED — kb-deploy/Caddyfile.snippet routes /api + /static/img |
    | DEPLOY-03 (install.sh idempotent) | kb-4-02 | ✓ VERIFIED — 6-prereq + cmp-s idempotency gate |
    | DEPLOY-04 (daily_rebuild.sh cron) | kb-4-04 | ✓ VERIFIED — chained pipeline + database-reviewer applied |
    | DEPLOY-05 (same-host smoke) | kb-4-06 | ✓ VERIFIED — all 3 smoke scenarios PASS |
    | UI-04 (real PNG logo) | kb-4-03 | <satisfied / carry-forward to operator> |

    ## Plan Inventory

    | Plan | Title | Wave | Skills invoked |
    |---|---|---|---|
    | kb-4-01 | systemd + Caddy | 1 | security-reviewer |
    | kb-4-02 | install.sh bootstrap | 1 | (none mandated) |
    | kb-4-03 | Logo PNG sourcing | 1 | (checkpoint:decision) |
    | kb-4-04 | daily_rebuild.sh | 2 | database-reviewer |
    | kb-4-05 | Local UAT | 3 | conditional ui-ux-pro-max + frontend-design |
    | kb-4-06 | 3 smoke scenarios | 3 | (verification — no Skill mandated) |
    | kb-4-07 | Hermes prod-shape | 3 | conditional ui-ux-pro-max + frontend-design |
    | kb-4-08 | Verification close | 4 | (close-out) |

    ## Skill Discipline Regex (per kb/docs/10-DESIGN-DISCIPLINE.md Check 1)

    ```
    security-reviewer: <N> SUMMARY(s)  (mandatory floor 1 — <PASS/FAIL>)
    database-reviewer: <N> SUMMARY(s)  (mandatory floor 1 — <PASS/FAIL>)
    ui-ux-pro-max: <N> SUMMARY(s)      (conditional — <triggered/not-triggered>)
    frontend-design: <N> SUMMARY(s)    (conditional — <triggered/not-triggered>)
    ```

    ## Smoke Test Verdict (the milestone gate)

    | Scenario | Sub-steps | Verdict |
    |---|---|---|
    | Smoke 1 — 双语 UI 切换 | 4 | <PASS 4/4> |
    | Smoke 2 — 双语搜索 + 详情页 | 5 | <PASS 5/5> |
    | Smoke 3 — RAG 问答双语 + 失败降级 | 3 | <PASS 3/3> |

    See kb-4-SMOKE-VERIFICATION.md for verbatim sub-step evidence + screenshots.

    ## Local UAT (Rule 3 mandatory artifact)

    See kb-4-LOCAL-UAT.md.

    Launcher: `.scratch/local_serve.py`
    Env: KB_DB_PATH=<path>, KB_IMAGES_DIR=<path>
    API smoke: 6/6 endpoints returned expected shape
    Playwright: 15 page screenshots × 3 viewports + 4 interactive flow screenshots
    Visual gaps observed: <0 / N — list>

    ## Hermes Prod-Shape (kb-3-12 deferred item)

    Path chosen: option-{a/b/c}
    See kb-4-HERMES-PRODSHAPE.md.

    ## Anti-pattern Compliance

    | Anti-pattern | Status |
    |---|---|
    | git add -A used | ✓ Explicit file paths only |
    | C1 contract surface (kg_synthesize.synthesize_response) edited | ✓ NOT touched |
    | C2 contract surface (omnigraph_search.query.search) edited | ✓ NOT touched |
    | C3 schema migration | ✓ None (only VACUUM, no schema change) |
    | New :root vars added | ✓ <0 / N — must justify> |
    | New CSS pages (e.g., search.html) | ✓ NOT created |
    | Speculative SSH to Hermes | ✓ NOT performed (memory feedback_dont_speculative_ssh_ask_hermes.md respected) |

    ## Outstanding Items (non-blocking)

    1. <list any deferred items, e.g. UI-04 if option-c was chosen>
    2. <pre-existing kb-2 unit test pollution — flagged from kb-3 deferred-items.md, not addressed in kb-4 per Surgical Changes>

    ## Decision

    **Phase kb-4: <COMPLETE / COMPLETE-WITH-CARRY-FORWARD>.**

    KB-v2 milestone status: <COMPLETE / COMPLETE-WITH-OPERATOR-DEPLOY-PENDING>.

    All 8 plans shipped, 5/5 DEPLOY REQs verified, UI-04 <satisfied / carry-forward>, all 3 smoke scenarios PASS, discipline regex floors met.
    ```

    Step 3 — Apply real values for all `<...>` placeholders by reading the prior SUMMARYs.
  </action>
  <verify>
    <automated>
      test -f .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E '^---' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md  # frontmatter
      grep -E 'phase: kb-4' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'DEPLOY-01.*VERIFIED' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'DEPLOY-05.*VERIFIED' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'security-reviewer:' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'database-reviewer:' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'Smoke 1.*PASS\|Smoke 1.*4/4' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
      grep -E 'Smoke 3.*PASS\|Smoke 3.*3/3' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
    </automated>
  </verify>
  <done>
    - kb-4-VERIFICATION.md exists with all 8 truth rows + 6 REQ rows + Skill discipline output + smoke verdicts + Hermes prod-shape pointer
    - Status decision (COMPLETE / COMPLETE-WITH-CARRY-FORWARD) explicit
  </done>
</task>

<task type="auto">
  <name>Task 2: Update STATE-KB-v2.md to milestone-complete</name>
  <files>.planning/STATE-KB-v2.md</files>
  <read_first>
    - .planning/STATE-KB-v2.md (current state — kb-3-complete-ready-for-kb-4)
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md (Task 1 output)
  </read_first>
  <action>
    Update STATE-KB-v2.md frontmatter:
    - `status:` `kb-3-complete-ready-for-kb-4` → `kb-4-complete-milestone-COMPLETE` (or `kb-4-complete-with-operator-deploy-pending` if option-c was used)
    - `last_updated:` ISO timestamp
    - `last_activity:` 1-paragraph summary citing kb-4-VERIFICATION.md decision line + 5 DEPLOY REQs status + 3 smoke verdicts
    - `progress.completed_phases:` 3 → 4
    - `progress.total_plans:` 33 → 41
    - `progress.completed_plans:` 32 → 40 (+8 kb-4 plans)

    In body, update the "Phase plan" table — add kb-4 row status to ✅ complete with verification link.

    Update "Current Position" section:
    - Phase: kb-4 complete
    - Plan: kb-4 8/8 executed and verified
    - Status: KB-v2 milestone COMPLETE (or partial-complete with operator deploy pending)
    - Last activity: cite kb-4-VERIFICATION.md

    Update "Immediate next step" section:
    - From: `/gsd:plan-phase kb-3`
    - To: Operator: run `sudo bash kb/deploy/install.sh` on Ubuntu host (per kb-4-VERIFICATION); milestone complete; future work = v2.1 candidates per REQUIREMENTS-KB-v2.md
  </action>
  <verify>
    <automated>
      grep -E 'status: kb-4-complete' .planning/STATE-KB-v2.md
      grep -E 'completed_phases: 4' .planning/STATE-KB-v2.md
      grep -E 'completed_plans: 40\|completed_plans: 41' .planning/STATE-KB-v2.md
    </automated>
  </verify>
  <done>
    - STATE-KB-v2.md frontmatter reflects milestone close
    - Body sections updated (Phase plan, Current Position, Immediate next step)
  </done>
</task>

<task type="auto">
  <name>Task 3: Update ROADMAP-KB-v2.md kb-4 row + Progress Table</name>
  <files>.planning/ROADMAP-KB-v2.md</files>
  <read_first>
    - .planning/ROADMAP-KB-v2.md
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md
  </read_first>
  <action>
    Update ROADMAP-KB-v2.md:

    Line ~65 — change kb-4 list bullet:
    ```
    - [ ] **Phase kb-4: Ubuntu Deploy + Cron + Smoke Verification** — systemd unit + Caddy snippet + `install.sh` + `daily_rebuild.sh` cron + 3 smoke scenarios pass.
    ```
    To:
    ```
    - [x] **Phase kb-4: Ubuntu Deploy + Cron + Smoke Verification** — Completed 2026-05-14. systemd unit + Caddy snippet + install.sh idempotent + daily_rebuild.sh cron (database-reviewer applied) + 3 PROJECT-KB-v2 smoke scenarios PASS (4/4 + 5/5 + 3/3) + Local UAT artifact (Rule 3) + Hermes prod-shape verification (option-{a/b/c}). 5/5 DEPLOY REQs · UI-04 <satisfied/carry-forward> · 8 plans across 4 waves · security-reviewer + database-reviewer Skill floors met. See kb-4-VERIFICATION.md.
    ```

    In Phase kb-4 section "Plans:" subsection, replace `Plans: TBD` with full plan list:
    ```
    Plans: 8 plans across 4 waves (planned 2026-05-14 by gsd-planner)
    - [x] kb-4-01-systemd-caddy-PLAN.md — kb/deploy/kb-api.service + kb/deploy/Caddyfile.snippet (security-reviewer applied) (Wave 1)
    - [x] kb-4-02-install-bootstrap-PLAN.md — kb/deploy/install.sh idempotent + 6-prereq checks (Wave 1)
    - [x] kb-4-03-logo-png-source-PLAN.md — UI-04 carry-forward gate (Wave 1, checkpoint:decision)
    - [x] kb-4-04-daily-rebuild-cron-PLAN.md — kb/scripts/daily_rebuild.sh (database-reviewer applied) (Wave 2)
    - [x] kb-4-05-local-uat-PLAN.md — Rule 3 mandatory: kb-4-LOCAL-UAT.md (Wave 3, conditional Skill block)
    - [x] kb-4-06-smoke-3-scenarios-PLAN.md — 3 PROJECT-KB-v2 scenarios verbatim (Wave 3)
    - [x] kb-4-07-hermes-prodshape-smoke-PLAN.md — closes kb-3-12 deferral via option-a/b/c (Wave 3, checkpoint:decision)
    - [x] kb-4-08-verification-close-PLAN.md — phase + milestone close (Wave 4)
    ```

    Update Progress Table near bottom:
    ```
    | kb-4: Ubuntu Deploy + Cron + Smoke Verification | 8/8 | Complete (5/5 DEPLOY REQs · 3 smoke PASS · Skill floors met) | 2026-05-14 |
    ```
  </action>
  <verify>
    <automated>
      grep -E '\[x\] \*\*Phase kb-4' .planning/ROADMAP-KB-v2.md
      grep -E 'kb-4-01-systemd-caddy-PLAN.md' .planning/ROADMAP-KB-v2.md
      grep -E 'kb-4-08-verification-close-PLAN.md' .planning/ROADMAP-KB-v2.md
      grep -E '8/8' .planning/ROADMAP-KB-v2.md  # Progress Table
    </automated>
  </verify>
  <done>
    - ROADMAP kb-4 list bullet ✅
    - kb-4 plan list populated (8 plans)
    - Progress Table updated
  </done>
</task>

</tasks>

<verification>
- kb-4-VERIFICATION.md exists with all DEPLOY REQs status + Skill discipline regex output + smoke verdicts
- STATE-KB-v2.md milestone-complete
- ROADMAP-KB-v2.md kb-4 row + plan list + Progress Table updated
- Discipline regex output documented (security-reviewer ≥1, database-reviewer ≥1)
</verification>

<success_criteria>
- KB-v2 milestone closed (or operator-deploy-pending if option-c)
- All artifacts on disk
- Memory `feedback_parallel_track_gates_manual_run.md` honored — direct edits, not gsd-tools state advance
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-08-SUMMARY.md` + `kb-4-VERIFICATION.md` + STATE/ROADMAP updates
</output>
