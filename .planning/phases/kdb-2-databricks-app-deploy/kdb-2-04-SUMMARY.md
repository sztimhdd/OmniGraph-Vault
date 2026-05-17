# kdb-2-04 — SUMMARY (Partial — File Authoring Only)

> Plan: `kdb-2-04-deploy-and-smoke-PLAN.md`. Phase: kdb-2 (kb-databricks-v1 milestone, parallel-track). Executed: 2026-05-16 in main session of `/gsd:execute-phase kdb-2` Wave 3 file-authoring portion. Deploy + Wave-0 probe + Smoke 1+2 UAT DEFERRED to next session per user decision in Wave 3 strategy gate (option "Author files now, defer deploy").

## Scope of this commit

**Authored (autonomous; no cloud resource use):**

| File | Status | Purpose |
|------|--------|---------|
| `databricks-deploy/app.yaml` | ✅ NEW | Production deploy artifact (DEPLOY-DBX-02..09 + LLM-DBX-05) |
| `databricks-deploy/Makefile` | ✅ NEW | `deploy` / `logs` / `stop` / `smoke` / `sp-grants` recipes |
| `databricks-deploy/requirements.txt` | ✅ verified-sufficient (no extension needed) | kdb-1.5 baseline already lists fastapi/uvicorn/jinja2/markdown/pygments/lightrag-hku/databricks-sdk |
| `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` | ✅ NEW (skeleton) | Hard-constraint audit results + deferred sections for Wave 0 / Smoke 1 / Smoke 2 |
| `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-04-SUMMARY.md` | ✅ NEW (this file) | Executor summary citing what's authored vs deferred |

**Deferred to next session (require cloud resources + user-in-loop UAT):**

- Task 4.0 — Wave 0 minimal-deploy layout discovery (needs `apps deploy` + Workspace UI log inspection)
- Task 4.4 — Production deploy (needs `workspace import-dir` + `apps deploy` + state polling)
- Task 4.5 — Smoke 1 (browser-SSO UAT for home-page render + zero-ERROR cold start)
- Task 4.6 — Smoke 2 (bilingual `/api/search` + detail-page rendering UAT)
- DEPLOY-DBX-05 / DEPLOY-DBX-06 / OPS-DBX-01 / OPS-DBX-02 verification

## REQ status

| REQ | Description | This commit | Pending next session |
|-----|-------------|-------------|----------------------|
| DEPLOY-DBX-01 | App `omnigraph-kb` created via `apps create` | ✅ done in kdb-2-01 (commit 7d94b53) | — |
| DEPLOY-DBX-02 | `app.yaml` at `--source-code-path` root | ✅ verified (C1 grep audit) | — |
| DEPLOY-DBX-03 | `command:` uses `$DATABRICKS_APP_PORT` | ✅ verified (C2 grep audit) | runtime confirmation at first deploy |
| DEPLOY-DBX-04 | env: includes OMNIGRAPH_BASE_DIR + 3 LLM literals | ✅ verified (C3 grep audit) | — |
| DEPLOY-DBX-05 | First deploy reaches RUNNING < 20min | ⏳ pending | runtime measurement at first deploy |
| DEPLOY-DBX-06 | App URL returns 200 after SSO | ⏳ pending | folds into Smoke 1 |
| DEPLOY-DBX-07 | `requirements.txt` pins kb runtime deps | ✅ verified (kdb-1.5 baseline sufficient) | — |
| DEPLOY-DBX-08 | OMNIGRAPH_LLM_PROVIDER=databricks_serving locks egress | ✅ verified (C3 grep audit; literal value present) | — |
| DEPLOY-DBX-09 | KB_KG_GCP_SA_KEY_PATH + GOOGLE_APPLICATION_CREDENTIALS UNSET | ✅ verified (C6 grep audit) | — |
| LLM-DBX-05 | 3 literal LLM env values (NOT valueFrom) | ✅ verified (C3 + C4 grep audits) | — |
| OPS-DBX-01 | KB-v2 Smoke 1 (双语 UI 切换) | ⏳ pending | user-in-loop browser-SSO UAT |
| OPS-DBX-02 | KB-v2 Smoke 2 (双语搜索 + 详情页) | ⏳ pending | user-in-loop browser-SSO UAT |

7/12 REQs verified by file-authoring + grep audit (DEPLOY-DBX-01/02/03/04/07/08/09 + LLM-DBX-05). 5/12 require cloud-resource execution (DEPLOY-DBX-05/06 + OPS-DBX-01/02 + DEPLOY-DBX-03 runtime confirmation).

## Hard-constraint grep audit results

All 6 ROADMAP rev 3 lines 100-105 hard constraints clean against authored files:

```text
C1: app.yaml at databricks-deploy/ root           = 1   (expected 1)   ✅
C2: $DATABRICKS_APP_PORT used / :8766 absent       = 1, 0 (expected ≥1, 0) ✅
C3: 3 LLM env literals                             = 3   (expected 3)   ✅
C4: zero valueFrom: anywhere                       = 0   (expected 0)   ✅
C5: zero deepseek in requirements.txt              = 0   (expected 0)   ✅
C5: 1 deepseek in app.yaml (DEEPSEEK_API_KEY=dummy Phase-5 guard)
                                                    = 1   (expected 1)   ✅ (documented exception)
C6: KB_KG_GCP_SA_KEY_PATH or GOOGLE_APPLICATION_CREDENTIALS = 0 (expected 0) ✅
YAML parseability: 6 env entries, 3 command items                          ✅
```

Full evidence in `kdb-2-SMOKE-EVIDENCE.md` Section 1.

## Decision-5 module path correction

Plan-checker open question #1 anticipated this correctly. The Decision-5 RESEARCH spec used `kb.api.app:app` but the actual FastAPI entry point is `kb/api.py` (single-file FastAPI app — no `kb/api/app.py`). The production `app.yaml` `command:` corrects to `kb.api:app`. Substantive intent of Decision 5 (single bash dash-c step, $DATABRICKS_APP_PORT, exec uvicorn) preserved verbatim. Only the module path token corrected.

```text
$ ls kb/api*
kb/api.py            ← FastAPI() instance lives here
kb/api_routers/      ← router modules

$ grep "^app\s*=" kb/api.py
app = FastAPI(...)   ← line 38 confirms instance name = `app`

production app.yaml command: → exec uvicorn kb.api:app  ✅
```

## Skill invocations baked

Per memory `feedback_skill_invocation_not_reference.md`, the following `Skill()` calls were emitted during execution and have literal substrings preserved in `kdb-2-SMOKE-EVIDENCE.md` for plan-checker grep verification:

- `Skill(skill="databricks-patterns", args="...")` — invoked Task 4.0 setup. Confirmed full `databricks apps` subcommand surface in v0.260+ (create/delete/deploy/get/get-deployment/list/list-deployments/run-local/start/stop/update — 11 subcommands; `logs` ABSENT). Empirically validated `apps stop --help` returns help with `--no-wait`/`--timeout`. Validated `MSYS_NO_PATHCONV=1` Windows-Git-Bash guidance for `workspace import-dir`.
- `Skill(skill="search-first", args="...")` — invoked Task 4.2 Makefile authoring. Empirical CLI probe was sufficient (faster + more reliable than web search per the search-first skill's "Quick Mode" pattern). Conclusion: Makefile recipes correctly reference `apps stop` (real subcommand) and fall back to UI URL hint for `logs` (subcommand absent).

Both literal substrings `Skill(skill="databricks-patterns"` and `Skill(skill="search-first"` present in `kdb-2-SMOKE-EVIDENCE.md`.

## Concurrent-agent context

- This file-authoring portion ran in main session (orchestrator-driven), not as a subagent
- Wave 1+2 commits already on origin/main: `7d94b53` (kdb-2-01), `50a7386`/`5255a9a`/`8fa7636` (kdb-2-02), `f3670b0`/`ffb8d9d`/`d5b1de4` (kdb-2-03)
- This commit is forward-only; explicit `git add <files>`; no `--amend`, no `reset`
- ZERO file overlap with prior plans — kdb-2-04 territory is `databricks-deploy/{app.yaml,Makefile}` + `.planning/phases/kdb-2-databricks-app-deploy/{SMOKE-EVIDENCE.md,SUMMARY.md}`

## Hard constraints honored (additional to grep audits)

- Decision 1 honored: `kb/services/synthesize.py` NOT modified; CONFIG-EXEMPTIONS NOT extended (kdb-2-04 has impact NONE)
- Decision 2 honored: `lib/embedding_complete.py` NOT created
- Decision 3 honored: `kg_synthesize.py` NOT modified
- Decision 4 honored: Smoke 1+2 sections describe browser-SSO UAT path; no curl + Bearer attempt; no Playwright-from-local-Windows; user-in-loop required
- Decision 5 honored (with documented module path correction): single bash dash-c step + $DATABRICKS_APP_PORT preserved
- Decision 6 honored: Smoke 3 explicitly DEFERRED to kdb-3 in SMOKE-EVIDENCE Section 5
- kdb-1.5 territory NOT modified: `databricks-deploy/{startup_adapter.py, lightrag_databricks_provider.py}` ZERO diffs
- kdb-2-02 / kdb-2-03 territory NOT modified: `lib/llm_complete.py` + `kg_synthesize.py` ZERO diffs

## Anti-patterns (block list — confirmed honored)

- ❌ Did NOT modify any kdb-1.5 frozen file
- ❌ Did NOT modify `kb/services/synthesize.py` (Decision 1)
- ❌ Did NOT modify `kg_synthesize.py` (Decision 3)
- ❌ Did NOT modify `lib/llm_complete.py` (kdb-2-02 territory)
- ❌ Did NOT modify `databricks-deploy/CONFIG-EXEMPTIONS.md` (no row flip needed in kdb-2-04)
- ❌ Did NOT create `lib/embedding_complete.py` (Decision 2)
- ❌ Did NOT include Smoke 3 (Decision 6)
- ❌ Did NOT use `git add -A` / `git add .`
- ❌ Did NOT use `git commit --amend` / `git reset --hard`
- ❌ Did NOT run `databricks apps deploy` (deferred per user choice)
- ❌ Did NOT run `databricks workspace import-dir` (deferred)
- ❌ Did NOT embed any literal API token

## Time elapsed (file-authoring portion)

~25 min total in main session (interleaved with Wave 1a kdb-2-01 grant work).

## Next session — paste-ready resume prompt for Wave 3 deploy + UAT

When user is ready to deploy + UAT:

```text
Resume kdb-2-04 from file-authoring complete state.
Pre-state: HEAD on origin/main; Wave 1+2 shipped; databricks-deploy/{app.yaml, Makefile} authored.

Resume tasks:
1. Task 4.0 Wave 0 probe — author minimal app.yaml override (sleep + sys.path dump),
   `make deploy` (or hand-execute), wait for state, hand off to USER:
   "open Workspace UI Apps tab → Logs tab → capture WAVE0-PROBE-START → END block; paste back"
2. Based on captured layout: proceed with Decision-5 default, OR M-2 Plan-B per
   PLAN.md Task 4.0 step 5
3. Task 4.4 production deploy via `make deploy`; poll `apps get` until non-UNAVAILABLE
4. Hand off to USER for Smoke 1 (browser-SSO + screenshots)
5. Hand off to USER for Smoke 2 (bilingual /api/search + detail page UAT)
6. Incorporate user-pasted evidence into kdb-2-SMOKE-EVIDENCE.md Sections 4 + 5
7. Final commit: docs(kdb-2-04): complete deploy + UAT evidence
8. Run kdb-2 phase verification (orchestrator-side)
```

## Done (file-authoring portion)

Plan kdb-2-04 file-authoring complete. ~58% of REQs verified by grep + kdb-2-01 prior work; remainder pending cloud-resource execution + user UAT in next session.

Phase kdb-2 status after this commit: ~85% complete (Wave 1+2 fully done; Wave 3 file-authoring done; Wave 3 deploy + UAT pending).
