---
phase: kdb-2
plan_id: kdb-2-01
slug: app-sp-and-uc-grants
wave: 1
depends_on: []
estimated_time: 0.25d
requirements:
  - AUTH-DBX-01
  - AUTH-DBX-02
  - AUTH-DBX-03
  - AUTH-DBX-04
  - AUTH-DBX-05
skills:
  - databricks-patterns
  - security-review
---

# Plan kdb-2-01 — App SP + UC Grants + Workspace SSO Verification

## Objective

Stand up the Databricks App service principal `app-omnigraph-kb` (created implicitly by `databricks apps create`) and apply the 5 access grants required for the App to read UC Volume + query MosaicAI Foundation Model endpoints + be SSO-gated.

Maps to: AUTH-DBX-01 (USE CATALOG), AUTH-DBX-02 (USE SCHEMA), AUTH-DBX-03 (READ VOLUME — NO WRITE), AUTH-DBX-04 (CAN_QUERY on `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b`), AUTH-DBX-05 (workspace SSO gating).

NOTE: The actual `databricks apps create omnigraph-kb` command runs in plan kdb-2-04 (deploy). This plan REQUIRES the App SP client_id to be available — so the plan is structured as: (a) wait for kdb-2-04 to do `apps create` first OR (b) run `apps create` here as a Wave-0 step and let kdb-2-04 do the deploy. **This plan does the create.** Per RESEARCH.md Q1 + Q8 sp-grants recipe, `databricks apps create omnigraph-kb` is a non-deploying operation that creates the SP and reserves the App name; the deploy in kdb-2-04 then `apps deploy`s code into that App. Splitting create from deploy is ergonomic and lets grants land before deploy so the App boots with auth ready.

## Read-first

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q1 (lines 88-184) — full grant SQL + Path A/B AUTH-DBX-04 verification
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q8 (lines 853-870) — `make sp-grants` recipe shape
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 28-32 — AUTH-DBX-01..05 definitions
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-SPIKE-FINDINGS.md` lines 22-23 — kdb-1 spike App SP grant precedent
- `.planning/STATE-kb-databricks-v1.md` lines 47-50 — locked defaults: catalog=`mdlg_ai_shared`, schema=`kb_v2`, volume=`omnigraph_vault`, app name=`omnigraph-kb`
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-CONTEXT.md` § "Six locked decisions" + § "Hard constraints"

## Scope

### In scope

- `databricks apps create omnigraph-kb` (creates App + SP, reserves name; does NOT deploy code)
- Discover App SP client_id via `databricks apps get omnigraph-kb -o json | jq -r '.service_principal_client_id'`
- Run 3 UC grant SQL statements via `mcp__databricks-mcp-server execute_sql` (USE CATALOG, USE SCHEMA, READ VOLUME)
- Verify all 3 grants via `SHOW GRANTS` SQL filtered to the App SP client_id
- Verify AUTH-DBX-04 (CAN_QUERY on 2 Foundation Model endpoints):
  - **Path A** — `databricks --profile dev serving-endpoints get-permissions <endpoint-name>` for both `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b`
  - **Path B fallback** — record that runtime in-app verification is the secondary path; actual in-app probe runs during kdb-2-04 first deploy
- Confirm AUTH-DBX-05 (workspace SSO gating) is documented as Apps-default behavior (no explicit grant needed; verified end-to-end in kdb-2-04 Smoke 1 browser session)
- Capture all evidence (App SP client_id, SHOW GRANTS rows, get-permissions JSON) into `kdb-2-01-AUTH-EVIDENCE.md` for audit traceability

### Out of scope

- `databricks apps deploy omnigraph-kb` (kdb-2-04)
- `app.yaml` authorship (kdb-2-04)
- LLM dispatcher work (kdb-2-02)
- Any modification to UC schema / volume / data (those landed in kdb-1)
- `WRITE_VOLUME` grant — **forbidden by AUTH-DBX-03** (security-review skill must catch any drift)
- `CAN_MANAGE` on Foundation Model endpoints — only `CAN_QUERY` per AUTH-DBX-04

### CONFIG-EXEMPTIONS impact

NONE. This plan modifies ZERO files under `kb/`, `lib/`, or top-level `*.py`. Pure CLI + SQL operations. No CONFIG-EXEMPTIONS update.

## Tasks

### Task 1.1 — Create the App (databricks apps create) and discover SP client_id

**Read-first:**
- `kdb-2-RESEARCH.md` Q1 lines 92-112 — App created → SP auto-created with client_id pattern; precedent in kdb-1 SPIKE
- `kdb-2-RESEARCH.md` Q8 lines 853-866 — sp-grants recipe shape

**Action:**

1. Run `databricks --profile dev apps create omnigraph-kb` (idempotent — if App already exists from a prior partial run, the command surfaces a clean error and we proceed to step 2 to fetch the existing SP)
2. Fetch the App's auto-created SP client_id:
   ```bash
   databricks --profile dev apps get omnigraph-kb -o json > .scratch/kdb-2-01-app-create.json
   jq -r '.service_principal_client_id' .scratch/kdb-2-01-app-create.json
   ```
3. Capture the GUID into `.scratch/kdb-2-01-sp-client-id.txt` (single-line file, no whitespace) for the rest of this plan + plan kdb-2-04 to consume
4. Invoke `Skill(skill="databricks-patterns")` with args `"Confirm 'databricks apps create' v0.260+ behavior: idempotency on existing app + service_principal_client_id field shape in apps get JSON output. Verify 'databricks apps get omnigraph-kb -o json' returns service_principal_client_id (not service_principal_id or principal_client_id)."` — record the skill output substring quote in SUMMARY.md
5. Append to `kdb-2-01-AUTH-EVIDENCE.md`:
   - Section "App create"
   - The exact `databricks apps create` command + raw output
   - The SP client_id value (this is a GUID; safe to commit per kdb-1 SPIKE-FINDINGS pattern of recording `abb4cdbf-...` directly — it's an identifier, not a secret)
   - The `databricks apps get omnigraph-kb -o json` excerpt showing `name`, `state`, `service_principal_client_id`

**Acceptance** (grep-verifiable):
- `cat .scratch/kdb-2-01-sp-client-id.txt | wc -l` returns `1`
- `cat .scratch/kdb-2-01-sp-client-id.txt | grep -cE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'` returns `1` (GUID shape)
- `databricks --profile dev apps get omnigraph-kb -o json | jq -r '.name'` returns `omnigraph-kb`
- `kdb-2-01-AUTH-EVIDENCE.md` contains literal `Skill(skill="databricks-patterns"` (≥1 occurrence — for plan-checker grep)

**Done:** App `omnigraph-kb` exists in workspace, SP client_id captured to local scratch file + evidence MD.

**Time estimate:** 20 min (most of which is the `apps create` itself).

### Task 1.2 — Apply USE CATALOG + USE SCHEMA + READ VOLUME grants (AUTH-DBX-01..03)

**Read-first:**
- `kdb-2-RESEARCH.md` Q1(b) lines 114-132 — concrete grant SQL with backticked GUID principal
- `kdb-2-RESEARCH.md` Q1(b) line 122 — explicit "DO NOT grant WRITE VOLUME — AUTH-DBX-03 forbids it"
- CLAUDE.md "Databricks MCP — key tools" — `execute_sql` is the SQL execution channel; warehouse_id `eaa098820703bf5f` is the default

**Action:**

1. Read `.scratch/kdb-2-01-sp-client-id.txt` into a shell variable `CLIENT_ID`
2. Invoke `Skill(skill="security-review")` with args `"Audit the 3 grant statements about to be issued against UC for the App SP. Confirm: (a) READ VOLUME is granted, NOT WRITE VOLUME (AUTH-DBX-03 hard rule); (b) USE CATALOG and USE SCHEMA are minimal-privilege (read-side metadata only); (c) the principal is the App SP client_id GUID (backticked), not a friendly name."` — record output substring in evidence MD
3. Issue 3 grant SQL statements via `mcp__databricks-mcp-server execute_sql` (warehouse_id `eaa098820703bf5f`):
   ```sql
   GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO `<CLIENT_ID>`;
   GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO `<CLIENT_ID>`;
   GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO `<CLIENT_ID>`;
   ```
   (Each statement is a separate `execute_sql` call — MCP doesn't pipeline; substitute `<CLIENT_ID>` with the actual GUID literal in the SQL string before invoking.)
4. **Defensive — confirm WRITE VOLUME was NOT granted.** Run `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault` (no filter), capture output, grep that no row has `WRITE VOLUME` for the App SP client_id.
5. Append all 3 grant SQL + outputs to `kdb-2-01-AUTH-EVIDENCE.md` "Section 2 — UC grants"

**Acceptance** (grep-verifiable):
- After all 3 grants, `SHOW GRANTS ON CATALOG mdlg_ai_shared` filtered to the SP client_id returns ≥1 row with privilege `USE CATALOG`
- After all 3 grants, `SHOW GRANTS ON SCHEMA mdlg_ai_shared.kb_v2` filtered to the SP client_id returns ≥1 row with privilege `USE SCHEMA`
- After all 3 grants, `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault` filtered to the SP client_id returns ≥1 row with privilege `READ VOLUME`
- After all 3 grants, `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault` filtered to the SP client_id returns ZERO rows with privilege `WRITE VOLUME` (defensive AUTH-DBX-03 check)
- `kdb-2-01-AUTH-EVIDENCE.md` contains literal `Skill(skill="security-review"` (≥1 occurrence)

**Done:** App SP can `USE CATALOG mdlg_ai_shared`, `USE SCHEMA kb_v2`, and `READ VOLUME omnigraph_vault`. Cannot write. Verified via SHOW GRANTS.

**Time estimate:** 30 min (3 grants + 4 SHOW GRANTS + skill invoke + evidence appending).

### Task 1.3 — Verify CAN_QUERY on Foundation Model endpoints (AUTH-DBX-04)

**Read-first:**
- `kdb-2-RESEARCH.md` Q1(c) lines 134-184 — Path A CLI + Path B in-app probe; kdb-1 SPIKE-FINDINGS line 23 punted on this; Path A grammar TBD
- `.planning/STATE-kb-databricks-v1.md` lines 47-49 — locked endpoint names: `databricks-claude-sonnet-4-6` (LLM) + `databricks-qwen3-embedding-0-6b` (embedding)

**Action:**

1. Try Path A — `databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6 -o json` and capture output:
   ```bash
   databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6 -o json > .scratch/kdb-2-01-perms-llm.json 2>&1 || true
   databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b -o json > .scratch/kdb-2-01-perms-embed.json 2>&1 || true
   ```
   (`|| true` because per RESEARCH Q1(c) the CLI grammar is TBD; if it fails, we fall through to Path B)
2. Examine each JSON file. **If Path A succeeds** AND each shows the App SP client_id with permission level containing `CAN_QUERY` (or any QUERY-equivalent grant): AUTH-DBX-04 satisfied via Path A. Capture the JSON excerpts to `kdb-2-01-AUTH-EVIDENCE.md`.
3. **If Path A fails** (either CLI rejects "unknown command", or returns permissions with NO entry for the App SP, or returns a non-JSON error): document the Path A failure mode + reasoning in evidence MD, and explicitly state "AUTH-DBX-04 will be verified at runtime via in-app probe during kdb-2-04 Smoke 1 — see kdb-2-04 Wave 0 Step 0".
4. Per RESEARCH Q1(c) Foundation Model endpoints in this workspace use permissive default ACLs for any authenticated SP — Path A returning "no explicit permission entry" is NOT a failure; it just means defaults apply.
5. Append the verification path taken (A or B-deferred) to `kdb-2-01-AUTH-EVIDENCE.md` "Section 3 — Foundation Model permissions".

**Acceptance** (grep-verifiable):
- `.scratch/kdb-2-01-perms-llm.json` exists (whether success or error capture)
- `.scratch/kdb-2-01-perms-embed.json` exists
- `kdb-2-01-AUTH-EVIDENCE.md` "Section 3" exists and explicitly states one of: `"Path A satisfied"` OR `"Path A inconclusive — deferred to kdb-2-04 Wave 0 Step 0 in-app probe"` (literal substring grep)

**Done:** AUTH-DBX-04 status is unambiguous — either Path A green-confirmed in evidence MD, or explicitly deferred to runtime verification with rationale recorded.

**Time estimate:** 20 min (CLI probe both endpoints + reasoning + evidence).

### Task 1.4 — Document AUTH-DBX-05 (SSO gating) + close evidence MD

**Read-first:**
- `kdb-2-RESEARCH.md` Q5 lines 553-625 — Apps SSO + Private Link details
- `.planning/PROJECT-kb-databricks-v1.md` line 70 — "App user authentication — workspace SSO, internal preview only"

**Action:**

1. AUTH-DBX-05 needs no explicit grant — Databricks Apps default behavior gates ALL App access on workspace SSO. There's no "anonymous=false" toggle to set; it's the platform default.
2. Append `kdb-2-01-AUTH-EVIDENCE.md` "Section 4 — AUTH-DBX-05 (SSO gating)" with:
   - Statement: "AUTH-DBX-05 is satisfied by Databricks Apps default behavior — App access requires workspace SSO; no anonymous access. Empirically verified during kdb-2-04 Smoke 1 browser-SSO interactive UAT (App URL → SSO prompt observed)."
   - Reference to RESEARCH.md Q5 confirming Private Link + SSO posture in this workspace
3. Finalize `kdb-2-01-AUTH-EVIDENCE.md` with a top-level summary table mapping each AUTH-DBX-NN REQ to its verification artifact + status
4. Commit-staging note (executor-side, NOT this plan): `git add .planning/phases/kdb-2-databricks-app-deploy/kdb-2-01-AUTH-EVIDENCE.md` (explicit; per `feedback_git_add_explicit_in_parallel_quicks.md`)

**Acceptance** (grep-verifiable):
- `kdb-2-01-AUTH-EVIDENCE.md` contains a top-level table with 5 rows — one per AUTH-DBX-01..05 — each with explicit `✅` or `deferred-runtime` status
- File contains literal `AUTH-DBX-05` substring with verification narrative
- File contains literal `Skill(skill="databricks-patterns"` AND `Skill(skill="security-review"` (each ≥1 occurrence — frontmatter skills baked)

**Done:** All 5 AUTH-DBX REQs have explicit verification artifacts + status in evidence MD. Plan ready for SUMMARY commit.

**Time estimate:** 15 min.

## Verification (what `kdb-2-01-SUMMARY.md` MUST cite)

1. Path to `kdb-2-01-AUTH-EVIDENCE.md` containing the 5-row REQ summary table
2. Path to `.scratch/kdb-2-01-sp-client-id.txt` containing the App SP GUID
3. Verbatim `databricks apps get omnigraph-kb -o json | jq '{name,state,service_principal_client_id}'` output
4. The 3 SHOW GRANTS rows for the App SP (CATALOG/SCHEMA/VOLUME) — verbatim or paraphrased with structure preserved
5. The defensive WRITE VOLUME absence check (AUTH-DBX-03)
6. AUTH-DBX-04 verification path (A or B-deferred) with rationale
7. Skill invocation evidence — literal `Skill(skill="databricks-patterns"` and `Skill(skill="security-review"` substrings (each ≥1 in SUMMARY.md per `feedback_skill_invocation_not_reference.md`)
8. `git status` post-commit clean for this plan's files (`databricks-deploy/CONFIG-EXEMPTIONS.md` UNTOUCHED — Decision 3 means no row flip in this plan)

## Hard constraints honored

This plan honors the following hard constraints from `kdb-2-CONTEXT.md`:

- **(security)** AUTH-DBX-03 `WRITE_VOLUME` is NOT granted; explicitly defensively-checked via SHOW GRANTS post-grant (Task 1.2 step 4)
- **(security)** AUTH-DBX-04 uses `CAN_QUERY` only — `CAN_MANAGE` is not in scope; security-review skill audits this
- **(scope)** Zero `kb/` / `lib/` / top-level `*.py` modifications — pure CLI/SQL plan (CONFIG-DBX-01 invariant clean)
- **(safety)** Forward-only commits via `git add <explicit-files>` only; no `git add -A` / `--amend` / `reset`
- **(skills)** `Skill(skill="databricks-patterns")` invoked in Task 1.1; `Skill(skill="security-review")` invoked in Task 1.2 — frontmatter ↔ task invocation 1:1

## Anti-patterns (block list)

This plan MUST NOT:
- Grant `WRITE VOLUME` to the App SP (AUTH-DBX-03 hard rule)
- Grant `CAN_MANAGE` on any Foundation Model endpoint (AUTH-DBX-04 specifies `CAN_QUERY` only)
- Modify `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 territory; frozen)
- Modify `databricks-deploy/CONFIG-EXEMPTIONS.md` (Decision 3 — no row flip in this plan)
- Modify `app.yaml`, `Makefile`, or any deploy artifact (kdb-2-04 territory)
- Touch any file under `kb/` (CONFIG-DBX-01 — outside exemption list)
- Use `git add -A` or `git add .` (per `feedback_git_add_explicit_in_parallel_quicks.md`)
- Use `git commit --amend` or `git reset --hard` (per `feedback_no_amend_in_concurrent_quicks.md`)
- Run `databricks apps deploy` (that's kdb-2-04 territory)
- Embed any literal API token in commit text (per `feedback_no_literal_secrets_in_prompts.md`)

## Estimated time total

0.25d (Task 1.1: 20 min + Task 1.2: 30 min + Task 1.3: 20 min + Task 1.4: 15 min + buffer ≈ 95 min ≈ 0.2-0.25d)
