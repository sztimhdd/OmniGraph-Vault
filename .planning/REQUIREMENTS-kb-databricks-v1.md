# Requirements — kb-databricks-v1 (rev 3)

> Parallel-track milestone. Sibling: REQUIREMENTS-KB-v2.md, REQUIREMENTS-Agentic-RAG-v1.md, REQUIREMENTS-v3.5-Ingest-Refactor.md. Main `REQUIREMENTS.md` is owned by v3.4 / v3.5 main track and is **untouched** by this milestone.
>
> Per `feedback_parallel_track_gates_manual_run.md`: gsd-tools.cjs init does NOT recognize suffix files; orchestrator hand-drives every gate.
>
> **rev 3 strategic constraints (user-locked 2026-05-15):**
> 1. ALL LLM calls (synthesis + entity extraction + embedding) route through MosaicAI Model Serving. DeepSeek fully retired in v1.
> 2. Hermes runtime fully separated — Databricks deploy is self-contained, no ongoing dependency on Hermes resources after the one-shot seed.
> 3. Synthesis model: `databricks-claude-sonnet-4-6` (locked).
> 4. Embedding model: `databricks-qwen3-embedding-0-6b` (locked — bilingual zh/en corpus).
> 5. "Zero `kb/` source-tree edits" hard rule **relaxed** — `lib/llm_complete.py` (add `databricks_serving` provider branch) and `kg_synthesize.py` (route through dispatcher) ARE editable in this milestone. All other `kb/` paths still locked. Exemptions tracked in `databricks-deploy/CONFIG-EXEMPTIONS.md`.

## v1 Requirements

Requirements grouped by category. REQ-ID format: `[CATEGORY]-NN`. Continuation of KB-v2's `STORAGE/AUTH/...` namespace is intentional — these are NEW requirements unique to the Databricks deploy target, NOT a re-statement of KB-v2.

### STORAGE-DBX — UC Volume + data layout

- [ ] **STORAGE-DBX-01**: UC schema `mdlg_ai_shared.kb_v2` exists in workspace, owned by `hhu@edc.ca`
- [ ] **STORAGE-DBX-02**: UC managed volume `omnigraph_vault` created under `mdlg_ai_shared.kb_v2`
- [ ] **STORAGE-DBX-03**: Volume layout populated with 4 sub-directories: `/data`, `/images`, `/lightrag_storage`, `/output` (initial empty markers OK)
- [ ] **STORAGE-DBX-04**: `data/kol_scan.db` present on Volume from one-shot user upload (per SEED-DBX-01), with WAL pre-checkpointed and `-wal`/`-shm` sidecars stripped. **Post-upload integrity check:** open the on-Volume DB read-only, query 1 known article by `content_hash` (e.g., a recent RSS article), confirm row exists with `LENGTH(body) > 0` and `content_hash` matches the source-side value byte-for-byte (proves no truncation / no encoding drift during transfer)
- [ ] **STORAGE-DBX-05**: Volume content readable from App container at path `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` (FUSE mount confirmed) OR via `databricks-sdk` Files API with documented fallback adapter

### AUTH-DBX — App service principal grants

- [ ] **AUTH-DBX-01**: App service principal `app-omnigraph-kb` has `USE CATALOG` on `mdlg_ai_shared`
- [ ] **AUTH-DBX-02**: App SP has `USE SCHEMA` on `mdlg_ai_shared.kb_v2`
- [ ] **AUTH-DBX-03**: App SP has `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` (no `WRITE VOLUME` in v1)
- [ ] **AUTH-DBX-04**: App SP has **`CAN QUERY`** on Model Serving endpoints `databricks-claude-sonnet-4-6` AND `databricks-qwen3-embedding-0-6b`. Verification: `databricks serving-endpoints get-permissions <endpoint>` shows `app-omnigraph-kb` with QUERY permission. Exact permission grammar (CAN_QUERY vs alternative grant model) confirmed during PREFLIGHT-DBX-02 spike.
- [ ] **AUTH-DBX-05**: App access gated by Databricks workspace SSO (Apps default; no anonymous access)

### LLM-DBX — MosaicAI Model Serving + provider config

> Five REQs covering: (1) provider dispatcher add, (2) `kg_synthesize.py` route-through, (3) LightRAG provider adapter file, (4) graceful degradation on Model Serving error, (5) env vars in `app.yaml`. **LLM-DBX-02 is the one REQ that requires `kb/`-source code modification** — explicitly approved per rev 3 constraint #5; tracked in `databricks-deploy/CONFIG-EXEMPTIONS.md`.

- [ ] **LLM-DBX-01**: `lib/llm_complete.py` adds `databricks_serving` provider branch alongside existing `deepseek` / `vertex_gemini`. Implementation: `from databricks.sdk import WorkspaceClient` + `w.serving_endpoints.query(name=os.environ["KB_LLM_MODEL"], messages=[ChatMessage(role=ChatMessageRole.USER, content=...)])`. Returns string content compatible with the existing dispatcher contract. Verification: `pytest tests/unit/test_llm_complete.py::test_databricks_serving_provider` PASS, including a mocked endpoint response and an error-path test that surfaces 503/429/timeout to caller.
- [ ] **LLM-DBX-02**: `kg_synthesize.synthesize_response(query_text, mode="hybrid")` re-routes its LLM call from hardcoded `deepseek_model_complete` to the dispatcher in `lib/llm_complete.py`. **C1 contract preserved** — function signature unchanged, return type unchanged. Only internal LLM call path changes. **This is the rev 3 `kb/`-source modification expressly authorized by user constraint #5.** Diff scope MUST be limited to: `kg_synthesize.py` swap one import + one call site. Anything broader = scope creep, blocks PR. Verification: existing kg_synthesize tests still pass; new test confirms dispatcher path executes when `OMNIGRAPH_LLM_PROVIDER=databricks_serving` is set.
- [ ] **LLM-DBX-03**: `databricks-deploy/lightrag_databricks_provider.py` (new file, NOT under `kb/`) provides two factory functions consumed by LightRAG instantiation:
  - `make_llm_func()` returns a callable matching LightRAG's `llm_model_func` signature, internally calling `WorkspaceClient().serving_endpoints.query(name=KB_LLM_MODEL, ...)`
  - `make_embedding_func()` returns an `EmbeddingFunc` matching LightRAG's expected interface, internally calling `WorkspaceClient().serving_endpoints.query(name=KB_EMBEDDING_MODEL, ...)`; embedding dim is `1024` (Qwen3-0.6B output dim)
  - Both factories close over `WorkspaceClient` instance + endpoint names from env vars; constructed once at App startup
  - Verification: standalone unit test instantiates LightRAG with these factories against mocked Model Serving responses, confirms `ainsert(small_doc)` + `aquery("test")` round-trips without raising
- [ ] **LLM-DBX-04**: Model Serving error path = graceful degrade (NEVER 500/502 from `/synthesize`). Reuses kb-v2.1-1 `KG_MODE_AVAILABLE` pattern: 503 / 429 / timeout / connection-error from Model Serving sets `kg_unavailable=true`, returns FTS5 fallback markdown + `confidence: "fts5_fallback"` + reason code `kg_serving_unavailable` (new code added to existing 3-code enum). One-shot WARNING log line, no endpoint name leak, no error stack to user.
- [ ] **LLM-DBX-05**: `app.yaml` `env:` list contains 3 literal values (NOT `valueFrom:`):
  - `OMNIGRAPH_LLM_PROVIDER=databricks_serving`
  - `KB_LLM_MODEL=databricks-claude-sonnet-4-6`
  - `KB_EMBEDDING_MODEL=databricks-qwen3-embedding-0-6b`

### DEPLOY-DBX — App create + app.yaml + first deploy

- [ ] **DEPLOY-DBX-01**: App `omnigraph-kb` created via `databricks apps create omnigraph-kb`
- [ ] **DEPLOY-DBX-02**: `app.yaml` lives at root of `--source-code-path` (NOT in nested subdirectory)
- [ ] **DEPLOY-DBX-03**: `app.yaml` `command:` invokes uvicorn with `--port $DATABRICKS_APP_PORT` substitution (NOT hardcoded `:8766`)
- [ ] **DEPLOY-DBX-04**: `app.yaml` `env:` list sets `OMNIGRAPH_BASE_DIR` (literal `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` OR `/tmp` if adapter pattern) PLUS the 3 LLM-DBX-05 literal env vars (`OMNIGRAPH_LLM_PROVIDER`, `KB_LLM_MODEL`, `KB_EMBEDDING_MODEL`). **No DeepSeek key, no `valueFrom:` for any LLM-related env** — Apps SP auto-injection (DATABRICKS_CLIENT_ID/SECRET/HOST) carries Model Serving auth.
- [ ] **DEPLOY-DBX-05**: First `databricks apps deploy omnigraph-kb` reaches `RUNNING` state within 20 min default timeout
- [ ] **DEPLOY-DBX-06**: App URL returns 200 on `/` after workspace SSO
- [ ] **DEPLOY-DBX-07**: `databricks-deploy/requirements.txt` exists and pins the `kb/` runtime deps the App needs (FastAPI, uvicorn, jinja2, markdown, pygments, lightrag, `databricks-sdk`). **Removed deps:** any DeepSeek client / SDK pieces — DeepSeek is fully retired in v1. Apps runtime auto-installs from this file; missing deps = cold-start fails.
- [ ] **DEPLOY-DBX-08**: `app.yaml` `env:` list explicitly sets `OMNIGRAPH_LLM_PROVIDER=databricks_serving` (literal `value:`, not `valueFrom:`). Defends against any code path that would otherwise default to DeepSeek or Vertex Gemini and try outbound calls to non-Databricks endpoints. Locking the provider here makes the LLM egress surface deterministic = Databricks Model Serving only (in-workspace, no external HTTPS).
- [ ] **DEPLOY-DBX-09**: `app.yaml` `env:` list **deliberately does NOT set** `KB_KG_GCP_SA_KEY_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`. Rationale: rev 3 constraint #1 retires Vertex Gemini path entirely; KG mode now flows through `databricks_serving` provider not GCP SA. Leaving these unset prevents accidental Vertex code path activation. Verification: `grep -E "KB_KG_GCP_SA_KEY_PATH|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml` returns empty.

### SEED-DBX — One-shot seed + re-index

> Replaces ongoing Hermes sync (rev 2.2 SYNC-DBX, now retired). Runtime Databricks is self-contained per constraint #2 — Hermes touchpoint exists ONLY during initial seed.

- [ ] **SEED-DBX-01**: User one-time uploads `data/kol_scan.db` (WAL-checkpointed, sidecar-stripped) and `~/.hermes/omonigraph-vault/images/` to UC Volume:
  - `dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db`
  - `dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/{hash}/...`
  
  Mechanism: user-side notebook + Databricks Connect / Files API. **Hermes-side tools NOT required and NOT used** — user pulls Hermes snapshot via existing scp/rsync, then runs upload from local dev box. This is the **only** Hermes touchpoint in the entire milestone; runtime is fully independent.
- [ ] **SEED-DBX-02** ⭐ — Re-index LightRAG storage (executed during NEW phase **kdb-2.5**, runs as a Databricks **Job** not in-App):
  - Job reads `/Volumes/.../data/kol_scan.db` and iterates over both `articles` (KOL, ~600) and `rss_articles` (~1400) tables
  - For each row: `lightrag.ainsert(content)` using the LightRAG instance constructed from `databricks-deploy/lightrag_databricks_provider.py` factories (LLM-DBX-03)
  - Entity extraction = `databricks-claude-sonnet-4-6`; embeddings = `databricks-qwen3-embedding-0-6b` (1024-dim)
  - Output written to `/Volumes/.../lightrag_storage/` (graphml + nano-vector-db JSON)
  - **Resilience:** single-article LightRAG failure → log + skip + continue (NOT fail-fast). Tracked in Job log; failed `content_hash`-list emitted as `kdb-2.5-FAILURES.csv` for selective retry
  - **Estimated time + cost:** 8–30 hours wallclock (sensitive to Model Serving concurrency + LightRAG `ainsert` batch tuning), $20–100 Model Serving cost. Risk #2 covers this; mitigation = small-batch validation first (50 articles → measure → extrapolate before full run).
- [ ] **SEED-DBX-03**: Re-index post-check sanity:
  - Read 5–10 random entities from on-Volume LightRAG storage; verify each entity vector has dim 1024 (Qwen3-0.6B output dim)
  - Verify entity name distribution covers both Chinese and English (e.g., grep entity names for at least 10 zh-CN + 10 en strings)
  - Run 1 KG-mode query end-to-end: `lightrag.aquery("LangGraph 与 CrewAI 的对比", mode="hybrid")` → returns non-empty Chinese-language response that cites a Chinese article from the corpus
  - Run 1 KG-mode query in English: same but `"compare LangGraph and CrewAI"` → English response citing English articles
  - All checks evidenced in `kdb-2.5-VERIFICATION.md` with raw output excerpts

### QA-DBX — /synthesize round-trip with MosaicAI

- [ ] **QA-DBX-01**: `POST /synthesize {query}` returns `202 + job_id`, polling endpoint returns markdown answer (KB-v2 D-19 contract preserved across deploy targets)
- [ ] **QA-DBX-02**: Underlying call to `kg_synthesize.synthesize_response()` succeeds (KB-v2 C1 contract preserved per LLM-DBX-02 dispatcher routing); LLM call routes to MosaicAI Model Serving endpoint `databricks-claude-sonnet-4-6` (verified via Apps Logs tab — log line shows endpoint name + HTTP 200 + latency < 5s for typical queries). Auth flows via Apps SP injection (no API key, no `valueFrom:` for LLM access).
- [ ] **QA-DBX-03**: Negative-path: `/synthesize` returns FTS5-fallback markdown (NEVER 500/502) for ALL 4 reason codes (3 from kb-v2.1-1 + 1 added in LLM-DBX-04):
  1. **`kg_disabled`** — explicit feature flag off (env-driven). Verify by setting kg-disable env var and POSTing `/synthesize`
  2. **`kg_credentials_missing`** — Vertex GCP creds env vars not set (the v1 default state per DEPLOY-DBX-09). Largely a no-op path now since v1 doesn't use Vertex; verify it still degrades cleanly
  3. **`kg_credentials_unreadable`** — env var points to non-existent / non-readable file
  4. **`kg_serving_unavailable`** (NEW per LLM-DBX-04) — Model Serving endpoint returns 503 / 429 / timeout / connection error. Verify by temporarily setting `KB_LLM_MODEL` to a non-existent endpoint name and POSTing `/synthesize`
  
  All four must return `confidence: "fts5_fallback"` markdown response, HTTP 200, and a one-shot WARNING log line with the reason code (no path leak, no endpoint name leak per kb-v2.1-1 hardening).

### CONFIG-DBX — Allowed source-tree changes invariant

- [ ] **CONFIG-DBX-01**: Source-tree changes scoped per **rev 3 constraint #5 relaxation**. Allowed `kb/`-relative edits in this milestone: `lib/llm_complete.py` (LLM-DBX-01 provider branch add) AND `kg_synthesize.py` (LLM-DBX-02 dispatcher route-through). Any other path under `kb/`, `lib/`, top-level `*.py` requires explicit user approval before edit.
  
  Verification command (run at kdb-3 close):
  ```bash
  git log <milestone-base>..HEAD --grep '(kdb-' --name-only -- \
    kb/ \
    lib/ \
    | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' \
    | sort -u
  ```
  Returns empty. The exemption list (`lib/llm_complete.py`, `kg_synthesize.py`) lives in `databricks-deploy/CONFIG-EXEMPTIONS.md` for audit traceability. `<milestone-base>` is the locked commit hash recorded in `STATE-kb-databricks-v1.md` (rev 3 forward commit).
- [ ] **CONFIG-DBX-02**: All Databricks-target NEW config + adapter code lives in `databricks-deploy/` directory at repo root: `app.yaml`, `databricks.yml` (if bundle used), `Makefile` recipes, `requirements.txt`, `lightrag_databricks_provider.py`, `CONFIG-EXEMPTIONS.md`, runbook docs. **No new files added under `kb/` or `lib/`** — only the two specifically-listed exemption files are *modified*; no new `kb/...` or `lib/...` files are *created* by this milestone.

### PREFLIGHT-DBX — kdb-1 early-warning gates (BEFORE building anything)

These two run on a **workspace-side serverless notebook or test-app** during kdb-1, NOT inside the production `omnigraph-kb` App. Purpose: surface the two highest-risk milestone blockers (Model Serving access + grant capability) early enough to escalate without losing kdb-2 timeline.

- [ ] **PREFLIGHT-DBX-01**: From a workspace serverless cluster (or scratch test-app), run a Python script:
  ```python
  from databricks.sdk import WorkspaceClient
  from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
  w = WorkspaceClient()
  resp = w.serving_endpoints.query(
      name="databricks-claude-sonnet-4-6",
      messages=[ChatMessage(role=ChatMessageRole.USER, content="hello")],
  )
  ```
  Pass = HTTP 200 with valid response body (`resp.choices[0].message.content` non-empty). Fail = ANY non-200, timeout, missing endpoint, or auth failure → escalate (likely SP grant gap, not network) BEFORE kdb-2 starts. Same probe repeated against `databricks-qwen3-embedding-0-6b`. Mitigation list (request CAN_QUERY grant, alternative endpoint name) documented in `kdb-1-PREFLIGHT-FINDINGS.md`.
- [ ] **PREFLIGHT-DBX-02**: User attempts a test grant on a throwaway target — e.g. `GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO 'test-principal'` (substitute a real test SP / user identity) — proves user has workspace-admin (or scope-admin) capability needed for kdb-2 AUTH-DBX-01..04. Fail → escalate to workspace admin BEFORE kdb-2 starts. Result documented in `kdb-1-PREFLIGHT-FINDINGS.md`.

### SPIKE-DBX — kdb-1 viability gate (5 sub-items)

These run from **inside a deployed test-app on Databricks Apps runtime** (NOT from a notebook — the runtime semantics differ). 30-min hard timer total. Any sub-item answering INCONCLUSIVE at the 30-min mark counts as ❌ for purposes of kdb-1.5 trigger (don't burn more time investigating; default to adapter pattern).

- [ ] **SPIKE-DBX-01a** — FUSE mount check: from a running test-app, `os.path.ismount("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault")` AND `os.listdir("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault")` returns the 4 sub-directories. Pass = both succeed; fail = either raises or returns empty
- [ ] **SPIKE-DBX-01b** — `os.makedirs(exist_ok=True)` check: from the test-app, run `os.makedirs("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage", exist_ok=True)` against the existing dir with App SP holding `READ VOLUME` only (no WRITE). Pass = no raise; fail = `OSError [Errno 30]` or similar
- [ ] **SPIKE-DBX-01c** — SQLite WAL-mode open from `/Volumes/...`: open `kol_scan.db` (post-checkpoint snapshot) read-only via `sqlite3.connect("file:/Volumes/.../kol_scan.db?mode=ro", uri=True)` and run `SELECT count(*) FROM articles`. Pass = count > 0 with no error; fail = "unable to open database file" / "database is locked" / WAL-related error
- [ ] **SPIKE-DBX-01d** — App cold-start time with full LightRAG state: time from `databricks apps start omnigraph-kb-spike` to first 200 response on `/health`. Pass = < 60s; fail = ≥ 60s (suggests `/Volumes/...` LightRAG load is too slow → adapter pattern)
- [ ] **SPIKE-DBX-01e** — In-App Model Serving call (complementing PREFLIGHT-DBX-01): from inside the test-app process, call `WorkspaceClient().serving_endpoints.query(name="databricks-claude-sonnet-4-6", messages=[...])` AND embedding endpoint. Pass = both HTTP 200 with valid response; fail = any non-200. Distinct from PREFLIGHT-01 because Apps runtime networking + SP injection may differ from a serverless cluster.

All 5 results committed to `kdb-1-SPIKE-FINDINGS.md` with raw evidence (log excerpts / curl outputs / timing measurements). Decision rule:

- **All 5 ✅** → proceed to kdb-2
- **Any ❌ or INCONCLUSIVE-at-30-min** → insert kdb-1.5 (LightRAG-Databricks provider adapter pattern OR copy-to-/tmp adapter, depending on which sub-checks failed)
- **PREFLIGHT-01 ❌** → milestone blocked pending escalation; do NOT proceed to spike or kdb-2 until resolved
- **PREFLIGHT-02 ❌** → milestone blocked pending workspace-admin grant; spike can still proceed (uses an existing volume), but kdb-2 cannot start

### OPS-DBX — smoke tests + sign-off

OPS-DBX-01..03 verbatim mirror **`PROJECT-KB-v2.md` "Smoke Test (acceptance criterion)"** Smoke 1/2/3. The KB module is identical between Aliyun (KB-v2 / kb-4) and Databricks (kb-databricks-v1) deploy targets — same user-flow tests must pass against both. Databricks-specific deploy mechanics (URL serves, SSO, port binding) are covered by DEPLOY-DBX-05/06 + AUTH-DBX-05; OPS-DBX layer verifies user-visible KB behavior.

- [ ] **OPS-DBX-01** — KB-v2 Smoke 1 (双语 UI 切换) verbatim:
  1. 浏览器 `Accept-Language: zh-CN` 访问首页 → 默认中文 UI
  2. 点击右上角语言切换 → 英文 UI 全站生效(nav / labels / buttons / footer 全英文)
  3. 刷新页面 → 偏好通过 cookie 持久化,仍英文 UI
  4. 访问 `/?lang=zh` → 硬切回中文,cookie 同步更新

- [ ] **OPS-DBX-02** — KB-v2 Smoke 2 (双语搜索 + 详情页) verbatim:
  1. 中文 UI 输入"AI Agent 框架" → 返回 ≥ 3 条中文文章命中
  2. 英文 UI 输入"langchain framework" → 返回 ≥ 3 条英文文章命中
  3. 点击任一英文文章 → 详情页 `<html lang="en">` + 标"English" badge + 内容原文(英文)
  4. 点击任一中文文章 → 详情页 `<html lang="zh-CN">` + 标"中文" badge + 内容原文(中文)
  5. 详情页底部 og:image / og:title metadata 正确(分享到 IM 群里有预览)
  6. **(Databricks-specific add-on)** Detail-page images load successfully via `/static/img/...` route (i.e., FastAPI `StaticFiles` mount on UC Volume works, OR adapter-served images work if kdb-1.5 fired)

- [ ] **OPS-DBX-03** — KB-v2 Smoke 3 (RAG 问答双语 + 失败降级) verbatim:
  1. 中文输入"LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown 答复 + 来源链接(post kdb-2.5 re-index, KG-mode answers backed by sonnet-4-6 + Qwen3 entity index)
  2. 英文输入"What is the difference between LangGraph and CrewAI?" → 异步 → 英文 markdown 答复 + 来源链接
  3. 模拟 LightRAG 不可用(stop kg backend or block storage path) → /synthesize 降级返回 FTS5 top-3 摘要拼接 + `confidence: "fts5_fallback"` 标记,**不 500**
  4. **(Databricks-specific add-on)** Apps Logs tab confirms Model Serving call succeeded (HTTP 200 from endpoint `databricks-claude-sonnet-4-6`) AND embedding endpoint call succeeded (HTTP 200 from `databricks-qwen3-embedding-0-6b`); zero auth errors in cold start.

- [ ] **OPS-DBX-04**: kdb-3 verification report `VERIFICATION-kb-databricks-v1.md` cites all OPS smokes with evidence (screenshots, log excerpts, curl outputs)
- [ ] **OPS-DBX-05**: User-facing runbook `databricks-deploy/RUNBOOK.md` covers: first-time deploy, one-shot seed (SEED-DBX-01) + re-index Job (SEED-DBX-02 / kdb-2.5), App restart, Model Serving endpoint troubleshoot (CAN_QUERY missing, endpoint not found), troubleshoot common errors (PERMISSION_DENIED, FUSE mount missing, 503/429 from Model Serving). **No DeepSeek / external API content — fully Databricks-native ops.**

## Future Requirements (deferred)

Tracked for v2 / v2.x but explicitly NOT in scope for v1:

- **v2 — Synthesis model upgrade (LLM-UPGRADE-DBX-01..0N):** Evaluate `databricks-claude-opus-4-6` (or successor) for synthesis quality vs cost; potentially differentiate `entity-extraction` model from `synthesis` model
- **v2 — Per-user OBO auth (OBO-DBX-01..0N):** `X-Forwarded-Access-Token` for audit + private documents
- **v2 — Concurrent-write safety (CONC-DBX-01..0N):** atomic write_json upstream patch OR adapter pattern; needed only if App ever writes to Volume during runtime (not relevant for v1 read-only)
- **v3 — Ongoing ingest pipeline migration (INGEST-DBX-01..0N):** daily-ingest cron → Workflow + Jobs running entirely on Databricks; scrape providers + LLM providers re-evaluated for Apps-runtime compatibility. Distinct from kdb-2.5 SEED-DBX-02 (which is a one-shot v1 step, not an ongoing pipeline).
- **v3 — Hermes sunset:** only after v3 ingest pipeline ships and runs stable for ≥ 1 month

## Out of Scope (v1 — explicit exclusions with reasoning)

| Item | Why excluded |
|------|--------------|
| **SQLite → Delta migration** | SQLite is a file, not a table. Migrating = rewriting every SQL query in `kb/`, `omnigraph_search/`, `kg_synthesize.py`. Months of work. Tracked for v2+ only if a concrete pain point materializes. |
| **DeepSeek as fallback LLM** | Per rev 3 constraint #1, DeepSeek is fully retired in v1. No fallback. Model Serving error path = FTS5 (per LLM-DBX-04). |
| **Vertex Gemini path** | Same — retired by constraint #1. Existing Vertex code paths in `lib/` and `kg_synthesize.py` remain reachable via `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` env var, but v1 deploy explicitly locks `databricks_serving`. |
| **Public access / zero-login KB on Databricks** | Apps gates on workspace SSO. Public access happens on Aliyun deploy (KB-v2 / kb-4). |
| **Hermes-side any modifications** | Strengthened per rev 3 constraint #2: Hermes is **read-only source for one-shot seed** (SEED-DBX-01) and untouched otherwise. No Hermes cron / config / code edits in this milestone. |
| **Ongoing ingest pipeline on Databricks** | Daily ingest = scheduled work + LLM + scrape; separate v3 milestone. **kdb-2.5 SEED-DBX-02 is a one-shot v1 step, NOT an ongoing pipeline.** Don't confuse the two — the Job runs once, produces Volume artifacts, then is archived. |
| **Per-user OBO auth** | All v1 users see same KB; no row filtering. v2 if private documents added. |
| **Ingest-side LightRAG `ainsert()` to UC Volume after kdb-2.5** | One-shot re-index in kdb-2.5 IS the only ainsert in v1. Subsequent ingest = on Hermes, then user re-runs SEED-DBX-01 + SEED-DBX-02 if KB needs refresh. v3 covers automation. |
| **Apps horizontal scaling / multi-instance** | Single instance; LightRAG `write_json` is non-atomic (verified `lightrag/utils.py:1255`). |
| **Modifying `kb/` source tree beyond exemption list** | Hard rule **with explicit exemptions** for v1: `lib/llm_complete.py` + `kg_synthesize.py` ONLY. CONFIG-DBX-01 enforces. Any additional `kb/`-relative edit requires a separate user approval before merge. |

## Traceability (filled by ROADMAP)

| REQ-ID | Phase |
|--------|-------|
| STORAGE-DBX-01..04 | kdb-1 |
| STORAGE-DBX-05 | kdb-1 spike (verify) + conditional kdb-1.5 (fix) |
| AUTH-DBX-01..05 | kdb-2 |
| LLM-DBX-01 | kdb-2 (provider branch + tests) |
| LLM-DBX-02 | kdb-2 (kg_synthesize dispatcher swap; CONFIG-EXEMPTIONS update) |
| LLM-DBX-03 | kdb-1.5 (adapter spike + factory file) |
| LLM-DBX-04 | kdb-2 (graceful degrade integrated with LLM-DBX-01) |
| LLM-DBX-05 | kdb-2 (env vars in app.yaml) |
| DEPLOY-DBX-01..09 | kdb-2 |
| SEED-DBX-01 | kdb-1 (one-shot data + image upload) |
| SEED-DBX-02 | kdb-2.5 ⭐ (Databricks Job re-index) |
| SEED-DBX-03 | kdb-2.5 (post-check + verification) |
| QA-DBX-01..03 | kdb-3 |
| CONFIG-DBX-01..02 | kdb-3 (final audit including CONFIG-EXEMPTIONS.md verification) |
| PREFLIGHT-DBX-01..02 | kdb-1 (must complete BEFORE spike) |
| SPIKE-DBX-01a..01e | kdb-1 spike |
| OPS-DBX-01..02 | kdb-2 (post-RUNNING smoke; OPS-02 may show degraded RAG until kdb-2.5 closes) |
| OPS-DBX-03 | kdb-3 (full bilingual RAG round-trip after re-index) |
| OPS-DBX-04..05 | kdb-3 |

**Total REQ count rev 3:** 36 unique items across 10 categories (5 STORAGE + 5 AUTH + 5 LLM + 9 DEPLOY + 3 SEED + 3 QA + 2 CONFIG + 2 PREFLIGHT + 5 SPIKE-sub-items + 5 OPS = sums to 44 if counting SPIKE 5 sub-items individually; reporting 36 to match user delta math which counts the SPIKE group as 1 super-REQ for net-delta tracking — net change vs rev 2.2 = -9 SECRETS/SYNC/DeepSeek-PREFLIGHT + 8 LLM/SEED + 0 modifications = -1 net, 37 → 36).

## Last Updated

2026-05-15 (rev 3) — Strategic restructure per user constraints #1-#5: ALL LLM through MosaicAI Model Serving (DeepSeek fully retired); Hermes runtime-separated (SEED-DBX one-shot replaces ongoing SYNC); synthesis = `databricks-claude-sonnet-4-6`; embedding = `databricks-qwen3-embedding-0-6b`; "zero `kb/` edits" hard-rule **relaxed** to allow `lib/llm_complete.py` + `kg_synthesize.py` per CONFIG-EXEMPTIONS.md. Removed: SECRETS-DBX (entire category), SYNC-DBX (entire category), DeepSeek-flavored PREFLIGHT-01, "FM-DBX swap" future req (now in v1). Added: LLM-DBX category (5 items), SEED-DBX category (3 items), kdb-2.5 NEW phase. Modified: DEPLOY-DBX-04/07/08, QA-DBX-02/03, PREFLIGHT-DBX-01, AUTH-DBX-04, CONFIG-DBX-01/02, SPIKE-DBX-01e, OPS-DBX-03/05, STORAGE-DBX-04 (Hermes wording dropped). Phase shape: kdb-1 / kdb-1.5 / kdb-2 / **kdb-2.5 NEW** / kdb-3. T-shirt: S → M.

2026-05-15 (rev 2.2) — Absorbed kb-v2.1-1 KG MODE HARDENING (sibling-track commit `eff934f`).

2026-05-15 (rev 2.1) — Doc self-consistency cleanup (30→36 REQ count fixes; risks #2 #3 mitigations now reference PREFLIGHT-DBX-01/02 closure path).

2026-05-15 (rev 2) — User P0/P1/P2 adjustments: SPIKE split into 5 sub-items, new PREFLIGHT category, DEPLOY-07/08, OPS verbatim KB-v2 smokes, etc.

2026-05-15 (rev 1) — Initial REQs drafted in main session by orchestrator. 30 REQs across 9 categories.
