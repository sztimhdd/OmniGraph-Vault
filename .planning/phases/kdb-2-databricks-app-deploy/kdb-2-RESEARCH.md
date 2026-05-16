# Phase kdb-2 — Databricks App Deploy — Research

**Researched:** 2026-05-16
**Domain:** Databricks Apps deploy + MosaicAI provider integration + UC grants + smoke verification
**Confidence:** HIGH on REQ-mapped items (kdb-1 PREFLIGHT/SPIKE evidence + kdb-1.5 deliverables on disk); MEDIUM on app.yaml multi-step `command:` shape (no second-source verification beyond Apps-runtime docs); MEDIUM on Smoke 1+2 verification path (Private Link constraint is documented but the "browser SSO works in workspace context" remediation is per-user, not per-app).

## Summary

kdb-2 is the deploy-and-prove-it phase. Its mission: stand up the production Databricks App `omnigraph-kb`, integrate the MosaicAI provider end-to-end via the `lib/llm_complete.py` dispatcher (LLM-DBX-01), wire the kdb-1.5 storage adapter into `app.yaml`'s `command:` (DEPLOY-DBX-04), grant the App SP everything it needs against UC + Model Serving (AUTH-DBX-01..04), and prove Smoke 1 + Smoke 2 PASS. RAG round-trip (Smoke 3) is intentionally deferred to kdb-3 because the LightRAG storage Volume is empty until kdb-2.5 re-indexes it; what works in kdb-2 is the FTS5 fallback path, which exercises every code path Smoke 3 needs except the actual KG embedding lookup.

Critically, kdb-2 builds DIRECTLY on kdb-1.5's two shipped artifacts. `databricks-deploy/startup_adapter.py` and `databricks-deploy/lightrag_databricks_provider.py` are already on disk, tested (9/9 green, 4/4 against REAL Model Serving), and frozen — kdb-2 IMPORTS them, never modifies them. The phase's only NEW Python code is the `databricks_serving` provider branch in `lib/llm_complete.py` (LLM-DBX-01, ~10 lines) and a possible `kg_serving_unavailable` reason-code addition in `kb/services/synthesize.py` (LLM-DBX-04). The biggest risk is that the kg_synthesize.py LLM-DBX-02 "1-import + 1-call-site" requirement specified by the REQ doc is **already substantially done** by quick-260509-s29 (line 19 + line 106 already use the dispatcher), but the embedding side (kg_synthesize.py:106 still wires `embedding_func` from `lib.lightrag_embedding` which is Vertex/Gemini dim=3072) needs special handling — see Q3 for the resolution.

<user_constraints>
## User Constraints (from PROJECT-kb-databricks-v1.md, REQUIREMENTS-kb-databricks-v1.md rev 3, ROADMAP-kb-databricks-v1.md rev 3, scope_constraints from orchestrator prompt)

> No phase-level CONTEXT.md exists. Constraints distilled from milestone-level PROJECT/REQ/ROADMAP rev 3 + the orchestrator prompt's `<scope_constraints>` block.

### Locked Decisions (rev 3 binding)

1. **All LLM via MosaicAI Model Serving** — DeepSeek + Vertex Gemini retired in v1 deploy.
2. **Synthesis model**: `databricks-claude-sonnet-4-6` (locked).
3. **Embedding model**: `databricks-qwen3-embedding-0-6b` (locked, dim=1024, bilingual zh/en).
4. **App name**: `omnigraph-kb` (locked).
5. **App port**: `:8080` via `$DATABRICKS_APP_PORT` substitution in `command:` (Apps runtime hardcoded).
6. **App auth → UC + Model Serving**: App SP auto-injection (`DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET`) — no external secret scope, no API key, NO `valueFrom:` for any LLM env.
7. **Hermes touchpoint**: NONE in kdb-2 (one-shot SEED-DBX-01 closed in kdb-1).
8. **UC paths**: `mdlg_ai_shared.kb_v2.omnigraph_vault` Volume layout `/data` · `/images` · `/lightrag_storage` (empty until kdb-2.5) · `/output`.
9. **App SP grants**: `USE CATALOG` + `USE SCHEMA` + `READ VOLUME` only — **NO `WRITE VOLUME`** in v1 (architectural constraint that drove kdb-1.5 adapter).
10. **CONFIG-EXEMPTIONS**: `lib/llm_complete.py` (LLM-DBX-01) + `kg_synthesize.py` (LLM-DBX-02) are the ONLY allowed `kb/`-relative edits in this phase. Any other path requires explicit user approval.
11. **kdb-2 RAG path expected degraded to FTS5 fallback** — Smoke 3 deferred to kdb-3 post-kdb-2.5.
12. **Forward-only commits** (per `feedback_no_amend_in_concurrent_quicks.md`): no `git commit --amend`, no `git reset`, no `git add -A`.
13. **No literal secrets in any commit** (per `feedback_no_literal_secrets_in_prompts.md`): SP auto-injection covers Model Serving auth; no token leaves the workspace.
14. **Skill discipline** (per `feedback_skill_invocation_not_reference.md`): named Skills MUST be invoked via `Skill(skill="...")` tool calls, not just listed in `<read_first>`. Literal substring check at SUMMARY.md commit time.
15. **Parallel-track gates manual** (per `feedback_parallel_track_gates_manual_run.md`): orchestrator hand-drives every gate; gsd-tools.cjs `init` will return `phase_found=false` for `kdb-2`.

### Claude's Discretion

1. Choice between `bash -c "python startup_adapter && uvicorn ..."` single-line shape vs a wrapper shell script under `databricks-deploy/` for the multi-step `command:` (Q7). Recommend single-line bash form (less moving parts).
2. Choice of pytest path for LLM-DBX-01 unit tests — extend the existing `tests/unit/test_llm_complete.py` (60 lines, 5 tests covering deepseek + vertex_gemini + invalid + lazy-import) or add a new file. Recommend extend existing file (`tests/unit/test_llm_complete.py`) so the dispatcher's full provider matrix lives in one test module.
3. Whether LLM-DBX-04 reason-code addition lives in `kb/services/synthesize.py` _outside_ the formal CONFIG-EXEMPTIONS list (would need user approval — see Q4) OR in a wrapper that intercepts MosaicAI errors before they reach `kg_synthesize.synthesize_response`.
4. Ordering / parallelization of plans 01..04 (Wave 0 / Wave 1 / Wave 2 etc.) — see "Recommended plan structure" below.
5. Whether `make smoke` recipe actually runs anything or is a manual checklist (Q8). Recommend it just `echo`s the human checklist, since Smoke 1+2 cannot be automated under Private Link.

### Deferred Ideas (OUT OF SCOPE for kdb-2)

- **kdb-2.5 re-index Job** — entire LightRAG re-indexing flow (separate phase).
- **Smoke 3 / RAG round-trip via MosaicAI** — kdb-3 after kdb-2.5 lands.
- **`WRITE_VOLUME` for App SP** — forbidden in v1 (AUTH-DBX-03 hard rule).
- **Modifications to kdb-1.5 deliverables** (`startup_adapter.py`, `lightrag_databricks_provider.py`) — kdb-2 IMPORTS, never modifies.
- **Aliyun deploy / Hermes / kb-v2 edits** — different milestones.
- **`kb/` source modifications BEYOND `lib/llm_complete.py` + `kg_synthesize.py`** — locked by CONFIG-DBX-01.
- **Embedding pipeline swap inside kg_synthesize.py:106** beyond what LLM-DBX-02 prescribes — see Q3 for the embedding-side handling rationale.
- **Public access / zero-login KB on Databricks** — Apps SSO is the gate (DEPLOY-DBX-06 + AUTH-DBX-05). Public access is Aliyun's job (KB-v2 / kb-4).
- **Fixing Apps logs CLI absence** — Workspace UI Apps tab is the only path (Q8 + risk #3).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **AUTH-DBX-01** | App SP `app-omnigraph-kb` has `USE CATALOG` on `mdlg_ai_shared` | Q1 (a) — kdb-1 SPIKE-FINDINGS confirms grant pattern works via `mcp__databricks-mcp-server execute_sql` with SP client_id |
| **AUTH-DBX-02** | App SP has `USE SCHEMA` on `mdlg_ai_shared.kb_v2` | Q1 (b) — same grant pattern |
| **AUTH-DBX-03** | App SP has `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` (no WRITE) | Q1 (b) — same grant pattern |
| **AUTH-DBX-04** | App SP has `CAN_QUERY` on `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b` | Q1 (c) — kdb-1 SPIKE FOUND `serving-endpoints list` doesn't expose IDs; documented workaround needed |
| **AUTH-DBX-05** | App access gated by workspace SSO (default Apps behavior; no anonymous) | Q5 — Private Link policy already enforces this |
| **LLM-DBX-01** | `lib/llm_complete.py` adds `databricks_serving` provider branch + unit tests | Q2 — lib/llm_complete.py is 48 lines, 2-branch dispatcher; concrete add-branch sketch below |
| **LLM-DBX-02** | `kg_synthesize.synthesize_response` re-routes LLM call through dispatcher (1 import + 1 call site swap) | Q3 — **already substantially done** by quick-260509-s29 (line 19 + line 106 already imports + uses get_llm_func()); REQ scope mostly satisfied — only env-var-driven test confirmation + CONFIG-EXEMPTIONS ledger entry remain. Embedding side has a separate concern documented below. |
| **LLM-DBX-04** | Model Serving error path = graceful degrade with new `kg_serving_unavailable` reason code (4th in enum) | Q4 — current 3 codes at `kb/services/synthesize.py:189-201`; concrete insertion shape sketched |
| **LLM-DBX-05** | `app.yaml` `env:` contains 3 literal `value:` (NOT `valueFrom:`) for `OMNIGRAPH_LLM_PROVIDER`, `KB_LLM_MODEL`, `KB_EMBEDDING_MODEL` | Q7 — concrete app.yaml shape |
| **DEPLOY-DBX-01** | App `omnigraph-kb` created via `databricks apps create` | Q8 — `make deploy` recipe |
| **DEPLOY-DBX-02** | `app.yaml` at root of `--source-code-path` (NOT nested) | Q7 — pin source-code-path to repo `databricks-deploy/` |
| **DEPLOY-DBX-03** | `app.yaml` `command:` uses `$DATABRICKS_APP_PORT` (not hardcoded `:8766`) | Q7 — multi-step bash wrapper retains env substitution |
| **DEPLOY-DBX-04** | `app.yaml` `env:` sets `OMNIGRAPH_BASE_DIR` (literal) PLUS the 3 LLM env literals; NO `valueFrom:` | Q7 — concrete env block |
| **DEPLOY-DBX-05** | First `databricks apps deploy` reaches `RUNNING` within 20-min default timeout | Q6 — kdb-1 spike measured 9s deploy-to-RUNNING for empty App; kdb-2 first deploy realistic target ~30-60s with adapter no-op (Volume empty) |
| **DEPLOY-DBX-06** | App URL returns 200 on `/` after workspace SSO | Q5 — Private Link blocks external Bearer; user-in-workspace browser is the only path |
| **DEPLOY-DBX-07** | `databricks-deploy/requirements.txt` pins kb runtime deps; ZERO DeepSeek deps | kdb-1.5 file already created; kdb-2 verifies + may extend |
| **DEPLOY-DBX-08** | `app.yaml` literal `OMNIGRAPH_LLM_PROVIDER=databricks_serving` (defends against egress to non-Databricks endpoints) | Q7 — same env block as DEPLOY-DBX-04 |
| **DEPLOY-DBX-09** | `app.yaml` `env:` deliberately does NOT set `KB_KG_GCP_SA_KEY_PATH` or `GOOGLE_APPLICATION_CREDENTIALS` | grep-verifiable |
| **OPS-DBX-01** | KB-v2 Smoke 1 verbatim (双语 UI 切换) | Q5 — browser UAT |
| **OPS-DBX-02** | KB-v2 Smoke 2 verbatim (双语搜索 + 详情页 + UC Volume image render) | Q5 — browser UAT |

20 REQs total scoped to kdb-2.
</phase_requirements>

---

## Q1 — Apps SP grant grammar (AUTH-DBX-01..04)

**Confidence:** HIGH on (a) (b); MEDIUM on (c) (workaround documented but not yet executed for production endpoints).

### (a) `USE CATALOG` on `mdlg_ai_shared`

The kdb-1 SPIKE-FINDINGS evidence (commit `cfe47b4` baseline + spike App `omnigraph-kb-spike` deploy 2026-05-15) proved:

- App created → SP auto-created with `client_id` = `abb4cdbf-f026-4c71-97cf-a14466450379` (per SPIKE-FINDINGS line 22).
- `mcp__databricks-mcp-server execute_sql` with that `client_id` as the principal worked: SPIKE-FINDINGS line 22 — *"Grant USE_CATALOG / USE_SCHEMA / READ_VOLUME on UC objects to spike SP — ✅ All 3 grants succeeded"*.

**Concrete grant SQL** (works on this workspace, executable via `mcp__databricks-mcp-server` `execute_sql` tool — note the principal is the **SP client_id GUID**, NOT the friendly app name):

```sql
-- Grant USE CATALOG (AUTH-DBX-01)
GRANT USE CATALOG ON CATALOG mdlg_ai_shared
  TO `<APP_SP_CLIENT_ID>`;

-- Verify
SHOW GRANTS ON CATALOG mdlg_ai_shared
  | filter principal = '<APP_SP_CLIENT_ID>';
-- expect: 1 row with privilege = 'USE CATALOG'
```

**Identifier shape** — Apps SP is referenced by **client-id GUID surrounded by backticks**, NOT by friendly name. The friendly name (`app-omnigraph-kb` is what the orchestrator prompt uses) is a Databricks UI label; the actual grant principal is the GUID. Discoverable via `databricks apps get omnigraph-kb -o json | jq '.service_principal_client_id'` after `apps create`.

### (b) `USE SCHEMA` + `READ VOLUME`

```sql
GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2
  TO `<APP_SP_CLIENT_ID>`;

GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault
  TO `<APP_SP_CLIENT_ID>`;

-- Explicitly DO NOT grant WRITE VOLUME — AUTH-DBX-03 forbids it.

-- Verify all 3 in one shot:
SHOW GRANTS ON CATALOG mdlg_ai_shared
  | filter principal = '<APP_SP_CLIENT_ID>';
SHOW GRANTS ON SCHEMA mdlg_ai_shared.kb_v2
  | filter principal = '<APP_SP_CLIENT_ID>';
SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault
  | filter principal = '<APP_SP_CLIENT_ID>';
```

### (c) Foundation Model `CAN QUERY` (AUTH-DBX-04) — workaround required

**The blocker found in kdb-1 SPIKE** (SPIKE-FINDINGS line 23):

> "`databricks-claude-sonnet-4-6` and `databricks-qwen3-embedding-0-6b` are Databricks-managed Foundation Model endpoints; `serving-endpoints list` does not expose endpoint IDs and `update-permissions` requires the ID. Skipped on assumption of permissive defaults; would have re-attempted on 01e fail."

Two complementary verification paths exist; recommend running **both** and treating either green as sufficient:

**Path A — `databricks serving-endpoints get-permissions`** (CLI v0.260+ accepts endpoint name, not ID):

```bash
# Try with endpoint name (CLI may accept it)
databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6
databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b
```

If those return JSON containing the App SP's GUID with `level: "CAN_QUERY"`, AUTH-DBX-04 is satisfied. **TBD in execute phase**: verify the CLI v0.260.0 sub-command shape — it may also accept an `endpoint_id` flag or a JSON payload.

**Path B — implicit verification via PREFLIGHT-DBX-01 SP path**:

Foundation Model endpoints in this workspace appear to use **permissive default ACLs** for any authenticated SP (per kdb-1 SPIKE-FINDINGS line 23 reasoning). The actual production-readiness check is whether the App SP can `WorkspaceClient().serving_endpoints.query(...)` from inside a deployed App.

The kdb-1.5 Plan 02 dry-run already proved the call shape works under user OAuth (PREFLIGHT-DBX-01 sub-tests 1.2 + 1.3 → HTTP 200, 2.65s + 1.33s latency). The remaining unknown is the **App-SP-vs-user-OAuth permission delta** — which surfaces immediately in kdb-2 first deploy when the App boots and `lightrag_databricks_provider.make_llm_func()` constructs `WorkspaceClient()` during LightRAG init.

**Recommended verification step in kdb-2-01 plan**:

```bash
# Step 1: deploy App (DEPLOY-DBX-01)
# Step 2: capture App SP client_id from `databricks apps get omnigraph-kb -o json`
# Step 3: run grant SQL (AUTH-DBX-01..03) using that client_id
# Step 4: try Path A (`get-permissions`) — if it succeeds, AUTH-DBX-04 done
# Step 5: if Path A fails or returns no SP entry, fall through to Path B —
#         user opens the App URL via in-workspace browser SSO, hits a debug
#         endpoint that tries WorkspaceClient().serving_endpoints.query(...)
#         and returns the result. HTTP 200 = AUTH-DBX-04 satisfied at runtime.
```

The Path B "debug endpoint" is a one-line FastAPI route (`/debug/probe-mosaic`) that the kdb-2 plan can include in the first deploy and remove in kdb-3 cleanup. It's cheaper than chasing CLI grammar.

**Output for planner — 4 concrete SQL/CLI lines**:

```sql
GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO `<APP_SP_CLIENT_ID>`;
GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO `<APP_SP_CLIENT_ID>`;
GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO `<APP_SP_CLIENT_ID>`;
```
```bash
databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6
```
(if CLI rejects, fall through to Path B in-app probe).

---

## Q2 — `lib/llm_complete.py` current shape (LLM-DBX-01)

**Confidence:** HIGH (file read end-to-end; pattern locked).

### Current file (48 lines)

`lib/llm_complete.py` is exactly 48 lines including module docstring. Structural elements:

- **Line 27**: `_VALID = ("deepseek", "vertex_gemini")` — the tuple LLM-DBX-01 must extend.
- **Lines 30-45**: `def get_llm_func() -> Callable:` — single function, single return path per branch.
- **Lines 34-35**: env reads `OMNIGRAPH_LLM_PROVIDER` defaulting to `"deepseek"` (with `.strip() or "deepseek"` empty-string defense).
- **Lines 36-38**: `if provider == "deepseek":` → lazy-import + return `deepseek_model_complete`.
- **Lines 39-41**: `if provider == "vertex_gemini":` → lazy-import + return `vertex_gemini_model_complete`.
- **Lines 42-45**: `raise ValueError(...)` listing `_VALID` for unknown providers.
- **Line 48**: `__all__ = ["get_llm_func"]`.

### LightRAG callable contract

Both existing branches return the function reference itself, NOT an invocation. LightRAG calls it as:

```python
async def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str
```

The `databricks-deploy/lightrag_databricks_provider.py` factory `make_llm_func()` returns exactly this shape (verified by kdb-1.5 dry-run e2e Test 3 — ainsert + aquery against REAL Model Serving succeeded). **The dispatcher branch should call the factory and return its callable** — NOT return the factory itself.

### Concrete add-branch implementation skeleton (LLM-DBX-01)

Insert **between** the existing `vertex_gemini` branch (line 41) and the `raise ValueError(...)` (line 42), and extend `_VALID` on line 27:

```python
# line 27 — extend valid tuple
_VALID = ("deepseek", "vertex_gemini", "databricks_serving")

# ... unchanged through line 41 ...

# line 42 — INSERT new branch
    if provider == "databricks_serving":
        # Wrap the kdb-1.5 factory (databricks-deploy/lightrag_databricks_provider.py).
        # Module is added to sys.path by the App's startup_adapter at boot time
        # (DEPLOY-DBX-04 wrapper); locally, callers prepend databricks-deploy/.
        # Lazy import preserves the dispatcher's import-on-demand contract:
        # DeepSeek-only callers don't pay databricks-sdk import cost.
        from databricks_deploy.lightrag_databricks_provider import make_llm_func
        return make_llm_func()

# line 42 (now line 47 after insertion) — ValueError unchanged
    raise ValueError(...)
```

**Caveat — module path discovery**: `databricks-deploy/` has a hyphen, which Python doesn't accept as a package name. Three options:

1. Add `databricks-deploy/` to `sys.path` and import `lightrag_databricks_provider` as a top-level module (matches what `databricks-deploy/tests/test_provider_dryrun.py` already does at line 465: `sys.path.insert(0, str(Path(__file__).parent.parent))`).
2. Rename `databricks-deploy/` to `databricks_deploy/` (would break kdb-1.5 frozen contract; rejected).
3. Use `importlib.util.spec_from_file_location` to import by file path (works but is ugly).

**Recommended: Option 1.** The dispatcher branch should `sys.path.insert(0, ...)` BEFORE the import; this is exactly what `databricks-deploy/startup_adapter.py` invocation needs to do anyway when wired into the App's `command:` (Q7). Concrete shape:

```python
    if provider == "databricks_serving":
        # The factory file lives under databricks-deploy/ which has a hyphen
        # — not a legal Python package name. Adapter path is added to sys.path
        # by the App startup wrapper (DEPLOY-DBX-04) before this branch runs.
        # Locally, tests prepend it explicitly.
        from lightrag_databricks_provider import make_llm_func
        return make_llm_func()
```

### LLM-DBX-01 unit test additions

Existing `tests/unit/test_llm_complete.py` (60 lines, 5 tests) already covers: `default_unset_returns_deepseek`, `explicit_deepseek_returns_deepseek`, `vertex_gemini_returns_vertex_func`, `unknown_provider_raises_valueerror`, `import_does_not_import_vertex_module` (lazy-import contract).

**Tests to add** (under same file — Discretion item #2):

1. `test_databricks_serving_returns_factory_callable` — set `OMNIGRAPH_LLM_PROVIDER=databricks_serving`, monkeypatch `lightrag_databricks_provider.make_llm_func` to return a sentinel async callable, assert `get_llm_func()` returns that sentinel.
2. `test_unknown_provider_lists_databricks_in_error` — assert `_VALID` mentioned in `ValueError` includes `databricks_serving` (extends existing test 4).
3. `test_databricks_branch_is_lazy_import` — assert `import lib.llm_complete` does NOT pull `databricks-sdk` or `databricks_deploy.lightrag_databricks_provider` into `sys.modules` (extends existing test 5 pattern).
4. `test_databricks_provider_error_path_surfaces` — when factory raises (mock 503/network error), assert the wrapped callable raises an exception with the original error type (exception bubbles up; matches REQ LLM-DBX-01 line 38 "error-path test that surfaces 503/429/timeout to caller").

The error-path test for (4) needs a mock since real 503s aren't reproducible cheaply. Pattern:

```python
def test_databricks_provider_error_path_surfaces(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
    sys.path.insert(0, "databricks-deploy")
    # Mock WorkspaceClient.serving_endpoints.query to raise 503
    import lightrag_databricks_provider as p
    async def boom(*a, **kw): raise RuntimeError("HTTP 503: model_overloaded")
    monkeypatch.setattr(p, "make_llm_func", lambda: boom)

    from lib.llm_complete import get_llm_func
    llm = get_llm_func()
    with pytest.raises(RuntimeError, match="503"):
        asyncio.run(llm("hi"))
```

---

## Q3 — LLM-DBX-02 actual diff scope (kg_synthesize.py)

**Confidence:** HIGH for the LLM-side finding (file read end-to-end; only one LLM call site exists at line 158, fed by the dispatcher); MEDIUM for the embedding-side concern (the embedding swap is technically out of LLM-DBX-02 REQ scope, but the deployed App will fail if not addressed somewhere).

### Pre-existing dispatcher integration (already done by quick-260509-s29)

`kg_synthesize.py` is 200 lines. LLM call sites verified via `grep -n "deepseek_model_complete\|vertex_gemini_model_complete\|llm_model_func\|aquery\|complete\(|chat\.completions"`:

```
106: rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=embedding_func)
158:             response = await rag.aquery(custom_prompt, param=param)
```

**Line 19** already has the dispatcher import (`from lib.llm_complete import get_llm_func  # quick-260509-s29 W3: dispatcher`). **Line 106** already passes `llm_model_func=get_llm_func()` to `LightRAG(...)`. Line 158 is just `rag.aquery(...)` — not a direct LLM call but a LightRAG-internal one that consumes the `llm_model_func` set at construction time.

**Implication**: LLM-DBX-02's literal text in REQUIREMENTS-kb-databricks-v1.md line 39 ("`kg_synthesize.synthesize_response(query_text, mode='hybrid')` re-routes its LLM call from hardcoded `deepseek_model_complete` to the dispatcher in `lib/llm_complete.py`") is **already substantially satisfied**. The "1 import + 1 call site swap" diff requirement is met by quick-260509-s29's existing change.

`grep -rn "get_llm_func\|deepseek_model_complete\|vertex_gemini_model_complete" *.py lib/ scripts/ tests/` (run during research) confirms the dispatcher pattern is widespread (`ingest_wechat.py:240`, `ingest_github.py:26`, `omnigraph_search/query.py:28`, `query_lightrag.py:13`, `scripts/wave0c_smoke.py:41` — all already through the dispatcher). The kg_synthesize migration was already done.

### What kdb-2 LLM-DBX-02 still owes

1. **No code change to kg_synthesize.py for the LLM side.** The literal dispatcher swap is already shipped. CONFIG-EXEMPTIONS.md will record this verbatim — both files (`lib/llm_complete.py` after LLM-DBX-01 lands, `kg_synthesize.py` reflecting the historical quick-260509-s29 change) become "MODIFIED in this milestone" with the latter's diff scope being **zero net change to kg_synthesize.py** for kdb-2.
2. **Test confirming `OMNIGRAPH_LLM_PROVIDER=databricks_serving` exercises the dispatcher path through `synthesize_response`.** This is the new test the REQ explicitly calls out at line 39: *"new test confirms dispatcher path executes when `OMNIGRAPH_LLM_PROVIDER=databricks_serving` is set."* It belongs in the kdb-2-03 (LLM-DBX-04 + integration) plan — see "Validation Architecture" section.
3. **CONFIG-EXEMPTIONS.md ledger update** to flip both rows from `NOT YET MODIFIED` to `MODIFIED — see commit <hash>` (tracking the LLM-DBX-01 commit that adds the dispatcher branch + the historical quick-260509-s29 commit that landed the kg_synthesize change).

### The embedding-side concern (NOT LLM-DBX-02; flag for plan-level decision)

`kg_synthesize.py:106` reads:

```python
rag = LightRAG(working_dir=RAG_WORKING_DIR,
               llm_model_func=get_llm_func(),
               embedding_func=embedding_func)
```

`embedding_func` is imported at line 20: `from lib.lightrag_embedding import embedding_func`. That module (`lib/lightrag_embedding.py`) is the **Vertex/Gemini embedding** path — `EMBEDDING_DIM = 3072` per `lib/models.py` (per `lib/lightrag_embedding.py:29`).

In a deployed kdb-2 App with `OMNIGRAPH_LLM_PROVIDER=databricks_serving`:

- The LLM dispatcher correctly returns `make_llm_func()` (Qwen3-via-MosaicAI-via-factory).
- The embedding func is STILL `lib.lightrag_embedding.embedding_func` (Vertex-Gemini, dim=3072).
- LightRAG instantiation will fail at first `ainsert`/`aquery` because the kdb-2.5 re-indexed Volume contains dim=1024 Qwen3 vectors and the embedding func is producing dim=3072 Vertex vectors. **Dim mismatch → `lightrag/utils.py` `wrap_embedding_func_with_attrs` decorator surfaces it as a hard runtime error.**

**This is NOT in the LLM-DBX-02 REQ scope** (REQ specifically pins LLM-DBX-02 to "swap one import + one call site" for the LLM side). The REQ author appears to have left the embedding-side migration implicit — assuming it's covered by either (a) an env-var-gated branch in `lib/lightrag_embedding.py` (which doesn't exist), or (b) a parallel embedding dispatcher (which doesn't exist), or (c) a `kg_synthesize.py:106` change to also use a factory for embedding (a 2nd `kb/`-edit beyond LLM-DBX-02's scope).

**Resolution options for kdb-2 plans** (planner must pick one + flag to user):

| Option | Where the change lands | CONFIG-EXEMPTIONS impact | Risk |
|--------|------------------------|--------------------------|------|
| **A. Mirror dispatcher pattern**: add `lib/embedding_complete.py` providing `get_embedding_func()` that routes by env, then change `kg_synthesize.py:20+106` to use it | New file under `lib/` (NOT in current exemption list) + 2-line edit to `kg_synthesize.py` | Requires user approval to add `lib/embedding_complete.py` to CONFIG-EXEMPTIONS.md + a SECOND kg_synthesize.py edit (line 20 import + line 106 arg) | LOW — clean architectural mirror; reusable by ingest_wechat / query_lightrag / etc. |
| **B. Inline check in `lib/lightrag_embedding.py`** at top: `if os.environ.get("OMNIGRAPH_LLM_PROVIDER") == "databricks_serving": from lightrag_databricks_provider import make_embedding_func; embedding_func = make_embedding_func()` | `lib/lightrag_embedding.py` (NOT in exemption list) | Requires user approval to add `lib/lightrag_embedding.py` to CONFIG-EXEMPTIONS | MEDIUM — introduces import-time env-coupling; harder to test in isolation |
| **C. Make `kg_synthesize.py:106` itself env-gate the embedding func** | `kg_synthesize.py` (already in exemption list) | Adds ~5 lines to kg_synthesize.py — within the existing exemption | LOW — but stretches the "1 import + 1 call site" REQ wording for LLM-DBX-02 to include embedding |
| **D. Plumb embedding through a NEW factory bus inside `databricks-deploy/`** that kdb-2.5 re-index Job uses too | NEW shim `databricks-deploy/embedding_dispatcher.py` import in kg_synthesize.py | Adds shim under `databricks-deploy/` (allowed) + extends kg_synthesize.py exemption use | MEDIUM — slight over-engineering; aligns kdb-2 + kdb-2.5 on identical embedding factory imports |

**Recommendation: Option A** (mirror dispatcher pattern). Rationale:

1. Cleanest architecture — symmetric to LLM dispatcher; reusable for `ingest_wechat.py`, `ingest_github.py`, `query_lightrag.py`, `omnigraph_search/query.py`, `scripts/wave0c_smoke.py` (all of which currently use `lib.lightrag_embedding.embedding_func` directly).
2. `lib/embedding_complete.py` is ~30 lines (mirror of `lib/llm_complete.py`); easy to test.
3. Requires explicit user approval to extend CONFIG-EXEMPTIONS — but this is the right call because the embedding-side migration is real architectural work, not a workaround.
4. **Alternatively, accept Option B/C as a stop-gap** if the user wants to minimize CONFIG-EXEMPTIONS surface — but the planner MUST surface this question explicitly to the user before kdb-2-02 plan starts. Do NOT silently choose.

**Concrete diff sketch for Option A (recommended)**:

`lib/embedding_complete.py` (NEW, ~35 lines):

```python
"""Provider dispatcher for LightRAG ``embedding_func`` — kdb-2 LLM-DBX-02 sibling.

OMNIGRAPH_LLM_PROVIDER env var routes to the matching embedding provider:
  - 'deepseek' / unset → lib.lightrag_embedding.embedding_func  (Vertex/Gemini, dim=3072)
  - 'vertex_gemini'    → same as deepseek (also Vertex; deepseek+vertex share embedding path)
  - 'databricks_serving' → databricks-deploy/lightrag_databricks_provider.make_embedding_func()  (Qwen3, dim=1024)

Mirror of lib/llm_complete.py; lazy-imports preserve provider isolation.
"""
from __future__ import annotations
import os
from typing import Any

_VALID = ("deepseek", "vertex_gemini", "databricks_serving")

def get_embedding_func() -> Any:
    provider = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip() or "deepseek"
    if provider in ("deepseek", "vertex_gemini"):
        from lib.lightrag_embedding import embedding_func
        return embedding_func
    if provider == "databricks_serving":
        # databricks-deploy/ on sys.path via App startup wrapper
        from lightrag_databricks_provider import make_embedding_func
        return make_embedding_func()
    raise ValueError(f"Unknown OMNIGRAPH_LLM_PROVIDER={provider!r}; expected one of {_VALID}")

__all__ = ["get_embedding_func"]
```

`kg_synthesize.py` diff (2 lines):

```python
# line 20 — change from:
from lib.lightrag_embedding import embedding_func
# to:
from lib.embedding_complete import get_embedding_func

# line 106 — change from:
rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=embedding_func)
# to:
rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=get_embedding_func())
```

CONFIG-EXEMPTIONS update — add:

| File | REQ | Phase | Status |
|------|-----|-------|--------|
| `lib/embedding_complete.py` | LLM-DBX-02 (extended scope) | kdb-2 | NEW — mirrors lib/llm_complete.py for embedding side |

**Risk if NOT addressed**: kdb-2.5 re-index will populate Volume with dim=1024 Qwen3 vectors; kdb-3 Smoke 3 will fail because LightRAG init in deployed App will dim-mismatch. This is the kind of "REQ-checkbox-satisfied but actually-undone" trap that `feedback_skill_invocation_not_reference.md` and `feedback_contract_shape_change_full_audit.md` warn about — surface to user explicitly during planning.

---

## Q4 — LLM-DBX-04 graceful degrade reuse pattern

**Confidence:** HIGH (file read end-to-end; pattern locked).

### Current `KG_MODE_AVAILABLE` shape in `kb/services/synthesize.py`

- **Lines 189-201**: `_check_kg_mode_available()` function — returns `(available: bool, reason: str)` tuple. Reasons enumerated:
  - `"kg_disabled"` (line 193) — `KB_KG_GCP_SA_KEY_PATH` is None; nothing set
  - `"kg_credentials_missing"` (line 198) — `FileNotFoundError` opening the path
  - `"kg_credentials_unreadable"` (line 200) — any other `OSError`
- **Lines 204-206**: `KG_MODE_AVAILABLE: bool` + `KG_MODE_UNAVAILABLE_REASON: str` set at module-import time.
- **Lines 207-214**: WARNING log if not available, with the reason (no path leak).
- **Lines 145**: `ConfidenceLevel = Literal["kg", "fts5_fallback", "kg_unavailable", "no_results"]` — note the `kg_unavailable` is in the enum but NOT used by the existing reason codes. **This is the slot LLM-DBX-04's `kg_serving_unavailable` reason should populate** — except the REQ says reason code is `kg_serving_unavailable` and the existing enum has `kg_unavailable`. Naming reconciliation needed (Q4 detail below).
- **Lines 420-450**: `kb_synthesize` function — try/except wrapping `await asyncio.wait_for(synthesize_response(...), timeout=KB_SYNTHESIZE_TIMEOUT)`:
  - Line 420: `if not KG_MODE_AVAILABLE:` → `_fts5_fallback(reason=f"KG mode unavailable: {KG_MODE_UNAVAILABLE_REASON}")` → return.
  - Line 445: `except asyncio.TimeoutError:` → `_fts5_fallback(reason="C1 timeout")`.
  - Line 448: `except Exception as e:` → `_fts5_fallback(reason=f"{type(e).__name__}: {e}")`.

### Call chain: does `kb_synthesize` route through `kg_synthesize.synthesize_response`?

**Yes.** `kb/services/synthesize.py:428`: `from kg_synthesize import synthesize_response` (lazy import, deferred to avoid heavy LightRAG init at module import time). Line 442: `await asyncio.wait_for(synthesize_response(query_text, mode="hybrid"), timeout=KB_SYNTHESIZE_TIMEOUT)`.

So the call path is:
```
HTTP POST /api/synthesize
  → kb.services.synthesize.kb_synthesize(question, lang, job_id)        [line 392]
    → KG_MODE_AVAILABLE check                                            [line 420]
    → asyncio.wait_for(synthesize_response(query_text, mode="hybrid"))   [line 442]
      → kg_synthesize.synthesize_response                                [kg_synthesize.py:105]
        → LightRAG(..., llm_model_func=get_llm_func(), ...)              [line 106]
          → MosaicAI Model Serving call (databricks_serving provider)
```

### Where the new `kg_serving_unavailable` reason code goes

**Option 1 (preferred per REQ spirit)**: extend the `ConfidenceLevel` Literal type to include the new reason code, and add detection logic in the `except Exception as e:` handler at line 448 that distinguishes Model Serving errors from other exceptions.

**Concrete diff sketch**:

`kb/services/synthesize.py` line 145 — extend Literal:

```python
# Before:
ConfidenceLevel = Literal["kg", "fts5_fallback", "kg_unavailable", "no_results"]
# After (add 1 value):
ConfidenceLevel = Literal["kg", "fts5_fallback", "kg_unavailable", "no_results", "kg_serving_unavailable"]
```

Wait — `kg_unavailable` exists in the enum but is unused. The REQ at line 95 says LLM-DBX-04 *adds* a 4th reason code (the existing 3 being `kg_disabled`, `kg_credentials_missing`, `kg_credentials_unreadable`, all in the `available, reason` tuple but routed through the `confidence` field as `fts5_fallback`). The enum's `kg_unavailable` is a leftover from kb-v2.1-1 hardening and is currently unused.

**Recommended naming reconciliation**:
- Rename existing unused enum entry `kg_unavailable` → `kg_serving_unavailable` (matches REQ wording exactly).
- Add detection in the `except Exception as e:` branch: when the exception type is from `databricks.sdk.errors.*` OR an HTTP 503/429/timeout/connection-error pattern, set `reason="kg_serving_unavailable"` instead of the generic `f"{type(e).__name__}: {e}"`.

**Concrete except-branch update** (at line 448-450):

```python
    except asyncio.TimeoutError:
        _fts5_fallback(question, lang, job_id, reason="C1 timeout")
        return
    except Exception as e:  # noqa: BLE001 — QA-05: NEVER 500; route to fallback
        # LLM-DBX-04: detect Model Serving-specific failure modes for the
        # 'kg_serving_unavailable' reason code; everything else uses the
        # generic reason format.
        reason = _classify_serving_error(e)
        _fts5_fallback(question, lang, job_id, reason=reason)
        return
```

with the helper:

```python
import socket
def _classify_serving_error(e: Exception) -> str:
    """Map Model Serving exceptions → 'kg_serving_unavailable' reason code (LLM-DBX-04).

    Catches: databricks.sdk.errors.* (PermissionDenied, ResourceDoesNotExist,
    InternalError, BadRequest, DeadlineExceeded, etc.), requests.exceptions.*
    (ConnectionError, Timeout, HTTPError with status 503/429/504),
    and socket.timeout / TimeoutError.
    """
    name = type(e).__name__
    msg = str(e)
    # Databricks SDK error class names - all live under databricks.sdk.errors.
    sdk_errors = {
        "InternalError", "DeadlineExceeded", "ResourceExhausted",
        "Unavailable", "ServiceUnavailable", "Aborted",
    }
    if name in sdk_errors:
        return "kg_serving_unavailable"
    # HTTP error with 5xx / 429 status surfaced by the SDK as text
    if any(code in msg for code in ("HTTP 503", "HTTP 429", "HTTP 504",
                                     "model_overloaded", "rate_limit")):
        return "kg_serving_unavailable"
    # Network-level
    if isinstance(e, (socket.timeout, ConnectionError)):
        return "kg_serving_unavailable"
    # Anything else - fall through to generic reason
    return f"{name}: {e}"
```

### CONFIG-EXEMPTIONS impact for LLM-DBX-04

`kb/services/synthesize.py` is **NOT in the current CONFIG-EXEMPTIONS list** (only `lib/llm_complete.py` + `kg_synthesize.py` are). Three options:

| Option | Where the kg_serving_unavailable detection lands | Approval needed |
|--------|------------------------------------------------|-----------------|
| **A. Add `kb/services/synthesize.py` to CONFIG-EXEMPTIONS** | Same file (lines 145 + 448) | YES — explicit user approval |
| **B. Implement at the LightRAG factory layer** (`databricks-deploy/lightrag_databricks_provider.py`) | Wrap `make_llm_func` to catch + re-raise as a recognizable exception type | NO — under databricks-deploy/, allowed |
| **C. Implement at dispatcher layer** (`lib/llm_complete.py`) | Wrap the `databricks_serving` branch's returned callable in try/except | YES — but it's already in CONFIG-EXEMPTIONS |

**Recommendation: Option A** (extend CONFIG-EXEMPTIONS for `kb/services/synthesize.py`). Rationale:

1. Cleanest detection point — the existing `except Exception as e:` block already catches the right exceptions; we just extend the reason classification.
2. Tightly mirrors the existing kb-v2.1-1 hardening pattern at lines 189-214.
3. Wrapping at LightRAG factory or dispatcher layer scatters the error-classification across files; harder to maintain.
4. The user has already given precedent for `kb/`-edit exemptions (`lib/llm_complete.py` + `kg_synthesize.py`); adding `kb/services/synthesize.py` to that list is a natural extension and the REQ spirit clearly anticipates it (LLM-DBX-04 says "Reuses kb-v2.1-1 `KG_MODE_AVAILABLE` pattern").

**The plan must surface this exemption-extension explicitly to the user**, just like the embedding-side concern in Q3.

### LLM-DBX-04 verification test

```python
# tests/integration/test_kg_synthesize_dispatcher.py (NEW for kdb-2-03)
async def test_kg_serving_unavailable_falls_back_to_fts5(monkeypatch):
    """Force MosaicAI 503 → confirm /api/synthesize returns FTS5 markdown
    + confidence='fts5_fallback' + error reason 'kg_serving_unavailable'.
    """
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
    # Mock factory to return a callable that raises a Databricks SDK 503 equivalent
    async def boom(*a, **kw):
        raise RuntimeError("HTTP 503 Service Unavailable: model_overloaded")
    sys.path.insert(0, "databricks-deploy")
    import lightrag_databricks_provider as p
    monkeypatch.setattr(p, "make_llm_func", lambda: boom)

    from kb.services.synthesize import kb_synthesize
    job_id = "test-503"
    # ... call kb_synthesize, await job_store.get_job(job_id) ...
    job = job_store.get_job(job_id)
    assert job["status"] == "done"  # NEVER 500
    assert job["confidence"] == "fts5_fallback"
    assert "kg_serving_unavailable" in job["error"]
```

---

## Q5 — Smoke 1/2 methodology in this Private-Link workspace

**Confidence:** HIGH on the constraint (kdb-1 SPIKE-FINDINGS provided extensive evidence); MEDIUM on the recommended verification path (specifically: in-workspace serverless notebook proxy CAN talk to App URL, but it has not been tested in this workspace).

### The Private Link blocker (verbatim from kdb-1 SPIKE-FINDINGS lines 87-103)

After spike-app `omnigraph-kb-spike-01b` deployed, all external paths failed:

- Browser access via public DNS → HTTP 403 `{"X-Databricks-Reason-Phrase":"Public access is not allowed for workspace: 2717931942638877"}`
- Workspace UI proxy access → same 403
- Bearer token via `databricks auth token` → same 403
- Adding `user_api_scopes` + `CAN_MANAGE` → no effect

**Root cause** (per kdb-1 finding line 98, citing MS Learn Q&A and Databricks Community search):

> "this workspace `2717931942638877` has Azure Private Link configured with no public network access. App URLs (`*.azure.databricksapps.com`) are CNAME-routed via the workspace's private endpoint, but the user's machine resolves via public DNS → workspace rejects. Documented fix is to set up a Private DNS Zone for `azure.databricksapps.com` → workspace's private IP — which is an Azure infrastructure change outside this milestone's scope."

The user confirmed "other Apps in this workspace also can't be hit directly via browser; they're accessed via in-workspace internal proxying that wasn't replicable from external CLI."

### Verification path options

| Path | How | Smoke 1 | Smoke 2 | Verdict |
|------|-----|---------|---------|---------|
| **External Bearer-token curl** (orchestrator prompt's original idea) | `curl -H "Authorization: Bearer $TOKEN" $APP_URL/` | ❌ Blocked by Private Link | ❌ | NOT VIABLE |
| **External browser SSO** (orchestrator prompt's fallback) | User opens App URL in browser → SSO prompt → KB renders | ❌ Same 403 (Private Link is at Azure-DNS level, not auth) | ❌ | NOT VIABLE |
| **In-workspace serverless notebook curl** | Spawn notebook in workspace; notebook does `requests.get(APP_URL, headers={"Authorization": f"Bearer {dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()}"})` | UNCERTAIN — same Private DNS issue may apply if notebook runs on serverless cluster (which routes via public DNS still) | UNCERTAIN | TBD in execute phase |
| **In-workspace classic-cluster notebook curl** | Same as above but on a workspace-VPC-attached cluster (private DNS resolves correctly inside workspace VNet) | LIKELY WORKS — workspace-VNet cluster resolves App URL via internal DNS | LIKELY WORKS | BEST AUTOMATION PATH (verify in plan kdb-2-04) |
| **Workspace UI in-browser** (user authenticated to workspace UI; clicks Apps tab → opens App URL in same browser) | Browser is already inside the workspace SSO session; the workspace UI proxies to the App | LIKELY WORKS — kdb-1 SPIKE didn't try this specifically (only tried direct App URL access from outside the workspace UI) | LIKELY WORKS | RECOMMENDED FOR HUMAN UAT |
| **User SSH to a Databricks-VNet jumphost** | If the user's corp network has VNet peering to the Databricks workspace VNet, a jumphost there can curl the App URL | UNKNOWN | UNKNOWN | Out of scope (infrastructure-level) |

### Recommended Smoke 1+2 verification path

**Primary path — User Workspace UI browser session (manual UAT, user-in-loop)**:

1. User opens Databricks workspace UI (`https://adb-2717931942638877.17.azuredatabricks.net/`) → SSO via EDC SSO.
2. Navigate to Apps tab → click `omnigraph-kb` → Workspace UI proxies to the App URL.
3. KB home page should render (Smoke 1 verification: home page renders, article count > 0, topic chips visible).
4. Use the page's search box → submit "AI Agent" (zh) → ≥ 3 hits.
5. Switch UI to en → submit "langchain framework" → ≥ 3 hits (Smoke 2).
6. Click a result → article detail page renders with images via `/static/img/...` (Smoke 2 add-on per OPS-DBX-02).

User captures screenshots → pastes paths into `kdb-2-SMOKE-EVIDENCE.md`. This is human-in-loop but unavoidable under Private Link.

**Secondary automation path — In-workspace classic-cluster notebook (best-effort automation, can be tried in parallel)**:

Workspace serverless cluster may not work (DNS resolves on cluster side via Azure public DNS), but a classic cluster attached to the workspace VNet should resolve App URLs via Azure private DNS. **TBD in execute phase**: try first, accept failure as expected if it doesn't work.

```python
# In a workspace classic-cluster notebook, attempt:
import requests
APP_URL = "https://omnigraph-kb-<workspace-id>.azure.databricksapps.com"
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
r = requests.get(f"{APP_URL}/", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
print(r.status_code, len(r.text))  # expect 200 + non-trivial body
r2 = requests.get(f"{APP_URL}/api/search?q=AI%20Agent", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
print(r2.status_code, len(r2.json().get("hits", [])))  # expect 200 + ≥ 3 hits
```

If this works, OPS-DBX-01/02 can be verified programmatically (notebook outputs captured as evidence).

**Tertiary fallback — Playwright MCP from local Windows box**:

Per CLAUDE.md, the user has Playwright MCP configured locally. If the user's home/corp network has DNS visibility to the workspace's App URL (e.g., via Tailscale or a workspace-VPN client), Playwright MCP can drive the browser through SSO. **TBD — likely unavailable on EDC corp network** (Private Link is precisely designed to block this), but the user may have a different network path.

### Plan-level recommendation for kdb-2-04 (smoke plan)

The Smoke 1+2 verification step in `kdb-2-04-deploy-and-smoke-PLAN.md` should be structured:

1. **Primary**: User-in-loop browser session (mandatory; manual UAT). Plan emits a checklist for the user; user pastes screenshots back into `kdb-2-SMOKE-EVIDENCE.md`.
2. **Secondary**: Attempt classic-cluster notebook automation IF the user has access to a classic cluster in this workspace. Capture notebook output → `kdb-2-SMOKE-EVIDENCE.md`.
3. **Tertiary**: Try Playwright MCP from local Windows. If it works, paste screenshot to `.playwright-mcp/kdb-2-smoke1-*.png` etc.

The plan must NOT silently assume external curl works. CLAUDE.md Rule 3 (KB local UAT) does NOT apply here (no `kb/` template/static change), but Rule 5 (don't outsource SSH/mechanical to user) DOES — the agent can't drive the browser session, but it CAN write a paste-ready prompt + checklist for the user to follow.

---

## Q6 — Cold-start budget (DEPLOY-DBX-05)

**Confidence:** HIGH (kdb-1 SPIKE measured 9s deploy-to-RUNNING for empty App; kdb-1.5 startup_adapter is fully tested for empty-source no-op).

### kdb-2 first deploy projected cold-start

Components, in order:

1. **Apps platform: deploy → SUCCEEDED**: ~9s measured in kdb-1 SPIKE-FINDINGS line 25 + 42 (`databricks apps deploy --wait` returned in 9s for the empty test-app).
2. **Apps runtime: pip install from `databricks-deploy/requirements.txt`**: 8 deps total (kdb-1.5 baseline) — `databricks-sdk`, `lightrag-hku==1.4.15`, `numpy>=1.26.0`, `fastapi`, `uvicorn`, `jinja2`, `markdown`, `pygments` + 2 test deps that won't be installed in production (`pytest`, `pytest-asyncio`). Estimated 30-60s on Apps runtime (cached layer for pinned versions accelerates subsequent deploys).
3. **Startup adapter: `hydrate_lightrag_storage_from_volume()`**: At kdb-2 baseline, `lightrag_storage/` on UC Volume is **empty** (verified per kdb-1 WAVE2-FINDINGS anti-pattern audit #5: *"DO NOT copy `lightrag_storage/` from Hermes ✅ Confirmed — `lightrag_storage/` sub-dir created empty"*). The adapter's empty-source branch (kdb-1.5-RESEARCH Decision 1, lines 348-356) returns `CopyResult(status="skipped", reason="source_empty_pre_seed")` in **<10ms** (just an `iterdir()` check + an mkdir).
4. **uvicorn boot + FastAPI module import**: 2-5s (FastAPI + lightrag + databricks-sdk imports; numpy at top of provider module is heavyish but already loaded by lightrag).
5. **`/health` endpoint first 200**: covered by uvicorn boot; no separate latency.

**Estimated total**: 9s (deploy) + 40s (pip install, conservative) + 0s (adapter no-op for empty Vol) + 5s (uvicorn boot) ≈ **~55s realistic**, well within DEPLOY-DBX-05's 20-min default budget.

### Post-kdb-2.5 cold-start projection (informational; not a kdb-2 concern)

kdb-1.5-RESEARCH Q2 estimated post-kdb-2.5 lightrag_storage size at **400-600 MB** (3× shrinkage from Hermes 1.315 GB at 3072-dim → 1024-dim Qwen3). With `shutil.copytree` from FUSE (>100 MB/s typical) the copy adds 4-6s. So post-kdb-2.5 realistic cold-start ≈ 60-65s — still within 20-min budget but worth noting as a kdb-3 verification check.

### Empty-source idempotency in kdb-1.5 adapter (verified)

kdb-1.5-01 Plan Test 1 (`test_hydrate_skipped_when_source_empty`) is one of 5 unit tests that PASS:

- `databricks-deploy/tests/test_startup_adapter.py::test_hydrate_skipped_when_source_empty`: confirms empty `src/lightrag_storage/` → `CopyResult(status="skipped", reason="source_empty_pre_seed", method=None)`, no raise, dst directory created but empty.
- `databricks-deploy/tests/test_startup_adapter.py::test_hydrate_idempotent_skip_on_repeat`: confirms second call short-circuits via the `dst.exists() and any(dst.iterdir())` check at `startup_adapter.py:81`.

Both branches are exercised by the fast path of kdb-2 first deploy.

### Verification methodology for DEPLOY-DBX-05

```bash
# kdb-2-04 plan verification step:
START=$(date +%s)
databricks --profile dev apps deploy omnigraph-kb \
  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb \
  --timeout 20m
END=$(date +%s)
echo "Deploy elapsed: $((END-START))s"
# expect: < 60s realistic, < 20min budget

# Then poll for RUNNING state:
for i in $(seq 1 30); do
  STATE=$(databricks --profile dev apps get omnigraph-kb -o json | jq -r '.compute_status.state')
  if [ "$STATE" = "ACTIVE" ]; then
    echo "RUNNING at iter $i (~${i}0s)"; break
  fi
  sleep 10
done
```

Capture the elapsed time + pip-install log excerpt + adapter log line (`startup_adapter: skip source_empty_pre_seed src=...`) into `kdb-2-SMOKE-EVIDENCE.md` for DEPLOY-DBX-05 evidence. The adapter log line also confirms DEPLOY-DBX-04's `command:` wiring works.

---

## Q7 — `app.yaml` `command:` shape for pre-uvicorn startup_adapter (DEPLOY-DBX-03/04)

**Confidence:** MEDIUM-HIGH on the recommended shape (sequence form is canonical per MS Learn STACK.md research lines 207-217); MEDIUM on the `bash -c` env-substitution behavior (Apps doesn't run command in a shell per STACK.md line 14, but `bash -c` invocation IS a shell — this is intentional).

### Apps `command:` constraints (from STACK.md research)

- **`command:` is a sequence (YAML list)**, not a single string. Apps does not parse it through a shell — there's no `&&` chaining, no `|` piping at the top level.
- **Env vars OUTSIDE `app.yaml` are not visible** to the command (STACK.md line 14: *"Apps does NOT run command in a shell — env vars defined outside app config aren't visible. **One exception:** `DATABRICKS_APP_PORT` is substituted at runtime in the command."*).
- **`$DATABRICKS_APP_PORT` is the only string-substituted env var** in the command itself. Inside Python (`os.environ['DATABRICKS_APP_PORT']`), it resolves at runtime.

### Three options for multi-step (run startup_adapter, THEN uvicorn)

| Option | Shape | Pros | Cons |
|--------|-------|------|------|
| **A. Single `bash -c` step** | `command: ["bash", "-c", "python -m startup_adapter && exec uvicorn app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT"]` | One YAML element; env-var substitution survives bash; tight | Requires bash in Apps base image (yes — STACK.md confirms Linux base); makes app.yaml slightly less readable |
| **B. Wrapper shell script** | `command: ["bash", "/app/databricks-deploy/start.sh"]` plus `start.sh` containing the python + uvicorn lines | Cleaner app.yaml; reusable across deploys | One extra file to maintain; sourcing logic split across `app.yaml` + script |
| **C. Sequence form with chain via Python** | `command: ["python", "-c", "import startup_adapter; startup_adapter.hydrate_lightrag_storage_from_volume(); import uvicorn; uvicorn.run('app:app', host='0.0.0.0', port=int(os.environ['DATABRICKS_APP_PORT']))"]` | Single language (Python); no shell | Complex one-liner; harder to debug; loses uvicorn's nice CLI flags |
| **D. Python entry-point file** | Create `databricks-deploy/main.py` that imports + runs adapter, then calls uvicorn programmatically. `command: ["python", "/app/databricks-deploy/main.py"]` | Clean; testable; single Python entry point | Extra file; bypasses uvicorn CLI ergonomics |

**Recommendation: Option A** (single `bash -c` step). Rationale:

1. Smallest diff to app.yaml (one YAML list element).
2. `$DATABRICKS_APP_PORT` substitution survives — Apps substitutes it BEFORE invoking the command, so by the time bash sees it, it's the literal port number.
3. `exec` ensures the uvicorn process replaces the bash process (clean signal handling on shutdown).
4. `&&` semantics: if startup_adapter fails (raises non-zero exit), uvicorn doesn't start — fail-fast.

### Concrete `app.yaml` (DEPLOY-DBX-02/03/04/08/09 + LLM-DBX-05)

```yaml
# databricks-deploy/app.yaml
command:
  - bash
  - "-c"
  - >-
    cd /app/databricks-deploy
    && PYTHONPATH=/app:/app/databricks-deploy
       python -c "from startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())"
    && exec uvicorn kb.api.app:app
       --host 0.0.0.0 --port $DATABRICKS_APP_PORT

env:
  # OmniGraph BASE_DIR — adapter copies to /tmp/omnigraph_vault; LightRAG
  # workspace_dir resolves there; kol_scan.db read direct from Volume via ?mode=ro
  - name: OMNIGRAPH_BASE_DIR
    value: "/tmp/omnigraph_vault"

  # LLM dispatcher provider lock — defends against any default-DeepSeek code path
  # making outbound calls to non-Databricks endpoints (DEPLOY-DBX-08).
  - name: OMNIGRAPH_LLM_PROVIDER
    value: "databricks_serving"

  # MosaicAI Model Serving endpoint names (LLM-DBX-05).
  - name: KB_LLM_MODEL
    value: "databricks-claude-sonnet-4-6"

  - name: KB_EMBEDDING_MODEL
    value: "databricks-qwen3-embedding-0-6b"

  # NOTE: NO `valueFrom:` for any LLM-related env. Apps SP auto-injection
  # (DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET) carries Model Serving auth.

  # NOTE: KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS are
  # deliberately UNSET (DEPLOY-DBX-09). Vertex Gemini path retired in v1.

  # KB_DB_PATH points the FastAPI article query layer at the on-Volume DB.
  - name: KB_DB_PATH
    value: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db"

  # Defensive: pin DEEPSEEK_API_KEY=dummy to satisfy the Phase 5 cross-coupling
  # at lib/__init__.py — without this, any import of lib that touches
  # llm_deepseek would raise. dummy is correct because dispatcher routes around
  # DeepSeek via OMNIGRAPH_LLM_PROVIDER=databricks_serving.
  - name: DEEPSEEK_API_KEY
    value: "dummy"
```

### Why `cd /app/databricks-deploy` first

The Apps runtime mounts source code at `/app/` (per Apps Cookbook). With `--source-code-path` pointing at the repo root, the workspace-mounted layout becomes `/app/databricks-deploy/...`. The startup_adapter and provider modules are top-level modules under `databricks-deploy/`, so we add that to PYTHONPATH (because Python doesn't accept hyphens in package names) AND `cd` into it so relative imports inside the adapter work.

### Risk: `app.yaml` location

DEPLOY-DBX-02 says `app.yaml` MUST be at root of `--source-code-path`. Two valid configurations:

1. `--source-code-path /Workspace/.../omnigraph-kb` where the workspace mirrors the repo (so app.yaml is at `databricks-deploy/app.yaml`); use `--source-code-path` pointing at `databricks-deploy/`.
2. Or copy app.yaml to repo root (NOT recommended — violates CONFIG-DBX-02 which says all Databricks-target config lives under `databricks-deploy/`).

**Recommended**: deploy with `--source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy` so Apps sees `app.yaml` at root.

But wait — this means the App can't access `kb/` (which lives at repo root, not under `databricks-deploy/`). That's a real problem. **Resolution**: `databricks workspace import-dir` should sync the WHOLE repo to the workspace, then `--source-code-path` points at `/Workspace/.../omnigraph-kb` (repo root) and **app.yaml lives at `databricks-deploy/app.yaml` BUT `--source-code-path` points at the parent**. Per STACK.md line 17: *"File location: **root of project directory**"* — this implies app.yaml at the same level as `--source-code-path`. So either:

- **Option a**: Move `app.yaml` to repo root → violates CONFIG-DBX-02.
- **Option b**: Set `--source-code-path` at `databricks-deploy/` → loses `kb/` access.
- **Option c**: Symlink `app.yaml` from repo root to `databricks-deploy/app.yaml` → CONFIG-DBX-02 strictly says no new files at repo root, but a symlink might be acceptable.
- **Option d**: Restructure so `databricks-deploy/` contains a copy/symlink of the `kb/` tree at deploy time, OR have `databricks-deploy/main.py` import from `../kb/`.

**TBD in execute phase** — verify the exact source-code-path semantics in kdb-2 first deploy. **Recommended to plan**: deploy with `--source-code-path /Workspace/.../omnigraph-kb/databricks-deploy` and have the `command:` `cd /app && exec uvicorn kb.api.app:app ...` (where `/app` is the parent that contains both the synced repo AND `databricks-deploy/`). This requires the workspace import-dir to land BOTH `kb/` AND `databricks-deploy/` under a common parent — achievable with `databricks workspace import-dir <repo> /Workspace/.../omnigraph-kb` (whole-repo sync).

This is the highest-uncertainty area in the research. **Recommend**: kdb-2-04 plan includes a Wave 0 step that **just deploys the App with a minimal `command:` and a no-op startup_adapter** to validate the path layout BEFORE wiring in the full multi-step. Cheap (one deploy, ~60s) and surfaces this concern early.

---

## Q8 — Makefile recipe surface (DEPLOY-DBX recipes)

**Confidence:** HIGH on most recipes (kdb-1.5 + kdb-1 already proved CLI subcommands); MEDIUM on `make stop` (subcommand existence not verified).

### Recipe by recipe

#### `make deploy` (DEPLOY-DBX-01 + DEPLOY-DBX-04 + DEPLOY-DBX-05)

```makefile
deploy:
	MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir \
	  . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
	databricks --profile dev apps deploy omnigraph-kb \
	  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
	databricks --profile dev apps get omnigraph-kb \
	  -o json | jq '{state: .compute_status.state, url: .url}'
```

- `MSYS_NO_PATHCONV=1` — required on Windows Git Bash (kdb-1 SPIKE-FINDINGS line 51).
- `import-dir` syncs whole repo first, so `databricks-deploy/` AND `kb/` land in workspace under same parent.
- `apps deploy` points at `/Workspace/.../omnigraph-kb/databricks-deploy` so app.yaml is at the source-code-path root.

#### `make logs` (operations runbook)

```makefile
logs:
	@echo "Apps logs not exposed via CLI in v0.260.0 (kdb-1 SPIKE-FINDINGS line 52)."
	@echo "View via: workspace UI Apps tab → omnigraph-kb → Logs"
	@echo "Workspace URL: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
	databricks --profile dev apps get omnigraph-kb -o json | \
	  jq '{state: .compute_status.state, url: .url, deployment_id: .active_deployment.deployment_id}'
```

`databricks apps logs` does NOT exist in v0.260.0 (verified in kdb-1 SPIKE-FINDINGS line 52). Only the workspace UI Apps tab shows logs. Recipe just `echo`s the URL hint and queries the deploy state via `apps get`.

#### `make stop` (operations)

```makefile
stop:
	databricks --profile dev apps stop omnigraph-kb
```

**TBD in execute phase**: verify `databricks apps stop` exists in v0.260.0. Apps Cookbook + STACK.md don't explicitly mention it. If it doesn't exist, fall back to `databricks apps delete` (destructive — recreates fresh) — but that loses Apps SP grants. **Recommend Plan kdb-2-04 to verify**: the user can run `databricks --profile dev apps stop --help` first; if it returns a help page, recipe is good. If "unknown command" → swap to `delete` with a comment.

#### `make smoke` (manual checklist)

```makefile
smoke:
	@echo "kdb-2 Smoke 1+2 — manual UAT required (Private Link blocks external curl)."
	@echo ""
	@echo "1. Open in browser (already authenticated to workspace):"
	@echo "   https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
	@echo ""
	@echo "2. Smoke 1 (OPS-DBX-01) — bilingual UI toggle:"
	@echo "   - Default zh-CN UI; switch to en; refresh; cookie persists; ?lang=zh hard-switch"
	@echo ""
	@echo "3. Smoke 2 (OPS-DBX-02) — bilingual search + detail page:"
	@echo "   - 中文 UI: 'AI Agent 框架' → ≥ 3 中文 hits"
	@echo "   - en UI: 'langchain framework' → ≥ 3 en hits"
	@echo "   - Click any en article → /article/<hash> renders <html lang=\"en\"> + 'English' badge + images via /static/img/..."
	@echo "   - Click any zh article → /article/<hash> renders <html lang=\"zh-CN\"> + '中文' badge"
	@echo ""
	@echo "4. Capture screenshots → kdb-2-SMOKE-EVIDENCE.md (paste paths)"
```

Per Q5 — automation isn't viable under Private Link; recipe just emits the checklist.

#### `make sp-grants` (AUTH-DBX-01..04)

```makefile
sp-grants:
	@echo "Run AUTH-DBX-01..04 grants. App SP client_id discovered from apps get."
	@CLIENT_ID=$$(databricks --profile dev apps get omnigraph-kb -o json | jq -r '.service_principal_client_id'); \
	  echo "App SP client_id: $$CLIENT_ID"; \
	  echo "Run via mcp__databricks-mcp-server execute_sql:"; \
	  echo "  GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO \`$$CLIENT_ID\`;"; \
	  echo ""; \
	  echo "Then verify CAN_QUERY on serving endpoints:"; \
	  echo "  databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6"; \
	  echo "  databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b"
```

The `mcp__databricks-mcp-server execute_sql` tool is the actual grant-execution channel (CLI doesn't have a direct `databricks unity-catalog grant ...` subcommand; SQL is the path). Recipe shows the user the SQL to paste.

#### Final Makefile skeleton (~30 lines)

```makefile
# databricks-deploy/Makefile — DEPLOY-DBX recipes
# kdb-2 deliverable. Uses --profile dev throughout (matches kdb-1.5 dry-run pattern).

.PHONY: deploy logs stop smoke sp-grants

deploy:
	MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir \
	  . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
	databricks --profile dev apps deploy omnigraph-kb \
	  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
	databricks --profile dev apps get omnigraph-kb -o json | \
	  jq '{state: .compute_status.state, url: .url}'

logs:
	@echo "Apps logs only via workspace UI Apps tab (databricks apps logs not in v0.260)."
	@echo "URL: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
	databricks --profile dev apps get omnigraph-kb -o json | \
	  jq '{state: .compute_status.state, url: .url}'

stop:
	databricks --profile dev apps stop omnigraph-kb

smoke:
	@echo "Smoke 1+2 manual UAT (Private Link). See kdb-2-04 plan checklist."
	@echo "Workspace UI: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"

sp-grants:
	@CLIENT_ID=$$(databricks --profile dev apps get omnigraph-kb -o json | jq -r '.service_principal_client_id'); \
	  echo "App SP client_id: $$CLIENT_ID"; \
	  echo "Paste into mcp__databricks-mcp-server execute_sql:"; \
	  echo "  GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO \`$$CLIENT_ID\`;"; \
	  databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6 || true; \
	  databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b || true
```

`MSYS_NO_PATHCONV=1` only on the Windows-relevant call (`workspace import-dir`); other CLI calls don't touch path-conv.

---

## Architectural Decisions (locked-in for planner)

### Decision 1: `app.yaml` `command:` shape — single `bash -c` step (Q7 Option A)

```yaml
command:
  - bash
  - "-c"
  - cd /app/databricks-deploy && PYTHONPATH=/app:/app/databricks-deploy python -c "from startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())" && exec uvicorn kb.api.app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT
```

Confidence: MEDIUM. Source-code-path layout is the highest-uncertainty area (Q7); kdb-2-04 plan needs a Wave 0 minimal-deploy validation step.

### Decision 2: `lib/llm_complete.py` `databricks_serving` branch (Q2)

Insert at line 42:

```python
    if provider == "databricks_serving":
        from lightrag_databricks_provider import make_llm_func
        return make_llm_func()
```

Plus extend `_VALID` on line 27 to include `"databricks_serving"`. Confidence: HIGH.

### Decision 3: LLM-DBX-02 actual scope (Q3)

- **LLM side**: NO new code in `kg_synthesize.py`. Existing quick-260509-s29 dispatcher integration (line 19 + line 106) is the satisfying diff. CONFIG-EXEMPTIONS.md flips both rows from `NOT YET MODIFIED` to `MODIFIED — see commit <hash>` (referencing the LLM-DBX-01 dispatcher-branch commit + the historical kg_synthesize commit).
- **Embedding side**: surface to user — recommend Option A (mirror dispatcher pattern with new `lib/embedding_complete.py`); CONFIG-EXEMPTIONS extension required. **Plan must NOT silently choose**.

Confidence: HIGH on LLM-side finding; MEDIUM on embedding-side recommendation (Option A is cleanest, but the user may prefer the smaller-blast-radius Option C).

### Decision 4: LLM-DBX-04 reason code + exception types (Q4)

- Rename existing unused `kg_unavailable` literal → `kg_serving_unavailable` in `kb/services/synthesize.py:145`.
- Add `_classify_serving_error(e)` helper that maps Databricks SDK errors + 503/429/timeout/connection patterns → `"kg_serving_unavailable"` reason.
- Update `kb_synthesize` `except Exception as e:` branch (line 448) to use the helper.
- Surface to user: extend CONFIG-EXEMPTIONS to include `kb/services/synthesize.py`.

Confidence: HIGH on the implementation shape; MEDIUM on the user-approval cycle.

### Decision 5: Smoke 1+2 verification path (Q5)

- **Primary**: User browser session via workspace UI Apps tab (mandatory manual UAT).
- **Secondary** (best-effort): Classic-cluster notebook proxy if available.
- **Tertiary** (optional): Playwright MCP from local Windows IF user network reaches App URL.

Plan emits paste-ready human checklist; user pastes screenshots back. **No external curl path**.

Confidence: MEDIUM. Workspace UI proxy approach is documented but not yet validated for this specific App in this workspace. Recommend kdb-2-04 includes a "Step 0" where user confirms they CAN see the App URL render in workspace UI before proceeding to detailed Smoke 1/2 checks.

---

## Risks

### Risk 1: Smoke 1+2 verification blocked by Private Link AND workspace UI proxy

**Probability**: LOW (workspace UI typically works for Apps within the same workspace SSO session).

**Impact**: kdb-2 cannot close on OPS-DBX-01/02 evidence; must escalate to user to provide alternative (e.g., classic cluster, jumphost).

**Mitigation**: kdb-2-04 plan includes early "App URL is reachable from user's session" check (Step 0). If that fails, milestone pauses pending escalation. Don't burn time on automation paths that may not work.

### Risk 2: Cold-start under real adapter load (kdb-2.5 Volume populated)

**Probability**: MEDIUM (kdb-1.5-RESEARCH Q2 estimated 400-600 MB post-Qwen3 lightrag_storage; actual UC Volume → App `/tmp` Files-API throughput is documentary only).

**Impact**: Post-kdb-2.5 cold-start exceeds 60s; need to raise app.yaml budget OR implement lazy-load LightRAG.

**Mitigation**: kdb-2 baseline (empty Volume) is trivial (< 60s); the 20-min DEPLOY-DBX-05 budget gives 20× headroom. Real measurement happens in kdb-3 first deploy after kdb-2.5 lands. Adapter logs `bytes_copied + elapsed_s` (kdb-1.5-01-SUMMARY.md) so kdb-3 has data.

### Risk 3: `databricks apps logs` CLI absence — operator UX regression

**Probability**: HIGH (kdb-1 SPIKE-FINDINGS line 52 confirmed absence in v0.260.0).

**Impact**: Operator (user) must always navigate to workspace UI for log inspection; less ergonomic than `gcloud logging read` etc.

**Mitigation**: Document in `RUNBOOK.md` (kdb-3 deliverable) + bake into `make logs` recipe (Q8) which echoes the workspace UI URL. Also document `databricks apps get omnigraph-kb` for state inspection.

### Risk 4: LLM-DBX-02 embedding-side gap surfaces only at first synthesis call

**Probability**: HIGH if Option C (smaller scope) is chosen; LOW if Option A (dispatcher mirror) is chosen.

**Impact**: deployed App with `OMNIGRAPH_LLM_PROVIDER=databricks_serving` AND post-kdb-2.5 dim=1024 Volume content → first `/synthesize` call raises dim-mismatch. Smoke 3 (kdb-3) would surface this; kdb-2 Smoke 1+2 wouldn't catch it because they don't exercise the embedding lookup.

**Mitigation**: surface to user during planning; default-recommend Option A (dispatcher mirror); add LLM-DBX-04 503-fallback test that exercises the FULL synthesize path including embedding.

### Risk 5: `app.yaml` `--source-code-path` layout produces wrong PYTHONPATH

**Probability**: MEDIUM (Q7 deferred to execute-phase verification).

**Impact**: First deploy fails because `kb/` modules aren't importable from where uvicorn is invoked.

**Mitigation**: kdb-2-04 plan Wave 0 step does a minimal-deploy with no-op `command:` (just `python -c "import sys; print(sys.path)"`) to verify the layout BEFORE wiring the full adapter + uvicorn.

### Risk 6: Apps SP CAN_QUERY ACL setup grammar (AUTH-DBX-04)

**Probability**: MEDIUM (kdb-1 SPIKE-FINDINGS line 23 punted on this; Path A `serving-endpoints get-permissions` not yet validated).

**Impact**: First synthesis call from deployed App returns 403 from Model Serving despite App being RUNNING.

**Mitigation**: Path B (in-app debug endpoint that probes WorkspaceClient().serving_endpoints.query) provides immediate runtime validation even if Path A CLI fails. Plan includes both paths; either green = AUTH-DBX-04 satisfied.

---

## Validation Architecture

> Per `.planning/config.json` workflow.nyquist_validation default — included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ + pytest-asyncio>=0.23.0 (existing in `databricks-deploy/requirements.txt`; project venv has both) |
| Config files | `databricks-deploy/pytest.ini` (kdb-1.5 deliverable, has `asyncio_mode=auto` + `dryrun` marker) ; `tests/` test discovery via project root `pytest.ini` (existing) |
| Quick run command | `pytest tests/unit/test_llm_complete.py -v` |
| Full suite command | `pytest databricks-deploy/tests/ tests/unit/test_llm_complete.py tests/integration/test_kg_synthesize_dispatcher.py -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-DBX-01 | App SP has USE_CATALOG | manual SQL | `mcp__databricks-mcp-server execute_sql "SHOW GRANTS ON CATALOG mdlg_ai_shared"` filter principal | manual (kdb-2-01) |
| AUTH-DBX-02 | App SP has USE_SCHEMA | manual SQL | same | manual (kdb-2-01) |
| AUTH-DBX-03 | App SP has READ_VOLUME (no WRITE) | manual SQL | same | manual (kdb-2-01) |
| AUTH-DBX-04 | App SP has CAN_QUERY on both Model Serving endpoints | CLI Path A + Path B | `databricks serving-endpoints get-permissions ...` AND in-app probe | manual + runtime |
| AUTH-DBX-05 | SSO gates | manual UAT | open App URL → SSO prompt observed | manual (kdb-2-04) |
| LLM-DBX-01 | dispatcher branch + 4 unit tests + lazy-import + error-path | pytest unit | `pytest tests/unit/test_llm_complete.py -v` | ❌ Wave 0 (extend existing 5-test file with 4 new tests) |
| LLM-DBX-02 LLM-side | env=databricks_serving exercises dispatcher through synthesize_response | pytest integration | `OMNIGRAPH_LLM_PROVIDER=databricks_serving pytest tests/integration/test_kg_synthesize_dispatcher.py::test_dispatcher_path_databricks -v` | ❌ Wave 0 |
| LLM-DBX-02 embedding-side | env=databricks_serving exercises Qwen3 dim=1024 path through embedding_func | pytest integration | same file, separate test | ❌ Wave 0 (assumes Option A in Q3) |
| LLM-DBX-04 | 503 forced-failure → FTS5 fallback markdown + reason='kg_serving_unavailable' | pytest integration | `pytest tests/integration/test_kg_synthesize_dispatcher.py::test_kg_serving_unavailable_falls_back_to_fts5 -v` | ❌ Wave 0 |
| LLM-DBX-05 | 3 literal env in app.yaml | grep | `grep -cE "OMNIGRAPH_LLM_PROVIDER\|KB_LLM_MODEL\|KB_EMBEDDING_MODEL" databricks-deploy/app.yaml` returns 3 | grep |
| DEPLOY-DBX-01 | App created | CLI | `databricks apps get omnigraph-kb` returns non-error | manual (kdb-2-04) |
| DEPLOY-DBX-02 | app.yaml at source-code-path root | grep | `find databricks-deploy -maxdepth 1 -name app.yaml` returns 1 | grep |
| DEPLOY-DBX-03 | command uses $DATABRICKS_APP_PORT | grep | `grep -c "DATABRICKS_APP_PORT" databricks-deploy/app.yaml` returns ≥ 1; `grep -c ":8766" databricks-deploy/app.yaml` returns 0 | grep |
| DEPLOY-DBX-04 | env literals present | grep | as LLM-DBX-05 | grep |
| DEPLOY-DBX-05 | RUNNING < 20 min | CLI | `databricks apps deploy omnigraph-kb --timeout 20m` returns SUCCEEDED | manual (kdb-2-04) |
| DEPLOY-DBX-06 | App URL returns 200 after SSO | manual UAT | browser session in workspace | manual (kdb-2-04) |
| DEPLOY-DBX-07 | requirements.txt no DeepSeek deps | grep | `grep -ci "deepseek" databricks-deploy/requirements.txt` returns 0 | grep (kdb-1.5 baseline) |
| DEPLOY-DBX-08 | OMNIGRAPH_LLM_PROVIDER=databricks_serving literal | grep | `grep -c "OMNIGRAPH_LLM_PROVIDER" databricks-deploy/app.yaml` and `grep -c "valueFrom" databricks-deploy/app.yaml` for that line returns 1 + 0 | grep |
| DEPLOY-DBX-09 | KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS NOT set | grep | `grep -cE "KB_KG_GCP_SA_KEY_PATH\|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml` returns 0 | grep |
| OPS-DBX-01 | KB-v2 Smoke 1 | manual UAT | user browser session screenshots | manual (kdb-2-04) |
| OPS-DBX-02 | KB-v2 Smoke 2 | manual UAT | user browser session screenshots | manual (kdb-2-04) |

### Sampling Rate

- **Per task commit**: `pytest tests/unit/test_llm_complete.py -v -x` (LLM-DBX-01 5 + 4 new = 9 tests, < 5s)
- **Per wave merge**: `pytest tests/unit/test_llm_complete.py tests/integration/test_kg_synthesize_dispatcher.py -v` (mocks, no Model Serving, < 30s)
- **Phase gate**: full suite green + manual UAT evidence in `kdb-2-SMOKE-EVIDENCE.md` before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/integration/test_kg_synthesize_dispatcher.py` — 3 new tests (dispatcher path, embedding path, kg_serving_unavailable)
- [ ] `tests/unit/test_llm_complete.py` — extended with 4 new tests for `databricks_serving` branch
- [ ] **Decision required from user**: Q3 embedding-side handling (Option A/B/C/D)
- [ ] **Decision required from user**: Q4 CONFIG-EXEMPTIONS extension to `kb/services/synthesize.py`
- [ ] `databricks-deploy/app.yaml` (NEW)
- [ ] `databricks-deploy/Makefile` (NEW)
- [ ] `databricks-deploy/CONFIG-EXEMPTIONS.md` extended ledger (kdb-1.5 baseline existed)
- [ ] `kdb-2-SMOKE-EVIDENCE.md` (NEW; populated during smoke)
- [ ] `kdb-2-VERIFICATION.md` (NEW; consolidates all 20 REQs at phase close)
- [ ] (If Option A from Q3): `lib/embedding_complete.py` (NEW)
- [ ] (Conditional on Q4 user-approval): `kb/services/synthesize.py` LLM-DBX-04 edits

---

## Files Affected

### NEW (created by kdb-2)

| Path | Purpose |
|------|---------|
| `databricks-deploy/app.yaml` | DEPLOY-DBX-02..04, LLM-DBX-05 |
| `databricks-deploy/Makefile` | DEPLOY-DBX recipes |
| `tests/integration/test_kg_synthesize_dispatcher.py` | LLM-DBX-02 + LLM-DBX-04 verification |
| `kdb-2-SMOKE-EVIDENCE.md` | OPS-DBX-01/02 evidence |
| `kdb-2-VERIFICATION.md` | phase-close 20-REQ checkbox audit |
| `lib/embedding_complete.py` | (Conditional on Q3 Option A user-approval) embedding dispatcher mirror |

### MODIFY (CONFIG-EXEMPTIONS scope; planner must surface for user approval)

| Path | Scope of change | Approval status |
|------|-----------------|-----------------|
| `lib/llm_complete.py` | Add `databricks_serving` branch + extend `_VALID` (Q2) | ALREADY in CONFIG-EXEMPTIONS — no extra approval |
| `kg_synthesize.py` | NO net change for kdb-2 (LLM dispatcher already integrated by quick-260509-s29; flip CONFIG-EXEMPTIONS row to MODIFIED reflects historical change). If Q3 Option A: 2-line edit (line 20 import + line 106 arg) for embedding dispatcher | ALREADY in CONFIG-EXEMPTIONS — no extra approval if Q3 Option A; otherwise no change |
| `databricks-deploy/CONFIG-EXEMPTIONS.md` | Flip both kdb-1.5 NOT YET MODIFIED rows to MODIFIED — see commit; ADD `lib/embedding_complete.py` (if Q3 Option A) and `kb/services/synthesize.py` (if Q4 Option A) | NEW exemption rows require user approval |
| `databricks-deploy/requirements.txt` | Possibly extend with kb runtime deps if kdb-1.5 baseline incomplete (e.g., starlette, pydantic — likely already pulled by FastAPI; verify) | trivial maintenance |
| `tests/unit/test_llm_complete.py` | Extend with 4 new tests for `databricks_serving` branch | tests directory — not in scope policy |
| `kb/services/synthesize.py` | LLM-DBX-04 reason code + `_classify_serving_error` helper | NEW exemption row required |

### VERIFY-ONLY (kdb-2 imports, doesn't modify)

| Path | Why imported, not modified |
|------|----------------------------|
| `databricks-deploy/startup_adapter.py` | kdb-1.5-01 deliverable; kdb-2 wires into `app.yaml` `command:` |
| `databricks-deploy/lightrag_databricks_provider.py` | kdb-1.5-02 deliverable; kdb-2 imports via dispatcher branch |
| `kb/services/synthesize.py` | (If Q4 user does NOT approve modification) read-only verification |
| `kb/data/article_query.py` | Existing `?mode=ro` URI pattern works on Volume (kdb-1.5-RESEARCH Q4) |
| `kb/config.py` | `OMNIGRAPH_BASE_DIR` + `KB_DB_PATH` already split correctly |
| `lib/lightrag_embedding.py` | (If Q3 Option A) read-only — `lib/embedding_complete.py` wraps it |
| `databricks-deploy/CONFIG-EXEMPTIONS.md` | kdb-1.5 baseline exists; kdb-2 EXTENDS the ledger |
| `databricks-deploy/requirements.txt` | kdb-1.5 baseline exists; possibly extends |
| `databricks-deploy/pytest.ini` | kdb-1.5-02 deliverable; unchanged |

---

## Skill Picks per Plan

Per `feedback_skill_invocation_not_reference.md`, the planner MUST emit explicit `Skill(skill="...")` tool calls in the executor prompts (not just list these in `<read_first>`).

### kdb-2-01 (AUTH-DBX-01..05 + grant SQL)

- `databricks-patterns` — UC grant grammar (CATALOG/SCHEMA/VOLUME), `serving-endpoints get-permissions` shape, App SP client_id discovery from `databricks apps get`.
- `security-review` — least-privilege audit (READ_VOLUME only, NOT WRITE_VOLUME; no `valueFrom:` for LLM auth).

### kdb-2-02 (LLM-DBX-01: dispatcher branch + tests)

- `python-patterns` — pure-Python pattern; lazy import; `_VALID` tuple extension; module-test isolation.
- `writing-tests` — Testing Trophy says these are unit tests (monkeypatched env, mocked SDK); 4 new tests extending the existing 5-test `test_llm_complete.py`.

### kdb-2-03 (LLM-DBX-02 + LLM-DBX-04: integration tests + reason code + (conditional) embedding dispatcher)

- `python-patterns` — `_classify_serving_error` helper design; `Literal` enum extension.
- `writing-tests` — integration tests with mocked factory (real LightRAG init takes too long for unit-test cycle; mock the make_llm_func to return a sentinel that raises 503 on call).

### kdb-2-04 (DEPLOY-DBX + OPS-DBX: deploy + smoke + Makefile + app.yaml)

- `databricks-patterns` — app.yaml schema (sequence form vs string), `--source-code-path` semantics, `MSYS_NO_PATHCONV=1` Windows note.
- `search-first` — verify CLI subcommands (`apps stop`, `apps logs`) before assuming they exist; Apps Cookbook patterns; SDK v0.260+ shape drift.

---

## Recommended plan structure (sketch for planner)

| Plan | Wave | Scope | Confidence |
|------|------|-------|------------|
| **kdb-2-01** | Wave 0 | AUTH-DBX-01..05 grants + Q4 + Q3 user-approval requests + Q1 verification | HIGH (well-scoped) |
| **kdb-2-02** | Wave 1 | LLM-DBX-01 (lib/llm_complete.py dispatcher branch + 4 unit tests). Independent of kdb-2-03/04. | HIGH |
| **kdb-2-03** | Wave 1 | LLM-DBX-02 + LLM-DBX-04 (integration test for dispatcher path; reason code; (conditional) lib/embedding_complete.py mirror). Depends on kdb-2-02 dispatcher branch landing first; can fan-out from there. | MEDIUM (depends on user decisions from kdb-2-01) |
| **kdb-2-04** | Wave 2 | DEPLOY-DBX-01..09 + LLM-DBX-05 + OPS-DBX-01/02 (app.yaml + Makefile + first deploy + Smoke 1+2 manual UAT). Sequential after Wave 1. | MEDIUM (Q7 source-code-path layout uncertainty + Q5 smoke methodology require Wave 0 minimal-deploy validation) |

**Wave 0 micro-step**: kdb-2-04 plan should include a Step 0 "minimal-deploy validation" that deploys the App with a no-op `command:` (just verifies path/sys.path layout) BEFORE doing the real deploy — surfaces Q7 layout risk cheaply.

---

## Open Questions / Risks Flagged for Execute or kdb-3

1. **Real cold-start size post-kdb-2.5** (Volume populated): measured during kdb-3 first deploy after re-index. Adapter logs `bytes_copied + elapsed_s` for analysis.
2. **`databricks apps stop` CLI subcommand existence in v0.260+**: verify in execute via `databricks --profile dev apps stop --help`. If missing, fall back to `databricks apps delete` (destructive) and document in RUNBOOK.
3. **In-workspace classic-cluster notebook proxy** (Smoke 1+2 automation candidate): test in kdb-2-04 Step 0; if it works, partial automation possible. If not, accept full manual UAT.
4. **Q3 embedding-side resolution** (Options A/B/C/D): user must decide before kdb-2-03 plan executes. Default-recommend Option A (dispatcher mirror); if user wants smaller blast radius, Option C (kg_synthesize.py 5-line gate within existing exemption).
5. **Q4 CONFIG-EXEMPTIONS extension to `kb/services/synthesize.py`**: user must approve before kdb-2-03 plan modifies that file. If user rejects, fall back to wrapping in `databricks-deploy/lightrag_databricks_provider.py` (Option B in Q4 table).
6. **Q7 `--source-code-path` + PYTHONPATH layout**: verify in kdb-2-04 Step 0 minimal deploy.
7. **Q1(c) AUTH-DBX-04 CLI grammar**: verify in kdb-2-01 against actual Foundation Model endpoint names in v0.260+; fall through to Path B in-app probe if Path A CLI fails.
8. **Workspace UI proxy works for omnigraph-kb specifically**: verify in kdb-2-04 first deploy (user browser session).
9. **Hyphen-in-package-name** (`databricks-deploy`): the dispatcher branch + `app.yaml` `command:` `cd /app/databricks-deploy && PYTHONPATH=...` pattern is the best workaround. If kdb-2-04 Step 0 reveals issues, alternate path is renaming to `databricks_deploy/` (would break kdb-1.5 frozen contract — REJECTED) or creating an `__init__.py` ad-hoc shim — keep simple.

---

## Sources

### Primary (HIGH confidence)

- `lib/llm_complete.py` (full file, 48 lines, read in research)
- `kg_synthesize.py` (full file, 200 lines, read in research; line 19 + 106 already use dispatcher)
- `kb/services/synthesize.py` (full file, 470 lines, read in research; lines 145, 189-214, 392-470)
- `databricks-deploy/startup_adapter.py` (full file, 133 lines, read in research; kdb-1.5 deliverable)
- `databricks-deploy/lightrag_databricks_provider.py` (full file, 148 lines, read in research; kdb-1.5 deliverable)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (29 lines; kdb-1.5 baseline)
- `databricks-deploy/requirements.txt` (kdb-1.5 baseline; 13 lines)
- `databricks-deploy/pytest.ini` (kdb-1.5 baseline)
- `databricks-deploy/tests/test_startup_adapter.py` + `databricks-deploy/tests/test_provider_dryrun.py` (9/9 tests green; verified by kdb-1.5-VERIFICATION.md)
- `tests/unit/test_llm_complete.py` (60 lines; 5 existing tests; pattern for LLM-DBX-01 extension)
- `lib/lightrag_embedding.py` (lines 1-60; reveals dim=3072 Vertex/Gemini path that conflicts with Qwen3 dim=1024 — Q3 risk)
- `lib/models.py` (`EMBEDDING_DIM = 3072` for Vertex/Gemini)
- `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md` (full file)
- `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-01-SUMMARY.md` + `kdb-1.5-02-SUMMARY.md` + `kdb-1.5-VERIFICATION.md`
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md` (Model Serving + grant capability evidence)
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-WAVE2-FINDINGS.md` (Volume populated; lightrag_storage/ INTENTIONALLY EMPTY)
- `.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-SPIKE-FINDINGS.md` (Private Link blocker; CLI v0.260.0 limits; `MSYS_NO_PATHCONV=1` requirement)
- `.planning/PROJECT-kb-databricks-v1.md` + `REQUIREMENTS-kb-databricks-v1.md` rev 3 + `ROADMAP-kb-databricks-v1.md` rev 3 + `STATE-kb-databricks-v1.md` rev 3
- Repo grep: `get_llm_func|llm_complete|deepseek_model_complete|vertex_gemini_model_complete` finds 13 files using the dispatcher pattern across the codebase.
- `.planning/research/kb-databricks-v1/STACK.md` (canonical app.yaml schema from MS Learn; CLI v0.260.0 sub-help)

### Secondary (MEDIUM confidence)

- Apps `command:` `bash -c` shape — inferred from STACK.md verbatim Streamlit + Flask examples + sequence form documentation; not directly tested with multi-step
- Workspace UI Apps tab as Smoke 1+2 verification path — kdb-1 SPIKE-FINDINGS confirms direct browser fails; UI proxy not directly tested for omnigraph-kb
- `databricks apps stop` CLI subcommand existence — TBD in execute phase
- `databricks serving-endpoints get-permissions` CLI shape — kdb-1 SPIKE punted; verifiable in v0.260+

### Tertiary (LOW confidence)

- Exact `PYTHONPATH` layout under `--source-code-path /Workspace/.../omnigraph-kb/databricks-deploy` — TBD in kdb-2-04 Step 0
- In-workspace classic-cluster notebook proxy reachability — TBD; documented as best-effort

## Metadata

**Confidence breakdown:**

- Standard stack (Apps + UC + MosaicAI + Python): HIGH — kdb-1.5 dry-run already exercised against REAL Model Serving endpoints
- Architecture (dispatcher + adapter + manual UAT): HIGH on dispatcher (Q2/Q3 source-traced); MEDIUM on adapter wire-in (Q7 layout uncertainty); MEDIUM on UAT (Q5 Private Link constraint)
- Pitfalls: HIGH — kdb-1.5-RESEARCH covered the deep technical pitfalls; kdb-1 SPIKE-FINDINGS covered the deploy/CLI pitfalls
- Q1: HIGH on (a) (b); MEDIUM on (c)
- Q2: HIGH (file fully read; pattern confirmed)
- Q3: HIGH on the existing-dispatcher-already-done finding (file 100% read; grep verified across 13 files); MEDIUM on the embedding-side recommendation (4 options; user decides)
- Q4: HIGH on the implementation shape; MEDIUM on the user-approval cycle for `kb/services/synthesize.py` exemption
- Q5: HIGH on the Private Link constraint; MEDIUM on the workspace UI proxy recommendation
- Q6: HIGH (kdb-1 SPIKE measured; kdb-1.5 adapter empty-source tested)
- Q7: MEDIUM — `bash -c` is the cleanest option but `--source-code-path` layout has real uncertainty
- Q8: HIGH on most recipes; MEDIUM on `make stop`

**Research date:** 2026-05-16

**Valid until:** 2026-06-16 (30 days for stable; both kdb-1.5 deliverables are frozen and tested; Databricks SDK + Apps runtime have no announced breaking changes; Private Link policy is workspace-level and unlikely to change)
