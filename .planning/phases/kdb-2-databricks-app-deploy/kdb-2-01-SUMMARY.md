# kdb-2-01 — SUMMARY

> Plan: `kdb-2-01-app-sp-and-uc-grants-PLAN.md`. Phase: kdb-2 (kb-databricks-v1 milestone, parallel-track). Executed: 2026-05-16 in main session of `/gsd:execute-phase kdb-2` (orchestrator-side execution because Tasks 1.2 + Task 1.3 use `mcp__databricks-mcp-server execute_sql` which is main-session-only per CLAUDE.md).

## REQ result

| REQ | Status | Verification artifact |
|-----|--------|------------------------|
| AUTH-DBX-01 | ✅ | `SHOW GRANTS` row `[459ebc59...,USE CATALOG,CATALOG,mdlg_ai_shared]` (AUTH-EVIDENCE Section 2) |
| AUTH-DBX-02 | ✅ | `SHOW GRANTS` row `[459ebc59...,USE SCHEMA,SCHEMA,mdlg_ai_shared.kb_v2]` (AUTH-EVIDENCE Section 2) |
| AUTH-DBX-03 | ✅ | `SHOW GRANTS` row `[459ebc59...,READ VOLUME,VOLUME,...omnigraph_vault]` + defensive scan: zero `WRITE VOLUME` rows for SP (AUTH-EVIDENCE Section 2) |
| AUTH-DBX-04 | deferred-runtime | Path A inconclusive (Foundation Model endpoints expose no `.id`); both endpoints `READY` with default permissive ACL — Path B in-app probe scheduled at kdb-2-04 Wave 0 (AUTH-EVIDENCE Section 3) |
| AUTH-DBX-05 | deferred-runtime | Apps platform-default behavior; empirical SSO confirmation scheduled at kdb-2-04 Smoke 1 browser session (AUTH-EVIDENCE Section 4) |

3/5 verified now via SQL evidence; 2/5 explicitly deferred to kdb-2-04 runtime probe per documented research findings (RESEARCH.md Q1(c) + Q5).

## Skill invocations baked

Per memory `feedback_skill_invocation_not_reference.md`, the following `Skill()` calls were emitted during execution and have literal substrings preserved in `kdb-2-01-AUTH-EVIDENCE.md` for plan-checker grep verification:

- `Skill(skill="databricks-patterns", args="Confirm 'databricks apps create' v0.260+ behavior: idempotency on existing app + service_principal_client_id field shape in apps get JSON output...")` — invoked in Task 1.1 step 4. The skill confirmed the App resource includes `service_principal_client_id` as the canonical GUID field name (NOT `service_principal_id` integer ID) and `MSYS_NO_PATHCONV=1` Git-Bash CLI guidance for kdb-2-04.
- `Skill(skill="security-review", args="Audit the 3 grant statements about to be issued against UC for the App SP. Confirm: (a) READ VOLUME is granted, NOT WRITE VOLUME...")` — invoked in Task 1.2 step 2. Verdict: SAFE TO PROCEED — (a) READ_VOLUME not WRITE_VOLUME ✅, (b) USE_CATALOG/USE_SCHEMA are minimal-privilege metadata-traversal only ✅, (c) principal is GUID in backticks not friendly name ✅.

## Files modified / created

**Created:**

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-01-AUTH-EVIDENCE.md` (full audit trail, 4 sections + REQ summary table)
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-01-SUMMARY.md` (this file)
- `.scratch/kdb-2-01-app-create.json` (gitignored — full apps get JSON)
- `.scratch/kdb-2-01-sp-client-id.txt` (gitignored — single GUID line)
- `.scratch/kdb-2-01-perms-llm.json` (gitignored — Path A inconclusive marker)
- `.scratch/kdb-2-01-perms-embed.json` (gitignored — Path A inconclusive marker)

**Modified:** None. Pure CLI/SQL plan. Zero source-code changes.

**Specifically NOT modified (Decision 3 + scope discipline):**

- `databricks-deploy/CONFIG-EXEMPTIONS.md` — kdb-2-01 plan PLAN.md § "CONFIG-EXEMPTIONS impact: NONE" — confirmed; only kdb-2-02 (LLM-DBX-01 row) and kdb-2-03 (LLM-DBX-02 row) flip rows
- `databricks-deploy/{startup_adapter.py, lightrag_databricks_provider.py}` — kdb-1.5 frozen territory
- `lib/llm_complete.py` — kdb-2-02 territory
- `kg_synthesize.py` — kdb-2-03 territory
- `kb/services/synthesize.py` — Decision 1 (NOT modified)
- Any `app.yaml` / `Makefile` / `requirements.txt` — kdb-2-04 territory

## Verification cite (per PLAN.md § Verification)

1. **Evidence MD path:** `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-01-AUTH-EVIDENCE.md` — contains 5-row REQ summary table + 4 sections covering App create, UC grants, Foundation Model permissions, SSO gating
2. **SP client_id scratch path:** `.scratch/kdb-2-01-sp-client-id.txt` — single line `459ebc59-0512-4da7-b962-f639312b8df6` (GUID-shape regex verified)
3. **`apps get omnigraph-kb -o json` excerpt:**

   ```json
   {
     "name": "omnigraph-kb",
     "service_principal_client_id": "459ebc59-0512-4da7-b962-f639312b8df6",
     "app_status": { "state": "UNAVAILABLE" },
     "compute_status": { "state": "ACTIVE" },
     "url": "https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com"
   }
   ```

   App is in `UNAVAILABLE` (no source code deployed yet — expected pre-kdb-2-04). Compute is `ACTIVE` so deploy will reach RUNNING quickly.

4. **3 SHOW GRANTS rows for SP (CATALOG / SCHEMA / VOLUME):** verbatim in AUTH-EVIDENCE.md Section 2; reproduced here for executor convenience:

   ```text
   ON CATALOG mdlg_ai_shared:    [459ebc59-...,USE CATALOG,CATALOG,mdlg_ai_shared]
   ON SCHEMA mdlg_ai_shared.kb_v2: [459ebc59-...,USE SCHEMA,SCHEMA,mdlg_ai_shared.kb_v2]
   ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault: [459ebc59-...,READ VOLUME,VOLUME,mdlg_ai_shared.kb_v2.omnigraph_vault]
   ```

5. **Defensive WRITE VOLUME absence (AUTH-DBX-03 hard rule):** Volume-level `SHOW GRANTS` (full unfiltered) returned 13 rows; filtered to App SP `459ebc59-0512-4da7-b962-f639312b8df6`, ONLY the `READ VOLUME` row appears. Zero `WRITE VOLUME` rows for the App SP.

6. **AUTH-DBX-04 verification path:** Path A inconclusive (CLI `serving-endpoints get-permissions` requires endpoint UUID; Foundation Models expose no `.id` field). Path B deferred to kdb-2-04 Wave 0 Step 0 in-app probe via `WorkspaceClient().serving_endpoints.query(name="databricks-claude-sonnet-4-6", ...)`. Both endpoints confirmed `READY` via `serving-endpoints get`. Default permissive ACLs apply to Foundation Models in this workspace per RESEARCH.md Q1(c).

7. **Skill invocation evidence:** literal `Skill(skill="databricks-patterns"` (Section 1) + `Skill(skill="security-review"` (Section 2) substrings present in AUTH-EVIDENCE.md for plan-checker grep.

8. **Git status post-commit:** Will be clean for this plan's tracked files (only the 2 plan-phase docs; .scratch files are gitignored).

## Hard constraints honored

- **(security)** AUTH-DBX-03 `WRITE VOLUME` not granted; defensive SHOW GRANTS check confirmed zero
- **(security)** AUTH-DBX-04 `CAN_QUERY` only — no `CAN_MANAGE` attempted (no grant attempted at all on Foundation Model endpoints; default ACL is sufficient)
- **(scope)** Zero `kb/` / `lib/` / top-level `*.py` modifications — `git diff 4966aa9..HEAD -- kb/ lib/ kg_synthesize.py kb/services/synthesize.py` returns empty for kdb-2-01's commit
- **(scope)** Zero `databricks-deploy/` modifications — kdb-2-01 territory is the workspace + UC, not the source tree
- **(safety)** Forward-only commits; explicit `git add` per `feedback_git_add_explicit_in_parallel_quicks.md`
- **(skills)** `Skill(skill="databricks-patterns")` invoked in Task 1.1; `Skill(skill="security-review")` invoked in Task 1.2 — frontmatter ↔ task invocation 1:1

## Anti-patterns (block list — confirmed honored)

- ❌ Did NOT grant `WRITE VOLUME` (AUTH-DBX-03 hard rule)
- ❌ Did NOT grant `CAN_MANAGE` on any Foundation Model endpoint
- ❌ Did NOT modify any kdb-1.5 territory file
- ❌ Did NOT modify `databricks-deploy/CONFIG-EXEMPTIONS.md` (Decision 3 — kdb-2-02 / kdb-2-03 own those row flips)
- ❌ Did NOT modify any `app.yaml` / `Makefile` / `requirements.txt` (kdb-2-04 territory)
- ❌ Did NOT touch any file under `kb/` (CONFIG-DBX-01 invariant)
- ❌ Did NOT use `git add -A` / `git add .`
- ❌ Did NOT use `git commit --amend` / `git reset --hard`
- ❌ Did NOT run `databricks apps deploy`
- ❌ Did NOT embed any literal API token

## Time elapsed

~15 min (within 0.25d budget; faster than the 95-min estimate because the 3 GRANTs went through MCP cleanly without retry, and Path A failed quickly with structural-limitation evidence rather than spelunking).

## Concurrent-agent context

- kdb-2-02 ran in parallel as background subagent during kdb-2-01 execution (Wave 1 parallelism)
- kdb-2-02 finished while kdb-2-01 was authoring AUTH-EVIDENCE.md
- kdb-2-02 commits (`50a7386`, `5255a9a`, `8fa7636`) landed on `origin/main` cleanly
- kdb-2-01 commit will be `git pull --ff-only` rebased/forwarded onto kdb-2-02's HEAD before push (or push directly if already up-to-date)
- ZERO file overlap between kdb-2-01 and kdb-2-02 file scope — Wave 1 parallel-safety verified empirically

## Done

Plan kdb-2-01 complete. Wave 1 ready for downstream waves:

- **Wave 2** (kdb-2-03) can now spawn — depends_on `kdb-2-02` is satisfied
- **Wave 3** (kdb-2-04) waits on Wave 2 completion + uses SP client_id `459ebc59-0512-4da7-b962-f639312b8df6` from `.scratch/kdb-2-01-sp-client-id.txt`
