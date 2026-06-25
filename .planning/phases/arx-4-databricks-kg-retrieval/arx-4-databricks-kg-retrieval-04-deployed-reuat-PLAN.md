---
phase: arx-4-databricks-kg-retrieval
plan: 04
type: execute
wave: 3
depends_on: ["02", "03"]
files_modified:
  - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md
  - .planning/STATE-Agentic-RAG-v1.1.md
autonomous: false
requirements: [ARX4-UAT, ARX4-64, ARX4-65]
user_setup: []

must_haves:
  truths:
    - "arx-2 Deep Research re-UAT on Databricks at iterations=1 PASSES the CONTEXT pass-bar: vector chunks >0, no WEIGHT-fallback WARNING, rerank reconciled (no misleading WARNING), sources>0, cited report renders."
    - "Evidence (commands run, log excerpts, before/after WARNING diff, screenshot) is cited in arx-4-...-VERIFICATION.md per Principle #6 — the phase is NOT complete until this is written."
  artifacts:
    - path: ".planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md"
      provides: "The Principle-#6 deployed re-UAT evidence section: launcher/query used, backend-log excerpts (vector chunks count, WEIGHT-fallback absence, rerank-WARNING absence), the rendered report proof"
      contains: "vector chunks"
  key_links:
    - from: "deployed /api/research (Deep Research, iterations=1)"
      to: "vector-similarity retrieval + reconciled rerank"
      via: "the combined effect of Plan 02 (#65) + Plan 03 (#64)"
      pattern: "vector chunks"
---

<objective>
This is the Principle-#6 acceptance gate for the whole phase: re-run the arx-2 Deep Research UAT on the deployed Databricks app at iterations=1 and prove that BOTH fixes landed together — #64 (vector-similarity retrieval restored, no WEIGHT fallback) AND #65 (rerank disagreement reconciled) — without regressing the arx-2 baseline (sources>0, cited report still renders). It depends on Plan 02 (#65 reconcile, deployed) AND Plan 03 (#64 sync+re-hydrate, deployed), so it is Wave 3 (last wave).

Per CLAUDE.md Principle #6: a green test suite is necessary but NOT sufficient — the phase MUST NOT be marked complete until this deployed re-UAT is performed and cited in VERIFICATION.md. Entra-SSO blocks Playwright on the Databricks app (per arx-2-finish), so the query step is human-driven; the executor owns the log verification + the VERIFICATION.md write-up.

Output: arx-4-...-VERIFICATION.md with the deployed-UAT evidence.

ZERO new features — this verifies the two repairs.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-02-SUMMARY.md
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-03-SUMMARY.md
@.planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: [DATABRICKS DEPLOY + HUMAN UAT] Re-run arx-2 Deep Research at iterations=1 on the deployed app; verify the combined pass-bar on the backend log</name>
  <files>(no repo files — deployed-app UAT + log verification; produces evidence for Task 2's VERIFICATION.md)</files>
  <read_first>
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md (the Verification section — the EXACT pass-bar strings)
    - .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md (the arx-2 Databricks UAT#3 baseline: query "what is a harness for agent", iterations=1, 11 sources, [1]-[11] cites, ~9000-word report, backend log `POST /api/research 200` — this is what we re-run + diff against)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-02-SUMMARY.md (the #65 branch + the rerank-WARNING before/after)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-03-SUMMARY.md (the #64 vector-chunks before/after)
    - MEMORY: databricks-apps-sse-300s-cap (WHY iterations=1 — iterations≥2 is out of scope #63), databricks_apps_logs_websocket (how to fetch logs — make logs / tail_app_logs.py, NOT `databricks apps logs`)
  </read_first>
  <action>
    **CHANNEL: DATABRICKS DEPLOY (Claude-owned CLI for log fetch + any redeploy, PowerShell/Git Bash per Principle #7) + HUMAN UAT (Entra-SSO blocks Playwright, so the user drives the browser query).**

    Pre-conditions to confirm before the UAT (executor, read-only via make logs + apps get):
    - The deployed app is the version with BOTH Plan 02 (#65 reconcile) AND Plan 03 (#64 sync+re-hydrate) landed. If Plan 02 and Plan 03 deployed independently, confirm the CURRENT deployed artifact contains both — if not, do one final `databricks apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy --profile dev` so the live app has both, then confirm via the startup log (`rerank_diag` line from Plan 02 present AND `startup_adapter: copied via` fresh hydrate from Plan 03 present).

    UAT (human-driven query, executor verifies log):
    1. User opens the deployed Databricks app in the browser (logged in via Entra SSO), navigates to the Deep Research / `/research/` page, enters the SAME query class as the arx-2 baseline — e.g. "what is a harness for agent" — with iterations=1 (the default; do NOT raise it — #63 is out of scope), and runs it. Wait for the 5-stage stepper to complete (~under 300s) and the cited report to render.
    2. Executor fetches the backend log (make logs / tail_app_logs.py) for the time window of that request and greps for the FOUR pass-bar conditions below.

    Capture for VERIFICATION.md:
    - The backend `POST /api/research 200` line (request succeeded).
    - The `Raw search results: N vector chunks` line with N>0 (#64 fixed — vector path active).
    - Confirmation the log does NOT contain `falling back to WEIGHT method` for that request (#64 fixed).
    - Confirmation the log does NOT contain `Rerank is enabled but no rerank model is configured` for that request (#65 fixed) — and, if Plan 02 took Branch B, a `Successfully reranked: N chunks` line is present (rerank actually applied).
    - The rendered report: sources count (>0, expect ~11 like baseline) + that inline cites [1]..[N] + a screenshot saved to `.playwright-mcp/arx-4-deployed-reuat.png` (user can screenshot the browser; or the executor notes the user-reported sources count + report length).
  </action>
  <what-built>Plan 01 fixed the OOM converter + regenerated Aliyun vdb; Plan 03 synced the aligned snapshot to the UC Volume + forced a re-hydrate (restoring vector-similarity retrieval, #64); Plan 02 reconciled the rerank init-vs-query disagreement (#65). This checkpoint re-runs the arx-2 Deep Research UAT at iterations=1 on the live Databricks app to prove both repairs landed together without regressing the baseline.</what-built>
  <how-to-verify>
    1. Executor confirms the live app has BOTH fixes (Plan 02 rerank_diag line + Plan 03 fresh-hydrate line in the current startup log); redeploys once if needed.
    2. User (Entra SSO) runs the Deep Research query "what is a harness for agent" at iterations=1 on the deployed app and waits for the cited report to render.
    3. Executor fetches the backend log for that request window and confirms all four pass-bar conditions.
  </how-to-verify>
  <verify>
    <automated>echo "MANUAL — see how-to-verify: executor greps deployed backend log for POST /api/research 200, 'vector chunks' >0, absence of 'falling back to WEIGHT method', absence of 'no rerank model is configured' after the human-run iterations=1 query"</automated>
  </verify>
  <acceptance_criteria>
    - Backend log for the UAT request contains `POST /api/research` with `200`.
    - Backend log contains `vector chunks` with count > 0 (NOT 0) for the request.
    - Backend log does NOT contain `falling back to WEIGHT method` for the request (#64 PASS).
    - Backend log does NOT contain `Rerank is enabled but no rerank model is configured` for the request (#65 PASS); Branch-B additionally shows `Successfully reranked`.
    - The rendered report has sources > 0 (user-confirmed count, expect ~11) and inline citations [1]..[N]; a screenshot or the user-reported metrics are recorded.
  </acceptance_criteria>
  <resume-signal>Type "approved" with the backend-log excerpt (the `vector chunks` count line, plus confirmation that BOTH the WEIGHT-fallback line and the rerank "no rerank model" WARNING are absent) and the report sources count — or describe which pass-bar condition failed.</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Write arx-4-...-VERIFICATION.md with the deployed re-UAT evidence (Principle #6 closure artifact)</name>
  <files>.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md, .planning/STATE-Agentic-RAG-v1.1.md</files>
  <read_first>
    - .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md (the format/structure to mirror — Local UAT / Deployed UAT sections, evidence citations)
    - The Task 1 checkpoint output (the approved backend-log excerpts + report metrics)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-01-SUMMARY.md + -02-SUMMARY.md + -03-SUMMARY.md (the per-issue evidence to roll up: #41 RSS proof, #65 branch+WARNING diff, #64 vector-chunks diff)
    - .planning/STATE-Agentic-RAG-v1.1.md (the milestone state file to add the arx-4 row to)
    - CLAUDE.md Principle #6 (the mandatory VERIFICATION.md content: launcher/query used, log excerpts, before/after WARNING diff) + memory feedback_parallel_track_gates_manual_run (suffix files skip gsd-tools gates — hand-drive)
  </read_first>
  <action>
    Write `.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md` (CHANNEL: local file write). Structure it per the arx-2-finish VERIFICATION precedent, with these mandatory sections:
    - **Phase + pass/fail header** (PASS only if all three issue closures verified).
    - **#41 (ARX4-41) evidence** (roll up from Plan 01 SUMMARY): the Aliyun `/usr/bin/time -v` Maximum-RSS line, no-OOM exit, vdb_relationships.json size, qdrant-snapshot.timer enabled+active.
    - **#64 (ARX4-64) evidence** (Plan 03 SUMMARY + Task 1): pre-sync gate numbers, UC Volume file_size, `startup_adapter: copied via` fresh-hydrate line, and the deployed-query before/after `vector chunks` (0 → N>0) + WEIGHT-fallback (present → absent) diff.
    - **#65 (ARX4-65) evidence** (Plan 02 SUMMARY + Task 1): the rerank_diag line, the chosen branch, and the before/after `no rerank model is configured` WARNING diff (present → absent), plus `Successfully reranked` if Branch B.
    - **Deployed re-UAT (ARX4-UAT)**: the query used, iterations=1, the `POST /api/research 200` line, the four pass-bar conditions with their log excerpts, the report sources count + screenshot path.
    - **Known-limitations carried forward**: note #63 (iterations≥2 async-job) remains OUT of scope (the SSE 300s cap is unchanged by this phase).

    Then update the milestone state file `.planning/STATE-Agentic-RAG-v1.1.md` to add an arx-4 row (CLOSED PASS, with the VERIFICATION.md path) — this is the parallel-track hand-driven gate per memory `feedback_parallel_track_gates_manual_run` (suffix files skip gsd-tools gates). (Leave the ISSUES.md row moves to the orchestrator per CLAUDE.md Principle #10 subagent boundary — surface #64/#65/#41 as resolved in this VERIFICATION + the close-out report; do NOT edit ISSUES.md from this task.)
  </action>
  <verify>
    <automated>test -f .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md && grep -nE "ARX4-41|ARX4-64|ARX4-65|ARX4-UAT|vector chunks|WEIGHT|rerank|Maximum resident set size" .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-VERIFICATION.md && grep -nE "arx-4.*(CLOSED|PASS)" .planning/STATE-Agentic-RAG-v1.1.md</automated>
  </verify>
  <acceptance_criteria>
    - `arx-4-databricks-kg-retrieval-VERIFICATION.md` EXISTS in the phase dir.
    - It contains a pass/fail header and the four evidence sections — grep returns hits for ALL of: `ARX4-41`, `ARX4-64`, `ARX4-65`, `ARX4-UAT`, `vector chunks`, `WEIGHT`, `rerank`, `Maximum resident set size`.
    - The #64 section records the deployed `vector chunks` count > 0 AND the WEIGHT-fallback present→absent diff; the #65 section records the `no rerank model is configured` present→absent diff; the #41 section records the Aliyun Maximum-RSS line + qdrant-snapshot.timer enabled.
    - `.planning/STATE-Agentic-RAG-v1.1.md` has an arx-4 row marked CLOSED PASS with the VERIFICATION.md path (parallel-track hand-driven gate per `feedback_parallel_track_gates_manual_run`).
    - The VERIFICATION explicitly notes #63 (iterations≥2 async-job) remains OUT of scope.
    - ISSUES.md is NOT edited by this task (orchestrator-only per Principle #10); #41/#64/#65 are surfaced as resolved in the close-out report instead.
  </acceptance_criteria>
  <done>VERIFICATION.md written with all four evidence sections (PASS header only if all three closures verified), STATE-Agentic-RAG-v1.1.md updated with the arx-4 CLOSED-PASS row, and the close-out report surfaces #41/#64/#65 as resolved for the orchestrator to move in ISSUES.md.</done>
</task>

</tasks>

<verification>
- VERIFICATION.md exists and greps clean for all four ARX4-* ids + the evidence keywords (`vector chunks`, `WEIGHT`, `rerank`, `Maximum resident set size`).
- Deployed re-UAT (iterations=1) backend log captured: `POST /api/research 200`, `vector chunks` > 0, NO `falling back to WEIGHT method`, NO `no rerank model is configured`.
- STATE-Agentic-RAG-v1.1.md carries the arx-4 CLOSED-PASS row.
</verification>

<success_criteria>
- arx-2 Deep Research re-UAT on Databricks at iterations=1 PASSES the four-condition pass-bar (vector chunks >0, no WEIGHT fallback, rerank reconciled, sources>0 cited report).
- All three issue closures (#41/#64/#65) have cited deployed/prod evidence rolled into VERIFICATION.md per Principle #6 — the phase is complete ONLY after this artifact exists.
- #63 explicitly carried forward as out-of-scope (SSE 300s duration cap unchanged).
</success_criteria>

<output>
After completion, the close-out report (NOT ISSUES.md — orchestrator-owned per Principle #10) surfaces #41, #64, #65 as RESOLVED with their resolving evidence, so the orchestrator can move those rows to Resolved (recent). VERIFICATION.md is the durable phase-closure artifact.
</output>