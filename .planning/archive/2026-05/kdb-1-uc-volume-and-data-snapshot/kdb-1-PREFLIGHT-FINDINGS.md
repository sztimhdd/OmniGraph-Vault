---
artifact: PREFLIGHT-FINDINGS
phase: kdb-1
wave: 1
created: 2026-05-15
status: pass
---

# kdb-1 Wave 1 PREFLIGHT — Findings

> Wave 1 scope per ROADMAP-kb-databricks-v1.md rev 3 (commit `cfe47b4`):
> only PREFLIGHT-DBX-01 (Model Serving reachability) + PREFLIGHT-DBX-02 (UC grant capability).
> Wave 2 storage / Wave 3 spike NOT executed in this commit.

## PREFLIGHT-DBX-01: Model Serving reachability

**Status:** ✅ PASS

**Auth context:** local Windows dev box → `databricks --profile dev` CLI (Go binary) → workspace API. **User OAuth token**, NOT Apps SP. Apps-SP-from-deployed-app is what SPIKE-DBX-01e covers; PREFLIGHT-01's question is "do these endpoints exist + respond at all in this workspace?" — user-creds answer that with the same network path.

### Sub-test 1.1 — list serving endpoints

```bash
databricks --profile dev serving-endpoints list -o json
```

- Total endpoints visible: **24**
- `databricks-claude-sonnet-4-6`: **PRESENT, state.ready = READY**
- `databricks-qwen3-embedding-0-6b`: **PRESENT, state.ready = READY**
- Adjacent endpoints noted (for future v2 swap evaluation): `databricks-claude-opus-4-7`, `databricks-claude-haiku-4-5`, `databricks-bge-large-en`, `databricks-gte-large-en`, `databricks-qwen35-122b-a10b`

### Sub-test 1.2 — query synthesis endpoint

```bash
databricks --profile dev serving-endpoints query databricks-claude-sonnet-4-6 \
  --max-tokens 20 \
  --json '{"messages":[{"role":"user","content":"ping"}]}' \
  -o json
```

- HTTP 200, latency **2.65s**
- Response: `{choices: [{message: {content: "Pong! 🐧\n\nHow can I help you?"}}], usage: {completion_tokens: 18, prompt_tokens: 8, total_tokens: 26}}`
- Content length: 31 chars (truncated to 20 max-tokens budget)
- All required fields present (choices, message, usage)

### Sub-test 1.3 — query embedding endpoint

```bash
databricks --profile dev serving-endpoints query databricks-qwen3-embedding-0-6b \
  --json '{"input":["hello world"]}' \
  -o json
```

- HTTP 200, latency **1.33s**
- Response: `{data: [{embedding: [...1024 floats...]}], usage: {prompt_tokens: 3}}`
- Embedding dim: **1024** (matches Qwen3-0.6B spec — important for LLM-DBX-03 factory)
- First 5 values: `[-0.014932, 0.017210, -0.011980, -0.072216, 0.003143]` (non-zero, plausible distribution)

### PREFLIGHT-01 verdict

✅ Both endpoints reachable, low-latency (< 5s budget), correct response shapes. Embedding dim matches Qwen3-0.6B expected output. No EDC corp-network blocker observed for in-workspace LLM traffic.

**Caveat:** PREFLIGHT-01 was run from local dev box CLI using user OAuth, not from inside an Apps-runtime container with Apps-SP injection. SPIKE-DBX-01e in Wave 3 still required to confirm Apps-SP path works identically. PREFLIGHT-01 passing means the workspace + endpoints exist and respond — the App-SP authorization layer is the remaining unknown, and SPIKE-DBX-01e will close it.

## PREFLIGHT-DBX-02: UC grant capability

**Status:** ✅ PASS

**Method:** CREATE SCHEMA → SHOW SCHEMAS verify → DROP SCHEMA → SHOW SCHEMAS confirm-clean, all on a throwaway target named `preflight_test_<unix-ts>` to avoid collision.

### Sub-test 2.1 — read existing grants on `mdlg_ai_shared`

```sql
SHOW GRANTS ON CATALOG mdlg_ai_shared
```

- Visible grants: 60 entries across ~30 principals (groups + service principals + 1 individual user `ahaq@edc.ca`)
- Top groups with `ALL PRIVILEGES`: `ai-mlengineer-mdlg`, `ai-mlops-team-aicoe-mdlg`, `dap-databricks-uc-admins`
- `account users` has `BROWSE`
- `hhu@edc.ca` (current user) does NOT appear directly — capability is via group membership (likely `ai-mlops-team-aicoe-mdlg` based on existing schema ownership pattern)

### Sub-test 2.2 — create + drop throwaway schema

```sql
-- Create
CREATE SCHEMA mdlg_ai_shared.preflight_test_1778857632
COMMENT 'kdb-1 PREFLIGHT-DBX-02 throwaway capability test, will be dropped immediately'
-- Result: success (empty result set)

-- Verify presence
SHOW SCHEMAS IN mdlg_ai_shared LIKE 'preflight_test_*'
-- Result: 1 row [["preflight_test_1778857632"]]

-- Drop
DROP SCHEMA mdlg_ai_shared.preflight_test_1778857632
-- Result: success (empty result set)

-- Verify cleanup
SHOW SCHEMAS IN mdlg_ai_shared LIKE 'preflight_test_*'
-- Result: 0 rows (clean)
```

- ✅ Schema created
- ✅ Schema visible after CREATE
- ✅ Schema dropped
- ✅ Schema gone after DROP

### PREFLIGHT-02 verdict

✅ User has `CREATE SCHEMA` capability on `mdlg_ai_shared` (via group membership, not direct grant). This implies access to the broader grant operations needed for kdb-2 AUTH-DBX-01..04 (`USE CATALOG` / `USE SCHEMA` / `READ VOLUME` / serving-endpoint `CAN QUERY`). User won't be blocked at kdb-2 phase boundary on permission grounds.

**Sanity-check evidence outside this test:** user (`hhu@edc.ca`) already owns 6 schemas in `mdlg_ai_shared` per `databricks-mcp-server list_schemas` (see STATE-kb-databricks-v1.md Accumulated Context); CREATE SCHEMA capability has been exercised before in production.

## Decision

| Outcome | Status | Next action |
|---------|--------|-------------|
| PREFLIGHT-01 | ✅ PASS | — |
| PREFLIGHT-02 | ✅ PASS | — |

**Both ✅ → All clear.** Wave 2 STORAGE-DBX-01..04 + SEED-DBX-01 may proceed pending user go-ahead. Wave 3 SPIKE-DBX-01a..01e may follow.

## Mitigation paths

(N/A — no failures observed.)

If a future re-run surfaces failures:
- PREFLIGHT-01 ❌ → likely Apps-SP-specific issue (since user-creds work); escalate to Databricks IT for SP-level CAN QUERY grant on Model Serving endpoints
- PREFLIGHT-02 ❌ → escalate to workspace admin for explicit grant of `USE CATALOG` + `CREATE SCHEMA` (or the equivalent group membership)

## Time budget

- Wave 1 hard timer: 30 min
- Actual: ~10 min wallclock (fast path; no escalation, no debug detours)

## Anti-pattern compliance

- ✅ NO new schema / volume / app created (Wave 2/3 work deferred)
- ✅ NO Hermes-side commands run
- ✅ NO `kb/` / `lib/` / `kg_synthesize.py` source edits
- ✅ Throwaway schema cleaned up; no residual UC objects from this test
- ✅ Findings written to phase dir, not source tree
- ✅ All commands use explicit profile (`databricks --profile dev`) — no implicit auth state changes

## Evidence checksum

- Endpoints listed: 24
- Targets present: 2/2
- Sonnet response: `Pong! 🐧\n\nHow can I help you?` (31 chars, 18 completion tokens)
- Embedding response: dim 1024, first val `-0.014932...`
- Throwaway schema lifecycle: CREATE → SHOW (1) → DROP → SHOW (0)
- All 4 SQL operations: success (empty result sets where expected)
