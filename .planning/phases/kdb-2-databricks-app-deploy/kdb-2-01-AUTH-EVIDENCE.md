# kdb-2-01 — AUTH Evidence

> Audit-traceable evidence for AUTH-DBX-01..05 verification. Authored 2026-05-16 in main session of `/gsd:execute-phase kdb-2`.

## Top-level REQ summary

| REQ | Description | Verification | Status |
|-----|-------------|--------------|--------|
| AUTH-DBX-01 | App SP `app-omnigraph-kb` has `USE CATALOG` on `mdlg_ai_shared` | `SHOW GRANTS` row `[459ebc59...,USE CATALOG,CATALOG,mdlg_ai_shared]` (Section 2) | ✅ |
| AUTH-DBX-02 | App SP has `USE SCHEMA` on `mdlg_ai_shared.kb_v2` | `SHOW GRANTS` row `[459ebc59...,USE SCHEMA,SCHEMA,mdlg_ai_shared.kb_v2]` (Section 2) | ✅ |
| AUTH-DBX-03 | App SP has `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault`; NO `WRITE VOLUME` | `SHOW GRANTS` row `[459ebc59...,READ VOLUME,VOLUME,...omnigraph_vault]` + defensive scan: zero `WRITE VOLUME` rows for SP (Section 2) | ✅ |
| AUTH-DBX-04 | App SP has `CAN QUERY` on `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b` | Path A inconclusive (Foundation Model endpoints expose no `.id`; CLI `get-permissions` requires UUID); both endpoints READY with default permissive ACL — Path B deferred to kdb-2-04 Wave 0 Step 0 runtime in-app probe (Section 3) | deferred-runtime |
| AUTH-DBX-05 | App access gated by Databricks workspace SSO | Apps platform default — verified empirically during kdb-2-04 Smoke 1 browser session (Section 4) | deferred-runtime |

3/5 verified now via SQL evidence; 2/5 deferred to kdb-2-04 runtime probe per documented research findings.

---

## Section 1 — App create

**Command:**

```bash
databricks --profile dev apps create omnigraph-kb
```

**Result:** App created. Key fields from `databricks --profile dev apps get omnigraph-kb -o json` (full JSON in `.scratch/kdb-2-01-app-create.json`):

```json
{
  "name": "omnigraph-kb",
  "id": "459ebc59-0512-4da7-b962-f639312b8df6",
  "service_principal_client_id": "459ebc59-0512-4da7-b962-f639312b8df6",
  "service_principal_id": 142869694197632,
  "service_principal_name": "app-529s0g omnigraph-kb",
  "url": "https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com",
  "create_time": "2026-05-16T23:55:58Z",
  "creator": "hhu@edc.ca",
  "app_status": { "state": "UNAVAILABLE", "message": "App has not been deployed yet. Run your app by deploying source code" },
  "compute_status": { "state": "ACTIVE", "message": "App compute is running." }
}
```

App SP client_id captured to `.scratch/kdb-2-01-sp-client-id.txt` (single GUID line, no whitespace; `wc -l` returns 1; GUID-shape regex `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` matches).

**Skill verification (Task 1.1 step 4):** `Skill(skill="databricks-patterns", args="Confirm 'databricks apps create' v0.260+ behavior: idempotency on existing app + service_principal_client_id field shape...")` invoked. The skill confirmed via Context7 + skill body content that:
- `POST /apps` is the underlying API (CLI translates to it)
- App resource includes `service_principal_client_id` field as a top-level GUID
- `MSYS_NO_PATHCONV=1` is required on Windows Git Bash for path-arg CLI commands (relevant for kdb-2-04)

Empirical confirmation: actual response shows `service_principal_client_id` as the canonical GUID field name (NOT `service_principal_id` which is an integer numeric ID, NOT `principal_client_id`).

---

## Section 2 — UC grants (AUTH-DBX-01..03)

**Skill audit (Task 1.2 step 2):** `Skill(skill="security-review", args="Audit the 3 grant statements about to be issued against UC for the App SP...")` invoked. Verdict: **SAFE TO PROCEED** —
- (a) `READ VOLUME` granted, NOT `WRITE VOLUME` — AUTH-DBX-03 hard rule honored
- (b) `USE CATALOG` and `USE SCHEMA` are read-side metadata-traversal privileges only — minimal-privilege; do not imply CREATE / MODIFY / SELECT-on-tables
- (c) Principal is the App SP client_id GUID `459ebc59-0512-4da7-b962-f639312b8df6` in backticks, NOT a friendly name (`app-529s0g omnigraph-kb`)

**Statements issued via `mcp__databricks-mcp-server execute_sql` (warehouse_id `eaa098820703bf5f`):**

```sql
GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO `459ebc59-0512-4da7-b962-f639312b8df6`;
GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO `459ebc59-0512-4da7-b962-f639312b8df6`;
GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO `459ebc59-0512-4da7-b962-f639312b8df6`;
```

All 3 returned `{"columns":null,"rows":null}` — DDL success shape.

**Verification — `SHOW GRANTS` rows for SP:**

```text
SHOW GRANTS `459ebc59-0512-4da7-b962-f639312b8df6` ON CATALOG mdlg_ai_shared:
  Principal                              ActionType    ObjectType  ObjectKey
  459ebc59-0512-4da7-b962-f639312b8df6  USE CATALOG   CATALOG     mdlg_ai_shared
  account users                          BROWSE        CATALOG     mdlg_ai_shared

SHOW GRANTS `459ebc59-0512-4da7-b962-f639312b8df6` ON SCHEMA mdlg_ai_shared.kb_v2:
  Principal                              ActionType    ObjectType  ObjectKey
  459ebc59-0512-4da7-b962-f639312b8df6  USE SCHEMA    SCHEMA      mdlg_ai_shared.kb_v2

SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault (filtered to SP):
  Principal                              ActionType    ObjectType  ObjectKey
  459ebc59-0512-4da7-b962-f639312b8df6  READ VOLUME   VOLUME      mdlg_ai_shared.kb_v2.omnigraph_vault
```

**Defensive WRITE VOLUME absence check (AUTH-DBX-03 step 4):** Volume-level `SHOW GRANTS` (full unfiltered) returned 13 rows. Filtering to App SP `459ebc59-0512-4da7-b962-f639312b8df6`, ONLY the `READ VOLUME` row appears. **Zero rows with `WRITE VOLUME` for the App SP.** Confirmed AUTH-DBX-03 hard rule: SP cannot write the volume.

(Other rows in the volume SHOW GRANTS belong to inherited-from-catalog privileges of pre-existing groups — `ai-mlengineer-mdlg`, `dap-databricks-uc-admins`, etc. — not granted by this plan.)

---

## Section 3 — Foundation Model permissions (AUTH-DBX-04)

**Path A attempted:**

```bash
databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6 -o json
# → Error: 'databricks-claude-sonnet-4-6' is not a valid Inference Endpoint ID.

databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b -o json
# → Error: 'databricks-qwen3-embedding-0-6b' is not a valid Inference Endpoint ID.
```

**Path A inconclusive — root cause:** The CLI subcommand `get-permissions` requires an Inference Endpoint UUID (`.id` field), but Foundation Model endpoints are system-managed and the API `get` response does not expose a top-level `.id` field for them:

```bash
databricks --profile dev serving-endpoints get databricks-claude-sonnet-4-6 -o json
# → id: None, name: databricks-claude-sonnet-4-6, state.ready: READY

databricks --profile dev serving-endpoints get databricks-qwen3-embedding-0-6b -o json
# → id: None, name: databricks-qwen3-embedding-0-6b, state.ready: READY
```

This matches the structural limitation noted in `kdb-1.5-SPIKE-FINDINGS.md` line 23 and reaffirmed in `kdb-2-RESEARCH.md` Q1(c). Foundation Model endpoints in this workspace use permissive default ACLs — any authenticated SP can query them — and explicit `CAN_QUERY` grant entries are not surfaced via `get-permissions` even though access works at runtime.

**Path A inconclusive — deferred to kdb-2-04 Wave 0 Step 0 in-app probe.** Both endpoints are confirmed `READY`. Default ACL behavior + runtime in-app `WorkspaceClient().serving_endpoints.query(name=...)` call will validate AUTH-DBX-04 empirically when kdb-2-04 deploys.

Evidence files: `.scratch/kdb-2-01-perms-llm.json` + `.scratch/kdb-2-01-perms-embed.json` (structured Path-A-inconclusive markers).

---

## Section 4 — AUTH-DBX-05 (workspace SSO gating)

AUTH-DBX-05 is satisfied by Databricks Apps default behavior — App access requires workspace SSO; no anonymous access is possible. There is no "anonymous=false" toggle to set; it's the platform default for all Apps.

Per `kdb-2-RESEARCH.md` Q5 (lines 553-625), the workspace `https://adb-2717931942638877.17.azuredatabricks.net` has Private Link enabled, so the App URL `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com` is accessible only:
- (a) From inside the corporate network OR
- (b) Via workspace SSO browser session

Both gate on workspace SSO. AUTH-DBX-05 will be empirically verified during kdb-2-04 Smoke 1 browser-SSO interactive UAT (App URL → SSO prompt observed).

---

## Acceptance summary

| Acceptance criterion | Result |
|----------------------|--------|
| `cat .scratch/kdb-2-01-sp-client-id.txt | wc -l` returns `1` | ✅ |
| GUID-shape regex matches the file content | ✅ |
| `databricks apps get omnigraph-kb -o json | jq -r '.name'` returns `omnigraph-kb` (jq replaced with python json.load — equivalent) | ✅ |
| Evidence MD contains literal `Skill(skill="databricks-patterns"` | ✅ (Section 1) |
| Evidence MD contains literal `Skill(skill="security-review"` | ✅ (Section 2) |
| `SHOW GRANTS` confirms USE CATALOG | ✅ |
| `SHOW GRANTS` confirms USE SCHEMA | ✅ |
| `SHOW GRANTS` confirms READ VOLUME | ✅ |
| Defensive: zero WRITE VOLUME for SP | ✅ |
| `.scratch/kdb-2-01-perms-llm.json` exists | ✅ |
| `.scratch/kdb-2-01-perms-embed.json` exists | ✅ |
| Section 3 explicitly states `"Path A inconclusive — deferred to kdb-2-04 Wave 0 Step 0 in-app probe"` | ✅ |
| Section 4 states `AUTH-DBX-05` verification narrative | ✅ |

---

## Hard constraints honored

- (security) AUTH-DBX-03 `WRITE VOLUME` NOT granted; defensively SHOW-GRANTS-checked
- (security) AUTH-DBX-04 `CAN_QUERY` only — no `CAN_MANAGE` (no grant attempted at all on Foundation Model endpoints — default ACLs are sufficient)
- (scope) Zero `kb/` / `lib/` / top-level `*.py` modifications — pure CLI/SQL plan; CONFIG-DBX-01 invariant clean
- (skills) `Skill(skill="databricks-patterns")` invoked Task 1.1; `Skill(skill="security-review")` invoked Task 1.2 — frontmatter ↔ task invocation 1:1

## Files (post-Task 1.4)

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-01-AUTH-EVIDENCE.md` (this file)
- `.scratch/kdb-2-01-app-create.json` (full apps get JSON; gitignored — `.scratch/` is gitignored)
- `.scratch/kdb-2-01-sp-client-id.txt` (single-line GUID; gitignored)
- `.scratch/kdb-2-01-perms-llm.json` (Path A inconclusive marker; gitignored)
- `.scratch/kdb-2-01-perms-embed.json` (Path A inconclusive marker; gitignored)

The .scratch artifacts are referenced from this evidence MD via verbatim paths so kdb-2-04 + kdb-3 close audit can re-fetch the SP client_id from the scratch file (it's an identifier, not a secret — same posture as kdb-1.5 SPIKE which recorded `abb4cdbf-...` directly).

## Next

Task 1.4 complete. Plan kdb-2-01 ready for SUMMARY.md + commit.
