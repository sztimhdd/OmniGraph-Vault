---
phase: kdb-2
plan_id: kdb-2-04
slug: deploy-and-smoke
wave: 3
depends_on:
  - kdb-2-01
  - kdb-2-02
  - kdb-2-03
estimated_time: 0.5-1d
requirements:
  - DEPLOY-DBX-01
  - DEPLOY-DBX-02
  - DEPLOY-DBX-03
  - DEPLOY-DBX-04
  - DEPLOY-DBX-05
  - DEPLOY-DBX-06
  - DEPLOY-DBX-07
  - DEPLOY-DBX-08
  - DEPLOY-DBX-09
  - LLM-DBX-05
  - OPS-DBX-01
  - OPS-DBX-02
skills:
  - databricks-patterns
  - search-first
---

# Plan kdb-2-04 — `app.yaml` + Makefile + Deploy + Smoke 1+2 Browser-SSO UAT

## Objective

Author the deploy artifacts (`databricks-deploy/app.yaml`, `databricks-deploy/Makefile`, optional extension to `databricks-deploy/requirements.txt`), validate the source-code-path layout via a Wave-0 minimal-deploy smoke (RESEARCH.md Q7 MEDIUM-confidence flag), execute the production deploy of `omnigraph-kb`, and verify Smoke 1 (App URL renders + zero-ERROR cold start) + Smoke 2 (bilingual `/api/search` + detail-page rendering) via browser-SSO interactive UAT (Decision 4). Capture all evidence in `kdb-2-SMOKE-EVIDENCE.md`.

Maps to: 9 DEPLOY-DBX REQs + LLM-DBX-05 + 2 OPS-DBX REQs = 12 REQs total. Smoke 3 is DEFERRED to kdb-3 (Decision 6).

This plan IMPORTS the kdb-1.5 frozen artifacts (`startup_adapter.py` + `lightrag_databricks_provider.py`) and the kdb-2-02 dispatcher branch (`lib/llm_complete.py`); it does NOT modify them.

## Read-first

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q5 (lines 553-625) — Private Link constraint + Smoke verification path options + Decision 4 rationale
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q6 (lines 629-679) — cold-start budget projection (~55s for empty Volume) + DEPLOY-DBX-05 verification methodology
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q7 (lines 683-781) — `app.yaml` `command:` shape + source-code-path layout MEDIUM-confidence flag → Wave 0 minimal-deploy validation
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q8 (lines 785-911) — Makefile recipe surface + `databricks apps logs` absence + `databricks apps stop` TBD
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Decision 5 (lines 916-925) — locked `command:` shape per phase Decision 5
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-CONTEXT.md` § "Decision 4" + § "Decision 5" + § "Decision 6"
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 53-65 — DEPLOY-DBX-01..09 full text
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 49-50 — LLM-DBX-05 (3 literal env values)
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 151-165 — OPS-DBX-01 + OPS-DBX-02 verbatim Smoke 1+2
- `.planning/ROADMAP-kb-databricks-v1.md` lines 90-105 — kdb-2 success criteria + 6 hard constraints
- `databricks-deploy/startup_adapter.py` (full 133 lines) — kdb-1.5 frozen; `hydrate_lightrag_storage_from_volume()` is the entry point wired into `app.yaml` `command:`
- `databricks-deploy/lightrag_databricks_provider.py` (full 148 lines) — kdb-1.5 frozen; consumed by kdb-2-02 dispatcher branch at runtime
- `databricks-deploy/requirements.txt` (13 lines) — kdb-1.5 baseline; this plan may extend
- `lib/llm_complete.py` (post kdb-2-02; ~75-95 lines) — `databricks_serving` branch with translation shim
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (post kdb-2-02 + kdb-2-03) — both rows now `MODIFIED`
- CLAUDE.md "Windows / Git Bash Notes" — `MSYS_NO_PATHCONV=1` requirement for path-bearing CLI calls
- CLAUDE.md "GSD Workflow Enforcement" + "Databricks App Development" sections

## Scope

### In scope

- **Wave-0 minimal-deploy validation (NEW step before main deploy)** — per RESEARCH.md Q7 + Decision 5: deploy a minimal `app.yaml` with no-op `command:` (just `python -c "import sys; print(sys.path)"` + sleep) to confirm `--source-code-path /Workspace/.../omnigraph-kb/databricks-deploy` correctly mounts `databricks-deploy/` files at `/app/databricks-deploy/` AND that `/app/` ALSO contains the synced `kb/` tree (so uvicorn `kb.api.app:app` will resolve). If layout assumption fails, surface to user before doing the real deploy.
- Author `databricks-deploy/app.yaml` (NEW file) per Decision 5 locked `command:` shape:
  ```yaml
  command:
    - bash
    - -c
    - "cd /app/databricks-deploy && PYTHONPATH=/app:/app/databricks-deploy python -c 'from startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())' && exec uvicorn kb.api.app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT"

  env:
    - name: OMNIGRAPH_BASE_DIR
      value: "/tmp/omnigraph_vault"
    - name: OMNIGRAPH_LLM_PROVIDER
      value: "databricks_serving"
    - name: KB_LLM_MODEL
      value: "databricks-claude-sonnet-4-6"
    - name: KB_EMBEDDING_MODEL
      value: "databricks-qwen3-embedding-0-6b"
    - name: KB_DB_PATH
      value: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db"
    - name: DEEPSEEK_API_KEY
      value: "dummy"
  ```
  (The trailing `DEEPSEEK_API_KEY=dummy` defends against the documented `lib/__init__.py:35` Phase-5 cross-coupling per CLAUDE.md; this is NOT a DeepSeek dep — DeepSeek-DBX is fully retired in v1; the dispatcher routes to `databricks_serving` so no real DeepSeek call ever fires.)
- Author `databricks-deploy/Makefile` (NEW file) with recipes: `deploy`, `logs`, `stop` (with `search-first`-skill verified subcommand), `smoke` (manual checklist echo), `sp-grants` (informational; kdb-2-01 already executed grants but the recipe documents the audit pattern)
- Verify + extend `databricks-deploy/requirements.txt` if FastAPI/uvicorn/jinja2/markdown baseline needs additions to support the deployed `kb/` runtime (current baseline already lists FastAPI, uvicorn, jinja2, markdown, pygments — likely sufficient)
- Run `databricks --profile dev workspace import-dir . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite` to sync the whole repo (so `databricks-deploy/` AND `kb/` land under common parent)
- Run the production `databricks --profile dev apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy --timeout 20m`; capture wall-clock + log excerpt
- Poll `databricks --profile dev apps get omnigraph-kb -o json` until `compute_status.state == "ACTIVE"` (or `RUNNING`); record elapsed
- **Smoke 1 (browser-SSO UAT per Decision 4):** user opens `https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb` in browser, completes workspace SSO, captures (a) home-page rendered screenshot, (b) Apps Logs tab screenshot showing zero ERROR during cold start + log line confirming `OMNIGRAPH_BASE_DIR` resolved + 3 LLM env literals echoed
- **Smoke 2 (browser-SSO UAT per Decision 4):** in the same workspace browser session, user (a) inputs "AI Agent" in zh-CN UI → captures ≥3 zh-CN search hits screenshot; (b) switches UI to en, inputs "langchain framework" → captures ≥3 en search hits screenshot; (c) clicks any en article → captures detail page with `<html lang="en">` + "English" badge + image rendering screenshot; (d) clicks any zh article → captures detail page with `<html lang="zh-CN">` + "中文" badge screenshot
- Capture all screenshots into `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` (paste paths/links + verification narrative; user-in-loop)
- 6 hard-constraint grep audits (cited in `kdb-2-SMOKE-EVIDENCE.md`):
  1. `find databricks-deploy -maxdepth 1 -name app.yaml | wc -l` returns 1
  2. `grep -c "DATABRICKS_APP_PORT" databricks-deploy/app.yaml` ≥ 1; `grep -c ":8766" databricks-deploy/app.yaml` returns 0
  3. `grep -cE "OMNIGRAPH_LLM_PROVIDER|KB_LLM_MODEL|KB_EMBEDDING_MODEL" databricks-deploy/app.yaml` returns 3
  4. `grep -c "valueFrom:" databricks-deploy/app.yaml` returns 0
  5. `grep -ci "deepseek" databricks-deploy/requirements.txt` returns 0; `grep -ci "deepseek" databricks-deploy/app.yaml` returns 1 (only the `DEEPSEEK_API_KEY=dummy` line — clarify in evidence)
  6. `grep -cE "KB_KG_GCP_SA_KEY_PATH|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml` returns 0

### Out of scope

- Smoke 3 (KG-mode RAG round-trip) — Decision 6: DEFERRED to kdb-3 post-kdb-2.5 re-index
- AUTH grants (kdb-2-01 territory)
- LLM dispatcher work (kdb-2-02 territory)
- Integration tests (kdb-2-03 territory)
- Modifications to `kb/`, `lib/`, top-level `*.py` (CONFIG-DBX-01 — outside exemption list)
- Modifications to `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 frozen)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` modification (kdb-2-02 + kdb-2-03 already flipped both rows; nothing to add per Decision 1)
- Embedding dispatcher work (Decision 2 — DEFERRED)
- Aliyun deploy / Hermes operations
- `kdb-2.5` re-index Job

### CONFIG-EXEMPTIONS impact

NONE in this plan. CONFIG-EXEMPTIONS was fully updated by kdb-2-02 + kdb-2-03 (both rows MODIFIED). This plan adds NEW files exclusively under `databricks-deploy/` (`app.yaml`, `Makefile`) which are out-of-scope for CONFIG-DBX-01 by definition (CONFIG-DBX-01 only constrains `kb/` + `lib/` + top-level `*.py`).

## Tasks

### Task 4.0 — Wave-0 minimal-deploy validation (RESEARCH.md Q7 layout uncertainty)

**Read-first:**
- `kdb-2-RESEARCH.md` Q7 lines 762-781 — Risk: `app.yaml` location + `--source-code-path` semantics; recommended Wave 0 minimal-deploy validation
- `kdb-2-RESEARCH.md` Risk #5 lines 1001-1007 — concrete mitigation: deploy minimal `app.yaml` with no-op `command:` first
- CLAUDE.md "Windows / Git Bash Notes" — `MSYS_NO_PATHCONV=1` for path-bearing CLI on Windows

**Action:**

1. Invoke `Skill(skill="databricks-patterns")` with args `"Confirm: 'databricks --profile dev apps deploy <app-name> --source-code-path <workspace-path>' v0.260+ semantics. Specifically: when --source-code-path points at /Workspace/.../omnigraph-kb/databricks-deploy, does the Apps runtime mount the directory contents at /app/, or at /app/databricks-deploy/? Confirm whether sibling kb/ tree (synced via 'workspace import-dir' to a parent path /Workspace/.../omnigraph-kb) is also reachable from the App's filesystem at /app/kb/. Provide concrete app.yaml command: layout that resolves both relative imports of startup_adapter (top-level under databricks-deploy/) AND uvicorn-style imports of kb.api.app (top-level under kb/)."` — record skill output in `kdb-2-SMOKE-EVIDENCE.md` "Wave 0 layout discovery" section
2. Author a minimal `databricks-deploy/app.yaml` for the validation deploy:
   ```yaml
   command:
     - bash
     - -c
     - "echo 'WAVE0-PROBE-START'; pwd; ls -la; echo '---'; ls -la /app/ 2>&1; echo '---'; python -c 'import sys; print(\"WAVE0-SYS-PATH:\", sys.path)'; echo 'WAVE0-PROBE-END'; sleep 30"
   ```
   (no `env:` block needed yet — pure layout probe)
3. Sync repo + deploy minimal app.yaml:
   ```bash
   MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
   databricks --profile dev apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy --timeout 5m
   ```
4. After deploy, navigate to workspace UI Apps tab → omnigraph-kb → Logs tab; capture the WAVE0-PROBE-START → WAVE0-PROBE-END log block; specifically look for:
   - Working directory at `command:` invocation
   - Whether `/app/` shows `databricks-deploy/` AND `kb/` as sibling subdirectories OR whether `/app/` IS `databricks-deploy/` directly
   - `sys.path` contents — does it include `/app/`? `/app/databricks-deploy/`?
5. **Decision branch:**
   - **If layout shows `/app/{databricks-deploy, kb, ...}` (whole repo synced under `/app/`)** → Decision 5 `command:` shape works; proceed to Task 4.1
   - **If layout shows `/app/{startup_adapter.py, app.yaml, ...}` (only `databricks-deploy/` mounted at `/app/`, no `kb/` reachable)** → STOP. Capture full escalation report into `kdb-2-SMOKE-EVIDENCE.md` "Wave 0 layout escalation" subsection containing: (i) `pwd` output from probe, (ii) `ls -la /app/` recursive listing, (iii) `sys.path` contents (full list), (iv) the workspace import-dir manifest (`databricks --profile dev workspace list /Workspace/Users/hhu@edc.ca/omnigraph-kb --recursive`). Then escalate to **orchestrator** (NOT user — Decision 5 is locked; this is a planner re-litigation, not a user decision).

   **Plan-B sketch (lower-risk default — pre-written for orchestrator handoff):** Re-spawn planner with the layout-escalation evidence and instruct it to produce ONLY a 1-task patch revising kdb-2-04 Task 4.1. The expected revision: change the `--source-code-path` argument from `/Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy` (current) to `/Workspace/Users/hhu@edc.ca/omnigraph-kb` (repo root), and revise `app.yaml` `command:` to:

   ```yaml
   command:
     - bash
     - -c
     - "cd /app && PYTHONPATH=/app:/app/databricks-deploy python -c 'from databricks_deploy.startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())' && exec uvicorn kb.api.app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT"
   ```

   (Note: `databricks_deploy` import path uses underscore because `databricks-deploy` is the directory name but Python module path requires underscores; the `cd /app` change ensures `kb/` is on the working tree.) **Diff scope is identical to Decision-5 baseline:** still ONLY `databricks-deploy/app.yaml` + `databricks-deploy/Makefile`. Does NOT modify any kdb-1.5 deliverable (`startup_adapter.py`, `lightrag_databricks_provider.py`). Does NOT extend CONFIG-EXEMPTIONS. The locked-decision fidelity check at Task 4.7 still passes.

   Option (b) — Workspace files API runtime fetch — is REJECTED as Plan-B because it would require new code under `databricks-deploy/` (a runtime-fetch wrapper), which itself would need a new CONFIG-EXEMPTIONS audit + additional unit tests. Option (a) is strictly preferred.

6. Capture the chosen layout + `sys.path` contents into `kdb-2-SMOKE-EVIDENCE.md` "Wave 0 layout discovery" section. If escalation triggered, also populate "Wave 0 layout escalation" subsection per step 5 above.

**Acceptance** (grep-verifiable):
- `kdb-2-SMOKE-EVIDENCE.md` "Wave 0 layout discovery" section exists
- The section contains literal `WAVE0-PROBE-START` and `WAVE0-PROBE-END` markers from the captured log
- The section contains literal `Skill(skill="databricks-patterns"` (≥1 occurrence)
- The section explicitly states one of: `"Layout confirmed — Decision 5 command: shape proceeds"` OR `"Layout deviation — escalated to user"`

**Done:** Source-code-path + PYTHONPATH layout uncertainty (RESEARCH.md MEDIUM-confidence flag) is RESOLVED before authoring the production `app.yaml`.

**Time estimate:** 1.0h (CLI deploy + log inspection + decision capture).

### Task 4.1 — Author `databricks-deploy/app.yaml` (production)

**Read-first:**
- `kdb-2-RESEARCH.md` Q7 Decision 5 (lines 916-925) — locked production `command:` shape
- `kdb-2-RESEARCH.md` lines 710-756 — full app.yaml `env:` block sketch
- Wave-0 layout findings from Task 4.0 in `kdb-2-SMOKE-EVIDENCE.md`
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 49-50 (LLM-DBX-05) + lines 56-61 (DEPLOY-DBX-04/08/09)

**Action:**

1. Replace the Wave-0 minimal `databricks-deploy/app.yaml` with the production version:
   ```yaml
   # databricks-deploy/app.yaml — kdb-2-04 production deploy artifact.
   # Wires the kdb-1.5 storage adapter (databricks-deploy/startup_adapter.py)
   # into the App startup sequence, then exec's uvicorn against kb.api.app.
   #
   # REQs satisfied here:
   #   - DEPLOY-DBX-02: this file at root of --source-code-path
   #   - DEPLOY-DBX-03: command: uses $DATABRICKS_APP_PORT (NOT :8766)
   #   - DEPLOY-DBX-04: env: includes OMNIGRAPH_BASE_DIR + 3 LLM literals; no valueFrom: for any LLM env
   #   - DEPLOY-DBX-08: OMNIGRAPH_LLM_PROVIDER=databricks_serving locks egress to MosaicAI in-workspace
   #   - DEPLOY-DBX-09: KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS deliberately UNSET
   #   - LLM-DBX-05: 3 literal value: entries (NOT valueFrom:) for OMNIGRAPH_LLM_PROVIDER, KB_LLM_MODEL, KB_EMBEDDING_MODEL
   #
   # Locked decisions honored: phase Decision 5 (single bash -c step), Decision 1
   # (LLM-DBX-04 translation lives in lib/llm_complete.py, not in any kb/ edit
   # nor any new env var here).

   command:
     - bash
     - -c
     - "cd /app/databricks-deploy && PYTHONPATH=/app:/app/databricks-deploy python -c 'from startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())' && exec uvicorn kb.api.app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT"

   env:
     # OmniGraph runtime data dir — adapter copies UC Volume's lightrag_storage
     # into /tmp/omnigraph_vault/lightrag_storage (writable; LightRAG's mandatory
     # os.makedirs at storage init time succeeds).
     - name: OMNIGRAPH_BASE_DIR
       value: "/tmp/omnigraph_vault"

     # LLM dispatcher provider lock — DEPLOY-DBX-08 defends against any default-
     # DeepSeek code path making outbound calls to non-Databricks endpoints.
     - name: OMNIGRAPH_LLM_PROVIDER
       value: "databricks_serving"

     # MosaicAI Model Serving endpoint names (LLM-DBX-05).
     - name: KB_LLM_MODEL
       value: "databricks-claude-sonnet-4-6"

     - name: KB_EMBEDDING_MODEL
       value: "databricks-qwen3-embedding-0-6b"

     # KB FastAPI article query reads kol_scan.db direct from UC Volume in
     # read-only mode (kdb-1.5-RESEARCH Q4 confirmed FUSE + ?mode=ro URI).
     - name: KB_DB_PATH
       value: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db"

     # Defensive: pin DEEPSEEK_API_KEY=dummy to satisfy the Phase 5 cross-coupling
     # at lib/__init__.py:35 (CLAUDE.md § Phase 5). Without this, importing
     # anything from lib/ that touches lib/__init__.py raises at module load.
     # The literal value 'dummy' is correct because the dispatcher routes around
     # DeepSeek via OMNIGRAPH_LLM_PROVIDER=databricks_serving — no real DeepSeek
     # call ever fires. This is NOT a DeepSeek dep; it's a transitive-import guard.
     - name: DEEPSEEK_API_KEY
       value: "dummy"

     # NOTE: NO valueFrom: for ANY LLM-related env. Apps SP auto-injection
     # (DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET) carries Model Serving auth.
     # NOTE: KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS are
     # deliberately UNSET (DEPLOY-DBX-09). Vertex Gemini path retired in v1.
   ```
2. Run all 6 hard-constraint grep audits and capture results:
   ```bash
   echo "C1: app.yaml at databricks-deploy/ root"
   find databricks-deploy -maxdepth 1 -name app.yaml | wc -l
   echo "C2: $DATABRICKS_APP_PORT used; :8766 absent"
   grep -c "DATABRICKS_APP_PORT" databricks-deploy/app.yaml
   grep -c ":8766" databricks-deploy/app.yaml
   echo "C3: 3 LLM env literals"
   grep -cE "OMNIGRAPH_LLM_PROVIDER|KB_LLM_MODEL|KB_EMBEDDING_MODEL" databricks-deploy/app.yaml
   echo "C4: zero valueFrom: anywhere"
   grep -c "valueFrom:" databricks-deploy/app.yaml
   echo "C5: zero DeepSeek deps in requirements.txt; only the dummy guard in app.yaml"
   grep -ci "deepseek" databricks-deploy/requirements.txt
   grep -ci "deepseek" databricks-deploy/app.yaml
   echo "C6: KB_KG_GCP_SA_KEY_PATH and GOOGLE_APPLICATION_CREDENTIALS UNSET"
   grep -cE "KB_KG_GCP_SA_KEY_PATH|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml
   ```
3. Append the grep audit results to `kdb-2-SMOKE-EVIDENCE.md` "Hard-constraint grep audit" section. Expected results:
   - C1: 1
   - C2: ≥1, 0
   - C3: 3
   - C4: 0
   - C5: 0, 1 (the `DEEPSEEK_API_KEY=dummy` line — clarify in evidence narrative)
   - C6: 0

**Acceptance** (grep-verifiable):
- All 6 grep audits return the expected values listed above
- `kdb-2-SMOKE-EVIDENCE.md` "Hard-constraint grep audit" section contains all 6 results verbatim
- `databricks-deploy/app.yaml` exists and is YAML-parseable (`python -c "import yaml; yaml.safe_load(open('databricks-deploy/app.yaml'))"` returns no error)

**Done:** Production `app.yaml` authored; all 6 ROADMAP rev 3 hard constraints grep-verified.

**Time estimate:** 1.0h.

### Task 4.2 — Author `databricks-deploy/Makefile`

**Read-first:**
- `kdb-2-RESEARCH.md` Q8 (lines 785-911) — full Makefile recipe sketch
- `kdb-2-RESEARCH.md` Q8 line 826 — `databricks apps stop` TBD; verify with `search-first` skill before adding
- CLAUDE.md "Windows / Git Bash Notes" — `MSYS_NO_PATHCONV=1` for `workspace import-dir`

**Action:**

1. Invoke `Skill(skill="search-first")` with args `"Verify subcommand existence in Databricks CLI v0.260+: (a) does 'databricks apps stop <app-name>' exist? (b) does 'databricks apps logs <app-name>' exist? (c) does 'databricks serving-endpoints get-permissions <endpoint-name>' accept the endpoint name without --id flag? Search Databricks CLI release notes / GitHub repo for v0.260+ apps subcommand surface. Goal: Makefile recipes must reference real subcommands or fall back gracefully (e.g., 'apps logs' returns 'unknown command' → recipe echoes UI URL instead)."` — record skill output in `kdb-2-SMOKE-EVIDENCE.md` "Makefile subcommand discovery" section
2. Run hands-on probes locally:
   ```bash
   databricks --profile dev apps stop --help 2>&1 || echo "apps stop SUBCOMMAND-MISSING"
   databricks --profile dev apps logs --help 2>&1 || echo "apps logs SUBCOMMAND-MISSING"
   ```
   Capture results to `.scratch/kdb-2-04-cli-probe.log`. RESEARCH.md Q8 already confirmed `apps logs` is missing in v0.260.0.
3. Author `databricks-deploy/Makefile`:
   ```makefile
   # databricks-deploy/Makefile — kdb-2-04 deploy + ops recipes.
   # Targets: deploy / logs / stop / smoke / sp-grants
   # Uses --profile dev throughout (matches kdb-1.5 dry-run pattern).
   # Windows Git Bash safe: MSYS_NO_PATHCONV=1 only on path-bearing calls.

   .PHONY: deploy logs stop smoke sp-grants

   # Sync repo + deploy. --source-code-path points at databricks-deploy/ so
   # app.yaml is at the source-code-path root (DEPLOY-DBX-02 constraint).
   # The whole-repo workspace import is required so kb/ lands as a sibling
   # of databricks-deploy/ (Wave-0 validated layout per kdb-2-04 Task 4.0).
   deploy:
   	MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir \
   	  . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
   	databricks --profile dev apps deploy omnigraph-kb \
   	  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy \
   	  --timeout 20m
   	databricks --profile dev apps get omnigraph-kb -o json | \
   	  jq '{name, state: .compute_status.state, url, deployment_id: .active_deployment.deployment_id}'

   # Apps logs not exposed via CLI in v0.260.0 (kdb-1 SPIKE-FINDINGS line 52;
   # confirmed via search-first in kdb-2-04 Task 4.2). Recipe echoes UI URL
   # + queries deploy state via 'apps get'.
   logs:
   	@echo "Apps logs only via workspace UI Apps tab (databricks apps logs not in v0.260)."
   	@echo "URL: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
   	databricks --profile dev apps get omnigraph-kb -o json | \
   	  jq '{state: .compute_status.state, url, deployment_id: .active_deployment.deployment_id}'

   # 'databricks apps stop' subcommand existence verified via search-first +
   # local CLI probe in kdb-2-04 Task 4.2.
   stop:
   	databricks --profile dev apps stop omnigraph-kb

   # Smoke 1+2 manual UAT (Decision 4 — Private Link blocks external curl).
   # Recipe just echoes the workspace UI URL + the kdb-2-04 plan checklist.
   smoke:
   	@echo "Smoke 1+2 manual UAT (browser-SSO interactive UAT)."
   	@echo "Workspace UI: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
   	@echo "Checklist: see .planning/phases/kdb-2-databricks-app-deploy/kdb-2-04-deploy-and-smoke-PLAN.md § Tasks 4.5 + 4.6"
   	@echo "Capture screenshots to kdb-2-SMOKE-EVIDENCE.md."

   # Informational — kdb-2-01 already executed AUTH-DBX-01..04 grants.
   # This recipe documents the audit pattern (re-runnable; idempotent).
   sp-grants:
   	@CLIENT_ID=$$(databricks --profile dev apps get omnigraph-kb -o json | jq -r '.service_principal_client_id'); \
   	  echo "App SP client_id: $$CLIENT_ID"; \
   	  echo "AUTH-DBX-01..03 grants (run via mcp__databricks-mcp-server execute_sql):"; \
   	  echo "  GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO \`$$CLIENT_ID\`;"; \
   	  echo "  GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO \`$$CLIENT_ID\`;"; \
   	  echo "  GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO \`$$CLIENT_ID\`;"; \
   	  echo ""; \
   	  echo "AUTH-DBX-04 verification (Path A — may need fallback to Path B in-app probe):"; \
   	  databricks --profile dev serving-endpoints get-permissions databricks-claude-sonnet-4-6 || true; \
   	  databricks --profile dev serving-endpoints get-permissions databricks-qwen3-embedding-0-6b || true
   ```
4. Verify Makefile shape:
   ```bash
   make -n deploy 2>&1 | head -10
   ```

**Acceptance** (grep-verifiable):
- `databricks-deploy/Makefile` exists
- `grep -c '^\.PHONY:' databricks-deploy/Makefile` returns 1
- `grep -cE "^(deploy|logs|stop|smoke|sp-grants):" databricks-deploy/Makefile` returns 5 (5 targets)
- `grep -c "MSYS_NO_PATHCONV=1" databricks-deploy/Makefile` returns ≥1 (Windows-safe)
- `grep -c "databricks apps logs" databricks-deploy/Makefile` returns 0 (subcommand absent in v0.260; recipe echoes UI URL instead)
- `grep -c "databricks apps stop" databricks-deploy/Makefile` returns 1 (verified via search-first)
- `kdb-2-SMOKE-EVIDENCE.md` "Makefile subcommand discovery" section contains literal `Skill(skill="search-first"` (≥1 occurrence)

**Done:** Makefile authored with verified-existing subcommands; `apps logs` correctly substituted with UI URL echo.

**Time estimate:** 45 min.

### Task 4.3 — Verify + extend `databricks-deploy/requirements.txt` if needed

**Read-first:**
- `databricks-deploy/requirements.txt` (current 13 lines) — kdb-1.5 baseline
- `kb/api/app.py` (if it exists) or whichever module uvicorn loads — to enumerate runtime deps

**Action:**

1. Probe `kb/`-level imports the deployed app needs:
   ```bash
   grep -rh "^from \|^import " kb/api/ kb/services/ kb/data/ 2>/dev/null | sort -u | head -40
   ```
   Compare against current `databricks-deploy/requirements.txt`. Look for any non-standard import not covered (e.g., `pydantic`, `starlette` — likely transitively pulled by `fastapi`; explicit pin only if production-test reveals a missing module).
2. **If gaps found:** extend `databricks-deploy/requirements.txt` with the missing pins. **If no gaps:** leave file unchanged.
3. Verify DEPLOY-DBX-07 contract: `grep -ci "deepseek" databricks-deploy/requirements.txt` returns 0.
4. Document in `kdb-2-SMOKE-EVIDENCE.md` "requirements.txt verification" section either: "No extension needed — kdb-1.5 baseline covers production deps" OR list any added pins with rationale.

**Acceptance** (grep-verifiable):
- `grep -ci "deepseek" databricks-deploy/requirements.txt` returns 0
- `databricks-deploy/requirements.txt` lists at minimum: `fastapi`, `uvicorn`, `jinja2`, `markdown`, `pygments`, `lightrag-hku`, `databricks-sdk`, `numpy`
- `kdb-2-SMOKE-EVIDENCE.md` "requirements.txt verification" section exists with explicit "No extension needed" OR list of additions

**Done:** Production deps verified or extended. DEPLOY-DBX-07 grep audit clean.

**Time estimate:** 30 min.

### Task 4.4 — Production deploy + verify RUNNING + cold-start measurement

**Read-first:**
- `kdb-2-RESEARCH.md` Q6 lines 657-678 — concrete deploy + poll loop + log-excerpt-capture pattern
- Wave-0 layout findings from Task 4.0
- Production app.yaml from Task 4.1

**Action:**

1. Sync repo + deploy:
   ```bash
   START=$(date +%s)
   MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
   databricks --profile dev apps deploy omnigraph-kb \
     --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy \
     --timeout 20m 2>&1 | tee .scratch/kdb-2-04-deploy.log
   ```
2. Poll for RUNNING/ACTIVE state:
   ```bash
   for i in $(seq 1 30); do
     STATE=$(databricks --profile dev apps get omnigraph-kb -o json | jq -r '.compute_status.state')
     echo "iter=$i state=$STATE elapsed=$(($(date +%s)-START))s"
     if [ "$STATE" = "ACTIVE" ] || [ "$STATE" = "RUNNING" ]; then
       END=$(date +%s)
       echo "RUNNING at iter $i after $((END-START))s"
       break
     fi
     sleep 10
   done
   ```
   Capture `.scratch/kdb-2-04-poll.log`.
3. From the workspace UI Apps tab, capture:
   - Deploy timeline (deploy time + boot time + first-200 time)
   - Cold-start log excerpt showing the line `startup_adapter: skip source_empty_pre_seed src=...` (per RESEARCH.md Q6 line 651 — proves DEPLOY-DBX-04 wiring works AND the kdb-1.5 adapter empty-source branch fired correctly because the Volume's `lightrag_storage/` is empty pre-kdb-2.5)
   - Cold-start log excerpt showing the 3 LLM env literals were resolved (`OMNIGRAPH_LLM_PROVIDER=databricks_serving`, `KB_LLM_MODEL=...`, `KB_EMBEDDING_MODEL=...`)
4. Append all evidence to `kdb-2-SMOKE-EVIDENCE.md` "Production deploy" section:
   - Total elapsed deploy-to-RUNNING in seconds (expected < 60s realistic, < 20min budget per RESEARCH.md Q6)
   - Deploy log excerpt
   - App URL (from `apps get` JSON `.url` field)
   - Cold-start log excerpt with adapter line + env-literal echoes
5. **DEPLOY-DBX-05 check:** elapsed time < 1200s (20min budget). Anything > 60s realistic should be investigated but is not a hard fail (budget is 20min).

**Acceptance** (grep-verifiable):
- `databricks --profile dev apps get omnigraph-kb -o json | jq -r '.compute_status.state'` returns `ACTIVE` or `RUNNING`
- `databricks --profile dev apps get omnigraph-kb -o json | jq -r '.url'` returns a non-null URL ending in `azure.databricksapps.com`
- `kdb-2-SMOKE-EVIDENCE.md` "Production deploy" section contains:
  - Literal `state: ACTIVE` or `state: RUNNING`
  - Literal `startup_adapter:` substring (from cold-start log)
  - Literal `OMNIGRAPH_LLM_PROVIDER=databricks_serving` (from cold-start log echo OR from `app.yaml` excerpt — proves env was set)
  - Total elapsed time as integer seconds, < 1200

**Done:** App is RUNNING + reachable at its URL; cold-start adapter wiring verified via log; DEPLOY-DBX-01/02/03/04/05/08/09 + LLM-DBX-05 all grep-evidenced.

**Time estimate:** 45 min (deploy + poll + log-capture).

### Task 4.5 — Smoke 1: browser-SSO UAT (OPS-DBX-01 + DEPLOY-DBX-06 + AUTH-DBX-05 runtime confirmation)

**Read-first:**
- `kdb-2-RESEARCH.md` Q5 lines 582-624 — browser-SSO UAT methodology + 4-step user checklist
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 151-156 — OPS-DBX-01 verbatim Smoke 1
- `.planning/PROJECT-kb-databricks-v1.md` lines 124-130 — Smoke 1 acceptance criterion

**Action:**

This task is USER-IN-LOOP per Decision 4. The plan emits a paste-ready checklist; the user (or operator running the executor) actually drives the browser session. Capture screenshots into `.playwright-mcp/` if Playwright MCP is available, OR into a user-specified directory referenced from `kdb-2-SMOKE-EVIDENCE.md`.

**Smoke 1 user checklist (Decision 4 — browser-SSO UAT):**

1. Open the workspace UI Apps tab in your browser (already authenticated to workspace SSO via EDC SSO):
   `https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb`
2. The workspace UI proxy should render the App's home page WITHOUT a 403 (kdb-1 SPIKE-FINDINGS confirmed direct external `*.azure.databricksapps.com` URL is blocked by Private Link, but the workspace UI proxy resolves via internal DNS).
3. Verify default zh-CN UI renders. Capture screenshot → save as `.playwright-mcp/kdb-2-smoke1-1-home-zh.png` (or user-chosen path).
4. Click the language toggle in the upper-right → switch to en. Verify all UI strings (nav / labels / buttons / footer) render in English. Capture screenshot → `.playwright-mcp/kdb-2-smoke1-2-toggle-en.png`.
5. Refresh the page. Verify en preference persists via cookie (UI still English). Capture screenshot → `.playwright-mcp/kdb-2-smoke1-3-refresh-persist.png`.
6. Visit `<APP_URL>/?lang=zh` directly. Verify hard switch back to zh-CN; cookie syncs. Capture screenshot → `.playwright-mcp/kdb-2-smoke1-4-querystring-zh.png`.
7. In the workspace UI Apps tab, click the **Logs** sub-tab. Verify ZERO log entries with severity `ERROR` during the cold-start window. Capture screenshot of the Logs tab → `.playwright-mcp/kdb-2-smoke1-5-logs-zero-error.png`.
8. The Logs tab should also show the cold-start log lines from Task 4.4 (`startup_adapter: skip source_empty_pre_seed`, env literal echoes); confirm visually.
9. Append all 5 screenshot paths + verification narrative to `kdb-2-SMOKE-EVIDENCE.md` "Smoke 1" section.

**Acceptance** (grep-verifiable + image-evidence):
- `kdb-2-SMOKE-EVIDENCE.md` "Smoke 1" section exists
- Section contains at minimum 5 screenshot paths (1 per checklist step 3-7) with `.png` extensions
- Section explicitly states: "Smoke 1 PASS — bilingual UI toggle works; cookie persistence works; ?lang=zh hard-switch works; Apps Logs tab shows zero ERROR during cold start"
- Section confirms `OMNIGRAPH_BASE_DIR` resolved + 3 LLM env literals visible in cold-start logs (cross-reference Task 4.4 evidence)

**Done:** OPS-DBX-01 + DEPLOY-DBX-06 + AUTH-DBX-05 all confirmed via browser session.

**Time estimate:** 30-45 min (user-driven; plan emits the checklist; user runs through it).

### Task 4.6 — Smoke 2: browser-SSO UAT (OPS-DBX-02)

**Read-first:**
- `kdb-2-RESEARCH.md` Q5 + Decision 5 — browser UAT methodology
- `.planning/REQUIREMENTS-kb-databricks-v1.md` lines 158-163 — OPS-DBX-02 verbatim Smoke 2 (zh + en search + detail-page + image rendering)

**Action:**

Continue the same browser session from Smoke 1 (no need to re-SSO).

**Smoke 2 user checklist:**

1. In zh-CN UI mode, type "AI Agent 框架" into the search input → submit. Capture screenshot of results page → `.playwright-mcp/kdb-2-smoke2-1-search-zh.png`. Verify ≥3 zh-CN article hits (count shown or visible cards).
2. Switch UI to en. Type "langchain framework" into search → submit. Capture screenshot → `.playwright-mcp/kdb-2-smoke2-2-search-en.png`. Verify ≥3 English article hits.
3. Click any English article from the en search result → article detail page renders. Verify:
   - `<html lang="en">` (browser DevTools Inspect element OR view source)
   - "English" badge visible somewhere on the page
   - Original English content text visible
   - Inline images load successfully via `/static/img/...` URLs (i.e., FastAPI `StaticFiles` mount on UC Volume works — kdb-1.5-RESEARCH Q4 confirmed FUSE works for read-only access)
   Capture screenshot → `.playwright-mcp/kdb-2-smoke2-3-detail-en.png`.
4. Click any Chinese article from a fresh zh search → detail page renders with `<html lang="zh-CN">` + "中文" badge + original Chinese content. Capture screenshot → `.playwright-mcp/kdb-2-smoke2-4-detail-zh.png`.
5. Right-click any article on home page or detail page → "View page source" or DevTools → confirm `og:image` and `og:title` metadata are present (sharing renders preview). Capture screenshot of the meta tags → `.playwright-mcp/kdb-2-smoke2-5-meta.png`.
6. **Note (per Decision 6 + ROADMAP line 96):** Smoke 2's full RAG path expected DEGRADED to FTS5 fallback at this point — KG-mode is unavailable until kdb-2.5 re-indexes the LightRAG storage with Qwen3 embeddings. Smoke 3 (RAG round-trip) is DEFERRED to kdb-3 post-kdb-2.5. **This is expected behavior, NOT a failure.** Document explicitly in evidence.
7. Append all 5 screenshot paths + verification narrative + the FTS5-fallback note to `kdb-2-SMOKE-EVIDENCE.md` "Smoke 2" section.

**Acceptance** (grep-verifiable + image-evidence):
- `kdb-2-SMOKE-EVIDENCE.md` "Smoke 2" section exists
- Section contains at minimum 5 screenshot paths (`.png`)
- Section explicitly states: "Smoke 2 PASS — bilingual search works (≥3 hits each); detail pages render with correct lang attr + badge + image rendering via /static/img/..."
- Section explicitly states: "Smoke 3 DEFERRED to kdb-3 post-kdb-2.5 re-index — Smoke 2 exercises the FTS5 fallback path which is the expected v1 baseline before re-index"
- Section confirms image rendering specifically via `/static/img/...` URLs (per OPS-DBX-02 Databricks-specific add-on)

**Done:** OPS-DBX-02 confirmed via browser session; Smoke 3 deferral note documented.

**Time estimate:** 30-45 min (user-driven).

### Task 4.7 — Finalize `kdb-2-SMOKE-EVIDENCE.md` + commit

**Read-first:**
- All sections of `kdb-2-SMOKE-EVIDENCE.md` accumulated through Tasks 4.0-4.6
- `feedback_no_amend_in_concurrent_quicks.md` + `feedback_git_add_explicit_in_parallel_quicks.md`

**Action:**

1. Add a top-level summary table to `kdb-2-SMOKE-EVIDENCE.md` mapping each of the 12 REQs in this plan to its evidence section + status:

   | REQ | Evidence section | Status |
   |-----|------------------|--------|
   | DEPLOY-DBX-01 | Production deploy | ✅ App created |
   | DEPLOY-DBX-02 | Hard-constraint grep audit (C1) | ✅ |
   | DEPLOY-DBX-03 | Hard-constraint grep audit (C2) | ✅ |
   | DEPLOY-DBX-04 | Hard-constraint grep audit (C3) + Production deploy cold-start log | ✅ |
   | DEPLOY-DBX-05 | Production deploy elapsed time | ✅ (< 1200s) |
   | DEPLOY-DBX-06 | Smoke 1 home-page screenshot | ✅ |
   | DEPLOY-DBX-07 | requirements.txt verification | ✅ (grep deepseek = 0) |
   | DEPLOY-DBX-08 | Hard-constraint grep audit (C4) | ✅ |
   | DEPLOY-DBX-09 | Hard-constraint grep audit (C6) | ✅ |
   | LLM-DBX-05 | Hard-constraint grep audit (C3) | ✅ |
   | OPS-DBX-01 | Smoke 1 | ✅ |
   | OPS-DBX-02 | Smoke 2 | ✅ |

2. Add a "Decision-fidelity self-check" section confirming each of the 6 locked decisions was honored:
   - Decision 1: `kb/services/synthesize.py` NOT modified; `git diff <milestone-base>..HEAD -- kb/services/synthesize.py` returns empty
   - Decision 2: `lib/embedding_complete.py` does NOT exist; `ls lib/embedding_complete.py 2>&1` shows "No such file"
   - Decision 3: `kg_synthesize.py` ZERO net change; `git diff <kdb-2-02-commit>..HEAD -- kg_synthesize.py` returns empty
   - Decision 4: Smoke 1+2 verified via browser-SSO interactive UAT; screenshots captured
   - Decision 5: `app.yaml` `command:` shape uses single bash -c step + `$DATABRICKS_APP_PORT` substitution
   - Decision 6: Smoke 3 NOT in this plan; explicitly deferred to kdb-3 in Smoke 2 evidence section
3. Add a "Skill invocations" section listing the literal `Skill(skill="...")` substrings invoked during this plan (Task 4.0: databricks-patterns; Task 4.2: search-first; …) — each substring at least once for plan-checker grep
4. Stage explicitly: `git add databricks-deploy/app.yaml databricks-deploy/Makefile .planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` (plus `databricks-deploy/requirements.txt` if extended in Task 4.3)
5. Commit forward-only:
   ```
   feat(kdb-2-04): app.yaml + Makefile + production deploy + Smoke 1+2 evidence

   - databricks-deploy/app.yaml (NEW): single bash -c command: that runs the
     kdb-1.5 startup_adapter then exec's uvicorn against kb.api.app; env: with
     OMNIGRAPH_BASE_DIR + 3 LLM literals + KB_DB_PATH + DEEPSEEK_API_KEY=dummy
     guard. Zero valueFrom: for any LLM env (Apps SP injection carries auth).
   - databricks-deploy/Makefile (NEW): deploy/logs/stop/smoke/sp-grants targets;
     'apps logs' echoes UI URL (subcommand absent in v0.260.0).
   - kdb-2-SMOKE-EVIDENCE.md (NEW): Wave 0 layout discovery + production deploy
     timeline + 6 hard-constraint grep audits + Smoke 1 (5 screenshots) +
     Smoke 2 (5 screenshots) + Decision-fidelity self-check.

   REQs: DEPLOY-DBX-01..09 (9), LLM-DBX-05 (1), OPS-DBX-01 (1), OPS-DBX-02 (1) = 12

   Smoke 3 DEFERRED to kdb-3 post-kdb-2.5 re-index per phase Decision 6.
   ```

**Acceptance** (grep-verifiable):
- `kdb-2-SMOKE-EVIDENCE.md` contains the 12-row top-level REQ summary table
- Section "Decision-fidelity self-check" exists with all 6 decisions explicitly addressed
- Section "Skill invocations" contains literal `Skill(skill="databricks-patterns"` AND `Skill(skill="search-first"` (each ≥1 occurrence — frontmatter ↔ task invocation 1:1)
- `git log -1 --name-only` shows ONLY: `databricks-deploy/app.yaml`, `databricks-deploy/Makefile`, `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` (and optionally `databricks-deploy/requirements.txt`). **NOT** any `kb/`, `lib/`, top-level `*.py`. **NOT** `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py`.
- `git diff <milestone-base>..HEAD -- kb/services/synthesize.py` returns empty (Decision 1)
- `ls lib/embedding_complete.py 2>&1 | grep -c "No such file"` returns 1 (Decision 2)

**Done:** All 12 REQs satisfied + evidenced; plan kdb-2-04 ready for SUMMARY commit.

**Time estimate:** 45 min.

## Verification (what `kdb-2-04-SUMMARY.md` MUST cite)

1. Path to `kdb-2-SMOKE-EVIDENCE.md` containing the 12-row REQ summary table
2. The 6 hard-constraint grep audit results (C1-C6 verbatim)
3. App URL (from `apps get` JSON `.url` field)
4. Total deploy-to-RUNNING elapsed time in seconds (DEPLOY-DBX-05)
5. Cold-start log excerpt showing `startup_adapter:` line + the 3 LLM env literals
6. The 5 Smoke 1 screenshot paths
7. The 5 Smoke 2 screenshot paths
8. Decision-fidelity self-check (all 6 locked decisions confirmed)
9. Smoke 3 deferral statement to kdb-3
10. Embedding dim risk (Decision 2 + RESEARCH.md Risk #4) re-stated explicitly: "Smoke 1+2 use FTS5 fallback path; embedding code path NOT exercised; embedding-side dim mismatch risk DEFERRED to post-kdb-2 (see RESEARCH.md § Risks #4)"
11. Commit hash for forward-only audit
12. Skill invocation evidence — literal `Skill(skill="databricks-patterns"` AND `Skill(skill="search-first"` substrings (each ≥1 in SUMMARY.md)

## Hard constraints honored

This plan honors all 11 hard constraints from `kdb-2-CONTEXT.md`:

- **(ROADMAP rev 3 line 100)** `app.yaml` at root of `--source-code-path` — verified by C1 grep audit
- **(ROADMAP rev 3 line 101)** `command:` uses `$DATABRICKS_APP_PORT` (NOT `:8766`) — verified by C2 grep audit
- **(ROADMAP rev 3 line 102 + LLM-DBX-05)** 3 literal LLM env values in `app.yaml` `env:` — verified by C3 grep audit
- **(ROADMAP rev 3 line 103)** Zero `valueFrom:` for any LLM-related env — verified by C4 grep audit
- **(ROADMAP rev 3 line 104 + DEPLOY-DBX-07)** Zero DeepSeek deps in `requirements.txt`; clarified `DEEPSEEK_API_KEY=dummy` in `app.yaml` is a Phase-5 cross-coupling guard NOT a real DeepSeek dep — verified by C5 grep audit + evidence narrative
- **(ROADMAP rev 3 line 105)** LLM-DBX-02 diff scope — N/A in this plan (kdb-2-03 owns it; this plan touches no `kg_synthesize.py` lines)
- **(DEPLOY-DBX-09)** `app.yaml` does NOT set `KB_KG_GCP_SA_KEY_PATH` or `GOOGLE_APPLICATION_CREDENTIALS` — verified by C6 grep audit
- **(Decision 1)** LLM-DBX-04 implementation lives in `lib/llm_complete.py` (kdb-2-02 territory); `kb/services/synthesize.py` NOT modified by this plan
- **(Decision 2)** Embedding dim risk explicitly DEFERRED — re-stated in evidence MD
- **(Decision 4)** Smoke 1+2 use BROWSER-SSO INTERACTIVE UAT — Tasks 4.5 + 4.6
- **(Decision 6)** Smoke 3 explicitly DEFERRED to kdb-3 — Task 4.6 evidence statement
- **(kdb-1.5 territory)** `databricks-deploy/startup_adapter.py` + `databricks-deploy/lightrag_databricks_provider.py` NOT modified — verified by `git log -1 --name-only` showing only `app.yaml`, `Makefile`, `kdb-2-SMOKE-EVIDENCE.md` (+ optional `requirements.txt`)
- **(safety)** Forward-only commits via `git add <explicit-files>` only

## Anti-patterns (block list)

This plan MUST NOT:
- Run Smoke 3 (Decision 6 — kdb-3 territory)
- Grant `WRITE_VOLUME` to App SP (kdb-2-01 territory + AUTH-DBX-03 hard rule)
- Modify `kb/services/synthesize.py` (Decision 1)
- Modify `kg_synthesize.py` (Decision 3 — kdb-2-03 territory)
- Create `lib/embedding_complete.py` (Decision 2)
- Modify `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 frozen)
- Modify `lib/llm_complete.py` (kdb-2-02 territory)
- Add any DeepSeek client SDK to `requirements.txt` (DEPLOY-DBX-07 hard rule; only the `DEEPSEEK_API_KEY=dummy` env in `app.yaml` is allowed as Phase-5 cross-coupling guard, NOT a real dep)
- Use `valueFrom:` for any LLM-related env in `app.yaml` (Apps SP injection carries auth)
- Hardcode the App URL in `Makefile` recipes (use `databricks apps get` JSON output)
- Use `git commit --amend`, `git reset --hard`, or `git add -A`
- Embed any literal Foundation Model API token / secret in any commit
- Attempt external Bearer-token curl from outside the workspace (Decision 4 — Private Link blocks this; useless to try)
- Attempt Playwright MCP from local Windows for Smoke 1+2 (Decision 4 — corp network + Private Link both block this path)

## Estimated time total

0.5-1d (Task 4.0: 1.0h + Task 4.1: 1.0h + Task 4.2: 45 min + Task 4.3: 30 min + Task 4.4: 45 min + Task 4.5: 30-45 min + Task 4.6: 30-45 min + Task 4.7: 45 min + buffer ≈ 5.5-7.0h ≈ 0.7-1.0d). Lower bound assumes Wave-0 layout validation succeeds first try; upper bound includes one re-deploy if Wave-0 surfaces an issue.
