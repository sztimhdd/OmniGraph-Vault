---
phase: arx-2-finish
plan: 04
wave: 5
status: human-uat-pending
reason: deployed App is on Databricks internal network — local browser cannot reach it; SSO+MFA gated
created: 2026-06-15
owner: user (manual UAT)
gate: REQ-1.1-B-5 — deployed-URL sources>0 + real prose
---

# Databricks Deep Research — MANUAL UAT handoff (REQ-1.1-B-5)

## Why this is manual (not an agent failure)

The deployed Databricks App is reachable only from inside the Databricks/corp internal
network and is gated behind interactive Microsoft Entra ID SSO + MFA. The agent:
- CANNOT complete Entra ID SSO/MFA (auth gate — agents do not handle credentials).
- CANNOT reach the App URL from the local browser (internal-network only).

Per the GSD `human_needed` pattern, the deployed-URL UAT is a HUMAN verification item.
Everything the agent COULD do autonomously is already done and green (below).

## Already PROVEN autonomously (do NOT re-do)

- **Deploy SUCCEEDED**: `deployment_id 01f168feac3612adaeb76bd4de4a5608`, status SUCCEEDED,
  app_status RUNNING, compute ACTIVE, update_time 2026-06-15T21:17:37Z.
  URL: `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com`
- **Full Makefile pipeline** (Principle #9 — NOT sync-only): Pass 0 SSG bake confirmed
  (`Uploaded static/research.js`, `Uploaded templates/_research_result.html` in sync log).
- **Deployed KG hydrated**: `LightRAG storage hydration complete: 93 files, 2,734,272,705 bytes`
  (the full ~28k-node UC-Volume store) at 21:29:55 CST + KB DB 44MB + FTS5 293 rows + images.
- **Local 5-step gate PASSED** (databricks-parity, app_entry:app): smoke (serving AUTH+LLM ok),
  uvicorn boot (provider=databricks_serving), curl SSE 5-stage+done, Playwright UI real report
  (answerLen=9002, 7 sources, tables + [1]-[7] citations, IS_OLD_STUB=False), triple-verify.
  Evidence: `arx-2-finish-04-SUMMARY.md` + `.playwright-mcp/arx-uat-01/02-local-dbx-*.png`.

## The ONE manual step (the REQ-1.1-B-5 gate)

On a machine inside the Databricks-accessible network, in a browser logged into Entra ID:

1. Open `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/research/`
   (complete the Entra ID SSO if prompted).
2. Confirm the page renders: hero, query box, "Verify iterations" (1-10), "Run Deep Research"
   button, 5-stage stepper present. Toggle 中/EN — labels switch (深度研究 ↔ Deep Research).
3. Type `What is an AI agent?`, set iterations = 1, click Run.
4. Watch the stepper stream: web_baseline → retriever → reasoner → verifier → synthesizer →
   final report (the deployed Claude-Sonnet serving endpoint is fast; expect < ~60s).
5. **THE GATE — record these:**
   - **Sources count** under "参考来源 / Sources" — MUST be **> 0** (deployed KG is healthy
     ~28k nodes, so expect ~7-10, like the local gate + the Aliyun Branch-A run's 10).
   - Report body is **real LLM prose** (structured report w/ headings + inline [n] citations),
     NOT the bare `# Research Answer / ## Knowledge Graph Retrieval / (entity dump)` stub.
   - Any embedded images render (`/static/img/...`).
6. **PASS** if sources > 0 AND real prose AND stepper completed. **FAIL/STOP** if sources = 0
   (that would be a deployed #44-class KG-join gap — flag it, do NOT mark B-5 passed).

## After you run it

Tell the orchestrator/agent the **sources count** + pass/fail. Then the agent (or you) will:
- Write the authoritative `arx-2-finish-04-VERIFICATION.md` (Agent A's draft is preserved at
  `_agentA-draft-04-VERIFICATION.md`).
- Flip `STATE-Agentic-RAG-v1.1.md` + `ROADMAP-Agentic-RAG-v1.1.md` → arx-2 CLOSED.
- Update `.planning/ISSUES.md`: arx-2 resolved + #44 annotation.

Until then arx-2 stays OPEN with B-5 as the sole outstanding human-UAT item.
