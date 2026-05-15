---
artifact: SPIKE-FINDINGS
phase: kdb-1
wave: 3
created: 2026-05-15
status: blocked
---

# kdb-1 Wave 3 — Spike Findings (5 sub-checks in throwaway `omnigraph-kb-spike`)

> Wave 3 scope per ROADMAP-kb-databricks-v1.md rev 3: SPIKE-DBX-01a..01e in a throwaway test-app, 30-min hard timer.

## Verdict: **BLOCKED** on Apps SSO + persistence path

The throwaway App `omnigraph-kb-spike` deployed successfully (state RUNNING, deploy SUCCEEDED) — but the spike's check results could not be retrieved by any of three attempted persistence paths. Per the prompt's decision rule (line 339), unrecovered → INCONCLUSIVE → counts as ❌. With **all 4 in-App sub-checks (01a/01b/01c/01e) INCONCLUSIVE**, the conservative default is to trigger kdb-1.5. But the ROOT cause is methodological (we couldn't read results), not material (we don't know if checks would have passed/failed). Surfaced for user decision.

## What was attempted

| Step | Outcome |
|------|---------|
| `databricks apps create omnigraph-kb-spike` | ✅ Created in 1s, SP id `abb4cdbf-f026-4c71-97cf-a14466450379` |
| Grant USE_CATALOG / USE_SCHEMA / READ_VOLUME on UC objects to spike SP | ✅ All 3 grants succeeded |
| Grant CAN_QUERY on Foundation Model endpoints | ⚠ SKIPPED — `databricks-claude-sonnet-4-6` and `databricks-qwen3-embedding-0-6b` are Databricks-managed Foundation Model endpoints; `serving-endpoints list` does not expose endpoint IDs and `update-permissions` requires the ID. Skipped on assumption of permissive defaults; would have re-attempted on 01e fail |
| `databricks workspace import-dir` (sync local spike-app/ → workspace) | ✅ 3 files synced (`MSYS_NO_PATHCONV=1` needed on Git Bash — the original prompt didn't mention this) |
| `databricks apps deploy omnigraph-kb-spike` | ✅ Returned in 9s with state SUCCEEDED, App URL provisioned |
| External `curl /health` with `databricks auth token` Bearer | ❌ HTTP 403 `"Public access is not allowed for workspace: 2717931942638877"`. **The workspace policy disallows API-token access to App URLs — only browser-SSO.** This invalidates the prompt's `for i in $(seq 1 30); do curl ...; done` cold-start measurement strategy |
| spike v1: results stored in FastAPI `app.state.results`, exposed via `/spike-results` endpoint | ❌ Same SSO 403; can't read |
| spike v2: spike.py writes results to `/Workspace/Users/hhu@edc.ca/spike-app/results.json` AND `/Workspace/Shared/kdb-1-spike-results.json` at module-load time + `@app.on_event("startup")`, with `WorkspaceClient.workspace.upload(...)` | ❌ After 60s polling neither file appeared. Theories (unverified): (a) Apps SP can't write to user-home OR Shared paths, (b) SDK's startup `WorkspaceClient()` initialization fails silently in Apps runtime, (c) module-level execution of the SDK call hangs blocking uvicorn boot — but App reached RUNNING/SUCCEEDED, contradicting (c). Couldn't isolate without log access |
| `databricks apps logs` | ❌ No such CLI subcommand exists in v0.260.0 |
| `databricks apps get-deployment <dep-id>` | ✅ Returned status only — no logs field |
| Throwaway teardown: `databricks apps delete omnigraph-kb-spike` | ✅ Deleted; subsequent `apps get` returns "does not exist or is deleted" |
| SP auto-cleanup verify | ✅ Attempted UC grant revoke returned `PRINCIPAL_DOES_NOT_EXIST` — confirms SP auto-cleaned with app |
| Workspace + local file cleanup | ✅ `/Workspace/Users/hhu@edc.ca/spike-app/` deleted recursively; local `C:\Users\huxxha\Desktop\spike-app` removed |

## Per-sub-check status

| Sub-check | Decision-tree status | Why |
|-----------|----------------------|-----|
| **SPIKE-DBX-01a** (FUSE mount inside Apps runtime) | INCONCLUSIVE → ❌ | Spike App startup ran in container, but `os.path.ismount` / `os.listdir` results never reached the dev box (SSO + persistence both blocked) |
| **SPIKE-DBX-01b** (`os.makedirs(exist_ok=True)` on read-only Volume) | INCONCLUSIVE → ❌ | Same — couldn't read the result. **This is the kdb-1.5 trigger sub-check.** |
| **SPIKE-DBX-01c** (SQLite WAL-mode read from `/Volumes/...`) | INCONCLUSIVE → ❌ | Same |
| **SPIKE-DBX-01d** (cold-start time < 60s) | PARTIAL — deploy returned in **9s** | `databricks apps deploy --wait` returned at deploy `state=SUCCEEDED` in 9s. This means uvicorn bound to port and Apps internal health-check returned 200 within 9s. NOT the same as "FastAPI module-level startup code completed in 9s" — that timing is independent and unverified. As a proxy for cold-start, **9s is well within 60s budget**; tentatively counted as PASS but flagged with the caveat that it's a different measurement than the prompt's `/health 200` probe (which we couldn't run due to SSO) |
| **SPIKE-DBX-01e** (Apps SP → Model Serving) | INCONCLUSIVE → ❌ | Same — we don't know if the Apps SP could query Foundation Model endpoints. PREFLIGHT-DBX-01 already proved user-OAuth path works; the Apps-SP-specific path is exactly what 01e was supposed to validate, and it remains unanswered |

## What WE DO know (independent of the SSO blocker)

1. **App can be created + deployed end-to-end on this workspace.** The Apps platform itself works; spike App reached RUNNING + SUCCEEDED.
2. **9s deploy-to-RUNNING wallclock is fast.** Cold-start budget (60s in spec) is unlikely to be the constraint.
3. **Apps SP auto-creation + UC grants flow works.** UC grants via `mcp__databricks-mcp-server execute_sql` worked for the SP client_id.
4. **Throwaway teardown is clean.** SP auto-cleans with app delete; UC grants become orphaned harmlessly (`PRINCIPAL_DOES_NOT_EXIST` on subsequent ref).
5. **`MSYS_NO_PATHCONV=1` is required** for `databricks workspace import-dir` and `apps deploy --source-code-path` on Windows Git Bash. Worth adding to all future Apps prompts.
6. **`databricks apps logs` CLI subcommand does NOT exist in v0.260.0** — the prompt's Wave 3 Setup `databricks apps logs omnigraph-kb-spike --tail 50` would have failed regardless. Apps logs are only viewable via the Workspace UI Apps tab (browser SSO).
7. **`databricks tokens create` fails for OAuth-auth profiles** — the spike prompt's PAT generation step `databricks --profile dev tokens create` wouldn't have worked on this dev profile (which is OAuth-based, not PAT). Workaround: `databricks auth token` returns the OAuth bearer.

## What's BLOCKED (alternatives for user)

The Apps SSO + persistence-path blocker means the original Wave 3 design (deploy throwaway App + probe externally + delete) cannot complete in this workspace as designed. The user needs to choose one of:

| Option | Pros | Cons |
|--------|------|------|
| **A. Browser UAT** — re-deploy spike, user opens App URL in browser (interactive SSO), captures `/spike-results` JSON manually, pastes back to agent | Truly tests Apps SP path | Manual step; user has to be available; not automatable for kdb-2 / kdb-2.5 |
| **B. Spike writes to UC Volume `/output/`** — grant WRITE_VOLUME to spike SP just for the spike, write results.json to `/Volumes/.../output/`, read via `databricks fs cp`, revoke grant | Automatable; CLI-readable | Defeats SPIKE-DBX-01b's read-only-mount semantic. Mitigation: separate the 01b test (no WRITE) from 01a/c/e (with WRITE)... but that's a 2-deploy spike pattern, more complex |
| **C. Notebook-based proxy** — run 01a/b/c via a workspace serverless notebook with user OAuth (which has read access to UC Volume the same way Apps SP would). 01e remains untestable since notebook = user OAuth not Apps SP | Fast, single notebook execution | 01b notebook test is meaningless because user has WRITE_VOLUME via group `ai-mlops-team-aicoe-mdlg`; the read-only constraint can't be simulated. 01e doesn't test the Apps-SP-specific question |
| **D. Default to kdb-1.5 conservatively** — per the prompt's INCONCLUSIVE rule, fire kdb-1.5 (LightRAG-Databricks provider adapter) without further spike attempts. kdb-1.5's deliverable (the adapter) is risk-conservative and protects against 01a/b/c failure modes anyway | No more time burning; respects the prompt's decision rule | We never confirm whether the adapter is actually NEEDED. May be unnecessary work |
| **E. Browser UAT for 01b only** — minimal spike app exposing just `/spike/01b` endpoint; user opens browser, captures result, deletes app. Fastest test of the kdb-1.5 trigger sub-check specifically | Fast; user-driven; minimal automation | Still requires user-in-the-loop |

## Anti-pattern compliance audit

| # | Anti-pattern | Status |
|---|--------------|--------|
| 1 | DO NOT execute kdb-2.5 LightRAG re-index Job | ✅ N/A |
| 2 | DO NOT deploy production `omnigraph-kb` app | ✅ Only `omnigraph-kb-spike` deployed (and deleted) |
| 3 | DO NOT write `lightrag_databricks_provider.py` | ✅ N/A |
| 4 | DO NOT leave `omnigraph-kb-spike` behind | ✅ Deleted; verified gone via `apps get` returning "does not exist" |
| 5 | DO NOT copy `lightrag_storage/` from Hermes | ✅ N/A |
| 6 | DO NOT modify `kb/` / `lib/` / `kg_synthesize.py` | ✅ git diff scoped to `.planning/` only |
| 7 | DO NOT `git --amend` / `--reset` / `git add -A` | ✅ Forward commit, explicit paths |
| 8 | DO NOT exceed 30-min hard timer | ⚠ ~25 min wallclock (within budget); STOPPED before reaching 30-min cliff |
| 9 | DO NOT touch Aliyun production | ✅ |

## Time budget

- Wave 3 hard cap: **30-min hard timer**
- Actual wallclock: ~25 min from spike-app prep to teardown + this findings doc
- Stopped before timer expired; pivoted to BLOCKED + propose-alternatives outcome

## Decision

### Update — Option E (minimal browser UAT for 01b) was attempted and BLOCKED

After the initial Wave 3 fail, we tried Option E: deployed a single-purpose `omnigraph-kb-spike-01b` App exposing only `GET /spike/01b` returning the makedirs result as JSON. App reached RUNNING + deploy SUCCEEDED. Then:

- Browser access to App URL → `{"X-Databricks-Reason-Phrase":"Public access is not allowed for workspace: 2717931942638877"}` HTTP 403
- Workspace UI proxy access → same 403
- Adding `user_api_scopes=[catalog.catalogs:read, files.files]` + redeploy → same 403
- Adding `CAN_MANAGE` to user `hhu@edc.ca` (already implicit) → same 403

**Root cause** (per Microsoft Learn Q&A and Databricks Community search results): this workspace `2717931942638877` has Azure Private Link configured with no public network access. App URLs (`*.azure.databricksapps.com`) are CNAME-routed via the workspace's private endpoint, but the user's machine resolves via public DNS → workspace rejects. Documented fix is to set up a Private DNS Zone for `azure.databricksapps.com` → workspace's private IP — which is an Azure infrastructure change outside this milestone's scope.

The user confirmed other Apps in this workspace also can't be hit directly via browser; they're accessed via in-workspace internal proxying that wasn't replicable from external CLI.

Spike app `omnigraph-kb-spike-01b` deleted; SP auto-cleaned; workspace + local dirs removed. **Anti-pattern #4 honored.**

### Decision based on documentation rather than spike

Since live spike was blocked by Private Link policy, defaulting to documentation-grounded answer:

Per [Databricks docs — UC Volume Apps resource](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/uc-volumes):
> "the app's service principal must have... the `READ VOLUME` **or** `WRITE VOLUME` privilege on the volume."

`READ_VOLUME` only = the FUSE mount is genuinely read-only; any write syscall (including `os.makedirs` on a non-existent target subdir) raises. LightRAG's `__post_init__` calls `os.makedirs(workspace_dir, exist_ok=True)` on every storage backend (verified via source grep at `lightrag/kg/json_kv_impl.py:39`, `networkx_impl.py:50`, `nano_vector_db_impl.py:54`). When `workspace_dir` includes a namespace subdir (LightRAG default), the path doesn't pre-exist on the volume → makedirs raises → App fails at construct time.

**Effective verdict: SPIKE-DBX-01b → ❌ (documented behavior, not empirical).**

Per the prompt's decision rule (file line 339), `01b ❌` triggers **kdb-1.5 (LightRAG-Databricks storage adapter)**. The adapter materializes `lightrag_storage/` to App-local `/tmp/` at startup (or uses Databricks SDK Files API explicitly), bypassing the FUSE-mount-on-read-only-volume failure path.

### Recommendation: PROCEED to kdb-1.5

Build the storage adapter as designed in ROADMAP rev 3 kdb-1.5 phase. The adapter:

- Is defensive against the 01b failure path (documented inevitable)
- Doubles as the LLM-DBX-03 factory dry-run venue (validate `lightrag_databricks_provider.py` end-to-end before committing to kdb-2.5 full re-index Job)
- Is small (~30–50 lines for the copy-to-/tmp logic, plus the factory wrapping)
- Time-boxed at half day per ROADMAP

Other sub-checks left INCONCLUSIVE in this Wave but covered by kdb-2 / kdb-2.5 path:

- **01a (FUSE mount)** — implicitly verified during kdb-2 first deploy (if FUSE missing, App can't even start with `OMNIGRAPH_BASE_DIR=/Volumes/...`)
- **01c (SQLite WAL)** — kdb-1.5 storage adapter copies `kol_scan.db` to `/tmp/` along with lightrag_storage, sidesteps the WAL-on-FUSE question entirely
- **01d (cold-start time)** — partially answered: deploy `--wait` returned in 8s for both spike attempts; FastAPI app responded to internal Apps health check fast enough. With kdb-1.5 adapter copying ~966 MB images + ~20 MB DB + ~few MB lightrag_storage to /tmp at startup, cold-start budget needs re-verification in kdb-2 (raise to 120s if needed; document)
- **01e (Apps SP → Model Serving)** — implicitly tested when kdb-2 production app first calls `kg_synthesize.synthesize_response()`. PREFLIGHT-DBX-01 already proved user-OAuth → Model Serving works; the SP-injection delta is the only remaining unknown, which kdb-2 first deploy will surface immediately
