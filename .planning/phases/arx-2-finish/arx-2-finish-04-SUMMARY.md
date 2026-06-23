---
phase: arx-2-finish
plan: 04
wave: 5
status: deployed-uat-FAILED
local_gate: PASSED
deploy: SUCCEEDED (01f168feac3612adaeb76bd4de4a5608)
deployed_uat: FAILED — retriever/reasoner/verifier errored, sources=0
completed: null
requirements: [REQ-1.1-B-4, REQ-1.1-B-5]
---

> **2026-06-15 UPDATE — Deployed-URL UAT FAILED (REQ-1.1-B-5 NOT met).** User ran the
> manual UAT (deployed App is internal-network only). Screenshot evidence: on
> `/research/` with query "What is AI Agent?", the stepper showed **Retriever / Reasoner /
> Verifier all FAILED (red), Synthesizer terminal, SOURCES = 0, no report body**. This is
> the explicit "sources=0 → STOP, do not close" gate. **Phase stays OPEN.**
>
> **Infra is provably healthy** (deployed app log): KG loaded 30833 nodes / 44371 edges,
> vdb_entities 30832 @ dim 3072, vdb_chunks 2025, rerank_init_ok provider=databricks_serving,
> singleton_ready 28.44s, `POST /api/research` 200. So the fault is a RUNTIME exception
> INSIDE the research stages (retriever caught it → status=failed → reason on SSE frame),
> NOT config/hydrate/dim. The research retriever uses the SAME
> `omnigraph_search.query.search(mode="hybrid")` as the working /api/synthesize, so the KG
> join is not the differentiator.
>
> **Diagnosis pending the SSE `reason` string** (only capturable from the internal-network
> browser). Leading hypotheses: (a) Vertex embedding SSL/auth failure from the research
> asyncio-worker context; (b) event-loop nesting in how lib/research invokes search() inside
> the running app loop; (c) timeout. Fix is a follow-up debug quick, NOT a Wave-5 re-run.

> **2026-06-17 UPDATE — ROOT-CAUSED + FIXED + REDEPLOYED.** User ran the diagnostic console
> snippet; the SSE `reason` fields gave exact causes:
> - `retriever | failed | GEMINI_API_KEY not found in environment.`
> - `reasoner  | failed | GEMINI_API_KEY not found in environment.`
> - `verifier  | failed | object list can't be used in 'await' expression`
> - `web_baseline | skipped | TAVILY_API_KEY unset` (expected — ar-1 stub mode)
>
> **Two bugs, both confirmed in code, neither a real provider misconfig:**
> 1. `omnigraph_search/query.py:66` — STALE guard raised `GEMINI_API_KEY not found`
>    unconditionally, but `lib.lightrag_embedding` runs in Vertex-SA mode when
>    `GOOGLE_APPLICATION_CREDENTIALS` is set (api_key unused) + LLM is databricks_serving
>    Claude. Databricks app.yaml correctly omits GEMINI_API_KEY → guard wrongly tripped,
>    failing BOTH retriever and reasoner (reasoner calls kg_search → same guard). Fixed:
>    require GEMINI_API_KEY only when NOT in Vertex-SA mode. Commit `f02440e`.
> 2. `lib/research/stages/verifier.py:152` — `await cfg.web_search(q)` but the SYNC
>    `_skipped_web_search` stub is installed when TAVILY_API_KEY unset → `await list` crash.
>    Fixed: await only if `inspect.isawaitable` (mirrors web_baseline.py). Regression test
>    `test_verifier_tolerates_sync_web_search_stub` added (RED-proof confirmed). Commit `f02440e`.
>
> **Deploy-pipeline gap also fixed** (`2a67a73`): `deploy.sh` Pass 0c never staged
> `omnigraph_search/` (a runtime CONTRACT-01 dep) — the workspace held a STALE copy, so Fix 1
> would not have shipped. Added omnigraph_search/ staging + Pass 1 --include.
>
> **Redeployed**: full deploy.sh, `deployment_id 01f16a57d1bd1f899c85d072e499a6c8`, SUCCEEDED/
> RUNNING/ACTIVE, update_time 2026-06-17T14:28:13Z. Both fixed files confirmed in the sync log
> (`Uploaded omnigraph_search/query.py`, `Uploaded lib/research/stages/verifier.py`). 187 research
> tests pass.
>
> **2026-06-17 re-UAT #1 (user, internal-network browser)** — the 2 fixes WORKED:
> `retriever | status= ok | chunk_count: 9` (was failed). web_baseline still `skipped`
> (TAVILY_API_KEY unset — by-design ar-1 stub; NOT a failure — the KG report needs no Tavily).

> **2026-06-17 Tavily enablement (user accepted risk, asked to wire keys permanently).**
> Stored Tavily key in `kb-translate` secret scope key `omnigraph_research_tavily_key`
> (NOT plaintext in app.yaml — app.yaml is public-git-tracked). Granted app SP
> `459ebc59-...` READ on the scope. app.yaml now has a `resources: [tavily-key → secret
> scope/key]` block + `TAVILY_API_KEY: {valueFrom: tavily-key}` env. Commit `8d98f61`
> (no secret value in git — only the reference). Redeployed: `deployment_id
> 01f16a60388a13a982eb76fadb4a48e8` SUCCEEDED/RUNNING/ACTIVE (CLI exited 1 on a network
> drop during status-poll, but server-side deploy completed — verified via apps get).
> **Awaiting user re-UAT #2 of deployed /research/: reasoner/verifier=ok + sources>0 +
> web_baseline now runs (not skipped) → then B-5 PASS and close arx-2.**
> NOTE: user must rotate the 2 Tavily keys pasted in chat (chat-history exposure).

> **2026-06-17 Tavily binding — TWO-PART mechanism (deploy #1 of the secret was incomplete).**
> First Tavily deploy (`01f16a60...`) logged `[BUILD] [ERROR] error resolving resource tavily-key
> for env TAVILY_API_KEY: resource tavily-key not found`. Root cause: app.yaml's `resources:` block
> declares the binding but does NOT register the resource at the app level — Databricks Apps
> requires BOTH:
>   1. **app.yaml**: `env: TAVILY_API_KEY {valueFrom: tavily-key}` + a `resources:` entry (commit 8d98f61).
>   2. **App-level resource registration** (one-time, persists across deploys): `databricks apps
>      update omnigraph-kb --json @.scratch/app-update-tavily.json` with
>      `resources: [{name: tavily-key, secret: {scope: kb-translate, key:
>      omnigraph_research_tavily_key, permission: READ}}]`. VERIFIED this survives subsequent
>      `apps deploy` (resources count stays 1) — so routine deploy.sh runs keep the binding.
> After registering the resource, redeployed (`deployment_id 01f16c168cb51ca29e4577d7e531845b`
> SUCCEEDED) so the build re-resolves valueFrom against the now-registered resource.
> **Awaiting user re-UAT #2 once this deploy hydrates: web_baseline should now run (not skip),
> reasoner/verifier=ok, sources>0 → B-5 PASS → close arx-2.**

> **2026-06-23 re-UAT #2 (user) — bug #3 found + fixed: SSE heartbeat.**
> Stepper showed **retriever GREEN + reasoner GREEN** (the 2 crash bugs CONFIRMED fixed!),
> but the stream died mid-verifier: browser `POST /api/research net::ERR_HTTP2_PROTOCOL_ERROR
> 200`, result panel "network error". Deployed app log proved the server pipeline kept
> running fine (multiple `Final context: NN entities/NN relations/NN chunks` lines, no crash,
> still computing ~278s after POST). Root cause: `kb/api_routers/research.py:_sse_event_stream`
> yielded SSE frames ONLY at stage boundaries; the reasoner/verifier agent-loops run 60-180s+
> with ZERO bytes between frames, and Databricks Apps HTTP/2 ingress resets a stream idle that
> long. NOT a stage crash — a transport-keepalive gap.
> Fix (commit `b7f0645`): background producer task drains the orchestrator into an
> asyncio.Queue; consumer races each get() against `_SSE_HEARTBEAT_SEC=15` and emits a
> `: keepalive` SSE comment on timeout (keeps stream warm; never cancels the producer).
> research.js parseFrame ignores comment frames (no event:/data: line). Regression test
> `test_sse_emits_keepalive_during_slow_stage_gap` added. 188 research tests pass. Redeployed.
> **Awaiting user re-UAT #3: full run completes to synthesizer + sources>0 (no HTTP/2 reset).**


# Wave 5 (plan 04) — Databricks E2E — SUMMARY (local gate PASSED; deploy pending network)

## Status

- **REQ-1.1-B-4 (local 5-step gate): ✅ PASSED** (evidence below).
- **REQ-1.1-B-5 (Databricks deploy + post-deploy UAT): ⏸️ BLOCKED** — network outage hit
  AFTER the user's "go" and AFTER tree reconciliation, BEFORE `bash databricks-deploy/deploy.sh`.
  The deploy + post-deploy UAT need the Databricks workspace + deployed URL (no network).
  NO `apps deploy` was run. The deployed app remains on its 2026-06-01 revision (deployment
  `01f15e15...`, ACTIVE) — UNCHANGED by this session.

**Phase is NOT closed.** The split-reality close requires the post-deploy `sources>0` proof on
the deployed UC-Volume KG, which has not happened. Resume the deploy when network returns.

## Local 5-step gate (REQ-1.1-B-4) — PASSED

Sole-deployer confirmed by user; concurrent session (Agent A) stood down on deploy.

**Step 1 — smoke (serving reachable):** The canned `scripts/smoke_databricks_serving_local.py`
is broken against the current OAuth `dev` profile (hardcodes `auth_type="pat"` at line 62; reads
unset `KB_EMBEDDING_MODEL`). BYPASSED it; called serving directly:
`WorkspaceClient(profile='dev')` (native OAuth, no auth_type override) + certifi corp-CA merge
(`REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE` → `certifi.where()`), then
`serving_endpoints.query(name='databricks-claude-sonnet-4-6', ...)`. **Reproducible 2/2 runs**
→ `AUTH hhu@edc.ca` + `LLM_OK 'ok'`. (Agent A's "list HUNG" was `serving_endpoints.list()` —
heavy enumerate; `.query()` on a named endpoint returns fast.)

**Step 2 — uvicorn `app_entry:app`:** `scripts/run_local_uvicorn.py` booted on :8000,
`lightrag_singleton_ready wall_s=2.77`, graph loaded **2625 nodes / 3412 edges** (LOCAL
`.dev-runtime/databricks-app-local` snapshot — NOT the deployed KG), `provider=databricks_serving`,
`Application startup complete`.

**Step 3 — curl SSE:** `POST /api/research {"query":"What is an AI agent?","max_iterations":1}`
→ `web_baseline → retriever → reasoner → verifier → synthesizer → done` (~103s, 12:45:25→12:47:08).
done payload: markdown 5233 chars, 7 sources, confidence 0.5, note_lines [], **IS_OLD_STUB=False**,
real English report.

**Step 4 — Playwright UI UAT (local):** navigated `http://127.0.0.1:8000/research/`, submitted
query (max_iterations=1). Stepper streamed `web_baseline=done, retriever=done, reasoner=running`
(mid-stream captured) → all 5 `done`. Rendered report **answerLen=9002**, 7 sources — a structured
report ("What Is an AI Agent? A Comprehensive Research Report") with Overview, 5 Key
Characteristics, Anatomy + comparison TABLES, Types, Use Cases, Conclusion, inline [1]-[7]
citations. 2 screenshots: `.playwright-mcp/arx-uat-01-local-dbx-stepper.png`,
`arx-uat-02-local-dbx-report.png`.

**Step 5 — triple verification (all 3 legs):**
- A (network 200): `POST /api/research => 200` (browser + uvicorn logs).
- B (provider call): `provider=databricks_serving`; the 5233/9002-char real reports prove the
  serving LLM (Claude Sonnet 4.6) was invoked, not a stub.
- C (content marker): `IS_OLD_STUB=False`, real structured report w/ tables + citations.

## CONFLICT resolutions (recorded — concurrent-session reconciliation)

1. **Smoke discrepancy** — both observations correct; different calls (see Step 1). The smoke
   script's `auth_type="pat"` bug is real → filed for ISSUES.md.
2. **KG provenance** — local UAT ran against a 2625-node LOCAL snapshot, NOT the deployed KG.
   The deployed app hydrates from UC Volume `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/
   lightrag_storage` (via `_db_bootstrap.py` → `/tmp/...`): measured **graphml 35.9MB (~28k nodes),
   vdb_chunks 57MB, vdb_entities 756MB**. Local green = PIPELINE proof only (Principle #6,
   necessary-not-sufficient). **Databricks FULL proof MUST come from post-deploy UAT confirming
   `sources>0` on the deployed KG.** sources=0 → STOP, flag Databricks #44-class gap, do not close.
3. **Sole deployer** — user confirmed Agent A stood down; git HEAD reconciled clean (contracts
   verified on disk: synthesizer real-LLM, research.js fetch-not-EventSource, export SSG block,
   locale parity 18), research tests 27 passed.

## Deploy plan (to resume when network returns)

1. `bash databricks-deploy/deploy.sh` — FULL pipeline (Pass 0 SSG bake `kb/output → _ssg` carries
   `research/index.html` [root base path confirmed] + Pass 0a overlay `kb/static → _ssg/static`;
   0b lang flip; 0c dep stage; 0d rebrand; Pass 1/2 sync; `apps deploy`). Principle #9: sync-only
   FORBIDDEN. NEVER `apps stop/start` (artifact wipe). PowerShell (Windows path handling).
2. Post-deploy Playwright UAT (main session) against
   `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/research/` — the GATE:
   deployed UC-Volume KG MUST return `sources>0` + real prose.
3. Triple-verify (network 200 + `make logs` LLM call + content marker), screenshots
   `.playwright-mcp/arx-dbx-uat-*.png`.
4. Write authoritative 04-VERIFICATION.md (Agent A's draft preserved at
   `_agentA-draft-04-VERIFICATION.md`).
5. Flip STATE/ROADMAP → arx-2 CLOSED (Databricks full / Aliyun degraded-pending-#44),
   ISSUES.md arx-2 resolved + #44 annotation. Forward-only push.

## Self-Check: PARTIAL (local gate PASSED; deploy blocked on network)

Local 5-step gate green with full evidence. Databricks deploy + post-deploy UAT NOT done
(network outage). Phase NOT closed — Databricks `sources>0` proof outstanding.

> **Heartbeat fix DEPLOYED**: `deployment_id 01f16f16a18014e5a1dd59688774db26` SUCCEEDED/RUNNING/ACTIVE (2026-06-23T15:27Z). Heartbeat code confirmed in deployed research.py (`_SSE_HEARTBEAT_SEC`, `: keepalive`). Tavily resource still bound. Ready for re-UAT #3.

> **2026-06-23 re-UAT #3 → bug#4: Databricks 300s HARD HTTP cap.** Run hit 393s still
> looping in reasoner → platform killed the stream (ERR_HTTP2_PROTOCOL_ERROR). Heartbeat
> prevents IDLE resets but not a hard TOTAL-duration cap. Root cause (measured from log):
> reasoner ran default max_iter_reasoner=5 (8+ kg_search, each cross-border LLM ~30-60s);
> UI slider only capped verifier so reasoner ALWAYS ran 5. Fix (commit f746a7c): cap BOTH
> loops with UI value, default max_iterations 3→1, + anti-buffering headers
> (X-Accel-Buffering: no). 188 tests pass. Deployed 01f16f25742f14cfb259e01d8789328b
> SUCCEEDED; all 3 changes confirmed in deployed source.
> ALSO (non-fatal, deferred): web_baseline shows status=failed when live Tavily call errors
> on Databricks egress — best-effort stage, never raises, pipeline proceeds (cosmetic red).
> **Awaiting user re-UAT #4: full run completes <300s to synthesizer + sources>0.**

> **2026-06-23 web_baseline 401 root-caused + fixed.** re-UAT showed `web_baseline reason=
> 401 Unauthorized` from api.tavily.com (NOT egress-blocked — app reached Tavily, key
> rejected) while `retriever | ok`. Both user-supplied keys tested VALID directly (HTTP 200),
> so the deployed app was sending a MANGLED value: the original `put-secret --string-value -`
> stdin store corrupted it (Windows stdin /truncation). Binding chain verified correct
> end-to-end (scope key omnigraph_research_tavily_key -> app resource tavily-key -> env
> TAVILY_API_KEY -> config.py:67 -> tavily_search api_key). Re-stored the key cleanly via
> file (exactly 41 bytes, no newline) + redeployed 01f16f2a4ae112109eb1a48c52bfcd34 SUCCEEDED.
> **Awaiting final re-UAT: web_baseline ok + all 5 stages green to synthesizer + sources>0.**
