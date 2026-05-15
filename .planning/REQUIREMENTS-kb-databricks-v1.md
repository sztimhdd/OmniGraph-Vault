# Requirements — kb-databricks-v1

> Parallel-track milestone. Sibling: REQUIREMENTS-KB-v2.md, REQUIREMENTS-Agentic-RAG-v1.md, REQUIREMENTS-v3.5-Ingest-Refactor.md. Main `REQUIREMENTS.md` is owned by v3.4 / v3.5 main track and is **untouched** by this milestone.
>
> Per `feedback_parallel_track_gates_manual_run.md`: gsd-tools.cjs init does NOT recognize suffix files; orchestrator hand-drives every gate.

## v1 Requirements

Requirements grouped by category. REQ-ID format: `[CATEGORY]-NN`. Continuation of KB-v2's `STORAGE/AUTH/...` namespace is intentional — these are NEW requirements unique to the Databricks deploy target, NOT a re-statement of KB-v2.

### STORAGE — UC Volume + data layout

- [ ] **STORAGE-DBX-01**: UC schema `mdlg_ai_shared.kb_v2` exists in workspace, owned by `hhu@edc.ca`
- [ ] **STORAGE-DBX-02**: UC managed volume `omnigraph_vault` created under `mdlg_ai_shared.kb_v2`
- [ ] **STORAGE-DBX-03**: Volume layout populated with 4 sub-directories: `/data`, `/images`, `/lightrag_storage`, `/output` (initial empty markers OK)
- [ ] **STORAGE-DBX-04**: `data/kol_scan.db` synced to Volume from Hermes snapshot, with WAL pre-checkpointed and `-wal`/`-shm` sidecars stripped. **Post-sync integrity check:** open the on-Volume DB read-only, query 1 known article by `content_hash` (e.g., a recent RSS article), confirm row exists with `LENGTH(body) > 0` and `content_hash` matches the Hermes-side value byte-for-byte (proves no truncation / no encoding drift during transfer)
- [ ] **STORAGE-DBX-05**: Volume content readable from App container at path `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` (FUSE mount confirmed) OR via `databricks-sdk` Files API with documented fallback adapter

### AUTH — App service principal grants

- [ ] **AUTH-DBX-01**: App service principal `app-omnigraph-kb` has `USE CATALOG` on `mdlg_ai_shared`
- [ ] **AUTH-DBX-02**: App SP has `USE SCHEMA` on `mdlg_ai_shared.kb_v2`
- [ ] **AUTH-DBX-03**: App SP has `READ VOLUME` on `mdlg_ai_shared.kb_v2.omnigraph_vault` (no `WRITE VOLUME` in v1)
- [ ] **AUTH-DBX-04**: App SP has `READ` on workspace secret scope `omnigraph-kb`
- [ ] **AUTH-DBX-05**: App access gated by Databricks workspace SSO (Apps default; no anonymous access)

### SECRETS — DeepSeek API key injection

- [ ] **SECRETS-DBX-01**: Workspace secret scope `omnigraph-kb` exists (created via `databricks secrets create-scope`)
- [ ] **SECRETS-DBX-02**: Secret key `deepseek_api_key` populated in scope (via `databricks secrets put-secret`)
- [ ] **SECRETS-DBX-03**: App resource of type Secret added (binds `omnigraph-kb`/`deepseek_api_key` to a resource key)
- [ ] **SECRETS-DBX-04**: `app.yaml` resolves `DEEPSEEK_API_KEY` env var via `valueFrom: <resource-key>` (NOT `value:` literal)
- [ ] **SECRETS-DBX-05**: Audit `git log --all -p -- databricks-deploy/` shows zero literal `sk-...` token strings ever (full deploy directory, not just `app.yaml` — covers `Makefile`, `requirements.txt`, `RUNBOOK.md`, any future config). Also `git log --all -p` whole-repo grep filtered to commits authored after milestone-base hash returns clean

### DEPLOY — App create + app.yaml + first deploy

- [ ] **DEPLOY-DBX-01**: App `omnigraph-kb` created via `databricks apps create omnigraph-kb`
- [ ] **DEPLOY-DBX-02**: `app.yaml` lives at root of `--source-code-path` (NOT in nested subdirectory)
- [ ] **DEPLOY-DBX-03**: `app.yaml` `command:` invokes uvicorn with `--port $DATABRICKS_APP_PORT` substitution (NOT hardcoded `:8766`)
- [ ] **DEPLOY-DBX-04**: `app.yaml` `env:` list sets `OMNIGRAPH_BASE_DIR` (literal `/Volumes/.../omnigraph_vault` OR `/tmp` if adapter pattern) and `DEEPSEEK_API_KEY` (`valueFrom:`)
- [ ] **DEPLOY-DBX-05**: First `databricks apps deploy omnigraph-kb` reaches `RUNNING` state within 20 min default timeout
- [ ] **DEPLOY-DBX-06**: App URL returns 200 on `/` after workspace SSO
- [ ] **DEPLOY-DBX-07**: `databricks-deploy/requirements.txt` exists and pins the `kb/` runtime deps the App needs (FastAPI, uvicorn, jinja2, markdown, pygments, lightrag, deepseek SDK pieces, etc.). Apps runtime auto-installs from this file; missing deps = cold-start fails
- [ ] **DEPLOY-DBX-08**: `app.yaml` `env:` list explicitly sets `OMNIGRAPH_LLM_PROVIDER=deepseek` (literal `value:`, not `valueFrom:`). Defends against any code path that would otherwise default to `vertex_gemini` and try outbound calls to `*.googleapis.com` — those may be blocked by EDC corp egress rules from the workspace. Locking the provider here makes the LLM egress surface deterministic = `api.deepseek.com` only

### CONFIG — zero `kb/` code changes invariant

- [ ] **CONFIG-DBX-01**: `git diff <milestone-base>..HEAD -- kb/` returns empty across this milestone, where `<milestone-base>` is the locked commit hash recorded in `STATE-kb-databricks-v1.md` (commit `7df6e5b` — REQ + ROADMAP setup completion). Verification command (run at kdb-3 close): `git log --oneline 7df6e5b..HEAD --grep '(kdb-' --name-only -- kb/` returns empty
- [ ] **CONFIG-DBX-02**: All Databricks-target config lives in `databricks-deploy/` directory at repo root: `app.yaml`, `databricks.yml` (if bundle used), `Makefile` recipes, `requirements.txt`, runbook docs

### SYNC — Hermes → UC Volume manual flow

- [ ] **SYNC-DBX-01**: 5-step manual sync runbook documented in `databricks-deploy/RUNBOOK.md`: SSH snapshot from Hermes → WAL checkpoint → sidecar cleanup → `databricks fs cp -r --overwrite` → App restart
- [ ] **SYNC-DBX-02**: Initial snapshot executed once during kdb-1, articles + lightrag state visible in Volume after first sync
- [ ] **SYNC-DBX-03**: Runbook re-executed after a deliberate Hermes-side change (e.g., 1 new article ingested), new article appears in App after restart

### QA — /synthesize round-trip with DeepSeek

- [ ] **QA-DBX-01**: `POST /synthesize {query}` returns `202 + job_id`, polling endpoint returns markdown answer (KB-v2 D-19 contract preserved across deploy targets)
- [ ] **QA-DBX-02**: Underlying call to `kg_synthesize.synthesize_response()` succeeds (KB-v2 C1 contract preserved); LLM call routes to `api.deepseek.com` (verified via App log line)
- [ ] **QA-DBX-03**: Negative-path: simulate LightRAG storage absence → `/synthesize` returns FTS5-fallback markdown with `confidence: "fts5_fallback"`, NOT 500

### PREFLIGHT — kdb-1 early-warning gates (BEFORE building anything)

These two run on a **workspace-side serverless notebook or test-app** during kdb-1, NOT inside the production `omnigraph-kb` App. Purpose: surface the two highest-risk milestone blockers (network egress + grant capability) early enough to escalate without losing kdb-2 timeline.

- [ ] **PREFLIGHT-DBX-01**: From a workspace serverless cluster (or scratch test-app), run a Python script that POSTs to `https://api.deepseek.com/v1/chat/completions` with a tiny `hello` prompt. Pass = HTTP 200 with valid response body. Fail = ANY non-200, timeout, or DNS failure → escalate to EDC networking BEFORE kdb-2 starts. Mitigation list (corp HTTPS proxy, FM-DBX swap pulled into v1) documented in `kdb-1-PREFLIGHT-FINDINGS.md`
- [ ] **PREFLIGHT-DBX-02**: User attempts a test grant on a throwaway target — e.g. `GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO 'test-principal'` (substitute a real test SP / user identity) — proves user has workspace-admin (or scope-admin) capability needed for kdb-2 AUTH-DBX-01..04. Fail → escalate to workspace admin BEFORE kdb-2 starts. Result documented in `kdb-1-PREFLIGHT-FINDINGS.md`

### SPIKE — kdb-1 viability gate (5 sub-items)

These run from **inside a deployed test-app on Databricks Apps runtime** (NOT from a notebook — the runtime semantics differ). 30-min hard timer total. Any sub-item answering INCONCLUSIVE at the 30-min mark counts as ❌ for purposes of kdb-1.5 trigger (don't burn more time investigating; default to adapter pattern).

- [ ] **SPIKE-DBX-01a** — FUSE mount check: from a running test-app, `os.path.ismount("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault")` AND `os.listdir("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault")` returns the 4 sub-directories. Pass = both succeed; fail = either raises or returns empty
- [ ] **SPIKE-DBX-01b** — `os.makedirs(exist_ok=True)` check: from the test-app, run `os.makedirs("/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage", exist_ok=True)` against the existing dir with App SP holding `READ VOLUME` only (no WRITE). Pass = no raise; fail = `OSError [Errno 30]` or similar
- [ ] **SPIKE-DBX-01c** — SQLite WAL-mode open from `/Volumes/...`: open `kol_scan.db` (post-checkpoint snapshot) read-only via `sqlite3.connect("file:/Volumes/.../kol_scan.db?mode=ro", uri=True)` and run `SELECT count(*) FROM articles`. Pass = count > 0 with no error; fail = "unable to open database file" / "database is locked" / WAL-related error
- [ ] **SPIKE-DBX-01d** — App cold-start time with full LightRAG state: time from `databricks apps start omnigraph-kb-spike` to first 200 response on `/health`. Pass = < 60s; fail = ≥ 60s (suggests `/Volumes/...` LightRAG load is too slow → adapter pattern)
- [ ] **SPIKE-DBX-01e** — Apps→DeepSeek egress (in-App, complementing PREFLIGHT-DBX-01): from inside the test-app process, hit DeepSeek with the same minimal prompt. Pass = HTTP 200; fail = any non-200. Distinct from PREFLIGHT-01 because Apps runtime networking may differ from a serverless cluster

All 5 results committed to `kdb-1-SPIKE-FINDINGS.md` with raw evidence (log excerpts / curl outputs / timing measurements). Decision rule:
- **All 5 ✅** → proceed to kdb-2 (3-phase happy path)
- **Any ❌ or INCONCLUSIVE-at-30-min** → insert kdb-1.5 (LightRAG storage adapter)
- **PREFLIGHT-01 ❌** → milestone blocked pending escalation; do NOT proceed to spike or kdb-2 until resolved
- **PREFLIGHT-02 ❌** → milestone blocked pending workspace-admin grant; spike can still proceed (uses an existing volume), but kdb-2 cannot start

### OPS — smoke tests + sign-off

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
  1. 中文输入"LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown 答复 + 来源链接
  2. 英文输入"What is the difference between LangGraph and CrewAI?" → 异步 → 英文 markdown 答复 + 来源链接
  3. 模拟 LightRAG 不可用(stop kg backend or block storage path) → /synthesize 降级返回 FTS5 top-3 摘要拼接 + `confidence: "fts5_fallback"` 标记,**不 500**
  4. **(Databricks-specific add-on)** Apps Logs tab confirms DeepSeek call succeeded (HTTP 200 from `api.deepseek.com`); no `KeyError: 'DEEPSEEK_API_KEY'` and no 401

- [ ] **OPS-DBX-04**: kdb-3 verification report `VERIFICATION-kb-databricks-v1.md` cites all OPS smokes with evidence (screenshots, log excerpts, curl outputs)
- [ ] **OPS-DBX-05**: User-facing runbook `databricks-deploy/RUNBOOK.md` covers: first-time deploy, manual sync, App restart-after-sync, secret rotation, troubleshoot common errors (PERMISSION_DENIED, valueFrom typo, FUSE mount missing, DeepSeek egress blocked)

## Future Requirements (deferred)

Tracked for v2 / v2.x but explicitly NOT in scope for v1:

- **v2 — Foundation Model swap (FM-DBX-01..0N):** DeepSeek → `databricks-claude-sonnet-4-6` for both Q&A and ingest paths, single cutover, secret scope retired in favor of model-serving auth
- **v2 — Automated sync (SYNC-AUTO-DBX-01..0N):** Workflow / Job replacing manual `databricks fs cp`; design phase + Hermes-side push or workspace-side pull decided
- **v2 — Per-user OBO auth (OBO-DBX-01..0N):** `X-Forwarded-Access-Token` for audit + private documents
- **v2 — Concurrent-write safety (CONC-DBX-01..0N):** atomic write_json upstream patch OR adapter pattern; needed only if App ever writes to Volume
- **v3 — Ingest pipeline migration (INGEST-DBX-01..0N):** daily-ingest cron → Workflow + Jobs; scrape providers re-evaluated for Apps runtime constraints

## Out of Scope (v1 — explicit exclusions with reasoning)

| Item | Why excluded |
|------|--------------|
| **SQLite → Delta migration** | SQLite is a file, not a table. Migrating = rewriting every SQL query in `kb/`, `omnigraph_search/`, `kg_synthesize.py`. Months of work. Tracked for v2+ only if a concrete pain point materializes. |
| **Foundation Model `databricks-claude-sonnet-4-6` swap** | Bundled with ingest-LLM swap in v2 — both Q&A and ingest LLMs cut over together for consistency. |
| **Public access / zero-login KB on Databricks** | Apps gates on workspace SSO. Public access happens on Aliyun deploy (KB-v2 / kb-4). |
| **Hermes sunset** | Ingest pipeline stays on Hermes; Hermes remains upstream writer. |
| **Ingest pipeline on Databricks** | Daily ingest = scheduled work + LLM + scrape; Apps cannot run scheduled scripts (would need Workflows + Jobs). Big lift, separate milestone. |
| **Per-user OBO auth** | All v1 users see same KB; no row filtering. v2 if private documents added. |
| **Ingest-side LightRAG `ainsert()` to UC Volume** | Requires Hermes to mount UC Volume (auth + driver). v1 keeps ainsert on Hermes local fs, then user `databricks fs cp` snapshot up. |
| **Apps horizontal scaling / multi-instance** | Single instance; LightRAG `write_json` is non-atomic (verified `lightrag/utils.py:1255`). |
| **Modifying `kb/` source tree** | v1 hard-rule: zero `kb/` edits. Delivered purely via env-var + deploy config. CONFIG-DBX-01 enforces. |

## Traceability (filled by ROADMAP)

| REQ-ID | Phase |
|--------|-------|
| STORAGE-DBX-01..04 | kdb-1 |
| STORAGE-DBX-05 | kdb-1 spike (verify) + conditional kdb-1.5 (fix) |
| PREFLIGHT-DBX-01..02 | kdb-1 (must complete BEFORE spike) |
| SPIKE-DBX-01a..01e | kdb-1 spike |
| SYNC-DBX-01..02 | kdb-1 |
| SYNC-DBX-03 | kdb-3 |
| AUTH-DBX-01..05 | kdb-2 |
| SECRETS-DBX-01..04 | kdb-2 |
| SECRETS-DBX-05 | kdb-3 (audit) |
| DEPLOY-DBX-01..08 | kdb-2 (DEPLOY-07 requirements.txt + DEPLOY-08 LLM_PROVIDER lock authored before first deploy) |
| CONFIG-DBX-01..02 | kdb-3 (final audit) |
| QA-DBX-01..03 | kdb-3 |
| OPS-DBX-01..02 | kdb-2 (post-RUNNING smoke) |
| OPS-DBX-03..05 | kdb-3 |

**Total REQ count:** 36 (was 30 in v1 draft; net +6 = +PREFLIGHT-01/02 +SPIKE split adds 4 vs 1 = +4 +DEPLOY-07/08 = +2; STORAGE-04/SECRETS-05/CONFIG-01 in-place expansions)

## Last Updated

2026-05-15 — Revision 2 incorporating user P0/P1/P2 adjustments: SPIKE-DBX-01 split into 5 sub-items (01a-01e) covering FUSE / makedirs / SQLite WAL / cold-start / DeepSeek egress; new PREFLIGHT category (DBX-01 DeepSeek egress preflight + DBX-02 grant capability test) front-loaded into kdb-1 to surface highest-risk milestone blockers early; DEPLOY-DBX-07 requirements.txt + DEPLOY-DBX-08 OMNIGRAPH_LLM_PROVIDER=deepseek explicit lock; OPS-DBX-01..03 verbatim mirror KB-v2 Smoke 1/2/3; STORAGE-DBX-04 post-sync DB integrity check; SECRETS-DBX-05 audit broadened to `databricks-deploy/`; CONFIG-DBX-01 anchored to milestone-base commit `7df6e5b`; SPIKE 30-min hard timer + INCONCLUSIVE→kdb-1.5 auto-trigger rule. Total: 36 REQs across 10 categories.

2026-05-15 (rev 1) — Initial REQs drafted in main session by orchestrator (no roadmapper agent — express path per user direction). 30 REQs across 9 categories, mapped to 3 phases with conditional kdb-1.5.
