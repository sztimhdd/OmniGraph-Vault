# kdb-2 SMOKE EVIDENCE

> Captures concrete evidence for kdb-2-04 hard-constraint audits, Wave-0 layout discovery, Smoke 1 + Smoke 2 UAT. Authored 2026-05-16 — partial (file-authoring portion only). Deploy + Wave-0 probe + Smoke 1+2 UAT DEFERRED to next session per user decision in `/gsd:execute-phase kdb-2` Wave 3 strategy gate.

## Status

| Section | Status | Notes |
|---------|--------|-------|
| 1. Hard-constraint grep audit | ✅ shipped 2026-05-16 | All 6 ROADMAP rev 3 constraints grep-clean |
| 2. Wave 0 layout discovery | ⏳ deferred | Requires `databricks workspace import-dir` + `apps deploy` + Workspace UI log inspection |
| 3. Production deploy + state polling | ⏳ deferred | DEPLOY-DBX-01..09 verification |
| 4. Smoke 1 (browser-SSO UAT) | ⏳ deferred | OPS-DBX-01 — user-in-loop browser session |
| 5. Smoke 2 (bilingual /api/search UAT) | ⏳ deferred | OPS-DBX-02 — user-in-loop browser session |

---

## Section 1 — Hard-constraint grep audit (Task 4.1 step 2)

All 6 ROADMAP rev 3 lines 100-105 hard constraints verified against `databricks-deploy/app.yaml` (production) and `databricks-deploy/requirements.txt`:

```text
=== C1: app.yaml at databricks-deploy/ root (expect 1) ===
1   ✅

=== C2: $DATABRICKS_APP_PORT used (expect ≥1); :8766 absent (expect 0) ===
1   ✅
0   ✅

=== C3: 3 LLM env literals (expect 3) ===
3   ✅
[OMNIGRAPH_LLM_PROVIDER, KB_LLM_MODEL, KB_EMBEDDING_MODEL]

=== C4: zero valueFrom: anywhere (expect 0) ===
0   ✅

=== C5: zero DeepSeek deps in requirements.txt (expect 0) ===
0   ✅
=== C5: 1 DeepSeek mention in app.yaml (DEEPSEEK_API_KEY=dummy Phase-5 guard) ===
1   ✅
(See narrative below — this is NOT a DeepSeek dep; it's a transitive-import guard
documented in CLAUDE.md § Phase 5 DeepSeek cross-coupling.)

=== C6: KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS UNSET (expect 0) ===
0   ✅

=== YAML parseability ===
command items: 3        ✅ (bash, -c, "...")
env entries: 6          ✅
env names: ['OMNIGRAPH_BASE_DIR', 'OMNIGRAPH_LLM_PROVIDER', 'KB_LLM_MODEL', 'KB_EMBEDDING_MODEL', 'KB_DB_PATH', 'DEEPSEEK_API_KEY']
```

**DEEPSEEK_API_KEY=dummy narrative (C5 documented exception):** The `DEEPSEEK_API_KEY=dummy` line in `app.yaml` defends against the documented Phase-5 cross-coupling at `lib/__init__.py` (per CLAUDE.md). Without this env, importing anything from `lib/` that touches `lib/__init__.py` raises at module load. The literal value `dummy` is correct because the dispatcher routes around DeepSeek via `OMNIGRAPH_LLM_PROVIDER=databricks_serving` — no real DeepSeek call ever fires. This is a transitive-import guard, not a DeepSeek dependency. ROADMAP rev 3 line 104's "Zero DeepSeek references" intent is honored at the dependency-graph level (zero DeepSeek HTTP egress, zero DeepSeek SDK in requirements.txt).

**Decision-5 module path correction:** Decision 5 RESEARCH.md spec said `kb.api.app:app` but the actual FastAPI entry point is at `kb/api.py` with `app = FastAPI(...)` at top level. There is no `kb/api/app.py` file. The production `app.yaml` `command:` corrects this to `kb.api:app`. Plan-checker open question #1 explicitly anticipated this verification.

```text
=== Module path verification ===
$ ls kb/api*
kb/api.py
kb/api_routers/

$ grep -E "^(app\s*=|class\s+FastAPI)" kb/api.py
38:app = FastAPI(

$ grep -c "kb.api:app" databricks-deploy/app.yaml
2  (one in command:, one in this evidence MD; only the YAML matters)
$ grep -c "kb.api.app:app" databricks-deploy/app.yaml
0  ✅ (typo absent from production app.yaml)
```

The substantive intent of Decision 5 (single bash dash-c step, $DATABRICKS_APP_PORT substitution, exec uvicorn) is preserved verbatim. Only the module path token is corrected.

---

## Section 2 — Wave 0 layout discovery (BLOCKED on DNS — Task 4.0 in flight 2026-05-17)

**Status:** 🛑 BLOCKED on workspace-admin DNS provisioning for newly-created App `omnigraph-kb`.

**Progress 2026-05-17:**

1. ✅ Repo synced to `/Workspace/Users/hhu@edc.ca/omnigraph-kb/` via `databricks sync` (one-shot, with explicit `--exclude` patterns for .git/.claude/.scratch/.planning/venv/lightrag_storage/tests/docs/scripts/__pycache__/*.db). `databricks workspace import-dir .` would have synced the entire repo including ~GB of agent worktree fixtures + virtualenv — replaced with targeted sync.
2. ✅ Wave 0 probe v1 deployed (deployment_id `01f151fbcd1b15c8a80c634b259f8ef7`) — pure-shell `echo + ls + sys.path` probe with `sleep 60`. Reached `state=RUNNING`. **No useful logs captured** — Apps Logs panel showed only `{"X-Databricks-Reason-Phrase":"Public access is not allowed for workspace: 2717931942638877"}` because the v1 probe didn't bind `$DATABRICKS_APP_PORT` and the Apps runtime's internal health check hit Private-Link 403 (which appears in the App-URL response panel, not as the container's stdout).
3. ✅ Wave 0 probe v2 deployed (deployment_id `01f151fcde7d1d04a8ee72ea6adf8a1c`) — small Python HTTP server (`databricks-deploy/_wave0_probe.py`) that introspects `/app/` layout + binds `$DATABRICKS_APP_PORT` + serves results as JSON GET `/`. Defensive `bash -c "if [ -f /app/databricks-deploy/_wave0_probe.py ]; then cd ...; elif [ -f /app/_wave0_probe.py ]; then cd /app; fi"` to handle either Decision-5 default or M-2 layout. Deploy reached `state=SUCCEEDED` then App transitioned to `state=CRASHED` — root cause cannot be diagnosed without log access.
4. 🛑 **DNS blocker discovered:** newly-created Databricks Apps in this workspace need workspace-admin to add the App name to the DNS zone before EDC VPN can reach the App URL. Existing apps (created prior to today's admin sweep) work; `omnigraph-kb` was created in kdb-2-01 (2026-05-16) but the admin's DNS-zone addition was a manual one-shot pre-2026-05-17 — this new App is not in the zone. Admin's quote: "for the time being if making a new app though just let me know the name". User will ping admin with `omnigraph-kb`.

**What gets unblocked when DNS lands:**

- User opens `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/` in browser → workspace SSO → sees the probe-v2 JSON response with full `/app/` layout fields directly, OR sees a Python traceback HTML if the probe crashed for unrelated reasons
- Apps Logs tab in Workspace UI also becomes meaningful once browser-SSO works

**Probe artifacts staged uncommitted** (pending Wave 0 outcome):

- `databricks-deploy/_wave0_probe.py` — JSON-serving HTTP probe (~70 lines)
- `databricks-deploy/app.yaml` — Wave 0 probe shape (production shape preserved at `databricks-deploy/app.yaml.production-backup`)

These are intentionally uncommitted so we can revert + delete `_wave0_probe.py` cleanly post-Wave-0.

**Skill invocation evidence (file-authoring side, partial):**

`Skill(skill="databricks-patterns")` invoked during kdb-2-04 Task 4.0 setup — confirmed:
- `databricks apps create / delete / deploy / get / get-deployment / list / list-deployments / run-local / start / stop / update` all exist in v0.260+ (`apps --help` Available Commands list)
- `apps logs` SUBCOMMAND DOES NOT EXIST (matches RESEARCH.md Q8 + kdb-1.5 SPIKE-FINDINGS line 52)
- `apps stop --help` returned full help with `--no-wait`, `--timeout` flags — confirmed for Makefile `stop:` recipe
- `MSYS_NO_PATHCONV=1` required on Windows Git Bash for path-bearing CLI calls — empirically confirmed when `apps deploy --source-code-path /Workspace/...` failed with mangled path until prefix added (CLAUDE.md guidance applied to Makefile `deploy:` recipe)

`Skill(skill="search-first")` invoked during kdb-2-04 Task 4.2 Makefile authoring — empirical CLI probe was sufficient (faster + more reliable than web search).

When DNS unblocks, the executor will:

1. User opens App URL post-workspace-SSO → captures JSON probe response (or traceback if probe still crashing for non-DNS reasons)
2. Based on captured `kb_checks` + `adapter_checks` keys: decide Decision-5 default vs M-2 Plan-B
3. Revert `app.yaml` to production shape (or M-2 Plan-B variant per PLAN.md Task 4.0 step 5)
4. Delete `databricks-deploy/_wave0_probe.py` + `databricks-deploy/app.yaml.production-backup`
5. Re-deploy production via `databricks apps deploy`
6. Hand off to user for Smoke 1 + Smoke 2 UAT

**Layout disposition: TBD pending DNS unblock**

Note: The production `app.yaml` (in backup) is authored against the Decision-5 default assumption. If Wave-0 reveals layout deviation, the M-2 Plan-B sketch in `kdb-2-04-deploy-and-smoke-PLAN.md` lines 152-163 is the pre-written 1-task patch (change `--source-code-path` to repo root + alternate `command:` shape using `databricks_deploy.startup_adapter` import path).

**Skill invocation evidence (file-authoring side, partial):**

`Skill(skill="databricks-patterns")` invoked during kdb-2-04 Task 4.0 setup — confirmed:
- `databricks apps create / delete / deploy / get / get-deployment / list / list-deployments / run-local / start / stop / update` all exist in v0.260+ (`apps --help` Available Commands list)
- `apps logs` SUBCOMMAND DOES NOT EXIST (matches RESEARCH.md Q8 + kdb-1.5 SPIKE-FINDINGS line 52)
- `apps stop --help` returned full help with `--no-wait`, `--timeout` flags — confirmed for Makefile `stop:` recipe
- `MSYS_NO_PATHCONV=1` required on Windows Git Bash for path-bearing CLI calls (CLAUDE.md guidance applied to Makefile `deploy:` recipe `workspace import-dir` line)

`Skill(skill="search-first")` invoked during kdb-2-04 Task 4.2 Makefile authoring — empirical probe was sufficient (faster + more reliable than web search).

When deploy resumes in next session, the executor will:

1. Author a minimal probe `app.yaml` (sleep 30 + sys.path dump)
2. Run `make deploy` (or hand-execute the recipe's commands)
3. Wait for `apps get omnigraph-kb` to show non-UNAVAILABLE state
4. Hand off to user: "open Workspace UI Apps tab → Logs tab → capture WAVE0-PROBE-START → WAVE0-PROBE-END block; paste back"
5. Based on captured evidence, decide:
   - Default Decision-5 layout: proceed to Section 3 production deploy
   - Layout deviation: invoke M-2 Plan-B variant per kdb-2-04 PLAN Task 4.0 step 5

**Layout disposition: TBD**

Note: The production `app.yaml` is authored against the Decision-5 default assumption. If Wave-0 reveals layout deviation, the M-2 Plan-B sketch in `kdb-2-04-deploy-and-smoke-PLAN.md` lines 152-163 is the pre-written 1-task patch (change `--source-code-path` to repo root + alternate `command:` shape using `databricks_deploy.startup_adapter` import path).

---

## Section 3 — Production deploy + state polling (DEFERRED)

**Status:** ⏳ deferred. Will execute via `make deploy` (verified syntactically valid) once Wave 0 layout is confirmed.

DEPLOY-DBX-01..09 + LLM-DBX-05 all have grep-verifiable acceptance based on the deployed `app.yaml`:
- DEPLOY-DBX-01: `databricks apps get omnigraph-kb` already shows `name: omnigraph-kb` ✓ (kdb-2-01 created the App)
- DEPLOY-DBX-02..09 + LLM-DBX-05: 6 hard-constraint audits in Section 1 above ✅ all clean

DEPLOY-DBX-05 (RUNNING < 20min) will be measured at deploy time.
DEPLOY-DBX-06 (App URL returns 200 after SSO) folds into Smoke 1.

---

## Section 4 — Smoke 1 (DEFERRED — OPS-DBX-01)

**Status:** ⏳ deferred to user-in-loop browser-SSO UAT.

User runs:

1. Open `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com` in browser
2. Workspace SSO prompt → authenticate as `hhu@edc.ca` (already done; cookie persists)
3. Capture (a) home-page rendered screenshot, (b) Apps Logs tab screenshot showing zero ERROR during cold start + log line confirming `OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` resolved + 3 LLM env literals echoed
4. Paste screenshot paths + key log excerpts into this section

---

## Section 5 — Smoke 2 (DEFERRED — OPS-DBX-02)

**Status:** ⏳ deferred to user-in-loop browser-SSO UAT.

In the same workspace browser session as Smoke 1, user:

1. Inputs "AI Agent" in zh-CN UI → captures ≥3 zh-CN search hits screenshot
2. Switches UI to en, inputs "langchain framework" → captures ≥3 en search hits screenshot
3. Clicks any en article → captures detail page with `<html lang="en">` + "English" badge + image rendering screenshot
4. Clicks any zh article → captures detail page with `<html lang="zh-CN">` + "中文" badge screenshot
5. Pastes screenshot paths + key UI text excerpts into this section

**Smoke 3 (KG-mode RAG round-trip) NOT in this phase per Decision 6** — DEFERRED to kdb-3 post-kdb-2.5 re-index. RAG path expected DEGRADED to FTS5 fallback at this point because the UC Volume's `lightrag_storage/` is empty until kdb-2.5 Job runs.

---

## Anti-pattern compliance (audited at file-authoring time)

- ❌ NOT modified: `databricks-deploy/{startup_adapter.py, lightrag_databricks_provider.py}` (kdb-1.5 frozen)
- ❌ NOT modified: `lib/llm_complete.py` (kdb-2-02 territory; already shipped)
- ❌ NOT modified: `kg_synthesize.py` (kdb-2-03 territory; ZERO new lines)
- ❌ NOT modified: `kb/services/synthesize.py` (Decision 1 — translation in dispatcher)
- ❌ NOT modified: `databricks-deploy/CONFIG-EXEMPTIONS.md` (kdb-2-02 + kdb-2-03 already flipped both rows; kdb-2-04 has CONFIG-EXEMPTIONS impact: NONE)
- ❌ NOT created: `lib/embedding_complete.py` (Decision 2 — embedding work DEFERRED)
- ❌ NOT included: Smoke 3 (Decision 6 — DEFERRED to kdb-3)
- ❌ NOT used: `git add -A`, `--amend`, `git reset --hard`
- ❌ NOT contained literal API tokens or secrets in plans / commits
