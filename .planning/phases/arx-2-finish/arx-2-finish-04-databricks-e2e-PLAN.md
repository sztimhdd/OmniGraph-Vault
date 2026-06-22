---
phase: arx-2-finish
plan: 04
type: execute
wave: 5
depends_on: ["arx-2-finish-02"]
files_modified:
  - .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md
autonomous: false   # FIRST research-endpoint deploy -> STATE Decision 2 "go" checkpoint (Principle #7 + human-in-the-loop)
requirements: [REQ-1.1-B-4, REQ-1.1-B-5]
must_haves:
  truths:
    - "The local Databricks UAT 5-step gate passes BEFORE any deploy (smoke -> uvicorn -> curl SSE -> Playwright -> triple-verification)"
    - "A deploy preflight (workspace path, app name, env diff, expected synced file count) is posted and the agent WAITS for user 'go'"
    - "The deploy uses the FULL Makefile pipeline (deploy.sh: Pass 0 SSG bake -> 0b lang -> 0c dep -> 0d brand -> Pass 1 -> Pass 2 -> apps deploy) — sync-only is FORBIDDEN (Principle #9)"
    - "Claude owns the deploy autonomously via PowerShell + databricks CLI (Principle #7)"
    - "Post-deploy Playwright UAT against the deployed Databricks URL passes with triple verification (network 200 + log SDK call + content marker)"
    - "If the deployed retriever shows 0 sources, the same conditional-acceptance logic as plan 03 applies (downshift + #44 caveat), not a phase failure"
  artifacts:
    - path: ".planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md"
      provides: "Local 5-step gate evidence + deploy preflight + full-pipeline deploy log + post-deploy UAT triple-verification + screenshots"
      contains: "triple verification"
      min_lines: 50
  key_links:
    - from: "databricks-deploy/deploy.sh"
      to: "Databricks Apps omnigraph-kb"
      via: "FULL pipeline (Pass 0 SSG bake includes research.html/research.js) then apps deploy --source-code-path"
      pattern: "deploy\\.sh"
    - from: "deployed Databricks /research/ page"
      to: "POST /api/research SSE"
      via: "Playwright MCP browser UAT + browser_network_requests 200"
      pattern: "/research/"
    - from: "post-deploy verification"
      to: "deployed app logs"
      via: "make logs / scripts/tail_app_logs.py (/logz/stream WebSocket)"
      pattern: "tail_app_logs|make logs"
---

<objective>
GAP E (Databricks half) + REQ-1.1-B-5 — the FIRST deploy of the Deep Research endpoint to
Databricks Apps. This is OPS work: local 5-step UAT gate, a human-in-the-loop "go" checkpoint,
a FULL Makefile-pipeline deploy, and a post-deploy browser UAT with triple verification.

Purpose: This is the only plan covering REQ-1.1-B-5 (Databricks deploy + post-deploy UAT) and
the Databricks half of REQ-1.1-B-4 (local 5-step gate). Wave 2 touched `kb/static/research.js`
+ `kb/templates/research.html` + `kb/templates/_research_result.html` — under `kb/static/` and
`kb/templates/`, so Principle #9 makes sync-only FORBIDDEN: the SSG bake (Pass 0) is the only
thing that regenerates `_ssg/research/index.html` and `_ssg/static/research.js`. Skipping it
ships stale assets and the research page 404s or runs old JS.

Output: 1 VERIFICATION.md with the local 5-step gate evidence, the deploy preflight + recorded
user "go", the full-pipeline deploy log, and the post-deploy UAT (screenshots + triple verification).

**Principle discipline:**
- #9 — `kb/static/` + `kb/templates/` changed => FULL pipeline (`bash databricks-deploy/deploy.sh`,
  aka `make -C databricks-deploy deploy`). NEVER a sync-only Pass 2+3.
- #7 — Claude owns the deploy autonomously via PowerShell + databricks CLI (no user copy-paste of
  `databricks sync` / `apps deploy` / `make logs`).
- STATE-Agentic-RAG-v1.1.md Decision 2 — this is the FIRST v1.1 research-endpoint deploy, so it
  PAUSES for user "go" after the local UAT passes. Post-deploy UAT failure -> agent fix-redeploys
  autonomously, no SECOND checkpoint. Hence this plan is `autonomous: false` (the go checkpoint).

**KG / dim note (from CONTEXT):** Databricks runtime embeds 3072-dim unconditionally — dim-mismatch
is a NON-issue here. The deployed-app retriever uses whatever KG the Databricks app hydrates (the
Unity Catalog volume the app mounts at startup, NOT the Aliyun graphml). If the Databricks KG ALSO
shows 0 sources, apply the SAME conditional-acceptance logic as plan 03 (downshift + #44-style caveat),
not a phase failure.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.1.md
@.planning/STATE-Agentic-RAG-v1.1.md
@CLAUDE.md
@databricks-deploy/deploy.sh
@databricks-deploy/Makefile
@scripts/smoke_databricks_serving_local.py
@scripts/run_local_uvicorn.py
@databricks-deploy/app_entry.py

<interfaces>
<!-- FULL-PIPELINE DEPLOY (Principle #9 — kb/static + kb/templates changed): -->
<!--   `bash databricks-deploy/deploy.sh`  (== `make -C databricks-deploy deploy`; Makefile `deploy:` delegates) -->
<!--   deploy.sh passes (read it): -->
<!--     Pass 0  : rm -rf _ssg; cp -R kb/output -> _ssg   (deploy-time SSG snapshot) -->
<!--     Pass 0a-fix: cp -R kb/static/. -> _ssg/static/   (defeats stale bake — ships research.js) -->
<!--     Pass 0b : flip <html lang> zh-CN -> en for Databricks audience -->
<!--     Pass 0c : stage kg_synthesize.py + config.py + lib/ into databricks-deploy/ -->
<!--     Pass 0d : rebrand _ssg (VitaClaw -> EDC Agentic AI Knowledge Base) -->
<!--     Pass 1  : databricks sync --full databricks-deploy/* -> workspace/databricks-deploy/  (--include _ssg/** kg_synthesize.py config.py lib/**) -->
<!--     Pass 2  : databricks sync --full kb/* -> workspace/databricks-deploy/kb/ -->
<!--     deploy  : databricks apps deploy omnigraph-kb --source-code-path WORKSPACE_ROOT/databricks-deploy -->
<!--   WORKSPACE_ROOT=/Workspace/Users/hhu@edc.ca/omnigraph-kb ; APP_NAME=omnigraph-kb ; PROFILE=dev -->
<!--   ** Pass 0a SSG bake is what regenerates _ssg/research/index.html — Wave 2's export_knowledge_base.py edit -->
<!--      must have run so kb/output/research/index.html EXISTS before deploy.sh's `cp -R kb/output _ssg`. -->
<!--      VERIFY kb/output/research/index.html exists (bake produced it) BEFORE invoking deploy.sh. -->

<!-- TOOL CHOICE (Principle #7 + Windows): run databricks CLI via POWERSHELL not Git Bash -->
<!--   (Git Bash path conversion breaks /Workspace/... -> "Path doesn't start with '/'"). -->
<!--   deploy.sh itself uses MSYS_NO_PATHCONV=1 on path-bearing calls; invoke `bash databricks-deploy/deploy.sh` -->
<!--   from PowerShell so the inner MSYS guard applies. -->

<!-- LOGS (memory databricks_apps_logs_websocket): `databricks apps logs` does NOT exist on CLI v0.260.0. -->
<!--   Use `make -C databricks-deploy logs` (one-shot, scripts/tail_app_logs.py --once) or `logs-tail` (live). -->
<!--   This is the channel for the triple-verification "log SDK call" leg. -->

<!-- LOCAL 5-STEP GATE (REQ-1.1-B-4, RESEARCH §Validation + CLAUDE.md "Local UAT Loop"): -->
<!--   1. smoke : scripts/smoke_databricks_serving_local.py exit 0 (proves serving endpoint reachable from venv+profile; -->
<!--              auth_type='pat' + certifi corp-CA merge per CLAUDE.md). -->
<!--   2. uvicorn: scripts/run_local_uvicorn.py -> stdout "Application startup complete" within ~10s. -->
<!--   3. curl  : POST /api/research on the local uvicorn -> 5 stage events + done event within OMNIGRAPH_LLM_TIMEOUT_SEC. -->
<!--   4. Playwright MCP UAT (main session) -> >= 5 screenshots .playwright-mcp/arx-uat-*.png. -->
<!--   5. triple verification: Network 200 + log SDK call + content marker — all 3 present. -->

<!-- DEPLOYED APP URLs (Makefile smoke target): -->
<!--   Workspace UI : https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb -->
<!--   App URL      : https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com  (post browser-SSO) -->
<!--   Research page on deployed app: <App URL>/research/  (KB_BASE_PATH empty on Databricks per deploy.sh comment). -->

<!-- CONDITIONAL ACCEPTANCE (same as plan 03): the deployed retriever uses the Databricks-hydrated KG -->
<!--   (Unity Catalog volume the app mounts, NOT Aliyun graphml). If it shows 0 sources, DOWNSHIFT: prove -->
<!--   pipeline runs end-to-end + UI stepper completes + document the starvation as a KNOWN-LIMITATION -->
<!--   (cross-ref ISSUE #44 pattern). At least ONE successful UI run = phase goal met. NOT a failure. -->
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: Local Databricks UAT 5-step gate (smoke -> uvicorn -> curl SSE -> Playwright -> triple-verification) THEN post the deploy preflight and WAIT for user "go"</name>
  <read_first>
    - CLAUDE.md "Local UAT Loop (5-step recipe)" + "Local end-to-end testing playbook" (certifi merge, auth_type='pat', .env.local mirror)
    - CLAUDE.md Principle #6 (cite real UAT evidence) + Principle #7 (Claude owns deploy)
    - .planning/REQUIREMENTS-Agentic-RAG-v1.1.md REQ-1.1-B-4 (the 5 sub-gates + their acceptance) + REQ-1.1-B-5 (the "go" gate wording)
    - .planning/STATE-Agentic-RAG-v1.1.md Decision 2 (first-deploy human-in-the-loop checkpoint)
    - scripts/smoke_databricks_serving_local.py + scripts/run_local_uvicorn.py (the actual launchers)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §Validation Architecture (REQ -> test map)
  </read_first>
  <what-built>
    No code. The local Databricks-parity UAT gate (REQ-1.1-B-4) run against a local uvicorn of the
    SAME app_entry the deployed App boots, followed by the STATE Decision 2 deploy preflight. The
    agent owns every command (Principle #7) — no user copy-paste of smoke/uvicorn/curl/databricks calls.
  </what-built>
  <how-to-verify>
    Run the 5 sub-gates IN ORDER (fail fast; do NOT proceed to the next until the prior is green):

    1. **smoke** — `venv/Scripts/python.exe scripts/smoke_databricks_serving_local.py` exits 0
       (auth ok + LLM ok + embedding ok). If it fails: certifi corp-CA merge missing OR PAT expired
       OR auth_type='pat' omitted (per CLAUDE.md). FIX before proceeding. Record the 3 "ok" lines.

    2. **uvicorn** — launch the local server via `scripts/run_local_uvicorn.py` (loads .env.local,
       runs the same `app_entry:app`). Confirm stdout shows "Application startup complete" within ~10s
       AND the LightRAG hydrate line (Loaded graph from ... with N nodes, M edges) so we know the KG
       loaded. Record both lines.

    3. **curl SSE** — `curl -N -X POST http://127.0.0.1:<port>/api/research -H 'Content-Type: application/json'
       -d '{"query":"What is LightRAG?","max_iterations":1}' --max-time <OMNIGRAPH_LLM_TIMEOUT_SEC>`.
       Confirm 5 stage events (web_baseline, retriever, reasoner, verifier, synthesizer) + a terminal
       `event: done`. Record the event-name sequence.

    4. **Playwright MCP UAT (main session ONLY)** — navigate to `http://127.0.0.1:<port>/research/`,
       submit a query (max_iterations=1), watch the stepper complete, render the report. Take >= 5
       screenshots to `.playwright-mcp/arx-uat-*.png` (form, stepper mid-stream, each key stage, final report).

    5. **triple verification** — confirm ALL THREE: (a) `browser_network_requests` shows POST /api/research
       returned 200; (b) the uvicorn stdout shows the SDK/provider call (the synthesizer's get_llm_func ->
       provider invocation); (c) the rendered report contains a content marker proving real synthesis
       (not a cached/empty/fallback string — e.g. a phrase tied to the query, or >= 1 real source chip).

    **CONDITIONAL ACCEPTANCE (mirror plan 03):** if the LOCAL retriever shows 0 sources (the local KG may
    also have the #44-style divergence), DOWNSHIFT: prove the pipeline runs end-to-end + the stepper
    completes + document the starvation as a KNOWN-LIMITATION; the 5-step gate still PASSES on
    "pipeline runs + UI completes". At least one successful UI run = gate met.

    THEN — STATE Decision 2 deploy PREFLIGHT. Post (and WAIT for user "go" before any sync/deploy):
    - Workspace path: `/Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy`
    - App name: `omnigraph-kb` (PROFILE dev)
    - Deploy command: `bash databricks-deploy/deploy.sh` (FULL pipeline — Principle #9, sync-only FORBIDDEN)
    - Env diff: any `app.yaml` env keys vs local `.env.local` that changed (list them; none expected for a UI-only change)
    - Expected synced file count / what's new: `_ssg/research/index.html` + `_ssg/static/research.js` +
      updated `_ssg/static/style.css` + the research templates baked into the SSG output.
    - Confirm kb/output/research/index.html EXISTS (Wave 2 SSG bake produced it) so Pass 0 `cp -R kb/output _ssg` carries it.

    Record the full preflight text + the user's "go" reply VERBATIM in VERIFICATION.md.
  </how-to-verify>
  <acceptance_criteria>
    - VERIFICATION.md records all 5 sub-gates with evidence: smoke 3x "ok"; uvicorn "Application startup complete" + hydrate node/edge count; curl 5-stage-event sequence + done; >= 5 screenshots `.playwright-mcp/arx-uat-*.png` (`ls .playwright-mcp/arx-uat-*.png | wc -l` >= 5); triple-verification all 3 legs present (network 200 + provider call in stdout + content marker).
    - VERIFICATION.md contains the deploy preflight block (workspace path + app name + full-pipeline deploy command + env diff + expected synced files) AND the recorded user "go".
    - VERIFICATION confirms `kb/output/research/index.html` exists before deploy (`grep -q "research/index.html" .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md`).
    - NO sync / apps deploy was run in this task (it waits for "go" — deploy happens in Task 2).
  </acceptance_criteria>
  <resume-signal>Type "go" to authorize the first Databricks research-endpoint deploy (or report which of the 5 local sub-gates failed).</resume-signal>
</task>

<task type="auto">
  <name>Task 2: FULL-pipeline deploy (deploy.sh) + post-deploy Playwright UAT against the deployed URL with triple verification; fix-redeploy autonomously on UAT failure (no second checkpoint)</name>
  <read_first>
    - CLAUDE.md Principle #9 (FULL Makefile required when kb/static or kb/templates changed — sync-only FORBIDDEN)
    - CLAUDE.md Principle #7 (Claude owns deploy via PowerShell + databricks CLI)
    - databricks-deploy/deploy.sh (the full pipeline this task invokes) + databricks-deploy/Makefile (logs target)
    - Memory databricks_apps_logs_websocket (`make logs` not `databricks apps logs`)
    - Memory databricks_apps_stop_start_wipes_deployment (do NOT stop/start as a "restart" — re-run deploy)
    - .planning/STATE-Agentic-RAG-v1.1.md Decision 2 (post-deploy failure -> fix-redeploy autonomously, NO second checkpoint)
  </read_first>
  <action>
    **This task runs ONLY after Task 1 recorded the user "go".**

    1. **Deploy (FULL pipeline, Principle #9 + #7).** From PowerShell, run the canonical full-pipeline
       deploy (NOT a sync-only subset): `bash databricks-deploy/deploy.sh`
       (equivalently `make -C databricks-deploy deploy` — the Makefile `deploy:` target delegates to deploy.sh).
       This runs Pass 0 SSG bake (regenerates `_ssg/research/index.html` + overlays `kb/static/research.js`),
       0b lang flip, 0c dep stage, 0d brand flip, Pass 1 sync, Pass 2 sync, then `apps deploy --source-code-path`.
       Capture the deploy log; confirm `apps get omnigraph-kb -o json` shows a fresh deployment_id + status.
       Do NOT use `apps stop`+`start` as a restart (it wipes the deployment artifact — memory).

    2. **Confirm startup.** `make -C databricks-deploy logs` (one-shot) — confirm the app booted and the
       research router is mounted (no import error; LightRAG hydrate line present). This is also the
       "log SDK call" channel for triple verification.

    3. **Post-deploy Playwright MCP UAT (main session ONLY).** Navigate to the deployed research page
       `<App URL>/research/` (App URL: https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/research/;
       browser-SSO interactive). Submit a real query (max_iterations=1), watch the 5-stage stepper stream,
       render the report. Screenshots to `.playwright-mcp/arx-dbx-uat-*.png` (>= 2: stepper + final report).

    4. **Triple verification (all 3 legs):**
       - Network 200: `browser_network_requests` shows POST /api/research -> 200 + SSE streamed.
       - Log SDK call: `make logs` shows the synthesizer's provider invocation for this request.
       - Content marker: the rendered report contains real synthesized content (query-tied phrase OR >= 1 source chip),
         not a cached/empty/fallback string.

    5. **CONDITIONAL ACCEPTANCE (mirror plan 03).** The deployed retriever uses the Databricks-hydrated KG.
       - If sources > 0: FULL acceptance — real prose report + >= 1 source + stepper completed.
       - If sources == 0: DOWNSHIFT — prove pipeline runs end-to-end + stepper completes + document the
         starvation as a KNOWN-LIMITATION cross-referencing the ISSUE #44 pattern (Databricks KG may share
         the graphml↔Qdrant divergence). NOT a phase failure. At least ONE successful UI run = phase goal met.

    6. **Fix-redeploy autonomously on failure (STATE Decision 2).** If the post-deploy UAT fails (404 on
       /research/, stale JS, import error, missing _ssg asset), fix the root cause and RE-RUN the FULL
       deploy.sh autonomously — NO second user checkpoint. Common root cause: SSG bake gap (stale
       `_ssg/research/index.html`) — re-bake kb/output then re-deploy. Record each redeploy in VERIFICATION.

    Append all evidence to `.planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md`: deploy log
    excerpt (deployment_id + status), `make logs` startup excerpt, screenshot paths, triple-verification
    three legs, branch chosen (full / downshift), and any fix-redeploy iterations.
  </action>
  <verify>
    <automated>grep -Eiq "deployment_id|apps deploy|deploy\.sh" .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md && grep -Eiq "triple verification|network 200|content marker" .planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md && echo "VERIFICATION cites deploy + triple verification"</automated>
  </verify>
  <acceptance_criteria>
    - VERIFICATION.md cites the FULL-pipeline deploy (`bash databricks-deploy/deploy.sh` or `make -C databricks-deploy deploy`) — NOT a sync-only Pass 2+3 (`grep -Eiq "deploy\.sh|make.*deploy"` succeeds; NO claim of sync-only deploy present).
    - VERIFICATION.md records a fresh deployment_id + status from `apps get omnigraph-kb -o json`.
    - VERIFICATION.md cites `make logs` (or tail_app_logs.py) startup evidence (the log-SDK-call leg).
    - >= 2 screenshots under `.playwright-mcp/arx-dbx-uat-*.png` (`ls .playwright-mcp/arx-dbx-uat-*.png | wc -l` >= 2).
    - Triple verification all 3 legs cited (network 200 + log SDK call + content marker). The automated verify grep passes.
    - Branch recorded: full (sources > 0) or downshift (sources == 0 with #44-style KNOWN-LIMITATION caveat). At least ONE successful Deep Research UI run demonstrated on the deployed Databricks app.
    - Any post-deploy UAT failure was fix-redeployed autonomously (no second "go" checkpoint) and the iteration is recorded.
  </acceptance_criteria>
  <done>Research endpoint deployed to Databricks via the full pipeline; deployed /research/ UI UAT passes triple verification (or downshift-passes with #44 caveat); evidence in VERIFICATION.md.</done>
</task>

</tasks>

<verification>
- Local 5-step gate (REQ-1.1-B-4) all green with evidence: smoke exit 0, uvicorn startup, curl 5 stage events + done, >= 5 `.playwright-mcp/arx-uat-*.png`, triple verification.
- Deploy preflight posted + user "go" recorded BEFORE any sync/deploy (STATE Decision 2).
- Deploy used the FULL Makefile pipeline (deploy.sh, Pass 0 SSG bake present) — sync-only NOT used (Principle #9).
- Deploy run by the agent via PowerShell + databricks CLI (Principle #7) — no user copy-paste.
- Post-deploy UAT (REQ-1.1-B-5) against the deployed Databricks URL passes triple verification (network 200 + log SDK call + content marker), with >= 2 deployed-app screenshots.
- Conditional acceptance: if sources == 0 on the Databricks KG, downshift + #44-style KNOWN-LIMITATION caveat — not a phase failure.
</verification>

<success_criteria>
- REQ-1.1-B-4 local 5-step gate PASSES with cited evidence.
- REQ-1.1-B-5 Databricks deploy + post-deploy UAT PASSES (full or downshifted) with the first-deploy "go" checkpoint honored.
- The deploy used the full Makefile pipeline (Principle #9) and was Claude-owned (Principle #7).
- At least ONE successful Deep Research UI run is demonstrated on the deployed Databricks app (phase goal: user CAN use Deep Research).
</success_criteria>

<output>
After completion, create `.planning/phases/arx-2-finish/arx-2-finish-04-SUMMARY.md`
</output>
